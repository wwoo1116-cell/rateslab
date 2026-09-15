/* 다섯 줄. **이게 제품 전부다.**
 *
 *     뷰       8분기 동결
 *     함의     3년 12개월 · 모형 3.83% vs 시장 4.07% — 24bp 리치
 *     논거     경로 0 / 준칙 0 / CD 0 / TP 0 / 스프레드 0
 *     트레이드  3년 리시브 · 2s5s 플래트너
 *     리스크    r* 는 bp 를 안 바꿔요 · 9~12분기 되돌림 · 룰 이탈 σ
 *
 * ## 문체 [미결 — 오너 질문]
 *
 * 앱은 해요체다. 데스크 노트는 합니다체가 맞을 수 있는데 이 리포에 **내보내기
 * 관례가 하나도 없다**(`clipboard` 0건). 컨텍스트 문서 §10-1 이 «답 오기 전까지
 * 해요체가 기본» 이라고 정해 두었으므로 해요체로 출하하고 질문으로 올린다.
 * 문체를 바꾸는 자리는 `speak()` 하나이므로 답이 오면 한 줄이다.
 *
 * ## 시간축 — 분기 사이를 보간하지 않는다
 *
 * 엔진이 분기 모형이라 `h` 는 정수뿐이다. 다음 금통위(as-of + 6일)는 눈금 사이라
 * 값을 만들려면 보간해야 하고 그 보간은 우리가 만든 숫자다. 그 칸은 **찍은 첫
 * 점**을 보여 주고 커브는 «한 분기부터» 라고 말한다. 빈칸도 보간도 아니다.
 */

import type { TenorDecomposition } from './decompose';
import { ENGINE_STATUS } from './assumptions';
import type { PathSolution, Tenor } from './path';
import type { Candidate, GapVector, TenorGap } from './trades';
import type { RiskLine } from './risk';
import { eul } from '@/lib/josa';

export type HorizonId = 'mpc' | 'q1' | 'q4';

export const HORIZONS: readonly { id: HorizonId; label: string; h: number | null }[] = [
  /* 커브 숫자가 없는 칸이다. 없앨 수도 있었지만 오너가 매일 보는 자리가 여기라,
     그 자리에서 정직하게 말할 수 있는 것(찍은 첫 점)을 대신 세운다. */
  { id: 'mpc', label: '다음 금통위까지', h: null },
  { id: 'q1', label: '3개월', h: 1 },
  { id: 'q4', label: '12개월', h: 4 },
];

export const DEFAULT_HORIZON: HorizonId = 'q4';

export const MPC_NO_CURVE =
  '분기 모형이라 커브 반응은 한 분기(3개월)부터 말할 수 있어요 — 그 사이를 보간하면 우리가 만든 숫자예요.';

/** 금통위 칸의 「논거」 자리. 같은 문장을 세 번 찍으면 화면이 고장 난 것처럼
 *  읽힌다 — 세 줄이 각자 그 자리에서 말할 수 있는 것을 말한다. */
export const MPC_NO_TERMS = '커브 성분은 3개월 자리부터 갈라져요.';

/** 12개월이 아닌 자리의 「트레이드」. 캐리를 비례로 잘라 쓰지 않는 이유다. */
export const NO_CARRY_HERE = '시장 대비는 12개월 자리에만 있어요 — 포워드 시작점이 1년이거든요.';

const TENOR_LABEL: Record<Tenor, string> = {
  '1y': '1년',
  '2y': '2년',
  '3y': '3년',
  '5y': '5년',
  '10y': '10년',
};

const bp1 = (v: number) => (Math.abs(v) < 0.05 ? '0.0' : Math.abs(v).toFixed(1));

/** 경로를 말로. 목록이지 요약이 아니다 — 요약하면 틀릴 자리가 생긴다. */
export function pathInWords(dots: readonly number[]): string {
  if (dots.every((v) => v === 0)) return `${dots.length}분기 동결`;
  const moves: string[] = [];
  let prev = 0;
  dots.forEach((v, q) => {
    const step = v - prev;
    if (step !== 0) moves.push(`${q + 1}분기 ${step > 0 ? '+' : '−'}${Math.abs(step)}bp`);
    prev = v;
  });
  const lastChange = dots.reduce((acc, v, q) => (v !== (q === 0 ? 0 : dots[q - 1]) ? q : acc), 0);
  const tail = lastChange < dots.length - 1 ? ` · 그 뒤 ${dots.length}분기까지 유지` : '';
  return moves.join(' · ') + tail;
}

