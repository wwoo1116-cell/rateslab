# -*- coding: utf-8 -*-
r"""「2016-01-01 에 100억으로 시작했다면」 — IRS 추세북의 자산 곡선 [OWNER 2026-09-09].

## 이 질문에 답하려면 정해야 하는 것 셋

1. **크기.** 이 북은 «금액»이 아니라 «위험»으로 큰다 — 목표 변동성이 곧 손잡이다.
   100억에 **연 변동성 5%**(= 5억/년)로 잡는다. 그 5% 는 이 데스크가 Phase 2 목표
   변동성으로 이미 말한 값이다. 다른 값을 넣으면 손익은 그 비율로 그대로 늘고 준다.
2. **노는 현금.** IRS 는 대차대조표를 안 쓰고 증거금만 쓴다[OWNER]. 그래서 100억은
   **거의 전부 단기로 굴러간다** — 콜금리로 붙인다(`mkt_irs_close.call_rate`,
   2016-01-15~). 이 데스크 규약이 MMF 벤치마크를 콜과 CD91 «범위»로 내라는 것이라
   콜은 그 아래끝이다. 위끝(CD91 = 기준금리 +20.2bp)도 같이 낸다.
3. **첫 해.** 250일 룩백이 차기 전에는 포지션이 없다. **2016 년은 캐리만 번다** —
   그게 이 표의 첫 줄이 조용한 이유다.

## 읽는 법

「추세만」 줄은 **초과수익**이고, 「캐리만」 줄이 그 벤치마크다. 둘을 더한 것이
실제로 손에 쥐는 것이다.

돌리기:  python -m scripts.momentum_irs_book100
"""

from __future__ import annotations

import datetime as dt
import math
import statistics as st

from sqlalchemy import text

from app import ctabacktest as cta, momentum as mom
from app.mysqldb import engine

BARS = 252
CAPITAL = 100e8                 # 100억
TARGET_VOL_PCT = 0.05           # 연 변동성 5%
IRS_COST_BP = 0.5               # 편도 [OWNER]
START = "2016-01-04"            # IRS 자료 첫날(2016-01-01 은 휴일)


def load_rates() -> tuple[list[str], dict[str, list[float]], dict[str, float]]:
    """IRS par 금리(−bp)와 콜금리. 같은 표에서 온다."""
    with engine().connect() as conn:
        rows = conn.execute(text(
            "SELECT irs_date, irs_3y, irs_10y, call_rate FROM mkt_irs_close "
            "WHERE irs_3y IS NOT NULL AND irs_10y IS NOT NULL "
            "ORDER BY irs_date ASC"
        )).fetchall()
    days, r3, r10, call = [], [], [], {}
    for r in rows:
        d = r[0]
        day = (d.date() if hasattr(d, "date") else d).isoformat()
        if day < START:
            continue
        days.append(day)
        r3.append(-float(r[1]) * 100.0)
        r10.append(-float(r[2]) * 100.0)
        if r[3] is not None and float(r[3]) > 0:
            call[day] = float(r[3])
    return days, {"3Y": r3, "10Y": r10}, call


def curve(days: list[str], pnl: list[float], rate: dict[str, float],
          spread_bp: float = 0.0) -> tuple[list[float], dict]:
    """자산 곡선 — 캐리는 **현재 자산에 복리로** 붙고 추세 손익은 그 위에 더해진다.

    캐리를 초기 자본에만 붙이면 10.7 년에서 복리를 통째로 버린다.
    """
    eq = CAPITAL
    out = [eq]
    last = dt.date.fromisoformat(days[0])
    r_last = None
    carry_only = CAPITAL
    carry_series = [carry_only]
    for i in range(1, len(days)):
        d = dt.date.fromisoformat(days[i])
        n = (d - last).days
        r = rate.get(days[i], r_last)
        r_last = r
        acc = (0.0 if r is None else (r + spread_bp / 100.0) / 100.0 * n / 365.0)
        eq = eq * (1 + acc) + pnl[i]
        carry_only = carry_only * (1 + acc)
        out.append(eq)
        carry_series.append(carry_only)
        last = d
    yrs = (dt.date.fromisoformat(days[-1]) - dt.date.fromisoformat(days[0])).days / 365.25
    peak = out[0]
    mdd = mdd_pct = 0.0
    for v in out:
        peak = max(peak, v)
        mdd = max(mdd, peak - v)
        mdd_pct = max(mdd_pct, (peak - v) / peak)
    return out, {
        "years": yrs,
        "final": out[-1],
        "cagr": (out[-1] / CAPITAL) ** (1 / yrs) - 1,
        "mdd": mdd, "mddPct": mdd_pct,
        "carryFinal": carry_series[-1],
        "carryCagr": (carry_series[-1] / CAPITAL) ** (1 / yrs) - 1,
    }


