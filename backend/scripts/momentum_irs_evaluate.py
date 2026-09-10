# -*- coding: utf-8 -*-
r"""IRS 로 세운 추세 다리를 **같은 게이트**에 태운다 — 「무엇으로 세우나」를 판정으로.

    python -m scripts.momentum_irs_evaluate            # 두 계기를 같은 창에서
    python -m scripts.momentum_irs_evaluate --costs    # 비용 가정을 흔든다
    python -m scripts.momentum_irs_evaluate --full     # IRS 가 가진 한 해를 더 쓴다

## 왜 이 자리가 필요한가

`scripts/momentum_irs.py` 가 2026-09-09 에 낸 것은 **카드**였다 — 같은 신호를 IRS 로
세우면 Sharpe 0.63 → 0.94. 그런데 그 표는 게이트를 안 통과한 수다. 지난 세션이
배운 것이 바로 그 자리다: **점추정만 보고 「4.9배 낫다」고 적었는데 구간을 열자
서로를 담고 있었다.** 그래서 계기를 바꾸는 결정도 카드가 아니라 판정문 위에서
해야 한다 — DSR · PBO · CDaR 비, 그리고 **오차막대**.

## 계기가 «고르는 축»이 되면 시행수가 는다

`momentum_evaluate.TRIALS` 는 36 이다(신호계 3 × 볼 윈도 3 × 다리 구성 4). 거기에
**선물이냐 IRS 냐**가 붙으면 그 레인이 훑은 칸이 두 배가 된다:

    N = 36 × 2 = 72

이건 벌이 아니라 회계다. 「IRS 가 낫더라」는 문장은 둘을 다 보고 나온 것이므로,
그 문장을 정당화하는 DSR 은 **둘을 다 본 N** 으로 재야 한다. 세지 않으면 계기를
갈아타는 것만으로 게이트가 헐거워진다.

## 창을 맞춘다 — 이 레인이 한 번 틀린 자리

`momentum_irs.py` 의 `START` 가 2017-01-06 이라 선물 추세 다리의 표본
(2017-01-06~2026-09-08 · 2370봉)과 겉으로는 같아 보이지만, IRS 고시 달력과 선물
거래일이 한 치도 같지는 않다. 그래서 **두 북의 날짜를 실제로 교집합**한 뒤 양쪽을
그 위에서 다시 잰다. 선물 쪽 판정문(`Momentum-trend.md`)과 숫자가 조금 다른 것은
결함이 아니라 **같은 자로 잰 결과**다.

`--full` 은 IRS 가 가진 2016 년까지 내려가는데, 그건 **비교가 아니라 서술**이다 —
선물 쪽에 없는 해라서 나란히 못 놓는다.

## 비용은 양쪽 다 정해져 있다

    IRS   편도 0.5bp                 [OWNER] — 이 리포의 그 상수
    선물  편도 0.5틱(규약)           3Y 0.175bp · 10Y 0.060bp 로 환산된다
          계약별 실측 0.43 / 1.20틱  (ktbf_flow 레인)

엔진이 계약별 비용을 안 받으므로 선물은 **범위**로 낸다. `--costs` 가 읽을 것은
「어느 조합에서든 판정이 같은가」 하나다.

## 칸

양쪽 다 신호계 3 × 볼 윈도 3 = **9칸**이다. IRS 북은 `external_signals` 를 안 쓰므로
신호 축이 살아 있다(매크로 다리에서 축이 죽던 그 사정이 여기엔 없다).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ctabacktest as cta                              # noqa: E402
from app import momentum as mo                                  # noqa: E402
from app.mysqldb import engine                                  # noqa: E402
from evaluation import metrics as ev, randomization as rz, report  # noqa: E402
from scripts import momentum_evaluate as me                     # noqa: E402
from scripts.lane_costs import tick_to_bp                       # noqa: E402

#: 선물 추세 다리의 표본 첫날 — `momentum_irs.START` 와 같은 값이고, 같은 이유로
#: 여기 다시 적었다(그 파일에서 꺼내 오면 그쪽이 창을 바꿀 때 여기가 조용히 따라간다).
START = "2017-01-06"

#: IRS 자료가 실제로 시작하는 날. `--full` 에서만 쓴다.
FULL_START = "2016-01-04"

#: IRS 편도 호가폭(bp) [OWNER 2026-09-09].
IRS_COST_BP = 0.5

#: 계기 축이 열렸다 — 그 레인의 N 에 «선물이냐 IRS 냐» 둘을 곱한다.
INSTRUMENTS = 2
TRIALS = me.TRIALS * INSTRUMENTS

#: 그 레인의 기본 칸 — 대표 계열로 쓴다.
BASE_COL = f"{mo.SIGNAL}-vw{mo.VOL_WINDOW}"

_IRS_RUNS: dict = {}
_SERIES: dict = {}


# --- IRS 계열 ----------------------------------------------------------

def load_irs_series(start: str = START) -> dict[str, tuple[list[str], list[float]]]:
    """`mkt_irs_close` par 금리를 **-bp** 로 — `momentum_irs.load_irs_bp` 와 같은 계열.

    부호를 뒤집는 이유는 하나다: 엔진은 「값이 오르면 롱이 번다」로 회계하는데 IRS 는
    금리가 내려야 리시브가 번다. 뒤집으면 +1 이 리시브가 되고 그 뒤로는 선물 북과
    같은 문장을 쓴다. 합성가(채권 가격식)를 안 만든다 — 이 데스크의 IRS 회계는
    bp × 명목이다.
    """
    key = ("series", start)
    if key in _SERIES:
        return _SERIES[key]
    with engine().connect() as conn:
        rows = conn.execute(text(
            "SELECT irs_date, irs_3y, irs_10y FROM mkt_irs_close "
            "WHERE irs_3y IS NOT NULL AND irs_10y IS NOT NULL ORDER BY irs_date ASC"
        )).fetchall()
    days, r3, r10 = [], [], []
    for r in rows:
        d = r[0]
        day = (d.date() if hasattr(d, "date") else d).isoformat()
        if not (start <= day <= mo.FREEZE):
            continue
        days.append(day)
        r3.append(-float(r[1]) * 100.0)
        r10.append(-float(r[2]) * 100.0)
    out = {"3Y": (days, r3), "10Y": (days, r10)}
    _SERIES[key] = out
    return out


def irs_points(*, signal: str = mo.SIGNAL, vol_window: int = mo.VOL_WINDOW,
               cost_bp: float = IRS_COST_BP, start: str = START) -> list[dict]:
    """IRS 추세북의 봉 — `momentum_irs.run` 과 **같은 호출**이다.

    롤이 없다(`roll_days=set()`). IRS 는 만기가 굴러오는 계약이 아니라 그날의 par
    금리라 롤 점프 자체가 없고, 그래서 선물 북이 롤에 물던 비용도 여기엔 없다.
    """
    key = (signal, vol_window, cost_bp, start)
    if key in _IRS_RUNS:
        return _IRS_RUNS[key]
    series = load_irs_series(start)
    book = cta.book_simulate(
        series, signal=signal, lookbacks=mo.LOOKBACKS, vol_window=vol_window,
        target_book_vol_krw=mo.TARGET_VOL, book_vol_window=mo.BOOK_VOL_WINDOW,
        roll_days=set(), continuous=True, cost_ticks=cost_bp / cta.TICK)
    _IRS_RUNS[key] = book["points"]
    return book["points"]


# --- 두 계기를 같은 창 위에 --------------------------------------------

def _fut_points(signal: str, vol_window: int, ticks: float) -> list[dict]:
    series, rolls, macro = me._inputs()
    return me.legs_of(series, rolls, macro, signal=signal, vol_window=vol_window,
                      ticks=ticks, cache=me._RUNS)["trend"]


def _cells() -> list[tuple[str, int]]:
    return [(s, vw) for s in cta.SIGNALS for vw in me.VOL_WINDOWS]


def irs_matrix(*, cost_bp: float = IRS_COST_BP,
               start: str = START) -> pd.DataFrame:
    return pd.DataFrame({
        f"{s}-vw{vw}": me.returns_of(
            irs_points(signal=s, vol_window=vw, cost_bp=cost_bp, start=start))
        for s, vw in _cells()}).dropna()


def fut_matrix(*, ticks: float = cta.COST_TICKS) -> pd.DataFrame:
    return pd.DataFrame({
        f"{s}-vw{vw}": me.returns_of(_fut_points(s, vw, ticks))
        for s, vw in _cells()}).dropna()


def matrices(*, ticks: float = cta.COST_TICKS,
             cost_bp: float = IRS_COST_BP) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(IRS, 선물) 칸 행렬 — **같은 날짜 위**로 잘라서 돌려준다."""
    irs, fut = irs_matrix(cost_bp=cost_bp), fut_matrix(ticks=ticks)
    idx = irs.index.intersection(fut.index)
    return irs.loc[idx], fut.loc[idx]


