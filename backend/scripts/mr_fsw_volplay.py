# -*- coding: utf-8 -*-
"""FSW 변동성 돌파 플레이 — **읽기 전용 측정** [트레이더 피드백 0번, 2026-09-21].

    python -m scripts.mr_fsw_volplay          # backend/ 에서. 표는 stdout + output/*.md

「변동성 국면에서 변동성이 이동평균선을 돌파할 때 일부러 커브를 여는 방식인 FSW 를
활용해서 플레이할 수도 있지 않을까」 — 「커브를 연다」가 세 뜻으로 읽혀 셋을 다 잰다.
화면은 안 바꾼다. 결과 표를 본 뒤 오너가 반영 여부를 정한다.

    ①  MR 을 **돌파 국면에서만** 진입 — `mrbacktest.simulate(gate=…)` (청산·손절은 게이트를
        안 본다는 엔진 규약 그대로). 대조 = 게이트 없음 · 보완(비돌파 국면에서만).
    ②  돌파 때 **벌어지는 방향을 따라가는** 진입(브레이크아웃) — 이 파일의 작은 루프.
        |z| ≥ 2 에서 dir = sign(z), |z| ≤ 0.5 로 되돌아오면 청산, 20봉 타임스탑.
        비용·캐리·롤 마스크는 엔진과 같은 식(`mtm = pos·N·Δ`, `c = −pos·carry`).
    ③  ①②를 **FSW 커브**(FSW-10Y − FSW-3Y, 날짜 교집합)에.

돌파 = 30일 실현변동성(`mrregime.realized_vol`) > 그 변동성의 SMA(60 · 120). 둘 중 하나가
없는 앞머리는 워밍업(진입 불가)이고 「지운 신호」에 안 센다 — 엔진의 `gated` 가 센 것은
게이트가 거짓인 봉의 신호이므로 워밍업도 포함한다는 점을 표가 같이 적는다.

준비는 `scripts/mr_evaluate._leg_inputs` 와 같은 유도(FSW 판): 계열은 `mr.series_points`
(FSW 는 bp 라 환산 없음), 캐리는 CD 91일 − IRS(`mrcarry`), 롤일 Δ 는 0 마스크, 양방향,
편도 0.5bp, 100만원/bp, 데스크 기본 60·2/0.5/2.5·이탈 즉시. FSW 는 `_mr_reconcilable` 로
안 자른다(라우트도 안 자른다). 롤 비용은 **안 물려 있다**(라이브도 그렇다 — `MR_LANE_STATE`).
"""
from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import mr as mr_mod                    # noqa: E402
from app import mrbacktest as bt                # noqa: E402
from app import mrcarry as mrc                  # noqa: E402
from app import mrmetrics as mrm                # noqa: E402
from app import mrregime as mrg                 # noqa: E402
from app import funding as fnd                  # noqa: E402

KNOBS = dict(lookback=60, entry_z=2.0, exit_z=0.5, stop_z=2.5, cost_bp=0.5,
             notional=1_000_000.0)
MA_WINDOWS = (60, 120)
TIME_STOP = 20
OUT = Path(__file__).resolve().parent.parent / "output" / "MR_FSW_VOLPLAY_2026-09-21.md"


def leg_inputs(sid: str) -> dict:
    """(날짜, bp 값, 봉당 캐리 ₩, 거래 가능 Δ, 롤 플래그) — `main._mr_leg` 와 같은 유도."""
    from app.main import _curves
    from app.dv01 import pv01
    from app.curves import TENOR_T

    body = mr_mod.series_points(sid)
    pts = [p for p in body["points"] if p.get("v") is not None]
    scale = 100.0 if body["unit"] == "%" else 1.0
    dates = [p["t"] for p in pts]
    vals = [float(p["v"]) * scale for p in pts]
    flags = [bool(p.get("roll")) for p in pts]
    spec = fnd.FundingSpec(basis=fnd.DEFAULT_BASIS, spread_bp=fnd.DEFAULT_SPREAD_BP)
    rates, _defn = mrc.carry_rates(sid, "fsw", dates, spec)
    pv = pv01(_curves["now"], TENOR_T[mrc._tenor_of(sid)])
    carry = mrc.carry_krw(rates, dates, notional_per_bp=KNOBS["notional"], pv01=pv)
    return {"dates": dates, "vals": vals, "carry": carry, "flags": flags, "spec": spec, "pv": pv}


