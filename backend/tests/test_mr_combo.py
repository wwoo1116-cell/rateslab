# -*- coding: utf-8 -*-
"""IRS 커브·플라이 계열 — 값의 규약·조합 목록·DV01 중립 가중·캐리의 부호
[OWNER 2026-09-09 — "스프레드(버터플라이나 커브와 같은 것도 연결해주기)"].

이 파일이 지키는 것 넷.
  ① **값은 `derive` 의 식이다.** 스프레드 `(긴 − 짧은)×100` · 플라이
     `(2×벨리 − 윙)×100`. 이 앱의 모니터·백테스트가 쓰는 그 규약이고, 갈리면
     같은 「3s10s」가 두 화면에서 다른 수가 된다.
  ② **조합 목록은 주요 세트를 그대로 읽는다** — 여기서 새로 고르지 않는다.
  ③ **가중은 DV01 중립이다.** 스프레드는 원금 비 = pv01 비, 플라이는 벨리가
     윙 둘의 합만큼(값 규약 `2×벨리` 의 짝).
  ④ **캐리의 첫 다리는 리시브**다. `position = -1`(값이 내리는 쪽)이 커브에서는
     플래트너이고, 그 다리 구성이 부호를 정한다 — 뒤집히면 캐리가 통째로 반대
     부호가 되고 그건 예외가 아니라 «그럴듯한 수» 로 나온다.

SQL 을 안 만진다: 번들(`mrseries.bundle`)을 합성값으로 갈아 끼운다.
"""
import pytest

from app import derive
from app import mr
from app import mrcarry as mc
from app import mrseries as mrs


@pytest.fixture
def bundle(monkeypatch):
    """이틀치 IRS 커브 + CD — 손으로 검산할 수 있는 크기."""
    irs = {
        "6M": {"2026-01-02": 3.00, "2026-01-05": 3.05},
        "9M": {"2026-01-02": 3.05, "2026-01-05": 3.06},
        "1Y": {"2026-01-02": 3.10, "2026-01-05": 3.12},
        "1.5Y": {"2026-01-02": 3.15, "2026-01-05": 3.16},
        "2Y": {"2026-01-02": 3.20, "2026-01-05": 3.24},
        "3Y": {"2026-01-02": 3.30, "2026-01-05": 3.31},
        "5Y": {"2026-01-02": 3.50, "2026-01-05": 3.55},
        "7Y": {"2026-01-02": 3.65, "2026-01-05": 3.66},
        "10Y": {"2026-01-02": 3.80, "2026-01-05": 3.90},
    }
    cd = {"2026-01-02": 2.90, "2026-01-05": 2.92}
    monkeypatch.setattr(mrs, "bundle", lambda: {"ktb": {}, "irs": irs, "cd": cd})
    return {"irs": irs, "cd": cd}


# ── ① 값의 규약 ──────────────────────────────────────────────────────────────

def test_curve_value_is_long_minus_short_in_bp(bundle):
    got = mrs.combo_points("IRC-3Y-10Y")
    assert got["unit"] == "bp"
    v = got["points"][0]["v"]
    assert v == pytest.approx((3.80 - 3.30) * 100.0)
    # 다리는 **긴 쪽 먼저** — 대사표의 「다리0 − 다리1 = 값」이 그 차례라야 닫힌다.
    assert got["points"][0]["legs"] == [3.80, 3.30]


def test_fly_value_is_twice_the_belly_minus_the_wings(bundle):
    v = mrs.combo_points("IRF-2Y-5Y-10Y")["points"][0]["v"]
    assert v == pytest.approx((2 * 3.50 - 3.20 - 3.80) * 100.0)


def test_fly_ships_no_leg_levels(bundle):
    """플라이는 다리 줄을 안 세운다 — `2×벨리 − 윙` 이 대사표의 부호 규약
    (`sign = -1 if j == 0 else 1`)과 안 맞고, 안 맞는 분해는 **그럴듯하게
    틀린 수**를 세운다. 그때 화면은 종합 한 줄짜리 대사표를 그린다."""
    assert "legs" not in mrs.combo_points("IRF-2Y-5Y-10Y")["points"][0]


