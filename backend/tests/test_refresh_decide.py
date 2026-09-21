"""아침 갱신의 판정을 못 박는다 [2026-09-22].

## 왜 이 시험이 있는가

`refresh.ps1` 은 2026-09-10 부터 09-22 까지 **열 번의 아침을 전부 「이미
최신이에요」로 적고 아무것도 안 했다**(refresh.log). 서버는 SQL 만큼은 최신이었고
SQL 이 전영업일을 안 들고 있었을 뿐인데, 그 둘이 한 문장으로 뭉개져 있었다.
Main·Backtest 는 부팅 스냅샷을 서빙하므로 그 열흘 동안 **늘 한 영업일 늦었다**.

판정을 PowerShell 에서 Python 으로 옮긴 이유가 이 파일이다 — PowerShell 에는
시험이 없다. `decide` 는 순수 함수라서 DB 도 시계도 안 본다.
"""

from __future__ import annotations

import pytest

cc = pytest.importorskip("scripts.check_close",
                         reason="scripts/ 가 sys.path 에 없다")


def v(served: str, serve_asof: str | None, expected: str | None = "2026-09-21",
      business: bool = True) -> str:
    return cc.decide(served, serve_asof, expected, business)["verdict"]


def test_stale_snapshot_restarts():
    """서버가 SQL 보다 낡으면 재기동. 09-21 아침의 실제 수."""
    assert v("2026-09-17", "2026-09-18") == "restart"


def test_waiting_is_not_current():
    """★이 리포의 열흘을 먹은 자리. 서버 = SQL 인데 SQL < 기대일이면 «기다림» 이다.

    옛 스크립트는 여기서 「이미 최신」을 적고 종료했고, 그래서 그날 늦게 도착한
    적재를 아무도 안 봤다."""
    assert v("2026-09-18", "2026-09-18", expected="2026-09-21") == "waiting"


def test_current_only_when_expected_day_is_served():
    assert v("2026-09-21", "2026-09-21", expected="2026-09-21") == "current"


def test_served_ahead_of_loader_is_current_not_restart():
    """서버가 로더보다 앞선 날짜를 들고 있으면 재기동하지 않는다.

    엑셀 병합분을 들고 뜬 뒤 그 엑셀이 치워진 경우가 이것이다. 재기동하면
    **뒤로 간다** — 그건 갱신이 아니다."""
    assert v("2026-09-21", "2026-09-18") == "current"


def test_backend_down_starts():
    assert v("", "2026-09-18") == "start"


def test_no_asof_never_restarts():
    """DB·엑셀 둘 다 죽었으면 재기동은 최악의 수다 — 뜨지도 못한다."""
    assert v("2026-09-18", None) == "error"
    assert v("", None) == "error"


def test_holiday_does_not_wait():
    """영업일이 아니면 기대 전영업일이 없다. 적재가 없으니 기다릴 것도 없다."""
    assert v("2026-09-18", "2026-09-18", expected=None, business=False) == "current"


def test_every_verdict_has_one_sentence():
    """로그 문장은 Python 에만 있다 — PowerShell 이 제 어휘를 만들면 한 사실에
    두 문장이 생긴다."""
    for verdict in ("error", "start", "restart", "waiting", "current"):
        assert cc._WHY[verdict].strip()
    seen = {
        v("", None),
        v("", "2026-09-18"),
        v("2026-09-17", "2026-09-18"),
        v("2026-09-18", "2026-09-18"),
        v("2026-09-21", "2026-09-21"),
    }
    assert seen == set(cc._WHY)
