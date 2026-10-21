import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments } from './_source';

/**
 * ── 눌리는 것은 24px 이상 — **앱 전체** (WCAG 2.2 §2.5.8) ────────────────────
 *
 * `CLAUDE.md` §키보드와 접근성 6 이 이 규칙을 2026-08-27 에 박았다. 가드는
 * `terminal-keyboard.test.ts` 하나였고, 그것은 **파일 둘의 상수 둘**을 지목한다
 * (`GraphApp` 의 `HIT_R = 12`, `TimelineApp` 의 `width={24}`). 규칙은 앱 전체인데
 * 가드는 두 자리만 봤다.
 *
 * 2026-10-21 디자인 감사가 그 틈에서 둘을 찾았다:
 *
 *   · Main 한 면의 상호작용 요소 62개 중 **26개가 24px 미만**. 그중 22개가
 *     `.sr-strip-slot`(차트 범례 — MA5·MA10·…·기준금리 × 카드 3장)이고
 *     하나가 `.sr-strip-collapse`(▾, 20×20).
 *   · `.sr-term-chip` 이 20px — **규칙이 태어난 터미널 레인 안에서** 그랬고,
 *     그 레인의 가드가 못 봤다.
 *
 * 그래서 이 파일이 생겼다. 「범위가 좁은 가드는 고친 자리만 지킨다」(2026-10-19
 * 디자인 점검)의 세 번째 되풀이를 끝내는 것이 목적이다.
 *
 * ── 무엇을 재나 ──────────────────────────────────────────────────────────────
 *
 * 테마 CSS 에서 **누를 수 있는 선택자**가 명시적으로 선언한 `height`/`width` 를
 * 잰다. 그 둘이 24 미만이면 실패하고, 같은 선택자에 **판정 확장**
 * (`::after`/`::before` 로 24px 이상을 덧댄 것)이 있으면 통과시킨다 — 지침의
 * 표준 해법이 「그림을 키우지 말고 판정만 넓힌다」이기 때문이다.
 *
 * ── 한계를 적어 둔다 ────────────────────────────────────────────────────────
 *
 * 이것은 **정적 검사**라 CSS 가 명시적으로 적은 치수만 본다. 내용으로 높이가
 * 정해지는 컨트롤(패딩+줄높이)이나 JSX 쪽 `height={…}` 는 안 잡는다. 그 둘은
 * 브라우저 실측의 몫이고, 이 가드는 「한 번 고친 자리가 조용히 되돌아가는 것」을
 * 막는 래칫이다. 잡는 범위가 전부가 아니라는 사실을 숨기지 않으려고 여기 적는다.
 */

const ROOT = path.resolve(import.meta.dirname, '..');
const FLOOR = 24;

/** 누를 수 있는 것의 이름. 이 리포의 클래스 작명을 따른다 — 캐논(`CLAUDE.md`
 *  §화면 문법)에 있는 이름들이고, 새 컨트롤을 만들면 여기 추가한다. */
const PRESSABLE = /(btn|chip|pill|slot|collapse|handle|tab(?![a-z])|toggle|hit)/i;

/** 눌리지 않는데 이름만 걸리는 것. 하나씩 **까닭을 적고** 뺀다 —
 *  허용 목록은 비면 비는 대로가 낫고, 차면 까닭이 보여야 한다. */
const NOT_PRESSABLE: { selector: string; why: string }[] = [
  { selector: '.sr-irf-swatch', why: 'Box 다 — 범례 색 견본이고 onClick 이 없다 (BasisIrf.tsx)' },
];

/** 눌리는데 **24px 미만이 맞는** 것 — §2.5.8 의 「간격 예외」다.
 *
 *  기준이 24×24 하나뿐인 것이 아니다: 작은 과녁이라도 그 경계상자를 중심으로
 *  **지름 24px 원을 그렸을 때 다른 과녁과 안 겹치면** 통과한다. 여기 적는 것은
 *  그 예외를 쓴 자리이고, 쓸 때마다 **어느 과녁과 안 겹치는지**를 적는다 —
 *  「작아도 된다」가 아니라 「이 배치에서 작아도 된다」이기 때문이다. */
const SPACING_EXCEPTION: { selector: string; why: string }[] = [
  {
    selector: '.sr-strip-handle',
    why:
      '접힌 바닥 띠 전체가 과녁이다(실측 1920×12). 띠가 접혀 있는 동안 그 줄에 ' +
      '다른 과녁이 없고(열린 띠의 ▾·앵커는 같이 사라진다) 위는 그림, 아래는 ' +
      '뷰포트 끝이라 24px 원이 아무것과도 안 겹친다. 높이를 24 로 키우면 접는 ' +
      '동작이 되찾아 주려던 공간을 절반 도로 먹는다.',
  },
];

type Rule = { file: string; selector: string; body: string };

function rules(): Rule[] {
  const out: Rule[] = [];
  const dir = path.join(ROOT, 'src/theme');
  for (const name of fs.readdirSync(dir)) {
    if (!name.endsWith('.css')) continue;
    const css = stripComments(fs.readFileSync(path.join(dir, name), 'utf8'));
    for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      out.push({ file: name, selector: m[1].trim().replace(/\s+/g, ' '), body: m[2] });
    }
  }
  return out;
}

