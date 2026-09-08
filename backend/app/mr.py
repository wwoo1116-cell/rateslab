# -*- coding: utf-8 -*-
"""Mean Reversion 측정면 — BSS 전 테너 밴드 위치 랭킹 (Strategy 둘째 세입자).

**측정이지 신호가 아니다.** `Desktop\\bollinger-mr` 의 사전등록 검증(누적 108구성)이
「볼린저 재진입」 신호 문법을 NO-GO 로 닫았다(REPORT.md·PREREG.md) — 이 화면은
그 결론 위에 선다: 각 테너가 평소 밴드(SMA20 ± 2σ) 대비 어디에 있는지를 재서
늘어난 순서로 세울 뿐, 진입·청산·추천을 말하지 않는다.

**유니버스는 본드스왑 스프레드(국고 − IRS)뿐이다** [OWNER 2026-08-25 — "일단
본드스왑만"]. 첫 판은 검증 레인의 비교군 12계열(선물·IRS 포함)을 그대로 실었는데
그건 범위를 잘못 읽은 것이었다 — 비교군은 검증을 위한 것이었고 화면은 오너가
지정한 유니버스만 싣는다. 선물·IRS 행은 여기서 내려갔다. 대신 BSS 는 일부
테너가 아니라 **전 테너**(6M~10Y, credit_matrix × mkt_irs_close 가 주는 아홉)다.

숫자는 전부 여기서 끝난다(§16): 밴드·z·%B·상태 판정·정렬·순위까지. 브라우저는
포맷만 한다. 데이터는 `universe_series`(호출 시 SQL, 두 다리 inner join)라
전 행이 한 소스·한 as-of 다 — 첫 판의 소스별 as-of 갈림도 같이 은퇴했다.
"""
from __future__ import annotations

import math
from typing import Any, Callable

from sqlalchemy import text

from .mysqldb import engine
from . import mrseries as mrs
from .universe import universe_series  # noqa: F401  (구 출처 — 아래 주석)

# 기본은 검증 레인(mr_backtest.py)과 같은 창·배수 — 화면과 검증이 딴 밴드를
# 말하면 안 된다. 기본을 바꾸려면 두 곳을 같이 바꾼다.
WINDOW = 20
K = 2.0
# 화면 선택지 [OWNER 2026-08-25 — "외부 리서치로 보통 사용하는 값들을 선택지로"].
# 근거 있는 값만 둔다: 20일·2σ 는 볼린저의 관례 기본값(그의 문헌 표준 조합).
# 60·120·252 는 채권 RV 리서치가 흔히 쓰는 분기·반기·1년 창이고, 252 는 이
# 리포의 universe·rv 화면 52주 창과 같은 낱말이다. 1.5σ·2.5σ 는 볼린저 문헌의
# 통상 변형(민감/보수 밴드). 자유 입력을 안 두는 이유: 근거 없는 조합을 화면이
# 권하는 셈이 되고, 검증 레인의 시행 장부와도 어긋난다.
WINDOWS = (20, 60, 120, 252)
KS = (1.5, 2.0, 2.5)
# 재진입 «최근» 판정 상한 — 검증 레인의 EXPIRE_N 과 같은 5영업일.
RECENT_N = 5

