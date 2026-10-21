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
    """순위 키는 **백분위**다 [2026-10-21] — 정렬은 `|백분위 − 50|`."""

    @staticmethod
    def _rows(*spec: tuple[str, float | None, float]):
        return [{"key": k, "pct": p, "sigma": None, "avgAbs": a} for k, p, a in spec]

    def test_하한_아래는_순위_밖이고_지우지_않는다(self):
        """±20계약짜리 종금이 1위가 되는 것을 막는 그 하한."""
        rows = flow.rank_rows(
            self._rows(("MERCH", 97.6, 27.0), ("SECU", 28.2, 6961.0)),
            flow.RANK_FLOOR)
        by = {r["key"]: r for r in rows}
        assert by["MERCH"]["ranked"] is False
        assert by["MERCH"]["rank"] is None       # 「없다」와 「0등」은 다른 말
        assert by["SECU"]["rank"] == 1
        assert len(rows) == 2                     # 지우지 않는다

    def test_백분위로도_하한이_필요하다(self):
        """★**내가 틀린 자리** [실측 2026-10-21].

        바꾸기 전에 「백분위는 안 터지니 하한을 없앨 수 있다」로 적었는데, 전수로
        재니 하한 아래가 1위를 가져가는 비중이 백분위 **37.9/60.8/29.1%** 로 σ
        (36.6/57.4/27.7%)와 거의 같고 **오히려 살짝 더 샌다.** 종금이 10계약
        거래한 날 백분위 97.6 이 **옳고** 다만 뜻이 없다 — 하한이 막던 것은 σ 의
        폭발이 아니라 그 뜻 없음이었다.

        그래서 이 시험이 **하한 없이 세우면 어떻게 되나**를 못 박는다.
        """
        spec = (("MERCH", 97.6, 2.0), ("SECU", 52.4, 3491.0))
        #: 하한을 0 으로 두면(= 없애면) 10계약짜리가 1위다.
        no_floor = flow.rank_rows(self._rows(*spec), 0.0)
        assert [r["key"] for r in no_floor] == ["MERCH", "SECU"]
        #: 하한을 두면 뜻 있는 쪽이 1위이고 작은 쪽은 순위 밖이다.
        with_floor = flow.rank_rows(self._rows(*spec), flow.RANK_FLOOR)
        assert [r["key"] for r in with_floor] == ["SECU", "MERCH"]
        assert with_floor[1]["ranked"] is False

    def test_극단성으로_세운다_방향이_아니라(self):
        """백분위 10 이 72 보다 센 날이다 — 큰 매도도 극단이다."""
        rows = flow.rank_rows(
            self._rows(("PENS", 72.0, 702.0), ("BANK", 10.0, 3805.0)),
            flow.RANK_FLOOR)
        assert [r["key"] for r in rows] == ["BANK", "PENS"]

    def test_50은_평소다(self):
        """정확히 평소인 주체가 꼴등이어야 한다 — `|50 − 50| = 0`."""
        rows = flow.rank_rows(
            self._rows(("FLAT", 50.0, 9999.0), ("HOT", 55.0, 9999.0)),
            flow.RANK_FLOOR)
        assert [r["key"] for r in rows] == ["HOT", "FLAT"]

    def test_백분위를_못_낸_주체도_순위_밖이다(self):
        rows = flow.rank_rows(self._rows(("X", None, 9999.0)), flow.RANK_FLOOR)
        assert rows[0]["ranked"] is False

    def test_순위_밖은_뒤에_선다(self):
        rows = flow.rank_rows(
            self._rows(("SMALL", 99.9, 1.0), ("BIG", 51.0, 9999.0)),
            flow.RANK_FLOOR)
        assert [r["key"] for r in rows] == ["BIG", "SMALL"]

    def test_현물_하한은_칼날_위에_없다(self):
        """국가지자체 일평균 49,450 이 하한에서 1% 아래면 날마다 뒤집힌다 —
        그래서 틈 가운데(40,000)로 내렸다. 그 여유를 여기서 지킨다."""
        assert flow.CASH_RANK_FLOOR <= 49_450 * 0.9
        assert flow.CASH_RANK_FLOOR >= 34_924 * 1.1


