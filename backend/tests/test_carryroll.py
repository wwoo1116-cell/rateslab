"""앞을 보는 캐리·롤다운 — 값이 아니라 **관계**를 잡는다.

`test_theta.py` 와 같은 자세다: 캐리와 롤다운은 눈으로 검산할 수 없는 수라
(서로 다른 단위에서 와서 호가 bp 로 합쳐진다) 여기서 잡는 것은 정의가 스스로
닫히는지다. 커브는 **합성**이라 DB 가 필요 없다 — `mrplan` 이 `leg_of` 를
주입받는 것과 같은 이유로 `for_series` 도 번들을 받는다.

가장 중요한 시험은 `test_outright_roll_matches_theta` 다. 이 모듈이 `theta.py`
의 **산술을 입력 커브만 갈아 끼워** 쓴다는 주장이 거기서 참이 되거나 거짓이
된다 — 그 주장이 깨지면 같은 양을 두 벌 구현한 것이고, 이 리포가 반복해 밟은
결함이 하나 더 는다.
"""

from __future__ import annotations

import pytest

from app import carryroll, funding as fnd, mrcarry, mrseries as mrs, theta as th
from app.curves import TENOR_T

DAY = "2026-10-15"
TENORS = ["6M", "9M", "1Y", "1.5Y", "2Y", "3Y", "5Y", "7Y", "10Y"]

#: 우상향 — 롤이 0 이 아닌 커브라야 부호와 크기를 잴 수 있다.
UP = {"6M": 3.00, "9M": 3.10, "1Y": 3.20, "1.5Y": 3.40, "2Y": 3.60,
      "3Y": 3.80, "5Y": 4.00, "7Y": 4.10, "10Y": 4.20}
#: 더 가파른 것 — 「가파르면 더 구른다」를 재는 짝.
STEEP = {"6M": 3.00, "9M": 3.20, "1Y": 3.40, "1.5Y": 3.80, "2Y": 4.20,
         "3Y": 4.60, "5Y": 5.00, "7Y": 5.20, "10Y": 5.40}
FLAT = {t: 3.00 for t in TENORS}

CD = 2.90


def _curve(vals: dict[str, float]) -> dict[str, dict[str, float]]:
    return {t: {DAY: v} for t, v in vals.items()}


def _bundle(irs: dict[str, float], *, govt_spread_bp: float = 5.0,
            govt_3m: float | None = 2.95) -> dict:
    """합성 번들. 국고는 IRS 에 상수 스프레드를 얹은 것 — BSS 의 **롤이 0 이
    되는** 커브라서, 거기서 안 0 이면 두 다리의 읽기가 어긋난 것이다."""
    ktb = {t: v + govt_spread_bp / 100.0 for t, v in irs.items()}
    if govt_3m is not None:
        ktb["3M"] = govt_3m
    return {"irs": _curve(irs), "ktb": _curve(ktb), "cd": {DAY: CD}}


@pytest.fixture
def nodb(monkeypatch):
    """`mrcarry` 가 DB 대신 합성 번들과 고정 조달을 보게 한다."""
    def _install(bundle: dict) -> dict:
        monkeypatch.setattr(mrs, "bundle", lambda: bundle)
        monkeypatch.setattr(fnd, "rate_on", lambda _spec, _d: 0.0285)
        return bundle
    return _install


# ── 커브 경로가 theta 와 같은가 ────────────────────────────────────────────