def _sr_var(mat: pd.DataFrame) -> float | None:
    v = float(((mat.mean() / mat.std(ddof=1)).dropna()).var(ddof=1))
    return v if v > 0 else None


def _placebo_for(which: str, *, cost_bp: float = IRS_COST_BP,
                 ticks: float = cta.COST_TICKS, mask_index=None) -> dict:
    """게이트 셋째 — 순환이동 위약 [OWNER 2026-09-10].

    이 층은 위약을 스스로 못 만든다(수익 계열만으로는 포지션을 못 되돌린다).
    북을 가진 이 자리가 재서 넘긴다.
    """
    if which == "IRS":
        series = load_irs_series()
        rolls: set = set()
        tk = cost_bp / cta.TICK
        book = cta.book_simulate(
            series, signal=mo.SIGNAL, lookbacks=mo.LOOKBACKS,
            vol_window=mo.VOL_WINDOW, target_book_vol_krw=mo.TARGET_VOL,
            book_vol_window=mo.BOOK_VOL_WINDOW, roll_days=set(),
            continuous=True, cost_ticks=tk)
    else:
        series, rolls = mo._load_prices()
        tk = ticks
        book = cta.book_simulate(
            series, signal=mo.SIGNAL, lookbacks=mo.LOOKBACKS,
            vol_window=mo.VOL_WINDOW, target_book_vol_krw=mo.TARGET_VOL,
            book_vol_window=mo.BOOK_VOL_WINDOW, roll_days=rolls,
            continuous=True, cost_ticks=tk)
    price = {k: dict(zip(*series[k])) for k in series}
    pl = rz.plumbing(book["dates"], price, rolls, tk, cta.TICK)
    keep = None if mask_index is None else set(mask_index)
    mask = (None if keep is None
            else np.array([t in keep for t in book["dates"]]))
    #: 이동 하한 = 최장 룩백. 그보다 짧게 밀면 신호가 덜 끊긴다.
    return rz.placebo(pl, book["pos"], shift_min=max(mo.LOOKBACKS), mask=mask)


