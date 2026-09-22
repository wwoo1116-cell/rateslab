# -*- coding: utf-8 -*-
"""페이퍼 북 — **표본밖 기록**의 산술과 저장을 핀으로 박는다.

`paper` 는 규칙도 손익 공식도 안 만든다. 엔진(`mrbacktest`)이 낸 봉을 자르고
(`mrmetrics.score`) 회계는 주입받는다. 그래서 이 파일이 재는 것은 그 «자르기»와
«기록»이 거짓말을 안 하는가다:

  · 등록하면 조건이 **얼고**, 다시 등록해도 안 덮어쓴다
  · 등록일 **뒤에 봉이 없으면 0 이 아니라 «아직»** 이다 (없던 날의 돈을 안 갖는다)
  · 내린 것은 **안 지운다** — 기록에 남고 「내린 날」이 붙는다
  · 일별을 날짜 축 하나로 모으고 누적을 **서버가** 끝낸다 (§16)
  · 회계가 죽어도 북은 선다 — 엔진 근사로 떨어지고 `real` 이 그 사실을 적는다
  · 저장은 **원자적**이다 — 반쪽 JSON 이 기록을 조용히 지우지 않는다

SQL 도 파일도 안 만진다(저장 시험만 `tmp_path`). 다리는 `test_mrplan.py` 와 같은
합성 계열에 실제 엔진을 건 것이다.
"""
import datetime as dt
import json
import math

import pytest

from app import mr as mr_mod
from app import mrbacktest as bt
from app import mrplan as mrp
from app import paper


# ── 픽스처 — `test_mrplan.py` 의 그 계열·그 달력 ─────────────────────────────
def _ou(n: int, *, seed: int, phi: float = 0.92, sd: float = 1.4,
        mu: float = 30.0) -> list[float]:
    s, v, out = seed, mu, []
    for _ in range(n):
        s = (s * 1664525 + 1013904223) % (2 ** 32)
        u1 = s / 0xFFFFFFFF
        s = (s * 1664525 + 1013904223) % (2 ** 32)
        u2 = s / 0xFFFFFFFF
        g = math.sqrt(-2 * math.log(u1 + 1e-12)) * math.cos(2 * math.pi * u2)
        v = mu + phi * (v - mu) + sd * g
        out.append(round(v * 100) / 100)
    return out


_D0 = dt.date(2020, 1, 1)
KNOBS = {"lookback": 60, "entryZ": 2.0, "exitZ": 0.5, "stopZ": 2.5,
         "entryMode": "level"}


def _dates(n: int) -> list[str]:
    return [(_D0 + dt.timedelta(days=i)).isoformat() for i in range(n)]


def _leg_of(n: int = 600, kind: str = "bss", unit: str = "bp"):
    vals = _ou(n, seed=7)
    dates = _dates(n)

    def leg_of(sid: str, knobs: dict, *, accounting: bool = True) -> dict:
        r = bt.simulate(dates, vals, lookback=int(knobs["lookback"]),
                        entry_z=float(knobs["entryZ"]),
                        exit_z=float(knobs["exitZ"]),
                        stop_z=float(knobs["stopZ"]), cost_bp=paper.COST_BP,
                        notional=paper.NOTIONAL,
                        allow_dirs=tuple(mr_mod.TRADABLE_DIRS[kind]),
                        entry_mode=str(knobs["entryMode"]))
        return {"id": sid, "label": f"{sid} 라벨", "kind": kind, "unit": unit,
                "real": bool(accounting), "dates": dates, "vals": vals, "r": r}

    return leg_of, dates, vals


# ── 저장 ────────────────────────────────────────────────────────────────────
class TestStore:
    def test_없는_파일은_빈_장부다(self, tmp_path):
        got = paper.load(tmp_path / "nope.json")
        assert got == paper.EMPTY

    def test_깨진_파일도_빈_장부다_예외를_안_던진다(self, tmp_path):
        """화면이 통째로 비는 것과 장부가 하나 없는 것은 다른 사고다."""
        p = tmp_path / "broken.json"
        p.write_text('{"enrolled": [', encoding="utf-8")
        assert paper.load(p) == paper.EMPTY

    def test_왕복한다(self, tmp_path):
        p = tmp_path / "book.json"
        st = dict(paper.EMPTY)
        paper.enroll(st, "BSS-2Y", KNOBS, label="BSS 2Y", today="2026-09-21")
        paper.save(st, p)
        assert paper.load(p)["enrolled"][0]["id"] == "BSS-2Y"

    def test_쓰다_죽어도_옛_장부가_남는다(self, tmp_path, monkeypatch):
        """원자적 갈아끼기 — 반쪽 JSON 이 기록을 조용히 지우면 안 된다."""
        p = tmp_path / "book.json"
        good = dict(paper.EMPTY)
        paper.enroll(good, "BSS-2Y", KNOBS, today="2026-09-21")
        paper.save(good, p)

        def boom(*a, **k):
            raise OSError("디스크가 찼어요")

        monkeypatch.setattr(paper.json, "dump", boom)
        with pytest.raises(OSError):
            paper.save({"opened": None, "enrolled": [], "trades": []}, p)
        # 옛 장부가 그대로다 — 그리고 임시 파일이 안 남는다.
        assert paper.load(p)["enrolled"][0]["id"] == "BSS-2Y"
        assert [f.name for f in tmp_path.iterdir()] == ["book.json"]


