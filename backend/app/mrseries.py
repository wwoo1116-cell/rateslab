# -*- coding: utf-8 -*-
"""BSS 계열의 **긴 표본** 출처 [OWNER 2026-08-28 — "옮기고"].

화면이 쓰던 `credit_matrix` 는 2020-01-02 부터라 BSS 가 6.7년이었다. 그 길이로는
다중검정 문턱을 못 넘는다(SR 1.05·시행 118 이면 최소 8.7년이 필요한데 3.5년밖에
없었다). `imx_data.timeseries` 에 **2014-05-28 부터의 국고채커브·스왑 IRS·CD 91일**
이 있어 12.0년이 된다.

## 이음매를 안 만든다

두 출처를 붙이면 그 자리에서 수준이 튀고, 그 튐이 z 에서 신호로 잡힌다. 겹치는
1,633일에서 **상관 0.9996~1.0000 · 중앙 차이 0.00~0.10bp · 최대 3.0bp** 로 같은
계열임을 확인했으므로 전 기간을 이 출처 하나로 쓴다.

## 보드의 오늘 숫자는 안 바뀐다

z·밴드·상태는 전부 **트레일링 창**이라 마지막 점의 값은 앞이 얼마나 길든 같다.
바뀌는 것은 (ㄱ) 전략 실험의 표본 길이와 (ㄴ) 히스토리 차트가 담을 수 있는 구간
뿐이다. 다만 두 출처의 차이가 0.1bp 언저리라 표시 소수 첫째 자리가 하루 이틀
다를 수는 있다.

## `universe_series` 를 안 건드리는 이유

그 함수는 Main·rv·시뮬이 같이 쓴다. MR 만 출처를 바꾸는 일에 앱 전체의 계열
유도를 흔들 이유가 없다 — 여기서 MR 몫만 따로 세운다.

## 캐시

한 번에 세 카테고리를 다 읽고(90,594행·0.85초) **워터마크(`MAX(trade_date)`,
0.014초)를 열쇠로** 메모한다. 이 리포의 캐시 규약이 그것이다. 카테고리별로 아홉
만기를 따로 읽으면 보드 한 번에 27번을 읽게 된다.
"""
from __future__ import annotations

import datetime as dt
import time
from functools import lru_cache
from typing import Any

from sqlalchemy import text

from .mysqldb import engine

CAT_KTB = "국고채커브"
CAT_IRS = "스왑-IRS(종합ALL)"
CAT_CD = "단기금리"
CD_ITEM = "CD 91일물"

#: 만기 라벨 → 그 카테고리의 항목명. 두 다리의 이름이 서로 달라서 표가 둘이다.
KTB_ITEM = {
    "6M": "6월이하(당일)", "9M": "9월이하(당일)", "1Y": "1년이하(당일)",
    "1.5Y": "1.5년이하(당일)", "2Y": "2년이하(당일)", "3Y": "3년이하(당일)",
    "5Y": "5년이하(당일)", "7Y": "7년이하(당일)", "10Y": "10년이하(당일)",
}
IRS_ITEM = {
    "6M": "6개월", "9M": "9개월", "1Y": "1년", "1.5Y": "18개월", "2Y": "2년",
    "3Y": "3년", "5Y": "5년", "7Y": "7년", "10Y": "10년",
}


#: 워터마크의 짧은 기억 — (잰 시각, 값). 적재는 하루 한 번인데 이 질의는
#: **호출마다** SSL 왕복이라 0.09초가 든다. 보드 한 번(계열 아홉 × 값·캐리
#: 두 길)이면 열여덟 번이라 1.6초였고, 통합 장부는 같은 자리를 또 지난다
#: (프로파일 2026-09-01). 창이 짧아 «갈아 끼는 열쇠» 라는 설계는 그대로다 —
#: 적재가 돌면 늦어도 이 초만큼 뒤에 새 번들이 선다.
_WATERMARK_TTL_S = 60.0
_watermark_memo: tuple[float, str] | None = None


