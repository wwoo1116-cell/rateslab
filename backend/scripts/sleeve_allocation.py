# -*- coding: utf-8 -*-
r"""배분이 액면으로 어떻게 흘러왔나 — 증거금 상한 100억 장부 위에서 [OWNER 2026-09-15].

    python -m scripts.sleeve_allocation

위험 기준으로만 적혀 있던 결합(총위험 고정 · w 0.25)을 **원화 액면과 증거금**으로 편다.
평균회귀 장부는 `margin_budget_book.simulate(with_face=True)` 의 만기별 배분 경로에서,
슬리브(추세·거시 50/50, 거시는 논문 구조)는 다섯 북의 포지션(DV01)에서 액면을 세운다.
등록서 W4 와 같은 산술(`sleeve_prereg_5050 --structure books`)이라 수가 맞아야 한다.

    MR 다리    액면 = 배정 증거금 / 증거금률(≤3Y 5% · >3Y 10%), 총위험 고정 배수 k_mr
    슬리브     DV01 = 0.5·추세 + 0.125·(cycle+policy+trade+risk), 배수 mult = k_tr·σ_MR(원) / σ_슬리브(원)
               액면(만기별) = |DV01| / pv01(1억당) × 1억 · 증거금 = 액면 × 5%
               «순액면» 은 다섯 북을 합친 DV01, «총액면» 은 북별 |DV01| 의 합(배분 그림용)

산출: output/sleeve_allocation_daily.csv · output/sleeve_allocation.png · 연도별 표(stdout)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
STYLE = BACKEND.parents[2] / "deliverables" / "크레딧논문"   # Projects/deliverables
sys.path.insert(0, str(STYLE))

from app import momentum as mo                                  # noqa: E402
from scripts import crs_evaluate as ce                          # noqa: E402
from scripts import hedge_test as ht                            # noqa: E402
from scripts import macro_paper_fix as mp                       # noqa: E402
from scripts import momentum_irs_evaluate as mie                # noqa: E402
from scripts import momentum_irs_legs as ml                     # noqa: E402
from scripts import momentum_irs_books as mib                   # noqa: E402
from scripts import sleeve_margin as sg                         # noqa: E402
from scripts.momentum_theme_books import pnl_of                 # noqa: E402

ANN = 252
W = 0.25
RATE = 0.05
BOOKS = ("trend", "cycle", "policy", "trade", "risk")
BW = {"trend": 0.5, "cycle": 0.125, "policy": 0.125, "trade": 0.125, "risk": 0.125}


def main() -> int:
    # ── 슬리브 다섯 북 ──────────────────────────────────────────────────
    series = mie.load_irs_series()
    sig = mib.registered_signals(series)         # ★IRS 달력 이월 포함 — 한 자리
    t_book = ml._book(series, signal=mo.SIGNAL, vol_window=mo.VOL_WINDOW)
    m_books = mib.macro_books(series, sig, mo.VOL_WINDOW)
    books = {"trend": t_book, **m_books}
    dates = [str(x)[:10] for x in t_book["dates"]]
    start = mib.start_of(sig)
    blend = sum(BW[b] * pnl_of(books[b]) for b in BOOKS)
    blend.index = [str(x)[:10] for x in blend.index]
    blend = blend[(blend.index >= start) & (blend.index <= mo.FREEZE)]
    vol_sleeve = float(blend.std(ddof=1) * math.sqrt(ANN))
    pv = sg.pv01_per_100m()

    # ── 평균회귀 장부(상한판 · 로트 50) ──────────────────────────────────
    mb = ce._lane()
    net, facts = ce.net_returns(mb, ce.REGISTERED_LOT_UK, "bound")
    P, L, Z, meta = mb.load()
    _d, used, dv_mr, _e, _b, wface = mb.simulate(P, L, Z, meta, ce.REGISTERED_LOT_UK, with_face=True)
    mr = ht.mr_returns()
    mr_vol_krw = float(net.std(ddof=1) * math.sqrt(ANN) * mb.CAP)
    idx = sorted(set(mr.index) & set(blend.index))
    m = ht.unit_vol(mr.loc[idx]).to_numpy()
    t = ht.unit_vol(blend.loc[idx]).to_numpy()
    s_mix = float(((1 - W) * m + W * t).std(ddof=1) * math.sqrt(ANN))
    k_mr, k_tr = (1 - W) / s_mix, W / s_mix
    mult = (k_tr * mr_vol_krw) / vol_sleeve
    print(f"창 {idx[0]}~{idx[-1]} {len(idx):,}봉 · MR 연변동성 {mr_vol_krw/1e8:.2f}억 · 슬리브 실현 {vol_sleeve/1e8:.3f}억 → 배수 {mult:.2f}"
          f" · 총위험 고정 k_mr {k_mr:.3f} · k_sleeve {k_tr:.3f} · 슬리브 목표 변동성 {k_tr*mr_vol_krw/1e8:.3f}억")

    # ── 일별 액면 ───────────────────────────────────────────────────────
    pos_ix = {d: i for i, d in enumerate(dates)}
    rows = []
    wf = wface.copy(); wf.index = [str(x)[:10] for x in wf.index]
    us = pd.Series(used.to_numpy(dtype=float), index=[str(x)[:10] for x in used.index])
    dvm = pd.Series(dv_mr.to_numpy(dtype=float), index=[str(x)[:10] for x in dv_mr.index])
    for d in idx:
        i = pos_ix[d]
        r = {"date": d}
        # MR
        mr_face = {tn: float(wf.at[d, tn]) * meta[tn]["base_face"] * k_mr for tn in mb.T}
        r["mr_face_total"] = sum(mr_face.values())
        r["mr_face_short"] = sum(v for tn, v in mr_face.items() if mb.MARGIN[tn] <= 0.05)
        r["mr_face_long"] = sum(v for tn, v in mr_face.items() if mb.MARGIN[tn] > 0.05)
        r["mr_margin"] = float(us.at[d]) * mb.CAP * k_mr
        r["mr_dv01"] = float(dvm.at[d]) * k_mr
        # 슬리브 — 북별 DV01 (₩/bp), 배수 반영
        net_dv = {k: 0.0 for k in pv}
        gross_face = {b: 0.0 for b in BOOKS}
        for b in BOOKS:
            for k in pv:
                dv = float(books[b]["pos"][k][i]) / 100.0 * BW[b] * mult
                net_dv[k] += dv
                gross_face[b] += abs(dv) / pv[k] * 1e8
        for k in pv:
            r[f"sl_face_{k}"] = abs(net_dv[k]) / pv[k] * 1e8
            r[f"sl_dv01_{k}"] = net_dv[k]
        r["sl_face_net"] = sum(r[f"sl_face_{k}"] for k in pv)
        for b in BOOKS:
            r[f"sl_gross_{b}"] = gross_face[b]
        r["sl_face_gross"] = sum(gross_face.values())
        r["sl_margin"] = r["sl_face_net"] * RATE
        r["sl_dv01"] = sum(abs(v) for v in net_dv.values())
        r["total_margin"] = r["mr_margin"] + r["sl_margin"]
        rows.append(r)
    df = pd.DataFrame(rows).set_index("date")
    df.index = pd.to_datetime(df.index)
    out_csv = BACKEND / "output" / "sleeve_allocation_daily.csv"
    df.to_csv(out_csv, encoding="utf-8-sig", float_format="%.0f")

    # ── 연도별 표 ───────────────────────────────────────────────────────
    y = df.groupby(df.index.year)
    print()
    print(f"{'연도':5s} {'MR증거금 평균/최대':>20s} {'MR액면 평균':>12s} {'슬리브 순액면 평균/최대':>24s} {'  3Y':>8s} {'  10Y':>8s} "
          f"{'슬리브 증거금 평/최':>20s} {'합산 증거금 최대':>14s} {'DV01 MR/슬리브':>16s}")
    for yr, g in y:
        print(f"{yr:<5d} {g['mr_margin'].mean()/1e8:8.1f} /{g['mr_margin'].max()/1e8:6.1f}억 "
              f"{g['mr_face_total'].mean()/1e8:10.0f}억 "
              f"{g['sl_face_net'].mean()/1e8:9.1f} /{g['sl_face_net'].max()/1e8:6.1f}억 "
              f"{g['sl_face_3Y'].mean()/1e8:7.1f} {g['sl_face_10Y'].mean()/1e8:7.1f} "
              f"{g['sl_margin'].mean()/1e8:8.2f} /{g['sl_margin'].max()/1e8:5.2f}억 "
              f"{g['total_margin'].max()/1e8:12.1f}억 "
              f"{g['mr_dv01'].mean()/1e4:7.0f}/{g['sl_dv01'].mean()/1e4:5.0f}만")
    print()
    print("슬리브 북별 총액면 평균(억) — 배분 그림:")
    print("  " + " · ".join(f"{b} {df[f'sl_gross_{b}'].mean()/1e8:.1f}" for b in BOOKS)
          + f" · 합 {df['sl_face_gross'].mean()/1e8:.1f} (순액면 {df['sl_face_net'].mean()/1e8:.1f} — 북끼리 상쇄)")
    over = int((df["total_margin"] > mb.CAP).sum())
    print(f"합산 증거금이 100억을 넘는 날 {over}일 / {len(df):,}일 · 슬리브 순액면 최대 {df['sl_face_net'].max()/1e8:.1f}억 "
          f"({df['sl_face_net'].idxmax():%Y-%m-%d}) · MR 증거금 최대 {df['mr_margin'].max()/1e8:.1f}억")
    print(f"위험 몫(평균 DV01): MR {df['mr_dv01'].mean()/1e4:,.0f}만/bp · 슬리브 {df['sl_dv01'].mean()/1e4:,.0f}만/bp")

    # ── 그림 ─────────────────────────────────────────────────────────────
    import research_style as rs                                   # noqa: PLC0415
    import matplotlib.pyplot as plt                                # noqa: PLC0415
    rs.apply()
    fig, axes = rs.figure(nrows=2, height=6.4, right=0.86, hspace=0.55)
    ax = axes[0]
    cols = [rs.ACCENT, rs.CONTRAST, rs.GREY_D, rs.GREY_M, rs.GREY_L]
    stack = [df[f"sl_gross_{b}"].rolling(20).mean() / 1e8 for b in BOOKS]
    ax.stackplot(df.index, *stack, colors=cols, alpha=0.9, linewidth=0)
    ax.plot(df.index, df["sl_face_net"].rolling(20).mean() / 1e8, color=rs.INK, lw=1.0)
    rs.frame(ax)
    rs.year_axis(ax, step=1, fmt="%Y")
    top = float(df["sl_face_gross"].rolling(20).mean().max() / 1e8)
    for j, b in enumerate(BOOKS):
        ax.text(df.index[-1], top * (0.95 - 0.11 * j), b, color=cols[j], fontsize=8, ha="left", va="top",
                transform=ax.transData)
    rs.exhibit(fig, 1, "슬리브 액면은 평균 42억, 다섯 북이 서로 상쇄해 순액면은 그 아래다",
               "슬리브 북별 총액면(쌓음, 억) · 검은 선 = 순액면 · 20일 이동평균 · 총위험 고정 w 0.25 배수 반영",
               "자료: 자체 산출 (sleeve_allocation.py)")
    ax = axes[1]
    ax.stackplot(df.index, df["mr_margin"].rolling(20).mean() / 1e8, df["sl_margin"].rolling(20).mean() / 1e8,
                 colors=[rs.GREY_L, rs.ACCENT], alpha=0.95, linewidth=0)
    ax.axhline(mb.CAP / 1e8, color=rs.CONTRAST, lw=0.9, ls="--")
    rs.frame(ax)
    rs.year_axis(ax, step=1, fmt="%Y")
    ax.text(df.index[-1], mb.CAP / 1e8, " 상한 100억", color=rs.CONTRAST, fontsize=8, va="center")
    ax.text(df.index[-1], (df["mr_margin"].rolling(20).mean() / 1e8).iloc[-1] * 0.5, " 평균회귀", color=rs.GREY_D, fontsize=8, va="center")
    fig.text(0.035, 0.44, "증거금 사용액(억) · 회색 = 평균회귀 장부(로트 50 · 배수 k_mr) · 남색 = 슬리브(액면 × 5%) · 20일 이동평균",
             color=rs.SUB, fontsize=8)
    out_png = BACKEND / "output" / "sleeve_allocation.png"
    fig.savefig(out_png, dpi=rs.DPI)
    plt.close(fig)
    print(f"\n  → {out_csv}\n  → {out_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
