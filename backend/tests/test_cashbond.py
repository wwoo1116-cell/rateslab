# -*- coding: utf-8 -*-
"""Cash Bond 엔진의 핀 [OWNER, 2026-08-14].

**합성 민평으로 돈다.** `credit_matrix` 는 SQL 에만 있고(이 배포의 `data/` 에는
Credit Matrix 워크북이 없다), 테스트가 사무실 네트워크 너머의 MariaDB 에
매달리면 비행기에서 게이트를 못 돌린다. 여기서 재는 것은 엔진의 산술이지 DB 의
가용성이 아니므로, 커브를 손으로 세운다. SQL 로더 자체는 `test_creditmatrix_*`
가 닿을 수 있을 때만 검사한다.

조달은 `base` 를 쓰되 **시계열을 여기서 시드한다** (V2). v1 에서 base 는 로컬
xlsx 라 그대로 읽었지만, v2 의 base 는 SQL `infomax.기준금리` 이고 그 테이블은
신선도 게이트에 걸려 있다(2026-03-21 정지 — funding.py 의 V2 절). 여기 시드하는
계단은 금통위 결정의 (발효일, %) 목록 — 시장데이터가 아니라 오너 검증 가능한
공개 사실이라 calendar.json 과 같은 성질이다. v1 `data/bokbaserate.xlsx` 에서
추출했고(2026-08-18), SQL 과 겹치는 3,733일이 전건 일치함을 같은 날 실측했다.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app import cashbond as cb
from app import creditmatrix as cm
from app import funding as fd

N = 1e10  # 100억


def _flat_curve(rate_pct: float) -> dict[str, float]:
    return {t: rate_pct for t in cm.TENOR_LABELS}


def synth(
    days: int = 400,
    curve=lambda i: _flat_curve(3.0),
    types=("KTB",),
    start=dt.date(2024, 1, 1),
) -> cm.CreditMatrix:
    """영업일 하루 간격의 합성 민평. `curve(i)` 가 그날의 {테너: %} 를 준다.

    달력을 주말 없이 하루씩 세는 것은 의도적이다 — 여기서 재는 것은 날짜 산술이
    아니라 가격 산술이고, 연속 달력이라야 '92일 뒤' 같은 단언이 눈으로 읽힌다.
    """
    dates = [start + dt.timedelta(days=k) for k in range(days)]
    values: dict[tuple[str, str], list[float | None]] = {}
    for t in types:
        for label in cm.TENOR_LABELS:
            values[(t, label)] = [curve(i).get(label) for i in range(days)]
    return cm.CreditMatrix(dates=dates, values=values, watermark=("synthetic", days))


SPEC0 = fd.FundingSpec("base", 0.0)

#: 한국은행 기준금리 계단 — (발효일, %). 모듈 독스트링의 근거 참조.
BOK_STAIRCASE: list[tuple[dt.date, float]] = [
    (dt.date(2016, 1, 1), 1.50),
    (dt.date(2016, 6, 9), 1.25),
    (dt.date(2017, 11, 30), 1.50),
    (dt.date(2018, 11, 30), 1.75),
    (dt.date(2019, 7, 18), 1.50),
    (dt.date(2019, 10, 16), 1.25),
    (dt.date(2020, 3, 17), 0.75),
    (dt.date(2020, 5, 28), 0.50),
    (dt.date(2021, 8, 26), 0.75),
    (dt.date(2021, 11, 25), 1.00),
    (dt.date(2022, 1, 14), 1.25),
    (dt.date(2022, 4, 14), 1.50),
    (dt.date(2022, 5, 26), 1.75),
    (dt.date(2022, 7, 13), 2.25),
    (dt.date(2022, 8, 25), 2.50),
    (dt.date(2022, 10, 12), 3.00),
    (dt.date(2022, 11, 24), 3.25),
    (dt.date(2023, 1, 13), 3.50),
    (dt.date(2024, 10, 11), 3.25),
    (dt.date(2024, 11, 28), 3.00),
    (dt.date(2025, 2, 25), 2.75),
    (dt.date(2025, 5, 29), 2.50),
    (dt.date(2026, 7, 16), 2.75),
]


@pytest.fixture(autouse=True)
def _seed_base_series():
    """base 시계열을 계단으로 시드한다 — `_ladder` 는 계단의 변화점만 있으면
    일별 시계열과 수학적으로 등가다(구간 적분이 같다). 게이트는 `_base_rate_series`
    안에 있으므로 캐시를 직접 채우면 지나가지 않는다 — 그것이 의도다: 여기서
    재는 것은 엔진의 산술이지 테이블의 신선도가 아니다."""
    fd.reset_cache()
    fd._series_cache["base"] = [(d, r / 100.0) for d, r in BOK_STAIRCASE]
    yield
    fd.reset_cache()


class TestBaseFreshnessGate:
    """멈춘 기준금리 피드는 실패 상태로 선다 (funding.py V2 절).

    2026-08-20 에 출처가 SQL `infomax.기준금리` 에서 **ECOS** 로 바뀌었다
    [OWNER — "ECOS API 로 아예 교체"]. 그래서 이 클래스는 이제 `mysqldb` 가
    아니라 `ecos` 를 가로챈다. 게이트 자체의 명제는 그대로다 — 멈춘 계단을
    평탄 연장하면 그 사이의 금통위를 조용히 놓친다.
    """

    def test_a_stale_series_is_refused_with_the_stop_date_named(self, monkeypatch):
        from app import ecos

        stale = [(dt.date(2026, 3, 21) - dt.timedelta(days=k), 0.025) for k in range(5, -1, -1)]
        monkeypatch.setattr(
            fd, "_call_rate_series", lambda: (_ for _ in ()).throw(AssertionError)
        )
        monkeypatch.setattr(ecos, "base_rate_series", lambda: list(stale))
        fd.reset_cache()
        with pytest.raises(fd.FundingError) as e:
            fd._base_rate_series()
        assert "2026-03-21" in str(e.value)
        assert "콜금리" in str(e.value)  # 대안을 같은 문장이 말한다

    def test_a_fresh_series_passes_the_gate(self, monkeypatch):
        from app import ecos

        today = dt.date.today()
        fresh = [(today - dt.timedelta(days=3), 0.025), (today, 0.0275)]
        monkeypatch.setattr(ecos, "base_rate_series", lambda: list(fresh))
        fd.reset_cache()
        s = fd._base_rate_series()
        assert s[-1] == (today, 0.0275)

    def test_an_ecos_failure_becomes_a_funding_sentence(self, monkeypatch):
        """ECOS 의 문장은 이미 사람 말이다 — 감싸되 덮지 않는다."""
        from app import ecos

        def boom():
            raise ecos.EcosError("ECOS_API_KEY 가 없습니다")

        monkeypatch.setattr(ecos, "base_rate_series", boom)
        fd.reset_cache()
        with pytest.raises(fd.FundingError) as e:
            fd._base_rate_series()
        assert "ECOS_API_KEY" in str(e.value)

    def test_the_default_basis_is_base(self):
        """[OWNER, 2026-08-20 — "조달 기본값은 한은 기준금리"].

        2026-08-19 까지 이 자리는 `call` 을 핀하고 있었고, 근거는 "base 가
        게이트 뒤라 기본이 될 수 없다" 였다. 출처를 ECOS 로 옮겨 그 근거가
        없어졌다 — 완화가 아니라 명제가 바뀐 것이다."""
        assert fd.DEFAULT_BASIS == "base"


# ── 가격의 기준선 ───────────────────────────────────────────────────────────


class TestParIdentity:
    """쿠폰 = 수익률이면 값은 정확히 액면이다. 이 화면 전체가 그 위에 선다."""

    @pytest.mark.parametrize("tenor", cm.TENOR_LABELS)
    @pytest.mark.parametrize("y", [0.001, 0.0378, 0.05, 0.15])
    def test_entry_price_is_exactly_par(self, tenor, y):
        n = cb.periods_for(tenor)
        dirty, accrued, coupons, redeemed = cb.price(y, y, n, 0.0)
        assert abs(dirty - 1.0) < 1e-12, (tenor, y, dirty)
        assert accrued == 0.0
        assert coupons == 0.0
        assert redeemed == 0.0

    def test_a_coupon_above_the_yield_prices_above_par(self):
        n = cb.periods_for("10Y")
        assert cb.price(0.03, 0.04, n, 0.0)[0] > 1.0
        assert cb.price(0.04, 0.03, n, 0.0)[0] < 1.0

    def test_coupons_pay_on_the_quarter_and_accrual_resets(self):
        n = cb.periods_for("3Y")
        c = 0.04 / 4
        just_before = cb.price(0.04, 0.04, n, 0.25 - 1e-7)
        on_the_day = cb.price(0.04, 0.04, n, 0.25)
        # 직전: 한 기 전액이 경과이자로 서 있고 받은 이표는 아직 0
        assert just_before[1] == pytest.approx(c, rel=1e-4)
        assert just_before[2] == 0.0
        # 당일: 경과이자는 0 으로 떨어지고 그 금액이 받은 이표로 넘어간다
        assert on_the_day[1] == 0.0
        assert on_the_day[2] == pytest.approx(c)
        # 만기가 아니므로 상환액면은 양쪽 다 0
        assert just_before[3] == 0.0 and on_the_day[3] == 0.0
        # dirty + 받은 이표는 그 경계에서 이어진다 (톱니가 없다)
        assert just_before[0] + just_before[2] == pytest.approx(
            on_the_day[0] + on_the_day[2], abs=1e-6
        )


# ── 백테스트의 항등식 ───────────────────────────────────────────────────────


class TestDecomposition:
    def test_entry_day_is_zero_in_every_bucket(self):
        """진입한 날 손익은 0 이다 — par 로 샀으니까. IRS 쪽에서 진입일에
        롤다운이 서던 결함(2026-08-14 개시 분리)의 현금채권 판 예방핀이다."""
        m = synth()
        pos = cb.BondPosition("CB", "KTB", "3Y", 1, N, m.dates[0], m.dates[0])
        r = cb.run_backtest(m, None, [pos], SPEC0)
        p = r["positions"][0]
        for k in ("pnl", "valuation", "carry", "rolldown", "funding", "startup"):
            assert p[k] == 0, k
        assert r["points"][0]["pnl"] == 0

    def test_the_five_buckets_sum_to_the_pnl(self):
        m = synth(days=500, curve=lambda i: {
            t: 3.0 + 0.5 * cm.TENOR_YEARS[t] / 10 + 0.002 * i for t in cm.TENOR_LABELS
        })
        book = [
            cb.BondPosition("CB", "KTB", "3Y", 1, N, m.dates[10]),
            cb.BondPosition("CB", "KTB", "10Y", 1, 2 * N, m.dates[40], m.dates[300]),
            cb.BondPosition("CB", "KTB", "1Y", 1, N, m.dates[5]),
        ]
        r = cb.run_backtest(m, None, book, SPEC0)
        for p in r["positions"]:
            parts = p["valuation"] + p["carry"] + p["rolldown"] + p["funding"] + p["startup"]
            assert abs(parts - p["pnl"]) <= 2, p["id"]

    def test_a_frozen_flat_curve_is_carry_and_nothing_else(self):
        """커브가 평평하고 멈춰 있으면 남는 것은 쿠폰뿐이다.

        평가는 정확히 0 이다 — 커브가 안 움직였으니까. 롤다운은 정확히 0 이
        **아니라** 예산 안이다: par 채권의 clean 가격은 이표기간 안에서 완전히
        평평하지 않다(할인은 복리, 경과이자는 단리라는 관행 조합의 결과로 기간
        중앙에서 액면의 1.2e-5 만큼 처졌다가 이표일에 돌아온다). 그 톱니는
        clean 변화이므로 롤다운 칸에 앉는 것이 맞고, 크기는 액면의 0.01bp
        미만이어야 한다. 이 예산이 깨지면 규약이 아니라 산술이 틀린 것이다.
        """
        m = synth(days=200, curve=lambda i: _flat_curve(3.0))
        entry = m.dates[0]
        pos = cb.BondPosition("CB", "KTB", "5Y", 1, N, entry, m.dates[92])
        r = cb.run_backtest(m, None, [pos], SPEC0)
        p = r["positions"][0]
        assert p["coupon"] == pytest.approx(3.0, abs=1e-9)
        assert abs(p["valuation"]) <= 1
        assert abs(p["rolldown"]) / N * 1e4 <= 0.01, p["rolldown"]
        # 92일치 쿠폰. 같은 규약 차이만큼만 어긋난다.
        expected = N * 0.03 * 92 / 365
        assert p["carry"] == pytest.approx(expected, rel=2e-4)

    def test_the_clean_price_sawtooth_stays_inside_its_budget(self):
        """위 예산의 근거를 직접 잰다 — 이표기간 안에서 par 채권의 clean 이
        얼마나 처지는가. 액면의 2e-5 를 넘으면 할인/경과이자 규약이 어긋난
        것이다."""
        n = cb.periods_for("10Y")
        worst = max(
            abs(cb.price(0.04, 0.04, n, k / 10_000)[0] - cb.price(0.04, 0.04, n, k / 10_000)[1] - 1.0)
            for k in range(0, 2500)
        )
        assert worst < 2e-5, worst

    def test_an_upward_curve_rolls_down_into_profit_for_a_buyer(self):
        """기울어진 커브가 멈춰 있으면 매수자는 롤다운으로 번다 — 잔존만기가
        줄며 더 낮은 금리로 값이 매겨진다. 평가는 여전히 0 이어야 한다."""
        m = synth(days=200, curve=lambda i: {
            t: 2.0 + 0.1 * cm.TENOR_YEARS[t] for t in cm.TENOR_LABELS
        })
        pos = cb.BondPosition("CB", "KTB", "5Y", 1, N, m.dates[0], m.dates[92])
        p = cb.run_backtest(m, None, [pos], SPEC0)["positions"][0]
        assert abs(p["valuation"]) <= 1, p["valuation"]
        assert p["rolldown"] > 0
        # 기울기 10bp/년 × 0.25년 = 2.5bp, 4.75Y 채권의 DV01 근방
        assert 5e6 < p["rolldown"] < 15e6, p["rolldown"]

    def test_selling_is_refused_rather_than_silently_priced(self):
        """매수뿐이다 [OWNER, 2026-08-14 — "국고채는 매도는 없는거고"].

        엔진은 부호를 다룰 줄 알지만(아래에서 거울임을 확인한다) **북 단계에서
        막는다**: 공매도는 채권을 빌리는 것이고 그 대차료를 이 화면은 모른다.
        모르는 비용을 0 으로 두면 공매도가 늘 이기는 백테스트가 된다."""
        m = synth(days=200)
        with pytest.raises(cb.CashBondError, match="매수만"):
            cb.run_backtest(
                m, None, [cb.BondPosition("CB", "KTB", "3Y", -1, N, m.dates[10])], SPEC0
            )

    def test_the_engine_itself_is_sign_symmetric(self):
        """거절은 상품의 규칙이지 산술의 한계가 아니다 — 다리 단계에서는 부호가
        정확히 거울이다. 나중에 대차료가 생겨 매도를 열 때, 그때 열 것이 이미
        맞다는 증거."""
        m = synth(days=200, curve=lambda i: {
            t: 3.0 + 0.05 * cm.TENOR_YEARS[t] + 0.003 * i for t in cm.TENOR_LABELS
        })
        e, x = m.dates[10], m.dates[120]
        sample = list(range(10, 121))
        out = []
        for d in (1, -1):
            pos = cb.BondPosition("CB", "KTB", "3Y", d, N, e, x)
            rec, _own, _prev = cb.run_bond_leg(m, pos, cb._bond_leg(m, pos), sample, SPEC0)
            out.append(rec)
        for k in ("valuation", "carry", "rolldown"):
            assert abs(out[0][k] + out[1][k]) <= 2, k
        assert out[1]["funding"] == 0  # 조달은 매수 원금에만 붙는다


class TestFunding:
    def test_funding_follows_the_policy_staircase_not_a_constant(self):
        """2020년 구간은 그 시점 기준금리로 조달해야 한다 — 오늘 값으로 전
        기간을 칠하면 옛 구간의 캐리가 통째로 거짓이 된다."""
        spec = fd.FundingSpec("base", 10.0)
        old = fd.rate_on(spec, dt.date(2020, 6, 1))
        new = fd.rate_on(spec, dt.date(2026, 8, 13))
        assert old < new
        assert old == pytest.approx(0.0050 + 0.0010, abs=1e-9)   # 기준금리 0.50%
        assert new == pytest.approx(0.0275 + 0.0010, abs=1e-9)   # 기준금리 2.75%

    def test_cost_is_act_365_on_the_purchase_price(self):
        spec = fd.FundingSpec("base", 10.0)
        d0, d1 = dt.date(2026, 7, 16), dt.date(2026, 8, 13)  # 인상 이후 구간 28일
        got = fd.cost_between(spec, d0, d1, N)
        assert got == pytest.approx(N * 0.0285 * 28 / 365, rel=1e-9)

    def test_the_spread_moves_the_cost_linearly(self):
        d0, d1 = dt.date(2026, 7, 16), dt.date(2026, 8, 13)
        a = fd.cost_between(fd.FundingSpec("base", 0.0), d0, d1, N)
        b = fd.cost_between(fd.FundingSpec("base", 10.0), d0, d1, N)
        assert b - a == pytest.approx(N * 0.0010 * 28 / 365, rel=1e-9)

    def test_a_wild_spread_is_refused_rather_than_silently_priced(self):
        with pytest.raises(fd.FundingError):
            fd.FundingSpec("base", 10_000.0).validated()
        with pytest.raises(fd.FundingError):
            fd.FundingSpec("무엇", 10.0).validated()


class TestSpanAndUniverse:
    def test_a_bond_stops_at_its_own_maturity(self):
        m = synth(days=400)
        pos = cb.BondPosition("CB", "KTB", "3M", 1, N, m.dates[0])
        p = cb.run_backtest(m, None, [pos], SPEC0)["positions"][0]
        assert p["matured"] is True
        # 91.25일 = 3개월. 하루 간격 달력이라 그 자리에서 멈춘다.
        assert (dt.date.fromisoformat(p["exit"]) - m.dates[0]).days == 91

    def test_a_tenor_the_type_does_not_have_is_refused(self):
        """통안채 5Y 처럼 **없는 만기**는 조용히 보간하지 않고 세운다. 0 을
        금리로 읽는 것이 이 테이블의 가장 큰 함정이라(creditmatrix 주석),
        없는 것은 없다고 말해야 한다."""
        m = synth(types=("MSB",))
        m = cm.CreditMatrix(
            dates=m.dates,
            values={k: v for k, v in m.values.items() if cm.TENOR_YEARS[k[1]] <= 3.0},
            watermark=m.watermark,
        )
        assert m.tenors_for("MSB") == ["3M", "6M", "9M", "1Y", "1.5Y", "2Y", "2.5Y", "3Y"]
        with pytest.raises(cb.CashBondError):
            cb.run_backtest(m, None, [cb.BondPosition("CB", "MSB", "5Y", 1, N, m.dates[0])], SPEC0)

    def test_asset_swap_only_where_both_markets_have_the_tenor(self):
        m = synth()
        for tenor in ("2.5Y", "20Y", "30Y"):
            with pytest.raises(cb.CashBondError):
                cb.run_backtest(
                    m, None, [cb.BondPosition("ASW", "KTB", tenor, 1, N, m.dates[0])], SPEC0
                )

    def test_ids_round_trip_and_junk_is_refused(self):
        assert cb.parse_id("CB:KTB:3Y") == ("CB", "KTB", "3Y")
        assert cb.parse_id("ASW:CB1:10Y") == ("ASW", "CB1", "10Y")
        for bad in ("KTB:3Y", "XX:KTB:3Y", "CB:없음:3Y", "CB:KTB:4Y"):
            with pytest.raises(cb.CashBondError):
                cb.parse_id(bad)

    def test_the_eight_types_are_the_owners_list(self):
        """[OWNER, 2026-08-14] 여덟이다. CB2~CB5 는 테이블에 있어도 이 화면의
        유니버스가 아니다."""
        assert list(cm.BOND_TYPES) == [
            "KTB", "MSB", "KDB", "SPB", "BD", "CB1", "CARD", "OFB",
        ]
        assert cm.BOND_TYPES["OFB"] == "캐피탈채 AA-"  # 기타금융채를 이렇게 부른다


class TestZeroIsMissing:
    """SQL 은 없는 값을 0.0 으로 채운다(NULL 이 아니라). 0 을 금리로 읽으면
    통안채 10년이 0% 로 그려지고 보간이 커브 전체를 끌어내린다 — 이 리포에서
    가장 비싼 오독이라 규칙에 핀을 둔다."""

    def test_zero_is_read_as_missing_not_as_a_rate(self):
        assert cm.rate_or_none(0) is None
        assert cm.rate_or_none(0.0) is None
        assert cm.rate_or_none(None) is None
        assert cm.rate_or_none(3.777) == 3.777
        assert cm.rate_or_none(-0.5) == -0.5  # 음수 금리는 결측이 아니다

    def test_a_missing_tenor_is_absent_from_the_curve_never_zero(self):
        m = synth(days=3, curve=lambda i: {**_flat_curve(3.0), "30Y": None})
        pts = cm.curve_points(m, "KTB", 0)
        assert all(r > 0 for _y, r in pts)
        assert 30.0 not in [y for y, _r in pts]
        # 그 만기를 물으면 있는 마지막 점으로 평탄 외삽한다 — 0 이 아니다
        assert cm.yield_at(m, "KTB", 0, 30.0) == pytest.approx(0.03)


# ── 라우트 ──────────────────────────────────────────────────────────────────
# 여기서부터는 **SQL 이 닿아야** 돈다 — 민평의 유일한 출처이기 때문이다.
# 닿지 않으면 건너뛴다: 네트워크가 없다는 사실이 엔진의 결함으로 보고되면
# 게이트가 거짓말을 하는 것이다.


def _sql_reachable() -> bool:
    try:
        cm.watermark()
        return True
    except Exception:
        return False


pytestmark_live = pytest.mark.skipif(
    not _sql_reachable(), reason="credit_matrix SQL 에 닿지 않습니다"
)


@pytestmark_live
class TestRoutes:
    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as c:
            yield c

    def test_instruments_carry_every_row_precomputed(self, client):
        r = client.get("/api/cashbond/instruments")
        assert r.status_code == 200
        body = r.json()
        assert body["rows"], "행이 하나도 없다"
        ids = {row["id"] for row in body["rows"]}
        # 통안채는 3Y 까지만, 30Y 는 국고채·공사채만 — 데이터가 강제하는 제약
        assert "CB:MSB:3Y" in ids
        assert "CB:MSB:5Y" not in ids
        assert "CB:KTB:30Y" in ids
        assert "CB:BD:30Y" not in ids
        # 자산스왑은 양쪽에 있는 만기만
        assert "ASW:KTB:3Y" in ids
        assert "ASW:KTB:20Y" not in ids
        for row in body["rows"]:
            assert row["now"] is not None
            assert set(row["changes"]) == {"d1", "mtd", "ytd"}

    def test_backtest_runs_and_the_buckets_close(self, client):
        r = client.get(
            "/api/cashbond/backtest",
            params={"positions": "CB:KTB:3Y,1,1e10,2026-05-13", "basis": "base", "spreadBp": 10},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        p = body["positions"][0]
        parts = p["valuation"] + p["carry"] + p["rolldown"] + p["funding"] + p["startup"]
        assert abs(parts - p["pnl"]) <= 2
        assert p["funding"] < 0, "매수는 조달비용이 음수로 선다"
        assert body["funding"]["label"] == "기준금리 +10bp"

    def test_an_asset_swap_carries_the_swap_legs_startup(self, client):
        r = client.get(
            "/api/cashbond/backtest",
            params={"positions": "ASW:KTB:3Y,1,1e10,2026-05-13"},
        )
        assert r.status_code == 200, r.text
        p = r.json()["positions"][0]
        # 스왑 다리는 스팟 시작이라 개시가 산다 [OWNER, 2026-08-14]
        assert p["startup"] != 0
        assert p["swapPnl"] is not None
        assert p["aswSpread"] is not None

    def test_a_cash_bond_has_no_startup_night(self, client):
        r = client.get(
            "/api/cashbond/backtest",
            params={"positions": "CB:KTB:3Y,1,1e10,2026-05-13"},
        )
        # 이 채권은 진입일에 발행돼 진입일부터 경과이자가 붙는다 — 셀 밤이 없다
        assert r.json()["positions"][0]["startup"] == 0

    @pytest.mark.parametrize("bad", [
        "",                                    # 빈 요청
        "KTB,1,1e10,2026-05-13",               # id 문법 아님
        "CB:MSB:10Y,1,1e10,2026-05-13",        # 통안채에 없는 만기
        "ASW:KTB:20Y,1,1e10,2026-05-13",       # IRS 에 없는 만기
        "CB:KTB:3Y,1,1e10",                    # 필드 부족
    ])
    def test_bad_requests_are_refused_with_a_reason(self, client, bad):
        r = client.get("/api/cashbond/backtest", params={"positions": bad})
        assert r.status_code == 422, (bad, r.text)
        assert r.json()["detail"]

    def test_the_funding_setting_route_reports_its_source(self, client):
        r = client.get("/api/settings/funding", params={"basis": "call", "spreadBp": 25})
        assert r.status_code == 200
        body = r.json()
        assert body["basisLabel"] == "콜금리"
        assert body["label"] == "콜금리 +25bp"
        assert body["from"] < body["to"]
        assert {o["id"] for o in body["options"]} == {"base", "call"}
        bad = client.get("/api/settings/funding", params={"basis": "무엇"})
        assert bad.status_code == 422


class TestThetaConventions:
    """세타의 두 규약 [OWNER, 2026-08-14] — 조용히 드리프트할 수 있는 것들.

    ① **하루치**다. 계산 창은 분기이고 표기만 일 단위인데(근거는
       `app/theta.py:HORIZON_Y`), 그 나누기가 빠지거나 두 번 되면 열이 91배
       틀리고 아무 테스트도 안 걸린다 — 부호도 순위도 그대로이기 때문이다.
    ② **조달을 빼지 않는다**. 시장 관행(carry = y − 레포)과 다른 선택이라,
       누가 "관행대로" 되돌려 놓으면 여기가 먼저 말한다.
    """

    def _curve(self):
        # 평평한 3% 커브 — 롤다운이 0 이라 캐리만 남는다
        return synth(days=400, curve=lambda i: _flat_curve(3.0))

    def test_carry_is_one_days_coupon_on_the_notional(self):
        m = self._curve()
        th = cb.theta_for_bond(m, "KTB", "5Y", len(m.dates) - 1)
        assert th is not None
        # 100억 × 3% ÷ 365. 이표기간 안의 복리/단리 규약 차이만큼만 어긋난다.
        assert th["carry"] == pytest.approx(1e10 * 0.03 / 365, rel=2e-3)

    def test_funding_is_not_subtracted(self):
        """조달이 다시 들어오면 캐리가 (3% − 2.85%) 쪽으로 확 줄어든다."""
        m = self._curve()
        th = cb.theta_for_bond(m, "KTB", "5Y", len(m.dates) - 1)
        gross = 1e10 * 0.03 / 365
        net = 1e10 * (0.03 - 0.0285) / 365  # 기준금리 2.75 + 10bp 를 뺐다면
        assert abs(th["carry"] - gross) < abs(th["carry"] - net)
        # 함수가 조달 스펙을 아예 안 받는다 — 받으면 언젠가 쓰인다
        import inspect

        assert "spec" not in inspect.signature(cb.theta_for_bond).parameters

    def test_a_flat_curve_has_no_rolldown(self):
        m = self._curve()
        th = cb.theta_for_bond(m, "KTB", "5Y", len(m.dates) - 1)
        # 액면의 0.01bp 예산 — clean 가격의 이표기간 톱니(위 참조)만 남는다
        assert abs(th["roll"]) / 1e10 * 1e4 <= 0.01, th["roll"]

    def test_an_upward_curve_rolls_the_buyer_into_profit(self):
        m = synth(days=400, curve=lambda i: {
            t: 2.0 + 0.1 * cm.TENOR_YEARS[t] for t in cm.TENOR_LABELS
        })
        th = cb.theta_for_bond(m, "KTB", "5Y", len(m.dates) - 1)
        assert th["roll"] > 0
        assert th["perDv01"] > 0  # 캐리도 롤도 매수에 유리한 커브다

    def test_a_tenor_that_would_mature_inside_the_window_has_none(self):
        """호라이즌을 지나고도 한 분기는 남아야 롤다운이 뜻이 있다 — 커브
        가장자리는 보간이 지배한다(IRS 쪽 문턱과 같은 규칙)."""
        m = self._curve()
        assert cb.theta_for_bond(m, "KTB", "3M", len(m.dates) - 1) is None
        assert cb.theta_for_bond(m, "KTB", "6M", len(m.dates) - 1) is not None


class TestHeldToMaturity:
    """만기까지 들고 있으면 무슨 일이 일어나야 하는가 [2026-08-14].

    오너가 "만기까지 보유한 채권 백테스트 손익이 이상하다" 로 잡아낸 결함의
    회귀 핀이다. 두 가지가 틀려 있었고 둘 다 총액과 분해에서 다르게 드러났다:

    ① `price` 의 결제현금에 **액면 상환이 빠져** 있었다. `dirty` 는 안 온
       현금흐름의 현재가치라 만기에 0 이 되는데, 그때 나간 액면 1 이 현금에
       안 잡히면 `dirty + 현금` 이 1.04 에서 0.04 로 떨어진다 — 만기 보유가
       **원금 전액 손실**로 찍혔다. FTSE Russell 의 지수 계산 규칙이 total
       return 의 cash 항을 "coupons **and any principal repayments**" 로
       정의하는 그대로다.

    ② 고치고 나니 이번엔 그 액면이 **캐리**로 들어갔다(만기 보유 3Y 캐리
       110억). 상환된 액면은 소득이 아니라 자본 회수라 가격 쪽이다.

    그래서 이 클래스가 못박는 것은 **총액과 분해 둘 다**이다.
    """

    def _ran(self, tenor: str, coupon_pct: float = 3.0):
        m = synth(days=1600, curve=lambda i: _flat_curve(coupon_pct))
        pos = cb.BondPosition("CB", "KTB", tenor, 1, N, m.dates[0])
        return m, cb.run_backtest(m, None, [pos], SPEC0)["positions"][0]

    def test_the_position_actually_reaches_maturity(self):
        _m, p = self._ran("3Y")
        assert p["matured"] is True

    def test_dirty_plus_settled_is_continuous_across_maturity(self):
        """만기 직전과 직후에 절벽이 없어야 한다 — 그 절벽이 결함의 얼굴이었다."""
        n = cb.periods_for("1Y")
        before = cb.price(0.04, 0.04, n, 1.0 - 1e-6)
        after = cb.price(0.04, 0.04, n, 1.0)
        worth = lambda t: t[0] + t[2] + t[3]  # dirty + 이표 + 상환액면  # noqa: E731
        assert worth(after) == pytest.approx(worth(before), abs=1e-6)
        assert worth(after) == pytest.approx(1.04)

    def test_price_and_rolldown_cancel_at_maturity(self):
        """par 로 사서 par 를 돌려받았으니 **가격으로 번 돈은 0** 이다.
        평가와 롤다운은 각자 0 이 아니어도 되지만 합은 0 이어야 한다."""
        _m, p = self._ran("3Y")
        assert abs(p["valuation"] + p["rolldown"]) <= 2, (p["valuation"], p["rolldown"])

    def test_the_pnl_is_coupons_minus_funding(self):
        m, p = self._ran("3Y", coupon_pct=3.0)
        days = (
            dt.date.fromisoformat(p["exit"]) - dt.date.fromisoformat(p["entry"])
        ).days
        coupons = N * 0.03 * days / 365
        assert p["carry"] == pytest.approx(coupons, rel=2e-3)
        assert p["pnl"] == pytest.approx(coupons + p["funding"], rel=2e-3)

    def test_accrual_stops_at_maturity(self):
        """만기 뒤에도 경과이자가 자라면 프로즌 테일이 조용히 부풀어 오른다."""
        n = cb.periods_for("1Y")
        for e in (1.0, 1.5, 3.0):
            _d, accrued, coupons, redeemed = cb.price(0.04, 0.04, n, e)
            assert accrued == 0.0
            assert coupons == pytest.approx(0.04)
            assert redeemed == 1.0


class TestFundingOnTheInitialInvestment:
    """조달은 **초기 투자금액**에 붙는다 [OWNER, 2026-08-14 — "조달은 초기 투자
    금액 기준으로 붙여야 함"].

    par 로 샀으므로 곧 액면이고, 이표가 들어와도 줄지 않는다. 잠깐 잔액 기준으로
    바꿨다가 오너가 되돌렸다 — 텀 레포로 매수금액을 통째로 조달하는 것이 데스크의
    방식이고, 이표로 차입을 갚아 나가는 것은 별개의 자금관리다. 그 구현과 실측은
    `git show 021f2894`. 여기서 못박는 것은 **다시 잔액 기준이 되면 걸린다**는 것.
    """

    SPEC = fd.FundingSpec("base", 10.0)

    def _run(self, tenor: str, coupon_pct: float):
        m = synth(days=1600, curve=lambda i: _flat_curve(coupon_pct))
        pos = cb.BondPosition("CB", "KTB", tenor, 1, N, m.dates[0])
        p = cb.run_backtest(m, None, [pos], self.SPEC)["positions"][0]
        return m, p

    def test_it_is_exactly_the_notional_funded_for_the_whole_span(self):
        _m, p = self._run("3Y", 4.0)
        expect = -fd.cost_between(
            self.SPEC,
            dt.date.fromisoformat(p["entry"]),
            dt.date.fromisoformat(p["exit"]),
            N,
        )
        assert p["funding"] == pytest.approx(expect, abs=1.0)

    def test_the_coupon_size_does_not_change_it(self):
        """쿠폰이 크든 작든 조달은 같다 — 초기 투자금액에만 붙으므로."""
        _m, low = self._run("3Y", 1.0)
        _m, high = self._run("3Y", 8.0)
        assert low["funding"] == pytest.approx(high["funding"], abs=1.0)

    def test_the_five_buckets_still_close(self):
        _m, p = self._run("3Y", 4.0)
        parts = p["valuation"] + p["carry"] + p["rolldown"] + p["funding"] + p["startup"]
        assert abs(parts - p["pnl"]) <= 2

class TestBookRecon:
    """일별 대사 [OWNER, 2026-08-14 — "현금채권/자산스왑 백테스트에서도 대사
    가능하게"]. IRS 쪽 `backtest.book_recon` 과 같은 규약이고, 조달 칸이 하나
    더 있다.

    여기서 못박는 것 넷 — 전부 조용히 깨질 수 있는 것들이다:

    ① 행 항등식. 네 성분이 그날 손익으로 닫혀야 한다.
    ② KRD 가 **성기다**. 단일수익률 할인이라 잔존만기를 감싸는 두 노드에만
       가중치가 실린다. 전 노드에 퍼지면 보간이 아니라 딴 것을 재고 있다.
    ③ 일별 합 = 백테스트 총액.
    ④ 포워드 세타는 **동결 커브**로 잰다. 처음 넣었을 때 내일 커브로 재는
       바람에 평가 열이 통째로 0 이 됐다 — 커브 무브까지 롤다운이 먹었고,
       행 항등식은 그래도 닫혀서 ①만으로는 안 잡혔다.
    """

    SPEC = fd.FundingSpec("base", 10.0)

    def _flat(self):
        return synth(days=400, curve=lambda i: _flat_curve(3.0))

    def _sloped(self):
        return synth(days=400, curve=lambda i: {
            t: 2.0 + 0.1 * cm.TENOR_YEARS[t] + 0.004 * i for t in cm.TENOR_LABELS
        })

    def _recon(self, m, tenor="3Y", start=10):
        pos = cb.BondPosition("CB", "KTB", tenor, 1, N, m.dates[start])
        return pos, cb.book_recon(m, None, [pos], self.SPEC)

    def test_every_row_is_an_identity(self):
        _pos, rc = self._recon(self._sloped())
        rows = [r for r in rc["rows"] if r["actual"] is not None]
        assert rows
        for r in rows:
            parts = r["valuation"] + r["carry"] + r["rolldown"] + r["funding"]
            assert abs(r["actual"] - parts) <= 2, r["t"]
            assert r["residual"] == r["valuation"] - r["estTotal"]

    def test_krd_lands_only_on_the_bracketing_nodes(self):
        _pos, rc = self._recon(self._sloped(), tenor="3Y")
        rows = [r for r in rc["rows"] if r["actual"] is not None]
        # 진입 직후: 잔존 ~3Y 라 2.5Y·3Y 두 노드에만 실려야 한다
        loaded = [lb for lb, v in rows[1]["krd"].items() if v]
        assert set(loaded) <= {"2.5Y", "3Y"}, loaded
        assert loaded, "KRD 가 전부 0 이면 범프가 안 걸린 것이다"

    def test_the_daily_rows_sum_to_the_backtest_total(self):
        """대사표가 총액과 안 맞으면 대사표가 아니다.

        이 핀이 잡는 것: 마지막 행이 **다음 마킹이 없는 밤**의 세타를 손익
        칸에 넣는 것. 넣으면 합이 딱 그 한 밤만큼 총액을 넘고, 행 항등식은
        그래도 닫혀서 ①로는 안 잡힌다 (IRS 표가 지금 그렇다 — 실측
        2026-08-14: 합−총액 −314,139원 = 마지막 행 캐리+롤 −314,142원).
        """
        m = synth(days=200, curve=lambda i: {
            t: 2.0 + 0.1 * cm.TENOR_YEARS[t] + 0.004 * i for t in cm.TENOR_LABELS
        })
        pos, rc = self._recon(m)
        assert rc["truncated"] is False, "창이 잘리면 합이 총액과 다른 게 정상이다"
        bt = cb.run_backtest(m, None, [pos], self.SPEC)["positions"][0]
        total = sum(r["actual"] for r in rc["rows"] if r["actual"] is not None)
        assert abs(total - bt["pnl"]) <= len(rc["rows"])

    def test_a_truncated_window_says_so(self):
        """250행 창보다 긴 북은 잘린다. 잘렸다고 말해야 화면이 '이게 전부'라고
        읽지 않는다 — 그때는 합이 총액과 달라도 맞는 것이다."""
        _pos, rc = self._recon(self._sloped())  # 400일
        assert rc["truncated"] is True
        assert len(rc["rows"]) <= cb.RECON_MAX_DAYS + 1  # +1 = 이월 앵커

    def test_a_frozen_curve_puts_nothing_in_valuation(self):
        """커브가 안 움직이면 평가는 0 이고 전부 캐리·롤다운이다. 이 핀이
        ④를 잡는다 — 동결 재평가를 빼먹으면 반대로 평가가 전부 0 이 되는데,
        그건 **움직이는** 커브에서만 보인다. 그래서 둘 다 잰다."""
        _pos, rc = self._recon(self._flat())
        rows = [r for r in rc["rows"] if r["actual"] is not None]
        for r in rows[1:-1]:
            assert abs(r["valuation"]) / N * 1e4 <= 0.01, (r["t"], r["valuation"])
            assert r["carry"] != 0

    def test_a_moving_curve_puts_something_in_valuation(self):
        _pos, rc = self._recon(self._sloped())
        rows = [r for r in rc["rows"] if r["actual"] is not None]
        moved = [r for r in rows[1:-1] if abs(r["valuation"]) > 1000]
        assert len(moved) > len(rows) // 2, "평가 열이 거의 비었다 — 동결 재평가를 의심할 것"

    def test_the_carryover_anchor_carries_risk_but_no_pnl(self):
        """열린 북은 내일 아침에도 리스크가 있다. 데이터가 끊긴 것이 포지션을
        없애지는 않으므로 앵커의 KRD 는 0 이 아니어야 한다 — 0 이면 화면이
        '북이 비었다'고 거짓말한다."""
        _pos, rc = self._recon(self._sloped())
        anchor = rc["rows"][-1]
        assert anchor.get("carryover") is True
        assert sum(1 for r in rc["rows"] if r.get("carryover")) == 1
        for key in ("estTotal", "actual", "valuation", "rolldown", "carry", "funding"):
            assert anchor[key] is None, key
        assert any(v != 0 for v in anchor["krd"].values())

    def test_a_matured_book_carries_nothing_over(self):
        """반대쪽. 만기가 와서 끝난 북은 진짜로 비었다 — 이월 리스크 0."""
        m = self._sloped()
        pos = cb.BondPosition("CB", "KTB", "3M", 1, N, m.dates[10])
        rc = cb.book_recon(m, None, [pos], self.SPEC)
        assert all(v == 0 for v in rc["rows"][-1]["krd"].values())

    def test_an_asset_swap_book_needs_the_irs_dataset(self):
        """자산스왑 행은 스프레드 격자를 흔든다 — 그 행이 호가하는 값이
        스프레드이고, par-par 라 패키지 손익 ≈ −D×Δ스프레드 이기 때문이다.
        그래서 IRS 쪽이 없으면 세울 수가 없고, 조용히 민평으로 떨어지는 대신
        말을 해야 한다."""
        m = self._sloped()
        pos = cb.BondPosition("ASW", "KTB", "3Y", 1, N, m.dates[10])
        with pytest.raises(cb.CashBondError):
            cb.book_recon(m, None, [pos], self.SPEC)


@pytestmark_live
class TestReconTiesOutOnLiveData:
    """대사표가 백테스트 총액과 맞는가 — **실데이터로**.

    합성 커브로는 자산스왑을 못 세운다(IRS 데이터셋이 필요하다). 그런데 이
    레인의 가장 큰 결함이 바로 거기 있었다: 자산스왑 대사가 **채권 다리만**
    세고 있었고, 행 항등식은 그래도 닫혀서 조용했다 (2026-08-14 실측 —
    3Y 자산스왑 대사 합 −2.52억 vs 백테스트 손익 +0.37억, 2.89억이 스왑
    다리). 총액 대조만이 그것을 잡는다.
    """

    SPEC = fd.FundingSpec("base", 10.0)

    #: 진입일을 행렬의 끝에서 세는 칸 수. 대사 창은 `cb.RECON_MAX_DAYS` (250)
    #: **행**이지 달력 날짜가 아니므로, 진입일도 같은 자로 잰다. 날짜를 박아 두면
    #: 하루가 갈 때마다 창이 한 행씩 길어지다 어느 날 `truncated` 가 True 로
    #: 뒤집히고, 그러면 이 시험이 재려던 것(행 합 = 백테스트 총액)을 못 잰다 —
    #: 2026-09-01 에 넷 다 그렇게 깨져 있었다(박혀 있던 값 2025-08-13).
    #: 50행은 여유다.
    ENTRY_ROWS_BACK = 200

    @pytest.fixture(scope="class")
    def live(self):
        from app.dataset import load_dataset_merged

        return cm.load(), load_dataset_merged()

    @pytest.mark.parametrize(
        "kind,tenor", [("CB", "3Y"), ("CB", "10Y"), ("ASW", "3Y"), ("ASW", "10Y")]
    )
    def test_the_daily_rows_sum_to_the_backtest_total(self, live, kind, tenor):
        m, ds = live
        entry = m.dates[-self.ENTRY_ROWS_BACK]
        pos = cb.BondPosition(kind, "KTB", tenor, 1, N, entry)
        bt = cb.run_backtest(m, ds, [pos], self.SPEC)["positions"][0]
        rc = cb.book_recon(m, ds, [pos], self.SPEC)
        rows = [r for r in rc["rows"] if r["actual"] is not None]
        # 잘리면 행이 백테스트보다 짧아 합을 견줄 수 없다 — 주제가 아니라 전제다.
        assert rc["truncated"] is False
        total = sum(r["actual"] for r in rows)
        # 행마다 원 단위로 반올림하므로 행 수만큼의 오차는 정상이다
        assert abs(total - round(bt["pnl"])) <= len(rows)
        for r in rows:
            parts = r["valuation"] + r["carry"] + r["rolldown"] + r["funding"]
            assert abs(r["actual"] - parts) <= 2, r["t"]

    def test_the_cash_bond_estimate_explains_the_move(self, live):
        """현금채권은 한 축짜리 표다 — KRD × Δ민평 이 평가를 거의 다 설명해야
        한다. 실측 잔차/평가 중앙값 0.04% (2026-08-14)."""
        import statistics as st

        m, ds = live
        rc = cb.book_recon(
            m, ds,
            [cb.BondPosition("CB", "KTB", "3Y", 1, N, dt.date(2025, 8, 13))],
            self.SPEC,
        )
        rows = [r for r in rc["rows"] if r["actual"] is not None][1:]
        ratio = st.median([abs(r["residual"]) for r in rows]) / st.median(
            [abs(r["valuation"]) for r in rows]
        )
        assert ratio < 0.05, ratio

    def test_the_asset_swap_estimate_leaves_the_irs_move_behind(self, live):
        """자산스왑은 **일부러** 덜 맞는다 — 모듈 주석의 분해 참조:
        잔차 = (D_스왑 − D_채권) × ΔIRS 이고, 추정 열은 "IRS 가 안 움직였다면"
        을 센다. 실측 잔차/평가 중앙값 43.7%.

        이 핀은 두 방향을 다 막는다. 0 에 가까워지면 누가 KRD 에 스왑 다리를
        더해 스프레드 민감도이기를 그만둔 것이고, 1 을 넘으면 추정이 설명하는
        것보다 어긋나게 하는 쪽이 커진 것이다."""
        import statistics as st

        m, ds = live
        rc = cb.book_recon(
            m, ds,
            [cb.BondPosition("ASW", "KTB", "3Y", 1, N, dt.date(2025, 8, 13))],
            self.SPEC,
        )
        rows = [r for r in rc["rows"] if r["actual"] is not None][1:]
        ratio = st.median([abs(r["residual"]) for r in rows]) / st.median(
            [abs(r["valuation"]) for r in rows]
        )
        assert 0.1 < ratio < 1.0, ratio

    def test_the_asset_swap_recon_is_not_just_the_bond(self, live):
        """스왑 다리를 빼먹으면 자산스왑 대사가 현금채권 대사와 **같아진다**.
        그게 이 결함의 지문이었다."""
        m, ds = live
        entry = dt.date(2025, 8, 13)
        cash = cb.book_recon(
            m, ds, [cb.BondPosition("CB", "KTB", "3Y", 1, N, entry)], self.SPEC
        )
        asw = cb.book_recon(
            m, ds, [cb.BondPosition("ASW", "KTB", "3Y", 1, N, entry)], self.SPEC
        )
        a = sum(r["actual"] for r in cash["rows"] if r["actual"] is not None)
        b = sum(r["actual"] for r in asw["rows"] if r["actual"] is not None)
        assert a != b, "자산스왑 대사가 채권 다리만 세고 있다"


class TestLegParts:
    """다리별 성분 [OWNER 2026-09-23 — "스왑과 채권의 평가, 롤다운, 캐리, 조달도
    같이 보여줄래?"].

    합계 칸만 보면 「캐리 +2억 8,185만원」이 채권 쿠폰인지 스왑 고정인지 알 수
    없다. 실측(ASW:KTB:3Y · 2025-09-22~): 합계 **평가 +1,865만원**이 실은
    국고 −3억 8,773만 + IRS +4억 638만이다 — 두 다리가 거의 상쇄된 결과가 한
    숫자에 접혀 있었다.

    하루씩은 이미 갈라 보였다(`book_recon(with_legs=True)` — [OWNER 2026-09-04
    「국고매수와 IRS Pay 를 별개로 뜨게 해줘」]). **누적만 안 갈라져 있었다.**
    """

    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as c:
            yield c

    #: 열을 닫는 산술은 화면이 하는 것과 같다 — 없는 성분(`None`)은 0 으로 세지
    #: 않고, 있는 값만 더한다.
    KEYS = ("valuation", "rolldown", "carry", "startup")

    def _rows(self, client, positions: str) -> list[dict]:
        r = client.get("/api/backtest", params={"positions": positions})
        assert r.status_code == 200, r.text
        return r.json()["positions"]

    @pytest.mark.parametrize("positions", [
        "3Y,1,1e10,2025-09-22",                 # 순수 스왑
        "3Y-10Y,1,1e10,2025-09-22",             # 커브 — 상품 다리는 둘, 자산은 하나
        "CB:KTB:3Y,1,1e10,2025-09-22",          # 현금채권
        "FUT:3Y,1,1e10,2025-09-22",             # 선물 아웃라이트
        "ASW:KTB:3Y,1,1e10,2025-09-22",         # 자산스왑
        "FSW:3Y,1,1e10,2025-09-22",             # 퓨처스왑
    ])
    def test_every_row_carries_leg_parts(self, client, positions):
        """**줄마다 반드시 온다** — 다리가 하나인 줄도 한 칸짜리로.

        일부만 실으면 혼합 북에서 화면이 다리 이름으로 묶을 때 열이 **조용히**
        안 닫힌다(빠진 줄의 몫이 어느 다리에도 안 들어간다).
        """
        for p in self._rows(client, positions):
            assert p.get("legParts"), f"{p.get('label') or p['id']} 에 legParts 가 없어요"

    @pytest.mark.parametrize("positions", [
        "ASW:KTB:3Y,1,1e10,2025-09-22",
        "ASW:BD:3Y,1,1e10,2025-09-22",
        "FSW:3Y,1,1e10,2025-09-22",
        # 혼합 북 — 자산스왑 · 순수 스왑 · 퓨처스왑이 한 북에.
        "ASW:KTB:3Y,1,1e10,2025-09-22;3Y,-1,1e10,2025-09-22;FSW:3Y,1,1e10,2025-09-22",
    ])
    def test_the_legs_add_back_to_the_row(self, client, positions):
        """성분마다 **다리의 합 = 줄의 합계 칸**, 그리고 다리 손익의 합 = 줄 손익.

        이것이 깨지면 화면의 세로가 헤드라인과 안 맞는다 — 읽는 사람이 더해서
        위 줄이 안 나오면 그 화면은 틀린 것이다(이 리포의 가산성 규칙).
        """
        for p in self._rows(client, positions):
            legs = p["legParts"]
            for k in self.KEYS:
                got = sum(l[k] for l in legs if l[k] is not None)
                want = p.get(k) or 0.0
                assert abs(got - want) <= 1, (
                    f"{p.get('label') or p['id']} 의 {k}: 다리합 {got} ≠ 합계 {want}")
            assert abs(sum(l["pnl"] for l in legs) - p["pnl"]) <= 2

    def test_absent_parts_are_blank_not_zero(self, client):
        """선물 다리엔 캐리·롤다운·개시가 **없다** — 0 이 아니라 `None` 이다.

        0 을 적으면 「그 기간 캐리가 0원이었다」는 다른 말이 된다. 합성채는 만기가
        고정이라 늙지 않고, 그래서 그 성분이 **존재하지 않는다**(`futures.py`).
        조달도 마찬가지다: 스왑·선물에는 조달할 원금이 없다.
        """
        p = self._rows(client, "FSW:3Y,1,1e10,2025-09-22")[0]
        fut = next(l for l in p["legParts"] if l["name"] == "선물")
        irs = next(l for l in p["legParts"] if l["name"] == "IRS")
        assert fut["rolldown"] is None and fut["carry"] is None
        assert fut["startup"] is None and fut["funding"] is None
        assert fut["valuation"] == fut["pnl"], "선물 다리는 손익이 전부 평가다"
        # 캐리·롤다운은 **통째로 스왑 다리 것**이다 — 합계 칸이 곧 IRS 다리다.
        assert irs["carry"] == p["carry"] and irs["rolldown"] == p["rolldown"]
        assert irs["funding"] is None, "IRS 에는 조달할 원금이 없다"

    def test_funding_belongs_to_the_bond_leg_alone(self, client):
        """자산스왑의 조달은 **채권 다리만** 진다 — 스왑 쪽은 공란."""
        p = self._rows(client, "ASW:KTB:3Y,1,1e10,2025-09-22")[0]
        bond, irs = p["legParts"]
        assert bond["funding"] == p["funding"] and bond["funding"] < 0
        assert irs["funding"] is None

    def test_the_bond_leg_is_named_for_its_type(self, client):
        """★이름은 **종목군**이다 — 그리고 어휘는 이미 있던 것을 쓴다.

        일별 대사가 「국고」로 박혀 있었는데 자산스왑은 여덟 종목군 전부에 설 수
        있어(`bond_types_for` 가 ASW 를 다 내놓는다) **은행채 자산스왑도 「국고」**
        라고 적히고 있었다 [2026-09-23].

        ⚠ 고칠 때 `creditmatrix.BOND_TYPES`(국고채·은행채 AAA …)를 쓰면 **KTB 의
        이름까지 바뀐다** — 없던 어휘를 하나 더 만드는 셈이고, 첫 판이 그래서
        `test_mixedbook` 과 `test_mr_legrecon` 을 깨뜨렸다. 이 표가 쓰는 사전은
        `universe.CURVE_LABEL` 이고 KTB 는 그대로 「국고」다.
        """
        ktb = self._rows(client, "ASW:KTB:3Y,1,1e10,2025-09-22")[0]
        bd = self._rows(client, "ASW:BD:3Y,1,1e10,2025-09-22")[0]
        assert [l["name"] for l in ktb["legParts"]] == ["국고", "IRS"]
        assert [l["name"] for l in bd["legParts"]] == ["은행", "IRS"]

    def test_the_daily_recon_uses_the_same_leg_name(self, client):
        """하루와 누적이 **같은 낱말**로 다리를 부른다.

        일별 대사는 백테스트 응답에 `recon` 으로 얹혀 온다(별도 라우트가 아니다
        — KRD 범프가 비싸서 엔진 함수만 둘로 나눠져 있다). 행과 **열 머리**
        (`legTenors`)를 같이 잰다: 머리가 「국고」인데 행이 「은행채 AAA」면
        읽는 사람이 한 표를 두 표로 읽는다.
        """
        r = client.get("/api/backtest",
                       params={"positions": "ASW:BD:3Y,1,1e10,2026-05-13"})
        assert r.status_code == 200, r.text
        bond = r.json()["recon"]["bond"]
        named = [d for d in bond["rows"] if d.get("legs")]
        assert named, "다리 블록이 서야 이 검정이 성립한다"
        assert [l["name"] for l in named[0]["legs"]] == ["은행", "IRS"]
        assert [l["name"] for l in bond["legTenors"]] == ["은행", "IRS"]

    def test_the_netted_view_really_was_hiding_the_legs(self, client):
        """★이 기능이 있어야 하는 이유를 **수로** 박는다.

        합계 평가는 두 다리 각각보다 **한 자릿수 작다** — 합계만 보면 「금리가
        거의 안 움직였다」로 읽히는데, 실제로는 두 다리가 각자 4억쯤 움직이고
        서로 상쇄한 것이다. 이 항등식이 깨지면 이 화면의 존재 이유가 사라지므로,
        수가 바뀌면 여기서 한 번 멈춰서 다시 보게 한다.
        """
        p = self._rows(client, "ASW:KTB:3Y,1,1e10,2025-09-22")[0]
        bond, irs = p["legParts"]
        assert abs(bond["valuation"]) > 10 * abs(p["valuation"])
        assert abs(irs["valuation"]) > 10 * abs(p["valuation"])
        # 부호가 반대라 상쇄된다 — 그게 「접혀 있었다」의 뜻이다.
        assert bond["valuation"] * irs["valuation"] < 0
