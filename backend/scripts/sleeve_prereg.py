# -*- coding: utf-8 -*-
r"""사전등록 동결 전에 닫아야 할 미결 둘 [OWNER 2026-09-11 · 스왑 증거금률 5%].

    python -m scripts.sleeve_prereg

## ① 증거금이 막는 날의 대가

`sleeve_margin` 이 센 것은 **넘는 날이 며칠인가**였다. 여기서는 **그 날 줄이면
성과가 얼마나 깎이나**를 잰다. 규약은 「남은 여력 안으로 비례 축소」다 —

    여력_t   = 상한 − 평균회귀가 그날 쓴 증거금
    허용_t   = min(슬리브가 원한 증거금, 여력_t)
    배율_t   = 허용_t / 원한_t            (≤ 1)

연속 북이라 「신규 진입만 막는다」가 정의되지 않는다(매일 크기가 바뀐다).
비례 축소는 그 레인의 배분기가 이미 하는 일과 같은 문법이고, 사후에 유리한 쪽을
고를 여지가 없다.

⚠ 손익에는 **전일 배율**을 건다. 오늘 포지션이 내일 변화를 먹으므로.

## ② 상관 −0.030 이 안정적인가

w=0.25 의 근거가 「상관이 0 언저리」인데, 그 값은 6.5년 **평균**이다. 250봉 롤링으로
펴 보고 범위를 적는다. 흔들리면 그것이 이 사전등록의 가장 큰 구멍이다.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import crs_evaluate as ce                           # noqa: E402
from scripts import hedge_test as ht                             # noqa: E402
from scripts import sleeve_margin as sg                          # noqa: E402

ANN = 252
RATE = 0.05          # [OWNER 2026-09-11] 스왑 증거금률
W = 0.25             # 등록 후보
ROLL = 250


def _sized(m: np.ndarray, t: np.ndarray, w: float):
    """(MR 배수, 추세 배수, σ_mix) — 총위험 고정의 그 산술."""
    s_mix = float(((1 - w) * m + w * t).std(ddof=1) * math.sqrt(ANN))
    return (1 - w) / s_mix, w / s_mix, s_mix


def _card(x: np.ndarray) -> tuple[float, float]:
    return ht._card(x)


def main() -> int:
    mb = ce._lane()
    net, facts = ce.net_returns(mb, ce.REGISTERED_LOT_UK, "bound")
    P, L, Z, meta = mb.load()
    _d, used, _dv, _e, _b = mb.simulate(P, L, Z, meta, ce.REGISTERED_LOT_UK)

    mr_u, legs = ht.aligned()
    m = mr_u.to_numpy()
    t = legs["IRS"].to_numpy()
    days = list(mr_u.index)
    k_mr, k_tr, s_mix = _sized(m, t, W)
    mr_vol_krw = float(net.std(ddof=1) * math.sqrt(ANN) * mb.CAP)
    trend_vol = float(pd.Series(
        [p["dailyPnl"] for p in sg.mie.irs_points()]).std(ddof=1) * math.sqrt(ANN))
    mult = (k_tr * mr_vol_krw) / trend_vol

    # ── 같은 날짜 위로
    dv = sg.sleeve_dv01()
    pv = sg.pv01_per_100m()
    face = sum((dv[k].abs() / pv[k] * 1e8) for k in dv.columns)
    face.index = [str(x)[:10] for x in face.index]
    u = pd.Series(used.to_numpy(dtype=float),
                  index=[str(x)[:10] for x in used.index])
    ix = [d for d in days if d in face.index and d in u.index]
    m_c = mr_u.loc[ix].to_numpy()
    t_c = legs["IRS"].loc[ix].to_numpy()
    want = face.loc[ix].to_numpy() * mult * RATE
    head = np.maximum(mb.CAP - u.loc[ix].to_numpy() * mb.CAP * k_mr, 0.0)

    print()
    print(f"── ① 증거금이 막는 날의 대가 (율 {RATE:.0%} · w {W} · {len(ix):,}봉) ──")
    scale = np.where(want > 0, np.minimum(want, head) / np.maximum(want, 1e-9), 1.0)
    scale = np.clip(scale, 0.0, 1.0)
    hit = int((scale < 0.999).sum())
    print(f"  줄인 날            {hit:,}일 ({hit / len(ix):.1%})")
    if hit:
        s_hit = scale[scale < 0.999]
        print(f"  줄인 날의 배율      평균 {s_hit.mean():.3f} · 최저 {s_hit.min():.3f}")

    lag = np.concatenate(([1.0], scale[:-1]))          # 전일 배율이 오늘 손익에
    base = (1 - W) / s_mix * m_c + W / s_mix * t_c
    capped = (1 - W) / s_mix * m_c + W / s_mix * t_c * lag
    b_cal, b_mdd = _card(base)
    c_cal, c_mdd = _card(capped)
    b_ann, c_ann = base.mean() * ANN, capped.mean() * ANN
    print()
    print(f"  {'':16s} {'연수익':>9s} {'Calmar':>8s} {'최대낙폭':>9s} {'연변동성':>9s}")
    for nm, x, cal, mdd in (("상한 무시", base, b_cal, b_mdd),
                            ("상한 지킴", capped, c_cal, c_mdd)):
        print(f"  {nm:16s} {x.mean() * ANN:9.4f} {cal:8.3f} {mdd:9.3f} "
              f"{x.std(ddof=1) * math.sqrt(ANN):9.3f}")
    print(f"  {'대가':16s} {c_ann - b_ann:+9.4f} {c_cal - b_cal:+8.3f} "
          f"{c_mdd - b_mdd:+9.3f}")
    print(f"  연수익 기준 {abs((c_ann - b_ann) / b_ann):.2%} 손실")

    print()
    print(f"── ② 상관 −0.030 이 안정적인가 ({ROLL}봉 롤링) ──")
    r = pd.Series(m_c).rolling(ROLL).corr(pd.Series(t_c)).dropna()
    print(f"  전체 평균          {float(np.corrcoef(m_c, t_c)[0, 1]):+.3f}")
    print(f"  롤링 평균          {r.mean():+.3f}")
    print(f"  롤링 범위          {r.min():+.3f} ~ {r.max():+.3f}")
    for q in (5, 25, 50, 75, 95):
        print(f"  {q:>3d}백분위          {np.percentile(r, q):+.3f}")
    over = int((r.abs() > 0.3).sum())
    print(f"  |상관| > 0.3 인 창   {over:,} / {len(r):,} ({over / len(r):.1%})")
    print()
    if over == 0:
        print("  ✔ 0.3 을 넘는 창이 없다 — W3 의 모니터링 문턱이 한 번도 안 걸린다.")
    else:
        print("  ⚠ 0.3 을 넘는 창이 있다 — 사전등록 §3-1 의 그 구멍이다.")
    print("  ⚠ 롤링 상관은 창이 겹쳐 독립 관측이 아니다. 범위는 서술이지 검정이 아니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
