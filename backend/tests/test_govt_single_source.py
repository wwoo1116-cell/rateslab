"""국고 커브는 **하나의 창구**다 [OWNER 2026-09-22 "하나로 통합해서 SQL에서"].

## 왜 이 파일이 생겼나 — 트레이더가 먼저 알아챘다

> "메인부터 시작해서 지금 전략까지 오면서 BSS나 IRS, 국고채와 같은 프로덕트에
>  대한 로직이 잘못된거 같다"

전수조사에서 나온 것: 국고 출처가 앱에 **둘**이었다. Main·Backtest·Simulation·
RV 는 민평(`credit_matrix`), MR/Strategy 의 BSS 만 긴 표본(`imx_data.timeseries`
국고채커브). 그리고 그 긴 표본이 **정수년이 아닌 만기에서 멈췄다** — 2026-09-11
이후 3월·6월·9월·1.5년·2.5년·15년이하에 새 행이 없다.

그래서 BSS 6M·9M·1.5Y 가 열흘 낡은 값이었고, 같은 국고 1.5Y 가 Main 에서는
3.940 · MR 의 BSS 계산에서는 3.825 였다(11.5bp). 보드의 asof 는 **가족 단위**라
그 사실이 화면에 안 드러났다 — 이 리포가 「조용히 낡는다」라고 부르는 그 자리다.

이 시험이 지키는 것은 **수가 아니라 구조**다: 두 창구가 오늘 같은 수를 말하는가,
그리고 한 만기가 뒤처지면 그것이 드러나는가.
"""

from __future__ import annotations

import pytest

pytest.importorskip("app.mrseries")

from app import creditmatrix as cm  # noqa: E402
from app import mrseries as mrs  # noqa: E402

#: BSS 가 실제로 세우는 만기 — `mr.SERIES` 의 그 아홉.
BSS_TENORS = ("6M", "9M", "1Y", "1.5Y", "2Y", "3Y", "5Y", "7Y", "10Y")


@pytest.fixture(scope="module")
def sources():
    try:
        b = mrs.bundle()
        m = cm.load()
    except BaseException as exc:                            # noqa: BLE001
        pytest.skip(f"SQL 을 못 읽어요: {exc}")
    dates = [d.isoformat() if hasattr(d, "isoformat") else str(d)[:10] for d in m.dates]
    return b, m, dates


def test_국고_다리가_민평과_같은_수다(sources):
    """오늘 값이 갈리면 화면마다 다른 국고를 말하게 된다 — 그게 이 수리의 이유다."""
    b, m, dates = sources
    for t in BSS_TENORS:
        if not m.has("KTB", t):
            continue
        ser = m.series("KTB", t)
        last_cm = next(v for v in reversed(ser) if v is not None)
        got = b["ktb"].get(t)
        assert got, f"{t}: 통합 창구에 국고가 없다"
        assert got[max(got)] == pytest.approx(last_cm, abs=1e-9), (
            f"{t}: 통합 국고가 민평과 다르다 — 화면마다 다른 수가 된다")


def test_국고_다리가_안_뒤처진다(sources):
    """한 만기만 멈춰도 BSS 그 줄이 낡는다. 09-11 사고가 그것이었다."""
    b, m, dates = sources
    newest = max(max(v) for v in b["ktb"].values())
    for t in BSS_TENORS:
        got = b["ktb"].get(t)
        if not got:
            continue
        assert max(got) == newest, (
            f"{t}: 국고가 {max(got)} 에서 멈춰 있다(가장 새 날 {newest}) — "
            "BSS 그 줄이 낡은 값으로 선다")


def test_민평_구간은_단일_출처다(sources):
    """2020 이후로는 민평 하나만 쓴다 — 연말 여섯 날을 버리고 얻은 것이 이것이다.

    긴 표본에만 있는 날을 채우면 1년에 한 번 출처가 갈리는 봉이 살아 있는 창에
    들어온다(짧은 만기에서 그 차가 최대 3.5bp).
    """
    b, m, dates = sources
    cm_days = {dates[i] for i, v in enumerate(m.series("KTB", "3Y")) if v is not None}
    got = b["ktb"]["3Y"]
    after = {d for d in got if d >= mrs.GOVT_SPLICE_FROM}
    assert after <= cm_days, "민평에 없는 날이 통합 커브에 들어왔다"


