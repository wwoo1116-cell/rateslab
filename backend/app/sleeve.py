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


def _signal_lane():
    """신호 격자·테마·다리 성적을 세우는 자리 — 여기도 **레인 것**이다.

    KTB 면이 주던 정보를 이 면으로 옮기면서 들어왔다 [OWNER 2026-09-21 — "원래
    있던 KTB 모멘텀을 대체하는거니까 거기서 제공하던 정보들도 들어가야해"].
    같은 값을 두 번 정의하지 않으려고 **엔진 함수를 그대로** 부른다:

        `ctabacktest.signal_continuous` · `trend_tstat`   KTB 보드가 쓰는 그 함수
        `momentum_irs_evaluate.load_irs_series`           IRS par 금리를 **−bp** 로
        `momentum_irs_books.registered_signals`           테마 넷(IRS 달력 이월)
        `momentum_irs_legs._book` · `momentum_irs_books.macro_books`

    ⚠ **계열이 −bp 다.** 그래서 신호 +1 이 «리시브»이고, 화면이 칠할 «금리» 방향은
    `-signal` 이다 — 선물 보드가 가격 계열에서 같은 식을 쓰는 것과 같은 결론이지만
    이유가 다르다(저쪽은 가격↑=금리↓, 이쪽은 계열 자체가 부호를 뒤집어 놨다).
    """
    from app import ctabacktest as cta
    from app import momentum as mo
    from scripts import momentum_irs_books as mib
    from scripts import momentum_irs_evaluate as mie
    from scripts import momentum_irs_legs as ml

    return cta, mo, mib, mie, ml


def _sign(v: float) -> int:
    return 0 if v == 0 else (1 if v > 0 else -1)


def _hold_days(vals: list[float]) -> int:
    """부호가 안 바뀌고 이어진 날 수 — 「유지」 칸(KTB 보드의 그것)."""
    if not vals:
        return 0
    s = _sign(vals[-1])
    n = 0
    for v in reversed(vals):
        if _sign(v) != s:
            break
        n += 1
    return n


def build_signals() -> dict[str, Any] | None:
    """오늘의 **신호** — 테너 × 룩백 격자와 테마 넷. KTB 면이 주던 그 두 표다.

    못 세우면 `None` 이다(빈 표를 그리느니 칸을 접는다). 값이 없는 것과 0 인 것은
    다른 사실이라 화면이 그 둘을 다르게 적는다.
    """
    try:
        cta, mo, mib, mie, ml = _signal_lane()
        series = mie.load_irs_series(end=None)
        sig = mib.registered_signals(series)
    except BaseException as exc:                            # noqa: BLE001
        return {"available": False, "why": f"신호를 못 세웠어요 — {exc}"}

    rows: list[dict] = []
    for t in sorted(series, key=lambda k: (len(k), k)):
        dates, px = series[t]
        cells = []
        for lb in mo.LOOKBACKS:
            v = cta.signal_continuous(px, mo.SIGNAL, lb)[-1]
            tv = cta.trend_tstat(px, lb)[-1]
            cells.append({"lookback": lb, "signal": round(float(v), 4),
                          # 화면이 칠할 값은 **금리** 방향이다(모듈 머리 §−bp).
                          "rate": round(-float(v), 4),
                          "tstat": None if tv is None else round(float(tv), 2)})
        comp = sum(c["signal"] for c in cells) / len(cells) if cells else 0.0
        # 속도합의 — 다섯 룩백 중 합성과 **같은 방향**인 것의 수. 갈리면 「모른다」다.
        agree = sum(1 for c in cells
                    if c["signal"] != 0 and _sign(c["signal"]) == _sign(comp))
        hold = _hold_days([float(x) for x in
                           cta.signal_continuous(px, mo.SIGNAL, mo.LOOKBACKS[0])])
        rows.append({"tenor": t, "asof": dates[-1],
                     # 계열이 −bp 라 그대로 적으면 음수로 보인다 — 금리로 되돌린다.
                     "rate": round(-float(px[-1]), 2),
                     "cells": cells, "composite": round(float(comp), 4),
                     "compositeRate": round(-float(comp), 4),
                     "agree": agree, "of": len(cells), "holdDays": hold})

    themes = []
    for name, s in sig.items():
        vals = [float(x) for x in s.to_numpy()]
        themes.append({"theme": name, "sign": _sign(vals[-1]) if vals else 0,
                       "holdDays": _hold_days(vals),
                       "asof": str(s.index[-1])[:10] if len(s) else None})
    macro_sign = (sum(t["sign"] for t in themes) / len(themes)) if themes else 0.0

    return {
        "available": True,
        "signal": mo.SIGNAL,
        "lookbacks": list(mo.LOOKBACKS),
        "rows": rows,
        "themes": themes,
        "macroSign": round(macro_sign, 4),
        "macroRate": round(-macro_sign, 4),
    }


