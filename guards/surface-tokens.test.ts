import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments } from './_source';

/**
 * The three surface tokens must be declared WHERE CDS's tokens are in scope.
 *
 * ── The failure this exists for (measured 2026-08-13) ───────────────────────
 * `--sr-page` / `--sr-card` / `--sr-control` are defined in terms of CDS tokens
 * (`var(--color-bg)` and friends). They were first declared on `:root`, and all
 * three silently became the guaranteed-invalid value, because **CDS emits
 * `--color-*` as inline styles on its own ThemeProvider wrapper, not on
 * `:root`** — and a custom property's value is substituted AT THE ELEMENT WHERE
 * IT IS DECLARED.
 *
 * Nothing looked broken. `background: var(--sr-card)` with an invalid value
 * falls back to transparent, and the cards still had their border and radius, so
 * the page read as "white cards on a white page" rather than as a bug. It was
 * only caught by reading `backgroundColor` back out of the DOM.
 *
 * This repo has now hit the same class of defect three times — the font family
 * (`type.css`: a `body { --fontFamily-body: … }` override that computed to CDS's
 * own value), the theme font stack, and this. The shape is always the same: a
 * variable defined above the scope that owns the value it references.
 *
 * Source-read rather than rendered, for the same reason as `ch-context`: jsdom
 * loads no CDS stylesheet, so a rendered assertion would measure jsdom.
 */

const ROOT = path.resolve(import.meta.dirname, '..');
/* **주석은 걷는다** [디자인 감사 2026-10-21 — 다섯 번째 재발].
 *
 * 이 가드는 줄 단위로 「`--sr-*` 가 보이면 `var(--color-` 가 있어야 한다」를
 * 잰다. 그런데 이 리포의 주석은 근거를 적는 자리라 **주석 문장 안에
 * `--sr-control` 같은 이름이 그대로 들어간다** — 2026-10-21 에 대비 문턱 수리의
 * 근거 주석(「… `--sr-control`(= bgSecondary, #282b31)이고 …」)이 선언으로
 * 읽혀서 이 가드가 빨개졌다. 코드는 멀쩡했고 가드가 산문을 읽은 것이다.
 *
 * `guards/guard-hygiene.test.ts` 가 바로 이 계열의 실패를 위해 있고, 그 파일이
 * 「소스를 훑는 가드 여섯이 `stripComments` 를 지난다」고 적는다. 이 가드는 그
 * 여섯에 안 들어 있었다 — `contrast.test.ts` 가 2026-09-21 에 같은 이유로
 * 합류한 뒤 **일곱 번째**로 합류한다. */
const CSS = stripComments(fs.readFileSync(path.join(ROOT, 'src/theme/direction.css'), 'utf8'));

/* --sr-scrim 은 4번째 재발(2026-08-18)로 합류했다 — :root 로 올라가 조용히
 * 무효가 됐고, 커브 표면의 실색 리졸버가 잡아냈다. */
const SURFACES = ['--sr-page', '--sr-card', '--sr-control', '--sr-scrim'] as const;

/** The body of the LAST rule whose selector matches, or ''. Takes the selector
 * RAW — escaping happens here, and passing a pre-escaped string double-escapes
 * it into something that matches nothing. */
function blockFor(selector: string): string {
  const re = new RegExp(`${selector.replace(/[[\]'.]/g, '\\$&')}\\s*\\{([^}]*)\\}`, 'g');
  let last = '';
  for (const m of CSS.matchAll(re)) last = m[1];
  return last;
}

const LIGHT = blockFor('[data-sr-scheme]');
const DARK = blockFor("[data-sr-scheme='dark']");

describe('surface tokens are declared where CDS tokens exist', () => {
  it('all three are declared on [data-sr-scheme]', () => {
    const block = LIGHT;
    for (const v of SURFACES) {
      expect(block, `${v} must be declared on [data-sr-scheme]`).toContain(v);
    }
  });

  it('none of them is declared on :root', () => {
    // `:root` sits ABOVE CDS's wrapper, so `var(--color-*)` resolves to nothing
    // there and the whole declaration dies without a warning.
    const rootBlock = CSS.slice(CSS.indexOf(':root'), CSS.indexOf('[data-sr-scheme'));
    for (const v of SURFACES) {
      expect(rootBlock, `${v} must NOT be declared on :root`).not.toContain(v);
    }
  });

  it('the dark scheme redefines all three', () => {
    // Light and dark do not merely differ in tone here, they use DIFFERENT CDS
    // tokens: light elevation is white-on-white (shadow only) while dark
    // elevation actually lightens. A dark block that forgot one would inherit a
    // light-scheme surface and invert the hierarchy on that one element.
    const dark = DARK;
    for (const v of SURFACES) {
      expect(dark, `${v} must be redefined for dark`).toContain(v);
    }
  });

  it('every surface resolves through a CDS token, never a literal', () => {
    const block = LIGHT + DARK;
    for (const line of block.split('\n')) {
      if (!SURFACES.some((v) => line.includes(v))) continue;
      /* 스크림의 다크 값은 **의도된 리터럴**이다 — CDS bgOverlay(gray0 @ 0.33)는
       * 어두운 바탕에서 아무것도 안 한다(direction.css 「덮개」 주석). 스크림이
       * 이 목록에 합류한 이유는 리터럴 금지가 아니라 :root 배치 함정(4번째
       * 재발, 2026-08-18)이고, 배치·다크 재정의 검사는 위에서 스크림을 그대로
       * 잰다. */
      if (line.includes('--sr-scrim') && !line.includes('var(')) continue;
      expect(line, `surface must use var(--color-*): ${line.trim()}`).toMatch(/var\(--color-/);
    }
  });

  it('signed numbers never sit on a surface measured to fail', () => {
    // `bgAlternate` holds the direction hues at only 4.08 / 3.98 in light
    // (measured), so it is the PAGE and controls, never the card. If someone
    // makes the card `bgAlternate`, the table's numbers drop below the floor.
    const dark = DARK;
    const light = LIGHT;
    expect(light).toMatch(/--sr-card:\s*var\(--color-bg\)/);
    expect(dark).toMatch(/--sr-card:\s*var\(--color-bgElevation1\)/);
  });
});
