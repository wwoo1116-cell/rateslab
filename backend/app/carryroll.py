# -*- coding: utf-8 -*-
"""MR 계열의 **앞을 보는 캐리·롤다운** — 그 계열의 호가 bp 로.

[OWNER 2026-10-16 — "캐리/롤다운 표랑 RV랑 같이 제공해주면 되지 않을까"]

계획면(`mrplan`)은 「지금 어디에 있고 얼마면 무엇을 하나」만 말한다. 그 표의
순위(Calmar)는 **지나간** 손익이라 «들고 있는 동안 돈을 받나 내나» 가 안 들어
있다. 같은 z 라도 캐리가 음수인 계열은 기다리는 값이 다르다 — 이 모듈이 그
한 칸을 만든다.

## 왜 또 쓰나 — `theta.py` 가 있는데

`theta.py` 가 같은 양을 이미 잰다(커브 동결 · 캐리 + 롤다운 · 분기로 재서 하루로
나눠 적기). **산술은 그것을 그대로 따른다.** 다른 것은 **커브**다:

    theta.py   wall 의 `Dataset` — `mkt_irs_close` + asof 하루만 종합ALL
    여기       `mrseries.bundle()` — imx 종합ALL · 국고는 민평(2020-01-02~)

MR 계열의 **호가가 뒤엣것으로 서 있다**(`mrseries.points` · `combo_points`).
「진입과 롤인이 같은 구성에서 나와야 차이가 순수한 기울기」라는 `theta.py` 머리의
규율이 여기서는 **「계열의 값과 그 값의 롤이 같은 커브에서 나와야 한다」** 가
된다. 앞엣것으로 재면 롤이 계열의 레벨과 안 닫히고, 그러면 이 리포가 반복해
밟은 **출처 둘** 결함(2026-10-07 「종가 출처가 둘」)이 그대로 재현된다.

그래서 **알고리즘은 하나, 입력이 둘**이다. 같은 커브를 주면 두 길이 같은 수를
내야 하고 `tests/test_carryroll.py` 가 그 항등을 잡는다.

## 부호는 **방향 +1**(호가값 롱) — 제품이 이미 쓰는 그 정의

`mr.DIR_LEGS` 의 `plus` 다: BSS +1 = IRS 페이 · 국고 매수, IRC +1 = 스티프너,
IRF +1 = 벨리 페이. `theta.py` 의 "방향 +1" 과 같은 문장이고, 그래서 **음수면 그
계열의 첫 번째 방향을 잡았을 때 시간이 돈을 가져간다.**

⚠ `mrcarry` 는 반대다 — 그 모듈의 연 캐리는 `position = -1` 기준이다(엔진이
`c = -position × carry` 로 먹는다). 여기서 한 번 뒤집고, 뒤집는 자리가 이 파일에
**하나뿐**이다(`_carry_bp`).

## 두 성분

    캐리   = `mrcarry` 의 연 캐리(%) 를 그 계열 **호가 bp** 로 환산
    롤다운 = 커브를 동결하고 h 만큼 나이 들었을 때 **호가가 저절로 가는 거리**
    세타   = 캐리 + 롤다운

롤다운을 「호가가 가는 거리」로 잡는 것이 이 계열들에서 맞는 이유: MR 엔진의
손익은 `Δ호가 × 그 계열의 DV01` 이다(`mrbacktest.simulate`). 포지션이 h 만큼
나이 들면 그 마크는 **(T−h) 자리의 값**으로 수렴하므로, 수렴 거리를 호가 bp 로
적으면 그것이 곧 손익이다. 엔진의 단위와 같아서 `exitGap`(청산까지 bp)과 **그냥
더할 수 있다** — 이 모듈이 계획면에 붙는 이유가 그 가산성이다.

## ★커브는 **부트스트랩한 제로커브**에서 읽는다 — par 선형보간이 아니다

처음에 `T − h` 를 **호가 par 금리의 선형보간**으로 읽었더니 같은 커브 위에서
`theta.py` 와 롤이 **30~100% 갈렸다**(실측 2026-10-16, asof 10-15):

    IRC-2Y-10Y    theta 1.99bp   선형보간 2.65bp
    IRC-1Y-2Y     theta 4.90bp   선형보간 5.88bp
    IRF-2Y-5Y-10Y theta 0.59bp   선형보간 1.23bp

롤은 **가까운 두 점의 차**라 보간 방식이 통째로 신호에 실린다 — 「작은 수의
30%」가 아니라 그 수 자체다. 그래서 `theta.py` 와 **같은 길**로 읽는다:
par 금리 → `bootstrap_zero_curve` → `forward_par_rate(zc, T)`.

같은 커브를 주면 **아웃라이트는 theta 와 소수점까지 같다**(실측: 1Y −8.7500 ·
2Y −2.4528 · 3Y −1.4236 · 10Y −0.1649, 두 길이 4자리까지 일치). 커브 경로가
공유됐다는 증거가 그 항등이고 `tests/test_carryroll.py::test_outright_roll_matches_theta`
가 그것을 잡는다.

## ⚠ 패키지는 theta 와 **일부러** 다르다 — 연금비 가중

    IRC-2Y-10Y     theta 2.0366   여기 2.2880   비 1.12
    IRC-1Y-2Y      theta 5.0459   여기 6.2970   비 1.25
    IRF-2Y-5Y-10Y  theta 0.6113   여기 1.4120   비 **2.31**

theta 는 **진입 명목을 고정한 채** 호라이즌에서 다리마다 다시 값을 매긴다 —
다리의 연금이 저마다 다른 속도로 줄어 DV01 중립이 풀리고, 그 풀림이 숫자에
들어간다. 실제로 북에 넣은 패키지의 손익은 그쪽이 맞다.

여기는 **호가 드리프트**다. 근거는 **MR 엔진의 손익 식**이다 —
`mrbacktest.simulate` 는 `Δ호가 × ₩/bp` 하나로 손익을 세고 다리 DV01 의 표류를
모른다. 이 표의 쓸모가 `exitGap`(청산까지 bp)과 **더해지는 것**이므로, 같은
세계의 수라야 그 덧셈이 참이다. 엔진의 근사 안에서 일관된 쪽을 고른 것이고,
**둘이 다르다는 사실 자체가 플라이에서 2.3배**라 여기 적어 둔다.

★**양 끝을 다 커브에서 읽는다** — 「진입은 호가, 롤인은 커브」로 섞으면 그 차가
통째로 롤다운에 실려 기울기가 아닌 것을 기울기라고 말하게 된다(`theta.py` 머리의
그 문단). 롤은 차라서 레벨 규약이 상쇄되므로, 이 선택이 계열의 공시 레벨
(`mrseries.points`)과 어긋나는 일은 없다.

★**CD 91일을 IRS 커브의 3M 노드로 넣는다.** `mrcarry` 가 이미 그렇게 적어 뒀다
(「CD 91일 = 스펙의 3M 노드 — `_fetch_irs` 의 매핑에는 6M~10Y 만 있어 따로
읽는다」). 짧은 끝이 안 서면 부트스트랩의 1Y 밑이 외삽이 되고, BSS-6M 처럼
`T − h` 가 0.25 로 떨어지는 계열이 통째로 빈다.

국고 다리도 **같은 길**로 읽는다. 민평 국고는 par 금리가 아니라 채권 수익률이라
par 로 다루는 것은 근사지만, **두 다리가 같은 방식이어야** BSS 의 롤이 깨끗한
기울기 차가 된다 — 한쪽만 선형으로 읽으면 보간 인공물이 안 상쇄되고 그 찌꺼기가
스프레드 롤로 나온다. [알려진 근사]

## 캐리의 bp 환산 — 한 줄 대수

`mrcarry.carry_krw` 의 규약 그대로다. 화면 노브가 `₩/bp`(=DV01)이고

    원금 P   = DV01 / (pv01 × 1e-4)            (`mrcarry` 머리 「명목 환산」)
    현금     = P × (rate/100) × h
    캐리(bp) = 현금 / DV01 = rate × h × 100 / pv01

DV01 이 약분되어 **노셔널에 무관**하다(`theta.perDv01` 이 무관한 것과 같은 이유).
`pv01` 은 **기준 다리**의 것이다 — BSS 는 그 만기, 커브는 긴 쪽, 플라이는 벨리
(`mrcarry._tenor_of` 의 그 규약). 기준 다리의 DV01 이 곧 호가 1bp 의 손익이라
(커브: `D·Δ긴 − D·Δ짧은 = D·Δ호가`, 플라이: `2D·Δ벨리 − D·Δ윙 = D·Δ호가`)
환산이 세 종류에서 **같은 식 하나**로 닫힌다.

## 호라이즌은 `theta.HORIZON_Y` 를 빌린다 — 분기

하루로 직접 재면 롤이 잡음이 된다는 실측(1Y 6.2배 · 10Y 18.9배 과대)이 그
모듈에 있다. 여기서도 **분기로 재고**, 하루치는 나눠서 같이 싣는다(`perDay`).
상수를 빌리는 이유는 둘이 갈리면 wall 의 세타와 이 표가 다른 창을 말하기 때문.

## 정밀도 — 롤은 **±0.2bp 쯤**이다

부트스트랩은 제로를 선형보간해 par 를 되짓는 물건이라 **호가 노드에서조차 par 가
정확히 되돌아오지 않는다**: 실측(2026-10-15 종합ALL) 2Y 0.03bp · 5Y 0.27bp ·
10Y 0.17bp, 노드 간격이 넓을수록 크다. 롤은 **0.25년 떨어진 두 점의 차**라 그
편의가 상당 부분 상쇄되지만, 남는 것이 이 표의 정밀도 하한이다.

그래서 **0.2bp 안쪽의 차이로 계열 순위를 바꾸지 말 것.** 쓸모 있는 자리는
「캐리·롤이 +4bp 인가 −2bp 인가」이지 「+0.41 과 +0.33 중 어느 쪽이 큰가」가
아니다. 같은 이유로 BSS 의 평행 스프레드 롤이 정확히 0 이 아니라 **−0.02bp**
다(`tests/test_carryroll.py` 의 그 시험).

## 못 재는 자리는 **빈다**

`T − h` 가 커브의 **가장 짧은 노드보다 앞이면 외삽**이라 `None` 이다. 실제로
BSS-6M(0.5 − 0.25 = 0.25)과 IRF-6M-9M-1Y 가 여기 걸린다 — 국고 민평에 3M 노드가
없다. 0 으로 채우면 「캐리가 없는 계열」이 되는데 그건 다른 말이다.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from . import funding as fnd
from . import mrcarry
from . import mrseries as mrs
from . import theta as theta_mod
from .curves import TENOR_T
from .dv01 import pv01 as pv01_of_zc
from .engine_port import bootstrap_zero_curve
from .forwards import forward_par_rate

log = logging.getLogger("app.carryroll")

#: 호라이즌 — `theta.py` 의 그 창. 빌리는 이유는 이 모듈 머리에.
HORIZON_Y = theta_mod.HORIZON_Y
HORIZON_DAYS = theta_mod.HORIZON_DAYS

#: 이 모듈이 다루는 계열 종류. FSW·FUT 는 **아직 아니다** — 선물 다리의 롤은
#: 베이시스 수렴이라 커브 보간으로 안 서고, 없는 것을 0 으로 적으면 「롤이 없는
#: 계열」이 된다(머리의 그 규칙). 빠진 계열은 호출자가 `None` 을 받는다.
KINDS = ("bss", "irc", "irf")


def _tenors_of(sid: str, kind: str) -> list[str]:
    """계열의 다리 만기 — 호가 식에 들어가는 차례 그대로.

    BSS 는 하나(두 다리가 같은 만기의 스왑·국고), 커브·플라이는
    `mrseries.combo_tenors` 의 차례(짧은 → 긴)다.
    """
    if kind == "bss":
        return [mrs.tenor_of(sid)]
    return mrs.combo_tenors(sid)


def _quote_bp(kind: str, ts: list[float], irs: Callable[[float], float | None],
              ktb: Callable[[float], float | None]) -> float | None:
    """만기 목록 `ts`(연수)에서 읽은 **호가 bp** — 계열의 값 정의 그대로.

    정의는 `mrseries.points`·`combo_points` 와 **같은 식**이어야 한다. 갈리면
    롤다운이 계열의 레벨과 안 닫힌다:

        bss  (IRS − 국고) × 100          [OWNER 2026-09-22 규약: 스왑 − 현물]
        irc  (긴 − 짧은) × 100
        irf  (2×벨리 − 윙) × 100

    한 다리라도 못 읽으면 `None` 이다 — 다리 둘로 그린 플라이는 완성돼 보이면서
    틀린다(`theta.theta_table` 의 그 규칙).
    """
    if kind == "bss":
        s, g = irs(ts[0]), ktb(ts[0])
        return None if s is None or g is None else (s - g) * 100.0
    vals = [irs(t) for t in ts]
    if any(v is None for v in vals):
        return None
    if kind == "irc":
        short, long = vals                       # combo_tenors 는 짧은 → 긴
        return (long - short) * 100.0            # type: ignore[operator]
    w_s, belly, w_l = vals
    return (2.0 * belly - w_s - w_l) * 100.0     # type: ignore[operator]


#: 세타를 붙일 수 있는 **최소 잔존**. `theta.theta_table.priceable` 의 그 문턱이고
#: 근거도 같다 — 잔존 한 분기 밑의 par 금리는 커브의 가장자리라 보간·외삽이
#: 지배한다. 「문턱은 상품의 성질이지 호라이즌의 함수가 아니다」.
MIN_REMAIN_Y = 0.25


def _par_reader(nodes: list[tuple[float, float]]
                ) -> tuple[Callable[[float], float | None], Any]:
    """[(연수, %)] → (**par 금리 조회(%)**, 제로커브). **외삽은 안 한다**.

    `theta.py` 와 같은 길이다: par 금리를 부트스트랩해 제로커브를 세우고,
    임의의 만기 par 금리를 `forward_par_rate` 로 되읽는다. 선형보간을 쓰면 안
    되는 이유는 이 모듈 머리의 실측 표에.

    범위 밖(가장 짧은 노드 앞 · 가장 긴 노드 뒤)과 `MIN_REMAIN_Y` 밑은 `None`
    이다 — 부트스트래퍼는 그 자리에서도 수를 내주지만, 그 수는 커브가 아니라
    외삽이라 롤이라고 부를 수 없다(머리의 「못 재는 자리는 빈다」).
    """
    if not nodes:
        return (lambda _t: None), None
    zc = bootstrap_zero_curve([(t, v / 100.0) for t, v in nodes])
    lo, hi = nodes[0][0], nodes[-1][0]

    def read(t: float) -> float | None:
        if t < max(lo, MIN_REMAIN_Y) - 1e-9 or t > hi + 1e-9:
            return None
        return float(forward_par_rate(zc, t, None)) * 100.0

    return read, zc


def curve_nodes(curve: dict[str, dict[str, float]], asof: str) -> list[tuple[float, float]]:
    """`mrseries.bundle()` 의 한 커브를 asof 하루의 [(연수, %)] 로.

    **그 날 찍힌 노드만** 담는다 — 이월해 채우면 없던 커브를 지어내게 된다
    (`mrseries.legs` 의 그 규율).

    ⚠ `curves.TENOR_T` 에 **없는 라벨은 버린다.** 국고 민평은 `2.5Y·20Y·30Y` 를
    들고 오는데 그 표에 없어서 셋 다 빠진다(IRS 쪽은 전부 든다). 20Y·30Y 는
    이 계열들의 최장이 10Y 라 무해하고, **2.5Y 만 실질적인 손실**이다 — BSS-3Y
    의 `T − h = 2.75` 가 2Y·3Y 사이 보간으로 서게 된다. 그 차이는 이 모듈
    머리의 정밀도(±0.2bp) 안이라 두고 간다. 여기에 두 번째 만기 파서를 들이면
    `TENOR_T` 와 갈릴 자리가 하나 더 는다.
    """
    out: list[tuple[float, float]] = []
    for tenor, by_date in curve.items():
        t = TENOR_T.get(tenor)
        v = by_date.get(asof)
        if t is not None and v is not None:
            out.append((t, float(v)))
    return sorted(out)


def _roll_bp(sid: str, kind: str, irs: Callable[[float], float | None],
             ktb: Callable[[float], float | None], h: float) -> float | None:
    """커브 동결 · h 만큼 나이 들었을 때 **호가가 가는 거리**(bp).

        롤 = 호가(T − h) − 호가(T)

    우상향 커브에서 BSS·IRC 가 어떤 부호인지는 **두 커브의 기울기 차**가 정한다 —
    한 쪽만 보고 부호를 외우면 틀린다. 그래서 이 함수는 부호를 모르고, 같은
    식을 두 번 읽을 뿐이다. 양 끝을 **같은 조회**로 읽는 것이 요점이다(머리).
    """
    ts = [TENOR_T[t] for t in _tenors_of(sid, kind)]
    now = _quote_bp(kind, ts, irs, ktb)
    aged = _quote_bp(kind, [t - h for t in ts], irs, ktb)
    if now is None or aged is None:
        return None
    return aged - now


def _carry_bp(rate_minus1: float, pv01_ref: float, h: float) -> float:
    """연 캐리(%) → **호가 bp**. 부호를 `position = -1` 에서 **+1 로 뒤집는다**.

    식의 유도는 이 모듈 머리 「캐리의 bp 환산」. 뒤집는 자리가 이 파일에서
    여기 하나뿐이라, 규약이 또 바뀌어도 고칠 곳이 한 줄이다.
    """
    return -rate_minus1 * h * 100.0 / pv01_ref


def for_series(sid: str, kind: str, *, asof: str | None = None,
               spec: fnd.FundingSpec | None = None,
               bundle: dict[str, Any] | None = None) -> dict | None:
    """계열 하나의 앞을 보는 캐리·롤다운 — **방향 +1 · 호가 bp · 분기**.

    `bundle` 을 받으면 그것을 쓴다(시험이 합성 커브로 이 산술 전부를 돌릴 수
    있게 — `mrplan` 이 `leg_of` 를 받는 것과 같은 이유). 안 주면
    `mrseries.bundle()` 이다.

    못 서면 `None` 이다. 호출자는 **그 칸을 비운다** — 0 이 아니다.
    """
    if kind not in KINDS:
        return None
    b = bundle if bundle is not None else mrs.bundle()
    spec = spec or fnd.FundingSpec().validated()

    irs_curve = b.get("irs") or {}
    ktb_curve = b.get("ktb") or {}

    # asof = 이 계열의 다리가 **다 찍힌** 마지막 날. 계열마다 다를 수 있고,
    # 다르면 그 사실이 payload 에 적혀야 한다(가족 단위 asof 가 낡은 다리를
    # 가린 전례 — `mrseries._merge_govt` 머리).
    tenors = _tenors_of(sid, kind)
    day_sets = [set((irs_curve.get(t) or {})) for t in tenors]
    if kind == "bss":
        day_sets.append(set(ktb_curve.get(tenors[0]) or {}))
    if not day_sets or not all(day_sets):
        return None
    days = set.intersection(*day_sets)
    if asof is not None:
        days = {d for d in days if d <= asof}
    if not days:
        return None
    day = max(days)

    irs_nodes = curve_nodes(irs_curve, day)
    # ★CD 91일 = IRS 커브의 **3M 노드** (머리). 커브가 이미 3M 을 가지고 있으면
    # 안 덮는다 — 같은 자리에 두 출처를 포개지 않는다.
    cd = (b.get("cd") or {}).get(day)
    if cd is not None and not any(abs(t - TENOR_T["3M"]) < 1e-9 for t, _ in irs_nodes):
        irs_nodes = sorted([*irs_nodes, (TENOR_T["3M"], float(cd))])
    ktb_nodes = curve_nodes(ktb_curve, day) if kind == "bss" else []
    if not irs_nodes or (kind == "bss" and not ktb_nodes):
        return None

    irs_read, zc = _par_reader(irs_nodes)

    def _no_govt(_t: float) -> float | None:
        """국고 다리가 없는 계열(커브·플라이)의 자리 — 읽으면 `None` 이다."""
        return None

    ktb_read: Callable[[float], float | None] = _no_govt
    if kind == "bss":
        ktb_read, _ktb_zc = _par_reader(ktb_nodes)

    roll = _roll_bp(sid, kind, irs_read, ktb_read, HORIZON_Y)
    if roll is None:
        return None

    # 캐리는 `mrcarry` 가 정본이다 — BSS 는 항등 자기검사(`assert_identity`)가
    # 붙어 있는 그 식이고, 커브·플라이는 DV01 중립 가중이 들어간 그 식이다.
    ref = TENOR_T[mrcarry._tenor_of(sid)]        # noqa: SLF001 — 같은 규약의 주인
    pv01_ref = pv01_of_zc(zc, ref)
    if pv01_ref <= 0:
        return None

    weights = None
    if kind in ("irc", "irf"):
        weights = mrcarry.combo_weights(sid, lambda t: pv01_of_zc(zc, TENOR_T[t]))
    rates, defn_minus1 = mrcarry.carry_rates(sid, kind, [day], spec, weights=weights)
    if not rates or rates[0] is None:
        return None

    carry = _carry_bp(rates[0], pv01_ref, HORIZON_Y)
    total = carry + roll
    return {
        "asof": day,
        "horizonY": HORIZON_Y,
        # 방향 +1 기준 · 그 계열의 호가 bp · **분기치**.
        "carryBp": round(carry, 3),
        "rollBp": round(roll, 3),
        "thetaBp": round(total, 3),
        # 하루치 — wall 의 `theta` 블록과 같은 단위로 견주라고 같이 싣는다.
        "perDay": {
            "carryBp": round(carry / HORIZON_DAYS, 5),
            "rollBp": round(roll / HORIZON_DAYS, 5),
            "thetaBp": round(total / HORIZON_DAYS, 5),
        },
        # 캐리 정의 문장은 **`mrcarry` 의 것 하나**다. 그 문장은 `position = -1`
        # 기준이므로 뒤집혔다는 사실을 같이 적는다 — 문장을 두 벌 들면 갈린다.
        "carryDefnMinus1": defn_minus1,
        "sign": "+1",
        "pv01Ref": round(pv01_ref, 6),
    }


def table(series: list[tuple[str, str, str]], *, spec: fnd.FundingSpec | None = None,
          bundle: dict[str, Any] | None = None) -> dict[str, dict]:
    """계열 목록 → {id: 블록}. **못 서는 계열은 아예 빠진다**(`theta_table` 과 같은 규칙).

    번들을 한 번만 읽어 돌린다 — `mrseries.bundle()` 은 SSL 왕복이 붙은 물건이라
    계열마다 부르면 보드 한 번에 수십 번이 된다(그 모듈 `_WATERMARK_TTL_S` 의 근거).
    """
    b = bundle if bundle is not None else mrs.bundle()
    out: dict[str, dict] = {}
    for sid, _label, kind in series:
        if kind not in KINDS:
            continue
        try:
            blk = for_series(sid, kind, spec=spec, bundle=b)
        except (KeyError, ValueError) as exc:
            log.warning("[carryroll] %s: %s", sid, exc)
            continue
        if blk is not None:
            out[sid] = blk
    return out
