# -*- coding: utf-8 -*-
"""전략 재현 엔진 — PMS 원본과의 적합성 벡터 + 규칙 의미 핀.

적합성 픽스처는 krw-fi-pms `backtest-kpi-fixture.test.tsx` 의 것 그대로다:
LCG(seed 42) 320일 시리즈에 기본 파라미터를 걸면 KPI 가 정확히 그 숫자여야
한다. **숫자를 다시 뽑아 맞추지 말 것** — 어긋나면 이식이 의미를 바꾼 것이다.
"""
import math

import pytest

from app import mrbacktest as bt

PIN = dict(lookback=60, entry_z=2.0, exit_z=0.5, stop_z=3.5,
           cost_bp=0.05, notional=1_000_000)


def _fixture():
    """원본 fixtureSeries(): LCG seed 42 · 320일 · 사인 + 노이즈 + 점프 둘."""
    s = 42
    vals, dates = [], []
    day0 = 0
    for i in range(320):
        s = (s * 1664525 + 1013904223) % (2 ** 32)
        rand = s / 0xFFFFFFFF - 0.5
        v = 50 + 6 * math.sin(i / 14) + rand * 4
        if 120 <= i < 180:
            v += 9
        if i >= 240:
            v -= 7
        vals.append(round(v * 100) / 100)
        dates.append(f"D{day0 + i:04d}")
    return dates, vals


def test_kpi_conformance_vector_matches_pms():
    dates, vals = _fixture()
    r = bt.simulate(dates, vals, **PIN)
    s = r["summary"]
    # 2026-07-16 캡처(원본 s16 head 2a52654) — 표기 반올림까지 그대로.
    assert round(s["totalPnl"]) == -3_580_000
    assert round(s["maxDrawdown"]) == 18_800_000
    assert round(s["winRate"] * 100) == 33
    assert f"{s['sharpe']:.2f}" == "-0.16"
    assert s["numTrades"] == 3


def test_rule_semantics_pins():
    dates, vals = _fixture()
    r = bt.simulate(dates, vals, **PIN)
    roll = r["roll"]
    # 창 미달·σ=0 → z 없음 (트레일링 포함 창).
    assert all(roll["z"][i] is None for i in range(PIN["lookback"] - 1))
    assert roll["z"][PIN["lookback"] - 1] is not None
    # 진입 봉은 MTM 없이 비용만 — dailyPnl == -notional*costBp.
    by_date = {p["date"]: p for p in r["points"]}
    for t in r["trades"]:
        entry = by_date[t["entryDate"]]
        assert math.isclose(entry["dailyPnl"], -PIN["notional"] * PIN["cost_bp"])
        # 방향은 z 역행 — entryZ 의 부호와 반대.
        assert t["direction"] == (-1 if t["entryZ"] > 0 else 1)
        # 손절은 z-발산: 청산 z 절대값이 stopZ 이상일 때만 "stop".
        if t["exitReason"] == "stop":
            assert abs(t["exitZ"]) >= PIN["stop_z"]
        else:
            assert abs(t["exitZ"]) <= PIN["exit_z"]
    # 누적 = 일별 합 (표본 끝 미청산 MTM 포함).
    assert math.isclose(r["points"][-1]["cumulativePnl"],
                        sum(p["dailyPnl"] for p in r["points"]))


def test_population_std_not_sample():
    # 모집단 σ — 표본 σ(ddof=1)와 다르다. 원본 pstdev 의 핀.
    vals = [1.0, 2.0, 3.0, 4.0]
    roll = bt.rolling_series(vals, 4)
    assert math.isclose(roll["std"][3], math.sqrt(5.0 / 4.0))


def test_no_reentry_on_exit_bar():
    # 청산 봉의 else-if 는 건너뛴다 — 같은 봉 재진입 금지. z 가 계속 진입권이어도
    # 다음 봉에야 다시 들어간다. 합성: 창 2, 진입 후 즉시 청산이 반복되는 계열.
    dates = [f"D{i}" for i in range(8)]
    vals = [0.0, 10.0, 0.0, 10.0, 0.0, 10.0, 0.0, 10.0]
    r = bt.simulate(dates, vals, lookback=2, entry_z=0.9, exit_z=0.95,
                    stop_z=99.0, cost_bp=0.0, notional=1.0)
    for a, b in zip(r["trades"], r["trades"][1:]):
        assert b["entryDate"] > a["exitDate"]


