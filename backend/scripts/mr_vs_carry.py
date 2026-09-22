# -*- coding: utf-8 -*-
"""**그냥 3년 국고채 캐리로 가져가는 것보다 나은가** [OWNER 2026-09-07].

## 왜 이걸 재나

2026-09-07 까지 이 레인이 잰 것은 전부 **전략 내부** 비교였다 — Calmar 몇,
격자에서 몇 등, 묶으면 순위가 읽히나. 그런데 데스크가 실제로 물어야 하는 것은
**「이 짓을 안 하고 그냥 국고 3년을 들고 있었으면 어땠나」**이고, 그건 한 번도
안 쟀다. 안 재면 「Calmar 1.76」이 좋은 수인지 나쁜 수인지 말할 근거가 없다.

## 벤치마크의 정의 — 엔진으로 값매긴다

`cashbond` 의 **같은 기계**로 국고 3년 아웃라이트(`KIND_CASH`)를 값매긴다.
두 번째 정의를 만들면 비교 자체가 무의미해진다 — 전략 쪽 손익은 엔진이 내는데
벤치마크만 손으로 계산하면 차이가 «전략의 값어치» 인지 «두 산술의 차» 인지
가릴 수 없다. 네 성분(평가·캐리·롤다운·조달)이 그대로 나온다.

**롤한다.** 3년 채권을 6년 반 들고 있으면 3년째에 만기가 온다. 데스크가 말하는
「3년 국고채를 캐리로 가져간다」는 상시 3년을 유지한다는 뜻이므로, 분기마다
새 3년으로 갈아탄다(`ROLL_MONTHS`).

## 크기를 어떻게 맞추나 — **이게 이 시험의 핵심 결정이다**

MR 장부는 만기 아홉에 각각 Delta 100만원/bp 를 걸지만 **51%의 날은 포지션이
하나도 없고** 평균 동시 다리가 1.15 다. 그래서 「같은 크기」가 한 가지가 아니다:

  (가) **한 다리 상당 · 상시**   국고 3년 DV01 100만원/bp 를 늘 들고 있는다.
  (나) **평균 위험 맞춤**        장부의 평균 DV01(= 1.15 × 100만원/bp)에 맞춘다.
  (다) **크기와 무관한 비율**    Calmar·Sortino 는 크기에 불변이라 그대로 비교된다.

셋을 다 낸다. (다)가 판정이고 (가)·(나)는 그 판정이 얼마짜리인지를 말한다.

## 이 시험이 답하지 않는 것

거래비용·실행가능성은 각자의 가정을 그대로 쓴다(전략은 편도 0.5bp, 벤치마크는
분기 롤의 편도 비용). 국고 다리는 양쪽 다 민평이다. 세금·레포 마진은 없다.

돌리기:  python -m scripts.mr_vs_carry
"""

from __future__ import annotations

import datetime as dt
import statistics as st

from app import cashbond, creditmatrix, funding, mrbook, mrmetrics as mrm
from app.main import _dataset, _mr_leg


KN = dict(lookback=60, entryZ=2.0, exitZ=0.5, stopZ=3.5, costBp=0.5,
          notional=1_000_000.0, carry=True, entryMode="level", timeStop=0,
          costModel="flat", regime="none", countOpen=False)

TENOR = "3Y"
ROLL_MONTHS = 3

