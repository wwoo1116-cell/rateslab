# -*- coding: utf-8 -*-
"""MR **계획면** — 「지금 어디에 있고, 얼마면 무엇을 하나」 (2026-09-21).

[OWNER 2026-09-21 · 시니어 트레이더 피드백] 종전 보드(`mr.py`)는 룩백·밴드 폭
알약이 정한 밴드 위의 **측정면**이었다: z·%B·상태와 진입 문턱 하나. 이 모듈은
같은 표를 **계획**으로 바꾼다 — 계열마다 격자가 고른 조건, 그 조건의 진입·청산·
손절 레벨, 그 조건이 지금 들고 있는 포지션, 그리고 지난 1년의 성적과 분해.

## 오너가 정한 것 넷 — 다시 묻지 말 것

1. **밴드는 계열마다 다르다.** 고정 (창, 배수)가 아니라 그 계열의 격자 1등 조건의
   밴드다. 화면 알약 둘은 그래서 내려갔다.
2. **조건도 성과도 지난 1년이다** [오후 정정 — 오전 결정은 「조건은 전체 표본」
   이었다]. 고르는 창과 채점하는 창이 같으므로 화면의 1년 손익은 **162칸 중 1등의
   값**이고, 그건 성과가 아니라 선택의 산물이다 — 화면이 그 사실을 적는다.
   (1년 창은 계열당 거래가 0~5건이라 162칸 순위가 잡음이라는 실측을 듣고 오너가
   그래도 1년으로 정했다. 되돌리는 손잡이는 `GRID_SPAN` 하나다.)
3. **청산·손절 레벨을 적는다.** 2026-09-09 의 「트리거는 진입 레벨까지」가 여기서
   뒤집혔다. **명목은 여전히 안 말한다** — 포지션 크기는 이 화면의 것이 아니다.
4. FSW 변동성 국면 플레이는 **측정 먼저**(`scripts/mr_fsw_volplay.py`), 화면 아님.

## 이 모듈은 DB 를 모른다

`leg_of`·`grid_of` 를 **받는다**(`main.py` 가 `_mr_leg`·`_mr_optimize` 를 꽂는다).
그래서 시험이 합성 계열로 이 산술 전부를 돌릴 수 있다(`tests/test_mrplan.py`) —
라우트를 타면 SQL·민평·조달이 딸려와 시험이 안 돈다.

## 왜 두 번 도나 — 격자는 회계 없이, 실행은 회계로

격자 162칸을 실가격(자산스왑 재가격)으로 매기면 계열 하나가 분 단위다. 그런데
`_mr_optimize` 는 `leg["r"]` 를 안 읽는다(봉·거래를 자기가 다시 시뮬한다) — 즉
**회계는 격자의 칸을 한 자도 안 바꾼다.** 그래서 격자용 실행은 `accounting=False`
로 돌리고, 고른 조건 하나만 회계를 붙여 다시 돈다. 카드가 말하는 돈은 늘 뒤엣것이다.

## 밴드를 여기서 다시 재지 않는다

`mr._assemble(bands=…)` 에 **엔진이 이미 잰 밴드**(`rolling_series` 의 mean ±
entryZ·std)를 넘긴다. 다시 재면 화면의 진입 문턱과 그 계열의 백테스트 진입이 다른
자리를 가리킬 수 있다 — 두 σ 규약이 갈려 있던 전례가 있다(2026-09-02 적대 대사).

⚠ **단위**: 엔진은 %-계열을 bp 로 환산해 돌린다(`main._mr_leg`). `_assemble` 과
레벨 산술은 **계열의 자기 단위**를 받아야 하므로 여기서 되돌린다 — 안 되돌리면
선물 계열의 거리만 100배가 된다.

⚠ **캐시 이름**: 계열마다 `mr-plan-{격자창}-{sid}` 로 굽는다(`cache_name`). 격자 창을
이름에 박는 이유는 그 머리에. 페이로드의 **모양**을 바꿀 때는 `cache.SCHEMA_VERSION`
을 올려야 한다 — 이름이 새것이라 지금은 안 올렸다.
"""
from __future__ import annotations

from typing import Any, Callable

from . import mr as mr_mod
from . import mrmetrics as mrm

