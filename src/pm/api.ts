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

import { BacktestUnavailable, type BacktestResult } from '@/lib/api';
import type { MrSplit } from '@/mr/api';
import {
  paperCloseUrl, paperEnrollUrl, paperInstrumentsUrl, paperLegCloseUrl,
  paperLegKnobsUrl, paperLegUrl, paperResetUrl, paperRetireUrl, paperSuggestUrl,
  paperTraceUrl, paperTradeUrl, paperUrl,
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
  /** ★**장중 레벨로 보고 있는가** [OWNER 2026-09-28 — "지금 2년은 4.06, 5년은 4.27,
   *  10년은 4.3375"]. 이 장부의 마크는 종가인데 데스크는 장중에 산다 — 지금 보는
   *  금리를 치면 서버가 그 값으로 다시 매겨 보내고, 이 칸이 무엇을 덮었는지 적는다.
   *  **장부엔 안 적힌다**(저장 경로가 없다). `null` 이면 종가로 보고 있는 것이다. */
  live?: { kind: string; tenor: string; level: number }[] | null;
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
    /** 묶음(트레이드) 수와 그중 들고 있는 수 — 사실 스트립이 읽는다(서버가 센다). */
    trades?: number;
    tradesOpen?: number;
    /** ★**제일 가까운 문** — 열린 묶음 중 청산·손절선에 제일 가까운 하나. 거리는
     *  계열 단위이고 0 이하면 이미 닿은 것이다. 화면이 묶음을 훑어 고르지 않게
     *  서버가 고른다(§16). 후보가 없으면 `null`. */
    nearest?: {
      key: string;
      label: string;
      series: string | null;
      kind: 'stop' | 'exit';
      gap: number;
      unit: string | null;
    } | null;
    /** **부호를 지고** 더한 DV01 — 페이와 리시브가 상쇄되는 것이 이 북의 알맹이다. */
    netDv01: number;
    grossDv01: number;
    /** 들고 있는 다리의 명목 합(원). */
    openNotional: number;
    /** ★묶음(트레이드) 소계 [OWNER 2026-09-28 — "각 트레이드 별과 포트폴리오 전체"].
     *  **서버가 센다**(§16) — 화면은 이 차례로 줄을 세우고 수를 읽기만 한다. */
    groups: PaperPositionGroup[];
  };
  /** 이 화면이 실제로 묻는 물음 — 내 판단이 규칙보다 나은가. */
  diff: { today: number; cum: number };
  failed: { id: string; why: string }[];
}

/** 묶음(트레이드) 하나의 소계 — `backend/app/paper.py::sum_legs`. 규율은 합계와
 *  같다: 한 다리라도 못 매겼으면 `pnl` 은 `null`, 매겨진 것만의 소계는 `scoredPnl`. */
