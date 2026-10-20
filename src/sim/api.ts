/* 시뮬레이션이 서버와 주고받는 세 가지. 백테스트와 같은 규율이다 —
 * **살아 있는 백엔드가 있어야 하는 화면**이고, 없으면 그 사실을 말한다.
 *
 * 굽기(static)에 실을 수 없는 이유가 백테스트와 같다: 답이 질문마다 다르고
 * 질문의 수가 무한하다. `/api/instruments` 카탈로그만은 정적이지만, 그것만 있고
 * 전개·실행이 없으면 고를 수는 있는데 실행이 안 되는 화면이 된다.
 */

import { TRUNCATED_RESPONSE_MSG } from "@/lib/api";
import { simExpandUrl, simInstrumentsUrl, simulateUrl } from "@/lib/staticPaths";

import type { EngineLeg, InstrumentCatalog, SimulateBody, SimResponse } from "./scenario";
import { ROUTE_MISSING_DETAIL } from "@/lib/apiBase";

export class SimulationUnavailable extends Error {
  constructor() {
    super(ROUTE_MISSING_DETAIL);
    this.name = "SimulationUnavailable";
  }
}

async function readOrThrow<T>(r: Response, what: string): Promise<T> {
  if (r.status === 404) throw new SimulationUnavailable();
  if (!r.ok) {
    // 백엔드가 422 에 읽을 수 있는 이유를 담는다("그 날 호가가 없어요") — 그대로 올린다.
    const detail = await r.json().catch(() => null);
    throw new Error(detail?.detail ?? `${what}: HTTP ${r.status}`);
  }
  /* 스트리밍 200 이 도중에 끊기면 여기 파싱 실패가 유일한 증상이다 — 파서의
   * 문장 대신 사람 말(@/lib/api 와 같은 문장)로 올린다. */
  const parsed = await r.json().catch(() => {
    throw new Error(TRUNCATED_RESPONSE_MSG);
  });
  /* 스트리밍 200 안의 에러 페이로드 — 헤더가 이미 나간 뒤 엔진이 죽으면
   * 백엔드가 상태코드 대신 `{"detail": …}` 를 몸통에 실어 보낸다(simulate.py).
   * 진짜 결과에는 detail 키가 없으므로 이 모양이 곧 판별이다. */
  if (parsed && typeof parsed === "object" && "detail" in parsed) {
    throw new Error(String((parsed as { detail: unknown }).detail));
  }
  return parsed as T;
}

/** 고를 수 있는 상품들. 목록의 주인은 백엔드다 — 프론트가 자기 목록을 들면 두
 * 화면의 "주요 스프레드" 가 갈리고 그 순간 비교가 끝난다. */
export async function fetchInstruments(): Promise<InstrumentCatalog> {
  return readOrThrow(await fetch(simInstrumentsUrl()), "instruments");
}

/** 상품 한 줄 → 엔진이 받는 다리들.
 *
 * 줄이 여럿이면 요청도 여럿이다 [v1]. 한 번에 묶는 엔드포인트를 만들지 않은
 * 이유는, 줄 하나가 실패해도 나머지는 살아야 하기 때문이다 — 6M 호가가 없는 날
 * 그 줄만 빠지고 다른 줄은 그대로 평가된다. 묶으면 전부 아니면 전무가 된다. */
export async function expandInstrument(body: {
  seriesId: string;
  direction: number;
  notional: number;
  baseDate: string;
}): Promise<{ seriesId: string; kind: string; legs: EngineLeg[] }> {
  const r = await fetch(simExpandUrl(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readOrThrow(r, "expand");
}

/** 한 번 돌린다.
 *
 * 응답은 **스트리밍**이다 — 엔진이 도는 동안 백엔드가 공백을 흘려 보내 프록시
 * 타임아웃(터널의 ~100초 벽)을 막는다. JSON 파서는 앞의 공백을 무시하므로
 * `r.json()` 이 그대로 통한다. */
export async function runSimulation(body: SimulateBody): Promise<SimResponse> {
  const r = await fetch(simulateUrl(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readOrThrow(r, "simulate");
}
