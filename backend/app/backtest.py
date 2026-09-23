"""Backtest: enter a position on a past date, revalue it every day since.

[OWNER, 2026-07-31] "며칠부터 며칠사이에 어떤 포지션으로 들어갔을 때 현재 기준
또는 특정일자까지 손익이 어떻게 움직였을 것이다."

A BOOK, NOT ONE TRADE [OWNER, 2026-07-31]. Several positions, each with its
own instrument, side, size, entry date AND exit date — you leg into things on
different days and out of them on different days. The published line is the
book total; each position also reports its own P&L so the total can be read
back to what made it.

A closed position stops moving. After its exit its contribution is FROZEN at
the P&L it had on that date, so it keeps counting toward the book total (that
money was made) without responding to a market it is no longer in. A position
that kept marking after it was closed is the classic way a backtest flatters
itself, so it is asserted rather than assumed.

WHAT THIS IS. On the entry date the position is struck at that day's own par
rates, so it is worth ~nothing. Every business day after, the swap is revalued
on THAT day's bootstrapped curve, and the P&L is the change in dirty NPV plus
the cash the position has actually settled along the way. Full revaluation, not
a DV01 approximation [OWNER chose "재평가 + 캐리까지"], which means the number
carries roll-down and carry rather than only the parallel rate move.

WHY IT IS NOT `Δrate × DV01 × notional`. That approximation is first-order in
the rate and blind to the passage of time: it cannot see that a 10Y entered a
year ago is a 9Y today, and it books no coupon. Over a few days the two agree
closely — `test_backtest.py` asserts they do, which is the cheapest available
check that the revaluation is not wildly wrong — and over a year they should
not, which is the whole reason for choosing revaluation.

THE DIRTY + SETTLED-CASH BASIS. A swap's dirty NPV drops by the coupon on every
payment date, because the flow leaves the valuation schedule the moment it is
paid. Marking P&L on NPV alone therefore draws a sawtooth that is pure
accounting artefact — the desk RECEIVED that money. So the series is
`ΔdirtyNPV + cumulative settled cash`, which is continuous across coupon dates.
The frozen engine reached the same convention (its s13 note); `settled_cash_between`
is ported from it.

LEG CONSTRUCTION. An outright is one swap. A spread is two and a butterfly is
three, weighted **DV01-neutral at the entry curve** [OWNER] so the quoted value
(r_long − r_short, 2·r_belly − r_short − r_long) is the P&L driver — the same
weighting `app/dv01.py` already serves to the table. The user's notional applies
to the reference leg (the longest for a spread, the belly for a fly) and the
others follow from it.

NO LOOK-AHEAD. Curves are bootstrapped from the row AT each date, and floating
periods take the CD91 print of F(R) = reset − 1 Seoul business day via the
ported `select_fixing`, which refuses a fixing dated after the valuation date.
A backtest that peeks is worse than no backtest.
"""

from __future__ import annotations

import datetime as dt
from bisect import bisect_left, bisect_right
from dataclasses import dataclass

import numpy as np

from .curves import TENOR_T, par_rates_at_index
from .dataset import Dataset
from .derive import derived_ids
from .engine_port import bootstrap_zero_curve, next_kr_business_day
from .dv01 import pv01
from .valuation_port import CurveBundle, VanillaSwap, settled_cash_between, value_booked_trade

# The CD91 series IS the 3M curve node (dataset._tenor_id), and it is the
# floating leg every KRW CD-IRS pays. One name for the coupling.
CD_TENOR = "3M"

# How many points the P&L line is downsampled to before it is served. A
# ten-year backtest is ~2,600 business days and the chart is ~1,100px wide, so
# every point beyond this is a number nobody can see (§20).
MAX_POINTS = 400

# A book, not a portfolio system. Past this the sheet is unreadable and each
# extra position is another full daily revaluation pass.
MAX_POSITIONS = 12


class BacktestError(Exception):
    """The request cannot be run — a bad instrument, or dates outside the data."""


@dataclass
class Leg:
    tenor: str
    """+1 = pay fixed on this leg, -1 = receive fixed."""
    sign: int
    notional: float
    entry_rate: float  # decimal
    dv01: float        # per unit notional, at the entry curve


def _legs_for(series_id: str) -> list[tuple[str, int]]:
    """(tenor, sign) per leg, sign relative to a `+1` position in the quoted
    value. A spread `A-B` is quoted r_B − r_A, so it is long B / short A; a fly
    `A-B-C` is 2·r_B − r_A − r_C, so it is 2 belly against the wings."""
    parts = series_id.split("-")
    if len(parts) == 1:
        return [(parts[0], +1)]
    if len(parts) == 2:
        return [(parts[1], +1), (parts[0], -1)]
    if len(parts) == 3:
        return [(parts[1], +1), (parts[0], -1), (parts[2], -1)]
    raise BacktestError(f"cannot build legs for {series_id!r}")


def _index_on_or_after(dates: list[dt.date], d: dt.date) -> int:
    i = bisect_left(dates, d)
    if i >= len(dates):
        raise BacktestError(f"{d} is after the last observation ({dates[-1]})")
    return i


def _index_on_or_before(dates: list[dt.date], d: dt.date) -> int:
    i = bisect_right(dates, d) - 1
    if i < 0:
        raise BacktestError(f"{d} is before the first observation ({dates[0]})")
    return i


def _validate(dataset: Dataset, pos: Position) -> None:
    """Everything that makes a position unrunnable, as a 422 rather than a
    stray KeyError from somewhere deeper."""
    if pos.direction not in (1, -1):
        raise BacktestError("direction must be +1 or -1")
    if pos.notional <= 0:
        raise BacktestError("notional must be positive")
    known = {sid for sid, _k, _l in derived_ids()} | set(dataset.series)
    if pos.series_id not in known:
        raise BacktestError(f"unknown instrument {pos.series_id!r}")
    for tenor, _sign in _legs_for(pos.series_id):
        if tenor not in TENOR_T:
            raise BacktestError(f"unknown tenor {tenor!r}")


def _maturity_of(entry: dt.date, tenor: str) -> dt.date:
    """When a swap struck on `entry` for `tenor` actually ends.

    Mirrors the ported `VanillaSwap.to_irs_trade`: spot is T+1 business days and
    the raw termination is that plus `round(years * 365)` calendar days. Derived
    rather than built, because this is asked once per leg per RUN while the
    trade object is built once per leg per DATE."""
    return next_kr_business_day(entry) + dt.timedelta(
        days=round(TENOR_T[tenor] * 365)
    )


