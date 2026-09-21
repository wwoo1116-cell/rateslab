/* Momentum 면의 서버 계약 — `/api/momentum/sleeve`.
 *
 * 숫자는 전부 서버가 끝낸다(§16, `backend/app/sleeve.py`) — 목표 액면·축소 후·
 * 어제와의 차이·칠지 말지까지. 이 파일은 타입과 페처뿐이다.
 *
 * ## 라우트 이름은 `sleeve` 로 남는다
 *
 * 화면 이름은 2026-09-21 에 Momentum 으로 옮겼지만 **라우트는 안 바꿨다**: 그
 * 이름이 가리키는 것은 화면이 아니라 **등록서**(`PREREG_sleeve_5050_2026-09-15`)
 * 이고, 그 등록이 스스로를 슬리브라 부른다. 바꾸면 화면과 등록서가 다른 낱말을
 * 쓰게 된다.
 *
 * ⚠ `/api/momentum/board`·`/book` 은 **09-08 KTB 등록**의 것이고 이 면은 그것을
 * 안 읽는다(그 면은 09-21 에 은퇴했다). 두 수를 섞으면 어느 등록의 성적인지
 * 못 읽는다.
 */

import { BacktestUnavailable } from '@/lib/api';
import { momentumSleeveUrl } from '@/lib/staticPaths';

/** 만기 한 줄 — 목표·축소 후·어제·**주문**.
 *
 *  ⚠ **부호 규약**: 계열이 −bp 라 `dv01` 이 양(+)이면 **리시브**다. 화면이 그
 *  규약을 다시 만들지 않게 서버가 `side` 를 같이 낸다. */
export interface SleeveLeg {
  tenor: string;
  /** 순 DV01(₩/bp) — 다섯 북을 더한 값. */
  dv01: number;
  /** 그날 실측 커브의 pv01 — 근사 pv01 은 3Y 3.8%·10Y 12.5% 과대평가였다. */
  pv01: number;
  face: number;
  /** W4 배율을 먹인 뒤. 배율이 1 이면 `face` 와 같다. */
  faceAfter: number;
  side: number;
  signedFace: number;
  prevSigned: number;
  /** **오늘 칠 것** — 목표가 아니라 어제와의 차이다. */
  delta: number;
  /** 1억 미만이면 거짓 — 호가 단위와 수수료를 못 이긴다. */
  trade: boolean;
}

/** 평균회귀 증거금이 어디서 왔나 — 어느 규칙·어느 기준일인지.
 *
 *  화면이 이것을 적어야 「여력은 하루 옛것인데 주문표는 오늘 것」을 말할 수 있다. */
export interface SleeveMarginSource {
  source: string;
  rule?: string;
  asof?: string;
  stale?: string[];
  stale_held?: number;
}

/** 원장 상태 — 아침 주문표가 남기는 그 파일.
 *
 *  **비어 있는 것은 결함이 아니라 결정 대기**다: 첫 채점 행을 적을지는 「슬리브를
 *  실제로 켤 것인가」와 같이 정할 일이라 이전 세션이 `--dry` 로 두었다. 화면은 그
 *  사실을 적기만 한다. */
export interface SleeveLedger {
  rows: number;
  last: string | null;
  lastRun: string | null;
  scoredRows: number;
  why?: string;
}

/** 한 테너의 **룩백 격자** 한 칸 — KTB 보드가 주던 그 칸이다.
 *
 *  ⚠ 계열이 **−bp** 라 `signal` +1 이 «리시브»이고, 화면이 칠할 값은 `rate`
 *  (= −signal)다. 선물 보드가 가격 계열에서 같은 식을 쓰는 것과 결론은 같지만
 *  이유가 다르다(저쪽은 가격↑=금리↓, 이쪽은 계열이 이미 뒤집혀 있다). */
export interface SignalCell {
  lookback: number;
  signal: number;
  rate: number;
  tstat: number | null;
}

export interface SignalRow {
  tenor: string;
  asof: string;
  /** 그 테너의 오늘 금리(bp). */
  rate: number;
  cells: SignalCell[];
  composite: number;
  compositeRate: number;
  /** 다섯 룩백 중 합성과 **같은 방향**인 것의 수 — 갈리면 「모른다」에 가깝다. */
  agree: number;
  of: number;
  holdDays: number;
}

export interface ThemeRow {
  theme: string;
  sign: number;
  holdDays: number;
  asof: string | null;
}

/** 오늘의 신호 — KTB 면이 주던 두 표가 **IRS 계열 위에서** 선다.
 *  못 세우면 `available: false` 와 사유이고, 그때 주문표는 그대로 선다. */
export interface SleeveSignals {
  available: boolean;
  why?: string;
  signal?: string;
  lookbacks?: number[];
  rows?: SignalRow[];
  themes?: ThemeRow[];
  macroSign?: number;
  macroRate?: number;
}

