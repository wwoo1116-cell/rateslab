# -*- coding: utf-8 -*-
"""발행 캘린더의 두 판정 — 민평 대비, 그리고 방향 [OWNER, 2026-08-21].

    민평 대비   그때 그 금리가 시장보다 오버였나 언더였나  (`issuance_mp`)
    방향        그 재료가 금리를 어느 쪽으로 미나          (`issuance_gloss`)

이 파일에서 하중을 지는 것은 **못 내는 판정을 안 내는지** 보는 검사들이다.
숫자를 내는 것은 쉽고, 낼 수 없을 때 입을 다무는 것이 어렵다:

    등급이 커브와 다르면      숫자는 내되 «오버/언더» 라고 부르지 않는다
    ±100bp 밖이면            원화 고정이표채가 아니라고 보고 판정을 안 낸다
    물가채는                 실질금리라 명목 민평과 안 견준다
    경쟁입찰이 없던 날은      «중립» 이 아니라 방향이 **없다**

민평은 SQL 이 있어야 읽힌다. 없는 PC 에서는 그 검사만 건너뛰고, **캘린더가
민평 없이도 서는지**는 SQL 과 무관하게 늘 본다 — 그게 이 배선의 계약이다.
"""

import datetime as dt

import pytest

from app import creditmatrix, issuance
from app import issuance_mp as mp
from app.issuance import IssuanceUnavailable, build, day_detail, months_from
from app.issuance_gloss import (
    BOTH,
    EVENT,
    EVENT_BIAS,
    LANE,
    LANE_BIAS,
    MPC_BIAS,
    STRENGTH_BIAS,
    for_event,
)
from app.policy import MPC_DATES

MPC = [d.isoformat() for d in MPC_DATES]

def _issuing_days(back: int = 60) -> list[str]:
    """발행이 실제로 있는 날. **자료에서 찾는다** — 날짜를 못 박으면 창이
    굴러갈 때 시험이 조용히 낡는다(2026-09-15 실측)."""
    stamp = issuance.data_stamp()
    end = dt.date.fromisoformat(stamp[:10]) if isinstance(stamp, str) else dt.date.today()
    out: list[str] = []
    for i in range(back):
        day = (end - dt.timedelta(days=i)).isoformat()
        try:
            if day_detail(day, MPC)["issuing"]:
                out.append(day)
        except Exception:  # noqa: BLE001 — 그날 자료가 없으면 그냥 넘어간다
            continue
    return out



def _has_data() -> bool:
    try:
        issuance.data_stamp()
        return True
    except IssuanceUnavailable:
        return False


def _has_mp() -> bool:
    try:
        mp.matrix()
        return True
    except Exception:  # noqa: BLE001 — SQL 계층의 예외가 여러 갈래다
        return False


needs_data = pytest.mark.skipif(not _has_data(), reason="rawData CSV 가 없는 환경")
needs_mp = pytest.mark.skipif(not _has_mp(), reason="민평 SQL 이 없는 환경")


# ── 방향 어휘 ───────────────────────────────────────────────────────────────


def test_every_event_key_has_a_direction():
    """`EVENT` 의 열쇠말마다 방향이 한 줄씩. 짝이 빠지면 그 하나만 방향 없이 뜬다."""
    missing = [k for k, _t in EVENT if k not in EVENT_BIAS]
    assert not missing, f"방향이 빠진 열쇠말: {missing}"
    orphan = set(EVENT_BIAS) - {k for k, _t in EVENT}
    assert not orphan, f"설명 없는 방향: {orphan}"
    # 방향만 드는 표다 — 근거는 바로 위 `EVENT` 의 문장이 든다. 그걸 여기
    # 한 번 더 적었더니 화면에 같은 문단이 두 번 찍혔다.
    assert all(isinstance(v, str) for v in EVENT_BIAS.values())


def test_no_event_key_is_inside_another():
    """열쇠말이 서로의 부분 문자열이면 안 된다.

    **실측 결함, 2026-08-21:** 원본의 열쇠말 «매입» 이 «RP매입» 의 부분
    문자열이라 RP매입 줄마다 바이백 설명이 따라붙었다. 원본은 라벨을 화면에서
    맞춰서 이 배선이 없었고, v2 가 서버에서 맞추면서 생긴 결함이다.
    """
    keys = [k for k, _t in EVENT]
    for a in keys:
        for b in keys:
            if a != b:
                assert a not in b, f"«{a}» 가 «{b}» 안에 들어 있어요"


def test_every_lane_has_a_direction():
    """레인마다 방향 한 줄. 설명은 있는데 방향이 없으면 화면이 반만 답한다."""
    assert set(LANE) == set(LANE_BIAS)