def _span_of(dataset: Dataset, pos: Position) -> tuple[int, int, bool]:
    """(first index, last index, ended at maturity) for the position's real life.

    A SWAP ENDS AT ITS MATURITY, whatever exit was asked for. Without this a 9M
    entered in 2020 was reported as held to 2026 — six years of "position" for a
    trade that ceased to exist after nine months. The P&L was already frozen
    (there is nothing left to value), so the FIGURE was right and the story was
    wrong: the period read six years and the daily change read 0원 for five of
    them, which is what made the readout look broken.

    The cap lives HERE rather than inside `_run_one` because the book's window
    is built from these spans too — computing the window from the requested exit
    while capping separately let the period column say 만기 while the chart drew
    a flat line past it. The longest leg decides, since that is when the package
    is finally done.
    """
    # Validated HERE because this is the first thing to touch a position — the
    # book computes every span before it runs anything, so a bad instrument
    # would otherwise reach `TENOR_T` as a KeyError instead of a 422.
    _validate(dataset, pos)

    dates = dataset.dates
    entry_i = _index_on_or_after(dates, pos.entry)
    exit_i = _index_on_or_before(dates, pos.exit) if pos.exit else len(dates) - 1
    # exit ON the entry date is a legal degenerate: struck and unwound at one
    # close, worth exactly 0 in both halves — a trivial answer, not an error
    # [V-PASS V5, 2026-08-03; it used to 422]. Exit BEFORE entry stays refused.
    if exit_i < entry_i:
        raise BacktestError(
            f"{pos.series_id}: the exit date must not precede the entry date"
        )
    matures = max(
        _maturity_of(dates[entry_i], t) for t, _sign in _legs_for(pos.series_id)
    )
    # The last row the swap still exists on. Reported rather than re-derived by
    # the caller: a maturity landing on a non-trading day (3M struck 2020-06-30
    # matures 2020-09-30, a day the file has no row for) makes
    # `maturity <= exit_date` false even though the position DID mature, which
    # is exactly the shape the first version got wrong.
    # `_index_on_or_before` CLAMPS to the last row, so a 10Y struck in 2020 —
    # maturing in 2030, well past the data — would otherwise report as matured
    # on the final date. It has to still be inside the file to have happened.
    matured = matures <= dates[-1] and _index_on_or_before(dates, matures) <= exit_i
    if matured:
        exit_i = _index_on_or_before(dates, matures)
        if exit_i < entry_i:
            raise BacktestError(
                f"{pos.series_id}: matures on {matures}, before it could be held"
            )
    return entry_i, exit_i, matured


def _curve_at(dataset: Dataset, i: int, cache: dict[int, np.ndarray] | None = None) -> np.ndarray:
    """The bootstrapped zero curve for the row at `i`.

    `cache` is per-RUN, not global: the curve depends on the dataset, and a
    module-level cache would survive a data refresh and serve yesterday's
    curve. Within one request the same date is valued once per position, so a
    three-position book was bootstrapping every date three times — measured
    0.7ms each, which is 0.8s of a 2.2s run spent recomputing the same array.
    """
    if cache is not None and i in cache:
        return cache[i]
    zc = bootstrap_zero_curve(par_rates_at_index(dataset, i))
    if cache is not None:
        cache[i] = zc
    return zc


def _cd_fixings(dataset: Dataset, upto: int) -> dict[dt.date, float]:
    """{date: decimal CD91} up to and including index `upto`. Bounded on
    purpose: handing the whole history to a valuation dated earlier would let
    `select_fixing`'s no-look-ahead guard be the only thing standing between us
    and a fixing from the future. Two guards are better than one."""
    vals = dataset.series[CD_TENOR]
    return {
        d: v / 100.0
        for d, v in zip(dataset.dates[: upto + 1], vals[: upto + 1])
        if v is not None
    }


def _build_legs(
    dataset: Dataset, series_id: str, notional: float, entry_i: int
) -> list[Leg]:
    """Struck at the entry date's own par rates, weighted DV01-neutral."""
    zc = _curve_at(dataset, entry_i)
    specs = _legs_for(series_id)

    built: list[Leg] = []
    for tenor, sign in specs:
        if tenor not in TENOR_T:
            raise BacktestError(f"unknown tenor {tenor!r}")
        rate = dataset.series.get(tenor, [None])[entry_i]
        if rate is None:
            raise BacktestError(f"no {tenor} rate on {dataset.dates[entry_i]}")
        built.append(
            Leg(
                tenor=tenor,
                sign=sign,
                notional=0.0,  # set below
                entry_rate=rate / 100.0,
                dv01=pv01(zc, TENOR_T[tenor]),
            )
        )

    # The reference leg carries the user's notional; the others are scaled so
    # each leg's DV01 contribution matches it — that is what makes the quoted
    # spread/fly value the P&L driver rather than a lopsided rate bet.
    ref = built[0]
    ref.notional = notional
    ref_dv = ref.dv01 * notional
    for leg in built[1:]:
        # a fly's belly carries twice the wings' weight (2·belly − wings)
        share = 0.5 if len(built) == 3 else 1.0
        leg.notional = (ref_dv * share) / leg.dv01 if leg.dv01 else 0.0
    return built


def _value_on(
    legs: list[Leg],
    dataset: Dataset,
    i: int,
    entry_date: dt.date,
    fixings: dict[dt.date, float],
    cache: dict[int, np.ndarray] | None = None,
    curve_idx: int | None = None,
) -> tuple[float, float]:
    """(clean NPV, accrued interest) of the position on the row at index `i`.

    Split rather than summed [OWNER, 2026-07-31] so the P&L can be reported as
    평가손익 + 캐리손익. Their sum is the dirty NPV, which is what the total is
    built from, so nothing about the headline number changes — only that it can
    now be read in two parts.

    `curve_idx` [OWNER, 2026-08-11 — 교과서 3분해]: value the swap AS OF
    `dates[i]` but on the curve bootstrapped from the row at `curve_idx`.
    The zero curve is a function of time-FROM-valuation-date, so an older
    curve at a later date is exactly the unchanged-term-structure
    (constant-maturity) assumption — the textbook roll-down revaluation.
    Default (None) keeps the ordinary same-day valuation.
    """
    curve = CurveBundle(
        dataset.dates[i],
        _curve_at(dataset, i if curve_idx is None else curve_idx, cache),
        [],
    )
    clean = 0.0
    accrued = 0.0
    for leg in legs:
        swap = VanillaSwap(
            # The FLOAT tenor, not a rounded integer. `VanillaSwap` annotates
            # this `int`, but the ported body's only use of it is
            # `round(tenor_years * 365)` to derive the maturity — so obeying the
            # annotation silently repriced every non-whole-year node: 1D, 3M, 6M
            # and 9M all became ONE-YEAR swaps (round(0.25) is 0, and `or 1`
            # finished the job) and 1.5Y became 2Y. Only integer-year tenors
            # were ever right.
            tenor_years=TENOR_T[leg.tenor],
            notional=leg.notional,
            fixed_rate=leg.entry_rate,
            pay_fixed=leg.sign > 0,
            trade_date=entry_date,
        )
        res = value_booked_trade(swap, curve, fixings)
        clean += res.clean_npv
        accrued += res.accrued_interest
    return clean, accrued


