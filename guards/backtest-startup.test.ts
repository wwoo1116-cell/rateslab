import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { splitKrw } from '../src/lib/krw';

/**
 * 개시(네 번째 칸)의 표시 규칙 [OWNER, 2026-08-14 — "개시손익 적으면 걍 무시해도
 * 될 거 같은데"] — 엔진은 그 밤을 따로 세고, **화면은 평가에 접는다.**
 *
 * 접는 자리가 둘이다(헤드라인 분해 · 대사 행). 한쪽만 접으면 3분해와 대사표가
 * 같은 날을 두고 다른 평가를 말한다 — 총손익은 불변이라 합계 검증으로는 안
 * 잡히는 종류의 어긋남이다.
 */

const read = (p: string) => fs.readFileSync(path.join(__dirname, '..', p), 'utf8');

describe('splitKrw — 개시는 평가에 접힌다', () => {
  it('startup 이 평가로 들어가고 캐리는 변하지 않는다', () => {
    const flat = splitKrw(100_000_000, 60_000_000, 20_000_000, 0);
    const folded = splitKrw(100_000_000, 50_000_000, 20_000_000, 10_000_000);
    expect(folded.uVal).toBe(flat.uVal);
    expect(folded.uRoll).toBe(flat.uRoll);
    expect(folded.uCarry).toBe(flat.uCarry);
  });

  it('옛 세션의 결과(필드 없음)는 기본값 0 으로 그대로 선다', () => {
    const u = splitKrw(1_234_567, 1_000_000);
    expect(u.uPnl).toBe(u.uVal + u.uRoll + u.uCarry);
  });
});

describe('접는 자리 둘 다 접는다 (소스 핀)', () => {
  it('헤드라인 분해가 포지션의 startup 을 더해 넘긴다', () => {
    const src = read('src/backtest/BacktestWindow.tsx');
    expect(src).toMatch(/startup \+= p\.startup \?\? 0/);
    /* 인자 하나가 더 붙었다 — 풀투파 [OWNER 2026-09-28 — 「칸을 나눈다」].
       이 핀이 재는 것은 **개시가 넘어가는가**이므로 거기까지만 본다. */
    expect(src).toMatch(/splitKrw\(result\.pnl, valuation, rolldown, startup/);
  });

  it('대사 행의 평가가 startup 을 접는다', () => {
    // 어댑터는 창 밖으로 나왔다 [2026-08-21] — `src/backtest/recon.ts` 의 머리글.
    const src = read('src/backtest/recon.ts');
    expect(src).toMatch(/r\.valuation \+ \(r\.startup \?\? 0\)/);
  });

  it('백엔드는 네 칸을 따로 보낸다 — 접는 것은 표시 결정이다', () => {
    const be = read('backend/app/backtest.py');
    expect(be).toMatch(/"startup": round\(/);
  });
});
