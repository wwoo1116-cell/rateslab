# -*- coding: utf-8 -*-
"""발행 캘린더 (`app/issuance.py`).

이 파일에서 하중을 지는 것은 `test_the_strength_module_is_a_verbatim_copy` 다.
나머지는 페이로드의 모양을 기술하지만, 그 하나는 **같은 입찰에 두 판정이 생기는
것**을 막는다.

`issuance_strength.py` 는 `Codex/rawData/src/strength.py` 를 글자 그대로 옮긴
것이다. 손대면 발행 캘린더의 원본 화면과 이 화면이 같은 입찰에 다른 등급을 붙이고,
그건 화면이 아니라 데이터의 문제로 보인다.

CSV 가 없는 환경(다른 PC·CI)에서는 데이터를 읽는 검사만 건너뛴다. 건너뛴 검사는
아무것도 보증하지 않으므로, 사본 대조는 CSV 와 무관하게 늘 돈다.
"""

import datetime as dt
import pathlib

import pytest

from app import issuance
from app.issuance import IssuanceUnavailable, build, day_detail, months_from
from app.policy import MPC_DATES

MPC = [d.isoformat() for d in MPC_DATES]

#: 원본. 없으면 사본 대조만 건너뛴다 — 이 리포 밖의 파일이다.
ORIGINAL = pathlib.Path(
    r"C:\Users\infomax\Projects\apps\rawdata\src\strength.py"
)


def _has_data() -> bool:
    try:
        issuance.data_stamp()
        return True
    except IssuanceUnavailable:
        return False


needs_data = pytest.mark.skipif(not _has_data(), reason="rawData CSV 가 없는 환경")


def test_the_strength_module_is_a_verbatim_copy():
    """판정 코드가 원본과 글자 그대로 같다.

    머리글(docstring)만 다르다 — 이식 사실과 되돌아가는 길을 적었다. 그 아래
    본문이 한 글자라도 갈리면 두 화면이 같은 입찰에 다른 등급을 붙인다.
    """
    if not ORIGINAL.exists():
        pytest.skip("원본 리포가 이 PC 에 없음")
    mine = pathlib.Path(issuance.__file__).with_name("issuance_strength.py")
    body = lambda p: p.read_text(encoding="utf-8").split('"""', 2)[2]  # noqa: E731
    assert body(ORIGINAL) == body(mine), "판정 코드가 원본과 갈렸어요"


def test_unavailable_names_the_path():
    """CSV 를 못 읽으면 화면이 이유를 말할 수 있어야 한다."""
    old = issuance.DATA_DIR
    try:
        issuance.DATA_DIR = pathlib.Path("Z:/없는경로")
        with pytest.raises(IssuanceUnavailable) as e:
            issuance.data_stamp()
        assert "없는경로" in str(e.value)
    finally:
        issuance.DATA_DIR = old


def test_months_from_wraps_the_year():
    assert months_from(2026, 11, 3) == [(2026, 11), (2026, 12), (2027, 1)]


@needs_data
def test_a_month_grid_is_every_weekday_of_the_month():
    """한 달치 평일이 하나도 안 빠지고 온다.

    토·일을 뺀 뒤에도 «달의 전부» 라는 성질은 지켜야 한다 — 중간이 비면 화면이
    그걸 «그날 아무 일도 없었다» 로 보여주는데, 사실은 서버가 안 보낸 것이다.
    """
    m = build(months_from(2026, 8, 1), MPC, today=dt.date(2026, 8, 20))["months"]["2026-08"]
    weekdays = [
        d
        for d in (dt.date(2026, 8, i) for i in range(1, 32))
        if d.weekday() < 5
    ]
    assert [d["iso"] for d in m["days"]] == [d.isoformat() for d in weekdays]
    # 2026-08-03(월)이 첫 평일 — 앞 여백 없음.
    assert m["lead"] == 0


