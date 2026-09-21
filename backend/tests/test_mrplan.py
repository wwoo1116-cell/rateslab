# -*- coding: utf-8 -*-
"""MR **계획면** — 「지금 어디에 있고, 얼마면 무엇을 하나」의 산술을 핀으로 박는다.

`mrplan` 은 규칙을 안 만든다. 규칙은 엔진(`mrbacktest`)과 보드(`mr`)의 것이고 이
모듈은 **번역**이다 — 그래서 이 파일이 재는 것도 그 번역이 원본과 갈리지 않는가다:

  · 격자 1등 고르기가 화면(`rankCells`)과 같은 규약인가 — 못 잰 칸은 후보가 아니다
  · 레벨 셋이 엔진의 세 문(|z| ≥ entryZ · |z| ≤ exitZ · |z| ≥ stopZ)과 **같은 자리**인가
  · %-계열에서 레벨은 자기 단위, 거리는 bp 인가 (100배 함정)
  · 행이 보드 행과 **같은 열쇠**를 갖는가 (통합 줄·화면 부품이 그것을 읽는다)
  · 1년 카드의 분해 다섯이 그 구간 순손익으로 닫히는가
  · 부분 결과를 «조용히» 내지 않는가 — 못 구운 것은 세어서 말한다

SQL 을 안 만진다 — 합성 계열에 실제 엔진을 걸어 재료를 만들고, 격자·다리는
주입한다(`leg_of`·`grid_of`). 그 주입 자리가 이 모듈이 DB 를 모르게 하는 이유다.
"""
import datetime as dt
import json
import math

import pytest

from app import cache as cache_mod
from app import mr as mr_mod
from app import mrbacktest as bt
from app import mrmetrics as mrm
from app import mrplan as mrp


# ── 픽스처 — `test_mrbook.py` 의 그 계열·그 달력 ─────────────────────────────
def _ou(n: int, *, seed: int, phi: float = 0.92, sd: float = 1.4,
        mu: float = 30.0) -> list[float]:
    """평균회귀 계열(AR(1)) — LCG + Box-Muller. 씨앗이 곧 계열이다."""
    s = seed
    v = mu
    out = []
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


def _dates(n: int) -> list[str]:
    return [(_D0 + dt.timedelta(days=i)).isoformat() for i in range(n)]


def _leg_of(sid: str, label: str, kind: str, unit: str, vals_u: list[float]):
    """주입할 `leg_of` — `main._mr_leg` 가 내는 재료의 모양 그대로.

    ⚠ `vals` 는 **엔진 눈금**이다: %-계열은 ×100 한 bp. `disp` 가 되돌린다.
    그 비대칭이 `mrplan` 이 지켜야 하는 계약이고, 이 파일이 그것을 잰다.
    """
    scale = 100.0 if unit == "%" else 1.0
    vals = [v * scale for v in vals_u]
    dates = _dates(len(vals))
    calls: list[dict] = []

    def leg_of(sid_: str, knobs: dict, *, accounting: bool = True) -> dict:
        calls.append({"id": sid_, "knobs": dict(knobs), "accounting": accounting})
        r = bt.simulate(dates, vals, lookback=int(knobs["lookback"]),
                        entry_z=float(knobs["entryZ"]), exit_z=float(knobs["exitZ"]),
                        stop_z=float(knobs["stopZ"]), cost_bp=mrp.COST_BP,
                        notional=mrp.NOTIONAL,
                        allow_dirs=tuple(mr_mod.TRADABLE_DIRS[kind]),
                        entry_mode=str(knobs["entryMode"]))
        return {
            "id": sid_, "label": label, "kind": kind, "unit": unit,
            # 회계를 안 돌린 판은 `real=False` 다 — 라우트의 그 규약.
            "real": bool(accounting),
            "dates": dates, "vals": vals,
            "disp": (lambda v: round(v / scale, 4)),
            "dirs": mr_mod.dirs_for(kind),
            "carryKrw": None, "carryDefn": None, "carryLegs": [],
            "gate": None, "costSeries": None, "r": r,
            "tradable": None, "pts": [{"t": t} for t in dates],
        }

    return leg_of, calls, dates, vals


