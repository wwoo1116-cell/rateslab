# -*- coding: utf-8 -*-
"""크레딧 RV (DTS) — **Lab 세입자**. 제품 `rv.py` 는 한 줄도 안 건드린다.

[OWNER 2026-10-02] 「정규화 할 때 리스크팩터를 DTS 로 두면?」 → 「좁은 게 싸 보인다,
이게 내가 원하는 방향성」 → 「전부 KTB 대비 스프레드로」 → 「통안은 뺀다」 →
**「DTS version 을 하나 Lab 에다가 만드는 게 낫겠는데?」**

## 왜 Lab 인가

이 축은 **표본밖에서 한 번 이겼을 뿐**이다(아래 근거). 제품 Credit RV 의 Score 는
트레이더 설계안(2026-08-18)이고, 검증이 한 바퀴 돈 것으로 산 화면의 신호를 갈아
끼우지 않는다 — 이 리포가 Lab 을 두는 이유가 그것이다(실시간 IRS 와 같은 자세).
둘을 나란히 두고 기록이 쌓이면 그때 승격을 묻는다.

## 무엇이 다른가 — 제품과 네 자리

| | 제품 `rv.py` | 여기 |
|---|---|---|
| 앵커 | 둘(앞단 국고 · 확산 특은) | **국고 하나** |
| 유니버스 | 7섹터 × 6테너 = 42칸 | **10섹터 × 12테너 = 120칸**(등급축 CB2~CB5) |
| 통안 | 포함 | **제외** — 크레딧이 아니라 금리물이고 국고 대비가 0 을 가로지른다 |
| 상대축 | `0.4·zAbs + 0.4·zSector + 0.2·zCurve`, 분모 σ | **zAbs 하나, 분모 `s`** |

## ★분모를 `s` 로 두는 근거 (research/credit-rv-dts, 2026-10-02)

제품의 원칙 ③은 「점수화는 level 이 아니라 **deviation 만**」인데, **같은 만기 안에서**
(= 트레이더가 실제로 고르는 자리) 지금 축의 레벨 누출은 **+0.418** 이다. 분모를 쓸면:

    σ(지금) +0.418 · s^0.5 +0.297 · s^0.75 +0.152 · **s(DTS) +0.076** · s^1.5 −0.136

β* ≈ 1 에서 0 을 지나고 음수인 날이 41% 로 대칭이 된다. 표본밖(2025-01~) 롱온리
순수 RV(−Δs, 캐리 없음, 테너 중립)도 **전 호라이즌에서 이긴다**:

    21일 +0.63(t 4.77) · 63일 +0.99(t 4.83) · 126일 +1.63(t 8.38)
    대조군(「넓은 걸 사라」) = +0.09 · −0.07 · −0.47   ← 순수 RV 에서 **음수**다

⚠**합성은 도움이 안 됐다** — `zSector` 는 같은 만기 안에서 「s − 동료평균」이고
동료평균이 공통항이라 **순서가 스프레드 순서와 같다**. 지우려던 수준을 되넣는다.

⚠**느린 회전에서만 산다**: 손익분기 왕복비용이 21일 0.63bp · 63일 0.99bp ·
126일 1.63bp 다. 이 리포 가정(1bp 왕복)에서 **21일 회전은 죽는다.**

⚠ 겹침이 심한 표본이라 t 를 액면대로 믿으면 안 된다(126일 판의 비중첩 구간 3~4개).
민평은 평가사 호가라 자기상관이 높고 **넓은 종목일수록 더 굼뜨다**.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from . import creditmatrix as cm
from . import mysqldb

#: 유니버스 — 크레딧만. KTB 는 앵커, **MSB(통안)는 뺀다**(위 표).
#: `creditmatrix.BOND_TYPES` 는 제품 유니버스(여덟)라 CB2~CB5 가 없다 — 등급축이
#: 이 화면의 핵심이므로 여기서 따로 센다.
SECTORS: dict[str, str] = {
    "KDB": "산금채 AAA",
    "SPB": "공사채 AAA",
    "BD": "은행채 AAA",
    "CB1": "회사채 AAA",
    "CB2": "회사채 AA+",
    "CB3": "회사채 AA",
    "CB4": "회사채 AA-",
    "CB5": "회사채 A",
    "CARD": "카드채 AA+",
    "OFB": "캐피탈채 AA-",
}

#: 테너 — 30Y 는 크레딧에 없다(국고·공사만).
TENORS: list[tuple[str, float]] = [
    ("3M", 0.25), ("6M", 0.5), ("9M", 0.75), ("1Y", 1.0), ("1.5Y", 1.5),
    ("2Y", 2.0), ("2.5Y", 2.5), ("3Y", 3.0), ("5Y", 5.0), ("7Y", 7.0),
    ("10Y", 10.0), ("20Y", 20.0),
]

_COL = {t: c for c, t, _y in cm.TENOR_COLS}

#: 자기이력 창(영업일). 제품의 52주와 같은 눈금이다.
WINDOW = 252
#: 창 안 최소 관측 — 이보다 얇으면 z 를 안 낸다(지어낸 z 는 숫자처럼 보이는 잡음).
MIN_OBS = 200
#: ★분모 바닥(bp). 스프레드가 2bp 인 날 `s` 로 나누면 그 칸 하나가 횡단면을 삼킨다
#: (실측: 최소 2~5bp 로 내려가는 칸이 아홉). Barclays 리뷰에서도 탄력성이 floor 에
#: 크게 휘둘렸다(0bp 0.703 ~ 15bp 0.937) — 그래서 **고정하고 화면에 적는다**.
FLOOR_BP = 5.0


class CreditDtsError(RuntimeError):
    """이 화면을 그릴 수 없다."""


def _fetch() -> tuple[list[dt.date], dict[tuple[str, str], list[float | None]]]:
    """민평 금리(%) 전량. 0 은 결측이다(`creditmatrix` 의 그 규약)."""
    cols = ", ".join(_COL[t] for t, _y in TENORS)
    want = list(SECTORS) + ["KTB"]
    rows = mysqldb.read_sql(
        f"SELECT bas_dt, bond_type, {cols} FROM {cm.TABLE} "
        f"WHERE bond_type IN ({', '.join(repr(t) for t in want)}) ORDER BY bas_dt ASC"
    )
    if not rows:
        raise CreditDtsError(f"{cm.TABLE} 에서 행을 읽지 못했습니다.")
    dates: list[dt.date] = []
    seen: set[dt.date] = set()
    grid: dict[tuple[str, str], dict[dt.date, float]] = {}
    for r in rows:
        m = r._mapping
        d = m["bas_dt"]
        if isinstance(d, dt.datetime):
            d = d.date()
        if d not in seen:
            seen.add(d)
            dates.append(d)
        bt = m["bond_type"]
        for tenor, _y in TENORS:
            v = cm.rate_or_none(m[_COL[tenor]])
            if v is None:
                continue
            grid.setdefault((bt, tenor), {})[d] = v
    return dates, {k: [by.get(d) for d in dates] for k, by in grid.items()}


def _z_now(seq: list[float | None], floor: float) -> tuple[float | None, float | None, float | None]:
    """(z, 자기평균, 분모). 창은 **마지막 252자리, 오늘 포함**(제품 `window_vals` 와 같다)."""
    w = [v for v in seq[-WINDOW:] if v is not None]
    now = seq[-1]
    if now is None or len(w) < MIN_OBS:
        return None, None, None
    mu = sum(w) / len(w)
    den = max(now, floor)
    if den <= 0:
        return None, round(mu, 1), None
    return round((now - mu) / den, 3), round(mu, 1), round(den, 1)


def analysis(floor_bp: float = FLOOR_BP) -> dict[str, Any]:
    """오늘의 120칸 — KTB 대비 스프레드와 **DTS z**.

    산술은 **여기 하나**다(§16) — 화면은 읽고 칠하기만 한다.
    """
    dates, g = _fetch()
    if not dates:
        raise CreditDtsError("민평 날짜가 없습니다.")
    items: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for sec, lab in SECTORS.items():
        for tenor, years in TENORS:
            mine = g.get((sec, tenor))
            base = g.get(("KTB", tenor))
            if mine is None or base is None:
                excluded.append({"id": f"{sec}:{tenor}", "label": f"{lab} {tenor}",
                                 "why": "민평에 이 칸이 없어요."})
                continue
            spread = [None if a is None or b is None else (a - b) * 100.0
                      for a, b in zip(mine, base)]
            now = spread[-1]
            if now is None:
                excluded.append({"id": f"{sec}:{tenor}", "label": f"{lab} {tenor}",
                                 "why": "오늘 값이 없어요."})
                continue
            z, mu, den = _z_now(spread, floor_bp)
            if z is None:
                excluded.append({
                    "id": f"{sec}:{tenor}", "label": f"{lab} {tenor}",
                    "why": f"창 {WINDOW}일 안 관측이 {MIN_OBS}일에 못 미쳐요."})
                continue
            items.append({
                "sector": sec, "sectorLabel": lab, "tenor": tenor, "years": years,
                #: 앵커는 **국고 하나**다 — 행마다 앵커 이름을 적을 이유가 없다.
                "nowBp": round(now, 1),
                "meanBp": mu,
                #: ★분모. 바닥에 걸린 칸은 화면이 그 사실을 적는다.
                "denomBp": den,
                "floored": bool(now < floor_bp),
                "z": z,
                "seriesId": f"DTS-{sec}-{tenor}",
            })

    #: 랭크는 **서버가 센다**(§16). z 큼 = 제 평소보다 벌어짐 = 싸다.
    ranked = sorted(items, key=lambda it: (-it["z"], it["seriesId"]))
    for i, it in enumerate(ranked):
        it["rank"] = i + 1

    return {
        "asof": dates[-1].isoformat(),
        "days": len(dates),
        "window": WINDOW,
        "floorBp": floor_bp,
        "items": items,
        "excluded": excluded,
        #: 화면이 「무엇을 보고 있나」를 지어내지 않게 서버가 말을 쥔다.
        "basis": "국고 대비 스프레드가 제 평소보다 얼마나 벌어졌나 ÷ 지금 스프레드",
    }