@needs_data
def test_the_substitute_holiday_is_not_a_business_day():
    """2026-08-15(광복절)이 토요일이라 8/17(월)이 대체공휴일이다.

    영업일 판정을 이 리포의 것(`engine_port._is_kr_business_day`)에 맡긴 이유가
    이것이다 — 대체공휴일을 손으로 관리하면 해마다 틀린다.
    """
    p = build(months_from(2026, 8, 1), MPC, today=dt.date(2026, 8, 20))
    biz = {d["d"]: d["biz"] for d in p["months"]["2026-08"]["days"]}
    assert biz[17] is False, "대체공휴일이 영업일로 잡혔어요"
    assert biz[18] is True


@needs_data
def test_sectors_keep_their_seat_even_at_zero():
    """발행이 0 인 섹터도 목록에서 안 빠진다 — 날마다 늘었다 줄었다 하면 필터가
    어디 있었는지 못 찾는다(원본의 규칙)."""
    p = build(months_from(2026, 8, 1), MPC, today=dt.date(2026, 8, 20))
    assert [s["k"] for s in p["sectors"]] == issuance.SECTORS


def _latest_filing_day() -> dt.date:
    """발행 파이프라인의 **마지막 제출일**.

    DART 파이프라인 CSV 는 수집기가 **최근 30일 창**으로 다시 쓴다(rawData README
    「DART 파이프라인 (최근 30일)」). 그래서 달을 손으로 박은 픽스처(2026-08)는 한
    달 뒤에 저절로 비었고, 그 실패는 「수집기가 멈췄다」로 읽혔다 — 실측 2026-09-28,
    수집기는 그날 아침에도 정상이었다. 자료가 있는 달은 자료가 말하게 한다.
    """
    stamps = sorted({(r.get("제출일") or "").replace("-", "")[:8]
                     for r in issuance._read("pipeline")})
    stamps = [s for s in stamps if len(s) == 8 and s.isdigit()]
    assert stamps, "발행 파이프라인 CSV 에 제출일이 하나도 없어요"
    return dt.datetime.strptime(stamps[-1], "%Y%m%d").date()


@needs_data
def test_the_server_does_not_pre_sum_the_sectors():
    """하루치가 섹터별로 갈려 있어야 화면의 필터가 달력을 바꿀 수 있다.

    달은 **자료가 있는 달**이다(`_latest_filing_day`) — 마지막 제출일의 달과 그
    전달 중 발행이 서는 쪽. 창이 30일이라 월초에는 마지막 제출일의 달이 며칠
    분밖에 없을 수 있어 둘을 본다.
    """
    last = _latest_filing_day()
    prev = (last.replace(day=1) - dt.timedelta(days=1))
    days: list[dict] = []
    for y, m in ((last.year, last.month), (prev.year, prev.month)):
        p = build(months_from(y, m, 1), MPC, today=last)
        days = [d for d in p["months"][f"{y}-{m:02d}"]["days"] if d["isec"]]
        if days:
            break
    assert days, f"{last} 기준 최근 두 달에 발행이 하나도 없어요 — 수집기를 보세요"
    assert all(isinstance(d["isec"], dict) and d["isec"] for d in days)
    assert all(set(d["isn"]) <= set(d["isec"]) for d in days)


@needs_data
def test_the_horizon_is_reported():
    """발행 공시가 닿는 끝과 입찰 결과가 나온 끝. 그 뒤의 빈칸은 «없음» 이 아니다."""
    p = build(months_from(2026, 8, 1), MPC, today=dt.date(2026, 8, 20))
    assert p["issuanceThrough"] and p["auctionThrough"]
    assert any("SHELF_HORIZON" in c for c in p["caveats"])
    assert any("ISSUANCE_ONLY" in c for c in p["caveats"])


