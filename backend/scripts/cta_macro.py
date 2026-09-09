# -*- coding: utf-8 -*-
r"""추세추종에 **매크로 모멘텀**을 붙이면 나아지나 — 원화 실측 [OWNER 2026-09-08].

## 무엇을 묻나

AQR(Brooks 2017)은 추세추종과 매크로 모멘텀을 반씩 섞으면 Sharpe 1.1 → 1.4,
최대낙폭이 절반이 된다고 보고한다. **그 표를 원화로 다시 그린다.** 신호 원천이
가격이냐 펀더멘털이냐만 다르고 나머지는 같아야 답이 뜻을 갖는다.

## 「나머지는 같다」를 어떻게 보장하나

`ctabacktest.book_simulate` 하나로 다섯을 전부 돌린다. 매크로판은
`external_signals` 로 신호만 갈아끼운다 — 크기 결정(포트폴리오 변동성 목표),
비용(편도 0.5틱 + 롤 왕복 1틱), 회계가 **한 글자도 안 바뀐다.** 그리고 다섯을
**같은 날짜 위에서** 채점한다(매크로가 늦게 시작하므로 추세도 그날부터 자른다).

## 매크로 신호는 어디서 오나

`Projects\data\krw-macro-vintage\out\macro_themes_daily.csv` — 네 테마의 부호
평균이고, 부호 규약은 그 파일 머리에 결과를 보기 전에 못박아 뒀다. 경기순환은
OECD `EDITION` 빈티지에서 오고 에디션은 다음 달 1일부터만 쓴다.

## ⚠ 이건 사전등록이 아니다

부호 넷을 내가 정했고(경제 논리이지 최적화는 아니나 여전히 내 선택이다),
표본 하나 위에서 잰다. **양수가 나와도 「된다」가 아니라 「사전등록할 값어치가
있다」까지가 최대다.** 음수면 그건 그것대로 결론이다.

돌리기:  python -m scripts.cta_macro
"""

from __future__ import annotations

import csv
import math
import os
import statistics as st

from app import ctabacktest as cta, futures, mrmetrics as mrm

#: backend/scripts → backend → sauron-v2 → apps → Projects
PROJECTS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "..", "..", "..", ".."))
LANE = os.path.join(PROJECTS, "data", "krw-macro-vintage", "out")
THEMES_CSV = os.path.join(LANE, "macro_themes_daily.csv")

LOOKBACKS = (20, 40, 60, 120, 250)
VOL_WINDOW = 60
BOOK_VOL_WINDOW = 120
TARGET_VOL = 1_000_000.0            # 북 전체의 하루 표준편차 100만원
BARS = 252
THEMES = ("cycle", "policy", "trade", "risk")


def load_prices():
    f = futures.load()
    out = {}
    for t in futures.FUT_TENORS:
        s = f.series[t]
        d = [x.isoformat() if hasattr(x, "isoformat") else str(x) for x in s.dates]
        px = list(s.price_adj)
        keep = [i for i, p in enumerate(px) if p is not None]
        out[t] = ([d[i] for i in keep], [float(px[i]) for i in keep])
    rolls = {x.isoformat() for x in futures.roll_days(list(f.series["3Y"].dates))}
    return out, rolls


