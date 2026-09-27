/* 「그날 1등」 줄의 가드 [OWNER 2026-09-23 — "들어간 시점에서의 최적 파라미터로"
 * → 「손으로 치되 1등을 제안」].
 *
 * 재는 것은 셋이다.
 *   ① 1등이 서는 **모든** 문장에 경고가 붙는다 — 「1등」이라고만 적으면 고르라는
 *      말로 읽힌다(PBO 레인).
 *   ② 화면은 순위를 **찾기만** 한다 — 글자로 온 조건을 수로 맞추되, 반쪽·프리셋
 *      밖은 칸이 아니다.
 *   ③ 화면에 「채택」이 없다 — 제안을 칸에 꽂는 손잡이가 생기면 이 줄은 제안이
 *      아니라 기본값이 된다(오너 선택의 반대편).
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { findCell, knobsComplete, type PaperSuggest, type PaperSuggestCell } from '@/pm/api';
import { SUGGEST_CAVEAT, suggestLine } from '@/pm/suggestLine';

const cell = (over: Partial<PaperSuggestCell> = {}): PaperSuggestCell => ({
  lookback: 60, entryZ: 2, exitZ: 0.5, stopZ: 2.5, entryMode: 'level',
  rank: 3, cdarRatio: 1.2, totalPnl: 1e6, maxDrawdown: -2e5, numTrades: 4, winRate: 0.5,
  ...over,
});

const got = (over: Partial<PaperSuggest> = {}): PaperSuggest => ({
  series: 'BSS-2Y', label: 'BSS 2Y', entry: '2026-09-22', asof: '2026-09-22',
  from: '2025-09-22', days: 245, span: '1y', rankKey: 'cdarRatio', inSample: true,
  cells: 162, ranked: 150,
  top: cell({ lookback: 120, entryZ: 2.5, exitZ: 0, stopZ: 3, rank: 1 }),
  list: [cell({ lookback: 120, entryZ: 2.5, exitZ: 0, stopZ: 3, rank: 1 }), cell()],
  why: null,
  ...over,
});

describe('findCell — 찾기만 한다', () => {
  it('글자로 온 조건을 수로 맞춘다', () => {
    const c = findCell(got().list, {
      lookback: '60', entryZ: '2.0', exitZ: '.5', stopZ: '2.5', entryMode: 'level',
    });
    expect(c?.rank).toBe(3);
  });
  it('반쪽 조건은 칸이 아니다', () => {
    const half = { lookback: '60', entryZ: '2', exitZ: undefined, stopZ: '2.5', entryMode: 'level' as const };
    expect(findCell(got().list, half)).toBeUndefined();
    expect(knobsComplete(half)).toBe(false);
    expect(knobsComplete(undefined)).toBe(false);
  });
  it('프리셋 밖은 다 찼어도 칸이 없다', () => {
    const out = { lookback: '45', entryZ: '2', exitZ: '0.5', stopZ: '2.5', entryMode: 'level' as const };
    expect(knobsComplete(out)).toBe(true);
    expect(findCell(got().list, out)).toBeUndefined();
  });
  it('진입 규칙이 다르면 다른 칸이다', () => {
    expect(findCell(got().list, {
      lookback: '60', entryZ: '2', exitZ: '0.5', stopZ: '2.5', entryMode: 'touch',
    })).toBeUndefined();
  });
});

describe('suggestLine — 1등 옆에는 늘 경고가 선다', () => {
  const base = { label: 'BSS 2Y', entryReady: true, busy: false, knobs: undefined };

  it('1등을 표의 꼴로 적고 경고를 붙인다', () => {
    const s = suggestLine({ ...base, got: got() });
    expect(s).toContain('그날 1등 120일 · 2.5/0/3σ · 이탈 즉시');
    expect(s).toContain('2026-09-22까지의 자료');
    expect(s).toContain('지난 1년');
    expect(s).toContain('CDaR 비 기준 150칸 중');
    expect(s).toContain('거래 4건');
    expect(s.endsWith(SUGGEST_CAVEAT)).toBe(true);
  });
  it('내 조건이 다 찼으면 등수를, 프리셋 밖이면 그 사실을 적는다', () => {
    const mine = suggestLine({ ...base, got: got(), knobs: {
      lookback: '60', entryZ: '2', exitZ: '0.5', stopZ: '2.5', entryMode: 'level',
    } });
    expect(mine).toContain('내 조건은 3등');
    expect(mine).toContain(SUGGEST_CAVEAT);
    const out = suggestLine({ ...base, got: got(), knobs: {
      lookback: '45', entryZ: '2', exitZ: '0.5', stopZ: '2.5', entryMode: 'level',
    } });
    expect(out).toContain('프리셋 밖');
    const half = suggestLine({ ...base, got: got(), knobs: {
      lookback: '60', entryZ: undefined, exitZ: undefined, stopZ: undefined, entryMode: 'level',
    } });
    expect(half).not.toContain('내 조건');
  });
  it('못 냈으면 사유를 적고 1등 문장을 만들지 않는다', () => {
    const s = suggestLine({ ...base, got: got({ top: null, list: [], ranked: 0,
      why: '격자가 순위를 못 매겼어요(낙폭이 없어 CDaR 비가 안 서는 칸뿐)' }) });
    expect(s).toContain('순위를 못 매겼어요');
    expect(s).not.toContain('σ');
    expect(suggestLine({ ...base, failed: '모르는 계열이에요: X' })).toContain('못 냈어요 — 모르는 계열');
    expect(suggestLine({ ...base, entryReady: false })).toContain('체결일을 다 치면');
    expect(suggestLine({ ...base, busy: true })).toContain('재는 중');
    expect(suggestLine({ ...base })).toBe('');
  });
});

describe('PortfolioPage — 제안이지 기본값이 아니다', () => {
  const src = readFileSync(path.resolve(__dirname, '../src/pm/PortfolioPage.tsx'), 'utf8');
  it('문장은 suggestLine 하나가 만든다', () => {
    expect(src).toMatch(/suggestLine\(/);
  });
  it('제안을 칸에 꽂는 손잡이가 없다 — 「채택」 금지', () => {
    /* 1등의 값을 읽어 노브 칸의 setter 로 보내는 줄이 있으면 이 줄은 제안이 아니다. */
    expect(src).not.toMatch(/suggest\??\.top\??\.(lookback|entryZ|exitZ|stopZ|entryMode)/);
    expect(src).not.toMatch(/setKnob\w*\([^)]*suggest/);
  });
});