def curve_inputs(a: dict, b: dict, sid_a: str, sid_b: str) -> dict:
    """FSW 커브 = b − a (10Y − 3Y). 캐리는 교집합 날짜 위에서 다리마다 다시 세워 뺀다."""
    from app.main import _curves
    from app.dv01 import pv01
    from app.curves import TENOR_T

    ia = {t: i for i, t in enumerate(a["dates"])}
    ib = {t: i for i, t in enumerate(b["dates"])}
    dates = [t for t in a["dates"] if t in ib]
    vals = [b["vals"][ib[t]] - a["vals"][ia[t]] for t in dates]
    flags = [a["flags"][ia[t]] or b["flags"][ib[t]] for t in dates]
    carries = []
    for sid, leg in ((sid_a, a), (sid_b, b)):
        rates, _ = mrc.carry_rates(sid, "fsw", dates, leg["spec"])
        pv = pv01(_curves["now"], TENOR_T[mrc._tenor_of(sid)])
        carries.append(mrc.carry_krw(rates, dates, notional_per_bp=KNOBS["notional"], pv01=pv))
    carry = [carries[1][i] - carries[0][i] for i in range(len(dates))]
    return {"dates": dates, "vals": vals, "carry": carry, "flags": flags}


def tradable_of(vals: list[float], flags: list[bool]) -> list[float]:
    return [0.0] + [0.0 if flags[i] else vals[i] - vals[i - 1] for i in range(1, len(vals))]


def gates_of(vals: list[float], n: int) -> tuple[list[bool], list[bool], int]:
    """(돌파 게이트, 보완 게이트, 워밍업 봉 수). 워밍업은 둘 다 거짓."""
    vol = mrg.realized_vol(vals, mrg.VOL_WIN)
    sma: list[float | None] = [None] * len(vals)
    for i in range(len(vals)):
        w = vol[i - n + 1:i + 1] if i - n + 1 >= 0 else []
        if len(w) == n and all(x is not None for x in w):
            sma[i] = sum(w) / n                        # type: ignore[arg-type]
    hot = [vol[i] is not None and sma[i] is not None and vol[i] > sma[i] for i in range(len(vals))]
    cold = [vol[i] is not None and sma[i] is not None and vol[i] <= sma[i] for i in range(len(vals))]
    warm = sum(1 for i in range(len(vals)) if vol[i] is None or sma[i] is None)
    return hot, cold, warm


def breakout(dates, vals, carry, tradable, gate) -> dict:
    """② 돌파 추종 — 엔진의 봉 산술을 그대로 쓴 작은 루프(엔진 파일은 안 건드린다)."""
    N, cost = KNOBS["notional"], KNOBS["notional"] * KNOBS["cost_bp"]
    z = bt.rolling_series(vals, KNOBS["lookback"])["z"]
    points, trades = [], []
    pos, entry_i, tp, cum, gated_days = 0, None, 0.0, 0.0, 0
    for i in range(len(vals)):
        daily, bar_cost, zi = 0.0, 0.0, z[i]
        if pos != 0:
            mtm, c = pos * N * tradable[i], -pos * carry[i]
            daily += mtm + c
            tp += mtm + c
            revert = zi is not None and abs(zi) <= KNOBS["exit_z"]
            timed = (i - entry_i) >= TIME_STOP
            if revert or timed:
                daily -= cost
                tp -= cost
                bar_cost = -cost
                trades.append({"entryDate": dates[entry_i], "exitDate": dates[i],
                               "direction": pos, "pnl": tp,
                               "exitReason": "revert" if revert else "time"})
                pos, entry_i, tp = 0, None, 0.0
        elif zi is not None and abs(zi) >= KNOBS["entry_z"]:
            if gate[i]:
                pos, entry_i = (1 if zi > 0 else -1), i
                daily -= cost
                tp = -cost
                bar_cost = -cost
            else:
                gated_days += 1
        cum += daily
        points.append({"dailyPnl": daily, "barCost": bar_cost, "cumulativePnl": cum,
                       "position": pos})
    return {"points": points, "trades": trades, "gated": {"days": gated_days}}


def sharpe(daily: list[float]) -> float | None:
    if len(daily) < 2:
        return None
    m = sum(daily) / len(daily)
    sd = math.sqrt(sum((x - m) ** 2 for x in daily) / len(daily))
    return None if sd == 0 else m / sd * math.sqrt(252)


def score(dates, r, start, gate, warm) -> dict:
    s = mrm.score(dates, r["points"], r["trades"], start, KNOBS["cost_bp"])
    daily = [p["dailyPnl"] for p in r["points"][start:]]
    live = [g for g in gate[start:]][warm - start if warm > start else 0:] if gate else []
    return {"n": s["numTrades"], "win": s["winRate"], "pnl": s["totalPnl"],
            "mdd": s["maxDrawdown"], "sr": sharpe(daily),
            "cover": (sum(live) / len(live)) if live else None,
            "gated": r["gated"].get("days", 0), "from": s["from"], "to": s["to"]}


