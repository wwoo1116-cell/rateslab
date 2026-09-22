# -*- coding: utf-8 -*-
"""대사표의 **다리 줄** — 스프레드는 한 물건이 아니다
[OWNER 2026-09-03 — "채권 KRD, bp, 손익과 IRS KRD, bp, 손익, 그리고 종합
손익이 하루에 찍혀야 함"].

## 무엇을 지키나

화면이 다리마다 세 줄(KRD·Δbp·손익)을 세우려면 그 셋이 **서버에서** 와야 하고
(§16 — 브라우저는 계산하지 않는다), 오면 항등 둘이 봉마다 닫혀야 한다:

    Σ 다리 손익 = 평가           ← 분해가 실제로 그 값을 만든다
    Σ 다리 KRD  = 0 (다리 둘)    ← DV01 중립이 눈으로 보인다
    Σ 다리 캐리 = 캐리           ← `c = -position × carry[i]` 가 선형이라

이 셋이 깨지면 화면의 표는 **자기와 다투는 표**가 된다. 세로합이 안 맞는
대사표는 대사표가 아니라 숫자 더미다.

## 왜 라우트를 타나

분해는 세 파일에 걸쳐 있다 — `mrcarry.carry_rates_by_leg`(캐리) ·
`mr._futures_series`(다리 레벨) · `main._attach_leg_recon`(부호와 곱셈). 어느
하나만 단위시험하면 셋을 잇는 배선이 안 잡힌다. 실제로 이 검사가 서는 자리는
「페이로드가 스스로 닫히나」이므로 라우트를 탄다.
"""
import datetime as dt

import pytest

from app import mr as mr_mod


def _sql_reachable() -> bool:
    try:
        mr_mod.series_points("BSS-3Y")
        return True
    except Exception:
        return False


pytestmark_live = pytest.mark.skipif(
    not _sql_reachable(), reason="MR 계열 SQL 에 닿지 않습니다"
)

#: 원 단위 표라 1원이 기준이다 — 서버의 `LEG_RECON_TOL_KRW` 와 같은 자.
TOL = 1.0

#: 계열 종류마다 다리 이름과 개수가 정해져 있다(`mrcarry.LEG_NAMES`).
#:
#: 다리 **분해**(감도·Δ·손익)는 이제 **아무 계열에도 없다.** 2026-09-03 에 BSS 가,
#: 2026-09-04 에 선물 넷이 실가격 회계로 옮겨가면서 그 구간의 돈은 대사표가 세고,
#: 점에는 「일별 레벨」이 쓰는 **레벨만** 실린다 — 폐기된 근사의 감도를 같이
#: 세우면 한 화면에 두 회계가 선다(`main._attach_leg_recon` 의 `levels_only`).
#:
#: 종전의 `CASES`(선물 = 근사 분해가 오던 계열)는 그래서 비었고, 그것을 지키던
#: 시험 셋(다리 세로합·줄의 곱셈·다리 KRD 부호)은 **명제가 죽어서** 폐기했다.
#: 같은 명제의 실가격 판은 `TestFuturesRealRecon` 이 진다.
#:
#: ★차례가 2026-09-22 에 **뒤집혔다** [OWNER — "스왑 - 채권현물 또는 국채선물"].
#: 값이 `IRS − 국고` 이므로 「다리0 − 다리1 = 값」이 스왑을 앞에 둬야 닫힌다 —
#: 아래 `TWO_LEG` 시험이 정확히 그것을 잰다.
LEVEL_ONLY = [
    ("BSS-3Y", ["IRS", "국고"]),
    ("BSS-7Y", ["IRS", "국고"]),
    ("FSW-3Y", ["IRS", "선물"]),
    ("FUT-KTB3", ["선물"]),
]
#: 다리가 둘인 계열 — 「다리 − 다리 = 값」이 성립하는 자리.
TWO_LEG = [(sid, names) for sid, names in LEVEL_ONLY if len(names) == 2]


@pytestmark_live
class TestLegRecon:
    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as c:
            yield c

    @pytest.mark.parametrize("sid,names", LEVEL_ONLY)
    def test_every_bar_carries_its_legs(self, client, sid, names):
        """**한 봉도 빠지지 않는다.** 일부만 있으면 화면이 어떤 날은 이중으로,
        어떤 날은 한 줄로 서서 읽는 사람이 그 차이를 데이터로 읽는다."""
        body = client.get(f"/api/mr/strategy?id={sid}").json()
        pts = body["points"]
        assert pts, f"{sid}: 봉이 없다"
        missing = [p["t"] for p in pts if not p.get("legs")]
        assert not missing, f"{sid}: 다리가 없는 봉 {len(missing)}개 (첫 {missing[:3]})"
        for p in pts:
            assert [g["k"] for g in p["legs"]] == names, f"{sid} {p['t']}"

    @pytest.mark.parametrize("sid,names", LEVEL_ONLY)
    def test_real_accounting_series_carry_levels_only(self, client, sid, names):
        """실가격 회계 계열은 점에 **레벨만** 온다.

        「일별 레벨」 칸이 그 값을 쓴다(`legs[].lvl`). 감도·손익·캐리는 폐기된
        근사의 값이라 안 싣는다 — 있으면 화면이 두 회계를 같이 세우게 된다.
        """
        pts = client.get(f"/api/mr/strategy?id={sid}").json()["points"]
        assert pts
        for p in pts:
            assert p.get("legs"), f"{sid} {p['t']}: 다리 레벨이 없다"
            assert [g["k"] for g in p["legs"]] == names
            for g in p["legs"]:
                assert set(g) == {"k", "lvl"}, f"{sid} {p['t']}: 근사의 값이 남아 있다"

    def test_a_roll_day_still_masks_the_value_delta(self, client):
        """롤일의 **Δ 는 여전히 0** 이다 — 그런데 이제 그 마스크는 돈에 안 닿는다.

        마스크의 근거는 값 계열이 **벤더 내재금리 직독**이라 계약이 갈리는 날
        통째로 튄다는 것이다(`mrbacktest` 의 그 주석). 그 명제는 살아 있다 —
        Δ 는 그 계열 위의 변화이므로 여기서 0 이 맞다.

        죽은 것은 **돈 쪽**이다. 2026-09-04 부터 그 구간의 돈은 조정가 차분에서
        나오고 조정가는 롤갭이 이미 빠진 계열이라, 마스크가 고치던 병이 그 자리에
        없다. 대신 갈아타기의 **마찰**을 비용으로 문다(`futures.roll_cost`).
        그래서 여기서 재는 것은 Δ 하나이고, 다리 손익은 **아예 안 온다.**
        """
        pts = client.get("/api/mr/strategy?id=FSW-3Y").json()["points"]
        rolls = [p for p in pts if p.get("roll")]
        assert rolls, "롤일이 한 봉도 없다 — 표본이나 규칙이 바뀌었다"
        for p in rolls:
            assert p["dv"] == 0, f"{p['t']}: 스프레드 Δ 가 안 마스크됐다"
            for g in p["legs"]:
                assert set(g) == {"k", "lvl"}, f"{p['t']}: 근사의 값이 남아 있다"

    @pytest.mark.parametrize("sid,_names", TWO_LEG)
    def test_two_leg_series_are_the_spread_itself(self, client, sid, _names):
        """다리 둘인 계열은 `(다리0 − 다리1) × 100 = 값` 이 정확히 성립한다 —
        다리 레벨이 스프레드의 **재료**이지 옆에 붙은 참고값이 아니라는 사실이다."""
        pts = client.get(f"/api/mr/strategy?id={sid}").json()["points"]
        for p in pts[:500]:
            g, s = p["legs"][0]["lvl"], p["legs"][1]["lvl"]
            assert abs((g - s) * 100.0 - p["v"]) <= 0.05, f"{p['t']}: 다리 − 다리 ≠ 값"