def test_value_matches_the_derive_convention(bundle):
    """`derive` 의 그 함수와 **같은 수**여야 한다 — 두 화면이 같은 3s10s 를
    다르게 말하면 비교가 불가능해진다. 저쪽은 `Dataset` 을 먹으므로 여기서는
    같은 자리에 같은 계열을 세워 부른다."""
    class _DS:
        series = {"3Y": [3.30], "10Y": [3.80], "2Y": [3.20], "5Y": [3.50]}

    assert (mrs.combo_points("IRC-3Y-10Y")["points"][0]["v"]
            == pytest.approx(derive.spread_series(_DS, "3Y", "10Y")[0]))
    assert (mrs.combo_points("IRF-2Y-5Y-10Y")["points"][0]["v"]
            == pytest.approx(derive.fly_series(_DS, "2Y", "5Y", "10Y")[0]))


def test_days_are_the_intersection_not_a_carry_forward(bundle):
    """한 다리가 빠진 날은 **그 날이 통째로 없다** — 이월해 채우면 없던 커브를
    지어내게 된다(`mrseries.legs` 의 그 규율)."""
    bundle["irs"]["10Y"].pop("2026-01-05")
    got = mrs.combo_points("IRC-3Y-10Y")
    assert [p["t"] for p in got["points"]] == ["2026-01-02"]


# ── ② 조합 목록 ──────────────────────────────────────────────────────────────

def test_combo_list_is_the_repo_key_sets():
    ids = {sid for sid, _, kind in mr.SERIES if kind in ("irc", "irf")}
    assert ids == ({f"IRC-{x}" for x in derive.KEY_SPREADS}
                   | {f"IRF-{x}" for x in derive.KEY_FLIES})
    # 라벨은 데스크의 말이다 — 「IRS 3Y-10Y」.
    labels = {sid: lb for sid, lb, _ in mr.SERIES}
    assert labels["IRC-3Y-10Y"] == "IRS 3Y-10Y"


def test_both_directions_are_tradable_for_swap_only_combos():
    """커브·플라이는 스왑끼리라 대차가 없다 — BSS 를 한 방향으로 묶은 그 사유가
    여기엔 없다."""
    for kind in ("irc", "irf"):
        d = mr.dirs_for(kind)
        assert d["allowed"] == [-1, 1] and d["why"] is None
    assert "스티프너" in mr.DIR_LEGS["irc"]["plus"]["short"]
    assert "벨리 리시브" in mr.DIR_LEGS["irf"]["minus"]["short"]


def test_trigger_stands_on_both_edges_for_a_curve():
    t = mr.triggers_for("irc", v=50.0, up=55.0, lo=40.0, scale=1.0)
    assert [x["side"] for x in t] == ["above", "below"]
    assert t[0]["legs"] == "긴 쪽 리시브 · 짧은 쪽 페이"        # 상단 → 플래트너


# ── ③ DV01 중립 가중 ─────────────────────────────────────────────────────────

PV01 = {"2Y": 1.95, "3Y": 2.90, "5Y": 4.60, "10Y": 8.50}


def test_spread_weight_is_the_pv01_ratio():
    w = mc.combo_weights("IRC-3Y-10Y", lambda t: PV01[t])
    # 기준은 **긴 쪽**(가중 1). 짧은 쪽은 원금이 pv01 비만큼 크다.
    assert w[0] == 1.0
    assert w[1] == pytest.approx(PV01["10Y"] / PV01["3Y"])
    assert mc._tenor_of("IRC-3Y-10Y") == "10Y"


def test_fly_belly_carries_twice_the_wing_weight():
    w = mc.combo_weights("IRF-2Y-5Y-10Y", lambda t: PV01[t])
    assert w[0] == 2.0                                   # 벨리 = 윙 둘의 합
    assert w[1] == pytest.approx(PV01["5Y"] / PV01["2Y"])
    assert w[2] == pytest.approx(PV01["5Y"] / PV01["10Y"])
    assert mc._tenor_of("IRF-2Y-5Y-10Y") == "5Y"         # 기준은 벨리


def test_weights_are_required_for_a_combo():
    """가중 없이 부르면 **죽는다** — 조용히 1 로 두면 DV01 중립이 아닌 캐리가
    나오고 그 수는 예외가 아니라 그럴듯한 값이다."""
    with pytest.raises(ValueError):
        mc.carry_rates_by_leg("IRC-3Y-10Y", "irc", ["2026-01-02"], spec=None)


# ── ④ 캐리의 부호 ────────────────────────────────────────────────────────────

