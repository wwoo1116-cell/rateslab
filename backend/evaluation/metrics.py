# -*- coding: utf-8 -*-
"""세 지표의 산술 — DSR · PBO(CSCV) · 변동성 정규화 CDaR.

식은 전부 **인용 가능한 출처**를 갖는다(이 리포의 규율 8):

  DSR·MinTRL   Bailey & López de Prado (2014) "The Deflated Sharpe Ratio:
               Correcting for Selection Bias, Backtest Overfitting and
               Non-Normality", Journal of Portfolio Management 40(5).
  PBO(CSCV)    Bailey, Borwein, López de Prado & Zhu (2017) "The Probability of
               Backtest Overfitting", Journal of Computational Finance 20(4).
  Ulcer/CDaR   Chekhlov, Uryasev & Zabarankin (2005) "Drawdown Measure in
               Portfolio Optimization" — CDaR = 조건부 낙폭(최악 α 꼬리의 평균).

## 단위 규약 — **비율이다**

들어오는 `returns` 는 **주기별 수익률**(비율)이고 원(₩)이 아니다. 이 데스크에는
AUM 이 없어서 분모를 정해야 했고, 오너가 **액면(원금)** 으로 정했다
[OWNER 2026-09-09 — 「액면(원금) · 거래마다 진입일 커브」]. 그 환산은 이 층의
**바깥**(호출부)에서 끝난다 — 여기서 다시 나누면 자본 기준이 두 곳에 살게 된다.

## SR 은 **주기별**로 다룬다

DSR 의 식은 표본길이 T 와 주기별 SR 위에 서 있다. 연환산은 보고용이라 마지막에
한 번만 곱한다(`ANN[freq]`). 연환산 SR 을 식에 넣으면 T 와 단위가 어긋나 DSR 이
조용히 낙관적으로 나온다 — 이 함수들이 주기별을 고집하는 이유다.
"""
from __future__ import annotations

import math
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

#: 주기 → 연 관측수. 「D」는 영업일이다(이 리포의 다른 자리와 같은 252).
ANN: dict[str, int] = {"D": 252, "W": 52, "M": 12}

#: 오일러-마스케로니 상수 — SR0 의 가우시안 최대값 근사에 든다.
EULER = 0.5772156649015329

#: 게이트 문턱 — 오너 사양의 값 그대로.
DSR_PASS = 0.95
PBO_PASS = 0.20
#: 「폐기」 문턱. 이 위면 고른 칸이 동전던지기보다 못하다는 뜻이다.
PBO_DISCARD = 0.50
#: 순위 지표의 기준선(사양) — 게이트가 아니라 읽는 눈금이다.
CDAR_REFERENCE = 1.0


# ── ① Deflated Sharpe Ratio ────────────────────────────────────────────────


def _sr_stats(r: np.ndarray) -> tuple[float, float, float, int]:
    """(주기별 SR, 왜도, **초과**첨도, T). 표본이 둘 미만이면 SR 은 0 이다."""
    n = int(r.size)
    if n < 2:
        return 0.0, 0.0, 0.0, n
    sd = float(np.std(r, ddof=1))
    sr = float(np.mean(r) / sd) if sd > 0 else 0.0
    #: 왜도·첨도는 **표본 보정 없이**(g1·g2) 쓴다 — Bailey 의 식이 그 모멘트를 쓴다.
    sk = float(stats.skew(r, bias=True))
    ku = float(stats.kurtosis(r, bias=True))          # 초과첨도(정규 = 0)
    return sr, sk, ku, n


def expected_max_sr(trials: int, sr_var: float) -> float:
    """N 번 시도했을 때 **아무 실력이 없어도** 기대되는 최고 SR(주기별).

        SR0 = √V · [ (1−γ)·Z⁻¹(1 − 1/N) + γ·Z⁻¹(1 − 1/(N·e)) ]

    `V` 는 시행들의 SR **분산**이다. 격자를 실제로 돌렸으면 그 칸들의 SR 분산을
    넣는 것이 정확하고(그때 이 수가 «이 격자에서 뽑기로 나오는 최고» 가 된다),
    모르면 귀무가설의 점근분산 `1/T` 를 쓴다 — 호출부가 그 선택을 `assumptions`
    에 적는다.

    N ≤ 1 이면 **고른 것이 없다** → 0. 깎을 것이 없다는 뜻이지 좋다는 뜻이 아니다.
    """
    if trials <= 1 or sr_var <= 0:
        return 0.0
    a = stats.norm.ppf(1.0 - 1.0 / trials)
    b = stats.norm.ppf(1.0 - 1.0 / (trials * math.e))
    return float(math.sqrt(sr_var) * ((1.0 - EULER) * a + EULER * b))


