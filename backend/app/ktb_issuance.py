# -*- coding: utf-8 -*-
"""국고채 **발행** 통계 — SQL 판 [OWNER 2026-10-19].

「국고채 발행 통계도 SQL 에 있는 데이터 가져와서 연결」. Flow 세입자의 **셋째 면**
(「발행」)이고, 같은 자료가 현물 면의 **PD 인수 보정**(아래 §PD) 원천이다.

## 원천 — `infomax_API.ktb_auction_result` 한 표 (실측 2026-10-19 전수)

    1,812행 · 입찰일 2020-01-06 ~ 2026-10-19 (당일 10년 입찰이 02:35 에 들어와 있었다)
    구분  경쟁 690 · 비경쟁Ⅱ 538 · 비경쟁Ⅲ(스트립) 345 · 매입 186 · 일반인 53
    단위  **억원** (10-19 10년 입찰금액 21,000 = 2.1조) → 화면엔 **백만원**으로 ×100 해서
          내보낸다. 현물 수급(`flow.py`)이 백만원이라 두 면이 같은 자(`fmtEok`·`fmtJo`)를 쓴다.
    열쇠  (입찰일, isin, 구분) 중복 0 · 응찰률 = 응찰금액/입찰금액×100 전건 일치
    만기물 '2'·'3'·'5'·'10'·'20'·'30'·'50'·'물가' — **매입 186행은 NULL**이고 isin 으로 푼다
    갱신  `updated_at` 이 있다 → 워터마크. 2020-01~05 경쟁 33건은 응찰률이 비어 있다(판정 없음).

## 왜 Lab 발행 캘린더의 CSV 가 아니라 이 표인가

`issuance.py` 는 rawdata CSV(2022-11~)를 읽는다. 같은 원천(재정경제부)을 다른 경로로
읽은 것이고 겹치는 구간 국고채 경쟁 **427 대 407** 로 95% 겹친다 — CSV 는 재정증권
(63일물 등 110건)을 경쟁입찰로 같이 담고, 이 표는 국고채만 담는다. 이 모듈은 **SQL
한 원천**만 읽는다. 출처 둘을 섞으면 어긋남이 결함처럼 보인다(`flow.py` 머리 ⑤의 규율).

## 판정은 `issuance_strength.annotate` 그대로

같은 입찰에 두 판정이 생기면 안 된다(`test_issuance.py` 의 하중). SQL 열을 그 함수의
어휘로 옮기기만 한다 — 구분 '경쟁'→'경쟁입찰' · 낙찰금리→가중평균낙찰금리 · 기관수→
인수기관수. ★**제목은 직접 짓는다.** 원문 제목이 물가채를 「국고채 10년물 … 및
물가연동국고채 발행금리」로 적어서 `tenor_of()` 가 명목 10년과 한 바구니에 넣는다
(실측). 「물가채 경쟁입찰」처럼 지어 넘기면 그 함정이 없다. 문장은 `speak` 로 해요체.

## PD 인수 — 배분은 자료에 없다, 그래서 노브다 [OWNER]

현물 `ktb_investor` 는 **유통시장만** 적는다. 10-12 3년 입찰(2.4조) 당일 그 종목의
열 주체 순매수 합이 **0** 이다(금융투자 +686,999 · 은행 −583,611 · …). 발행시장에서
PD 가 받아 간 물량은 자료에 없다는 뜻이고, 그래서 금융투자의 순매도는 「받은 것을
푸는 것」인데 받은 쪽이 안 보인다.

PD 는 증권 11 · 은행 7(2026) 인데 **누가 얼마를 받았는지는 공표되지 않는다** → 배분은
가정이고 노브다(`pd_share` = 금융투자 몫, 은행은 나머지, 기본 0.6). 공급은
경쟁 낙찰 + 비경쟁Ⅱ + 비경쟁Ⅲ(스트립) − 매입(바이백). 일반인(53행 · 합 35억)은 PD 가
아니라 뺀다. 비경쟁은 행사기간(월~목)이 있고 표의 입찰일은 그 **마지막 날**이라
그 날에 귀속한다(실측: 비경쟁 입찰일 93% 가 목·금).

## 종목 → 만기물: `infomax.국채_발행정보`

489행(분리채 포함). `ROUND((만기일−발행일)/365.25)` 가 2·3·5·10·20·30·50 중 하나에
떨어진다 — `imx_data.bond_issues.tenor_class` 와 **89/89 일치**. 물가는 소분류
'물가연동국채'. 현물 164종목·매입 63종목 **전부** 덮는다(실측 2026-10-19).

## 산술은 DB 를 모른다

정규화·공급표·누적·면 조립은 전부 `_fetch` **밖**의 순수 함수다(`flow.py` 의 규율).
"""
from __future__ import annotations