#: 순위 기준 — 화면(`src/mr/api.ts::MR_RANK_KEYS`)의 기본과 **같은 값**이어야 한다
#: [OWNER 2026-09-09 「CDaR 비로 옮긴다」]. 갈리면 계획면의 1등과 전략 실험 창의
#: 1등이 다른 칸이 되고, 창을 열 때마다 조건이 바뀐 것처럼 보인다.
#: ★**PnL 과 MDD** 다 [OWNER 2026-10-15 — "이제 우선순위는 PnL과 MDD야"].
#:
#: Calmar = 연환산 손익 ÷ 최대낙폭 — 그 둘을 한 수로 쓰는 자리다. 2026-09-09 에
#: 이 자리를 CDaR 비에 넘긴 근거는 「**MaxDD 는 단일관측 추정량**」이었고 그 말은
#: 그대로 참이다. 되돌리는 근거는 **CDaR 의 우위가 이 창에서 없다는 실측**이다
#: [전수조사 2026-10-15]: 1년 창에서 채택된 조건의 **6/25 가 사건 하나** 위에 서
#: 있었다(꼬리 13점이 전부 한 낙폭 구간에서 왔다). 사건이 하나면 CDaR 도 사실상
#: 단일관측이라, 둘 중 하나가 나은 것이 아니라 **둘 다 1년 창에서는 관측이 얇다.**
#: 그러면 읽는 사람이 되짚을 수 있는 쪽(PnL ÷ MDD)이 낫다.
#:
#: ⚠ 총손익 **단독**은 기준이 아니다 — 표본을 반 갈라 재니 그 기준의 1~5등이
#: 뒤절반에서 162칸 중 71~116등이고 중앙 −2,000만원 대 전체 +4,060만원이었다
#: (`src/mr/api.ts::MR_RANK_KEYS` 의 그 ⚠ · `scripts/mr_grid_oos.py`). 위험을 안
#: 보는 기준이라 낙폭이 큰 칸이 그대로 1등이 된다. Calmar 는 그 분모를 세운다.
#:
#: ⚠ 낙폭 **단독**도 기준이 아니다 — 「가장 안 아팠던 구성」은 «아무것도 안 한
#: 구성» 이라 1등이 늘 거래 0 건이 된다(그 목록 머리의 그 문단).
PLAN_RANK_KEY = "calmar"

#: 성과·트리거를 채점하는 창 — 지난 1년. `mrmetrics.SPANS` 의 그 키·그 달수다.
PLAN_SPAN = "1y"
PLAN_SPAN_MONTHS = 12

#: 조건을 고르는 창 — **채점하는 창과 같다** [OWNER 2026-09-21 오후 — "이것도
#: 그냥 표본도 1년으로 하죠?"]. 오전 결정은 「전체 표본」이었고 근거는 거래 수였다
#: (1년 창은 계열당 0~5건이라 162칸 순위가 잡음이다) — 오너가 그 답을 듣고 1년으로
#: 바꿨다.
#:
#: ⚠ **바뀐 것은 자유도가 아니라 「무엇을 주장할 수 있나」다.** 고른 창과 잰 창이
#: 같으므로 화면의 1년 손익은 **162칸 중 가장 좋은 칸의 값**이다 — 그 수는 성과가
#: 아니라 **선택의 산물**이고, 표본밖 기대값이 아니다. 화면 각주가 그 사실을
#: 적는다(`MrPage` 조건 바). 표본밖으로 보고 싶으면 이 값을 "all" 로 되돌리면
#: 되고, 그때는 1년 성과가 선택과 분리된다.
GRID_SPAN = PLAN_SPAN

#: 격자를 돌릴 때의 기준 노브 — 화면 기본값(`src/mr/api.ts::MR_STRATEGY_DEFAULTS`)과
#: 같다. 격자가 이 다섯을 흔들므로 «어디서 출발했나» 이상의 뜻은 없지만, 격자가
#: 순위를 못 매긴 계열에서는 이 칸이 그대로 답이 된다(그때 `fallback` 이 선다).
BASE_KNOBS: dict[str, Any] = {
    "lookback": 60, "entryZ": 2.0, "exitZ": 0.5, "stopZ": 2.5, "entryMode": "level",
}

#: 비용·Delta — 격자가 **안 흔드는** 값이다(그날 그 종목의 호가폭과 이 데스크의
#: 포지션 크기라 최적화할 대상이 아니다 — `mr.STRATEGY_PRESETS` 머리의 그 규율).
COST_BP = 0.5
NOTIONAL = 1_000_000.0


