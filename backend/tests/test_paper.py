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
                         "/api/paper/reset",
                         # 그날의 1등 [OWNER 2026-09-23 「손으로 치되 1등을 제안」] —
                         # **읽기**다. 장부에 쓰지 않고 옆에 설 뿐이라(`Test그날_1등_
                         # 제안`) 위 「쓰기는 덧쓰기뿐」 규율과 무관하다.
                         "/api/paper/suggest",
                         # 조건이 없던 다리에 조건 붙이기 [OWNER 2026-09-28] — 덧쓰기다
                         # (빈 칸을 적는다 · 언 조건은 거절 · `Test조건_붙이기`).
                         "/api/paper/leg/knobs",
                         # 트레이드 추적 [OWNER 2026-09-28] — **읽기**. 다리들을 백테스트
                         # 엔진에 실어 진입일부터 분해한다(`Test트레이드_추적`).
                         "/api/paper/trace",
                         # 지금 시세 [OWNER 2026-09-28] — **읽기**. 인포맥스 IRS·국채선물
                         # 장중을 장중 레벨의 낱말로 옮길 뿐, 여기서 장부를 안 매긴다.
                         "/api/paper/live"}

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


# ── 청산 레벨도 **내가 적는다** [OWNER 2026-09-22 — "내가 적는 청산 레벨까지"] ──
#
# 라우트는 처음부터 레벨을 받고 있었고 비어 있던 것은 **입력 칸**이었다. 그 사이
# 장부의 청산 레벨은 전부 마지막 종가였고, 한 거래 안에 「진입은 내 체결가 ·
# 청산은 종가」라는 두 규약이 서 있었다.

class Test청산:
    def _book(self, entry="2026-09-15"):
        st = dict(paper.EMPTY)
        st["legs"] = []
        paper.add_leg(st, kind="irs", tenor="3Y", side="pay", entry=entry,
                      level=4.050, notional=1e10, dv01=2_950_000.0, tag="IRS 3Y")
        return st

    def test_내가_적은_레벨로_닫힌다(self):
        st = self._book()
        paper.close_leg(st, 1, "2026-09-18", 4.111)
        lg = st["legs"][0]
        assert lg["exit"] == "2026-09-18" and lg["exitLevel"] == 4.111
        # 그 레벨이 손익을 정한다 — 마크는 안 쓴다(청산했으니까).
        got = paper.score_leg(lg, 9.99, mark_t="2026-09-21")
        assert got["bp"] == pytest.approx((4.111 - 4.050) * 100)

    def test_없는_다리는_조용히_넘어가지_않는다(self):
        """★종전에는 `n` 이 안 맞으면 목록을 그대로 두고 끝났다 — 라우트는 200,
        화면은 「닫았어요」, 장부는 그대로. **안 한 일을 했다고 적는 것**이 이
        장부에서 제일 나쁜 결함이다."""
        with pytest.raises(paper.LegRejected):
            paper.close_leg(self._book(), 99, "2026-09-18", 4.1)

    def test_이미_닫힌_다리는_다시_안_닫는다(self):
        st = self._book()
        paper.close_leg(st, 1, "2026-09-18", 4.111)
        with pytest.raises(paper.LegRejected):
            paper.close_leg(st, 1, "2026-09-19", 4.2)
        assert st["legs"][0]["exitLevel"] == 4.111      # 첫 기록이 산다

    def test_청산일이_체결일보다_앞설_수_없다(self):
        """보유기간이 음수인 다리는 손익의 부호가 뒤집히는데, 표에는
        「09-15 → 09-10 청산」이라고 멀쩡히 선다."""
        with pytest.raises(paper.LegRejected):
            paper.close_leg(self._book(), 1, "2026-09-10", 4.1)

    def test_청산일이_미래일_수_없다(self):
        import datetime as dt

        future = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        with pytest.raises(paper.LegRejected):
            paper.close_leg(self._book(), 1, future, 4.1)

    def test_오늘_열고_오늘_닫는_것은_된다(self):
        """진입과 청산이 같은 날인 거래는 정상이다 — `check_exit` 가 «앞선다»만
        막고 «같다»는 안 막는 것이 그 이유다."""
        import datetime as dt

        today = dt.date.today().isoformat()
        st = self._book(entry=today)
        paper.close_leg(st, 1, today, 4.2)
        assert st["legs"][0]["exit"] == today


class Test다리에_얼린_조건:
    """★다리는 **그날의 조건으로** 들어갔다 [트레이더 2026-09-23].

    > "어제자에 진입한 조건은 60일, 2.5/0.5/3 … 오늘 보니까 120/2.5/0/3 이래서
    >  확인할 수가 없게 됐다"

    Strategy 화면의 노브는 **오늘 것**이다. 어제 다리를 오늘 노브로 읽으면
    청산선도 손절선도 딴 선이 되고, 그러면 그 다리의 청산·손절을 추적할 수가
    없다. 규칙 북(`enroll`)은 처음부터 「조건을 그 자리에서 언다」였는데
    **포지션 카드만 그 규율 밖**에 있었다.
    """

    OK = {"lookback": 60, "entryZ": 2.5, "exitZ": 0.5, "stopZ": 3.0,
          "entryMode": "level"}

    def leg(self, knobs, **kw):
        st = dict(paper.EMPTY, legs=[])
        base = dict(kind="irs", tenor="2Y", side="pay", entry="2026-09-21",
                    level=3.00, notional=1e10, dv01=1_900_000.0)
        paper.add_leg(st, **{**base, **kw}, knobs=knobs)
        return st["legs"][-1]

    def test_조건은_다리에_그대로_언다(self):
        """어제 친 값이 그대로 남는다 — 오늘 노브가 뭐든."""
        got = self.leg(self.OK)["knobs"]
        assert got == self.OK

    def test_안_적은_다리는_None_이다_빈_사전이_아니다(self):
        """★「안 적었다」와 「전부 0 으로 들어갔다」는 **다른 말**이다.

        빈 사전으로 바꾸면 화면이 「룩백 0일 · 0/0/0σ」를 적게 되고, 그건 없는
        사실을 적는 것이다(이 리포의 공란 정책).
        """
        assert self.leg(None)["knobs"] is None
        assert self.leg({})["knobs"] is None
        # 전부 None 인 사전도 «안 적은» 것이다 — 화면이 빈 칸을 그렇게 보낸다.
        assert self.leg({k: None for k in paper.LEG_KNOBS})["knobs"] is None

    def test_반쪽_조건은_거절한다(self):
        """「룩백만 적힌」 다리는 청산선을 못 그린다 — 그런 조건은 안 받는다."""
        for missing in paper.LEG_KNOBS:
            half = {k: v for k, v in self.OK.items() if k != missing}
            with pytest.raises(paper.LegRejected) as e:
                self.leg(half)
            assert missing in str(e.value)

    def test_모르는_칸은_거절한다(self):
        """조용히 버리면 장부에 안 적힌 조건이 적힌 줄 안다."""
        with pytest.raises(paper.LegRejected) as e:
            self.leg({**self.OK, "timeStop": 20})
        assert "timeStop" in str(e.value)

    @pytest.mark.parametrize("bad,why", [
        ({"lookback": 1}, "룩백"),
        ({"lookback": 601}, "룩백"),
        ({"lookback": "예순"}, "룩백"),
        ({"entryZ": -0.1}, "진입"),
        ({"exitZ": 20.1}, "청산"),
        ({"stopZ": "삼"}, "손절"),
        ({"entryMode": "즉시"}, "진입 규칙"),
    ])
    def test_범위_밖은_사유를_들고_죽는다(self, bad, why):
        """범위는 `main._mr_check_knobs` 와 **같다**.

        두 문이 다른 값을 통과시키면 장부에 **엔진이 못 받는 조건**이 적히고,
        그때 그 다리는 「무슨 규칙이었는지」를 영원히 못 돌려준다.
        """
        with pytest.raises(paper.LegRejected) as e:
            self.leg({**self.OK, **bad})
        assert why in str(e.value)

    def test_프리셋_밖의_값도_받는다(self):
        """★막는 것은 **범위**이지 프리셋이 아니다.

        프리셋(룩백 20/60/120 …)은 화면이 고르는 칸이고, 장부는 «실제로 무엇으로
        들어갔나» 를 적는 자리다. 프리셋으로 막으면 자유 입력으로 돌린 조건의
        다리를 장부가 못 받는다.
        """
        odd = {**self.OK, "lookback": 77, "entryZ": 1.85}
        assert self.leg(odd)["knobs"]["lookback"] == 77

    def test_두_책이_같은_낱말을_쓴다(self):
        """`enroll` 의 `knobs` 와 **같은 칸 이름**이다.

        규칙 북과 포지션 카드가 같은 조건을 다른 이름으로 적으면 나중에 둘을
        못 잇는다 — 이 리포가 반복해서 밟은 자리다.
        """
        st = dict(paper.EMPTY)
        paper.enroll(st, "BSS-2Y", self.OK, today="2026-09-23")
        assert set(st["enrolled"][0]["knobs"]) == set(paper.LEG_KNOBS)

    def test_숫자로_바꿔서_넣는다(self):
        """화면은 글자를 보낸다 — 장부에는 수로 앉아야 한다."""
        got = self.leg({"lookback": "60", "entryZ": "2.5", "exitZ": "0.5",
                        "stopZ": "3", "entryMode": "touch"})["knobs"]
        assert got["lookback"] == 60 and isinstance(got["lookback"], int)
        assert got["entryZ"] == 2.5 and isinstance(got["entryZ"], float)
        assert got["entryMode"] == "touch"


class Test청산_손절_추적:
    """★얼린 조건으로 **지금** 닿았는가 [OWNER 2026-09-23].

    이 시험이 지키는 것은 하나다 — **엔진과 같은 규칙인가.** 장부가 제 규칙으로
    「청산 닿음」을 적으면 그 순간 이 데스크에 청산선이 둘이 된다.
    """

    OK = {"lookback": 3, "entryZ": 2.0, "exitZ": 0.5, "stopZ": 3.0,
          "entryMode": "level"}

    def leg(self, vals, entry, knobs=None, series="BSS-2Y"):
        pts = [{"t": f"2026-01-{i + 1:02d}", "v": v} for i, v in enumerate(vals)]
        leg = {"entry": entry, "knobs": knobs if knobs is not None else self.OK,
               "series": series}
        return paper.track_leg(leg, points_of=lambda _s: pts)

    def test_조건이나_계열이_없으면_None_이다(self):
        """「못 잰다」와 「안 닿았다」는 다른 말이다."""
        pts = [{"t": "2026-01-01", "v": 1.0}]
        assert paper.track_leg({"entry": "2026-01-01", "knobs": None,
                                "series": "BSS-2Y"}, points_of=lambda _s: pts) is None
        assert paper.track_leg({"entry": "2026-01-01", "knobs": self.OK,
                                "series": None}, points_of=lambda _s: pts) is None

    def test_창이_안_차면_사유를_싣는다(self):
        got = self.leg([1.0, 2.0], "2026-01-02")
        assert got["hit"] is None and "룩백" in got["why"]

    def test_방향은_진입일_z_의_부호가_정한다(self):
        """엔진의 `position > 0` = 「아래에서 들어갔다」 = 진입 봉 z 가 음수."""
        # 아래에서: 마지막이 창의 평균보다 훨씬 낮다 → z < 0 → 롱
        down = self.leg([10.0, 10.0, 8.0], "2026-01-03")
        assert down["dir"] == 1 and down["entryZ"] < 0
        up = self.leg([10.0, 10.0, 12.0], "2026-01-03")
        assert up["dir"] == -1 and up["entryZ"] > 0

    def test_손절은_방향을_안_본다(self):
        """`|z| ≥ stopZ` — 엔진의 그 줄 그대로."""
        # 진입 뒤 같은 쪽으로 더 벌어진다(롱인데 더 내려감)
        vals = [10.0, 10.0, 8.0, 9.0, 10.5, 0.0]
        got = self.leg(vals, "2026-01-03", {**self.OK, "stopZ": 1.0})
        assert got["dir"] == 1
        assert abs(got["z"]) >= 1.0 and got["hit"] == "stop"

    def test_청산은_교차선이고_방향을_본다(self):
        """롱이면 `z ≥ −exitZ` — 밴드 안으로 **돌아온** 봉."""
        # 롱 진입 뒤 중심선을 지나 위로. ⚠ 마지막 창이 **평평하면 σ=0 이라 z 가
        # 없다** — 그건 「안 닿았다」가 아니라 「못 잰다」이므로 값을 움직여 둔다.
        vals = [10.0, 10.0, 8.0, 9.0, 10.0, 11.0]
        got = self.leg(vals, "2026-01-03", {**self.OK, "exitZ": 0.5, "stopZ": 9.0})
        assert got["dir"] == 1 and got["hit"] == "exit"

    def test_아직_안_닿았으면_hit_은_None(self):
        vals = [10.0, 10.0, 8.0, 9.0, 10.5, 8.2]
        got = self.leg(vals, "2026-01-03", {**self.OK, "exitZ": 0.0, "stopZ": 9.0})
        assert got["dir"] == 1 and got["hit"] is None

    def test_손절이_청산을_이긴다(self):
        """같은 날 둘 다 참이면 **손절**이 이름을 갖는다 — 엔진의 우선순위.

        손절 조건에서 나간 것을 「청산」이라 적으면 사후에 원인을 셀 수 없다.
        """
        # 롱인데 반대쪽으로 크게 지나감 → 청산선도 넘고 손절선도 넘는다
        vals = [10.0, 10.0, 8.0, 9.0, 10.5, 30.0]
        got = self.leg(vals, "2026-01-03", {**self.OK, "exitZ": 0.5, "stopZ": 1.0})
        assert got["dir"] == 1
        assert got["z"] >= -0.5, "청산 조건도 참이어야 이 검정이 성립한다"
        assert abs(got["z"]) >= 1.0
        assert got["hit"] == "stop"

    def test_z_는_엔진의_그_함수다(self):
        """장부와 엔진이 **같은 z** 를 쓴다 — 모집단 σ, 같은 창."""
        from app import mrbacktest as bt
        vals = [10.0, 11.0, 9.0, 12.0, 8.0, 13.0]
        got = self.leg(vals, "2026-01-06", {**self.OK, "lookback": 3})
        want = bt.rolling_series(vals, 3)["z"][-1]
        assert got["z"] == round(want, 3)

    def test_모르는_계열은_거절한다(self):
        """오타 하나가 「영원히 추적 안 되는 다리」를 만든다."""
        with pytest.raises(paper.LegRejected) as e:
            paper.check_series("BSS-2년")
        assert "모르는 계열" in str(e.value)
        assert paper.check_series(None) is None
        assert paper.check_series("  ") is None


