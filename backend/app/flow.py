# -*- coding: utf-8 -*-
"""투자자별 수급 — **Strategy 네 번째 세입자**.

[OWNER 2026-10-16] 「선물+현물 둘 다 · 새 세입자」. 계획 정본은
`docs/PLAN_flow_tenant_2026-10-16.md`.

## 이 면이 **순위면이 아니라 대조면**인 까닭

투자자별 순매수는 **영합**이다 — 한쪽의 순매수가 다른 쪽의 순매도와 같다. 그래서
대분류(외국인·기관계·개인·기타)에 순위를 매기면 **매일 같은 두 줄**이 나온다.
실측(2026): 외국인과 기관계의 상관이 **3년 −0.9996 · 10년 −0.9992**이고, 둘의 합
(= 개인 + 기타)은 중위 176 / 114 계약이다. 그래서 대분류는 **대조**로 세우고,
순위는 기관계를 세분한 하위 분류가 진다 — 거기에만 진짜 경쟁이 있다.

## 순위 키 — **과거 분포 대비**, 그리고 하한 [OWNER 2026-10-19]

규모로 세우면 외국인·증권이 매일 1·2위라 화면이 날마다 같은 말을 한다. 자기
직전 252봉 분포 대비 당일 편차(σ)로 세운다 — 인접 세입자 Mean Reversion 이 밴드
대비 위치를 재는 것과 같은 결이다.

⚠ 그런데 **분모가 거의 0인 주체가 위로 올라온다**. 하한 없이 σ 로 세우면 3년
1위가 개인(−598계약), 10년 1위가 기타(+98계약)가 된다. 그래서 `RANK_FLOOR` 를
둔다. 실측 일평균 |순매수|(직전 252봉):

    3Y  외국인 8,399 · 기관계 8,324 · 증권 6,961 · 은행 3,805 · 투신 1,338 ·
        연기금 702 · 보험 570 │ 개인 225 · 기타 64 · 종금 27
    10Y 외국인 4,129 · 기관계 4,085 · 증권 3,461 · 은행 1,140 · 투신 589 ·
        보험 557 │ 연기금 314 · 개인 142 · 기타 40 · 종금 1

500 이 그 틈을 가른다. 면마다 순위 대상이 달라지는데 **자료가 정하는 것**이라
그대로 두고, 빠진 주체는 지우지 않고 `ranked: False` 로 같이 내보낸다.

## 함정 다섯 (계획 §1 — 전수로 다시 쟀다)

① **`INST`(기관계)는 동료가 아니라 상위 집합이다.**
   `INST = SECU + TRUST + BANK + INSUR + MERCH + PENS` 가 **5,288행 전부에서
   오차 0**. 두 층을 같이 더하면 기관을 두 번 센다.
② **`ETCQUANTITY` 칼럼이 없다.** `ETCPRICE / CLOSE` 로 역산하면 안 된다 —
   `CLOSE` 는 후방 조정된 연속 계열이라 수준이 없다(`futures.py` 머리, 3Y 중위
   89.5bp 틀림). **영합 폐쇄**로 구한다: `ETC = −(INST + FRGN + INDI + GOVT)`.
③ **`GOVT`(정부)는 죽은 칼럼이다** — 전 구간 0. `excluded` 에 적고 뺀다.
④ **현물에 중복 22,775조합**(`date,isin,market,buysell` 기준). `deal_time`
   최대값 행 한 장만 쓴다.
⑤ **현물 은행이 bis 와 안 맞는다**(10-15 장외매수 969,935 vs 790,102). 외국인·
   보험은 맞는다. 원인 미확인 — 이 모듈은 `ktb_investor` 한 원천만 읽고, 대사는
   레인의 다음 걸음이다.

## 두 원천의 `asof` 가 **다른 것이 정상**이다 [OWNER 2026-10-19]

현물이 선물보다 늦게 들어온다. 실측(2026-10-19 10:11): 선물은 금요일(10-16)치를
08시대에 받았고 현물은 아직 10-15 였다. **결측이 아니라 안 온 것**이다. 그래서
`watermark()` 가 두 표를 잇는 **복합**이어야 한다 — 한쪽만 세면 다른 쪽이 들어와도
캐시 열쇠가 안 바뀐다.

## 종가 기준이다 — 일중 틱 없음

`infomax_API.investor_intra` 는 오늘치까지 있지만 `underlying` 이 **빈 문자열**이라
계약코드를 못 푼다. 일중은 별도 레인이다.

## 산술은 DB 를 모른다

영합 폐쇄·누적·편차·순위는 전부 `_fetch` **밖**의 순수 함수다. SQL 없이 잴 수 있어야
시험이 자료에 안 붙는다(`paperlive.py` 의 그 규율).
"""
from __future__ import annotations

