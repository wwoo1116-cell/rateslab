# -*- coding: utf-8 -*-
"""입찰 강도 — `Codex/rawData/src/strength.py` 를 **글자 그대로** 옮긴 것.

## 왜 그대로인가

이 파일은 판정을 만든다(같은 연물 52주 응찰률 백분위 → 등급). 옮기면서 손보면
발행 캘린더의 원본 화면과 sauron 의 화면이 같은 입찰에 다른 등급을 붙이는 날이
온다. 그래서 계산은 한 줄도 안 고쳤다 — 바꾼 것은 이 머리글뿐이다.

원본이 자기 규율을 아래 원래 docstring 에 적어 두었고, 그중 셋이 이 판정의 성격을
정한다:

    비교 단위는 줄이 아니라 **하루**    지표종목 교체기에 한 입찰이 두 줄로 갈린다
    같은 **연물**끼리만 견준다          2년물 중위 303% · 50년물 170% (실측)
    **표본 6회 미만이면 등급을 안 낸다** 백분위가 계단이라 숫자가 과장된다

## 되돌아가는 길

원본이 바뀌면 이 파일도 같이 바뀌어야 한다. 둘이 갈리면 같은 입찰에 두 판정이
생기고, 그건 화면이 아니라 데이터의 문제로 보인다.

---
입찰 강도 — 같은 연물의 과거 52주 입찰과 견줘 이번 입찰이 셌는지 본다.

**비교 단위는 줄이 아니라 하루다.** 지표종목 교체기(6개월마다)에는 신규발행과
통합발행이 같은 날 병행돼 한 입찰이 두 줄로 나뉜다(경과·신지표 두 종목을
같은 날 통합발행만 하는 날도 있다). 줄 단위로 견주면 그날
시장이 소화한 물량을 절반으로 세고, 응찰률도 종목별로 갈라져 과거의 한 줄짜리
입찰과 어긋난다. 그래서 **하루에 발행한 같은 연물을 한 건으로 합쳐** —
가중평균 낙찰금리와 총 발행액으로 눌러서 — 과거의 하루들과 견준다.

**왜 같은 연물끼리만 비교하나.** 응찰률은 연물마다 수준이 다르다. 실측
중위값이 2년물 303%, 50년물 170%다(2022-11~2026-08). 전체 평균과 견주면
2년물은 늘 강하고 50년물은 늘 약한 것으로 나온다 — 그건 수요가 아니라
만기의 성질이다.
미국 국채 시장도 응찰배수를 절대 수준이 아니라 **같은 만기의 직전 서너 회
평균과 견줘** 읽는다. 같은 관례다.

**왜 52주인가.** 금리 국면이 바뀌면 응찰률의 정상 범위도 통째로 이동한다.
3년을 다 쓰면 국면이 섞이고, 반년은 표본이 서너 개뿐이라 백분위가 의미를 잃는다.

**무엇을 어떻게 견주나.**

    응찰률(하루 합산)   백분위 -> 등급. 주 신호. 응찰배수가 높은 입찰 뒤
                        유통금리가 내린다는 실증이 근거다(Beetsma 외 2018,
                        J. Banking & Finance).
    총 발행액           평년(52주 중위) 대비 몇 % 많고 적은지 적는다. 1년 내
                        최대·최소면 그렇게 말한다. 등급에 섞지 않는다. 물량이
                        가격을 누르는 건 국채에서도 실증된 사실이다(Lou·Yan·
                        Zhang 2013, Rev. Financial Studies).
    가중평균 낙찰금리    직전 같은 연물 입찰 대비 몇 bp인지 적는다. 시장
                        코멘트가 낙찰금리를 읽는 표준이 "직전·민평 대비 bp"인데,
                        여기엔 민평이 없으니 직전 입찰이 잣대다. 1년 내 최고·
                        최저에 닿으면 그것도 적는다.
    낙찰금리 폭         곁들이. 최고 − 최저 = 낙찰된 응찰의 흩어짐. 실측 95%가
                        폭 0이라 벌어진 드문 날(1bp 이상)만 말한다. 흩어짐은
                        값에 대한 의견이 갈렸다는 뜻이다(Cammack 1991,
                        J. Political Economy).

금리 **수준**의 백분위는 만들지 않는다 — 그건 수요가 아니라 금리 국면이다.
셋을 하나의 점수로 합성하지도 않는다 — 가중치를 지어내야 하는데 근거가 없다.

판정은 **표본이 충분할 때만** 낸다. 6회 미만이면 백분위가 계단이라 숫자가
과장된다. 그때는 등급 대신 "표본 부족"이라고 말한다. 다만 직전 입찰 대비
bp는 두 숫자의 뺄셈이라 표본과 무관하게 적는다.
"""
from __future__ import annotations