def _selection_for(mat: pd.DataFrame) -> dict:
    """진단 — 격자에서 매년 고르면 얼마 잃나(§17-4). **게이트가 아니다.**

    고르는 자는 오너가 정한 순위기준(CDaR 비)이다. 표본내 SR 로 고르면 부호가
    뒤집히는 다리가 있어서(§17-4), 우리가 «실제로 쓰는» 자로 재야 뜻이 있다.
    """
    from scripts import hard_test as ht                       # noqa: PLC0415
    w = ht.walk_forward(mat, score=ht._score_cdar)
    picked, fixed = float(w["picked"].sum()), float(w["fixed"].sum())
    return {"picked": picked, "fixed": fixed, "delta": picked - fixed,
            "basis": "CDaR 비[OWNER]"}


def evaluate_side(name: str, mat: pd.DataFrame, *, trials: int = TRIALS,
                  splits: int = 16, cost_bp_rt: float,
                  placebo: dict | None = None, selection: dict | None = None,
                  notes: list[str]) -> dict:
    """한 계기의 판정문. 대표 계열은 그 레인의 기본 칸(`macross-vw60`)이다."""
    return ev.evaluate(
        mat[BASE_COL].reset_index(drop=True), trials=trials,
        is_oos_splits=splits, configs=mat, sr_var=_sr_var(mat),
        strategy_id=name, cost_bp_roundtrip=cost_bp_rt,
        placebo=placebo, selection=selection,
        assumptions=notes + [
            "자본 분모를 안 만들었다 [OWNER 2026-09-09] — 수익 계열이 원(₩) 손익 "
            "그대로다. 두 북 다 `target_book_vol_krw` 로 **같은 ₩ 변동성**에 "
            "맞춰져 있어서 위험을 맞춘 뒤의 비교다.",
            f"시행수 N = {trials} (신호계 {len(cta.SIGNALS)} × 볼 윈도 "
            f"{len(me.VOL_WINDOWS)} × 다리 구성 {me.LEG_FORMS} × 계기 "
            f"{INSTRUMENTS}). **계기를 축으로 세었다** — 「IRS 가 낫더라」는 둘을 "
            f"다 보고 나온 문장이라 그것을 정당화하는 DSR 도 둘을 다 본 N 이어야 "
            f"한다.",
            f"칸 {mat.shape[1]}개 · {mat.shape[0]}봉 "
            f"({mat.index[0]}~{mat.index[-1]}).",
        ])


