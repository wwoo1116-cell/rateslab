# -*- coding: utf-8 -*-
r"""IRS 로 옮길 때 **거시 다리가 안 따라왔다** — 세 다리를 같은 게이트에 태운다.

    python -m scripts.momentum_irs_legs

## 왜 이 자리가 필요한가

그 레인의 **등록된 북은 추세·거시 50/50** 이다(사전등록 2026-09-08 동결). 그런데
`momentum_irs_evaluate.irs_points()` 는 `external_signals` 를 안 넘긴다 — 즉 IRS 로
계기를 옮기면서 **추세 다리만 건너왔다.** 결정으로 뺀 것이 아니라 **안 만들어서
없었다.** 판정문 넷(`Momentum-trend-IRS`, `-full`, 선물 셋)이 전부 그 위에 서 있다.

⚠ **이 자리가 하는 일은 «고르기»가 아니다.** 등록된 구조(50/50)를 새 계기 위에
세워 게이트에 태우는 것이고, 그래야 「IRS 에서는 추세만 쓴다」가 **결정**이 될 수
있다. 지금은 결정이 아니라 누락이다.

## 셈

`momentum_evaluate` 가 선물에서 쓰는 그 축을 그대로 쓴다 — 신호계 3 × 볼 윈도 3.
다리별 칸 계획도 그 레인 것과 같다(`cells_for`): 거시 다리는 신호 축이
`external_signals` 에 막혀 3칸뿐이다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ctabacktest as cta                              # noqa: E402
from app import momentum as mo                                  # noqa: E402
from evaluation import metrics as ev, randomization as rz, report  # noqa: E402
from scripts import momentum_evaluate as me                     # noqa: E402
from scripts import momentum_irs_evaluate as mie                # noqa: E402

_RUNS: dict = {}


def macro_sign_from(macro: dict, themes: tuple[str, ...]) -> dict[str, float]:
    """테마 부분집합으로 `macro_sign` 을 다시 센다.

    원본 `macro_sign` 은 **그날 값이 있는 테마들의 평균**이다(각 ±1). 실측으로
    2,360일 중 1,323일이 「합의 부호」와 갈리는데, 그건 평균이라서다 —
    (−1,−1,+1,−1) 이면 합의 부호는 −1 이지만 평균은 −0.5 다.

    ⚠ 빼는 것은 **사양 변경**이다. 등록된 북은 테마 넷이고, 여기서 셋으로 줄이면
    그 북이 아니다. 호출부가 그 사실을 적어야 한다.
    """
    days = set()
    for t in themes:
        days |= set(macro[t])
    out = {}
    for d in sorted(days):
        vals = [macro[t][d] for t in themes if d in macro[t]]
        if vals:
            out[d] = sum(vals) / len(vals)
    return out


def _ext_key(external) -> int | None:
    """외부 신호의 **내용**으로 키를 만든다. `is not None` 만 보면 원천이 다른 두
    거시 북(oecd/bok · drop 조합)이 한 프로세스에서 조용히 서로를 재사용한다
    (2026-09-15 계보 감사). 호출부가 캐시를 비우던 관행은 이제 필요 없다."""
    if external is None:
        return None
    return hash(tuple((k, tuple(sorted(v.items()))) for k, v in sorted(external.items())))


def _book(series, *, signal: str, vol_window: int, external=None) -> dict:
    key = (signal, vol_window, _ext_key(external))
    if key in _RUNS:
        return _RUNS[key]
    out = cta.book_simulate(
        series, signal=signal, lookbacks=mo.LOOKBACKS, vol_window=vol_window,
        target_book_vol_krw=mo.TARGET_VOL, book_vol_window=mo.BOOK_VOL_WINDOW,
        roll_days=set(), continuous=True, external_signals=external,
        cost_ticks=mie.IRS_COST_BP / cta.TICK)
    _RUNS[key] = out
    return out


def _pnl(points) -> pd.Series:
    return pd.Series([p["dailyPnl"] for p in points],
                     index=[p["t"] for p in points], dtype=float)


def legs(series, macro, sign=None) -> dict[str, dict]:
    """다리 셋의 (수익 계열, 칸 행렬, 위약). 선물 쪽 `legs_of` 와 같은 합성이다."""
    sig = macro["macro_sign"] if sign is None else sign
    ext = {k: sig for k in series}
    start = min(sig)

    def cut(s: pd.Series) -> pd.Series:
        return s[(s.index >= start) & (s.index <= mo.FREEZE)]

    out: dict[str, dict] = {}
    for leg in ("trend", "macro", "blend"):
        cols = {}
        for sg, vw in me.cells_for(leg):
            e = None if leg == "trend" else ext
            if leg == "blend":
                t = cut(_pnl(_book(series, signal=sg, vol_window=vw)["points"]))
                m = cut(_pnl(_book(series, signal=sg, vol_window=vw,
                                   external=ext)["points"]))
                ix = t.index.intersection(m.index)
                cols[f"{sg}-vw{vw}"] = 0.5 * t.loc[ix] + 0.5 * m.loc[ix]
            else:
                cols[f"{sg}-vw{vw}"] = cut(
                    _pnl(_book(series, signal=sg, vol_window=vw,
                               external=e)["points"]))
        mat = pd.DataFrame(cols).dropna()
        out[leg] = {"mat": mat, "rets": mat[mie.BASE_COL if leg != "macro"
                                            else mat.columns[0]]}
    return out


def placebo_for(leg: str, series, macro, mask_index, sign=None) -> dict:
    """위약 두 판. blend 는 두 북을 **같은 k 로** 밀어 손익을 반씩 섞는다."""
    ext = {k: (macro["macro_sign"] if sign is None else sign) for k in series}
    t_book = _book(series, signal=mo.SIGNAL, vol_window=mo.VOL_WINDOW)
    price = {k: dict(zip(*series[k])) for k in series}
    tk = mie.IRS_COST_BP / cta.TICK
    pl = rz.plumbing(t_book["dates"], price, set(), tk, cta.TICK)
    pl_g = rz.plumbing(t_book["dates"], price, set(), 0.0, cta.TICK)
    keep = set(mask_index)
    mask = np.array([d in keep for d in t_book["dates"]])
    lo = max(mo.LOOKBACKS)

    if leg == "trend":
        return rz.placebo(pl, t_book["pos"], shift_min=lo, mask=mask,
                          pl_gross=pl_g)
    m_book = _book(series, signal=mo.SIGNAL, vol_window=mo.VOL_WINDOW,
                   external=ext)
    if leg == "macro":
        return rz.placebo(pl, m_book["pos"], shift_min=lo, mask=mask,
                          pl_gross=pl_g)

    def blended(which, a, b):
        return 0.5 * rz.repnl(which, a) + 0.5 * rz.repnl(which, b)

    shifts = list(range(lo, pl["n"] - lo, rz.SHIFT_STEP))

    def one(which):
        real = rz._sr(blended(which, t_book["pos"], m_book["pos"])[mask])
        a = np.array([rz._sr(blended(which,
                                     rz.shifted(t_book["pos"], k, sign_only=True),
                                     rz.shifted(m_book["pos"], k, sign_only=True))
                             [mask]) for k in shifts])
        beat = int((a >= real).sum())
        return (beat + 1) / (len(a) + 1), real, beat, a

    p, real, beat, a = one(pl)
    pg, real_g, beat_g, g = one(pl_g)
    return {"p": p, "n_shifts": len(a), "real_sr": real, "beat": beat,
            "placebo_median": float(np.median(a)),
            "placebo_p95": float(np.percentile(a, 95)),
            "p_gross": pg, "real_sr_gross": real_g, "beat_gross": beat_g,
            "placebo_gross_median": float(np.median(g)),
            "placebo_gross_p95": float(np.percentile(g, 95)),
            "sign_only": True, "why": None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop", default="", help="뺄 테마(쉼표). 예: policy")
    ap.add_argument("--paper", action="store_true",
                    help="테마 둘을 원논문 정의로 — 통화정책 통안2Y · 위험선호 주식초과수익")
    ap.add_argument("--cycle", choices=("oecd", "bok"), default="oecd",
                    help="경기순환 원천 — oecd 실현치(지금) 또는 bok 한은 전망치(논문). "
                         "--paper 와 같이 쓸 때만 의미가 있다")
    a = ap.parse_args()
    if a.cycle == "bok" and not a.paper:
        raise SystemExit("--cycle bok 은 --paper 와 같이 쓰세요 — "
                         "경기순환만 논문으로 되돌리는 판은 등록된 적이 없어요")

    series = mie.load_irs_series()
    _s, _r, macro = me._inputs()
    if macro is None:
        raise SystemExit("매크로 신호가 없어서 거시·50/50 다리를 못 세워요")

    if a.paper:
        #: 원논문(Brooks 2017) Appendix B 정의로 되돌린 신호. 성과를 보고 고른
        #: 것이 아니라 원문과 대조해 어긋난 자리를 맞춘 것이다.
        from scripts import macro_paper_fix as mp
        macro = dict(macro)
        macro["macro_sign"] = mp.as_signal(
            mp.themes(mp._load(), paper=True, cycle=a.cycle))

    drop = tuple(x.strip() for x in a.drop.split(",") if x.strip())
    all_th = tuple(k for k, _l in mo.THEMES)
    bad = [x for x in drop if x not in all_th]
    if bad:
        raise SystemExit(f"그런 테마가 없어요 — {bad}. 있는 것은 {all_th} 예요")
    keep = tuple(t for t in all_th if t not in drop)
    sign = None if not drop else macro_sign_from(macro, keep)
    #: ⚠ 원천이 다르면 다른 판이다. 판정문 id 가 같으면 **조용히 덮어쓴다**(09-11 에
    #: 한 번 그랬다). 태그에 넣는다. 두 판 모두 2,389봉이다(RESULT_cycle_bok §1).
    tag = (("-paper" if a.paper else "")
           + ("-bokcycle" if a.cycle == "bok" else "")
           + ("" if not drop else f"-no-{'-'.join(drop)}"))

    L = legs(series, macro, sign)

    print()
    if drop:
        print(f"★테마를 뺐다 — 남은 것 {keep} · 뺀 것 {drop} [OWNER 2026-09-11]")
    print(f"── IRS 세 다리 · 등록 구조는 **50/50** 이다 ({len(L['blend']['mat']):,}봉) ──")
    print(f"  {'다리':10s} {'DSR':>8s} {'PBO':>8s} {'위약 후':>8s} {'위약 전':>8s} "
          f"{'CDaR비':>8s}  판정")
    for leg in ("trend", "macro", "blend"):
        mat = L[leg]["mat"]
        rets = L[leg]["rets"]
        sr_var = float(((mat.mean() / mat.std(ddof=1)).dropna()).var(ddof=1))
        out = ev.evaluate(
            rets.reset_index(drop=True), trials=mie.TRIALS, is_oos_splits=16,
            configs=mat, sr_var=sr_var if sr_var > 0 else None,
            #: ⚠ id 가 momentum_irs_evaluate 의 판정문과 겹치면 **덮어쓴다**.
            #: 창이 달라(여기 2,389봉 · 거기 2,370봉 — 선물 달력과 교집합) 수도
            #: 다르므로 반드시 다른 이름이어야 한다. 2026-09-11 에 실제로 한 번
            #: 덮어썼다.
            strategy_id=f"Momentum-{leg}-IRS-legs{tag}",
            cost_bp_roundtrip=mie.IRS_COST_BP * 2,
            placebo=placebo_for(leg, series, macro, mat.index, sign),
            assumptions=[
                "★등록된 북은 **추세·거시 50/50** 이다(사전등록 2026-09-08). IRS 로 "
                "계기를 옮길 때 추세 다리만 건너왔고, 이 표가 그 누락을 메운다.",
                (f"⚠ 테마 {drop} 를 뺐다 [OWNER 2026-09-11] — macro_sign 을 남은 "
                 f"{keep} 의 평균으로 다시 셌다. **등록된 북(테마 넷)이 아니므로 "
                 f"사전등록을 다시 얼어야 결정이 된다.**") if drop else
                "테마 넷을 다 쓴다 — 등록된 구성 그대로다.",
                f"시행수 N = {mie.TRIALS} — `momentum_irs_evaluate` 와 같은 셈"
                f"(신호계 × 볼 윈도 × 다리 구성 × 계기 둘).",
                f"칸 {mat.shape[1]}개 · {mat.shape[0]}봉 "
                f"({mat.index[0]}~{mat.index[-1]}). 거시 다리는 신호 축이 "
                f"external_signals 에 막혀 칸이 적다.",
            ])
        g, r = out["gate"], out["ranking"]

        def num(v, f=".4f"):
            return f"{v:{f}}" if v is not None else "—"
        print(f"  {leg:10s} {num(g['dsr']):>8s} {num(g['pbo']):>8s} "
              f"{num(g['placebo_p']):>8s} {num(g['placebo_p_gross']):>8s} "
              f"{num(r['cdar_ratio'], '.3f'):>8s}  "
              f"{'통과' if g['overall_pass'] else '미통과'}   "
              f"{report.write(out).name}")

    t = L["trend"]["rets"]
    m = L["macro"]["rets"]
    ix = t.index.intersection(m.index)
    print()
    print(f"  추세-거시 일별손익 상관 {float(np.corrcoef(t.loc[ix], m.loc[ix])[0, 1]):+.3f}")
    print("  ⚠ 이 표는 «고르는» 자리가 아니다. 등록 구조를 새 계기에 세워 본 것이고,")
    print("  어느 다리를 쓸지는 **사전등록을 다시 얼어야** 결정이 된다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