def deflated_sharpe(returns: pd.Series, trials: int,
                    sr_var: float | None = None) -> dict[str, Any]:
    """DSR — 「이 SR 이 **시행수·왜도·첨도·표본길이**를 다 감안하고도 0 보다 큰가」.

        DSR = Φ( (SR − SR0)·√(T−1) / √(1 − γ3·SR + (γ4−1)/4·SR²) )

    γ3 는 왜도, γ4 는 **비초과** 첨도(정규 = 3)다. 분모가 그 둘을 지고 있어서
    **음의 왜도·두꺼운 꼬리를 벌한다** — 승률 높은 평균회귀가 자동으로 깎이고,
    그게 이 지표를 고른 이유다.
    """
    r = np.asarray(returns.dropna(), dtype=float)
    sr, sk, ex_ku, n = _sr_stats(r)
    var = (1.0 / n if n > 1 else 0.0) if sr_var is None else sr_var
    sr0 = expected_max_sr(trials, var)
    ku = ex_ku + 3.0
    denom = 1.0 - sk * sr + (ku - 1.0) / 4.0 * sr * sr
    if n < 2 or denom <= 0:
        return {"dsr": None, "sr": sr, "sr0": sr0, "skew": sk,
                "excess_kurtosis": ex_ku, "n_obs": n,
                "why": "표본이 둘 미만이거나 모멘트 보정항이 음수예요"}
    z = (sr - sr0) * math.sqrt(n - 1) / math.sqrt(denom)
    return {"dsr": float(stats.norm.cdf(z)), "sr": sr, "sr0": sr0, "skew": sk,
            "excess_kurtosis": ex_ku, "n_obs": n, "why": None}


def min_trl(returns: pd.Series, trials: int, sr_var: float | None = None,
            alpha: float = 0.95, freq: str = "D") -> float | None:
    """**최소 필요 관측 길이**(년) — 지금 SR 이 95% 로 유의해지려면 얼마나 길어야 하나.

        MinTRL = 1 + [1 − γ3·SR + (γ4−1)/4·SR²] · ( Z_α / (SR − SR0) )²

    `SR ≤ SR0` 이면 **아무리 길어도 안 된다** → `None`. 그것도 답이다.
    """
    r = np.asarray(returns.dropna(), dtype=float)
    sr, sk, ex_ku, n = _sr_stats(r)
    var = (1.0 / n if n > 1 else 0.0) if sr_var is None else sr_var
    sr0 = expected_max_sr(trials, var)
    if sr <= sr0:
        return None
    ku = ex_ku + 3.0
    adj = 1.0 - sk * sr + (ku - 1.0) / 4.0 * sr * sr
    periods = 1.0 + adj * (stats.norm.ppf(alpha) / (sr - sr0)) ** 2
    return float(periods / ANN.get(freq, 252))


# ── ② PBO via CSCV ─────────────────────────────────────────────────────────


