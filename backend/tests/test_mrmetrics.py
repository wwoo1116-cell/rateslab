# -*- coding: utf-8 -*-
"""절대수익형 성과지표와 구간 채점 — 정의를 손으로 검산한다.

이 파일이 지키는 것 넷.
  ① **구간은 달력으로 센다** — 봉 수가 아니다. 휴장이 많은 구간이 조용히
     길어지면 카드와 차트가 다른 구간을 말한다.
  ② **GPR 은 월 버킷, Omega 는 일별**이다. 같은 계열에서 재면 `GPR = Omega − 1`
     이라 한 지표를 두 번 적는 셈이 되고, 그 항등을 여기서 실제로 잰다.
  ③ **회복일은 골에서** 센다(고점에서가 아니다). 못 되찾은 구간은 일수와
     «회복 안 함» 을 같이 낸다 — 한쪽만 보면 아직 물속인 구간이 회복한 구간처럼
     읽힌다.
  ④ **손익분기 비용의 닫힌형**이 엔진의 것(`mrbacktest.breakeven_cost_bp`)과
     같은 답을 준다. 여기서는 «문 돈» 하나로 배수를 내므로 건수를 안 센다 —
     두 자리가 갈리면 화면의 두 숫자가 갈린다.
"""
import datetime as dt
import math

from app import mrbacktest as bt
from app import mrmetrics as mrm


def _bizdays(start: dt.date, n: int) -> list[str]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def _points(daily: list[float], bar_cost: float = 0.0) -> list[dict]:
    cum, out = 0.0, []
    for x in daily:
        cum += x
        out.append({"dailyPnl": x, "cumulativePnl": cum, "barCost": -bar_cost})
    return out


# ── ① 구간 ──────────────────────────────────────────────────────────────────

def test_span_start_counts_calendar_months_not_bars():
    dates = _bizdays(dt.date(2024, 1, 1), 500)
    i = mrm.span_start(dates, 12)
    # 마지막 봉에서 달력 12개월 앞 — 그 날짜 **이후 첫 봉**이다.
    assert dates[i] >= mrm._months_before(dates[-1], 12)
    assert dates[i - 1] < mrm._months_before(dates[-1], 12)
    assert mrm.span_start(dates, None) == 0


def test_span_start_survives_month_end_overflow():
    # 5-31 에서 3개월을 물리면 2-31 이 없다 — 다음 달로 굴린다(Date.UTC 판례).
    assert mrm._months_before("2024-05-31", 3) == "2024-03-02"
    assert mrm._months_before("2024-01-15", 12) == "2023-01-15"


def test_span_never_returns_an_empty_window():
    dates = _bizdays(dt.date(2024, 1, 1), 5)          # 표본이 한 주뿐
    i = mrm.span_start(dates, 12)                     # 구간이 표본보다 길다
    assert i == 0
    dates2 = ["2020-01-02"]                           # 봉 하나, 구간 밖
    assert mrm.span_start(dates2, 1) == 0


# ── ② 지표의 정의 ───────────────────────────────────────────────────────────

def test_omega_and_daily_gain_to_pain_are_the_same_number_plus_one():
    """그래서 GPR 을 **월 버킷**으로 잰다 — 안 그러면 카드 하나가 중복이다."""
    daily = [3.0, -1.0, 2.0, -4.0, 5.0]
    gains = sum(x for x in daily if x > 0)
    losses = -sum(x for x in daily if x < 0)
    assert math.isclose(gains / losses - 1.0, sum(daily) / losses)