# ── 등록 ────────────────────────────────────────────────────────────────────
class TestEnroll:
    def test_조건이_그_자리에서_언다(self):
        st = dict(paper.EMPTY)
        paper.enroll(st, "BSS-2Y", KNOBS, today="2026-09-21")
        assert st["enrolled"][0]["knobs"] == KNOBS
        assert st["enrolled"][0]["opened"] == "2026-09-21"
        assert st["opened"] == "2026-09-21"

    def test_다시_등록해도_안_덮어쓴다(self):
        """덮어쓰면 표본밖 기록이 그 순간 사라지고 화면은 아무 말도 안 한다."""
        st = dict(paper.EMPTY)
        paper.enroll(st, "BSS-2Y", KNOBS, today="2026-09-21")
        paper.enroll(st, "BSS-2Y", {**KNOBS, "lookback": 120}, today="2026-10-01")
        assert len(st["enrolled"]) == 1
        assert st["enrolled"][0]["knobs"]["lookback"] == 60
        assert st["enrolled"][0]["opened"] == "2026-09-21"

    def test_장부를_연_날은_첫_등록일이다(self):
        """파일을 만든 날로 세면 아무것도 등록 안 한 날부터 표본밖이 부푼다."""
        st = dict(paper.EMPTY)
        paper.enroll(st, "A", KNOBS, today="2026-09-21")
        paper.enroll(st, "B", KNOBS, today="2026-10-05")
        assert st["opened"] == "2026-09-21"

    def test_내린_것은_안_지운다(self):
        st = dict(paper.EMPTY)
        paper.enroll(st, "BSS-2Y", KNOBS, today="2026-09-21")
        paper.retire(st, "BSS-2Y")
        assert len(st["enrolled"]) == 1
        assert st["enrolled"][0]["retired"]


# ── 규칙 북 ─────────────────────────────────────────────────────────────────
class TestRuleBook:
    def test_등록일_이후만_센다(self):
        leg_of, dates, _ = _leg_of()
        cut = dates[400]
        got = paper.rule_leg("X", {"id": "X", "opened": cut, "knobs": KNOBS},
                             leg_of=leg_of)
        assert got["days"] == len(dates) - 400
        assert got["daily"][0]["t"] == cut
        assert got["daily"][-1]["t"] == dates[-1]

    def test_등록_뒤_봉이_없으면_0_이_아니라_아직이다(self):
        """★ 실측 2026-09-21 — 09-21 등록인데 마지막 봉이 09-18 이었다.

        `mrmetrics.index_at` 은 빈 구간을 안 만들려고 마지막 봉을 남기는데,
        페이퍼 북에서는 그 봉이 **등록 전의 하루**다. 그날 손익을 얹으면 장부가
        있지도 않았던 날의 돈을 갖는다.
        """
        leg_of, dates, _ = _leg_of()
        after = (dt.date.fromisoformat(dates[-1]) + dt.timedelta(days=3)).isoformat()
        got = paper.rule_leg("X", {"id": "X", "opened": after, "knobs": KNOBS},
                             leg_of=leg_of)
        assert got["days"] == 0
        assert got["daily"] == []
        assert got["totalPnl"] == 0.0
        assert dates[-1] in got["why"]

    def test_구간_순손익이_일별의_합이다(self):
        leg_of, dates, _ = _leg_of()
        got = paper.rule_leg("X", {"id": "X", "opened": dates[300], "knobs": KNOBS},
                             leg_of=leg_of)
        assert got["totalPnl"] == pytest.approx(
            sum(d["pnl"] for d in got["daily"]), abs=1e-6)

    def test_계획면과_같은_자를_쓴다(self):
        """`mrmetrics.score` 한 벌 — 두 화면이 같은 계열에 다른 돈을 매기면 안 된다."""
        leg_of, dates, _ = _leg_of()
        e = {"id": "X", "opened": dates[200], "knobs": KNOBS}
        got = paper.rule_leg("X", e, leg_of=leg_of)
        leg = leg_of("X", KNOBS)
        from app import mrmetrics as mrm
        want = mrm.score(leg["dates"], leg["r"]["points"], leg["r"]["trades"],
                         200, paper.COST_BP)
        assert got["totalPnl"] == want["totalPnl"]
        assert got["numTrades"] == want["numTrades"]

    def test_회계를_켜고_돈다(self):
        """규칙 북은 **실가격**이다 — 수동 북과 같은 바닥 위에 서야 견줄 수 있다."""
        seen: list[bool] = []
        base, dates, _ = _leg_of()

        def leg_of(sid, knobs, *, accounting=True):
            seen.append(accounting)
            return base(sid, knobs, accounting=accounting)

        paper.rule_leg("X", {"id": "X", "opened": dates[300], "knobs": KNOBS},
                       leg_of=leg_of)
        assert seen == [True]