def test_allow_dirs_blocks_one_side_without_touching_the_other():
    """한 방향을 막으면 그 진입만 사라진다 [OWNER 2026-08-25 — "BSS에서 숏은
    없는거야,, 현물대차매도는 안할거거든"].

    막힌 봉은 **거래도 비용도 아니다** — 못 한 거래에 비용을 물리면 그 자리에서
    안 한 거래가 손실이 된다. 그리고 남은 방향의 거래는 양방향 실행의 그것과
    글자 하나 다르지 않아야 한다(진입 규칙은 레벨 검사라 서로를 안 본다).
    """
    dates, vals = _fixture()
    both = bt.simulate(dates, vals, **PIN)
    only_short = bt.simulate(dates, vals, **PIN, allow_dirs=(-1,))

    assert both["blocked"] == {"spells": 0, "days": 0}
    assert all(t["direction"] == -1 for t in only_short["trades"])
    kept = [t for t in both["trades"] if t["direction"] == -1]
    assert [t["entryDate"] for t in only_short["trades"]] == [t["entryDate"] for t in kept]
    assert [round(t["pnl"], 6) for t in only_short["trades"]] == [round(t["pnl"], 6) for t in kept]
    # 막힌 쪽이 실제로 있었다 — 없으면 이 시험이 아무것도 안 잰다.
    assert any(t["direction"] == 1 for t in both["trades"])
    assert only_short["blocked"]["spells"] >= 1
    assert only_short["blocked"]["days"] >= only_short["blocked"]["spells"]

    # 막힌 봉의 손익은 0 이다(무포지션 · 비용 없음).
    dir_by_entry = {t["entryDate"]: t["direction"] for t in both["trades"]}
    blocked_dates = [d for d, v in dir_by_entry.items() if v == 1]
    by_date = {p["date"]: p for p in only_short["points"]}
    for d in blocked_dates:
        assert by_date[d]["position"] == 0
        assert by_date[d]["dailyPnl"] == 0.0


def test_blocked_spell_counts_runs_not_bars():
    """열흘 내리 막힌 것은 열 번 못 들어간 게 아니라 한 번이다."""
    dates = [f"D{i}" for i in range(12)]
    # 창 2 의 단조 상승 — 두 값의 창이라 z 는 매 봉 정확히 +1 이고(진입권),
    # 그 방향(숏)이 막혀 있으니 한 구간이 열한 봉 내리 이어진다.
    vals = [float(i) for i in range(12)]
    r = bt.simulate(dates, vals, lookback=2, entry_z=0.5, exit_z=0.1,
                    stop_z=99.0, cost_bp=0.0, notional=1.0, allow_dirs=(1,))
    assert r["trades"] == []
    assert r["blocked"] == {"spells": 1, "days": 11}


def test_breakeven_cost_is_exact_not_approximate():
    """손익분기 비용은 닫힌형이다 — 그 값으로 다시 돌리면 총손익이 0 이어야 한다.

    거래 목록이 z 에만 달려 있어 비용을 바꿔도 안 변한다는 사실이 이 닫힌형의
    전제다. 그 전제까지 같이 잰다(거래 수·진입일이 그대로여야 한다).
    """
    dates, vals = _fixture()
    base = dict(PIN, cost_bp=0.5)
    r = bt.simulate(dates, vals, **base)
    be = r["summary"]["breakevenCostBp"]
    assert be is not None

    again = bt.simulate(dates, vals, **dict(base, cost_bp=be))
    assert abs(again["summary"]["totalPnl"]) < 1e-6
    # 전제: 비용은 거래를 안 바꾼다
    assert again["summary"]["numTrades"] == r["summary"]["numTrades"]
    assert [t["entryDate"] for t in again["trades"]] == [t["entryDate"] for t in r["trades"]]


