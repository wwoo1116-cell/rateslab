"""
Integration tests for POST /api/simulate (the port of rates-simulator-main's
scenario simulator into irs_pricer).

Two layers of numerical evidence:

1. `test_matches_source_backend_golden` -- full-response parity against the
   REAL source implementation. tests/data/simulate_golden_source_response.json
   was captured on 2026-07-15 by running rates-simulator-main/backend/main.py
   (its own venv: numpy 2.4.6, scipy 1.17.1, holidays 0.100) on :8200 and
   POSTing tests/data/simulate_request_representative.json -- a request built
   exactly the way the frontend's buildSimulateRequest() builds one
   (scenario-curves.ts transcribed: generateShockCurves node-for-node), with
   3 bonds across the short/blend/long zones, a receive-fixed and a pay-fixed
   IRS with real schedule dates, one BOK cut, ramp+matrix mode, and a
   30-day-waypoint custom path over a 90-day horizon. At capture time the
   ported route reproduced the golden with ZERO diffs at rel_tol=1e-9
   (every rounded int exact, floats to the last bit).

2. `test_bond_only_analytic` -- hand-derived closed-form numbers for a
   single-bond parallel/step scenario, independent of any golden file:
   day-t bond MTM = pvbp * (remaining-t)/remaining * (-shock_bp), and daily
   carry = eval * (mtmYield - funding*100)/100 / 365 — 쿠폰(마크) 고정
   [OWNER, 2026-08-25 — "충격 미가산" · 감사록 F1]. 종전에는 mtmYield 에
   시나리오 충격을 가산했는데 그건 보유 고정이표가 금리 상승에서 더 버는
   팬텀 캐리였다.

Contract note: the response shape is the frozen frontend contract
(UIUX_test src/features/simulation/api/simulate-dto.ts). Key names are
camelCase by design.
"""

from __future__ import annotations

import inspect
import json
import math
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app  # the simulation rides on braveworld's app now (:8100)

DATA = Path(__file__).parent / "data"

