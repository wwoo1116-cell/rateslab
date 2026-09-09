# -*- coding: utf-8 -*-
"""두 레인의 **비용 가정과 회전율을 같은 자로** 잰다 [OWNER 규율].

    python -m scripts.lane_costs

## 왜 이 스크립트가 있나

오너가 평가층에 못 박은 규율 하나가 이것이다 — 「**전략마다 다른 비용 가정을
쓰지 않는다.** MR 회전율이 추세추종의 5~20배라 2bp 대 5bp 가정 하나가 순위를
뒤집는다」. 그런데 두 레인의 비용은 **단위가 다르게** 적혀 있다:

    MR   편도 **0.5bp** (스프레드 패키지 · 국고+IRS 두 다리)
    CTA  편도 **0.5틱** (국채선물 가격 0.01포인트) + 보유 중 롤일마다 왕복 1틱

bp 와 틱은 그대로 못 견준다. **가정하지 말고 재고 들어갈 것** — 그래서 이 파일은
①두 비용을 **bp 한 단위로** 옮기고 ②실현 회전율을 같은 정의로 재고 ③비용 가정을
흔들어 **판정이 뒤집히는지**까지 본다.

## 같은 정의로 재는 회전율

    연 회전(편도) = Σ|Δ액면| / (포지션이 선 날의 평균 |액면|) / 년수

분모가 «포지션이 선 날» 인 것이 요점이다 — MR 은 봉의 88%가 무포지션이라 전 봉
평균으로 나누면 회전이 여덟 배로 부풀어 두 레인이 못 견준다.

## 틱 → bp

선물 액면 F 의 편도 비용은 `F/100 × 0.01 × 틱수` 원이고, 그 액면의 DV01 은
`F / F₁` 원/bp 다(`F₁` = DV01 1원/bp 를 내는 액면 — `futures.face_for_dv01`).
나누면 **액면이 소거되고** 편도 비용이 bp 로 남는다:

    편도(bp) = (틱수 × 1e-4) × F₁

⚠ **CTA 레인은 아직 미커밋이다**(`app/ctabacktest.py`·`scripts/cta_macro.py` 가
다른 세션의 작업). 없으면 이 스크립트는 **조용히 0 을 내지 않고** 그 사실을 적고
MR 쪽만 잰다.
"""
from __future__ import annotations

import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import futures                                        # noqa: E402

#: MR 화면의 비용 노브 — 편도 bp(스프레드 패키지).
MR_COST_BP = 0.5


def tick_to_bp(tenor: str, ticks: float = 0.5) -> tuple[float, float, float]:
    """(편도 bp, 그 계약의 내재금리, DV01 1원/bp 액면) — 모듈 머리의 그 식."""
    f = futures.load()
    y = [v for v in f.series[tenor].implied if v is not None][-1]
    face1 = futures.face_for_dv01(1.0, y, tenor)
    return ticks * 1e-4 * face1, y, face1


def cta_book(cost_ticks: float = 0.5, signal: str = "macross",
             lookbacks: tuple[int, ...] = (20, 250)) -> dict | None:
    """CTA 북 한 판 — **엔진 기본 인자**로 돈다. 레인이 없으면 `None`.

    ⚠ 이것은 **등록된 북이 아니다.** 룩백 둘에 북 변동성 목표가 없다. 처음 이
    자리를 잴 때 등록된 북이 뭔지 몰라 엔진 기본값으로 쟀고, 그 수(연 회전 30.98회 ·
    비용비 10.5%)를 오너에게 보고했다. 등록된 북은 `registered_book()` 이다 —
    룩백 다섯에 북 전체 변동성 목표가 걸려 있고, 그것으로 재면 **27.86회 · 8.4%**
    다. 결론(회전은 이쪽이 훨씬 크고 단가는 MR 이 훨씬 비싸다)은 안 바뀌지만
    수는 바뀌었으므로 둘 다 남겨 둔다.
    """
    try:
        from app import ctabacktest as cta
    except ImportError:
        return None
    f = futures.load()
    inst = {}
    for t in futures.FUT_TENORS:
        s = f.series[t]
        pairs = [(d.isoformat(), p) for d, p in zip(s.dates, s.price_adj) if p is not None]
        inst[t] = ([a for a, _ in pairs], [b for _, b in pairs])
    rolls = {d.isoformat() for t in futures.FUT_TENORS
             for d in futures.roll_days(list(f.series[t].dates))}
    return cta.book_simulate(inst, signal=signal, lookbacks=lookbacks,
                             roll_days=rolls, cost_ticks=cost_ticks)