def test_the_direction_words_are_the_bond_markets():
    """채권의 «강세» 는 금리가 내리는 것이다 — 주식의 반대다.

    이 네 글자가 화면 색까지 정한다(파랑은 하락 전용이라 강세가 파랑이다).
    풀어 쓰는 문장이 방향과 어긋나면 색과 글이 서로 다른 말을 한다.
    """
    assert EVENT_BIAS["RP매입"] == "강세"  # 돈을 푼다
    assert EVENT_BIAS["RP매각"] == "약세"  # 돈을 거둔다
    assert EVENT_BIAS["통안증권"] == "약세"  # 흡수 + 물량
    assert EVENT_BIAS["통안 중도환매"] == "강세"  # 공급 + 물량 회수
    assert MPC_BIAS["인하"]["dir"] == "강세"
    assert MPC_BIAS["인상"]["dir"] == "약세"
    assert MPC_BIAS["동결"]["dir"] == "중립"
    assert STRENGTH_BIAS["강세"]["dir"] == "강세"
    assert STRENGTH_BIAS["약세"]["dir"] == "약세"


def test_a_direction_never_travels_without_its_reason():
    """방향만 있고 근거가 없으면 그건 점괘다."""
    for table in (LANE_BIAS, MPC_BIAS, STRENGTH_BIAS):
        for key, b in table.items():
            assert b["dir"], key
            assert b["why"] and len(b["why"]) > 8, key


def test_the_buyback_gloss_no_longer_rides_on_rp_purchases():
    """부분 문자열 결함의 회귀 검사 — 라벨 하나로 실제로 걸어 본다."""
    assert [b["key"] for b in for_event("RP매입")] == ["RP매입"]
    assert [b["key"] for b in for_event("바이백")] == ["바이백"]


def test_the_explanation_and_its_direction_arrive_as_one():
    """설명과 방향을 두 벌로 내면 화면이 같은 문단을 두 번 찍는다.

    **실측 결함, 2026-08-21:** 비경쟁인수 줄에 «…행사한 물량이에요» 문단이
    한 번, 그 아래 «강세 요인» 과 함께 같은 문장이 또 한 번 찍혔다.
    """
    got = for_event("비경쟁인수 Ⅱ 국고03500-2906")
    assert [g["key"] for g in got] == ["비경쟁"]
    assert set(got[0]) == {"key", "text", "dir"}
    assert got[0]["dir"] == "강세"
    assert "옵션" in got[0]["text"]


@needs_data
def test_a_zero_exercise_gets_no_direction():
    """**실측 결함, 2026-08-21:** 0억 행사 비경쟁인수에 «강세 요인» 이 붙었다.

    비경쟁인수의 방향은 «있었다» 가 아니라 «얼마나 행사됐나» 에서 나온다 —
    행사가 있었다는 것이 곧 그 사이 시장이 낙찰금리 아래로 내려왔다는 방증인데,
    0 이면 그 방증이 없다. 라벨은 둘 다 «비경쟁인수 Ⅲ» 이라 정적인 표로는
    못 가르므로 금액이 가른다. **설명은 걷지 않는다** — 그건 «이게 무엇인가»
    라 행사액과 무관하게 참이다.
    """
    zero = [
        a
        for a in day_detail("2026-07-16", MPC)["auctions"]
        if "비경쟁" in a["kind"] and not a["allotted"]
    ]
    assert zero, "그날 0억 비경쟁인수가 없어요 — 앵커가 바뀌었어요"
    ev = zero[0]["events"]
    assert [e["key"] for e in ev] == ["비경쟁"]
    assert ev[0]["dir"] is None, "안 오간 물량에 방향이 붙었어요"
    assert "옵션" in ev[0]["text"], "설명까지 같이 걷었어요"


# ── 민평: 못 내는 판정을 안 낸다 ────────────────────────────────────────────


def test_the_grade_normaliser_strips_the_agency_not_the_grade():
    """«AA-NICE» 는 AA- 다. 평가사 이름은 등급이 아니라 출처다."""
    assert mp.normalize_grade("AA-NICE") == "AA-"
    assert mp.normalize_grade(" aa+ ") == "AA+"
    # «AA» 와 «AA0» 은 같은 등급의 두 표기다(원화 관행은 AA0 이 정식).
    assert mp.normalize_grade("AA") == "AA0"
    assert mp.normalize_grade("A") == "A0"
    assert mp.normalize_grade("") is None
    assert mp.normalize_grade(None) is None


