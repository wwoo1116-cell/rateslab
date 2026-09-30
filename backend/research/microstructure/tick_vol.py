# -*- coding: utf-8 -*-
r"""변동성 정규화 틱사이즈 ρ̄ — **우리 상품이 어느 계층인가**.

    python -m research.microstructure.tick_vol

## 왜 재나 [2026-09-30]

외부 문헌(「Is Trend Still Your Friend? A Microstructural Account of the Demise
of Short-Term Trend-Following」, arXiv 2607.01550)의 결론은 **「추세가 죽었다」가
계약을 가린다**는 것이다. 판별 변수가 **변동성 정규화 틱사이즈**다:

    ρ̄(i,m) = (1/D_m) Σ_t  Ψ_i(t) / σ_i(t)        Ψ=호가단위 · σ=일변동성
    매월 계약을 이 비율로 줄 세워 중위에서 반 — 하위 50% 소형틱(ST) · 상위 50% 대형틱(LT)

    소형틱 : 2008 이후 추세 PnL **완전 붕괴**(SR ~0.8 → ~0), 전 지평(5·10·20·50일),
             5~20일이 최악
    대형틱 : **거의 온전**(0~30% 열화만)
    국채·금리 선물은 주로 **대형틱** 계층이고 열화가 없었다

기제: 2008 이후 HFT 메이커가 방향성 주문흐름에서 유동성을 빼면서, 얇은 소형틱
호가장에서는 공격적 체결에 필요한 잔여 깊이가 사라져 「신호→거래→가격충격→신호
강화」의 자기실현 고리가 끊겼다. 두꺼운 대형틱 장부는 그 고리를 유지했다.

## 이 스크립트가 재는 것

  ① KTB 3Y·10Y 선물의 ρ̄ (전표본 · 논문식 시변 σ · 연도별)
  ② 같은 자로 「편도 비용 / 하루 σ」 — **IRS 와 선물을 같은 눈금에** 올린다
     (ρ̄ 는 호가장이 있는 상품에만 뜻이 있고, 라이브 슬리브는 IRS 다)

## ⚠ 규약

· Ψ 는 `app/futures.py::TICK`(0.01 가격포인트) — 여기서 다시 적지 않는다.
· 선물 일변동성은 **`price_adj` 의 차분**으로 잰다(그 계열의 존재 이유 — 수준은
  무의미하고 차분은 정확하다). `implied` 는 bp 환산에만 쓴다.
· 비용 규약: 선물 편도 0.5틱(`app/futures.py::roll_cost`) · IRS 편도 0.5bp
  (`docs/PREREG_sleeve_5050_2026-09-15.md`). **IRS 쪽은 일부러 보수적인 값**이라
  이 표의 IRS 비율은 상한이다.
· ★가격↔bp 환산은 **이미 아는 수로 대조**한다 — 내재 수정듀레이션이 3Y≈2.8년 ·
  10Y≈9.4년 으로 나와야 한다(안 나오면 환산이 틀렸다).
"""
from __future__ import annotations

import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import futures as F                                   # noqa: E402
from app.dataset import load_dataset_merged                    # noqa: E402

#: σ_i(t) 추정창(영업일). 논문은 「daily volatility」만 말하고 창을 안 박았다 —
#: 그래서 이 값은 **고른 값**이고, 아래가 그 민감도를 같이 찍는다.
WINDOWS = (20, 60)

IRS_COST_BP = 0.5          # 등록서 편도 가정(보수적)
FUT_COST_TICK = 0.5        # roll_cost 의 편도


def _fut_diffs(s) -> list[tuple[object, float]]:
    """`price_adj` 의 일변화 — None 을 건너뛴다."""
    out = []
    for i in range(1, len(s.price_adj)):
        a, b = s.price_adj[i - 1], s.price_adj[i]
        if a is None or b is None:
            continue
        out.append((s.dates[i], b - a))
    return out


def _yield_diffs_bp(s) -> list[float]:
    ys = [v for v in s.implied if v is not None]
    return [(ys[i] - ys[i - 1]) * 100.0 for i in range(1, len(ys))]


