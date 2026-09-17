# -*- coding: utf-8 -*-
"""동결 벽을 두 등록이 공유하지 않게 한 자리 — 그 갈래가 조용히 새지 않는가 [2026-09-17].

09-16 까지 `momentum_irs_evaluate.load_irs_series()` 는 `app/momentum.py` 의
`FREEZE = "2026-09-08"` 하나로 잘렸다. 그 상수는 **09-08 매크로 등록의 벽**인데
IRS 슬리브(09-15 동결 · 09-16 채점)의 집행 경로도 같은 함수를 지나서, 슬리브는
채점 봉을 원리상 한 개도 못 쌓고 있었다 — `sleeve_daily` 의
`scored = d > FREEZE_DATE(09-15)` 가 영원히 거짓이었다.

여기서 재는 것은 넷이다.

① **비트 동일** — 기본 호출은 예전과 한 행도 다르면 안 된다. 다르면 이건 「옮긴 것」이
   아니라 새 규칙이고 시행수를 하나 더 쓴다(인계문 §10-9).
② **갈래가 실제로 열린다** — `end=None` 이 동결일 너머를 실제로 낸다.
③ **캐시가 창을 섞지 않는다** — 먼저 부른 쪽의 창이 뒤에 부른 쪽에 나가면 안 된다
   (`_RUNS` 캐시 키가 원천을 안 봐서 다른 북이 재사용됐던 그 결함과 같은 자리).
④ **크기 상수는 동결일 값이다** — 옆 레인 적재가 이 레인의 표를 못 움직인다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

mie = pytest.importorskip("scripts.momentum_irs_evaluate",
                          reason="원천(MySQL)이 없으면 건너뛴다")
sm = pytest.importorskip("scripts.sleeve_monitor",
                         reason="원천(그 레인·MySQL)이 없으면 건너뛴다")

from app import momentum as mo  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]

#: 갈래를 내기 **전** 이 함수가 내던 창. 손으로 적은 수가 아니라 09-17 실측이고,
#: 이 둘이 흔들리면 09-08 등록의 모든 표가 같이 흔들린다.
FROZEN_FIRST, FROZEN_LAST, FROZEN_N = "2017-01-06", "2026-09-08", 2389


@pytest.fixture(scope="module")
def frozen():
    try:
        return mie.load_irs_series()
    except Exception as e:                      # noqa: BLE001 — DB 없는 환경
        pytest.skip(f"IRS 계열을 못 읽었다: {e}")


def test_default_call_is_bit_identical(frozen):
    """① 기본 호출 = 09-08 등록의 창. 한 행도 안 움직인다."""
    days = frozen["3Y"][0]
    assert (days[0], days[-1], len(days)) == (FROZEN_FIRST, FROZEN_LAST, FROZEN_N)
    assert days[-1] == mo.FREEZE, "기본값이 09-08 등록의 벽에서 떨어졌다"
    assert frozen["10Y"][0] == days, "두 만기가 같은 달력 위에 있어야 한다"
    assert len(frozen["3Y"][1]) == len(days) == len(frozen["10Y"][1])


def test_live_branch_actually_opens(frozen):
    """② `end=None` 은 동결일 **너머**를 낸다 — 이게 안 되면 채점 봉이 영영 0 이다."""
    live = mie.load_irs_series(end=None)
    fd, ld = frozen["3Y"][0], live["3Y"][0]
    assert len(ld) >= len(fd)
    assert ld[-1] >= mo.FREEZE
    #: 동결 창과 겹치는 부분은 **값까지 같아야 한다** — 창을 늘렸다고 과거가 바뀌면
    #: 그건 인과적이지 않은 계열이라는 뜻이다.
    assert ld[:len(fd)] == fd
    assert live["3Y"][1][:len(fd)] == frozen["3Y"][1]
    assert live["10Y"][1][:len(fd)] == frozen["10Y"][1]


def test_cache_key_separates_the_windows(frozen):
    """③ 캐시가 두 창을 섞지 않는다."""
    live = mie.load_irs_series(end=None)
    again = mie.load_irs_series()
    assert again["3Y"][0][-1] == mo.FREEZE
    assert len(again["3Y"][0]) == FROZEN_N
    if len(live["3Y"][0]) > FROZEN_N:
        assert live["3Y"][0][-1] != again["3Y"][0][-1]


def test_sizing_constants_are_the_frozen_day_values():
    """④ 크기 셋은 **동결일에 기록된 값**이다 — 반올림한 등록서 표기가 아니라."""
    state = json.loads((BACKEND / "output" / "sleeve_monitor_state.json")
                       .read_text(encoding="utf-8"))
    first = next(e for e in state["log"] if e["run"] == "2026-09-15")["daily"]
    assert sm.K_MR_REGISTERED == first["k_mr"]
    assert sm.K_TR_REGISTERED == first["k_tr"]

    led = json.loads((BACKEND / "output" / "sleeve_daily_ledger.json")
                     .read_text(encoding="utf-8"))
    frozen_run = next(r for r in led["rows"] if r["run"] == "2026-09-15")
    assert sm.MULT_REGISTERED == frozen_run["mult"]

    #: 등록서가 적어 둔 반올림 표기와도 맞아야 한다(§3 「11.89배」 · W4 0.954/0.318).
    assert round(sm.MULT_REGISTERED, 2) == 11.89
    assert round(sm.K_MR_REGISTERED, 3) == 0.954
    assert round(sm.K_TR_REGISTERED, 3) == 0.318


def test_execution_uses_the_registered_multiple_not_todays():
    """④-b 집행 경로가 **등록 배수**를 쓰고, 오늘 다시 센 값은 대조로만 들고 간다."""
    from scripts import sleeve_execution as se               # noqa: PLC0415

    try:
        _per, _net, meta = se.sleeve_dv01_path()
    except Exception as e:                                   # noqa: BLE001
        pytest.skip(f"집행 경로를 못 돌렸다: {e}")
    assert meta["mult"] == sm.MULT_REGISTERED
    assert meta["k_mr"] == sm.K_MR_REGISTERED
    assert meta["k_tr"] == sm.K_TR_REGISTERED
    assert "mult_live" in meta and "k_mr_live" in meta