def _settled_to(
    legs: list[Leg],
    entry_date: dt.date,
    upto: dt.date,
    fixings: dict[dt.date, float],
) -> float:
    total = 0.0
    for leg in legs:
        swap = VanillaSwap(
            # The FLOAT tenor, not a rounded integer. `VanillaSwap` annotates
            # this `int`, but the ported body's only use of it is
            # `round(tenor_years * 365)` to derive the maturity — so obeying the
            # annotation silently repriced every non-whole-year node: 1D, 3M, 6M
            # and 9M all became ONE-YEAR swaps (round(0.25) is 0, and `or 1`
            # finished the job) and 1.5Y became 2Y. Only integer-year tenors
            # were ever right.
            tenor_years=TENOR_T[leg.tenor],
            notional=leg.notional,
            fixed_rate=leg.entry_rate,
            pay_fixed=leg.sign > 0,
            trade_date=entry_date,
        )
        total += settled_cash_between(swap, fixings, entry_date, upto)
    return total


def _thin(idx: list[int], keep: int) -> list[int]:
    """Evenly thin an index list to at most `keep`, always keeping the ends."""
    if len(idx) <= keep:
        return idx
    step = (len(idx) - 1) / (keep - 1)
    out = sorted({idx[round(k * step)] for k in range(keep)})
    if out[-1] != idx[-1]:
        out.append(idx[-1])
    return out


@dataclass
class Position:
    """One line of the book, as the caller states it."""

    series_id: str
    direction: int
    notional: float
    entry: dt.date
    exit: dt.date | None = None


