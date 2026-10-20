# -*- coding: utf-8 -*-
"""국고채 발행 통계 — SQL 판 (`app/ktb_issuance.py`) [2026-10-19].

선례는 `test_flow.py` 다: `_fetch` 대신 `set_data` 로 주입해 **SQL 없이** 잰다.

이 파일이 지는 명제 다섯:
    ① 종목은 발행일·만기일로 만기물이 풀리고, 분리채는 안 센다.
    ② 물가채는 제목을 **직접 지어** 넘겨서 명목 10년과 섞이지 않는다(원문 제목의 함정).
    ③ 공급 = 경쟁 + 비경쟁Ⅱ·Ⅲ − 매입. 일반인은 PD 가 아니라 빠진다. 억→백만원 ×100.
    ④ 공급을 현물 날짜축에 얹을 때 없는 날은 다음 날로 넘기고, 축 뒤는 세어서 말한다.
    ⑤ 면 한 장이 서고 문장은 해요체다.
"""
from __future__ import annotations

import datetime as dt
import re

import pytest

from app import ktb_issuance as ki

UPD = dt.datetime(2026, 10, 19, 2, 35, 3)


def _raw(date: str, kind: str = "경쟁", tenor: str | None = "3",
         name: str = "국고03500-2906", isin: str = "KR103501GG62",
         amt: float = 24000, ratio: float | None = 277.6, rate: float | None = 3.94,
         title: str = "국고채 3년물 경쟁입찰 결과") -> dict:
    """SQL 한 행 — `ktb_auction_result` 의 열 이름 그대로."""
    return {
        "sn": f"S-{date}-{kind}", "구분": kind, "종목명": name, "isin": isin, "만기물": tenor,
        "입찰일": dt.date.fromisoformat(date), "행사시작일": None, "대금지급일": None, "발행일": None,
        "입찰금액": amt, "응찰금액": None if ratio is None else round(amt * ratio / 100),
        "응찰률": ratio, "응찰금리하": None, "응찰금리상": None,
        "낙찰금액": amt, "낙찰금리": rate, "최저낙찰금리": rate, "최고낙찰금리": rate,
        "부분낙찰률": 45.0, "기관수": None, "게시일": None, "제목": title,
        "created_at": UPD, "updated_at": UPD,
    }


TENOR_OF = {"KR103501GG62": "3Y", "KR103503GG60": "10Y", "KR103504GE95": "20Y"}


class Test만기물:
    def test_발행일과_만기일로_풀린다(self):
        assert ki.tenor_bucket(dt.date(2026, 6, 10), dt.date(2029, 6, 10), "3Y") == "3Y"
        assert ki.tenor_bucket(dt.date(2026, 9, 10), dt.date(2076, 9, 10), None) == "50Y"
        # 몇 달 어긋나도 가장 가까운 만기물로 간다(2.25년 → 2년물).
        assert ki.tenor_bucket(dt.date(2026, 3, 10), dt.date(2028, 6, 10), None) == "2Y"

    def test_물가는_소분류가_정하고_분리채는_안_센다(self):
        assert ki.tenor_bucket(dt.date(2026, 6, 10), dt.date(2036, 6, 10), "물가연동국채") == "물가"
        assert ki.tenor_bucket(dt.date(2026, 6, 10), dt.date(2036, 6, 10), "원금이자분리채권") is None
        assert ki.tenor_bucket(None, dt.date(2036, 6, 10), None) is None

    def test_표의_만기물_열은_열쇠로_바뀐다(self):
        assert ki.tenor_key("3") == "3Y"
        assert ki.tenor_key("물가") == "물가"
        assert ki.tenor_key(None) is None
        assert ki.tenor_key("7") is None


class Test정규화:
    def test_물가채_제목은_직접_짓는다(self):
        """원문 제목이 「국고채 10년물 … 및 물가연동국고채 발행금리」라 그대로 넘기면
        `tenor_of()` 가 명목 10년과 한 바구니에 넣는다(실측 2026-10-19)."""
        rows = ki.normalize([_raw(
            "2026-10-08", tenor="물가", name="물가01125-3606", isin="KR103503GG61",
            title='국고채 10년물 "국고01375-2912" 입찰결과 및 물가연동국고채 발행금리')],
            TENOR_OF)
        assert rows[0]["tenor"] == "물가"
        assert rows[0]["제목"] == "물가채 경쟁"
        assert "년물" not in rows[0]["제목"]

    def test_억이_백만원이_된다(self):
        rows = ki.normalize([_raw("2026-10-12", amt=24000)], TENOR_OF)
        assert rows[0]["amount"] == 2_400_000
        assert rows[0]["낙찰금액"] == 24000            # annotate 어휘는 억 그대로

    def test_매입은_isin_으로_만기물을_푼다(self):
        rows = ki.normalize([_raw("2026-09-16", kind="매입", tenor=None,
                                  name="국고02875-4409-20", isin="KR103504GE95",
                                  amt=8640, ratio=None, rate=None)], TENOR_OF)
        assert rows[0]["tenor"] == "20Y"
        assert rows[0]["kind"] == "매입"


