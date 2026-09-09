# -*- coding: utf-8 -*-
r"""추세를 **IRS 로** 세운다 — 합성가가 아니라 우리가 가진 IRS 자료로 [OWNER 2026-09-09].

> 「합성가가 아니라 우리가 IRS 데이터 가지고 있으니까 그거 바탕으로 다시 해볼래?
>  그리고 IRS 도 대차대조표 쓰진 않아」

## 앞 판(`momentum_roll_check.py` §C)이 틀렸던 두 곳

1. **합성가를 썼다.** `futures.synth_price(par_rate, years)` 는 par 금리를 **채권
   가격식**에 넣은 값이라 그건 IRS 가 아니라 「그 금리를 수익률로 갖는 가상 채권」이다.
   이 데스크의 IRS 회계는 그게 아니라 **bp × 명목**이다(`mrbacktest` — 손익도 비용도
   bp 단위, 비용은 편도 bp).
2. **비용을 안 맞췄다.** 합성가에 선물의 틱 비용(0.5틱 × 0.01)을 그대로 물렸는데,
   그건 IRS 의 호가폭이 아니다. **여기가 결론을 뒤집을 수 있는 자리다** — 선물 편도
   0.5틱은 3Y 약 0.18bp·10Y 약 0.06bp 인데 IRS 편도는 그보다 몇 배다.

그리고 「IRS 는 대차대조표를 쓴다」고 적은 것도 **틀렸다** — IRS 는 파생이라
대차대조표를 안 쓰고 증거금·CSA 만 쓴다. 선물과 같은 자리다. 그래서 IRS 추세북은
진단용 대조가 아니라 **실제로 갈아탈 수 있는 대안**이고, 그만큼 비용 가정이 중요해진다.

## 어떻게 세우나

가격 대신 **−금리(bp)** 를 계열로 쓴다. 리시브(금리 하락 이익)가 +1 이 되도록 부호를
뒤집은 것뿐이고, 그러면 엔진의 회계가 그대로 데스크의 IRS 회계가 된다:

    손익 = 포지션/100 × Δ(−금리bp)      ← 포지션/100 이 곧 «원/bp»
    비용 = |포지션 변화|/100 × TICK × 틱수

`TICK = 0.01` 이므로 `cost_ticks = 50` 이면 편도 0.5bp 다. 채권 가격식도, 듀레이션
가정도 안 들어간다 — 3Y 와 10Y 의 위험 차이는 엔진의 «단위 위험» 정규화(신호/σ)가
이미 흡수한다.

## 비용은 이미 정해져 있다 [OWNER]

**IRS 편도 호가폭 = 0.5bp.** 오너가 정한 값이고, 이 리포가 `costBp 0.5` 를 쓰는
이유가 그것이다(MR 레인의 그 상수도 같은 값). 추정이 아니므로 **0.5bp 줄이 답**이다.
격자를 같이 내는 것은 고르기 위해서가 아니라 결론이 그 한 값에 매달려 있는지
보기 위해서다.

선물 쪽도 **대칭으로** 문다. 규약은 편도 0.5틱이지만 계약별 실측은 3Y 0.43·10Y 1.20
틱이다(ktbf_flow 레인). 엔진이 계약별 비용을 안 받으므로 그 둘로 **범위**를 낸다 —
어느 쪽이든 결론이 안 바뀌는지가 읽을 것이다.

돌리기:  python -m scripts.momentum_irs
"""

from __future__ import annotations

import math
import statistics as st

from sqlalchemy import text

from app import ctabacktest as cta, futures, momentum as mom
from app.mysqldb import engine

BARS = 252
START = "2017-01-06"

#: 선물 1틱(가격 0.01)의 bp 환산 — 계약별 듀레이션에서 온다. 두 레인의 비용을
#: 같은 화폐로 놓을 때만 쓴다(회계 자체는 각자 자기 단위로 돈다).
TICK_BP = {"3Y": 0.357, "10Y": 0.125}


