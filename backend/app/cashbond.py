"""Cash Bond — 민평 커브에서 par 로 발행한 3개월 이표채를 매일 재평가한다
[OWNER, 2026-08-14].

Backtest 섹션의 여섯 번째 종목군이다. IRS 백테스트(`app/backtest.py`)가 스왑에
대해 하는 일을 현금채권에 대해 한다 — 진입일에 그날 par 로 스트라이크하고,
그 뒤로 매일 그날의 시장으로 다시 값을 매기고, 손익을 칸으로 쪼갠다.

## 규약 [OWNER, 2026-08-14]

    표면금리   진입일 민평 (그 종목군 · 그 만기)
    할인       **단일 민평수익률** — 잔존만기에 보간한 값 하나로 전 현금흐름
    이표       3개월 (스왑과 기준을 맞춘다)
    조달       Setting 탭의 기준 시계열 + 스프레드, Cash Bond 에만 차감

쿠폰 = 수익률이므로 **진입일 가격은 정확히 par** 다. 연금 항등식이 그렇게
만든다: c=y/4, q=1+y/4 이면 Σ c·q^-k + q^-n = 1. 이 성질이 이 화면의 기준선
이고, `test_cashbond.py` 가 소수 열두 자리까지 못박는다.

## 왜 제로커브가 아닌가 [OWNER, 2026-08-14 — 선택]

민평은 par 호가가 아니라 **매매수익률**이다. 시장이 그 숫자 하나로 값을
주고받으므로 그 관행을 그대로 옮긴다. 스왑(제로커브 부트스트랩)과 할인
기계가 달라지는 것은 알고 받아들인 대가이고, 자산스왑 행이 두 기계의 차이를
그대로 보여 준다.

## 스케줄은 이상화돼 있다

이 채권은 실재하는 종목(ISIN)이 아니라 **커브 노드의 합성물**이다. 3Y 를
사면 만기는 진입일+3년이고 이표는 정확히 1/4년 간격이다 — 영업일 보정도
스텁도 없다. 실물 종목이라면 틀렸겠지만 여기서 재는 것은 "그 만기의 민평이
어떻게 움직였나" 이고, 이상화된 격자라야 진입일 par 가 정확해지고 롤다운이
매끄럽다. 실제 발행 종목을 붙일 때가 오면 `pos_krw_bond`(현재 0행)가 그
자리다.

## 손익 분해 [OWNER, 2026-08-14 — 4분해]

    평가     민평 수익률이 움직인 몫 (clean 변화에서 롤다운을 뺀 나머지)
    캐리     쿠폰 — 경과이자 증가분 + 이미 받은 이표
    롤다운   커브가 멈춰도 잔존만기가 줄며 생기는 몫 (전일 커브 동결, 체인)
    조달     원금을 조달한 비용 (음수로 표시)

`app/backtest.py` 의 3분해와 같은 항등식이다. 개시(거래일→발효일) 칸이 없는
이유는 이 채권이 **진입일에 발행돼 진입일부터 경과이자가 붙기** 때문이다 —
결제 시차가 없으므로 셀 밤도 없다. 자산스왑 행에서는 스왑 다리가 자기 개시를
싣고 오므로 그 칸이 산다.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

from . import creditmatrix as cm
from . import funding as fd
from .creditmatrix import CreditMatrix, CreditMatrixError

log = logging.getLogger("app.cashbond")

#: 이표 주기 (연 4회) [OWNER — "3개월 이표채라고 가정해서 스왑과 기준을 맞춘다"]
FREQ = 4

#: 부동소수 경계에서 "오늘이 이표일" 을 판정하는 폭. 1e-9년 = 0.03초.
_EPS = 1e-9

#: 손익 라인의 발행 점 수 — `app/backtest.py:MAX_POINTS` 와 같은 이유·같은 값.
MAX_POINTS = 400

#: 한 번에 재는 포지션 수 상한 — 같은 이유.
MAX_POSITIONS = 12

#: 자산스왑이 설 수 있는 테너 = 민평 격자 ∩ IRS 격자. 채권의 2.5Y·20Y·30Y 는
#: 대응 IRS 노드가 없고, IRS 의 4Y·6Y·8Y·9Y 는 대응 민평 노드가 없다. 보간으로
#: 메우면 "같은 만기 두 상품" 이라는 이 행의 전제가 깨지므로 세우지 않는다.
ASW_TENORS: list[str] = ["3M", "6M", "9M", "1Y", "1.5Y", "2Y", "3Y", "5Y", "7Y", "10Y"]

KIND_CASH = "CB"
KIND_ASW = "ASW"


class CashBondError(Exception):
    """요청을 실행할 수 없다 — 없는 종목군/테너이거나 데이터 밖의 날짜다."""


@dataclass(frozen=True)
class BondPosition:
    kind: str          # "CB" | "ASW"
    bond_type: str     # "KTB" …
    tenor: str         # "3Y"
    direction: int     # +1 매수, -1 매도
    notional: float
    entry: dt.date
    exit: dt.date | None = None

    @property
    def id(self) -> str:
        return f"{self.kind}:{self.bond_type}:{self.tenor}"


# ── 가격 ────────────────────────────────────────────────────────────────────


def periods_for(tenor: str) -> int:
    """그 테너의 이표 횟수. 3M→1, 1.5Y→6, 2.5Y→10, 30Y→120."""
    years = cm.TENOR_YEARS.get(tenor)
    if years is None:
        raise CashBondError(f"알 수 없는 테너입니다: {tenor}")
    return max(1, round(years * FREQ))


def price(
    y: float, coupon: float, n: int, elapsed: float
) -> tuple[float, float, float, float]:
    """(dirty, 경과이자, 결제된 이표, **상환된 액면**) — 액면 1 기준.

    `y`·`coupon` 은 소수(0.0378), `elapsed` 는 진입일로부터 흐른 년수(ACT/365).
    현금흐름 k 는 진입일로부터 k/4년에 있고, 마지막에 액면 1 이 함께 온다.
    할인은 이표 주기 복리 — `(1+y/4)^(-4τ)`, τ 는 그 현금흐름까지 남은 년수다.

    `elapsed=0` · `coupon=y` 면 dirty 는 정확히 1.0 이다(연금 항등식). 이표일을
    막 지난 순간의 경과이자는 0 이고, 지급 직전에는 한 기 전액에 수렴한다.

    ## 셋째 값은 이표만이 아니라 **원금 상환까지** 포함한다

    2026-08-14 에 이것이 빠져 있어서 **만기까지 들고 있으면 원금만큼 손실**로
    찍혔다. `dirty` 는 아직 안 온 현금흐름의 현재가치이므로 만기에 0 이 되는데,
    그때 나간 액면 1 이 결제현금에 안 잡히면 `dirty + 현금` 이 1.04 에서 0.04 로
    떨어진다(1Y·쿠폰 4% 실측). 손익 = Δdirty + 결제현금 이라는 이 화면의 항등식
    자체는 옳고, **결제현금의 정의가 좁았다**.

    교과서도 지수 계산 규칙도 같은 말을 한다 — FTSE Russell 의 Guide to
    Calculation 은 total return 의 cash 항을 "the sum of any coupons **and any
    principal repayments** … including cumulative cash from principal
    redemption" 로 정의한다. 스왑 쪽에는 이 결함이 없다: 바닐라 IRS 는 원금
    교환이 없어 잃을 원금이 애초에 없다(2026-08-14 실측으로 확인).

    ## 이표와 액면을 **따로** 돌려주는 이유

    총액에는 둘이 같이 들어가지만 **분해에서는 서로 다른 칸**이다. 이표는
    소득(캐리)이고 상환된 액면은 자본 회수 — par 로 사서 par 를 돌려받은 것이라
    가격 쪽에 붙어야 한다. 한 값으로 합쳐 돌려주었더니 만기 보유 3Y 의 캐리가
    110억, 롤다운이 −102억으로 찍혔다(실측). 총액은 맞고 칸만 틀린, 이 리포가
    오늘 오전에도 한 번 겪은 결함이다.
    """
    q = 1.0 + y / FREQ
    c = coupon / FREQ
    dirty = 0.0
    paid_count = 0
    for k in range(1, n + 1):
        tau = k / FREQ - elapsed
        if tau <= _EPS:
            paid_count = k
            continue
        cf = c + (1.0 if k == n else 0.0)
        dirty += cf * q ** (-FREQ * tau)
    matured = paid_count >= n
    # 현재 이표기간에서 흐른 비율. paid_count 가 직전 이표이므로 [0,1) 이다.
    # 만기 뒤에는 붙을 이표가 없다 — 이 가드가 없으면 `frac` 이 무한정 자란다.
    frac = 0.0 if matured else elapsed * FREQ - paid_count
    return dirty, c * max(0.0, frac), c * paid_count, 1.0 if matured else 0.0


# ── 백테스트 ────────────────────────────────────────────────────────────────


def _entry_index(m: CreditMatrix, d: dt.date) -> int:
    """진입일 이상의 첫 영업일 자리. 민평 달력 밖이면 에러."""
    for i, x in enumerate(m.dates):
        if x >= d:
            return i
    raise CashBondError(f"민평 데이터 이후의 날짜입니다: {d} (마지막 {m.dates[-1]})")


def _span(m: CreditMatrix, pos: BondPosition) -> tuple[int, int, bool]:
    """(진입 자리, 종료 자리, 만기도달 여부). 종료는 만기에서 잘린다 — 만기가
    지난 채권을 계속 마킹하면 백테스트가 스스로를 미화한다."""
    if not m.has(pos.bond_type, pos.tenor):
        raise CashBondError(
            f"{cm.BOND_TYPES.get(pos.bond_type, pos.bond_type)} 에는 {pos.tenor} 민평이 없습니다."
        )
    entry_i = _entry_index(m, pos.entry)
    years = cm.TENOR_YEARS[pos.tenor]
    maturity = m.dates[entry_i] + dt.timedelta(days=round(years * 365))

    last = len(m.dates) - 1
    exit_i = last
    if pos.exit is not None:
        for i in range(len(m.dates) - 1, -1, -1):
            if m.dates[i] <= pos.exit:
                exit_i = i
                break
        else:
            raise CashBondError(f"청산일이 민평 데이터보다 앞섭니다: {pos.exit}")
    matured = False
    for i in range(entry_i, exit_i + 1):
        if m.dates[i] >= maturity:
            exit_i, matured = i, True
            break
    if exit_i < entry_i:
        raise CashBondError("청산일이 진입일보다 앞섭니다.")
    return entry_i, exit_i, matured


def _thin(idx: list[int], keep: int) -> list[int]:
    """`app/backtest.py:_thin` 과 같은 규칙 — 양 끝은 반드시 남는다."""
    if len(idx) <= keep:
        return idx
    step = (len(idx) - 1) / (keep - 1)
    out = sorted({idx[round(k * step)] for k in range(keep)} | {idx[0], idx[-1]})
    return out


@dataclass
class _BondLeg:
    """한 포지션의 채권 다리를 그린 것 — 자산스왑도 이 다리를 그대로 쓴다."""

    coupon: float
    n: int
    years: float
    entry_i: int
    exit_i: int
    matured: bool


def _bond_leg(m: CreditMatrix, pos: BondPosition) -> _BondLeg:
    entry_i, exit_i, matured = _span(m, pos)
    years = cm.TENOR_YEARS[pos.tenor]
    coupon = cm.yield_at(m, pos.bond_type, entry_i, years)
    return _BondLeg(coupon, periods_for(pos.tenor), years, entry_i, exit_i, matured)


def run_bond_leg(
    m: CreditMatrix,
    pos: BondPosition,
    leg: _BondLeg,
    sample: list[int],
    spec: fd.FundingSpec,
) -> tuple[dict, dict[int, float], dict[int, float]]:
    """채권 다리 하나를 매일 재평가한다.

    (요약, {자리: 손익}, {자리: **전영업일** 손익}) 을 돌려준다. 셋째가 있는
    이유는 차트의 당일 변화 때문이다 — `live` 가 이미 발행점 하루 전까지 값을
    매기고 있으므로(아래) 공짜에 가깝고, 없으면 화면이 발행점 사이의 차이를
    "당일" 이라고 부르게 된다. IRS 쪽 `_run_one` 의 `prev_day` 와 같은 규약이다.

    부호 규약은 IRS 쪽과 같다: `direction` 이 +1 이면 매수(금리가 내리면 이익),
    −1 이면 매도. 조달은 **매수에만** 붙는다 — 공매도는 돈을 빌리는 것이 아니라
    채권을 빌리는 것이고, 그 비용(대차료)은 이 화면이 아는 값이 아니다.
    """
    N = pos.notional * pos.direction
    entry_i, exit_i = leg.entry_i, leg.exit_i
    entry_date = m.dates[entry_i]

    # 진입일: 쿠폰 = 그날 수익률이므로 dirty 는 정확히 1.0, 경과이자 0.
    dirty0, accrued0, _cp0, _rd0 = price(leg.coupon, leg.coupon, leg.n, 0.0)
    clean0 = dirty0 - accrued0

    live = sorted(
        {i for i in sample if entry_i <= i <= exit_i}
        | {exit_i}
        | {i - 1 for i in sample if entry_i < i <= exit_i}
    )

    own: dict[int, float] = {}
    last = last_val = last_roll = last_carry = last_fund = 0.0
    prev_i, prev_clean = entry_i, clean0
    roll_cum = 0.0

    for i in live:
        elapsed = (m.dates[i] - entry_date).days / 365.0
        remaining = max(0.0, leg.years - elapsed)
        y = cm.yield_at(m, pos.bond_type, i, remaining) if remaining > 0 else leg.coupon
        dirty, accrued, coupons, redeemed = price(y, leg.coupon, leg.n, elapsed)
        # **상환된 액면은 가격 쪽이다** — par 로 사서 par 를 돌려받은 것이라
        # 소득이 아니라 자본 회수다. 여기 안 넣고 캐리에 두면 만기에 캐리가
        # 액면만큼 부풀고 롤다운이 그만큼 음수가 된다(price 독스트링의 실측).
        clean = dirty - accrued + redeemed

        if i > prev_i:
            # 롤다운 = **전일 커브**로 오늘의 (짧아진) 채권을 다시 값 매긴 것.
            # Tuckman 의 불변 기간구조 가정이고, IRS 쪽 체인과 같은 규약이다.
            y_frozen = (
                cm.yield_at(m, pos.bond_type, prev_i, remaining)
                if remaining > 0
                else leg.coupon
            )
            d_f, a_f, _cp_f, rd_f = price(y_frozen, leg.coupon, leg.n, elapsed)
            roll_cum += (d_f - a_f + rd_f) - prev_clean

        # 조달은 **초기 투자금액**에 붙는다 [OWNER, 2026-08-14 — "조달은 초기
        # 투자 금액 기준으로 붙여야 함" · 2026-09-09 — "실제로 Bond를 매입하는데
        # 들어간 비용이 조달원금"]. **이 모형에서 그 둘은 같은 수다**:
        #
        #     진입일 dirty = price(y, coupon=y, n, elapsed=0) = 1.000000000000
        #
        # 진입일에 쿠폰을 그날 수익률로 스트럭하는 합성채라(위 `dirty0` 줄) 매수
        # 금액이 **정확히 액면**이다 — 연금 항등식이고, 실측으로도 소수 12자리까지
        # 1.0 이다(y = 2.5%·3.78%·5% 에서 확인, 2026-09-09).
        #
        # ⚠ krw-crs 레인이 「할인채면 조달이 1% 남짓 과다 계상된다」를 올렸는데
        # (`PROMPT_v2_accounting_2026-09-09.md` §4), **이 모형에는 할인채가
        # 없다.** 실제 온더런 종목을 그 시장가로 사는 판을 세우면 그 지적이 살아
        # 나므로, 그때는 이 줄이 `pos.notional × dirty0` 이 되어야 한다.
        #
        # 받은 이표를 굴리지 않는 것과 앞뒤가 맞는다 [OWNER, 2026-08-14 — "이건
        # 굴리는거 상정 안 하긴 해"]: 매수금액을 조달해서 사고, 들어온 현금은
        # 0% 로 그대로 쌓인다. 손익은 그만큼 보수적이다(3Y 쿠폰 10.95억을 2.8%
        # 로 굴렸다면 43M, 손익의 3.9%).
        #
        # 잠깐 잔액 기준으로 바꿨다가 오너가 되돌렸다. 들어온 이표가 차입을
        # 갚아 나가는 처리였고 크기도 쟀는데(3Y 만기 보유에서 +42,712,000,
        # 손익의 3.9%), 데스크가 조달을 잡는 방식은 텀 레포로 매수금액을
        # 통째로 조달하는 쪽이다 — 이표를 받아 그때그때 차입을 갚는 것은 별개의
        # 자금관리이지 이 포지션의 비용이 아니다. 되돌릴 일이 생기면
        # `git show 021f2894` 에 그 구현과 실측이 있다.
        #
        # 매도는 위 주석대로 0.
        funding = (
            fd.cost_between(spec, entry_date, m.dates[i], pos.notional)
            if pos.direction > 0
            else 0.0
        )

        val_total = (clean - clean0) * N
        carry = (accrued - accrued0 + coupons) * N
        own[i] = last = val_total + carry - funding
        last_val = val_total - roll_cum * N
        last_roll = roll_cum * N
        last_carry, last_fund = carry, funding
        prev_i, prev_clean = i, clean

    def at(i: int) -> float:
        if i < entry_i:
            return 0.0
        if i > exit_i:
            return last
        return own[i]

    record = {
        "coupon": round(leg.coupon * 100, 4),
        "entryYield": round(leg.coupon * 100, 4),
        "exitYield": round(
            cm.yield_at(
                m, pos.bond_type, exit_i,
                max(0.0, leg.years - (m.dates[exit_i] - entry_date).days / 365.0),
            ) * 100,
            4,
        ),
        "valuation": round(last_val, 0),
        "rolldown": round(last_roll, 0),
        "carry": round(last_carry, 0),
        "funding": round(-last_fund, 0),  # 화면에서 빼는 값이라 부호를 여기서 준다
        "pnl": round(last, 0),
        "matured": leg.matured,
    }
    return (
        record,
        {i: at(i) for i in sample},
        {i: at(i - 1) for i in sample if i - 1 >= 0},
    )


# ── 자산스왑 ────────────────────────────────────────────────────────────────


def _irs_index_map(m: CreditMatrix, dataset) -> dict[int, int]:
    """민평 자리 → IRS 자리. 민평 달력은 IRS 달력의 **부분집합**이다(실측
    2026-08-14: 겹치는 1,624일 전부 포함, 반대로 IRS 에만 있는 날이 15일 —
    연말 폐장일 등). 그래서 이 사상은 전사이고, 없는 날이 나오면 그것은
    데이터가 변했다는 뜻이므로 조용히 넘기지 않고 세운다."""
    pos = {d: i for i, d in enumerate(dataset.dates)}
    out: dict[int, int] = {}
    for i, d in enumerate(m.dates):
        j = pos.get(d)
        if j is not None:
            out[i] = j
    return out


# ── 북 ──────────────────────────────────────────────────────────────────────


def run_backtest(
    m: CreditMatrix,
    dataset,
    positions: list[BondPosition],
    spec: fd.FundingSpec,
) -> dict:
    """포지션 여럿을 매일 재평가해 합친다 — `app/backtest.py:run_backtest` 의
    현금채권 판이다. 창은 가장 이른 진입부터 가장 늦은 종료까지이고, 모든
    포지션을 **같은 날짜들**에서 재서 합계가 점마다 맞는다."""
    if not positions:
        raise CashBondError("포지션이 하나는 있어야 합니다.")
    if len(positions) > MAX_POSITIONS:
        raise CashBondError(f"포지션은 최대 {MAX_POSITIONS}개입니다.")
    # 매수뿐이다 [OWNER, 2026-08-14 — "국고채는 매도는 없는거고"]. 현금채권을
    # 공매도하려면 채권을 빌려야 하고, 그 대차료는 이 화면이 아는 값이 아니다 —
    # 모르는 비용을 0 으로 두고 계산하면 공매도가 늘 이기는 백테스트가 된다.
    # 화면에는 고를 것 자체가 없으므로 여기 걸리는 것은 손으로 만든 URL 뿐이고,
    # 그때 조용히 값을 내놓는 것보다 거절하는 편이 옳다.
    for p in positions:
        if p.direction != 1:
            raise CashBondError(
                "현금채권은 매수만 됩니다 — 공매도는 대차료가 필요한데 그 값이 없습니다."
            )
    spec = spec.validated()

    legs = [_bond_leg(m, p) for p in positions]
    first = min(l.entry_i for l in legs)
    last = max(l.exit_i for l in legs)
    sample = _thin(list(range(first, last + 1)), MAX_POINTS)

    # IRS 달력 사상은 자산스왑 행이 있을 때만 세운다 — 현금채권만 있는 북은
    # IRS 데이터셋 없이도 돌아야 하고(게이트가 합성 민평으로 그렇게 돈다),
    # 없는 의존을 요구하면 그 자체가 결함이다.
    needs_swap = any(p.kind == KIND_ASW for p in positions)
    if needs_swap and dataset is None:
        raise CashBondError("자산스왑 행에는 IRS 데이터셋이 필요합니다.")
    imap = _irs_index_map(m, dataset) if needs_swap else {}
    swap_cache: dict[int, object] = {}

    records: list[dict] = []
    series: list[dict[int, float]] = []
    prevs: list[dict[int, float]] = []

    for p, leg in zip(positions, legs):
        rec, own, own_prev = run_bond_position(
            m, dataset, p, leg, sample, spec, imap, swap_cache
        )
        records.append(rec)
        series.append(own)
        prevs.append(own_prev)

    # 손익 라인. `d` 는 **늘 1영업일** 변화다 — 발행점 사이가 아니라.
    # 창이 MAX_POINTS 를 넘어 솎이면 점 사이가 며칠씩 벌어지는데, 그 간격을
    # "당일" 이라고 부르면 거짓말이 된다. 그래서 각 포지션이 발행점의 **전날**
    # 손익도 같이 내고(`run_bond_leg` 의 셋째 반환값), 여기서 그 차를 쓴다.
    # 값싸다: `live` 가 이미 그 날짜들을 평가하고 있다.
    #
    # 브라우저에서 빼지 않는 것도 규약이다(§16) — 이미 원 단위로 반올림된
    # 계열을 화면에서 차분하면 읽는 사람이 보는 두 숫자와 안 맞는 값이 나온다.
    points = []
    for k, i in enumerate(sample):
        total = round(sum(s.get(i, 0.0) for s in series), 0)
        d = (
            None
            if k == 0
            else round(total - sum(pd.get(i, 0.0) for pd in prevs), 0)
        )
        points.append({"t": m.dates[i].isoformat(), "pnl": total, "d": d})

    pnls = [p["pnl"] for p in points]
    return {
        "positions": records,
        "from": m.dates[first].isoformat(),
        "to": m.dates[last].isoformat(),
        "complete": len(sample) == last - first + 1,
        "points": points,
        "pnl": pnls[-1] if pnls else 0.0,
        "maxProfit": max(pnls) if pnls else 0.0,
        "maxLoss": min(pnls) if pnls else 0.0,
        "funding": fd.provenance(spec),
    }


def run_bond_position(
    m: CreditMatrix,
    dataset,
    pos: BondPosition,
    leg: _BondLeg,
    sample: list[int],
    spec: fd.FundingSpec,
    imap: dict[int, int],
    swap_cache: dict,
) -> tuple[dict, dict[int, float], dict[int, float]]:
    """한 줄 → (기록, {자리: 손익}, {자리: 전영업일 손익}).

    현금채권은 채권 다리 하나, 자산스왑은 거기에 같은 명목의 페이 고정을 더한
    둘이다(`_swap_leg` 의 par-par 규약). 두 다리를 합치는 산술이 **한 군데에만**
    있어야 하는 이유 [2026-08-21]: 혼합 북(`app/mixedbook.py`)이 같은 줄을 다른
    달력 위에서 세는데, 그 병합을 저쪽에 한 벌 더 적으면 같은 자산스왑이 두
    화면에서 다른 수를 낼 수 있다 — 이 리포가 claim-vs-behaviour 결함이라 이름
    붙여 둔 것이 정확히 그것이다.
    """
    rec, own, own_prev = run_bond_leg(m, pos, leg, sample, spec)
    rec = {
        "id": pos.id,
        "kind": pos.kind,
        "bondType": pos.bond_type,
        "label": instrument_label(pos.kind, pos.bond_type, pos.tenor),
        "tenor": pos.tenor,
        "direction": pos.direction,
        "notional": pos.notional,
        "entry": m.dates[leg.entry_i].isoformat(),
        "exit": m.dates[leg.exit_i].isoformat(),
        "closed": leg.exit_i < len(m.dates) - 1,
        **rec,
        # 스왑 다리가 없는 행은 개시가 없다 — 이 채권은 진입일에 발행돼
        # 진입일부터 경과이자가 붙으므로 결제 시차의 밤 자체가 없다.
        "startup": 0.0,
        "swapPnl": None,
    }

    if pos.kind == KIND_ASW:
        srec, sown, sprev = _swap_leg(dataset, pos, leg, m, sample, imap, swap_cache)
        for key in ("valuation", "rolldown", "carry", "startup"):
            rec[key] = round(rec[key] + srec[key], 0)
        rec["swapPnl"] = srec["pnl"]
        rec["swapEntryRate"] = srec["entryRate"]
        rec["aswSpread"] = round((leg.coupon * 100 - srec["entryRate"]) * 100, 2)
        for i in own:
            own[i] += sown.get(i, 0.0)
        for i in own_prev:
            own_prev[i] += sprev.get(i, 0.0)
        rec["pnl"] = round(own[sample[-1]] if sample else 0.0, 0)

    return rec, own, own_prev


def _swap_leg(
    dataset, p: BondPosition, leg: _BondLeg, m: CreditMatrix,
    sample: list[int], imap: dict[int, int], cache: dict,
) -> tuple[dict, dict[int, float], dict[int, float]]:
    """자산스왑의 IRS 다리 — 채권 매수에 **같은 명목**의 페이 고정 [OWNER,
    2026-08-14 — par-par]. DV01 중립이 아닌 이유는 진입일 스프레드가 표에 보이는
    민평 − IRS 그대로 읽히기 때문이고, 대가는 채권이 par 에서 멀어지면 남는
    잔여 금리노출이다(채권 DV01 은 단일수익률, 스왑 PV01 은 제로커브).

    기존 IRS 백테스트 엔진을 그대로 부른다 — 이 다리는 그냥 스왑이고, 개시
    칸까지 그쪽 규약을 물려받는다."""
    from .backtest import Position, _run_one

    if p.tenor not in ASW_TENORS:
        raise CashBondError(
            f"{p.tenor} 는 자산스왑을 세울 수 없습니다 — 채권과 IRS 양쪽에 있는 "
            f"만기만 가능합니다 ({'·'.join(ASW_TENORS)})."
        )
    if leg.entry_i not in imap or leg.exit_i not in imap:
        raise CashBondError("민평 날짜가 IRS 달력에 없습니다 — 데이터를 확인하세요.")

    spos = Position(
        series_id=p.tenor,
        direction=p.direction,   # 채권 매수 = 스왑 페이
        notional=p.notional,
        entry=m.dates[leg.entry_i],
        exit=m.dates[leg.exit_i],
    )
    isample = sorted({imap[i] for i in sample if i in imap})
    rec, own, prev = _run_one(dataset, spos, isample, cache)
    back = {i: own.get(imap[i], 0.0) for i in sample if i in imap}
    # 전영업일도 **IRS 달력의** 하루 전이다. 민평 달력에 없는 날(연말 폐장일
    # 등 15일)이 그 사이에 끼면 채권 다리와 하루가 어긋나는데, 그 어긋남은
    # 스왑이 실제로 그날 값이 매겨졌다는 사실 그대로다.
    back_prev = {i: prev.get(imap[i], 0.0) for i in sample if i in imap}
    rec["entryRate"] = rec["legs"][0]["entryRate"] if rec["legs"] else 0.0
    return rec, back, back_prev


# ── 표 ──────────────────────────────────────────────────────────────────────


def instrument_label(kind: str, bond_type: str, tenor: str) -> str:
    """화면 이름. 종목군 이름은 오너가 부르는 그대로다 (creditmatrix.BOND_TYPES)."""
    name = cm.BOND_TYPES.get(bond_type, bond_type)
    return f"{name} {tenor}" if kind == KIND_CASH else f"{name} {tenor} 자산스왑"


def _basis_indices(m: CreditMatrix) -> dict[str, int | None]:
    """d1 / mtd / ytd 각각의 **직전 종가** 자리 — `derive.basis_dates` 와 같은
    정의다(그 기간이 시작되기 전 마지막 영업일)."""
    asof = m.asof

    def last_before(cutoff: dt.date) -> int | None:
        j = None
        for i, d in enumerate(m.dates):
            if d < cutoff:
                j = i
            else:
                break
        return j

    return {
        "d1": last_before(asof),
        "mtd": last_before(asof.replace(day=1)),
        "ytd": last_before(asof.replace(month=1, day=1)),
    }


def _last_at_or_before(values: list[float | None], i: int | None) -> float | None:
    if i is None:
        return None
    while i >= 0:
        if values[i] is not None:
            return values[i]
        i -= 1
    return None


def asw_series(m: CreditMatrix, dataset, bond_type: str, tenor: str) -> list[float | None]:
    """자산스왑 스프레드(bp) = 민평 − IRS, 민평 날짜에 맞춰서.

    par-par 규약이라 진입일 스프레드가 이 숫자 그대로다 [OWNER, 2026-08-14].
    IRS 쪽에만 있는 날(연말 폐장일 등 15일)은 민평 격자에 없으므로 자연히 빠진다.
    """
    irs = dataset.series.get(tenor)
    if irs is None:
        raise CashBondError(f"IRS 에 {tenor} 계열이 없습니다.")
    pos = {d: i for i, d in enumerate(dataset.dates)}
    mp = m.series(bond_type, tenor)
    out: list[float | None] = []
    for i, d in enumerate(m.dates):
        j = pos.get(d)
        a = mp[i]
        b = irs[j] if j is not None else None
        out.append(None if a is None or b is None else round((a - b) * 100, 2))
    return out


def series_for(m: CreditMatrix, dataset, series_id: str) -> list[float | None]:
    kind, bond_type, tenor = parse_id(series_id)
    if kind == KIND_CASH:
        return m.series(bond_type, tenor)
    return asw_series(m, dataset, bond_type, tenor)


def parse_id(series_id: str) -> tuple[str, str, str]:
    parts = series_id.split(":")
    if len(parts) != 3 or parts[0] not in (KIND_CASH, KIND_ASW):
        raise CashBondError(f"알 수 없는 종목입니다: {series_id!r} (CB:KTB:3Y 형식)")
    kind, bond_type, tenor = parts
    if bond_type not in cm.BOND_TYPES:
        raise CashBondError(f"알 수 없는 종목군입니다: {bond_type}")
    if tenor not in cm.TENOR_YEARS:
        raise CashBondError(f"알 수 없는 테너입니다: {tenor}")
    return kind, bond_type, tenor


def instruments(
    m: CreditMatrix,
    dataset,
    irs_theta: dict[str, dict] | None = None,
) -> dict:
    """Cash Bond 표의 행 전부 — 현금채권과 자산스왑.

    §16 계산 경계: 수준·변화·백분위·52주 범위를 전부 여기서 내고 브라우저는
    그리기만 한다. IRS 표(`app/payloads.py`)와 같은 규약이다.

    행이 서는 조건은 **그 종목군이 그 만기를 실제로 갖는 것**이다. 통안채는
    3Y 까지, 30Y 는 국고채·공사채만 — `creditmatrix` 가 관측이 얇은 계열을
    이미 떨어냈으므로 여기서는 있는 것만 돈다.
    """
    from .derive import annual_stats

    bases = _basis_indices(m)
    last = len(m.dates) - 1
    rows: list[dict] = []
    for bond_type in cm.TYPE_ORDER:
        for tenor in m.tenors_for(bond_type):
            for kind in (KIND_CASH, KIND_ASW):
                if kind == KIND_ASW and tenor not in ASW_TENORS:
                    continue
                try:
                    vals = series_for(m, dataset, f"{kind}:{bond_type}:{tenor}")
                except CashBondError:
                    continue
                now = _last_at_or_before(vals, len(vals) - 1)
                if now is None:
                    continue
                stats = annual_stats(vals)
                changes: dict[str, float | None] = {}
                for k, bi in bases.items():
                    prev = _last_at_or_before(vals, bi)
                    # 현금채권은 %, 자산스왑은 이미 bp — 변화는 둘 다 bp 다.
                    mult = 100.0 if kind == KIND_CASH else 1.0
                    changes[k] = None if prev is None else round((now - prev) * mult, 2)
                rows.append({
                    "id": f"{kind}:{bond_type}:{tenor}",
                    "kind": kind,
                    "bondType": bond_type,
                    "tenor": tenor,
                    "label": instrument_label(kind, bond_type, tenor),
                    # 화면의 단위 어휘 그대로 ("%" | "bp") — IRS 행과 같은 값을
                    # 써야 같은 포매터(`lib/format.ts:fmtLevel`)를 탄다.
                    "unit": "%" if kind == KIND_CASH else "bp",
                    "now": round(now, 4),
                    "changes": changes,
                    "pct": stats["pct"],
                    "rangeHigh": stats["max"],
                    "rangeLow": stats["min"],
                    "rangeAvg": stats["avg"],
                    # 정렬 키도 서버가 정한다(§6/§16): 종목군 사다리 → 만기.
                    "sortKey": [cm.TYPE_ORDER.index(bond_type), cm.TENOR_YEARS[tenor]],
                    "theta": _row_theta(m, bond_type, tenor, kind, last, irs_theta),
                })
    return {
        "asof": m.asof.isoformat(),
        "from": m.dates[0].isoformat(),
        "types": [{"id": t, "label": cm.BOND_TYPES[t]} for t in cm.TYPE_ORDER],
        "rows": rows,
        # 세타가 무엇을 뜻하는지는 표 아래에 한 번 적는다 — 행마다 되풀이할
        # 문장이 아니다. `app/theta.py` 의 `meta` 와 같은 자리·같은 이유.
        #
        # 조달은 여기 없다 [OWNER, 2026-08-14] — 세타가 그것을 안 뺀다. Setting
        # 의 조달값은 백테스트의 조달 칸이 여전히 쓴다.
        "thetaBasis": {
            "horizonDays": 1,
            "notional": NOTIONAL,
            "side": "buy",
        },
    }


def _row_theta(
    m: CreditMatrix,
    bond_type: str,
    tenor: str,
    kind: str,
    i: int,
    irs_theta: dict[str, dict] | None,
) -> dict | None:
    """행 하나의 세타. 현금채권은 그대로, 자산스왑은 **두 다리의 합**이다.

    자산스왑의 정규화 분모는 **채권 다리의 DV01** 이다. par-par 라 순 DV01 이
    0 에 가깝고, 0 에 가까운 수로 나누면 숫자가 폭발한다 — IRS 쪽이 스프레드·
    플라이에서 기준 다리의 DV01 을 쓰는 것과 같은 이유이고 같은 처리다
    (`theta.theta_for_package` 의 근거 참조).
    """
    bond = theta_for_bond(m, bond_type, tenor, i)
    if bond is None:
        return None
    if kind == KIND_CASH:
        return bond
    swap = (irs_theta or {}).get(tenor)
    if swap is None:
        return None  # 그 만기에 IRS 세타가 없으면 패키지 세타도 없다
    cash = bond["cash"] + swap["cash"]
    dv01 = bond["dv01"]
    return {
        "perDv01": round(cash / (dv01 / 1_000_000)) if dv01 else 0,
        "cash": round(cash),
        "carry": round(bond["carry"] + swap["carry"]),
        "roll": round(bond["roll"] + swap["roll"]),
        "dv01": round(dv01),
        # 본전은 **스프레드**가 몇 bp 움직여야 하나 — 그 행의 레벨 칸과 같은 단위
        "beBp": round((cash / dv01) if dv01 else 0.0, 2),
    }


# ── 세타 ────────────────────────────────────────────────────────────────────
# 표에 상시로 뜨는 열이다 — IRS 쪽 `app/theta.py` 와 **같은 자리·같은 질문**.
# 그쪽 모듈 주석이 근거를 다 들어 뒀으므로 여기서는 다른 점만 적는다.
#
# 다른 점 하나: **캐리에서 조달을 빼지 않는다** [OWNER, 2026-08-14 — "채권에서는
# 조달 차감하지 않는 걸로 하기"]. IRS 세타와 정의를 맞추기 위한 결정이다.
#
# **이것은 시장 관행과 다르다**, 그래서 여기 적어 둔다. 외부 확인(2026-08-14):
# 채권 캐리의 표준 정의는 `carry = y − r_f` — 수익률에서 조달(레포)을 뺀 값이고,
# yieldcurve.pro 는 "You collect coupon, you pay financing, and the difference is
# yours" 로, AnalystPrep 은 "income a bond earns above its funding cost" 로 적는다.
# 조달을 빼지 않으면 이 열은 **총 쿠폰**이 되어 수익률 높은 종목이 늘 이긴다 —
# 캐피탈채가 국고채보다 늘 위에 서는 것이 그 뜻이다.
#
# 되돌리려면 아래 `funding` 한 줄을 다시 빼면 된다. 조달값 자체는 Setting 이
# 여전히 들고 있고 백테스트의 조달 칸이 쓴다 — 사라진 것이 아니라 세타에서만
# 빠졌다.
#
# 다른 점 둘: **부호가 매수 기준**이다. IRS 표의 행은 방향이 없어서 페이로
# 고정했지만, 현금채권은 살 수만 있으므로(매도 거절) 살 때의 숫자가 곧 그 행의
# 숫자다. 우상향 커브에서 양수로 뜨는 것이 정상이다.

#: `app/theta.py` 와 **같은** 호라이즌·노셔널·bp. 세 값이 갈리면 두 표의 세타를
#: 나란히 놓고 읽을 수 없다 — 그래서 재정의하지 않고 가져온다.
from .theta import BP, HORIZON_DAYS, HORIZON_Y, NOTIONAL  # noqa: E402


def dv01_at(y: float, coupon: float, n: int, elapsed: float) -> float:
    """액면 1 기준 DV01 (원/bp) — 수익률을 ±0.5bp 흔든 clean 가격의 중앙차분.

    해석해를 쓰지 않는 이유는 `price` 가 이 화면의 유일한 가격 정의이기
    때문이다. 미분을 따로 적으면 규약이 둘이 되고, 둘이 어긋나도 아무도
    모른다(이 리포가 이미 한 번 겪은 결함 종류).
    """
    half = BP / 2
    up = price(y + half, coupon, n, elapsed)
    dn = price(y - half, coupon, n, elapsed)
    # clean = dirty − 경과이자 + 상환액면. 상환분은 수익률에 안 흔들리므로
    # 차분에서 지워지지만, 같은 식으로 적어 두어야 정의가 하나로 남는다.
    clean = lambda t: t[0] - t[1] + t[3]  # noqa: E731
    return clean(dn) - clean(up)


def theta_for_bond(
    m: CreditMatrix,
    bond_type: str,
    tenor: str,
    i: int,
) -> dict | None:
    """한 현금채권의 세타 블록. 값을 낼 수 없으면 None (표가 em dash 를 그린다).

    호라이즌은 **하루**이고 커브는 **동결**이다 — 오늘 커브 하나로 닫힌 식이라
    백테스트를 돌리지 않아도 나온다. 그것이 이 열의 존재 이유다. 기간은 IRS 쪽과
    같은 상수를 쓴다(`theta.HORIZON_Y`) — 두 표의 세타를 나란히 놓고 읽으려면
    그 값이 하나여야 한다.
    """
    years = cm.TENOR_YEARS[tenor]
    # 호라이즌을 지나고도 한 분기는 남아야 롤다운이 뜻이 있다 — IRS 쪽
    # `theta.theta_table` 의 같은 문턱과 같은 이유(민평 커브의 가장자리는
    # 보간이 지배한다).
    if years - HORIZON_Y < 0.25 - 1e-9:
        return None
    try:
        y0 = cm.yield_at(m, bond_type, i, years)
        y_roll = cm.yield_at(m, bond_type, i, years - HORIZON_Y)
    except CreditMatrixError:
        return None

    n = periods_for(tenor)
    coupon = y0  # 진입일 par — 표면금리가 곧 그날 민평이다

    # 호라이즌의 마킹: 잔존이 짧아진 채권을 **오늘 커브의** 그 지점으로 값 매김
    d_h, a_h, cp_h, rd_h = price(y_roll, coupon, n, HORIZON_Y)
    clean_h = d_h - a_h + rd_h

    roll = (clean_h - 1.0) * NOTIONAL          # par 로 샀으므로 기준이 1.0
    # 조달은 빼지 않는다 — 모듈 주석의 [OWNER] 와 그 아래 외부 확인 참조.
    carry = (a_h + cp_h) * NOTIONAL            # 분기치 쿠폰(경과 + 받은 것)

    dv01 = dv01_at(y0, coupon, n, 0.0) * NOTIONAL
    dv01_h = dv01_at(y_roll, coupon, n, HORIZON_Y) * NOTIONAL

    # 분기에서 재고 하루로 나눈다 — IRS 쪽 `theta._block` 과 같은 자리·같은 이유
    # (하루 간격 두 지점으로 롤을 재면 커브 보간 잡음이 롤보다 커진다).
    carry /= HORIZON_DAYS
    roll /= HORIZON_DAYS
    cash = carry + roll
    return {
        "perDv01": round(cash / (dv01 / 1_000_000)) if dv01 else 0,
        "cash": round(cash),
        "carry": round(carry),
        "roll": round(roll),
        "dv01": round(dv01),
        # 본전: 이 종목의 **호가값**(민평 수익률)이 몇 bp 올라야 세타가
        # 상쇄되나. IRS 표의 같은 열과 같은 문장이다.
        "beBp": round((cash / dv01_h) if dv01_h else 0.0, 2),
    }


# ── 일별 대사 ───────────────────────────────────────────────────────────────
#
# IRS 쪽 `backtest.book_recon` 과 **같은 규약·같은 화면**(ui/ReconStack)이다
# [OWNER, 2026-08-14 — "현금채권/자산스왑 백테스트에서도 대사 가능하게"].
# 그쪽 주석이 근거를 다 들고 있으므로 여기서는 다른 점만 적는다.
#
# ## 어느 커브를 흔드나
#
#   현금채권   그 종목군의 **민평 격자**. 행이 호가하는 값이 민평 수익률이다.
#   자산스왑   같은 격자를 흔들되 읽기는 **스프레드**다 — IRS 는 안 움직이고
#              민평만 1bp 움직이는 것이 곧 스프레드 1bp 이므로.
#
# 자산스왑에서 이것이 성립하는 이유를 적어 둔다. par-par 라 두 다리의 DV01 이
# 거의 같으므로 패키지 손익 ≈ −D×Δ민평 + D×ΔIRS = −D×Δ스프레드 다.
#
# **자산스왑의 추정 열은 현금채권만큼 안 맞는다. 그것이 정상이다.** Δ민평 =
# Δ스프레드 + ΔIRS 로 풀면
#
#   패키지 = −D_b×Δ스프레드 + (D_s − D_b)×ΔIRS
#            └─ 추정 열이 세는 것 ─┘   └─ 잔차로 떨어지는 것 ─┘
#
# 이라, 잔차는 두 다리의 듀레이션 차 × **IRS 무브**다. 추정 열이 "IRS 는
# 안 움직였다면" 을 세기 때문이고, 실제 하루는 둘 다 움직인다. 실측
# (2026-08-14, 3Y 100억, 진입 2025-08-13, 잔차/평가 중앙값):
#
#   현금채권    0.04%   ← 추정이 움직임을 거의 다 설명한다
#   자산스왑   43.7%    ← 절반 이상이 IRS 무브다
#
# 이 숫자를 줄이려면 IRS 격자도 함께 흔들어 **두 축**(Δ스프레드·ΔIRS)으로
# 세는 표가 되어야 한다. 지금 표는 한 축이다 — 자산스왑 행이 호가하는 값이
# 스프레드 하나이기 때문이고, 그래서 이 잔차는 결함이 아니라 규약의 값이다.
# 43.7% 를 "고치려고" 자산스왑 KRD 에 스왑 다리를 더하지 말 것: 그러면 KRD 가
# 스프레드 민감도이기를 그만두고 dbp 열과 짝이 안 맞는다.
#
# ## KRD 는 T+1 평가 기준
#
# IRS 쪽과 같다. 오늘 아침에 들고 있던 리스크를 내일 마킹으로 재는 것이 인포맥스
# 대사와 맞는다는 실측(2026-08-11)이 그쪽에 있고, 두 표가 같은 자를 써야 한다.

#: 대사 행을 **서빙하는** 창 — IRS 쪽과 같은 수(약 1년).
#:
#: ⚠ 이 수는 **화면 페이로드의 크기**를 정하려고 놓은 것이다. 그런데 같은 수가
#: `truncated` 를 통해 **회계가 설 수 있는가**까지 정하고 있었다: 잘린 창은
#: 반쪽이라 `main._mr_recon_rows` 가 `None` 을 내고, 그러면 그 다리 전체가 엔진
#: 근사로 되돌아간다. 화면 편의가 회계를 죽이는 자리였다.
#:
#: 2026-09-09 에 **창을 둘로 갈랐다**(`book_recon(max_days=…)`) — 회계 경로는
#: `max_days=None`(전 구간)으로 부르고 서빙 경로는 이 상수를 그대로 쓴다.
#: 그래서 페이로드·응답시간은 한 자도 안 바뀌고, 회계만 전 구간을 받는다.
#: 근거(krw-crs 레인 실측 `PROPOSAL_recon_max_days_2026-09-09.md`):
#:   · 250봉 초과 거래는 전 격자 26,628건 중 **395건(1.5%)** 뿐이다.
#:   · 두 경로의 비용이 **6배** 다르다 — 최장 거래(1,356봉)에서 회계 경로
#:     371ms → 1,247ms 인데 화면 경로는 2,358ms → 7,282ms 다. **회계가 쓰는
#:     쪽이 싼 쪽**이라(`with_legs=False`) 전 구간을 줘도 최악 +0.9초다.
RECON_MAX_DAYS = 250


def _krd_bond(
    m: CreditMatrix,
    pos: BondPosition,
    leg: "_BondLeg",
    i: int,
    elapsed: float,
    labels: list[str],
) -> dict[str, float]:
    """민평 노드를 1bp 올렸을 때의 **가치 변화에 부호를 뒤집은 것**(원/bp).

    단일수익률 할인이라 노드 하나를 흔들면 잔존만기를 감싸는 **두 노드에만**
    가중치가 실린다(선형보간). 그래서 KRD 가 저절로 성긴 행이 되고, IRS 쪽
    범프 표와 같은 모양으로 읽힌다.
    """
    out = {lb: 0.0 for lb in labels}
    remaining = leg.years - elapsed
    if remaining <= 0:
        return out  # 만기 뒤에는 흔들릴 것이 없다
    pts = cm.curve_points(m, pos.bond_type, i)
    if not pts:
        return out
    scale = pos.notional * pos.direction
    base_y = cm.interp(pts, remaining)
    base = price(base_y, leg.coupon, leg.n, elapsed)[0]
    for lb in labels:
        yrs = cm.TENOR_YEARS[lb]
        bumped = [(y, r + (BP if abs(y - yrs) < 1e-9 else 0.0)) for y, r in pts]
        y_b = cm.interp(bumped, remaining)
        if y_b == base_y:
            continue  # 이 노드는 그 잔존만기를 감싸지 않는다
        out[lb] = -(price(y_b, leg.coupon, leg.n, elapsed)[0] - base) * scale
    return out


def book_recon(
    m: CreditMatrix,
    dataset,
    positions: list[BondPosition],
    spec: fd.FundingSpec,
    with_legs: bool = False,
    *,
    max_days: int | None = RECON_MAX_DAYS,
) -> dict:
    """일별 대사 블록. `backtest.book_recon` 과 같은 응답 모양이다.

    조달이 한 칸 더 있다 — 그날 밤의 조달비용이고, 세 성분과 같은 밤을 가리킨다
    (전부 포워드). 그래야 `평가 + 캐리 + 롤다운 + 조달 = 그날 손익` 이 닫힌다.

    ## `with_legs` — **물어보는 쪽만 받는다** [2026-09-04]

    (이름이 `legs` 가 아닌 이유: 이 함수 안에 이미 `legs` 가 있다 — 채권 다리
    목록이다. 처음에 `legs` 로 두었더니 그 리스트가 인자를 가려 «끔» 이 언제나
    켬으로 돌았고, 실측에서 비용이 안 줄어 잡혔다.)

    켜면 행마다 `legs: [국고, IRS]` 와 `legTenors` 가 붙는다(자산스왑 북에서만).
    기본이 꺼짐인 이유는 값이 아니라 **비용**이다: IRS 다리의 KRD 는 파 커브를
    노드마다 흔들어 다시 값매기는 것이라, 실측 2026-09-04 로 250일 창의 채권
    대사가 828ms → 4,599ms(5.55배)가 된다. 백테스트·시뮬의 채권 표는 그 다리를
    그리지 않으므로 그 값을 물 이유가 없다.

    ## `max_days` — **회계와 서빙이 다른 창을 쓴다** [2026-09-09]

    기본은 상수(`RECON_MAX_DAYS`)이고 `None` 이면 전 구간이다. 잘린 창은
    `truncated: True` 로 나가고, 그 값을 보는 쪽(`main._mr_recon_rows`)은 반쪽을
    총손익이라 부르지 않는다 — 그 규율은 그대로다. 바뀐 것은 **회계 경로가 애초에
    안 잘린 창을 받는다**는 것뿐이다. 근거·실측은 상수 머리에.

    **끄면 화면도 안 바뀐다**는 것이 두 번째 이유다. `ReconStack` 은 다리가
    실려 오면 다리 모드로 바뀌는데, 그 화면들이 넘기는 열 목록은 민평 것뿐이라
    IRS 전용 노드(1D·4Y·6Y·8Y)가 **소리 없이 사라진다.** 그 표들도 다리로
    보려면 열을 `reconTenors` 로 바꿔야 하고, 그건 오너 판정이다.
    """
    if not positions:
        raise CashBondError("포지션이 하나는 있어야 합니다.")
    spec = spec.validated()
    if any(p.kind == KIND_ASW for p in positions) and dataset is None:
        raise CashBondError("자산스왑 행에는 IRS 데이터셋이 필요합니다.")

    legs = [_bond_leg(m, p) for p in positions]
    first = min(l.entry_i for l in legs)
    last = max(l.exit_i for l in legs)

    # 열은 이 북이 실제로 만질 수 있는 만기까지만 — 마지막 노드는 가장 긴
    # 잔존을 덮는 첫 노드다(IRS 쪽 `bump` 집합과 같은 규칙).
    types = {p.bond_type for p in positions}
    labels = [lb for lb in cm.TENOR_LABELS if any(m.has(t, lb) for t in types)]
    longest = max(l.years for l in legs)
    keep: list[str] = []
    for lb in labels:
        keep.append(lb)
        if cm.TENOR_YEARS[lb] >= longest:
            break
    labels = keep

    # 자산스왑 북이면 Δ 는 스프레드(이미 bp), 현금채권이면 민평(% → ×100)
    asw = all(p.kind == KIND_ASW for p in positions)
    node_series: dict[str, list[float | None]] = {}
    for lb in labels:
        for t in types:
            if not m.has(t, lb):
                continue
            node_series[lb] = (
                asw_series(m, dataset, t, lb)
                if asw and lb in ASW_TENORS
                else m.series(t, lb)
            )
            break
    delta_scale = 1.0 if asw else 100.0

    # 창 — `None` 이면 **전 구간**이다(회계 경로). 상수의 머리 주석에 왜 둘로
    # 갈랐는지가 있다. 서빙 경로는 기본값을 그대로 받아 종전과 한 자도 안 다르다.
    start = first if max_days is None else max(first, last - max_days + 1)

    # ── 스왑 다리 ───────────────────────────────────────────────────────────
    #
    # 자산스왑 행은 **두 다리**다. 채권만 세면 표가 채권 백테스트를 자산스왑
    # 이라고 부르는 셈이 된다 (2026-08-14 실측: 3Y 자산스왑 대사 합 −2.52억,
    # 같은 창의 백테스트 손익 +0.37억 — 2.89억이 스왑 다리였다).
    #
    # 스왑을 **여기서** 값매긴다. IRS 쪽 `backtest.book_recon` 을 따로 불러
    # 날짜로 합치는 길도 있었는데, 두 달력이 양쪽으로 어긋나서 그 길은 손익을
    # 흘린다 (실측: IRS 에만 있는 날 9일 — 12/25·1/1·3/2·5/1·5/5·5/25·6/3·
    # 7/17·12/31, 민평에만 있는 날 3일). 한 달력 위에서 세면 그 문제가 없다:
    # 민평이 안 뜬 날의 스왑 손익은 다음 민평 행의 마크 차이에 그대로 들어
    # 있고, 그게 실제로 그 행이 대사해야 하는 값이다.
    swap_cache: dict[int, object] = {}
    imap = _irs_index_map(m, dataset) if any(p.kind == KIND_ASW for p in positions) else {}

    def _swap_statics(pos: BondPosition, leg: _BondLeg) -> dict | None:
        """진입일에 struck 된 스왑 다리. 채권 매수 = 같은 명목 페이 고정
        (`_swap_leg` 의 par-par 주석 참조)."""
        if pos.kind != KIND_ASW:
            return None
        from .backtest import _build_legs, _leg_swap, _maturity_of
        from .curves import TENOR_T as IRS_T

        if pos.tenor not in ASW_TENORS:
            raise CashBondError(
                f"{pos.tenor} 는 자산스왑을 세울 수 없습니다 — 채권과 IRS 양쪽에 "
                f"있는 만기만 가능합니다 ({chr(0xB7).join(ASW_TENORS)})."
            )
        if leg.entry_i not in imap:
            raise CashBondError("민평 진입일이 IRS 달력에 없습니다 — 데이터를 확인하세요.")
        entry_date = m.dates[leg.entry_i]
        slegs = _build_legs(dataset, pos.tenor, pos.notional, imap[leg.entry_i])
        for sl in slegs:
            sl.sign *= pos.direction
        # 이 다리가 **느낄 수 있는** IRS 노드 — 진입일 잔존을 덮는 첫 노드까지.
        # 백테스트 표의 `bump` 와 같은 규칙이다(열이 늙어도 안 흔들리게 진입일에
        # 한 번 고정한다).
        tau = (_maturity_of(entry_date, pos.tenor) - entry_date).days / 365.0
        bump: list[str] = []
        for lb in IRS_T:
            bump.append(lb)
            if IRS_T[lb] >= tau:
                break
        return {
            "legs": slegs,
            "swaps": [_leg_swap(sl, entry_date) for sl in slegs],
            "entry_date": entry_date,
            "bump": bump,
        }

    def _swap_dirty(sw: dict, on: dt.date, zc, fx) -> tuple[float, float]:
        """(clean, 경과이자) — 주어진 제로커브 위에서의 스왑 다리."""
        from .valuation_port import CurveBundle, value_booked_trade

        curve = CurveBundle(on, zc, [])
        clean = accrued = 0.0
        for swap in sw["swaps"]:
            res = value_booked_trade(swap, curve, fx)
            clean += res.clean_npv
            accrued += res.accrued_interest
        return clean, accrued

    def _swap_mark(sw: dict, i: int, curve_i: int) -> tuple[float, float, float]:
        """(clean, 경과이자, 결제현금) — 스왑 다리. 채권 `mark_bond` 와 같은
        규약이고 `curve_i` 의 뜻도 같다(동결 재평가)."""
        from .backtest import _cd_fixings, _curve_at, _settled_to

        on = m.dates[i]
        j_curve, j_fix = imap.get(curve_i), imap.get(i)
        if j_curve is None or j_fix is None:
            # 민평 달력은 IRS 달력의 부분집합이다 — `_irs_index_map` 의 실측.
            # 그게 깨졌다면 데이터가 변한 것이고, 그때 마크를 지어내면 대사표가
            # 조용히 틀린다. 세우는 편이 낫다(그 함수의 정책과 같다).
            raise CashBondError("민평 날짜가 IRS 달력에 없습니다 — 데이터를 확인하세요.")
        fx = _cd_fixings(dataset, j_fix)
        clean, accrued = _swap_dirty(sw, on, _curve_at(dataset, j_curve, swap_cache), fx)
        cash = _settled_to(sw["legs"], sw["entry_date"], on, fx)
        return clean, accrued, cash

    def _swap_krd(sw: dict, i: int, j: int, cache: dict) -> dict[str, float]:
        """스왑 다리의 **노드별 KRD**(원/bp) — 파 노드를 1bp 올렸을 때의 가치
        변화에 부호를 뒤집은 것.

        범프 커브는 `backtest.bumped_par_curve` 를 부른다 — KRD 의 정의가 두
        곳에 서면 스왑 표와 채권 표가 같은 리스크를 다르게 말한다.

        **오늘 커브를 흔들어 내일 값을 매긴다.** KRD 는 T+1 평가 기준이라는
        백테스트 표의 규약과 같은 자다(`_book_recon` 의 그 주석 — 인포맥스
        실측 대사로 정해졌다).
        """
        from .backtest import _cd_fixings, _curve_at, bumped_par_curve
        from .curves import par_rates_at_index

        j_curve, j_fix = imap.get(i), imap.get(j)
        if j_curve is None or j_fix is None:
            raise CashBondError("민평 날짜가 IRS 달력에 없습니다 — 데이터를 확인하세요.")
        on = m.dates[j]
        fx = _cd_fixings(dataset, j_fix)
        par = par_rates_at_index(dataset, j_curve)
        b_c, b_a = _swap_dirty(sw, on, _curve_at(dataset, j_curve, swap_cache), fx)
        base = b_c + b_a
        out: dict[str, float] = {}
        for lb in sw["bump"]:
            zc = bumped_par_curve(par, lb, cache)
            if zc is None:
                continue                       # 그날 노드가 없다 — KRD 0
            c, a = _swap_dirty(sw, on, zc, fx)
            out[lb] = -((c + a) - base)
        return out

    info = [
        {"prev": None, "prev_fwd": None, "prev_s": None, "prev_fwd_s": None,
         "leg": l, "pos": p, "swap": _swap_statics(p, l)}
        for p, l in zip(positions, legs)
    ]

    # IRS 다리가 서는 노드 — 민평 라벨과 **다른 집합**이다(민평엔 2.5Y·20Y·30Y,
    # IRS 엔 1D·4Y·6Y·8Y·9Y). 그래서 한 표에 두 다리를 세우면 열이 어긋나고,
    # 어긋나는 칸은 빈칸으로 둔다 [OWNER 2026-09-04].
    #: 다리 블록을 실을 것인가 — 자산스왑 북이고 부른 쪽이 물었을 때만.
    want_legs = asw and with_legs

    swap_labels: list[str] = []
    if want_legs:
        from .curves import TENOR_T as IRS_T

        seen = {lb for d in info if d["swap"] for lb in d["swap"]["bump"]}
        swap_labels = [lb for lb in IRS_T if lb in seen]

    # 다리마다의 Δ 는 **자기 커브**다 — 국고는 민평, IRS 는 스왑 종가. 종전 표는
    # 국고 다리의 KRD 에 «민평 − IRS» 스프레드 Δ 를 곱하고 있었다(한 다리의
    # 감도에 두 다리의 Δ). 그 섞인 자를 다리별로 가른다 [OWNER 2026-09-04].
    bond_node: dict[str, list[float | None]] = {}
    for lb in labels:
        for t in types:
            if m.has(t, lb):
                bond_node[lb] = m.series(t, lb)
                break
    swap_node: dict[str, list[float | None] | None] = (
        {lb: dataset.series.get(lb) for lb in swap_labels} if want_legs else {}
    )

    def _leg_delta(
        node: list[float | None] | None, cur_i: int | None, prv_i: int | None
    ) -> float | None:
        """그날의 Δbp — 두 종가의 차(% → ×100). 한쪽이라도 없으면 `None` 이고
        0 이 아니다(「그날 안 움직였다」는 다른 말이다).

        **색인을 두 개 받는 이유**: 이 표의 행은 민평 달력의 하룻밤인데 IRS
        계열은 **자기 달력** 위에 있다. 그래서 IRS 다리의 Δ 는 `imap[i]` 와
        `imap[i-1]` 로 읽어야 그 밤과 같은 밤이 된다. 민평 색인을 그대로
        넣으면 엉뚱한 이틀의 차가 나온다(그 실수를 한 번 했다 — 잔차가
        16배로 뛰어 잡혔다).
        """
        if not node or cur_i is None or prv_i is None or prv_i < 0:
            return None
        cur, prv = node[cur_i], node[prv_i]
        return None if cur is None or prv is None else (cur - prv) * 100.0

    def mark_bond(d: dict, i: int, curve_i: int | None = None) -> tuple[float, float, float]:
        """(clean, 경과이자, 결제현금) — **국고 다리**의 마킹. 셋의 합이 마크다.

        `curve_i` 는 **어느 날의 커브로** 값을 매길지다. 기본은 그날 자신이고,
        포워드 세타를 잴 때는 **오늘 커브로 내일 값을 매긴다**(동결 재평가) —
        커브가 안 움직였다면 얼마였겠나가 곧 캐리+롤다운이기 때문이다. 이걸
        빼먹으면 그날의 커브 무브까지 롤다운에 들어가고, 평가가 통째로 0 이
        된다(2026-08-14 에 실제로 그랬다: 평가 열 전체가 0).
        """
        leg, pos = d["leg"], d["pos"]
        elapsed = (m.dates[i] - m.dates[leg.entry_i]).days / 365.0
        remaining = max(0.0, leg.years - elapsed)
        src = i if curve_i is None else curve_i
        y = cm.yield_at(m, pos.bond_type, src, remaining) if remaining > 0 else leg.coupon
        dirty, accrued, coupons, redeemed = price(y, leg.coupon, leg.n, elapsed)
        scale = pos.notional * pos.direction
        return (dirty - accrued + redeemed) * scale, accrued * scale, coupons * scale

    def mark_swap(d: dict, i: int, curve_i: int | None = None) -> tuple[float, float, float]:
        """(clean, 경과이자, 결제현금) — **IRS 다리**. 다리가 없으면 전부 0."""
        if d["swap"] is None:
            return 0.0, 0.0, 0.0
        return _swap_mark(d["swap"], i, i if curve_i is None else curve_i)

    rows: list[dict] = []
    prev_krd = {lb: 0.0 for lb in labels}
    prev_krd_s = {lb: 0.0 for lb in swap_labels}
    nxt = m.dates[last]
    for i in range(max(start - 1, first), last + 1):
        on = m.dates[i]
        nxt = m.dates[min(i + 1, len(m.dates) - 1)]
        krd = {lb: 0.0 for lb in labels}
        krd_s = {lb: 0.0 for lb in swap_labels}
        bumped: dict[str, object] = {}        # 한 행 안에서 공유 (부트스트랩이 비싸다)
        b_val = b_carry = b_roll = b_fund = 0.0
        s_val = s_carry = s_roll = 0.0

        for d in info:
            leg, pos = d["leg"], d["pos"]
            if i < leg.entry_i or i > leg.exit_i:
                continue
            has_swap = d["swap"] is not None
            bc, ba, bh = mark_bond(d, i)
            b_now = bc + ba + bh
            sc = sa = sh = 0.0
            if has_swap:
                sc, sa, sh = mark_swap(d, i)
            s_now = sc + sa + sh

            if i > leg.entry_i:
                if d["prev_fwd"] is not None:
                    pc, pr, _pf = d["prev_fwd"]
                    b_val += (b_now - d["prev"]) - (pc + pr)
                    if has_swap:
                        qc, qr = d["prev_fwd_s"]
                        s_val += (s_now - d["prev_s"]) - (qc + qr)
                else:
                    # 잘린 창의 첫 행: 전일 커브로 동결 재평가해 시드한다.
                    # **다리마다 따로 언다** — 종전엔 두 다리를 합친 마크에서
                    # 국고만 동결한 값을 빼서, 그 한 행에 스왑의 clean 전액이
                    # 평가로 들어갔다(자산스왑에서만 터지는 자리였다).
                    el = (on - m.dates[leg.entry_i]).days / 365.0
                    rem = max(0.0, leg.years - el)
                    if rem > 0:
                        y_f = cm.yield_at(m, pos.bond_type, i - 1, rem)
                        df, af, _c, rd = price(y_f, leg.coupon, leg.n, el)
                        b_val += bc - (df - af + rd) * pos.notional * pos.direction
                    if has_swap:
                        f_c, _f_a, _f_h = mark_swap(d, i, curve_i=i - 1)
                        s_val += sc - f_c

            # 포워드 세타는 **다음 마킹이 있을 때만** 손익이다. 마지막 데이터
            # 날의 밤은 실현될 자리가 없으므로 칸에 넣지 않는다 — 넣으면 일별
            # 합이 백테스트 총액을 딱 그 한 밤만큼 넘는다. IRS 표가 그렇게
            # 하고 있고(실측 2026-08-14: 열린 북 합−총액 = −314,139원 =
            # 마지막 행 캐리+롤 −314,142원, 청산 북 −699,630원 = −699,630원),
            # 대사표가 총액과 안 맞으면 대사표가 아니다.
            alive_fwd = i < leg.exit_i
            # 리스크는 다르다. 청산하지 않은 북은 내일 아침에도 그대로 들고
            # 있다 — 데이터가 끊겼다는 사실이 포지션을 없애지는 않는다. 그래서
            # 종가 KRD 는 재서 이월 앵커에 싣는다. 만기가 와서 끝난 북은
            # 진짜로 비므로 `matured` 는 뺀다.
            open_end = (
                i == leg.exit_i and leg.exit_i == len(m.dates) - 1 and not leg.matured
            )
            if alive_fwd:
                # **오늘 커브로** 내일을 매긴다 — 동결 재평가 (mark_bond 의 주석)
                fb_c, fb_a, fb_h = mark_bond(d, i + 1, curve_i=i)
                carry_b = (fb_a - ba) + (fb_h - bh)
                roll_b = fb_c - bc
                # 조달은 **국고 다리만** 진다 — 현물을 조달해 들고 있는 비용이고
                # IRS 다리엔 조달할 원금이 없다(그 다리의 캐리는 CD − 고정이다).
                fund_b = (
                    fd.cost_between(spec, on, nxt, pos.notional)
                    if pos.direction > 0
                    else 0.0
                )
                b_carry += carry_b
                b_roll += roll_b
                b_fund += fund_b
                d["prev_fwd"] = (carry_b, roll_b, fund_b)
                if has_swap:
                    fs_c, fs_a, fs_h = mark_swap(d, i + 1, curve_i=i)
                    carry_s = (fs_a - sa) + (fs_h - sh)
                    roll_s = fs_c - sc
                    s_carry += carry_s
                    s_roll += roll_s
                    d["prev_fwd_s"] = (carry_s, roll_s)
            else:
                d["prev_fwd"] = (0.0, 0.0, 0.0)
                d["prev_fwd_s"] = (0.0, 0.0)
            if alive_fwd or open_end:
                # 마지막 날에는 `nxt` 가 오늘이라 이것이 그대로 종가 KRD 다
                # (자리도 같이 물려야 한다 — 안 그러면 열린 북에서 색인 초과).
                j = min(i + 1, len(m.dates) - 1)
                el_next = (nxt - m.dates[leg.entry_i]).days / 365.0
                for lb, v in _krd_bond(m, pos, leg, j, el_next, labels).items():
                    krd[lb] += v
                if has_swap and want_legs:
                    # 이 범프가 이 함수에서 제일 비싼 자리다 — 안 물었으면 안 돈다.
                    for lb, v in _swap_krd(d["swap"], i, j, bumped).items():
                        if lb in krd_s:
                            krd_s[lb] += v
            d["prev"] = b_now
            d["prev_s"] = s_now

        if i >= start:
            day_val = b_val + s_val
            day_carry = b_carry + s_carry
            day_roll = b_roll + s_roll
            day_fund = b_fund
            dbp: dict[str, float | None] = {}
            est: dict[str, float] = {}
            for lb in labels:
                node = node_series.get(lb)
                cur = node[i] if node else None
                prv = node[i - 1] if node and i > 0 else None
                delta = None if cur is None or prv is None else (cur - prv) * delta_scale
                dbp[lb] = None if delta is None else round(delta, 2)
                est[lb] = 0.0 if delta is None else -prev_krd[lb] * delta
            total_est = round(sum(est.values()))
            row = {
                "t": on.isoformat(),
                "krd": {lb: round(prev_krd[lb]) for lb in labels},
                "dbp": dbp,
                "est": {lb: round(est[lb]) for lb in labels},
                "estTotal": total_est,
                "actual": round(day_val + day_carry + day_roll - day_fund),
                "valuation": round(day_val),
                "rolldown": round(day_roll),
                "carry": round(day_carry),
                # 화면이 빼는 값이라 부호를 여기서 준다 (백테스트 조달 칸과 같은 규약)
                "funding": round(-day_fund),
                "residual": round(day_val) - total_est,
            }
            if want_legs:
                # ── 다리별 블록 [OWNER 2026-09-04 — 국고매수와 IRS Pay 를
                #    별개로] ─────────────────────────────────────────────────
                # 다리마다 **자기 커브의 Δ** 를 곱한다. 그래서 이 추정은 종전
                # (국고 KRD × Δ스프레드)보다 잔차가 작다 — 감도와 Δ 가 같은
                # 커브 위에 서기 때문이다.
                b_dbp: dict[str, float | None] = {}
                b_est: dict[str, float] = {}
                for lb in labels:
                    dl = _leg_delta(bond_node.get(lb), i, i - 1)
                    b_dbp[lb] = None if dl is None else round(dl, 2)
                    b_est[lb] = 0.0 if dl is None else -prev_krd[lb] * dl
                s_dbp: dict[str, float | None] = {}
                s_est: dict[str, float] = {}
                j_now, j_prv = imap.get(i), imap.get(i - 1)
                for lb in swap_labels:
                    dl = _leg_delta(swap_node.get(lb), j_now, j_prv)
                    s_dbp[lb] = None if dl is None else round(dl, 2)
                    s_est[lb] = 0.0 if dl is None else -prev_krd_s[lb] * dl
                b_total = round(sum(b_est.values()))
                s_total = round(sum(s_est.values()))
                row["legs"] = [
                    {
                        "name": "국고",
                        "krd": {lb: round(prev_krd[lb]) for lb in labels},
                        "dbp": b_dbp,
                        "est": {lb: round(b_est[lb]) for lb in labels},
                        "estTotal": b_total,
                        "actual": round(b_val + b_carry + b_roll - b_fund),
                        "valuation": round(b_val),
                        "carry": round(b_carry),
                        "rolldown": round(b_roll),
                        "funding": round(-b_fund),
                        "residual": round(b_val) - b_total,
                    },
                    {
                        "name": "IRS",
                        "krd": {lb: round(prev_krd_s[lb]) for lb in swap_labels},
                        "dbp": s_dbp,
                        "est": {lb: round(s_est[lb]) for lb in swap_labels},
                        "estTotal": s_total,
                        "actual": round(s_val + s_carry + s_roll),
                        "valuation": round(s_val),
                        "carry": round(s_carry),
                        "rolldown": round(s_roll),
                        # 조달은 국고 다리만 진다 — 여기 0 을 적으면 「그날 조달이
                        # 0 이었다」는 다른 말이 된다(공란 정책).
                        "funding": None,
                        "residual": round(s_val) - s_total,
                    },
                ]
            rows.append(row)
        prev_krd = krd
        prev_krd_s = krd_s

    # 이월 앵커 — 종가 KRD 만 싣고 손익 필드는 전부 None (IRS 쪽 공란 정책)
    if rows:
        anchor = {
            "t": nxt.isoformat(),
            "krd": {lb: round(prev_krd[lb]) for lb in labels},
            "dbp": {},
            "est": {},
            "estTotal": None,
            "actual": None,
            "valuation": None,
            "rolldown": None,
            "carry": None,
            "funding": None,
            "residual": None,
            "carryover": True,
        }
        if want_legs:
            anchor["legs"] = [
                {"name": "국고", "krd": {lb: round(prev_krd[lb]) for lb in labels},
                 "dbp": {}, "est": {}, "estTotal": None, "actual": None,
                 "valuation": None, "carry": None, "rolldown": None,
                 "funding": None, "residual": None},
                {"name": "IRS", "krd": {lb: round(prev_krd_s[lb]) for lb in swap_labels},
                 "dbp": {}, "est": {}, "estTotal": None, "actual": None,
                 "valuation": None, "carry": None, "rolldown": None,
                 "funding": None, "residual": None},
            ]
        rows.append(anchor)

    out = {"tenors": labels, "rows": rows, "truncated": start > first}
    if want_legs:
        # 표의 열은 두 다리의 **합집합**이다 — 화면이 이것으로 칸을 세운다.
        out["legTenors"] = [
            {"name": "국고", "tenors": labels},
            {"name": "IRS", "tenors": swap_labels},
        ]
    return out