def test_gpr_uses_month_buckets_and_is_none_when_there_are_under_two():
    # 한 달 안에서만 도는 표본 — 버킷이 하나라 GPR 은 「그 달의 부호」일 뿐이다.
    dates = _bizdays(dt.date(2024, 3, 1), 15)
    m = mrm.score(dates, _points([1.0] * 14 + [-3.0]), [], 0, 0.5)
    assert m["gprMonths"] == 1 and m["gpr"] is None
    # 두 달로 늘리고 둘째 달을 손실로 — 이제 분모가 선다.
    dates = _bizdays(dt.date(2024, 3, 1), 45)
    daily = [1.0] * 21 + [-2.0] * 24
    m = mrm.score(dates, _points(daily), [], 0, 0.5)
    assert m["gprMonths"] >= 2
    mon: dict[str, float] = {}
    for t, x in zip(dates, daily):
        mon[t[:7]] = mon.get(t[:7], 0.0) + x
    loss = -sum(v for v in mon.values() if v < 0)
    assert math.isclose(m["gpr"], round(sum(mon.values()) / loss, 3))


def test_sortino_divides_by_all_days_not_only_losing_days():
    daily = [1.0, 1.0, 1.0, -2.0]
    m = mrm.score(_bizdays(dt.date(2024, 1, 1), 4), _points(daily), [], 0, 0.5)
    dd = math.sqrt((2.0 ** 2) / 4)                    # 전체 일수로 나눈다
    want = (sum(daily) / 4) / dd * math.sqrt(252)
    assert math.isclose(m["sortino"], round(want, 3))


def test_calmar_and_martin_share_the_same_annualised_numerator():
    daily = [5.0, -3.0, 4.0, -6.0, 2.0, 3.0]
    dates = _bizdays(dt.date(2024, 1, 1), len(daily))
    m = mrm.score(dates, _points(daily), [], 0, 0.5)
    ann = sum(daily) * 252 / len(daily)
    assert math.isclose(m["calmar"], round(ann / m["maxDrawdown"], 3))
    # Ulcer 는 카드에 **원 단위 두 자리**로 실리므로, 나눗셈은 반올림 전 값으로
    # 검산한다 — 실린 수로 되나누면 셋째 자리에서 갈린다(실측 65.328 대 65.421).
    cum, peak, dd = 0.0, 0.0, []
    for x in daily:
        cum += x
        peak = max(peak, cum)
        dd.append(peak - cum)
    ulcer = math.sqrt(sum(d * d for d in dd) / len(dd))
    assert math.isclose(m["martin"], round(ann / ulcer, 3))
    # Ulcer 는 **낙폭 경로의 RMS** 라 늘 최대낙폭 이하다(둘 다 원 단위).
    assert 0 < m["ulcer"] <= m["maxDrawdown"]


def test_profit_factor_is_measured_on_trades_not_on_days():
    daily = [1.0] * 10
    dates = _bizdays(dt.date(2024, 1, 1), 10)
    trades = [{"exitDate": dates[3], "pnl": 6.0}, {"exitDate": dates[7], "pnl": -2.0}]
    m = mrm.score(dates, _points(daily), trades, 0, 0.5)
    assert math.isclose(m["profitFactor"], 3.0)
    assert m["numTrades"] == 2 and math.isclose(m["winRate"], 0.5)
    # 일별로는 손실 난 날이 없어 Omega 가 아예 안 선다 — 분모가 다르다는 사실.
    assert m["omega"] is None


def test_window_counts_only_trades_closed_inside_it():
    dates = _bizdays(dt.date(2024, 1, 1), 300)
    trades = [{"exitDate": dates[10], "pnl": 9.0}, {"exitDate": dates[290], "pnl": -1.0}]
    m = mrm.score(dates, _points([0.5] * 300), trades, 250, 0.5)
    assert m["numTrades"] == 1 and m["winRate"] == 0.0
    assert m["from"] == dates[250] and m["days"] == 50


# ── ③ 낙폭과 회복 ───────────────────────────────────────────────────────────

def test_recovery_is_counted_from_the_trough_and_says_when_it_never_came():
    #  +10, −10, −10, +5, +5, +10  → 골은 index 2, 전고점 10 을 index 5 에 회복
    daily = [10.0, -10.0, -10.0, 5.0, 5.0, 10.0]
    dates = _bizdays(dt.date(2024, 1, 1), len(daily))
    m = mrm.score(dates, _points(daily), [], 0, 0.5)
    assert math.isclose(m["maxDrawdown"], 20.0)
    assert m["recoveryDays"] == 3 and m["recovered"] is True
    # 회복 전에 표본이 끊기면 «몇 일을 물속에 있었나» 와 «아직» 을 같이 낸다.
    m2 = mrm.score(dates[:5], _points(daily[:5]), [], 0, 0.5)
    assert m2["recovered"] is False and m2["recoveryDays"] == 2


