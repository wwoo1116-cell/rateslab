# -*- coding: utf-8 -*-
"""부호 규약 «스왑 − 채권현물/국채선물» — 뒤집기가 **경제적으로 무해**했나
[OWNER 2026-09-22 — "BSS나 FSW같은거 이제 컨벤션 바꾸는게 스왑 - 채권현물 또는
국채선물이야" · "ㅇㅇ 뒤집어" · "뜻이 뒤집히는게 정상이야"].

## 이 파일이 답하는 물음

규약을 뒤집는 일은 **부호 하나를 빠뜨리기 딱 좋은 작업**이다. 자리가 열둘이고
(계열 둘 · 다리 차례 · 캐리 두 항 · 실행 가능 방향 · 회계 방향 매핑 · 자산스왑 축 ·
화면 어휘), 어느 하나를 빠뜨려도 **예외는 안 난다** — 숫자가 조용히 반대로 선다.

그래서 검사는 「부호가 맞나」가 아니라 **불변량**으로 세운다. 계열 부호와
`TRADABLE_DIRS` 를 **같이** 뒤집으면 다음이 참이어야 한다:

    ① 계열     새 v = −(옛 v)              · 다리 차례가 [스왑, 현물/선물]
    ② 항등     다리0 − 다리1 = v           · 뒤집어도 닫힌다
    ③ z        |z| 불변                    · 표준화는 평행이동·부호에 불변
    ④ 실행     막히는 것은 **국고 매도**    · 부호가 아니라 거래가 기준이다
    ⑤ 거래     진입·청산 날짜가 한 건도 안 움직인다
    ⑥ 손익     총손익이 한 자도 안 갈린다
    ⑦ 캐리     `position = -1` 이 가리키는 거래가 바뀌었으므로 캐리도 부호를 바꾼다

⑤·⑥ 이 이 파일의 **핵심**이다. 같은 자료에서 같은 시점에 같은 거래를 잡아
같은 돈을 벌어야 규약 바꾸기가 «표기» 였다는 뜻이고, 안 맞으면 어딘가 부호를
하나 빠뜨린 것이다 — 그때 화면은 그럴듯하게 틀린 손익을 낸다.

## 왜 「옛 판」을 직접 안 부르나

옛 코드는 지웠다(두 벌을 남기면 언젠가 갈린다 — 이 리포의 그 규율). 대신
**뒤집기가 대칭이라는 성질**을 쓴다: 엔진에 `-v` 계열과 뒤집은 허용 방향을
넣으면 원래 계열과 같은 거래·같은 손익이 나와야 한다. 그것이 곧 ⑤·⑥ 이다.
"""
import pytest

from app import mr as mr_mod
from app import mrbacktest as mrbt
from app import mrcarry as mrc


def _sql_reachable() -> bool:
    try:
        mr_mod.series_points("BSS-3Y")
        return True
    except Exception:                                  # noqa: BLE001
        return False


live = pytest.mark.skipif(not _sql_reachable(), reason="MR 계열 SQL 에 닿지 않습니다")


# ── 규약 그 자체 (SQL 없이도 선다) ──────────────────────────────────────────

class TestConventionDeclared:
    def test_다리_이름이_스왑부터다(self):
        """차례가 곧 「다리0 − 다리1 = 값」의 차례다(`mrseries.points` 머리)."""
        assert mrc.LEG_NAMES["bss"] == ("IRS", "국고")
        assert mrc.LEG_NAMES["fsw"] == ("IRS", "선물")

    def test_정의_문장이_스왑부터다(self):
        assert mr_mod.KIND_DEFN["bss"] == "IRS − 국고"
        assert mr_mod.KIND_DEFN["fsw"] == "IRS − 선물내재"

    def test_막히는_것은_부호가_아니라_국고_매도다(self):
        """[OWNER 2026-08-25] 「BSS에서 숏은 없는거야,, 현물대차매도는 안할거거든」.

        규약을 뒤집으면 **같은 거래가 반대 부호로 불린다.** 금지는 부호가 아니라
        거래에 걸려 있으므로, 허용 방향도 같이 옮겨 앉아야 **같은 거래**가 계속
        막힌다. 한쪽만 뒤집으면 이 데스크가 못 하는 거래가 조용히 열린다 —
        그때 백테스트는 대차료 0 의 공매도로 늘 이긴다.
        """
        assert mr_mod.TRADABLE_DIRS["bss"] == (1,)
        legs = mr_mod.DIR_LEGS["bss"]
        assert "국고 매수" in legs["plus"]["legs"]      # 허용되는 쪽
        assert "국고 매도" in legs["minus"]["legs"]     # 막히는 쪽
        allowed = mr_mod.TRADABLE_DIRS["bss"][0]
        word = legs["plus" if allowed > 0 else "minus"]["legs"]
        assert "매도" not in word, f"실행 가능한 방향이 매도를 품었어요: {word}"

    def test_퓨처스왑도_같은_규약이다(self):
        legs = mr_mod.DIR_LEGS["fsw"]
        assert legs["plus"]["legs"] == "IRS 페이 · 선물 매수"
        assert legs["minus"]["legs"] == "IRS 리시브 · 선물 매도"


