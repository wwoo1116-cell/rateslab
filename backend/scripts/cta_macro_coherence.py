# -*- coding: utf-8 -*-
r"""원화에 머문 채로 「추세 + 매크로 50/50」의 **정합성**을 검정한다 [OWNER 2026-09-08].

브레드스 실측이 「N 을 못 늘리면 Sharpe 0.6 대가 상한」이라고 말했다. 그러면
남는 질문은 「더 올릴 수 있나」가 아니라 **「지금 이 0.61 이 진짜인가」**다.
세 자리를 본다.

    ① 비용   두 레인이 안 맞는 10년물 비용에서 결론이 뒤집히나
    ② 부호   테마 넷의 경제 논리가 원화 자료에서 실제로 성립하나
    ③ 유의   섞기의 이득이 우연으로 나올 수 있는 크기인가

## ① 비용 — 미해결 항목을 여기서 닫는다

`ctabacktest.COST_TICKS = 0.5` 를 두 계약에 똑같이 물려 왔다. 그런데
`research\ktbf_flow\HANDOFF.md` 의 오너 실측은 편도 **0.15bp(금리)** 이고
듀레이션 환산이 **KTB3 0.43틱 · KTB10 1.20틱** 이다. 3년물은 맞고 10년물이
2.4배 싸게 매겨져 있다. 두 규약과 손익분기 배수를 나란히 낸다.

## ② 부호 — 거래 얹기 전에 원자료에서 성립하나

매매 규칙을 통과시키면 「신호가 맞았나」와 「크기 규칙이 맞았나」가 섞인다.
그래서 **포지션 없이** 본다: 테마 부호별로 이후 20·60·250일 선물 가격변화의
평균을 갈라 t 값을 낸다. 부호는 `build_themes.py` 가 결과 보기 전에 못박은
그것이고, 여기서 뒤집지 않는다.

## ③ 유의 — 귀무분포를 만들어 경험적 p 를 낸다

공식 대신 **순환이동 귀무분포**를 쓴다. 매크로 신호를 통째로 밀면 자기상관·
롱숏비중·회전이 전부 보존된 채 가격과의 정렬만 깨진다. 그렇게 만든 가짜
매크로로 똑같이 섞어 Calmar 를 200개 모으고, 진짜가 그 분포의 어디에 서는지
본다. 이게 이 표본에서 낼 수 있는 가장 정직한 p 다.

⚠ 그래도 사전등록은 아니다. 부호 넷은 내가 정했다.

돌리기:  python -m scripts.cta_macro_coherence
"""

from __future__ import annotations

import csv
import math
import os
import statistics as st

from app import ctabacktest as cta, futures, mrmetrics as mrm

PROJECTS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "..", "..", "..", ".."))
THEMES_CSV = os.path.join(PROJECTS, "data", "krw-macro-vintage", "out",
                          "macro_themes_daily.csv")

LOOKBACKS = (20, 40, 60, 120, 250)
VOL_WINDOW = 60
BOOK_VOL_WINDOW = 120
TARGET_VOL = 1_000_000.0
BARS = 252
THEMES = ("cycle", "policy", "trade", "risk")
#: [ktbf_flow 레인 오너 실측] 편도 0.15bp 를 듀레이션으로 환산한 계약별 틱 수.
COST_MEASURED = {"3Y": 0.43, "10Y": 1.20}
#: 귀무 표본 수. 인자로 덮어쓴다 — 212회는 10분이 넘어 못 기다린다.
N_NULL = int(os.sys.argv[1]) if len(os.sys.argv) > 1 else 60


