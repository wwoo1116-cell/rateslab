# -*- coding: utf-8 -*-
"""`scripts/momentum_evaluate` — **남의 레인을 재는 자리**의 계약을 잰다.

이 시험이 지키는 것은 하나다: 평가층에 올라가는 계열이 그 레인의 «등록된 북» 과
**같은 것**이어야 한다. 재구성이 조용히 어긋나면 판정이 딴 전략의 판정이 된다.

⚠ 모멘텀 레인이 이 트리에 없으면 통째로 건너뛴다(그 레인은 아직 미커밋이다).
없는 것을 통과로 두지 않으려고 skip 이지 pass 가 아니다.
"""
from __future__ import annotations

import math

import pytest

mo = pytest.importorskip("app.momentum",
                         reason="모멘텀 레인이 이 트리에 없어요")

from scripts import momentum_evaluate as me      # noqa: E402


@pytest.fixture(scope="module")
def built():
    """그 레인의 `build_book()` 과 내 재구성 — 한 번만 세워 나눠 쓴다(느리다)."""
    book = mo.build_book()
    series, rolls, macro = me._inputs()
    mine = me.legs_of(series, rolls, macro, cache={})
    return book, mine


# ── ① 재구성 등식 — 이 파일이 있는 이유 ─────────────────────────────────

def test_legs_match_the_lane(built):
    """다리 이름과 개수가 그 레인의 북과 같다."""
    book, mine = built
    assert [leg["key"] for leg in book["legs"]] == list(mine)


def test_cards_match_the_lane(built):
    """**내 계열로 다시 낸 카드 = 그 레인의 카드.**

    한 지표만 보면 우연히 맞을 수 있어서 넷을 본다. 반올림 자리까지 그 레인의
    `_card` 를 그대로 부르므로 정확히 같아야 한다 — 근사 비교가 아니다.
    """
    book, mine = built
    for leg in book["legs"]:
        got = mo._card(mine[leg["key"]])
        for k in ("sharpe", "calmar", "maxDrawdown", "ulcer"):
            assert got[k] == leg["card"][k], f"{leg['key']} 의 {k} 가 어긋났어요"


def test_window_matches_the_lane(built):
    """표본 창(시작·끝)이 그 레인이 응답에 적는 창과 같다."""
    book, mine = built
    w = book["window"]
    for key, pts in mine.items():
        assert pts[0]["t"] == w["start"], f"{key} 의 시작이 달라요"
        assert pts[-1]["t"] == w["end"], f"{key} 의 끝이 달라요"


# ── ② 동결 규율 — 채점 구간을 안 본다 ───────────────────────────────────

def test_nothing_after_freeze(built):
    """동결일 뒤의 봉이 **한 개도** 안 실린다.

    엔진은 오늘까지 그리므로 자르는 것은 이 자리의 책임이다. 사전등록이
    「판정일까지 들여다보지 말 것」이라고 못박은 그 구간이다.
    """
    _book, mine = built
    for key, pts in mine.items():
        assert pts, f"{key} 가 비었어요"
        assert max(p["t"] for p in pts) <= mo.FREEZE, f"{key} 가 동결일을 넘겼어요"


def test_cut_drops_post_freeze_bars():
    """`_cut` 자체가 동결일 뒤를 버린다 — 엔진 없이 직접 잰다."""
    pts = [{"t": "2026-09-07"}, {"t": mo.FREEZE}, {"t": "2026-09-09"}]
    assert [p["t"] for p in me._cut(pts, None)] == ["2026-09-07", mo.FREEZE]
    assert [p["t"] for p in me._cut(pts, mo.FREEZE)] == [mo.FREEZE]


# ── ③ 칸 계획 — 죽은 축을 세우지 않는다 ─────────────────────────────────

def test_cells_shapes():
    """추세·50/50 은 아홉 칸, 매크로는 셋(모듈 머리의 그 표)."""
    assert len(me.cells_for("trend")) == 9
    assert len(me.cells_for("blend")) == 9
    assert len(me.cells_for("macro")) == 3


