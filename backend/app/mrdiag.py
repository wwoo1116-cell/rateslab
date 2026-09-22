# -*- coding: utf-8 -*-
"""전략 실험 창의 **진단** — 「이 성과가 어디서 왔는가」 를 화면이 스스로 말하게 하는 넷
[OWNER 2026-08-28 — "저렇게 단순한 전략이 승률이 이렇게 높을 수 있다는게 이해가
잘 안간다" · "과거에 Overfitting 된거 아닌가"].

의심 둘 다 화면 밖에서만 답할 수 있었다. 그래서 성과 카드가 승률 93% 를 내걸고,
그것이 진입의 공로인지 청산 규칙의 산물인지, 최근에도 유지되는지를 말하지 않았다.
이 모듈이 그 넷을 잰다.

  `exit_tally`    청산 사유별 건수·승률·평균. **높은 승률의 정체가 여기서 갈린다** —
                  익절만 세면 90%대가 나오고 손절·타임스탑을 같이 세면 내려간다.
  `payoff`        손익비와 프로핏팩터. 승률만으로는 「작게 여러 번 이기고 크게
                  가끔 지는」 모양인지 알 수 없다.
  `forward_edge`  청산 규칙을 **떼고** 신호일의 고정 보유 수익을 잰다. 승률이
                  청산이 만든 것이라면 여기서 사라진다. 실측(9계열·H=10)에서
                  신호일 +2.596bp·적중 76% 대 비신호일 −0.130bp·적중 50% 였다 —
                  즉 진입이 실제로 일을 한다.
  `period_split`  구간을 갈라 같은 규칙을 잰다. 과거적합이면 최근이 무너지고,
                  엣지 소멸이면 크기가 단조로 줄어든다. **모양이 다르다.**

산술은 전부 순수 함수다. 돈 단위(₩)를 bp 로 되돌릴 때는 명목(₩/bp)으로 나눈다 —
계열마다 명목이 같아도 bp 로 적어야 만기 간 비교가 선다.
"""
from __future__ import annotations

import math
import statistics as st
from typing import Any

from .mrbacktest import _entry_signal

FWD_BARS = 10
"""고정 보유 기간(영업일). 10 은 이 전략의 실측 중앙 보유기간 언저리이고,
그보다 짧으면 되돌림이 안 끝나고 길면 신호와 무관한 구간이 섞인다."""

PERIODS = 3
"""구간 분할 수. 셋이면 각 구간이 3~4년이라 방향을 볼 수 있고, 넷 이상이면
구간당 거래가 한 자리로 떨어져 SR 이 잡음이 된다."""


def _bp(pnl: float, notional: float) -> float:
    return pnl / notional if notional else 0.0


def exit_tally(trades: list[dict], notional: float) -> list[dict[str, Any]]:
    """청산 사유별 집계 — **사유 순서를 고정**한다.

    빈도순으로 정렬하면 실행마다 줄 순서가 바뀌어 눈이 비교를 못 한다. 순서는
    **청산 → 손절 → 역신호 → 타임스탑 → 미청산**(아래 order 그대로 — 종전
    독스트링은 「손절 > 청산」이라 적어 코드와 모순이었다. 그건 엔진의 판정
    우선순위지 이 표의 줄 순서가 아니다; 2026-09-02 적대 대사가 잡음). 0 건인
    사유는 빼지 않고 **아예 안 만든다** — 없는 일을 0 으로 적으면 표가
    길어지기만 한다.
    """
    order = ("exit", "stop", "reverse", "time", "open")
    out: list[dict[str, Any]] = []
    for why in order:
        g = [t for t in trades if t.get("exitReason") == why]
        if not g:
            continue
        bps = [_bp(t["pnl"], notional) for t in g]
        wins = sum(1 for b in bps if b > 0)
        out.append({
            "why": why, "n": len(g), "wins": wins, "winRate": wins / len(g),
            "avgBp": sum(bps) / len(bps), "sumBp": sum(bps),
            "avgBars": sum(t["bars"] for t in g) / len(g),
        })
    return out


def payoff(trades: list[dict], notional: float) -> dict[str, Any] | None:
    """손익비와 프로핏팩터 — 승률 옆에 없으면 승률이 거짓말을 한다.

    승률 90% 는 「작게 아홉 번 이기고 크게 한 번 진다」와 구별되지 않는다. 그
    구별을 하는 수가 이 둘이다. 이긴 거래나 진 거래가 아예 없으면 정의되지
    않으므로 `None` 을 준다 — 0 이나 ∞ 로 채우지 않는다.
    """
    w = [_bp(t["pnl"], notional) for t in trades if t["pnl"] > 0]
    l = [_bp(t["pnl"], notional) for t in trades if t["pnl"] <= 0]
    if not w or not l:
        return None
    aw, al = sum(w) / len(w), sum(l) / len(l)
    return {
        "wins": len(w), "losses": len(l),
        "avgWinBp": aw, "avgLossBp": al,
        "payoff": aw / abs(al) if al else None,
        "profitFactor": sum(w) / abs(sum(l)) if sum(l) else None,
    }