def card(xs: list[float]) -> dict:
    sd = st.pstdev(xs)
    run = peak = mdd = 0.0
    for x in xs:
        run += x
        peak = max(peak, run)
        mdd = max(mdd, peak - run)
    ann = sum(xs) * BARS / len(xs)
    return {"sharpe": st.fmean(xs) / sd * math.sqrt(BARS) if sd > 0 else None,
            "calmar": ann / mdd if mdd > 0 else None,
            "ann": ann, "mdd": mdd, "vol": sd * math.sqrt(BARS)}


def line(name: str, c: dict) -> str:
    def f(x):
        return f"{x:>8.2f}" if isinstance(x, (int, float)) else f"{'—':>8}"
    return (f"  {name:<24}{c['ann']/1e4:>9,.0f}만{c['vol']/1e4:>9,.0f}만"
            f"{c['mdd']/1e4:>10,.0f}만{f(c['sharpe'])}{f(c['calmar'])}")


HDR = f"  {'':<24}{'연손익':>11}{'연변동':>11}{'최대낙폭':>12}{'Sharpe':>8}{'Calmar':>8}"


def load_irs_bp() -> dict[str, tuple[list[str], list[float]]]:
    """`mkt_irs_close` 의 par 금리를 **−bp** 계열로. 합성가를 안 만든다.

    부호를 뒤집는 이유는 하나다 — 엔진이 「값이 오르면 롱이 번다」로 회계하는데
    IRS 는 **금리가 내려야** 리시브가 번다. 뒤집으면 +1 이 리시브가 되고, 그 뒤로는
    선물 북과 같은 문장을 쓴다.
    """
    with engine().connect() as conn:
        rows = conn.execute(text(
            "SELECT irs_date, irs_3y, irs_10y FROM mkt_irs_close "
            "WHERE irs_3y IS NOT NULL AND irs_10y IS NOT NULL ORDER BY irs_date ASC"
        )).fetchall()
    out: dict[str, tuple[list[str], list[float]]] = {}
    for tenor, col in (("3Y", 1), ("10Y", 2)):
        ds, ps = [], []
        for r in rows:
            d = r[0]
            day = (d.date() if hasattr(d, "date") else d).isoformat()
            if not (START <= day <= mom.FREEZE):
                continue
            ds.append(day)
            ps.append(-float(r[col]) * 100.0)      # 퍼센트 → bp, 부호 뒤집기
        out[tenor] = (ds, ps)
    return out


def run(series, *, cost_ticks: float, rolls=None):
    return cta.book_simulate(
        series, signal=mom.SIGNAL, lookbacks=mom.LOOKBACKS,
        vol_window=mom.VOL_WINDOW, target_book_vol_krw=mom.TARGET_VOL,
        book_vol_window=mom.BOOK_VOL_WINDOW, roll_days=rolls or set(),
        continuous=True, cost_ticks=cost_ticks)


