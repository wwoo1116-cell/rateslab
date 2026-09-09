# -*- coding: utf-8 -*-
"""BSS 평균회귀 — 실전 운용 재설계 · 전진분석 [OWNER 2026-08-28].

지시 다섯을 그대로 집행한다. 화면(전략 실험 창)은 여전히 **재현 도구**이고,
이 스크립트는 그 위에서 «실전에 들고 갈 수 있는가» 를 재는 물건이다.

## 사전 등록 — OOS 를 보기 **전에** 못 박은 것

이 절이 먼저 있는 이유는 이 리포의 규율이다: 격자를 돌린 뒤에 기준을 고르면
그건 측정이 아니라 사후 이야기다.

  창          훈련 756봉(3년) · 시험 252봉(1년) · 걸음 252봉. 시험 창은
              직전 `lookback` 봉을 **웜업으로만** 쓰고 그 구간에서는 진입을
              막는다(게이트) — 웜업은 과거 자료라 미래 참조가 아니다.
  격자        룩백 {20, 60, 120} × 진입σ {1.5, 2.0, 2.5} × 청산σ {0, 0.5, 1.0}
              = 27칸. 252 룩백은 뺐다 — 훈련 창이 756봉인데 그 셋째를 웜업으로
              먹으면 남는 신호 구간이 2년이라 칸의 뜻이 흐려진다.
  고정        손절σ 3.5 · 타임스탑 20봉 · 방향 `(-1,)` 한쪽 · 캐리 켬.
  선택 규칙   훈련 창 **Sharpe 최대**, 단 거래 8건 이상. 없으면 3건 이상에서
              고른다. 그것도 없으면 그 폴드는 **거래 없음**으로 기록한다
              (조건을 낮춰 억지로 고르지 않는다).
  동점        낙폭이 작은 칸.

## 다섯 지시가 코드의 어디에 있는가

  1 전진분석     `walk_forward()` — 전체 기간 격자 탐색을 버린다.
  2 꼬리 위험    미청산은 **원래부터** 총손익·MDD 에 실시간으로 들어 있다
                (누적이 보유 봉마다 MTM 을 더한다). 빠져 있던 것은 승률·거래
                수·보유기간이라, `close_open_at_end=True` 로 그것까지 센다.
                타임스탑은 엔진의 `time_stop`.
  3 레짐 필터    `app/mrregime.vol_gate`(주) · `trend_gate`(부) → 엔진의 `gate`
  4 단방향 제약  `reverse_exit=True` + `benchmarks()` 의 IR
  5 동적 비용    `app/mrregime.cost_path` → 엔진의 `cost_bp_series`

## 알려진 근사

  - 폴드 경계에서 포지션을 **평가로 접는다**(다음 폴드는 무포지션으로 시작).
    전진분석의 표준 관행이고, 청산 비용을 안 물리므로 비용을 그만큼 적게 센다.
  - 캐리의 원금 환산은 지금 커브의 pv01 하나를 쓴다(`mrcarry` 머리의 그 근사).
  - 변동성 백분위는 **확장 창**(과거만)이고, 관측 250봉이 쌓이기 전에는 필터가
    쉰다 — 표본 앞머리에서 「위험한 날」을 정의할 근거가 없기 때문이다.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app import funding as fnd  # noqa: E402
from app import mr as mr_mod  # noqa: E402
from app import mrbacktest as bt  # noqa: E402
from app import mrcarry as mrc  # noqa: E402
from app import mrregime as rg  # noqa: E402
from app import universe as uni  # noqa: E402
from app.curves import TENOR_T, build_basis_curves  # noqa: E402
from app.dataset import load_dataset_merged  # noqa: E402
from app.dv01 import pv01  # noqa: E402
from app.mysqldb import engine  # noqa: E402

TRAIN, TEST = 756, 252
GRID_LOOKBACK = (20, 60, 120)
GRID_ENTRY = (1.5, 2.0, 2.5)
GRID_EXIT = (0.0, 0.5, 1.0)
#: ★**사전등록 값이다 — 프리셋에서 유도하지 말 것** [판단 2026-09-09].
#:
#: 화면 프리셋이 2026-09-08 에 {3.0,3.5,4.0} → {2.5,3.0,3.5} 로 갈렸고(커밋
#: `74d8eb8f`), 2026-09-09 에는 화면 **기본값**도 3.5 → 2.5 로 옮겼다. 그때마다
#: 이 상수를 따라 옮기고 싶어지는데, 그러면 **이 스크립트가 재는 것이 없어진다**:
#: 위 「사전 등록」 절이 OOS 를 보기 전에 「고정 · 손절σ 3.5」를 못 박았고, 그
#: 못 박음이 이 전진분석의 유일한 근거다. 나중에 바꾼 값으로 옛 폴드를 다시
#: 돌리면 그건 측정이 아니라 사후 이야기다(그 절의 첫 문장).
#:
#: 그래서 여기는 **동결 상수**로 남는다. 2.5 로 재고 싶으면 이 값을 고치는 것이
#: 아니라 **새 사전등록**을 열고 그 사실을 절에 적어야 한다.
STOP_Z = 3.5
TIME_STOP = 20
NOTIONAL = 1_000_000.0
LEGACY_COST = 0.05
# 필터·비용의 상수는 `app/mrregime.py` 가 진다(VOL_WIN·VOL_BLOCK·COST_LO/HI 등).
MIN_TRADES, MIN_TRADES_FALLBACK = 8, 3


# ── 재료 ────────────────────────────────────────────────────────────────────

_CURVE: list = []


def _now_curve():
    """오늘 커브 한 번만 — 부트스트랩이 싸도 폴드마다 다시 세울 이유는 없다.

    화면(`main._curves["now"]`)과 **같은 것**을 같은 방법으로 세운다: 캐리의
    원금 환산이 이 pv01 에 달려 있어, 여기서 딴 커브를 쓰면 스크립트와 화면의
    수가 조용히 갈린다.
    """
    if not _CURVE:
        _CURVE.append(build_basis_curves(load_dataset_merged())["now"])
    return _CURVE[0]

def load(sid: str) -> dict:
    """한 계열의 값·캐리·벤치마크 재료. 화면과 **같은 창구**를 쓴다."""
    body = mr_mod.series_points(sid)
    pts = [p for p in body["points"] if p.get("v") is not None]
    dates = [p["t"] for p in pts]
    vals = [float(p["v"]) for p in pts]          # BSS 는 bp
    spec = fnd.FundingSpec(basis=fnd.DEFAULT_BASIS, spread_bp=fnd.DEFAULT_SPREAD_BP)
    rates, _ = mrc.carry_rates(sid, "bss", dates, spec)
    pv = pv01(_now_curve(), TENOR_T[mrc._tenor_of(sid)])
    carry = mrc.carry_krw(rates, dates, notional_per_bp=NOTIONAL, pv01=pv)
    principal = NOTIONAL / (pv * 1e-4)

    tenor = mrc._tenor_of(sid)
    with engine().connect() as conn:
        cdates, cv = uni._fetch_curves(conn)
        rows = conn.execute(text(
            "SELECT irs_date, cd_rate FROM sim_portfolio.mkt_irs_close ORDER BY irs_date"
        )).mappings().fetchall()
    ktb = {d.isoformat(): v for d, v in zip(cdates, cv.get("KTB", {}).get(tenor, []))
           if v is not None}
    cd = {r["irs_date"].isoformat(): float(r["cd_rate"]) for r in rows
          if r["cd_rate"] is not None}
    fund = [fnd.rate_on(spec, dt.date.fromisoformat(t)) * 100.0 for t in dates]
    return {"sid": sid, "dates": dates, "vals": vals, "carry": carry,
            "principal": principal, "ktb": [ktb.get(t) for t in dates],
            "cd": [cd.get(t) for t in dates], "fund": fund}


# ── 긴 표본 [OWNER 2026-08-28 — "더 길게 보지 뭐"] ──────────────────────────
#
# 화면이 쓰는 `credit_matrix` 는 2020-01-02 부터라 BSS 가 6.7년이다. 그 길이로는
# 다중검정 문턱을 못 넘는다(SR 1.05·시행 118 이면 최소 8.7년이 필요한데 3.5년
# 밖에 없었다). `imx_data.timeseries` 에 **2014-05-28 부터의 국고채커브·IRS·CD**
# 가 있어 12.2년이 된다.
#
# **이음매를 안 만든다.** 두 출처를 붙이면 그 자리에서 수준이 튀고, 그 튐이
# 신호로 잡힌다. 겹치는 1,633일에서 상관 0.9996~1.0000 · 중앙 차이 0.00~0.10bp
# 로 같은 계열임을 확인했으므로(`_overlap_check`), **전 기간을 새 출처 하나로**
# 쓴다. 화면(`mr.series_points`)은 건드리지 않는다 — 보드의 z 와 순위가 통째로
# 바뀌는 일이라 별도 결정이다.

LONG_KTB = {'6M': '6월이하(당일)', '9M': '9월이하(당일)', '1Y': '1년이하(당일)',
            '1.5Y': '1.5년이하(당일)', '2Y': '2년이하(당일)', '3Y': '3년이하(당일)',
            '5Y': '5년이하(당일)', '7Y': '7년이하(당일)', '10Y': '10년이하(당일)'}
LONG_IRS = {'6M': '6개월', '9M': '9개월', '1Y': '1년', '1.5Y': '18개월', '2Y': '2년',
            '3Y': '3년', '5Y': '5년', '7Y': '7년', '10Y': '10년'}
CAT_KTB, CAT_IRS, CAT_CD = '국고채커브', '스왑-IRS(종합ALL)', '단기금리'


def _pull(cat: str, item: str) -> dict[str, float]:
    with engine().connect() as conn:
        rows = conn.execute(text(
            "SELECT trade_date, value FROM imx_data.timeseries "
            "WHERE category = :c AND item = :i ORDER BY trade_date"
        ), {"c": cat, "i": item}).fetchall()
    return {r[0].isoformat(): float(r[1]) for r in rows if r[1] is not None}


def load_long(sid: str) -> dict:
    """긴 표본판 `load()`. 같은 열쇠를 돌려주므로 아래 기계가 그대로 돈다.

    스프레드는 **두 다리가 같은 날 다 찍힌 날에만** 선다(`universe._align` 의 그
    규율) — 한쪽을 이월해 채우면 없던 스프레드를 지어내게 된다.
    """
    t = mrc._tenor_of(sid)
    govt, swap = _pull(CAT_KTB, LONG_KTB[t]), _pull(CAT_IRS, LONG_IRS[t])
    cd = _pull(CAT_CD, 'CD 91일물')
    dates = sorted(set(govt) & set(swap) & set(cd))
    vals = [(govt[d] - swap[d]) * 100.0 for d in dates]          # bp

    spec = fnd.FundingSpec(basis=fnd.DEFAULT_BASIS, spread_bp=fnd.DEFAULT_SPREAD_BP)
    fund = [fnd.rate_on(spec, dt.date.fromisoformat(d)) * 100.0 for d in dates]
    # 캐리(%/년) = (국고 − 조달) + (CD − 스왑). `mrcarry` 의 그 항등 그대로다.
    rates = [(govt[d] - fund[i]) + (cd[d] - swap[d]) for i, d in enumerate(dates)]
    pv = pv01(_now_curve(), TENOR_T[t])
    carry = mrc.carry_krw(rates, dates, notional_per_bp=NOTIONAL, pv01=pv)
    return {"sid": sid, "dates": dates, "vals": vals, "carry": carry,
            "principal": NOTIONAL / (pv * 1e-4),
            "ktb": [govt[d] for d in dates], "cd": [cd[d] for d in dates],
            "fund": fund}


def overlap_check(sid: str) -> dict:
    """긴 출처와 화면 출처가 겹치는 구간에서 같은 계열인가 — 이음매 대신 이 검정."""
    new, old = load_long(sid), load(sid)
    a = dict(zip(new["dates"], new["vals"]))
    b = dict(zip(old["dates"], old["vals"]))
    both = sorted(set(a) & set(b))
    if len(both) < 50:
        return {"n": len(both), "rho": None, "medAbs": None, "maxAbs": None}
    x = [a[d] for d in both]
    y = [b[d] for d in both]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    num = sum((x[i] - mx) * (y[i] - my) for i in range(len(x)))
    dx = math.sqrt(sum((v - mx) ** 2 for v in x))
    dy = math.sqrt(sum((v - my) ** 2 for v in y))
    dif = sorted(abs(x[i] - y[i]) for i in range(len(x)))
    return {"n": len(both), "rho": num / (dx * dy) if dx and dy else None,
            "medAbs": dif[len(dif) // 2], "maxAbs": dif[-1],
            "meanDiff": mx - my}


# ── 3 레짐 필터 · 5 동적 비용 ────────────────────────────────────────────────
#
# **여기서 다시 만들지 않는다.** 화면과 이 스크립트가 같은 필터를 써야 하고,
# 두 벌이면 수가 갈릴 때 어느 쪽이 옳은지 판정할 자료가 없다 — 2026-08-28 에
# `app/mrregime.py` 로 올렸다(미래를 안 보는 성질은 그쪽 테스트가 잰다).

realized_vol = rg.realized_vol
vol_percentile = rg.vol_percentile
trend_gate = rg.trend_gate
cost_path_of = rg.cost_path


def vol_gate(vals: list[float]) -> tuple[list[bool], list[float | None]]:
    """게이트와 백분위를 같이 — 백분위는 비용 경로가 다시 쓴다."""
    return rg.vol_gate(vals), rg.vol_percentile(vals)


def cost_path(pct: list[float | None]) -> list[float]:
    """백분위 → 편도 비용(bp). 정의는 `mrregime.cost_path` 가 진다."""
    return [rg.COST_LO + (rg.COST_HI - rg.COST_LO) * (p if p is not None else 0.0)
            for p in pct]


# ── 성과 ────────────────────────────────────────────────────────────────────

def stats(daily: list[float], trades: list[dict]) -> dict:
    """봉 손익 계열 + 거래 목록 → 보고 지표. 미청산은 이미 `daily` 에 있다."""
    n = len(daily)
    total = sum(daily)
    peak, mdd, cum = -math.inf, 0.0, 0.0
    for x in daily:
        cum += x
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    sharpe = None
    if n >= 2:
        sd = st.pstdev(daily)
        sharpe = (total / n) / sd * math.sqrt(252) if sd else None
    wins = sum(1 for t in trades if t["pnl"] > 0)
    return {
        "days": n, "totalPnl": total, "maxDrawdown": mdd, "sharpe": sharpe,
        "numTrades": len(trades),
        "winRate": (wins / len(trades)) if trades else None,
        "avgBars": (sum(t["bars"] for t in trades) / len(trades)) if trades else None,
        "exposure": (sum(t["bars"] for t in trades) / n) if (trades and n) else 0.0,
    }


def benchmarks(d: dict, lo: int, hi: int) -> dict[str, list[float]]:
    """같은 날짜 위의 벤치마크 셋. 전부 **봉당 ₩**, 같은 명목이다.

    ① 국고 매수 보유 — 듀레이션을 그대로 지는 판. 손익 = −명목 × Δy(bp) +
       (국고 − 조달) 경과. 이 전략이 «금리 방향을 안 걸고 스프레드만 건다» 는
       주장의 대조군이다.
    ② CD 수취 — 현금. 아무것도 안 하는 판의 값.
    ③ 상시 BSS 롱 — 신호를 끄고 늘 들고 있는 판. **타이밍이 값을 더했는가**를
       재는 가장 날카로운 대조군이라 셋 중 이것이 핵심이다.
    """
    dates, vals, ktb, cd, fund = d["dates"], d["vals"], d["ktb"], d["cd"], d["fund"]
    P = d["principal"]
    bond: list[float] = []
    cash: list[float] = []
    always: list[float] = []
    for i in range(lo, hi):
        days = (dt.date.fromisoformat(dates[i]) - dt.date.fromisoformat(dates[i - 1])).days
        y0, y1 = ktb[i - 1], ktb[i]
        f = fund[i]
        bond.append(0.0 if (y0 is None or y1 is None) else
                    -NOTIONAL * (y1 - y0) * 100.0 + P * (y1 - f) / 100.0 * days / 365.0)
        c = cd[i]
        cash.append(0.0 if c is None else P * (c / 100.0) * days / 365.0)
        always.append(-NOTIONAL * (vals[i] - vals[i - 1]) + d["carry"][i])
    return {"국고 매수 보유": bond, "CD 수취": cash, "상시 BSS 롱": always}


def info_ratio(a: list[float], b: list[float]) -> float | None:
    if len(a) != len(b) or len(a) < 2:
        return None
    ex = [x - y for x, y in zip(a, b)]
    sd = st.pstdev(ex)
    return (sum(ex) / len(ex)) / sd * math.sqrt(252) if sd else None


# ── 1 전진분석 ──────────────────────────────────────────────────────────────

def run_slice(d: dict, lo: int, hi: int, p: dict, *, opt: dict,
              entry_from: int | None = None) -> dict:
    """[lo, hi) 구간 한 판. `entry_from` 이 있으면 그 앞은 진입만 막는다(웜업)."""
    dates, vals = d["dates"][lo:hi], d["vals"][lo:hi]
    carry = d["carry"][lo:hi]
    gate = opt["gate"][lo:hi] if opt.get("gate") else None
    if entry_from is not None:
        w = entry_from - lo
        base = gate if gate else [True] * len(vals)
        gate = [base[i] and i >= w for i in range(len(vals))]
    cost = opt["cost"][lo:hi] if opt.get("cost") else None
    return bt.simulate(
        dates, vals, lookback=p["lookback"], entry_z=p["entryZ"],
        exit_z=p["exitZ"], stop_z=STOP_Z, cost_bp=opt["costBp"],
        notional=NOTIONAL, allow_dirs=(-1,), carry=carry, gate=gate,
        cost_bp_series=cost, time_stop=opt["timeStop"],
        reverse_exit=opt["reverseExit"], close_open_at_end=True)


def pick(d: dict, lo: int, hi: int, opt: dict) -> dict | None:
    """훈련 창의 선택 — 사전 등록한 규칙 그대로."""
    cands = []
    for lb in GRID_LOOKBACK:
        for ez in GRID_ENTRY:
            for xz in GRID_EXIT:
                p = {"lookback": lb, "entryZ": ez, "exitZ": xz}
                s = run_slice(d, lo, hi, p, opt=opt)["summary"]
                if s["sharpe"] is None:
                    continue
                cands.append((p, s["numTrades"], s["sharpe"], s["maxDrawdown"]))
    for floor in (MIN_TRADES, MIN_TRADES_FALLBACK):
        ok = [c for c in cands if c[1] >= floor]
        if ok:
            ok.sort(key=lambda c: (-c[2], c[3]))
            return {**ok[0][0], "trainTrades": ok[0][1], "trainSharpe": ok[0][2]}
    return None


def walk_forward(d: dict, opt: dict) -> dict:
    """폴드를 굴려 OOS 를 이어 붙인다."""
    n = len(d["vals"])
    folds: list[dict] = []
    daily: list[float] = []
    trades: list[dict] = []
    lo = 0
    while lo + TRAIN + 1 <= n:
        tr_lo, tr_hi = lo, lo + TRAIN
        te_lo, te_hi = tr_hi, min(tr_hi + TEST, n)
        if te_hi - te_lo < 20:
            break
        p = pick(d, tr_lo, tr_hi, opt)
        if p is None:
            folds.append({"from": d["dates"][te_lo], "to": d["dates"][te_hi - 1],
                          "params": None, "stats": None})
            lo += TEST
            continue
        warm = max(p["lookback"], 1)
        s_lo = max(0, te_lo - warm)
        r = run_slice(d, s_lo, te_hi, p, opt=opt, entry_from=te_lo)
        off = te_lo - s_lo
        fd = [pt["dailyPnl"] for pt in r["points"][off:]]
        ft = [t for t in r["trades"] if t["entryDate"] >= d["dates"][te_lo]]
        daily += fd
        trades += ft
        folds.append({"from": d["dates"][te_lo], "to": d["dates"][te_hi - 1],
                      "params": p, "stats": stats(fd, ft),
                      "lo": te_lo, "hi": te_hi})
        lo += TEST
    return {"folds": folds, "daily": daily, "trades": trades,
            "stats": stats(daily, trades),
            "oosLo": folds[0].get("lo") if folds else None,
            "oosHi": folds[-1].get("hi") if folds else None}


def options(**kw) -> dict:
    """한 판의 규칙. 사다리가 이 사전을 한 칸씩 켠다."""
    return {"costBp": kw.get("costBp", LEGACY_COST), "cost": kw.get("cost"),
            "gate": kw.get("gate"), "timeStop": kw.get("timeStop"),
            "reverseExit": kw.get("reverseExit", False)}


# ── 고정 파라미터 한 판 — 사다리의 대조군 ───────────────────────────────────

def fixed_run(d: dict, lo: int, hi: int, p: dict, opt: dict) -> dict:
    """[lo, hi) 를 **고르지 않은** 파라미터로 한 판. 웜업은 앞에서 끌어온다.

    사다리(`walk_forward`)는 칸마다 파라미터를 다시 고르므로, 어떤 rung 의 변화가
    «그 기전» 때문인지 «선택이 바뀌어서» 인지 섞인다. 이 함수는 파라미터를 못
    박아 그 둘을 분리한다 — 기전 하나만 켜고 끄는 대조군이다.
    """
    warm = max(p["lookback"], 1)
    s_lo = max(0, lo - warm)
    r = run_slice(d, s_lo, hi, p, opt=opt, entry_from=lo)
    off = lo - s_lo
    daily = [pt["dailyPnl"] for pt in r["points"][off:]]
    trades = [t for t in r["trades"] if t["entryDate"] >= d["dates"][lo]]
    return {"daily": daily, "trades": trades, "stats": stats(daily, trades)}


def gates_and_cost(d: dict) -> dict:
    """이 계열의 필터·비용 경로를 한 번에."""
    g, pct = vol_gate(d["vals"])
    return {"volGate": g, "volPct": pct, "trendGate": trend_gate(d["vals"]),
            "cost": cost_path(pct)}


def final_options(gc: dict, *, gate: str = "vol") -> dict:
    """지시 다섯이 전부 켜진 규칙."""
    return options(cost=gc["cost"], timeStop=TIME_STOP,
                   gate=gc["volGate"] if gate == "vol" else gc["trendGate"],
                   reverseExit=True)