def load():
    f = futures.load()
    series, rolls = {}, set()
    for t in futures.FUT_TENORS:
        s = f.series[t]
        d = [x.isoformat() for x in s.dates]
        series[t] = (d, [float(p) for p in s.price_adj])
    rolls = {x.isoformat() for x in futures.roll_days(list(f.series["3Y"].dates))}
    macro: dict[str, dict[str, float]] = {c: {} for c in ("macro_sign",) + THEMES}
    with open(THEMES_CSV, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            day = row["date"][:10]
            for c in macro:
                v = row.get(c, "")
                if v not in ("", "nan", "NA"):
                    macro[c][day] = float(v)
    return series, rolls, macro


def sharpe(daily: list[float]) -> float:
    sd = st.pstdev(daily)
    return st.fmean(daily) / sd * math.sqrt(BARS) if sd > 0 else 0.0


def calmar(daily: list[float]) -> float:
    run = peak = 0.0
    mdd = 0.0
    for x in daily:
        run += x
        peak = max(peak, run)
        mdd = max(mdd, peak - run)
    ann = sum(daily) * BARS / len(daily)
    return ann / mdd if mdd > 0 else 0.0


class Fast:
    """`book_simulate` 와 **같은 산술**인데 변동성을 한 번만 잰다.

    귀무분포를 200번 돌리려면 계약별 `realized_vol` 재계산이 병목이다. 그건
    신호와 무관하므로 캐시한다. 같은 값을 내는지는 `main` 이 실측으로 대조한다.
    """

    def __init__(self, series, rolls, cost: dict[str, float]):
        self.series, self.rolls, self.cost = series, rolls, cost
        self.dates = sorted(set().union(*[set(d) for d, _ in series.values()]))
        self.at = {t: i for i, t in enumerate(self.dates)}
        self.n = len(self.dates)
        self.vol = {k: cta.realized_vol(p, VOL_WINDOW) for k, (_d, p) in series.items()}
        self.px = {k: dict(zip(d, p)) for k, (d, p) in series.items()}
        self.trend = {k: [st.fmean([sg[j] for sg in
                                    [cta.signal_continuous(p, "macross", lb)
                                     for lb in LOOKBACKS]])
                          for j in range(len(p))]
                      for k, (_d, p) in series.items()}

    def run(self, ext: dict[str, float] | None) -> list[dict]:
        unit = {k: [0.0] * self.n for k in self.series}
        for k, (d, _p) in self.series.items():
            v = self.vol[k]
            for j, day in enumerate(d):
                if v[j] is None or v[j] <= 0:
                    continue
                s = ext.get(day, 0.0) if ext is not None else self.trend[k][j]
                unit[k][self.at[day]] = s / v[j]
        raw = [0.0] * self.n
        for k in self.series:
            p = self.px[k]
            for i in range(1, self.n):
                t0, t1 = self.dates[i - 1], self.dates[i]
                if t0 in p and t1 in p:
                    raw[i] += unit[k][i - 1] * (p[t1] - p[t0])
        scale = [0.0] * self.n
        for i in range(self.n):
            seg = [x for x in raw[max(1, i - BOOK_VOL_WINDOW + 1):i + 1] if x != 0.0]
            if len(seg) >= max(20, BOOK_VOL_WINDOW // 3):
                sd = st.pstdev(seg)
                if sd > 0:
                    scale[i] = TARGET_VOL / sd
        pos = {k: [unit[k][i] * scale[i] * 100.0 for i in range(self.n)]
               for k in self.series}
        out = []
        for i in range(self.n):
            pnl = cost = 0.0
            for k in self.series:
                p = self.px[k]
                t0 = self.dates[i - 1] if i else None
                t1 = self.dates[i]
                prev = pos[k][i - 1] if i else 0.0
                if i and t0 in p and t1 in p and prev:
                    pnl += prev / 100.0 * (p[t1] - p[t0])
                cost -= abs(pos[k][i] - prev) / 100.0 * cta.TICK * self.cost[k]
                if prev and t1 in self.rolls:
                    cost -= abs(prev) / 100.0 * cta.TICK * 1.0
            out.append({"t": t1, "dailyPnl": pnl + cost, "barCost": -cost})
        return out


def blend(a, b):
    bi = {p["t"]: p for p in b}
    return [{"t": p["t"], "dailyPnl": 0.5 * p["dailyPnl"] + 0.5 * bi[p["t"]]["dailyPnl"],
             "barCost": 0.5 * p["barCost"] + 0.5 * bi[p["t"]]["barCost"]}
            for p in a if p["t"] in bi]


def main() -> int:
    series, rolls, macro = load()
    sign = macro["macro_sign"]
    start = min(sign)
    print(f"\n=== 원화 정합성 검정 · {start} ~ {max(sign)} ===")

    # ── ① 비용 ────────────────────────────────────────────────────────
    print("\n① 비용 규약을 바꾸면")
    print(f"  {'':<26}{'추세 Sharpe':>12}{'매크로':>9}{'50/50':>9}"
          f"{'50/50 Calmar':>14}{'총비용(만)':>11}")
    saved = {}
    for lab, cost in (("데스크 0.5틱 (지금)", {"3Y": 0.5, "10Y": 0.5}),
                      ("실측 0.15bp 환산", COST_MEASURED),
                      ("실측 x2 (보수)", {k: 2 * v for k, v in COST_MEASURED.items()}),
                      ("비용 0 (상한 확인)", {"3Y": 0.0, "10Y": 0.0})):
        eng = Fast(series, rolls, cost)
        tr = [p for p in eng.run(None) if p["t"] >= start]
        mc = [p for p in eng.run(sign) if p["t"] >= start]
        bl = blend(tr, mc)
        saved[lab] = (tr, mc, bl, eng)
        dl = [p["dailyPnl"] for p in bl]
        print(f"  {lab:<26}{sharpe([p['dailyPnl'] for p in tr]):>12.2f}"
              f"{sharpe([p['dailyPnl'] for p in mc]):>9.2f}{sharpe(dl):>9.2f}"
              f"{calmar(dl):>14.2f}"
              f"{sum(p['barCost'] for p in bl)/1e4:>11,.0f}")

    # 손익분기 — 문 돈 위의 닫힌형(mrmetrics 와 같은 산술)
    tr, mc, bl, _ = saved["데스크 0.5틱 (지금)"]
    paid = sum(p["barCost"] for p in bl)
    tot = sum(p["dailyPnl"] for p in bl)
    print(f"\n  50/50 손익분기 비용 배수 = {1 + tot/paid:.1f}배 "
          f"(0.5틱 기준 → 편도 {(1 + tot/paid)*0.5:.1f}틱까지 견딤)")

    # ── ② 부호 ────────────────────────────────────────────────────────
    print("\n② 테마 부호가 원자료에서 성립하나 (포지션 없이, KTB10 조정가 변화)")
    d10, p10 = series["10Y"]
    at = {t: i for i, t in enumerate(d10)}
    print(f"  {'테마':<10}{'지평':>6}{'롱일때':>10}{'숏일때':>10}{'차이':>10}{'t':>8}{'N':>7}")
    for th in THEMES:
        s = macro[th]
        for h in (20, 60, 250):
            up, dn = [], []
            for day, v in s.items():
                i = at.get(day)
                if i is None or i + h >= len(p10) or v == 0:
                    continue
                r = p10[i + h] - p10[i]
                (up if v > 0 else dn).append(r)
            if len(up) < 30 or len(dn) < 30:
                continue
            diff = st.fmean(up) - st.fmean(dn)
            se = math.sqrt(st.pvariance(up)/len(up) + st.pvariance(dn)/len(dn))
            # 겹치는 창이라 t 는 과대하다 — 아래에서 h 로 나눠 보정한다.
            t = diff / se / math.sqrt(h) if se > 0 else 0.0
            print(f"  {th:<10}{h:>6}{st.fmean(up):>10.3f}{st.fmean(dn):>10.3f}"
                  f"{diff:>10.3f}{t:>8.2f}{len(up)+len(dn):>7,}")

    # ── ③ 유의 ────────────────────────────────────────────────────────
    print(f"\n③ 순환이동 귀무분포 {N_NULL}회 — 섞기의 이득이 우연인가")
    eng = saved["데스크 0.5틱 (지금)"][3]
    tr = saved["데스크 0.5틱 (지금)"][0]
    days = sorted(sign)
    real_c = calmar([p["dailyPnl"] for p in blend(tr, saved["데스크 0.5틱 (지금)"][1])])
    real_s = sharpe([p["dailyPnl"] for p in blend(tr, saved["데스크 0.5틱 (지금)"][1])])
    nc, ns = [], []
    step = max(1, (len(days) - 240) // N_NULL)
    for off in range(120, len(days) - 120, step):
        sh = {days[i]: sign[days[(i + off) % len(days)]] for i in range(len(days))}
        mcx = [p for p in eng.run(sh) if p["t"] >= start]
        bx = blend(tr, mcx)
        dl = [p["dailyPnl"] for p in bx]
        nc.append(calmar(dl))
        ns.append(sharpe(dl))
    nc.sort()
    ns.sort()
    pc = sum(1 for x in nc if x >= real_c) / len(nc)
    ps = sum(1 for x in ns if x >= real_s) / len(ns)
    tr_c = calmar([p["dailyPnl"] for p in tr])
    beat = sum(1 for x in nc if x >= tr_c) / len(nc)
    print(f"  귀무 {len(nc)}개 · Calmar 중앙 {nc[len(nc)//2]:.2f} "
          f"(5~95% {nc[int(.05*len(nc))]:.2f}~{nc[int(.95*len(nc))]:.2f})")
    print(f"  진짜 50/50 Calmar {real_c:.2f}  →  경험적 p = {pc:.3f}")
    print(f"  진짜 50/50 Sharpe {real_s:.2f}  →  경험적 p = {ps:.3f}")
    print(f"  ※ 가짜 매크로를 섞어도 추세 단독({tr_c:.2f})을 넘는 비율 {100*beat:.0f}% "
          f"— 「반만 태우는 것」자체의 효과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
