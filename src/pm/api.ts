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
  paperCloseUrl, paperEnrollUrl, paperInstrumentsUrl, paperLegCloseUrl,
  paperLegUrl, paperResetUrl, paperRetireUrl, paperTradeUrl, paperUrl,
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
  /** **자료의 날** — 마지막 종가가 찍힌 날이다. 「오늘」이 아니다. */
  asof: string | null;
  /** **오늘**(서버의 실제 달력). 체결은 장중에 일어나고 마크는 종가라 둘이
   *  다를 수 있다 [OWNER 2026-09-22 — "민평 종가는 9월 21일까지 들어와있지만 …
   *  오늘 장중에 진입했다면 그건 22일날 진입한거임"]. 체결일·청산일의 기본값은
   *  **이쪽**이다 — `asof` 를 쓰면 오늘 한 거래가 어제 날짜로 장부에 들어간다. */
  today: string;
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
  /** 손으로 쌓은 다리 [OWNER 2026-09-22 — "IRS pay receive 하나 씩 쌓는 방식"].
   *
   *  위 둘과 **다른 물건**이라 일별 곡선이 없다. 저 둘은 엔진이 날마다 값을 매긴
   *  계열이고 이것은 「내 레벨에서 지금 레벨까지」 한 수다 — 없는 곡선을 지어내면
   *  차이 그래프가 거짓말을 한다. */
  position: {
    legs: PaperPositionLeg[];
    open: number;
    closed: number;
    /** 한 다리라도 못 매겼으면 **`null`** 이다(0 이 아니다). 오늘 체결한 다리가
     *  늘 그 자리에 선다 — 마크는 종가라 하루 뒤에 온다. */
    pnl: number | null;
    /** **매겨진 다리만의 소계.** 합계(`pnl`)가 `null` 일 때도 카드가 말할 것이
     *  있게 하는 칸이고, 합계와 **다른 칸**이라 둘을 섞을 수 없다. */
    scoredPnl: number | null;
    /** 매겨진 다리 수 · 아직인 다리 수 — 화면이 「3다리 중 2다리」를 적는다. */
    scored: number;
    pending: number;
    /** **부호를 지고** 더한 DV01 — 페이와 리시브가 상쇄되는 것이 이 북의 알맹이다. */
    netDv01: number;
    grossDv01: number;
  };
  /** 이 화면이 실제로 묻는 물음 — 내 판단이 규칙보다 나은가. */
  diff: { today: number; cum: number };
  failed: { id: string; why: string }[];
}

/** 손으로 쌓은 다리 하나 — **계기 하나 · 내가 체결한 레벨**.
 *
 *  `rateSign` 이 이 물건의 전부다: +1 이면 금리가 오를 때 번다. 계기마다 낱말이
 *  다르지만(페이/리시브 · 매수/매도) 산술은 이 부호 하나를 지난다. */
/**
 * 다리와 같이 얼린 **그날의 조건** [트레이더 2026-09-23].
 *
 * > "어제자에 진입한 조건은 60일, 2.5/0.5/3 … 오늘 보니까 120/2.5/0/3 이래서
 * >  확인할 수가 없게 됐다"
 *
 * Strategy 화면의 노브는 **오늘 것**이라, 어제 다리를 오늘 노브로 읽으면 청산선도
 * 손절선도 딴 선이 된다. 규칙 북(`enroll`)은 처음부터 조건을 얼리고 있었고
 * 포지션 카드만 그 규율 밖에 있었다.
 *
 * ⚠ **다섯이 다 있거나 아예 없거나**다 — 서버가 반쪽을 거절한다(「룩백만 적힌」
 * 다리는 청산선을 못 그린다). 그래서 이 타입에 선택 칸이 없다.
 */
export interface PaperLegKnobs {
  lookback: number;
  entryZ: number;
  exitZ: number;
  stopZ: number;
  /** `level` = 이탈 즉시 · `touch` = 밴드 복귀. 낱말은 MR 화면과 **같은 것**을
   *  쓴다(`mr/api.ts::MR_ENTRY_MODES`) — 두 화면이 같은 규칙을 다르게 부르면
   *  읽는 사람이 둘을 못 잇는다. */
  entryMode: 'level' | 'touch';
}