@needs_data
def test_a_scheduled_meeting_without_a_decision_is_not_the_same_as_no_meeting():
    """달력에는 있고 결과표에는 아직 없는 날.

    한 필드에 접으면 «회의가 없는 날» 과 «회의는 있는데 아직 안 열린 날» 이
    구분되지 않는다 — 화면이 «오늘 금통위예요, 결과는 아직» 을 말할 수 있어야 한다.

    **날짜를 박지 않는다.** 예전에는 «다음 회의» 였던 2026-08-27 을 박아 뒀는데,
    그날이 오고 금통위가 인상하면서 전제가 만료돼 시험이 깨졌다(2026-09-01).
    `mpc.csv` 는 `rawDataWatch` 가 5분마다 갱신하므로 다음 회의 날짜로 바꾸는
    것은 폭탄을 재장전하는 것이다. 재는 것은 날짜가 아니라 **상태**이므로,
    결과표가 영원히 가질 수 없는 미래 회의를 달력에만 넣어 그 상태를 만든다.
    """
    pending = (dt.date.today() + dt.timedelta(days=180)).isoformat()
    upcoming = day_detail(pending, MPC + [pending])["mpc"]
    # `bias` 가 2026-08-21 에 늘었다. 결정이 아직이면 방향도 아직이다 —
    # 그 성질은 `test_issuance_mp.py` 가 따로 잠근다.
    assert upcoming == {"scheduled": True, "decision": None, "bias": None}
    # 같은 날이라도 달력에 없으면 «회의가 없는 날» 이다 — 갈리는 것은 그 한 칸뿐.
    assert day_detail(pending, MPC)["mpc"] is None
    assert day_detail("2026-08-10", MPC)["mpc"] is None


@needs_data
def test_the_auction_strength_rides_along():
    """같은 연물 52주 판정이 그날 상세에 붙는다.

    2026-08-10 의 3년물 경쟁입찰이 실측 앵커다 — 응찰률 257.3%, 평년 271.9%,
    등급 «약한 수요». 이 값이 바뀌면 판정 코드나 데이터가 바뀐 것이다.
    """
    comp = [
        a for a in day_detail("2026-08-10", MPC)["auctions"] if a["kind"] == "경쟁입찰"
    ]
    assert comp, "그날 경쟁입찰이 없어요"
    s = comp[0]["strength"]
    assert s is not None
    assert s["label"] == "3년물"
    assert s["pct"] is not None, "표본이 있는데 등급을 안 냈어요"
    assert 0 <= s["pct"] <= 100


@needs_data
def test_weekends_are_dropped_but_weekday_holidays_stay():
    """토·일은 격자에서 빠지고 평일 공휴일은 남는다 [OWNER, 2026-08-20].

    잃는 것이 없다 — 입찰·공개시장운영·금통위는 영업일에만 서고 발행 납입일은
    Following 으로 이미 밀려 있다. 반대로 평일 공휴일은 정말로 «거래가 없던 날»
    이라 자리가 뜻이다(8/17 대체공휴일).
    """
    m = build(months_from(2026, 8, 1), MPC, today=dt.date(2026, 8, 20))["months"]["2026-08"]
    assert {d["dow"] for d in m["days"]} == {0, 1, 2, 3, 4}
    assert 17 in [d["d"] for d in m["days"]], "평일 공휴일이 같이 빠졌어요"
    # 1일(토)·2일(일)이 빠졌으므로 5열 격자의 앞 여백은 0 이다.
    assert m["lead"] == 0


def test_the_gloss_speaks_the_apps_register():
    """설명이 해요체다.

    원본은 합니다체다. 사실은 그대로 두고 어미만 옮겼다 — 한 화면에 두 목소리가
    서면 그게 곧 «디자인 통일성이 낮다» 는 것이다.
    """
    from app.issuance_gloss import LANE, explain

    text = " ".join(
        v or "" for lane in LANE.values() for v in lane.values()
    )
    assert "니다" not in text, "합니다체가 남았어요"
    # 받침 없는 말 뒤는 «예요» 다 — 눈으로 고르면 «업무이에요» 가 남는다.
    assert "업무예요" in explain("omo")["what"]


@needs_data
def test_the_day_carries_its_own_explanation():
    """판정만 남기고 설명이 사라지면 «강한 수요» 가 무엇을 잰 것인지 알 수 없다.

    서버가 문장의 단일 출처다 — 프런트에 두면 두 벌이 되고 한쪽만 고치면 갈린다.
    """
    d = day_detail("2026-08-10", MPC)
    assert set(d["gloss"]) == {"iss", "ktb", "omo", "mpc"}
    ktb = d["gloss"]["ktb"]
    assert ktb["title"] == "국고채 입찰"
    assert "응찰률" in (ktb["note"] or ""), "응찰률을 어떻게 읽는지가 빠졌어요"
    # 라벨에 걸리는 덧붙임도 같이 온다(그날 비경쟁인수가 있다). 설명과 방향은
    # **한 벌**이다 — 따로 내면 같은 문단이 두 번 찍힌다.
    assert any(a["events"] for a in d["auctions"])


