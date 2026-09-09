# -*- coding: utf-8 -*-
"""`scripts/crs_evaluate` — 증거금 상한판을 평가층에 올리는 자리의 계약.

⚠ 그 장부(`krw-crs`)는 **이 리포 밖에 산다.** 없으면 통째로 건너뛴다 — 없는 것을
통과로 두지 않으려고 skip 이지 pass 가 아니다.
"""
from __future__ import annotations

import pytest

from scripts import crs_evaluate as ce


def _lane_or_skip():
    try:
        return ce._lane()
    except SystemExit as e:
        pytest.skip(str(e))


@pytest.fixture(scope="module")
def mb():
    return _lane_or_skip()


# ── ① 자본비용 규약 — **판정이 여기서 갈린다** ──────────────────────────

def test_bound_funding_charges_less_than_full_capital(mb):
    """「묶인 증거금에만」이 「전액」보다 **덜 문다** — 그래서 순수익이 높다.

    두 규약이 살아 있고(PREREG 2판이 「묶인 것만」으로 바꿨다) 실제로 이 하나가
    DSR 을 0.79 → 0.998 로 옮긴다. 방향을 뒤집어 구현하면 판정이 통째로 거짓이
    되므로 부호를 시험이 잡는다.
    """
    bound, f = ce.net_returns(mb, ce.REGISTERED_LOT_UK, "bound")
    cap, _ = ce.net_returns(mb, ce.REGISTERED_LOT_UK, "cap")
    assert bound.sum() > cap.sum()
    # 사용률이 100% 가 아니어야 두 규약이 실제로 다르다 — 아니면 이 시험이 공허하다.
    assert 0.0 < f["use_mean"] < 1.0


def test_unknown_funding_mode_is_refused(mb):
    """모르는 규약은 **조용히 하나를 고르지 않는다** — 멈춘다."""
    with pytest.raises(SystemExit):
        ce.net_returns(mb, ce.REGISTERED_LOT_UK, "whatever")


# ── ② 자본 기준 — 이 레인에서 처음으로 분모가 가정이 아니다 ─────────────

def test_returns_are_divided_by_the_hundred_billion_capital(mb):
    """수익률 = 그날 순손익 / **100억**(그 레인의 제약이지 내 가정이 아니다)."""
    r, _f = ce.net_returns(mb, ce.REGISTERED_LOT_UK, "bound")
    assert mb.CAP == 100e8
    # 하루 수익률이 자본의 몇 %대라야 «비율» 이다 — 원 단위가 새어 나오면 터진다.
    assert r.abs().max() < 0.1, "하루 10% 넘는 봉이 있어요 — 분모가 빠졌나요"
    assert r.std() > 0


# ── ③ 칸 계획 — 그 레인이 결과 보기 전 고정한 격자 ──────────────────────

def test_matrix_is_the_lane_lot_grid(mb):
    """칸 = 로트 격자 여섯. 이름도 그 격자에서 나온다."""
    m = ce.config_matrix(mb, "bound")
    assert list(m.columns) == [f"lot{x}" for x in mb.LOTS_UK]
    assert m.shape[1] == 6 and m.shape[0] > 1000


def test_trials_is_the_lane_number_not_mine():
    """N=50 은 **그 레인이 `PREREG_03` §5.1 에 세어 둔 값**이다.

    모멘텀 자리의 36 은 내가 그 레인 문서를 읽어 센 값이라 성질이 다르다 —
    여기는 그쪽이 이미 적어 둔 수라 내가 다시 세면 안 된다.
    """
    assert ce.TRIALS == 50
    assert ce.REGISTERED_LOT_UK == 50


# ── ④ 그 레인이 이 리포 밖이라는 사실 ───────────────────────────────────

def test_missing_lane_says_why_instead_of_returning_zero(monkeypatch, tmp_path):
    """장부가 없으면 **조용히 0 을 내지 않고** 어디를 봤는지 말한다."""
    monkeypatch.setattr(ce, "LANE", tmp_path)
    with pytest.raises(SystemExit) as e:
        ce._lane()
    assert "margin_budget_book" in str(e.value)
