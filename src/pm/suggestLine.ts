/* 「그날 1등」 한 줄 — 담는 줄 아래에 서는 **글**이다, 컨트롤이 아니다.
 *
 * [OWNER 2026-09-23 — "들어간 시점에서의 최적 파라미터로"] 선택지에서 **「손으로
 * 치되 1등을 제안」**을 고르셨다. 그래서 이 줄은 고르지 않는다: 계열을 진입일까지의
 * 자료로 격자에 돌린 1등을 적고, 내 조건이 그 격자에서 몇 등인지를 **찾아서**
 * 적을 뿐이다(순위는 서버가 매긴다 — `findCell` 은 찾기만 한다).
 *
 * ## 문장이 여기 있는 이유
 *
 * 「1등」이라고만 적으면 고르라는 말로 읽힌다. 그런데 이 1등은 고른 창에서 잰
 * 순위라 성과가 아니라 **선택의 산물**이고(계획면 머리 · PBO 레인), 1년 창은
 * 계열당 거래가 0~5건이라 순위 자체가 잡음일 수 있다. 그 둘을 1등 옆에 **늘**
 * 같이 세우려면 문장을 만드는 자리가 하나여야 한다 — 화면이 조건마다 문장을
 * 조립하면 어느 갈래에선가 경고가 빠진다. 가드(`guards/paper-suggest.test.ts`)가
 * 1등이 서는 모든 문장에 경고가 붙는지를 잰다.
 */

import { eul } from '@/lib/josa';
import { MR_RANK_KEYS } from '@/mr/api';

import { findCell, knobsComplete, type PaperLegKnobs, type PaperSuggest } from './api';
import { knobWord } from './words';

/** 1등 옆에 **늘** 서는 문장. 빠지면 「1등」이 지시가 된다. */
export const SUGGEST_CAVEAT =
  '⚠ 고른 창에서 잰 순위라 성과가 아니라 선택의 산물이에요(표본내) — 담기는 것은 위에 친 조건이에요.';

/** 격자 창의 우리말 — 서버 `mrmetrics.SPANS` 의 열쇠. 모르는 열쇠는 그대로 적는다. */
const SPAN_WORD: Record<string, string> = {
  all: '전체 표본', '1y': '지난 1년', '1q': '지난 1분기', '1m': '지난 1개월',
};

export type KnobDraft = Partial<Record<keyof PaperLegKnobs, string | number | undefined>>;

export function suggestLine(a: {
  /** 계열 라벨 — 재는 중일 때 「무엇을」 적는다. */
  label: string;
  /** 체결일 칸이 비었거나 열 글자 꼴인가. 아니면 아직 안 묻는다. */
  entryReady: boolean;
  busy: boolean;
  /** 서버가 못 냈을 때의 사유(422 문장 · 옛 백엔드). */
  failed?: string;
  got?: PaperSuggest;
  /** 위 칸에 친 조건 — 다 찼을 때만 등수를 찾는다. */
  knobs: KnobDraft | undefined;
}): string {
  if (!a.entryReady) return '체결일을 다 치면 그날 1등을 재요 (YYYY-MM-DD).';
  if (a.busy) {
    return `그날 1등을 재는 중… — ${a.label}${eul(a.label)} 체결일까지의 자료로 격자에 돌려요.`;
  }
  if (a.failed) return `그날 1등을 못 냈어요 — ${a.failed}`;
  const g = a.got;
  if (!g) return '';
  if (!g.top) return `그날 1등 — ${g.why ?? '못 냈어요'}`;

  const rankLabel = MR_RANK_KEYS.find((k) => k.v === g.rankKey)?.label ?? g.rankKey;
  const span = SPAN_WORD[g.span] ?? g.span;
  /* 거래 수를 같이 적는 이유: 1년 창은 계열당 0~5건이라 그 순위가 잡음이라는
     실측을 오너가 듣고도 1년으로 정했다(계획면 머리). 수를 보여야 읽는 사람이
     그 잡음을 스스로 잰다. */
  const trades = g.top.numTrades == null ? '' : ` · 거래 ${g.top.numTrades}건`;
  let mine = '';
  if (knobsComplete(a.knobs)) {
    const cell = findCell(g.list, a.knobs);
    mine = cell
      ? ` · 내 조건은 ${cell.rank}등`
      : ' · 내 조건은 프리셋 밖이라 격자에 없어요';
  }
  return `그날 1등 ${knobWord(g.top)} — ${g.asof ?? g.entry}까지의 자료 · ${span} · `
    + `${rankLabel} 기준 ${g.ranked}칸 중${trades}${mine}. ${SUGGEST_CAVEAT}`;
}