export interface PaperPositionGroup {
  key: string;
  label: string;
  total: boolean;
  /** 이 묶음의 다리 번호들 — 표의 줄 차례가 이것이다. */
  legs: number[];
  open: number;
  closed: number;
  pnl: number | null;
  scoredPnl: number | null;
  scored: number;
  pending: number;
  netDv01: number;
  grossDv01: number;
  openNotional: number;
  /** 조건 없는 **열린** 다리 수 — 그 묶음에 청산선이 안 서는 다리가 몇인가.
   *  화면이 다리를 세지 않게 서버가 센다(§16). */
  unconditioned?: number;
  /** ── 묶음의 **계열 시선** [OWNER 2026-09-28 — "묶음으로 지금 얼마나 벌어져있는지
   *  왜 안알려줘?"]. 다리 줄이 다리의 금리를 말하면 묶음 줄은 계열 값을 말한다.
   *  전체 줄(화면이 `position` 에서 옮겨 적는 것)에는 없다 — 계열이 하나가 아니다. */
  series?: string | null;
  /** 계열 시선을 못 세운 사유(계열 없음 · 계열이 갈림 · 못 읽음). */
  seriesWhy?: string | null;
  unit?: string | null;
  asof?: string | null;
  /** 계열의 지금 값(계열 단위). */
  now?: number | null;
  entryT?: string | null;
  entryV?: number | null;
  /** 내 레벨 — 내 체결로 만든 진입 스프레드(`fill`)거나, 못 세우면 진입일 종가(`close`). */
  myLevel?: number | null;
  myBasis?: 'fill' | 'close' | null;
  /** 지금 − 내 레벨 (계열 단위) — 「얼마나 벌어졌나」. */
  delta?: number | null;
  /** 계열 값이 **장중 레벨** 위에 섰는가 — 다리가 전부 덮였을 때만 참이다. */
  live?: boolean;
  /** 묶음의 조건(조건 있는 첫 다리) · 다리마다 다르면 `knobsMixed`. */
  knobs?: PaperLegKnobs | null;
  knobsMixed?: boolean;
  /** 계열 밴드 — z·닿음·계열의 청산·손절 레벨(`mine` 은 없다). */
  track?: PaperLegTrack | null;
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

/**
 * 청산·손절 **추적** [OWNER 2026-09-23 — "청산이랑 손절 추적할 수 있게"].
 *
 * 판정은 **엔진의 문을 그대로** 옮긴 것이다(`backend/app/paper.py::track_leg`):
 * 손절 `|z| ≥ stopZ`(방향 무관) · 청산은 교차선이고 방향을 본다 · **손절이
 * 먼저** 이름을 갖는다. 장부가 제 규칙으로 판정하면 이 데스크에 청산선이 둘이
 * 된다.
 *
 * 방향은 **진입일 z 의 부호**가 정한다 — 엔진에서 「아래에서 들어갔다」가 곧
 * 진입 봉 z 가 음수라는 뜻이다. 다리에 방향을 따로 안 적는 이유이기도 하다
 * (적으면 화면이 방향을 두 번 정의한다).
 */
export interface PaperLegTrack {
  series: string;
  /** 지금 z. 못 재면 `null` 이고 `why` 가 사유를 진다. */
  z: number | null;
  /** 진입일의 z — 방향의 근거라 화면이 같이 적는다. */
  entryZ: number | null;
  /** +1 = 아래에서 들어감(롱) · −1 = 위에서. */
  dir: number | null;
  /** 이 판정이 선 날(계열의 마지막 관측). */
  asof: string | null;
  /** `stop` · `exit` · 아직이면 `null`. */
  hit: 'stop' | 'exit' | null;
  /** 못 잰 사유. 「안 닿았다」와 **다른 말**이라 칸이 따로 있다. */
  why: string | null;
  /** ── 레벨 [OWNER 2026-09-28 — "언제 손절, 익절인지 레벨로 표시"] ──────────
   *  z 의 두 문을 **오늘 밴드의 값**으로 푼 것(`중심선 ± 배수·σ`, 계열의 자기
   *  단위). 방향은 진입일 z 의 부호라 진입한 쪽의 선 하나씩이다. 중심선과 σ 가
   *  매일 움직이므로 두 수도 매일 바뀐다. 못 재면 전부 `null`. */
  unit: string | null;
  /** 지금 값 · 중심선 · σ. */
  v: number | null;
  ma: number | null;
  sd: number | null;
  exitLevel: number | null;
  stopLevel: number | null;
  /** 거리(계열 단위). **살아 있으면 양수** — 0 이하는 닿은 것이고 `hit` 와 같은 말. */
  exitGap: number | null;
  stopGap: number | null;
  /** 두 문 중 **가까운 쪽** — 화면이 둘을 견줘 고르지 않게 서버가 고른다(§16).
   *  같으면 손절이 이름을 갖는다(엔진의 우선순위). */
  nearest: { kind: 'stop' | 'exit'; gap: number } | null;
  /** ★**내 다리의 레벨** [OWNER 2026-09-28 — "각각 레벨로 적어줘야지 2년이면 3.xx
   *  에서 얼마, 10년이면 4.xx 에서 얼마"]. 계열 값 = scale × Σ w·r 이므로 **다른
   *  다리를 지금 값에 둔 채** 이 다리만 움직여 계열이 그 선에 닿는 레벨(%)과, 그
   *  레벨에서 걷을 때의 이 다리 손익(왕복 비용). 내 계기가 계열의 다리가 아니면
   *  `null` 이고 `mineWhy` 가 사유를 진다 — 그때 화면은 계열 값으로 적는다. */
  mine: {
    name: string;
    w: number;
    exitLevel: number;
    stopLevel: number;
    exitPnl: number;
    stopPnl: number;
    /** 고정해 둔 나머지 다리와 그 지금 값 — 가정을 수와 같이 싣는다. */
    others: { name: string; v: number }[];
    /** 내 다리가 계열의 진입 방향과 **같은 쪽**인가. 어긋나면 「청산」 레벨에서 이
     *  다리는 손해다 — 사실이라 지우지 않고 화면이 ⚠ 로 적는다. */
    aligned: boolean | null;
  } | null;
  mineWhy: string | null;
  /** 진입일의 계열 값 — 묶음 줄의 Δ 근거. */
  entryV: number | null;
  /** 오늘의 계열 다리 표(이름 · 만기 · 계기 · 부호 · 지금 값). 못 세우면 `null`. */
  legsNow: { name: string; tenor: string; kind: string; w: number; v: number }[] | null;
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
  /** 이 다리가 속한 **계열**(`BSS-2Y` …). 묶음과 **다른 칸**이다 — 묶음은 부르는
   *  이름이고 산술에 안 쓴다. 추적은 계열의 z 로 하므로 이 칸이 있어야 선다. */
  series: string | null;
  /** 조건을 **뒤에 붙인 날**(`attachKnobs`). 담을 때 얼린 다리엔 없다 — 있으면
   *  「그날의 조건」이 아니라 「뒤에 붙인 조건」이라는 뜻이고 화면이 그 날을 적는다. */
  knobsAt?: string | null;
  /** 얼린 조건으로 **지금** 닿았는가. 들고 있는 다리에만 서고, 못 잴 때도 같은
   *  모양으로 온다(`why` 에 사유). */
  track: PaperLegTrack | null;
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
  /** 이 마크가 **장중 레벨**인가(내가 친 값) — 종가가 아니라는 사실은 수와 같이 간다. */
  live?: boolean;
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
  /** 고를 수 있는 계열 — **서버가 낸다**. 화면이 제 손으로 적으면 없는 계열을
   *  고를 수 있게 되고, 그 다리는 영원히 추적이 안 된다. */
  series?: { id: string; label: string }[];
  asof: string | null;
  kinds: {
    kind: 'irs' | 'bond' | 'fut';
    label: string;
    tenors: string[];
    sides: { v: string; label: string }[];
    why?: string;
  }[];
}

export async function fetchPaper(marks?: string): Promise<PaperSheet> {
  const r = await fetch(paperUrl(marks));
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
  /** 이 다리가 속한 계열. 주면 청산·손절 추적이 선다. */
  series?: string;
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

/** 조건이 **없던** 다리에 조건을 붙인다 [OWNER 2026-09-28]. 이미 언 다리·닫힌
 *  다리·반쪽 조건은 서버가 422 로 거절한다(「다시 고르지 않는다」 규율). 붙인
 *  날이 `knobsAt` 에 남는다 — 그날의 조건이 아니라 뒤에 붙인 조건임을 장부가
 *  말한다. 숫자는 `addLeg` 와 같은 이유로 **글자 그대로** 보낸다. */
export const attachKnobs = (
  n: number,
  knobs: Partial<Record<keyof PaperLegKnobs, string | number | undefined>>,
  series?: string,
) => post(paperLegKnobsUrl(), { n, knobs, ...(series ? { series } : {}) });

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


/**
 * 그날의 1등 [OWNER 2026-09-23 — "들어간 시점에서의 최적 파라미터로" → 선택지에서
 * 「손으로 치되 1등을 제안」].
 *
 * 다리를 담을 때 그 계열을 **진입일까지의 자료로** 격자(계획면과 같은 162칸)에
 * 돌린 순위다. 고르지 않는다 — 장부는 여전히 내가 친 조건을 얼고, 이 표는 옆에
 * 서기만 한다(`backend/app/paper.py::suggest`).
 *
 * ⚠ `inSample` — 고른 창에서 잰 순위라 **성과가 아니라 선택의 산물**이다(PBO
 * 레인의 그 경고). 화면은 「1등」 옆에 반드시 그 문장을 세운다 — 「1등」이라고만
 * 적으면 고르라는 말로 읽힌다.
 *
 * 순위는 **서버가 매긴다**(`rank`). 화면은 내 조건을 `list` 에서 **찾기만** 한다
 * (`findCell`) — 여기서 다시 정렬하면 두 번째 정의가 생긴다.
 */
export interface PaperSuggestCell extends PaperLegKnobs {
  rank: number;
  cdarRatio: number | null;
  totalPnl: number | null;
  maxDrawdown: number | null;
  /** 1년 창은 계열당 거래가 0~5건이라 순위가 잡음일 수 있다 — 화면이 같이 적는다. */
  numTrades: number | null;
  winRate: number | null;
}

export interface PaperSuggest {
  series: string;
  label: string;
  entry: string;
  /** 격자가 본 마지막 봉 — 진입일 이하의 마지막 관측. `null` 이면 재료가 없었다. */
  asof: string | null;
  from: string | null;
  days: number;
  span: string;
  rankKey: string;
  inSample: boolean;
  cells: number;
  ranked: number;
  /** 1등. 못 냈으면 `null` 이고 `why` 가 사유를 진다 — 「없다」와 「못 잰다」는 다른 말. */
  top: PaperSuggestCell | null;
  list: PaperSuggestCell[];
  why: string | null;
}

export async function fetchSuggest(
  series: string, entry: string, signal?: AbortSignal,
): Promise<PaperSuggest> {
  const r = await fetch(paperSuggestUrl(series, entry), { signal });
  /* 404 는 **옛 백엔드**다 — 라우트를 모르는 판. 조용히 빈 줄을 두면 「제안이
     없는 날」과 구별이 안 된다(규약이 어긋난 채 배포하면 조용히 사라진다 — 인계문). */
  if (r.status === 404) throw new BacktestUnavailable();
  if (!r.ok) {
    const detail = (await r.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `suggest: HTTP ${r.status}`);
  }
  return r.json() as Promise<PaperSuggest>;
}

/** 내 조건이 격자의 어느 칸인가 — **찾기만** 한다.
 *
 *  칸은 글자로 온다(`addLeg` 의 그 규율). `Number()` 로 같은지 보되, 하나라도
 *  비거나 숫자가 아니면 `undefined` 다 — 반쪽 조건은 칸이 아니다. 프리셋 밖의
 *  값(룩백 45)도 `undefined` 다: 격자는 화면이 고를 수 있는 값 위에서만 돈다
 *  (`_mr_optimize` 머리). 그 둘은 부르는 쪽이 갈라 적는다. */
export function findCell(
  list: PaperSuggestCell[],
  knobs: Partial<Record<keyof PaperLegKnobs, string | number | undefined>> | undefined,
): PaperSuggestCell | undefined {
  if (!knobs) return undefined;
  const num = (v: string | number | undefined): number =>
    v === undefined || String(v).trim() === '' ? NaN : Number(v);
  const lb = num(knobs.lookback);
  const ez = num(knobs.entryZ);
  const xz = num(knobs.exitZ);
  const sz = num(knobs.stopZ);
  if (![lb, ez, xz, sz].every(Number.isFinite)) return undefined;
  return list.find((c) =>
    c.lookback === lb && c.entryZ === ez && c.exitZ === xz && c.stopZ === sz
    && c.entryMode === knobs.entryMode);
}

/** 다섯 칸이 다 찼는가 — 「내 조건은 몇 등」을 적어도 되는 순간이다.
 *  반쪽이면 등수도 「프리셋 밖」도 적지 않는다(둘 다 없는 사실이다). */
export function knobsComplete(
  knobs: Partial<Record<keyof PaperLegKnobs, string | number | undefined>> | undefined,
): boolean {
  if (!knobs) return false;
  return (['lookback', 'entryZ', 'exitZ', 'stopZ'] as const)
    .every((k) => knobs[k] !== undefined && String(knobs[k]).trim() !== '');
}

/**
 * 트레이드 추적 [OWNER 2026-09-28 — "그 트레이드를 클릭했을 때 진입일 시점부터
 * PnL 을 분해시켜서 트레이스가 가능하게"].
 *
 * 이 장부의 손익은 한 수(rateSign × Δbp × DV01 − 비용)라 분해가 없다. 분해는
 * **백테스트 엔진**이 이미 한다 — 다리들을 그 엔진의 포지션으로 옮겨 값매기고
 * (`book` 은 `/api/backtest` 응답 그대로), 두 자리의 진입가 차이를 「체결 차이」로
 * 이름 붙여 대조한다(`backend/app/paper.py` 트레이드 추적 절):
 *
 *     장부 손익 = 체결 차이 + 엔진 손익(평가+캐리+롤다운+개시+조달) − 비용 + 차이
 *
 * 「차이」는 장부의 선형(진입일 DV01 고정)과 엔진의 재평가가 갈리는 몫이다 —
 * 지우지 않고 열에 세운다. 없는 성분은 `null`(공란 정책).
 */
export interface PaperTraceRow {
  n: number;
  id: string | null;
  label: string | null;
  entry: string | null;
  exit: string | null;
  /** 내 체결 레벨(%) · 엔진이 친 진입일 종가(%). */
  level: number;
  entryClose: number | null;
  /** rateSign × (진입일 종가 − 내 레벨) × 100 × DV01. */
  exec: number | null;
  engine: number | null;
  valuation: number | null;
  carry: number | null;
  rolldown: number | null;
  startup: number | null;
  funding: number | null;
  cost: number | null;
  /** 화면 표의 그 줄 손익(`score_leg`). */
  paper: number | null;
  residual: number | null;
}

export interface PaperTrace {
  legs: number[];
  rows: PaperTraceRow[];
  /** 열마다의 합 — 한 줄이라도 못 센 열은 `null`. */
  total: Record<'exec' | 'engine' | 'valuation' | 'carry' | 'rolldown' | 'startup'
    | 'funding' | 'cost' | 'paper' | 'residual', number | null>;
  /** `/api/backtest` 응답 그대로 — Backtest 창의 부품이 그대로 읽는다. */
  book: BacktestResult;
  /** 묶음의 계열 시선(`group_series`) — 창 머리띠의 내 레벨·지금·Δ·z. */
  group: Pick<PaperPositionGroup,
    'series' | 'seriesWhy' | 'unit' | 'asof' | 'now' | 'entryT' | 'entryV'
    | 'myLevel' | 'myBasis' | 'delta' | 'knobs' | 'knobsMixed' | 'track'>;
  /** 계열의 **경로** [OWNER 2026-09-28 — "추적 … 정교화"] — 진입 앞 몇 봉부터
   *  오늘까지의 값과 그날그날의 중심선·청산선·손절선(`series_path`, `track_leg` 와
   *  같은 번역). 밴드가 안 선 봉은 `null` 이라 선이 끊긴다. 못 그리면 `why`. */
  path: {
    series: string | null;
    unit?: string | null;
    dates?: string[];
    values?: number[];
    ma?: (number | null)[];
    exit?: (number | null)[];
    stop?: (number | null)[];
    entryIdx?: number | null;
    dir?: number | null;
    why: string | null;
  };
}

export async function fetchTrace(ns: readonly number[], signal?: AbortSignal,
                                 marks?: string): Promise<PaperTrace> {
  const r = await fetch(paperTraceUrl(ns, marks), { signal });
  if (r.status === 404) throw new BacktestUnavailable();
  if (!r.ok) {
    const detail = (await r.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `trace: HTTP ${r.status}`);
  }
  return r.json() as Promise<PaperTrace>;
}
