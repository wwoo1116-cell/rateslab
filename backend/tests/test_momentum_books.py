# -*- coding: utf-8 -*-
"""논문 구조 거시 다리(북 넷)와 북 여럿 위약의 검정 [2026-09-15].

합성 자료로만 잰다 — 엔진을 안 돌린다. 재는 것:
  ① `placebo_multi` 는 북 하나·가중 1 이면 `rz.placebo` 와 같은 p 를 낸다
  ② 같은 북 둘을 반씩 섞으면 북 하나와 같다(선형)
  ③ `momentum_irs_books.signals` — 위험선호는 확장 평균 대비, 테마 하나가 비면 그날 전부 비운다
  ④ `momentum_irs_legs._ext_key` — 외부 신호의 **내용**이 다르면 키가 다르다
  ⑤ `metrics.evaluate` 사유줄 — 비용전 판만 깨져도 그 값을 적는다
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from evaluation import metrics as ev, randomization as rz
from scripts import momentum_irs_books as mib
from scripts import momentum_irs_legs as ml
from scripts.momentum_theme_books import placebo_multi


def _pl(n: int = 600, ticks: float = 0.0, seed: int = 0):
    rng = np.random.default_rng(seed)
    dates = [f"d{i:04d}" for i in range(n)]
    px = 100.0 + np.cumsum(rng.normal(0, 0.3, n))
    price = {"A": dict(zip(dates, px.tolist()))}
    return dates, price, rz.plumbing(dates, price, set(), ticks, 0.01), px


def _signal_pos(px: np.ndarray, n: int) -> dict:
    """내일 오르면 오늘 롱 — 일부러 «완벽한» 신호."""
    nxt = np.concatenate((np.sign(np.diff(px)), [0.0]))
    return {"A": (100.0 * nxt).tolist()}


# ── ①② 북 여럿 위약 ────────────────────────────────────────────────────

def test_placebo_multi_with_one_book_equals_placebo():
    dates, price, pl, px = _pl()
    pl_g = rz.plumbing(dates, price, set(), 0.0, 0.01)
    pos = _signal_pos(px, len(dates))
    mask = np.ones(len(dates), dtype=bool)
    single = rz.placebo(pl, pos, shift_min=50, mask=mask, pl_gross=pl_g)
    multi = placebo_multi(pl, pl_g, [(1.0, pos)], mask, 50)
    assert multi["p"] == pytest.approx(single["p"])
    assert multi["p_gross"] == pytest.approx(single["p_gross"])
    assert multi["real_sr"] == pytest.approx(single["real_sr"])
    assert multi["placebo_median"] == pytest.approx(single["placebo_median"])


def test_placebo_multi_is_linear_in_weights():
    dates, price, pl, px = _pl(ticks=20.0)
    pl_g = rz.plumbing(dates, price, set(), 0.0, 0.01)
    pos = _signal_pos(px, len(dates))
    mask = np.ones(len(dates), dtype=bool)
    one = placebo_multi(pl, pl_g, [(1.0, pos)], mask, 50)
    two = placebo_multi(pl, pl_g, [(0.5, pos), (0.5, pos)], mask, 50)
    assert two["p"] == pytest.approx(one["p"])
    assert two["real_sr"] == pytest.approx(one["real_sr"])


def test_placebo_multi_perfect_signal_gets_small_p():
    dates, price, pl, px = _pl()
    pl_g = rz.plumbing(dates, price, set(), 0.0, 0.01)
    pos = _signal_pos(px, len(dates))
    got = placebo_multi(pl, pl_g, [(0.5, pos), (0.5, pos)], np.ones(len(dates), dtype=bool), 50)
    assert got["p"] <= 0.05 and got["p_gross"] <= 0.05


# ── ③ 논문 구조 신호 ────────────────────────────────────────────────────

def _themes(n: int = 400, risk_last: float | None = None) -> pd.DataFrame:
    idx = pd.bdate_range("2020-01-01", periods=n)
    rng = np.random.default_rng(1)
    th = pd.DataFrame({
        "cycle_raw": rng.normal(0, 1, n), "policy_raw": rng.normal(0, 1, n),
        "trade_raw": rng.normal(0, 1, n),
        # risk_raw = −(주식 초과수익) 규약. 초과수익을 양(+)의 상수로 두면 확장 평균과 같아 부호 0 이어야 한다
        "risk_raw": np.full(n, -0.10),
    }, index=idx)
    if risk_last is not None:
        th.iloc[-1, th.columns.get_loc("risk_raw")] = -risk_last
    return th


def test_risk_sign_is_relative_to_expanding_mean_not_zero():
    th = _themes()
    sig = mib.signals(th)
    # 초과수익이 늘 +10% 면 0 대비로는 전부 숏(−1)이지만, 확장 평균 대비로는 0 이다
    r = sig["risk"]
    assert (r == 0).all()
    # 마지막 날만 초과수익이 평균보다 크면(+30%) → 위험선호 개선 → 국채 숏(−1)
    th2 = _themes(risk_last=0.30)
    assert mib.signals(th2)["risk"].iloc[-1] == -1
    # 마지막 날만 평균보다 작으면(−5%) → 국채 롱(+1)
    th3 = _themes(risk_last=-0.05)
    assert mib.signals(th3)["risk"].iloc[-1] == 1


def test_signals_drop_the_day_when_any_theme_is_missing():
    th = _themes()
    th.iloc[300, th.columns.get_loc("trade_raw")] = np.nan
    sig = mib.signals(th)
    day = th.index[300]
    for k in ("cycle", "policy", "trade", "risk"):
        assert day not in sig[k].index
    assert mib.start_of(sig) >= th.index[mib.MIN_MEAN - 1].strftime("%Y-%m-%d")


def test_other_themes_keep_plain_sign():
    th = _themes()
    sig = mib.signals(th)
    live = sig["cycle"].index
    assert np.array_equal(sig["cycle"].to_numpy(), np.sign(th.loc[live, "cycle_raw"]).to_numpy())
    assert np.array_equal(sig["policy"].to_numpy(), np.sign(th.loc[live, "policy_raw"]).to_numpy())


# ── ④ 캐시 키 ────────────────────────────────────────────────────────────

def test_ext_key_sees_signal_content():
    a = {"A": {"d1": 1.0, "d2": -1.0}}
    b = {"A": {"d1": 1.0, "d2": 1.0}}
    c = {"A": {"d2": -1.0, "d1": 1.0}}           # 같은 내용, 다른 순서
    assert ml._ext_key(None) is None
    assert ml._ext_key(a) == ml._ext_key(c)
    assert ml._ext_key(a) != ml._ext_key(b)


# ── ⑤ 사유줄 ─────────────────────────────────────────────────────────────

def test_reason_line_names_the_gross_placebo_when_that_is_what_fails():
    rng = np.random.default_rng(3)
    r = pd.Series(rng.normal(0.0004, 0.01, 1500))
    mat = pd.DataFrame({"a": r, "b": r * 0.9 + rng.normal(0, 0.002, 1500), "c": r * 1.1})
    placebo = {"p": 0.0105, "p_gross": 0.0842, "n_shifts": 189, "real_sr": 0.9, "beat": 1,
               "placebo_median": -0.2, "placebo_p95": 0.7, "sign_only": True, "why": None,
               "real_sr_gross": 1.0, "beat_gross": 15, "placebo_gross_median": -0.1, "placebo_gross_p95": 1.0}
    out = ev.evaluate(r, trials=72, is_oos_splits=16, configs=mat, sr_var=None,
                      strategy_id="test-reason", cost_bp_roundtrip=1.0, placebo=placebo, assumptions=["test"])
    text = json.dumps(out["gate"], ensure_ascii=False) + json.dumps(out.get("notes", ""), ensure_ascii=False)
    assert out["gate"]["overall_pass"] is False
    assert "0.0842" in text            # 깨진 판(비용전)의 값이 적혀 있어야 한다