def test_drawdown_is_rebased_to_the_window_start():
    # 앞 구간에서 크게 잃고 뒤 구간은 단조 상승 — 구간 낙폭은 0 이어야 한다.
    daily = [-100.0] * 10 + [1.0] * 10
    dates = _bizdays(dt.date(2024, 1, 1), 20)
    m = mrm.score(dates, _points(daily), [], 10, 0.5)
    assert m["maxDrawdown"] == 0.0 and m["calmar"] is None
    assert math.isclose(m["totalPnl"], 10.0)


# ── ④ 손익분기 — 엔진의 닫힌형과 같은 답 ────────────────────────────────────

def test_breakeven_matches_the_engine_closed_form():
    n, cost_bp = 1_000_000.0, 0.5
    vals = [0.0]
    rng = [3.0, -2.0, 5.0, -7.0, 4.0, 1.0, -1.0, 6.0, -3.0, 2.0]
    for i in range(200):
        vals.append(vals[-1] + rng[i % len(rng)] * (1 if i % 3 else -1))
    dates = _bizdays(dt.date(2020, 1, 1), len(vals))
    r = bt.simulate(dates, vals, lookback=20, entry_z=2.0, exit_z=0.5,
                    stop_z=3.5, cost_bp=cost_bp, notional=n)
    m = mrm.score(dates, r["points"], r["trades"], 0, cost_bp)
    events = sum(1 for t in r["trades"] for _ in (0, 1))   # 진입 + 청산
    if r["open"]:
        events += 1
    want = bt.breakeven_cost_bp(r["summary"]["totalPnl"], cost_bp, n, events)
    assert m["breakevenCostBp"] is not None
    assert math.isclose(m["breakevenCostBp"], round(want, 3), abs_tol=1e-3)
    assert math.isclose(m["breakevenCostMult"], round(want / cost_bp, 3), abs_tol=1e-3)


def test_spans_for_gives_all_four_and_all_is_the_whole_sample():
    daily = [1.0, -0.5] * 400
    dates = _bizdays(dt.date(2021, 1, 1), len(daily))
    out = mrm.spans_for(dates, _points(daily, bar_cost=0.1), [], 0.5)
    assert [b["span"] for b in out] == ["all", "1y", "1q", "1m"]
    assert out[0]["from"] == dates[0] and out[0]["days"] == len(daily)
    # 구간이 짧아질수록 봉이 줄고, 순서가 뒤집히지 않는다.
    assert out[0]["days"] > out[1]["days"] > out[2]["days"] > out[3]["days"]


# ── ⑤ 근사 최적화 격자 [OWNER 2026-09-04] ───────────────────────────────────
#
# 라우트가 아니라 격자 함수를 직접 부른다 — SQL·민평을 안 만지고 산술만 잰다
# (`test_mr.py` 가 보드에 대해 하는 것과 같은 규율).

def _walk(n: int = 900) -> tuple[list[str], list[float]]:
    import random
    rng = random.Random(7)
    vals = [0.0]
    for _ in range(n):
        vals.append(vals[-1] * 0.98 + rng.gauss(0, 1))
    return _bizdays(dt.date(2020, 1, 1), len(vals)), vals


BASE = {"lookback": 60, "entryZ": 2.0, "exitZ": 0.5, "stopZ": 3.5,
        "costBp": 0.5, "notional": 1_000_000.0, "entryMode": "level"}


