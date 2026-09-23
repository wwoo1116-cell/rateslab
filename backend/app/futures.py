# -*- coding: utf-8 -*-
"""국채선물·퓨처스왑 백테스트 엔진 [OWNER, 2026-08-25 — "선물이랑 선물스왑도
백테스트와 시뮬레이션에 추가하기"].

── 데이터 ──────────────────────────────────────────────────────────────────
`sim_portfolio.mkt_futures_investor_close` — KTB 3Y/10Y 연결(최근월물) 종가,
2016-01-04 부터. MR 세입자(app/mr.py)가 먼저 검증해 쓰는 그 표다. **연결
계열의 롤오버 갭 병은 실측으로 없다** (2026-08-25: 결제월 롤 주간의 일중
|Δ내재| 분포가 평상일과 통계적으로 동일 — 3Y 평균 3.19bp/3.05bp·p95
9.05/9.16, 최대 점프는 전부 시장 스트레스 실제 날짜) — 종가 변화를 그대로
손익으로 세도 된다. 캐시는 creditmatrix 와 같은 규율(워터마크 키).

── 상품과 방향 ────────────────────────────────────────────────────────────
    FUT:3Y / FUT:10Y   국채선물 아웃라이트. +1 = **매수**(가격 롱 — 금리가
                       내리면 이득). 손익 = 방향 × 액면/100 × Δ종가.
                       현금결제(CTD 없음)·연결 계열이라 만기 롤오프가 없고,
                       캐리·조달·롤다운은 존재하지 않는 성분이다(공란 정책;
                       근거는 futures_pricing 모듈 doc — 합성채는 늙지 않는다).
    FSW:3Y / FSW:10Y   퓨처스왑 = 같은 만기 IRS − 선물 내재금리 [OWNER,
                       2026-08-25 — "3선이면 3년 IRS, 10선이면 10년 IRS" ·
                       ★부호 규약 2026-09-22 — "스왑 - 채권현물 또는 국채선물"].
                       +1 = 호가값(스프레드) 롱 = **IRS 페이 + 선물 매수**
                       (IRS↑ 에서 이득 + 내재↓ = 선물 가격↑ 에서 이득).
                       ⚠ 2026-09-22 에 **뜻이 뒤집혔다** — 같은 `+1` 이 종전에는
                       선물 매도·IRS 리시브였다. 계열 부호를 뒤집으면서 다리도
                       같이 뒤집어야 「+1 = 스프레드 확대」가 계속 참이 된다.
                       두 다리는 진입일 DV01 중립으로 가중한다 — 엔진이
                       스프레드·플라이에 이미 쓰는 규칙(_build_legs)과 같다.
                       IRS 다리는 스왑 엔진(_run_one) 그대로다: 엔진을 새로
                       쓰지 않는다(mixedbook 의 그 규칙).

── 대사 ────────────────────────────────────────────────────────────────────
선물 대사표는 스왑 표와 같은 모양(전일 KRD × Δ내재 = est, 실측과의 차 =
잔차)이되, 캐리·롤다운·개시 열이 없다 — 잔차가 싣는 것은 컨벡시티다(추정은
선형 KRD, 실측은 실제 가격). FSW 의 IRS 다리는 **스왑 대사표에** 선다(자기
달력 위 자기 엔진 — 엔진 단위 분리 [OWNER, 2026-08-25]).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import text

from irs_pricer.services.simulation.futures_pricing import (
    FUT_YEARS,
    implied_yield,
    synth_pvbp,
)

from .backtest import (
    MAX_POINTS,
    RECON_MAX_DAYS,
    BacktestError,
    Position,
    _build_legs,
    _index_on_or_after,
    _index_on_or_before,
    _run_one,
    _span_of,
    _thin,
)
from .backtest import book_recon as swap_book_recon
from .engine_port import next_kr_business_day
from .mysqldb import engine

KIND_FUT = "FUT"
KIND_FSW = "FSW"
FUT_TENORS: tuple[str, ...] = ("3Y", "10Y")

#: 표의 ktb_type ↔ 화면 라벨. MR 세입자의 용어(«KTB3 내재금리»·«퓨처스왑 3Y»)
#: 와 같은 계열이다 — 용어 동결.
FUT_LABELS = {"3Y": "KTB3 선물", "10Y": "KTB10 선물"}
FSW_LABELS = {"3Y": "퓨처스왑 3Y", "10Y": "퓨처스왑 10Y"}


class FuturesError(Exception):
    """선물 백테스트를 실행할 수 없다 — 라우트가 422 로 옮긴다."""


#: 벤더 표 — 계약별 종가와 **그 벤더가 낸 내재금리**. 조정가 표와 달리 2012 부터다.
VENDOR_TABLE = {"3Y": "infomax.daily_ktb_price", "10Y": "infomax.daily_lktb_price"}

#: 벤더 종가를 «거래 가능한 가격» 으로 화면에 실을지 가르는 문턱(가격점).
#: 그 종가가 같은 행의 벤더 내재금리와 폐형으로 맞는 날만 싣는다 — 둘이 어긋난
#: 날에 나란히 적으면 한 줄이 서로 다른 두 수를 말한다. 근거는 실측이다
#: (FUTURES_LANE_STATE §Phase 1 항목 2): 10Y 는 전 구간 잔차 중앙 0.002~0.003,
#: 3Y 는 2012 년 5.110 에서 2026 년 0.001 로 수렴한다. 0.10 은 그 둘을 가르는
#: 자리이고, 못 싣는 날은 «가격 없음» 으로 정직하게 빈다.
PRICE_RECONCILE_TOL = 0.10


@dataclass(frozen=True)
class FuturesSeries:
    """한 테너의 세 계열 — **역할이 이름에 있다.**

    ── 이 구분이 왜 있는가 [OWNER, 2026-08-25] ────────────────────────────────
    `mkt_futures_investor_close.CLOSE` 는 **뒤로 조정된 연속 계열**이다(실측:
    분기 롤마다 상수 오프셋이 계단으로 바뀌고 현재 계약에서 0 — KTB3 41 구간·
    KTB10 43 구간). 그런 계열은 **차분에는 정확하고**(그게 존재 이유다 — 롤갭이
    없다) **수준에는 무의미하다**. 그런데 그 위에서 내재금리를 역산하고 있었고,
    벤더 값 대비 중앙 28.5bp(10Y)·89.5bp(3Y), 최대 182bp 까지 틀렸다.

    폐형 산술은 옳다 — 현재 계약에서 벤더와 ±0.05bp 로 맞는다. 틀린 것은
    **입력**이었다. 그래서 규약을 이름으로 못 박는다:

        price_adj   조정가. **차분에만** 쓴다(손익·일별 변화). 절대 역산 금지.
        implied     벤더 `선물내재수익률`. **수준·스프레드·백분위·표시**는 전부
                    이것이다. 유도하지 않고 읽는다 — `universe.py` 가 저평가에
                    대해 이미 적어 둔 그 규칙("read, not derived")과 같다.
        price_ctr   벤더 계약별 종가. 화면에 «그날 거래된 가격» 으로 실을 수 있는
                    유일한 것. `implied` 와 폐형으로 안 맞는 날은 None 이다.

    `guards`(test_futures.py::TestNoInversionOfAdjusted)가 `price_adj` 를
    역산하는 코드가 다시 생기면 실패한다.
    """

    dates: list[dt.date]
    price_adj: list[float]
    implied: list[float | None]
    price_ctr: list[float | None]


@dataclass(frozen=True)
class FuturesData:
    series: dict[str, FuturesSeries]     # tenor → 세 계열
    watermark: tuple[str, int]


# ── 적재 (creditmatrix 와 같은 규율: 워터마크 키 캐시 + 테스트 주입) ────────

_cached: FuturesData | None = None
_injected: FuturesData | None = None


def set_data(data: FuturesData | None) -> None:
    """테스트 주입 시임 — irsdata.set_dataset 과 같은 규율. None 이면 해제."""
    global _injected
    _injected = data


def watermark() -> tuple[str, int]:
    with engine().connect() as conn:
        row = conn.execute(text(
            "SELECT MAX(deal_date), COUNT(*) FROM mkt_futures_investor_close "
            "WHERE CLOSE IS NOT NULL"
        )).one()
    return (str(row[0]), int(row[1]))


def _fetch() -> FuturesData:
    """조정가(차분용) + 벤더 내재금리·계약별 종가(수준용)를 한 번에.

    달력은 **조정가 표**가 진다 — 손익이 그 위에서 나므로 그 날짜들이 곧 이
    상품의 거래일이다. 벤더 표는 2012 부터라 더 길지만, 조정가가 없는 날은
    손익을 셀 수 없어 여기서는 버린다(그 이력을 쓰려면 별도 판단이 필요하다).
    벤더 값은 날짜로 붙인다 — 두 표의 행 순서를 믿지 않는다.
    """
    from irs_pricer.services.simulation.futures_pricing import synth_price

    with engine().connect() as conn:
        rows = conn.execute(text(
            "SELECT deal_date, ktb_type, CLOSE FROM mkt_futures_investor_close "
            "WHERE CLOSE IS NOT NULL ORDER BY deal_date ASC"
        )).fetchall()
        vendor: dict[str, dict[dt.date, tuple[float, float]]] = {}
        for tenor, tbl in VENDOR_TABLE.items():
            vrows = conn.execute(text(
                f"SELECT 일자, 종가, 선물내재수익률 FROM {tbl} "
                "WHERE 종가 IS NOT NULL AND 선물내재수익률 IS NOT NULL"
            )).fetchall()
            vendor[tenor] = {
                (d.date() if hasattr(d, "date") else d): (float(p), float(y))
                for d, p, y in vrows
            }

    series: dict[str, tuple[list[dt.date], list[float]]] = {t: ([], []) for t in FUT_TENORS}
    for d, typ, close in rows:
        if typ not in series or close is None:
            continue
        ds, cs = series[typ]
        ds.append(d.date() if hasattr(d, "date") else d)
        cs.append(float(close))

    out: dict[str, FuturesSeries] = {}
    for t, (ds, cs) in series.items():
        vt = vendor.get(t, {})
        years = FUT_YEARS[t]
        imp: list[float | None] = []
        ctr: list[float | None] = []
        for d in ds:
            hit = vt.get(d)
            if hit is None:
                imp.append(None)
                ctr.append(None)
                continue
            p_v, y_v = hit
            imp.append(y_v)
            # 그 종가가 같은 행의 내재금리와 폐형으로 맞는 날만 «가격» 으로 싣는다.
            ctr.append(p_v if abs(p_v - synth_price(y_v, years)) <= PRICE_RECONCILE_TOL else None)
        out[t] = FuturesSeries(dates=ds, price_adj=cs, implied=imp, price_ctr=ctr)

    return FuturesData(series=out, watermark=watermark())


def load() -> FuturesData:
    """주입본이 있으면 그것, 없으면 SQL(워터마크 키 캐시)."""
    if _injected is not None:
        return _injected
    global _cached
    wm = watermark()
    if _cached is None or _cached.watermark != wm:
        _cached = _fetch()
    return _cached


def reset_cache() -> None:
    global _cached
    _cached = None


# ── id 문법 ─────────────────────────────────────────────────────────────────

def is_futures(series_id: str) -> bool:
    return series_id.startswith((f"{KIND_FUT}:", f"{KIND_FSW}:"))


def parse_id(series_id: str) -> tuple[str, str]:
    """`FUT:3Y` → ("FUT", "3Y"). 모르는 꼴은 422 감."""
    parts = series_id.split(":")
    if len(parts) != 2 or parts[0] not in (KIND_FUT, KIND_FSW) or parts[1] not in FUT_TENORS:
        raise FuturesError(f"unknown instrument {series_id!r}")
    return parts[0], parts[1]


@dataclass(frozen=True)
class FuturesPosition:
    kind: str          # FUT | FSW
    tenor: str         # 3Y | 10Y
    direction: int     # +1 = 호가값 롱 (FUT: 매수 / FSW: 스프레드(IRS−선물) 확대)
    notional: float    # 선물 액면 (원)
    entry: dt.date
    exit: dt.date | None = None

    @property
    def id(self) -> str:
        return f"{self.kind}:{self.tenor}"


def as_position(series_id: str, direction: int, notional: float,
                entry: dt.date, exit: dt.date | None) -> FuturesPosition:
    kind, tenor = parse_id(series_id)
    if direction not in (1, -1):
        raise FuturesError("direction must be +1 or -1")
    if notional <= 0:
        raise FuturesError("notional must be positive")
    return FuturesPosition(kind, tenor, direction, notional, entry, exit)


# ── 계열 (화면이 읽는 히스토리) ─────────────────────────────────────────────

#: 호가 단위(가격 포인트). KTB 선물은 3년·10년 모두 0.01 이다.
TICK = 0.01


def dv01_of(notional: float, y: float, tenor: str) -> float:
    """선물 **DV01**(원/bp) — 액면 `notional` 을 수준 `y`(%)에서 들었을 때.

        DV01 = 액면 / 100 x synth_pvbp(y, 만기)

    PVBP 가 **수준의 함수**라 어느 날의 금리로 재는지가 값을 정한다. 이 리포의
    규약은 **진입일 벤더 내재금리**다(`fsw_swap_leg` 의 그 주석 — 조정가 역산으로
    재던 종전 값은 최대 182bp 틀려 헤지 비율까지 어긋났다).
    """
    return (notional / 100.0) * synth_pvbp(y, FUT_YEARS[tenor])


def face_for_dv01(dv01_won: float, y: float, tenor: str) -> float:
    """`dv01_of` 의 **역** — 「원/bp」 노브를 액면으로.

    MR 의 명목은 액면이 아니라 DV01(원/bp)이라(`main._mr_principal_at` 가 BSS 에
    대해 하는 일과 같은 자리) 선물에 태우려면 이 환산이 필요하다. 실측
    2026-09-04: 100만원/bp 는 3Y 에서 진입일에 따라 31.96~34.98억, 10Y 는
    9.67~12.07억이다.
    """
    pvbp = synth_pvbp(y, FUT_YEARS[tenor])
    if pvbp <= 0:
        raise FuturesError(f"{tenor} PVBP 를 셀 수 없습니다 (y={y}).")
    return dv01_won * 100.0 / pvbp


def roll_cost(notional: float) -> float:
    """분기 갈아타기 **한 번**의 비용(원) — 왕복 1틱(0.5틱 편도 x 2)
    [OWNER 2026-09-04 — "0.5틱으로 해두자"].

    ## 연결선물인데 왜 무나

    연결 계열은 **데이터 구조물이지 상품이 아니다.** 셋째 화요일을 넘겨 시장에
    남아 있으려면 실제로 구계약을 팔고 신계약을 사야 한다. 조정가가 빼는 것은
    계약 사이의 **가격 단차**(캘린더 스프레드 수준)이지 그 갈아타기의 **마찰**이
    아니다 — 즉 조정가 차분의 손익은 «공짜로 롤했다고 가정한 포지션» 의 손익이고,
    그 가정의 값이 이 함수다. (모듈 머리의 「롤오버 갭 병은 실측으로 없다」는
    가격 계열이 깨끗하다는 말이지 롤이 공짜라는 말이 아니다.)

    롤을 피하는 길이 더 비싼 것도 근거다: 롤 전 청산·롤 후 재진입은 편도 0.5bp
    왕복이라 0.5틱 왕복보다 3배 비싸다. **0.5틱은 보수적인 값이 아니라 가장 싼
    경로의 값이다.**

    ## bp 가 아니라 틱인 이유

    1틱이 몇 bp 인지가 **수준을 따라 움직인다**(실측: 100만원/bp 포지션에서 3Y 는
    표본 첫날 0.324bp -> 끝날 0.350bp, 10Y 는 0.097 -> 0.121bp). 고정 bp 로 박으면
    6년에 걸쳐 8~25% 조용히 어긋난다. 액면 위에서 재면 저절로 따라간다.
    """
    return notional / 100.0 * TICK


def instrument_label(kind: str, tenor: str) -> str:
    return (FUT_LABELS if kind == KIND_FUT else FSW_LABELS)[tenor]


def implied_at_index(fs: FuturesSeries, i: int, tenor: str) -> float:
    """그 날의 내재금리(%) — **벤더가 낸 값을 읽는다.**

    `price_adj` 를 역산하지 않는다(그건 조정가라 수준이 없다 — 클래스 머리 주석).
    벤더 값이 없는 날은 손익은 셀 수 있어도 «금리» 를 말할 수 없으므로 명문으로
    죽는다 — 조용히 0 이나 근사로 때우면 화면이 없는 사실을 말하게 된다.
    """
    y = fs.implied[i] if 0 <= i < len(fs.implied) else None
    if y is None:
        raise FuturesError(
            f"{tenor} {fs.dates[i] if 0 <= i < len(fs.dates) else '?'}: "
            "벤더 선물내재수익률이 없습니다."
        )
    return y


def implied_on_or_before(fs: FuturesSeries, d: dt.date, tenor: str) -> float:
    return implied_at_index(fs, _index_on_or_before(fs.dates, d), tenor)


def series_payload(fut: FuturesData, dataset, series_id: str, res: str = "full") -> dict:
    """한 선물·퓨처스왑 계열의 전 기간 — `/api/series/{id}` 와 **같은 몸통**.

    ── 왜 이 함수가 생겼나 [OWNER, 2026-08-25] ────────────────────────────────
    백테스트 창의 진입 레벨이 선물 줄에서만 «—» 였고, 커서를 대도 손익이 안
    따라왔다. 원인은 하나였다: 창이 종목 히스토리를 `/api/series/{id}` 로 받는데
    **`FUT:3Y` 는 그 카탈로그에 없어 404** 였다(실측 2026-08-25). 히스토리가
    비면 진입 레벨이 «—» 로 서고, 「종목 추이 ↔ 누적 손익」 한 쌍 중 위 차트가
    아예 안 그려져서 스크러버·리드아웃까지 같이 사라진다. 데이터가 없어서가
    아니라 닿는 길이 없어서였다 — 같은 종가로 시뮬레이션은 이미 내재금리를
    찍고 있었다.

    `cashbond.series_for` 와 같은 규율이다: 몸통은 `derive.series_history` 를
    쓴다. 같은 차트 부품이 먹을 모양이어야 하기 때문이다(점마다 전일 대비 `d`,
    52주 min/max/avg).

    ── 두 단위를 한 번에 [OWNER 선택, 2026-08-25 — "가격 + 내재금리 둘 다"] ──
    선물은 **가격으로 거래되고 금리로 읽힌다**. 둘 중 하나만 실으면 한쪽 화면이
    딴 말을 한다(Main 국채선물 행은 「가격」 단위이고 백테스트 결과 줄은 이미
    내재금리로 적는다). 그래서 `points` 는 가격이고, 점마다 `y` 에 그 날의
    내재금리를 같이 싣는다 — 진입 레벨 칸이 두 줄로 그 둘을 적는다.
    다운샘플(res=preview)을 지나도 어긋나지 않게 **날짜로** 맞춘다.

    퓨처스왑은 가격이 아니라 **스프레드**(IRS − 내재, bp)라 `y` 가 없다. 그
    다리 결합은 MR 보드(`app/mr.py::_fut_bundle`)와 같은 정의이고, 같은 inner
    join 규율이다 — 양쪽 다 마킹이 있는 날만, 보간·이월 없음.
    """
    from .derive import series_history
    from .payloads import series_pairs

    kind, tenor = parse_id(series_id)
    fs = fut.series.get(tenor)
    if fs is None or not fs.dates:
        raise FuturesError(f"{tenor} 선물 종가가 없습니다.")
    years = FUT_YEARS[tenor]

    if kind == KIND_FUT:
        # **수준 계열은 내재금리다** — 조정가는 차분에만 쓴다(클래스 머리 주석).
        # 첫 줄에 적을 «거래된 가격» 은 벤더 계약별 종가이고, 그 종가가 같은
        # 행의 내재금리와 안 맞는 날은 None 으로 빈다(PRICE_RECONCILE_TOL).
        pairs = []
        plut: dict[str, float | None] = {}
        for d, y, pc in zip(fs.dates, fs.implied, fs.price_ctr):
            if y is None:
                continue
            t = d.isoformat()
            pairs.append((t, round(y, 4)))
            plut[t] = pc
        unit = "%"
        ylut = None
    else:
        # IRS 다리는 데이터셋의 그 테너 — 엔진이 다리를 세울 때 읽는 것과
        # 같은 출처다(두 번째 정의 금지).
        irs_pairs, _u = series_pairs(dataset, tenor)
        irs_by = dict(irs_pairs)
        pairs = []
        plut = None
        for d, y in zip(fs.dates, fs.implied):
            if y is None:
                continue
            t = d.isoformat()
            leg = irs_by.get(t)
            if leg is None:
                continue
            pairs.append((t, round((float(leg) - y) * 100.0, 4)))
        unit = "bp"
        ylut = None
    if not pairs:
        raise FuturesError(f"{series_id}: 그릴 수 있는 날이 없습니다.")

    body = series_history(pairs, unit, res)
    if plut is not None:
        # `p.v` 는 내재금리(%), `p.price` 는 그날 거래된 계약 가격(없으면 null).
        # 다운샘플을 지나도 어긋나지 않게 **날짜로** 맞춘다.
        for p in body["points"]:
            p["price"] = plut.get(p["t"])
    return {
        "id": series_id,
        "label": instrument_label(kind, tenor),
        "asof": pairs[-1][0],
        # 52주 통계·백분위는 이제 내재금리 위에서 난다 — **롤 불연속을 그대로
        # 담고 있다**(실측: KTB3 중앙 5.70bp·최대 27.2bp, KTB10 3.40/16.3bp).
        # 매끄럽게 만들거나 이어붙이지 않는다. 읽는 사람이 알도록 문구를 준다.
        "levelNote": "롤 시점 불연속 포함",
        **body,
    }


def _third_tuesday(year: int, month: int) -> dt.date:
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(1 - d.weekday()) % 7)   # 그 달 첫 화요일
    return d + dt.timedelta(days=14)


def roll_days(dates: list[dt.date]) -> set[dt.date]:
    """계약이 갈리는 **거래일** — 분기월(3·6·9·12)의 셋째 화요일, 휴장이면 그
    직전 거래일.

    ## 왜 필요한가 [OWNER 2026-09-02 — "롤일 Δ 를 0 으로 마스크"]

    MR 의 선물·퓨처스왑 손익은 **벤더 내재수익률의 차분** 위에 선다. 내재는
    «수준»의 정본이지만(이 파일 머리의 규약) 계약이 갈리는 날의 차분은
    **거래할 수 없는 값**이다 — 앞 계약의 마지막 값과 뒷 계약의 첫 값을 뺀
    것이라 아무도 그 손익을 실현하지 못한다. 실측(2026-09-02 적대 대사):
    FUT 거래 109건 중 35건이 >1bp 팬텀, 최대 25.6bp/거래.

    ## 왜 달력인가 — 가격으로 못 잡는 날이 있다

    `price_adj`(조정가, 롤갭 없음)와 `price_ctr`(계약별 종가, 롤갭 있음)의
    차분이 갈리는 날을 잡는 것이 직접적이지만, `price_ctr` 은 폐형이 안 맞는
    날 `None` 이라 **3Y 는 43번의 롤 중 4번만** 잡힌다. 달력은 전부 잡는다.

    실측 대조(2026-09-02): 가격으로 탐지된 롤(3Y 4건·10Y 40건)이 **전부** 이
    달력의 부분집합이다(차집합 0). 롤일의 내재 Δ 크기도 이 파일이 이미 적어
    둔 값과 같다 — 3Y 중앙 5.7bp·최대 27.2bp, 10Y 3.4/16.3bp.

    휴장 보정이 실재한다: 2021-09-17·2024-09-13 은 셋째 화요일이 추석 연휴라
    만기가 앞당겨진 해다. 「셋째 화요일 **이하** 마지막 거래일」이 그 둘을
    포함해 43/43 을 맞춘다.
    """
    if not dates:
        return set()
    lo, hi = min(dates), max(dates)
    out: set[dt.date] = set()
    for y in range(lo.year, hi.year + 1):
        for m in (3, 6, 9, 12):
            t3 = _third_tuesday(y, m)
            # 만기가 자료 밖이면 그 롤은 **아직 안 일어났다**. 이 가드가 없으면
            # `max(prior)` 가 마지막 거래일을 집어 분기월이 아닌 날을 롤이라고
            # 말한다(시험이 잡은 자리 — 자료 끝이 분기 만기보다 앞설 때).
            if not lo <= t3 <= hi:
                continue
            prior = [d for d in dates if d <= t3]
            if prior:
                out.add(max(prior))
    return out


# ── 달력 ────────────────────────────────────────────────────────────────────

def calendar_of(fut: FuturesData, dataset, pos: FuturesPosition) -> list[dt.date]:
    """포지션이 사는 날짜들. FUT 는 그 테너의 선물 달력, FSW 는 선물 ∩ IRS
    (양쪽 다 마킹이 있는 날만 — MR 의 inner join 규율: 보간·이월 없음)."""
    fs = fut.series.get(pos.tenor)
    if fs is None or not fs.dates:
        raise FuturesError(f"{pos.tenor} 선물 종가가 없습니다.")
    if pos.kind == KIND_FUT:
        return fs.dates
    dset = set(dataset.dates)
    return [d for d in fs.dates if d in dset]


def _span_on(cal: list[dt.date], pos: FuturesPosition) -> tuple[int, int]:
    """(entry_i, exit_i) — 스왑 엔진과 같은 스냅(진입은 다음 거래일로,
    청산은 이전 거래일로). 연결 계열이라 만기 캡은 없다(FSW 는 호출부가
    스왑 다리의 만기로 따로 캡한다)."""
    try:
        entry_i = _index_on_or_after(cal, pos.entry)
        exit_i = _index_on_or_before(cal, pos.exit) if pos.exit else len(cal) - 1
    except BacktestError as exc:
        raise FuturesError(f"{pos.id}: {exc}")
    if exit_i < entry_i:
        raise FuturesError(f"{pos.id}: the exit date must not precede the entry date")
    return entry_i, exit_i


# ── FSW 의 IRS 다리 ────────────────────────────────────────────────────────

def fsw_swap_leg(
    fut: FuturesData, dataset, pos: FuturesPosition
) -> tuple[Position, float, float]:
    """(IRS 다리 Position, 진입 내재금리 %, 선물 DV01 원/bp).

    다리 규칙 [OWNER, 2026-08-25]: 같은 만기 IRS, 진입일 DV01 중립.
    ★2026-09-22 규약 뒤집기: 스프레드가 `IRS − 선물` 이므로
    +1(스프레드 롱) = **IRS 페이** = Position.direction **+1** (스왑 엔진의 +1 이
    호가 롱 = 페이). 명목 = 선물 DV01 / 스왑 단위 DV01. run 과 recon 이 같은
    함수를 불러 같은 다리를 얻는다 — 두 번째 정의 금지.
    """
    cal = calendar_of(fut, dataset, pos)
    entry_i, _exit_i = _span_on(cal, pos)
    entry_date = cal[entry_i]
    fs = fut.series[pos.tenor]
    # 진입 내재금리는 **벤더 값을 읽는다** — 조정가 역산이 아니다. DV01 산정이
    # 이 금리에 달려 있어서, 종전 값(최대 182bp 오차)은 헤지 비율까지 틀렸다.
    y0 = implied_at_index(fs, fs.dates.index(entry_date), pos.tenor)
    fut_dv01_won = dv01_of(pos.notional, y0, pos.tenor)

    j = _index_on_or_after(dataset.dates, entry_date)
    if dataset.dates[j] != entry_date:
        # calendar_of 의 FSW 달력은 ∩ 라 여기 못 온다 — 방어만.
        raise FuturesError(f"{pos.id}: {entry_date} 에 IRS 마킹이 없습니다.")
    unit_dv01 = _build_legs(dataset, pos.tenor, 1.0, j)[0].dv01
    if unit_dv01 <= 0:
        raise FuturesError(f"{pos.id}: 스왑 DV01 을 셀 수 없습니다.")
    # `Leg.dv01` 은 연금계수다(pv01 — 명목 1 의 1bp 가 아니라 ×10⁴ 스케일):
    # 실제 원/bp = dv01 × 명목 × 1e-4 (백테스트 창의 표시식이 그 규약의 핀).
    # 처음 이 나눗셈에 1e-4 가 없어 스왑 다리가 10⁴배 작게 섰다 — 실측
    # 2026-08-25: 100억 FSW 의 IRS 다리가 100만원. 그 결함이 이 주석의 이유다.
    swap_notional = fut_dv01_won / (unit_dv01 * 1e-4)
    swap_pos = Position(
        series_id=pos.tenor,
        direction=pos.direction,
        notional=swap_notional,
        entry=entry_date,
        exit=pos.exit,
    )
    return swap_pos, y0, fut_dv01_won


# ── 실행 ────────────────────────────────────────────────────────────────────

def run_one(
    fut: FuturesData,
    dataset,
    pos: FuturesPosition,
    sample_dates: list[dt.date],
    cache: dict | None = None,
) -> tuple[dict, dict[dt.date, float], dict[dt.date, float]]:
    """한 줄: (record, 날짜→손익, 날짜→전거래일 손익).

    스왑 엔진의 (rec, own, prev) 프로토콜을 날짜 키로 든다 — 혼합 병합이
    달력이 다른 엔진들을 날짜로 합치기 때문이다. `prev` 의 "전거래일" 은
    **자기 달력**의 전 거래일이다(병합의 갭 판정이 이 사실을 쓴다).
    """
    cal = calendar_of(fut, dataset, pos)
    entry_i, exit_i = _span_on(cal, pos)
    fs = fut.series[pos.tenor]
    idx_of = {d: i for i, d in enumerate(fs.dates)}
    years = FUT_YEARS[pos.tenor]

    # 표본 날짜와, 자기 달력의 전 거래일들(아래 prev 가 묻는 날들) — 스왑
    # 다리 시리즈가 이 전부를 답할 수 있어야 한다(빠지면 조용한 0).
    ask_dates = set(sample_dates)
    for d in sample_dates:
        if d >= cal[0]:
            i = _index_on_or_before(cal, d)
            if i >= 1:
                ask_dates.add(cal[i - 1])

    swap_rec = None
    swap_ser: dict[int, float] = {}
    fut_dir = pos.direction
    if pos.kind == KIND_FSW:
        # 스프레드(IRS − 선물) 롱 = 선물 **매수** (+ IRS 페이 — 아래 스왑 엔진
        # 위임). 2026-09-22 규약 뒤집기 전에는 여기가 `-pos.direction` 이었다.
        fut_dir = pos.direction
        swap_pos, y0, _dv = fsw_swap_leg(fut, dataset, pos)
        _s_entry, s_exit, _m = _span_of(dataset, swap_pos)
        # 스왑 다리가 만기로 끝나면 선물 다리도 그 마크에서 얼린다 — 안
        # 얼리면 만기 뒤가 벌거벗은 선물이 된다(스프레드가 아닌 것).
        swap_end = dataset.dates[s_exit]
        exit_i = min(exit_i, _index_on_or_before(cal, swap_end))
        ds_sample = sorted({
            _index_on_or_before(dataset.dates, d) for d in ask_dates
            if d >= dataset.dates[0]
        })
        swap_rec, swap_ser, _swap_prev = _run_one(dataset, swap_pos, ds_sample, cache)

    entry_date, exit_date = cal[entry_i], cal[exit_i]
    # 손익은 **조정가의 차분**이다 — 롤갭이 없는 것이 조정 계열의 존재 이유이고,
    # 상수 오프셋은 차분에서 상쇄된다. 여기서 역산하지 않는다.
    p_entry = fs.price_adj[idx_of[entry_date]]

    def fut_pnl_at(d: dt.date) -> float:
        """자기 달력 밖 날짜는 직전 자기 거래일 마크로 — 얼린 값."""
        if d < entry_date:
            return 0.0
        mark = min(d, exit_date)
        i = idx_of.get(mark)
        if i is None:
            k = _index_on_or_before(fs.dates, mark)
            i = k
        return fut_dir * (pos.notional / 100.0) * (fs.price_adj[i] - p_entry)

    def swap_pnl_at(d: dt.date) -> float:
        if swap_rec is None:
            return 0.0
        j = _index_on_or_before(dataset.dates, max(d, dataset.dates[0]))
        return swap_ser.get(j, 0.0)

    own: dict[dt.date, float] = {}
    prev: dict[dt.date, float] = {}
    for d in sample_dates:
        own[d] = fut_pnl_at(d) + swap_pnl_at(d)
        # 자기 달력의 전 거래일 마크.
        i = _index_on_or_before(cal, d) if d >= cal[0] else -1
        if i >= 1:
            pd = cal[i - 1]
            prev[d] = fut_pnl_at(pd) + swap_pnl_at(pd)
        elif i == 0:
            prev[d] = 0.0

    last = own[sample_dates[-1]] if sample_dates else 0.0
    p_exit = fs.price_adj[idx_of[exit_date]]
    # 표시용 금리는 벤더 값 — 손익(위의 p_exit − p_entry)만 조정가로 센다.
    y_entry = implied_at_index(fs, idx_of[entry_date], pos.tenor)
    y_exit = implied_at_index(fs, idx_of[exit_date], pos.tenor)
    fut_leg_pnl = fut_dir * (pos.notional / 100.0) * (p_exit - p_entry)

    legs: list[dict] = [{
        "kind": "fut",
        "tenor": pos.tenor,
        "side": "long" if fut_dir > 0 else "short",
        "notional": round(pos.notional, 0),
        "entryRate": round(y_entry, 4),
        "entryPrice": round(p_entry, 2),
    }]
    if swap_rec is not None:
        for lg in swap_rec["legs"]:
            legs.append({"kind": "irs", **lg})

    record = {
        "id": pos.id,
        "direction": pos.direction,
        "notional": pos.notional,
        "entry": entry_date.isoformat(),
        "exit": exit_date.isoformat(),
        "closed": exit_date < cal[-1],
        # 연결 계열이라 선물 자체는 만기가 없다. FSW 는 스왑 다리 만기에서
        # 얼린다(위) — 그때 matured 를 스왑 다리의 사실로 싣는다.
        "matured": bool(swap_rec and swap_rec.get("matured")),
        "legs": legs,
        # 표시값 = 내재금리(%) — 스왑 아웃라이트의 % 표기와 같은 축.
        # FSW 는 스프레드(bp) = IRS 진입 par − 내재 [부호 규약 2026-09-22].
        "entryValue": round(y_entry, 4) if pos.kind == KIND_FUT else round(
            (swap_rec["legs"][0]["entryRate"] - y_entry) * 100.0, 2
        ),
        "exitValue": round(y_exit, 4) if pos.kind == KIND_FUT else None,
        "pnl": round(last, 0),
        # 성분: 선물 다리는 전부 평가다(캐리·롤·개시 없음 — 모듈 doc). FSW 는
        # 스왑 다리의 4분해가 그대로 얹힌다 — 합이 pnl 로 닫힌다.
        "valuation": round(fut_leg_pnl + (swap_rec["valuation"] if swap_rec else 0.0), 0),
        "carry": swap_rec["carry"] if swap_rec else None,
        "rolldown": swap_rec["rolldown"] if swap_rec else None,
        "startup": swap_rec["startup"] if swap_rec else None,
    }
    # ── 다리별 성분 [OWNER 2026-09-23] ──────────────────────────────────────
    # 퓨처스왑에서 **합쳐지는 것은 평가뿐**이다(위 줄) — 캐리·롤다운·개시는
    # 통째로 스왑 다리 것이고 선물 다리엔 그 성분이 **없다**(합성채는 안 늙는다).
    # 그래서 화면의 「캐리 +x」는 이미 전부 IRS 인데, 합계만 보면 그 사실이
    # 안 보인다. 하루씩은 이미 갈라 보인다(`book_recon(with_legs=True)` 의 버킷).
    #
    # ⚠ 키가 `legs` 가 아니라 `legParts` 인 이유: 이 기록의 `legs` 는 **상품
    #   다리 서술**(만기·방향·명목·진입가)이고 프런트 `BacktestLeg` 가 그것이다.
    #
    # 없는 성분에는 `None` 을 적는다 — 0 을 적으면 「캐리가 0원이었다」는 다른
    # 말이 된다(이 리포의 공란 정책). 조달은 양쪽 다 없다: 선물엔 조달할 원금이
    # 없고 IRS 에도 없다(현물 다리만 진다).
    if pos.kind == KIND_FUT:
        # 선물 아웃라이트 — 다리 하나고 손익이 전부 평가다(합성채는 안 늙는다).
        # 없는 성분엔 공란을 적는다. 혼합 북의 열을 닫으려고 싣는다 [2026-09-23].
        record["legParts"] = [{
            "name": "선물",
            "valuation": record["valuation"],
            "rolldown": None,
            "carry": None,
            "startup": None,
            "funding": None,
            "pnl": record["pnl"],
        }]
    elif swap_rec is not None:
        record["legParts"] = [
            {
                "name": "선물",
                "valuation": round(fut_leg_pnl, 0),
                "rolldown": None,
                "carry": None,
                "startup": None,
                "funding": None,
                "pnl": round(fut_leg_pnl, 0),
            },
            {
                "name": "IRS",
                "valuation": swap_rec["valuation"],
                "rolldown": swap_rec["rolldown"],
                "carry": swap_rec["carry"],
                "startup": swap_rec["startup"],
                "funding": None,
                "pnl": swap_rec["pnl"],
            },
        ]
    return record, own, prev


def run_backtest(fut: FuturesData, dataset, positions: list[FuturesPosition]) -> dict:
    """선물만 있는 북 — 스왑 엔진 run_backtest 와 같은 응답 모양."""
    if not positions:
        raise FuturesError("at least one position is required")

    cals = [calendar_of(fut, dataset, p) for p in positions]
    spans = [_span_on(c, p) for c, p in zip(cals, positions)]
    # 북의 창 = 전체 진입~청산. 공통 달력 = 관련 달력의 교집합(그 창 안).
    starts = [c[a] for c, (a, _b) in zip(cals, spans)]
    ends = [c[b] for c, (_a, b) in zip(cals, spans)]
    lo, hi = min(starts), max(ends)
    common = sorted(set.intersection(*[set(c) for c in cals]))
    window = [d for d in common if lo <= d <= hi]
    if not window:
        raise FuturesError("포지션들이 함께 사는 날짜가 없습니다.")
    idxs = _thin(list(range(len(window))), MAX_POINTS)
    sample_dates = [window[i] for i in idxs]

    cache: dict = {}
    records, owns, prevs = [], [], []
    for p in positions:
        rec, own, prev = run_one(fut, dataset, p, sample_dates, cache)
        records.append(rec)
        owns.append(own)
        prevs.append(prev)

    points = []
    for k, d in enumerate(sample_dates):
        total = round(sum(o[d] for o in owns), 0)
        dd = (
            None if k == 0
            else round(total - sum(pv.get(d, 0.0) for pv in prevs), 0)
        )
        points.append({"t": d.isoformat(), "pnl": total, "d": dd})

    pnls = [p["pnl"] for p in points]
    return {
        "positions": records,
        "from": sample_dates[0].isoformat(),
        "to": sample_dates[-1].isoformat(),
        "complete": len(sample_dates) == len(window),
        "points": points,
        "pnl": pnls[-1] if pnls else 0.0,
        "maxProfit": max(pnls) if pnls else 0.0,
        "maxLoss": min(pnls) if pnls else 0.0,
    }


# ── 대사 ────────────────────────────────────────────────────────────────────

def book_recon(fut: FuturesData, dataset, positions: list[FuturesPosition],
               with_legs: bool = False) -> dict:
    """선물 일별 대사 — {tenors, rows, truncated}. 스왑 표와 같은 관행(행의
    krd 는 est 가 곱한 전일 것), 열은 평가·잔차뿐이다(캐리·롤·개시 = 존재하지
    않는 성분 — None).

    ## `with_legs` — 퓨처스왑을 **하루 일곱 줄**로 [OWNER 2026-09-04]

    끄면 종전 그대로다: FSW 는 **선물 다리만** 여기 서고 IRS 다리는 스왑 표에
    선다(2026-08-25 「엔진 단위 분리」). 켜면 행마다 `legs: [선물, IRS]` 와
    `legTenors` 가 붙어 자산스왑 대사와 같은 모양이 되고 — 다리마다 KRD·Δbp·
    손익 세 줄에 합계 한 줄 — 부르는 쪽은 **스왑 표에서 그 다리를 빼야 한다**
    (`mixedbook.book_recon`). 안 빼면 같은 돈이 두 표에 선다.

    ### 두 달력을 어떻게 한 표에 세우나 — **버킷**이다

    IRS 다리는 IRS 달력 위에서 스왑 엔진이 값매긴다(여기서 다시 가격하지
    않는다 — 두 번째 정의 금지). 그 행들을 선물 달력의 **행마다 하나씩 담는다**:
    선물 행 `d` 의 IRS 다리는 «직전 선물 행 다음부터 `d` 까지» 의 IRS 행 전부다.

    이 규칙이 사는 이유는 **돈이 보존되기 때문**이다. IRS 가 쉰 날의 선물 행은
    IRS 쪽이 0 이고(마킹이 없으니 실현될 것도 없다), 다음 IRS 마킹은 두 밤을
    한 번에 재므로 그 돈이 다음 버킷에 통째로 들어간다. 세로합은 스왑 표에서
    떼어 온 그 다리의 합과 정확히 같다 — 자산스왑 대사가 IRS 다리를 민평
    달력에 얹을 때 쓴 것과 같은 사상이다(`cashbond._leg_delta` 의 `imap`).

    **Δbp 는 그 버킷의 차**다(하루가 아니라 «지난 선물 행 이후»). 버킷 안에서
    KRD 가 움직이면 `KRD × Δbp` 가 `est` 와 미세하게 갈리는데, 그 몫은 잔차
    열에 선다. 버킷에 IRS 행이 둘 이상 드는 날은 드물다(두 달력이 갈리는 날 —
    민평 대 IRS 실측이 12일이었다).
    """
    if not positions:
        raise FuturesError("at least one position is required")

    tenors = [t for t in FUT_TENORS if any(p.tenor == t for p in positions)]
    # 표의 달력 = 관련 테너 선물 달력의 교집합 (FSW 다리 값은 선물 종가만 쓴다).
    cals = []
    for t in tenors:
        fs = fut.series.get(t)
        if fs is None or not fs.dates:
            raise FuturesError(f"{t} 선물 종가가 없습니다.")
        cals.append(fs.dates)
    common = sorted(set.intersection(*[set(c) for c in cals]))
    if not common:
        raise FuturesError("선물 달력이 비었습니다.")

    # 포지션 준비: 자기 달력 위 스팬 → 공통 달력으로 옮긴다.
    infos = []
    first_d, last_d = None, None
    for p in positions:
        cal = calendar_of(fut, dataset, p)
        a, b = _span_on(cal, p)
        if p.kind == KIND_FSW:
            swap_pos, _y0, _dv = fsw_swap_leg(fut, dataset, p)
            _sa, s_exit, _m = _span_of(dataset, swap_pos)
            b = min(b, _index_on_or_before(cal, dataset.dates[s_exit]))
        fs = fut.series[p.tenor]
        # 2026-09-22 규약 뒤집기 뒤로 FSW 도 선물 다리가 **같은 부호**다
        # (`IRS − 선물` 확대 = 선물 매수) — `run_one` 의 `fut_dir` 과 한 문장.
        fut_dir = p.direction
        open_end = p.exit is None and cal[b] == cal[-1]
        infos.append({
            "pos": p, "fs": fs, "dir": fut_dir,
            "entry_d": cal[a], "exit_d": cal[b], "open_end": open_end,
        })
        first_d = cal[a] if first_d is None else min(first_d, cal[a])
        last_d = cal[b] if last_d is None else max(last_d, cal[b])

    window = [d for d in common if first_d <= d <= last_d]
    start = max(0, len(window) - RECON_MAX_DAYS)
    rows: list[dict] = []
    years = {t: FUT_YEARS[t] for t in tenors}

    def level_at(fs: FuturesSeries, i: int, t: str) -> float:
        """PVBP 를 세울 **수준**(%). 그날 벤더 값이 없으면 **직전 값으로 잇는다.**

        `implied_at_index` 는 값이 없으면 명문으로 죽는다 — 「금리」를 물었는데
        없으면 지어내지 말라는 규약이고 그건 옳다. 그런데 여기서 쓰는 것은 금리
        자체가 아니라 **PVBP 의 인자**이고, PVBP 는 수준의 완만한 함수다(3Y 는
        6년에 걸쳐 0.0311 -> 0.0286). 하루를 잇는 오차보다 **표 전체가 죽는 쪽이
        훨씬 나쁘다** — 실측 2026-09-04: 벤더 두 표에 2019-02-15 가 없어서
        FSW-10Y 의 거래 하나가 못 서고, 「한 건이라도 못 재면 전부 안 바꾼다」는
        회계 규칙에 걸려 **그 계열 67거래가 통째로 옛 근사로 떨어졌다.**

        Δbp 는 잇지 않는다 — 그건 **변화**라 지어내면 없는 사실을 말하는 것이다
        (아래 `vendor_at`, 공란 정책).
        """
        j = i
        while j >= 0 and fs.implied[j] is None:
            j -= 1
        if j < 0:
            raise FuturesError(f"{t}: {fs.dates[i]} 앞에 벤더 내재금리가 없습니다.")
        return fs.implied[j]

    def vendor_at(fs: FuturesSeries, i: int) -> float | None:
        """그날 **벤더가 실제로 낸** 값. 없으면 None — 이으면 안 되는 자리용."""
        return fs.implied[i] if 0 <= i < len(fs.implied) else None

    # ── IRS 다리 — **스왑 엔진의 표를 받아** 선물 행에 버킷으로 담는다 ──────
    fsw = [p for p in positions if p.kind == KIND_FSW]
    want_legs = bool(with_legs and fsw)
    swap_labels: list[str] = []
    #: 선물 행 날짜 → 그 버킷에 든 IRS 행들
    bucket: dict[dt.date, list[dict]] = {d: [] for d in window}
    swap_anchor: dict[str, float] = {}
    if want_legs:
        swap_pos = [fsw_swap_leg(fut, dataset, p)[0] for p in fsw]
        swap_rec = swap_book_recon(dataset, swap_pos, with_krd=True)
        # 열은 **그 다리가 실제로 흔든 노드**만 — 전 노드를 세우면 스왑 표의
        # 열 목록(TENOR_T 전부)이 통째로 따라와 빈 칸이 스무 개 선다.
        seen: set[str] = set()
        for r in swap_rec["rows"]:
            for lb, v in (r.get("krd") or {}).items():
                if v:
                    seen.add(lb)
        swap_labels = [lb for lb in swap_rec["tenors"] if lb in seen]
        lo = window[start - 1] if start > 0 else None
        for r in swap_rec["rows"]:
            rd = dt.date.fromisoformat(r["t"])
            if r.get("carryover"):
                # 이월 앵커는 «내일 아침 리스크» 라 돈이 없다 — 선물 표의
                # 이월 앵커에 KRD 만 얹는다.
                swap_anchor = {lb: v for lb, v in (r.get("krd") or {}).items()
                               if lb in swap_labels}
                continue
            if lo is not None and rd <= lo:
                continue                      # 잘린 창 앞 — 표가 truncated 라 말한다
            j = _index_on_or_after(window, rd)
            # 마지막 선물 행보다 뒤인 IRS 행은 **마지막 행에** 담는다. 버리면
            # 세로합이 그만큼 스왑 표와 갈린다.
            key = window[j] if j < len(window) and window[j] >= rd else window[-1]
            if key < window[start]:
                key = window[start]
            bucket[key].append(r)

    prev_krd = {t: 0.0 for t in tenors}
    for k in range(max(start - 1, 0), len(window)):
        d = window[k]
        krd = {t: 0.0 for t in tenors}
        day_val = 0.0
        for info in infos:
            if d < info["entry_d"] or d > info["exit_d"]:
                continue
            fs, t = info["fs"], info["pos"].tenor
            i = _index_on_or_before(fs.dates, d)
            # 평가(백워드): 진입일 행은 0 (그날 종가로 struck — 스왑 표 규칙).
            # **차분**이라 조정가가 맞다.
            if d > info["entry_d"]:
                p_prev = fs.price_adj[max(i - 1, 0)]
                day_val += info["dir"] * (info["pos"].notional / 100.0) * (fs.price_adj[i] - p_prev)
            # KRD (내일 아침 들고 갈 리스크): 청산 마크면 0 — 스왑 표 규칙.
            # PVBP 는 **수준**에 달렸으므로 벤더 내재금리를 읽는다.
            alive_fwd = d < info["exit_d"] or (d == window[-1] and info["open_end"])
            if alive_fwd:
                y = level_at(fs, i, t)
                krd[t] += info["dir"] * (info["pos"].notional / 100.0) * synth_pvbp(y, years[t])

        if k >= start:
            dbp: dict[str, float | None] = {}
            est: dict[str, float] = {}
            for t in tenors:
                fs = fut.series[t]
                i = _index_on_or_before(fs.dates, d)
                cur, prv = vendor_at(fs, i), vendor_at(fs, i - 1) if i >= 1 else None
                if cur is not None and prv is not None:
                    # 두 **수준**의 차다. 조정가 역산의 차로 내면 상수 오프셋이
                    # 비선형을 지나 안 상쇄된다 — 벤더 값의 차로 낸다.
                    # 롤일에는 계약이 바뀌므로 여기 Δbp 가 진짜로 튄다(실측
                    # KTB3 중앙 5.70bp·최대 27.2bp). 그건 사실이라 안 지운다.
                    dy = (cur - prv) * 100.0
                    dbp[t] = round(dy, 2)
                    est[t] = -prev_krd[t] * dy
                else:
                    # 한쪽이라도 벤더 값이 없으면 **그날 Δ 를 말할 수 없다** —
                    # 0 은 「안 움직였다」는 다른 말이라 안 쓴다(공란 정책).
                    dbp[t] = None
                    est[t] = 0.0
            total_est = round(sum(est.values()))
            row = {
                "t": d.isoformat(),
                "krd": {t: round(prev_krd[t]) for t in tenors},
                "dbp": dbp,
                "est": {t: round(est[t]) for t in tenors},
                "estTotal": total_est,
                "actual": round(day_val),
                "valuation": round(day_val),
                # 존재하지 않는 성분 — 공란 정책 (모듈 doc).
                "carry": None,
                "rolldown": None,
                "startup": None,
                "residual": round(day_val) - total_est,
            }
            if want_legs:
                irs = _bucket_leg(bucket[d], swap_labels)
                row["legs"] = [
                    {
                        "name": "선물",
                        "krd": row["krd"], "dbp": dbp,
                        "est": row["est"], "estTotal": total_est,
                        "actual": round(day_val), "valuation": round(day_val),
                        # 합성채는 만기가 고정이라 캐리·롤다운이 없다(모듈 doc).
                        "carry": None, "rolldown": None, "funding": None,
                        "residual": round(day_val) - total_est,
                    },
                    irs,
                ]
                # 합계 줄은 **두 다리의 합**이다 — 이 표가 이제 FSW 전체를
                # 진다(IRS 다리가 스왑 표에서 빠진다는 계약의 다른 쪽).
                row["estTotal"] = total_est + (irs["estTotal"] or 0)
                row["valuation"] = round(day_val) + (irs["valuation"] or 0)
                row["carry"] = irs["carry"]
                row["rolldown"] = irs["rolldown"]
                row["startup"] = irs["startup"]
                row["actual"] = round(day_val) + (irs["actual"] or 0)
                row["residual"] = row["valuation"] - row["estTotal"]
            rows.append(row)
        prev_krd = krd

    if rows:
        # 이월 앵커 — 종가 KRD. 날짜는 다음 선물 거래일이 데이터 밖이라
        # 달력상 다음 영업일로 적는다(스왑 표와 같은 처리).
        anchor = {
            "t": next_kr_business_day(window[-1]).isoformat(),
            "krd": {t: round(krd[t]) for t in tenors},
            "dbp": {},
            "est": {},
            "estTotal": None,
            "actual": None,
            "valuation": None,
            "carry": None,
            "rolldown": None,
            "startup": None,
            "residual": None,
            "carryover": True,
        }
        if want_legs:
            blank = {"dbp": {}, "est": {}, "estTotal": None, "actual": None,
                     "valuation": None, "carry": None, "rolldown": None,
                     "startup": None, "funding": None, "residual": None}
            anchor["legs"] = [
                {"name": "선물", "krd": anchor["krd"], **blank},
                {"name": "IRS",
                 "krd": {lb: round(v) for lb, v in swap_anchor.items()}, **blank},
            ]
        rows.append(anchor)

    out = {"tenors": tenors, "rows": rows, "truncated": start > 0}
    if want_legs:
        # 표의 열은 두 다리의 **합집합**이다 — 화면이 이것으로 칸을 세운다
        # (자산스왑 대사의 `legTenors` 와 같은 계약).
        out["legTenors"] = [
            {"name": "선물", "tenors": tenors},
            {"name": "IRS", "tenors": swap_labels},
        ]
    return out


def _bucket_leg(rows: list[dict], labels: list[str]) -> dict:
    """선물 행 하나가 지는 **IRS 다리 한 줄** — 그 버킷의 IRS 행들을 접는다.

    돈은 **더한다**(그 버킷에서 실제로 마킹된 밤 전부). KRD 는 버킷의 **첫**
    행 것이다 — 그 행의 «전일 종가 KRD» 가 곧 이 버킷이 시작될 때의 감도이고,
    추정이 곱한 값도 그것이다(표 규약: 한 블록 안에서 KRD × Δbp = 추정).

    Δbp 도 **더한다**. 수준의 차라서 이어 붙이면 그대로 «지난 선물 행 이후의
    변화» 가 된다(a−b + b−c = a−c). 버킷의 어느 행에서도 그 노드를 못 재면
    None 이다 — 0 은 「안 움직였다」는 다른 말이다(공란 정책).

    빈 버킷(IRS 가 쉰 날)은 돈이 0 이고 Δ 는 전부 공란이다. 「그날은 IRS 마킹이
    없었다」가 사실이고, 그 밤의 돈은 다음 버킷이 진다.
    """
    krd = ({lb: (rows[0].get("krd") or {}).get(lb, 0.0) for lb in labels}
           if rows else {lb: 0.0 for lb in labels})
    dbp: dict[str, float | None] = {}
    est: dict[str, float] = {}
    for lb in labels:
        seen = [v for r in rows for v in [(r.get("dbp") or {}).get(lb)]
                if v is not None]
        dbp[lb] = round(sum(seen), 2) if seen else None
        est[lb] = sum((r.get("est") or {}).get(lb, 0.0) for r in rows)

    def _sum(key: str) -> float:
        return sum(r.get(key) or 0.0 for r in rows)

    est_total = round(sum(est.values()))
    val = round(_sum("valuation"))
    return {
        "name": "IRS",
        "krd": {lb: round(v) for lb, v in krd.items()},
        "dbp": dbp,
        "est": {lb: round(v) for lb, v in est.items()},
        "estTotal": est_total,
        "valuation": val,
        "carry": round(_sum("carry")),
        "rolldown": round(_sum("rolldown")),
        # 개시(거래일→발효일 한 밤)는 진입일 행에만 선다 — 스왑 표의 그 칸.
        "startup": round(_sum("startup")),
        # 조달은 현물 다리만 진다 — IRS 에는 조달할 원금이 없다(공란 정책).
        "funding": None,
        "actual": round(_sum("actual")),
        "residual": val - est_total,
    }
