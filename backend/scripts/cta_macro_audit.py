# -*- coding: utf-8 -*-
r"""정합성 잔여 다섯 자리를 닫는다 [OWNER 2026-09-08 — 「A랑 B만 확인하면 될 듯」].

오너가 지평을 **2016** 에 놓았다(그 이전은 글로벌 금융위기라 국면이 다르다).
그래서 2012~2015 확장 결과는 철회했고, 이 감사는 **2016 기준** 위에서만 돈다.

    A1  부호 조합 16가지 전수      — 내가 고른 부호가 특별한가
    A2  테마 부분집합 15가지 전수   — 넷 다 필요한가, 특정 둘이 다 하는가
    A3  on/off 보존 위약           — 「절반을 쉬는 것」과 「방향」을 가른다
    A4  듀레이션 상수 민감도        — 8.0 이 상수인가 손잡이인가
    A5  stationary bootstrap      — 순환이동 61개의 낮은 해상도를 올린다

## ★ A3 가 이 감사의 급소다

매크로북은 43.8% 의 날 신호가 0 이라 포지션을 안 잡는다. 그러면 50/50 은 그
기간 동안 **반만 태운 추세북**이고, 낙폭이 주는 것이 신호 때문인지 노출을
줄인 것 때문인지 안 갈린다. 순환이동 위약은 그걸 **부분적으로만** 가른다 —
민 결과의 0 자리가 달라지기 때문이다.

그래서 A3 은 **0 인 날의 위치를 글자 그대로 보존**하고 0 이 아닌 날의 값만
민다. 그러면 노출 일정·회전·크기 분포가 전부 같고 **방향만** 무의미해진다.
진짜가 이 귀무를 못 넘으면, 이득은 신호가 아니라 노출 축소에서 온 것이다.

## 배관

`book_simulate` 와 **같은 산술**을 numpy 로 다시 쓴다(600회를 돌려야 한다).
같은 값을 내는지는 `main` 이 실측으로 대조하고, 안 맞으면 선다.

돌리기:  python -m scripts.cta_macro_audit
"""

from __future__ import annotations

import csv
import itertools
import math
import os

import numpy as np

from app import ctabacktest as cta, futures
from scripts.cta_macro_weights import newey_west_t

PROJECTS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "..", "..", "..", ".."))
THEMES_CSV = os.path.join(PROJECTS, "data", "krw-macro-vintage", "out",
                          "macro_themes_daily.csv")
LOOKBACKS = (20, 40, 60, 120, 250)
VOL_W, BOOK_W, TARGET, BARS = 60, 120, 1_000_000.0, 252
THEMES = ("cycle", "policy", "trade", "risk")
BARS_1Y = 250
N_BOOT = 1000