#: 신용 사다리 [OWNER 2026-09-07 — "캐피탈 AA 캐리면?"].
#:
#: 국고 3년 캐리가 진 이유는 **캐리가 조달을 못 덮어서**였다(캐리 +5.87억 대
#: 조달 −5.29억, 순 +5,789만). 그러면 자연히 「더 높은 캐리를 받으면?」이 다음
#: 질문이고, 이 데스크의 민평 매트릭스에 사다리가 통째로 있다.
#:
#: ⚠ **부도를 안 센다.** 여기 손익은 민평 평가손익이라 스프레드 확대는 들어가고
#: **부도 손실은 안 들어간다.** AA− 캐피탈채를 6년 반 굴리면서 한 건도 안 터진다는
#: 가정이고, 그 가정이 이 표에서 가장 큰 미측정 항이다 — 표가 그 사실을 적는다.
LADDER = [
    ("KTB", "국고채"),
    ("BD", "은행채 AAA"),
    ("CB1", "회사채 AAA"),
    ("CARD", "카드채 AA+"),
    ("OFB", "캐피탈채 AA-"),
]
#: 롤 한 번의 편도 비용(bp). 전략의 편도 0.5bp 와 같은 자를 쓴다 — 벤치마크에만
#: 비용을 안 물리면 그 비교는 벤치마크 쪽으로 기운다.
ROLL_COST_BP = 0.5

#: MMF 대용치 [OWNER 2026-09-07 — "벤치마크를 mmf라고 가정하고"].
#:
#: 한국 MMF 는 CP·CD·단기채를 담으므로 수익률이 **콜금리 위, CD 91일 근처**다.
#: 하나를 고르지 않고 **둘을 범위로** 낸다 — 대용치를 하나로 못 박으면 그 선택이
#: 결론을 만드는데, 다행히 이 표본에서는 둘 다 같은 결론을 준다.
MMF_PROXIES = [("콜금리", "bigfoot_call_d.csv", 0.0),
               ("CD 91일", "bigfoot_cd91_d.csv", 0.0)]


def _add_months(d: dt.date, n: int) -> dt.date:
    y, m = d.year, d.month + n
    while m > 12:
        m -= 12
        y += 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return dt.date(y, m, day)


def _bench(m, spec, dv01_krw: float, first: dt.date, last: dt.date,
           bond_type: str = "KTB") -> dict:
    """국고 3년을 분기마다 갈아타며 상시 보유 — 일별 손익 계열.

    액면은 **롤마다 다시 잡는다**. DV01 을 고정하는 것이 목적이므로(전략과 같은
    크기), 금리가 움직이면 같은 DV01 을 내는 액면이 달라진다. 근사는 데스크의
    그것과 같다: DV01 ≈ 액면 × 듀레이션 × 1e-4, 듀레이션 ≈ 만기(3년) 근처.
    """
    daily: dict[str, float] = {}
    #: 조달을 뺀 판 — **결론이 이 가정 하나에 걸려 있어서** 같이 낸다. 이 표본에서
    #: 조달이 최대 항이다. 자기자금으로 들고 있는 북이면 그 항이 없고 답이 뒤집힌다.
    #: 어느 쪽이 맞는지는 이 스크립트가 아니라 **그 북이 어떻게 자금을 대는가**가 정한다.
    daily_nf: dict[str, float] = {}
    comp = {"valuation": 0.0, "carry": 0.0, "rolldown": 0.0, "funding": 0.0}
    cost_total = 0.0
    rolls = 0
    start = first
    while start < last:
        end = min(_add_months(start, ROLL_MONTHS), last)
        # 같은 DV01 을 내는 액면. 3년 국고의 수정듀레이션은 표본 안에서 2.8~2.9 라
        # 2.85 로 고정한다 — 액면을 매일 다시 잡으면 롤 비용이 없는 재조정이 되어
        # 벤치마크가 부당하게 좋아진다.
        notional = dv01_krw / (2.85 * 1e-4)
        pos = cashbond.BondPosition(kind=cashbond.KIND_CASH, bond_type=bond_type,
                                    tenor=TENOR, direction=1, notional=notional,
                                    entry=start, exit=end)
        try:
            rec = cashbond.book_recon(m, _dataset, [pos], spec)
        except Exception:                                      # noqa: BLE001
            start = end
            continue
        for r in rec["rows"]:
            if r.get("actual") is None:
                continue                                       # 이월 앵커
            daily[r["t"]] = daily.get(r["t"], 0.0) + r["actual"]
            daily_nf[r["t"]] = daily_nf.get(r["t"], 0.0) + r["actual"] - (r.get("funding") or 0.0)
            for k in comp:
                v = r.get(k)
                if v:
                    comp[k] += v
        # 갈아타기 비용 — 편도 두 번(판다/산다)이 아니라 왕복 한 번으로 센다
        # (전략의 진입·청산이 각각 편도인 것과 같은 규약).
        cost_total -= dv01_krw * ROLL_COST_BP
        rolls += 1
        start = end
    return {"daily": daily, "dailyNoFunding": daily_nf, "comp": comp,
            "cost": cost_total, "rolls": rolls}


