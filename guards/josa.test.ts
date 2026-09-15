import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { eul, eun, euro, gwa, i, withJosa } from '../src/lib/josa';
import { stripComments } from './_source';

/**
 * 조사는 **한 곳**에서만 정한다.
 *
 * ── 왜 이 가드가 생겼나 (2026-09-15 디자인 점검) ────────────────────────────
 * 화면 셋이 각자 다른 방법으로 같은 문제를 풀고 있었고 셋 다 틀렸다.
 *
 *   `ui/DataState.tsx`   `{what}을` 고정 → 「시장 데이터**을** 불러오지 못했어요」
 *                        (실제 화면 스크린샷으로 확인)
 *   `lab/…/note.ts`      `${what}을` 고정 → what 이 「+25bp」면 「bp**을**」
 *   `ui/BottomStrip.tsx` `(으)로` 회피형 → 낭독기가 「십와이 **으로** 이동」
 *
 * 들어가는 말 아홉 중 넷(발행 캘린더·시장 데이터·오늘의 커브·온톨로지)이
 * 받침이 없어 「를」이어야 했다. 두 컴포넌트에 각각 들어가니 **여덟 자리**다.
 *
 * ── 이 가드가 재는 두 가지 ──────────────────────────────────────────────────
 * (1) 헬퍼가 이 앱이 실제로 넣는 말을 맞게 가른다 — 한글·영문·숫자 꼬리 전부.
 * (2) 소스에 **조사를 손으로 붙인 자리**가 다시 안 생긴다. 변수 보간 바로 뒤에
 *     조사가 오면 그건 앞말을 안 보고 정한 것이다.
 */

const ROOT = path.resolve(import.meta.dirname, '..');
const SRC = path.join(ROOT, 'src');
const HELPER = 'src/lib/josa.ts';

function walk(dir: string, exts: string[]): string[] {
  const out: string[] = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p, exts));
    else if (exts.some((x) => e.name.endsWith(x))) out.push(p);
  }
  return out;
}

/** `${...}을` · `{what}를` 처럼 **보간 바로 뒤**에 붙은 조사. */
const HARDCODED = /\}(을|를|이가|은|는|과|와|으로)(?=[\s.,)」』"'`]|$)/gm;
/** 「(으)로」 같은 회피형 — 낭독기가 그대로 읽는다. */
const EVASIVE = /\((으|이|을|과)\)(로|가|를|와)/g;

describe('조사는 한 곳에서만 정한다', () => {
  it('받침 있는 말 — 을·이·은·과·으로', () => {
    expect(eul('시계열')).toBe('을'); // ㄹ
    expect(eul('커브 표면')).toBe('을'); // ㄴ
    expect(eul('RV 분석')).toBe('을'); // ㄱ
    expect(i('사람')).toBe('이');
    expect(eun('사람')).toBe('은');
    expect(gwa('사람')).toBe('과');
    expect(euro('사람')).toBe('으로');
  });

  it('받침 없는 말 — 를·가·는·와·로', () => {
    expect(eul('시장 데이터')).toBe('를');
    expect(eul('오늘의 커브')).toBe('를');
    expect(eul('발행 캘린더')).toBe('를');
    expect(eul('온톨로지')).toBe('를');
    expect(i('커브')).toBe('가');
    expect(eun('커브')).toBe('는');
    expect(gwa('커브')).toBe('와');
    expect(euro('커브')).toBe('로');
  });

  it('ㄹ 받침은 「으로」가 아니라 「로」다', () => {
    expect(euro('시계열')).toBe('로'); // 시계열로
    expect(euro('1Y')).toBe('로'); // 일와이 — Y 는 받침 없음
    expect(euro('10Y')).toBe('로');
    expect(euro('서울')).toBe('로');
    expect(euro('강남')).toBe('으로'); // ㅁ
  });

  it('영문 꼬리는 한국어 독음의 받침으로 가른다', () => {
    expect(eul('Momentum')).toBe('을'); // 모멘텀 — ㅁ
    expect(eul('Mean Reversion')).toBe('을'); // 리버전 — ㄴ
    expect(eul('RV')).toBe('를'); // 알브이 — 없음
    expect(eul('3s10s')).toBe('를'); // 에스 — 없음
    expect(eul('1Yx1Y')).toBe('를'); // 와이 — 없음
    expect(eul('Excel')).toBe('을'); // 엑셀 — ㄹ
  });

  it('숫자 꼬리도 독음으로 가른다', () => {
    expect(eul('+25bp')).toBe('를'); // 비피 — 없음
    expect(eul('3')).toBe('을'); // 삼 — ㅁ
    expect(eul('2')).toBe('를'); // 이 — 없음
    expect(eul('7')).toBe('을'); // 칠 — ㄹ
    expect(euro('7')).toBe('로'); // ㄹ 이라 「칠로」
  });

  it('못 읽는 꼬리는 받침 없음으로 떨어진다 — 덜 어색한 쪽', () => {
    expect(eul('(주)')).toBe('를');
    expect(eul('')).toBe('를');
  });

  it('withJosa 는 앞말과 붙여 준다', () => {
    expect(withJosa('시장 데이터', eul)).toBe('시장 데이터를');
    expect(withJosa('시계열', eul)).toBe('시계열을');
  });

  it('소스에 조사를 손으로 붙인 자리가 없다', () => {
    const bad: string[] = [];
    for (const f of walk(SRC, ['.ts', '.tsx'])) {
      const name = path.relative(ROOT, f).replace(/\\/g, '/');
      if (name === HELPER) continue; // 헬퍼 자신은 조사를 적는 곳이다
      const body = stripComments(fs.readFileSync(f, 'utf8'));
      for (const m of body.matchAll(HARDCODED)) bad.push(`${name}: …}${m[1]}`);
      for (const m of body.matchAll(EVASIVE)) bad.push(`${name}: ${m[0]} — 회피형`);
    }
    expect(bad).toEqual([]);
  });
});