def _expected_cells(lookbacks: int, base: dict | None = None) -> int:
    """프리셋 전개에서 **제외 칸을 뺀** 수. 수를 손으로 적지 않는다 [2026-10-16] —
    프리셋이나 제외 규칙이 바뀌면 이 셈이 같이 따라와야 하고, 그래야 이 시험이
    「162」라는 철자 때문에 결정을 막는 쪽이 되지 않는다(`test_mrplan` 이 그걸로
    7건 빨간 채였다)."""
    from app import mr as mr_mod

    P = mr_mod.STRATEGY_PRESETS
    lbs = list(P["lookback"])
    if base and base["lookback"] not in lbs:
        lbs.append(base["lookback"])
    assert len(lbs) == lookbacks
    n = 0
    for lb in lbs:
        for ez in P["entryZ"]:
            for sz in P["stopZ"]:
                for xz in P["exitZ"]:
                    for md in ("level", "touch"):
                        cur = bool(base) and (lb == base["lookback"] and ez == base["entryZ"]
                                              and sz == base["stopZ"] and xz == base["exitZ"]
                                              and md == base["entryMode"])
                        if not mr_mod.grid_excludes(ez, sz) or cur:
                            n += 1
    return n


def test_grid_is_the_preset_cross_product_and_marks_exactly_one_current_cell():
    from app import main as M
    from app import mr as mr_mod

    dates, vals = _walk()
    got = M._mr_optimize(dates, vals, dict(BASE), (-1, 1), span="all")
    # 프리셋 넷 × 진입 규칙 둘 **− 제외 칸**(손절선이 진입선 안쪽: 2.5/2.5).
    assert len(got["cells"]) == _expected_cells(3) == 144
    # ★성질 자체를 잰다 — 수가 맞아도 엉뚱한 칸이 남아 있으면 이 단언이 잡는다.
    assert not [c for c in got["cells"] if mr_mod.grid_excludes(c["entryZ"], c["stopZ"])]
    cur = [c for c in got["cells"] if c["current"]]
    assert len(cur) == 1, "지금 노브가 표에서 한 칸으로 서야 순위를 읽을 수 있다"
    c = cur[0]
    assert (c["lookback"], c["entryZ"], c["exitZ"], c["stopZ"], c["entryMode"]) == (
        60, 2.0, 0.5, 3.5, "level")
    # 조합이 다 다르다 — 같은 칸을 두 번 돌면 순위가 거짓이 된다.
    keys = {(c["lookback"], c["entryZ"], c["exitZ"], c["stopZ"], c["entryMode"])
            for c in got["cells"]}
    assert len(keys) == len(got["cells"])


def test_a_free_knob_value_joins_the_grid_as_its_own_cell():
    from app import main as M

    dates, vals = _walk()
    base = dict(BASE, lookback=45)                    # 프리셋 밖(자유 룩백)
    got = M._mr_optimize(dates, vals, base, (-1, 1), span="all")
    assert len(got["cells"]) == _expected_cells(4, base) == 192
    assert sum(1 for c in got["cells"] if c["current"]) == 1
    assert 45 in {c["lookback"] for c in got["cells"]}


def test_my_own_cell_stays_in_the_table_even_when_the_grid_excludes_it():
    """⚠제외의 **예외**: 손으로 2.5/2.5 를 고른 사람에게 「내 칸이 없는 표」를
    주지 않는다 [2026-10-16]. 자동 채택은 `mrplan.BASE_KNOBS`(2.0/2.5)에서
    출발하므로 그 길로는 이 칸이 아예 서지 않는다 — 여기 서는 것은 **사람이 그
    조합을 직접 고른 경우** 하나뿐이고, 그러면 표가 그 칸의 등수를 말해야 한다."""
    from app import main as M
    from app import mr as mr_mod

    dates, vals = _walk()
    base = dict(BASE, entryZ=2.5, stopZ=2.5)          # 제외 대상 그 칸
    got = M._mr_optimize(dates, vals, base, (-1, 1), span="all")
    assert len(got["cells"]) == _expected_cells(3, base) == 145   # 144 + 내 칸
    cur = [c for c in got["cells"] if c["current"]]
    assert len(cur) == 1
    assert (cur[0]["entryZ"], cur[0]["stopZ"]) == (2.5, 2.5)
    # 그 하나 말고는 제외 규칙이 그대로 지켜진다.
    others = [c for c in got["cells"]
              if mr_mod.grid_excludes(c["entryZ"], c["stopZ"]) and not c["current"]]
    assert others == []


