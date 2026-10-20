/* 시나리오가 서버와 주고받는 둘 — 앵커와 거시 실측.
 *
 * 손잡이는 프런트가 돌린다(`combine.ts`). 서버가 답하는 것은 **오늘의 시장**뿐이라
 * 이 요청은 화면당 한 번이고, 그래서 손잡이를 끌 때 왕복이 없다.
 *
 * 백엔드가 없으면 그 사실을 말한다 — 백테스트·시뮬과 같은 규약이다(404 = 라우트가
 * 없다 = 뒤에 백엔드가 없다). 커브 없이는 «현재» 칸도 «시장» 칸도 못 그리므로
 * 이 화면은 굽기에 실을 수 없다.
 */

import { scenarioAnchorsUrl, scenarioMacroUrl } from '@/lib/staticPaths';

import type { Anchors } from './assemble';
import { ROUTE_MISSING_DETAIL } from '@/lib/apiBase';

export class ScenarioUnavailable extends Error {
  constructor() {
    super(ROUTE_MISSING_DETAIL);
    this.name = 'ScenarioUnavailable';
  }
}

/** 백엔드가 보내는 것. `Anchors` 에 서버만 아는 것들이 붙어 있다. */
export type AnchorsPayload = Anchors & {
  /** 이 커브가 정직하게 답할 수 있는 마지막 만기(년). 10Y 빈칸의 근거다. */
  curveLastTenorY: number;
  /** 포워드 시작점(년). 12개월이면 1. */
  fwdStartY: number;
  caveats: string[];
};

export async function fetchScenarioAnchors(): Promise<AnchorsPayload> {
  const r = await fetch(scenarioAnchorsUrl());
  if (r.status === 404) throw new ScenarioUnavailable();
  if (!r.ok) {
    const detail = (await r.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `시나리오 앵커: HTTP ${r.status}`);
  }
  return (await r.json().catch(() => {
    throw new Error('서버가 응답을 끝내지 못했어요, 다시 열어 보세요');
  })) as AnchorsPayload;
}

/** 모형이 딛고 선 거시 실측 — 손잡이 셋이 무엇에 얹히는 값인지.
 *
 * **없어도 화면은 선다.** 시나리오의 본체는 구운 기저와 오늘의 커브라 이 실측이
 * 빠져도 계산은 그대로다. 그래서 백엔드도 503 이 아니라 빈 목록을 주고, 여기서도
 * 실패를 시나리오 전체의 실패로 올리지 않는다.
 */
export type MacroPoint = { q: string; v: number };

export type MacroSeries = {
  key: string;
  label: string;
  unit: string;
  /** 어느 손잡이가 이 값에 얹히는가. */
  knob: string;
  source: string;
  /** 한국은행이 **발표하는** 통계인가. GDP 갭은 아니다 — HP 필터 산출물이다. */
  official: boolean;
  points: MacroPoint[];
};

export type MacroPayload = {
  asof: string | null;
  quarters: number;
  series: MacroSeries[];
  notes: string[];
  /** 옛 캐시로 연명 중인가. 그렇다면 `notes[0]` 이 그 사실을 말한다. */
  stale: boolean;
};

export async function fetchScenarioMacro(): Promise<MacroPayload> {
  const r = await fetch(scenarioMacroUrl());
  if (r.status === 404) throw new ScenarioUnavailable();
  if (!r.ok) throw new Error(`거시 실측: HTTP ${r.status}`);
  return (await r.json().catch(() => {
    throw new Error('서버가 응답을 끝내지 못했어요');
  })) as MacroPayload;
}
