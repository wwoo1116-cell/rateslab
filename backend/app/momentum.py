# -*- coding: utf-8 -*-
r"""Momentum 측정면 — 추세 다리와 매크로 다리를 **나란히** 세운다 (Strategy 셋째 세입자).

**방향과 강도를 재는 화면이지 단독 전략이 아니다.** 선물 추세 단독은 자본비용
전액 규약에서 MMF 초과 −1.07 ~ +0.97%/년이었다(`research\ktb-tsmom` vs_mmf).
그래서 이 면은 크기·진입·손절을 말하지 않는다 — Credit RV 의 「랭킹이지
투자판단이 아니다」, MR 의 「측정이지 신호가 아니다」와 같은 명구 의무다.

## 구조는 «등록된 북» 그대로다 [OWNER 2026-09-09]

AQR(Brooks 2017)의 병렬 50/50 이 이 레인이 채택한 설계다. 그러니 화면도 두
다리로 선다:

    추세 다리   계약 2 × 룩백 5, 신호는 **macross 하나**       ← cta_macro.py 가 그것
    매크로 다리 네 테마 부호 평균(`macro_sign`)
    50/50      두 북을 따로 돌려 **손익**을 반씩

⚠ `tsmom`·`donchian` 은 `scripts/cta_validate.py` 의 **PBO 격자 차원**이지 이 북에
안 들어간다. 화면에 올리면 안 쓰는 신호를 매일 보여주게 된다.

⚠ 곱하지 않는다. 「추세 × 매크로」 변조는 2026-09-09 에 NO-GO 였다 — 지지 점수가
계열 하나라 북 총 크기의 시간 변조로 축퇴하고 북 변동성 목표가 되돌린다(추세와
상관 0.977, `data\krw-macro-vintage\RESULT_cta_macro_mod.md`). 그래서 두 다리는
**나란히** 서고 곱해진 값은 어디에도 없다.

## 룩백은 손잡이가 아니라 축이다

이 레인의 규율이 「룩백을 고르지 마라」다(매년 전진 선택하면 7년 합 −3,230만).
셀렉트로 두면 화면이 그 규율을 어기는 도구가 되므로 다섯을 **전부 열로** 세운다.
왼쪽 빠름 → 오른쪽 느림. 그 줄의 «모양»이 합성값 하나로는 안 보이는 것을 말한다.

## 색은 신호 부호가 아니라 «금리» 방향을 진다

가격 상승 = 금리 하락이다. 그래서 신호 +1 은 이 데스크의 관례에서 **파랑**이고,
부호를 그대로 칠하면 색이 통째로 뒤집힌다. 서버가 `rate = −signal` 을 같이 내고
화면은 그 값으로 `directionClass`/`directionGlyph` 를 부른다 — 캐논을 굽히지 않고
관례를 지키는 자리.

## ★ 채점 잠금

`data\krw-macro-vintage\PREREG.md` 가 2026-09-08 에 동결됐고 채점 대상은 그 다음
영업일부터다. 그 문서가 「판정일까지 들여다보지 말 것 — 중간에 보는 것 자체가
사전등록을 훼손한다」고 못박고 있으므로, **동결일 이후의 손익 계열은 응답에서
잘라낸다.** 프런트에서 자르면 네트워크 탭에 그대로 남는다 — 자르는 자리가 여기여야
한다. 세 다리를 **모두** 자른다: 추세만 남기면 50/50 과의 차로 매크로를 역산할 수
있고, 한 규칙이 무너뜨리기 어렵다.

오늘의 «신호 상태»는 잠금 대상이 아니다. 그건 성적이 아니라 포지션이다.
"""
from __future__ import annotations

import csv
import math
import os
import statistics as st

from . import ctabacktest as cta, futures

#: 동결일. 이 날 **다음** 영업일부터가 채점 구간이고, 그 구간의 손익은 안 나간다.
FREEZE = "2026-09-08"

#: 등록된 북의 손잡이. 격자가 아니라 **고정값**이다 — 고르지 않는다.
SIGNAL = "macross"
LOOKBACKS = (20, 40, 60, 120, 250)
VOL_WINDOW = 60
BOOK_VOL_WINDOW = 120
TARGET_VOL = 1_000_000.0          # 북 전체의 하루 표준편차
BARS = 252

TENORS = ("3Y", "10Y")

#: 네 테마 — 이름과 순서는 `data\krw-macro-vintage\src\build_themes.py` 의 그 표다.
THEMES = (
    ("cycle", "경기순환"),
    ("policy", "통화정책"),
    ("trade", "국제교역"),
    ("risk", "위험선호"),
)