# (id, 라벨, 종류) — BSS 전 테너 + 국채선물 내재금리 + 퓨처스왑 [OWNER
# 2026-08-25 — "선물 들어왔는데 국채선물 롱숏이랑 선물 − IRS = 퓨처스왑 롱숏도
# 반영하기"]. 검증이 잰 것은 BSS 3·5·10Y 셋이고 나머지는 측정만 싣는 계열이다
# (측정 화면이라 문제없되, 사실은 사실대로 적어 둔다).
#
# 선물 값은 **내재수익률**이다 — «선물 − IRS» 가 성립하려면 금리끼리 빼야
# 한다. 출처는 2026-08-25 부터 **벤더 내재금리 직독**(`futures.load().implied`,
# infomax daily_ktb_price·daily_lktb_price — «read, not derived»)이고, 종가를
# 5% 합성채로 역산하던 `_implied_yield` 는 별칭 유지용으로만 남아 있다.
# ⚠ 벤더 내재와 5% 합성 역산은 같은 것이 아니다 — KTB3 는 역사 구간에서
# 계약별 상수 격차(중앙 58bp, 2012년 180bp → 2025-10 이후 0.02bp 수렴)가
# 실측됐다(2026-09-02 적대 대사). 그래서 KIND_DEFN 의 fut 문장도 «벤더
# 내재금리» 로 적는다 — 「5% 합성」이라 적으면 계열의 절반 이력에서 거짓이다.
# 이 화면의 낱말은 전부 금리 bp 다 — 가격 계열을 섞으면 전략 실험 창의
# 명목(₩/bp)이 그 행에서만 거짓이 된다.
"""전략 실험 창의 노브 허용값 — 프런트 `src/mr/api.ts::MR_STRATEGY_PRESETS`
가 이 목록을 거울로 삼는다. 근거 있는 값만 늘어놓는 규율은 보드(WINDOWS·KS)와
같고, 「이웃 칸」 민감도는 **이 목록 위에서** 돈다 — 화면이 고를 수 있는 칸이
곧 화면이 견고성을 재야 하는 칸이다.

비용·명목은 여기 없다. 그 둘은 통상값이 아니라 그날 그 종목의 호가폭이고 이
데스크의 포지션 크기라, 셋을 늘어놓으면 근거가 아니라 지어낸 기준이 된다.
"""
STRATEGY_PRESETS: dict[str, list[float]] = {
    "lookback": [20, 60, 120],
    "entryZ": [1.5, 2.0, 2.5],
    "exitZ": [0.0, 0.5, 1.0],
    # 손절 셋은 [3.0, 3.5, 4.0] 이었다 — 무제한 자본·단일 다리 프레임의 값이다.
    # [OWNER 2026-09-08 — "v2에서 손절을 3.0 3.5 4.0이 아니라 2.5 3.0 3.5로"]
    # 증거금 예산(100억·6다리·규칙 B·묶인 증거금에만 기준+10bp) 안에서는 손절이
    # 풀어 준 자리로 막힌 신호가 들어가 **2.5 가 순연환산 1등**(+6.99% 대 3.5 의
    # +5.32%, 표본 전·후반 반쪽 모두에서)이었다. 기제는 손실 꼬리 축소가 아니라
    # 자본 회전이다 — 단일 다리로는 손절을 풀수록 낫다(꼬리는 손절이 만든다).
    # 근거: krw-crs `RESULT_stop_in_book_2026-09-08.md`(실가격 회계 정정판).
    # ★격자 162칸의 구성이 바뀐다 — MR_LANE_STATE 의 OOS·PBO 수치는 옛 격자 기록.
    "stopZ": [2.5, 3.0, 3.5],
}

# 열 제목이 **단위를 진다** — 칸 라벨에 「2σ」로 적었더니 CDS `caption` 이 대문자
# 변환을 걸어 σ 가 **Σ 로 렌더됐다**(실측 2026-08-26, 브라우저 스크린샷). 시그마는
# 대소문자가 서로 다른 글자라 그건 오타가 아니라 **틀린 기호**다. 단위를 제목으로
# 올리면 칸에는 숫자만 남고, 설정 줄의 라벨(「룩백 (일)」·「진입 σ」)과도 같아진다.
STRATEGY_KNOB_LABELS: dict[str, tuple[str, str]] = {
    "lookback": ("룩백 (일)", "일"),
    "entryZ": ("진입 σ", "σ"),
    "exitZ": ("청산 σ", "σ"),
    "stopZ": ("손절 σ", "σ"),
}


