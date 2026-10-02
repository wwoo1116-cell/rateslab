import type { RvCreditItem } from './api';

/* ── 버킷 매핑 규칙 — 「사려는 유통물」→ v2 Score 버킷 [OWNER 2026-10-01] ────────
 *
 * [OWNER] 「장중에 거래되는 유통물을 사고 싶은데 지금 얼마나 매력적인지, 원래
 * 쓰던 Score 로 바로 계산해달라.」 개별 유통물에는 고유 시계열 모델이 없다 —
 * 그래서 (섹터, 잔존)을 v2 의 **섹터×테너 버킷**으로 매핑해 그 버킷의 Score 를
 * 빌려 온다. 규칙은 셋:
 *
 *   ① 섹터는 그대로 쓴다. v2 크레딧은 **각 대표등급 하나**(통안 · 산금채 AAA ·
 *      공사채 AAA · 은행채 AAA · 회사채 AAA · 카드채 AA+ · 캐피탈채 AA-)라
 *      등급축이 따로 없다.
 *   ② 잔존(년)은 그 섹터가 가진 테너 버킷 중 **가장 가까운 것**으로 스냅하고,
 *      **얼마나 멀리 스냅했는지(`gapYears`)를 같이 돌려준다** — 빌려온 칸이
 *      얼마나 먼 칸인지는 화면이 말해야 할 사실이다.
 *   ③ **양쪽 끝은 스냅하지 않고 사유를 돌려준다.** 상한도 하한도 조용히 끌면
 *      거짓이 된다(아래 ★).
 *
 * ── ★채점되는 잔존은 **양쪽**이 막혀 있다 [하한 추가 2026-10-02] ──────────────
 *
 * 처음 판은 상한(`maxYears`, 이 화면은 3년)만 막았다. 그런데 산 페이로드를 재
 * 보니 Score 가 붙은 테너는 **9M~3Y 여섯 칸**이고 히트맵의 3M·6M 두 칸에는
 * Score 가 없다. 서버가 사유까지 들고 있다 —
 *
 *     "만기 보유(H 안에 만기) — 금리 위험이 없어 버퍼가 정의되지 않아요."
 *
 * 그래서 잔존 0.4년을 넣으면 **조용히 9M 버킷으로 끌려갔다**: 잔존이 거의 두 배인
 * 칸의 Score 를 빌려 쓰면서 화면은 그 사실을 안 적었다(0.1년이면 6.5배다). 상한
 * 쪽에 「조용히 3Y 로 끌려가 거짓이 된다」고 적어 둔 바로 그 결함이 **아래쪽에만
 * 가드가 없어** 살아 있었다. 오너 책에는 잔존 수개월 종목이 실제로 돈다.
 *
 * 하한의 식은 **서버 것 그대로** 쓴다 — `rv.py` 의 `maturity <= horizon`, 즉
 * 연 단위로 `years <= hMonths / 12`. 여기에 상수(0.75 등)를 적으면 H 가 화면
 * 컨트롤(3/6/12개월)이라 **화면이 거짓말을 한다**(RankingTable 의 `hMonths`
 * prop 이 같은 이유로 있다). 그래서 bounds 는 페이로드를 그대로 받는다.
 *
 * ★장기 로드맵(kbond-live): 장중 호가의 (cls, rt, ttm)→(v2 섹터, 잔존)→이 규칙
 *   으로 호가마다 Score 를 컬러 inline. `kbond-web` 은 **별 리포라 이 코드를 못
 *   가져온다** — 그때는 이 규칙을 그대로 옮긴다(두 벌로 갈리면 색이 어긋난다).
 *   v2 가 대표등급뿐이라 커버 못 하는 종목(대표등급 밖·유동화·MBS)은 무색.
 *
 * ⚠ 최근접 탐색을 배열 리듀스로 쓰지 않는다 — `guards/rv-analysis` 가 `src/rv/`
 *   전체에서 그 호출을 **서버 재계산 흔적**으로 금지한다(§16). 좌표 변환
 *   (min/max/abs)은 허용이라 아래 for-루프로 센다.
 */

/** 채점 가능한 잔존의 **양쪽 끝**. 둘 다 서버 페이로드의 값이다 — 화면 상수가
 *  아니다. `RvPayload` 가 이 꼴을 그대로 만족하므로 호출부는 `data` 를 넘긴다. */
export interface PickBounds {
  /** 이 화면의 만기 상한(년). 워크북 커브가 3M~3Y 여덟 노드라서 3.0 이다. */
  maxYears: number;
  /** 보유기간 H(개월). 하한은 `hMonths / 12` — H 안에 만기가 들면 버퍼가 없다. */
  hMonths: number;
}

/** 스냅 결과. `null` = 아직 지정 전(섹터 미선택 또는 잔존 0). */
export type PickOutcome =
  /** 적중 — `gapYears` 는 입력 잔존과 빌려온 버킷의 거리(년, 양수). */
  | { kind: 'hit'; item: RvCreditItem; gapYears: number }
  /** 채점 범위 밖. `side` 가 어느 끝인지, `edgeYears` 가 그 끝의 값(년)이다 —
   *  화면이 사유 문장을 이 둘로 쓴다(숫자를 화면에 또 적지 않는다). */
  | { kind: 'oob'; side: 'above' | 'below'; edgeYears: number };

export function snapCreditBucket(
  items: readonly RvCreditItem[],
  sector: string,
  ttm: number,
  bounds: PickBounds,
): PickOutcome | null {
  if (sector === '' || !(ttm > 0)) return null;
  /* 상한 밖은 스냅 금지 — 사유로 돌려준다(규칙 ③). */
  if (ttm > bounds.maxYears) return { kind: 'oob', side: 'above', edgeYears: bounds.maxYears };
  /* ★하한도 같다. 식은 서버의 `maturity <= horizon` 그대로(위 ★). */
  const minYears = bounds.hMonths / 12;
  if (ttm <= minYears) return { kind: 'oob', side: 'below', edgeYears: minYears };
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
  /* 섹터는 items 에서 뽑으므로 보통 하나 이상 있다 — 방어적으로 없으면 사유.
     그때의 끝은 상한이다(그 섹터에 칸이 아예 없다는 뜻이라 아래쪽 사유가 아니다). */
  if (!best) return { kind: 'oob', side: 'above', edgeYears: bounds.maxYears };
  return { kind: 'hit', item: best, gapYears: bestGap };
}