def forward_edge(values: list[float], z: list[float | None], *,
                 entry_z: float, allow_dirs: tuple[int, ...],
                 entry_mode: str = "level", horizon: int = FWD_BARS) -> dict[str, Any]:
    """청산 규칙을 **떼고** 신호일의 고정 보유 수익을 잰다.

    이 함수가 답하는 질문: 「승률이 높은 것은 진입 덕인가, 청산 규칙 덕인가.」
    청산이 만든 것이라면 고정 보유로 바꿨을 때 신호일과 비신호일이 안 갈린다.

    **실행 가능한 방향만 센다.** BSS 는 한쪽뿐이라 `z ≥ +진입σ` 인 날만 신호다
    (규약이 `IRS − 국고` 로 뒤집힌 2026-09-22 부터 — 종전에는 `z ≤ −진입σ` 였다). 방향을 빼먹고 `|z| ≥ 진입σ` 로 세면 못 하는 거래의 수익이 섞여
    답이 뒤집힌다(실측 2026-08-28: 그렇게 세면 신호일 −0.374bp·적중 47% 로
    나왔고, 방향을 넣으면 +1.842bp·적중 72% 였다).

    신호 판정은 엔진의 `_entry_signal` 을 그대로 부른다 — 진입 규칙이 둘이라
    여기서 다시 쓰면 두 벌이 된다.

    비신호일의 방향은 실행 가능한 방향이 하나면 그것을 쓰고, 둘이면 그날 z 의
    역방향을 쓴다(문턱이 0 이었다면 갔을 쪽).
    """
    n = len(values)
    one = allow_dirs[0] if len(allow_dirs) == 1 else None
    on: list[float] = []
    off: list[float] = []
    for i in range(n - horizon):
        if z[i] is None:
            continue
        want = _entry_signal(z, i, entry_z, entry_mode)
        move = values[i + horizon] - values[i]
        if want is not None and want in allow_dirs:
            on.append(want * move)
        else:
            d = one if one is not None else (-1 if z[i] > 0 else 1)
            off.append(d * move)

    def agg(g: list[float]) -> dict[str, Any] | None:
        if not g:
            return None
        return {"n": len(g), "meanBp": sum(g) / len(g),
                "hitRate": sum(1 for x in g if x > 0) / len(g),
                "medianBp": st.median(g)}

    return {"bars": horizon, "onSignal": agg(on), "offSignal": agg(off)}


def period_split(dates: list[str], points: list[dict], *,
                 parts: int = PERIODS) -> list[dict[str, Any]]:
    """구간을 갈라 같은 규칙을 잰다 — **과거적합과 엣지 소멸은 모양이 다르다**.

    과거적합이면 최근 구간이 갑자기 무너지고 부호가 바뀐다. 엣지 소멸이면 부호가
    유지된 채 크기만 단조로 줄어든다. 화면이 구간을 안 보여 주면 둘을 구별할 수
    없고, 전체 기간 SR 하나만 남는다.

    구간은 **봉 수로** 균등 분할한다(날짜로 나누면 자료가 빈 해에 구간이 짧아진다).
    """
    n = len(points)
    if n < parts * 20:
        return []
    out: list[dict[str, Any]] = []
    edges = [round(n * k / parts) for k in range(parts + 1)]
    for k in range(parts):
        a, b = edges[k], edges[k + 1]
        daily = [p["dailyPnl"] for p in points[a:b]]
        # ⚠ `summarize()` 를 쓰면 안 된다 — 그쪽의 총손익·낙폭은 **전 구간 누적**
        # (`cumulativePnl`)에서 읽으므로, 조각에 그대로 걸면 앞 구간의 누적이
        # 이 구간의 손익으로 잡힌다. 조각은 조각의 일별 손익에서 다시 센다.
        cum = 0.0
        peak = -math.inf
        mdd = 0.0
        for x in daily:
            cum += x
            peak = max(peak, cum)
            mdd = max(mdd, peak - cum)
        sd = st.pstdev(daily) if len(daily) >= 2 else 0.0
        out.append({
            "from": dates[a], "to": dates[b - 1], "days": b - a,
            "totalPnl": sum(daily), "maxDrawdown": mdd,
            "sharpe": (sum(daily) / len(daily)) / sd * math.sqrt(252) if sd else None,
        })
    return out