def run_series(name: str, leg: dict) -> list[dict]:
    dates, vals, carry = leg["dates"], leg["vals"], leg["carry"]
    tradable = tradable_of(vals, leg["flags"])
    n = len(vals)
    starts = {"전체": 0, "1년": mrm.span_start(dates, 12)}

    def mr(gate):
        return bt.simulate(dates, vals, lookback=KNOBS["lookback"], entry_z=KNOBS["entry_z"],
                           exit_z=KNOBS["exit_z"], stop_z=KNOBS["stop_z"],
                           cost_bp=KNOBS["cost_bp"], notional=KNOBS["notional"],
                           allow_dirs=(-1, 1), gate=gate, carry=carry, tradable_dv=tradable)

    rows = []
    runs = [("① MR 기준(게이트 없음)", "—", mr(None), None, 0),
            ("② 추종(게이트 없음)", "—", breakout(dates, vals, carry, tradable, [True] * n), None, 0)]
    for ma in MA_WINDOWS:
        hot, cold, warm = gates_of(vals, ma)
        runs += [(f"① MR 돌파만", ma, mr(hot), hot, warm),
                 (f"① MR 비돌파만", ma, mr(cold), cold, warm),
                 (f"② 돌파 추종", ma, breakout(dates, vals, carry, tradable, hot), hot, warm)]
    for label, ma, r, gate, warm in runs:
        for win, st in starts.items():
            rows.append({"series": name, "variant": label, "ma": ma, "window": win,
                         **score(dates, r, st, gate, warm)})
    return rows


def fmt(x, kind):
    if x is None:
        return "—"
    if kind == "pct":
        return f"{x * 100:.0f}%"
    if kind == "man":
        return f"{x / 1e4:,.0f}"
    if kind == "r":
        return f"{x:.2f}"
    return str(x)


def table(rows: list[dict]) -> str:
    head = ("| 변형 | MA | 창 | 거래 | 승률 | 총손익(만) | MDD(만) | SR | 게이트 통과율 | 지운 신호(일·전체) |\n"
            "|---|---|---|---|---|---|---|---|---|---|")
    body = [f"| {r['variant']} | {r['ma']} | {r['window']} | {r['n']} | {fmt(r['win'], 'pct')} | "
            f"{fmt(r['pnl'], 'man')} | {fmt(r['mdd'], 'man')} | {fmt(r['sr'], 'r')} | "
            f"{fmt(r['cover'], 'pct')} | {r['gated']} |" for r in rows]
    return "\n".join([head, *body])


def main() -> None:
    try:
        legs = {sid: leg_inputs(sid) for sid in ("FSW-3Y", "FSW-10Y")}
    except Exception as exc:                        # noqa: BLE001
        msg = f"DB 를 못 읽었어요 — 측정 없음: {type(exc).__name__}: {exc}"
        print(msg)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(f"# FSW 변동성 돌파 측정 (2026-09-21)\n\n{msg}\n", encoding="utf-8")
        return
    legs["FSW 커브 (10Y−3Y)"] = curve_inputs(legs["FSW-3Y"], legs["FSW-10Y"], "FSW-3Y", "FSW-10Y")
    out = [f"# FSW 변동성 돌파 플레이 — 측정 (2026-09-21)\n",
           "읽기 전용 측정 · 화면 무변 · 산술은 `scripts/mr_fsw_volplay.py` 머리 주석. "
           f"노브 {KNOBS['lookback']}일 · {KNOBS['entry_z']}/{KNOBS['exit_z']}/{KNOBS['stop_z']}σ · "
           f"편도 {KNOBS['cost_bp']}bp · {KNOBS['notional']:,.0f}₩/bp · 캐리 켬 · 롤일 Δ 마스크 · "
           f"**롤 비용 미반영**. 돌파 = 30일 실현변동성 > 그 SMA(60·120). 추종 청산 = |z|≤0.5 또는 {TIME_STOP}봉.\n"]
    for name, leg in legs.items():
        rows = run_series(name, leg)
        span = f"{leg['dates'][0]} ~ {leg['dates'][-1]} · {len(leg['dates'])}봉 · 1년 창 {rows[1]['from']}~"
        out += [f"\n## {name}\n", span + "\n", table(rows)]
    text = "\n".join(out) + "\n"
    print(text)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
