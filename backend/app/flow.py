# -*- coding: utf-8 -*-
"""투자자별 수급 — **Strategy 네 번째 세입자**.

[OWNER 2026-10-16] 「선물+현물 둘 다 · 새 세입자」. 계획 정본은
`docs/PLAN_flow_tenant_2026-10-16.md`.

## 이 면이 **순위면이 아니라 대조면**인 까닭

투자자별 순매수는 **영합**이다 — 한쪽의 순매수가 다른 쪽의 순매도와 같다. 그래서
대분류(외국인·기관계·개인·기타)에 순위를 매기면 **매일 같은 두 줄**이 나온다.
실측(2026): 외국인과 기관계의 상관이 **3년 −0.9996 · 10년 −0.9992**이고, 둘의 합
(= 개인 + 기타)은 중위 176 / 114 계약이다. 그래서 대분류는 **대조**로 세우고,
순위는 기관계를 세분한 하위 분류가 진다 — 거기에만 진짜 경쟁이 있다.

## 순위 키 — **과거 분포 대비**, 그리고 하한 [OWNER 2026-10-19]

규모로 세우면 외국인·증권이 매일 1·2위라 화면이 날마다 같은 말을 한다. 자기
직전 252봉 분포 대비 당일 편차(σ)로 세운다 — 인접 세입자 Mean Reversion 이 밴드
대비 위치를 재는 것과 같은 결이다.

⚠ 그런데 **분모가 거의 0인 주체가 위로 올라온다**. 하한 없이 σ 로 세우면 3년
1위가 개인(−598계약), 10년 1위가 기타(+98계약)가 된다. 그래서 `RANK_FLOOR` 를
둔다. 실측 일평균 |순매수|(직전 252봉):

    3Y  외국인 8,399 · 기관계 8,324 · 증권 6,961 · 은행 3,805 · 투신 1,338 ·
        연기금 702 · 보험 570 │ 개인 225 · 기타 64 · 종금 27
    10Y 외국인 4,129 · 기관계 4,085 · 증권 3,461 · 은행 1,140 · 투신 589 ·
        보험 557 │ 연기금 314 · 개인 142 · 기타 40 · 종금 1

500 이 그 틈을 가른다. 면마다 순위 대상이 달라지는데 **자료가 정하는 것**이라
그대로 두고, 빠진 주체는 지우지 않고 `ranked: False` 로 같이 내보낸다.

## 함정 다섯 (계획 §1 — 전수로 다시 쟀다)

① **`INST`(기관계)는 동료가 아니라 상위 집합이다.**
   `INST = SECU + TRUST + BANK + INSUR + MERCH + PENS` 가 **5,288행 전부에서
   오차 0**. 두 층을 같이 더하면 기관을 두 번 센다.
② **`ETCQUANTITY` 칼럼이 없다.** `ETCPRICE / CLOSE` 로 역산하면 안 된다 —
   `CLOSE` 는 후방 조정된 연속 계열이라 수준이 없다(`futures.py` 머리, 3Y 중위
   89.5bp 틀림). **영합 폐쇄**로 구한다: `ETC = −(INST + FRGN + INDI + GOVT)`.
③ **`GOVT`(정부)는 죽은 칼럼이다** — 전 구간 0. `excluded` 에 적고 뺀다.
④ **현물에 중복 22,775조합**(`date,isin,market,buysell` 기준). `deal_time`
   최대값 행 한 장만 쓴다.
⑤ **현물이 `bis_otc_investor_daily` 와 안 맞는 것은 결함이 아니다**
   [대사 완료 2026-10-19]. 첫 판은 「은행만 어긋나고 외국인· 보험은 맞는다」로
   적혀 있었는데 그것이 **하루치 우연**이었다 — 10-16 로 다시 재니 외국인
   −40,001 · 보험 −340,000 · 개인 −37,551 · 기금공제 −39,300 으로 **열 주체 전부**
   어긋났다(장외· 순매수· `kind='국채'`· 백만원).

   두 표는 **설계가 다른 측정**이라 서로를 판정할 수 없다. 가른 자는 영합이다:

   - `ktb_investor` 는 **주체 합이 0** 이다 — 30영업일(09-01~10-16) 전부, 잔차
     −1~−3백만원(반올림). 양쪽 다리를 다 적는 **완결 회계**라는 뜻이고, 그래서
     딜러(`financial_investment`)가 한 주체로 선다(10-16 순매수 −333,904).
     `매수 − 매도 = 순매수` 도 50칸 전부 일치.
   - bis 는 **한쪽 면만** 적는다 — 매수 `전체` 2,580,670 = 부분들의 합이고
     `증권사간` 은 0 이다. 딜러가 아예 빠져 있으니 합이 0 이 될 수 없다.

   즉 bis 의 투자자 행은 「최종 투자자 한 다리」이고 ktb 는 「두 다리 전부」다.
   채권 모집단(`kind='국채'` 대 국고 종목별)까지 다르다 — 어긋남이 400억· 3,600억
   처럼 **둥근 수**인 것이 종목 몇 개가 한쪽에만 있다는 신호다.

   화면이 쓰는 수는 `ktb_investor` 한 원천이고 그것은 제 안에서 닫힌다. 대사는
   **끝났다** — bis 를 섞으면 안 되고, 그것이 이 모듈이 한 원천만 읽는 이유다.

## 두 원천의 `asof` 가 **다른 것이 정상**이다 [OWNER 2026-10-19]

현물이 선물보다 늦게 들어온다. 실측(2026-10-19 10:11): 선물은 금요일(10-16)치를
08시대에 받았고 현물은 아직 10-15 였다. **결측이 아니라 안 온 것**이다. 그래서
`watermark()` 가 두 표를 잇는 **복합**이어야 한다 — 한쪽만 세면 다른 쪽이 들어와도
캐시 열쇠가 안 바뀐다.

## 종가 기준이다 — 일중 틱 없음

`infomax_API.investor_intra` 는 오늘치까지 있지만 `underlying` 이 **빈 문자열**이라
계약코드를 못 푼다. 일중은 별도 레인이다.

## ★가격 × 미결제약정 2×2 [OWNER 2026-10-21 — 「해외에선 어떻게 해?」]

선물 데스크의 **1차 판독**이고, 같은 순매수를 네 가지로 가른다:

|  | 미결제 ↑ | 미결제 ↓ |
|---|---|---|
| 가격 ↑ | 신규 매수 | 숏 커버 |
| 가격 ↓ | 신규 매도 | 롱 청산 |

같은 「+5,000계약」이 **새로 산 것**인지 **숏을 되돌린 것**인지를 순매수 혼자서는
말하지 못한다. 미결제가 늘면 포지션이 **생긴 것**이고 줄면 **풀린 것**이다.
이 데스크의 선례도 같은 쪽을 가리킨다 — KTBF 외인수급 레인에서 살아남은 둘 중
하나가 OI 분해였다.

배관은 **0** 이다. `INTEREST`·`VOLUME`·`CLOSE` 가 이 모듈이 이미 읽는 표에 있고
(실측: 2,646봉 · NULL 0), 종전 쿼리가 수량 칼럼만 골라 왔을 뿐이다.

⚠**셋을 조심한다.**

1. **`CLOSE` 는 후방 조정된 연속 계열이라 수준이 없다**(`futures.py` 머리 · 함정 ②).
   2×2 는 **차분의 부호**만 쓰므로 유효하지만, 화면이 그 선에서 **값을 읽으면 안 된다**.
   그래서 `priceNote` 가 그 사실을 싣는다.
2. **미결제는 시장 전체 한 수**다 — 주체별 미결제가 아니다. 그래서 2×2 는 **시장의
   말**이고, 「누가」는 옆의 순매수 표가 진다. 둘을 한 주체의 포지션으로 읽으면 안 된다.
3. **가격이지 금리가 아니다.** 선물 가격 ↑ = 금리 ↓. 라벨을 금리로 바꾸지 않았다 —
   2×2 의 네 이름은 **가격 기준**으로 정의된 외부 관례이고, 여기서 뒤집으면 그
   관례를 읽어 온 사람이 거꾸로 읽는다. `basis` 가 부호 규약을 적는다.

## 현물 만기물 분리 · PD 인수 · 이동평균 [OWNER 2026-10-19 추가]

① **현물은 만기물로 갈린다.** `ktb_investor` 는 종목(isin)별이고 종목의 만기물은
   `infomax.국채_발행정보` 의 발행일·만기일로 풀린다(`ktb_issuance.tenor_bucket` —
   `bond_issues.tenor_class` 와 89/89 일치, 현물 164종목 전부 덮음). SQL 이 `CASE isin`
   으로 (날짜 × 만기물) 집계를 내고, `ALL` 은 그 합이다 — 그래서 `ALL` 은 10-19 이전
   화면과 **같은 수**다.
② **PD 인수는 자료에 없다 → 노브.** 입찰 당일 그 종목의 열 주체 합이 0 이라(실측
   10-12 3년 2.4조) 발행시장 인수분이 빠져 있다. `pd_share`(금융투자 몫, 은행은
   나머지)를 주면 `ktb_issuance.supply_table` 의 공급(경쟁+비경쟁−매입, 백만원)을 그
   비율로 금융투자·은행 일별 순매수에 **더한다**. 받은 쪽이 보이면 금융투자의 순매도가
   「받은 것을 푸는 것」으로 읽힌다.
   ★**가정인 것과 아닌 것을 가른다** [OWNER 2026-10-20 — 「금융투자가 60%면 남는
   40%는 은행이 하는 거 알고있지?」]. 두 주체가 **나눠 받는다**(합이 100)는 것은
   제도이고 `apply_pd` 가 그렇게만 더한다 — 몫 하나를 받아 나머지를 은행에 준다.
   가정인 것은 **60 이라는 수**다. 공표되지 않는 것은 *어느 PD 가 얼마를 받았나*이지
   두 주체가 나눈다는 사실이 아니다. `basis` 가 그 둘을 갈라 말한다.
③ **이동평균은 서버가 낸다**(§16). 일별 그림의 주체(`daily`)와 창(`ma` ∈ 5·20·60)을
   받아 `series.ma` 로 싣는다. 창 길이 미만 자리는 `None` 이다 — 0 으로 채우면 선이
   지어낸 값으로 시작한다.

## 산술은 DB 를 모른다

영합 폐쇄·누적·편차·순위는 전부 `_fetch` **밖**의 순수 함수다. SQL 없이 잴 수 있어야
시험이 자료에 안 붙는다(`paperlive.py` 의 그 규율).
"""
from __future__ import annotations