def test_open_leg_is_reported_but_not_counted():
    """미청산 다리는 밖으로 나오되 거래·승률·건수에는 안 들어간다(원본 규약).

    누적에는 있으므로 «총손익 − 거래 손익 합» 이 곧 그 다리의 MTM 이다 — 화면이
    승률 옆에 이 수를 적을 수 있어야 80% 가 무슨 뜻인지 읽힌다.
    """
    dates, vals = _fixture()
    # 마지막 봉이 진입 문턱 밖이 되도록 꼬리를 밀어 미청산 상태로 끝낸다.
    vals = list(vals) + [vals[-1] - 8.0]
    dates = list(dates) + ["D0320"]
    r = bt.simulate(dates, vals, **PIN)

    assert r["open"] is not None
    assert r["points"][-1]["position"] != 0
    assert r["open"]["entryDate"] == dates[r["open"]["bars"] * -1 - 1]

    closed = sum(t["pnl"] for t in r["trades"])
    assert math.isclose(r["summary"]["openPnl"], r["summary"]["totalPnl"] - closed, abs_tol=1e-6)
    assert r["summary"]["numTrades"] == len(r["trades"])
    # 규약 유지 — 승률의 분모는 청산된 거래뿐이다
    wins = sum(1 for t in r["trades"] if t["pnl"] > 0)
    assert math.isclose(r["summary"]["winRate"], wins / len(r["trades"]))


def test_open_leg_is_none_when_flat_at_end():
    dates, vals = _fixture()
    r = bt.simulate(dates, vals, **PIN)
    if r["points"][-1]["position"] == 0:
        assert r["open"] is None
        assert r["summary"]["openPnl"] is None


# ── gate — 「조건이 맞을 때만 진입」의 배관 ────────────────────────────────
#
# 조건이 **무엇인가** 는 여기 없다(그건 오너가 정한다). 여기 있는 것은 조건이
# 무엇이든 지켜져야 하는 성질뿐이다.

def test_gate_none_and_gate_all_true_are_the_same_run():
    """게이트를 안 걸면 예전 수 그대로 — 배관이 산술을 안 건드렸다는 핀."""
    dates, vals = _fixture()
    base = bt.simulate(dates, vals, **PIN)
    allon = bt.simulate(dates, vals, **PIN, gate=[True] * len(vals))
    assert base["summary"] == allon["summary"]
    assert [t["entryDate"] for t in base["trades"]] == [t["entryDate"] for t in allon["trades"]]
    assert base["gated"] == {"spells": 0, "days": 0}


def test_gate_all_false_trades_nothing_and_counts_every_lost_signal():
    dates, vals = _fixture()
    base = bt.simulate(dates, vals, **PIN)
    off = bt.simulate(dates, vals, **PIN, gate=[False] * len(vals))
    assert off["trades"] == []
    assert off["summary"]["totalPnl"] == 0.0
    # 지워진 신호가 조용히 사라지지 않는다 — 최소한 원래 거래 수만큼은 세어야 한다
    assert off["gated"]["spells"] >= len(base["trades"])
    assert off["gated"]["days"] >= off["gated"]["spells"]


def test_gate_does_not_hold_a_position_hostage():
    """**안전 규칙**: 게이트는 진입에만 듣는다.

    나가는 문까지 조건을 달면 조건이 꺼진 동안 포지션이 갇히고 보유기간이
    규칙이 아니라 지표의 부산물이 된다. 진입 봉에서만 참인 게이트를 걸어도
    거래는 원래 규칙대로 **끝나야** 한다.
    """
    dates, vals = _fixture()
    base = bt.simulate(dates, vals, **PIN)
    first = base["trades"][0]
    at = {d: i for i, d in enumerate(dates)}
    g = [False] * len(vals)
    g[at[first["entryDate"]]] = True          # 그 한 봉에서만 진입 허용

    r = bt.simulate(dates, vals, **PIN, gate=g)
    assert len(r["trades"]) == 1
    got = r["trades"][0]
    assert got["entryDate"] == first["entryDate"]
    # 청산일·사유·손익이 게이트 없는 판과 같아야 한다 — 나가는 규칙은 안 바뀌었다
    assert got["exitDate"] == first["exitDate"]
    assert got["exitReason"] == first["exitReason"]
    assert math.isclose(got["pnl"], first["pnl"])


def test_gate_warmup_none_counts_as_blocked_not_as_permission():
    """지표가 아직 못 서는 봉(None)은 «조건이 맞았다» 가 아니다."""
    dates, vals = _fixture()
    g = [None] * len(vals)
    r = bt.simulate(dates, vals, **PIN, gate=g)
    assert r["trades"] == []
    assert r["gated"]["spells"] >= 1


