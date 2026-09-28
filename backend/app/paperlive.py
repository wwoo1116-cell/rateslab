# -*- coding: utf-8 -*-
r"""장중 시세 — **지금 화면에 떠 있는 값**을 그대로 [OWNER 2026-09-28].

> "장중에 그러면 CRS IRS 종합이랑 3년국채, 10년국채선물 떠있는거 보고 바로바로
>  입력해주면 안되나? 불가능?"

불가능하지 않다. 그 화면들이 이미 이 데스크의 MySQL 로 흘러들고 있다 —
`infomax_API.irs_infomax`(IRS 전 만기, 초 단위)와 `infomax_API.ktbf_live`(3년·10년
국채선물 연결, 초 단위). 페이퍼 북이 안 보고 있었을 뿐이다(그쪽은 종가 피드를 읽는다).

## 이 모듈이 지는 것 — **읽기와 번역뿐**

값을 어떻게 쓰는지는 `paper.py` 가 안다(장중 레벨은 마크를 덮고 밴드를 다시 세운다).
여기서는 두 표를 읽어 `{(계기, 만기): 금리}` 로 옮긴다. `paper` 가 DB 를 모르는 규율은
그대로다 — 그 모듈은 주입만 받는다.

## 선물은 **가격으로 온다** — 금리는 우리가 푼다

`ktbf_live.implied_yield` 는 이 피드에서 **비어 있다**(실측 2026-09-28: 전부 0.0).
그래서 연결 가격을 리포의 폐형식(`futures_pricing.implied_yield`)으로 푼다 — 화면·
백테스트가 쓰는 그 함수라 두 자리가 같은 금리를 말한다. 표면 5%·반년 복리의 그
정의이고, 벤더 내재금리와 최대 182bp 갈렸던 옛 역산과는 다른 물건이다
(`futures.fsw_swap_leg` 머리의 그 실측).

## 오래된 값을 「지금」이라 적지 않는다

두 표 다 마지막 행의 날·시각을 같이 낸다. 오늘이 아니거나 `MAX_AGE_MIN` 을 넘으면
값을 **안 싣고** 사유를 든다. 장 마감 뒤에 열어 둔 화면이 어제 값을 「지금」으로
적으면, 그 수로 매긴 손익은 그럴듯하게 틀린 수가 된다.

⚠ **국고 현물은 아직 없다.** 지표물 장중은 `infomax_API.ktb_tick`·`hoga_real` 에
종목 단위로 오는데, 만기(3Y·10Y)로 부르려면 지표물 표(`infomax.ontherun_schedule`)를
같이 읽어야 한다. 이 북의 다리가 전부 IRS 라 그 자리는 비워 두고 사유를 적는다 —
안 되는 것을 되는 척하지 않는다.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import text

from irs_pricer.services.simulation.futures_pricing import implied_yield

from .mysqldb import engine

#: 마지막 시세가 이보다 오래되면 「지금」이라 안 부른다(분).
MAX_AGE_MIN = 30

#: 만기 라벨 → `irs_infomax` 의 칸. **1.5Y 는 `irs_18m`** 이다 — 이 표만 개월로
#: 적는다(나머지는 연). 3M 은 이 표에 없다(6M 부터다).
IRS_COL: dict[str, str] = {
    "6M": "irs_6m", "9M": "irs_9m", "1Y": "irs_1y", "1.5Y": "irs_18m",
    "2Y": "irs_2y", "3Y": "irs_3y", "4Y": "irs_4y", "5Y": "irs_5y",
    "6Y": "irs_6y", "7Y": "irs_7y", "8Y": "irs_8y", "9Y": "irs_9y",
    "10Y": "irs_10y", "12Y": "irs_12y", "15Y": "irs_15y", "20Y": "irs_20y",
    "30Y": "irs_30y",
}

#: 선물 연결 코드 → (만기 라벨, 표준물 연수). `futures.FUT_TENORS` 와 같은 둘이다.
FUT_CODE: dict[str, tuple[str, int]] = {"C65": ("3Y", 3), "C67": ("10Y", 10)}


def _hhmmss(v: Any) -> str:
    """`irs_time` 은 `TIME` 이라 `timedelta` 로 온다 — 사람이 읽는 꼴로."""
    if isinstance(v, dt.timedelta):
        s = int(v.total_seconds())
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    return str(v)


def _age_min(day: dt.date, hhmmss: str, now: dt.datetime) -> float | None:
    try:
        h, m, s = (int(x) for x in hhmmss.split(":"))
    except ValueError:
        return None
    at = dt.datetime.combine(day, dt.time(h, m, s))
    return (now - at).total_seconds() / 60.0


def live_marks(*, now: dt.datetime | None = None,
               max_age_min: int = MAX_AGE_MIN) -> dict[str, Any]:
    """지금 시세 — `{"levels": [...], "asof": …, "sources": [...], "why": …}`.

    `levels` 의 한 칸은 `{"kind", "tenor", "level", "at", "source"}` 이고 `paper` 의
    장중 레벨 열쇠(`(계기, 만기)`)와 같은 낱말이다. 한 출처가 죽어도 나머지는 선다 —
    사유는 `sources` 의 그 줄이 진다(rv exclusions 문법).
    """
    now = now or dt.datetime.now()
    out: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []

    with engine().connect() as c:
        # ── IRS (CRS·IRS 종합 화면의 그 줄) ─────────────────────────────────
        src: dict[str, Any] = {"name": "IRS", "table": "infomax_API.irs_infomax"}
        try:
            row = c.execute(text(
                "SELECT * FROM `infomax_API`.`irs_infomax` "
                "ORDER BY irs_date DESC, irs_time DESC LIMIT 1"
            )).mappings().first()
            if row is None:
                src["why"] = "표가 비어 있어요"
            else:
                day, at = row["irs_date"], _hhmmss(row["irs_time"])
                age = _age_min(day, at, now)
                src.update({"asof": f"{day} {at}", "ageMin": None if age is None else round(age, 1)})
                if day != now.date():
                    src["why"] = f"오늘 자료가 아니에요 — 마지막이 {day} {at} 예요"
                elif age is not None and age > max_age_min:
                    src["why"] = f"{round(age)}분 전 값이에요 — 지금이라고 부르지 않아요"
                else:
                    for tenor, col in IRS_COL.items():
                        v = row.get(col)
                        if v is None:
                            continue
                        out.append({"kind": "irs", "tenor": tenor, "level": float(v),
                                    "at": at, "source": "IRS"})
        except Exception as exc:                       # noqa: BLE001 — 사유를 싣고 산다
            src["why"] = f"못 읽었어요: {exc}"
        sources.append(src)

        # ── 국채선물 3년·10년 (연결) ────────────────────────────────────────
        src = {"name": "국채선물", "table": "infomax_API.ktbf_live"}
        try:
            got = c.execute(text(
                "SELECT t.code, t.price, t.deal_date, t.deal_time FROM `infomax_API`.`ktbf_live` t "
                "JOIN (SELECT code, MAX(CONCAT(deal_date,' ',deal_time)) AS mx "
                "      FROM `infomax_API`.`ktbf_live` WHERE code IN ('C65','C67') GROUP BY code) m "
                "  ON m.code = t.code AND CONCAT(t.deal_date,' ',t.deal_time) = m.mx"
            )).fetchall()
            if not got:
                src["why"] = "연결 선물 줄이 없어요"
            else:
                stamps = []
                for code, price, day, at in got:
                    if code not in FUT_CODE or price is None:
                        continue
                    tenor, years = FUT_CODE[code]
                    day = day if isinstance(day, dt.date) else dt.date.fromisoformat(str(day))
                    at = _hhmmss(at)
                    age = _age_min(day, at, now)
                    stamps.append((day, at, age))
                    if day != now.date():
                        continue
                    if age is not None and age > max_age_min:
                        continue
                    # ★가격으로 오므로 금리는 **우리가 푼다** — 화면·백테스트의 그 함수다.
                    out.append({"kind": "fut", "tenor": tenor,
                                "level": round(implied_yield(float(price), years), 4),
                                "at": at, "source": "국채선물"})
                if stamps:
                    day, at, age = max(stamps)
                    src.update({"asof": f"{day} {at}",
                                "ageMin": None if age is None else round(age, 1)})
                    if day != now.date():
                        src["why"] = f"오늘 자료가 아니에요 — 마지막이 {day} {at} 예요"
                    elif age is not None and age > max_age_min:
                        src["why"] = f"{round(age)}분 전 값이에요 — 지금이라고 부르지 않아요"
        except Exception as exc:                       # noqa: BLE001
            src["why"] = f"못 읽었어요: {exc}"
        sources.append(src)

    # 국고 현물은 아직 이 창구에 없다 — 없는 것을 있는 척하지 않는다.
    sources.append({
        "name": "국고 현물", "table": None,
        "why": "지표물 장중은 종목 단위로 와서 만기로 부르려면 지표물 표를 같이 읽어야 해요 — 아직 안 이었어요.",
    })

    asof = max((l["at"] for l in out), default=None)
    why = None if out else " · ".join(
        f'{s["name"]}: {s["why"]}' for s in sources if s.get("why"))
    return {"levels": out, "asof": asof, "sources": sources, "why": why}