#: 매크로 신호가 사는 자리. 아침 굽기가 레인(`data\krw-macro-vintage\out`)에서
#: 여기로 **복사한다** — 그 레인은 git 리포가 아니라 배포된 백엔드에 경로가 없다
#: (`backend/data/raw/bigfoot_*.csv` 가 같은 선례다). 없으면 매크로 다리만 비고
#: 추세 다리는 그대로 뜬다 — 값이 없는 것과 0 인 것을 섞지 않는다.
THEMES_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "data", "macro_themes_daily.csv")


class MomentumError(ValueError):
    """설 수 없는 입력 — 조용히 0 을 내지 않는다."""


def _sign(x: float) -> int:
    return 0 if x == 0 else (1 if x > 0 else -1)


def _load_prices() -> tuple[dict[str, tuple[list[str], list[float]]], set[str]]:
    """조정가 — **차분만 유효**하다(레인 규약). 수준은 어디서도 안 쓴다."""
    f = futures.load()
    out: dict[str, tuple[list[str], list[float]]] = {}
    for t in TENORS:
        s = f.series[t]
        d = [x.isoformat() if hasattr(x, "isoformat") else str(x) for x in s.dates]
        px = list(s.price_adj)
        keep = [i for i, p in enumerate(px) if p is not None]
        if not keep:
            raise MomentumError(f"{t} 조정가가 비었어요")
        out[t] = ([d[i] for i in keep], [float(px[i]) for i in keep])
    rolls = {x.isoformat() for x in futures.roll_days(list(f.series["3Y"].dates))}
    return out, rolls


def _load_macro() -> dict[str, dict[str, float]] | None:
    """`{열: {날짜: 값}}`. 파일이 없으면 **None** — 빈 dict 와 구별한다."""
    path = os.path.abspath(THEMES_CSV)
    if not os.path.exists(path):
        return None
    cols = ("macro_sign",) + tuple(k for k, _ in THEMES)
    out: dict[str, dict[str, float]] = {c: {} for c in cols}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            day = row["date"][:10]
            for c in cols:
                v = row.get(c, "")
                if v not in ("", "NA", "nan"):
                    out[c][day] = float(v)
    return out if out["macro_sign"] else None


def _trend_signals(series) -> dict[str, dict[str, float]]:
    """엔진이 **내부에서 만드는 것과 같은** 신호를 밖으로 꺼낸다.

    `book_simulate(continuous=True)` 는 룩백별 `signal_continuous` 를 등가중
    평균한다. 같은 계산이라야 「보드가 보여주는 값 = 북이 실제로 태우는 값」이다.
    """
    out: dict[str, dict[str, float]] = {}
    for key, (dates, px) in series.items():
        sigs = [cta.signal_continuous(px, SIGNAL, lb) for lb in LOOKBACKS]
        out[key] = {d: st.fmean([s[j] for s in sigs]) for j, d in enumerate(dates)}
    return out


def _run_book(series, rolls, *, external=None):
    return cta.book_simulate(
        series, signal=SIGNAL, lookbacks=LOOKBACKS, vol_window=VOL_WINDOW,
        target_book_vol_krw=TARGET_VOL, book_vol_window=BOOK_VOL_WINDOW,
        roll_days=rolls, continuous=True, external_signals=external)


def _hold_days(vals: list[float]) -> int:
    """지금 부호를 며칠째 유지하고 있나. 0 은 방향이 아니라 「모른다」라 끊는다."""
    s = _sign(vals[-1])
    if s == 0:
        return 0
    n = 0
    for v in reversed(vals):
        if _sign(v) != s:
            break
        n += 1
    return n


def _headline(rows: list[dict], macro: dict | None) -> dict | None:
    """표 앞에 설 한 줄 — 「지금 가장 또렷한 다리」와 그 판단 재료.

    또렷함 = (속도합의, |합성 강도|) 사전식. 이 레인의 규율이 「다섯 룩백이 갈리면
    «모른다»에 가깝다」이므로 합의가 먼저다. `rate` 는 **금리 방향**이라 화면이
    그대로 색으로 쓴다(가격 상승 = 금리 하락).
    """
    if not rows:
        return None
    best = max(rows, key=lambda r: (r["speedAgree"], abs(r["composite"])))
    agrees: bool | None = None
    if macro is not None and macro["rate"] != 0 and best["compositeRate"] != 0:
        agrees = (macro["rate"] > 0) == (best["compositeRate"] > 0)
    return {
        "tenor": best["tenor"],
        # 부호는 **방향이 진다** — 강도는 무부호다(캐논: 글리프가 부호를 지고
        # 숫자는 크기만 적는다).
        "rate": best["compositeRate"],
        "strength": round(abs(best["composite"]), 3),
        "speedAgree": best["speedAgree"],
        "speedOf": best["speedOf"],
        "holdDays": best["holdDays"],
        #: 매크로가 없거나 어느 한쪽이 중립이면 **모른다**(`None`) — 「반대」가 아니다.
        "macroAgrees": agrees,
        "macroRate": (macro["rate"] if macro is not None else None),
    }


