import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { LOAD_DEADLINE_MS, unreachableDetail, withDeadline } from '../src/lib/apiBase';

/**
 * 첫 자료 적재에 **시한**이 있는가. [2026-10-01, 트레이더 자리에서 「불러오는 중」만 떴다]
 *
 * `ui/DataState` 는 「기다림과 실패는 다르게 보여야 한다」로 쓰인 부품이고, 그 머리에
 * v1 사고가 적혀 있다 — **모든 실패가 똑같이 영원한 「불러오는 중」이었고 81초에도
 * 여전히 loading 이었다.** 그런데 그 갈라짐은 fetch 가 **거절할 때만** 듣는다.
 * 방화벽이 패킷을 조용히 버리면 `fetch` 는 settle 하지 않고 `Promise.all` 도 끝나지
 * 않아 `error` 가 서지 않는다 → 영원히 `LoadingState`.
 *
 * 2026-10-01 에 트레이더 자리에서 본 것이 정확히 그것이다. 여기서 재는 것은
 * **매달린 약속이 시한 안에 실패로 바뀌는가** 하나다.
 */
describe('첫 적재에 시한이 있다', () => {
  it('★매달린 약속이 시한에 실패로 바뀐다', async () => {
    /* 영원히 settle 하지 않는 약속 = 조용히 버려진 패킷. */
    const never = new Promise<string>(() => {});
    await expect(withDeadline(never, 20)).rejects.toThrow();
  });

  it('제때 오면 그대로 통과한다 — 되는 길을 막지 않는다', async () => {
    await expect(withDeadline(Promise.resolve('ok'), 1_000)).resolves.toBe('ok');
  });

  it('원래 실패는 원래 사유로 올라온다 — 시한이 사유를 덮지 않는다', async () => {
    const boom = Promise.reject(new Error('forwards: HTTP 500'));
    await expect(withDeadline(boom, 1_000)).rejects.toThrow('forwards: HTTP 500');
  });

  it('시한이 무거운 호출을 끊을 만큼 짧지 않다', () => {
    /* 화면을 여는 다섯은 실측 1~2초다. 백테스트(수십 초)에는 이 시한을 걸지 않는다. */
    expect(LOAD_DEADLINE_MS).toBeGreaterThanOrEqual(10_000);
    expect(LOAD_DEADLINE_MS).toBeLessThanOrEqual(60_000);
  });
});

describe('문구가 읽는 사람의 말이다', () => {
  it('★어디에 못 닿았는지를 적는다', async () => {
    const { API_BASE } = await import('../src/lib/apiBase');
    const msg = unreachableDetail(20_000);
    expect(msg).toContain('20초');
    if (API_BASE !== '') expect(msg).toContain(API_BASE);
    /* 「화면은 떠 있으니 자료 경로만 막힌 것」 — 멀리서 보는 사람이 가장 먼저
       알아야 하는 구분이다(그가 보고 있는 것이 바로 그 상태다). */
    expect(msg).toContain('자료');
  });

  it('★원인을 화면에 **못박지** 않는다 — 주소는 설정에서 온다', () => {
    /* 종전 기본 문구가 「백엔드(:8200)가 응답하지 않았어요」로 **화면에 박혀** 있었다.
       멀리서 보는 사람의 PC 에는 :8200 이 없으니, 읽는 사람이 확인할 수 없는 사실을
       원인으로 적는 셈이었다. 지금은 주소가 `lib/apiBase` 에서 온다.
       ⚠개발에서는 그 주소가 마침 `localhost:8200` 이라 문구에 8200 이 **정당하게**
         들어간다 — 그래서 문자열을 금지하는 대신 **박혀 있지 않은지**를 잰다. */
    const src = readFileSync(
      path.join(import.meta.dirname, '..', 'src', 'ui', 'DataState.tsx'), 'utf8');
    const body = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
    expect(body).not.toMatch(/백엔드\(:\d+\)/);
    expect(body).toContain('unreachableDetail()');
  });
});
