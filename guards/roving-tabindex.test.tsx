import fs from 'node:fs';
import path from 'node:path';

import { ThemeProvider } from '@coinbase/cds-web';
import { defaultTheme } from '@coinbase/cds-web/themes/defaultTheme';
import { fireEvent, render } from '@testing-library/react';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';

import { InstrumentTable } from '../src/table/InstrumentTable';
import type { Row } from '../src/table/rows';
import { stripComments } from './_source';

/**
 * ★**roving tabindex** — 긴 목록은 탭 정지 **한 칸**이다 [2026-10-19].
 *
 * ## 왜 이 파일이 필요한가
 *
 * 이 규칙은 CLAUDE.md 「키보드와 접근성」 규칙 1 이고, 터미널 레인이 2026-08-27 에
 * **실측으로** 세운 것이다(`terminal/apps/TableApp.tsx:34` — 「탭 348번이고, 가상
 * 스크롤이라 탭이 아직 그려지지 않은 행에는 닿지도 못한다 = 반쪽 키보드」).
 *
 * 그런데 그것을 재는 가드(`terminal-keyboard.test.ts:47`)의 `PLOT_APPS` 는
 * **`src/terminal/` 만** 들었다. 그래서 같은 결함이 **배운 원본인 제품 표**
 * (`src/table/InstrumentTable.tsx`)에 2026-10-19 까지 그대로 서 있었다 — 가드
 * 2,005판이 전부 초록인 채로. 범위가 좁은 가드는 **고친 자리만** 지킨다.
 *
 * 이 파일은 그 범위를 앱 전체로 넓힌다. 둘로 잰다: ①은 **동작**(진짜로 화살표가
 * 움직이나), ②는 **전수 등록**(새 파일이 조용히 빠져나가지 못하게).
 */

/** ★id 에 **escape 가 필요한 문자**를 일부러 넣는다. 화살표 이동은 id 로 선택자를
 *  조립하므로(`CSS.escape`), 전부 `R0` 같은 안전한 id 면 그 경로가 돌지 않은 채
 *  초록이 된다 — 실제로 2026-10-19 에 그 꼴로 한 번 속았다(`guards/setup.ts` 머리).
 *  제품 id(`IRC-1Y-3Y`)는 하이픈뿐이라 안전하지만, 그 방어가 **작동하는지**는
 *  여기서만 드러난다. */
const IDS = ['R0', 'R.1', 'R:2'];

const ROWS: Row[] = [0, 1, 2].map(
  (i) =>
    ({
      id: IDS[i],
      label: `R${i}`,
      group: 'spread',
      unit: 'bp',
      now: 1,
      changes: { d1: 1, mtd: 1, ytd: 1 },
      pct: 50,
      seriesId: IDS[i],
      rangeHigh: 2,
      rangeLow: 0,
      rangeAvg: 1,
      sortKey: [i + 1, i + 2],
      movePct: 0,
      key: true,
    }) as Row,
);

/* jsdom 에 레이아웃이 없어서 가상화가 0행을 그린다 — `hover-preview.test.tsx` 의
   그 스텁과 같은 것이고 까닭은 그 파일 머리에 적혀 있다. 아래 어느 단언도 픽셀을
   읽지 않는다. */
const SIZE = { offsetWidth: 900, offsetHeight: 600 };
const originals: Record<string, PropertyDescriptor | undefined> = {};
beforeAll(() => {
  for (const [prop, value] of Object.entries(SIZE)) {
    originals[prop] = Object.getOwnPropertyDescriptor(HTMLElement.prototype, prop);
    Object.defineProperty(HTMLElement.prototype, prop, { configurable: true, value });
  }
});
afterAll(() => {
  for (const [prop, desc] of Object.entries(originals)) {
    if (desc) Object.defineProperty(HTMLElement.prototype, prop, desc);
  }
});

function setup() {
  const onSelect = vi.fn();
  const { container } = render(
    <ThemeProvider theme={defaultTheme} activeColorScheme="light">
      <div style={{ overflowY: 'auto', height: 600 }}>
        <InstrumentTable rows={ROWS} onSelect={onSelect} onHover={() => undefined} />
      </div>
    </ThemeProvider>,
  );
  const trs = () => [...container.querySelectorAll<HTMLElement>('tr[data-sr-row]')];
  expect(trs().length, '행이 안 그려졌어요 — 동작이 아니라 하네스가 깨진 거예요').toBe(3);
  const host = container.querySelector<HTMLElement>('div[tabindex="-1"]')!;
  const stops = () => trs().filter((t) => t.getAttribute('tabindex') === '0');
  return { onSelect, container, trs, host, stops };
}

