# -*- coding: utf-8 -*-
"""`scripts/hedge_test` — 보험 검정의 배관을 잰다.

이 검정이 조용히 거짓말할 수 있는 자리 넷.

① **낙폭 구간 찾기** — 겹치는 구간을 두 번 세면 「다섯 구간」이 사실은 한 구간이 된다.
② **단위 맞추기** — MR 은 비율, 추세는 원(₩)이다. 안 맞추고 더하면 큰 쪽이 다 먹는다.
③ **짝짓기** — 개선의 구간은 두 계열을 «같은 블록»으로 뽑아야 뜻이 있다.
④ **이항 꼬리** — 「4/5」에 붙이는 기준선이 맞아야 그 낱말이 증거가 된다.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("app.momentum", reason="모멘텀 레인이 이 트리에 없어요")

from scripts import hedge_test as ht                  # noqa: E402


# ── ① 낙폭 구간 ─────────────────────────────────────────────────────────

def test_spells_are_non_overlapping_and_sorted_by_depth():
    """깊은 순으로 나오고, 서로 안 겹친다."""
    x = pd.Series([1, 1, -5, -5, 1, 1, 1, -9, -9, 1, 1],
                  index=[f"d{i:02d}" for i in range(11)], dtype=float)
    got = ht.spells(x, k=3)
    depths = [d for d, _a, _b in got]
    assert depths == sorted(depths, reverse=True)
    for i, (_d, a, b) in enumerate(got):
        for _e, c, e in got[i + 1:]:
            assert b < c or a > e, "구간이 겹쳤어요"


def test_spells_find_the_deepest_run():
    """구간의 시작은 **전고점이 선 날**이다(첫 손실일이 아니다).

    `smile_use.py` 의 그 규약을 그대로 물려받았다 — 창이 하루 일찍 시작한다는
    뜻이고, 09-08 판정과 나란히 놓으려면 같아야 하는 자리다.
    """
    x = pd.Series([1, -1, -1, -1, 5], index=list("abcde"), dtype=float)
    (depth, a, b), = ht.spells(x, k=1)
    assert (a, b) == ("a", "d")
    assert depth == pytest.approx(3.0)


def test_spells_returns_fewer_when_there_are_fewer():
    x = pd.Series([1.0, 2.0, 3.0], index=list("abc"))   # 낙폭이 없다
    assert ht.spells(x, k=5) == []


# ── ② 단위 ──────────────────────────────────────────────────────────────

def test_unit_vol_gives_annual_vol_one():
    rng = np.random.default_rng(0)
    s = pd.Series(rng.normal(3.0, 7.0, 2000))
    u = ht.unit_vol(s)
    assert float(u.std(ddof=1) * math.sqrt(ht.ANN)) == pytest.approx(1.0)


def test_unit_vol_survives_a_flat_series():
    s = pd.Series([0.0] * 50)
    assert float(ht.unit_vol(s).abs().sum()) == 0.0


def test_unit_vol_is_scale_free():
    """원(₩)이든 비율이든 같은 계열이 나와야 두 장부를 나란히 놓을 수 있다."""
    rng = np.random.default_rng(1)
    s = pd.Series(rng.normal(0.0, 1.0, 500))
    assert np.allclose(ht.unit_vol(s), ht.unit_vol(s * 1e8))


# ── ③ 짝짓기 ────────────────────────────────────────────────────────────

def test_paired_ci_of_a_series_with_itself_is_exactly_zero():
    """같은 계열을 섞으면 개선이 0 이다 — 블록을 따로 뽑으면 여기서 0 이 안 나온다."""
    rng = np.random.default_rng(2)
    m = rng.normal(0.001, 0.01, 800)
    ci = ht._paired_ci(m, m, 0.25, n=40, block=20)
    assert ci["cal"] == (pytest.approx(0.0), pytest.approx(0.0))
    assert ci["mdd"] == (pytest.approx(0.0), pytest.approx(0.0))


def test_paired_ci_is_reproducible():
    rng = np.random.default_rng(3)
    m, t = rng.normal(0, 0.01, 600), rng.normal(0, 0.01, 600)
    a = ht._paired_ci(m, t, 0.25, n=30, block=20)
    b = ht._paired_ci(m, t, 0.25, n=30, block=20)
    assert a == b


def test_card_reports_a_positive_drawdown():
    """MDD 는 **크기**다 — 부호가 뒤집히면 「얕아졌다」를 거꾸로 읽는다."""
    x = np.array([1.0, -3.0, 1.0, 1.0])
    cal, mdd = ht._card(x)
    assert mdd > 0
    assert cal == pytest.approx(x.mean() * ht.ANN / mdd)


# ── ④ 이항 꼬리 ─────────────────────────────────────────────────────────

def test_binom_tail_matches_the_hand_calculation():
    """P(X ≥ 4 | n=5, p=0.5) = 6/32."""
    assert ht._binom_tail(4, 5, 0.5) == pytest.approx(6 / 32)
    assert ht._binom_tail(0, 5, 0.3) == pytest.approx(1.0)
    assert ht._binom_tail(5, 5, 0.5) == pytest.approx(1 / 32)


def test_binom_tail_rises_with_p():
    assert ht._binom_tail(4, 5, 0.6) > ht._binom_tail(4, 5, 0.4)


# ── 규약 ────────────────────────────────────────────────────────────────

def test_registered_weight_and_grid_match_the_prior_session():
    """09-08 이 쓴 격자와 가중을 여기서 다시 고르지 않는다."""
    assert ht.W_REGISTERED == 0.25
    assert ht.W_REGISTERED in ht.WEIGHTS
    assert ht.WEIGHTS[0] == 0.0          # 기준선이 있어야 Δ 를 낸다


def test_speeds_bracket_the_registered_bundle():
    """빠름·느림이 등록된 다발을 **양쪽에서** 감싸야 «흔든 것»이 된다."""
    from app import momentum as mo
    reg = ht.SPEEDS["등록 (20~250)"]
    assert reg == mo.LOOKBACKS
    fast, slow = ht.SPEEDS["빠름 (5~60)"], ht.SPEEDS["느림 (60~500)"]
    assert max(fast) <= min(reg) * 3 and max(fast) < max(reg)
    assert min(slow) >= min(reg) and max(slow) > max(reg)


def test_shift_floor_clears_the_longest_lookback():
    from app import momentum as mo
    assert ht.SHIFT_MIN >= max(mo.LOOKBACKS)