import datetime as dt
import re
import statistics as st
from dataclasses import dataclass, field
from typing import Any

from . import ktb_issuance, mysqldb

#: 선물 투자자별. 같은 표의 `CLOSE`·`INTEREST`·`VOLUME` 은 §미결제 분해가 읽는다.
FUT_TABLE = "sim_portfolio.mkt_futures_investor_close"
#: 현물 투자자별 — 데스크의 인포맥스 창고. 대소문자가 섞여 백틱으로 묶는다.
CASH_TABLE = "`infomax_API`.`ktb_investor`"

#: 선물 **대분류** — 서로 더하면 0. `ETC` 는 칼럼이 없어 영합으로 닫는다(함정 ②).
FUT_TOP: list[tuple[str, str]] = [
    ("FRGN", "외국인"), ("INST", "기관계"), ("INDI", "개인"),
]
#: 선물 **기관계 세분** — 이 여섯의 합이 `INST` 다(함정 ①).
FUT_SUB: list[tuple[str, str]] = [
    ("SECU", "증권"), ("TRUST", "투신"), ("BANK", "은행"),
    ("INSUR", "보험"), ("MERCH", "종금"), ("PENS", "연기금"),
]
#: 전 구간 0 인 죽은 칼럼(함정 ③). 영합 폐쇄에는 넣고 화면에선 뺀다.
FUT_DEAD = "GOVT"

FUT_TENORS = ("3Y", "10Y")

#: ★선물 **시장 칼럼 셋** [2026-10-21]. 같은 표에 있는데 이 모듈이 안 읽고 있었다.
#: 실측 2026-10-21: 만기마다 2,646봉 · 2016-01-04~2026-10-20 · NULL 0 · 0 없음.
FUT_MKT_COLS: list[tuple[str, str]] = [
    ("CLOSE", "close"), ("INTEREST", "oi"), ("VOLUME", "volume"),
]

#: 현물 주체 열 — 계층이 없다(선물과 달리 상위 집합이 없다).
CASH_COLS: list[tuple[str, str]] = [
    ("financial_investment", "금융투자"), ("foreigner", "외국인"),
    ("insurance", "보험"), ("asset_management", "자산운용"),
    ("bank", "은행"), ("individual", "개인"),
    ("fund_or_mutual_aid", "기금공제"), ("government_or_municipal", "국가지자체"),
    ("other_corporate", "기타법인"), ("other_financial", "기타금융"),
]

#: 편차를 재는 창(영업일). 계열 자기이력이라 `creditdts.WINDOW` 와 같은 눈금이다.
WINDOW = 252
#: 편차를 내려면 창 안에 이만큼은 있어야 한다.
MIN_OBS = 120
#: ★순위 하한(계약/일). 위 §순위 키의 실측이 근거다 — 이 아래는 분모가 거의 0이라
#: σ 가 폭발한다. **고정하고 화면에 적는다**(`creditdts.FLOOR_BP` 와 같은 자세).
RANK_FLOOR = 500.0
#: 현물 하한(백만원/일). 단위가 다르니 수도 다르다.
#:
#: ⚠**선물처럼 깨끗한 틈이 없다.** 직전 252봉 일평균 |순매수|(백만원) 실측:
#:
#:     개인 24,162 · 기타금융 34,924 · 국가지자체 49,450 │ 기타법인 65,841 ·
#:     보험 132,113 · 자산운용 173,878 · 기금공제 211,689 · 은행 417,606 ·
#:     외국인 498,461 · 금융투자 794,719
#:
#: 선물 쪽은 570 과 225 사이가 2.5배라 500 이 안전했는데, 여기서 가장 넓은 틈은
#: 34,924→49,450 의 **1.42배**뿐이다. 50,000 으로 두면 국가지자체(49,450)가
#: 하한에서 1% 아래라 **날마다 뒤집힌다** — 그래서 그 틈의 가운데로 내린다
#: (기하평균 41,560). 지금 여유는 아래쪽 15% · 위쪽 24%.
CASH_RANK_FLOOR = 40_000.0

#: 현물 면의 만기물 — `ALL` 이 기본이고 10-19 이전 화면과 같은 수다(§현물 만기물 ①).
CASH_TENORS = ("ALL",) + ktb_issuance.TENORS
CASH_TENOR_LABEL = {"ALL": "전체", **ktb_issuance.LABEL}
#: 만기물을 못 푼 종목이 모이는 바구니. 합계엔 들고 만기물 표에선 빠진다.
CASH_OTHER = "기타"
#: 이동평균 창(영업일). 0 은 끔.
#: ★**120 이 있어야 느린 주체를 본다** [OWNER 2026-10-20]. 보험은 30년물 한 자리에
#: 전 표본 순매수의 88%(134.4조 중 118.0조)를 담는데 그 움직임이 분기 눈금이라,
#: 60일까지로는 가속·감속이 잡음에 묻힌다(아래 §감마의 실측).
MA_WINDOWS = (0, 5, 20, 60, 120)
#: PD 인수를 받는 두 주체(§현물 만기물 ②).
PD_COLS = ("financial_investment", "bank")

_ISIN = re.compile(r"^[A-Z0-9]{12}$")


class FlowError(RuntimeError):
    """이 화면을 그릴 수 없다."""