def test_direction_is_counted_before_the_gate():
    """실행 불가능한 신호를 게이트의 공으로 돌리지 않는다.

    한 방향만 허용하고 게이트를 전부 끄면, 막힌 방향의 신호는 `blocked` 로만
    가고 `gated` 로 이중 계상되지 않아야 한다.
    """
    dates, vals = _fixture()
    both = bt.simulate(dates, vals, **PIN)
    short_only_open = bt.simulate(dates, vals, **PIN, allow_dirs=(-1,))
    r = bt.simulate(dates, vals, **PIN, allow_dirs=(-1,), gate=[False] * len(vals))

    # 방향 카운트는 게이트 유무와 무관하다
    assert r["blocked"] == short_only_open["blocked"]
    # 게이트는 «할 수 있었는데 안 한» 것만 센다
    assert r["gated"]["days"] + r["blocked"]["days"] >= len(both["trades"])
    assert r["trades"] == []


def test_gated_spell_counts_runs_not_bars():
    """열흘 내리 막힌 것은 열 번이 아니라 한 번 못 들어간 것이다(blocked 와 같은 규율)."""
    dates, vals = _fixture()
    # 문턱을 낮춰 신호가 여러 봉 **연달아** 나게 한다 — 그 연속이 한 구간이다.
    r = bt.simulate(dates, vals, lookback=60, entry_z=0.5, exit_z=0.1, stop_z=99.0,
                    cost_bp=0.0, notional=1_000_000, gate=[False] * len(vals))
    assert r["trades"] == []
    assert r["gated"]["spells"] >= 1
    assert r["gated"]["days"] > r["gated"]["spells"], "연속 봉이 한 구간으로 묶여야 한다"


# ── 진입 규칙 둘 [OWNER 2026-08-28 — "진입 기준이 외부로 이탈했다가 다시 그
#    선을 터치할 때"] ────────────────────────────────────────────────────────


def _excursion():
    """밴드를 뚫고 나갔다가 되돌아오는 계열 하나.

    잔잔한 40봉 → 이탈 두 봉(D40·D41) → 복귀(D42~). `level` 은 뚫는 봉 D40 에,
    `touch` 는 복귀 봉 D42 에 들어가야 한다. 이탈이 트레일링 창에 들어가면서
    σ 가 커져 복귀 뒤 곧 청산되므로, 두 판 다 **닫힌 거래**로 끝난다.
    """
    vals = [10.0 + (0.1 if i % 2 else 0.0) for i in range(40)]
    vals += [12.0, 12.0]
    vals += [10.05] * 18
    return [f"D{i:02d}" for i in range(len(vals))], vals


_EXC = dict(lookback=20, entry_z=1.5, exit_z=0.5, stop_z=99.0,
            cost_bp=0.0, notional=1.0)


def test_touch_enters_on_the_return_bar_not_the_piercing_bar():
    dates, vals = _excursion()
    lvl = bt.simulate(dates, vals, **_EXC, entry_mode="level")
    tch = bt.simulate(dates, vals, **_EXC, entry_mode="touch")
    assert [t["entryDate"] for t in lvl["trades"]] == ["D40"]
    assert [t["entryDate"] for t in tch["trades"]] == ["D42"]
    # 뚫는 봉은 밴드 **밖**, 복귀 봉은 **안**이다.
    assert abs(lvl["trades"][0]["entryZ"]) >= _EXC["entry_z"]
    assert abs(tch["trades"][0]["entryZ"]) < _EXC["entry_z"]


def test_touch_direction_comes_from_the_side_it_left_not_the_return_bar():
    """복귀 봉의 z 부호가 반대여도 방향은 **나갔던 쪽**이 정한다.

    이 픽스처의 복귀 봉 z 는 −0.34 다(중심선을 지나쳐 내려왔다). 그 부호를
    쓰면 「비싼 것을 샀다」가 되어 규칙이 정확히 뒤집힌다.
    """
    dates, vals = _excursion()
    t = bt.simulate(dates, vals, **_EXC, entry_mode="touch")["trades"][0]
    assert t["entryZ"] < 0 and t["peakZ"] > 0
    assert t["direction"] == -1


def test_touch_carries_the_excursion_it_entered_on():
    dates, vals = _excursion()
    t = bt.simulate(dates, vals, **_EXC, entry_mode="touch")["trades"][0]
    assert (t["outFrom"], t["outDays"]) == ("D40", 2)
    assert abs(t["peakZ"]) >= _EXC["entry_z"]


