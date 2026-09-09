# -*- coding: utf-8 -*-
"""평균회귀 백테스트의 **캐리** — 두 다리의 중간 현금흐름
[OWNER 2026-08-27 — "중간에 CF는 상쇄되는건가?" · "퓨처스왑도 마찬가지임"].

## 안 상쇄된다

`mrbacktest` 의 원본(PMS 이식) 산술은 손익이 **스프레드 변화뿐**이다. 실제
거래에는 다리마다 중간 현금흐름이 붙고, 두 다리를 합쳐도 **남는다**:

    BSS −1 = 국고 매수 · IRS 페이
        국고 매수 :  + 쿠폰 − 조달        ≈ +(국고금리 − 조달)
        IRS 페이  :  − 고정  + CD 91일    ≈ +(CD − 스왑고정)
        합계      = (국고 − 스왑) + (CD − 조달) = **BSS + (CD − 조달)**

    FSW −1 = 선물 매수 · IRS 페이
        선물 매수 :  **0**  ← 조달 현금흐름이 없다(아래)
        IRS 페이  :  +(CD − 스왑고정)
        합계      = **CD − 스왑고정**

    FUT −1 = 선물 매수
        합계      = **0**

부호 기준은 언제나 `position = -1` 이다(`mrbacktest.simulate` 의 `carry` 규약).
반대 방향은 엔진이 `-position` 으로 뒤집는다 — 같은 베이시스를 반대로 무는 것이
맞다.

## 선물에 조달 항을 붙이지 않는 이유

선물은 증거금만 걸고 일일정산한다 — 원금을 조달하지 않는다. 채권의 캐리는
**선물 가격에 이미 박혀 있고**(인도일로 가면서 베이시스가 수렴한다), 이 엔진이
재는 값은 그 가격에서 나온 **내재수익률**이다. 그래서 조달을 또 빼면
**이중계상**이다.

그 결과 BSS 와 FSW 는 캐리의 **부호가 다를 수 있다**: 커브가 우상향이면
`CD − 스왑 < 0` 이라 FSW 페이는 음의 캐리이고, BSS 는 거기에 `국고 − 조달` 이
더 붙어 대개 양이다. 둘의 차가 정확히 «현물을 조달해 들고 있는 값» 이다.

## 명목 환산 — 화면 노브는 `₩/bp`(DV01)다

캐리는 **원금**에 붙는데 노브는 DV01 이라 환산이 필요하다.

    DV01(₩/bp) = 명목 × pv01 × 1e-4       (`dv01.pv01` = 파스왑 연금계수)
    ⇒ 명목 = DV01 / (pv01 × 1e-4)

`pv01` 은 **지금 커브**에서 읽는다. 6년 표본 내내 그 값이 변하는데도 하나로
쓰는 것은 근사다 — 다만 이 환산은 캐리의 **크기만** 정하고 부호나 시점은 안
건드린다(pv01 이 5% 틀리면 캐리가 5% 틀리고, 그건 거래 손익의 0.5% 수준이다).
정확히 하려면 봉마다 커브를 다시 세워야 하는데, 이 엔진은 커브가 아니라 **한
계열의 시계열**만 받는 물건이라 그 자리가 없다. [알려진 근사]

## 하루가 아니라 실제 날수

봉 사이가 늘 하루는 아니다(금→월은 사흘). 캐리는 **달력 날수**로 쌓는다 —
`ACT/365`. 이 근사가 무해한 이유는 이 앱의 조달 모듈이 이미 같은 규약이기
때문이다(`funding.cost_between`).
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Callable

from . import funding as fnd
from .universe import _fetch_curves, _fetch_irs  # noqa: PLC2701 — 같은 데이터 창구
from . import mrseries as mrs
from .mysqldb import engine
from .mr import FSW_IRS_COL


#: CD 91일 = 스펙의 **3M 노드**. `universe._fetch_irs` 의 매핑에는 6M~10Y 만
#: 있어 따로 읽는다.
#:
#: ## 출처는 하나다 — imx `단기금리 · CD 91일물` [OWNER 2026-09-02]
#:
#: 종전에는 BSS 만 imx 를 읽고 FSW 는 `sim_portfolio.mkt_irs_close.cd_rate` 를
#: 읽었다. 한 화면의 두 캐리가 다른 CD 위에 서 있었고, 겹치는 날의 **70.1%**
#: 가 불일치(평균 4.15bp·최대 61bp)였다.
#:
#: 어느 쪽이 「지금 CD」인가를 실측으로 갈랐다(2026-09-02):
#:
#:   · `mkt` 는 imx 를 **10영업일 지연**시킨 계열에 가장 가깝다 — 같은 날
#:     평균절대차 4.15bp 인데 imx 를 10영업일 당기면 **0.53bp** 로 준다.
#:   · 제3의 표 `infomax.단기금리.CD_3개월` 이 imx 와 소수점까지 같다
#:     (2022-10: imx·infomax 3.28 → 3.85 인 구간에 mkt 는 2.99 → 3.32).
#:   · 범위도 imx 가 넓다 — mkt 는 2016-01 부터라 BSS 12년 표본의 앞
#:     406일(2014-05~2016-01)에 캐리가 없다.
#:
#: 그래서 `mkt_irs_close.cd_rate` 를 이 파일에서 **안 읽는다**. 그 열은 IRS
#: 종가 표의 부속이지 CD 의 정본이 아니다.
#: (구 출처였던 `mkt_irs_close.cd_rate` 의 열 이름은 **안 남긴다** — 안 읽는
#: 상수가 파일에 서 있으면 다음 사람이 그 열을 아직 쓴다고 읽는다. 이력은 위
#: 주석이 진다.)


def _tenor_of(sid: str) -> str:
    """계열 id 의 **기준 만기**. `BSS-3Y` → `3Y`, `FSW-10Y` → `10Y`.

    커브·플라이는 다리가 둘·셋이라 「그 계열의 만기」가 하나가 아니다. 기준은
    **가중이 100 으로 정규화되는 다리**다(`dv01.dv01_payload` 의 그 규약):
    스프레드는 **긴 쪽**, 플라이는 **벨리**. 명목(₩/bp)의 원금 환산이 이 만기의
    pv01 로 서고, 나머지 다리는 pv01 비로 따라온다(`combo_weights`).
    """
    if sid.startswith("FSW-"):
        return FSW_IRS_COL[sid][0]
    if sid.startswith("IRC-"):
        return sid.split("-")[-1]                      # 긴 쪽
    if sid.startswith("IRF-"):
        return sid.split("-")[2]                       # 벨리
    return sid.split("-", 1)[1]


def combo_weights(sid: str, pv01_of: "Callable[[str], float]") -> list[float]:
    """다리마다의 **가중** — 기준 다리의 원금을 1 로 둔 배수.

    DV01 중립이 이 거래의 정의다(`dv01.py` 머리: 아무도 커브를 같은 명목으로
    치지 않는다). 기준 다리의 DV01 을 `D` 라 하면

        스프레드   긴 D · 짧은 D              → 원금 비 = pv01(긴)/pv01(짧은)
        플라이     벨리 2D · 윙 각 D          → 벨리 2 · 윙 pv01(벨리)/pv01(윙)

    벨리가 2 인 것은 값의 규약(`2·벨리 − 윙`) 때문이다: 그 값이 1bp 움직일 때의
    손익이 `D/2` 가 되도록 벨리에 윙 둘의 합만큼을 건다 — `dv01.dv01_payload`
    가 벨리를 100 으로 두고 윙을 각각 절반씩 맞추는 그 가중과 같은 것이다.

    차례는 `LEG_NAMES` 의 차례이고, **첫 다리가 리시브 쪽**이다(`position = -1`
    기준 — 값이 내리는 데 거는 쪽). 그 약속이 아래 산술의 부호를 정한다.
    """
    ts = sid.split("-")[1:]
    if sid.startswith("IRC-"):
        short, long = ts
        return [1.0, pv01_of(long) / pv01_of(short)]
    if sid.startswith("IRF-"):
        s_w, belly, l_w = ts
        return [2.0, pv01_of(belly) / pv01_of(s_w), pv01_of(belly) / pv01_of(l_w)]
    raise KeyError(f"{sid}: 커브·플라이가 아니다")


def carry_rates(sid: str, kind: str, dates: list[str],
                spec: fnd.FundingSpec,
                *, weights: list[float] | None = None) -> tuple[list[float | None], str]:
    """`position = -1` 을 하루 들고 있을 때의 **연 캐리(%)** — 봉마다 하나.

    돌려주는 둘째 값은 화면이 읽을 정의 문장이다(숫자 옆에 무엇인지가 없으면
    읽는 사람이 부호를 자기 방향으로 읽는다 — `mr.KIND_DEFN` 과 같은 규율).

    **이 함수는 이제 `carry_rates_by_leg` 의 합이다.** 이 모듈 머리의 식이 원래
    다리별로 적혀 있었는데(「국고 매수: +(국고 − 조달) · IRS 페이: +(CD − 스왑)」)
    코드가 그 둘을 더한 값만 내보내고 있었다. 대사표가 다리마다 캐리를 세우려면
    안 접힌 것이 필요하다 [OWNER 2026-09-03]. 합의 값은 한 자도 안 바뀐다.
    """
    legs = carry_rates_by_leg(sid, kind, dates, spec, weights=weights)
    defn = CARRY_DEFN[kind]
    out: list[float | None] = []
    for i in range(len(dates)):
        vals = [r[i] for _, r in legs]
        out.append(None if any(v is None for v in vals) else sum(vals))
    return out, defn


#: 다리 이름 — 화면의 대사표 구분 칸이 이 말을 쓴다. 계열 종류마다 다르고,
#: 길이가 곧 «다리 몇 개인가» 다(하나면 대사표가 백테스트와 같은 3줄이 된다).
LEG_NAMES: dict[str, tuple[str, ...]] = {
    "bss": ("국고", "IRS"),
    "fsw": ("선물", "IRS"),
    "fut": ("선물",),
    # 커브·플라이는 **만기를 이름에 못 넣는다** — 이 사전은 종류마다 하나인데
    # 조합마다 만기가 다르다(만기는 행 이름 「IRS 3Y-10Y」가 말한다). 차례는
    # 값의 차례다: 커브는 `긴 − 짧은`, 플라이는 `2×벨리 − 윙`.
    "irc": ("긴 다리", "짧은 다리"),
    # ⚠ 플라이의 이름이 여기 있는 것은 **캐리 때문**이고, 대사표의 다리 줄은
    # 안 선다 — `mrseries.combo_points` 가 플라이에는 다리 레벨을 안 싣고
    # (`sign = -1 if j == 0 else 1` 규약이 `2×벨리 − 윙` 에서 거짓이라),
    # `main._attach_leg_recon` 이 레벨을 못 찾아 통째로 접는다. 그 자리에는
    # 종합 한 줄짜리 대사표가 선다.
    "irf": ("벨리", "짧은 윙", "긴 윙"),
}

#: 캐리 정의 문장 — 종전에 `carry_rates` 가 자리마다 돌려주던 그 문자열이다.
CARRY_DEFN: dict[str, str] = {
    "bss": "(국고 − 조달) + (CD 91일 − IRS)",
    "fsw": "CD 91일 − IRS  (선물 다리는 조달이 없어요)",
    "fut": "선물은 조달 현금흐름이 없어요 (캐리 0)",
    # 커브·플라이는 **스왑끼리**라 조달이 없다 — 원금을 주고받지 않는다.
    # 남는 것은 다리마다의 (고정 − CD) 액크루얼이고, 다리 크기가 DV01 중립
    # 가중이라 그 비(pv01 비)가 캐리에 그대로 들어간다.
    "irc": "(긴 IRS − CD 91일) 리시브 + (CD 91일 − 짧은 IRS) 페이 · DV01 중립 가중",
    "irf": "(벨리 IRS − CD 91일) 리시브 ×2 + (CD 91일 − 윙 IRS) 페이 · DV01 중립 가중",
}


def carry_rates_by_leg(
    sid: str, kind: str, dates: list[str], spec: fnd.FundingSpec,
    *, weights: list[float] | None = None,
) -> list[tuple[str, list[float | None]]]:
    """다리마다의 **연 캐리(%)** — `(이름, 봉마다 하나)` 의 목록.

    부호 기준은 `carry_rates` 와 같은 `position = -1` 이고, 엔진이 봉마다
    `-position` 을 곱한다(`mrbacktest.simulate`: `c = -position * carry[i]`).
    그 곱셈이 **선형**이라 다리별 합이 총 캐리와 한 자도 안 갈린다 — 대사표의
    「다리 캐리 합 = 캐리」가 항등으로 닫히는 근거다.
    """
    if kind == "fut":
        rates = [[0.0] * len(dates)]
    elif kind in ("irc", "irf"):
        if weights is None:
            raise ValueError(f"{sid}: 커브·플라이는 가중이 있어야 캐리가 선다")
        rates = _irs_combo_rates_by_leg(sid, dates, weights)
    elif kind == "bss":
        # 값 계열이 긴 출처로 옮겨갔으므로(`mrseries`) **캐리도 같은 출처**에서
        # 읽는다 [OWNER 2026-08-28 — "옮기고"]. 안 그러면 2014~2020 구간에서
        # 국고·IRS 를 못 찾아 캐리가 조용히 0 이 되고, 6년치 손익이 캐리 없이
        # 계산된다 — 없는 값을 0 으로 채우는 그 사고다.
        rates = _bss_rates_by_leg(sid, dates, spec)
    else:
        # 남는 kind 는 **퓨처스왑뿐**이다. 종전에는 이 자리가 fall-through 였고
        # 그 아래에 닿지 않는 `kind == "bss"` 분기가 서 있었다 — 안 도는 코드가
        # 「BSS 캐리는 이렇게 계산한다」고 말하면 다음 사람이 그것을 읽는다
        # (2026-09-02 감사). 이제 세 갈래가 다 이름을 대고 서 있다.
        rates = _fsw_rates_by_leg(sid, dates)
    # **이름은 한 곳에서만 온다.** 종전에는 계산하는 자리마다 문자열을 적었는데,
    # 화면 쪽(`main._attach_leg_recon`)은 `LEG_NAMES` 로 다리를 찾으므로 둘이
    # 갈리면 캐리가 조용히 0 이 되고 대사표가 통째로 사라진다 — 예외도 안 난다.
    # 짝지음을 한 줄로 모아 그 갈릴 자리를 없앤다(2026-09-03 감사).
    names = LEG_NAMES[kind]
    if len(rates) != len(names):
        raise ValueError(f"{kind}: 다리 수({len(rates)})가 이름 수({len(names)})와 달라요")
    return list(zip(names, rates))


def _irs_combo_rates_by_leg(
    sid: str, dates: list[str], weights: list[float],
) -> list[list[float | None]]:
    """커브·플라이의 다리별 연 캐리(%) — **기준 다리 원금 위에서** 잰다.

    `position = -1`(값이 내리는 데 거는 쪽)의 다리는 첫 칸이 **리시브**, 나머지가
    **페이**다(`combo_weights` 의 그 약속):

        커브 −1 = 플래트너 = 긴 쪽 리시브 · 짧은 쪽 페이
        플라이 −1 = 벨리 리시브 · 윙 페이

    그래서 리시브 다리는 `+(고정 − CD)`, 페이 다리는 `+(CD − 고정)` 이고, 각각에
    가중이 곱해진다. 조달 항이 **없다** — 스왑끼리라 원금을 주고받지 않는다
    (BSS 의 `(국고 − 조달)` 이 여기 없는 이유이고, 그래서 이 계열의 캐리는
    커브의 기울기와 CD 의 자리만으로 정해진다).

    ⚠ 가중은 **지금 커브의 pv01 비**다(`main._mr_leg` 가 재서 넘긴다) — 표본
    전체에 그 하나를 쓰는 것은 캐리의 원금 환산이 이미 지고 있는 근사와 같은
    것이다(이 모듈 머리 「명목 환산」의 [알려진 근사]).
    """
    ts = mrs.combo_tenors(sid)
    if len(ts) != len(weights):
        raise ValueError(f"{sid}: 다리 수({len(ts)})와 가중 수({len(weights)})가 다르다")
    # 차례를 **다리 차례로** 맞춘다 — `combo_tenors` 는 id 의 차례(짧은 → 긴)이고
    # 캐리·이름의 차례는 「리시브 다리부터」다.
    order = [ts[-1], ts[0]] if len(ts) == 2 else [ts[1], ts[0], ts[2]]

    b = bundle_irs = mrs.bundle()
    cd91 = dict(b["cd"])
    curves = {t: bundle_irs["irs"].get(t, {}) for t in order}

    out: list[list[float | None]] = []
    for j, t in enumerate(order):
        w = weights[j]
        sign = 1.0 if j == 0 else -1.0                 # 첫 다리가 리시브
        col: list[float | None] = []
        for d in dates:
            r = curves[t].get(d)
            c = cd91.get(d)
            col.append(None if (r is None or c is None) else w * sign * (r - c))
        out.append(col)
    return out


def _fsw_rates_by_leg(sid: str, dates: list[str]) -> list[list[float | None]]:
    """퓨처스왑의 연 캐리(%) — 선물 다리 `0` · IRS 다리 `CD 91일 − 스왑고정`."""
    tenor = _tenor_of(sid)
    with engine().connect() as conn:
        idates, irs = _fetch_irs(conn)

    # 날짜 → 값. 없는 날은 아예 안 담는다 — 캐리를 지어내지 않는다.
    # **CD 는 한 출처다** — `mrseries`(imx `단기금리 · CD 91일물`).
    cd91 = dict(mrs.bundle()["cd"])
    swap = {d.isoformat(): v for d, v in zip(idates, irs.get(tenor, [])) if v is not None}

    out: list[float | None] = []
    for t in dates:
        s = swap.get(t)
        c = cd91.get(t)
        out.append(None if (s is None or c is None) else c - s)   # CD − 스왑고정

    # 선물 다리는 **0 이 아니라 «0 이라고 아는 값»** 이다 — 이 모듈 머리의 그
    # 문단(증거금·일일정산이라 조달 현금흐름이 없고, 채권 캐리는 이미 선물
    # 가격에 박혀 있어 또 빼면 이중계상)이 근거다. 대사표에 줄로 서야 읽는
    # 사람이 «왜 이 다리는 캐리가 없나» 를 표에서 본다.
    return [[0.0] * len(dates), out]


def _bss_rates_by_leg(
    sid: str, dates: list[str], spec: fnd.FundingSpec,
) -> list[list[float | None]]:
    """BSS 의 연 캐리(%) — 국고 다리 `(국고 − 조달)` · IRS 다리 `(CD 91일 − 스왑)`.

    ⚠ **단위가 다르다.** 커브(국고·IRS·CD)는 %(3.817)이고 `funding.rate_on` 은
    소수(0.0285)다 — 실측 2026-08-27 에 그대로 빼서 100배 틀린 캐리(중앙
    2.667%/년)를 냈다. 대수적으로 이 식은 `BSS + (CD − 조달)` 로 접히므로 0.1%
    안팎이어야 하고, 그 항등이 이 산술의 자기검사다.
    """
    d, govt, swap, cd = mrs.legs(sid, need_cd=True)
    g = dict(zip(d, govt))
    s = dict(zip(d, swap))
    c = dict(zip(d, cd))
    bond: list[float | None] = []
    irs: list[float | None] = []
    for t in dates:
        if t not in g or t not in s or t not in c:
            # **한쪽만 아는 날은 없다** — 셋이 같은 교집합에서 오므로 결측은
            # 늘 같이 온다. 그래도 다리마다 None 을 넣는다: 합을 내는 쪽이
            # 「하나라도 None 이면 None」으로 접으므로 종전 값과 같아진다.
            bond.append(None)
            irs.append(None)
            continue
        f = fnd.rate_on(spec, dt.date.fromisoformat(t)) * 100.0
        bond.append(g[t] - f)
        irs.append(c[t] - s[t])
    return [bond, irs]


def carry_krw(rates: list[float | None], dates: list[str], *,
              notional_per_bp: float, pv01: float) -> list[float]:
    """연 캐리(%) → **봉당 원(₩)**. `mrbacktest.simulate(carry=…)` 이 먹는 꼴.

    첫 봉은 앞 봉이 없어 0 이다. 값이 없는 날(휴일 사이 결측)도 0 으로 둔다 —
    «모르는 날» 에 캐리를 지어내지 않는다.
    """
    principal = notional_per_bp / (pv01 * 1e-4)
    out = [0.0]
    for i in range(1, len(dates)):
        r = rates[i]
        if r is None:
            out.append(0.0)
            continue
        d0 = dt.date.fromisoformat(dates[i - 1])
        d1 = dt.date.fromisoformat(dates[i])
        out.append(principal * (r / 100.0) * ((d1 - d0).days / 365.0))
    return out


def summarize(trades: list[dict[str, Any]]) -> dict[str, float]:
    """거래들의 삼분해 합 — 대사표의 바닥 줄."""
    return {
        "mtm": sum(t.get("mtm", 0.0) for t in trades),
        "carry": sum(t.get("carry", 0.0) for t in trades),
        "cost": sum(t.get("cost", 0.0) for t in trades),
    }


def assert_identity(sid: str, kind: str, dates: list[str],
                    rates: list[float | None], spread_bp: list[float],
                    spec: fnd.FundingSpec) -> None:
    """BSS 의 캐리는 대수적으로 **`BSS + (CD − 조달)`** 로 접힌다.

        (국고 − 조달) + (CD − 스왑) = (국고 − 스왑) + (CD − 조달)

    두 길로 같은 수가 나오는지를 재는 것이 이 함수다. 단위가 어긋나면(커브는
    %, 조달은 소수) 이 항등이 **가장 먼저** 깨진다 — 실측 2026-08-27 에 그
    사고가 났고, 그때 결과는 «그럴듯한 큰 수» 였지 예외가 아니었다.
    """
    if kind != "bss":
        return
    # **같은 CD 를 읽는다** [OWNER 2026-09-02]. 종전에는 이 검사만 `mkt_irs_close`
    # 를 읽어서, 계산은 imx CD 로 하고 검사는 딴 CD 로 하고 있었다 — 그 조합에서
    # 이 항등은 **참인 산술에서도 깨진다**(겹치는 날 70% 불일치). 죽은 코드라
    # 아무도 안 밟았을 뿐이고, 살리는 순간 거짓 경보가 났을 자리다.
    cd91 = dict(mrs.bundle()["cd"])
    for i, t in enumerate(dates):
        if rates[i] is None or t not in cd91:
            continue
        f = fnd.rate_on(spec, dt.date.fromisoformat(t)) * 100.0
        other = spread_bp[i] / 100.0 + (cd91[t] - f)
        if abs(other - rates[i]) > 1e-6:
            raise AssertionError(
                f"{sid} {t}: 캐리 항등이 깨졌어요 — "
                f"직접 {rates[i]:.6f}% vs BSS+(CD−조달) {other:.6f}%"
            )