# ── 그날 1등 제안 ────────────────────────────────────────────────────────────
class Test그날_1등_제안:
    """★다리를 담을 때 **그날의 1등을 옆에 적는다** [OWNER 2026-09-23 — "들어간
    시점에서의 최적 파라미터로" → 선택지에서 「손으로 치되 1등을 제안」].

    고르지 않는다 — 장부는 여전히 내가 친 것을 언다(`add_leg` 는 한 자도 안
    바뀐다). 여기서 재는 것은 셋이다: 격자가 **진입일까지의 자료만** 받는가
    (미래를 안 보는가) · 순위 규약이 계획면(`mrplan.pick_cell`)과 같은가 · 못 낼
    때 「1등이 없다」와 「못 잰다」를 가르는가.
    """

    @staticmethod
    def _cell(**kw) -> dict:
        base = dict(lookback=60, entryZ=2.0, exitZ=0.5, stopZ=2.5, entryMode="level",
                    cdarRatio=None, totalPnl=0.0, maxDrawdown=0.0, numTrades=0,
                    winRate=None)
        base.update(kw)
        return base

    @staticmethod
    def _grid_of(cells: list[dict]):
        """주입할 `grid_of` — 받은 재료를 적어 두고 칸 목록을 그대로 낸다."""
        seen: dict = {}

        def grid_of(leg: dict, knobs: dict, *, span: str) -> dict:
            seen["leg"] = leg
            seen["knobs"] = knobs
            seen["span"] = span
            return {"span": span, "from": leg["dates"][0], "to": leg["dates"][-1],
                    "days": len(leg["dates"]), "cells": cells}

        return grid_of, seen

    def test_격자는_진입일까지의_봉만_받는다(self):
        """★미래를 안 본다. 진입일 뒤의 봉이 격자에 들어가면 「그날의 1등」이
        아니라 「오늘의 1등을 그날에 붙인 것」이다 — 체결일을 뒤로 적은 다리에서
        그 둘은 다른 칸이다."""
        leg_of, dates, vals = _leg_of(600)
        grid_of, seen = self._grid_of([self._cell(cdarRatio=1.0)])
        out = paper.suggest("BSS-3Y", "2020-12-31", leg_of=leg_of, grid_of=grid_of)
        got = seen["leg"]
        assert got["dates"][-1] <= "2020-12-31"
        assert got["dates"][-1] == max(t for t in dates if t <= "2020-12-31")
        assert got["dates"] == dates[:len(got["dates"])], "앞머리는 그대로여야 한다"
        assert len(got["vals"]) == len(got["dates"]), "값 열이 날짜 열과 같은 자리에서 잘려야 한다"
        assert "r" not in got, "전체 표본의 시뮬을 잘린 재료와 같이 들고 가면 안 된다"
        assert out["asof"] == got["dates"][-1]
        assert seen["span"] == mrp.GRID_SPAN, "계획면과 같은 창이어야 같은 1등이다"
        assert seen["knobs"] == mrp.BASE_KNOBS
        assert out["inSample"] is True
        assert out["top"]["rank"] == 1

    def test_나란한_열을_전부_같은_자리에서_자른다(self):
        """캐리·게이트·비용 경로·롤 마스크는 봉마다 한 칸씩인 열이다. 하나만
        자르면 엔진이 어긋난 열을 곱한다 — 열쇠마다 길이를 잰다."""
        leg_of, dates, vals = _leg_of(300)
        n = len(dates)

        def rich(sid, knobs, *, accounting=True):
            base = leg_of(sid, knobs, accounting=accounting)
            return {**base, "carryKrw": [1.0] * n, "gate": [True] * n,
                    "costSeries": [0.5] * n, "tradable": [0.0] * n,
                    "pts": [{"t": t, "v": v} for t, v in zip(dates, vals)],
                    "carryLegs": [("a", [0.5] * n), ("b", [0.5] * n)]}

        cut = paper.cut_leg(rich("BSS-3Y", KNOBS), dates[99])
        for key in ("dates", "vals", "carryKrw", "gate", "costSeries", "tradable", "pts"):
            assert len(cut[key]) == 100, key
        assert all(len(xs) == 100 for _, xs in cut["carryLegs"])
        # 없는 열은 없는 채로 둔다 — BSS 는 롤 마스크가 None 이다.
        bare = paper.cut_leg({**rich("BSS-3Y", KNOBS), "tradable": None}, dates[99])
        assert bare["tradable"] is None

    def test_진입일_앞에_봉이_없으면_사유를_든다(self):
        leg_of, _dates, _vals = _leg_of(100)
        grid_of, seen = self._grid_of([self._cell(cdarRatio=1.0)])
        out = paper.suggest("BSS-3Y", "2019-06-01", leg_of=leg_of, grid_of=grid_of)
        assert out["top"] is None and out["list"] == []
        assert "앞서요" in out["why"]
        assert not seen, "재료가 없는데 격자를 돌리면 안 된다"

    def test_표본이_룩백보다_짧으면_사유를_든다(self):
        leg_of, dates, _vals = _leg_of(100)
        grid_of, seen = self._grid_of([self._cell(cdarRatio=1.0)])
        out = paper.suggest("BSS-3Y", dates[9], leg_of=leg_of, grid_of=grid_of)
        assert out["top"] is None
        assert "짧아요" in out["why"]
        assert out["asof"] == dates[9], "못 재도 어느 날까지 봤는지는 적는다"
        assert not seen

    def test_전부_못_잰_칸이면_1등이_없다고_말한다(self):
        """「1등이 없다」와 「못 잰다」는 다른 말이다 — `cells` 는 세고 `ranked` 는 0."""
        leg_of, _dates, _vals = _leg_of(300)
        grid_of, _seen = self._grid_of([self._cell(), self._cell(lookback=20)])
        out = paper.suggest("BSS-3Y", "2020-09-01", leg_of=leg_of, grid_of=grid_of)
        assert out["cells"] == 2 and out["ranked"] == 0
        assert out["top"] is None
        assert "순위를 못 매겼어요" in out["why"]

    def test_순위_규약은_계획면과_같다(self):
        """★두 벌을 둘 수밖에 없으면 대사로 묶는다 — `rank_cells` 의 1등은
        `mrplan.pick_cell` 의 그 칸이어야 한다. 못 잰 칸은 빠지고, 동점은 격자
        차례가 이긴다."""
        cells = [
            self._cell(lookback=20, cdarRatio=None),
            self._cell(lookback=60, cdarRatio=0.8),
            self._cell(lookback=120, cdarRatio=1.7),
            self._cell(lookback=20, entryZ=2.5, cdarRatio=1.7),   # 동점 — 뒤 칸
            self._cell(lookback=60, entryZ=2.5, cdarRatio=-0.2),
        ]
        ranked = paper.rank_cells(cells)
        assert [c["rank"] for c in ranked] == [1, 2, 3, 4]
        assert [c["cdarRatio"] for c in ranked] == [1.7, 1.7, 0.8, -0.2]
        assert mrp.knobs_of(ranked[0]) == mrp.knobs_of(mrp.pick_cell(cells))
        assert ranked[0]["lookback"] == 120 and ranked[1]["entryZ"] == 2.5
        assert all(set(paper.SUGGEST_FIELDS) <= set(c) for c in ranked)
        assert all(isinstance(c["lookback"], int) for c in ranked)

    def test_실제_격자와_잇는다(self):
        """`main._mr_optimize` 를 그대로 꽂아도 선다 — 잘린 재료가 그 함수의
        입력 규약(날짜·값·기준 노브·방향)을 만족하는가."""
        from app import main as M

        leg_of, dates, vals = _leg_of(600)

        def grid_of(leg: dict, knobs: dict, *, span: str) -> dict:
            return M._mr_optimize(leg["dates"], leg["vals"],
                                  {**knobs, "costBp": paper.COST_BP,
                                   "notional": paper.NOTIONAL},
                                  tuple(mr_mod.TRADABLE_DIRS["bss"]), span=span)

        entry = dates[399]
        out = paper.suggest("BSS-3Y", entry, leg_of=leg_of, grid_of=grid_of)
        assert out["cells"] == 162, "프리셋 그대로면 162칸이다"
        assert out["asof"] == entry
        assert out["top"] is not None and out["top"]["rank"] == 1
        assert out["list"][0] == out["top"]
        assert set(mrp.KNOB_KEYS) <= set(out["top"])
        # 같은 재료를 직접 돌린 1등과 같은 칸 — 이 함수가 격자를 손대지 않는다.
        direct = M._mr_optimize(dates[:400], vals[:400],
                                {**mrp.BASE_KNOBS, "costBp": paper.COST_BP,
                                 "notional": paper.NOTIONAL},
                                tuple(mr_mod.TRADABLE_DIRS["bss"]), span=mrp.GRID_SPAN)
        assert mrp.knobs_of(out["top"]) == mrp.knobs_of(mrp.pick_cell(direct["cells"]))

    def test_모르는_계열과_미래_진입일은_문에서_죽는다(self):
        leg_of, _d, _v = _leg_of(100)
        grid_of, seen = self._grid_of([])
        with pytest.raises(paper.LegRejected, match="모르는 계열"):
            paper.suggest("없는것", "2020-03-01", leg_of=leg_of, grid_of=grid_of)
        with pytest.raises(paper.LegRejected, match="미래"):
            paper.suggest("BSS-3Y", "2999-01-01", leg_of=leg_of, grid_of=grid_of)
        with pytest.raises(paper.LegRejected, match="계열이 있어야"):
            paper.suggest(None, "2020-03-01", leg_of=leg_of, grid_of=grid_of)
        assert not seen

    def test_라우트도_같은_문을_진다(self):
        """자료를 안 읽고 죽는 셋 — 화면이 사유를 그대로 세운다(422)."""
        from fastapi.testclient import TestClient

        from app import main as M

        c = TestClient(M.app)
        r = c.get("/api/paper/suggest", params={"series": "없는것", "entry": "2026-09-21"})
        assert r.status_code == 422 and "모르는 계열" in r.json()["detail"]
        r = c.get("/api/paper/suggest", params={"series": "BSS-3Y", "entry": "2999-01-01"})
        assert r.status_code == 422 and "미래" in r.json()["detail"]
        r = c.get("/api/paper/suggest", params={"series": "BSS-3Y"})
        assert r.status_code == 422

    def test_장부는_한_자도_안_바뀐다(self):
        """제안은 옆에 설 뿐이다 — `add_leg` 는 친 것을 언다(오너 선택)."""
        import inspect

        src = inspect.getsource(paper.add_leg)
        assert "suggest" not in src and "rank_cells" not in src