def test_level_out_days_is_one_because_entry_is_the_first_bar_outside():
    dates, vals = _excursion()
    t = bt.simulate(dates, vals, **_EXC, entry_mode="level")["trades"][0]
    assert (t["outFrom"], t["outDays"]) == (t["entryDate"], 1)


def test_default_entry_mode_is_the_original_rule():
    """인자를 안 주면 예전 호출과 **같은 객체**가 나온다 — 적합성 벡터의 짝."""
    dates, vals = _fixture()
    assert bt.simulate(dates, vals, **PIN) == bt.simulate(dates, vals, **PIN,
                                                          entry_mode="level")


def test_unknown_entry_mode_is_refused_not_silently_defaulted():
    dates, vals = _fixture()
    try:
        bt.simulate(dates, vals, **PIN, entry_mode="reentry")
    except ValueError as e:
        assert "level" in str(e) and "touch" in str(e)
    else:
        raise AssertionError("모르는 모드를 조용히 기본값으로 삼았다")


# ── `hold` — 대사표가 곱셈을 눈으로 닫게 하는 값 [OWNER 2026-08-28] ─────────


def test_hold_is_the_position_that_multiplied_the_move():
    """봉마다 `mtm == hold × 명목 × Δ값` 이 **정확히** 성립한다.

    끝난 뒤의 `position` 으로는 안 닫힌다 — 진입 봉(mtm 0 인데 position ±1)과
    청산 봉(mtm ≠ 0 인데 position 0)에서 어긋난다. 대사표가 그 값을 실으면
    「감도 × 변화 = 평가」가 한 줄 안에서 거짓이 된다.
    """
    dates, vals = _fixture()
    r = bt.simulate(dates, vals, **PIN)
    pts = r["points"]
    mismatched_with_position = 0
    for i, p in enumerate(pts):
        move = 0.0 if i == 0 else vals[i] - vals[i - 1]
        assert math.isclose(p["mtm"], p["hold"] * PIN["notional"] * move,
                            abs_tol=1e-6)
        if not math.isclose(p["mtm"], p["position"] * PIN["notional"] * move,
                            abs_tol=1e-6):
            mismatched_with_position += 1
    # 진입 봉·청산 봉이 실제로 어긋난다 — 이 테스트가 tautology 가 아님을 잰다.
    assert mismatched_with_position >= 2 * len(r["trades"])


def test_trade_running_total_closes_on_the_exit_bar():
    """거래 안 누적(`tradePnl`)의 마지막 줄 = 그 거래의 손익.

    대사표의 **세로합**이 이 값이다. 표가 「합계」 줄에서 스스로 맞는지 보이려면
    줄마다의 누적이 있어야 하고, 그 마지막이 거래 손익과 다르면 표가 거짓이다.
    """
    dates, vals = _fixture()
    r = bt.simulate(dates, vals, **PIN)
    by_date = {p["date"]: p for p in r["points"]}
    assert r["trades"]
    for t in r["trades"]:
        assert math.isclose(by_date[t["exitDate"]]["tradePnl"], t["pnl"], abs_tol=1e-6)
    # 무포지션 봉은 0 이다 — 지난 거래의 잔상이 남지 않는다.
    flat = [p for p in r["points"] if p["position"] == 0 and p["hold"] == 0]
    assert flat and all(p["tradePnl"] == 0.0 for p in flat)


def test_out_run_counts_consecutive_bars_outside_the_band():
    dates, vals = _excursion()
    r = bt.simulate(dates, vals, **_EXC)
    by_date = {p["date"]: p for p in r["points"]}
    assert (by_date["D40"]["out"], by_date["D40"]["outRun"]) == (1, 1)
    assert (by_date["D41"]["out"], by_date["D41"]["outRun"]) == (1, 2)
    # 복귀 봉은 밖이 아니다 — 세는 것도 끊긴다.
    assert (by_date["D42"]["out"], by_date["D42"]["outRun"]) == (0, 0)


# ── 실전 손잡이 넷 [OWNER 2026-08-28 — 실전 운용 재설계] ────────────────────