function px(body: string, prop: 'height' | 'width'): number | null {
  const m = body.match(new RegExp(`(?:^|[\\s;])${prop}:\\s*(\\d+)px`));
  return m ? Number(m[1]) : null;
}

/** `min-height` 로 세운 상자. 내용 높이가 모자라도 이 값이 바닥을 깐다. */
function minPx(body: string): number | null {
  const m = body.match(/(?:^|[\s;])min-height:\s*(\d+)px/);
  return m ? Number(m[1]) : null;
}

/** 이 선택자에 24px 이상의 판정이 덧대어져 있나 (`::after` / `::before`). */
function hasHitExtension(all: Rule[], selector: string): boolean {
  const base = selector.replace(/::(after|before)$/, '');
  return all.some((r) => {
    if (!/::(after|before)/.test(r.selector)) return false;
    if (!r.selector.includes(base.split(' ').pop() ?? base)) return false;
    const h = px(r.body, 'height');
    return h !== null && h >= FLOOR;
  });
}

describe('눌리는 것의 판정은 24px 이상이다 — 앱 전체 (WCAG 2.2 §2.5.8)', () => {
  const all = rules();
  const excused = new Set([
    ...NOT_PRESSABLE.map((e) => e.selector),
    ...SPACING_EXCEPTION.map((e) => e.selector),
  ]);

  const suspects = all.filter((r) => {
    if (/::(after|before)/.test(r.selector)) return false;
    if (!PRESSABLE.test(r.selector)) return false;
    if (excused.has(r.selector)) return false;
    const h = px(r.body, 'height');
    const w = px(r.body, 'width');
    return (h !== null && h < FLOOR) || (w !== null && w < FLOOR);
  });

  it('테마 CSS 가 선언한 누름 치수 중 24px 미만이 없다', () => {
    const bad = suspects
      .filter((r) => !hasHitExtension(all, r.selector))
      .map((r) => {
        const h = px(r.body, 'height');
        const w = px(r.body, 'width');
        return `${r.file} ${r.selector} (h=${h ?? '-'} w=${w ?? '-'})`;
      });
    expect(
      bad,
      `24px 미만으로 선언된 누름 요소가 있어요.\n` +
        `고치는 법 둘 — 상자를 키우거나, 지침의 표준 해법대로 ::after 로 판정만 넓히거나.\n` +
        `눌리지 않는 것이면 NOT_PRESSABLE 에 **까닭과 함께** 적어 주세요.\n` +
        bad.map((b) => `  · ${b}`).join('\n'),
    ).toEqual([]);
  });

  it('감사가 고친 네 자리가 되돌아가지 않았다', () => {
    /* 브라우저 실측으로 닫은 자리들이다(`elementFromPoint` 로 판정을 짚었다).
       정적 검사라 선언만 보지만, 되돌아가는 것은 선언이다. */
    const find = (sel: string) => all.find((r) => r.selector === sel);

    const series = find('.sr-strip-series');
    expect(series, '.sr-strip-series 규칙이 사라졌어요').toBeTruthy();
    expect(px(series!.body, 'height'), '차트 범례 줄').toBeGreaterThanOrEqual(FLOOR);

    const slot = find('.sr-readout-strip .sr-strip-slot');
    expect(slot, '.sr-strip-slot 의 min-height 규칙이 사라졌어요').toBeTruthy();
    expect(minPx(slot!.body), '차트 범례 칸').toBeGreaterThanOrEqual(FLOOR);

    const collapse = find('.sr-strip-collapse');
    expect(collapse, '.sr-strip-collapse 규칙이 사라졌어요').toBeTruthy();
    expect(px(collapse!.body, 'height'), '▾ 높이').toBeGreaterThanOrEqual(FLOOR);
    expect(px(collapse!.body, 'width'), '▾ 폭').toBeGreaterThanOrEqual(FLOOR);

    const anchor = find('.sr-strip-anchor');
    expect(anchor, '.sr-strip-anchor 규칙이 사라졌어요').toBeTruthy();
    expect(minPx(anchor!.body), '바닥 스트립 칸').toBeGreaterThanOrEqual(FLOOR);

    const chip = find('.sr-term-chip');
    expect(chip, '.sr-term-chip 규칙이 사라졌어요').toBeTruthy();
    expect(px(chip!.body, 'height'), '터미널 필터 칩').toBeGreaterThanOrEqual(FLOOR);
  });

  it('제외 목록의 모든 항목에 까닭이 적혀 있다', () => {
    const thin = [...NOT_PRESSABLE, ...SPACING_EXCEPTION]
      .filter((e) => e.why.trim().length < 10)
      .map((e) => e.selector);
    expect(thin, '까닭 없는 제외는 제외가 아니라 구멍이에요').toEqual([]);
  });

  it('간격 예외를 쓴 자리는 실제로 CSS 에 있다 — 죽은 예외를 안 남긴다', () => {
    const missing = SPACING_EXCEPTION.filter((e) => !all.some((r) => r.selector === e.selector));
    expect(missing.map((e) => e.selector), '없는 선택자의 예외가 남아 있어요').toEqual([]);
  });
});
