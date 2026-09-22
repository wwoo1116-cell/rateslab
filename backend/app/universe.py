# -*- coding: utf-8 -*-
"""The expanded universe, read from live tables — no mock market data anywhere.

V2-LOCAL: this module does not exist in braveworld. It reads three live sources the
swap monitor never touched:

    sim_portfolio.credit_matrix    12 curve types x 13 tenors, daily since 2020-01-02
    infomax.daily_ktb_price        3Y KTB futures, daily since 2012-01-02
    infomax.daily_lktb_price       10Y KTB futures, same

and derives the two spreads a KRW desk actually watches. Both legs of both spreads
come from tables that closed on the same date, so nothing is interpolated and nothing
is carried forward.

§16 COMPUTATION BOUNDARY. Every number here is finished server-side — level, the three
deltas, the 52-week statistics and the percentile. The browser formats; it does not
compute. That rule is why this module exists rather than a fetch in the frontend.

WHAT IS DELIBERATELY ABSENT
  - issuer-level credit and sector x rating detail. Their source (`infomax.matrix_*`)
    stopped updating 2026-01-23, seven months ago. A 52-week percentile over a stopped
    feed is wrong in a way nothing on screen would show, so those rows ship as empty
    structure rather than as stale numbers.
  - 5Y futures. There is no table; only 3Y and 10Y exist.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Iterable

from .derive import MA_WINDOWS, moving_averages
from .mysqldb import engine
from sqlalchemy import text

log = logging.getLogger("sauron.universe")

# credit_matrix tenor columns -> (label, years). 30m is dropped: it has no IRS
# counterpart and no desk quotes it.
TENORS: list[tuple[str, str, float]] = [
    ("rt_6m", "6M", 0.5),
    ("rt_9m", "9M", 0.75),
    ("rt_1y", "1Y", 1.0),
    ("rt_18m", "1.5Y", 1.5),
    ("rt_2y", "2Y", 2.0),
    ("rt_3y", "3Y", 3.0),
    ("rt_5y", "5Y", 5.0),
    ("rt_7y", "7Y", 7.0),
    ("rt_10y", "10Y", 10.0),
]

# The IRS column that pairs with each tenor, for the bond-swap spread.
IRS_COL = {
    "6M": "irs_6m", "9M": "irs_9m", "1Y": "irs_1y", "1.5Y": "irs_18m",
    "2Y": "irs_2y", "3Y": "irs_3y", "5Y": "irs_5y", "7Y": "irs_7y", "10Y": "irs_10y",
}

# `bond_type` -> display label. KTB is the government curve and is the benchmark every
# credit spread is measured against, so it is not itself a credit row.
CURVE_LABEL = {
    "KTB": "국고", "MSB": "통안", "KDB": "산금", "SPB": "특수",
    "BD": "은행", "CARD": "카드", "OFB": "기타금융",
    "CB1": "회사 AAA", "CB2": "회사 AA+", "CB3": "회사 AA",
    "CB4": "회사 AA−", "CB5": "회사 A",
}
CREDIT_TYPES = ["MSB", "KDB", "SPB", "BD", "CARD", "OFB", "CB1", "CB2", "CB3", "CB4", "CB5"]

FUTURES = [
    ("daily_ktb_price", "KTB3", "3년 국채선물"),
    ("daily_lktb_price", "KTB10", "10년 국채선물"),
]

# 선물 계약 코드 -> (IRS 테너 라벨, 정렬용 연수). 퓨처스왑이 어느 IRS 다리와
# 짝인지가 여기 한 번만 적힌다 [OWNER, 2026-08-25 — "3선이면 3년 IRS, 10선이면
# 10년 IRS"]. 엔진(`futures.FSW_IRS_COL`)이 쓰는 그 짝과 같은 문장이다.
FUT_TENOR = {"KTB3": ("3Y", 3.0), "KTB10": ("10Y", 10.0)}

# A year of business days. The 52-week window is trailing 252 observations, the same
# window v1 settled on after a 10-year window pinned every level at the 99th percentile.
WINDOW = 252


def _stats(series: list[float | None]) -> dict[str, Any]:
    """52-week high / low / mean / percentile over the trailing window.

    `None` is not zero and is not carried forward — it is skipped, and a window with
    fewer than two observations yields nulls rather than a percentile computed from
    one point.
    """
    vals = [v for v in series[-WINDOW:] if v is not None]
    if len(vals) < 2:
        return {"min": None, "max": None, "avg": None, "pct": None}
    lo, hi = min(vals), max(vals)
    now = vals[-1]
    pct = None if hi == lo else round((now - lo) / (hi - lo) * 100, 1)
    return {
        "min": round(lo, 4),
        "max": round(hi, 4),
        "avg": round(sum(vals) / len(vals), 4),
        "pct": pct,
    }


def _deltas(series: list[float | None], dates: list[dt.date], unit: str) -> dict[str, float | None]:
    """D-1 / MTD / YTD change. In bp for a %-quoted level, in the row's own unit for a
    spread that is already bp."""
    if not series or series[-1] is None:
        return {"d1": None, "mtd": None, "ytd": None}
    now = series[-1]
    today = dates[-1]
    scale = 100.0 if unit == "%" else 1.0

    def prior(pred) -> float | None:
        for i in range(len(dates) - 2, -1, -1):
            if pred(dates[i]) and series[i] is not None:
                return series[i]
        return None

    d1 = series[-2] if len(series) > 1 else None
    mtd = prior(lambda d: d.month != today.month or d.year != today.year)
    ytd = prior(lambda d: d.year != today.year)
    return {
        "d1": None if d1 is None else round((now - d1) * scale, 4),
        "mtd": None if mtd is None else round((now - mtd) * scale, 4),
        "ytd": None if ytd is None else round((now - ytd) * scale, 4),
    }


def _row(
    rid: str, label: str, kind: str, unit: str,
    series: list[float | None], dates: list[dt.date],
    sort_key: list[float], key: bool,
) -> dict[str, Any]:
    """A SeriesSummary-shaped row — the same shape the swap monitor's builder already
    consumes, so the frontend needs no second row vocabulary."""
    now = series[-1] if series else None
    stats = _stats(series)
    deltas = _deltas(series, dates, unit)
    return {
        "id": rid,
        "label": label,
        "kind": kind,
        "unit": unit,
        "now": None if now is None else round(now, 4),
        "deltas": deltas,
        "basisValues": {"d1": None, "mtd": None, "ytd": None},
        "range1y": stats,
        "sortKey": sort_key,
        "quoted": True,
        "movePct": None,
        "key": key,
    }


def _fetch_curves(
    conn, tenors: list[tuple[str, str, float]] = TENORS
) -> tuple[list[dt.date], dict[str, dict[str, list[float | None]]]]:
    """credit_matrix, pivoted to {bond_type: {tenor_label: [values by date]}}.

    `tenors` 기본값은 표의 유니버스(TENORS)다. 3D 표면만 더 넓은 컬럼 집합
    (3M·20Y·30Y 포함)을 자기 리스트로 넘긴다 [OWNER 2026-08-19 — "3M부터 30까지
    데이터 있으면 추가"] — 표의 행 집합은 오너가 따로 정한 것이라 안 넓힌다.
    """
    cols = ", ".join(f"`{c}`" for c, _, _ in tenors)
    rows = conn.execute(text(
        f"SELECT bas_dt, bond_type, {cols} FROM sim_portfolio.credit_matrix ORDER BY bas_dt"
    )).fetchall()

    dates: list[dt.date] = []
    seen: set[dt.date] = set()
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            dates.append(r[0])
    idx = {d: i for i, d in enumerate(dates)}

    out: dict[str, dict[str, list[float | None]]] = {}
    for r in rows:
        bt = r[1]
        by_tenor = out.setdefault(bt, {lbl: [None] * len(dates) for _, lbl, _ in tenors})
        for j, (_, lbl, _) in enumerate(tenors):
            v = r[2 + j]
            # 0.0 in this feed means "no such point on this curve" (MSB past 3Y), not a
            # zero rate. Treating it as a level would draw a curve that collapses.
            by_tenor[lbl][idx[r[0]]] = None if v in (None, 0.0) else float(v)
    return dates, out


def _fetch_irs(conn) -> tuple[list[dt.date], dict[str, list[float | None]]]:
    cols = ", ".join(sorted(set(IRS_COL.values())))
    rows = conn.execute(text(
        f"SELECT irs_date, {cols} FROM sim_portfolio.mkt_irs_close ORDER BY irs_date"
    )).mappings().fetchall()
    dates = [r["irs_date"] for r in rows]
    by_tenor: dict[str, list[float | None]] = {}
    for lbl, col in IRS_COL.items():
        by_tenor[lbl] = [None if r[col] is None else float(r[col]) for r in rows]
    return dates, by_tenor


def _align(a_dates: list[dt.date], a: list[float | None],
           b_dates: list[dt.date], b: list[float | None]) -> tuple[list[dt.date], list[float | None]]:
    """Inner join on date. A spread is only defined where BOTH legs printed — joining
    on the union and carrying one leg forward would invent a spread that never traded."""
    bmap = {d: v for d, v in zip(b_dates, b)}
    dates, out = [], []
    for d, v in zip(a_dates, a):
        w = bmap.get(d)
        if v is not None and w is not None:
            dates.append(d)
            out.append(v - w)
    return dates, out


def build_universe() -> dict[str, Any]:
    """Every live row outside swaps. Raises on a dead database rather than returning
    an empty universe that looks like a quiet market."""
    with engine().connect() as conn:
        cdates, curves = _fetch_curves(conn)
        idates, irs = _fetch_irs(conn)
        futures_raw = {}
        for tbl, code, _ in FUTURES:
            futures_raw[code] = conn.execute(text(
                f"SELECT 일자, 종가, 선물내재수익률, 저평가 FROM infomax.`{tbl}` ORDER BY 일자"
            )).fetchall()

    rows: list[dict[str, Any]] = []

    # ── 국고 현물 ────────────────────────────────────────────────────────────
    ktb = curves.get("KTB", {})
    for _, lbl, yrs in TENORS:
        s = ktb.get(lbl)
        if not s or s[-1] is None:
            continue
        rows.append(_row(f"GOVT-{lbl}", f"국고 {lbl}", "govt", "%", s, cdates, [yrs], yrs in (1, 3, 5, 10)))

    # ── 크레딧 스프레드 (해당 곡선 − 국고, 같은 테너) ──────────────────────────
    for bt in CREDIT_TYPES:
        cur = curves.get(bt)
        if not cur:
            continue
        for _, lbl, yrs in TENORS:
            gs, cs = ktb.get(lbl), cur.get(lbl)
            if not gs or not cs:
                continue
            d, spread = _align(cdates, cs, cdates, gs)
            if not spread:
                continue
            rows.append(_row(
                f"CRD-{bt}-{lbl}", f"{CURVE_LABEL[bt]} {lbl}", "credit", "bp",
                [v * 100 for v in spread], d, [yrs, CREDIT_TYPES.index(bt)],
                yrs == 3.0,
            ))

    # ── 본드스왑스프레드 (IRS − 국고) ────────────────────────────────────────
    # ★부호 규약 **스왑 − 채권현물** [OWNER 2026-09-22 — "BSS나 FSW같은거 이제
    # 컨벤션 바꾸는게 스왑 - 채권현물 또는 국채선물이야"]. 이 표는 메인 보드·
    # RV·시뮬이 같이 읽으므로, MR 쪽(`mrseries.points`)만 뒤집으면 같은 날 같은
    # 만기가 두 화면에서 반대 부호로 선다 — 2026-09-22 전수조사가 잡은 바로 그
    # 결함(출처 둘)의 부호 판이다. 한 규약이어야 한다.
    for _, lbl, yrs in TENORS:
        gs = ktb.get(lbl)
        if not gs or lbl not in IRS_COL:
            continue
        d, spread = _align(idates, irs[lbl], cdates, gs)
        if not spread:
            continue
        rows.append(_row(
            f"BSS-{lbl}", f"BSS {lbl}", "bss", "bp",
            [v * 100 for v in spread], d, [yrs], yrs in (3, 5, 10),
        ))

    # ── 국채선물 · 퓨처스왑 ──────────────────────────────────────────────────
    for tbl, code, name in FUTURES:
        raw = futures_raw[code]
        if not raw:
            continue
        fdates = [r[0].date() if hasattr(r[0], "date") else r[0] for r in raw]
        close = [None if r[1] is None else float(r[1]) for r in raw]
        imp = [None if r[2] is None else float(r[2]) for r in raw]
        cheap = [None if r[3] is None else float(r[3]) for r in raw]
        lbl, yrs = FUT_TENOR[code]
        rows.append(_row(f"FUT-{code}", f"{name} 가격", "futures", "가격", close, fdates, [yrs, 0], True))
        rows.append(_row(f"FUT-{code}-IY", f"{name} 내재금리", "futures", "%", imp, fdates, [yrs, 1], True))
        # 저평가 is the vendor's own basis figure, already in the right unit. It is read,
        # not derived — deriving it would need the CTD basket this contract does not have
        # (KTB futures are cash-settled against a synthetic basket).
        rows.append(_row(f"FUT-{code}-BS", f"{name} 저평가", "futures", "가격", cheap, fdates, [yrs, 2], True))

        # 퓨처스왑 = 같은 만기 IRS − **벤더 내재금리**. 본드스왑과 같은 모양이고
        # 같은 inner join 규율(양쪽이 다 프린트한 날만)이다. 내재금리는 유도하지
        # 않고 읽는다 — 조정가(`mkt_futures_investor_close.CLOSE`)를 역산하면
        # 수준이 무의미해진다(FUTURES_LANE_STATE §Phase 1·2). 이 표는 그 조정가
        # 표를 아예 열지 않으므로 여기에 그 결함이 들어올 길이 없다.
        d, spread = _align(idates, irs[lbl], fdates, imp)
        if not spread:
            continue
        rows.append(_row(
            f"FSW-{code}", f"퓨처스왑 {lbl}", "futuresswap", "bp",
            [v * 100 for v in spread], d, [yrs], True,
        ))

    asof = max(
        [cdates[-1] if cdates else dt.date.min, idates[-1] if idates else dt.date.min],
    )

    # Freshness is computed HERE, per source, for the same reason the swap monitor
    # computes its own: a browser that decides what "stale" means is a second opinion,
    # and the two will disagree on the day it matters. Business days, Seoul.
    def _age(d: dt.date | None) -> int | None:
        if d is None:
            return None
        n, cur = 0, d
        today = dt.date.today()
        while cur < today:
            cur += dt.timedelta(days=1)
            if cur.weekday() < 5:
                n += 1
        return n

    def _level(age: int | None) -> str:
        if age is None:
            return "stale"
        return "current" if age <= 1 else ("behind" if age <= 3 else "stale")

    fut_asof = None
    for code in futures_raw:
        rows_f = futures_raw[code]
        if rows_f:
            d = rows_f[-1][0]
            d = d.date() if hasattr(d, "date") else d
            fut_asof = d if fut_asof is None else max(fut_asof, d)
    idate_last = idates[-1] if idates else None
    fsw_asof = (min(fut_asof, idate_last)
                if (fut_asof is not None and idate_last is not None) else None)
    return {
        "asof": asof.isoformat(),
        "rows": rows,
        "sources": {
            "govt": {
                "table": "sim_portfolio.credit_matrix",
                "asof": cdates[-1].isoformat() if cdates else None,
                "ageBusinessDays": _age(cdates[-1] if cdates else None),
                "level": _level(_age(cdates[-1] if cdates else None)),
            },
            "credit": {
                "table": "sim_portfolio.credit_matrix",
                "asof": cdates[-1].isoformat() if cdates else None,
                "ageBusinessDays": _age(cdates[-1] if cdates else None),
                "level": _level(_age(cdates[-1] if cdates else None)),
            },
            "bss": {
                "table": "credit_matrix × mkt_irs_close",
                "asof": asof.isoformat(),
                "ageBusinessDays": _age(asof),
                "level": _level(_age(asof)),
            },
            "futures": {
                "table": "infomax.daily_ktb_price / daily_lktb_price",
                "asof": fut_asof.isoformat() if fut_asof else None,
                "ageBusinessDays": _age(fut_asof),
                "level": _level(_age(fut_asof)),
            },
            # 두 다리 중 **늦은 쪽**이 이 행의 나이다 — 둘을 평균 내면 한쪽이
            # 멈춘 날 화면이 조용히 신선해 보인다(이 파일 위 주석의 그 결함).
            "futuresswap": {
                "table": "daily_ktb_price × mkt_irs_close",
                "asof": fsw_asof.isoformat() if fsw_asof else None,
                "ageBusinessDays": _age(fsw_asof),
                "level": _level(_age(fsw_asof)),
            },
        },
        # Named so the screen can say WHY a class is empty rather than just being bare.
        "absent": [
            {"id": "issuer", "label": "종목별 크레딧",
             "reason": "출처 infomax.matrix_* 가 2026-01-23 에 멈췄어요. 멈춘 피드로 52주 통계를 내면 화면에 안 보이는 방식으로 틀려요."},
            {"id": "fut5y", "label": "5년 국채선물",
             "reason": "테이블이 없어요. 3년과 10년만 있어요."},
        ],
    }


def _universe_series(rid: str) -> dict[str, Any]:
    """History for ONE universe row.

    Targeted rather than served out of the summary payload: 120 series x ~1,600 points
    would be a multi-megabyte response to draw one line. Each branch re-queries only
    the legs that row needs, which is a single indexed scan.

    The series is built by the SAME code paths the summary uses — same 0.0-is-absent
    rule, same inner join for spreads — so a chart and its row can never disagree
    about what the number was.
    """
    with engine().connect() as conn:
        if rid.startswith("FUT-"):
            code = rid.split("-")[1]
            tbl = "daily_ktb_price" if code == "KTB3" else "daily_lktb_price"
            col = {"IY": "선물내재수익률", "BS": "저평가"}.get(rid.split("-")[-1], "종가")
            unit = "%" if col == "선물내재수익률" else "가격"
            rows = conn.execute(text(
                f"SELECT 일자, `{col}` FROM infomax.`{tbl}` ORDER BY 일자"
            )).fetchall()
            pts = [
                {"t": (r[0].date() if hasattr(r[0], "date") else r[0]).isoformat(), "v": float(r[1])}
                for r in rows if r[1] is not None
            ]
            return {"id": rid, "unit": unit, "points": pts}

        if rid.startswith("FSW-"):
            code = rid.split("-", 1)[1]
            if code not in FUT_TENOR:
                raise KeyError(rid)
            lbl, _ = FUT_TENOR[code]
            tbl = "daily_ktb_price" if code == "KTB3" else "daily_lktb_price"
            frows = conn.execute(text(
                f"SELECT 일자, 선물내재수익률 FROM infomax.`{tbl}` ORDER BY 일자"
            )).fetchall()
            fdates = [(r[0].date() if hasattr(r[0], "date") else r[0]) for r in frows]
            imp = [None if r[1] is None else float(r[1]) for r in frows]
            idates, irs = _fetch_irs(conn)
            d, spread = _align(idates, irs[lbl], fdates, imp)
            pts = [{"t": t.isoformat(), "v": v * 100} for t, v in zip(d, spread)]
            return {"id": rid, "unit": "bp", "points": pts}

        cdates, curves = _fetch_curves(conn)
        ktb = curves.get("KTB", {})

        if rid.startswith("GOVT-"):
            lbl = rid.split("-", 1)[1]
            s = ktb.get(lbl, [])
            pts = [{"t": d.isoformat(), "v": v} for d, v in zip(cdates, s) if v is not None]
            return {"id": rid, "unit": "%", "points": pts}

        if rid.startswith("BSS-"):
            lbl = rid.split("-", 1)[1]
            idates, irs = _fetch_irs(conn)
            d, spread = _align(cdates, ktb.get(lbl, []), idates, irs.get(lbl, []))
            return {"id": rid, "unit": "bp",
                    "points": [{"t": x.isoformat(), "v": round(v * 100, 4)} for x, v in zip(d, spread)]}

        if rid.startswith("CRD-"):
            _, bt, lbl = rid.split("-", 2)
            d, spread = _align(cdates, curves.get(bt, {}).get(lbl, []), cdates, ktb.get(lbl, []))
            return {"id": rid, "unit": "bp",
                    "points": [{"t": x.isoformat(), "v": round(v * 100, 4)} for x, v in zip(d, spread)]}

    raise KeyError(rid)


def universe_series(rid: str) -> dict[str, Any]:
    """`_universe_series` + 이동평균.

    갈래가 여섯이라 반환 자리마다 적지 않고 한 번 감싼다. 이 계열은 솎지 않으므로
    (전 구간 그대로 나간다) MA 는 나가는 점들 위에서 그대로 계산된다 — 스왑 쪽
    (`derive.series_history`)이 솎기 전에 얹어야 했던 이유가 여기엔 없다.

    창은 `derive.MA_WINDOWS` 하나다. 화면이 「MA120」이라고 부르는 수가 국고에서와
    퓨처스왑에서 다르면 안 된다.
    """
    body = _universe_series(rid)
    values = [p["v"] for p in body.get("points", [])]
    mas = moving_averages(values)
    body["ma"] = {str(w): mas[w] for w in MA_WINDOWS}
    body["maWindows"] = list(MA_WINDOWS)
    return body
