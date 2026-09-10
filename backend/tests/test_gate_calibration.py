# -*- coding: utf-8 -*-
"""`scripts/gate_calibration` — 눈금 자체가 맞는지 잰다.

이 파일은 «해석»을 안 잰다. 재는 것은 셋이다.

① **허들이 진짜 허들인가** — 그 SR 을 도로 DSR 식에 넣으면 문턱이 나와야 한다.
② **필요 연수가 허들의 역함수인가** — 두 함수가 같은 식의 양쪽이라 어긋나면
   표 두 개가 서로 다른 말을 하게 된다.
③ **문턱을 안 건드렸다** — 이 스크립트가 사양을 조용히 바꾸지 않았다는 것.
   외부 눈금에 출처가 붙어 있는지도 여기서 잰다(숫자만 있는 줄은 대조가 안 된다).
"""
from __future__ import annotations

import math

import pytest
from scipy import stats

from evaluation import metrics as ev
from scripts import gate_calibration as gc

#: 실제 계열을 안 쓴다 — 이 시험은 산술을 재는 것이지 북을 재는 것이 아니다.
SK, EXKU, N = 1.2, 9.0, 2370
SR0 = 0.01


def _dsr(sr: float) -> float:
    den = 1.0 - SK * sr + (EXKU + 3.0 - 1.0) / 4.0 * sr * sr
    return float(stats.norm.cdf((sr - SR0) * math.sqrt(N - 1) / math.sqrt(den)))


def test_hurdle_reproduces_the_threshold():
    """① 허들을 도로 넣으면 DSR 이 문턱이다."""
    h = gc.hurdle_sr(SK, EXKU, N, SR0)
    assert _dsr(h) == pytest.approx(ev.DSR_PASS, abs=1e-9)


def test_hurdle_rises_with_trials():
    """시행수가 늘면 허들이 오른다 — 방향이 뒤집히면 표가 거짓말을 한다."""
    var = 1.0 / N
    prev = None
    for trials in (1, 9, 72, 1000):
        sr0 = ev.expected_max_sr(trials, var)
        h = gc.hurdle_sr(SK, EXKU, N, sr0)
        if prev is not None:
            assert h > prev
        prev = h


def test_years_needed_inverts_the_hurdle():
    """② 허들만큼의 연 SR 이면 필요 연수가 «지금 표본»으로 떨어진다."""
    h = gc.hurdle_sr(SK, EXKU, N, SR0)
    y = gc.years_needed(h * math.sqrt(gc.ANN), SK, EXKU, SR0)
    assert y == pytest.approx(N / gc.ANN, rel=1e-6)


def test_years_needed_is_none_below_the_selection_penalty():
    """뽑기 벌보다 낮은 SR 은 «몇 년이든» 못 넘는다 — 0 이 아니라 None 이다."""
    assert gc.years_needed(SR0 * math.sqrt(gc.ANN) * 0.5, SK, EXKU, SR0) is None


def test_fee_arithmetic():
    """운용보수는 SR 단위로 0.02/σ 만큼, 성과보수는 나머지의 20%."""
    assert gc.after_fees(1.0, 0.10) == pytest.approx(0.8 * (1.0 - 0.2))
    assert gc.after_fees(1.0, 0.20) == pytest.approx(0.8 * (1.0 - 0.1))
    # σ 가 클수록 운용보수의 SR 부담이 준다.
    assert gc.after_fees(0.85, 0.15) > gc.after_fees(0.85, 0.10)


def test_thresholds_are_untouched():
    """③ 이 스크립트는 사양을 안 바꾼다.

    ⚠ 값 자체는 2026-09-10 에 **오너가** 바꿨다(PBO 0.20 → 0.50 · 위약 신설 · §21).
    이 시험이 지키는 것은 그 값이 아니라 **교정 스크립트가 값을 건드리지 않는다**는
    것이다. 사양 값 자체는 `test_evaluation.test_the_gate_thresholds_are_the_owner_spec`
    이 못 박는다.
    """
    assert ev.DSR_PASS == 0.95
    assert ev.PBO_PASS == 0.50 == ev.PBO_DISCARD
    assert ev.PLACEBO_PASS == 0.05


def test_every_peer_carries_a_source_and_a_period():
    """숫자만 있는 눈금 줄은 다음 세션이 대조를 못 한다."""
    assert len(gc.PEERS) >= 5
    for label, sr, period, fee, src in gc.PEERS:
        assert label and period and fee and src, f"{label} 에 출처나 기간이 없어요"
        assert 0.0 < sr < 2.0
        assert any(ch.isdigit() for ch in period), f"{label} 의 기간에 연도가 없어요"
