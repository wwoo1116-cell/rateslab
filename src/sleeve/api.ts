/* 모멘텀 **슬리브** 집행면의 서버 계약 — `/api/momentum/sleeve`.
 *
 * 숫자는 전부 서버가 끝낸다(§16, `backend/app/sleeve.py`) — 목표 액면·축소 후·
 * 어제와의 차이·칠지 말지까지. 이 파일은 타입과 페처뿐이다.
 *
 * ## 옆의 `momentum` 면과 **다른 북**이다
 *
 *     `/api/momentum/board`   2026-09-08 등록(선물·합성)의 거울 — 굴리지 않는다
 *     `/api/momentum/sleeve`  2026-09-15 동결·09-16 채점 중인 IRS 50/50 — 실물
 *
 * 두 수를 섞으면 어느 등록의 성적인지 못 읽는다. 세입자를 가른 이유가 그것이다.
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

export interface SleeveSheet {
  /** 굽는 중인가 — 첫 요청은 참으로 곧바로 돌아온다(한 번 세우는 데 44초). */
  building: boolean;
  available: boolean;
  /** 못 세웠으면 **왜** — 빈 표를 조용히 내지 않는다. */
  why?: string;
  asof?: string;
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
  /** W4 — 평균회귀가 증거금을 많이 쓰면 오늘 액면을 비례로 줄인다. */
  scale?: number;
  marginNeed?: number;
  mrMargin?: number;
  headroom?: number;
  /** ★평균회귀를 **실제로 안 줄이면** 이렇게 된다. 등록서의 「평균회귀 쪽은 안
   *  건드린다」와 k_mr 을 여력에 거는 것이 한 문장에서 충돌하는 자리라, 화면이
   *  두 수를 나란히 적는다(인계문 §5-1). */
  headroomNoShrink?: number;
  scaleNoShrink?: number;
  kMr?: number;
  kMrLive?: number;
  marginSource?: SleeveMarginSource;
  /** 상한을 실제로 넘은 날 / 전체 날 — 「이 배율이 자주 걸리나」. */
  histHitDays?: number;
  histDays?: number;
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
