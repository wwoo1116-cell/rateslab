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
    # `failure_shape` 는 2026-09-09 에 **더한** 칸이다 [OWNER — 「실패 유형만
    # 적는다」]. 게이트·순위·문턱은 한 글자도 안 바뀌었고, 「미통과」 한 낱말이
    # 서로 다른 세 사정을 같은 말로 만들던 것을 갈라 적기만 한다.
    assert set(out) == {"strategy_id", "failure_shape", "gate", "ranking",
                        "diagnostics", "inputs", "assumptions"}
    assert set(out["gate"]) == {"dsr", "dsr_pass", "min_trl_years",
                                "actual_years", "pbo", "pbo_pass", "overall_pass"}
    # 순위 블록에 **자기 근거의 두께**가 더해졌다(2026-09-09) — 그 비율이 몇 개의
    # 낙폭 «사건» 위에 서 있는지. Calmar → CDaR 로 옮긴 이유가 「MaxDD 는 단일관측」
    # 이었으므로, CDaR 이 실제로 사건 둘 위에 서 있으면 그것도 적혀야 한다.
    assert set(out["ranking"]) == {"cdar_ratio", "cdar", "ann_return_normalized",
                                   "tail_episodes", "total_episodes",
                                   "tail_points", "reason_if_null", "reference"}
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


# ── 보고서의 수 적기 ─────────────────────────────────────────────────────

def test_report_number_drops_meaningless_decimals_on_large_values():
    """이 층은 **비율 계열도 원(₩) 계열도** 먹는다 — 자릿수가 그 사정을 따라야 한다.

    모멘텀 레인은 자본 분모를 안 만들기로 해서(그 레인의 결정 1) 원 손익이 그대로
    들어온다. 넷째 자리를 고정해 두면 「532,493.628808」 같은 줄이 나오는데, 원
    단위에서 소수점 아래 여섯 자리는 **뜻이 없는 자리**다.
    """
    from evaluation.report import _num

    assert _num(532493.628808) == "532,494"
    assert _num(-478099.649493) == "-478,100"
    # 비율 자리는 그대로 — 게이트가 읽는 수는 넷째 자리가 뜻을 가진다.
    assert _num(0.9381) == "0.9381"
    assert _num(1.6834) == "1.6834"
    # 없는 값은 «—» 다(0 이 아니다).
    assert _num(None) == "—"


# ── 자기상관 보정 Sharpe ─────────────────────────────────────────────────

def test_sharpe_lo_reduces_to_root_q_when_days_are_independent():
    """ρ = 0 이면 Lo 보정이 **√252 곱셈으로 되돌아온다** — 식이 맞다는 증거."""
    import numpy as np
    from evaluation.metrics import sharpe_lo

    rng = np.random.default_rng(20260909)
    r = pd.Series(rng.normal(0.0004, 0.01, 4000))
    plain = float(r.mean() / r.std(ddof=0) * math.sqrt(252))
    got = sharpe_lo(r)
    assert got is not None
    # iid 표본이라 ρ 가 정확히 0 은 아니다 — 5% 안이면 같은 수로 본다.
    assert abs(got - plain) < abs(plain) * 0.05


def test_sharpe_lo_deflates_positively_autocorrelated_series():
    """**양의 자기상관은 √252 곱셈을 부풀린다** — 그래서 보정하면 내려간다.

    MR 이 그 자리다(AR(1) +0.21 — 무포지션인 날이 절반이라 0 이 뭉치고 캐리가
    매일 같은 방향으로 쌓인다). 한쪽만 부푼 자를 그대로 쓰면 같은 기준이 아니다.
    """
    import numpy as np
    from evaluation.metrics import sharpe_lo

    rng = np.random.default_rng(11)
    e = rng.normal(0, 0.01, 4000)
    x = np.zeros(4000)
    for i in range(1, 4000):
        x[i] = 0.4 * x[i - 1] + e[i]
    r = pd.Series(x + 0.0004)
    plain = float(r.mean() / r.std(ddof=0) * math.sqrt(252))
    got = sharpe_lo(r)
    assert got is not None and 0 < got < plain, f"{got} 가 {plain} 보다 작아야 해요"


def test_sharpe_lo_is_scale_invariant():
    """배율을 곱해도 안 변한다 — 원(₩) 계열과 비율 계열을 나란히 놓는 자리라서."""
    import numpy as np
    from evaluation.metrics import sharpe_lo

    rng = np.random.default_rng(7)
    r = pd.Series(rng.normal(0.0003, 0.008, 2000))
    base = sharpe_lo(r)
    for c in (1e-6, 1e6):
        assert math.isclose(sharpe_lo(r * c), base, rel_tol=1e-9)


# ── 실패 «유형» — 판정은 안 바꾸고 사정만 적는다 [OWNER 2026-09-09] ────────

