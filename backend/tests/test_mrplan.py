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
        """BSS 의 하단은 국고 매도다 — 이 데스크가 못 하는 거래의 문턱을 권하지 않는다.

        ★2026-09-22 규약 뒤집기로 **살아남는 방향이 `-1` 에서 `+1` 로** 옮겨
        앉았다. 막히는 거래는 같은 거래(국고 대차매도)이고 그것을 가리키는
        부호만 바뀌었다 — 그 불변량은 `test_mr_convention.py` 가 잰다.
        """
        lv = mrp.levels_for("bss", ma=30.0, sd=2.0, v=30.0, entry_z=2.0,
                            exit_z=0.5, stop_z=2.5, scale=1.0)
        assert [x["dir"] for x in lv] == [1]
        assert lv[0]["legs"] == mr_mod.DIR_LEGS["bss"]["plus"]["legs"]

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
        # 조건을 고르는 창 — **성과를 잰 창과 같다** [OWNER 2026-09-21 오후].
        assert seen[0]["span"] == mrp.PLAN_SPAN
        assert calls[0]["knobs"] == mrp.BASE_KNOBS      # 격자는 기준 노브에서 출발
        # 실행은 **고른 칸**의 노브로 돈다.
        assert calls[1]["knobs"]["entryZ"] == 2.5
        assert calls[1]["knobs"]["entryMode"] == "touch"
        assert out["real"] is True

    def test_조건이_화면에_설_재료를_다_진다(self):
        out, _c, _s, _d, _v = self._built()
        cond = out["cond"]
        assert cond["lookback"] == 60 and cond["entryZ"] == 2.5
        assert cond["basis"] == "cdarRatio" and cond["span"] == mrp.PLAN_SPAN
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
        # BSS 가 할 수 있는 방향은 `+1` 하나다(2026-09-22 규약 뒤집기).
        lv = [x for x in out["levels"] if x["dir"] == 1][0]
        tr = [t for t in out["triggers"] if t["dir"] == 1][0]
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
        # ★**아래로** 민다(2026-09-22 규약 뒤집기). 엔진은 「늘어난 쪽의 반대」에
        # 걸므로 위로 밀면 `dir -1` 이 나오는데, BSS 에서 그쪽은 이제 국고
        # 대차매도라 막혀 있다 — 막힌 방향으로 밀면 다리가 아예 안 열리고 이
        # 시험은 「우연히 건너뛰는 판」이 된다(이 docstring 이 경계하는 바로 그것).
        vals_u[-1] = vals_u[-1] - 12.0            # |z| ≥ 2 → 그 봉에 진입
        leg_of, calls, _d, vals = _leg_of("BSS-3Y", "BSS 3Y", "bss", "bp", vals_u)
        # 손절을 아주 멀리 둬서 같은 봉에 손절로 안 닫히게 한다(우선순위: 손절 > 청산).
        grid_of, _seen = _grid_of([_cell(cdarRatio=1.0, lookback=60, entryZ=2.0,
                                         exitZ=0.5, stopZ=99.0, entryMode="level")])
        out = mrp.build_series("BSS-3Y", leg_of=leg_of, grid_of=grid_of)
        pos = out["position"]
        assert pos is not None and pos["dir"] == 1    # 줄어든 쪽의 반대에 건다
        assert pos["bars"] == 0 and pos["entryT"] == out["asof"]
        # 나가는 문은 **오늘의 것**이고 `exitsNow` 와 같은 수다(두 벌이 아니다).
        now = out["exitsNow"]
        assert (pos["exit"], pos["stop"]) == (now["exit"], now["stop"])
        assert (pos["exitGap"], pos["stopGap"]) == (now["exitGap"], now["stopGap"])
        # 아래로 밀어 넣었으니 지금 쪽도 아래다 — 중심선을 안 넘었다.
        assert pos["crossed"] is False and now["side"] == "below"
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

    def test_고른_창과_잰_창이_같다는_것이_결정이다(self):
        """[OWNER 2026-09-21 오후 — "이것도 그냥 표본도 1년으로 하죠?"]

        오전 결정은 「조건은 전체 표본」이었고 근거는 거래 수였다(1년 창은 계열당
        0~5건). 오너가 그 답을 듣고 1년으로 바꿨다 — **선택과 채점이 같은 창**이
        됐다는 뜻이고, 그래서 화면의 1년 손익은 162칸 중 1등의 값이다. 이 등식이
        조용히 갈리면 화면 각주가 거짓이 되므로 여기서 박는다.
        """
        assert mrp.GRID_SPAN == mrp.PLAN_SPAN == "1y"

    def test_기준값이_페이로드에_적힌다(self):
        """화면이 「무엇을 잰 수인가」를 지어내지 않게."""
        got = mrp.build_plan([], total=25, excluded=[], building=True)
        p = got["params"]
        assert p["span"] == "1y" and p["months"] == 12
        assert p["rankKey"] == "cdarRatio" and p["gridSpan"] == p["span"]
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