def build_perf() -> dict[str, Any] | None:
    """**표본내 성적** — 다리 셋(추세·거시·50/50)을 등록 창에서 채점한 표.

    KTB 면이 주던 셋째 표다 [OWNER 2026-09-21]. 옮기면서 두 가지가 바뀌었다:

    ① **창이 등록서의 «증거» 창이다** — 시작은 위험선호 확장 평균이 250일을 채운
       날(2017-01-09)이고 끝은 **`app.momentum.FREEZE`(2026-09-08)**다. 자르는
       자리가 **서버**인 이유는 KTB 면의 그것과 같다: 프런트에서 자르면 잘린
       구간이 네트워크 탭에 그대로 남는다.

       ⚠ **끝이 동결일(09-15)이 아니다.** 슬리브는 09-15 에 동결됐지만 그 판정문
       (`Momentum-*-IRS-books-paper`)이 선 창은 09-08 까지다 — 평가 경로는
       `load_irs_series` 의 기본 `end` 를 쓰고 집행 경로만 `end=None` 이다
       (2026-09-17 갈래). 실측으로 확인한 차이가 작지 않다:

           끝 2026-09-08   추세 0.847 · 거시 0.925 · 50/50 **1.000**  ← 등록서의 수
           끝 2026-09-15   추세 0.847 · 거시 0.960 · 50/50 **1.168**

       한 주를 더 넣었을 뿐인데 50/50 이 17% 좋아진다. 그 수를 화면에 세우면
       **화면이 등록서와 다른 말을 한다** — 시험이 등록 수 재현을 못 박는다
       (`tests/test_sleeve.py::TestPerfReproduces`).
    ② **세 다리를 다 자른다** — 추세만 남기면 50/50 과의 차로 거시를 역산할 수 있다.

    ## 원화 열은 **혼자 못 읽는다**

    다리마다 실제로 건 위험이 다르다. 원화 낙폭만 보면 「섞으면 반이 된다」로
    읽히는데 그중 얼마는 «덜 걸어서 덜 아팠던 것»이다(2026-09-09 재점검). 그래서
    낙폭에는 **위험 맞춤 짝**을 붙이고(추세 다리의 실현 변동성에 맞춘 뒤), 무차원
    비율(Martin·Sharpe)을 같이 낸다 — 이 데스크에는 자본 분모가 없으므로 **없는
    분모를 지어내지 않는다**.
    """
    try:
        cta, mo, mib, mie, ml = _signal_lane()
        from scripts.momentum_theme_books import pnl_of

        series = mie.load_irs_series(end=None)
        sig = mib.registered_signals(series)
        t_book = ml._book(series, signal=mo.SIGNAL, vol_window=mo.VOL_WINDOW)
        m_books = mib.macro_books(series, sig, mo.VOL_WINDOW)
    except BaseException as exc:                            # noqa: BLE001
        return {"available": False, "why": f"성적을 못 세웠어요 — {exc}"}

    import math

    start = mib.start_of(sig)
    end = mo.FREEZE                 # ← 동결일(09-15)이 아니다. 위 ① 의 그 이유.

    def cut(sr):
        ix = [str(x)[:10] for x in sr.index]
        return [float(v) for t, v in zip(ix, sr.to_numpy()) if start <= t <= end]

    trend = cut(pnl_of(t_book))
    macro_each = [cut(pnl_of(b)) for b in m_books.values()]
    n = min([len(trend)] + [len(x) for x in macro_each]) if macro_each else len(trend)
    trend = trend[-n:] if n else trend
    macro = [sum(col) / len(col) for col in
             zip(*[x[-n:] for x in macro_each])] if macro_each and n else []
    blend = [0.5 * a + 0.5 * b for a, b in zip(trend, macro)] if macro else []

    ANN = 252

    def stats(x: list[float], ref_vol: float | None) -> dict:
        if len(x) < 2:
            return {}
        m = sum(x) / len(x)
        sd = math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))
        vol = sd * math.sqrt(ANN)
        cum, peak, mdd, sq = 0.0, 0.0, 0.0, 0.0
        for v in x:
            cum += v
            peak = max(peak, cum)
            dd = peak - cum
            mdd = max(mdd, dd)
            sq += dd * dd
        ulcer = math.sqrt(sq / len(x))
        ann = m * ANN
        # ★위험 맞춤 — 다리마다 건 위험이 다르므로 **기준 다리의 변동성**에 맞춘 뒤
        #   낙폭을 다시 잰다. 비율(Sharpe·Martin)은 척도 불변이라 안 바뀐다.
        k = 1.0 if (not ref_vol or vol <= 0) else ref_vol / vol
        return {
            "annPnl": round(ann, 2), "annVol": round(vol, 2),
            "maxDrawdown": round(mdd, 2),
            "maxDrawdownVolMatched": round(mdd * k, 2),
            "ulcer": round(ulcer, 2),
            # 원화 열은 **짝이 있어야 읽힌다** — 낙폭과 같은 사정이다(캐논 가드의
            # 그 불변식). 비율(Martin·Sharpe)은 척도 불변이라 맞춰도 안 변한다.
            "ulcerVolMatched": round(ulcer * k, 2),
            "martin": round(ann / ulcer, 3) if ulcer > 0 else None,
            "sharpe": round(m / sd * math.sqrt(ANN), 3) if sd > 0 else None,
            "days": len(x),
        }

    t_stats = stats(trend, None)
    ref = t_stats.get("annVol")
    rows = [{"leg": "trend", **t_stats},
            {"leg": "macro", **stats(macro, ref)},
            {"leg": "blend", **stats(blend, ref)}]
    return {
        "available": True,
        "window": {"start": start, "end": end},
        "refVol": ref,
        "rows": [r for r in rows if r.get("days")],
    }


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
    except BaseException as exc:                            # noqa: BLE001
        # ⚠ `BaseException` 이다 — 레인 스크립트가 `SystemExit` 으로 멈춘다(배분기
        #   폴더가 없거나 집행표 CSV 가 없을 때). 웹 프로세스에서 그것을 안 잡으면
        #   요청이 통째로 죽는다.
        return {"available": False,
                "why": f"슬리브 수를 세우지 못했어요 — {exc}"}

    # ── W4 는 **따로 잡는다** — 이 북은 MR 없이도 선다 ────────────────────────
    #
    # [OWNER 2026-09-21 — "이거 MR이랑은 여기서는 별개도 돌아가게 해주고"]. 배율은
    # 평균회귀가 증거금을 얼마나 쓰고 있나에 달렸고(W4), 그 경로는 **리포 밖 배분기**
    # (`Projects\data\krw-crs`)를 읽는다. 종전에는 그것이 통째로 한 `try` 안에
    # 있어서 배분기가 없는 날 **주문표 전체가 안 섰다** — 이 북 자신의 수는 멀쩡한데.
    #
    # 이제 갈래가 둘이다:
    #     독립   이 북 혼자 — 배율 1.0. **늘 선다.**
    #     연동   W4 를 먹인 등록 규약. 배분기가 있는 날만 선다.
    # 화면은 둘을 나란히 적고, 연동이 없으면 그 사유를 적는다.
    w4: dict | None = None
    w4_why: str | None = None
    try:
        w4 = sm.daily(verbose=False)
    except BaseException as exc:                            # noqa: BLE001
        w4_why = f"평균회귀 증거금 경로를 못 읽어서 배율을 못 세웠어요 — {exc}"

    led_raw: dict[str, Any] = {"rows": []}
    p = ledger_path or LEDGER_PATH
    if p.exists():
        try:
            led_raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            led_raw = {"rows": []}
    rows = led_raw.get("rows") or []
    prev = rows[-1] if rows else None

    scale = float(w4["scale"]) if w4 else 1.0
    legs = _legs(se, net_dv, rp, d, scale, prev)
    face_total = sum(l["face"] for l in legs)
    turnover = sum(abs(l["delta"]) for l in legs)
    #: **독립 판** — 이 북 혼자일 때. 배율이 1 이면 연동 판과 같은 수이고, 그때도
    #: 두 칸을 다 싣는다(같은 수라는 것 자체가 읽는 사람이 알아야 하는 사실이다).
    solo = _legs(se, net_dv, rp, d, 1.0, prev)
    solo_face = sum(l["face"] for l in solo)

    return {
        "available": True,
        "asof": d,
        # ── 이름은 **서버가 낸다** ────────────────────────────────────────────
        # 클라이언트가 동결일을 다시 적으면 두 번째 진실이 된다 — 등록서가 바뀐 날
        # 화면만 옛 날짜를 말하게 되고, 그건 이 리포가 「조용히 낡는다」라고 부르는
        # 결함이다(`guards/critique-repairs` 가 KTB 면에 대해 이미 못 박은 명제다).
        "registry": {
            "book": "IRS 50/50 슬리브",
            "instrument": "IRS " + " · ".join(se.LEG_T),
            "freeze": sm.FREEZE_DATE,
            "note": "2026-09-08 등록(선물·합성)과 **별개의 북**이에요 — 그 면은 "
                    "2026-09-21 에 내려갔고, 수는 판정문에 그대로 있어요.",
        },
        # 이 북 혼자의 답 — MR 이 없어도, 배분기가 못 읽혀도 **늘 선다**.
        "standalone": {
            "legs": solo, "faceTotal": solo_face,
            "marginNeed": solo_face * sm.RATE,
            "turnover": sum(abs(l["delta"]) for l in solo),
        },
        # 등록 규약(W4 연동)이 섰나 — 못 섰으면 사유가 있다.
        "linked": w4 is not None,
        "linkedWhy": w4_why,
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
        "mrMargin": float(w4["mr_margin"]) if w4 else None,
        "headroom": float(w4["headroom"]) if w4 else None,
        # ★★축소를 **안 하면** 이렇게 된다 — 등록서의 「평균회귀 쪽은 안 건드린다」와
        #   k_mr 을 여력에 거는 것이 한 문장에서 충돌하는 자리다(인계문 §5-1).
        "headroomNoShrink": float(w4["headroom_no_shrink"]) if w4 else None,
        "scaleNoShrink": float(w4["scale_no_shrink"]) if w4 else None,
        "kMr": float(w4["k_mr"]) if w4 else None,
        "kMrLive": float(w4["k_mr_live"]) if w4 else None,
        "marginSource": w4["margin_source"] if w4 else None,
        "histDays": int(w4["hist_days"]) if w4 else None,
        "histHitDays": int(w4["hist_hit_days"]) if w4 else None,
        "ledger": read_ledger(p),
        # 오늘의 신호 — KTB 면이 주던 두 표(테너 × 룩백 격자 · 테마 넷).
        # 못 세워도 주문표는 선다(그 칸만 접힌다).
        "signals": build_signals(),
        # 표본내 성적 — **등록 창에서 서버가 잘라서** 낸다(그 함수 머리 §창).
        "perf": build_perf(),
    }