def _grid_of(cells: list[dict]):
    """주입할 `grid_of` — 칸 목록을 그대로 돌려준다(격자 산술은 `_mr_optimize` 것)."""
    seen: list[dict] = []

    def grid_of(leg: dict, knobs: dict, *, span: str) -> dict:
        seen.append({"span": span, "knobs": dict(knobs), "legReal": leg["real"]})
        return {"span": span, "cells": cells}

    return grid_of, seen


def _cell(**kw) -> dict:
    base = {"lookback": 60, "entryZ": 2.0, "exitZ": 0.5, "stopZ": 2.5,
            "entryMode": "level", "cdarRatio": None}
    base.update(kw)
    return base


# ── ① 격자 1등 고르기 ────────────────────────────────────────────────────────
class TestPickCell:
    def test_못_잰_칸은_후보가_아니다(self):
        """`None` 은 「그 구간에서 안 선다」이지 「0 이다」가 아니다 — 0 으로 채워
        정렬하면 못 잰 칸이 한복판에 끼어든다(화면 `rankCells` 와 같은 규약)."""
        cells = [_cell(cdarRatio=None, entryZ=1.5), _cell(cdarRatio=-0.4, entryZ=2.0),
                 _cell(cdarRatio=None, entryZ=2.5)]
        assert mrp.pick_cell(cells)["entryZ"] == 2.0

    def test_클수록_이긴다(self):
        cells = [_cell(cdarRatio=0.2, entryZ=1.5), _cell(cdarRatio=1.7, entryZ=2.0),
                 _cell(cdarRatio=0.9, entryZ=2.5)]
        assert mrp.pick_cell(cells)["entryZ"] == 2.0

    def test_동점은_격자_차례가_이긴다(self):
        """같은 자료에서 두 번 부르면 같은 칸이 나와야 한다 — 엄격한 `>` 비교."""
        cells = [_cell(cdarRatio=1.0, stopZ=2.5), _cell(cdarRatio=1.0, stopZ=3.0)]
        assert mrp.pick_cell(cells)["stopZ"] == 2.5

    def test_후보가_없으면_None(self):
        assert mrp.pick_cell([_cell(), _cell()]) is None
        assert mrp.pick_cell([]) is None

    def test_기준을_바꿔_고를_수_있다(self):
        cells = [_cell(cdarRatio=2.0, calmar=0.1, entryZ=1.5),
                 _cell(cdarRatio=0.1, calmar=2.0, entryZ=2.5)]
        assert mrp.pick_cell(cells, "calmar")["entryZ"] == 2.5

    def test_룩백은_정수다(self):
        """엔진이 색인으로 쓴다 — 실수로 넘어가면 `range` 에서 터진다."""
        k = mrp.knobs_of(_cell(lookback=120.0, cdarRatio=1.0))
        assert k["lookback"] == 120 and isinstance(k["lookback"], int)
        assert set(k) == set(mrp.KNOB_KEYS)


