/* 투자자별 수급 — 서버 계약과 페처 [2026-10-19].
 *
 * **산술은 서버가 한다**(§16). 여기는 타입과 fetch 셋줄뿐이고, 화면은 읽고
 * 칠하기만 한다 — 영합 폐쇄·누적·편차·순위는 전부 `backend/app/flow.py` 에
 * 있고 그 머리에 근거가 적혀 있다.
 */

import { BacktestUnavailable } from '@/lib/api';
import { flowBoardUrl, flowHistoryUrl } from '@/lib/staticPaths';

/** 면 둘. **단위가 달라 한 축에 못 겹친다**(계약 대 백만원) — 겹치는 그림이
 *  아니라 갈라지는 면인 이유다. */
export type FlowSide = 'fut' | 'cash';
export type FlowTenor = '3Y' | '10Y';

/** 대분류 한 칸 — 서로 더하면 **0** 이다(영합). 순위가 아니라 대조다. */
export interface FlowTop {
  key: string;
  label: string;
  value: number;
}

/** 순위표 한 줄. */
export interface FlowRow {
  key: string;
  label: string;
  group: string;
  d1: number;
  d5: number;
  d20: number;
  ytd: number;
  /** 자기 과거 분포 대비 당일 편차. **창은 오늘을 뺀다**. 못 재면 `null`. */
  sigma: number | null;
  /** 직전 252봉 일평균 |순매수| — 하한을 넘었나를 이 수가 정한다. */
  avgAbs: number;
  /** 하한 아래면 `false` 이고 **지우지 않는다**. */
  ranked: boolean;
  /** 순위 밖이면 `null` — 「없다」와 「0등」은 다른 말이다. */
  rank: number | null;
}

export interface FlowSeries {
  key: string;
  label: string;
  values: number[];
}

export interface FlowChart {
  dates: string[];
  /** 누적 — **최대 4계열**이다(N계열 팔레트가 없다). 전수는 표가 진다. */
  cum: FlowSeries[];
  /** 일별 — 한 계열. 막대로 그린다(이산 일별값). */
  daily: FlowSeries | null;
}

export interface FlowBoard {
  side: FlowSide;
  tenor: FlowTenor | null;
  /** ★**둘이 다른 것이 정상**이다 — 현물이 늦게 들어온다 [OWNER 2026-10-19].
   *  화면이 둘을 따로 적어야 하고, 어긋나는 것은 경고가 아니다. */
  asof: { fut: string | null; cash: string | null };
  unit: string;
  days: number;
  /** 현물면은 **빈 배열**이다 — 상위 집합이 없으니 대조 칸도 없다. */
  top: FlowTop[];
  sub: FlowRow[];
  rankFloor: number;
  series: FlowChart;
  excluded: { id: string; label: string; why: string }[];
  /** 「무엇을 보고 있나」를 **서버가** 말한다. 화면이 지어내지 않는다. */
  basis: string;
}

export interface FlowHistory {
  key: string;
  label: string;
  side: FlowSide;
  tenor: FlowTenor | null;
  dates: string[];
  daily: number[];
  cum: number[];
}

/** 한 벌. 404 는 **백엔드가 없다**는 뜻이고(라이브 전용 화면) 그 사실을
 *  화면이 다른 문장으로 말한다 — 그래서 일반 오류와 가른다. */
async function get<T>(url: string, what: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(url, signal ? { signal } : undefined);
  if (r.status === 404) throw new BacktestUnavailable();
  if (!r.ok) {
    const detail = await r.json().catch(() => null);
    throw new Error(detail?.detail ?? `${what}: HTTP ${r.status}`);
  }
  return r.json();
}

export async function fetchFlowBoard(
  side: FlowSide, tenor: FlowTenor, signal?: AbortSignal,
): Promise<FlowBoard> {
  return get(flowBoardUrl(`side=${side}&tenor=${tenor}`), 'flow', signal);
}

export async function fetchFlowHistory(
  key: string, side: FlowSide, tenor: FlowTenor,
): Promise<FlowHistory> {
  return get(flowHistoryUrl(key, `side=${side}&tenor=${tenor}`), 'flow-history');
}
