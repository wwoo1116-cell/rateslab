/* 크레딧 RV (DTS) — Lab 세입자의 자료 계약 [OWNER 2026-10-02].
 *
 * **산술은 서버 하나다**(§16) — 스프레드도 z 도 랭크도 `app/creditdts.py` 가 낸다.
 * 화면은 읽고 칠하기만 한다. 근거(표본밖 성적·회전 비용 문턱·겹침 한계)는 그 모듈
 * 머리와 `research/credit-rv-dts/RESULT.md` 에 있다.
 *
 * ⚠ **라이브 전용**이다 — 민평이 SQL 에만 있어 구워 둘 수 없다(제품 RV 와 같다).
 */
import { BacktestUnavailable } from '@/lib/api';
import { labCreditDtsUrl } from '@/lib/staticPaths';

export interface CreditDtsItem {
  sector: string;
  sectorLabel: string;
  tenor: string;
  years: number;
  /** 국고 대비 스프레드(bp). **앵커는 하나**라 행마다 앵커 이름을 안 적는다. */
  nowBp: number;
  /** 창 안 자기평균(bp). */
  meanBp: number;
  /** z 의 분모 = max(지금 스프레드, 바닥). 바닥에 걸리면 `floored` 가 참이다. */
  denomBp: number;
  floored: boolean;
  /** ★이 화면의 점수 — (지금 − 자기평균) ÷ 지금. 큼 = 제 평소보다 벌어짐 = 싸다. */
  z: number;
  rank: number;
  seriesId: string;
}

export interface CreditDts {
  asof: string;
  days: number;
  window: number;
  floorBp: number;
  items: CreditDtsItem[];
  /** 못 세운 칸 — **사유와 함께**. 조용히 빼면 「내 칸이 왜 없지」가 된다. */
  excluded: { id: string; label: string; why: string }[];
  /** 「무엇을 보고 있나」. 화면은 이 말을 **옮겨 적기만** 한다. */
  basis: string;
}

export async function fetchCreditDts(signal?: AbortSignal): Promise<CreditDts> {
  const r = await fetch(labCreditDtsUrl(), { signal });
  if (r.status === 404) throw new BacktestUnavailable();
  if (!r.ok) {
    const detail = (await r.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `creditdts: HTTP ${r.status}`);
  }
  return r.json() as Promise<CreditDts>;
}