export type NoteLines = {
  view: string;
  /** 모형 as-of. **엔진이 준 문장 그대로** 다시 쓰지 않는다. */
  asOf: string;
  implication: string;
  argument: string;
  trade: string;
  risk: string[];
};

/** 금통위 칸이 정직하게 말할 수 있는 것 — **오너가 찍은 첫 점 그 자체**.
 *
 *  커브 숫자를 못 내는 자리라고 빈칸으로 두지 않는다. 다음 회의에서 무엇을
 *  보고 있는지는 입력이 이미 답하고 있고, 그건 보간이 아니다. */
export function mpcDecision(dots: readonly number[]): string {
  const d = dots[0] ?? 0;
  const when = ENGINE_STATUS.next_event.date;
  const what = d === 0 ? '동결' : `${d > 0 ? '+' : '−'}${Math.abs(d)}bp`;
  const label = ENGINE_STATUS.next_event.label ?? '다음 회의';
  const tail = `${label}에 ${what}${eul(what)} 보고 있어요.`;
  return when ? `${when} ${tail}` : tail;
}

function implicationLine(
  g: TenorGap | null,
  h: number | null,
  provenance: string,
  dots: readonly number[],
): string {
  /* 커브 숫자가 없는 칸이라고 빈칸을 두지 않는다 — 그 자리에서 정직하게 말할 수
     있는 것(찍은 첫 점)을 세우고, 왜 커브가 없는지는 아래 한 줄이 진다. */
  if (h === null) return mpcDecision(dots);
  if (!g || g.vsMarketBp === null || g.marketPct === null) return NO_CARRY_HERE;
  const rich = g.vsMarketBp < 0;
  return (
    `${TENOR_LABEL[g.tenor]} · 모형 ${g.modelPct.toFixed(2)}% vs 시장 ${g.marketPct.toFixed(2)}% — ` +
    `${bp1(g.vsMarketBp)}bp ${rich ? '리치' : '치퍼'} (${provenance})`
  );
}

function argumentLine(d: TenorDecomposition | null, h: number | null): string {
  if (h === null) return MPC_NO_TERMS;
  if (!d) return MPC_NO_TERMS;
  return d.terms.map((t) => `${t.label} ${t.value >= 0 ? '+' : '−'}${bp1(t.value)}`).join(' / ');
}

/** 후보의 크기는 **절댓값**이다 — 방향은 이름이 이미 말한다(리시브·스티프너).
 *  「리시브 −55.2bp」 는 부호를 두 번 말하는 셈이라 읽는 사람이 되묻는다. */
function tradeLine(cands: Candidate[], h: number | null): string {
  if (h === null) return NO_CARRY_HERE;
  if (cands.length === 0) return NO_CARRY_HERE;
  return cands
    .map(
      (c) =>
        `${c.label} ${bp1(c.bp)}bp` +
        (c.convergenceAtEdge ? ` (${c.convergenceQ}분기까지 벌어짐)` : ` (${c.convergenceQ}분기)`),
    )
    .join(' · ');
}

export function buildNote(args: {
  sol: PathSolution;
  gaps: GapVector | null;
  headlineGap: TenorGap | null;
  headlineDecomp: TenorDecomposition | null;
  candidates: Candidate[];
  risks: RiskLine[];
  h: number | null;
  /** 헤드라인 테너의 프로비넌스 등급. §C.5 — 다섯 다 `ARITHMETIC` 이다. */
  provenance: string;
}): NoteLines {
  return {
    view: pathInWords(args.sol.dots),
    asOf: ENGINE_STATUS.as_of_sentence,
    implication: implicationLine(args.headlineGap, args.h, args.provenance, args.sol.dots),
    argument: argumentLine(args.headlineDecomp, args.h),
    trade: tradeLine(args.candidates, args.h),
    risk: args.risks.map((r) => r.text),
  };
}

/**
 * 붙여 넣을 평문. 주간 원페이저에 그대로 들어가는 모양이다.
 *
 * 마크다운을 안 쓴다 — 붙여 넣는 자리가 워드일 수도 텔레그램일 수도 있어서
 * `**` 가 그대로 찍히면 그게 더 나쁘다.
 */
export function noteText(n: NoteLines, meta: { asof: string; basisAsOf: string }): string {
  return [
    `뷰        ${n.view}`,
    `함의      ${n.implication}`,
    `논거      ${n.argument}`,
    `트레이드   ${n.trade}`,
    ...n.risk.map((r, i) => `${i === 0 ? '리스크    ' : '          '}${r}`),
    '',
    `커브 ${meta.asof} · 모형 기저 ${meta.basisAsOf}`,
    n.asOf,
  ].join('\n');
}
