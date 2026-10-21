import { defaultTheme } from '@coinbase/cds-web/themes/defaultTheme';

import type { ThemeConfig } from '@coinbase/cds-web/core/theme';

/**
 * One face for Latin and Hangul both.
 *
 * Mixed Latin/Hangul inside one cell is this product's normal case ("IRS 3Y",
 * "회사 AA− 3Y"). Two faces mean two baselines, two sets of metrics, and a column
 * width computed from format maxima that holds for only half the strings in the
 * column.
 *
 * Self-hosted from `public/fonts/`, with `local()` deliberately absent — see
 * `theme/type.css` for the measurement that forced it (this desk has no
 * Pretendard installed, so the former `local()`-only source had been silently
 * falling back to Malgun).
 */
/* `Pretendard SR` FIRST, and it is the only entry here that resolves to
 * anything on this desk.
 *
 * ── MEASURED BUG, 2026-08-13 ────────────────────────────────────────────────
 * This stack used to begin `'Pretendard Variable', Pretendard, …` and the face
 * never loaded, so the product rendered in Malgun — the exact defect the
 * self-hosting change was made to fix. The `@font-face` in `theme/type.css`
 * declares the family as **`Pretendard SR`** (a name chosen so a differently
 * versioned locally-installed Pretendard cannot be picked up by accident), and
 * that name appeared only in that file's `--sr-font-sans`. CDS components read
 * `--fontFamily-*`, which comes from THIS object, so the CSS variable was never
 * consulted and the two stacks silently disagreed.
 *
 * Measured in the running app: the computed stack rendered at a 125.75px
 * advance for a fixed probe string — Malgun's — against 124.95 for
 * `Pretendard SR` and a 120.00 no-such-face baseline. `Pretendard Variable` is
 * not installed here and nothing declares it, so it was dead weight at the head
 * of the stack.
 *
 * The consequence was not only the face. Malgun ships three weights, so the
 * 500/600 pair below collapsed to Regular/Bold and the type had no middle
 * register — which is the same silent failure, one layer down.
 *
 * The remaining entries are the ordered fallback for the ~3s `font-display:
 * block` timeout only; `Pretendard Variable`/`Pretendard` stay so a machine
 * that DOES have the face installed still lands on the right family before
 * dropping to a system Hangul face. */
const SR_FONT_STACK =
  "'Pretendard SR', 'Pretendard Variable', Pretendard, -apple-system, 'Apple SD Gothic Neo', 'Malgun Gothic', system-ui, sans-serif";

/**
 * v2's theme, derived from CDS `defaultTheme`.
 *
 * It is deliberately a thin derivation right now. This spike has ONE independent
 * variable — the component layer — so the theme changes nothing about colour,
 * type or geometry yet. Density is *measured* in V2.7 and decided by the owner
 * later; surface tone, radius and hairline policy belong to the aesthetic
 * session (§2 of the session prompt), not here.
 *
 * The two direction hues are NOT in this object. They are in `direction.css`,
 * because CDS has no slot for "the two hues this product signs numbers with"
 * that does not already mean something else to CDS (`fgPositive`/`fgNegative`
 * carry the green-good/red-bad reading, which is inverted here).
 */
export const sauronTheme: ThemeConfig = {
  ...defaultTheme,
  id: 'sauron-v2',
  /* ROW_H is 48 and the row must actually BE 48 — virtualisation computes spacer
   * heights from it, so a row that is 52.58 makes the scrollbar lie.
   *
   * The height is not set on the `<tr>`: an inline `height` there is a MINIMUM,
   * and CDS's cell content overrides it upward (measured — the inline 48px was
   * present and the row still rendered 52.58). It comes from the cell's inner
   * padding, which is `--space-1` top and bottom. 8 → 6 removes the 4.58 px.
   * Tuned to land on the number rather than accepting what falls out. */
  space: { ...defaultTheme.space, '1': 6 },

  /* D4 — the face, set through the THEME and not through CSS.
   * CDS's ThemeProvider emits `--fontFamily-*` as inline styles on its wrapper
   * (measured: 698 inline custom properties), and no stylesheet rule can beat an
   * inline style on the same element. A `body { --fontFamily-body: … }` override
   * was tried first and computed to `Noto Sans KR` — CDS's own value, unchanged. */
  fontFamily: Object.fromEntries(
    Object.keys(defaultTheme.fontFamily).map((k) => [k, SR_FONT_STACK]),
  ) as ThemeConfig['fontFamily'],

  /* Coinbase's weights, which is to say CDS's, unchanged — except `legal`.
   * [OWNER 2026-08-13: 방향색은 토스, 나머지는 Coinbase]
   *
   * ── Why almost nothing is overridden ────────────────────────────────────────
   * CDS IS Coinbase's design system, so its 14-token scale already IS the thing
   * being copied. Measured on coinbase.com the same day: body 16/400, emphasis
   * 16/600, section heading 20/600, hero number 40/400 — which are exactly CDS's
   * `body`, `headline`, `title3` and `display3`. Overriding them to imitate
   * Coinbase would mean editing Coinbase's own values to look more like
   * Coinbase. So `body` and `label2` were reverted to 400.
   *
   * ── The one exception: `legal` (13px) stays 500 ─────────────────────────────
   * Hangul at 12–13px renders with visibly broken strokes at 400 — the counters
   * inside ㅇ/ㅎ and the joins in ㄹ/ㅂ fill in at that size, which Latin at the
   * same size does not do.
   *
   * Coinbase never has to solve this because **Coinbase never sets body text at
   * 13px**: its smallest body register is 14/400 (measured — the second line of
   * the asset-table name cell). This product runs one step denser (60px rows
   * against Coinbase's 76px, [OWNER]), so its second line lands at 13px, and at
   * 13px the Latin-tuned 400 does not survive the writing system.
   *
   * So this is not a disagreement with Coinbase's scale. It is the correction
   * that Coinbase's scale would need if it were asked to render Hangul at a size
   * it never uses. If ROW_H ever grows enough for a 14px second line, delete
   * this and the override goes away with it. */
  fontWeight: {
    ...defaultTheme.fontWeight,
    legal: '500',
  },
};

