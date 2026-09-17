# -*- coding: utf-8 -*-
"""⑨ W4 여력의 분모 — 「평균회귀가 그날 쓴 증거금」이 어디서 오나.

2026-09-15 까지 이 수는 **이 리포가 다시 시뮬레이션한 규칙 A**(균등 로트)였다.
그 레인이 실제로 굴리는 것은 규칙 B(효율가중)라, 같은 날의 여력이 52.31억과
4.63억으로 갈렸다. 2026-09-16 에 그 자리를 그 레인의 배분기 하나로 모았다
(`data/krw-crs/src/margin_headroom.py`).

조용히 거짓말할 수 있는 자리 넷을 잰다.

① **재현** — 새 배분기가 `alloc_grid` 의 규칙 B 를 그대로 내야 한다. 안 그러면
   그건 옮긴 것이 아니라 **새 규칙**이고, 시행수를 하나 더 쓴다.
② **한 번뿐인 진입** — 진입일에 예산이 없어 막힌 다리는 뒤에 예산이 풀려도
   들어가지 않는다. 다시 시도하게 만들면 그게 곧 다른 규칙이다.
③ **라이브 규약이 증거금을 더 푸는 일은 없다** — 적재가 멈춘 다리의 증거금을
   증권사가 돌려주지 않는다는 것이 이 규약의 전부다.
④ **항등식** — 묶인 것 + 여력 = 상한.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

sm = pytest.importorskip("scripts.sleeve_monitor",
                         reason="원천(그 레인·MySQL)이 없으면 건너뛴다")

mh = sm._allocator()
if mh is None:
    pytest.skip("배분기(margin_headroom)가 없는 환경", allow_module_level=True)


@pytest.fixture(scope="module")
def panel():
    return mh.panel()


def test_replay_reproduces_the_lane_rule_b(panel):
    """① 새 배분기(등록 규약·all9)가 `alloc_grid` 규칙 B 와 **비트 동일**이어야 한다."""
    import alloc_grid as ag                                  # noqa: PLC0415
    import margin_budget_book as mb                          # noqa: PLC0415

    P0, L0, Z0, meta0 = mb.load()
    rules, _eff = ag.rules(meta0)
    _daily, used, _en, _bl = ag.simulate(P0, L0, Z0, meta0,
                                         mh.LOT_UK * 1e8, rules["B 효율가중"])
    theirs = pd.Series(used.to_numpy(dtype=float) * mh.CAP,
                       index=[str(t)[:10] for t in used.index])

    P, Z, meta, _asof = panel
    mine = mh.replay(P, Z, meta, "registered", mh.LOT_UK, norm="all9")["used"]

    common = sorted(set(theirs.index) & set(mine.index))
    assert len(common) == len(theirs) == len(mine)
    assert float((theirs.loc[common] - mine.loc[common]).abs().max()) < 1.0


def test_identity_used_plus_headroom_is_the_cap(panel):
    """④ 묶인 것 + 여력 = 100억. 어느 규약에서나."""
    P, Z, meta, _asof = panel
    for convention in mh.CONVENTIONS:
        D = mh.replay(P, Z, meta, convention, mh.LOT_UK)
        assert float((D["used"] + D["headroom"] - mh.CAP).abs().max()) < 1.0
        assert float(D["used"].min()) >= -1.0
        assert float(D["used"].max()) <= mh.CAP + 1.0


def test_live_never_frees_more_than_registered(panel):
    """③ 라이브 규약이 등록 규약보다 증거금을 **덜 묶는 날이 없어야** 한다."""
    P, Z, meta, _asof = panel
    live = mh.replay(P, Z, meta, "live", mh.LOT_UK)["used"]
    reg = mh.replay(P, Z, meta, "registered", mh.LOT_UK)["used"]
    assert float((reg - live).max()) < 1.0


def _synthetic():
    """다리 셋만 사는 작은 판 — 효율을 같게 놓아 가중이 전부 1.0 이 되게 한다."""
    days = pd.to_datetime([f"2026-01-{i:02d}" for i in (5, 6, 7, 8, 9)])
    pv01 = {t: (10.0 if mh.MARGIN[t] == .10 else 5.0) for t in mh.T}   # eff 를 동일하게
    meta = {t: {"pv01": pv01[t], "base_face": 1e10, "open": None} for t in mh.T}
    pos = pd.DataFrame(np.nan, index=days, columns=mh.T)
    z = pd.DataFrame(0.0, index=days, columns=mh.T)
    #          1/5  1/6  1/7  1/8  1/9
    pos["1Y"] = [-1, -1, -1, 0, 0]        # 첫날 진입, 1/8 청산 → 예산이 풀린다
    pos["2Y"] = [0, -1, -1, -1, -1]       # 둘째 날 진입
    pos["3Y"] = [0, 0, -1, -1, -1]        # 셋째 날 진입 — 예산이 없어 **막힌다**
    return pos, z, meta


def test_a_blocked_entry_does_not_come_back(panel):
    """② 진입일에 막힌 다리는 예산이 풀려도 **다시 들어가지 않는다**."""
    pos, z, meta = _synthetic()
    D = mh.replay(pos, z, meta, "live", mh.LOT_UK)
    assert float(D.iloc[0]["mg_1Y"]) == pytest.approx(50e8)
    assert float(D.iloc[1]["mg_2Y"]) == pytest.approx(50e8)
    assert float(D.iloc[2]["mg_3Y"]) == 0.0        # 예산 0 → 막힘
    assert int(D.iloc[2]["blocked"]) == 1
    assert float(D.iloc[3]["headroom"]) == pytest.approx(50e8)   # 1Y 청산으로 풀린 예산
    assert float(D.iloc[3]["mg_3Y"]) == 0.0       # ★풀려도 안 들어간다
    assert float(D.iloc[4]["mg_3Y"]) == 0.0


def test_stale_leg_keeps_its_margin_under_live():
    """③의 본체 — 자료가 끊긴 다리는 라이브 규약에서 증거금을 그대로 묶고 있다."""
    pos, z, meta = _synthetic()
    pos.loc[pos.index[2:], "1Y"] = np.nan        # 1/7 부터 적재 중단(청산이 아니다)
    live = mh.replay(pos, z, meta, "live", mh.LOT_UK)
    reg = mh.replay(pos, z, meta, "registered", mh.LOT_UK)
    assert float(live.iloc[-1]["mg_1Y"]) == pytest.approx(50e8)
    assert float(reg.iloc[-1]["mg_1Y"]) == 0.0
    assert int(live.iloc[-1]["stale_held"]) == 1


def test_margin_path_is_in_won_and_under_the_cap():
    """슬리브가 부르는 자리 — 단위가 원이고 상한 아래여야 한다."""
    margin, src = sm.mr_margin_path("allocator")
    assert src["source"] == "allocator"
    assert src["rule"].startswith("B")
    assert len(margin) > 1000
    assert 0.0 <= float(margin.min()) and float(margin.max()) <= mh.CAP + 1.0
