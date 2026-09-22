# -*- coding: utf-8 -*-
"""근사 최적화 격자는 **의미가 있나** — 표본내 1등이 표본밖에서도 1등인가.

## 왜 이걸 재나

2026-09-07 에 낱개 창과 통합 장부에 162칸 격자가 붙었다. 화면은 「지금 칸이 몇
등인가」를 답하고, 각주가 「1등은 뽑기의 결과이기도 하다」고 적는다. 그런데
**얼마나 뽑기인지는 아무도 안 쟀다.** 안 재면 그 각주는 예의 표시일 뿐이고,
읽는 사람은 결국 1등 칸을 채택한다.

## 어떻게 재나 — 반으로 가른다

표본을 앞뒤 절반으로 갈라

    앞절반에서 162칸을 매긴다  →  그 순위를 **뒤절반**에서 채점한다

세 가지를 답한다:

1. **순위 상관**(스피어만). 0 에 가까우면 앞절반 순위가 뒤절반에 대해 아무 말도
   안 한다 — 그러면 「지금 칸 45등」도 아무 말이 아니다.
2. **앞절반 TOP 5 가 뒤절반에서 중앙값을 이기나.** 이게 채택 버튼의 값어치다.
3. **기본 노브는 어디에 있나.** 1등을 좇는 것과 기본값을 두는 것 중 무엇이 나은가.

## 이 시험이 답하지 않는 것

거래비용·실행가능성은 격자와 같은 가정이다(엔진 근사). 여기서 재는 것은
**「격자의 순위가 정보인가」** 하나이고, 그게 아니라면 나머지 논의가 필요 없다.

돌리기:  python -m scripts.mr_grid_oos            (BSS 통합 장부)
        python -m scripts.mr_grid_oos BSS-3Y    (낱개 계열)
"""

from __future__ import annotations

import statistics as st
import sys

from app import funding, mr as mr_mod, mrbacktest as mrbt, mrbook, mrmetrics as mrm
from app.main import MR_ENTRY_MODES_ALL, _mr_leg


KN = dict(lookback=60, entryZ=2.0, exitZ=0.5, stopZ=3.5, costBp=0.5,
          notional=1_000_000.0, carry=True, entryMode="level", timeStop=0,
          costModel="flat", regime="none", countOpen=False)

#: 순위를 매기는 축. 화면 기본과 같다(Calmar). 축을 바꾸면 결론이 바뀌는지도 본다.
AXES = ("calmar", "sortino", "martin", "totalPnl")


def _legs(spec):
    if len(sys.argv) > 1 and sys.argv[1] != "book":
        return [_mr_leg(sys.argv[1], spec=spec, **KN)]
    out = []
    for sid, _label in mrbook.bss_series():
        try:
            out.append(_mr_leg(sid, spec=spec, **KN))
        except Exception as exc:                               # noqa: BLE001
            print(f"  [빠짐] {sid}: {exc}")
    return out


