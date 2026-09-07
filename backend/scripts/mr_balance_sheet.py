# -*- coding: utf-8 -*-
"""다리를 **대차대조표로** 고르면 어떻게 되나 [OWNER 2026-09-07].

## 왜 묻나

MR 통합은 만기 아홉에 각각 **DV01 100만원/bp** 를 건다. 그런데 DV01 을 맞추면
**짧은 만기가 훨씬 큰 액면을 문다**(6M 201.9억 대 10Y 11.5억). Calmar·Sortino 는
분자도 분모도 원이라 자본이 **약분되어** 그 사실을 못 본다.

실측(2026-09-07, 대차대조표당 연수익):

    6M 0.33% · 9M 0.45% · 1Y 1.13% · 2Y 1.59% · 3Y 1.66%
    5Y 3.13% · 7Y 2.11% · 1.5Y 2.37% · **10Y 5.45%**

**6M·9M 이 액면의 55%를 쓰고 손익의 20%만 낸다.**

## 무엇을 재나 — **한 축으로 최적화하지 않는다**

[OWNER] 「데스크에서 구속하는 건 대차대조표긴 한데, 지금 받은 건 신경 쓰지 말고
자유롭게 하라는 쪽」. 그래서 어느 한 축을 정답으로 놓지 않고 **세 축을 나란히**
세운다 — 구속이 무엇이냐에 따라 답이 갈리기 때문이다.

    총손익      크기가 구속이 아닐 때
    Calmar      낙폭이 구속일 때        ← 지금 화면의 축
    대차대조표당  액면이 구속일 때        ← 오늘 새로 보이는 축

## 세 가지 판을 돌린다

    A. 현행        동일 DV01 (다리마다 100만원/bp)
    B. 동일 액면    다리마다 같은 액면 — 대차대조표가 구속일 때의 «자연스러운» 크기
    C. 부분집합     동일 DV01 을 유지하되 다리를 뺀다

**B 가 C 보다 먼저다.** 다리를 빼는 것은 「이 만기는 안 한다」는 큰 결정이고,
크기를 바꾸는 것은 같은 아홉을 다르게 잡는 일이라 되돌리기 쉽다.

## ★ 크기는 사후에 조정할 수 있다 — 엔진을 다시 안 돌린다

**거래 목록은 z 에만 달려 있다**(`mrbacktest` 머리) — 명목을 돌려도 진입·청산
날짜가 안 움직인다. 손익·비용·캐리가 전부 명목에 **선형**이므로, DV01 d 의 손익은
`(d / 1e6) ×` 기준 손익이다. 그래서 아홉을 한 번만 돌리고 크기는 곱셈으로 만든다.

## ⚠ 이건 **표본내 선택**이다

「대차대조표당이 낮은 다리를 뺀다」도 결국 표본을 보고 고르는 것이다. 그래서
**앞절반에서 고르고 뒤절반에서 채점**하는 판을 같이 낸다(오늘 만든
`mr_grid_oos.py`·`mr_pbo.py` 와 같은 규율). 그게 없으면 이 표는 사후설명이다.

돌리기:  python -m scripts.mr_balance_sheet
"""

from __future__ import annotations

import datetime as dt
import itertools
import statistics as st

from app import funding, mrbook, mrcarry as mrc, mrmetrics as mrm
from app.main import _mr_leg, _mr_principal_at


KN = dict(lookback=60, entryZ=2.0, exitZ=0.5, stopZ=3.5, costBp=0.5,
          notional=1_000_000.0, carry=True, entryMode="level", timeStop=0,
          costModel="flat", regime="none", reverseExit=False, countOpen=False)
BARS = 252


def load():
    """아홉 다리 — 기준 DV01(100만원/bp)에서 한 번만 돌린다."""
    spec = funding.FundingSpec().validated()
    out = []
    for sid, _l in mrbook.bss_series():
        try:
            leg = _mr_leg(sid, spec=spec, **KN)
        except Exception as exc:                               # noqa: BLE001
            print(f"  [빠짐] {sid}: {exc}")
            continue
        ten = mrc._tenor_of(sid)                               # noqa: SLF001
        faces = [p for t in leg["r"]["trades"]
                 if (p := _mr_principal_at(dt.date.fromisoformat(t["entryDate"]),
                                           ten, KN["notional"]))]
        if not faces:
            continue
        out.append({
            "id": sid, "tenor": ten, "leg": leg,
            #: 그 다리가 DV01 100만원/bp 를 내려면 사야 하는 액면(중앙값).
            "face1": st.median(faces),
        })
    return out


