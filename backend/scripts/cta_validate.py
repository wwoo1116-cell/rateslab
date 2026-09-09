# -*- coding: utf-8 -*-
"""국채선물 CTA — **된다. 다만 얇다.** [OWNER 2026-09-07].

## 결론

    최고 한 칸(macross 20)   Calmar 0.22 (표본밖 0.36) · Sortino 0.56
    룩백 5개 섞음(macross)   Calmar 0.29 (표본밖 0.25)
    신호3 x 룩백5 섞음       Calmar 0.18 (표본밖 0.19)

**고르든 섞든 0.1~0.36 대다.** MR 통합(1.76)의 5~15분의 1이다.
전략이 깨진 게 아니라 **이 시장에서 얇다.**

## ★★★ 내가 두 번 틀렸고, 오너 지적으로 고쳤다

**틀림 1 — 「손익의 대부분이 정적 숏이다」.** 표준 마켓타이밍 분해
(`PnL = 평균포지션 x 총수익 + (포지션−평균) x 수익`)로 재니 **정확히 반대**였다:

    신호        총손익      정적(평균포지션)      타이밍     숏비중
    macross 20  14,900만          −26만        14,926만      50%
    tsmom  250  13,259만         +407만        12,853만      53%
    donchian 40 13,362만           −9만        13,371만      53%

**정적 성분이 0 이고 타이밍이 100%다.** 평균 포지션이 0.2~0.7억(거의 중립)이고
숏 비중이 50~53%라 «계속 숏» 이 전혀 아니었다. 내가 「항상 숏 +7,029만」과
나란히 놓은 것은 **크기가 다른 딴 전략**이라 비교 자체가 틀렸다.

**틀림 2 — 「추세가 아니라 표본이다」.** [OWNER] 「금리가 오르는 창이랑 추세랑
같은 말 아니니」 — 맞다. **지속적 금리 상승은 추세이고 그걸 잡는 것이 추세추종이다.**
「표본 탓」이라는 말은 추세추종을 부정할 근거가 못 된다.

## PBO 0.80 은 무엇이었나 — 다른 질문이다

    「추세추종이 되나」        → 된다. 다섯 칸 전부 타이밍에서 9,490~14,926만.
    「격자가 최적 칸을 고르나」 → 못 한다(PBO 0.80 · 표본밖 순위 상관 −0.108).

**둘째가 첫째 때문일 수 있다.** 칸들이 서로 비슷하면 표본내 1등이 사실상 무작위로
정해지고 PBO 가 0.5 위로 오른다 — 조사해 온 그 비판(「후보가 늘면 PBO 가 오른다」)이
여기선 **동질성** 때문에 문다. 그래서 실무 CTA 처럼 **섞어** 봤는데(위 표),
섞어도 0.25~0.29 라 수준 자체가 오르지 않는다. **고르지 않는 것이 옳지만
고르지 않아도 얇다.**

## 배관검증 — 엔진 탓이 아니다 (NO-GO 전 의무)

    양성(추세+잡음)  상승 Calmar 4.15~8.14 · 하락 3.70~6.53   ← 양방향 다 잡는다
    음성(무추세)     Calmar −0.03~−0.11
    음성(무작위보행) 손익 −2,480~−5,276만
    비용            비용전 대비 10~19%                        ← 비용이 먹은 게 아니다

## 남은 것 — 이걸 지어서 알게 된 가장 쓸모 있는 사실

**MR 과 상관 −0.500.** 같은 선물 위의 MR(평균회귀)과 CTA(추세)가 정확히 반대
베팅이다. 이 데스크의 MR 이 `FUT-KTB3` 에서 **암묵적으로 추세의 반대편에 서
있다**는 뜻이고, 화면 어디에도 안 적혀 있다.

⚠ **맥락 하나** — Calmar 0.2~0.3 은 절대적으로 낮지만, 실물 매니지드퓨처스
지수의 장기 성적과 크게 동떨어진 수는 아니다(추세추종은 원래 그런 전략이다).
**MR 의 1.76 이 유별난 쪽**일 수 있다 — 아홉 다리 스프레드 전략과 두 계약
추세추종을 Calmar 하나로 나란히 놓는 것 자체가 공정한 비교는 아니다.
그 판단은 이 스크립트가 못 한다.

원화 선물에서 추세가 안 서면 화면을 지을 이유가 없다. 그래서 순서가
엔진 → **검정** → 화면이다.

오늘 만든 도구를 그대로 붙인다: `mrmetrics.score`(절대수익형 채점) ·
표본 반 가르기(`mr_grid_oos`) · CSCV/PBO(`mr_pbo`). 같은 자로 재야 MR 과
나란히 읽힌다.

## 네 가지를 답한다

    ① 서는가          신호 셋 × 룩백에서 무엇이 얼마나 버나
    ② 방향이 있나      롱·숏을 갈라 본다 — 공매도가 되는 자리의 값어치가 여기 있다
    ③ 격자가 정보인가  표본 반 가르기 + PBO. **신호계를 격자에 넣은 대가**를 잰다
    ④ MR 과 겹치나    같은 선물에 MR 도 돌고 있다. 상관이 높으면 새 전략이 아니다

## ⚠ ③ 이 이 스크립트의 존재 이유다

오너가 신호 셋을 다 격자에 넣기로 했다. 그건 자유도를 쓰는 선택이고, 그 대가는
**논쟁이 아니라 측정**으로 답한다 — 오늘 MR 격자에서 「N 이 커지면 PBO 가 저절로
오른다」는 비판이 안 물린 것을 확인했으니(N=18/54/162 에서 0.044/0.079/0.052),
같은 검정을 여기서 신호계 차원에 대고 한다.

돌리기:  python -m scripts.cta_validate
"""

