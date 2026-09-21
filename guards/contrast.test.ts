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
