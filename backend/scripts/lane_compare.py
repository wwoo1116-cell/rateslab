# -*- coding: utf-8 -*-
r"""MR 과 Momentum 을 **같은 기준으로** 잰다 [OWNER 2026-09-09 — 「이거 MR 이랑
같은 기준으로 재줄 수는 없는거야?」].

## 공용 지표 모듈을 안 건드려도 된다

두 레인을 나란히 놓는 데 필요한 것은 **일별 손익 계열 둘**뿐이다. 거기서 나오는
Sharpe·Calmar·Martin 은 계열에 상수를 곱해도 안 변하므로(무차원), 오너가 정한
「분모를 안 만든다」 아래에서도 비교가 선다. mrmetrics 를 지금 손대지 않기로 한
결정(같은 날)과 충돌하지 않는다.

## 그런데 그냥 나란히 놓으면 셋이 어긋난다 — 그 셋을 여기서 맞춘다

  ① **창이 다르다.** MR 장부는 2020-01 부터(민평이 그때부터), Momentum 은
     2017-01 부터다. 겹치는 구간에서만 잰다 — 안 그러면 2017~2019 를 한쪽만
     갖고 비교하는 셈이다.
  ② **위험이 다르다.** Momentum 은 북 변동성 목표가 있고 MR 은 없다. 원화 열
     (낙폭·Ulcer)은 그래서 그대로 못 비교한다. **MR 통합의 실현 변동성**에
     맞춘 값을 같이 낸다(Man 2016 Figure 7 의 그 규약).
  ③ **수준이 다르다.** 이 MR 장부는 **증거금 상한을 안 본 판**이다(통합 SR 1.74,
     상한 아래 0.8). 레인 규율이 「수준을 옮기지 마라 — 상대 개선만 인용한다」라
     MR 의 절대 수치를 Momentum 과 «누가 크냐»로 읽으면 안 된다. 여기서 읽을 수
     있는 것은 **성질**(낙폭 표본 수·자기상관·꼬리·비용 쿠션)이다.

돌리기:  python -m scripts.lane_compare
"""

from __future__ import annotations

import json
import math
import os
import statistics as st

from app import momentum as mom
from scripts.momentum_audit import ar1, drawdowns, kurtosis

BARS = 252

#: MR 통합 장부(BSS 9다리) 캐시. **출처를 먼저 밝힌다**(레인 규율) —
#: `data\krw-crs\work\_book_20260907.json`, 2026-09-07 as-of, 룩백 60 · 진입 2σ ·
#: 청산 0.5σ · 손절 3.5σ · 비용 편도 0.5bp. 증거금 상한을 안 본 판이다.
MR_BOOK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", "data", "krw-crs", "work", "_book_20260907.json")


def load_mr() -> tuple[dict[str, float], dict]:
    with open(os.path.abspath(MR_BOOK), encoding="utf-8") as fh:
        d = json.load(fh)
    return {p["t"]: float(p["pnl"]) for p in d["points"]}, d


def sharpe_lo(xs: list[float], q: int = BARS) -> float | None:
    """자기상관을 보정한 연 Sharpe — Lo(2002)의 그 식.

    ## 왜 필요한가

    일별 Sharpe 에 √252 를 곱하는 것은 **날들이 서로 독립일 때만** 맞다. 손익이
    자기상관을 가지면 그 곱셈이 Sharpe 를 부풀린다. 이 자리가 두 레인에서
    비대칭이다 — MR 은 AR(1) 이 +0.21 이고(포지션 없는 날이 절반이라 0 이 뭉치고
    캐리가 매일 같은 방향으로 쌓인다), Momentum 은 −0.15 다.

    **한쪽만 부풀어 있는 자를 그대로 쓰면 그건 같은 기준이 아니다.**

        SR_연 = SR_일 · q / √( q + 2·Σ_{k=1}^{q−1} (q−k)·ρ_k )

    ρ_k 는 AR(1) 가정으로 ρ^k 를 쓴다(ρ 하나만 추정한다 — 252개를 추정하면
    표본이 감당 못 한다). ρ 가 0 이면 분모가 √q 라 √252 곱셈으로 되돌아온다.
    """
    sd = st.pstdev(xs)
    if sd <= 0:
        return None
    rho = ar1(xs)
    if rho is None:
        return None
    rho = max(-0.99, min(0.99, rho))
    acc = sum((q - k) * (rho ** k) for k in range(1, q))
    den = math.sqrt(q + 2 * acc)
    if den <= 0:
        return None
    return st.fmean(xs) / sd * q / den


def card(xs: list[float]) -> dict:
    sd = st.pstdev(xs)
    run = peak = mdd = 0.0
    path = []
    for x in xs:
        run += x
        peak = max(peak, run)
        dd = peak - run
        path.append(dd)
        mdd = max(mdd, dd)
    ann = sum(xs) * BARS / len(xs)
    ulcer = math.sqrt(sum(d * d for d in path) / len(path))
    dds = sorted(drawdowns(xs), key=lambda x: -x[0])
    return {
        "days": len(xs),
        "annVol": sd * math.sqrt(BARS),
        "annPnl": ann,
        "sharpe": st.fmean(xs) / sd * math.sqrt(BARS) if sd > 0 else None,
        "sharpeLo": sharpe_lo(xs),
        "mdd": mdd,
        "calmar": ann / mdd if mdd > 0 else None,
        "ulcer": ulcer,
        "martin": ann / ulcer if ulcer > 0 else None,
        "ddCount": len(dds),
        "ddBig": sum(1 for d in dds if d[0] >= 0.5 * mdd),
        "ar1": ar1(xs),
        "kurt": kurtosis(xs),
        "live": sum(1 for x in xs if x != 0.0) / len(xs),
    }


