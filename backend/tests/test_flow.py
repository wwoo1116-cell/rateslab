# -*- coding: utf-8 -*-
"""투자자별 수급 — 산술과 배관 [2026-10-19].

선례는 `test_creditdts.py` 다: `_fetch` 를 monkeypatch 로 끊어 **SQL 없이** 잰다.
`flow.py` 가 영합 폐쇄·누적·편차·순위를 `_fetch` 밖 순수 함수로 꺼내 둔 이유가
이것이고, 그래서 이 파일의 거의 전부는 자료를 안 탄다.

이 파일이 지는 명제 다섯:
    ① 기관계는 상위 집합이다 — 두 층을 같이 더하면 이중계상(함정 ①).
    ② 기타는 **영합 폐쇄**로 구한다 — `CLOSE` 역산 금지(함정 ②).
    ③ 편차는 **오늘을 뺀** 창에서 난다.
    ④ 하한 아래는 **순위 밖**이고 지우지 않는다.
    ⑤ 라우트가 붙어 있고 바닥·천장을 검사한다.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app import flow, ktb_issuance


def _row(**over: int) -> dict[str, int]:
    """선물 한 행 — 세분 여섯이 기관계를 이룬다(항등식이 **참인** 행)."""
    sub = {"SECU": -8556, "TRUST": -134, "BANK": -5243,
           "INSUR": 158, "MERCH": 20, "PENS": 670}
    sub.update({k: v for k, v in over.items() if k in sub})
    inst = sum(sub.values())
    row = {"INST": inst, "FRGN": -inst, "INDI": 0, "GOVT": 0, **sub}
    row.update(over)
    return row


class Test유니버스:
    def test_기관계는_세분_여섯의_합이다(self):
        """함정 ① — 2026-10-16 실측 행으로 재면 오차가 0 이다."""
        assert flow.inst_identity_error(_row()) == 0

    def test_항등식이_깨지면_수가_아니라_사실이_나온다(self):
        """어긋난 행은 **조용히 넘어가면 안 된다** — 그 차이가 이중계상의 크기다."""
        bad = _row()
        bad["INST"] = bad["INST"] + 100
        assert flow.inst_identity_error(bad) == 100

    def test_세분은_여섯이고_대분류와_안_겹친다(self):
        subs = {k for k, _ in flow.FUT_SUB}
        tops = {k for k, _ in flow.FUT_TOP}
        assert len(subs) == 6
        assert subs & tops == set()
        assert "INST" in tops


class Test영합:
    def test_기타는_가격_없이_구해진다(self):
        """함정 ② — `ETCPRICE / CLOSE` 역산 금지. 네 주체만으로 닫힌다."""
        got = flow.close_zero_sum({"INST": -13085, "FRGN": 13683,
                                   "INDI": -598, "GOVT": 0})
        assert got == 0

    def test_다섯을_다_더하면_0이다(self):
        top = {"INST": -6329, "FRGN": 6283, "INDI": -52, "GOVT": 0}
        etc = flow.close_zero_sum(top)
        assert etc == 98
        assert sum(top.values()) + etc == 0

    def test_정부는_영합에_들어가되_화면에선_빠진다(self):
        """전 구간 0 이라 화면에선 빼지만, 폐쇄식에서 빼면 식이 틀린다."""
        assert flow.FUT_DEAD == "GOVT"
        assert flow.FUT_DEAD not in {k for k, _ in flow.FUT_TOP + flow.FUT_SUB}
        assert flow.close_zero_sum({"INST": 0, "FRGN": 0, "INDI": 0, "GOVT": 7}) == -7


class Test누적:
    def test_누적은_길이를_지킨다(self):
        assert flow.cumulative([1, 2, 3]) == [1, 3, 6]
        assert flow.cumulative([]) == []

    def test_음수가_섞여도_되돌아온다(self):
        assert flow.cumulative([5, -5, 3]) == [5, 0, 3]


class Test편차:
    def test_창은_오늘을_뺀다(self):
        """오늘이 제 분모를 키우면 「평소 대비 오늘」이 아니게 된다."""
        hist = [10, -10] * 130           # σ = 10
        sigma, avg = flow.sigma_of(hist, 20)
        assert sigma == 2.0
        assert avg == 10.0

    def test_관측이_얇으면_안_낸다(self):
        """지어낸 편차는 숫자처럼 보이는 잡음이다."""
        sigma, _ = flow.sigma_of([1, -1] * 10, 5)
        assert sigma is None

    def test_안_움직이는_주체는_편차가_없다(self):
        """σ 가 0 이면 나눌 수 없다 — 0 으로도 큰 수로도 안 채운다."""
        sigma, avg = flow.sigma_of([0] * 200, 20)
        assert sigma is None
        assert avg == 0.0

    @pytest.mark.parametrize("n", [flow.MIN_OBS - 1, flow.MIN_OBS])
    def test_문턱_양쪽을_다_민다(self, n):
        """첫 판이 문턱에서 통과해 버리는 것을 막는다(`test_creditdts` 의 그 규율).

        ★길이를 **정확히 n** 으로 만든다 — `* (n//2+1)` 로 만들면 119 를 달라고
        해놓고 120 을 주게 된다(첫 판에서 밟았다).
        """
        hist = [10 if i % 2 else -10 for i in range(n)]
        assert len(hist) == n
        sigma, _ = flow.sigma_of(hist, 20)
        assert (sigma is not None) is (n >= flow.MIN_OBS)


class Test이동평균:
    def test_창_미만은_None이고_그_뒤는_평균이다(self):
        assert flow.moving_average([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
        assert flow.moving_average([5], 1) == [5.0]
        assert flow.moving_average([], 5) == []

    def test_PD_적용은_두_열만_바꾼다(self):
        cols = {"financial_investment": [0, 0], "bank": [0, 0], "insurance": [7, 7]}
        out = flow.apply_pd(cols, [0.0, 1000.0], 0.6)
        assert out["financial_investment"] == [0, 600]
        assert out["bank"] == [0, 400]
        assert out["insurance"] == [7, 7]
        assert cols["bank"] == [0, 0]            # 원본은 그대로


class Test순위:
    @staticmethod
    def _rows(*spec: tuple[str, float | None, float]):
        return [{"key": k, "sigma": s, "avgAbs": a} for k, s, a in spec]

    def test_하한_아래는_순위_밖이고_지우지_않는다(self):
        """±20계약짜리 종금이 1위가 되는 것을 막는 그 하한."""
        rows = flow.rank_rows(
            self._rows(("MERCH", 3.1, 27.0), ("SECU", -0.93, 6961.0)),
            flow.RANK_FLOOR)
        by = {r["key"]: r for r in rows}
        assert by["MERCH"]["ranked"] is False
        assert by["MERCH"]["rank"] is None       # 「없다」와 「0등」은 다른 말
        assert by["SECU"]["rank"] == 1
        assert len(rows) == 2                     # 지우지 않는다

    def test_편차의_크기로_세운다_부호가_아니라(self):
        """−1.09 가 +0.72 보다 센 날이다."""
        rows = flow.rank_rows(
            self._rows(("PENS", 0.72, 702.0), ("BANK", -1.09, 3805.0)),
            flow.RANK_FLOOR)
        assert [r["key"] for r in rows] == ["BANK", "PENS"]

    def test_편차를_못_낸_주체도_순위_밖이다(self):
        rows = flow.rank_rows(self._rows(("X", None, 9999.0)), flow.RANK_FLOOR)
        assert rows[0]["ranked"] is False

    def test_순위_밖은_뒤에_선다(self):
        rows = flow.rank_rows(
            self._rows(("SMALL", 9.9, 1.0), ("BIG", 0.1, 9999.0)),
            flow.RANK_FLOOR)
        assert [r["key"] for r in rows] == ["BIG", "SMALL"]

    def test_현물_하한은_칼날_위에_없다(self):
        """국가지자체 일평균 49,450 이 하한에서 1% 아래면 날마다 뒤집힌다 —
        그래서 틈 가운데(40,000)로 내렸다. 그 여유를 여기서 지킨다."""
        assert flow.CASH_RANK_FLOOR <= 49_450 * 0.9
        assert flow.CASH_RANK_FLOOR >= 34_924 * 1.1


class Test페이로드:
    @staticmethod
    def _data() -> flow.FlowData:
        """가짜 두 원천 — `_fetch` 를 대신한다. 날짜는 두 해에 걸친다."""
        n = flow.WINDOW + 10
        dates = [f"2025-{1 + i % 12:02d}-{1 + i % 28:02d}" for i in range(n - 5)]
        dates += [f"2026-01-{1 + i:02d}" for i in range(5)]
        cols: dict[str, list[int]] = {}
        for k, _ in flow.FUT_SUB:
            cols[k] = [(1000 if k == "SECU" else 10) * (1 if i % 2 else -1)
                       for i in range(n)]
        cols["INST"] = [sum(cols[k][i] for k, _ in flow.FUT_SUB) for i in range(n)]
        cols["FRGN"] = [-v for v in cols["INST"]]
        cols["INDI"] = [0] * n
        cols["GOVT"] = [0] * n
        cols["ETC"] = [0] * n
        cash = {c: [100_000 * (1 if i % 2 else -1) for i in range(n)]
                for c, _ in flow.CASH_COLS}
        #: 만기물 바구니 — 현물은 **전부 3년물**에 들고 나머지는 0. `ALL` 은 그 합이라
        #: 분리 전 한 장과 같은 수다(§현물 만기물 ①).
        buckets = {
            k: (dates, cash if k == "3Y" else {c: [0] * n for c, _ in flow.CASH_COLS})
            for k in flow.CASH_TENORS if k != "ALL"
        }
        buckets[flow.CASH_OTHER] = (dates, {c: [0] * n for c, _ in flow.CASH_COLS})
        buckets["ALL"] = (dates, flow.sum_cash_buckets(buckets, dates))
        return flow.FlowData(fut={t: (dates, cols) for t in flow.FUT_TENORS},
                             cash=buckets, watermark=("x|y", 1))

    @staticmethod
    def _issuance(dates: list[str]):
        """가짜 발행 통계 — 현물 날짜축의 **올해** 날 하나에 3년 경쟁 2.4조, 그리고
        현물이 아직 안 닿은 날(마지막 날 뒤)에 10년 경쟁 하나."""
        from app import ktb_issuance as ki
        year = dates[-1][:4]
        on = next(d for d in dates if d[:4] == year)
        after = f"{year}-12-31"
        raw = [
            {"구분": "경쟁", "종목명": "국고03500-2906", "isin": "KR103501GG62", "만기물": "3",
             "입찰일": dt.date.fromisoformat(on), "입찰금액": 24000, "응찰금액": 66630,
             "응찰률": 277.6, "낙찰금액": 24000, "낙찰금리": 3.94, "최저낙찰금리": 3.94,
             "최고낙찰금리": 3.94, "부분낙찰률": 45.0, "기관수": None,
             "updated_at": dt.datetime(2026, 10, 19, 2, 35, 3)},
            {"구분": "경쟁", "종목명": "국고04250-3606", "isin": "KR103503GG60", "만기물": "10",
             "입찰일": dt.date.fromisoformat(after), "입찰금액": 21000, "응찰금액": 60060,
             "응찰률": 286.0, "낙찰금액": 21000, "낙찰금리": 4.155, "최저낙찰금리": 4.155,
             "최고낙찰금리": 4.155, "부분낙찰률": 32.7, "기관수": None,
             "updated_at": dt.datetime(2026, 10, 19, 2, 35, 3)},
        ]
        tenor_of = {"KR103501GG62": "3Y", "KR103503GG60": "10Y"}
        return ki.IssuanceData(rows=ki.normalize(raw, tenor_of), tenor_of=tenor_of,
                               schedule=[], watermark=("i", 2))

    @pytest.fixture
    def injected(self):
        from app import ktb_issuance as ki
        d = self._data()
        flow.set_data(d)
        ki.set_data(self._issuance(d.cash["ALL"][0]))
        yield
        flow.set_data(None)
        ki.set_data(None)

    def test_선물면이_대조와_순위를_같이_낸다(self, injected):
        b = flow.board("fut", "3Y")
        assert b["unit"] == "계약"
        assert {t["key"] for t in b["top"]} == {"FRGN", "INST", "INDI", "ETC"}
        assert {r["key"] for r in b["sub"]} == {k for k, _ in flow.FUT_SUB}

    def test_대분류는_합이_0이다(self, injected):
        b = flow.board("fut", "3Y")
        assert sum(t["value"] for t in b["top"]) == 0

    def test_그림은_최대_네_계열이다(self, injected):
        """N계열 범주형 팔레트가 없다 — 전수는 표가 진다."""
        b = flow.board("fut", "3Y")
        assert len(b["series"]["cum"]) <= 4

    def test_두_원천의_asof_를_따로_싣는다(self, injected):
        """현물이 늦게 들어오는 것이 정상이라 한 수로 못 적는다."""
        b = flow.board("fut", "3Y")
        assert set(b["asof"]) == {"fut", "cash"}

    def test_정부는_이유와_함께_빠진다(self, injected):
        b = flow.board("fut", "3Y")
        why = {e["id"]: e["why"] for e in b["excluded"]}
        assert "GOVT" in why and why["GOVT"]

    def test_YTD_는_해를_가른다(self, injected):
        """2026 다섯 봉만 센다 — 전체 합이 아니다."""
        b = flow.board("fut", "3Y")
        secu = next(r for r in b["sub"] if r["key"] == "SECU")
        assert abs(secu["ytd"]) <= 5 * 1000

    def test_현물면엔_대분류가_없다(self, injected):
        """현물엔 상위 집합이 없다 — 빈 칸이 맞다."""
        b = flow.board("cash", "ALL")
        assert b["top"] == []
        assert b["unit"] == "백만원"
        assert [t["key"] for t in b["tenors"]] == list(flow.CASH_TENORS)

    def test_만기물의_합이_전체다(self, injected):
        """`ALL` 은 바구니의 합 — 분리 전 화면과 같은 수여야 한다(§현물 만기물 ①)."""
        a = {r["key"]: r for r in flow.board("cash", "ALL")["sub"]}
        t3 = {r["key"]: r for r in flow.board("cash", "3Y")["sub"]}
        t10 = {r["key"]: r for r in flow.board("cash", "10Y")["sub"]}
        for k in a:
            assert a[k]["d1"] == t3[k]["d1"] + t10[k]["d1"]
            assert a[k]["ytd"] == t3[k]["ytd"]
            assert t10[k]["d1"] == 0
        assert flow.board("cash", "3Y")["basis"].startswith("3년물만 봐요.")

    def test_행렬의_합계가_전체_바구니와_같다(self, injected):
        """테너 × (발행 + 주체) 표 [OWNER 2026-10-20].

        맨 아랫줄 `합계` 는 **따로 센 수**다 — 행마다의 바구니를 더한 것이고,
        `ALL` 바구니는 SQL 집계의 합이다. 둘이 어긋나면 만기물을 못 푼 종목이
        생겼다는 뜻이라 여기서 잡힌다.
        """
        b = flow.board("cash", "ALL", span=None)
        m = b["matrix"]
        assert [r["key"] for r in m["rows"]] == list(ktb_issuance.TENORS)
        dates, cols = flow.load().cash["ALL"]
        for c, _lab in flow.CASH_COLS:
            assert m["total"]["cols"][c] == sum(cols[c]), c
            assert m["total"]["cols"][c] == sum(r["cols"][c] for r in m["rows"]), c
        assert m["to"] == dates[-1]
        # 발행 열은 공급표 그대로 — 3년 2.4조만 날짜축에 얹히고 10년은 축 뒤다.
        assert m["total"]["supply"] == 2_400_000
        assert m["pending"] == 1

    def test_행렬은_구간을_봉_수로_자른다(self, injected):
        """표와 그림이 **같은 창**을 봐야 한다 — 화면이 쓰는 봉 수를 그대로 받는다."""
        dates, cols = flow.load().cash["ALL"]
        for span in (5, 63, len(dates), len(dates) + 100):
            m = flow.board("cash", "ALL", span=span)["matrix"]
            cut = flow.span_slice(len(dates), span)
            assert m["from"] == dates[cut][0]
            for c, _lab in flow.CASH_COLS:
                assert m["total"]["cols"][c] == sum(cols[c][cut]), (span, c)
        # 전구간을 넘는 수와 None 은 같은 것이다.
        assert (flow.board("cash", "ALL", span=99_999)["matrix"]["from"]
                == flow.board("cash", "ALL", span=None)["matrix"]["from"] == dates[0])

    def test_행렬의_발행_열은_PD_노브에_안_움직인다(self, injected):
        """노브는 공급을 **주체에 더하는** 것이다 — 공급 자체를 바꾸면 두 번 센다."""
        off = flow.board("cash", "ALL", span=None)["matrix"]
        on = flow.board("cash", "ALL", span=None, pd_share=0.6)["matrix"]
        assert on["total"]["supply"] == off["total"]["supply"]
        for a, b2 in zip(off["rows"], on["rows"]):
            assert a["supply"] == b2["supply"], a["key"]
        fi, bk = flow.PD_COLS
        assert on["total"]["cols"][fi] - off["total"]["cols"][fi] == 1_440_000
        assert on["total"]["cols"][bk] - off["total"]["cols"][bk] == 960_000

    def test_PD_문구가_제도와_가정을_가른다(self, injected):
        """[OWNER 2026-10-20] 둘이 나눠 받는 것은 제도고, 60 이라는 수가 가정이다.

        합이 100 이라는 것까지 「가정」으로 읽히면 안 된다 — `apply_pd` 가 몫
        하나를 받아 나머지를 은행에 주므로 합은 **구조적으로** 100 이다.
        """
        note = flow.board("cash", "ALL", pd_share=0.6)["pd"]["note"]
        assert "제도" in note and "가정" in note
        assert "60 대 40" in note
        # 어떤 몫이든 둘이 공급을 정확히 나눈다.
        for share in (0.0, 0.25, 0.6, 1.0):
            off = flow.board("cash", "ALL", span=None)["matrix"]["total"]["cols"]
            on = flow.board("cash", "ALL", span=None, pd_share=share)["matrix"]["total"]["cols"]
            fi, bk = flow.PD_COLS
            added = (on[fi] - off[fi]) + (on[bk] - off[bk])
            assert added == 2_400_000, share

    def test_PD_인수는_두_주체에만_더해진다(self, injected):
        """발행시장 인수분(2.4조 = 2,400,000백만원)이 금융투자 60%·은행 40% 로 들어가고
        다른 주체는 그대로다. 현물이 아직 안 닿은 날의 입찰은 **세어서 말한다**."""
        off = {r["key"]: r for r in flow.board("cash", "ALL")["sub"]}
        b = flow.board("cash", "ALL", pd_share=0.6)
        on = {r["key"]: r for r in b["sub"]}
        assert on["financial_investment"]["ytd"] - off["financial_investment"]["ytd"] == 1_440_000
        assert on["bank"]["ytd"] - off["bank"]["ytd"] == 960_000
        assert on["insurance"]["ytd"] == off["insurance"]["ytd"]
        assert b["pd"]["supplyYtd"] == 2_400_000
        assert b["pd"]["pending"] == 1          # 10년 입찰은 현물 날짜축 뒤 — 반영 전
        assert "가정" in b["pd"]["note"] and "가정" in b["basis"]
        # 만기물을 가르면 3년 공급은 3년 바구니에만 든다.
        t10 = flow.board("cash", "10Y", pd_share=0.6)
        assert t10["pd"]["supplyYtd"] == 0

    def test_PD_배분은_0과_1_사이다(self, injected):
        with pytest.raises(flow.FlowError):
            flow.board("cash", "ALL", pd_share=1.5)
        assert flow.board("cash", "ALL", pd_share=None)["pd"] is None

    def test_이동평균은_서버가_내고_창_미만은_None이다(self, injected):
        b = flow.board("fut", "3Y", ma=20, daily="BANK")
        ma = b["series"]["ma"]
        assert ma["key"] == "BANK" and ma["window"] == 20
        assert ma["values"][:19] == [None] * 19
        assert ma["values"][19] is not None
        assert b["series"]["daily"]["key"] == "BANK"
        assert flow.board("fut", "3Y")["series"]["ma"] is None
        with pytest.raises(flow.FlowError):
            flow.board("fut", "3Y", ma=7)
        with pytest.raises(flow.FlowError):
            flow.board("fut", "3Y", daily="NOPE")

    def test_화면_문장은_해요체다(self, injected):
        """판정은 `test_register.FORMAL` 과 같은 자다 — **금칙**으로 잰다.
        끝 글자로 재면 괄호로 닫는 문장(「… 순위 밖).」)이 거짓 빨강이 된다."""
        import re
        formal = re.compile(r"(니다|한다\.|이다\.|않는다\.)")
        for side in ("fut", "cash"):
            b = flow.board("cash") if side == "cash" else flow.board("fut", "3Y")
            assert not formal.search(b["basis"]), b["basis"]
            assert "예요" in b["basis"] or "에요" in b["basis"]

    def test_모르는_면과_만기는_거절한다(self, injected):
        with pytest.raises(flow.FlowError):
            flow.board("xxx")
        with pytest.raises(flow.FlowError):
            flow.board("fut", "7Y")

    def test_이력은_누적과_일별을_같이_낸다(self, injected):
        h = flow.history("FRGN", side="fut", tenor="3Y")
        assert len(h["dates"]) == len(h["daily"]) == len(h["cum"])
        with pytest.raises(KeyError):
            flow.history("NOPE")


class Test라우트:
    def test_붙어_있고_바닥을_검사한다(self):
        from fastapi.testclient import TestClient

        from app import main as M

        paths = {r.path for r in M.app.routes if "flow" in getattr(r, "path", "")}
        assert paths == {"/api/flow/board", "/api/flow/history/{key}", "/api/flow/issuance"}
        c = TestClient(M.app)
        assert c.get("/api/flow/board?side=xxx").status_code == 422
        assert c.get("/api/flow/board?side=fut&tenor=7Y").status_code == 422
        assert c.get("/api/flow/board?side=cash&tenor=7Y").status_code == 422
        assert c.get("/api/flow/board?side=fut&tenor=3Y&ma=7").status_code == 422
        assert c.get("/api/flow/board?side=cash&tenor=ALL&pd=1.5").status_code == 422

    def test_워터마크는_복합이다(self):
        """★한쪽만 세면 다른 쪽이 들어와도 캐시 열쇠가 안 바뀐다 — 두 원천이
        다른 시각에 도착하므로 그 실수가 조용히 하루를 숨긴다."""
        import inspect
        src = inspect.getsource(flow.watermark)
        # f-string 이라 소스에는 **자리표시자**가 남는다 — 값이 아니라 그것을 본다.
        assert "{FUT_TABLE}" in src and "{CASH_TABLE}" in src
        assert '"{f[0]}|{c[0]}"' in src.replace("f\"", '"')