# ── 청산·손절 레벨 · 조건 붙이기 ─────────────────────────────────────────────
class Test청산_손절_레벨:
    """★z 의 두 문을 **오늘 밴드의 값**으로 푼다 [OWNER 2026-09-28 — "언제 손절,
    익절인지 레벨로 표시해주기로 했었는데 어디간거임?"].

    번역이지 계산이 아니다(`mrplan.levels_for` 와 같은 식): 롱은 청산 = 중심선 −
    exitZ·σ · 손절 = 중심선 − stopZ·σ, 숏은 반대쪽. 거리는 살아 있으면 양수이고
    0 이하면 `hit` 와 같은 말이어야 한다 — 두 표현이 갈리면 화면이 스스로를
    반박한다.
    """

    KN = {"lookback": 20, "entryZ": 2.0, "exitZ": 0.5, "stopZ": 3.0, "entryMode": "level"}

    @staticmethod
    def _pts(vals: list[float]) -> list[dict]:
        return [{"t": t, "v": v} for t, v in zip(_dates(len(vals)), vals)]

    def _leg(self, entry_idx: int, series: str = "BSS-3Y") -> dict:
        return {"entry": _dates(entry_idx + 1)[-1], "knobs": self.KN, "series": series}

    def test_롱의_레벨은_중심선_아래쪽_두_선이다(self):
        """진입일 z 가 음수(아래에서 들어감) → 청산선은 중심선 − 0.5σ, 손절선은 − 3σ."""
        vals = [10.0] * 19 + [4.0] + [8.0] * 5           # 20번째 봉에서 급락 → 진입
        pts = self._pts(vals)
        got = paper.track_leg(self._leg(19), points_of=lambda _s: pts)
        assert got["dir"] == 1 and got["hit"] is None
        assert got["exitLevel"] == pytest.approx(got["ma"] - 0.5 * got["sd"], abs=1e-3)
        assert got["stopLevel"] == pytest.approx(got["ma"] - 3.0 * got["sd"], abs=1e-3)
        assert got["exitLevel"] > got["stopLevel"]
        assert got["v"] == pytest.approx(vals[-1])
        # 살아 있으면 두 거리가 양수 — 값은 청산선 아래·손절선 위에 있다.
        assert got["exitGap"] > 0 and got["stopGap"] > 0
        assert got["exitGap"] == pytest.approx(got["exitLevel"] - got["v"], abs=1e-3)
        assert got["stopGap"] == pytest.approx(got["v"] - got["stopLevel"], abs=1e-3)
        # 가까운 문 — 서버가 고른다(§16). 이 픽스처는 청산선이 더 가깝다.
        near = got["nearest"]
        assert near["kind"] == ("exit" if got["exitGap"] <= got["stopGap"] else "stop")
        assert near["gap"] == pytest.approx(min(got["exitGap"], got["stopGap"]), abs=1e-3)

    def test_숏은_전부_반대쪽이다(self):
        vals = [10.0] * 19 + [16.0] + [12.0] * 5
        pts = self._pts(vals)
        got = paper.track_leg(self._leg(19), points_of=lambda _s: pts)
        assert got["dir"] == -1
        assert got["exitLevel"] == pytest.approx(got["ma"] + 0.5 * got["sd"], abs=1e-3)
        assert got["stopLevel"] == pytest.approx(got["ma"] + 3.0 * got["sd"], abs=1e-3)
        assert got["exitGap"] == pytest.approx(got["v"] - got["exitLevel"], abs=1e-3)
        assert got["stopGap"] == pytest.approx(got["stopLevel"] - got["v"], abs=1e-3)

    def test_거리가_0_이하면_hit_와_같은_말이다(self):
        """청산선을 지나면 exitGap ≤ 0 이고 hit == exit — 손절도 마찬가지."""
        vals = [10.0] * 19 + [4.0] + [10.5] * 3          # 되돌아와 중심선을 지났다
        got = paper.track_leg(self._leg(19), points_of=lambda _s: self._pts(vals))
        assert got["hit"] == "exit" and got["exitGap"] <= 0
        vals = [10.0] * 19 + [4.0] + [-40.0]              # 더 벌어져 손절
        got = paper.track_leg(self._leg(19), points_of=lambda _s: self._pts(vals))
        assert got["hit"] == "stop" and got["stopGap"] <= 0

    def test_못_잴_때도_레벨_칸이_같은_모양으로_온다(self):
        got = paper.track_leg(self._leg(2), points_of=lambda _s: self._pts([1.0] * 5))
        assert got["hit"] is None and got["why"]
        for k in ("unit", "v", "ma", "sd", "exitLevel", "stopLevel", "exitGap", "stopGap"):
            assert k in got and got[k] is None, k

    def test_단위는_계열의_것이고_주입하면_모른다(self):
        """주입 경로(시험)는 단위를 모르므로 None — 지어내지 않는다."""
        vals = [10.0] * 19 + [4.0] + [8.0] * 5
        got = paper.track_leg(self._leg(19), points_of=lambda _s: self._pts(vals))
        assert got["unit"] is None

    def test_못_잴_때도_내_다리_칸이_같은_모양으로_온다(self):
        """빈 모양과 산 모양의 열쇠가 같다 — 한쪽에만 칸을 더하면 여기서 깨진다."""
        got = paper.track_leg(self._leg(2), points_of=lambda _s: self._pts([1.0] * 5))
        assert "mine" in got and got["mine"] is None
        assert "mineWhy" in got and got["mineWhy"] is None

        def boom(_s):
            raise RuntimeError("DB 꺼짐")

        got = paper.track_leg(self._leg(2), points_of=boom)
        assert got["hit"] is None and "계열을 못 읽었어요" in got["why"] and "DB 꺼짐" in got["why"]
        live = paper.track_leg(self._leg(19), points_of=lambda _s: self._pts([10.0] * 19 + [4.0] + [8.0] * 5))
        assert set(got) == set(live)


