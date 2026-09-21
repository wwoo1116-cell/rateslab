# -*- coding: utf-8 -*-
r"""페이퍼 북 — **표본밖 기록**을 쌓는 자리.

[OWNER 2026-09-21 오후] "Strategy와 동일 위계로 존재하는 Portfolio Management
tab을 만들어서 거기에서 이제 우리가 테스트했던 걸 직접 페이퍼 트레이드를 할 수
있게, 그러니까 매일 PnL을 확인할 수 있게 환경을 하나 만들어다오."

## 이 화면이 없을 때 이 데스크에 없던 것

MR 계획면은 스스로 이렇게 적는다 — 「조건을 고른 창과 성과를 잰 창이 같아서
표본내 과적합이 붙어요」. 맞는 말이고, 그래서 그 화면의 1년 손익은 **성과가
아니라 고른 결과**다. 이 레인에 없던 것은 그 다음이다: **고른 뒤에 무슨 일이
일어났는가.**

페이퍼 북이 그 자리다. 등록하는 순간 조건을 **얼리고**, 그 뒤로는 시장만
움직인다. 하루가 지날 때마다 표본밖이 하루씩 길어진다. 이 파일이 지키는 단 하나의
규율이 그것이다 — **등록 뒤에는 조건을 다시 고르지 않는다**(레인 §10-5 의 그 규율).

## 북이 둘인 이유 [OWNER 선택 — "자동 북 + 수동 북 둘 다"]

    규칙 북   등록한 조건이 «시키는 대로» 한 것. 사람 손이 안 들어간다.
    수동 북   오너가 직접 잡은 것. 규칙을 안 따르는 판단도 들어간다.

둘을 나란히 두는 값어치는 **차이**에 있다. 규칙 북만 있으면 「이 규칙이 사나」를
알고, 둘이 있으면 「내 판단이 규칙보다 나은가」를 안다. 후자가 이 데스크가 실제로
묻는 물음이다.

## 산술을 새로 만들지 않는다 (레인 §10-8·§10-10)

여기에는 손익 공식이 **한 줄도 없다**. 규칙 북은 `mrbacktest.simulate` 가 낸 봉을
자르고(`mrmetrics.score`), 수동 북은 그 엔진의 거래 자리에 오너의 거래를 얹어
**같은 회계 함수**(`main._mr_real_accounting` → `cashbond.book_recon`)를 지난다.
두 번째 정의를 만들면 페이퍼 북과 계획면이 다른 수를 말하게 되고, 그 순간 이
화면은 대조가 아니라 세 번째 의견이 된다.

그래서 이 모듈은 **DB 를 모른다** — `mrplan` 과 같은 규약으로 `leg_of`·`grid_of`·
`account_of` 를 주입받는다. 시험이 합성 다리로 전부 돌 수 있는 이유이기도 하다.

## 저장은 파일 하나다

`backend/data/paper_book.json`. 이 리포에 쓰기 라우트가 **처음 생긴다** — 지금까지
사용자 상태는 전부 `localStorage` 였다(조달·백테스트 북·오버레이). 페이퍼 북을
브라우저에 두지 않는 이유는 둘이다: ①아침에 다른 자리에서 열어도 같은 북이어야
하고 ②캐시를 지워도 기록이 안 날아가야 한다. **기록이 날아가는 장부는 장부가
아니다.**

⚠ 이 파일은 리포 내용이 아니라 **데스크 상태**라 `.gitignore` 에 있다.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Callable

from . import mrmetrics as mrm

#: 장부 파일. 리포 밖이 아니라 `backend/data/` 인 이유는 백업·이관이 한 자리에서
#: 끝나기 때문이다(`krwswapdata` 와 같은 칸).
STORE = Path(__file__).resolve().parent.parent / "data" / "paper_book.json"

#: 계획면과 **같은** 비용·Delta. 다른 값을 쓰면 두 화면이 같은 거래에 다른 돈을
#: 매긴다 — 그러면 대조가 안 된다.
COST_BP = 0.5
NOTIONAL = 1_000_000.0

#: 빈 장부. `opened` 는 **첫 등록 때** 박힌다(파일을 만든 날이 아니다 — 아무것도
#: 등록 안 한 날부터 세면 표본밖 길이가 부풀어 오른다).
EMPTY: dict[str, Any] = {"opened": None, "enrolled": [], "trades": []}


# ── 저장 ────────────────────────────────────────────────────────────────────

def load(path: Path | None = None) -> dict[str, Any]:
    """장부를 읽는다. 없거나 깨졌으면 **빈 장부**다(예외를 안 던진다).

    깨진 파일에서 죽으면 화면이 통째로 빈다. 장부가 하나 없는 것과 화면이 없는
    것은 다른 사고라, 여기서는 빈 장부로 떨어지고 화면이 「비어 있다」를 적는다.
    """
    p = STORE if path is None else path
    try:
        got = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(EMPTY)
    if not isinstance(got, dict):
        return dict(EMPTY)
    return {**EMPTY, **got}


def save(store: dict[str, Any], path: Path | None = None) -> None:
    """**원자적으로** 쓴다 — 같은 디렉터리에 임시 파일을 만들고 갈아 끼운다.

    장부 한가운데서 죽으면 반쪽 JSON 이 남고, 그 다음 `load` 가 빈 장부를 내준다
    = 기록이 조용히 사라진다. `os.replace` 는 같은 볼륨에서 원자적이라 그 창이
    없다(윈도에서도 그렇다).
    """
    p = STORE if path is None else path
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── 쓰기 ────────────────────────────────────────────────────────────────────

def enroll(store: dict[str, Any], sid: str, knobs: dict, *,
           label: str = "", today: str | None = None) -> dict[str, Any]:
    """계열 하나를 규칙 북에 올린다 — **조건을 그 자리에서 언다**.

    이미 있으면 **안 덮어쓴다**. 덮어쓰면 표본밖 기록이 그 순간 사라지고(조건이
    바뀌면 그 전 손익은 다른 규칙의 것이다) 화면은 아무 말도 안 한다. 조건을
    갈고 싶으면 내렸다가 다시 올린다 — 그건 새 기록이라는 뜻이고, 그 사실이
    `opened` 에 남는다.
    """
    t = today or date.today().isoformat()
    if any(e["id"] == sid for e in store["enrolled"]):
        return store
    store["enrolled"] = [*store["enrolled"], {
        "id": sid, "label": label, "opened": t, "knobs": dict(knobs),
    }]
    if store.get("opened") is None:
        store["opened"] = t
    return store


def retire(store: dict[str, Any], sid: str) -> dict[str, Any]:
    """규칙 북에서 내린다. 기록은 **안 지운다** — 내린 날을 적는다.

    지워 버리면 「이 규칙은 한 번도 없었다」가 되고, 그건 진 규칙을 조용히 빼는
    가장 흔한 방법이다(생존 편향이 장부에 들어오는 자리).
    """
    store["enrolled"] = [
        {**e, "retired": e.get("retired") or date.today().isoformat()}
        if e["id"] == sid else e
        for e in store["enrolled"]
    ]
    return store


def add_trade(store: dict[str, Any], *, sid: str, direction: int, entry: str,
              notional: float = NOTIONAL, label: str = "",
              note: str = "") -> dict[str, Any]:
    """수동 북에 한 건. `exit` 는 비워 둔다(아직 들고 있다)."""
    store["trades"] = [*store["trades"], {
        "n": len(store["trades"]) + 1,
        "id": sid, "label": label, "dir": int(direction),
        "entry": entry, "exit": None,
        "notional": float(notional), "note": note,
    }]
    if store.get("opened") is None:
        store["opened"] = entry
    return store


def close_trade(store: dict[str, Any], n: int, exit_t: str) -> dict[str, Any]:
    """수동 북의 한 건을 닫는다. 지우는 것이 아니라 **닫는 것**이다."""
    store["trades"] = [{**t, "exit": exit_t} if t["n"] == n else t
                       for t in store["trades"]]
    return store


# ── 읽기(산술) ──────────────────────────────────────────────────────────────

def _slice(dates: list[str], points: list[dict], start_iso: str | None
           ) -> tuple[int, list[str], list[dict]]:
    """등록일 **이후 첫 봉**부터. 날짜로 자른다(봉 수로 세면 휴장이 길어진다).

    ⚠ **등록일 뒤에 봉이 하나도 없으면 빈 창이다.** `mrmetrics.index_at` 은 그
    자리에서 마지막 봉 하나를 남기는데(빈 구간을 안 만든다는 그쪽 규약) 여기서는
    그게 틀린 답이 된다 — 오늘 등록했는데 자료가 어제까지면, 그 마지막 봉은
    **등록 전의 하루**다. 그날 손익을 페이퍼 북에 얹으면 장부가 있지도 않았던
    날의 돈을 갖게 된다(실측 2026-09-21: 09-21 등록 · 마지막 봉 09-18).
    """
    if not dates:
        return 0, [], []
    if start_iso is not None and dates[-1] < start_iso:
        return len(dates), [], []
    i = mrm.index_at(dates, start_iso)
    return i, dates[i:], points[i:]


def rule_leg(sid: str, e: dict, *, leg_of: Callable[..., dict],
             cost_bp: float = COST_BP) -> dict:
    """등록된 계열 하나의 **표본밖 조각**.

    엔진은 전체 표본에서 한 번 돌고(룩백 워밍업이 구간 앞에 있어야 z 가 선다 —
    `mrmetrics` 머리 §구간) 채점만 등록일 이후로 자른다. `mrplan` 의 1년 성적이
    같은 규약이라 두 화면의 수가 같은 뜻이다.
    """
    leg = leg_of(sid, e["knobs"], accounting=True)
    r = leg["r"]
    dates = leg["dates"]
    i, wdates, wpoints = _slice(dates, r["points"], e["opened"])
    if not wdates:
        # 등록은 했는데 아직 그 뒤의 봉이 없다 — **0 이 아니라 «아직»** 이다.
        return {
            "id": sid, "label": e.get("label") or leg.get("label") or sid,
            "opened": e["opened"], "retired": e.get("retired"),
            "knobs": e["knobs"], "days": 0, "totalPnl": 0.0, "numTrades": 0,
            "winRate": None, "maxDrawdown": 0.0, "split": None, "open": None,
            "daily": [],
            "why": f"등록일({e['opened']}) 뒤의 봉이 아직 없어요 — 마지막 봉은 {dates[-1]} 이에요.",
        }
    perf = mrm.score(dates, r["points"], r["trades"], i, cost_bp)
    return {
        "id": sid,
        "label": e.get("label") or leg.get("label") or sid,
        "opened": e["opened"],
        "retired": e.get("retired"),
        "knobs": e["knobs"],
        "days": len(wdates),
        "totalPnl": perf["totalPnl"],
        "numTrades": perf["numTrades"],
        "winRate": perf["winRate"],
        "maxDrawdown": perf["maxDrawdown"],
        # 클릭 없이 분해가 선다 [OWNER 2026-09-09 — 계획면에 건 그 규율].
        "split": perf["split"],
        # 아직 안 닫힌 다리 — 페이퍼 북에서는 이것이 「지금 들고 있는 것」이다.
        "open": r.get("open"),
        "why": None,
        "daily": [{"t": t, "pnl": p["dailyPnl"]}
                  for t, p in zip(wdates, wpoints, strict=True)],
    }


def manual_leg(sid: str, trades: list[dict], *, leg_of: Callable[..., dict],
               account_of: Callable[..., bool] | None,
               knobs: dict, cost_bp: float = COST_BP) -> dict:
    """수동 거래를 **엔진의 회계 경로**에 얹는다.

    엔진이 낸 거래를 오너의 거래로 갈아 끼우고 같은 함수를 지난다. 그래서 평가·
    캐리·롤다운·조달의 뜻이 계획면과 한 자도 안 다르다(레인 §10-10).

    `account_of` 가 없거나 실패하면 **엔진 근사**로 떨어지고 그 사실을 `real` 이
    적는다 — 조용히 다른 수를 내지 않는다.
    """
    leg = leg_of(sid, knobs, accounting=False)
    dates, vals = leg["dates"], leg["vals"]
    at = {t: i for i, t in enumerate(dates)}
    last = dates[-1] if dates else None

    objs: list[dict] = []
    for tr in trades:
        i0 = at.get(tr["entry"])
        if i0 is None:
            continue                       # 그날 봉이 없다 — 조용히 빼되 아래에서 센다
        x = tr.get("exit") or last
        i1 = at.get(x)
        if i1 is None or i1 < i0:
            continue
        objs.append({
            "n": tr["n"], "dir": int(tr["dir"]),
            "entryT": dates[i0], "exitT": dates[i1],
            "entryV": vals[i0], "exitV": vals[i1],
            "bars": i1 - i0,
            "notional": float(tr.get("notional") or NOTIONAL),
            "open": tr.get("exit") is None,
        })

    # 엔진 근사 — 명목 × Δ스프레드 × 방향, 비용은 왕복.
    #   ⚠ 부호 규약: 값이 **−bp 파 금리**라 방향 +1 이 리시브다(`mr` 머리).
    #     여기서 규약을 다시 쓰지 않는다 — 엔진이 낸 `vals` 를 그대로 뺀다.
    for o in objs:
        gross = o["dir"] * (o["exitV"] - o["entryV"]) * o["notional"]
        cost = cost_bp * o["notional"] * (1.0 if o["open"] else 2.0)
        o["pnl"] = gross - cost
        o["mtm"] = gross
        o["cost"] = -cost

    real = False
    if account_of is not None and objs:
        try:
            real = bool(account_of(sid=sid, leg=leg, trades=objs,
                                   cost_bp=cost_bp))
        except BaseException:              # noqa: BLE001 — 회계가 못 서도 북은 선다
            real = False

    daily: dict[str, float] = {}
    for o in objs:
        # 봉마다 고르게 펴지 않는다 — 그건 없는 일별 곡선을 지어내는 것이다.
        # 회계가 붙은 거래는 `day` 를 들고 오고(실가격), 아니면 **청산일 한 점**에
        # 선다. 화면이 그 차이를 적는다(`real`).
        got = o.get("day")
        if got:
            for t, v in got.items():
                daily[t] = daily.get(t, 0.0) + v
        else:
            daily[o["exitT"]] = daily.get(o["exitT"], 0.0) + o["pnl"]

    def _sum(key: str) -> float | None:
        # 엔진 근사에는 롤다운·조달이 **없다**. 0 으로 적으면 「0 원이었다」는 딴
        # 사실이 되고, 화면의 «—» 가 사라진다(`parts.SplitColumn` 의 그 규약).
        got = [o.get(key) for o in objs]
        if any(v is None for v in got) or not got:
            return None
        return round(sum(float(v) for v in got), 2)

    return {
        "id": sid,
        "label": trades[0].get("label") or leg.get("label") or sid,
        "real": real,
        "split": {
            "mtm": _sum("mtm"), "carry": _sum("carry"),
            "rolldown": _sum("rolldown"), "funding": _sum("funding"),
            "cost": _sum("cost"),
            "total": round(sum(o["pnl"] for o in objs), 2),
        } if objs else None,
        "totalPnl": round(sum(o["pnl"] for o in objs), 2),
        "numTrades": len(objs),
        "openTrades": sum(1 for o in objs if o["open"]),
        "skipped": len(trades) - len(objs),
        "trades": objs,
        "daily": [{"t": t, "pnl": round(v, 2)} for t, v in sorted(daily.items())],
    }


def _roll(daily: list[dict]) -> list[dict]:
    """일별 → 누적. 화면이 다시 더하지 않게 서버가 끝낸다(§16)."""
    out, c = [], 0.0
    for d in daily:
        c += d["pnl"]
        out.append({"t": d["t"], "pnl": round(d["pnl"], 2), "cum": round(c, 2)})
    return out


def merge_split(legs: list[dict]) -> dict | None:
    """다리들의 분해를 더한다. 한 다리라도 못 잰 항이 있으면 **그 항은 `None`** 이다.

    섞어서 더하면 「실가격 셋 + 근사 하나」의 합이 실가격처럼 보인다.
    """
    got = [lg["split"] for lg in legs if lg.get("split")]
    if not got:
        return None
    out: dict[str, float | None] = {}
    for k in ("mtm", "carry", "rolldown", "funding", "cost", "total"):
        vals = [sp.get(k) for sp in got]
        out[k] = (None if any(v is None for v in vals)
                  else round(sum(float(v) for v in vals), 2))
    return out


def merge_daily(legs: list[dict]) -> list[dict]:
    """여러 다리의 일별을 **날짜 축 하나**로 모은다."""
    agg: dict[str, float] = {}
    for lg in legs:
        for d in lg["daily"]:
            agg[d["t"]] = agg.get(d["t"], 0.0) + d["pnl"]
    return _roll([{"t": t, "pnl": v} for t, v in sorted(agg.items())])


def build_sheet(*, leg_of: Callable[..., dict],
                account_of: Callable[..., bool] | None = None,
                store: dict[str, Any] | None = None,
                cost_bp: float = COST_BP) -> dict[str, Any]:
    """페이퍼 북 한 장 — 규칙 북 · 수동 북 · 둘의 차이.

    한 다리가 죽어도 나머지는 선다(`why` 에 사유가 남는다). 25계열을 도는 물건이
    아니라 **등록한 것만** 도는 물건이라 라우트가 동기로 끝난다.
    """
    st = load() if store is None else store
    live = [e for e in st["enrolled"] if not e.get("retired")]

    rule_legs, failed = [], []
    for e in st["enrolled"]:
        try:
            rule_legs.append(rule_leg(e["id"], e, leg_of=leg_of, cost_bp=cost_bp))
        except BaseException as exc:       # noqa: BLE001
            failed.append({"id": e["id"], "why": str(exc)})

    by_sid: dict[str, list[dict]] = {}
    for tr in st["trades"]:
        by_sid.setdefault(tr["id"], []).append(tr)
    man_legs = []
    for sid, trs in by_sid.items():
        # 수동 거래의 「노브」는 회계가 계열을 준비하는 데만 쓰인다 — 진입·청산은
        # 오너가 정했으므로 엔진의 시점 규칙은 이 북에 **안 들어온다**.
        e = next((x for x in st["enrolled"] if x["id"] == sid), None)
        knobs = (e or {}).get("knobs") or {
            "lookback": 60, "entryZ": 2.0, "exitZ": 0.5, "stopZ": 2.5,
            "entryMode": "level"}
        try:
            man_legs.append(manual_leg(sid, trs, leg_of=leg_of,
                                       account_of=account_of, knobs=knobs,
                                       cost_bp=cost_bp))
        except BaseException as exc:       # noqa: BLE001
            failed.append({"id": sid, "why": str(exc)})

    rule_daily = merge_daily(rule_legs)
    man_daily = merge_daily(man_legs)
    asof = max([d["t"] for d in rule_daily + man_daily], default=None)

    def _today(rows: list[dict]) -> float:
        return next((r["pnl"] for r in rows if r["t"] == asof), 0.0)

    rule_cum = rule_daily[-1]["cum"] if rule_daily else 0.0
    man_cum = man_daily[-1]["cum"] if man_daily else 0.0
    return {
        "opened": st.get("opened"),
        "asof": asof,
        "costBp": cost_bp,
        "notional": NOTIONAL,
        "rule": {
            "enrolled": len(live),
            "retired": len(st["enrolled"]) - len(live),
            "today": round(_today(rule_daily), 2),
            "cum": rule_cum,
            "legs": rule_legs,
            "split": merge_split(rule_legs),
            "daily": rule_daily,
        },
        "manual": {
            "trades": len(st["trades"]),
            "open": sum(lg["openTrades"] for lg in man_legs),
            "today": round(_today(man_daily), 2),
            "cum": man_cum,
            "legs": man_legs,
            "split": merge_split(man_legs),
            "daily": man_daily,
        },
        # 이 화면이 실제로 묻는 물음 — 내 판단이 규칙보다 나은가.
        "diff": {"today": round(_today(man_daily) - _today(rule_daily), 2),
                 "cum": round(man_cum - rule_cum, 2)},
        "failed": failed,
    }
