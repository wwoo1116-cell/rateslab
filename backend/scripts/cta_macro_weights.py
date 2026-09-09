# -*- coding: utf-8 -*-
r"""가중치는 50/50 이어야 하나 + 부호 검정을 Newey-West 로 [OWNER 2026-09-08].

## ① 왜 50/50 이었나

**자유모수가 0 이기 때문이다.** AQR 이 논문에서 쓴 값이고 이 표본을 보기 전에
정해진 값이다. 격자로 고르면 그 순간 손잡이가 하나 생기고, 그 대가는 이
데스크가 이미 여러 번 치렀다(MR 격자 PBO·CTA 격자 PBO 0.80).

그래도 **최적값이 어디인지, 그리고 그것이 표본밖에서 지켜지는지**는 재야 한다.
안 재고 「50/50 이 원칙이라서」라고만 하면 그건 근거가 아니라 관습이다.
그래서 격자를 돌리되 **반드시 표본 반 가르기와 같이** 낸다.

## ② Newey-West

앞선 부호 검정의 t 는 겹치는 창을 `sqrt(h)` 로 나눈 조잡한 보정이었다. 제대로
하면 회귀

    r_{t→t+h} = a + b·s_t + e_t

에 **Newey-West(lag = h)** 표준오차를 쓴다. 겹침이 만드는 오차 자기상관을
직접 다루므로 t 가 커질 수도 작아질 수도 있다 — 어느 쪽인지가 답이다.

돌리기:  python -m scripts.cta_macro_weights
"""

from __future__ import annotations

import csv
import math
import os
import statistics as st

from app import ctabacktest as cta, futures

PROJECTS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "..", "..", "..", ".."))
THEMES_CSV = os.path.join(PROJECTS, "data", "krw-macro-vintage", "out",
                          "macro_themes_daily.csv")
LOOKBACKS = (20, 40, 60, 120, 250)
BARS = 252
THEMES = ("cycle", "policy", "trade", "risk")


def newey_west_t(y: list[float], x: list[float], lag: int) -> tuple[float, float, float]:
    """`y = a + b·x` 의 b 와 그 Newey-West t. 반환 (b, se, t)."""
    n = len(y)
    mx, my = st.fmean(x), st.fmean(y)
    sxx = sum((v - mx) ** 2 for v in x)
    if sxx <= 0:
        return 0.0, 0.0, 0.0
    b = sum((x[i] - mx) * (y[i] - my) for i in range(n)) / sxx
    a = my - b * mx
    e = [y[i] - a - b * x[i] for i in range(n)]
    z = [(x[i] - mx) * e[i] for i in range(n)]
    # S = γ0 + 2·Σ_{j=1..L} (1 − j/(L+1))·γj   (Bartlett 커널)
    s = sum(v * v for v in z) / n
    for j in range(1, lag + 1):
        g = sum(z[i] * z[i - j] for i in range(j, n)) / n
        s += 2.0 * (1.0 - j / (lag + 1.0)) * g
    var_b = n * s / (sxx ** 2)
    se = math.sqrt(var_b) if var_b > 0 else 0.0
    return b, se, (b / se if se > 0 else 0.0)


def calmar(dl: list[float]) -> float:
    run = peak = mdd = 0.0
    for v in dl:
        run += v
        peak = max(peak, run)
        mdd = max(mdd, peak - run)
    return (sum(dl) * BARS / len(dl)) / mdd if mdd > 0 else 0.0


def sharpe(dl: list[float]) -> float:
    sd = st.pstdev(dl)
    return st.fmean(dl) / sd * math.sqrt(BARS) if sd > 0 else 0.0


