# -*- coding: utf-8 -*-
"""수급 신호 실험 — **오너가 직접 재 보는 자리** [OWNER 2026-10-20].

> "이거 내가 사용할 수 있어야한다고,, Backtest에서 처럼"

2026-10-20 에 「수급으로 금리 방향을 맞추나」를 전수로 재서 **KILL** 했다
(`docs/VERDICT_flow_direction_2026-10-20.md`). 그런데 그 검정은 전부 세션의
스크래치패드에서 돌았고 **증발했다** — 오너가 직접 만질 길이 없었고, 다음 사람이
같은 탐색을 손으로 다시 돌릴 길도 없었다. 이 모듈이 그 산술을 제품으로 옮긴다.

## ★이 모듈이 지는 제일 중요한 규칙 — **결과 옆에 우연을 같이 적는다**

오늘의 교훈이 이것 하나다. 신호 하나를 재서 「Calmar 0.53」을 보면 사람은 그것을
실력으로 읽는다. 그런데 **같은 크기의 탐색을 가짜 자료에 돌리면 우연의 1등이
0.53~0.91 을 낸다**. 그래서 이 모듈은 수를 혼자 내보내지 않는다:

  ① `shuffle` — **그 칸** 의 우연 분포. 신호를 수익에 대해 원형 이동시켜
     자기상관은 두고 **맞물림만** 깬다. p 값이 그 칸의 정직한 세기다.
  ② `searchCeiling` — **탐색** 의 우연 천장. 창을 바꿔 가며 고르는 행위 자체가
     탐색이므로, 격자 전체를 가짜 자료에 돌린 1등 분포를 같이 싣는다.

②가 없으면 화면이 ①만 보여 주고, 사람은 손으로 스무 칸을 돌린 뒤 제일 좋은 것을
믿게 된다. **내가 오늘 정확히 그렇게 한 번 틀렸다**(「p 0.025 로 살았다」 → 탐색
전체로 재니 우연의 중위보다 못했다).

## 달력 규약 — `VERDICT` §0 과 **같은 것**

  축      수급 영업일 ∩ 금리 영업일
  지연    **1일**. t 까지의 흐름으로 만든 신호 → t+1 종가 진입 → 손익 y[t+2]−y[t+1]
          (현물 수급은 하루 늦게 들어온다 — asof 10-19 를 10-20 에 본다)
  창      **봉 수**(영업일)이지 달력일이 아니다
  비용    거래 한 번 `COST_BP`(0.5bp) — 포지션이 바뀐 봉에만
  채점    **Calmar** = 연환산 순손익 / 최대낙폭

⚠산술은 **DB 를 모른다** — `run()` 은 계열을 받고, 자료를 읽는 것은 `board()` 다
(`flow.py` 의 그 규율). 그래야 시험이 SQL 없이 돈다.
"""
from __future__ import annotations

import random
from typing import Any

from . import flow, mrplan, mrseries

#: 비용은 **한 곳에서** 온다 — 계획면이 정본이다(`paper.py` 머리의 그 규율).
COST_BP = mrplan.COST_BP
#: 1bp 의 돈. 수는 여기에 비례하므로 눈금일 뿐이다.
DV01 = 10_000_000.0
#: 공표 지연(영업일). 자료 사실이지 손잡이가 아니다 — 화면에 안 내놓는다.
LAG = 1
#: 가짜 판을 돌릴 때 **가장자리 정렬**을 피한다. 너무 작게 돌리면 원래 맞물림이
#: 거의 남아서 「우연」이 우연이 아니게 된다.
MIN_SHIFT = 60

#: 실험할 수 있는 표적 금리.
TARGETS = ("3Y", "5Y", "10Y", "20Y", "30Y")
#: 창 쌍·보유기간의 **격자** — 탐색 천장을 재는 모집단이다. 화면이 고르는 값도
#: 이 안에서만 받는다(격자 밖을 고르면 천장과 견줄 수 없다).
SHORTS = (5, 10, 15, 20, 25, 30)
LONGS = (40, 50, 60, 70, 90, 120)
HOLDS = (1, 5, 10, 20, 40)


class LabError(RuntimeError):
    """이 실험을 못 돌린다."""


# ── 순수 산술 (DB 를 모른다) ────────────────────────────────────────────────

def positions(sig: list[float | None], hold: int) -> list[int]:
    """신호 부호 → 포지션. **한 번 들면 `hold` 봉은 안 바꾼다**.

    +1 은 듀레이션 롱(금리가 내리면 번다). 신호가 아직 안 선 봉은 0 이다.
    """
    out: list[int] = []
    cur, since = 0, 0
    for v in sig:
        want = 0 if v is None else (1 if v > 0 else -1)
        if cur == 0 or (since >= hold and want != cur and want != 0):
            cur, since = want, 0
        out.append(cur)
        since += 1
    return out


