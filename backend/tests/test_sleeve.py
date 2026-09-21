# -*- coding: utf-8 -*-
"""모멘텀 **슬리브** 집행면 — 「오늘 칠 것」의 산술과 배관을 핀으로 박는다.

이 모듈은 규칙을 안 만든다. 규칙은 레인 스크립트(`scripts/sleeve_*`) 것이고 여기서는
그것을 불러 모으기만 한다 — 그래서 이 파일이 재는 것도 **모으기가 맞는가**다:

  · 주문은 목표가 아니라 **어제와의 차이**다(연속 북이라 진입 사건이 없다)
  · 부호 규약 — 계열이 −bp 라 DV01 이 양이면 **리시브**
  · 1억 미만은 안 친다
  · 못 세우면 **왜 못 세우는지**를 말한다(빈 표를 안 낸다) — `SystemExit` 까지
  · 원장이 비어 있는 것은 결함이 아니라 **결정 대기**다

레인을 주입해서 돌린다(`lane=`) — 실제 배관은 44초이고 리포 밖 배분기를 읽는다.
"""
import json

import pytest

from app import sleeve


# ── 가짜 레인 — `scripts.sleeve_{execution,monitor}` 의 얼굴 ──────────────────
class _Frame:
    """`net_dv`/`rp` 자리 — `.index` 와 `.at[d, k]` 만 쓴다(pandas 를 안 세운다)."""

    def __init__(self, data: dict[str, dict[str, float]]):
        self._d = data
        self.index = list(data)

    @property
    def at(self):
        outer = self._d

        class _At:
            def __getitem__(self, key):
                d, k = key
                return outer[d][k]

        return _At()


class _Se:
    LEG_T = ("3Y", "10Y")

    def __init__(self, *, dv, pv, asof="2026-09-18"):
        self._dv, self._pv, self._asof = dv, pv, asof

    def real_pv01(self):
        return _Frame(self._pv)

    def sleeve_dv01_path(self):
        return None, _Frame(self._dv), {"mult": 11.89}

    def asof_for(self, ix, meta):
        # 실제 함수와 같은 계약 — 쓸 수 있는 날 중 기준일 하나.
        return self._asof


class _Sm:
    FREEZE_DATE = "2026-09-15"
    RATE = 0.05

    def __init__(self, **over):
        self._d = {
            "scale": 1.0, "mr_margin": 9.537e9, "headroom": 4.63e8,
            "headroom_no_shrink": 0.0, "scale_no_shrink": 0.0,
            "k_mr": 0.9538, "k_mr_live": 0.9538,
            "margin_source": {"source": "allocator", "rule": "B 효율가중",
                              "asof": "2026-09-16", "stale": [], "stale_held": 0},
            "hist_days": 2318, "hist_hit_days": 24,
        }
        self._d.update(over)

    def daily(self, verbose=True, source="allocator"):
        return dict(self._d)


def _lane(*, dv=None, pv=None, asof="2026-09-18", **sm_over):
    dv = dv or {"2026-09-18": {"3Y": -1_422_000.0, "10Y": -1_300_000.0}}
    pv = pv or {"2026-09-18": {"3Y": 28_205.0, "10Y": 81_858.0}}
    return lambda: (_Se(dv=dv, pv=pv, asof=asof), _Sm(**sm_over))


def _ledger(tmp_path, rows):
    p = tmp_path / "ledger.json"
    p.write_text(json.dumps({"rows": rows}, ensure_ascii=False), encoding="utf-8")
    return p