def _watermark() -> str:
    global _watermark_memo
    now = time.monotonic()
    if _watermark_memo is not None and now - _watermark_memo[0] < _WATERMARK_TTL_S:
        return _watermark_memo[1]
    with engine().connect() as conn:
        row = conn.execute(text("SELECT MAX(trade_date) FROM imx_data.timeseries")).fetchone()
    mark = "" if row is None or row[0] is None else str(row[0])
    _watermark_memo = (now, mark)
    return mark


@lru_cache(maxsize=2)
def _bundle(_watermark_key: str) -> dict[str, Any]:
    """세 카테고리를 한 번에. 열쇠는 워터마크라 적재가 돌면 저절로 갈린다."""
    with engine().connect() as conn:
        rows = conn.execute(text(
            "SELECT trade_date, category, item, value FROM imx_data.timeseries "
            "WHERE category IN (:a, :b, :c) ORDER BY trade_date"
        ), {"a": CAT_KTB, "b": CAT_IRS, "c": CAT_CD}).fetchall()
    ktb: dict[str, dict[str, float]] = {}
    irs: dict[str, dict[str, float]] = {}
    cd: dict[str, float] = {}
    want_k = {v: k for k, v in KTB_ITEM.items()}
    want_i = {v: k for k, v in IRS_ITEM.items()}
    for d, cat, item, val in rows:
        if val is None:
            continue
        day = d.isoformat() if isinstance(d, (dt.date, dt.datetime)) else str(d)[:10]
        if cat == CAT_KTB and item in want_k:
            ktb.setdefault(want_k[item], {})[day] = float(val)
        elif cat == CAT_IRS and item in want_i:
            irs.setdefault(want_i[item], {})[day] = float(val)
        elif cat == CAT_CD and item == CD_ITEM:
            cd[day] = float(val)
    return {"ktb": ktb, "irs": irs, "cd": cd}


def bundle() -> dict[str, Any]:
    return _bundle(_watermark())


def reset_cache() -> None:
    """시험이 부른다 — 라이브 경로는 워터마크가 알아서 갈아 낀다."""
    global _watermark_memo
    _watermark_memo = None
    _bundle.cache_clear()


def tenor_of(sid: str) -> str:
    """`BSS-3Y` → `3Y`. 이 모듈은 BSS 만 다룬다."""
    return sid.split("-", 1)[1]


def legs(sid: str, *, need_cd: bool = False) -> tuple[list[str], list[float], list[float], list[float]]:
    """(날짜, 국고, 스왑, CD) — **세(또는 두) 다리가 다 찍힌 날에만** 선다.

    한쪽을 이월해 채우면 없던 스프레드를 지어내게 된다(`universe._align` 의 그
    규율). `need_cd` 는 캐리를 쓸 때만 참이다 — 값 자체는 CD 없이도 선다.
    """
    t = tenor_of(sid)
    b = bundle()
    g = b["ktb"].get(t)
    s = b["irs"].get(t)
    if not g or not s:
        raise KeyError(f"{sid}: 긴 표본에 없는 만기다 ({t})")
    days = set(g) & set(s)
    if need_cd:
        days &= set(b["cd"])
    dates = sorted(days)
    if not dates:
        raise ValueError(f"{sid}: 두 다리가 같이 찍힌 날이 없다")
    cd = b["cd"]
    return (dates, [g[d] for d in dates], [s[d] for d in dates],
            [cd.get(d, 0.0) for d in dates])


def points(sid: str) -> dict[str, Any]:
    """`mr.series_points` 가 먹는 모양 — 값은 **bp**(국고 − 스왑, ×100)."""
    dates, govt, swap, _cd = legs(sid)
    return {
        "id": sid, "unit": "bp",
        "points": [{"t": d, "v": round((govt[i] - swap[i]) * 100.0, 4)}
                   for i, d in enumerate(dates)],
    }