# ── 수동 북 ─────────────────────────────────────────────────────────────────
class TestManualBook:
    def _trades(self, dates):
        return [{"n": 1, "id": "X", "dir": -1, "entry": dates[100],
                 "exit": dates[140], "notional": paper.NOTIONAL, "label": "X"},
                {"n": 2, "id": "X", "dir": 1, "entry": dates[200],
                 "exit": None, "notional": paper.NOTIONAL, "label": "X"}]

    def test_안_닫은_거래는_마지막_봉까지_선다(self):
        leg_of, dates, _ = _leg_of()
        got = paper.manual_leg("X", self._trades(dates), leg_of=leg_of,
                               account_of=None, knobs=KNOBS)
        assert got["numTrades"] == 2
        assert got["openTrades"] == 1
        assert got["trades"][1]["exitT"] == dates[-1]

    def test_미청산은_편도_비용만_문다(self):
        """왕복을 미리 물면 아직 안 낸 돈이 오늘 손익에서 빠진다."""
        leg_of, dates, _ = _leg_of()
        got = paper.manual_leg("X", self._trades(dates), leg_of=leg_of,
                               account_of=None, knobs=KNOBS)
        closed, open_ = got["trades"]
        assert closed["cost"] == pytest.approx(-paper.COST_BP * paper.NOTIONAL * 2)
        assert open_["cost"] == pytest.approx(-paper.COST_BP * paper.NOTIONAL)

    def test_부호_규약은_엔진의_것을_그대로_쓴다(self):
        """방향을 뒤집으면 손익도 정확히 뒤집힌다(비용을 뺀 총손익 기준)."""
        leg_of, dates, vals = _leg_of()
        one = [{"n": 1, "id": "X", "dir": 1, "entry": dates[100],
                "exit": dates[140], "notional": paper.NOTIONAL}]
        other = [{**one[0], "dir": -1}]
        a = paper.manual_leg("X", one, leg_of=leg_of, account_of=None, knobs=KNOBS)
        b = paper.manual_leg("X", other, leg_of=leg_of, account_of=None, knobs=KNOBS)
        assert a["trades"][0]["mtm"] == pytest.approx(-b["trades"][0]["mtm"])

    def test_봉에_없는_날은_세어서_말한다(self):
        """조용히 빼면 「내 거래가 왜 장부에 없죠」가 된다."""
        leg_of, dates, _ = _leg_of()
        bad = [{"n": 1, "id": "X", "dir": -1, "entry": "1999-01-01",
                "exit": None, "notional": paper.NOTIONAL}]
        got = paper.manual_leg("X", bad, leg_of=leg_of, account_of=None, knobs=KNOBS)
        assert got["numTrades"] == 0
        assert got["skipped"] == 1

    def test_회계가_죽어도_북은_선다(self):
        leg_of, dates, _ = _leg_of()

        def account_of(**kw):
            raise RuntimeError("민평 행렬을 못 읽었어요")

        got = paper.manual_leg("X", self._trades(dates), leg_of=leg_of,
                               account_of=account_of, knobs=KNOBS)
        assert got["real"] is False
        assert got["numTrades"] == 2

    def test_회계가_붙으면_일별이_그_회계의_것이다(self):
        leg_of, dates, _ = _leg_of()

        def account_of(*, sid, leg, trades, cost_bp):
            for o in trades:
                o["day"] = {o["entryT"]: 100.0, o["exitT"]: 50.0}
                o["pnl"] = 150.0
            return True

        got = paper.manual_leg("X", self._trades(dates), leg_of=leg_of,
                               account_of=account_of, knobs=KNOBS)
        assert got["real"] is True
        assert got["totalPnl"] == pytest.approx(300.0)
        assert sum(d["pnl"] for d in got["daily"]) == pytest.approx(300.0)


