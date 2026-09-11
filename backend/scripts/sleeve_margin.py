# -*- coding: utf-8 -*-
r"""슬리브를 얹으면 증거금이 감당되나 — 「총위험 고정」의 전제 [OWNER 2026-09-11].

    python -m scripts.sleeve_margin

## 무엇을 묻나

오너가 고른 결합은 **총위험 고정**이다. 위험기준 w 로 섞은 뒤 전체를 다시 키워
평균회귀 단독과 같은 연변동성으로 맞춘다. 그러면 이렇게 된다:

    결합 = (1−w)/σ_mix · MR/σ_M  +  w/σ_mix · T/σ_T          σ_mix = 혼합 변동성

    w=0.25 · σ_mix 0.783 →  MR 다리 **0.958배**(거의 그대로)
                            추세 다리 **0.319배**(= MR 변동성의 31.9%)

즉 「기존 장부를 4% 줄이고, MR 변동성의 32% 짜리 IRS 추세북을 새로 얹는다」이다.
증거금 물음은 그래서 **그 새 북이 얼마를 먹느냐** 하나로 좁혀진다.

## ⚠ 이 스크립트가 «가정하지 않는» 것

`margin_budget_book.MARGIN` 은 **BSS 스프레드 패키지**의 증거금률이다(≤2Y 5% ·
5Y+ 10%). 스프레드는 두 다리가 상쇄돼 아웃라이트보다 덜 먹으므로, 그 율을
IRS 아웃라이트에 그대로 쓰면 **소요를 과소평가한다.** 이 자리는 데스크의 실제
IRS 증거금 스케줄을 모르므로 **율을 인자로 받고 범위로 낸다.** 한 값을 골라
「된다/안 된다」를 말하지 않는다.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ctabacktest as cta                              # noqa: E402
from app import momentum as mo                                  # noqa: E402
from scripts import crs_evaluate as ce                          # noqa: E402
from scripts import hedge_test as ht                            # noqa: E402
from scripts import momentum_irs_evaluate as mie                # noqa: E402

ANN = 252

#: 재 볼 증거금률 — BSS 패키지 율을 바닥으로 두고 위로 훑는다.
#: 아웃라이트는 상쇄가 없어 이보다 높은 것이 정상이다.
RATES = (0.05, 0.10, 0.15, 0.20)

#: 슬리브 비중. 오너가 w 를 사전등록으로 미뤘으므로 후보를 같이 낸다.
WEIGHTS = (0.15, 0.25, 0.40, 0.60)


def sleeve_dv01() -> pd.DataFrame:
    """등록된 추세북의 만기별 DV01(₩/bp).

    엔진 회계가 `pos/100 × Δ(-bp)` 라 **pos/100 이 곧 ₩/bp** 다. 위약 배관이
    같은 등식 위에 서 있고 시험이 그것을 잰다.
    """
    series = mie.load_irs_series()
    book = cta.book_simulate(
        series, signal=mo.SIGNAL, lookbacks=mo.LOOKBACKS,
        vol_window=mo.VOL_WINDOW, target_book_vol_krw=mo.TARGET_VOL,
        book_vol_window=mo.BOOK_VOL_WINDOW, roll_days=set(),
        continuous=True, cost_ticks=mie.IRS_COST_BP / cta.TICK)
    return pd.DataFrame({k: np.asarray(v, dtype=float) / 100.0
                         for k, v in book["pos"].items()},
                        index=book["dates"])


def pv01_per_100m() -> dict[str, float]:
    """1억원 명목당 pv01(₩/bp) — 액면을 세우는 환산.

    근사식 `pv01 ≈ 명목 × 만기 × 1e-4` 를 쓴다. 커브가 평평하다고 보는 셈이라
    3Y 에서 2~3%, 10Y 에서 5~8% 어긋나는데, 이 자리가 묻는 것은 「상한에 닿나」의
    자릿수라 그 오차를 감당한다. 정확히 재려면 `app.dv01.pv01` 에 그날 커브를
    넣어야 하고 그건 진입일마다 다시 재는 일이다(그 레인의 그 규약).
    """
    return {"3Y": 1e8 * 3.0 * 1e-4, "10Y": 1e8 * 10.0 * 1e-4}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lot", type=int, default=ce.REGISTERED_LOT_UK)
    a = ap.parse_args()

    mb = ce._lane()
    net, facts = ce.net_returns(mb, a.lot, "bound")
    P, L, Z, meta = mb.load()
    _daily, used, _dv, _en, _bl = mb.simulate(P, L, Z, meta, a.lot)

    mr_vol_krw = float(net.std(ddof=1) * math.sqrt(ANN) * mb.CAP)
    print()
    print(f"── 평균회귀 상한판 (로트 {a.lot}억 · 자본비용 묶인것만) ──")
    print(f"  표본 {facts['start']} ~ {facts['end']} · {facts['bars']:,}봉")
    print(f"  연변동성            {mr_vol_krw / 1e8:8.3f}억원 "
          f"({net.std(ddof=1) * math.sqrt(ANN):.2%} of 자본)")
    print(f"  증거금 사용률       평균 {facts['use_mean']:.1%} · "
          f"최대 {facts['use_max']:.1%}")
    over = int((used > 0.999).sum())
    print(f"  상한(100억) 닿은 날  {over:,}일 / {len(used):,}일 "
          f"({over / len(used):.1%})")
    print(f"  남는 여력           평균 {(1 - facts['use_mean']) * mb.CAP / 1e8:.1f}억 · "
          f"최악 {(1 - facts['use_max']) * mb.CAP / 1e8:.1f}억")

    dv = sleeve_dv01()
    pv = pv01_per_100m()
    face = pd.DataFrame({k: dv[k].abs() / pv[k] * 1e8 for k in dv.columns})
    trend_vol = float(pd.Series(
        [p["dailyPnl"] for p in mie.irs_points()]).std(ddof=1) * math.sqrt(ANN))

    print()
    print("── 등록된 추세북(그대로) ──")
    print(f"  연변동성            {trend_vol / 1e8:8.3f}억원")
    for k in dv.columns:
        print(f"  {k:4s} DV01          평균 {dv[k].abs().mean():>10,.0f}₩/bp · "
              f"최대 {dv[k].abs().max():>11,.0f}₩/bp")
        print(f"  {k:4s} 액면          평균 {face[k].mean() / 1e8:>10,.1f}억 · "
              f"최대 {face[k].max() / 1e8:>11,.1f}억")

    print()
    print("── 총위험 고정에서 슬리브가 실제로 서는 크기 ──")
    print("  결합을 평균회귀 단독과 같은 연변동성으로 되돌린 판이다.")
    print(f"  {'w':>5s} {'σ_mix':>7s} {'MR 배수':>8s} {'추세 배수':>9s} "
          f"{'추세 연변동성':>13s} {'등록북 대비':>10s}")
    mr_u, legs = ht.aligned()
    m = mr_u.to_numpy()
    t = legs["IRS"].to_numpy()
    sized = {}
    for w in WEIGHTS:
        x = (1 - w) * m + w * t
        s_mix = float(x.std(ddof=1) * math.sqrt(ANN))
        k_mr, k_tr = (1 - w) / s_mix, w / s_mix
        vol_tr = k_tr * mr_vol_krw                    # MR 과 같은 단위로
        sized[w] = (k_tr, vol_tr)
        print(f"  {w:5.2f} {s_mix:7.3f} {k_mr:8.3f} {k_tr:9.3f} "
              f"{vol_tr / 1e8:11.3f}억 {vol_tr / trend_vol:9.2f}배")

    print()
    print("── 그 크기에서 슬리브가 먹는 증거금 ──")
    print("  ⚠ 아웃라이트 증거금률을 모른다. **범위로 낸다** — 한 값을 고르지 않는다.")
    print("  ⚠ 0.05/0.10 은 BSS **스프레드 패키지**의 율이라 아웃라이트에는 «바닥»이다.")
    base_face_max = float(sum(face[k].max() for k in face.columns))
    base_face_mean = float(sum(face[k].mean() for k in face.columns))
    print()
    print(f"  {'w':>5s} {'배수':>6s} " + " ".join(
        f"{'율 ' + f'{r:.0%}':>22s}" for r in RATES))
    for w in WEIGHTS:
        k_tr, vol_tr = sized[w]
        mult = vol_tr / trend_vol
        cells = []
        for r in RATES:
            need_max = base_face_max * mult * r
            need_mean = base_face_mean * mult * r
            cells.append(f"평 {need_mean / 1e8:5.1f} 최 {need_max / 1e8:6.1f}억")
        print(f"  {w:5.2f} {mult:6.2f} " + " ".join(f"{c:>22s}" for c in cells))

    print()
    print("── 합산이 상한(100억)에 닿나 — **일별로 겹쳐서** ──")
    print("  ⚠ 최댓값끼리 더하면 두 최악이 같은 날 온다고 가정하는 셈이다.")
    print("  같은 날짜 위에서 더해 **넘는 날이 며칠인가**를 센다.")
    print("  평균회귀 다리도 총위험 고정의 (1−w)/σ_mix 배로 줄여서 넣는다.")

    used_s = pd.Series(used.to_numpy(dtype=float),
                       index=[str(t)[:10] for t in used.index])
    face_s = pd.Series(
        sum(face[k] for k in face.columns).to_numpy(dtype=float),
        index=[str(t)[:10] for t in face.index])
    common = sorted(set(used_s.index) & set(face_s.index))
    if len(common) < 100:
        raise SystemExit(f"겹치는 날이 {len(common)}일뿐이라 못 재요")
    u = used_s.loc[common].to_numpy()
    f = face_s.loc[common].to_numpy()
    print(f"  공통 창 {common[0]} ~ {common[-1]} · {len(common):,}봉")

    print()
    print(f"  {'w':>5s} {'율':>5s} {'평균':>8s} {'95%':>8s} {'최대':>8s} "
          f"{'초과일':>8s} {'초과율':>7s}")
    for w in WEIGHTS:
        k_tr, vol_tr = sized[w]
        mult = vol_tr / trend_vol
        k_mr = (1 - w) / float(
            (((1 - w) * m + w * t).std(ddof=1)) * math.sqrt(ANN))
        for r in RATES:
            tot = u * mb.CAP * k_mr + f * mult * r
            over = int((tot > mb.CAP).sum())
            print(f"  {w:5.2f} {r:5.0%} {tot.mean() / 1e8:7.1f}억 "
                  f"{np.percentile(tot, 95) / 1e8:7.1f}억 "
                  f"{tot.max() / 1e8:7.1f}억 {over:7,}일 "
                  f"{over / len(tot):6.1%}")

    print()
    print("  ★기준선 — 평균회귀 단독. ⚠**같은 사건이 아니다.**")
    print("  단독의 «닿은 날» = 배분기가 상한에 막혀 다리를 더 못 넣은 날이다")
    print("  (엔진이 스스로 막으므로 넘지 않는다). 결합의 «초과일» = 상한을 넘어")
    print("  무언가를 줄여야 하는 날이다. 수를 나란히 놓되 같은 줄로 읽지 말 것.")
    base = u * mb.CAP
    print(f"  단독(닿은날)    {base.mean() / 1e8:7.1f}억 "
          f"{np.percentile(base, 95) / 1e8:7.1f}억 "
          f"{base.max() / 1e8:7.1f}억 "
          f"{int((base > mb.CAP * 0.999).sum()):7,}일 "
          f"{int((base > mb.CAP * 0.999).sum()) / len(base):6.1%}")
    print()
    print("  ⚠ 단독이 이미 상한에 붙어 있는 날이 있으면, 슬리브는 그 날 «못 들어간다».")
    print("  그때 선택은 둘이다 — 슬리브를 그날 건너뛰거나(추적오차), 평균회귀 쪽")
    print("  로트를 줄이거나(그 레인 사전등록 사안). 이 자리는 그 결정을 안 한다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
