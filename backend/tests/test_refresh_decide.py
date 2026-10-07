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
      business: bool = True, served_source: str | None = None,
      serve_source: str | None = None) -> str:
    return cc.decide(served, serve_asof, expected, business,
                     served_source, serve_source)["verdict"]


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


# ── 출처가 갈린 날 [2026-10-07] ────────────────────────────────────────────
#
# 보충 출처(종합ALL)로 하루를 메운 뒤 원출처가 따라잡는 날이 있다. 실측:
# 09:28 에 종합ALL 로 10-06 을 메워 재기동했고, 09:4x 에 `mkt_irs_close` 자신의
# 10-06 행이 도착했다. 날짜가 둘 다 10-06 이라 종전 판정은 `current` 였고 화면은
# 대체분을 하루 더 들었다 — 11개 테너는 같지만 8Y·9Y 가 최대 1.00bp 다르다.


def test_same_day_but_substituted_source_restarts():
    assert v("2026-10-06", "2026-10-06", expected="2026-10-06",
             served_source="sql+imx-day", serve_source="sql") == "restart"


def test_same_day_same_source_is_current():
    assert v("2026-10-06", "2026-10-06", expected="2026-10-06",
             served_source="sql", serve_source="sql") == "current"
    assert v("2026-10-06", "2026-10-06", expected="2026-10-06",
             served_source="sql+imx-day",
             serve_source="sql+imx-day") == "current"


def test_source_rule_is_skipped_when_either_side_is_unknown():
    """이 필드 이전의 백엔드도 떠 있어야 한다 — 모르면 그 판정만 건너뛴다."""
    for a, b in ((None, "sql"), ("sql+imx-day", None), ("", ""), (None, None)):
        assert v("2026-10-06", "2026-10-06", expected="2026-10-06",
                 served_source=a, serve_source=b) == "current"


def test_the_date_rule_still_wins_over_the_source_rule():
    """날짜가 앞서면 그것만으로 재기동이다 — 출처를 못 읽어도 멈추지 않는다."""
    assert v("2026-10-05", "2026-10-06", expected="2026-10-06",
             served_source=None, serve_source=None) == "restart"


def test_waiting_is_not_masked_by_the_source_rule():
    """출처가 같고 SQL 이 기대일을 안 들고 있으면 여전히 «기다림» 이다."""
    assert v("2026-10-02", "2026-10-02", expected="2026-10-06",
             served_source="sql", serve_source="sql") == "waiting"
