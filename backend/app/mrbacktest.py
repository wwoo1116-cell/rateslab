# -*- coding: utf-8 -*-
"""z-스코어 평균회귀 백테스트 — 첫 PMS(krw-fi-pms) entry-signals 창의 산술 이식.

원본: `krw-fi-pms/src/lib/math/backtest.ts::simulateMeanReversion` +
`rolling-stats.ts` — 그 자신이 `irs_pricer/services/spread_backtest_service.py`
의 이식이었으니 한 바퀴 돌아 다시 파이썬이 된 셈이다. **의미를 하나도 바꾸지
않는다** [OWNER 2026-08-25 — "맨처음 만들었던 PMS 의 그 창 참고해서 구현"]:

  - 트레일링 **포함** 창 lookback · **모집단** 표준편차(pstdev, two-pass) ·
    창 미달 또는 σ=0 → z 없음
  - 진입: |z| ≥ entryZ 역행 — z>0(비쌈) 숏, z≤0(쌈) 롱. 교차 감지 아님 —
    **레벨 검사**다. (2026-08-28: `entry_mode="touch"` 로 «밖에 있다가 밴드로
    복귀하는 봉» 규칙을 고를 수 있다 — 기본은 원본 그대로 `"level"` 이다.
    `_entry_signal` 에 두 규칙이 나란히 적혀 있다.)
  - `allow_dirs` — 부를 사람이 «이 방향은 우리가 못 한다» 를 말할 수 있는
    자리다(기본은 양방향이라 원본 산술 그대로). 막힌 방향의 진입 신호는
    **조용히 사라지지 않고** `blocked` 로 세어서 돌아온다.
  - 청산: 진입한 쪽에서 청산선을 **지났을 때**(롱 z ≥ −exitZ · 숏 z ≤ +exitZ).
    손절: |z| ≥ stopZ (z-발산 손절 — 돈이 아니라 z) ·
    둘 다 참이면 손절이 이긴다.
  - **당일 종가 체결**(다음 봉 지연 없음) · 진입 봉엔 MTM 없이 비용만 ·
    청산 봉은 그날 MTM 적립 후 비용 · 비용 = notional × costBp **편도**
  - 청산 봉 재진입 금지(다음 봉부터) · 포지션은 늘 ±1 단위 · z 없음이면
    보유 중 청산 검사 건너뜀 · 표본 끝의 미청산 포지션은 MTM 만 누적에
    남고 거래·승률·건수에는 안 잡힌다
  - Sharpe = mean(daily)/pstdev(daily)×√252 — **전 봉**(무포지션 0 포함),
    무위험 0 · MDD 는 누적 PnL 의 피크 대비 낙폭(원화, 양수 보고)

산술은 위가 전부다. 그 아래 **파생 둘**은 같은 수를 다시 말하는 것이라 규약을
바꾸지 않는다(적합성 벡터가 그대로 통과한다):

  - `open` · `summary.openPnl` — 표본 끝의 미청산 다리. 원본 규약대로 거래·
    승률·건수에는 **안** 들어가고, 그 사실을 화면이 말할 수 있게 밖으로만 낸다.
    승률 80% 가 «미청산 1건을 뺀 15건 중 12건» 이라는 뜻임을 카드가 스스로
    말하지 못하면, 열려 있는 손실 포지션이 승률에서 조용히 사라진다.
  - `summary.breakevenCostBp` — 총손익이 0 이 되는 편도 비용(`breakeven_cost_bp`).

이 산술이 NO-GO 로 닫힌 연구(Desktop\\bollinger-mr)의 규칙과 **다른 물건**임을
적어 둔다 — 저쪽은 밴드 재진입·익일 체결·bp 손익이고, 이쪽은 PMS 창의 재현이다.
그래서 이 엔진은 추천이 아니라 **재현 도구**다(화면 명구가 그 사실을 말한다).

적합성: `tests/test_mrbacktest.py` 의 LCG 픽스처가 PMS 가 못 박아 둔 KPI 벡터
(총손익 −3,580,000 등)와의 일치를 잰다 — 숫자가 어긋나면 이식이 의미를 바꾼
것이다.
"""
from __future__ import annotations

import math
from typing import Any


def _window_mean_std(values: list[float], start: int, end: int) -> tuple[float, float]:
    n = end - start
    s = 0.0
    for k in range(start, end):
        s += values[k]
    mean = s / n
    sq = 0.0
    for k in range(start, end):
        d = values[k] - mean
        sq += d * d
    return mean, math.sqrt(sq / n)


