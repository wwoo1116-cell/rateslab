# -*- coding: utf-8 -*-
"""`scripts/why_irs` — 분해가 조용히 거짓말할 수 있는 자리를 잰다.

① **항등식** — IRS = KTB + 스왑스프레드. 부호 하나 뒤집으면 표 전체가 딴 말이
   된다(첫 판이 실제로 그랬고, 잔차 검사가 잡았다).
② **분산비** — 임의보행이면 1, 추세면 >1, 평균회귀면 <1. 셋을 심어서 잰다.
③ **짝짓기** — ΔVR 의 구간은 두 계열을 «같은 블록» 으로 뽑아야 뜻이 있다.
④ **부호 규약** — 계열이 전부 «−bp» 여야 「금리가 내리면 번다」가 성립한다.
"""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("app.momentum", reason="모멘텀 레인이 이 트리에 없어요")

from scripts import why_irs as w                     # noqa: E402


# ── ② 분산비 ────────────────────────────────────────────────────────────

def test_vr_of_a_random_walk_is_about_one():
    rng = np.random.default_rng(0)
    x = np.concatenate(([0.0], np.cumsum(rng.normal(0, 1, 20000))))
    assert w._vr(x, 20) == pytest.approx(1.0, abs=0.15)


def test_a_constant_drift_does_not_move_vr():
    """★VR 은 «드리프트» 를 안 본다 — 분산이 평균을 이미 뺀다.

    이걸 헷갈리면 VR>1 을 「수익률이 양수다」로 읽게 된다. VR 이 재는 것은
    **증분의 자기상관**이고, 그래서 이 층에서 「추세를 그린다」의 뜻이 된다.
    """
    rng = np.random.default_rng(1)
    d = rng.normal(0.0, 1.0, 20000)
    flat = np.concatenate(([0.0], np.cumsum(d)))
    drift = np.concatenate(([0.0], np.cumsum(d + 0.15)))
    assert w._vr(drift, 60) == pytest.approx(w._vr(flat, 60), abs=1e-9)


def test_vr_of_positively_autocorrelated_increments_is_above_one():
    """증분이 양의 자기상관이면 q 가 커질수록 VR 이 커진다 — 이게 «추세»다."""
    rng = np.random.default_rng(1)
    e = rng.normal(0, 1, 40000)
    d = np.empty_like(e)
    d[0] = e[0]
    for i in range(1, len(e)):
        d[i] = 0.3 * d[i - 1] + e[i]
    x = np.concatenate(([0.0], np.cumsum(d)))
    assert w._vr(x, 60) > w._vr(x, 5) > 1.0


def test_vr_of_a_mean_reverting_series_is_below_one():
    """AR(1) 음수 — 되돌리는 계열은 q일 분산이 q 배만큼 안 큰다."""
    rng = np.random.default_rng(2)
    e = rng.normal(0, 1, 20000)
    d = np.empty_like(e)
    d[0] = e[0]
    for i in range(1, len(e)):
        d[i] = -0.4 * d[i - 1] + e[i]
    x = np.concatenate(([0.0], np.cumsum(d)))
    assert w._vr(x, 20) < 0.8


def test_vr_is_scale_free():
    """계열이 bp 든 가격포인트든 같은 수가 나와야 나란히 놓을 수 있다."""
    rng = np.random.default_rng(3)
    x = np.concatenate(([0.0], np.cumsum(rng.normal(0, 1, 3000))))
    assert w._vr(x, 20) == pytest.approx(w._vr(x * 137.0, 20))


# ── ③ 짝짓기 ────────────────────────────────────────────────────────────

def test_paired_vr_of_a_series_with_itself_is_zero():
    """같은 계열끼리면 ΔVR 구간이 정확히 0 이다 — 블록을 따로 뽑으면 안 나온다."""
    rng = np.random.default_rng(4)
    x = np.concatenate(([0.0], np.cumsum(rng.normal(0, 1, 2000))))
    d = w._vr_paired(x, x, 20, n=40, block=63)
    assert d["lo"] == pytest.approx(0.0)
    assert d["hi"] == pytest.approx(0.0)


def test_paired_vr_finds_a_planted_difference():
    """한쪽에만 고주파 잡음을 얹으면 그쪽 VR 이 내려간다 — 차이가 잡혀야 한다."""
    rng = np.random.default_rng(5)
    d = rng.normal(0, 1, 4000)
    clean = np.concatenate(([0.0], np.cumsum(d)))
    noisy = clean + rng.normal(0, 1.5, clean.size)      # 되돌리는 잡음
    got = w._vr_paired(clean, noisy, 20, n=100, block=63)
    assert got["lo"] > 0, "잡음 얹은 쪽이 더 추세로 나오면 셈이 틀린 거예요"
    assert got["p"] < 0.05