def test_time_stop_closes_at_exactly_n_bars_and_says_so():
    """진입 후 N봉이면 손익 불문 나온다 — 그리고 사유가 「time」이다.

    픽스처의 기본 판은 19·40·45봉을 들고 있다. 20봉 타임스탑을 걸면 19봉짜리는
    그대로고 나머지 둘이 잘려야 한다.
    """
    dates, vals = _fixture()
    base = bt.simulate(dates, vals, **PIN)
    assert [t["bars"] for t in base["trades"]] == [19, 40, 45]
    r = bt.simulate(dates, vals, **PIN, time_stop=20)
    assert all(t["bars"] <= 20 for t in r["trades"])
    cut = [t for t in r["trades"] if t["exitReason"] == "time"]
    assert cut and all(t["bars"] == 20 for t in cut)
    # 19봉짜리는 원래대로 청산이다 — 타임스탑이 남의 사유를 뺏지 않는다.
    assert r["trades"][0]["bars"] == 19 and r["trades"][0]["exitReason"] == "exit"


def test_time_stop_does_not_steal_the_name_from_a_real_exit():
    """같은 봉에 청산 조건도 참이면 이름은 「청산」이다(우선순위 핀)."""
    dates, vals = _fixture()
    r = bt.simulate(dates, vals, **PIN, time_stop=19)
    first = r["trades"][0]
    assert first["bars"] == 19 and abs(first["exitZ"]) <= PIN["exit_z"]
    assert first["exitReason"] == "exit"


def test_time_stop_fires_even_where_the_indicator_is_blank():
    """z 가 없는 봉에서도 시간은 흐른다 — 지표가 비어도 갇히지 않는다.

    창이 찬 뒤 값이 완전히 평평해지면 σ=0 이라 z 가 사라지고, 청산·손절은 둘 다
    z 를 보므로 그 구간에서는 **어떤 문도 열리지 않는다**. 타임스탑만 열린다.
    """
    # ⚠ **단조 증가**여야 한다 [수리 2026-09-22]. 종전 파형(0,1,0,1,…)은 진입
    #   다음 봉에서 z 가 +1 → −1 로 뒤집혀서, 방향 청산 규칙에서는 거기서 나온다
    #   (숏은 z ≤ exitZ 에서 나간다). 그러면 이 시험이 재려던 «z 가 빈 구간» 에
    #   애초에 도달하지 않는다. 오르는 파형이면 숏이 z=+1 로 버티다 평평해진다.
    vals = [0.0, 1.0, 2.0, 3.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0]
    dates = [f"D{i:02d}" for i in range(len(vals))]
    kw = dict(lookback=2, entry_z=1.0, exit_z=0.5, stop_z=99.0,
              cost_bp=0.0, notional=1.0)
    stuck = bt.simulate(dates, vals, **kw)
    assert stuck["trades"] == [] and stuck["open"]["entryDate"] == "D01"
    assert all(z is None for z in stuck["roll"]["z"][5:]), "블랭크 구간의 전제"

    r = bt.simulate(dates, vals, **kw, time_stop=8)
    assert r["open"] is None
    assert [(t["exitDate"], t["bars"], t["exitReason"]) for t in r["trades"]]         == [("D09", 8, "time")]


def test_cost_series_beats_the_scalar_and_is_read_at_each_bar():
    """비용은 **그 봉의** 값으로 문다 — 진입 봉과 청산 봉이 다를 수 있다."""
    dates, vals = _fixture()
    flat = [0.05] * len(dates)
    same = bt.simulate(dates, vals, **PIN, cost_bp_series=flat)
    assert round(same["summary"]["totalPnl"]) == round(
        bt.simulate(dates, vals, **PIN)["summary"]["totalPnl"])
    # 진입 봉만 비싸게 매기면 그 차액만큼 정확히 줄어든다.
    spiky = list(flat)
    entries = {t["entryDate"] for t in same["trades"]}
    idx = {d: i for i, d in enumerate(dates)}
    for d in entries:
        spiky[idx[d]] = 0.25
    r = bt.simulate(dates, vals, **PIN, cost_bp_series=spiky)
    lost = (0.25 - 0.05) * PIN["notional"] * len(entries)
    assert math.isclose(same["summary"]["totalPnl"] - r["summary"]["totalPnl"],
                        lost, abs_tol=1e-6)