def test_outright_roll_matches_theta():
    """아웃라이트 한 다리에서 **호가 드리프트 == theta 의 롤**(bp).

    패키지에서는 둘이 갈린다(연금비 가중 — 모듈 머리의 그 표). 갈리지 **않아야**
    하는 자리가 여기이고, 여기서 갈리면 커브를 읽는 길이 둘로 쪼개진 것이다.
    """
    nodes = sorted((TENOR_T[t], v) for t, v in UP.items())
    read, zc = carryroll._par_reader(nodes)          # noqa: SLF001 — 이 모듈의 시험
    leg = th._leg_cache(zc, CD / 100.0)              # noqa: SLF001 — theta 의 다리 캐시

    for ten in ("1Y", "2Y", "3Y", "5Y", "10Y"):
        t = TENOR_T[ten]
        _carry_u, roll_u, _a_now, a_h = leg(t)
        theta_roll_bp = roll_u / (a_h * 1e-4)
        drift_bp = (read(t - carryroll.HORIZON_Y) - read(t)) * 100.0
        assert theta_roll_bp == pytest.approx(drift_bp, abs=1e-6), ten


def test_par_reader_round_trips_quoted_nodes():
    """호가 노드에서는 되읽은 par 가 그 호가다 — 부트스트랩이 제자리를 지키는지.

    ★**짧은 끝이 잡혀 있어야** 그렇다. 3M 노드 없이 6M 부터 시작하는 커브에서는
    0.25 구간의 제로가 외삽이라 6M par 가 1.1bp 어긋난다(실측). 그래서 실전
    경로는 **CD 91일을 3M 노드로 넣고**(`for_series`), 이 시험도 같은 구성으로
    잰다 — 시험이 실전과 다른 커브를 쓰면 실전의 성질을 못 잡는다.

    ⚠ 그래도 **정확히 같지는 않다.** 제로를 선형보간해 par 를 되짓는 과정이라
    노드 간격이 넓은 자리에서 가장 크게 벌어진다 — 합성 커브에서 5Y 0.72bp,
    실측(2026-10-15 종합ALL)에서 5Y 0.27bp · 10Y 0.17bp · 2Y 0.03bp. 문턱을
    **1bp** 로 둔 근거가 그 분포이고, 이 잔차가 롤의 정밀도 하한이다
    (모듈 머리 「정밀도」).
    """
    nodes = sorted(
        [(TENOR_T[t], v) for t, v in UP.items()] + [(TENOR_T["3M"], CD)])
    read, _zc = carryroll._par_reader(nodes)         # noqa: SLF001
    for t, v in nodes:
        if t < carryroll.MIN_REMAIN_Y:
            continue
        assert read(t) == pytest.approx(v, abs=0.01), t


def test_reader_refuses_outside_the_curve():
    """범위 밖·잔존 한 분기 밑은 **없는 값**이다 — 외삽을 롤이라 부르지 않는다."""
    nodes = sorted((TENOR_T[t], v) for t, v in UP.items())
    read, _zc = carryroll._par_reader(nodes)         # noqa: SLF001
    assert read(0.1) is None                          # 짧은 끝 밖
    assert read(30.0) is None                         # 긴 끝 밖
    assert read(0.5) is not None


# ── 정의가 스스로 닫히는가 ─────────────────────────────────────────────────


@pytest.mark.parametrize("sid,kind", [
    ("BSS-3Y", "bss"), ("IRC-2Y-10Y", "irc"), ("IRF-2Y-5Y-10Y", "irf"),
])
def test_flat_curve_has_no_roll(nodb, sid, kind):
    """평평한 커브에서는 나이가 들어도 호가가 안 움직인다 — 롤 0.

    캐리는 0 이 아니다(고정과 CD 의 차는 남는다). 둘이 **따로** 서는지를 이
    시험이 가른다 — 한쪽이 다른 쪽에 샜으면 여기서 0 이 안 나온다.
    """
    b = nodb(_bundle(FLAT, govt_3m=3.05))
    blk = carryroll.for_series(sid, kind, bundle=b)
    assert blk is not None
    assert blk["rollBp"] == pytest.approx(0.0, abs=1e-6)


