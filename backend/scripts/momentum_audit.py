# -*- coding: utf-8 -*-
r"""Momentum 채점 재점검 — MR 레인 Phase 0 진단의 다섯 항목을 이 레인에 그대로 건다.

## 왜 이걸 도나

2026-09-09 에 MR 레인(BSS-10Y)에서 채점 층 진단이 나왔다. 요지 다섯:

  D1 미청산 거래를 성적표에서 빼서 Profit Factor·승률이 부풀었다
  D2 Ulcer 가 부호도 단위도 틀렸다(화면이 음수로 뒤집고, 퍼센트가 아니라 원화)
  D3 시행 횟수 N 을 안 세고 Sharpe 를 그대로 읽었다
  D4 수익 «계열»이 수익률이 아니라 원화 손익이라 변동성 정규화가 안 된다
  D5 MaxDD 가 사실상 표본 하나라 Calmar 의 오차가 넓다

그리고 그 진단이 **이 레인을 직접 지목한다** — 「CTA 레인이 이미 같은 지표
모듈을 쓰고 있어서 «MR 에 유리한 잣대» 문제가 미래가 아니라 지금 두 레인에서
벌어지고 있다」. 그러니 남의 레인 결과로 넘기지 말고 **여기서 다시 재야 한다.**

## 이 파일이 답하는 것

다섯 항목이 이 레인에 «걸리나 안 걸리나»를 하나씩 실측한다. 안 걸리면 왜 안
걸리는지가 결론이고(구조가 다르면 같은 병이 안 생긴다), 걸리면 무엇을 고쳐야
하는지가 결론이다.

돌리기:  python -m scripts.momentum_audit
"""

from __future__ import annotations

import math
import statistics as st

from app import ctabacktest as cta, momentum as mom

BARS = 252


def daily(points: list[dict]) -> list[float]:
    return [p["dailyPnl"] for p in points]


def sharpe(xs: list[float]) -> float | None:
    sd = st.pstdev(xs)
    return (st.fmean(xs) / sd * math.sqrt(BARS)) if sd > 0 else None


def ar1(xs: list[float]) -> float | None:
    """오늘 손익이 어제와 얼마나 닮았나. 0.2 를 넘으면 일별 지표를 의심한다."""
    if len(xs) < 30:
        return None
    m = st.fmean(xs)
    num = sum((xs[i] - m) * (xs[i - 1] - m) for i in range(1, len(xs)))
    den = sum((x - m) ** 2 for x in xs)
    return num / den if den > 0 else None


def kurtosis(xs: list[float]) -> float | None:
    """초과첨도. 크면 꼬리가 두껍고 Sharpe 의 표준오차 보정이 커야 한다."""
    sd = st.pstdev(xs)
    if sd <= 0:
        return None
    m = st.fmean(xs)
    return sum(((x - m) / sd) ** 4 for x in xs) / len(xs) - 3.0


def drawdowns(xs: list[float]) -> list[tuple[float, int]]:
    """(깊이, 물속 일수) 목록 — 봉우리에서 봉우리까지를 한 사건으로 센다."""
    run = peak = 0.0
    depth = 0.0
    days = 0
    out: list[tuple[float, int]] = []
    for x in xs:
        run += x
        if run >= peak:
            if depth > 0:
                out.append((depth, days))
            peak, depth, days = run, 0.0, 0
        else:
            depth = max(depth, peak - run)
            days += 1
    if depth > 0:
        out.append((depth, days))
    return out


def cost_breakeven(series, rolls, external=None) -> float | None:
    """손익이 0 이 되는 비용 배수. 클수록 비용 가정이 결론을 안 흔든다."""
    base = None
    lo, hi = 1.0, 200.0
    for _ in range(40):
        mid = (lo + hi) / 2
        b = cta.book_simulate(
            series, signal=mom.SIGNAL, lookbacks=mom.LOOKBACKS,
            vol_window=mom.VOL_WINDOW, target_book_vol_krw=mom.TARGET_VOL,
            book_vol_window=mom.BOOK_VOL_WINDOW, roll_days=rolls,
            continuous=True, external_signals=external,
            cost_ticks=cta.COST_TICKS * mid)
        tot = sum(p["dailyPnl"] for p in b["points"] if p["t"] <= mom.FREEZE)
        if base is None:
            base = tot
        if tot > 0:
            lo = mid
        else:
            hi = mid
    return round(lo, 2)