from __future__ import annotations

import itertools
import math
import statistics as st

import numpy as np

from app import ctabacktest as cta, futures, mrmetrics as mrm

LOOKBACKS = (20, 40, 60, 120, 250)
VOL_WINDOWS = (20, 60, 120)
TARGET_VOL = 1_000_000.0            # 하루 표준편차 100만원
BARS = 252


def load():
    f = futures.load()
    out = {}
    for t in futures.FUT_TENORS:
        s = f.series[t]
        d = [x.isoformat() if hasattr(x, "isoformat") else str(x) for x in s.dates]
        px = list(s.price_adj)
        keep = [i for i, p in enumerate(px) if p is not None]
        out[t] = ([d[i] for i in keep], [float(px[i]) for i in keep])
    rolls = {x.isoformat() for x in futures.roll_days(list(f.series["3Y"].dates))}
    return out, rolls


def run(series, rolls, sig, lb, vw):
    """두 선물을 각각 돌리고 날짜로 포갠 장부."""
    dates = sorted(set().union(*[set(d) for d, _p in series.values()]))
    runs = []
    for _t, (d, p) in series.items():
        runs.append(cta.simulate(d, p, signal=sig, lookback=lb, vol_window=vw,
                                 target_vol_krw=TARGET_VOL, roll_days=rolls))
    return dates, cta.combine(runs, dates), runs


def card(dates, book, start=0):
    return mrm.score(dates, book["points"], book["trades"], start, 0.0)