def test_grid_cell_matches_a_standalone_simulate_of_the_same_knobs():
    """격자가 «다른 엔진» 이면 채택 버튼이 거짓말이 된다 — 같은 수인지 잰다.

    고르는 칸은 **프리셋에서 유도한다**. 예전에는 `(120, 2.5, 0.0, 4.0, "touch")`
    라고 적어 뒀는데, 손절 목록이 3.0/3.5/4.0 → 2.5/3.0/3.5 로 바뀌자
    (2026-09-08 오너 결정) 그 칸이 사라져 이 시험이 `StopIteration` 으로 죽었다.
    이 시험이 지키려는 것은 «어느 칸» 이 아니라 «격자 칸 = 낱개 시뮬» 이므로,
    목록의 끝값을 집어 기본 노브와 다른 칸 하나를 만든다.
    """
    from app import main as M
    from app import mr as mr_mod

    ps = mr_mod.STRATEGY_PRESETS
    lb, ez, xz, sz = (int(ps["lookback"][-1]), ps["entryZ"][-1],
                      ps["exitZ"][0], ps["stopZ"][-1])
    dates, vals = _walk()
    got = M._mr_optimize(dates, vals, dict(BASE), (-1, 1), span="1y")
    cell = next(c for c in got["cells"]
                if (c["lookback"], c["entryZ"], c["exitZ"], c["stopZ"],
                    c["entryMode"]) == (lb, ez, xz, sz, "touch"))
    r = bt.simulate(dates, vals, lookback=lb, entry_z=ez, exit_z=xz,
                    stop_z=sz, cost_bp=BASE["costBp"],
                    notional=BASE["notional"], allow_dirs=(-1, 1),
                    entry_mode="touch")
    m = mrm.score(dates, r["points"], r["trades"],
                  mrm.span_start(dates, 12), BASE["costBp"])
    for k in ("totalPnl", "maxDrawdown", "sortino", "calmar", "numTrades"):
        assert cell[k] == m[k], k


def test_the_roll_handoff_does_not_change_a_single_number():
    """`simulate(roll=…)` 는 캐시 손잡이지 산술이 아니다 — 격자의 전제다."""
    dates, vals = _walk(400)
    kw = dict(lookback=60, entry_z=2.0, exit_z=0.5, stop_z=3.5,
              cost_bp=0.5, notional=1_000_000.0)
    a = bt.simulate(dates, vals, **kw)
    b = bt.simulate(dates, vals, roll=bt.rolling_series(vals, 60), **kw)
    assert a["summary"] == b["summary"]
    assert a["trades"] == b["trades"]
    assert a["points"] == b["points"]


def test_grid_refuses_to_run_when_it_would_be_too_big():
    import pytest
    from fastapi import HTTPException

    from app import main as M

    dates, vals = _walk(300)
    # 룩백·진입·청산·손절 넷 다 프리셋 밖이면 4⁴×2 = 512 로 상한에 붙고,
    # 진입 규칙까지 낯설면 그 위다 — 화면에 안 쓰는 계산에 몇 초를 안 쓴다.
    base = dict(BASE, lookback=45, entryZ=1.75, exitZ=0.25, stopZ=3.25,
                entryMode="reentry")
    with pytest.raises(HTTPException) as e:
        M._mr_optimize(dates, vals, base, (-1, 1), span="all")
    assert e.value.status_code == 422


# ── ⑤ 누적 분해 [OWNER 2026-09-09] ─────────────────────────────────────────
#
# 분해가 지켜야 하는 것은 둘이다: **성분의 합이 누적과 같다**(안 같으면 그
# 분해는 거짓이다), 그리고 **없는 성분은 0 이 아니라 None 이다**(0 은 「그날
# 롤다운이 없었다」는 다른 말이고, 화면은 그 0 을 사실로 읽는다).

