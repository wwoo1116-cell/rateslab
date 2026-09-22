# -*- coding: utf-8 -*-
"""BSS 실전 재설계 — 리포트 [OWNER 2026-08-28].

`mr_live_wfo.py` 의 기계를 돌려 표를 찍는다. 계산은 저쪽, 배열은 이쪽이다.

    python backend/scripts/mr_live_report.py            # 3Y 헤드라인 전부
    python backend/scripts/mr_live_report.py --all      # + 전 만기 9개
"""
from __future__ import annotations

import math
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mr_live_wfo as W  # noqa: E402

# ── 표본 길이 [OWNER 2026-08-28 — "더 길게 보지 뭐"] ───────────────────────
# `--long` 이면 `imx_data.timeseries`(2014-06~) 를 쓴다. 화면 출처는 2020-01~
# 이라 6.7년밖에 안 되고, 그 길이로는 다중검정 문턱을 못 넘는다. 겹치는 1,633일
# 에서 두 출처가 같은 계열임을 확인했으므로(`W.overlap_check`) **전 기간을 한
# 출처로** 쓴다 — 이음매를 만들면 그 자리에서 수준이 튀고 그것이 신호로 잡힌다.
LONG = "--long" in sys.argv


def load(sid: str) -> dict:
    return W.load_long(sid) if LONG else W.load(sid)


def oos_window(n: int) -> tuple[int, int]:
    """폴드를 굴리지 않고 창만 — 격자 탐색이 필요 없는 자리에서 쓴다."""
    lo, hi = 0, n
    while lo + W.TRAIN + 1 <= n:
        a = lo + W.TRAIN
        b = min(a + W.TEST, n)
        if b - a < 20:
            break
        hi = b
        lo += W.TEST
    return W.TRAIN, hi

BSS = ["BSS-6M", "BSS-9M", "BSS-1Y", "BSS-1.5Y", "BSS-2Y", "BSS-3Y",
       "BSS-5Y", "BSS-7Y", "BSS-10Y"]
# 화면 기본 = 원본 PMS s16. 「고르지 않은」 판의 파라미터다.
LEGACY = {"lookback": 60, "entryZ": 2.0, "exitZ": 0.5}
HEAD = (f"{'':<26}{'총손익':>12}{'MDD':>11}{'SR':>7}{'거래':>5}"
        f"{'승률':>7}{'보유':>8}{'익스':>7}")


def fm(s: dict | None) -> str:
    if s is None:
        return " " * 26 + "—"
    sr = s["sharpe"]
    wr = s["winRate"]
    return (f"{s['totalPnl']/1e4:>9,.0f}만 {s['maxDrawdown']/1e4:>8,.0f}만 "
            f"{(sr if sr is not None else float('nan')):>6.2f} {s['numTrades']:>4} "
            f"{(wr*100 if wr is not None else 0):>5.0f}% "
            f"{(s['avgBars'] or 0):>6.1f}봉 {s['exposure']*100:>5.0f}%")