def cost_multiple(sid: str) -> float:
    """계열 하나가 **한 번 거래에** 무는 비용의 배수(`COST_BP` 대비).

    ★**플라이만 2 다** [OWNER 2026-10-20]. 까닭은 「계열 1bp」와 「내가 옮기는
    위험」이 플라이에서만 갈리기 때문이다. 윙 DV01 을 `w` 라 하면

        값의 규약 `2·벨리 − 윙둘` · 가중 벨리 2w · 윙 w 둘
        → 계열 1bp 가 버는 돈 = w          (엔진의 `NOTIONAL` 이 이 자리다)
        → 내가 내놓는 위험   = 페이 2w · 리시브 2w → **2w**

    비용은 뒤쪽에 붙으므로 계열 기준으로는 `0.5bp × 2 = 1.0bp` 다. 아웃라이트와
    커브는 둘이 같은 수라 배수가 1 이고, 그래서 **이 변화는 플라이에만 닿는다**.

    > [트레이더 2026-10-20] "이거 5th Trade 비용이 왜 250만원으로 잡힘?
    > 500만원이 맞는데" — 장부 `IRF-2Y-5Y-10Y`(벨리 1,000만원/bp · 윙 500 둘).

    장부 카드는 같은 사실을 **다리의 DV01** 로 센다(`paper.cost_dv01_of` — 페이
    쪽과 리시브 쪽 중 큰 쪽). 두 자리가 **한 사실의 두 표현**이라 한쪽만 고치면
    카드와 계획면이 같은 거래에 다른 돈을 매긴다(2026-10-15 에 닫았던 그 병).
    """
    return 2.0 if sid.startswith("IRF-") else 1.0

#: 1년의 영업일 — `universe.WINDOW` 의 그 수다. 엔진의 봉이 영업일이므로
#: 보유 봉수를 연으로 바꾸는 제수가 이것이다.
BARS_PER_YEAR = 252.0

#: 보유기간의 **중앙값**을 내려면 거래가 이만큼은 있어야 한다. 1년 창은 계열당
#: 0~5건이라(모듈 머리 §오너가 정한 것 2) 한 건짜리 중앙값은 그 한 건이다 —
#: 그런 수로 순기대를 세우면 「기대」가 아니라 일화다.
MIN_TRADES_FOR_HOLD = 2

#: 노브 다섯 — 격자 칸에서 이 열쇠만 꺼낸다.
KNOB_KEYS = ("lookback", "entryZ", "exitZ", "stopZ", "entryMode")

#: 1년 카드가 싣는 것. 전부 `mrmetrics.score` 의 열쇠다 — 여기서 다시 유도하지
#: 않는다(두 번째 정의 금지). `split` 이 그 구간의 **분해**이고, 화면은 그것을
#: 클릭 없이 세운다 [OWNER 2026-09-21 — "내가 클릭따로 안해도 바로 캐리, 롤다운,
#: 평가 등으로 분해"].
PERF_KEYS = ("from", "to", "days", "totalPnl", "maxDrawdown", "winRate",
             "numTrades",
             # ★**채택 기준** [OWNER 2026-10-15] — 이 수가 162칸 중 이 칸을 뽑았다.
             # 화면의 「채택 기준」 칸이 이것을 읽는다.
             "calmar",
             # CDaR 비는 **남긴다** — 전략 창이 고를 수 있는 여섯 중 하나이고,
             # 둘을 나란히 두면 「기준을 바꾸면 1등이 바뀐다」를 카드에서 본다.
             "cdarRatio",
             # ★순위 기준이 **몇 개의 사건 위에 서 있나** [전수조사 2026-10-15].
             # 평가층이 이미 내던 수인데 `mrmetrics` 가 버리고 있었다. 순위는
             # 안 바꾼다 — 적기만 한다(그 층의 ⚠ 를 그대로 지킨다).
             "cdarTailPoints", "cdarTailEpisodes", "cdarPointsPerEpisode",
             "cdarBars", "cdarWhy", "ddEpisodes",
             "split")


def cache_name(sid: str) -> str:
    """디스크 캐시 이름 — **격자 창을 이름에 박는다**.

    `GRID_SPAN` 을 바꾸면 조건이 통째로 달라지는데 페이로드의 «모양» 은 그대로라
    `SCHEMA_VERSION` 이 그것을 못 잡는다(그 상수는 모양을 잡는 물건이다). 이름에
    창을 넣으면 바꾼 날 옛 조건이 조용히 나가는 일이 없고, 다른 페이로드(예보·
    표면·유니버스)를 통째로 다시 굽는 값도 안 치른다.
    """
    return f"mr-plan-{GRID_SPAN}-{sid}"