def test_a_mismatched_grade_gets_the_number_but_not_the_verdict():
    """섹터만 맞고 등급이 다르면 숫자는 내되 «오버/언더» 라고 안 부른다.

    −24bp 의 대부분이 가격이 아니라 등급 차이인데 «언더 24bp» 라고 적으면
    그건 거짓말이다. 화면이 커브 이름과 이 종목의 등급을 같이 적는다.
    """
    got = mp._judge(-24.0, matched=False)
    assert got == (None, None)
    assert mp._judge(-24.0, matched=True)[0] == "언더"
    assert mp._judge(+3.3, matched=True)[0] == "오버"
    # 0.5bp 아래는 반올림의 영역이다 — 민평이 소수 셋째 자리까지 고시된다.
    assert mp._judge(+0.3, matched=True)[0] == "민평"


def test_a_number_that_cannot_be_a_krw_fixed_coupon_gets_no_verdict():
    """±100bp 밖이면 판정을 안 낸다.

    **실측 앵커, 2026-08-21:** 현대커머셜 579 가 표면 2.2% 로 올라와 캐피탈채
    AA- 민평 대비 −224bp 가 나왔다 — CNH 표시 채권이다. DART 공시에 통화 칸이
    없어서 앞에서 거를 방법이 없고, 이 문턱 하나가 외화표시·변동금리·할인채·
    자료 오류를 함께 잡는다.
    """
    side, why = mp._judge(-224.1, matched=True)
    assert side is None
    assert why and "원화 고정이표채가 아닌" in why
    # 멀쩡한 발행은 안 자른다 — 실측 범위가 국고 ±12.6bp, 크레딧 −13~+33bp 다.
    assert mp._judge(+33.1, matched=True)[0] == "오버"


def test_the_bond_code_carries_the_maturity_month_not_the_day():
    """`국고03375-3206` = 표면 3.375%, 만기 2032년 06월. 일자는 원발행일의 것이다."""
    assert mp._ktb_maturity("국고03375-3206", dt.date(2022, 6, 10)) == (
        "국고",
        dt.date(2032, 6, 10),
    )
    # 월말 발행이 짧은 달에 떨어져도 조립이 안 깨진다.
    assert mp._ktb_maturity("국고02000-3102", dt.date(2021, 2, 28))[1] == dt.date(
        2031, 2, 28
    )
    # 재정증권은 코드에 만기가 없다 — 제목의 «63일물» 이 유일한 단서다.
    assert mp._ktb_maturity("재정증권2023-001", dt.date(2023, 1, 5)) is None


@needs_mp
def test_an_inflation_linker_is_not_measured_against_a_nominal_curve():
    """물가채 낙찰금리는 실질금리다. 명목 민평과 견주면 −100bp 대가 나온다."""
    got = mp.for_auction(
        mp.matrix(),
        code="물가01125-3406",
        bid_date=dt.date(2026, 8, 7),
        issue_date=dt.date(2024, 6, 10),
        wavg=1.2,
    )
    assert got["side"] is None
    assert "실질금리" in got["why"]


@needs_mp
def test_a_sector_without_a_curve_says_so():
    """증권·지주·보험은 견줄 등급 커브가 없다. 회사채 커브로 때우지 않는다."""
    got = mp.for_issue(
        mp.matrix(),
        sector="지주",
        grade_raw="AAA",
        filed=dt.date(2026, 8, 12),
        paid=dt.date(2026, 8, 13),
        maturity=dt.date(2029, 8, 13),
        coupon=4.0,
    )
    assert got["side"] is None
    assert "지주" in got["why"]


# ── 붙어서 나가는지 ─────────────────────────────────────────────────────────


@needs_data
@needs_mp
def test_the_auction_carries_its_distance_from_the_market():
    """2026-08-10 3년물 경쟁입찰이 실측 앵커다.

    가중평균 3.780%, 그날 국고 민평 3.747% → **+3.3bp 오버**. 잔존은 2.84Y 이지
    3Y 가 아니다 — 통합발행이라 연물 이름과 실제 잔존이 다르고, 커브를 연물
    이름으로 읽으면 그 차이만큼 틀린다.
    """
    comp = [
        a for a in day_detail("2026-08-10", MPC)["auctions"] if a["kind"] == "경쟁입찰"
    ]
    assert comp, "그날 경쟁입찰이 없어요"
    m = comp[0]["mp"]
    assert m["curve"] == "국고채"
    assert m["side"] == "오버"
    assert m["bp"] == pytest.approx(3.3, abs=0.2)
    assert m["years"] == pytest.approx(2.84, abs=0.02)
    assert m["asof"] == "2026-08-10"