# ── ② 레벨 셋 — 엔진의 세 문과 같은 자리인가 ──────────────────────────────────
class TestLevels:
    def test_레벨이_z_문턱을_되짚는다(self):
        """(레벨 − 중심선)/σ 가 그 문턱의 배수여야 한다 — 이게 번역의 항등이다."""
        lv = mrp.levels_for("fut", ma=100.0, sd=4.0, v=100.0,
                            entry_z=2.0, exit_z=0.5, stop_z=2.5, scale=1.0)
        by = {x["dir"]: x for x in lv}
        assert (by[-1]["entry"] - 100.0) / 4.0 == pytest.approx(2.0)
        assert (by[-1]["exit"] - 100.0) / 4.0 == pytest.approx(0.5)
        assert (by[-1]["stop"] - 100.0) / 4.0 == pytest.approx(2.5)
        # +1 은 거울이다.
        assert (100.0 - by[1]["entry"]) / 4.0 == pytest.approx(2.0)
        assert (100.0 - by[1]["exit"]) / 4.0 == pytest.approx(0.5)
        assert (100.0 - by[1]["stop"]) / 4.0 == pytest.approx(2.5)

    def test_진입까지_남은_거리(self):
        """양수면 아직, 음수면 지났다. 방향마다 «가야 하는 쪽» 이 다르다."""
        lv = {x["dir"]: x for x in mrp.levels_for(
            "fut", ma=100.0, sd=4.0, v=101.0, entry_z=2.0, exit_z=0.5,
            stop_z=2.5, scale=1.0)}
        # dir −1: 진입 108 까지 7 더 올라야 한다. dir +1: 진입 92 까지 9 내려가야.
        assert lv[-1]["entryGap"] == pytest.approx(7.0)
        assert lv[1]["entryGap"] == pytest.approx(9.0)
        assert lv[-1]["entryReached"] is False
        # 청산·손절 «거리» 는 여기 없다 — 들어가기 전에는 뜻이 없는 수다.
        assert "exitGap" not in lv[-1] and "stopGap" not in lv[-1]

    def test_문턱을_지나면_reached(self):
        lv = {x["dir"]: x for x in mrp.levels_for(
            "fut", ma=100.0, sd=4.0, v=109.0, entry_z=2.0, exit_z=0.5,
            stop_z=2.5, scale=1.0)}
        assert lv[-1]["entryReached"] is True
        assert lv[-1]["entryGap"] == pytest.approx(-1.0)

    def test_못_하는_방향은_안_싣는다(self):
        """BSS 의 하단은 국고 매도다 — 이 데스크가 못 하는 거래의 문턱을 권하지 않는다."""
        lv = mrp.levels_for("bss", ma=30.0, sd=2.0, v=30.0, entry_z=2.0,
                            exit_z=0.5, stop_z=2.5, scale=1.0)
        assert [x["dir"] for x in lv] == [-1]
        assert lv[0]["legs"] == mr_mod.DIR_LEGS["bss"]["minus"]["legs"]

    def test_퍼센트_계열은_레벨은_자기_단위_거리는_bp(self):
        """100배 함정 — 선물 계열에서만 거리가 100배 작아지던 그 자리."""
        lv = {x["dir"]: x for x in mrp.levels_for(
            "fut", ma=3.0, sd=0.04, v=3.01, entry_z=2.0, exit_z=0.5,
            stop_z=2.5, scale=100.0)}
        assert lv[-1]["entry"] == pytest.approx(3.08)      # % 그대로
        assert lv[-1]["entryGap"] == pytest.approx(7.0)    # bp

    def test_밴드가_못_서면_빈_목록(self):
        assert mrp.levels_for("bss", ma=None, sd=None, v=1.0, entry_z=2.0,
                              exit_z=0.5, stop_z=2.5, scale=1.0) == []
        assert mrp.levels_for("bss", ma=30.0, sd=0.0, v=30.0, entry_z=2.0,
                              exit_z=0.5, stop_z=2.5, scale=1.0) == []