@needs_data
def test_issuance_only():
    """만기도래는 페이로드에 없다 [OWNER].

    2026-08-21 에 넷이 늘었다 — `mp`(민평을 못 읽는 PC 에서 «왜 오버·언더가
    없나» 를 말할 자리)·`res`(지준)·`sum`(그날 규모)·`src`(출처). 만기도래는
    여전히 없다.
    """
    d = day_detail("2026-08-10", MPC)
    assert set(d) == {
        "date", "gloss", "issuing", "auctions", "omo", "mpc",
        "mp", "res", "sum", "src",
    }
    assert all("maturityDue" not in r for r in d["issuing"])
    # 발행은 서버가 안 센다 — 섹터 필터가 목록을 줄이면 머리의 건수와
    # 아래 목록의 길이가 어긋난다. 화면이 자기가 그리는 것을 센다.
    assert "issN" not in d["sum"] and "issJo" not in d["sum"]


@needs_data
def test_the_reserve_lane_stands_on_the_published_table():
    """지준이 달력에 선다 [OWNER, 2026-08-21 — 지시에 짚은 레인].

    설명과 방향은 `issuance_gloss` 에 처음부터 있었는데 **데이터가 없어** 한 번도
    뜬 적이 없었다. 한국은행 공표표를 실어 그 자리를 채웠다.
    """
    p = build(months_from(2026, 8, 1), MPC, today=dt.date(2026, 8, 21))
    days = {d["iso"]: [e["label"] for e in d["ev"]] for d in p["months"]["2026-08"]["days"]}
    assert "지준 마감" in days["2026-08-05"]
    assert "지준 시작" in days["2026-08-06"]
    # 상세는 남은 날수를 센다 — 마감이 다가올수록 조정이 단기자금으로 몰린다.
    r = day_detail("2026-08-06", MPC)["res"]
    assert r["kind"] == "지준 시작" and r["days"] == 35
    assert r["gloss"]["title"] == "지급준비금"
    assert day_detail("2026-08-10", MPC)["res"] is None


@needs_data
def test_the_meeting_leads_and_the_reserve_follows():
    """칸은 두 줄까지만 적는다. 순서가 곧 위계다 — 금통위 → 지준 → 입찰 → 조작."""
    p = build(months_from(2026, 8, 1), MPC, today=dt.date(2026, 8, 21))
    days = {d["iso"]: [e["lane"] for e in d["ev"]] for d in p["months"]["2026-08"]["days"]}
    assert days["2026-08-06"][0] == "res", "지준이 공개시장운영 뒤로 밀렸어요"
    assert days["2026-08-05"][0] == "res"


@needs_data
def test_every_lane_names_where_its_numbers_came_from():
    """출처 한 줄. **원본이 화면 바닥에 적던 것**을 v2 가 빼먹고 있었다.

    응찰 강도가 «약한 수요» 라고 말하는데 그 숫자가 어느 공고에서 왔는지가
    화면에 없었다.
    """
    src = day_detail("2026-08-10", MPC)["src"]
    assert set(src) == {"iss", "ktb", "omo", "mpc", "res"}
    for lane, v in src.items():
        assert v["who"] and v["what"] and v["url"].startswith("https://"), lane


@needs_data
def test_the_day_carries_its_own_size():
    """열자마자 그날 규모가 보이게. 흡수와 공급은 **상계하지 않는다**.

    순액 하나로 누르면 «3조 흡수 + 3조 공급» 이 «0» 이 되는데, 그 둘은 같은 날
    다른 창구로 오간 진짜 물량이다.
    """
    s = day_detail("2026-08-18", MPC)["sum"]
    assert set(s) == {"ktbWon", "ktbN", "omoAbsorb", "omoSupply"}
    assert s["omoSupply"] > 0, "그날 RP매입과 통안 중도환매가 있었어요"
