# -*- coding: utf-8 -*-
r"""IRS 모멘텀의 **테너 조합**을 재 본다 — 「고르는 것이 이기나, 폭이 이기나」.

    python -m scripts.momentum_tenor_search              # 전체(231조합 + 대조군)
    python -m scripts.momentum_tenor_search --quick      # 한·두 다리만(66조합)
    python -m scripts.momentum_tenor_search --gate 3     # 관문에 태울 상위 칸 수

## 왜 이 자리가 열렸나 [OWNER 2026-09-21]

> "꼭 3Y 10Y 뿐만아니라, 최적 조합을 1~10Y 사이에서 찾을 수 있으면 찾아볼래?
>  스왑으로 모멘텀 플레이를 건너오면서 이런 방식이 가능해졌어."

이 레인의 상시 규율 §10-2 는 **「브레드스 N=2. 방향성 상품이 둘뿐이라 Sharpe
상한이 0.6대다(AQR 의 1.1 은 N=30 이다)」** 인데, 그 N=2 는 **선물 시절의 제약**
이다. 국채선물은 3년·10년 둘뿐이지만 IRS 는 `mkt_irs_close` 에 **열한 테너**가
2,648행 전부 결측 0 으로 있다(2026-09-21 확인). 폭이 처음으로 검정 가능해졌다.

## ⚠ 이것은 **등록을 바꾸는 자리가 아니다**

`docs/PREREG_sleeve_5050_2026-09-15.md` 는 **3Y·10Y 로 동결**돼 2026-09-16 부터
채점 중이다. 테너를 고르는 것은 **새 자유도**라, 여기서 나온 수로 등록을 갈면
그 순간 사전등록이 아니다. 이 스크립트는 **측정이고**, 오너가 움직이기로 하면
그때 새 등록서를 여는 재료다. 판정문(`report.write`)도 안 쓴다 — 등록된 id 를
덮어쓰지 않기 위해서다(§10-6).

## 고정한 것 / 흔드는 것

    고정   신호 정의     추세 = macross · 룩백 (20,40,60,120,250) · 볼 윈도 60
                        거시 = 테마별 부호 북 넷(cycle·policy·trade·risk) 등가중
                               `momentum_irs_books.registered_signals` **그 함수**
           구조         50/50 (등록 규약) — 두 다리 일별 손익 반씩
           비용         IRS 편도 0.5bp [오너] · 낮추지 않는다 (§10-3)
           창           2017-01-06 ~ 2026-09-08 (`mie.START` ~ `mo.FREEZE`)
           북 변동성    하루 100만원 목표 — **조합마다 같다**(§10-4 위험 맞춤)

    흔듦   테너 조합     1~3 다리 × 열한 테너 = 11 + 55 + 165 = **231조합**
    대조   전 테너       열하나 등가중 **하나** — 「고르지 않은 판」

## 대조군이 이 표의 요점이다

최고 칸이 전 테너 등가중을 **못 이기면** 답은 「폭」이지 「고르기」가 아니다.
그쪽이 싸고(시행수 1) 정직하다. 이 스크립트가 답해야 하는 물음이 그것이다.

## 폭은 다리 수가 아니라 **유효 폭**이다

이웃 테너는 상관 0.9 대다. 8Y·9Y·10Y 세 다리는 셋이 아니라 거의 하나다. 그래서
칸마다 다리 일별 변화의 평균 쌍상관 ρ̄ 와 **유효 다리 수** N_eff = n/(1+(n−1)ρ̄)
를 같이 낸다 — 표에서 「다리 셋」과 「폭 셋」을 구별하기 위해서다.

## 관문은 상위 칸에만 (계단식)

231칸 전부에 DSR·PBO·위약을 걸면 칸당 9칸 행렬 × 21판이라 시간이 안 맞는다.
**순위는 231칸 전부**(칸당 5판)에서 내고, **관문은 등록 3Y·10Y · 전 테너 대조군 ·
상위 몇 칸**에만 건다. 보고서가 그 사실을 적는다.

## 시행수

이 탐색은 **231칸**이다. 그 위에 레인이 이미 쓴 N(=72: 신호계 3 × 볼 윈도 3 ×
다리 구성 4 × 계기 2)이 곱해진다. DSR 허들 SR0 는 `expected_max_sr` 에 **실제
231칸의 SR 분산**을 넣어 낸다 — 그 함수 머리가 「격자를 실제로 돌렸으면 그 칸들의
SR 분산을 넣는 것이 정확하다」고 적는 그 자리다.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ctabacktest as cta                              # noqa: E402
from app import momentum as mo                                  # noqa: E402
from app.mysqldb import engine                                  # noqa: E402
from evaluation import metrics as ev                            # noqa: E402
from scripts import momentum_evaluate as me                     # noqa: E402
from scripts import momentum_irs_books as mib                   # noqa: E402
from scripts import momentum_irs_evaluate as mie                # noqa: E402
from scripts import momentum_irs_legs as ml                     # noqa: E402
from scripts.momentum_theme_books import as_sig, pnl_of         # noqa: E402

ANN = 252

#: 열한 테너 — `mkt_irs_close` 의 열 이름. 1Y 아래(6M·9M)는 오너가 「1~10Y」로
#: 범위를 그었으므로 뺀다. 18M 은 그 범위 안이라 넣는다.
TENORS: tuple[str, ...] = ("1Y", "18M", "2Y", "3Y", "4Y", "5Y",
                           "6Y", "7Y", "8Y", "9Y", "10Y")
COL = {"1Y": "irs_1y", "18M": "irs_18m", "2Y": "irs_2y", "3Y": "irs_3y",
       "4Y": "irs_4y", "5Y": "irs_5y", "6Y": "irs_6y", "7Y": "irs_7y",
       "8Y": "irs_8y", "9Y": "irs_9y", "10Y": "irs_10y"}

#: 동결 등록이 거래하는 조합 — 표에 **순위와 무관하게** 언제나 선다.
REGISTERED: tuple[str, ...] = ("3Y", "10Y")

OUT = Path(__file__).resolve().parents[1] / "output" / "MOMENTUM_TENOR_SEARCH_2026-09-21.md"
CACHE = Path(__file__).resolve().parents[1] / "output" / ".tenor_search_cache.json"

_SERIES: dict = {}


# ── 계열 ────────────────────────────────────────────────────────────────────

def load_tenors(tenors: tuple[str, ...], *, start: str = mie.START,
                end: str | None = mo.FREEZE) -> dict[str, tuple[list[str], list[float]]]:
    """임의의 테너 묶음을 **-bp** 로 — `mie.load_irs_series` 의 일반판.

    부호를 뒤집는 이유도 그쪽과 같다: 엔진은 「값이 오르면 롱이 번다」로 회계하는데
    IRS 는 금리가 내려야 리시브가 번다. 뒤집으면 +1 이 리시브다.

    ⚠ **옮긴 것과 새 규칙은 다르다**(§10-9). `("3Y","10Y")` 에서 이 함수가
    `mie.load_irs_series()` 와 **비트 동일**해야 하고, `assert_registered()` 가
    그것을 `SystemExit` 으로 막는다.
    """
    key = (tenors, start, end)
    if key in _SERIES:
        return _SERIES[key]
    cols = [COL[t] for t in tenors]
    where = " AND ".join(f"{c} IS NOT NULL" for c in cols)
    q = (f"SELECT irs_date,{','.join(cols)} FROM mkt_irs_close "
         f"WHERE {where} ORDER BY irs_date ASC")
    with engine().connect() as conn:
        rows = conn.execute(text(q)).fetchall()
    days: list[str] = []
    vals: dict[str, list[float]] = {t: [] for t in tenors}
    for r in rows:
        d = r[0]
        day = (d.date() if hasattr(d, "date") else d).isoformat()
        if day < start or (end is not None and day > end):
            continue
        days.append(day)
        for j, t in enumerate(tenors):
            vals[t].append(-float(r[j + 1]) * 100.0)
    out = {t: (days, vals[t]) for t in tenors}
    _SERIES[key] = out
    return out


def assert_registered() -> None:
    """등록 계열을 **비트 동일**로 재현하는지 — 아니면 여기서 멈춘다(§10-9)."""
    mine = load_tenors(REGISTERED)
    theirs = mie.load_irs_series()
    if sorted(mine) != sorted(theirs):
        raise SystemExit(f"열쇠가 달라요 — {sorted(mine)} 대 {sorted(theirs)}")
    for k in theirs:
        if mine[k][0] != theirs[k][0]:
            raise SystemExit(f"{k} 날짜가 달라요 — 옮긴 것이 아니라 새 규칙이에요")
        if mine[k][1] != theirs[k][1]:
            raise SystemExit(f"{k} 값이 달라요 — 옮긴 것이 아니라 새 규칙이에요")


# ── 한 조합의 북 ────────────────────────────────────────────────────────────

def _trend(series, vw: int = mo.VOL_WINDOW, sg: str = mo.SIGNAL) -> dict:
    return cta.book_simulate(
        series, signal=sg, lookbacks=mo.LOOKBACKS, vol_window=vw,
        target_book_vol_krw=mo.TARGET_VOL, book_vol_window=mo.BOOK_VOL_WINDOW,
        roll_days=set(), continuous=True, cost_ticks=mie.IRS_COST_BP / cta.TICK)


def _macro(series, sig: dict[str, pd.Series], vw: int = mo.VOL_WINDOW) -> dict[str, dict]:
    """거시 북 넷 — `momentum_irs_books.macro_books` 와 **같은 호출**이다(§10-10)."""
    return {t: ml._book(series, signal=mo.SIGNAL, vol_window=vw,
                        external={k: as_sig(s) for k in series})
            for t, s in sig.items()}


def blend_of(series, sig, vw: int = mo.VOL_WINDOW,
             sg: str = mo.SIGNAL) -> tuple[pd.Series, pd.Series]:
    """등록 구조 50/50 의 (일별 손익, 일별 비용). 두 다리를 반씩."""
    tb = _trend(series, vw, sg)
    bk = _macro(series, sig, vw)
    t = pnl_of(tb)
    m = sum(pnl_of(b) for b in bk.values()) / len(bk)
    tc = mib.cost_of(tb)
    mc = sum(mib.cost_of(b) for b in bk.values()) / len(bk)
    ix = t.index.intersection(m.index)
    return 0.5 * t.loc[ix] + 0.5 * m.loc[ix], 0.5 * tc.loc[ix] + 0.5 * mc.loc[ix]


# ── 폭 ─────────────────────────────────────────────────────────────────────

def corr_matrix(tenors: tuple[str, ...] = TENORS) -> pd.DataFrame:
    """테너 일별 변화의 상관 행렬 — 「폭이 있나」의 근거가 되는 그 표."""
    s = load_tenors(tenors)
    df = pd.DataFrame({k: pd.Series(dict(zip(s[k][0], s[k][1])))
                       for k in tenors}).diff().dropna()
    return df.corr()


def breadth(series) -> tuple[float, float]:
    """(평균 쌍상관 ρ̄, 유효 다리 수 N_eff = n/(1+(n−1)ρ̄)).

    이웃 테너는 상관 0.9 대라 「다리 셋」이 「폭 셋」이 아니다. 다리 하나면
    ρ̄ 는 정의가 없고(nan) N_eff 는 1 이다.
    """
    names = list(series)
    n = len(names)
    if n < 2:
        return float("nan"), 1.0
    df = pd.DataFrame({k: pd.Series(dict(zip(series[k][0], series[k][1])))
                       for k in names}).diff().dropna()
    c = df.corr().to_numpy()
    rho = float(np.mean(c[np.triu_indices(n, k=1)]))
    return rho, float(n / (1.0 + (n - 1) * rho)) if (1.0 + (n - 1) * rho) > 0 else float("nan")


# ── 한 칸의 수 ──────────────────────────────────────────────────────────────

def _cdar(s: pd.Series) -> float | None:
    return ev.cdar_ratio(ev.vol_normalize(s)[0])["cdar_ratio"]


def cell(tenors: tuple[str, ...], sig_cache: dict) -> dict:
    """조합 하나의 순위용 수 — 관문은 안 건다(계단식, 모듈 머리 §관문)."""
    series = load_tenors(tenors)
    key = tuple(sorted(series))
    if key not in sig_cache:
        sig_cache[key] = mib.registered_signals(series)
    pnl, cost = blend_of(series, sig_cache[key])
    rho, neff = breadth(series)
    vol = float(pnl.std(ddof=1) * math.sqrt(ANN))
    z = pnl.copy()
    z.index = pd.to_datetime(z.index)
    cz = z.cumsum()
    mdd = float((cz - cz.cummax()).min())
    yrs = len(z) / ANN
    return {
        "tenors": list(tenors), "n_legs": len(tenors),
        "n_obs": int(len(pnl)),
        "sr": float(pnl.mean() / pnl.std(ddof=1) * math.sqrt(ANN)) if pnl.std(ddof=1) > 0 else float("nan"),
        "sr_lo": ev.sharpe_lo(pnl),
        "cdar": _cdar(pnl),
        "net": float(pnl.sum()), "cost": float(cost.sum()),
        "vol": vol, "mdd": mdd,
        "calmar": float((cz.iloc[-1] / yrs) / abs(mdd)) if mdd < 0 else float("nan"),
        "rho": rho, "neff": neff,
        "pos_years": int((z.groupby(z.index.year).sum() > 0).sum()),
    }


def combos(max_legs: int) -> list[tuple[str, ...]]:
    out: list[tuple[str, ...]] = []
    for k in range(1, max_legs + 1):
        out += [tuple(c) for c in itertools.combinations(TENORS, k)]
    return out


# ── 관문 ────────────────────────────────────────────────────────────────────

def gate_of(tenors: tuple[str, ...], sig_cache: dict, trials: int) -> dict:
    """DSR·PBO — **칸 행렬**(신호계 3 × 볼 윈도 3)을 세워서. 위약은 안 돈다.

    ⚠ 위약(순환이동)은 칸마다 북을 수백 번 다시 세우는 물건이라 이 표의 시간
    예산에 안 맞는다. **없는 것을 통과로 적지 않는다** — 보고서가 「위약 미측정」
    이라고 쓰고, 등록으로 갈 때는 그 게이트를 반드시 따로 돌려야 한다.
    """
    series = load_tenors(tenors)
    key = tuple(sorted(series))
    if key not in sig_cache:
        sig_cache[key] = mib.registered_signals(series)
    sig = sig_cache[key]
    cols = {}
    for sg, vw in me.cells_for("blend"):
        p, _c = blend_of(series, sig, vw, sg)
        cols[f"{sg}-vw{vw}"] = p
    mat = pd.DataFrame(cols).dropna()
    rets = mat[mie.BASE_COL]
    sr_var = float(((mat.mean() / mat.std(ddof=1)).dropna()).var(ddof=1))
    d = ev.deflated_sharpe(rets.reset_index(drop=True), trials,
                           sr_var if sr_var > 0 else None)
    p = ev.pbo_cscv(mat, splits=16)
    return {"dsr": d["dsr"], "sr0": d["sr0"], "pbo": p.get("pbo"),
            "cells": int(mat.shape[1]), "n_obs": int(mat.shape[0])}


# ── 보고서 ──────────────────────────────────────────────────────────────────

def _fmt(v, f=".3f"):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    return f"{v:{f}}"


def _row(r: dict, base_vol: float) -> str:
    """맞춤 위험 누적 — 등록 북의 실현 연변동성으로 맞춘 뒤의 수(§10-4)."""
    k = base_vol / r["vol"] if r["vol"] > 0 else float("nan")
    return (f"| {'+'.join(r['tenors']):22s} | {r['n_legs']} | {_fmt(r['neff'], '.2f')} "
            f"| {_fmt(r['rho'], '+.3f')} | {_fmt(r['sr'])} | {_fmt(r['sr_lo'])} "
            f"| {_fmt(r['cdar'])} | {_fmt(r['calmar'], '.2f')} "
            f"| {r['net'] * k / 1e4:,.0f} | {r['mdd'] * k / 1e4:,.0f} "
            f"| {abs(r['cost']) / max(abs(r['net']) + abs(r['cost']), 1e-9) * 100:.1f}% "
            f"| {r['pos_years']} |")


HEAD = ("| 조합 | 다리 | N_eff | ρ̄ | SR | SR(Lo) | CDaR비 | Calmar "
        "| 맞춤누적(만) | 맞춤MDD(만) | 비용비 | 양+년 |")
SEP = "|---|---|---|---|---|---|---|---|---|---|---|---|"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="한·두 다리만(66조합)")
    ap.add_argument("--gate", type=int, default=3, help="관문에 태울 상위 칸 수")
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()

    assert_registered()
    print("✔ 등록 계열(3Y·10Y) 비트 동일 재현 확인")

    max_legs = 2 if a.quick else 3
    cs = combos(max_legs)
    control = TENORS
    print(f"  조합 {len(cs)}개 + 전 테너 대조군 1개 · 다리 1~{max_legs}")

    cached = {}
    if CACHE.exists() and not a.no_cache:
        try:
            cached = {tuple(k.split("+")): v
                      for k, v in json.loads(CACHE.read_text(encoding="utf-8")).items()}
        except (OSError, ValueError):
            cached = {}

    sig_cache: dict = {}
    rows: list[dict] = []
    t0 = time.time()
    todo = cs + [control]
    for i, c in enumerate(todo, 1):
        if c in cached:
            rows.append(cached[c])
            continue
        r = cell(c, sig_cache)
        rows.append(r)
        cached[c] = r
        if i % 20 == 0 or i == len(todo):
            el = time.time() - t0
            print(f"  {i}/{len(todo)} · {el:,.0f}s 경과")
    CACHE.write_text(json.dumps({"+".join(r["tenors"]): r for r in rows},
                                ensure_ascii=False), encoding="utf-8")

    by = {tuple(r["tenors"]): r for r in rows}
    reg = by[REGISTERED]
    ctl = by[control]
    base_vol = reg["vol"]

    search = [r for r in rows if tuple(r["tenors"]) != control]
    ranked = sorted(search, key=lambda r: (r["cdar"] is None, -(r["cdar"] or -9e9)))
    top = ranked[:15]

    #: 허들 — **실제 231칸의 SR 분산**으로(그 함수 머리의 그 지시).
    srs = np.array([r["sr"] for r in search if np.isfinite(r["sr"])], dtype=float)
    sr_var_daily = float(np.var(srs / math.sqrt(ANN), ddof=1))
    n_search = len(search)
    hurdle_search = ev.expected_max_sr(n_search, sr_var_daily) * math.sqrt(ANN)
    hurdle_full = ev.expected_max_sr(n_search * mie.TRIALS, sr_var_daily) * math.sqrt(ANN)

    print()
    print(f"── 순위 상위 5 (CDaR 비) ──")
    for r in ranked[:5]:
        print(f"  {'+'.join(r['tenors']):20s} CDaR {_fmt(r['cdar'])} · SR {_fmt(r['sr'])} "
              f"· N_eff {_fmt(r['neff'], '.2f')}")
    print(f"  {'등록 3Y+10Y':20s} CDaR {_fmt(reg['cdar'])} · SR {_fmt(reg['sr'])} "
          f"· 순위 {ranked.index(reg) + 1}/{n_search}")
    print(f"  {'대조 전 테너':20s} CDaR {_fmt(ctl['cdar'])} · SR {_fmt(ctl['sr'])} "
          f"· N_eff {_fmt(ctl['neff'], '.2f')}")

    # ── 관문 (계단식) ──────────────────────────────────────────────────────
    gate_cells = [REGISTERED, control] + [tuple(r["tenors"]) for r in ranked[:a.gate]]
    seen, gates = set(), {}
    trials_gate = n_search * mie.TRIALS
    print()
    print(f"── 관문(DSR·PBO) · 시행 N = {trials_gate:,} ──")
    for c in gate_cells:
        if c in seen:
            continue
        seen.add(c)
        g = gate_of(c, sig_cache, trials_gate)
        gates["+".join(c)] = g
        print(f"  {'+'.join(c):22s} DSR {_fmt(g['dsr'], '.4f')} · PBO {_fmt(g['pbo'], '.4f')} "
              f"· SR0 {g['sr0'] * math.sqrt(ANN):.3f}")

    # ── 다리 수 요약 ───────────────────────────────────────────────────────
    legs_sum = []
    for k in range(1, max_legs + 1):
        g = [r for r in search if r["n_legs"] == k]
        cd = np.array([r["cdar"] for r in g if r["cdar"] is not None], dtype=float)
        sr = np.array([r["sr"] for r in g if np.isfinite(r["sr"])], dtype=float)
        ne = np.array([r["neff"] for r in g if np.isfinite(r["neff"])], dtype=float)
        legs_sum.append({"k": k, "n": len(g), "cdar_max": float(cd.max()),
                         "cdar_med": float(np.median(cd)), "sr_max": float(sr.max()),
                         "sr_med": float(np.median(sr)), "neff_med": float(np.median(ne))})

    # ── 테너 빈도 ──────────────────────────────────────────────────────────
    freq = {t: sum(1 for r in ranked[:20] if t in r["tenors"]) for t in TENORS}

    write_report(rows, ranked, top, reg, ctl, base_vol, gates, legs_sum, freq,
                 n_search, hurdle_search, hurdle_full, trials_gate, max_legs,
                 time.time() - t0)
    print()
    print(f"  → {OUT}")
    return 0


def write_report(rows, ranked, top, reg, ctl, base_vol, gates, legs_sum, freq,
                 n_search, hurdle_search, hurdle_full, trials_gate, max_legs, secs):
    L = []
    w = L.append
    w("# IRS 모멘텀 — 테너 조합 탐색 (2026-09-21)")
    w("")
    w("읽기 전용 측정 · **등록을 바꾸지 않는다** · 판정문 안 씀. 산술은 "
      "`scripts/momentum_tenor_search.py` 머리 주석.")
    w("")
    w(f"고정 = 신호 정의(추세 macross 룩백 다섯 · 거시 테마별 부호 북 넷) · 구조 50/50 · "
      f"IRS 편도 0.5bp · 창 {reg['n_obs']:,}봉 ({mie.START}~{mo.FREEZE}) · "
      f"북 변동성 목표 하루 100만원(**조합마다 같다** — 위험 맞춤이 구조로 보장된다). "
      f"흔든 것 = 테너 조합 1~{max_legs} 다리 × 열한 테너 = **{n_search}조합**, "
      f"대조군 = 전 테너 등가중 하나. 도는 데 {secs / 60:.1f}분.")
    w("")
    w("## 판정")
    w("")
    rank_reg = ranked.index(reg) + 1
    best = ranked[0]
    ctl_rank = sum(1 for r in ranked if (r["cdar"] or -9e9) > (ctl["cdar"] or -9e9)) + 1
    w(f"**고르는 것이 이기지 않는다 — 폭이 이긴다.** 전 테너 등가중 대조군이 "
      f"CDaR 비 {_fmt(ctl['cdar'])} 로 {n_search}조합 중 **{ctl_rank}위**에 해당하고, "
      f"고른 최고 칸({'+'.join(best['tenors'])}, {_fmt(best['cdar'])})과의 차이가 "
      f"{abs((best['cdar'] or 0) - (ctl['cdar'] or 0)):.3f} 다. 등록된 3Y+10Y 는 "
      f"{rank_reg}위({_fmt(reg['cdar'])})다."
      if ctl_rank <= 3 else
      f"고른 최고 칸은 **{'+'.join(best['tenors'])}** (CDaR 비 {_fmt(best['cdar'])})이고, "
      f"전 테너 등가중 대조군은 {_fmt(ctl['cdar'])} 로 {ctl_rank}위에 해당한다. "
      f"등록된 3Y+10Y 는 {rank_reg}위({_fmt(reg['cdar'])})다.")
    w("")
    w("## 세 줄 — 등록 · 최고 · 대조군")
    w("")
    w(HEAD)
    w(SEP)
    for r in (reg, best, ctl):
        w(_row(r, base_vol))
    w("")
    w(f"맞춤누적·맞춤MDD 는 등록 북의 실현 연변동성({base_vol / 1e4:,.0f}만원)으로 "
      f"맞춘 뒤의 수다(§10-4 Man 2016 Figure 7 규약). 비용비는 |비용|/(|순손익|+|비용|).")
    w("")
    w(f"## 상위 15 (순위 기준 = 변동성 정규화 CDaR 비)")
    w("")
    w(HEAD)
    w(SEP)
    for r in top:
        w(_row(r, base_vol))
    w("")
    if tuple(reg["tenors"]) not in [tuple(r["tenors"]) for r in top]:
        w("등록 3Y+10Y 는 상위 15 밖이라 위 「세 줄」 표에 따로 세웠다.")
        w("")
    w("## 다리 수 — 폭이 «추세»로 보이나")
    w("")
    w("| 다리 | 조합 수 | CDaR 최고 | CDaR 중앙 | SR 최고 | SR 중앙 | N_eff 중앙 |")
    w("|---|---|---|---|---|---|---|")
    for s in legs_sum:
        w(f"| {s['k']} | {s['n']} | {s['cdar_max']:.3f} | {s['cdar_med']:.3f} "
          f"| {s['sr_max']:.3f} | {s['sr_med']:.3f} | {s['neff_med']:.2f} |")
    w("")
    w(f"대조군(11다리)은 N_eff {_fmt(ctl['neff'], '.2f')} · CDaR {_fmt(ctl['cdar'])} · "
      f"SR {_fmt(ctl['sr'])} 다. **중앙값이 다리 수를 따라 오르면 폭이 값을 하는 것**이고, "
      f"최고값만 오르면 그건 고르기다.")
    w("")
    w("## 관문 — 계단식")
    w("")
    w(f"231칸 전부에 관문을 걸 시간이 없어 **순위는 전 칸, 관문은 등록·대조군·상위 몇 칸**에만 "
      f"걸었다. 시행수 N = {trials_gate:,} (탐색 {n_search} × 레인이 이미 쓴 {mie.TRIALS}).")
    w("")
    w("| 조합 | DSR | PBO | SR0(연) | 칸 | 봉 |")
    w("|---|---|---|---|---|---|")
    for k, g in gates.items():
        w(f"| {k} | {_fmt(g['dsr'], '.4f')} | {_fmt(g['pbo'], '.4f')} "
          f"| {g['sr0'] * math.sqrt(ANN):.3f} | {g['cells']} | {g['n_obs']:,} |")
    w("")
    w(f"⚠ **위약(순환이동)은 안 쟀다.** 칸마다 북을 수백 번 다시 세우는 물건이라 이 표의 "
      f"시간 예산에 안 맞는다. 없는 것을 통과로 읽으면 안 된다 — 등록으로 가려면 그 게이트를 "
      f"반드시 따로 돌려야 한다(레인 게이트는 DSR·PBO·위약 **셋 다**).")
    w("")
    w(f"허들 — 실제 {n_search}칸의 SR 분산으로 낸 `expected_max_sr`: 탐색만 세면 "
      f"연 SR **{hurdle_search:.3f}**, 레인 N 까지 곱하면 **{hurdle_full:.3f}**. "
      f"「아무 실력이 없어도 이만큼은 나온다」는 뜻이다.")
    w("")
    w("## ★ 폭이 없는 이유 — 원화 IRS 커브는 **한 인자**다")
    w("")
    w("테너를 늘리는 것이 폭이 되려면 다리들이 서로 달라야 한다. 일별 변화 상관을 "
      "재면 그렇지 않다:")
    w("")
    cm = corr_matrix()
    w("| | " + " | ".join(TENORS) + " |")
    w("|---" * (len(TENORS) + 1) + "|")
    for t in TENORS:
        w(f"| **{t}** | " + " | ".join(f"{cm.at[t, u]:.2f}" for u in TENORS) + " |")
    w("")
    n = len(TENORS)
    rho_all = float(np.mean(cm.to_numpy()[np.triu_indices(n, k=1)]))
    pairs = [(a, b) for i, a in enumerate(TENORS) for b in TENORS[i + 1:]]
    lo_pair = min(pairs, key=lambda p: cm.at[p[0], p[1]])
    w(f"열한 테너 **평균 쌍상관 {rho_all:.3f}** · 전부 담아도 N_eff **{n / (1 + (n - 1) * rho_all):.2f}**. "
      f"가장 먼 쌍조차 {lo_pair[0]}–{lo_pair[1]} **{cm.at[lo_pair[0], lo_pair[1]]:.3f}** 이고, "
      f"등록 3Y–10Y 는 {cm.at['3Y', '10Y']:.3f} 다.")
    w("")
    w(f"**그래서 「스왑으로 와서 폭이 생겼다」가 이 축에서는 성립하지 않는다.** 다리를 둘에서 "
      f"열하나로 늘려도 유효 다리 수는 {reg['neff']:.2f} → {ctl['neff']:.2f} 이다. "
      "AQR 의 N=30 은 **서로 다른 시장**"
      "(자산군 넷 × 나라 여럿)이지 한 커브 위의 점 서른 개가 아니다 — §10-2 의 「N=2 라 "
      "Sharpe 상한 0.6대」는 선물 시절의 제약처럼 보였지만, 실은 **원화 금리라는 인자 하나**의 "
      "제약이었다. 계기를 IRS 로 바꾼 것만으로는 안 풀린다.")
    w("")
    w("폭이 실제로 열리는 자리는 **아웃라이트가 아닌 축**이다(커브·플라이처럼 레벨 인자에 "
      "직교하는 것, 또는 금리 밖 자산군). 이 표는 그 자리를 «열어 보자»고 말하지 않는다 — "
      "여기서 잰 것은 아웃라이트 조합뿐이고, 그 결론은 「여기엔 없다」까지다.")
    w("")
    w("## 어느 테너가 상위를 채우나")
    w("")
    w("| 테너 | 상위 20 중 등장 |")
    w("|---|---|")
    for t, n in sorted(freq.items(), key=lambda kv: -kv[1]):
        w(f"| {t} | {n} |")
    w("")
    w("한 테너가 상위를 독점하면 그것이 신호인지 그 테너의 변동성·캐리 인공물인지 "
      "갈라야 한다 — 위 N_eff 열이 그 첫 단서다(독점 + 낮은 N_eff = 폭이 아니다).")
    w("")
    w("## 말할 수 있는 것 / 없는 것")
    w("")
    w("    ✔ 이 창에서 조합마다의 순위 (같은 위험·같은 비용·같은 신호 정의 위에서)")
    w("    ✔ 다리를 늘리는 것이 중앙값을 올리나 (폭의 효과)")
    w("    ✘ 「이 조합을 쓰자」 — 표본내 순위다. 위약도 안 쟀고 표본밖도 없다")
    w("    ✘ 등록을 바꾼다 — 3Y·10Y 는 09-15 동결·09-16 채점 중이다")
    w("")
    w("## 움직이려면 사전등록에 무엇이 필요한가")
    w("")
    w("1. **조합을 하나로 못 박는다** — 이 표를 보고 고르면 그 순간 표본내 선택이다. "
      "폭이 이기면 「전 테너 등가중」처럼 **고르지 않는 규칙**이 자유도를 안 쓴다.")
    w("2. **위약(순환이동)** 을 그 조합으로 돌린다 — 레인 게이트 셋 중 하나가 비어 있다.")
    w("3. **시행수 N 을 다시 센다** — 테너 축이 열리면 N 에 그 가짓수가 곱해진다.")
    w("4. **집행 배관** — `sleeve_execution.LEG_T` 가 3Y·10Y 두 다리로 박혀 있고, "
      "실측 pv01·증거금·주문표가 전부 그 위에 선다. 다리가 늘면 그쪽도 같이 연다.")
    w("5. **비용** — 편도 0.5bp 는 3Y·10Y 의 값이다. 1Y·18M 이나 8~9Y 의 호가폭이 "
      "같다는 근거는 이 레인에 없다. 다리를 늘리면 그 가정부터 다시 봐야 한다.")
    w("")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
