# -*- coding: utf-8 -*-
"""혼합 북(현금채권 + 스왑)의 핀 [OWNER, 2026-08-21].

합성 데이터로 돈다 — 민평은 SQL 에만 있고 IRS 워크북은 배포마다 다르다
(`test_cashbond` 의 같은 근거). 여기서 재는 것은 **병합의 산술**이지 데이터의
가용성이 아니다: 두 엔진이 각자 옳다는 것은 저쪽 파일들이 이미 핀으로 박고
있으므로, 이 파일이 지는 명제는 셋뿐이다.

    1. 섞은 북의 손익 = 따로 돌린 둘의 합 (같은 날짜 위에서).
    2. 한 종류뿐인 북은 종전 엔진의 답 **그대로**다 — 통합이 기존 화면의
       숫자를 한 원도 바꾸면 안 된다.
    3. 대사표의 행은 가로로 닫히고, 두 KRD 격자는 섞이지 않는다.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app import cashbond as cb
from app import creditmatrix as cm
from app import funding as fd
from app import mixedbook as mb
from app.backtest import Position, run_backtest as swap_run_backtest
from app.engine_port import bootstrap_zero_curve

from tests.synthetic import frozen_dataset

N = 1e10  # 100억

#: 기울어진 par 커브 하나 — 합성 IRS 데이터셋의 씨앗.
_SEED_PAR = [
    (1.0 / 365.0, 0.0250), (91.0 / 365.0, 0.0255), (0.5, 0.0260), (0.75, 0.0265),
    (1.0, 0.0270), (1.5, 0.0278), (2.0, 0.0285), (3.0, 0.0295), (4.0, 0.0302),
    (5.0, 0.0308), (6.0, 0.0313), (7.0, 0.0317), (8.0, 0.0320), (9.0, 0.0323),
    (10.0, 0.0325),
]


@pytest.fixture(autouse=True)
def _seed_funding():
    """조달 계단을 직접 시드한다 — 신선도 게이트는 여기서 재는 것이 아니다
    (`test_cashbond._seed_base_series` 와 같은 이유·같은 수법)."""
    fd.reset_cache()
    fd._series_cache["base"] = [(dt.date(2020, 1, 1), 0.0250)]
    yield
    fd.reset_cache()


SPEC = fd.FundingSpec("base", 0.0)


def _dataset(n_days: int = 300, start: dt.date = dt.date(2024, 1, 2)):
    zc = bootstrap_zero_curve(_SEED_PAR)
    return frozen_dataset(zc, start, n_days)


def _matrix(dates: list[dt.date], rate_pct: float = 3.10) -> cm.CreditMatrix:
    """그 날짜들 위의 평평한 합성 민평. 종목군은 국고채 하나면 충분하다."""
    values: dict[tuple[str, str], list[float | None]] = {}
    for label in cm.TENOR_LABELS:
        values[("KTB", label)] = [rate_pct] * len(dates)
    return cm.CreditMatrix(
        dates=list(dates), values=values, watermark=("synthetic-mixed", len(dates))
    )


def _futdata(dates: list[dt.date], price: float = 104.0):
    """페이크 선물 — 값이 평평해 손익 0 이다(이 시험은 **달력**만 잰다)."""
    from app import futures as ft
    from irs_pricer.services.simulation.futures_pricing import implied_yield

    def mk(years: int) -> "ft.FuturesSeries":
        path = [price] * len(dates)
        return ft.FuturesSeries(
            dates=list(dates), price_adj=list(path),
            implied=[implied_yield(price, years)] * len(dates), price_ctr=list(path),
        )

    return ft.FuturesData(series={"3Y": mk(3), "10Y": mk(10)},
                          watermark=("test", len(dates)))


def _pos(sid: str, direction: int, entry: dt.date, exit: dt.date | None = None):
    return mb.MixedPosition(sid, direction, N, entry, exit)


# ── 1. 섞은 북 = 따로 돌린 둘의 합 ──────────────────────────────────────────


class TestAdditivity:
    """두 다리가 한 북에서 **더해진다**. 이것이 안 되면 나머지는 볼 것도 없다."""

    def test_a_mixed_book_totals_the_two_engines(self):
        ds = _dataset()
        m = _matrix(ds.dates)              # 달력이 완전히 겹치는 판
        entry = ds.dates[5]

        swap_only = mb.run_backtest(m, ds, [_pos("3Y", 1, entry)], SPEC)
        bond_only = mb.run_backtest(m, ds, [_pos("CB:KTB:3Y", 1, entry)], SPEC)
        both = mb.run_backtest(
            m, ds, [_pos("3Y", 1, entry), _pos("CB:KTB:3Y", 1, entry)], SPEC
        )

        assert both["pnl"] == pytest.approx(
            swap_only["pnl"] + bond_only["pnl"], abs=2.0
        )
        assert len(both["positions"]) == 2
        assert [p["kind"] for p in both["positions"]] == ["swap", "cashbond"]

    def test_the_line_adds_up_point_for_point(self):
        """점마다 더해진다 — 합계만 맞고 선이 어긋나면 차트가 거짓말한다."""
        ds = _dataset()
        m = _matrix(ds.dates)
        entry = ds.dates[5]

        a = mb.run_backtest(m, ds, [_pos("5Y", -1, entry)], SPEC)
        b = mb.run_backtest(m, ds, [_pos("CB:KTB:5Y", 1, entry)], SPEC)
        both = mb.run_backtest(
            m, ds, [_pos("5Y", -1, entry), _pos("CB:KTB:5Y", 1, entry)], SPEC
        )

        by_t = {p["t"]: p["pnl"] for p in both["points"]}
        pa = {p["t"]: p["pnl"] for p in a["points"]}
        pb = {p["t"]: p["pnl"] for p in b["points"]}
        common = set(pa) & set(pb) & set(by_t)
        assert len(common) > 100
        for t in common:
            assert by_t[t] == pytest.approx(pa[t] + pb[t], abs=2.0)

    def test_an_asset_swap_row_keeps_its_two_legs_in_a_mixed_book(self):
        """자산스왑은 한 줄에 두 다리다 — 혼합 북에서도 그 병합은
        `cashbond.run_bond_position` 한 군데서만 일어난다."""
        ds = _dataset()
        m = _matrix(ds.dates)
        entry = ds.dates[5]
        out = mb.run_backtest(
            m, ds, [_pos("ASW:KTB:3Y", 1, entry), _pos("10Y", 1, entry)], SPEC
        )
        asw = out["positions"][0]
        assert asw["kind"] == "assetswap"
        assert asw["swapPnl"] is not None
        assert out["positions"][1]["kind"] == "swap"

        # ── ★상품 다리 서술도 **살아서 나간다** [2026-09-29] ─────────────────
        # 종전 태그가 `{**rec, "legs": []}` 라 엔진이 실은 다리 목록을 통째로
        # 지웠고(스왑·선물 태그는 `rec` 가 이기는데 이 함수만 반대였다), 그래서
        # 자산스왑의 IRS 다리 명목·DV01 이 화면에 닿을 길이 없었다. 이 단정을
        # 되돌리면(둘 중 하나만 되돌려도) 빨개진다.
        kinds = [lg.get("kind") for lg in asw["legs"]]
        assert kinds == ["bond", "irs"], f"자산스왑 상품 다리가 {kinds} 다"
        bond_leg, irs_leg = asw["legs"]
        assert bond_leg["side"] == "long" and irs_leg["side"] == "pay", "par-par 규약"
        # par-par 는 **같은 명목**이다(DV01 중립이 아니다 — `_swap_leg` 의 그 규약).
        assert bond_leg["notional"] == irs_leg["notional"] == asw["notional"]
        # IRS 다리만 DV01 을 진다(채권 다리의 감도는 단일수익률이라 이 칸에
        # 안 적는다 — 적으면 스왑 PV01 과 같은 자로 읽힌다).
        assert irs_leg["dv01"] > 0 and "dv01" not in bond_leg
        # 진입금리는 누적 칸과 **같은 수**다 — 두 곳이 갈리면 화면이 두 답을 말한다.
        assert irs_leg["entryRate"] == asw["swapEntryRate"]

        # 현금채권은 다리가 **하나**다 — 화면이 그 줄을 안 편다(선물 아웃라이트와
        # 같은 규칙). 빈 목록이 아니라 한 칸짜리다.
        cb_out = mb.run_backtest(m, ds, [_pos("CB:KTB:3Y", 1, entry)], SPEC)
        cb_legs = cb_out["positions"][0]["legs"]
        assert [lg["kind"] for lg in cb_legs] == ["bond"], cb_legs


# ── 2. 한 종류뿐인 북은 종전 그대로 ─────────────────────────────────────────


class TestDelegation:
    """통합은 **기존 답을 바꾸지 않는다.** 스왑만 있는 북이 민평에 닿을 이유도 없다."""

    def test_a_swap_only_book_matches_the_irs_engine_to_the_won(self):
        ds = _dataset()
        entry = ds.dates[5]
        mine = mb.run_backtest(None, ds, [_pos("3Y-10Y", 1, entry)], SPEC)
        theirs = swap_run_backtest(ds, [Position("3Y-10Y", 1, N, entry)])
        assert mine["pnl"] == theirs["pnl"]
        assert [p["pnl"] for p in mine["points"]] == [p["pnl"] for p in theirs["points"]]

    def test_a_swap_only_book_never_touches_the_credit_matrix(self):
        """민평을 `None` 으로 줘도 돈다 — 그것이 위임의 증거다."""
        ds = _dataset()
        out = mb.run_backtest(None, ds, [_pos("10Y", 1, ds.dates[3])], SPEC)
        assert out["points"]

    def test_a_bond_only_book_matches_the_cash_bond_engine(self):
        ds = _dataset()
        m = _matrix(ds.dates)
        entry = ds.dates[5]
        mine = mb.run_backtest(m, ds, [_pos("CB:KTB:3Y", 1, entry)], SPEC)
        theirs = cb.run_backtest(
            m, ds, [cb.BondPosition("CB", "KTB", "3Y", 1, N, entry)], SPEC
        )
        assert mine["pnl"] == theirs["pnl"]
        assert [p["pnl"] for p in mine["points"]] == [p["pnl"] for p in theirs["points"]]

    def test_a_bond_row_without_a_matrix_says_so(self):
        ds = _dataset()
        with pytest.raises(mb.MixedBookError) as e:
            mb.run_backtest(None, ds, [_pos("CB:KTB:3Y", 1, ds.dates[5])], SPEC)
        assert "민평" in str(e.value)


# ── 3. 달력 ─────────────────────────────────────────────────────────────────


class TestCalendar:
    """민평 달력에 구멍이 뚫려도 지어내지 않는다."""

    def test_the_book_runs_on_the_intersection(self):
        ds = _dataset()
        holes = {ds.dates[40], ds.dates[41], ds.dates[90]}
        m = _matrix([d for d in ds.dates if d not in holes])
        out = mb.run_backtest(
            m, ds, [_pos("3Y", 1, ds.dates[5]), _pos("CB:KTB:3Y", 1, ds.dates[5])], SPEC
        )
        got = {p["t"] for p in out["points"]}
        assert not (got & {d.isoformat() for d in holes})
        assert out["calendar"]["dropped"] == 3

    def test_the_rows_are_clipped_to_the_book_window(self):
        """★Σ줄 == 헤드라인 [OWNER 2026-09-28 — 「북 창으로 깎는다」].

        종전에는 헤드라인이 공통 달력의 마지막 점이고 줄들은 각자 **자기 달력의
        청산일**까지 살아서, 같은 화면의 두 수가 어긋났다(실장 실측 683,680원 ·
        선물 없는 `_mixed` 경로에서도 491,829원). 적대 검증(2026-09-28)이 잡았고,
        그때 이 자리의 가드는 **달력이 완전히 겹치는 픽스처**여서 아무것도 안
        재고 있었다 — 그래서 이 시험은 **달력을 일부러 어긋나게** 만든다.

        고른 길: 모든 수가 한 날 위에 선다. 깎이기 전에 어디까지 살았는지는
        버리지 않고 `clippedTo` 로 싣는다(「안 적었다」 ≠ 「0」).
        """
        ds = _dataset()
        # 민평 달력을 **뒤에서 사흘** 짧게 만든다 — 스왑은 그 사흘을 더 산다.
        m = _matrix(ds.dates[:-3])
        book = [_pos("10Y", 1, ds.dates[5]), _pos("CB:KTB:3Y", 1, ds.dates[5])]
        out = mb.run_backtest(m, ds, book, SPEC)
        rows = out["positions"]
        assert out["to"] == m.dates[-1].isoformat(), "북 창이 민평 끝이 아니다"
        assert out["pnl"] == pytest.approx(sum(r["pnl"] for r in rows), abs=len(rows)), (
            f'헤드라인 {out["pnl"]:,.0f} != Σ줄 {sum(r["pnl"] for r in rows):,.0f}')
        # 스왑 줄은 깎였고, **어디까지 살았는지**를 말한다.
        swap = next(r for r in rows if r["id"] == "10Y")
        assert swap["exit"] == out["to"], "스왑 줄이 북 창 밖에서 끝난다"
        assert swap["clippedTo"] == ds.dates[-1].isoformat(), swap.get("clippedTo")
        # 채권 줄은 원래 북 창까지라 깎일 것이 없다 — 그럴 때는 칸이 없다.
        bond = next(r for r in rows if r["id"] == "CB:KTB:3Y")
        assert "clippedTo" not in bond, bond.get("clippedTo")

    def test_the_clip_covers_the_futures_path_too(self):
        """같은 규율이 `_mixed_any`(선물이 낀 북)에도 선다 — 경로가 둘이라
        한쪽만 고치면 같은 북이 선물 유무로 다른 수를 낸다."""
        ds = _dataset()
        m = _matrix(ds.dates[:-3])
        fut = _futdata(ds.dates)
        book = [_pos("10Y", 1, ds.dates[5]), _pos("CB:KTB:3Y", 1, ds.dates[5]),
                _pos("FUT:3Y", 1, ds.dates[5])]
        out = mb.run_backtest(m, ds, book, SPEC, fut=fut)
        rows = out["positions"]
        assert out["pnl"] == pytest.approx(sum(r["pnl"] for r in rows), abs=len(rows)), (
            f'헤드라인 {out["pnl"]:,.0f} != Σ줄 {sum(r["pnl"] for r in rows):,.0f}')
        swap = next(r for r in rows if r["id"] == "10Y")
        assert swap["clippedTo"] == ds.dates[-1].isoformat()

    def test_a_gap_day_measures_from_the_last_shared_close(self):
        """민평이 하루 빠진 다음 날의 `d` 는 **직전 공통일 대비**다 — 두 계열의
        서로 다른 밤을 더하지 않는다(모듈 주석의 `d` 절)."""
        ds = _dataset()
        hole = ds.dates[40]
        m = _matrix([d for d in ds.dates if d != hole])
        out = mb.run_backtest(
            m, ds, [_pos("3Y", 1, ds.dates[5]), _pos("CB:KTB:3Y", 1, ds.dates[5])], SPEC
        )
        pts = {p["t"]: p for p in out["points"]}
        after = ds.dates[41].isoformat()
        before = ds.dates[39].isoformat()
        assert after in pts and before in pts
        assert pts[after]["d"] == pytest.approx(
            pts[after]["pnl"] - pts[before]["pnl"], abs=2.0
        )

    def test_an_entry_before_the_shared_calendar_is_named(self):
        """민평은 IRS 보다 늦게 시작한다(실측 2020-01-02 대 2016년). 그 앞에
        들어간 스왑을 채권과 섞으면 **선만** 늦게 시작하고 총액은 옳다 — 0 에서
        출발하지 않는 선을 설명 없이 두면 오독이라 날짜를 실어 보낸다."""
        ds = _dataset(300)
        m = _matrix(ds.dates[50:])          # 민평이 50영업일 늦게 시작한다
        out = mb.run_backtest(
            m, ds, [_pos("3Y", 1, ds.dates[5]), _pos("CB:KTB:3Y", 1, ds.dates[60])], SPEC
        )
        assert out["from"] == ds.dates[50].isoformat()
        assert out["calendar"]["clippedFrom"] == ds.dates[5].isoformat()
        # 총액은 진입일부터 다 들어 있다 — 첫 점이 0 이 아닌 것이 그 증거다
        assert out["points"][0]["pnl"] != 0
        # 줄의 기록은 **진짜 진입일**을 그대로 든다
        assert out["positions"][0]["entry"] == ds.dates[5].isoformat()

    def test_a_book_inside_the_shared_calendar_is_not_flagged(self):
        ds = _dataset(300)
        m = _matrix(ds.dates)
        out = mb.run_backtest(
            m, ds, [_pos("3Y", 1, ds.dates[5]), _pos("CB:KTB:3Y", 1, ds.dates[5])], SPEC
        )
        assert out["calendar"]["clippedFrom"] is None
        assert out["points"][0]["pnl"] == 0

    def test_the_first_point_has_no_daily_change(self):
        ds = _dataset()
        m = _matrix(ds.dates)
        out = mb.run_backtest(
            m, ds, [_pos("3Y", 1, ds.dates[5]), _pos("CB:KTB:3Y", 1, ds.dates[5])], SPEC
        )
        assert out["points"][0]["d"] is None


# ── 4. 거절 ─────────────────────────────────────────────────────────────────


class TestRefusals:
    def test_a_bond_cannot_be_sold_even_beside_a_swap(self):
        """[OWNER, 2026-08-14 — "국고채는 매도는 없는거고"]. 스왑이 옆에 있다고
        규칙이 바뀌지 않는다."""
        ds = _dataset()
        m = _matrix(ds.dates)
        with pytest.raises(mb.MixedBookError) as e:
            mb.run_backtest(
                m, ds,
                [_pos("3Y", 1, ds.dates[5]), _pos("CB:KTB:3Y", -1, ds.dates[5])],
                SPEC,
            )
        assert "매수" in str(e.value)

    def test_an_empty_book_is_refused(self):
        with pytest.raises(mb.MixedBookError):
            mb.run_backtest(None, _dataset(), [], SPEC)

    def test_thirteen_rows_are_refused(self):
        ds = _dataset()
        book = [_pos("3Y", 1, ds.dates[5])] * 13
        with pytest.raises(mb.MixedBookError):
            mb.run_backtest(None, ds, book, SPEC)


# ── 5. 대사 ─────────────────────────────────────────────────────────────────


class TestRecon:
    """`book_recon` 은 표를 **둘**로 낸다 [OWNER, 2026-08-25 — 엔진 단위 분리].

    2026-08-21 병합판(민평 ∩ IRS 한 표)이 지불하던 대가 — 드롭(세로합 ≠ 기간
    3분해)·0 채움·병합 이월 앵커 — 는 전부 사라진다. 각 표는 그 엔진
    `book_recon` 의 모양 그대로이고, 이 파일은 분리 계약과 «각자 자기 달력
    위에 온전히 선다»만 지킨다. 각 표 내부의 산술은 엔진 자기 테스트
    (test_backtest_recon·test_cashbond)가 이미 핀으로 박고 있다.
    """

    def _recon(self):
        ds = _dataset(120)
        m = _matrix(ds.dates)
        book = [_pos("3Y", 1, ds.dates[5]), _pos("CB:KTB:3Y", 1, ds.dates[5])]
        return ds, m, mb.book_recon(m, ds, book, SPEC)

    def test_a_mixed_book_yields_two_tables(self):
        _ds, _m, r = self._recon()
        # [2026-08-25] 선물 합류로 키는 셋 — 선물 없는 북은 그 자리가 None 이다.
        assert set(r) == {"swap", "bond", "futures"}
        assert r["swap"] and r["bond"]
        assert r["futures"] is None
        # 각 표는 자기 엔진의 모양 그대로 — 접두사도 그룹 머리도 없다.
        for block in (r["swap"], r["bond"]):
            assert "groups" not in block
            assert all(":" not in t for t in block["tenors"])

    def test_each_table_closes_with_its_own_identity(self):
        """스왑: 평가+롤다운+캐리+개시 = 그날 손익. 채권: +조달까지.
        조달 열은 채권 표에만 있다 — 스왑에는 그 질문이 없다."""
        _ds, _m, r = self._recon()
        s_body = [x for x in r["swap"]["rows"] if not x.get("carryover")]
        b_body = [x for x in r["bond"]["rows"] if not x.get("carryover")]
        assert s_body and b_body
        for row in s_body:
            assert "funding" not in row
            # 순수 스왑에는 풀투파가 **없다** — 0 이 아니라 없다(공란 정책).
            assert row.get("pullToPar") is None
            total = row["valuation"] + row["rolldown"] + row["carry"] + (row.get("startup") or 0)
            assert total == pytest.approx(row["actual"], abs=2.0)
        for row in b_body:
            # ★채권 표에는 풀투파가 있다 [OWNER 2026-09-28 — 「칸을 나눈다」].
            # 롤다운 칸에서 떼어낸 그 몫이라, 항등식에 같이 안 넣으면 안 닫힌다.
            total = (
                row["valuation"] + row["rolldown"] + (row["pullToPar"] or 0)
                + row["carry"] + (row.get("startup") or 0) + (row["funding"] or 0)
            )
            assert total == pytest.approx(row["actual"], abs=2.0)

    def test_each_table_keeps_its_own_carryover_anchor(self):
        _ds, _m, r = self._recon()
        for block in (r["swap"], r["bond"]):
            anchor = block["rows"][-1]
            assert anchor["carryover"] is True
            assert anchor["actual"] is None and anchor["estTotal"] is None
            assert any(v for v in anchor["krd"].values())

    def test_a_calendar_gap_costs_nothing(self):
        """분리의 요점: 한쪽만 쉰 날이 있어도 **어느 표에서도 날이 빠지지
        않는다**. 병합판은 그 날과 다음 날을 떨궈야 했다(다른 밤 문제) — 각
        표가 자기 달력 위에 서면 그 문제 자체가 없다."""
        ds = _dataset(200)
        hole = ds.dates[150]
        m = _matrix([d for d in ds.dates if d != hole])
        book = [_pos("3Y", 1, ds.dates[5]), _pos("CB:KTB:3Y", 1, ds.dates[5])]
        r = mb.book_recon(m, ds, book, SPEC)
        s_dates = {x["t"] for x in r["swap"]["rows"] if not x.get("carryover")}
        b_dates = {x["t"] for x in r["bond"]["rows"] if not x.get("carryover")}
        # 스왑 표는 IRS 달력의 그 날을 그대로 싣고, 그 다음 날도 산다.
        assert hole.isoformat() in s_dates
        assert ds.dates[151].isoformat() in s_dates
        # 채권 표는 민평 달력대로 — 구멍 다음 날이 정상적으로 선다.
        assert hole.isoformat() not in b_dates
        assert ds.dates[151].isoformat() in b_dates

    def test_each_column_totals_its_engines_decomposition(self):
        """세로합 = 기간 3분해 — 병합판이 드롭 때문에 못 지키던 성질.

        각 표의 캐리·롤다운 열을 세로로 더하면 그 엔진 백테스트 레코드의
        기간 스칼라와 만나야 한다(포워드 귀속이라, 열린 북은 마지막 행의
        «오늘 밤» 하루만큼 스칼라보다 앞서간다 — app/backtest.py 모듈 주석).
        여기서는 그 이월 한 밤을 마지막 행에서 빼고 비교한다."""
        ds = _dataset(120)
        m = _matrix(ds.dates)
        book = [_pos("3Y", 1, ds.dates[5]), _pos("CB:KTB:3Y", 1, ds.dates[5])]
        r = mb.book_recon(m, ds, book, SPEC)
        bt = mb.run_backtest(m, ds, book, SPEC)
        swap_rec = next(p for p in bt["positions"] if p["kind"] == "swap")
        bond_rec = next(p for p in bt["positions"] if p["kind"] != "swap")
        for block, rec in ((r["swap"], swap_rec), (r["bond"], bond_rec)):
            body = [x for x in block["rows"] if not x.get("carryover")]
            tol = len(body) * 2.0
            last = body[-1]
            carry_open = last["carry"] or 0
            roll_open = last["rolldown"] or 0
            assert sum(x["carry"] for x in body) - carry_open == pytest.approx(
                rec["carry"], abs=tol
            )
            assert sum(x["rolldown"] for x in body) - roll_open == pytest.approx(
                rec["rolldown"], abs=tol
            )

    def test_a_pure_book_fills_one_slot(self):
        """한 종류뿐이면 그 엔진의 블록이 자기 자리에 서고 다른 쪽은 None."""
        ds = _dataset(120)
        r = mb.book_recon(None, ds, [_pos("3Y", 1, ds.dates[5])], SPEC)
        assert r["bond"] is None
        assert r["swap"] and all(":" not in k for k in r["swap"]["tenors"])

    def test_an_asset_swap_row_stands_as_two_legs_in_the_bond_table(self):
        """자산스왑은 채권 표 안에서 **하루 일곱 줄**이다 [OWNER 2026-09-04].

        다리마다 KRD·Δbp·손익 셋에 합계 한 줄. 여기서 재는 것은 그 다리가
        실려 오는가와 **합계가 다리 합인가**뿐이다 — 다리 산술 자체는
        `test_cashbond` 와 `test_mr_legrecon` 이 이미 박고 있다.
        """
        ds = _dataset(120)
        m = _matrix(ds.dates)
        r = mb.book_recon(m, ds, [_pos("ASW:KTB:3Y", 1, ds.dates[5])], SPEC)
        block = r["bond"]
        assert [lg["name"] for lg in block["legTenors"]] == ["국고", "IRS"]
        body = [x for x in block["rows"] if not x.get("carryover")]
        assert body
        for row in body:
            assert [lg["name"] for lg in row["legs"]] == ["국고", "IRS"]
            legs = row["legs"]
            for key in ("valuation", "carry", "rolldown", "actual"):
                assert row[key] == pytest.approx(
                    legs[0][key] + legs[1][key], abs=2.0), key
            # 조달은 국고 다리만 진다 — IRS 다리는 «그 질문이 없다»(공란).
            assert legs[1]["funding"] is None
            assert row["funding"] == legs[0]["funding"]

    def test_a_plain_cash_bond_book_stays_three_rows_a_day(self):
        """다리는 **자산스왑에만** 있다 — 현물채권은 다리가 하나뿐이라
        가를 것이 없고, 가르면 IRS KRD 범프 값(250일 5.55배)만 문다."""
        ds = _dataset(120)
        m = _matrix(ds.dates)
        r = mb.book_recon(m, ds, [_pos("CB:KTB:3Y", 1, ds.dates[5])], SPEC)
        assert "legTenors" not in r["bond"]
        assert all("legs" not in x for x in r["bond"]["rows"])


# ── 6. 라우트 ───────────────────────────────────────────────────────────────


class TestRoutes:
    """`/api/backtest` 가 두 문법을 다 받는다. 창이 하나이므로 라우트도 하나다."""

    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as c:
            yield c

    def test_a_swap_book_still_answers(self, client):
        r = client.get("/api/backtest", params={"positions": "10Y,1,1e10,2025-01-02"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["positions"][0]["kind"] == "swap"
        # 스왑만 있는 북은 조달도 달력 각주도 없다 — 없는 개념을 적지 않는다.
        assert "funding" not in body
        assert "calendar" not in body

    def test_a_mixed_book_answers_with_both_rows(self, client):
        r = client.get(
            "/api/backtest",
            params={
                "positions": "10Y,1,1e10,2025-01-02;CB:KTB:3Y,1,1e10,2025-01-02",
                "basis": "call",
                "spreadBp": 0,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert [p["kind"] for p in body["positions"]] == ["swap", "cashbond"]
        assert body["calendar"]["basis"] == "민평 ∩ IRS"
        assert body["funding"]["label"]
        # 대사는 표 둘이다 [OWNER, 2026-08-25] — 각자 자기 달력 위의 자기 표.
        assert body["recon"]["swap"] and body["recon"]["bond"]
        assert all(":" not in t for t in body["recon"]["swap"]["tenors"])
        assert all(":" not in t for t in body["recon"]["bond"]["tenors"])

    def test_selling_a_bond_is_refused_with_a_sentence(self, client):
        r = client.get(
            "/api/backtest",
            params={"positions": "10Y,1,1e10,2025-01-02;CB:KTB:3Y,-1,1e10,2025-01-02"},
        )
        assert r.status_code == 422
        assert "매수" in r.json()["detail"]

    def test_an_unknown_swap_id_still_says_so(self, client):
        r = client.get("/api/backtest", params={"positions": "42Y,1,1e10,2025-01-02"})
        assert r.status_code == 422
        assert "unknown instrument" in r.json()["detail"]
