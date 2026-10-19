/* 차트 부품이 프롭을 **내용**으로 보는가 [2026-08-27].
 *
 * ── 무엇을 막는 가드인가 ────────────────────────────────────────────────────
 * 커서를 차트 위에 올려 둔 채 리드아웃 카드가 생겼다 사라지기를 반복했다
 * (실측 2026-08-27 라이브: 마우스 5px 이동에 카드 2번 생성·2번 제거, 조회
 * 시점 카드 0개). 뿌리는 계열을 세우는 이펙트의 의존성이 전부 참조 타입이라,
 * `dates={points.map((p) => p.t)}` 같은 평범한 호출부가 매 렌더 계열 전체의
 * 파괴·재생성을 부른 것이었다. 경위는 `src/chart/stable.ts` 머리에 있다.
 *
 * 수리는 **부품 쪽**에 했다 [OWNER 2026-08-27 — "부품부로 ㄱㄱ"]. 그러면 이
 * 가드가 지켜야 할 것도 부품이다:
 *
 *   1. 비교 함수가 «같다/다르다» 를 정확히 말하는가 (아래 §비교)
 *   2. 계열을 세우는 이펙트가 **날것 프롭을 의존성에 두지 않는가** (§의존성)
 *
 * 2 는 소스 스캔이다. 이 리포는 「가드는 안 넘긴 옵션을 못 본다」를 이미 한 번
 * 비싸게 배웠는데(docs/CHART_LANE_STATE.md §8), 여기서는 반대다 — 의존성 배열은
 * 소스에 **적혀 있는** 것이라 스캔이 실제로 볼 수 있다. 화면으로만 지키면
 * 다음 사람이 `sDates` 를 `dates` 로 되돌려도 아무 말이 없다.
 */

import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  sameLines,
  sameMarkLines,
  sameMarkers,
  sameNodes,
  samePriceLines,
  sameStrings,
  sameValues,
} from '../src/chart/stable';
import { stripComments } from './_source';

describe('비교 — 내용이 같으면 같다고 말한다', () => {
  it('값 배열은 원소로 본다 (참조가 달라도 같다)', () => {
    expect(sameValues([1, 2, null], [1, 2, null])).toBe(true);
    expect(sameValues([1, 2, null], [1, 2, 3])).toBe(false);
    expect(sameValues([1, 2], [1, 2, 3])).toBe(false);
    expect(sameValues(undefined, undefined)).toBe(true);
    expect(sameValues(undefined, [])).toBe(false);
  });

  it('`null` 과 `0` 은 다른 것이다 — 값 없음과 값 0', () => {
    expect(sameValues([0], [null])).toBe(false);
  });

  it('날짜 축', () => {
    expect(sameStrings(['2026-08-25'], ['2026-08-25'])).toBe(true);
    expect(sameStrings(['2026-08-25'], ['2026-08-26'])).toBe(false);
  });

  it('선은 **모양과 값**만 본다 — 색·서식 함수는 보지 않는다', () => {
    const shape = { id: 'a', values: [1, 2], width: 1 as const, axis: 'main' };
    /* 색 함수가 매 렌더 새 화살표인 호출부가 있다. 그것 때문에 계열을 다시
       세우면 수리 이전으로 돌아간다. */
    expect(sameLines([{ ...shape }], [{ ...shape }])).toBe(true);
    expect(sameLines([shape], [{ ...shape, values: [1, 3] }])).toBe(false);
    expect(sameLines([shape], [{ ...shape, id: 'b' }])).toBe(false);
    expect(sameLines([shape], [{ ...shape, width: 2 }])).toBe(false);
    expect(sameLines([shape], [{ ...shape, axis: 'aux' }])).toBe(false);
    expect(sameLines([shape], [{ ...shape, area: 'dots' }])).toBe(false);
    expect(sameLines([shape], [shape, shape])).toBe(false);
  });

  it('표시점·상수선·사실선·노드', () => {
    expect(sameMarkers([{ index: 3 }], [{ index: 3 }])).toBe(true);
    expect(sameMarkers([{ index: 3 }], [{ index: 4 }])).toBe(false);
    expect(samePriceLines([{ value: 0 }], [{ value: 0 }])).toBe(true);
    expect(samePriceLines([{ value: 0 }], [{ value: 0, dash: true }])).toBe(false);
    expect(sameMarkLines([{ index: 1, label: '진입' }], [{ index: 1, label: '진입' }])).toBe(true);
    expect(sameMarkLines([{ index: 1, label: '진입' }], [{ index: 1, label: '청산' }])).toBe(false);
    const n = { x: 36, label: '3Y', weight: 8 };
    expect(sameNodes([{ ...n }], [{ ...n }])).toBe(true);
    expect(sameNodes([n], [{ ...n, weight: 9 }])).toBe(false);
  });
});