# ── 한 장 ───────────────────────────────────────────────────────────────────
class TestSheet:
    def test_누적을_서버가_끝낸다(self):
        """§16 — 브라우저는 포맷만 한다."""
        leg_of, dates, _ = _leg_of()
        st = {"opened": dates[300], "trades": [],
              "enrolled": [{"id": "X", "opened": dates[300], "knobs": KNOBS}]}
        got = paper.build_sheet(leg_of=leg_of, store=st)
        daily = got["rule"]["daily"]
        assert daily[-1]["cum"] == pytest.approx(
            sum(d["pnl"] for d in daily), abs=1e-6)
        assert got["rule"]["cum"] == daily[-1]["cum"]

    def test_오늘은_마지막_봉의_하루다(self):
        leg_of, dates, _ = _leg_of()
        st = {"opened": dates[300], "trades": [],
              "enrolled": [{"id": "X", "opened": dates[300], "knobs": KNOBS}]}
        got = paper.build_sheet(leg_of=leg_of, store=st)
        assert got["asof"] == dates[-1]
        assert got["rule"]["today"] == pytest.approx(
            got["rule"]["daily"][-1]["pnl"])

    def test_차이가_수동_빼기_규칙이다(self):
        """이 화면이 실제로 묻는 물음 — 내 판단이 규칙보다 나은가."""
        leg_of, dates, _ = _leg_of()
        st = {"opened": dates[300],
              "enrolled": [{"id": "X", "opened": dates[300], "knobs": KNOBS}],
              "trades": [{"n": 1, "id": "X", "dir": -1, "entry": dates[310],
                          "exit": None, "notional": paper.NOTIONAL}]}
        got = paper.build_sheet(leg_of=leg_of, store=st)
        assert got["diff"]["cum"] == pytest.approx(
            got["manual"]["cum"] - got["rule"]["cum"], abs=1e-6)

    def test_한_다리가_죽어도_나머지가_선다(self):
        base, dates, _ = _leg_of()

        def leg_of(sid, knobs, *, accounting=True):
            if sid == "BAD":
                raise RuntimeError("계열을 못 읽었어요")
            return base(sid, knobs, accounting=accounting)

        st = {"opened": dates[300], "trades": [],
              "enrolled": [{"id": "BAD", "opened": dates[300], "knobs": KNOBS},
                           {"id": "X", "opened": dates[300], "knobs": KNOBS}]}
        got = paper.build_sheet(leg_of=leg_of, store=st)
        assert [lg["id"] for lg in got["rule"]["legs"]] == ["X"]
        assert got["failed"][0]["id"] == "BAD"

    def test_내린_다리도_기록에_남는다(self):
        """생존 편향이 장부에 들어오는 자리 — 진 규칙이 조용히 사라지면 안 된다."""
        leg_of, dates, _ = _leg_of()
        st = {"opened": dates[300], "trades": [],
              "enrolled": [{"id": "X", "opened": dates[300], "knobs": KNOBS,
                            "retired": dates[-1]}]}
        got = paper.build_sheet(leg_of=leg_of, store=st)
        assert got["rule"]["enrolled"] == 0
        assert got["rule"]["retired"] == 1
        assert got["rule"]["legs"][0]["retired"] == dates[-1]