SERIES: list[tuple[str, str, str]] = [
    ("BSS-6M", "BSS 6M", "bss"),
    ("BSS-9M", "BSS 9M", "bss"),
    ("BSS-1Y", "BSS 1Y", "bss"),
    ("BSS-1.5Y", "BSS 1.5Y", "bss"),
    ("BSS-2Y", "BSS 2Y", "bss"),
    ("BSS-3Y", "BSS 3Y", "bss"),
    ("BSS-5Y", "BSS 5Y", "bss"),
    ("BSS-7Y", "BSS 7Y", "bss"),
    ("BSS-10Y", "BSS 10Y", "bss"),
    ("FUT-KTB3", "KTB3 내재금리", "fut"),
    ("FUT-KTB10", "KTB10 내재금리", "fut"),
    ("FSW-3Y", "퓨처스왑 3Y", "fsw"),
    ("FSW-10Y", "퓨처스왑 10Y", "fsw"),
]

# 행의 정의 문장 — 화면 서브라인이 그대로 읽는다(혼합 유니버스에서 숫자 옆에
# 무엇인지가 없으면 두 단위를 같은 자로 읽게 된다 — rv 랭킹 표의 그 판단).
KIND_DEFN = {
    "bss": "국고 − IRS",
    # «(5% 합성)» 이라 적었던 것을 정정 — 실제 값은 벤더 내재금리 직독이고,
    # KTB3 는 역사 구간에서 5% 합성 역산과 중앙 58bp 어긋난다(위 주석).
    "fut": "선물 내재수익률 (벤더 직독)",
    "fsw": "선물내재 − IRS",
}

# 퓨처스왑의 IRS 다리 — 선물 상장 만기와 같은 테너.
FSW_IRS_COL = {"FSW-3Y": ("3Y", "irs_3y"), "FSW-10Y": ("10Y", "irs_10y")}


# ── 방향이 실제로 무슨 거래인가 ─────────────────────────────────────────────
#
# 엔진(mrbacktest)에서 `+1` 은 언제나 «값이 오르면 버는 쪽» 이다. 이 화면의 값은
# 전부 금리(또는 금리차)라 그 +1 이 실제로 무슨 다리인지는 계열마다 다르고,
# 「롱/숏」이라고만 적으면 읽는 사람이 채권 방향으로 읽는다(BSS 에서는 정확히
# 반대다 — 스프레드 롱 = 국고 매도).
#
#   BSS = 국고 − IRS  → +1 은 스프레드 확대에 거는 쪽 = 국고 매도 · IRS 리시브
#                        −1 은 축소에 거는 쪽       = 국고 매수 · IRS 페이
#   FUT = 선물 내재금리 → +1 은 금리 상승 = 선물 매도 (백테스트 북의 방향 라벨은
#                        **가격** 계열이라 부호가 반대다 — 여기는 금리다)
#   FSW = 선물내재 − IRS → 백테스트 북 `directionLabel` 의 퓨처스왑과 같은 문장
DIR_LEGS = {
    "bss": {"plus": {"short": "국고 매도", "legs": "국고 매도 · IRS 리시브"},
            "minus": {"short": "국고 매수", "legs": "국고 매수 · IRS 페이"}},
    "fut": {"plus": {"short": "선물 매도", "legs": "선물 매도"},
            "minus": {"short": "선물 매수", "legs": "선물 매수"}},
    "fsw": {"plus": {"short": "선물 매도", "legs": "선물 매도 · IRS 리시브"},
            "minus": {"short": "선물 매수", "legs": "선물 매수 · IRS 페이"}},
}

# 실행할 수 있는 방향 [OWNER 2026-08-25 — "BSS에서 숏은 없는거야,, 현물대차매도는
# 안할거거든"]. 이 데스크에 **이미 있던 규칙**이다 — 백테스트·시뮬의 현금채권은
# 매수만 받는다(cashbond.py: "국고채는 매도는 없는거고" [OWNER 2026-08-14]).
# BSS 의 +1(스프레드 확대)은 국고를 빌려 파는 다리라 그 규칙에 걸린다. 선물은
# 대차가 필요 없으므로 FUT·FSW 는 양방향 그대로다.
#
# 못 하는 거래를 재현해 두면 성과가 «할 수 있었던 것» 이 아니라 그 절반이
# 상상인 숫자가 된다 — 대차료를 0 으로 둔 공매도 백테스트가 늘 이기는 것과
# 같은 결함이다.
TRADABLE_DIRS = {"bss": (-1,), "fut": (-1, 1), "fsw": (-1, 1)}

