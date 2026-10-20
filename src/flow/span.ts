/* 구간 손잡이 — Flow 의 네 면이 같이 쓴다 [2026-10-19].
 *
 * 자르는 자리는 **화면**이다. 서버는 전구간을 보내고 그 위에서 누적이 서므로,
 * 창을 서버가 자르면 누적의 시작점이 0 이 아니게 된다. 여기서 자르면 선이 그
 * 창의 첫날부터 다시 0 에서 오른다 — 「이 구간에 얼마나 샀나/찍었나」가 그림이
 * 말해야 하는 것이다.
 *
 * 수급 면은 **봉 수**로 자르고(영업일 축이 빽빽하다), 발행 면은 **달 수**로
 * 자른다(입찰일 축은 한 해 140개 안팎으로 성글어서 봉 수가 기간을 뜻하지 않는다).
 */

export type Span = '3M' | '1Y' | '3Y' | 'ALL';

/** 수급 면 — 영업일 봉 수. */
export const SPAN_BARS: Record<Span, number> = { '3M': 63, '1Y': 252, '3Y': 756, ALL: Infinity };

/** 발행 면 — 달 수. `null` 은 전체. */
export const SPAN_MONTHS: Record<Span, number | null> = { '3M': 3, '1Y': 12, '3Y': 36, ALL: null };

export const SPAN_OPTIONS: { value: Span; label: string }[] = [
  { value: '3M', label: '3M' },
  { value: '1Y', label: '1Y' },
  { value: '3Y', label: '3Y' },
  { value: 'ALL', label: '전체' },
];

/** `last` 에서 `months` 달 앞의 ISO 날짜. 발행 면이 창을 자르는 자. */
export function monthsBefore(last: string, months: number): string {
  const [y, m, d] = last.split('-').map(Number);
  const t = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1 - months, d ?? 1));
  return t.toISOString().slice(0, 10);
}