@dataclass(frozen=True)
class FlowData:
    """두 원천의 **일별 순매수**. 산술 전의 날것이다."""
    #: 만기 → (날짜, 주체키 → 값). 주체키는 `FUT_TOP`+`FUT_SUB`+`GOVT`+`ETC`.
    fut: dict[str, tuple[list[str], dict[str, list[int]]]]
    #: 만기물(`CASH_TENORS`) → (날짜, 주체키 → 값). 단위 **백만원**. 날짜축은 공통이다.
    cash: dict[str, tuple[list[str], dict[str, list[int]]]]
    watermark: tuple[str, int]
    #: ★만기 → `close`·`oi`·`volume`. 축은 `fut` 와 **같은 날짜**다(§미결제 2×2).
    #: ⚠**기본값이 빈 사전**이다 — 시험 픽스처가 이 필드 없이 `FlowData` 를 짓고,
    #: 없으면 2×2 를 **안 싣는다**(지어내지 않는다).
    mkt: dict[str, dict[str, list[float]]] = field(default_factory=dict)


# ── 순수 산술 (DB 를 모른다) ────────────────────────────────────────────────

def close_zero_sum(top: dict[str, int]) -> int:
    """`ETC` — 영합 폐쇄로 구한다(함정 ②). 가격이 아예 필요 없다."""
    return -(top.get("INST", 0) + top.get("FRGN", 0)
             + top.get("INDI", 0) + top.get(FUT_DEAD, 0))


def inst_identity_error(row: dict[str, int]) -> int:
    """`INST − (여섯의 합)`. **0 이어야 한다**(함정 ①, 5,288행 실측)."""
    return row.get("INST", 0) - sum(row.get(k, 0) for k, _ in FUT_SUB)


def cumulative(vals: list[int]) -> list[int]:
    """누적 순매수. 길이는 그대로."""
    out: list[int] = []
    run = 0
    for v in vals:
        run += v
        out.append(run)
    return out


#: 2×2 의 네 이름 — **가격 기준**이다(§미결제 ⚠3). 서버가 말을 쥔다(§16).
OI_NEW_LONG = "신규 매수"
OI_SHORT_COVER = "숏 커버"
OI_NEW_SHORT = "신규 매도"
OI_LONG_LIQ = "롱 청산"


def oi_regime(d_close: float, d_oi: float) -> str | None:
    """가격 Δ × 미결제 Δ → 네 이름 중 하나. 어느 쪽이든 0 이면 `None`.

    0 을 한쪽에 붙이지 않는다 — 「안 움직였다」는 네 칸 어디도 아니고, 가격이
    제자리인 날을 「신규 매수」로 적으면 그 날 수가 거짓이 된다. 실측으로 가격 Δ=0
    인 날이 있다(연속 계열이라 조정일에 생긴다).
    """
    if d_close == 0 or d_oi == 0:
        return None
    if d_close > 0:
        return OI_NEW_LONG if d_oi > 0 else OI_SHORT_COVER
    return OI_NEW_SHORT if d_oi > 0 else OI_LONG_LIQ


def oi_tally(close: list[float], oi: list[float], span: int | None = None,
             ) -> tuple[list[str | None], dict[str, int]]:
    """봉마다의 이름과 **고른 구간의 집계**.

    첫 봉은 차분이 없어 `None` 이다 — 0 으로 채우면 없는 날을 세게 된다.
    집계는 마지막 `span` 봉만 센다(화면이 그림을 자르는 그 수).
    """
    names: list[str | None] = [None]
    for i in range(1, min(len(close), len(oi))):
        names.append(oi_regime(close[i] - close[i - 1], oi[i] - oi[i - 1]))
    cut = names[-span:] if span else names
    tally = {n: 0 for n in (OI_NEW_LONG, OI_SHORT_COVER, OI_NEW_SHORT, OI_LONG_LIQ)}
    for n in cut:
        if n is not None:
            tally[n] += 1
    return names, tally


def sigma_of(hist: list[int], today: int) -> tuple[float | None, float]:
    """(편차, 일평균 |순매수|) — 창은 **오늘을 뺀** 직전 `WINDOW` 봉.

    오늘을 넣으면 그날이 제 분모를 키워 편차가 줄어든다. 「평소 대비 오늘」이라는
    질문에 오늘이 들어가면 안 된다.
    """
    w = hist[-WINDOW:]
    if len(w) < MIN_OBS:
        return None, 0.0
    avg = st.mean(abs(v) for v in w)
    sd = st.pstdev(w)
    if sd <= 0:
        return None, avg
    return round(today / sd, 2), avg


def rank_rows(rows: list[dict[str, Any]], floor: float) -> list[dict[str, Any]]:
    """편차 큰 순. **하한 아래는 순위 밖**이고 지우지 않는다(위 §순위 키).

    순위를 못 받은 줄은 뒤에 서고 `rank` 가 `None` 이다 — 「없다」와 「0등」은
    다른 말이다.
    """
    for r in rows:
        r["ranked"] = bool(r["avgAbs"] >= floor and r["sigma"] is not None)
    rows.sort(key=lambda r: (not r["ranked"], -abs(r["sigma"] or 0.0), r["key"]))
    n = 0
    for r in rows:
        if r["ranked"]:
            n += 1
            r["rank"] = n
        else:
            r["rank"] = None
    return rows


def moving_average(vals: list[int] | list[float], n: int) -> list[float | None]:
    """단순 이동평균. **창 길이 미만 자리는 `None`** — 0 으로 채우면 선이 지어낸
    값으로 시작한다(§현물 만기물 ③)."""
    out: list[float | None] = []
    run = 0.0
    for i, v in enumerate(vals):
        run += v
        if i >= n:
            run -= vals[i - n]
        out.append(round(run / n, 1) if i >= n - 1 else None)
    return out


def apply_pd(cols: dict[str, list[int]], supply: list[float], share: float) -> dict[str, list[int]]:
    """발행시장 인수분을 금융투자·은행에 **더한다**(§현물 만기물 ②). 다른 주체는 그대로.

    `supply` 는 `ktb_issuance.align_supply` 가 현물 날짜축에 얹어 준 공급(백만원).
    매입(바이백)은 거기서 이미 음수라, 되산 날엔 두 주체의 순매수가 줄어든다.
    """
    out = {k: list(v) for k, v in cols.items()}
    fi, bk = PD_COLS
    for i, a in enumerate(supply):
        if not a:
            continue
        out[fi][i] += round(a * share)
        out[bk][i] += round(a * (1.0 - share))
    return out


def gamma(vals: list[int], n: int) -> list[float | None]:
    """감마 — **속도의 변화**. `MA_n(t) − MA_n(t−n)` 이다 [OWNER 2026-10-20].

    ## 왜 감마냐 — 부호가 거기서만 산다

    순매수의 **부호에는 정보가 거의 없다**. 국채 잔액이 늘고 이 회계는 영합이라
    (`ktb_investor` 는 열 주체 합이 0), 금융투자(PD)가 내놓는 것을 나머지가 **늘**
    받는다. 실측(60일 MA 의 양수 비중): 보험·30년물 **100%** · 국가지자체·전체
    100% · 외국인·30년물 100%. 「사나 파나」는 물어볼 필요가 없는 질문이다.

    감마는 다르다 — 양수 비중 **44~57%** 에 부호 구간이 24~160개다. 「빨라지나
    느려지나」는 진짜 질문이고, 그래서 이 면이 재는 축은 속도가 아니라 이쪽이다.

    ## 창이 짧으면 잡음이다 — 화면이 그 사실을 적는다

    감마 부호가 이어지는 길이(중위, 영업일) 실측:

        Γ5·Γ20   5~7일   (부호 구간 116~160개)  → **잡음**
        Γ60      9~24일  (43~87개)              → 쓸 만
        Γ120     8~46일  (24~45개)              → 제일 쓸 만

    Γ20 이 10년에 150번 뒤집히면 그건 신호가 아니다. `WINDOW_TRUST` 가 이 판정을
    들고 `verdict()` 가 화면에 그대로 적는다 — 수만 주고 「믿어도 되나」를 안
    적으면 화면이 잡음을 신호처럼 보여 주게 된다.

    ## 왜 `MA_n(t) − MA_n(t−n)` 인가

    **창 하나만큼 떨어진 두 평균의 차**라 「지난 n일이 그 앞 n일보다」가 한 문장으로
    읽히고, 단위가 안 바뀐다(둘 다 백만원/일). 짧은 창에서 긴 창을 빼는 꼴
    (`MA5 − MA20`)도 생각했는데 그건 **창 둘을 섞어** 어느 쪽의 변화인지 안 갈린다.

    창이 안 찬 자리와 `t−n` 이 축 밖인 자리는 `None` 이다 — 0 으로 채우면 「안
    변했다」가 되는데 그건 「모른다」와 다른 말이다(`moving_average` 와 같은 규율).
    """
    m = moving_average(vals, n)
    out: list[float | None] = [None] * len(m)
    for i in range(len(m)):
        if i - n < 0:
            continue
        a, b = m[i], m[i - n]
        if a is None or b is None:
            continue
        out[i] = a - b
    return out