def rolling_series(values: list[float], lookback: int) -> dict[str, list]:
    """SMA·모집단 σ·z 를 한 번에 — 창이 차기 전은 None (원본 rollingSeries)."""
    n = len(values)
    mean: list[float | None] = [None] * n
    std: list[float | None] = [None] * n
    z: list[float | None] = [None] * n
    if lookback <= 0:
        return {"mean": mean, "std": std, "z": z}
    for i in range(lookback - 1, n):
        m, sd = _window_mean_std(values, i - lookback + 1, i + 1)
        mean[i] = m
        std[i] = sd
        z[i] = None if sd == 0 else (values[i] - m) / sd
    return {"mean": mean, "std": std, "z": z}


ENTRY_MODES = ("level", "touch")


def _entry_signal(z: list[float | None], i: int, entry_z: float,
                  mode: str) -> int | None:
    """그 봉의 진입 신호 — 방향(±1) 또는 없음(None).

    방향은 두 모드에서 같은 뜻이다: **평소 대비 너무 높으면 떨어진다에 걸고
    (숏 = −1), 너무 낮으면 롱(+1)** 이다. 다른 것은 «언제 그 판단을 실행에
    옮기는가» 뿐이다.

    ``level`` — |z| ≥ entryZ 인 **모든** 봉이 신호다(교차 감지가 아니라 레벨
        검사). 밴드를 뚫고 나가는 그 봉에 들어간다. 원본 PMS 규칙이고 기본값이다.

    ``touch`` — **밖에 있다가 밴드 선으로 되돌아오는** 봉이 신호다
        [OWNER 2026-08-28 — "진입 기준이 외부로 이탈했다가 다시 그 선을 터치할
        때"]. 직전 봉이 밖(|z| ≥ entryZ)이고 이 봉이 안(|z| < entryZ)이면
        복귀한 것이고, 방향은 **나갔던 쪽**이 정한다(위로 나갔으면 숏) — 복귀
        봉의 z 부호가 아니다. 그 둘은 갈릴 수 있다(위 밴드 밖에서 하루 만에
        중심선을 지나 아래로 내려오는 봉).

        측정면(`mr.py::_state`)이 이미 이 어휘로 판정한다 — 보드가 «재진입
        1일째» 라고 적는 바로 그 봉이 여기서 신호다. 두 화면이 같은 사건을
        다른 규칙으로 말하면 안 된다.

        이 규칙은 **거래를 늦추고 줄인다.** 늦추는 만큼 되돌림의 앞머리를
        내주고, 줄이는 만큼 「끝까지 벌어지기만 하는」 구간을 피한다. 어느
        쪽이 큰지는 계열마다 다르고, 그래서 판정이 아니라 **노브**다.

    warm-up(창 미달·σ=0)으로 z 가 없는 봉은 신호가 아니다 — 지표가 못 서는
    구간에 «조건이 맞았다» 고 할 수 없다. ``touch`` 는 직전 봉의 z 도 필요해서
    창 앞머리에서 한 봉 더 늦게 선다.
    """
    zi = z[i]
    if zi is None:
        return None
    if mode == "level":
        return None if abs(zi) < entry_z else (-1 if zi > 0 else 1)
    # touch — 직전 봉이 밖, 이 봉이 안.
    if abs(zi) >= entry_z or i == 0:
        return None
    zp = z[i - 1]
    if zp is None or abs(zp) < entry_z:
        return None
    return -1 if zp > 0 else 1