def _row(label: str, out: dict, tail: str = "") -> None:
    """없는 값은 «—» 다 — 게이트에 떨어지면 CDaR 비를 아예 안 낸다(사양)."""
    g, r = out["gate"], out["ranking"]

    def num(v, w, f):
        return f"{v:{w}{f}}" if v is not None else f"{'—':>{w}}"

    ci, sci = r["cdar_ratio_ci"], r["sr_lo_ci"]
    print(f"  {label:24s} {num(g['dsr'], 8, '.4f')} {num(g['pbo'], 8, '.4f')} "
          f"{num(r['cdar_ratio'], 8, '.3f')}  "
          f"[{num(ci[0], 5, '.2f')},{num(ci[1], 6, '.2f')}] "
          f"[{num(sci[0], 5, '.2f')},{num(sci[1], 6, '.2f')}]  "
          f"{'통과' if g['overall_pass'] else '미통과'}{tail}")


HDR = (f"  {'계기':24s} {'DSR':>8s} {'PBO':>8s} {'CDaR비':>8s}  "
       f"{'CDaR비 90%':>13s} {'Lo SR 90%':>13s}  판정")


def head_to_head(splits: int = 16, ticks: float = cta.COST_TICKS,
                 cost_bp: float = IRS_COST_BP, write: bool = True) -> dict:
    irs, fut = matrices(ticks=ticks, cost_bp=cost_bp)
    bp3, _y, _f = tick_to_bp("3Y", ticks)
    bp10, _y, _f = tick_to_bp("10Y", ticks)
    o_irs = evaluate_side(
        "Momentum-trend-IRS", irs, splits=splits, cost_bp_rt=cost_bp * 2,
        placebo=_placebo_for("IRS", cost_bp=cost_bp, mask_index=irs.index),
        selection=_selection_for(irs),
        notes=[f"IRS 편도 {cost_bp}bp [OWNER] — 왕복 {cost_bp * 2}bp. 합성가가 "
               f"아니라 par 금리(-bp)를 그대로 넣었고 회계는 bp × 명목이다. "
               f"롤이 없다."])
    o_fut = evaluate_side(
        "Momentum-trend-FUT-on-IRS-window", fut, splits=splits,
        cost_bp_rt=bp3 * 2,
        placebo=_placebo_for("선물", ticks=ticks, mask_index=fut.index),
        selection=_selection_for(fut),
        notes=[f"선물 편도 {ticks}틱 = 3Y {bp3:.3f}bp · 10Y {bp10:.3f}bp. "
               f"`Momentum-trend.md` 와 같은 북이지만 **IRS 달력과 교집합한 창** "
               f"위에서 다시 쟀다 — 그래서 숫자가 조금 다르다."])
    print()
    print(f"── 추세 다리를 무엇으로 세우나 · 공통 창 {irs.index[0]}~{irs.index[-1]} "
          f"· {len(irs):,}봉 ──")
    print(HDR)
    for label, out in ((f"IRS (편도 {cost_bp:.1f}bp)", o_irs),
                       (f"선물 (편도 {ticks:.2f}틱)", o_fut)):
        _row(label, out, tail=f"   {report.write(out).name}" if write else "")
    return {"irs": o_irs, "fut": o_fut, "n": len(irs)}


