# -*- coding: utf-8 -*-
"""현금채권과 스왑을 **한 북**에 담는 백테스트 [OWNER, 2026-08-21 —
"현금채권이랑 스왑을 섞어서 백테스팅이나 시뮬레이션"].

시뮬레이션은 이미 섞였다 — `app/instruments.py` 가 `CB:`·`ASW:` 를 스왑과 같은
페이로드에 실어 보내고 엔진이 `bondType != "swap"` 갈래로 채권을 값매긴다.
막혀 있던 것은 백테스트였다: 라우트도 엔진도 창도 둘이었고, `CB:KTB:3Y` 를 IRS
쪽에 넣으면 `_validate` 가 `unknown instrument` 로 세웠다.

이 모듈은 **엔진을 새로 쓰지 않는다.** 스왑 줄은 `backtest._run_one`, 채권 줄은
`cashbond.run_bond_position` 이 그대로 값매긴다 — 같은 상품이 두 화면에서 다른
수를 내는 순간 비교가 끝나기 때문이고, 그것이 이 리포가 `instruments.py` 에서
이미 지키고 있는 규칙이다. 여기서 새로 정하는 것은 **어느 날짜 위에서 더하느냐**
하나뿐이다.

── 달력 ────────────────────────────────────────────────────────────────────

두 달력이 다르다. `cashbond.book_recon` 이 이미 이 문제에 답을 내놨다 (그 함수의
주석, 2026-08-14 실측): 두 백테스트를 각자의 달력에서 돌린 뒤 날짜로 합치는 길은
**손익을 흘린다** — IRS 에만 있는 날 9일(12/25·1/1·3/2·5/1·5/5·5/25·6/3·7/17·
12/31), 민평에만 있는 날 3일. 그래서 자산스왑의 스왑 다리를 민평 달력 위에서
직접 값매기는 쪽을 택했다.

혼합 북도 같은 규칙이다. **한 달력 = 민평 ∩ IRS**, 그 위에서 두 엔진을 같은
날짜들로 부른다. 양쪽에 다 마킹이 있는 날만 세므로 없는 마크를 지어내지 않고,
빠진 날의 손익은 다음 공통 마킹의 차이에 그대로 들어 있다.

`d`(그날 변화)만 한 자리 더 조심한다. 두 엔진이 각자 "전영업일" 을 자기 달력에서
세므로, 공통 달력의 어제가 양쪽에서 같은 날일 때만 그 둘이 같은 밤을 가리킨다.
다른 밤이면(위의 12일) 그 자리에서는 **직전 공통 영업일 대비**로 바꿔 잰다 —
그 날짜를 평가 표본에 하나 더 넣는 값싼 대가로, 화면이 "당일" 이라고 부르는
숫자가 두 계열의 서로 다른 밤을 섞지 않게 된다.

── 대사 ────────────────────────────────────────────────────────────────────

`book_recon` 은 **표 자체를 둘**로 낸다 [OWNER, 2026-08-25 — 엔진 단위 분리].
스왑 표는 IRS 달력, 채권 표는 민평 달력 위에 각자 서고, 이 함수는 두 엔진의
블록을 `{"swap": …, "bond": …}` 로 나란히 돌려줄 뿐 병합하지 않는다.

**한 거래의 다리 둘은 예외다** [OWNER 2026-09-04]. 자산스왑(국고 + IRS)과
퓨처스왑(선물 + IRS)은 «상품 하나» 라, 두 다리가 다른 표에 서면 그 거래의 그날
손익을 화면이 한 줄로 못 말한다. 그 둘은 자기 표 **안에서** 다리로 갈라지고
(하루 일곱 줄: 다리마다 KRD·Δbp·손익 셋 + 합계 하나), 표 자체는 여전히 자기
엔진의 달력 위에 선다. 그래서 퓨처스왑의 IRS 다리는 **스왑 표에서 빠진다**.
2026-08-21 판(민평 ∩ IRS 병합 한 표)은 한쪽만 쉰 날과 그 다음 날을 떨궈야
했고 — 두 계열이 다른 밤을 재므로 — 그 드롭이 세로합을 기간 3분해와
어긋나게 했다. 위의 달력 문단은 **차트·헤드라인**(run_backtest)에만 남는다.
"""

from __future__ import annotations