# ── ⑥ 배관 — 배경 빌더와 라우트 [감사 2026-09-21] ────────────────────────────
#
# 이 절이 늦게 붙었다. 첫 판은 `mrplan` 의 산술만 재고 `main` 의 배관(스레드·공유
# 사전·캐시 키)은 **한 줄도 안 쟀는데**, 그 사이 `_mr_plan_build` 의 머리 주석은
# 「스레드를 안 만든다 — 시험이 이것을 동기로 부른다」고 적고 있었다. 그 시험이
# 없었다. 감사가 그 빈칸에서 실제 경쟁 조건 하나(락 밖 `start()`)와 사전 동시
# 변경 하나를 찾아냈다 — 아래가 그 둘을 박는 자리다.
class TestWorker:
    """워커와 시작 문 — **SQL 을 안 탄다**(계열 하나 굽는 자리를 주입한다)."""

    @pytest.fixture()
    def m(self, monkeypatch, tmp_path):
        from app import main as m

        # 상태를 시험마다 깨끗이 — 모듈 전역이라 안 하면 앞 시험이 샌다.
        monkeypatch.setattr(m, "_mr_plan_thread", None, raising=False)
        monkeypatch.setattr(m, "_mr_plan_key", None, raising=False)
        m._mr_plan_excluded.clear()
        return m

    def test_워커가_계열마다_따로_잡고_사유를_적는다(self, m, monkeypatch):
        """하나가 터져도 나머지는 구워진다 — `/api/mr/book` 의 그 규율."""
        baked: list[str] = []
        bad = mr_mod.SERIES[1][0]

        def fake_one(sid):
            if sid == bad:
                raise ValueError("이력이 룩백보다 짧아요")
            baked.append(sid)

        monkeypatch.setattr(m, "peek", lambda *a, **k: None)
        monkeypatch.setattr(m, "_mr_plan_one", fake_one)
        monkeypatch.setattr(m, "_mr_plan_key", "K", raising=False)
        m._mr_plan_build("K")                       # ← 동기로 부른다(주석의 그 계약)
        assert len(baked) == len(mr_mod.SERIES) - 1
        assert list(m._mr_plan_excluded) == [bad]
        assert m._mr_plan_excluded[bad]["reason"] == "이력이 룩백보다 짧아요"

    def test_이미_구운_계열은_다시_안_굽는다(self, m, monkeypatch):
        """재기동을 견디는 자리 — 디스크에 있으면 그냥 지나간다."""
        calls: list[str] = []
        monkeypatch.setattr(m, "peek", lambda *a, **k: {"v": 1})
        monkeypatch.setattr(m, "_mr_plan_one", lambda sid: calls.append(sid))
        monkeypatch.setattr(m, "_mr_plan_key", "K", raising=False)
        m._mr_plan_build("K")
        assert calls == []

    def test_자료가_갈리면_스스로_멈춘다(self, m, monkeypatch):
        monkeypatch.setattr(m, "peek", lambda *a, **k: None)
        monkeypatch.setattr(m, "_mr_plan_one", lambda sid: None)
        monkeypatch.setattr(m, "_mr_plan_key", "다른키", raising=False)
        m._mr_plan_build("K")                       # 키가 안 맞으면 첫 계열에서 반환
        assert m._mr_plan_excluded == {}

    def test_같은_키로_스레드가_둘_뜨지_않는다(self, m, monkeypatch):
        """★감사가 잡은 경쟁 조건 — `start()` 가 자물쇠 **밖**에 있으면 A 가
        시작하기 전의 틈에 B 가 `is_alive()` 거짓을 보고 두 번째 빌더를 띄웠다.

        그 틈을 재현한다: 스레드를 **안 돌리는** 가짜로 바꿔 `is_alive()` 가 늘
        거짓이게 만들고, 두 번 부른다. 자물쇠 안에서 시작하면 두 번째 호출은
        「지금 굽고 있다」로 돌아서야 한다.
        """
        started: list[object] = []

        class FakeThread:
            def __init__(self, *a, **k):
                self.alive = False

            def start(self):
                started.append(self)
                self.alive = True          # 자물쇠 안에서 시작 → 곧바로 살아 있다

            def is_alive(self):
                return self.alive

        monkeypatch.setattr(m.threading, "Thread", FakeThread)
        assert m._mr_plan_start("K") is True
        assert m._mr_plan_start("K") is True
        assert len(started) == 1

    def test_실패_기록을_읽는_동안_워커가_넣어도_안_터진다(self, m, monkeypatch):
        """★감사가 잡은 둘째 — 라우트가 `values()` 를 순회하는 동안 워커가 넣으면
        CPython 이 `RuntimeError: dictionary changed size` 를 낸다. 두 쪽이 같은
        자물쇠를 쓰는지를 **자물쇠를 잡고** 확인한다."""
        import threading as th

        m._mr_plan_fail("X", "X", "why")
        hit = []

        def writer():
            try:
                m._mr_plan_fail("Y", "Y", "why2")
            except Exception as exc:                 # noqa: BLE001
                hit.append(exc)

        with m._mr_plan_lock:                        # 라우트가 베끼는 그 구간
            t = th.Thread(target=writer)
            t.start()
            t.join(timeout=0.3)
            assert t.is_alive(), "워커가 자물쇠를 안 기다렸다 — 읽기 중 변경이 가능하다"
            snapshot = list(m._mr_plan_excluded.values())
        t.join(timeout=2)
        assert hit == [] and len(snapshot) == 1
        assert len(m._mr_plan_excluded) == 2

    def test_캐시_이름에_격자_창이_박혀_있다(self, m):
        """창을 바꾼 날 옛 조건이 조용히 나가면 안 된다(`mrplan.cache_name` 머리)."""
        assert mrp.cache_name("BSS-3Y") == f"mr-plan-{mrp.GRID_SPAN}-BSS-3Y"
        assert mrp.GRID_SPAN in mrp.cache_name("X")


def test_격자는_엔진_결과를_볼_수_없다():
    """「회계가 격자의 칸을 안 바꾼다」의 **진짜 근거는 서명**이다.

    앞의 `TestBuildSeries` 는 `accounting` 플래그의 **차례**만 잰다(가짜 `leg_of`
    가 그 값을 `real` 에만 쓴다) — 회계가 칸을 바꾸는 회귀가 나도 그 시험은
    통과한다. 못 바꾸는 이유는 `_mr_optimize` 가 **엔진 결과를 아예 안 받는다**는
    것이고, 그건 인자 목록에 적혀 있다. 그 자리를 여기서 박는다.
    """
    import inspect

    from app import main as m

    params = set(inspect.signature(m._mr_optimize).parameters)
    assert "leg" not in params and "r" not in params
    # 봉·거래는 자기가 다시 시뮬한다 — 받는 것은 날짜·값과 노브뿐이다.
    assert {"dates", "vals", "base", "allow"} <= params
    src = inspect.getsource(m._mr_optimize)
    assert 'leg["r"]' not in src and "leg['r']" not in src