/** 다리 하나의 **표본내 성적**.
 *
 *  ⚠ 원화 열(`annPnl`·`maxDrawdown`·`ulcer`)은 **혼자 못 읽는다** — 다리마다 실제로
 *  건 위험이 다르다. 낙폭에는 «위험 맞춤» 짝이 붙고(추세 다리의 변동성에 맞춘 뒤),
 *  다리끼리 견주는 것은 무차원 비율(`martin`·`sharpe`)이다. 이 데스크에는 자본
 *  분모가 없으므로 **없는 분모를 지어내지 않는다**. */
export interface PerfRow {
  leg: string;
  annPnl: number;
  annVol: number;
  maxDrawdown: number;
  maxDrawdownVolMatched: number;
  ulcer: number;
  /** 원화 열은 **짝이 있어야 읽힌다** — 낙폭과 같은 사정이다. */
  ulcerVolMatched: number;
  martin: number | null;
  sharpe: number | null;
  days: number;
}

/** 표본내 성적 — **서버가 등록 창에서 잘라서** 낸다.
 *
 *  창의 끝은 동결일(09-15)이 아니라 **2026-09-08** 이다: 슬리브 판정문이 선 창이
 *  그쪽이고, 한 주를 더 넣으면 50/50 SR 이 1.000 → 1.168 로 간다(실측). 프런트는
 *  절단을 **하지 않는다** — 하면 잘린 구간이 네트워크 탭에 남는다. */
export interface SleevePerf {
  available: boolean;
  why?: string;
  window?: { start: string; end: string };
  refVol?: number;
  rows?: PerfRow[];
}

/** MR 없이 선 판 — 배율을 안 먹인 이 북 자신의 수 [OWNER 2026-09-21 「별개도
 *  돌아가게」]. 배분기를 못 읽는 날에도 이쪽은 선다. */
export interface SleeveStandalone {
  legs: SleeveLeg[];
  faceTotal: number;
  marginNeed: number;
  turnover: number;
}

/** 어느 등록 북인가 — **서버가 낸다**.
 *
 *  클라이언트가 동결일을 다시 적으면 두 번째 진실이 된다: 등록서가 바뀐 날 화면만
 *  옛 날짜를 말한다. KTB 면에 대해 이미 못 박혀 있던 명제이고(`guards/
 *  critique-repairs`), 자리의 주인이 바뀌어도 그대로 산다. */
export interface SleeveRegistry {
  book: string;
  instrument: string;
  freeze: string;
  note: string;
}

export interface SleeveSheet {
  /** 굽는 중인가 — 첫 요청은 참으로 곧바로 돌아온다(한 번 세우는 데 44초). */
  building: boolean;
  available: boolean;
  /** 못 세웠으면 **왜** — 빈 표를 조용히 내지 않는다. */
  why?: string;
  asof?: string;
  registry?: SleeveRegistry;
  /** 채점 창인가 — 동결일 다음 영업일부터다. */
  scored?: boolean;
  freeze?: string;
  mult?: number;
  legs?: SleeveLeg[];
  faceTotal?: number;
  faceAfter?: number;
  /** 오늘 칠 것의 절대합. */
  turnover?: number;
  minTicket?: number;
  /** 이 북 혼자의 답 — **늘 선다**. */
  standalone?: SleeveStandalone;
  /** 등록 규약(W4 연동)이 섰나. 거짓이면 `linkedWhy` 가 사유를 진다. */
  linked?: boolean;
  linkedWhy?: string | null;
  /** 오늘의 신호 — 테너 × 룩백 격자와 테마 넷. */
  signals?: SleeveSignals | null;
  /** 표본내 성적 — 다리 셋. 창은 등록 판정문의 창이다. */
  perf?: SleevePerf | null;
  /** W4 — 평균회귀가 증거금을 많이 쓰면 오늘 액면을 비례로 줄인다.
   *  연동이 안 서면 **1.0** 이다(모르는 것을 0 으로 치지 않는다). */
  scale?: number;
  marginNeed?: number;
  mrMargin?: number | null;
  headroom?: number | null;
  /** ★평균회귀를 **실제로 안 줄이면** 이렇게 된다. 등록서의 「평균회귀 쪽은 안
   *  건드린다」와 k_mr 을 여력에 거는 것이 한 문장에서 충돌하는 자리라, 화면이
   *  두 수를 나란히 적는다(인계문 §5-1). */
  headroomNoShrink?: number | null;
  scaleNoShrink?: number | null;
  kMr?: number | null;
  kMrLive?: number | null;
  marginSource?: SleeveMarginSource | null;
  /** 상한을 실제로 넘은 날 / 전체 날 — 「이 배율이 자주 걸리나」. */
  histHitDays?: number | null;
  histDays?: number | null;
  ledger?: SleeveLedger;
}

export async function fetchSleeve(): Promise<SleeveSheet> {
  const r = await fetch(momentumSleeveUrl());
  if (r.status === 404) throw new BacktestUnavailable();
  if (!r.ok) {
    const detail = await r.json().catch(() => null);
    throw new Error(detail?.detail ?? `sleeve: HTTP ${r.status}`);
  }
  return r.json();
}