import datetime as dt
import statistics as st
from dataclasses import dataclass
from typing import Any

from . import mysqldb

#: 선물 투자자별 — 이 리포가 처음 읽는 칼럼들. 같은 표의 `CLOSE` 는 `futures.py` 가 읽는다.
FUT_TABLE = "sim_portfolio.mkt_futures_investor_close"
#: 현물 투자자별 — 데스크의 인포맥스 창고. 대소문자가 섞여 백틱으로 묶는다.
CASH_TABLE = "`infomax_API`.`ktb_investor`"

#: 선물 **대분류** — 서로 더하면 0. `ETC` 는 칼럼이 없어 영합으로 닫는다(함정 ②).
FUT_TOP: list[tuple[str, str]] = [
    ("FRGN", "외국인"), ("INST", "기관계"), ("INDI", "개인"),
]
#: 선물 **기관계 세분** — 이 여섯의 합이 `INST` 다(함정 ①).
FUT_SUB: list[tuple[str, str]] = [
    ("SECU", "증권"), ("TRUST", "투신"), ("BANK", "은행"),
    ("INSUR", "보험"), ("MERCH", "종금"), ("PENS", "연기금"),
]
#: 전 구간 0 인 죽은 칼럼(함정 ③). 영합 폐쇄에는 넣고 화면에선 뺀다.
FUT_DEAD = "GOVT"

FUT_TENORS = ("3Y", "10Y")

#: 현물 주체 열 — 계층이 없다(선물과 달리 상위 집합이 없다).
CASH_COLS: list[tuple[str, str]] = [
    ("financial_investment", "금융투자"), ("foreigner", "외국인"),
    ("insurance", "보험"), ("asset_management", "자산운용"),
    ("bank", "은행"), ("individual", "개인"),
    ("fund_or_mutual_aid", "기금공제"), ("government_or_municipal", "국가지자체"),
    ("other_corporate", "기타법인"), ("other_financial", "기타금융"),
]

#: 편차를 재는 창(영업일). 계열 자기이력이라 `creditdts.WINDOW` 와 같은 눈금이다.
WINDOW = 252
#: 편차를 내려면 창 안에 이만큼은 있어야 한다.
MIN_OBS = 120
#: ★순위 하한(계약/일). 위 §순위 키의 실측이 근거다 — 이 아래는 분모가 거의 0이라
#: σ 가 폭발한다. **고정하고 화면에 적는다**(`creditdts.FLOOR_BP` 와 같은 자세).
RANK_FLOOR = 500.0
#: 현물 하한(백만원/일). 단위가 다르니 수도 다르다.
#:
#: ⚠**선물처럼 깨끗한 틈이 없다.** 직전 252봉 일평균 |순매수|(백만원) 실측:
#:
#:     개인 24,162 · 기타금융 34,924 · 국가지자체 49,450 │ 기타법인 65,841 ·
#:     보험 132,113 · 자산운용 173,878 · 기금공제 211,689 · 은행 417,606 ·
#:     외국인 498,461 · 금융투자 794,719
#:
#: 선물 쪽은 570 과 225 사이가 2.5배라 500 이 안전했는데, 여기서 가장 넓은 틈은
#: 34,924→49,450 의 **1.42배**뿐이다. 50,000 으로 두면 국가지자체(49,450)가
#: 하한에서 1% 아래라 **날마다 뒤집힌다** — 그래서 그 틈의 가운데로 내린다
#: (기하평균 41,560). 지금 여유는 아래쪽 15% · 위쪽 24%.
CASH_RANK_FLOOR = 40_000.0


class FlowError(RuntimeError):
    """이 화면을 그릴 수 없다."""


@dataclass(frozen=True)
class FlowData:
    """두 원천의 **일별 순매수**. 산술 전의 날것이다."""
    #: 만기 → (날짜, 주체키 → 값). 주체키는 `FUT_TOP`+`FUT_SUB`+`GOVT`+`ETC`.
    fut: dict[str, tuple[list[str], dict[str, list[int]]]]
    #: (날짜, 주체키 → 값). 단위 **백만원**.
    cash: tuple[list[str], dict[str, list[int]]]
    watermark: tuple[str, int]


# ── 순수 산술 (DB 를 모른다) ────────────────────────────────────────────────