def _run_one(
    dataset: Dataset,
    pos: Position,
    sample: list[int],
    cache: dict[int, np.ndarray] | None = None,
) -> tuple[dict, dict[int, float]]:
    """One position: its record, and its P&L at each sampled index.

    A position contributes NOTHING before its entry and stays FROZEN at its
    closing P&L after its exit. Both matter: a position that started paying
    before it was opened would be free money, and one that kept marking after
    it was closed is the classic way a backtest flatters itself.
    """
    dates = dataset.dates
    entry_i, exit_i, matured = _span_of(dataset, pos)  # validates, caps at maturity 
    legs = _build_legs(dataset, pos.series_id, pos.notional, entry_i)
    for leg in legs:
        leg.sign *= pos.direction

    entry_date = dates[entry_i]
    entry_fx = _cd_fixings(dataset, entry_i)
    clean0, accrued0 = _value_on(legs, dataset, entry_i, entry_date, entry_fx, cache)

    # ── 개시 = 거래일 → 발효일 한 밤 [OWNER, 2026-08-14] ────────────────────
    # KRW CD-IRS 는 스팟 시작이다 (`VanillaSwap.to_irs_trade`: 발효일 =
    # next_kr_business_day(거래일)). 그 한 밤 동안 스왑은 아직 발효 전이라
    # 경과이자가 한 푼도 붙지 않는다 — `value_booked_trade` 가 경과이자를
    # `val_date > a_start` 일 때만 잡기 때문이고, 그것은 옳다.
    #
    # 결과는 옳지 않았다. 캐리 = Δ경과이자 + 결제현금 이므로 그 밤의 캐리가
    # 구조적으로 0 이 되고, 롤 = Δclean 이므로 **그 밤의 세타 전체가 롤다운으로
    # 떨어졌다**. 같은 캘린더 밤을 하루 먼저 든 포지션과 나란히 재면 갈리는 것이
    # 배분뿐임이 보인다 (2026-06-19 3Y 100억, 금→월 3일 밤):
    #
    #     06-18 진입(이튿날 밤)   캐리 −784,932   롤 + 12,180   Δdirty −772,752
    #     06-19 진입(첫날  밤)   캐리        0   롤 −688,359   Δdirty −688,359
    #
    # 진입일 40개 표본에서 첫날 밤 롤의 중앙값이 이후 밤의 중앙값보다 3Y −91,802
    # · 10Y −155,294 만큼 더 손실 쪽이었고(78% / 82%), 10일 보유에서는 보고된
    # 롤다운의 24~26% 가 이 한 밤이었다.
    #
    # 캐리도 롤도 아닌 밤이라 **네 번째 칸으로 뺀다** [OWNER, 2026-08-14 —
    # "지어내는 숫자가 없음"]. 경과이자를 거래일부터 발생시키는 대안은 법적으로
    # 없는 하루치 이자를 만들어 내므로 오너가 물렸다.
    #
    # 총손익은 불변이다. 이 수정이 바꾸는 것은 clean 변화를 평가·롤다운·개시
    # 셋으로 가르는 방식뿐이고, `own[i]`(= 손익 라인)은 한 줄도 건드리지 않는다.
    eff_i = min(entry_i + 1, exit_i)
    startup = 0.0
    if eff_i > entry_i:
        clean_eff_frozen, _a_eff = _value_on(
            legs, dataset, eff_i, entry_date, entry_fx, cache, curve_idx=entry_i
        )
        startup = clean_eff_frozen - clean0

    # Valued only on the sampled dates INSIDE its own life, plus its exit — so
    # the frozen tail is the real closing figure, not the last sample before it.
    live = sorted(
        {i for i in sample if entry_i <= i <= exit_i}
        | {exit_i}
        # Plus the business day BEFORE each published point, so the chart can
        # report a real ONE-DAY change even where the series is thinned. A
        # ten-year book publishes 400 of ~2,600 days, so the step between
        # neighbours is ~6 days; without these the readout could only say how
        # much moved between two dots, which is not what anyone means by "that
        # day". Costs one extra valuation per point — measured 0.6s -> 1.2s on
        # ten years, which is not a trade worth agonising over.
        | {i - 1 for i in sample if entry_i < i <= exit_i}
    )

    own: dict[int, float] = {}
    last = 0.0
    last_carry = 0.0
    last_val = 0.0
    last_roll = 0.0
    last_start = 0.0
    last_cash = 0.0
    # 롤다운 체인의 시드는 **발효일**이다 (종전에는 거래일). 거래일→발효일
    # 한 밤은 위에서 `startup` 으로 이미 빠졌으므로, 여기서 다시 세면 두 번
    # 센다. `live` 안의 어떤 자리도 entry_i 와 eff_i 사이에 없다 — eff_i 가
    # entry_i + 1 이기 때문 — 이라 시드를 옮겨도 체인에 구멍이 나지 않는다.
    prev_i = eff_i
    prev_fx = _cd_fixings(dataset, eff_i)
    if eff_i > entry_i:
        prev_clean, _a_seed = _value_on(legs, dataset, eff_i, entry_date, prev_fx, cache)
    else:
        prev_clean = clean0
    roll_cum = 0.0
    for i in live:
        fx = _cd_fixings(dataset, i)
        clean, accrued = _value_on(legs, dataset, i, entry_date, fx, cache)
        cash = _settled_to(legs, entry_date, dates[i], fx)
        # An exact split, not an attribution model [OWNER, 2026-08-11 — 교과서
        # 3분해: 평가 + 캐리 + 롤다운]:
        #   pnl = (dirty_t − dirty_0) + cash
        #       = (clean_t − clean_0) + (accrued_t − accrued_0 + cash)
        #       = (평가손익 + 롤다운손익) +        캐리손익
        # 캐리 = settled + accrued net interest — the textbook cash carry (the
        # coupon differential earned by doing nothing; Clarus/Tuckman).
        # 롤다운 = the clean-price change from AGING ALONE, chained step by
        # step: value today's (shorter) swap on the PREVIOUS valued date's
        # curve, unchanged in tenor space — Tuckman's unchanged-term-structure
        # assumption, the P&L-explain "yesterday's curve" convention this repo
        # already adopted for the recon estimate (2026-08-10). 평가 = the
        # remainder of the clean change, i.e. what the CURVE MOVING did that
        # step. The chain telescopes, so 평가 + 롤다운 == clean_t − clean_0 to
        # the float, and the three parts still sum to the published figure by
        # construction. On a thinned book (>MAX_POINTS days) a chain step
        # spans several days; the split stays exact, only the step width of
        # the unchanged-curve assumption widens (test_backtest_theta pins the
        # daily case: a frozen market puts the whole clean change in 롤다운
        # and exactly 0 in 평가).
        val_total = clean - clean0
        carry = accrued - accrued0 + cash
        if i > prev_i:
            # 동결 재평가는 **전일 시점의 픽싱**으로 [OWNER, 2026-08-11 —
            # 평가일 기준 세타]: 스텝 사이에 새로 찍힌 CD 프린트(리셋 t+1,
            # F(R)=t 인 기간)는 "어제 알던 것"이 아니므로 동결 세계에 넣지
            # 않는다 — 그 서프라이즈는 잔여(평가)로 떨어진다. 이래야 일별
            # 대사의 포워드 세타(전일에 booking)와 레코드 스칼라의 버킷이
            # 정확히 일치한다(안 맞추면 픽싱일마다 롤다운으로 새서 Σ가
            # 어긋난다 — 실측 5개월 25만원).
            clean_frozen, _acc_f = _value_on(
                legs, dataset, i, entry_date, prev_fx, cache, curve_idx=prev_i
            )
            roll_cum += clean_frozen - prev_clean
        # 개시는 발효일에 한 번 켜지고 그 뒤로 상수다 — 진입일 당일 행에서는
        # 아직 그 밤이 지나지 않았으므로 0 이어야 한다 (그날 네 칸이 모두 0).
        start_cum = startup if i >= eff_i else 0.0
        own[i] = last = val_total + carry
        last_val = val_total - roll_cum - start_cum
        last_roll = roll_cum
        last_start = start_cum
        last_carry, last_cash = carry, cash
        # 진입일 행에서는 체인 커서를 건드리지 않는다. 커서는 이미 발효일에
        # 놓여 있고, 여기서 무조건 갱신하면 그 시드가 거래일로 되돌아가 다음
        # 걸음이 개시의 밤을 롤다운으로 다시 센다 (이 수정을 처음 넣었을 때
        # 정확히 그렇게 됐다 — 롤다운이 한 푼도 안 줄었다).
        if i >= eff_i:
            prev_i, prev_clean, prev_fx = i, clean, fx

    def at(i: int) -> float:
        if i < entry_i:
            return 0.0                 # not yet on
        if i > exit_i:
            return last                # closed: frozen, still counted
        return own[i]

    series = {i: at(i) for i in sample}
    # the same position one business day earlier, for the daily change
    prev_day = {i: at(i - 1) for i in sample if i - 1 >= 0}

    record = {
        "id": pos.series_id,
        "direction": pos.direction,
        "notional": pos.notional,
        "entry": entry_date.isoformat(),
        "exit": dates[exit_i].isoformat(),
        "closed": exit_i < len(dates) - 1,
        # 만기 and 청산 are different facts: one ran to the end of its own
        # schedule, the other was closed out early.
        "matured": matured,
        "legs": [
            {
                "tenor": leg.tenor,
                "side": "pay" if leg.sign > 0 else "receive",
                "notional": round(leg.notional, 0),
                "entryRate": round(leg.entry_rate * 100, 4),
                "dv01": round(leg.dv01, 6),
            }
            for leg in legs
        ],
        "entryValue": _quoted_value(dataset, pos.series_id, entry_i),
        "exitValue": _quoted_value(dataset, pos.series_id, exit_i),
        "pnl": round(last, 0),
        # Closing scalars, not paths. The sheet shows accumulated carry per
        # position; shipping a full npv/cash series for each would be 12 × 400
        # × 2 numbers to draw one total line. `trace()` below reconstructs the
        # path when something needs to look at it.
        # The FOUR parts of `pnl`, which they sum to exactly (§backtest)
        # [OWNER, 2026-08-11 — 교과서 3분해 · 2026-08-14 — 개시 분리]. 평가 =
        # what the curve MOVING did (clean change minus the roll chain minus
        # 개시). 롤다운 = clean change from aging alone on the unchanged curve,
        # chained from the EFFECTIVE date. 캐리 = interest actually earned or
        # paid, settled plus still accruing. 개시 = the trade-date→effective-date
        # night, which is neither (the swap has not started, so nothing accrues).
        "valuation": round(last_val, 0),
        "rolldown": round(last_roll, 0),
        "carry": round(last_carry, 0),
        # 개시 = 거래일→발효일 한 밤 (위 주석). 넷을 더하면 `pnl` 이다.
        "startup": round(last_start, 0),
        "cash": round(last_cash, 0),
    }
    # ── 다리별 성분 — 스왑 줄은 **다리가 하나**다 [OWNER 2026-09-23] ─────────
    # 커브·플라이도 하나로 센다: 3s10s 는 상품 다리가 둘이어도 «IRS 포지션
    # 하나» 이고, 이 열의 뜻은 「어느 자산의 성분인가」이지 「몇 개를 거래했나」
    # 가 아니다(상품 다리 서술은 위 `legs` 가 이미 지고 있다).
    #
    # 한 줄짜리 북에서는 화면이 이 블록을 **안 그린다**(합계와 같은 수를 한 번
    # 더 적는 꼴이라). 이것이 있어야 하는 자리는 **혼합 북**이다 — 자산스왑과
    # 순수 스왑이 같이 선 북에서 「IRS」 열이 둘을 다 안아야 열이 닫힌다.
    record["legParts"] = [{
        "name": "IRS",
        "valuation": record["valuation"],
        "rolldown": record["rolldown"],
        "carry": record["carry"],
        "startup": record["startup"],
        # 스왑에는 조달할 원금이 없다 — 0 이 아니라 공란이다(공란 정책).
        "funding": None,
        "pnl": record["pnl"],
    }]
    return record, series, prev_day


