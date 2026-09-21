# -*- coding: utf-8 -*-
"""모멘텀 **슬리브** 집행면 — 「오늘 칠 것」 (2026-09-21).

[OWNER 2026-09-21 — "모멘텀도 좀 고쳐두자.. 원래 우리 하던 방향있잖아"] MR 을
계획면으로 바꾼 그 방향을 모멘텀에 옮긴 것이다. 다만 **모멘텀에서의 「지금 할 일」은
진입 트리거가 아니다** — 이 북은 매일 크기가 바뀌는 연속 북이라 「진입」이라는 사건이
없고, 데스크가 실제로 치는 것은 **어제와의 차이**다(`scripts/sleeve_daily` 머리).

## 왜 화면이 필요했나

이 데스크의 모멘텀 등록 북은 **둘**이다:

    `/momentum` 면   2026-09-08 등록(선물·합성)을 비추는 거울 — **굴리지 않는다**
    슬리브           2026-09-15 동결·09-16 채점 중인 IRS 50/50 — **이쪽이 실물**

그런데 굴리는 쪽에 화면이 없었다. 아침 주문표도 배율·여력도 상관 경보도 전부
스크립트와 마크다운뿐이라, 매일 손으로 돌려야 보였다. 이 모듈이 그 셋을 한 페이로드로
잇는다 — **규칙을 만들지 않는다.**

## 이 모듈은 레인의 함수를 **부른다** — 다시 구현하지 않는다

산술은 전부 `backend/scripts/sleeve_{execution,monitor,daily}.py` 것이고 여기서는
그것을 불러 모으기만 한다. 그 레인의 상시 규율이 그렇게 적혀 있다:

    §10-8  남의 레인 코드를 여기서 고치지 않는다 — 그쪽 모듈을 불러 쓴다
    §10-10 같은 축은 두 표에서 **같은 함수**를 지난다

그래서 `app` 이 `scripts` 를 임포트한다(보통은 반대 방향이지만, 여기서 정의를 한 벌
더 만들면 화면과 주문표가 다른 수를 말하게 된다 — 그게 이 리포가 반복해서 밟은 결함).
임포트는 **함수 안**이다: 그 모듈들이 뜰 때 CSV·외부 폴더를 읽어서, 모듈 머리에 두면
그것들이 없는 환경에서 앱 자체가 안 뜬다.

## 느리다 — 그래서 배경에서 굽는다

실측(2026-09-21): `real_pv01` 2.5초 · `sleeve_dv01_path` 8.4초 · `sleeve_monitor.daily`
**33.3초** = 한 번에 약 45초. 한 요청 안에서 못 끝내므로 MR 계획면과 같은 배관을 쓴다
(디스크 캐시 + 배경 빌더 + 화면 폴링).

## 못 세우면 **왜 못 세우는지**를 말한다

이 배관은 리포 밖(`Projects\\data\\krw-crs` 배분기)과 굽는 산출물(`output/
sleeve_execution_daily.csv`)에 기댄다. 없으면 빈 화면을 내지 않고 사유를 적는다 —
그리고 스크립트들이 `SystemExit` 으로 멈추므로 그것까지 잡는다(웹 프로세스에서
`SystemExit` 은 요청을 죽인다).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

#: 원장 — 아침 주문표가 남기는 그 파일(`scripts/sleeve_daily.LEDGER`).
LEDGER_PATH = Path(__file__).resolve().parent.parent / "output" / "sleeve_daily_ledger.json"

#: 1억 미만 차이는 안 친다 — 호가 단위와 수수료를 못 이긴다(`sleeve_daily.MIN_TICKET`).
MIN_TICKET = 1e8


def _lane():
    """레인 모듈 셋 — **함수 안에서** 들여온다(모듈 머리 §임포트).

    `sys.path` 는 안 건드린다: 백엔드가 `backend/` 에서 뜨므로 `scripts` 가 이미
    패키지 경로에 있고, 스크립트들도 자기 머리에서 같은 일을 한다.
    """
    from scripts import sleeve_execution as se
    from scripts import sleeve_monitor as sm

    return se, sm


def read_ledger(path: Path | None = None) -> dict[str, Any]:
    """원장 상태 — 행 수·마지막 행·**채점일인데 비어 있는 날**.

    빈 원장은 결함이 아니라 **결정 대기**다 [인계문 §3]: 첫 채점 행을 적을지는
    「슬리브를 실제로 켤 것인가」와 같이 정할 일이라 이전 세션이 `--dry` 로 두었다.
    화면은 그 사실을 적기만 한다 — 여기서 채우지 않는다.
    """
    p = path or LEDGER_PATH
    if not p.exists():
        return {"rows": 0, "last": None, "lastRun": None, "scoredRows": 0}
    try:
        blob = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"rows": 0, "last": None, "lastRun": None, "scoredRows": 0,
                "why": "원장을 읽지 못했어요"}
    rows = blob.get("rows") or []
    last = rows[-1] if rows else None
    return {
        "rows": len(rows),
        "last": None if last is None else last.get("date"),
        "lastRun": None if last is None else last.get("run"),
        "scoredRows": sum(1 for r in rows if r.get("scored")),
    }


def _legs(se, net_dv, rp, d: str, scale: float, prev: dict | None) -> list[dict]:
    """만기별 한 줄 — 목표·축소 후·어제·**주문**.

    부호 규약은 주문표 그대로다: 계열이 −bp 라 **DV01 이 양(+)이면 리시브**다.
    「주문」은 목표가 아니라 **어제와의 차이**이고, 1억 미만은 «안 친다».
    """
    out: list[dict] = []
    for k in se.LEG_T:
        dv = float(net_dv.at[d, k])
        pv = float(rp.at[d, k])
        face = abs(dv) / pv * 1e8
        side = 1 if dv > 0 else (-1 if dv < 0 else 0)
        after = face * scale
        signed = after * side
        prev_signed = float(prev["legs"][k]["signed_face"]) if prev and k in (prev.get("legs") or {}) else 0.0
        delta = signed - prev_signed
        out.append({
            "tenor": k, "dv01": dv, "pv01": pv,
            "face": face, "faceAfter": after, "side": side,
            "signedFace": signed, "prevSigned": prev_signed,
            "delta": delta,
            # 칠 것인가 — 화면이 이 판정을 다시 하지 않게 서버가 끝낸다.
            "trade": abs(delta) >= MIN_TICKET,
        })
    return out


def build_sheet(*, lane: Callable[[], tuple] | None = None,
                ledger_path: Path | None = None) -> dict[str, Any]:
    """오늘의 주문표 + 배율·여력 + 원장 상태 — 한 페이로드.

    실패는 **사유 문장**으로 돌려준다(`available: False`). 이 배관은 리포 밖
    배분기와 굽는 CSV 에 기대므로, 없는 날 화면이 빈 표를 그리면 안 된다.
    """
    try:
        se, sm = (lane or _lane)()
    except Exception as exc:                                # noqa: BLE001
        return {"available": False,
                "why": f"슬리브 배관을 불러오지 못했어요 — {exc}"}

    try:
        rp = se.real_pv01()
        _per, net_dv, meta = se.sleeve_dv01_path()
        ix = [d for d in net_dv.index if d in rp.index]
        if not ix:
            return {"available": False,
                    "why": "집행 경로와 실측 pv01 이 겹치는 날이 없어요."}
        # ★기준일은 **집행표와 같은 함수**로 고른다 [§10-10] — 매크로 신호가 IRS
        #  종가보다 하루 늦게 끝나는 날 거시 북 넷이 0 인 북을 오늘의 목표로
        #  내놓지 않기 위해서다(`sleeve_execution.asof_for`).
        d = se.asof_for(ix, meta)
        w4 = sm.daily(verbose=False)
    except BaseException as exc:                            # noqa: BLE001
        # ⚠ `BaseException` 이다 — 레인 스크립트가 `SystemExit` 으로 멈춘다(배분기
        #   폴더가 없거나 집행표 CSV 가 없을 때). 웹 프로세스에서 그것을 안 잡으면
        #   요청이 통째로 죽는다.
        return {"available": False,
                "why": f"슬리브 수를 세우지 못했어요 — {exc}"}

    led_raw: dict[str, Any] = {"rows": []}
    p = ledger_path or LEDGER_PATH
    if p.exists():
        try:
            led_raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            led_raw = {"rows": []}
    rows = led_raw.get("rows") or []
    prev = rows[-1] if rows else None

    scale = float(w4["scale"])
    legs = _legs(se, net_dv, rp, d, scale, prev)
    face_total = sum(l["face"] for l in legs)
    turnover = sum(abs(l["delta"]) for l in legs)

    return {
        "available": True,
        "asof": d,
        # 채점 창인가 — 동결일 다음 영업일부터다.
        "scored": d > sm.FREEZE_DATE,
        "freeze": sm.FREEZE_DATE,
        "mult": float(meta["mult"]),
        "legs": legs,
        "faceTotal": face_total,
        "faceAfter": face_total * scale,
        "turnover": turnover,
        "minTicket": MIN_TICKET,
        # ── W4 — 평균회귀가 증거금을 얼마나 쓰고 있나 ──────────────────────
        "scale": scale,
        "marginNeed": face_total * scale * sm.RATE,
        "mrMargin": float(w4["mr_margin"]),
        "headroom": float(w4["headroom"]),
        # ★★축소를 **안 하면** 이렇게 된다 — 등록서의 「평균회귀 쪽은 안 건드린다」와
        #   k_mr 을 여력에 거는 것이 한 문장에서 충돌하는 자리다(인계문 §5-1).
        "headroomNoShrink": float(w4["headroom_no_shrink"]),
        "scaleNoShrink": float(w4["scale_no_shrink"]),
        "kMr": float(w4["k_mr"]),
        "kMrLive": float(w4["k_mr_live"]),
        "marginSource": w4["margin_source"],
        "histDays": int(w4["hist_days"]),
        "histHitDays": int(w4["hist_hit_days"]),
        "ledger": read_ledger(p),
    }