@needs_data
@needs_mp
def test_the_issue_carries_its_distance_from_the_market():
    """등급이 커브와 다르면 **숫자는 내되 판정은 안 낸다.**

    원 앵커는 2026-08-13 하나카드 307 이었다: 표면 4.356% · AA0 인데 잣대는
    카드채 **AA+** 커브라 등급이 갈리고, 그래서 bp 는 나오되 오버·언더는
    안 부른다. 기준일은 제출일이지 납입기일이 아니다.

    ⚠ 그 날짜를 못 박아 뒀더니 **시험이 낡았다** [2026-09-15]. 발행 자료는
    굴러가는 창이고(지금 시작이 2026-08-21), 앵커가 창 밖으로 나가자 「그날
    하나카드 발행이 없어요」로 떨어졌다 — 배선이 깨진 게 아니라 날짜가 샌 것이다.
    그래서 이제 **자료에서 사례를 찾아** 성질을 잰다. 사례가 하나도 없으면
    그것도 실패다(빈 표를 통과로 읽지 않는다).
    """
    days = sorted(day for day in _issuing_days())
    assert days, "발행이 있는 날이 하나도 없어요 — 자료가 비었어요"

    mismatched = [
        (day, r)
        for day in days
        for r in day_detail(day, MPC)["issuing"]
        if r.get("mp") and r["mp"].get("match") is False
    ]
    assert mismatched, "등급이 커브와 다른 발행이 창 안에 하나도 없어요"

    for day, r in mismatched:
        m = r["mp"]
        who = f"{day} {r['issuer']}"
        assert m["side"] is None, f"{who}: 등급이 다른데 오버·언더라고 불렀어요"
        assert m["curve"] and m["grade"], f"{who}: 커브·등급을 안 적었어요"
        assert m["curve"].split()[-1] != m["grade"], f"{who}: match=False 인데 등급이 같아요"
        # 숫자는 낸다 — 판정만 안 내는 것이 이 규칙이다.
        assert m["rate"] is not None, f"{who}: 숫자까지 지웠어요"
        # 기준일은 **그날 이전**이다(제출일). 납입기일을 쓰면 미래를 보는 것이다.
        assert m["asof"] < day, f"{who}: 기준일({m['asof']})이 발행일 이후예요"


@needs_data
def test_the_meeting_is_the_first_thing_the_cell_says():
    """칸은 두 줄까지만 적고 나머지는 «+N» 이다. 뒤에 놓인 것은 안 보인다.

    **실측 결함, 2026-08-21:** 첫 판이 입찰 → 공개시장운영 → 금통위 순이라
    2026-07-16 인상 결정이 «+2» 뒤에 숨었다. 그날 하나만 볼 수 있다면 그건
    금통위다.
    """
    days = build(months_from(2026, 7, 1), MPC, today=dt.date(2026, 8, 20))["months"][
        "2026-07"
    ]["days"]
    day = next(d for d in days if d["iso"] == "2026-07-16")
    assert len(day["ev"]) > 2, "이 날은 일정이 셋 이상이라 순서가 뜻을 갖는다"
    assert day["ev"][0]["lane"] == "mpc"
    assert day["ev"][0]["dir"] == "약세", "그날 0.25%p 인상했다"


@needs_data
def test_a_meeting_without_a_decision_has_no_direction_yet():
    """열린 회의와 안 열린 회의는 다른 사실이다. 방향도 그렇다.

    안 열린 쪽은 날짜를 박지 않는다 — 박아 두면 그날이 오는 순간 결정이 생겨
    전제가 만료된다(2026-08-27 이 그렇게 깨졌다). 달력에만 있는 미래 회의로
    상태를 만든다. 열린 쪽은 2026-07-16 인상이 앵커다.
    """
    assert day_detail("2026-07-16", MPC)["mpc"]["bias"]["dir"] == "약세"  # 인상
    pending = (dt.date.today() + dt.timedelta(days=180)).isoformat()
    assert day_detail(pending, MPC + [pending])["mpc"]["bias"] is None