# 막힌 방향을 화면이 뭐라 말하는가 — 사유는 서버 것이다(rv exclusions 문법).
BLOCKED_WHY = "현물 대차매도를 안 해서 반대 방향(국고 매도)은 재현하지 않아요."


def dirs_for(kind: str) -> dict:
    """계열 종류 하나의 방향 사전 — 허용 방향 + 두 방향의 이름 + 사유."""
    legs = DIR_LEGS[kind]
    allowed = TRADABLE_DIRS[kind]
    return {
        "allowed": list(allowed),
        "plus": legs["plus"],
        "minus": legs["minus"],
        "why": BLOCKED_WHY if len(allowed) < 2 else None,
    }


def triggers_for(kind: str, v: float, up: float | None, lo: float | None,
                 scale: float) -> list[dict]:
    """밴드 경계를 **지금 만질 수 있는 거래**로 옮겨 적은 것 — 「얼마 레벨이면
    어느 다리인가」 [OWNER 2026-09-09 — "누르면 얼마 레벨에서는 매수 추천과 같은
    플로우"].

    ## 계산이 아니라 **번역**이다 — 그래서 추천이 아니다

    새 판정을 하나도 안 만든다. 밴드(SMA ± k·σ)는 이미 이 화면의 값이고,
    방향과 다리 이름은 이미 `DIR_LEGS`·`TRADABLE_DIRS` 의 값이다. 이 함수가
    더하는 것은 그 둘을 한 문장으로 **잇는 것**뿐이다: 「+25.57bp 이상이면
    국고 매수 · IRS 페이」. 종전 화면은 둘을 따로 적어 두고 읽는 사람이 머리로
    이으라고 했다 — 그런데 경계 레벨은 화면에 **숫자로 서 있지도 않았다**
    (`upper`·`lower` 는 페이로드에만 있었다).

    명구 의무는 그대로 산다(`MrPage` 머리 주석): 명목·손절·목표를 말하지 않고,
    **진입 문턱 하나**만 말한다 [OWNER 2026-09-09 — 「트리거 레벨까지」].

    ## 어느 경계가 어느 다리인가

    엔진 규약은 `|z| ≥ 진입σ` 인 봉에서 `want = -1 if z > 0 else +1` 이다 —
    **늘어난 쪽의 반대**에 건다. 그래서 경계마다 방향이 하나로 정해진다:

        값 ≥ 상단  →  dir −1  (축소에 거는 쪽)
        값 ≤ 하단  →  dir +1  (확대에 거는 쪽)

    `TRADABLE_DIRS` 에 없는 방향은 **아예 안 싣는다** — BSS 의 하단은 국고
    매도라 이 데스크가 못 하는 거래이고(`BLOCKED_WHY`), 그 자리에 레벨을
    적으면 화면이 못 하는 거래의 문턱을 권하는 셈이다. 화면이 그 사실을 말할
    수 있게 사유는 행의 `triggerBlocked` 가 따로 진다.

    ## `gap` 의 부호 — 「아직 얼마 남았나」

    양수면 그만큼 더 가야 문턱이고, 음수면 **이미 지났다**(그때 `reached`).
    단위는 행의 변화 열과 같은 bp 다(`scale` 이 %-계열을 옮긴다) — 레벨은
    계열의 자기 단위인데 거리를 그 단위로 적으면 선물 계열에서만 100배 작은
    수가 된다(이 파일이 `d1`·`width` 에서 이미 지키는 규약).
    """
    legs = DIR_LEGS[kind]
    out: list[dict] = []
    for dirn, side, level, word in ((-1, "above", up, legs["minus"]),
                                    (1, "below", lo, legs["plus"])):
        if level is None or dirn not in TRADABLE_DIRS[kind]:
            continue
        gap = (level - v) if side == "above" else (v - level)
        out.append({
            "dir": dirn, "side": side,
            "level": round(level, 4),
            "short": word["short"], "legs": word["legs"],
            "gap": round(gap * scale, 4),
            "reached": gap <= 0,
        })
    return out


