# -*- coding: utf-8 -*-
r"""빡센 검정 — **§16 의 관점 위에서** 두 추세 다리를 다시 턴다 [OWNER 2026-09-10].

    python -m scripts.hard_test              # 넷 다
    python -m scripts.hard_test --regime     # ① 레짐 집중도
    python -m scripts.hard_test --placebo    # ② 위약(순환이동)
    python -m scripts.hard_test --placebo-grid  # ②′ 그 p 가 격자에 매달렸나
    python -m scripts.hard_test --bench      # ③ 벤치마크 대비 검정
    python -m scripts.hard_test --wfo        # ④ 전진 선택이 손해인가

## 왜 다시 도나 — 물음이 바뀌었다

§16 이 보인 것은 **DSR 게이트의 귀무가설이 이 표본에서 쓸모가 적다**는 것이다.
「SR 이 0 보다 큰가」를 9.40년으로 묻고 있는데, CTA 수준(0.5~0.61)의 참 Sharpe 조차
그 물음에 **11~26년**을 요구한다. 그러니 「미통과」는 전략에 대한 진술이 아니라
표본에 대한 진술이고, 그 자리에 계속 서 있으면 아무것도 안 배운다.

그래서 귀무가설을 **업계 수준으로 옮기고**(③), 그 전에 표본 자체가 무엇으로 만들어져
있는지를 먼저 턴다(①·②). 마지막으로 PBO 가 «확률» 로 말하던 것을 **돈으로** 다시
묻는다(④).

    ① 레짐 집중도    이 9.40년의 손익이 몇 개의 «시기» 위에 서 있나
    ② 위약           순환이동으로 타이밍만 죽이면 얼마가 남나 — 둘로 쪼갠다
    ③ 벤치마크 검정   H₀ 를 «0» 이 아니라 «SG CTA 0.61 / 펀드 0.50 / AQR 0.40» 로
    ④ 전진 선택      격자에서 매년 고르면 실제로 돈을 버나 잃나

## ② 위약을 **둘로** 쪼개는 이유

포지션 경로를 통째로 밀면 방향 타이밍만이 아니라 **변동성 타이밍**(위험 클 때
작게 드는 것)까지 같이 죽는다. 그러면 위약이 실제보다 세져 전략이 쉽게 이긴다.

    P1 경로 전체 이동   |포지션|·부호를 같이 민다 → 방향 + 변동성 타이밍이 죽는다
    P2 부호만 이동      |포지션| 은 제자리, 부호만 민다 → **방향 타이밍만** 죽는다

P2 가 진짜 시험이다. P1 은 그 위약이 얼마나 세게 잡았는지를 재는 대조군이다.

## ③ 「못 이긴다」와 「진다」는 다른 말이다

양쪽을 다 낸다 — `P(SR ≤ 눈금)` 과 `P(SR ≥ 눈금)`. 둘 다 크면 결론은 「미통과」가
아니라 **「이 표본에서 업계 눈금과 구별되지 않는다」**이고, 그것이 지금 우리가
말할 수 있는 가장 정확한 문장이다.

수수료는 §16-3 과 같은 자로 맞춘다(2/20 · σ 를 안 고르고 범위로).

## ④ 전진 선택 — PBO 를 돈으로 다시 묻는다

CSCV 는 «순위» 로 말한다. 여기서는 매년 말에 그때까지의 성적으로 아홉 칸 중
하나를 골라 **다음 해에 그것만** 들고, 그 실현 손익을 셋과 견준다.

    고르기        해마다 표본내 최고 칸
    고정          그 레인의 등록된 칸(`macross-vw60`) — 안 고르는 쪽
    등가중         아홉 칸을 다 반씩 — 「고르지 마라」의 극단

이 레인에는 이미 판례가 있다 — 룩백을 매년 전진 선택하면 7년 합이 −3,230만이었다
(`ktb-tsmom` 2026-09-08). 같은 물음을 계기 격자에 대고 다시 묻는 것이다.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ctabacktest as cta                              # noqa: E402
from app import momentum as mo                                  # noqa: E402
from evaluation import metrics as ev                            # noqa: E402
from scripts import gate_calibration as gc                      # noqa: E402
from scripts import momentum_evaluate as me                     # noqa: E402
from scripts import momentum_irs_evaluate as mie                # noqa: E402

ANN = 252

#: 한국 기준금리 인상기 — BOK 2021-08-26 첫 인상 ~ 2023-01-13 마지막 인상.
#: `ktb-tsmom` 레인이 「손익 70% 가 이 구간」이라고 적어 둔 그 창이다.
HIKING = ("2021-08-26", "2023-01-13")

#: 위약 이동 폭(영업일). 신호 룩백 최장이 250 이라 그보다 짧게 밀면 덜 끊긴다 —
#: 그래서 **양 끝 250봉을 뺀 전부**를 쓴다. 순환이동은 군(群)이라 이렇게 «가능한
#: 이동을 다 도는 것»이 이 위약의 정확한 형태다(랜덤 뽑기가 아니다). 음의 이동은
#: 곧 n−k 이동이라 따로 안 센다 — 그러면 같은 판을 두 번 세게 된다.
SHIFT_MIN = 250
SHIFT_STEP = 10

#: 벤치마크 눈금 — `gate_calibration.PEERS` 에서 «실거래·보수 차감 후» 셋만.
BENCH: tuple[tuple[str, float], ...] = (
    ("SG CTA 지수", 0.61),
    ("CTA 펀드 장수 수렴", 0.50),
    ("AQR 보수적 전망", 0.40),
)


# ── 북 ──────────────────────────────────────────────────────────────────

def books() -> dict[str, dict]:
    """두 다리의 **전체 북**(포지션·날짜까지) — 위약이 포지션을 필요로 한다."""
    irs_series = mie.load_irs_series()
    irs = cta.book_simulate(
        irs_series, signal=mo.SIGNAL, lookbacks=mo.LOOKBACKS,
        vol_window=mo.VOL_WINDOW, target_book_vol_krw=mo.TARGET_VOL,
        book_vol_window=mo.BOOK_VOL_WINDOW, roll_days=set(), continuous=True,
        cost_ticks=mie.IRS_COST_BP / cta.TICK)
    fut_series, rolls = mo._load_prices()
    fut = cta.book_simulate(
        fut_series, signal=mo.SIGNAL, lookbacks=mo.LOOKBACKS,
        vol_window=mo.VOL_WINDOW, target_book_vol_krw=mo.TARGET_VOL,
        book_vol_window=mo.BOOK_VOL_WINDOW, roll_days=rolls, continuous=True,
        cost_ticks=cta.COST_TICKS)
    return {"IRS": {"book": irs, "series": irs_series, "rolls": set(),
                    "ticks": mie.IRS_COST_BP / cta.TICK},
            "선물": {"book": fut, "series": fut_series, "rolls": rolls,
                    "ticks": cta.COST_TICKS}}


def _window() -> list[str]:
    """두 다리가 공유하는 날짜 — 모든 표가 이 창 위에 선다."""
    irs, fut = mie.matrices()
    return list(irs.index)


def leg_returns() -> dict[str, pd.Series]:
    irs, fut = mie.matrices()
    return {"IRS": irs[mie.BASE_COL], "선물": fut[mie.BASE_COL]}


def sr_ann(x) -> float:
    a = np.asarray(x, dtype=float)
    s = a.std(ddof=1)
    return float(a.mean() / s * math.sqrt(ANN)) if s > 0 else 0.0


# ── ① 레짐 집중도 ────────────────────────────────────────────────────────

def regime() -> None:
    print()
    print("── ① 이 9.40년의 손익이 몇 개의 «시기» 위에 서 있나 ──────────")
    rets = leg_returns()
    print(f"  {'해':>6s} " + " ".join(f"{k + ' 손익(만)':>13s} {k + ' SR':>8s}"
                                      for k in rets))
    years = sorted({t[:4] for t in rets["IRS"].index})
    for y in years:
        cells = []
        for r in rets.values():
            seg = r[[t for t in r.index if t.startswith(y)]]
            cells.append(f"{seg.sum() / 1e4:>13,.0f} {sr_ann(seg):>8.2f}")
        print(f"  {y:>6s} " + " ".join(cells))

    print()
    print(f"  {'구간':28s} " + " ".join(f"{k + ' SR':>9s} {k + ' 손익몫':>10s}"
                                        for k in rets))
    lo, hi = HIKING
    for label, keep in (
            (f"전체 ({len(rets['IRS']):,}봉)", lambda t: True),
            (f"인상기만 {lo}~{hi}", lambda t: lo <= t <= hi),
            ("인상기를 **빼면**", lambda t: not (lo <= t <= hi)),
    ):
        cells = []
        for r in rets.values():
            seg = r[[t for t in r.index if keep(t)]]
            share = seg.sum() / r.sum() if r.sum() else float("nan")
            cells.append(f"{sr_ann(seg):>9.2f} {100 * share:>9.1f}%")
        print(f"  {label:28s} " + " ".join(cells))

    print()
    print("  ★가장 좋았던 12개월 창을 하나 빼면")
    for name, r in rets.items():
        idx = list(r.index)
        best_i, best_v = 0, -math.inf
        for i in range(0, len(idx) - ANN):
            v = float(r.iloc[i:i + ANN].sum())
            if v > best_v:
                best_i, best_v = i, v
        drop = set(idx[best_i:best_i + ANN])
        rest = r[[t for t in idx if t not in drop]]
        print(f"    {name:5s} {idx[best_i]}~{idx[best_i + ANN - 1]} 이 손익의 "
              f"{100 * best_v / r.sum():>5.1f}% · 그 해를 빼면 SR "
              f"{sr_ann(r):.2f} → **{sr_ann(rest):.2f}**")


# ── ② 위약 — 순환이동 ────────────────────────────────────────────────────

def _plumbing(book: dict, series: dict, rolls: set, ticks: float) -> dict:
    """엔진 회계를 배열로 옮겨 둔다 — 위약을 수백 번 돌려야 해서 벡터로 편다.

    ⚠ 이 자리가 조용히 틀리기 제일 쉬운 곳이라, 실제 포지션을 넣으면 엔진의
    `dailyPnl` 과 **한 치도 안 달라야** 한다(`test_hard_test` 가 그걸 잰다).
    """
    dates = book["dates"]
    n = len(dates)
    dp, keys = {}, list(series)
    for k in keys:
        p = {d: v for d, v in zip(*series[k])}
        a = np.zeros(n)
        for i in range(1, n):
            t0, t1 = dates[i - 1], dates[i]
            if t0 in p and t1 in p:
                a[i] = p[t1] - p[t0]
        dp[k] = a
    roll = np.array([1.0 if t in rolls else 0.0 for t in dates])
    return {"dates": dates, "keys": keys, "dp": dp, "roll": roll,
            "ticks": ticks, "n": n}


def _repnl(pl: dict, pos: dict[str, list[float]]) -> np.ndarray:
    """포지션 경로 하나로 일별 손익(비용 포함)을 낸다."""
    n = pl["n"]
    out = np.zeros(n)
    unit = cta.TICK * pl["ticks"]
    for k in pl["keys"]:
        a = np.asarray(pos[k], dtype=float)
        prev = np.concatenate(([0.0], a[:-1]))
        out += prev / 100.0 * pl["dp"][k]
        out -= np.abs(a - prev) / 100.0 * unit
        out -= np.abs(prev) / 100.0 * cta.TICK * pl["roll"]
    return out


def _shifted(pos: dict[str, list[float]], k: int, *,
             sign_only: bool) -> dict[str, list[float]]:
    out = {}
    for key, v in pos.items():
        a = np.asarray(v, dtype=float)
        rolled = np.roll(a, k)
        out[key] = np.abs(a) * np.sign(rolled) if sign_only else rolled
    return out


def placebo() -> None:
    win = set(_window())
    for name, b in books().items():
        book, series = b["book"], b["series"]
        pl = _plumbing(book, series, b["rolls"], b["ticks"])
        mask = np.array([t in win for t in pl["dates"]])
        shifts = list(range(SHIFT_MIN, pl["n"] - SHIFT_MIN, SHIFT_STEP))
        if name == "IRS":
            print()
            print(f"── ② 위약 — 순환이동 **{len(shifts)}회** "
                  f"(이동 ≥ {SHIFT_MIN}봉 = 최장 룩백) ──")
        real_sr = sr_ann(_repnl(pl, book["pos"])[mask])
        print(f"\n  [{name}] 실제 SR {real_sr:.3f} · 이동 {len(shifts)}가지")
        for label, sign_only in (("P1 경로 전체 이동", False),
                                 ("P2 부호만 이동", True)):
            a = np.array([sr_ann(_repnl(pl, _shifted(book["pos"], k,
                                                     sign_only=sign_only))[mask])
                          for k in shifts])
            beat = int((a >= real_sr).sum())
            print(f"    {label:16s} 위약 SR 중앙 {np.median(a):+.3f} "
                  f"[{a.min():+.3f}, {a.max():+.3f}] · 95백분위 "
                  f"{np.percentile(a, 95):+.3f} · 실제를 이긴 위약 "
                  f"**{beat}/{len(a)}** (p = {(beat + 1) / (len(a) + 1):.4f})")
    print()
    print("  P2 가 시험이고 P1 은 대조군이다 — P1 이 훨씬 약하면 그 위약이 변동성")
    print("  타이밍까지 죽여서 세진 것이고, 그만큼 P1 의 p 는 낙관적으로 읽힌다.")


# ── ③ 벤치마크 대비 검정 ─────────────────────────────────────────────────

def _boot_sr(r: pd.Series, n: int = 1000, block: int = ev.BOOT_BLOCK,
             seed: int = ev.BOOT_SEED) -> np.ndarray:
    """순환 블록 부트스트랩으로 뽑은 **Lo 보정 연 SR** 분포."""
    x = np.asarray(r.dropna(), dtype=float)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(x.size / block))
    out = []
    for _ in range(n):
        starts = rng.integers(0, x.size, nb)
        idx = np.concatenate([np.arange(s, s + block)
                              for s in starts])[:x.size] % x.size
        v = ev.sharpe_lo(pd.Series(x[idx]))
        if v is not None and np.isfinite(v):
            out.append(float(v))
    return np.array(out)


def bench() -> None:
    print()
    print("── ③ H₀ 를 «0» 이 아니라 «업계 눈금» 으로 옮기면 ────────────")
    for name, r in leg_returns().items():
        a = _boot_sr(r)
        pt = ev.sharpe_lo(r)
        print(f"\n  [{name}] Lo 보정 연 SR {pt:.3f} · 90% 구간 "
              f"[{np.percentile(a, 5):.3f}, {np.percentile(a, 95):.3f}] "
              f"(뽑기 {len(a)})")
        print(f"    {'견줄 눈금':22s} {'총 SR 기준':>22s} "
              f"{'2/20 후 σ=10%':>22s} {'2/20 후 σ=15%':>22s}")
        for label, level in BENCH:
            cells = []
            for adj in (None, 0.10, 0.15):
                d = a if adj is None else gc.after_fees(a, adj)
                lo = float((d <= level).mean())
                hi = float((d >= level).mean())
                cells.append(f"↓{lo:.3f} ↑{hi:.3f}")
            print(f"    {label:22s} " + " ".join(f"{c:>22s}" for c in cells))
    print()
    print("  ↓ = P(우리 SR ≤ 눈금) · ↑ = P(우리 SR ≥ 눈금). **둘 다 0.05 를 넘으면**")
    print("  이 표본에서 그 눈금과 구별되지 않는다는 뜻이다 — 「진다」도 「이긴다」도")
    print("  아니다. 이 층이 지금 말할 수 있는 가장 정확한 문장이 그 자리에 있다.")


# ── ④ 전진 선택이 손해인가 ───────────────────────────────────────────────

def placebo_grid() -> None:
    """★위약의 p 가 **격자 선택에 매달려 있나** — 그 자체를 흔든다.

    이동 폭의 하한과 간격은 내가 고른 값이다. p 가 0.05 언저리로 나온 쪽(선물)이
    있으니 「하한·간격을 달리 잡았으면 통과했을 것」인지를 먼저 닫아야 한다.
    안 닫으면 이 검정도 노브 두 개짜리 격자가 된다.
    """
    win = set(_window())
    print()
    print("── ②′ 위약 p 가 이동 격자에 매달려 있나 (P2 부호만 이동) ──────")
    print(f"  {'다리':6s} {'이동 하한':>9s} {'간격':>5s} {'이동수':>6s} "
          f"{'이긴 위약':>11s} {'p':>8s}")
    for name, b in books().items():
        pl = _plumbing(b["book"], b["series"], b["rolls"], b["ticks"])
        mask = np.array([t in win for t in pl["dates"]])
        real = sr_ann(_repnl(pl, b["book"]["pos"])[mask])
        for lo in (250, 500, 750):
            for step in (5, 10, 25):
                sh = list(range(lo, pl["n"] - lo, step))
                a = np.array([
                    sr_ann(_repnl(pl, _shifted(b["book"]["pos"], k,
                                               sign_only=True))[mask])
                    for k in sh])
                beat = int((a >= real).sum())
                print(f"  {name:6s} {lo:>9d} {step:>5d} {len(sh):>6d} "
                      f"{beat:>6d}/{len(sh):<4d} {(beat + 1) / (len(a) + 1):>8.4f}")
    print()
    print("  ⚠ 성긴 격자에서는 p 의 **바닥**이 1/(이동수+1) 이라 작아질 수가 없다 —")
    print("     간격 25 줄의 p 가 커 보이는 것은 그 바닥 때문이지 증거가 약해진 것이")
    print("     아니다. 읽을 것은 두 다리가 **어느 격자에서도 갈리는가** 하나다.")


def _score_sr(is_rows: pd.DataFrame) -> pd.Series:
    return is_rows.mean() / is_rows.std(ddof=1)


def _score_cdar(is_rows: pd.DataFrame) -> pd.Series:
    """★오너가 정한 순위 기준으로 고른다 — 화면 자동채택이 쓰는 그 자다.

    「고르기가 손해인가」는 **무엇으로 고르느냐**에 매달릴 수 있다. SR 로만 재면
    이 레인이 실제로 쓰는 손잡이를 안 흔든 것이 된다.
    """
    out = {}
    for c in is_rows.columns:
        v = ev.cdar_ratio(ev.vol_normalize(is_rows[c])[0])["cdar_ratio"]
        out[c] = -math.inf if v is None else float(v)
    return pd.Series(out)


def walk_forward(mat: pd.DataFrame, fixed_col: str = mie.BASE_COL,
                 score=_score_sr) -> dict:
    """해마다 «그때까지의 자료만» 보고 고른다 — 고른 해는 절대 안 본다.

    ⚠ 룩어헤드가 들어가기 제일 쉬운 자리다. 표본내는 `t < y` 로 자르므로 그 해의
    첫날도 안 들어간다(`test_hard_test` 가 심어 둔 칸으로 그걸 잰다).
    """
    years = sorted({t[:4] for t in mat.index})
    picked, fixed, equal, picks = [], [], [], []
    for y in years[1:]:                       # 첫 해는 표본내가 없다
        is_rows = mat[[t < y for t in mat.index]]
        oos = mat[[t.startswith(y) for t in mat.index]]
        if is_rows.empty or oos.empty:
            continue
        best = score(is_rows).idxmax()
        picks.append((y, best))
        picked.append(oos[best])
        fixed.append(oos[fixed_col])
        equal.append(oos.mean(axis=1))
    return {"picked": pd.concat(picked), "fixed": pd.concat(fixed),
            "equal": pd.concat(equal), "picks": picks,
            "years": (years[1], years[-1])}


def wfo() -> None:
    print()
    print("── ④ 격자에서 매년 고르면 돈을 버나 잃나 ───────────────────")
    irs, fut = mie.matrices()
    for name, mat in (("IRS", irs), ("선물", fut)):
        for crit, fn in (("표본내 SR", _score_sr), ("CDaR 비[OWNER]", _score_cdar)):
            w = walk_forward(mat, score=fn)
            p, f, e = w["picked"], w["fixed"], w["equal"]
            print(f"\n  [{name} · {crit} 로 고름] 표본밖 {len(p):,}봉 "
                  f"({w['years'][0]}~{w['years'][1]})")
            for label, s in (("해마다 고르기", p), ("고정(등록된 칸)", f),
                             ("등가중 아홉 칸", e)):
                print(f"    {label:16s} 손익 {s.sum() / 1e4:>9,.0f}만 · "
                      f"SR {sr_ann(s):>6.3f}")
            gap = p.sum() - f.sum()
            print(f"    → 고르기가 고정 대비 {gap / 1e4:>+,.0f}만 "
                  f"({'손해' if gap < 0 else '이득'})")
            print("    고른 칸: " + " · ".join(f"{y}:{c}" for y, c in w["picks"]))
    print()
    print("  ⚠ 이 창은 2017년(둘 다 손실인 해)을 빼고 시작한다 — 표본내가 있어야")
    print("     고를 수 있어서다. 그래서 여기 SR 은 전체 표본 SR 보다 높게 나온다.")
    print("     읽을 것은 수준이 아니라 **세 줄의 차이**다.")


def main() -> int:
    ap = argparse.ArgumentParser()
    for flag in ("regime", "placebo", "bench", "wfo"):
        ap.add_argument(f"--{flag}", action="store_true")
    ap.add_argument("--placebo-grid", action="store_true", dest="grid",
                    help="위약 p 가 이동 격자에 매달려 있나")
    a = ap.parse_args()
    todo = [f for f, on in ((regime, a.regime), (placebo, a.placebo),
                            (placebo_grid, a.grid), (bench, a.bench),
                            (wfo, a.wfo)) if on]
    for f in todo or (regime, placebo, placebo_grid, bench, wfo):
        f()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
