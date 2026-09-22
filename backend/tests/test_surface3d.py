# -*- coding: utf-8 -*-
"""3D 커브 표면 (app/surface3d.py) — 3풀 페이로드의 거짓말 자리들.

`assemble()` 은 SQL 을 만지지 않는 순수 절반이라 게이트가 DB 없이 잡는다.
잡는 것은 넷:

1. **마지막 능선은 풀마다 자기 as-of 다** — 풀별 자기 달력 [OWNER].
2. **스왑 노드에 7Y 가 없다.** SQL 의 irs_7y 는 업스트림 보간이고, 표면 위에서
   보간 노드는 점 마커로 구분되지 않는다 (surface.py 의 같은 판정).
3. **전부 결측인 테너는 이름을 밝히고 빠진다** — 격자가 조용히 좁아지는 것은
   눈으로 안 잡힌다.
4. **역전 부호 규약** — long − short, 음수 = 역전. 스왑은 spread_series 를
   그대로 태워 표의 스프레드 행과 어긋나지 않는다 (§16).
"""

from __future__ import annotations

import datetime as dt

from app.dataset import Dataset
from app.surface3d import (
    BOND_TENORS,
    CREDIT_DEFAULT,
    CREDIT_TYPES_3D,
    SWAP_TENORS,
    assemble,
)


def _dataset(n: int = 23) -> Dataset:
    dates = [dt.date(2016, 1, 4) + dt.timedelta(days=i) for i in range(n)]
    tenors = ["1D", "3M", "6M", "9M", "1Y", "1.5Y", "2Y", "3Y", "5Y", "10Y"]
    series = {
        t: [round(1.0 + k * 0.1 + i * 0.001, 4) for i in range(n)]
        for k, t in enumerate(tenors)
    }
    return Dataset(dates=dates, series=series, tenor_order=tenors)


def _credit(n: int = 17) -> tuple[list[dt.date], dict[str, dict[str, list[float | None]]]]:
    """장난감 credit_matrix 피벗 — KTB 전량, BD 는 7Y 전결측, 나머지 타입 없음."""
    dates = [dt.date(2020, 1, 2) + dt.timedelta(days=i) for i in range(n)]
    full = {t: [round(2.0 + y * 0.1 + i * 0.001, 4) for i in range(n)] for t, y in BOND_TENORS}
    bd = {t: list(v) for t, v in full.items()}
    bd["7Y"] = [None] * n
    return dates, {"KTB": full, "BD": bd}


def test_swap_nodes_are_quoted_only():
    labels = [t for t, _ in SWAP_TENORS]
    # 업스트림 보간 컬럼(4Y·6~9Y)은 못 들어온다. 6M·9M 은 실컬럼 호가라 들어왔다
    # [OWNER 2026-08-19 — "3M부터 30까지 있으면 추가"]. 3M 은 IRS 컬럼이 없다(CD).
    assert "7Y" not in labels
    assert "4Y" not in labels
    assert "3M" not in labels
    assert labels == ["6M", "9M", "1Y", "1.5Y", "2Y", "3Y", "5Y", "10Y"]
    # 채권 격자에는 7Y 가 있다 — 민평은 그 만기를 실제로 고시한다. 3M~30Y 확장도
    # 같은 근거다(실측 100% 컬럼만, 2.5Y 는 비호가 판정 승계로 제외).
    bond_labels = [t for t, _ in BOND_TENORS]
    assert "7Y" in bond_labels
    assert bond_labels[:3] == ["3M", "6M", "9M"]
    assert bond_labels[-2:] == ["20Y", "30Y"]
    assert "2.5Y" not in bond_labels


def test_each_pool_ends_on_its_own_asof():
    ds = _dataset()
    cdates, curves = _credit()
    p = assemble(ds, cdates, curves)
    assert p["pools"]["swap"]["asof"] == ds.dates[-1].isoformat()
    assert p["pools"]["govt"]["asof"] == cdates[-1].isoformat()
    assert p["pools"]["swap"]["dates"][-1] == ds.dates[-1].isoformat()
    assert p["pools"]["govt"]["dates"][-1] == cdates[-1].isoformat()
    # 풀별 자기 달력 — 스왑이 2016, 채권이 2020 에서 시작한다.
    assert p["pools"]["swap"]["dates"][0] < p["pools"]["govt"]["dates"][0]


