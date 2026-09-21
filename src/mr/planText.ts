/* 계획면의 **문장** — 「지금 어디에 있고, 얼마면 무엇을 하나」를 두 줄로
 * [OWNER 2026-09-21 · 시니어 트레이더 피드백 — "상태 칸에 토스스타일의 문장으로
 * 구현해서. 진입 추천 타점을 같이 적어줘야 할 거 같아"].
 *
 * ## 왜 파일 하나인가
 *
 * 같은 문장이 서는 자리가 셋이다: 표의 상태 칸 · 1순위 히어로 · 상세 카드. 셋이
 * 같은 줄을 조금씩 다르게 말하면 화면이 스스로를 반박한다 — `parts.condWord` 가
 * 같은 이유로 한 벌인 것과 같은 자리(캐논 얼라인 8).
 *
 * ## 화면은 계산하지 않는다 (§16)
 *
 * 여기 있는 것은 **옮겨 적기**뿐이다. 레벨·거리·상태·포지션은 전부 서버가 끝낸
 * 값이고(`backend/app/mrplan.py`), 이 파일은 그 수들을 우리말로 잇는다. 밴드를
 * 화면에서 다시 내면 보드와 창이 다른 수를 말하게 된다 — 가드가 그 자리를 잰다.
 *
 * ## 낱말은 데스크 표준이다 [OWNER 2026-09-21 오후]
 *
 * > "오글거리거나 모호한 단어 보다는 … 채권, FICC 에 대해서 외부 리서치를 통해서
 * >  공용으로 사용하고 일반적인 트레이더도 알아들을 수 있는 단어로 바꿔다오."
 *
 * 문장 꼴(「~예요」)은 그대로 두고 **명사만** 국내 금리 데스크가 실제로 쓰는
 * 말로 맞췄다(이데일리 본드웹 계열 보도의 어휘 — 본드스왑스프레드·페이/리시브·
 * 언와인딩·캐리·와이든/타이튼). 바꾼 자리:
 *
 *     늘어남 → 괴리도        (평균 대비 σ 배수 = z-score. 「늘어남」은 우리 조어다)
 *     지금 할 일 → 시그널
 *     밴드 안 → 밴드 내 · 상단 밖 → 상단 이탈 · 재진입 → 밴드 복귀
 *     들고 있어요 → 보유      (「보유 n일」이 데스크 표기다)
 *     지났어요 → 돌파
 *     아직 못 재요 → 산출 불가 (사유는 「표본 부족」)
 *     미청산 → 미실현
 *
 * ## 명목은 안 적는다
 *
 * 2026-09-09 의 「트리거는 진입 레벨까지」는 청산·손절이 붙으면서 뒤집혔지만
 * [OWNER 2026-09-21], **명목·목표가는 여전히 이 화면의 것이 아니다**. 포지션
 * 크기는 데스크가 정하는 것이고, 그것까지 적으면 이 화면이 주문 카드가 된다.
 */

import type { Unit } from '@/lib/api';
import { fmtLevel, unitSuffix } from '@/lib/format';
import { fmtKrw } from '@/lib/krw';

import type { MrPlanLevel, MrPlanPosition, MrPlanRow } from './api';

const MINUS = '−';

/** z 표기 — 부호 명시, 반올림 후 0 은 부호 없이(rv fmt 의 규칙 그대로).
 *
 *  ⚠ **앱에 한 벌이다** — 종전에는 `MrPage` 안에 있었고, 계획면의 문장이 같은
 *  표기를 쓰게 되면서 여기로 내려왔다. 두 벌이면 한쪽만 자릿수가 바뀐다. */
export function fmtZ(z: number | null): string {
  if (z == null) return '—';
  const s = Math.abs(z).toFixed(2);
  if (Number(s) === 0) return '0.00σ';
  return z > 0 ? `+${s}σ` : `${MINUS}${s}σ`;
}

/** 레벨 한 수 — 계열의 자기 단위로. **앱에 한 벌**(상세 카드도 이것을 쓴다). */
export const lvl = (v: number | null | undefined, unit: string): string =>
  `${fmtLevel(v ?? null, unit as Unit)}${unitSuffix(unit as Unit)}`;

/** 거리 한 수 — 늘 **bp** 다(서버가 그렇게 끝낸다). 부호는 안 적는다: 「얼마나
 *  더 가야 하나」라서 방향은 낱말이 진다. */
export const gap = (v: number | null | undefined, dUnit: string): string =>
  v == null ? '—' : `${fmtLevel(Math.abs(v), dUnit as Unit)}${unitSuffix(dUnit as Unit)}`;

/** 히어로·표가 적을 **한 방향** — 지난 것이 먼저, 없으면 가까운 것.
 *
 *  양방향 계열(선물·퓨처스왑·커브)은 문턱이 둘이라 고르는 규칙이 있어야 한다.
 *  지난 문턱이 곧 「지금 할 수 있는 것」이라 그쪽이 먼저이고, 둘 다 멀면 더 가까운
 *  쪽이 다음에 닿을 문턱이다. 둘 다 보여 주는 자리는 상세 카드의 「트리거」 칸이다.
 *  (보드의 `heroTrigger` 와 같은 규칙 — 두 화면이 다른 다리를 앞세우지 않는다.) */