#: 창마다 「그 감마를 믿어도 되나」 — 위 §창이 짧으면 잡음이다의 실측이 근거다.
#: 화면이 수와 **함께** 적는다.
WINDOW_TRUST: dict[int, str] = {
    5: "잡음", 20: "잡음", 60: "보통", 120: "믿을 만",
}


def verdict(cols: dict[str, list[int]], key: str) -> dict[str, Any]:
    """고른 주체 한 칸의 **판별** — 네 창의 속도와 감마, 그리고 한 문장 [OWNER 2026-10-20].

    판정은 **믿을 만한 창**(`WINDOW_TRUST` 가 「잡음」이 아닌 60·120)만 본다. 둘이
    같은 부호면 그쪽으로 말하고, 갈리면 **갈린다고 말한다** — 한쪽을 골라 적으면
    화면이 없는 확신을 지어낸다.

    속도는 거의 늘 양수라(위 §왜 감마냐) 판정문에 안 쓴다. 다만 수는 같이 싣는다 —
    「얼마나 사면서 빨라지나」를 읽으려면 둘 다 필요하다.
    """
    vals = cols[key]
    wins = [w for w in MA_WINDOWS if w]
    rows = []
    for w in wins:
        sp = moving_average(vals, w)[-1] if vals else None
        gm = gamma(vals, w)[-1] if vals else None
        rows.append({"window": w, "speed": sp, "gamma": gm,
                     "trust": WINDOW_TRUST.get(w, "보통")})
    trusted = [r for r in rows if r["trust"] != "잡음" and r["gamma"] is not None]
    if not trusted:
        say = "믿을 만한 창(60·120일)에서 감마를 낼 만큼 이력이 길지 않아요."
        tone = None
    else:
        signs = {1 if r["gamma"] > 0 else -1 if r["gamma"] < 0 else 0 for r in trusted}
        names = "·".join(f"{r['window']}일" for r in trusted)
        if signs == {1}:
            say, tone = f"{names} 모두에서 사는 속도가 빨라지고 있어요.", "up"
        elif signs == {-1}:
            say, tone = f"{names} 모두에서 사는 속도가 느려지고 있어요.", "down"
        else:
            say, tone = (f"{names}이 서로 다른 방향이에요 — 한쪽으로 말할 수 없어요.",
                         None)
    return {
        "key": key, "rows": rows, "say": say, "tone": tone,
        #: 왜 짧은 창을 판정에서 뺐는지, 그리고 **이것이 예측이 아니라는 것**을
        #: 화면이 적을 수 있게. 뒤 문장의 근거는 아래 §판정 2026-10-20.
        "note": ("판정은 60·120일만 봐요 — 5·20일 감마는 부호가 중위 5~7일마다 "
                 "뒤집혀서 신호가 아니에요. 그리고 이 줄은 설명이지 예측이 아니에요 — "
                 "수급으로 금리 방향을 맞추는 것은 재서 안 되는 것으로 "
                 "나왔어요(2026-10-20)."),
    }


# ── ★판정 [2026-10-20] — 이 면은 **설명이지 예측이 아니다** ────────────────
#
# 오너의 「재봅시다」로 수급이 금리 방향을 맞추는지 전수로 쟀다. **안 된다.**
# 네 번 쟀고 네 번 다 같은 답이다 — 자세한 것은 `docs/VERDICT_flow_direction_
# 2026-10-20.md`, 요지만:
#
#   ① 보험 감마 → 30년 금리   사전등록 네 관문 **전부 실패**(G1 부호·G2 |t|≥2·
#      G3 연도집중·G4 가속우위). Γ120 의 연도별 기여가 +119%/+144%/−95% 로
#      해마다 뒤집힌다.
#   ② 외국인 MA 교차 단일 120개   1등 Calmar 0.87 대 **우연 1등 95%p 0.93**
#   ③ AND/OR 조합 1,560개         1등 0.92 대 **우연 1.02**
#   ④ 보유기간까지 840개          1등 0.97 대 **우연 1.36**(가짜가 37% 이김)
#
# ★**손잡이를 더하면 진짜도 오르는데 우연이 더 빨리 오른다.** ④에서 보유기간을
# 넣자 1등이 0.87 → 0.97 로 올랐지만 우연 천장은 0.93 → 1.36 으로 뛰었다. 표본이
# **6.6년 · 금리 사이클 하나**(2020-01 ~ 2026-10, 수급 ∩ 금리 1,662봉)라 자유도를
# 늘릴수록 우연이 그 사이클을 타는 조합을 반드시 찾아낸다.
#
# 가짜 자료는 **원형 이동**이다 — 신호와 수익의 자기상관은 그대로 두고 맞물림만
# 깬다. 같은 크기의 탐색을 거기 돌려 **1등끼리** 맞댔다. 한 칸만 무작위와 견주면
# 「고르는 행위」의 우연이 안 지워진다(그 검정으로 한 번 틀린 판정을 냈다).
#
# 문헌도 같은 쪽이다 — Czech·Huang·Lou·Wang(2021 JFE, 길트 전수 체결자료)에서
# **보험·연기금(ICPF)은 일별·월별 어느 빈도에서도 예측력이 없고**, 까닭으로
# **부채 매칭**을 든다. 우리가 본 「보험 = 30년물 한 자리에 118조」가 그 행동이다.
#
# 되살릴 조건 하나: **2016~2019 수급 자료가 메워져 사이클이 둘 이상이 되면**
# 표본밖으로 다시 잰다. 그 전에는 열지 않는다.
#
# 남는 값어치는 **설명**이다(그래서 이 모듈을 안 지운다): 보험 30년물 쏠림,
# 20년물 2022년부터 매도, 공급 감속 × 수요 가속, 그리고 「순매수 부호에는 정보가
# 없다」(60일 MA 양수 비중 88~100%) 자체.


def span_slice(n: int, span: int | None) -> slice:
    """구간이 보는 **마지막 `span` 봉**. `None`·0·음수는 전구간.

    ★**봉 수로 받는다 — 날짜가 아니다.** 구간을 자르는 자리는 원래 화면이고
    (`src/flow/span.ts` 머리), 그 규약은 **누적** 때문이다: 서버가 자르면 선이
    0 에서 다시 오르지 않는다. 행렬은 누적이 아니라 **합**이라 그 사정이 없지만,
    대신 「표의 수와 그림의 수가 같아야 한다」는 더 센 요구가 있다. 화면이 쓰는
    봉 수(`SPAN_BARS`)를 그대로 받아 같은 창을 잘라서 **구조적으로** 맞춘다 —
    날짜로 받으면 휴일 하나에 둘이 갈린다.
    """
    if not span or span <= 0 or span >= n:
        return slice(0, n)
    return slice(n - span, n)


