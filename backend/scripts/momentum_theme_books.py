# -*- coding: utf-8 -*-
r"""거시 다리의 «구조»를 2×2 로 가른다 — 합성 하나 대 북 넷 × 부호 대 연속값 [2026-09-15].

    python -m scripts.momentum_theme_books            # 경기순환 OECD(등록 입력)
    python -m scripts.momentum_theme_books --cycle bok

## 왜

등록 북의 거시 다리는 **네 테마 부호의 평균 하나**를 외부 신호로 북 한 개에 넣는다.
원논문(Brooks 2017)은 **테마마다 북을 따로** 세워 같은 위험으로 맞춘 뒤 등가중한다.
09-08 탐색이 돌린 「매크로 z」는 네 z 의 평균을 북 하나에 넣은 것이라 논문 구조가
아니었다(`RESULT_cta_macro.md` ③). 그래서 두 축을 갈라 넷을 다 세운다.

    합성·부호   등록 북 (macro_sign 평균, 북 하나)
    합성·연속   09-08 탐색의 「매크로 z」 (zcap 평균, 북 하나)
    북넷·부호   테마별 부호 → 북 넷 → 등가중   ← 논문 부록 C 의 directional 구조가 이것이다
    북넷·연속   테마별 zcap → 북 넷 → 등가중   (연속값·순위 표준화는 논문에서 횡단면 롱숏에만 쓴다)
    북넷·부호·위험선호평균제거   위험선호 부호를 확장 평균 대비로 (부록 C 의 그 문장)
    북넷·부호·논문충실         위 + 경기순환을 성장 북·물가 북으로 갈라 평균 (각주 12)

각 북은 같은 배관(`momentum_irs_legs._book`)이고 북 변동성 목표 100만원/일이라, 북
넷의 등가중은 곧 **테마 간 위험 등배분**이다. 50/50 은 등록 규약대로 추세와 거시의
일별 손익 0.5:0.5 (위험 맞춤은 표에서 따로 낸다).

## ⚠ 지위

이 표는 **표본내 탐색**이다. 09-08 등록서가 「부호 평균」으로 얼려 있고, 여기서 무엇이
좋아 보이든 등록 북을 바꾸는 근거가 되지 않는다. 쓰려면 새 사전등록이다.
연속값(zcap)은 확장 표준편차 120일 워밍업이 붙어 창이 뒤로 밀린다 — 네 변형을
**같은 창**에서 잰다.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ctabacktest as cta                              # noqa: E402
from app import momentum as mo                                  # noqa: E402
from evaluation import metrics as ev, randomization as rz       # noqa: E402
from scripts import macro_paper_fix as mp                       # noqa: E402
from scripts import momentum_evaluate as me                     # noqa: E402
from scripts import momentum_irs_evaluate as mie                # noqa: E402
from scripts import momentum_irs_legs as ml                     # noqa: E402

ANN = 252
THEMES = ("cycle", "policy", "trade", "risk")
Z_CAP = 2.0


def zcap(x: pd.Series, cap: float = Z_CAP) -> pd.Series:
    """`build_themes.zcap` 과 같다 — 확장표준편차(120일)로 나눠 ±cap 포화, /cap."""
    sd = x.expanding(min_periods=120).std()
    return (x / sd.replace(0.0, np.nan)).clip(-cap, cap) / cap


def as_sig(s: pd.Series) -> dict[str, float]:
    s = s.dropna()
    return {d.strftime("%Y-%m-%d"): float(v) for d, v in s.items()}


def pnl_of(book: dict) -> pd.Series:
    return pd.Series([p["dailyPnl"] for p in book["points"]],
                     index=[p["t"] for p in book["points"]], dtype=float)


def sr(x) -> float:
    x = np.asarray(x, dtype=float)
    return float(x.mean() / x.std(ddof=1) * math.sqrt(ANN)) if x.std(ddof=1) > 0 else float("nan")


def placebo_multi(pl: dict, pl_g: dict, books: list[tuple[float, dict]], mask: np.ndarray, lo: int) -> dict:
    """북 여럿의 가중합에 순환이동 위약 — 전부 **같은 k** 로 민다(`placebo_for` 의 blend 와 같은 셈)."""
    shifts = list(range(lo, pl["n"] - lo, rz.SHIFT_STEP))

    def pnl(which, posl):
        return sum(w * rz.repnl(which, p) for w, p in posl)

    def one(which):
        real = rz._sr(pnl(which, books)[mask])
        a = np.array([rz._sr(pnl(which, [(w, rz.shifted(p, k, sign_only=True)) for w, p in books])[mask])
                      for k in shifts])
        beat = int((a >= real).sum())
        return (beat + 1) / (len(a) + 1), real, beat, a

    p, real, beat, a = one(pl)
    pg, real_g, beat_g, g = one(pl_g)
    return {"p": p, "n_shifts": len(a), "real_sr": real, "beat": beat,
            "placebo_median": float(np.median(a)), "placebo_p95": float(np.percentile(a, 95)),
            "p_gross": pg, "real_sr_gross": real_g, "beat_gross": beat_g,
            "placebo_gross_median": float(np.median(g)), "placebo_gross_p95": float(np.percentile(g, 95)),
            "sign_only": True, "why": None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycle", choices=("oecd", "bok"), default="oecd")
    a = ap.parse_args()
    t0 = time.time()

    series = mie.load_irs_series()
    th = mp.themes(mp._load(), paper=True, cycle=a.cycle)
    raw = th[[f"{t}_raw" for t in THEMES]].rename(columns={f"{t}_raw": t for t in THEMES})
    full = raw.notna().all(axis=1)

    sign = np.sign(raw).where(full)
    zed = pd.DataFrame({t: zcap(raw[t]) for t in THEMES}).where(full)

    #: 논문 부록 B·C 대조(2026-09-15)로 드러난 두 자리를 논문대로 되돌린 계열.
    #:  ① 위험선호 — "since one-year equity returns are positive on average, I compare to an
    #:     expanding mean" : 부호를 0 이 아니라 **확장 평균** 대비로 낸다.
    #:  ② 경기순환 — 성장·물가를 신호에서 평균한 뒤 부호를 내는 것이 아니라(sign(mean)),
    #:     논문 각주 12 처럼 **성장 북과 물가 북을 따로 세워 평균**한다(mean of books).
    #:     수출(EX)·물가(CP) 가속을 따로 꺼내 쓴다 — 성장률 자리에 수출이 서 있는 것은 그대로다.
    eq_ex = -raw["risk"]                                   # 주식 초과수익 1년 (부호 되돌림)
    risk_dm = -(eq_ex - eq_ex.expanding(min_periods=250).mean())
    pit = pd.read_csv(mp.PROJECTS / "data" / "krw-macro-vintage" / "out" / "macro_pit_monthly.csv",
                      encoding="utf-8-sig", parse_dates=["available_from"])
    comp = {}
    for m_ in ("EX", "CP"):
        w_ = pit[pit["measure"] == m_].dropna(subset=["dg_1y"]).set_index("available_from")["dg_1y"].sort_index()
        comp[m_] = -w_.reindex(raw.index, method="ffill")   # 가속 → 국채 숏이라 부호 −
    sign_dm = sign.copy(); sign_dm["risk"] = np.sign(risk_dm).where(full)

    sigs = {
        "합성·부호": {"composite": (1.0, sign.mean(axis=1))},
        "합성·연속": {"composite": (1.0, zed.mean(axis=1))},
        "북넷·부호": {t: (1.0, sign[t]) for t in THEMES},
        "북넷·연속": {t: (1.0, zed[t]) for t in THEMES},
        "북넷·부호·위험선호평균제거": {t: (1.0, sign_dm[t]) for t in THEMES},
        "북넷·부호·논문충실": {"growth": (0.5, np.sign(comp["EX"]).where(full)),
                          "inflation": (0.5, np.sign(comp["CP"]).where(full)),
                          "policy": (1.0, sign["policy"]), "trade": (1.0, sign["trade"]),
                          "risk": (1.0, sign_dm["risk"])},
    }
    # 같은 창 — 네 변형 중 가장 늦게 서는 날부터 FREEZE 까지
    start = max(min(as_sig(s_.dropna())) for v in sigs.values() for _w, s_ in v.values())
    print(f"공통 창 {start} ~ {mo.FREEZE} (연속판 워밍업 때문에 등록 창 2017-01-06 보다 늦다)")

    def cut(s: pd.Series) -> pd.Series:
        return s[(s.index >= start) & (s.index <= mo.FREEZE)]

    # 추세 다리 (칸 셋)
    trend_cells = {vw: cut(pnl_of(ml._book(series, signal=mo.SIGNAL, vol_window=vw)))
                   for vw in me.VOL_WINDOWS}
    trend = trend_cells[mo.VOL_WINDOW]
    t_book = ml._book(series, signal=mo.SIGNAL, vol_window=mo.VOL_WINDOW)
    dates = t_book["dates"]
    price = {k: dict(zip(*series[k])) for k in series}
    tk = mie.IRS_COST_BP / cta.TICK
    pl = rz.plumbing(dates, price, set(), tk, cta.TICK)
    pl_g = rz.plumbing(dates, price, set(), 0.0, cta.TICK)
    lo = max(mo.LOOKBACKS)
    keep = set(trend.index)
    mask = np.array([d in keep for d in dates])
    print(f"추세 다리 {len(trend):,}봉 · SR {sr(trend):.3f}  ({time.time()-t0:,.0f}s)", flush=True)

    out: dict = {"cycle": a.cycle, "window": [start, mo.FREEZE, len(trend)],
                 "trend": {"sr": sr(trend), "vol": float(trend.std(ddof=1) * math.sqrt(ANN))},
                 "variants": {}}
    rows = []
    for name, parts in sigs.items():
        books = {}
        for vw in me.VOL_WINDOWS:
            books[vw] = {}
            for t, (_w, s_) in parts.items():
                ext = {k: as_sig(s_) for k in series}
                books[vw][t] = ml._book(series, signal=mo.SIGNAL, vol_window=vw, external=ext)
        n = len(parts)
        wsum = sum(w_ for w_, _s in parts.values())
        wt = {t: w_ / wsum for t, (w_, _s) in parts.items()}
        macro_cells = {vw: cut(sum(wt[t] * pnl_of(b) for t, b in books[vw].items())) for vw in me.VOL_WINDOWS}
        macro = macro_cells[mo.VOL_WINDOW]
        ix = trend.index.intersection(macro.index)
        blend_cells = {vw: 0.5 * trend_cells[vw].loc[ix] + 0.5 * macro_cells[vw].loc[ix] for vw in me.VOL_WINDOWS}
        blend = blend_cells[mo.VOL_WINDOW]
        # 신호의 0 비중 (합성은 신호 자체, 북넷은 네 북 포지션이 전부 0 인 날)
        if n == 1:
            s0 = cut(parts["composite"][1].dropna().rename(lambda d: d.strftime("%Y-%m-%d")))
            zero = float((s0 == 0).mean())
        else:
            pos_sum = sum(np.abs(np.asarray(b["pos"][k], dtype=float))
                          for b in books[mo.VOL_WINDOW].values() for k in b["pos"])
            zero = float((pos_sum[mask] == 0).mean())
        rho = float(np.corrcoef(trend.loc[ix], macro.loc[ix])[0, 1])
        per_theme = ({t: sr(cut(pnl_of(b))) for t, b in books[mo.VOL_WINDOW].items()} if n > 1 else {})

        #: 논문식 — 거시 다리를 추세 다리의 변동성으로 맞춘 뒤 0.5:0.5. 등록 규약(일별 손익 반반)은
        #: 북넷에서 거시 몫이 위험 기준 30% 안팎으로 내려가므로 이 판을 나란히 둔다.
        k_rp = {vw: float(trend_cells[vw].loc[ix].std(ddof=1) / macro_cells[vw].loc[ix].std(ddof=1))
                for vw in me.VOL_WINDOWS}
        rp_cells = {vw: 0.5 * trend_cells[vw].loc[ix] + 0.5 * k_rp[vw] * macro_cells[vw].loc[ix]
                    for vw in me.VOL_WINDOWS}
        rp = rp_cells[mo.VOL_WINDOW]
        res = {"k_rp": k_rp[mo.VOL_WINDOW]}
        for leg, cells, series_ in (("macro", macro_cells, macro), ("blend", blend_cells, blend),
                                    ("blend_rp", rp_cells, rp)):
            mat = pd.DataFrame({f"{mo.SIGNAL}-vw{vw}": c for vw, c in cells.items()}).dropna()
            sr_var = float(((mat.mean() / mat.std(ddof=1)).dropna()).var(ddof=1))
            if leg == "macro":
                wts = [(wt[t], b["pos"]) for t, b in books[mo.VOL_WINDOW].items()]
            else:
                km = 1.0 if leg == "blend" else k_rp[mo.VOL_WINDOW]
                wts = [(0.5, t_book["pos"])] + [(0.5 * km * wt[t], b["pos"]) for t, b in books[mo.VOL_WINDOW].items()]
            pb = placebo_multi(pl, pl_g, wts, mask, lo)
            e = ev.evaluate(mat[f"{mo.SIGNAL}-vw{mo.VOL_WINDOW}"].reset_index(drop=True),
                            trials=mie.TRIALS, is_oos_splits=16, configs=mat,
                            sr_var=sr_var if sr_var > 0 else None,
                            strategy_id=f"explore-{name}-{leg}", cost_bp_roundtrip=mie.IRS_COST_BP * 2,
                            placebo=pb, assumptions=["표본내 탐색 — 판정문에 쓰지 않는다"])
            g = e["gate"]
            res[leg] = {"sr": sr(series_), "vol": float(series_.std(ddof=1) * math.sqrt(ANN)),
                        "dsr": g["dsr"], "pbo": g["pbo"], "p": g["placebo_p"], "p_gross": g["placebo_p_gross"],
                        "pass": bool(g["overall_pass"]), "cdar": e["ranking"].get("cdar_ratio")}
        # 위험 맞춤(추세 변동성) 후 50/50 누적·낙폭·Calmar
        for key, bl in (("blend_matched", blend), ("blend_rp_matched", rp)):
            z = bl * (trend.std(ddof=1) / bl.std(ddof=1))
            cz = z.cumsum(); mdz = float((cz - cz.cummax()).min()); yrs = len(z) / ANN
            res[key] = {"cum": float(cz.iloc[-1]), "mdd": mdz, "calmar": float((cz.iloc[-1] / yrs) / abs(mdz))}
        res["zero_share"] = zero; res["rho_trend"] = rho; res["per_theme_sr"] = per_theme
        out["variants"][name] = res
        rows.append((name, res))
        print(f"  [{name}] 끝  ({time.time()-t0:,.0f}s)", flush=True)

    tz = trend * 1.0; ct = tz.cumsum(); mdt = float((ct - ct.cummax()).min())
    print()
    print(f"── 거시 다리의 구조 2×2 · 경기순환 {a.cycle} · 창 {start}~{mo.FREEZE} {len(trend):,}봉 ──")
    print(f"  추세 단독: SR {sr(trend):.3f} · 누적 {ct.iloc[-1]/1e4:,.0f}만 · MDD {mdt/1e4:,.0f}만 · Calmar {(ct.iloc[-1]/(len(trend)/ANN))/abs(mdt):.2f}")
    print()
    print(f"  {'변형':10s} {'거시SR':>7s} {'거시vol':>8s} {'0비중':>6s} {'추세ρ':>6s} {'거시위약후/전':>14s} | "
          f"{'50/50SR':>8s} {'DSR':>7s} {'PBO':>7s} {'위약후/전':>14s} {'판정':>4s} | {'맞춤누적':>8s} {'맞춤MDD':>8s} {'Calmar':>6s}")
    for name, r in rows:
        m, b, bm = r["macro"], r["blend"], r["blend_matched"]
        print(f"  {name:14s} {m['sr']:7.3f} {m['vol']/1e4:7,.0f}만 {r['zero_share']:6.3f} {r['rho_trend']:+6.3f} "
              f"{m['p']:6.4f}/{m['p_gross']:6.4f} | {b['sr']:8.3f} {b['dsr']:7.4f} {b['pbo']:7.4f} "
              f"{b['p']:6.4f}/{b['p_gross']:6.4f} {'통과' if b['pass'] else '미통과':>4s} | "
              f"{bm['cum']/1e4:8,.0f} {bm['mdd']/1e4:8,.0f} {bm['calmar']:6.2f}")
    print()
    print("  논문식 — 거시 다리를 추세 변동성으로 맞춘 뒤 0.5:0.5 (k = σ추세/σ거시)")
    print(f"  {'변형':10s} {'k':>5s} | {'50/50SR':>8s} {'DSR':>7s} {'PBO':>7s} {'위약후/전':>14s} {'판정':>4s} | {'맞춤누적':>8s} {'맞춤MDD':>8s} {'Calmar':>6s}")
    for name, r in rows:
        b, bm = r["blend_rp"], r["blend_rp_matched"]
        print(f"  {name:14s} {r['k_rp']:5.2f} | {b['sr']:8.3f} {b['dsr']:7.4f} {b['pbo']:7.4f} "
              f"{b['p']:6.4f}/{b['p_gross']:6.4f} {'통과' if b['pass'] else '미통과':>4s} | "
              f"{bm['cum']/1e4:8,.0f} {bm['mdd']/1e4:8,.0f} {bm['calmar']:6.2f}")
    print()
    for name, r in rows:
        if r["per_theme_sr"]:
            print(f"  {name} 테마별 북 SR(vw60): " + " · ".join(f"{t} {v:.3f}" for t, v in r["per_theme_sr"].items()))

    p = Path(__file__).resolve().parents[1] / "output" / f"momentum_theme_books_{a.cycle}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(f"\n  → {p}  ({time.time()-t0:,.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
