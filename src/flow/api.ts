/* 투자자별 수급 — 서버 계약과 페처 [2026-10-19].
 *
 * **산술은 서버가 한다**(§16). 여기는 타입과 fetch 셋줄뿐이고, 화면은 읽고
 * 칠하기만 한다 — 영합 폐쇄·누적·편차·순위는 전부 `backend/app/flow.py` 에
 * 있고 그 머리에 근거가 적혀 있다.
 */

import { BacktestUnavailable } from '@/lib/api';
import { flowBoardUrl, flowHistoryUrl, flowIssuanceUrl, flowLabUrl } from '@/lib/staticPaths';

/** 면 둘. **단위가 달라 한 축에 못 겹친다**(계약 대 백만원) — 겹치는 그림이
 *  아니라 갈라지는 면인 이유다. */
export type FlowSide = 'fut' | 'cash';
export type FutTenor = '3Y' | '10Y';
/** 현물 만기물 — `ALL` 이 분리 전 화면과 같은 수다(`flow.py` §현물 만기물 ①). */
export type CashTenor = 'ALL' | '2Y' | '3Y' | '5Y' | '10Y' | '20Y' | '30Y' | '50Y' | '물가';
export type FlowTenor = FutTenor | CashTenor;
/** 이동평균 창(영업일). 0 은 끔. 서버의 `MA_WINDOWS` 와 같다. */
export type MaWindow = 0 | 5 | 20 | 60 | 120;

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
  /** 자기 과거 분포 대비 당일 편차. **창은 오늘을 뺀다**. 못 재면 `null`.
   *  ⚠**순위 키가 아니다** — 2026-10-21 부터 `pct` 가 그 자리다. 지우지 않은
   *  이유는 읽는 사람이 이미 보는 수이고 실험 창이 쓸 수 있어서다. */
  sigma: number | null;
  /** ★순위 키 — **백분위(0~100)**. 50 이 평소, 100 이 가장 큰 순매수.
   *
   *  σ 대신 이것인 까닭은 외부 관례(CFTC COT 를 읽는 그 자)와 같다 — 흐름은
   *  꼬리가 두껍고 비대칭인데 σ 는 분포를 가정하고, 백분위는 **0~100 에 갇혀**
   *  계약과 백만원이 한 눈금에 선다.
   *
   *  ⚠**꼬리 해상도를 잃는다** — 2.5σ 와 4σ 가 둘 다 99 대다. 꼬리의 크기가
   *  필요하면 같은 줄의 `d1` 과 `avgAbs` 를 본다.
   *  ⚠없을 수 있다(서버가 옛 코드일 때). */
  pct?: number | null;
  /** ★COT index — **0~100, 순포지션 위, 156주, min-max**(CFTC 관례 그대로).
   *
   *  위 `pct` 와 **다른 수**다. 저쪽은 「오늘 얼마나 샀나」의 1년 **순위**이고,
   *  이쪽은 「지금 얼마나 들고 있나」의 3년 **자리**다. 한 칸에 섞지 않는다.
   *  창(780봉)이 안 차면 `null`. ⚠없을 수 있다(서버가 옛 코드일 때). */
  cot?: number | null;
  /** ★그 수가 **이 주체에서 뜻이 있나**. 거짓이면 화면은 수준 대신 `pct` 를
   *  세운다 — 까닭은 서버 `_cot_usable` 머리에 있다(단조 축적 주체에서는
   *  수준 지표가 천장·바닥에 붙어 변별을 못 한다). */
  cotUsable?: boolean;
  /** 창 안에서 누적이 되돌아온 정도(0~1). 「왜 못 쓰나」를 화면이 말할 때 쓴다. */
  retrace?: number | null;
  /** 직전 252봉 일평균 |순매수| — 하한을 넘었나를 이 수가 정한다. */
  avgAbs: number;
  /** 하한 아래면 `false` 이고 **지우지 않는다**. */
  ranked: boolean;
  /** 순위 밖이면 `null` — 「없다」와 「0등」은 다른 말이다. */
  rank: number | null;
  /** ★지금 들고 있는 양 — **누적 순매수가 아니다**(그쪽은 시작일이 임의다).
   *
   *  ⚠**`null` 은 「0」이 아니라 「짝이 없다」**다. 딜러(금융투자)와 기금공제가
   *  그렇다 — 보유잔고표에 그 주체가 없다. 0 으로 그리면 「안 들고 있다」로
   *  읽힌다. 없을 수 있다(옛 서버). */
  hold?: {
    /** 백만원 — 흐름과 같은 자. */
    face: number;
    /** 그 만기물 **보유 합 대비 몫**. 분모가 없으면 큰 수인지 알 수 없다. */
    share: number | null;
    /** 한 잔고표가 흐름 **두 열**을 덮을 때 그 두 이름(보험기금). */
    merged: string[] | null;
  } | null;
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
  /** 일별 — 한 계열. 막대로 그린다(이산 일별값). 주체는 `daily` 질의가 고른다. */
  daily: FlowSeries | null;
  /** 일별 위에 서는 이동평균 — **서버가 낸다**(§16). 창 길이 미만 자리는 `null`. */
  ma: (FlowSeries & { window: number; values: (number | null)[] }) | null;
  /** ★창 **넷 전부** [OWNER 2026-10-20 — 「동시에 여러 MA도 보고 싶고 그런거야」].
   *
   *  가속은 창마다 다른 말을 한다 — 보험·30년물에서 Γ5 −948 · Γ20 −314 인데
   *  Γ60 +220 · Γ120 +321 이다. 짧은 쪽은 식고 긴 쪽은 빨라진다는 그 사실이
   *  네 선을 **같이 봐야** 보인다. 차례가 곧 진하기 배정이다(짧을수록 흐리다). */
  /** ⚠**없을 수 있다** — 프런트가 서버보다 새로울 때(배포는 즉시, 백엔드는
   *  30분 주기 재기동). 읽는 쪽이 `?? []` 로 받는다. */
  mas?: (FlowSeries & { window: number; values: (number | null)[] })[];
  /** ★선물 가격 — 흐름 혼자서는 안 읽힌다(외부 관례의 그 짝).
   *
   *  ⚠**수준에 뜻이 없다**(후방 조정 연속 계열) — 모양과 방향만 읽는 선이고,
   *  그래서 **보조축**에 세우고 리드아웃에도 값을 안 싣는다. 현물 면은 `null`.
   *  ⚠없을 수 있다(위 `mas` 와 같은 까닭). */
  price?: FlowSeries | null;
  /** ★미결제약정 — **시장 전체**다(주체별이 아니다). 현물 면은 `null`. */
  oi?: FlowSeries | null;
}