import datetime as dt
import re

# 종목코드에서 연물을 뽑는다. `국고03000-2803` 은 표면금리 3.000%, 만기 28년 03월.
# 연물 자체는 코드에 없다 — 제목의 `2년물`·`30년물`·`물가채` 가 유일한 단서다.
TENOR = re.compile(r"(\d+)\s*년물|(물가|외평|국고)")


def tenor_of(row: dict) -> str | None:
    """비교 그룹 키. 제목의 `N년물` 이 우선, 없으면 종목코드의 종류."""
    t = str(row.get("제목") or "")
    m = re.search(r"(\d+)\s*년물", t)
    if m:
        return f"{m.group(1)}년"
    # 재정증권은 일물이다. 국고채 연물과 섞으면 안 되므로 따로 묶는다.
    m = re.search(r"(\d+)\s*일물", t)
    if m:
        return f"{m.group(1)}일"
    if "물가" in t:
        return "물가"
    if "외평" in t:
        return "외평"
    code = str(row.get("종목코드") or "")
    if code.startswith("물가"):
        return "물가"
    if code.startswith("외평"):
        return "외평"
    return None


def label_of(ten: str) -> str:
    """비교 그룹을 사람이 읽는 말로. `2년` -> `2년물`, `물가` -> `물가채`."""
    if ten.endswith("년") or ten.endswith("일"):
        return f"{ten}물"
    return f"{ten}채"


def _pct_rank(x: float, hist: list[float]) -> float:
    """x 가 hist 안에서 몇 백분위인가 (0~100). 같은 값은 절반으로 센다."""
    lo = sum(1 for h in hist if h < x)
    eq = sum(1 for h in hist if h == x)
    return 100.0 * (lo + eq / 2) / len(hist)


#: 백분위 -> 등급. 경계는 사분위다 — 지어낸 구간이 아니라 표본을 넷으로 가른 것.
#: 등급 말은 **수요**까지만 간다 [OWNER 2026-08-10 교과서 수준만] — 응찰률은
#: 수요÷공급이라는 산수라 "강한 수요"까지는 정의이고, 그것이 금리 강세로
#: 이어진다는 건 실증의 영역이다. 첫 칸(tone)은 화면 색을 고르는 내부 토큰.
def _grade(p: float) -> tuple[str, str, str]:
    if p >= 75:
        return ("강세", "강한 수요",
                "같은 연물 최근 1년에서 상위 25% 안에 드는 수요입니다.")
    if p >= 55:
        return "약강세", "다소 강한 수요", "평년보다 조금 나은 수요입니다."
    if p > 45:
        return "중립", "평년 수준", "응찰이 평년 수준입니다."
    if p > 25:
        return "약약세", "다소 약한 수요", "평년보다 조금 못한 수요입니다."
    return ("약세", "약한 수요",
            "같은 연물 최근 1년에서 하위 25%에 드는 수요입니다.")


MIN_N = 6


def _won(eok: float) -> str:
    """억원 숫자를 읽는 말로. 10000 -> `1.00조`, 8000 -> `8,000억`."""
    return f"{eok / 1e4:.2f}조" if eok >= 1e4 else f"{eok:,.0f}억"


def _amount(row: dict) -> float | None:
    """집계 가중치. 낙찰금액이 원칙, 없으면 입찰금액(전액 낙찰이 예사다)."""
    for k in ("낙찰금액", "입찰금액"):
        v = row.get(k)
        if v is not None:
            return float(v)
    return None