def close_zero_sum(top: dict[str, int]) -> int:
    """`ETC` — 영합 폐쇄로 구한다(함정 ②). 가격이 아예 필요 없다."""
    return -(top.get("INST", 0) + top.get("FRGN", 0)
             + top.get("INDI", 0) + top.get(FUT_DEAD, 0))


def inst_identity_error(row: dict[str, int]) -> int:
    """`INST − (여섯의 합)`. **0 이어야 한다**(함정 ①, 5,288행 실측)."""
    return row.get("INST", 0) - sum(row.get(k, 0) for k, _ in FUT_SUB)


def cumulative(vals: list[int]) -> list[int]:
    """누적 순매수. 길이는 그대로."""
    out: list[int] = []
    run = 0
    for v in vals:
        run += v
        out.append(run)
    return out


def sigma_of(hist: list[int], today: int) -> tuple[float | None, float]:
    """(편차, 일평균 |순매수|) — 창은 **오늘을 뺀** 직전 `WINDOW` 봉.

    오늘을 넣으면 그날이 제 분모를 키워 편차가 줄어든다. 「평소 대비 오늘」이라는
    질문에 오늘이 들어가면 안 된다.
    """
    w = hist[-WINDOW:]
    if len(w) < MIN_OBS:
        return None, 0.0
    avg = st.mean(abs(v) for v in w)
    sd = st.pstdev(w)
    if sd <= 0:
        return None, avg
    return round(today / sd, 2), avg


def rank_rows(rows: list[dict[str, Any]], floor: float) -> list[dict[str, Any]]:
    """편차 큰 순. **하한 아래는 순위 밖**이고 지우지 않는다(위 §순위 키).

    순위를 못 받은 줄은 뒤에 서고 `rank` 가 `None` 이다 — 「없다」와 「0등」은
    다른 말이다.
    """
    for r in rows:
        r["ranked"] = bool(r["avgAbs"] >= floor and r["sigma"] is not None)
    rows.sort(key=lambda r: (not r["ranked"], -abs(r["sigma"] or 0.0), r["key"]))
    n = 0
    for r in rows:
        if r["ranked"]:
            n += 1
            r["rank"] = n
        else:
            r["rank"] = None
    return rows


# ── 적재 (futures.py 와 같은 규율: 워터마크 키 캐시 + 주입 시임) ─────────────

_cached: FlowData | None = None
_injected: FlowData | None = None


def set_data(data: FlowData | None) -> None:
    """테스트 주입 시임 — `futures.set_data` 와 같은 규율. None 이면 해제."""
    global _injected
    _injected = data


def watermark() -> tuple[str, int]:
    """★**복합**이다 — 두 표의 `(MAX, COUNT)` 를 잇는다.

    `futures.watermark()` 를 재사용하면 안 된다: 그것은 `WHERE CLOSE IS NOT NULL`
    로 걸러 **투자자 행의 모집단이 아니다**. 그리고 한쪽만 세면 다른 쪽이
    들어와도 캐시 열쇠가 안 바뀐다 — 두 원천이 **다른 시각에 도착**하므로
    (§두 원천의 asof) 그 실수가 조용히 하루를 숨긴다.
    """
    with mysqldb.engine().connect() as conn:
        f = conn.execute(mysqldb.text(
            f"SELECT MAX(deal_date), COUNT(*) FROM {FUT_TABLE}")).one()
        c = conn.execute(mysqldb.text(
            f"SELECT MAX(deal_date), COUNT(*) FROM {CASH_TABLE}")).one()
    return (f"{f[0]}|{c[0]}", int(f[1]) + int(c[1]))


