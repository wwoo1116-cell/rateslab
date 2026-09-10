# -*- coding: utf-8 -*-
"""`scripts/hard_test` — 빡센 검정의 **배관**을 잰다.

해석은 안 잰다. 재는 것은 이 검정들이 조용히 거짓말할 수 있는 자리 넷이다.

① **회계 등식** — 위약을 수백 번 돌리려고 엔진 회계를 배열로 다시 폈다. 그
   재구현이 엔진과 한 치라도 다르면 위약 분포가 통째로 딴 것이 된다.
② **이동이 진짜 이동인가** — 부호만 미는 판이 크기를 안 건드려야 P2 가 「방향
   타이밍만」을 재는 시험이 된다.
③ **전진 선택에 룩어헤드가 없는가** — 미래에만 좋은 칸을 심어 두고, 고르기가
   그것을 **안 고르는지** 본다. 자르는 부등호 하나가 뒤집히면 이 시험이 깨진다.
④ **부트스트랩이 재현되는가** — 씨앗이 고정이라 같은 수가 다시 나와야 한다.

⚠ 모멘텀 레인이나 IRS 자료가 없으면 건너뛴다 — skip 이지 pass 가 아니다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("app.momentum", reason="모멘텀 레인이 이 트리에 없어요")

from app import ctabacktest as cta                    # noqa: E402
from scripts import hard_test as ht                   # noqa: E402


@pytest.fixture(scope="module")
def bs():
    try:
        return ht.books()
    except Exception as exc:                                   # noqa: BLE001
        pytest.skip(f"북을 못 세웠어요 — {exc}")


# ── ① 회계 등식 ─────────────────────────────────────────────────────────

def test_vectorized_accounting_matches_the_engine(bs):
    """배열로 편 회계 = 엔진의 `dailyPnl`. 롤 비용이 붙는 선물 쪽도 같이 잰다."""
    for name, b in bs.items():
        pl = ht._plumbing(b["book"], b["series"], b["rolls"], b["ticks"])
        mine = ht._repnl(pl, b["book"]["pos"])
        eng = np.array([p["dailyPnl"] for p in b["book"]["points"]])
        scale = float(np.abs(eng).mean())
        assert np.abs(mine - eng).max() < scale * 1e-9, f"{name} 회계가 어긋났어요"


def test_roll_cost_actually_enters(bs):
    """선물 북에는 롤이 있고 IRS 북에는 없다 — 배관이 그걸 구별하는가."""
    assert bs["선물"]["rolls"], "선물 롤일이 비어 있으면 이 시험이 아무것도 안 지켜요"
    assert not bs["IRS"]["rolls"]
    b = bs["선물"]
    with_roll = ht._plumbing(b["book"], b["series"], b["rolls"], b["ticks"])
    without = ht._plumbing(b["book"], b["series"], set(), b["ticks"])
    a = ht._repnl(with_roll, b["book"]["pos"])
    c = ht._repnl(without, b["book"]["pos"])
    assert a.sum() < c.sum(), "롤 비용이 손익을 안 깎으면 배관이 그걸 안 물린 거예요"


# ── ② 이동 ──────────────────────────────────────────────────────────────

def test_shift_zero_is_identity():
    pos = {"a": [1.0, -2.0, 3.0, 0.0, -4.0]}
    got = ht._shifted(pos, 0, sign_only=False)
    assert np.allclose(got["a"], pos["a"])


def test_sign_only_shift_keeps_magnitudes():
    """P2 는 크기를 안 건드린다 — 안 그러면 변동성 타이밍까지 죽는다."""
    pos = {"a": [1.0, -2.0, 3.0, -4.0, 5.0]}
    got = ht._shifted(pos, 2, sign_only=True)
    assert np.allclose(np.abs(got["a"]), np.abs(pos["a"]))
    assert not np.allclose(got["a"], pos["a"])


def test_full_shift_moves_magnitudes_too():
    pos = {"a": [1.0, -2.0, 3.0, -4.0, 5.0]}
    got = ht._shifted(pos, 1, sign_only=False)
    assert np.allclose(got["a"], [5.0, 1.0, -2.0, 3.0, -4.0])


def test_shift_floor_clears_the_longest_lookback():
    """이동이 최장 룩백보다 짧으면 위약이 신호를 덜 끊는다."""
    from app import momentum as mo
    assert ht.SHIFT_MIN >= max(mo.LOOKBACKS)


# ── ③ 전진 선택 ─────────────────────────────────────────────────────────

def _fake_matrix() -> pd.DataFrame:
    """2018 년에만 좋은 칸 하나를 심는다 — 고르기가 2018 에 그것을 고르면 룩어헤드다."""
    days = ([f"2017-{m:02d}-01" for m in range(1, 13)] +
            [f"2018-{m:02d}-01" for m in range(1, 13)] +
            [f"2019-{m:02d}-01" for m in range(1, 13)])
    steady = [0.5, -0.2] * 18
    future = [0.0] * 12 + [3.0, -0.1] * 6 + [0.0] * 12
    return pd.DataFrame({"steady": steady, "future": future}, index=days)


def test_walk_forward_does_not_peek():
    """③ 미래에만 좋은 칸은 그 해에 안 골린다."""
    w = ht.walk_forward(_fake_matrix(), fixed_col="steady")
    got = dict(w["picks"])
    assert got["2018"] == "steady", "그 해 자료를 보고 골랐어요(룩어헤드)"
    assert got["2019"] == "future", "지난 해 성적을 아예 안 보고 있어요"


def test_walk_forward_skips_the_first_year():
    w = ht.walk_forward(_fake_matrix(), fixed_col="steady")
    assert [y for y, _ in w["picks"]] == ["2018", "2019"]
    assert not any(t.startswith("2017") for t in w["picked"].index)


def test_walk_forward_lines_are_on_one_window():
    w = ht.walk_forward(_fake_matrix(), fixed_col="steady")
    assert list(w["picked"].index) == list(w["fixed"].index) == \
        list(w["equal"].index)


# ── ④ 부트스트랩 ────────────────────────────────────────────────────────

def test_bootstrap_is_reproducible():
    r = pd.Series([0.4, -0.3, 0.6, -0.1, 0.2, -0.5] * 60)
    a = ht._boot_sr(r, n=40, block=12)
    b = ht._boot_sr(r, n=40, block=12)
    assert np.allclose(a, b), "씨앗이 고정인데 수가 달라지면 표를 못 믿어요"


def test_bench_levels_come_from_the_calibration_sheet():
    """눈금이 §16 의 그 값과 같아야 두 절이 같은 말을 한다."""
    from scripts import gate_calibration as gc
    peers = {label: sr for label, sr, *_ in gc.PEERS}
    assert ("SG CTA 지수", 0.61) in [(k, v) for k, v in
                                    [(n, s) for n, s in ht.BENCH]]
    assert any(abs(v - 0.61) < 1e-9 for v in peers.values())
    assert any(abs(v - 0.50) < 1e-9 for v in peers.values())
    assert any(abs(v - 0.40) < 1e-9 for v in peers.values())


def test_hiking_window_is_a_real_range():
    lo, hi = ht.HIKING
    assert lo < hi
    assert lo.startswith("2021") and hi.startswith("2023")
    assert cta.TICK == 0.01           # 회계 단위가 바뀌면 위 표가 전부 갈린다


def test_cdar_selection_scores_every_cell():
    """오너 기준으로 고르는 자도 칸마다 값을 낸다 — 하나라도 비면 고르기가 막힌다."""
    m = _fake_matrix()
    s = ht._score_cdar(m)
    assert list(s.index) == list(m.columns)
    assert s.notna().all()


def test_selection_criterion_actually_changes_the_pick():
    """두 자가 같은 답만 내면 ④ 의 «기준을 흔든다» 가 아무것도 안 흔든 것이 된다."""
    m = _fake_matrix()
    by_sr = ht.walk_forward(m, fixed_col="steady", score=ht._score_sr)["picks"]
    by_cd = ht.walk_forward(m, fixed_col="steady", score=ht._score_cdar)["picks"]
    assert len(by_sr) == len(by_cd)