def pick_cell(cells: list[dict], key: str = PLAN_RANK_KEY) -> dict | None:
    """격자의 1등 칸 — **못 잰 칸은 후보가 아니다**.

    프런트 `rankCells`(`src/mr/api.ts`)의 서버판이고 규약이 같다: `None` 은
    「그 구간에서 그 지표가 안 선다」이지 「0 이다」가 아니라서 0 으로 채워
    정렬하면 못 잰 칸이 한복판에 끼어든다. 여기서는 아예 건너뛴다.

    동점은 **격자 차례**가 이긴다(엄격한 `>` 비교) — 그래야 같은 자료에서 두 번
    부르면 같은 칸이 나온다. 후보가 하나도 없으면 `None` 이고, 부르는 쪽이 기본
    칸으로 떨어지며 그 사유를 화면에 적는다.
    """
    best: dict | None = None
    for c in cells:
        v = c.get(key)
        if v is None:
            continue
        if best is None or v > best[key]:
            best = c
    return best


def knobs_of(cell: dict) -> dict[str, Any]:
    """격자 칸 → 노브 다섯. 룩백은 **정수**다(엔진이 색인으로 쓴다)."""
    out = {k: cell[k] for k in KNOB_KEYS}
    out["lookback"] = int(out["lookback"])
    return out


def levels_for(kind: str, *, ma: float | None, sd: float | None, v: float,
               entry_z: float, exit_z: float, stop_z: float,
               scale: float) -> list[dict]:
    """오늘 밴드의 **진입·청산·손절 레벨** — 거래할 수 있는 방향마다 한 벌
    [OWNER 2026-09-21 — "청산 시점과 손절 시점을 데일리로 트리거 레벨로"].

    ## 계산이 아니라 번역이다

    엔진 규약을 레벨로 옮겨 적기만 한다(`mrbacktest.simulate` 의 그 세 문):

        진입  |z| ≥ entryZ 이고 **늘어난 쪽의 반대**에 건다
        청산  |z| ≤ exitZ
        손절  |z| ≥ stopZ

    z = (값 − 중심선)/σ 이므로 각 문턱은 `중심선 ± 배수·σ` 다. 방향이 정해지면
    부호도 하나로 정해진다:

        dir −1 (축소에 거는 쪽 · 값이 위로 늘어났을 때 들어간다)
            진입 = 중심선 + entryZ·σ   (그 위면 진입 자리)
            청산 = 중심선 + exitZ·σ    (거기까지 **내려오면** 청산)
            손절 = 중심선 + stopZ·σ    (거기까지 **더 오르면** 손절)
        dir +1 은 전부 반대쪽이다.

    ⚠ 청산 문턱은 `|z| ≤ exitZ` 라 반대편에도 선(−exitZ)이 있지만, 위에서
    내려오는 경로는 **+exitZ 를 먼저 지난다**. 그래서 방향마다 한 자리만 적는다.
    손절도 같은 이유로 진입한 쪽의 바깥 선 하나다.

    ## 여기 적는 것은 **들어가기 전의 이야기**다

    「이쪽으로 들어가면 저기서 나온다」 — 진입 레벨과, 그 진입에 딸린 청산·손절
    레벨이다. `entryGap` 만 거리를 적는다(단위 **bp** — 레벨은 계열의 자기 단위인데
    거리를 그 단위로 적으면 선물 계열에서만 100배 작은 수가 된다).

    **이미 들고 있는 다리의 청산·손절은 여기가 아니라 `position_of` 가 잰다.**
    엔진의 두 문은 `|z|` 위에 있어서 **방향이 아니라 지금 값이 어느 쪽인가**가
    정하는데, 들고 있는 다리는 중심선을 넘어가 있을 수 있다(실측 2026-09-21:
    FUT-KTB3 이 아래에서 진입해 지금 위쪽 +1.47σ 다). 그때 이 표의 수를 그대로
    쓰면 화면이 「청산선을 지났는데 왜 들고 있나」라고 말하게 된다.

    못 하는 방향은 **안 싣는다**(BSS 의 하단은 국고 매도라 이 데스크가 못 한다 —
    사유는 행의 `triggerBlocked` 가 따로 진다). 밴드가 못 서면(창 미달·σ=0) 빈
    목록이고, 화면은 「아직 못 재요」라고 적는다.
    """
    if ma is None or sd is None or sd <= 0:
        return []
    legs = mr_mod.DIR_LEGS[kind]
    out: list[dict] = []
    for dirn in mr_mod.TRADABLE_DIRS[kind]:
        word = legs["minus"] if dirn == -1 else legs["plus"]
        # 부호 하나가 두 방향을 다 적는다 — dir −1 은 위쪽 선들, +1 은 아래쪽.
        sign = -1.0 * dirn
        entry = ma + sign * entry_z * sd
        out.append({
            "dir": dirn,
            "side": "above" if dirn == -1 else "below",
            "short": word["short"], "legs": word["legs"],
            "entry": round(entry, 4),
            # 그 진입에 딸린 두 문 — 들어간 쪽에서 되돌아오면 청산, 더 벌어지면 손절.
            "exit": round(ma + sign * exit_z * sd, 4),
            "stop": round(ma + sign * stop_z * sd, 4),
            "entryGap": round(sign * (entry - v) * scale, 4),
            "entryReached": sign * (entry - v) <= 0,
        })
    return out