def score(pos: list[int], dy: list[float], *, cost_bp: float = COST_BP,
          dv01: float = DV01) -> dict[str, Any]:
    """손익·낙폭·Calmar. `dy` 는 **그 봉에 실현되는** 금리 변화(bp)다.

    포지션이 바뀐 봉에 비용을 문다 — 첫 봉도 드는 거래라 센다.
    """
    daily: list[float] = []
    prev = 0
    for p, d in zip(pos, dy):
        v = -p * d * dv01
        if p != prev:
            v -= cost_bp * dv01
        daily.append(v)
        prev = p
    cum, run, peak, mdd = [], 0.0, 0.0, 0.0
    for v in daily:
        run += v
        peak = max(peak, run)
        mdd = max(mdd, peak - run)
        cum.append(run)
    n = len(daily)
    tot = cum[-1] if cum else 0.0
    ann = tot * 252.0 / n if n else 0.0
    trades = sum(1 for i, p in enumerate(pos) if p != (pos[i - 1] if i else 0))
    return {
        "total": tot, "mdd": mdd, "calmar": (ann / mdd) if mdd > 0 else None,
        "trades": trades, "bars": n, "cum": cum, "daily": daily,
    }


def shift(xs: list[float], k: int) -> list[float]:
    """원형 이동 — 자기상관은 두고 **맞물림만** 깬다."""
    n = len(xs)
    k %= n or 1
    return xs[-k:] + xs[:-k] if k else list(xs)


def null_calmars(pos: list[int], dy: list[float], draws: int,
                 rng: random.Random, **kw: Any) -> list[float]:
    """**그 칸**의 우연 분포 — 수익을 돌려 가며 같은 포지션을 채점한다."""
    n = len(dy)
    out: list[float] = []
    for _ in range(draws):
        k = rng.randint(MIN_SHIFT, max(MIN_SHIFT + 1, n - MIN_SHIFT))
        c = score(pos, shift(dy, k), **kw)["calmar"]
        if c is not None:
            out.append(c)
    return sorted(out)


def pct_rank(xs: list[float], v: float) -> float:
    """정렬된 `xs` 에서 `v` 이상인 몫 — 곧 p 값이다."""
    return (sum(1 for x in xs if x >= v) / len(xs)) if xs else 1.0


def by_year(dates: list[str], daily: list[float]) -> list[dict[str, Any]]:
    """연도별 순손익 — 한 해가 다 먹고 있지 않은지 보는 자리."""
    agg: dict[str, float] = {}
    for d, v in zip(dates, daily):
        agg[d[:4]] = agg.get(d[:4], 0.0) + v
    tot = sum(agg.values())
    return [{"year": y, "pnl": v,
             "share": (v / tot) if tot else None}
            for y, v in sorted(agg.items())]


# ── 자료를 읽는 자리 ────────────────────────────────────────────────────────

def _align(tenor: str, target: str) -> tuple[list[str], dict[str, list[int]], list[float]]:
    """(날짜, 주체별 일별 순매수, **그 봉에 실현되는** 금리변화 bp).

    ★공표 지연을 **여기서** 넣는다. 신호는 `k` 봉까지의 흐름으로 서고, 돈은
    `k+LAG` 종가에 들어가 `k+1+LAG` 종가에 나온다. 한 곳에서 맞춰 두면 호출부가
    실수로 엿보기를 만들 수 없다 — 2026-10-20 에 백테스트가 정확히 그걸 했다.
    """
    d = flow.load()
    if tenor not in d.cash:
        raise LabError(f"모르는 만기물이에요: {tenor}")
    if target not in TARGETS:
        raise LabError(f"모르는 표적이에요: {target} ({'·'.join(TARGETS)})")
    fdates, cols = d.cash[tenor]
    y = mrseries.bundle()["ktb"].get(target)
    if not y:
        raise LabError(f"{target} 국고 금리를 못 읽었어요.")
    common = [t for t in fdates if t in y]
    n = len(common) - 1 - LAG
    if n < 200:
        raise LabError(f"겹치는 날이 너무 적어요: {max(n, 0)}봉")
    at = {t: i for i, t in enumerate(fdates)}
    dy = [(y[common[k + 1 + LAG]] - y[common[k + LAG]]) * 100.0 for k in range(n)]
    cut = {c: [cols[c][at[common[k]]] for k in range(n)] for c, _ in flow.CASH_COLS}
    return common[:n], cut, dy


def _sig(v: list[int], short: int, long: int) -> list[float | None]:
    """짧은 창 − 긴 창. 둘 다 서야 값이 선다."""
    a, b = flow.moving_average(v, short), flow.moving_average(v, long)
    return [None if (x is None or z is None) else (x - z) for x, z in zip(a, b)]