def registered_book(cost_ticks: float = 0.5) -> dict | None:
    """**등록된 북** — 모멘텀 레인의 추세 다리 그 자체다.

    그 레인이 사전등록에 동결한 북이 곧 이 데스크의 CTA 다(신호 macross 하나 ·
    룩백 다섯 등가중 · 북 전체 변동성 목표). 그래서 「CTA 를 잰다」는 말은 이
    북을 잰다는 뜻이고, `momentum_evaluate` 가 그 북을 다시 세우는 자리라
    여기서는 그 자리를 부른다 — 재구성이 두 곳에 살면 갈린다.
    """
    try:
        from app import momentum as mo
        from scripts import momentum_evaluate as me
    except ImportError:
        return None
    series, rolls, _macro = me._inputs()
    return me._run(series, rolls, signal=mo.SIGNAL, vol_window=mo.VOL_WINDOW,
                   ticks=cost_ticks)


def turnover(pos: dict[str, list[float]], n: int, years: float) -> tuple[float, float]:
    """(연 회전 편도배수, 포지션이 선 날의 평균 |액면|) — 모듈 머리의 그 정의."""
    traded = 0.0
    face_on: list[float] = []
    for i in range(n):
        tot = 0.0
        for k in pos:
            prev = pos[k][i - 1] if i else 0.0
            traded += abs(pos[k][i] - prev)
            tot += abs(pos[k][i])
        if tot > 0:
            face_on.append(tot)
    avg = st.fmean(face_on) if face_on else 0.0
    return (traded / avg / years if avg > 0 else 0.0), avg


def cta_matrix(cost_ticks: float = 0.5) -> "object | None":
    """CTA 가 **실제로 고른 축** 위의 칸 행렬 — 신호 셋.

    ⚠ 룩백은 칸이 아니다. 그 레인은 다섯 룩백을 **등가중 평균**해 한 계열로 쓴다
    (AQR·AHL 의 그 규율이 모듈 머리에 적혀 있다) — 고르지 않은 축을 칸으로 세우면
    PBO 가 «있지도 않은 자유도» 로 벌하게 된다.

    ⚠ 그래서 칸이 **셋뿐**이고, 순위 공간이 {1,2,3} 이라 CSCV 가 거칠다. 이 값을
    MR 의 PBO 와 나란히 놓고 크기를 견주면 안 된다 — 판정은 각 레인의 것이다.
    """
    import pandas as pd
    from app import ctabacktest as cta

    cols = {}
    for sig in cta.SIGNALS:
        out = cta_book(cost_ticks=cost_ticks, signal=sig)
        if out is None:
            return None
        cols[sig] = [p["dailyPnl"] for p in out["points"]]
    return pd.DataFrame(cols)


def verdicts_by_cost() -> None:
    """**비용 가정을 흔들면 판정이 뒤집히나** — 오너 규율이 겨눈 바로 그 물음.

    두 레인을 각자의 단위로 흔든다(MR 은 bp, CTA 는 틱). 같은 «bp» 를 선물에
    억지로 물리지 않는 이유는 그것이 **없는 비용을 가정하는 것**이기 때문이다 —
    규율의 뜻은 「한쪽에 유리한 가정을 쓰지 말라」이지 「다른 상품에 같은 수를
    적으라」가 아니다. 대신 위에서 두 비용을 **같은 단위로 옮겨** 견줄 수 있게 했다.

    ★ CTA 쪽은 `momentum_evaluate` 에 넘긴다. 처음 판은 여기서 칸 셋(신호계)만으로
    급히 세웠는데, 그 격자는 **등록된 북의 격자가 아니었다** — 그 레인의 축은
    신호계 셋 × 볼 윈도 셋이고 시행수도 다리 구성까지 세야 한다. 그 자리가 생겼으니
    여기서 다시 정의하지 않는다.
    """
    from scripts import mr_evaluate as mre

    print()
    print("── 비용 가정을 흔들면 판정이 뒤집히나 ──────────────────")
    print(f"  {'레인/가정':24s} {'DSR':>8s} {'PBO':>8s} {'CDaR비':>8s}  판정")
    for bp in (0.25, 0.5, 1.0):
        mre.BASE["costBp"] = bp
        _verdict_row(f"MR BSS-2Y 편도 {bp}bp", mre.evaluate_leg("BSS-2Y"))
    mre.BASE["costBp"] = 0.5

    try:
        from scripts import momentum_evaluate as me
    except ImportError:
        print("  ⚠ 모멘텀/CTA 레인이 없어 못 쟀습니다.")
        return
    for ticks in (0.25, 0.5, 1.0):
        bp, _y, _f = tick_to_bp("3Y", ticks)
        _verdict_row(f"CTA 추세 편도 {ticks}틱(3Y {bp:.3f}bp)",
                     me.evaluate_leg("trend", ticks=ticks))


