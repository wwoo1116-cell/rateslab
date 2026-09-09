# -*- coding: utf-8 -*-
"""한 장짜리 판정문 — `evaluation/reports/{strategy_id}.md`.

**게이트 판정이 맨 위**다(사양). 읽는 사람이 스크롤해서 찾아야 하는 판정은
판정이 아니고, 이 층이 존재하는 이유가 「순위 매기기 전에 통과 여부를 먼저
말하는 것」이기 때문이다.

동반 진단은 **셋과 뚜렷이 갈라** 아래에 둔다 — MR 과 모멘텀의 DSR 이 비슷하게
나올 때 서로 다른 실패 방식이 보이라고 두는 값들이지 순위가 아니다.
"""
from __future__ import annotations

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

    lines += [
        "## 순위 지표",
        "",
        "| 값 | 수 |",
        "|---|---|",
        f"| 변동성 정규화 CDaR 비 | {_num(r['cdar_ratio'])} (기준선 {r['reference']}) |",
        f"| CDaR (최악 5% 낙폭 평균) | {_num(r['cdar'])} |",
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
