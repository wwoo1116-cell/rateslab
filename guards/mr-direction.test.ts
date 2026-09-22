/* 전략 실험 창의 **방향은 부호말이 아니라 다리다** [OWNER 2026-08-25 — "v2에서
 * Strategy/Mean Reversion에서 BSS에서 숏은 없는거야,, 현물대차매도는 안할거거든"].
 *
 * ## 이 파일이 지는 명제 둘
 *
 * **「롱/숏」이라고 적으면 반대로 읽힌다.** 엔진의 `+1` 은 «값이 오르면 버는 쪽»
 * 이고, 그게 실제로 무슨 다리인지는 **계열마다 다르다**: FUT 는 금리 계열이라
 * 「롱」이 선물 매도이고, BSS(IRS − 국고)는 2026-09-22 규약 뒤집기 뒤로 「롱」이
 * 국고 **매수**다(그 전에는 매도였다). 낱말 하나로는 못 적는다 — 북의
 * `directionLabel` 이 플라이에서 내린 판단(«단어를 만들지 말고 다리를 적는다»)이
 * 여기에도 들고, **규약이 바뀌어도 그 판단은 안 바뀐다**는 것이 이 절의 값이다.
 *
 * **못 하는 거래는 화면에 없어야 한다.** 이 데스크는 현물을 빌려 팔지 않는다 —
 * 백테스트·시뮬의 현금채권이 매수만 받는 그 규칙(cashbond.py [OWNER 2026-08-14])
 * 과 같은 것이고, 이름이 서버에 있으므로 화면은 짓지 않는다(§16).
 *
 * 방향의 뜻 자체(BSS 는 `-1` = 국고 매수)는 파이썬 쪽 시험이 진다
 * (`backend/tests/test_mr.py::test_bss_has_no_short_side`) — 부호와 이름이
 * 갈리는 사고를 잡는 자리는 그 계산이 사는 곳이다.
 */

import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments } from './_source';

const root = path.resolve(import.meta.dirname, '..');
const src = (rel: string) => stripComments(fs.readFileSync(path.join(root, rel), 'utf8'));

describe('MR 전략 창의 방향', () => {
  it('부호말을 손으로 적지 않는다 — 이름은 서버가 준다', () => {
    const code = src('src/mr/StrategyWindow.tsx');
    expect(code).not.toMatch(/['"]롱['"]/);
    expect(code).not.toMatch(/['"]숏['"]/);
    /* 표 칸은 서버가 지은 두 이름 중 하나를 고른다. */
    expect(code).toMatch(/run\.dirs\.plus\s*:\s*run\.dirs\.minus/);
  });

  it('한 방향뿐이면 그 사실과 못 들어간 신호 수를 화면이 말한다', () => {
    const code = src('src/mr/StrategyWindow.tsx');
    /* 조용히 빠진 진입은 «신호가 없었다» 로 읽힌다 — 세어서 말한다. */
    expect(code).toMatch(/run\.dirs\.blocked\.spells/);
    expect(code).toMatch(/run\.dirs\.why/);
  });

  it('계약에 방향 사전이 있다 — 허용 방향·두 이름·사유·막힌 수', () => {
    const api = src('src/mr/api.ts');
    expect(api).toMatch(/dirs:\s*MrStrategyDirs/);
    for (const key of ['allowed', 'plus', 'minus', 'why', 'blocked']) {
      expect(api).toMatch(new RegExp(`${key}:`));
    }
  });

  it('현금채권 매수-only 규칙과 같은 말을 쓴다 — 규칙이 둘이면 둘로 갈린다', () => {
    /* 서버가 짓는 이름의 낱말(「국고 매수」·「IRS 페이」)은 북의 방향 라벨과
       같은 어휘여야 한다 — 두 화면이 같은 거래를 딴 이름으로 부르면 안 된다.

       ★2026-09-22 규약 뒤집기 [OWNER — "스왑 - 채권현물 또는 국채선물"]:
       허용 방향이 `(-1,)` → `(1,)` 로 **옮겨 앉았다.** 금지는 부호가 아니라
       「국고를 파는가」에 걸려 있고, 계열 부호를 뒤집으면 같은 거래가 반대
       부호로 불리므로 둘이 같이 움직여야 **같은 거래**가 계속 막힌다.
       그 불변량 자체는 `backend/tests/test_mr_convention.py` 가 잰다. */
    const py = fs.readFileSync(path.join(root, 'backend/app/mr.py'), 'utf8');
    expect(py).toMatch(/TRADABLE_DIRS = \{"bss": \(1,\)/);
    expect(py).toContain('IRS 페이 · 국고 매수');
    const book = src('src/backtest/book.ts');
    expect(book).toContain('IRS 페이 · 선물 매수');
  });
});