/**
 * The surfaces v2 is allowed to paint, because they are the surfaces that can
 * hold the frozen direction pair at 4.5:1. `guards/contrast.test.ts` resolves
 * each out of the theme and measures both hues on it in both schemes; painting
 * anything outside this list fails that guard by design.
 *
 * ── MEASURED FINDING, 2026-08-13 (V1) ────────────────────────────────────────
 * `bgAlternate` and `bgSecondary` are BOTH rgb(238,240,243) in CDS light, and
 * the frozen hues do not clear the floor there:
 *
 *     up   #d92d3c on rgb(238,240,243) = 4.19:1
 *     down #0064ff on rgb(238,240,243) = 4.31:1
 *
 * Retuning the hue is forbidden (session prompt V1.3), so the surface goes
 * instead. Consequence for the component layer, and it is a real constraint on
 * V2: **v2 may not zebra-stripe table rows with `bgAlternate`.** Signed numbers
 * live on `bg` / `bgElevation1` / `bgElevation2` only. v1 stripes nothing and
 * separates rows with hairlines, so this costs nothing that v1 had.
 *
 * Both schemes clear the floor on all three surfaces below; the failure is
 * light-only.
 */
/* ── ★거부 목록이 비었다 [OWNER 2026-10-21 — 라이트 쌍 명도 −10pt] ───────────
 *
 * 위 문단이 「`bgAlternate` 에서 4.19 / 4.31 로 떨어지니 그 면에는 부호 있는
 * 숫자를 못 올린다」로 **면을 거부**했다. 그 거부는 **옛 쌍의 성질**이었다.
 *
 * 2026-10-21 에 라이트 쌍이 틴트 위 문턱을 넘기려고 명도를 10pt 내려가면서
 * (`direction.css` 의 「라이트 쌍을 한 번 더 민다」) 그 제약이 **같이 사라졌다**:
 *
 *     bgAlternate(#eef0f3) 위    up 4.08 → 5.67    down 3.98 → 5.47
 *
 * 그래서 두 면이 거부 목록에서 측정 목록으로 옮겨 간다. 거부 목록은 **빈 채로
 * 남긴다** — 지우지 않는 이유는, 「CDS 가 면을 손보면 빨개진다」는 그 가드의
 * 목적이 여전히 유효하고 다음에 거부할 면이 생기면 여기 적어야 하기 때문이다.
 *
 * ⚠ 제약이 풀렸다고 **줄무늬를 치라는 뜻은 아니다.** 위 문단의 「v1 은 줄무늬
 * 없이 헤어라인으로 행을 가른다」는 디자인 판단이고 대비와 무관하게 그대로다. */
export const DIRECTION_SURFACES = [
  'bg',
  'bgElevation1',
  'bgElevation2',
  'bgAlternate',
  'bgSecondary',
] as const;

/** Surfaces CDS offers that v2 has measured and rejected for direction text.
 * Named so the guard can assert they STILL fail — if CDS ever lightens them,
 * that is news, and news should arrive as a failing test rather than silence.
 *
 * 2026-10-21 에 비었다 — 위 블록의 까닭. */
export const REJECTED_FOR_DIRECTION = [] as const as readonly string[];

export type DirectionSurface = (typeof DIRECTION_SURFACES)[number];

/**
 * A denser space scale, MEASURED but NOT SELECTED.
 *
 * V2.7 measures row height and hands the number to the owner; choosing a
 * density is a separate decision (§2). This exists so the third measurement in
 * that report is a real render rather than an extrapolation, and so the owner
 * can see what a custom scale buys over CDS `compact`.
 *
 * Only the small end moves. The large steps are page rhythm and have nothing to
 * do with a table row.
 */
export const sauronDenseTheme: ThemeConfig = {
  ...sauronTheme,
  id: 'sauron-v2-dense',
  space: {
    ...sauronTheme.space,
    '0.25': 1,
    '0.5': 2,
    '0.75': 3,
    '1': 4,
    '1.5': 6,
    '2': 8,
  },
};
