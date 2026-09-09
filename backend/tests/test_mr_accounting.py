# -*- coding: utf-8 -*-
"""회계 정직성 — 화면이 **자기 회계를 말하는가** [krw-crs 레인 2026-09-09].

MR 엔진은 «언제»만 정하고 «얼마»는 `_mr_real_accounting` 이 실가격 자산스왑으로
다시 센다. 그 함수는 **못 재면 조용히 엔진 근사로 되돌린다** — 그래서 화면이 그
사실을 말해야 하고, 되돌아가는 조건이 «사고» 여서는 안 된다.

이 파일이 지키는 것 넷.
  ① **통합 장부가 회계를 말한다** — 불리언 하나가 아니라 «몇/몇 + 어느 다리».
     섞였을 때 「근사」로 뭉뚱그리면 8/9 와 0/9 가 같은 말이 된다.
  ② **실패를 캐시하지 않는다.** 종전에는 DB 가 한 번 버벅이면 그 거래창이
     재시작 전까지 근사로 묶였다(레인 실측: 162칸 중 87칸이 뒤집혔다). 결정적
     실패(창이 잘렸다)만 붙들고, 예외는 다음 요청이 다시 잰다.
  ③ **창이 둘이다** — 회계 경로는 전 구간(`max_days=None`), 서빙 경로는 상수.
     그리고 그 창이 **캐시 열쇠에 든다**(안 넣으면 화면이 채운 절단 캐시를 회계가
     받아 창을 가른 것이 아무 일도 안 한다 — `with_legs` 가 열쇠에 든 그 이유).
  ④ **조달 원금 = 매수금액**이고, 이 모형에서 그것은 정확히 액면이다(진입일 par).
"""
import datetime as dt

import pytest

from app import cashbond as cb
from app import mrbook


# ── ① 통합 장부가 회계를 말한다 ─────────────────────────────────────────────

def _leg(sid: str, real):
    """`aggregate` 가 먹는 최소한의 다리 — 회계 칸만 보는 시험이라 봉은 하나다."""
    pts = [{"date": "2026-01-02", "value": 1.0, "z": None, "position": 0, "hold": 0,
            "dailyPnl": 0.0, "mtm": 0.0, "barCarry": 0.0, "barCost": 0.0,
            "tradePnl": 0.0, "out": 0, "outRun": 0, "cumulativePnl": 0.0}]
    leg = {"id": sid, "label": sid, "dates": ["2026-01-02"],
           "r": {"points": pts, "trades": [], "open": None,
                 "summary": {"totalPnl": 0.0, "maxDrawdown": 0.0, "winRate": None,
                             "sharpe": None, "numTrades": 0, "openPnl": None},
                 "blocked": {"spells": 0, "days": 0},
                 "gated": {"spells": 0, "days": 0}}}
    if real is not ...:
        leg["real"] = real
    return leg


def _agg(legs):
    return mrbook.aggregate(legs, notional=1e6, cost_bp=0.5, dynamic_cost=False)


def test_book_says_which_accounting_it_used():
    out = _agg([_leg("BSS-3Y", True), _leg("BSS-10Y", True)])
    assert out["accounting"] == {"real": 2, "total": 2, "approx": [], "unknown": []}
    assert [lg["real"] for lg in out["legs"]] == [True, True]


def test_mixed_book_names_the_approximated_leg():
    """**8/9 와 0/9 가 같은 말이 되면 안 된다** — 센 수와 이름을 같이 낸다."""
    out = _agg([_leg("BSS-3Y", True), _leg("BSS-2Y", False), _leg("BSS-10Y", True)])
    assert out["accounting"]["real"] == 2 and out["accounting"]["total"] == 3
    assert out["accounting"]["approx"] == ["BSS-2Y"]


def test_unknown_is_not_counted_as_approximate():
    """회계를 **안 말한** 다리를 근사로 세면 화면이 없는 사실을 말하게 된다."""
    out = _agg([_leg("BSS-3Y", ...), _leg("BSS-10Y", True)])
    assert out["accounting"] == {"real": 1, "total": 2,
                                 "approx": [], "unknown": ["BSS-3Y"]}


# ── ③ 창이 둘이다 ───────────────────────────────────────────────────────────

def test_book_recon_window_is_a_parameter_and_defaults_to_the_constant():
    """상수는 **서빙**의 값이고, 회계는 `None`(전 구간)으로 부른다.

    상수를 올리는 대신 창을 가른 이유는 비용이다 — 화면 경로(`with_legs=True`)가
    회계 경로의 6배라(최장 거래 7,282ms 대 1,247ms) 상수를 올리면 페이로드와
    응답시간이 같이 커진다(`cashbond.RECON_MAX_DAYS` 머리의 실측).
    """
    import inspect

    sig = inspect.signature(cb.book_recon)
    assert sig.parameters["max_days"].default == cb.RECON_MAX_DAYS
    assert cb.RECON_MAX_DAYS == 250          # 서빙 창은 안 바뀐다
    src = inspect.getsource(cb.book_recon)
    assert "start = first if max_days is None" in src


