# -*- coding: utf-8 -*-
"""크레딧 RV (DTS) — Lab 세입자의 산술 핀.

[OWNER 2026-10-02] 「DTS version 을 하나 Lab 에다가」. 제품 `rv.py` 와 **다른 모듈**
이고, 이 파일은 그 다름이 **의도대로**인지를 잰다 — 앵커 하나 · 통안 없음 ·
등급축 있음 · 분모가 `s` · 바닥이 걸리는 자리.

근거는 `app/creditdts.py` 머리(research/credit-rv-dts 의 R0~R5).
"""
import datetime as dt

import pytest

from app import creditdts as cd


class Test유니버스:
    def test_통안은_유니버스에_없다(self):
        """크레딧이 아니라 금리물이고, 국고 대비가 **0 을 가로지른다**(−33.7~+7.1bp)
        — `s` 로 나누는 순간 폭발하고 부호가 뒤집힌다."""
        assert "MSB" not in cd.SECTORS
        assert "KTB" not in cd.SECTORS, "국고는 앵커지 후보가 아니다"

    def test_등급축이_있다(self):
        """★제품(`creditmatrix.BOND_TYPES`)은 회사채를 CB1 하나만 든다. 등급축이
        이 화면의 핵심이라 CB2~CB5 를 여기서 따로 센다."""
        for g in ("CB1", "CB2", "CB3", "CB4", "CB5"):
            assert g in cd.SECTORS
        assert len(cd.SECTORS) == 10

    def test_테너는_열둘이고_30Y_는_없다(self):
        """30Y 민평은 국고·공사에만 있다 — 크레딧 횡단면이 안 선다."""
        labs = [t for t, _y in cd.TENORS]
        assert len(labs) == 12 and "30Y" not in labs
        assert labs[0] == "3M" and labs[-1] == "20Y"


class Test분모:
    """★이 모듈의 존재 이유 — 분모가 σ 가 아니라 **s** 다."""

    @staticmethod
    def _seq(n: int, val: float, last: float) -> list[float]:
        return [val] * (n - 1) + [last]

    def test_z_는_지금_스프레드로_나눈다(self):
        """(now − 자기평균) ÷ max(now, floor). σ 가 아니다."""
        seq = self._seq(cd.WINDOW, 20.0, 40.0)
        z, mu, den = cd._z_now(seq, cd.FLOOR_BP)
        # 평균 ≈ 20.08, 분모 = 40 → z ≈ (40−20.08)/40
        assert den == pytest.approx(40.0)
        assert z == pytest.approx((40.0 - mu) / 40.0, abs=1e-3)

    def test_바닥이_좁은_칸을_구한다(self):
        """★스프레드 2bp 인 날 `s` 로 나누면 그 칸 하나가 횡단면을 삼킨다
        (실측: 최소 2~5bp 로 내려가는 칸이 아홉)."""
        seq = self._seq(cd.WINDOW, 20.0, 2.0)
        _z, _mu, den = cd._z_now(seq, cd.FLOOR_BP)
        assert den == pytest.approx(cd.FLOOR_BP), "바닥 아래는 바닥으로 나눈다"

    def test_창이_얇으면_수를_안_낸다(self):
        """지어낸 z 는 숫자처럼 보이는 잡음이다 — 0 이 아니라 None."""
        # ⚠하나 모자라게 만든다 — `MIN_OBS - 1` 에 오늘을 더하면 **딱 문턱**이라
        #   통과해 버린다(첫 판이 그랬다). 경계는 양쪽을 다 잰다.
        z, _mu, _den = cd._z_now([20.0] * (cd.MIN_OBS - 2) + [30.0], cd.FLOOR_BP)
        assert z is None, "문턱 아래는 수를 안 낸다"
        ok, _mu, _den = cd._z_now([20.0] * (cd.MIN_OBS - 1) + [30.0], cd.FLOOR_BP)
        assert ok is not None, "문턱 딱 맞으면 낸다"

    def test_좁아진_칸은_음수다(self):
        """★오너가 원한 방향 — 제 평소보다 **좁으면** 비싸다(z < 0)."""
        z, _mu, _den = cd._z_now(self._seq(cd.WINDOW, 30.0, 10.0), cd.FLOOR_BP)
        assert z is not None and z < 0


class Test페이로드:
    @staticmethod
    def _rows(n: int = cd.WINDOW + 5):
        """민평 두 종목(국고·산금) × 두 테너의 가짜 행. `_fetch` 를 대신한다."""
        d0 = dt.date(2020, 1, 1)
        dates = [d0 + dt.timedelta(days=i) for i in range(n)]
        g = {}
        for tenor in ("2Y", "3Y"):
            g[("KTB", tenor)] = [3.0] * n
            g[("KDB", tenor)] = [3.2] * (n - 1) + [3.5]     # 20bp → 50bp 로 벌어짐
        return dates, g

    def test_앵커는_국고_하나다(self, monkeypatch):
        """제품은 앵커가 둘이라 행마다 이름을 적어야 했다. 여기는 하나라 그 칸이 없다."""
        monkeypatch.setattr(cd, "_fetch", self._rows)
        got = cd.analysis()
        assert got["items"], "칸이 서야 한다"
        for it in got["items"]:
            assert "base" not in it and "baseLabel" not in it

    def test_랭크는_서버가_센다(self, monkeypatch):
        """§16 — 화면은 읽기만 한다. z 큼 = 싸다 = 1등."""
        monkeypatch.setattr(cd, "_fetch", self._rows)
        got = cd.analysis()
        ranks = sorted(it["rank"] for it in got["items"])
        assert ranks == list(range(1, len(got["items"]) + 1))
        best = min(got["items"], key=lambda it: it["rank"])
        assert best["z"] == max(it["z"] for it in got["items"])

    def test_못_세운_칸은_사유와_함께_뺀다(self, monkeypatch):
        """조용히 빼면 「내 칸이 왜 없지」가 된다(이 리포의 그 규율)."""
        def thin():
            dates, g = self._rows()
            g[("KDB", "2Y")] = [None] * len(dates)      # 통째 결측
            return dates, g

        monkeypatch.setattr(cd, "_fetch", thin)
        got = cd.analysis()
        assert any(e["label"].endswith("2Y") for e in got["excluded"])
        assert all(e["why"] for e in got["excluded"])

    def test_무엇을_보고_있나를_서버가_말한다(self, monkeypatch):
        """화면이 기준을 지어내면 서버가 바꾼 날 화면만 옛말을 한다."""
        monkeypatch.setattr(cd, "_fetch", self._rows)
        got = cd.analysis()
        assert "국고 대비" in got["basis"] and "지금 스프레드" in got["basis"]
        assert got["floorBp"] == cd.FLOOR_BP and got["window"] == cd.WINDOW


class Test라우트:
    def test_붙어_있고_바닥을_검사한다(self):
        from fastapi.testclient import TestClient

        from app import main as M

        paths = {r.path for r in M.app.routes if "creditdts" in getattr(r, "path", "")}
        assert paths == {"/api/lab/creditdts"}
        c = TestClient(M.app)
        assert c.get("/api/lab/creditdts?floor=-1").status_code == 422
        assert c.get("/api/lab/creditdts?floor=999").status_code == 422