class TestSheet:
    def test_주문은_목표가_아니라_어제와의_차이다(self, tmp_path):
        """★이 북은 매일 크기가 바뀌는 **연속 북**이라 「진입」이라는 사건이 없다 —
        데스크가 실제로 치는 것은 어제와의 차이다(`sleeve_daily` 머리)."""
        prev = {"date": "2026-09-08", "legs": {
            "3Y": {"signed_face": -2.75e9}, "10Y": {"signed_face": -1.09e9}}}
        out = sleeve.build_sheet(lane=_lane(), ledger_path=_ledger(tmp_path, [prev]))
        legs = {l["tenor"]: l for l in out["legs"]}
        # 목표는 |DV01| / pv01 × 1e8 이고, 주문은 «부호 붙인 목표 − 어제»다.
        want3 = 1_422_000.0 / 28_205.0 * 1e8
        assert legs["3Y"]["face"] == pytest.approx(want3, rel=1e-9)
        assert legs["3Y"]["signedFace"] == pytest.approx(-want3, rel=1e-9)
        assert legs["3Y"]["delta"] == pytest.approx(-want3 + 2.75e9, rel=1e-9)
        assert out["turnover"] == pytest.approx(
            sum(abs(l["delta"]) for l in out["legs"]), rel=1e-12)

    def test_첫날은_목표_전체가_주문이다(self, tmp_path):
        out = sleeve.build_sheet(lane=_lane(), ledger_path=_ledger(tmp_path, []))
        for l in out["legs"]:
            assert l["prevSigned"] == 0.0
            assert l["delta"] == pytest.approx(l["signedFace"], rel=1e-12)

    def test_부호는_DV01이_양이면_리시브다(self, tmp_path):
        """계열이 **−bp** 라서다 — 화면이 이 규약을 다시 만들지 않게 서버가 낸다."""
        out = sleeve.build_sheet(
            lane=_lane(dv={"2026-09-18": {"3Y": +1_000_000.0, "10Y": -1_000_000.0}}),
            ledger_path=_ledger(tmp_path, []))
        legs = {l["tenor"]: l for l in out["legs"]}
        assert legs["3Y"]["side"] == 1 and legs["10Y"]["side"] == -1
        assert legs["3Y"]["signedFace"] > 0 and legs["10Y"]["signedFace"] < 0

    def test_1억_미만은_안_친다(self, tmp_path):
        """호가 단위와 수수료를 못 이긴다(`sleeve_daily.MIN_TICKET`)."""
        want3 = 1_422_000.0 / 28_205.0 * 1e8
        prev = {"date": "x", "legs": {
            "3Y": {"signed_face": -(want3 - 5e7)},        # 5천만 차이 → 안 친다
            "10Y": {"signed_face": 0.0}}}                 # 전액 → 친다
        out = sleeve.build_sheet(lane=_lane(), ledger_path=_ledger(tmp_path, [prev]))
        legs = {l["tenor"]: l for l in out["legs"]}
        assert legs["3Y"]["trade"] is False
        assert legs["10Y"]["trade"] is True
        assert out["minTicket"] == sleeve.MIN_TICKET

    def test_W4_배율이_액면을_줄인다(self, tmp_path):
        out = sleeve.build_sheet(lane=_lane(scale=0.5), ledger_path=_ledger(tmp_path, []))
        for l in out["legs"]:
            assert l["faceAfter"] == pytest.approx(l["face"] * 0.5, rel=1e-12)
        assert out["faceAfter"] == pytest.approx(out["faceTotal"] * 0.5, rel=1e-12)
        assert out["marginNeed"] == pytest.approx(out["faceAfter"] * 0.05, rel=1e-12)

    def test_축소를_안_하면_못_선다는_사실을_같이_낸다(self, tmp_path):
        """★등록서의 「평균회귀 쪽은 안 건드린다」와 k_mr 을 여력에 거는 것이 한
        문장에서 충돌한다(인계문 §5-1). 화면이 그 둘을 나란히 적을 수 있어야 한다."""
        out = sleeve.build_sheet(lane=_lane(), ledger_path=_ledger(tmp_path, []))
        assert out["headroom"] > 0 and out["headroomNoShrink"] == 0.0
        assert out["scale"] == 1.0 and out["scaleNoShrink"] == 0.0
        assert out["kMr"] == pytest.approx(0.9538)

    def test_채점_창은_동결일_다음부터다(self, tmp_path):
        a = sleeve.build_sheet(lane=_lane(asof="2026-09-18"),
                               ledger_path=_ledger(tmp_path, []))
        b = sleeve.build_sheet(
            lane=_lane(dv={"2026-09-15": {"3Y": -1e6, "10Y": -1e6}},
                       pv={"2026-09-15": {"3Y": 28_205.0, "10Y": 81_858.0}},
                       asof="2026-09-15"),
            ledger_path=_ledger(tmp_path, []))
        assert a["scored"] is True and b["scored"] is False
        assert a["freeze"] == "2026-09-15"

    def test_증거금_출처를_그대로_싣는다(self, tmp_path):
        """어느 규칙·어느 기준일의 여력인지 — 화면이 「여력이 하루 옛것」을 말해야 한다."""
        out = sleeve.build_sheet(lane=_lane(), ledger_path=_ledger(tmp_path, []))
        assert out["marginSource"]["rule"] == "B 효율가중"
        assert out["marginSource"]["asof"] == "2026-09-16"
        assert out["asof"] == "2026-09-18"        # 표는 09-18, 여력은 09-16