def _split_points(rows: list[tuple[float, float, float, float, float]],
                  *, real: bool = True) -> list[dict]:
    out = []
    for v, c, rd, f, cost in rows:
        p = {"mtm": v, "barCarry": c, "barCost": cost,
             "dailyPnl": v + c + (rd + f if real else 0.0) + cost}
        if real:
            p["barRolldown"] = rd
            p["barFunding"] = f
        out.append(p)
    return out


def test_split_parts_sum_to_the_cumulative():
    pts = _split_points([(100.0, 10.0, 5.0, -3.0, -2.0),
                         (-40.0, 11.0, 5.0, -3.0, 0.0)])
    s = mrm.split(pts)
    assert s == {"mtm": 60.0, "carry": 21.0, "rolldown": 10.0,
                 "funding": -6.0, "cost": -2.0, "total": 83.0}
    assert s["mtm"] + s["carry"] + s["rolldown"] + s["funding"] + s["cost"] == s["total"]


def test_split_leaves_missing_parts_empty_not_zero():
    s = mrm.split(_split_points([(100.0, 10.0, 0.0, 0.0, -2.0)], real=False))
    assert s["rolldown"] is None and s["funding"] is None
    assert s["mtm"] == 100.0 and s["total"] == 108.0


def test_split_refuses_a_part_that_only_some_bars_have():
    # 통합 장부는 다리 아홉의 봉을 한 통에 모으므로 **섞인 판**이 실제로 생긴다.
    mixed = (_split_points([(1.0, 0.0, 2.0, 0.0, 0.0)])
             + _split_points([(1.0, 0.0, 0.0, 0.0, 0.0)], real=False))
    s = mrm.split(mixed)
    assert s["rolldown"] is None
    assert s["total"] == 4.0


def test_split_closes_on_the_engine_itself():
    # 엔진 근사 판에서도 항등이 선다 — 그때 성분은 셋이다.
    dates = _bizdays(dt.date(2020, 1, 1), 120)
    vals = [100.0 + 5.0 * math.sin(i / 7.0) for i in range(120)]
    r = bt.simulate(dates, vals, lookback=20, entry_z=1.5, exit_z=0.5,
                    stop_z=3.0, cost_bp=0.5, notional=1_000_000.0)
    s = mrm.split(r["points"])
    assert s["rolldown"] is None and s["funding"] is None
    # 성분은 **2자리로 반올림해서** 나간다(화면이 읽는 자리) — 그래서 허용차는
    # 원의 1/100 이다. 1e-6 으로 잡으면 이 시험이 반올림을 잡는 시험이 된다.
    assert abs(s["total"] - r["summary"]["totalPnl"]) < 0.01
    assert abs(s["mtm"] + s["carry"] + s["cost"] - s["total"]) < 0.01


# ── CDaR 은 **창의 봉을 안 잃는다** [전수조사 2026-10-15] ─────────────────────
#
# > (트레이더) "MR에서 MDD 계산하는게 이상하다"
#
# 범인은 MDD 가 아니라 **그것을 쓰는 쪽**이었다. CDaR 비는 `vol_normalize`
# (확장창 `min_obs=60`)를 지나는데, 종전에는 **구간을 먼저 자른 뒤** 그 안에서
# 정규화를 다시 시작했다 — 창의 앞 60봉이 통째로 NaN 이 되어 버려졌다. 1년 창
# 247봉이 **187봉**으로 줄었고, 하필 그 카드의 최대낙폭이 버려진 60봉 안에 있어서
# 「같은 카드가 표본 둘을 말한다」가 됐다(`maxDrawdown` 은 247봉, `cdarRatio` 는
# 187봉). 그 값은 계획면 격자의 **순위 기준**이라 25계열 중 22계열의 1등이 바뀌었다.


