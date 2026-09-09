# -*- coding: utf-8 -*-
"""`scripts/momentum_irs_evaluate` — 계기를 바꾼 판정의 계약을 잰다.

이 파일이 지키는 것 셋이다.

① **재구성 등식** — 평가층에 올라가는 IRS 계열이 `scripts/momentum_irs.py` 가 세운
   그 북과 같은 것이어야 한다. 그 스크립트가 구조를 바꾸면 여기가 조용히 딴 것을
   재는 대신 시험이 깨진다(`test_momentum_evaluate` 와 같은 규율).
② **창이 하나** — 두 계기를 나란히 놓는 표는 같은 날짜 위에서만 뜻이 있다.
③ **짝짓기가 실제로 짝을 짓는다** — `paired_ci` 가 두 계열에 같은 블록을 먹이지
   않으면 그건 차이의 검정이 아니라 주변 구간 둘을 다시 겹쳐 보는 것이다.

⚠ 모멘텀 레인이나 IRS 자료가 없으면 통째로 건너뛴다 — 없는 것을 통과로 두지
않으려고 skip 이지 pass 가 아니다.
"""
from __future__ import annotations

import pandas as pd
import pytest

mo = pytest.importorskip("app.momentum", reason="모멘텀 레인이 이 트리에 없어요")

from app import ctabacktest as cta                    # noqa: E402
from scripts import momentum_evaluate as me           # noqa: E402
from scripts import momentum_irs as mi                # noqa: E402
from scripts import momentum_irs_evaluate as mie      # noqa: E402


@pytest.fixture(scope="module")
def series():
    try:
        s = mie.load_irs_series()
    except Exception as exc:                                   # noqa: BLE001
        pytest.skip(f"IRS 자료를 못 읽었어요 — {exc}")
    if not s["3Y"][0]:
        pytest.skip("IRS 자료가 비어 있어요")
    return s


# ── ① 재구성 등식 ────────────────────────────────────────────────────────

def test_series_match_momentum_irs(series):
    """`-bp` 계열이 그 스크립트의 `load_irs_bp` 와 **한 치도 안 다르다**."""
    theirs = mi.load_irs_bp()
    common = sorted(set(theirs["3Y"][0]) & set(theirs["10Y"][0]))
    for tenor in ("3Y", "10Y"):
        mine_days, mine_vals = series[tenor]
        assert mine_days == common, f"{tenor} 의 날짜가 달라요"
        theirs_map = dict(zip(*theirs[tenor]))
        assert mine_vals == [theirs_map[d] for d in common], f"{tenor} 의 값이 달라요"


def test_book_matches_momentum_irs(series):
    """**내 북 = 그 스크립트의 북.** 편도 0.5bp[OWNER] 그 줄에서 잰다."""
    theirs = mi.run(series, cost_ticks=mie.IRS_COST_BP / cta.TICK)
    mine = mie.irs_points()
    assert len(mine) == len(theirs["points"])
    for a, b in zip(mine, theirs["points"]):
        assert a["t"] == b["t"]
        assert a["dailyPnl"] == b["dailyPnl"], f"{a['t']} 의 손익이 달라요"


def test_no_roll_days_in_the_irs_book(series):
    """IRS 는 굴러오는 계약이 아니다 — 롤을 넣으면 없는 점프를 그린다.

    롤을 넣은 북과 안 넣은 북이 **달라지는지**로 잰다. 인자를 읽는 시험이 아니라
    회계가 실제로 갈리는 자리를 잡는 시험이다.
    """
    days = series["3Y"][0]
    rolled = cta.book_simulate(
        series, signal=mo.SIGNAL, lookbacks=mo.LOOKBACKS,
        vol_window=mo.VOL_WINDOW, target_book_vol_krw=mo.TARGET_VOL,
        book_vol_window=mo.BOOK_VOL_WINDOW,
        roll_days={days[len(days) // 2]}, continuous=True,
        cost_ticks=mie.IRS_COST_BP / cta.TICK)
    mine = mie.irs_points()
    assert [p["dailyPnl"] for p in mine] != \
        [p["dailyPnl"] for p in rolled["points"]], \
        "롤이 회계를 안 바꾸면 이 시험이 아무것도 안 지켜요"


def test_window_stops_at_freeze(series):
    pts = mie.irs_points()
    assert pts[0]["t"] >= mie.START
    assert pts[-1]["t"] <= mo.FREEZE


# ── ② 창이 하나 ─────────────────────────────────────────────────────────

def test_head_to_head_is_on_one_window(series):
    """두 칸 행렬이 **같은 날짜** 위에 선다 — 안 그러면 표가 거짓말을 한다."""
    irs, fut = mie.matrices()
    assert list(irs.index) == list(fut.index)
    assert len(irs) > 1000


def test_cells_are_nine_and_the_signal_axis_is_live(series):
    """칸 9개(신호계 3 × 볼 윈도 3)이고 신호 축이 **실제로 움직인다**.

    IRS 북은 `external_signals` 를 안 쓰므로 매크로 다리에서 축이 죽던 사정이
    여기엔 없다 — 그 말이 사실인지를 값으로 잰다.
    """
    mat = mie.irs_matrix()
    assert mat.shape[1] == 9
    base = f"{mo.SIGNAL}-vw{mo.VOL_WINDOW}"
    others = [c for c in mat.columns
              if c.endswith(f"-vw{mo.VOL_WINDOW}") and c != base]
    assert others
    for c in others:
        assert not mat[c].equals(mat[base]), f"{c} 가 {base} 와 같아요"


def test_trials_count_the_instrument_axis():
    """계기가 «고르는 축»이 되면 N 이 두 배다 — 세지 않으면 게이트가 헐거워진다."""
    assert mie.INSTRUMENTS == 2
    assert mie.TRIALS == me.TRIALS * 2 == 72


# ── ③ 짝짓기 ────────────────────────────────────────────────────────────

def test_paired_ci_of_a_series_against_itself_is_exactly_zero():
    """같은 계열끼리는 **차이가 0 이고 폭도 0** 이다.

    블록을 따로 뽑으면 여기서 0 이 안 나온다 — 이 한 줄이 「짝을 지었나」를 잰다.
    """
    s = pd.Series([0.3, -0.2, 0.5, -0.1, 0.4, -0.6] * 40)
    d = mie.paired_ci(s, s, lambda x: float(x.mean()), block=12, n=40)
    assert d["lo"] == d["hi"] == d["median"] == 0.0


def test_paired_ci_rejects_mismatched_lengths():
    a = pd.Series([0.1] * 200)
    with pytest.raises(ValueError):
        mie.paired_ci(a, pd.Series([0.1] * 199), lambda x: float(x.mean()),
                      block=12, n=10)


def test_paired_ci_finds_a_planted_difference():
    """한쪽에 상수를 얹으면 그만큼이 차이로 나온다 — 부호와 크기 둘 다."""
    a = pd.Series([0.3, -0.2, 0.5, -0.1, 0.4, -0.6] * 40)
    d = mie.paired_ci(a + 1.0, a, lambda x: float(x.mean()), block=12, n=40)
    assert d["lo"] == pytest.approx(1.0)
    assert d["hi"] == pytest.approx(1.0)
    assert d["p_le0"] == 0.0