class Test내_다리의_레벨:
    """★계열 값이 아니라 **내 다리의 금리**로 [OWNER 2026-09-28 — "이거 각각 레벨로
    적어줘야지 2년이면 3.xx 에서 얼마, 10년이면 4.xx 에서 얼마"].

    계열 값 = scale × Σ w·r. 나머지 다리를 지금 값에 둔 채 이 다리만 움직일 때
    계열이 그 선에 닿는 레벨 — 계열마다 다리 차례·부호가 다르므로 표 한 곳
    (`series_legs`)에서 만들고, 여기서 계열 가족마다 그 표가 **값을 닫는지**와
    번역이 맞는지를 잰다.
    """

    KN = {"lookback": 20, "entryZ": 2.0, "exitZ": 0.5, "stopZ": 3.0, "entryMode": "level"}

    def _pt(self, v, legs=None, t="2020-06-01"):
        return {"t": t, "v": v, "legs": legs}

    @staticmethod
    def _closes(table, v):
        return sum(l["w"] * l["v"] for l in table["legs"]) * table["scale"] == pytest.approx(v, abs=1e-6)

    def test_BSS_는_IRS_와_국고_두_다리다(self):
        t = paper.series_legs("bss", "BSS-3Y", self._pt(4.25, [4.0375, 3.995]))
        assert [(l["name"], l["kind"], l["tenor"], l["w"]) for l in t["legs"]] == [
            ("IRS", "irs", "3Y", 1.0), ("국고", "bond", "3Y", -1.0)]
        assert self._closes(t, 4.25)
        # 계열이 10bp 에 닿을 때: IRS 다리는 국고를 둔 채 3.995 + 0.10, 국고 다리는 IRS 를 둔 채 4.0375 − 0.10
        assert paper.leg_level_for(t, "irs", "3Y", 10.0) == (0, pytest.approx(4.095))
        assert paper.leg_level_for(t, "bond", "3Y", 10.0) == (1, pytest.approx(3.9375))
        assert paper.leg_level_for(t, "fut", "3Y", 10.0) is None, "선물은 BSS 의 다리가 아니다"
        assert paper.leg_level_for(t, "irs", "2Y", 10.0) is None, "만기가 다르면 다리가 아니다"

    def test_커브는_긴_짧은_차례고_짧은_쪽이_음수다(self):
        t = paper.series_legs("irc", "IRC-5Y-10Y", self._pt(5.0, [4.16, 4.11]))
        assert [(l["tenor"], l["w"]) for l in t["legs"]] == [("10Y", 1.0), ("5Y", -1.0)]
        assert self._closes(t, 5.0)
        # 9.55bp 로 스팁: 5Y 다리는 10Y 를 4.16 에 둔 채 4.0645, 10Y 다리는 5Y 를 둔 채 4.2055
        assert paper.leg_level_for(t, "irs", "5Y", 9.55)[1] == pytest.approx(4.0645)
        assert paper.leg_level_for(t, "irs", "10Y", 9.55)[1] == pytest.approx(4.2055)

    def test_퓨처스왑과_선물(self):
        t = paper.series_legs("fsw", "FSW-3Y", self._pt(-9.65, [4.0375, 4.134]))
        assert [(l["kind"], l["w"]) for l in t["legs"]] == [("irs", 1.0), ("fut", -1.0)]
        assert self._closes(t, -9.65)
        assert paper.leg_level_for(t, "fut", "3Y", 0.0)[1] == pytest.approx(4.0375)
        f = paper.series_legs("fut", "FUT-KTB10", self._pt(4.2, [4.2]))
        assert f["scale"] == 1.0 and f["legs"][0]["tenor"] == "10Y"
        assert paper.leg_level_for(f, "fut", "10Y", 4.31)[1] == pytest.approx(4.31)

    def test_플라이는_번들에서_읽고_벨리가_2다(self):
        irs = {"2Y": 3.9, "5Y": 4.1, "10Y": 4.2}
        t = paper.series_legs("irf", "IRF-2Y-5Y-10Y", self._pt(10.0),
                              irs_of=lambda tenor, _d: irs[tenor])
        assert [(l["tenor"], l["w"]) for l in t["legs"]] == [("2Y", -1.0), ("5Y", 2.0), ("10Y", -1.0)]
        assert self._closes(t, (2 * 4.1 - 3.9 - 4.2) * 100)
        # 벨리 다리: 윙 둘을 둔 채 플라이가 20bp 가 되는 5Y = (0.20 + 3.9 + 4.2) / 2
        assert paper.leg_level_for(t, "irs", "5Y", 20.0)[1] == pytest.approx((0.20 + 3.9 + 4.2) / 2)
        assert paper.series_legs("irf", "IRF-2Y-5Y-10Y", self._pt(10.0)) is None, "번들이 없으면 못 세운다"

    def test_눈금은_종류가_정한다(self):
        """주입 경로는 단위를 모른다 — bp 계열을 % 로 읽으면 조용히 100배 틀린다."""
        t = paper.series_legs("irc", "IRC-5Y-10Y", self._pt(5.0, [4.16, 4.11]))
        assert t["scale"] == 100.0
        assert paper.series_legs("fut", "FUT-KTB3", self._pt(4.13, [4.13]))["scale"] == 1.0

    def test_track_leg_이_내_다리로_옮겨_적고_손익까지_센다(self):
        """IRC-5Y-10Y 를 계열로 둔 5Y 리시브 — 계열 청산선을 5Y 금리로, 그 레벨에서의 손익은 장부의 식(왕복 비용)."""
        dates = _dates(26)
        curve = [5.0] * 19 + [-4.0] + [1.0] * 6                       # bp, 20번째에 급락 → 롱(스팁)
        pts = [{"t": d, "v": v, "legs": [4.16, 4.16 - v / 100.0]} for d, v in zip(dates, curve)]
        leg = {"entry": dates[19], "knobs": {"lookback": 20, "entryZ": 2.0, "exitZ": 0.5,
                                            "stopZ": 3.0, "entryMode": "level"},
               "series": "IRC-5Y-10Y", "kind": "irs", "tenor": "5Y",
               "rateSign": -1, "level": 4.145, "dv01": 1e7}
        got = paper.track_leg(leg, points_of=lambda _s: pts, cost_bp=0.5)
        assert got["dir"] == 1 and got["mine"] is not None and got["mineWhy"] is None
        m = got["mine"]
        # 10Y 를 4.16 에 둔 채: 5Y* = 4.16 − 계열선/100
        assert m["exitLevel"] == pytest.approx(4.16 - got["exitLevel"] / 100.0, abs=1e-4)
        assert m["stopLevel"] == pytest.approx(4.16 - got["stopLevel"] / 100.0, abs=1e-4)
        assert m["others"] == [{"name": "IRS 10Y", "v": 4.16}]
        # 손익 = rateSign × (레벨 − 내 레벨) × 100 × DV01 − 왕복 비용
        assert m["exitPnl"] == pytest.approx(-1 * (m["exitLevel"] - 4.145) * 100 * 1e7 - 2 * 0.5 * 1e7, abs=1)
        # 커브 롱(스팁)에서 짧은 다리(w<0)는 리시브라야 같은 쪽 — 이 다리는 맞다.
        assert m["aligned"] is True
        # 같은 다리를 페이로 잡았다면 계열 방향과 반대다 — 사실이라 지우지 않고 적는다.
        got_rev = paper.track_leg({**leg, "rateSign": 1}, points_of=lambda _s: pts)
        assert got_rev["mine"]["aligned"] is False
        # 계열의 다리가 아닌 계기(2Y)면 mine 은 없고 사유가 선다 — 계열 값은 그대로.
        got2 = paper.track_leg({**leg, "tenor": "2Y"}, points_of=lambda _s: pts)
        assert got2["mine"] is None and "다리가 아니에요" in got2["mineWhy"]
        assert got2["exitLevel"] == got["exitLevel"]

    # ── 아래 아홉은 적대 검증(2026-09-28 워크플로)의 시험 비평이 잡은 빈 자리다 ──

    def test_선물_아웃라이트는_scale_1_이고_매도가_롱과_같은_쪽이다(self):
        """다리가 하나라 계열 선 = 내 레벨(%, 100배 안 한다). 계열 롱(내재금리 반등)에
        선물 매도(+1)가 같은 쪽. 눈금을 100 으로 바꾸면 여기서 죽는다(변이 확인)."""
        dates = _dates(26)
        yld = [4.10] * 19 + [4.00] + [4.05] * 6                       # 20번째 급락 → 롱
        pts = [{"t": d, "v": v, "legs": [v]} for d, v in zip(dates, yld)]
        leg = {"entry": dates[19], "knobs": self.KN, "series": "FUT-KTB3",
               "kind": "fut", "tenor": "3Y", "rateSign": +1, "level": 4.01, "dv01": 2.8e6}
        got = paper.track_leg(leg, points_of=lambda _s: pts, cost_bp=0.5)
        m = got["mine"]
        assert got["dir"] == 1 and got["hit"] is None and m is not None
        assert m["w"] == 1.0 and m["others"] == []
        assert m["exitLevel"] == got["exitLevel"] and m["stopLevel"] == got["stopLevel"]
        assert m["exitPnl"] == pytest.approx((m["exitLevel"] - 4.01) * 100 * 2.8e6 - 2 * 0.5 * 2.8e6, abs=1)
        assert m["aligned"] is True
        assert paper.track_leg({**leg, "rateSign": -1}, points_of=lambda _s: pts)["mine"]["aligned"] is False
        # 점에 legs 가 없어도 값 자체가 다리다
        bare = [{"t": d, "v": v} for d, v in zip(dates, yld)]
        assert paper.track_leg(leg, points_of=lambda _s: bare)["mine"]["exitLevel"] == m["exitLevel"]
        ten = paper.track_leg({**leg, "series": "FUT-KTB10", "tenor": "10Y"}, points_of=lambda _s: pts)
        assert ten["mine"] is not None and ten["mine"]["name"] == "선물"
        # 3Y 다리는 KTB10 의 다리가 아니다
        assert paper.track_leg({**leg, "series": "FUT-KTB10"}, points_of=lambda _s: pts)["mine"] is None

    def test_퓨처스왑의_선물_다리는_IRS_를_둔_채_반대로_움직인다(self):
        t = paper.series_legs("fsw", "FSW-3Y", self._pt(-9.65, [4.0375, 4.134]))
        # 계열이 +10bp 로 가려면(IRS 고정) 선물 내재금리는 **내려야** 한다
        assert paper.leg_level_for(t, "fut", "3Y", 10.0)[1] == pytest.approx(3.9375)
        assert paper.leg_level_for(t, "irs", "3Y", 10.0)[1] == pytest.approx(4.234)
        assert paper.leg_level_for(t, "bond", "3Y", 10.0) is None, "국고는 FSW 의 다리가 아니다"
        dates = _dates(26)
        fsw = [-5.0] * 19 + [-14.0] + [-10.0] * 6                     # 롱 = IRS 페이 · 선물 매수
        pts = [{"t": d, "v": v, "legs": [4.0375, 4.0375 - v / 100.0]} for d, v in zip(dates, fsw)]
        leg = {"entry": dates[19], "knobs": self.KN, "series": "FSW-3Y", "kind": "fut", "tenor": "3Y",
               "rateSign": -1, "level": 4.134, "dv01": 2.8e6}
        got = paper.track_leg(leg, points_of=lambda _s: pts)
        m = got["mine"]
        assert got["dir"] == 1 and got["hit"] is None
        assert m["name"] == "선물" and m["w"] == -1.0 and m["aligned"] is True
        assert m["exitLevel"] == pytest.approx(4.0375 - got["exitLevel"] / 100.0, abs=1e-4)
        assert m["stopLevel"] == pytest.approx(4.0375 - got["stopLevel"] / 100.0, abs=1e-4)
        assert m["others"] == [{"name": "IRS", "v": 4.0375}]
        assert paper.track_leg({**leg, "rateSign": +1}, points_of=lambda _s: pts)["mine"]["aligned"] is False
        irs = paper.track_leg({**leg, "kind": "irs", "rateSign": +1}, points_of=lambda _s: pts)["mine"]
        assert irs["w"] == 1.0 and irs["aligned"] is True

    def test_BSS_국고_매수는_롱과_같은_쪽이고_다리가_없는_점이면_사유가_선다(self):
        dates = _dates(26)
        bss = [5.0] * 19 + [-4.0] + [1.0] * 6
        pts = [{"t": d, "v": v, "legs": [4.0 + v / 100.0, 4.0]} for d, v in zip(dates, bss)]   # [IRS, 국고]
        leg = {"entry": dates[19], "knobs": self.KN, "series": "BSS-3Y", "kind": "bond", "tenor": "3Y",
               "rateSign": -1, "level": 4.0, "dv01": 2.8e6}
        got = paper.track_leg(leg, points_of=lambda _s: pts)
        m = got["mine"]
        assert got["dir"] == 1 and m["name"] == "국고" and m["w"] == -1.0 and m["aligned"] is True
        irs_now = pts[-1]["legs"][0]
        assert m["exitLevel"] == pytest.approx(irs_now - got["exitLevel"] / 100.0, abs=1e-4)
        assert m["others"] == [{"name": "IRS", "v": round(irs_now, 4)}]
        irs = paper.track_leg({**leg, "kind": "irs", "rateSign": +1}, points_of=lambda _s: pts)["mine"]
        assert irs["w"] == 1.0 and irs["aligned"] is True
        assert irs["exitLevel"] == pytest.approx(4.0 + got["exitLevel"] / 100.0, abs=1e-4)
        # 다리 레벨이 없는 점이면 mine 은 없고 계열 값·hit 는 그대로다
        bare = [{"t": d, "v": v} for d, v in zip(dates, bss)]
        got2 = paper.track_leg(leg, points_of=lambda _s: bare)
        assert got2["mine"] is None and "다리 레벨을 못 읽었어요" in got2["mineWhy"]
        assert got2["exitLevel"] == got["exitLevel"] and got2["hit"] == got["hit"]

    def test_플라이는_track_leg_에서_번들로_읽고_없는_날이면_사유가_선다(self):
        dates = _dates(26)
        fly = [10.0] * 19 + [1.0] + [6.0] * 6                        # bp = 100·(2·5Y − 2Y − 10Y), 20번째 급락 → 롱
        pts = [{"t": d, "v": v} for d, v in zip(dates, fly)]          # 플라이 점엔 다리가 없다
        by_day = dict(zip(dates, fly))
        wings = {"2Y": 3.9, "10Y": 4.2}

        def irs_of(tenor, day):
            if tenor in wings:
                return wings[tenor]
            return (by_day[day] / 100.0 + 3.9 + 4.2) / 2.0           # 5Y 가 플라이 값을 닫게

        leg = {"entry": dates[19], "knobs": self.KN, "series": "IRF-2Y-5Y-10Y", "kind": "irs",
               "tenor": "5Y", "rateSign": +1, "level": 4.08, "dv01": 4.5e6}
        got = paper.track_leg(leg, points_of=lambda _s: pts, irs_of=irs_of)
        m = got["mine"]
        assert got["dir"] == 1 and got["hit"] is None and m is not None
        assert m["name"] == "IRS 5Y" and m["w"] == 2.0 and m["aligned"] is True      # 벨리 페이 = 플라이 롱
        assert m["exitLevel"] == pytest.approx((got["exitLevel"] / 100.0 + 3.9 + 4.2) / 2.0, abs=1e-4)
        assert m["stopLevel"] == pytest.approx((got["stopLevel"] / 100.0 + 3.9 + 4.2) / 2.0, abs=1e-4)
        assert m["others"] == [{"name": "IRS 2Y", "v": 3.9}, {"name": "IRS 10Y", "v": 4.2}]
        wing = paper.track_leg({**leg, "tenor": "2Y", "rateSign": -1},
                               points_of=lambda _s: pts, irs_of=irs_of)["mine"]
        assert wing["w"] == -1.0 and wing["aligned"] is True                          # 윙 리시브 = 플라이 롱
        belly_now = irs_of("5Y", dates[-1])
        assert wing["exitLevel"] == pytest.approx(2 * belly_now - 4.2 - got["exitLevel"] / 100.0, abs=1e-4)
        # 번들에 마지막 날이 없으면(적재 지연) mine 은 없고 계열 값은 남는다
        got2 = paper.track_leg(leg, points_of=lambda _s: pts,
                               irs_of=lambda t, d: None if d == dates[-1] else irs_of(t, d))
        assert got2["mine"] is None and "못 읽었어요" in got2["mineWhy"]
        assert got2["exitLevel"] == got["exitLevel"]
        # 점만 주입하고 irs_of 를 안 주면 같은 사유(플라이 점엔 다리가 없다)
        got3 = paper.track_leg(leg, points_of=lambda _s: pts)
        assert got3["mine"] is None and got3["mineWhy"]

    def test_주입_없이_부르면_계열은_mr_에서_다리는_번들에서_읽는다(self, monkeypatch):
        """build_sheet 의 그 호출(`track_leg(lg)`) — 계열은 `mr.series_points`, 플라이 다리는 `mrseries.bundle`."""
        from app import mrseries as mrs
        dates = _dates(26)
        fly = [10.0] * 19 + [1.0] + [6.0] * 6
        monkeypatch.setattr(mr_mod, "series_points",
                            lambda sid: {"id": sid, "unit": "bp",
                                         "points": [{"t": d, "v": v} for d, v in zip(dates, fly)]})
        irs = {"2Y": {d: 3.9 for d in dates}, "10Y": {d: 4.2 for d in dates},
               "5Y": {d: (v / 100.0 + 8.1) / 2.0 for d, v in zip(dates, fly)}}
        monkeypatch.setattr(mrs, "bundle", lambda: {"irs": irs})
        leg = {"entry": dates[19], "knobs": self.KN, "series": "IRF-2Y-5Y-10Y", "kind": "irs",
               "tenor": "5Y", "rateSign": +1, "level": 4.08, "dv01": 4.5e6}
        got = paper.track_leg(leg)
        assert got["unit"] == "bp" and got["mine"] is not None
        assert got["mine"]["exitLevel"] == pytest.approx((got["exitLevel"] / 100.0 + 8.1) / 2.0, abs=1e-4)
        del irs["5Y"][dates[-1]]                                       # 번들이 마지막 날에 아직 안 닿았다
        got2 = paper.track_leg(leg)
        assert got2["mine"] is None and got2["mineWhy"] and got2["exitLevel"] == got["exitLevel"]
        del irs["2Y"]                                                  # 만기 자체가 없어도 죽지 않는다
        assert paper.track_leg(leg)["mine"] is None

    def test_주입_없이_BSS_는_계열의_다리를_그대로_쓴다(self, monkeypatch):
        dates = _dates(26)
        bss = [5.0] * 19 + [-4.0] + [1.0] * 6
        monkeypatch.setattr(mr_mod, "series_points",
                            lambda sid: {"id": sid, "unit": "bp",
                                         "points": [{"t": d, "v": v, "legs": [4.0 + v / 100.0, 4.0]}
                                                    for d, v in zip(dates, bss)]})
        leg = {"entry": dates[19], "knobs": self.KN, "series": "BSS-3Y", "kind": "irs", "tenor": "3Y",
               "rateSign": +1, "level": 4.0, "dv01": 2.8e6}
        got = paper.track_leg(leg)
        assert got["unit"] == "bp" and got["mine"]["others"] == [{"name": "국고", "v": 4.0}]

    def test_계기_종류가_다르면_다리가_아니다(self):
        dates = _dates(26)
        curve = [5.0] * 19 + [-4.0] + [1.0] * 6
        pts = [{"t": d, "v": v, "legs": [4.16, 4.16 - v / 100.0]} for d, v in zip(dates, curve)]
        base = {"entry": dates[19], "knobs": self.KN, "series": "IRC-5Y-10Y", "tenor": "5Y",
                "rateSign": -1, "level": 4.145, "dv01": 1e7}
        for kind in ("bond", "fut"):
            got = paper.track_leg({**base, "kind": kind}, points_of=lambda _s: pts)
            assert got["mine"] is None, kind
            assert "IRC-5Y-10Y" in got["mineWhy"] and "다리가 아니에요" in got["mineWhy"]
            assert got["exitLevel"] is not None                       # 계열 값은 그대로 선다
        # 계기 칸이 아예 없는 옛 다리 · tenor None 도 죽지 않고 사유로 떨어진다
        got = paper.track_leg(base, points_of=lambda _s: pts)
        assert got["mine"] is None and got["mineWhy"] and got["hit"] is None
        got = paper.track_leg({**base, "kind": "irs", "tenor": None}, points_of=lambda _s: pts)
        assert got["mine"] is None and got["mineWhy"]

    def test_손절_손익도_적힌_레벨로_닫히고_비용은_왕복이다(self):
        dates = _dates(26)
        curve = [5.0] * 19 + [-4.0] + [1.0] * 6
        pts = [{"t": d, "v": v, "legs": [4.16, 4.16 - v / 100.0]} for d, v in zip(dates, curve)]
        leg = {"entry": dates[19], "knobs": self.KN, "series": "IRC-5Y-10Y", "kind": "irs", "tenor": "5Y",
               "rateSign": -1, "level": 4.145, "dv01": 1e7}
        m = paper.track_leg(leg, points_of=lambda _s: pts, cost_bp=0.5)["mine"]
        for lv, pnl in (("exitLevel", "exitPnl"), ("stopLevel", "stopPnl")):
            assert m[lv] == round(m[lv], 4)
            # 적힌 레벨(4자리)로 다시 곱해 같은 돈 — 1원 안에서 (안 접은 레벨로 세면 2~4만원 어긋난다)
            assert m[pnl] == pytest.approx(-1 * (m[lv] - 4.145) * 100 * 1e7 - 2 * 0.5 * 1e7, abs=1)
        m0 = paper.track_leg(leg, points_of=lambda _s: pts, cost_bp=0.0)["mine"]
        assert m0["exitPnl"] - m["exitPnl"] == pytest.approx(2 * 0.5 * 1e7, abs=1)     # 왕복
        assert m0["stopPnl"] - m["stopPnl"] == pytest.approx(2 * 0.5 * 1e7, abs=1)
        assert m0["exitPnl"] > 0 > m0["stopPnl"]                                          # 이 픽스처에서 청산=이익·손절=손해
        md = paper.track_leg(leg, points_of=lambda _s: pts)["mine"]                      # 기본 비용 = 장부의 그 상수
        assert md["exitPnl"] == pytest.approx(m0["exitPnl"] - 2 * paper.COST_BP * 1e7, abs=1)


class Test계열_다리_규약_대사:
    """★두 벌을 둘 수밖에 없으면 대사로 묶는다 — `series_legs` 는 `mrseries.points`
    ([스왑, 국고])와 `combo_points`([긴, 짧은])의 다리 차례를 **손으로 옮겨 적은 것**이다.
    저쪽이 차례를 바꾸면 페이퍼 북이 국고 금리를 IRS 줄에 적게 된다 — 합성 점이 아니라
    **그 함수가 낸 점**으로 표가 값을 닫는지를 잰다."""

    def test_BSS_점의_다리_차례는_스왑_국고이고_표가_그_값을_닫는다(self, monkeypatch):
        from app import mrseries as mrs
        dates = ["2026-01-02", "2026-01-05"]
        govt, swap, cd = [3.995, 4.000], [4.0375, 4.050], [2.9, 2.9]
        monkeypatch.setattr(mrs, "legs", lambda sid, *, need_cd=False: (dates, govt, swap, cd))
        last = mrs.points("BSS-3Y")["points"][-1]
        t = paper.series_legs("bss", "BSS-3Y", last)
        assert sum(l["w"] * l["v"] for l in t["legs"]) * t["scale"] == pytest.approx(last["v"], abs=1e-6)
        assert next(l["v"] for l in t["legs"] if l["kind"] == "irs") == swap[-1]
        assert next(l["v"] for l in t["legs"] if l["kind"] == "bond") == govt[-1]

    def test_커브_점의_다리_차례는_긴_짧은이고_표가_그_값을_닫는다(self, monkeypatch):
        from app import mrseries as mrs
        irs = {"5Y": {"2026-01-02": 4.11}, "10Y": {"2026-01-02": 4.16}}
        monkeypatch.setattr(mrs, "bundle", lambda: {"ktb": {}, "irs": irs, "cd": {}})
        last = mrs.combo_points("IRC-5Y-10Y")["points"][-1]
        t = paper.series_legs("irc", "IRC-5Y-10Y", last)
        assert sum(l["w"] * l["v"] for l in t["legs"]) * t["scale"] == pytest.approx(last["v"], abs=1e-6)
        assert next(l["v"] for l in t["legs"] if l["tenor"] == "10Y") == 4.16
        assert next(l["v"] for l in t["legs"] if l["tenor"] == "5Y") == 4.11
        irs.update({"2Y": {"2026-01-02": 3.9}})
        fly = mrs.combo_points("IRF-2Y-5Y-10Y")["points"][-1]
        assert paper.series_legs("irf", "IRF-2Y-5Y-10Y", fly) is None       # 플라이 점엔 다리가 없다
        t = paper.series_legs("irf", "IRF-2Y-5Y-10Y", fly,
                              irs_of=lambda tenor, day: mrs.bundle()["irs"][tenor].get(day))
        assert sum(l["w"] * l["v"] for l in t["legs"]) * t["scale"] == pytest.approx(fly["v"], abs=1e-6)