def _fetch() -> FlowData:
    """두 표를 **한 연결**에서 읽는다 — `read_sql()` 은 호출마다 연결을 새로 연다."""
    qty = ", ".join(f"{k}QUANTITY" for k, _ in FUT_TOP + FUT_SUB) + f", {FUT_DEAD}QUANTITY"
    cash_cols = ", ".join(f"SUM(t.{c}) AS {c}" for c, _ in CASH_COLS)
    with mysqldb.engine().connect() as conn:
        frows = conn.execute(mysqldb.text(
            f"SELECT deal_date, ktb_type, {qty} FROM {FUT_TABLE} ORDER BY deal_date ASC"
        )).fetchall()
        crows = conn.execute(mysqldb.text(f"""
            SELECT t.deal_date, {cash_cols}
            FROM {CASH_TABLE} t
            JOIN (SELECT deal_date, isin, market, buysell, MAX(deal_time) mt
                  FROM {CASH_TABLE}
                  WHERE market = '전체' AND buysell = '순매수'
                  GROUP BY deal_date, isin, market, buysell) k
              ON t.deal_date = k.deal_date AND t.isin = k.isin
             AND t.market = k.market AND t.buysell = k.buysell
             AND t.deal_time = k.mt
            WHERE t.market = '전체' AND t.buysell = '순매수'
              AND t.isin_nm NOT LIKE '국고이자%' AND t.isin_nm NOT LIKE '국고원금%'
            GROUP BY t.deal_date ORDER BY t.deal_date ASC
        """)).fetchall()
    if not frows:
        raise FlowError(f"{FUT_TABLE} 에서 행을 읽지 못했습니다.")

    keys = [k for k, _ in FUT_TOP + FUT_SUB] + [FUT_DEAD]
    fut: dict[str, tuple[list[str], dict[str, list[int]]]] = {}
    for tenor in FUT_TENORS:
        dates: list[str] = []
        cols: dict[str, list[int]] = {k: [] for k in keys + ["ETC"]}
        for r in frows:
            if str(r[1]) != tenor:
                continue
            dates.append(_iso(r[0]))
            row = {k: int(r[2 + i] or 0) for i, k in enumerate(keys)}
            for k in keys:
                cols[k].append(row[k])
            cols["ETC"].append(close_zero_sum(row))
        fut[tenor] = (dates, cols)

    cdates: list[str] = []
    ccols: dict[str, list[int]] = {c: [] for c, _ in CASH_COLS}
    for r in crows:
        cdates.append(_iso(r[0]))
        for i, (c, _lab) in enumerate(CASH_COLS):
            ccols[c].append(int(r[1 + i] or 0))

    return FlowData(fut=fut, cash=(cdates, ccols), watermark=watermark())


def _iso(d: Any) -> str:
    return (d.date() if isinstance(d, dt.datetime) else d).isoformat()


def load() -> FlowData:
    """주입본이 있으면 그것, 없으면 SQL(워터마크 키 캐시).

    **디스크 캐시를 안 쓴다** — 두 원천 합 2.6초라(실측 2026-10-19: 선물 0.28s ·
    현물 2.30s) 모듈의 워터마크 캐시로 충분하다. 라이브 전용 선례는
    `/api/lab/creditdts`·`/api/rv/analysis`.
    """
    if _injected is not None:
        return _injected
    global _cached
    wm = watermark()
    if _cached is None or _cached.watermark != wm:
        _cached = _fetch()
    return _cached


def reset_cache() -> None:
    global _cached
    _cached = None


# ── 화면이 읽는 한 장 ───────────────────────────────────────────────────────

def board(side: str = "fut", tenor: str = "3Y") -> dict[str, Any]:
    """한 면 — 대분류 대조 + 세분 순위 + 누적·일별 계열.

    산술은 **여기 하나**다(§16) — 화면은 읽고 칠하기만 한다.
    """
    if side not in ("fut", "cash"):
        raise FlowError(f"모르는 면이에요: {side}")
    if side == "fut" and tenor not in FUT_TENORS:
        raise FlowError(f"모르는 만기예요: {tenor}")
    d = load()
    return _fut_board(d, tenor) if side == "fut" else _cash_board(d)


def _series_row(key: str, label: str, group: str, dates: list[str],
                vals: list[int]) -> dict[str, Any]:
    """한 주체의 오늘·구간·편차. **창은 오늘을 뺀** 직전 `WINDOW` 봉이다."""
    today = vals[-1] if vals else 0
    sigma, avg = sigma_of(vals[:-1], today)
    year = dates[-1][:4] if dates else ""
    return {
        "key": key, "label": label, "group": group,
        "d1": today,
        "d5": sum(vals[-5:]),
        "d20": sum(vals[-20:]),
        "ytd": sum(v for dte, v in zip(dates, vals) if dte[:4] == year),
        "sigma": sigma,
        "avgAbs": round(avg),
    }