class Test백분위:
    """0~100 에 갇히고 분포를 가정하지 않는다. 동점은 **중간 순위**."""

    def test_창이_안_차면_None이다(self):
        assert flow.percentile_of([1] * (flow.MIN_OBS - 1), 5) is None

    def test_0에_몰린_주체의_0은_중앙에_선다(self):
        """★동점을 절반씩 나눠 갖는 규약 — 「미만의 수」로만 세면 0 이 **바닥**
        으로 읽힌다. 종금처럼 0 이 많은 주체에서 그게 거짓이 된다."""
        hist = [0] * 200 + [10] * 26 + [-10] * 26
        got = flow.percentile_of(hist, 0)
        assert got is not None and 45.0 <= got <= 55.0

    def test_최고와_최저가_끝에_붙는다(self):
        """⚠`x or 기본값` 을 쓰지 않는다 — **0.0 이 유효한 값**이라
        `0.0 or 100` 이 100 이 된다(이 시험을 쓰면서 한 번 걸렸다)."""
        hist = list(range(-130, 130))
        hi = flow.percentile_of(hist, 10_000)
        lo = flow.percentile_of(hist, -10_000)
        assert hi is not None and hi > 99.0
        assert lo is not None and lo < 1.0

    def test_꼬리가_두꺼워도_안_터진다(self):
        """σ 가 터지는 모양 — 거의 전부 0 이고 한 번 큰 값. 백분위는 갇힌다."""
        hist = [0] * 259 + [1_000_000]
        got = flow.percentile_of(hist, 50)
        assert got is not None and 0.0 <= got <= 100.0


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
        #: ★**영합이어야 한다** [고침 2026-10-20]. 종전에는 열 주체가 전부 같은
        #: 값이라 하루 합이 ±1,000,000 이었다 — 실제 `ktb_investor` 는 열 주체 합이
        #: 0 인 완결 회계이고(`flow.py` 머리 §현물 ②), 그 성질을 안 닮은 픽스처
        #: 위에서는 「표가 닫혔나」를 아예 못 잰다. 주체마다 **부호를 갈라** 합을
        #: 0 으로 두되, 봉마다 뒤집는 것은 그대로 둔다(σ 가 서야 순위 시험이 산다).
        cash = {c: [(1 if j % 2 else -1) * 100_000 * (1 if i % 2 else -1)
                    for i in range(n)]
                for j, (c, _) in enumerate(flow.CASH_COLS)}
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

    def test_시장_칼럼이_없으면_2x2를_안_싣는다(self, injected):
        """픽스처에는 `mkt` 가 없다 — 그러면 **지어내지 않는다**."""
        b = flow.board("fut", "3Y")
        assert b["oi"] is None
        assert b["series"]["price"] is None and b["series"]["oi"] is None

    def test_현물면은_2x2를_가지지_않는다(self, injected):
        """현물엔 미결제가 없다. 열쇠는 있고 값이 `None` 이어야 화면이 추측을 안 한다."""
        b = flow.board("cash", "ALL")
        assert "oi" in b and b["oi"] is None

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

    def test_가정이_섞인_열을_표가_말한다(self, injected):
        """★[OWNER 2026-10-20] PD 가 켜지면 금융투자·은행 칸은 「실제로 산 수」가
        아니다 — 조건 줄의 회색 문장만 그 사실을 말하면 **표만 보고는 못 가린다**.
        어느 열이 가정인지 페이로드가 든다."""
        off = flow.board("cash", "ALL", span=None)["matrix"]
        assert not any(c["pd"] for c in off["cols"]), "안 켰는데 가정 표식이 섰어요"
        on = flow.board("cash", "ALL", span=None, pd_share=0.6)["matrix"]
        marked = {c["key"] for c in on["cols"] if c["pd"]}
        assert marked == set(flow.PD_COLS)

    def test_표가_닫혔나를_서버가_센다(self, injected):
        """주체 합은 PD 끔이면 0, 켬이면 발행과 같다 — 그 한 줄이 「만기물 분해가
        샜나 · PD 가 두 번 더해졌나」를 동시에 잡는다."""
        off = flow.board("cash", "ALL", span=None)["matrix"]["check"]
        assert off["ok"] and off["sum"] == 0 and off["breaks"] == []
        assert "0 이에요" in off["say"]
        on = flow.board("cash", "ALL", span=None, pd_share=0.6)["matrix"]["check"]
        assert on["ok"] and on["pd"] and "발행과 같아요" in on["say"]

    def test_안_닫히는_날은_지목한다(self, injected):
        """★합만 보면 반올림이 쌓여 **깨진 하루**가 그 속에 숨는다 — 실제 자료에
        2026-04-13 하루가 350억이고 그것이 1년 창 잔차의 거의 전부다. 「어긋나요」만
        적으면 쓸 수 없는 경고라, 날짜와 크기를 든다."""
        d = flow.load()
        dates, _ = d.cash["ALL"]
        # 한 봉에 반올림으로 설명 안 되는 구멍을 낸다.
        d.cash["3Y"][1]["insurance"][-2] += flow.CHECK_BREAK * 3
        got = flow.board("cash", "ALL", span=None)["matrix"]["check"]
        assert got["ok"] is False
        assert got["breaks"] and got["breaks"][0]["date"] == dates[-2]
        assert got["breaks"][0]["amount"] == flow.CHECK_BREAK * 3
        assert dates[-2] in got["say"]
        d.cash["3Y"][1]["insurance"][-2] -= flow.CHECK_BREAK * 3

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
        assert paths == {"/api/flow/board", "/api/flow/history/{key}",
                         "/api/flow/issuance",
                         #: 수급 신호 실험 [OWNER 2026-10-20] — 라이브 전용·캐시 없음.
                         "/api/flow/lab"}
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