def build_board() -> dict:
    """오늘의 두 다리. 숫자는 여기서 끝난다(§16) — 브라우저는 포맷만 한다."""
    series, rolls = _load_prices()
    macro = _load_macro()
    trend = _trend_signals(series)

    b_trend = _run_book(series, rolls)
    asof = max(d[-1] for d, _p in series.values())

    def notional(book, key: str, day: str | None = None) -> float:
        """그 북의 **자기 as-of 날짜** 액면.

        매크로는 OECD 에디션 규약상 가격보다 하루 늦게 선다(그날 신호가 없으면
        포지션도 없다). 마지막 칸을 그냥 읽으면 매크로 다리가 매일 「0억」으로
        보이는데, 그건 「매크로가 빠졌다」가 아니라 「그 소스의 날짜가 다르다」다.
        MR 이 소스별 as-of 를 행마다 따로 세우는 그 규칙과 같다.
        """
        i = (book["dates"].index(day) if day in book["dates"]
             else len(book["dates"]) - 1)
        return abs(book["pos"][key][i])

    rows = []
    for t in TENORS:
        dates, px = series[t]
        sigs = {lb: cta.signal_continuous(px, SIGNAL, lb) for lb in LOOKBACKS}
        tstat = {lb: cta.trend_tstat(px, lb) for lb in LOOKBACKS}
        cells = []
        for lb in LOOKBACKS:
            v = sigs[lb][-1]
            tv = tstat[lb][-1]
            cells.append({
                "lookback": lb,
                "signal": round(v, 4),
                # 화면이 칠할 값 — 가격이 아니라 «금리» 방향이다.
                "rate": round(-v, 4),
                "tstat": round(tv, 2) if tv is not None else None,
            })
        comp_series = list(trend[t].values())
        comp = comp_series[-1]
        agree = sum(1 for c in cells if _sign(c["signal"]) == _sign(comp) and c["signal"] != 0)
        rows.append({
            "tenor": t,
            "price": round(px[-1], 3),
            "asof": dates[-1],
            "cells": cells,
            "composite": round(comp, 4),
            "compositeRate": round(-comp, 4),
            "holdDays": _hold_days(comp_series),
            "speedAgree": agree,
            "speedOf": len(LOOKBACKS),
            "notionalKrw": round(notional(b_trend, t)),
        })

    leg_macro = None
    if macro is None:
        macro_note = ("매크로 신호 파일이 아직 안 왔어요 — 추세 다리만 보여드려요.")
    else:
        day = max(macro["macro_sign"])
        sgn = macro["macro_sign"][day]
        days = sorted(macro["macro_sign"])
        b_macro = _run_book(series, rolls,
                            external={k: macro["macro_sign"] for k in series})
        leg_macro = {
            "asof": day,
            "themes": [{"key": k, "label": lab,
                        "sign": macro[k].get(day),
                        "rate": (None if macro[k].get(day) is None
                                 else -macro[k][day])}
                       for k, lab in THEMES],
            "sign": round(sgn, 3),
            "rate": round(-sgn, 3),
            "holdDays": _hold_days([macro["macro_sign"][d] for d in days]),
            "notionalKrw": {t: round(notional(b_macro, t, day)) for t in TENORS},
        }
        macro_note = None

    return {
        "asof": asof,
        "signal": SIGNAL,
        "lookbacks": list(LOOKBACKS),
        "targetBookVolKrw": TARGET_VOL,
        "costTicks": cta.COST_TICKS,
        "tstatCap": cta.TSTAT_CAP,
        "trend": rows,
        "macro": leg_macro,
        "macroNote": macro_note,
        # ── 히어로: 「지금 무엇을 볼까」의 답을 표 **앞**에 세운다 ─────────────
        #
        # [OWNER 2026-09-09 — 「Momentum도 RV나 MR과 같이 위에 Hero 하나 올려서
        # 트레이더가 바로 판단할 수 있게」]. RV 의 「지금 가장 매력적이에요」,
        # MR 의 「지금 모니터링할 테너예요」와 같은 자리다.
        #
        # **고르는 규칙은 이 레인이 이미 적어 둔 것이다** — 「속도합의가 갈리면
        # «모른다»에 가깝다」. 그러니 또렷함의 첫 열쇠는 강도가 아니라 **합의**이고,
        # 동률일 때만 강도가 가른다. 내가 새 순위를 지어낸 것이 아니다.
        #
        # ⚠ 여기서 고르는 이유는 §16(브라우저는 계산하지 않는다)이다. 화면이
        # `sort` 를 들면 「무엇이 1순위인가」가 두 곳에 살게 된다.
        #
        # 매크로 다리는 이 순위에 **안 들어간다** — 속도합의가 없어 같은 자로
        # 못 잰다. 대신 「같은 방향인가」로 메타에 붙는다. 두 다리를 나란히 세운
        # 이 화면에서 트레이더가 제일 먼저 묻는 것이 그것이라서다.
        "headline": _headline(rows, leg_macro),
        # 50/50 은 **손익 수준** 결합이라 「합쳐진 신호」가 없다. 그 사실을 적는다.
        "blend": {
            "weight": 0.5,
            "note": "두 북을 따로 돌려 손익을 반씩 섞어요 — 신호를 곱하지 않아요.",
        },
        "lock": {
            "freeze": FREEZE,
            "note": "동결일 이후 성적은 판정일까지 안 보여드려요.",
        },
    }