# KRX 국채선물 이론가의 역함수 — 2026-08-25 선물·퓨처스왑이 백테스트/시뮬에
# 합류하면서 `futures_pricing` 으로 승격했다(같은 수를 두 곳에서 정의하지
# 않는다). 구간·횟수 등 산술은 바이트 단위로 그때 그대로다 — 이 별칭은 이
# 화면(및 test_mr)이 부르던 이름을 지킨다.
from irs_pricer.services.simulation.futures_pricing import (  # noqa: E402
    implied_yield as _implied_yield,
)


def _fut_bundle() -> dict[str, dict[str, Any]]:
    """새 선물 표 + IRS 종가에서 넉 장을 한 번에 — 내재금리 2, 퓨처스왑 2.

    두 표 모두 `sim_portfolio` 라 같은 커넥션의 두 스캔이고, 퓨처스왑은 BSS 와
    같은 inner join 규율(양쪽 다 있는 날만, 보간·이월 없음)이다.
    """
    from . import futures as ft

    with engine().connect() as conn:
        irs = conn.execute(text(
            "SELECT irs_date, irs_3y, irs_10y FROM mkt_irs_close ORDER BY irs_date ASC"
        )).fetchall()

    # ── 내재금리는 **벤더 값을 읽는다** [OWNER, 2026-08-25] ────────────────────
    # 종전에는 `mkt_futures_investor_close.CLOSE` 를 역산했는데 그 계열은 뒤로
    # 조정된 연속 가격이라 **수준이 없다**(FUTURES_LANE_STATE §Phase 1). 벤더
    # 값 대비 중앙 28.5bp(10Y)·89.5bp(3Y), 최대 182bp 까지 틀린 계열을 이 보드와
    # 전략 실험 창이 함께 쓰고 있었다. 로더(`futures.load`)가 이미 두 역할을
    # 갈라 들고 있으므로 여기서 SQL 을 또 읽지 않는다 — 한 출처.
    fut = ft.load()
    yields: dict[str, list[tuple[str, float]]] = {"3Y": [], "10Y": []}
    for typ in ("3Y", "10Y"):
        fs = fut.series.get(typ)
        if fs is None:
            continue
        for d, y in zip(fs.dates, fs.implied):
            if y is not None:
                yields[typ].append((d.isoformat(), y))

    irs_by_date: dict[str, dict[str, float]] = {}
    for d, y3, y10 in irs:
        irs_by_date[d.isoformat()] = {"irs_3y": y3, "irs_10y": y10}

    # 계약이 갈리는 날 — 봉마다 «이 Δ 는 거래할 수 없다» 는 표시가 된다
    # [OWNER 2026-09-02 — "롤일 Δ 를 0 으로 마스크"]. 규칙과 실측은
    # `futures.roll_days` 주석에. 퓨처스왑도 같은 날이다 — 그 계열의 롤 점프는
    # 선물 다리에서 오고 IRS 다리는 상수만기라 롤이 없다.
    rolls = {typ: {d.isoformat() for d in ft.roll_days(list(fut.series[typ].dates))}
             for typ in ("3Y", "10Y") if fut.series.get(typ) is not None}

    out: dict[str, dict[str, Any]] = {}
    for sid, typ in (("FUT-KTB3", "3Y"), ("FUT-KTB10", "10Y")):
        rd = rolls.get(typ, set())
        # `legs` = 그 봉의 **다리 레벨**(%) — 대사표가 다리마다 Δ·손익을 세운다
        # [OWNER 2026-09-03]. 선물 아웃라이트는 다리가 하나라 값 자체가 그 다리다.
        # **안 반올림한다**: 값(`v`)이 4자리로 접히므로 다리에서 또 접으면
        # 「다리 Δ 의 차 = 값의 Δ」 항등에 잡티가 쌓인다(표시 자릿수는 화면 몫).
        out[sid] = {"unit": "%",
                    "points": [{"t": t, "v": round(v, 4), "roll": t in rd,
                                "legs": [v]}
                               for t, v in yields[typ]]}
    for sid, (typ, col) in FSW_IRS_COL.items():
        rd = rolls.get(typ, set())
        pts = []
        for t, v in yields[typ]:
            leg = irs_by_date.get(t, {}).get(col)
            if leg is None:
                continue
            # 다리 둘을 그대로 싣는다 — 화면의 «선물 − IRS = 레벨» 이 닫히고,
            # 대사표가 다리마다 Δbp 를 잰다. 값은 %(레벨 문법) 그대로다.
            pts.append({"t": t, "v": round((v - float(leg)) * 100.0, 4),
                        "roll": t in rd,
                        "legs": [v, float(leg)]})
        out[sid] = {"unit": "bp", "points": pts}
    return out