def main() -> int:
    series, rolls = mom._load_prices()
    macro = mom._load_macro()
    start = min(macro["macro_sign"])

    def cut(pts):
        return [p for p in pts if start <= p["t"] <= mom.FREEZE]

    b_trend = mom._run_book(series, rolls)
    b_macro = mom._run_book(series, rolls,
                            external={k: macro["macro_sign"] for k in series})
    t_pts, m_pts = cut(b_trend["points"]), cut(b_macro["points"])
    mi = {p["t"]: p for p in m_pts}
    blend = [{"t": p["t"],
              "dailyPnl": 0.5 * p["dailyPnl"] + 0.5 * mi[p["t"]]["dailyPnl"],
              "barCost": 0.5 * p["barCost"] + 0.5 * mi[p["t"]]["barCost"]}
             for p in t_pts if p["t"] in mi]
    legs = {"추세": t_pts, "매크로": m_pts, "50/50": blend}

    print("\n=== Momentum 채점 재점검 — MR Phase 0 다섯 항목을 이 레인에 ===")
    print(f"창 {start} ~ {mom.FREEZE} · {len(t_pts):,}일\n")

    # ── D1 미청산 ─────────────────────────────────────────────────────────
    print("D1 미청산 거래가 성적표에서 빠졌나")
    flat = 0
    idx = [i for i, t in enumerate(b_trend["dates"]) if start <= t <= mom.FREEZE]
    for i in idx:
        if all(b_trend["pos"][k][i] == 0.0 for k in b_trend["pos"]):
            flat += 1
    print(f"  이 레인은 «거래 목록»으로 채점하지 않는다 — 매일 시가평가한 일별 손익뿐이다.")
    print(f"  포지션 없는 날 {100*flat/len(idx):.1f}% · 열린 포지션도 매일 손익에 든다.")
    print("  → 안 걸린다. 뺄 «미청산 거래»라는 것이 구조적으로 없다.\n")

    # ── D2 Ulcer ─────────────────────────────────────────────────────────
    print("D2 Ulcer 부호·단위")
    print("  이 화면은 Ulcer 를 **안 낸다**(Sharpe·Calmar·연손익·연변동·최대낙폭만).")
    print("  → 지금은 안 걸린다. 단 MR 이 Ulcer 를 퍼센트로 고치면 이 레인도 같이 가야 한다.\n")

    # ── D4 원화 손익 · 정규화 ────────────────────────────────────────────
    print("D4 수익 계열의 성질 — 원화 손익이지 수익률이 아니다")
    for name, pts in legs.items():
        xs = daily(pts)
        sd = st.pstdev(xs)
        print(f"  {name:<6} 일 σ {sd/1e4:>7,.1f}만원 · 목표 {mom.TARGET_VOL/1e4:,.0f}만원 "
              f"· 비 {sd/mom.TARGET_VOL:>4.2f}")
    print("  ★ 이 레인은 **북 변동성 목표**가 있다 — 사전 일 σ 를 100만원에 맞춘다.")
    print("     그래서 원화 손익이어도 계열이 이미 «위험 고정»이고 Sharpe 가 뜻을 갖는다.")
    print("     MR 은 그 장치가 없다. **두 레인의 Sharpe 를 나란히 놓으려면 이 차이를 적어야 한다.**\n")

    # ── D5 낙폭 사건 수 ──────────────────────────────────────────────────
    print("D5 큰 낙폭이 몇 번인가 (Calmar 의 분모가 표본 하나인가)")
    for name, pts in legs.items():
        dds = sorted(drawdowns(daily(pts)), key=lambda x: -x[0])
        if not dds:
            continue
        mdd = dds[0][0]
        big = [d for d in dds if d[0] >= 0.5 * mdd]
        print(f"  {name:<6} 낙폭 사건 {len(dds):>3}건 · MaxDD {mdd/1e4:>6,.0f}만원 "
              f"· 그 절반을 넘는 것 {len(big)}건")
        for depth, days in dds[:3]:
            print(f"         {depth/1e4:>6,.0f}만원 · 물속 {days:>3}일")
    print()

    # ── 덤: AR(1)·첨도 ───────────────────────────────────────────────────
    print("덤 일별 지표가 부풀 조건인가 (AR(1) · 초과첨도)")
    for name, pts in legs.items():
        xs = daily(pts)
        print(f"  {name:<6} AR(1) {ar1(xs):+.3f} · 초과첨도 {kurtosis(xs):>6.1f} "
              f"· Sharpe {sharpe(xs):.3f}")
    print("  기준은 AR(1) 0.2 — 넘으면 일별 지표를 그대로 못 읽는다.\n")

    # ── 덤: 비용 쿠션 ────────────────────────────────────────────────────
    print("덤 비용이 결론을 흔드나 (손익 0 이 되는 비용 배수)")
    print(f"  추세   {cost_breakeven(series, rolls)}배")
    print(f"  매크로 {cost_breakeven(series, rolls, {k: macro['macro_sign'] for k in series})}배")
    print("  MR(BSS-10Y)는 3.5배였다(0.5bp → 1.774bp 에서 0).\n")

    # ── D3 시행 횟수 ─────────────────────────────────────────────────────
    print("D3 이 레인의 시행 횟수 N — 셈은 사람이 한다")
    print("  고정(고르지 않았다): 신호 macross · 룩백 5개 등가중 · 변동성 창 · 북 목표 · 비용")
    print("  고른 것: 부호 조합 16개 중 1 · 테마 부분집합 15개 중 1 · 가중 21칸 중 1")
    print("           그리고 신호계 3 × 룩백 5 격자를 cta_validate 가 한 번 돌았다(PBO 1~11%).")
    print("  → 이 레인의 N 은 1 이 아니다. 다만 **격자 1등을 채택하지 않았고**")
    print("     룩백은 규율상 고를 수 없게 막아 두었다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
