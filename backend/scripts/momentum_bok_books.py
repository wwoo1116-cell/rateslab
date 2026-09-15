# -*- coding: utf-8 -*-
r"""논문 구조 + 한은 전망치 — 성장 북·물가 북을 따로, 위험선호는 확장 평균 대비 [OWNER 2026-09-15].

    python -m scripts.momentum_bok_books

## 무엇을 세우나

오너 지시: 「전망치를 월별로 하지 말고 한국은행 자료를 쓰고, 성장 북과 물가 북을 따로
세우고, 확장 평균 대비로」. 부록 B·C 대조(`docs/BROOKS2017_appendix_BC.md`)의 어긋남
넷 중 자료가 있는 셋을 한꺼번에 논문 쪽으로 놓는다.

    성장 북    한은 경제전망 GDP 전망의 「네 발표 전」 대비 변화 부호 (발표일 다음 영업일부터 플랫)
    물가 북    같은 방식의 CPI 전망 변화 부호
    경기순환   성장 북·물가 북의 평균 (각주 12) → 테마 넷 등가중 (성장·물가는 각 1/8)
    통화정책   통안 2Y 1년 변화 부호 (09-11 논문 수정 그대로)
    국제교역   NEER 1년 로그변화 부호 (논문과 같음)
    위험선호   주식 초과수익 1년 − 그때까지의 확장 평균, 의 부호 (부록 C)
    구성       테마별 부호 북, 각 북 변동성 목표 100만원/일, 등가중 (부록 C 방향성)

전망 축은 셋을 다 낸다 — 금년(09-14 등록 규약) · 내년 · 금년내년평균. 논문은 지평을 명시하지
않으므로 어느 축이 «논문»인지는 모호하고, 그 모호함을 오너에게 묻는다.

## ⚠ 지위

표본내 탐색. 등록 둘(09-08 매크로 · 09-15 슬리브)은 안 바꾼다.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
VINT = BACKEND.parents[2] / "data" / "krw-macro-vintage"
sys.path.insert(0, str(VINT / "src"))

from app import ctabacktest as cta                              # noqa: E402
from app import momentum as mo                                  # noqa: E402
from evaluation import metrics as ev, randomization as rz       # noqa: E402
from scripts import macro_paper_fix as mp                       # noqa: E402
from scripts import momentum_evaluate as me                     # noqa: E402
from scripts import momentum_irs_evaluate as mie                # noqa: E402
from scripts import momentum_irs_legs as ml                     # noqa: E402
from scripts.momentum_theme_books import as_sig, placebo_multi, pnl_of, sr   # noqa: E402
import build_cycle_bok as bcb                                   # noqa: E402

ANN = 252
MIN_MEAN = 250   # 확장 평균의 최소 관측(1년 초과수익 1년치) — 모호한 자리 ②


def spread(t: pd.DataFrame, col: str, index: pd.DatetimeIndex) -> pd.Series:
    """발표일 다음 영업일부터 다음 발표 전까지 플랫 (`build_cycle_bok.spread_daily` 와 같은 규칙)."""
    out = pd.Series(np.nan, index=index, dtype=float)
    for _ym, row in t.iterrows():
        hit = index[index > row["published"]]
        if len(hit) == 0:
            continue
        out.loc[index >= hit[0]] = row[col]
    return out


def main() -> int:
    t0 = time.time()
    series = mie.load_irs_series()
    d = mp._load()
    th = mp.themes(d, paper=True, cycle="oecd")
    idx = th.index

    # 위험선호 — 확장 평균 대비
    eq_ex = -th["risk_raw"]
    risk_dm = -(eq_ex - eq_ex.expanding(min_periods=MIN_MEAN).mean())
    sign = {"policy": np.sign(th["policy_raw"]), "trade": np.sign(th["trade_raw"]),
            "risk0": np.sign(th["risk_raw"]), "risk": np.sign(risk_dm),
            "cycle_oecd": np.sign(th["cycle_raw"])}

    # 한은 전망 — 성장·물가 따로, 축 셋
    vt = bcb.vintage_table()
    for base in ("cur", "next"):
        pass
    vt["d_gdp_avg"] = vt[["d_gdp_cur", "d_gdp_next"]].mean(axis=1, skipna=False)
    vt["d_cpi_avg"] = vt[["d_cpi_cur", "d_cpi_next"]].mean(axis=1, skipna=False)
    bok = {}
    for ax in ("cur", "next", "avg"):
        bok[ax] = {"growth": np.sign(-spread(vt, f"d_gdp_{ax}", idx)),
                   "inflation": np.sign(-spread(vt, f"d_cpi_{ax}", idx)),
                   "cycle_mean": np.sign(-(spread(vt, f"d_gdp_{ax}", idx) + spread(vt, f"d_cpi_{ax}", idx)) / 2)}
    zeros = {ax: {"gdp": int((vt[f"d_gdp_{ax}"] == 0).sum()), "cpi": int((vt[f"d_cpi_{ax}"] == 0).sum()),
                  "n": int(vt[f"d_gdp_{ax}"].notna().sum())} for ax in ("cur", "next", "avg")}

    full_oecd = th[["cycle_raw", "policy_raw", "trade_raw", "risk_raw"]].notna().all(axis=1)
    def W(s): return s.where(full_oecd)

    sigs = {
        "합성·부호 (등록·OECD)": {"composite": (1.0, W(th["macro_sign"]))},
        "북넷·부호·평균제거 (OECD)": {"cycle": (1.0, W(sign["cycle_oecd"])), "policy": (1.0, W(sign["policy"])),
                                 "trade": (1.0, W(sign["trade"])), "risk": (1.0, W(sign["risk"]))},
    }
    for ax, label in (("cur", "금년"), ("next", "내년"), ("avg", "금년내년평균")):
        sigs[f"한은·{label}·북분리"] = {"growth": (0.5, W(bok[ax]["growth"])), "inflation": (0.5, W(bok[ax]["inflation"])),
                                    "policy": (1.0, W(sign["policy"])), "trade": (1.0, W(sign["trade"])),
                                    "risk": (1.0, W(sign["risk"]))}
    sigs["한은·금년·경기순환합성"] = {"cycle": (1.0, W(bok["cur"]["cycle_mean"])), "policy": (1.0, W(sign["policy"])),
                                "trade": (1.0, W(sign["trade"])), "risk": (1.0, W(sign["risk"]))}
    sigs["한은·금년·북분리·위험선호0대비"] = {"growth": (0.5, W(bok["cur"]["growth"])), "inflation": (0.5, W(bok["cur"]["inflation"])),
                                       "policy": (1.0, W(sign["policy"])), "trade": (1.0, W(sign["trade"])),
                                       "risk": (1.0, W(sign["risk0"]))}

    start = max(min(as_sig(s_.dropna())) for v in sigs.values() for _w, s_ in v.values())
    print(f"공통 창 {start} ~ {mo.FREEZE}")
    print("한은 전망 변화가 정확히 0 인 발표(축별): " + " · ".join(
        f"{ax} GDP {z['gdp']}/{z['n']} CPI {z['cpi']}/{z['n']}" for ax, z in zeros.items()))

    def cut(s: pd.Series) -> pd.Series:
        return s[(s.index >= start) & (s.index <= mo.FREEZE)]

    trend_cells = {vw: cut(pnl_of(ml._book(series, signal=mo.SIGNAL, vol_window=vw))) for vw in me.VOL_WINDOWS}
    trend = trend_cells[mo.VOL_WINDOW]
    t_book = ml._book(series, signal=mo.SIGNAL, vol_window=mo.VOL_WINDOW)
    dates = t_book["dates"]
    price = {k: dict(zip(*series[k])) for k in series}
    tk = mie.IRS_COST_BP / cta.TICK
    pl = rz.plumbing(dates, price, set(), tk, cta.TICK)
    pl_g = rz.plumbing(dates, price, set(), 0.0, cta.TICK)
    lo = max(mo.LOOKBACKS)
    keep = set(trend.index)
    mask = np.array([dd in keep for dd in dates])
    print(f"추세 다리 {len(trend):,}봉 · SR {sr(trend):.3f}  ({time.time()-t0:,.0f}s)", flush=True)

    out: dict = {"window": [start, mo.FREEZE, len(trend)], "zeros": zeros,
                 "trend": {"sr": sr(trend), "vol": float(trend.std(ddof=1) * math.sqrt(ANN))}, "variants": {}}
    rows = []
    for name, parts in sigs.items():
        books = {vw: {t: ml._book(series, signal=mo.SIGNAL, vol_window=vw, external={k: as_sig(s_) for k in series})
                      for t, (_w, s_) in parts.items()} for vw in me.VOL_WINDOWS}
        wsum = sum(w_ for w_, _s in parts.values())
        wt = {t: w_ / wsum for t, (w_, _s) in parts.items()}
        macro_cells = {vw: cut(sum(wt[t] * pnl_of(b) for t, b in books[vw].items())) for vw in me.VOL_WINDOWS}
        macro = macro_cells[mo.VOL_WINDOW]
        ix = trend.index.intersection(macro.index)
        blend_cells = {vw: 0.5 * trend_cells[vw].loc[ix] + 0.5 * macro_cells[vw].loc[ix] for vw in me.VOL_WINDOWS}
        blend = blend_cells[mo.VOL_WINDOW]
        pos_sum = sum(np.abs(np.asarray(b["pos"][k], dtype=float)) for b in books[mo.VOL_WINDOW].values() for k in b["pos"])
        zero = float((pos_sum[mask] == 0).mean())
        rho = float(np.corrcoef(trend.loc[ix], macro.loc[ix])[0, 1])
        per = {t: sr(cut(pnl_of(b))) for t, b in books[mo.VOL_WINDOW].items()}
        res = {"zero_share": zero, "rho_trend": rho, "per_theme_sr": per}
        for leg, cells, series_ in (("macro", macro_cells, macro), ("blend", blend_cells, blend)):
            mat = pd.DataFrame({f"{mo.SIGNAL}-vw{vw}": c for vw, c in cells.items()}).dropna()
            sr_var = float(((mat.mean() / mat.std(ddof=1)).dropna()).var(ddof=1))
            if leg == "macro":
                wts = [(wt[t], b["pos"]) for t, b in books[mo.VOL_WINDOW].items()]
            else:
                wts = [(0.5, t_book["pos"])] + [(0.5 * wt[t], b["pos"]) for t, b in books[mo.VOL_WINDOW].items()]
            pb = placebo_multi(pl, pl_g, wts, mask, lo)
            e = ev.evaluate(mat[f"{mo.SIGNAL}-vw{mo.VOL_WINDOW}"].reset_index(drop=True),
                            trials=mie.TRIALS, is_oos_splits=16, configs=mat,
                            sr_var=sr_var if sr_var > 0 else None,
                            strategy_id=f"explore-bok-{name}-{leg}", cost_bp_roundtrip=mie.IRS_COST_BP * 2,
                            placebo=pb, assumptions=["표본내 탐색 — 판정문에 쓰지 않는다"])
            g = e["gate"]
            res[leg] = {"sr": sr(series_), "vol": float(series_.std(ddof=1) * math.sqrt(ANN)),
                        "dsr": g["dsr"], "pbo": g["pbo"], "p": g["placebo_p"], "p_gross": g["placebo_p_gross"],
                        "pass": bool(g["overall_pass"])}
        z = blend * (trend.std(ddof=1) / blend.std(ddof=1))
        cz = z.cumsum(); mdz = float((cz - cz.cummax()).min()); yrs = len(z) / ANN
        res["blend_matched"] = {"cum": float(cz.iloc[-1]), "mdd": mdz, "calmar": float((cz.iloc[-1] / yrs) / abs(mdz))}
        out["variants"][name] = res
        rows.append((name, res))
        print(f"  [{name}] 끝  ({time.time()-t0:,.0f}s)", flush=True)

    ct = trend.cumsum(); mdt = float((ct - ct.cummax()).min())
    print()
    print(f"── 논문 구조 + 한은 전망치 · 창 {start}~{mo.FREEZE} {len(trend):,}봉 ──")
    print(f"  추세 단독: SR {sr(trend):.3f} · 누적 {ct.iloc[-1]/1e4:,.0f}만 · MDD {mdt/1e4:,.0f}만 · Calmar {(ct.iloc[-1]/(len(trend)/ANN))/abs(mdt):.2f}")
    print()
    print(f"  {'변형':26s} {'거시SR':>7s} {'거시vol':>8s} {'0비중':>6s} {'추세ρ':>6s} {'거시위약후/전':>14s} | "
          f"{'50/50SR':>8s} {'DSR':>7s} {'PBO':>7s} {'위약후/전':>14s} {'판정':>4s} | {'맞춤누적':>8s} {'맞춤MDD':>8s} {'Calmar':>6s}")
    for name, r in rows:
        m, b, bm = r["macro"], r["blend"], r["blend_matched"]
        print(f"  {name:26s} {m['sr']:7.3f} {m['vol']/1e4:7,.0f}만 {r['zero_share']:6.3f} {r['rho_trend']:+6.3f} "
              f"{m['p']:6.4f}/{m['p_gross']:6.4f} | {b['sr']:8.3f} {b['dsr']:7.4f} {b['pbo']:7.4f} "
              f"{b['p']:6.4f}/{b['p_gross']:6.4f} {'통과' if b['pass'] else '미통과':>4s} | "
              f"{bm['cum']/1e4:8,.0f} {bm['mdd']/1e4:8,.0f} {bm['calmar']:6.2f}")
    print()
    for name, r in rows:
        print(f"  {name} 북별 SR(vw60): " + " · ".join(f"{t} {v:.3f}" for t, v in r["per_theme_sr"].items()))

    p = BACKEND / "output" / "momentum_bok_books.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(f"\n  → {p}  ({time.time()-t0:,.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