class Test미결제분해:
    """가격 × 미결제약정 2×2 [2026-10-21 — 외부 관례를 옮긴 것].

    재는 것은 **네 칸의 정의**와 **0 을 어디에도 붙이지 않는다**는 것이다. 가격이
    제자리인 날을 한 칸에 넣으면 그 칸의 수가 거짓이 된다.
    """

    def test_네_칸은_금리가_아니라_가격으로_정의된다(self):
        """뒤집으면 이 관례를 읽어 온 사람이 거꾸로 읽는다(모듈 머리 ⚠3)."""
        assert flow.oi_regime(+1.0, +100) == flow.OI_NEW_LONG
        assert flow.oi_regime(+1.0, -100) == flow.OI_SHORT_COVER
        assert flow.oi_regime(-1.0, +100) == flow.OI_NEW_SHORT
        assert flow.oi_regime(-1.0, -100) == flow.OI_LONG_LIQ

    def test_한쪽이_0인_날은_네_칸_어디도_아니다(self):
        assert flow.oi_regime(0.0, +100) is None
        assert flow.oi_regime(+1.0, 0) is None
        assert flow.oi_regime(0.0, 0) is None

    def test_집계는_구간만_세고_분모를_같이_낸다(self):
        close = [100.0, 101.0, 100.0, 100.0, 99.0]
        oi = [1000.0, 1100.0, 1050.0, 1050.0, 1200.0]
        names, tally = flow.oi_tally(close, oi)
        #: 첫 봉은 차분이 없다 — 0 으로 채우면 없는 날을 센다.
        assert names[0] is None
        assert names[1] == flow.OI_NEW_LONG
        assert names[2] == flow.OI_LONG_LIQ
        assert names[3] is None
        assert names[4] == flow.OI_NEW_SHORT
        #: 다섯 봉 중 이름이 선 것은 셋이고, 이름 없는 봉은 분모에서도 빠진다.
        assert sum(tally.values()) == 3
        _n, last2 = flow.oi_tally(close, oi, span=2)
        assert sum(last2.values()) == 1 and last2[flow.OI_NEW_SHORT] == 1

    def test_첫_봉이_하나뿐이면_이름이_없다(self):
        names, tally = flow.oi_tally([100.0], [1000.0])
        assert names == [None] and sum(tally.values()) == 0


