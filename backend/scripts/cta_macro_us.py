# -*- coding: utf-8 -*-
r"""미국 매크로가 KTB 를 더 잘 설명하나 + 부호가 나라를 넘어 서나 [OWNER 2026-09-08].

## 왜 이걸 재나

앞선 검정에서 **KTB10 = β x UST10 이 20일 지평 R² 0.567 · 60일 0.531 · 250일
0.448** 로 나왔다. 일별로는 0.056 뿐이라 놓칠 뻔했는데, 중기에서는 미국이
한국 금리 변동의 절반을 설명한다. 그러면 정직한 의심이 하나 선다 —

    「원화 국채의 매크로 축은 한국 매크로가 아니라 미국 매크로 아닌가」

## 두 가지를 나눠 본다

    ① 국내 대 미국   같은 규격의 경기순환 신호를 한국판·미국판으로 만들어
                     KTB10 선도수익에 각각 회귀한다. 이게 진짜 질문이다 —
                     네 테마 중 «비가격» 은 경기순환 하나뿐이므로.
    ② 외적 타당성    한국에서 정한 부호 규약을 그대로 미국 채권에 대면
                     방향이 서는가. 서면 경제 논리가 나라를 넘는다는 뜻이고,
                     그건 원화 표본을 늘리는 것보다 강한 증거다.

## 미국판은 세 테마다

위험선호를 뺐다 — 미국 주가지수 계열이 디스크에 없다(`Momentum` 마스터 108열,
`env_panel2` 어디에도 S&P 가 없다). **없는 것을 근사로 채우지 않는다.** 나머지
셋은 규격이 한국판과 같다.

    경기순환  OECD USA `EX`+`CP` 빈티지의 1년 변화 평균      부호 −
    통화정책  UST 2Y 1년 변화                               부호 −
    국제교역  DXY 1년 로그변화                              부호 +

돌리기:  python -m scripts.cta_macro_us
"""

from __future__ import annotations

import csv
import math
import os
import statistics as st

from app import ctabacktest as cta, futures
from scripts.cta_macro_weights import calmar, newey_west_t, sharpe

PROJECTS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "..", "..", "..", ".."))
LANE = os.path.join(PROJECTS, "data", "krw-macro-vintage", "out")
BARS_1Y = 250
DUR_UST10 = 8.0


def read_csv_cols(path, cols, datecol="date"):
    out = {c: {} for c in cols}
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        d = r[datecol][:10]
        for c in cols:
            v = r.get(c, "")
            if v not in ("", "nan", "NA"):
                out[c][d] = float(v)
    return out


def pit_cycle(path: str) -> dict[str, float]:
    """빈티지 패널 → `available_from` 별 경기순환 원값(성장·물가 가속 평균)."""
    ex, cp = {}, {}
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        if r["dg_1y"] in ("", "nan"):
            continue
        (ex if r["measure"] == "EX" else cp if r["measure"] == "CP" else {})[
            r["available_from"][:10]] = float(r["dg_1y"])
    both = sorted(set(ex) & set(cp))
    return {d: (ex[d] + cp[d]) / 2.0 for d in both}


def ffill(src: dict[str, float], days: list[str]) -> dict[str, float]:
    keys = sorted(src)
    out, j, cur = {}, 0, None
    for d in days:
        while j < len(keys) and keys[j] <= d:
            cur = src[keys[j]]
            j += 1
        if cur is not None:
            out[d] = cur
    return out


def diff_sign(s: dict[str, float], days: list[str], lb: int) -> dict[str, float]:
    out = {}
    for i in range(lb, len(days)):
        a, b = s.get(days[i]), s.get(days[i - lb])
        if a is not None and b is not None:
            out[days[i]] = math.copysign(1.0, a - b) if a != b else 0.0
    return out