def test_curve_carry_first_leg_receives_second_pays(bundle):
    w = [1.0, PV01["10Y"] / PV01["3Y"]]
    legs = mc.carry_rates_by_leg("IRC-3Y-10Y", "irc", ["2026-01-02"], spec=None,
                                 weights=w)
    names = [n for n, _ in legs]
    assert names == ["긴 다리", "짧은 다리"]
    got = [r[0] for _, r in legs]
    # position −1 = 플래트너 = 긴 쪽 리시브 · 짧은 쪽 페이.
    assert got[0] == pytest.approx(3.80 - 2.90)                       # +(고정 − CD)
    assert got[1] == pytest.approx(w[1] * (2.90 - 3.30))              # −가중×(고정 − CD)
    # 우상향 커브에서 플래트너의 캐리는 **음수**일 수 있다 — 짧은 쪽 원금이 크다.
    total, defn = mc.carry_rates("IRC-3Y-10Y", "irc", ["2026-01-02"], spec=None,
                                 weights=w)
    assert total[0] == pytest.approx(sum(got))
    assert "DV01 중립" in defn


def test_fly_carry_sums_the_three_legs(bundle):
    w = mc.combo_weights("IRF-2Y-5Y-10Y", lambda t: PV01[t])
    legs = mc.carry_rates_by_leg("IRF-2Y-5Y-10Y", "irf", ["2026-01-02"],
                                 spec=None, weights=w)
    assert [n for n, _ in legs] == ["벨리", "짧은 윙", "긴 윙"]
    got = [r[0] for _, r in legs]
    assert got[0] == pytest.approx(2.0 * (3.50 - 2.90))
    assert got[1] == pytest.approx(w[1] * (2.90 - 3.20))
    assert got[2] == pytest.approx(w[2] * (2.90 - 3.80))


def test_missing_cd_leaves_the_bar_empty_not_zero(bundle):
    """CD 를 모르는 날은 **None** 이다 — 0 으로 채우면 「그날 캐리가 0」이라는
    다른 말이 되고, 엔진은 그 0 을 사실로 더한다."""
    bundle["cd"].pop("2026-01-05")
    w = [1.0, 2.0]
    legs = mc.carry_rates_by_leg("IRC-3Y-10Y", "irc", ["2026-01-02", "2026-01-05"],
                                 spec=None, weights=w)
    assert [r[1] for _, r in legs] == [None, None]


# ── ⑤ 다리별 액면 — DV01 중립이 **되곱아서** 확인된다 ────────────────────────

def test_combo_faces_are_dv01_neutral():
    """`액면 × pv01 × 1e-4 = 명목`(벨리만 두 배)이 다리마다 닫힌다.

    이 시험이 있는 이유: 첫 판은 각 다리의 pv01 로 **또** 나눠서 윙의 DV01 이
    1.5배로 나왔다. 화면에는 그럴듯한 억 단위 수가 섰고 예외는 없었다 — 이
    리포가 반복해서 밟는 «그럴듯하게 틀린 수» 다.
    """
    from app import main as m

    N = 1_000_000.0
    pv = {t: m.pv01(m._curves["now"], m.TENOR_T[t]) for t in ("1Y", "1.5Y", "2Y", "3Y", "10Y")}

    faces = dict(m.mr_combo_faces("IRC-3Y-10Y", N))
    for t, face in faces.items():
        assert face * pv[t] * 1e-4 == pytest.approx(N, rel=1e-9)

    faces = dict(m.mr_combo_faces("IRF-1Y-1.5Y-2Y", N))
    assert faces["1.5Y"] * pv["1.5Y"] * 1e-4 == pytest.approx(2 * N, rel=1e-9)   # 벨리
    for t in ("1Y", "2Y"):
        assert faces[t] * pv[t] * 1e-4 == pytest.approx(N, rel=1e-9)             # 윙


def test_combo_faces_start_with_the_receive_leg():
    """차례는 캐리·이름과 같다 — 커브는 긴 쪽, 플라이는 벨리가 먼저."""
    from app import main as m

    assert [t for t, _ in m.mr_combo_faces("IRC-3Y-10Y", 1e6)] == ["10Y", "3Y"]
    assert [t for t, _ in m.mr_combo_faces("IRF-2Y-5Y-10Y", 1e6)] == ["5Y", "2Y", "10Y"]
