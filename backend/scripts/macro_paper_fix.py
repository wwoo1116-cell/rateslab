# -*- coding: utf-8 -*-
r"""테마 둘을 **원논문 정의로 되돌린다** [OWNER 2026-09-11 「고칠 수 있는 거 고치자」].

    python -m scripts.macro_paper_fix            # 넷 다 · 원논문 판
    python -m scripts.macro_paper_fix --compare  # 지금 판과 나란히

## 원논문이 뭐라고 했나

Brooks, *A Half Century of Macro Momentum*(AQR 2017) Appendix B 를 그대로 옮기면:

    통화정책   "one-year changes in the front end of the yield curve.
               From 1992 onwards, I use **two-year yields**"
    위험선호   "one-year **equity market excess returns**"

우리 구현은 둘 다 어긋나 있었다.

    통화정책   국고 **1년물** 을 썼다          → 통안 **2년물** 로
    위험선호   주식 − 채권(듀레이션 8 근사)    → 주식 − **무위험(콜)**

## 왜 통안 2년인가

국고 2년(`ktb_2y`)은 ECOS 에 **2021-03 부터**만 있다(결측 56.7%). 그걸 쓰면 표본이
2,389봉 → 1,350봉으로 반토막 난다. 통안 2년(`msb_2y`)은 2017년부터 결측이 없고,
겹치는 1,351일에서 **1년 변화 상관 0.9991 · 부호 일치 98.9% · 수준차 평균 0.3bp**
라 사실상 같은 계열이다. 게다가 통안채는 **한국은행 자신의 발행물**이라 「통화정책」
테마에는 국고보다 오히려 맞다.

## 왜 이 수정이 «고르기» 가 아닌가

둘 다 **논문 정의로 되돌리는** 변경이다. 성과를 보고 고른 것이 아니라 원문과
대조해 어긋난 자리를 맞춘 것이고, 방향이 결과 이전에 정해져 있다.

곁들여 두 가지가 같이 풀린다.

  ① 국고 1년물은 원화 커브에서 고시가 뭉개진 구간이다(AR(1) **+0.145** · Δ=0
     4.9%). 통안 2년은 +0.033 · 2.1% 다. 「policy 테마만 이상하다」던 자리가
     원천 교체로 사라지는지가 이 스크립트의 물음 하나다.
  ② 지금 위험선호에는 `ktb_10y` 가 들어 있다 — **우리가 거래하는 그 자산**이
     신호 안에 있다. 논문 정의로 되돌리면 그 순환이 없어진다.

## 안 건드리는 것

경기순환·국제교역은 논문과 같다(OECD 빈티지 EX·CP 평균 · NEER 수출가중 로그 1년
변화). 부호 규약 넷, 룩백 250봉, `macro_sign` = 테마 평균도 그대로다.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import momentum as mo                                  # noqa: E402

PROJECTS = Path(r"C:\Users\infomax\Projects")
THEMES_CSV = Path(mo.THEMES_CSV).resolve()
RATES_CSV = PROJECTS / "data" / "ktb-supply" / "out" / "ecos_daily_rates.csv"

BARS_1Y = 250          # 논문의 "one-year" — 그 레인 상수와 같다
DUR_10Y = 8.0          # 지금 판이 쓰는 근사 듀레이션(비교용으로만 남긴다)


def _load() -> pd.DataFrame:
    if not THEMES_CSV.exists():
        raise SystemExit(f"테마 파일을 못 찾았어요 — {THEMES_CSV}")
    if not RATES_CSV.exists():
        raise SystemExit(f"ECOS 일별 금리를 못 찾았어요 — {RATES_CSV}")
    th = pd.read_csv(THEMES_CSV, encoding="utf-8-sig",
                     parse_dates=["date"]).set_index("date")
    rt = pd.read_csv(RATES_CSV, encoding="utf-8-sig",
                     parse_dates=["date"]).set_index("date")
    d = th.join(rt[["msb_2y", "ktb_2y", "call_1d"]], how="left")
    for c in ("msb_2y", "call_1d"):
        d[c] = d[c].ffill()
    return d


def themes(d: pd.DataFrame, *, paper: bool) -> pd.DataFrame:
    """네 테마의 부호와 `macro_sign`. `paper=True` 면 논문 정의다."""
    lb = BARS_1Y
    out = pd.DataFrame(index=d.index)

    # 경기순환 · 국제교역 — 논문과 같다. 그대로 쓴다.
    #: ⚠ CSV 의 cycle_raw 는 그 레인이 **이미 부호를 뒤집어** 저장한 값이다.
    #: 여기서 다시 뒤집으면 조용히 반대가 된다 — 그대로 쓴다.
    out["cycle_raw"] = d["cycle_raw"]
    out["trade_raw"] = np.log(d["neer"]).diff(lb)

    if paper:
        # 통화정책 — 논문: 2년 수익률의 1년 변화. 긴축(상승)이면 국채 숏 → 부호 −
        out["policy_raw"] = -(d["msb_2y"] - d["msb_2y"].shift(lb))
        # 위험선호 — 논문: 주식 «초과» 수익 1년. 무위험은 콜금리.
        rf = d["call_1d"].rolling(lb).mean() / 100.0
        out["risk_raw"] = -(np.log(d["kospi"]).diff(lb) - rf)
    else:
        out["policy_raw"] = -(d["ktb_1y"] - d["ktb_1y"].shift(lb))
        eq = np.log(d["kospi"]).diff(lb)
        bd = -DUR_10Y * (d["ktb_10y"] - d["ktb_10y"].shift(lb)) / 100.0
        out["risk_raw"] = -(eq - bd)

    names = ["cycle", "policy", "trade", "risk"]
    for t in names:
        out[t] = np.sign(out[f"{t}_raw"])
        out.loc[out[f"{t}_raw"].isna(), t] = np.nan
    out["n_themes"] = out[names].notna().sum(axis=1)
    out["macro_sign"] = out[names].mean(axis=1)
    out.loc[out["n_themes"] != 4, "macro_sign"] = np.nan
    return out


def as_signal(t: pd.DataFrame) -> dict[str, float]:
    """`external_signals` 가 먹는 꼴 — {날짜문자열: 값}."""
    s = t["macro_sign"].dropna()
    return {d.strftime("%Y-%m-%d"): float(v) for d, v in s.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", action="store_true")
    a = ap.parse_args()

    d = _load()
    new = themes(d, paper=True)
    old = themes(d, paper=False)

    print()
    print("── 원논문 정의로 되돌린 둘 ──")
    print("  통화정책  국고 1년물  →  통안 2년물"
          "   (논문: two-year yields, 1992~)")
    print("  위험선호  주식 − 채권  →  주식 − 무위험(콜)"
          "   (논문: equity market excess returns)")

    live = new["macro_sign"].dropna()
    print()
    print(f"  네 테마 완비 {len(live):,}일 · {live.index.min().date()}"
          f" ~ {live.index.max().date()}")

    if a.compare:
        names = ["cycle", "policy", "trade", "risk"]
        both = new[names].dropna().index.intersection(old[names].dropna().index)
        print()
        print(f"  {'테마':<8}{'부호 일치':>10}{'전환 지금':>10}{'전환 논문':>10}"
              f"{'롱비중 지금':>12}{'롱비중 논문':>12}")
        for t in names:
            a_, b_ = old.loc[both, t], new.loc[both, t]
            print(f"  {t:<8}{(a_ == b_).mean():>10.1%}"
                  f"{int((a_.diff() != 0).sum()):>10,}"
                  f"{int((b_.diff() != 0).sum()):>10,}"
                  f"{(a_ > 0).mean():>12.1%}{(b_ > 0).mean():>12.1%}")
        s_old = old.loc[both, "macro_sign"].dropna()
        s_new = new.loc[both, "macro_sign"].dropna()
        ix = s_old.index.intersection(s_new.index)
        print()
        print(f"  macro_sign 상관 {s_old.loc[ix].corr(s_new.loc[ix]):+.3f}"
              f" · 부호 일치 {(np.sign(s_old.loc[ix]) == np.sign(s_new.loc[ix])).mean():.1%}")
        print()
        print("  ★원천 계열의 성질 — 「policy 만 뭉개져 있다」가 풀리나")
        for c, lbl in (("ktb_1y", "지금 · 국고 1Y"), ("msb_2y", "논문 · 통안 2Y")):
            x = d[c].dropna().diff().dropna()
            print(f"    {lbl:<16} AR(1) {x.autocorr(1):+.3f} · Δ=0 {(x == 0).mean():5.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
