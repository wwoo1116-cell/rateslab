"""Shared fixtures.

Came over with the simulation. The frozen krw-fi-pms conftest was almost
entirely DB scaffolding — an in-memory SQLite engine, MySQL-only upsert shims,
a seeded tenor_pillar table. None of it applied to simulation_project, which
had no database, and none of it applies here yet either.

This is now the FIRST conftest in this backend: the monitor's own tests never
needed one (they run as `cd backend; python -m pytest tests -q`, and that is
what puts `backend/` on sys.path for `from app import ...` — unchanged, and
`irs_pricer` resolves the same way). The autouse fixture below therefore runs
for every test in this directory, monitor tests included. That is harmless —
the TTL cache it clears is the simulation's, and a monitor test that never
touches it clears an empty dict — but it is a real widening, so it is written
down rather than left to be discovered.
"""

from __future__ import annotations

import pytest

from app import futures as _futures_mod
from irs_pricer.core import ttl_cache
from irs_pricer.loaders import irsdata as _irsdata_loader
from irs_pricer.services.simulation import bond_roll


@pytest.fixture(autouse=True)
def futures_data_off():
    """선물 종가 주입본을 매 테스트 앞뒤에서 내린다 [2026-08-25].

    sql_snapshot_off 와 같은 규율: 주입이 없으면 `futures.load()` 는 SQL 로
    가므로, 결정적이어야 하는 테스트는 자기 페이크를 `set_data` 로 주입한 뒤
    이 픽스처가 되돌린다."""
    _futures_mod.set_data(None)
    yield
    _futures_mod.set_data(None)


@pytest.fixture(autouse=True)
def sql_snapshot_off():
    """시뮬 IRS 스냅샷의 주입 데이터셋을 매 테스트 앞에서 내린다 [2026-08-25].

    `with TestClient(app)` 가 lifespan 을 돌리면 app 이 병합(SQL 우선)
    데이터셋을 전역 주입한다 — 그 순간부터 스냅샷 골든이 «SQL 이 무엇을
    담고 있나»라는 환경 사실에 붙는다. bond_roll_lane_off 와 같은 규율:
    기본은 워크북(결정적), SQL 경로를 시험하는 테스트만 자기 페이크를 주입."""
    _irsdata_loader.set_dataset(None)
    yield
    _irsdata_loader.set_dataset(None)


@pytest.fixture(autouse=True)
def bond_roll_lane_off():
    """채권 롤다운 커브 공급자를 매 테스트 앞에서 내린다 [2026-08-25].

    공급자는 프로세스 전역이고, `with TestClient(app)` 가 lifespan 을 돌리면
    app 이 **실제 SQL 민평** 공급자를 등록한다 — 그 순간부터 골든·항등식
    테스트의 수치가 «SQL 이 닿는가» 라는 환경 사실에 붙는다. 여기서 매번
    내려 «롤 레인 꺼짐»을 결정적 기본으로 만들고, 롤 레인을 시험하는 테스트
    (test_simulate_mixed_recon)만 이 픽스처를 명시적으로 요청한 뒤 자기
    커브를 얹는다 — 요청 관계가 곧 실행 순서 보증이다.
    """
    bond_roll.set_sector_curve_provider(None)
    yield
    bond_roll.set_sector_curve_provider(None)


@pytest.fixture(autouse=True, scope="session")
def _offline_data_sources():
    """시험은 **망을 안 때리고 추적되는 원자료를 다시 쓰지 않는다** [2026-09-15].

    `bigfoot/data/ecos.py` 는 받아온 응답을 `backend/data/raw/bigfoot_*.csv` 에
    캐시로 쓴다. 값은 같아도 행마다 박힌 `retrieved_at` 이 갈려서 **전 행이 diff 로
    뜨고**, 그 파일들은 git 이 추적한다. 실측: 전체 시험을 한 번 돌리면 열넷이
    통째로 다시 쓰였다.

    `test_rebake.py` 는 이미 호출마다 `offline=True` 를 넘겨 이 자리를 막고 있었다.
    여기서 **세션 전체**로 넓힌다 — 새 시험이 로더를 부를 때마다 같은 사고가 나는
    것을 막는 편이 호출부마다 기억하는 것보다 싸다. 덤으로 통과 여부가 망 상태에
    안 달린다.

    ⚠ 일부러 온라인을 재야 하는 시험은 `monkeypatch.delenv("BIGFOOT_OFFLINE")` 로
    그 시험 안에서만 끈다.
    """
    import os
    before = os.environ.get("BIGFOOT_OFFLINE")
    os.environ["BIGFOOT_OFFLINE"] = "1"
    yield
    if before is None:
        os.environ.pop("BIGFOOT_OFFLINE", None)
    else:
        os.environ["BIGFOOT_OFFLINE"] = before


@pytest.fixture(autouse=True)
def _isolate_caches():
    """Reset the process-global TTL cache around every test.

    market_data_service's load_snapshot/load_fixings/list_available_dates are
    TTL-cached, and these tests deliberately swap the underlying source between
    cases. Without this, one test's cached snapshot answers the next test's
    differently-mocked call and the failure lands somewhere unrelated. Autouse
    because it's needed by any test that touches market data, directly or
    transitively.
    """
    ttl_cache.clear()
    yield
    ttl_cache.clear()