def exits_now(*, ma: float | None, sd: float | None, v: float,
              exit_z: float, stop_z: float, scale: float) -> dict | None:
    """**지금 들고 있는 다리의 나가는 문 둘** — 오늘 레벨로.

    엔진의 두 문은 방향을 안 본다:

        청산  |z| ≤ exitZ      손절  |z| ≥ stopZ

    그래서 문턱은 **지금 값이 중심선의 어느 쪽인가**가 정한다 — 위쪽이면 위쪽
    가장자리(중심선 + 배수·σ)가 먼저 닿는 선이다. 진입 방향으로 정하면 안 된다:
    들고 있는 동안 값이 중심선을 지나 반대쪽으로 갈 수 있고(실측 2026-09-21
    FUT-KTB3), 그때 진입 쪽 선은 이미 지나간 수라 화면이 스스로를 반박한다.

    거리(bp)의 뜻:

        exitGap  좁혀져야 하는 거리 — 중심선 쪽으로 이만큼 오면 청산이다
        stopGap  더 벌어질 수 있는 거리 — 이만큼 더 가면 손절이다

    **들고 있는 다리에서는 둘 다 양수다** — |z| 가 exitZ 와 stopZ 사이에 있기
    때문이다(밖이면 엔진이 이미 닫았다). 포지션이 없는 줄에서는 `exitGap` 이 음수일
    수 있고(값이 이미 청산 구간 안), 그건 결함이 아니라 「들어가 있었다면 벌써
    나왔을 자리」라는 뜻이다. 화면은 이 두 수를 **포지션이 있을 때만** 적는다.
    """
    if ma is None or sd is None or sd <= 0:
        return None
    z = (v - ma) / sd
    sign = 1.0 if z >= 0 else -1.0
    return {
        "side": "above" if z >= 0 else "below",
        "z": round(z, 4),
        "exit": round(ma + sign * exit_z * sd, 4),
        "stop": round(ma + sign * stop_z * sd, 4),
        "exitGap": round((abs(z) - exit_z) * sd * scale, 4),
        "stopGap": round((stop_z - abs(z)) * sd * scale, 4),
    }


def position_of(op: dict | None, *, kind: str, now: dict | None,
                disp: Callable[[float], float]) -> dict | None:
    """**지금 들고 있다고 가정한 포지션** — 백테스트가 표본 끝에 연 다리다.

    [OWNER 2026-09-21 — "이미 진입했다고 가정한 포지션이 존재한다면"] 그 「가정」의
    정체가 이것이다: 같은 조건으로 표본을 끝까지 돌렸을 때 아직 안 닫힌 다리
    (`mrbacktest.simulate` 의 `open`). 원본 규약대로 거래 수·승률에는 안 들어가고
    총손익·낙폭에는 이미 들어가 있다 — 그 사실은 화면이 따로 적는다.

    청산·손절 레벨은 **오늘의** 것이다(`exits_now`) — 매일 중심선과 σ 가 움직이니
    두 수도 매일 바뀐다. 그것이 「데일리로」의 뜻이다.

    `crossed` 는 **중심선을 넘어가 있는가**다. 들어간 쪽에서 되돌아오다 지나쳐
    반대쪽에 서 있으면 참이고, 그때 청산선은 진입 쪽이 아니라 **지금 쪽**에 있다.
    화면이 그 사실을 말할 수 있어야 「이미 지난 선이 청산선으로 적혀 있다」가
    안 된다.

    성분은 실행의 회계를 따라간다: 실가격 판은 다섯(평가·캐리·롤다운·조달·비용),
    엔진 근사 판은 셋이다. **없는 항은 안 싣는다** — 0 으로 채우면 「그 구간에
    롤다운이 없었다」는 다른 말이 된다.
    """
    if not op:
        return None
    dirn = op["direction"]
    word = mr_mod.DIR_LEGS[kind]["minus" if dirn == -1 else "plus"]
    out: dict[str, Any] = {
        "dir": dirn, "short": word["short"], "legs": word["legs"],
        "entryT": op["entryDate"],
        "entryV": disp(op["entryValue"]),
        "entryZ": round(op["entryZ"], 2) if op.get("entryZ") is not None else None,
        "bars": op["bars"],
        "pnl": round(op["pnl"], 2),
        "mtm": round(op["mtm"], 2),
        "carry": round(op["carry"], 2),
        "cost": round(op["cost"], 2),
        # 오늘의 나가는 문 둘 — 밴드가 못 서면 null 이고 화면이 그 사실을 적는다.
        "exit": None if now is None else now["exit"],
        "stop": None if now is None else now["stop"],
        "exitGap": None if now is None else now["exitGap"],
        "stopGap": None if now is None else now["stopGap"],
        "z": None if now is None else now["z"],
        # 진입한 쪽(−1 은 위)과 지금 쪽이 다른가 — 중심선을 지나쳤다는 뜻이다.
        "crossed": (None if now is None
                    else (now["side"] == "above") != (dirn == -1)),
    }
    for k in ("rolldown", "funding"):
        if k in op:
            out[k] = round(op[k], 2)
    return out


