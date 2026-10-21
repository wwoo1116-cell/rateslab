import fs from 'node:fs';
import path from 'node:path';

import { defaultTheme } from '@coinbase/cds-web/themes/defaultTheme';
import { describe, expect, it } from 'vitest';

import { DIRECTION_SURFACES, REJECTED_FOR_DIRECTION } from '../src/theme/sauronTheme';

import { stripComments } from './_source';

/**
 * The two direction hues are frozen. This guard does not police the hues — it
 * measures them against every surface v2 actually paints, in both schemes, and
 * fails loudly if a CDS surface cannot hold one of them at 4.5:1.
 *
 * A failure here is a FINDING, not a licence to retune the hue (session prompt
 * V1.3). If this goes red, the answer is a different surface or a different
 * component, never a different red.
 */

const ROOT = path.resolve(import.meta.dirname, '..');
const FLOOR = 4.5;

// ── colour maths ────────────────────────────────────────────────────────────
type RGB = [number, number, number];

function parseColor(value: string): RGB {
  const hex = value.trim().match(/^#([0-9a-f]{6})$/i);
  if (hex) {
    const n = parseInt(hex[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const rgb = value.trim().match(/^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i);
  if (rgb) return [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])];
  throw new Error(`cannot parse colour: ${value}`);
}

function luminance([r, g, b]: RGB): number {
  const f = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(parseColor(a)), luminance(parseColor(b))].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// ── the direction pair, read from the token file (never re-typed here) ──────
function readPair(scheme: 'light' | 'dark'): { up: string; down: string } {
  const css = fs.readFileSync(path.join(ROOT, 'src/theme/direction.css'), 'utf8');
  const block =
    scheme === 'light'
      ? css.slice(css.indexOf(':root'), css.indexOf('[data-sr-scheme'))
      : css.slice(css.indexOf('[data-sr-scheme'));
  const up = block.match(/--sr-up:\s*(#[0-9a-f]{3,8})/i)?.[1];
  const down = block.match(/--sr-down:\s*(#[0-9a-f]{3,8})/i)?.[1];
  if (!up || !down) throw new Error(`no ${scheme} direction pair in direction.css`);
  return { up, down };
}

// ── the surfaces the app actually paints ────────────────────────────────────
function walk(dir: string, out: string[] = []): string[] {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === 'node_modules' || e.name === '.next') continue;
      walk(full, out);
    } else if (/\.tsx?$/.test(e.name)) out.push(full);
  }
  return out;
}

/** Every `background="…"` in v2's own components. Enumerated from the source, not
 * hand-listed — a screen that paints a surface nobody measured is the defect this
 * catches.
 *
 * **주석은 걷는다** [2026-09-21]. 이 리포의 주석은 근거를 적는 자리라 «이
 * 토큰을 왜 안 쓰는가» 같은 문장에 `background="transparent"` 가 그대로
 * 들어간다. 안 걷으면 가드가 «칠하지 않기로 한 것» 을 칠한 것으로 읽는다 —
 * `guards/guard-hygiene.test.ts` 가 있는 이유가 바로 이 계열의 실패이고, 이
 * 파일은 그 함수를 안 지나는 여섯 번째였다. */
function paintedInSource(): string[] {
  const found = new Set<string>();
  for (const file of walk(path.join(ROOT, 'src'))) {
    const body = stripComments(fs.readFileSync(file, 'utf8'));
    for (const m of body.matchAll(/background=(?:"([^"]+)"|\{'([^']+)'\})/g)) {
      found.add(m[1] ?? m[2]);
    }
  }
  return [...found];
}

describe('direction hues clear 4.5:1 on every painted surface', () => {
  const schemes = [
    { name: 'light' as const, palette: defaultTheme.lightColor as Record<string, string> },
    { name: 'dark' as const, palette: defaultTheme.darkColor as Record<string, string> },
  ];

  it('every surface the app paints is one this guard covers', () => {
    const painted = paintedInSource();
    const uncovered = painted.filter(
      (s) => !(DIRECTION_SURFACES as readonly string[]).includes(s),
    );
    expect(
      uncovered,
      `painted but unmeasured: ${uncovered.join(', ')} — add to DIRECTION_SURFACES ` +
        `(and prove it clears 4.5) or stop painting it`,
    ).toEqual([]);
  });

  /* The rejected surfaces stay measured [pass 2, C3]. Two things are asserted,
   * and they are different things:
   *   1. the surfaces STILL fail — if CDS lightens either value, this turns red
   *      and the constraint gets revisited on purpose rather than by accident;
   *   2. nothing in v2 paints them at all, so no signed number can land there
   *      by a route the first assertion would not notice. */
  for (const surface of REJECTED_FOR_DIRECTION) {
    it(`light · ${surface} is still too dark for the frozen pair`, () => {
      const bg = (defaultTheme.lightColor as Record<string, string>)[surface];
      const { up, down } = readPair('light');
      const cUp = contrast(up, bg);
      const cDown = contrast(down, bg);
      expect(cUp, `up on ${surface} = ${cUp.toFixed(2)}:1 — CDS changed it`).toBeLessThan(FLOOR);
      expect(cDown, `down on ${surface} = ${cDown.toFixed(2)}:1 — CDS changed it`).toBeLessThan(
        FLOOR,
      );
    });
  }

  it('no v2 component paints a rejected surface at all', () => {
    const painted = paintedInSource();
    const forbidden = painted.filter((s) =>
      (REJECTED_FOR_DIRECTION as readonly string[]).includes(s),
    );
    expect(
      forbidden,
      `v2 paints a surface the frozen hues cannot sit on: ${forbidden.join(', ')}`,
    ).toEqual([]);
  });

  for (const { name, palette } of schemes) {
    const pair = readPair(name);
    for (const surface of DIRECTION_SURFACES) {
      for (const [role, hue] of Object.entries(pair)) {
        it(`${name} · ${role} on ${surface}`, () => {
          const bg = palette[surface];
          expect(bg, `theme has no surface ${surface}`).toBeTruthy();
          const ratio = contrast(hue, bg);
          expect(
            Number(ratio.toFixed(2)),
            `${role} ${hue} on ${surface} ${bg} = ${ratio.toFixed(2)}:1`,
          ).toBeGreaterThanOrEqual(FLOOR);
        });
      }
    }
  }
});

/* ── 전경이 방향색 둘만이 아니다 [디자인 감사 2026-10-21] ────────────────────
 *
 * 이 가드는 2026-08 부터 **방향색 두 개**만 재 왔다. 그래서 2026-10-21 감사가
 * 다크에서 찾은 위반을 한 번도 못 봤다:
 *
 *     fgMuted #8a919e  on  bgSecondary #282b31  =  4.476 : 1    (문턱 4.5)
 *
 * 그 자리는 선택행 둘째 줄(「1년 평균 …」)과 바닥 스트립이고, 둘 다
 * `--sr-control` 을 칠한다. 라이트는 전수 통과였다.
 *
 * **구멍이 둘이었다.**
 *   ① 전경 — 방향색만 보고 `fgMuted` 는 안 봤다. 그런데 화면의 글자 대부분이
 *      잉크 아니면 뮤트다.
 *   ② 표면 — `paintedInSource()` 는 JSX `background="…"` 속성만 훑는다.
 *      `--sr-control` 은 **CSS 변수로** 칠해서 그 집계에 안 잡힌다. 그래서
 *      `bgSecondary` 가 「v2 가 안 칠하는 면」으로 분류돼 있었는데(위
 *      `REJECTED_FOR_DIRECTION` 검사) 다크에서는 실제로 칠하고 있었다.
 *
 * 그래서 여기서는 **표면 목록을 CDS 쪽이 아니라 `direction.css` 에서 읽는다** —
 * `--sr-page`/`--sr-card`/`--sr-control` 이 각 스킴에서 가리키는 CDS 이름을
 * 그대로 따라간다. 면을 새로 하나 쓰면 그 줄이 여기 자동으로 들어온다.
 *
 * 문턱은 본문 기준 4.5 다(WCAG 2.2 §1.4.3). 뮤트는 보조 문구지 「큰 글자」가
 * 아니므로 3:1 완화를 안 받는다 — 13px 이다. */
/* 면 토큰은 `:root` 가 아니라 `[data-sr-scheme]` 에 산다 — 그 까닭은
 * `direction.css` §「`:root` 가 아니라 `[data-sr-scheme]` 인 이유」에 실측으로
 * 적혀 있다(CDS 변수를 **참조**하는 값은 `:root` 에서 죽는다).
 *
 * 그래서 베이스(`[data-sr-scheme]`, 라이트 값)를 먼저 읽고, 다크는 그 위에
 * `[data-sr-scheme='dark']` 의 덮어쓰기를 얹는다 — 캐스케이드와 같은 순서다. */
/* ⚠ `[data-sr-scheme='dark'] {` 는 이 파일에 **여러 번** 나온다(방향색 쌍 ·
 * 면 세 단 · 그 밖). 처음 걸리는 것으로 자르면 면 블록 앞에서 잘린다 —
 * 첫 판에서 실제로 그렇게 비었다. 그래서 위치가 아니라 **내용**으로 고른다:
 * `--sr-page` 를 선언하는 블록이 면 블록이다. */
function cssBlocks(): { base: string; dark: string } {
  const css = fs.readFileSync(path.join(ROOT, 'src/theme/direction.css'), 'utf8');
  let base = '';
  let dark = '';
  for (const m of css.matchAll(/(\[data-sr-scheme[^{]*)\{([\s\S]*?)\n\}/g)) {
    const [, selector, body] = m;
    if (!body.includes('--sr-page:')) continue;
    if (/='dark'/.test(selector)) dark += body;
    else base += body;
  }
  if (!base) throw new Error('direction.css 에서 면 베이스 블록(--sr-page)을 못 찾았어요');
  if (!dark) throw new Error('direction.css 에서 면 다크 블록(--sr-page)을 못 찾았어요');
  return { base, dark };
}

function readSurfaceTokens(scheme: 'light' | 'dark'): Record<string, string> {
  const { base, dark } = cssBlocks();
  const out: Record<string, string> = {};
  const scan = (block: string) => {
    for (const m of block.matchAll(/--sr-(page|card|control):\s*var\(--color-([A-Za-z0-9]+)\)/g)) {
      out[`--sr-${m[1]}`] = m[2];
    }
  };
  scan(base);
  if (scheme === 'dark') scan(dark);
  return out;
}

/** 다크에서 `direction.css` 가 CDS `--color-fgMuted` 를 덮는다(문턱 수리).
 *  덮은 값이 있으면 그것을, 없으면 CDS 값을 잰다 — 화면에 실제로 서는 쪽. */
function readMuted(scheme: 'light' | 'dark', palette: Record<string, string>): string {
  const { base, dark } = cssBlocks();
  const pick = (block: string) => block.match(/--color-fgMuted:\s*(#[0-9a-f]{3,8})/i)?.[1];
  return (scheme === 'dark' ? (pick(dark) ?? pick(base)) : pick(base)) ?? palette.fgMuted;
}

describe('뮤트 글자도 v2 가 칠하는 모든 면에서 4.5:1 을 넘는다', () => {
  for (const { name, palette } of [
    { name: 'light' as const, palette: defaultTheme.lightColor as Record<string, string> },
    { name: 'dark' as const, palette: defaultTheme.darkColor as Record<string, string> },
  ]) {
    const surfaces = readSurfaceTokens(name);
    const muted = readMuted(name, palette);

    it(`${name} · 면 세 개를 전부 읽었다`, () => {
      expect(
        Object.keys(surfaces).sort(),
        'direction.css 의 --sr-page/--sr-card/--sr-control 중 못 읽은 것이 있어요',
      ).toEqual(['--sr-card', '--sr-control', '--sr-page']);
    });

    for (const [token, cdsName] of Object.entries(surfaces)) {
      it(`${name} · fgMuted on ${token} (= ${cdsName})`, () => {
        const bg = palette[cdsName];
        expect(bg, `theme has no surface ${cdsName}`).toBeTruthy();
        const ratio = contrast(muted, bg);
        expect(
          Number(ratio.toFixed(2)),
          `fgMuted ${muted} on ${token}=${cdsName} ${bg} = ${ratio.toFixed(2)}:1 — ` +
            `direction.css 의 문턱 규칙(「0.01 도 안 봐준다」)에 걸렸어요.`,
        ).toBeGreaterThanOrEqual(FLOOR);
      });
    }
  }
});