def test_긴_표본이_2020_이전을_그대로_잇는다(sources):
    """민평은 2020-01 부터다. 그 앞이 사라지면 BSS 표본이 6.7년으로 반토막 난다."""
    b, _m, _dates = sources
    got = b["ktb"]["3Y"]
    assert min(got) < "2015-01-01", "긴 표본이 안 이어졌다"
    assert len(got) > 3000, f"표본이 {len(got)}일뿐이다 — 긴 꼬리가 끊겼다"


# ── 장이 쉰 날의 행은 종가가 아니다 [전수조사 2026-10-15] ─────────────────────
#
# 전수조사 둘째 판에서 나온 것: `mkt_irs_close` 의 휴일 복사 행을 자르는 컷이
# `dataset._finalize` 에만 있고 이 **긴 표본** 로더에는 없었다. 그래서 IRC·IRF
# 12계열이 전영업일의 복사본 9행을 관측으로 세고 있었다(최근 260일의 3.1%).
#
# BSS·FUT 가 깨끗했던 것은 규칙이 아니라 사고였다 — `legs()` 가 국고 ∩ 스왑을
# 교집합하고 국고에 휴일 행이 없어서 떨어졌을 뿐이다. 그래서 이 시험이 재는 것은
# 「BSS 가 깨끗한가」가 아니라 **로더가 자르는가**다.

def test_컷은_달력을_다시_구현하지_않는다():
    """★엔진 달력 하나다. 요일로 세면 달력이 둘이 되고, 그것이 같은 전수조사에서
    잡힌 둘째 결함(`universe._age` — 휴일을 모르는 복제본)이다."""
    import inspect

    src = inspect.getsource(mrs._cut_holidays)
    assert "_is_kr_business_day" in src
    assert "weekday" not in src, "요일로 세면 휴일을 모르는 둘째 달력이 생긴다"


def test_로더가_비영업일_행을_버린다():
    """달력은 엔진 것을 그대로 쓰고, 세 가족 전부에서 버린다 — 교집합이 지켜
    주기를 기대하지 않는다(그것이 BSS 를 지켜 준 「사고」였다)."""
    import datetime as dt

    holiday = "2026-05-05"          # 어린이날 — 엔진 달력의 비영업일
    biz = "2026-05-04"
    from app.engine_port import _is_kr_business_day
    assert not _is_kr_business_day(dt.date.fromisoformat(holiday))
    assert _is_kr_business_day(dt.date.fromisoformat(biz))

    got = mrs._cut_holidays({
        "ktb": {"3Y": {biz: 3.0, holiday: 3.0}},
        "irs": {"3Y": {biz: 3.1, holiday: 3.1}, "10Y": {biz: 3.5, holiday: 3.5}},
        "cd":  {biz: 3.25, holiday: 3.25},
    })
    assert list(got["ktb"]["3Y"]) == [biz]
    assert list(got["irs"]["3Y"]) == [biz] and list(got["irs"]["10Y"]) == [biz]
    assert list(got["cd"]) == [biz]


def test_긴_표본에_비영업일_행이_하나도_없다(sources):
    """산 SQL 로 — 세 가족 전부. 종전에는 `irs` 에 9행이 살아 있었다."""
    import datetime as dt

    from app.engine_port import _is_kr_business_day
    b, _m, _dates = sources
    bad: dict[str, list[str]] = {}
    for fam in ("ktb", "irs"):
        days = {d for ser in b[fam].values() for d in ser}
        out = sorted(d for d in days
                     if not _is_kr_business_day(dt.date.fromisoformat(d)))
        if out: bad[fam] = out
    out = sorted(d for d in b["cd"]
                 if not _is_kr_business_day(dt.date.fromisoformat(d)))
    if out: bad["cd"] = out
    shown = {k: v[:5] for k, v in bad.items()}
    assert not bad, f"휴일 행이 살아 있어요: {shown}"


def test_커브_플라이도_깨끗하다(sources):
    """★여기가 종전에 새던 자리다 — `combo_points` 는 스왑 ∩ 스왑이라 교집합이
    아무것도 안 떨어뜨린다."""
    import datetime as dt

    from app import mr as mr_mod
    from app.engine_port import _is_kr_business_day
    checked = 0
    for sid, _label, kind in mr_mod.SERIES:
        if kind not in ("irc", "irf"):
            continue
        pts = mr_mod.series_points(sid)["points"]
        bad = [p["t"] for p in pts
               if not _is_kr_business_day(dt.date.fromisoformat(p["t"]))]
        assert not bad, f"{sid} 에 휴일 행 {len(bad)}개: {bad[:5]}"
        checked += 1
    assert checked == 12, f"IRC 8 + IRF 4 를 다 봐야 한다 (봤다: {checked})"
