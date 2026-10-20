# -*- coding: utf-8 -*-
"""수급 신호 실험 — 산술과 **우연을 같이 적는 규율** [2026-10-20].

선례는 `test_flow.py` 와 같다: 산술이 `_align` 밖의 순수 함수라 **SQL 없이** 잰다.

이 파일이 지는 명제 넷:
    ① 포지션은 최소 보유기간을 지킨다 — 신호가 뒤집혀도 N 봉은 안 바꾼다.
    ② 비용은 **포지션이 바뀐 봉에만** 문다(첫 봉 포함).
    ③ 원형 이동은 **길이와 값 묶음을 보존**한다 — 맞물림만 깬다.
    ④ ★**수를 혼자 안 내보낸다** — 한 칸의 우연과 탐색의 우연을 같이 싣는다.
"""
from __future__ import annotations

import random

import pytest

from app import flowlab


class Test포지션:
    def test_최소_보유기간을_지킨다(self):
        """신호가 매 봉 뒤집혀도 3봉은 들고 간다."""
        sig = [1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0]
        got = flowlab.positions(sig, 3)
        assert got == [1, 1, 1, -1, -1, -1, 1, 1]

    def test_보유_1봉이면_신호를_그대로_탄다(self):
        sig = [1.0, -1.0, -1.0, 1.0]
        assert flowlab.positions(sig, 1) == [1, -1, -1, 1]

    def test_신호가_없는_앞머리는_0_이다(self):
        """창이 안 찬 봉은 **안 든다** — 0 으로 채우면 없는 포지션을 지어낸다."""
        assert flowlab.positions([None, None, 1.0, 1.0], 1) == [0, 0, 1, 1]


class Test채점:
    def test_비용은_바뀐_봉에만_문다(self):
        """첫 봉도 드는 거래라 센다. 3봉 중 진입 한 번 + 뒤집기 한 번 = 2회."""
        pos = [1, 1, -1]
        got = flowlab.score(pos, [0.0, 0.0, 0.0], cost_bp=0.5, dv01=1e7)
        assert got["trades"] == 2
        assert got["total"] == pytest.approx(-2 * 0.5 * 1e7)

    def test_금리가_내리면_롱이_번다(self):
        got = flowlab.score([1], [-1.0], cost_bp=0.0, dv01=1e7)
        assert got["total"] == pytest.approx(1e7)      # −(+1)×(−1bp)×DV01
        got2 = flowlab.score([-1], [-1.0], cost_bp=0.0, dv01=1e7)
        assert got2["total"] == pytest.approx(-1e7)

    def test_낙폭은_고점_대비다(self):
        got = flowlab.score([1, 1, 1], [-1.0, 2.0, 0.0], cost_bp=0.0, dv01=1e7)
        #: 누적 +1 → −1 → −1(천만원 단위). 고점 +1 에서 −1 까지 = 2.
        assert got["mdd"] == pytest.approx(2e7)

    def test_안_움직이면_Calmar_가_None_이다(self):
        """낙폭이 0 이면 나눌 수 없다 — 0 으로도 큰 수로도 안 채운다."""
        assert flowlab.score([0, 0], [1.0, 1.0], cost_bp=0.0)["calmar"] is None


class Test원형이동:
    def test_길이와_값_묶음이_보존된다(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        got = flowlab.shift(xs, 1)
        assert got == [4.0, 1.0, 2.0, 3.0]
        assert sorted(got) == sorted(xs)

    def test_0_이면_그대로다(self):
        xs = [1.0, 2.0, 3.0]
        assert flowlab.shift(xs, 0) == xs

    def test_우연_분포는_같은_포지션을_돌려_가며_잰다(self):
        """★맞물림만 깬다 — 포지션도 수익도 그대로고 **정렬만** 바뀐다."""
        rng = random.Random(0)
        pos = [1] * 300 + [-1] * 300
        #: ⚠**낙폭이 있어야 Calmar 가 선다.** 첫 판은 완벽히 유리한 자료를 줬다가
        #: 누적이 단조로 올라 MDD 가 0 이 되었고, `calmar` 가 `None` 이라 비교가
        #: 터졌다. 열 봉마다 거스르는 날을 섞어 낙폭을 만든다.
        dy = [((-1.0 if i < 300 else 1.0) if i % 10 else (0.5 if i < 300 else -0.5))
              for i in range(600)]
        real = flowlab.score(pos, dy)["calmar"]
        assert real is not None
        nulls = flowlab.null_calmars(pos, dy, 40, rng)
        assert len(nulls) > 0
        assert nulls == sorted(nulls)
        #: 맞물린 진짜가 돌린 것들보다 세야 한다(이 합성 자료는 완벽히 맞물렸다).
        assert real > nulls[-1]


class Test우연을_같이_적는다:
    def test_p값은_이상인_몫이다(self):
        xs = [0.0, 1.0, 2.0, 3.0]
        assert flowlab.pct_rank(xs, 2.0) == pytest.approx(0.5)
        assert flowlab.pct_rank(xs, 9.0) == 0.0
        assert flowlab.pct_rank([], 1.0) == 1.0

    def test_연도별로_갈라_한_해가_다_먹는지_본다(self):
        rows = flowlab.by_year(["2024-01-02", "2024-02-02", "2025-01-02"],
                               [10.0, 10.0, 80.0])
        assert [r["year"] for r in rows] == ["2024", "2025"]
        assert rows[1]["share"] == pytest.approx(0.8)

    def test_격자는_천장을_잴_모집단이다(self):
        """화면이 고를 수 있는 값은 **격자 안**이어야 한다 — 밖이면 천장과
        견줄 수 없고, 그러면 이 모듈이 존재할 까닭이 없다."""
        assert 20 in flowlab.SHORTS and 60 in flowlab.LONGS and 20 in flowlab.HOLDS
        cells = [(s, L, h) for s in flowlab.SHORTS for L in flowlab.LONGS
                 for h in flowlab.HOLDS if s < L]
        assert len(cells) > 100      # 천장이 뜻을 가지려면 칸이 넉넉해야 한다

    def test_비용과_지연은_손잡이가_아니다(self):
        """둘 다 **자료 사실**이다. 비용은 계획면 정본에서 오고(두 화면이 같은
        거래에 다른 돈을 매기면 안 된다), 지연은 현물 수급이 하루 늦는다는 사실이다."""
        from app import mrplan
        assert flowlab.COST_BP == mrplan.COST_BP
        assert flowlab.LAG == 1
