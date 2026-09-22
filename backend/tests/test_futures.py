# -*- coding: utf-8 -*-
"""국채선물·퓨처스왑 합류 [OWNER, 2026-08-25 — "선물이랑 선물스왑도 백테스트와
시뮬레이션에 추가하기"].

이 파일이 지는 명제:
    ① 폐형 산술: P(5%) = 100 핀·역산 왕복·pvbp 부호 (futures_pricing).
    ② 백테스트 FUT: 손익 = 방향 × 액면/100 × Δ종가, 롱+숏 = 0.
    ③ 백테스트 FSW: 다리 = 같은 만기 IRS·진입일 DV01 중립 [OWNER 선택],
       +1 = 선물 매도 + IRS 리시브 — 내재만 오르면 이익.
    ④ 선물 대사표: actual = Δ종가 손익, est = 전일 KRD × Δ내재, 잔차 =
       컨벡시티. 캐리·롤다운 열은 None(존재하지 않는 성분 — 공란 정책).
    ⑤ 시뮬 엔진: 선물 분기 = KRX 폐형 재값매김(고정 지평·감쇠 없음),
       캐리·조달 0. E2E 로 futMtm·항등식·자기 대사표가 선다.

데이터는 전부 페이크 주입(futures.set_data / 자체 Dataset) — conftest 의
futures_data_off 가 매 테스트 앞뒤로 되돌린다. SQL 없이 결정적이다.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app import backtest as bt_engine
from app import futures as ft
from app import instruments
from app.backtest import BacktestError
from app.dataset import Dataset
from app.main import app
from app import mixedbook
from irs_pricer.services.simulation import daily_valuation as dv
from irs_pricer.services.simulation.futures_pricing import (
    FUT_YEARS,
    implied_yield,
    synth_price,
    synth_pvbp,
)

# ── 페이크 시장 ─────────────────────────────────────────────────────────────

NODES = ["1D", "3M", "6M", "9M", "1Y", "1.5Y", "2Y", "3Y", "5Y", "10Y"]
FLAT = 3.00   # 평평한 IRS 커브 — 스왑 다리의 세타가 ~0 이 되게


def _weekdays(start: dt.date, n: int) -> list[dt.date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


DATES = _weekdays(dt.date(2026, 9, 1), 12)


def _dataset(rates: dict[str, list[float]] | None = None) -> Dataset:
    series = rates or {n: [FLAT] * len(DATES) for n in NODES}
    return Dataset(dates=DATES, series=series, tenor_order=list(NODES), source="test")


def _futdata(path_3y: list[float], path_10y: list[float] | None = None) -> ft.FuturesData:
    """페이크 시장. 조정가 = 계약가 = 벤더 금리의 폐형가격 — **오프셋 0 인 세계**.

    실장에서 그 셋은 갈린다(조정가는 과거로 갈수록 계약가와 벌어진다). 여기서
    같게 두는 이유는 **다른 것을 재려는 것이 아니기 때문**이다: 엔진의 산술과
    역할 배선을 재는 픽스처이고, 갈라짐 자체는 `TestVendorLevels` 가 따로 잰다.
    """
    p10 = path_10y or [120.0] * len(DATES)
    assert len(path_3y) == len(DATES) and len(p10) == len(DATES)

    def mk(path: list[float], years: int) -> ft.FuturesSeries:
        imp = [implied_yield(p, years) for p in path]
        return ft.FuturesSeries(
            dates=list(DATES), price_adj=list(path),
            implied=list(imp), price_ctr=list(path),
        )

    return ft.FuturesData(
        series={"3Y": mk(path_3y, 3), "10Y": mk(p10, 10)},
        watermark=("test", len(DATES)),
    )


# ── ① 폐형 산술 ─────────────────────────────────────────────────────────────

class TestPricing:
    def test_par_pin(self):
        """표면 5% 표준물은 5% 에서 정확히 100 — KRX 정의의 자명한 핀."""
        assert synth_price(5.0, 3) == pytest.approx(100.0, abs=1e-9)
        assert synth_price(5.0, 10) == pytest.approx(100.0, abs=1e-9)

    def test_roundtrip(self):
        for years in (3, 10):
            for y in (1.5, 3.71, 5.0, 8.2):
                assert implied_yield(synth_price(y, years), years) == pytest.approx(y, abs=1e-6)

    def test_pvbp_sign_and_scale(self):
        """롱이 양수·10Y 가 3Y 보다 크다(듀레이션)."""
        p3, p10 = synth_pvbp(3.5, 3), synth_pvbp(3.5, 10)
        assert 0 < p3 < p10
        # 3Y 합성채 mod dur ≈ 2.8 → pvbp ≈ 0.028 (액면 100 기준)
        assert p3 == pytest.approx(0.028, rel=0.2)

    def test_mr_alias_is_this_function(self):
        """mr.py 의 _implied_yield 는 이 모듈의 그 함수다 — 두 진실 금지."""
        from app.mr import _implied_yield

        assert _implied_yield is implied_yield


# ── ② FUT 백테스트 ─────────────────────────────────────────────────────────

class TestFutBacktest:
    def test_pnl_is_price_change(self):
        path = [104.0, 104.2, 104.5, 104.1, 103.8, 103.9, 104.0, 104.3, 104.6, 104.4, 104.2, 104.0]
        fut = _futdata(path)
        ds = _dataset()
        pos = ft.as_position("FUT:3Y", 1, 1e10, DATES[0], None)
        rec, own, _prev = ft.run_one(fut, ds, pos, DATES)
        for i, d in enumerate(DATES):
            assert own[d] == pytest.approx(1e10 / 100.0 * (path[i] - path[0]))
        assert rec["pnl"] == pytest.approx(1e10 / 100.0 * (path[-1] - path[0]))
        # 선물 손익은 전부 평가다 — 캐리·롤다운·개시는 None (공란 정책).
        assert rec["valuation"] == rec["pnl"]
        assert rec["carry"] is None and rec["rolldown"] is None and rec["startup"] is None

    def test_long_plus_short_is_zero(self):
        path = [104.0, 104.5, 103.7, 104.2, 104.9, 104.1, 103.5, 104.0, 104.8, 104.3, 104.6, 104.2]
        fut = _futdata(path)
        ds = _dataset()
        long = ft.as_position("FUT:3Y", 1, 5e9, DATES[0], None)
        short = ft.as_position("FUT:3Y", -1, 5e9, DATES[0], None)
        _r1, own_l, _p1 = ft.run_one(fut, ds, long, DATES)
        _r2, own_s, _p2 = ft.run_one(fut, ds, short, DATES)
        for d in DATES:
            assert own_l[d] + own_s[d] == pytest.approx(0.0, abs=1e-6)

    def test_mixed_swap_plus_futures_book(self):
        """스왑+선물 혼합 북 — 일반화 병합(_mixed_any) 경로.

        평평한 IRS(세타 ~0) + 선물 가격만 이동 → 북 총액 ≈ 선물 다리 손익.
        줄마다 자기 kind 가 붙고, 총액이 두 엔진 합으로 닫힌다."""
        path = [104.0] * 3 + [104.5] * 9        # +0.5pt
        ft.set_data(_futdata(path))
        ds = _dataset()
        out = mixedbook.run_backtest(
            None, ds,
            [
                mixedbook.MixedPosition("3Y", 1, 1e10, DATES[0], None),
                mixedbook.MixedPosition("FUT:3Y", 1, 1e10, DATES[0], None),
            ],
            _spec(), fut=ft.load(),
        )
        kinds = [p["kind"] for p in out["positions"]]
        assert kinds == ["swap", "futures"]
        fut_pnl = 1e10 / 100.0 * (path[-1] - path[0])
        swap_pnl = out["positions"][0]["pnl"]
        assert out["pnl"] == pytest.approx(swap_pnl + fut_pnl, abs=2.0)
        assert out["calendar"]["basis"] == "IRS ∩ 선물"
        # 점마다 d 가 서고(첫 점 제외), 마지막 점이 총액이다.
        assert out["points"][0]["d"] is None
        assert all(p["d"] is not None for p in out["points"][1:])
        assert out["points"][-1]["pnl"] == out["pnl"]

    def test_mixedbook_routes_futures_only_book(self):
        path = [104.0] * 6 + [105.0] * 6
        ft.set_data(_futdata(path))
        ds = _dataset()
        out = mixedbook.run_backtest(
            None, ds,
            [mixedbook.MixedPosition("FUT:10Y", 1, 1e10, DATES[0], None)],
            _spec(), fut=ft.load(),
        )
        assert out["positions"][0]["kind"] == "futures"
        assert out["positions"][0]["label"] == "KTB10 선물"
        # 10Y 페이크는 상수 120 — 손익 0. 3Y 경로는 이 북과 무관하다.
        assert out["pnl"] == 0.0


def _spec():
    from app import funding as fd

    return fd.FundingSpec(basis="call", spread_bp=0.0)


# ── ②-b 계열 (진입 레벨·종목 추이 차트가 읽는 것) ───────────────────────────

class TestSeriesPayload:
    """`/api/futures/series/{id}` [OWNER, 2026-08-25].

    이 표면이 없던 동안 백테스트 창은 선물 히스토리를 `/api/series/{id}` 로
    찾다가 **404** 를 받았고, 그래서 진입 레벨이 «—» 로 서고 「종목 추이」
    차트가 통째로 안 그려져 커서 리드아웃까지 죽었다. 여기서 잠그는 것은
    그 회귀다: 선물은 가격 + 내재금리 둘 다, 퓨처스왑은 스프레드 bp.
    """

    def test_fut_level_is_the_vendor_yield_price_rides_along(self):
        path = [104.0, 104.2, 104.5, 104.1, 103.8, 103.9,
                104.0, 104.3, 104.6, 104.4, 104.2, 104.0]
        body = ft.series_payload(_futdata(path), _dataset(), "FUT:3Y")
        # **수준은 금리다** — 조정가는 수준이 없다(back-adjusted).
        assert body["unit"] == "%"
        assert body["label"] == "KTB3 선물"
        assert body["levelNote"] == "롤 시점 불연속 포함"
        assert len(body["points"]) == len(DATES)
        for p, close in zip(body["points"], path):
            assert p["v"] == pytest.approx(round(implied_yield(close, 3), 4))
            assert p["price"] == pytest.approx(close)
        # %-계열이라 전일 대비는 bp 다(derive.series_history 의 규약).
        d1 = (implied_yield(path[1], 3) - implied_yield(path[0], 3)) * 100.0
        assert body["points"][1]["d"] == pytest.approx(d1, abs=0.01)

    def test_fsw_is_spread_in_bp(self):
        path = [104.0] * len(DATES)
        body = ft.series_payload(_futdata(path), _dataset(), "FSW:3Y")
        assert body["unit"] == "bp"
        assert body["label"] == "퓨처스왑 3Y"
        # 평평한 IRS(3.00) 대비 — **IRS − 벤더 내재**, bp
        # [부호 규약 OWNER 2026-09-22 — "스왑 - 채권현물 또는 국채선물"].
        want = round((FLAT - implied_yield(104.0, 3)) * 100.0, 4)
        assert body["points"][-1]["v"] == pytest.approx(want, abs=1e-3)
        assert "price" not in body["points"][-1]

    def test_price_is_withheld_when_it_disagrees_with_the_vendor_yield(self):
        """계약가와 벤더 금리가 안 맞는 날은 **가격을 안 싣는다**.

        실장의 KTB3 이 그렇다(2021 이전 최대 5 가격점 어긋남). 나란히 적으면
        한 줄이 서로 다른 두 수를 말하므로, 못 싣는 날은 정직하게 빈다.
        """
        path = [104.0] * len(DATES)
        fut = _futdata(path)
        fs = fut.series["3Y"]
        broken = ft.FuturesSeries(
            dates=fs.dates, price_adj=fs.price_adj, implied=fs.implied,
            price_ctr=[None] * len(fs.dates),      # 로더가 문턱에서 거른 모습
        )
        data = ft.FuturesData(series={**fut.series, "3Y": broken}, watermark=fut.watermark)
        body = ft.series_payload(data, _dataset(), "FUT:3Y")
        assert all(p["price"] is None for p in body["points"])
        # 금리는 그대로 선다 — 가격이 없다고 수준까지 잃지 않는다.
        assert body["points"][-1]["v"] == pytest.approx(round(implied_yield(104.0, 3), 4))

    def test_missing_vendor_yield_fails_loudly(self):
        path = [104.0] * len(DATES)
        fut = _futdata(path)
        fs = fut.series["3Y"]
        blank = ft.FuturesSeries(dates=fs.dates, price_adj=fs.price_adj,
                                 implied=[None] * len(fs.dates), price_ctr=fs.price_ctr)
        with pytest.raises(ft.FuturesError):
            ft.implied_at_index(blank, 0, "3Y")

    def test_fsw_drops_days_without_an_irs_mark(self):
        """inner join 규율 — 보간도 이월도 없다(MR 보드와 같은 규칙)."""
        rates = {n: [FLAT] * len(DATES) for n in NODES}
        short = Dataset(dates=DATES[:5], series={n: v[:5] for n, v in rates.items()},
                        tenor_order=list(NODES), source="test")
        body = ft.series_payload(_futdata([104.0] * len(DATES)), short, "FSW:3Y")
        assert len(body["points"]) == 5

    def test_unknown_id_is_a_futures_error(self):
        with pytest.raises(ft.FuturesError):
            ft.series_payload(_futdata([104.0] * len(DATES)), _dataset(), "FUT:7Y")

    def test_main_and_mr_report_the_same_implied_yield(self):
        """Main 목록과 MR 보드가 **같은 날 같은 수**를 말한다.

        이 레인이 고친 결함이 바로 그 둘의 불일치였다 — Main(`universe.py`)은
        벤더 컬럼을 읽고 MR 보드(`mr._fut_bundle`)는 조정가를 역산해서, 한
        이름(「KTB3 내재금리」)에 최대 182bp 벌어진 두 수가 있었다. 이제 둘 다
        같은 로더의 `implied` 를 지난다.
        """
        from app import mr

        path3 = [104.0 + i * 0.05 for i in range(len(DATES))]
        path10 = [120.0 - i * 0.07 for i in range(len(DATES))]
        ft.set_data(_futdata(path3, path10))
        bundle = mr._fut_bundle()
        fut = ft.load()
        for sid, tenor in (("FUT-KTB3", "3Y"), ("FUT-KTB10", "10Y")):
            fs = fut.series[tenor]
            pts = {p["t"]: p["v"] for p in bundle[sid]["points"]}
            for d, y in zip(fs.dates, fs.implied):
                # 보드가 내는 수 == 로더가 든 벤더 값(반올림만 다르다).
                assert pts[d.isoformat()] == pytest.approx(y, abs=5e-5)

    def test_no_source_inverts_the_adjusted_price(self):
        """**가드**: 조정가를 역산해 금리를 만드는 코드가 다시 생기면 실패한다.

        이 레인의 결함이 정확히 그것이었다 — `implied_yield(CLOSE)`. 조정가는
        분기 롤마다 상수 오프셋이 얹힌 연속 계열이라 차분에만 뜻이 있고, 그
        위에서 낸 금리는 벤더 값 대비 최대 182bp 틀렸다. 사람이 규칙을 기억하는
        대신 파일이 기억하게 둔다.

        재는 방법: `price_adj` 를 첨자한 표현이 `implied_yield(`/`synth_pvbp(`
        의 인자로 들어가는 줄을 소스에서 찾는다. 주석은 세지 않는다.
        """
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[1]
        bad: list[str] = []
        for rel in ("app/futures.py", "app/mr.py", "app/instruments.py",
                    "app/mixedbook.py", "app/universe.py",
                    "irs_pricer/services/simulation/daily_valuation.py",
                    "irs_pricer/services/simulation/aggregates.py"):
            f = root / rel
            if not f.exists():
                continue
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                code = line.split("#", 1)[0]
                if re.search(r"(implied_yield|synth_pvbp)\s*\([^)]*price_adj", code):
                    bad.append(f"{rel}:{n}: {line.strip()}")
                # 옛 이름으로 되돌아가는 것도 막는다 — `.close[` 는 이제 없다.
                if re.search(r"\bfs\.close\b|\.series\[[^\]]+\]\.close\b", code):
                    bad.append(f"{rel}:{n}: (옛 이름 .close) {line.strip()}")
        assert bad == [], (
            "조정가에서 금리를 유도하는 코드가 있어요 — 수준은 벤더 "
            "`선물내재수익률` 을 읽습니다(app/futures.py::FuturesSeries 머리 주석).\n"
            + "\n".join(bad)
        )

    def test_main_never_opens_the_adjusted_table(self):
        """**가드 · Phase 4 인수 조건**: Main 목록이 내는 선물 파생 수는 전부
        `implied`(벤더)이거나 `price_adj` 의 차분이어야 한다.

        Main 쪽에서 그것을 지키는 가장 강한 방법은 조정가 표를 **아예 열지 않는
        것**이다 — 열지 않으면 역산할 대상이 없다. `app/universe.py` 는 벤더
        표(`infomax.daily_ktb_price`/`daily_lktb_price`)와 `mkt_irs_close` 만
        읽는다. 퓨처스왑 행도 그 벤더 내재금리에서 난다.
        """
        import pathlib

        src = (pathlib.Path(__file__).resolve().parents[1] / "app" / "universe.py"
               ).read_text(encoding="utf-8")
        # 주석은 안 센다. 줄은 붙이지 말고 그대로 둔다 — 이어 붙이면 줄
        # 경계를 넘어선 우연한 일치가 생긴다.
        code = [line.split("#", 1)[0] for line in src.splitlines()]
        assert not any("mkt_futures_investor_close" in c for c in code), (
            "Main 이 조정가 표를 열었어요 — 수준은 벤더 컬럼을 읽습니다."
        )
        # 그리고 퓨처스왑은 그 벤더 내재금리와 IRS 의 교집합이다(이월·보간 없음).
        assert any("선물내재수익률" in c for c in code)
        # ★차례가 규약을 진다 — `IRS − 내재` 라 IRS 가 첫 인자다(2026-09-22).
        assert any("_align(idates, irs[lbl], fdates, imp)" in c for c in code)

    def test_route_serves_it(self):
        """`with TestClient(app)` 를 쓰지 않는다 — 이 파일의 아래쪽 관례와 같다.

        컨텍스트 매니저는 **lifespan 을 띄우고**, 이 앱의 기동은 SQL 을 읽고
        `backend/output/` 의 굽기 산출물을 다시 쓴다. 그러면 같은 세션의
        `test_rebake` 넷이 어제 것을 보고 실패한다 — 파일 단독으로는 통과하고
        전체 실행에서만 빨개지는 오염이었다(실측 2026-08-25). 라우트만 재는 데
        기동은 필요 없다.
        """
        ft.set_data(_futdata([104.0] * len(DATES)))
        c = TestClient(app)
        r = c.get("/api/futures/series/FUT:3Y")
        assert r.status_code == 200
        assert r.json()["unit"] == "%"          # 수준은 금리다
        assert c.get("/api/futures/series/FUT:7Y").status_code == 422


# ── ③ FSW ──────────────────────────────────────────────────────────────────

class TestFsw:
    def test_leg_is_dv01_neutral_same_tenor(self):
        fut = _futdata([104.0] * len(DATES))
        ds = _dataset()
        pos = ft.as_position("FSW:3Y", 1, 1e10, DATES[0], None)
        swap_pos, y0, fut_dv01 = ft.fsw_swap_leg(fut, ds, pos)
        assert swap_pos.series_id == "3Y"          # 같은 만기 [OWNER]
        # ★2026-09-22 규약 뒤집기: 스프레드가 `IRS − 선물` 이라 +1 = **IRS 페이**
        # 이고, 스왑 엔진의 +1 이 곧 페이다. 종전에는 −1(리시브)이었다.
        assert swap_pos.direction == 1             # +1 = IRS 페이
        assert fut_dv01 == pytest.approx(1e10 / 100.0 * synth_pvbp(y0, 3))
        # DV01 중립: 스왑 원/bp(= 명목 × 연금계수 × 1e-4 — 백테스트 창의
        # 표시식이 이 규약의 핀) == 선물 원/bp. 처음 이 테스트가 1e-4 없는
        # 잘못된 규약을 같이 믿어 10⁴배 결함을 통과시켰다(실측 2026-08-25:
        # 100억 FSW 의 IRS 다리가 100만원) — 크기 상식 단언을 같이 박는다.
        from app.backtest import _build_legs

        j = ds.dates.index(swap_pos.entry)
        unit = _build_legs(ds, "3Y", 1.0, j)[0].dv01
        assert swap_pos.notional * unit * 1e-4 == pytest.approx(fut_dv01, rel=1e-9)
        # 같은 만기·비슷한 듀레이션이면 두 다리 명목은 같은 자릿수여야 한다.
        assert 0.5 * 1e10 < swap_pos.notional < 2.0 * 1e10

    def test_implied_up_alone_loses_for_a_long_spread(self):
        """IRS 평평 고정·선물 가격만 하락(내재 상승) → FSW +1 **손실** ≈ DV01×Δbp.

        ★2026-09-22 에 **뜻이 뒤집혔다** [OWNER — "스왑 - 채권현물 또는 국채선물"].
        스프레드가 `IRS − 내재` 라 내재만 오르면 스프레드가 **줄고**, 그 확대에
        건 +1 은 잃는다. 크기는 그대로다 — 뒤집힌 것은 부호뿐이고, 그래서 이
        시험은 「부호가 뒤집혔나」와 「크기가 그대로인가」를 같이 잰다.
        """
        p0 = 104.0
        y0 = implied_yield(p0, 3)
        y1 = y0 + 0.10                              # +10bp
        p1 = synth_price(y1, 3)
        path = [p0] * 2 + [p1] * (len(DATES) - 2)
        fut = _futdata(path)
        ds = _dataset()
        pos = ft.as_position("FSW:3Y", 1, 1e10, DATES[0], None)
        _rec, own, _prev = ft.run_one(fut, ds, pos, DATES)
        fut_dv01 = 1e10 / 100.0 * synth_pvbp(y0, 3)
        expected = -fut_dv01 * 10.0                 # 10bp, 스프레드는 줄었다
        # 스왑 다리는 커브가 안 움직여 세타뿐 — 평평 커브 페이 par 라 작다.
        assert own[DATES[-1]] == pytest.approx(expected, rel=0.05)
        assert own[DATES[-1]] < 0

    def test_recon_puts_both_legs_in_the_futures_table(self):
        """FSW 의 IRS 다리는 **선물 표 안에 다리로** 선다 [OWNER 2026-09-04].

        2026-08-25 판은 그 다리를 스왑 표로 보냈다(엔진 단위 분리). 한 거래의
        두 다리가 다른 표에 서면 「이 거래가 그날 얼마를 벌었나」를 화면이 한
        줄로 못 말한다 — 자산스왑이 이미 다리 둘을 한 표에 세우고 있었고
        퓨처스왑이 그것을 따라갔다. **스왑 표에서는 빠진다**(중복 금지).
        """
        p0 = 104.0
        path = [p0] * len(DATES)
        ft.set_data(_futdata(path))
        ds = _dataset()
        out = mixedbook.book_recon(
            None, ds,
            [mixedbook.MixedPosition("FSW:3Y", 1, 1e10, DATES[0], None)],
            _spec(), fut=ft.load(),
        )
        assert set(out) == {"swap", "bond", "futures"}
        assert out["bond"] is None
        # 스왑 줄이 하나도 없는 북이라 스왑 표 자체가 안 선다 — IRS 다리는
        # 선물 표 안에 있다(같은 돈이 두 표에 서지 않는다).
        assert out["swap"] is None
        assert out["futures"] is not None
        rows = out["futures"]["rows"]
        assert rows[-1].get("carryover") is True
        # 하루 일곱 줄의 재료: 다리 둘(선물·IRS) + 합계는 행 자신이다.
        assert out["futures"]["legTenors"][0]["name"] == "선물"
        assert out["futures"]["legTenors"][1]["name"] == "IRS"
        for r in rows:
            assert [lg["name"] for lg in r["legs"]] == ["선물", "IRS"]
            # 선물 다리는 캐리·롤다운이 **없는 성분**이다 — 다리 줄에서 공란.
            assert r["legs"][0]["carry"] is None
            assert r["legs"][0]["rolldown"] is None
            # 조달은 어느 다리도 안 진다(현물이 아니다).
            assert r["legs"][1]["funding"] is None
        body = [r for r in rows if not r.get("carryover")]
        for r in body:
            # 합계 = 두 다리의 합. 이 항등이 깨지면 표가 대사표가 아니다.
            assert r["actual"] == r["legs"][0]["actual"] + r["legs"][1]["actual"]
            assert r["valuation"] == (r["legs"][0]["valuation"]
                                      + r["legs"][1]["valuation"])
            assert r["estTotal"] == (r["legs"][0]["estTotal"]
                                     + r["legs"][1]["estTotal"])
            # 캐리·롤다운·개시는 IRS 다리에서만 온다(선물엔 그 성분이 없다).
            assert r["carry"] == r["legs"][1]["carry"]
            assert r["rolldown"] == r["legs"][1]["rolldown"]

    def test_fsw_legs_conserve_the_swap_leg_money_across_the_two_calendars(self):
        """버킷이 **돈을 흘리지 않는다** — 세로합이 스왑 표의 그 다리와 같다.

        IRS 다리는 IRS 달력 위에서 값매겨지고 선물 표는 선물 달력 위에 선다.
        두 달력이 갈리는 날 IRS 쪽은 0 이고, 다음 마킹이 두 밤을 한 번에
        재므로 합은 보존돼야 한다(`futures.book_recon` 의 `with_legs` 머리).
        """
        path = [104.0, 104.0, 103.5, 103.5, 103.8, 103.8,
                103.8, 104.1, 104.1, 104.1, 104.0, 104.0]
        fut = _futdata(path)
        ds = _dataset()
        pos = ft.as_position("FSW:3Y", 1, 1e10, DATES[0], None)
        with_legs = ft.book_recon(fut, ds, [pos], with_legs=True)
        # 같은 다리를 스왑 엔진에게 직접 물었을 때의 표.
        swap_pos, _y0, _dv = ft.fsw_swap_leg(fut, ds, pos)
        alone = bt_engine.book_recon(ds, [swap_pos])

        def _money(rec, pick):
            return sum(pick(r) or 0.0 for r in rec["rows"] if not r.get("carryover"))

        for key in ("actual", "valuation", "carry", "rolldown", "startup"):
            got = _money(with_legs, lambda r, k=key: r["legs"][1][k])
            want = _money(alone, lambda r, k=key: r[k])
            assert got == pytest.approx(want, abs=1.0), key


# ── ④ 선물 대사표 ──────────────────────────────────────────────────────────

class TestFutRecon:
    def test_actual_est_residual(self):
        path = [104.0, 104.0, 103.5, 103.5, 103.8, 103.8, 103.8, 104.1, 104.1, 104.1, 104.0, 104.0]
        fut = _futdata(path)
        ds = _dataset()
        out = ft.book_recon(
            fut, ds, [ft.as_position("FUT:3Y", 1, 1e10, DATES[0], None)]
        )
        assert out["tenors"] == ["3Y"]
        body = [r for r in out["rows"] if not r.get("carryover")]
        # 진입일 행: 그날 종가로 struck — 평가 0, 전일 KRD 0 (아침엔 없었다).
        assert body[0]["actual"] == 0 and body[0]["krd"]["3Y"] == 0
        for i, r in enumerate(body):
            if i == 0:
                continue
            d_price = path[i] - path[i - 1]
            assert r["actual"] == pytest.approx(1e10 / 100.0 * d_price, abs=1.0)
            assert r["residual"] == r["valuation"] - r["estTotal"]
            # 잔차 = 컨벡시티 — 선형 추정 대비 작아야 한다 (50bp 미만 이동).
            if r["estTotal"]:
                assert abs(r["residual"]) < abs(r["estTotal"]) * 0.02 + 2
        assert out["rows"][-1]["carryover"] is True
        assert out["rows"][-1]["krd"]["3Y"] != 0     # 열린 북 — 이월 리스크


# ── ⑤ 시뮬 엔진 ────────────────────────────────────────────────────────────

def _fut_row(direction: int = 1, notional: float = 1e10, tenor: str = "3Y",
             y0: float = 3.5) -> dict:
    years = FUT_YEARS[tenor]
    pvbp = direction * notional / 100.0 * synth_pvbp(y0, years)
    return {
        "id": f"FUT:{tenor}#0", "name": f"KTB{years} 선물", "book": "직접입력",
        "bondType": "futures", "sector": "국채선물",
        "maturityDate": (dt.date(2026, 9, 1) + dt.timedelta(days=int(years * 365))).isoformat(),
        "couponRate": 5.0, "frequency": 2, "notional": notional,
        "entryYield": y0, "entryYieldPurchase": y0, "mtmYield": y0,
        "evaluationAmount": 0.0, "duration": 2.8, "pvbp": pvbp, "tenor": tenor,
        "remainingDays": years * 365.0, "durationWeight": 0.0,
        "krdMap": {tenor: pvbp}, "direction": direction,
        "startDate": "2026-09-01",
    }


class TestSimEngine:
    def test_exact_reval_no_aging(self):
        """폐형 재값매김 — t 와 무관하게 같은 충격이면 같은 MTM(합성채는 늙지
        않는다). 선형 pvbp 와의 차 = 컨벡시티가 실재한다."""
        from irs_pricer.services.simulation.models import FrontendPosition

        p = FrontendPosition(**_fut_row(direction=1, y0=3.5))
        for t in (1, 90, 179):
            got = dv.calculate_daily_mtm([p], "parallel", "step", 250.0, None, 1.0, t)
            exact = 1e10 / 100.0 * (synth_price(3.5 + 2.5, 3) - synth_price(3.5, 3))
            assert got == pytest.approx(exact)
        linear = p.pvbp * -250.0
        assert abs(got - linear) > 1e5     # 컨벡시티는 0 이 아니다 (+250bp)
        assert got > linear                # 롱의 컨벡시티는 이득 쪽

    def test_carry_and_funding_are_absent(self):
        from irs_pricer.services.simulation.models import FrontendPosition

        p = FrontendPosition(**_fut_row())
        carry = dv.calculate_daily_carry([p], "parallel", "step", 100.0, None, 0.03, 1.0, 5)
        cost = dv.calculate_daily_funding_cost([p], 0.03, 5)
        assert carry == 0.0 and cost == 0.0

    def test_matrix_mode_reads_ktb_curve_at_fixed_horizon(self):
        from irs_pricer.services.simulation.models import (
            FrontendPosition,
            FrontendShockCurves,
        )

        p = FrontendPosition(**_fut_row(tenor="10Y", y0=3.8))
        curves = FrontendShockCurves(
            bondCurves={"국채": [{"t": 3.0, "val": 10.0}, {"t": 10.0, "val": 50.0}]},
            swapCurve=[],
        )
        got = dv.calculate_daily_mtm([p], "matrix", "step", 0.0, curves, 1.0, 30)
        exact = 1e10 / 100.0 * (synth_price(3.8 + 0.50, 10) - synth_price(3.8, 10))
        assert got == pytest.approx(exact)


class TestSimE2E:
    def _req(self, rows: list[dict]) -> dict:
        return {
            "positions": rows,
            "shockCurves": {"bondCurves": {}, "swapCurve": []},
            "dailyShockCurves": {"bondCurves": {}, "swapCurve": []},
            "fundingRate": 0.03, "fundingEvents": [],
            "simDays": 30, "shockType": "ramp", "shockMode": "parallel",
            "baseShockBp": 100, "baseDate": "2026-09-01",
            "irsCurves": [],
            "customPath": [{"day": 0, "bp": 0}, {"day": 30, "bp": 100}],
            "includeDistribution": False,
        }

    def test_futures_only_run(self):
        r = TestClient(app).post("/api/simulate", json=self._req([_fut_row()]))
        assert r.status_code == 200, r.text
        body = r.json()
        d = body["totalReturnDecomposition"]
        exact = 1e10 / 100.0 * (synth_price(3.5 + 1.0, 3) - synth_price(3.5, 3))
        assert d["futMtm"] == pytest.approx(exact, rel=1e-6)
        # 항등: 성분 합 == total (선물 외 성분은 전부 0).
        assert d["total"] == pytest.approx(
            d["bondMtm"] + d["bondCarry"] + d["bondRolldown"] + d["fundingCost"]
            + d["futMtm"] + (d["swapMtm"] or 0) + (d["swapCarry"] or 0)
            + (d["swapRolldown"] or 0)
        )
        assert d["bondCarry"] == 0.0 and d["fundingCost"] == 0.0
        assert body["summary"]["finalFut"] == round(exact)
        # 자기 대사표가 선다 — 채권·스왑 표는 없다.
        tbl = body["futuresDailyReconciliation"]
        assert tbl and tbl["groups"][0]["label"] == "국채선물"
        assert body["bondDailyReconciliation"] is None
        assert body["irsDailyReconciliation"] == []
        # 세로 검산: Σ평가 == futMtm (±행 라운딩).
        rows = [x for x in tbl["rows"] if not x.get("carryover")]
        assert sum(x["valuation"] for x in rows) == pytest.approx(d["futMtm"], abs=len(rows))
        # 잔차 = 컨벡시티: Σ잔차 == futMtm − 선형 추정.
        est = sum(x["totalEstPnl"] for x in rows)
        res = sum(x["residual"] for x in rows)
        assert res == pytest.approx(d["futMtm"] - est, abs=len(rows))
        for x in rows:
            assert x["carry"] is None and x["rolldown"] is None and x["funding"] is None
        # KRD 패널: 국채선물 섹터 행이 선다.
        krd = {row["sector"]: row for row in body["pvbpSensitivity"]}
        assert krd["국채선물"]["total"] == pytest.approx(_fut_row()["pvbp"], rel=1e-6)

    def test_expand_fsw_makes_two_rows(self):
        ft.set_data(_futdata([104.0] * len(DATES)))
        ds = _dataset()
        rows = instruments.expand(ds, "FSW:3Y", 1, 1e10, DATES[0])
        assert len(rows) == 2
        fut_leg, swap_leg = rows
        assert fut_leg["bondType"] == "futures" and fut_leg["direction"] == -1
        assert swap_leg["bondType"] == "swap" and swap_leg["direction"] == 1  # 리시브
        y0 = implied_yield(104.0, 3)
        assert fut_leg["mtmYield"] == pytest.approx(y0)
        # DV01 중립 명목 — 원/bp = 명목 × 연금계수 × 1e-4 (위 백테스트 쪽
        # 테스트와 같은 규약·같은 크기 상식 단언).
        from app.backtest import _build_legs

        unit = _build_legs(ds, "3Y", 1.0, 0)[0].dv01
        assert swap_leg["notional"] * unit * 1e-4 == pytest.approx(
            1e10 / 100.0 * synth_pvbp(y0, 3), rel=1e-9
        )
        assert 0.5 * 1e10 < swap_leg["notional"] < 2.0 * 1e10

    def test_expand_fut_row_shape(self):
        ft.set_data(_futdata([104.0] * len(DATES)))
        ds = _dataset()
        rows = instruments.expand(ds, "FUT:10Y", -1, 2e10, DATES[0])
        assert len(rows) == 1
        r = rows[0]
        assert r["bondType"] == "futures" and r["direction"] == -1
        assert r["pvbp"] < 0                      # 숏은 음수 (롱 양수 관행)
        assert r["evaluationAmount"] == 0.0       # 현금 지출 없음
        assert r["krdMap"] == {"10Y": r["pvbp"]}


# ── ⑥ 시뮬 선물 진입가 [OWNER 결정 2, 2026-08-25] ──────────────────────────

class TestSimEntryPrice:
    """선물은 가격으로 거래되므로 사람이 아는 진입 수준은 «104.36 에 샀다» 다.
    그 가격을 서버가 내재금리로 환산한다(§16 — 브라우저는 계산하지 않는다)."""

    def test_default_is_unchanged(self):
        """`entry_price` 를 안 주면 한 자도 안 바뀐다 — 벤더 값을 읽는다."""
        ft.set_data(_futdata([104.0] * len(DATES)))
        ds = _dataset()
        a = instruments.expand(ds, "FUT:3Y", 1, 1e10, DATES[0])
        b = instruments.expand(ds, "FUT:3Y", 1, 1e10, DATES[0], None)
        assert a == b
        assert a[0]["mtmYield"] == pytest.approx(implied_yield(104.0, 3))

    def test_price_sets_the_level_through_the_closed_form(self):
        ft.set_data(_futdata([104.0] * len(DATES)))
        ds = _dataset()
        r = instruments.expand(ds, "FUT:3Y", 1, 1e10, DATES[0], 105.43)[0]
        y = implied_yield(105.43, 3)
        # 세 자리 전부 그 금리다 — 하나만 옮기면 화면이 두 수를 말한다.
        assert r["mtmYield"] == pytest.approx(y)
        assert r["entryYield"] == pytest.approx(y)
        assert r["entryYieldPurchase"] == pytest.approx(y)
        # DV01 도 그 수준의 것이다(pvbp 는 y0 의 함수).
        assert r["pvbp"] == pytest.approx(1e10 / 100.0 * synth_pvbp(y, 3))
        assert r["pvbp"] != pytest.approx(
            1e10 / 100.0 * synth_pvbp(implied_yield(104.0, 3), 3)
        )

    def test_fsw_reweights_its_swap_leg(self):
        """퓨처스왑에 오면 **선물 다리의** 진입가다 — DV01 이 바뀌므로 중립
        가중된 스왑 명목도 따라 움직인다."""
        ft.set_data(_futdata([104.0] * len(DATES)))
        ds = _dataset()
        base = instruments.expand(ds, "FSW:3Y", 1, 1e10, DATES[0])
        edit = instruments.expand(ds, "FSW:3Y", 1, 1e10, DATES[0], 101.00)
        y = implied_yield(101.00, 3)
        assert edit[0]["mtmYield"] == pytest.approx(y)
        assert edit[1]["notional"] != pytest.approx(base[1]["notional"])
        from app.backtest import _build_legs

        unit = _build_legs(ds, "3Y", 1.0, 0)[0].dv01
        assert edit[1]["notional"] * unit * 1e-4 == pytest.approx(
            1e10 / 100.0 * synth_pvbp(y, 3), rel=1e-9
        )

    def test_a_price_the_closed_form_cannot_read_says_so(self):
        ft.set_data(_futdata([104.0] * len(DATES)))
        ds = _dataset()
        with pytest.raises(BacktestError):
            instruments.expand(ds, "FUT:3Y", 1, 1e10, DATES[0], 0.0)

    def test_only_futures_have_an_entry_price(self):
        """스왑에 진입가를 주면 조용히 버리지 않고 거절한다 — 먹히는 척하는
        컨트롤이 이 리포가 이름 붙인 claim-vs-behaviour 결함이다."""
        ft.set_data(_futdata([104.0] * len(DATES)))
        ds = _dataset()
        with pytest.raises(BacktestError):
            instruments.expand(ds, "3Y", 1, 1e10, DATES[0], 104.0)


class TestRollDays:
    """롤일 달력 [OWNER 2026-09-02 — "롤일 Δ 를 0 으로 마스크"].

    분기월(3·6·9·12)의 셋째 화요일, 휴장이면 그 직전 거래일. 가격으로 잡는
    방법(`price_adj` 대 `price_ctr`)은 `price_ctr` 이 없는 날 못 잡는다 —
    실측 2026-09-02: 3Y 는 43번의 롤 중 4번만 잡혔다. 달력은 전부 잡는다.
    """

    def test_the_third_tuesday_of_the_quarter_months(self):
        dates = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(400)
                 if (dt.date(2026, 1, 1) + dt.timedelta(days=i)).weekday() < 5]
        rolls = ft.roll_days(dates)
        # 2026: 3/17 · 6/16 · 9/15 · 12/15 가 셋째 화요일이다.
        for d in (dt.date(2026, 3, 17), dt.date(2026, 6, 16),
                  dt.date(2026, 9, 15), dt.date(2026, 12, 15)):
            assert d in rolls, d
            assert d.weekday() == 1
        assert all(d.month in (3, 6, 9, 12) for d in rolls)

    def test_a_closed_third_tuesday_falls_back_to_the_prior_session(self):
        """추석이 셋째 화요일에 걸린 해(2021-09-21·2024-09-17)의 그 자리."""
        base = [dt.date(2021, 9, 1) + dt.timedelta(days=i) for i in range(30)]
        sessions = [d for d in base if d.weekday() < 5
                    and d not in {dt.date(2021, 9, 20), dt.date(2021, 9, 21),
                                  dt.date(2021, 9, 22)}]
        rolls = ft.roll_days(sessions)
        assert dt.date(2021, 9, 17) in rolls      # 연휴 직전 거래일
        assert dt.date(2021, 9, 21) not in rolls  # 셋째 화요일이지만 휴장

    def test_no_dates_no_rolls(self):
        assert ft.roll_days([]) == set()