# 히스토리 차트가 드는 길이 — 대략 1년.
HISTORY_N = 260


def _bands(vals: list[float], window: int = WINDOW, k: float = K) -> tuple[list, list, list]:
    """SMA(window) ± k·**모집단** SD. 창이 차기 전은 None — 0 이 아니다.

    **σ 규약은 엔진이 정본이다** [OWNER 2026-09-02 — "엔진(모집단 σ)으로 통일"].
    2026-09-02 적대 대사가 잡은 자리: 이 보드는 ddof=1(표본), 전략 엔진
    (`mrbacktest.rolling_series` — PMS 원본 이식)은 모집단 σ 라, **같은 계열·
    같은 창·같은 날**의 z 가 √((w−1)/w) 배 갈렸다. BSS-3Y 2,958봉 중 9봉이
    진입 문턱 반대편에 섰다 — 보드에서 「밴드 밖」인 날이 창에서는 아니었다.

    엔진 쪽으로 맞춘 이유: 엔진은 PMS 재현이 계약이고 적합성 벡터로 잠겨 있어
    바꾸면 그 계약이 깨진다. 보드는 순위·표시용이라 규약을 따라오면 된다.
    (보드 z 는 이 변경으로 모두 √(w/(w−1)) 배 = 창 60 에서 0.84% 커진다.)"""
    n = len(vals)
    ma: list[float | None] = [None] * n
    up: list[float | None] = [None] * n
    lo: list[float | None] = [None] * n
    if n < window:
        return ma, up, lo
    s = sum(vals[:window])
    s2 = sum(x * x for x in vals[:window])
    for i in range(window - 1, n):
        if i >= window:
            old, new = vals[i - window], vals[i]
            s += new - old
            s2 += new * new - old * old
        m = s / window
        # 모집단 σ(ddof=0) — 엔진과 같은 규약. 수치 오차로 음수가 될 수 있어
        # 0 에서 자른다.
        var = max(0.0, (s2 - window * m * m) / window)
        sd = math.sqrt(var)
        ma[i], up[i], lo[i] = m, m + k * sd, m - k * sd
    return ma, up, lo


def _out(vals: list[float], up: list, lo: list, i: int) -> int:
    """밴드 밖 방향 — +1 하단 밖, −1 상단 밖, 0 안(또는 창 미달)."""
    if up[i] is None:
        return 0
    if vals[i] < lo[i]:
        return 1
    if vals[i] > up[i]:
        return -1
    return 0