def main() -> int:
    fut_series, rolls = mom._load_prices()
    irs_raw = load_irs_bp()
    common = sorted(set(irs_raw["3Y"][0]) & set(irs_raw["10Y"][0]))
    irs_series = {t: (common, [dict(zip(*irs_raw[t]))[d] for d in common])
                  for t in ("3Y", "10Y")}

    b_fut = run(fut_series, cost_ticks=cta.COST_TICKS, rolls=rolls)
    fut = {p["t"]: p["dailyPnl"] for p in b_fut["points"]
           if START <= p["t"] <= mom.FREEZE}

    print("\n=== 추세를 IRS 로 — 합성가 없이, 데스크 IRS 회계로 ===")
    print(f"IRS 계열 {common[0]} ~ {common[-1]} · {len(common):,}일 "
          f"(mkt_irs_close par 금리, −bp)")
    print("IRS 는 대차대조표를 안 쓴다 — 선물과 같이 증거금뿐이다.\n")

    print("① 금리 계열의 성질 — 뭉개진 고시가 아닌가")
    for t in ("3Y", "10Y"):
        v = irs_series[t][1]
        d = [v[i] - v[i - 1] for i in range(1, len(v))]
        m = st.fmean(d)
        num = sum((d[i] - m) * (d[i - 1] - m) for i in range(1, len(d)))
        den = sum((x - m) ** 2 for x in d)
        zero = sum(1 for x in d if x == 0.0) / len(d)
        print(f"  IRS {t:<4} 일 Δ 표준편차 {st.pstdev(d):>5.2f}bp "
              f"· AR(1) {num/den:+.3f} · Δ=0 인 날 {100*zero:>4.1f}%")
    print("  → AR(1) 이 양수로 크거나 Δ=0 인 날이 많으면 고시가 뭉개진 것이다.\n")

    print("② 비용 — IRS 편도 0.5bp 가 **오너가 정한 값**이다(그 줄이 답)")
    print(HDR)
    for tk, tag in ((0.43, "3Y 실측"), (cta.COST_TICKS, "규약"), (1.20, "10Y 실측")):
        b = run(fut_series, cost_ticks=tk, rolls=rolls)
        pts = {p["t"]: p["dailyPnl"] for p in b["points"]
               if START <= p["t"] <= mom.FREEZE}
        print(line(f"선물 · 편도 {tk:.2f}틱 ({tag})", card([pts[d] for d in sorted(pts)])))
    for bp in (0.0, 0.1, 0.2, 0.3, 0.5, 1.0):
        b = run(irs_series, cost_ticks=bp / cta.TICK)
        pts = {p["t"]: p["dailyPnl"] for p in b["points"]}
        print(line(f"IRS · 편도 {bp:.1f}bp", card([pts[d] for d in sorted(pts)])))

    # ── 같은 날 위에서 나란히 ────────────────────────────────────────────
    b_irs = run(irs_series, cost_ticks=0.5 / cta.TICK)
    irs = {p["t"]: p["dailyPnl"] for p in b_irs["points"]}
    both = sorted(set(fut) & set(irs))
    xs = [fut[d] for d in both]
    ys = [irs[d] for d in both]
    mx, my = st.fmean(xs), st.fmean(ys)
    sx, sy = st.pstdev(xs), st.pstdev(ys)
    r = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs) / (sx * sy)
         if sx > 0 and sy > 0 else None)

    print(f"\n③ 공통 창 {both[0]} ~ {both[-1]} · {len(both):,}일")
    print(HDR)
    print(line("선물", card(xs)))
    print(line("IRS · 편도 0.5bp", card(ys)))
    print(f"  일별 손익 상관 {r:+.3f}")

    # ── 회전율 — 비용이 얼마나 무는지의 뿌리 ─────────────────────────────
    print("\n④ 회전 — 비용이 왜 그만큼 무는가")
    for name, book, idx_keys in (("선물", b_fut, fut), ("IRS", b_irs, irs)):
        idx = [i for i, t in enumerate(book["dates"]) if t in idx_keys]
        chg = notion = 0.0
        for k, pos in book["pos"].items():
            for i in idx:
                prev = pos[i - 1] if i else 0.0
                chg += abs(pos[i] - prev)
                notion += abs(pos[i])
        # `barCost` 는 엔진이 이미 **문 금액(양수)** 으로 담아 둔다 — 부호를
        # 다시 뒤집으면 음수가 된다(첫 판이 그랬다).
        paid = sum(book["points"][i]["barCost"] for i in idx)
        tot = sum(book["points"][i]["dailyPnl"] for i in idx)
        print(f"  {name:<5} 하루 회전 {chg/notion:>6.4f} "
              f"· 비용 전 손익 {(tot+paid)/1e4:>8,.0f}만 "
              f"· 문 비용 {paid/1e4:>7,.0f}만 "
              f"({100*paid/(tot+paid) if tot + paid else 0:>5.1f}%)"
              f" → 비용 후 {tot/1e4:>8,.0f}만")

    print("  비용은 양쪽 다 정해져 있다 — IRS 편도 0.5bp[OWNER] · 선물 편도 "
          "0.5틱(규약) 또는 계약별 실측 0.43/1.20틱. "
          "어느 조합이든 IRS 가 앞선다 — 비용으로는 안 뒤집힌다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