@pytestmark_live
class TestRealRecon:
    """`/api/mr/recon` — **실가격 자산스왑 대사** [OWNER 2026-09-03 — "이 방향이
    정확한 대사"].

    BSS 를 자산스왑으로 세워 민평 노드를 1bp 씩 범프한 테너별 KRD 다. 값을
    만드는 것은 `cashbond` 이고 그쪽에 자기 시험이 있으므로, 여기서 재는 것은
    **MR 이 그것을 옳게 부르는가**다: 액면 환산 · 방향 · 못 세우는 자리.
    """

    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as c:
            yield c

    def test_a_trade_inside_the_matrix_gets_a_tenor_grid(self, client):
        """표가 서고, **줄마다 곱셈이 닫힌다**(`추정 = −KRD × Δbp`).

        이게 이 표의 전부다 — 테너별 KRD 를 세우는 이유가 그 곱셈이 테너마다
        보이게 하는 것이기 때문이다.
        """
        b = client.get("/api/mr/strategy?id=BSS-7Y").json()
        first = client.get("/api/mr/recon?id=BSS-7Y"
                           "&entry=2021-04-30&exit=2021-06-08&dir=-1").json()
        assert first["available"], first.get("why")
        assert first["tenors"], "테너 열이 비었다"
        assert first["rows"], "행이 없다"
        # 액면은 **그 거래의 진입일 커브**로 잰 것이다 — 머리의 액면(«지금
        # 세우면»)과 다른 것이 정상이다(2026-09-03 검산). 두 화면이 갈리지
        # 않는다는 것은 「명목 = 액면 × pv01 × 1e-4」가 닫히는 것으로 잰다.
        n = b["params"]["notional"]
        p0 = first["principal"]
        assert abs(p0["krw"] * p0["pv01"] * 1e-4 - n) < 1.0

        checked = 0
        for r in first["rows"]:
            krd, dbp, est = r.get("krd") or {}, r.get("dbp") or {}, r.get("est") or {}
            for lb, k in krd.items():
                d = dbp.get(lb)
                if d is None:
                    continue
                assert abs(-k * d - est.get(lb, 0.0)) <= 1.0, f"{r['t']} {lb}"
                checked += 1
            if r.get("estTotal") is not None:
                assert abs(sum(est.values()) - r["estTotal"]) <= 1.0, r["t"]
            if r.get("residual") is not None and r.get("valuation") is not None:
                assert abs(r["valuation"] - r["estTotal"] - r["residual"]) <= 1.0, r["t"]
        assert checked > 20, f"곱셈을 잰 칸이 {checked}개뿐이다"

    def test_the_sensitivity_sits_where_the_bond_lives(self, client):
        """KRD 가 **잔존만기 언저리 노드**에만 실린다.

        단일수익률 할인이라 노드 하나를 흔들면 잔존을 감싸는 두 노드에만
        가중치가 실린다(`cashbond._krd_bond`). 7년 자산스왑의 감도가 3M 에
        실려 있으면 그건 가격기를 잘못 부른 것이다.
        """
        r = client.get("/api/mr/recon?id=BSS-7Y"
                       "&entry=2021-04-30&exit=2021-06-08&dir=-1").json()
        mid = r["rows"][len(r["rows"]) // 2]
        hot = [lb for lb, v in (mid["krd"] or {}).items() if abs(v) > 1.0]
        assert hot, f"{mid['t']}: KRD 가 전부 0 이다"
        assert set(hot) <= {"5Y", "7Y", "10Y"}, f"{mid['t']}: 감도가 엉뚱한 데 있다 — {hot}"

    def test_a_trade_before_the_matrix_says_so_instead_of_inventing(self, client):
        """민평 이력 밖은 **비운다** [OWNER 2026-09-03]. 지어낸 대사를 세우면
        읽는 사람이 그것을 실측으로 읽는다."""
        r = client.get("/api/mr/recon?id=BSS-7Y"
                       "&entry=2015-06-11&exit=2015-08-18&dir=-1").json()
        assert r["available"] is False
        assert "민평" in r["why"] and "2020-01-02" in r["why"]
        assert "rows" not in r, "못 세운다면서 행을 보냈다"

    def test_futures_series_come_as_one_block(self, client):
        """선물 계열은 **블록 하나**로 온다 [OWNER 2026-09-07].

        자산스왑은 아니지만 자기 엔진의 실가격이 있다. FUT 은 선물 달력 한 표고,
        FSW 도 **한 표**다 — IRS 다리가 그 안에 `legTenors` 로 서서 하루가 일곱
        줄이 된다(백테스트 창이 2026-09-04 에 간 그 길).

        종전에는 FSW 가 둘이었다(선물 달력 + IRS 달력 — 엔진 단위 분리
        [OWNER 2026-08-25]). 그 분리는 «표는 자기 달력 위에 선다» 까지 살고,
        「한 거래의 두 다리는 한 표에」가 그 위에 얹혔다. 그 앞의 명제
        («자산스왑이 아니라 못 세운다»)는 2026-09-04 에 죽었다.
        """
        want = {"FUT-KTB3": [], "FSW-3Y": ["선물", "IRS"]}
        for sid, legs in want.items():
            r = client.get(f"/api/mr/recon?id={sid}"
                           "&entry=2021-01-04&exit=2021-02-01&dir=-1").json()
            assert r["available"] is True, (sid, r.get("why"))
            assert [b["name"] for b in r["blocks"]] == ["선물"], sid
            blk = r["blocks"][0]
            # 다리는 **FSW 에만** 있다. FUT 아웃라이트는 물건이 하나라 그 질문이
            # 없고, 빈 목록을 실으면 화면이 다리 판으로 들어가 열을 못 세운다.
            assert [lg["name"] for lg in blk.get("legTenors", [])] == legs, sid
            if legs:
                assert blk["rows"][0]["legs"], f"{sid}: 다리 목록만 있고 행에 다리가 없다"
            assert r["principal"]["krw"] > 0, sid
            # 스왑의 항등(`명목 = 액면 x pv01 x 1e-4`)이 안 서는 자리라 비운다.
            assert r["principal"]["pv01"] is None, sid

    def test_an_unknown_series_is_a_404_not_an_empty_table(self, client):
        assert client.get("/api/mr/recon?id=NOPE&entry=2021-01-04"
                          "&exit=2021-02-01&dir=-1").status_code == 404

    def test_every_bss_trade_on_screen_can_be_reconciled(self, client):
        """**화면이 보여 주는 것은 전부 대사할 수 있다** [OWNER 2026-09-03 —
        "2020-01-02 이전의 데이터를 안 보이게 해서 차단"].

        MR 의 값 계열은 `imx_data.timeseries`(2014-05-28~)인데 실가격 대사는
        민평 행렬(`credit_matrix`, 2020-01-02~)로 채권을 다시 가격한다. 종전에는
        그 갈림 때문에 거래의 절반이 «표가 안 뜨는 거래» 였다(BSS-7Y 34건 중 18).

        표본을 민평의 첫 날로 자른 것이 그 답이다. 이 시험이 재는 것은 **자른
        결과가 실제로 그 성질을 만드나** — 한 건이라도 못 재면 화면이 다시
        「왜 안 뜨죠」를 받는다.
        """
        from app import creditmatrix

        first = creditmatrix.load().dates[0].isoformat()
        for sid in ("BSS-3Y", "BSS-7Y"):
            b = client.get(f"/api/mr/strategy?id={sid}").json()
            assert b["points"][0]["t"] >= first, f"{sid}: 표본이 민평보다 앞선다"
            bad = []
            for t in b["trades"]:
                r = client.get(f"/api/mr/recon?id={sid}&entry={t['entryT']}"
                               f"&exit={t['exitT']}&dir={t['dir']}").json()
                if not r.get("available"):
                    bad.append((t["entryT"], r.get("why", "")[:40]))
            assert not bad, f"{sid}: 대사 못 하는 거래 {len(bad)}건 — {bad[:2]}"
            assert len(b["trades"]) > 5, f"{sid}: 자르고 나니 거래가 너무 적다"

    def test_futures_keep_their_full_sample(self, client):
        """**선물 계열은 안 자른다.** 자산스왑이 아니라 민평 제약이 걸리지 않는
        자리다 — 거기까지 자르면 얻는 것 없이 표본만 천 봉 잃는다(실측 FSW-3Y
        2,614 → 1,636)."""
        from app import creditmatrix

        first = creditmatrix.load().dates[0].isoformat()
        for sid in ("FSW-3Y", "FUT-KTB3"):
            b = client.get(f"/api/mr/strategy?id={sid}").json()
            assert b["points"][0]["t"] < first, f"{sid}: 선물인데 잘렸다"

    def test_the_table_is_the_book(self, client):
        """**대사표가 곧 엔진의 장부다** [OWNER 2026-09-03 — "캐리 롤다운 다
        넣고 우리가 원래 사용하던 백테스트/시뮬레이션에서의 대사와 동일하게"].

        종전에는 둘이 다른 회계였다 — 엔진은 `평가 = 명목 × Δ스프레드` 하나라
        롤다운도 조달도 없었고, 실측에서 안 세는 롤다운이 세는 전부보다 컸다.
        이제 진입·청산 시점만 엔진이 정하고 그 구간의 돈은 이 표가 센다.

        **정확히 0 이어야 한다.** «거의 같다» 는 두 화면이 다른 수를 말한다는
        뜻이고, 그러면 트레이더가 어느 쪽을 믿을지 골라야 한다.
        """
        b = client.get("/api/mr/strategy?id=BSS-7Y").json()
        assert b["real"] is True, "BSS 인데 실가격 회계가 아니다"
        assert b["trades"], "거래가 없다"
        for t in b["trades"]:
            r = client.get(f"/api/mr/recon?id=BSS-7Y&entry={t['entryT']}"
                           f"&exit={t['exitT']}&dir={t['dir']}").json()
            assert r["available"], f"{t['entryT']}: 대사가 안 선다"
            tot = sum(x.get("actual") or 0 for x in r["rows"])
            assert abs((tot + t["cost"]) - t["pnl"]) < 0.01,                 f"{t['entryT']}: 표 세로합 + 비용 ≠ 거래 손익"

    def test_five_components_close_on_every_trade(self, client):
        """`평가 + 캐리 + 롤다운 + 조달 + 비용 = 손익` — 다섯이 닫힌다.

        백테스트·시뮬 대사의 네 성분에 전략의 비용 하나가 붙은 모양이다. 비용이
        표에 없는 이유는 그것이 상품의 성질이 아니라 노브이기 때문이다.
        """
        b = client.get("/api/mr/strategy?id=BSS-3Y").json()
        assert b["real"] is True
        for t in b["trades"]:
            five = (t["mtm"] + t["carry"] + t["rolldown"] + t["funding"] + t["cost"])
            assert abs(five - t["pnl"]) < 0.02, f"{t['entryT']}: 다섯이 안 닫힌다"
        # 봉 단위로도 닫힌다 — 대사표의 가로가 그것이다.
        for p in b["points"]:
            five = p["mtm"] + p["carry"] + p["rolldown"] + p["funding"] + p["cost"]
            assert abs(five - p["pnl"]) < 0.02, f"{p['t']}: 봉의 다섯이 안 닫힌다"

    def test_futures_are_real_too(self, client):
        """선물 계열도 **실가격 회계**다 [2026-09-04]. 종전에는 여기서
        `real is False` 를 지켰는데, 그 명제는 오너 결정으로 죽었다."""
        for sid in ("FUT-KTB3", "FUT-KTB10", "FSW-3Y", "FSW-10Y"):
            b = client.get(f"/api/mr/strategy?id={sid}").json()
            assert b["real"] is True, sid
            p = b["points"][len(b["points"]) // 2]
            # 다섯 성분이 봉에서 닫힌다 — BSS 와 같은 계약.
            assert abs((p["mtm"] + p["carry"] + p["rolldown"] + p["funding"]
                        + p["cost"]) - p["pnl"]) < 0.02, sid

    def test_the_locked_pms_vector_still_passes(self):
        """**엔진 함수는 안 건드렸다.** 회계는 라우트에서 얹으므로 `simulate`
        의 적합성 벡터가 그대로 통과해야 한다 — 이 시험이 그 사실의 기록이다."""
        from tests import test_mrbacktest as tb

        tb.test_kpi_conformance_vector_matches_pms()

    def test_the_notional_knob_means_the_same_thing_on_every_trade(self, client):
        """**「명목 N원/bp」가 모든 거래에서 같은 뜻이다** [검산 2026-09-03].

        자산스왑의 명목은 액면인데 노브는 DV01(₩/bp)이라 환산이 필요하다.
        종전에는 그 환산을 **지금 커브** pv01 하나로 6년 내내 했다 — `mrcarry` 가
        「[알려진 근사]」로 적으면서 «크기만 정하고 부호·시점은 안 건드린다» 고
        했고, 손익이 `명목 × Δ스프레드` 이던 시절에는 참이었다.

        **회계가 실가격으로 바뀌면서 그 문장이 거짓이 됐다.** 손익이 액면을
        가격해서 나오므로 환산 오차가 손익 전체를 스케일한다. 손으로 재 보니
        진입 시점 연금계수가 지금보다 최대 16%(10Y) 커서, 옛 거래가 노브가
        말하는 것보다 그만큼 큰 포지션이었고 총손익이 2~8% 부풀어 있었다.

        그래서 거래마다 진입일 커브로 잰다. 이 시험이 재는 것이 그 항등이다 —
        페이로드 안에서 **정확히** 닫혀야 손 대사가 선다.
        """
        for sid in ("BSS-3Y", "BSS-7Y", "BSS-10Y"):
            b = client.get(f"/api/mr/strategy?id={sid}").json()
            n = b["params"]["notional"]
            sizes = []
            for t in b["trades"]:
                r = client.get(f"/api/mr/recon?id={sid}&entry={t['entryT']}"
                               f"&exit={t['exitT']}&dir={t['dir']}").json()
                assert r["available"], f"{sid} {t['entryT']}: {r.get('why')}"
                p = r["principal"]
                assert abs(p["krw"] * p["pv01"] * 1e-4 - n) < 1.0,                     f"{sid} {t['entryT']}: 명목 ≠ 액면 × pv01 × 1e-4"
                sizes.append(p["krw"])
            # 커브가 움직인 만큼 액면도 움직여야 한다 — 다 같으면 옛 규약이다.
            assert max(sizes) / min(sizes) > 1.005, f"{sid}: 액면이 안 움직인다"

    def test_the_open_leg_is_priced_too(self, client):
        """**미청산 다리도 대사를 돈다** [전수 검산 2026-09-03].

        표본 끝에 열려 있는 다리는 `trades` 에 없다. 그런데 총손익과 낙폭은
        그것을 **실시간으로 지고 있다** — 누적이 보유 봉마다 MTM 을 더하기
        때문이다(`mrbacktest` 의 그 주석). 실가격 회계를 얹으면서 그 구간을
        빼먹었더니 **그 봉들이 통째로 0** 이 됐다(실측: BSS-9M 51봉 · 3Y 31봉 ·
        7Y 13봉). 곡선이 거짓말을 하고, `Σ거래 + 미청산 ≠ 총손익` 이 됐다.

        이 시험이 재는 것이 그 항등이다. 아홉 계열 전부를 본다 — 한 계열만
        보면 마침 그때 평평한 계열을 골라 초록을 볼 수 있다.
        """
        for sid in ("BSS-6M", "BSS-9M", "BSS-2Y", "BSS-3Y", "BSS-7Y", "BSS-10Y"):
            b = client.get(f"/api/mr/strategy?id={sid}").json()
            assert b["real"] is True, sid
            s_ = b["summary"]
            got = sum(t["pnl"] for t in b["trades"]) + (s_.get("openPnl") or 0.0)
            assert abs(got - s_["totalPnl"]) < 1.0,                 f"{sid}: Σ거래 + 미청산 ≠ 총손익 ({got:,.0f} vs {s_['totalPnl']:,.0f})"
            # 보유 중인데 손익이 0 인 봉 — 대사가 안 돈 구간의 지문이다.
            held = [p for p in b["points"] if p["hold"] != 0]
            zero = [p for p in held if p["pnl"] == 0]
            assert len(zero) <= max(5, len(held) // 50),                 f"{sid}: 보유 {len(held)}봉 중 {len(zero)}봉이 손익 0 — 대사가 안 돈 구간이 있다"

    def test_every_recon_row_lands_on_a_bar(self, client):
        """대사 행이 **하나도 안 버려진다**.

        대사는 민평 달력, 엔진은 계열 달력이라 어긋날 수 있다. 어긋난 날의 돈을
        버리면 거래의 세로합이 표와 갈리고, 마지막 봉에 몰아 얹으면 곡선이
        그날만 튄다. 실측은 **어긋난 날 0** 이지만, 데이터가 바뀌면 조용히
        생기는 종류라 여기서 지킨다.
        """
        for sid in ("BSS-3Y", "BSS-10Y"):
            b = client.get(f"/api/mr/strategy?id={sid}").json()
            bars = {p["t"] for p in b["points"]}
            for t in b["trades"]:
                r = client.get(f"/api/mr/recon?id={sid}&entry={t['entryT']}"
                               f"&exit={t['exitT']}&dir={t['dir']}").json()
                off = [x["t"] for x in r["rows"]
                       if x.get("actual") is not None and x["t"] not in bars]
                assert not off, f"{sid} {t['entryT']}: 봉에 없는 대사 날 {off[:3]}"

    def test_the_signal_curve_and_the_pricing_curve_are_the_same(self, client):
        """**신호가 본 국고와 대사가 가격하는 국고가 같은 커브다.**

        값 계열은 `imx_data.timeseries`, 대사는 `credit_matrix` 민평이다. 둘이
        갈리면 표는 **신호가 잡은 것과 다른 채권**을 가격하게 되고, 그건 대사가
        아니다. 겹치는 날 전부에서 잰다(단위가 다르다 — `yield_at` 은 소수,
        점의 다리 레벨은 %).
        """
        from app import creditmatrix

        m = creditmatrix.load()
        idx = {d.isoformat(): i for i, d in enumerate(m.dates)}
        for sid in ("BSS-3Y", "BSS-7Y", "BSS-10Y"):
            yrs = creditmatrix.TENOR_YEARS[sid.split("-", 1)[1]]
            b = client.get(f"/api/mr/strategy?id={sid}").json()
            worst = 0.0
            for p in b["points"]:
                i = idx.get(p["t"])
                if i is None or not p.get("legs"):
                    continue
                mp = creditmatrix.yield_at(m, "KTB", i, yrs)
                # ★다리를 **이름으로** 찾는다 — 차례는 규약이 정하고 규약은
                # 바뀐다(2026-09-22 에 `[국고, IRS]` → `[IRS, 국고]`). 첨자로
                # 집으면 그때 이 시험이 **IRS 를 국고라고 부르며** 18.5bp 를
                # 낸다(실제로 그랬다). 이름은 `mrcarry.LEG_NAMES` 가 정본이다.
                govt = next((lg for lg in p["legs"] if lg["k"] == "국고"), None)
                assert govt is not None, f'{sid} {p["t"]}: 국고 다리가 없어요'
                if mp is not None:
                    worst = max(worst, abs(govt["lvl"] - mp * 100.0) * 100.0)
            assert worst < 3.0, f"{sid}: 두 국고 커브가 {worst:.2f}bp 갈린다"


class TestTwoLegRecon:
    """대사표가 **국고 매수와 IRS 페이를 별개로** 세운다
    [OWNER 2026-09-04 — 「국고매수랑 IRS Pay가 별개로 뜨게 해줘」].

    종전 표는 자가 섞여 있었다: KRD 는 `_krd_bond` 라 **국고 다리 것만**인데
    Δbp 는 `asw_series` 라 **«민평 − IRS» 스프레드**였다. par-par 자산스왑의
    1차 근사로는 성립하지만 한 다리의 감도에 두 다리의 Δ 를 곱한 자였고, 그
    몫이 전부 잔차로 갔다.

    여기서 재는 것은 셋이다: 다리가 **닫히는가**(합·성분·곱셈), 다리가 **자기
    커브 위에 서는가**, 그리고 그래서 **잔차가 실제로 줄었는가**.
    """

    #: 오너가 화면에서 짚은 그 거래 — 9봉, 국고 매수·IRS 페이, 청산.
    #: ★`dir` 이 `-1` → `+1` 로 옮겨 앉았다(2026-09-22 규약 뒤집기). **거래는
    #: 같은 거래다** — 값이 `IRS − 국고` 가 되면서 「국고 매수·IRS 페이」를
    #: 가리키는 부호가 바뀌었을 뿐이고, 안 바꾸면 이 표가 **국고 매도**를 세운다
    #: (조달 부호와 KRD 부호가 통째로 뒤집혀 아래 두 시험이 먼저 깨진다).
    TRADE = "id=BSS-7Y&entry=2020-03-27&exit=2020-04-09&dir=1&notional=1000000"

    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as c:
            yield c

    @pytest.fixture(scope="class")
    def rec(self, client):
        r = client.get(f"/api/mr/recon?{self.TRADE}").json()
        assert r.get("available"), r.get("why")
        return r

    def test_every_row_carries_both_legs(self, rec):
        """행마다 다리 둘. 하나라도 비면 그날 화면이 한 다리만 말한다."""
        assert rec.get("legTenors"), "다리별 열 목록이 없다"
        assert [g["name"] for g in rec["legTenors"]] == ["국고", "IRS"]
        for r in rec["rows"]:
            legs = r.get("legs")
            assert legs and [lg["name"] for lg in legs] == ["국고", "IRS"], r["t"]

    def test_the_two_legs_add_up_to_the_day(self, rec):
        """국고 + IRS = 그날 손익, **원 단위로 0**.

        반올림을 각자 하면 여기가 갈린다 — 그래서 총계 행이 정본이고 국고
        다리가 잔차를 진다(`main._mr_scale_rows`). 이 시험이 그 규율의 핀이다.
        """
        for r in rec["rows"]:
            if r.get("actual") is None:
                continue
            b, s = r["legs"]
            assert b["actual"] + s["actual"] == r["actual"], r["t"]

    def test_each_leg_closes_its_own_components(self, rec):
        """다리마다 `평가 + 캐리 + 롤다운 + 조달 = 그날 손익`, 0원.

        그리고 다리별 캐리·롤다운의 합이 하루의 것과 같다 — 안 그러면 표가
        세로로는 닫히는데 가로로는 안 닫힌다.
        """
        for r in rec["rows"]:
            if r.get("actual") is None:
                continue
            b, s = r["legs"]
            for lg in (b, s):
                parts = (lg["valuation"] + (lg["carry"] or 0)
                         + (lg["rolldown"] or 0) + (lg["funding"] or 0))
                assert parts == lg["actual"], f"{r['t']} {lg['name']}"
            assert (b["carry"] or 0) + (s["carry"] or 0) == (r["carry"] or 0), r["t"]
            assert (b["rolldown"] or 0) + (s["rolldown"] or 0) == (r["rolldown"] or 0), r["t"]

    def test_only_the_bond_leg_is_funded(self, rec):
        """조달은 **국고 다리만** 진다 — 현물을 조달해 들고 있는 비용이다.

        IRS 다리는 `None` 이다. 0 으로 채우면 「그날 조달이 0 이었다」는 다른
        말이 되고, 화면이 그 다리에도 조달 칸을 세운다(공란 정책).
        """
        funded = 0
        for r in rec["rows"]:
            if r.get("actual") is None:
                continue
            b, s = r["legs"]
            assert s["funding"] is None, f"{r['t']}: IRS 다리에 조달이 섰다"
            if b["funding"]:
                funded += 1
        assert funded > 0, "국고 다리에 조달이 한 번도 안 섰다"

    def test_each_leg_closes_its_own_multiplication(self, rec):
        """다리마다 `추정 = −KRD × Δbp`, 칸마다.

        이 곱셈이 다리 안에서 닫혀야 «감도와 Δ 가 같은 커브 위에 있다» 가
        참이다. 종전 표에서 안 닫히던 것이 이 변경의 이유다.
        """
        checked = 0
        for r in rec["rows"]:
            for lg in r.get("legs") or []:
                krd, dbp, est = lg["krd"], lg["dbp"] or {}, lg["est"] or {}
                for lb, k in krd.items():
                    d = dbp.get(lb)
                    if d is None:
                        continue
                    assert est.get(lb, 0) == round(-k * d), f"{r['t']} {lg['name']} {lb}"
                    checked += 1
                if lg["estTotal"] is not None:
                    assert sum(est.values()) == lg["estTotal"], f"{r['t']} {lg['name']}"
        assert checked > 100, f"곱셈을 잰 칸이 {checked}개뿐이다"

    def test_the_legs_stand_on_their_own_curves(self, rec):
        """국고는 민평 노드, IRS 는 IRS 노드 — **다른 집합**이다.

        민평엔 2.5Y 가 있고 IRS 엔 4Y·6Y 가 있다. 두 열이 같으면 그건 아직
        한 커브로 재고 있다는 뜻이다.
        """
        bond, swap = rec["legTenors"]
        assert "2.5Y" in bond["tenors"], "민평 전용 노드가 국고 다리에 없다"
        assert {"4Y", "6Y"} <= set(swap["tenors"]), "IRS 전용 노드가 IRS 다리에 없다"
        assert set(bond["tenors"]) != set(swap["tenors"])

    def test_paying_fixed_is_short_where_the_bond_is_long(self, rec):
        """**부호가 반대다.** 국고 매수는 잔존 언저리에서 KRD 양수, IRS 페이는
        같은 자리에서 음수다(앱 규약: 손익 = −KRD × Δbp).

        둘이 같은 부호로 서면 자산스왑을 두 번 산 것이고, 그건 이 표가 말할 수
        있는 가장 큰 거짓말이다.
        """
        mid = [r for r in rec["rows"] if r.get("actual") is not None][len(rec["rows"]) // 2]
        b, s = mid["legs"]
        assert b["krd"].get("7Y", 0) > 0, f"{mid['t']}: 국고 7Y 가 양수가 아니다"
        assert s["krd"].get("7Y", 0) < 0, f"{mid['t']}: IRS 7Y 가 음수가 아니다"

    def test_the_leg_ruler_beats_the_spread_ruler(self, rec):
        """**잔차가 줄어야 한다** — 이 변경의 값어치가 그것이다.

        종전 잔차는 `평가 − (국고 KRD × Δ스프레드)` 였고, 새 잔차는 두 다리가
        자기 커브에서 낸 추정의 합을 뺀 것이다. 후자가 크면 자를 잘못 바꾼
        것이다(실측 2026-09-04: 199만 → 6.4만원, 96.8% 감소).
        """
        old = new = 0.0
        for r in rec["rows"]:
            if r.get("residual") is None:
                continue
            b, s = r["legs"]
            old += abs(r["residual"])
            new += abs(b["residual"] + s["residual"])
        assert old > 0, "옛 잔차가 전부 0 이라 비교가 안 된다"
        assert new < old * 0.5, f"잔차가 안 줄었다 — 옛 {old:,.0f} 새 {new:,.0f}"


@pytestmark_live
class TestFuturesRealRecon:
    """선물 넷이 **실가격 대사**로 돈다 [OWNER 2026-09-04 — "0.5틱으로 해두자"].

    인계문의 임무였다. 배선은 셋이었고 셋 다 실측으로 정했다: 액면은 진입일
    벤더 내재금리로 환산하고(`futures.face_for_dv01`), 방향은 FUT −dir · FSW +dir
    이며, FSW 의 IRS 다리는 **스왑 표에** 선다(엔진 단위 분리).

    그리고 결정이 하나 붙었다 — **롤 비용**. 연결 계열은 데이터 구조물이지
    상품이 아니라서, 분기마다 실제로 갈아타는 왕복(0.5틱 편도 x 2 = 1틱)을
    문다. 종전에는 그 자리가 0 이었고 롤일 Δ 마스크가 그 사실을 가리고 있었다.

    ⚠ **IRS 다리의 자리가 2026-09-07 에 바뀌었다** [OWNER]. 화면에서는 선물 표
    **안**에 들어와 하루가 일곱 줄이 되고(`with_legs`), 회계는 종전대로 두 블록을
    받는다(다리 표는 IRS 파 커브를 범프해야 서는데 회계는 거래마다 돈다). 두
    길의 **돈이 같다**는 것을 `test_the_two_paths_are_the_same_money` 가 잰다.
    """

    KN = "notional=1000000&costBp=0.5"

    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as c:
            yield c

    def _recon(self, client, sid, t):
        return client.get(
            f"/api/mr/recon?id={sid}&entry={t['entryT']}&exit={t['exitT']}"
            f"&dir={t['dir']}&notional=1000000"
        ).json()

    @pytest.mark.parametrize("sid", ["FUT-KTB3", "FUT-KTB10", "FSW-3Y", "FSW-10Y"])
    def test_every_trade_on_screen_can_be_reconciled(self, sid, client):
        """**화면이 보여 주는 것은 전부 대사할 수 있다.** 한 건이라도 못 재면
        회계가 통째로 옛 근사로 떨어진다(「한 건이라도 못 재면 전부 안 바꾼다」)
        — 그 자리를 실제로 밟았다: 벤더 두 표에 2019-02-15 가 없어서 FSW-10Y
        67거래가 통째로 떨어져 있었다."""
        b = client.get(f"/api/mr/strategy?id={sid}&{self.KN}").json()
        assert b["real"] is True, sid
        bad = [t["entryT"] for t in b["trades"]
               if not self._recon(client, sid, t).get("available")]
        assert not bad, f"{sid}: 대사 못 세운 거래 {len(bad)}건 (첫 {bad[:3]})"

    @pytest.mark.parametrize("sid", ["FUT-KTB3", "FSW-3Y", "FSW-10Y"])
    def test_the_blocks_are_the_book(self, sid, client):
        """**표의 세로합 + 비용 = 거래 손익.** BSS 와 같은 계약이다.

        FSW 는 두 달력이 어긋나는데도 합이 닫힌다 — IRS 다리가 선물 행마다
        «지난 행 이후» 의 밤으로 담기고(버킷), 마지막 행이 남은 밤을 지기
        때문이다. 화면이 한 표든(`with_legs`) 회계가 두 블록이든 **같은 수**라야
        한다는 것이 이 시험의 다른 쪽이다.
        """
        b = client.get(f"/api/mr/strategy?id={sid}&{self.KN}").json()
        checked = 0
        for t in b["trades"][:8]:
            r = self._recon(client, sid, t)
            assert r["available"], (sid, t["entryT"], r.get("why"))
            tot = sum(row["actual"] for blk in r["blocks"] for row in blk["rows"]
                      if row.get("actual") is not None)
            assert abs(tot + t["cost"] - t["pnl"]) <= 2.0, \
                f"{sid} {t['entryT']}: 세로합 {tot:,.0f} + 비용 {t['cost']:,.0f} ≠ 손익 {t['pnl']:,.0f}"
            checked += 1
        assert checked >= 5, f"{sid}: 잰 거래가 {checked}건뿐이다"

    @pytest.mark.parametrize("sid", ["FSW-3Y", "FSW-10Y"])
    def test_the_two_paths_are_the_same_money(self, sid, client):
        """**한 표(화면)와 두 블록(회계)이 같은 돈이다** [OWNER 2026-09-07].

        모양이 갈리는 것은 값이 갈려도 된다는 뜻이 아니다. 화면은 IRS 다리를
        선물 표 안에 버킷으로 담고, 회계는 두 블록의 행을 한 줄기로 펴서 날짜로
        얹는다 — **더하는 순서만 다르고 더하는 것은 같은 밤들**이다.

        이 시험이 없으면 어느 한쪽만 고쳤을 때 화면과 헤드라인이 조용히 갈린다.
        성분마다 잰다(합만 재면 두 오차가 상쇄되는 자리를 놓친다).
        """
        from app import main as m

        b = client.get(f"/api/mr/strategy?id={sid}&{self.KN}").json()
        checked = 0
        for t in b["trades"][:5]:
            e_d = dt.date.fromisoformat(t["entryT"])
            x_d = dt.date.fromisoformat(t["exitT"])
            one = m._mr_fut_recon(sid, int(t["dir"]), 1_000_000.0, e_d, x_d,
                                  with_krd=True, with_legs=True)
            two = m._mr_fut_recon(sid, int(t["dir"]), 1_000_000.0, e_d, x_d,
                                  with_krd=False)
            assert one is not None and two is not None, t["entryT"]
            assert len(one["blocks"]) == 1 and len(two["blocks"]) == 2, t["entryT"]
            for key in ("actual", "valuation", "carry", "rolldown"):
                a = sum(r.get(key) or 0.0
                        for r in one["blocks"][0]["recon"]["rows"])
                c = sum(r.get(key) or 0.0 for blk in two["blocks"]
                        for r in blk["recon"]["rows"])
                assert abs(a - c) <= 2.0, \
                    f"{sid} {t['entryT']} {key}: 한 표 {a:,.0f} ≠ 두 블록 {c:,.0f}"
            assert one["face"] == two["face"], t["entryT"]
            assert one["rolls"] == two["rolls"], t["entryT"]
            checked += 1
        assert checked >= 3, f"{sid}: 잰 거래가 {checked}건뿐이다"

    def test_the_futures_leg_has_no_carry_or_funding(self, client):
        """선물 다리는 캐리·롤다운·조달이 **존재하지 않는 성분**이다 — 현금결제·
        연결 계열이라 조달할 원금도 늙을 잔존도 없다. `None` 이지 0 이 아니다.

        ⚠ 재는 자리가 **행이 아니라 다리**다 [2026-09-07]. FSW 가 한 표가 되면서
        행의 `carry` 는 두 다리의 **합**(= IRS 것)이 됐다. 종전처럼 행을 재면
        「선물 다리에 캐리가 있다」는 거짓을 잡게 된다 — 표가 합계 줄을 지는 것과
        다리가 그 성분을 지는 것은 다른 명제다.
        """
        b = client.get(f"/api/mr/strategy?id=FSW-3Y&{self.KN}").json()
        r = self._recon(client, "FSW-3Y", b["trades"][0])
        blk = r["blocks"][0]
        live = [row for row in blk["rows"] if row.get("actual") is not None]
        assert live
        for row in live:
            fut_leg, irs_leg = row["legs"]
            assert fut_leg["name"] == "선물" and irs_leg["name"] == "IRS", row["t"]
            assert fut_leg["carry"] is None and fut_leg["rolldown"] is None, row["t"]
            assert fut_leg["funding"] is None, row["t"]
            assert fut_leg["actual"] == fut_leg["valuation"], row["t"]
        # IRS 다리는 반대로 캐리를 진다(CD 91일 − 스왑 고정), 그리고 **행의
        # 캐리는 그 다리에서 온다** — 합계 줄이 다리의 합이라는 계약.
        assert any(row["legs"][1].get("carry") for row in live), "IRS 다리에 캐리가 없다"
        for row in live:
            assert row["carry"] == row["legs"][1]["carry"], row["t"]

    def test_the_roll_is_paid_for(self, client):
        """**갈아타기를 문다** [OWNER 2026-09-04]. 비용 = 진입·청산 편도 둘 +
        보유 중 롤일마다 왕복 1틱.

        종전에는 두 번째 항이 0 이었다 — 분기마다 실제로 구계약을 팔고 신계약을
        사는데 그 왕복이 모형에 없었다. 연결선물이라서 안 무는 게 아니라
        **연결선물이라서 무는** 자리다: 조정가가 빼는 것은 계약 사이의 가격
        단차이지 갈아타기의 마찰이 아니다.
        """
        b = client.get(f"/api/mr/strategy?id=FUT-KTB3&{self.KN}").json()
        one_way = 1_000_000.0 * 0.5                    # 명목 x 편도 bp
        rolled = 0
        for t in b["trades"]:
            r = self._recon(client, "FUT-KTB3", t)
            assert r["available"], t["entryT"]
            want = -(2 * one_way) - r["roll"]["days"] * r["roll"]["won"]
            assert abs(t["cost"] - want) <= 2.0, \
                f"{t['entryT']}: 비용 {t['cost']:,.0f} ≠ {want:,.0f} (롤 {r['roll']['days']}회)"
            rolled += r["roll"]["days"]
        assert rolled > 0, "보유 중 롤일이 한 번도 없다 — 표본이 바뀌었다"

    def test_longing_the_spread_is_long_the_futures(self, client):
        """**부호가 경제와 맞나** — 조용히 뒤집히는 종류다.

        규약은 `손익 = −KRD × Δbp` 이고, 양수 KRD = 금리 오르면 잃는 쪽이다.
        FSW 는 ★2026-09-22 규약 뒤집기 뒤로 `+1 = 호가값(IRS − 내재) 롱 =
        IRS 페이 + 선물 **매수**` 이므로, 그 방향에서 선물 다리의 KRD 는
        **양수**(내재금리가 오르면 잃는다)여야 한다. 종전에는 정확히 반대였고,
        그 뒤집힘이 계열·다리·라벨 셋을 같이 돌렸다는 증거다.
        MR 엔진의 `direction` 을 그대로 넘긴다는 사상이 여기서 확인된다.
        """
        b = client.get(f"/api/mr/strategy?id=FSW-3Y&{self.KN}").json()
        longs = [t for t in b["trades"] if t["dir"] > 0]
        assert longs, "스프레드 롱 거래가 없다"
        r = self._recon(client, "FSW-3Y", longs[0])
        fut_blk = next(x for x in r["blocks"] if x["name"] == "선물")
        mid = [row for row in fut_blk["rows"] if row.get("actual") is not None][1]
        krd = [v for v in mid["krd"].values() if abs(v) > 1.0]
        assert krd and all(v > 0 for v in krd), \
            f"{mid['t']}: 스프레드 롱인데 선물 KRD 가 양수가 아니다 — {mid['krd']}"

    def test_a_missing_vendor_day_blanks_one_cell_not_the_table(self, client):
        """벤더 값이 없는 날은 **칸 하나가 비고 표는 산다.**

        실측: 2019-02-15 는 벤더 두 표에 없다(레인 문서의 「백필 대상」). 종전에는
        `implied_at_index` 가 그 자리에서 죽어 **FSW-10Y 67거래가 통째로** 옛
        근사로 떨어졌다. PVBP 의 수준은 직전 값으로 잇고(수준의 완만한 함수),
        **Δbp 는 안 잇는다** — 변화를 지어내면 없는 사실을 말하는 것이다.
        """
        r = client.get("/api/mr/recon?id=FSW-10Y&entry=2019-01-04"
                       "&exit=2019-03-12&dir=-1&notional=1000000").json()
        assert r["available"] is True, r.get("why")
        fut_blk = next(x for x in r["blocks"] if x["name"] == "선물")
        gap = [row for row in fut_blk["rows"] if row["t"] == "2019-02-15"]
        assert gap, "그날 행이 아예 없다 — 표본이 바뀌었다"
        row = gap[0]
        assert all(v is None for v in row["dbp"].values()), "Δbp 를 지어냈다"
        assert row["actual"] is not None and row["actual"] != 0, \
            "돈까지 지웠다 — 조정가는 그날에도 있다"