def test_breakeven_multiple_is_exact_for_a_cost_path():
    """경로를 그 배수만큼 키우면 총손익이 정확히 0 이 된다."""
    dates, vals = _fixture()
    path = [0.02 + 0.0001 * i for i in range(len(dates))]
    r = bt.simulate(dates, vals, **PIN, cost_bp_series=path)
    m = r["summary"]["breakevenCostMult"]
    assert m is not None
    scaled = bt.simulate(dates, vals, **PIN, cost_bp_series=[c * m for c in path])
    assert abs(scaled["summary"]["totalPnl"]) < 1e-6 * PIN["notional"]


def test_blocked_direction_never_becomes_a_trade():
    """막힌 방향의 신호는 **거래가 되지 않는다** — 세어서 돌려줄 뿐이다.

    종전 이름은 「반대 방향 신호는 나가는 문일 뿐」이었고 `reverse_exit=True` 를
    같이 넘겼다. 그 문은 2026-09-23 에 엔진에서 빠졌지만(도달 불가) **이 시험이
    재던 것은 그 문이 아니라 `allow_dirs` 였다** — 현물 대차매도가 안 되는
    데스크에서 +1 다리가 조용히 열리면 백테스트가 대차료 0 으로 늘 이긴다.
    """
    dates, vals = _fixture()
    r = bt.simulate(dates, vals, **PIN, allow_dirs=(-1,))
    assert r["trades"], "거래가 있어야 검정이 성립한다"
    assert all(t["direction"] == -1 for t in r["trades"])
    if r["open"]:
        assert r["open"]["direction"] == -1


def test_there_is_no_reverse_exit_door():
    """★역신호 문은 **지웠다** [OWNER 2026-09-23] — 도달할 수가 없어서다.

    2026-09-22 에 청산을 **교차**로 고친 뒤(`z ≥ −exitZ` / `z ≤ exitZ`) 반대
    밴드에 닿으려면 먼저 청산선을 지나야 하고, 문의 우선순위가 손절 > 청산 >
    역신호라 **청산이 항상 먼저 이름을 갖는다.**

    프리셋 탓이 아니다 — `main._mr_check_knobs` 가 `0 ≤ exitZ` 를 강제하므로
    도달에 필요한 `exitZ < 0` 은 **모든 경로에서 422** 다. 그래서 지웠다.

    이 시험이 지키는 것 둘: 엔진이 그 인자를 더는 받지 않는다는 것과, 그 자리의
    봉이 「역신호」가 아니라 **「청산」으로** 이름을 갖는다는 것이다.
    """
    vals = ([10.0 + (0.1 if i % 2 else 0.0) for i in range(40)]
            + [12.0, 11.5, 11.0, 10.5, 10.2, 7.0])
    dates = [f"D{i:02d}" for i in range(len(vals))]
    kw = dict(lookback=20, entry_z=1.5, exit_z=0.0, stop_z=99.0,
              cost_bp=0.0, notional=1.0)
    r = bt.simulate(dates, vals, **kw)
    assert all(t["exitReason"] != "reverse" for t in r["trades"]), (
        "「역신호」는 어휘에서 빠졌다")
    assert any(t["exitReason"] == "exit" for t in r["trades"]), "청산문은 열려야 한다"
    # 그리고 **그 청산은 중심선을 지난 봉**이다 — exitZ=0 의 뜻이 그것이다
    # [OWNER 2026-09-22 "0 sigma를 뚫고가면 청산하겠다는거야"].
    got = [t for t in r["trades"] if t["exitReason"] == "exit"][0]
    assert got["direction"] == -1 and got["exitZ"] is not None and got["exitZ"] <= 0.0
    # 인자 자체가 없다 — 남아 있으면 「껐다 켰다」 할 수 있다는 뜻이 된다.
    with pytest.raises(TypeError):
        bt.simulate(dates, vals, **kw, reverse_exit=True)  # type: ignore[call-arg]

def test_open_leg_can_be_counted_as_a_trade_without_paying_an_exit():
    """미청산을 거래로 세면 승률·거래 수·보유기간이 달라지고, 총손익은 안 바뀐다.

    팔지 않았으니 청산 비용은 없다 — 없는 비용을 물리면 그건 다른 전략이다.
    """
    dates, vals = _fixture()
    base = bt.simulate(dates, vals, **PIN)
    r = bt.simulate(dates, vals, **PIN, close_open_at_end=True)
    assert base["open"] is not None
    assert r["summary"]["numTrades"] == base["summary"]["numTrades"] + 1
    # 총손익·낙폭은 원래부터 미청산을 지고 있었다 — 여기서 바뀌면 이중 계상이다.
    assert math.isclose(r["summary"]["totalPnl"], base["summary"]["totalPnl"])
    assert math.isclose(r["summary"]["maxDrawdown"], base["summary"]["maxDrawdown"])
    added = r["trades"][-1]
    assert added["exitReason"] == "open"
    assert math.isclose(added["pnl"], base["open"]["pnl"])
    assert math.isclose(added["cost"], base["open"]["cost"])  # 진입 편도 하나뿐