def _cells(sr_list, n=800, rho=0.95, seed=3):
    """칸 행렬 하나 — 공통 인자 `rho` 로 칸끼리 닮은 정도를 조절한다."""
    import numpy as np

    rng = np.random.default_rng(seed)
    common = rng.normal(0, 0.01, n)
    cols = {}
    for j, target in enumerate(sr_list):
        own = rng.normal(0, 0.01, n)
        x = rho * common + math.sqrt(max(0.0, 1 - rho ** 2)) * own
        x = (x - x.mean()) / x.std(ddof=1)
        cols[f"c{j}"] = x * 0.01 + target / math.sqrt(252) * 0.01
    return pd.DataFrame(cols)


def test_failure_shape_is_empty_when_the_gate_passes():
    """통과했으면 «어떻게 떨어졌나» 가 없다 — 없는 사정을 지어내지 않는다."""
    from evaluation.metrics import failure_shape

    got = failure_shape(dsr_pass=True, pbo_pass=True, min_trl_years=1.0,
                        actual_years=5.0, configs=None)
    assert got["shapes"] == [] and got["note"] is None


def test_failure_shape_reads_homogeneous_cells_as_cannot_pick():
    """**칸이 닮았고 제일 나쁜 칸도 좋으면** 「못 고른다」다 — 과적합이 아니다.

    증거금 상한판이 그 자리였다(칸 상관 0.90 · 칸별 SR 1.07~1.32). 어느 칸을
    골랐어도 됐다는 뜻이라 못 고르는 것이 안 아프다.
    """
    from evaluation.metrics import failure_shape

    m = _cells([1.1, 1.2, 1.3, 1.15, 1.25, 1.05], rho=0.97)
    got = failure_shape(dsr_pass=True, pbo_pass=False, min_trl_years=None,
                        actual_years=6.0, configs=m)
    assert got["shapes"] == ["칸이 닮아 못 고른다"]
    assert got["cells_median_corr"] > 0.8
    assert got["cells_sr_min"] > 0


def test_failure_shape_reads_diverging_cells_as_a_real_signal():
    """**칸이 갈리는데** 표본밖에서 뒤집히면 그건 딴 이야기다(BSS-6M 이 그 자리)."""
    from evaluation.metrics import failure_shape

    m = _cells([0.1, 0.4, -0.3, 0.2, -0.1, 0.35], rho=0.2)
    got = failure_shape(dsr_pass=True, pbo_pass=False, min_trl_years=None,
                        actual_years=6.0, configs=m)
    assert got["shapes"] == ["칸이 갈리는데 표본밖에서 뒤집힌다"]


def test_failure_shape_grades_the_sample_gap_by_multiple():
    """필요 표본이 실제의 **몇 배**인가로 나눈다 — 1.3년과 1,043년은 다른 말이다."""
    from evaluation.metrics import failure_shape

    def shape(trl, actual):
        return failure_shape(dsr_pass=False, pbo_pass=True, min_trl_years=trl,
                             actual_years=actual, configs=None)["shapes"]

    assert shape(10.74, 9.40) == ["표본이 곧 닿는다"]        # 모멘텀 50/50
    assert shape(15.03, 9.40) == ["표본이 한참 모자라다"]     # 모멘텀 추세
    assert shape(1049.0, 6.54) == ["이 SR 로는 못 닿는다"]    # BSS-6M
    # SR ≤ SR0 이면 MinTRL 이 아예 없다 — 그것도 사정이다.
    assert shape(None, 6.54) == ["DSR 을 못 쟀다"]


def test_failure_shape_never_touches_the_verdict():
    """이 함수는 **아무것도 통과시키지 않는다** — 사양은 그대로다.

    오너 결정이 「실패 유형만 적는다」였고, 딱지가 게이트를 건드리는 순간 그
    결정을 어긴 것이 된다. `evaluate` 의 판정이 딱지와 무관함을 여기서 잰다.
    """
    import numpy as np
    from evaluation.metrics import evaluate

    rng = np.random.default_rng(5)
    r = pd.Series(rng.normal(0.0002, 0.01, 900))
    m = _cells([1.1, 1.2, 1.3], rho=0.99)
    out = evaluate(r, trials=50, configs=m, is_oos_splits=8)
    assert "failure_shape" in out
    assert out["gate"]["overall_pass"] == (out["gate"]["dsr_pass"]
                                           and out["gate"]["pbo_pass"])


# ── 낙폭 «사건» 수 — 이 층의 자기 감사 ────────────────────────────────────

def _path(segments):
    """구간마다 (봉수, 일별수익)을 주면 계열을 만든다 — 낙폭 사건을 손으로 짓는다."""
    out = []
    for n, v in segments:
        out += [v] * n
    return pd.Series(out, dtype=float)


