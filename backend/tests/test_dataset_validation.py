"""The loader refuses a workbook it cannot trust (stability session, Pass C).

Pass A mutated a synthetic copy of the real sheet one cell at a time and
recorded what happened (docs/diagnostics/failure-modes.md §2). Four mutations
loaded without a word and produced confidently wrong numbers:

    duplicated date, two rows swapped, decimal slip (4135 for 4.135),
    negative rate (-99)

The first two misdirect `derive.value_at`, a bisect on an assumed-ascending
unique list, so every change column reads the wrong day while the levels look
perfect. The second two flow into the bootstrap and out through every derived
number. All four now raise DataFileError and the server does not start.

The distinction these tests pin is UNUSABLE vs STALE. A file whose numbers
cannot be trusted is refused. A file that is merely old, gappy, or has a blank
cell still loads and says so — refusing to start on a stale file would take the
product down for a reason the reader could ride out.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import openpyxl
import pytest

from app.dataset import DataFileError, MAX_GAP_DAYS, load_dataset

# One label per value column, exactly as the Infomax export lays them out:
# the first label is merged across the date column and the first value
# column, so it reads as A2 with B2 blank. Everything after is one per column.
LABELS = [
    "원화 IRS 종합코드 6개월",   # A2, merged across A:B — so B2 reads blank
    None,                       # B2, the 6M value column
    "원화 IRS 종합코드 1년",     # C2 -> 1Y
    "원화 IRS 종합코드 10년",    # D2 -> 10Y
    "원화표준 지표수익률 콜금리",  # E2 -> 1D
]
FIELDS = ["일자", "MID종가", "MID종가", "MID종가", "수익률"]
BASE = [3.18, 3.50, 4.26, 2.80]


def write_book(path: Path, rows: list[tuple]) -> Path:
    """A workbook with the real sheet's geometry: metadata row, merged-label
    row, field row, then data rows DESCENDING.

    Built synthetically rather than by re-saving the real file — Pass A's
    first harness did that, openpyxl dropped the merged-label row on the way
    out, and all seven mutations then failed identically for a reason that had
    nothing to do with the mutation.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["기간", dt.datetime(2016, 1, 1), "Data 개수", 99999])
    ws.append(LABELS)
    ws.append(FIELDS)
    for r in rows:
        ws.append(list(r))
    wb.save(path)
    return path


def good_rows(n: int = 40, end: dt.date | None = None) -> list[tuple]:
    """`n` consecutive KR BUSINESS DAYS, most recent first. Ends YESTERDAY by
    default: a row dated today is dropped by the 전일종가 cutoff (see the
    dedicated tests below), and these fixtures are about everything else.

    업무일이지 평일이 아니다 [2026-10-07]. 종전에는 `weekday() < 5` 였고, 그때는
    통했다 — 비영업일 컷이 없었으니까. 컷이 생긴 뒤로는 창에 공휴일이 끼는
    날(기본값은 「어제까지 40칸」이라 돌리는 날마다 창이 움직인다)마다 이
    픽스처가 경고를 하나 달고 와서 「좋은 파일」이 아니게 된다. 픽스처의 뜻은
    **종가가 든 멀쩡한 파일**이고, 멀쩡한 인포맥스 내보내기에는 휴일 행이
    없다 — 그래서 달력을 엔진 것으로 맞춘다.
    """
    from app.engine_port import _is_kr_business_day

    end = end or dt.date.today() - dt.timedelta(days=1)
    out: list[tuple] = []
    d = end
    while len(out) < n:
        if _is_kr_business_day(d):
            out.append((dt.datetime(d.year, d.month, d.day), *BASE))
        d -= dt.timedelta(days=1)
    return out


@pytest.fixture
def book(tmp_path):
    def make(rows):
        return write_book(tmp_path / "irsdata.xlsx", rows)

    return make


def test_a_good_file_loads(book):
    ds = load_dataset(book(good_rows()))
    assert ds.dates == sorted(ds.dates)
    assert ds.warnings == []
    assert ds.latest("10Y") == 4.26


# ── unusable: the server must not start ────────────────────────────────────


def test_duplicate_date_is_refused(book):
    rows = good_rows()
    rows[5] = (rows[4][0], *BASE)  # repeat the date above it
    with pytest.raises(DataFileError) as e:
        load_dataset(book(rows))
    assert "already appears at row" in str(e.value)


def test_swapped_rows_are_refused(book):
    """The orientation check reads dates[0] vs dates[-1] only, so a mid-file
    swap used to sail straight through it."""
    rows = good_rows()
    rows[10], rows[11] = rows[11], rows[10]
    with pytest.raises(DataFileError) as e:
        load_dataset(book(rows))
    assert "date order" in str(e.value)


@pytest.mark.parametrize("bad", [4135.0, 413.5, -99.0, -6.0])
def test_value_outside_the_plausible_band_is_refused(book, bad):
    """A decimal slip and a sign error, the two mutations Pass A found
    completely invisible."""
    rows = good_rows()
    rows[3] = (rows[3][0], BASE[0], bad, BASE[2], BASE[3])
    with pytest.raises(DataFileError) as e:
        load_dataset(book(rows))
    assert "decimal point" in str(e.value)