def test_accounting_path_asks_for_the_whole_window():
    """`_mr_real_accounting` 은 잘린 창을 받으면 그 다리를 통째로 근사로 되돌린다.
    그래서 **그 경로만** 전 구간을 부른다."""
    import inspect

    from app import main as m

    src = inspect.getsource(m._mr_real_accounting)
    assert "max_days=None" in src


def test_window_is_in_the_cache_key():
    """안 넣으면 화면이 채운 **절단 캐시**를 회계가 받아 창을 가른 것이 아무 일도
    안 한다 — `with_legs` 를 열쇠에 넣은 것과 정확히 같은 이유다."""
    import inspect

    from app import main as m

    src = inspect.getsource(m._mr_recon_rows)
    key = src[src.index("key = ("):src.index("if key in _mr_recon_cache")]
    for part in ("with_legs", "max_days"):
        assert part in key, f"{part} 가 캐시 열쇠에 없다"


# ── ② 실패를 캐시하지 않는다 ───────────────────────────────────────────────

class _FakeMatrix:
    watermark = "wm"


def _clear(m):
    m._mr_recon_cache.clear()


def test_transient_failure_is_retried_not_frozen(monkeypatch):
    """예외로 못 잰 자리는 **다음 요청이 다시 재 본다**.

    종전에는 `None` 을 영구히 붙들어서, DB 가 한 번 흔들리면 재시작 전까지 그
    거래창이 근사로 묶였다 — 사용자에게는 「같은 화면인데 열 때마다 손익이 다르다」
    로 보인다(레인 실측: 87칸이 뒤집혔다).
    """
    from app import main as m

    _clear(m)
    calls = {"n": 0}

    def flaky(*_a, **_kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise cb.CashBondError("DB 가 흔들렸다")
        return {"tenors": ["3Y"], "rows": [{"t": "2026-01-02"}], "truncated": False}

    monkeypatch.setattr(cb, "book_recon", flaky)
    spec = type("S", (), {"basis": "base", "spread_bp": 10.0})()
    args = (_FakeMatrix(), "3Y", dt.date(2026, 1, 2), dt.date(2026, 2, 2), -1, spec)

    assert m._mr_recon_rows(*args) is None            # 첫 판: 실패
    got = m._mr_recon_rows(*args)                     # 둘째 판: 다시 잰다
    assert got is not None and calls["n"] == 2
    _clear(m)


def test_deterministic_truncation_is_cached(monkeypatch):
    """**창이 잘렸다**는 「못 잰다」가 아니라 잰 결과다 — 같은 자료면 늘 같은 답이라
    다시 재는 것이 값이 없다. 그래서 **이것만** 붙든다."""
    from app import main as m

    _clear(m)
    calls = {"n": 0}

    def truncating(*_a, **_kw):
        calls["n"] += 1
        return {"tenors": [], "rows": [], "truncated": True}

    monkeypatch.setattr(cb, "book_recon", truncating)
    spec = type("S", (), {"basis": "base", "spread_bp": 10.0})()
    args = (_FakeMatrix(), "3Y", dt.date(2026, 1, 2), dt.date(2026, 2, 2), -1, spec)

    assert m._mr_recon_rows(*args) is None
    assert m._mr_recon_rows(*args) is None
    assert calls["n"] == 1, "결정적 실패는 한 번만 잰다"
    _clear(m)


def test_failure_never_enters_the_cache(monkeypatch):
    """고장은 **다음 요청에 낫는다** — 붙드는 시간이 0 이다.

    TTL 을 두는 길도 있었지만(그러면 고장이 그 시간 안에 낫는다) 여기는 회계다:
    늘 실패하는 자리가 무는 것은 예외 하나의 값이고, 붙들었을 때 무는 것은 **틀린
    손익을 화면에 띄우는 값**이다.
    """
    from app import main as m

    _clear(m)
    def boom(*_a, **_kw):
        raise cb.CashBondError("자료 없음")

    monkeypatch.setattr(cb, "book_recon", boom)
    spec = type("S", (), {"basis": "base", "spread_bp": 10.0})()
    assert m._mr_recon_rows(_FakeMatrix(), "3Y", dt.date(2026, 1, 2),
                            dt.date(2026, 2, 2), -1, spec) is None
    assert not m._mr_recon_cache, "실패가 캐시에 들어갔다"


# ── ④ 조달 원금 = 매수금액 = 액면 ───────────────────────────────────────────

@pytest.mark.parametrize("y", [0.025, 0.0378, 0.05])
def test_entry_price_is_exactly_par_so_face_is_the_purchase_amount(y):
    """[OWNER 2026-09-09 — "실제로 Bond를 매입하는데 들어간 비용이 조달원금"].

    이 모형은 진입일에 쿠폰을 그날 수익률로 스트럭하는 **합성 par 채**라 매수금액이
    정확히 액면이다(연금 항등식). 그래서 `funding` 이 `pos.notional` 위에 서는 것이
    오너 규칙 그대로다 — krw-crs 레인이 올린 「할인채면 1% 과다 계상」은 **실제
    종목을 시장가로 사는 판**에서 살아나는 지적이고, 이 모형에는 할인채가 없다.
    """
    dirty, accrued, _cp, _rd = cb.price(y, y, 12, 0.0)
    assert dirty == pytest.approx(1.0, abs=1e-12)
    assert accrued == pytest.approx(0.0, abs=1e-12)
