import type { RvCreditItem } from './api';

/* ── 버킷 매핑 규칙 — 「사려는 유통물」→ v2 Score 버킷 [OWNER 2026-10-01] ────────
 *
 * [OWNER] 「장중에 거래되는 유통물을 사고 싶은데 지금 얼마나 매력적인지, 원래
 * 쓰던 Score 로 바로 계산해달라.」 개별 유통물에는 고유 시계열 모델이 없다 —
 * 그래서 (섹터, 잔존)을 v2 의 **섹터×테너 버킷**으로 매핑해 그 버킷의 Score 를
 * 빌려 온다. 규칙은 둘:
 *
 *   ① 섹터는 그대로 쓴다. v2 크레딧은 **6섹터 = 각 대표등급 하나**(산금채 AAA ·
 *      공사채 AAA · 은행채 AAA · 회사채 AAA · 카드채 AA+ · 캐피탈채 AA-)라
 *      등급축이 따로 없다.
 *   ② 잔존(년)은 그 섹터가 가진 테너 버킷 중 **가장 가까운 것**으로 스냅한다.
 *      상한(maxYears, 이 화면은 3년) 밖이면 **스냅하지 않고** 사유를 띄운다 —
 *      스냅하면 5Y·10Y 가 조용히 3Y 로 끌려가 거짓이 된다(만기 상한은 서버가
 *      정한다, OWNER 2026-08-20).
 *
 * ★장기 로드맵(kbond-live): 장중 호가의 (cls, rt, ttm)→(v2 섹터, 잔존)→이 규칙
 *   으로 호가마다 Score 를 컬러 inline. `kbond-web` 은 **별 리포라 이 코드를 못
 *   가져온다** — 그때는 이 규칙을 그대로 옮긴다(두 벌로 갈리면 색이 어긋난다).
 *   v2 가 6섹터×대표등급뿐이라 커버 못 하는 종목(대표등급 밖·유동화·MBS)은 무색.
 *
 * ⚠ 최근접 탐색을 배열 리듀스로 쓰지 않는다 — `guards/rv-analysis` 가 `src/rv/`
 *   전체에서 그 호출을 **서버 재계산 흔적**으로 금지한다(§16). 좌표 변환
 *   (min/max/abs)은 허용이라 아래 for-루프로 센다.
 */

/** 스냅 결과. `null` = 아직 지정 전(섹터 미선택 또는 잔존 0). */
export type PickOutcome =
  | { kind: 'hit'; item: RvCreditItem }
  | { kind: 'oob' };

export function snapCreditBucket(
  items: readonly RvCreditItem[],
  sector: string,
  ttm: number,
  maxYears: number,
): PickOutcome | null {
  if (sector === '' || !(ttm > 0)) return null;
  /* 상한 밖은 스냅 금지 — 사유로 돌려준다(위 규칙 ②). */
  if (ttm > maxYears) return { kind: 'oob' };
  let best: RvCreditItem | null = null;
  let bestGap = Infinity;
  for (const it of items) {
    if (it.sector !== sector) continue;
    const gap = Math.abs(it.years - ttm);
    if (gap < bestGap) {
      best = it;
      bestGap = gap;
    }
  }
  /* 섹터는 items 에서 뽑으므로 보통 하나 이상 있다 — 방어적으로 없으면 사유. */
  if (!best) return { kind: 'oob' };
  return { kind: 'hit', item: best };
}
