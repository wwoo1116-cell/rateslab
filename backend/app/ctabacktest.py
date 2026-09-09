# -*- coding: utf-8 -*-
"""국채선물 **추세추종(CTA)** 엔진 [OWNER 2026-09-07 — "CTA 전략을 구현해보자"].

## 왜 선물인가 — 이 데스크에서 유일하게 제약이 둘 다 없는 자리

- **공매도 제약이 없다.** 다른 모든 레인이 「국고를 못 빌린다」에 걸려 한 방향만
  재현하는데(BSS·스윙·MR), 선물은 양방향이다. 추세추종은 **하락 추세에서 버는
  것이 절반**이므로 이 차이가 결정적이다.
- **대차대조표를 안 쓴다.** MR 통합이 평균 88억·최대 627억을 묶는 대가로 연
  1.02%를 내는데(2026-09-07 실측), 선물은 증거금뿐이다.
- **비용이 확정돼 있다** — 편도 0.5틱(`ktb-futures` 레인이 항등식으로 확정).
  CTA 는 회전이 월 단위라 그 비용이 안 구속한다.
- **표본이 10.7년**(2016-01-04~)이다. 민평이 2020년부터라 MR 은 6.7년뿐이다.

## 가격은 **조정가**를 쓰고 차분만 본다

`futures.price_adj` 는 롤 갭이 빠진 연결 계열이라 **차분만 유효**하다(수준은
아니다 — 레인 규약). 추세 신호는 전부 차분·비교로 만들므로 그대로 맞다.
**롤 마스크는 안 쓴다** — 그건 벤더 내재금리 차분에만 참인 규약이고 조정가
위에서는 죽는다(MR 실가격 회계가 같은 판단을 했다). 대신 **롤 비용은 문다**:
보유 중 갈아타는 날마다 왕복 1틱.

## 신호 셋 [OWNER — "셋 다 넣고 공용 격자로 고른다"]

    tsmom      sign(P_t − P_{t−L})            자유모수 1 (L)
    macross    sign(MA_s − MA_l), s = l//4    자유모수 1 (l) — 짧은 창을 비율로 묶는다
    donchian   L일 최고면 +1 · 최저면 −1       자유모수 1 (L)
               그 사이에는 **직전 방향을 유지**한다(브레이크아웃의 정의)

`macross` 의 짧은 창을 **비율로 묶은 것**이 이 모듈의 유일한 재량이다. 두 창을
따로 열면 이 신호만 자유모수가 둘이 되어 격자에서 부당하게 유리해진다 — 셋을
한 격자에 넣기로 한 이상 자유도를 맞춰야 공정하다.

⚠ 신호계를 격자 차원으로 두면 **자유도를 쓴다.** 그 대가는 PBO 로 잰다
(`scripts/cta_validate.py`) — 논쟁 대신 측정한다.

## 크기 — 변동성 목표 [OWNER]

    액면_t = 목표변동성(원/일) ÷ (σ_t / 100)

`σ_t` 는 최근 `vol_window` 일의 조정가 차분 표준편차(가격포인트)다. 손익이
`액면/100 × Δ가격` 이므로(선물 회계의 그 규약) 위 식이 「하루 표준편차가 목표
금액」을 만든다. **이게 CTA 를 CTA 로 만드는 자리다** — 이게 없으면 그냥 모멘텀
백테스트이고, 3Y·10Y 의 위험도 안 맞는다(10Y 가 3Y 의 세 배 가까이 움직인다).

## 룩어헤드 — 신호는 t 까지, 손익은 t+1 부터

`position[t]` 는 **t 종가까지의 정보**로 정하고 `t+1` 의 차분에 곱한다. σ 도
같다. 이 한 칸이 밀리면 결과가 통째로 거짓이 된다.
"""

from __future__ import annotations

import math
import statistics as st

SIGNALS: tuple[str, ...] = ("tsmom", "macross", "donchian")