def build_history(key: str) -> dict:
    """상세 차트의 재료.

    **수준을 안 그린다** — 조정가는 차분만 유효하므로 「차분 누적, 창 시작 = 100」
    으로 낸다. 신호 강도는 같은 날짜 위에 얹는다.
    """
    if key == "macro":
        macro = _load_macro()
        if macro is None:
            raise MomentumError("매크로 신호 파일이 없어요")
        days = sorted(macro["macro_sign"])[-500:]
        return {"key": key, "dates": days,
                "index": None,
                "signal": [round(macro["macro_sign"][d], 4) for d in days],
                "rate": [round(-macro["macro_sign"][d], 4) for d in days]}
    if key not in TENORS:
        raise MomentumError(f"모르는 계열이에요: {key!r}")
    series, _rolls = _load_prices()
    dates, px = series[key]
    dates, px = dates[-500:], px[-500:]
    base = px[0]
    sigs = [cta.signal_continuous(*(px, SIGNAL, lb)) for lb in LOOKBACKS]
    comp = [st.fmean([s[j] for s in sigs]) for j in range(len(px))]
    return {
        "key": key,
        "dates": dates,
        "index": [round(100.0 + (p - base), 3) for p in px],
        "signal": [round(c, 4) for c in comp],
        "rate": [round(-c, 4) for c in comp],
    }


def _card(points: list[dict]) -> dict:
    """이 다리의 성적표.

    ## 분모를 안 만든다 [OWNER 2026-09-09]

    퍼센트 지표를 내려면 자본이 필요한데 이 데스크에는 AUM 이 없다. 지어내는
    대신 **비율만** 낸다 — Sharpe·Calmar·Martin 은 계열에 상수를 곱해도 안 변해서
    분모 없이도 두 레인을 나란히 놓을 수 있다. 퍼센트가 꼭 필요한 자리에서는
    「연 5% 가정 자본 ○억 기준」처럼 **가정을 숫자 옆에 적는다.**

    ## Ulcer 는 MR 과 **같은 잣대**다 [OWNER 2026-09-09]

    `mrmetrics.score` 의 그 식 그대로 — 낙폭 경로의 제곱평균제곱근이다.
    제곱해서 루트를 씌우므로 **음수가 될 수 없다**: 화면이 보기 좋으라고 부호를
    뒤집으면 그 순간 다른 물건이 된다(MR 화면 `parts.tsx` 가 `-perf.ulcer` 로
    뒤집고 있었고, 그게 2026-09-09 진단의 D2 다). 여기서는 안 뒤집는다.

    단위는 원화라 **다리끼리 그대로 못 비교한다** — 최대낙폭과 같은 사정이고,
    그래서 위험 맞춤 값을 `build_book` 이 따로 붙인다. Martin(연손익÷Ulcer)은
    무차원이라 그 문제가 없다.
    """
    daily = [p["dailyPnl"] for p in points]
    if len(daily) < 30:
        return {"sharpe": None, "calmar": None, "maxDrawdown": None,
                "ulcer": None, "martin": None,
                "annPnlKrw": None, "annVolKrw": None, "days": len(daily)}
    sd = st.pstdev(daily)
    run = peak = mdd = 0.0
    dd_path: list[float] = []
    for x in daily:
        run += x
        peak = max(peak, run)
        dd = peak - run
        dd_path.append(dd)
        mdd = max(mdd, dd)
    ann = sum(daily) * BARS / len(daily)
    ulcer = math.sqrt(sum(d * d for d in dd_path) / len(dd_path))
    return {
        "sharpe": round(st.fmean(daily) / sd * math.sqrt(BARS), 3) if sd > 0 else None,
        "calmar": round(ann / mdd, 3) if mdd > 0 else None,
        "maxDrawdown": round(mdd),
        "ulcer": round(ulcer),
        "martin": round(ann / ulcer, 3) if ulcer > 0 else None,
        "annPnlKrw": round(ann),
        "annVolKrw": round(sd * math.sqrt(BARS)),
        "days": len(daily),
    }


