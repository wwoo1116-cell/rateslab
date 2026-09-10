# -*- coding: utf-8 -*-
r"""게이트가 얼마나 높은가 — **글로벌 CTA 수준**에 대고 잰다 [OWNER 2026-09-10].

    python -m scripts.gate_calibration            # 전부
    python -m scripts.gate_calibration --hurdle   # 허들만(문턱을 분해한다)
    python -m scripts.gate_calibration --peers    # 외부 눈금과 나란히

> 「둘 다 기준이 너무 Harsh 한 거 같은데 글로벌 CTA 수준이랑 비교해볼래?」

## 이 파일이 «안» 하는 것

**문턱을 안 건드린다.** `DSR_PASS = 0.95` · `PBO_PASS = 0.20` 은 오너 사양의 값이고
(`metrics.py:43` 「게이트 문턱 — 오너 사양의 값 그대로」), 이 스크립트는 그 문턱이
**실물 눈금에서 어디쯤인지**만 낸다. 바꿀지 말지는 오너가 정한다 — 게이트에 걸린
것을 사양을 고쳐 통과시키지 않는 것이 이 레인의 규율이다[OWNER 2026-09-09].

## 허들 SR — 「이 표본에서 DSR 0.95 를 넘으려면 연 SR 이 얼마여야 하나」

DSR 을 뒤집어 푼다. 문턱 z = Φ⁻¹(0.95) = 1.6449 일 때

    (SR − SR0)·√(T−1) / √(1 − γ₃·SR + (γ₄−1)/4·SR²) = z

를 SR 에 대해 푼 값이 허들이다. 그 허들은 **둘로 쪼개진다**:

    허들 = SR0(뽑기 벌 — 시행수 N 이 정한다) + 유의폭(표본 길이 T 가 정한다)

이 쪼갬이 이 파일의 요점이다. 「기준이 harsh 하다」가 **시행수 벌 때문인지 표본이
짧아서인지**는 손잡이가 완전히 다른 물음이고, 실측하면 답이 한쪽으로 몰린다.

## 수수료 — 같은 단위로 옮기지 않으면 비교가 거짓말이 된다

SG CTA 지수는 **운용보수·성과보수를 뺀 뒤**의 수익이고, 우리 북은 거래비용만 뺐지
보수는 없다. `lane_costs` 가 「비용을 한 단위로」 했던 것과 같은 일을 여기서는
**보수**에 대해 한다. 2/20 을 물리면(운용 2% · 성과 20%)

    순 SR ≈ 0.8 × (총 SR − 0.02/σ)      σ = 자본 대비 연 변동성

운용보수는 «자본의» 2% 라 SR 단위로는 0.02/σ 만큼 깎이고, 성과보수는 이익에
비례하므로 대략 0.8배다. ⚠ σ 는 이 레인이 **일부러 안 정한 값**이다(자본 분모를
안 만든다[OWNER]) — 그래서 두 값(10%·15%)으로 범위를 낸다. 고르는 것이 아니라
「어느 쪽이든 결론이 같은가」를 보는 것이다.

## 외부 눈금 — 출처를 적는다

`PEERS` 의 각 줄에 논문·지수와 기간이 붙어 있다. 규칙 8(라이브러리 중립 판단은
인용 가능한 외부 표준에 둔다)의 숫자 판이다 — 「업계가 대충 0.5쯤」이라고 적으면
다음 세션이 그걸 못 대조한다.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
from scipy import optimize, stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation import metrics as ev                           # noqa: E402
from scripts import momentum_irs_evaluate as mie               # noqa: E402

ANN = 252

#: 외부 눈금 — (이름, 연 SR, 표본, 수수료 처리, 출처).
#: 전부 «초과» Sharpe 다: AQR 은 2/20 차감 후 현금 초과(총 14.3% · 변동성 9.9% ·
#: SR 1.00 이 그 셈으로만 맞는다), SG CTA 지수는 운용사 보수 차감 후 지수 수익이다.
PEERS: tuple[tuple[str, float, str, str, str], ...] = (
    ("CFM 200년 TF 백테스트", 0.70, "1800년대~2013", "비용·보수 전",
     "Lempérière 외 «Two centuries of trend following»(2014) · CFM 2022 재인용"),
    ("AQR TSMOM 67시장 전체표본", 1.00, "1903-01~2012-06", "2/20 차감",
     "Hurst·Ooi·Pedersen «A Century of Evidence»(Exhibit 1)"),
    ("AQR TSMOM 최근 10년", 0.61, "2003-01~2012-06", "2/20 차감",
     "같은 Exhibit 1 의 마지막 줄 — 10년 창이라 우리 표본과 길이가 비슷하다"),
    ("SG CTA 지수(실거래)", 0.61, "2000-01~2022", "보수 차감 후",
     "CFM 2022 Fig.2(Bloomberg) — 대형 20개사 · 연 수익 4.90%"),
    ("CTA 펀드 1,200개 장수 수렴", 0.50, "Eurekahedge 전수 ~2022", "보수 차감 후",
     "CFM 2022 Fig.3 — 트랙이 길어질수록 중앙값이 0.5 로 수렴"),
    ("AQR 의 «보수적» 전망 가정", 0.40, "2017 논문의 전망", "비용·보수 차감 후",
     "같은 논문 본문 — 「역사적 관측의 절반 이하」라고 스스로 단 값"),
)

#: 2/20 — 운용 2% · 성과 20%.
MGMT_FEE = 0.02
PERF_FEE = 0.20

#: 자본 대비 연 변동성 후보. 이 레인은 분모를 안 만드니 **고르지 않고 범위를 낸다**.
VOL_CASES: tuple[float, ...] = (0.10, 0.15)


def moments(mat) -> tuple[float, float, float, int, float]:
    """(주기 SR, 왜도, 초과첨도, 봉수, 격자 SR 분산) — DSR 이 먹는 것 그대로."""
    x = np.asarray(mat[mie.BASE_COL], dtype=float)
    sr = float(x.mean() / x.std(ddof=1))
    sk = float(stats.skew(x, bias=False))
    exku = float(stats.kurtosis(x, bias=False))
    var = float(((mat.mean() / mat.std(ddof=1)).dropna()).var(ddof=1))
    return sr, sk, exku, len(x), var


def _den(sr: float, sk: float, exku: float) -> float:
    return 1.0 - sk * sr + (exku + 3.0 - 1.0) / 4.0 * sr * sr


def hurdle_sr(sk: float, exku: float, n: int, sr0: float,
              target: float = ev.DSR_PASS) -> float:
    """DSR = 문턱이 되는 **주기 SR**. 없으면 못 넘는다는 뜻이 아니라 못 푸는 것이다."""
    z = stats.norm.ppf(target)

    def f(s: float) -> float:
        d = _den(s, sk, exku)
        return (s - sr0) * math.sqrt(n - 1) / math.sqrt(max(d, 1e-12)) - z

    return float(optimize.brentq(f, sr0 + 1e-12, 1.0))


def years_needed(sr_ann: float, sk: float, exku: float, sr0: float,
                 target: float = ev.DSR_PASS) -> float | None:
    """이 연 SR 이 «참»이라면 문턱을 넘기는 데 몇 년이 필요한가.

    `min_trl` 과 같은 물음인데 방향이 반대다 — 저쪽은 우리 SR 로 필요 연수를 내고,
    이쪽은 **남의 SR** 을 넣어 「그 수준이면 몇 년이 필요한가」를 낸다.
    """
    sr = sr_ann / math.sqrt(ANN)
    if sr <= sr0:
        return None
    z = stats.norm.ppf(target)
    n = 1.0 + (z * math.sqrt(_den(sr, sk, exku)) / (sr - sr0)) ** 2
    return n / ANN


def after_fees(sr_ann: float, vol: float) -> float:
    """2/20 을 물린 뒤의 연 SR — SG CTA 지수와 **같은 단위**로 옮기는 자리."""
    return (1.0 - PERF_FEE) * (sr_ann - MGMT_FEE / vol)


def _legs() -> dict[str, object]:
    irs, fut = mie.matrices()
    return {"IRS": irs, "선물": fut}


def show_hurdle() -> None:
    """허들을 «뽑기 벌»과 «표본 길이»로 쪼갠다 — 어느 쪽이 무거운지."""
    print()
    print("── DSR 0.95 를 넘으려면 연 SR 이 얼마여야 하나 ────────────────")
    for name, mat in _legs().items():
        sr, sk, exku, n, var = moments(mat)
        print(f"\n  [{name}] {n:,}봉 = {n / ANN:.2f}년 · 실현 연 SR "
              f"{sr * math.sqrt(ANN):.3f} · 왜도 {sk:+.2f} · 초과첨도 {exku:.1f}")
        print(f"    {'시행수 N':>10s} {'뽑기 벌 SR0':>12s} {'유의폭':>9s} "
              f"{'= 허들 연 SR':>13s}")
        for trials in (1, 9, 36, mie.TRIALS, 180, 1000):
            sr0 = ev.expected_max_sr(trials, var)
            h = hurdle_sr(sk, exku, n, sr0)
            tag = "  ← 지금" if trials == mie.TRIALS else ""
            print(f"    {trials:>10d} {sr0 * math.sqrt(ANN):>12.3f} "
                  f"{(h - sr0) * math.sqrt(ANN):>9.3f} "
                  f"{h * math.sqrt(ANN):>13.3f}{tag}")
    print()
    print("  ★ N=1 줄이 이 표의 요점이다 — **시행을 하나도 안 세도** 허들이 0.52 다.")
    print("     허들의 4분의 3은 「9.4년밖에 없다」에서 오고 시행수 벌은 4분의 1이다.")
    print("     N 을 어떻게 세든 이 표본에서는 결론이 안 바뀐다.")


def show_peers() -> None:
    """외부 눈금을 같은 자에 올린다 — 그 수준이면 몇 년이 필요한가."""
    legs = _legs()
    stats_by_leg = {k: moments(v) for k, v in legs.items()}
    print()
    print("── 글로벌 CTA 눈금 · 그 연 SR 이면 우리 게이트에 몇 년이 필요한가 ──")
    print(f"  {'눈금':28s} {'연 SR':>6s} {'수수료':>10s}  "
          f"{'필요 트랙(IRS)':>14s} {'필요 트랙(선물)':>15s}")
    for label, sr_ann, _period, fee, _src in PEERS:
        cells = []
        for leg in ("IRS", "선물"):
            sk, exku, var = (stats_by_leg[leg][1], stats_by_leg[leg][2],
                             stats_by_leg[leg][4])
            sr0 = ev.expected_max_sr(mie.TRIALS, var)
            y = years_needed(sr_ann, sk, exku, sr0)
            cells.append(f"{y:,.1f}년" if y else "∞")
        print(f"  {label:28s} {sr_ann:>6.2f} {fee:>10s}  "
              f"{cells[0]:>14s} {cells[1]:>15s}")
    print(f"  {'─' * 76}")
    for leg, mat in legs.items():
        sr, _sk, _exku, n, _var = moments(mat)
        print(f"  {'우리 ' + leg + ' 추세 다리':28s} "
              f"{sr * math.sqrt(ANN):>6.2f} {'보수 없음':>10s}  "
              f"{'가진 것 ' + f'{n / ANN:.2f}년':>14s}")
    print()
    print("  ⚠ 우리 수는 **보수 전**이라 이대로 견주면 우리 쪽이 유리하다. 아래가 그 정정이다.")


def before_fees(sr_net: float, vol: float) -> float:
    """보수 차감 «전» 으로 되돌린다 — `after_fees` 의 역함수.

    ## 왜 이 방향도 필요한가 [OWNER 2026-09-10]

    첫 판은 **우리 수를 보수 차감 후로 내리는 한 방향만** 냈다. 그건 「투자자가
    지수를 사면 받는 것」과 견주는 자리이고, 이 데스크는 지수를 사는 쪽이 아니라
    **전략을 굴리는 쪽**이다. 그러니 반대 방향, 즉 업계 지수를 **보수 전으로
    되돌려** 우리 자기자본 북과 같은 자리에 놓는 비교도 같이 내야 대칭이 된다.

    두 방향은 서로 다른 물음에 답한다.

        후(after)  「지수를 사는 것과 우리 북 중 무엇이 나은가」 — 원화에서는 살
                   지수가 없으므로 실행 가능한 대안이 아니다
        전(before) 「업계가 «하는 일» 과 우리가 «하는 일» 중 무엇이 나은가」 —
                   자기자본 북의 채택 판단은 이쪽이다
    """
    return sr_net / (1.0 - PERF_FEE) + MGMT_FEE / vol


def show_fees() -> None:
    """양방향으로 단위를 맞춘다 — 우리를 내리고, 업계를 올린다."""
    print()
    print("── 같은 수수료 단위로 옮기면 (2/20) ──────────────────────")
    print(f"  {'다리':10s} {'총 연 SR':>9s} " +
          " ".join(f"{'σ=' + f'{v:.0%}' + ' 순 SR':>12s}" for v in VOL_CASES))
    for name, mat in _legs().items():
        sr, _sk, _exku, _n, _var = moments(mat)
        g = sr * math.sqrt(ANN)
        cells = " ".join(f"{after_fees(g, v):>12.3f}" for v in VOL_CASES)
        print(f"  {name:10s} {g:>9.3f} {cells}")
    print()
    print("  ── 반대 방향: 업계 눈금을 **보수 전**으로 되돌리면 (우리 북과 같은 자리) ──")
    print(f"  {'눈금':24s} {'보수 후':>8s} " +
          " ".join(f"{'σ=' + f'{v:.0%}' + ' 보수 전':>13s}" for v in VOL_CASES))
    for label, sr_ann, _period, fee, _src in PEERS:
        if "차감 후" not in fee:
            continue
        cells = " ".join(f"{before_fees(sr_ann, v):>13.3f}" for v in VOL_CASES)
        print(f"  {label:24s} {sr_ann:>8.2f} {cells}")
    print()
    for name, mat in _legs().items():
        sr, _sk, _exku, _n, _var = moments(mat)
        print(f"  우리 {name} 다리(보수 없음) {sr * math.sqrt(ANN):>8.3f}")
    print()
    print("  ★두 방향이 **같은 말을 한다**: 우리를 내리면 0.52~0.57 대 지수 0.61,")
    print("     업계를 올리면 우리 0.851 대 지수 0.89~0.96. 어느 쪽으로 맞추든")
    print("     **우리가 살짝 아래이고, 구별할 수 있을 만큼은 아니다**(§17-3 참조).")
    print("  ⚠ σ 는 이 레인이 일부러 안 정한 값이다 — 고른 것이 아니라 범위다.")
    print("  ⚠ 단, 업계 눈금은 **50~70개 시장**에 분산된 포트폴리오다. 시장당으로 보면")
    print("     문헌 평균이 0.4 이므로 계기 둘짜리 0.851 은 그쪽 기준으로는 위다.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hurdle", action="store_true")
    ap.add_argument("--peers", action="store_true")
    ap.add_argument("--fees", action="store_true")
    a = ap.parse_args()
    todo = [f for f, on in ((show_hurdle, a.hurdle), (show_peers, a.peers),
                            (show_fees, a.fees)) if on]
    for f in todo or (show_hurdle, show_peers, show_fees):
        f()
    if not todo:
        print()
        print("  ※ 문턱은 안 건드렸다 — DSR 0.95 · PBO 0.20 은 오너 사양의 값이다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