def test_a_rate_written_as_a_fraction_is_NOT_caught(book):
    """Stated as a test so the limit of this check is on the record: the band
    is a magnitude check, and 0.0413 for 4.13% sits well inside it. Catching
    that would need a cross-check against the neighbouring days' levels, which
    is a different (and much more opinionated) piece of work.
    """
    rows = good_rows()
    rows[3] = (rows[3][0], BASE[0], 0.0413, BASE[2], BASE[3])
    ds = load_dataset(book(rows))
    assert ds.series["1Y"][-4] == 0.0413


def test_text_where_a_number_belongs_is_refused(book):
    rows = good_rows()
    rows[2] = (rows[2][0], BASE[0], "n/a", BASE[2], BASE[3])
    with pytest.raises(DataFileError) as e:
        load_dataset(book(rows))
    assert "expected a number" in str(e.value)


def test_an_entirely_blank_column_is_refused(book):
    rows = [(r[0], r[1], None, r[3], r[4]) for r in good_rows()]
    with pytest.raises(DataFileError) as e:
        load_dataset(book(rows))
    assert "every value is blank" in str(e.value)


def test_no_data_rows_is_refused(book):
    with pytest.raises(DataFileError):
        load_dataset(book([]))


def test_a_wrong_header_says_what_was_expected(book):
    path = book(good_rows())
    wb = openpyxl.load_workbook(path)
    wb.active["A3"] = "date"
    wb.save(path)
    with pytest.raises(DataFileError) as e:
        load_dataset(path)
    assert "일자" in str(e.value)


# ── every message names the cell ───────────────────────────────────────────


@pytest.mark.parametrize(
    "mutate, expect",
    [
        # row 3 of the data is sheet row 6; the bad value is in column C
        (lambda r: r.__setitem__(2, (r[2][0], BASE[0], 4135.0, BASE[2], BASE[3])), "C6"),
        (lambda r: r.__setitem__(0, ("not a date", *BASE)), "A4"),
    ],
)
def test_errors_name_the_cell_not_the_row(book, mutate, expect):
    """The person fixing this is looking at a spreadsheet. A cell reference
    goes straight into the name box; "row 6, third series" does not."""
    rows = good_rows()
    mutate(rows)
    with pytest.raises(DataFileError) as e:
        load_dataset(book(rows))
    assert expect in str(e.value)


# ── stale: loud, but the server runs ───────────────────────────────────────


def test_a_gap_warns_and_still_loads(book):
    rows = good_rows(20)
    # drop a fortnight out of the middle
    rows = rows[:5] + rows[15:]
    ds = load_dataset(book(rows))
    assert ds.dates  # loaded
    assert any("gap" in w for w in ds.warnings)


def test_an_old_file_warns_and_still_loads(book):
    old = dt.date.today() - dt.timedelta(days=60)
    ds = load_dataset(book(good_rows(20, end=old)))
    assert ds.dates
    assert any("days old" in w for w in ds.warnings)


def test_a_blank_cell_warns_and_still_loads(book):
    rows = good_rows()
    rows[4] = (rows[4][0], BASE[0], None, BASE[2], BASE[3])
    ds = load_dataset(book(rows))
    assert ds.series["1Y"][-5] is None
    assert any("blank" in w for w in ds.warnings)


def test_stale_and_unusable_are_different_outcomes(book):
    """The distinction, stated as a test so it cannot erode: an old file
    loads with a warning; an untrustworthy one does not load at all."""
    old = dt.date.today() - dt.timedelta(days=MAX_GAP_DAYS * 10)
    assert load_dataset(book(good_rows(20, end=old))).warnings

    rows = good_rows(20)
    rows[7] = (rows[6][0], *BASE)
    with pytest.raises(DataFileError):
        load_dataset(book(rows))


def test_the_real_data_file_passes_its_own_validation():
    """The shipped file must satisfy every rule above — a validator the real
    data cannot pass is a validator someone will delete."""
    real = Path(__file__).resolve().parents[2] / "data" / "irsdata.xlsx"
    ds = load_dataset(real)
    assert len(ds.dates) > 2000


# ── 전일종가 cutoff [OWNER, 2026-08-05] ─────────────────────────────────────
# A row dated today is the Infomax add-in's LIVE quotes at whatever moment
# the workbook was saved, not a close. The loader treats it as missing: the
# basis is always the last completed close. These inject `today` so the
# tests do not depend on when they run.


def test_a_today_dated_row_is_dropped(book):
    today = dt.date(2026, 8, 5)  # a Wednesday
    rows = good_rows(10, end=today)
    ds = load_dataset(book(rows), today=today)
    assert ds.asof == dt.date(2026, 8, 4)  # the previous weekday's close
    assert all(d < today for d in ds.dates)
    assert len(ds.dates) == 9
    assert any("전일종가" in w for w in ds.warnings)