def main() -> int:
    days, rates, call = load_rates()
    series = {t: (days, rates[t]) for t in ("3Y", "10Y")}
    b = cta.book_simulate(
        series, signal=mom.SIGNAL, lookbacks=mom.LOOKBACKS,
        vol_window=mom.VOL_WINDOW, target_book_vol_krw=1_000_000.0,
        book_vol_window=mom.BOOK_VOL_WINDOW, roll_days=set(),
        continuous=True, cost_ticks=IRS_COST_BP / cta.TICK)
    raw = [p["dailyPnl"] for p in b["points"]]

    # 위험을 100억의 연 5% 로 맞춘다 — 실현 변동성 기준(사전 목표는 안 맞는다).
    live = [x for x in raw if x != 0.0]
    k = (CAPITAL * TARGET_VOL_PCT / math.sqrt(BARS)) / st.pstdev(live)
    pnl = [x * k for x in raw]

    print(f"\n=== 2016-01-04 에 100억으로 시작했다면 — IRS 추세북 ===")
    print(f"창 {days[0]} ~ {days[-1]} · {len(days):,}일")
    print(f"크기 = 연 변동성 {TARGET_VOL_PCT*100:.0f}% (= {CAPITAL*TARGET_VOL_PCT/1e8:.0f}억/년) "
          f"· IRS 편도 {IRS_COST_BP}bp[OWNER] · 배수 {k:,.1f}×")
    first_live = next(days[i] for i, x in enumerate(raw) if x != 0.0)
    print(f"첫 포지션 {first_live} — 그 전은 룩백 워밍업이라 **캐리만** 번다\n")

    for tag, spread in (("콜금리", 0.0), ("CD 91일 (콜 +20.2bp)", 20.2)):
        eq, s = curve(days, pnl, call, spread)
        _, only = curve(days, [0.0] * len(days), call, spread)
        print(f"── 노는 현금을 {tag} 로 굴렸을 때 ──")
        print(f"  캐리만 (벤치마크)   최종 {only['final']/1e8:>7,.1f}억 "
              f"· 연 {100*only['cagr']:>5.2f}%")
        print(f"  캐리 + 추세         최종 {s['final']/1e8:>7,.1f}억 "
              f"· 연 {100*s['cagr']:>5.2f}%  → 초과 {100*(s['cagr']-only['cagr']):>+5.2f}%p")
        print(f"  최대낙폭            {s['mdd']/1e8:>7,.1f}억 ({100*s['mddPct']:.2f}%)\n")

    # 추세 단독의 성질 — 캐리를 뺀 순수 초과분
    d = [x for x in pnl[1:]]
    ann = sum(d) * BARS / len(d)
    vol = st.pstdev(d) * math.sqrt(BARS)
    peak = run = mdd = 0.0
    for x in d:
        run += x
        peak = max(peak, run)
        mdd = max(mdd, peak - run)
    print("── 추세 손익만 떼어 보면 (캐리 제외) ──")
    print(f"  총 {sum(d)/1e8:>6,.2f}억 · 연평균 {ann/1e8:>5,.2f}억 "
          f"· 연변동 {vol/1e8:>5,.2f}억 · 최대낙폭 {mdd/1e8:>5,.2f}억")
    print(f"  Sharpe {st.fmean(d)/st.pstdev(d)*math.sqrt(BARS):.2f} "
          f"· Calmar {ann/mdd:.2f}")
    dv01 = st.fmean([sum(abs(b["pos"][t][i]) for t in b["pos"]) / 100.0 * k
                     for i in range(len(days)) if raw[i] != 0.0])
    print(f"  평균 DV01 {dv01/1e4:,.0f}만원/bp — 이만큼의 금리 위험을 지고 있다는 뜻")
    print("\n  ⚠ 크기가 연 변동성 5% 가정에서 온다 — 그 값을 바꾸면 손익도 비례해 바뀐다.")
    print("  ⚠ 표본내다. 사전등록 채점 구간(2026-09-09~)은 여기 없다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
