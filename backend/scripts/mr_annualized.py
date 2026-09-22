# -*- coding: utf-8 -*-
"""MR 통합을 **연환산**하고, 그 분모를 실제로 재 본다 [OWNER 2026-09-07].

## 분모가 문제다 — 이 데스크에는 AUM 이 없다

MR 의 노브는 Delta(₩/bp)이지 자본이 아니다. 그래서 「연 몇 %」를 말하려면 자본을
정해야 하는데, 이 창의 지표(Calmar·Sortino)는 그 질문을 **피해 간다** — 분자도
분모도 원이라 자본이 약분된다. 그게 그 지표들의 장점이자 **함정**이다:

    DV01 을 맞추면 **짧은 만기가 훨씬 큰 액면을 문다.**
    6M 다리가 DV01 100만원/bp 를 내려면 액면이 200억이고,
    10Y 다리는 같은 DV01 에 12억이면 된다.

MMF 와 견주는 순간 그 사실이 되살아난다. MMF 수익은 **자본에 붙지 DV01 에 안
붙기** 때문이다. 그래서 여기서는 **날마다 실제로 묶인 액면**을 세고, 그 위에서
연환산한다.

## 두 가지 연환산을 낸다 — 둘이 다른 질문이다

    (가) 원 단위      연환산 손익 = 총손익 / 연수.   Calmar 의 분자와 같은 수.
    (나) 자본 대비    연환산 손익 / 평균 묶인 액면.  MMF 수익률과 같은 자.

(가)는 「이 크기로 굴리면 한 해 얼마」이고, (나)는 「그 돈을 MMF 에 뒀을 때와
견주면 몇 %p」다. **데스크가 답해야 하는 것은 (나)** 이고, 이 스크립트를 쓴 이유가
그것이다.

## 이 시험이 답하지 않는 것

레포 헤어컷·증거금을 안 센다. 실제로 묶이는 현금은 액면 전체가 아니라 헤어컷
(국고 2~5%)과 증거금이므로, **(나)는 자본 효율을 보수적으로 잡은 하한**이다.
반대로 대차대조표는 액면 전부를 쓴다 — 어느 쪽이 구속인지는 그 데스크가 안다.

돌리기:  python -m scripts.mr_annualized
"""

from __future__ import annotations

import datetime as dt
import statistics as st

from app import funding, mrbook, mrmetrics as mrm
from app.main import _mr_leg, _mr_principal_at
from app import mrcarry as mrc


KN = dict(lookback=60, entryZ=2.0, exitZ=0.5, stopZ=3.5, costBp=0.5,
          notional=1_000_000.0, carry=True, entryMode="level", timeStop=0,
          costModel="flat", regime="none", countOpen=False)

BARS_PER_YEAR = 252


