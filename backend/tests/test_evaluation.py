# -*- coding: utf-8 -*-
"""평가층 — 사양이 요구한 다섯 시험 + 계약·게이트 논리.

원 지시의 다섯(`HANDOFF-eval-framework-2026-09-09.md` §10):
  · DSR: IID 정규 · 알려진 SR · N=1 → 고전적 SR t-검정 p값을 근사 복원.
  · DSR: 수익 고정하고 `trials` 를 늘리면 **단조 감소**.
  · PBO: 일부러 과적합시킨 합성(순수 잡음 200칸) → **0.5 에 근접**.
  · CDaR: 큰 낙폭 하나 대 같은 MaxDD 의 중간 낙폭 다섯 → **다섯 쪽이 더 나쁜(큰) CDaR**.
  · 변동성 정규화: 실현 변동성이 `target_vol` 허용오차 안.

그 위에 이 층이 지는 규율 셋을 더 잰다 — 게이트는 AND 이고, 못 잰 게이트는
**통과가 아니며**, 떨어지면 순위값을 안 낸다.
"""
import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from evaluation import metrics as ev


def _iid(sr_ann: float, n: int = 1260, seed: int = 7) -> pd.Series:
    """연 SR 이 **정확히** `sr_ann` 인 IID 정규 계열(일별).

    ⚠ 그냥 `normal(mu, sd)` 로 뽑으면 **시드 운**이 그대로 실현 SR 이 된다 —
    T=1260 에서 연 SR 의 표준오차가 0.45 라, 목표 1.2 를 뽑아도 시드에 따라
    0.08~1.8 이 나온다(실측). 그러면 시험이 「식이 맞는가」가 아니라 「그 시드가
    운이 좋았는가」를 재게 된다. 표준화한 뒤 목표를 얹어 그 자유도를 없앤다.
    """
    rng = np.random.default_rng(seed)
    x = rng.normal(0.0, 1.0, n)
    x = (x - x.mean()) / x.std(ddof=1)
    return pd.Series((x + sr_ann / math.sqrt(252)) * 0.01)


# ── ① DSR: N=1 이면 고전적 t-검정에 가깝다 ─────────────────────────────────

def test_dsr_with_one_trial_recovers_the_classic_t_test():
    """시행이 하나면 깎을 것이 없다(SR0 = 0) — 그때 DSR 은 「SR > 0」의 p값이다.

    IID 정규라 왜도·첨도 보정항이 거의 1 이고, 남는 것은 `Φ(SR·√(T−1))` 이다.
    이 시험이 실패하면 식의 어느 항이 자리를 잘못 잡은 것이다.
    """
    r = _iid(1.0)
    got = ev.deflated_sharpe(r, trials=1)
    n = len(r)
    t = float(np.mean(r) / (np.std(r, ddof=1) / math.sqrt(n)))
    p_one_sided = 1.0 - stats.t.sf(t, df=n - 1)        # = P(SR > 0)
    assert got["sr0"] == 0.0
    assert got["dsr"] == pytest.approx(p_one_sided, abs=0.01)


def test_dsr_decreases_monotonically_in_trials():
    """**수익은 그대로 두고 시행수만 늘린다** — 깎이는 폭이 커지므로 단조 감소다.

    이 성질이 이 지표를 고른 이유의 절반이다(나머지 절반은 왜도·첨도 보정).
    """
    r = _iid(1.2)
    got = [ev.deflated_sharpe(r, trials=n)["dsr"] for n in (1, 3, 9, 27, 162, 1000)]
    assert all(a > b for a, b in zip(got, got[1:])), got
    assert got[0] > 0.9 and got[-1] < got[0]


def test_dsr_punishes_negative_skew_and_fat_tails():
    """같은 SR 이라도 **왼쪽 꼬리가 두꺼우면 깎인다** — MR 과 추세를 견주게 하는 그 항.

    사양이 DSR 을 고른 근거가 이것이라, 식에서 그 항이 살아 있는지 직접 잰다.
    """
    rng = np.random.default_rng(11)
    n = 1260
    clean = rng.normal(0.0004, 0.01, n)
    # 같은 평균·표준편차인데 왼쪽 꼬리만 두꺼운 계열(작은 이익 다수 · 가끔 큰 손실)
    skewed = rng.normal(0.0009, 0.006, n)
    hits = rng.choice(n, size=25, replace=False)
    skewed[hits] -= 0.045
    skewed = (skewed - skewed.mean()) / skewed.std() * clean.std() + clean.mean()
    a = ev.deflated_sharpe(pd.Series(clean), trials=9)
    b = ev.deflated_sharpe(pd.Series(skewed), trials=9)
    assert b["skew"] < a["skew"] - 0.5
    assert b["dsr"] < a["dsr"], (a["dsr"], b["dsr"])


def test_min_trl_is_none_when_the_sr_cannot_clear_the_bar():
    """`SR ≤ SR0` 이면 **아무리 길어도 안 된다** — 큰 수가 아니라 `None` 이다."""
    r = _iid(0.1)
    assert ev.min_trl(r, trials=10_000) is None
    assert ev.min_trl(_iid(2.0), trials=1) is not None