def _grid(legs, dates, at, half):
    """162칸을 두 반쪽에서 각각 채점한다 — 시뮬은 **전체 위에서 한 번만** 돈다.

    구간을 잘라 다시 돌리면 룩백 워밍업이 없어 뒤절반의 첫 봉들이 못 선다
    (`mrmetrics` 머리의 그 규율). 바뀌는 것은 채점뿐이다.
    """
    opts = {k: list(mr_mod.STRATEGY_PRESETS[k]) for k in ("lookback", "entryZ", "exitZ", "stopZ")}
    cells = []
    for lb in opts["lookback"]:
        lb = int(lb)
        rolls, usable = {}, []
        for leg in legs:
            if lb >= 2 and len(leg["vals"]) >= lb + 1:
                rolls[leg["id"]] = mrbt.rolling_series(leg["vals"], lb)
                usable.append(leg)
        if not usable:
            continue
        for ez in opts["entryZ"]:
            for xz in opts["exitZ"]:
                for sz in opts["stopZ"]:
                    for md in MR_ENTRY_MODES_ALL:
                        daily = [0.0] * len(dates)
                        bcost = [0.0] * len(dates)
                        raw = []
                        for leg in usable:
                            r = mrbt.simulate(
                                leg["dates"], leg["vals"], lookback=lb, entry_z=ez,
                                exit_z=xz, stop_z=sz, cost_bp=KN["costBp"],
                                notional=KN["notional"],
                                allow_dirs=tuple(leg["dirs"]["allowed"]),
                                carry=leg["carryKrw"], entry_mode=md, gate=leg["gate"],
                                time_stop=None, cost_bp_series=leg["costSeries"],
                                close_open_at_end=False,
                                tradable_dv=leg["tradable"], roll=rolls[leg["id"]])
                            for j, pt in enumerate(r["points"]):
                                i = at[leg["dates"][j]]
                                daily[i] += pt["dailyPnl"]
                                bcost[i] += pt["barCost"]
                            raw.extend(r["trades"])
                        pts = [{"dailyPnl": daily[i], "barCost": bcost[i]} for i in range(len(dates))]
                        # 앞절반: 0..half 를 창으로 — `score` 는 start 만 받으므로
                        # 뒤를 잘라 넘긴다. 뒤절반: start=half.
                        a = mrm.score(dates[:half], pts[:half],
                                      [t for t in raw if t["exitDate"] < dates[half]], 0, KN["costBp"])
                        b = mrm.score(dates, pts, raw, half, KN["costBp"])
                        cells.append({
                            "knob": (lb, ez, xz, sz, md),
                            "cur": (lb == KN["lookback"] and ez == KN["entryZ"]
                                    and xz == KN["exitZ"] and sz == KN["stopZ"]
                                    and md == KN["entryMode"]),
                            "in": a, "out": b,
                        })
    return cells


def _spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = st.fmean(rx), st.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return None if den == 0 else num / den


def main() -> int:
    spec = funding.FundingSpec(funding.DEFAULT_BASIS, funding.DEFAULT_SPREAD_BP) \
        if hasattr(funding, "FundingSpec") else funding.spec_for(funding.DEFAULT_BASIS, funding.DEFAULT_SPREAD_BP)
    legs = _legs(spec)
    if not legs:
        print("다리가 하나도 안 섰어요")
        return 1
    dates = sorted({t for leg in legs for t in leg["dates"]})
    at = {t: i for i, t in enumerate(dates)}
    half = len(dates) // 2
    who = sys.argv[1] if len(sys.argv) > 1 else "BSS 통합(9만기)"
    print(f"\n=== {who} · {len(dates)}봉 · 앞절반 {dates[0]}~{dates[half-1]} / "
          f"뒤절반 {dates[half]}~{dates[-1]} ===\n")

    cells = _grid(legs, dates, at, half)
    print(f"칸 {len(cells)}개\n")

    for axis in AXES:
        ok = [c for c in cells if c["in"][axis] is not None and c["out"][axis] is not None]
        if len(ok) < 20:
            print(f"[{axis}] 잴 수 있는 칸이 {len(ok)}개뿐 — 건너뜀")
            continue
        rho = _spearman([c["in"][axis] for c in ok], [c["out"][axis] for c in ok])
        ok.sort(key=lambda c: -c["in"][axis])
        top5 = ok[:5]
        med_out = st.median([c["out"][axis] for c in ok])
        top5_out = st.median([c["out"][axis] for c in top5])
        cur = next((c for c in ok if c["cur"]), None)
        cur_in = ok.index(cur) + 1 if cur else None
        byout = sorted(ok, key=lambda c: -c["out"][axis])
        cur_out = byout.index(cur) + 1 if cur else None
        top5_out_ranks = [byout.index(c) + 1 for c in top5]
        print(f"[{axis}]")
        print(f"  순위 상관(스피어만)      {rho:+.3f}")
        print(f"  앞절반 TOP5 의 뒤절반 값  중앙 {top5_out:+.3f}  대  전체 중앙 {med_out:+.3f}"
              f"   → {'이긴다' if top5_out > med_out else '못 이긴다'}")
        print(f"  앞절반 TOP5 의 뒤절반 등수 {top5_out_ranks}  (/{len(ok)})")
        if cur:
            print(f"  기본 노브                앞절반 {cur_in}등 · 뒤절반 {cur_out}등")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