def main() -> int:
    spec = funding.FundingSpec().validated()
    legs = []
    for sid, _l in mrbook.bss_series():
        try:
            legs.append(_mr_leg(sid, spec=spec, **KN))
        except Exception as exc:                               # noqa: BLE001
            print(f"  [빠짐] {sid}: {exc}")

    dates = sorted({t for leg in legs for t in leg["dates"]})
    at = {t: i for i, t in enumerate(dates)}
    n = len(dates)
    years = n / BARS_PER_YEAR

    daily = [0.0] * n
    live = [0] * n
    #: 그날 묶인 **액면**. 다리마다 그 거래의 진입일 커브로 환산한다
    #: (`_mr_principal_at` — 화면이 카드에 적는 「액면 약 35.4억」과 같은 자).
    face = [0.0] * n
    per_leg_face: dict[str, list[float]] = {}

    for leg in legs:
        tenor = mrc._tenor_of(leg["id"])                        # noqa: SLF001
        faces = []
        for t in leg["r"]["trades"]:
            p = _mr_principal_at(dt.date.fromisoformat(t["entryDate"]), tenor,
                                 KN["notional"])
            if p:
                faces.append(p)
        per_leg_face[leg["id"]] = faces
        med = st.median(faces) if faces else 0.0
        for j, pt in enumerate(leg["r"]["points"]):
            i = at[leg["dates"][j]]
            daily[i] += pt["dailyPnl"]
            if pt["position"] != 0:
                live[i] += 1
                face[i] += med          # 그 다리가 선 날의 액면(중앙값으로 근사)

    pts = [{"dailyPnl": x, "barCost": 0.0} for x in daily]
    s = mrm.score(dates, pts, [], 0, 0.0)
    total = s["totalPnl"]
    mdd = s["maxDrawdown"]

    print(f"\n=== MR 통합 · {dates[0]} ~ {dates[-1]} · {n}봉 = {years:.2f}년 ===\n")

    print("다리별 액면 — DV01 100만원/bp 를 내려면 얼마를 사야 하나")
    for leg in legs:
        f = per_leg_face[leg["id"]]
        if not f:
            continue
        print(f"  {leg['label']:<10} 중앙 {st.median(f)/1e8:>7.1f}억  "
              f"(거래 {len(f)}건 · {min(f)/1e8:.1f}~{max(f)/1e8:.1f}억)")

    live_face = [f for f in face if f > 0]
    print(f"\n묶인 액면 — 평균 {st.fmean(face)/1e8:,.1f}억 (선 날만 보면 "
          f"{st.fmean(live_face)/1e8:,.1f}억) · 최대 {max(face)/1e8:,.1f}억")
    print(f"  무포지션 {sum(1 for x in live if x == 0)/n*100:.0f}% · "
          f"평균 동시 다리 {st.fmean(live):.2f}")

    print("\n(가) 원 단위 연환산")
    print(f"  총손익        {total/1e4:>12,.0f}만원  ({years:.2f}년)")
    print(f"  연환산 손익    {total/years/1e4:>12,.0f}만원/년")
    print(f"  최대낙폭      {-mdd/1e4:>12,.0f}만원   → Calmar {total/years/mdd:.2f}")

    cap = st.fmean(face)
    print("\n(나) 자본 대비 연환산 — MMF 와 같은 자")
    print(f"  분모 = 평균 묶인 액면 {cap/1e8:,.1f}억")
    print(f"  연환산 수익률  {total/years/cap*100:>12.2f}%/년")
    print(f"  (선 날만 굴린다고 보면 {total/years/st.fmean(live_face)*100:.2f}%/년)")

    # MMF 대용치 — 같은 창, 같은 자.
    import csv
    from pathlib import Path
    for name, fname in (("콜금리", "bigfoot_call_d.csv"), ("CD 91일", "bigfoot_cd91_d.csv")):
        src = Path(__file__).resolve().parents[1] / "data" / "raw" / fname
        ser = {}
        for r in csv.DictReader(src.open(encoding="utf-8-sig")):
            t, v = r["TIME"], r["DATA_VALUE"]
            if len(t) == 8 and v:
                ser[f"{t[:4]}-{t[4:6]}-{t[6:]}"] = float(v)
        ks = sorted(k for k in ser if dates[0] <= k <= dates[-1])
        tot, prev = 0.0, None
        for k in ks:
            d = dt.date.fromisoformat(k)
            days = 1 if prev is None else (d - prev).days
            tot += ser[k] / 100.0 * days / 365.0
            prev = d
        print(f"  MMF({name})   {tot/years*100:>12.2f}%/년"
              f"   (조달선과 견줄 값 — 아래 ★)")

    print(f"\n★ MR 의 초과수익은 {total/years/cap*100:+.2f}%p/년 이다 — 빼지 않는다.")
    print("  MR 손익은 이미 조달을 물고 나온 수다: `main._mr_leg` 이 캐리를")
    print("  `carry_krw(..., notional_per_bp, pv01)` 로 액면 전체에 환산하고,")
    print("  그 캐리 안에 (국고 − 조달)의 조달이 이미 빠져 있다. 조달선이 MMF")
    print("  범위 안이므로 위 수 자체가 MMF 초과분이다 — 또 빼면 이중 계상이다.")

    print("\n※ 레포 헤어컷·증거금을 안 셌다. 실제로 묶이는 현금은 액면 전부가")
    print("  아니라 헤어컷(국고 2~5%)과 증거금이라, (나)는 자본 효율의 **하한**이다.")
    print("  대차대조표를 쓰는 쪽으로 보면 액면 전부가 맞다 — 어느 쪽이 구속인지는")
    print("  그 데스크가 안다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