def spearman(a: list[float], b: list[float]) -> float | None:
    """순위 상관 — 훈련 창의 순위가 시험 창의 순위를 말하는지 재는 자."""
    n = len(a)
    if n < 3:
        return None

    def rank(x: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: x[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and x[order[j + 1]] == x[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    ra, rb = rank(a), rank(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = math.sqrt(sum((x - ma) ** 2 for x in ra))
    db = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return num / (da * db) if da and db else None


def selection_skill(d: dict, opt: dict) -> list[dict]:
    """폴드마다 27칸 전부의 훈련 SR 과 시험 SR — 「고르는 것이 값을 더하는가」.

    사다리가 좋아 보여도, 고른 칸이 시험 창에서 **중간쯤**이면 그 선택은
    운이었다. 이 표가 그것을 판정한다: 순위 상관이 0 근처면 훈련 창의 Sharpe 는
    다음 해에 대해 아무 말도 하지 않는다.
    """
    n = len(d["vals"])
    out: list[dict] = []
    lo = 0
    while lo + W.TRAIN + 1 <= n:
        tr_lo, tr_hi = lo, lo + W.TRAIN
        te_lo, te_hi = tr_hi, min(tr_hi + W.TEST, n)
        if te_hi - te_lo < 20:
            break
        cells = []
        for lb in W.GRID_LOOKBACK:
            for ez in W.GRID_ENTRY:
                for xz in W.GRID_EXIT:
                    p = {"lookback": lb, "entryZ": ez, "exitZ": xz}
                    tr = W.run_slice(d, tr_lo, tr_hi, p, opt=opt)["summary"]
                    te = W.fixed_run(d, te_lo, te_hi, p, opt)["stats"]
                    if tr["sharpe"] is None or te["sharpe"] is None:
                        continue
                    cells.append((p, tr["numTrades"], tr["sharpe"], te["sharpe"]))
        if not cells:
            lo += W.TEST
            continue
        chosen = W.pick(d, tr_lo, tr_hi, opt)
        te_sorted = sorted(cells, key=lambda c: -c[3])
        rank = None
        if chosen:
            for k, c in enumerate(te_sorted, 1):
                if all(c[0][key] == chosen[key] for key in ("lookback", "entryZ", "exitZ")):
                    rank = k
                    break
        out.append({
            "from": d["dates"][te_lo], "to": d["dates"][te_hi - 1],
            "cells": len(cells),
            "rho": spearman([c[2] for c in cells], [c[3] for c in cells]),
            "rank": rank,
            "chosenTest": next((c[3] for c in cells if chosen and all(
                c[0][k] == chosen[k] for k in ("lookback", "entryZ", "exitZ"))), None),
            "medianTest": st.median([c[3] for c in cells]),
            "bestTest": max(c[3] for c in cells),
        })
        lo += W.TEST
    return out


def headline(sid: str, deep: bool = True) -> dict:
    d = load(sid)
    gc = W.gates_and_cost(d)
    ref = W.walk_forward(d, W.final_options(gc))
    lo, hi = ref["oosLo"], ref["oosHi"]
    print(f"\n{'='*96}\n{sid}  ·  OOS 창 {d['dates'][lo]} ~ {d['dates'][hi-1]} "
          f"({hi-lo}봉)  ·  전체 {len(d['vals'])}봉 {d['dates'][0]}~\n{'='*96}")

    if deep:
        print("\n── 1. 전진분석은 파라미터 선택에 값을 더하는가 ──")
        print(f"{'시험 창':<26}{'칸':>4}{'훈련↔시험 순위상관':>20}"
              f"{'고른 칸 순위':>14}{'고른 SR':>10}{'중앙 SR':>10}{'최고 SR':>10}")
        for f in selection_skill(d, W.final_options(gc)):
            rho = "—" if f["rho"] is None else f"{f['rho']:+.2f}"
            ch = "—" if f["chosenTest"] is None else f"{f['chosenTest']:.2f}"
            rk = "—" if f["rank"] is None else f"{f['rank']}/{f['cells']}"
            print(f"{f['from']}~{f['to']:<12}{f['cells']:>4}{rho:>20}{rk:>14}"
                  f"{ch:>10}{f['medianTest']:>10.2f}{f['bestTest']:>10.2f}")

        print("\n── 2. 기전 대조군 (파라미터 고정 60/2.0σ/0.5σ · 같은 OOS 창) ──")
        print(HEAD)
        for name, opt in [
            ("기존 규칙 그대로", W.options()),
            ("+ 동적비용만", W.options(cost=gc["cost"])),
            ("+ 타임스탑만", W.options(timeStop=W.TIME_STOP)),
            ("+ 레짐필터(변동성)만", W.options(gate=gc["volGate"])),
            ("+ 레짐필터(추세)만", W.options(gate=gc["trendGate"])),
            # 「+ 역신호청산만」은 2026-09-23 에 뺐다 — 청산이 교차가 된 뒤로
            # 그 문이 못 열려 **「기존 규칙 그대로」와 같은 수**였다. 같은 수가
            # 다른 이름으로 두 줄 서면 읽는 사람은 차이가 없다는 것이 아니라
            # 차이를 못 봤다고 읽는다.
            ("넷 전부 · 변동성", W.final_options(gc)),
            ("넷 전부 · 추세", W.final_options(gc, gate="trend")),
        ]:
            print(f"{name:<26}{fm(W.fixed_run(d, lo, hi, LEGACY, opt)['stats'])}")

        print("\n── 3. 파이프라인 사다리 (칸마다 다시 고른다) ──")
        print(HEAD)
        for name, opt in [
            ("L1 전진분석만", W.options()),
            ("L2 + 동적비용", W.options(cost=gc["cost"])),
            ("L3 + 타임스탑", W.options(cost=gc["cost"], timeStop=W.TIME_STOP)),
            ("L4 + 레짐필터", W.options(cost=gc["cost"], timeStop=W.TIME_STOP,
                                     gate=gc["volGate"])),
            ("L5 + 역신호청산", W.final_options(gc)),
        ]:
            r = W.walk_forward(d, opt)
            print(f"{name:<26}{fm(r['stats'])}")
            for f in r["folds"]:
                p = f["params"]
                tag = (f"lb{p['lookback']} 진입{p['entryZ']} 청산{p['exitZ']}"
                       if p else "선택 없음")
                print(f"    {f['from']}~{f['to']}  {tag:<26}"
                      f"{fm(f['stats']) if f['stats'] else ''}")

    print("\n── 4. 최종 구성 · 벤치마크 대비 ──")
    fin = W.fixed_run(d, lo, hi, LEGACY, W.final_options(gc))
    print(HEAD)
    print(f"{'전략 (다섯 전부·고정)':<26}{fm(fin['stats'])}")
    bms = W.benchmarks(d, lo, hi)
    for bname, series in bms.items():
        s = W.stats(series, [])
        print(f"{'  벤치 ' + bname:<26}{s['totalPnl']/1e4:>9,.0f}만 "
              f"{s['maxDrawdown']/1e4:>8,.0f}만 "
              f"{(s['sharpe'] if s['sharpe'] is not None else float('nan')):>6.2f}"
              f"{'':>5}{'':>7}{'':>8}{'':>7}")
    print(f"\n{'벤치마크':<26}{'초과손익':>12}{'IR':>8}")
    for bname, series in bms.items():
        ex = sum(fin["daily"]) - sum(series)
        ir = W.info_ratio(fin["daily"], series)
        print(f"{bname:<26}{ex/1e4:>10,.0f}만 "
              f"{(ir if ir is not None else float('nan')):>8.2f}")
    return {"d": d, "gc": gc, "lo": lo, "hi": hi, "fin": fin}


def all_tenors() -> None:
    print(f"\n{'='*96}\n전 만기 · 최종 구성(다섯 전부·파라미터 고정)"
          f"  vs  기존 규칙 · 같은 OOS 창\n{'='*96}")
    print(f"{'계열':<10}{'판':<12}{'총손익':>12}{'MDD':>11}{'SR':>7}{'거래':>5}"
          f"{'승률':>7}{'보유':>8}{'IR(상시롱)':>12}")
    port_new: list[float] = []
    port_old: list[float] = []
    tr_new: list[dict] = []
    tr_old: list[dict] = []
    bm_port: dict[str, list[float]] = {}
    for sid in BSS:
        d = load(sid)
        gc = W.gates_and_cost(d)
        ref = W.walk_forward(d, W.final_options(gc))
        lo, hi = ref["oosLo"], ref["oosHi"]
        old = W.fixed_run(d, lo, hi, LEGACY, W.options())
        new = W.fixed_run(d, lo, hi, LEGACY, W.final_options(gc))
        bm = W.benchmarks(d, lo, hi)["상시 BSS 롱"]
        for tag, r in (("기존", old), ("최종", new)):
            s = r["stats"]
            ir = W.info_ratio(r["daily"], bm)
            print(f"{sid if tag=='기존' else '':<10}{tag:<12}"
                  f"{s['totalPnl']/1e4:>10,.0f}만 {s['maxDrawdown']/1e4:>9,.0f}만 "
                  f"{(s['sharpe'] if s['sharpe'] is not None else float('nan')):>6.2f}"
                  f"{s['numTrades']:>5}"
                  f"{(s['winRate']*100 if s['winRate'] is not None else 0):>6.0f}% "
                  f"{(s['avgBars'] or 0):>6.1f}봉"
                  f"{(ir if ir is not None else float('nan')):>12.2f}")
        # 계열마다 OOS 창 길이가 같다고 **가정하지 않는다** — 다르면 짧은 쪽에 맞춘다.
        n = min(len(new["daily"]), len(old["daily"]))
        if not port_new:
            port_new = [0.0] * n
            port_old = [0.0] * n
            bm_port = {k: [0.0] * n for k in W.benchmarks(d, lo, hi)}
        m = min(n, len(port_new))
        port_new = [port_new[i] + new["daily"][i] for i in range(m)]
        port_old = [port_old[i] + old["daily"][i] for i in range(m)]
        tr_new += new["trades"]
        tr_old += old["trades"]
        for k, v in W.benchmarks(d, lo, hi).items():
            bm_port[k] = [bm_port[k][i] + v[i] for i in range(m)]
    print()
    print("포트폴리오 (9계열 동일가중 합 · 같은 OOS 창)")
    print(HEAD)
    print(f"{'기존 규칙':<26}{fm(W.stats(port_old, tr_old))}")
    print(f"{'최종 구성':<26}{fm(W.stats(port_new, tr_new))}")
    print()
    print(f"{'포트폴리오 벤치마크':<26}{'총손익':>12}{'MDD':>11}{'SR':>7}"
          f"{'초과(최종)':>13}{'IR':>8}")
    for k, v in bm_port.items():
        st_ = W.stats(v, [])
        ir = W.info_ratio(port_new, v)
        print(f"{k:<26}{st_['totalPnl']/1e4:>10,.0f}만 {st_['maxDrawdown']/1e4:>9,.0f}만 "
              f"{(st_['sharpe'] if st_['sharpe'] is not None else float('nan')):>6.2f}"
              f"{(sum(port_new)-sum(v))/1e4:>11,.0f}만 "
              f"{(ir if ir is not None else float('nan')):>8.2f}")


if __name__ == "__main__":
    headline("BSS-3Y")
    if "--all" in sys.argv:
        all_tenors()
