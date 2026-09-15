# -*- coding: utf-8 -*-
r"""배분 히트맵 — 행은 구성요소, 열은 월, 색은 월평균 억원 [OWNER 2026-09-15 「히트맵으로」].

    python -m scripts.sleeve_allocation_heatmap

`sleeve_allocation.py` 가 낸 일별 표(`output/sleeve_allocation_daily.csv`)를 월평균으로 접어
두 장으로 그린다. 위는 증거금 사용액(평균회귀 · 슬리브 · 합산, 상한 100억), 아래는 슬리브 액면
(북별 총액면 다섯 · 순액면 3Y·10Y). 크기(magnitude)라 **한 색상(house navy)의 밝기 한 축**으로만
칠하고, 두 장은 눈금이 달라 각자 색막대를 둔다(이중축 대신 두 그림).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
STYLE = BACKEND.parents[2] / "deliverables" / "크레딧논문"
sys.path.insert(0, str(STYLE))
import research_style as rs                                     # noqa: E402
import matplotlib.pyplot as plt                                 # noqa: E402
from matplotlib.colors import LinearSegmentedColormap           # noqa: E402

SRC = BACKEND / "output" / "sleeve_allocation_daily.csv"
OUT = BACKEND / "output" / "sleeve_allocation_heatmap.png"
CAP = 100.0

#: 한 색상, 밝음 → 어두움. 바탕색에서 house navy 까지.
CMAP = LinearSegmentedColormap.from_list("navy_seq", ["#FFFFFF", "#DCE3EC", "#9FB3C8", "#5E7EA3", "#1F4E79"])


def panel(ax, mat: pd.DataFrame, vmax: float | None, labels: list[str], unit: str, rowwise: bool = False):
    """rowwise=True 면 행마다 제 최대값 대비(0~1)로 칠한다 — 작은 행의 흐름이 보이게. 절대값은 오른쪽 라벨이 진다."""
    arr = mat.to_numpy(dtype=float)
    if rowwise:
        arr = arr / np.maximum(arr.max(axis=1, keepdims=True), 1e-9)
        vmax = 1.0
    im = ax.imshow(arr, aspect="auto", cmap=CMAP, vmin=0, vmax=vmax, interpolation="nearest")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8.5, color=rs.INK)
    months = mat.columns
    jan = [i for i, m in enumerate(months) if m.month == 1]
    ax.set_xticks(jan)
    ax.set_xticklabels([str(months[i].year) for i in jan], fontsize=8.5, color=rs.GREY_D)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    # 행 사이 2px 바탕색 틈, 연도 경계에 옅은 세로줄
    for y in range(1, len(labels)):
        ax.axhline(y - 0.5, color="white", lw=2)
    for i in jan[1:]:
        ax.axvline(i - 0.5, color="white", lw=1.2)
    # 오른쪽 직접 라벨 — 행 평균
    for y, lab in enumerate(labels):
        ax.text(len(months) - 0.5 + 1.0, y, f"평균 {mat.iloc[y].mean():,.1f} · 최대 {mat.iloc[y].max():,.0f}{unit}",
                va="center", ha="left", fontsize=7.5, color=rs.GREY_D, clip_on=False)
    return im


def main() -> int:
    df = pd.read_csv(SRC, encoding="utf-8-sig", parse_dates=["date"]).set_index("date") / 1e8
    m = df.resample("MS").mean()
    m.columns = df.columns
    mon = m.index

    top = pd.DataFrame({"평균회귀 장부": m["mr_margin"], "합산": m["total_margin"]}).T
    top.columns = mon
    bot = pd.DataFrame({"슬리브 증거금": m["sl_margin"], "추세 북": m["sl_gross_trend"], "경기순환 북": m["sl_gross_cycle"], "통화정책 북": m["sl_gross_policy"],
                        "국제교역 북": m["sl_gross_trade"], "위험선호 북": m["sl_gross_risk"],
                        "순액면 3Y": m["sl_face_3Y"], "순액면 10Y": m["sl_face_10Y"]}).T
    bot.columns = mon

    rs.apply()
    fig, axes = plt.subplots(2, 1, figsize=(rs.FIG_W, 6.8), gridspec_kw={"height_ratios": [2, 8], "hspace": 0.5},
                             constrained_layout=False)
    fig.subplots_adjust(top=0.82, bottom=0.09, left=0.13, right=0.80)
    im1 = panel(axes[0], top, CAP, list(top.index), "억")
    cb1 = fig.colorbar(im1, ax=axes[0], fraction=0.06, pad=0.24, aspect=10)
    cb1.set_label("증거금 사용액 (억) · 상한 100", fontsize=7.5, color=rs.SUB)
    cb1.ax.tick_params(labelsize=7, length=0, colors=rs.GREY_D)
    cb1.outline.set_visible(False)
    im2 = panel(axes[1], bot, None, list(bot.index), "억", rowwise=True)
    cb2 = fig.colorbar(im2, ax=axes[1], fraction=0.04, pad=0.24, aspect=18, ticks=[0, 0.5, 1.0])
    cb2.ax.set_yticklabels(["0", "½", "행 최대"])
    cb2.set_label("행마다 제 최대값 대비", fontsize=7.5, color=rs.SUB)
    cb2.ax.tick_params(labelsize=7, length=0, colors=rs.GREY_D)
    cb2.outline.set_visible(False)
    # 상한을 넘은 달 표시 — 합산 행 위에 작은 점
    hit = (df["total_margin"] > CAP).resample("MS").sum()
    over = [i for i, mo_ in enumerate(mon) if hit.get(mo_, 0) > 0]
    for i in over:
        axes[0].plot(i, -0.75, marker="v", color=rs.CONTRAST, ms=4, clip_on=False)
    rs.exhibit(fig, 2, "증거금은 평균회귀가 채우고, 슬리브는 2억 안팎으로 얇게 얹힌다",
               "위: 증거금 사용액(억, 월평균, 절대 눈금 · ▼ 합산 100억 초과 달) · "
               "아래: 슬리브 항목(월평균, 행별 최대 대비 · 오른쪽에 평균·최대 억)",
               "자료: 자체 산출 (sleeve_allocation_heatmap.py · 2020-01~2026-09)")
    fig.savefig(OUT, dpi=rs.DPI)
    plt.close(fig)
    print(f"→ {OUT}")
    print("증거금 합산 월평균 최대:", f"{top.loc['합산'].max():.1f}억 ({top.loc['합산'].idxmax():%Y-%m})",
          "· 슬리브 순액면 월평균 최대:", f"{(bot.loc['순액면 3Y'] + bot.loc['순액면 10Y']).max():.1f}억")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