class Test공급:
    @staticmethod
    def _rows():
        return ki.normalize([
            _raw("2026-10-12", amt=24000),                                       # 경쟁 3Y
            _raw("2026-10-15", kind="비경쟁Ⅱ", amt=5320, ratio=None, rate=None),   # 3Y
            _raw("2026-10-15", kind="비경쟁Ⅲ(스트립)", amt=3100, ratio=None, rate=None),
            _raw("2026-10-16", kind="매입", tenor=None, name="국고02875-4409-20",
                 isin="KR103504GE95", amt=8640, ratio=None, rate=None),       # 20Y 바이백
            _raw("2026-10-14", kind="일반인", amt=1, ratio=None, rate=None),      # PD 아님
        ], TENOR_OF)

    def test_경쟁_더하기_비경쟁_빼기_매입이고_일반인은_없다(self):
        s = ki.supply_by_day(self._rows())
        assert s["2026-10-12"] == 2_400_000
        assert s["2026-10-15"] == 842_000
        assert s["2026-10-16"] == -864_000
        assert "2026-10-14" not in s

    def test_만기물로_가른다(self):
        t = ki.supply_table(self._rows())
        assert t["3Y"]["2026-10-12"] == 2_400_000 and "2026-10-16" not in t["3Y"]
        assert t["20Y"]["2026-10-16"] == -864_000
        assert sum(t["ALL"].values()) == sum(sum(t[k].values()) for k in ki.TENORS)

    def test_현물_축에_얹을_때_없는_날은_다음_날로_간다(self):
        dates = ["2026-10-12", "2026-10-13", "2026-10-16"]
        got, pending = ki.align_supply(dates, {"2026-10-12": 10.0, "2026-10-15": 5.0,
                                               "2026-10-19": 7.0})
        assert got == [10.0, 0.0, 5.0]
        assert pending == 1                      # 10-19 는 축 뒤 — 지우지 않고 센다


class Test면:
    @staticmethod
    def _data() -> ki.IssuanceData:
        """3년 경쟁 여덟 달(강도가 서는 표본) + 10년 하나 + 비경쟁·매입·일정."""
        raw = [_raw(f"2026-{m:02d}-10", amt=24000 + m * 100, ratio=250.0 + m * 5)
               for m in range(1, 9)]
        raw.append(_raw("2026-08-24", tenor="10", name="국고04250-3606", isin="KR103503GG60",
                        amt=21000, ratio=286.0, rate=4.155, title="국고채 10년물 경쟁입찰"))
        raw.append(_raw("2026-08-13", kind="비경쟁Ⅱ", amt=5320, ratio=None, rate=None))
        raw.append(_raw("2026-08-19", kind="매입", tenor=None, name="국고02875-4409-20",
                        isin="KR103504GE95", amt=8640, ratio=None, rate=None))
        rows = ki.normalize(raw, TENOR_OF)
        sched = [{"date": "2026-08-31", "tenor": "5Y", "label": "5년물", "name": None,
                  "planned": None, "source": "calendar"},
                 {"date": "2026-08-01", "tenor": "2Y", "label": "2년물", "name": None,
                  "planned": None, "source": "calendar"}]
        return ki.IssuanceData(rows=rows, tenor_of=TENOR_OF, schedule=sched, watermark=("w", 1))

    @pytest.fixture
    def injected(self):
        ki.set_data(self._data())
        yield
        ki.set_data(None)

    def test_한_장이_선다(self, injected):
        b = ki.board()
        assert b["asof"]["auction"] == "2026-08-24"
        assert b["unit"] == "백만원"
        assert b["latest"]["tenor"] == "10Y" and b["latest"]["amount"] == 2_100_000
        assert [t["key"] for t in b["tenors"]] == list(ki.TENORS)
        t3 = next(t for t in b["tenors"] if t["key"] == "3Y")
        assert t3["ytdCount"] == 8 and t3["ytdNoncomp"] == 532_000
        t20 = next(t for t in b["tenors"] if t["key"] == "20Y")
        assert t20["ytdBuyback"] == 864_000 and t20["last"] is None
        assert len(b["series"]["cum"]) <= 4
        assert b["series"]["daily"]["key"] == "ALL"
        # 앞의 일정은 asof **뒤**만, 날짜 차례로.
        assert [s["date"] for s in b["next"]] == ["2026-08-31"]

    def test_강도는_같은_만기물_1년과_견준다(self, injected):
        b = ki.board()
        t3 = next(t for t in b["tenors"] if t["key"] == "3Y")["last"]
        assert t3["grade"] == "강한 수요"           # 여덟 달 중 응찰률 최고
        assert t3["pct"] is not None and t3["rateDelta"] is not None
        # 10년은 혼자라 판정이 없다 — 숫자처럼 보이는 잡음을 안 낸다.
        assert b["latest"]["grade"] == "표본 부족"

    def test_문장은_해요체다(self, injected):
        import json
        formal = re.compile(r"(니다|한다\.|이다\.|않는다\.)")
        b = ki.board()
        blob = json.dumps({"basis": b["basis"], "pd": b["pd"], "excluded": b["excluded"],
                           "latest": {"why": b["latest"]["why"], "notes": b["latest"]["notes"]},
                           "tenors": [t["last"] and {"why": t["last"]["why"], "notes": t["last"]["notes"]}
                                      for t in b["tenors"]]}, ensure_ascii=False)
        assert not formal.search(blob), formal.search(blob).group(0)
        assert "예요" in b["basis"]


class Test라우트:
    def test_붙어_있다(self):
        from app import main as M
        paths = {r.path for r in M.app.routes if "issuance" in getattr(r, "path", "")}
        assert "/api/flow/issuance" in paths
