# -*- coding: utf-8 -*-
"""BSS 테너 **통합** 장부 — 합치기의 의미를 핀으로 박는다.

`mrbook` 은 규칙을 안 쓴다. 규칙은 `mrbacktest` 것이고 이 모듈은 **더하기만**
한다 — 그래서 이 파일이 재는 것도 「더하기가 맞는가」다:

  · 통합 총손익 = 아홉 낱개 총손익의 합 (항등)
  · 통합 승률 = **한 통에 모은 거래**의 승률 (≠ 아홉 승률의 평균)
  · 날짜가 다른 계열도 **날짜로** 맞춘다 (인덱스로 맞추면 하루씩 밀린다)
  · 동시 다리 수와 손익분기 비용은 그 자리에서 되짚어 검산한다

SQL 을 안 만진다 — 합성 계열에 실제 엔진을 걸어 재료를 만든다.
"""
import datetime as dt
import math

import pytest

from app import mr as mr_mod
from app import mrbacktest as bt
from app import mrbook

PIN = dict(lookback=20, entry_z=2.0, exit_z=0.5, stop_z=3.5,
           cost_bp=0.5, notional=1_000_000)


def _ou(n: int, *, seed: int, phi: float, sd: float = 1.4, mu: float = 30.0) -> list[float]:
    """평균회귀 계열(AR(1)) — LCG + Box-Muller 라 난수 씨앗이 곧 계열이다.

    사인파를 쓰면 안 된다: 트레일링 창의 평균이 파도를 따라 올라가서 z 가 높은
    채로 값이 계속 오르고, 그러면 이 픽스처가 **추세를 역행하는 판**이 되어
    합치기가 아니라 엔진의 성질을 재게 된다. AR(1)은 창 안에서 실제로 되돌아온다.
    """
    s = seed
    v = mu
    out = []
    for _ in range(n):
        s = (s * 1664525 + 1013904223) % (2 ** 32)
        u1 = s / 0xFFFFFFFF
        s = (s * 1664525 + 1013904223) % (2 ** 32)
        u2 = s / 0xFFFFFFFF
        g = math.sqrt(-2 * math.log(u1 + 1e-12)) * math.cos(2 * math.pi * u2)
        v = mu + phi * (v - mu) + sd * g
        out.append(round(v * 100) / 100)
    return out


#: 픽스처의 첫 날. 실제 달력이라야 하는 이유는 **구간**이다 [2026-09-07] —
#: `mrmetrics.span_cut` 이 「마지막 봉에서 달력으로 n개월」을 세므로 `D0000`
#: 같은 가짜 날짜로는 못 선다. 종전 픽스처가 그 꼴이었고, 구간이 장부에 들어온
#: 날 아홉 시험이 한꺼번에 죽었다 — 시험이 **생산의 계약(ISO)** 을 표현하지
#: 못하고 있었다는 뜻이라, 날짜 쪽을 계약에 맞췄다.
#: 달력일을 그대로 쓴다(주말을 안 뺀다). 이 파일이 재는 것은 «합치기» 이지
#: 영업일 규칙이 아니고, 날짜가 서로 다르고 순서가 있으면 그 시험은 선다.
_D0 = dt.date(2020, 1, 1)


def _dates(n: int, start: int = 0) -> list[str]:
    return [(_D0 + dt.timedelta(days=start + i)).isoformat() for i in range(n)]


def _leg(sid: str, label: str, dates: list[str], vals: list[float], **over) -> dict:
    p = {**PIN, **over}
    return {"id": sid, "label": label, "dates": dates,
            "r": bt.simulate(dates, vals, **p)}


#: 세 다리 — 회귀 속도·진폭을 달리 둬서 거래 수와 승률이 서로 다르게 나온다
#: (같으면 「승률의 평균 ≠ 모은 승률」을 재는 시험이 아무것도 안 잰다).
SPEC = [("BSS-2Y", "BSS 2Y", 7, 0.85, 1.4),
        ("BSS-3Y", "BSS 3Y", 99, 0.75, 1.4),
        ("BSS-10Y", "BSS 10Y", 5, 0.90, 0.9)]
N = 400


def _span(out: dict, key: str) -> dict:
    """집계 결과에서 구간 하나 — 없으면 그 자리에서 죽는다(조용히 None 금지)."""
    hit = [s for s in out["spans"] if s["span"] == key]
    assert hit, f"구간 {key} 가 없다 — 있는 것: {[s['span'] for s in out['spans']]}"
    return hit[0]


