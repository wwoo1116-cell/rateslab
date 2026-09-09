/* 채점 잠금 — Momentum 화면이 **동결된 사전등록을 훔쳐보지 못하게** 한다.
 *
 * ## 왜 가드가 필요한가
 *
 * `data\krw-macro-vintage\PREREG.md` 가 2026-09-08 에 동결됐고 채점 대상은 그
 * 다음 영업일부터다. 그 문서가 「판정일까지 들여다보지 말 것 — 중간에 보는 것
 * 자체가 사전등록을 훼손한다」고 못박고 있다. 그런데 이 화면은 매일 열린다.
 * 잠금이 없으면 화면이 그 규율을 **매일** 어기는 도구가 된다.
 *
 * ## 이 파일이 지는 명제 셋
 *
 * **자르는 자리가 서버다.** 프런트에서 자르면 잘린 값이 네트워크 탭에 그대로
 * 남는다 — 그건 잠금이 아니라 가리개다. `build_book` 이 `p["t"] <= FREEZE` 로
 * 거른다.
 *
 * **세 다리를 다 자른다.** 추세만 남기면 50/50 과의 차로 매크로를 역산할 수
 * 있다. 한 규칙이 무너뜨리기 어렵다.
 *
 * **동결일은 상수다.** 코드 여기저기에 날짜가 흩어지면 한 곳만 고쳐지는 날이
 * 온다.
 */

import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const root = path.resolve(import.meta.dirname, '..');
const read = (rel: string) => fs.readFileSync(path.join(root, rel), 'utf8');

/** 파이썬에는 `stripComments`(TS용)를 못 쓴다 — `#` 줄 주석과 `"""` 독스트링을
 *  걷는다. 줄 수는 보존한다(실패가 줄 번호를 말할 수 있게). */
function stripPy(source: string): string {
  return source
    .replace(/(^|\n)(\s*)(?:r?"""|r?''')[\s\S]*?(?:"""|''')/g, (m) =>
      m.replace(/[^\n]/g, ' '),
    )
    .replace(/(^|[^'"])#.*$/gm, '$1');
}

describe('Momentum 채점 잠금', () => {
  const code = stripPy(read('backend/app/momentum.py'));

  it('동결일이 상수 하나다', () => {
    expect(code).toMatch(/FREEZE\s*=\s*"2026-09-08"/);
    /* 날짜 리터럴이 그 상수 말고 또 있으면 언젠가 한쪽만 고쳐진다. */
    const literals = code.match(/"20\d\d-\d\d-\d\d"/g) ?? [];
    expect(literals).toEqual(['"2026-09-08"']);
  });

  it('장부가 동결일 이후를 잘라서 낸다 — 자르는 자리가 서버다', () => {
    expect(code).toMatch(/p\["t"\]\s*<=\s*FREEZE/);
  });

  it('세 다리가 모두 같은 절단을 통과한다', () => {
    /* `cut(...)` 을 거치지 않고 `points` 를 그대로 채점하면 그 다리가 샌다.
       정의(`def _card(...)`)는 호출이 아니므로 뺀다. */
    const calls = (code.match(/(?<!def )_card\(([^)]*)\)/g) ?? []).filter(
      (c) => !c.includes('list[dict]'),
    );
    expect(calls.length).toBeGreaterThanOrEqual(3);
    for (const c of calls) {
      expect(/cut\(|_pts|blend/.test(c), c).toBe(true);
    }
  });

  it('프런트는 절단을 «하지» 않는다 — 서버가 준 것만 그린다', () => {
    const page = read('src/momentum/MomentumPage.tsx');
    const api = read('src/momentum/api.ts');
    for (const s of [page, api]) {
      expect(s).not.toMatch(/2026-09-08/);
      expect(s).not.toMatch(/\.filter\([^)]*freeze/i);
    }
  });

  it('화면이 잠겼다는 사실을 «말한다» — 조용히 비우지 않는다', () => {
    expect(code).toMatch(/판정일까지 안 보여드려요/);
    expect(read('src/momentum/MomentumPage.tsx')).toMatch(/book\.lock\.note/);
  });
});