function pickLevel(r: MrPlanRow): MrPlanLevel | undefined {
  const ls = r.levels ?? [];
  return ls.find((l) => l.entryReached) ?? [...ls].sort((a, b) => a.entryGap - b.entryGap)[0];
}

export interface PlanLines {
  /** 첫 줄 — 지금 무슨 상태인가. */
  lead: string;
  /** 둘째 줄 — 그래서 얼마면 무엇을 하나. */
  sub: string;
  /** 첫 줄이 인쇄하는 **돈**(평가손익) — 색은 여기서 정하지 않는다.
   *
   *  ⚠ 종전 판은 `'up'|'down'` 을 넘겼는데 그건 `table/tint.ts::directionClass`
   *  의 재구현이었고 **0 에서 갈렸다**(캐논은 `sr-flat` 뮤트, 이 판은 맨 잉크).
   *  같은 행의 1년 손익 칸이 캐논을 쓰므로 평가손익 0 인 줄에서 한 행에 두 기제가
   *  섰다. 숫자만 넘기고 색은 캐논 한 곳이 정한다. */
  pnl?: number;
}

/** 한 계열의 두 줄.
 *
 *  갈래는 셋이고 **순서가 곧 우선순위**다:
 *
 *    ① 못 재는 줄        창이 안 찼거나 σ=0 이라 밴드가 없다
 *    ② 들고 있는 줄      백테스트가 표본 끝에 연 다리가 있다 → 나가는 문을 적는다
 *    ③ 비어 있는 줄      진입 문턱과 남은 거리를 적는다
 *
 *  ②가 ③보다 앞인 이유: 들고 있으면 「얼마면 들어가나」는 지금 할 일이 아니다.
 */
export function planLines(r: MrPlanRow): PlanLines {
  const unit = r.unit;
  const dUnit = r.dUnit;

  // ① 밴드가 못 선다 — 「없다」가 아니라 「못 잰다」라고 적는다.
  if (r.z == null || r.levels.length === 0) {
    return {
      lead: '산출 불가',
      /* z 가 없는 이유는 둘이다 — 창 미달 **또는 σ=0**(값이 창 안에서 한 번도
         안 움직인 계열). 창 탓으로만 적으면 평평한 계열에서 거짓이 된다. */
      sub: `표본 부족 — ${r.cond.lookback}일 창`,
    };
  }

  // ② 들고 있는 다리 — 나가는 문 둘이 오늘 레벨로 선다.
  const p = r.position;
  if (p) {
    const won = fmtKrw(p.pnl);
    const lead = `보유 ${p.bars}일 · ${won}`;
    if (p.exit == null || p.stop == null) {
      return { lead, sub: `${p.legs} · 밴드 미산출로 청산·손절선 없음`,
               pnl: p.pnl };
    }
    // 방향 낱말은 **지금 값이 중심선의 어느 쪽인가**가 정한다(서버의 그 규약) —
    // 위쪽이면 내려와야 청산이고 더 올라야 손절이다.
    const above = (p.z ?? 0) >= 0;
    const sub = `청산 ${lvl(p.exit, unit)} ${above ? '이하' : '이상'}`
      + ` · 손절 ${lvl(p.stop, unit)} ${above ? '이상' : '이하'}`;
    return { lead, sub, pnl: p.pnl };
  }

  // ③ 비어 있는 줄 — 진입 문턱 하나와 남은 거리.
  const l = pickLevel(r);
  if (!l) {
    // 문턱이 아예 없다 = 이 데스크가 할 수 있는 방향이 없다는 뜻이고, 사유는
    // 행이 따로 진다(`triggerBlocked`) — 지어내지 않는다.
    return { lead: `${fmtZ(r.z)} 확대`, sub: r.triggerBlocked ?? '진입선 없음' };
  }
  const word = l.side === 'above' ? '이상' : '이하';
  const touch = r.cond.entryMode === 'touch';
  const out = r.state.kind === 'above' || r.state.kind === 'below';
  /* 앞머리는 **늘 상태**다 — 종전 판은 여기서 z 를 다시 적었는데, 바로 왼쪽
     「늘어남」 열이 그 수를 이미 인쇄하고 있어서 한 행에 같은 수가 두 번 섰다
     (브라우저 실측 2026-09-21). 이 칸이 더할 것은 **그래서 무엇을 하나**다. */
  const head = stateText(r.state);

  if (touch) {
    // 「밴드 복귀」 규칙 — 밖에 있다가 **돌아오는** 봉에 들어간다. 그래서 문턱을
    // 지났다고 진입 자리가 아니다(그 사실을 안 적으면 화면이 거짓을 말한다).
    return out
      ? { lead: `${head} · 밴드 복귀 시 진입`,
          sub: `${lvl(l.entry, unit)} 안으로 복귀하면 ${l.legs}` }
      : { lead: `${head} · 진입까지 ${gap(l.entryGap, dUnit)}`,
          sub: `${lvl(l.entry, unit)} 이탈 후 복귀하면 ${l.legs}` };
  }
  return l.entryReached
    ? { lead: `${head} · 진입 시그널`,
        sub: `${lvl(l.entry, unit)} ${word} · ${gap(l.entryGap, dUnit)} 돌파 → ${l.legs}` }
    : { lead: `${head} · 진입까지 ${gap(l.entryGap, dUnit)}`,
        sub: `${lvl(l.entry, unit)} ${word} 시 ${l.legs}` };
}