def cash_matrix(d: FlowData, span: int | None = None,
                pd_share: float | None = None) -> dict[str, Any]:
    """테너 × (발행 + 주체) 한 표 [OWNER 2026-10-20].

    행이 만기물이고 열이 `발행` + `CASH_COLS` 열이다. 칸은 **구간 합**이고,
    맨 아랫줄 `합계` 는 열마다의 합이다 — `ALL` 바구니와 같은 수여야 한다
    (만기물을 못 푼 종목이 없으면. 있으면 `CASH_OTHER` 가 차이를 든다).

    ★왜 한 표인가 [OWNER 2026-10-20 — 「테너별 발행량이랑 각 투자주체들이 어떻게
    이를 담아가는지」]: 공급과 수요가 **같은 행**에 서야 「30년물 40.6조를 찍었는데
    보험이 11.3조를 담았다」가 한 줄로 읽힌다. 종전에는 발행이 다른 면에 있어서
    둘을 눈으로 이어야 했다.

    `pd_share` 가 있으면 주체 칸은 PD 인수를 **반영한 뒤**의 수다(발행 열은 그대로다 —
    그 열이 바로 더해지는 원천이라 두 번 세면 안 된다).
    """
    dates, _ = d.cash["ALL"]
    cut = span_slice(len(dates), span)
    supply_all = ktb_issuance.supply_table(ktb_issuance.load().rows)

    rows: list[dict[str, Any]] = []
    total = {c: 0 for c, _ in CASH_COLS}
    total_supply = 0.0
    pending_total = 0
    #: 봉마다의 **잔차** — 표가 닫혔나를 날 단위로 재려고 모은다(`_matrix_check`).
    #: 합만 재면 반올림이 쌓여 「깨진 하루」가 그 속에 숨는다.
    resid = [0] * len(dates)
    for key in ktb_issuance.TENORS:
        got = d.cash.get(key)
        if got is None:
            continue
        _dts, cols = got
        sup, pending = ktb_issuance.align_supply(dates, supply_all[key])
        pending_total += pending
        if pd_share is not None:
            cols = apply_pd(cols, sup, pd_share)
        s = sum(sup[cut])
        total_supply += s
        #: 이 만기물이 봉마다 보태는 잔차. PD 가 켜졌으면 `cols` 에 공급이 이미
        #: 들어 있으므로 그만큼 빼야 기대(0)로 돌아온다.
        for i in range(len(dates)):
            resid[i] += sum(cols[c][i] for c, _ in CASH_COLS)
            if pd_share is not None:
                resid[i] -= round(sup[i])
        vals = {c: sum(cols[c][cut]) for c, _ in CASH_COLS}
        for c, v in vals.items():
            total[c] += v
        rows.append({
            "key": key, "label": ktb_issuance.LABEL[key],
            "supply": round(s), "cols": vals,
        })
    return {
        "span": span or len(dates),
        "from": dates[cut][0] if dates[cut] else None,
        "to": dates[-1] if dates else None,
        #: ★`pd` = **가정이 섞인 열** [OWNER 2026-10-20]. 노브가 켜지면 금융투자·
        #: 은행 칸은 「실제로 산 수」가 아니라 공급을 비율로 더한 수다(실측: 은행
        #: 3년물 +12.9 → +27.8조, 공급 37.3 × 0.4 = 14.9 를 얹은 것). 종전에는
        #: 조건 스트립의 회색 문장만 그 사실을 말해서, **표만 보면 못 가렸다**.
        #: 가정이 섞인 칸은 표 안에서 구별돼야 한다.
        "cols": [{"key": c, "label": lab,
                  "pd": bool(pd_share is not None and c in PD_COLS)}
                 for c, lab in CASH_COLS],
        "rows": rows,
        "total": {"label": "합계", "supply": round(total_supply), "cols": total},
        "pending": pending_total,
        #: ★**표가 닫혔나** — 화면이 눈으로 더하지 않아도 되게 서버가 센다.
        #:
        #: `ktb_investor` 는 열 주체 합이 **0** 인 완결 회계다(머리 §현물 ②의 증거).
        #: PD 노브가 켜지면 공급을 두 주체에 더하므로 그 합이 **공급과 같아진다**
        #: (실측 2026-10-20, 1Y: −6.1+85.4+…+0.5 = 198.9조 = 발행 열). 즉 이 한
        #: 줄이 「만기물 분해가 샜나 · PD 가 두 번 더해졌나」를 동시에 잡는다.
        "check": _matrix_check(resid, dates, cut, pd_share is not None),
    }


#: 봉 하나가 반올림으로 벌어질 수 있는 폭(백만원).
#:
#: ★**원천이 영합을 반올림까지만 지킨다** [실측 2026-10-20]. 1,795봉 중 **911봉**
#: 에서 열 주체 합이 0 이 아니고, 거의 전부 ±1~5백만원이다 — 벤더가 주체마다
#: 백만원으로 끊어 적어서 합이 정확히 0 으로 안 닫힌다. 인계문의 「주체 합이 0
#: 이다(30영업일 전부)」는 그 30일 표본에서 참이었고 **전 구간에서는 근사**다.
CHECK_TOL_PER_BAR = 10

#: 반올림으로는 설명이 안 되는 봉 — 이 위면 **자료가 깨진 날**이다.
#: 실측 넷: 2026-04-13 **35,000**(350억) · 2023-01-18 6,999 · 2026-04-17 5,999 ·
#: 2023-04-11 1,998. 나머지 봉은 전부 5 이하다.
CHECK_BREAK = 1_000


def _matrix_check(resid: list[int], dates: list[str], cut: slice,
                  pd_on: bool) -> dict[str, Any]:
    """주체 합이 기대와 맞나 — 기대는 PD 가 꺼졌으면 0, 켜졌으면 공급이다.

    ★**합만 보면 안 된다.** 반올림 잔차가 봉마다 깔려 있어 창이 길면 저절로
    쌓이고, 그 속에 **진짜 깨진 하루**가 숨는다(2026-04-13 의 350억이 1년 창의
    잔차 289.7억의 거의 전부다). 그래서 봉 단위로 재서 **깨진 날을 지목한다** —
    「어긋난다」만 적으면 화면이 쓸 수 없는 경고가 된다.
    """
    win = resid[cut]
    days = dates[cut]
    got = sum(win)
    breaks = sorted(
        ((abs(v), d, v) for v, d in zip(win, days) if abs(v) > CHECK_BREAK),
        reverse=True)
    ok = not breaks and abs(got) <= CHECK_TOL_PER_BAR * max(len(win), 1)
    if ok:
        say = ("주체 합이 발행과 같아요 — PD 인수를 더했으니 그래야 해요."
               if pd_on else "주체 합이 0 이에요 — 유통시장 회계라 그래야 해요.")
    elif breaks:
        _a, d0, v0 = breaks[0]
        more = f" 그런 날이 {len(breaks)}일이에요." if len(breaks) > 1 else ""
        say = (f"이 구간에 원천이 안 닫히는 날이 있어요 — {d0} 하루가 "
               f"{v0 / 100:,.0f}억이에요.{more}")
    else:
        say = "주체 합이 반올림보다 많이 벌어졌어요 — 만기물 분해를 다시 봐야 해요."
    return {
        "sum": got, "ok": ok, "pd": pd_on,
        "breaks": [{"date": d, "amount": v} for _a, d, v in breaks[:5]],
        "say": say,
    }


def sum_cash_buckets(buckets: dict[str, tuple[list[str], dict[str, list[int]]]],
                     dates: list[str]) -> dict[str, list[int]]:
    """만기물 바구니들의 합 = `ALL`. 10-19 이전 화면의 그 수다(§현물 만기물 ①)."""
    cols: dict[str, list[int]] = {c: [0] * len(dates) for c, _ in CASH_COLS}
    for _k, (_d, bc) in buckets.items():
        for c, vals in bc.items():
            tgt = cols[c]
            for i, v in enumerate(vals):
                tgt[i] += v
    return cols


# ── 적재 (futures.py 와 같은 규율: 워터마크 키 캐시 + 주입 시임) ─────────────

_cached: FlowData | None = None
_injected: FlowData | None = None


