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
 * ★쓰고 나면 지운다. 비밀은 안 싣는다 — 부르는 주소는 이미 공개된 Funnel 이고
 *   돌려주는 것은 상태코드·소요시간·오류 이름뿐이다.
 */
import { probeTargets } from '@/lib/apiBase';

export const dynamic = 'force-dynamic';

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
