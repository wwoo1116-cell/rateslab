/* RV 화면의 수량 표기 — 한 벌만 둔다 (RvScatter·RankingTable 이 각자 들고 있던
 * `sig` 중복의 정리, 2026-08-19 크리틱 P3).
 *
 * 규칙 둘:
 * 1. 부호 있는 값은 + 를 명시한다 — 표의 이웃 행과 부호로 비교하는 화면이다.
 * 2. **반올림 후 0 은 부호가 없다** — `(-0.04).toFixed(1)` 은 "-0.0" 을 찍는데,
 *    0 은 방향이 아니다(theme/tint.ts 의 같은 판단). 실측: 랭킹 52·64위가
 *    "-0.0σ" 로 서 있었다.
 */

/** 부호 명시 표기. 반올림 결과가 0 이면 부호 없이 "0.0" 류로. */
export function sig(v: number, digits = 1): string {
  const s = v.toFixed(digits);
  if (Number(s) === 0) return (0).toFixed(digits);
  return v > 0 ? `+${s}` : s;
}

/** bp 수준 표기 — 소수 첫째 자리 하나로 통일 (리드아웃 `nice()` 와 표
 * `toFixed(1)` 이 같은 양을 188bp / 188.0 두 모양으로 찍던 이원화의 정리). */
export function bp1(v: number): string {
  return v.toFixed(1);
}

/** 년 표기 — 잔존과 스냅 거리가 같은 자를 쓴다 [2026-10-02]. 뒤 0 은 떼므로
 * 0.25 → "0.25" · 0.5 → "0.5" · 3 → "3" 이다("3.00년"은 정수 만기를 소수처럼
 * 보이게 한다). 자리수를 아는 곳을 늘리지 않기 위해 여기 둔다 — RV 화면의
 * 수량 표기는 이 파일 한 벌이다(위 머리 주석). */
export function yr(v: number): string {
  return String(Number(v.toFixed(2)));
}