# ── 배관 ────────────────────────────────────────────────────────────────────
class TestPlumbing:
    def test_비용과_Delta_가_계획면과_같다(self):
        """다른 값을 쓰면 같은 거래에 두 화면이 다른 돈을 매긴다."""
        assert paper.COST_BP == mrp.COST_BP
        assert paper.NOTIONAL == mrp.NOTIONAL

    def test_장부는_리포_안이되_추적_대상이_아니다(self):
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent.parent
        assert paper.STORE.name == "paper_book.json"
        ignored = (root / ".gitignore").read_text(encoding="utf-8")
        assert "backend/data/paper_book.json" in ignored

    def test_라우트가_붙어_있다(self):
        from app.main import app
        paths = {r.path for r in app.routes if "paper" in getattr(r, "path", "")}
        assert paths == {"/api/paper", "/api/paper/enroll", "/api/paper/retire",
                         "/api/paper/trade", "/api/paper/close",
                         # 손으로 쌓는 다리 [OWNER 2026-09-22] — 계열+방향이 아니라
                         # 계기 하나에 내가 체결한 레벨. `instruments` 가 서버에서
                         # 목록을 내는 이유는 «못 하는 거래는 고를 수조차 없어야»
                         # 하기 때문이다(선물 2Y 를 화면이 만들어 내던 자리).
                         "/api/paper/leg", "/api/paper/leg/close",
                         "/api/paper/instruments",
                         # 초기화는 **지우기가 아니다** — 옛 장부를 보관하고 새로
                         # 연다(`paper.reset`). 아래 「지우는 라우트는 없다」가
                         # 여전히 서는 이유가 그것이다.
                         "/api/paper/reset"}

    def test_지우는_라우트는_없다(self):
        """진 기록을 지우는 것이 생존 편향이 장부에 들어오는 가장 흔한 길이다."""
        from app.main import app
        for r in app.routes:
            if "paper" in getattr(r, "path", ""):
                assert "DELETE" not in getattr(r, "methods", set())


# ── 분해 [OWNER 2026-09-09 — 계획면에 건 「클릭 없이 분해」의 그 규율] ──────
class TestSplit:
    def test_규칙_북의_분해가_구간_순손익으로_닫힌다(self):
        leg_of, dates, _ = _leg_of()
        got = paper.rule_leg("X", {"id": "X", "opened": dates[300], "knobs": KNOBS},
                             leg_of=leg_of)
        sp = got["split"]
        five = sum(v for k, v in sp.items()
                   if k != "total" and v is not None)
        assert five == pytest.approx(sp["total"], abs=1.0)
        assert sp["total"] == pytest.approx(got["totalPnl"], abs=1.0)

    def test_근사_판은_없는_항을_0_으로_안_적는다(self):
        """0 으로 적으면 「0 원이었다」는 딴 사실이 되고 화면의 «—» 가 사라진다."""
        leg_of, dates, _ = _leg_of()
        trades = [{"n": 1, "id": "X", "dir": -1, "entry": dates[100],
                   "exit": dates[140], "notional": paper.NOTIONAL}]
        got = paper.manual_leg("X", trades, leg_of=leg_of, account_of=None,
                               knobs=KNOBS)
        assert got["split"]["rolldown"] is None
        assert got["split"]["funding"] is None
        assert got["split"]["mtm"] is not None

    def test_실가격과_근사를_섞어_더하지_않는다(self):
        """실가격 셋 + 근사 하나의 합이 실가격처럼 보이면 안 된다."""
        real = {"split": {"mtm": 1.0, "carry": 2.0, "rolldown": 3.0,
                          "funding": 4.0, "cost": -1.0, "total": 9.0}}
        approx = {"split": {"mtm": 1.0, "carry": 2.0, "rolldown": None,
                            "funding": None, "cost": -1.0, "total": 2.0}}
        got = paper.merge_split([real, approx])
        assert got["rolldown"] is None
        assert got["funding"] is None
        assert got["mtm"] == pytest.approx(2.0)
        assert got["total"] == pytest.approx(11.0)