describe('① 동작 — 표는 탭 정지 한 칸이고 안에서는 화살표다', () => {
  it('탭 정지가 **정확히 하나**다 — 행마다 두면 표가 함정이 된다', () => {
    const { stops, trs } = setup();
    expect(stops().length).toBe(1);
    expect(stops()[0]).toBe(trs()[0]);
    /* 나머지는 `-1` 이다. 속성이 **없는** 것과는 다르다 — 없으면 `<tr>` 이
       프로그램 초점의 대상이 아니고, 그러면 아래 초점 이동이 안 된다. */
    for (const t of trs().slice(1)) expect(t.getAttribute('tabindex')).toBe('-1');
  });

  it('↓ 가 탭 정지와 **초점**을 같이 옮긴다', () => {
    const { host, trs, stops } = setup();
    fireEvent.keyDown(host, { key: 'ArrowDown' });
    expect(stops().length).toBe(1);
    expect(stops()[0]).toBe(trs()[1]);
    expect(document.activeElement).toBe(trs()[1]);
  });

  it('↑ 가 되돌리고, 양 끝에서는 **멈춘다**(한 바퀴 돌지 않는다)', () => {
    const { host, trs, stops } = setup();
    fireEvent.keyDown(host, { key: 'ArrowDown' });
    fireEvent.keyDown(host, { key: 'ArrowUp' });
    expect(stops()[0]).toBe(trs()[0]);
    /* 첫 줄에서 더 올라가도 마지막 줄로 넘어가지 않는다 — 넘어가면 「목록이
       끝났다」를 키보드로 알 길이 없다. */
    fireEvent.keyDown(host, { key: 'ArrowUp' });
    expect(stops()[0]).toBe(trs()[0]);
  });

  it('Home·End 가 양 끝으로 간다', () => {
    const { host, trs, stops } = setup();
    fireEvent.keyDown(host, { key: 'End' });
    expect(stops()[0]).toBe(trs()[2]);
    fireEvent.keyDown(host, { key: 'Home' });
    expect(stops()[0]).toBe(trs()[0]);
  });

  it('PageDown 이 열 줄 뛰되 **끝을 넘지 않는다**', () => {
    const { host, trs, stops } = setup();
    fireEvent.keyDown(host, { key: 'PageDown' });
    expect(stops()[0]).toBe(trs()[2]);
  });

  it('Enter 와 Space 가 고른다 — 이동과 고르기는 다른 키다', () => {
    const { host, onSelect, trs } = setup();
    fireEvent.keyDown(trs()[0], { key: 'Enter' });
    expect(onSelect.mock.calls.map((c) => c[0]?.id)).toEqual(['R0']);
    fireEvent.keyDown(host, { key: 'ArrowDown' });
    fireEvent.keyDown(trs()[1], { key: ' ' });
    expect(onSelect.mock.calls.map((c) => c[0]?.id)).toEqual(['R0', 'R.1']);
  });

  it('정렬 버튼 위에서는 화살표를 **안 먹는다** — 거기선 다음 컨트롤이다', () => {
    const { container, host, trs, stops } = setup();
    const btn = container.querySelector<HTMLElement>('thead button');
    expect(btn, '열 머리에 정렬 버튼이 없어요 — 이 단언의 전제가 사라졌어요').not.toBeNull();
    fireEvent.keyDown(btn!, { key: 'ArrowDown' });
    expect(stops()[0], '버튼 위의 화살표가 행을 움직였어요').toBe(trs()[0]);
    /* 같은 키가 표 위에서는 듣는다 — 위 단언이 「화살표가 아예 죽었다」를
       통과시키지 않게 대조한다. */
    fireEvent.keyDown(host, { key: 'ArrowDown' });
    expect(stops()[0]).toBe(trs()[1]);
  });
});

const SRC = path.resolve(import.meta.dirname, '../src');

function walk(dir: string, out: string[] = []): string[] {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (e.name.endsWith('.tsx')) out.push(p);
  }
  return out;
}

const FILES = walk(SRC).map((f) => ({
  rel: path.relative(SRC, f).split(path.sep).join('/'),
  src: stripComments(fs.readFileSync(f, 'utf8')),
}));

const BARE_STOP = /tabIndex=\{0\}/;
const ROVING = /tabIndex=\{[^}]*\?\s*0\s*:\s*-1\s*\}/;

