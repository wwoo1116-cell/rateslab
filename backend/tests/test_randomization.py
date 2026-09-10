# -*- coding: utf-8 -*-
"""`evaluation/randomization` — 게이트 셋째의 배관을 잰다.

이 검정이 조용히 거짓말할 수 있는 자리 넷.

① **회계 등식** — 배열로 편 회계가 엔진의 `dailyPnl` 과 한 치라도 다르면 위약
   분포가 통째로 딴 것이 된다.
② **이동이 진짜 이동인가** — 부호만 미는 판이 크기를 안 건드려야 P2 가 「방향
   타이밍만」을 재는 시험이 된다.
③ **p 의 방향** — 신호를 심으면 p 가 작아지고, 잡음이면 커져야 한다.
④ **바닥** — 이동이 너무 적으면 p 가 작아질 수가 없다. 그때는 수를 내지 말고
   못 쟀다고 말해야 한다.
"""
from __future__ import annotations

import numpy as np
import pytest

from evaluation import randomization as rz


def _pl(n: int = 800, rolls: set[str] | None = None, ticks: float = 0.0):
    dates = [f"d{i:04d}" for i in range(n)]
    rng = np.random.default_rng(0)
    px = np.concatenate(([100.0], 100.0 + np.cumsum(rng.normal(0, 1, n - 1))))
    price = {"A": dict(zip(dates, px))}
    return dates, price, rz.plumbing(dates, price, rolls or set(), ticks, 0.01)


# ── ① 회계 ──────────────────────────────────────────────────────────────

def test_repnl_matches_a_hand_computed_pnl():
    """오늘 가격변화에는 **어제** 포지션이 걸린다. 하루 어긋나면 룩어헤드다."""
    dates = ["a", "b", "c"]
    price = {"X": {"a": 100.0, "b": 100.0, "c": 107.0}}
    pl = rz.plumbing(dates, price, set(), 0.0, 0.01)
    got = rz.repnl(pl, {"X": [0.0, 10.0, 0.0]})
    assert got[1] == 0.0
    assert got[2] == pytest.approx(10.0 / 100.0 * 7.0)


def test_cost_is_charged_on_position_change():
    dates, price, _ = _pl(n=3)
    pl = rz.plumbing(dates, price, set(), 50.0, 0.01)      # 편도 0.5
    flat = rz.repnl(pl, {"A": [0.0, 0.0, 0.0]})
    traded = rz.repnl(pl, {"A": [100.0, 100.0, 100.0]})
    assert flat[0] == 0.0
    assert traded[0] == pytest.approx(-100.0 / 100.0 * 0.01 * 50.0)


def test_roll_cost_only_lands_on_roll_days():
    dates, price, _ = _pl(n=5)
    with_roll = rz.plumbing(dates, price, {dates[3]}, 0.0, 0.01)
    without = rz.plumbing(dates, price, set(), 0.0, 0.01)
    pos = {"A": [50.0] * 5}
    diff = rz.repnl(without, pos) - rz.repnl(with_roll, pos)
    assert diff[3] == pytest.approx(50.0 / 100.0 * 0.01)
    assert np.allclose(np.delete(diff, 3), 0.0)


# ── ② 이동 ──────────────────────────────────────────────────────────────

def test_shift_zero_is_identity():
    pos = {"A": [1.0, -2.0, 3.0, 0.0]}
    assert np.allclose(rz.shifted(pos, 0, sign_only=False)["A"], pos["A"])


def test_sign_only_shift_keeps_magnitudes():
    pos = {"A": [1.0, -2.0, 3.0, -4.0, 5.0]}
    got = rz.shifted(pos, 2, sign_only=True)["A"]
    assert np.allclose(np.abs(got), np.abs(pos["A"]))
    assert not np.allclose(got, pos["A"])


def test_full_shift_moves_magnitudes_too():
    pos = {"A": [1.0, -2.0, 3.0, -4.0, 5.0]}
    assert np.allclose(rz.shifted(pos, 1, sign_only=False)["A"],
                       [5.0, 1.0, -2.0, 3.0, -4.0])


# ── ③ p 의 방향 ─────────────────────────────────────────────────────────

def test_a_perfect_signal_gets_a_small_p():
    """다음 날 가격변화의 부호를 아는 북은 어떤 이동도 못 이긴다."""
    dates, price, pl = _pl(n=800)
    dp = pl["dp"]["A"]
    pos = {"A": [float(np.sign(dp[i + 1])) * 100.0 if i + 1 < len(dp) else 0.0
                 for i in range(len(dates))]}
    got = rz.placebo(pl, pos, shift_min=50, step=10)
    assert got["p"] is not None
    assert got["p"] < 0.02
    assert got["real_sr"] > got["placebo_p95"]


def test_a_noise_book_does_not_get_a_small_p():
    """가격과 무관한 포지션이면 위약과 구별되지 않아야 한다."""
    dates, price, pl = _pl(n=800)
    rng = np.random.default_rng(7)
    pos = {"A": list(rng.normal(0, 100, len(dates)))}
    got = rz.placebo(pl, pos, shift_min=50, step=10)
    assert got["p"] is not None
    assert got["p"] > 0.05


def test_the_mask_restricts_the_window():
    dates, price, pl = _pl(n=800)
    pos = {"A": [100.0] * len(dates)}
    mask = np.array([i >= 400 for i in range(len(dates))])
    whole = rz.placebo(pl, pos, shift_min=50)
    part = rz.placebo(pl, pos, shift_min=50, mask=mask)
    assert whole["real_sr"] != part["real_sr"]


# ── ④ 바닥 ──────────────────────────────────────────────────────────────

def test_too_few_shifts_says_it_cannot_measure():
    """이동이 적으면 p 의 바닥이 1/(이동수+1) 이라 작아질 수가 없다.

    그때 수를 내면 「쟀는데 못 넘었다」와 「잴 수가 없었다」가 같은 말이 된다.
    """
    dates, price, pl = _pl(n=120)
    got = rz.placebo(pl, {"A": [100.0] * len(dates)}, shift_min=50, step=10)
    assert got["p"] is None
    assert "바닥" in got["why"]


def test_p_never_reaches_zero():
    """무작위화 검정의 관례 — 실제 자신도 하나의 배치로 센다(+1)."""
    dates, price, pl = _pl(n=800)
    dp = pl["dp"]["A"]
    pos = {"A": [float(np.sign(dp[i + 1])) * 100.0 if i + 1 < len(dp) else 0.0
                 for i in range(len(dates))]}
    got = rz.placebo(pl, pos, shift_min=50, step=10)
    assert got["p"] >= 1.0 / (got["n_shifts"] + 1)


def test_gate_threshold_is_the_owner_spec():
    from evaluation import metrics as ev
    assert rz.PLACEBO_PASS == ev.PLACEBO_PASS == 0.05