# ── 계열과 항등 ─────────────────────────────────────────────────────────────

@live
@pytest.mark.parametrize("sid", ["BSS-3Y", "BSS-1.5Y", "FSW-3Y"])
class TestSeriesIdentity:
    def test_다리_차이가_값이다(self, sid):
        """②. `(다리0 − 다리1) × 100 = v`. 뒤집어도 닫혀야 한다 — 부호를 한 곳만
        바꾸면 **여기가 제일 먼저 깨진다**(차례와 값이 따로 놀므로)."""
        pts = mr_mod.series_points(sid)["points"]
        assert pts, f"{sid}: 점이 없어요"
        bad = []
        for p in pts[-500:]:
            lg = p.get("legs")
            assert lg and len(lg) == 2, f"{sid}: 다리가 둘이 아니에요 — {lg}"
            if abs((lg[0] - lg[1]) * 100.0 - p["v"]) > 1e-3:
                bad.append(p["t"])
        assert not bad, f"{sid}: 다리 − 다리 ≠ 값 인 날 {len(bad)}건 (예 {bad[:3]})"

    def test_스왑이_앞이다(self, sid):
        """①. 다리0 이 스왑이어야 한다. 원화 IRS 는 국고보다 **높게** 서는 것이
        보통이라 그 자체로는 판정이 약하지만, 위 항등과 짝지으면 차례가 바뀌는
        순간 값의 부호가 통째로 뒤집혀 잡힌다. 여기서는 **이름**으로 직접 잰다.
        """
        kind = dict((s, k) for s, _l, k in mr_mod.SERIES)[sid]
        assert mrc.LEG_NAMES[kind][0] in ("IRS",)


# ── 뒤집기가 거래와 돈을 안 건드렸나 (이 파일의 핵심) ───────────────────────

@live
@pytest.mark.parametrize("sid", ["BSS-3Y", "BSS-2Y", "FSW-3Y"])
def test_뒤집어도_같은_거래_같은_손익(sid):
    """⑤⑥. 계열 부호와 허용 방향을 **같이** 뒤집으면 엔진이 같은 답을 내야 한다.

    이것이 오너에게 약속한 검정이다 — "뒤집은 뒤 그걸 검정으로 확인하겠습니다,
    안 맞으면 어딘가 부호를 하나 빠뜨린 것입니다."

    거래 목록은 `z` 에만 달려 있고 `z` 는 부호를 뒤집으면 부호만 뒤집힌다.
    허용 방향까지 같이 뒤집으면 **잡히는 봉이 같고 방향 라벨만 반대**가 된다.
    손익은 `방향 × Δ값` 이라 두 부호가 상쇄돼 **한 자도 안 갈린다**.
    """
    kind = dict((s, k) for s, _l, k in mr_mod.SERIES)[sid]
    pts = mr_mod.series_points(sid)["points"]
    dates = [p["t"] for p in pts]
    vals = [p["v"] for p in pts]
    allow = mr_mod.TRADABLE_DIRS[kind]

    now = mrbt.simulate(dates, vals, lookback=60, entry_z=2.0, exit_z=0.5,
                        stop_z=2.5, cost_bp=0.5, notional=1_000_000.0,
                        allow_dirs=allow)
    flipped = mrbt.simulate(dates, [-v for v in vals], lookback=60, entry_z=2.0,
                            exit_z=0.5, stop_z=2.5, cost_bp=0.5,
                            notional=1_000_000.0,
                            allow_dirs=tuple(-d for d in allow))

    a = [(t["entryDate"], t["exitDate"], t["direction"]) for t in now["trades"]]
    b = [(t["entryDate"], t["exitDate"], t["direction"]) for t in flipped["trades"]]
    assert len(a) == len(b), f"{sid}: 거래 수가 갈려요 — {len(a)} 대 {len(b)}"
    for (e1, x1, d1), (e2, x2, d2) in zip(a, b):
        assert (e1, x1) == (e2, x2), f"{sid}: 시점이 움직였어요 — {e1}/{x1} 대 {e2}/{x2}"
        assert d1 == -d2, f"{sid}: 방향이 반대가 아니에요 — {d1} 대 {d2}"

    # 돈. 원 단위 표라 1원이 기준이다(이 리포의 `LEG_RECON_TOL_KRW` 와 같은 자).
    for key in ("totalPnl", "maxDrawdown", "winRate", "numTrades"):
        x, y = now["summary"][key], flipped["summary"][key]
        assert abs(x - y) <= 1.0, f"{sid}: {key} 가 갈려요 — {x:,.4f} 대 {y:,.4f}"


