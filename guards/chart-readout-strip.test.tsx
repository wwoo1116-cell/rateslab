/* 그림 **위**의 리드아웃 줄 [OWNER 2026-09-21].
 *
 * 트레이더 보고: 차트 위에 떠 있는 흰 카드가 그림을 가린다. 실측으로도 그렇다 —
 * 카드는 세로 약 220px 인데 오버뷰 열의 그림은 200px, 백테스트 아래 차트는
 * 140px 이라 «그림보다 큰 툴팁» 이었다.
 *
 * 고친 방향은 «자리를 더 잘 잡기» 가 아니라 «그림 밖으로 내보내기» 다. 그래서
 * 이 파일이 재는 것은 전부 그 한 문장의 따름정리다:
 *
 *   ① 그림 안에 hover 로 뜨는 것이 **없다**
 *   ② 커서가 어디인지는 **라이브러리의 축 라벨**이 말한다 — DOM 을 안 덧댄다
 *   ③ 줄은 **안 움직인다** — 쉴 때와 짚을 때 높이도 칸 자리도 같다
 *   ④ 변화는 단위와 부호를 **둘 다** 지고 나간다
 *   ⑤ 좁아지면 값만 내려놓고 **손잡이는 남는다**
 *
 * 카드(`ui/ReadoutCard.tsx`)는 은퇴하지 않았다 — 시뮬·rv·MR·Lab 의 열네 자리가
 * 아직 쓰고, 그쪽 계약은 `guards/readout-card-width.test.ts` 가 잰다.
 */

import fs from 'node:fs';
import path from 'node:path';

import { ThemeProvider } from '@coinbase/cds-web';
import { defaultTheme } from '@coinbase/cds-web/themes/defaultTheme';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ChartReadoutStrip, slotChars, type StripSlot } from '../src/ui/ChartReadoutStrip';

import { stripComments } from './_source';

const ROOT = path.resolve(import.meta.dirname, '..');
const read = (p: string) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const code = (p: string) => stripComments(read(p));

/** 줄로 옮긴 표면들. 새 표면이 옮겨 오면 여기 추가되어야 한다. */
const STRIP_SURFACES = ['src/ui/PreviewPane.tsx', 'src/backtest/LinkedCharts.tsx'];

describe('① 그림 안에 hover 로 뜨는 것이 없다', () => {
  it('두 표면 어디에도 `.sr-readout` 이 없다', () => {
    /* **컴포넌트 이름이 아니라 클래스로 잰다.** 백테스트의 카드는
       `<ReadoutCard>` 가 아니라 `<VStack className="sr-readout">` 이었다 —
       부품 이름으로 걸면 그 자리는 영원히 안 걸린다. */
    const offenders = STRIP_SURFACES.filter((f) => code(f).includes('sr-readout'));
    expect(offenders).toEqual([]);
  });

  it('커서 자리를 재던 배선도 없다', () => {
    /* 자리가 고정이면 잴 것이 없다. `placeReadout` 이 남아 있다는 것은 어딘가
       다시 떠 있는 것이 생겼다는 뜻이다. */
    for (const f of STRIP_SURFACES) {
      expect(code(f), f).not.toMatch(/placeReadout|onMouseMove=/);
    }
  });

  it('줄은 그림 상자 **밖**에 선다', () => {
    /* `.sr-plot` 은 `position: relative` 라, 줄이 그 안에 들어가면 다시 그림 위에
       겹칠 수 있는 자리가 된다. 소스에서 `<ChartReadoutStrip` 이 `className="sr-plot"`
       상자보다 **먼저** 나와야 한다(형제이자 위쪽). */
    for (const f of STRIP_SURFACES) {
      const src = code(f);
      const strip = src.indexOf('<ChartReadoutStrip');
      const plot = src.indexOf('className="sr-plot"');
      expect(strip, `${f}: 줄이 없다`).toBeGreaterThan(-1);
      expect(plot, `${f}: 그림 상자가 없다`).toBeGreaterThan(-1);
      expect(strip, `${f}: 줄이 그림보다 뒤에 있다`).toBeLessThan(plot);
    }
  });
});