# ── ④ 부호 규약 ─────────────────────────────────────────────────────────

def test_ktb_series_is_negative_bp():
    """국고채 금리는 «−bp» 로 들어와야 IRS 계열과 같은 부호 규약이다."""
    try:
        ktb = w.load_ktb_bp()
    except SystemExit as exc:                                  # noqa: BLE001
        pytest.skip(f"국고채 계열이 없어요 — {exc}")
    for t in w.TENORS:
        vals = list(ktb[t].values())
        assert vals, f"{t} 가 비었어요"
        assert max(vals) < 0, f"{t} 가 양수예요 — 부호 규약이 뒤집혔어요"
        assert min(vals) > -2000, f"{t} 의 크기가 bp 가 아니에요"


def test_ktb_dates_are_iso():
    try:
        ktb = w.load_ktb_bp()
    except SystemExit as exc:                                  # noqa: BLE001
        pytest.skip(f"국고채 계열이 없어요 — {exc}")
    for t in w.TENORS:
        d = next(iter(ktb[t]))
        assert len(d) == 10 and d[4] == "-" and d[7] == "-"


# ── ① 항등식 ────────────────────────────────────────────────────────────

def test_apply_is_additive_over_price_pieces():
    """같은 포지션을 두 조각에 걸어 더하면 합친 조각에 건 것과 같다.

    ②의 「금리 몫 + 스프레드 몫 = 전체」가 이 성질 위에 서 있다. 조각을 잘못
    잡으면 여기서는 안 걸리고 **실제 계열의 잔차**에서만 걸린다 — 그래서 그
    스크립트가 잔차를 출력한다.
    """
    n = 50
    pos = {t: list(np.linspace(-100.0, 100.0, n)) for t in w.TENORS}
    rng = np.random.default_rng(6)
    a = {t: rng.normal(0, 1, n) for t in w.TENORS}
    b = {t: rng.normal(0, 1, n) for t in w.TENORS}
    both = {t: a[t] + b[t] for t in w.TENORS}
    assert np.allclose(w._apply(pos, both),
                       w._apply(pos, a) + w._apply(pos, b))


def test_apply_uses_yesterdays_position():
    """오늘 가격변화에는 **어제** 포지션이 걸린다 — 하루 어긋나면 룩어헤드다."""
    pos = {t: [0.0, 10.0, 0.0] for t in w.TENORS}
    dp = {t: np.array([0.0, 0.0, 7.0]) for t in w.TENORS}
    got = w._apply(pos, dp)
    assert got[1] == 0.0
    assert got[2] == pytest.approx(len(w.TENORS) * 10.0 / 100.0 * 7.0)


def test_vr_horizons_cover_the_lookback_bundle():
    """분산비를 재는 지평이 이 북의 룩백 다발을 감싸야 뜻이 있다."""
    from app import momentum as mo
    assert min(w.VR_Q) <= min(mo.LOOKBACKS)
    assert max(w.VR_Q) >= max(mo.LOOKBACKS)


# ── ⑥ 선후 관계 ─────────────────────────────────────────────────────────

def test_xcorr_lag_sign_is_not_flipped():
    """b 가 a 를 **하루 늦게** 따라가면 corr(a_t, b_(t+1)) 이 커야 한다.

    부호를 헷갈리면 「현물이 선물을 따라간다」와 그 반대가 뒤집힌다 — 그 한 칸이
    「비동시 마감이다/아니다」를 가르는 자리다.
    """
    rng = np.random.default_rng(7)
    a = rng.normal(0, 1, 3000)
    b = np.concatenate(([0.0], a[:-1]))          # b 는 a 의 하루 지연
    assert w._xcorr(a, b, 1) > 0.9
    assert abs(w._xcorr(a, b, 0)) < 0.1
    assert abs(w._xcorr(a, b, -1)) < 0.1


def test_xcorr_at_zero_is_plain_correlation():
    rng = np.random.default_rng(8)
    a = rng.normal(0, 1, 500)
    b = a * 2.0 + rng.normal(0, 0.1, 500)
    assert w._xcorr(a, b, 0) == pytest.approx(float(np.corrcoef(a, b)[0, 1]))


def test_krw_bond_futures_have_no_ctd_note_is_pinned():
    """★[OWNER 2026-09-10] 원화 국채선물은 현금결제라 CTD 가 없다.

    이 사실을 모듈 머리에 못 박아 둔다 — 다음 세션이 미국 국채선물의 인도 옵션을
    다시 옮겨 적지 않도록. 문서가 지워지면 이 시험이 깨진다.
    """
    doc = w.__doc__ or ""
    assert "CTD 가 없다" in doc
    assert "현금결제" in doc