class TestCdar창의봉을안잃는다:
    def _daily(self, n: int, seed: int = 11) -> list[float]:
        """잔물결 + 중간에 낙폭 하나 — 결정적이어야 두 번 불러 같은 수가 나온다."""
        out = []
        for i in range(n):
            x = math.sin(i / 7.0) * 1_000_000 + ((i * seed) % 13 - 6) * 50_000
            if 70 <= i < 90:
                x -= 900_000                      # 창 앞머리에 심는 낙폭
            out.append(x)
        return out

    def test_구간을_잘라도_그_구간의_봉을_다_쓴다(self):
        """★이것이 그 결함이다. 창이 247봉이면 CDaR 도 247봉을 본다.

        표본을 400봉으로 두는 이유: 창이 **전 표본의 앞 60봉을 걸치면** 그 봉은
        정말로 못 잰다(확장창이 배수를 못 내놓는다). 그건 결함이 아니라 추정기의
        성질이고, 아래 `test_창이_표본_앞머리를_걸치면` 이 그 경우를 따로 잰다.
        """
        daily = self._daily(400)
        dates = _bizdays(dt.date(2023, 1, 2), 400)
        m = mrm.score(dates, _points(daily), [], 400 - 247, 0.5)
        assert m["days"] == 247
        assert m["cdarBars"] == 247, "창의 봉을 하나도 안 잃는다"

    def test_창이_표본_앞머리를_걸치면_그만큼만_못_잰다(self):
        """창이 첫 60봉에 걸치면 걸친 만큼만 빠진다 — 그리고 **그 사실이 실린다**
        (`cdarBars` ≠ `days`). 종전 결함은 「창을 어디로 잡든 늘 60봉이 사라지는」
        것이었다."""
        m = mrm.score(_bizdays(dt.date(2023, 1, 2), 300),
                      _points(self._daily(300)), [], 53, 0.5)
        assert m["days"] == 247
        assert m["cdarBars"] == 240, "앞 60봉 중 걸친 7봉만 빠진다"

    def test_정규화는_창_앞의_역사를_쓴다(self):
        """같은 창을 두 번 재는데 **앞의 역사만** 다르면 수가 달라야 한다 —
        달라지지 않으면 창 안에서 다시 정규화하고 있다는 뜻이다."""
        win = self._daily(120)
        quiet = [x * 0.05 for x in self._daily(200, seed=5)]
        loud = [x * 5.0 for x in self._daily(200, seed=5)]
        dates = _bizdays(dt.date(2023, 1, 2), 320)
        a = mrm.score(dates, _points(quiet + win), [], 200, 0.5)
        b = mrm.score(dates, _points(loud + win), [], 200, 0.5)
        assert a["cdarBars"] == b["cdarBars"] == 120
        assert a["cdarRatio"] != b["cdarRatio"], \
            "앞의 역사가 배수를 정하므로 수가 달라야 한다(창 안 정규화면 같아진다)"

    def test_못_쟀으면_사유가_구분된다(self):
        """「낙폭이 없어서」와 「봉이 모자라서」는 **다른 사실**이다 — 종전에는
        둘 다 같은 `None` 으로 뭉쳤다."""
        short = mrm.score(_bizdays(dt.date(2024, 1, 1), 30),
                          _points(self._daily(30)), [], 0, 0.5)
        assert short["cdarRatio"] is None
        assert short["cdarWhy"] and "봉" in short["cdarWhy"], short["cdarWhy"]
        # 봉은 넉넉하고 변동도 있는데 **한 번도 물속에 안 간** 계열 — 그때는
        # 「낙폭이 없다」다. 상수 계열로는 못 잰다(분산이 0 이면 배수가 안 선다).
        rise = [100_000.0 + (i % 7) * 10_000 for i in range(200)]
        up = mrm.score(_bizdays(dt.date(2023, 1, 2), 200), _points(rise), [], 0, 0.5)
        assert up["cdarBars"] and up["cdarBars"] > 60
        assert up["cdarRatio"] is None
        assert up["cdarWhy"] and "낙폭" in up["cdarWhy"], up["cdarWhy"]

    def test_비율이_몇_개의_사건_위에_섰나를_싣는다(self):
        """★평가층이 이미 내던 자기 감사를 **버리지 않는다**. CDaR 을 Calmar
        대신 고른 근거가 「MaxDD 는 단일관측 추정량」이라, 사건이 하나면 그 근거가
        그 칸에서 무너진 것이고 그 사실이 보여야 한다. 순위는 안 바꾼다."""
        m = mrm.score(_bizdays(dt.date(2023, 1, 2), 300),
                      _points(self._daily(300)), [], 53, 0.5)
        assert m["cdarTailPoints"] and m["cdarTailPoints"] > 0
        assert m["cdarTailEpisodes"] is not None
        assert m["cdarPointsPerEpisode"] is not None
        assert m["cdarTailPoints"] >= m["cdarTailEpisodes"]
        # ★채택 기준이 Calmar 로 돌아오면서(OWNER 2026-10-15 — PnL·MDD) 창의
        # **낙폭 사건 수**가 그 기준의 분모를 감사하는 수가 된다: MaxDD 는 이
        # N 개 중 가장 깊은 하나다.
        assert m["ddEpisodes"] is not None and m["ddEpisodes"] >= m["cdarTailEpisodes"]

    def test_낙폭_사건_수는_변동성_추정기에_안_걸린다(self):
        """★`maxDrawdown` 이 서는 창이면 그 감사도 서야 한다. 사건 수를 CDaR 의
        `vol_normalize` 뒤에 두면 봉 60개가 안 되는 창에서 **MDD 는 나오는데
        그 분모의 감사는 None** 이 된다 — 실측으로 그 자리를 밟았다."""
        daily = [100.0] * 5 + [-50.0] * 4 + [100.0] * 5          # 14봉
        m = mrm.score(_bizdays(dt.date(2024, 1, 1), 14), _points(daily), [], 0, 0.5)
        assert m["maxDrawdown"] > 0
        assert m["cdarRatio"] is None, "60봉이 안 되면 CDaR 비는 못 선다"
        assert m["ddEpisodes"] == 1, "그래도 사건 수는 선다"

    def test_낙폭_사건_수가_MDD_의_후보_수다(self):
        """물속에 들어가 전고점을 되찾기까지가 한 사건이다. 한 번만 물속에
        들어갔다 나온 계열은 사건 하나 — 그때 MaxDD 는 후보가 하나다."""
        daily = [100.0] * 5 + [-50.0] * 4 + [100.0] * 5    # 물속 한 번
        m = mrm.score(_bizdays(dt.date(2024, 1, 1), 14), _points(daily), [], 0, 0.5)
        assert m["ddEpisodes"] == 1
        twice = [100.0] * 5 + [-50.0] * 4 + [100.0] * 5 + [-60.0] * 4 + [200.0] * 5
        m2 = mrm.score(_bizdays(dt.date(2024, 1, 1), 23), _points(twice), [], 0, 0.5)
        assert m2["ddEpisodes"] == 2


class TestMDD의자는한벌이다:
    """★피크 초기값이 갈려 있었다 [맞춤 2026-10-15] — `mrmetrics` 는 `0.0`,
    `mrbacktest.summarize`·`mrbook._curve` 는 `-inf`. 첫 봉이 손실인 계열에서
    후자는 그 손실을 낙폭에 안 넣어 **MDD 가 |총손익| 보다 작아진다.**"""

    def test_첫_봉이_손실이면_셋이_같은_수를_낸다(self):
        from app import mrbook

        daily = [-30.0, 10.0, -5.0, 20.0]
        pts = [{"dailyPnl": x, "cumulativePnl": sum(daily[: i + 1])}
               for i, x in enumerate(daily)]
        a = bt.summarize(pts, [])["maxDrawdown"]
        b = mrbook._curve(daily)[2]
        c = mrm._drawdowns(daily)[0]
        assert a == b == c == 30.0

    def test_손실_계열에서_MDD_가_총손익보다_작지_않다(self):
        daily = [-10.0] * 20
        pts = [{"dailyPnl": x, "cumulativePnl": sum(daily[: i + 1])}
               for i, x in enumerate(daily)]
        s = bt.summarize(pts, [])
        assert s["maxDrawdown"] >= -s["totalPnl"]