def _mmf(fname: str, add: float, capital: float, lo: str, hi: str) -> float:
    """그 자본을 MMF 에 넣어 뒀을 때의 누적 수익(원). 일할 계산(act/365).

    **이게 «아무것도 안 하기» 의 값이다.** 벤치마크가 MMF 라는 것은 「이 짓을
    안 하고 돈을 그냥 굴렸으면」과 견준다는 뜻이고, 그러면 채권 캐리가 버는
    캐리에서 이 수를 빼야 한다 — 그 자본이 묶여 있었기 때문이다.
    """
    import csv as _csv
    from pathlib import Path as _P
    src = _P(__file__).resolve().parents[1] / "data" / "raw" / fname
    ser = {}
    for r in _csv.DictReader(src.open(encoding="utf-8-sig")):
        t, v = r["TIME"], r["DATA_VALUE"]
        if len(t) == 8 and v:
            ser[f"{t[:4]}-{t[4:6]}-{t[6:]}"] = float(v)
    ks = sorted(k for k in ser if lo <= k <= hi)
    tot, prev = 0.0, None
    for k in ks:
        d = dt.date.fromisoformat(k)
        n = 1 if prev is None else (d - prev).days
        tot += (ser[k] + add) / 100.0 * n / 365.0
        prev = d
    return capital * tot


def _score(dates: list[str], daily: list[float], label: str) -> dict:
    pts = [{"dailyPnl": x, "barCost": 0.0} for x in daily]
    s = mrm.score(dates, pts, [], 0, 0.0)
    return {"label": label, **s}


def _line(s: dict, extra: str = "") -> str:
    return (f"  {s['label']:<22} 총손익 {s['totalPnl']/1e4:>10,.0f}만원 · "
            f"낙폭 {-s['maxDrawdown']/1e4:>9,.0f}만원 · "
            f"Calmar {s['calmar'] if s['calmar'] is not None else float('nan'):>6.2f} · "
            f"Sortino {s['sortino'] if s['sortino'] is not None else float('nan'):>6.2f}"
            + (f" · {extra}" if extra else ""))