class TestExitsNow:
    """나가는 문 둘은 **방향을 안 본다** — `|z|` 위의 규칙이라 지금 값의 쪽이 정한다."""

    def test_위쪽이면_위쪽_가장자리가_먼저_닿는다(self):
        now = mrp.exits_now(ma=100.0, sd=4.0, v=106.0, exit_z=0.5, stop_z=2.5,
                            scale=1.0)
        assert now["side"] == "above" and now["z"] == pytest.approx(1.5)
        assert now["exit"] == pytest.approx(102.0)   # 중심선 + 0.5σ
        assert now["stop"] == pytest.approx(110.0)   # 중심선 + 2.5σ
        # 4bp 좁혀지면 청산, 4bp 더 벌어지면 손절.
        assert now["exitGap"] == pytest.approx(4.0)
        assert now["stopGap"] == pytest.approx(4.0)

    def test_아래쪽이면_거울이다(self):
        now = mrp.exits_now(ma=100.0, sd=4.0, v=94.0, exit_z=0.5, stop_z=2.5,
                            scale=1.0)
        assert now["side"] == "below"
        assert now["exit"] == pytest.approx(98.0) and now["stop"] == pytest.approx(90.0)
        assert now["exitGap"] == pytest.approx(4.0) and now["stopGap"] == pytest.approx(4.0)

    def test_중심선을_넘어가면_문도_같이_넘어간다(self):
        """실측에서 잡은 자리 — 아래에서 진입한 다리가 지금 위쪽에 서 있으면
        청산선은 **위쪽** 가장자리다. 진입 쪽으로 적으면 이미 지난 수가 된다."""
        now = mrp.exits_now(ma=100.0, sd=4.0, v=101.0, exit_z=0.0, stop_z=2.5,
                            scale=1.0)
        assert now["side"] == "above"
        assert now["exit"] == pytest.approx(100.0)      # exitZ=0 이면 중심선 자체
        assert now["exitGap"] == pytest.approx(1.0)     # 양수 — 아직 안 닿았다
        assert now["stopGap"] == pytest.approx(9.0)

    def test_퍼센트_계열은_거리가_bp(self):
        now = mrp.exits_now(ma=3.0, sd=0.04, v=3.06, exit_z=0.5, stop_z=2.5,
                            scale=100.0)
        assert now["exit"] == pytest.approx(3.02)
        assert now["exitGap"] == pytest.approx(4.0)

    def test_밴드가_못_서면_None(self):
        assert mrp.exits_now(ma=None, sd=None, v=1.0, exit_z=0.5, stop_z=2.5,
                             scale=1.0) is None
        assert mrp.exits_now(ma=3.0, sd=0.0, v=3.0, exit_z=0.5, stop_z=2.5,
                             scale=1.0) is None


class TestPositionUnit:
    """들고 있는 다리 한 줄 — 실측에서 잡은 자리를 그대로 핀으로 박는다."""

    def _op(self, **kw):
        base = {"direction": 1, "entryDate": "2026-08-28", "entryValue": 90.0,
                "entryZ": -2.53, "bars": 15, "pnl": 3.5, "mtm": 4.0,
                "carry": 0.0, "cost": -0.5}
        base.update(kw)
        return base

    def test_중심선을_넘어가_있으면_crossed_이고_문도_같이_넘어간다(self):
        """2026-09-21 라이브 실측 — FUT-KTB3 이 아래(−2.53σ)에서 들어갔는데 지금은
        위쪽 +1.0σ 에 서 있었다. 진입 쪽으로 청산선을 적으면 「이미 지난 선」이
        청산선으로 화면에 선다."""
        now = mrp.exits_now(ma=100.0, sd=4.0, v=104.0, exit_z=0.5, stop_z=3.0,
                            scale=1.0)
        pos = mrp.position_of(self._op(), kind="fut", now=now,
                              disp=lambda v: round(v, 4))
        assert pos["crossed"] is True
        assert pos["exit"] == pytest.approx(102.0)      # 위쪽 가장자리
        assert pos["stop"] == pytest.approx(112.0)
        assert pos["exitGap"] > 0 and pos["stopGap"] > 0

    def test_같은_쪽이면_crossed_아니다(self):
        now = mrp.exits_now(ma=100.0, sd=4.0, v=94.0, exit_z=0.5, stop_z=3.0,
                            scale=1.0)
        pos = mrp.position_of(self._op(), kind="fut", now=now,
                              disp=lambda v: round(v, 4))
        assert pos["crossed"] is False and pos["exit"] == pytest.approx(98.0)

    def test_실가격_판은_성분_다섯을_그대로_진다(self):
        now = mrp.exits_now(ma=100.0, sd=4.0, v=104.0, exit_z=0.5, stop_z=3.0,
                            scale=1.0)
        pos = mrp.position_of(self._op(rolldown=1.25, funding=-2.5), kind="fut",
                              now=now, disp=lambda v: round(v, 4))
        assert pos["rolldown"] == 1.25 and pos["funding"] == -2.5

    def test_밴드가_못_서도_다리는_선다(self):
        """레벨만 null 이고 나머지는 사실이다 — 「없다」와 「못 잰다」는 다른 말."""
        pos = mrp.position_of(self._op(), kind="fut", now=None,
                              disp=lambda v: round(v, 4))
        assert pos["exit"] is None and pos["crossed"] is None
        assert pos["entryT"] == "2026-08-28" and pos["bars"] == 15

    def test_없으면_None(self):
        assert mrp.position_of(None, kind="bss", now=None, disp=float) is None


