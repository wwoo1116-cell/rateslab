# -*- coding: utf-8 -*-
r"""등록 50/50 슬리브의 사전등록 수 — 제1안 [OWNER 2026-09-15].

    python -m scripts.sleeve_prereg_5050

`sleeve_prereg.py` 가 **추세 단독** 슬리브에 대해 낸 W1·W4·상관 셋을 **등록
구조(추세·거시 50/50, 원논문 정의 테마, 경기순환 OECD 실현치)** 위에서 다시 낸다.
같은 창에서 추세 단독도 나란히 내어 두 슬리브가 한 자로 견줘지게 한다.

## 창 — 여기서 못 박는다

09-11 초안은 1,640봉과 1,646봉을 같이 적었다. 1,640 은 `hedge_test.aligned()` 가
`momentum_irs_evaluate.matrices()` 를 쓰는 탓에 **IRS 달력을 선물 거래일과
교집합**한 것이고, 1,646 은 `momentum_irs_legs.legs()` 의 IRS 달력 그대로다.
슬리브는 IRS 를 거래하므로 선물 달력이 낄 이유가 없다. **이 문서의 창은
IRS 고시 달력 ∩ 평균회귀 장부 달력(1,646봉)** 이다. 추세 단독의 09-11 수
(ΔCalmar +0.309 · P 0.040)가 여기서 +0.307 · P 0.048 로 옮겨 오는 것은 그 6봉이다.

## `--structure books` (2026-09-15 밤)

거시 다리를 논문 구조(테마별 부호 북 넷 · 위험선호 확장 평균, `momentum_irs_books`)로 세운
판. 50/50 의 DV01 은 추세 북과 «네 북 평균»의 반씩 합이다. 산출은 `_books.json`.

## 50/50 의 포지션

`legs()` 의 50/50 손익은 두 북 손익의 반씩 합이므로 DV01 도 두 북 포지션의
반씩 합이다(엔진 회계 `pos/100 × Δ(−bp)` 가 선형). 비용은 각 북이 제 회전을
따로 무는 셈이라 **물리적으로 한 북으로 세우면 이보다 덜 든다** — 보수적이다.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import momentum as mo                                  # noqa: E402
from scripts import crs_evaluate as ce                          # noqa: E402
from scripts import hedge_test as ht                            # noqa: E402
from scripts import macro_paper_fix as mp                       # noqa: E402
from scripts import momentum_evaluate as me                     # noqa: E402
from scripts import momentum_irs_evaluate as mie                # noqa: E402
from scripts import momentum_irs_legs as ml                     # noqa: E402
from scripts import sleeve_margin as sg                         # noqa: E402

ANN = 252
RATE = 0.05          # [OWNER 2026-09-11] 스왑 증거금률
W = 0.25             # 등록 후보 — 09-11 초안 W1 그대로
W_UP = 0.40          # W2 의 유일한 상향 후보
ROLL = 250


def iso(s: pd.Series) -> pd.Series:
    return pd.Series(s.values.astype(float), index=[str(t)[:10] for t in s.index])


def _sized(m: np.ndarray, t: np.ndarray, w: float):
    s_mix = float(((1 - w) * m + w * t).std(ddof=1) * math.sqrt(ANN))
    return (1 - w) / s_mix, w / s_mix, s_mix


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--structure", choices=("composite", "books"), default="composite",
                    help="composite = 09-08 등록 구조(부호 평균 → 북 하나) · books = 논문 구조(테마별 부호 북 넷 · 위험선호 확장 평균)")
    a = ap.parse_args()
    # ── 슬리브 둘 ────────────────────────────────────────────────────────
    series = mie.load_irs_series()
    _s, _r, macro = me._inputs()
    if macro is None:
        raise SystemExit("매크로 신호가 없어서 50/50 을 못 세워요")
    t_book = ml._book(series, signal=mo.SIGNAL, vol_window=mo.VOL_WINDOW)
    if a.structure == "composite":
        macro = dict(macro)
        macro["macro_sign"] = mp.as_signal(mp.themes(mp._load(), paper=True, cycle="oecd"))
        L = ml.legs(series, macro)
        ext = {k: macro["macro_sign"] for k in series}
        m_books = {"composite": ml._book(series, signal=mo.SIGNAL, vol_window=mo.VOL_WINDOW, external=ext)}
    else:
        from scripts import momentum_irs_books as mb
        sig = mb.registered_signals(series)      # ★IRS 달력 이월 포함 — 한 자리
        L = mb.legs(series, sig)
        m_books = mb.macro_books(series, sig, mo.VOL_WINDOW)
    rets = {leg: iso(L[leg]["rets"]) for leg in ("trend", "macro", "blend")}
    for b in m_books.values():
        assert list(t_book["dates"]) == list(b["dates"])
    nb = len(m_books)
    dv = {}
    for k in t_book["pos"]:
        pt = np.asarray(t_book["pos"][k], dtype=float) / 100.0
        pm = sum(np.asarray(b["pos"][k], dtype=float) for b in m_books.values()) / nb / 100.0
        dv[k] = {"trend": pt, "blend": 0.5 * (pt + pm)}
    dates = [str(x)[:10] for x in t_book["dates"]]
    pv = sg.pv01_per_100m()
    face = {}
    for name in ("trend", "blend"):
        face[name] = pd.Series(sum(np.abs(dv[k][name]) / pv[k] * 1e8 for k in dv),
                               index=dates)
    vol_full = {name: float(rets[name].std(ddof=1) * math.sqrt(ANN))
                for name in ("trend", "blend")}

    # ── 평균회귀 상한판 ─────────────────────────────────────────────────
    mb = ce._lane()
    net, facts = ce.net_returns(mb, ce.REGISTERED_LOT_UK, "bound")
    P, Lz, Z, meta = mb.load()
    _d, used, _dv, _e, _b = mb.simulate(P, Lz, Z, meta, ce.REGISTERED_LOT_UK)
    mr = ht.mr_returns()
    mr_vol_krw = float(net.std(ddof=1) * math.sqrt(ANN) * mb.CAP)
    u = pd.Series(used.to_numpy(dtype=float), index=[str(x)[:10] for x in used.index])

    idx = sorted(set(mr.index) & set(rets["trend"].index) & set(rets["blend"].index))
    m = ht.unit_vol(mr.loc[idx]).to_numpy()
    base_cal, base_mdd = ht._card(m)
    out: dict = {"window": [idx[0], idx[-1], len(idx)], "mr": {"cal": base_cal, "mdd": base_mdd},
                 "sleeves": {}}
    print()
    print(f"── [{a.structure}] 창 {idx[0]}~{idx[-1]} · {len(idx):,}봉 (IRS 달력 ∩ MR 달력) · "
          f"MR 단독 Calmar {base_cal:.3f} MDD {base_mdd:.3f} ──")
    print(f"  슬리브 실현 연변동성(전체 창)  추세 {vol_full['trend']/1e4:,.0f}만 · 50/50 {vol_full['blend']/1e4:,.0f}만")

    for name, label in (("blend", "50/50 (등록 구조)"), ("trend", "추세 단독 (대조)")):
        t = ht.unit_vol(rets[name].loc[idx]).to_numpy()
        rho = float(np.corrcoef(m, t)[0, 1])
        rows = {w: ht._card((1 - w) * m + w * t) for w in ht.WEIGHTS}
        ci = ht._paired_ci(m, t, W)
        ci_up = ht._paired_ci(m, t, W_UP)
        k_mr, k_tr, s_mix = _sized(m, t, W)
        print()
        print(f"[{label}]  상관 {rho:+.3f}")
        print(f"  {'w':>5s} {'Calmar':>8s} {'ΔCalmar':>9s} {'MDD':>8s} {'ΔMDD':>8s}")
        for w, (cal, md) in rows.items():
            print(f"  {w:5.2f} {cal:8.3f} {cal-base_cal:+9.3f} {md:8.3f} {md-base_mdd:+8.3f}")
        print(f"  w={W}  ΔCalmar {rows[W][0]-base_cal:+.3f} · 90% [{ci['cal'][0]:+.3f}, {ci['cal'][1]:+.3f}] "
              f"· P(Δ≤0) {ci['p_cal']:.3f} · ΔMDD {rows[W][1]-base_mdd:+.3f} · P(ΔMDD≥0) {ci['p_mdd']:.3f}")
        print(f"  w={W_UP} ΔCalmar {rows[W_UP][0]-base_cal:+.3f} · 90% [{ci_up['cal'][0]:+.3f}, {ci_up['cal'][1]:+.3f}] "
              f"· P(Δ≤0) {ci_up['p_cal']:.3f}")
        print(f"  총위험 고정 w={W}: σ_mix {s_mix:.3f} · MR 배수 {k_mr:.3f} · 슬리브 배수 {k_tr:.3f} "
              f"· 슬리브 연변동성 {k_tr*mr_vol_krw/1e8:.3f}억 = 등록북 대비 {k_tr*mr_vol_krw/vol_full[name]:.2f}배")

        # W4 — 증거금이 막는 날의 대가
        mult = (k_tr * mr_vol_krw) / vol_full[name]
        ix = [d for d in idx if d in face[name].index and d in u.index]
        m_c = ht.unit_vol(mr.loc[idx]).loc[ix].to_numpy()
        t_c = ht.unit_vol(rets[name].loc[idx]).loc[ix].to_numpy()
        want = face[name].loc[ix].to_numpy() * mult * RATE
        head = np.maximum(mb.CAP - u.loc[ix].to_numpy() * mb.CAP * k_mr, 0.0)
        scale = np.where(want > 0, np.minimum(want, head) / np.maximum(want, 1e-9), 1.0)
        scale = np.clip(scale, 0.0, 1.0)
        hit = int((scale < 0.999).sum())
        lag = np.concatenate(([1.0], scale[:-1]))
        base = (1 - W) / s_mix * m_c + W / s_mix * t_c
        capped = (1 - W) / s_mix * m_c + W / s_mix * t_c * lag
        b_cal, b_mdd = ht._card(base)
        c_cal, c_mdd = ht._card(capped)
        b_ann, c_ann = base.mean() * ANN, capped.mean() * ANN
        fmax = float(face[name].loc[ix].max() * mult)
        fmean = float(face[name].loc[ix].mean() * mult)
        print(f"  W4 증거금(율 {RATE:.0%}): 액면 평균 {fmean/1e8:,.1f}억 · 최대 {fmax/1e8:,.1f}억 "
              f"· 소요 평균 {fmean*RATE/1e8:.2f}억 · 최대 {fmax*RATE/1e8:.2f}억")
        print(f"     줄인 날 {hit:,}일 ({hit/len(ix):.1%})"
              + (f" · 배율 평균 {scale[scale<0.999].mean():.3f} · 최저 {scale[scale<0.999].min():.3f}" if hit else ""))
        print(f"     상한 무시  연수익 {b_ann:.4f} Calmar {b_cal:.3f} MDD {b_mdd:.3f}")
        print(f"     상한 지킴  연수익 {c_ann:.4f} Calmar {c_cal:.3f} MDD {c_mdd:.3f}")
        print(f"     대가       연수익 {c_ann-b_ann:+.4f} ({abs((c_ann-b_ann)/b_ann):.2%}) · Calmar {c_cal-b_cal:+.3f} · MDD {c_mdd-b_mdd:+.3f}")

        # 상관 안정성
        r = pd.Series(m).rolling(ROLL).corr(pd.Series(t)).dropna()
        print(f"  롤링 {ROLL}봉 상관: 평균 {r.mean():+.3f} · 범위 {r.min():+.3f} ~ {r.max():+.3f} · "
              f"+0.3 초과 창 {int((r > 0.3).sum()):,}/{len(r):,} · 5/95백분위 {np.percentile(r,5):+.3f}/{np.percentile(r,95):+.3f}")

        out["sleeves"][name] = {
            "rho": rho, "rows": {str(w): list(v) for w, v in rows.items()},
            "ci_w": ci, "ci_up": ci_up, "s_mix": s_mix, "k_mr": k_mr, "k_tr": k_tr,
            "vol_full": vol_full[name], "mult": mult,
            "w4": {"n": len(ix), "hit": hit, "face_mean": fmean, "face_max": fmax,
                   "ann_base": b_ann, "ann_capped": c_ann, "cal_base": b_cal, "cal_capped": c_cal,
                   "mdd_base": b_mdd, "mdd_capped": c_mdd},
            "roll": {"mean": float(r.mean()), "min": float(r.min()), "max": float(r.max()),
                     "over": int((r > 0.3).sum()), "n": int(len(r))},
        }

    p = Path(__file__).resolve().parents[1] / "output" / (
        "sleeve_prereg_5050.json" if a.structure == "composite" else "sleeve_prereg_5050_books.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(f"\n  → {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