class TestLegs:
    """손으로 쌓는 다리 [OWNER 2026-09-22].

    > "포지션은 써서 넣을 수 있게 … IRS pay receive 하나 씩 쌓는 방식으로"
    > "ex. BSS라고 하면, 국채선물 2년 금리 몇에 매수 / IRS Pay 2년 금리 몇에 매도"

    계열+방향(`trades`)과 다른 물건이라 시험도 따로 선다. 여기서 재는 것은 **부호
    규약**과 **못 하는 거래의 거절**이다 — 값을 매기는 식은 한 줄이라 그 한 줄이
    계기 셋에서 같은 뜻인지가 전부다.
    """

    def leg(self, **kw):
        st = dict(paper.EMPTY, legs=[])
        base = dict(kind="irs", tenor="2Y", side="pay", entry="2026-09-21",
                    level=3.00, notional=1e10, dv01=1_900_000.0)
        paper.add_leg(st, **{**base, **kw})
        return st["legs"][-1]

    def test_IRS_페이는_금리가_오르면_번다(self):
        l = self.leg(side="pay")
        assert l["rateSign"] == +1
        got = paper.score_leg(l, mark=3.10, cost_bp=0.0)       # +10bp
        assert got["bp"] == pytest.approx(10.0)
        assert got["gross"] == pytest.approx(10.0 * 1_900_000.0)

    def test_리시브는_부호가_뒤집힌다(self):
        a = paper.score_leg(self.leg(side="pay"), mark=3.10, cost_bp=0.0)
        b = paper.score_leg(self.leg(side="receive"), mark=3.10, cost_bp=0.0)
        assert a["gross"] == pytest.approx(-b["gross"])

    def test_선물_매수와_현물_매수는_같은_쪽이다(self):
        """가격을 사는 다리는 **금리가 내리면** 번다 — 낱말이 달라도 부호는 같다."""
        f = self.leg(kind="fut", tenor="3Y", side="buy")
        b = self.leg(kind="bond", tenor="2Y", side="buy")
        assert f["rateSign"] == b["rateSign"] == -1

    def test_BSS_처럼_쌓으면_금리위험이_상쇄된다(self):
        """오너 예시 그대로 — 선물 매수 + IRS 페이. 순 DV01 이 둘의 **차**다."""
        st = dict(paper.EMPTY, legs=[])
        paper.add_leg(st, kind="fut", tenor="3Y", side="buy", entry="2026-09-21",
                      level=2.95, notional=1e10, dv01=2_800_000.0, tag="BSS 2Y")
        paper.add_leg(st, kind="irs", tenor="2Y", side="pay", entry="2026-09-21",
                      level=3.00, notional=1e10, dv01=1_900_000.0, tag="BSS 2Y")
        net = sum(l["rateSign"] * l["dv01"] for l in st["legs"])
        assert net == pytest.approx(1_900_000.0 - 2_800_000.0)

    def test_현물_국고_매도는_아예_안_받는다(self):
        """[OWNER 2026-09-22 「아예 막는다」] — 엔진의 `TRADABLE_DIRS` 와 같은 규칙."""
        with pytest.raises(paper.LegRejected) as e:
            self.leg(kind="bond", side="sell")
        assert "대차매도" in str(e.value)

    def test_없는_선물_만기는_안_받는다(self):
        """2년 국채선물은 KRX 에도 이 리포에도 없다 — 오너 예시의 그 자리다."""
        with pytest.raises(paper.LegRejected) as e:
            self.leg(kind="fut", tenor="2Y", side="buy")
        assert "3Y" in str(e.value)

    def test_오늘_레벨을_못_읽으면_0_이_아니라_None(self):
        """0 은 「안 벌었다」이고 None 은 「아직 모른다」다 — 이 리포의 그 규율."""
        got = paper.score_leg(self.leg(), mark=None)
        assert got["pnl"] is None and got["why"]

    def test_닫힌_다리는_내가_적은_청산_레벨을_쓴다(self):
        """진입을 종가로 안 매겼으니 청산도 그래야 한다. 시장 레벨은 안 본다."""
        st = dict(paper.EMPTY, legs=[])
        paper.add_leg(st, kind="irs", tenor="2Y", side="pay", entry="2026-09-01",
                      level=3.00, notional=1e10, dv01=1_000_000.0)
        paper.close_leg(st, 1, "2026-09-10", 3.20)
        got = paper.score_leg(st["legs"][0], mark=9.99, cost_bp=0.0)
        assert got["open"] is False
        assert got["bp"] == pytest.approx(20.0)                # 9.99 를 안 본다

    def test_비용은_열린_다리에_편도_닫힌_다리에_왕복(self):
        o = paper.score_leg(self.leg(), mark=3.00, cost_bp=0.5)
        st = dict(paper.EMPTY, legs=[])
        paper.add_leg(st, kind="irs", tenor="2Y", side="pay", entry="2026-09-01",
                      level=3.00, notional=1e10, dv01=1_900_000.0)
        paper.close_leg(st, 1, "2026-09-10", 3.00)
        c = paper.score_leg(st["legs"][0], mark=3.00, cost_bp=0.5)
        assert c["cost"] == pytest.approx(2 * o["cost"])