def _aggregate(day: dt.date, ten: str, members: list[dict]) -> dict:
    """하루에 발행한 같은 연물을 한 건으로 누른다.

    지표종목 교체기에는 신규발행·통합발행 두 종목이 같은 날 나온다. 물량은
    합치고, 금리는 발행액으로 가중평균하고, 응찰률은 응찰·입찰 합계로 다시
    구한다 — 종목별 응찰률의 단순평균은 물량이 다르면 틀린다.
    """
    tot = sum(a for a in (_amount(m) for m in members) if a is not None)
    bid = off = 0.0
    for m in members:
        o = m.get("입찰금액")
        if o is None:
            continue
        b = m.get("응찰금액")
        if b is None and m.get("응찰률") is not None:
            b = float(m["응찰률"]) * float(o) / 100
        if b is None:
            continue
        bid += float(b)
        off += float(o)
    rw = [(float(m["가중평균낙찰금리"]), _amount(m)) for m in members
          if m.get("가중평균낙찰금리") is not None and _amount(m) is not None]
    kinds = {k for m in members
             for k in ("신규발행", "통합발행", "선매출")
             if k in str(m.get("제목") or "")}
    return {
        "day": day, "tenor": ten, "members": members, "tot": tot, "kinds": kinds,
        "ratio": round(100 * bid / off, 1) if off else None,
        "wavg": (round(sum(r * w for r, w in rw) / sum(w for _, w in rw), 3)
                 if rw else None),
    }


def _median(xs: list[float]) -> float:
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def _row_notes(row: dict,
               peer_rows: list[dict]) -> tuple[list[str], float | None]:
    """종목 하나에만 해당하는 곁들이. (예외 문장들, 부분낙찰률 평년) 을 준다.

    부분낙찰률 평년은 수치라 필드로 내보낸다 — 화면이 카드의 부분낙찰 행에
    붙인다. 낙찰금리 폭(최고 − 최저)은 낙찰된 응찰들이 얼마나 흩어졌는가다.
    입찰 연구의 오랜 결과로, 응찰이 흩어질수록 값에 대한 의견이 갈렸다는
    뜻이고 발행자가 그만큼 비싸게 조달한다(Cammack 1991, J. Political
    Economy). **우리 실측으로는 95%의 입찰이 폭 0** — 그래서 평년과 견주지
    않고, 1bp 이상 벌어진 드문 날만 말한다.
    """
    notes: list[str] = []
    part_med = None
    if row.get("부분낙찰률") is not None:
        pl = [float(h["부분낙찰률"]) for h in peer_rows
              if h.get("부분낙찰률") is not None]
        if len(pl) >= MIN_N:
            part_med = round(_median(pl), 1)
    hi, lo = row.get("최고낙찰금리"), row.get("최저낙찰금리")
    if hi is not None and lo is not None:
        tail = (float(hi) - float(lo)) * 100
        if tail >= 1:
            notes.append(
                f"낙찰금리가 최저 {float(lo):.3f}%에서 최고 {float(hi):.3f}%까지 "
                f"{tail:.0f}bp 벌어졌습니다 — 낙찰이 한 값에 모이는 게 예사라, "
                "값을 보는 눈이 갈렸다는 뜻입니다.")
    return notes, part_med


