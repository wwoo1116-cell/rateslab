# -*- coding: utf-8 -*-
"""추세 신호를 **조기경보기**로 쓸 수 있나 [OWNER 2026-09-07 —
"조기경보기 정도로 사용해서 필요할 때 밀 수 있게 트레이더의 확신을 도와주는 도구"].

## 바가 다르다

전략으로 쓰려면 Calmar 가 문턱을 넘어야 한다(실측 0.1~0.36 — 얇다). **경보기로
쓰려면 그 문턱이 아니라 「미리 알려 주나」가 기준이다.** 손익을 안 내도, MR 이
아플 때를 하루 먼저 말해 주면 값이 있다.

## 왜 이 데스크에서 특히 그런가

오늘 실측: **MR(FUT-KTB3)과 CTA 북의 일별 손익 상관이 −0.500.** 같은 선물 위에서
평균회귀와 추세가 정확히 반대 베팅이다. 그러면 추세 신호는 **MR 의 역풍계**다 —
MR 이 이 데스크의 실제 전략이므로, 그 반대편 신호가 켜질 때를 아는 것이 곧
「지금은 밀지 마라 / 지금은 밀어도 된다」다.

## 셋을 답한다 — 전부 **사전에 알 수 있는 것**만 쓴다

    ① 예지력    t−1 의 신호 상태가 t 이후 MR 손익을 가르나
    ② 정렬도    룩백 다섯이 한 방향일 때(«추세가 뚜렷») MR 이 더 아픈가
    ③ 방향 적중  신호가 다음 N일 방향을 얼마나 맞히나 (손익이 아니라 적중률)

**신호는 t−1 까지의 정보로만 만든다.** 한 칸이라도 밀리면 경보기가 아니라
사후설명이 된다.

## 이 시험이 답하지 않는 것

「얼마나 밀어야 하나」는 안 답한다. 크기 규칙은 다른 문제이고, 여기서 재는 것은
**「신호가 앞을 아는가」** 하나다.

돌리기:  python -m scripts.cta_as_warning
"""

from __future__ import annotations

import statistics as st

from app import ctabacktest as cta, funding, futures, mrbook, mrmetrics as mrm
from app.main import _mr_leg

LOOKBACKS = (20, 40, 60, 120, 250)
KN = dict(lookback=60, entryZ=2.0, exitZ=0.5, stopZ=3.5, costBp=0.5,
          notional=1_000_000.0, carry=True, entryMode="level", timeStop=0,
          costModel="flat", regime="none", reverseExit=False, countOpen=False)


def trend_state():
    """{날짜: (정렬도, 방향)} — 룩백 다섯의 **부호 합**을 −1~+1 로.

    정렬도 |x| 가 1 이면 다섯이 한 방향(추세가 뚜렷), 0 이면 갈렸다.
    3Y·10Y 둘을 평균한다 — 커브 전체의 추세 상태다.
    """
    f = futures.load()
    per: dict[str, list[float]] = {}
    for t in futures.FUT_TENORS:
        s = f.series[t]
        d = [x.isoformat() for x in s.dates]
        px = [float(p) for p in s.price_adj]
        sigs = [cta.signal_series(px, "macross", lb) for lb in LOOKBACKS]
        for i, day in enumerate(d):
            v = st.fmean([sg[i] for sg in sigs])
            per.setdefault(day, []).append(v)
    return {d: st.fmean(v) for d, v in per.items()}


def mr_daily(sid: str):
    spec = funding.FundingSpec().validated()
    leg = _mr_leg(sid, spec=spec, **KN)
    return {d: p["dailyPnl"] for d, p in zip(leg["dates"], leg["r"]["points"])}


def book_daily():
    spec = funding.FundingSpec().validated()
    out: dict[str, float] = {}
    for sid, _l in mrbook.bss_series():
        try:
            leg = _mr_leg(sid, spec=spec, **KN)
        except Exception:                                      # noqa: BLE001
            continue
        for d, p in zip(leg["dates"], leg["r"]["points"]):
            out[d] = out.get(d, 0.0) + p["dailyPnl"]
    return out


