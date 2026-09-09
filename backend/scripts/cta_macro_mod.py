# -*- coding: utf-8 -*-
r"""추세를 매크로로 **변조**하면 나아지나 — Macrosynergy 설계의 원화 실측 [OWNER 2026-09-09].

## 무엇이 다른가 — 병렬(AQR)이 아니라 변조(Macrosynergy)

    AQR (Brooks 2017)      추세북 + 매크로북 «병렬», 손익 50/50      ← cta_macro.py 가 한 것
    Macrosynergy           추세 신호를 매크로 순풍/역풍으로 «변조»    ← 이 파일

병렬판에는 구조적 흠이 하나 있었다. 매크로북이 **43.8% 의 날 신호 0**(네 테마가
2:2 로 갈린다)이라 그날 포지션이 없고, 낙폭 개선의 얼마가 「신호」이고 얼마가
「그냥 안 걸었다」인지 가를 수가 없다. 0 의 «위치»까지 보존한 위약을 못 넘었다
(p=0.135)는 것이 그 말이다.

**변조는 그 흠을 구조적으로 없앤다.** 매크로가 0 이면 계수가 1 이 되어 추세가
그대로 간다 — 쉬는 날이 생기지 않는다. 노출은 추세북과 사실상 같고, 바뀌는 것은
**크기의 배분**뿐이다. 그래서 「낙폭이 준 것이 신호냐 노출 축소냐」라는 질문이
성립하지 않는다. 이 파일의 ③ 이 그것을 수치로 확인한다.

## 변조 공식 — 우리가 고른 것이 아니다

Macrosynergy 가 공개한 형태 그대로다:

    계수 = 2 / (1 + 7^(-x))          x = 매크로 지지 점수
    변조된 추세 = 추세 × (계수 if 추세>0 else 2 − 계수)

`7` 은 우리가 맞춘 값이 아니라 그쪽 규격(「x=±1 에서 계수 0.25·1.75」)에서
역산되는 상수다(ln 7 = 1.9459). x=0 이면 계수 1 — 매크로가 침묵하면 추세가
손대지 않은 채 간다. 부호가 추세와 갈리면 최대 0 까지 줄고, 맞으면 최대 2 배까지
키운다. **비대칭이 아니라 대칭**이라는 것이 게이팅과의 차이다.

두 번째 형태(「균형」)도 같이 잰다 — 추세와 매크로의 **신호 수준 평균**이다.
AQR 의 손익 수준 50/50 과 다른 자리에 있으므로 셋을 나란히 놓아야 읽힌다.

## 지지 점수로 무엇을 넣나 [자유도 회계]

`macro_sign`(네 테마 부호 평균, ∈ {−1,−½,0,½,1})을 **주 판정으로 쓴다.** 이유는
손잡이가 하나도 안 늘기 때문이다 — 이미 동결된 표제 신호이고 ±1 눈금 위에 있어
Macrosynergy 규격에 그대로 맞는다. `macro_z` 는 이 표본에서 표준편차가 0.337 뿐이라
그대로 넣으면 계수가 1±0.15 로 눌려 변조가 사실상 꺼진다 — 표준화 창을 새로 열어야
하고 그건 손잡이가 하나 느는 것이다. 그래서 **부수**로만 낸다(확장창 표준화, 룩어헤드 없음).

## ⚠ 이건 사전등록이 아니다 · 동결된 PREREG.md 는 건드리지 않는다

`data\krw-macro-vintage\PREREG.md` 는 **병렬 설계**를 동결한 것이고 채점은
2026-09-09 이후 영업일뿐이다. 변조는 **다른 설계**이므로 그 사전등록의 채점이
아니며, 지금 이 파일은 「사전등록할 값어치가 있는가」까지만 답한다.

⚠ Macrosynergy 는 그 자료를 파는 회사다(이해상충). 보고된 것은 전부 백테스트다.

돌리기:  python -m scripts.cta_macro_mod
"""

from __future__ import annotations

import math
import random
import statistics as st

from app import ctabacktest as cta
from scripts.cta_macro import (BARS, BOOK_VOL_WINDOW, LOOKBACKS, TARGET_VOL,
                               VOL_WINDOW, blend, card, corr, load_macro,
                               load_prices)

#: 로지스틱 기울기. Macrosynergy 규격 「x=±1 에서 0.25·1.75」의 역산값이고
#: **우리가 고른 값이 아니다.** 민감도는 ⑥ 에서 격자로 보이되 고르지 않는다.
LOGIT_BASE = 7.0