def main() -> int:
    series, rolls = load()
    dates0 = sorted(set().union(*[set(d) for d, _p in series.values()]))
    print(f"\n=== 국채선물 CTA · {dates0[0]} ~ {dates0[-1]} · {len(dates0)}일 "
          f"({len(dates0)/BARS:.1f}년) · 3Y+10Y ===")
    print(f"변동성 목표 하루 {TARGET_VOL/1e4:,.0f}만원/계약 · 편도 {cta.COST_TICKS}틱 "
          f"· 롤 왕복 1틱\n")

    # ── ① 서는가 ─────────────────────────────────────────────────────────
    print("① 신호 × 룩백 (변동성창 60일 고정) — 총손익 / Calmar")
    print(f"  {'룩백':>5} " + "".join(f"{s:>22}" for s in cta.SIGNALS))
    grid = {}
    for lb in LOOKBACKS:
        row = f"  {lb:>5} "
        for sig in cta.SIGNALS:
            dates, book, _ = run(series, rolls, sig, lb, 60)
            s = card(dates, book)
            grid[(sig, lb, 60)] = s
            cal = s["calmar"]
            row += f"{s['totalPnl']/1e4:>13,.0f}만/{cal if cal is not None else float('nan'):>6.2f}"
        print(row)

    best = max(grid.items(), key=lambda kv: (kv[1]["calmar"] or -9))
    print(f"\n  Calmar 최고: {best[0][0]} 룩백 {best[0][1]}  "
          f"총손익 {best[1]['totalPnl']/1e4:,.0f}만 · Calmar {best[1]['calmar']:.2f} · "
          f"Sortino {best[1]['sortino']:.2f} · 거래 {best[1]['numTrades']}")

    # ── ② 방향 — 공매도가 되는 자리의 값어치 ──────────────────────────────
    print("\n② 롱·숏을 가른다 — 이 데스크에서 숏이 되는 유일한 자리다")
    sig, lb = best[0][0], best[0][1]
    dates, book, runs = run(series, rolls, sig, lb, 60)
    for name, want in (("롱만", 1), ("숏만", -1)):
        tot = days = 0.0, 0
        pnl = 0.0
        cnt = 0
        for r in runs:
            for p in r["points"]:
                if (p["position"] > 0 and want > 0) or (p["position"] < 0 and want < 0):
                    pnl += p["dailyPnl"]
                    cnt += 1
        print(f"  {name:<6} 손익 {pnl/1e4:>10,.0f}만원 · 그 방향으로 선 봉 {cnt:,}")
    both = card(dates, book)
    print(f"  {'합':<6} 손익 {both['totalPnl']/1e4:>10,.0f}만원 · Calmar {both['calmar']:.2f}")

    # ── ③ 격자가 정보인가 ────────────────────────────────────────────────
    print("\n③ 격자 — 표본 반 가르기 + PBO (신호계를 격자에 넣은 대가를 잰다)")
    cells, knobs = [], []
    for sig in cta.SIGNALS:
        for lb in LOOKBACKS:
            for vw in VOL_WINDOWS:
                dts, bk, _ = run(series, rolls, sig, lb, vw)
                at = {t: i for i, t in enumerate(dates0)}
                col = np.zeros(len(dates0))
                for p in bk["points"]:
                    i = at.get(p["t"])
                    if i is not None:
                        col[i] = p["dailyPnl"]
                cells.append(col)
                knobs.append((sig, lb, vw))
    M = np.column_stack(cells)
    print(f"  격자 {M.shape[1]}칸 ({len(cta.SIGNALS)} 신호 × {len(LOOKBACKS)} 룩백 "
          f"× {len(VOL_WINDOWS)} 변동성창)")

    half = len(dates0) // 2
    ins, oos = [], []
    for j, k in enumerate(knobs):
        a = mrm.score(dates0[:half], [{"dailyPnl": x, "barCost": 0.0} for x in M[:half, j]],
                      [], 0, 0.0)
        b = mrm.score(dates0, [{"dailyPnl": x, "barCost": 0.0} for x in M[:, j]],
                      [], half, 0.0)
        ins.append(a["calmar"]); oos.append(b["calmar"])
    ok = [i for i in range(len(knobs)) if ins[i] is not None and oos[i] is not None]
    if len(ok) >= 10:
        rho = _spearman([ins[i] for i in ok], [oos[i] for i in ok])
        order = sorted(ok, key=lambda i: -ins[i])
        byout = sorted(ok, key=lambda i: -oos[i])
        top5 = order[:5]
        print(f"  순위 상관(Calmar, 스피어만)  {rho:+.3f}")
        print(f"  앞절반 TOP5 의 뒤절반 등수   {[byout.index(i)+1 for i in top5]} /{len(ok)}")
        print(f"  앞절반 TOP5 뒤절반 Calmar 중앙 {st.median([oos[i] for i in top5]):+.3f}"
              f"  대  전체 중앙 {st.median([oos[i] for i in ok]):+.3f}")
        for i in top5[:3]:
            print(f"    {knobs[i]}  표본내 {ins[i]:.2f} → 표본밖 {oos[i]:.2f}")

    print("\n  PBO (CSCV) — 신호계 차원을 넣은 격자가 과적합하나")
    for S in (8, 10, 16):
        p = _pbo(M, S)
        print(f"    S={S:>2} ({math.comb(S, S//2):>6,}조합)  PBO {p:.3f}")
    print("  N 을 바꿔 가며 (비판 검정 — MR 격자에서 안 물렸던 그것)")
    rng = np.random.default_rng(11)
    for n in (9, 21, M.shape[1]):
        sub = M if n == M.shape[1] else M[:, rng.choice(M.shape[1], n, replace=False)]
        print(f"    N={n:>3}  PBO {_pbo(sub, 10):.3f}")

    # ── ④ MR 과 겹치나 ───────────────────────────────────────────────────
    print("\n④ MR 과 겹치나 — 같은 선물에 MR 도 돈다")
    print("  (겹치면 새 전략이 아니라 같은 베팅의 다른 이름이다)")
    try:
        from app import funding, mrbook                        # noqa: PLC0415
        from app.main import _mr_leg                           # noqa: PLC0415
        spec = funding.FundingSpec().validated()
        mr = _mr_leg("FUT-KTB3", spec=spec, lookback=60, entryZ=2.0, exitZ=0.5,
                     stopZ=3.5, costBp=0.5, notional=1_000_000.0, carry=True,
                     entryMode="level", timeStop=0, costModel="flat", regime="none",
                     reverseExit=False, countOpen=False)
        mrd = {d: p["dailyPnl"] for d, p in zip(mr["dates"], mr["r"]["points"])}
        cd = {p["t"]: p["dailyPnl"] for p in book["points"]}
        common = sorted(set(mrd) & set(cd))
        a = [mrd[t] for t in common]
        b = [cd[t] for t in common]
        c = _corr(a, b)
        print(f"  일별 손익 상관 (MR FUT-KTB3 대 CTA 북) = {c:+.3f}  ({len(common):,}일 겹침)")
        print("  → 0 근처면 서로 다른 것을 잡는다. 음수면 반대 베팅이다(추세 대 회귀).")
    except Exception as exc:                                   # noqa: BLE001
        print(f"  [못 잼] {exc}")
    return 0