# ── ② PBO: 순수 잡음이면 0.5 로 간다 ───────────────────────────────────────

def test_pbo_on_pure_noise_approaches_one_half():
    """칸이 전부 잡음이면 훈련 1등은 시험에서 **동전던지기**다.

    사양의 그 시험이고, 이 값이 0 에 붙으면 CSCV 가 순위를 안 섞고 있다는 뜻이다.
    """
    rng = np.random.default_rng(3)
    m = pd.DataFrame(rng.normal(0, 0.01, (520, 200)))
    got = ev.pbo_cscv(m, splits=8)
    assert got["pbo"] == pytest.approx(0.5, abs=0.15), got["pbo"]
    assert got["n_splits"] == 70                      # C(8,4)


def test_pbo_is_low_when_one_cell_is_genuinely_better():
    """진짜 우위가 있으면 훈련 1등이 시험에서도 위쪽이다 — PBO 가 낮아야 한다."""
    rng = np.random.default_rng(5)
    m = rng.normal(0, 0.01, (520, 20))
    m[:, 0] += 0.0025                                  # 한 칸만 실력이 있다
    got = ev.pbo_cscv(pd.DataFrame(m), splits=8)
    assert got["pbo"] < 0.2, got["pbo"]
    assert got["degradation"] is not None


def test_pbo_says_it_cannot_measure_instead_of_returning_zero():
    """못 재는 판에서 0 을 내면 「과적합이 없다」는 **없는 사실**이 된다."""
    m = pd.DataFrame(np.zeros((10, 5)))
    got = ev.pbo_cscv(m, splits=16)
    assert got["pbo"] is None and got["why"]


# ── ③ CDaR: 같은 MaxDD 라도 사건이 여럿이면 더 나쁘다 ──────────────────────

def test_cdar_is_worse_when_the_same_maxdd_happens_five_times():
    """큰 낙폭 **하나** 대 같은 크기의 낙폭 **다섯** — 다섯 쪽 CDaR 이 크다(나쁘다).

    MaxDD 는 둘을 구분하지 못한다. 그것이 Calmar 를 대신하는 이유다.
    """
    def series(n_events: int) -> pd.Series:
        r = [0.001] * 60
        for _ in range(n_events):
            r += [-0.02] * 5 + [0.004] * 30           # 낙폭 하나 + 회복
        return pd.Series(r + [0.001] * 60)

    one, five = series(1), series(5)
    dd1, dd5 = ev._drawdowns(one), ev._drawdowns(five)
    assert dd1.max() == pytest.approx(dd5.max(), rel=1e-9)      # 같은 MaxDD
    c1 = ev.cdar_ratio(one)["cdar"]
    c5 = ev.cdar_ratio(five)["cdar"]
    assert c5 > c1, (c1, c5)


def test_cdar_ratio_is_none_without_a_drawdown():
    up = pd.Series([0.001] * 300)
    got = ev.cdar_ratio(up)
    assert got["cdar_ratio"] is None and got["why"]


# ── ④ 변동성 정규화: 목표에 맞고, 미래를 안 본다 ───────────────────────────

def test_vol_normalization_hits_the_target():
    rng = np.random.default_rng(9)
    r = pd.Series(rng.normal(0.0002, 0.02, 1500))      # 연 32% 짜리
    scaled, name = ev.vol_normalize(r, target_vol=0.05)
    realized = float(scaled.iloc[300:].std(ddof=1) * math.sqrt(252))
    assert realized == pytest.approx(0.05, rel=0.25), realized
    assert "확장창" in name and "shift 1" in name


def test_vol_normalization_never_looks_ahead():
    """**오늘의 크기 조절에 오늘의 변동성을 쓰지 않는다.**

    마지막 봉만 폭발시킨 계열을 만든다 — 룩어헤드가 있으면 그 봉의 배수가 작아져
    스케일된 값이 원래보다 작아진다. 확장창 + `shift(1)` 이면 그 봉은 **어제까지의**
    변동성으로 걸리므로 그대로 커진다.
    """
    rng = np.random.default_rng(17)
    #: ⚠ **상수 계열은 못 쓴다** — 변동성이 0 이면 목표로 키울 배수가 없어 전부
    #: NaN 이다(그게 맞는 처리다). 잔잔한 잡음 위에 마지막 봉만 폭발시킨다.
    r = pd.Series(list(rng.normal(0.0, 0.001, 400)) + [0.25])
    scaled, _ = ev.vol_normalize(r, target_vol=0.05)
    assert abs(scaled.iloc[-1]) > abs(scaled.iloc[-2]) * 50


# ── ⑤ 게이트 논리와 출력 계약 ──────────────────────────────────────────────