# ── IRS 커브·플라이 [OWNER 2026-09-09 — "스프레드(버터플라이나 커브와 같은 것도
#    연결해주기)" · 축은 「IRS 커브·플라이」] ──────────────────────────────────
#
# ## 조합의 정본은 이 리포에 이미 있다
#
# 어느 조합을 실을지를 여기서 새로 고르지 않는다 — `app/derive.py` 의 **주요
# 세트**(`KEY_SPREADS` 여덟 · `KEY_FLIES` 넷)가 이 앱의 모니터·백테스트·시뮬이
# 같이 쓰는 목록이고 [OWNER 2026-07-31], 두 화면이 서로 다른 「주요 스프레드」를
# 가지면 그 순간 비교가 불가능해진다(`instruments.py` 머리의 그 문장).
#
# ## 값의 규약도 그 파일의 것이다
#
#     스프레드 a-b   = (r_b − r_a) × 100      (긴 쪽 − 짧은 쪽, bp)
#     플라이  a-b-c  = (2·r_b − r_a − r_c) × 100
#
# `derive.spread_series`·`fly_series` 와 **같은 식**이다. 저쪽은 `Dataset`(엑셀
# 스냅샷)을 먹고 이쪽은 긴 표본 번들(`bundle`)을 먹어서 함수를 그대로는 못 부르지만,
# 수는 같은 수여야 한다 — `tests/test_mrseries_combo.py` 가 두 길을 대조한다.
#
# ## 다리는 **커브 그대로** 실린다
#
# DV01 중립 가중은 손익 산술의 몫이고(`main._mr_leg` 의 pv01 환산), 값 계열은
# 호가 규약 그대로다. 가중을 값에 섞으면 그 계열의 「레벨」이 데스크가 부르는
# 3s10s 와 달라진다.

#: 커브·플라이의 노드 — `IRS_ITEM` 에 있는 만기만. 주요 세트 열둘은 전부 여기 든다
#: (6M·9M·1Y·1.5Y·2Y·3Y·5Y·10Y). 4Y·6Y 같은 노드는 이 표에 없어서 조합도 없다.
COMBO_TENORS: tuple[str, ...] = tuple(IRS_ITEM.keys())


def combo_tenors(sid: str) -> list[str]:
    """`IRC-3Y-10Y` → `['3Y','10Y']` · `IRF-2Y-5Y-10Y` → `['2Y','5Y','10Y']`.

    앞의 접두(`IRC`/`IRF`)만 떼고 나머지를 `-` 로 가른다 — 만기 라벨에는 `-` 가
    없다(`1.5Y` 처럼 점은 있다).
    """
    return sid.split("-")[1:]


def combo_points(sid: str) -> dict[str, Any]:
    """`mr.series_points` 가 먹는 모양 — 값은 **bp**.

    다리 레벨(`legs`)은 **커브 스프레드에만** 싣는다. 대사표의 다리 줄
    (`main._attach_leg_recon`)이 「다리0 − 다리1」을 전제로 부호를 매기므로
    (`sign = -1 if j == 0 else 1`) 두 다리짜리에서만 그 전제가 참이다. 플라이는
    `2·벨리 − 윙` 이라 그 부호 규약이 안 맞고, 안 맞는 분해를 실으면 대사표가
    **그럴듯하게 틀린 수**를 세운다 — 그래서 아예 안 싣고, 그때 화면은 종합
    한 줄짜리 대사표를 그린다(`mrcarry.LEG_NAMES` 에 `irf` 가 없는 것과 한 몸).

    다리의 차례는 `[긴 쪽, 짧은 쪽]` 이다 — 값이 `긴 − 짧은` 이므로 그 차례라야
    「다리0 − 다리1 = 값」이 대사표에서 닫힌다.
    """
    ts = combo_tenors(sid)
    b = bundle()
    series = []
    for t in ts:
        s = b["irs"].get(t)
        if not s:
            raise KeyError(f"{sid}: 긴 표본에 없는 만기다 ({t})")
        series.append(s)
    days = set(series[0])
    for s in series[1:]:
        days &= set(s)
    dates = sorted(days)
    if not dates:
        raise ValueError(f"{sid}: 다리들이 같이 찍힌 날이 없다")

    pts = []
    for d in dates:
        vals = [s[d] for s in series]
        if len(vals) == 2:
            a, bb = vals                                  # 짧은, 긴
            pt = {"t": d, "v": round((bb - a) * 100.0, 4), "legs": [bb, a]}
        else:
            a, mid, c = vals                              # 짧은 윙, 벨리, 긴 윙
            pt = {"t": d, "v": round((2 * mid - a - c) * 100.0, 4)}
        pts.append(pt)
    return {"id": sid, "unit": "bp", "points": pts}