def _corr(a, b):
    if len(a) < 2:
        return float("nan")
    sa, sb = st.pstdev(a), st.pstdev(b)
    if sa == 0 or sb == 0:
        return float("nan")
    ma, mb = st.fmean(a), st.fmean(b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / len(a) / (sa * sb)


def _spearman(xs, ys):
    def rank(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for pos, i in enumerate(o):
            r[i] = pos + 1
        return r
    return _corr(rank(xs), rank(ys))


def _pbo(M, S):
    T, N = M.shape
    cut = np.array_split(np.arange(T), S)
    sx = np.array([M[c].sum(axis=0) for c in cut])
    sxx = np.array([(M[c] ** 2).sum(axis=0) for c in cut])
    cnt = np.array([len(c) for c in cut], dtype=float)

    def sharpe(i):
        m = sx[i].sum(0) / cnt[i].sum()
        var = sxx[i].sum(0) / cnt[i].sum() - m * m
        return np.where(var > 0, m / np.sqrt(np.maximum(var, 1e-300)), -np.inf)

    lam = []
    for tr in itertools.combinations(range(S), S // 2):
        te = [i for i in range(S) if i not in tr]
        a, b = sharpe(list(tr)), sharpe(te)
        best = int(np.argmax(a))
        w = (float((b < b[best]).sum() + 1)) / (N + 1)
        w = min(max(w, 1e-9), 1 - 1e-9)
        lam.append(math.log(w / (1 - w)))
    return float((np.array(lam) < 0).mean())


if __name__ == "__main__":
    raise SystemExit(main())
