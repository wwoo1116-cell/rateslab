# -*- coding: utf-8 -*-
r"""집행 준비 ① — 실측 커브 pv01 로 액면을 잡는다 [OWNER 2026-09-15 「얼리고 집행준비 시작」].

    python -m scripts.sleeve_execution              # 대조표 + 오늘의 집행표
    python -m scripts.sleeve_execution --ticket     # 집행표만

## 왜

동결 등록서(`docs/PREREG_sleeve_5050_2026-09-15.md`)의 액면·증거금 수는 **pv01 근사식**
(명목 × 만기 × 1e-4)으로 세웠다. 등록한 것은 «위험 배분»(w 0.25 · 총위험 고정)이라 근사가
등록을 흔들지는 않지만, **집행 규모는 그날 커브로 잡아야 한다.** 이 스크립트가 그 자리다.

    근사     pv01(3Y) = 3.0e4 ₩/bp per 1억 · pv01(10Y) = 10.0e4
    실측     `app.dv01.pv01(zc, T)` — `mkt_irs_close` 전 만기로 부트스트랩한 제로커브의 파스왑 애뉴이티

액면 = |DV01| / pv01 × 1억. pv01 이 크면 같은 DV01 에 액면이 **적게** 든다. 근사가 pv01 을
과대평가하면 액면을 과소 계상하는 셈이라 증거금이 예상보다 더 든다 — 그래서 방향이 중요하다.

## 무엇을 내나

  ① 대조    2017~2026 전 영업일의 근사 대 실측 pv01, 액면·증거금 차이의 분포
  ② 집행표  마지막 영업일의 다섯 북 포지션 → 만기별 순 DV01 → 실측 액면 → 증거금
            **채점 시작일(2026-09-16)에 세울 북이 이것이다.**

⚠ 이 스크립트는 등록서를 고치지 않는다. 등록서 §4 가 「집행 배관이 서면 부기하되 W0~W6 은
   고치지 않는다」고 적어 두었다.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app import momentum as mo                                  # noqa: E402
from app.dv01 import pv01                                       # noqa: E402
from app.engine_port import bootstrap_zero_curve                # noqa: E402
from scripts import crs_evaluate as ce                          # noqa: E402
from scripts import hedge_test as ht                            # noqa: E402
from scripts import macro_paper_fix as mp                       # noqa: E402
from scripts import momentum_irs_evaluate as mie                # noqa: E402
from scripts import momentum_irs_legs as ml                     # noqa: E402
from scripts import momentum_irs_books as mib                   # noqa: E402
from scripts import sleeve_margin as sg                         # noqa: E402
from scripts.momentum_theme_books import pnl_of                 # noqa: E402

ANN = 252
W = 0.25
RATE = 0.05
CAP = 100e8
BOOKS = ("trend", "cycle", "policy", "trade", "risk")
BW = {"trend": 0.5, "cycle": 0.125, "policy": 0.125, "trade": 0.125, "risk": 0.125}

#: `mkt_irs_close` 의 만기 열 → 연수. `app.curves.TENOR_T` 와 같은 눈금이다.
COLS = {"irs_6m": 0.5, "irs_9m": 0.75, "irs_1y": 1.0, "irs_18m": 1.5, "irs_2y": 2.0,
        "irs_3y": 3.0, "irs_4y": 4.0, "irs_5y": 5.0, "irs_6y": 6.0, "irs_7y": 7.0,
        "irs_8y": 8.0, "irs_9y": 9.0, "irs_10y": 10.0}
LEG_T = {"3Y": 3.0, "10Y": 10.0}


def real_pv01() -> pd.DataFrame:
    """날짜별 3Y·10Y 실측 pv01(₩/bp per 1억). 커브가 빈 날은 그날을 건너뛴다."""
    cols = ", ".join(COLS)
    with mie.engine().connect() as conn:
        rows = conn.execute(text(
            f"SELECT irs_date, {cols} FROM mkt_irs_close ORDER BY irs_date ASC")).fetchall()
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        d = r[0]
        day = (d.date() if hasattr(d, "date") else d).isoformat()
        pars = [(COLS[c], float(v) / 100.0) for c, v in zip(COLS, r[1:]) if v is not None]
        if len(pars) < 6:
            continue
        zc = bootstrap_zero_curve(sorted(pars))
        #: `pv01()` 은 **애뉴이티(연 단위)** 다. ₩/bp 로 바꾸려면 명목 × 1e-4 를 곱한다.
        #: 근사식(`sleeve_margin.pv01_per_100m`)이 만기를 애뉴이티로 쓰는 것과 같은 자리다.
        out[day] = {k: pv01(zc, t) * 1e8 * 1e-4 for k, t in LEG_T.items()}
    return pd.DataFrame(out).T.sort_index()


def sleeve_dv01_path():
    """다섯 북의 만기별 DV01(₩/bp) 경로와 총위험 고정 배수.

    ★두 창이 **다른 물음**이라 다른 끝을 쓴다 [2026-09-17].

        신호·DV01 경로   `end=None` — 자료가 있는 마지막 봉까지. 오늘 세울 북을 묻는다.
        크기(vol·배수)   `mo.FREEZE` 까지 — 동결 창. **규칙을 만든 자료**를 묻는다.

    둘을 한 끝으로 묶으면 둘 중 하나가 틀린다. 09-16 까지는 신호 쪽이 09-08 에 묶여
    있어서 슬리브가 채점 봉을 한 개도 못 쌓았다.

    ★배수는 `sleeve_monitor` 의 **등록 상수**를 쓴다. 여기서 다시 계산한 값은 버리지
    않고 `meta["mult_live"]` 로 같이 돌려준다 — 갈리면 표에 보인다.
    """
    from scripts import sleeve_monitor as sm_    # noqa: PLC0415  순환 import 회피

    series = mie.load_irs_series(end=None)
    sig = mib.registered_signals(series)         # ★IRS 달력 이월 포함 — 한 자리
    t_book = ml._book(series, signal=mo.SIGNAL, vol_window=mo.VOL_WINDOW)
    m_books = mib.macro_books(series, sig, mo.VOL_WINDOW)
    books = {"trend": t_book, **m_books}
    dates = [str(x)[:10] for x in t_book["dates"]]
    start = mib.start_of(sig)
    blend = sum(BW[b] * pnl_of(books[b]) for b in BOOKS)
    blend.index = [str(x)[:10] for x in blend.index]
    blend = blend[(blend.index >= start) & (blend.index <= mo.FREEZE)]
    vol_sleeve = float(blend.std(ddof=1) * math.sqrt(ANN))

    mb = ce._lane()
    net, _facts = ce.net_returns(mb, ce.REGISTERED_LOT_UK, "bound")
    mr = ht.mr_returns()
    mr_vol_krw = float(net.std(ddof=1) * math.sqrt(ANN) * mb.CAP)
    idx = sorted(set(mr.index) & set(blend.index))
    m = ht.unit_vol(mr.loc[idx]).to_numpy()
    t = ht.unit_vol(blend.loc[idx]).to_numpy()
    s_mix = float(((1 - W) * m + W * t).std(ddof=1) * math.sqrt(ANN))
    k_mr, k_tr = (1 - W) / s_mix, W / s_mix
    #: 오늘 자료로 다시 세면 이것 — **쓰지 않는다.** 대조로만 들고 간다.
    mult_live = (k_tr * mr_vol_krw) / vol_sleeve
    mult = sm_.MULT_REGISTERED

    per = {}
    for b in BOOKS:
        per[b] = pd.DataFrame({k: np.asarray(books[b]["pos"][k], dtype=float) / 100.0 * BW[b] * mult
                               for k in LEG_T}, index=dates)
    net_dv = sum(per.values())
    #: ⚠ 매크로 신호는 IRS 종가보다 **하루 늦게** 끝난다(테마 입력이 T−1 까지). 그 날 거시 북 넷은
    #: 엔진에서 조용히 0 이 된다(`ext.get(day, 0.0)`). 룩어헤드는 아니지만 **집행표를 그날로 찍으면
    #: 거시 다리가 없는 북을 세우게 된다.** 신호가 선 마지막 날을 같이 돌려준다.
    live = sorted(set().union(*(set(v.index.strftime("%Y-%m-%d")) for v in sig.values())))
    return per, net_dv, {"mult": mult, "mult_live": mult_live,
                         "k_mr": sm_.K_MR_REGISTERED, "k_tr": sm_.K_TR_REGISTERED,
                         "k_mr_live": k_mr, "k_tr_live": k_tr, "s_mix": s_mix,
                         "vol_sleeve": vol_sleeve, "mr_vol_krw": mr_vol_krw, "mb": mb,
                         "signal_last": live[-1]}


def asof_for(ix: list[str], meta: dict) -> str:
    """집행표·주문표가 **같이 쓰는** 기준일 — 신호가 선 마지막 날 [§10-10].

    매크로 신호는 IRS 종가보다 하루 늦게 끝난다(테마 입력이 T−1 까지). 그 하루로
    표를 찍으면 거시 북 넷이 엔진에서 조용히 0 이 되고(`ext.get(day, 0.0)`), 추세
    한 다리만 선 북을 「오늘의 목표」로 내놓게 된다. 09-16 까지는 두 표가 다 09-08
    에 묶여 있어서 이 자리가 안 보였다 — 라이브로 풀리는 순간부터 매일 걸린다.
    """
    sl = meta["signal_last"]
    return sl if sl in ix else ix[-1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticket", action="store_true", help="집행표만 찍는다")
    a = ap.parse_args()

    rp = real_pv01()
    approx = sg.pv01_per_100m()
    per, net_dv, meta = sleeve_dv01_path()
    ix = [d for d in net_dv.index if d in rp.index]
    rp = rp.loc[ix]
    net_dv = net_dv.loc[ix]

    if not a.ticket:
        print()
        print(f"── ① pv01 대조 (근사 대 실측 · {len(ix):,}일 {ix[0]}~{ix[-1]}) ──")
        print(f"  {'만기':5s} {'근사':>10s} {'실측 평균':>10s} {'최소':>9s} {'최대':>9s} {'근사/실측 평균':>13s}")
        for k in LEG_T:
            r = rp[k]
            print(f"  {k:5s} {approx[k]/1e4:9,.1f}만 {r.mean()/1e4:9,.1f}만 {r.min()/1e4:8,.1f}만 "
                  f"{r.max()/1e4:8,.1f}만 {approx[k]/r.mean():13.3f}")
        worse = [k for k in LEG_T if rp[k].mean() < approx[k]]
        print(f"  ★실측이 근사보다 작은 만기: {worse or '없음'} — 작으면 같은 DV01 에 액면이 **더** 든다.")

        face_ap = sum(net_dv[k].abs() / approx[k] * 1e8 for k in LEG_T)
        face_rl = sum(net_dv[k].abs() / rp[k] * 1e8 for k in LEG_T)
        #: 액면이 0 인 날(다섯 북의 순 DV01 이 두 다리 다 0)은 비율이 정의되지 않는다 — 빼고 센다.
        ok = face_ap > 0
        diff = (face_rl[ok] / face_ap[ok] - 1.0)

        #: ⚠ 등록서 W4 의 수(2.09 / 9.88억 · 22일)는 **MR 달력과 겹치는 창**(1,646봉)에서 나왔다.
        #: 여기 대조는 슬리브 전 창(2,389봉)이라 평균이 다르다 — 나란히 놓으려면 같은 창으로 자른다.
        mb = meta["mb"]
        P, L, Z, m_ = mb.load()
        _d, used, _dv, _e, _b = mb.simulate(P, L, Z, m_, ce.REGISTERED_LOT_UK)
        u = pd.Series(used.to_numpy(dtype=float), index=[str(x)[:10] for x in used.index])
        both = [d for d in ix if d in u.index]
        print()
        print(f"  전 창({len(ix):,}봉) 액면  근사 평균 {face_ap.mean()/1e8:6.2f}억 · 실측 평균 {face_rl.mean()/1e8:6.2f}억"
              f"  → **{diff.mean():+.1%}** (5~95백분위 {np.percentile(diff,5):+.1%} ~ {np.percentile(diff,95):+.1%})")
        print(f"  MR 창({len(both):,}봉) 액면  근사 평균 {face_ap.loc[both].mean()/1e8:6.2f}억 · 최대 {face_ap.loc[both].max()/1e8:7.2f}억"
              f"   ← 등록서 W4 의 41.86 / 197.64억")
        print(f"  {'':18s}실측 평균 {face_rl.loc[both].mean()/1e8:6.2f}억 · 최대 {face_rl.loc[both].max()/1e8:7.2f}억")
        print(f"  증거금(실측 · 율 {RATE:.0%}) 평균 {face_rl.loc[both].mean()*RATE/1e8:.2f}억 · 최대 {face_rl.loc[both].max()*RATE/1e8:.2f}억"
              f"   ← 등록서 2.09 / 9.88억")
        tot = u.loc[both].to_numpy() * CAP * meta["k_mr"] + face_rl.loc[both].to_numpy() * RATE
        tot_ap = u.loc[both].to_numpy() * CAP * meta["k_mr"] + face_ap.loc[both].to_numpy() * RATE
        print(f"  합산 증거금이 100억을 넘는 날 실측 **{int((tot > CAP).sum())}일** · 근사 {int((tot_ap > CAP).sum())}일"
              f" / {len(both):,}일 — W4 가 그날을 비례 축소한다")
        #: ★위 수는 **규칙 A 재시뮬**(`margin_budget_book`)의 평균회귀 증거금으로 센 것이고,
        #: 등록서 §4.1 이 인용한 그 수라 **재현되도록 그대로 둔다**. 2026-09-16 부터 W4 집행은
        #: 그 레인의 배분기(규칙 B · 라이브)에서 받으므로, 같은 축을 두 표가 다른 함수로 지나면
        #: 안 된다 — 아래에 **같은 함수로** 한 줄 더 찍는다(`docs/RESULT_margin_source_2026-09-16.md`).
        try:
            from scripts import sleeve_monitor as sm_            # noqa: PLC0415
            alloc, src_ = sm_.mr_margin_path("allocator")
            both_a = [d_ for d_ in both if d_ in alloc.index]
            tot_a = (alloc.loc[both_a].to_numpy() * meta["k_mr"]
                     + face_rl.loc[both_a].to_numpy() * RATE)
            print(f"  같은 셈을 **배분기**(「{src_['rule']}」 · {src_['convention']})로 하면 "
                  f"**{int((tot_a > CAP).sum())}일** / {len(both_a):,}일 — 집행이 쓰는 것은 이쪽이다")
        except SystemExit as e:
            print(f"  ⚠ 배분기 쪽은 못 쟀다 — {e}")

    # ── ② 집행표 ────────────────────────────────────────────────────────
    sl = meta["signal_last"]
    d = asof_for(ix, meta)
    print()
    print(f"── ② 집행표 · 기준일 {d} (채점 시작 2026-09-16 에 세울 북) ──")
    if ix[-1] != d:
        print(f"  ⚠ IRS 종가는 {ix[-1]} 까지 있으나 매크로 신호는 {sl} 까지다 — 그 하루는 거시 북 넷이")
        print(f"     엔진에서 0 이 된다. 집행표는 **신호가 선 마지막 날**로 찍는다.")
    print(f"  총위험 고정 배수 {meta['mult']:.2f} · MR 배수 {meta['k_mr']:.3f} · 슬리브 배수 {meta['k_tr']:.3f}")
    print()
    print(f"  {'북':8s} {'가중':>6s} {'3Y DV01':>12s} {'10Y DV01':>12s}")
    for b in BOOKS:
        print(f"  {b:8s} {BW[b]:6.3f} {per[b].at[d, '3Y']/1e4:11,.1f}만 {per[b].at[d, '10Y']/1e4:11,.1f}만")
    print(f"  {'합(순)':8s} {'':6s} {net_dv.at[d, '3Y']/1e4:11,.1f}만 {net_dv.at[d, '10Y']/1e4:11,.1f}만")
    print()
    print(f"  {'만기':5s} {'순 DV01':>11s} {'실측 pv01':>11s} {'액면':>11s} {'방향':>6s} {'증거금':>9s}")
    tot_face = 0.0
    for k in LEG_T:
        dv = float(net_dv.at[d, k]); p = float(rp.at[d, k])
        face = abs(dv) / p * 1e8
        tot_face += face
        side = "리시브" if dv > 0 else ("페이" if dv < 0 else "없음")
        print(f"  {k:5s} {dv/1e4:10,.1f}만 {p/1e4:10,.1f}만 {face/1e8:10,.1f}억 {side:>6s} {face*RATE/1e8:8,.2f}억")
    print(f"  {'합':5s} {'':11s} {'':11s} {tot_face/1e8:10,.1f}억 {'':6s} {tot_face*RATE/1e8:8,.2f}억")
    print()
    print("  ⚠ 부호 규약: 계열이 **−bp** 라 DV01 이 양(+)이면 금리 하락에 벌고 = **리시브**다.")
    print("  ⚠ 이 표는 기준일 종가 신호다. 실제 집행일에 다시 돌려 그날 커브·신호로 잡는다.")

    out = pd.DataFrame({"pv01_3Y": rp["3Y"], "pv01_10Y": rp["10Y"],
                        "dv01_3Y": net_dv["3Y"], "dv01_10Y": net_dv["10Y"],
                        "face_3Y": net_dv["3Y"].abs() / rp["3Y"] * 1e8,
                        "face_10Y": net_dv["10Y"].abs() / rp["10Y"] * 1e8})
    out["face_total"] = out["face_3Y"] + out["face_10Y"]
    out["margin"] = out["face_total"] * RATE
    p = BACKEND / "output" / "sleeve_execution_daily.csv"
    out.to_csv(p, encoding="utf-8-sig", float_format="%.0f")
    print(f"\n  → {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
