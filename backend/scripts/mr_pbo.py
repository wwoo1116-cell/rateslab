# -*- coding: utf-8 -*-
"""격자 과적합을 **확률**로 — CSCV/PBO [OWNER 2026-09-07 — "B는 한 번 테스트"].

## 오늘 아침에 한 것과 무엇이 다른가

`mr_grid_oos.py` 는 표본을 **한 번** 갈라 앞절반 순위가 뒤절반과 맞는지 봤다
(통합 ρ 0.73). 분할이 하나라 그 수의 표준오차를 못 냈다.

CSCV(Bailey·Borwein·López de Prado·Zhu)는 표본을 S 조각으로 잘라 **가능한 모든
절반 조합**에서 같은 일을 한다: 훈련 절반에서 1등을 뽑고, 그 칸이 **시험 절반에서
몇 등인지**를 본다. 1등이 시험에서 중앙값 아래로 떨어지는 **빈도**가 PBO 다.

    PBO = P(logit(ω) < 0),  ω = 시험 절반에서 그 칸의 상대 순위

## ★ 그런데 이 방법에는 알려진 비판이 있다 — 그것부터 검정한다

「후보 수 N 이 커지면 **실제 예측력과 무관하게** PBO 가 1 로 간다」. 162칸이면
그 영역에 들어갈 수 있다. 그래서 이 스크립트는 PBO 를 **N=18·54·162 에서 각각**
재고, 그 수가 N 을 따라 오르는지 본다. **오르면 PBO 는 이 격자에서 못 쓰는
지표**이고, 그 사실을 아는 것이 PBO 값 자체보다 중요하다.

같은 이유로 **양성·음성 대조군**을 같이 돌린다:

    양성  진짜 신호가 있는 칸 하나를 심는다 → PBO 가 낮아야 한다
    음성  전 칸을 순수 잡음으로 바꾼다     → PBO 가 0.5 근처여야 한다

대조군이 그 값을 안 내면 배관이 틀린 것이고, 본 결과를 읽으면 안 된다.
(이 리포의 규율 — 「NO-GO 전 배관검증」·「양성대조군 항등식」.)

## 지표 — 왜 Sharpe·Sortino 인가

CSCV 는 훈련 절반(= 떨어진 조각들을 이어 붙인 것) 위에서 지표를 다시 잰다.
**Sharpe·Sortino 는 조각별 합(Σx·Σx²·Σmin(x,0)²·n)에서 재조립되므로** 12,870
조합을 벡터로 돌릴 수 있다. **Calmar·Martin 은 경로 의존**이라 그렇게 못 하고
(최대낙폭은 조각을 잇는 **순서**에 달렸다), 조합마다 822봉을 다시 훑어야 한다 —
S=10(252조합)에서만 같이 낸다.

이 데스크가 화면에서 샤프를 내린 것과 여기서 쓰는 것은 **다른 일**이다. 여기서
재는 것은 「이 선택 절차가 과적합하나」이지 「이 전략이 좋나」가 아니다.

돌리기:  python -m scripts.mr_pbo
"""

from __future__ import annotations

import itertools
import math
import statistics as st

import numpy as np

from app import funding, mr as mr_mod, mrbacktest as mrbt, mrbook
from app.main import MR_ENTRY_MODES_ALL, _mr_leg


KN = dict(lookback=60, entryZ=2.0, exitZ=0.5, stopZ=3.5, costBp=0.5,
          notional=1_000_000.0, carry=True, entryMode="level", timeStop=0,
          costModel="flat", regime="none", countOpen=False)