def trace(dataset: Dataset, pos: Position) -> list[dict]:
    """One position's full daily path: pnl, npv and settled cash per date.

    Not served by any endpoint — the sheet draws the book total and needs only
    closing scalars per position, and shipping this for a dozen positions would
    be thousands of numbers to draw one line. It exists because the properties
    worth asserting about this engine (cash steps only on payment dates, and
    each step equal to the real net coupon) are properties of the PATH, and a
    test that cannot see the path cannot check them.
    """
    dates = dataset.dates
    # the same span the book uses, maturity cap included — a trace that ran
    # past the swap's own end would disagree with the line drawn from it
    entry_i, exit_i, _matured = _span_of(dataset, pos)
    legs = _build_legs(dataset, pos.series_id, pos.notional, entry_i)
    for leg in legs:
        leg.sign *= pos.direction
    entry_date = dates[entry_i]
    entry_fx = _cd_fixings(dataset, entry_i)
    clean0, accrued0 = _value_on(legs, dataset, entry_i, entry_date, entry_fx)

    # 개시 — `_run_one` 과 같은 규약 (그쪽 주석이 근거를 든다)
    eff_i = min(entry_i + 1, exit_i)
    startup = 0.0
    if eff_i > entry_i:
        clean_eff_frozen, _a_eff = _value_on(
            legs, dataset, eff_i, entry_date, entry_fx, curve_idx=entry_i
        )
        startup = clean_eff_frozen - clean0

    out = []
    # the same chained roll-down as `_run_one` (see the comments there — the
    # frozen step prices with the PREVIOUS point's fixings, so a fresh CD
    # print falls into 평가, not 롤다운) — the trace grid is the thinned full
    # span, so each chain step is one grid step. 시드는 발효일이다.
    prev_i = eff_i
    prev_fx = _cd_fixings(dataset, eff_i)
    if eff_i > entry_i:
        prev_clean, _a_seed = _value_on(legs, dataset, eff_i, entry_date, prev_fx)
    else:
        prev_clean = clean0
    roll_cum = 0.0
    for i in _thin(list(range(entry_i, exit_i + 1)), MAX_POINTS):
        fx = _cd_fixings(dataset, i)
        clean, accrued = _value_on(legs, dataset, i, entry_date, fx)
        cash = _settled_to(legs, entry_date, dates[i], fx)
        val_total = clean - clean0
        carry = accrued - accrued0 + cash
        if i > prev_i:
            clean_frozen, _acc_f = _value_on(
                legs, dataset, i, entry_date, prev_fx, curve_idx=prev_i
            )
            roll_cum += clean_frozen - prev_clean
        start_cum = startup if i >= eff_i else 0.0
        # 진입일 행에서는 커서를 안 옮긴다 — `_run_one` 과 같은 이유
        if i >= eff_i:
            prev_i, prev_clean, prev_fx = i, clean, fx
        out.append(
            {
                "t": dates[i].isoformat(),
                "pnl": round(val_total + carry, 0),
                "valuation": round(val_total - roll_cum - start_cum, 0),
                "rolldown": round(roll_cum, 0),
                "carry": round(carry, 0),
                "startup": round(start_cum, 0),
                "npv": round(clean + accrued, 0),
                "cash": round(cash, 0),
            }
        )
    return out


# ── 일별 대사: KRD · Δbp · 손익 [OWNER, 2026-08-11] ──────────────────────────
#
# "직접 트레이딩 시스템과 대사하기 위해서" — for every business day of the
# book's life (capped, below): the book's per-tenor KRD on that day's own
# curve, the ACTUAL per-tenor par move (this is history — the Δbp are real
# quotes, not a scenario), the P&L-explain linear estimate (yesterday's KRD ×
# today's Δbp, the same start-of-day convention the simulation recon adopted
# 2026-08-10), and the day's actual P&L split 평가/캐리/롤다운.
#
# 세타의 귀속은 **평가일 기준 포워드**다 [OWNER, 2026-08-11 — "결제일 기준이
# 아니라 평가일 기준으로 계산하기 때문에, 금요일날 토일월의 캐리롤다운이
# 반영되어야 … 월요일에 값이 튀는 게 아니라 금요일에 튀어야"]. 즉 행 t 의
# 캐리·롤다운은 (t → 다음 영업일) 구간 몫이다 — 금요일 행이 토·일·월 사흘치
# 세타를 싣고, 월요일 행은 하루치만 싣는다. 평가(커브무브)는 여전히 전일
# 대비(백워드)다: 데스크 관행 그대로 "마켓무브는 어제 종가 대비, 세타는
# 오늘부터 내일까지". 수학적으로 백워드 세타(t−1→t, 전일 커브 동결)와 포워드
# 세타(t−1 행에서 계산한 t−1→t)는 같은 양이라, 이 전환은 세타 열을 한 칸
# 앞으로 옮기고 마지막 행에 오늘 커브의 다음-영업일 세타를 더한 것과 같다.
# 따라서 행 합("그날 손익") = 평가(백워드) + 캐리·롤다운(포워드)이고, 청산된
# 포지션의 행 합계는 포지션 스칼라와 정확히 일치하며, 아직 열린 포지션만
# 마지막 행의 "오늘 밤" 세타 하루만큼 스칼라보다 앞서간다(내일로 이월되는
# 몫 — 데스크의 YTD 도 같은 크기만큼 앞서간다). 진입일도 행을 갖는다:
# 평가 0, 첫날 밤 세타부터 booking — 시스템의 리스크-온 표기와 같다.
#
# KRD convention matches the simulation engine's DV01 sign: positive =
# receive-fixed gains when rates FALL, so the estimate is −KRD × Δbp. The
# recon KRD/세타 관행은 시뮬 recon(irs_pricer recon.py)도 동일하게 따른다
# [OWNER, 같은 날 "같이 맞춰"] — 세 표면(백테스트·시뮬·인포맥스)이 한 기준.

RECON_MAX_DAYS = 250          # business days of recon rows served (~1 year)
# Rough cap on extra valuations for KRD bumps. Measured ~0.5ms per valuation,
# so this is ~6s worst case (a six-position decade book shrinks to ~120 rows —
# still half again the owner's "80일이면 240줄" spec); a typical 1–3 position
# book is untouched by the cap and answers in well under a second.
RECON_VALUATION_BUDGET = 12_000


def _leg_swap(leg: Leg, entry_date: dt.date) -> VanillaSwap:
    """The valuation object for one leg — same construction as `_value_on`
    (see the FLOAT-tenor comment there; `TENOR_T[leg.tenor]` must stay the
    unrounded float)."""
    return VanillaSwap(
        tenor_years=TENOR_T[leg.tenor],
        notional=leg.notional,
        fixed_rate=leg.entry_rate,
        pay_fixed=leg.sign > 0,
        trade_date=entry_date,
    )