def test_tail_from_one_episode_is_not_a_sample_of_many():
    """**꼬리 점의 수는 표본이 아니다.**

    깊은 낙폭 하나 + 얕은 것 하나를 지어 놓으면, 최악 5% 꼬리는 깊은 **한 사건**
    에서만 나온다. 그 사실이 안 적히면 CDaR 이 MaxDD 와 뭐가 다른지 말할 수 없다
    (Calmar → CDaR 로 옮긴 이유가 「MaxDD 는 단일관측」이었다).
    """
    from evaluation.metrics import drawdown_episodes

    #: ⚠ 회복은 **전고점을 넘겨야** 사건이 끝난다. 처음 판은 회복 폭이 모자라
    #: 계열이 끝까지 물속이었고, 그래서 「사건 하나」가 나왔다 — 시험이 아니라
    #: 내가 지은 경로가 틀렸던 자리다.
    r = _path([(50, 0.001), (40, -0.01), (250, 0.002),  # 깊은 낙폭 → 전고점 회복
               (10, -0.001), (40, 0.001)])              # 얕은 낙폭 → 회복
    got = drawdown_episodes(r, alpha=0.05)
    assert got["tail_episodes"] == 1
    assert got["total_episodes"] >= 2
    assert got["tail_points"] > got["tail_episodes"], "점 수와 사건 수는 다른 물건이다"


def test_two_equally_deep_episodes_are_counted_as_two():
    """같은 깊이의 낙폭이 둘이면 꼬리도 둘에서 온다 — 세는 방식이 맞다는 증거."""
    from evaluation.metrics import drawdown_episodes

    leg = [(30, -0.01), (60, 0.006)]                    # 내려갔다 회복
    r = _path([(20, 0.001)] + leg + leg)
    got = drawdown_episodes(r, alpha=0.20)
    assert got["tail_episodes"] == 2


def test_cdar_ratio_carries_the_episode_count():
    """순위 지표가 **자기 근거의 두께**를 같이 낸다 — 보고서가 그걸 적는다."""
    from evaluation.metrics import cdar_ratio

    r = _path([(50, 0.001), (40, -0.01), (100, 0.002)])
    got = cdar_ratio(r)
    assert got["tail_episodes"] >= 1
    assert got["total_episodes"] >= got["tail_episodes"]
    assert got["points_per_episode"] is not None


# ── 묶은 봉의 AR(1) — 문헌의 환율이 «월별» 위에 있다 ──────────────────────

def test_daily_ar1_dies_by_monthly_aggregation():
    """일별 AR(1) 0.2 짜리는 **21봉 묶음에서 사실상 0** 이다.

    이 데스크의 실측이 그것이다 — MR 상한판은 일별 +0.213 인데 21봉에서 −0.060.
    그래서 Man/Harvey 외(2020)의 「**월별** 자기상관 0.1 ≈ Sharpe 0.5→0.4」 환율을
    **일별 AR(1) 에 그대로 대면 안 된다.** 두 수를 나란히 내는 이유다.
    """
    import numpy as np
    from evaluation.metrics import ar1_blocked

    rng = np.random.default_rng(42)
    e = rng.normal(0, 0.01, 8000)
    x = np.zeros(8000)
    for i in range(1, 8000):
        x[i] = 0.2 * x[i - 1] + e[i]
    r = pd.Series(x)
    #: ⚠ 묶으면 표본이 줄어든다 — 8,000봉이 380묶음이 되고 표준오차가 1/√380 ≈
    #: 0.05 다. 이론값은 φ/(m(1−φ²)) ≈ 0.01 인데 실측은 그 표준오차 안에서 흔들린다.
    #: 「0 이다」가 아니라 「0 과 구별되지 않는다」가 이 시험이 재는 것이다.
    v, blocks = ar1_blocked(r, block=21)
    assert r.autocorr(1) > 0.15
    assert abs(v) < 3.0 / math.sqrt(blocks), (v, blocks)


def test_blocked_ar1_survives_when_the_memory_is_long():
    """반대쪽도 잰다 — 기억이 길면 묶어도 **안 죽는다**(안 그러면 항상 0 이 나온다)."""
    import numpy as np
    from evaluation.metrics import ar1_blocked

    rng = np.random.default_rng(9)
    e = rng.normal(0, 0.01, 8000)
    x = np.zeros(8000)
    for i in range(1, 8000):
        x[i] = 0.97 * x[i - 1] + e[i]
    assert ar1_blocked(pd.Series(x), block=21)[0] > 0.3


def test_blocked_ar1_needs_enough_blocks():
    """묶음이 셋도 안 되면 **못 잰다고 말한다** — 0 을 내지 않는다."""
    from evaluation.metrics import ar1_blocked

    assert ar1_blocked(pd.Series([0.01] * 40), block=21)[0] is None