class Test조건_붙이기:
    """조건이 **없던** 다리에 조건을 붙인다 [OWNER 2026-09-28]. 「다시 고른다」가
    아니라 「비어 있던 칸을 적는다」 — 언 다리는 거절하고, 붙인 날을 적는다."""

    KN = {"lookback": 60, "entryZ": 2.5, "exitZ": 0.5, "stopZ": 3.0, "entryMode": "level"}

    def _store(self, *, knobs=None, closed=False) -> dict:
        st = dict(paper.EMPTY, legs=[])
        paper.add_leg(st, kind="irs", tenor="2Y", side="pay", entry="2026-09-21",
                      level=3.0, notional=1e10, dv01=1_900_000.0, knobs=knobs)
        if closed:
            paper.close_leg(st, 1, "2026-09-22", 3.1)
        return st

    def test_빈_다리에_붙고_붙인_날이_남는다(self):
        st = self._store()
        paper.attach_knobs(st, 1, self.KN, "BSS-2Y", today="2026-09-28")
        lg = st["legs"][0]
        assert lg["knobs"] == self.KN
        assert lg["series"] == "BSS-2Y"
        assert lg["knobsAt"] == "2026-09-28", "뒤에 붙인 조건은 그 날을 들고 있어야 한다"

    def test_언_조건은_다시_고르지_않는다(self):
        st = self._store(knobs=self.KN)
        with pytest.raises(paper.LegRejected, match="이미 조건이"):
            paper.attach_knobs(st, 1, {**self.KN, "lookback": 20}, None, today="2026-09-28")
        assert st["legs"][0]["knobs"] == self.KN and "knobsAt" not in st["legs"][0]

    def test_닫힌_다리와_반쪽_조건과_없는_다리는_거절한다(self):
        with pytest.raises(paper.LegRejected, match="닫혔어요"):
            paper.attach_knobs(self._store(closed=True), 1, self.KN, None)
        with pytest.raises(paper.LegRejected, match="빠진 것"):
            paper.attach_knobs(self._store(), 1, {"lookback": 60}, None)
        with pytest.raises(paper.LegRejected, match="붙일 조건이"):
            paper.attach_knobs(self._store(), 1, None, None)
        with pytest.raises(paper.LegRejected, match="없어요"):
            paper.attach_knobs(self._store(), 9, self.KN, None)

    def test_계열은_없을_때만_받는다(self):
        st = dict(paper.EMPTY, legs=[])
        paper.add_leg(st, kind="irs", tenor="2Y", side="pay", entry="2026-09-21",
                      level=3.0, notional=1e10, dv01=1_900_000.0, series="BSS-2Y")
        paper.attach_knobs(st, 1, self.KN, "BSS-3Y", today="2026-09-28")
        assert st["legs"][0]["series"] == "BSS-2Y", "담을 때 적은 계열이 이긴다"

    def test_라우트가_사유를_그대로_낸다(self, monkeypatch, tmp_path):
        from fastapi.testclient import TestClient

        from app import main as M

        monkeypatch.setattr(paper, "STORE", tmp_path / "book.json")
        c = TestClient(M.app)
        c.post("/api/paper/leg", json=dict(kind="irs", tenor="2Y", side="pay",
                                           entry="2026-09-21", level=3.0, notional=1e10))
        r = c.post("/api/paper/leg/knobs", json=dict(n=1, knobs={"lookback": "60"}))
        assert r.status_code == 422 and "빠진 것" in r.json()["detail"]
        r = c.post("/api/paper/leg/knobs", json=dict(n=1, knobs=self.KN, series="BSS-2Y"))
        assert r.status_code == 200, r.text
        assert r.json()["available"] is True
        lg = r.json()["position"]["legs"][0]
        assert lg["knobs"]["lookback"] == 60 and lg["knobsAt"]
        r = c.post("/api/paper/leg/knobs", json=dict(n=1, knobs=self.KN))
        assert r.status_code == 422 and "이미 조건이" in r.json()["detail"]


# ── 트레이드 추적 ────────────────────────────────────────────────────────────
class Test트레이드_추적:
    """다리들을 **백테스트 엔진의 포지션**으로 옮겨 적고, 장부 손익을 그 분해로
    대조한다 [OWNER 2026-09-28]. 산술은 안 만든다 — 방향 번역 한 번과 대조식 하나."""

    def _leg(self, kind: str, side: str, **kw) -> dict:
        base = dict(n=1, kind=kind, tenor="3Y", side=side,
                    rateSign=paper.SIDE_SIGN[(kind, side)],
                    entry="2025-09-22", exit=None, level=3.0,
                    notional=1e10, dv01=2_850_000.0)
        base.update(kw)
        return base

    def test_방향은_계기마다_한_번만_옮긴다(self):
        """스왑 +1 = 페이(금리↑에 번다) · 채권·선물 +1 = 매수(금리↓에 번다)."""
        got = paper.trace_positions([
            self._leg("irs", "pay"), self._leg("irs", "receive", n=2),
            self._leg("bond", "buy", n=3), self._leg("fut", "sell", n=4),
            self._leg("fut", "buy", n=5, exit="2026-01-05"),
        ])
        assert [(g["id"], g["direction"]) for g in got] == [
            ("3Y", 1), ("3Y", -1), ("CB:KTB:3Y", 1), ("FUT:3Y", -1), ("FUT:3Y", 1)]
        assert got[4]["exit"] == "2026-01-05" and got[0]["exit"] is None
        assert all(g["entry"] == "2025-09-22" and g["notional"] == 1e10 for g in got)

    def test_대조식이_닫힌다(self):
        """장부 손익 = 체결 차이 + 엔진 손익 − 비용 + 차이 — 그리고 차이는 남는 몫이다."""
        leg = self._leg("irs", "pay", level=3.97)
        row = {"id": "3Y", "label": "3Y", "entry": "2025-09-22", "exit": "2026-09-23",
               "entryValue": 3.99, "pnl": 100_000.0, "valuation": 90_000.0,
               "carry": 20_000.0, "rolldown": -10_000.0, "startup": 0.0}
        got = paper.reconcile_leg(leg, row, paper_pnl=150_000.0, cost=1_425_000.0)
        # 페이인데 종가(3.99)보다 싸게(3.97) 냈다 → 체결 차이 = +2bp × DV01
        assert got["exec"] == pytest.approx(2.0 * 2_850_000.0, abs=1)
        assert got["engine"] == 100_000.0 and got["funding"] is None
        assert got["residual"] == pytest.approx(
            150_000.0 - (got["exec"] + 100_000.0 - 1_425_000.0), abs=1)
        assert got["entryClose"] == 3.99 and got["level"] == 3.97

    def test_진입일_종가를_모르면_체결_차이도_차이도_없다(self):
        leg = self._leg("bond", "buy")
        got = paper.reconcile_leg(leg, {"id": "CB:KTB:3Y", "pnl": 1.0},
                                  paper_pnl=2.0, cost=3.0)
        assert got["exec"] is None and got["residual"] is None
        # 채권은 `entryYield` 가 진입일 종가다.
        assert paper.entry_close_of({"entryYield": 2.457, "entryValue": None}) == 2.457

    def test_라우트의_문(self, monkeypatch, tmp_path):
        from fastapi.testclient import TestClient

        from app import main as M

        monkeypatch.setattr(paper, "STORE", tmp_path / "book.json")
        c = TestClient(M.app)
        assert c.get("/api/paper/trace", params={"legs": "a"}).status_code == 422
        assert c.get("/api/paper/trace", params={"legs": ""}).status_code == 422
        r = c.get("/api/paper/trace", params={"legs": "7"})
        assert r.status_code == 422 and "없는 다리" in r.json()["detail"]