class TestTradableDvMask:
    """롤일 Δ 마스크 [OWNER 2026-09-02 — "롤일 Δ 를 0 으로 마스크"].

    선물·퓨처스왑의 값은 벤더 내재수익률이라 **수준**은 옳지만, 계약이 갈리는
    날의 차분은 앞 계약 마지막과 뒷 계약 첫 값을 뺀 것이라 아무도 실현하지
    못한다. 마스크는 그 봉의 Δ 만 0 으로 만들고 **수준·z·신호는 안 건드린다**.
    """

    @staticmethod
    def _wave(n: int = 120) -> list[float]:
        import math as _m
        return [10.0 + 3.0 * _m.sin(i / 6.0) for i in range(n)]

    def test_none_is_the_old_arithmetic(self):
        """안 주면 예전과 **완전히 같은 수** — 원본 PMS 재현이 안 깨진다."""
        vals = self._wave()
        dates = [f"2020-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(len(vals))]
        a = bt.simulate(dates, vals, lookback=20, entry_z=1.0, exit_z=0.2,
                                stop_z=4.0, cost_bp=0.0, notional=1.0)
        b = bt.simulate(dates, vals, lookback=20, entry_z=1.0, exit_z=0.2,
                                stop_z=4.0, cost_bp=0.0, notional=1.0,
                                tradable_dv=None)
        assert a["trades"] == b["trades"]
        assert a["summary"] == b["summary"]

    def test_masked_bar_pays_nothing_and_the_trade_says_so(self):
        vals = self._wave()
        dates = [f"2020-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(len(vals))]
        plain = [0.0] + [vals[i] - vals[i - 1] for i in range(1, len(vals))]
        a = bt.simulate(dates, vals, lookback=20, entry_z=1.0, exit_z=0.2,
                                stop_z=4.0, cost_bp=0.0, notional=1.0)
        # 한 봉만 마스크한다 — **어떤 거래의 보유 구간 안**을 고른다(밖을 고르면
        # 아무 거래도 안 갈리고 이 시험은 아무것도 안 잰다).
        first = a["trades"][0]
        cut = dates.index(first["entryDate"]) + 1
        assert cut <= dates.index(first["exitDate"])
        masked = list(plain)
        masked[cut] = 0.0
        b = bt.simulate(dates, vals, lookback=20, entry_z=1.0, exit_z=0.2,
                                stop_z=4.0, cost_bp=0.0, notional=1.0,
                                tradable_dv=masked)

        # 신호는 값 위에서 나므로 거래의 **날짜와 방향**은 안 바뀐다.
        assert [(t["entryDate"], t["exitDate"], t["direction"]) for t in a["trades"]] == \
               [(t["entryDate"], t["exitDate"], t["direction"]) for t in b["trades"]]

        # 그 봉을 지나는 거래는 정확히 그 봉의 Δ 만큼 갈린다.
        gap = plain[cut]
        touched = 0
        for x, y in zip(a["trades"], b["trades"]):
            if x["masked"] == 0 and y["masked"] == 0:
                assert x == y
                continue
            touched += 1
            assert y["masked"] == 1
            assert math.isclose(y["dv"], x["dv"] - gap, abs_tol=1e-9)
            # 수준은 안 건드린다 — 진입·청산 값은 그대로다.
            assert (y["entryValue"], y["exitValue"]) == (x["entryValue"], x["exitValue"])
        assert touched == 1

    def test_length_must_match(self):
        vals = self._wave(40)
        dates = [f"2020-01-{1 + i:02d}" for i in range(len(vals))]
        with pytest.raises(ValueError, match="tradable_dv"):
            bt.simulate(dates, vals, lookback=10, entry_z=1.0, exit_z=0.2,
                                stop_z=4.0, cost_bp=0.0, notional=1.0,
                                tradable_dv=[0.0] * (len(vals) - 1))
