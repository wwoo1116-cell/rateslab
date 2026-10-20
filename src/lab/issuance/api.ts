/* 발행 캘린더가 서버와 주고받는 둘 — 달과 하루.
 *
 * CSV 가 원천이라 굽기에 실을 수 없다. 수집기가 평일 5분마다 새로 쓰고, 서버는
 * mtime 을 캐시 키로 써서 다음 요청 때 알아서 읽는다. 백엔드가 없거나 CSV 경로가
 * 안 잡히면 화면이 그 사실을 말한다 — 백테스트·시뮬과 같은 규약이다.
 */

import { issuanceCalendarUrl, issuanceDayUrl } from '@/lib/staticPaths';
import { ROUTE_MISSING_DETAIL } from '@/lib/apiBase';

export class IssuanceUnavailable extends Error {
  constructor(detail?: string) {
    super(detail ?? ROUTE_MISSING_DETAIL);
    this.name = 'IssuanceUnavailable';
  }
}

/** 달력 한 칸. 섹터 합계를 서버가 미리 더하지 않는다 — 화면의 섹터 필터가 달력을
 * 실제로 바꾸려면 하루치가 섹터별로 갈려 있어야 한다. */
export type CalDay = {
  d: number;
  iso: string;
  /** 0=월 … 4=금. 토·일은 애초에 안 온다. */
  dow: number;
  /** 영업일인가. 비영업일도 자리는 지킨다 — 빠지면 요일이 어긋난다. */
  biz: boolean;
  past: boolean;
  today: boolean;
  /** 섹터 → 조원. */
  isec: Record<string, number>;
  /** 섹터 → 건수. */
  isn: Record<string, number>;
  /** 그날의 일정. `dir` 은 **재료가 미는 쪽**이지 시장의 반응이 아니다 —
   * 이미 반영된 재료는 반대로 간다(페이로드의 `BIAS_IS_THE_MATERIAL`).
   * `null` 은 «중립» 이 아니라 «잰 것이 없다» 다(그날 경쟁입찰이 없었다). */
  ev: { lane: string; label: string; dir: Dir | null }[];
};

export type CalMonth = {
  /** 5열 격자의 앞 여백. 1일이 토·일이면 그 이틀은 빠졌으므로 0 이다. */
  lead: number;
  days: CalDay[];
};

export type IssuanceCalendar = {
  months: Record<string, CalMonth>;
  order: string[];
  sectors: { k: string; v: number; n: number; fin: boolean }[];
  today: string;
  /** 발행 공시가 닿는 마지막 날. 그 뒤의 빈칸은 «없음» 이 아니다. */
  issuanceThrough: string | null;
  /** 국고채 입찰 **결과**가 나온 마지막 날. 앞날의 예정은 이 판에 없다. */
  auctionThrough: string | null;
  caveats: string[];
};

/** 채권의 «강세» 는 금리가 내리는 것이다 — 주식의 반대다. 이 앱에서 파랑이
 * 하락 전용이라 강세가 파랑, 약세가 빨강이 된다. */
export type Dir = '강세' | '약세' | '중립' | '양방향';

/** 방향 하나. **근거 없이 방향만 오지 않는다** — 그러면 그건 점괘다. */
export type Bias = { dir: Dir; why: string };

/** 종목·조작의 성격에 걸리는 «설명 + 방향» 한 벌.
 *
 * **둘이 한 벌인 이유:** 따로 오면 화면이 설명 문단과 방향 문단을 각각 그리고,
 * 둘이 같은 사실을 말하므로 같은 문단이 두 번 찍힌다(실측 2026-08-21). */
export type EventNote = { key: string; text: string; dir: Dir | null };

/** 레인의 원문 출처. **원본이 화면 바닥에 한 줄씩 적던 것**이고, v2 는 그걸
 * 빼먹은 채로 판정만 보여 주고 있었다 — «약한 수요» 라는 말은 있는데 그 숫자가
 * 어느 공고에서 왔는지가 없었다. */
export type Src = { who: string; what: string; url: string };

/** 발행 당시 민평 대비. **잣대는 등급 커브지 개별종목 민평이 아니다** — 이
 * 데이터에 종목 단위 시가평가가 없어서, 화면이 커브 이름을 같이 적는다.
 *
 * `side` 가 `null` 인데 `bp` 가 있으면 «숫자는 냈지만 판정은 안 낸다» 는 뜻이다
 * (등급이 커브와 다른 경우). `bp` 까지 없으면 `why` 가 못 잰 이유를 든다. */