describe('② 커서 자리는 라이브러리가 말한다', () => {
  const canon = code('src/chart/useLwChart.ts');

  it('날짜·가격 축 라벨이 **둘 다** 켜져 있다', () => {
    expect(canon).toMatch(/vertLine: \{[^}]*labelVisible: true/);
    expect(canon).toMatch(/horzLine: \{[^}]*labelVisible: true/);
  });

  it('가로선 자체는 **안 그린다** — 그림을 가로지르는 선도 덧댄 것이다', () => {
    expect(canon).toMatch(/horzLine: \{ visible: false/);
  });

  it('그 대가인 축 폭 바닥이 **한 곳**에서 난다', () => {
    /* 라이브러리 안에 판정이 둘이고 서로 다르다(번들 실측): 라벨을 그리는 쪽은
       `labelVisible` 만 보고, 축 폭을 잡는 쪽은 `horzLine.visible` 까지 본다.
       그래서 폭은 우리가 잡는다 — 그리고 형제 차트끼리 폭을 맞추는 바닥과
       **한 줄에서 합쳐야** 한다(같은 키에 두 번 쓰면 나중 것이 앞 것을 덮는다). */
    expect(canon).toMatch(/export const CROSSHAIR_LABEL_MIN_W = \d+;/);
    expect(code('src/chart/TimeChart.tsx')).toMatch(
      /minimumWidth: Math\.max\(scaleWidth \?\? 0, CROSSHAIR_LABEL_MIN_W\)/,
    );
  });

  it('날짜 글자는 축 눈금과 **같은 함수**를 지난다', () => {
    /* `tickMarkFormatter`(눈금)와 `localization.timeFormatter`(크로스헤어 라벨)는
       별개 손잡이다. 한쪽만 주면 눈금은 ISO 인데 크로스헤어는 로케일 글자가
       되고, 한 차트가 두 날짜 문법을 쓴다. */
    expect(canon).toMatch(/localization: \{ timeFormatter: isoTick \}/);
    expect(canon).toMatch(/tickMarkFormatter: isoTick/);
  });

  it('구슬은 **주선 하나**다 — 기본값이 여덟 개를 띄운다', () => {
    expect(code('src/chart/series.ts')).toMatch(/crosshairMarkerVisible: line\.beacon \?\? false/);
    const pane = code('src/ui/PreviewPane.tsx');
    expect([...pane.matchAll(/beacon: true/g)]).toHaveLength(1);
  });
});

/* ── 렌더로 재는 것들 ────────────────────────────────────────────────────── */

const wrap = (ui: React.ReactNode) => (
  <ThemeProvider theme={defaultTheme} activeColorScheme="light">
    {ui}
  </ThemeProvider>
);

const SLOTS: StripSlot[] = [
  { key: 'level', label: '레벨', value: '3.2450', color: 'var(--sr-up)', chars: 7 },
  { key: 'MA10', label: 'MA10', value: '3.2380', color: 'var(--sr-ma)', chars: 7, drop: 1 },
  { key: 'MA20', label: 'MA20', value: '3.2510', color: 'var(--sr-ma)', chars: 7, drop: 2 },
  { key: 'CD91', label: 'CD 91일', value: '2.9300', color: 'var(--sr-ref-cd)', chars: 7, drop: 3 },
  { key: 'BASE', label: '기준금리', value: '2.5000', color: 'var(--sr-ref-policy)', chars: 7, drop: 4 },
];

describe('③ 줄은 안 움직인다', () => {
  const widths = (root: HTMLElement) =>
    [...root.querySelectorAll('.sr-strip-slot')].map(
      (el) => (el as HTMLElement).style.getPropertyValue('--sr-strip-ch'),
    );

  it('쉴 때와 짚을 때 **칸 수와 칸 폭이 같다**', () => {
    /* 같은 DOM 에 글자만 바뀐다는 계약이다. 칸이 생겼다 없어지거나 폭이
       달라지면 옆 칸이 밀리고, 읽는 동안 숫자가 움직인다. */
    const idle = render(
      wrap(<ChartReadoutStrip date="2026-09-18" slots={SLOTS} change={{ label: '당일 변화', text: '+2.2bp', v: 2.2 }} />),
    );
    const scrubbed: StripSlot[] = SLOTS.map((s) => ({ ...s, value: '12.0100' }));
    const scrub = render(
      wrap(<ChartReadoutStrip date="2026-03-02" slots={scrubbed} change={{ label: '당일 변화', text: '−11.4bp', v: -11.4 }} />),
    );
    expect(widths(scrub.container as HTMLElement)).toEqual(widths(idle.container as HTMLElement));
    expect(scrub.container.querySelectorAll('.sr-strip-slot').length).toBe(
      idle.container.querySelectorAll('.sr-strip-slot').length,
    );
  });

  it('높이는 **상수**다 — 재는 화면이 그림 높이를 그걸로 정한다', () => {
    const css = read('src/theme/type.css');
    expect(code('src/ui/ChartReadoutStrip.tsx')).toMatch(/export const READOUT_STRIP_H = \d+;/);
    /* 넘치면 줄바꿈이 아니라 잘린다 — 줄바꿈은 높이를 바꾸고, 높이가 바뀌면
       그림이 흔들린다(이 줄이 존재하는 이유의 정반대). */
    const block = css.slice(css.indexOf('.sr-readout-strip {'), css.indexOf('.sr-strip-slot {'));
    expect(block).toMatch(/flex-wrap: nowrap/);
    expect(block).toMatch(/overflow: hidden/);
  });

  it('자리는 **서식이 잰다** — 손으로 센 수가 아니다', () => {
    /* `%` 는 네 자리 고정이라 길이는 정수부가 정한다. 구간의 고·저를 같은
       서식에 통과시키면 그 최대치가 나온다. */
    const fmt = (v: number) => v.toFixed(4);
    expect(slotChars(fmt, 3.99, 2.51)).toBe(6); // "3.9900"
    expect(slotChars(fmt, 12.01, 2.51)).toBe(7); // "12.0100"
    expect(slotChars(fmt, null, undefined)).toBe(1);
  });
});

describe('④ 변화는 단위와 부호를 둘 다 진다', () => {
  it('`bp` 와 방향 글리프가 같이 나간다', () => {
    /* 종전 카드는 `+2.2` 만 찍었다 — 단위를 붙이는 일이 `unitSuffix` 라는
       **별개 호출**이었고 이 자리가 그걸 안 불렀다. 이제 서식이 단위를 진다. */
    const { container } = render(
      wrap(<ChartReadoutStrip date="2026-09-18" slots={[]} change={{ label: '당일 변화', text: '+2.2bp', v: 2.2 }} />),
    );
    const txt = container.querySelector('.sr-strip-change')?.textContent ?? '';
    expect(txt).toContain('bp');
    expect(txt).toMatch(/[↗↘]/);
  });

  it('내려가면 내려가는 색이다', () => {
    const { container } = render(
      wrap(<ChartReadoutStrip date="2026-09-18" slots={[]} change={{ label: '당일 변화', text: '−11.4bp', v: -11.4 }} />),
    );
    expect(container.querySelector('.sr-strip-change .sr-down')).toBeTruthy();
  });

  it('0 에는 화살표가 없다 — 방향이 없는 것에 방향을 그리지 않는다', () => {
    const { container } = render(
      wrap(<ChartReadoutStrip date="2026-09-18" slots={[]} change={{ label: '당일 변화', text: '+0.0bp', v: 0 }} />),
    );
    expect(container.querySelector('.sr-strip-change')?.textContent ?? '').not.toMatch(/[↗↘]/);
  });

  it('**변화의 단위는 레벨의 단위가 아니다** — 한 함수가 그 규약을 진다', () => {
    /* `%` 레벨의 변화는 bp 다(`derive.py::series_history`, `table/rows.ts:85`).
       호출부가 그걸 기억해야 했을 때 두 자리가 각자 틀렸다: 카드는 단위를
       안 붙였고 히어로는 `%` 를 붙였다. */
    const fmt = code('src/lib/format.ts');
    expect(fmt).toMatch(/export function deltaUnitSuffix/);
    expect(fmt).toMatch(/return unit === "%" \|\| unit === "bp" \? "bp" : ""/);
    const pane = code('src/ui/PreviewPane.tsx');
    expect(pane).toMatch(/fmtDeltaUnit\(toDeltaUnit\(view\.net, row\.unit\), row\.unit\)/);
    /* 히어로가 레벨의 접미사를 변화에 붙이던 자리 — 되살아나면 안 된다. */
    expect(pane).not.toMatch(/fmtDelta\(view\.net, row\.unit\)\}\s*\n?\s*\{u\}/);
  });
});

