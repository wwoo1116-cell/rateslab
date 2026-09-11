# -*- coding: utf-8 -*-
r"""MR 위약이 «약한 검정»인가 — 세 판을 나란히 잰다 [OWNER 2026-09-11 「더 센 위약」].

    python -m scripts.mr_placebo_strength
    python -m scripts.mr_placebo_strength --sid BSS-10Y

## 물음

§23-3 이 적은 것: BSS 아홉의 위약 95백분위가 −0.04~+0.11 이라 **연 SR 이 양수이기만
하면 거의 통과한다.** 위약이 음수로 깔리는 이유는 민 경로도 왕복비용은 그대로 무는데
회귀는 못 잡아서다. 그래서 「더 센 판을 설계하라」가 지시였다.

## 그런데 «더 세게» 가 무엇인지부터 정해야 한다

    A 지금 판      경로 전체를 순환이동. 비용 포함.
                  ★순환이동은 **보유구간 수·길이·포지션 일수를 이미 정확히 보존한다**
                  (np.roll 은 배열을 돌릴 뿐이라 런 구조가 안 깨진다). 즉 「거래
                  횟수와 보유기간 분포를 유지한다」는 처방은 **이미 만족돼 있다.**

    B 비용 0 판    실제와 위약 둘 다 비용을 빼고 잰다. 음수로 깔던 힘을 없애
                  귀무가설을 0 언저리로 올린다. **문턱이 실제로 올라가는 판.**

    C 재배치 판    보유구간 길이를 섞어 창 안에 무작위로 다시 놓는다. 순환이동이
                  못 만드는 배치까지 포함한다(이동은 순환군 위의 2,620가지뿐).

A 와 C 가 같은 답을 내면 **지금 판이 이미 옳고**, 약해 보이는 것은 검정의 결함이
아니라 비용이 만든 귀무가설의 성질이다. 그 경우 답은 「더 센 검정」이 아니라
**B 를 같이 적는 것**이다.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation import randomization as rz                       # noqa: E402
from scripts import mr_evaluate as me                            # noqa: E402

ANN = 252
N_DRAW = 400
SEED = 20260911


def runs_of(pos: np.ndarray) -> tuple[list[int], np.ndarray]:
    """(보유구간 길이들, 각 구간의 부호). MR 은 숏 전용이라 부호는 전부 −1 이다."""
    lens, signs, cur, sgn = [], [], 0, 0.0
    for v in pos:
        if v != 0:
            cur += 1
            sgn = v
        elif cur:
            lens.append(cur)
            signs.append(sgn)
            cur, sgn = 0, 0.0
    if cur:
        lens.append(cur)
        signs.append(sgn)
    return lens, np.asarray(signs, dtype=float)


def replace_runs(n: int, lens: list[int], signs: np.ndarray,
                 rng: np.random.Generator) -> np.ndarray:
    """길이를 섞어 창 안에 겹치지 않게 다시 놓는다.

    구간 사이에 최소 한 봉의 빈틈을 둔다 — 안 두면 두 구간이 붙어 하나가 되고
    거래 «횟수»가 줄어 비용이 달라진다. 그러면 보존하려던 것을 깨는 셈이다.
    """
    k = len(lens)
    order = rng.permutation(k)
    ls = [lens[i] for i in order]
    sg = signs[order]
    slack = n - sum(ls) - (k - 1)
    if slack < 0:
        raise SystemExit("구간이 창보다 길어요 — 재배치가 불가능합니다")
    # 빈틈 k+1 칸에 slack 을 무작위로 나눈다(막대와 칸막이)
    cuts = np.sort(rng.integers(0, slack + 1, k))
    gaps = np.diff(np.concatenate(([0], cuts, [slack])))
    out = np.zeros(n)
    at = int(gaps[0])
    for i, ln in enumerate(ls):
        out[at:at + ln] = sg[i]
        at += ln + 1 + int(gaps[i + 1])
    return out


def measure(sid: str) -> None:
    dates, vals, carry, face = me._leg_inputs(sid)
    base = me._run(dates, vals, carry)
    pts = base["points"]
    pos = np.array([float(p["position"]) for p in pts])
    n = len(pos)
    dv = [0.0] + [vals[i] - vals[i - 1] for i in range(1, len(vals))]

    pl_cost = rz.plumbing_mr(dv[:n], list(carry)[:n],
                             me.BASE["notional"], me.BASE["costBp"])
    pl_free = rz.plumbing_mr(dv[:n], list(carry)[:n],
                             me.BASE["notional"], 0.0)

    lens, signs = runs_of(pos)
    print()
    print(f"── {sid} · {n:,}봉 ──")
    print(f"  포지션 있는 날 {int((pos != 0).sum()):,}일 "
          f"({(pos != 0).mean():.1%}) · 보유구간 {len(lens)}개 · "
          f"평균 {np.mean(lens):.1f}봉 · 최장 {max(lens)}봉")

    def card(pl, p):
        return rz._sr(rz.repnl_mr(pl, {"leg": p}))

    real_cost = card(pl_cost, pos)
    real_free = card(pl_free, pos)
    print(f"  실현 SR  비용 후 {real_cost:+.3f} · 비용 전 {real_free:+.3f}")

    lo = me.BASE["lookback"]
    shifts = list(range(lo, n - lo, rz.SHIFT_STEP))
    rng = np.random.default_rng(SEED)

    rows = []
    # A · C 는 같은 이동/배치를 비용 포함으로, B 는 비용 0 으로
    a = np.array([card(pl_cost, np.roll(pos, k)) for k in shifts])
    rows.append(("A 순환이동 · 비용 포함", real_cost, a))
    b = np.array([card(pl_free, np.roll(pos, k)) for k in shifts])
    rows.append(("B 순환이동 · 비용 0", real_free, b))
    c = np.array([card(pl_cost, replace_runs(n, lens, signs, rng))
                  for _ in range(N_DRAW)])
    rows.append(("C 구간 재배치 · 비용 포함", real_cost, c))

    print()
    print(f"  {'판':26s} {'표본':>6s} {'중앙':>8s} {'95%':>8s} {'이긴 위약':>10s} "
          f"{'p':>8s}")
    for name, real, arr in rows:
        beat = int((arr >= real).sum())
        p = (beat + 1) / (len(arr) + 1)
        print(f"  {name:26s} {len(arr):6,d} {np.median(arr):+8.3f} "
              f"{np.percentile(arr, 95):+8.3f} {beat:6,d}/{len(arr):<4,d} "
              f"{p:8.4f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sid", default=None)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    sids = ([s for s, _l, k in me.mr_mod.SERIES if k == "bss"] if a.all
            else [a.sid or "BSS-2Y"])
    for sid in sids:
        measure(sid)
    print()
    print("  ★읽는 법. A 와 C 가 같은 답이면 순환이동이 이미 「거래 횟수·보유기간")
    print("  분포 유지」를 하고 있다는 뜻이다(np.roll 은 런 구조를 안 깬다).")
    print("  그때 약해 보이는 것은 검정의 결함이 아니라 **비용이 만든 귀무가설의")
    print("  성질**이고, 답은 「더 센 검정」이 아니라 **B 를 같이 적는 것**이다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
