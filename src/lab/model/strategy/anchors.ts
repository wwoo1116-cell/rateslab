/* 오늘의 시장 — 이 면이 서버에 닿는 **유일한 자리**.
 *
 * 손잡이는 프런트가 돌린다(`path.ts`). 서버가 답하는 것은 오늘의 커브뿐이라
 * 요청은 화면당 한 번이고, 점을 찍을 때 왕복이 없다.
 *
 * ## ⚠ 세션 3 에게 — 이 라우트가 은퇴하면 이 면이 같이 죽는다
 *
 * `/api/scenario/anchors`(`backend/app/labscenario.py`)는 시나리오 레인이
 * 만들었지만 **이 면도 그것 말고는 오늘의 커브에 닿을 길이 없다.** 시나리오
 * 화면을 은퇴시킬 때 라우트까지 같이 내리면 「전략」 면의 함의·트레이드 두 줄이
 * 통째로 빈다. 라우트는 남기거나, 남길 수 없으면 이름을 옮기고 알려 주세요.
 *
 * 백엔드가 없으면 그 사실을 말한다 — 404 = 라우트가 없다 = 뒤에 백엔드가 없다.
 * 오늘의 커브 없이는 「함의」도 「트레이드」도 못 그리므로 이 면은 굽기에 못
 * 싣는다. 다만 **「뷰」·「논거」·「리스크」 세 줄은 서야 한다** — 그 셋은 구운
 * 기저만으로 나오는 값이라, 커브가 없다고 화면 전체를 내리면 말할 수 있는 것도
 * 같이 사라진다.
 */

import { scenarioAnchorsUrl } from '@/lib/staticPaths';

import type { StrategyAnchors } from './trades';
import { ROUTE_MISSING_DETAIL } from '@/lib/apiBase';

export class AnchorsUnavailable extends Error {
  constructor() {
    super(ROUTE_MISSING_DETAIL);
    this.name = 'AnchorsUnavailable';
  }
}

export async function fetchAnchors(): Promise<StrategyAnchors> {
  const r = await fetch(scenarioAnchorsUrl());
  if (r.status === 404) throw new AnchorsUnavailable();
  if (!r.ok) {
    const detail = (await r.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `오늘의 커브: HTTP ${r.status}`);
  }
  return (await r.json().catch(() => {
    throw new Error('서버가 응답을 끝내지 못했어요, 다시 열어 보세요');
  })) as StrategyAnchors;
}