def simulate(dates: list[str], values: list[float], *, lookback: int,
             entry_z: float, exit_z: float, stop_z: float,
             cost_bp: float, notional: float,
             allow_dirs: tuple[int, ...] = (-1, 1),
             gate: list[Any] | None = None,
             carry: list[float] | None = None,
             entry_mode: str = "level",
             time_stop: int | None = None,
             cost_bp_series: list[float] | None = None,
             reverse_exit: bool = False,
             close_open_at_end: bool = False,
             tradable_dv: list[float] | None = None,
             roll: dict[str, list] | None = None) -> dict[str, Any]:
    """원본 simulateMeanReversion 의 바-루프 그대로. 반환 키도 그 어휘를 쓴다.

    `allow_dirs` 만 원본에 없던 자리다 — 실행할 수 있는 방향(+1 = 값이 오르면
    버는 쪽)의 목록이고, 기본값은 양방향이라 **기본 호출은 원본과 같은 수**를
    낸다(적합성 벡터가 그 사실을 잰다). 막힌 방향의 진입 신호는 세어서
    `blocked` 로 돌려준다 — 화면이 «몇 번을 못 들어갔는지» 를 말할 수 있어야
    하고, 말 없는 누락은 «신호가 없었다» 로 읽힌다.

    ## `gate` — 「z 문턱이 났는데도 안 들어가는」 자리

    봉마다의 참/거짓 목록이고, **진입에만** 듣는다. `None` 이면 게이트가 없는
    것이고 그때의 수는 예전과 완전히 같다.

    청산과 손절은 **게이트를 안 본다**. 이건 취향이 아니라 안전 규칙이다 —
    나가는 문까지 조건을 달면 조건이 꺼진 동안 포지션이 갇히고, 보유기간이
    규칙이 아니라 지표의 부산물이 된다. 들어갈 때만 고르고, 일단 들어갔으면
    원래 규칙대로 나온다.

    게이트가 지운 신호는 `gated` 로 **세어서 돌려준다**(`blocked` 와 같은 규율:
    구간 수와 일수 둘 다). 필터를 달면 거래 수가 줄고 승률은 거의 반드시
    올라가므로, 몇 건이 사라졌는지를 화면이 말하지 못하면 그 승률은 읽는 사람을
    속인다. `blocked`(방향 때문에 못 하는 거래)와 따로 세는 이유도 그것이다 —
    방향은 이 데스크의 제약이고 게이트는 **우리가 고른 것**이라, 둘을 한
    숫자로 합치면 선택의 대가가 제약 뒤에 숨는다.

    warm-up 으로 아직 값이 없는 봉(`None`)은 거짓으로 친다 — 지표가 못 서는
    구간에 «조건이 맞았다» 고 할 수는 없다. 다만 그것도 `gated` 에 세므로
    창 앞머리에서 몇 건이 그렇게 빠졌는지가 숫자로 남는다.

    ## `entry_mode` — 「언제 실행에 옮기는가」

    `"level"`(기본) 은 원본 PMS 규칙이고, `"touch"` 는 밖에 있다가 밴드로
    복귀하는 봉에 들어간다. 규칙 둘의 전문은 `_entry_signal` 에 있다. 기본값이
    `"level"` 이라 **인자를 안 주면 예전과 완전히 같은 수**다(적합성 벡터가
    그것을 잰다).

    청산·손절은 모드를 안 본다. 나가는 문의 규칙을 진입 규칙에 매달면 모드를
    바꿀 때마다 보유기간의 뜻이 같이 흔들려, 두 판을 나란히 놓고 비교할 수
    없게 된다. **한 번에 하나만 바꾼다.**

    ## 실전 운용 쪽으로 여는 손잡이 넷 [OWNER 2026-08-28]

    넷 다 **기본값이 꺼짐**이라, 안 주면 원본 PMS 산술 그대로다(적합성 벡터가
    그것을 잰다). 하나씩 켜서 무엇이 얼마를 바꾸는지 잴 수 있게 따로 둔다.

      `time_stop`        진입 후 N봉이 지나면 손익 불문 강제 청산. **z 를 안 본다** —
                         시간은 지표가 서든 말든 흐르고, 지표가 비는 구간에
                         포지션이 갇히는 것을 막는 것이 이 문의 일이다.
      `cost_bp_series`   봉마다의 **편도** 비용(bp). 주면 `cost_bp` 를 이긴다.
                         z 가 문턱을 넘는 봉은 호가가 벌어져 있는 봉이므로,
                         평시 호가를 상수로 쓰면 진입 비용이 조직적으로 싸다.
      `reverse_exit`     반대 방향 진입 신호를 **나가는 문**으로 쓴다. 이 데스크는
                         그 방향으로 못 들어가므로(현물 대차매도 불가) 신호를
                         버리거나 나가는 데 쓰거나 둘 중 하나인데, 버리면
                         「전제가 뒤집혔다」는 사실까지 같이 버린다.
      `close_open_at_end` 표본 끝의 미청산 다리를 **거래로 센다**(청산 비용 없음,
                         `exitReason="open"`). 총손익·MDD 는 이미 미청산을 지고
                         있고, 빠져 있던 것은 승률·거래 수·보유기간이다.

    ## `carry` — 두 다리의 중간 현금흐름 [OWNER 2026-08-27 — "중간에 CF는
       상쇄되는건가?"]

    **안 상쇄된다.** 국고 매수 + IRS 페이의 중간 현금흐름을 적으면

        국고 매수 :  + 쿠폰 − 조달              ≈ +(국고금리 − 조달)
        IRS 페이  :  − 고정  + CD 91일          ≈ +(CD − 스왑고정)
        ────────────────────────────────────────────────────────
        합계      ≈ (국고 − 스왑) + (CD − 조달) =  BSS + (CD − 조달)

    스프레드 자체와 «CD·조달 베이시스» 가 남는다. 원본 PMS 의 산술에는 그 항이
    없다 — 손익이 스프레드 변화뿐이다. 그래서 여기 **선택 인자**로 둔다:
    `None` 이면 예전과 완전히 같은 수이고(적합성 벡터가 그것을 잰다), 주면
    보유 중인 봉마다 더해진다.

    단위는 **봉당 원(₩)**, 부호는 **`position = -1`(국고 매수 · IRS 페이) 기준**
    이다. 엔진은 `-position` 을 곱하므로 반대 방향에서는 부호가 뒤집힌다 —
    같은 베이시스를 반대로 무는 것이 맞다.

    쌓이는 자리는 **MTM 과 같다**: 진입 봉에는 안 붙고(그 봉엔 아직 하루를 안
    들고 있었다), 청산 봉에는 붙는다(전 봉 종가부터 그날 종가까지 들고 있었다).
    """
    if entry_mode not in ("level", "touch"):
        raise ValueError(f"entry_mode 는 level|touch 다: {entry_mode!r}")

    n = len(values)
    # `roll` 은 **캐시 손잡이**다 — 산술이 아니라 «이미 잰 것을 다시 안 잰다».
    # 안 주면 여기서 잰다(원본과 완전히 같은 수, 적합성 벡터가 그것을 잰다).
    #
    # 근거는 최적화 격자다: 162칸이 룩백 셋을 나눠 쓰는데 `rolling_series` 가
    # 칸마다 다시 도니 그 함수 하나가 격자 시간의 63%였다(실측 2026-09-04,
    # 3,000봉: 20일 5.9ms · 60일 14.7ms · 120일 27.5ms × 54칸씩 = 2.6s/4.1s).
    # 룩백이 같으면 결과가 같은 순수 함수라, 부르는 쪽이 한 번 재서 나눠 준다.
    roll = rolling_series(values, lookback) if roll is None else roll
    z = roll["z"]

    # ── 봉마다 **거래 가능한** Δ [OWNER 2026-09-02 — "롤일 Δ 를 0 으로 마스크"] ──
    #
    # 기본은 계열의 차분 그대로다(`tradable_dv=None`) — 원본 PMS 와 완전히 같은
    # 수이고 적합성 벡터가 그것을 잰다. 선물·퓨처스왑처럼 **계약이 갈리는 날의
    # 차분을 아무도 실현하지 못하는** 계열만 그 봉을 0 으로 받아 온다
    # (`futures.roll_days` 가 그 날을 정하고 `main._mr_leg` 이 넘긴다).
    #
    # 왜 계열을 안 고치고 Δ 를 따로 받나: 수준(z·밴드·진입 레벨·표시)은 벤더
    # 내재금리가 정본이라 그대로 둬야 하고, 뒤로 조정한 계열을 쓰면 그 수준이
    # 무의미해진다(`futures.FuturesSeries` 머리의 규약). **수준과 손익은 다른
    # 계열 위에 설 수 있다** — 그 사실을 이 인자 하나로 적는다.
    if tradable_dv is not None and len(tradable_dv) != n:
        raise ValueError(f"tradable_dv 길이가 값과 달라요: {len(tradable_dv)} ≠ {n}")
    dv_bar = ([0.0] + [values[i] - values[i - 1] for i in range(1, n)]
              if tradable_dv is None else list(tradable_dv))

    def cost_at(i: int) -> float:
        """그 봉의 **편도** 비용(₩). 경로가 주어지면 그것이 이긴다."""
        return notional * (cost_bp if cost_bp_series is None else cost_bp_series[i])

    points: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []

    position = 0
    entry_idx: int | None = None
    entry_z_val: float | None = None
    entry_run: tuple[int, float] | None = None
    trade_pnl = 0.0
    # 거래 하나의 삼분해 — 평가·캐리·비용. 셋의 합이 그 거래의 손익이고,
    # 화면의 대사표가 그 항등을 잰다(이 앱의 3분해·4분해와 같은 문법).
    trade_mtm = 0.0
    trade_carry = 0.0
    trade_cost = 0.0
    cumulative = 0.0
    # 비용을 문 횟수 — 진입 한 번·청산 한 번이 각각 편도 하나다. 손익분기
    # 비용을 닫힌형으로 풀려면 이 수가 필요하고, 표본 끝의 미청산 다리는
    # 진입만 물었으므로 청산 수(=거래 수)와 따로 세야 한다.
    entry_events = 0
    # 막힌 진입 — 일수와 «구간» 둘 다 센다. 열흘 내리 막힌 것은 열 번이 아니라
    # 한 번 못 들어간 것이고, 그 둘을 한 숫자로 말하면 어느 쪽이든 거짓이 된다.
    blocked_days = 0
    blocked_spells = 0
    blocked_prev = False
    # 게이트가 지운 신호 — 방향 때문에 못 한 것(blocked)과 **따로** 센다.
    gated_days = 0
    gated_spells = 0
    gated_prev = False
    # ── 밴드 밖 구간 ─────────────────────────────────────────────────────────
    # 「언제 나갔고 얼마나 벌어졌나」 — 진입 한 줄이 그 사실을 지고 다니게 한다.
    # `touch` 모드에서는 진입 봉의 z 가 밴드 선 언저리라, 그 수만으로는 무엇을
    # 보고 들어갔는지 화면이 말할 수 없다(위로 4σ 까지 갔다 온 것과 2.01σ 를
    # 살짝 넘었다 온 것이 같은 줄로 보인다).
    cur_start: int | None = None   # 지금 이어지는 이탈 구간의 첫 봉
    cur_peak: float | None = None  # 그 구간의 |z| 최대(부호 유지)
    cur_side = 0
    prev_run: tuple[int, float] | None = None  # 방금 끝난 이탈 구간
    out_run = 0                    # 지금 봉까지 연속 며칠째 밖인가(안이면 0)

    for i in range(n):
        daily_pnl = 0.0
        # 그 봉의 MTM 을 곱한 바로 그 포지션 — 봉이 끝난 뒤의 `position` 과
        # **다르다**(진입 봉은 0, 청산 봉은 ±1). 백테스트 대사표가 「전일
        # 종가 KRD」를 싣는 것과 같은 이유다: 한 줄 안에서 감도 × 변화 = 평가
        # 가 닫혀야 눈이 위 줄로 오갈 일이 없다.
        hold = position
        zi = z[i]
        # 이 봉이 끝난 시점의 «그 거래» 누적 — 대사표의 세로합을 줄마다 적는다.
        # 청산 봉에서는 확정된 거래 손익이고, 무포지션이면 0 이다.
        bar_trade = 0.0

        # 이탈 구간 장부 — 신호를 내기 **전에** 갱신한다.
        side = 0 if zi is None or abs(zi) < entry_z else (1 if zi > 0 else -1)
        if side != 0:
            if side != cur_side:
                cur_start, cur_peak, cur_side = i, zi, side
                out_run = 0
            elif cur_peak is None or abs(zi) > abs(cur_peak):
                cur_peak = zi
            out_run += 1
        elif cur_side != 0:
            prev_run = (cur_start, cur_peak)  # type: ignore[assignment]
            cur_start = cur_peak = None
            cur_side = 0
            out_run = 0
        else:
            out_run = 0

        # 진입 신호는 **봉 머리에서** 낸다 — 그 봉에 청산이 나도 `want` 는
        # 여전히 «들어오기 전» 의 판정이라, 청산 봉 재진입 금지가 구조로
        # 지켜진다(원본 규약). 보유 중이면 아예 묻지 않는다.
        want = None if hold != 0 else _entry_signal(z, i, entry_z, entry_mode)
        bar_mtm = 0.0
        bar_carry = 0.0
        bar_cost = 0.0
        blocked_now = False
        gated_now = False

        if position != 0:
            mtm = position * notional * dv_bar[i]
            daily_pnl += mtm
            trade_mtm += mtm
            bar_mtm = mtm
            if carry is not None:
                # 부호 기준은 `position = -1`(국고 매수 · IRS 페이).
                c = -position * carry[i]
                daily_pnl += c
                trade_carry += c
                bar_carry = c
            trade_pnl += daily_pnl
            bar_trade = trade_pnl

            # ── 나가는 문 넷 — **우선순위가 곧 이름**이다 ──────────────────
            # 손절 > 청산 > 역신호 > 타임스탑. 같은 봉에 둘이 참이면 위엣것이
            # 이름을 갖는다: 손절 조건에서 나간 것을 「타임스탑」이라 적으면
            # 사후에 원인을 셀 수 없다.
            #
            # 타임스탑만 z 를 안 본다 — 시간은 지표가 서든 말든 흐른다.
            # 지표가 비는 구간에 포지션이 갇히는 것을 막는 것이 이 문의 일이다.
            should_stop = zi is not None and abs(zi) >= stop_z
            # ── 청산은 **방향을 본다** [OWNER 2026-09-22 · 논리 수리] ──────
            #
            # > "청산라인이 0 sigma라는건 0 sigma를 뚫고가면 청산하겠다는거야.
            # >  청산 라인 자체가 존재하지 않는게 아니라"
            #
            # 종전 규칙은 `|z| ≤ exitZ` 였다. 이건 «청산선을 향해 돌아왔나» 가
            # 아니라 «지금 중심 근처인가» 라서, 두 자리에서 틀린다:
            #
            #   ① `exitZ = 0` 이면 z 가 **정확히 0** 인 날에만 열린다 — 일별
            #      표본에서는 사실상 문이 없다. 그래서 IRC-3Y-10Y 가 442일째
            #      들고 있었다. 프리셋에 0 을 둔 것이 잘못이 아니라 **0 의 뜻을
            #      코드가 잘못 읽고 있었다.**
            #   ② 아래에서 들어간 포지션이 위로 **지나쳐 버리면**(z: −2.5 → +1.0)
            #      되돌림은 이미 끝났는데 `|z| ≤ exitZ` 는 거짓이라 계속 들고 있다.
            #
            # 두 문제의 뿌리가 같다 — 청산선은 **넘어가는 선**이지 구간이 아니다.
            # 그래서 진입한 쪽에서 그 선을 지났는지를 묻는다:
            #
            #     롱(아래에서 진입) → z ≥ −exitZ
            #     숏(위에서 진입)   → z ≤ +exitZ
            #
            # `exitZ > 0` 에서는 종전과 «거의» 같다(지나쳐 버린 봉에서만 갈린다).
            # `exitZ = 0` 에서는 문이 처음으로 열린다.
            should_exit = zi is not None and (
                zi >= -exit_z if position > 0 else zi <= exit_z)
            # 역신호 = 지금 무포지션이었다면 **반대 방향**으로 들어갔을 봉.
            # 이 데스크는 그 방향으로 못 들어가므로(현물 대차매도 불가) 진입에
            # 쓸 수 없다. 대신 «전제가 뒤집혔다» 는 사실로 읽고 나온다.
            rev = _entry_signal(z, i, entry_z, entry_mode) if reverse_exit else None
            should_rev = rev is not None and rev != position
            should_time = time_stop is not None and (i - entry_idx) >= time_stop
            if should_stop or should_exit or should_rev or should_time:
                exit_cost = cost_at(i)
                daily_pnl -= exit_cost
                trade_pnl -= exit_cost
                trade_cost -= exit_cost
                bar_cost = -exit_cost
                trades.append({
                    "entryDate": dates[entry_idx],
                    "exitDate": dates[i],
                    "direction": position,
                    "entryZ": entry_z_val,
                    "exitZ": zi,
                    "entryValue": values[entry_idx],
                    "exitValue": values[i],
                    # 보유 동안의 총 변화 — 대사표 「합계」 줄의 Δ 칸이다.
                    # 줄마다의 Δ 를 세로로 더한 값과 같아야 한다.
                    # **거래 가능한** Δ 의 합이다: `tradable_dv` 가 없으면
                    # `values[i] − values[entry_idx]` 와 정확히 같고, 있으면
                    # 마스크된 봉만큼 그것과 갈린다(그 봉 수가 `masked`).
                    "dv": sum(dv_bar[k] for k in range(entry_idx + 1, i + 1)),
                    "masked": sum(1 for k in range(entry_idx + 1, i + 1)
                                  if dv_bar[k] != values[k] - values[k - 1]),
                    "pnl": trade_pnl,
                    # 대사용 삼분해 — 합이 `pnl` 과 같아야 한다.
                    "mtm": trade_mtm,
                    "carry": trade_carry,
                    "cost": trade_cost,
                    "bars": i - entry_idx,
                    # 진입 직전의 밴드 밖 구간 — 며칠 나가 있었고 얼마나
                    # 벌어졌는가. `level` 이면 outDays 는 늘 1 이다.
                    "outFrom": dates[entry_run[0]] if entry_run else None,
                    "outDays": (entry_idx - entry_run[0] + (0 if entry_mode == "touch" else 1))
                               if entry_run else None,
                    "peakZ": entry_run[1] if entry_run else None,
                    "exitReason": ("stop" if should_stop else "exit" if should_exit
                                   else "reverse" if should_rev else "time"),
                })
                bar_trade = trade_pnl
                position = 0
                entry_idx = None
                entry_z_val = None
                entry_run = None
                trade_pnl = 0.0
                trade_mtm = trade_carry = trade_cost = 0.0
        elif want is not None:
            if want not in allow_dirs:
                # 못 하는 거래는 안 한 것으로 둔다 — 비용도 손익도 없다.
                # 방향을 **먼저** 본다: 애초에 실행 불가능한 신호를 두고
                # 「게이트가 걸렀다」고 세면 필터의 공이 부풀려진다.
                blocked_now = True
                blocked_days += 1
                if not blocked_prev:
                    blocked_spells += 1
            elif gate is not None and not gate[i]:
                # 할 수 있었는데 **우리가 안 한** 거래. 여기 세는 것이 필터의 대가다.
                gated_now = True
                gated_days += 1
                if not gated_prev:
                    gated_spells += 1
            else:
                position = want
                entry_idx = i
                entry_z_val = zi
                # 무엇을 보고 들어갔는가 — `level` 은 지금 이어지는 구간(이 봉이
                # 그 첫 봉이다), `touch` 는 방금 끝난 구간이다.
                run = (cur_start, cur_peak) if entry_mode == "level" else prev_run
                entry_run = run if run and run[0] is not None else None
                entry_events += 1
                entry_cost = cost_at(i)
                daily_pnl -= entry_cost
                trade_pnl = daily_pnl
                trade_mtm = 0.0
                trade_carry = 0.0
                trade_cost = -entry_cost
                bar_cost = -entry_cost
                bar_trade = trade_pnl

        blocked_prev = blocked_now
        gated_prev = gated_now
        cumulative += daily_pnl
        points.append({
            "date": dates[i], "value": values[i], "z": zi,
            "position": position, "hold": hold, "dailyPnl": daily_pnl,
            # 그날의 분해 — 거래 한 줄을 눌렀을 때 **날짜별 대사**가 이걸 편다
            # (백테스트 창의 「일별 대사」와 같은 문법). 셋의 합이 `dailyPnl` 이다.
            "mtm": bar_mtm, "barCarry": bar_carry, "barCost": bar_cost,
            # 거래 안에서의 누적 — 마지막 줄이 그 거래의 손익과 같아야 한다.
            "tradePnl": bar_trade,
            # 밴드 밖 여부(부호 = 나간 쪽)와 연속 일수 — 화면이 「지금 어디에
            # 서 있나」를 말할 수 있게. 측정면 `mr._state` 와 같은 어휘다.
            "out": side, "outRun": out_run,
            "cumulativePnl": cumulative,
        })

    # 표본 끝의 미청산 다리 — 누적에는 있고 거래·승률·건수에는 없다(원본 규약).
    # 규약을 바꾸지 않고 «없다는 사실» 만 밖으로 낸다: 화면이 승률 옆에 그것을
    # 말할 수 있어야 80% 가 «15건 중 12건» 이라는 뜻으로 읽힌다.
    open_leg = None
    if position != 0 and entry_idx is not None:
        open_leg = {"entryDate": dates[entry_idx], "direction": position,
                    "entryIdx": entry_idx,
                    "entryZ": entry_z_val, "entryValue": values[entry_idx],
                    "pnl": trade_pnl, "mtm": trade_mtm, "carry": trade_carry,
                    "cost": trade_cost, "bars": n - 1 - entry_idx,
                    "outFrom": dates[entry_run[0]] if entry_run else None,
                    "outDays": (entry_idx - entry_run[0]
                                + (0 if entry_mode == "touch" else 1)) if entry_run else None,
                    "peakZ": entry_run[1] if entry_run else None}

    # ── 미청산 다리를 거래로 세는 자리 [OWNER 2026-08-28 — 「승률 100% 착시」] ──
    #
    # 총손익과 MDD 는 **이미** 미청산을 실시간으로 지고 있다: 누적은 보유 중인
    # 봉마다 MTM 을 더하므로 열려 있는 손실이 곡선에 그대로 찍히고 낙폭에 든다.
    # 빠져 있던 것은 **승률·거래 수·보유기간** 뿐이었고, 그래서 「12승 0패」
    # 옆에서 −600만짜리 열린 다리가 조용히 사라졌다.
    #
    # 이 스위치는 그 다리를 마지막 봉의 평가로 **거래 목록에 넣는다**. 청산
    # 비용은 안 문다 — 팔지 않았으니 없는 비용이다. `exitReason="open"` 으로
    # 표시해 사후에 걸러낼 수 있게 둔다.
    if close_open_at_end and open_leg is not None:
        trades = trades + [{
            "entryDate": open_leg["entryDate"], "exitDate": dates[-1],
            "direction": open_leg["direction"], "entryZ": open_leg["entryZ"],
            "exitZ": z[-1], "entryValue": open_leg["entryValue"],
            "exitValue": values[-1],
            "dv": sum(dv_bar[k] for k in range(open_leg["entryIdx"] + 1, len(values))),
            "masked": sum(1 for k in range(open_leg["entryIdx"] + 1, len(values))
                          if dv_bar[k] != values[k] - values[k - 1]),
            "pnl": open_leg["pnl"], "mtm": open_leg["mtm"],
            "carry": open_leg["carry"], "cost": open_leg["cost"],
            "bars": open_leg["bars"], "outFrom": open_leg["outFrom"],
            "outDays": open_leg["outDays"], "peakZ": open_leg["peakZ"],
            "exitReason": "open",
        }]

    summary = summarize(points, trades)
    summary["openPnl"] = open_leg["pnl"] if open_leg else None
    # 비용 경로를 주면 「편도 몇 bp 까지 견디는가」가 한 숫자로 안 나온다 —
    # 봉마다 다른 값이기 때문이다. 대신 **그 경로의 몇 배까지 견디는가**를 답한다.
    # 거래 목록이 z 에만 달려 있어 총손익이 여전히 비용의 정확한 일차식이라,
    # 둘 다 닫힌형이다.
    cost_events = entry_events + len([t for t in trades if t["exitReason"] != "open"])
    if cost_bp_series is None:
        summary["breakevenCostBp"] = breakeven_cost_bp(
            summary["totalPnl"], cost_bp, notional, cost_events)
        summary["breakevenCostMult"] = None
    else:
        # 실제로 문 돈 전부 — **봉에서** 센다. 거래 목록에서 세면 표본 끝
        # 미청산 다리의 진입 비용이 빠져 답이 틀린다(실측: 잔차 878,409원).
        paid = -sum(p["barCost"] for p in points)
        summary["breakevenCostBp"] = None
        summary["breakevenCostMult"] = (
            None if paid <= 0 else 1.0 + summary["totalPnl"] / paid)

    return {"points": points, "trades": trades,
            "summary": summary, "roll": roll, "open": open_leg,
            "blocked": {"spells": blocked_spells, "days": blocked_days},
            "gated": {"spells": gated_spells, "days": gated_days}}