def build_matrix() -> tuple[np.ndarray, list[tuple]]:
    """T×N 일별 손익 행렬 — 칸마다 통합 장부(아홉 만기)의 그날 손익.

    칸의 값은 **더한 뒤에** 나온다(다리별 값의 평균이 아니다) — `_mr_book_optimize`
    와 같은 사상이고, Calmar·낙폭이 비선형이라 그래야 맞다.
    """
    spec = funding.FundingSpec().validated()
    legs = []
    for sid, _l in mrbook.bss_series():
        try:
            legs.append(_mr_leg(sid, spec=spec, **KN))
        except Exception as exc:                               # noqa: BLE001
            print(f"  [빠짐] {sid}: {exc}")
    dates = sorted({t for leg in legs for t in leg["dates"]})
    at = {t: i for i, t in enumerate(dates)}

    opts = {k: list(mr_mod.STRATEGY_PRESETS[k]) for k in ("lookback", "entryZ", "exitZ", "stopZ")}
    cols, knobs = [], []
    for lb in opts["lookback"]:
        lb = int(lb)
        rolls, usable = {}, []
        for leg in legs:
            if lb >= 2 and len(leg["vals"]) >= lb + 1:
                rolls[leg["id"]] = mrbt.rolling_series(leg["vals"], lb)
                usable.append(leg)
        if not usable:
            continue
        for ez in opts["entryZ"]:
            for xz in opts["exitZ"]:
                for sz in opts["stopZ"]:
                    for md in MR_ENTRY_MODES_ALL:
                        daily = np.zeros(len(dates))
                        for leg in usable:
                            r = mrbt.simulate(
                                leg["dates"], leg["vals"], lookback=lb, entry_z=ez,
                                exit_z=xz, stop_z=sz, cost_bp=KN["costBp"],
                                notional=KN["notional"],
                                allow_dirs=tuple(leg["dirs"]["allowed"]),
                                carry=leg["carryKrw"], entry_mode=md, gate=leg["gate"],
                                time_stop=None, cost_bp_series=leg["costSeries"],
                                close_open_at_end=False,
                                tradable_dv=leg["tradable"], roll=rolls[leg["id"]])
                            for j, pt in enumerate(r["points"]):
                                daily[at[leg["dates"][j]]] += pt["dailyPnl"]
                        cols.append(daily)
                        knobs.append((lb, ez, xz, sz, md))
    return np.column_stack(cols), knobs


def _sharpe(sx, sxx, n):
    """조각 합에서 재조립한 샤프 — 조합마다 다시 훑지 않으려고."""
    m = sx / n
    var = sxx / n - m * m
    return np.where(var > 0, m / np.sqrt(np.maximum(var, 1e-300)), -np.inf)


def _sortino(sx, sdn, n):
    """하방편차 판 — 분모가 `sqrt(Σmin(x,0)²/n)` 라 이것도 조각 합에서 선다."""
    m = sx / n
    dd = np.sqrt(sdn / n)
    return np.where(dd > 0, m / np.maximum(dd, 1e-300), -np.inf)