def hold_bars(trades: list[dict], since: str) -> float | None:
    """구간 안에서 **청산된** 거래들의 보유 봉수 중앙값. 모자라면 `None`.

    순기대가 「분기당 캐리」를 실제 보유기간으로 환산하려면 그 기간이 있어야
    하는데, 가정으로 꽂으면 그 가정이 숫자의 크기를 정해 버린다. 그래서 **이
    계열이 실제로 얼마나 들고 있었는가**를 쓴다.

    ★세는 규약은 `mrmetrics.score` 와 **같다** — 「거래는 구간 안에서 청산된
    것만」이다(그 함수 머리). 진입 기준으로 세면 승률·거래수와 다른 모집단에서
    중앙값을 내게 되고, 한 카드 안의 두 수가 다른 거래를 말하게 된다.

    ⚠ 이 수도 **선택의 산물**이다 — 조건을 고른 창과 같은 창에서 나온다
    (`GRID_SPAN == PLAN_SPAN`, 모듈 머리 §오너가 정한 것 2). 표본밖 기대
    보유기간이 아니다.
    """
    xs = sorted(float(t["bars"]) for t in trades
                if t.get("bars") and str(t.get("exitDate", "")) >= since)
    if len(xs) < MIN_TRADES_FOR_HOLD:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def net_expectation(levels: list[dict], *, theta_bp: float | None,
                    horizon_y: float, bars: float | None, scale: float,
                    cost_bp: float) -> list[dict]:
    """방향마다 **「들어가서 청산까지」의 기대 bp** — 수렴 + 캐리·롤 − 비용.

        수렴   = |진입 − 청산|            언제나 버는 쪽 (문 둘 사이 거리)
        캐리·롤 = 세타(+1) × 방향 × 보유기간/호라이즌
        순기대 = 수렴 + 캐리·롤 − **왕복 비용**(2 × `COST_BP`)

    ★이 덧셈이 참인 이유는 세 항이 **같은 단위**이기 때문이다 — 엔진의 손익이
    `Δ호가 × ₩/bp` 라(`mrbacktest.simulate`) 호가 bp 로 적힌 것끼리 더해진다.
    `carryroll` 이 세타를 연금이 아니라 **호가 드리프트**로 재는 이유가 이
    가산성이고, 그 선택의 근거와 대가는 그 모듈 머리에.

    왕복인 이유: 들어갈 때 한 번, 나올 때 한 번 [OWNER — 거래 한 번 0.5bp ·
    왕복 1bp, 정본 `paper.cost_dv01_of`].

    **캐리·롤이 음수인 방향은 수렴이 그만큼을 먼저 갚아야 한다.** 이 표가
    말하려는 것이 그 한 문장이고, 그래서 `carryRollBp` 를 따로도 싣는다 —
    합만 보면 어느 쪽이 깎았는지 안 보인다.

    세타나 보유기간이 없으면 **순기대를 안 만든다**(그 열쇠가 아예 없다).
    0 으로 채우면 「비용만큼 손해인 거래」로 읽힌다.
    """
    out: list[dict] = []
    for lv in levels:
        row = {"dir": lv["dir"], "short": lv["short"]}
        converge = abs(lv["entry"] - lv["exit"]) * scale
        row["convergeBp"] = round(converge, 3)
        if theta_bp is not None and bars is not None and horizon_y > 0:
            cr = theta_bp * lv["dir"] * (bars / BARS_PER_YEAR) / horizon_y
            row["carryRollBp"] = round(cr, 3)
            row["netBp"] = round(converge + cr - 2.0 * cost_bp, 3)
        out.append(row)
    return out