# ── 묶음 소계 ────────────────────────────────────────────────────────────────
class Test묶음_소계:
    """「트레이드」= 묶음. 소계는 **서버가 센다**(§16) — 화면 가드
    (`guards/portfolio-canon.test.ts`)가 화면에 `reduce` 가 없음을 잰다."""

    @staticmethod
    def _row(n: int, tag: str, *, pnl, open=True, rs=1, dv01=1_000_000.0,
             notional=1e10) -> dict:
        return {"n": n, "tag": tag, "pnl": pnl, "open": open, "rateSign": rs,
                "dv01": dv01, "notional": notional}

    def test_묶음_차례는_첫_등장이고_없는_다리는_제_혼자다(self):
        rows = [self._row(1, "A", pnl=1.0), self._row(2, "", pnl=2.0),
                self._row(3, "A", pnl=3.0), self._row(4, "B", pnl=None)]
        got = paper.group_legs(rows)
        assert [g["key"] for g in got] == ["tag:A", "leg:2", "tag:B"]
        assert got[0]["legs"] == [1, 3] and got[0]["label"] == "A"
        assert got[1]["label"].startswith("2번 다리")

    def test_합의_규율은_카드와_같다(self):
        """한 다리라도 아직이면 합계는 None, 매겨진 것만의 소계는 따로."""
        rows = [self._row(1, "A", pnl=1.0, rs=1, dv01=2.0),
                self._row(2, "A", pnl=None, rs=-1, dv01=3.0),
                self._row(3, "A", pnl=5.0, open=False, rs=1, dv01=9.0)]
        g = paper.group_legs(rows)[0]
        assert g["pnl"] is None and g["scoredPnl"] == 6.0
        assert g["scored"] == 2 and g["pending"] == 1
        assert g["open"] == 2 and g["closed"] == 1
        # DV01 은 부호를 지고, 들고 있는 다리만.
        assert g["netDv01"] == pytest.approx(2.0 - 3.0)
        assert g["grossDv01"] == pytest.approx(5.0)
        assert g["openNotional"] == pytest.approx(2e10)
        assert g["unconditioned"] == 2, "열린 두 다리 다 조건이 없다(닫힌 다리는 안 센다)"
        full = paper.group_legs([self._row(1, "A", pnl=1.0), self._row(2, "A", pnl=2.5)])[0]
        assert full["pnl"] == 3.5 and full["scoredPnl"] == 3.5 and full["pending"] == 0

    def test_묶음_줄은_계열_값을_말한다(self):
        """★[OWNER 2026-09-28 — "묶음으로 지금 얼마나 벌어져있는지 왜 안알려줘?"].
        내 체결로 만든 진입 스프레드 · 지금 · Δ · 밴드 · 계열 청산·손절."""
        dates = _dates(26)
        curve = [5.0] * 19 + [-4.0] + [1.0] * 6                       # IRC-5Y-10Y, 20번째 급락
        pts = [{"t": d, "v": v, "legs": [4.16, 4.16 - v / 100.0]} for d, v in zip(dates, curve)]
        KN = {"lookback": 20, "entryZ": 2.0, "exitZ": 0.5, "stopZ": 3.0, "entryMode": "level"}
        rows = [
            {"n": 1, "tag": "T", "pnl": 1.0, "open": True, "rateSign": -1, "dv01": 1e7,
             "notional": 2e10, "kind": "irs", "tenor": "5Y", "level": 4.145,
             "entry": dates[19], "series": "IRC-5Y-10Y", "knobs": KN},
            {"n": 2, "tag": "T", "pnl": -1.0, "open": True, "rateSign": 1, "dv01": 1e7,
             "notional": 1e10, "kind": "irs", "tenor": "10Y", "level": 4.195,
             "entry": dates[20], "series": "IRC-5Y-10Y", "knobs": None},
        ]
        g = paper.group_legs(rows, points_of=lambda _s: pts)[0]
        assert g["series"] == "IRC-5Y-10Y" and g["seriesWhy"] is None
        # 내 체결로 만든 스프레드: (4.195 − 4.145) × 100 = 5.0bp — 계열 단위
        assert g["myLevel"] == pytest.approx(5.0) and g["myBasis"] == "fill"
        assert g["unit"] == "bp" and g["now"] == pytest.approx(1.0) and g["asof"] == dates[-1]
        assert g["delta"] == pytest.approx(1.0 - 5.0)
        # 진입은 묶음의 **첫** 체결일 — 그날의 계열 값도 같이
        assert g["entryT"] == dates[19] and g["entryV"] == pytest.approx(-4.0)
        # 조건은 조건 있는 첫 다리의 것, 밴드·청산·손절은 계열 값(내 다리 번역은 없다)
        assert g["knobs"] == KN and g["knobsMixed"] is False
        t = g["track"]
        assert t["dir"] == 1 and t["exitLevel"] is not None and t["mine"] is None
        assert t["legsNow"][0]["tenor"] == "10Y" and t["entryV"] == pytest.approx(-4.0)

    def test_묶음_계열_시선의_빈_자리들(self):
        dates = _dates(26)
        curve = [5.0] * 19 + [-4.0] + [1.0] * 6
        pts = [{"t": d, "v": v, "legs": [4.16, 4.16 - v / 100.0]} for d, v in zip(dates, curve)]
        base = {"pnl": None, "open": True, "rateSign": -1, "dv01": 1e7, "notional": 1e10,
                "kind": "irs", "level": 4.145, "entry": dates[19], "knobs": None}
        # 반쪽 묶음(5Y 만) — 스프레드를 내 체결로 못 만들어 진입일 종가로 떨어진다
        half = paper.group_series([{**base, "n": 1, "tag": "H", "tenor": "5Y", "series": "IRC-5Y-10Y"}],
                                  points_of=lambda _s: pts)
        assert half["myLevel"] == pytest.approx(-4.0) and half["myBasis"] == "close"
        assert half["delta"] == pytest.approx(1.0 - (-4.0)) and half["track"] is None
        # 계열 밖 계기가 섞여도(2Y) 내 스프레드는 안 세운다
        extra = paper.group_series([
            {**base, "n": 1, "tenor": "5Y", "series": "IRC-5Y-10Y"},
            {**base, "n": 2, "tenor": "10Y", "rateSign": 1, "level": 4.195, "series": "IRC-5Y-10Y"},
            {**base, "n": 3, "tenor": "2Y", "series": "IRC-5Y-10Y"},
        ], points_of=lambda _s: pts)
        assert extra["myBasis"] == "close"
        # 계열이 갈리면 · 계열이 없으면 사유만 선다
        mixed = paper.group_series([{**base, "n": 1, "tenor": "5Y", "series": "IRC-5Y-10Y"},
                                    {**base, "n": 2, "tenor": "10Y", "series": "BSS-10Y"}],
                                   points_of=lambda _s: pts)
        assert mixed["series"] is None and "달라요" in mixed["seriesWhy"]
        none = paper.group_series([{**base, "n": 1, "tenor": "5Y", "series": None}])
        assert none["series"] is None and "없어요" in none["seriesWhy"] and none["now"] is None
        # 조건이 다리마다 다르면 첫 것을 쓰고 그 사실을 적는다
        k1 = {"lookback": 20, "entryZ": 2.0, "exitZ": 0.5, "stopZ": 3.0, "entryMode": "level"}
        k2 = {**k1, "lookback": 25}
        mixk = paper.group_series([{**base, "n": 1, "tenor": "5Y", "series": "IRC-5Y-10Y", "knobs": k1},
                                   {**base, "n": 2, "tenor": "10Y", "rateSign": 1, "level": 4.195,
                                    "series": "IRC-5Y-10Y", "knobs": k2}],
                                  points_of=lambda _s: pts)
        assert mixk["knobs"] == k1 and mixk["knobsMixed"] is True and mixk["track"] is not None
        # 계열을 못 읽으면 사유가 선다 — 죽지 않는다
        def boom(_s):
            raise RuntimeError("DB 꺼짐")
        dead = paper.group_series([{**base, "n": 1, "tenor": "5Y", "series": "IRC-5Y-10Y"}], points_of=boom)
        assert dead["series"] == "IRC-5Y-10Y" and "DB 꺼짐" in dead["seriesWhy"] and dead["now"] is None

    def test_계열_경로는_진입_앞_봉부터_선을_같이_낸다(self):
        """추적 창의 그림 재료 — 값·중심선·청산선·손절선이 같은 길이로, 진입 자리가
        어딘지, 선은 `track_leg` 와 같은 번역인지."""
        dates = _dates(60)
        vals = [10.0 + (i % 5) * 0.4 for i in range(60)]
        vals[40] = 2.0                                                # 41번째 급락 → 롱
        pts = [{"t": d, "v": v} for d, v in zip(dates, vals)]
        KN = {"lookback": 20, "entryZ": 2.0, "exitZ": 0.5, "stopZ": 3.0, "entryMode": "level"}
        p = paper.series_path("IRC-5Y-10Y", dates[40], KN, points_of=lambda _s: pts, lead=10)
        assert p["why"] is None and p["dir"] == 1 and p["unit"] == "bp"
        assert p["dates"][0] == dates[30] and p["entryIdx"] == 10
        assert len(p["dates"]) == len(p["values"]) == len(p["ma"]) == len(p["exit"]) == len(p["stop"]) == 30
        # 선은 오늘 `track_leg` 가 내는 그 값과 같다(같은 번역)
        t = paper.track_leg({"entry": dates[40], "knobs": KN, "series": "IRC-5Y-10Y",
                             "kind": "", "tenor": ""}, points_of=lambda _s: pts)
        assert p["exit"][-1] == pytest.approx(t["exitLevel"], abs=1e-4)
        assert p["stop"][-1] == pytest.approx(t["stopLevel"], abs=1e-4)
        # 롱이면 청산선이 손절선보다 위, 둘 다 중심선 아래
        assert p["exit"][-1] > p["stop"][-1] and p["ma"][-1] > p["exit"][-1]
        # 앞머리(창 미달)는 None 이고 값은 그대로 있다 — 선이 끊길 뿐 지어내지 않는다
        p0 = paper.series_path("IRC-5Y-10Y", dates[40], KN, points_of=lambda _s: pts, lead=45)
        assert p0["ma"][0] is None and p0["values"][0] == pytest.approx(vals[0])
        # 못 그리는 경우는 사유로
        assert "앞서요" in paper.series_path("IRC-5Y-10Y", "2019-01-01", KN, points_of=lambda _s: pts)["why"]
        assert "조건이" in paper.series_path("IRC-5Y-10Y", dates[40], {"lookback": 20}, points_of=lambda _s: pts)["why"]
        assert "모르는" in paper.series_path("XXX", dates[40], KN, points_of=lambda _s: pts)["why"]

    def test_my_series_level_은_다리마다_하나씩일_때만(self):
        t = paper.series_legs("bss", "BSS-3Y", {"t": "2026-09-23", "v": 4.25, "legs": [4.0375, 3.995]})
        irs = {"kind": "irs", "tenor": "3Y", "level": 4.03}
        bond = {"kind": "bond", "tenor": "3Y", "level": 4.00}
        assert paper.my_series_level(t, [irs, bond]) == pytest.approx(3.0)      # (4.03 − 4.00) × 100
        assert paper.my_series_level(t, [irs]) is None                            # 반쪽
        assert paper.my_series_level(t, [irs, bond, dict(bond)]) is None          # 겹침
        assert paper.my_series_level(t, [irs, bond, {"kind": "fut", "tenor": "3Y", "level": 4.1}]) is None
        f = paper.series_legs("fut", "FUT-KTB3", {"t": "2026-09-23", "v": 4.134, "legs": [4.134]})
        assert paper.my_series_level(f, [{"kind": "fut", "tenor": "3Y", "level": 4.13}]) == pytest.approx(4.13)

    def test_장중_레벨로_다시_매긴다(self):
        """★[OWNER 2026-09-28 — "지금 2년은 4.06, 5년은 4.27, 10년은 4.3375"].

        마크는 종가인데 데스크는 장중에 산다 — 연휴 뒤 첫날엔 장부가 사흘 전 수에
        묶인다. 친 값으로 **다시 매기되** 장부엔 안 적고, 종가가 아니라는 사실을
        수와 같이 싣는다(`live`). 계열 값·밴드도 그 값 위에 서야 한다 — 마크만
        바꾸고 밴드를 종가로 두면 한 줄이 두 시계를 말한다.
        """
        dates = _dates(26)
        curve = [5.0] * 19 + [-4.0] + [1.0] * 6
        pts = [{"t": d, "v": v, "legs": [4.16, 4.16 - v / 100.0]} for d, v in zip(dates, curve)]
        KN = {"lookback": 20, "entryZ": 2.0, "exitZ": 0.5, "stopZ": 3.0, "entryMode": "level"}
        base = {"pnl": 0.0, "open": True, "dv01": 1e7, "notional": 1e10, "kind": "irs",
                "entry": dates[19], "series": "IRC-5Y-10Y", "knobs": KN, "tag": "T"}
        rows = [{**base, "n": 1, "tenor": "5Y", "rateSign": -1, "level": 4.145},
                {**base, "n": 2, "tenor": "10Y", "rateSign": 1, "level": 4.195}]
        mk = paper.parse_marks("irs:5Y=4.27;irs:10Y=4.3375")
        assert mk == {("irs", "5Y"): 4.27, ("irs", "10Y"): 4.3375}

        g = paper.group_legs(rows, points_of=lambda _s: pts, marks=mk)[0]
        # 계열 값 = 100 × (10Y − 5Y) = 6.75bp · 내 레벨 5.00 → Δ +1.75
        assert g["now"] == pytest.approx(6.75) and g["live"] is True
        assert g["myLevel"] == pytest.approx(5.0) and g["delta"] == pytest.approx(1.75)
        assert g["asof"] == dt.date.today().isoformat(), "장중이면 날은 오늘이다"
        assert g["track"]["live"] is True and g["track"]["z"] is not None

        # 종가로 보면 같은 장부가 다른 수다 — 그 차이가 이 기능의 값어치다.
        g0 = paper.group_legs(rows, points_of=lambda _s: pts)[0]
        assert g0["live"] is False and g0["now"] == pytest.approx(1.0)
        assert g0["track"]["z"] != g["track"]["z"]

        # 반쪽(한 다리만)은 계열 값을 안 만든다 — 두 시계를 섞지 않는다.
        half = paper.group_series(rows, points_of=lambda _s: pts,
                                  marks=paper.parse_marks("irs:5Y=4.27"))
        assert half["live"] is False and half["now"] == pytest.approx(1.0)

    def test_장중_레벨의_문(self):
        assert paper.parse_marks(None) == {} and paper.parse_marks("  ") == {}
        for bad, why in (("irs5Y=4", "꼴이 이상"), ("xxx:5Y=4", "모르는 계기"),
                         ("irs:5Y=사", "숫자가 아니"), ("irs:5Y=99", "범위")):
            with pytest.raises(paper.LegRejected, match=why):
                paper.parse_marks(bad)

    def test_live_한_낱말이_지금_시세를_통째로_깐다(self, monkeypatch):
        """★[OWNER 2026-09-28 — "따로 내가 입력 안해도 되게 그냥 1년부터 10년까지
        자동으로 다 넣어주고"]. `marks=live` 는 시세를 깔고, 친 칸이 그 위를 덮는다.
        시세를 못 읽어도 **죽지 않고** 종가로 선다 — 장 끝난 뒤에도 화면은 선다."""
        from app import main as M, paperlive

        monkeypatch.setattr(paperlive, "live_marks", lambda: {"levels": [
            {"kind": "irs", "tenor": "5Y", "level": 4.27, "at": "13:30:48", "source": "IRS"},
            {"kind": "irs", "tenor": "10Y", "level": 4.3375, "at": "13:30:48", "source": "IRS"},
            {"kind": "fut", "tenor": "3Y", "level": 4.2648, "at": "13:33", "source": "국채선물"},
        ], "asof": "13:33", "sources": [], "why": None})
        assert M._paper_marks("live") == {("irs", "5Y"): 4.27, ("irs", "10Y"): 4.3375,
                                          ("fut", "3Y"): 4.2648}
        # 친 칸이 깔린 값을 덮는다 — 한 칸만 달리 보고 싶을 때.
        got = M._paper_marks("live;irs:5Y=4.50")
        assert got[("irs", "5Y")] == 4.50 and got[("irs", "10Y")] == 4.3375
        # 낱말이 없으면 종전 그대로(손으로 친 것만).
        assert M._paper_marks("irs:5Y=4.50") == {("irs", "5Y"): 4.50}
        assert M._paper_marks("") == {} and M._paper_marks(None) == {}

        def boom():
            raise RuntimeError("인포맥스 꺼짐")

        monkeypatch.setattr(paperlive, "live_marks", boom)
        assert M._paper_marks("live") == {}, "시세를 못 읽으면 종가로 선다 — 안 죽는다"
        assert M._paper_marks("live;irs:5Y=4.50") == {("irs", "5Y"): 4.50}

    def test_지금_시세는_낱말을_옮길_뿐이다(self):
        """★[OWNER 2026-09-28 — "떠있는거 보고 바로바로 입력해주면 안되나?"].

        `paperlive` 는 **읽기와 번역**만 한다 — 값을 어떻게 쓰는지는 `paper` 가 안다.
        오래된 값을 「지금」이라 안 적는 것이 이 모듈의 하중이라 그것을 잰다.
        """
        import datetime as _d

        from app import paperlive as pl

        # 만기 낱말이 다리의 그것과 같다 — 1.5Y 는 이 표에서만 개월(`irs_18m`)이다.
        assert pl.IRS_COL["1.5Y"] == "irs_18m" and pl.IRS_COL["10Y"] == "irs_10y"
        assert pl.FUT_CODE["C65"] == ("3Y", 3) and pl.FUT_CODE["C67"] == ("10Y", 10)
        # 시각은 `TIME` 이라 timedelta 로 온다 — 사람이 읽는 꼴로 옮긴다.
        assert pl._hhmmss(_d.timedelta(seconds=48648)) == "13:30:48"
        now = _d.datetime(2026, 9, 28, 13, 40, 0)
        assert pl._age_min(_d.date(2026, 9, 28), "13:30:00", now) == pytest.approx(10.0)
        assert pl._age_min(_d.date(2026, 9, 28), "엉망", now) is None

    def test_만기_오타가_장중을_사칭하지_못한다(self):
        """★[적대 검증 2026-09-28]. `irs:5YY=4.27` 이 **200 으로 통과**했다 —
        아무 다리에도 안 물리는데 응답의 `live` 목록에는 그 낱말이 실려서, 화면이
        종가를 보면서 「장중」을 적었다. `parse_marks` 의 독스트링이 「모르는 낱말은
        조용히 버리지 않고 사유를 들고 죽는다」고 이미 약속한 자리였고, 코드는 계기만
        보고 있었다.
        """
        for bad, why in (("irs:5YY=4.27", "없는 만기"), ("bond:99Y=3.0", "없는 만기"),
                         ("fut:2Y=4.0", "없는 만기")):
            with pytest.raises(paper.LegRejected, match=why):
                paper.parse_marks(bad)
        # 사유가 고를 수 있는 목록을 들고 있다 — 막고 이유를 안 적으면 다음 사람이 헤맨다.
        with pytest.raises(paper.LegRejected, match="3Y · 10Y"):
            paper.parse_marks("fut:2Y=4.0")
        # 진짜 만기는 그대로 산다(좁게 잡아 기능을 없애지 않았는가).
        assert paper.parse_marks("irs:1.5Y=3.9")[("irs", "1.5Y")] == 3.9
        assert paper.parse_marks("irs:4Y=3.9")[("irs", "4Y")] == 3.9      # LEG_TENORS 쪽
        assert paper.parse_marks("bond:3M=3.9")[("bond", "3M")] == 3.9    # ASW_TENORS 쪽

    def test_만기_어휘가_화면의_그것을_덮는다(self):
        """어휘가 **한 진실**인가 — 화면이 고를 수 있는 것을 마크가 다 받아야 한다.

        화면의 목록은 `/api/paper/instruments` 가 내리고 그것은 `cashbond.ASW_TENORS`
        (+ 선물은 `paper.FUT_TENORS`)다. 이 시험이 없으면 한쪽만 늘어나 「화면에서는
        고를 수 있는데 장중 레벨은 못 받는 만기」가 생긴다.
        """
        from app import cashbond, instruments

        vocab = paper._mark_tenors()
        for t in cashbond.ASW_TENORS:
            assert t in vocab["irs"] and t in vocab["bond"], t
        for t in instruments.LEG_TENORS:
            assert t in vocab["irs"], t
        assert vocab["fut"] == paper.FUT_TENORS

    def test_두_선물이_따로_늙는다(self):
        """★[적대 검증 2026-09-28]. 3년은 지금이고 10년이 40분 전이면, 종전에는
        10년이 **말없이 사라졌다** — `continue` 로 버리면서 `why` 는 `max(stamps)`
        한 줄로만 적었기 때문이다. 「19칸 들어가는 중」이 18칸이 되는데 화면에 사유가
        없으면, 다음 사람은 그 칸이 원래 없는 줄로 읽는다.
        """
        import datetime as _d

        from app import paperlive as pl
        from irs_pricer.services.simulation.futures_pricing import implied_yield

        now = _d.datetime(2026, 9, 28, 13, 40, 0)
        rows = [("C65", 102.03, _d.date(2026, 9, 28), _d.timedelta(hours=13, minutes=39)),
                ("C67", 103.26, _d.date(2026, 9, 28), _d.timedelta(hours=13, minutes=0))]
        lv, why, meta = pl.fut_levels(rows, now)
        assert [x["tenor"] for x in lv] == ["3Y"], "낡은 10Y 가 섰다"
        assert why and "10Y" in why and "40분" in why, f"사유가 없다: {why}"
        # 산 쪽은 **가격에서 푼 금리**다 — 벤더의 `implied_yield` 는 0.0 으로 온다.
        assert lv[0]["level"] == pytest.approx(implied_yield(102.03, 3), abs=1e-4)
        assert meta["asof"] == "2026-09-28 13:39:00"
        # 아예 한 줄만 오면 없는 쪽도 사유를 얻는다.
        lv1, why1, _m = pl.fut_levels([rows[0]], now)
        assert [x["tenor"] for x in lv1] == ["3Y"] and "10Y" in (why1 or "")
        # 둘 다 어제면 둘 다 사유를 얻고 레벨은 빈다.
        old = [(c, p, _d.date(2026, 9, 25), t) for c, p, _d_, t in rows]
        lv0, why0, _m0 = pl.fut_levels(old, now)
        assert lv0 == [] and "3Y" in why0 and "10Y" in why0

    def test_IRS_줄의_문을_SQL_없이_잰다(self):
        """30분 문·오늘 문·빈 표 — 종전에는 이 셋이 `with engine().connect()` 안에
        있어서 SQL 없이는 한 줄도 잴 수 없었다(적대 검증 2026-09-28 — 「시험이 하나도
        없다」).
        """
        import datetime as _d

        from app import paperlive as pl

        now = _d.datetime(2026, 9, 28, 13, 40, 0)
        fresh = {"irs_date": _d.date(2026, 9, 28),
                 "irs_time": _d.timedelta(hours=13, minutes=38),
                 "irs_5y": 4.2675, "irs_10y": 4.335}
        lv, why, meta = pl.irs_levels(fresh, now)
        assert why is None and meta["ageMin"] == pytest.approx(2.0)
        assert {(x["tenor"], x["level"]) for x in lv} == {("5Y", 4.2675), ("10Y", 4.335)}
        assert all(x["at"] == "13:38:00" and x["kind"] == "irs" for x in lv)
        # ★30분 문 — 넘으면 레벨이 **하나도** 안 선다(반쪽 시계를 안 만든다).
        stale = {**fresh, "irs_time": _d.timedelta(hours=12, minutes=0)}
        lv, why, _m = pl.irs_levels(stale, now)
        assert lv == [] and "분 전" in why
        # 오늘이 아니면 마찬가지다 — 어제 종가를 「지금」이라 안 부른다.
        old = {**fresh, "irs_date": _d.date(2026, 9, 25)}
        lv, why, _m = pl.irs_levels(old, now)
        assert lv == [] and "오늘 자료가 아니" in why
        # 빈 표.
        assert pl.irs_levels(None, now) == ([], "표가 비어 있어요", {})
        # 안 적힌 칸은 건너뛴다 — 「안 적었다」는 0 이 아니다.
        assert pl.irs_levels({**fresh, "irs_5y": None}, now)[0] == [
            {"kind": "irs", "tenor": "10Y", "level": 4.335, "at": "13:38:00", "source": "IRS"}]

    def test_반쪽_장중은_반쪽이라고_말한다(self):
        """★[적대 검증 2026-09-28]. 장중이 다리를 **반만** 덮으면 돈 칸은 두 시계를
        섞은 수인데, 화면은 계열 시선의 `live`(계열이 전부 덮였을 때만 참)를 읽어
        **「종가」라고 적었다**. 실측으로 5Y 한 칸만 쳐도 포지션 합계가
        −55,000,000 → −215,000,000 으로 움직이는데 그걸 종가라 부르고 있었다.

        고른 길은 「반쪽이면 묶음째 종가로 되돌리기」가 아니다 — BSS 는 IRS + 국고
        현물이고 국고 장중은 이 창구에 아직 없어서, 그러면 이 데스크가 제일 많이 하는
        거래가 장중을 켜도 영원히 안 움직인다. 거짓은 수가 아니라 **이름표**였다.
        """
        leg_of, _d, _v = _leg_of(120)
        st = dict(paper.EMPTY, legs=[])
        paper.add_leg(st, kind="irs", tenor="5Y", side="pay", entry="2020-03-02",
                      level=3.0, notional=1e10, dv01=1_900_000.0, tag="BSS")
        paper.add_leg(st, kind="bond", tenor="5Y", side="buy", entry="2020-03-02",
                      level=3.1, notional=1e10, dv01=1_900_000.0, tag="BSS")

        def sheet(marks):
            return paper.build_sheet(leg_of=leg_of, store=st,
                                     mark_of=lambda k, t: ("2020-03-03", 3.05),
                                     marks=marks)["position"]["groups"][0]

        close = sheet(None)
        assert close["clock"] == "close" and close["staleLegs"] == [1, 2]
        # 한 다리만 덮으면 **mixed** 이고, 아직 종가인 다리가 누구인지 말한다.
        half = sheet({("irs", "5Y"): 3.40})
        assert half["clock"] == "mixed", "반쪽인데 mixed 가 아니다"
        assert half["staleLegs"] == [2], half["staleLegs"]
        assert half["pnl"] != close["pnl"], "돈이 안 움직였다 — 픽스처가 약하다"
        # 계열 시선은 그대로 all-or-nothing 이다(반쪽 스프레드는 계열 값이 아니다).
        assert half["live"] is False
        # 둘 다 덮이면 live — 그때는 계열 시선과 돈이 같은 말을 한다.
        full = sheet({("irs", "5Y"): 3.40, ("bond", "5Y"): 3.20})
        assert full["clock"] == "live" and full["staleLegs"] is None
        # 닫힌 다리는 시계를 안 흐린다 — 열린 다리만 센다(마크가 없는 다리다).
        paper.close_leg(st, 1, exit_t="2020-03-04", exit_level=3.2)
        only_open = sheet({("bond", "5Y"): 3.20})
        assert only_open["clock"] == "live", only_open

    def test_추적_창이_두_시계를_나란히_말한다(self, monkeypatch, tmp_path):
        """★[적대 검증 2026-09-28]. 대사 표는 **늘 종가**다(엔진이 종가로 돈다).
        머리띠의 계열 값·경로는 `marks` 를 받으면 장중이다. 종전에는 둘이 한 창에
        나란히 서면서 아무 말도 안 해서, 같은 트레이드가 표에서는 −4,500만원이고
        머리띠에서는 +1,750만원이었다.

        「표도 장중으로」는 답이 아니다 — 장중으로 매긴 장부 손익을 종가까지 돈
        엔진과 빼면 「차이」 열이 선형 대 재평가의 몫이 아니라 두 시계의 차가 된다.
        그래서 둘을 다 싣고 **이름을 붙인다**.
        """
        from fastapi.testclient import TestClient

        from app import main as M, paperlive

        monkeypatch.setattr(paperlive, "live_marks", lambda: {"levels": [
            {"kind": "irs", "tenor": "5Y", "level": 4.27, "at": "13:30", "source": "IRS"},
        ], "asof": "13:30", "sources": [], "why": None})
        c = TestClient(M.app)
        st = paper.load()
        ns = [int(lg["n"]) for lg in st.get("legs", [])][:2]
        if not ns:
            pytest.skip("장부에 다리가 없어요 — 이 시험은 실장부를 읽습니다")
        arg = ",".join(str(n) for n in ns)
        for marks, head in (("", "close"), ("live", "live")):
            r = c.get("/api/paper/trace", params={"legs": arg, "marks": marks})
            assert r.status_code == 200, r.text
            b = r.json()["basis"]
            assert b["table"] == "close", "대사 표가 종가가 아니라고 적혔다"
            assert b["head"] == head, (marks, b)
            if head == "live":
                assert b["why"] and "종가 기준" in b["why"]
                assert b["marks"], "무엇을 깔았는지 안 싣는다"
            else:
                assert b["why"] is None and b["marks"] is None

    def test_라우트가_장중_레벨을_받는다(self, monkeypatch, tmp_path):
        from fastapi.testclient import TestClient

        from app import main as M

        monkeypatch.setattr(paper, "STORE", tmp_path / "book.json")
        c = TestClient(M.app)
        r = c.get("/api/paper", params={"marks": "irs:5Y=xx"})
        assert r.status_code == 422 and "숫자가 아니" in r.json()["detail"]
        ok = c.get("/api/paper", params={"marks": ""})
        assert ok.status_code == 200 and ok.json()["live"] is None

    def test_시트가_묶음과_전체_명목을_싣는다(self):
        leg_of, _d, _v = _leg_of(120)
        st = dict(paper.EMPTY, legs=[])
        paper.add_leg(st, kind="irs", tenor="2Y", side="pay", entry="2020-03-02",
                      level=3.0, notional=1e10, dv01=1_900_000.0, tag="BSS 2Y")
        paper.add_leg(st, kind="fut", tenor="3Y", side="buy", entry="2020-03-02",
                      level=3.1, notional=2e10, dv01=1_900_000.0, tag="BSS 2Y")
        sheet = paper.build_sheet(leg_of=leg_of, store=st,
                                  mark_of=lambda k, t: ("2020-03-03", 3.05))
        pos = sheet["position"]
        assert pos["openNotional"] == pytest.approx(3e10)
        assert len(pos["groups"]) == 1 and pos["groups"][0]["legs"] == [1, 2]
        assert pos["groups"][0]["pnl"] == pos["pnl"]
        assert pos["trades"] == 1 and pos["tradesOpen"] == 1