describe('⑤ 좁아지면 값만 내려놓는다', () => {
  const css = read('src/theme/type.css');

  it('사다리는 **꼬리부터**다 — 기준금리 → CD91 → MA20 → MA10', () => {
    /* 순서를 재는 방법: 각 `data-drop` 이 걸리는 container 폭이 단조 감소해야
       한다. 넓은 창에서 먼저 사라지는 것이 꼬리다. */
    const at = (n: number) => {
      const marker = `.sr-strip-slot[data-drop='${n}'] .sr-strip-v`;
      const i = css.indexOf(marker);
      expect(i, `drop=${n} 규칙이 없다`).toBeGreaterThan(-1);
      const head = css.lastIndexOf('@container', i);
      return Number(/max-width:\s*(\d+)px/.exec(css.slice(head, i))?.[1]);
    };
    const [d4, d3, d2, d1] = [at(4), at(3), at(2), at(1)];
    expect(d4).toBeGreaterThan(d3);
    expect(d3).toBeGreaterThan(d2);
    expect(d2).toBeGreaterThan(d1);
  });

  it('날짜·레벨·당일 변화는 **어느 폭에서도** 남는다 — 분기점이 아니라 구조로', () => {
    /* **실측에서 고친 자리다** [2026-09-21 브라우저]: MA 를 다섯 다 켜면 칸이
       열이 되고, 그때 `당일 변화` 가 오른쪽 끝으로 밀려 잘렸다. 켤 수 있는
       계열 수가 변수라 분기점을 아무리 촘촘히 잡아도 어떤 조합에서는 넘친다.

       그래서 «항상 보인다» 를 분기점이 아니라 구조로 만든다: 줄어드는 상자는
       `.sr-strip-series` 하나뿐이고, 날짜와 당일 변화는 그 **밖**에 있다. */
    const { container } = render(
      wrap(<ChartReadoutStrip date="2026-09-18" slots={SLOTS} change={{ label: '당일 변화', text: '+2.2bp', v: 2.2 }} />),
    );
    const series = container.querySelector('.sr-strip-series');
    expect(series, '줄어드는 상자가 있다').toBeTruthy();
    expect(series?.querySelector('.sr-strip-change'), '당일 변화는 그 밖이다').toBeNull();
    expect(container.querySelector('.sr-strip-change'), '당일 변화는 있다').toBeTruthy();
    /* 계열 칸은 **전부** 그 안이다 — 하나라도 밖에 있으면 그 칸이 줄을 넘친다. */
    expect(series?.querySelectorAll('.sr-strip-slot').length).toBe(SLOTS.length);

    const css = read('src/theme/type.css');
    const block = css.slice(css.indexOf('.sr-strip-series {'), css.indexOf('.sr-strip-slot {'));
    expect(block).toMatch(/min-width: 0/);
    expect(block).toMatch(/container-type: inline-size/);
    /* 레벨에는 `drop` 이 없다 — 있으면 좁은 창에서 줄이 아무 말도 안 하게 된다. */
    const pane = code('src/ui/PreviewPane.tsx');
    const from = pane.indexOf("key: 'level'");
    expect(pane.slice(from, from + 200)).not.toMatch(/drop:/);
  });

  it('사다리는 **켤 수 있는 계열 수만큼** 깊다', () => {
    /* MA 다섯 + 기준선 둘 = 떨굴 수 있는 칸 일곱. 네 단이던 시절 실측에서
       모자랐다. 서버 목록이 다섯이므로 최소 여섯 단이어야 한다. */
    const derive = read('backend/app/derive.py');
    const windows = /MA_WINDOWS: tuple\[int, \.\.\.\] = \(([^)]*)\)/.exec(derive)?.[1] ?? '';
    const n = windows.split(',').filter((x) => x.trim()).length;
    const css = read('src/theme/type.css');
    const levels = new Set(
      [...css.matchAll(/\.sr-strip-slot\[data-drop='(\d)'\]/g)].map((m) => Number(m[1])),
    );
    expect(levels.size, `MA ${n}개 + 기준선 둘을 덮어야 한다`).toBeGreaterThanOrEqual(n + 1);
  });

  it('**칸은 안 떨군다** — 떨구면 그 계열을 켤 길이 없어진다', () => {
    /* [OWNER 2026-09-21] 이 줄은 범례이기도 하다. 좁은 창에서 칸이 통째로
       사라지면 손잡이가 같이 사라지고, 그러면 Setting 까지 가야 한다. */
    expect(css).toMatch(/\.sr-strip-slot\[data-drop='\d'\] \.sr-strip-v \{\s*\n\s*display: none/);
    expect(css).not.toMatch(/\.sr-strip-slot\[data-drop='\d'\] \{\s*\n\s*display: none/);
  });

  it('끈 계열도 **누를 수 있다** — 이름과 견본이 손잡이다', () => {
    const off: StripSlot[] = [
      { key: 'CD91', label: 'CD 91일', value: '', color: 'var(--sr-ref-cd)', toggle: { on: false, onToggle: () => {} } },
    ];
    const { container } = render(wrap(<ChartReadoutStrip date="2026-09-18" slots={off} />));
    const btn = container.querySelector('button.sr-strip-slot');
    expect(btn).toBeTruthy();
    expect(btn?.getAttribute('aria-label') ?? '').toContain('켜기');
    /* 끈 것은 흐려져 «있지만 지금은 안 그린다» 가 읽힌다. */
    const dash = container.querySelector('.sr-casedash') as HTMLElement | null;
    expect(dash?.style.opacity).toBe('0.3');
  });
});