/** 가격 × 미결제약정 2×2 — 선물 면에서만 선다(현물엔 미결제가 없다).
 *
 *  선물 데스크의 1차 판독이다. 같은 순매수가 **새 포지션**인지 **되돌림**인지를
 *  순매수 혼자서는 말하지 못하고, 미결제의 방향이 그것을 가른다.
 *
 *  ⚠**시장의 말이고 한 주체의 포지션이 아니다** — 미결제는 시장 전체 한 수다.
 *  「누가」는 옆의 순위표가 진다. */
export interface FlowOi {
  asof: string | null;
  /** 가격 Δ. ⚠수준은 안 온다 — 뜻이 없어서 서버가 아예 안 싣는다. */
  dClose: number;
  dOi: number;
  oi: number;
  volume: number | null;
  /** 네 이름 중 하나. **한쪽이 0 인 날은 `null`** — 「안 움직였다」는 네 칸
   *  어디도 아니다. */
  regime: string | null;
  span: number | null;
  /** 이름이 선 봉 수 = 집계의 **분모**. `span` 보다 작을 수 있다. */
  counted: number;
  tally: Record<string, number>;
  priceNote: string;
}

/** 발행시장 인수 보정이 켜졌을 때의 사실. 꺼져 있으면 `null`. */
export interface FlowPd {
  /** 금융투자 몫(0~1). 은행은 나머지. **가정**이다. */
  share: number;
  /** 올해 더한 공급 합(백만원). */
  supplyYtd: number;
  /** 현물 자료가 아직 그 날에 안 닿아 반영 못 한 입찰 건수. */
  pending: number;
  asof: string | null;
  note: string;
}

