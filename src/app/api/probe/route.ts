/**
 * ⚠**임시 진단 라우트** — 왜 Vercel→Funnel 이 502 인지 **Vercel 안에서** 재는 자리.
 *
 * 2026-10-01: `next.config.ts` 의 rewrite 로 `/be/*` → Funnel 을 걸었더니 로컬
 * `next start` 는 200 인데 **배포에서는 세 번 다 502**(각 30초)였다. 로컬에서 되는
 * 것이 배포에서 되는 것이 아니라는 뜻이고, 이유를 **짐작으로** 고치려다 라이브를
 * 한 번 깼다(`e30419c1` → `4fc89ff8` 되돌림). 그래서 사유를 **읽는다**.
 *
 * ★주소를 아는 곳은 `lib/apiBase` 하나다 — 첫 판에서 이 파일이 `process.env` 를 직접
 *   읽고 URL 을 이어 붙였고, `guards/production-env` 가 **그 자리에서 잡았다**.
 * ★★폴더 이름이 `_probe` 였을 때는 **길이 안 났다**(404) — Next App Router 는
 *   `_` 로 시작하는 폴더를 **라우팅에서 제외**한다(private folder). 404 를 보고
 *   「배포가 안 됐다」로 읽을 뻔했고, 그게 오늘 세 번째 오독이 될 자리였다.
 * ★쓰고 나면 지운다. 비밀은 안 싣는다 — 부르는 주소는 이미 공개된 Funnel 이고
 *   돌려주는 것은 상태코드·소요시간·오류 이름뿐이다.
 */
import { probeTargets } from '@/lib/apiBase';

export const dynamic = 'force-dynamic';

/** ★**어느 리전에서 나가는가** — 2026-10-01 실측이 이걸 범인으로 지목했다.
 *  기본값에서는 함수가 `iad1`(미국 동부)에서 돌았고, Tailscale 중계는 APAC
 *  (`103.84.155.x`)이라 **TCP 연결이 10.5초에 타임아웃**했다
 *  (`UND_ERR_CONNECT_TIMEOUT`). 화면은 `icn1`(서울) 에서 나가는데 함수는 미국이었다.
 *  여기를 서울로 못박아 「서울에서는 닿나」를 가른다. */
export const preferredRegion = 'icn1';

export async function GET() {
  const out: unknown[] = [];
  for (const url of probeTargets()) {
    const t0 = Date.now();
    try {
      const r = await fetch(url, { cache: 'no-store', signal: AbortSignal.timeout(20_000) });
      const body = await r.text();
      out.push({ url, ok: r.ok, status: r.status, ms: Date.now() - t0, bytes: body.length,
                 head: body.slice(0, 80) });
    } catch (e: unknown) {
      const err = e as { name?: string; message?: string; cause?: { code?: string } };
      out.push({ url, ms: Date.now() - t0, error: err?.name, message: err?.message,
                 code: err?.cause?.code });
    }
  }
  return Response.json({ region: process.env.VERCEL_REGION ?? null, probes: out });
}