# ── ③ 계열 하나 ─────────────────────────────────────────────────────────────
class TestBuildSeries:
    def _built(self, unit="bp", cells=None, seed=7, n=900, kind="bss",
               sid="BSS-3Y"):
        vals_u = _ou(n, seed=seed)
        if unit == "%":
            vals_u = [v / 100.0 for v in vals_u]
        leg_of, calls, dates, vals = _leg_of(sid, "BSS 3Y", kind, unit, vals_u)
        grid_of, seen = _grid_of(cells if cells is not None else
                                 [_cell(cdarRatio=0.4, lookback=20, entryZ=2.0),
                                  _cell(cdarRatio=1.9, lookback=60, entryZ=2.5,
                                        exitZ=1.0, stopZ=3.0, entryMode="touch"),
                                  _cell(cdarRatio=None, lookback=120)])
        out = mrp.build_series(sid, leg_of=leg_of, grid_of=grid_of)
        return out, calls, seen, dates, vals

    def test_격자는_회계_없이_실행은_회계로_돈다(self):
        """회계는 격자의 칸을 한 자도 안 바꾸는데 계열 하나가 초 단위다 —
        그래서 격자용 실행만 `accounting=False` 다."""
        out, calls, seen, _d, _v = self._built()
        assert [c["accounting"] for c in calls] == [False, True]
        assert seen[0]["span"] == "all"                 # 조건은 전체 표본에서 고른다
        assert calls[0]["knobs"] == mrp.BASE_KNOBS      # 격자는 기준 노브에서 출발
        # 실행은 **고른 칸**의 노브로 돈다.
        assert calls[1]["knobs"]["entryZ"] == 2.5
        assert calls[1]["knobs"]["entryMode"] == "touch"
        assert out["real"] is True

    def test_조건이_화면에_설_재료를_다_진다(self):
        out, _c, _s, _d, _v = self._built()
        cond = out["cond"]
        assert cond["lookback"] == 60 and cond["entryZ"] == 2.5
        assert cond["basis"] == "cdarRatio" and cond["span"] == "all"
        assert cond["cells"] == 3 and cond["fallback"] is None

    def test_격자가_순위를_못_매기면_기본_조건으로_떨어지고_사유를_적는다(self):
        """「이게 최적이에요」로 읽히면 안 된다 — 공란 정책의 문장 판."""
        out, calls, _s, _d, _v = self._built(cells=[_cell(), _cell(lookback=20)])
        assert calls[1]["knobs"] == mrp.BASE_KNOBS
        assert out["cond"]["fallback"] and "기본 조건" in out["cond"]["fallback"]

    def test_행이_보드_행과_같은_열쇠를_갖는다(self):
        """통합 줄(`mrbook.watch`)과 화면 부품이 이 열쇠들을 읽는다 — 하나라도
        빠지면 그쪽이 조용히 빈다."""
        out, _c, _s, _d, _v = self._built()
        for k in ("id", "label", "kind", "defn", "unit", "v", "d1", "dUnit",
                  "ma", "upper", "lower", "z", "pctB", "width", "asof",
                  "state", "triggers", "triggerBlocked"):
            assert k in out, k
        assert out["defn"] == mr_mod.KIND_DEFN["bss"]

    def test_밴드가_엔진의_것이다(self):
        """z·밴드를 여기서 다시 재지 않는다 — 화면의 진입 문턱과 그 계열의
        백테스트 진입이 같은 자리를 가리켜야 한다."""
        out, calls, _s, dates, vals = self._built()
        knobs = calls[1]["knobs"]
        roll = bt.rolling_series(vals, int(knobs["lookback"]))
        i = len(vals) - 1
        assert out["z"] == pytest.approx(round(roll["z"][i], 2), abs=5e-3)
        assert out["upper"] == pytest.approx(
            roll["mean"][i] + knobs["entryZ"] * roll["std"][i], abs=1e-4)

    def test_퍼센트_계열은_레벨이_자기_단위다(self):
        """엔진은 bp 로 돌고 화면은 % 로 읽는다 — 되돌리는 자리가 여기다."""
        out, _c, _s, _d, vals = self._built(unit="%", kind="fut", sid="FUT-KTB3")
        assert out["unit"] == "%" and out["dUnit"] == "bp"
        assert out["v"] == pytest.approx(vals[-1] / 100.0, abs=1e-4)
        lv = {x["dir"]: x for x in out["levels"]}
        assert set(lv) == {-1, 1}                       # 선물은 양방향
        # 레벨은 %, 거리는 bp — 두 자릿수가 100배 갈린다.
        assert abs(lv[-1]["entry"]) < 10
        sd = (out["upper"] - out["ma"]) / out["cond"]["entryZ"]
        assert lv[-1]["entryGap"] == pytest.approx(
            (out["ma"] + out["cond"]["entryZ"] * sd - out["v"]) * 100.0, abs=0.02)

    def test_진입_레벨은_보드_트리거와_같은_수다(self):
        """한 화면이 같은 문턱을 두 수로 말하지 않는다."""
        out, _c, _s, _d, _v = self._built()
        lv = [x for x in out["levels"] if x["dir"] == -1][0]
        tr = [t for t in out["triggers"] if t["dir"] == -1][0]
        assert lv["entry"] == pytest.approx(tr["level"], abs=1e-4)
        assert lv["entryGap"] == pytest.approx(tr["gap"], abs=1e-4)
        assert lv["entryReached"] == tr["reached"]

    def test_1년_카드의_분해가_그_구간_순손익으로_닫힌다(self):
        out, _c, _s, dates, _v = self._built()
        perf = out["perf1y"]
        assert set(perf) == set(mrp.PERF_KEYS)
        sp = perf["split"]
        got = sum(sp[k] for k in ("mtm", "carry", "rolldown", "funding", "cost")
                  if sp[k] is not None)
        assert got == pytest.approx(sp["total"], abs=1e-6)
        assert sp["total"] == pytest.approx(perf["totalPnl"], abs=1e-6)
        # 창이 진짜 1년이다 — 달력으로 센다(봉 수가 아니다).
        assert perf["from"] >= mrm.span_cut(dates, 12)

    def test_이력은_고른_조건의_밴드다(self):
        out, calls, _s, _d, vals = self._built()
        pts = out["history"]["points"]
        assert len(pts) == min(len(vals), mr_mod.HISTORY_N)
        knobs = calls[1]["knobs"]
        roll = bt.rolling_series(vals, int(knobs["lookback"]))
        assert pts[-1]["up"] == pytest.approx(
            round(roll["mean"][-1] + knobs["entryZ"] * roll["std"][-1], 4), abs=1e-4)

    def test_포지션은_엔진이_연_다리이고_나가는_문_둘을_진다(self):
        """[OWNER 2026-09-21 — "이미 진입했다고 가정한 포지션"] 그 가정의 정체.

        마지막 봉에 계열을 크게 밀어 **반드시 열린 채로 끝나게** 만든다 — 씨앗을
        돌려 찾으면 그 시험은 엔진의 우연에 기대게 되고, 우연이 바뀌면 조용히
        건너뛴다(그 판이 실제로 한 번 서 있었다).
        """
        vals_u = _ou(900, seed=7)
        vals_u[-1] = vals_u[-1] + 12.0            # |z| ≥ 2 → 그 봉에 진입
        leg_of, calls, _d, vals = _leg_of("BSS-3Y", "BSS 3Y", "bss", "bp", vals_u)
        # 손절을 아주 멀리 둬서 같은 봉에 손절로 안 닫히게 한다(우선순위: 손절 > 청산).
        grid_of, _seen = _grid_of([_cell(cdarRatio=1.0, lookback=60, entryZ=2.0,
                                         exitZ=0.5, stopZ=99.0, entryMode="level")])
        out = mrp.build_series("BSS-3Y", leg_of=leg_of, grid_of=grid_of)
        pos = out["position"]
        assert pos is not None and pos["dir"] == -1   # 늘어난 쪽의 반대에 건다
        assert pos["bars"] == 0 and pos["entryT"] == out["asof"]
        # 나가는 문은 **오늘의 것**이고 `exitsNow` 와 같은 수다(두 벌이 아니다).
        now = out["exitsNow"]
        assert (pos["exit"], pos["stop"]) == (now["exit"], now["stop"])
        assert (pos["exitGap"], pos["stopGap"]) == (now["exitGap"], now["stopGap"])
        # 위로 밀어 넣었으니 지금 쪽도 위다 — 중심선을 안 넘었다.
        assert pos["crossed"] is False and now["side"] == "above"
        # 들고 있는 다리는 두 문 **사이**에 있다(밖이면 엔진이 이미 닫았다).
        assert pos["exitGap"] > 0 and pos["stopGap"] > 0
        assert pos["legs"] == mr_mod.DIR_LEGS[out["kind"]][
            "minus" if pos["dir"] == -1 else "plus"]["legs"]
        # 진입 레벨은 **그 봉의 값**이다(당일 종가 체결 — 엔진 규약).
        assert pos["entryV"] == pytest.approx(round(vals[-1], 4), abs=1e-4)
        # 근사 판에는 롤다운·조달이 **아예 없다** — 0 으로 채우지 않는다.
        assert "rolldown" not in pos and "funding" not in pos

    def test_열린_다리가_없으면_None이다(self):
        """「없다」와 「못 잰다」를 가르는 자리 — 화면이 그 둘을 다르게 적는다."""
        outs = [self._built(seed=s)[0]["position"] for s in range(3, 12)]
        assert any(o is None for o in outs)