def set_data(data: FlowData | None) -> None:
    """테스트 주입 시임 — `futures.set_data` 와 같은 규율. None 이면 해제."""
    global _injected
    _injected = data


def watermark() -> tuple[str, int]:
    """★**복합**이다 — 두 표의 `(MAX, COUNT)` 를 잇는다.

    `futures.watermark()` 를 재사용하면 안 된다: 그것은 `WHERE CLOSE IS NOT NULL`
    로 걸러 **투자자 행의 모집단이 아니다**. 그리고 한쪽만 세면 다른 쪽이
    들어와도 캐시 열쇠가 안 바뀐다 — 두 원천이 **다른 시각에 도착**하므로
    (§두 원천의 asof) 그 실수가 조용히 하루를 숨긴다.
    """
    with mysqldb.engine().connect() as conn:
        f = conn.execute(mysqldb.text(
            f"SELECT MAX(deal_date), COUNT(*) FROM {FUT_TABLE}")).one()
        c = conn.execute(mysqldb.text(
            f"SELECT MAX(deal_date), COUNT(*) FROM {CASH_TABLE}")).one()
    return (f"{f[0]}|{c[0]}", int(f[1]) + int(c[1]))


def _bucket_case(tenor_of: dict[str, str]) -> str:
    """`CASE t.isin WHEN … END` — 종목을 만기물로 접는 SQL 조각(§현물 만기물 ①).

    값을 글자로 박는다 — 바인드 변수 340개보다 읽기 쉽고, isin 은 `^[A-Z0-9]{12}$` 로
    걸러서 넣는다(DB 가 준 값이지만 그래도 거른다). 만기물은 고정 집합이다.
    """
    whens = " ".join(
        f"WHEN '{isin}' THEN '{b}'"
        for isin, b in sorted(tenor_of.items())
        if _ISIN.match(isin) and b in ktb_issuance.TENORS
    )
    return f"CASE t.isin {whens} ELSE '{CASH_OTHER}' END"


def _fetch() -> FlowData:
    """세 표를 **한 연결**에서 읽는다 — `read_sql()` 은 호출마다 연결을 새로 연다."""
    qty = ", ".join(f"{k}QUANTITY" for k, _ in FUT_TOP + FUT_SUB) + f", {FUT_DEAD}QUANTITY"
    #: ★시장 칼럼 셋을 **같은 쿼리에** 붙인다(§미결제 2×2) — 연결을 더 열지 않는다.
    mkt = ", ".join(c for c, _ in FUT_MKT_COLS)
    cash_cols = ", ".join(f"SUM(t.{c}) AS {c}" for c, _ in CASH_COLS)
    with mysqldb.engine().connect() as conn:
        frows = conn.execute(mysqldb.text(
            f"SELECT deal_date, ktb_type, {qty}, {mkt} FROM {FUT_TABLE} "
            f"ORDER BY deal_date ASC"
        )).fetchall()
        tenor_of = ktb_issuance.fetch_tenor_map(conn)
        crows = conn.execute(mysqldb.text(f"""
            SELECT t.deal_date, {_bucket_case(tenor_of)} AS bucket, {cash_cols}
            FROM {CASH_TABLE} t
            JOIN (SELECT deal_date, isin, market, buysell, MAX(deal_time) mt
                  FROM {CASH_TABLE}
                  WHERE market = '전체' AND buysell = '순매수'
                  GROUP BY deal_date, isin, market, buysell) k
              ON t.deal_date = k.deal_date AND t.isin = k.isin
             AND t.market = k.market AND t.buysell = k.buysell
             AND t.deal_time = k.mt
            WHERE t.market = '전체' AND t.buysell = '순매수'
              AND t.isin_nm NOT LIKE '국고이자%' AND t.isin_nm NOT LIKE '국고원금%'
            GROUP BY t.deal_date, bucket ORDER BY t.deal_date ASC
        """)).fetchall()
    if not frows:
        raise FlowError(f"{FUT_TABLE} 에서 행을 읽지 못했어요.")

    keys = [k for k, _ in FUT_TOP + FUT_SUB] + [FUT_DEAD]
    #: 시장 칼럼은 수량 뒤에 붙어 있다 — 자리를 수로 적지 않고 길이로 센다.
    mkt_at = 2 + len(keys)
    fut: dict[str, tuple[list[str], dict[str, list[int]]]] = {}
    mkts: dict[str, dict[str, list[float]]] = {}
    for tenor in FUT_TENORS:
        dates: list[str] = []
        cols: dict[str, list[int]] = {k: [] for k in keys + ["ETC"]}
        mk: dict[str, list[float]] = {name: [] for _c, name in FUT_MKT_COLS}
        for r in frows:
            if str(r[1]) != tenor:
                continue
            dates.append(_iso(r[0]))
            row = {k: int(r[2 + i] or 0) for i, k in enumerate(keys)}
            for k in keys:
                cols[k].append(row[k])
            cols["ETC"].append(close_zero_sum(row))
            for j, (_c, name) in enumerate(FUT_MKT_COLS):
                mk[name].append(float(r[mkt_at + j] or 0.0))
        fut[tenor] = (dates, cols)
        mkts[tenor] = mk

    return FlowData(mkt=mkts, fut=fut, cash=assemble_cash(
        [(_iso(r[0]), str(r[1]), [int(r[2 + i] or 0) for i in range(len(CASH_COLS))])
         for r in crows]), watermark=watermark())


def assemble_cash(rows: list[tuple[str, str, list[int]]],
                  ) -> dict[str, tuple[list[str], dict[str, list[int]]]]:
    """(날짜, 바구니, 값들) → 만기물마다 **공통 날짜축** 위의 계열 + `ALL`.

    어느 날 거래가 없던 만기물은 그 날 0 이다 — 축을 공유해야 그림 둘이 한 커서를
    나눌 수 있다. `ALL` 은 바구니 전부(`기타` 포함)의 합이라 분리 전 화면과 같은 수다.
    """
    dates = sorted({d for d, _b, _v in rows})
    idx = {d: i for i, d in enumerate(dates)}
    buckets: dict[str, dict[str, list[int]]] = {}
    for d, b, vals in rows:
        bc = buckets.setdefault(b, {c: [0] * len(dates) for c, _ in CASH_COLS})
        i = idx[d]
        for (c, _lab), v in zip(CASH_COLS, vals):
            bc[c][i] += v
    out: dict[str, tuple[list[str], dict[str, list[int]]]] = {
        k: (dates, buckets.get(k, {c: [0] * len(dates) for c, _ in CASH_COLS}))
        for k in ktb_issuance.TENORS
    }
    out[CASH_OTHER] = (dates, buckets.get(CASH_OTHER, {c: [0] * len(dates) for c, _ in CASH_COLS}))
    out["ALL"] = (dates, sum_cash_buckets({k: (dates, bc) for k, bc in buckets.items()}, dates))
    return out


def _iso(d: Any) -> str:
    return (d.date() if isinstance(d, dt.datetime) else d).isoformat()


def load() -> FlowData:
    """주입본이 있으면 그것, 없으면 SQL(워터마크 키 캐시).

    **디스크 캐시를 안 쓴다** — 두 원천 합 2.6초라(실측 2026-10-19: 선물 0.28s ·
    현물 2.30s) 모듈의 워터마크 캐시로 충분하다. 라이브 전용 선례는
    `/api/lab/creditdts`·`/api/rv/analysis`.
    """
    if _injected is not None:
        return _injected
    global _cached
    wm = watermark()
    if _cached is None or _cached.watermark != wm:
        _cached = _fetch()
    return _cached


def reset_cache() -> None:
    global _cached
    _cached = None


# ── 화면이 읽는 한 장 ───────────────────────────────────────────────────────