def load_macro() -> dict[str, dict[str, float]]:
    """`{열이름: {날짜: 값}}`. 빈 칸은 안 담는다 — 없는 날은 포지션이 없다."""
    cols = ("macro_sign", "macro_z") + THEMES
    out: dict[str, dict[str, float]] = {c: {} for c in cols}
    with open(THEMES_CSV, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            day = row["date"][:10]
            for c in cols:
                v = row.get(c, "")
                if v not in ("", "NA", "nan"):
                    out[c][day] = float(v)
    return out


def sharpe(daily: list[float]) -> float | None:
    if len(daily) < 30:
        return None
    sd = st.pstdev(daily)
    return (st.fmean(daily) / sd * math.sqrt(BARS)) if sd > 0 else None


def clip(book: dict, dates: list[str], start: str) -> tuple[list[str], list[dict]]:
    pts = [p for p in book["points"] if p["t"] >= start]
    return [p["t"] for p in pts], pts


def blend(a: list[dict], b: list[dict], wa: float = 0.5) -> list[dict]:
    """두 장부를 날짜로 포개 가중합. AQR 의 50/50 이 이것이다."""
    bi = {p["t"]: p for p in b}
    out = []
    for p in a:
        q = bi.get(p["t"])
        if q is None:
            continue
        out.append({"t": p["t"],
                    "dailyPnl": wa * p["dailyPnl"] + (1 - wa) * q["dailyPnl"],
                    "barCost": wa * p["barCost"] + (1 - wa) * q["barCost"]})
    return out


def card(pts: list[dict]) -> dict:
    ds = [p["t"] for p in pts]
    s = mrm.score(ds, pts, [], 0, 0.0)
    daily = [p["dailyPnl"] for p in pts]
    s["sharpe"] = sharpe(daily)
    s["annVolKrw"] = st.pstdev(daily) * math.sqrt(BARS) if len(daily) > 1 else 0.0
    s["annPnlKrw"] = sum(daily) * BARS / len(daily) if daily else 0.0
    return s


def line(name: str, s: dict) -> str:
    def f(x, w=7, p=2):
        return f"{x:>{w}.{p}f}" if isinstance(x, (int, float)) else f"{'—':>{w}}"
    return (f"  {name:<22}{f(s['annPnlKrw']/1e4, 9, 0)}{f(s['annVolKrw']/1e4, 9, 0)}"
            f"{f(s['maxDrawdown']/1e4, 9, 0)}{f(s['sharpe'])}{f(s['calmar'])}"
            f"{f(s['sortino'])}{f(s['ulcer']/1e4, 9, 0)}")


def corr(a: list[dict], b: list[dict]) -> float | None:
    bi = {p["t"]: p["dailyPnl"] for p in b}
    xs, ys = [], []
    for p in a:
        q = bi.get(p["t"])
        if q is not None:
            xs.append(p["dailyPnl"])
            ys.append(q)
    if len(xs) < 30:
        return None
    mx, my = st.fmean(xs), st.fmean(ys)
    sx, sy = st.pstdev(xs), st.pstdev(ys)
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs) / (sx * sy)


def run_book(series, rolls, *, external=None, continuous=True):
    return cta.book_simulate(
        series, signal="macross", lookbacks=LOOKBACKS, vol_window=VOL_WINDOW,
        target_book_vol_krw=TARGET_VOL, book_vol_window=BOOK_VOL_WINDOW,
        roll_days=rolls, continuous=continuous, external_signals=external)


