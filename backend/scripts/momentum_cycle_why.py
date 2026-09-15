# -*- coding: utf-8 -*-
r"""한은 전망치 판이 왜 나쁜가 — 신호와 손익을 갈라 본다 [2026-09-15].

    python -m scripts.momentum_cycle_why

답은 「같은 손익에 위험 17% 증가 · 추세와 상관 0.396→0.445 · 손익분기 상관 교차」다.
정본은 `docs/RESULT_cycle_bok_2026-09-14.md` §7. 여기서 내는 것:

  1. 전망치 원자료(READINGS) 꼬리
  2. 경기순환 테마 부호 둘 — 일치율 · 전환 수 · 롱 비중 · 전환일 · 변화량 분포
  3. macro_sign 이 갈리는 날의 거시 다리 손익 · 50/50 SR 의 산술 분해 · 선후 검사
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = str(Path(__file__).resolve().parents[1])
VINT = str(Path(BACKEND).parents[2] / "data" / "krw-macro-vintage")
os.chdir(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, str(Path(VINT) / "src"))
from scripts import momentum_evaluate as me          # noqa: E402
from scripts import momentum_irs_evaluate as mie     # noqa: E402
from scripts import momentum_irs_legs as ml          # noqa: E402
from scripts import macro_paper_fix as mp            # noqa: E402
import pull_bok_outlook as pbo                        # noqa: E402

ANN = 252
pd.set_option("display.width", 200)


def sr(x: pd.Series) -> float:
    return float(x.mean() / x.std(ddof=1) * math.sqrt(ANN)) if x.std(ddof=1) > 0 else float("nan")


def main() -> int:
    # ── 1. 전망치 원자료 ────────────────────────────────────────────────
    R = pbo.READINGS
    df = pd.DataFrame([{"ym": k, **R[k]} for k in sorted(R)]).set_index("ym")
    print("READINGS 열:", list(df.columns))
    print(df.tail(12).to_string())

    # ── 2. 일별 경기순환 계열 둘 ───────────────────────────────────────
    d = mp._load()
    th_o = mp.themes(d, paper=True, cycle="oecd")
    th_b = mp.themes(d, paper=True, cycle="bok")
    cyc_o = np.sign(th_o["cycle_raw"]).dropna()
    cyc_b = np.sign(th_b["cycle_raw"]).dropna()
    ix = cyc_o.index.intersection(cyc_b.index)
    ix = ix[(ix >= "2017-01-06") & (ix <= "2026-09-08")]
    co, cb = cyc_o.loc[ix], cyc_b.loc[ix]
    print(f"\n경기순환 테마 부호 (2017-01-06~2026-09-08, {len(ix):,}일)")
    print(f"  일치 {float((co == cb).mean()):.3f} · 전환 oecd {int((co.diff() != 0).sum())} bok {int((cb.diff() != 0).sum())}"
          f" · 롱(+) 비중 oecd {float((co > 0).mean()):.3f} bok {float((cb > 0).mean()):.3f}"
          f" · 0 비중 oecd {float((co == 0).mean()):.3f} bok {float((cb == 0).mean()):.3f}")
    yr = pd.DataFrame({"일치": (co == cb).astype(float), "oecd롱": (co > 0).astype(float), "bok롱": (cb > 0).astype(float)})
    print(yr.groupby(yr.index.year).mean().round(2).to_string())
    tr = cb[cb.diff() != 0]
    print("\nbok 경기순환 부호 전환일:", [f"{t:%Y-%m-%d}:{int(v):+d}" for t, v in tr.items()])
    tro = co[co.diff() != 0]
    print("oecd 전환 수", len(tro), "· 월별 전환 분포:", tro.groupby(tro.index.month).size().to_dict())
    raw_b = th_b["cycle_raw"].dropna()
    raw_b = raw_b[(raw_b.index >= "2017-01-06") & (raw_b.index <= "2026-09-08")]
    print("\nbok cycle_raw 분포(일별): |x|<0.25 비중 %.3f · 중앙 |x| %.2f · 값 종류 %d"
          % (float((raw_b.abs() < 0.25).mean()), float(raw_b.abs().median()), raw_b.nunique()))

    # ── 3. macro_sign 과 다리 손익 ──────────────────────────────────────
    series = mie.load_irs_series()
    _s, _r, macro = me._inputs()
    out = {}
    for cyc in ("oecd", "bok"):
        m = dict(macro)
        m["macro_sign"] = mp.as_signal(mp.themes(d, paper=True, cycle=cyc))
        for k in [k for k in ml._RUNS if k[2]]:
            del ml._RUNS[k]
        L = ml.legs(series, m)
        out[cyc] = {leg: pd.Series(L[leg]["rets"].values,
                                   index=pd.to_datetime([str(t)[:10] for t in L[leg]["rets"].index]))
                    for leg in ("trend", "macro", "blend")}
        sg = pd.Series(m["macro_sign"])
        sg.index = pd.to_datetime([str(t)[:10] for t in sg.index])
        out[cyc]["sign"] = sg

    P = pd.DataFrame({"trend": out["oecd"]["trend"], "mo": out["oecd"]["macro"], "mb": out["bok"]["macro"],
                      "bo": out["oecd"]["blend"], "bb": out["bok"]["blend"]}).dropna()
    S = pd.DataFrame({"so": out["oecd"]["sign"], "sb": out["bok"]["sign"]}).reindex(P.index).ffill()
    same = np.sign(S["so"]) == np.sign(S["sb"])
    print(f"\nmacro_sign 부호 일치일 {int(same.sum()):,} · 불일치일 {int((~same).sum()):,}")
    print(f"  일치일   거시 oecd 누적 {P.loc[same,'mo'].sum()/1e4:8,.0f}만  bok {P.loc[same,'mb'].sum()/1e4:8,.0f}만")
    print(f"  불일치일 거시 oecd 누적 {P.loc[~same,'mo'].sum()/1e4:8,.0f}만  bok {P.loc[~same,'mb'].sum()/1e4:8,.0f}만")
    diff = P["mb"] - P["mo"]
    print("  거시 bok−oecd 연도별(원 계열, 만원):", (diff.groupby(diff.index.year).sum() / 1e4).round(0).to_dict())
    dd = diff[~same]
    print("  그중 불일치일 기여:", (dd.groupby(dd.index.year).sum() / 1e4).round(0).to_dict())

    print(f"\n추세-거시 상관 oecd {P['trend'].corr(P['mo']):+.3f} · bok {P['trend'].corr(P['mb']):+.3f}")
    print(f"거시 SR oecd {sr(P['mo']):.3f} · bok {sr(P['mb']):.3f} · 추세 {sr(P['trend']):.3f}")
    for tag, mcol, bcol in (("oecd", "mo", "bo"), ("bok", "mb", "bb")):
        t, mm = P["trend"], P[mcol]
        rho = t.corr(mm)
        st, sm = t.std(ddof=1), mm.std(ddof=1)
        mu = 0.5 * (t.mean() + mm.mean())
        sd = 0.5 * math.sqrt(st**2 + sm**2 + 2 * rho * st * sm)
        # 손익분기 상관 — 이 아래여야 50/50 SR 이 추세 SR 을 넘는다
        srt, srm = sr(t), sr(mm)
        need = (srt * st + srm * sm) / srt
        rho_be = (need**2 - st**2 - sm**2) / (2 * st * sm)
        print(f"  50/50 {tag}: 실측 SR {sr(P[bcol]):.3f} · 산술 {mu/sd*math.sqrt(ANN):.3f}  "
              f"(σ추세 {st/1e4:,.0f}만 σ거시 {sm/1e4:,.0f}만 ρ {rho:+.3f} · 손익분기 ρ {rho_be:.3f})")
    for tag, col in (("oecd", "so"), ("bok", "sb")):
        s = S[col]
        print(f"  macro_sign {tag}: 0 비중 {float((s == 0).mean()):.3f} · |sign| 평균 {float(s.abs().mean()):.3f} · 부호 전환 {int((np.sign(s).diff() != 0).sum())}")

    mb_sign = np.sign(S["sb"]); mo_sign = np.sign(S["so"])
    lead = {}
    for k in (-60, -20, 0, 20, 60):
        a = mo_sign.shift(k)
        m_ = a.notna() & mb_sign.notna()
        lead[k] = float((a[m_] == mb_sign[m_]).mean())
    print("\nbok 부호 대 oecd 부호를 k일 민 것의 일치율(양수 k = oecd 가 앞선다):", {k: round(v, 3) for k, v in lead.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