#: 짧은 창 = 긴 창 ÷ 이 값. 위 머리의 「자유도를 맞춘다」가 이 상수의 이유다.
MACROSS_RATIO = 4
#: 편도 비용(틱). `futures.TICK` 은 가격 단위 0.01 이고, 이 값은 **틱 수**다.
COST_TICKS = 0.5
TICK = 0.01


class CtaError(ValueError):
    """엔진이 설 수 없는 입력 — 조용히 0 을 내지 않는다."""


def _sma(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    if n <= 0 or len(xs) < n:
        return out
    run = sum(xs[:n])
    out[n - 1] = run / n
    for i in range(n, len(xs)):
        run += xs[i] - xs[i - n]
        out[i] = run / n
    return out


def signal_series(prices: list[float], kind: str, lookback: int) -> list[int]:
    """봉마다 −1 · 0 · +1. **그 봉 종가까지의 정보만** 쓴다.

    0 은 「아직 못 정한다」이지 「중립을 취한다」가 아니다 — 워밍업 구간이다.
    """
    n = len(prices)
    out = [0] * n
    if kind == "tsmom":
        for i in range(lookback, n):
            d = prices[i] - prices[i - lookback]
            out[i] = 1 if d > 0 else (-1 if d < 0 else 0)
    elif kind == "macross":
        short = max(2, lookback // MACROSS_RATIO)
        ms, ml = _sma(prices, short), _sma(prices, lookback)
        for i in range(n):
            a, b = ms[i], ml[i]
            if a is None or b is None:
                continue
            out[i] = 1 if a > b else (-1 if a < b else 0)
    elif kind == "donchian":
        # 최고를 뚫으면 +1, 최저를 뚫으면 −1, 사이에서는 **직전 방향 유지**.
        # 그 «유지» 가 브레이크아웃의 정의다 — 안 하면 채널 안에서 신호가 꺼져
        # 추세를 타는 도중에 나가게 된다.
        held = 0
        for i in range(n):
            if i < lookback:
                continue
            win = prices[i - lookback:i]          # **오늘을 뺀** 과거 창
            if prices[i] >= max(win):
                held = 1
            elif prices[i] <= min(win):
                held = -1
            out[i] = held
    else:
        raise CtaError(f"모르는 신호예요: {kind!r} (tsmom·macross·donchian)")
    return out


def realized_vol(prices: list[float], window: int) -> list[float | None]:
    """최근 `window` 일 조정가 **차분**의 표준편차(가격포인트). 그 봉까지만 쓴다."""
    n = len(prices)
    out: list[float | None] = [None] * n
    d = [None] + [prices[i] - prices[i - 1] for i in range(1, n)]
    for i in range(n):
        seg = [x for x in d[max(1, i - window + 1):i + 1] if x is not None]
        out[i] = st.pstdev(seg) if len(seg) >= max(5, window // 2) else None
    return out


def simulate(
    dates: list[str],
    prices: list[float],
    *,
    signal: str = "tsmom",
    lookback: int = 60,
    vol_window: int = 60,
    target_vol_krw: float = 1_000_000.0,
    cost_ticks: float = COST_TICKS,
    roll_days: set[str] | None = None,
    max_notional: float | None = None,
) -> dict:
    """한 선물의 CTA — `{points, summary}`.

    `points[i]` 는 `mrbacktest.simulate` 와 **같은 어휘**다(`dailyPnl`·`barCost`·
    `position`) — `mrmetrics.score` 와 오늘 만든 채점·격자·PBO 도구가 그대로 붙는다.

    ## 회계

        손익_t = 방향_{t−1} × 액면_{t−1}/100 × (P_t − P_{t−1})
        비용   = |액면_t·방향_t − 액면_{t−1}·방향_{t−1}| /100 × 틱 × 비용틱수
                 + (보유 중 롤일이면) 액면/100 × 틱 × 1   ← 왕복 1틱

    비용을 **액면 변화**에 물리는 것이 요점이다. 변동성 목표는 방향이 안 바뀌어도
    크기를 조금씩 바꾸므로, 방향 전환에만 비용을 물리면 그 재조정이 공짜가 된다.
    """
    if len(dates) != len(prices):
        raise CtaError("날짜와 가격의 길이가 달라요")
    if lookback < 2 or vol_window < 5:
        raise CtaError(f"창이 너무 짧아요 (룩백 {lookback} · 변동성 {vol_window})")
    n = len(dates)
    sig = signal_series(prices, signal, lookback)
    vol = realized_vol(prices, vol_window)
    rolls = roll_days or set()

    pos_notional = [0.0] * n          # 부호 있는 액면 — 이게 실제 포지션이다
    for i in range(n):
        v = vol[i]
        if sig[i] == 0 or v is None or v <= 0:
            continue
        size = target_vol_krw / (v / 100.0)
        if max_notional is not None:
            size = min(size, max_notional)
        pos_notional[i] = sig[i] * size

    points = []
    trades: list[dict] = []
    open_from: str | None = None
    open_dir = 0
    open_pnl = 0.0
    for i in range(n):
        prev = pos_notional[i - 1] if i > 0 else 0.0
        pnl = 0.0
        if i > 0 and prev != 0.0:
            pnl = prev / 100.0 * (prices[i] - prices[i - 1])
        # 비용 — 액면 변화 + 보유 중 롤
        turn = abs(pos_notional[i] - prev)
        cost = -turn / 100.0 * TICK * cost_ticks
        if prev != 0.0 and dates[i] in rolls:
            cost -= abs(prev) / 100.0 * TICK * 1.0
        points.append({
            "t": dates[i], "position": pos_notional[i],
            "dailyPnl": pnl + cost, "barCost": -cost,
            "signal": sig[i], "vol": vol[i],
        })
        # 거래 = 방향이 유지되는 구간. 승률·손익비가 그 단위로 서야 읽힌다.
        d = 0 if pos_notional[i] == 0 else (1 if pos_notional[i] > 0 else -1)
        if d != open_dir:
            if open_dir != 0 and open_from is not None:
                trades.append({"entryDate": open_from, "exitDate": dates[i],
                               "direction": open_dir, "pnl": open_pnl})
            open_dir, open_from, open_pnl = d, dates[i], 0.0
        open_pnl += pnl + cost
    if open_dir != 0 and open_from is not None:
        trades.append({"entryDate": open_from, "exitDate": dates[-1],
                       "direction": open_dir, "pnl": open_pnl})

    daily = [p["dailyPnl"] for p in points]
    total = sum(daily)
    peak = run = 0.0
    mdd = 0.0
    for x in daily:
        run += x
        peak = max(peak, run)
        mdd = max(mdd, peak - run)
    live = sum(1 for p in points if p["position"] != 0)
    return {
        "points": points,
        "trades": trades,
        "summary": {
            "totalPnl": total, "maxDrawdown": mdd,
            "numTrades": len(trades),
            "exposure": live / n if n else 0.0,
            "avgNotional": (st.fmean([abs(p["position"]) for p in points if p["position"]])
                            if live else 0.0),
            "cost": sum(p["barCost"] for p in points),
            "flips": sum(1 for i in range(1, n)
                         if (points[i]["signal"] or 0) * (points[i - 1]["signal"] or 0) < 0),
        },
    }


def combine(runs: list[dict], dates: list[str]) -> dict:
    """여러 선물의 합 — 날짜로 포갠다.

    **더한 뒤에 채점한다**(오늘 통합 장부에서 정한 그 규율) — Calmar·낙폭이
    비선형이라 계약별 값의 평균이 북의 값이 아니다.
    """
    at = {t: i for i, t in enumerate(dates)}
    daily = [0.0] * len(dates)
    cost = [0.0] * len(dates)
    for r in runs:
        for p in r["points"]:
            i = at.get(p["t"])
            if i is not None:
                daily[i] += p["dailyPnl"]
                cost[i] += p["barCost"]
    return {"points": [{"t": dates[i], "dailyPnl": daily[i], "barCost": cost[i]}
                       for i in range(len(dates))],
            "trades": [t for r in runs for t in r["trades"]]}


# ── 업계 문헌에 맞춘 개선 셋 [OWNER 2026-09-07 — "일단 다 고쳐봐"] ──────────
#
# 처음 판(위)은 교과서 최소판이었다. 세 자리가 실제 CTA 와 달랐고, 그중 하나는
# 오류였다. 근거는 전부 공개 문헌이다:
#
#   ① 포트폴리오 수준 변동성 목표   AQR (Hurst-Ooi-Pedersen, 2017)
#   ② 연속 신호 강도(TREND 규칙)     Baltas-Kosowski (2013)
#   ③ 상관이 낮게 속도 고르기        Man AHL (Need for Speed)
#
# ⚠ **Yang-Zhang 변동성 추정량은 못 쓴다**(회전 −17%). 고가·저가가 필요한데
# 이 데스크의 선물 계열은 종가뿐이다(`FuturesSeries` = dates·implied·price_adj·
# price_ctr). 막힌 길이라 적어 둔다.


def trend_tstat(prices: list[float], lookback: int) -> list[float | None]:
    """추세의 **통계적 강도** — 창 안에서 가격을 시간에 회귀한 기울기의 t 값.

    Baltas-Kosowski 의 「TREND」 규칙이 이것이다. 이진 부호(±1)를 t 값으로
    바꾸면 **회전이 24% 줄고** 성과 저하는 유의하지 않다는 것이 그 논문의 결과다.

    ## 왜 이 데스크에 특히 맞나 [OWNER 2026-09-07]

    쓰임새가 「손익을 내는 전략」이 아니라 **「트레이더의 확신을 돕는 도구」**로
    바뀌었다. 확신 도구가 필요한 것은 «켜짐/꺼짐» 이 아니라 **«얼마나 강한가»**다.
    이진 부호는 그 질문에 답할 수 없다.

    회귀는 `p = a + b·t` 이고 `t값 = b / SE(b)`. 창 밖은 안 본다(룩어헤드 없음).
    """
    n = len(prices)
    out: list[float | None] = [None] * n
    for i in range(lookback - 1, n):
        y = prices[i - lookback + 1:i + 1]
        m = len(y)
        xs = list(range(m))
        mx = (m - 1) / 2
        my = sum(y) / m
        sxx = sum((x - mx) ** 2 for x in xs)
        if sxx <= 0:
            continue
        b = sum((xs[k] - mx) * (y[k] - my) for k in range(m)) / sxx
        a = my - b * mx
        resid = [y[k] - (a + b * xs[k]) for k in range(m)]
        dof = m - 2
        if dof <= 0:
            continue
        s2 = sum(r * r for r in resid) / dof
        se = math.sqrt(s2 / sxx) if s2 > 0 else 0.0
        out[i] = (b / se) if se > 0 else 0.0
    return out


#: t 값을 −1~+1 로 누르는 포화점. 이보다 강한 추세는 더 크게 안 간다 —
#: 「강하다」와 「아주 강하다」를 크기로 구분하면 꼬리에서 위험이 폭발한다.
#: 값 자체는 재량이라 격자의 손잡이로 두지 않고 **고정**한다(자유도 절약).
TSTAT_CAP = 4.0


def signal_continuous(prices: list[float], kind: str, lookback: int) -> list[float]:
    """−1~+1 **연속** 신호. 이진 `signal_series` 의 자리를 대신한다.

    `kind` 는 방향을 정하고(위 세 규칙 그대로), **크기는 t 값이 정한다.** 방향과
    강도를 갈라 두는 이유는 둘이 다른 질문이기 때문이다 — 「어느 쪽인가」는
    규칙마다 다르고, 「얼마나 확실한가」는 규칙과 무관한 추세의 성질이다.
    """
    d = signal_series(prices, kind, lookback)
    ts = trend_tstat(prices, lookback)
    out = []
    for i in range(len(prices)):
        t = ts[i]
        if d[i] == 0 or t is None:
            out.append(0.0)
            continue
        mag = min(abs(t) / TSTAT_CAP, 1.0)
        out.append(d[i] * mag)
    return out


def pick_speeds(prices: list[float], kind: str, candidates: list[int],
                *, max_corr: float = 0.35, want: int = 5) -> list[int]:
    """**상관이 낮은 속도만** 고른다 — Man AHL 의 그 규율.

    AHL 은 다섯 속도를 「잡으려는 추세의 범위를 덮으면서 **모델 간 상관을
    최소화하도록**」 고르고, 최속·최저속 상관이 0.17 이다. 실측(2026-09-07)
    내 룩백 20/40/60/120/250 은 양 끝이 0.10 인데 **가운데가 0.53~0.68 로
    겹쳤다** — 다섯을 섞어도 사실상 둘 반쯤이었고, 섞기가 안 먹힌 이유일 수 있다.

    빠른 것부터 담되 **이미 담긴 것과 `max_corr` 를 넘으면 버린다.** 빠른 쪽을
    먼저 담는 이유는 AHL 의 「방어적 용도에는 빠른 속도가 낫다」이다(느린 쪽이
    샤프는 높지만 빠른 쪽이 왜도가 좋다 — 손실을 빨리 자른다).
    """
    sigs = {lb: signal_continuous(prices, kind, lb) for lb in candidates}

    def corr(a: list[float], b: list[float]) -> float:
        pair = [(x, y) for x, y in zip(a, b) if x != 0.0 or y != 0.0]
        if len(pair) < 30:
            return 1.0
        xs = [p[0] for p in pair]
        ys = [p[1] for p in pair]
        mx, my = st.fmean(xs), st.fmean(ys)
        sx, sy = st.pstdev(xs), st.pstdev(ys)
        if sx == 0 or sy == 0:
            return 1.0
        return sum((x - mx) * (y - my) for x, y in pair) / len(pair) / (sx * sy)

    chosen: list[int] = []
    for lb in sorted(candidates):
        if len(chosen) >= want:
            break
        if all(abs(corr(sigs[lb], sigs[c])) <= max_corr for c in chosen):
            chosen.append(lb)
    return chosen


def book_simulate(
    instruments: dict[str, tuple[list[str], list[float]]],
    *,
    signal: str = "macross",
    lookbacks: tuple[int, ...] = (20, 250),
    vol_window: int = 60,
    target_book_vol_krw: float = 1_000_000.0,
    book_vol_window: int = 120,
    cost_ticks: float = COST_TICKS,
    roll_days: set[str] | None = None,
    continuous: bool = True,
    external_signals: dict[str, dict[str, float]] | None = None,
) -> dict:
    """**포트폴리오 수준** 변동성 목표로 도는 북 — AQR 의 그 규율.

    ## `external_signals` — 가격이 아닌 신호를 같은 배관에 태운다

    주면 `signal`·`lookbacks`·`continuous` 를 **대신한다**(가격에서 신호를 안
    만든다). 값은 계약별 `{날짜: −1~+1}` 이고 없는 날은 0(포지션 없음)이다.
    크기 결정·비용·회계는 한 글자도 안 바뀐다 — **바뀌는 것은 신호 하나뿐**
    이어야 매크로 모멘텀과 추세추종을 나란히 놓은 값이 뜻을 갖는다.

    ## 왜 계약당 목표가 오류인가

    처음 판은 계약마다 「하루 σ = 목표」로 맞췄다. 그런데 **KTB3·KTB10 일간 변화
    상관이 0.889**(실측 2026-09-07)라, 둘이 같은 방향일 때 북의 위험이 거의 두
    배가 되고 갈릴 때 반으로 준다 — **목표 위험이 실제로 안 지켜진다.** AQR 은
    포트폴리오 전체의 사전 변동성을 목표에 맞춘다(그 논문은 연 10%).

    ## 어떻게 맞추나

        1. 계약마다 **단위 위험**으로 정규화한다      u_i = 신호_i / σ_i
        2. 룩백들을 평균해 한 계열로 만든다            (등가중 — AQR·AHL 둘 다)
        3. 그 «미조정 북» 의 **과거** 변동성을 재고     ← 오늘까지만 본다
        4. 목표/그 변동성 으로 북 전체를 곱한다

    3에서 **과거만 보는 것**이 핵심이다. 북의 변동성은 상관을 이미 품고 있으므로
    공분산 행렬을 따로 추정할 필요가 없다 — 그리고 그쪽이 추정 오차도 작다.
    """
    dates = sorted(set().union(*[set(d) for d, _p in instruments.values()]))
    at = {t: i for i, t in enumerate(dates)}
    n = len(dates)
    rolls = roll_days or set()

    # 1·2 — 계약마다 단위 위험, 룩백 등가중 평균
    unit = {k: [0.0] * n for k in instruments}
    for key, (d, px) in instruments.items():
        vol = realized_vol(px, vol_window)
        ext = external_signals.get(key) if external_signals else None
        if ext is None and external_signals is not None:
            raise CtaError(f"외부 신호에 {key!r} 가 없어요 — 빈 계약을 조용히 0 으로 두지 않아요")
        sigs = None if ext is not None else [
            (signal_continuous(px, signal, lb) if continuous
             else [float(x) for x in signal_series(px, signal, lb)])
            for lb in lookbacks]
        for j, day in enumerate(d):
            v = vol[j]
            if v is None or v <= 0:
                continue
            s = ext.get(day, 0.0) if ext is not None else st.fmean([sg[j] for sg in sigs])
            unit[key][at[day]] = s / v          # 단위: 신호 / 가격포인트

    # 3 — 미조정 북의 «과거» 변동성. 1원 곱으로 도는 가상 북의 일별 손익.
    raw = [0.0] * n
    for key, (d, px) in instruments.items():
        p = {day: px[j] for j, day in enumerate(d)}
        for i in range(1, n):
            t0, t1 = dates[i - 1], dates[i]
            if t0 in p and t1 in p:
                raw[i] += unit[key][i - 1] * (p[t1] - p[t0])
    scale = [0.0] * n
    for i in range(n):
        seg = raw[max(1, i - book_vol_window + 1):i + 1]
        seg = [x for x in seg if x != 0.0]
        if len(seg) >= max(20, book_vol_window // 3):
            sd = st.pstdev(seg)
            if sd > 0:
                scale[i] = target_book_vol_krw / sd

    # 4 — 북 전체를 곱하고 회계
    pos = {k: [0.0] * n for k in instruments}
    for key in instruments:
        for i in range(n):
            pos[key][i] = unit[key][i] * scale[i] * 100.0   # 부호 있는 «액면»

    points = []
    for i in range(n):
        pnl = cost = 0.0
        for key, (d, px) in instruments.items():
            p = {day: px[j] for j, day in enumerate(d)}
            t0, t1 = (dates[i - 1] if i else None), dates[i]
            prev = pos[key][i - 1] if i else 0.0
            if i and t0 in p and t1 in p and prev != 0.0:
                pnl += prev / 100.0 * (p[t1] - p[t0])
            cost -= abs(pos[key][i] - prev) / 100.0 * TICK * cost_ticks
            if prev != 0.0 and t1 in rolls:
                cost -= abs(prev) / 100.0 * TICK * 1.0
        points.append({"t": dates[i], "dailyPnl": pnl + cost, "barCost": -cost,
                       "position": sum(pos[k][i] for k in instruments)})
    return {"points": points, "trades": [], "dates": dates,
            "scale": scale, "pos": pos}