class TestDV01환산:
    """계약수로는 만기물을 더할 수 없다 [OWNER 2026-10-21].

    실측 2026-10-20: 3년 한 계약 28,562원/bp · 10년 84,134 — **2.95배**.
    """

    def test_선물_한_계약의_DV01이_만기마다_다르다(self):
        a = flow.fut_dv01_per_contract(3.909, "3Y")
        b = flow.fut_dv01_per_contract(4.189, "10Y")
        assert 28_000 < a < 29_000
        assert 83_000 < b < 85_000
        assert b / a > 2.5          # 계약수를 그냥 더하면 이만큼 틀린다

    def test_par_PVBP는_퍼센트를_받는다(self):
        """★이 리포가 단위로 세 번 틀린 자리 — `creditmatrix` 는 **소수**를 준다.

        0.03835(소수)를 그대로 넣으면 금리가 0 에 가까워 듀레이션이 만기와 같아
        지고, PVBP 가 **1.6배 크게** 나온다.
        """
        right = flow.par_pvbp(3.835, 3.0)      # 3.835%
        wrong = flow.par_pvbp(0.03835, 3.0)    # 소수를 그대로 넣은 꼴
        assert right < wrong
        assert wrong / right > 1.04            # 조용히 지나갈 크기가 아니다

    def test_금리가_0이면_듀레이션이_만기다(self):
        """극한 — 할인이 없으면 par 채권의 듀레이션은 만기와 같다."""
        got = flow.par_pvbp(0.0, 10.0)
        assert abs(got - 10.0 * 100.0 / 10_000.0) < 1e-12

    def test_현물_백만원당_DV01이_만기에_따라_커진다(self):
        got = [flow.cash_dv01_per_unit(4.0, b) for b in ("2Y", "10Y", "30Y")]
        assert got[0] < got[1] < got[2]
        assert got[2] / got[0] > 6              # 2년과 30년은 다른 물건이다

    def test_모르는_바구니는_0이고_지어내지_않는다(self):
        assert flow.cash_dv01_per_unit(4.0, flow.CASH_OTHER) == 0.0
        assert flow.cash_dv01_per_unit(4.0, "없는것") == 0.0

    def test_전체는_바구니마다_환산한_뒤_더한다(self):
        """★액면 합에 배수 하나를 곱하면 **틀린다**.

        2년물과 30년물에 액면 1,000 씩이면 액면 합은 2,000 이지만 DV01 합은
        배수가 다른 둘의 합이다.
        """
        buckets = {"2Y": {"X": [1000]}, "30Y": {"X": [1000]}}
        yields = {"2Y": [190.86], "30Y": [1683.20]}
        got = flow.cash_dv01_sum(buckets, yields)
        assert got["X"][0] == 1000 * 190.86 + 1000 * 1683.20
        #: 액면 합(2,000)에 한 배수를 곱한 어느 값과도 다르다.
        assert got["X"][0] != 2000 * 190.86
        assert got["X"][0] != 2000 * 1683.20

    def test_연수가_없는_바구니는_합에_안_들어간다(self):
        buckets = {"3Y": {"X": [10]}, flow.CASH_OTHER: {"X": [999]}}
        got = flow.cash_dv01_sum(buckets, {"3Y": [280.85]})
        assert got["X"][0] == 10 * 280.85

    def test_앞_채움은_원천이_늦으면_0이다(self):
        """지어내지 않는다 — 0 이면 그 봉이 DV01 합에 안 들어간다."""
        got = flow.align_forward(["2015-01-02", "2020-01-02", "2020-01-03"],
                                 [("2020-01-02", 5.0)])
        assert got == [0.0, 5.0, 5.0]

    def test_하한은_표시_눈금이_아니라_날것으로_잰다(self):
        """★내가 만든 단위 버그 [2026-10-21].

        DV01 눈금에서 `avgAbs` 가 원/bp 인데 하한은 계약·백만원이라, 같은 계열로
        재면 하한이 **조용히 무력해진다**. 「순위에 들 만큼 큰가」는 표시 눈금과
        무관한 성질이다.
        """
        dates = [f"2026-01-{1 + i % 28:02d}" for i in range(flow.WINDOW + 1)]
        native = [(100 if i % 2 else -100) for i in range(flow.WINDOW + 1)]
        shown = [v * 1000 for v in native]      # 환산해 1,000배로 커진 꼴
        row = flow._series_row("X", "X", "g", dates, shown, native)
        #: 하한이 보는 수는 **날것**이라 1,000배로 커지지 않는다.
        assert row["avgAbs"] == 100
        #: 그래서 하한 100 위에서 순위 밖이다.
        assert flow.rank_rows([row], 500.0)[0]["ranked"] is False