import bisect
import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

from . import mysqldb
from .issuance_gloss import speak
from .issuance_strength import annotate as annotate_auctions

RESULT_TABLE = "`infomax_API`.`ktb_auction_result`"
SCHEDULE_TABLE = "`infomax_API`.`ktb_auction_schedule`"
MASTER_TABLE = "`infomax`.`국채_발행정보`"

#: 만기물 차례 — 화면 차례다.
TENORS = ("2Y", "3Y", "5Y", "10Y", "20Y", "30Y", "50Y", "물가")
LABEL = {
    "2Y": "2년물", "3Y": "3년물", "5Y": "5년물", "10Y": "10년물",
    "20Y": "20년물", "30Y": "30년물", "50Y": "50년물", "물가": "물가채",
}
_YEARS = (2, 3, 5, 10, 20, 30, 50)

KIND_COMP = "경쟁"
KIND_NONCOMP = ("비경쟁Ⅱ", "비경쟁Ⅲ(스트립)")
KIND_BUYBACK = "매입"
KIND_RETAIL = "일반인"
#: 공급으로 세는 구분 — PD 가 받아 가는 것.
PD_KINDS = (KIND_COMP,) + KIND_NONCOMP

EOK_TO_MIL = 100
#: 금융투자 몫 기본값. **가정**이다 — 화면이 그렇게 말한다.
DEFAULT_PD_SHARE = 0.6

_ISIN = re.compile(r"^[A-Z0-9]{12}$")


class IssuanceError(RuntimeError):
    """이 면을 그릴 수 없다."""


@dataclass(frozen=True)
class IssuanceData:
    """정규화된 입찰 행(강도 붙음) + 종목→만기물 + 앞의 일정. 산술 전의 날것이다."""
    rows: list[dict[str, Any]]
    tenor_of: dict[str, str]
    schedule: list[dict[str, Any]]
    watermark: tuple[str, int]


# ── 순수 산술 (DB 를 모른다) ────────────────────────────────────────────────

def tenor_bucket(issue: dt.date | None, maturity: dt.date | None,
                 sub: str | None) -> str | None:
    """종목 하나의 만기물. 분리채는 `None`(세지 않는다)."""
    if sub == "원금이자분리채권":
        return None
    if sub == "물가연동국채":
        return "물가"
    if issue is None or maturity is None:
        return None
    yrs = (maturity - issue).days / 365.25
    return f"{min(_YEARS, key=lambda y: abs(y - yrs))}Y"


def tenor_key(raw: str | None) -> str | None:
    """표의 `만기물` 열('3'·'물가') → 열쇠('3Y'·'물가')."""
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "물가":
        return "물가"
    return f"{s}Y" if s.isdigit() and int(s) in _YEARS else None


def _iso(d: Any) -> str | None:
    if d is None:
        return None
    return (d.date() if isinstance(d, dt.datetime) else d).isoformat()


def _f(v: Any) -> float | None:
    return None if v is None else float(v)