@live
def test_z_의_절대값은_불변이다():
    """③. 표준화는 부호 뒤집기에 대해 `z → −z` 다. 격자가 고르는 조건이 |z| 위에
    서 있으므로(`mr._state`·`mrplan`) 규약 바꾸기가 **선택을 안 바꾼다**."""
    pts = mr_mod.series_points("BSS-3Y")["points"]
    vals = [p["v"] for p in pts]
    dates = [p["t"] for p in pts]
    a = mrbt.simulate(dates, vals, lookback=60, entry_z=2.0, exit_z=0.5,
                      stop_z=2.5, cost_bp=0.0, notional=1.0, allow_dirs=(-1, 1))
    b = mrbt.simulate(dates, [-v for v in vals], lookback=60, entry_z=2.0,
                      exit_z=0.5, stop_z=2.5, cost_bp=0.0, notional=1.0,
                      allow_dirs=(-1, 1))
    for pa, pb in zip(a["points"], b["points"]):
        if pa["z"] is None or pb["z"] is None:
            assert pa["z"] is None and pb["z"] is None
            continue
        assert abs(abs(pa["z"]) - abs(pb["z"])) < 1e-9


# ── 캐리 ────────────────────────────────────────────────────────────────────

@live
def test_캐리가_position_마이너스1_의_거래를_따라갔다():
    """⑦. `position = -1` 은 이제 **IRS 리시브 · 국고 매도**다.

    그 포지션의 캐리는 `(스왑 − CD) + (조달 − 국고)` 이고, 대수적으로
    `BSS − (CD − 조달)` 로 접힌다 — 그 항등을 `mrcarry.assert_identity` 가
    이미 잰다. 여기서는 **엔진에 들어가는 쪽**을 잰다: 다리 합이 총캐리와 같고,
    첫 다리(IRS)가 리시브라서 「스왑 − CD」의 부호로 선다.

    ⚠ 단위 사고가 이 자리에서 두 번 났다(2026-08-27 100배 · 2026-09-22 %/소수).
    연 캐리가 ±1%/년 밖이면 그건 산술이 아니라 단위다.
    """
    from app import funding as fnd

    sid = "BSS-3Y"
    pts = mr_mod.series_points(sid)["points"][-250:]
    dates = [p["t"] for p in pts]
    spec = fnd.FundingSpec(basis=fnd.DEFAULT_BASIS,
                           spread_bp=fnd.DEFAULT_SPREAD_BP).validated()
    legs = mrc.carry_rates_by_leg(sid, "bss", dates, spec)
    names = [n for n, _ in legs]
    assert names == ["IRS", "국고"]

    total, _defn = mrc.carry_rates(sid, "bss", dates, spec)
    for i in range(len(dates)):
        parts = [r[i] for _n, r in legs]
        if any(v is None for v in parts):
            assert total[i] is None
            continue
        assert abs(sum(parts) - total[i]) < 1e-9
        assert abs(total[i]) < 1.0, (
            f"{dates[i]}: 연 캐리 {total[i]:.3f}%/년 — 단위를 의심하세요"
        )