def coef(x: float, base: float = LOGIT_BASE) -> float:
    """매크로 지지 점수 → 0~2 의 변조 계수. x=0 이면 정확히 1."""
    return 2.0 / (1.0 + base ** (-x))


def modulate(trend: float, support: float, base: float = LOGIT_BASE) -> float:
    """Macrosynergy 「modified trend」. 추세가 숏이면 계수를 1 에 대해 접는다."""
    if trend == 0.0:
        return 0.0
    c = coef(support, base)
    return trend * (c if trend > 0 else 2.0 - c)


def trend_signals(series) -> dict[str, dict[str, float]]:
    """엔진이 **내부에서 만드는 것과 같은** 추세 신호를 밖으로 꺼낸다.

    `book_simulate(continuous=True)` 는 룩백별 `signal_continuous` 를 등가중
    평균한다. 그 계산을 여기서 똑같이 재현해야 「변조판과 추세판의 차이가
    변조뿐」이라고 말할 수 있다 — ① 의 항등 검사가 그것을 증명한다.
    """
    out: dict[str, dict[str, float]] = {}
    for key, (dates, px) in series.items():
        sigs = [cta.signal_continuous(px, "macross", lb) for lb in LOOKBACKS]
        out[key] = {d: st.fmean([sg[j] for sg in sigs]) for j, d in enumerate(dates)}
    return out


def run_book(series, rolls, *, external=None, continuous=True):
    return cta.book_simulate(
        series, signal="macross", lookbacks=LOOKBACKS, vol_window=VOL_WINDOW,
        target_book_vol_krw=TARGET_VOL, book_vol_window=BOOK_VOL_WINDOW,
        roll_days=rolls, continuous=continuous, external_signals=external)


def apply_mod(trend: dict[str, dict[str, float]], support: dict[str, float],
              *, base: float = LOGIT_BASE) -> dict[str, dict[str, float]]:
    """계약마다 `{날짜: 변조된 추세}`. 매크로가 없는 날은 **손대지 않는다**(계수 1)."""
    return {k: {d: modulate(v, support.get(d, 0.0), base) for d, v in s.items()}
            for k, s in trend.items()}


def apply_balance(trend: dict[str, dict[str, float]],
                  support: dict[str, float]) -> dict[str, dict[str, float]]:
    """「균형」 — 신호 수준에서 반씩. 매크로 없는 날은 추세만(0 과 섞지 않는다)."""
    out = {}
    for k, s in trend.items():
        out[k] = {d: ((v + support[d]) / 2.0 if d in support else v)
                  for d, v in s.items()}
    return out


def flat_share(book: dict, start: str) -> float:
    """포지션이 **하나도 없는** 날의 비중. 변조의 요점이 이 숫자에 있다."""
    idx = [i for i, t in enumerate(book["dates"]) if t >= start]
    if not idx:
        return 0.0
    flat = sum(1 for i in idx if all(book["pos"][k][i] == 0.0 for k in book["pos"]))
    return flat / len(idx)


def gross(book: dict, start: str) -> float:
    """하루 평균 총액면(억). 「0 이 아니다」와 「크다」는 다른 질문이라 따로 잰다.

    무포지션 일수가 0% 여도 액면이 반토막이면 그건 여전히 «노출 축소»다.
    A3 비판을 진짜로 닫으려면 이 숫자가 추세판과 비슷해야 한다.
    """
    idx = [i for i, t in enumerate(book["dates"]) if t >= start]
    if not idx:
        return 0.0
    return st.fmean([sum(abs(book["pos"][k][i]) for k in book["pos"]) for i in idx]) / 1e8


def turnover(book: dict, start: str) -> float:
    """하루 평균 |액면 변화| ÷ 평균 |액면|. 변조가 회전을 얼마나 늘리나."""
    idx = [i for i, t in enumerate(book["dates"]) if t >= start]
    chg = notion = 0.0
    for k, pos in book["pos"].items():
        for i in idx:
            prev = pos[i - 1] if i else 0.0
            chg += abs(pos[i] - prev)
            notion += abs(pos[i])
    return chg / notion if notion else 0.0