/** 테너 × (발행 + 주체) 한 표 [OWNER 2026-10-20].
 *
 *  칸은 **고른 구간의 합**(백만원)이고, `total` 은 열마다의 합이다 — `ALL`
 *  바구니와 같은 수여야 한다(`test_flow` 가 맞댄다). 구간은 화면이 그림을
 *  자르는 봉 수(`SPAN_BARS`)를 서버에 그대로 넘겨 맞춘다. */
export interface FlowMatrixBoard {
  /** 합한 봉 수. */
  span: number;
  from: string | null;
  to: string | null;
  /** `pd` 가 참인 열은 **가정이 섞인 칸**이다 — PD 노브가 켜지면 금융투자·은행에
   *  공급을 비율로 더하므로 「실제로 산 수」가 아니다. 표가 그 사실을 적어야 한다. */
  cols: { key: string; label: string; pd: boolean }[];
  rows: { key: CashTenor; label: string; supply: number; cols: Record<string, number> }[];
  /** ★장기 합산 줄 — **서버가 더한다**(`flow.py::LONG_FOLD_KEYS`).
   *
   *  화면은 더하지 않는다(§16 · `guards/strategy-flow`). 토글이 켜지면 `of` 의
   *  줄들을 빼고 이 줄을 그 자리에 끼운다. 열쇠(`LONG`)는 **고를 수 있는 만기물이
   *  아니다** — 고르기는 `ALL` 로 간다. 접을 줄이 둘 미만이면 `null`. */
  fold?: {
    key: string; label: string; supply: number;
    cols: Record<string, number>;
    /** 이 줄이 접은 만기물들. */
    of: CashTenor[];
  } | null;
  total: { label: string; supply: number; cols: Record<string, number> };
  /** 현물 자료가 그 날에 아직 안 닿아 발행 열에 못 얹은 입찰 건수. */
  pending: number;
  /** 표가 닫혔나 — 주체 합은 PD 끔이면 0, 켬이면 발행과 같아야 한다. 서버가 센다. */
  check: {
    sum: number;
    ok: boolean;
    pd: boolean;
    /** 반올림으로 설명이 안 되는 날들(큰 것부터 최대 다섯). */
    breaks: { date: string; amount: number }[];
    say: string;
  };
}

/** 눈금 둘. `native` 가 원천(계약·백만원), `dv01` 이 덧눈금(원/bp).
 *
 *  금리 데스크는 흐름을 계약수로 적지 않는다 — 3년 한 계약 28,562원/bp 와
 *  10년 84,134 는 **2.95배** 다르므로 환산 없이는 만기물을 더할 수 없다. */
export type FlowUnit = 'native' | 'dv01';