class TestWriteResponseShape:
    """**쓰기 응답도 읽기와 같은 모양이어야 한다** [수리 2026-09-22].

    화면은 `if (!sheet.available)` 하나로 전체를 에러 면으로 바꾼다. 그런데 종전에
    `available` 은 GET 라우트가 «감싸면서» 달던 칸이라 쓰기 다섯에는 없었고,
    그래서 **쓰기가 성공할 때마다 화면이 「못 세웠어요」로 죽었다.** 서버 로그는
    전부 200 이라 어디에도 안 드러난다 — 이 리포가 반복해서 밟는 그 «조용한 실패»다.

    한 칸 빠진 것이라 시험도 한 줄이면 된다. 다섯을 다 도는 이유는, 여섯째 쓰기가
    생길 때 이 줄이 빨개지는 것이 유일한 알림이라서다.
    """

    def test_쓰기_응답이_읽기와_같은_칸을_진다(self, monkeypatch, tmp_path):
        from fastapi.testclient import TestClient

        from app import main as M

        monkeypatch.setattr(paper, "STORE", tmp_path / "book.json")
        c = TestClient(M.app)

        read = c.get("/api/paper").json()
        assert read["available"] is True

        # 쓰기 다섯. 등록은 계획면 캐시를 요구하므로(409) 여기서는 **모양**만 본다 —
        # 성공한 응답은 반드시 `available` 을 진다.
        wrote = c.post("/api/paper/leg", json=dict(
            kind="irs", tenor="2Y", side="pay", entry="2026-09-21",
            level=3.97, notional=1e10))
        assert wrote.status_code == 200, wrote.text
        assert wrote.json()["available"] is True, "쓰기 응답에 available 이 빠지면 화면이 죽는다"

        closed = c.post("/api/paper/leg/close",
                        json=dict(n=1, exit="2026-09-21", level=4.00))
        assert closed.status_code == 200
        assert closed.json()["available"] is True

    def test_쓰기_라우트_전부가_같은_헬퍼를_지난다(self):
        """다섯이 `_paper_sheet()` 하나를 지나야 칸이 갈리지 않는다."""
        import inspect

        from app import main as M

        for name in ("paper_enroll", "paper_retire", "paper_trade",
                     "paper_close", "paper_add_leg", "paper_close_leg"):
            src = inspect.getsource(getattr(M, name))
            assert "_paper_sheet()" in src, f"{name} 이 장부를 따로 세우고 있다"


class TestReset:
    """초기화 [OWNER 2026-09-22] — **지우기가 아니라 치우기**다.

    「지우는 라우트는 없다」와 「초기화가 필요하다」는 둘 다 참이라, 옛 장부를
    파일로 남기고 새 장부를 연다. 치운 것을 못 찾으면 그건 결국 삭제다.
    """

    def test_옛_장부가_파일로_남는다(self, tmp_path):
        p = tmp_path / "book.json"
        st = dict(paper.EMPTY, legs=[])
        paper.add_leg(st, kind="irs", tenor="2Y", side="pay", entry="2026-09-21",
                      level=3.97, notional=1e10, dv01=1.9e6)
        paper.save(st, p)

        st2 = paper.load(p)
        kept_name = paper.reset(st2, p)
        paper.save(st2, p)

        assert kept_name and kept_name.startswith("paper_book_")
        # ★보관본 이름은 **장부에 안 들어간다** — 들어가면 다음 보관본까지 따라간다.
        assert "archivedTo" not in paper.load(p)
        assert paper.load(p)["legs"] == []
        kept = list((p.parent / "paper_archive").glob("paper_book_*.json"))
        assert len(kept) == 1, "옛 장부가 어디에도 없으면 그건 삭제다"
        assert json.loads(kept[0].read_text(encoding="utf-8"))["legs"][0]["level"] == 3.97

    def test_빈_장부를_초기화하면_보관본을_안_만든다(self, tmp_path):
        p = tmp_path / "book.json"
        st = paper.load(p)
        assert paper.reset(st, p) is None
        assert not (p.parent / "paper_archive").exists()

    def test_확인_낱말이_없으면_안_지운다(self, monkeypatch, tmp_path):
        from fastapi.testclient import TestClient

        from app import main as M

        monkeypatch.setattr(paper, "STORE", tmp_path / "book.json")
        c = TestClient(M.app)
        c.post("/api/paper/leg", json=dict(kind="irs", tenor="2Y", side="pay",
                                           entry="2026-09-21", level=3.97, notional=1e10))
        assert c.post("/api/paper/reset", json={}).status_code == 400
        assert len(paper.load(tmp_path / "book.json")["legs"]) == 1

        ok = c.post("/api/paper/reset", json={"confirm": "초기화"})
        assert ok.status_code == 200
        assert ok.json()["available"] is True
        assert ok.json()["archivedTo"].startswith("paper_book_")
        assert paper.load(tmp_path / "book.json")["legs"] == []


