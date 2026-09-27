/* 페이퍼 북의 **낱말** — 표와 제안 줄이 같은 말을 쓰게 한 곳에 둔다.
 *
 * 2026-09-28 에 `PortfolioPage` 에서 갈라 냈다. 「그날 1등」 줄(`suggestLine`)이
 * 얼린 조건을 표와 **같은 꼴**로 적어야 하는데, 표의 함수가 화면 모듈 안에
 * 갇혀 있으면 둘째 자리가 제 손으로 다시 적게 된다 — 그러면 표는 「2.5/0.5/3σ」
 * 라 하고 제안은 「2.50/0.50/3.00」 이라 하는 날이 온다(캐논 규칙 1). */

import type { PaperLegKnobs } from './api';

/** 진입 규칙의 우리말 — **MR 화면의 그 낱말**을 그대로 쓴다
 *  (`mr/api.ts::MR_ENTRY_MODES`). 두 화면이 같은 규칙을 다르게 부르면 읽는
 *  사람이 어제 다리와 오늘 노브를 못 잇는다. */
export const ENTRY_WORD: Record<PaperLegKnobs['entryMode'], string> = {
  level: '이탈 즉시',
  touch: '밴드 복귀',
};

/** 얼린 조건 한 줄 — `120일 · 2.5/0.5/3σ · 이탈 즉시`.
 *
 *  σ 셋을 슬래시로 잇는 것은 트레이더가 부르는 꼴 그대로다("2.5/0.5/3").
 *  단위는 **묶음이 진다** — 숫자마다 σ 를 붙이면 한 줄이 세 번 같은 말을 한다
 *  (CLAUDE.md 「얼라인」 의 «열 제목이 단위를 진다» 와 같은 규칙). */
export function knobWord(k: PaperLegKnobs): string {
  const z = [k.entryZ, k.exitZ, k.stopZ]
    .map((v) => String(Number(v.toFixed(2))))
    .join('/');
  return `${k.lookback}일 · ${z}σ · ${ENTRY_WORD[k.entryMode]}`;
}