import dataclasses as _dc
import datetime as dt
from bisect import bisect_left, bisect_right
from dataclasses import dataclass

from . import cashbond as cb
from . import funding as fd
from . import futures as ft
from .backtest import (
    MAX_POINTS,
    MAX_POSITIONS,
    Position,
    _run_one,
    _span_of,
    _thin,
)
from .backtest import book_recon as swap_book_recon
from .backtest import run_backtest as swap_run_backtest
from .creditmatrix import CreditMatrix

class MixedBookError(Exception):
    """혼합 북을 실행할 수 없다 — 라우트가 422 로 옮긴다."""


@dataclass(frozen=True)
class MixedPosition:
    """한 줄. `series_id` 가 스왑 문법(`10Y`·`3Y-10Y`)이거나 채권 문법
    (`CB:KTB:3Y`·`ASW:KTB:3Y`)이다 — 어느 쪽인지는 **id 만 보고** 안다
    (`instruments.kind_of` 와 같은 규칙)."""

    series_id: str
    direction: int
    notional: float
    entry: dt.date
    exit: dt.date | None = None


def is_bond(series_id: str) -> bool:
    return series_id.startswith((f"{cb.KIND_CASH}:", f"{cb.KIND_ASW}:"))


def is_futures(series_id: str) -> bool:
    return ft.is_futures(series_id)


def has_bond(positions: list[MixedPosition]) -> bool:
    return any(is_bond(p.series_id) for p in positions)


def has_futures(positions: list[MixedPosition]) -> bool:
    return any(is_futures(p.series_id) for p in positions)


def has_swap(positions: list[MixedPosition]) -> bool:
    return any(
        not is_bond(p.series_id) and not is_futures(p.series_id) for p in positions
    )


def _as_swap(p: MixedPosition) -> Position:
    return Position(
        series_id=p.series_id,
        direction=p.direction,
        notional=p.notional,
        entry=p.entry,
        exit=p.exit,
    )


def _as_bond(p: MixedPosition) -> cb.BondPosition:
    kind, bond_type, tenor = cb.parse_id(p.series_id)
    return cb.BondPosition(
        kind=kind,
        bond_type=bond_type,
        tenor=tenor,
        direction=p.direction,
        notional=p.notional,
        entry=p.entry,
        exit=p.exit,
    )


def _check(positions: list[MixedPosition]) -> None:
    if not positions:
        raise MixedBookError("포지션이 하나는 있어야 합니다.")
    if len(positions) > MAX_POSITIONS:
        raise MixedBookError(f"포지션은 최대 {MAX_POSITIONS}개입니다.")


# ── 기록의 한 모양 ──────────────────────────────────────────────────────────
#
# 두 엔진의 기록이 다르게 생겼다(스왑은 `legs`·`entryValue`, 채권은 `tenor`·
# `entryYield`·`funding`). 화면 하나가 둘 다 그리려면 **무엇인지 말하는 칸**이
# 있어야 한다 — `kind` 다. 없는 칸을 0 으로 채우지 않는 이유는 이 리포의 공란
# 정책과 같다: 스왑에 조달이 0 이라고 적으면 "조달이 0 원이었다" 로 읽힌다.


def _as_futures(p: MixedPosition) -> ft.FuturesPosition:
    return ft.as_position(p.series_id, p.direction, p.notional, p.entry, p.exit)


def _tag_swap(rec: dict) -> dict:
    return {"kind": "swap", "label": rec["id"], "funding": None, **rec}


def _tag_futures(rec: dict) -> dict:
    kind, tenor = ft.parse_id(rec["id"])
    label = (ft.FUT_LABELS if kind == ft.KIND_FUT else ft.FSW_LABELS)[tenor]
    return {"kind": "futures", "label": label, "funding": None, **rec}


def _tag_bond(rec: dict) -> dict:
    kind = "assetswap" if rec.get("kind") == cb.KIND_ASW else "cashbond"
    return {**rec, "kind": kind, "legs": []}


def _same_night(
    m: CreditMatrix, dataset, mi: list[int], di: list[int], k: int
) -> bool:
    """공통 달력의 어제가 두 달력에서 **같은 날**인가.

    참이면 두 엔진의 `prev` 가 같은 밤을 가리키므로 그 둘을 더한 것이 그대로
    하루치 변화다. 거짓이면 한쪽만 그 사이에 마킹이 하나 더 있었다는 뜻이다.
    """
    b, s = mi[k], di[k]
    if b == 0 or s == 0:
        return False
    return m.dates[b - 1] == dataset.dates[s - 1]