# ── 자산스왑 축 — BSS 의 실가격 회계가 쓰는 그 표 ───────────────────────────

@live
class TestAswAxis:
    """자산스왑은 **BSS 와 같은 수**다 — `ASW:KTB:3Y` 와 `BSS-3Y` 가 같은 출처에서
    같은 산술로 난다. 그래서 규약도 같이 움직여야 한다(`cashbond.asw_series`).
    """

    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as c:
            yield c

    def test_자산스왑이_BSS_와_같은_수다(self):
        """한쪽만 뒤집으면 **같은 화면 안에서** 계열 차트와 합계 줄이 반대 부호로
        선다 — 2026-09-22 전수조사가 「출처가 둘이면 하나가 멈춰도 모른다」로 잡은
        결함의 부호 판이다."""
        from app import cashbond as cb
        from app import creditmatrix as cm
        from app.main import _dataset

        mm = cm.load()
        ser = cb.asw_series(mm, _dataset, "KTB", "3Y")
        asw = {d.isoformat(): v for d, v in zip(mm.dates, ser) if v is not None}
        bss = mr_mod.series_points("BSS-3Y")["points"]
        checked = 0
        for p in bss[-60:]:
            if p["t"] not in asw:
                continue
            checked += 1
            assert abs(asw[p["t"]] - p["v"]) < 0.05, (
                f'{p["t"]}: 자산스왑 {asw[p["t"]]:+.2f} vs BSS {p["v"]:+.2f}'
            )
        assert checked >= 20, f"겹치는 날이 {checked}일뿐이에요"

    def test_스왑_없는_만기_칸은_비어_있다(self, client):
        """★2026-09-22 규약 뒤집기가 **드러낸 옛 결함**이다.

        민평에는 있고 IRS 에는 없는 만기가 셋이다(2.5Y·20Y·30Y). 자산스왑 북의
        대사표는 그 칸에 **민평 커브(%)를** 넣고 있었는데, 이 표의 Δ 배율은
        자산스왑에서 1.0(이미 bp)이라 그 칸만 «%를 bp 로 읽는» 100배 오차였고
        축도 채권 축이었다(합계 줄은 스프레드 축).

        찾은 방법이 기록할 값이다 — **다른 칸이 전부 부호를 뒤집는데 이 칸만 Δ 가
        그대로였다.** 규약을 뒤집는 일이 그 자리를 비춘 것이고, 돈(평가·손익)은
        한 자도 안 건드리는 칸이라 종전에는 아무도 안 밟았다(BSS-3Y 한 거래에서
        36행 합쳐 19,754원 · 같은 거래의 평가는 −1,071,219원).

        고친 방향은 이 리포의 공란 정책이다 — 못 재면 «—», 0 이나 근사로 안 채운다.
        """
        d = client.get("/api/mr/strategy?id=BSS-3Y&lookback=60&entryZ=2.0"
                       "&exitZ=0.5&stopZ=2.5").json()
        assert d["trades"], "거래가 없어서 대사표를 못 봐요"
        t = d["trades"][-1]
        j = client.get(f'/api/mr/recon?id=BSS-3Y&entry={t["entryT"]}'
                       f'&exit={t["exitT"]}&dir={t["dir"]}&notional=1000000').json()
        assert j.get("available") is not False, j.get("why")
        rec = j.get("recon") or j
        from app import cashbond as cb

        gap = [lb for lb in rec["tenors"] if lb not in cb.ASW_TENORS]
        assert gap, "스왑 없는 만기가 열에 없으면 이 시험은 아무것도 안 잽니다"
        for row in rec["rows"]:
            if row.get("carryover"):
                continue
            for lb in gap:
                assert row["dbp"].get(lb) is None, (
                    f'{row["t"]} {lb}: 스왑이 없는 만기에 Δ 가 섰어요 — '
                    f'{row["dbp"][lb]} (민평 %를 bp 로 읽는 그 자리)'
                )
                assert row["est"].get(lb) == 0, (
                    f'{row["t"]} {lb}: 못 재는 칸에 추정이 섰어요 — {row["est"][lb]}'
                )