export type Versus = {
  /** 잣대의 이름. 등급이 박혀 있다 — "은행채 AAA" · "카드채 AA+". */
  curve?: string;
  /** 이 종목의 등급. 입찰(국고)에는 없다. */
  grade?: string | null;
  /** 등급이 커브와 같은가. 다르면 오버·언더라고 부르지 않는다. */
  match?: boolean;
  years?: number;
  /** 민평 수익률, 퍼센트. */
  rate?: number;
  /** 그 민평이 선 날. 그날 것이 없으면 직전 관측이다. */
  asof?: string;
  /** 발행금리 − 민평, bp. */
  bp?: number;
  side: '오버' | '언더' | '민평' | null;
  why?: string | null;
  /** 외평채처럼 잣대에 곁들일 말이 있을 때. */
  note?: string | null;
};

/** 공개시장운영 하루치 판정. 방향이 주 신호, 규모·응찰배율·스프레드가 근거다. */
export type OmoStrength = {
  dir: string;
  kind: string;
  won: number;
  legs: number;
  rate: number | null;
  size: string | null;
  sizePct: number | null;
  sizeMed: number | null;
  cover: number | null;
  coverMed: number | null;
  spread: number | null;
  base: number | null;
  grade: string;
  notes: string[];
};

/** 같은 연물 52주와 견준 판정. 표본이 모자라면 등급 대신 그렇다고 말한다. */
export type Strength = {
  grade: string;
  tone?: string | null;
  label?: string | null;
  /** 응찰률 백분위. `null` 이면 표본 부족이라 등급을 안 낸 것이다. */
  pct: number | null;
  median?: number | null;
  why?: string | null;
  legs?: number;
  tot?: number | null;
  ratio?: number | null;
  wavgDelta?: number | null;
  prevDate?: string | null;
  totMed?: number | null;
  partMed?: number | null;
  notes?: string[];
};

/** 레인 하나가 무엇이고 왜 보는지. **서버가 문장의 단일 출처**라 화면은 그대로
 * 출력만 한다 — 프런트에 문장을 두면 두 벌이 되고 한쪽만 고치면 조용히 갈린다. */
export type Gloss = {
  title: string | null;
  what: string | null;
  why: string | null;
  note: string | null;
  extra: string[];
  /** 이 레인이 금리를 어느 쪽으로 미나. 결과가 정하는 레인은 «양방향» 이다. */
  bias: Bias | null;
  /** 방향을 적는 자리마다 따라가는 한 줄 — 재료의 방향과 시장의 반응은 다르다. */
  biasCaveat: string | null;
};