def build_book() -> dict:
    """**표본내** 성적. 동결일 이후는 여기서 잘라 낸다 — 위 머리의 그 이유."""
    series, rolls = _load_prices()
    macro = _load_macro()

    def cut(points: list[dict], start: str | None) -> list[dict]:
        return [p for p in points
                if p["t"] <= FREEZE and (start is None or p["t"] >= start)]

    b_trend = _run_book(series, rolls)
    legs = []
    if macro is None:
        start = None
        t_pts = cut(b_trend["points"], None)
        legs.append({"key": "trend", "label": "추세",
                     "card": _card(t_pts), "_pts": t_pts})
    else:
        start = min(macro["macro_sign"])
        b_macro = _run_book(series, rolls,
                            external={k: macro["macro_sign"] for k in series})
        t_pts = cut(b_trend["points"], start)
        m_pts = cut(b_macro["points"], start)
        mi = {p["t"]: p for p in m_pts}
        blend = [{"t": p["t"],
                  "dailyPnl": 0.5 * p["dailyPnl"] + 0.5 * mi[p["t"]]["dailyPnl"],
                  "barCost": 0.5 * p["barCost"] + 0.5 * mi[p["t"]]["barCost"]}
                 for p in t_pts if p["t"] in mi]
        legs = [
            {"key": "trend", "label": "추세", "card": _card(t_pts), "_pts": t_pts},
            {"key": "macro", "label": "매크로", "card": _card(m_pts), "_pts": m_pts},
            {"key": "blend", "label": "50/50", "card": _card(blend), "_pts": blend},
        ]

    # ── 위험 맞춤 낙폭 — 이 표의 원화 열은 그냥 못 비교한다 ──────────────
    #
    # Sharpe 와 Calmar 는 계열에 상수를 곱해도 안 변한다(둘 다 비율이다). 그런데
    # **연손익·연변동·최대낙폭은 변한다.** 그리고 세 다리의 실현 변동성이 실제로
    # 다르다(추세 목표의 1.14배 · 매크로 0.73 · 50/50 0.81) — 북 변동성 목표는
    # 사전 추정이라 사후로는 안 맞는다.
    #
    # 그 상태로 낙폭만 보면 「섞으면 낙폭이 반이 된다」로 읽히는데, 그중 얼마는
    # **덜 걸어서 덜 아팠던 것**이다. 이 데스크가 게이팅 레인에서 배운 그 규율이고
    # (Man 2016 Figure 7 이 제약판을 사후 변동성 맞춰 비교하는 그 규약), 그래서
    # 기준 다리(추세)의 변동성에 맞춘 낙폭을 **같이** 낸다.
    ref = None
    for leg in legs:
        pts = leg.pop("_pts", None)
        if pts is None:
            continue
        sd = st.pstdev([p["dailyPnl"] for p in pts])
        if ref is None:
            ref = sd
        g = (ref / sd) if sd > 0 else 1.0
        mdd = leg["card"]["maxDrawdown"]
        ulc = leg["card"]["ulcer"]
        leg["card"]["maxDrawdownVolMatched"] = None if mdd is None else round(mdd * g)
        # Ulcer 도 원화라 같은 사정이다. Martin 은 비율이라 안 건드린다.
        leg["card"]["ulcerVolMatched"] = None if ulc is None else round(ulc * g)
        leg["card"]["volRatio"] = round(sd / ref, 3) if ref else None

    return {
        "window": {"start": start, "end": FREEZE},
        "legs": legs,
        "volMatch": {
            "ref": "trend",
            "note": "원화 열은 다리마다 실제로 건 위험이 달라요 — 낙폭은 추세 다리에 맞춘 값도 같이 봐요.",
        },
        "lock": {
            "freeze": FREEZE,
            "note": "동결일 이후 성적은 판정일까지 안 보여드려요.",
            "why": "판정은 채점 750영업일 또는 방향전환 12회 중 나중에 와요.",
        },
    }
