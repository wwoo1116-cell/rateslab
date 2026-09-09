# -*- coding: utf-8 -*-
"""한 장짜리 판정문 — `evaluation/reports/{strategy_id}.md`.

**게이트 판정이 맨 위**다(사양). 읽는 사람이 스크롤해서 찾아야 하는 판정은
판정이 아니고, 이 층이 존재하는 이유가 「순위 매기기 전에 통과 여부를 먼저
말하는 것」이기 때문이다.

동반 진단은 **셋과 뚜렷이 갈라** 아래에 둔다 — MR 과 모멘텀의 DSR 이 비슷하게
나올 때 서로 다른 실패 방식이 보이라고 두는 값들이지 순위가 아니다.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

REPORTS = Path(__file__).resolve().parent / "reports"


def _num(v: Any, nd: int = 4, suffix: str = "") -> str:
    """**없는 값은 «—» 다** — 0 으로 적으면 「쟀는데 0」과 구별이 안 된다.

    소수 자리는 **크기를 보고** 정한다. 이 층은 비율 계열(액면 대비)도 먹고 원(₩)
    계열도 먹는데(모멘텀 레인은 자본 분모를 안 만들기로 했다), 넷째 자리를 고정하면
    원 계열에서 「532,493.628808」 같은 줄이 나온다 — 소수점 아래가 뜻을 잃은
    자리다. 1,000 을 넘으면 정수로 적는다.
    """
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "예" if v else "아니오"
    if isinstance(v, (int,)) and not isinstance(v, bool):
        return f"{v:,}{suffix}"
    if abs(v) >= 1000:
        return f"{v:,.0f}{suffix}"
    return f"{v:,.{nd}f}{suffix}"


def render(out: dict[str, Any]) -> str:
    """평가 결과 → 마크다운 한 장."""
    g, r, d, i = out["gate"], out["ranking"], out["diagnostics"], out["inputs"]
    verdict = "**통과**" if g["overall_pass"] else "**미통과**"
    lines = [
        f"# 평가 판정 — {out['strategy_id']}",
        "",
        f"## {verdict}",
        "",
        (f"- DSR **{_num(g['dsr'])}** ({'통과' if g['dsr_pass'] else '미통과'} "
         f"· 문턱 0.95)"),
        (f"- PBO **{_num(g['pbo'])}** ({'통과' if g['pbo_pass'] else '미통과'} "
         f"· 문턱 0.20)"),
        (f"- 필요 표본 **{_num(g['min_trl_years'], 2, '년')}** 대 실제 "
         f"**{_num(g['actual_years'], 2, '년')}**"),
        "",
    ]
    if not g["overall_pass"]:
        lines += [f"> 순위는 안 매긴다 — {r['reason_if_null']}", ""]
        # **어떻게 떨어졌나** — 판정은 안 바꾸고 사정만 적는다 [OWNER 2026-09-09].
        # 「미통과」 한 낱말로만 적으면 「SR 이 닿을 물건이 아니다」와 「표본이
        # 1.3년 모자라다」와 「칸이 닮아 못 고른다」가 같은 말로 읽힌다.
        sh = out.get("failure_shape") or {}
        if sh.get("note"):
            lines += [f"**어떻게 떨어졌나 — {sh['note']}**", ""]
            ev = []
            if sh.get("trl_multiple") is not None:
                ev.append(f"필요 표본이 실제의 **{_num(sh['trl_multiple'], 1)}배**")
            if sh.get("cells_median_corr") is not None:
                ev.append(
                    f"칸 사이 상관 중앙 **{_num(sh['cells_median_corr'], 2)}** · "
                    f"칸별 연 SR **{_num(sh['cells_sr_min'], 2)}"
                    f"~{_num(sh['cells_sr_max'], 2)}**")
            if ev:
                lines += ["- " + "\n- ".join(ev), "",
                          "> 이 눈금(상관 0.8 · 배수 1.5·5)은 **서술**이지 게이트가 "
                          "아니다. 문턱도 판정도 안 바뀐다.", ""]

    lines += [
        "## 순위 지표",
        "",
        "| 값 | 수 |",
        "|---|---|",
        f"| 변동성 정규화 CDaR 비 | {_num(r['cdar_ratio'])} (기준선 {r['reference']}) |",
        f"| CDaR (최악 5% 낙폭 평균) | {_num(r['cdar'])} |",
        # ★**꼬리 점의 수는 표본이 아니다.** 같은 물속 구간에서 나온 관측들은
        # 독립이 아니라 **사건 하나**에 가깝다. Calmar → CDaR 로 옮긴 이유가
        # 「MaxDD 는 단일관측 추정량」이었으므로, CDaR 이 실제로 몇 개의 사건 위에
        # 서 있는지를 안 적으면 같은 결함을 이름만 바꿔 들고 있는 셈이 된다
        # (Van Hemert 외 2020 의 「낙폭 통계는 관측을 낭비한다」가 이 자리다).
        (f"| ★그 꼬리가 나온 **낙폭 사건 수** | "
         f"{_num(r.get('tail_episodes'), 0)} / 전체 "
         f"{_num(r.get('total_episodes'), 0)} "
         f"(꼬리 관측 {_num(r.get('tail_points'), 0)}점) |"),
        f"| 연환산 수익(정규화 후) | {_num(r['ann_return_normalized'])} |",
        "",
        "## 동반 진단 — **순위에 안 쓴다**",
        "",
        "| 항목 | 수 |",
        "|---|---|",
        f"| 왜도 | {_num(d.get('skew'), 3)} |",
        f"| 초과첨도 | {_num(d.get('excess_kurtosis'), 3)} |",
        f"| 꼬리비(95/5) | {_num(d.get('tail_ratio'), 3)} |",
        f"| 최장 낙폭 지속 | {_num(d.get('longest_drawdown_days'), 0, '일')} |",
        # **봉 기준**이다 — 수익 계열 위에서 세므로 무포지션 봉(이 전략은 88%)이
        # 분모에 든다. 거래 기준 승률(화면의 그 수)과 다른 물건이라 이름에 적는다.
        f"| 승률(봉 기준 · 무포지션 포함) | {_num(d.get('win_rate'), 4)} |",
        f"| 평균이익 / 평균손실 | {_num(d.get('avg_win'), 6)} / {_num(d.get('avg_loss'), 6)} |",
        f"| 연환산 변동성 | {_num(d.get('ann_vol'), 4)} |",
        f"| SR(주기별 / 연환산) | {_num(d.get('sr_period'), 5)} / {_num(d.get('sr_annualized'), 3)} |",
        # 연환산 바로 아래 둔다 — 두 수의 **차이**가 「√252 곱셈이 이 계열에서
        # 얼마나 부풀렸나」이고, 그 부풀림이 레인마다 비대칭이라(MR +0.21 대
        # 모멘텀 −0.15) 나란히 안 놓으면 같은 자로 견줬다고 말할 수 없다.
        f"| 연환산 SR — AR(1) 보정(Lo 2002) | {_num(d.get('sr_annualized_lo'), 3)} |",
        # 문헌의 환율이 **월별** 자기상관 위에 있다 — Man/Harvey 외(2020): 「월별
        # 자기상관 0.1 이 기대 최대낙폭에 주는 충격 ≈ Sharpe 0.5 → 0.4」. 일별
        # AR(1) 을 그 문장에 그대로 대면 단위가 어긋나서 21봉 묶음을 같이 낸다.
        (f"| AR(1) — 21봉 묶음(≈월) | {_num(d.get('ar1_21bar'), 3)}"
         + (f" (묶음 {d['ar1_21bar_blocks']}개 · 표준오차 ≈ "
            f"{_num(1.0 / math.sqrt(d['ar1_21bar_blocks']), 2)})"
            if d.get("ar1_21bar_blocks") else "") + " |"),
        f"| SR0(뽑기로 나오는 최고) | {_num(d.get('sr0_period'), 5)} |",
        f"| PBO 열화 기울기 | {_num(d.get('pbo_degradation'), 3)} |",
        f"| PBO 시험 손실확률 | {_num(d.get('pbo_prob_oos_loss'), 3)} |",
        "",
        "## 입력",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 시행수 N | {_num(i['trials'], 0)} |",
        f"| 비용 가정(왕복 bp) | {_num(i['cost_bp'], 2)} |",
        f"| 목표 변동성 | {_num(i['target_vol'], 3)} |",
        f"| 변동성 추정기 | {i['vol_estimator']} |",
        f"| 관측 수 | {_num(i['n_obs'], 0)} |",
        f"| AR(1) | {_num(i['ar1'], 3)} |",
        f"| CSCV 블록 수 S | {_num(i['is_oos_splits'], 0)} |",
        "",
    ]
    if out["assumptions"]:
        lines += ["## 가정", ""] + [f"- {a}" for a in out["assumptions"]] + [""]
    # ⚠ **생성 시각을 안 적는다.** 이 판정문은 리포에 남는 산출물이라, 시각이
    # 있으면 같은 수를 다시 뽑을 때마다 diff 가 생겨 「무엇이 바뀌었나」를 못
    # 읽는다. 언제 잰 것인지는 커밋이 말한다.
    return "\n".join(lines)


def write(out: dict[str, Any], root: Path | None = None) -> Path:
    """판정문을 파일로. 경로를 돌려준다."""
    base = root or REPORTS
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{out['strategy_id']}.md"
    path.write_text(render(out), encoding="utf-8")
    return path
