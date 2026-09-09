# -*- coding: utf-8 -*-
r"""표본을 2012년까지 늘려 다시 잰다 [OWNER 2026-09-08].

## 왜

2017-01~ 9.4년은 1년 신호 기준 **유효 독립 관측이 9개**다. t 값이 ±1.5 안에
갇힌 진짜 이유가 그것이고, 신호를 다듬어서 풀 수 있는 문제가 아니다.

## 무엇이 막고 있었나 · 어떻게 뚫었나

    OECD 빈티지        2010-02~ 이미 있음
    수출가중 바스켓     ECOS 위안 고시가 2016-01 부터 → **좁은 바스켓**으로 우회
                       (`krw-neer/src/pull_neer_long.py`, 구 위안 계열 접합,
                        커버리지 총수출의 61~68%, 넓은판과 12개월 상관 0.990)
    선물 가격          `futures` 계열이 2016-01-04 부터 → `ktbf_flow` 의
                       `ktb3_clean.csv`(2001~)·`ktb10_clean.csv`(2008~) 로 연장

## 선물 연장의 함정 — 롤 점프

`ktb*_clean.csv` 의 `close` 는 **조정가가 아니다.** 분기마다 근월물이 바뀌며
가격이 튄다. 크기로는 못 가른다(KTB10 일간 sd 0.428 인데 실제 급등락도 1.0 을
넘는다). 그래서 `ktbf_flow` 레인이 쓴 규칙을 옮긴다 —

    분기별 **ΔOI 가 가장 크게 감소한 날**을 롤일로 보고 그날 «차분» 을 버린다

차분만 버리므로 레벨은 이어지고, 추세 신호는 차분으로 만들어지니 정합적이다.
그날의 진짜 시장 움직임도 같이 버려지는데, 그걸 살리려면 종목별 가격이
필요하고 이 데스크에 없다(기억: 「종목별 국채선물은 파일로 없다」).

## 이어붙이는 규약 — 2016 이후는 **손대지 않는다**

2016-01-04~ 는 `futures.price_adj` 를 그대로 쓰고, 그 앞만 위 방식으로 잇는다.
그래야 앞선 결과들과 나란히 읽힌다. 겹치는 구간에서 두 방식의 차분을 대조해
연장분이 얼마나 거친지를 **숫자로 남긴다** — 그 대조가 이 스크립트의 게이트다.

돌리기:  python -m scripts.cta_macro_long
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
FLOW = os.path.join(PROJECTS, "research", "ktbf_flow")
NEER_LONG = os.path.join(PROJECTS, "data", "krw-neer", "out", "krw_neer_daily_long.csv")
PIT = os.path.join(PROJECTS, "data", "krw-macro-vintage", "out", "macro_pit_monthly.csv")
RATES = os.path.join(PROJECTS, "data", "ktb-supply", "out", "ecos_daily_rates.csv")
SPLICE = "2016-01-04"
BARS_1Y = 250
DUR_10Y = 8.0
LOOKBACKS = (20, 40, 60, 120, 250)


def read_flow(name: str) -> list[tuple[str, float, float | None]]:
    out = []
    for r in csv.DictReader(open(os.path.join(FLOW, name), encoding="utf-8-sig")):
        c, oi = r.get("close", ""), r.get("oi", "")
        if c in ("", "nan"):
            continue
        out.append((r["date"][:10], float(c),
                    float(oi) if oi not in ("", "nan") else None))
    return sorted(out)


def roll_days_from_oi(rows) -> set[str]:
    """분기마다 ΔOI 가 가장 크게 감소한 날. 그날의 차분을 버린다."""
    by_q: dict[str, list[tuple[float, str]]] = {}
    for i in range(1, len(rows)):
        d, _c, oi = rows[i]
        _pd, _pc, poi = rows[i - 1]
        if oi is None or poi is None:
            continue
        q = f"{d[:4]}Q{(int(d[5:7]) - 1) // 3 + 1}"
        by_q.setdefault(q, []).append((oi - poi, d))
    return {min(v)[1] for v in by_q.values() if v}


def continuous(rows, rolls: set[str]) -> dict[str, float]:
    """롤일 차분을 버린 연속 계열. 레벨은 이어지고 차분만 유효하다."""
    out, cur = {}, 100.0
    out[rows[0][0]] = cur
    for i in range(1, len(rows)):
        d, c, _ = rows[i]
        if d not in rolls:
            cur += c - rows[i - 1][1]
        out[d] = cur
    return out


def build_series():
    """2016 이후는 `futures.price_adj` 그대로, 그 앞은 연장분."""
    f = futures.load()
    modern = {t: dict(zip([x.isoformat() for x in f.series[t].dates],
                          [float(p) for p in f.series[t].price_adj]))
              for t in futures.FUT_TENORS}
    rolls_modern = {x.isoformat() for x in futures.roll_days(list(f.series["3Y"].dates))}

    ext, rolls_old, checks = {}, set(), {}
    for tenor, fn in (("3Y", "ktb3_clean.csv"), ("10Y", "ktb10_clean.csv")):
        rows = read_flow(fn)
        rl = roll_days_from_oi(rows)
        rolls_old |= rl
        cont = continuous(rows, rl)
        # 게이트 — 겹치는 구간에서 두 방식의 «차분» 이 얼마나 같은가
        days = sorted(d for d in cont if d in modern[tenor] and d >= SPLICE)
        a = [cont[days[i]] - cont[days[i - 1]] for i in range(1, len(days))]
        b = [modern[tenor][days[i]] - modern[tenor][days[i - 1]] for i in range(1, len(days))]
        ma, mb = st.fmean(a), st.fmean(b)
        sa, sb = st.pstdev(a), st.pstdev(b)
        rho = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / len(a) / (sa * sb)
        bad = sum(1 for x, y in zip(a, b) if abs(x - y) > 0.02)
        checks[tenor] = (rho, bad, len(a), len(rl))
        # 뒤로 잇기 — 2016-01-04 레벨을 맞추고 그 앞을 차분으로 채운다
        old = sorted(d for d in cont if d < SPLICE)
        merged = dict(modern[tenor])
        anchor = min(d for d in modern[tenor])
        lvl = modern[tenor][anchor]
        prev = None
        for d in reversed(old):
            if prev is None:
                nxt = min(dd for dd in cont if dd >= SPLICE) if any(
                    dd >= SPLICE for dd in cont) else None
                step = cont[nxt] - cont[d] if nxt else 0.0
                lvl = lvl - step
            else:
                lvl = lvl - (cont[prev] - cont[d])
            merged[d] = lvl
            prev = d
        ext[tenor] = merged
    series = {t: (sorted(v), [v[d] for d in sorted(v)]) for t, v in ext.items()}
    return series, rolls_modern | rolls_old, checks


def load_signal_long(days: list[str]) -> dict[str, float]:
    """긴 표본용 네 테마 — 규격은 `build_themes.py` 와 같고 원자료만 길다."""
    def col(path, cols, dc="date"):
        out = {c: {} for c in cols}
        for r in csv.DictReader(open(path, encoding="utf-8-sig")):
            for c in cols:
                v = r.get(c, "")
                if v not in ("", "nan"):
                    out[c][r[dc][:10]] = float(v)
        return out
    neer = col(NEER_LONG, ["neer", "n_ccy_used"])
    rates = col(RATES, ["ktb_1y", "ktb_10y"])
    kospi = col(os.path.join(PROJECTS, "research", "ktbf_flow", "env_panel2.csv"),
                ["kospi"])["kospi"]
    ex, cp = {}, {}
    for r in csv.DictReader(open(PIT, encoding="utf-8-sig")):
        if r["dg_1y"] in ("", "nan"):
            continue
        (ex if r["measure"] == "EX" else cp if r["measure"] == "CP" else {})[
            r["available_from"][:10]] = float(r["dg_1y"])
    cyc_src = {d: (ex[d] + cp[d]) / 2 for d in sorted(set(ex) & set(cp))}

    def ff(src):
        keys, out, j, cur = sorted(src), {}, 0, None
        for d in days:
            while j < len(keys) and keys[j] <= d:
                cur = src[keys[j]]
                j += 1
            if cur is not None:
                out[d] = cur
        return out

    cyc = ff(cyc_src)
    nz = {d: v for d, v in neer["neer"].items() if neer["n_ccy_used"].get(d, 0) >= 12}
    r1, r10 = rates["ktb_1y"], rates["ktb_10y"]
    ffk = ff({d: v for d, v in kospi.items()})
    ffn = ff(nz)
    ff1 = ff(r1)
    ff10 = ff(r10)

    def sgn(v):
        return 0.0 if v == 0 else math.copysign(1.0, v)

    out = {}
    for i in range(BARS_1Y, len(days)):
        d, d0 = days[i], days[i - BARS_1Y]
        parts = []
        if d in cyc:
            parts.append(sgn(-cyc[d]))
        if d in ff1 and d0 in ff1:
            parts.append(sgn(-(ff1[d] - ff1[d0])))
        if d in ffn and d0 in ffn and ffn[d] > 0 and ffn[d0] > 0:
            parts.append(sgn(math.log(ffn[d] / ffn[d0])))
        if all(k in x for k, x in ((d, ffk), (d0, ffk), (d, ff10), (d0, ff10))):
            eq = math.log(ffk[d] / ffk[d0])
            bd = -DUR_10Y * (ff10[d] - ff10[d0]) / 100.0
            parts.append(sgn(-(eq - bd)))
        if len(parts) == 4:
            out[d] = st.fmean(parts)
    return out


def main() -> int:
    series, rolls, checks = build_series()
    print("\n=== 선물 연장 게이트 (겹치는 2016~ 구간, 차분 대조) ===")
    for t, (rho, bad, n, nroll) in checks.items():
        print(f"  {t:<4} 상관 {rho:.6f} · |차이|>0.02 인 날 {bad}/{n:,} "
              f"· 검출 롤일(전기간) {nroll}")
    days = sorted(set(series["3Y"][0]) & set(series["10Y"][0]))
    print(f"  연장 후 {days[0]} ~ {days[-1]} · {len(days):,}일")

    sign = load_signal_long(days)
    print(f"\n=== 네 테마 완비 {len(sign):,}일 "
          f"{min(sign)} ~ {max(sign)} ({len(sign)/252:.1f}년) ===")

    d10, p10 = series["10Y"]
    at = {t: i for i, t in enumerate(d10)}
    print("\n① 합성 신호 → KTB10 선도수익 (Newey-West)")
    print(f"  {'표본':<16}{'지평':>6}{'b':>10}{'NW t':>9}{'N':>8}")
    old_sign = {d: v for d, v in sign.items() if d >= "2017-01-06"}
    for lab, s in (("긴 표본", sign), ("기존 창만", old_sign)):
        for h in (20, 60):
            xs, ys = [], []
            for day, v in s.items():
                i = at.get(day)
                if i is None or i + h >= len(p10):
                    continue
                xs.append(v)
                ys.append(p10[i + h] - p10[i])
            b, se, t = newey_west_t(ys, xs, h)
            print(f"  {lab:<16}{h:>6}{b:>10.3f}{t:>9.2f}{len(xs):>8,}")

    K = dict(signal="macross", vol_window=60, target_book_vol_krw=1_000_000.0,
             book_vol_window=120, roll_days=rolls)
    start = min(sign)
    tr = {p["t"]: p["dailyPnl"] for p in cta.book_simulate(
        series, lookbacks=LOOKBACKS, continuous=True, **K)["points"] if p["t"] >= start}
    mc = {p["t"]: p["dailyPnl"] for p in cta.book_simulate(
        series, lookbacks=(20, 250), external_signals={k: sign for k in series},
        **K)["points"] if p["t"] >= start}
    dd = sorted(set(tr) & set(mc))
    print(f"\n② 장부 · {dd[0]}~{dd[-1]} · {len(dd):,}일 ({len(dd)/252:.1f}년)")
    print(f"  {'':<22}{'Calmar':>8}{'Sharpe':>8}")
    for lab, dl in (("추세", [tr[d] for d in dd]),
                    ("매크로", [mc[d] for d in dd]),
                    ("50/50", [0.5*tr[d]+0.5*mc[d] for d in dd])):
        print(f"  {lab:<20}{calmar(dl):>8.2f}{sharpe(dl):>8.2f}")

    print("\n③ 세 구간으로 갈라 — 50/50 이 어디서나 이기나")
    n = len(dd)
    for lab, seg in (("초기 2013~2017", dd[:n//3]), ("중기", dd[n//3:2*n//3]),
                     ("최근", dd[2*n//3:])):
        a = [tr[d] for d in seg]
        b = [0.5*tr[d]+0.5*mc[d] for d in seg]
        m = [mc[d] for d in seg]
        print(f"  {lab:<16}{seg[0]}~{seg[-1]}  추세 {calmar(a):>5.2f} · "
              f"매크로 {calmar(m):>5.2f} · 50/50 {calmar(b):>5.2f}")

    print("\n④ 가중치 격자 (긴 표본)")
    best = max((w/20 for w in range(21)),
               key=lambda w: calmar([(1-w)*tr[d]+w*mc[d] for d in dd]))
    for w in (0.0, 0.25, 0.4, 0.5, 0.6, 0.75, 1.0):
        dl = [(1-w)*tr[d]+w*mc[d] for d in dd]
        print(f"  w={w:<5.2f} Calmar {calmar(dl):>5.2f} · Sharpe {sharpe(dl):>5.2f}")
    print(f"  표본내 최적 w = {best:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