def pbo_cscv(matrix: pd.DataFrame, splits: int = 16) -> dict[str, Any]:
    """과적합 확률 — 「표본내 1등이 표본밖에서 중앙값 아래로 가는 비율」.

    `matrix` 는 **T × 칸**이다(칸 = 파라미터 조합 하나의 수익 계열). 행을 S 개
    **연속 블록**으로 자르고, C(S, S/2) 가지의 훈련/시험 분할마다 훈련 1등을 뽑아
    그 칸이 시험에서 몇 등인지를 본다.

        ω = (시험 순위) / (칸 수 + 1)      λ = ln(ω / (1−ω))
        PBO = λ < 0 인 분할의 비율            (= 시험에서 중앙값 아래)

    같이 내는 둘:
      · `degradation` — 훈련 성적 대 시험 성적의 회귀 기울기. 1 에 가까우면 성적이
        따라가고, 0 이하면 훈련에서 좋을수록 시험에서 나쁘다.
      · `prob_oos_loss` — 훈련 1등의 시험 수익이 음수인 분할의 비율.

    성능 기준은 **SR**이다(사양의 「IS-optimal config」). 총손익으로 고르면 이
    리포가 이미 잰 그 함정 — 표본밖에서 무작위보다 나쁜 칸이 1등으로 올라온다.

    ⚠ S 는 **짝수**여야 하고 행이 S 보다 많아야 한다. 아니면 잴 수 없다고 말한다
    (0 을 내면 「과적합이 없다」는 없는 사실이 된다).
    """
    if matrix.shape[1] < 2:
        return {"pbo": None, "why": "칸이 둘은 있어야 순위가 선다",
                "degradation": None, "prob_oos_loss": None, "n_splits": 0}
    if splits % 2 or splits < 2 or matrix.shape[0] < splits:
        return {"pbo": None,
                "why": f"블록 {splits} 개로는 못 잘라요 — 짝수여야 하고 행({matrix.shape[0]})이 더 많아야 해요",
                "degradation": None, "prob_oos_loss": None, "n_splits": 0}

    m = matrix.to_numpy(dtype=float)
    blocks = np.array_split(np.arange(m.shape[0]), splits)
    n_cells = m.shape[1]
    lambdas: list[float] = []
    is_perf: list[float] = []
    oos_perf: list[float] = []
    losses = 0

    def _sr(x: np.ndarray) -> np.ndarray:
        sd = np.std(x, axis=0, ddof=1)
        mu = np.mean(x, axis=0)
        return np.where(sd > 0, mu / np.where(sd > 0, sd, 1.0), 0.0)

    for pick in combinations(range(splits), splits // 2):
        tr = np.concatenate([blocks[i] for i in pick])
        te = np.concatenate([blocks[i] for i in range(splits) if i not in pick])
        s_tr, s_te = _sr(m[tr]), _sr(m[te])
        best = int(np.argmax(s_tr))
        #: 순위는 **큰 것이 1등**이라 내림차순이다. 동점은 평균 순위(`average`).
        rank = float(stats.rankdata(s_te)[best])           # 1 = 최악
        omega = rank / (n_cells + 1.0)
        omega = min(max(omega, 1e-9), 1 - 1e-9)
        lambdas.append(math.log(omega / (1.0 - omega)))
        is_perf.append(float(s_tr[best]))
        oos_perf.append(float(s_te[best]))
        if float(np.sum(m[te][:, best])) < 0:
            losses += 1

    n = len(lambdas)
    slope = None
    if n >= 2 and np.std(is_perf) > 0:
        slope = float(np.polyfit(is_perf, oos_perf, 1)[0])
    return {
        "pbo": float(sum(1 for x in lambdas if x < 0) / n),
        "degradation": slope,
        "prob_oos_loss": float(losses / n),
        "n_splits": n,
        "why": None,
    }


# ── ③ 변동성 정규화 CDaR 비 ────────────────────────────────────────────────


def vol_normalize(returns: pd.Series, target_vol: float = 0.05,
                  freq: str = "D", min_obs: int = 60) -> tuple[pd.Series, str]:
    """**사전(ex-ante)** 변동성으로 목표 변동성에 맞춘 계열 + 추정기 이름.

    ⚠ **전표본 실현변동성 금지**(오너 규율) — 그건 룩어헤드다. 여기는 **확장창**이고
    그 창은 «어제까지» 다(`shift(1)`): 오늘의 크기 조절에 오늘의 변동성을 쓰면
    오늘을 알고 어제 걸었다는 뜻이 된다.

    관측이 `min_obs` 에 못 미치는 앞머리는 **NaN 으로 버린다**(지표들이 `dropna`
    한다). 배수 1 로 두는 길도 있었고 처음에 그렇게 썼는데, 그건 **스케일 불변을
    깬다**: 원(₩) 계열을 넣으면 뒤쪽 배수가 5e-8 인데 앞 60봉만 배수 1 로 남아
    그 구간이 계열을 통째로 지배한다(실측 2026-09-09 — 같은 칸이 비율 계열에서
    CDaR 비 **+7.27**, 원 계열에서 **−0.15** 로 부호까지 갈렸다). 초기 몇 봉의
    표준편차로 스무 배를 걸지 않으려던 원래 뜻은 그대로이고, 그 구간을 «안 건드림»
    이 아니라 «못 잼» 으로 적는 것이 맞다.

    그래서 이 함수는 **스케일 불변**이다 — `r → c·r` 이면 `vol → c·vol` 이라
    배수가 `1/c` 배가 되어 결과가 같다. 그 성질 위에서 CDaR 비가 자본 기준 없이
    서고(`docs/EVAL_LANE_STATE.md` §7-4), `tests/test_evaluation.py` 가 그것을 잰다.
    """
    ann = ANN.get(freq, 252)
    r = returns.astype(float)
    vol = r.expanding(min_periods=min_obs).std(ddof=1).shift(1) * math.sqrt(ann)
    scale = (target_vol / vol).where(vol > 0)
    return r * scale, f"확장창(min {min_obs}, shift 1) · 목표 {target_vol:.1%}"


def _drawdowns(returns: pd.Series) -> np.ndarray:
    """전고점 대비 낙폭(비율, 비음수). **누적은 덧셈**이다.

    수익률이 작고(일 0.0x%) 이 층의 입력이 이미 «액면 대비» 라, 복리로 굴리면
    자본이 스스로 커지는 판을 가정하게 된다 — 이 데스크는 액면을 고정해 두고
    돌린다. 그래서 덧셈 누적 위의 낙폭이다(엔진·화면의 누적 곡선과도 같은 규약).
    """
    eq = np.cumsum(np.asarray(returns.dropna(), dtype=float))
    peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    return np.maximum(peak - eq, 0.0)


def cdar_ratio(returns: pd.Series, alpha: float = 0.05,
               freq: str = "D") -> dict[str, Any]:
    """CDaR 과 그 비율 — **최악 α 꼬리 낙폭의 평균**으로 연환산 수익을 나눈다.

    MaxDD 를 안 쓰는 이유는 그것이 **단일관측 추정량**이어서다(Phase 0 D5: 이
    표본에서 MaxDD 의 50% 를 넘는 낙폭 사건이 셋뿐이고 1등은 코로나 창이다).
    CDaR 은 꼬리 **여럿**의 평균이라 같은 MaxDD 에서도 사건이 많을수록 나빠진다.
    """
    r = returns.dropna().astype(float)
    if r.empty:
        return {"cdar": None, "cdar_ratio": None, "ann_return": None,
                "why": "봉이 없어요"}
    dd = _drawdowns(r)
    k = max(1, int(math.ceil(len(dd) * alpha)))
    worst = np.sort(dd)[-k:]
    cdar = float(np.mean(worst))
    ann = float(np.mean(r) * ANN.get(freq, 252))
    return {
        "cdar": cdar,
        "ann_return": ann,
        "cdar_ratio": (ann / cdar) if cdar > 0 else None,
        "why": None if cdar > 0 else "낙폭이 없어 비율이 안 서요",
    }


# ── 동반 진단 — 내되 **순위에 안 쓴다** ────────────────────────────────────


def diagnostics(returns: pd.Series, freq: str = "D") -> dict[str, Any]:
    """왜도·첨도·꼬리비·최장 낙폭·승률·평균이익/손실.

    이 셋(게이트 둘 + 순위 하나)과 **뚜렷이 갈라** 둔다. MR 과 모멘텀의 DSR 이
    비슷하게 나올 때 서로 다른 **실패 방식**이 보이라고 두는 값들이다.
    """
    r = returns.dropna().astype(float)
    x = np.asarray(r, dtype=float)
    if x.size == 0:
        return {}
    wins, losses = x[x > 0], x[x < 0]
    dd = _drawdowns(r)
    #: 물속 구간의 최장 길이 — 낙폭의 «깊이» 가 아니라 «길이» 다.
    longest, cur = 0, 0
    for d in dd:
        cur = cur + 1 if d > 0 else 0
        longest = max(longest, cur)
    q95, q05 = float(np.quantile(x, 0.95)), float(np.quantile(x, 0.05))
    return {
        "skew": float(stats.skew(x, bias=True)),
        "excess_kurtosis": float(stats.kurtosis(x, bias=True)),
        "tail_ratio": (abs(q95) / abs(q05)) if q05 != 0 else None,
        "longest_drawdown_days": int(longest),
        "win_rate": float(wins.size / x.size),
        "avg_win": float(np.mean(wins)) if wins.size else None,
        "avg_loss": float(np.mean(losses)) if losses.size else None,
        "ann_vol": float(np.std(x, ddof=1) * math.sqrt(ANN.get(freq, 252))),
        "ar1": float(pd.Series(x).autocorr(lag=1)) if x.size > 2 else None,
    }


# ── 진입점 ─────────────────────────────────────────────────────────────────


def evaluate(returns: pd.Series,
             trials: int,
             is_oos_splits: int = 16,
             target_vol: float = 0.05,
             freq: str = "D",
             *,
             configs: pd.DataFrame | None = None,
             sr_var: float | None = None,
             strategy_id: str = "unknown",
             cost_bp_roundtrip: float | None = None,
             assumptions: list[str] | None = None) -> dict[str, Any]:
    """게이트 둘 + 순위 하나 + 동반 진단. 계약은 `HANDOFF` §9 그대로다.

    `returns` 는 **비용 차감 후 비율** 계열이다(자본 기준은 호출부가 정한다 —
    이 레인에서는 액면).

    `configs` 는 PBO 가 먹는 **T × 칸** 행렬이다. 없으면 PBO 를 못 재고, 그때는
    **게이트를 통과시키지 않는다** — 사양의 「탐색이 없었으면 꼬리비로 갈아 끼운다」
    는 *탐색을 안 한 전략*의 규칙이고, 이 레인은 탐색을 했다(격자가 화면 기능이다).
    못 잰 것을 통과로 두면 그 순간 이 층이 하는 일이 없어진다.

    `cost_bp_roundtrip` 은 **계산에 안 쓴다** — 수익 계열이 이미 비용 차감 후다.
    그래도 입력에 실려 나가는 이유는 오너 규율이다: 전략마다 다른 비용 가정을
    쓰지 않으려면 무엇을 가정한 수인지가 보고서에 **적혀** 있어야 한다.
    """
    notes = list(assumptions or [])
    r = returns.dropna().astype(float)
    ann = ANN.get(freq, 252)

    if sr_var is None:
        notes.append(
            "SR0 의 시행 분산 V 를 귀무가설 점근값 1/T 로 뒀어요 — 격자 칸들의 "
            "SR 분산을 넘기면 그 격자에서의 «뽑기 최고» 가 더 정확해져요.")

    d = deflated_sharpe(r, trials, sr_var)
    trl = min_trl(r, trials, sr_var, freq=freq)
    actual_years = len(r) / ann
    dsr_pass = bool(d["dsr"] is not None and d["dsr"] > DSR_PASS)

    if configs is None:
        p = {"pbo": None, "degradation": None, "prob_oos_loss": None,
             "n_splits": 0,
             "why": "칸 행렬을 안 받았어요 — 이 레인은 탐색을 했으므로 CSCV 가 "
                    "필요해요(꼬리비 대체는 탐색이 없는 전략의 규칙이에요)"}
    else:
        p = pbo_cscv(configs, is_oos_splits)
    pbo_pass = bool(p["pbo"] is not None and p["pbo"] < PBO_PASS)

    scaled, vol_estimator = vol_normalize(r, target_vol, freq)
    c = cdar_ratio(scaled, freq=freq)

    overall = dsr_pass and pbo_pass
    reason = None
    if not overall:
        bad = []
        if not dsr_pass:
            bad.append(f"DSR {d['dsr']:.4f} ≤ {DSR_PASS}" if d["dsr"] is not None
                       else f"DSR 을 못 쟀어요({d['why']})")
        if not pbo_pass:
            bad.append(f"PBO {p['pbo']:.4f} ≥ {PBO_PASS}" if p["pbo"] is not None
                       else f"PBO 를 못 쟀어요({p['why']})")
        reason = " · ".join(bad)
    if p["pbo"] is not None and p["pbo"] >= PBO_DISCARD:
        notes.append(f"PBO {p['pbo']:.2f} ≥ {PBO_DISCARD} — 사양은 이 전략을 폐기하라고 해요.")

    return {
        "strategy_id": strategy_id,
        "gate": {
            "dsr": d["dsr"], "dsr_pass": dsr_pass,
            "min_trl_years": trl, "actual_years": actual_years,
            "pbo": p["pbo"], "pbo_pass": pbo_pass,
            "overall_pass": overall,
        },
        "ranking": {
            # **게이트를 통과한 전략만 순위가 매겨진다** — 떨어졌으면 비율을
            # 아예 안 낸다(사양). 낙폭 자체는 서술이라 같이 낸다.
            "cdar_ratio": c["cdar_ratio"] if overall else None,
            "cdar": c["cdar"],
            "ann_return_normalized": c["ann_return"],
            "reason_if_null": None if overall else reason,
            "reference": CDAR_REFERENCE,
        },
        "diagnostics": {**diagnostics(r, freq),
                        "sr_period": d["sr"], "sr_annualized": d["sr"] * math.sqrt(ann),
                        "sr0_period": d["sr0"],
                        "pbo_degradation": p["degradation"],
                        "pbo_prob_oos_loss": p["prob_oos_loss"],
                        "pbo_splits": p["n_splits"]},
        "inputs": {
            "trials": trials, "cost_bp": cost_bp_roundtrip,
            "target_vol": target_vol, "vol_estimator": vol_estimator,
            "n_obs": int(len(r)), "ar1": diagnostics(r, freq).get("ar1"),
            "is_oos_splits": is_oos_splits, "freq": freq,
        },
        "assumptions": notes,
    }