def _matrix(seed: int = 4, better: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    m = rng.normal(0, 0.01, (520, 20))
    if better:
        m[:, 0] += 0.0025
    return pd.DataFrame(m)


def test_contract_shape_is_the_agreed_one():
    out = ev.evaluate(_iid(1.5), trials=9, configs=_matrix(), is_oos_splits=8,
                      strategy_id="BSS-10Y", cost_bp_roundtrip=1.0)
    assert set(out) == {"strategy_id", "gate", "ranking", "diagnostics",
                        "inputs", "assumptions"}
    assert set(out["gate"]) == {"dsr", "dsr_pass", "min_trl_years",
                                "actual_years", "pbo", "pbo_pass", "overall_pass"}
    assert set(out["ranking"]) == {"cdar_ratio", "cdar", "ann_return_normalized",
                                   "reason_if_null", "reference"}
    #: 비용 가정은 **계산에 안 쓰지만 적혀 나간다** — 전략마다 다른 가정을 쓰지
    #: 않으려면 무엇을 가정했는지가 보고서에 있어야 한다(오너 규율).
    assert out["inputs"]["cost_bp"] == 1.0
    assert out["inputs"]["vol_estimator"].startswith("확장창")


def test_gate_is_an_and_and_ranking_is_withheld_when_it_fails():
    """게이트가 떨어지면 **순위값을 안 낸다** — 사유가 대신 선다."""
    out = ev.evaluate(_iid(0.2, seed=13), trials=162, configs=_matrix(better=False),
                      is_oos_splits=8)
    assert out["gate"]["dsr_pass"] is False
    assert out["gate"]["overall_pass"] is False
    assert out["ranking"]["cdar_ratio"] is None
    assert out["ranking"]["reason_if_null"]
    #: 낙폭 자체는 **서술**이라 게이트와 무관하게 낸다.
    assert out["ranking"]["cdar"] is not None


def test_missing_config_matrix_does_not_pass_the_gate():
    """PBO 를 **못 잰 것**은 통과가 아니다 — 사양의 꼬리비 대체는 «탐색이 없는»
    전략의 규칙이고, 이 레인은 탐색을 했다(격자가 화면 기능이다)."""
    out = ev.evaluate(_iid(3.0), trials=1)             # DSR 은 확실히 통과할 계열
    assert out["gate"]["dsr_pass"] is True
    assert out["gate"]["pbo"] is None
    assert out["gate"]["overall_pass"] is False
    assert "CSCV" in out["ranking"]["reason_if_null"]


def test_profit_factor_and_omega_are_not_in_the_layer():
    """[OWNER] **아예 안 낸다** — 둘 다 승률의 준-단조변환이라 MR 을 편든다."""
    out = ev.evaluate(_iid(1.0), trials=9, configs=_matrix(), is_oos_splits=8)
    blob = repr(out).lower()
    assert "profit_factor" not in blob and "profitfactor" not in blob
    assert "omega" not in blob


def test_vol_normalization_is_scale_invariant():
    """**원(₩)으로 넣든 비율로 넣든 같은 수가 나온다.**

    ⚠ 이 시험은 실측으로 잡은 결함 위에 서 있다(2026-09-09). 워밍업 구간을
    `fillna(1.0)`(배수 1)으로 두었더니 스케일 불변이 깨졌다 — 원 계열에서는 뒤쪽
    배수가 5e-8 인데 앞 60봉만 배수 1 로 남아 그 구간이 계열을 통째로 지배했고,
    같은 칸의 CDaR 비가 비율 계열 **+7.27** 대 원 계열 **−0.15** 로 **부호까지**
    갈렸다. 지금은 워밍업을 NaN 으로 버린다.

    이 성질이 필요한 이유: 화면의 자동 채택 기준이 이 비율이고(격자는 원 손익을
    넣는다) 평가층은 비율 계열을 넣는다. 둘이 같은 자여야 화면이 고른 칸을
    평가층이 다시 재도 같은 답이 나온다.
    """
    rng = np.random.default_rng(21)
    base = pd.Series(rng.normal(0.0003, 0.01, 900))
    got = []
    for c in (1.0, 1e6, 1e-3):
        scaled, _ = ev.vol_normalize(base * c)
        got.append(ev.cdar_ratio(scaled)["cdar_ratio"])
    assert got[0] == pytest.approx(got[1], rel=1e-9)
    assert got[0] == pytest.approx(got[2], rel=1e-9)


def test_vol_normalization_drops_the_warmup_instead_of_leaving_it_raw():
    """워밍업은 **못 잰 구간**이지 «안 건드린 구간» 이 아니다 — NaN 으로 나간다."""
    rng = np.random.default_rng(23)
    r = pd.Series(rng.normal(0.0005, 0.01, 100))
    scaled, _ = ev.vol_normalize(r, min_obs=60)
    assert scaled.iloc[:60].isna().all()
    assert scaled.iloc[60:].notna().all()
    #: 변동성이 **0 인 구간**도 NaN 이다 — 0 에서 목표로 키울 배수가 없다.
    flat, _ = ev.vol_normalize(pd.Series([0.001] * 100), min_obs=60)
    assert flat.isna().all()
