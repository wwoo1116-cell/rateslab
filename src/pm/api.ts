/* 페이퍼 북의 계약 — `backend/app/paper.py` 의 페이로드 그대로.
 *
 * ## 이 화면이 Strategy 와 다른 점
 *
 * 계획면(`/api/mr/plan`)은 **표본내**를 말한다 — 조건을 고른 창과 성과를 잰 창이
 * 같아서, 그 화면의 1년 손익은 성과가 아니라 고른 결과다(그 화면이 스스로 그렇게
 * 적는다). 페이퍼 북은 그 다음을 말한다: **고른 뒤에 무슨 일이 일어났나.**
 *
 * ## 쓰기가 있는 유일한 화면이다
 *
 * 나머지는 전부 읽기이고 사용자 상태는 `localStorage` 에 있다. 여기만 서버에
 * 쓰는 이유는 기록이 브라우저를 넘어 살아야 하기 때문이다(`paper.py` 머리).
 * 쓰기 넷은 전부 **덧쓰기**다 — 지우는 경로가 없다.
 *
 * ## 숫자는 서버가 끝낸다 (§16)
 *
 * 누적도 차이도 오늘 손익도 전부 서버가 낸 값이다. 여기서 다시 더하면 두 번째
 * 정의가 생기고, 반올림이 갈리는 날 화면이 스스로를 반박한다.
 */

import { BacktestUnavailable } from '@/lib/api';
import type { MrSplit } from '@/mr/api';
import {
  paperCloseUrl, paperEnrollUrl, paperRetireUrl, paperTradeUrl, paperUrl,
} from '@/lib/staticPaths';

/** 하루 한 점. `cum` 은 **서버가 굴린** 누적이다. */
export interface PaperDay {
  t: string;
  pnl: number;
  cum: number;
}

/** 규칙 북의 한 다리 — 등록한 조건이 시키는 대로 한 것.
 *
 *  `why` 가 서면 그 다리는 아직 «잴 것이 없다»는 뜻이다(등록일 뒤의 봉이 없음).
 *  0 과 구별해야 한다 — 0 은 「안 벌었다」이고 이것은 「아직 안 시작했다」다. */
export interface PaperRuleLeg {
  id: string;
  label: string;
  opened: string;
  retired: string | null;
  knobs: Record<string, number | string>;
  days: number;
  totalPnl: number;
  numTrades: number;
  winRate: number | null;
  maxDrawdown: number;
  /** 클릭 없이 서는 분해 — 계획면에 건 그 규율 그대로. */
  split: MrSplit | null;
  open: { entryDate: string; direction: number } | null;
  why: string | null;
  daily: { t: string; pnl: number }[];
}

/** 수동 북의 한 건. `open` 이면 아직 들고 있다. */
export interface PaperTrade {
  n: number;
  dir: number;
  entryT: string;
  exitT: string;
  entryV: number;
  exitV: number;
  bars: number;
  notional: number;
  open: boolean;
  pnl: number;
  mtm: number;
  cost: number;
  carry?: number;
  rolldown?: number;
  funding?: number;
}

/** 수동 북의 한 계열. `real` 이 거짓이면 **엔진 근사**이고 화면이 그것을 적는다. */
export interface PaperManualLeg {
  id: string;
  label: string;
  real: boolean;
  totalPnl: number;
  numTrades: number;
  openTrades: number;
  skipped: number;
  split: MrSplit | null;
  trades: PaperTrade[];
  daily: { t: string; pnl: number }[];
}

export interface PaperSheet {
  available: boolean;
  why?: string;
  opened: string | null;
  asof: string | null;
  costBp: number;
  notional: number;
  rule: {
    enrolled: number;
    retired: number;
    today: number;
    cum: number;
    legs: PaperRuleLeg[];
    /** 다리들의 합. 한 다리라도 못 잰 항은 **`null`** 이다(0 이 아니다). */
    split: MrSplit | null;
    daily: PaperDay[];
  };
  manual: {
    trades: number;
    open: number;
    today: number;
    cum: number;
    legs: PaperManualLeg[];
    split: MrSplit | null;
    daily: PaperDay[];
  };
  /** 이 화면이 실제로 묻는 물음 — 내 판단이 규칙보다 나은가. */
  diff: { today: number; cum: number };
  failed: { id: string; why: string }[];
}

export async function fetchPaper(): Promise<PaperSheet> {
  const r = await fetch(paperUrl());
  if (r.status === 404) throw new BacktestUnavailable();
  if (!r.ok) {
    const detail = (await r.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `paper: HTTP ${r.status}`);
  }
  return r.json() as Promise<PaperSheet>;
}

/** 쓰기 한 벌 — 응답은 **갱신된 장부 전체**라 화면이 다시 묻지 않는다.
 *
 *  서버가 장부를 쓰고 곧바로 다시 세워서 돌려준다. 쓰기와 읽기를 두 번 왕복하면
 *  그 사이에 다른 창이 쓴 것과 갈릴 수 있고, 화면은 그 사실을 모른다. */
async function post(url: string, body: unknown): Promise<PaperSheet> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (res.status === 404) throw new BacktestUnavailable();
  if (!res.ok) {
    /* 서버가 사유를 한국어로 적어 보낸다(`detail`) — 그것을 그대로 세운다.
       상태 코드만 보여 주면 읽는 사람이 무엇을 고쳐야 할지 모른다. */
    let why = `HTTP ${res.status}`;
    try {
      const got = (await res.json()) as { detail?: string };
      if (got?.detail) why = got.detail;
    } catch {
      /* 본문이 JSON 이 아니면 상태 코드로 남긴다. */
    }
    throw new Error(why);
  }
  return (await res.json()) as PaperSheet;
}

export const enrollSeries = (id: string) => post(paperEnrollUrl(), { id });
export const retireSeries = (id: string) => post(paperRetireUrl(), { id });
export const addTrade = (t: {
  id: string; dir: number; entry: string; notional?: number; label?: string;
}) => post(paperTradeUrl(), t);
export const closeTrade = (n: number, exit: string) =>
  post(paperCloseUrl(), { n, exit });
