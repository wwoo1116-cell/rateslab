# -*- coding: utf-8 -*-
r"""추세가 **롤 때문에 나는 것 아닌가** — 트레이더 지적의 실측 [2026-09-09].

> 「지금 모멘텀 전략이 잘 나오는 건 연결선물의 롤링에 의한 것일 수 있으므로
>  IRS 를 통해서 더 명확하게 파악할 것」

## 왜 이 지적이 무거운가

이 레인의 가격은 `futures.price_adj` 이고, 그건 **벤더가 이어 붙인 연결 계열**이다
(`mkt_futures_investor_close.CLOSE` — 이 리포가 만든 것이 아니다). 계약이 분기마다
갈리므로 계열에는 43번의 이음매가 있고, 이 파일이 이미 그 크기를 적어 두었다 —
롤일 내재 Δ 가 **3Y 중앙 5.7bp·최대 27.2bp · 10Y 3.4/16.3bp**(`futures.roll_days`).

10Y 3.4bp 를 듀레이션 8 로 환산하면 롤 하나에 가격 0.27 포인트, 연 4회면 1.1
포인트다. 이 북의 평균 액면이 5.78억이라 **연 600만원대** — 북의 연손익(966만)과
같은 자릿수다. 곧 **이음매가 손익을 만들고 있다면 이 전략은 이음매를 파는 것**이고,
그건 아무도 실현할 수 없는 손익이다.

## 세 가지를 잰다

  A **이음매가 손익을 만드나** — 롤일 손익의 비중, 롤일 Δ 가 평시보다 큰가,
    그리고 롤일 손익을 아예 지우고 다시 채점하면 성적이 무너지나
  B **벤더가 실제로 조정했나** — 조정가 Δ 와 내재금리 Δ 가 롤일에 갈리는가
    (조정이 됐다면 조정가 Δ 는 평시처럼 조용하고 내재 Δ 만 튄다)
  C **★IRS 로 다시 세우면 사나** — `mkt_irs_close` 의 상수만기 par 금리는
    **롤도 조정도 없다.** 같은 신호·같은 엔진에 그 계열을 태워 성적을 비교한다.
    이게 트레이더가 말한 그 대조다.

## C 의 한계를 먼저 적는다

IRS 합성가는 선물이 아니다 — 베이시스(퓨처스왑)도, 실물 인도도, 증거금도 다르다.
그러니 **손익 수준을 옮겨 읽으면 안 되고**, 읽을 수 있는 것은 「가격에서 추세를
읽는 규칙이 이음매 없는 계열에서도 서느냐」 하나다. 그것이 지적의 핵심이다.

돌리기:  python -m scripts.momentum_roll_check
"""

from __future__ import annotations

import datetime as dt
import math
import statistics as st

from sqlalchemy import text

from app import ctabacktest as cta, futures, momentum as mom
from app.mysqldb import engine

BARS = 252


def card(xs: list[float]) -> dict:
    sd = st.pstdev(xs)
    run = peak = mdd = 0.0
    for x in xs:
        run += x
        peak = max(peak, run)
        mdd = max(mdd, peak - run)
    ann = sum(xs) * BARS / len(xs)
    return {
        "sharpe": st.fmean(xs) / sd * math.sqrt(BARS) if sd > 0 else None,
        "calmar": ann / mdd if mdd > 0 else None,
        "ann": ann, "mdd": mdd, "vol": sd * math.sqrt(BARS), "days": len(xs),
    }


def line(name: str, c: dict) -> str:
    def f(x, w=8, p=2):
        return f"{x:>{w}.{p}f}" if isinstance(x, (int, float)) else f"{'—':>{w}}"
    return (f"  {name:<26}{c['ann']/1e4:>9,.0f}만{c['vol']/1e4:>9,.0f}만"
            f"{c['mdd']/1e4:>10,.0f}만{f(c['sharpe'])}{f(c['calmar'])}")


HDR = f"  {'':<26}{'연손익':>11}{'연변동':>11}{'최대낙폭':>12}{'Sharpe':>8}{'Calmar':>8}"


def load_irs() -> dict[str, tuple[list[str], list[float]]]:
    """상수만기 IRS par 금리 → 선물과 **같은 폐형**으로 합성가.

    `futures.synth_price` 는 이 리포가 벤더 종가와 내재금리의 일치를 확인할 때
    쓰는 그 함수다. 같은 함수를 쓰면 두 계열이 같은 단위(가격 포인트)에 서고
    `book_simulate` 의 회계가 한 글자도 안 바뀐다.

    **이 계열에는 이음매가 없다** — 상수만기라 계약이 갈리는 날이 없다.
    """
    from irs_pricer.services.simulation.futures_pricing import synth_price

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
            ds.append((d.date() if hasattr(d, "date") else d).isoformat())
            ps.append(float(synth_price(float(r[col]), futures.FUT_YEARS[tenor])))
        out[tenor] = (ds, ps)
    return out