def board(subject: str, tenor: str = "30Y", target: str = "30Y",
          short: int = 20, long: int = 60, hold: int = 20,
          draws: int = 300, seed: int = 11) -> dict[str, Any]:
    """실험 한 판 — **고른 칸 + 그 칸의 우연 + 탐색의 우연**.

    셋을 같이 내보내는 것이 이 모듈의 존재 이유다(머리 §결과 옆에 우연을).
    """
    keys = dict(flow.CASH_COLS)
    if subject not in keys:
        raise LabError(f"모르는 주체예요: {subject}")
    if short not in SHORTS or long not in LONGS or hold not in HOLDS:
        raise LabError("격자 밖의 창이에요 — 천장과 견줄 수 없어요.")
    if short >= long:
        raise LabError(f"짧은 창이 긴 창보다 길어요: {short} ≥ {long}")

    dates, cols, dy = _align(tenor, target)
    rng = random.Random(seed)
    pos = positions(_sig(cols[subject], short, long), hold)
    got = score(pos, dy)
    nulls = null_calmars(pos, dy, draws, rng)
    cal = got["calmar"]

    # ── 탐색 천장 — 격자 전체를 **같은 가짜 판**에 돌린 1등 분포 ──────────
    #
    # ★이것이 핵심이다. 사람이 창을 바꿔 가며 고르면 그건 탐색이고, 탐색의
    # 우연은 한 칸의 우연보다 **훨씬 세다**. 실측 2026-10-20: 한 칸 기준으로는
    # 「p 0.025 로 살았다」가 탐색 기준으로는 우연의 중위보다 못했다.
    grid = [(s, L, h) for s in SHORTS for L in LONGS for h in HOLDS if s < L]
    gpos = {(s, L, h): positions(_sig(cols[subject], s, L), h) for s, L, h in grid}
    ceil_rng = random.Random(seed + 1)
    ceiling: list[float] = []
    n = len(dy)
    for _ in range(max(draws // 6, 20)):
        k = ceil_rng.randint(MIN_SHIFT, max(MIN_SHIFT + 1, n - MIN_SHIFT))
        sd = shift(dy, k)
        best = None
        for p in gpos.values():
            c = score(p, sd)["calmar"]
            if c is not None and (best is None or c > best):
                best = c
        if best is not None:
            ceiling.append(best)
    ceiling.sort()

    def q(xs: list[float], p: float) -> float | None:
        return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None

    return {
        "subject": subject, "subjectLabel": keys[subject],
        "tenor": tenor, "tenorLabel": flow.CASH_TENOR_LABEL.get(tenor, tenor),
        "target": target, "short": short, "long": long, "hold": hold,
        "from": dates[0], "to": dates[-1],
        "costBp": COST_BP, "dv01": DV01, "lag": LAG,
        "dates": dates,
        "result": {k: got[k] for k in ("total", "mdd", "calmar", "trades", "bars")},
        "cum": got["cum"],
        "byYear": by_year(dates, got["daily"]),
        #: ① 그 칸의 우연
        "shuffle": {"draws": len(nulls), "median": q(nulls, 0.5),
                    "p95": q(nulls, 0.95), "p": pct_rank(nulls, cal) if cal is not None else None},
        #: ② 탐색의 우연 — 격자를 가짜 판에 돌린 1등
        "searchCeiling": {"cells": len(grid), "draws": len(ceiling),
                          "median": q(ceiling, 0.5), "p95": q(ceiling, 0.95),
                          "beat": (pct_rank(ceiling, cal) if cal is not None else None)},
        "grid": {"shorts": list(SHORTS), "longs": list(LONGS), "holds": list(HOLDS),
                 "targets": list(TARGETS)},
        "subjects": [{"key": c, "label": lab} for c, lab in flow.CASH_COLS],
        "tenors": [{"key": k, "label": flow.CASH_TENOR_LABEL[k]} for k in flow.CASH_TENORS],
        "basis": ("수급 신호를 그대로 포지션으로 세운 수예요 — 신호는 그날까지의 "
                  "흐름으로 서고, 돈은 다음 영업일 종가에 들어가요(현물 수급이 "
                  "하루 늦게 들어와서예요). 비용은 거래 한 번 "
                  f"{COST_BP}bp 예요."),
        #: ⚠화면이 평문으로 찍으므로 **마크다운을 쓰지 않는다** — 첫 판에서
        #: 별표가 그대로 보였다(`verdict().note` 에서 한 번 밟은 그 자리).
        "warn": ("창을 바꿔 가며 고르는 것은 그 자체가 탐색이에요 — 그때는 한 칸의 p 가 "
                 "아니라 아래 「탐색의 우연」과 견줘야 해요. 2026-10-20 판정에서 "
                 "이 가족은 그 천장을 못 넘었어요."),
    }