def _analyse_unit(unit: dict, peers: list[dict]) -> dict:
    """하루치 한 건을 과거의 하루들과 견준다. `peers` 는 같은 연물·52주 안."""
    ten, label = unit["tenor"], label_of(unit["tenor"])
    legs = len(unit["members"])
    out: dict = {
        "tenor": ten, "label": label, "n": len(peers), "legs": legs,
        "ratio": unit["ratio"], "tot": round(unit["tot"]),
        "wavg": unit["wavg"],
        "median": None, "pct": None, "tone": None, "grade": None, "why": None,
        "totPct": None, "totMed": None,
        "wavgPrev": None, "wavgDelta": None, "prevDate": None,
        "notes": [],
    }

    # 쌍입찰 — 두 종목을 왜 한 건으로 보는지 그 자리에서 말한다. 교체기의
    # 신규+통합 병행이 대부분이지만, 두 종목을 같은 날 통합발행만 하는 날도
    # 있다(54회 중 13회) — 제목을 보고 맞는 문장을 고른다.
    # 합산 수치는 "이날 합계" 행이 보여 준다 — 문장은 왜 합치는지만 말한다.
    if legs >= 2 and unit["ratio"] is not None:
        out["notes"].append(
            ("지표종목 교체기라 신규발행과 통합발행이 같은 날 나왔습니다. "
             if unit["kinds"] & {"신규발행", "선매출"}
             else "두 종목이 같은 날 입찰됐습니다. ")
            + "물량·응찰은 두 종목 합계로 과거와 견줍니다.")

    # 가중평균 낙찰금리 — 직전 같은 연물 입찰 대비. 뺄셈이라 표본 수와 무관.
    # 수치는 필드로만 내보낸다(화면이 행으로 그린다) — 문장은 예외적 사실만.
    prev = next((p for p in reversed(peers) if p["wavg"] is not None), None)
    if prev is not None and unit["wavg"] is not None:
        bp = (unit["wavg"] - prev["wavg"]) * 100
        out.update({"wavgPrev": prev["wavg"], "wavgDelta": round(bp, 1),
                    "prevDate": prev["day"].isoformat()})
        rates = [p["wavg"] for p in peers if p["wavg"] is not None]
        if len(rates) >= MIN_N:
            if unit["wavg"] > max(rates):
                out["notes"].append(
                    f"최근 1년 {label} 입찰 중 가장 높은 금리입니다.")
            elif unit["wavg"] < min(rates):
                out["notes"].append(
                    f"최근 1년 {label} 입찰 중 가장 낮은 금리입니다.")

    hist = [p["ratio"] for p in peers if p["ratio"] is not None]
    if unit["ratio"] is None or len(hist) < MIN_N:
        out["grade"] = "표본 부족"
        out["why"] = (f"같은 {label} 최근 1년 입찰이 {len(hist)}회뿐이라 "
                      "강도를 판단하지 않습니다.")
        return out

    p = _pct_rank(unit["ratio"], hist)
    tone, grade, why = _grade(p)
    out.update({"median": round(_median(hist), 1), "pct": round(p),
                "tone": tone, "grade": grade, "why": why})

    # 총 발행액 — 물량 부담. 등급에 섞지 않는다. 평년 대비는 필드로만
    # 내보내고(화면이 행으로 그린다), 문장은 1년 내 최대·최소일 때만 쓴다.
    tots = [p_["tot"] for p_ in peers if p_["tot"]]
    if len(tots) >= MIN_N and unit["tot"]:
        med = _median(tots)
        out.update({"totPct": round(_pct_rank(unit["tot"], tots)),
                    "totMed": round(med)})
        if unit["tot"] > max(tots):
            out["notes"].append(
                f"최근 1년 {label} 중 가장 큰 하루 물량입니다.")
        elif unit["tot"] < min(tots):
            out["notes"].append(
                f"최근 1년 {label} 중 가장 작은 하루 물량입니다.")
    return out


def annotate(rows: list[dict], weeks: int = 52) -> list[dict]:
    """표 전체에 강도를 붙인다. 부르는 쪽이 매번 과거를 훑지 않게.

    같은 날·같은 연물의 경쟁입찰 줄들은 하루치 한 건으로 묶여 같은 판정을
    나눠 받는다. 곁들이 근거(부분낙찰률·응찰 상단)만 줄마다 따로 붙는다.
    """
    units: dict[tuple[dt.date, str], list[dict]] = {}
    for r in rows:
        r["강도"] = None
        if r.get("구분") != "경쟁입찰" or r.get("응찰률") is None:
            continue
        ten = tenor_of(r)
        if not ten:
            continue
        try:
            day = dt.date.fromisoformat(str(r["입찰일"])[:10])
        except (ValueError, KeyError, TypeError):
            continue
        units.setdefault((day, ten), []).append(r)

    by_tenor: dict[str, list[dict]] = {}
    for (day, ten), members in sorted(units.items(), key=lambda kv: kv[0][0]):
        by_tenor.setdefault(ten, []).append(_aggregate(day, ten, members))

    for ten, series in by_tenor.items():
        for i, unit in enumerate(series):
            since = unit["day"] - dt.timedelta(weeks=weeks)
            peers = [u for u in series[:i] if u["day"] >= since]
            shared = _analyse_unit(unit, peers)
            peer_rows = [m for u in peers for m in u["members"]]
            for r in unit["members"]:
                extra, part_med = _row_notes(r, peer_rows)
                r["강도"] = {**shared, "partMed": part_med,
                             "notes": shared["notes"] + extra}
    return rows