class TestUnavailable:
    """못 세우면 **왜 못 세우는지**를 말한다 — 빈 표를 안 낸다."""

    def test_레인을_못_불러오면_사유를_낸다(self):
        def boom():
            raise ImportError("scripts 가 없어요")

        out = sleeve.build_sheet(lane=boom)
        assert out["available"] is False and "불러오지 못했어요" in out["why"]

    def test_SystemExit_도_잡는다(self):
        """★레인 스크립트는 자료가 없으면 `SystemExit` 으로 멈춘다 — 웹 프로세스에서
        그것을 안 잡으면 요청이 통째로 죽는다(`Exception` 으로는 안 잡힌다)."""
        class _Bad(_Se):
            def real_pv01(self):
                raise SystemExit("집행표를 먼저 돌리세요")

        out = sleeve.build_sheet(
            lane=lambda: (_Bad(dv={}, pv={}), _Sm()))
        assert out["available"] is False
        assert "집행표를 먼저" in out["why"]

    def test_겹치는_날이_없으면_사유를_낸다(self):
        out = sleeve.build_sheet(lane=_lane(
            dv={"2026-09-18": {"3Y": 1.0, "10Y": 1.0}},
            pv={"2026-09-17": {"3Y": 1.0, "10Y": 1.0}}))
        assert out["available"] is False and "겹치는 날이 없어요" in out["why"]


class TestLedger:
    """원장이 비어 있는 것은 **결함이 아니라 결정 대기**다 — 채우지 않는다."""

    def test_빈_원장도_사실로_낸다(self, tmp_path):
        assert sleeve.read_ledger(tmp_path / "없는파일.json") == {
            "rows": 0, "last": None, "lastRun": None, "scoredRows": 0}

    def test_마지막_행과_채점_행수를_센다(self, tmp_path):
        p = _ledger(tmp_path, [
            {"date": "2026-09-08", "run": "2026-09-15", "scored": False, "legs": {}},
            {"date": "2026-09-16", "run": "2026-09-16", "scored": True, "legs": {}}])
        got = sleeve.read_ledger(p)
        assert got == {"rows": 2, "last": "2026-09-16",
                       "lastRun": "2026-09-16", "scoredRows": 1}

    def test_망가진_원장은_조용히_안_넘어간다(self, tmp_path):
        p = tmp_path / "ledger.json"
        p.write_text("{", encoding="utf-8")
        got = sleeve.read_ledger(p)
        assert got["rows"] == 0 and "why" in got


# ── 배관 — 캐시 이름과 «조용한 실패» [실측 2026-09-21] ───────────────────────
class TestPlumbing:
    """라우트가 실제로 밟은 결함 둘을 박는다.

    둘 다 시험이 없어서 **브라우저에서** 드러났다: 캐시 이름에 키를 넣어 윈도에서
    못 쓰는 파일명이 됐고(`:`·`|`), 그 실패가 화면에 안 드러나 열 번을 불러도
    「굽는 중」만 섰다.
    """

    def test_캐시_이름은_파일로_쓸_수_있어야_한다(self):
        """★`cached(name, hash, …)` 의 **첫 인자가 그대로 파일명**이다. 키를 이름에
        넣으면 `sql:…|…` 이 되어 윈도에서 `[Errno 22]` 로 죽는다 — 그런데 라우트는
        200 을 돌려주므로 화면은 영원히 「굽는 중」이다."""
        from app import main as m

        bad = set(r':|<>"?*\/')
        assert not (set(m.SLEEVE_CACHE) & bad), m.SLEEVE_CACHE
        # 키는 이름이 아니라 **해시**로 간다 — 그쪽은 파일명이 안 된다.
        assert ":" in m._sleeve_key()

    def test_키가_읽는_파일을_따라간다(self, monkeypatch, tmp_path):
        """스크립트를 다시 돌리면 화면도 따라와야 한다 — 자료 키만 보면 옛 표가
        계속 나간다(이 리포의 「조용한 스테일」)."""
        from app import main as m

        p = tmp_path / "sleeve_daily_ledger.json"
        p.write_text('{"rows": []}', encoding="utf-8")
        monkeypatch.setattr(m.sleeve, "LEDGER_PATH", p)
        first = m._sleeve_key()
        p.write_text('{"rows": [{"date": "2026-09-18"}]}', encoding="utf-8")
        assert m._sleeve_key() != first

    def test_굽다_죽으면_사유를_낸다(self, monkeypatch):
        """★「굽는 중」만 되풀이하면 아무도 이유를 모른다."""
        from app import main as m

        monkeypatch.setattr(m, "_sleeve_error", "[Errno 22] Invalid argument", raising=False)
        monkeypatch.setattr(m, "_sleeve_start", lambda key: True)
        monkeypatch.setattr(m, "peek", lambda *a, **k: None)
        out = m.momentum_sleeve()
        assert out["available"] is False
        assert "굽다가 멈췄어요" in out["why"] and "Errno 22" in out["why"]

    def test_구워져_있으면_그대로_낸다(self, monkeypatch):
        from app import main as m

        monkeypatch.setattr(m, "peek", lambda *a, **k: {"available": True, "asof": "2026-09-18"})
        out = m.momentum_sleeve()
        assert out == {"building": False, "available": True, "asof": "2026-09-18"}
