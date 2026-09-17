# -*- coding: utf-8 -*-
r"""집행 준비 ③④⑤ — 매일의 W4 축소, 분기 점검, 연 1회 재채점 [OWNER 2026-09-15].

    python -m scripts.sleeve_monitor              # 오늘 할 것 전부
    python -m scripts.sleeve_monitor --daily      # ③ W4 배율만
    python -m scripts.sleeve_monitor --quarterly  # ④⑤ 관문·상관 점검
    python -m scripts.sleeve_monitor --annual     # W2 상향 조건

동결 등록서 `docs/PREREG_sleeve_5050_2026-09-15.md` (동결·재동결 2026-09-15 · 채점 2026-09-16~).
**이 스크립트는 규칙을 만들지 않는다** — 등록서의 W2·W3·W4 와 §3-6 을 집행 가능한 꼴로 옮길 뿐이다.

## ③ 매일 — W4 비례 축소

    여력_t = 100억 − 평균회귀가 그날 쓴 증거금(총위험 고정 배수 k_mr 적용)
    원한_t = 슬리브 액면(실측 pv01) × 5%
    배율_t = min(원한_t, 여력_t) / 원한_t          (≤ 1)

    ★손익에는 **전일 배율**을 건다. 오늘 포지션이 내일 변화를 먹으므로.
    ★평균회귀 쪽은 건드리지 않는다.

## ④ 분기 — 관문 셋 + 상관 경보

    관문   `momentum_irs_books` 판정문 셋을 다시 내고 DSR·PBO·위약을 본다.
           **하나라도 깨지면 그날부터 W3 (w = 0).** 첫 판정일을 안 기다린다.
    상관   롤링 250봉 상관이 **+0.3 을 6개월(≈126봉) 지속**하면 경보. 음의 방향은 경보가 아니다.

## ⑤ 연 1회 — W2 상향 조건 (셋 다여야 0.40)

    ① 결합 창 ≥ 2,520봉  ② w=0.40 의 P(ΔCalmar ≤ 0) < 0.05  ③ 게이트 셋 통과

⚠ 채점은 **동결 이후 손익만** 쓴다. 이 스크립트가 찍는 「채점 창」이 그것이고, 동결 전 구간은
   참고로만 같이 찍는다.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from scripts import crs_evaluate as ce                          # noqa: E402
from scripts import hedge_test as ht                            # noqa: E402
from scripts import momentum_irs_evaluate as mie                # noqa: E402
from scripts import momentum_irs_books as mib                   # noqa: E402
from scripts import sleeve_execution as se                      # noqa: E402

ANN = 252
CAP = 100e8
RATE = 0.05

# ── 동결 등록서의 상수 — 여기서 바꾸지 않는다 ──────────────────────────────
FREEZE_DATE = "2026-09-15"          # 동결일 (채점 시작 = 다음 영업일)
W_REGISTERED = 0.25                 # W1
W_UP = 0.40                         # W2 의 유일한 후보
BARS_FOR_W2 = 2520                  # W2 ①
P_FOR_W2 = 0.05                     # W2 ②
CORR_THRESHOLD = 0.30               # §3-6 모니터링 문턱 (양의 방향만)
CORR_PERSIST = 126                  # 6개월 지속
ROLL = 250
GATES = {"dsr": 0.95, "pbo": 0.50, "placebo": 0.05}

STATE = BACKEND / "output" / "sleeve_monitor_state.json"

#: ⑨ 「평균회귀가 그날 쓴 증거금」을 **어디서 받나** — W4 여력의 분모다.
#:
#:   allocator  그 레인의 배분기를 그대로 부른다. 규칙 B(효율가중 · `PREREG_03` §3.3) ·
#:              라이브 규약(적재가 멈춘 다리의 증거금은 안 푼다).
#:              자리: `data/krw-crs/src/margin_headroom.py`
#:   resim      이 리포가 다시 시뮬레이션한 규칙 **A**(균등 로트) 경로. 2026-09-15 까지
#:              쓰던 자리이고, 그 레인이 굴리는 규칙이 아니다. 대조로만 남긴다.
#:
#: ⚠ 이것은 등록서를 고치는 것이 아니다. W4 가 등록한 것은 «평균회귀가 그날 쓴 증거금»
#:   이라는 **말**이고, 그 말이 가리키는 자리는 처음부터 그 레인의 배분기였다.
MARGIN_SOURCE = "allocator"
MARGIN_SOURCES = ("allocator", "resim")


def _allocator():
    """그 레인의 배분기 모듈 — 없으면 None 을 주고 **조용히 넘어가지 않는다**."""
    src = ce.LANE / "src"
    if not (src / "margin_headroom.py").exists():
        return None
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    import margin_headroom as mh                            # noqa: PLC0415
    return mh


def mr_margin_path(source: str = MARGIN_SOURCE) -> tuple[pd.Series, dict]:
    """평균회귀가 날마다 묶어 둔 증거금(₩) — **총위험 고정 배수 k_mr 적용 전**.

    돌려주는 둘째 값이 「이 수가 어디서 왔나」다. 출처를 못 적는 수는 W4 에 못 쓴다.
    """
    if source not in MARGIN_SOURCES:
        raise ValueError(f"출처는 {MARGIN_SOURCES} 중 하나여야 해요 — {source!r}")
    if source == "allocator":
        mh = _allocator()
        if mh is None:
            raise SystemExit(
                f"배분기를 못 찾았어요 — {ce.LANE / 'src' / 'margin_headroom.py'} 가 "
                f"없습니다. 그 레인이 다른 자리면 KRW_CRS_DIR 로 알려 주시고, "
                f"대조판으로 가려면 --margin-source resim 을 쓰세요.")
        P, Z, meta, asof = mh.panel()
        path = mh.replay(P, Z, meta, "live", mh.LOT_UK)
        book_asof = max(asof.values())
        return path["used"], {
            "source": "allocator", "rule": "B 효율가중 (PREREG_03 §3.3)",
            "convention": "live", "asof": book_asof, "lot_uk": mh.LOT_UK,
            "stale": {t: a for t, a in asof.items() if a != book_asof},
            "stale_held": int(path.iloc[-1]["stale_held"])}
    _mb, _mr, u, _v, _f = _mr()
    return u * CAP, {"source": "resim", "rule": "A 균등 로트", "convention": "n/a",
                     "asof": str(u.index[-1]), "lot_uk": ce.REGISTERED_LOT_UK,
                     "stale": {}, "stale_held": 0}


def _series_and_books():
    series = mie.load_irs_series()
    sig = mib.registered_signals(series)
    L = mib.legs(series, sig)
    return series, sig, L


def _mr():
    mb = ce._lane()
    net, facts = ce.net_returns(mb, ce.REGISTERED_LOT_UK, "bound")
    P, Lz, Z, meta = mb.load()
    _d, used, _dv, _e, _b = mb.simulate(P, Lz, Z, meta, ce.REGISTERED_LOT_UK)
    u = pd.Series(used.to_numpy(dtype=float), index=[str(x)[:10] for x in used.index])
    mr_vol = float(net.std(ddof=1) * math.sqrt(ANN) * mb.CAP)
    return mb, ht.mr_returns(), u, mr_vol, facts


def _sizing(mr_u: np.ndarray, sl_u: np.ndarray, w: float):
    s_mix = float(((1 - w) * mr_u + w * sl_u).std(ddof=1) * math.sqrt(ANN))
    return (1 - w) / s_mix, w / s_mix, s_mix


# ── ③ 매일 ────────────────────────────────────────────────────────────────

def daily(verbose: bool = True, source: str = MARGIN_SOURCE) -> dict:
    series, sig, L = _series_and_books()
    blend = pd.Series(L["blend"]["rets"].values.astype(float),
                      index=[str(t)[:10] for t in L["blend"]["rets"].index])
    mb, mr, u_resim, mr_vol, _f = _mr()
    idx = sorted(set(mr.index) & set(blend.index))
    k_mr, k_tr, _s = _sizing(ht.unit_vol(mr.loc[idx]).to_numpy(),
                             ht.unit_vol(blend.loc[idx]).to_numpy(), W_REGISTERED)

    margin, src = mr_margin_path(source)
    ex = pd.read_csv(BACKEND / "output" / "sleeve_execution_daily.csv",
                     encoding="utf-8-sig", index_col=0)
    ex.index = [str(t)[:10] for t in ex.index]
    both = [d for d in ex.index if d in margin.index]
    if not both:
        raise SystemExit("슬리브 집행표와 평균회귀 경로가 겹치는 날이 없어요 — "
                         "`python -m scripts.sleeve_execution` 를 먼저 돌리세요")
    d = both[-1]
    want = float(ex.at[d, "face_total"]) * RATE
    mr_margin = float(margin.at[d]) * k_mr
    head = max(CAP - mr_margin, 0.0)
    scale = 1.0 if want <= 0 else min(1.0, head / want)

    hist_want = ex.loc[both, "face_total"].to_numpy() * RATE
    hist_head = np.maximum(CAP - margin.loc[both].to_numpy() * k_mr, 0.0)
    hist_scale = np.where(hist_want > 0, np.minimum(1.0, hist_head / np.maximum(hist_want, 1e-9)), 1.0)
    #: 발동 판정은 **원한값이 여력을 넘는가** 하나다. 배율에 문턱(0.999)을 걸면 0.9995 같은
    #: 아슬아슬한 날을 놓쳐 `sleeve_execution` 의 「상한 초과일」과 하루씩 갈린다(2026-09-15 실측).
    hit = int((hist_want > hist_head).sum())

    #: 대조 — 09-15 까지 쓰던 재시뮬 경로가 같은 날 뭐라고 하나. 둘이 갈리면 그 사실을 찍는다.
    other = None
    if source == "allocator" and d in u_resim.index:
        o_margin = float(u_resim.at[d]) * CAP * k_mr
        o_head = max(CAP - o_margin, 0.0)
        other = {"source": "resim", "mr_margin": o_margin, "headroom": o_head,
                 "scale": 1.0 if want <= 0 else min(1.0, o_head / want)}

    raw_headroom = max(CAP - float(margin.at[d]), 0.0)
    out = {"date": d, "mr_margin": mr_margin, "sleeve_want": want, "headroom": head,
           "scale": scale, "k_mr": k_mr, "k_tr": k_tr,
           "face_total": float(ex.at[d, "face_total"]),
           "hist_hit_days": hit, "hist_days": len(both),
           "margin_source": src, "contrast": other,
           "headroom_no_shrink": raw_headroom,
           "scale_no_shrink": 1.0 if want <= 0 else min(1.0, raw_headroom / want)}
    if verbose:
        print()
        print(f"── ③ W4 배율 · 기준일 {d} ──")
        if src["source"] == "allocator":
            print(f"  출처             배분기 「{src['rule']}」 · {src['convention']} 규약 · "
                  f"로트 {src['lot_uk']}억")
        else:
            print(f"  출처             재시뮬 「{src['rule']}」 ★대조판 — 그 레인이 굴리는 규칙이 아니다")
        if src["asof"] != d:
            print(f"  ⚠ 배분기 기준일 {src['asof']} · 이 표의 기준일 {d} — **하루 이상 갈린다**")
        if src["stale"]:
            print(f"  ⚠ 적재 지연 {len(src['stale'])}다리 "
                  f"({' · '.join(src['stale'])}) · 그중 증거금 묶고 있는 것 {src['stale_held']}")
        print(f"  평균회귀 증거금   {mr_margin/1e8:7.2f}억  (배수 k_mr {k_mr:.3f})")
        print(f"  여력             {head/1e8:7.2f}억")
        print(f"  슬리브 원한 증거금 {want/1e8:7.2f}억  (실측 액면 {ex.at[d,'face_total']/1e8:.1f}억 × {RATE:.0%})")
        print(f"  → **배율 {scale:.3f}**" + ("  (축소 없음)" if scale >= 0.999 else "  ★오늘 액면을 이만큼으로 줄인다"))
        #: ★ k_mr 은 「평균회귀 장부를 95.4% 로 줄여 세운다」는 **총위험 고정의 가정**이다.
        #:   그 레인은 그 축소를 하지 않는다(등록서 「평균회귀 쪽은 안 건드린다」). 그러면
        #:   여력은 이 줄이 말하는 값이고, 그것이 실제로 증권사에 남아 있는 돈이다.
        raw_head = raw_headroom
        if raw_head < head - 1e6:
            raw_scale = 1.0 if want <= 0 else min(1.0, raw_head / want)
            print(f"  ★★평균회귀를 실제로 안 줄이면 여력은 {raw_head/1e8:.2f}억 · "
                  f"배율 {raw_scale:.3f} 이다. 위 수는 그 장부를 k_mr={k_mr:.3f} 로 "
                  f"줄여 세운다는 **가정 위**에 있다 — 그 축소를 그 레인에 지시하지 않았으면 "
                  f"아래 줄이 실물이다.")
        if other is not None and abs(other["headroom"] - head) > 1e6:
            print(f"  ★대조: 09-15 까지 쓰던 재시뮬(규칙 A)은 같은 날 여력을 "
                  f"{other['headroom']/1e8:.2f}억 · 배율 {other['scale']:.3f} 이라고 한다 "
                  f"— 여력 {other['headroom']/1e8:.2f}억 → {head/1e8:.2f}억.")
            if want > 0:
                print(f"     원한({want/1e8:.2f}억) 대비 방석이 "
                      f"{other['headroom']/want:.1f}배 → {head/want:.1f}배로 얇아진다.")
        print(f"  ⚠ 손익에는 **전일 배율**을 건다. 평균회귀 쪽은 안 건드린다.")
        print(f"  참고: 지난 {len(both):,}일 중 축소 발동 {hit}일 ({hit/len(both):.1%}) · "
              f"최저 배율 {hist_scale.min():.3f}")
    return out


# ── ④ 분기 ────────────────────────────────────────────────────────────────

def quarterly(verbose: bool = True) -> dict:
    series, sig, L = _series_and_books()
    blend = pd.Series(L["blend"]["rets"].values.astype(float),
                      index=[str(t)[:10] for t in L["blend"]["rets"].index])
    mb, mr, u, mr_vol, _f = _mr()
    idx = sorted(set(mr.index) & set(blend.index))
    m_u = ht.unit_vol(mr.loc[idx]).to_numpy()
    s_u = ht.unit_vol(blend.loc[idx]).to_numpy()

    # 관문 — 판정문을 다시 내지 않고 읽는다(무거우므로). 없으면 그렇게 말한다.
    gates = {}
    for leg in ("trend", "macro", "blend"):
        f = BACKEND / "evaluation" / "reports" / f"Momentum-{leg}-IRS-books-paper.md"
        if not f.exists():
            gates[leg] = {"why": "판정문이 없어요 — `python -m scripts.momentum_irs_books` 를 먼저 돌리세요"}
            continue
        txt = f.read_text(encoding="utf-8")
        head = txt.split("## 순위 지표")[0]
        gates[leg] = {"pass": "## **통과**" in head, "head": head.strip().split("\n")[2:8]}

    # 상관 경보
    r = pd.Series(m_u).rolling(ROLL).corr(pd.Series(s_u)).dropna()
    over = (r > CORR_THRESHOLD).to_numpy()
    run = best = 0
    for v in over:
        run = run + 1 if v else 0
        best = max(best, run)
    alarm = best >= CORR_PERSIST

    # 채점 창 — 동결 이후만
    scored = [d for d in idx if d > FREEZE_DATE]
    out = {"gates": {k: v.get("pass") for k, v in gates.items()},
           "corr_now": float(r.iloc[-1]), "corr_min": float(r.min()), "corr_max": float(r.max()),
           "corr_over_run": int(best), "corr_alarm": bool(alarm),
           "scored_bars": len(scored), "total_bars": len(idx)}
    if verbose:
        print()
        print(f"── ④⑤ 분기 점검 · {date.today().isoformat()} ──")
        print(f"  채점 창(동결 {FREEZE_DATE} 이후)  **{len(scored):,}봉**  / 전체 {len(idx):,}봉")
        if not scored:
            print("     아직 채점 대상 영업일이 없다 — 채점은 2026-09-16 부터다.")
        print()
        print("  관문 셋 (판정문 `Momentum-*-IRS-books-paper`)")
        for leg, g in gates.items():
            if "why" in g:
                print(f"    {leg:6s} {g['why']}")
            else:
                mark = "통과" if g["pass"] else "**미통과 → W3 발동(w = 0)**"
                print(f"    {leg:6s} {mark}")
                for line in g["head"]:
                    if line.startswith("- "):
                        print(f"           {line[2:]}")
        bad = [k for k, v in out["gates"].items() if v is False]
        print(f"  → {'전부 통과' if not bad else f'**{bad} 미통과 — W3**'}")
        print()
        print(f"  상관 경보 (롤링 {ROLL}봉 > +{CORR_THRESHOLD} 가 {CORR_PERSIST}봉 지속)")
        print(f"    지금 {r.iloc[-1]:+.3f} · 범위 {r.min():+.3f} ~ {r.max():+.3f} · 최장 초과 연속 {best}봉")
        print(f"    → {'**경보**' if alarm else '경보 없음'}  (음의 방향은 경보가 아니다)")
    return out


# ── ⑤ 연 1회 ──────────────────────────────────────────────────────────────

def annual(verbose: bool = True) -> dict:
    series, sig, L = _series_and_books()
    blend = pd.Series(L["blend"]["rets"].values.astype(float),
                      index=[str(t)[:10] for t in L["blend"]["rets"].index])
    mb, mr, u, mr_vol, _f = _mr()
    idx = sorted(set(mr.index) & set(blend.index))
    m_u = ht.unit_vol(mr.loc[idx]).to_numpy()
    s_u = ht.unit_vol(blend.loc[idx]).to_numpy()
    ci = ht._paired_ci(m_u, s_u, W_UP)
    base_cal, _ = ht._card(m_u)
    cal_up, _ = ht._card((1 - W_UP) * m_u + W_UP * s_u)
    q = quarterly(verbose=False)
    c1 = len(idx) >= BARS_FOR_W2
    c2 = ci["p_cal"] < P_FOR_W2
    c3 = all(v is True for v in q["gates"].values())
    go = c1 and c2 and c3
    out = {"bars": len(idx), "c1_bars": c1, "p40": ci["p_cal"], "c2_p": c2,
           "c3_gates": c3, "w2_go": go, "dcal_40": cal_up - base_cal}
    if verbose:
        print()
        print(f"── ⑤ W2 상향 조건 (w {W_REGISTERED} → {W_UP}) ──")
        print(f"  ① 결합 창 ≥ {BARS_FOR_W2:,}봉      {len(idx):,}봉        {'✔' if c1 else '✗'}")
        print(f"  ② w={W_UP} 의 P(ΔCalmar ≤ 0) < {P_FOR_W2}  {ci['p_cal']:.3f}"
              f"  (ΔCalmar {cal_up-base_cal:+.3f})  {'✔' if c2 else '✗'}")
        print(f"  ③ 관문 셋 통과                             {'✔' if c3 else '✗'}")
        print(f"  → **{'w 를 0.40 으로 올린다' if go else f'셋이 다 서지 않는다 — w {W_REGISTERED} 유지'}**")
        print(f"  ⚠ 후보는 0.40 **하나**다. 못 넘으면 다시 묻지 않는다.")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    for f in ("daily", "quarterly", "annual"):
        ap.add_argument(f"--{f}", action="store_true")
    ap.add_argument("--margin-source", choices=MARGIN_SOURCES, default=MARGIN_SOURCE,
                    help="W4 여력의 분모를 어디서 받나 (기본 allocator = 그 레인의 배분기)")
    a = ap.parse_args()
    todo = [f for f, on in (("daily", a.daily), ("quarterly", a.quarterly), ("annual", a.annual)) if on]
    todo = todo or ["daily", "quarterly", "annual"]
    res = {}
    for f in todo:
        res[f] = (daily(source=a.margin_source) if f == "daily"
                  else {"quarterly": quarterly, "annual": annual}[f]())
    STATE.parent.mkdir(parents=True, exist_ok=True)
    prev = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"log": []}
    prev["log"].append({"run": date.today().isoformat(), **res})
    prev["latest"] = res
    STATE.write_text(json.dumps(prev, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(f"\n  → {STATE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