def _verdict_row(label: str, out: dict) -> None:
    """없는 값은 «—» 다 — 게이트에 떨어지면 CDaR 비를 아예 안 낸다(사양)."""
    g, r = out["gate"], out["ranking"]

    def num(v, w, f):
        return f"{v:{w}{f}}" if v is not None else f"{'—':>{w}}"

    print(f"  {label:24s} {num(g['dsr'], 8, '.4f')} {num(g['pbo'], 8, '.4f')} "
          f"{num(r['cdar_ratio'], 8, '.3f')}  "
          f"{'통과' if g['overall_pass'] else '미통과'}")


def _measure(name: str, out: dict | None) -> None:
    """북 한 판의 회전율·비용 — 두 북에 **같은 자**를 댄다."""
    if out is None:
        print(f"  ⚠ {name}: 그 레인이 이 트리에 없어요 — 못 쟀습니다.")
        return
    pts, pos, dates = out["points"], out["pos"], out["dates"]
    n = len(pts)
    years = n / 252
    net = sum(p["dailyPnl"] for p in pts)
    # ⚠ **`barCost` 의 부호 규약이 두 엔진에서 반대다.** MR(`mrbacktest`)은 음수로
    # 싣고(`paid = -sum(barCost)`) CTA(`ctabacktest`)는 **양수**로 싣는다
    # (`"barCost": -cost`, cost <= 0). 한 자로 견주는 자리에서 이걸 안 보면 비용이
    # 손익에서 **두 번 빠지거나** 더해져 조용히 틀린다 — 그래서 절댓값으로 센다.
    paid = abs(sum(p["barCost"] for p in pts))
    gross = net + paid
    turns, avg_face = turnover(pos, n, years)
    print(f"  {name}")
    print(f"    {dates[0]}~{dates[-1]} · {n}봉 · {years:.2f}년")
    print(f"    순손익 {net:,.0f}원 · 비용 {paid:,.0f}원 · 비용전 {gross:,.0f}원")
    print(f"    비용/비용전 = {paid / abs(gross) * 100:.1f}%")
    print(f"    평균 |액면|(포지션 선 날) {avg_face:,.0f}원 · "
          f"**연 회전 {turns:.2f}회(편도)**")


def main() -> int:
    print("── 틱 → bp ─────────────────────────────────────────────")
    for t in futures.FUT_TENORS:
        bp, y, f1 = tick_to_bp(t)
        print(f"  {t}: 내재 {y:.3f}% · DV01 1원/bp 액면 {f1:,.0f}원 "
              f"→ 편도 0.5틱 = **{bp:.3f}bp**")
    print(f"  MR 은 편도 {MR_COST_BP}bp — 스프레드 패키지(국고+IRS) 기준")

    print()
    print("── CTA 북 실측 ─────────────────────────────────────────")
    _measure("등록된 북(룩백 다섯 · 북 변동성 목표) — 이것이 이 데스크의 CTA 다",
             registered_book())
    print()
    _measure("엔진 기본 인자 북(룩백 둘) — 처음 보고한 수가 이것이었다",
             cta_book())
    verdicts_by_cost()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