def _three(**over) -> list[dict]:
    return [_leg(sid, label, _dates(N), _ou(N, seed=seed, phi=phi, sd=sd), **over)
            for sid, label, seed, phi, sd in SPEC]


# ── 계열 목록 ───────────────────────────────────────────────────────────────


def test_book_covers_every_bss_tenor_in_maturity_order():
    """랭킹은 |z| 순이지만 통합은 **만기 순**이다 — 커브의 모양이 그 순서에만 보인다."""
    ids = [sid for sid, _ in mrbook.bss_series()]
    assert ids == [sid for sid, _, kind in mr_mod.SERIES if kind == "bss"]
    assert len(ids) == 9
    assert ids[0] == "BSS-6M" and ids[-1] == "BSS-10Y"
    # 통합 id 는 계열 목록에 **없다** — 순위는 |z| 로 매기는데 집계 줄은 값이 아니다.
    assert mrbook.BOOK_ID not in {sid for sid, _, _ in mr_mod.SERIES}


def test_tenor_of_reads_the_label():
    assert mrbook.tenor_of("BSS-1.5Y") == "1.5Y"
    assert mrbook.tenor_of("BSS-10Y") == "10Y"


# ── 보드의 통합 행 ──────────────────────────────────────────────────────────


def _row(sid, z, pct_b, kind, days=None, v=10.0):
    return {"id": sid, "label": sid.replace("-", " "), "kind": "bss", "v": v,
            "d1": 0.5, "z": z, "pctB": pct_b, "asof": "2026-08-28",
            "state": {"kind": kind, "days": days}}


def test_watch_counts_states_and_averages_only_unitless_numbers():
    rows = [
        _row("BSS-2Y", -2.6, -12.0, "below", 3),
        _row("BSS-3Y", 0.4, 60.0, "inside"),
        _row("BSS-10Y", 2.1, 104.0, "above", 1),
        _row("BSS-5Y", -0.9, 27.0, "reentry-low", 2),
        # 다른 계열은 통합에 안 든다 — BSS 만의 장부다.
        {**_row("FUT-KTB3", 3.0, 120.0, "above", 4), "kind": "fut"},
    ]
    w = mrbook.watch(rows)
    assert w["id"] == mrbook.BOOK_ID and w["kind"] == "book"
    assert w["n"] == 4
    assert (w["outLow"], w["outHigh"], w["reentry"], w["inside"]) == (1, 1, 1, 1)
    # |z| 와 %B 는 단위가 없어 평균이 뜻을 갖는다.
    assert w["meanAbsZ"] == pytest.approx((2.6 + 0.4 + 2.1 + 0.9) / 4, abs=5e-3)
    assert w["meanPctB"] == pytest.approx((-12.0 + 60.0 + 104.0 + 27.0) / 4, abs=5e-2)
    # **레벨은 없다** — 만기가 다른 아홉 스프레드의 평균은 거래할 수 있는 값이 아니다.
    assert "v" not in w and "d1" not in w
    # 가장 늘어난 다리를 이름으로 말한다 — 개수만 남으면 「어디가」를 못 읽는다.
    assert w["peak"]["id"] == "BSS-2Y"
    # 종가일이 갈리면 그 사실을 센다 — 최댓값만 적으면 아홉 다 최신인 척한다.
    assert w["asof"] == "2026-08-28" and w["asofMin"] == "2026-08-28" and w["stale"] == 0
    # 다리는 **만기 순**이다(랭킹 순이 아니다).
    assert [g["id"] for g in w["legs"]] == ["BSS-2Y", "BSS-3Y", "BSS-5Y", "BSS-10Y"]
    assert [g["tenor"] for g in w["legs"]] == ["2Y", "3Y", "5Y", "10Y"]


def test_watch_survives_a_series_without_a_band_yet():
    """창이 안 찬 계열은 z·%B 가 None 이다 — 평균에서 빠지되 개수에는 든다."""
    w = mrbook.watch([_row("BSS-2Y", None, None, "inside"),
                      _row("BSS-3Y", 1.0, 70.0, "inside")])
    assert w["n"] == 2 and w["inside"] == 2
    assert w["meanAbsZ"] == 1.0 and w["meanPctB"] == 70.0


