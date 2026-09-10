# -*- coding: utf-8 -*-
r"""순환이동 무작위화 검정 — 게이트 셋째 [OWNER 2026-09-10].

## 왜 게이트에 들어왔나

DSR 의 허들은 **표본길이가 4분의 3을 정한다**(§16-1). 시행수를 1 로 두어 선택벌점을
완전히 없애도 연 SR 0.52 가 필요하고, 그 결과 SG CTA 지수의 실현 Sharpe 0.61 조차
9.40년으로는 통과하지 못한다. 즉 「미통과」가 전략이 아니라 **표본**에 대한 진술이
되어 버렸다.

이 검정은 그 자리를 메운다. 포지션 경로를 순환이동시켜 **시점 정합성만** 없애고
포지션 크기 분포·회전율·변동성 목표·거래비용 구조는 그대로 둔다. 그러면 귀무가설이
「이 북의 타이밍에는 정보가 없다」가 되고, **정규성·시행수·표본길이 어느 것도 안
쓴다.** 2026-09-10 실측에서 이 검정만이 두 계기를 갈랐다(IRS p 0.011 · 선물 0.061).

## 위약을 둘로 쪼갠다

경로를 통째로 밀면 방향 타이밍뿐 아니라 **변동성 타이밍**(위험이 클 때 작게 드는
것)까지 같이 죽는다. 그러면 위약이 실제보다 세져 전략이 쉽게 이긴다.

    P1 경로 전체 이동   |포지션|·부호를 같이 민다 → 방향 + 변동성 타이밍이 죽는다
    P2 부호만 이동      |포지션| 은 제자리, 부호만 민다 → **방향 타이밍만** 죽는다

**게이트가 읽는 것은 P2** 다. P1 은 그 위약이 얼마나 세게 잡았는지를 재는 대조군이다.

## 이동폭

최장 룩백보다 짧게 밀면 신호가 덜 끊긴다. 그래서 **양 끝에서 최장 룩백만큼을 뺀
전부**를 돈다. 순환이동은 군(群)이므로 «가능한 이동을 다 도는 것»이 이 검정의 정확한
형태이고 무작위 표본추출이 아니다. 음의 이동은 곧 n−k 이동이라 따로 세지 않는다.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

ANN = 252

#: 게이트 문턱 [OWNER 2026-09-10].
PLACEBO_PASS = 0.05

#: 이동폭의 하한은 호출부가 최장 룩백으로 준다. 간격은 이 값이다 — 촘촘할수록 p 의
#: 바닥(1/(이동수+1))이 낮아진다. 2026-09-10 에 5·10·25 로 흔들어 결론 불변을 확인.
SHIFT_STEP = 10


def _sr(x: np.ndarray) -> float:
    s = x.std(ddof=1)
    return float(x.mean() / s * math.sqrt(ANN)) if s > 0 else 0.0


def plumbing(dates: list[str], price: dict[str, dict[str, float]],
             rolls: set[str], ticks: float, tick_size: float) -> dict:
    """엔진 회계를 배열로 편다 — 위약을 수백 번 돌려야 해서.

    ⚠ 실제 포지션을 넣으면 엔진의 `dailyPnl` 과 **한 치도 안 달라야** 한다.
    그 등식을 시험이 잰다(`test_randomization`).
    """
    n = len(dates)
    dp = {}
    for k, p in price.items():
        a = np.zeros(n)
        for i in range(1, n):
            t0, t1 = dates[i - 1], dates[i]
            if t0 in p and t1 in p:
                a[i] = p[t1] - p[t0]
        dp[k] = a
    return {"dates": dates, "keys": list(price), "dp": dp, "n": n,
            "roll": np.array([1.0 if t in rolls else 0.0 for t in dates]),
            "unit": tick_size * ticks, "tick": tick_size}


def repnl(pl: dict, pos: dict[str, Any]) -> np.ndarray:
    """포지션 경로 하나로 일별 손익(비용 포함)을 낸다."""
    out = np.zeros(pl["n"])
    for k in pl["keys"]:
        a = np.asarray(pos[k], dtype=float)
        prev = np.concatenate(([0.0], a[:-1]))
        out += prev / 100.0 * pl["dp"][k]
        out -= np.abs(a - prev) / 100.0 * pl["unit"]
        out -= np.abs(prev) / 100.0 * pl["tick"] * pl["roll"]
    return out


def shifted(pos: dict[str, Any], k: int, *, sign_only: bool) -> dict:
    out = {}
    for key, v in pos.items():
        a = np.asarray(v, dtype=float)
        rolled = np.roll(a, k)
        out[key] = np.abs(a) * np.sign(rolled) if sign_only else rolled
    return out


def placebo(pl: dict, pos: dict[str, Any], *, shift_min: int,
            mask: np.ndarray | None = None, sign_only: bool = True,
            step: int = SHIFT_STEP) -> dict:
    """순환이동 위약의 p 값.

    `mask` 는 판정을 낼 창(다른 다리와 겹치는 구간 등)이다. 없으면 전 구간.
    돌려주는 `p` 는 (실제를 이긴 위약 + 1) / (이동수 + 1) 이고, 이 «+1» 은 무작위화
    검정의 관례다(실제 자신도 하나의 배치로 센다).
    """
    m = np.ones(pl["n"], dtype=bool) if mask is None else mask
    real = _sr(repnl(pl, pos)[m])
    shifts = list(range(shift_min, pl["n"] - shift_min, step))
    if len(shifts) < 20:
        return {"p": None, "n_shifts": len(shifts), "real_sr": real,
                "why": f"이동이 {len(shifts)}가지뿐이라 p 의 바닥이 너무 높아요"}
    a = np.array([_sr(repnl(pl, shifted(pos, k, sign_only=sign_only))[m])
                  for k in shifts])
    beat = int((a >= real).sum())
    return {"p": (beat + 1) / (len(a) + 1), "n_shifts": len(a),
            "real_sr": real, "beat": beat,
            "placebo_median": float(np.median(a)),
            "placebo_p95": float(np.percentile(a, 95)),
            "sign_only": sign_only, "why": None}