def board(side: str = "fut", tenor: str = "3Y", pd_share: float | None = None,
          ma: int = 0, daily: str | None = None,
          span: int | None = None) -> dict[str, Any]:
    """한 면 — 대분류 대조 + 세분 순위 + 누적·일별 계열(+이동평균).

    산술은 **여기 하나**다(§16) — 화면은 읽고 칠하기만 한다.

    `tenor` 는 선물이면 `3Y`·`10Y`, 현물이면 `ALL` 또는 만기물(`CASH_TENORS`).
    `pd_share` 는 현물에서만 뜻이 있다(금융투자 몫 0~1). `ma` 는 `MA_WINDOWS` 중 하나,
    `daily` 는 일별 그림에 세울 주체 열쇠다(없으면 그림 첫 계열). `span` 은 테너 × 주체
    행렬이 합할 **마지막 봉 수**다(없으면 전구간) — 그림을 자르는 화면과 같은 수를 받는다.
    """
    if side not in ("fut", "cash"):
        raise FlowError(f"모르는 면이에요: {side}")
    if side == "fut" and tenor not in FUT_TENORS:
        raise FlowError(f"모르는 만기예요: {tenor}")
    if side == "cash" and tenor not in CASH_TENORS:
        raise FlowError(f"모르는 만기물이에요: {tenor}")
    if ma not in MA_WINDOWS:
        raise FlowError(f"이동평균 창은 {'·'.join(str(w) for w in MA_WINDOWS[1:])}일 중 하나예요: {ma}")
    if pd_share is not None and not (0.0 <= pd_share <= 1.0):
        raise FlowError(f"PD 배분은 0~1 사이예요: {pd_share}")
    d = load()
    if side == "fut":
        return _fut_board(d, tenor, ma=ma, daily=daily, span=span)
    return _cash_board(d, tenor, pd_share=pd_share, ma=ma, daily=daily, span=span)


def _series_row(key: str, label: str, group: str, dates: list[str],
                vals: list[int]) -> dict[str, Any]:
    """한 주체의 오늘·구간·편차. **창은 오늘을 뺀** 직전 `WINDOW` 봉이다."""
    today = vals[-1] if vals else 0
    sigma, avg = sigma_of(vals[:-1], today)
    year = dates[-1][:4] if dates else ""
    return {
        "key": key, "label": label, "group": group,
        "d1": today,
        "d5": sum(vals[-5:]),
        "d20": sum(vals[-20:]),
        "ytd": sum(v for dte, v in zip(dates, vals) if dte[:4] == year),
        "sigma": sigma,
        "avgAbs": round(avg),
    }


def _fut_board(d: FlowData, tenor: str, ma: int = 0,
               daily: str | None = None, span: int | None = None) -> dict[str, Any]:
    dates, cols = d.fut[tenor]
    if not dates:
        raise FlowError(f"선물 {tenor} 자료가 없어요.")
    last = {k: v[-1] for k, v in cols.items()}

    #: 함정 ① — 항등식이 깨지면 **세지 않고 말한다**. 조용히 더하면 이중계상이다.
    err = inst_identity_error(last)
    excluded: list[dict[str, str]] = [{
        "id": FUT_DEAD, "label": "정부",
        "why": "전 구간 0 이라 뺐어요 — 죽은 칼럼이에요.",
    }]
    if err:
        excluded.append({
            "id": "INST", "label": "기관계",
            "why": f"기관계와 세분 여섯의 합이 {err}계약 어긋나요 — 세분을 믿지 마세요.",
        })

    top = [{"key": k, "label": lab, "value": last[k]} for k, lab in FUT_TOP]
    top.append({"key": "ETC", "label": "기타", "value": last["ETC"]})
    sub = rank_rows(
        [_series_row(k, lab, "기관계 세분", dates, cols[k]) for k, lab in FUT_SUB],
        RANK_FLOOR,
    )
    #: 그림에 올릴 계열 — 외국인 + 세분 상위 셋. **최대 넷**이다(화면 제약).
    picked = ["FRGN"] + [r["key"] for r in sub if r["ranked"]][:3]
    cash_dates = d.cash["ALL"][0] if "ALL" in d.cash else []
    return {
        "side": "fut", "tenor": tenor,
        "asof": {"fut": dates[-1], "cash": cash_dates[-1] if cash_dates else None},
        "unit": "계약",
        "days": len(dates),
        "top": top,
        "sub": sub,
        "rankFloor": RANK_FLOOR,
        "series": _chart(dates, cols, picked, FUT_TOP + FUT_SUB, daily=daily, ma=ma,
                         mkt=d.mkt.get(tenor)),
        #: ★가격 × 미결제 2×2 — **시장의 말**이다(§미결제 ⚠2). 자료가 없으면 `None`.
        "oi": _oi_block(d.mkt.get(tenor), dates, span),
        "pd": None,
        "tenors": None,
        "excluded": excluded,
        #: 화면이 「무엇을 보고 있나」를 지어내지 않게 서버가 말을 쥔다.
        #: ★하한의 **수**는 안 적는다 — 화면이 제 자(계약·억)로 조건 스트립에
        #: 이미 적는다. 서버가 원단위로 또 적으면 한 화면에 두 수가 선다.
        "basis": "투자자별 순매수예요 — 집계이고 새 판단이 아니에요. "
                 "대분류는 영합이라 순위가 아니라 대조로 세우고, "
                 "순위는 기관계 세분이 져요.",
    }


def _cash_board(d: FlowData, tenor: str = "ALL", pd_share: float | None = None,
                ma: int = 0, daily: str | None = None,
                span: int | None = None) -> dict[str, Any]:
    dates, cols = d.cash[tenor]
    if not dates:
        raise FlowError("현물 자료가 없어요.")

    #: 발행시장 인수 — 노브가 켜졌을 때만 공급을 두 주체에 더한다(§현물 만기물 ②).
    pd: dict[str, Any] | None = None
    if pd_share is not None:
        iss = ktb_issuance.load()
        supply, pending = ktb_issuance.align_supply(dates, ktb_issuance.supply_table(iss.rows)[tenor])
        cols = apply_pd(cols, supply, pd_share)
        year = dates[-1][:4]
        pd = {
            "share": pd_share,
            "supplyYtd": round(sum(v for dte, v in zip(dates, supply) if dte[:4] == year)),
            "pending": pending,
            "asof": iss.rows[-1]["date"] if iss.rows else None,
            #: ★**구조와 선택을 가른다** [OWNER 2026-10-20 — 「금융투자가 60%면
            #: 남는 40%는 은행이 하는 거 알고있지?」]. 둘이 나눠 받는다는 것(합이
            #: 100)은 제도이고 `apply_pd` 가 그렇게만 더한다. 가정인 것은 **60 이라는
            #: 수**다. 종전 문장은 「자료에 없는 배분이라 가정이에요」였는데 그게
            #: 합까지 의심하는 말로 읽혔다 — 공표되지 않는 것은 *어느 PD 가 얼마를
            #: 받았나*이지 두 주체가 나눈다는 사실이 아니다(머리 §현물 ②의 그 증거).
            "note": (f"발행시장 인수분을 금융투자 {round(pd_share * 100)}%·은행 "
                     f"{round((1 - pd_share) * 100)}% 로 더했어요 — 둘이 나눠 받는 것은 "
                     f"제도이고, {round(pd_share * 100)} 대 {round((1 - pd_share) * 100)} "
                     "이라는 몫이 가정이에요."
                     + (f" 입찰 {pending}건은 현물 자료가 그 날에 아직 안 닿아 반영 전이에요."
                        if pending else "")),
        }

    rows = rank_rows(
        [_series_row(c, lab, "국고채 현물", dates, cols[c]) for c, lab in CASH_COLS],
        CASH_RANK_FLOOR,
    )
    picked = [r["key"] for r in rows if r["ranked"]][:4]
    other = d.cash.get(CASH_OTHER)
    excluded = [{
        "id": "strip", "label": "원금·이자 분리채",
        "why": "국고 명목만 봐요 — 분리채는 뺐어요.",
    }]
    if tenor != "ALL" and other and any(any(v) for v in other[1].values()):
        excluded.append({
            "id": "unmapped", "label": "만기물 미상 종목",
            "why": "종목을 만기물로 못 풀어서 전체에만 들어 있어요.",
        })
    basis = ("국고채 현물 투자자별 순매수예요 — 장외와 장내를 합친 수이고, "
             "집계이지 새 판단이 아니에요. 평소에도 거의 안 움직이는 주체는 "
             "순위에서 빼요.")
    if tenor != "ALL":
        basis = f"{CASH_TENOR_LABEL[tenor]}만 봐요. " + basis
    if pd:
        basis += " " + pd["note"]
    return {
        "side": "cash", "tenor": tenor,
        "asof": {"fut": None, "cash": dates[-1]},
        "unit": "백만원",
        "days": len(dates),
        #: 현물엔 상위 집합이 없다 — 대분류 대조 칸이 **없는 것이 맞다**.
        "top": [],
        "sub": rows,
        "rankFloor": CASH_RANK_FLOOR,
        "series": _chart(dates, cols, picked, CASH_COLS, daily=daily, ma=ma),
        #: ★현물엔 미결제약정이 없다 — 열쇠는 **두고** 값을 `None` 으로 둔다.
        #: 열쇠가 면마다 없으면 화면이 「안 왔다」와 「없다」를 구별 못 해 추측한다.
        "oi": None,
        #: ★고른 칸의 **감마 한 줄** [OWNER 2026-10-20 — 「그림아래 감마 한줄로」].
        #: 그림이 세운 그 주체와 **같은 열쇠**를 쓴다(`_chart` 의 그 규칙) — 둘이
        #: 갈리면 그림과 그 아래 줄이 다른 계열을 말한다.
        "gamma": (verdict(cols, daily or picked[0])
                  if (daily or picked) else None),
        #: 테너 × (발행 + 주체) — 화면 왼쪽의 그 표 [OWNER 2026-10-20].
        "matrix": cash_matrix(d, span=span, pd_share=pd_share),
        "pd": pd,
        "tenors": [{"key": k, "label": CASH_TENOR_LABEL[k]} for k in CASH_TENORS],
        "excluded": excluded,
        "basis": basis,
    }