def paired_ci(a: pd.Series, b: pd.Series, stat, *, block: int = ev.BOOT_BLOCK,
              n: int = ev.BOOT_N, seed: int = ev.BOOT_SEED) -> dict:
    """**차이**의 90% 구간 — 두 계열을 «같은 블록»으로 다시 뽑는다.

    ## 왜 주변 구간 둘을 눈으로 겹쳐 보면 안 되나

    이 자리가 지난 세션의 그 실수를 한 칸 더 밀고 간 곳이다. 그때 배운 것은
    「점추정만 보고 낫다고 하지 마라」였는데, 그 교훈을 그대로 적용해 주변 구간
    둘을 겹쳐 보는 것도 **차이의 검정이 아니다**. 두 북은 같은 날짜 위에 있고 일별
    손익이 상관돼 있어서, 각자의 폭에는 «시장이 어떤 해였나»가 통째로 들어 있고
    그 부분은 둘에 **공통**이다. 공통 부분은 차이에서 지워진다.

    그래서 블록 시작점을 **한 번만** 뽑아 두 계열에 같이 먹인 뒤 그 판에서의
    차이를 잰다. 남는 폭이 「계기를 바꿔서 생긴 차이」의 진짜 불확실성이다.

    돌려주는 `p_le0` 는 뽑기 중 차이가 0 이하였던 비율이다 — 구간이 0 을 안 물면
    그 표본에서 방향이 식별된 것이고, 물면 못 가른 것이다.
    """
    x = a.to_numpy(dtype=float)
    y = b.to_numpy(dtype=float)
    if x.size != y.size:
        raise ValueError("짝이 안 맞아요 — 같은 창에서 잘라 넣어야 해요")
    rng = ev.np.random.default_rng(seed)
    nb = int(ev.np.ceil(x.size / block))
    diffs: list[float] = []
    for _ in range(n):
        starts = rng.integers(0, x.size, nb)
        idx = ev.np.concatenate(
            [ev.np.arange(s, s + block) for s in starts])[:x.size] % x.size
        va, vb = stat(pd.Series(x[idx])), stat(pd.Series(y[idx]))
        if va is not None and vb is not None and ev.np.isfinite(va - vb):
            diffs.append(float(va - vb))
    if len(diffs) < 20:
        return {"lo": None, "hi": None, "p_le0": None, "n": len(diffs)}
    arr = ev.np.array(diffs)
    return {"lo": float(ev.np.percentile(arr, 5)),
            "hi": float(ev.np.percentile(arr, 95)),
            "median": float(ev.np.median(arr)),
            "p_le0": float((arr <= 0).mean()), "n": len(arr)}


def _cdar_of(s: pd.Series) -> float | None:
    return ev.cdar_ratio(ev.vol_normalize(s)[0])["cdar_ratio"]


