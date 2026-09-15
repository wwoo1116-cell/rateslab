# -*- coding: utf-8 -*-
r"""거시 다리를 **논문 구조**로 세운 판정문 — 테마별 부호 북 넷 등가중 · 위험선호 확장 평균 [OWNER 2026-09-15].

    python -m scripts.momentum_irs_books

## 왜 이 자리가 필요한가

`momentum_irs_legs` 의 거시 다리는 네 부호의 평균을 북 하나에 넣는다. Brooks(2017) 부록 C 의
방향성 구성은 **테마마다 부호 롱/숏 북을 세워 같은 위험으로 맞춘 뒤 등가중**이고, 위험선호는
"since one-year equity returns are positive on average, I compare to an expanding mean" 이다
(`docs/BROOKS2017_appendix_BC.md`). 이 스크립트가 그 구조로 세 다리를 같은 관문에 태운다.

    추세       `momentum_irs_legs` 와 같다 (macross · 룩백 다섯 · 볼 윈도 60)
    거시       cycle · policy · trade · risk 네 북, 각 북 변동성 목표 100만원/일, 손익 등가중(1/4)
               cycle  = sign(OECD EX·CP 가속 평균)   — 09-08 등록 정의 그대로(성장 자리의 수출은 못 고침)
               policy = sign(통안 2Y 1년 변화의 −)   trade = sign(NEER 1년 로그변화)
               risk   = sign(−(주식 초과수익 1년 − 확장 평균))   확장 평균은 이 레인 KOSPI(2015~) 이력, 최소 250일
    50/50      두 다리의 일별 손익 0.5:0.5 (등록 규약)

판정문 id 는 `Momentum-{macro,blend}-IRS-books-paper` — `-legs-` 와 갈라 둔다(덮어쓰기 금지).
위약은 북 여럿을 **같은 k 로** 순환이동한다(`momentum_theme_books.placebo_multi`).

## 창

위험선호 확장 평균이 250일을 요구해 첫 날이 2017-01-09 다(등록 창 2017-01-06 보다 하루 뒤,
두 영업일). 표본내 탐색(`RESULT_bok_books`)에서 등록 북의 수가 이 창에서 그대로 재현됐다.
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
from evaluation import metrics as ev, randomization as rz, report  # noqa: E402
from scripts import macro_paper_fix as mp                       # noqa: E402
from scripts import momentum_evaluate as me                     # noqa: E402
from scripts import momentum_irs_evaluate as mie                # noqa: E402
from scripts import momentum_irs_legs as ml                     # noqa: E402
from scripts.momentum_theme_books import as_sig, placebo_multi, pnl_of  # noqa: E402

ANN = 252
THEMES = ("cycle", "policy", "trade", "risk")
MIN_MEAN = 250          # 확장 평균 최소 관측 [OWNER 09-15: 지금 이력(2015~)만]
TAG = "-books-paper"


def signals(th: pd.DataFrame) -> dict[str, pd.Series]:
    """네 테마의 일별 부호. 위험선호만 확장 평균 대비."""
    full = th[["cycle_raw", "policy_raw", "trade_raw", "risk_raw"]].notna().all(axis=1)
    eq_ex = -th["risk_raw"]
    risk_dm = -(eq_ex - eq_ex.expanding(min_periods=MIN_MEAN).mean())
    sig = {"cycle": np.sign(th["cycle_raw"]), "policy": np.sign(th["policy_raw"]),
           "trade": np.sign(th["trade_raw"]), "risk": np.sign(risk_dm)}
    return {k: v.where(full).dropna() for k, v in sig.items()}


def start_of(sig: dict[str, pd.Series]) -> str:
    return max(s.index.min() for s in sig.values()).strftime("%Y-%m-%d")


def macro_books(series, sig: dict[str, pd.Series], vol_window: int) -> dict[str, dict]:
    return {t: ml._book(series, signal=mo.SIGNAL, vol_window=vol_window,
                        external={k: as_sig(s) for k in series}) for t, s in sig.items()}


def cost_of(book: dict) -> pd.Series:
    return pd.Series([p["barCost"] for p in book["points"]],
                     index=[p["t"] for p in book["points"]], dtype=float)


def legs(series, sig: dict[str, pd.Series]) -> dict[str, dict]:
    """세 다리의 (수익 계열, 칸 행렬, 비용). `momentum_irs_legs.legs` 와 같은 합성, 거시만 북 넷."""
    start = start_of(sig)

    def cut(s: pd.Series) -> pd.Series:
        return s[(s.index >= start) & (s.index <= mo.FREEZE)]

    out: dict[str, dict] = {}
    cols_t, cols_m, cols_b, cost = {}, {}, {}, {}
    for sg, vw in me.cells_for("trend"):
        cols_t[f"{sg}-vw{vw}"] = cut(pnl_of(ml._book(series, signal=sg, vol_window=vw)))
    for vw in me.VOL_WINDOWS:
        bk = macro_books(series, sig, vw)
        cols_m[f"{mo.SIGNAL}-vw{vw}"] = cut(sum(pnl_of(b) for b in bk.values()) / len(bk))
        if vw == mo.VOL_WINDOW:
            cost["macro"] = cut(sum(cost_of(b) for b in bk.values()) / len(bk))
    cost["trend"] = cut(cost_of(ml._book(series, signal=mo.SIGNAL, vol_window=mo.VOL_WINDOW)))
    for sg, vw in me.cells_for("blend"):
        t = cols_t[f"{sg}-vw{vw}"]; m = cols_m[f"{mo.SIGNAL}-vw{vw}"]
        ix = t.index.intersection(m.index)
        cols_b[f"{sg}-vw{vw}"] = 0.5 * t.loc[ix] + 0.5 * m.loc[ix]
    ixc = cost["trend"].index.intersection(cost["macro"].index)
    cost["blend"] = 0.5 * cost["trend"].loc[ixc] + 0.5 * cost["macro"].loc[ixc]
    for leg, cols in (("trend", cols_t), ("macro", cols_m), ("blend", cols_b)):
        mat = pd.DataFrame(cols).dropna()
        out[leg] = {"mat": mat, "rets": mat[mie.BASE_COL], "cost": cost[leg].loc[mat.index], "start": start}
    return out


def placebo_for(leg: str, series, sig, mask_index) -> dict:
    t_book = ml._book(series, signal=mo.SIGNAL, vol_window=mo.VOL_WINDOW)
    bk = macro_books(series, sig, mo.VOL_WINDOW)
    price = {k: dict(zip(*series[k])) for k in series}
    tk = mie.IRS_COST_BP / cta.TICK
    pl = rz.plumbing(t_book["dates"], price, set(), tk, cta.TICK)
    pl_g = rz.plumbing(t_book["dates"], price, set(), 0.0, cta.TICK)
    keep = set(mask_index)
    mask = np.array([d in keep for d in t_book["dates"]])
    lo = max(mo.LOOKBACKS)
    n = len(bk)
    if leg == "trend":
        return rz.placebo(pl, t_book["pos"], shift_min=lo, mask=mask, pl_gross=pl_g)
    if leg == "macro":
        return placebo_multi(pl, pl_g, [(1.0 / n, b["pos"]) for b in bk.values()], mask, lo)
    return placebo_multi(pl, pl_g, [(0.5, t_book["pos"])] + [(0.5 / n, b["pos"]) for b in bk.values()], mask, lo)


def sr(x: pd.Series) -> float:
    return float(x.mean() / x.std(ddof=1) * math.sqrt(ANN)) if x.std(ddof=1) > 0 else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true", help="판정문을 안 쓴다")
    a = ap.parse_args()

    series = mie.load_irs_series()
    th = mp.themes(mp._load(), paper=True, cycle="oecd")
    sig = signals(th)
    L = legs(series, sig)
    n = len(L["blend"]["mat"])
    print()
    print(f"── IRS 세 다리 · 거시는 **논문 구조**(테마별 부호 북 넷 · 위험선호 확장 평균) · {n:,}봉 {L['blend']['start']}~{mo.FREEZE} ──")
    print(f"  {'다리':8s} {'SR':>6s} {'DSR':>8s} {'PBO':>8s} {'위약 후':>8s} {'위약 전':>8s} {'MinTRL':>7s} {'CDaR비':>7s}  판정")
    res = {}
    for leg in ("trend", "macro", "blend"):
        mat, rets = L[leg]["mat"], L[leg]["rets"]
        sr_var = float(((mat.mean() / mat.std(ddof=1)).dropna()).var(ddof=1))
        out = ev.evaluate(
            rets.reset_index(drop=True), trials=mie.TRIALS, is_oos_splits=16,
            configs=mat, sr_var=sr_var if sr_var > 0 else None,
            strategy_id=f"Momentum-{leg}-IRS{TAG}",
            cost_bp_roundtrip=mie.IRS_COST_BP * 2,
            placebo=placebo_for(leg, series, sig, mat.index),
            assumptions=[
                "★거시 다리는 **논문 구조**다 — 테마별 부호 북 넷(각 변동성 목표 100만원/일) 등가중, "
                "위험선호는 주식 초과수익 1년 − 확장 평균(이 레인 KOSPI 2015~ 이력, 최소 250일)의 부호 "
                "[OWNER 2026-09-15 · Brooks 2017 부록 B·C 대조 `docs/BROOKS2017_appendix_BC.md`].",
                "경기순환은 09-08 등록 정의(OECD EX·CP 가속 평균의 부호) 그대로 — 성장 자리의 수출은 "
                "월별 빈티지 GDP 전망이 국내에 없어 못 고쳤다. 성장·물가 북 분리(각주 12)는 수출 입력에서 "
                "더 나빠 채택하지 않았다(`RESULT_theme_books` §3-3).",
                "통화정책·위험선호 측정은 09-11 원논문 정의. 국제교역은 논문과 같다.",
                f"시행수 N = {mie.TRIALS} — `momentum_irs_legs` 와 같은 셈. 위약은 북 여럿을 같은 k 로 순환이동.",
                f"칸 {mat.shape[1]}개 · {mat.shape[0]}봉 ({mat.index[0]}~{mat.index[-1]}). "
                "첫 날이 등록 창(2017-01-06)보다 두 영업일 늦은 것은 확장 평균의 250일 때문이다.",
                "09-14 판정문 `-legs-paper`(합성·부호 = 09-08 등록 구조)와 나란히 읽는다. 이 판이 논문이고 그 판이 등록이다.",
            ])
        g, r = out["gate"], out["ranking"]
        cost = float(L[leg]["cost"].sum()); net = float(rets.sum())

        def num(v, f=".4f"):
            return f"{v:{f}}" if v is not None else "—"
        path = None if a.no_write else report.write(out)
        print(f"  {leg:8s} {sr(rets):6.3f} {num(g['dsr']):>8s} {num(g['pbo']):>8s} {num(g['placebo_p']):>8s} "
              f"{num(g['placebo_p_gross']):>8s} {num(g['min_trl_years'], '.2f'):>7s} {num(r['cdar_ratio'], '.3f'):>7s}  "
              f"{'통과' if g['overall_pass'] else '미통과'}   {path.name if path else '(안 씀)'}")
        res[leg] = {"sr": sr(rets), "net": net, "cost": cost, "gross": net + cost, "gate": g,
                    "vol": float(rets.std(ddof=1) * math.sqrt(ANN))}

    t, m, b = L["trend"]["rets"], L["macro"]["rets"], L["blend"]["rets"]
    ix = t.index.intersection(m.index)
    rho = float(np.corrcoef(t.loc[ix], m.loc[ix])[0, 1])
    base = res["trend"]["vol"]
    print()
    print(f"  추세-거시 일별손익 상관 {rho:+.3f}")
    print(f"  {'다리':8s} {'손익 전':>9s} {'비용':>8s} {'후':>9s} {'연변동':>7s} | {'맞춤누적':>9s} {'맞춤MDD':>9s} {'Calmar':>7s} {'양+년':>5s}")
    for leg, s in (("trend", t), ("macro", m), ("blend", b)):
        z = s * base / res[leg]["vol"]
        z.index = pd.to_datetime(z.index)
        cz = z.cumsum(); mdz = float((cz - cz.cummax()).min()); yrs = len(z) / ANN
        pos_y = int((z.groupby(z.index.year).sum() > 0).sum())
        print(f"  {leg:8s} {res[leg]['gross']/1e4:9,.0f} {res[leg]['cost']/1e4:8,.0f} {res[leg]['net']/1e4:9,.0f} "
              f"{res[leg]['vol']/1e4:7,.0f} | {cz.iloc[-1]/1e4:9,.0f} {mdz/1e4:9,.0f} {(cz.iloc[-1]/yrs)/abs(mdz):7.2f} {pos_y:5d}")
    bk = macro_books(series, sig, mo.VOL_WINDOW)
    start = L["blend"]["start"]
    print("  거시 북별 SR(vw60): " + " · ".join(
        f"{k} {sr(pnl_of(v)[(pnl_of(v).index >= start) & (pnl_of(v).index <= mo.FREEZE)]):.3f}" for k, v in bk.items()))
    print("  ⚠ 이 판은 논문 구조의 «판정문»이지 등록이 아니다. 등록서(`PREREG_sleeve_5050`)가 이 판정문을 인용하면 그때 등록이다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