def normalize(raw: list[dict[str, Any]], tenor_of: dict[str, str]) -> list[dict[str, Any]]:
    """SQL 행 → 화면 어휘 + `annotate` 어휘. 강도까지 붙여 날짜 오름차순으로 돌려준다."""
    rows: list[dict[str, Any]] = []
    for r in raw:
        kind = str(r.get("구분") or "").strip()
        isin = r.get("isin")
        tenor = tenor_key(r.get("만기물")) or (tenor_of.get(isin) if isin else None)
        date = _iso(r.get("입찰일"))
        if not date or not kind:
            continue
        eok = _f(r.get("낙찰금액")) or 0.0
        rows.append({
            "date": date, "kind": kind, "tenor": tenor, "isin": isin,
            "name": str(r.get("종목명") or ""),
            "amount": eok * EOK_TO_MIL,
            "offered": None if r.get("입찰금액") is None else _f(r["입찰금액"]) * EOK_TO_MIL,
            "bid": None if r.get("응찰금액") is None else _f(r["응찰금액"]) * EOK_TO_MIL,
            "ratio": _f(r.get("응찰률")),
            "rate": _f(r.get("낙찰금리")),
            "rateLo": _f(r.get("최저낙찰금리")),
            "rateHi": _f(r.get("최고낙찰금리")),
            "partial": _f(r.get("부분낙찰률")),
            "inst": None if r.get("기관수") is None else int(r["기관수"]),
            "updated": _iso(r.get("updated_at")),
            # ── `issuance_strength.annotate` 의 어휘 (억원 그대로) ──
            "구분": "경쟁입찰" if kind == KIND_COMP else kind,
            "제목": f"{LABEL.get(tenor or '', '')} {kind}".strip(),
            "종목코드": str(r.get("종목명") or ""),
            "입찰일": date,
            "응찰률": _f(r.get("응찰률")),
            "입찰금액": _f(r.get("입찰금액")),
            "응찰금액": _f(r.get("응찰금액")),
            "낙찰금액": _f(r.get("낙찰금액")),
            "가중평균낙찰금리": _f(r.get("낙찰금리")),
            "최저낙찰금리": _f(r.get("최저낙찰금리")),
            "최고낙찰금리": _f(r.get("최고낙찰금리")),
            "부분낙찰률": _f(r.get("부분낙찰률")),
            "인수기관수": None if r.get("기관수") is None else int(r["기관수"]),
        })
    rows.sort(key=lambda x: (x["date"], x["kind"], x["name"]))
    annotate_auctions(rows)
    return rows


def supply_by_day(rows: list[dict[str, Any]], tenor: str = "ALL") -> dict[str, float]:
    """날짜 → 공급(백만원). 경쟁 + 비경쟁Ⅱ·Ⅲ − 매입. 일반인은 PD 가 아니라 안 센다."""
    out: dict[str, float] = {}
    for r in rows:
        if tenor != "ALL" and r["tenor"] != tenor:
            continue
        if r["kind"] in PD_KINDS:
            out[r["date"]] = out.get(r["date"], 0.0) + r["amount"]
        elif r["kind"] == KIND_BUYBACK:
            out[r["date"]] = out.get(r["date"], 0.0) - r["amount"]
    return out