def main() -> int:
    f = futures.load()
    series = {t: ([x.isoformat() for x in f.series[t].dates],
                  [float(p) for p in f.series[t].price_adj])
              for t in futures.FUT_TENORS}
    rolls = {x.isoformat() for x in futures.roll_days(list(f.series["3Y"].dates))}
    d10, p10 = series["10Y"]
    at = {t: i for i, t in enumerate(d10)}

    e1 = read_csv_cols(os.path.join(PROJECTS, "research", "ktbf_flow", "env_panel.csv"),
                       ["ust2", "ust10"])
    e2 = read_csv_cols(os.path.join(PROJECTS, "research", "ktbf_flow", "env_panel2.csv"),
                       ["dxy"])
    days = sorted(set(e1["ust2"]) & set(e1["ust10"]) & set(e2["dxy"]) & set(d10))
    print(f"공통 영업일 {days[0]} ~ {days[-1]} · {len(days):,}일")

    cyc_kr = ffill(pit_cycle(os.path.join(LANE, "macro_pit_monthly.csv")), days)
    cyc_us = ffill(pit_cycle(os.path.join(LANE, "macro_pit_monthly_USA.csv")), days)

    # 부호 규약 — 한국판과 같다. 가속하면 숏, 긴축이면 숏, 통화 강세면 롱.
    sig = {}
    sig["cycle_KR"] = {d: -math.copysign(1.0, v) for d, v in cyc_kr.items() if v}
    sig["cycle_US"] = {d: -math.copysign(1.0, v) for d, v in cyc_us.items() if v}
    sig["policy_US"] = {d: -v for d, v in diff_sign(e1["ust2"], days, BARS_1Y).items()}
    lg = {d: math.log(v) for d, v in e2["dxy"].items() if v > 0}
    sig["trade_US"] = diff_sign(lg, days, BARS_1Y)

    us_keys = ("cycle_US", "policy_US", "trade_US")
    common = sorted(set.intersection(*[set(sig[k]) for k in us_keys]))
    sig["macro_US"] = {d: st.fmean(sig[k][d] for k in us_keys) for d in common}

    # 한국 합성(기존 산출물)
    rows = {r["date"][:10]: r for r in csv.DictReader(
        open(os.path.join(LANE, "macro_themes_daily.csv"), encoding="utf-8-sig"))}
    sig["macro_KR"] = {d: float(r["macro_sign"]) for d, r in rows.items()
                       if r["macro_sign"] not in ("", "nan")}

    # ── ① KTB10 선도수익 회귀 (Newey-West) ────────────────────────────
    print("\n① KTB10 선도수익 = a + b x 신호   (Newey-West, lag=h)")
    print(f"  {'신호':<12}{'지평':>6}{'b':>10}{'NW t':>9}{'N':>8}")
    for name in ("cycle_KR", "cycle_US", "macro_KR", "macro_US"):
        s = sig[name]
        for h in (20, 60, 250):
            xs, ys = [], []
            for day, v in s.items():
                i = at.get(day)
                if i is None or i + h >= len(p10) or v == 0:
                    continue
                xs.append(v)
                ys.append(p10[i + h] - p10[i])
            if len(xs) < 200:
                continue
            b, se, t = newey_west_t(ys, xs, h)
            print(f"  {name:<12}{h:>6}{b:>10.3f}{t:>9.2f}{len(xs):>8,}")

    # ── ② 외적 타당성 — 미국 신호가 «미국 채권» 을 예측하나 ────────────
    print("\n② 같은 부호 규약을 미국 채권에 (합성 UST10, P=100+Σ(−D·Δy))")
    us_days = sorted(set(e1["ust10"]))
    pu, cur = {}, 100.0
    for i, d in enumerate(us_days):
        if i:
            cur += -DUR_UST10 * (e1["ust10"][d] - e1["ust10"][us_days[i - 1]])
        pu[d] = cur
    print(f"  {'신호':<12}{'지평':>6}{'b':>10}{'NW t':>9}{'N':>8}")
    for name in ("macro_US", "cycle_US", "macro_KR"):
        s = sig[name]
        for h in (20, 60, 250):
            xs, ys = [], []
            for j, day in enumerate(us_days):
                if j + h >= len(us_days) or day not in s or s[day] == 0:
                    continue
                xs.append(s[day])
                ys.append(pu[us_days[j + h]] - pu[day])
            if len(xs) < 200:
                continue
            b, se, t = newey_west_t(ys, xs, h)
            print(f"  {name:<12}{h:>6}{b:>10.3f}{t:>9.2f}{len(xs):>8,}")

    # ── ③ 장부로 — 미국 축을 KTB 에 태우면 ────────────────────────────
    print("\n③ KTB 장부 (추세 5속도 대비)")
    K = dict(signal="macross", vol_window=60, target_book_vol_krw=1_000_000.0,
             book_vol_window=120, roll_days=rolls)
    start = max(min(sig["macro_KR"]), min(sig["macro_US"]))
    tr = {p["t"]: p["dailyPnl"] for p in cta.book_simulate(
        series, lookbacks=(20, 40, 60, 120, 250), continuous=True, **K)["points"]
        if p["t"] >= start}
    books = {}
    for name in ("macro_KR", "macro_US"):
        books[name] = {p["t"]: p["dailyPnl"] for p in cta.book_simulate(
            series, lookbacks=(20, 250), external_signals={k: sig[name] for k in series},
            **K)["points"] if p["t"] >= start}
    dd = sorted(set(tr) & set(books["macro_KR"]) & set(books["macro_US"]))
    print(f"  창 {dd[0]}~{dd[-1]} · {len(dd):,}일")
    print(f"  {'':<26}{'Calmar':>8}{'Sharpe':>8}")
    print(f"  {'추세 단독':<24}{calmar([tr[d] for d in dd]):>8.2f}"
          f"{sharpe([tr[d] for d in dd]):>8.2f}")
    for name in ("macro_KR", "macro_US"):
        b = books[name]
        solo = [b[d] for d in dd]
        mix = [0.5 * tr[d] + 0.5 * b[d] for d in dd]
        print(f"  {name+' 단독':<24}{calmar(solo):>8.2f}{sharpe(solo):>8.2f}")
        print(f"  {'추세 + '+name+' 50/50':<24}{calmar(mix):>8.2f}{sharpe(mix):>8.2f}")
    tri = [(tr[d] + books["macro_KR"][d] + books["macro_US"][d]) / 3 for d in dd]
    print(f"  {'추세+KR+US 1/3 씩':<24}{calmar(tri):>8.2f}{sharpe(tri):>8.2f}")
    x = [books["macro_KR"][d] for d in dd]
    y = [books["macro_US"][d] for d in dd]
    mx, my = st.fmean(x), st.fmean(y)
    sx, sy = st.pstdev(x), st.pstdev(y)
    print(f"\n  KR 매크로북 대 US 매크로북 손익 상관 "
          f"{sum((a-mx)*(b-my) for a, b in zip(x, y))/len(x)/(sx*sy):+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