def test_watch_counts_the_legs_that_lag():
    """만기마다 민평×IRS 교집합이라 한 다리만 하루 뒤처질 수 있다."""
    rows = [_row("BSS-2Y", 1.0, 50.0, "inside"),
            {**_row("BSS-3Y", 1.0, 50.0, "inside"), "asof": "2026-08-21"},
            {**_row("BSS-5Y", 1.0, 50.0, "inside"), "asof": "2026-08-24"}]
    w = mrbook.watch(rows)
    assert w["asof"] == "2026-08-28" and w["asofMin"] == "2026-08-21"
    assert w["stale"] == 2


def test_watch_is_none_without_bss_rows():
    assert mrbook.watch([{**_row("FUT-KTB3", 1.0, 50.0, "inside"), "kind": "fut"}]) is None


# ── 통합 백테스트 ───────────────────────────────────────────────────────────


def test_total_is_the_sum_of_the_legs():
    legs = _three()
    out = mrbook.aggregate(legs, notional=PIN["notional"],
                           cost_bp=PIN["cost_bp"], dynamic_cost=False)
    parts = sum(leg["r"]["summary"]["totalPnl"] for leg in legs)
    assert out["summary"]["totalPnl"] == pytest.approx(parts, abs=1.0)
    # 다리별 표도 같은 수를 진다 — 두 곳이 갈리면 화면이 어느 쪽을 믿을지 모른다.
    assert sum(p["totalPnl"] for p in out["legs"]) == pytest.approx(parts, abs=9.0)
    assert [p["id"] for p in out["legs"]] == [leg["id"] for leg in legs]


def test_win_rate_pools_trades_instead_of_averaging_rates():
    """거래 수가 다른 아홉 승률의 평균은 묶음의 승률이 **아니다**."""
    legs = _three()
    out = mrbook.aggregate(legs, notional=PIN["notional"],
                           cost_bp=PIN["cost_bp"], dynamic_cost=False)
    trades = [t for leg in legs for t in leg["r"]["trades"]]
    assert out["summary"]["numTrades"] == len(trades)
    # **반올림 전** 손익으로 센다 — 화면용 소수 둘째 자리로 세면 0.004원짜리
    # 거래가 패로 넘어가 낱개 창의 승률과 갈린다.
    wins = sum(1 for t in trades if t["pnl"] > 0)
    assert out["summary"]["winRate"] == pytest.approx(wins / len(trades), abs=5e-5)
    rates = [leg["r"]["summary"]["winRate"] for leg in legs]
    # 이 픽스처에서 둘이 실제로 갈린다 — 안 갈리면 이 시험이 아무것도 안 잰다.
    assert abs(sum(rates) / len(rates) - out["summary"]["winRate"]) > 1e-6
    # 거래마다 어느 만기의 것인지가 붙는다(표의 첫 칸).
    assert {t["sid"] for t in out["trades"]} <= {leg["id"] for leg in legs}
    assert out["trades"] == sorted(out["trades"], key=lambda t: (t["entryT"], t["sid"]))
    # 거래 줄의 어휘는 낱개 창의 것과 같다 — 두 표가 같은 사건을 다르게 안 부른다.
    assert set(out["trades"][0]) >= {"sid", "tenor", "entryT", "exitT", "dir",
                                     "entryZ", "exitZ", "pnl", "why", "bars"}


def test_dates_are_matched_by_date_not_by_index():
    """계열마다 표본이 하루씩 다를 수 있다 — 인덱스로 더하면 손익이 밀린다."""
    n = 120
    a = _leg("BSS-2Y", "BSS 2Y", _dates(n), _ou(n, seed=7, phi=0.85))
    # 열흘 늦게 시작하는 계열.
    b = _leg("BSS-3Y", "BSS 3Y", _dates(n, start=10), _ou(n, seed=99, phi=0.75))
    out = mrbook.aggregate([a, b], notional=PIN["notional"],
                           cost_bp=PIN["cost_bp"], dynamic_cost=False)
    assert out["from"] == _dates(1)[0] and out["to"] == _dates(1, start=n + 9)[0]
    assert out["bars"] == n + 10
    at = {p["t"]: p for p in out["points"]}
    ap = {p["date"]: p for p in a["r"]["points"]}
    bp_ = {p["date"]: p for p in b["r"]["points"]}
    for t, p in at.items():
        want = ap.get(t, {}).get("dailyPnl", 0.0) + bp_.get(t, {}).get("dailyPnl", 0.0)
        assert p["pnl"] == pytest.approx(want, abs=0.01), t
    # 누적은 마지막 줄이 총손익이다.
    assert out["points"][-1]["cum"] == pytest.approx(out["summary"]["totalPnl"], abs=1.0)