def main() -> int:
    series, rolls = mom._load_prices()
    b = mom._run_book(series, rolls)
    dates = b["dates"]
    start = "2017-01-06"
    idx = [i for i, t in enumerate(dates) if start <= t <= mom.FREEZE]
    pnl = {dates[i]: b["points"][i]["dailyPnl"] for i in idx}
    roll_set = {d for d in rolls if start <= d <= mom.FREEZE}

    print("\n=== 추세가 롤 때문인가 — 트레이더 지적 실측 ===")
    print(f"창 {dates[idx[0]]} ~ {dates[idx[-1]]} · {len(idx):,}일 "
          f"· 롤일 {len(roll_set & set(pnl))}일\n")

    # ── A 이음매가 손익을 만드나 ─────────────────────────────────────────
    on = [v for d, v in pnl.items() if d in roll_set]
    off = [v for d, v in pnl.items() if d not in roll_set]
    tot = sum(pnl.values())
    print("A 롤일이 손익을 만드나")
    print(f"  롤일 {len(on)}일 손익 합 {sum(on)/1e4:>8,.0f}만원 "
          f"({100*sum(on)/tot if tot else 0:>5.1f}% of {tot/1e4:,.0f}만)")
    print(f"  평시 {len(off)}일 손익 합 {sum(off)/1e4:>8,.0f}만원")
    print(f"  하루 평균 — 롤일 {st.fmean(on)/1e4:>6,.1f}만 · 평시 {st.fmean(off)/1e4:>6,.1f}만")
    print(f"  하루 표준편차 — 롤일 {st.pstdev(on)/1e4:>6,.1f}만 "
          f"· 평시 {st.pstdev(off)/1e4:>6,.1f}만 "
          f"(비 {st.pstdev(on)/st.pstdev(off):.2f})")
    print(f"  → 날 수 비중은 {100*len(on)/len(pnl):.1f}% 다. 손익 비중이 그보다"
          f" 훨씬 크면 이음매를 파는 것이다.\n")

    print("  롤일 손익을 **지우고** 다시 채점 (포지션은 그대로, 그날 손익만 0)")
    print(HDR)
    print(line("있는 그대로", card([pnl[d] for d in sorted(pnl)])))
    print(line("롤일 손익 제거", card([0.0 if d in roll_set else pnl[d]
                                   for d in sorted(pnl)])))

    # ── B 벤더가 조정했나 ────────────────────────────────────────────────
    print("\nB 조정가가 실제로 이어져 있나 — 롤일 Δ 를 평시와 비교")
    f = futures.load()
    for t in ("3Y", "10Y"):
        s = f.series[t]
        ds = [x.isoformat() if hasattr(x, "isoformat") else str(x) for x in s.dates]
        px = list(s.price_adj)
        imp = list(s.implied)
        rs = {d.isoformat() for d in futures.roll_days(list(s.dates))}
        d_on, d_off, y_on, y_off = [], [], [], []
        for i in range(1, len(ds)):
            if not (start <= ds[i] <= mom.FREEZE):
                continue
            dp = abs(px[i] - px[i - 1])
            bucket = d_on if ds[i] in rs else d_off
            bucket.append(dp)
            if imp[i] is not None and imp[i - 1] is not None:
                (y_on if ds[i] in rs else y_off).append(abs(imp[i] - imp[i - 1]) * 100)
        print(f"  {t:<4} 조정가 |Δ| 중앙 — 롤일 {st.median(d_on):.3f} "
              f"· 평시 {st.median(d_off):.3f} (비 {st.median(d_on)/st.median(d_off):.2f})")
        print(f"       내재금리 |Δ| 중앙 — 롤일 {st.median(y_on):.2f}bp "
              f"· 평시 {st.median(y_off):.2f}bp (비 {st.median(y_on)/st.median(y_off):.2f})")
    print("  → 조정가 비가 1 언저리이고 내재 비만 크면 «벤더가 이었다» 는 뜻이다.")

    # ── C IRS 로 다시 세우면 ─────────────────────────────────────────────
    print("\nC ★ IRS 상수만기로 다시 — **이음매가 없는 계열**")
    irs = load_irs()
    common = sorted(set(irs["3Y"][0]) & set(irs["10Y"][0]))
    common = [d for d in common if start <= d <= mom.FREEZE]
    irs_series = {t: ([d for d in common],
                      [dict(zip(*irs[t]))[d] for d in common]) for t in ("3Y", "10Y")}
    b_irs = cta.book_simulate(
        irs_series, signal=mom.SIGNAL, lookbacks=mom.LOOKBACKS,
        vol_window=mom.VOL_WINDOW, target_book_vol_krw=mom.TARGET_VOL,
        book_vol_window=mom.BOOK_VOL_WINDOW, roll_days=set(), continuous=True)
    irs_pnl = {p["t"]: p["dailyPnl"] for p in b_irs["points"]}

    both = sorted(set(pnl) & set(irs_pnl))
    print(f"  공통 창 {both[0]} ~ {both[-1]} · {len(both):,}일 "
          f"(롤 비용 없음 — 갈아탈 계약이 없다)")
    print(HDR)
    print(line("선물 조정가 (지금 북)", card([pnl[d] for d in both])))
    print(line("IRS 상수만기", card([irs_pnl[d] for d in both])))

    xs = [pnl[d] for d in both]
    ys = [irs_pnl[d] for d in both]
    mx, my = st.fmean(xs), st.fmean(ys)
    sx, sy = st.pstdev(xs), st.pstdev(ys)
    r = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs) / (sx * sy)
         if sx > 0 and sy > 0 else None)
    print(f"\n  두 북의 일별 손익 상관 {r:+.3f}")
    print("  → 상관이 높고 성적이 비슷하면 추세는 이음매가 아니라 «가격»에서 온다.")
    print("     IRS 쪽이 크게 나쁘면 트레이더 지적이 맞다.")
    print("\n  ⚠ 수준을 옮겨 읽지 말 것 — IRS 합성가는 선물이 아니다"
          " (베이시스·인도·증거금이 다르다). 읽을 것은 «규칙이 서느냐» 하나다.")

    # ── D 그러면 왜 IRS 가 더 좋은가 — 격차를 가른다 ──────────────────────
    #
    # C 가 지적을 뒤집었다면 질문도 뒤집힌다. 격차의 후보는 둘이다:
    #   ① 롤 비용 — 선물 북만 보유 중 롤일마다 왕복 1틱을 문다
    #   ② 계열 자체 — IRS par 고시가 «뭉개져» 있으면 추세가 인위적으로 잘 선다
    # ②가 참이면 IRS 의 1.00 은 믿을 수가 없다. MR 레인이 AR(1) 로 걸린 그 함정과
    # 같은 자리라 **같은 자로 잰다.**
    print("\nD 격차를 가른다 — 롤 비용인가, 계열이 뭉개진 것인가")
    b_nr = cta.book_simulate(
        series, signal=mom.SIGNAL, lookbacks=mom.LOOKBACKS,
        vol_window=mom.VOL_WINDOW, target_book_vol_krw=mom.TARGET_VOL,
        book_vol_window=mom.BOOK_VOL_WINDOW, roll_days=set(), continuous=True)
    nr = {p["t"]: p["dailyPnl"] for p in b_nr["points"]}
    print(HDR)
    print(line("선물 · 롤 비용 있음(지금)", card([pnl[d] for d in both])))
    print(line("선물 · 롤 비용 뺌", card([nr[d] for d in both if d in nr])))
    print(line("IRS 상수만기", card([irs_pnl[d] for d in both])))
    print("  → 롤 비용을 빼도 IRS 에 한참 못 미치면 격차는 «계열»에서 온다.")

    print("\n  계열이 뭉개졌나 — 원계열 차분과 북 손익의 자기상관")
    from scripts.momentum_audit import ar1, kurtosis

    def diffs(vals):
        return [vals[i] - vals[i - 1] for i in range(1, len(vals))]

    for name, vals in (("선물 조정가 3Y", series["3Y"][1]),
                       ("선물 조정가 10Y", series["10Y"][1]),
                       ("IRS 합성가 3Y", irs_series["3Y"][1]),
                       ("IRS 합성가 10Y", irs_series["10Y"][1])):
        d = diffs(vals)
        print(f"  {name:<16} 차분 AR(1) {ar1(d):+.3f} · 초과첨도 {kurtosis(d):>6.1f}")
    print(f"  {'선물 북 손익':<16} AR(1) {ar1([pnl[d] for d in both]):+.3f} "
          f"· 초과첨도 {kurtosis([pnl[d] for d in both]):>6.1f}")
    print(f"  {'IRS 북 손익':<16} AR(1) {ar1([irs_pnl[d] for d in both]):+.3f} "
          f"· 초과첨도 {kurtosis([irs_pnl[d] for d in both]):>6.1f}")
    print("  → IRS 원계열 차분의 AR(1) 이 양수로 크면 **고시가 뭉개진 것**이고,"
          " 그 위의 추세 성적은 부풀어 있다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