export interface PaperPositionLeg {
  n: number;
  kind: 'irs' | 'bond' | 'fut';
  tenor: string;
  side: string;
  rateSign: number;
  entry: string;
  /** 내가 체결한 레벨(%). 종가가 아니다 — 그게 이 북의 존재 이유다. */
  level: number;
  notional: number;
  dv01: number;
  tag: string;
  note: string;
  /** 얼린 조건 — **안 적은 다리는 `null`** 이다(빈 사전이 아니다). 「안 적었다」와
   *  「전부 0 으로 들어갔다」는 다른 말이다. */
  knobs: PaperLegKnobs | null;
  exit: string | null;
  exitLevel: number | null;
  open: boolean;
  /** 오늘 시장 레벨(%). 못 읽었으면 `null` — 「아직」이지 0 이 아니다. */
  mark: number | null;
  /** 그 마크가 **어느 날의 종가**인가. 체결일보다 앞서면 서버가 손익을 안 매긴다
   *  (「어제 종가 − 오늘 체결가」는 손익이 아니라 시간을 거꾸로 센 수다 —
   *  `backend/app/paper.py::score_leg` 머리). 그때 `pnl` 은 `null` 이고 사유가
   *  `why` 에 선다. */
  markT: string | null;
  bp: number | null;
  gross: number | null;
  cost: number | null;
  pnl: number | null;
  why: string | null;
}

/** 쓸 수 있는 계기 — **서버가 낸다**.
 *
 *  화면이 만기 목록을 손으로 적으면 선물에 2Y 를 넣는 일이 화면에서만 가능해진다
 *  (오너 예시가 그 자리였다 — 2년 국채선물은 KRX 에도 없다). `why` 는 빠진
 *  방향의 사유다(현물 매도). */
export interface PaperInstruments {
  asof: string | null;
  kinds: {
    kind: 'irs' | 'bond' | 'fut';
    label: string;
    tenors: string[];
    sides: { v: string; label: string }[];
    why?: string;
  }[];
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

/** 다리 하나 쌓기. **명목과 DV01 중 하나만** 준다 — 나머지는 서버가 그 계기의
 *  식으로 채운다. 둘 다 보내면 400 이고, 그건 규율이다: 안 맞는 쌍이 장부에
 *  들어오면 그 뒤로 어느 쪽이 참인지 아무도 모른다. */
export const addLeg = (l: {
  kind: string; tenor: string; side: string; entry: string; level: number;
  notional?: number; dv01?: number; tag?: string; note?: string;
  /** 그날의 조건. 주면 이 다리에 **언다** — 안 주면 조건 없는 다리다.
   *
   *  ⚠ 숫자 칸은 **글자 그대로** 보낸다(`'60'`). 화면에서 `Number()` 로 바꾸면
   *  빈 칸이 `0` 이 되어 「0σ 로 들어갔다」가 되고, 못 읽는 글자는 `NaN` → JSON
   *  `null` 이 되어 사유가 「빠졌다」로 바뀐다. 서버가 파싱해야 「숫자가
   *  아니에요: '삼'」을 말할 수 있다. */
  knobs?: Partial<Record<keyof PaperLegKnobs, string | number | undefined>>;
}) => post(paperLegUrl(), l);

/** 다리 하나 닫기. **청산 레벨도 내가 적는다** — 진입을 종가로 안 매겼다. */
export const closeLeg = (n: number, exit: string, level: number) =>
  post(paperLegCloseUrl(), { n, exit, level });

/** 장부를 새로 시작한다 — **지우지 않는다**. 옛 장부는 서버가 파일로 남기고
 *  `archivedTo` 로 그 이름을 돌려준다. 확인 낱말은 서버가 검사한다(실수 방지). */
export const resetBook = (): Promise<PaperSheet & { archivedTo?: string }> =>
  post(paperResetUrl(), { confirm: '초기화' }) as Promise<
    PaperSheet & { archivedTo?: string }>;

export async function fetchInstruments(): Promise<PaperInstruments> {
  const r = await fetch(paperInstrumentsUrl());
  if (r.status === 404) throw new BacktestUnavailable();
  if (!r.ok) throw new Error(`instruments: HTTP ${r.status}`);
  return r.json() as Promise<PaperInstruments>;
}