/** 보유 포지션의 **매력도 한 줄** [OWNER 2026-09-21 오후 — "원래 진입하는 조건이
 *  매력도고 그 위치에 대한 순위를 유지해주면 됨"].
 *
 *  새 척도를 만들지 않는다. 델타를 더 열지 말지는 **그 계열을 애초에 사게 한 그
 *  조건**이 지금도 서 있느냐로 판단한다 — 진입선을 아직 넘어 있으면 더 실을 자리,
 *  밴드로 돌아왔으면 더 실을 이유가 없다. 순위(|z|)도 진입 후보와 **같은 한 줄**을
 *  쓴다. 그래서 이 함수가 보는 것은 `levels` 이지 포지션이 아니다. */
export function entryNote(r: MrPlanRow): string {
  const l = pickLevel(r);
  if (!l) return r.triggerBlocked ?? '진입선 없음';
  const d = gap(l.entryGap, r.dUnit);
  if (r.cond.entryMode === 'touch') {
    const out = r.state.kind === 'above' || r.state.kind === 'below';
    return out ? '밴드 복귀 시 추가' : `진입선까지 ${d}`;
  }
  return l.entryReached ? `진입선 ${d} 돌파 · 추가 가능` : `진입선까지 ${d}`;
}

/** 청산·손절선에 붙는 **부등호 낱말** — 지금 값이 중심선의 어느 쪽인가가 정한다.
 *
 *  위쪽이면 내려와야 청산이고 더 올라야 손절이다(서버의 `exits_now` 규약).
 *  표의 두 열과 문장이 같은 낱말을 써야 해서 여기 한 벌로 둔다. */
export function exitWords(p: MrPlanPosition): { exit: string; stop: string } {
  const above = (p.z ?? 0) >= 0;
  return above ? { exit: '이하', stop: '이상' } : { exit: '이상', stop: '이하' };
}

/** 상태 한 낱말 — **판정이지 행동이 아니다**.
 *
 *  앱에 한 벌이다: 계획면의 문장, 통합 스트립의 툴팁, 그리고 보드가 쓰던 그
 *  어휘가 전부 이것이다. 두 화면이 같은 사건을 다르게 부르면 나란히 못 읽는다. */
export function stateText(s: MrPlanRow['state']): string {
  if (s.kind === 'below') return `하단 이탈 ${s.days}일째`;
  if (s.kind === 'above') return `상단 이탈 ${s.days}일째`;
  /* 「재진입」은 밴드로 돌아온 것인지 밴드를 또 뚫은 것인지가 안 갈린다 —
     데스크 말로 **복귀**다. 어느 쪽에서 돌아왔는지는 괄호가 진다. */
  if (s.kind === 'reentry-low') return `밴드 복귀 ${s.days}일째 (하단)`;
  if (s.kind === 'reentry-high') return `밴드 복귀 ${s.days}일째 (상단)`;
  return '밴드 내';
}

/** 「지난 1년」 한 줄 — 표의 손익 칸 밑에 서는 뒷말.
 *
 *  거래 수를 **같이** 적는다: 1년 창은 계열당 거래가 한 줌이라(실측 BSS-3Y 1건)
 *  손익만 적으면 그 수가 몇 건 위에 서 있는지 안 보인다 [OWNER 2026-09-21 —
 *  조건은 전체 표본, 성과는 1년]. */
export function perfNote(r: MrPlanRow): string {
  const n = r.perf1y.numTrades;
  if (!n) {
    /* ★거래가 없는데 돈이 있는 줄이 실제로 선다 — 그 해가 **들고 있는 다리의
       평가**이기 때문이다(실측 2026-09-21: IRS 3Y-10Y 가 −336만원·0건, 442일째
       보유 중). 「1년 거래 없어요」만 적으면 읽는 사람이 「거래가 없는데 왜
       손익이 있나」에서 멈춘다 — 그 답을 이 줄이 적는다. */
    return r.perf1y.totalPnl === 0 ? '1년 거래 0건' : '미실현 평가만 · 1년 거래 0건';
  }
  const wr = r.perf1y.winRate;
  return `1년 ${n}건${wr == null ? '' : ` · 승률 ${Math.round(wr * 100)}%`}`;
}