/** 계열을 세우는 이펙트의 의존성 배열을 소스에서 꺼낸다. */
function structureDeps(file: string): string[] {
  const src = stripComments(fs.readFileSync(path.join(process.cwd(), file), 'utf8'));
  /* 계열을 **세우는** 이펙트가 «구조» 이펙트다. 그 블록의 끝에 붙은
     `}, [ … ]);` 를 읽는다.

     ★탐지를 이름으로 한다, 호출 모양이 아니라 [2026-10-19]. 종전에는 문자열
     `'addLine('` 를 찾았는데 막대 계열이 들어오면서 호출이
     `(ln.kind === 'histogram' ? addHistogram : addLine)(` 가 됐다 — 그 순간
     `addLine(` 이 **문자열로 없어져** 탐지가 샜다. 아래 `deps.length > 0` 이
     그것을 잡아 주긴 했지만(빈 목록이면 실패), 실패 문장이 「의존성이 없다」라
     진짜 원인을 안 말했다. 세우는 함수가 더 늘어도 안 새도록 이름으로 센다. */
  const ADDERS = /\badd(Line|Histogram)\b/;
  const chunks = src.split('useEffect(');
  const found: string[] = [];
  for (const c of chunks) {
    if (!ADDERS.test(c)) continue;
    const m = /\}\s*,\s*\[([^\]]*)\]\s*\)/.exec(c);
    if (m) found.push(...m[1].split(',').map((s) => s.trim()).filter(Boolean));
  }
  return found;
}

describe('의존성 — 구조 이펙트는 날것 프롭을 안 본다', () => {
  /* 날것 이름 = 호출부가 매 렌더 새로 만들 수 있는 것들. 안정화된 짝은
     `sDates`·`sLines` 처럼 `s` 로 시작한다. */
  const RAW = ['dates', 'lines', 'markers', 'priceLines', 'markLines', 'nodes', 'tickFormat'];

  for (const file of ['src/chart/TimeChart.tsx', 'src/chart/ScaleChart.tsx']) {
    it(`${file}`, () => {
      const deps = structureDeps(file);
      expect(deps.length).toBeGreaterThan(0);
      expect(deps.filter((d) => RAW.includes(d))).toEqual([]);
    });
  }

  it('두 부품 다 `useStable` 을 지난다', () => {
    for (const file of ['src/chart/TimeChart.tsx', 'src/chart/ScaleChart.tsx']) {
      const src = stripComments(fs.readFileSync(path.join(process.cwd(), file), 'utf8'));
      expect(src).toContain('useStable(');
    }
  });

  it('짝 커서는 **세운 적이 있을 때만** 지운다', () => {
    /* 그냥 지우면 커서가 이 차트 위에 있을 때도 크로스헤어가 내려가고, 그
       순간 빈 이벤트가 리드아웃 카드를 지운다 — 번쩍거림의 두 번째 뿌리였다.
       Main 미리보기는 `syncIndex` 를 아예 안 넘기므로 렌더마다 그 일이 났다. */
    const src = stripComments(
      fs.readFileSync(path.join(process.cwd(), 'src/chart/TimeChart.tsx'), 'utf8'),
    );
    const i = src.indexOf('clearCrosshairPosition');
    expect(i).toBeGreaterThan(0);
    expect(src.slice(Math.max(0, i - 400), i)).toContain('syncedRef.current');
  });
});