def line(name: str, s: dict) -> str:
    def f(x, w=7, p=2):
        return f"{x:>{w}.{p}f}" if isinstance(x, (int, float)) else f"{'—':>{w}}"
    return (f"  {name:<24}{f(s['annPnlKrw']/1e4, 9, 0)}{f(s['annVolKrw']/1e4, 9, 0)}"
            f"{f(s['maxDrawdown']/1e4, 9, 0)}{f(s['sharpe'])}{f(s['calmar'])}"
            f"{f(s['sortino'])}{f(s['ulcer']/1e4, 9, 0)}")


HDR = (f"  {'':<24}{'연손익':>9}{'연변동':>9}{'최대낙폭':>9}"
       f"{'Sharpe':>7}{'Calmar':>7}{'Sortino':>7}{'Ulcer':>9}")


def vol_matched(pts: list[dict], ref: list[dict]) -> list[dict]:
    """Man(Hamill-Rattray-van Hemert 2016) Figure 7 의 규약 — 비교 전에 **사후
    변동성을 기준판에 맞춘다.** 안 맞추면 「덜 걸어서 덜 아팠던 것」이 개선으로
    보인다. 이 데스크가 2026-09-08 게이팅 레인에서 배운 것과 같은 규율이다.
    """
    a = st.pstdev([p["dailyPnl"] for p in pts])
    b = st.pstdev([p["dailyPnl"] for p in ref])
    g = (b / a) if a > 0 else 1.0
    return [{"t": p["t"], "dailyPnl": p["dailyPnl"] * g,
             "barCost": p["barCost"] * g} for p in pts]


def expanding_z(support: dict[str, float], *, minobs: int = 250) -> dict[str, float]:
    """확장창 표준화 — **그날까지만** 본다. `macro_z` 를 ±1 눈금으로 옮길 때만 쓴다."""
    days = sorted(support)
    out: dict[str, float] = {}
    for i, d in enumerate(days):
        seg = [support[x] for x in days[:i + 1]]
        if len(seg) < minobs:
            continue
        sd = st.pstdev(seg)
        if sd > 0:
            out[d] = (support[d] - st.fmean(seg)) / sd
    return out


