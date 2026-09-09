/* Momentum 측정면의 서버 계약 — `/api/momentum/board` · `/history/{key}` · `/book`.
 *
 * 숫자는 전부 서버가 끝낸다(§16, `backend/app/momentum.py`): 신호 강도·합성·
 * 유지일수·속도합의·액면·표본내 성적까지. 이 파일은 타입과 페처뿐이다.
 * 라이브 전용이다 — 선물 종가가 SQL 에만 있다(Credit RV·MR 과 같은 사정).
 *
 * **손잡이가 없어 파라미터도 없다.** 룩백은 이 레인의 규율상 고르는 것이 아니라
 * 축이고(고르면 7년 합 −3,230만), 신호는 등록된 북 그대로 `macross` 하나다.
 */

import { BacktestUnavailable } from '@/lib/api';
import { momentumBoardUrl, momentumBookUrl, momentumHistoryUrl } from '@/lib/staticPaths';

/** 한 룩백의 칸. `signal` 은 엔진 값(−1~+1), `rate` 는 그것을 **금리 방향**으로
 *  뒤집은 값이다 — 가격 상승 = 금리 하락이라 화면은 `rate` 로 칠한다. */
export interface MomentumCell {
  lookback: number;
  signal: number;
  rate: number;
  tstat: number | null;
}

export interface MomentumTrendRow {
  tenor: string;
  price: number;
  asof: string;
  cells: MomentumCell[];
  composite: number;
  compositeRate: number;
  holdDays: number;
  /** 다섯 룩백 중 합성과 같은 방향인 것의 수. 이 화면 고유의 사실이다. */
  speedAgree: number;
  speedOf: number;
  notionalKrw: number;
}

export interface MomentumTheme {
  key: string;
  label: string;
  sign: number | null;
  rate: number | null;
}

export interface MomentumMacroLeg {
  asof: string;
  themes: MomentumTheme[];
  sign: number;
  rate: number;
  holdDays: number;
  notionalKrw: Record<string, number>;
}

/** 표 **앞**에 서는 한 줄 — 「지금 무엇을 볼까」의 답.
 *
 *  고르는 것은 **서버**다(§16). 또렷함 = (속도합의, |합성 강도|) 사전식이고,
 *  그 순서는 이 레인의 규율에서 온다 — 「다섯 룩백이 갈리면 «모른다»에 가깝다」.
 *  강도는 **무부호**이고 방향은 `rate` 가 진다(가격 상승 = 금리 하락).
 *
 *  `macroAgrees` 는 **셋째 값이 있다**: 매크로가 없거나 한쪽이 중립이면 `null`
 *  이고 그건 「반대」가 아니라 **모른다**다. */
export interface MomentumHeadline {
  tenor: string;
  rate: number;
  strength: number;
  speedAgree: number;
  speedOf: number;
  holdDays: number;
  macroAgrees: boolean | null;
  macroRate: number | null;
}

export interface MomentumBoard {
  asof: string;
  signal: string;
  lookbacks: number[];
  targetBookVolKrw: number;
  costTicks: number;
  tstatCap: number;
  trend: MomentumTrendRow[];
  /** 없을 수 있다 — 추세 행이 하나도 없으면 서버가 `null` 을 낸다. */
  headline: MomentumHeadline | null;
  /** 매크로 신호 파일이 아직 안 왔으면 null — 그때는 `macroNote` 가 이유를 든다.
   *  값이 없는 것과 0 인 것을 섞지 않는다. */
  macro: MomentumMacroLeg | null;
  macroNote: string | null;
  blend: { weight: number; note: string };
  lock: { freeze: string; note: string };
}

export interface MomentumHistory {
  key: string;
  dates: string[];
  /** 조정가 **차분 누적**(창 시작 = 100). 수준이 아니다 — 매크로 다리는 null. */
  index: number[] | null;
  signal: number[];
  rate: number[];
}

export interface MomentumCard {
  sharpe: number | null;
  calmar: number | null;
  maxDrawdown: number | null;
  /** 기준 다리(추세)의 실현 변동성에 맞춘 낙폭. **원화 열은 다리마다 건 위험이
   *  달라 그냥 못 비교한다** — Sharpe·Calmar 는 비율이라 안 변하지만 낙폭은
   *  변한다(2026-09-09 재점검). Man 2016 Figure 7 의 그 규약. */
  maxDrawdownVolMatched: number | null;
  /** 낙폭 경로의 제곱평균제곱근. `mrmetrics.score` 와 **같은 식**이고 제곱해서
   *  루트를 씌우므로 **음수가 될 수 없다** — 화면이 부호를 뒤집지 않는다
   *  (MR 화면이 뒤집고 있었던 것이 2026-09-09 진단 D2). 단위는 원화. */
  ulcer: number | null;
  ulcerVolMatched: number | null;
  /** 연손익 ÷ Ulcer. **무차원이라 자본 분모 없이 두 레인을 비교할 수 있다.** */
  martin: number | null;
  /** 기준 다리 대비 실현 변동성 비. 1.0 이 기준 다리 자신이다. */
  volRatio: number | null;
  annPnlKrw: number | null;
  annVolKrw: number | null;
  days: number;
}

export interface MomentumBook {
  window: { start: string | null; end: string };
  legs: { key: string; label: string; card: MomentumCard }[];
  volMatch?: { ref: string; note: string };
  lock: { freeze: string; note: string; why: string };
}

async function get<T>(url: string, what: string): Promise<T> {
  const r = await fetch(url);
  if (r.status === 404) throw new BacktestUnavailable();
  if (!r.ok) {
    const detail = await r.json().catch(() => null);
    throw new Error(detail?.detail ?? `${what}: HTTP ${r.status}`);
  }
  return r.json();
}

export function fetchMomentumBoard(): Promise<MomentumBoard> {
  return get<MomentumBoard>(momentumBoardUrl(), 'momentum board');
}

export function fetchMomentumHistory(key: string): Promise<MomentumHistory> {
  return get<MomentumHistory>(momentumHistoryUrl(key), 'momentum history');
}

export function fetchMomentumBook(): Promise<MomentumBook> {
  return get<MomentumBook>(momentumBookUrl(), 'momentum book');
}
