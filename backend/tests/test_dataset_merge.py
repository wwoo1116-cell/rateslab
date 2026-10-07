"""병합 로더의 판정을 못 박는다 [OWNER, 2026-08-11 — 아침 자동 굽기].

오너 규칙 세 줄이 전부다:

    SQL 이 기대 전영업일을 온전히 들고 있으면 SQL 그대로.
    1D 만 비면 그 칸만 엑셀에서 채운다.
    하루가 통째로 없으면 그 하루를 엑셀에서 덧붙인다.

2026-10-07 에 그 셋째 줄의 출처가 둘이 되었다 — **종합ALL(`imx_data.timeseries`)
이 먼저, 엑셀이 나중**. 같은 서버에 10-06 종가가 이미 와 있는데 `mkt_irs_close`
만 서 있던 날 붙였고, 고른 근거는 대조다 — 겹친 34,528칸에서 불일치 14건(0.04%)·
최대 1.00bp 이고 그 14건이 전부 8Y·9Y 다.
종합ALL 에는 1D·3M 이 없어서 그 날 그 두 칸은 **빈칸**이다(화면에서는
`derive.value_at` 이 직전 종가로 이어 붙인다 — 원래 동작) — 그래서 아래
「섞지 않는다」 시험이 하나 더 있다.

여기서 지키는 불변식은 두 가지다. 첫째, **과거사는 절대 엑셀로 갈아타지
않는다** — 1D 는 두 출처가 다른 계열(80.8% 불일치)이라, 폴백이 역사를 건드리면
SQL 이 뒤늦게 적재된 날 1D 차트에 유령 점프가 생긴다. 둘째, **엑셀이 섞이면
`source` 가 반드시 말한다** — 화면 칩과 manifest 가 이 값 하나를 읽는다.

`merge_expected_close` 는 순수 함수라서 DB 도 워크북도 없이 Dataset 리터럴로
전 케이스를 친다.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.dataset import (
    DataFileError,
    Dataset,
    merge_expected_close,
    prev_kr_business_day,
)

MON = dt.date(2026, 8, 10)   # 월요일 — 기대 전영업일 (화요일 아침 기준)
FRI = dt.date(2026, 8, 7)    # 그 전 영업일


def ds(dates: list[dt.date], series: dict[str, list[float | None]],
       source: str) -> Dataset:
    return Dataset(
        dates=list(dates),
        series={t: list(v) for t, v in series.items()},
        tenor_order=list(series),
        source=source,
    )


def sql_two_days(d1_latest: float | None = 2.5) -> Dataset:
    return ds(
        [FRI, MON],
        {"1D": [2.49, d1_latest], "3Y": [3.30, 3.31], "10Y": [3.60, 3.62]},
        source="sql",
    )


def xlsx_two_days() -> Dataset:
    # 1D 가 SQL 과 다른 값인 것이 포인트다 — 다른 계열이라는 사실이 테스트의
    # 관찰 수단이 된다.
    return ds(
        [FRI, MON],
        {"1D": [2.60, 2.61], "3Y": [3.30, 3.31], "10Y": [3.60, 3.62]},
        source="xlsx",
    )


# ── 정상 경로: SQL 이 온전하면 손대지 않는다 ────────────────────────────────

def test_sql_complete_untouched():
    out = merge_expected_close(sql_two_days(), xlsx_two_days(), MON)
    assert out.source == "sql"
    assert out.latest("1D") == 2.5          # 엑셀 2.61 이 새어들지 않았다
    assert out.asof == MON
    assert out.warnings == []


# ── 1D 만 빈 날: 그 칸만 엑셀 [OWNER "1D는 엑셀에서 가져와서 채우는 걸로"] ──

def test_missing_1d_patched_from_xlsx():
    out = merge_expected_close(sql_two_days(d1_latest=None), xlsx_two_days(), MON)
    assert out.source == "sql+xlsx-1d"
    assert out.latest("1D") == 2.61          # asof 의 1D 만 엑셀 값
    assert out.series["1D"][0] == 2.49       # 과거사는 SQL 그대로
    assert out.latest("3Y") == 3.31          # 다른 노드는 손대지 않았다
    assert any("1D" in w for w in out.warnings)


def test_missing_1d_nowhere_stays_none():
    xl = xlsx_two_days()
    xl.series["1D"][-1] = None
    out = merge_expected_close(sql_two_days(d1_latest=None), xl, MON)
    assert out.source == "sql"               # 엑셀이 못 채웠으면 라벨도 없다
    assert out.latest("1D") is None
    assert any("엑셀에도 없다" in w for w in out.warnings)


def test_missing_1d_without_xlsx_stays_none():
    out = merge_expected_close(sql_two_days(d1_latest=None), None, MON)
    assert out.source == "sql"
    assert out.latest("1D") is None


# ── 하루가 통째로 없는 날: 그 하루만 보충 출처에서 덧붙인다 ─────────────────

def test_missing_day_appended_from_xlsx():
    sql = ds([FRI], {"1D": [2.49], "3Y": [3.30], "10Y": [3.60]}, source="sql")
    out = merge_expected_close(sql, xlsx_two_days(), MON)
    assert out.source == "sql+xlsx-day"
    assert out.asof == MON
    assert out.latest("1D") == 2.61          # 덧붙인 날은 전부 엑셀 값
    assert out.latest("3Y") == 3.31
    assert out.series["1D"][0] == 2.49       # 과거사는 SQL 그대로
    assert out.dates == [FRI, MON]           # 오름차순 유지


def test_missing_day_xlsx_lacks_a_tenor():
    # 엑셀에는 없는 노드(SQL 전용 4Y 같은 것)는 그 날 빈칸이 된다 — 값을
    # 지어내지 않는다.
    sql = ds([FRI], {"1D": [2.49], "3Y": [3.30], "4Y": [3.40]}, source="sql")
    out = merge_expected_close(sql, xlsx_two_days(), MON)
    assert out.source == "sql+xlsx-day"
    assert out.latest("4Y") is None
    assert any("4Y" in w for w in out.warnings)


def test_missing_day_xlsx_also_stale_stays_sql():
    sql = ds([FRI], {"1D": [2.49], "3Y": [3.30]}, source="sql")
    xl = ds([FRI], {"1D": [2.60], "3Y": [3.30]}, source="xlsx")
    out = merge_expected_close(sql, xl, MON)
    assert out.source == "sql"               # 덧붙일 것이 없다 — 지연 칩의 몫
    assert out.asof == FRI
    assert any("보충 출처" in w for w in out.warnings)


def test_missing_day_without_xlsx_stays_sql():
    sql = ds([FRI], {"1D": [2.49], "3Y": [3.30]}, source="sql")
    out = merge_expected_close(sql, None, MON)
    assert out.source == "sql"
    assert out.asof == FRI


# ── 보충 출처 둘의 순서 [2026-10-07] ───────────────────────────────────────
#
# 실측 판례가 이 시험들의 출처다: 2026-10-07 아침 `mkt_irs_close` 의 MAX 는
# 2026-10-05(휴일 복사본)였고 10-06 행이 없었는데, 같은 서버
# `imx_data.timeseries` 종합ALL 에는 10-06 이 2년 3.87 · 5년 4.085 · 10년 4.18
# 로 이미 들어와 있었다 [OWNER — "이거 왜 종가업데이트 안 되냐"].


def imx_day_mon() -> dict[str, float]:
    """종합ALL 이 주는 모양 — IRS 테너만, 1D·3M 없이."""
    return {"3Y": 3.33, "10Y": 3.65}


def test_missing_day_appended_from_imx():
    sql = ds([FRI], {"1D": [2.49], "3Y": [3.30], "10Y": [3.60]}, source="sql")
    out = merge_expected_close(sql, None, MON, imx_day_mon())
    assert out.source == "sql+imx-day"
    assert out.asof == MON
    assert out.latest("3Y") == 3.33
    assert out.series["3Y"][0] == 3.30       # 과거사는 SQL 그대로
    assert out.dates == [FRI, MON]


def test_imx_beats_xlsx_and_does_not_mix():
    """종합ALL 이 이기고, 그 날 1D 는 **빈칸**이다 — 엑셀의 1D 가 새어들면 안 된다.

    엑셀의 1D(2.61)는 SQL 과 80.8% 불일치하는 다른 계열이다. 섞으면 「엑셀이
    섞이면 source 가 반드시 말한다」를 라벨 하나로 표현할 수 없고, 그 전에
    커브의 짧은 끝이 다른 계열 값을 입는다 — 빈칸으로 두면 화면은 **같은 계열의
    직전 종가**를 이어 붙인다(`derive.value_at`), 그쪽이 낫다.
    """
    sql = ds([FRI], {"1D": [2.49], "3Y": [3.30], "10Y": [3.60]}, source="sql")
    out = merge_expected_close(sql, xlsx_two_days(), MON, imx_day_mon())
    assert out.source == "sql+imx-day"
    assert out.latest("3Y") == 3.33          # 엑셀의 3.31 이 아니다
    assert out.latest("1D") is None          # 엑셀의 2.61 이 아니다
    assert any("1D" in w for w in out.warnings)   # 빈 노드를 이름으로 말한다
    assert out.series["1D"][0] == 2.49       # 과거사의 1D 는 SQL 그대로


def test_imx_empty_falls_through_to_xlsx():
    """종합ALL 에 그 날이 없으면(빈 dict/None) 종전 경로가 그대로 산다."""
    for empty in ({}, None):
        sql = ds([FRI], {"1D": [2.49], "3Y": [3.30], "10Y": [3.60]},
                 source="sql")
        out = merge_expected_close(sql, xlsx_two_days(), MON, empty)
        assert out.source == "sql+xlsx-day"
        assert out.latest("1D") == 2.61


def test_imx_with_no_overlapping_tenor_falls_through():
    """SQL 의 노드와 하나도 안 겹치면 그것은 「그 날이 있다」가 아니다."""
    sql = ds([FRI], {"1D": [2.49], "3Y": [3.30]}, source="sql")
    out = merge_expected_close(sql, xlsx_two_days(), MON, {"7Y": 3.5})
    assert out.source == "sql+xlsx-day"
    assert out.latest("3Y") == 3.31


def test_imx_lacks_a_tenor_is_named():
    sql = ds([FRI], {"1D": [2.49], "3Y": [3.30], "4Y": [3.40]}, source="sql")
    out = merge_expected_close(sql, None, MON, {"3Y": 3.33})
    assert out.source == "sql+imx-day"
    assert out.latest("4Y") is None
    assert out.latest("1D") is None
    assert any("4Y" in w and "1D" in w for w in out.warnings)


def test_imx_does_not_touch_history():
    """★이 리포의 불변식 — 과거사는 어떤 보충 출처로도 갈아타지 않는다."""
    sql = ds([FRI, MON], {"1D": [2.49, 2.5], "3Y": [3.30, 3.31]}, source="sql")
    out = merge_expected_close(sql, None, MON, {"3Y": 9.99})
    assert out.source == "sql"               # 그 날을 이미 들고 있다
    assert out.series["3Y"] == [3.30, 3.31]  # 9.99 가 어디에도 없다


# ── 라벨 지도 [2026-10-07] ─────────────────────────────────────────────────
#
# 지도 하나가 틀리면 커브의 한 칸이 조용히 다른 만기 값을 입는다 — 특히
# "18개월" → 1.5Y 는 한글 라벨과 테너 id 가 안 닮은 유일한 칸이다.


def test_imx_item_map_covers_the_sql_irs_columns():
    """종합ALL 13칸이 `mkt_irs_close` 의 `irs_*` 컬럼과 1:1 이어야 한다.

    SQL 쪽에만 있는 1D(콜)·3M(CD91)은 종합ALL 에 **없는 것이 맞다** — 그 둘은
    다른 계열이라 채우지 않기로 한 자리다.
    """
    from app.dataset import IMX_ITEM_TENOR, SQL_COLUMN_TENOR

    sql_irs = {t for c, t in SQL_COLUMN_TENOR.items() if c.startswith("irs_")}
    assert set(IMX_ITEM_TENOR.values()) == sql_irs
    assert len(IMX_ITEM_TENOR) == 13
    assert IMX_ITEM_TENOR["18개월"] == "1.5Y"
    assert {"1D", "3M"} & set(IMX_ITEM_TENOR.values()) == set()


def test_imx_day_values_maps_labels_and_drops_unknowns(monkeypatch):
    import app.mysqldb as mysqldb
    from app.dataset import imx_day_values

    monkeypatch.setattr(
        mysqldb, "imx_irs_day",
        lambda d: {"18개월": 3.5, "10년": 4.18, "모르는항목": 1.0},
    )
    out = imx_day_values(MON)
    assert out == {"1.5Y": 3.5, "10Y": 4.18}   # 모르는 항목은 안 들어온다


def test_imx_day_values_returns_none_when_absent_or_broken(monkeypatch):
    """없는 날도, 죽은 DB 도 **None** 이다 — 둘 다 「보충 못 함」이고 서버는 뜬다."""
    import app.mysqldb as mysqldb
    from app.dataset import imx_day_values

    monkeypatch.setattr(mysqldb, "imx_irs_day", lambda d: {})
    assert imx_day_values(MON) is None

    def boom(d):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(mysqldb, "imx_irs_day", boom)
    assert imx_day_values(MON) is None


# ── 비상 경로: SQL 자체를 못 읽었다 ─────────────────────────────────────────

def test_sql_down_falls_back_to_xlsx_whole():
    out = merge_expected_close(None, xlsx_two_days(), MON)
    assert out.source == "xlsx"
    assert out.latest("1D") == 2.61
    assert any("폴백" in w for w in out.warnings)


def test_both_down_raises():
    with pytest.raises(DataFileError):
        merge_expected_close(None, None, MON)


# ── 기대 전영업일 계산 ──────────────────────────────────────────────────────

def test_prev_business_day_skips_weekend():
    assert prev_kr_business_day(dt.date(2026, 8, 10)) == FRI   # 월 → 금
    assert prev_kr_business_day(dt.date(2026, 8, 11)) == MON   # 화 → 월


def test_prev_business_day_skips_holiday():
    # 광복절 2026-08-15 는 토요일 — 8/17(월)의 전영업일은 8/14(금)이고,
    # 8/14 가 대체공휴일이면 그 앞 영업일로 물러난다. 달력이 어느 쪽으로
    # 답하든 "주말도 공휴일도 아닌 날" 이라는 성질만 못 박는다.
    from app.engine_port import _is_kr_business_day

    d = prev_kr_business_day(dt.date(2026, 8, 17))
    assert _is_kr_business_day(d)
    assert d < dt.date(2026, 8, 17)
