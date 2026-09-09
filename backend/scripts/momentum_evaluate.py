# -*- coding: utf-8 -*-
"""Momentum 세 다리를 **평가층**에 태운다 — `mr_evaluate` 와 같은 자리·같은 `evaluate()`.

    python -m scripts.momentum_evaluate                # 세 다리
    python -m scripts.momentum_evaluate blend
    python -m scripts.momentum_evaluate --costs        # 비용 가정을 흔든다

## 이 파일은 «남의 레인» 을 재는 자리다

`app/momentum.py` 와 `app/ctabacktest.py` 는 모멘텀 레인의 것이다 — **여기서
고치지 않는다.** 이 스크립트는 그 레인의 «등록된 북» 을 그대로 다시 세워 평가층에
태우기만 한다. 그래서 재구성이 그 레인의 `build_book()` 과 한 치도 안 달라야 하고,
그 등식을 시험이 잰다(`tests/test_momentum_evaluate.py`) — 그쪽이 구조를 바꾸면
여기가 조용히 딴 것을 재는 대신 **시험이 깨진다.**

## ★ 동결 이후는 안 본다

`data\\krw-macro-vintage\\PREREG.md` 가 2026-09-08 에 동결됐고 「판정일까지
들여다보지 말 것」이 그 문서의 규율이다. 그래서 이 스크립트가 재는 것은
**표본내(동결일까지)** 뿐이다. 엔진(`cta.book_simulate`)은 동결일 **뒤까지**
그리므로 자르는 자리가 여기여야 한다 — `build_book` 이 응답에서 자르는 것과 같은
이유이고, 같은 자름이다.

## 자본 분모를 안 만든다 [OWNER 2026-09-09 — 그 레인의 결정 1]

MR 자리는 액면(원금)으로 나눴는데 이 레인은 오너가 **자본 분모를 안 만들기로**
정했다(무차원 비율로 비교한다). 그래서 수익 계열을 **원(₩) 그대로** 넣는다.

그래도 되는 이유는 이 층이 스케일 불변이기 때문인데, 그 불변은 2026-09-09 에 실제로
**깨져 있다가 고친** 자리다(`vol_normalize` 의 워밍업 `fillna(1.0)` — 원 계열을
넣으면 앞 60봉만 배수 1 로 남아 CDaR 비의 부호까지 갈렸다). 그 수리가 없었으면 이
결정을 집행할 수 없었다.

## 시행수 N — 이 레인이 **확정할** 값이다

그 레인의 문서에서 셋을 읽어 세었다:

    신호계   3   `ctabacktest.SIGNALS`          — macross 를 골랐다
    볼 윈도  3   `cta_validate.VOL_WINDOWS`     — 60 을 골랐다
    다리 구성 4  추세·매크로·50/50·변조          — 변조는 2026-09-09 NO-GO
    ────────────────────────────────────────
    N = 36

**룩백 다섯은 안 셌다.** 그 레인의 규율이 「룩백을 고르지 마라」이고(매년 전진
선택하면 7년 합 −3,230만) 실제로 다섯을 등가중 평균해 쓴다. 고르지 않은 축을
시행으로 세면 PBO 와 SR0 가 «있지도 않은 자유도» 로 벌하게 된다.

⚠ 이 셈은 **내가 그 레인의 문서를 읽어 센 것**이지 그 레인이 사전등록에 적어 둔
값이 아니다. `--trials` 로 덮어쓸 수 있고, 무엇을 셌는지는 보고서의 「가정」에
적힌다. 그 레인이 자기 N 을 확정하면 그 값으로 다시 재는 것이 옳다.

## 칸 행렬은 **다리마다 다르다**

CSCV 는 T × 칸을 먹는데, 이 북에서 축이 실제로 움직이는 범위가 다리마다 다르다.
`book_simulate` 의 `external_signals` 는 `signal`·`lookbacks`·`continuous` 를
**대신하므로**(그 함수의 머리 주석), 매크로 다리에서는 신호 축이 죽는다:

    추세    신호 3 × 볼 윈도 3 = 9칸
    매크로  볼 윈도 3          = 3칸      ← 신호 축이 external 에 막힌다
    50/50   신호 3 × 볼 윈도 3 = 9칸      ← 추세 절반이 움직인다

죽은 축을 칸으로 세우면 같은 열이 셋씩 서고 CSCV 의 순위가 무더기 동점이 된다.
그래서 세우지 않는다 — 그리고 그것이 사실인지는 시험이 잰다(추측이 아니다).

⚠ 매크로 다리는 **3칸**이라 순위 공간이 {1,2,3} 이고 CSCV 가 거칠다. CTA 쪽에서
같은 사정을 적어 둔 그 경고와 같은 자리다(`lane_costs.cta_matrix`).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ctabacktest as cta                              # noqa: E402
from app import momentum as mo                                  # noqa: E402
from evaluation import metrics as ev, report                    # noqa: E402
from scripts.lane_costs import tick_to_bp                       # noqa: E402

#: 그 레인이 실제로 훑은 축. 볼 윈도는 `scripts/cta_validate.py` 의 그 셋인데
#: 거기서 꺼내 오지 않고 **여기 다시 적었다** — 그 파일은 그 레인의 것이고 아직
#: 커밋도 안 됐다. 남의 미커밋 파일에 이 자리를 매달면 그쪽이 지우는 순간 여기가
#: 죽는다. 대신 값이 갈리면 시험(`test_vol_windows_match_the_lane`)이 잡는다.
VOL_WINDOWS: tuple[int, ...] = (20, 60, 120)

#: 다리 구성의 가짓수 — 추세·매크로·50/50 셋에 **변조**를 더한 넷이다. 변조는
#: 2026-09-09 에 NO-GO 로 닫혔지만 «해 본 것» 이므로 시행에서 빼면 안 된다.
LEG_FORMS = 4

LEGS: tuple[str, ...] = ("trend", "macro", "blend")

#: 북 한 판은 1.3초쯤 걸리고 세 다리가 **같은 판을 나눠 쓴다**(50/50 은 추세와
#: 매크로를 합성한 것이라 새 판이 아니다). 그래서 판을 여기 한 곳에 모아 둔다 —
#: 열쇠에 비용(틱)이 들어 있어 `--costs` 가 남의 판을 집어 오지 않는다.
_RUNS: dict = {}

#: N = 신호계 × 볼 윈도 × 다리 구성 (모듈 머리의 그 셈).
TRIALS = len(cta.SIGNALS) * len(VOL_WINDOWS) * LEG_FORMS


def cells_for(leg: str) -> list[tuple[str, int]]:
    """그 다리에서 **실제로 움직이는** 칸 — 모듈 머리의 그 표.

    순수 함수라 시험이 엔진을 안 돌리고도 칸 계획을 잴 수 있다.
    """
    sigs = cta.SIGNALS if leg in ("trend", "blend") else (mo.SIGNAL,)
    return [(s, vw) for s in sigs for vw in VOL_WINDOWS]


# ── 그 레인의 북을 그대로 다시 세운다 ────────────────────────────────────

def _inputs():
    """가격·롤·매크로 — 그 레인의 적재를 그대로 쓴다(따로 읽지 않는다)."""
    series, rolls = mo._load_prices()
    return series, rolls, mo._load_macro()


def _run(series, rolls, *, signal: str, vol_window: int, ticks: float,
         external=None) -> dict:
    """`momentum._run_book` 과 같은 호출 — 흔드는 축만 인자로 뺐다."""
    return cta.book_simulate(
        series, signal=signal, lookbacks=mo.LOOKBACKS, vol_window=vol_window,
        target_book_vol_krw=mo.TARGET_VOL, book_vol_window=mo.BOOK_VOL_WINDOW,
        roll_days=rolls, continuous=True, external_signals=external,
        cost_ticks=ticks)


def _cut(points: list[dict], start: str | None) -> list[dict]:
    """동결일까지만 — `build_book` 의 `cut` 과 **같은 자름**이다."""
    return [p for p in points
            if p["t"] <= mo.FREEZE and (start is None or p["t"] >= start)]


def _blend(t_pts: list[dict], m_pts: list[dict]) -> list[dict]:
    """50/50 — 두 북을 따로 돌려 **손익**을 반씩(그 레인의 그 합성)."""
    mi = {p["t"]: p for p in m_pts}
    return [{"t": p["t"],
             "dailyPnl": 0.5 * p["dailyPnl"] + 0.5 * mi[p["t"]]["dailyPnl"],
             "barCost": 0.5 * p["barCost"] + 0.5 * mi[p["t"]]["barCost"]}
            for p in t_pts if p["t"] in mi]


def legs_of(series, rolls, macro, *, signal: str = mo.SIGNAL,
            vol_window: int = mo.VOL_WINDOW, ticks: float = cta.COST_TICKS,
            cache: dict | None = None) -> dict[str, list[dict]]:
    """다리 → 봉 목록. 기본 인자면 그 레인의 `build_book()` 과 같은 것이 나온다."""
    start = None if macro is None else min(macro["macro_sign"])

    def run(external_key: str | None):
        key = (signal, vol_window, ticks, external_key)
        if cache is not None and key in cache:
            return cache[key]
        ext = None if external_key is None else {k: macro["macro_sign"]
                                                 for k in series}
        out = _run(series, rolls, signal=signal, vol_window=vol_window,
                   ticks=ticks, external=ext)
        if cache is not None:
            cache[key] = out
        return out

    t_pts = _cut(run(None)["points"], start)
    if macro is None:
        return {"trend": t_pts}
    m_pts = _cut(run("macro")["points"], start)
    return {"trend": t_pts, "macro": m_pts, "blend": _blend(t_pts, m_pts)}


def returns_of(points: list[dict]) -> pd.Series:
    """봉의 손익(₩) 그대로 — **자본 분모를 안 만든다**(모듈 머리의 그 결정)."""
    return pd.Series([p["dailyPnl"] for p in points],
                     index=[p["t"] for p in points], dtype=float)


def config_matrix(series, rolls, macro, leg: str, ticks: float,
                  cache: dict | None = None) -> pd.DataFrame:
    """칸마다의 수익 계열 — CSCV 가 먹는 T × 칸.

    날짜로 맞춰 붙인다. 볼 윈도가 달라지면 앞쪽 워밍업이 달라질 수 있어서
    자리로 붙이면 서로 다른 날이 한 줄에 서게 된다.
    """
    cols: dict[str, pd.Series] = {}
    for sg, vw in cells_for(leg):
        pts = legs_of(series, rolls, macro, signal=sg, vol_window=vw,
                      ticks=ticks, cache=cache)[leg]
        cols[f"{sg}-vw{vw}"] = returns_of(pts)
    return pd.DataFrame(cols).dropna()


def evaluate_leg(leg: str, *, trials: int | None = None, splits: int = 16,
                 ticks: float = cta.COST_TICKS) -> dict:
    series, rolls, macro = _inputs()
    if macro is None and leg != "trend":
        raise SystemExit(f"매크로 신호가 없어서 「{leg}」 다리를 못 세웠어요 — "
                         f"{mo.THEMES_CSV} 가 있어야 해요.")
    pts = legs_of(series, rolls, macro, ticks=ticks, cache=_RUNS)[leg]
    rets = returns_of(pts)
    mat = config_matrix(series, rolls, macro, leg, ticks, cache=_RUNS)
    #: 격자 칸들의 SR 분산 — 있으면 SR0 가 「이 격자에서 뽑기로 나오는 최고」가 된다.
    sr_var = float(((mat.mean() / mat.std(ddof=1)).dropna()).var(ddof=1))
    bp3, _y, _f = tick_to_bp("3Y", ticks)
    bp10, _y, _f = tick_to_bp("10Y", ticks)
    return ev.evaluate(
        rets.reset_index(drop=True), trials=trials if trials is not None else TRIALS,
        is_oos_splits=splits, configs=mat,
        sr_var=sr_var if sr_var > 0 else None,
        strategy_id=f"Momentum-{leg}",
        cost_bp_roundtrip=bp3 * 2,
        assumptions=[
            "자본 분모를 안 만들었다 [OWNER 2026-09-09] — 수익 계열이 원(₩) 손익 "
            "그대로다. 이 층은 스케일 불변이라 게이트·순위가 안 바뀐다.",
            f"비용 편도 {ticks}틱 = 3Y {bp3:.3f}bp · 10Y {bp10:.3f}bp. MR 자리는 "
            f"편도 0.5bp 라 **단위가 다르다** — 같은 bp 를 선물에 물리는 것은 없는 "
            f"비용을 가정하는 것이라 안 했고, 대신 `--costs` 가 양쪽을 각자의 "
            f"단위로 흔들어 판정이 뒤집히는지를 본다.",
            f"시행수 N = {trials if trials is not None else TRIALS} "
            f"(신호계 {len(cta.SIGNALS)} × 볼 윈도 {len(VOL_WINDOWS)} × 다리 구성 "
            f"{LEG_FORMS}). **룩백 다섯은 안 셌다** — 그 레인이 고르지 않는 축이다. "
            f"이 셈은 그 레인의 문서를 읽어 센 것이지 사전등록에 적힌 값이 아니다.",
            f"칸 {mat.shape[1]}개 · {mat.shape[0]}봉."
            + (" 매크로 다리는 신호 축이 external_signals 에 막혀 3칸뿐이라 "
               "CSCV 가 거칠다." if leg == "macro" else ""),
            f"표본 {pts[0]['t']}~{pts[-1]['t']} · {len(pts)}봉 — **동결일 "
            f"{mo.FREEZE} 까지만**이다. 사전등록의 채점 구간은 안 봤다.",
        ])


def verdicts_by_cost(splits: int = 16) -> None:
    """비용을 흔들면 판정이 뒤집히나 — MR 자리의 그 물음을 이 레인에도."""
    print()
    print("── 비용 가정을 흔들면 판정이 뒤집히나 ──────────────────")
    print(f"  {'다리/가정':22s} {'DSR':>8s} {'PBO':>8s} {'CDaR비':>8s}  판정")
    for ticks in (0.25, 0.5, 1.0):
        for leg in LEGS:
            out = evaluate_leg(leg, splits=splits, ticks=ticks)
            _row(f"{leg} 편도 {ticks}틱", out)


def trials_sweep(leg: str = "blend", splits: int = 16) -> None:
    """**N 을 흔들면 판정이 뒤집히나** — 「그 레인이 N 을 확정하면」을 기다리지 않는다.

    이 자리의 N=36 은 내가 그 레인의 문서를 읽어 센 값이라 그 레인이 다르게 셀 수
    있다. 기다리는 대신 **범위를 재 두면** 그 확정이 판정을 바꿀 일인지 아닌지가
    미리 나온다 — 「가정하지 말고 재라」의 N 판이다.

        9    룩백을 안 세고 다리 구성도 안 센 최소치(신호계 × 볼 윈도)
        36   지금 값(신호계 × 볼 윈도 × 다리 구성)
        180  룩백 다섯까지 시행으로 센 최대치 — 그 레인의 규율상 틀린 셈이지만
             **N 이 다섯 배가 돼도 판정이 그대로면** 이 축은 결론을 안 흔든다
    """
    print()
    print(f"── N 을 흔들면 판정이 뒤집히나 (「{leg}」) ──────────────")
    print(f"  {'시행수 N':22s} {'DSR':>8s} {'PBO':>8s} {'CDaR비':>8s}  판정")
    for n in (9, TRIALS, 180):
        _row(f"N = {n}", evaluate_leg(leg, trials=n, splits=splits))
    print()
    print("  ⚠ PBO 는 N 과 무관하다 — CSCV 는 **칸 행렬**만 먹는다. 움직이는 것은")
    print("     DSR 뿐이고, 그것이 이 표가 답하는 물음이다.")


def _row(label: str, out: dict, tail: str = "") -> None:
    """없는 값은 «—» 다 — 게이트에 떨어지면 CDaR 비를 **아예 안 낸다**(사양)."""
    g, r = out["gate"], out["ranking"]

    def num(v, w, f):
        return f"{v:{w}{f}}" if v is not None else f"{'—':>{w}}"

    print(f"  {label:22s} {num(g['dsr'], 8, '.4f')} {num(g['pbo'], 8, '.4f')} "
          f"{num(r['cdar_ratio'], 8, '.3f')}  "
          f"{'통과' if g['overall_pass'] else '미통과'}{tail}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("leg", nargs="?", default=None, choices=[*LEGS, None])
    ap.add_argument("--trials", type=int, default=None)
    ap.add_argument("--splits", type=int, default=16)
    ap.add_argument("--ticks", type=float, default=cta.COST_TICKS)
    ap.add_argument("--costs", action="store_true", help="비용 가정 민감도")
    ap.add_argument("--trials-sweep", action="store_true", dest="sweep",
                    help="시행수 N 민감도")
    a = ap.parse_args()

    if a.sweep:
        trials_sweep(a.leg or "blend", a.splits)
        return 0
    if a.costs:
        verdicts_by_cost(a.splits)
        return 0

    legs = [a.leg] if a.leg else list(LEGS)
    print(f"{'다리':22s} {'DSR':>8s} {'PBO':>8s} {'CDaR비':>8s}  판정   보고서")
    for leg in legs:
        out = evaluate_leg(leg, trials=a.trials, splits=a.splits, ticks=a.ticks)
        path = report.write(out)
        _row(leg, out, tail=f"   {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