def _common(m: CreditMatrix, dataset) -> tuple[list[int], list[int]]:
    """(민평 자리들, 같은 날의 IRS 자리들) — 두 달력이 다 가진 날만, 오름차순.

    `cashbond._irs_index_map` 과 같은 사상이고 모양만 리스트다(k → 두 자리의
    쌍이 필요해서). 겹치는 날이 없으면 세운다 — 그때 아무 날짜나 골라 합치면
    표가 조용히 틀린다.
    """
    if dataset is None:
        raise MixedBookError("혼합 북에는 IRS 데이터셋이 필요합니다.")
    where = {d: j for j, d in enumerate(dataset.dates)}
    mi: list[int] = []
    di: list[int] = []
    for i, d in enumerate(m.dates):
        j = where.get(d)
        if j is not None:
            mi.append(i)
            di.append(j)
    if len(mi) < 2:
        raise MixedBookError(
            "민평과 IRS 달력이 겹치는 날이 없습니다 — 데이터를 확인하세요."
        )
    return mi, di


def _k_span(idx: list[int], entry_i: int, exit_i: int, label: str) -> tuple[int, int]:
    """엔진 자리 구간 → 공통 달력 자리 구간. 진입은 **이후 첫** 공통일,
    청산은 **이전 마지막** 공통일로 스냅한다 — 양쪽 다 그 포지션이 실제로
    살아 있던 날이다."""
    a = bisect_left(idx, entry_i)
    b = bisect_right(idx, exit_i) - 1
    if a > b or a >= len(idx):
        raise MixedBookError(
            f"{label}: 두 달력이 겹치는 날 중에 이 포지션이 살아 있는 날이 없습니다."
        )
    return a, b


def _dropped_days(m: CreditMatrix, dataset, a: dt.date, b: dt.date) -> int:
    """구간 안에서 **한쪽 달력에만** 있는 날의 수. 화면이 한 줄로 말한다."""
    ms = {d for d in m.dates if a <= d <= b}
    ds = {d for d in dataset.dates if a <= d <= b}
    return len(ms ^ ds)


# ── 실행 ────────────────────────────────────────────────────────────────────


def run_backtest(
    m: CreditMatrix | None,
    dataset,
    positions: list[MixedPosition],
    spec: fd.FundingSpec,
    fut: "ft.FuturesData | None" = None,
) -> dict:
    """섞인 북을 매일 재평가해 합친다.

    한 종류만 있는 북은 **그 엔진에 그대로 넘긴다** — 숫자가 종전과 한 원도
    달라지지 않아야 하고(정적 쌍둥이·가드가 그것을 핀으로 박고 있다), 스왑만
    있는 북이 민평 SQL 에 닿아야 할 이유도 없다. 섞인 북만 병합 경로로 간다:
    채권+스왑 두 달력은 종전 `_mixed` 그대로(골든 보호), **선물이 낀 북만**
    일반화 병합 `_mixed_any` 를 탄다 [OWNER, 2026-08-25 — 선물·퓨처스왑 합류].
    """
    _check(positions)
    if has_futures(positions) and fut is None:
        raise MixedBookError(
            "선물 줄에는 선물 종가가 필요합니다 — 백엔드가 SQL 에 닿는지 확인해 주세요."
        )
    if has_bond(positions) and m is None:
        raise MixedBookError(
            "채권 줄에는 민평이 필요합니다 — 백엔드가 SQL 에 닿는지 확인해 주세요."
        )
    if not has_bond(positions) and not has_futures(positions):
        out = swap_run_backtest(dataset, [_as_swap(p) for p in positions])
        out["positions"] = [_tag_swap(r) for r in out["positions"]]
        return out
    if not has_swap(positions) and not has_futures(positions):
        out = cb.run_backtest(m, dataset, [_as_bond(p) for p in positions], spec)
        out["positions"] = [_tag_bond(r) for r in out["positions"]]
        return out
    if not has_swap(positions) and not has_bond(positions):
        try:
            out = ft.run_backtest(fut, dataset, [_as_futures(p) for p in positions])
        except ft.FuturesError as exc:
            raise MixedBookError(str(exc))
        out["positions"] = [_tag_futures(r) for r in out["positions"]]
        return out
    if not has_futures(positions):
        return _mixed(m, dataset, positions, spec)
    return _mixed_any(m, dataset, fut, positions, spec)