def pbo(M: np.ndarray, S: int, metric: str = "sharpe",
        path_metric: bool = False) -> tuple[float, np.ndarray]:
    """CSCV — (PBO, 조합마다의 logit).

    조각을 **시간 순서 그대로** 자른다(섞지 않는다). 훈련은 절반 조각의 합집합,
    시험은 나머지다. 두 쪽이 같은 크기라 「대칭」이다.
    """
    T, N = M.shape
    cut = np.array_split(np.arange(T), S)
    if path_metric:
        chunks = [M[c] for c in cut]
    else:
        sx = np.array([M[c].sum(axis=0) for c in cut])
        sxx = np.array([(M[c] ** 2).sum(axis=0) for c in cut])
        sdn = np.array([(np.minimum(M[c], 0.0) ** 2).sum(axis=0) for c in cut])
        cnt = np.array([len(c) for c in cut], dtype=float)

    lam = []
    for tr in itertools.combinations(range(S), S // 2):
        te = tuple(i for i in range(S) if i not in tr)
        if path_metric:
            a = np.vstack([chunks[i] for i in tr])
            b = np.vstack([chunks[i] for i in te])
            ins, oos = _calmar(a), _calmar(b)
        else:
            ti = list(tr); si = list(te)
            ins = (_sharpe(sx[ti].sum(0), sxx[ti].sum(0), cnt[ti].sum())
                   if metric == "sharpe" else
                   _sortino(sx[ti].sum(0), sdn[ti].sum(0), cnt[ti].sum()))
            oos = (_sharpe(sx[si].sum(0), sxx[si].sum(0), cnt[si].sum())
                   if metric == "sharpe" else
                   _sortino(sx[si].sum(0), sdn[si].sum(0), cnt[si].sum()))
        best = int(np.argmax(ins))
        # 시험 절반에서 그 칸의 상대 순위(1 = 최고). 동점은 평균 순위로 두지 않고
        # 그대로 센다 — 동점이 많으면 그 자체가 「고를 것이 없다」는 사실이다.
        rank = float((oos < oos[best]).sum() + 1)
        w = rank / (N + 1)
        w = min(max(w, 1e-9), 1 - 1e-9)
        lam.append(math.log(w / (1 - w)))
    lam = np.array(lam)
    return float((lam < 0).mean()), lam


def _calmar(x: np.ndarray) -> np.ndarray:
    """열마다 연환산/최대낙폭 — 경로 의존이라 조합마다 다시 훑는다."""
    cum = np.cumsum(x, axis=0)
    peak = np.maximum.accumulate(cum, axis=0)
    mdd = (peak - cum).max(axis=0)
    ann = cum[-1] * 252.0 / x.shape[0]
    return np.where(mdd > 0, ann / np.maximum(mdd, 1e-300), -np.inf)


def main() -> int:
    print("격자를 만드는 중… (162칸 × 아홉 만기)")
    M, knobs = build_matrix()
    T, N = M.shape
    print(f"행렬 {T}봉 × {N}칸\n")

    print("=" * 62)
    print("① 본 결과 — 통합 장부 162칸")
    print("=" * 62)
    for S in (8, 10, 16):
        p_sh, _ = pbo(M, S, "sharpe")
        p_so, _ = pbo(M, S, "sortino")
        extra = ""
        if S == 10:
            p_ca, _ = pbo(M, S, path_metric=True)
            extra = f" · Calmar {p_ca:.3f}"
        print(f"  S={S:>2} ({math.comb(S, S//2):>6,}조합)  PBO  Sharpe {p_sh:.3f} · "
              f"Sortino {p_so:.3f}{extra}")

    print()
    print("=" * 62)
    print("② 비판 검정 — N 이 커지면 PBO 가 저절로 오르나")
    print("=" * 62)
    print("  「후보 수가 늘면 실제 예측력과 무관하게 PBO 가 1 로 간다」가 사실이면")
    print("  162칸의 PBO 는 격자가 아니라 격자 **크기**를 재는 수가 된다.")
    rng = np.random.default_rng(7)
    for n in (18, 54, 162):
        if n == N:
            sub = M
        else:
            sub = M[:, rng.choice(N, n, replace=False)]
        p, _ = pbo(sub, 10, "sharpe")
        print(f"  N={n:>3}  PBO {p:.3f}")

    print()
    print("=" * 62)
    print("③ 대조군 — 배관이 맞나")
    print("=" * 62)
    # 음성: 순수 잡음. 고를 것이 없으니 PBO 가 0.5 근처여야 한다.
    noise = rng.normal(0, 1, size=(T, N)) * float(np.std(M))
    p_neg, _ = pbo(noise, 10, "sharpe")
    print(f"  음성(순수 잡음)        PBO {p_neg:.3f}   ← 0.5 근처여야 한다")
    # 양성: 잡음 위에 **진짜로 나은 칸 하나**를 심는다. 그 칸이 늘 뽑히고
    # 시험에서도 1등이어야 하므로 PBO 가 0 에 가까워야 한다.
    good = noise.copy()
    good[:, 0] += 0.35 * float(np.std(M))
    p_pos, _ = pbo(good, 10, "sharpe")
    print(f"  양성(한 칸에 진짜 신호) PBO {p_pos:.3f}   ← 0 근처여야 한다")

    print()
    print("=" * 62)
    print("④ 참고 — 지금 노브가 전 표본에서 몇 등인가")
    print("=" * 62)
    cur = next((i for i, k in enumerate(knobs)
                if k == (KN["lookback"], KN["entryZ"], KN["exitZ"], KN["stopZ"],
                         KN["entryMode"])), None)
    full = _sharpe(M.sum(0), (M ** 2).sum(0), float(T))
    order = np.argsort(-full)
    if cur is not None:
        print(f"  지금 칸 {int(np.where(order == cur)[0][0]) + 1}등 / {N}  (전 표본 Sharpe 기준)")
    print(f"  전 표본 Sharpe 분포: 중앙 {np.median(full):.2f} · "
          f"최고 {full.max():.2f} · 최저 {full.min():.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