def test_bss_roll_is_zero_when_two_curves_are_parallel(nodb):
    """국고가 IRS + 상수면 BSS 는 커브가 가팔라도 **안 구른다**.

    BSS 의 롤은 두 커브의 **기울기 차**라는 주장이 참이면 이 수는 0 이다.
    한 다리만 다른 방식으로 읽으면(옛 선형보간 섞기) 여기서 큰 찌꺼기가 남는다.

    ⚠ 정확히 0 은 아니다 — **−0.02bp** 가 남는다(실측). 부트스트랩이 비선형이라
    「IRS+5bp 커브의 par(T−h)」와 「IRS 커브의 par(T−h) + 5bp」가 한 자리까지
    같지 않기 때문이고, 민평 국고 수익률을 par 로 다루는 [알려진 근사]의 크기가
    곧 이 수다. 실전 롤이 0.2~11bp 인 것에 견주면 0.02bp 는 묻히지만, **0 이
    아니라는 사실**은 적어 둔다 — 다음 사람이 0 을 기대하고 디버깅하지 않도록.
    """
    b = nodb(_bundle(STEEP, govt_spread_bp=5.0, govt_3m=None))
    blk = carryroll.for_series("BSS-3Y", "bss", bundle=b)
    assert blk is not None
    assert blk["rollBp"] == pytest.approx(0.0, abs=0.05)


def test_steeper_curve_rolls_more(nodb):
    """가파를수록 스티프너의 롤이 크다 — 부호와 단조성."""
    gentle = carryroll.for_series("IRC-1Y-2Y", "irc", bundle=nodb(_bundle(UP)))
    steep = carryroll.for_series("IRC-1Y-2Y", "irc", bundle=nodb(_bundle(STEEP)))
    assert gentle["rollBp"] > 0
    assert steep["rollBp"] > gentle["rollBp"]


def test_quote_definition_matches_mrseries():
    """`_quote_bp` 가 계열의 값 정의와 같은 식인가 — 갈리면 롤이 레벨과 안 닫힌다."""
    irs = {2.0: 3.60, 10.0: 4.20, 5.0: 4.00}
    ktb = {2.0: 3.65}
    r_irs = lambda t: irs.get(t)                      # noqa: E731
    r_ktb = lambda t: ktb.get(t)                      # noqa: E731
    # bss = (IRS − 국고) × 100  [OWNER 2026-09-22 규약]
    assert carryroll._quote_bp("bss", [2.0], r_irs, r_ktb) == pytest.approx(-5.0)   # noqa: SLF001
    # irc = (긴 − 짧은) × 100, 차례는 combo_tenors(짧은 → 긴)
    assert carryroll._quote_bp("irc", [2.0, 10.0], r_irs, r_ktb) == pytest.approx(60.0)  # noqa: SLF001
    # irf = (2×벨리 − 윙) × 100
    assert carryroll._quote_bp(                                                      # noqa: SLF001
        "irf", [2.0, 5.0, 10.0], r_irs, r_ktb) == pytest.approx(2 * 400.0 - 360.0 - 420.0)


def test_quote_is_none_when_a_leg_is_missing():
    """다리 하나가 없으면 통째로 없다 — 다리 둘로 그린 플라이는 완성돼 보이면서 틀린다."""
    r = lambda t: None if t == 5.0 else 3.5           # noqa: E731
    assert carryroll._quote_bp("irf", [2.0, 5.0, 10.0], r, r) is None    # noqa: SLF001


# ── 캐리의 환산과 부호 ─────────────────────────────────────────────────────


def test_carry_bp_formula():
    """`캐리(bp) = −rate × h × 100 / pv01` — 모듈 머리의 그 한 줄 대수."""
    assert carryroll._carry_bp(1.0, 2.5, 0.25) == pytest.approx(-10.0)   # noqa: SLF001
    assert carryroll._carry_bp(-1.0, 2.5, 0.25) == pytest.approx(10.0)   # noqa: SLF001