def test_all_missing_tenor_is_named_not_silent():
    p = assemble(_dataset(), *_credit())
    bd = p["pools"]["credit:BD"]
    assert "7Y" in bd["missingNodes"]
    assert "7Y" not in [t["t"] for t in bd["tenors"]]
    # z 행 수는 남은 테너 수와 같다 — 자리가 밀리면 능선이 옆 테너 값을 입는다.
    assert len(bd["z"]) == len(bd["tenors"])


def test_inversion_sign_is_long_minus_short():
    ds = _dataset()
    p = assemble(ds, *_credit())
    swap = p["pools"]["swap"]
    # 장난감 값은 장기가 항상 높다 → 역전 없음(양수).
    assert all(v is not None and v > 0 for v in swap["inversionBp"])
    # 값 자체가 (10Y − 2Y)×100 인지 마지막 칸으로 못 박는다.
    i = len(ds.dates) - 1
    want = round((ds.series["10Y"][i] - ds.series["2Y"][i]) * 100, 2)
    assert swap["inversionBp"][-1] == want


def test_credit_selector_lists_only_present_types():
    p = assemble(_dataset(), *_credit())
    ids = [c["id"] for c in p["creditTypes"]]
    assert ids == ["BD"]  # 장난감엔 BD 뿐 — 없는 타입이 셀렉터에 뜨면 빈 표면이 된다.
    assert CREDIT_DEFAULT in CREDIT_TYPES_3D


def test_spread_pools_follow_universe_sign_convention():
    # §16 — 표의 BSS·CRD 행과 부호가 같아야 한다: BSS = **IRS − 국고**
    # [부호 규약 OWNER 2026-09-22], 신용 = 크레딧 − 국고(이쪽은 스왑 대 현물이
    # 아니라 그대로다 — 한 규약이 모든 스프레드에 걸리지 않는다는 것이 요점이다).
    cdates, curves = _credit()
    # BSS 는 inner join 이라 달력이 겹쳐야 선다 — 민평 달력과 같은 날짜의 IRS.
    tenors = ["1D", "3M", "6M", "9M", "1Y", "1.5Y", "2Y", "3Y", "5Y", "10Y"]
    ds = Dataset(
        dates=list(cdates),
        series={
            t: [round(1.0 + k * 0.1 + i * 0.001, 4) for i in range(len(cdates))]
            for k, t in enumerate(tenors)
        },
        tenor_order=tenors,
    )
    p = assemble(ds, cdates, curves)
    bss = p["pools"]["bss"]
    assert bss["unit"] == "bp"
    assert all(v is None for v in bss["inversionBp"])  # 스프레드의 2s10s 는 없다
    i = len(cdates) - 1
    ti = [x["t"] for x in bss["tenors"]].index("3Y")
    want_bss = round((ds.series["3Y"][i] - curves["KTB"]["3Y"][i]) * 100.0, 4)
    assert bss["z"][ti][-1] == want_bss
    crd = p["pools"]["crd:BD"]
    assert crd["unit"] == "bp"
    want = round((curves["BD"]["3Y"][i] - curves["KTB"]["3Y"][i]) * 100.0, 4)
    tj = [x["t"] for x in crd["tenors"]].index("3Y")
    assert crd["z"][tj][-1] == want


def test_bss_refuses_to_invent_spreads_on_disjoint_calendars():
    # 달력이 안 겹치면(스왑 2016 장난감 vs 민평 2020) BSS 는 서지 않아야 한다 —
    # 한쪽만 찍힌 날의 스프레드는 지어낸 값이다.
    p = assemble(_dataset(), *_credit())
    assert "bss" not in p["pools"]


def test_cd_rides_along_for_the_readout():
    # hover 리드아웃의 "CD 얼마" — IRS 달력 일별 그대로, 값은 4dp 라운드 관통.
    ds = _dataset()
    p = assemble(ds, *_credit())
    assert p["cd"] is not None
    assert len(p["cd"]["dates"]) == len(ds.dates)
    assert p["cd"]["values"][-1] == round(ds.series["3M"][-1], 4)


def test_values_pass_through_rounded_not_recomputed():
    ds = _dataset()
    p = assemble(ds, *_credit())
    swap = p["pools"]["swap"]
    # z 는 데이터셋 그대로다 (§16) — 마지막 능선 = as-of 열.
    ti = [t["t"] for t in swap["tenors"]].index("5Y")
    assert swap["z"][ti][-1] == round(ds.series["5Y"][-1], 4)