def test_concurrent_legs_are_counted_and_priced():
    """동일가중 합의 대가는 명목이다 — 아홉이 서면 걸린 돈이 아홉 배다."""
    legs = _three()
    out = mrbook.aggregate(legs, notional=PIN["notional"],
                           cost_bp=PIN["cost_bp"], dynamic_cost=False)
    at = {p["t"]: p["legs"] for p in out["points"]}
    for leg in legs:
        for p in leg["r"]["points"]:
            assert at[p["date"]] >= (1 if p["position"] != 0 else 0)
    live = [p["legs"] for p in out["points"]]
    assert out["book"]["maxLegs"] == max(live) <= len(legs)
    assert out["book"]["peakNotional"] == max(live) * PIN["notional"]
    assert at[out["book"]["peakT"]] == max(live)
    assert out["book"]["idleShare"] == pytest.approx(
        sum(1 for x in live if x == 0) / len(live), abs=5e-5)


def test_breakeven_cost_zeroes_the_book():
    """손익분기는 닫힌형이다 — 그 비용으로 다시 돌리면 총손익이 0 이어야 한다."""
    legs = _three()
    out = mrbook.aggregate(legs, notional=PIN["notional"],
                           cost_bp=PIN["cost_bp"], dynamic_cost=False)
    be = out["summary"]["breakevenCostBp"]
    assert be is not None and be > 0
    again = mrbook.aggregate(_three(cost_bp=be), notional=PIN["notional"],
                             cost_bp=be, dynamic_cost=False)
    # 정확히 0 이 아닌 이유는 `be` 를 소수 셋째 자리에서 자르기 때문이다(화면이
    # 읽을 수 있는 자리수). 남는 것은 그 반올림 × 명목 × 비용 문 횟수뿐이다.
    assert abs(again["summary"]["totalPnl"]) < abs(out["summary"]["totalPnl"]) * 0.01
    # 동적 비용 판에서는 「몇 bp」가 한 숫자로 안 나온다 — 배수만 답한다.
    dyn = mrbook.aggregate(legs, notional=PIN["notional"],
                           cost_bp=PIN["cost_bp"], dynamic_cost=True)
    assert dyn["summary"]["breakevenCostBp"] is None
    assert dyn["summary"]["breakevenCostMult"] == pytest.approx(
        out["summary"]["breakevenCostMult"], abs=1e-3)


def test_diversification_reads_one_when_the_legs_are_the_same_trade():
    """같은 계열 셋을 더하면 유효 독립은 하나다 — 분산 효과가 없다는 사실."""
    n = 260
    same = [_leg(f"BSS-{i}Y", f"BSS {i}Y", _dates(n), _ou(n, seed=7, phi=0.85))
            for i in (2, 3, 5)]
    out = mrbook.aggregate(same, notional=PIN["notional"], cost_bp=PIN["cost_bp"],
                           dynamic_cost=False)
    # 구간을 따라간다 [2026-09-07] — 「전체」가 종전 `diag` 자리의 그 수다.
    d = _span(out, "all")["diversification"]
    assert d["n"] == 3
    assert d["meanPairCorr"] == pytest.approx(1.0, abs=1e-6)
    assert d["effectiveN"] == pytest.approx(1.0, abs=0.05)
    assert d["days"] == out["bars"], "전체 구간인데 상관을 일부 봉에서만 쟀다"
    # 서로 다른 계열이면 유효 독립이 늘어난다.
    mixed = mrbook.aggregate(_three(), notional=PIN["notional"],
                             cost_bp=PIN["cost_bp"], dynamic_cost=False)
    assert _span(mixed, "all")["diversification"]["effectiveN"] > 1.0
    # 짧은 구간은 **적은 봉에서** 잰다 — 화면이 그 사실을 가려야 하므로 값이
    # 아니라 «몇 봉에서 쟀나» 가 실려 있어야 한다.
    assert _span(mixed, "1m")["diversification"]["days"] < _span(mixed, "all")["diversification"]["days"]


