# -*- coding: utf-8 -*-
"""MR 다리 하나를 **평가층**에 태운다 — 수익 계열·시행수·칸 행렬을 만들어 준다.

    python -m scripts.mr_evaluate BSS-10Y            # 한 다리
    python -m scripts.mr_evaluate --all              # BSS 아홉

## 평가 단위는 **다리 하나**다 [OWNER 2026-09-09]

통합 장부로 재면 「고르는 행위」가 없어져 깎을 것이 거의 없고 전부 통과한다.
오너는 **다리 하나**를 단위로 정했다 — 그러면 「왜 이 만기였나」가 시행수에 들어가고,
게이트가 그만큼 엄해진다. 이 스크립트는 그 결정을 그대로 집행한다.

## 자본 기준 = **액면(원금)** [OWNER 2026-09-09]

이 데스크에 AUM 이 없어서 수익률의 분모를 정해야 했다. 거래마다 **진입일 커브**로
환산한 액면이 그 답이고, 그래서 봉마다의 수익률은

    r[i] = 그날 손익(₩) / 그 봉에 물려 있던 액면(₩)          (무포지션이면 0)

이다. 액면은 `_mr_principal_at`(진입일 커브)이 재고, 이 스크립트가 그것을 봉에
펴 바른다 — 평가층 안에서 다시 나누지 않는다(자본 기준이 두 곳에 살면 안 된다).

## 정직한 시행수 N

    룩백 3 × 진입σ 3 × 청산σ 3 × 손절σ 3 × 진입규칙 2 = 162칸
    × 계열 고르기 (BSS 아홉)                          = 1,458

**손잡이 셋(룩백·진입σ·청산σ)은 데이터로 고른 게 아니다** [OWNER 2026-09-09 —
「60일/2σ/0.5σ 는 딱히 데이터 보고 정한 건 아님」]. 그래서 그 셋은 빠진다.
**손절σ 는 들어간다** [OWNER 2026-09-09 — 「탐색한 축이다」]: 2026-09-08 에 프리셋을
갈고 09-09 에 기본값을 옮긴 근거가 예산 안 실측이었으므로, 자료를 보고 고른 값이다.

    N = 손절 3 × 진입규칙 2 × 계열 9 = 54            (기본값)

`--trials` 로 덮어쓸 수 있다. 무엇을 셌는지는 보고서의 「가정」에 적힌다.

## 칸 행렬(PBO)

CSCV 는 **T × 칸** 행렬을 먹는다. 격자 라우트(`/api/mr/optimize`)는 칸마다 지표만
주고 계열을 안 주므로, 여기서는 엔진을 직접 돌려 칸마다 일별 손익을 만든다.
★**격자와 카드가 다른 자다**(인계문 §11-1) — 격자는 엔진 근사 회계, 카드는 실가격
회계다. 그래서 이 스크립트는 **양쪽을 같은 자로** 맞춘다: 수익 계열도 칸 행렬도
전부 **엔진 회계**로 만든다. 순위를 매긴 자와 보고한 자가 다르면 PBO 가 재는 것이
없어지기 때문이다. 그 사실은 보고서의 「가정」에 적힌다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import mr as mr_mod                                   # noqa: E402
from app import mrbacktest as bt                               # noqa: E402
from app import mrcarry as mrc                                 # noqa: E402
from app import mrseries as mrs                                # noqa: E402
from app import funding as fnd                                 # noqa: E402
from evaluation import metrics as ev, report                   # noqa: E402

#: 화면 기본 노브 — 「지금 화면이 말하는 그 전략」을 재는 것이 이 스크립트의 일이다.
BASE = dict(lookback=60, entryZ=2.0, exitZ=0.5, stopZ=2.5, costBp=0.5,
            notional=1_000_000.0, entryMode="level")

#: 시행으로 세는 축 — **자료를 보고 고른 것만**(모듈 머리의 그 셈).
SEARCHED = {"stopZ": mr_mod.STRATEGY_PRESETS["stopZ"],
            "entryMode": ["level", "touch"]}


def _leg_inputs(sid: str):
    """(날짜, bp 값, 캐리 ₩/봉) — 라우트의 `_mr_leg` 와 **같은 유도**를 쓴다.

    ★**표본도 라우트와 같게 자른다**(`_mr_reconcilable`). 값 계열 자체는 2014-05
    부터 있는데 화면은 민평 이력(2020-01-02~)으로 잘라서 보여 준다 — 「화면이
    보여 주는 것은 전부 대사할 수 있어야 한다」는 그 규율이다. 여기서 안 자르면
    **화면이 안 보여 주는 6년**을 같이 재게 되고, 그러면 이 판정이 화면의 그
    전략에 대한 판정이 아니게 된다(실측: 안 자르면 3,022봉 · SR 연 −0.03,
    자르면 1,647봉 · SR 연 +0.90 — 판정이 통째로 갈린다).
    """
    from app.main import _mr_reconcilable

    body = mr_mod.series_points(sid)
    kind = {s: k for s, _l, k in mr_mod.SERIES}[sid]
    pts = [p for p in body["points"] if p.get("v") is not None]
    pts = _mr_reconcilable(pts, kind)
    dates = [p["t"] for p in pts]
    scale = 100.0 if body["unit"] == "%" else 1.0
    vals = [float(p["v"]) * scale for p in pts]
    spec = fnd.FundingSpec(basis=fnd.DEFAULT_BASIS, spread_bp=fnd.DEFAULT_SPREAD_BP)
    rates, _defn = mrc.carry_rates(sid, kind, dates, spec)
    from app.dv01 import pv01
    from app.curves import TENOR_T
    from app.main import _curves
    pv = pv01(_curves["now"], TENOR_T[mrc._tenor_of(sid)])
    carry = mrc.carry_krw(rates, dates, notional_per_bp=BASE["notional"], pv01=pv)
    face = BASE["notional"] / (pv * 1e-4)
    return dates, vals, carry, face


def _run(dates, vals, carry, **over) -> dict:
    p = {**BASE, **over}
    return bt.simulate(dates, vals, lookback=p["lookback"], entry_z=p["entryZ"],
                       exit_z=p["exitZ"], stop_z=p["stopZ"], cost_bp=p["costBp"],
                       notional=p["notional"], allow_dirs=(-1,), carry=carry,
                       entry_mode=p["entryMode"])


def returns_of(r: dict, face: float) -> pd.Series:
    """봉의 손익(₩) → **액면 대비 수익률**. 무포지션 봉은 0 이다."""
    return pd.Series([p["dailyPnl"] / face for p in r["points"]])


def config_matrix(dates, vals, carry, face) -> pd.DataFrame:
    """칸마다의 수익 계열 — CSCV 가 먹는 T × 칸.

    **탐색한 축만** 흔든다(모듈 머리의 N). 안 흔든 축까지 넣으면 PBO 가 「고르지도
    않은 자유도」로 벌하게 되고, 그건 이 지표가 답하는 물음이 아니다.
    """
    cols: dict[str, list[float]] = {}
    for sz in SEARCHED["stopZ"]:
        for md in SEARCHED["entryMode"]:
            r = _run(dates, vals, carry, stopZ=sz, entryMode=md)
            cols[f"stop{sz}-{md}"] = [p["dailyPnl"] / face for p in r["points"]]
    return pd.DataFrame(cols)


def evaluate_leg(sid: str, trials: int | None = None,
                 splits: int = 16) -> dict:
    dates, vals, carry, face = _leg_inputs(sid)
    base = _run(dates, vals, carry)
    rets = returns_of(base, face)
    mat = config_matrix(dates, vals, carry, face)
    n = trials if trials is not None else (
        len(SEARCHED["stopZ"]) * len(SEARCHED["entryMode"])
        * len([1 for _s, _l, k in mr_mod.SERIES if k == "bss"]))
    #: 격자 칸들의 SR 분산 — 있으면 SR0 가 「이 격자에서 뽑기로 나오는 최고」가 된다.
    sr_var = float(((mat.mean() / mat.std(ddof=1)).dropna()).var(ddof=1))
    out = ev.evaluate(
        rets, trials=n, is_oos_splits=splits, configs=mat,
        sr_var=sr_var if sr_var > 0 else None,
        strategy_id=sid,
        cost_bp_roundtrip=BASE["costBp"] * 2,
        assumptions=[
            f"자본 기준 = 액면 {face:,.0f}원(지금 커브의 pv01 하나 — 진입일마다 "
            f"다시 재면 표본 안에서 5~16% 움직인다).",
            "평가 단위 = **다리 하나** [OWNER 2026-09-09]. 통합 장부로 재면 "
            "고르는 행위가 없어져 게이트가 헐거워진다.",
            "시행수 N 에 룩백·진입σ·청산σ 는 **안 넣었다** [OWNER — 「데이터 보고 "
            "정한 건 아님」]. 손절σ·진입규칙·계열 고르기만 셌다.",
            "수익 계열과 칸 행렬을 **둘 다 엔진 회계**로 만들었다 — 화면 상단 카드는 "
            "실가격 회계라 그 수와 다르다(같은 설정에서 Calmar 0.576 대 0.623). "
            "순위를 매긴 자와 보고한 자가 같아야 PBO 가 뜻을 갖는다.",
            f"표본 {dates[0]}~{dates[-1]} · {len(dates)}봉.",
        ])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sid", nargs="?", default="BSS-10Y")
    ap.add_argument("--all", action="store_true", help="BSS 아홉 만기 전부")
    ap.add_argument("--trials", type=int, default=None)
    ap.add_argument("--splits", type=int, default=16)
    a = ap.parse_args()

    ids = [s for s, _l, k in mr_mod.SERIES if k == "bss"] if a.all else [a.sid]
    print(f"{'계열':14s} {'DSR':>8s} {'PBO':>8s} {'CDaR비':>8s}  판정   보고서")
    for sid in ids:
        out = evaluate_leg(sid, a.trials, a.splits)
        g, r = out["gate"], out["ranking"]
        path = report.write(out)
        print(f"{sid:14s} {g['dsr'] or float('nan'):8.4f} "
              f"{(g['pbo'] if g['pbo'] is not None else float('nan')):8.4f} "
              f"{(r['cdar_ratio'] if r['cdar_ratio'] is not None else float('nan')):8.3f}  "
              f"{'통과' if g['overall_pass'] else '미통과'}   {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