def test_carry_sign_is_flipped_from_mrcarry(nodb):
    """`mrcarry` 는 `position = -1`, 이 표는 **+1** — 부호가 반대라야 맞다."""
    b = nodb(_bundle(UP))
    spec = fnd.FundingSpec().validated()
    rates, _defn = mrcarry.carry_rates("BSS-3Y", "bss", [DAY], spec)
    blk = carryroll.for_series("BSS-3Y", "bss", bundle=b)
    assert rates[0] is not None
    assert blk["carryBp"] * rates[0] < 0, "부호가 안 뒤집혔다"


def test_bss_carry_identity_holds(nodb):
    """BSS 캐리의 자기검사 — `BSS − (CD − 조달)` 로 접히는가.

    `mrcarry.assert_identity` 가 단위 사고를 가장 먼저 잡는 자리다(실측
    2026-08-27 에 100배 틀린 캐리를 이 항등이 잡았다). 이 모듈이 그 식을
    **그대로 부르는지** 여기서 확인한다 — 직접 다시 짜면 이 항등이 깨진다.
    """
    nodb(_bundle(UP))
    spec = fnd.FundingSpec().validated()
    rates, _defn = mrcarry.carry_rates("BSS-3Y", "bss", [DAY], spec)
    spread_bp = (UP["3Y"] - (UP["3Y"] + 0.05)) * 100.0
    mrcarry.assert_identity("BSS-3Y", "bss", [DAY], rates, [spread_bp], spec)


# ── 모양과 경계 ────────────────────────────────────────────────────────────


def test_components_sum_to_theta(nodb):
    """캐리 + 롤 = 세타. 셋을 따로 싣는 이유가 **더해지기 때문**이다."""
    b = nodb(_bundle(UP))
    blk = carryroll.for_series("IRC-2Y-10Y", "irc", bundle=b)
    assert blk["carryBp"] + blk["rollBp"] == pytest.approx(blk["thetaBp"], abs=1e-3)
    per = blk["perDay"]
    assert per["thetaBp"] == pytest.approx(
        blk["thetaBp"] / carryroll.HORIZON_DAYS, abs=1e-5)


def test_unsupported_kinds_are_absent(nodb):
    """FSW·FUT 는 아직 롤이 안 선다 — **0 이 아니라 없음**이다."""
    b = nodb(_bundle(UP))
    assert carryroll.for_series("FSW-3Y", "fsw", bundle=b) is None
    assert carryroll.for_series("FUT-KTB3", "fut", bundle=b) is None
    series = [("FSW-3Y", "퓨처스왑 3Y", "fsw"), ("BSS-3Y", "BSS 3Y", "bss")]
    assert set(carryroll.table(series, bundle=b)) == {"BSS-3Y"}


def test_blank_when_aged_tenor_falls_off_the_curve(nodb):
    """`T − h` 가 커브 밖이면 그 계열은 **빈다**(0 이 아니다).

    국고에 3M 노드가 없으면 BSS-6M 이 바로 그 자리다 — 0.5 − 0.25 = 0.25 가
    가장 짧은 노드(0.5)보다 앞이다.
    """
    b = nodb(_bundle(UP, govt_3m=None))
    assert carryroll.for_series("BSS-6M", "bss", bundle=b) is None
    # 3M 노드를 주면 선다.
    b2 = nodb(_bundle(UP, govt_3m=2.95))
    assert carryroll.for_series("BSS-6M", "bss", bundle=b2) is not None


def test_asof_is_the_day_every_leg_printed(nodb):
    """asof 는 **이 계열의** 다리가 다 찍힌 날이다 — 가족 단위 asof 가 낡은
    다리를 가린 전례(`mrseries._merge_govt`)의 반대편."""
    b = nodb(_bundle(UP))
    blk = carryroll.for_series("BSS-3Y", "bss", bundle=b)
    assert blk["asof"] == DAY
    assert blk["horizonY"] == carryroll.HORIZON_Y
    assert blk["sign"] == "+1"