def difference(splits: int = 16, ticks: float = cta.COST_TICKS,
               cost_bp: float = IRS_COST_BP) -> None:
    """IRS − 선물 — 짝지은 차이로. 「어느 쪽이 크냐」를 처음으로 검정한다."""
    irs, fut = matrices(ticks=ticks, cost_bp=cost_bp)
    a, b = irs[BASE_COL], fut[BASE_COL]
    print()
    print(f"── IRS − 선물 · 짝지은 차이 ({len(a):,}봉 · 블록 {ev.BOOT_BLOCK} · "
          f"뽑기 {ev.BOOT_N}) ──")
    print(f"  일별 손익 상관 {float(a.corr(b)):+.3f}")
    print(f"  {'지표':22s} {'IRS':>8s} {'선물':>8s} {'차이':>8s} "
          f"{'뽑기 중앙':>9s} {'차이 90% 구간':>18s}  {'P(차이≤0)':>9s}")
    for name, stat in (("Lo 보정 SR", ev.sharpe_lo), ("CDaR 비", _cdar_of)):
        va, vb = stat(a), stat(b)
        d = paired_ci(a, b, stat)
        flag = " ⚠" if (d["median"] - (va - vb)) * (va - vb) < 0 else ""
        print(f"  {name:22s} {va:8.3f} {vb:8.3f} {va - vb:8.3f} "
              f"{d['median']:9.3f} [{d['lo']:7.3f},{d['hi']:8.3f}] "
              f"{d['p_le0']:9.3f}{flag}")
    print()
    print("  주변 구간 둘을 겹쳐 보는 것은 차이의 검정이 아니다 — 두 북은 같은 날짜")
    print("  위에 있고 그 공통 부분이 차이에서 지워진다. 이 표가 그 자리다.")
    print("  ⚠ = 뽑기 중앙이 점추정의 **반대편**에 있다. 그 지표의 점추정이 이 표본에서")
    print("     안정한 요약이 아니라는 뜻이다 — 꼬리가 낙폭 사건 한둘 위에 서 있으면")
    print("     블록을 다시 뽑을 때마다 그 사건이 들었다 났다 한다.")


def by_cost(splits: int = 16) -> None:
    """비용을 흔들면 계기 판정이 뒤집히나 — 두 축을 각자의 단위로."""
    print()
    print("── 비용을 흔들면 계기 판정이 뒤집히나 ────────────────────")
    print(HDR)
    ref = irs_matrix()
    fut_ref = fut_matrix()
    idx = ref.index.intersection(fut_ref.index)
    for bp in (0.25, IRS_COST_BP, 1.0):
        mat = irs_matrix(cost_bp=bp).loc[idx]
        _row(f"IRS 편도 {bp:.2f}bp",
             evaluate_side(f"tmp-irs-{bp}", mat, splits=splits,
                           cost_bp_rt=bp * 2, notes=[]))
    for tk, tag in ((0.43, "3Y 실측"), (cta.COST_TICKS, "규약"), (1.20, "10Y 실측")):
        mat = fut_matrix(ticks=tk).loc[idx]
        bp3, _y, _f = tick_to_bp("3Y", tk)
        _row(f"선물 편도 {tk:.2f}틱({tag})",
             evaluate_side(f"tmp-fut-{tk}", mat, splits=splits,
                           cost_bp_rt=bp3 * 2, notes=[]))
    print()
    print("  ⚠ 판정문은 안 쓴다(임시 이름) — 이 표는 민감도이지 등록된 수가 아니다.")


def full_sample(splits: int = 16) -> None:
    """IRS 가 가진 한 해를 더 — **비교가 아니라 서술**이다(선물엔 없는 해)."""
    mat = irs_matrix(start=FULL_START)
    out = evaluate_side(
        "Momentum-trend-IRS-full", mat, splits=splits,
        cost_bp_rt=IRS_COST_BP * 2,
        notes=[f"표본을 IRS 자료 첫날({FULL_START})까지 늘렸다. 선물엔 없는 해라 "
               f"**나란히 못 놓는다** — 이 줄은 「표본이 길어지면 게이트가 어떻게 "
               f"움직이나」만 답한다."])
    print()
    print(f"── IRS 표본을 {FULL_START} 까지 늘리면 ({len(mat):,}봉) ──")
    print(HDR)
    _row("IRS · 긴 표본", out, tail=f"   {report.write(out).name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", type=int, default=16)
    ap.add_argument("--costs", action="store_true", help="비용 민감도")
    ap.add_argument("--full", action="store_true", help="IRS 긴 표본")
    ap.add_argument("--diff-only", action="store_true", dest="diff",
                    help="짝지은 차이만")
    a = ap.parse_args()

    if a.costs:
        by_cost(a.splits)
        return 0
    if a.full:
        full_sample(a.splits)
        return 0
    if a.diff:
        difference(a.splits)
        return 0
    head_to_head(a.splits)
    difference(a.splits)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