def _mixed(
    m: CreditMatrix, dataset, positions: list[MixedPosition], spec: fd.FundingSpec
) -> dict:
    spec = spec.validated()
    mi, di = _common(m, dataset)
    imap = dict(zip(mi, di))

    swaps: dict[int, Position] = {}
    bonds: dict[int, cb.BondPosition] = {}
    legs: dict[int, cb._BondLeg] = {}
    spans: dict[int, tuple[int, int]] = {}

    entered: list[dt.date] = []      # 각 줄이 **실제로** 들어간 날 (스냅 뒤)
    for n, p in enumerate(positions):
        if is_bond(p.series_id):
            bp = _as_bond(p)
            if bp.direction != 1:
                # 백테스트·시뮬레이션 쪽과 같은 거절 [OWNER, 2026-08-14].
                raise MixedBookError(
                    "현금채권은 매수만 됩니다 — 공매도는 대차료가 필요한데 그 값이 없습니다."
                )
            leg = cb._bond_leg(m, bp)
            bonds[n], legs[n] = bp, leg
            spans[n] = _k_span(mi, leg.entry_i, leg.exit_i, bp.id)
            entered.append(m.dates[leg.entry_i])
        else:
            sp = _as_swap(p)
            entry_i, exit_i, _matured = _span_of(dataset, sp)
            swaps[n] = sp
            spans[n] = _k_span(di, entry_i, exit_i, sp.series_id)
            entered.append(dataset.dates[entry_i])

    first_k = min(a for a, _b in spans.values())
    last_k = max(b for _a, b in spans.values())
    sample_k = _thin(list(range(first_k, last_k + 1)), MAX_POINTS)

    # ── ★줄을 **북 창으로 깎는다** [OWNER 2026-09-28] ────────────────────────
    # `_mixed_any` 의 그 절과 같은 규율이고 같은 이유다(적대 검증은 이 경로에도
    # 같은 어긋남이 있다고 했고, 실측 491,829원이었다). 헤드라인은 공통 달력의
    # 마지막 점인데 줄은 자기 달력의 청산일까지 살아서 Σ줄 ≠ 헤드라인이었다.
    book_end = m.dates[mi[last_k]]
    clipped: dict[int, str] = {}
    for n, bp in list(bonds.items()):
        own_exit = m.dates[legs[n].exit_i]
        if own_exit > book_end:
            clipped[n] = own_exit.isoformat()
            bonds[n] = _dc.replace(bp, exit=book_end)
            legs[n] = cb._bond_leg(m, bonds[n])
    for n, sp in list(swaps.items()):
        _e_i, x_i, _mat = _span_of(dataset, sp)
        own_exit = dataset.dates[x_i]
        if own_exit > book_end:
            clipped[n] = own_exit.isoformat()
            swaps[n] = _dc.replace(sp, exit=book_end)

    # 두 달력이 어긋난 자리 — 모듈 주석의 `d` 절. 그 날만 직전 공통일을 평가
    # 표본에 더한다(전체에 더하지 않는 이유: 롤다운 체인의 걸음 폭이 바뀐다).
    gaps = {
        k for k in sample_k if k > first_k and not _same_night(m, dataset, mi, di, k)
    }
    eval_k = sorted(set(sample_k) | {k - 1 for k in gaps})
    swap_sample = [di[k] for k in eval_k]
    bond_sample = [mi[k] for k in eval_k]

    records: dict[int, dict] = {}
    own_k: dict[int, dict[int, float]] = {}
    prev_k: dict[int, dict[int, float]] = {}

    curve_cache: dict[int, object] = {}
    for n, sp in swaps.items():
        rec, own, prev = _run_one(dataset, sp, swap_sample, curve_cache)
        records[n] = _tag_swap(rec)
        own_k[n] = {k: own[di[k]] for k in eval_k}
        prev_k[n] = {k: prev[di[k]] for k in eval_k if di[k] in prev}

    swap_cache: dict[int, object] = {}
    for n, bp in bonds.items():
        rec, own, prev = cb.run_bond_position(
            m, dataset, bp, legs[n], bond_sample, spec, imap, swap_cache
        )
        records[n] = _tag_bond(rec)
        own_k[n] = {k: own[mi[k]] for k in eval_k}
        prev_k[n] = {k: prev[mi[k]] for k in eval_k if mi[k] in prev}

    points = []
    for k in sample_k:
        total = round(sum(own_k[n][k] for n in own_k), 0)
        if k == first_k:
            d = None
        elif k in gaps:
            # 양쪽의 "어제" 가 다른 날이라 하루치를 그대로 못 더한다 — 직전
            # 공통 영업일 대비로 잰다(모듈 주석).
            d = round(total - sum(own_k[n][k - 1] for n in own_k), 0)
        else:
            d = round(total - sum(prev_k[n].get(k, 0.0) for n in prev_k), 0)
        points.append({"t": m.dates[mi[k]].isoformat(), "pnl": total, "d": d})

    pnls = [p["pnl"] for p in points]
    a, b = m.dates[mi[first_k]], m.dates[mi[last_k]]
    for n, upto in clipped.items():
        # 이 줄은 원래 `upto` 까지 살았는데 북 창(`to`)에서 끊겼다.
        records[n]["clippedTo"] = upto
    return {
        "positions": [records[n] for n in range(len(positions))],
        "from": a.isoformat(),
        "to": b.isoformat(),
        "complete": len(sample_k) == last_k - first_k + 1,
        "points": points,
        "pnl": pnls[-1] if pnls else 0.0,
        "maxProfit": max(pnls) if pnls else 0.0,
        "maxLoss": min(pnls) if pnls else 0.0,
        "funding": fd.provenance(spec),
        # 화면이 한 줄로 말한다 — 무엇을 안 세었는지는 데이터 사실이다.
        "calendar": {
            "basis": "민평 ∩ IRS",
            "dropped": _dropped_days(m, dataset, a, b),
            # **선이 늦게 시작하는가.** 민평은 2020-01-02 부터인데 IRS 는 그보다
            # 앞이라, 2019년에 들어간 스왑을 채권과 섞으면 공통 달력이 그 진입을
            # 못 담는다. 그때도 **총액은 옳다**(각 줄의 누적은 자기 진입일부터
            # 세고, 첫 점이 그 값을 그대로 싣는다) — 그림만 중간부터 시작한다.
            # 0 에서 출발하지 않는 선은 설명 없이 두면 오독이라 여기서 말한다.
            "clippedFrom": min(entered).isoformat() if entered and min(entered) < a else None,
        },
    }


