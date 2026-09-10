# -*- coding: utf-8 -*-
r"""왜 스왑 다리가 선물 다리보다 1.8배를 버나 [OWNER 2026-09-10].

    python -m scripts.why_irs             # 넷 다
    python -m scripts.why_irs --cross     # ① 신호 × 수익 2×2 — 어느 쪽 탓인가
    python -m scripts.why_irs --decomp    # ② 스왑 스프레드로 쪼갠다 ★결정적
    python -m scripts.why_irs --trend     # ③ 계열 자체가 더 추세를 그리나(분산비)
    python -m scripts.why_irs --roll      # ④ 롤이 얼마나 무나

## 무엇을 설명해야 하나

§15 의 실측: **비용 전** 손익이 IRS 18,278만 대 선물 10,039만(1.82배)인데 회전은
IRS 가 **더 적다**(0.1002 대 0.1125). 그러니 답은 비용도 회전도 아니다. 그리고
「고시가 뭉갠 것」도 닫혔다(IRS 일 Δ AR(1) −0.006/−0.041 · Δ=0 인 날 4.8%/3.7%).

## 이 파일이 묻는 것 넷

    ① 신호냐 수익이냐   같은 신호를 남의 계열에 걸어 본다 — 2×2 면 답이 갈린다
    ② ★스왑 스프레드    IRS 금리 = KTB 금리 + 스왑 스프레드. **같은 포지션**을 두
                       조각에 각각 걸어 IRS 손익을 «금리 몫»과 «스프레드 몫»으로 쪼갠다
    ③ 계열의 추세성      분산비 VR(q) = Var(q일 변화)/(q·Var(1일 변화)). 1 보다 크면 추세
    ④ 롤               선물만 무는 비용 — 크기가 설명력을 갖는지

②가 결정적인 이유: 선물은 **국채(KTB)** 를 보고 IRS 는 **스왑**을 본다. 둘의 차이가
곧 스왑 스프레드이고, 그것이 제 나름의 추세를 가지면 IRS 다리는 **두 개의 추세**를
타는 셈이 된다. 그러면 「계기가 둘」이 아니라 사실상 셋이었다는 말이 되고, §19-1 의
폭(breadth) 이야기와 같은 자리로 이어진다.

## 창을 맞춘다

두 계열을 **공통 날짜**로 자른 뒤 넷을 돌린다. 그래야 2×2 의 네 칸이 같은 달력
위에 선다. 등록된 북과 봉 수가 몇 개 다를 수 있는데(IRS 달력이 19일 길다) 이 표는
**상대 비교**용이라 그게 옳다.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ctabacktest as cta                              # noqa: E402
from app import momentum as mo                                  # noqa: E402
from evaluation import metrics as ev                            # noqa: E402
from scripts import momentum_irs_evaluate as mie                # noqa: E402

ANN = 252
TENORS = ("3Y", "10Y")

#: 국고채 금리(일별, %) — **남의 레인 파일이다.** 읽기만 하고 절대 안 건드린다.
KTB_CSV = {"3Y": Path(__file__).resolve().parents[1] / "data" / "raw"
           / "bigfoot_ktb3y_d.csv",
           "10Y": Path(__file__).resolve().parents[1] / "data" / "raw"
           / "bigfoot_ktb10y_d.csv"}

#: 분산비를 재는 지평 — 이 북의 룩백 다발과 같은 자리에 놓는다.
VR_Q: tuple[int, ...] = (5, 20, 60, 120, 250)


# ── 계열 ────────────────────────────────────────────────────────────────

def load_ktb_bp() -> dict[str, dict[str, float]]:
    """국고채 금리를 **−bp** 로 — IRS 계열과 같은 부호 규약(내리면 번다)."""
    out: dict[str, dict[str, float]] = {}
    for t, path in KTB_CSV.items():
        if not path.exists():
            raise SystemExit(f"국고채 금리 계열을 못 찾았어요 — {path}")
        rows = {}
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                v = r.get("DATA_VALUE", "")
                if v in ("", "NA", "nan"):
                    continue
                d = r["TIME"]
                rows[f"{d[:4]}-{d[4:6]}-{d[6:8]}"] = -float(v) * 100.0
        out[t] = rows
    return out


def series_pair() -> tuple[dict, dict, list[str]]:
    """(IRS 계열, 선물 계열, 공통 날짜) — 넷이 같은 달력 위에 서도록."""
    irs_raw = mie.load_irs_series()
    fut_raw, _rolls = mo._load_prices()
    common = set(irs_raw["3Y"][0])
    for t in TENORS:
        common &= set(fut_raw[t][0])
    days = sorted(common)
    irs = {t: (days, [dict(zip(*irs_raw[t]))[d] for d in days]) for t in TENORS}
    fut = {t: (days, [dict(zip(*fut_raw[t]))[d] for d in days]) for t in TENORS}
    return irs, fut, days


def book(series: dict, *, external=None, ticks: float = 0.0,
         rolls: set | None = None) -> dict:
    """비용을 **0 으로 두고** 돌린다 — 이 파일이 묻는 것은 비용 전 손익이다."""
    return cta.book_simulate(
        series, signal=mo.SIGNAL, lookbacks=mo.LOOKBACKS,
        vol_window=mo.VOL_WINDOW, target_book_vol_krw=mo.TARGET_VOL,
        book_vol_window=mo.BOOK_VOL_WINDOW, roll_days=rolls or set(),
        continuous=True, external_signals=external, cost_ticks=ticks)


def _pnl(b: dict) -> pd.Series:
    return pd.Series([p["dailyPnl"] for p in b["points"]],
                     index=[p["t"] for p in b["points"]], dtype=float)


def sr(x) -> float:
    a = np.asarray(x, dtype=float)
    s = a.std(ddof=1)
    return float(a.mean() / s * math.sqrt(ANN)) if s > 0 else 0.0


# ── ① 신호 × 수익 2×2 ───────────────────────────────────────────────────

def cross() -> None:
    irs, fut, days = series_pair()
    s_irs = mo._trend_signals(irs)
    s_fut = mo._trend_signals(fut)

    print()
    print(f"── ① 신호 × 수익 2×2 — 어느 쪽 탓인가 (비용 0 · {len(days):,}봉) ──")
    #: 신호가 실제로 얼마나 다른가부터.
    print(f"  {'테너':6s} {'신호 상관':>9s} {'부호 일치':>9s} {'|신호| IRS':>11s} "
          f"{'|신호| 선물':>11s}")
    for t in TENORS:
        a = np.array([s_irs[t].get(d, 0.0) for d in days])
        b = np.array([s_fut[t].get(d, 0.0) for d in days])
        same = float(np.mean(np.sign(a) == np.sign(b)))
        print(f"  {t:6s} {float(np.corrcoef(a, b)[0, 1]):>9.3f} {same:>9.3f} "
              f"{float(np.abs(a).mean()):>11.4f} {float(np.abs(b).mean()):>11.4f}")

    grid = {
        ("IRS", "IRS"): _pnl(book(irs)),
        ("IRS", "선물"): _pnl(book(fut, external=s_irs)),
        ("선물", "IRS"): _pnl(book(irs, external=s_fut)),
        ("선물", "선물"): _pnl(book(fut)),
    }
    print()
    print(f"  {'신호 \\ 수익':14s} {'IRS 계열':>22s} {'선물 계열':>22s}")
    for sg in ("IRS", "선물"):
        cells = []
        for rt in ("IRS", "선물"):
            x = grid[(sg, rt)]
            cells.append(f"{x.sum() / 1e4:>12,.0f}만 SR {sr(x):>5.2f}")
        print(f"  {sg + ' 신호':14s} {cells[0]:>22s} {cells[1]:>22s}")
    print()
    print("  ★읽는 법: 같은 «수익 계열» 안에서 두 줄이 비슷하면 신호는 죄가 없다.")
    print("     같은 «신호» 안에서 두 칸이 크게 다르면 **수익 계열**이 답이다.")


# ── ② 스왑 스프레드로 쪼갠다 ─────────────────────────────────────────────

def _dp(series: dict, days: list[str]) -> dict[str, np.ndarray]:
    out = {}
    for t in TENORS:
        p = dict(zip(*series[t]))
        a = np.zeros(len(days))
        for i in range(1, len(days)):
            a[i] = p[days[i]] - p[days[i - 1]]
        out[t] = a
    return out


def _apply(pos: dict, dp: dict[str, np.ndarray]) -> np.ndarray:
    """같은 포지션 경로를 다른 가격변화에 건다 — 비용은 안 센다(총손익 분해)."""
    out = np.zeros(len(next(iter(dp.values()))))
    for t in TENORS:
        a = np.asarray(pos[t], dtype=float)
        prev = np.concatenate(([0.0], a[:-1]))
        out += prev / 100.0 * dp[t]
    return out


def decomp() -> None:
    irs, _fut, days = series_pair()
    ktb = load_ktb_bp()
    have = [d for d in days if all(d in ktb[t] for t in TENORS)]
    if len(have) < 500:
        raise SystemExit(f"국고채 금리와 겹치는 날이 {len(have)}일뿐이에요")
    irs_c = {t: (have, [dict(zip(*irs[t]))[d] for d in have]) for t in TENORS}
    ktb_c = {t: (have, [ktb[t][d] for d in have]) for t in TENORS}
    #: 스왑 스프레드 조각 — 항등식이 **irs = ktb + spr** 이 되도록 잡는다.
    #: 세 계열이 모두 «−bp» 규약이므로 spr = irs − ktb 다.
    #: ⚠ 첫 판은 이걸 뒤집어 적었고, 아래 잔차 검사가 그걸 잡았다(5.8e6). 이
    #: 항등식 줄이 없으면 부호 하나로 표 전체가 조용히 거짓말을 한다.
    spr_c = {t: (have, [dict(zip(*irs[t]))[d] - ktb[t][d] for d in have])
             for t in TENORS}

    b = book(irs_c)
    dp_irs, dp_ktb, dp_spr = (_dp(x, have) for x in (irs_c, ktb_c, spr_c))
    tot = _apply(b["pos"], dp_irs)
    part_k = _apply(b["pos"], dp_ktb)
    part_s = _apply(b["pos"], dp_spr)

    print()
    print(f"── ② IRS 다리의 손익을 «금리 몫»과 «스프레드 몫»으로 ({len(have):,}봉 "
          f"· {have[0]}~{have[-1]}) ──")
    print("  같은 포지션 경로를 세 조각에 각각 건다. IRS 금리 = KTB 금리 + 스왑 스프레드")
    print("  이므로 아래 둘의 합이 위와 같아야 한다(항등식).")
    print(f"  {'조각':22s} {'손익(만)':>12s} {'SR':>7s} {'몫':>8s}")
    for label, x in (("IRS 다리 전체", tot), ("  ├ 국고채 금리 몫", part_k),
                     ("  └ 스왑 스프레드 몫", part_s)):
        share = x.sum() / tot.sum() if tot.sum() else float("nan")
        print(f"  {label:22s} {x.sum() / 1e4:>12,.0f} {sr(x):>7.2f} "
              f"{100 * share:>7.1f}%")
    resid = float(np.abs(tot - part_k - part_s).max())
    print(f"  항등식 잔차 {resid:.3e} (0 이어야 한다)")

    print()
    print("  스프레드 자체가 추세를 갖나 — 스프레드 «만» 보고 세운 북")
    b_spr = book(spr_c)
    b_ktb = book(ktb_c)
    x_spr, x_ktb = _pnl(b_spr), _pnl(b_ktb)
    print(f"  {'북':22s} {'손익(만)':>12s} {'SR':>7s} {'IRS 다리와 상관':>16s}")
    ti = pd.Series(tot, index=have)
    for label, x in (("스프레드 단독 북", x_spr), ("국고채 단독 북", x_ktb)):
        rho = float(np.corrcoef(x.to_numpy(), ti.to_numpy())[0, 1])
        print(f"  {label:22s} {x.sum() / 1e4:>12,.0f} {sr(x):>7.2f} {rho:>16.3f}")
    print()
    print("  ★스프레드 몫이 크면 IRS 다리는 «금리 추세»에 «스프레드 추세»를 하나 더")
    print("     얹은 것이고, 그건 신호가 좋아서가 아니라 **탄 시장이 하나 더**여서다.")


# ── ③ 계열의 추세성 ─────────────────────────────────────────────────────

def _vr(x: np.ndarray, q: int) -> float:
    d1 = np.diff(x)
    dq = x[q:] - x[:-q]
    v1 = d1.var(ddof=1)
    return float(dq.var(ddof=1) / (q * v1)) if v1 > 0 else float("nan")


def _vr_ci(x: np.ndarray, q: int, n: int = 300, block: int = 63,
           seed: int = ev.BOOT_SEED) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    d = np.diff(x)
    nb = int(np.ceil(d.size / block))
    vals = []
    for _ in range(n):
        st = rng.integers(0, d.size, nb)
        ix = np.concatenate([np.arange(s, s + block) for s in st])[:d.size] % d.size
        vals.append(_vr(np.concatenate(([0.0], np.cumsum(d[ix]))), q))
    a = np.array([v for v in vals if np.isfinite(v)])
    return float(np.percentile(a, 5)), float(np.percentile(a, 95))


def _vr_paired(a: np.ndarray, b: np.ndarray, q: int, n: int = 400,
               block: int = 63, seed: int = ev.BOOT_SEED) -> dict:
    """VR 차이의 구간 — **같은 블록**으로 두 계열을 다시 뽑는다.

    주변 구간 둘을 겹쳐 보는 것은 차이의 검정이 아니다(§15-3). 두 계열은 같은
    날짜 위에 있고 같은 금리를 보므로 «그 해가 어땠나»가 공통이고, 그 부분은
    차이에서 지워진다.
    """
    da, db = np.diff(a), np.diff(b)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(da.size / block))
    out = []
    for _ in range(n):
        st = rng.integers(0, da.size, nb)
        ix = np.concatenate([np.arange(s, s + block)
                             for s in st])[:da.size] % da.size
        va = _vr(np.concatenate(([0.0], np.cumsum(da[ix]))), q)
        vb = _vr(np.concatenate(([0.0], np.cumsum(db[ix]))), q)
        if np.isfinite(va) and np.isfinite(vb):
            out.append(va - vb)
    arr = np.array(out)
    return {"lo": float(np.percentile(arr, 5)),
            "hi": float(np.percentile(arr, 95)),
            "p": float((arr <= 0).mean())}


def trend() -> None:
    irs, fut, days = series_pair()
    ktb = load_ktb_bp()
    have = [d for d in days if all(d in ktb[t] for t in TENORS)]
    cash = {t: [ktb[t][d] for d in have] for t in TENORS}
    keep = [i for i, d in enumerate(days) if d in set(have)]
    print()
    print(f"── ③ 계열 자체가 더 추세를 그리나 — 분산비 VR(q) ({len(have):,}봉) ──")
    print("  VR = Var(q일 변화)/(q·Var(1일 변화)). 임의보행이면 1, 추세면 >1.")
    print(f"  {'계열':14s} " + " ".join(f"{'VR(' + str(q) + ')':>16s}"
                                       for q in VR_Q))
    ser = {}
    for label, s in (("IRS 3Y", np.asarray(irs["3Y"][1])[keep]),
                     ("국고 현물 3Y", np.asarray(cash["3Y"])),
                     ("국고 선물 3Y", np.asarray(fut["3Y"][1])[keep]),
                     ("IRS 10Y", np.asarray(irs["10Y"][1])[keep]),
                     ("국고 현물 10Y", np.asarray(cash["10Y"])),
                     ("국고 선물 10Y", np.asarray(fut["10Y"][1])[keep])):
        x = np.asarray(s, dtype=float)
        ser[label] = x
        cells = []
        for q in VR_Q:
            lo, hi = _vr_ci(x, q)
            cells.append(f"{_vr(x, q):.2f} [{lo:.2f},{hi:.2f}]")
        print(f"  {label:14s} " + " ".join(f"{c:>16s}" for c in cells))

    print()
    print("  ★같은 시장을 보는 **현물 금리 대 선물 조정가** — 짝지은 차이로")
    print(f"  {'짝':22s} " + " ".join(f"{'ΔVR(' + str(q) + ')':>20s}"
                                     for q in VR_Q))
    for tenor in ("3Y", "10Y"):
        a, b = ser[f"국고 현물 {tenor}"], ser[f"국고 선물 {tenor}"]
        cells = []
        for q in VR_Q:
            d = _vr_paired(a, b, q)
            cells.append(f"{_vr(a, q) - _vr(b, q):+.2f} [{d['lo']:+.2f},"
                         f"{d['hi']:+.2f}] p{d['p']:.2f}")
        print(f"  {'현물−선물 ' + tenor:22s} " + " ".join(f"{c:>20s}"
                                                       for c in cells))
    print()
    print("  주변 구간 둘을 겹쳐 보는 것은 차이의 검정이 아니다(§15-3) — 아래 줄이")
    print("  그 자리다. 두 계열이 **같은 시장**을 보는데 ΔVR 이 0 을 배제하면,")
    print("  차이를 만든 것은 시장이 아니라 **계열을 만든 방식**이다.")


# ── ④ 롤 ────────────────────────────────────────────────────────────────

def roll() -> None:
    irs, fut, days = series_pair()
    _s, rolls = mo._load_prices()
    inwin = {d for d in rolls if d in set(days)}
    print()
    print(f"── ④ 롤 — 선물만 무는 것 ({len(inwin)}일이 창 안에 있다) ──")
    b0 = book(fut, ticks=cta.COST_TICKS, rolls=set())
    b1 = book(fut, ticks=cta.COST_TICKS, rolls=rolls)
    x0, x1 = _pnl(b0), _pnl(b1)
    print(f"  롤 비용 없이   {x0.sum() / 1e4:>10,.0f}만 · SR {sr(x0):.3f}")
    print(f"  롤 비용 물려   {x1.sum() / 1e4:>10,.0f}만 · SR {sr(x1):.3f}")
    print(f"  → 롤 비용 {abs(x1.sum() - x0.sum()) / 1e4:>10,.0f}만")
    print()
    print("  ⚠ 이 크기가 8,000만 짜리 격차를 설명하지 못하면 롤은 답이 아니다.")
    print("     그리고 조정가라 **롤 점프 자체**는 이미 계열에서 빠져 있다.")


def adjust() -> None:
    """★③ 이 「계열을 만든 방식」이라고 했으니 **어디서** 어긋나는지까지 본다.

    조정가는 롤에서 점프를 빼도록 만든 계열이다. 제대로 됐다면 롤일의 일변화가
    다른 날과 다를 이유가 없다. 그래서 셋을 잰다 — 현물 금리 변화와의 상관, 그
    회귀의 **잔차가 롤일에 몰리는가**, 그리고 **롤일을 빼면 추세성이 돌아오는가**.
    """
    irs, fut, days = series_pair()
    ktb = load_ktb_bp()
    have = [d for d in days if all(d in ktb[t] for t in TENORS)]
    keep = [i for i, d in enumerate(days) if d in set(have)]
    _s, rolls = mo._load_prices()
    print()
    print(f"── ⑤ 조정가가 어디서 어긋나나 ({len(have):,}봉 · 롤 "
          f"{len([d for d in have if d in rolls])}일) ──")
    print(f"  {'테너':6s} {'Δ상관':>7s} {'R²':>6s} {'잔차 몫':>7s} "
          f"{'잔차σ 롤/그밖':>13s} {'롤일 빼면 VR(250)':>18s} "
          f"{'잔차 자체의 VR(20/250)':>22s}")
    for t in TENORS:
        c = np.diff(np.asarray([ktb[t][d] for d in have], dtype=float))
        f_ = np.diff(np.asarray(fut[t][1], dtype=float)[keep])
        rho = float(np.corrcoef(c, f_)[0, 1])
        beta = float(np.polyfit(c, f_, 1)[0])
        res = f_ - beta * c - float(np.polyfit(c, f_, 1)[1])
        onroll = np.array([have[i + 1] in rolls for i in range(len(res))])
        s_on = float(res[onroll].std(ddof=1)) if onroll.sum() > 2 else float("nan")
        s_off = float(res[~onroll].std(ddof=1))
        #: 롤일의 일변화를 빼고(그날을 «없던 날»로) 다시 이어 붙인 계열의 VR.
        kept = np.concatenate(([0.0], np.cumsum(f_[~onroll])))
        raw = np.asarray(fut[t][1], dtype=float)[keep]
        cum = np.concatenate(([0.0], np.cumsum(res)))
        print(f"  {t:6s} {rho:>7.3f} {rho ** 2:>6.3f} "
              f"{1 - rho ** 2:>7.3f} {s_on / s_off:>13.2f} "
              f"{_vr(raw, 250):>8.2f} → {_vr(kept, 250):<7.2f} "
              f"{_vr(cum, 20):>10.2f} / {_vr(cum, 250):<9.2f}")
    print()
    print("  ★읽는 법 셋.")
    print("   · 롤일 잔차σ 배수가 크면 조정이 롤에서 뭔가를 남긴 것이다. 다만")
    print("     **롤일을 빼도 VR 이 안 돌아오면** 롤은 범인이 아니다(38일뿐이다).")
    print("   · 잔차 자체의 VR 이 1 보다 **한참 작으면** 그 잔차는 평균회귀하는")
    print("     고주파 잡음이다 — 베이시스·CTD 가 그런 모양이다.")
    print("   · 그 잡음은 **1일 분산(분모)만 부풀리고** q일 분산(분자)에는 안 쌓인다.")
    print("     그래서 VR 이 내려간다. 전략에는 두 번 문다 — 신호가 잡음 위에서")
    print("     만들어지고, 크기 조절이 쓰는 실현변동성도 같이 부푼다.")


def main() -> int:
    ap = argparse.ArgumentParser()
    for flag in ("cross", "decomp", "trend", "roll", "adjust"):
        ap.add_argument(f"--{flag}", action="store_true")
    a = ap.parse_args()
    todo = [f for f, on in ((cross, a.cross), (decomp, a.decomp),
                            (trend, a.trend), (roll, a.roll),
                            (adjust, a.adjust)) if on]
    for f in todo or (cross, decomp, trend, roll, adjust):
        f()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
