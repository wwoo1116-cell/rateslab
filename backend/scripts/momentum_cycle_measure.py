# -*- coding: utf-8 -*-
r"""한은 전망치 판 50/50 의 안 잰 둘 — 위험 맞춤 후 손익·낙폭, MR 결합 구간 [2026-09-15].

    python -m scripts.momentum_cycle_measure

수는 여기서 만들지 않는다. `momentum_irs_legs.legs()` · `make_charts.frames()` 의 셈 ·
`hedge_test.mix()` 의 셈을 그대로 부른다. OECD 판을 같이 재서 09-14 보고의 수와
맞는지(15,482 / −2,078 / 0.79 · ΔCalmar +0.234 P 0.077)를 먼저 확인한다.

⚠ `momentum_irs_legs._RUNS` 의 키는 (signal, vol_window, external is not None) 이라
신호 **내용**을 안 본다. 원천을 바꿔 다시 부를 때 거시 북 캐시를 비워야 한다.

창은 `legs()` 의 IRS 달력(2,389봉) ∩ MR 장부 달력 = 1,646봉이다. 09-11 초안의
1,640 은 선물 거래일과 교집합한 `hedge_test.aligned()` 의 창이다(6봉 차이가
추세 결합 P 를 0.040 ↔ 0.048 로 가른다). 정본 정의는 `sleeve_prereg_5050.py` 머리.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = str(Path(__file__).resolve().parents[1])
OUT = Path(BACKEND) / "output" / "momentum_cycle_measure.json"
os.chdir(BACKEND)
sys.path.insert(0, BACKEND)

from scripts import momentum_evaluate as me          # noqa: E402
from scripts import momentum_irs_evaluate as mie     # noqa: E402
from scripts import momentum_irs_legs as ml          # noqa: E402
from scripts import macro_paper_fix as mp            # noqa: E402
from scripts import hedge_test as ht                 # noqa: E402

ANN = 252


def iso(s: pd.Series) -> pd.Series:
    return pd.Series(s.values.astype(float), index=[str(t)[:10] for t in s.index])


def main() -> int:
    t0 = time.time()
    series = mie.load_irs_series()
    _s, _r, macro = me._inputs()
    if macro is None:
        raise SystemExit("매크로 신호가 없어서 거시·50/50 다리를 못 세워요")

    R: dict[str, dict[str, pd.Series]] = {}
    for cyc in ("oecd", "bok"):
        m = dict(macro)
        m["macro_sign"] = mp.as_signal(mp.themes(mp._load(), paper=True, cycle=cyc))
        for k in [k for k in ml._RUNS if k[2]]:
            del ml._RUNS[k]
        L = ml.legs(series, m)
        R[cyc] = {leg: iso(L[leg]["rets"]) for leg in ("trend", "macro", "blend")}
        R[cyc]["sign"] = pd.Series(m["macro_sign"])
        print(f"[{cyc}] legs done  {time.time() - t0:,.0f}s  {len(R[cyc]['blend']):,}봉 "
              f"{R[cyc]['blend'].index[0]}~{R[cyc]['blend'].index[-1]}", flush=True)

    # ── A. 위험 맞춤 후 (make_charts.frames 의 셈) ───────────────────────
    cols = {"trend": R["oecd"]["trend"],
            "macro_oecd": R["oecd"]["macro"], "blend_oecd": R["oecd"]["blend"],
            "macro_bok": R["bok"]["macro"], "blend_bok": R["bok"]["blend"]}
    df = pd.DataFrame(cols).dropna()
    df.index = pd.to_datetime(df.index)
    vol = {c: float(df[c].std(ddof=1)) * math.sqrt(ANN) for c in df}
    base = vol["trend"]
    A = {}
    for c in df:
        s = df[c]
        z = s * base / vol[c]
        cs, cz = s.cumsum(), z.cumsum()
        mdd = float((cs - cs.cummax()).min())
        mdz = float((cz - cz.cummax()).min())
        yrs = len(s) / ANN
        A[c] = {
            "sr": float(s.mean() / s.std(ddof=1) * math.sqrt(ANN)),
            "vol": vol[c], "cum": float(cs.iloc[-1]), "mdd": mdd,
            "cum_z": float(cz.iloc[-1]), "mdd_z": mdz,
            "calmar_z": float((cz.iloc[-1] / yrs) / abs(mdz)),
            "win": float((s > 0).mean()),
            "pos_years": int((z.groupby(z.index.year).sum() > 0).sum()),
            "yearly_z": {int(k): float(v) for k, v in z.groupby(z.index.year).sum().items()},
        }
    corr = df.corr().round(3).to_dict()
    print(f"\n창 {df.index[0]:%Y-%m-%d}~{df.index[-1]:%Y-%m-%d} {len(df):,}봉 · 기준 연변동성 {base/1e4:,.0f}만")
    print(f"{'계열':12s} {'SR':>6s} {'연변동':>7s} {'누적':>8s} {'MDD':>8s} {'맞춤누적':>8s} {'맞춤MDD':>8s} {'Calmar':>7s} {'승률':>6s} {'양+년':>4s}")
    for c, a in A.items():
        print(f"{c:12s} {a['sr']:6.3f} {a['vol']/1e4:7,.0f} {a['cum']/1e4:8,.0f} {a['mdd']/1e4:8,.0f} "
              f"{a['cum_z']/1e4:8,.0f} {a['mdd_z']/1e4:8,.0f} {a['calmar_z']:7.2f} {a['win']:6.3f} {a['pos_years']:4d}")
    print("\n상관: trend-macro_oecd %+.3f · trend-macro_bok %+.3f · blend_oecd-blend_bok %+.3f · macro_oecd-macro_bok %+.3f"
          % (corr["trend"]["macro_oecd"], corr["trend"]["macro_bok"],
             corr["blend_oecd"]["blend_bok"], corr["macro_oecd"]["macro_bok"]))
    print("\n연도별(위험 맞춤 후, 만원)")
    years = sorted(A["trend"]["yearly_z"])
    print("년   " + " ".join(f"{c:>11s}" for c in A))
    for y in years:
        print(f"{y} " + " ".join(f"{A[c]['yearly_z'][y]/1e4:11,.0f}" for c in A))

    so, sb = R["oecd"]["sign"], R["bok"]["sign"]
    ix = so.index.intersection(sb.index)
    agree = float((np.sign(so.loc[ix]) == np.sign(sb.loc[ix])).mean())
    print(f"\nmacro_sign 부호 일치 {agree:.3f} ({len(ix):,}일) · 롱비중 oecd {float((so.loc[ix]>0).mean()):.3f} bok {float((sb.loc[ix]>0).mean()):.3f}")

    # ── B. MR 결합 (hedge_test.mix 의 셈) ────────────────────────────────
    mr = ht.mr_returns()
    legs = {"추세": R["oecd"]["trend"], "50/50 OECD": R["oecd"]["blend"],
            "50/50 한은": R["bok"]["blend"], "거시 OECD": R["oecd"]["macro"],
            "거시 한은": R["bok"]["macro"]}
    idx = mr.index
    for s in legs.values():
        idx = idx.intersection(s.index)
    idx = sorted(idx)
    m = ht.unit_vol(mr.loc[idx]).to_numpy()
    base_cal, base_mdd = ht._card(m)
    print(f"\n── MR 결합 ({len(idx):,}봉 {idx[0]}~{idx[-1]}) · MR 단독 Calmar {base_cal:.3f} MDD {base_mdd:.3f} · w={ht.W_REGISTERED}")
    B = {"n": len(idx), "base_cal": base_cal, "base_mdd": base_mdd, "legs": {}}
    print(f"{'슬리브':12s} {'상관':>7s} {'Calmar':>7s} {'ΔCalmar':>8s} {'90%구간':>18s} {'P(Δ≤0)':>7s} {'MDD':>6s} {'ΔMDD':>7s} {'P(Δ≥0)':>7s}")
    for name, s in legs.items():
        t = ht.unit_vol(s.loc[idx]).to_numpy()
        rho = float(np.corrcoef(m, t)[0, 1])
        cal, md = ht._card((1 - ht.W_REGISTERED) * m + ht.W_REGISTERED * t)
        ci = ht._paired_ci(m, t, ht.W_REGISTERED)
        rows = {w: ht._card((1 - w) * m + w * t) for w in ht.WEIGHTS}
        B["legs"][name] = {"rho": rho, "cal": cal, "dcal": cal - base_cal, "mdd": md,
                           "dmdd": md - base_mdd, "ci": ci,
                           "rows": {str(w): list(v) for w, v in rows.items()}}
        print(f"{name:12s} {rho:+7.3f} {cal:7.3f} {cal-base_cal:+8.3f} "
              f"[{ci['cal'][0]:+.3f}, {ci['cal'][1]:+.3f}] {ci['p_cal']:7.3f} "
              f"{md:6.3f} {md-base_mdd:+7.3f} {ci['p_mdd']:7.3f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"A": A, "corr": corr, "B": B, "agree": agree,
                               "window": [str(df.index[0])[:10], str(df.index[-1])[:10], len(df)]},
                              ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(f"\nsaved {OUT}  {time.time() - t0:,.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