class Test발생액접기:
    """★[OWNER 2026-10-01] 「캐리랑 롤다운은 전일 종가로 하고, 평가만 시가로」

    왜 이 묶음이 있는가: 카드(`score_leg`)는 **평가 − 비용**만 세고 추적
    (`/api/paper/trace`)은 체결차이+캐리+롤다운+개시+조달까지 셌다. 같은 다리를 두고
    **한 화면이 두 수를 말했고**, 산 장부 실측(자료일 2026-09-30 · 09-22 진입)에서
    합계의 **부호가 뒤집혔다**: 카드 −500만 ↔ 추적 +781만. 빠진 돈의 대부분이
    캐리(+534만)와 롤다운(+197만)이었다.

    엔진은 그 격차를 이미 계산해 `residual`(차이)이라 적고 있었다 — 즉 **시스템이
    알면서 카드에만 안 넣고 있었다.** 그걸 말로 두지 않고 여기 박는다.
    """

    @staticmethod
    def _leg(n=1, **over):
        o = {"n": n, "kind": "irs", "tenor": "5Y", "side": "pay", "rateSign": 1,
             "entry": "2026-09-22", "level": 4.0, "notional": 1e10,
             "dv01": 10_000_000.0, "exit": None, "exitLevel": None}
        o.update(over)
        return o

    @staticmethod
    def _acc(**over):
        a = {"exec": 1_000_000.0, "carry": 2_000_000.0, "rolldown": 500_000.0,
             "startup": 100_000.0, "funding": None, "valuation": 7_000_000.0}
        a.update(over)
        return a

    def test_평가만의_수를_mtm_으로_남긴다(self):
        """`pnl` 의 뜻이 바뀌었으니 옛 수가 사라지면 안 된다 — 장중 시선이 그것을 쓴다."""
        row = paper.score_leg(self._leg(), 4.1, mark_t="2026-09-30")
        assert row["mtm"] == row["gross"] - row["cost"]
        assert row["pnl"] == row["mtm"]        # 접기 전에는 같다

    def test_발생액을_접으면_손익이_그_합이다(self):
        row = paper.score_leg(self._leg(), 4.1, mark_t="2026-09-30")
        got = paper.fold_accrual(row, self._acc())
        assert got["accrued"] is True
        # 체결차이 + 캐리 + 롤다운 + 개시 + 엔진평가 − 비용
        want = 1e6 + 2e6 + 5e5 + 1e5 + 7e6 - row["cost"]
        assert got["pnl"] == pytest.approx(round(want, 2))

    def test_발생액이_없으면_접지_않고_그_사실을_싣는다(self):
        """★0 으로 적으면 「캐리가 0 원이었다」는 **딴 사실**이 되고 화면의 «—» 가
        사라진다. 2026-10-01 에 `json` 임포트 하나가 빠져 엔진이 조용히 죽었는데,
        이 규약 덕에 `accrued=False` 로 **드러났다**(0 이었으면 못 봤다)."""
        row = paper.score_leg(self._leg(), 4.1, mark_t="2026-09-30")
        got = paper.fold_accrual(row, None)
        assert got["accrued"] is False and got["accrual"] is None
        assert got["pnl"] == row["mtm"]        # 평가만의 수로 남는다

    def test_반쪽_발생액은_접지_않는다(self):
        """캐리는 왔는데 평가가 없으면 「장부 손익」이 무엇의 합인지 말할 수 없다."""
        row = paper.score_leg(self._leg(), 4.1, mark_t="2026-09-30")
        assert paper.fold_accrual(row, self._acc(valuation=None))["accrued"] is False
        assert paper.fold_accrual(row, self._acc(carry=None))["accrued"] is False

    def test_조달이_없는_것은_반쪽이_아니다(self):
        """IRS 만 있는 북에서 조달은 `None` 이다 — 없는 항이고 못 잰 항이 아니다.
        합에서 0 으로 **세지 않고** 그 칸만 비운다(공란 정책)."""
        row = paper.score_leg(self._leg(), 4.1, mark_t="2026-09-30")
        got = paper.fold_accrual(row, self._acc(funding=None))
        assert got["accrued"] is True and got["accrual"]["funding"] is None

    def test_마크에_걸리는_항은_평가뿐이다(self):
        """★[OWNER] 의 그 식. 캐리·롤다운·개시·체결차이는 **시간과 진입**이 정하므로
        지금 레벨과 무관하다 — 장중 시선에서 움직이는 것은 평가 하나다."""
        base = paper.score_leg(self._leg(), 4.1, mark_t="2026-09-30")
        base["live"], base["closeMark"] = True, 4.1
        same = paper.fold_accrual(base, self._acc(), close_mark=4.1)
        assert same["liveMove"] == 0.0
        moved = dict(base)
        moved["mark"] = 4.11                       # 장중에 1bp 움직였다
        got = paper.fold_accrual(moved, self._acc(), close_mark=4.1)
        # 1bp × DV01 1,000만원 × rateSign +1 = +1,000만원
        assert got["liveMove"] == pytest.approx(10_000_000.0)
        assert got["pnl"] - same["pnl"] == pytest.approx(10_000_000.0)
        # 발생액은 **안 움직인다**
        assert got["accrual"] == same["accrual"]

    def test_종가_시선에서는_이동이_없다(self):
        row = paper.score_leg(self._leg(), 4.1, mark_t="2026-09-30")
        row["live"] = False
        got = paper.fold_accrual(row, self._acc(), close_mark=4.0)
        assert got["liveMove"] is None

    def test_엔진이_죽어도_카드가_선다(self):
        """`accrual_of` 가 터지면 사유가 `failed` 에 남고 카드는 평가만의 수로 선다."""
        leg_of, _d, _v = _leg_of(120)
        st = dict(paper.EMPTY, legs=[])
        paper.add_leg(st, kind="irs", tenor="2Y", side="pay", entry="2020-03-02",
                      level=3.0, notional=1e10, dv01=1_900_000.0)

        def boom(_rows):
            raise RuntimeError("엔진이 죽었어요")

        sheet = paper.build_sheet(leg_of=leg_of, store=st,
                                  mark_of=lambda k, t: ("2020-03-03", 3.05),
                                  accrual_of=boom)
        assert any(f["id"] == "position/accrual" for f in sheet["failed"])
        assert sheet["position"]["legs"][0]["accrued"] is False

    def test_합계가_접힌_수의_합이다(self):
        """★«대조» — 묶음 소계와 전체 합이 **접힌 뒤의** 수를 센다. 접기를 합계보다
        늦게 하면 카드 머리와 줄이 다른 수를 말한다."""
        leg_of, _d, _v = _leg_of(120)
        st = dict(paper.EMPTY, legs=[])
        paper.add_leg(st, kind="irs", tenor="2Y", side="pay", entry="2020-03-02",
                      level=3.0, notional=1e10, dv01=1_900_000.0, tag="T")
        acc = {1: {"exec": 1e6, "carry": 2e6, "rolldown": 5e5, "startup": 1e5,
                   "funding": None, "valuation": 7e6}}
        sheet = paper.build_sheet(leg_of=leg_of, store=st,
                                 mark_of=lambda k, t: ("2020-03-03", 3.05),
                                 accrual_of=lambda rows: acc)
        pos = sheet["position"]
        leg = pos["legs"][0]
        assert leg["accrued"] is True
        assert pos["pnl"] == pytest.approx(leg["pnl"])
        assert pos["groups"][0]["pnl"] == pytest.approx(leg["pnl"])
        assert leg["pnl"] != leg["mtm"]        # 접혔다는 것이 수에 드러난다

    def test_묶음마다_분해가_있고_합이_전체와_닫힌다(self):
        """★[OWNER 2026-10-01 — 「합계랑 분해랑 각각을 트레이드별로」].

        묶음의 분해는 전체(`position.split`)와 **같은 함수**(`position_split`)가
        센다. 두 벌의 산술로 갈리면 화면이 트레이드를 펼칠 때와 접을 때 다른 수를
        말한다 — 그래서 여기서 재는 것은 「칸이 있다」가 아니라 **1원까지 닫힌다**다.
        """
        leg_of, _d, _v = _leg_of(120)
        st = dict(paper.EMPTY, legs=[])
        paper.add_leg(st, kind="irs", tenor="2Y", side="pay", entry="2020-03-02",
                      level=3.0, notional=1e10, dv01=1_900_000.0, tag="1st")
        paper.add_leg(st, kind="irs", tenor="5Y", side="receive", entry="2020-03-02",
                      level=3.5, notional=1e10, dv01=4_300_000.0, tag="2nd")
        acc = {1: {"exec": 1e6, "carry": 2e6, "rolldown": 5e5, "startup": 1e5,
                   "funding": None, "valuation": 7e6},
               2: {"exec": -3e5, "carry": 4e6, "rolldown": -2e5, "startup": 5e4,
                   "funding": None, "valuation": -1.5e6}}
        sheet = paper.build_sheet(leg_of=leg_of, store=st,
                                 mark_of=lambda k, t: ("2020-03-03", 3.05),
                                 accrual_of=lambda rows: acc)
        pos = sheet["position"]
        groups = pos["groups"]
        assert [g["label"] for g in groups] == ["1st", "2nd"]
        whole = pos["split"]
        for g in groups:
            assert g["split"], "묶음마다 분해가 있다"
            assert g["split"]["legs"] == 1 and g["split"]["folded"] == 1
        # ★성분도 합계도 1원까지 닫힌다 — 반올림 두 번이 끼어들 자리가 없다.
        for k in (*paper.ACCRUAL_KEYS, "valuation", "engineValuation", "cost",
                  "total", "foldedTotal"):
            parts = [g["split"][k] for g in groups]
            if whole[k] is None:
                assert all(v is None for v in parts), k
                continue
            assert sum(parts) == pytest.approx(whole[k], abs=1.0), k
        assert whole["legs"] == 2 and whole["folded"] == 2
        # 기여의 합 = 카드 머리의 합계. 화면이 퍼센트를 여기서 센다.
        assert (groups[0]["split"]["foldedTotal"] + groups[1]["split"]["foldedTotal"]
                == pytest.approx(pos["pnl"], abs=1.0))

    def test_못_접은_다리가_있는_묶음은_합계를_비운다(self):
        """★분해가 합계를 설명하는 것처럼 보이면 안 된다 — 그 묶음의 `total` 은
        `None` 이고 `foldedTotal`/`folded` 로 말한다(전체와 같은 규율)."""
        leg_of, _d, _v = _leg_of(120)
        st = dict(paper.EMPTY, legs=[])
        paper.add_leg(st, kind="irs", tenor="2Y", side="pay", entry="2020-03-02",
                      level=3.0, notional=1e10, dv01=1_900_000.0, tag="T")
        paper.add_leg(st, kind="irs", tenor="5Y", side="receive", entry="2020-03-02",
                      level=3.5, notional=1e10, dv01=4_300_000.0, tag="T")
        acc = {1: {"exec": 1e6, "carry": 2e6, "rolldown": 5e5, "startup": 1e5,
                   "funding": None, "valuation": 7e6}}       # 2번은 엔진이 못 셌다
        sheet = paper.build_sheet(leg_of=leg_of, store=st,
                                 mark_of=lambda k, t: ("2020-03-03", 3.05),
                                 accrual_of=lambda rows: acc)
        sp = sheet["position"]["groups"][0]["split"]
        assert sp["total"] is None, "하나라도 안 접혔으면 합계는 비운다"
        assert sp["folded"] == 1 and sp["legs"] == 2
        assert sp["foldedTotal"] is not None