def bumped_par_curve(
    par: list[tuple[float, float]],
    label: str,
    cache: dict[str, "np.ndarray | None"],
) -> "np.ndarray | None":
    """`label` 파 노드만 1bp 올린 제로커브. 그날 그 노드가 없으면 `None`.

    `_book_recon` 의 KRD 범프가 쓰던 인라인 산술을 그대로 들어낸 것이다. 채권
    표의 **자산스왑 스왑 다리**도 이것을 부른다(`cashbond._swap_krd`) — KRD 의
    정의가 두 곳에 서면 두 표가 같은 리스크를 다르게 말한다. 이 리포의
    「두 번째 정의 금지」가 그 규칙이다.

    `cache` 는 **한 행 안에서** 공유한다. 부트스트랩이 비싸고 한 행의 여러
    포지션이 같은 노드를 흔들기 때문이다. 노드가 없는 라벨은 `None` 으로 캐시해
    포지션마다 다시 훑지 않는다.
    """
    if label in cache:
        return cache[label]
    t_l = TENOR_T[label]
    if not any(abs(t - t_l) < 1e-9 for t, _r in par):
        cache[label] = None          # 그날 노드가 없다 — KRD 0 (시뮬의 분할과 같은 규약)
        return None
    cache[label] = bootstrap_zero_curve(
        [(t, r + (1e-4 if abs(t - t_l) < 1e-9 else 0.0)) for t, r in par]
    )
    return cache[label]