# ── 체결일은 **오늘**이지 자료의 날이 아니다 [OWNER 2026-09-22] ─────────────
#
# > "포트폴리오에 포지션 쌓아서 매수하는 건 민평 종가가 들어온 기준이 아니라,
# >  실제로 오늘임. 예를 들면 현재 시스템상 민평 종가는 9월 21일까지 들어와있지만,
# >  오늘 장중에 내가 스왑 금리를 보고 포지션을 진입했다면 그건 22일날 진입한거임"
#
# 이 북의 진입은 **장중 체결**이고 마크는 **종가**다. 둘은 다른 시계이고, 마크가
# 체결일보다 **앞설 수 있다**. 그때 「마크 − 내 레벨」은 손익이 아니라 시간을
# 거꾸로 센 수인데, 부호까지 그럴듯해서 화면만 보고는 못 가른다.

class Test체결일과_마크의_날:
    def _leg(self, entry, level=4.10, exit_=None, exit_lv=None):
        return {"n": 1, "kind": "irs", "tenor": "3Y", "side": "pay",
                "rateSign": 1, "entry": entry, "level": level,
                "notional": 1e10, "dv01": 2_950_000.0, "tag": "", "note": "",
                "exit": exit_, "exitLevel": exit_lv}

    def test_마크가_체결일보다_앞서면_안_매긴다(self):
        """★이 파일의 핵심. 0 이 아니라 **「아직」**이다 — 규칙 북이 `index_at`
        에서 밟은 그 병의 포지션 카드 판이다."""
        got = paper.score_leg(self._leg("2026-09-22"), 4.15, mark_t="2026-09-21")
        assert got["pnl"] is None, f'지어낸 손익이 섰어요: {got["pnl"]}'
        assert got["why"] and "아직" in got["why"]
        # 레벨과 그 날은 **그대로 올린다** — 화면이 간극을 보여야 한다.
        assert got["mark"] == 4.15 and got["markT"] == "2026-09-21"

    def test_마크가_체결일에_닿으면_그날_매겨진다(self):
        """「아직」은 영원이 아니다 — 종가가 오면 저절로 선다."""
        got = paper.score_leg(self._leg("2026-09-22"), 4.15, mark_t="2026-09-22")
        assert got["pnl"] is not None and got["why"] is None
        assert got["bp"] == pytest.approx(5.0)

    def test_지난_날_체결은_그대로_매겨진다(self):
        got = paper.score_leg(self._leg("2026-09-15"), 4.15, mark_t="2026-09-21")
        assert got["pnl"] is not None and got["why"] is None

    def test_청산한_다리는_마크의_날과_무관하다(self):
        """청산 레벨은 **내가 적은 것**이라 종가를 안 쓴다(`close_leg` 의 그 규약).
        여기까지 「아직」으로 막으면 오늘 열고 오늘 닫은 거래가 안 매겨진다."""
        got = paper.score_leg(
            self._leg("2026-09-22", exit_="2026-09-22", exit_lv=4.15),
            4.99, mark_t="2026-09-21")
        assert got["pnl"] is not None and got["why"] is None
        assert got["bp"] == pytest.approx(5.0)          # 4.15 − 4.10, 마크와 무관

    def test_마크를_안_주면_종전과_같다(self):
        """`mark_t` 는 선택이다 — 옛 호출부를 안 깬다."""
        got = paper.score_leg(self._leg("2026-09-22"), 4.15)
        assert got["pnl"] is not None and got["why"] is None

    def test_장부가_오늘을_따로_싣는다(self):
        """`asof`(자료의 날)와 `today`(실제 달력)는 **다른 칸**이다. 화면의
        체결일 기본값이 `asof` 였던 것이 이 결함의 뿌리다."""
        import datetime as dt

        sheet = paper.build_sheet(leg_of=lambda *a, **k: {}, store=dict(paper.EMPTY))
        assert sheet["today"] == dt.date.today().isoformat()

    def test_체결일이_미래면_거절한다(self):
        """미래 날짜는 **영원히 「아직」**이 된다(마크가 늘 그보다 앞서므로) —
        그 다리가 왜 안 매겨지는지 아무도 모른다. 들어올 때 막는다."""
        import datetime as dt

        today = dt.date.today()
        paper.check_entry(today.isoformat())                   # 오늘은 통과
        paper.check_entry((today - dt.timedelta(days=30)).isoformat())   # 과거도 통과
        for bad in ((today + dt.timedelta(days=1)).isoformat(), "", "22/09/2026"):
            with pytest.raises(paper.LegRejected):
                paper.check_entry(bad)