# ── ④ 페이로드 — 부분 결과 ───────────────────────────────────────────────────
class TestBuildPlan:
    def _row(self, sid, kind, z, asof="2026-09-18", v=30.0):
        return {"id": sid, "label": sid, "kind": kind,
                "defn": mr_mod.KIND_DEFN[kind], "unit": "bp", "v": v, "d1": 0.1,
                "dUnit": "bp", "z": z, "pctB": 50.0, "asof": asof,
                "state": {"kind": "inside", "days": None}}

    def test_순위는_늘어남_순이고_구워진_것들_안에서_매겨진다(self):
        rows = [self._row("BSS-3Y", "bss", 0.4), self._row("BSS-2Y", "bss", -2.1),
                self._row("BSS-5Y", "bss", 1.2)]
        got = mrp.build_plan(rows, total=25, excluded=[], building=True)
        assert [r["id"] for r in got["rows"]] == ["BSS-2Y", "BSS-5Y", "BSS-3Y"]
        assert [r["rank"] for r in got["rows"]] == [1, 2, 3]

    def test_못_구운_것을_세어서_말한다(self):
        """비어 있는 표를 조용히 내지 않는다 — 못 잰 것은 0 이 아니다."""
        rows = [self._row("BSS-3Y", "bss", 1.0)]
        exc = [{"id": "BSS-6M", "label": "BSS 6M", "reason": "짧아요"}]
        got = mrp.build_plan(rows, total=25, excluded=exc, building=True)
        assert got["done"] == 1 and got["pending"] == 23 and got["building"] is True
        assert got["excluded"] == exc
        assert got["total"] == 25

    def test_다_구워지면_대기가_0이다(self):
        rows = [self._row(f"BSS-{i}", "bss", i * 0.1) for i in range(1, 25)]
        got = mrp.build_plan(rows, total=25, excluded=[
            {"id": "x", "label": "x", "reason": "y"}], building=False)
        assert got["pending"] == 0 and got["building"] is False

    def test_소스별_종가가_셋으로_갈린다(self):
        """민평·선물·IRS 커브는 다른 날일 수 있다 — 한 칸에 뭉치면 거짓말이 된다."""
        rows = [self._row("BSS-3Y", "bss", 1.0, asof="2026-09-18"),
                self._row("FUT-KTB3", "fut", 0.5, asof="2026-09-19"),
                self._row("IRC-3Y-10Y", "irc", 0.2, asof="2026-09-17")]
        got = mrp.build_plan(rows, total=25, excluded=[], building=False)
        assert got["asof"] == {"bss": "2026-09-18", "fut": "2026-09-19",
                               "irs": "2026-09-17"}

    def test_통합_줄이_보드와_같은_산술로_선다(self):
        rows = [self._row("BSS-3Y", "bss", 1.0), self._row("FUT-KTB3", "fut", 2.0)]
        got = mrp.build_plan(rows, total=25, excluded=[], building=False)
        assert got["watch"]["n"] == 1                   # BSS 만 묶는다
        assert got["watch"]["kind"] == "book"

    def test_기준값이_페이로드에_적힌다(self):
        """화면이 「무엇을 잰 수인가」를 지어내지 않게."""
        got = mrp.build_plan([], total=25, excluded=[], building=True)
        p = got["params"]
        assert p["span"] == "1y" and p["months"] == 12
        assert p["rankKey"] == "cdarRatio" and p["gridSpan"] == "all"
        assert p["costBp"] == 0.5 and p["notional"] == 1_000_000.0
        assert got["rows"] == [] and got["watch"] is None