export type IssuanceDay = {
  date: string;
  gloss: { iss: Gloss; ktb: Gloss; omo: Gloss; mpc: Gloss };
  issuing: {
    issuer: string;
    sector: string;
    round: string | null;
    /** 억원. */
    eok: number;
    coupon: number | null;
    maturity: string | null;
    rating: string | null;
    stage: string | null;
    report: string | null;
    rcept: string | null;
    /** 그때 그 금리가 시장보다 오버였나 언더였나. 기준일은 **제출일**이다. */
    mp: Versus | null;
  }[];
  auctions: {
    kind: string;
    name: string;
    code: string | null;
    offered: number | null;
    bid: number | null;
    ratio: number | null;
    allotted: number | null;
    lowRate: number | null;
    highRate: number | null;
    wavgRate: number | null;
    partial: number | null;
    dealers: number | null;
    issueDate: string | null;
    strength: Strength | null;
    /** 종목의 성격에 걸리는 덧붙임(물가채·외평채·비경쟁인수·교환·바이백 …). */
    events: EventNote[];
    /** 그날의 방향. **응찰 강도가 정한다** — 발행 자체는 미리 공표돼 이미
     * 반영돼 있고, 새로 알게 되는 사실은 «얼마나 들어왔나» 뿐이다. */
    bias: Bias | null;
    /** 낙찰금리가 그날 국고 민평보다 오버였나 언더였나. */
    mp: Versus | null;
  }[];
  omo: {
    kind: string;
    name: string | null;
    planned: number | null;
    allotted: number | null;
    rate: number | null;
    /** 통안 경쟁입찰은 금리가 구간으로 낙찰된다. 하단과 다를 때만 뜻이 있다. */
    rateHigh: number | null;
    code: string | null;
    /** 결과인가 공고인가. 공고만 뜬 날은 아직 아무것도 안 오갔다. */
    stage: string | null;
    /** 예정 대비 얼마나 몰렸나 — 이 줄의 다른 사실이다. */
    bid: number | null;
    /** 흡수인가 공급인가 — 설명과 방향이 한 벌로 온다. */
    events: EventNote[];
    /** 그게 평년보다 큰 규모인가. 방향만 있고 규모가 없으면 흡수 1천억과
     * 흡수 3조가 화면에서 같은 무게로 읽힌다. */
    strength: OmoStrength | null;
  }[];
  /** 금통위가 **있는 날**인지와 그날 **무엇을 정했는지**는 다른 사실이다.
   * `scheduled` 는 검증된 달력이, `decision` 은 수집기의 결과표가 답한다. */
  mpc: {
    scheduled: boolean;
    decision: {
      decision: string | null;
      before: number | null;
      after: number | null;
      changePp: number | null;
      gist: string | null;
    } | null;
    /** 인하는 강세, 인상은 약세, 동결은 중립. **결정이 아직이면 방향도 아직**
     * 이다 — 열린 회의와 안 열린 회의는 다른 사실이다. */
    bias: Bias | null;
  } | null;
  /** 민평이 붙었는지, 그리고 그 잣대가 무엇인지. SQL 이 없는 PC 에서는
   * 오버·언더만 빠지고 나머지는 그대로 선다 — `note` 가 왜 없는지를 말한다. */
  mp: { note: string | null; caveat: string | null };
  /** 지급준비금 적립기간의 시작·마감. 그날이 둘 다 아니면 `null`.
   *
   * **규칙으로 찍지 않는다** — «매월 둘째 목요일» 은 2026년 열둘 중 둘에서
   * 어긋난다. 한국은행 공표표 단독이다. */
  res: {
    kind: '지준 시작' | '지준 마감';
    /** 이 적립기간이 대응하는 계산 대상월. */
    month: string;
    start: string;
    end: string;
    /** 적립기간 길이. 4주(28일)와 5주(35일)가 섞여 있다. */
    days: number;
    /** 마감까지 남은 날. 줄어들수록 남은 조정이 단기자금으로 몰린다. */
    leftDays: number;
    gloss: Gloss;
  } | null;
  /** 열자마자 보이는 그날 규모. **발행은 여기 없다** — 섹터 필터가 목록을
   * 줄이므로 화면이 자기가 그리는 것을 센다(한 벌만 존재하게). */
  sum: {
    /** 억원. 비경쟁인수까지 그날 실제로 나간 물량. */
    ktbWon: number;
    ktbN: number;
    /** 억원. **상계하지 않는다** — 순액으로 누르면 «3조 흡수 + 3조 공급» 이
     * «0» 이 되는데 둘은 같은 날 다른 창구로 오간 진짜 물량이다. */
    omoAbsorb: number;
    omoSupply: number;
  };
  src: Record<'iss' | 'ktb' | 'omo' | 'mpc' | 'res', Src>;
};

/** DART 원문 한 건으로 가는 길. 접수번호가 그 열쇠다. */
export const dartUrl = (rcept: string) =>
  `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${encodeURIComponent(rcept)}`;

async function get<T>(url: string, what: string): Promise<T> {
  const r = await fetch(url);
  if (r.status === 404) throw new IssuanceUnavailable();
  if (r.status === 503) {
    const detail = (await r.json().catch(() => null)) as { detail?: string } | null;
    throw new IssuanceUnavailable(detail?.detail);
  }
  if (!r.ok) {
    const detail = (await r.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `${what}: HTTP ${r.status}`);
  }
  return (await r.json().catch(() => {
    throw new Error('서버가 응답을 끝내지 못했어요, 다시 열어 보세요');
  })) as T;
}

export const fetchIssuanceCalendar = (ym: string, months: number) =>
  get<IssuanceCalendar>(issuanceCalendarUrl(ym, months), '발행 캘린더');

export const fetchIssuanceDay = (iso: string) =>
  get<IssuanceDay>(issuanceDayUrl(iso), '그날 발행');