def main() -> int:
    spec = funding.FundingSpec().validated()
    m = creditmatrix.load()

    legs = []
    for sid, _l in mrbook.bss_series():
        try:
            legs.append(_mr_leg(sid, spec=spec, **KN))
        except Exception as exc:                               # noqa: BLE001
            print(f"  [빠짐] {sid}: {exc}")
    dates = sorted({t for leg in legs for t in leg["dates"]})
    at = {t: i for i, t in enumerate(dates)}

    # ── 전략(통합 장부) ───────────────────────────────────────────────────
    book = [0.0] * len(dates)
    live = [0] * len(dates)
    for leg in legs:
        for j, p in enumerate(leg["r"]["points"]):
            i = at[leg["dates"][j]]
            book[i] += p["dailyPnl"]
            if p["position"] != 0:
                live[i] += 1
    mean_legs = st.fmean(live)
    idle = sum(1 for x in live if x == 0) / len(live)

    d0, d1 = dt.date.fromisoformat(dates[0]), dt.date.fromisoformat(dates[-1])
    print(f"\n=== {dates[0]} ~ {dates[-1]} · {len(dates)}봉 · 만기 {len(legs)}개 ===")
    print(f"장부 평균 동시 다리 {mean_legs:.2f} · 무포지션 {idle*100:.0f}%\n")

    strat = _score(dates, book, "MR 통합(아홉)")

    # ── 신용 사다리 — 전부 같은 DV01(한 다리 상당·상시) ───────────────────
    out = [strat]
    for bt, name in LADDER:
        b = _bench(m, spec, KN["notional"], d0, d1, bond_type=bt)
        if not b["daily"]:
            print(f"  [빠짐] {name}: 그 표본에 민평이 없어요")
            continue
        # 롤 비용을 마지막 봉에 몰지 않고 롤 수로 나눠 고르게 얹으면 낙폭이
        # 과소평가된다 — 그냥 총손익에서만 뺀다(낙폭은 비용 전 값이라 명시한다).
        s = _score(dates, [b["daily"].get(t, 0.0) for t in dates], f"{name} 캐리")
        s["_cost"] = b["cost"]
        s["_rolls"] = b["rolls"]
        s["_comp"] = b["comp"]
        out.append(s)
        nf = _score(dates, [b["dailyNoFunding"].get(t, 0.0) for t in dates],
                    f"{name} 자기자금")
        nf["_cost"] = b["cost"]
        nf["_rolls"] = b["rolls"]
        out.append(nf)

    print("(다) 크기와 무관한 비율 — 이게 판정이다")
    for s in out:
        extra = ""
        if "_rolls" in s:
            extra = f"롤 {s['_rolls']}회 · 비용 {s['_cost']/1e4:,.0f}만원(총손익에 미포함)"
        print(_line(s, extra))

    print("\n성분(벤치마크) — 캐리가 얼마나 나르나")
    for s in [x for x in out if "_comp" in x]:
        c = s["_comp"]
        tot = sum(c.values())
        print(f"  {s['label']:<22} " + " · ".join(
            f"{k} {v/1e4:>+8,.0f}만원" for k, v in c.items()) + f"  (합 {tot/1e4:+,.0f}만원)")

    # ── MMF — 「아무것도 안 하기」의 값 ───────────────────────────────────
    cap = KN["notional"] / (2.85 * 1e-4)
    print(f"\nMMF 대용치 — 자본 {cap/1e8:.1f}억(= DV01 100만원/bp 를 내는 액면)을 그냥 굴렸으면")
    mm = {}
    for name, fname, add in MMF_PROXIES:
        mm[name] = _mmf(fname, add, cap, dates[0], dates[-1])
        print(f"  {name:<10} {mm[name]/1e4:>10,.0f}만원")
    fund = next((s["_comp"]["funding"] for s in out if "_comp" in s), 0.0)
    print(f"  (엔진이 문 조달  {fund/1e4:>10,.0f}만원 — 조달선이 MMF 범위 안이면")
    print("   「캐리(조달)」 열이 이미 MMF 초과수익이라 따로 뺄 것이 없다)")

    print(f"\n★ MMF 대비 초과수익 — 낙폭 1원당 얼마를 받았나")
    lo_p, hi_p = min(mm.values()), max(mm.values())
    for s in out:
        if "자기자금" in s["label"]:
            continue                    # MMF 기회비용을 무시한 판이라 여기 안 세운다
        dd = s["maxDrawdown"]
        per = "—" if dd <= 0 else f"{s['totalPnl']/dd:>6.2f}배"
        print(f"  {s['label']:<22} 초과 {s['totalPnl']/1e4:>10,.0f}만원 · "
              f"낙폭 {-dd/1e4:>9,.0f}만원 · 낙폭당 {per}")
    print(f"  {'MMF(기준)':<22} 초과 {0:>10,.0f}만원 · 낙폭 {0:>9,.0f}만원 · 낙폭당      —")
    print(f"  ※ MMF 대용치 범위 {lo_p/1e4:,.0f}~{hi_p/1e4:,.0f}만원, 조달 {-fund/1e4:,.0f}만원")

    print("\n회복·물속")
    for s in out:
        rec = "회복 못 함" if not s["recovered"] else f"{s['recoveryDays']}일"
        print(f"  {s['label']:<22} 최대낙폭 회복 {rec} · 승률 "
              f"{'—' if s['winRate'] is None else f'{s['winRate']*100:.0f}%'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