def _mixed_any(
    m: CreditMatrix | None,
    dataset,
    fut: "ft.FuturesData",
    positions: list[MixedPosition],
    spec: fd.FundingSpec,
) -> dict:
    """선물이 낀 혼합 북 — 날짜 키의 일반화 병합 [OWNER, 2026-08-25].

    `_mixed`(채권+스왑 두 달력)의 같은 규칙을 달력 N개로 일반화한다: 한 달력
    = 관련 달력 전부의 교집합, 그 위에서 각 엔진을 같은 날짜들로 부른다.
    `d` 의 갭 규칙도 같다 — 공통 달력의 어제가 **모든** 관련 달력에서 자기
    전 거래일과 같은 날일 때만 엔진들의 prev 를 그대로 더하고, 아니면 직전
    공통 영업일 대비로 바꿔 잰다. `_mixed` 를 일반화로 대체하지 않는 이유는
    골든 보호다(run_backtest doc) — 선물 없는 북은 종전 경로 바이트 그대로.
    """
    from bisect import bisect_left as _bl

    spec = spec.validated()

    swaps: dict[int, Position] = {}
    bonds: dict[int, cb.BondPosition] = {}
    blegs: dict[int, "cb._BondLeg"] = {}
    futs: dict[int, ft.FuturesPosition] = {}
    fut_cals: dict[int, list[dt.date]] = {}

    cals: list[list[dt.date]] = []          # 교집합·갭 판정에 드는 달력들

    def _add_cal(c: list[dt.date]) -> None:
        if not any(c is existing or c == existing for existing in cals):
            cals.append(c)

    entered: list[dt.date] = []
    exited: list[dt.date] = []
    for n, p in enumerate(positions):
        if is_bond(p.series_id):
            bp = _as_bond(p)
            if bp.direction != 1:
                raise MixedBookError(
                    "현금채권은 매수만 됩니다 — 공매도는 대차료가 필요한데 그 값이 없습니다."
                )
            leg = cb._bond_leg(m, bp)
            bonds[n], blegs[n] = bp, leg
            entered.append(m.dates[leg.entry_i])
            exited.append(m.dates[leg.exit_i])
            _add_cal(m.dates)
            if bp.kind == cb.KIND_ASW:
                # ASW 의 스왑 다리는 IRS 커브가 필요하다 — 그 달력도 교집합에.
                _add_cal(dataset.dates)
        elif is_futures(p.series_id):
            try:
                fp = _as_futures(p)
                cal = ft.calendar_of(fut, dataset, fp)
                a, b = ft._span_on(cal, fp)
            except ft.FuturesError as exc:
                raise MixedBookError(str(exc))
            futs[n], fut_cals[n] = fp, cal
            entered.append(cal[a])
            exited.append(cal[b])
            _add_cal(cal)
        else:
            sp = _as_swap(p)
            entry_i, exit_i, _matured = _span_of(dataset, sp)
            swaps[n] = sp
            entered.append(dataset.dates[entry_i])
            exited.append(dataset.dates[exit_i])
            _add_cal(dataset.dates)

    common = sorted(set.intersection(*[set(c) for c in cals]))
    window = [d for d in common if min(entered) <= d <= max(exited)]
    if not window:
        raise MixedBookError("포지션들이 함께 사는 날짜가 없습니다.")

    # ── ★줄을 **북 창으로 깎는다** [OWNER 2026-09-28] ────────────────────────
    #
    # 종전에는 헤드라인이 교집합 달력의 마지막 점이고(`pnls[-1]`) 줄들은 각자
    # **자기 달력의 청산일**까지 살아서, 같은 화면의 Σ줄과 헤드라인이 어긋났다
    # (실측 683,680원 · 그중 670,000원을 화면 캐리 칸이 먹었다). 두 길이 있었고
    # 오너가 이쪽을 골랐다 — **모든 수가 한 날 위에 선다.**
    #
    # 반대 길(헤드라인을 Σ줄로 바꾸기)을 안 고른 이유: 그러면 헤드라인 하나가
    # 09-23 과 09-25 를 섞은 수가 되어 「어느 날의 북인가」에 답을 못 한다 —
    # 같은 날 고친 「반쪽 장중」과 똑같은 병이다(한 줄은 한 시계만 말한다).
    #
    # 깎이기 전에 어디까지 살았는지는 **버리지 않는다**: 줄마다 `clippedTo` 로
    # 싣는다 — 값은 **깎이기 전 그 줄의 청산일**이다(이름이 가리키는 목표가
    # 아니라 출처다). ⚠지금은 **자료에만 있다**: `src/lib/api.ts` 의
    # `BacktestPosition` 이 이 열을 아직 안 받고 화면도 안 적는다. 화면은 깎인
    # 청산일(`exit`)만 말하므로 거짓은 아니고, 「원래 어디까지였나」를 적을지는
    # 오너 판단으로 열려 있다(2026-09-29 확인).
    book_end = window[-1]
    clipped: dict[int, str] = {}
    for n, bp in list(bonds.items()):
        own_exit = m.dates[blegs[n].exit_i]
        if own_exit > book_end:
            clipped[n] = own_exit.isoformat()
            bonds[n] = _dc.replace(bp, exit=book_end)
            blegs[n] = cb._bond_leg(m, bonds[n])
    for n, sp in list(swaps.items()):
        _e_i, x_i, _mat = _span_of(dataset, sp)
        own_exit = dataset.dates[x_i]
        if own_exit > book_end:
            clipped[n] = own_exit.isoformat()
            swaps[n] = _dc.replace(sp, exit=book_end)
    for n, fp in list(futs.items()):
        _a, b_i = ft._span_on(fut_cals[n], fp)
        own_exit = fut_cals[n][b_i]
        if own_exit > book_end:
            clipped[n] = own_exit.isoformat()
            futs[n] = _dc.replace(fp, exit=book_end)

    sample_k = _thin(list(range(len(window))), MAX_POINTS)

    def _own_prev(cal: list[dt.date], d: dt.date) -> dt.date | None:
        i = _bl(cal, d)
        return cal[i - 1] if 0 < i < len(cal) and cal[i] == d else None

    gaps = {
        k for k in sample_k
        if k > 0 and any(_own_prev(c, window[k]) != window[k - 1] for c in cals)
    }
    eval_k = sorted(set(sample_k) | {k - 1 for k in gaps})
    eval_dates = [window[k] for k in eval_k]

    records: dict[int, dict] = {}
    own_by: dict[int, dict[dt.date, float]] = {}
    prev_by: dict[int, dict[dt.date, float]] = {}

    curve_cache: dict[int, object] = {}
    ds_idx = {d: i for i, d in enumerate(dataset.dates)}
    for n, sp in swaps.items():
        sample_idx = [ds_idx[d] for d in eval_dates]
        rec, own, prevd = _run_one(dataset, sp, sample_idx, curve_cache)
        records[n] = _tag_swap(rec)
        own_by[n] = {d: own[ds_idx[d]] for d in eval_dates}
        prev_by[n] = {d: prevd[ds_idx[d]] for d in eval_dates if ds_idx[d] in prevd}

    if bonds:
        m_idx = {d: i for i, d in enumerate(m.dates)}
        imap = {m_idx[d]: ds_idx[d] for d in common if d in ds_idx}
        swap_cache: dict[int, object] = {}
        bond_sample = [m_idx[d] for d in eval_dates]
        for n, bp in bonds.items():
            rec, own, prevd = cb.run_bond_position(
                m, dataset, bp, blegs[n], bond_sample, spec, imap, swap_cache
            )
            records[n] = _tag_bond(rec)
            own_by[n] = {d: own[m_idx[d]] for d in eval_dates}
            prev_by[n] = {d: prevd[m_idx[d]] for d in eval_dates if m_idx[d] in prevd}

    for n, fp in futs.items():
        try:
            rec, own, prevd = ft.run_one(fut, dataset, fp, eval_dates, curve_cache)
        except ft.FuturesError as exc:
            raise MixedBookError(str(exc))
        records[n] = _tag_futures(rec)
        own_by[n] = own
        prev_by[n] = prevd

    points = []
    first_k = sample_k[0]
    for k in sample_k:
        d = window[k]
        total = round(sum(own_by[n][d] for n in own_by), 0)
        if k == first_k:
            dd = None
        elif k in gaps:
            dd = round(total - sum(own_by[n][window[k - 1]] for n in own_by), 0)
        else:
            dd = round(total - sum(pv.get(d, 0.0) for pv in prev_by.values()), 0)
        points.append({"t": d.isoformat(), "pnl": total, "d": dd})

    pnls = [p["pnl"] for p in points]
    a, b = window[sample_k[0]], window[sample_k[-1]]
    kinds = []
    if bonds:
        kinds.append("민평")
    if swaps or any(bp.kind == cb.KIND_ASW for bp in bonds.values()):
        kinds.append("IRS")
    if futs:
        kinds.append("선물")
    for n, upto in clipped.items():
        # 이 줄은 원래 `upto` 까지 살았는데 북 창(`to`)에서 끊겼다.
        records[n]["clippedTo"] = upto
    union_dates = sorted(set().union(*[set(c) for c in cals]))
    dropped = len([d for d in union_dates if a <= d <= b]) - len(
        [d for d in window if a <= d <= b]
    )
    return {
        "positions": [records[n] for n in range(len(positions))],
        "from": a.isoformat(),
        "to": b.isoformat(),
        "complete": len(sample_k) == len(window),
        "points": points,
        "pnl": pnls[-1] if pnls else 0.0,
        "maxProfit": max(pnls) if pnls else 0.0,
        "maxLoss": min(pnls) if pnls else 0.0,
        "funding": fd.provenance(spec) if bonds else None,
        "calendar": {
            "basis": " ∩ ".join(kinds) if len(kinds) > 1 else (kinds[0] if kinds else ""),
            "dropped": dropped,
            "clippedFrom": min(entered).isoformat() if entered and min(entered) < a else None,
        },
    }