describe('② 전수 등록 — 새 파일이 조용히 빠져나가지 못한다', () => {
  /** 긴 목록을 가상화하는 표. 손 목록이 아니라 **발견**이다 — 목록이 좁아서
   *  결함이 살아남은 것이 이 파일의 존재 이유다. */
  const virt = FILES.filter((f) => f.src.includes('useVirtualizer'));
  const VIRT = ['table/InstrumentTable.tsx', 'terminal/apps/TableApp.tsx'];

  it('가상화 표가 둘이다 — 늘면 아래 단언이 그 파일도 같이 잰다', () => {
    expect(virt.map((f) => f.rel).sort()).toEqual([...VIRT].sort());
  });

  it.each(VIRT)('%s — 행의 탭 정지가 **조건부**다', (rel) => {
    const src = virt.find((f) => f.rel === rel)!.src;
    /* 「한 줄만 0, 나머지는 −1」의 꼴. 상수 `tabIndex={0}` 이 행에 붙으면 탭이
       그려진 행 전부를 걷고, 안 그려진 행에는 닿지도 못한다. */
    expect(src, '행에 조건부 tabIndex 가 없어요 — roving 이 아니에요').toMatch(ROVING);
    expect(BARE_STOP.test(src), '상수 tabIndex={0} 이 남아 있어요').toBe(false);
  });

  /** 그림 축 — `<svg>` 를 손으로 그리는 화면 전부. 셋으로만 갈린다. */
  const plots = FILES.filter((f) => f.src.includes('<svg')).map((f) => f.rel);

  /** 그림 전체가 위젯 하나다 — `role="application"` + 화살표. */
  const ONE_WIDGET = [
    'lab/creditdts/CreditDtsPage.tsx',
    'lab/model/model/WiringGraph.tsx',
    'terminal/apps/ChartApp.tsx',
    'terminal/apps/GraphApp.tsx',
    'terminal/apps/TimelineApp.tsx',
  ];
  /** 포인터 **지름길**이다 — 같은 목적지로 가는 키보드 경로가 **다른 곳**에 있다
   *  (`rv/RankingTable.tsx` 의 행마다 선 `<button>`). 그림은 탭 정지가 아니다.
   *  같은 계약을 `rv/TenorHeat.tsx:16`·`rv/ScoreHeat.tsx:15` 가 글로 적어 뒀다. */
  const POINTER_SHORTCUT = ['rv/RvScatter.tsx'];
  /** 아직 안 고친 자리. **비어 있다.** `WiringGraph`(노드 35개마다 탭 정지)가
   *  유일한 항목이었고 [OWNER 2026-10-19] 에 고쳐서 위 `ONE_WIDGET` 으로 갔다.
   *  목록은 **줄기만 한다** — 여기 적는 것은 수리를 미룬다는 선언이라, 적을 때는
   *  왜 미루는지를 같이 적는다. */
  const KNOWN_GAP: string[] = [];

  it('그림 축 전부가 셋 중 하나로 분류돼 있다', () => {
    expect(plots.sort()).toEqual([...ONE_WIDGET, ...POINTER_SHORTCUT, ...KNOWN_GAP].sort());
  });

  it.each(ONE_WIDGET)('%s — 그림이 **위젯 하나**다', (rel) => {
    const src = FILES.find((f) => f.rel === rel)!.src;
    expect(src).toContain('role="application"');
    expect(src).toContain('onKeyDown');
  });

  it.each(POINTER_SHORTCUT)('%s — 그림이 탭 정지가 **아니다**', (rel) => {
    const src = FILES.find((f) => f.rel === rel)!.src;
    expect(
      BARE_STOP.test(src),
      '포인터 지름길인데 탭 정지를 만들었어요 — 같은 항목이 두 번 걸립니다',
    ).toBe(false);
  });

  it('미룬 자리에 **아직 탭 정지가 남아 있다** — 고쳤으면 목록에서 지운다', () => {
    /* 고친 파일이 목록에 남아 있으면 그 줄은 거짓이 되고, 거짓인 목록은 다음
       사람에게 「여기는 아직 고장났다」고 말한다. 그래서 양쪽을 다 잰다. */
    for (const rel of KNOWN_GAP) {
      const src = FILES.find((f) => f.rel === rel)!.src;
      expect(BARE_STOP.test(src), `${rel} 는 고쳐졌어요 — KNOWN_GAP 에서 지우세요`).toBe(true);
    }
    /* 이 수는 **올라갈 수 없다**. 새 그림 축이 규칙 1 을 안 지키면 그 커밋이
       수리를 들고 와야지, 이 목록을 늘려서는 안 된다. */
    expect(KNOWN_GAP.length, '미룬 자리가 늘었어요 — 목록은 줄기만 합니다').toBeLessThanOrEqual(0);
  });
});
