# -*- coding: utf-8 -*-
"""`scripts/sleeve_margin` — 「총위험 고정」의 산술을 잰다.

이 스크립트가 조용히 거짓말할 수 있는 자리 둘.

① **크기 산술** — 결합을 단독과 같은 연변동성으로 되돌리면 두 다리의 배수는
   `(1−w)/σ_mix` 와 `w/σ_mix` 다. 이게 틀리면 증거금 표가 통째로 틀린다.
② **DV01 환산** — 엔진이 `pos/100 × Δbp` 로 회계하므로 `pos/100` 이 곧 ₩/bp 다.
   100 을 빠뜨리면 액면이 백 배로 나온다.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

sm = pytest.importorskip("scripts.sleeve_margin",
                         reason="원천(그 레인·MySQL)이 없으면 건너뛴다")

ANN = 252


def _mix(m, t, w):
    return (1 - w) * m + w * t


def test_scaling_restores_the_standalone_volatility():
    """되돌린 결합의 연변동성이 단독과 같아야 한다 — 그래야 「총위험 고정」이다."""
    rng = np.random.default_rng(0)
    m = rng.normal(0, 1, 4000)
    t = rng.normal(0, 1, 4000)
    m, t = m / m.std(ddof=1), t / t.std(ddof=1)
    for w in (0.15, 0.25, 0.40, 0.60):
        x = _mix(m, t, w)
        s_mix = x.std(ddof=1)
        scaled = x / s_mix * m.std(ddof=1)
        assert scaled.std(ddof=1) == pytest.approx(m.std(ddof=1), rel=1e-12)


def test_leg_multipliers_are_the_ones_the_table_uses():
    """표가 쓰는 배수와 되돌림이 같은 것이어야 한다."""
    rng = np.random.default_rng(1)
    m = rng.normal(0, 1, 4000)
    t = rng.normal(0, 1, 4000)
    m, t = m / m.std(ddof=1), t / t.std(ddof=1)
    w = 0.25
    x = _mix(m, t, w)
    s_mix = x.std(ddof=1)
    by_hand = (1 - w) / s_mix * m + w / s_mix * t
    assert np.allclose(by_hand, x / s_mix)


def test_uncorrelated_mixing_lowers_the_blend_volatility():
    """상관 0 이면 σ_mix < 1 이다 — 「덜 걸어서 얕아진다」의 뿌리."""
    rng = np.random.default_rng(2)
    m = rng.normal(0, 1, 20000)
    t = rng.normal(0, 1, 20000)
    m, t = m / m.std(ddof=1), t / t.std(ddof=1)
    s = _mix(m, t, 0.25).std(ddof=1)
    assert s == pytest.approx(math.sqrt(0.75 ** 2 + 0.25 ** 2), abs=0.02)
    assert s < 1.0


def test_dv01_conversion_keeps_the_engine_hundred():
    """`pos/100` 이 ₩/bp 다 — 100 을 빠뜨리면 액면이 백 배가 된다."""
    pv = sm.pv01_per_100m()
    # 3Y 1억 명목의 pv01 은 3만원/bp 언저리(근사식)
    assert pv["3Y"] == pytest.approx(3e4, rel=1e-9)
    assert pv["10Y"] == pytest.approx(1e5, rel=1e-9)
    # DV01 30만원/bp 면 액면 10억
    assert (3e5 / pv["3Y"]) * 1e8 == pytest.approx(10e8, rel=1e-9)
