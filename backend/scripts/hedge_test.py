# -*- coding: utf-8 -*-
r"""추세 슬리브가 **보험 노릇을 하나** — 계기를 갈아타기 전 마지막 한 칸.

    python -m scripts.hedge_test            # 셋 다
    python -m scripts.hedge_test --spells   # ① MR 이 가장 아팠던 구간에서 추세는
    python -m scripts.hedge_test --mix      # ② 결합 가중 — 개선의 «구간»까지
    python -m scripts.hedge_test --speed    # ③ 문헌이 가리킨 손잡이(추세 속도)

## 왜 이 자리가 필요한가

09-08 에 추세 슬리브를 승인한 근거는 단독 Sharpe 가 아니라 **헤지**였다 — 「MR 최악
낙폭 5구간 중 4에서 추세 양수 · w=0.25」(`research/ktb-tsmom/smile_use.py` B-2).
그런데 그 검정은 **선물 다리**로, 그리고 **증거금 상한을 안 본 MR 장부**로 돌린
것이다. 계기를 IRS 로 갈아타려면 그 보험이 그대로인지를 다시 물어야 한다.

여기서는 셋을 고친다.

    ① MR 장부를 **상한판**으로   `crs_evaluate.net_returns`(로트 50 · 묶인 것만)
    ② 「4/5」에 **p 를 붙인다**   구간 다섯은 표본이 아니다 — 순환이동 위약으로 잰다
    ③ 개선에 **구간을 붙인다**   ΔCalmar 점추정만 보고 「낫다」고 하지 않는다(§15 교훈)

## ★ 문헌이 미리 말해 주는 것 두 가지 — 그래서 ③ 을 같이 잰다

**(가) 위기알파의 기제는 «폭»과 «속도»다.** Nawrocki 외(2022, IRFA 80) 는 CTA 의
일별 섹터 포지션까지 들여다보고 위기알파의 출처를 둘로 짚는다 — 여러 시장에 걸쳐
**버는 시장이 깨지는 시장을 상쇄**하는 것, 그리고 **15일 안에 위기 시장 익스포저를
줄이는 속도**. 우리 슬리브는 **계기가 둘**(3Y·10Y 한 커브)이라 앞의 기제가
**구조적으로 없다.** 그러면 남는 것은 속도뿐이고, 그래서 ③ 이 룩백 다발을 흔든다.

**(나) 위험목표 규약이 Sharpe 와 위기알파를 맞바꾼다.** Kaminski·Hoffman 은 **상수
위험목표가 Sharpe 는 가장 높고 위기알파는 가장 작다**고 적는다. 우리 북은 정확히
상수 위험목표(`target_book_vol_krw`)다 — 즉 **보험으로 쓰려던 것을 수익 극대화
설정으로 굴리고 있다.** 이 스크립트는 그 사실을 바꾸지 않고 **재기만** 한다.

⚠ ③ 은 「룩백을 고르는 것」이 아니다. 이 데스크 규율은 「룩백을 매년 전진 선택하지
마라」(7년 −3,230만)이고 그건 **표본내 성적으로 고르는 것**을 금한다. 여기서 흔드는
것은 «슬리브의 일이 무엇이냐»에 맞춘 **설계 선택**이고, 고르려면 결과를 보기 전에
사전등록으로 얼려야 한다 — 이 표는 그 사전등록의 재료이지 채택이 아니다.

## 단위 — 둘 다 «단위 연변동성»으로 옮긴다

MR 은 자본 대비 비율이고 추세는 원(₩) 손익이라 그대로는 못 더한다. 둘을 각각
**연변동성 1** 로 맞춘 뒤 섞는다. 그러면 Calmar·MDD 가 무단위가 되고, 데스크 규율
(「위험 맞춤 후 비교」)과도 같은 자다. **수준은 옮기지 말고 상대 개선만 읽을 것.**
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ctabacktest as cta                              # noqa: E402
from app import momentum as mo                                  # noqa: E402
from evaluation import metrics as ev                            # noqa: E402
from scripts import crs_evaluate as ce                          # noqa: E402
from scripts import momentum_irs_evaluate as mie                # noqa: E402

ANN = 252

#: 결합 가중 격자 — `smile_use.py` 가 쓴 그 격자 그대로(다시 고르지 않는다).
WEIGHTS: tuple[float, ...] = (0.0, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50)

#: 09-08 에 승인된 가중.
W_REGISTERED = 0.25

#: 위약 이동 — `hard_test` 와 같은 규약(최장 룩백 이상 · 가능한 이동 전부).
SHIFT_MIN, SHIFT_STEP = 250, 10

#: ③ 이 흔드는 룩백 다발. 가운데가 **등록된 것**이고 양쪽이 빠르게/느리게 기운 판.
SPEEDS: dict[str, tuple[int, ...]] = {
    "빠름 (5~60)": (5, 10, 20, 40, 60),
    "등록 (20~250)": mo.LOOKBACKS,
    "느림 (60~500)": (60, 120, 250, 375, 500),
}


# ── 계열 ────────────────────────────────────────────────────────────────

def _iso(idx) -> list[str]:
    return [str(t)[:10] for t in idx]


def unit_vol(s: pd.Series) -> pd.Series:
    """연변동성 1 로 맞춘다 — 수준을 지우고 «모양»만 남기는 자리."""
    sd = float(s.std(ddof=1))
    return s * 0.0 if sd <= 0 else s / (sd * math.sqrt(ANN))


#: 09-08 의 B 검정이 쓴 **상한 무시판** 캐시. 그 판정을 같은 자로 다시 보려고 둔다.
LEGACY_BOOK = ce.LANE / "work" / "_book_20260907.json"

#: 어느 MR 장부를 쓰나. 기본은 상한판이다(§10 — 그쪽이 실물이다).
BOOK = "cap"


def mr_returns(book: str | None = None) -> pd.Series:
    """MR 장부의 일별 계열.

    `cap`    **증거금 상한판**(로트 50 · 자본비용은 묶인 것만) — §10 의 그 판.
    `legacy` 09-08 의 B 검정이 쓴 상한 무시판. 그때 판정을 재현·대조할 때만.
    """
    which = book or BOOK
    if which == "legacy":
        import json                                        # noqa: PLC0415
        if not LEGACY_BOOK.exists():
            raise SystemExit(f"옛 장부 캐시를 못 찾았어요 — {LEGACY_BOOK}")
        pts = json.loads(LEGACY_BOOK.read_text(encoding="utf-8"))["points"]
        return pd.Series([float(q["pnl"]) for q in pts],
                         index=[str(q["t"])[:10] for q in pts], dtype=float)
    mb = ce._lane()
    net, _facts = ce.net_returns(mb, ce.REGISTERED_LOT_UK, "bound")
    return pd.Series(net.to_numpy(dtype=float), index=_iso(net.index))


def trend_returns() -> dict[str, pd.Series]:
    irs, fut = mie.matrices()
    return {"IRS": irs[mie.BASE_COL], "선물": fut[mie.BASE_COL]}


def aligned() -> tuple[pd.Series, dict[str, pd.Series]]:
    """MR 과 두 다리를 **한 창** 위에 올리고 단위 연변동성으로 맞춘다."""
    mr = mr_returns()
    legs = trend_returns()
    idx = mr.index
    for s in legs.values():
        idx = idx.intersection(s.index)
    idx = sorted(idx)
    return unit_vol(mr.loc[idx]), {k: unit_vol(v.loc[idx]) for k, v in legs.items()}


def irs_leg_with(lookbacks: tuple[int, ...]) -> pd.Series:
    """룩백 다발만 갈아 끼운 IRS 추세 다리 — ③ 이 쓰는 판."""
    book = cta.book_simulate(
        mie.load_irs_series(), signal=mo.SIGNAL, lookbacks=lookbacks,
        vol_window=mo.VOL_WINDOW, target_book_vol_krw=mo.TARGET_VOL,
        book_vol_window=mo.BOOK_VOL_WINDOW, roll_days=set(), continuous=True,
        cost_ticks=mie.IRS_COST_BP / cta.TICK)
    return pd.Series([p["dailyPnl"] for p in book["points"]],
                     index=[p["t"] for p in book["points"]], dtype=float)


# ── 낙폭 구간 ────────────────────────────────────────────────────────────

def spells(x: pd.Series, k: int = 5) -> list[tuple[float, str, str]]:
    """MR 이 가장 아팠던 **겹치지 않는** k 구간 — `smile_use.py` 의 그 셈이다."""
    run = peak = 0.0
    start = x.index[0]
    out = []
    for t, v in x.items():
        run += float(v)
        if run >= peak:
            peak, start = run, t
        else:
            out.append((peak - run, start, t))
    worst: list[tuple[float, str, str]] = []
    for depth, a, b in sorted(out, key=lambda z: -z[0]):
        if all(b < wa or a > wb for _d, wa, wb in worst):
            worst.append((depth, a, b))
        if len(worst) == k:
            break
    return worst


def _spell_sum(leg: np.ndarray, ix: list[np.ndarray]) -> tuple[float, int]:
    tot = 0.0
    hit = 0
    for i in ix:
        v = float(leg[i].sum())
        tot += v
        hit += v > 0
    return tot, hit


def spell_test(verbose: bool = True) -> dict:
    mr, legs = aligned()
    ws = spells(mr)
    idx = {t: i for i, t in enumerate(mr.index)}
    ix = [np.array([idx[t] for t in mr.index if a <= t <= b]) for _d, a, b in ws]
    lens = [len(i) for i in ix]
    if verbose:
        print()
        print(f"── ① MR(상한판)이 가장 아팠던 다섯 구간에서 추세는 "
              f"({len(mr):,}봉 · {mr.index[0]}~{mr.index[-1]}) ──")
        print("  단위 연변동성 1 로 맞춘 뒤라 수준이 아니라 **모양**만 읽는다.")
        print(f"  {'구간':>26s} {'일수':>5s} {'MR':>8s} " +
              " ".join(f"{k:>8s}" for k in legs))
    out: dict = {"spells": ws, "legs": {}}
    for n, (_d, a, b) in enumerate(ws):
        row = [f"{float(mr.to_numpy()[ix[n]].sum()):>8.3f}"]
        for s in legs.values():
            row.append(f"{float(s.to_numpy()[ix[n]].sum()):>8.3f}")
        if verbose:
            print(f"  {a}~{b:<12s} {lens[n]:>5d} " + " ".join(row))

    for name, s in legs.items():
        arr = s.to_numpy()
        tot, hit = _spell_sum(arr, ix)
        shifts = range(SHIFT_MIN, len(arr) - SHIFT_MIN, SHIFT_STEP)
        pl = np.array([_spell_sum(np.roll(arr, k), ix)[0] for k in shifts])
        p = (int((pl >= tot).sum()) + 1) / (len(pl) + 1)
        #: 「양수 구간 몇 개」의 기준선 — 같은 길이 창이 그냥 양수일 확률.
        base = float(np.mean([
            float(np.roll(arr, k)[i].sum()) > 0
            for k in shifts for i in ix]))
        out["legs"][name] = {"total": tot, "hits": hit, "p": p, "base": base,
                             "placebo_median": float(np.median(pl))}
        if verbose:
            print(f"\n  [{name}] 다섯 구간 합 **{tot:+.3f}** · 양수 구간 "
                  f"**{hit}/5** · 위약 중앙 {np.median(pl):+.3f}")
            print(f"    위약({len(pl)}회 순환이동) 대비 **p = {p:.4f}** · "
                  f"같은 길이 창이 그냥 양수일 확률 {base:.3f} "
                  f"→ 4/5 의 이항 p = {_binom_tail(4, 5, base):.3f}")
    if verbose:
        print()
        print("  ★「4/5」는 그 자체로 증거가 아니다 — 구간이 다섯뿐이라 이항 꼬리가")
        print("     크다. 읽을 것은 **합의 위약 p** 이고, 그것이 이 표의 판정이다.")
    return out


def _binom_tail(k: int, n: int, p: float) -> float:
    return float(sum(math.comb(n, j) * p ** j * (1 - p) ** (n - j)
                     for j in range(k, n + 1)))


# ── 결합 ────────────────────────────────────────────────────────────────

def _card(x: np.ndarray) -> tuple[float, float]:
    """(Calmar, MDD) — 단위 연변동성 계열 위에서."""
    run = peak = mdd = 0.0
    for v in x:
        run += v
        peak = max(peak, run)
        mdd = max(mdd, peak - run)
    ann = x.mean() * ANN
    return (ann / mdd if mdd > 0 else float("nan")), mdd


def mix(verbose: bool = True) -> dict:
    mr, legs = aligned()
    m = mr.to_numpy()
    base_cal, base_mdd = _card(m)
    if verbose:
        print()
        print("── ② 결합 — 개선에 «구간»을 붙인다 (단위 연변동성 · 무단위) ──")
        print(f"  MR 단독 Calmar {base_cal:.3f} · MDD {base_mdd:.3f} · "
              f"상관: " + " · ".join(
                  f"{k} {float(np.corrcoef(m, v.to_numpy())[0, 1]):+.3f}"
                  for k, v in legs.items()))
    out: dict = {}
    for name, s in legs.items():
        t = s.to_numpy()
        if verbose:
            print(f"\n  [{name}]  {'w':>5s} {'Calmar':>8s} {'ΔCalmar':>9s} "
                  f"{'MDD':>8s} {'ΔMDD':>8s}")
        rows = {}
        for w in WEIGHTS:
            cal, md = _card((1 - w) * m + w * t)
            rows[w] = (cal, md)
            if verbose:
                print(f"        {w:>5.2f} {cal:>8.3f} {cal - base_cal:>+9.3f} "
                      f"{md:>8.3f} {md - base_mdd:>+8.3f}")
        #: 등록된 w 에서의 개선에 **짝지은 블록 부트스트랩 구간**을 붙인다.
        ci = _paired_ci(m, t, W_REGISTERED)
        out[name] = {"rows": rows, "ci": ci}
        if verbose:
            print(f"    w={W_REGISTERED} 의 ΔCalmar {rows[W_REGISTERED][0] - base_cal:+.3f} "
                  f"· 90% 구간 [{ci['cal'][0]:+.3f}, {ci['cal'][1]:+.3f}] "
                  f"· P(ΔCalmar ≤ 0) = {ci['p_cal']:.3f}")
            print(f"    {'':17s}ΔMDD    {rows[W_REGISTERED][1] - base_mdd:+.3f} "
                  f"· 90% 구간 [{ci['mdd'][0]:+.3f}, {ci['mdd'][1]:+.3f}] "
                  f"· P(ΔMDD ≥ 0) = {ci['p_mdd']:.3f}")
    if verbose:
        print()
        print("  ΔMDD 는 **음수여야** 개선이다(낙폭이 얕아진다). 점추정만 보고")
        print("  「보험이 된다」고 하지 않는 것이 §15 에서 배운 자리다.")
    return out


def _paired_ci(m: np.ndarray, t: np.ndarray, w: float, n: int = 400,
               block: int = ev.BOOT_BLOCK, seed: int = ev.BOOT_SEED) -> dict:
    """두 계열을 **같은 블록**으로 다시 뽑아 «개선» 의 구간을 낸다."""
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(m.size / block))
    dcal, dmdd = [], []
    for _ in range(n):
        starts = rng.integers(0, m.size, nb)
        ix = np.concatenate([np.arange(s, s + block)
                             for s in starts])[:m.size] % m.size
        mm, tt = m[ix], t[ix]
        b_cal, b_mdd = _card(mm)
        c_cal, c_mdd = _card((1 - w) * mm + w * tt)
        if np.isfinite(b_cal) and np.isfinite(c_cal):
            dcal.append(c_cal - b_cal)
            dmdd.append(c_mdd - b_mdd)
    a, b = np.array(dcal), np.array(dmdd)
    return {"cal": (float(np.percentile(a, 5)), float(np.percentile(a, 95))),
            "mdd": (float(np.percentile(b, 5)), float(np.percentile(b, 95))),
            "p_cal": float((a <= 0).mean()), "p_mdd": float((b >= 0).mean())}


# ── ③ 속도 ──────────────────────────────────────────────────────────────

def speed(verbose: bool = True) -> dict:
    """문헌이 가리킨 손잡이 — 폭이 없으면 남는 것은 **속도**다.

    ⚠ 고르는 표가 아니다. 사전등록 없이 여기서 하나를 집으면 이 레인이 금지한
    바로 그 짓(성적을 보고 룩백을 고르는 것)이 된다.
    """
    mr, _legs = aligned()
    m = mr.to_numpy()
    base_cal, base_mdd = _card(m)
    ws = spells(mr)
    idx = {t: i for i, t in enumerate(mr.index)}
    ix = [np.array([idx[t] for t in mr.index if a <= t <= b]) for _d, a, b in ws]
    print()
    print("── ③ 추세 속도를 흔들면 (IRS 다리 · 단위 연변동성) ──────────")
    print(f"  MR 단독 Calmar {base_cal:.3f} · MDD {base_mdd:.3f}")
    print(f"  {'룩백 다발':16s} {'단독 SR':>8s} {'상관':>7s} {'다섯구간 합':>11s} "
          f"{'양수':>5s} {'위약 p':>8s} {f'w={W_REGISTERED} ΔCalmar':>14s} "
          f"{'ΔMDD':>8s}")
    out = {}
    for label, lbs in SPEEDS.items():
        raw = irs_leg_with(lbs)
        s = unit_vol(raw.reindex(mr.index).dropna())
        if len(s) != len(mr):
            s = unit_vol(raw.loc[[t for t in mr.index if t in raw.index]])
        t = s.to_numpy()
        sr = float(raw.mean() / raw.std(ddof=1) * math.sqrt(ANN))
        tot, hit = _spell_sum(t, ix)
        shifts = range(SHIFT_MIN, len(t) - SHIFT_MIN, SHIFT_STEP)
        pl = np.array([_spell_sum(np.roll(t, k), ix)[0] for k in shifts])
        p = (int((pl >= tot).sum()) + 1) / (len(pl) + 1)
        cal, md = _card((1 - W_REGISTERED) * m + W_REGISTERED * t)
        rho = float(np.corrcoef(m, t)[0, 1])
        out[label] = {"sr": sr, "rho": rho, "total": tot, "hits": hit, "p": p,
                      "dcal": cal - base_cal, "dmdd": md - base_mdd}
        print(f"  {label:16s} {sr:>8.3f} {rho:>+7.3f} {tot:>11.3f} "
              f"{hit:>3d}/5 {p:>8.4f} {cal - base_cal:>+14.3f} "
              f"{md - base_mdd:>+8.3f}")
    print()
    print("  ★문헌의 예측: 폭(여러 시장)이 없으면 위기알파는 **속도**에서만 나온다")
    print("     (Nawrocki 외 2022 — 위기 시장 익스포저를 15일 안에 줄이는 것).")
    print("     그리고 상수 위험목표는 Sharpe 를 키우고 위기알파를 줄인다")
    print("     (Kaminski·Hoffman). 이 표는 그 둘을 우리 장부에서 확인하는 자리다.")
    print("  ⚠ **고르는 표가 아니다** — 고르려면 결과를 보기 전에 얼려야 한다.")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    for flag in ("spells", "mix", "speed"):
        ap.add_argument(f"--{flag}", action="store_true")
    ap.add_argument("--book", choices=("cap", "legacy"), default="cap",
                    help="MR 장부 — 상한판(기본) 또는 09-08 이 쓴 상한 무시판")
    a = ap.parse_args()
    globals()["BOOK"] = a.book
    todo = [f for f, on in ((spell_test, a.spells), (mix, a.mix),
                            (speed, a.speed)) if on]
    for f in todo or (spell_test, mix, speed):
        f()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