def build_series(sid: str, *, leg_of: Callable[..., dict],
                 grid_of: Callable[..., dict],
                 carry_of: Callable[[str, str], dict | None] | None = None,
                 base: dict[str, Any] | None = None,
                 cost_bp: float = COST_BP,
                 rank_key: str = PLAN_RANK_KEY) -> dict:
    """계열 하나의 계획 — 격자 → 채택 → 실행 → 행·레벨·포지션·1년 성적·캐리.

    `leg_of(sid, knobs, accounting=…)` 는 `main._mr_leg` 의 얼굴이고,
    `grid_of(leg, knobs, span=…)` 는 `main._mr_optimize` 의 얼굴이다.
    `carry_of(sid, kind)` 는 `carryroll.for_series` 의 얼굴 — **이 모듈은 DB 를
    모른다**는 계약(머리)이 그대로 서야 해서 세 번째도 주입이다. 안 주면
    캐리 칸이 **없다**(0 이 아니다).
    """
    base = dict(BASE_KNOBS if base is None else base)

    # ① 격자 — **회계 없이** 돈다(모듈 머리 §왜 두 번).
    grid_leg = leg_of(sid, base, accounting=False)
    grid = grid_of(grid_leg, base, span=GRID_SPAN)
    cells = grid.get("cells") or []
    cell = pick_cell(cells, rank_key)
    if cell is None:
        knobs = dict(base)
        # 왜 기본 칸인지를 화면이 말해야 한다 — 「이게 최적이에요」로 읽히면 안 된다.
        fallback = ("격자가 순위를 못 매겼어요(낙폭이 없어 CDaR 비가 안 서는 칸뿐)"
                    " — 기본 조건으로 돌렸어요.")
    else:
        knobs = knobs_of(cell)
        fallback = None

    # ② 실행 — 고른 조건 하나만 **회계를 붙여** 다시 돈다.
    leg = leg_of(sid, knobs, accounting=True)
    r = leg["r"]
    dates, vals = leg["dates"], leg["vals"]
    unit, kind, label = leg["unit"], leg["kind"], leg["label"]
    # 엔진 눈금(bp) → 계열 자기 눈금. `disp` 는 표시용(4자리)이고, 밴드·레벨 산술은
    # **안 반올림한 값** 위에서 한다(반올림한 밴드로 z 를 내면 잡티가 쌓인다).
    scale = 100.0 if unit == "%" else 1.0
    disp = leg["disp"]
    vals_u = [x / scale for x in vals]

    # ③ 보드 행 — 밴드는 **엔진이 잰 것**을 되돌려 넘긴다(모듈 머리 §밴드).
    roll = r["roll"]
    entry_z = float(knobs["entryZ"])
    ma = [None if m is None else m / scale for m in roll["mean"]]
    up = [None if roll["mean"][i] is None else
          (roll["mean"][i] + entry_z * roll["std"][i]) / scale
          for i in range(len(vals))]
    lo = [None if roll["mean"][i] is None else
          (roll["mean"][i] - entry_z * roll["std"][i]) / scale
          for i in range(len(vals))]
    row, history = mr_mod._assemble(
        sid, label, kind, unit, dates, vals_u,
        window=int(knobs["lookback"]), k=entry_z, bands=(ma, up, lo))
    # 다리 레벨 — 보드와 **같은 창구**를 지난다(`mr._row_legs`). 두 화면이 같은
    # 상품의 다리를 다른 이름·다른 차례로 적으면 안 된다.
    row["legs"] = mr_mod._row_legs(kind, leg.get("legLevels"))

    # ④ 오늘의 레벨 셋과 포지션.
    m_now, u_now = ma[-1], up[-1]
    sd_now = None if (m_now is None or u_now is None) else (u_now - m_now) / entry_z
    exit_z, stop_z = float(knobs["exitZ"]), float(knobs["stopZ"])
    levels = levels_for(kind, ma=m_now, sd=sd_now, v=vals_u[-1],
                        entry_z=entry_z, exit_z=exit_z, stop_z=stop_z, scale=scale)
    now = exits_now(ma=m_now, sd=sd_now, v=vals_u[-1],
                    exit_z=exit_z, stop_z=stop_z, scale=scale)
    position = position_of(r.get("open"), kind=kind, now=now, disp=disp)

    # ⑤ 지난 1년 — 엔진은 **전체 표본에서 한 번만** 돌고 채점만 잘린다
    #    (`mrmetrics` 머리 §구간 — 룩백 워밍업이 구간 앞에 있어야 z 가 선다).
    span_from = mrm.span_start(dates, PLAN_SPAN_MONTHS)
    perf = mrm.score(dates, r["points"], r["trades"], span_from, cost_bp)

    # ⑥ 앞을 보는 캐리·롤다운, 그리고 방향마다의 순기대.
    #    `carryroll` 이 서는 계열은 BSS·IRC·IRF 뿐이라 나머지는 `None` 이 온다 —
    #    그 계열의 화면에는 이 칸이 **없다**.
    carry_blk = carry_of(sid, kind) if carry_of is not None else None
    # `span_from` 은 **색인**이다(`mrmetrics.span_start`) — 날짜로 바꿔서 넘긴다.
    bars = hold_bars(r["trades"], dates[span_from] if dates else "")
    carry_roll = None
    if carry_blk is not None:
        carry_roll = {
            **carry_blk,
            "holdBars": bars,
            "costBp": cost_bp,
            # 방향마다 한 줄. 세타나 보유기간이 없으면 `netBp` 가 빠진다.
            "byDir": net_expectation(
                levels, theta_bp=carry_blk["thetaBp"],
                horizon_y=carry_blk["horizonY"], bars=bars,
                scale=scale, cost_bp=cost_bp),
        }

    return {
        **row,
        "cond": {
            **knobs,
            "basis": rank_key, "span": GRID_SPAN, "cells": len(cells),
            "fallback": fallback,
        },
        "levels": levels,
        # 오늘의 나가는 문 둘 — 들고 있든 아니든 같은 수다(엔진의 두 문은 방향을
        # 안 본다). 포지션이 있으면 `position` 이 같은 수를 되풀이해 진다.
        "exitsNow": now,
        "position": position,
        "perf1y": {k: perf[k] for k in PERF_KEYS},
        # 앞을 보는 캐리·롤다운 — 계열이 안 서면 `None` 이고 화면은 그 칸을 비운다.
        "carryRoll": carry_roll,
        # 이 계열의 돈이 실가격 회계인가 엔진 근사인가 — 분해 카드의 «—» 가 그 값이다.
        "real": leg["real"],
        "history": history,
    }