REPRESENTATIVE_REQUEST = json.loads(
    (DATA / "simulate_request_representative.json").read_text(encoding="utf-8")
)
# [CHANGED, DV01-B] The golden is now the CURRENT backend's captured response
# (simulate_golden_dv01_response.json). Byte-parity with the SOURCE capture
# (simulate_golden_source_response.json, kept in-repo as the historical
# record) held until DV01-FIX Phase B intentionally departed on the bond MtM
# path: bond pvbp is re-derived server-side (services/bond_risk bump-reval)
# instead of trusting the wire's frozen-blotter figure. Representative-fixture
# delta at the departure: finalMTM −254,095,011 → −255,182,266 (+0.43% —
# the fixture's wire pvbp was internally consistent, so the re-derivation
# moves it only by the schedule/yield-base refinement; real stale blotters
# correct by ×0.678 aggregate, see DV01_FIX_REPORT.md); finalCarry/finalSwap
# byte-identical (swaps and carry never touch this data).
# [RE-PINNED 2026-08-10] 일별 recon 추정이 전일(start-of-day) KRD × 당일
# Δbp 로 바뀌며(chart.py `_pvbp_prev_r` 시드 주석 — P&L explain 민감도
# 방식의 교과서 관행) irsDailyReconciliation 의 `pnl`/`totalEstPnl`/
# `residual` 만 달라졌다. `pvbp`(그날의 KRD 수준값)·totalActual·theta/
# valuation 및 그 밖의 모든 키는 이전 골든과 동일하다. 이번 캡처부터
# swapContributions 가 골든 안에 포함된다(아래 extras 단언 주석).
# [RE-PINNED 2026-08-11] 교과서 3분해 — 세타(구 swapCarry)가 캐리/롤다운으로
# 갈렸다(carry_split.py). 재캡처 전 blast-radius 스크립트로 단언한 변경 범위:
# chartData 행 +swapCashCarryPnL/+swapRolldownPnL, decompositionDaily·
# totalReturnDecomposition 의 swapCarry 값 변경 +swapRolldown 추가,
# irsDailyReconciliation 행 +carryPnl/+rolldownPnl — 그 밖의 모든 키·값
# (swapMtm·total·bond·funding·pvbp·totalActual 포함)은 바이트 동일, 그리고
# 새 swapCarry+swapRolldown == 구 swapCarry(세타)가 float 그대로 성립.
# [RE-PINNED 2026-08-11 #2] recon 행의 `pvbp` 가 추정에 쓴 전일(start-of-day)
# KRD 그 자체가 됐고(한 블록 안에서 pvbp × dailyDbp = pnl 이 닫힌다 —
# recon.py 모듈 주석) rows 끝에 이월 앵커(carryover=True, 종가 KRD 만,
# 손익 필드 전부 null)가 붙었다. blast-radius 로 단언한 범위: 61개 행의
# pvbp 가 정확히 한 칸 시프트(행 0 시드는 동일)·전 행 +carryover=False·
# 앵커 1행 추가 — pvbp/carryover 밖의 모든 키·값과 recon 밖 전체는 바이트
# 동일.
# [2026-08-21] 대사표가 **채권 줄까지** 세면서 다시 떴다. 종전에는 스왑만 세서
# 혼합 북에서 표의 합이 헤드라인과 조용히 어긋났다 — 이 대표 요청에서만 표 합
# +26,167,884 대 헤드라인 −192,093,885 로 **2억 1,826만원**(정확히 finalSwap
# 만큼: 표가 스왑만 세고 있었다는 증거)이었고, 지금은 −192,093,893 로 8원 차다
# (61행 × 라운딩). 재핀의 폭발 반경을 실측으로 좁혀 두었다:
#
#   대사 **밖의 모든 키** — 바이트 동일 (헤드라인·chartData·decomposition 불변)
#   대사 **안**          — 움직인 필드는 carryPnl · totalActual · valuationPnl 셋뿐
#                          (채권 몫이 더해진 자리). pvbp/pnl/dailyDbp/cumulativeBp/
#                          thetaPnl/rolldownPnl/settleCf/npvChange/residual/
#                          totalEstPnl 은 전부 불변. 행 수도 62 그대로.
#   새 키                — `funding` 하나 (채권 줄이 있을 때만 숫자)
#
# 골든 파일도 `irsDailyReconciliation` **한 키만** 갈아 끼웠다 — 나머지가 표류할
# 자리를 만들지 않는다.
# [RE-PINNED 2026-10-16 — 전수조사 셋째 판] 스왑 표의 **세타 귀속이 한 행 당겨졌다**
# (`recon.py::_fwd_theta`). 궤적이 결제일(T+1) 색인이라 종전 차분은 «다음 행의 밤»
# 이었고, 그래서 주말 사흘치가 금요일이 아니라 **목요일** 행에 섰다(이 대표 요청
# 실측: 목 43,345 대 나머지 ~11,000 — 같은 응답의 채권 표는 금 695,304 로 제대로
# 섰다). [OWNER 2026-08-11] 「결제일 기준이 아니라 평가일 기준 … 금요일에 튀어야」
# 와 백테스트 recon 이 둘 다 금요일이므로 시뮬의 스왑 표만 어긋나 있었다.
# blast-radius 를 기계로 센 변경 범위(= 골든 diff 와 정확히 같은 211 자리):
#
#   움직인 필드 — `irsDailyReconciliation` 의 thetaPnl(61) · totalActual(61) ·
#                 rolldownPnl(61) · carryPnl(28). **그 밖의 모든 키는 딥-동일**
#                 (headline·chartData·decomposition·채권/선물 표·pvbp 포함 —
#                 갈아 끼우기 전에 그 사실을 단언하고 바꿨다).
#   불변       — 네 열의 **세로합**: theta 1,131,257 · carry 1,957,744 ·
#                 rolldown −826,487 · totalActual 26,167,884. 이동이라 망원경
#                 합이 그대로다. 그래서 `finalSwap` 핀도 바이트 동일이다.
#   날짜 끝    — D+0 행의 세타가 **0** 이 됐다(거래일→발효일 한 밤은 스왑이 시작
#                 전이라 쌓이는 것이 없다 — 백테스트의 `startup` 과 같은 자리),
#                 마지막 행이 자기 밤(4,607)을 지게 됐다(종전 0).
GOLDEN_RESPONSE = json.loads(
    (DATA / "simulate_golden_dv01_response.json").read_text(encoding="utf-8")
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def representative_response(client: TestClient) -> dict:
    """One shared run of the representative request -- the endpoint is seconds
    of engine work (per-business-day KRD curve rebuilds), so shape and parity
    tests share a single response."""
    r = client.post("/api/simulate", json=REPRESENTATIVE_REQUEST)
    assert r.status_code == 200, r.text
    return r.json()


# ── 1. Contract shape ────────────────────────────────────────────────────────

def test_response_matches_frontend_contract_shape(representative_response: dict) -> None:
    body = representative_response

    # SimulateResponse keys (simulate-dto.ts) -- status is a source extra.
    # fundingCurve/distribution are the s11 additive extensions (T3/T4),
    # exclusions/totalReturnDecomposition the s15 ones (T2), and
    # decompositionDaily the HARDEN-1 one: the source contract may only ever
    # GROW by explicitly-listed keys, never change.
    assert set(body.keys()) == {
        "status", "chartData", "summary", "pvbpSensitivity",
        "bookDailyPnLs", "irsSettlementEvents", "irsDailyReconciliation",
        "bondDailyReconciliation",
        # [OWNER, 2026-08-25] 국채선물 일별 대사 — 세 번째 자기 표.
        "futuresDailyReconciliation",
        "fundingCurve", "distribution", "exclusions", "totalReturnDecomposition",
        "decompositionDaily", "fundingBasis",
        # 2026-08-06: 포지션별 기여. 목록에 이름을 올리는 것이 이 계약이 자라는
        # 유일한 방법이고, 올리는 순간 아래에서 모양까지 못박는다 — 키만 늘리고
        # 내용을 안 보면 "있기는 한데 무엇인지 모르는" 필드가 생긴다.
        "swapContributions",
    }
    assert body["status"] == "ok"

    # swapContributions: 스왑 한 건당 한 행, 만기 시점 기여.
    contribs = body["swapContributions"]
    assert isinstance(contribs, list) and contribs, "대표 픽스처는 스왑을 포함한다"
    assert all(
        set(row) == {
            "positionId", "positionName", "book", "notional", "direction",
            "fixedRate", "maturityDate", "mtm", "carry", "total",
        }
        for row in contribs
    )
    # total은 두 성분의 합이다 — 별도로 계산된 세 번째 숫자가 아니다.
    assert all(
        math.isclose(r["total"], r["mtm"] + r["carry"], rel_tol=0, abs_tol=1e-6)
        for r in contribs
    )
    # 그리고 행들의 합은 응답의 스왑 성분 합과 같아야 한다 — 이 표가 전체를
    # 설명한다는 주장이 성립하는지 확인한다. (엔진 세타/평가 재분해와 반올림
    # 차이가 있을 수 있어 ±₩1로 본다.) [2026-08-11 3분해] 스왑 성분은 셋이다
    # — swapRolldown 을 빼먹으면 캐리/롤다운 분리분만큼 어긋난다.
    decomp = body["totalReturnDecomposition"]
    swap_total = (
        (decomp["swapMtm"] or 0.0)
        + (decomp["swapCarry"] or 0.0)
        + (decomp["swapRolldown"] or 0.0)
    )
    assert math.isclose(sum(r["total"] for r in contribs), swap_total, rel_tol=0, abs_tol=1.0)

    # chartData: day 0 anchor + one row per Korean business day in the horizon.
    chart = body["chartData"]
    assert chart[0]["day"] == 0
    assert all(
        set(row) >= {"day", "mtmPnL", "cumulativeCarry", "swapPnL", "totalPnL",
                     "swapThetaPnL", "swapValuationPnL"}
        for row in chart
    )
    assert [row["day"] for row in chart] == sorted(row["day"] for row in chart)

    # SimulationSummary keys, exactly. [2026-08-25] finalFut — 선물 합류.
    assert set(body["summary"]) == {
        "finalMTM", "finalCarry", "finalSwap", "finalFut", "finalTotal",
        "breakEvenDay",
    }

    # pvbpSensitivity: all 10 sectors plus the 합계 row, each with tenors +
    # total. [2026-08-25] 국채선물 — 목록에 없으면 선물 krdMap 이 통째로
    # 떨어진다(aggregates.py 의 30Y 실측과 같은 병).
    sectors = [row["sector"] for row in body["pvbpSensitivity"]]
    assert sectors == ["국고채", "통안채", "특은채", "시은채", "공사채",
                       "여전채", "회사채", "국채선물", "IRS", "OIS", "합계"]
    for row in body["pvbpSensitivity"]:
        assert "합계" in row["tenors"]
        assert math.isclose(row["total"], row["tenors"]["합계"], rel_tol=1e-12)

    # bookDailyPnLs: one row per book plus Total, BookDailyPnL keys.
    books = [row["bookName"] for row in body["bookDailyPnLs"]]
    assert books == ["RP Fund", "Trading", "Total"]
    assert set(body["bookDailyPnLs"][0]) == {
        "bookName", "dailyCarry", "fundingCost", "bondValuation",
        "futuresValuation", "swapValuation", "swapThetaPnL", "totalDailyPnL",
    }


def test_route_streams_and_offloads_the_engine() -> None:
    """simulate now STREAMS (Cloudflare tunnel ~100s 524 fix): the endpoint is
    an `async def` returning a StreamingResponse that flushes keepalive bytes
    while the run computes. Two properties still matter and are asserted here:

    1. It carries no declarative response_model (StreamingResponse can't be
       validated against one) — payload typing is instead preserved by
       serializing through SimulateResponse inside the handler, and the response
       *shape* is pinned by test_response_shape / the golden parity tests.
    2. The CPU-bound engine work must NOT run on the event loop. We can't prove
       run_in_executor structurally, but we guard the specific regression that
       would reintroduce blocking: the source module must reference
       `run_in_executor` (offload the run) rather than awaiting/calling
       run_simulation directly in the coroutine."""
    import inspect as _inspect

    from irs_pricer.api.routers import simulate as simulate_mod

    route = next(
        r for r in _walk(app.routes)
        if isinstance(r, APIRoute) and r.path == "/api/simulate"
    )
    assert route.response_model is None
    assert inspect.iscoroutinefunction(route.endpoint)
    assert "run_in_executor" in _inspect.getsource(simulate_mod.simulate), (
        "the engine run must be offloaded to a worker thread, never awaited "
        "directly in the streaming coroutine (that would block the event loop)."
    )


def _walk(routes):
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _walk(inner.routes)


# ── 2. Golden parity vs the source implementation ────────────────────────────

def _assert_deep_close(mine, golden, path=""):
    if isinstance(golden, dict):
        assert isinstance(mine, dict) and set(mine) == set(golden), \
            f"{path}: keys {sorted(mine)} != {sorted(golden)}"
        for k in golden:
            _assert_deep_close(mine[k], golden[k], f"{path}.{k}")
    elif isinstance(golden, list):
        assert isinstance(mine, list) and len(mine) == len(golden), \
            f"{path}: len {len(mine)} != {len(golden)}"
        for i, (m, g) in enumerate(zip(mine, golden)):
            _assert_deep_close(m, g, f"{path}[{i}]")
    elif isinstance(golden, (int, float)) and not isinstance(golden, bool):
        # rel 1e-9 tolerates float serialisation noise while still requiring
        # every rounded-int field to agree exactly (their diffs are >= 1).
        assert math.isclose(mine, golden, rel_tol=1e-9, abs_tol=1e-6), \
            f"{path}: {mine} != {golden}"
    else:
        assert mine == golden, f"{path}: {mine!r} != {golden!r}"


def test_matches_source_backend_golden(representative_response: dict) -> None:
    # The golden file is the SOURCE backend's response. s11 extended the route
    # additively (fundingCurve/distribution), s15 again (exclusions/
    # totalReturnDecomposition), HARDEN-1 again (decompositionDaily) -- parity
    # is asserted over every key the source emitted, at full depth, and the
    # extras must be EXACTLY the known extensions (an unlisted key is a
    # contract change, not an extension, and must fail here).
    # [CHANGED, DV01-B] the golden is now a full current-contract capture, so
    # there are no extension keys beyond it. The historical additive-extension
    # provenance (fundingCurve → … → fundingBasis over the SOURCE golden) is
    # recorded at the GOLDEN_RESPONSE loader comment; an unlisted NEW key must
    # still fail here.
    #
    # [2026-08-10] 골든을 다시 떴다 — 일별 recon 추정이 전일(start-of-day)
    # KRD 기준으로 바뀌면서(교과서 P&L-explain 관행, chart.py 시드 주석)
    # `pnl`/`totalEstPnl`/`residual` 이 의도적으로 달라졌다. DV01-B 와 같은
    # 재핀이고, 같은 대가를 치른다: 이 캡처에는 swapContributions 까지 다
    # 들어 있어 더 이상 "골든에 없는 확장 키"가 없다 — 목록에 없는 새 키는
    # 이제 응답 키 셋 비교(test_response_matches_frontend_contract_shape)와
    # 아래 extras 빈 셋 단언이 잡는다.
    extras = set(representative_response) - set(GOLDEN_RESPONSE)
    assert extras == set(), f"예상 밖 응답 키: {extras}"
    _assert_deep_close(
        {k: representative_response[k] for k in GOLDEN_RESPONSE}, GOLDEN_RESPONSE
    )

    # Spot-pin the headline numbers so a stale/regenerated golden file can't
    # silently weaken this test. [CHANGED, DV01-B] from the 2026-07-15 source
    # capture's finalMTM −254,095,011 / finalTotal −191,006,631: the bond MtM
    # leg now rides bond_risk's reval DV01 (derivation in the module comment
    # above); carry and swap legs are byte-identical to the source.
    # [RE-PINNED 2026-08-25 — OWNER "충격 미가산" · 감사록 F1] 채권 캐리가
    # 쿠폰(마크) 고정으로 정정되며 finalCarry 36,920,495 → 20,106,895
    # (경로 충격 가산분 −16,813,600), finalTotal 도 같은 델타. MTM·swap 은
    # 바이트 동일 — 캐리 항만 닿는 수정임이 이 두 핀의 불변으로 증명된다.
    # [RE-PINNED 2026-08-25 — 선물·퓨처스왑 합류] 골든을 다시 떴다: 가산 키만
    # 늘었다(futPnL·futMtm·finalFut·futuresValuation·futuresDailyReconciliation·
    # pvbpSensitivity 의 국채선물 행). 재생성 때 «가산 키를 걷어내면 종전
    # 골든과 딥-동일» 을 기계로 증명하고 갈아 끼웠다 — 종전 수치는 전부
    # 바이트 동일.
    assert representative_response["summary"] == {
        "finalMTM": -255_182_266,
        "finalCarry": 20_106_895,
        "finalSwap": 26_167_885,
        "finalFut": 0,
        "finalTotal": -208_907_486,
        "breakEvenDay": -1,
    }
    assert len(representative_response["chartData"]) == 61


# ── 3. Analytic bond-only case (no golden dependency) ────────────────────────

def test_bond_only_analytic(client: TestClient) -> None:
    """Single 1Y bond, parallel STEP shock of +10bp, 10 calendar days from
    Mon 2026-01-05 (8 KR business days: 1,2,3,4,7,8,9,10).

    Closed forms — 캐리는 쿠폰 고정 [OWNER, 2026-08-25 — "충격 미가산"]:
      MTM(t)      = pvbp * (365-t)/365 * (-10)
      carry/cal-d = eval*mtmYield/100/365 - eval*funding/365
                  = 0                        (mtmYield 3.0 == funding 3.0%)
    이 픽스처가 이제 «마크 = 조달이면 순캐리 0» 이라는 정확 모형의 성질
    자체를 시연한다 — 종전에는 충격 10bp 가 캐리로 새서 하루 27,397원이
    찍혔었다(그 값이 곧 팬텀 캐리의 최소 재현이었다).
    accrued per CALENDAR day (each business day books dt_cal days of carry).
    """
    req = {
        "positions": [{
            "id": "b1", "name": "KTB", "book": "RP Fund", "bondType": "bond",
            "sector": "국고채", "couponRate": 3.0, "notional": 10_000_000_000,
            "evaluationAmount": 10_000_000_000, "mtmYield": 3.0,
            "duration": 1.0, "pvbp": 1_000_000, "tenor": "1Y",
            "remainingDays": 365, "krdMap": {"1Y": 1_000_000},
        }],
        "shockCurves": {"bondCurves": {}, "swapCurve": []},
        "dailyShockCurves": {"bondCurves": {}, "swapCurve": []},
        "fundingRate": 0.03,
        "fundingEvents": [],
        "simDays": 10,
        "shockType": "step",
        "shockMode": "parallel",
        "baseShockBp": 10,
        "baseDate": "2026-01-05",
        # A flat par curve so the daily KRD reconciliation loop runs (the
        # empty-curve path is covered by test_bond_only_empty_irs_curves).
        "irsCurves": [{"t": 1.0, "rate": 0.03}, {"t": 5.0, "rate": 0.03}],
        "customPath": [],
    }
    r = client.post("/api/simulate", json=req)
    assert r.status_code == 200, r.text
    body = r.json()

    chart = body["chartData"]
    # Day 0 anchor + 8 business days.
    assert [row["day"] for row in chart] == [0, 1, 2, 3, 4, 7, 8, 9, 10]

    # Day 1: MTM = 1e6 * 364/365 * -10 = -9,972,602.74 ; carry = 0 (마크=조달)
    day1 = chart[1]
    assert day1["mtmPnL"] == round(1_000_000 * 364 / 365 * -10) == -9_972_603
    assert day1["cumulativeCarry"] == 0
    assert day1["totalPnL"] == round(1_000_000 * 364 / 365 * -10) == -9_972_603
    assert day1["swapPnL"] == 0

    # Final day 10: MTM = 1e6 * 355/365 * -10, carry stays 0 all the way.
    final = chart[-1]
    assert final["mtmPnL"] == round(1_000_000 * 355 / 365 * -10) == -9_726_027
    assert final["cumulativeCarry"] == 0
    assert body["summary"] == {
        "finalMTM": -9_726_027,
        "finalCarry": 0,
        "finalSwap": 0,
        "finalFut": 0,              # [2026-08-25] 선물 합류 — 선물 없는 북은 0
        "finalTotal": -9_726_027,
        "breakEvenDay": -1,
    }

    # bookDailyPnLs with a zero daily shock: carry and funding cancel exactly.
    assert body["bookDailyPnLs"] == [
        {"bookName": "RP Fund", "dailyCarry": 821_918, "fundingCost": -821_918,
         "bondValuation": 0, "futuresValuation": 0, "swapValuation": 0,
         "swapThetaPnL": 0, "totalDailyPnL": 0},
        {"bookName": "Total", "dailyCarry": 821_918, "fundingCost": -821_918,
         "bondValuation": 0, "futuresValuation": 0, "swapValuation": 0,
         "swapThetaPnL": 0, "totalDailyPnL": 0},
    ]

    # pvbpSensitivity aggregates the bond's krdMap into its sector row.
    ktb_row = next(r for r in body["pvbpSensitivity"] if r["sector"] == "국고채")
    assert ktb_row["tenors"]["1Y"] == 1_000_000
    assert ktb_row["total"] == 1_000_000
    grand = next(r for r in body["pvbpSensitivity"] if r["sector"] == "합계")
    assert grand["total"] == 1_000_000


# ── s11 T3: distribution fan bands ───────────────────────────────────────────

def test_distribution_bands(representative_response: dict) -> None:
    """Additive percentile fan: p50 must equal the base totalPnL trace exactly
    (the z=0 run IS the base run), bands aligned to chartData's day axis, and
    deterministic (no RNG).

    s15 T4: bands are keyed to their GENERATING rate-quantile scenario -- no
    per-day re-sorting -- so p5<=...<=p95 ordering is NOT asserted anymore
    (bands may cross on non-monotone books; on a rates-up-loses book the p95
    rate path sits below p50 by design). Scenario identity itself is pinned by
    test_fan_scenario_identity_non_monotone_book below."""
    dist = representative_response["distribution"]
    assert dist is not None
    assert dist["percentiles"] == [5, 25, 50, 75, 95]
    assert dist["sigmaBpDaily"] == 2.0
    assert dist["method"] == "quantile-scenario"

    chart = representative_response["chartData"]
    bands = dist["bands"]
    assert [b["day"] for b in bands] == [row["day"] for row in chart]
    for b, row in zip(bands, chart):
        assert b["p50"] == pytest.approx(row["totalPnL"]), (
            f"day {b['day']}: median band must be the base scenario trace"
        )
    # The fan must actually open: by the horizon the outer band pair straddles
    # a nonzero spread (a zero-width fan means the offset runs were dropped).
    assert bands[-1]["p95"] != bands[-1]["p5"]


def test_distribution_is_deterministic(client: TestClient, representative_response: dict) -> None:
    r2 = client.post("/api/simulate", json=REPRESENTATIVE_REQUEST)
    assert r2.status_code == 200
    assert r2.json()["distribution"] == representative_response["distribution"]


# ── s11 T4: funding-rate strip ───────────────────────────────────────────────

def test_funding_curve(representative_response: dict) -> None:
    """fundingCurve rides the same day axis as chartData and its rates obey the
    engine's own funding assumption: base fundingRate stepped by fundingEvents,
    carryBp == (positionRate - fundingRate) * 1e4."""
    fc = representative_response["fundingCurve"]
    chart = representative_response["chartData"]
    assert [p["day"] for p in fc] == [row["day"] for row in chart]

    req_rate = REPRESENTATIVE_REQUEST["fundingRate"]
    events = REPRESENTATIVE_REQUEST.get("fundingEvents") or \
        (REPRESENTATIVE_REQUEST.get("shockCurves") or {}).get("fundingEvents", [])
    base_date = REPRESENTATIVE_REQUEST["baseDate"][:10]

    for p in fc:
        expected = req_rate + sum(
            ev.get("shiftBp", 0) / 10000.0
            for ev in events
            if ev.get("date") and ev["date"] <= p["date"]
        )
        assert p["fundingRate"] == pytest.approx(expected), p
        if p["positionRate"] is not None:
            assert p["carryBp"] == pytest.approx(
                (p["positionRate"] - p["fundingRate"]) * 10000.0, abs=0.005
            ), p
    assert fc[0]["date"] == base_date
    # The representative book holds live bonds: the strip must be populated,
    # not a row of nulls.
    assert all(p["positionRate"] is not None for p in fc)


# ── s13 T2: configurable σ ───────────────────────────────────────────────────

def _bond_only_request(sigma_bp: float | None) -> dict:
    """The analytic single-bond fixture from test_bond_only_analytic: totalPnL
    is AFFINE in a parallel offset there (pvbp MTM + linear carry), so band
    half-widths must scale exactly with σ up to the engine's per-day rounding."""
    req = {
        "positions": [{
            "id": "b1", "name": "KTB", "book": "RP Fund", "bondType": "bond",
            "sector": "국고채", "couponRate": 3.0, "notional": 10_000_000_000,
            "evaluationAmount": 10_000_000_000, "mtmYield": 3.0,
            "duration": 1.0, "pvbp": 1_000_000, "tenor": "1Y",
            "remainingDays": 365, "krdMap": {"1Y": 1_000_000},
        }],
        "shockCurves": {"bondCurves": {}, "swapCurve": []},
        "dailyShockCurves": {"bondCurves": {}, "swapCurve": []},
        "fundingRate": 0.03,
        "fundingEvents": [],
        "simDays": 10,
        "shockType": "step",
        "shockMode": "parallel",
        "baseShockBp": 10,
        "baseDate": "2026-01-05",
        "irsCurves": [],
        "customPath": [],
    }
    if sigma_bp is not None:
        req["sigma_bp"] = sigma_bp
    return req


def test_sigma_omitted_equals_two_exactly(client: TestClient) -> None:
    """Backward compat: no sigma_bp == sigma_bp=2.0, byte-identical response."""
    r_default = client.post("/api/simulate", json=_bond_only_request(None))
    r_two = client.post("/api/simulate", json=_bond_only_request(2.0))
    assert r_default.status_code == r_two.status_code == 200
    assert r_default.json() == r_two.json()
    assert r_default.json()["distribution"]["sigmaBpDaily"] == 2.0


@pytest.mark.parametrize("bad", [0, -1.5, 25.01, 100])
def test_sigma_out_of_bounds_is_422(client: TestClient, bad: float) -> None:
    r = client.post("/api/simulate", json=_bond_only_request(bad))
    assert r.status_code == 422, r.text
    assert "sigma_bp" in r.text


def test_sigma_scales_bands_and_never_moves_the_median(client: TestClient) -> None:
    """For ANY σ the median is the base scenario trace (z=0 run is the base
    run, σ-independent), and on the affine bond fixture the half-widths scale
    linearly in σ (tolerance = the engine's per-day int rounding)."""
    responses = {s: client.post("/api/simulate", json=_bond_only_request(s)).json()
                 for s in (1.0, 2.0, 4.0)}

    base_trace = [row["totalPnL"] for row in responses[2.0]["chartData"]]
    for s, body in responses.items():
        assert body["distribution"]["sigmaBpDaily"] == s
        assert [row["totalPnL"] for row in body["chartData"]] == base_trace
        assert [b["p50"] for b in body["distribution"]["bands"]] == pytest.approx(base_trace)

    def half_widths(body: dict) -> list[tuple[float, float]]:
        # s15 T4: bands are scenario-keyed (p95 = the +1.645sigma RATE path), so
        # on this LONG bond fixture p95 sits BELOW p50 -- the "half-widths" are
        # signed offsets from the median and scale linearly in sigma either way.
        return [(b["p95"] - b["p50"], b["p50"] - b["p5"]) for b in body["distribution"]["bands"][1:]]

    for hw1, hw2, hw4 in zip(half_widths(responses[1.0]), half_widths(responses[2.0]),
                             half_widths(responses[4.0])):
        for k in (0, 1):
            assert hw2[k] == pytest.approx(2.0 * hw1[k], abs=3.0), (hw1, hw2)
            assert hw4[k] == pytest.approx(2.0 * hw2[k], abs=3.0), (hw2, hw4)
    # and the fan actually opens
    assert abs(half_widths(responses[2.0])[-1][0]) > 0


# ── 4. The live bridge's request shape (empty irsCurves) ─────────────────────

def test_bond_only_empty_irs_curves(client: TestClient) -> None:
    """The S6 position bridge (UIUX_test position-bridge.ts) does not carry IRS
    par rates yet: every real click on 시뮬레이션 실행 posts irsCurves: [] with
    bond-only positions. The SOURCE implementation 500s on that (its daily-KRD
    reconciliation loop bootstraps the par curve unconditionally -- ValueError
    on the empty list, measured 2026-07-15). This port's ONE deliberate runtime
    divergence: with an empty par curve the IRS reconciliation table is simply
    empty, and every bond-side output is still produced."""
    req = {
        "positions": [{
            "id": "b1", "name": "KTB", "book": "RP Fund", "bondType": "bond",
            "sector": "국고채", "couponRate": 3.0, "notional": 10_000_000_000,
            "evaluationAmount": 10_000_000_000, "mtmYield": 3.0,
            "duration": 1.0, "pvbp": 1_000_000, "tenor": "1Y",
            "remainingDays": 365, "krdMap": {},
        }],
        "shockCurves": {"bondCurves": {"국채": [{"t": 1, "val": 10}]}, "swapCurve": [{"t": 1, "val": 13}]},
        "dailyShockCurves": {"bondCurves": {}, "swapCurve": []},
        "fundingRate": 0.042,
        "fundingEvents": [],
        "simDays": 10,
        "shockType": "ramp",
        "shockMode": "matrix",
        "baseShockBp": 10,
        "baseDate": "2026-01-05",
        "irsCurves": [],
        "customPath": [{"day": 0, "bp": 0}, {"day": 10, "bp": 10}],
    }
    r = client.post("/api/simulate", json=req)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert len(body["chartData"]) == 9  # day 0 + 8 business days
    assert body["irsSettlementEvents"] == []
    # The bond math is unaffected by the missing par curve.
    assert body["chartData"][-1]["mtmPnL"] != 0
    assert body["summary"]["finalSwap"] == 0

    # [OWNER, 2026-08-25 — 엔진 단위 분리] 채권만 북의 대사는 **자기 표**에
    # 선다. 스왑 표는 v1 계약(스왑 + par 커브 있을 때만)으로 돌아가 여기서는
    # 비고, 채권 표가 손익 대사(평가·캐리·롤다운·조달)를 진다.
    assert body["irsDailyReconciliation"] == []
    tbl = body["bondDailyReconciliation"]
    assert tbl is not None, "채권만 있는 북의 채권 대사표가 비었다"
    rows = [r_ for r_ in tbl["rows"] if not r_.get("carryover")]
    assert rows
    # 표는 채권 몫(= 이 북의 헤드라인)으로 닫힌다 — 이 표가 있는 이유다.
    assert sum(r_["actual"] for r_ in rows) == pytest.approx(
        body["summary"]["finalTotal"], abs=len(rows)
    )
    # 조달 열이 선다 (서버가 이미 음수로 준다).
    assert any(isinstance(r_.get("funding"), int) for r_ in rows)