def supply_table(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """`ALL` + 만기물마다의 공급표."""
    return {"ALL": supply_by_day(rows, "ALL"), **{k: supply_by_day(rows, k) for k in TENORS}}


def align_supply(dates: list[str], supply: dict[str, float]) -> tuple[list[float], int]:
    """공급을 **현물 날짜축**에 얹는다 — 그 날이 없으면 다음 있는 날로 넘긴다.

    돌려주는 둘째 값은 **아직 닿지 않은** 건수다: 현물 자료가 그 날에 아직 안 왔으면
    (오늘 입찰·현물 어제) 어디에도 못 얹는다. 지우지 않고 세어서 화면이 말한다.
    """
    out = [0.0] * len(dates)
    pending = 0
    for d, v in supply.items():
        i = bisect.bisect_left(dates, d)
        if i >= len(dates):
            pending += 1
            continue
        out[i] += v
    return out, pending


def cumulative(vals: list[float]) -> list[float]:
    out: list[float] = []
    run = 0.0
    for v in vals:
        run += v
        out.append(round(run, 1))
    return out


# ── 적재 (flow.py 와 같은 규율: 워터마크 키 캐시 + 주입 시임) ───────────────

_cached: IssuanceData | None = None
_injected: IssuanceData | None = None


def set_data(data: IssuanceData | None) -> None:
    global _injected
    _injected = data


def reset_cache() -> None:
    global _cached
    _cached = None


def watermark() -> tuple[str, int]:
    """두 표의 갱신 시각과 행 수를 잇는다 — 일정표만 바뀌어도 열쇠가 바뀌어야 한다."""
    with mysqldb.engine().connect() as conn:
        a = conn.execute(mysqldb.text(
            f"SELECT MAX(updated_at), MAX(입찰일), COUNT(*) FROM {RESULT_TABLE}")).one()
        s = conn.execute(mysqldb.text(
            f"SELECT MAX(updated_at), COUNT(*) FROM {SCHEDULE_TABLE}")).one()
    return (f"{a[0]}|{a[1]}|{s[0]}", int(a[2]) + int(s[1]))


def fetch_tenor_map(conn: Any) -> dict[str, str]:
    """`국채_발행정보` → {isin: 만기물}. 분리채는 빠진다. `flow.py` 도 이걸 쓴다."""
    rows = conn.execute(mysqldb.text(
        f"SELECT 표준코드, 발행일, 만기일, 인포맥스소분류 FROM {MASTER_TABLE}")).fetchall()
    out: dict[str, str] = {}
    for code, issue, mat, sub in rows:
        code = str(code or "").strip()
        if not _ISIN.match(code):
            continue
        b = tenor_bucket(
            issue.date() if isinstance(issue, dt.datetime) else issue,
            mat.date() if isinstance(mat, dt.datetime) else mat,
            None if sub is None else str(sub),
        )
        if b:
            out[code] = b
    return out


def _fetch() -> IssuanceData:
    with mysqldb.engine().connect() as conn:
        tenor_of = fetch_tenor_map(conn)
        raw = [dict(r._mapping) for r in conn.execute(mysqldb.text(
            f"SELECT * FROM {RESULT_TABLE} ORDER BY 입찰일 ASC, sn ASC")).fetchall()]
        sched = conn.execute(mysqldb.text(
            f"SELECT 입찰일, 만기물, 종목명, 발행예정액, 출처 FROM {SCHEDULE_TABLE} "
            "ORDER BY 입찰일 ASC")).fetchall()
    if not raw:
        raise IssuanceError(f"{RESULT_TABLE} 에서 행을 읽지 못했어요.")
    schedule = []
    for d, ten, name, planned, src in sched:
        iso = _iso(d)
        if not iso:
            continue
        k = tenor_key(ten)
        schedule.append({
            "date": iso, "tenor": k, "label": LABEL.get(k or "", str(ten or "")),
            "name": (str(name).strip() or None) if name else None,
            "planned": None if planned is None else float(planned) * EOK_TO_MIL,
            "source": str(src or ""),
        })
    return IssuanceData(rows=normalize(raw, tenor_of), tenor_of=tenor_of,
                        schedule=schedule, watermark=watermark())


def load() -> IssuanceData:
    """주입본이 있으면 그것, 없으면 SQL(워터마크 키 캐시). 디스크 캐시는 안 쓴다."""
    if _injected is not None:
        return _injected
    global _cached
    wm = watermark()
    if _cached is None or _cached.watermark != wm:
        _cached = _fetch()
    return _cached


# ── 화면이 읽는 한 장 ───────────────────────────────────────────────────────

def _unit(unit_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """같은 날·같은 만기물 경쟁입찰 묶음 하나(교체기엔 두 종목) → 화면 한 덩이.

    합산 수치는 `annotate` 가 이미 냈다(`강도.tot/ratio/wavg`). 여기선 자(억→백만원)와
    말투(해요체)만 바꾼다.
    """
    r0 = unit_rows[0]
    st = r0.get("강도") or {}
    tot = st.get("tot")
    return {
        "date": r0["date"], "tenor": r0["tenor"],
        "label": LABEL.get(r0["tenor"] or "", r0["tenor"] or "?"),
        "names": [r["name"] for r in unit_rows],
        "legs": len(unit_rows),
        "amount": (tot * EOK_TO_MIL) if tot is not None else sum(r["amount"] for r in unit_rows),
        "ratio": st.get("ratio", r0["ratio"]),
        "rate": st.get("wavg", r0["rate"]),
        "rateDelta": st.get("wavgDelta"),
        "prevDate": st.get("prevDate"),
        "grade": st.get("grade"),
        "pct": st.get("pct"),
        "median": st.get("median"),
        "tone": st.get("tone"),
        "n": st.get("n"),
        "totPct": st.get("totPct"),
        "totMed": None if st.get("totMed") is None else st["totMed"] * EOK_TO_MIL,
        "why": speak(st.get("why")),
        "notes": speak(st.get("notes") or []),
    }


def _same_day_prev_year(iso: str) -> str:
    y = int(iso[:4]) - 1
    return f"{y}{iso[4:]}"


def _tenor_row(key: str, rows: list[dict[str, Any]], asof: str) -> dict[str, Any]:
    year, month = asof[:4], asof[:7]
    mine = [r for r in rows if r["tenor"] == key]
    comp = [r for r in mine if r["kind"] == KIND_COMP]
    row: dict[str, Any] = {
        "key": key, "label": LABEL[key],
        "last": None,
        "ytd": sum(r["amount"] for r in comp if r["date"][:4] == year),
        "ytdNoncomp": sum(r["amount"] for r in mine
                          if r["kind"] in KIND_NONCOMP and r["date"][:4] == year),
        "ytdBuyback": sum(r["amount"] for r in mine
                          if r["kind"] == KIND_BUYBACK and r["date"][:4] == year),
        "ytdCount": len({r["date"] for r in comp if r["date"][:4] == year}),
        "ytdPrev": sum(r["amount"] for r in comp
                       if r["date"][:4] == str(int(year) - 1)
                       and r["date"] <= _same_day_prev_year(asof)),
        "mtd": sum(r["amount"] for r in comp if r["date"][:7] == month),
    }
    if comp:
        last_date = comp[-1]["date"]
        row["last"] = _unit([r for r in comp if r["date"] == last_date])
    return row


def _board(d: IssuanceData) -> dict[str, Any]:
    rows = d.rows
    comp = [r for r in rows if r["kind"] == KIND_COMP]
    if not comp:
        raise IssuanceError("경쟁입찰 행이 없어요.")
    asof = comp[-1]["date"]
    year = asof[:4]
    last = comp[-1]
    latest = _unit([r for r in comp if r["date"] == last["date"] and r["tenor"] == last["tenor"]])

    sup = supply_table(rows)
    dates = sorted(sup["ALL"])
    ytd_by_tenor = {k: sum(v for dd, v in sup[k].items() if dd[:4] == year) for k in TENORS}
    #: 그림엔 **최대 넷** — 올해 공급이 큰 순. 전수는 표가 진다(`flow.py` 와 같은 제약).
    picked = sorted(TENORS, key=lambda k: -ytd_by_tenor[k])[:4]
    unmapped = [r for r in rows if r["tenor"] is None and r["kind"] != KIND_RETAIL]

    excluded = [{
        "id": "retail", "label": "일반인",
        "why": "PD 가 아니라 공급에서 뺐어요 — 전 구간 합이 35억이에요.",
    }]
    if unmapped:
        excluded.append({
            "id": "unmapped", "label": f"만기물 미상 {len(unmapped)}건",
            "why": "종목을 만기물로 못 풀어서 만기물 표에선 빠지고 합계엔 들어 있어요.",
        })
    updated = max((r["updated"] or "" for r in rows), default=None) or None
    return {
        "asof": {"auction": asof, "updated": updated},
        "unit": "백만원",
        "since": comp[0]["date"],
        "count": len({(r["date"], r["tenor"]) for r in comp}),
        "latest": latest,
        "next": [s for s in d.schedule if s["date"] > asof][:3],
        "tenors": [_tenor_row(k, rows, asof) for k in TENORS],
        "year": {
            "label": year,
            "comp": sum(r["amount"] for r in comp if r["date"][:4] == year),
            "noncomp": sum(r["amount"] for r in rows
                           if r["kind"] in KIND_NONCOMP and r["date"][:4] == year),
            "buyback": sum(r["amount"] for r in rows
                           if r["kind"] == KIND_BUYBACK and r["date"][:4] == year),
            "compPrev": sum(r["amount"] for r in comp
                            if r["date"][:4] == str(int(year) - 1)
                            and r["date"] <= _same_day_prev_year(asof)),
        },
        "series": {
            "dates": dates,
            "cum": [{"key": k, "label": LABEL[k],
                     "values": cumulative([sup[k].get(dd, 0.0) for dd in dates])}
                    for k in picked],
            "daily": {"key": "ALL", "label": "발행 합계",
                      "values": [round(sup["ALL"].get(dd, 0.0), 1) for dd in dates]},
            "ma": None,
        },
        "pd": {
            "defaultShare": DEFAULT_PD_SHARE,
            "kinds": list(PD_KINDS),
            "note": "발행시장 인수분은 현물 수급 자료에 없어요 — 입찰 당일 그 종목의 "
                    "열 주체 순매수 합이 0 이에요. PD 배분은 공표되지 않아서 가정이고, "
                    "현물 면의 노브로 바꿔요.",
        },
        "excluded": excluded,
        "basis": "국고채 발행 통계예요 — 재정경제부 입찰 결과를 모은 것이고 새 판단이 "
                 "아니에요. 응찰 강도는 같은 만기물 최근 1년과 견준 백분위이고, "
                 "공급은 경쟁 낙찰에 비경쟁인수를 더하고 매입을 뺀 수예요.",
    }


def board() -> dict[str, Any]:
    """「발행」 면 한 장. 산술은 여기 하나다 — 화면은 읽고 칠하기만 한다."""
    return _board(load())