def series(legs, weights: dict[str, float], dates, at):
    """가중(= DV01 배수)을 준 장부의 (일별 손익, 일별 묶인 액면).

    손익이 명목에 선형이라 곱셈으로 만든다 — 엔진을 다시 안 돌린다.
    """
    n = len(dates)
    daily = [0.0] * n
    face = [0.0] * n
    for L in legs:
        w = weights.get(L["id"], 0.0)
        if w == 0.0:
            continue
        for j, p in enumerate(L["leg"]["r"]["points"]):
            i = at[L["leg"]["dates"][j]]
            daily[i] += p["dailyPnl"] * w
            if p["position"] != 0:
                face[i] += L["face1"] * w
    return daily, face


def score(dates, daily, face, start=0):
    pts = [{"dailyPnl": x, "barCost": 0.0} for x in daily]
    s = mrm.score(dates, pts, [], start, 0.0)
    win_face = face[start:]
    cap = st.fmean(win_face) if win_face else 0.0
    yrs = (len(dates) - start) / BARS
    s["_cap"] = cap
    s["_bs"] = (s["totalPnl"] / yrs / cap * 100) if cap else 0.0
    return s


def corr(a, b):
    if len(a) < 2:
        return None
    sa, sb = st.pstdev(a), st.pstdev(b)
    if sa == 0 or sb == 0:
        return None
    ma, mb = st.fmean(a), st.fmean(b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / len(a) / (sa * sb)


def diversification(legs, ids, weights, dates, at, start=0):
    ser = []
    for L in legs:
        if L["id"] not in ids:
            continue
        v = [0.0] * len(dates)
        for j, p in enumerate(L["leg"]["r"]["points"]):
            v[at[L["leg"]["dates"][j]]] = p["dailyPnl"] * weights.get(L["id"], 0.0)
        ser.append(v[start:])
    pairs = [c for i in range(len(ser)) for j in range(i + 1, len(ser))
             if (c := corr(ser[i], ser[j])) is not None]
    if not pairs:
        return None, None
    rho = st.fmean(pairs)
    n = len(ser)
    den = 1 + (n - 1) * rho
    return rho, (n / den if den > 0 else float(n))


def line(name, s, rho=None, eff=None, extra=""):
    return (f"  {name:<20} {s['totalPnl']/1e4:>9,.0f}만 "
            f"{-s['maxDrawdown']/1e4:>9,.0f}만 "
            f"{(s['calmar'] if s['calmar'] is not None else float('nan')):>6.2f} "
            f"{s['_cap']/1e8:>8,.1f}억 {s['_bs']:>7.2f}% "
            + (f"{rho:>6.3f} {eff:>5.1f}" if rho is not None else f"{'—':>6} {'—':>5}")
            + (f"  {extra}" if extra else ""))


HEAD = (f"  {'구성':<20} {'총손익':>11} {'최대낙폭':>11} {'Calmar':>6} "
        f"{'묶인액면':>9} {'대차당':>8} {'쌍상관':>6} {'유효N':>5}")


def main() -> int:
    legs = load()
    dates = sorted({t for L in legs for t in L["leg"]["dates"]})
    at = {t: i for i, t in enumerate(dates)}
    ids = [L["id"] for L in legs]
    ones = {i: 1.0 for i in ids}
    half = len(dates) // 2

    print(f"\n=== MR 통합 · {dates[0]} ~ {dates[-1]} · {len(dates)}봉 · 만기 {len(legs)}개 ===")

    # ── 다리별 — 어느 만기가 대차대조표를 버는가 ──────────────────────────
    print("\n① 다리별 (동일 DV01 100만원/bp)")
    print(HEAD)
    per = []
    for L in legs:
        w = {L["id"]: 1.0}
        d, f = series(legs, w, dates, at)
        s = score(dates, d, f)
        per.append((L, s))
        print(line(L["tenor"], s, extra=f"액면 {L['face1']/1e8:,.1f}억/다리"))

    # ── A. 현행 · B. 동일 액면 ────────────────────────────────────────────
    print("\n② 크기를 바꾼다 — 다리는 아홉 그대로")
    print(HEAD)
    dA, fA = series(legs, ones, dates, at)
    sA = score(dates, dA, fA)
    rA, eA = diversification(legs, set(ids), ones, dates, at)
    print(line("A 동일 DV01(현행)", sA, rA, eA))

    #: 동일 액면 — 다리마다 같은 액면을 물게 DV01 을 조정한다. 기준 액면은
    #: **현행 평균 다리 액면**으로 잡아 총 대차대조표를 비슷하게 둔다(크기가
    #: 아니라 «배분» 을 비교하는 것이 목적이라 규모를 맞춰야 공정하다).
    target = st.fmean([L["face1"] for L in legs])
    wB = {L["id"]: target / L["face1"] for L in legs}
    dB, fB = series(legs, wB, dates, at)
    sB = score(dates, dB, fB)
    rB, eB = diversification(legs, set(ids), wB, dates, at)
    print(line("B 동일 액면", sB, rB, eB,
               extra=f"DV01 {min(wB.values()):.2f}~{max(wB.values()):.1f}배"))

    # ── C. 부분집합 — 대차대조표당 순으로 하나씩 더한다 ────────────────────
    print("\n③ 다리를 뺀다 — 대차대조표당 순으로 하나씩 더하며 (동일 DV01)")
    print(HEAD)
    order = [L for L, _s in sorted(per, key=lambda x: -x[1]["_bs"])]
    for k in range(1, len(order) + 1):
        sub = {L["id"] for L in order[:k]}
        w = {i: (1.0 if i in sub else 0.0) for i in ids}
        d, f = series(legs, w, dates, at)
        s = score(dates, d, f)
        r, e = diversification(legs, sub, w, dates, at)
        names = "+".join(L["tenor"] for L in order[:k])
        print(line(f"상위 {k}", s, r, e, extra=names if k <= 5 else ""))

    # ── 표본밖 — 앞절반에서 고르고 뒤절반에서 채점 ─────────────────────────
    print(f"\n④ 표본밖 — 앞절반({dates[0]}~{dates[half-1]})에서 고르고 "
          f"뒤절반에서 채점")
    print("  「대차대조표당이 낮은 다리를 뺀다」도 표본을 보고 고르는 일이다.")
    print(HEAD)
    ins = []
    for L in legs:
        w = {L["id"]: 1.0}
        d, f = series(legs, w, dates, at)
        pts = [{"dailyPnl": x, "barCost": 0.0} for x in d[:half]]
        m = mrm.score(dates[:half], pts, [], 0, 0.0)
        cap = st.fmean(f[:half])
        bs = m["totalPnl"] / (half / BARS) / cap * 100 if cap else 0.0
        ins.append((L, bs))
    order_in = [L for L, _b in sorted(ins, key=lambda x: -x[1])]
    print("  앞절반 대차대조표당 순위: " + " > ".join(L["tenor"] for L in order_in))
    for k in (len(order_in), 7, 5, 3):
        if k > len(order_in):
            continue
        sub = {L["id"] for L in order_in[:k]}
        w = {i: (1.0 if i in sub else 0.0) for i in ids}
        d, f = series(legs, w, dates, at)
        s = score(dates, d, f, start=half)
        r, e = diversification(legs, sub, w, dates, at, start=half)
        print(line(f"뒤절반 · 상위 {k}", s, r, e))
    # 동일 액면도 표본밖에서
    dB2, fB2 = series(legs, wB, dates, at)
    sB2 = score(dates, dB2, fB2, start=half)
    rB2, eB2 = diversification(legs, set(ids), wB, dates, at, start=half)
    print(line("뒤절반 · B 동일액면", sB2, rB2, eB2))

    print("\n※ 손익은 명목에 선형이라 크기를 곱셈으로 만들었다(거래 목록은 z 에만")
    print("  달려 있다 — 엔진을 다시 안 돌린다). 레포 헤어컷·증거금은 안 셌으므로")
    print("  「묶인 액면」은 대차대조표 쪽 구속이고, 현금 구속은 이것보다 훨씬 작다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