# ═══ 공개시장운영 ═══════════════════════════════════════════════════════
# **국고채와 같은 잣대를 쓸 수 없다.** 국고채는 응찰률이 높을수록 사려는 힘이
# 세다는 뜻이라 그대로 강세다. RP매각은 반대다 — 응찰이 몰린다는 건 은행에
# 굴릴 데 없는 여윳돈이 많다는 뜻이라, 같은 숫자가 정반대를 가리킨다.
#
# 그래서 **주 신호를 방향으로 바꾼다.** 한국은행이 돈을 풀었나 거뒀나는
# 해석이 필요 없는 사실이다. 등급도 그 수준에 머문다 — "유동성 공급/흡수"
# 까지가 정의이고, 그것이 채권 강세·약세로 이어진다는 건 실증의 영역이라
# 라벨에 박지 않는다 [OWNER 2026-08-10 교과서 수준만].
#
#     공급(RP매입·통안 중도환매)   자금이 시장으로 나간다
#     흡수(RP매각·통안증권·통안계정) 자금이 묶인다
#
# 응찰배율과 기준금리 스프레드는 **곁들이는 근거**로만 적는다. 셋을 합성해
# 하나의 점수로 만들려면 가중치를 지어내야 하는데 그 근거가 없다.

#: 구분 -> (방향, 무엇이 오갔는가). 제목이 아니라 이 표가 유일한 출처다.
OMO_DIR = {
    "RP매입": ("공급", "한국은행이 채권을 사고 돈을 풀었습니다"),
    "RP매각": ("흡수", "한국은행이 채권을 팔고 돈을 거뒀습니다"),
    "통안 중도환매": ("공급", "한국은행이 통안증권을 되사 돈을 풀었습니다"),
    "통안증권": ("흡수", "한국은행이 통안증권을 팔아 돈을 거뒀습니다"),
    "통안계정": ("흡수", "은행 자금이 한국은행 예치로 묶였습니다"),
}


def _aggregate_omo(day: dt.date, kind: str, members: list[dict]) -> dict:
    """하루의 같은 구분을 한 건으로 누른다.

    통안 중도환매·통안증권 발행은 한 날에 여러 종목(1·2·3년물)을 함께
    다룬다. 국고채와 같은 이유로 종목별로 따로 견주지 않는다 — 금액은
    합계, 금리는 낙찰금액 가중평균이 그날의 사실이다.
    """
    won = sum(float(m["낙찰금액"]) for m in members)
    bid = sum(float(m["응찰금액"]) for m in members
              if m.get("응찰금액") is not None)
    plan = sum(float(m["예정금액"]) for m in members
               if m.get("예정금액") is not None)
    rw = [(float(m["금리"]), float(m["낙찰금액"])) for m in members
          if m.get("금리") is not None and float(m["금리"]) > 0
          and m.get("낙찰금액") and float(m["낙찰금액"]) > 0]
    return {
        "day": day, "kind": kind, "members": members, "legs": len(members),
        "won": won, "bid": bid or None, "plan": plan or None,
        "rate": (round(sum(r * w for r, w in rw) / sum(w for _, w in rw), 3)
                 if rw else None),
    }