def _book_recon(
    dataset: Dataset,
    positions: list[Position],
    spans: list[tuple[int, int, bool]],
    cache: dict[int, np.ndarray],
    with_krd: bool = True,
) -> dict:
    """The daily reconciliation block for the whole book.

    One extra pass over the window. Costs: per day, one base valuation per
    live position, one NEXT-BUSINESS-DAY valuation on the same curve (the
    forward theta — 평가일 기준 귀속, 모듈 주석), and one bumped-curve
    valuation per (tenor the position can feel × live position). The bump set
    per position is cut at its own longest remaining maturity — bumping 10Y
    for a 1Y book moves nothing and would triple the pass for a row of
    zeros. The window is the LAST `RECON_MAX_DAYS` business days of the book
    (a 10-year backtest reconciles its recent year, not 2,600 rows nobody
    scrolls), shrunk further only if the bump budget demands it.

    평가(백워드 마켓무브)는 전일 커브 재평가를 따로 하지 않는다: 전일 행이
    계산해 둔 포워드 세타가 곧 오늘의 백워드 세타이므로, 평가 = (오늘 실측
    변화) − (전일 행의 포워드 세타)로 나온다. 잘린 창의 첫 행만 전일 커브
    동결 재평가 한 번으로 시드한다.

    행의 `krd` 는 그 행의 추정에 쓴 **전일(start-of-day) KRD** 다 [OWNER,
    2026-08-11 — "전일걸 가져와서 붙이는게 대사하기 편하지 않을까"]: 한
    블록 안에서 krd × dbp = est 가 닫힌다. 진입일 행의 krd 는 0 이다(그날
    아침엔 포지션이 없었다 — 참인 기초 리스크). 마지막 날의 종가 KRD(다음
    영업일로 들고 가는 이월 리스크)는 rows 끝의 이월 앵커 행
    (`carryover: True`)이 싣고, 그 행의 손익 필드는 전부 None 이다 — 아직
    오지 않은 날의 손익을 0 이라고 말하지 않는다(공란 정책).
    """
    dates = dataset.dates
    labels = list(TENOR_T)  # insertion order == ascending tenor
    first = min(a for a, _b, _m in spans)
    last = max(b for _a, b, _m in spans)

    # per-position statics: legs at entry, span, longest maturity, bump set
    pos_info = []
    for pos, (entry_i, exit_i, matured) in zip(positions, spans):
        legs = _build_legs(dataset, pos.series_id, pos.notional, entry_i)
        for leg in legs:
            leg.sign *= pos.direction
        entry_date = dates[entry_i]
        matures = max(_maturity_of(entry_date, t) for t, _s in _legs_for(pos.series_id))
        # tenors this position can feel: every node up to and including the
        # first one at or beyond the longest remaining maturity AT ENTRY (the
        # set only shrinks as it ages; one fixed set keeps columns stable)
        tau = (matures - entry_date).days / 365.0
        bump: list[str] = []
        for lb in labels:
            bump.append(lb)
            if TENOR_T[lb] >= tau:
                break
        pos_info.append({
            "entry_i": entry_i, "exit_i": exit_i, "entry_date": entry_date,
            "legs": legs, "swaps": [_leg_swap(leg, entry_date) for leg in legs],
            "bump": bump,
            # 마지막 행에서 이 포지션을 **들고 가는가**. 청산도 만기도 아니고
            # 데이터가 끊겼을 뿐이면 내일 아침에도 그대로 들고 있다. 청산한
            # 북은 반대로 이월 리스크가 0 이어야 한다 [OWNER, 2026-08-14].
            "open_end": (
                not matured and pos.exit is None and exit_i == len(dates) - 1
            ),
            "prev": None,       # (clean + accrued + cash) — 어제의 실측 마크
            "prev_fwd": None,   # (carry_fwd, roll_fwd) — 어제 행이 booking 한 오늘치 세타
        })

    # 진입일부터 행이 선다 (평가 0 + 첫날 밤 포워드 세타 — 모듈 주석)
    start = max(first, last - RECON_MAX_DAYS + 1)
    # budget guard: shrink the window rather than serve a 30-second response
    cost_per_day = sum(len(p["bump"]) + 3 for p in pos_info) or 1
    max_days = max(30, RECON_VALUATION_BUDGET // cost_per_day)
    start = max(start, last - max_days + 1)

    def dirty_on(info: dict, on: dt.date, zc: np.ndarray, fx) -> tuple[float, float]:
        """(clean, accrued) of one position on an explicit curve."""
        curve = CurveBundle(on, zc, [])
        clean = accrued = 0.0
        for swap in info["swaps"]:
            res = value_booked_trade(swap, curve, fx)
            clean += res.clean_npv
            accrued += res.accrued_interest
        return clean, accrued

    rows: list[dict] = []
    prev_krd: dict[str, float] = {lb: 0.0 for lb in labels}
    for i in range(max(start - 1, first), last + 1):
        on = dates[i]
        fx = _cd_fixings(dataset, i)
        par = par_rates_at_index(dataset, i)
        zc_base = _curve_at(dataset, i, cache)
        bumped: dict[str, np.ndarray] = {}  # lazy, shared across positions
        # 이 행이 세타를 booking 하는 구간의 끝 = 다음 마크. 창 안쪽에서는
        # 데이터의 다음 행(공휴일 건너뜀 포함 — 실제 다음 평가일), 마지막
        # 행에서는 달력상 다음 영업일이다.
        nxt = dates[i + 1] if i < last else next_kr_business_day(dates[last])

        krd = {lb: 0.0 for lb in labels}
        day_carry = day_roll = day_val = day_start = 0.0
        for info in pos_info:
            if i < info["entry_i"] or i > info["exit_i"]:
                continue  # not yet on / closed & frozen: no risk, no day P&L
            clean, accrued = dirty_on(info, on, zc_base, fx)
            cash = _settled_to(info["legs"], info["entry_date"], on, fx)
            mark = clean + accrued + cash

            # 평가(백워드) = 실측 변화 − 어제 행이 booking 한 오늘치 세타.
            # 진입일은 0(그날 종가 par 로 struck), 잘린 창의 첫 행은 전일
            # 커브 동결 재평가로 시드(어제 행이 없어서).
            if i > info["entry_i"]:
                if info["prev_fwd"] is not None:
                    p_carry_f, p_roll_f = info["prev_fwd"]
                    day_val += (mark - info["prev"]) - (p_carry_f + p_roll_f)
                else:
                    # 전일 시점 픽싱으로(레코드 체인과 같은 규칙 — _run_one)
                    clean_frozen, _af = _value_on(
                        info["legs"], dataset, i, info["entry_date"],
                        _cd_fixings(dataset, i - 1), cache, curve_idx=i - 1,
                    )
                    day_val += clean - clean_frozen

            # 포워드 세타 (i → nxt), 오늘 커브 동결·오늘 알려진 픽싱으로.
            # 청산/만기 행에서는 없다 — 그 마크에서 얼어붙는 포지션이다.
            #
            # 두 물음이 다르다 [OWNER, 2026-08-14 — 현금채권 규약에 맞춤]:
            #
            #   `books_pnl`  그 밤이 **실현되는가**. 창 안에 다음 마킹이 있을
            #                때만이다. 마지막 행의 밤은 데이터 뒤라 실현될
            #                자리가 없다.
            #   `alive_fwd`  그 밤을 **들고 가는가**. 청산도 만기도 아니고
            #                데이터가 끊겼을 뿐이면 들고 간다 — 그때만 종가
            #                KRD 를 재서 이월 앵커에 싣는다.
            #
            # 종전에는 하나였고, 마지막 행의 세타가 손익 칸에 들어가 일별 합이
            # 딱 그 한 밤만큼 백테스트 총액을 넘었다 (실측 2026-08-14, 3Y
            # 아웃라이트 100억: 열린 북 합−총액 −314,139원 = 마지막 행 캐리+롤
            # −314,142원, 청산 북 −699,630원 = −699,630원). 대사표가 총액과
            # 안 맞으면 대사표가 아니다.
            books_pnl = i < info["exit_i"]
            alive_fwd = books_pnl or (i == last and info["open_end"])
            if alive_fwd:
                f_clean, f_accrued = dirty_on(info, nxt, zc_base, fx)
                f_cash = _settled_to(info["legs"], info["entry_date"], nxt, fx)
                carry_f = (f_accrued - accrued) + (f_cash - cash)
                roll_f = f_clean - clean
            if books_pnl:
                if i == info["entry_i"]:
                    # 거래일→발효일 한 밤 = 개시 [OWNER, 2026-08-14]. 이 밤은
                    # 스왑이 발효 전이라 `carry_f` 가 구조적으로 0 이고, 종전에는
                    # `roll_f` 가 통째로 롤다운 칸에 들어가 진입일 행에만 큰
                    # 롤다운이 섰다 (`_run_one` 의 개시 주석에 실측이 있다).
                    # 세타 자체는 그대로 booking 한다 — `prev_fwd` 가 내일
                    # 백워드 평가에서 빼는 값이므로 칸만 옮긴다.
                    day_start += carry_f + roll_f
                else:
                    day_carry += carry_f
                    day_roll += roll_f
                info["prev_fwd"] = (carry_f, roll_f)
            else:
                info["prev_fwd"] = (0.0, 0.0)
            info["prev"] = mark

            # KRD 는 **T+1(다음 영업일) 평가 기준**이다 [OWNER, 2026-08-11 —
            # 인포맥스 실측 대사: 3/9 1Y Rec 을 3/9 커브·3/10 평가로 재면
            # 12M 버킷이 49원(0.005%)까지 붙는다. 당일 평가로 재면 2,847원
            # 어긋나고 1.5Y 로 스필도 샌다]. 시뮬 엔진의 결제일 관행과도
            # 같아져 세 표면(백테스트·시뮬·인포맥스)이 한 기준이 됐다.
            # 청산 마크의 포지션은 내일 리스크가 없다 — KRD 0.
            if alive_fwd and with_krd:
                # 범프가 이 함수에서 제일 비싼 자리다 — 안 물었으면 안 돈다.
                base_dirty = f_clean + f_accrued
                for lb in info["bump"]:
                    zc_b = bumped_par_curve(par, lb, bumped)
                    if zc_b is None:
                        continue  # no node that day — KRD 0, like the sim's partition
                    b_clean, b_accrued = dirty_on(info, nxt, zc_b, fx)
                    krd[lb] += -((b_clean + b_accrued) - base_dirty)

        if i >= start:
            dbp: dict[str, float | None] = {}
            est: dict[str, float] = {}
            for lb in labels:
                vals = dataset.series.get(lb)
                cur = vals[i] if vals else None
                prv = vals[i - 1] if vals and i > 0 else None
                d = None if cur is None or prv is None else (cur - prv) * 100.0
                dbp[lb] = None if d is None else round(d, 2)
                est[lb] = 0.0 if d is None else -prev_krd[lb] * d
            total_est = round(sum(est.values()))
            row = {
                "t": on.isoformat(),
                # 그날 손익 = 평가(백워드) + 캐리·롤다운(포워드) — 평가일
                # 기준 데일리. 차트의 `d`(종가 대 종가)와는 세타 귀속이 하루
                # 어긋난다: 금요일 행이 주말치를 실으므로 여기가 튀고, 차트의
                # d 는 월요일에 튄다. 그게 이 관행의 정의다(모듈 주석).
                "actual": round(day_val + day_carry + day_roll + day_start),
                "valuation": round(day_val),
                "rolldown": round(day_roll),
                "carry": round(day_carry),
                # 개시 — 진입일 행에만 선다 (그 밖의 날은 0)
                "startup": round(day_start),
            }
            if with_krd:
                # 리스크 칸은 **잰 때만** 싣는다(위 `with_krd` 머리 — 안 잰 값을
                # 0 으로 채우면 다음 사람이 그것을 실측으로 읽는다).
                row.update({
                    # 전일(start-of-day) KRD — est 가 곱한 바로 그 값 (모듈 주석)
                    "krd": {lb: round(prev_krd[lb]) for lb in labels},
                    "dbp": dbp,
                    "est": {lb: round(est[lb]) for lb in labels},
                    "estTotal": total_est,
                    # 선형화 잔차: 추정(전일 KRD × Δbp)이 설명하는 대상은
                    # 평가(커브무브)뿐이다 — 세타를 섞어 빼던 종전 정의를 정리.
                    "residual": round(day_val) - total_est,
                })
            rows.append(row)
        prev_krd = krd

    # 이월 앵커 행 [OWNER, 2026-08-11]: 마지막 날의 종가 KRD(다음 영업일
    # 기준 재평가 — 곧 내일 아침 들고 갈 리스크). 날짜는 마지막 행이 세타를
    # booking 한 구간의 끝(`nxt`)이고, 손익 필드는 전부 None — 공란 정책.
    if rows:
        anchor = {
            "t": nxt.isoformat(),
            "actual": None,
            "valuation": None,
            "rolldown": None,
            "carry": None,
            "startup": None,
            "carryover": True,
        }
        if with_krd:
            # 이월 앵커가 싣는 것은 **종가 KRD 하나**다 — 그것을 안 쟀으면
            # 이 행은 날짜뿐이고, 0 을 적어 «리스크가 없다» 고 말하지 않는다.
            anchor.update({
                "krd": {lb: round(krd[lb]) for lb in labels},
                "dbp": {}, "est": {}, "estTotal": None, "residual": None,
            })
        rows.append(anchor)

    return {
        "tenors": labels,
        "rows": rows,
        "truncated": start > first,
    }


def run_backtest(dataset: Dataset, positions: list[Position]) -> dict:
    """Revalue a BOOK of positions daily and sum them.

    The book's window is the earliest entry to the latest exit, and every
    position is sampled on the same dates so the totals add up point for point
    — sampling each on its own grid and summing would compare figures from
    different days.
    """
    if not positions:
        raise BacktestError("at least one position is required")
    if len(positions) > MAX_POSITIONS:
        raise BacktestError(f"at most {MAX_POSITIONS} positions")

    dates = dataset.dates
    # the union of the positions' ACTUAL lives, maturity cap included
    spans = [_span_of(dataset, p) for p in positions]
    first = min(a for a, _b, _m in spans)
    last = max(b for _a, b, _m in spans)
    sample = _thin(list(range(first, last + 1)), MAX_POINTS)

    # One curve per date for the whole run, shared by every position (see
    # `_curve_at`). Scoped to this call so a data refresh cannot be served a
    # stale curve.
    cache: dict[int, np.ndarray] = {}

    records = []
    series: list[dict[int, float]] = []
    prevs: list[dict[int, float]] = []
    for pos in positions:
        rec, own, prev_day = _run_one(dataset, pos, sample, cache)
        records.append(rec)
        series.append(own)
        prevs.append(prev_day)

    # The published line, with each point's CHANGE from the one before it.
    #
    # Computed here and not in the browser (§16). The rule is not ceremony:
    # `PreviewChart` carries the same note because differencing a rounded
    # series client-side gives a number that disagrees with the difference of
    # the two figures the reader can see.
    #
    # `d` is the step BETWEEN PUBLISHED POINTS, which is a day only while the
    # series is unthinned. `daily` says which — a ten-year book is ~2,600
    # business days thinned to 400, and calling a 6-day move "당일 변화" there
    # would be a plain lie.
    points = []
    for i in sample:
        total = round(sum(s[i] for s in series), 0)
        # `d` is the change over ONE BUSINESS DAY, always — the position is
        # valued on `i` and on `i-1` regardless of how far apart the published
        # points are. Differenced here rather than in the browser (§16):
        # subtracting a series that has already been rounded to the won gives a
        # figure that disagrees with the two the reader can see.
        d = (
            None
            if i == first
            else round(total - sum(pd.get(i, 0.0) for pd in prevs), 0)
        )
        points.append({"t": dates[i].isoformat(), "pnl": total, "d": d})

    pnls = [p["pnl"] for p in points]
    return {
        "positions": records,
        "from": dates[first].isoformat(),
        "to": dates[last].isoformat(),
        # Whether every business day is PUBLISHED. `d` is a one-day change
        # either way now; this only says whether the LINE is drawn at full
        # resolution, which the chart's own density depends on.
        "complete": len(sample) == last - first + 1,
        "points": points,
        "pnl": pnls[-1] if pnls else 0.0,
        "maxProfit": max(pnls) if pnls else 0.0,
        "maxLoss": min(pnls) if pnls else 0.0,
    }


def book_recon(
    dataset: Dataset, positions: list[Position], with_krd: bool = True
) -> dict:
    """The 일별 대사 block, as its own call [OWNER, 2026-08-11].

    Separate from `run_backtest` ON PURPOSE: the KRD bump pass costs several
    times the backtest itself, and every property test that replays books
    would pay it for rows it never reads. The ENDPOINT merges this under
    `recon` in the same response; the engine tests call whichever they test.

    ## `with_krd=False` — **돈만 필요할 때** [2026-09-04]

    MR 회계는 이 블록에서 **하루의 돈**(평가·캐리·롤다운)만 읽어 봉에 얹는다.
    그런데 범프 한 번이 그 일의 대부분이라, 퓨처스왑 52거래의 IRS 다리를 거래마다
    세우면 전략 라우트가 24초가 된다(실측 2026-09-04: 42봉 한 거래에 465ms).

    끄면 **`krd`·`dbp`·`est`·`estTotal`·`residual` 을 아예 안 싣는다.** 0 으로
    채우지 않는 이유는 이 리포의 공란 정책 그대로다 — 「그날 KRD 가 0 이었다」는
    다른 말이고, 안 잰 값을 0 이라 적으면 다음 사람이 그것을 실측으로 읽는다.
    """
    if not positions:
        raise BacktestError("at least one position is required")
    if len(positions) > MAX_POSITIONS:
        raise BacktestError(f"at most {MAX_POSITIONS} positions")
    spans = [_span_of(dataset, p) for p in positions]
    cache: dict[int, np.ndarray] = {}
    return _book_recon(dataset, positions, spans, cache, with_krd=with_krd)


def _quoted_value(dataset: Dataset, series_id: str, i: int) -> float | None:
    """The instrument's own quoted number on that row — % for an outright, bp
    for a spread/fly. Read for display beside the P&L, never used to compute
    it: the P&L comes from revaluation and these two are allowed to tell
    slightly different stories (that difference IS carry and roll)."""
    from .derive import series_values

    try:
        vals = series_values(dataset, series_id)
    except KeyError:
        return None
    v = vals[i]
    return None if v is None else round(v, 4)
