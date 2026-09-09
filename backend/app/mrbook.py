# -*- coding: utf-8 -*-
"""BSS 테너 **통합** 밴드 워치 — 아홉 만기를 한 장부로 [OWNER 2026-09-01
— "BSS만을 활용한 전략을 구상한다고 할 때 지금은 각 테너별로 흩어져있는데,
BSS 테너 통합 밴드 워치를 하나 만들어서 승률 및 세부사항들을 확인할 수 있게"].

측정면(`mr.py`)은 만기마다 한 줄을 세우고, 전략 실험(`main.mr_strategy`)은
**한 계열**만 재현한다. 그래서 「이 규칙을 BSS 전체에 걸면 무엇이 되는가」는
화면에 없었다 — 아홉 칸을 눈으로 더해야 했고, 그렇게 더한 승률은 틀린다
(거래 수가 다른 아홉 승률의 평균은 묶음의 승률이 아니다).

## 통합의 정의 — 연구 레인과 **같은 것**을 쓴다

`backend/scripts/mr_live_report.py::all_tenors` 가 이미 포트폴리오를 세고 있고
(«9계열 동일가중 합»), 그 정의를 여기서 다시 짓지 않는다:

  · **동일가중 합** — 만기마다 같은 명목(₩/bp)을 걸고 일별 손익을 더한다.
  · **거래는 한 통에 모은다** — 승률·손익비는 아홉 목록을 이어 붙인 위에서 센다.
  · 계열마다 표본 날짜가 조금씩 다르므로(민평×IRS 교집합) **날짜로** 맞춘다.
    연구 스크립트는 인덱스로 맞추는데, 그건 같은 OOS 창을 잘라 쓰기 때문이고
    화면은 전 기간이라 날짜가 맞는 자리다.

## 다리 수는 **세어서 말한다**

동일가중 합의 대가는 명목이다. 아홉이 동시에 서면 걸린 돈이 아홉 배이고, 그
사실을 안 적으면 「명목 100만원/bp」 라고 적힌 화면이 실제로는 900만원/bp 를
움직이고 있게 된다. `book.maxLegs` 와 그 날짜가 그 자리다.

## 상관은 통합의 **유일한 공짜 점심**이다

아홉을 더해 SR 이 개별 중앙값보다 오르면 그건 분산 효과이고, 얼마나 오르는지는
쌍상관이 정한다. 연구 레인이 같은 자료에서 «평균 쌍상관 0.216 → 유효 독립 계열
3.3/9» 를 냈다 — 화면이 그 수를 스스로 말해야 통합이 왜 나은지가 주장이 아니라
숫자가 된다.

숫자는 전부 여기서 끝난다(§16). 산술은 `mrbacktest.simulate` 그대로이고 이
파일은 **합치기만** 한다 — 규칙을 하나라도 다시 쓰면 통합의 수가 아홉 칸의
합과 갈린다.
"""
from __future__ import annotations

import math
import statistics as st
from typing import Any

from . import mr as mr_mod
from . import mrdiag as mrd
from . import mrmetrics as mrm

#: 통합 장부의 id·이름 — 보드의 랭킹 **아래**에 따로 서는 한 줄이고, 전략
#: 실험 창이 이 id 로 열린다. 계열 목록(`mr.SERIES`)에는 **안 넣는다**:
#: 순위는 |z| 로 매겨지는데 이 줄은 값이 아니라 집계라 그 정렬에 낄 수 없다.
BOOK_ID = "BSS-ALL"
BOOK_LABEL = "BSS 통합"
#: 서브라인이 그대로 읽는다. **만기 수를 안 적는다** — 화면이 그 뒤에 「아래 수는
#: 평균이에요」를 붙이는데, 거기에 개수까지 넣으면 계열 열이 40px 넓어져 표가
#: 카드를 넘고 마지막 열(상태)이 잘린다(실측 2026-09-01, 「말줄임 절대 금지」).
#: 개수는 상세 카드(「만기 9개」)와 통합 창의 「BSS 9만기」가 진다.
BOOK_DEFN = "국고 − IRS 전 만기 묶음"