class Test카드와추적이같은수를말한다:
    """★★«대조 문» — 이 묶음이 없어서 결함이 한 달 가까이 살았다.

    카드(`position.legs[*].pnl`)와 추적(`/api/paper/trace` 의 `exec + engine − cost`)이
    같은 다리에 다른 수를 말하고 있었고, 엔진은 그 격차를 `residual` 로 **적고 있었는데도**
    아무것도 빨개지지 않았다. 둘이 같은 함수(`_position_engine_book`)를 쓰는 것과
    `residual` 이 0 으로 닫히는 것을 여기서 묶는다.

    ⚠산 백엔드를 안 쓴다 — 엔진 줄을 손으로 주입해 **대조의 산술만** 잰다.
      산 엔진까지 태우는 것은 `/api/paper/trace` 라우트 시험이 진다.
    """

    @staticmethod
    def _engine_row(**over):
        r = {"id": "5Y", "label": "5Y", "entry": "2020-03-02", "exit": None,
             # ★열쇠는 `entryValue` 다(`entry_close_of`) — 스왑·선물의 호가값.
             # 처음 `entryClose` 로 적었더니 체결차이가 `None` 이 되어 대조가 통째로
             # `None` 이었다. **`None` 은 0 이 아니고, 0 으로 닫힌 것도 아니다.**
             "entryValue": 3.02, "valuation": 7_000_000.0, "carry": 2_000_000.0,
             "rolldown": 500_000.0, "startup": 100_000.0, "funding": None,
             "pnl": 9_600_000.0}
        r.update(over)
        return r

    def test_차이가_0_으로_닫힌다(self):
        """`reconcile_leg` 의 `residual` 은 「장부 손익 − (체결차이 + 엔진 − 비용)」이다.
        카드가 발생액을 접으면 그 수가 **0** 이어야 한다 — 0 이 아니면 둘이 다른 것을
        세고 있다는 뜻이고, 2026-10-01 까지 그 값이 −1,017만원이었다."""
        leg = Test발생액접기._leg(level=3.0, dv01=10_000_000.0, rateSign=1)
        row = self._engine_row()
        # 카드가 보는 발생액 — `main._position_accrual` 과 같은 길(같은 `reconcile_leg`)
        rec = paper.reconcile_leg(leg, row, paper_pnl=None, cost=None)
        acc = {k: rec[k] for k in paper.ACCRUAL_KEYS}
        acc["valuation"] = rec["valuation"]
        scored = paper.score_leg(leg, 3.05, mark_t="2026-09-30")
        card = paper.fold_accrual(scored, acc)
        # 그 수로 다시 대조하면 차이가 사라진다
        again = paper.reconcile_leg(leg, row, paper_pnl=card["pnl"], cost=card["cost"])
        assert again["residual"] == pytest.approx(0.0, abs=1.0)

    def test_접기_전에는_차이가_남는다(self):
        """★이 시험이 위의 0 을 **뜻있게** 만든다 — 접지 않으면 차이가 선다."""
        leg = Test발생액접기._leg(level=3.0, dv01=10_000_000.0, rateSign=1)
        row = self._engine_row()
        scored = paper.score_leg(leg, 3.05, mark_t="2026-09-30")
        plain = paper.fold_accrual(scored, None)          # 종전 동작
        rec = paper.reconcile_leg(leg, row, paper_pnl=plain["pnl"], cost=plain["cost"])
        assert rec["residual"] is not None and abs(rec["residual"]) > 1.0

    def test_엔진을_부르는_자리가_하나다(self):
        """★카드와 추적이 각자 엔진을 부르면 또 갈린다. 부르는 곳이 하나임을 박는다
        (끊는 날·조달·엔진이 그 함수 안에 한 벌로 있다)."""
        import inspect

        from app import main as M

        src = inspect.getsource(M)
        assert "def _position_engine_book(" in src
        # `_book_result` 를 포지션 쪽에서 직접 부르는 자리가 그 함수 말고 없어야 한다
        pos = src.index("def _position_engine_book(")
        after = src[pos:]
        body = after[: after.index("\ndef _position_accrual(")]
        assert "_book_result(" in body
        assert src.count("_position_engine_book(") >= 3   # 정의 1 + 부르는 곳 2