def _fut_board(d: FlowData, tenor: str) -> dict[str, Any]:
    dates, cols = d.fut[tenor]
    if not dates:
        raise FlowError(f"선물 {tenor} 자료가 없어요.")
    last = {k: v[-1] for k, v in cols.items()}

    #: 함정 ① — 항등식이 깨지면 **세지 않고 말한다**. 조용히 더하면 이중계상이다.
    err = inst_identity_error(last)
    excluded: list[dict[str, str]] = [{
        "id": FUT_DEAD, "label": "정부",
        "why": "전 구간 0 이라 뺐어요 — 죽은 칼럼이에요.",
    }]
    if err:
        excluded.append({
            "id": "INST", "label": "기관계",
            "why": f"기관계와 세분 여섯의 합이 {err}계약 어긋나요 — 세분을 믿지 마세요.",
        })

    top = [{"key": k, "label": lab, "value": last[k]} for k, lab in FUT_TOP]
    top.append({"key": "ETC", "label": "기타", "value": last["ETC"]})
    sub = rank_rows(
        [_series_row(k, lab, "기관계 세분", dates, cols[k]) for k, lab in FUT_SUB],
        RANK_FLOOR,
    )
    #: 그림에 올릴 계열 — 외국인 + 세분 상위 셋. **최대 넷**이다(화면 제약).
    picked = ["FRGN"] + [r["key"] for r in sub if r["ranked"]][:3]
    return {
        "side": "fut", "tenor": tenor,
        "asof": {"fut": dates[-1], "cash": d.cash[0][-1] if d.cash[0] else None},
        "unit": "계약",
        "days": len(dates),
        "top": top,
        "sub": sub,
        "rankFloor": RANK_FLOOR,
        "series": _chart(dates, cols, picked, FUT_TOP + FUT_SUB),
        "excluded": excluded,
        #: 화면이 「무엇을 보고 있나」를 지어내지 않게 서버가 말을 쥔다.
        "basis": "투자자별 순매수예요 — 집계이고 새 판단이 아니에요. "
                 "대분류는 영합이라 순위가 아니라 대조로 세우고, "
                 f"순위는 기관계 세분이 져요(일평균 {RANK_FLOOR:,.0f}계약 미만은 순위 밖).",
    }


def _cash_board(d: FlowData) -> dict[str, Any]:
    dates, cols = d.cash
    if not dates:
        raise FlowError("현물 자료가 없어요.")
    rows = rank_rows(
        [_series_row(c, lab, "국고채 현물", dates, cols[c]) for c, lab in CASH_COLS],
        CASH_RANK_FLOOR,
    )
    picked = [r["key"] for r in rows if r["ranked"]][:4]
    return {
        "side": "cash", "tenor": None,
        "asof": {"fut": None, "cash": dates[-1]},
        "unit": "백만원",
        "days": len(dates),
        #: 현물엔 상위 집합이 없다 — 대분류 대조 칸이 **없는 것이 맞다**.
        "top": [],
        "sub": rows,
        "rankFloor": CASH_RANK_FLOOR,
        "series": _chart(dates, cols, picked, CASH_COLS),
        "excluded": [{
            "id": "strip", "label": "원금·이자 분리채",
            "why": "국고 명목만 봐요 — 분리채는 뺐어요.",
        }],
        "basis": "국고채 현물 투자자별 순매수예요(장외+장내 합산 · 단위 백만원) — "
                 "집계이고 새 판단이 아니에요. "
                 f"일평균 {CASH_RANK_FLOOR:,.0f}백만원 미만은 순위 밖이에요.",
    }


def _chart(dates: list[str], cols: dict[str, list[int]], picked: list[str],
           names: list[tuple[str, str]]) -> dict[str, Any]:
    """그림이 받는 것 — 누적 ≤4계열 + 일별 1계열(첫 계열).

    ★**최대 4계열**이다. 이 리포에는 N계열 범주형 팔레트가 없어서(이름 있는 색은
    방향 2 + 참조 4뿐) 열한 주체를 한 그림에 칠할 수 없다. 전수는 표가 진다.
    """
    lab = dict(names)
    return {
        "dates": dates,
        "cum": [{"key": k, "label": lab.get(k, k), "values": cumulative(cols[k])}
                for k in picked if k in cols],
        "daily": {"key": picked[0], "label": lab.get(picked[0], picked[0]),
                  "values": cols[picked[0]]} if picked else None,
    }


def history(key: str, side: str = "fut", tenor: str = "3Y") -> dict[str, Any]:
    """한 주체 한 계열의 전구간 — 미리보기용."""
    d = load()
    if side == "cash":
        dates, cols = d.cash
        names = dict(CASH_COLS)
    else:
        if tenor not in FUT_TENORS:
            raise FlowError(f"모르는 만기예요: {tenor}")
        dates, cols = d.fut[tenor]
        names = dict(FUT_TOP + FUT_SUB)
        names["ETC"] = "기타"
    if key not in cols:
        raise KeyError(key)
    return {
        "key": key, "label": names.get(key, key), "side": side,
        "tenor": None if side == "cash" else tenor,
        "dates": dates, "daily": cols[key], "cum": cumulative(cols[key]),
    }
