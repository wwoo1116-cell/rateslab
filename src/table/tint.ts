/**
 * The change-cell tint ramp, carried from v1 unchanged.
 *
 * It is NOT re-derived from CDS colours and must not be: the ramp is an opacity
 * over the direction hue, and the direction hue is frozen (V1). CDS has no
 * opinion about it and should not acquire one.
 *
 * Two rules from v1 §4 that the ramp exists to serve:
 *   - only signed numbers take colour; a level stays ink;
 *   - below the floor there is NO tint at all. A 0.2bp move is not a faint
 *     version of a move, it is noise, and tinting it teaches the eye to read
 *     noise as signal.
 */

/** bp below which a change carries no tint at all. */
export const TINT_FLOOR = 0.5;

/** bp at which the tint reaches full strength. */
export const TINT_CEIL = 10;

/** Alpha for a change, 0 when below the floor. Monotone in |v| between. */
export function tintAlpha(v: number | null | undefined): number {
  if (v == null) return 0;
  const a = Math.abs(v);
  if (a < TINT_FLOOR) return 0;
  const t = Math.min(1, (a - TINT_FLOOR) / (TINT_CEIL - TINT_FLOOR));
  return Number((0.06 + t * 0.14).toFixed(3));
}

/** The class that colours the number itself. Levels never call this. */
export function directionClass(v: number | null | undefined): string {
  if (v == null || v === 0) return 'sr-flat';
  return v > 0 ? 'sr-up' : 'sr-down';
}

/** Background wash for a change cell, as an inline style. Uses the same two
 * custom properties the text does, so a tint can never disagree with its
 * number about which way the market went. */
export function tintStyle(v: number | null | undefined): React.CSSProperties | undefined {
  const alpha = tintAlpha(v);
  if (alpha === 0) return undefined;
  const hue = v! > 0 ? 'var(--sr-up)' : 'var(--sr-down)';
  return {
    backgroundColor: `color-mix(in srgb, ${hue} ${Math.round(alpha * 100)}%, transparent)`,
  };
}

/* ── 매트릭스의 틴트는 **다른 눈금**이다 (v1 §J, 그대로) ─────────────────────
 *
 * 위의 `tintAlpha` 는 변화 열의 것이고 bp 로 눈금을 잰다. 매트릭스는 그럴 수가
 * 없다: 168칸이 한 화면에 있고, 그날의 최대값으로 정규화하면 큰 날에는 거의 모든
 * 칸이 칠해진다(v1 실측 96~99%). 그래서 매트릭스는 **자기 과거 대비 백분위**로
 * 잰다 — 이 칸의 오늘 움직임이 이 칸의 역사에서 얼마나 드문 일인가. 백분위는
 * 서버가 낸다(`movePct`, §16).
 *
 * 그리고 강도의 상한이 다르다. 변화 열의 숫자는 **색 있는 글자**라 뒤에 채움을
 * 깔면 그 글자의 대비를 갉아먹는다(그래서 위쪽 램프는 0.20 에서 멈춘다).
 * 매트릭스의 숫자는 **잉크**라 깊이를 견딘다 — 0.45 까지 간다.
 */

/** pct70 에서의 최소 틴트. 이 아래는 아예 안 칠한다. */
export const MATRIX_FLOOR = 0.06;
/** pct97 에서의 최대 틴트. 잉크 위라 여기까지 갈 수 있다. */
export const MATRIX_FULL = 0.45;
export const MATRIX_PCT_LO = 70;
export const MATRIX_PCT_HI = 97;

/** 매트릭스 칸의 등급 틴트. `pct` 는 서버가 낸 자기 과거 백분위. */
export function matrixTint(
  pct: number | null | undefined,
  up: boolean,
): React.CSSProperties | undefined {
  if (pct == null || pct < MATRIX_PCT_LO) return undefined;
  const f = Math.min(1, (pct - MATRIX_PCT_LO) / (MATRIX_PCT_HI - MATRIX_PCT_LO));
  const alpha = MATRIX_FLOOR + (MATRIX_FULL - MATRIX_FLOOR) * f;
  const hue = up ? 'var(--sr-up)' : 'var(--sr-down)';
  return {
    backgroundColor: `color-mix(in srgb, ${hue} ${(alpha * 100).toFixed(1)}%, transparent)`,
  };
}

/**
 * D4.1 — the sign as a GLYPH, not only as a hue.
 *
 * v1's rule is that sign must stay legible in monochrome; a bare `+` / `−`
 * satisfied it thinly (a minus is one thin stroke, and at caption size on a
 * tinted cell it is easy to lose). An arrow carries direction in its shape, so
 * the colour becomes reinforcement rather than the only channel.
 *
 * Zero gets no arrow: it has no direction, and drawing one would claim it does.
 */
export function directionGlyph(v: number | null | undefined): string {
  if (v == null || v === 0) return '';
  return v > 0 ? '↗' : '↘';
}

/** The number without its sign — the arrow carries that now. Keeps the digits
 * `tabular-nums`-aligned, which a leading `+`/`−` of differing width did not. */
export function unsignedDelta(text: string): string {
  return text.replace(/^[+\u2212-]/, '');
}

/* ── 신호 강도의 틴트는 **또 다른 눈금**이다 (Momentum, 2026-09-09) ──────────
 *
 * 위 둘과 같은 이유로 눈금이 따로 선다. `tintAlpha` 는 **bp** 로 재고
 * (0.5 아래는 잡음), `matrixTint` 는 **자기 과거 백분위**로 잰다. Momentum 의
 * 칸은 둘 다 아니다 — 값이 −1~+1 의 «추세 강도»이고, 그 눈금은 엔진이 이미
 * 고정해 두었다(`ctabacktest.TSTAT_CAP` = 4, 그래서 |t|=4 면 1.0).
 *
 * 그 값을 bp 램프에 그대로 넣으면 전 칸이 바닥(0.5) 아래라 **아무것도 안 칠해진다**.
 * 그래서 눈금만 옮기고 **알파 끝점은 변화 열의 것을 그대로 쓴다**(0.06~0.20):
 * 이 칸의 숫자도 변화 열처럼 **색 있는 글자**라, 뒤에 깊은 채움을 깔면 그 글자의
 * 대비를 갉아먹는다. 매트릭스가 0.45 까지 가는 것은 거기 숫자가 잉크이기 때문이다.
 *
 * 바닥은 |t| = 0.5 에 해당하는 0.125 다. 그 아래를 칠하면 「추세랄 것이 없다」를
 * 옅은 추세로 읽게 가르친다 — 위 램프가 0.2bp 에 대해 하는 말과 같다.
 */

/** 강도(0~1) 바닥. 이 아래는 아예 안 칠한다. |t| = 0.5 에 해당한다. */
export const SIGNAL_FLOOR = 0.125;

/**
 * 신호 칸의 틴트. `rate` 는 **금리 방향**으로 부호를 뒤집은 값이다
 * (가격 상승 = 금리 하락 — `backend/app/momentum.py` 머리).
 */
export function signalTint(rate: number | null | undefined): React.CSSProperties | undefined {
  if (rate == null || rate === 0) return undefined;
  const a = Math.abs(rate);
  if (a < SIGNAL_FLOOR) return undefined;
  const t = Math.min(1, (a - SIGNAL_FLOOR) / (1 - SIGNAL_FLOOR));
  const alpha = Number((0.06 + t * 0.14).toFixed(3));
  const hue = rate > 0 ? 'var(--sr-up)' : 'var(--sr-down)';
  return {
    backgroundColor: `color-mix(in srgb, ${hue} ${Math.round(alpha * 100)}%, transparent)`,
  };
}