def measure() -> dict:
    d = F.load()
    out = {"tick": F.TICK, "watermark": d.watermark, "fut": {}, "irs": {}}

    for k in ("3Y", "10Y"):
        s = d.series[k]
        rows = _fut_diffs(s)
        dp = [x[1] for x in rows]
        dy = _yield_diffs_bp(s)
        sp, sy = st.pstdev(dp), st.pstdev(dy)
        pts_per_bp = sp / sy
        tick_bp = F.TICK / pts_per_bp
        rec = {
            "n": len(dp), "first": rows[0][0], "last": rows[-1][0],
            "sigma_pts": sp, "sigma_bp": sy,
            "ticks_per_day": sp / F.TICK, "rho_full": F.TICK / sp,
            "pts_per_bp": pts_per_bp, "implied_duration": pts_per_bp / 0.01,
            "tick_bp": tick_bp, "cost_bp": FUT_COST_TICK * tick_bp,
            "cost_over_sigma": FUT_COST_TICK * tick_bp / sy,
            "rho_rolling": {}, "rho_by_year": {},
        }
        for W in WINDOWS:
            ratios, by_year = [], defaultdict(list)
            for i in range(W, len(rows)):
                sd = st.pstdev([x[1] for x in rows[i - W:i]])
                if sd > 0:
                    r = F.TICK / sd
                    ratios.append(r)
                    by_year[rows[i][0].year].append(r)
            rec["rho_rolling"][W] = st.mean(ratios)
            rec["rho_by_year"][W] = {y: st.mean(v) for y, v in sorted(by_year.items())}
        out["fut"][k] = rec

    ds = load_dataset_merged()
    for k in ("3Y", "10Y"):
        v = ds.series[k]
        dy = [(v[i] - v[i - 1]) * 100.0
              for i in range(1, len(v)) if v[i] is not None and v[i - 1] is not None]
        sy = st.pstdev(dy)
        out["irs"][k] = {"n": len(dy), "sigma_bp": sy, "cost_bp": IRS_COST_BP,
                         "cost_over_sigma": IRS_COST_BP / sy}
    return out


def main() -> int:
    m = measure()
    print(f"Ψ = {m['tick']} 가격포인트 (app/futures.py::TICK) · 워터마크 {m['watermark']}")
    print()
    print("── ① 대조: 가격↔bp 환산이 아는 듀레이션을 내는가 (3Y≈2.8 · 10Y≈9.4)")
    for k, r in m["fut"].items():
        print(f"   {k}: {r['pts_per_bp']:.4f} 포인트/bp → 내재 수정듀레이션 {r['implied_duration']:.2f}년")
    print()
    print("── ② ρ̄ 와 틱/일")
    for k, r in m["fut"].items():
        print(f"   {k}: 전표본 ρ̄ {r['rho_full']:.4f} · {r['ticks_per_day']:.1f} 틱/일"
              f"  ({r['n']}차분 · {r['first']}~{r['last']})")
        for W in WINDOWS:
            rr = r["rho_rolling"][W]
            print(f"       창 {W}일: ρ̄ {rr:.4f} → {1/rr:.1f} 틱/일")
        yrs = r["rho_by_year"][WINDOWS[0]]
        worst = max(yrs, key=lambda y: 1 / yrs[y])
        print(f"       연도별(창 {WINDOWS[0]}일) 최악 {worst}년 {1/yrs[worst]:.1f} 틱/일"
              f" · 최선 {min(yrs, key=lambda y: 1/yrs[y])}년 "
              f"{min(1/v for v in yrs.values()):.1f} 틱/일")
    print()
    print("── ③ 편도 비용 / 하루 σ — IRS 와 선물을 같은 눈금에")
    print(f"   {'상품':12s} {'σ(bp/일)':>9s} {'1틱(bp)':>8s} {'편도(bp)':>9s} {'비용/σ':>8s}")
    for k, r in m["fut"].items():
        print(f"   {'KTB'+k+' 선물':12s} {r['sigma_bp']:9.2f} {r['tick_bp']:8.3f}"
              f" {r['cost_bp']:9.3f} {r['cost_over_sigma']*100:7.1f}%")
    for k, r in m["irs"].items():
        print(f"   {'IRS '+k:12s} {r['sigma_bp']:9.2f} {'—':>8s}"
              f" {r['cost_bp']:9.3f} {r['cost_over_sigma']*100:7.1f}%")
    print()
    print("⚠ IRS 0.5bp 는 등록서의 **보수적** 가정이라 그 비율은 상한이다.")
    print("⚠ ρ̄ 는 호가장이 있는 상품의 자다 — IRS(장외)에는 대응물이 없다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
