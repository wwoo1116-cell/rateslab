# -*- coding: utf-8 -*-
"""3D 커브 표면 — 국고·크레딧·스왑 3풀, 3M~30Y (Lab, 2026-08-18 / 확장 08-19).

V2-LOCAL. 기존 커브 표면(`surface.py`, IRS 3M~10Y 고정 투영)을 **교체**하는
화면의 페이로드다 [OWNER 2026-08-18 — 설계 4결정 + "회전 가능하게"]. 이 모듈은
값만 만든다 — 투영·회전·보간(PCHIP)은 전부 프론트의 그리기 결정이고, 여기서
나가는 것은 실측 노드뿐이다 (§16).

── 풀과 노드 ─────────────────────────────────────────────────────────────────
    govt          credit_matrix 의 KTB. 3M~30Y 실측 컬럼 12노드(CM_TENORS).
    credit:<T>    같은 테이블의 신용 사다리 6종. 기본 = BD(은행 AAA) [OWNER].
                  통안(MSB)은 3Y까지뿐이라 표면에서 제외. CB2~CB5 도
                  유니버스가 표에서만 다루는 급이라 제외 — 필요하면 한 줄씩.
    swap          `Dataset.series` 의 **호가 8노드** 6M,9M,1,1.5,2,3,5,10.
                  SQL 의 irs_4y·6y~9y 는 업스트림 보간이라 여기 못 들어온다 —
                  표면의 매끄러움이 그 자체로 "여기 값이 있다"는 주장이기
                  때문이고(surface.py 의 같은 판정), 그 위에 프론트가 다시
                  보간하면 이중 보간이다.
    2.5Y(30m)는 universe.py 가 "IRS 짝이 없고 데스크가 호가하지 않는다"로 이미
    버렸다 — 그 판정을 승계한다.

── 시간축 ────────────────────────────────────────────────────────────────────
풀마다 **자기 달력**이다 [OWNER — 풀별 자기 시간축]: 스왑은 2016~, 국고·크레딧은
credit_matrix 가 시작하는 2020-01-02~. **일별이다** [OWNER 2026-08-18 — "우리도
일별 데이터로"]. 전작 표면의 "주별이 기본" 판정은 지워진 히트맵(표)의 소음
얘기였고, 매끈한 면에는 반대로 밀도가 정답이다 — NYT 의 비단결이 일별에서
온다(실측). 능선 2,600장은 WebGL 에겐 공짜다.

── 0 은 결측이다 ─────────────────────────────────────────────────────────────
credit_matrix 는 없는 값을 0.0 으로 채운다. universe._fetch_curves 가 파싱
시점에 None 으로 바꾸고, 이 모듈은 그 뒤만 본다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .dataset import Dataset
from .derive import spread_series
from .mysqldb import engine
from .universe import CURVE_LABEL, _fetch_curves  # noqa: F401 — CM_TENORS 를 넘겨 쓴다

# (컬럼, 라벨, 년수) — 표면 전용의 credit_matrix 파싱 집합 [OWNER 2026-08-19 —
# "3M부터 30까지 데이터 있으면 추가, 없으면 냅두기"]. 실측(2026-08-19, 1,626일
# 전수): 3M·6M·9M·20Y 는 전 발행체 100%, 30Y 는 KTB·SPB 만 100%(은행·카드 등은
# 0 = 구조적 부재 — _pool 이 풀별로 "빠진 값"에 밝히고 뺀다). 2.5Y(rt_30m)는
# 데이터는 있으나 "데스크가 호가하지 않는다"[universe 승계 판정] 그대로 제외.
# 15Y 는 컬럼 자체가 없다. 표의 유니버스(universe.TENORS)는 안 넓힌다.
CM_TENORS: list[tuple[str, str, float]] = [
    ("rt_3m", "3M", 0.25), ("rt_6m", "6M", 0.5), ("rt_9m", "9M", 0.75),
    ("rt_1y", "1Y", 1.0), ("rt_18m", "1.5Y", 1.5), ("rt_2y", "2Y", 2.0),
    ("rt_3y", "3Y", 3.0), ("rt_5y", "5Y", 5.0), ("rt_7y", "7Y", 7.0),
    ("rt_10y", "10Y", 10.0), ("rt_20y", "20Y", 20.0), ("rt_30y", "30Y", 30.0),
]

# (라벨, 년수). 라벨은 이 리포의 테너 어휘 그대로 — universe.TENORS 와 문자열로
# 만나야 하고, 화면에 두 벌의 이름이 도는 것이 이 리포의 반복 결함이다.
BOND_TENORS: list[tuple[str, float]] = [(lbl, yrs) for _, lbl, yrs in CM_TENORS]

#: 스왑은 호가 노드만 — 6M·9M 은 mkt_irs_close 실컬럼이고 업스트림 보간 금지
#: 목록(4Y·6~9Y)에 없다 [OWNER 2026-08-19 확장]. 3M 은 IRS 컬럼 자체가 없고
#: (그 자리는 CD), 10Y 너머도 없다 — 없는 것은 그대로 둔다. 7Y 가 없는 것이
#: 데이터의 사실이다 — 보간으로 메우지 않는다.
SWAP_TENORS: list[tuple[str, float]] = [
    ("6M", 0.5), ("9M", 0.75),
    ("1Y", 1.0), ("1.5Y", 1.5), ("2Y", 2.0), ("3Y", 3.0),
    ("5Y", 5.0), ("10Y", 10.0),
]

#: 신용 사다리 순 [OWNER — 기본 은행 AAA + 셀렉터].
CREDIT_TYPES_3D: list[str] = ["KDB", "SPB", "BD", "CB1", "CARD", "OFB"]
CREDIT_DEFAULT = "BD"

#: 역전을 재는 짝 — surface.py 와 같은 규약 (long − short, 음수 = 역전).
INVERSION_PAIR = ("2Y", "10Y")


def surface3d_watermark() -> str:
    """credit_matrix 의 (MAX(bas_dt), COUNT(*)) — 캐시 키의 크레딧 절반.

    이 테이블에는 updated_at 이 없어 과거 행의 조용한 수정은 못 잡는다
    (mysqldb.watermark 의 같은 한계). universe 라우트는 dataset 키만 쓰지만,
    이 페이로드는 크레딧이 절반이라 크레딧 쪽 낡음도 키에 넣는다.
    """
    with engine().connect() as conn:
        row = conn.execute(text(
            "SELECT MAX(bas_dt) AS d, COUNT(*) AS n FROM sim_portfolio.credit_matrix"
        )).one()
    return f"{row.d}:{row.n}"


def _pool(
    label: str,
    tenors: list[tuple[str, float]],
    dates: list,
    by_tenor: dict[str, list[float | None]],
    inversion_bp: list[float | None] | None = None,
    unit: str = "%",
    with_inversion: bool = True,
) -> dict[str, Any] | None:
    """한 풀의 페이로드. 주별로 솎고(마지막 = as-of), 전부 결측인 테너는
    이름을 밝히고 뺀다 — 격자가 조용히 한 칸 좁아지는 것은 눈으로 절대 안
    잡힌다(surface.py 의 missingNodes 와 같은 이유).

    `inversion_bp` 를 주면 그대로 쓰고(스왑 — spread_series 가 표의 스프레드
    행과 같은 값을 내야 한다, §16), 없으면 여기서 계산한다(채권 풀 — 이 짝을
    싣는 표 행이 없어 어긋날 상대가 없다).
    """
    if not dates:
        return None
    idx = list(range(len(dates)))  # 일별 — 마지막이 곧 as-of 다

    rows: list[list[float | None]] = []
    kept: list[dict[str, Any]] = []
    missing: list[str] = []
    for t, yrs in tenors:
        s = by_tenor.get(t)
        if s is None or all(s[i] is None for i in idx):
            missing.append(t)
            continue
        kept.append({"t": t, "years": yrs})
        rows.append([None if s[i] is None else round(s[i], 4) for i in idx])

    if not kept:
        return None

    short, long_ = INVERSION_PAIR
    if not with_inversion:
        # 스프레드 풀 — 스프레드의 2s10s 는 굳이 만들면 만들어지지만 아무도 그
        # 이름으로 부르지 않는 숫자다. 없는 것으로 나간다.
        inv: list[float | None] = [None] * len(idx)
    elif inversion_bp is not None:
        inv = [None if inversion_bp[i] is None else round(inversion_bp[i], 2) for i in idx]
    else:
        s2, s10 = by_tenor.get(short), by_tenor.get(long_)
        inv = []
        for i in idx:
            a = s2[i] if s2 else None
            b = s10[i] if s10 else None
            inv.append(None if a is None or b is None else round((b - a) * 100.0, 2))

    d0 = dates[0]
    return {
        "label": label,
        "unit": unit,
        "asof": dates[-1].isoformat() if hasattr(dates[-1], "isoformat") else str(dates[-1]),
        "tenors": kept,
        "dates": [d.isoformat() if hasattr(d, "isoformat") else str(d) for d in (dates[i] for i in idx)],
        "z": rows,
        "inversionPair": f"{short}-{long_}",
        "inversionBp": inv,
        "missingNodes": missing,
        "start": d0.isoformat() if hasattr(d0, "isoformat") else str(d0),
    }


def assemble(
    dataset: Dataset,
    cdates: list,
    curves: dict[str, dict[str, list[float | None]]],
) -> dict[str, Any]:
    """페이로드 조립 — SQL 을 만지지 않는 순수 절반. 게이트는 이 함수를 잡는다."""
    swap_by_tenor = {t: dataset.series[t] for t, _ in SWAP_TENORS if t in dataset.series}
    swap_inv = spread_series(dataset, *INVERSION_PAIR)

    pools: dict[str, Any] = {}
    p = _pool("스왑", SWAP_TENORS, list(dataset.dates), swap_by_tenor, inversion_bp=swap_inv)
    if p:
        pools["swap"] = p
    p = _pool("국고", BOND_TENORS, cdates, curves.get("KTB", {}))
    if p:
        pools["govt"] = p
    for bt in CREDIT_TYPES_3D:
        cur = curves.get(bt)
        if not cur:
            continue
        p = _pool(CURVE_LABEL.get(bt, bt), BOND_TENORS, cdates, cur)
        if p:
            pools[f"credit:{bt}"] = p

    # ── 스프레드 풀 [OWNER 2026-08-18 — "스프레드 표면"]. 부호·정렬은 universe
    # 의 표 행과 같다(§16): BSS = IRS − 국고(inner join — 한쪽만 찍힌 날의
    # 스프레드를 지어내지 않는다 · 부호 규약은 [OWNER 2026-09-22] «스왑 −
    # 채권현물»), 신용 스프레드 = 크레딧 − 국고(같은 달력 — 이쪽은 **안 뒤집는다**,
    # 크레딧 스프레드는 스왑 대 현물이 아니다).
    # 둘 다 ×100 = bp.
    ktb = curves.get("KTB", {})
    irs_idx = {d: i for i, d in enumerate(dataset.dates)}
    bss_by_tenor: dict[str, list[float | None]] = {}
    for tlbl, _y in SWAP_TENORS:
        gs = ktb.get(tlbl)
        ss = dataset.series.get(tlbl)
        if gs is None or ss is None:
            continue
        vals: list[float | None] = []
        for i, d in enumerate(cdates):
            j = irs_idx.get(d)
            a = gs[i]
            b = ss[j] if j is not None else None
            vals.append(None if a is None or b is None else (b - a) * 100.0)
        bss_by_tenor[tlbl] = vals
    p = _pool("BSS", SWAP_TENORS, cdates, bss_by_tenor, unit="bp", with_inversion=False)
    if p:
        pools["bss"] = p
    for bt in CREDIT_TYPES_3D:
        cur = curves.get(bt)
        if not cur:
            continue
        sp_by_tenor: dict[str, list[float | None]] = {}
        for tlbl, _y in BOND_TENORS:
            cs = cur.get(tlbl)
            gs = ktb.get(tlbl)
            if cs is None or gs is None:
                continue
            sp_by_tenor[tlbl] = [
                None if a is None or b is None else (a - b) * 100.0
                for a, b in zip(cs, gs)
            ]
        p = _pool(
            f"{CURVE_LABEL.get(bt, bt)}−국고",
            BOND_TENORS,
            cdates,
            sp_by_tenor,
            unit="bp",
            with_inversion=False,
        )
        if p:
            pools[f"crd:{bt}"] = p

    # CD91 — hover 리드아웃이 "그날의 CD" 를 같이 적기 위한 것 [OWNER 2026-08-18].
    # IRS 달력의 일별 그대로 나간다. 프론트는 짚은 날짜 이하의 마지막 값을 고를
    # 뿐 계산하지 않는다(§16). 기준금리는 이미 PolicyStep(steps)이 지고 있다.
    cd_series = dataset.series.get("3M")
    cd = None
    if cd_series is not None:
        cd = {
            "dates": [d.isoformat() for d in dataset.dates],
            "values": [None if v is None else round(v, 4) for v in cd_series],
        }

    return {
        "unit": "%",
        "stride": 1,  # 일별 — 화면이 "능선 하나가 며칠"을 적을 때 읽는 값
        "creditTypes": [
            {"id": bt, "label": CURVE_LABEL.get(bt, bt)}
            for bt in CREDIT_TYPES_3D
            if f"credit:{bt}" in pools
        ],
        "creditDefault": CREDIT_DEFAULT,
        "cd": cd,
        "pools": pools,
    }


def build_surface3d(dataset: Dataset) -> dict[str, Any]:
    """전체 빌드 — 크레딧 절반은 SQL, 스왑 절반은 dataset. 라우트가 캐시에 태운다."""
    with engine().connect() as conn:
        cdates, curves = _fetch_curves(conn, tenors=CM_TENORS)
    return assemble(dataset, cdates, curves)