# ── ⑤ 캐시의 읽기 전용 문 ────────────────────────────────────────────────────
class TestPeek:
    def test_없으면_None이고_계산도_안_한다(self, tmp_path):
        assert cache_mod.peek("nope", "h", cache_dir=tmp_path) is None

    def test_해시가_맞을_때만_준다(self, tmp_path):
        cache_mod.cached("x", "h1", lambda: {"a": 1}, cache_dir=tmp_path)
        assert cache_mod.peek("x", "h1", cache_dir=tmp_path) == {"a": 1}
        assert cache_mod.peek("x", "h2", cache_dir=tmp_path) is None

    def test_망가진_파일은_조용히_미스다(self, tmp_path):
        (tmp_path / "y.json").write_text("[1,2,3]", encoding="utf-8")
        assert cache_mod.peek("y", "h", cache_dir=tmp_path) is None
        (tmp_path / "z.json").write_text("{", encoding="utf-8")
        assert cache_mod.peek("z", "h", cache_dir=tmp_path) is None

    def test_구운_것은_다시_안_굽는다(self, tmp_path):
        """빌더가 재기동을 견디는 자리 — 이미 구운 계열은 디스크에서 온다."""
        calls = []

        def compute():
            calls.append(1)
            return {"v": 1}

        cache_mod.cached("k", "h", compute, cache_dir=tmp_path)
        assert cache_mod.peek("k", "h", cache_dir=tmp_path) == {"v": 1}
        cache_mod.cached("k", "h", compute, cache_dir=tmp_path)
        assert len(calls) == 1
        blob = json.loads((tmp_path / "k.json").read_text(encoding="utf-8"))
        assert blob["hash"] == "h"
