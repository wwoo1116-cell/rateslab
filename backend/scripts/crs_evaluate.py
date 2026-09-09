# -*- coding: utf-8 -*-
r"""**증거금 상한 아래의** BSS 통합 장부를 평가층에 태운다 — 세 번째 소비자.

    python -m scripts.crs_evaluate                 # 등록 예정 칸(로트 50억)
    python -m scripts.crs_evaluate --lots          # 로트 여섯 칸 전부

## 왜 이 자리가 필요한가

이 데스크의 세 레인이 같은 문장에서 막혀 있었다 — 「**MR 장부는 상한 무시판이라
누가 큰지 말할 수 없다**」(`HANDOFF-momentum` §11-1 · `EVAL_LANE_STATE` §10-③ ·
`krw-crs` 인계문). MR 통합 SR 1.74 는 증거금이 무한하다는 판의 수이고, 상한
(≤3Y 5% · >3Y 10% · 합 100억) 아래로 넣으면 그 수가 안 선다.

그 상한판은 **`krw-crs` 레인이 이미 지어 놨다**(`src/margin_budget_book.py`).
없던 것은 그 장부를 **같은 게이트**에 올리는 자리뿐이라, 이 파일이 그 자리다.
`momentum_evaluate` 와 같은 규율을 진다 — **남의 레인 코드를 여기서 고치지 않고**
그쪽 모듈을 그대로 불러 쓴다.

## ⚠ 이것은 그 레인의 «판정 I» 이 아니다

`PREREG_03_book_2026-09-09.md` 는 **아직 얼지 않았다**(「오너가 동결을 선언하면
그때부터 §7 의 실행을 한 번만 돌린다」). 그리고 `margin_budget_book` 자신이 머리에
**「★탐색적 — 사전등록 아님」** 이라고 적어 두고 있다. 그러니 여기서 나오는 수는
그 레인이 이미 자유롭게 하고 있는 **탐색적 측정**이지 사전등록의 판정이 아니다.
그 사실은 보고서의 「가정」 맨 앞에 적힌다.

## 시행수 N = 50 — **그 레인이 이미 세어 둔 값이다**

내가 세지 않는다. `PREREG_03` §5.1 이 이렇게 적어 뒀다:

    배분 격자   규칙 5 × 로트 5                              = 25
    로트 격자   margin_budget_book 의 {100,50,33,25,20,11}   =  6
    손절 축     {2.10 … 4.0, 없음}                           =  8
    …                                                       → 50

「격자들이 겹쳐 50 은 실제 독립 시행보다 크다 — **더 크게 세는 쪽이 보수적**이라
그대로 쓴다」는 그 문서의 말도 그대로 따른다. `--trials` 로 덮어쓸 수 있다.

## 자본 기준은 여기서 **진짜로 있다**

MR 다리 자리는 AUM 이 없어서 액면을 분모로 삼았고 모멘텀 자리는 아예 분모를 안
만들었는데, 이 장부는 **자본이 100억으로 정해져 있다.** 그래서 수익률이 그냥
`그날 순손익 / 100억` 이다 — 이 레인에서 처음으로 분모가 가정이 아니다.

## ★자본비용을 어디에 물리나 — **판정이 여기서 갈린다**

두 규약이 살아 있고 둘이 같은 장부를 다르게 채점한다.

    전액(CAP)   100억 전부에 기준+10bp 를 연중 — `margin_budget_book.main()` 이 그것
    묶인 것만   그날 실제로 잡힌 증거금에만    — [OWNER 2026-09-08] 「BSS 들어가
                                                 있는 동안에만」 · PREREG 2판 #2

평균 사용률이 24% 라 둘의 차이가 작지 않다. **가정하지 말고 둘 다 재고**, 어느
쪽이 옳은지는 그 레인의 사전등록이 정한다(2판은 「묶인 것만」이다).
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation import metrics as ev, report                    # noqa: E402

#: 그 레인이 이 리포 밖에 산다(`Projects\data\krw-crs`). `momentum.THEMES_CSV` 와
#: 같은 사정이고 같은 규율이다 — 없으면 **조용히 0 을 내지 않고** 그 사실을 적는다.
LANE = Path(os.environ.get(
    "KRW_CRS_DIR",
    Path(__file__).resolve().parents[4] / "data" / "krw-crs"))

#: 사전등록 2판이 등록 예정으로 적은 칸. 격자를 본 뒤 고른 칸이고 그 선택 비용은
#: N=50 이 문다(그 문서 §4 의 그 문장).
REGISTERED_LOT_UK = 50

#: 그 레인이 §5.1 에 세어 둔 시행수. 내가 세지 않는다.
TRIALS = 50

FUNDING_MODES = ("bound", "cap")

#: 칸 행렬은 **자본비용 규약에만** 달렸지 어느 칸을 보고하느냐와는 무관하다.
#: 로트 여섯을 훑을 때 같은 행렬을 여섯 번 다시 세우면 서른여섯 판이 된다.
_MATRIX: dict = {}


def _lane():
    """그 레인의 모듈 — 없으면 왜 없는지 말하고 멈춘다."""
    src = LANE / "src"
    if not (src / "margin_budget_book.py").exists():
        raise SystemExit(
            f"증거금 상한 장부를 못 찾았어요 — {src / 'margin_budget_book.py'} 가 "
            f"없습니다. 그 레인이 다른 자리에 있으면 KRW_CRS_DIR 로 알려 주세요.")
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    import margin_budget_book as mb           # noqa: PLC0415
    return mb


def base_rate(mb, index) -> pd.Series:
    """기준금리(연, 소수) — 그 레인이 `main()` 에서 읽는 그 파일이다."""
    path = (LANE.parents[1] / "research" / "krw-bss-r0" / "data" / "real"
            / "krw_bss_tenors.csv")
    if not path.exists():
        raise SystemExit(f"기준금리 계열을 못 찾았어요 — {path}")
    mk = pd.read_csv(path, parse_dates=["date"]).set_index("date")
    return mk["bok_base"].reindex(index).ffill() / 100.0


def net_returns(mb, lot_uk: int, funding: str) -> tuple[pd.Series, dict]:
    """(자본 대비 일별 순수익률, 그 판의 사실들).

    `simulate` 가 주는 `daily` 는 **전략 손익**(엔진 봉이라 체결비용은 이미 빠져
    있다)이고, 자본비용은 여기서 뺀다 — 어디에 물리느냐가 인자다.
    """
    if funding not in FUNDING_MODES:
        raise SystemExit(f"자본비용 규약은 {FUNDING_MODES} 중 하나예요")
    P, L, Z, meta = mb.load()
    daily, used, dv01, entered, blocked = mb.simulate(P, L, Z, meta, lot_uk)
    base = base_rate(mb, P.index)
    rate = (base + 0.001) / mb.DAYS
    # 「묶인 것만」 = 그날 실제로 잡힌 증거금(= 사용률 × 자본)에만 문다.
    charged = mb.CAP * (used if funding == "bound" else 1.0)
    net = daily - rate * charged
    facts = {"bars": len(net), "entered": entered, "blocked": blocked,
             "use_mean": float(used.mean()), "use_max": float(used.max()),
             "start": str(P.index.min().date()), "end": str(P.index.max().date()),
             "dv01_live": float(dv01[dv01 > 0].mean()) if (dv01 > 0).any() else None}
    return net / mb.CAP, facts


def config_matrix(mb, funding: str) -> pd.DataFrame:
    """칸 = **로트 격자 여섯**(그 레인이 결과 보기 전 고정한 그 격자).

    ⚠ 여섯뿐이라 CSCV 의 순위 공간이 거칠다. 배분 규칙 다섯까지 칸으로 세우면
    스물다섯이 되는데 그 격자를 만드는 것은 그 레인의 `alloc_grid.py` 이고
    여기서 그 규칙을 다시 구현하면 **재구성이 두 곳에 살게 된다** — 그래서 안 한다.
    """
    if funding in _MATRIX:
        return _MATRIX[funding]
    cols = {}
    for lot in mb.LOTS_UK:
        r, _f = net_returns(mb, lot, funding)
        cols[f"lot{lot}"] = r
    _MATRIX[funding] = pd.DataFrame(cols).dropna()
    return _MATRIX[funding]


def evaluate_lot(lot_uk: int = REGISTERED_LOT_UK, *, funding: str = "bound",
                 trials: int | None = None, splits: int = 16) -> dict:
    mb = _lane()
    rets, facts = net_returns(mb, lot_uk, funding)
    mat = config_matrix(mb, funding)
    sr_var = float(((mat.mean() / mat.std(ddof=1)).dropna()).var(ddof=1))
    charged = "그날 묶인 증거금에만" if funding == "bound" else "자본 100억 전액 연중"
    return ev.evaluate(
        rets.reset_index(drop=True), trials=trials if trials is not None else TRIALS,
        is_oos_splits=splits, configs=mat,
        sr_var=sr_var if sr_var > 0 else None,
        strategy_id=f"CRS-lot{lot_uk}-{funding}",
        cost_bp_roundtrip=1.0,
        assumptions=[
            "⚠ **그 레인의 «판정 I» 이 아니다.** `PREREG_03_book_2026-09-09.md` 는 "
            "아직 안 얼었고, 이 장부(`margin_budget_book`)는 자기 머리에 «탐색적 — "
            "사전등록 아님» 이라고 적어 두고 있다. 여기 수는 탐색적 측정이다.",
            f"자본 기준 = **100억**(가정이 아니라 그 레인의 제약이다). 증거금률 "
            f"≤3Y 5% · >3Y 10% · 합 ≤ 100억, 로트 {lot_uk}억, 우선순위 |z| 큰 순.",
            f"자본비용 = 기준금리+10bp 를 **{charged}** 물렸다. 두 규약이 살아 있어 "
            f"(PREREG 2판이 「묶인 것만」으로 바꿨다) 판정이 갈릴 수 있는 자리라 "
            f"`--funding` 으로 둘 다 잰다. 이 판의 평균 사용률 "
            f"{facts['use_mean']:.0%} · 최대 {facts['use_max']:.0%}.",
            f"시행수 N = {trials if trials is not None else TRIALS} — **그 레인이 "
            f"`PREREG_03` §5.1 에 세어 둔 값**이다(배분 25 + 로트 6 + 손절 8 …). "
            f"겹쳐서 실제 독립 시행보다 크지만 「크게 세는 쪽이 보수적」이라 그대로 쓴다.",
            f"칸 {mat.shape[1]}개 = 로트 격자 {list(mb.LOTS_UK)}억(결과 보기 전 고정). "
            f"배분 규칙 다섯은 안 세웠다 — 그 격자는 그 레인의 `alloc_grid.py` 것이고 "
            f"여기서 다시 구현하면 재구성이 두 곳에 산다.",
            f"체결비용은 계열에 **이미 들어 있다**(엔진 봉) — 그 레인이 편도 0.5bp 로 "
            f"높게 잡아 마크 할인을 대신하고 있다 [OWNER 2026-09-09].",
            f"표본 {facts['start']}~{facts['end']} · {facts['bars']}봉 · "
            f"진입 {facts['entered']}건 · 증거금이 없어 막힌 신호 {facts['blocked']}건.",
        ])


def compare(splits: int = 16) -> None:
    """★**두 레인의 «수준» 을 처음으로 견준다** — 상한판 MR 대 모멘텀 50/50.

    이 비교가 지금까지 막혀 있던 이유는 하나였다: MR 쪽 수(통합 SR 1.74)가
    **증거금이 무한한 판**의 것이라 「누가 크냐」를 물을 수 없었다. 상한판이 서면
    그 질문이 처음으로 성립한다.

    셋을 맞춰야 같은 자다 — **창 · 위험 · 자기상관.**

    창    두 계열의 **교집합**만 쓴다(모멘텀은 2017-01 부터, 상한판은 2020-01 부터).
    위험  CDaR 비는 계열을 목표 변동성에 맞춘 뒤 재므로 크기 차이가 지워진다.
          그래서 원(₩) 계열과 비율 계열을 나란히 놓아도 된다.
    자기상관  √252 곱셈은 날들이 독립일 때만 맞다. MR 은 AR(1) 이 양수고 모멘텀은
          음수라 **한쪽만 부푼 자**가 된다 — Lo(2002) 를 둘 다에 건다.
    """
    from evaluation.metrics import cdar_ratio, sharpe_lo, vol_normalize

    mb = _lane()
    crs, facts = net_returns(mb, REGISTERED_LOT_UK, "bound")
    crs.index = [d.date().isoformat() for d in crs.index]

    try:
        from scripts import momentum_evaluate as me
    except ImportError:
        print("  ⚠ 모멘텀 레인이 이 트리에 없어 못 견줬습니다.")
        return
    series, rolls, macro = me._inputs()
    if macro is None:
        print("  ⚠ 매크로 신호가 없어 50/50 을 못 세웠습니다.")
        return
    legs = me.legs_of(series, rolls, macro, cache={})
    mom = me.returns_of(legs["blend"])

    common = sorted(set(crs.index) & set(mom.index))
    a, b = crs.loc[common], mom.loc[common]
    print()
    print("── 수준 비교 — 공통 창·같은 자 ─────────────────────────")
    print(f"  창 {common[0]}~{common[-1]} · {len(common)}봉 "
          f"(상한판 {len(crs)}봉 · 모멘텀 {len(mom)}봉의 교집합)")
    print(f"  {'':22s} {'연SR':>8s} {'AR(1)':>8s} {'AR보정':>8s} {'CDaR비':>8s}")
    for name, r in (("MR 증거금 상한판", a), ("Momentum 50/50", b)):
        sr = float(r.mean() / r.std(ddof=0) * math.sqrt(252))
        ar = float(r.autocorr(lag=1))
        lo = sharpe_lo(r)
        cd = cdar_ratio(vol_normalize(r.reset_index(drop=True))[0])["cdar_ratio"]
        print(f"  {name:22s} {sr:8.3f} {ar:8.3f} "
              f"{(lo if lo is not None else float('nan')):8.3f} "
              f"{(cd if cd is not None else float('nan')):8.3f}")
    print()
    print("  ⚠ 게이트는 별개다 — 이 표는 «수준» 이지 판정이 아니다. 상한판은 PBO 로,")
    print("     모멘텀은 DSR 로 떨어져 있고 그 사실이 이 수들로 지워지지 않는다.")


def _row(label: str, out: dict, tail: str = "") -> None:
    g, r = out["gate"], out["ranking"]

    def num(v, w, f):
        return f"{v:{w}{f}}" if v is not None else f"{'—':>{w}}"

    print(f"  {label:24s} {num(g['dsr'], 8, '.4f')} {num(g['pbo'], 8, '.4f')} "
          f"{num(r['cdar_ratio'], 8, '.3f')}  "
          f"{'통과' if g['overall_pass'] else '미통과'}{tail}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lot", type=int, default=REGISTERED_LOT_UK)
    ap.add_argument("--lots", action="store_true", help="로트 여섯 칸 전부")
    ap.add_argument("--funding", choices=[*FUNDING_MODES, "both"], default="both")
    ap.add_argument("--trials", type=int, default=None)
    ap.add_argument("--splits", type=int, default=16)
    ap.add_argument("--vs", action="store_true",
                    help="상한판 MR 과 모멘텀 50/50 의 수준 비교")
    a = ap.parse_args()

    if a.vs:
        compare(a.splits)
        return 0

    mb = _lane()
    lots = list(mb.LOTS_UK) if a.lots else [a.lot]
    modes = list(FUNDING_MODES) if a.funding == "both" else [a.funding]

    print(f"{'칸/자본비용':24s} {'DSR':>8s} {'PBO':>8s} {'CDaR비':>8s}  판정   보고서")
    for funding in modes:
        for lot in lots:
            out = evaluate_lot(lot, funding=funding, trials=a.trials,
                               splits=a.splits)
            path = report.write(out)
            _row(f"로트 {lot}억 · {funding}", out, tail=f"   {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