def main() -> int:
    rows = {r["date"][:10]: r for r in
            csv.DictReader(open(THEMES_CSV, encoding="utf-8-sig"))}
    sign = {d: float(r["macro_sign"]) for d, r in rows.items()
            if r["macro_sign"] not in ("", "nan")}
    start = min(sign)

    f = futures.load()
    series = {t: ([x.isoformat() for x in f.series[t].dates],
                  [float(p) for p in f.series[t].price_adj])
              for t in futures.FUT_TENORS}
    rolls = {x.isoformat() for x in futures.roll_days(list(f.series["3Y"].dates))}
    K = dict(signal="macross", vol_window=60, target_book_vol_krw=1_000_000.0,
             book_vol_window=120, roll_days=rolls)

    tr = {p["t"]: p["dailyPnl"] for p in
          cta.book_simulate(series, lookbacks=LOOKBACKS, continuous=True, **K)["points"]
          if p["t"] >= start}
    mc = {p["t"]: p["dailyPnl"] for p in
          cta.book_simulate(series, lookbacks=(20, 250),
                            external_signals={k: sign for k in series},
                            **K)["points"] if p["t"] >= start}
    days = sorted(set(tr) & set(mc))
    mid = days[len(days) // 2]
    h1 = [d for d in days if d < mid]
    h2 = [d for d in days if d >= mid]

    def mix(w, dd):
        return [(1 - w) * tr[d] + w * mc[d] for d in dd]

    print(f"\n=== ① 매크로 비중 w 격자 · {days[0]}~{days[-1]} · {len(days):,}일 ===")
    print(f"  w=0 이 순수 추세, w=1 이 순수 매크로. 경계 {mid}")
    print(f"\n  {'w':>5}{'전체 Calmar':>13}{'전체 Sharpe':>13}"
          f"{'전반 Calmar':>13}{'후반 Calmar':>13}")
    grid = [i / 20 for i in range(21)]
    best = None
    for w in grid:
        c = calmar(mix(w, days))
        s = sharpe(mix(w, days))
        c1, c2 = calmar(mix(w, h1)), calmar(mix(w, h2))
        star = ""
        if best is None or c > best[1]:
            best = (w, c)
        if abs(w - 0.5) < 1e-9:
            star = "  <- AQR 사전 선택"
        print(f"  {w:>5.2f}{c:>13.2f}{s:>13.2f}{c1:>13.2f}{c2:>13.2f}{star}")
    print(f"\n  표본내 최적 w = {best[0]:.2f} (Calmar {best[1]:.2f}) · "
          f"50/50 대비 이득 {best[1]-calmar(mix(0.5, days)):+.2f}")

    # 반쪽에서 고른 w 를 다른 반쪽에 적용 — 격자가 정보인가
    print("\n  ★ 반쪽에서 고른 w 를 다른 반쪽에 적용하면")
    for lab, fit, test in (("전반→후반", h1, h2), ("후반→전반", h2, h1)):
        wbest = max(grid, key=lambda w: calmar(mix(w, fit)))
        print(f"    {lab}: 고른 w={wbest:.2f} → 표본밖 Calmar {calmar(mix(wbest, test)):.2f}"
              f"  (거기서 w=0.5 는 {calmar(mix(0.5, test)):.2f}"
              f" · w=0 은 {calmar(mix(0.0, test)):.2f})")

    # ── ② Newey-West ────────────────────────────────────────────────────
    print("\n=== ② 테마 부호 검정 — Newey-West(lag=h) ===")
    d10, p10 = series["10Y"]
    at = {t: i for i, t in enumerate(d10)}
    print(f"  {'테마':<10}{'지평':>6}{'b':>10}{'NW t':>9}{'구 t(sqrt h)':>14}{'N':>8}")
    old = {("cycle",20):0.92,("cycle",60):0.65,("cycle",250):0.57,
           ("policy",20):0.59,("policy",60):0.29,("policy",250):-0.86,
           ("trade",20):0.64,("trade",60):1.06,("trade",250):0.74,
           ("risk",20):0.84,("risk",60):1.06,("risk",250):0.14}
    for th in THEMES:
        s = {d: float(rows[d][th]) for d in rows
             if rows[d].get(th, "") not in ("", "nan")}
        for h in (20, 60, 250):
            xs, ys = [], []
            for day, v in s.items():
                i = at.get(day)
                if i is None or i + h >= len(p10) or v == 0:
                    continue
                xs.append(v)
                ys.append(p10[i + h] - p10[i])
            if len(xs) < 100:
                continue
            b, se, t = newey_west_t(ys, xs, h)
            print(f"  {th:<10}{h:>6}{b:>10.3f}{t:>9.2f}"
                  f"{old.get((th,h),float('nan')):>14.2f}{len(xs):>8,}")

    print("\n  합성 신호(macro_sign)도 같은 자로")
    for h in (20, 60, 250):
        xs, ys = [], []
        for day, v in sign.items():
            i = at.get(day)
            if i is None or i + h >= len(p10):
                continue
            xs.append(v)
            ys.append(p10[i + h] - p10[i])
        b, se, t = newey_west_t(ys, xs, h)
        print(f"  {'macro_sign':<10}{h:>6}{b:>10.3f}{t:>9.2f}{'':>14}{len(xs):>8,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
