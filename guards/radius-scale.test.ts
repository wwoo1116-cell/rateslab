import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments } from './_source';

/**
 * 반경도 **한 계단** 위에 선다.
 *
 * ── 왜 이 가드가 뒤늦게 생겼나 (2026-09-15 디자인 점검) ──────────────────────
 * CLAUDE.md 규칙 4 는 이 앱의 규칙 중 **유일하게 숫자를 적어 둔 것**이다 —
 * `100`=4 · `200`=8 · `300`=12 · `400`=16 · `500`=24, 「같은 수를 px 로 다시
 * 적지 않는다」. 그런데 `spacing-scale` 가드의 정규식은
 * `padding|margin|gap|row-gap|column-gap` 만 잰다. 반경은 **아무도 안 보고
 * 있었고**, `type.css` 에 계단 값 그대로의 px 리터럴이 16건 남아 있었다.
 *
 * 값이 같으니 시각은 같다. 다른 것은 **출처**다. `sauronTheme` 이 언젠가
 * `borderRadius` 를 덮으면 토큰을 쓴 자리만 따라오고 px 리터럴은 남는다 —
 * 간격에서 이미 겪은 그 어긋남(`space['1']` 8→6)이 반경에서 반복되는 자리다.
 *
 * ── 예외는 «근거가 적힌 것» 하나뿐 ──────────────────────────────────────────
 * `terminal.css` 의 `4px` 는 CDS radius-100 과 값이 **우연히** 같다. 출처는
 * Blueprint 실측(`--bp-surface-border-radius`)이고 파일 머리 5–12행이 그것을
 * 적고 있다. 터미널은 별도 시각 레지스터라 CDS 토큰으로 끌어오면 그 화면이
 * CDS 테마를 따라 움직이게 된다 — 그건 이 가드가 정할 일이 아니다.
 * **근거 주석이 있는 파일만** 면제하고, 면제 목록은 여기 한 곳에 적는다.
 */

const ROOT = path.resolve(import.meta.dirname, '..');
const SRC = path.join(ROOT, 'src');

/** CDS 반경 계단(px → 토큰 번호). `defaultTheme.borderRadius` 그대로. */
const SCALE: Record<number, string> = { 4: '100', 8: '200', 12: '300', 16: '400', 24: '500' };

/**
 * 계단 값을 px 로 적어도 되는 파일과 그 이유.
 * 여기 없는 파일이 계단 값을 px 로 적으면 실패한다 — 새 예외는 **이유와 함께**
 * 이 표에 적어야 통과한다.
 */
const EXEMPT: Record<string, string> = {
  'src/theme/terminal.css':
    'Blueprint 실측(--bp-surface-border-radius: 4px)이 출처다. CDS radius-100 과 값만 우연히 같고, ' +
    '터미널을 CDS 테마에 묶는 것은 별도 결정이다 — 파일 머리 5~12행이 근거를 적고 있다.',
};

function walk(dir: string, exts: string[]): string[] {
  const out: string[] = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p, exts));
    else if (exts.some((x) => e.name.endsWith(x))) out.push(p);
  }
  return out;
}

/** CSS 선언. `border-radius` 와 논리 속성 둘 다. */
const RADIUS_DECL = /(?:^|[\s;{])(border(?:-\w+)?-radius|border-radius):\s*([^;}]+)/g;
/** JSX 스타일 prop. `borderRadius={N}` 은 CDS 토큰 번호라 계단과 다른 축이다. */
const RADIUS_STYLE = /borderRadius:\s*(\d+(?:\.\d+)?)\b/g;

const cssFiles = walk(SRC, ['.css']);
const tsxFiles = walk(SRC, ['.tsx', '.ts']);

function rel(f: string) {
  return path.relative(ROOT, f).replace(/\\/g, '/');
}

/** 계단 값을 px 로 적은 자리. `var()`·`calc()`·% 는 이 가드의 일이 아니다. */
function offToken(): string[] {
  const bad: string[] = [];
  for (const f of cssFiles) {
    const name = rel(f);
    if (name in EXEMPT) continue;
    const body = stripComments(fs.readFileSync(f, 'utf8'));
    for (const m of body.matchAll(RADIUS_DECL)) {
      const decl = m[2];
      if (/var\(|calc\(|%/.test(decl)) continue;
      for (const v of [...decl.matchAll(/(\d+(?:\.\d+)?)px/g)].map((x) => Number(x[1]))) {
        if (v in SCALE) bad.push(`${name}: ${m[1]}: ${v}px → var(--borderRadius-${SCALE[v]})`);
      }
    }
  }
  for (const f of tsxFiles) {
    const name = rel(f);
    if (name in EXEMPT) continue;
    const body = stripComments(fs.readFileSync(f, 'utf8'));
    for (const m of body.matchAll(RADIUS_STYLE)) {
      const v = Number(m[1]);
      if (v in SCALE) bad.push(`${name}: style borderRadius: ${v} → CDS prop borderRadius="${SCALE[v]}"`);
    }
  }
  return bad;
}

describe('반경은 한 계단 위에 선다', () => {
  it('검사할 소스를 실제로 찾았다', () => {
    // 스코프가 비면 아래가 공짜로 통과한다.
    expect(cssFiles.length).toBeGreaterThanOrEqual(3);
    expect(tsxFiles.length).toBeGreaterThan(50);
  });

  it('계단 값(4·8·12·16·24)을 px 로 다시 적지 않는다', () => {
    expect(offToken()).toEqual([]);
  });

  it('면제는 근거가 적힌 파일만이고, 그 파일은 실재한다', () => {
    for (const [f, why] of Object.entries(EXEMPT)) {
      expect(fs.existsSync(path.join(ROOT, f)), `${f} 가 없어요 — 면제 목록이 낡았어요`).toBe(true);
      // 이유 없는 면제는 면제가 아니라 구멍이다.
      expect(why.length).toBeGreaterThan(40);
    }
  });

  it('계단 밖 값은 건드리지 않는다 — 이 가드의 일이 아니다', () => {
    // 999(스타디움) · 1 · 2 · 3 · 6 · 10 px 은 토큰이 없다. 잡으면 안 된다.
    const body = '.a { border-radius: 999px; } .b { border-radius: 6px; }';
    const found = [...body.matchAll(RADIUS_DECL)].flatMap((m) =>
      [...m[2].matchAll(/(\d+)px/g)].map((x) => Number(x[1])).filter((v) => v in SCALE),
    );
    expect(found).toEqual([]);
  });
});