def breakeven_cost_bp(total_pnl: float, cost_bp: float, notional: float,
                      cost_events: int) -> float | None:
    """총손익이 0 이 되는 편도 비용(bp) — 닫힌형이다.

    진입·청산·손절 판정이 **z 에만** 달려 있어 비용을 올려도 거래 목록이 안
    바뀐다. 그래서 총손익은 비용의 정확한 일차식이고, 기울기는 비용을 문 횟수
    × 명목이다:  PnL(c) = PnL(c₀) − notional·(c − c₀)·events.

    노브를 돌려 가며 0 을 찾는 대신 한 번에 답한다 — 「이 구성이 얼마짜리
    호가폭까지 견디는가」 는 비용 노브의 값보다 먼저 알아야 할 사실이다.
    음수가 나오면(이미 손실) None 이 아니라 그 음수를 준다 — «비용이 0 이어도
    안 된다» 는 것도 답이다.
    """
    if cost_events <= 0 or notional <= 0:
        return None
    return cost_bp + total_pnl / (notional * cost_events)


def summarize(points: list[dict], trades: list[dict]) -> dict[str, Any]:
    total_pnl = points[-1]["cumulativePnl"] if points else 0.0

    max_drawdown = 0.0
    running_max = -math.inf
    for pt in points:
        running_max = max(running_max, pt["cumulativePnl"])
        max_drawdown = max(max_drawdown, running_max - pt["cumulativePnl"])

    win_rate = (sum(1 for t in trades if t["pnl"] > 0) / len(trades)) if trades else None

    sharpe = None
    daily = [pt["dailyPnl"] for pt in points]
    if len(daily) >= 2:
        m = sum(daily) / len(daily)
        sd = math.sqrt(sum((x - m) ** 2 for x in daily) / len(daily))
        if sd != 0:
            sharpe = m / sd * math.sqrt(252)

    return {"totalPnl": total_pnl, "maxDrawdown": max_drawdown,
            "winRate": win_rate, "sharpe": sharpe, "numTrades": len(trades)}