def main() -> int:
    series, rolls = load_prices()
    macro = load_macro()
    if not macro["macro_sign"]:
        raise SystemExit("매크로 신호가 비었어요 — build_themes.py 를 먼저 돌리세요")

    start = min(macro["macro_sign"])
    dates_all = sorted(set().union(*[set(d) for d, _p in series.values()]))
    common = [d for d in dates_all if d >= start and d in macro["macro_sign"]]
    print(f"\n=== 추세추종 대 매크로 모멘텀 · KTB3+KTB10 ===")
    print(f"창 {common[0]} ~ {common[-1]} · {len(common):,}일 ({len(common)/BARS:.1f}년)")
    print(f"북 변동성 목표 하루 {TARGET_VOL/1e4:,.0f}만원 · 편도 {cta.COST_TICKS}틱 "
          f"· 롤 왕복 1틱 · 신호 macross×5속도\n")

    keys = list(series)
    ext_all = {k: macro["macro_sign"] for k in keys}

    books = {
        "추세 연속(검증 구성)": run_book(series, rolls, continuous=True),
        "추세 부호": run_book(series, rolls, continuous=False),
        "매크로 모멘텀": run_book(series, rolls, external=ext_all),
    }
    pts = {k: [p for p in v["points"] if p["t"] >= start] for k, v in books.items()}
    pts["50/50 (연속+매크로)"] = blend(pts["추세 연속(검증 구성)"], pts["매크로 모멘텀"])
    pts["50/50 (부호+매크로)"] = blend(pts["추세 부호"], pts["매크로 모멘텀"])

    hdr = (f"  {'':<22}{'연손익':>9}{'연변동':>9}{'최대낙폭':>9}"
           f"{'Sharpe':>7}{'Calmar':>7}{'Sortino':>7}{'Ulcer':>9}")
    print("① 본 비교 (금액 단위 만원)")
    print(hdr)
    cards = {}
    for k in ("추세 연속(검증 구성)", "추세 부호", "매크로 모멘텀",
              "50/50 (연속+매크로)", "50/50 (부호+매크로)"):
        cards[k] = card(pts[k])
        print(line(k, cards[k]))

    print(f"\n  상관 — 추세(연속) 대 매크로 : "
          f"{corr(pts['추세 연속(검증 구성)'], pts['매크로 모멘텀']):+.3f}")
    print(f"  상관 — 추세(부호) 대 매크로 : "
          f"{corr(pts['추세 부호'], pts['매크로 모멘텀']):+.3f}")

    print("\n② 테마를 따로 — 어느 것이 지고 가나 (탐색용)")
    print(hdr)
    for t in THEMES:
        if not macro[t]:
            continue
        b = run_book(series, rolls, external={k: macro[t] for k in keys})
        p = [x for x in b["points"] if x["t"] >= start]
        print(line(t, card(p)))

    print("\n③ 연속판 매크로(z, 포화 2σ) — 부호 대신 강도를 쓰면")
    print(hdr)
    bz = run_book(series, rolls, external={k: macro["macro_z"] for k in keys})
    pz = [x for x in bz["points"] if x["t"] >= start]
    print(line("매크로 z", card(pz)))
    print(line("50/50 (연속+매크로z)", card(blend(pts["추세 연속(검증 구성)"], pz))))

    print("\n④ 낙폭 겹침 — 추세가 가장 아팠던 다섯 구간에서 매크로는")
    tr = pts["추세 연속(검증 구성)"]
    mc = {p["t"]: p["dailyPnl"] for p in pts["매크로 모멘텀"]}
    run = peak = 0.0
    dd_start = tr[0]["t"]
    spells: list[tuple[float, str, str]] = []
    for p in tr:
        run += p["dailyPnl"]
        if run >= peak:
            if peak - run < 0 and dd_start != p["t"]:
                pass
            peak = run
            dd_start = p["t"]
        else:
            spells.append((peak - run, dd_start, p["t"]))
    worst: list[tuple[float, str, str]] = []
    for depth, a, b in sorted(spells, key=lambda x: -x[0]):
        if all(b < wa or a > wb for _d, wa, wb in worst):
            worst.append((depth, a, b))
        if len(worst) == 5:
            break
    print(f"  {'구간':<26}{'추세 손익':>11}{'매크로 손익':>13}")
    for depth, a, b in worst:
        t_pnl = sum(p["dailyPnl"] for p in tr if a <= p["t"] <= b)
        m_pnl = sum(v for k, v in mc.items() if a <= k <= b)
        print(f"  {a}~{b:<12}{t_pnl/1e4:>11,.0f}{m_pnl/1e4:>13,.0f}")

    # ── ⑤ 검증 — 붙기 전에 배관과 룩어헤드를 턴다 ──────────────────────
    print("\n⑤ 검증")
    print(hdr)

    # (a) 신호를 하루 더 늦춘다. 1년 신호가 하루에 무너지면 그건 매크로가 아니다.
    lag1 = {}
    days = sorted(macro["macro_sign"])
    for i, day in enumerate(days):
        if i:
            lag1[day] = macro["macro_sign"][days[i - 1]]
    b = run_book(series, rolls, external={k: lag1 for k in keys})
    p_lag = [x for x in b["points"] if x["t"] >= start]
    print(line("(a) 매크로 1일 지연", card(p_lag)))
    print(line("    50/50 (지연판)", card(blend(pts["추세 연속(검증 구성)"], p_lag))))

    # (b) 부호를 전부 뒤집는다. 대칭이면 신호이고, 안 대칭이면 배관에 뭔가 있다.
    flip = {d: -v for d, v in macro["macro_sign"].items()}
    b = run_book(series, rolls, external={k: flip for k in keys})
    print(line("(b) 부호 전부 반대", card([x for x in b["points"] if x["t"] >= start])))

    # (c) 순환이동 위약 — **지속성은 그대로 두고** 가격과의 정렬만 깬다.
    #     매일 새로 뽑는 잡음은 회전이 폭발해 비용만 재는 통제가 된다(그건
    #     신호가 없다는 증거가 아니라 회전이 비싸다는 증거다). 실제 신호를
    #     통째로 밀면 자기상관·롱숏 비중·회전이 전부 보존된다.
    import random
    rnd = []
    g = random.Random(0)
    offsets = sorted(g.sample(range(120, len(days) - 120), 20))
    for off in offsets:
        shifted = {days[i]: macro["macro_sign"][days[(i + off) % len(days)]]
                   for i in range(len(days))}
        bb = run_book(series, rolls, external={k: shifted for k in keys})
        rnd.append(card([x for x in bb["points"] if x["t"] >= start]))
    print(f"  {'(c) 순환이동 20회 평균':<22}"
          f"{st.fmean(c['annPnlKrw'] for c in rnd)/1e4:>9,.0f}"
          f"{st.fmean(c['annVolKrw'] for c in rnd)/1e4:>9,.0f}"
          f"{st.fmean(c['maxDrawdown'] for c in rnd)/1e4:>9,.0f}"
          f"{st.fmean(c['sharpe'] for c in rnd):>7.2f}"
          f"{st.fmean(c['calmar'] for c in rnd if c['calmar'] is not None):>7.2f}"
          f"{st.fmean(c['sortino'] for c in rnd if c['sortino'] is not None):>7.2f}"
          f"{st.fmean(c['ulcer'] for c in rnd)/1e4:>9,.0f}")

    # (d) 표본 반 가르기 — 섞기의 이득이 두 반쪽에 다 있나
    mid = common[len(common) // 2]
    print(f"\n  표본 반 가르기 (경계 {mid})")
    print(f"  {'':<22}{'전반 Sharpe':>13}{'후반 Sharpe':>13}"
          f"{'전반 Calmar':>13}{'후반 Calmar':>13}")
    for name in ("추세 연속(검증 구성)", "매크로 모멘텀", "50/50 (연속+매크로)"):
        h1 = card([p for p in pts[name] if p["t"] < mid])
        h2 = card([p for p in pts[name] if p["t"] >= mid])
        def g(x):
            return f"{x:>13.2f}" if isinstance(x, (int, float)) else f"{'—':>13}"
        print(f"  {name:<22}{g(h1['sharpe'])}{g(h2['sharpe'])}"
              f"{g(h1['calmar'])}{g(h2['calmar'])}")

    # ── ⑥ 정적 대 타이밍 — 「그냥 계속 숏이었던 것 아닌가」에 답한다 ────────
    #
    # 매크로 신호는 1년 변화라 몇 달씩 안 바뀐다. 그러면 손익이 «타이밍» 이
    # 아니라 «표본 기간의 방향» 에서 왔을 수 있고, 그건 전혀 다른 주장이다.
    # 표준 분해:  손익 = 평균포지션 × 총수익 + (포지션 − 평균) × 수익
    print("\n⑥ 정적 대 타이밍 (비용 전, 만원)")
    print(f"  {'':<22}{'총손익':>10}{'정적':>10}{'타이밍':>10}"
          f"{'숏 비중':>9}{'평균액면(억)':>13}")
    px_by = {k: dict(zip(d, p)) for k, (d, p) in series.items()}
    for name, book in (("추세 연속(검증 구성)", books["추세 연속(검증 구성)"]),
                       ("매크로 모멘텀", books["매크로 모멘텀"])):
        bd = book["dates"]
        idx = [i for i, t in enumerate(bd) if t >= start]
        gross = static = 0.0
        shorts = tot = 0
        notion = []
        for k in keys:
            pos = book["pos"][k]
            seg = [pos[i] for i in idx]
            avg = st.fmean(seg)
            notion += [abs(x) for x in seg if x]
            shorts += sum(1 for x in seg if x < 0)
            tot += sum(1 for x in seg if x)
            for i in idx:
                if i == 0:
                    continue
                t0, t1 = bd[i - 1], bd[i]
                if t0 in px_by[k] and t1 in px_by[k]:
                    dp = px_by[k][t1] - px_by[k][t0]
                    gross += pos[i - 1] / 100.0 * dp
                    static += avg / 100.0 * dp
        print(f"  {name:<22}{gross/1e4:>10,.0f}{static/1e4:>10,.0f}"
              f"{(gross-static)/1e4:>10,.0f}{100*shorts/tot if tot else 0:>8.0f}%"
              f"{st.fmean(notion)/1e8 if notion else 0:>13.1f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