def build_plan(rows: list[dict], *, total: int, excluded: list[dict],
               building: bool, cost_bp: float = COST_BP,
               notional: float = NOTIONAL) -> dict[str, Any]:
    """구워진 계열들을 한 페이로드로 — **부분 결과가 정상이다**.

    25계열의 격자+실행이 약 1분이라(실측 66초) 첫 요청에 다 있을 수 없다. 못 구운 것은
    「없는 것」이 아니라 「아직」이므로 **세어서 말한다**(`pending`) — 못 잰 것을
    0 으로 적지 않는 이 리포의 규율이 여기서는 「비어 있는 표를 조용히 내지
    않는다」로 선다.

    순위는 보드와 같은 축(|z| 내림차순)이고 **구워진 것들 안에서** 매겨진다 —
    빌드가 끝나면 다시 매겨진다. 그 사실도 화면이 적는다.
    """
    rows = sorted(rows, key=lambda r: (-abs(r["z"]) if r["z"] is not None else float("inf")))
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    asof: dict[str, str | None] = {"bss": None, "fut": None, "irs": None}
    for r in rows:
        fam = ("bss" if r["kind"] == "bss"
               else "irs" if r["kind"] in ("irc", "irf") else "fut")
        if asof[fam] is None or r["asof"] > asof[fam]:
            asof[fam] = r["asof"]
    # 통합 줄은 보드의 그 산술을 그대로 쓴다 — 행 모양이 같아서 그냥 선다.
    from . import mrbook
    done = len(rows)
    return {
        "asof": asof,
        "params": {
            "span": PLAN_SPAN, "months": PLAN_SPAN_MONTHS,
            "rankKey": PLAN_RANK_KEY, "gridSpan": GRID_SPAN,
            "costBp": cost_bp, "notional": notional, "carry": True,
        },
        "total": total,
        "done": done,
        "pending": max(0, total - done - len(excluded)),
        "building": building,
        "rows": rows,
        "watch": mrbook.watch(rows),
        "excluded": excluded,
    }
