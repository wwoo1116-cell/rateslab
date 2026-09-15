# -*- coding: utf-8 -*-
r"""아침에 이것 하나 — 오늘 세울 북과 **어제와의 차이(주문)** [OWNER 2026-09-15].

    python -m scripts.sleeve_daily              # 오늘 주문표
    python -m scripts.sleeve_daily --dry        # 기록 안 남김

동결 등록서 `docs/PREREG_sleeve_5050_2026-09-15.md`(동결·재동결 2026-09-15 · 채점 2026-09-16~).
**규칙을 만들지 않는다** — 흩어져 있던 셋을 한 줄로 잇는다.

    ① 신호      `momentum_irs_books.registered_signals`  (IRS 달력 전일 이월)
    ② 목표 액면  다섯 북 DV01 → 실측 커브 pv01 → 만기별 액면        (`sleeve_execution`)
    ③ W4 배율   여력 = 100억 − 평균회귀 증거금, 넘으면 비례 축소     (`sleeve_monitor`)
    ④ **주문**   오늘 목표 − 어제 실제 = 오늘 칠 것

★목표가 아니라 **차이**를 찍는 이유: 이 북은 매일 크기가 바뀌는 연속 북이라 「진입」이라는
 사건이 없다. 데스크가 실제로 치는 것은 어제와의 차이다.

★손익 귀속에는 **전일 배율**을 건다(W4). 오늘 세운 포지션이 내일 변화를 먹으므로.

⚠ 채점 창이 열리기 전(2026-09-16 이전)에는 「연습」으로 찍는다 — 기록은 남기되 채점엔 안 쓴다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from scripts import sleeve_execution as se                      # noqa: E402
from scripts import sleeve_monitor as sm                        # noqa: E402

LEDGER = BACKEND / "output" / "sleeve_daily_ledger.json"
RATE = sm.RATE
MIN_TICKET = 1e8        # 1억 미만 차이는 안 친다 — 호가 단위와 수수료를 못 이긴다


def _load() -> dict:
    if LEDGER.exists():
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    return {"rows": []}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="기록을 안 남긴다")
    a = ap.parse_args()

    # ① ② — 목표 액면 (실측 pv01)
    rp = se.real_pv01()
    per, net_dv, meta = se.sleeve_dv01_path()
    ix = [d for d in net_dv.index if d in rp.index]
    d = ix[-1]
    tgt = {}
    for k in se.LEG_T:
        dv = float(net_dv.at[d, k]); p = float(rp.at[d, k])
        tgt[k] = {"dv01": dv, "pv01": p, "face": abs(dv) / p * 1e8, "side": 1 if dv > 0 else (-1 if dv < 0 else 0)}
    face_total = sum(v["face"] for v in tgt.values())

    # ③ — W4 배율
    w4 = sm.daily(verbose=False)
    scale = w4["scale"]

    # ④ — 어제와의 차이
    led = _load()
    prev = led["rows"][-1] if led["rows"] else None
    scored = d > sm.FREEZE_DATE

    print()
    print(f"── 슬리브 주문표 · 기준일 {d} {'(채점 창)' if scored else '(연습 · 채점은 2026-09-16 부터)'} ──")
    print(f"  배수 {meta['mult']:.2f} · W4 배율 **{scale:.3f}**"
          + ("" if scale >= 0.999 else f"  ★평균회귀가 증거금을 많이 써서 오늘 액면을 줄인다"))
    if prev:
        print(f"  직전 기록 {prev['date']} (배율 {prev['scale']:.3f})")
    else:
        print("  직전 기록 없음 — 오늘이 첫 날이다. 목표 전체가 주문이 된다.")

    print()
    print(f"  {'만기':5s} {'순 DV01':>10s} {'목표 액면':>11s} {'축소 후':>11s} {'방향':>6s} {'어제':>11s} {'**주문**':>13s}")
    rows = {}
    order_total = 0.0
    for k in se.LEG_T:
        t = tgt[k]
        after = t["face"] * scale
        signed = after * t["side"]
        prev_signed = prev["legs"][k]["signed_face"] if prev else 0.0
        delta = signed - prev_signed
        order_total += abs(delta)
        side = "리시브" if t["side"] > 0 else ("페이" if t["side"] < 0 else "없음")
        act = "—" if abs(delta) < MIN_TICKET else (f"페이 {abs(delta)/1e8:,.1f}억" if delta < 0 else f"리시브 {abs(delta)/1e8:,.1f}억")
        print(f"  {k:5s} {t['dv01']/1e4:9,.1f}만 {t['face']/1e8:10,.1f}억 {after/1e8:10,.1f}억 {side:>6s} "
              f"{prev_signed/1e8:10,.1f}억 {act:>13s}")
        rows[k] = {"dv01": t["dv01"], "pv01": t["pv01"], "face": t["face"],
                   "face_after": after, "side": t["side"], "signed_face": signed, "delta": delta}
    print(f"  {'합':5s} {'':10s} {face_total/1e8:10,.1f}억 {face_total*scale/1e8:10,.1f}억 {'':6s} {'':11s} "
          f"{'회전 ' + format(order_total/1e8, ',.1f') + '억':>13s}")
    print()
    print(f"  증거금 소요 {face_total*scale*RATE/1e8:.2f}억  (평균회귀 {w4['mr_margin']/1e8:.2f}억 · 여력 {w4['headroom']/1e8:.2f}억)")
    print(f"  ⚠ 부호: 계열이 −bp 라 DV01 이 양(+)이면 **리시브**다. 표의 「주문」은 어제와의 차이다.")
    print(f"  ⚠ {MIN_TICKET/1e8:.0f}억 미만 차이는 «—» 로 두고 안 친다.")
    if not scored:
        print(f"  ⚠ 채점 창은 {sm.FREEZE_DATE} 다음 영업일부터다 — 오늘 기록은 연습이다.")

    if not a.dry:
        led["rows"].append({"run": date.today().isoformat(), "date": d, "scale": scale,
                            "mult": meta["mult"], "face_total": face_total,
                            "face_after": face_total * scale, "margin": face_total * scale * RATE,
                            "mr_margin": w4["mr_margin"], "headroom": w4["headroom"],
                            "scored": scored, "legs": rows})
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps(led, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
        print(f"\n  → {LEDGER}  ({len(led['rows'])}일치)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