def main() -> int:
    mr_daily, mr_raw = load_mr()
    series, rolls = mom._load_prices()
    macro = mom._load_macro()

    b_trend = mom._run_book(series, rolls)
    b_macro = mom._run_book(series, rolls,
                            external={k: macro["macro_sign"] for k in series})
    t_all = {p["t"]: p["dailyPnl"] for p in b_trend["points"]}
    m_all = {p["t"]: p["dailyPnl"] for p in b_macro["points"]}

    # ① 공통 창 — 두 계열이 **둘 다 있는 날**만.
    days = sorted(set(mr_daily) & set(t_all) & set(m_all))
    days = [d for d in days if d <= mom.FREEZE]
    if not days:
        raise SystemExit("겹치는 날이 없어요")

    lanes = {
        "MR 통합(BSS 9다리)": [mr_daily[d] for d in days],
        "Momentum 추세": [t_all[d] for d in days],
        "Momentum 매크로": [m_all[d] for d in days],
        "Momentum 50/50": [0.5 * t_all[d] + 0.5 * m_all[d] for d in days],
    }
    cards = {k: card(v) for k, v in lanes.items()}

    print("\n=== MR 대 Momentum — 같은 창·같은 배터리 ===")
    print(f"공통 창 {days[0]} ~ {days[-1]} · {len(days):,}일")
    print("⚠ MR 장부는 증거금 상한을 안 본 판이다 — **수준이 아니라 성질만** 읽는다.\n")

    # ── 무차원 지표: 분모가 없어도 그대로 비교된다 ────────────────────────
    print("① 무차원 — 자본 기준이 없어도 나란히 놓인다")
    print(f"  {'':<22}{'Sharpe':>9}{'AR보정':>9}{'Calmar':>9}{'Martin':>9}")
    for k, c in cards.items():
        def f(x):
            return f"{x:>9.2f}" if x is not None else f"{'—':>9}"
        print(f"  {k:<22}{f(c['sharpe'])}{f(c['sharpeLo'])}{f(c['calmar'])}{f(c['martin'])}")
    print("  AR보정 = Lo(2002) — √252 곱셈은 날들이 독립일 때만 맞다.")

    # ── 원화 지표: MR 통합의 위험에 맞춘 뒤에만 읽는다 ───────────────────
    ref = cards["MR 통합(BSS 9다리)"]["annVol"]
    print(f"\n② 원화 — **MR 통합의 위험**({ref/1e4:,.0f}만원/년)에 맞춘 뒤")
    print(f"  {'':<22}{'위험비':>8}{'연손익':>11}{'최대낙폭':>11}{'Ulcer':>11}")
    for k, c in cards.items():
        g = ref / c["annVol"] if c["annVol"] > 0 else 1.0
        print(f"  {k:<22}{c['annVol']/ref:>8.2f}{c['annPnl']*g/1e4:>10,.0f}만"
              f"{c['mdd']*g/1e4:>10,.0f}만{c['ulcer']*g/1e4:>10,.0f}만")

    # ── 성질: 이 표가 이 문서의 값어치다 ─────────────────────────────────
    print("\n③ 성질 — 지표를 «믿어도 되나»")
    print(f"  {'':<22}{'낙폭 사건':>10}{'절반 초과':>10}{'AR(1)':>9}"
          f"{'초과첨도':>9}{'포지션 있는 날':>15}")
    for k, c in cards.items():
        print(f"  {k:<22}{c['ddCount']:>10}{c['ddBig']:>10}{c['ar1']:>+9.3f}"
              f"{c['kurt']:>9.1f}{100*c['live']:>14.1f}%")

    print("\n  기준 — 낙폭 절반 초과가 1건이면 Calmar 는 표본 하나짜리다.")
    print("         AR(1) 0.2 를 넘으면 일별 지표를 그대로 못 읽는다.")
    print("         초과첨도가 크면 Sharpe 의 표준오차를 정규 가정으로 못 쓴다.")

    # ── 비용 쿠션 ────────────────────────────────────────────────────────
    print("\n④ 비용이 결론을 흔드나 — 손익 0 이 되는 비용 배수")
    print(f"  MR 통합(BSS 9다리)   {mr_raw['summary']['breakevenCostMult']:>6.2f}배"
          f"  (편도 {mr_raw['cost']['bp']}bp → {mr_raw['summary']['breakevenCostBp']}bp)")
    print(f"  ⚠ 이 값만 MR 의 **자기 전체 창**(2020-01~2026-09-07)에서 온 것이다"
          f" — 장부 캐시가 일별 비용을 안 들고 있어 공통 창에서 다시 못 잰다.")
    print(f"  Momentum 추세        {mom_cost(series, rolls):>6.2f}배  (편도 0.5틱)")
    return 0


def mom_cost(series, rolls) -> float:
    from scripts.momentum_audit import cost_breakeven
    return cost_breakeven(series, rolls)


if __name__ == "__main__":
    raise SystemExit(main())