def bucket_report(name: str, pnl: dict[str, float], state: dict[str, float]):
    """t−1 의 추세 상태로 t 의 손익을 가른다 — **사전에 아는 정보만**."""
    days = sorted(set(pnl) & set(state))
    rows = []
    for i in range(1, len(days)):
        s = state[days[i - 1]]                     # 어제까지의 상태
        rows.append((abs(s), pnl[days[i]]))
    if len(rows) < 200:
        print(f"  {name}: 표본 부족 ({len(rows)})")
        return
    #: 정렬도 셋으로 — 갈림(<0.4) · 보통 · 뚜렷(≥0.8, 다섯 중 넷 이상 한 방향)
    buckets = {"갈림 |x|<0.4": [], "보통 0.4~0.8": [], "뚜렷 |x|≥0.8": []}
    for a, p in rows:
        key = ("갈림 |x|<0.4" if a < 0.4 else
               ("보통 0.4~0.8" if a < 0.8 else "뚜렷 |x|≥0.8"))
        buckets[key].append(p)
    print(f"\n  [{name}]  총 {len(rows):,}일")
    print(f"    {'추세 정렬도':<14}{'일수':>7}{'하루 평균':>12}{'연환산':>13}{'승률':>7}")
    for k, v in buckets.items():
        if not v:
            continue
        ann = st.fmean(v) * 252
        win = sum(1 for x in v if x > 0) / len(v) * 100
        print(f"    {k:<14}{len(v):>7,}{st.fmean(v)/1e4:>10,.1f}만{ann/1e4:>11,.0f}만{win:>6.0f}%")


def main() -> int:
    state = trend_state()
    print(f"\n=== 추세 신호를 조기경보기로 — 정렬도 = macross 룩백 5개의 부호 평균 ===")
    print(f"신호는 **어제까지**의 정보로 만들고 오늘 손익을 가른다.")
    al = sorted(abs(v) for v in state.values())
    print(f"정렬도 분포: 중앙 {al[len(al)//2]:.2f} · |x|≥0.8 인 날 "
          f"{sum(1 for x in al if x >= 0.8)/len(al)*100:.0f}%\n")

    print("① MR 이 추세가 뚜렷할 때 더 아픈가")
    bucket_report("MR FUT-KTB3 (선물 평균회귀)", mr_daily("FUT-KTB3"), state)
    bucket_report("MR BSS 통합 (아홉 만기)", book_daily(), state)

    # ── ③ 방향 적중 — 손익이 아니라 적중률 ──────────────────────────────
    print("\n② 신호의 방향 적중률 — 다음 N일 선물 가격이 신호 쪽으로 갔나")
    f = futures.load()
    for t in futures.FUT_TENORS:
        s = f.series[t]
        d = [x.isoformat() for x in s.dates]
        px = [float(p) for p in s.price_adj]
        sigs = [cta.signal_series(px, "macross", lb) for lb in LOOKBACKS]
        align = [st.fmean([sg[i] for sg in sigs]) for i in range(len(px))]
        print(f"    {t}:", end="")
        for h in (5, 20, 60):
            hit = tot = 0
            hit_s = tot_s = 0
            for i in range(len(px) - h):
                a = align[i]
                if a == 0:
                    continue
                fwd = px[i + h] - px[i]
                if fwd == 0:
                    continue
                ok = (a > 0) == (fwd > 0)
                tot += 1
                hit += ok
                if abs(a) >= 0.8:                  # 뚜렷할 때만
                    tot_s += 1
                    hit_s += ok
            print(f"  {h:>3}일 전체 {hit/tot*100:>4.1f}% / 뚜렷 {hit_s/tot_s*100:>4.1f}%", end="")
        print()
    print("\n  ※ 50%가 동전이다. 경보기의 값어치는 «얼마나 넘나» 이지 손익이 아니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
