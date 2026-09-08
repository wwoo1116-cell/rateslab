# -*- coding: utf-8 -*-
"""절대수익형 성과지표 — **샤프를 대신한다** [OWNER 2026-09-04 — "샤프가 아니라
절대수익형펀드(헤지펀드)에서 사용하는 성과지표 가져와서 사용해주기"].

## 왜 샤프가 아닌가

샤프는 **상승 변동성도 벌**한다. 평균회귀 전략의 수익 분포는 왼쪽이 두꺼운
쪽(손절)이고 오른쪽은 작고 잦은 이익이라, 분모에 σ 를 통째로 넣으면 「크게 이긴
날」이 「크게 잃은 날」과 같은 무게로 깎인다. 절대수익을 파는 데스크가 실제로
답해야 하는 물음은 **「얼마를 걸고 얼마나 아팠나」**이고, 그 물음의 분모는 σ 가
아니라 **낙폭**이거나 **하방편차**다.

## 여기 있는 지표와 그 분모

    Sortino   평균 / 하방편차 × √252     — 손실 쪽 변동만 벌한다(MAR = 0)
    Calmar    연환산 손익 / 최대낙폭     — 절대수익형의 표준. MAR 비율과 같은 산술
    GPR       Σ월손익 / Σ|음의 월손익|   — Schwager Gain-to-Pain, **월 버킷**
    Omega     Σ이익일 / Σ손실일         — θ=0, **일별**. GPR 과 분모가 다르다
    Profit F. Σ이긴 거래 / |Σ진 거래|    — **거래** 기준(위 둘은 시간 기준)
    Ulcer     RMS 낙폭(₩)                — 낙폭의 «깊이 × 길이»
    Martin    연환산 손익 / Ulcer        — Ulcer 를 분모로 쓴 Calmar
    회복일    최대낙폭의 골 → 전고점 회복까지 영업일

**GPR 을 월 버킷으로 재는 이유**는 Omega 와 갈라 두기 위해서다. 같은 일별
계열에서 재면 `GPR = Omega − 1` 이라 한 지표를 두 번 적는 셈이 된다(Σ손익 =
Σ이익 − Σ손실 이므로 항등). Schwager 의 원 정의도 월 수익률이다. 구간이 짧아
월 버킷이 둘도 안 되면 **None** 이다 — 지어내지 않는다(이 리포의 공란 정책).

## 단위 — 수익률이 아니라 **원**이다

이 데스크에는 AUM 이 없다. 명목은 「1bp 움직일 때의 손익(₩/bp)」이라 분모로 쓸
자본이 아니다. 그래서 비율 지표의 분자·분모를 **둘 다 원**으로 두고 나눈다:
Calmar 는 원/원, Ulcer 는 원, Martin 은 원/원이다. Sortino 만 원/원이면서
√252 를 곱해 «연» 단위를 얻는다. 수익률 기반 문헌값과 크기를 직접 비교하면
안 되고, 같은 화면 안의 구성끼리 비교하는 값이다 — 화면이 그 사실을 적는다.

## 구간 [OWNER 2026-09-04 — "지난 1년, 지난 1분기, 지난 1개월을 전역 설정값으로
## 두고 이를 조정하면 성과도 바뀌게"]

엔진은 **늘 전체 표본 위에서** 돈다 — 룩백의 워밍업이 구간 앞에 있어야 z 가
서고, 구간을 잘라 다시 돌리면 1개월 창에서 120일 룩백이 아예 못 선다. 바뀌는
것은 **채점**이다: 구간 안의 봉만 더하고, 구간 안에서 청산된 거래만 센다.
누적 손익은 구간 시작을 0 으로 다시 긋는다(화면의 누적 곡선이 이미 그 규약).
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any

#: 구간 프리셋 — 프런트 `src/mr/api.ts::MR_SPANS` 가 이 목록을 거울로 삼는다.
#: `months=None` 이 전체다.
SPANS: list[tuple[str, int | None]] = [
    ("all", None),
    ("1y", 12),
    ("1q", 3),
    ("1m", 1),
]

#: 연환산 계수 — 이 리포의 다른 자리(`mrbacktest.summarize`)와 같은 값이다.
YEAR_BARS = 252


def _months_before(iso: str, months: int) -> str:
    """ISO 날짜에서 n개월 전 — **달력으로** 센다(봉 수가 아니다).

    프런트의 `monthsBefore` 와 같은 산술이다(말일 넘침은 다음 달로 굴린다).
    두 자리가 다른 날을 고르면 화면의 차트와 카드가 서로 다른 구간을 말한다.
    """
    y, m, d = (int(x) for x in iso.split("-"))
    y2, m2 = y, m - months
    while m2 <= 0:
        m2 += 12
        y2 -= 1
    # 말일 넘침(5-31 − 3개월 = 2-31)은 다음 달로 굴린다 — Date.UTC 와 같은 처리.
    try:
        return dt.date(y2, m2, d).isoformat()
    except ValueError:
        over = d - _days_in(y2, m2)
        nm, ny = (m2 + 1, y2) if m2 < 12 else (1, y2 + 1)
        return dt.date(ny, nm, over).isoformat()


def _days_in(y: int, m: int) -> int:
    nm, ny = (m + 1, y) if m < 12 else (1, y + 1)
    return (dt.date(ny, nm, 1) - dt.date(y, m, 1)).days


def span_cut(dates: list[str], months: int | None) -> str | None:
    """구간의 **첫 날**(ISO). 전체(`months=None`)면 None.

    색인이 아니라 «날짜» 를 내는 자리가 따로 있는 이유는 **장부** 때문이다
    [2026-09-07]. 통합 장부는 만기 아홉을 더하는데 만기마다 달력이 조금씩
    다르다(마지막 봉이 3만기는 2026-08-24, 나머지는 09-04 인 실측). 각자
    `span_start` 를 부르면 **저마다 자기 마지막 봉에서 1년을 물려** 아홉이 서로
    다른 창을 보게 되고, 그러면 만기별 표의 합이 통합과 안 맞는다.

    그래서 자르는 날은 **장부 달력에서 한 번** 정하고(`span_cut`), 다리마다는
    그 날로 색인을 찾는다(`index_at`).
    """
    if months is None or not dates:
        return None
    return _months_before(dates[-1], months)


def index_at(dates: list[str], cut: str | None) -> int:
    """그 날 **이후 첫 봉**의 색인. `cut` 이 None 이면 0.

    봉 수로 세면 휴장이 많은 구간이 조용히 길어지므로 날짜로 찾는다.
    """
    if cut is None or not dates:
        return 0
    for i, t in enumerate(dates):
        if t >= cut:
            return i
    # 구간 안에 봉이 하나도 없다 — 마지막 봉 하나만 남긴다(빈 구간을 만들지
    # 않는다. 0 개로 두면 아래 산술이 전부 None 이 되어 화면이 통째로 빈다).
    return max(0, len(dates) - 1)


def span_start(dates: list[str], months: int | None) -> int:
    """구간의 첫 봉 색인 — 자기 달력에서 자른다(계열 하나짜리 화면용).

    마지막 봉에서 달력으로 n개월을 물린 날 **이후 첫 봉**이다. 여러 계열을
    한 창에 세우는 자리에서는 이걸 쓰면 안 된다 — `span_cut` 머리를 보라.
    """
    return index_at(dates, span_cut(dates, months))


def _downside_dev(xs: list[float]) -> float:
    """하방편차 — **0 을 목표수익(MAR)** 으로 둔 RMS 손실이다.

    분모를 「손실 난 날의 수」가 아니라 **전체 일수**로 둔다(Sortino 의 표준
    정의). 손실이 드물수록 분모가 커져 값이 좋아지는 것이 이 지표의 뜻이다 —
    손실 난 날만으로 나누면 「가끔 크게 잃는다」와 「자주 조금 잃는다」가 뒤집힌다.
    """
    if not xs:
        return 0.0
    return math.sqrt(sum(min(x, 0.0) ** 2 for x in xs) / len(xs))


def _drawdowns(daily: list[float]) -> tuple[float, list[float], int | None, bool]:
    """(최대낙폭, 낙폭 경로, 회복 영업일수, 회복했는가).

    누적은 **구간 시작 0** 에서 시작한다. 회복일수는 최대낙폭의 **골**에서
    직전 고점을 되찾을 때까지의 영업일이다 — 「고점에서 골까지」가 아니라
    「골에서 회복까지」인 이유는, 데스크가 실제로 견디는 시간이 그쪽이기
    때문이다(고점은 지나고 나서야 고점인 줄 안다).

    구간 끝까지 못 되찾으면 `(일수=구간 끝까지, 회복=False)` 다 — None 으로
    두면 「낙폭이 없었다」와 구분이 안 된다.
    """
    cum = 0.0
    peak = 0.0
    dd_path: list[float] = []
    max_dd = 0.0
    trough_i = None
    peak_at_trough = 0.0
    for i, x in enumerate(daily):
        cum += x
        peak = max(peak, cum)
        dd = peak - cum
        dd_path.append(dd)
        if dd > max_dd:
            max_dd = dd
            trough_i = i
            peak_at_trough = peak
    if trough_i is None or max_dd <= 0:
        return 0.0, dd_path, None, True
    cum = sum(daily[: trough_i + 1])
    for j in range(trough_i + 1, len(daily)):
        cum += daily[j]
        if cum >= peak_at_trough:
            return max_dd, dd_path, j - trough_i, True
    return max_dd, dd_path, len(daily) - 1 - trough_i, False


def _monthly(dates: list[str], daily: list[float]) -> list[float]:
    """월 버킷 손익 — Schwager GPR 의 분자·분모가 서는 자리."""
    out: dict[str, float] = {}
    for t, x in zip(dates, daily):
        out[t[:7]] = out.get(t[:7], 0.0) + x
    return list(out.values())


def score(dates: list[str], points: list[dict], trades: list[dict],
          start: int, cost_bp: float) -> dict[str, Any]:
    """구간 하나의 성과 카드 한 벌.

    `points` 는 엔진(`mrbacktest.simulate`)의 봉이고 `trades` 는 그 거래다 —
    화면 페이로드가 아니라 **엔진 산출** 을 받는다. 그래야 전략 라우트와
    최적화 격자가 같은 자를 쓴다(두 번째 정의 없음).

    거래는 **구간 안에서 청산된 것**만 센다. 화면의 누적 곡선이 이미 그 규약이고
    (구간 순손익 = 구간 끝 누적 − 구간 직전 누적), 진입 기준으로 세면 구간
    끝에 걸친 거래의 손익이 곡선에는 있는데 승률에는 없게 된다.
    """
    win = points[start:]
    wdates = dates[start:]
    daily = [p["dailyPnl"] for p in win]
    n = len(daily)
    total = sum(daily)
    max_dd, dd_path, rec_days, recovered = _drawdowns(daily)

    ann = total * YEAR_BARS / n if n else 0.0

    mean = total / n if n else 0.0
    dd_dev = _downside_dev(daily)
    sortino = mean / dd_dev * math.sqrt(YEAR_BARS) if dd_dev > 0 else None

    calmar = ann / max_dd if max_dd > 0 else None

    gains = sum(x for x in daily if x > 0)
    losses = -sum(x for x in daily if x < 0)
    omega = gains / losses if losses > 0 else None

    mon = _monthly(wdates, daily)
    # 월 버킷이 둘도 안 되면 GPR 은 「한 달의 부호」일 뿐이다 — 안 낸다.
    mon_loss = -sum(x for x in mon if x < 0)
    gpr = (sum(mon) / mon_loss) if (len(mon) >= 2 and mon_loss > 0) else None

    ulcer = math.sqrt(sum(d * d for d in dd_path) / n) if n else 0.0
    martin = ann / ulcer if ulcer > 0 else None

    since = wdates[0] if wdates else None
    wt = [t for t in trades if since is not None and t["exitDate"] >= since]
    wins = [t for t in wt if t["pnl"] > 0]
    lost = [t for t in wt if t["pnl"] < 0]
    win_rate = (len(wins) / len(wt)) if wt else None
    won = sum(t["pnl"] for t in wins)
    lostv = -sum(t["pnl"] for t in lost)
    profit_factor = (won / lostv) if lostv > 0 else None

    # 손익분기 비용 — **구간 안에서 문 돈** 위의 닫힌형이다.
    #   PnL(c) = PnL(c₀) − 명목·(c − c₀)·건수,  문 돈 = 명목·c₀·건수
    #   ⇒ c* = c₀·(1 + PnL/문 돈)
    # 건수를 따로 세지 않아도 «문 돈» 하나면 배수가 나온다(`mrbacktest.
    # breakeven_cost_bp` 와 같은 산술을 비율로 다시 쓴 것).
    paid = -sum(p["barCost"] for p in win)
    mult = (1.0 + total / paid) if paid > 0 else None

    return {
        "from": since,
        "to": wdates[-1] if wdates else None,
        "days": n,
        "totalPnl": round(total, 2),
        "maxDrawdown": round(max_dd, 2),
        "sortino": _r(sortino, 3),
        "calmar": _r(calmar, 3),
        "gpr": _r(gpr, 3),
        # GPR 이 왜 없는지를 화면이 가려야 한다 — **월 버킷이 모자란 것**과
        # **손실 월이 하나도 없는 것**은 다른 사실이다(둘 다 None 이 된다).
        "gprMonths": len(mon),
        "omega": _r(omega, 3),
        "profitFactor": _r(profit_factor, 3),
        "ulcer": round(ulcer, 2),
        "martin": _r(martin, 3),
        # 회복일수와 «회복했는가» 는 **다른 사실**이다. 「74일」만 적으면 아직
        # 물속인 구간이 회복한 구간처럼 읽힌다.
        "recoveryDays": rec_days,
        "recovered": recovered,
        "winRate": _r(win_rate, 4),
        "numTrades": len(wt),
        # 이 구간 누적 손익의 **성분** [OWNER 2026-09-09]. 구간 카드 안에 있어야
        # 화면의 분해가 옆 칸들과 같은 구간을 말한다 — 전체 기간의 분해를 구간
        # 카드 옆에 세우면 두 칸이 딴 구간의 수다(이 모듈 §구간의 그 규율).
        "split": split(win),
        "breakevenCostMult": _r(mult, 3),
        "breakevenCostBp": _r(cost_bp * mult if mult is not None else None, 3),
    }


def _r(v: float | None, nd: int) -> float | None:
    return None if v is None else round(v, nd)


def dv_net(dv: float, cost: float, direction: int, notional: float) -> float | None:
    """**체결비용까지 문 Δ**(bp) [OWNER 2026-09-09 — "체결비용이 델타에는
    반영되게 해야 직관적으로 델타와 손익을 비교 가능"].

    거래 표의 Δ 는 종전에 **수준의 변화**였다 — 「2.00bp 움직였다」. 그런데 옆
    칸의 손익은 비용을 문 뒤의 돈이라, 두 칸을 나란히 보면 Δ 가 언제나 손익보다
    좋아 보였다(편도 0.5bp 짜리 왕복이면 1bp 가 Δ 에서만 빠져 있다).

    그래서 비용을 **bp 로 되돌려** Δ 에 싣는다. 감도(₩/bp)가 `방향 × 명목` 이고
    평가가 `감도 × Δ` 이므로,

        감도 × (Δ + 비용/감도) = 평가 + 비용

    이다 — 비용은 음수이므로 부호가 저절로 «나쁜 쪽» 으로 간다(방향이 −1 이면
    순Δ 가 커지고, 그쪽이 손실 방향이다). 두 칸이 **같은 것을 잰 두 단위**가
    되므로 Δ 와 손익을 눈으로 비교할 수 있다.

    ## 원 Δ 를 지우지 않는다

    Δ 는 **대사의 열**이다 — 「청산 레벨 − 진입 레벨 = Δ」가 줄에서 닫히고,
    그 항등이 이 표의 자기검사다(거래 표 머리 주석). 비용을 섞으면 그 검산이
    깨지므로 열을 **둘** 둔다: Δ 는 시장이 움직인 것, 순Δ 는 우리가 가진 것.

    ## 실가격 회계에서는 **근사**다

    실가격 판(`_mr_real_accounting`)의 평가는 `감도 × Δ` 가 아니라 자산스왑
    대사의 값이라, 위 항등이 원 단위까지는 안 닫힌다. 이 수가 답하는 물음
    (「비용이 Δ 로 몇 bp 인가」)은 그대로 서지만, 「순Δ × 감도 = 순손익」을
    그 판에서 원까지 맞추려 들면 안 된다 — 화면이 그 사실을 각주로 적는다.
    """
    if notional == 0 or direction == 0:
        return None
    return round(dv + cost / (direction * notional), 4)


#: 누적 분해의 성분 — (페이로드 이름, 봉의 엔진 키).
#: 순서가 화면 순서다: 값이 움직여 번 것 → 가만히 있어서 번 것 셋 → 비용.
SPLIT_PARTS: tuple[tuple[str, str], ...] = (
    ("mtm", "mtm"),
    ("carry", "barCarry"),
    ("rolldown", "barRolldown"),
    ("funding", "barFunding"),
    ("cost", "barCost"),
)


def split(points: list[dict]) -> dict[str, Any]:
    """누적 손익을 **성분별로** 더한다 [OWNER 2026-09-09 — "누적 채권 + 스왑
    손익을 롤다운 캐리로 분해해서 보여주기"].

    ## 정의는 v1 대사 엔진의 것이다 [OWNER 2026-09-09 — 「v1 대사 엔진 정의 이식」]

    성분은 여기서 새로 정의하지 않는다 — `main._mr_real_accounting` 이 봉마다
    세워 둔 그 다섯이고, 그 함수는 `cashbond.book_recon`(백테스트·시뮬 대사가
    쓰는 바로 그 함수)을 부르므로 **v1 `app/backtest.py` 의 3분해와 같은 말**이다:

        캐리   = 가만히 있어 확정되는 현금흐름(미정산 순액크루얼 + 정산 CF)
        롤다운 = 커브가 그대로인데 잔존만기가 짧아져서 생기는 클린 가격 변화
                 (전일 커브 위에서 오늘의 짧아진 물건을 다시 가격 — Tuckman
                 unchanged-term-structure)
        평가   = 클린 변화의 **잔여** = 커브가 움직여서 생긴 것
        조달   = 현물 다리의 조달 비용(선물에는 없는 항 — `mrcarry` 머리)
        비용   = 전략의 노브(체결비용·롤 갈아타기) — 상품의 성질이 아니다

    이 함수가 하는 일은 **더하기뿐**이다. 성분을 여기서 다시 유도하면 화면과
    대사표가 다른 수를 말할 자리가 생긴다(`mrbook` 머리의 그 규율).

    ## 엔진 근사 판에서는 둘이 **None 이다 — 0 이 아니다**

    실가격 회계가 못 선 실행(민평 이력 밖·선물 계열의 일부)에는 롤다운·조달이
    라는 항이 **아예 없다**. 0 으로 채우면 「그날 롤다운이 0 이었다」는 다른
    말이 되고, 화면은 그 0 을 사실로 읽는다(`api.ts` 의 그 주석과 같은 규약).

    `total` 은 성분의 합이 아니라 **봉의 그날 손익을 더한 것**이다 — 둘이
    갈리면 분해가 거짓이라는 뜻이라, 시험이 그 항등을 잰다
    (`tests/test_mr_split.py`).
    """
    out: dict[str, Any] = {}
    for name, key in SPLIT_PARTS:
        vals = [p[key] for p in points if key in p]
        # **일부 봉에만 있으면 안 싣는다.** 섞인 합은 성분이 아니라 잡탕이다 —
        # 통합 장부는 다리 아홉을 한 통에 모으므로 한 다리만 실가격인 판이
        # 실제로 생긴다(민평 이력 밖 구간·선물 다리).
        out[name] = round(sum(vals), 2) if vals and len(vals) == len(points) else None
    out["total"] = round(sum(p["dailyPnl"] for p in points), 2)
    return out


def spans_for(dates: list[str], points: list[dict], trades: list[dict],
              cost_bp: float) -> list[dict]:
    """네 구간을 **한 번에** 낸다 — 화면이 고르개를 돌려도 서버에 안 묻는다.

    구간은 엔진을 다시 안 돌리므로(모듈 머리 §구간) 네 벌을 내는 비용이 봉
    배열을 네 번 훑는 것뿐이다. 대신 고르개가 조용한 재계산도 stale 도 안
    만든다 — 값이 이미 와 있기 때문이다.
    """
    out = []
    for key, months in SPANS:
        i = span_start(dates, months)
        out.append({"span": key, **score(dates, points, trades, i, cost_bp)})
    return out