class Engine:
    """numpy 판 `book_simulate`. 두 계약이 같은 날짜 축을 쓰는 것을 전제한다."""

    def __init__(self, series, rolls, cost_ticks=cta.COST_TICKS):
        keys = list(series)
        self.dates = series[keys[0]][0]
        for k in keys:
            if series[k][0] != self.dates:
                raise cta.CtaError("계약별 날짜 축이 달라요 — numpy 판은 같은 축만 받아요")
        self.n = len(self.dates)
        self.keys = keys
        self.px = np.array([series[k][1] for k in keys], dtype=float)
        self.dp = np.zeros_like(self.px)
        self.dp[:, 1:] = np.diff(self.px, axis=1)
        self.vol = np.array([[np.nan if v is None else v
                              for v in cta.realized_vol(series[k][1], VOL_W)]
                             for k in keys])
        self.trend = np.array([
            np.mean([cta.signal_continuous(series[k][1], "macross", lb)
                     for lb in LOOKBACKS], axis=0) for k in keys])
        self.roll = np.array([d in rolls for d in self.dates])
        self.cost_ticks = cost_ticks

    def run(self, sig: np.ndarray | None) -> np.ndarray:
        """`sig` 가 None 이면 추세, 아니면 그 신호(계약 공통)."""
        s = self.trend if sig is None else np.tile(sig, (len(self.keys), 1))
        with np.errstate(invalid="ignore", divide="ignore"):
            unit = np.where((self.vol > 0) & np.isfinite(self.vol), s / self.vol, 0.0)
        unit = np.nan_to_num(unit)
        raw = np.zeros(self.n)
        raw[1:] = (unit[:, :-1] * self.dp[:, 1:]).sum(axis=0)
        nz = raw != 0.0
        k = np.concatenate([[0], np.cumsum(nz)])
        s1 = np.concatenate([[0], np.cumsum(np.where(nz, raw, 0.0))])
        s2 = np.concatenate([[0], np.cumsum(np.where(nz, raw * raw, 0.0))])
        lo = np.maximum(1, np.arange(self.n) - BOOK_W + 1)
        hi = np.arange(self.n) + 1
        cnt = k[hi] - k[lo]
        sm = s1[hi] - s1[lo]
        sq = s2[hi] - s2[lo]
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = sm / cnt
            var = sq / cnt - mean * mean
            sd = np.sqrt(np.maximum(var, 0.0))
            scale = np.where((cnt >= max(20, BOOK_W // 3)) & (sd > 0), TARGET / sd, 0.0)
        scale = np.nan_to_num(scale)
        pos = unit * scale * 100.0
        pnl = np.zeros(self.n)
        pnl[1:] = (pos[:, :-1] * self.dp[:, 1:]).sum(axis=0) / 100.0
        turn = np.abs(np.diff(pos, axis=1, prepend=0.0)).sum(axis=0)
        cost = turn / 100.0 * cta.TICK * self.cost_ticks
        held = np.abs(np.concatenate([np.zeros((len(self.keys), 1)), pos[:, :-1]],
                                     axis=1)).sum(axis=0)
        cost += np.where(self.roll, held / 100.0 * cta.TICK * 1.0, 0.0)
        return pnl - cost


def calmar(d: np.ndarray) -> float:
    c = np.cumsum(d)
    mdd = float(np.max(np.maximum.accumulate(c) - c))
    return (float(d.sum()) * BARS / len(d)) / mdd if mdd > 0 else 0.0


def sharpe(d: np.ndarray) -> float:
    sd = float(d.std())
    return float(d.mean()) / sd * math.sqrt(BARS) if sd > 0 else 0.0


def main() -> int:
    rows = {r["date"][:10]: r for r in csv.DictReader(open(THEMES_CSV, encoding="utf-8-sig"))}
    f = futures.load()
    series = {t: ([x.isoformat() for x in f.series[t].dates],
                  [float(p) for p in f.series[t].price_adj])
              for t in futures.FUT_TENORS}
    rolls = {x.isoformat() for x in futures.roll_days(list(f.series["3Y"].dates))}
    eng = Engine(series, rolls)
    dates = eng.dates

    def col(name):
        return np.array([float(rows[d][name]) if d in rows
                         and rows[d].get(name, "") not in ("", "nan") else np.nan
                         for d in dates])

    th = {t: col(t) for t in THEMES}
    base = col("macro_sign")
    live = np.isfinite(base)
    start = int(np.argmax(live))
    win = slice(start, eng.n)
    print(f"\n=== 정합성 감사 · {dates[start]} ~ {dates[-1]} · "
          f"{int(live.sum()):,}일 (2016 지평) ===")

    # 배관 대조 — numpy 판이 엔진과 같은 값을 내는가
    ref = cta.book_simulate(series, signal="macross", lookbacks=LOOKBACKS,
                            vol_window=VOL_W, target_book_vol_krw=TARGET,
                            book_vol_window=BOOK_W, roll_days=rolls,
                            continuous=True)["points"]
    a = np.array([p["dailyPnl"] for p in ref])
    b = eng.run(None)
    diff = float(np.max(np.abs(a - b)))
    print(f"  [배관] numpy 판 대 엔진 최대 차이 {diff:.6e} 원/일")
    if diff > 1e-6:
        raise cta.CtaError(f"numpy 판이 엔진과 다릅니다 ({diff:.3e}) — 감사를 못 합니다")

    tr = eng.run(None)[win]

    def blend_of(sig: np.ndarray) -> np.ndarray:
        m = eng.run(np.nan_to_num(sig))[win]
        return 0.5 * tr + 0.5 * m

    real = blend_of(base)
    print(f"  기준: 추세 Calmar {calmar(tr):.2f} · 50/50 Calmar {calmar(real):.2f} "
          f"· Sharpe {sharpe(real):.2f}")

    # ── A1 부호 조합 16가지 ────────────────────────────────────────────
    print("\nA1. 부호 조합 16가지 — 내 조합(++++)이 몇 등인가")
    res = []
    for fl in itertools.product((1, -1), repeat=4):
        s = np.nanmean([fl[i] * th[t] for i, t in enumerate(THEMES)], axis=0)
        s = np.where(live, s, np.nan)
        res.append(("".join("+" if v > 0 else "-" for v in fl), calmar(blend_of(s))))
    res.sort(key=lambda x: -x[1])
    rank = [i for i, (k, _) in enumerate(res, 1) if k == "++++"][0]
    for i, (k, c) in enumerate(res, 1):
        mark = "  <- 내 조합" if k == "++++" else ""
        if i <= 5 or k == "++++" or i >= 15:
            print(f"   {i:>2}. {k}  Calmar {c:>6.2f}{mark}")
    print(f"   → 내 조합 {rank}/16 등")

    # ── A2 테마 부분집합 15가지 ────────────────────────────────────────
    print("\nA2. 테마 부분집합 15가지 (날짜는 넷 다 있는 날로 고정)")
    sub = []
    for r in range(1, 5):
        for c in itertools.combinations(range(4), r):
            s = np.nanmean([th[THEMES[i]] for i in c], axis=0)
            s = np.where(live, s, np.nan)
            sub.append(("+".join(THEMES[i][:4] for i in c), calmar(blend_of(s))))
    sub.sort(key=lambda x: -x[1])
    for i, (k, c) in enumerate(sub, 1):
        mark = "  <- 넷 전부" if k.count("+") == 3 else ""
        print(f"   {i:>2}. {k:<24} Calmar {c:>6.2f}{mark}")

    # ── A3 on/off 보존 위약 ────────────────────────────────────────────
    print("\nA3. ★ on/off 보존 위약 — 0 인 날은 그대로, 0 아닌 값만 민다")
    idx = np.where(live)[0]
    vals = base[idx]
    nzpos = np.where(vals != 0.0)[0]
    nzval = vals[nzpos]
    print(f"   0 인 날 {100*(vals == 0).mean():.1f}% 를 위치까지 보존 · "
          f"0 아닌 값 {len(nzval):,}개만 순환이동")
    null = []
    for off in range(20, len(nzval) - 20, max(1, (len(nzval) - 40) // 200)):
        v = vals.copy()
        v[nzpos] = np.roll(nzval, off)
        s = np.full(eng.n, np.nan)
        s[idx] = v
        null.append(calmar(blend_of(s)))
    null = np.array(sorted(null))
    p3 = float((null >= calmar(real)).mean())
    print(f"   귀무 {len(null)}개 · 중앙 {np.median(null):.2f} "
          f"(5~95% {null[int(.05*len(null))]:.2f}~{null[int(.95*len(null))]:.2f})")
    print(f"   진짜 {calmar(real):.2f}  →  경험적 p = {p3:.3f}")
    print(f"   ※ 이 귀무는 노출 일정·회전·크기 분포가 진짜와 «같다». "
          f"넘으면 이득이 방향에서 온 것이다")
    print(f"   추세 단독({calmar(tr):.2f})을 넘는 귀무 비율 "
          f"{100*float((null >= calmar(tr)).mean()):.0f}%")

    # ── A4 듀레이션 민감도 ─────────────────────────────────────────────
    print("\nA4. 위험선호 듀레이션 상수 민감도")
    kospi, k10 = col("kospi"), col("ktb_10y")
    print(f"   {'D':>5}{'Calmar':>9}{'Sharpe':>9}{'60일 NW t':>11}")
    d10 = series["10Y"][1]
    for D in (4.0, 6.0, 8.0, 10.0, 12.0):
        eq = np.full(eng.n, np.nan)
        bd = np.full(eng.n, np.nan)
        eq[BARS_1Y:] = np.log(kospi[BARS_1Y:] / kospi[:-BARS_1Y])
        bd[BARS_1Y:] = -D * (k10[BARS_1Y:] - k10[:-BARS_1Y]) / 100.0
        risk = -np.sign(eq - bd)
        s = np.nanmean([th["cycle"], th["policy"], th["trade"], risk], axis=0)
        s = np.where(np.isfinite(s) & live, s, np.nan)
        bl = blend_of(s)
        xs, ys = [], []
        for i in range(eng.n - 60):
            if np.isfinite(s[i]):
                xs.append(float(s[i]))
                ys.append(d10[i + 60] - d10[i])
        _b, _se, t = newey_west_t(ys, xs, 60)
        mark = "  <- 채택값" if D == 8.0 else ""
        print(f"   {D:>5.1f}{calmar(bl):>9.2f}{sharpe(bl):>9.2f}{t:>11.2f}{mark}")

    # ── A5 stationary bootstrap ────────────────────────────────────────
    print(f"\nA5. stationary bootstrap {N_BOOT}회 (평균 블록 = 실측 보유일)")
    sgn = np.sign(vals)
    runs, cur = [], 1
    for i in range(1, len(sgn)):
        if sgn[i] == sgn[i - 1]:
            cur += 1
        else:
            runs.append(cur)
            cur = 1
    L = max(5.0, float(np.mean(runs)))
    print(f"   실측 평균 보유 {L:.0f}일 → 블록 재시작 확률 {1/L:.4f}")
    rng = np.random.default_rng(0)
    boot = np.empty(N_BOOT)
    m = len(vals)
    for j in range(N_BOOT):
        out = np.empty(m)
        i = int(rng.integers(m))
        for k2 in range(m):
            out[k2] = vals[i]
            i = int(rng.integers(m)) if rng.random() < 1.0 / L else (i + 1) % m
        s = np.full(eng.n, np.nan)
        s[idx] = out
        boot[j] = calmar(blend_of(s))
    boot.sort()
    p5 = float((boot >= calmar(real)).mean())
    print(f"   귀무 중앙 {np.median(boot):.2f} "
          f"(5~95% {boot[int(.05*N_BOOT)]:.2f}~{boot[int(.95*N_BOOT)]:.2f})")
    print(f"   진짜 {calmar(real):.2f}  →  경험적 p = {p5:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