def _state(vals: list[float], up: list, lo: list) -> dict[str, Any]:
    """오늘의 밴드 상태 — 밖이면 며칠째인지, 안이면 최근 재진입인지.

    검증 레인의 상태기계와 같은 어휘(밖/재진입)를 쓰되 판정만 있고 행동이 없다.
    """
    n = len(vals)
    now = _out(vals, up, lo, n - 1)
    if now != 0:
        d = 1
        while n - 1 - d >= 0 and _out(vals, up, lo, n - 1 - d) == now:
            d += 1
        return {"kind": "below" if now == 1 else "above", "days": d}
    i = n - 2
    while i >= 0 and _out(vals, up, lo, i) == 0:
        i -= 1
    if i >= 0 and (n - 1 - i) <= RECENT_N:
        side = _out(vals, up, lo, i)
        return {"kind": "reentry-low" if side == 1 else "reentry-high",
                "days": n - 1 - i}
    return {"kind": "inside", "days": None}


def _assemble(sid: str, label: str, kind: str, unit: str,
              dates: list[str], vals: list[float],
              window: int = WINDOW, k: float = K) -> tuple[dict, dict]:
    """한 계열의 보드 행과 히스토리 조각. 반환 = (row, history)."""
    if len(vals) < window + 1:
        raise ValueError(f"{sid}: 창({window})보다 짧은 이력({len(vals)})")
    ma, up, lo = _bands(vals, window, k)
    v, m, u, l = vals[-1], ma[-1], up[-1], lo[-1]
    sd = (u - m) / k if (u is not None and m is not None) else None
    z = (v - m) / sd if sd else None
    pct_b = (v - l) / (u - l) * 100.0 if (u is not None and u != l) else None
    d1 = v - vals[-2]
    width = (u - l) if u is not None else None
    # %-계열의 차·폭은 bp 로 끝내서 보낸다 — 브라우저는 계산하지 않는다(§16).
    # (BSS 는 bp 라 scale=1 이지만, 단위 규칙은 계열이 아니라 함수의 것이다.)
    scale = 100.0 if unit == "%" else 1.0
    d_unit = "bp" if unit == "%" else unit
    row = {
        "id": sid, "label": label, "kind": kind, "defn": KIND_DEFN[kind],
        "unit": unit,
        "v": round(v, 4),
        "d1": round(d1 * scale, 4), "dUnit": d_unit,
        "ma": round(m, 4) if m is not None else None,
        "upper": round(u, 4) if u is not None else None,
        "lower": round(l, 4) if l is not None else None,
        "z": round(z, 2) if z is not None else None,
        "pctB": round(pct_b, 1) if pct_b is not None else None,
        "width": round(width * scale, 4) if width is not None else None,
        "asof": dates[-1],
        "state": _state(vals, up, lo),
        # 「얼마 레벨이면 어느 다리인가」 — 밴드 경계의 번역이다(그 함수 머리).
        # 0~2개이고, 못 하는 방향은 안 싣는다.
        "triggers": triggers_for(kind, v, u, l, scale),
        # 왜 한쪽만 서는가 — 빠진 경계를 화면이 조용히 숨기지 않는다(rv
        # exclusions 문법과 같은 자리).
        "triggerBlocked": dirs_for(kind)["why"],
    }
    lo_i = max(0, len(vals) - HISTORY_N)
    history = {
        "id": sid, "label": label, "unit": unit,
        "points": [
            {
                "t": dates[i], "v": round(vals[i], 4),
                "ma": round(ma[i], 4) if ma[i] is not None else None,
                "up": round(up[i], 4) if up[i] is not None else None,
                "lo": round(lo[i], 4) if lo[i] is not None else None,
            }
            for i in range(lo_i, len(vals))
        ],
    }
    return row, history


def series_points(sid: str, *, fut_bundle: dict | None = None) -> dict[str, Any]:
    """한 계열의 원 시계열 — 보드와 전략 실험이 **같은 유도**를 쓰는 단일 창구."""
    kinds = {s: kd for s, _, kd in SERIES}
    kind = kinds.get(sid)
    if kind is None:
        raise KeyError(sid)
    if kind == "bss":
        # 긴 표본 출처 [OWNER 2026-08-28 — "옮기고"]. 종전에는
        # `universe_series`(= `credit_matrix`, 2020-01~)였고 그래서 BSS 가
        # 6.7년이었다. `mrseries` 는 같은 벤더 피드를 2014-05 부터 읽는다 —
        # 겹치는 1,633일에서 상관 0.9996~1.0000·중앙 차이 0.00~0.10bp 로 같은
        # 계열임을 확인하고 **이음매 없이** 전 기간을 이쪽으로 옮겼다.
        # 보드의 오늘 숫자는 트레일링 창이라 안 바뀐다(그쪽 머리 주석).
        return mrs.points(sid)
    bundle = fut_bundle if fut_bundle is not None else _fut_bundle()
    return bundle[sid]