@needs_data
def test_a_day_without_a_graded_auction_has_no_direction_not_a_neutral_one():
    """«중립» 은 «평년 수준이라 안 민다» 는 판정이고, 여기는 잰 것이 없다.

    둘을 한 값으로 접으면 화면이 안 잰 것을 판정으로 읽는다. 2026-08-20 은
    비경쟁인수만 있던 날이라 등급이 없다.
    """
    days = {
        d["iso"]: d["ev"]
        for d in build(months_from(2026, 8, 1), MPC, today=dt.date(2026, 8, 20))[
            "months"
        ]["2026-08"]["days"]
    }
    ktb = {
        iso: [e["dir"] for e in ev if e["lane"] == "ktb"] for iso, ev in days.items()
    }
    assert ktb["2026-08-20"] == [None]
    assert ktb["2026-08-10"] == ["약세"], "그날 3년물은 등급이 났어요"
    # 방향이 붙은 이상 그 한계도 달력에서 말해야 한다 — 상세를 안 열어 본
    # 사람이 색만 보고 간다.
    caveats = build(months_from(2026, 8, 1), MPC, today=dt.date(2026, 8, 20))["caveats"]
    assert any("BIAS_IS_THE_MATERIAL" in c for c in caveats)


@needs_data
def test_the_open_market_operation_carries_both_a_direction_and_a_size():
    """방향만 있고 규모가 없으면 흡수 1천억과 흡수 3조가 같은 무게로 읽힌다.

    `annotate_omo` 는 이식할 때 같이 왔지만 첫 판에서 안 불렀다. 방향을
    붙이면서 같이 켰다.
    """
    rows = day_detail("2026-08-20", MPC)["omo"]
    assert rows, "그날 공개시장운영이 없어요"
    rp = [o for o in rows if o["kind"] == "RP매각"]
    assert rp
    # 설명과 방향은 한 벌로 온다 — 따로 내면 같은 문단이 두 번 찍힌다.
    assert [e["dir"] for e in rp[0]["events"]] == ["약세"]
    s = rp[0]["strength"]
    assert s["dir"] == "흡수"
    assert s["size"] in {"큰 규모", "보통 규모", "작은 규모"}
    # 기준금리를 결과표에서 뽑아 넘기므로 스프레드가 선다.
    assert s["base"] is not None and s["spread"] is not None


@needs_data
def test_the_calendar_stands_without_the_market_prices(monkeypatch):
    """**이 배선의 계약.** SQL 이 없는 PC 에서 캘린더 전체가 같이 죽으면 안 된다.

    CSV 는 잡히는데 SQL 이 안 잡히는 PC 가 있다. 그때 오버·언더만 빠지고
    나머지는 그대로 서야 하고, `mp.note` 가 왜 없는지를 말해야 한다.
    """
    def dead():
        raise mp.Unavailable("SQL 이 안 잡혀요")

    monkeypatch.setattr(mp, "matrix", dead)
    d = day_detail("2026-08-10", MPC)
    assert d["mp"]["note"] and "민평" in d["mp"]["note"]
    assert d["mp"]["caveat"] is None
    assert d["auctions"] and all(a["mp"] is None for a in d["auctions"])
    # 방향은 민평과 무관하다 — 응찰 강도에서 나온다.
    assert any(a["bias"] for a in d["auctions"])


@needs_mp
def test_the_benchmark_is_named_as_a_grade_curve_not_an_issuer_quote():
    """개별종목 민평은 이 데이터에 없다. 없는 것을 있는 척하지 않는다.

    `sim_portfolio` 스키마에 종목 단위 시가평가 표가 없다(실측 2026-08-21).
    있는 것은 (종목군 × 등급) × 테너의 격자뿐이고, 화면이 그 이름을 적는다.
    """
    assert "등급 커브" in mp.CAVEAT
    for bt, _grade in mp.SECTOR_CURVE.values():
        assert bt in creditmatrix.BOND_TYPES
        # 커브 이름에 등급이 박혀 있어야 화면이 그걸 그대로 적을 수 있다.
        assert creditmatrix.BOND_TYPES[bt].split()[-1] in {"AAA", "AA+", "AA-"}


def test_the_lane_bias_says_the_market_reacts_to_surprise():
    """방향을 적는 자리마다 이 한 줄이 따라간다.

    없으면 «인상인데 왜 금리가 내렸지» 가 화면의 결함으로 보인다. 방향을 안
    붙이는 것보다 방향과 그 한계를 같이 적는 것이 낫다.
    """
    from app.issuance_gloss import BIAS_CAVEAT, explain

    assert "기대와의 차이" in BIAS_CAVEAT
    for lane in ("iss", "ktb", "omo", "pol"):
        g = explain(lane)
        assert g["bias"]["dir"]
        assert g["biasCaveat"] == BIAS_CAVEAT
    # 금통위·공개시장운영·국고채 입찰은 결과가 방향을 정한다 — 레인 자체는 갈린다.
    assert explain("pol")["bias"]["dir"] == BOTH
    assert explain("omo")["bias"]["dir"] == BOTH
    assert explain("ktb")["bias"]["dir"] == BOTH