def _analyse_omo_unit(unit: dict, peers: list[dict],
                      base: float | None) -> dict | None:
    """하루치 한 건. 방향이 주 신호, 규모·응찰배율·스프레드가 근거.

    `base` 는 그날 유효한 기준금리(`mpc.csv` 에서 뽑아 넘긴다). 없으면 스프레드를
    적지 않는다 — 기준금리를 모르는 채로 `+85bp` 라고 쓸 수는 없다.
    """
    side, what = OMO_DIR[unit["kind"]]
    if not unit["won"]:
        return None  # 낙찰이 0 — 아무것도 오가지 않은 날은 판정할 것이 없다.
    kind, won, legs = unit["kind"], unit["won"], unit["legs"]
    out: dict = {
        "dir": side, "what": what, "kind": kind,
        "won": won, "n": len(peers), "legs": legs, "rate": unit["rate"],
        "sizePct": None, "sizeMed": None, "size": None,
        "cover": None, "coverMed": None,
        "spread": None, "base": base,
        "grade": f"유동성 {side}",
        "notes": [],
    }
    # 수치는 전부 필드로만 내보낸다 — 화면이 행으로 그린다. 문장을 여기
    # 더하는 건 예외적 사실이 생겼을 때뿐이다.

    # 규모 — 같은 구분의 하루끼리만 견준다. RP 는 조 단위, 통안계정은 천억
    # 단위라 섞으면 통안계정이 늘 '작은 규모' 가 된다. 표본이 모자라면
    # 평년 행이 안 그려지는 것으로 충분하다 — 사과문을 쓰지 않는다.
    amt = [p["won"] for p in peers if p["won"]]
    if len(amt) >= MIN_N:
        med = _median(amt)
        p = _pct_rank(won, amt)
        out.update({"sizePct": round(p), "sizeMed": round(med),
                    "size": "큰 규모" if p >= 75 else
                            "작은 규모" if p <= 25 else "보통 규모"})

    # 응찰배율 — 예정 대비 얼마나 몰렸나.
    # ★ 정정(2026-10-20): "중도환매는 예정액이 본문에 없다" 고 적혀 있었는데 **틀렸다.**
    #   본문 머리줄에 `매입예정금액 : 4,000억원` 이 있고 수집기가 그걸 버리고 있었다.
    #   이제 `총예정금액`·`총응찰금액`·`총낙찰금액` 열로 들어온다(종목별 `예정금액` 은
    #   여전히 빈칸이다 — 한은이 종목별로 쪼개 공표하지 않는다). 여기서 그 열을 쓰면
    #   v2 화면에 응찰배율 행이 새로 생기므로 **그 레인 세션에 넘긴다.** 봇은 자기
    #   쪽(`imx-brief/brief/issuance.py`)에서 총액 열을 직접 읽는다.
    if unit["plan"] and unit["bid"]:
        out["cover"] = round(unit["bid"] / unit["plan"], 2)
        cl = [p["bid"] / p["plan"] for p in peers
              if p.get("plan") and p.get("bid")]
        if len(cl) >= MIN_N:
            out["coverMed"] = round(_median(cl), 2)

    # 기준금리 스프레드 — 조작 금리가 정책금리에서 얼마나 떨어졌나.
    if unit["rate"] is not None and base is not None:
        out["spread"] = round((unit["rate"] - float(base)) * 100, 1)
    return out


def annotate_omo(rows: list[dict], base_at, weeks: int = 52) -> list[dict]:
    """`base_at(iso) -> 기준금리` 를 받아 표 전체에 강도를 붙인다.

    같은 날·같은 구분의 줄들은 하루치 한 건으로 묶여 같은 판정을 나눠 받는다.
    """
    units: dict[tuple[dt.date, str], list[dict]] = {}
    for r in rows:
        r["강도"] = None
        if str(r.get("구분") or "") not in OMO_DIR or r.get("낙찰금액") is None:
            continue
        try:
            day = dt.date.fromisoformat(str(r["일자"])[:10])
        except (ValueError, KeyError, TypeError):
            continue
        units.setdefault((day, str(r["구분"])), []).append(r)

    by_kind: dict[str, list[dict]] = {}
    for (day, kind), members in sorted(units.items(), key=lambda kv: kv[0][0]):
        by_kind.setdefault(kind, []).append(_aggregate_omo(day, kind, members))

    for kind, series in by_kind.items():
        for i, unit in enumerate(series):
            since = unit["day"] - dt.timedelta(weeks=weeks)
            peers = [u for u in series[:i] if u["day"] >= since]
            shared = _analyse_omo_unit(
                unit, peers, base_at(unit["day"].isoformat()))
            for r in unit["members"]:
                r["강도"] = shared
    return rows