def bss_series() -> list[tuple[str, str]]:
    """(id, 라벨) — **만기 순서**다(`mr.SERIES` 의 차례가 곧 6M→10Y).

    랭킹은 |z| 순이지만 통합 화면은 만기 순으로 읽는다: 어느 구간이 늘어났는지는
    커브의 모양이라 순위로 늘어놓으면 안 보인다.
    """
    return [(sid, label) for sid, label, kind in mr_mod.SERIES if kind == "bss"]


def tenor_of(sid: str) -> str:
    """`BSS-3Y` → `3Y`."""
    return sid.split("-", 1)[1]


# ── 보드의 통합 행 ──────────────────────────────────────────────────────────


def watch(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """랭킹 아래 한 줄 + 만기 순 다리 목록. 못 세우면 None.

    **레벨을 지어내지 않는다.** 만기가 다른 아홉 스프레드의 평균은 거래할 수
    있는 값이 아니라서 「값」·「전일」 칸이 없다. 대신 단위 없는 둘(|z| 과 %B)만
    평균 내고, 나머지는 **개수**다 — 밴드 워치가 답해야 하는 질문이 「지금 몇
    개가 나가 있나」이기 때문이다.
    """
    bss = [r for r in rows if r["kind"] == "bss"]
    if not bss:
        return None
    order = {sid: i for i, (sid, _) in enumerate(bss_series())}
    bss.sort(key=lambda r: order.get(r["id"], 99))

    zs = [abs(r["z"]) for r in bss if r["z"] is not None]
    pbs = [r["pctB"] for r in bss if r["pctB"] is not None]
    kinds = [r["state"]["kind"] for r in bss]
    # 가장 늘어난 다리 — 통합 줄이 「어디가」를 안 말하면 개수만 남는다.
    peak = max((r for r in bss if r["z"] is not None),
               key=lambda r: abs(r["z"]), default=None)
    return {
        "id": BOOK_ID,
        "label": BOOK_LABEL,
        "kind": "book",
        "defn": BOOK_DEFN,
        "n": len(bss),
        "outLow": sum(1 for k in kinds if k == "below"),
        "outHigh": sum(1 for k in kinds if k == "above"),
        "reentry": sum(1 for k in kinds if k.startswith("reentry")),
        "inside": sum(1 for k in kinds if k == "inside"),
        "meanAbsZ": round(st.fmean(zs), 2) if zs else None,
        "meanPctB": round(st.fmean(pbs), 1) if pbs else None,
        "peak": None if peak is None else {"id": peak["id"], "label": peak["label"],
                                           "z": peak["z"]},
        # as-of 가 만기마다 다를 수 있다 — 민평×IRS 교집합이라 한 만기가 하루
        # 안 찍히면 그 다리만 뒤처진다(실측 2026-09-01: 6M·9M·1.5Y 가 08-24,
        # 나머지가 08-31). 최댓값만 적으면 화면이 아홉 다 최신인 척한다.
        "asof": max((r["asof"] for r in bss), default=None),
        "asofMin": min((r["asof"] for r in bss), default=None),
        "stale": sum(1 for r in bss
                     if r["asof"] < max(x["asof"] for x in bss)),
        # 만기 순 다리 — 상세 카드가 그대로 그린다(밴드 위치 스트립).
        "legs": [
            {"id": r["id"], "label": r["label"], "tenor": tenor_of(r["id"]),
             "v": r["v"], "d1": r["d1"], "z": r["z"], "pctB": r["pctB"],
             "state": r["state"], "asof": r["asof"]}
            for r in bss
        ],
    }


# ── 통합 백테스트 ───────────────────────────────────────────────────────────


def _pooled(legs: list[dict[str, Any]]) -> tuple[list[str], list[float], list[int], list[float]]:
    """(날짜, 그날 합산 손익, 그날 포지션이 선 다리 수, 그날 문 비용).

    날짜는 **합집합**이다. 어떤 만기가 하루 안 찍힌 날은 그 다리가 0 을 낸 것과
    같게 두는데, 그건 실제로 그날 그 다리를 못 움직였다는 뜻이라 맞는 처리다.
    (짧은 쪽에 맞춰 자르면 다른 만기의 표본을 버리게 된다.)

    다리 수는 **봉이 끝난 시점의 포지션**으로 센다 — 당일 종가 체결 규약이라
    진입 봉부터 들고 있는 것이고, 걸린 명목이 그날부터 아홉 배로 커진다.
    """
    dates = sorted({t for leg in legs for t in leg["dates"]})
    at = {t: i for i, t in enumerate(dates)}
    daily = [0.0] * len(dates)
    live = [0] * len(dates)
    #: 그날 문 비용 — 손익분기(`mrmetrics.score`)가 «구간 안에서 문 돈» 을
    #: 분모로 쓴다. 거래 목록에서 세면 미청산 다리의 진입 비용이 빠진다
    #: (`aggregate` 의 `paid` 가 같은 이유로 봉에서 센다).
    cost = [0.0] * len(dates)
    for leg in legs:
        for j, p in enumerate(leg["r"]["points"]):
            i = at[leg["dates"][j]]
            daily[i] += p["dailyPnl"]
            cost[i] += p["barCost"]
            if p["position"] != 0:
                live[i] += 1
    return dates, daily, live, cost


#: 봉의 성분 — (집계 키, 다리 봉의 엔진 키). `mrmetrics.SPLIT_PARTS` 와 같은
#: 어휘다(비용은 `_pooled` 이 이미 따로 센다).
_PART_KEYS: tuple[str, ...] = ("mtm", "barCarry", "barRolldown", "barFunding")


def _pooled_parts(legs: list[dict[str, Any]], dates: list[str]) -> list[dict[str, float]]:
    """봉마다 아홉 다리의 **성분**을 더한다 — 누적 분해가 구간을 따라가게
    [OWNER 2026-09-09 — "누적 채권 + 스왑 손익을 롤다운 캐리로 분해해서"].

    **한 다리라도 그 성분이 없으면 아예 안 싣는다.** 실가격 회계가 못 선 다리가
    섞이면 남은 여덟의 합이 되는데, 그 수는 「여덟 다리의 롤다운」이지 이 장부의
    롤다운이 아니다 — 지어낸 분해를 화면에 올리지 않는 이 리포의 규율이고,
    `mrmetrics.split` 도 같은 판정을 자기 쪽에서 한 번 더 한다.
    """
    at = {t: i for i, t in enumerate(dates)}
    have = {k: all(k in p for leg in legs for p in leg["r"]["points"])
            for k in _PART_KEYS}
    out: list[dict[str, float]] = [
        {k: 0.0 for k in _PART_KEYS if have[k]} for _ in dates
    ]
    for leg in legs:
        for j, p in enumerate(leg["r"]["points"]):
            row = out[at[leg["dates"][j]]]
            for k in row:
                row[k] += p[k]
    return out


def _curve(daily: list[float]) -> tuple[list[float], float, float]:
    """(누적, 총손익, 최대낙폭) — `mrbacktest.summarize` 와 같은 정의."""
    cum: list[float] = []
    run = 0.0
    peak = -math.inf
    mdd = 0.0
    for x in daily:
        run += x
        cum.append(run)
        peak = max(peak, run)
        mdd = max(mdd, peak - run)
    return cum, (cum[-1] if cum else 0.0), mdd


def _sharpe(daily: list[float]) -> float | None:
    """전 봉 기준 · 무위험 0 · 모집단 σ — 엔진(`mrbacktest.summarize`)과 같다."""
    if len(daily) < 2:
        return None
    m = st.fmean(daily)
    sd = st.pstdev(daily)
    return None if sd == 0 else m / sd * math.sqrt(252)


def _corr(a: list[float], b: list[float]) -> float | None:
    if len(a) < 2 or len(b) < 2:
        return None
    sa, sb = st.pstdev(a), st.pstdev(b)
    if sa == 0 or sb == 0:
        return None
    ma, mb = st.fmean(a), st.fmean(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / len(a)
    return cov / (sa * sb)


def _diversification(legs: list[dict[str, Any]], dates: list[str],
                     start: int = 0) -> dict[str, Any]:
    """쌍상관의 평균과 «유효 독립 계열 수» — **구간 안에서**.

    N_eff = N / (1 + (N−1)·ρ̄) — 상관이 0 이면 N, 1 이면 1 이 되는 그 표준식이다.
    이 수가 통합의 값어치를 말한다: 아홉을 더해도 유효하게는 셋뿐이면, 통합이
    개별보다 크게 나아지지 않는 것이 정상이고 그건 결함이 아니라 사실이다.

    ⚠ **짧은 구간에서는 상관이 상관을 못 잰다.** 「지난 1개월」이면 봉이 스물
    남짓이라 ρ̄ 의 표준오차가 0.2 를 넘는다 — 그 수를 「분산이 좋아졌다」로 읽으면
    안 된다. 화면이 봉 수를 같이 적어 읽는 사람이 가리게 한다(`days`).
    """
    at = {t: i for i, t in enumerate(dates)}
    series: list[list[float]] = []
    for leg in legs:
        v = [0.0] * len(dates)
        for j, p in enumerate(leg["r"]["points"]):
            v[at[leg["dates"][j]]] = p["dailyPnl"]
        series.append(v[start:])
    pairs = [c for i in range(len(series)) for j in range(i + 1, len(series))
             if (c := _corr(series[i], series[j])) is not None]
    n = len(series)
    rho = st.fmean(pairs) if pairs else None
    eff = None
    if rho is not None and n > 1:
        denom = 1.0 + (n - 1) * rho
        eff = n / denom if denom > 0 else float(n)
    return {
        "meanPairCorr": round(rho, 3) if rho is not None else None,
        "effectiveN": round(eff, 1) if eff is not None else None,
        "n": n,
        # 이 상관을 잰 봉 수 — 짧으면 수를 믿으면 안 된다(머리의 그 경고).
        "days": len(series[0]) if series else 0,
    }


def _spans(legs: list[dict[str, Any]], dates: list[str], points: list[dict],
           raw: list[dict], cost_bp: float) -> list[dict[str, Any]]:
    """네 구간을 **한 번에** 낸다 — 통합 성과 · 만기별 · 통합 대 개별 · 분산.

    낱개 창이 `mrmetrics.spans_for` 로 하는 것을 장부에서 하는 자리이고, 규율도
    같다: 엔진은 **늘 전체 표본 위에서** 돌고 바뀌는 것은 **채점**뿐이다. 고르개가
    서버에 다시 안 물으므로 stale 도 재실행도 없다.

    ## 자르는 날은 **장부 달력에서 한 번** 정한다

    만기마다 마지막 봉이 다르다(실측: 3만기 2026-08-24 · 나머지 09-04). 다리마다
    `span_start` 를 부르면 저마다 자기 끝에서 1년을 물려 **아홉이 서로 다른 창**을
    보고, 그러면 만기별 표의 합이 통합과 안 맞는다. 그래서 `span_cut` 으로 날을
    한 번 정하고 다리마다 `index_at` 으로 색인을 찾는다.

    ## 왜 SR 이 아니라 Calmar 인가 [OWNER 2026-09-07]

    「묶어서 나아졌나」의 축이 샤프에서 **Calmar** 로 갈렸다. 그러면서 이 절이
    답하는 질문도 갈렸다는 것을 적어 둔다 — 샤프판은 «묶어서 **분산**이 줄었나»
    였고 바로 아래 「유효 독립」과 산술이 맞물렸다(SR 은 1/σ 로 움직이므로 통합
    /개별 ≈ √N_eff 가 검산이 됐다). Calmar 의 분모는 **최대낙폭**이라 그 검산이
    안 선다 — 최대낙폭은 경로의 한 점이라 √N 으로 줄지 않는다.

    지금 이 절이 답하는 것은 «묶어서 **낙폭 대비**가 나아졌나» 이고, 유효 독립은
    그 옆에서 **왜 그만큼인지의 사정**을 말한다(상관만으로 서는 수라 그대로 산다).
    화면이 그 사실을 적는다.
    """
    out: list[dict[str, Any]] = []
    for key, months in mrm.SPANS:
        cut = mrm.span_cut(dates, months)
        i = mrm.index_at(dates, cut)
        card = mrm.score(dates, points, raw, i, cost_bp)

        per: list[dict[str, Any]] = []
        for leg in legs:
            j = mrm.index_at(leg["dates"], cut)
            m = mrm.score(leg["dates"], leg["r"]["points"], leg["r"]["trades"],
                          j, cost_bp)
            tr = [t for t in leg["r"]["trades"]
                  if cut is None or t["exitDate"] >= cut]
            per.append({
                "id": leg["id"], "label": leg["label"], "tenor": tenor_of(leg["id"]),
                "totalPnl": m["totalPnl"], "maxDrawdown": m["maxDrawdown"],
                "calmar": m["calmar"], "sortino": m["sortino"],
                "winRate": m["winRate"], "numTrades": m["numTrades"],
                "avgBars": round(st.fmean([t["bars"] for t in tr]), 1) if tr else None,
                # 몫 — 총합이 0 이거나 부호가 섞이면 비율이 뜻을 잃는다(120% 금지).
                "share": (round(m["totalPnl"] / card["totalPnl"], 4)
                          if card["totalPnl"] > 0 and m["totalPnl"] >= 0 else None),
            })

        cal = [p["calmar"] for p in per if p["calmar"] is not None]
        out.append({
            "span": key, **card,
            "legs": per,
            # 통합이 개별보다 나은지 — 중앙값 옆에 놓아야 판정이 선다.
            # **못 잰 다리는 안 센다**: 낙폭이 0 이면 Calmar 가 None 인데(구간
            # 안에서 한 번도 안 물속이었다는 뜻) 0 으로 채우면 «최악» 으로 줄을
            # 서서 중앙값을 끌어내린다. `n` 이 몇을 셌는지를 화면이 적는다.
            "legCalmar": {
                "median": round(st.median(cal), 3) if cal else None,
                "min": round(min(cal), 3) if cal else None,
                "max": round(max(cal), 3) if cal else None,
                "positive": sum(1 for c in cal if c > 0),
                "n": len(cal), "of": len(per),
            },
            "diversification": _diversification(legs, dates, i),
        })
    return out


def aggregate(legs: list[dict[str, Any]], *, notional: float,
              cost_bp: float, dynamic_cost: bool) -> dict[str, Any]:
    """아홉 다리 → 한 장부. 반환은 라우트가 그대로 썰어 내보내는 모양이다.

    `legs` 한 칸 = ``{"id","label","dates","r"}`` 이고 `r` 은
    `mrbacktest.simulate` 의 반환 그대로다. 이 함수는 **더하기만** 한다 —
    진입·청산 규칙을 여기서 다시 쓰면 통합의 수가 아홉 칸의 합과 갈린다.
    """
    dates, daily, live, barcost = _pooled(legs)
    cum, total, mdd = _curve(daily)

    # 진단이 먹는 **엔진 어휘 그대로의** 거래 목록(`exitReason` 등). 아래에서
    # 화면 어휘로 다시 쓰는데, 진단 함수(`mrdiag`)는 엔진 어휘를 읽으므로
    # 이름을 바꾼 쪽을 넘기면 사유별 집계가 조용히 빈다.
    raw = [t for leg in legs for t in leg["r"]["trades"]]

    # 거래는 한 통에 — 계열 이름을 달아 둔다(어느 만기의 거래인지가 표의 첫 칸).
    # 모양은 낱개 창의 거래 줄과 **같은 어휘**다(`MrStrategyTrade` + 계열 셋).
    # 두 표가 같은 사건을 다른 이름으로 부르면 안 된다.
    trades: list[dict[str, Any]] = []
    for leg in legs:
        show = leg.get("disp") or (lambda v: round(v, 4))
        for t in leg["r"]["trades"]:
            trades.append({
                "sid": leg["id"], "label": leg["label"], "tenor": tenor_of(leg["id"]),
                "entryT": t["entryDate"], "exitT": t["exitDate"],
                "dir": t["direction"],
                # 청산 z 는 None 일 수 있다 — 타임스탑이 σ=0(z=null) 봉에
                # 앉을 때(main.py 낱개 직렬화의 그 주석·같은 수리 2026-09-02).
                "entryZ": round(t["entryZ"], 2),
                "exitZ": round(t["exitZ"], 2) if t["exitZ"] is not None else None,
                "entryV": show(t["entryValue"]), "exitV": show(t["exitValue"]),
                "outFrom": t["outFrom"], "outDays": t["outDays"],
                "peakZ": round(t["peakZ"], 2) if t["peakZ"] is not None else None,
                "dv": round(t["dv"], 4),
                # 체결비용까지 문 Δ [OWNER 2026-09-09] — 낱개 창과 **같은 함수**
                # 다(`mrmetrics.dv_net`). 두 표가 같은 열을 다르게 계산하면 그
                # 순간 두 화면이 딴 수를 말한다.
                "dvNet": mrm.dv_net(t["dv"], t["cost"], t["direction"], notional),
                "pnl": round(t["pnl"], 2), "why": t["exitReason"],
                "mtm": round(t["mtm"], 2), "carry": round(t["carry"], 2),
                # 롤다운·조달은 **실가격 회계에서만** 있다 — 낱개 창과 같은
                # 규약으로 없으면 안 싣는다(0 은 「그날 롤다운이 0」이라는 다른
                # 말이다). 한 장부에 두 회계가 섞일 수 있어 다리마다 본다.
                **({"rolldown": round(t["rolldown"], 2),
                    "funding": round(t["funding"], 2)} if "rolldown" in t else {}),
                "cost": round(t["cost"], 2), "bars": t["bars"],
            })
    trades.sort(key=lambda t: (t["entryT"], t["sid"]))
    # 승패는 **반올림 전** 손익으로 가른다 — 화면용으로 소수 둘째 자리에서 자른
    # 값을 세면 0.004원짜리 거래가 패로 넘어가고, 그 한 건이 낱개 창의 승률과
    # 통합 승률을 갈라 놓는다(엔진 `summarize` 도 원값으로 센다).
    wins = sum(1 for t in raw if t["pnl"] > 0)

    # 표본 끝의 미청산 — 만기마다 하나씩 있을 수 있다. 원본 규약대로 거래·승률에는
    # 안 들어가고(countOpen 을 켜면 거래 목록에 이미 들어와 있다), 「몇 다리가
    # 열려 있는지」를 승률 옆에서 말할 수 있게 따로 낸다.
    opens = []
    for leg in legs:
        o = leg["r"]["open"]
        if o is None:
            continue
        show = leg.get("disp") or (lambda v: round(v, 4))
        pts = leg["r"]["points"]
        # 진입 이후의 총 변화(bp) — **수준의 차**다. 이 장부는 BSS 전용이고
        # (`bss_series`) BSS 는 상수만기라 롤 마스크가 없으므로 「거래 가능한 Δ」와
        # 수준의 차가 같다(`main._mr_leg` 의 `tradable` 이 BSS 에서는 None).
        # 마스크가 있는 계열이 이 장부에 들어오는 날에는 그 배열로 세야 한다 —
        # `leg` 의 계약(id·label·dates·r)에는 그 배열이 없으므로 그때는 이 함수의
        # 입력을 늘려야 한다. 지금 조용히 수준 차를 적으면 그 계열에서만 틀린다.
        ei = o["entryIdx"]
        o_dv = pts[-1]["value"] - pts[ei]["value"] if pts else 0.0
        opens.append({
            "sid": leg["id"], "label": leg["label"], "tenor": tenor_of(leg["id"]),
            "entryT": o["entryDate"], "dir": o["direction"],
            "entryZ": round(o["entryZ"], 2), "entryV": show(o["entryValue"]),
            # ── 모은 거래 표에 **줄로 설 수 있게** [OWNER 2026-09-09 —
            #    "미청산도 PnL에 포함하기"] ──────────────────────────────────
            # 종전에는 손익과 봉 수만 나갔다. 그러면 화면이 승률 옆에 「열린
            # 다리 둘」이라고만 말할 수 있고, **모은 거래 표의 세로합이 누적과
            # 갈린다**. 「청산」 쪽 값은 마지막 봉의 평가다(청산이 아니다).
            "exitT": leg["dates"][-1] if leg["dates"] else None,
            "exitV": show(pts[-1]["value"]) if pts else None,
            "exitZ": (round(pts[-1]["z"], 2)
                      if pts and pts[-1]["z"] is not None else None),
            "outFrom": o["outFrom"], "outDays": o["outDays"],
            "peakZ": round(o["peakZ"], 2) if o["peakZ"] is not None else None,
            "mtm": round(o["mtm"], 2), "carry": round(o["carry"], 2),
            **({"rolldown": round(o["rolldown"], 2),
                "funding": round(o["funding"], 2)} if "rolldown" in o else {}),
            "cost": round(o["cost"], 2),
            "dv": round(o_dv, 4),
            "dvNet": mrm.dv_net(o_dv, o["cost"], o["direction"], notional),
            "pnl": round(o["pnl"], 2), "bars": o["bars"],
        })

    # 실제로 문 비용 — **봉에서** 센다(거래 목록에서 세면 미청산 다리의 진입
    # 비용이 빠진다 — `mrbacktest` 가 같은 자리에서 겪은 그 잔차다).
    paid = -sum(p["barCost"] for leg in legs for p in leg["r"]["points"])
    mult = None if paid <= 0 else 1.0 + total / paid

    per: list[dict[str, Any]] = []
    for leg in legs:
        s = leg["r"]["summary"]
        tr = leg["r"]["trades"]
        per.append({
            "id": leg["id"], "label": leg["label"], "tenor": tenor_of(leg["id"]),
            # ── 이 다리의 돈이 **어느 회계에서 나왔나** [2026-09-09] ──────────
            # `_mr_real_accounting` 은 못 재면 조용히 엔진 근사로 되돌린다. 낱개
            # 창과 격자는 그 사실을 `real`/`headReal` 로 말하는데 **통합 장부만
            # 안 말하고 있었다** — 다리마다 갈릴 수 있으므로 합계가 두 회계를
            # 더한 수가 될 수 있다(krw-crs 레인 실측: 162칸 중 42칸이 섞임).
            # `None` 은 「이 다리가 회계를 안 말한다」다 — 0/1 로 뭉개지 않는다.
            "real": leg.get("real"),
            "totalPnl": round(s["totalPnl"], 2),
            "maxDrawdown": round(s["maxDrawdown"], 2),
            "sharpe": round(s["sharpe"], 3) if s["sharpe"] is not None else None,
            "winRate": round(s["winRate"], 4) if s["winRate"] is not None else None,
            "numTrades": s["numTrades"],
            "avgBars": round(st.fmean([t["bars"] for t in tr]), 1) if tr else None,
            "openPnl": round(s["openPnl"], 2) if s["openPnl"] is not None else None,
            # 총손익에서 이 다리가 차지하는 몫. 총합이 0 이거나 부호가 섞이면
            # 비율이 뜻을 잃으므로 그때는 None 이다 — 120% 같은 수를 안 적는다.
            "share": (round(s["totalPnl"] / total, 4)
                      if total > 0 and s["totalPnl"] >= 0 else None),
            "blocked": leg["r"]["blocked"],
            "gated": leg["r"]["gated"],
            "asof": leg["dates"][-1] if leg["dates"] else None,
        })

    # ── 장부 수준의 회계 — **불리언 하나가 아니라 «몇/몇»** [2026-09-09] ────
    #
    # 섞였을 때 「근사」로 뭉뚱그리면 **8/9 와 0/9 가 같은 말**이 된다. 그래서
    # 센 수와 **어느 다리인지**를 같이 낸다(이 리포의 「빈칸으로 렌더하느니 이유를
    # 쓴다」 규율 — `MR_RECON_WHY` 가 그 본보기).
    #
    # 셋째 칸 `unknown` 은 「그 다리가 회계를 안 말한다」다(구 계약·시험 픽스처).
    # 모르는 것을 근사로 세면 화면이 없는 사실을 말하게 된다.
    reals = [(leg["id"], leg.get("real")) for leg in legs]
    accounting = {
        "real": sum(1 for _sid, v in reals if v is True),
        "total": len(reals),
        "approx": [sid for sid, v in reals if v is False],
        "unknown": [sid for sid, v in reals if v is None],
    }

    port_sharpe = _sharpe(daily)
    idle = sum(1 for x in live if x == 0)
    # 채점용 봉 — `mrmetrics.score` 는 엔진 봉의 어휘를 먹는다(`dailyPnl`·
    # `barCost`). 화면 페이로드가 아니라 이 어휘로 넘겨야 낱개 창의 구간 카드와
    # **같은 자**가 된다(두 번째 정의 없음).
    #: 성분까지 실어 둔다 [OWNER 2026-09-09] — 구간 카드의 누적 분해가 이 봉에서
    #: 나오고, 장부 전체의 분해도 **같은 배열**에서 나온다(두 수가 갈릴 자리를
    #: 안 만든다).
    parts = _pooled_parts(legs, dates)
    spoints = [{"dailyPnl": daily[i], "barCost": barcost[i], **parts[i]}
               for i in range(len(dates))]
    peak_i = max(range(len(live)), key=lambda i: live[i]) if live else None

    return {
        "asof": dates[-1] if dates else None,
        # 어느 회계로 잰 장부인가 — 위 주석의 그 셋.
        "accounting": accounting,
        "from": dates[0] if dates else None,
        "to": dates[-1] if dates else None,
        "bars": len(dates),
        "points": [{"t": dates[i], "pnl": round(daily[i], 2),
                    "cum": round(cum[i], 2), "legs": live[i]}
                   for i in range(len(dates))],
        "trades": trades,
        "legs": per,
        "open": opens,
        "summary": {
            "totalPnl": round(total, 2),
            "maxDrawdown": round(mdd, 2),
            "winRate": round(wins / len(trades), 4) if trades else None,
            "sharpe": round(port_sharpe, 3) if port_sharpe is not None else None,
            "numTrades": len(trades),
            "openLegs": len(opens),
            "openPnl": round(sum(o["pnl"] for o in opens), 2) if opens else None,
            # 손익분기 — 다리마다 같은 명목·같은 비용이라 총손익이 여전히 비용의
            # 일차식이다(`mrbacktest.breakeven_cost_bp` 와 같은 논증). 동적 비용
            # 판에서는 「몇 bp」가 한 숫자로 안 나오므로 **경로의 몇 배**만 답한다.
            "breakevenCostBp": (None if dynamic_cost or mult is None
                                else round(cost_bp * mult, 3)),
            "breakevenCostMult": round(mult, 3) if mult is not None else None,
            # 누적 손익의 성분 [OWNER 2026-09-09 — "누적 채권 + 스왑 손익을
            # 롤다운 캐리로 분해해서 보여주기"]. 아홉 다리의 봉을 한 통에 모아
            # 더한다 — 다리별 분해는 「만기별 성적」이 이미 진다. 한 다리라도
            # 성분이 없으면 그 성분은 None 이다(`mrmetrics.split` 의 그 규율).
            "split": mrm.split(spoints),
        },
        # 걸린 돈 — 동일가중 합의 대가다. 이걸 안 적으면 화면의 「명목」이
        # 실제로 움직인 돈을 최대 아홉 배 작게 말한다.
        "book": {
            "maxLegs": max(live) if live else 0,
            "meanLegs": round(st.fmean(live), 2) if live else None,
            "idleShare": round(idle / len(live), 4) if live else None,
            "peakT": dates[peak_i] if peak_i is not None else None,
            "peakNotional": (max(live) if live else 0) * notional,
        },
        # 구간 넷을 한 번에 [OWNER 2026-09-07] — 통합 성과·만기별·통합 대 개별·
        # 분산이 전부 여기 들어 있다. 고르개는 이 목록에서 고르기만 한다.
        "spans": _spans(legs, dates, spoints, raw, cost_bp),
        "diag": {
            # 사유별·손익비는 **한 통에 모은 거래** 위에서 센다 — 아홉 승률의
            # 평균이 아니다(거래 수가 다르면 그 평균은 아무것도 아니다).
            "exits": mrd.exit_tally(raw, notional),
            "payoff": mrd.payoff(raw, notional),
            # **표본 삼분할은 항상 전체 위에 선다** [OWNER 2026-09-07]. 이건
            # «시대가 바뀌어도 사나» 를 재는 안정성 검사라 채점 구간과 무관하다 —
            # 「지난 1개월」을 다시 셋으로 쪼개면 한 조각이 열흘이라 수가 뜻을
            # 잃는다. 화면이 그 사실을 제목과 각주에 적는다.
            "periods": mrd.period_split(
                dates, [{"dailyPnl": x} for x in daily]),
        },
        # 방향·필터로 못 들어간 신호 — 다리마다 세서 더한다(둘을 한 숫자로
        # 합치지 않는 규율은 엔진과 같다).
        "blocked": {"spells": sum(leg["r"]["blocked"]["spells"] for leg in legs),
                    "days": sum(leg["r"]["blocked"]["days"] for leg in legs)},
        "gated": {"spells": sum(leg["r"]["gated"]["spells"] for leg in legs),
                  "days": sum(leg["r"]["gated"]["days"] for leg in legs)},
    }