# ── 대사 ────────────────────────────────────────────────────────────────────


def book_recon(
    m: CreditMatrix | None,
    dataset,
    positions: list[MixedPosition],
    spec: fd.FundingSpec,
    fut: "ft.FuturesData | None" = None,
) -> dict:
    """일별 대사 — 스왑·채권 **각자 자기 표** [OWNER, 2026-08-25].

    2026-08-21 판은 두 엔진의 표를 민평 ∩ IRS 병합 달력 위에서 한 표로
    합쳤다. 그 병합이 요구한 것들 — 한쪽만 쉰 날과 그 다음 날을 떨구는
    드롭(세로합 ≠ 기간 3분해), 끝난 쪽의 0 채움, 늦은 쪽 이월 앵커 — 은
    전부 «두 계열이 서로 다른 밤을 잰다»는 사실을 한 표에 욱여넣은 대가였다.

    분리하면 그 대가가 통째로 사라진다: 각 표가 자기 달력 위에 서므로 빠지는
    날이 없고, 세로합이 자기 엔진의 기간 3분해와 닫히고, 조달 열은 채권 표에만
    선다. 북 전체의 하루 총액 한 줄은 사라지는데, 그것은 숨긴 것이 아니라
    애초에 어느 하루도 아니었던 수를 그리지 않게 된 것이다(모듈 주석 `d` 절).

    반환은 언제나 `{"swap": 블록|None, "bond": 블록|None, "futures": 블록|None}`
    — 한 종류뿐인 북은 그 엔진의 블록이 자기 자리에 그대로 서고 다른 쪽은
    None 이다. 각 블록은 그 엔진 `book_recon` 의 모양 그대로다(두 번째 정의
    없음). 선물 표 [OWNER, 2026-08-25]: FUT 와 FSW 의 선물 다리가 서고, FSW
    의 IRS 다리는 실제 스왑이므로 스왑 표에 합류한다(아래 주석).
    """
    _check(positions)
    swap_recon = bond_recon = futures_recon = None

    # 퓨처스왑의 IRS 다리는 **선물 표 안에 다리로** 선다 [OWNER 2026-09-04 —
    # "Backtest의 퓨처스왑과 자산스왑도 … 하루당 행 7개로"]. 2026-08-25 의
    # 「엔진 단위 분리」는 그 다리를 스왑 표로 보냈는데, 그러면 한 거래의 두
    # 다리가 서로 다른 표에 서서 «이 거래가 그날 얼마를 벌었나» 를 화면이
    # 한 줄로 못 말한다. 자산스왑이 이미 다리 둘을 한 표에 세우고 있었고
    # (`cashbond.book_recon` 의 `with_legs`), 퓨처스왑이 그것을 따라간다.
    #
    # **그래서 스왑 표에서는 뺀다** — 안 빼면 같은 돈이 두 표에 선다
    # (`futures.book_recon` 의 `with_legs` 머리가 그 계약의 다른 쪽).
    if has_futures(positions):
        if fut is None:
            raise MixedBookError(
                "선물 줄에는 선물 종가가 필요합니다 — 백엔드가 SQL 에 닿는지 확인해 주세요."
            )
        try:
            futures_recon = ft.book_recon(
                fut, dataset,
                [_as_futures(p) for p in positions if is_futures(p.series_id)],
                with_legs=True,
            )
        except ft.FuturesError as exc:
            raise MixedBookError(str(exc))

    swap_positions = [
        _as_swap(p) for p in positions
        if not is_bond(p.series_id) and not is_futures(p.series_id)
    ]
    if swap_positions:
        swap_recon = swap_book_recon(dataset, swap_positions)
    if has_bond(positions):
        if m is None:
            raise MixedBookError("채권 줄에는 민평이 필요합니다.")
        # 자산스왑도 다리 둘이다 [OWNER 2026-09-04] — 국고 매수와 IRS 페이가
        # 하루 안에서 각자 KRD·Δbp·손익을 지고 합계가 닫는다. 비용은 IRS 다리의
        # KRD 범프이고(250일 창에서 5.55배 — `cashbond.book_recon` 의 그 실측),
        # **자산스왑 줄이 있을 때만** 문다(그 함수가 `asw and with_legs` 로 잰다).
        bond_recon = cb.book_recon(
            m, dataset, [_as_bond(p) for p in positions if is_bond(p.series_id)],
            spec, with_legs=True,
        )
    return {"swap": swap_recon, "bond": bond_recon, "futures": futures_recon}