export interface FlowBoard {
  side: FlowSide;
  tenor: FlowTenor | null;
  /** ★**둘이 다른 것이 정상**이다 — 현물이 늦게 들어온다 [OWNER 2026-10-19].
   *  화면이 둘을 따로 적어야 하고, 어긋나는 것은 경고가 아니다. */
  asof: { fut: string | null; cash: string | null };
  /** 화면이 쓸 단위 낱말 — 「계약」·「백만원」·「원/bp」. */
  unit: string;
  /** ★어느 눈금인가. ⚠`unit='dv01'` 로 물었는데 배수를 못 읽으면 서버가
   *  **원단위로 떨어지고** 이 값이 `native` 로 온다 — 화면이 손잡이를 그 자리로
   *  되돌려야 읽는 사람이 원/bp 라고 믿지 않는다. 없을 수 있다(옛 서버). */
  unitKey?: FlowUnit;
  /** 그 눈금의 한계 한 줄(환산 원천·커브 없는 구간·행렬은 금액 그대로).
   *  원단위에서는 `null`. */
  unitNote?: string | null;
  days: number;
  /** 현물면은 **빈 배열**이다 — 상위 집합이 없으니 대조 칸도 없다. */
  top: FlowTop[];
  sub: FlowRow[];
  rankFloor: number;
  series: FlowChart;
  /** ★가격 × 미결제 2×2 — **선물 면에서만** 선다. 현물은 `null`(미결제가 없다).
   *  ⚠없을 수 있다(서버가 옛 코드일 때) — 읽는 쪽이 `?? null` 로 받는다. */
  oi?: FlowOi | null;
  /** ★보유잔량 머리 — `asof` 와 그 측정의 성질. 원천을 못 읽거나 선물 면이면
   *  `null` 이고 화면이 보유 칸을 **안 세운다**. */
  hold?: { asof: string | null; note: string | null } | null;
  /** 현물 면의 테너 × (발행 + 주체) 표. 선물 면은 `null`. */
  matrix: FlowMatrixBoard | null;
  /** 그림에 선 주체의 **감마 한 줄** — 속도의 변화다. 선물 면은 `null`.
   *
   *  ★순매수의 **부호에는 정보가 거의 없다**(60일 MA 양수 비중이 보험·30년물
   *  100%). 잔액이 늘고 회계가 영합이라 PD 가 내놓는 것을 나머지가 늘 받기
   *  때문이다. 감마는 양수 비중 44~57% 라 **부호가 산다** — 「사나 파나」가
   *  아니라 「빨라지나 느려지나」가 진짜 질문이다(`flow.gamma` 머리). */
  gamma: {
    key: string;
    rows: {
      window: number;
      /** 그 창의 하루 평균 순매수(백만원/일). 창이 안 차면 `null`. */
      speed: number | null;
      /** `MA_n(t) − MA_n(t−n)`. 창 하나만큼 떨어진 두 평균의 차. */
      gamma: number | null;
      /** 「잡음」·「보통」·「믿을 만」 — 부호가 얼마나 오래 버티나의 실측 판정. */
      trust: string;
    }[];
    say: string;
    tone: 'up' | 'down' | null;
    note: string;
  } | null;
  /** 현물 면에서 노브가 켜졌을 때만. 선물 면은 `null`. */
  pd: FlowPd | null;
  /** 현물 면의 만기물 선택지. 선물 면은 `null`. */
  tenors: { key: CashTenor; label: string }[] | null;
  excluded: { id: string; label: string; why: string }[];
  /** 「무엇을 보고 있나」를 **서버가** 말한다. 화면이 지어내지 않는다. */
  basis: string;
}

/** `/api/flow/board` 의 손잡이 — 서버 질의와 1:1. */
export interface FlowQuery {
  side: FlowSide;
  tenor: FlowTenor;
  /** 금융투자 몫(0~1). 없으면 보정 안 함. 현물에서만 뜻이 있다. */
  pdShare?: number | null;
  ma?: MaWindow;
  /** 일별 그림에 세울 주체 열쇠. 없으면 그림 첫 계열. */
  daily?: string | null;
  /** 행렬이 합할 마지막 봉 수(`SPAN_BARS`). 없거나 `Infinity` 면 전구간. */
  span?: number | null;
  /** 눈금. 없으면 `native`(원천). */
  unit?: FlowUnit;
}

/* ── 「발행」 면 (`backend/app/ktb_issuance.py`) ───────────────────────────── */

/** 같은 날·같은 만기물 경쟁입찰 묶음 하나 — 교체기엔 두 종목이 한 덩이다. */
export interface IssuanceUnit {
  date: string;
  tenor: string | null;
  label: string;
  names: string[];
  legs: number;
  /** 낙찰 합(백만원). */
  amount: number;
  ratio: number | null;
  rate: number | null;
  /** 직전 같은 만기물 입찰 대비 bp. */
  rateDelta: number | null;
  prevDate: string | null;
  /** 「강한 수요」…「표본 부족」 — `issuance_strength` 의 그 등급. */
  grade: string | null;
  pct: number | null;
  median: number | null;
  tone: string | null;
  n: number | null;
  totPct: number | null;
  totMed: number | null;
  why: string | null;
  notes: string[];
}

export interface IssuanceTenorRow {
  key: string;
  label: string;
  last: IssuanceUnit | null;
  /** 올해 경쟁 낙찰 합(백만원). */
  ytd: number;
  ytdNoncomp: number;
  ytdBuyback: number;
  ytdCount: number;
  /** 작년 같은 날까지의 경쟁 낙찰 합. */
  ytdPrev: number;
  mtd: number;
}