def build_mr(dataset=None, *, window: int = WINDOW, k: float = K,
             fetch_uni: Callable[[str], dict] | None = None,
             fetch_fut: Callable[[], dict] | None = None) -> dict[str, Any]:
    """보드 + 히스토리 전부. 라우트는 이 페이로드를 썰어서만 답한다.

    `dataset` 은 이제 안 읽는다 — 모든 다리가 호출 시 SQL 이라 기동 스냅샷
    의존이 없다. 자리는 남긴다: 라우트가 캐시 키로 `_dataset.data_key` 를 계속
    쓰고(universe 와 같은 판단), 서명을 바꾸면 그 호출부가 흔들린다.

    window·k 의 허용값 검증(WINDOWS·KS)은 라우트가 한다 — 여기는 계산만.

    fetch_uni·fetch_fut 은 시험 주입 자리 — 기본은 실제 SQL 을 읽는다. 못 읽은
    계열은 조용히 빼지 않고 `excluded` 에 사유와 함께 선다(rv exclusions 문법).
    """
    fetch_uni = fetch_uni or mrs.points

    rows: list[dict] = []
    histories: dict[str, dict] = {}
    excluded: list[dict] = []
    # 소스별 as-of — BSS(민평×IRS)와 선물(선물표×IRS)이 갈라질 수 있고, 갈라진
    # 날은 화면이 그렇다고 말해야 한다(rv 의 B-2).
    asof: dict[str, str | None] = {"bss": None, "fut": None}
    fut: dict | None = None
    for sid, label, kind in SERIES:
        try:
            if kind == "bss":
                body = fetch_uni(sid)
            else:
                if fut is None:
                    fut = (fetch_fut or _fut_bundle)()
                body = fut[sid]
            pts = [p for p in body["points"] if p.get("v") is not None]
            row, history = _assemble(sid, label, kind, body["unit"],
                                     [p["t"] for p in pts],
                                     [float(p["v"]) for p in pts],
                                     window, k)
        except (KeyError, ValueError) as exc:
            excluded.append({"id": sid, "label": label, "reason": str(exc)})
            continue
        rows.append(row)
        histories[sid] = history
        fam = "bss" if kind == "bss" else "fut"
        if asof[fam] is None or row["asof"] > asof[fam]:
            asof[fam] = row["asof"]

    # 늘어난 순서 — |z| 내림차순, 창 미달(None)은 끝. 랭킹과 순위 숫자까지
    # 여기서 끝난다(§16).
    rows.sort(key=lambda r: (-abs(r["z"]) if r["z"] is not None else math.inf))
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    # BSS 통합 한 줄 [OWNER 2026-09-01] — 랭킹 **아래**에 따로 선다. 순위는 |z|
    # 로 매기는데 이 줄은 값이 아니라 집계라 그 정렬에 낄 수 없다.
    #
    # 임포트가 함수 안인 이유: `mrbook` 이 계열 목록·만기 순서를 여기서 읽으므로
    # (`mr_mod.SERIES`) 모듈 머리에 두면 순환이다. 이쪽만 늦추면 방향이 하나로
    # 선다 — 통합은 계열 목록을 알아야 하고, 계열 목록은 통합을 몰라도 된다.
    from . import mrbook
    return {
        "asof": asof,
        "params": {"window": window, "k": k, "recentN": RECENT_N},
        "rows": rows,
        "watch": mrbook.watch(rows),
        "excluded": excluded,
        "history": histories,
    }