def test_leg_calmar_sits_next_to_the_book_calmar():
    """통합이 개별보다 나은지는 중앙값 옆에 놓아야 판정이 선다.

    축이 샤프 → **Calmar** 로 갈렸다 [OWNER 2026-09-07]. 그래서 이 시험이 재는
    것도 갈렸다: 종전에는 「통합 SR 이 개별 중앙보다 √유효독립 배쯤 크다」가
    검산이었는데, Calmar 의 분모는 최대낙폭이라 그 검산이 안 선다. 남는 명제는
    **줄 세우기가 성립하나**(min ≤ median ≤ max)와 **못 잰 다리를 안 센다**이다.
    """
    legs = _three()
    out = mrbook.aggregate(legs, notional=PIN["notional"],
                           cost_bp=PIN["cost_bp"], dynamic_cost=False)
    lc = _span(out, "all")["legCalmar"]
    assert lc["of"] == 3, "다리 수를 잘못 셌다"
    assert lc["n"] <= lc["of"]
    if lc["n"]:
        assert lc["min"] <= lc["median"] <= lc["max"]
        assert 0 <= lc["positive"] <= lc["n"]
    # **0 으로 채우지 않는다** — 낙폭이 0 인 다리는 Calmar 가 None 이고, 0 으로
    # 메우면 그 다리가 «최악» 으로 줄을 서서 중앙값을 끌어내린다.
    cal = [g["calmar"] for g in _span(out, "all")["legs"]]
    assert lc["n"] == sum(1 for c in cal if c is not None)
    # 사유별·손익비는 **모은 거래** 위에서 센다.
    assert sum(e["n"] for e in out["diag"]["exits"]) == out["summary"]["numTrades"]
    pay = out["diag"]["payoff"]
    if pay is not None:
        assert pay["wins"] + pay["losses"] == out["summary"]["numTrades"]


def test_open_legs_are_named_not_hidden():
    """표본 끝의 미청산은 승률에 안 들어간다 — 몇 다리인지를 대신 말한다."""
    legs = _three()
    out = mrbook.aggregate(legs, notional=PIN["notional"],
                           cost_bp=PIN["cost_bp"], dynamic_cost=False)
    opens = [leg for leg in legs if leg["r"]["open"] is not None]
    assert out["summary"]["openLegs"] == len(opens)
    assert {o["sid"] for o in out["open"]} == {leg["id"] for leg in opens}
    if opens:
        assert out["summary"]["openPnl"] == pytest.approx(
            sum(leg["r"]["open"]["pnl"] for leg in opens), abs=1.0)


def test_blocked_and_gated_are_summed_separately():
    """방향(데스크의 제약)과 필터(우리가 고른 것)를 한 숫자로 합치지 않는다."""
    legs = _three(allow_dirs=(-1,))
    out = mrbook.aggregate(legs, notional=PIN["notional"],
                           cost_bp=PIN["cost_bp"], dynamic_cost=False)
    assert out["blocked"]["spells"] == sum(leg["r"]["blocked"]["spells"] for leg in legs)
    assert out["blocked"]["spells"] > 0          # 한 방향뿐이면 실제로 막힌다
    assert out["gated"] == {"spells": 0, "days": 0}


def test_points_carry_the_cost_paid_as_a_positive_number():
    """봉마다 **문 비용**이 실린다 — 다른 레인이 공통 창에서 다시 재려면 필요하다.

    두 가지를 잰다.

    ① **부호는 지불액(양수)** 이다. 엔진 봉의 `barCost` 는 MR 에서 음수인데 CTA
       엔진에서는 양수라 규약이 반대다(`scripts/lane_costs` 가 그 함정을 적어 뒀고,
       실제로 한 번 10.5% 를 13.3% 로 잘못 낸 적이 있다). 페이로드를 읽는 쪽이 그
       사정을 알 리 없으므로 이 칸에서는 부호를 없앤다.
    ② **합이 손익분기 배수와 맞는다.** 봉의 비용을 다 더한 것이 장부가 실제로 문
       비용이고, `breakevenCostMult = 1 + 총손익/문 비용` 이 그 위에 선다. 두 수가
       갈리면 화면의 손익분기가 딴 비용을 말하고 있는 것이다.
    """
    legs = _three()
    out = mrbook.aggregate(legs, notional=PIN["notional"],
                           cost_bp=PIN["cost_bp"], dynamic_cost=False)
    costs = [p["cost"] for p in out["points"]]
    assert costs, "봉이 없어요"
    assert all(c >= 0 for c in costs), "비용이 음수로 실렸어요"
    assert sum(costs) > 0, "비용이 통째로 0 이에요"

    paid = sum(costs)
    mult = out["summary"]["breakevenCostMult"]
    assert mult == pytest.approx(1.0 + out["summary"]["totalPnl"] / paid, abs=1e-3)