export interface IssuanceBoard {
  asof: { auction: string; updated: string | null };
  unit: string;
  since: string;
  count: number;
  latest: IssuanceUnit;
  next: { date: string; tenor: string | null; label: string; name: string | null;
    planned: number | null; source: string }[];
  tenors: IssuanceTenorRow[];
  year: { label: string; comp: number; noncomp: number; buyback: number; compPrev: number };
  series: FlowChart;
  pd: { defaultShare: number; kinds: string[]; note: string };
  excluded: { id: string; label: string; why: string }[];
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

export function flowQueryString(q: FlowQuery): string {
  const parts = [`side=${q.side}`, `tenor=${encodeURIComponent(q.tenor)}`];
  if (q.side === 'cash' && q.pdShare != null) parts.push(`pd=${q.pdShare}`);
  if (q.ma) parts.push(`ma=${q.ma}`);
  if (q.daily) parts.push(`daily=${encodeURIComponent(q.daily)}`);
  /* `Infinity`(구간 「전체」)는 **안 싣는다** — 숫자가 아니라 `span=Infinity` 라는
     글자로 나가서 서버가 거절한다. 빼면 서버 기본이 전구간이라 뜻이 같다. */
  if (q.span != null && Number.isFinite(q.span)) parts.push(`span=${q.span}`);
  /* 기본값은 **안 싣는다** — 캐시 열쇠를 같게 두려고(옛 주소와 한 글자도 안 갈린다). */
  if (q.unit && q.unit !== 'native') parts.push(`unit=${q.unit}`);
  return parts.join('&');
}

export async function fetchFlowBoard(q: FlowQuery, signal?: AbortSignal): Promise<FlowBoard> {
  return get(flowBoardUrl(flowQueryString(q)), 'flow', signal);
}

export async function fetchIssuanceBoard(signal?: AbortSignal): Promise<IssuanceBoard> {
  return get(flowIssuanceUrl(), 'flow-issuance', signal);
}

export async function fetchFlowHistory(
  key: string, side: FlowSide, tenor: FlowTenor,
): Promise<FlowHistory> {
  return get(flowHistoryUrl(key, `side=${side}&tenor=${tenor}`), 'flow-history');
}

/* ── 수급 신호 실험 (`backend/app/flowlab.py`) ────────────────────────────── */

/** 실험 한 판 — 고른 칸 + **그 칸의 우연** + **탐색의 우연**.
 *
 *  ★셋이 같이 오는 것이 이 라우트의 존재 이유다. 수 하나만 보면 사람은 그것을
 *  실력으로 읽는데, 같은 크기의 탐색을 가짜 자료에 돌리면 우연의 1등이 그만큼
 *  낸다. 2026-10-20 판정에서 **내가 정확히 그렇게 한 번 틀렸다**. */
export interface FlowLab {
  subject: string;
  subjectLabel: string;
  tenor: string;
  tenorLabel: string;
  target: string;
  short: number;
  long: number;
  hold: number;
  from: string;
  to: string;
  costBp: number;
  dv01: number;
  /** 공표 지연(영업일) — 자료 사실이지 손잡이가 아니다. */
  lag: number;
  dates: string[];
  result: { total: number; mdd: number; calmar: number | null; trades: number; bars: number };
  cum: number[];
  byYear: { year: string; pnl: number; share: number | null }[];
  /** ① **그 칸**의 우연. `p` 가 그 칸의 정직한 세기다. */
  shuffle: { draws: number; median: number | null; p95: number | null; p: number | null };
  /** ② **탐색**의 우연. `beat` = 가짜 탐색의 1등이 이 칸을 이긴 몫. */
  searchCeiling: {
    cells: number; draws: number;
    median: number | null; p95: number | null; beat: number | null;
  };
  grid: { shorts: number[]; longs: number[]; holds: number[]; targets: string[] };
  subjects: { key: string; label: string }[];
  tenors: { key: string; label: string }[];
  basis: string;
  warn: string;
}

export interface FlowLabQuery {
  subject: string;
  tenor: string;
  target: string;
  short: number;
  long: number;
  hold: number;
}

export async function fetchFlowLab(q: FlowLabQuery, signal?: AbortSignal): Promise<FlowLab> {
  const qs = `subject=${encodeURIComponent(q.subject)}&tenor=${encodeURIComponent(q.tenor)}`
    + `&target=${q.target}&short=${q.short}&long=${q.long}&hold=${q.hold}`;
  return get(flowLabUrl(qs), 'flow-lab', signal);
}