def test_yesterdays_close_is_kept_whole(book):
    # the cut removes ONLY today's row — every completed close survives, and
    # the series stay aligned to the shortened date axis
    today = dt.date(2026, 8, 5)
    rows = good_rows(10, end=today)
    ds = load_dataset(book(rows), today=today)
    assert all(len(v) == len(ds.dates) for v in ds.series.values())
    assert ds.latest("10Y") == 4.26


def test_a_file_without_a_today_row_is_untouched(book):
    today = dt.date(2026, 8, 5)
    rows = good_rows(10, end=dt.date(2026, 8, 4))
    ds = load_dataset(book(rows), today=today)
    assert ds.asof == dt.date(2026, 8, 4)
    assert len(ds.dates) == 10
    assert not any("전일종가" in w for w in ds.warnings)


def test_all_rows_on_or_after_today_is_refused(book):
    # nothing left to serve — same class as an empty sheet
    rows = good_rows(3, end=dt.date(2026, 8, 7))
    with pytest.raises(DataFileError) as e:
        load_dataset(book(rows), today=dt.date(2026, 8, 1))
    assert "completed closes" in str(e.value)


# ── 비영업일 컷 [2026-10-07] ────────────────────────────────────────────────
# `mkt_irs_close` 가 휴일에 전영업일 커브를 복사한 행을 만든다. 그 행이 asof 가
# 되면 화면 머리가 장이 쉰 날을 「종가」라 부르고, 영업일만 걷는 장부와 날짜가
# 갈린다 [OWNER 2026-10-07 — "이거 왜 종가업데이트 안 되냐"]. 실측 판례가
# 2026-10-05(개천절 대체공휴일)이고, 그 행은 10-02 와 IRS 13칼럼이 한 자리까지
# 같았다.


def _row(d: dt.date, *vals) -> tuple:
    return (dt.datetime(d.year, d.month, d.day), *(vals or BASE))


def test_a_holiday_row_is_dropped(book):
    """장이 쉰 날의 행은 종가가 아니다 — 실측 그대로의 날짜로 친다."""
    today = dt.date(2026, 10, 7)          # 수요일
    rows = [
        _row(dt.date(2026, 10, 5)),       # 개천절 대체공휴일 — 복사본
        _row(dt.date(2026, 10, 2)),       # 금요일 종가
        _row(dt.date(2026, 10, 1)),
    ]
    ds = load_dataset(book(rows), today=today)
    assert ds.asof == dt.date(2026, 10, 2)
    assert dt.date(2026, 10, 5) not in ds.dates
    assert any("non-business-day" in w for w in ds.warnings)


def test_a_weekend_row_is_dropped_too(book):
    """주말도 같은 컷이다 — 「공휴일만」이 아니라 「영업일이 아닌 날」이다."""
    today = dt.date(2026, 10, 7)
    rows = [
        _row(dt.date(2026, 10, 3)),       # 토요일(개천절)
        _row(dt.date(2026, 10, 2)),
        _row(dt.date(2026, 10, 1)),
    ]
    ds = load_dataset(book(rows), today=today)
    assert ds.dates == [dt.date(2026, 10, 1), dt.date(2026, 10, 2)]


def test_the_cut_keeps_the_series_aligned(book):
    """날짜만 빼고 값을 안 빼면 모든 bisect 가 한 칸씩 어긋난다 — 그 축을 박는다."""
    today = dt.date(2026, 10, 7)
    rows = [
        _row(dt.date(2026, 10, 5), 1.0, 2.0, 9.99, 3.0),   # 10Y = 9.99, 버려질 행
        _row(dt.date(2026, 10, 2), 1.0, 2.0, 4.26, 3.0),
    ]
    ds = load_dataset(book(rows), today=today)
    assert all(len(v) == len(ds.dates) for v in ds.series.values())
    assert ds.latest("10Y") == 4.26        # 유령 행의 9.99 가 아니다


def test_a_business_day_only_file_is_untouched(book):
    today = dt.date(2026, 10, 7)
    rows = [_row(dt.date(2026, 10, 6)), _row(dt.date(2026, 10, 2))]
    ds = load_dataset(book(rows), today=today)
    assert len(ds.dates) == 2
    assert not any("non-business-day" in w for w in ds.warnings)


def test_all_rows_on_non_business_days_is_refused(book):
    """남는 종가가 없다 — 빈 시트와 같은 부류로 거절한다."""
    rows = [_row(dt.date(2026, 10, 5)), _row(dt.date(2026, 10, 3))]
    with pytest.raises(DataFileError) as e:
        load_dataset(book(rows), today=dt.date(2026, 10, 7))
    assert "weekend or a KR holiday" in str(e.value)


def test_the_intraday_cut_speaks_first_on_a_holiday(book):
    """오늘이 휴일인 날의 오늘 자 행은 「장중」이라고 말하는 쪽이 정확하다."""
    today = dt.date(2026, 10, 9)          # 한글날 — 휴일이면서 '오늘'
    rows = [_row(today), _row(dt.date(2026, 10, 8))]
    ds = load_dataset(book(rows), today=today)
    assert ds.asof == dt.date(2026, 10, 8)
    assert any("전일종가" in w for w in ds.warnings)
    assert not any("non-business-day" in w for w in ds.warnings)