def test_macro_leg_signal_axis_is_inert(built):
    """**매크로 다리에서 신호 축이 정말 죽는가** — 추측이 아니라 잰다.

    `book_simulate` 의 머리 주석이 「`external_signals` 가 `signal` 을 대신한다」
    고 적고 있고, 이 자리는 그 말을 믿고 매크로의 칸을 셋으로 줄였다. 믿은 값이
    사실인지를 여기서 확인한다 — 아니면 PBO 가 재는 것이 달라진다.
    """
    series, rolls, macro = me._inputs()
    if macro is None:
        pytest.skip("매크로 신호 파일이 없어요")
    a = me.legs_of(series, rolls, macro, signal="tsmom", cache={})["macro"]
    b = me.legs_of(series, rolls, macro, signal="donchian", cache={})["macro"]
    assert [p["t"] for p in a] == [p["t"] for p in b]
    assert all(x["dailyPnl"] == y["dailyPnl"] for x, y in zip(a, b))


def test_trend_leg_signal_axis_is_live(built):
    """반대쪽도 잰다 — 추세 다리에서는 신호를 갈면 **실제로 달라진다.**

    앞 시험만 있으면 「엔진이 신호를 통째로 무시한다」와 구별이 안 된다.
    """
    series, rolls, macro = me._inputs()
    a = me.legs_of(series, rolls, macro, signal="tsmom", cache={})["trend"]
    b = me.legs_of(series, rolls, macro, signal="donchian", cache={})["trend"]
    assert any(x["dailyPnl"] != y["dailyPnl"] for x, y in zip(a, b))


# ── ④ 그 레인의 축과 안 갈렸나 ──────────────────────────────────────────

def test_vol_windows_match_the_lane():
    """볼 윈도 셋이 그 레인의 `cta_validate.VOL_WINDOWS` 와 같다.

    여기 다시 적어 둔 값이라 그쪽이 축을 바꾸면 조용히 어긋난다. 그 파일이 아직
    없으면 건너뛴다 — 없는 것을 통과로 두지 않는다.
    """
    cv = pytest.importorskip("scripts.cta_validate",
                             reason="그 레인의 검증 스크립트가 아직 없어요")
    assert tuple(me.VOL_WINDOWS) == tuple(cv.VOL_WINDOWS)


def test_trials_counts_only_searched_axes():
    """N 은 신호계 × 볼 윈도 × 다리 구성 — **룩백은 안 센다.**

    그 레인의 규율이 「룩백을 고르지 마라」이고 실제로 다섯을 등가중 평균한다.
    고르지 않은 축이 N 에 들어가면 SR0 와 PBO 가 없는 자유도로 벌한다.
    """
    from app import ctabacktest as cta
    assert me.TRIALS == len(cta.SIGNALS) * len(me.VOL_WINDOWS) * me.LEG_FORMS
    assert me.TRIALS % len(mo.LOOKBACKS) != 0 or len(mo.LOOKBACKS) == 1, (
        "룩백이 N 에 곱해져 있지 않은지 확인하세요")


# ── ⑤ 수익 계열은 원(₩) 그대로 — 자본 분모를 안 만든다 ──────────────────

def test_returns_are_raw_krw(built):
    """계열이 봉의 손익 그대로다(나누지 않는다) [OWNER 2026-09-09]."""
    _book, mine = built
    pts = mine["trend"]
    r = me.returns_of(pts)
    assert len(r) == len(pts)
    assert r.iloc[0] == pts[0]["dailyPnl"]
    assert list(r.index[:3]) == [p["t"] for p in pts[:3]]


def test_layer_is_scale_invariant_on_this_series(built):
    """그래서 **원 계열로 넣어도** 게이트·순위가 안 바뀐다.

    이 성질이 2026-09-09 에 실제로 깨져 있었다(`vol_normalize` 워밍업). 이 레인이
    자본 분모를 안 만들기로 한 결정이 그 위에 서 있으므로 여기서도 잰다.
    """
    from evaluation import metrics as ev

    _book, mine = built
    r = me.returns_of(mine["blend"]).reset_index(drop=True)
    base = ev.cdar_ratio(ev.vol_normalize(r)[0])["cdar_ratio"]
    for c in (1e-6, 1e3):
        got = ev.cdar_ratio(ev.vol_normalize(r * c)[0])["cdar_ratio"]
        assert math.isclose(got, base, rel_tol=1e-9), f"배율 {c} 에서 갈렸어요"