def main() -> int:
    series, rolls = load_prices()
    macro = load_macro()
    if not macro["macro_sign"]:
        raise SystemExit("매크로 신호가 비었어요 — build_themes.py 를 먼저 돌리세요")

    start = min(macro["macro_sign"])
    keys = list(series)
    trend = trend_signals(series)
    sign = macro["macro_sign"]

    print("\n=== 추세 변조(Macrosynergy) 대 병렬 50/50(AQR) · KTB3+KTB10 ===")
    print(f"창 {start} ~ · 북 변동성 목표 하루 {TARGET_VOL/1e4:,.0f}만원 "
          f"· 편도 {cta.COST_TICKS}틱 · 롤 왕복 1틱")
    print(f"변조 계수 = 2/(1+{LOGIT_BASE:.0f}^(−x)) · 지지 점수 x = macro_sign\n")

    # ── ① 배관 항등 검사 — 이걸 통과 못 하면 아래 전부가 뜻이 없다 ──────────
    #
    # 추세 신호를 «밖에서 만들어» external_signals 로 태우면 엔진이 내부에서
    # 만든 추세북과 **한 원까지 같아야** 한다. 같지 않으면 내가 재현한 신호가
    # 엔진의 그것이 아니라는 뜻이고, 변조판과 추세판의 차이를 변조 탓으로
    # 돌릴 수 없다.
    b_int = run_book(series, rolls, continuous=True)
    b_ext = run_book(series, rolls, external=trend)
    d_int = {p["t"]: p["dailyPnl"] for p in b_int["points"] if p["t"] >= start}
    d_ext = {p["t"]: p["dailyPnl"] for p in b_ext["points"] if p["t"] >= start}
    gap = max(abs(d_int[t] - d_ext.get(t, 0.0)) for t in d_int)
    scale = max(abs(v) for v in d_int.values())
    print(f"① 배관 항등 — 추세를 외부신호로 태운 것 대 엔진 내부판")
    print(f"   최대 일별 손익 차 {gap:,.6f}원 (일별 손익 최대 {scale:,.0f}원) "
          f"→ {'항등 성립' if gap < 1e-6 else '★불일치 — 아래 결과 읽지 말 것'}")
    if gap >= 1e-6:
        return 1

    # ── ② 본 비교 ────────────────────────────────────────────────────────
    b_macro = run_book(series, rolls, external={k: sign for k in keys})
    b_mod = run_book(series, rolls, external=apply_mod(trend, sign))
    b_bal = run_book(series, rolls, external=apply_balance(trend, sign))

    def clip(b):
        return [p for p in b["points"] if p["t"] >= start]

    pts = {
        "추세 단독": clip(b_int),
        "매크로 단독": clip(b_macro),
        "변조 (Macrosynergy)": clip(b_mod),
        "균형 (신호 평균)": clip(b_bal),
    }
    pts["50/50 병렬 (AQR)"] = blend(pts["추세 단독"], pts["매크로 단독"])
    order = ["추세 단독", "매크로 단독", "50/50 병렬 (AQR)",
             "변조 (Macrosynergy)", "균형 (신호 평균)"]

    print("\n② 본 비교 (금액 단위 만원)")
    print(HDR)
    cards = {}
    for k in order:
        cards[k] = card(pts[k])
        print(line(k, cards[k]))

    print("\n   Man Figure 7 규약 — 추세 단독에 **사후 변동성을 맞춘 뒤** 다시")
    print(HDR)
    for k in ("50/50 병렬 (AQR)", "변조 (Macrosynergy)", "균형 (신호 평균)"):
        print(line(k + " ·vol맞춤", card(vol_matched(pts[k], pts["추세 단독"]))))

    print(f"\n   상관 — 변조 대 추세 : {corr(pts['변조 (Macrosynergy)'], pts['추세 단독']):+.3f}"
          f" · 변조 대 매크로 : {corr(pts['변조 (Macrosynergy)'], pts['매크로 단독']):+.3f}")

    # ── ③ 변조가 흠을 없앴나 — 노출·회전 ──────────────────────────────────
    #
    # 병렬판의 약점은 매크로북이 43.8% 를 쉰다는 것이었다. 변조판이 추세판과
    # 같은 노출을 유지한다면 그 비판 자체가 성립하지 않는다.
    print("\n③ 노출 — 「낙폭이 준 것이 신호냐 안 걸어서냐」가 성립하나")
    print(f"  {'':<24}{'무포지션 일수':>14}{'평균 총액면(억)':>16}{'평균 회전':>11}")
    for name, b in (("추세 단독", b_int), ("매크로 단독", b_macro),
                    ("변조 (Macrosynergy)", b_mod), ("균형 (신호 평균)", b_bal)):
        print(f"  {name:<24}{100*flat_share(b, start):>13.1f}%"
              f"{gross(b, start):>16,.2f}{turnover(b, start):>11.4f}")
    print("   ★ 무포지션 0% 는 필요조건일 뿐이다 — 총액면이 반토막이면 그것도 노출 축소다.")

    # ── ④ 위약 — 지속성은 두고 정렬만 깬다 ────────────────────────────────
    #
    # 규약(2026-09-08): 위약은 «무엇을 깨나»가 아니라 «무엇을 보존하나»로 짠다.
    # 순환이동은 자기상관·롱숏비중·회전을 전부 보존한 채 가격과의 정렬만 깬다.
    #
    # **두 갈래 다 돌린다.** 좋아 보이는 쪽만 검정하면 그게 곧 선택 편향이고,
    # 나빠 보이는 쪽만 검정하면 살아남은 것을 못 잡는다.
    days = sorted(sign)
    g = random.Random(0)

    def battery(name: str, make, draws: int = 20) -> None:
        # 20회로는 도달 가능한 최소 p 가 1/21 = 0.048 이라 「0.10 이냐 0.02 냐」를
        # 못 가른다. **살아남은 갈래만** 200회로 올린다 — 죽은 갈래(p≈0.43)에
        # 계산을 더 쓰는 것은 답이 안 바뀌는 자리에 쓰는 것이다.
        offsets = sorted(g.sample(range(120, len(days) - 120), draws))
        print(f"\n④ 위약 — 매크로를 순환이동 {draws}회 · 대상 「{name}」")
        shuf = []
        for off in offsets:
            moved = {days[i]: sign[days[(i + off) % len(days)]] for i in range(len(days))}
            shuf.append(card(clip(run_book(series, rolls, external=make(moved)))))
        real = cards[name]
        for metric in ("sharpe", "calmar"):
            vals = sorted(c[metric] for c in shuf if c[metric] is not None)
            beat = sum(1 for v in vals if v >= real[metric])
            p95 = vals[int(0.95 * (len(vals) - 1))]
            print(f"   {metric:<7} 실측 {real[metric]:.2f} · 위약 평균 {st.fmean(vals):.2f}"
                  f" · 95백분위 {p95:.2f} · 실측을 넘은 위약 {beat}/{len(vals)}"
                  f"  → p ≈ {(beat + 1) / (len(vals) + 1):.3f}")
        flip = {d: -v for d, v in sign.items()}
        lag1 = {days[i]: sign[days[i - 1]] for i in range(1, len(days))}
        print(HDR)
        print(line(f"{name} ·부호반대", card(clip(run_book(series, rolls,
                                                        external=make(flip))))))
        print(line(f"{name} ·1일 지연", card(clip(run_book(series, rolls,
                                                       external=make(lag1))))))

    battery("변조 (Macrosynergy)", lambda s: apply_mod(trend, s))
    battery("균형 (신호 평균)", lambda s: apply_balance(trend, s), draws=200)

    # ── ⑤ 표본 반 가르기 ─────────────────────────────────────────────────
    common = sorted(d_int)
    mid = common[len(common) // 2]
    print(f"\n⑤ 표본 반 가르기 (경계 {mid})")
    print(f"  {'':<24}{'전반 Sharpe':>13}{'후반 Sharpe':>13}"
          f"{'전반 Calmar':>13}{'후반 Calmar':>13}")
    for name in order:
        h1 = card([p for p in pts[name] if p["t"] < mid])
        h2 = card([p for p in pts[name] if p["t"] >= mid])

        def f(x):
            return f"{x:>13.2f}" if isinstance(x, (int, float)) else f"{'—':>13}"
        print(f"  {name:<24}{f(h1['sharpe'])}{f(h2['sharpe'])}"
              f"{f(h1['calmar'])}{f(h2['calmar'])}")

    # ── ⑥ 민감도 — 고르는 것이 아니라 보이는 것 ──────────────────────────
    #
    # 로지스틱 기울기는 Macrosynergy 규격에서 온 값이지 우리가 맞춘 값이 아니다.
    # 격자를 내는 이유는 **고르기 위해서가 아니라** 결론이 그 값 하나에 매달려
    # 있는지 보기 위해서다. 여기서 1등을 채택하면 그 순간 자유도를 쓴 것이 된다.
    print("\n⑥ 민감도 — 로지스틱 기울기 (★고르지 않는다)")
    print(HDR)
    for base in (2.0, 3.0, 5.0, 7.0, 10.0, 20.0):
        bb = run_book(series, rolls, external=apply_mod(trend, sign, base=base))
        mark = " ←규격" if base == LOGIT_BASE else ""
        print(line(f"변조 base={base:.0f}{mark}", card(clip(bb))))

    # ── ⑦ 부수 — 지지 점수를 macro_z 로 (확장창 표준화) ──────────────────
    print("\n⑦ 부수 — 지지 점수를 macro_z 로 (확장창 표준화, 룩어헤드 없음)")
    print(HDR)
    zs = expanding_z(macro["macro_z"])
    if zs:
        bz = run_book(series, rolls, external=apply_mod(trend, zs))
        print(line("변조 ·macro_z", card(clip(bz))))
        print(line("변조 ·macro_z ·vol맞춤",
                   card(vol_matched(clip(bz), pts["추세 단독"]))))
        raw_sd = st.pstdev(list(macro["macro_z"].values()))
        print(f"   원 macro_z 표준편차 {raw_sd:.3f} — 표준화 없이는 계수가 "
              f"{coef(raw_sd):.2f}/{coef(-raw_sd):.2f} 로 눌려 변조가 사실상 꺼진다")
    else:
        print("   확장창 표본이 부족해요")

    # ── ⑧ 변조가 왜 거의 아무 일도 안 하나 ───────────────────────────────
    #
    # 지지 점수가 **계열 하나**라 계수가 그날 두 계약에 똑같이 곱해진다. 곧
    # 변조는 북 전체의 «총 크기»를 시간에 따라 흔드는 것일 뿐이고, 그 위에서
    # 북 변동성 목표가 다시 총 크기를 목표에 맞춘다 — 되돌린다. 방향은 한 번도
    # 안 바뀐다(계수가 음수가 될 수 없으므로). 그래서 상관이 0.977 이 된다.
    #
    # Macrosynergy 가 이 설계로 이득을 본 자리는 시장이 여럿이고 매크로 점수가
    # **시장마다 다른** 횡단면이다. 우리는 방향성 계약이 둘이고 매크로가 하나다.
    print("\n⑧ 변조는 왜 되돌려지나 — 북 변동성 목표와의 상쇄")
    fac = [coef(sign.get(t, 0.0)) for t in b_int["dates"] if t >= start]
    fac = [f if f else 1.0 for f in fac]
    sc_i = [s for t, s in zip(b_int["dates"], b_int["scale"]) if t >= start]
    sc_m = [s for t, s in zip(b_mod["dates"], b_mod["scale"]) if t >= start]
    ratio = [m / i for m, i in zip(sc_m, sc_i) if i > 0]
    fac_live = [f for f, i in zip(fac, sc_i) if i > 0]
    print(f"   변조 계수 — 평균 {st.fmean(fac_live):.3f} · 표준편차 {st.pstdev(fac_live):.3f}"
          f" · 범위 {min(fac_live):.2f}~{max(fac_live):.2f}")
    print(f"   북 스케일 비 (변조/추세) — 평균 {st.fmean(ratio):.3f}"
          f" · 표준편차 {st.pstdev(ratio):.3f}")
    prod = [f * r for f, r in zip(fac_live, ratio)]
    print(f"   둘의 곱 — 평균 {st.fmean(prod):.3f} (1 에 가까울수록 완전히 되돌려진 것)")
    print(f"   방향이 바뀐 날 0 건 — 계수는 음수가 될 수 없다(0~2). "
          f"변조는 «크기»만 건드린다.")

    # ── ⑨ 균형은 AQR 50/50 과 다른 것인가 · 이득이 타이밍인가 ─────────────
    #
    # 둘 다 「반씩」이지만 «어디서» 반씩인지가 다르다. AQR 은 두 북을 따로 돌려
    # **손익**을 반씩 섞고, 균형은 **신호**를 반씩 섞은 뒤 한 북으로 돌린다.
    # 신호에서 섞으면 두 신호가 갈릴 때 포지션 자체가 줄고, 그 상태에서 북
    # 변동성 목표가 다시 크기를 맞춘다 — 손익에서 섞을 때는 안 일어나는 일이다.
    print("\n⑨ 균형 대 AQR 50/50 — 같은 것인가")
    print(f"   상관 — 균형 대 50/50 병렬 : "
          f"{corr(pts['균형 (신호 평균)'], pts['50/50 병렬 (AQR)']):+.3f}")
    print(f"   상관 — 균형 대 추세 : {corr(pts['균형 (신호 평균)'], pts['추세 단독']):+.3f}"
          f" · 균형 대 매크로 : {corr(pts['균형 (신호 평균)'], pts['매크로 단독']):+.3f}")

    # 정적 대 타이밍 — 「그냥 그 기간에 숏이 맞았던 것 아닌가」에 답한다.
    # 손익 = 평균포지션 × 총수익  +  (포지션 − 평균) × 수익
    print("\n   정적 대 타이밍 (비용 전, 만원)")
    print(f"  {'':<24}{'총손익':>10}{'정적':>10}{'타이밍':>10}{'숏 비중':>9}")
    px_by = {k: dict(zip(d, p)) for k, (d, p) in series.items()}
    for name, book in (("추세 단독", b_int), ("매크로 단독", b_macro),
                       ("변조 (Macrosynergy)", b_mod), ("균형 (신호 평균)", b_bal)):
        bd = book["dates"]
        idx = [i for i, t in enumerate(bd) if t >= start]
        g_pnl = s_pnl = 0.0
        shorts = tot = 0
        for k in keys:
            seg = [book["pos"][k][i] for i in idx]
            avg = st.fmean(seg)
            shorts += sum(1 for x in seg if x < 0)
            tot += sum(1 for x in seg if x)
            for i in idx:
                if not i:
                    continue
                t0, t1 = bd[i - 1], bd[i]
                if t0 in px_by[k] and t1 in px_by[k]:
                    dp = px_by[k][t1] - px_by[k][t0]
                    g_pnl += book["pos"][k][i - 1] / 100.0 * dp
                    s_pnl += avg / 100.0 * dp
        print(f"  {name:<24}{g_pnl/1e4:>10,.0f}{s_pnl/1e4:>10,.0f}"
              f"{(g_pnl-s_pnl)/1e4:>10,.0f}{100*shorts/tot if tot else 0:>8.0f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