def _oi_block(mk: dict[str, list[float]] | None, dates: list[str],
              span: int | None) -> dict[str, Any] | None:
    """2×2 의 페이로드 — 오늘의 이름 + 고른 구간의 집계.

    `mk` 가 없으면(시험 픽스처) **안 싣는다** — 지어내지 않는다.

    ★`close` 의 **수준은 뜻이 없다**(후방 조정 연속 계열). 그래서 Δ 만 내보내고
    오늘의 수준은 아예 안 적는다 — 적으면 누군가 그 수를 호가로 읽는다.
    """
    if not mk or not mk.get("close") or not mk.get("oi"):
        return None
    close, oi = mk["close"], mk["oi"]
    names, tally = oi_tally(close, oi, span)
    n = min(len(close), len(oi))
    if n < 2:
        return None
    d_close = close[n - 1] - close[n - 2]
    d_oi = oi[n - 1] - oi[n - 2]
    counted = sum(tally.values())
    return {
        "asof": dates[-1] if dates else None,
        #: 오늘 — Δ 와 이름. `regime` 이 `None` 이면 한쪽이 안 움직인 날이다.
        "dClose": round(d_close, 3),
        "dOi": int(d_oi),
        "oi": int(oi[n - 1]),
        "volume": int(mk["volume"][n - 1]) if mk.get("volume") else None,
        "regime": oi_regime(d_close, d_oi),
        #: 구간 집계 — 「요즘 무슨 장이었나」. 분모를 같이 싣는다(이름 없는 날 제외).
        "span": span,
        "counted": counted,
        "tally": tally,
        #: ⚠평문이다 — 화면은 마크다운을 안 그린다(이 리포가 두 번 밟은 자리).
        "priceNote": "가격 선은 후방 조정된 연속 계열이라 수준에 뜻이 없어요 — "
                     "모양과 방향만 읽어요. 가격이 오르면 금리는 내려요.",
    }


def _chart(dates: list[str], cols: dict[str, list[int]], picked: list[str],
           names: list[tuple[str, str]], daily: str | None = None,
           ma: int = 0, mkt: dict[str, list[float]] | None = None) -> dict[str, Any]:
    """그림이 받는 것 — 누적 ≤4계열 + 일별 1계열(+이동평균).

    ★**최대 4계열**이다. 이 리포에는 N계열 범주형 팔레트가 없어서(이름 있는 색은
    방향 2 + 참조 4뿐) 열한 주체를 한 그림에 칠할 수 없다. 전수는 표가 진다.

    일별 그림의 주체는 `daily` 가 고르고(없으면 첫 계열), 그 위에 이동평균이 선다 —
    「각 주체마다 이동평균」[OWNER 2026-10-19].

    ## ★평균은 **네 창을 다 보낸다** [OWNER 2026-10-20 — 「동시에 여러 MA도 보고
    싶고 그런거야」]

    종전에는 `ma` 가 고른 **한 창**만 실었다. 그런데 이 면이 재는 것은 가속이고
    (§감마), 가속은 **창마다 다른 말을 한다** — 실측(보험·30년물): Γ5 −948 ·
    Γ20 −314 인데 Γ60 +220 · Γ120 +321 이다. 짧은 쪽은 식고 긴 쪽은 빨라진다는
    그 사실이 네 선을 **같이 봐야** 보인다. 하나씩 갈아 끼우면 둘을 기억으로
    맞대야 하고, 그건 화면이 할 일이다.

    `ma` 인자는 **남긴다** — 옛 호출부와 시험이 쓰고, 「조건 스트립에 적을 창」을
    고르는 데 아직 뜻이 있다. 다만 그림은 `mas` 를 쓴다.
    """
    lab = dict(names)
    key = daily or (picked[0] if picked else None)
    if key is not None and key not in cols:
        raise FlowError(f"모르는 주체예요: {key}")
    wins = [w for w in MA_WINDOWS if w]
    return {
        "dates": dates,
        "cum": [{"key": k, "label": lab.get(k, k), "values": cumulative(cols[k])}
                for k in picked if k in cols],
        "daily": {"key": key, "label": lab.get(key, key), "values": cols[key]}
        if key is not None else None,
        "ma": {"key": key, "label": f"{lab.get(key, key)} {ma}일 이동평균", "window": ma,
               "values": moving_average(cols[key], ma)}
        if key is not None and ma else None,
        #: 창 넷 전부 — 차례가 곧 색 배정이다(화면의 `INK`).
        "mas": [{"key": f"{key}-ma{w}", "window": w, "label": f"{w}일",
                 "values": moving_average(cols[key], w)}
                for w in wins] if key is not None else [],
        #: ★가격 — 흐름 혼자서는 안 읽힌다(§미결제). 선물 면에서만 선다.
        #: ⚠**수준에 뜻이 없다**(후방 조정 연속 계열) — 모양만 읽는 선이다.
        "price": {"key": "close", "label": "선물 가격", "values": mkt["close"]}
        if mkt and mkt.get("close") else None,
        #: ★미결제약정 — **시장 전체**다(주체별이 아니다).
        "oi": {"key": "oi", "label": "미결제약정", "values": mkt["oi"]}
        if mkt and mkt.get("oi") else None,
    }


def history(key: str, side: str = "fut", tenor: str = "3Y") -> dict[str, Any]:
    """한 주체 한 계열의 전구간 — 미리보기용."""
    d = load()
    if side == "cash":
        if tenor not in CASH_TENORS:
            tenor = "ALL"
        dates, cols = d.cash[tenor]
        names = dict(CASH_COLS)
    else:
        if tenor not in FUT_TENORS:
            raise FlowError(f"모르는 만기예요: {tenor}")
        dates, cols = d.fut[tenor]
        names = dict(FUT_TOP + FUT_SUB)
        names["ETC"] = "기타"
    if key not in cols:
        raise KeyError(key)
    return {
        "key": key, "label": names.get(key, key), "side": side,
        "tenor": None if side == "cash" else tenor,
        "dates": dates, "daily": cols[key], "cum": cumulative(cols[key]),
    }
