import path from 'node:path';

import type { NextConfig } from 'next';

/* ── 자료는 **같은 출처**로 들어온다 [2026-10-01, 트레이더 자리에서 안 보였다] ──
 *
 * 종전: 브라우저가 Vercel 에서 화면을 받고 **자기 네트워크에서** Funnel
 * (`https://<host>.ts.net/v2`)로 직접 나갔다. 그래서 끊길 자리가 둘이고, 둘째가
 * **보는 사람의 네트워크**다 — 데스크에서 `*.ts.net` 이 막히면 화면은 열리고
 * 자료만 안 온다. 실측 2026-10-01: 화면 200 · 백엔드(진짜 외부에서) 200 ·
 * CORS 허용인데 트레이더 자리에서는 자료가 안 왔다.
 *
 * 지금: 브라우저는 **사이트 자신**(`/be/...`)을 부르고 Vercel 서버가 Funnel 로
 * 넘긴다. 보는 사람 쪽에서 `ts.net` 을 풀 필요도, CORS 도 없다 — 이미 화면을
 * 받고 있는 그 출처 하나만 열려 있으면 된다.
 *
 * ⚠`NEXT_PUBLIC_API_BASE` 는 여전히 **백엔드가 어디인가** 하나를 말한다(대시보드
 *   값 그대로). 바뀐 것은 «누가 그 주소로 나가는가» 다 — 브라우저가 아니라 Vercel.
 * ⚠이 파일에서 그 변수를 읽는 것은 **서버 쪽**이다. 브라우저 쪽에서 그 값을 정하는
 *   곳은 여전히 `src/lib/apiBase.ts` 하나다(`guards/production-env` 의 그 규칙).
 */
const PROXY_PREFIX = '/be';

/** 넘길 곳 — 대시보드의 `NEXT_PUBLIC_API_BASE`. 비었으면 넘기지 않는다
 *  (정적 모드이거나 백엔드 없이 구운 것이고, 그 선택은 그쪽에 적혀 있다). */
const BACKEND = (process.env.NEXT_PUBLIC_API_BASE ?? '')
  .replace(/[\uFEFF\u200B-\u200D]/g, '')
  .trim()
  .replace(/\/+$/, '');

const nextConfig: NextConfig = {
  /* A stray `package-lock.json` in the user's home directory makes Next pick
   * `C:\Users\infomax` as the workspace root for file tracing. Pin it here so
   * the build traces this project and nothing above it. */
  outputFileTracingRoot: path.resolve(import.meta.dirname),

  async rewrites() {
    if (!BACKEND) return [];
    return [{ source: `${PROXY_PREFIX}/:path*`, destination: `${BACKEND}/:path*` }];
  },

  /* 캐시 헤더는 **여기**에 적는다, `vercel.json` 이 아니라 [2026-08-20].
   *
   * v1 에서 vercel.json 에 적었다가 로컬 `next start` 와 배포가 갈렸다 — 로컬
   * 서버는 그 파일을 읽지 않아서, 배포에서만 나타나는 캐시 동작을 로컬에서
   * 재현할 방법이 없었고 아무도 그 사실을 몰랐다. `headers()` 는 두 곳 다
   * 적용된다. (이 리포에는 아직 vercel.json 이 없다 — 옮겨 올 것도 없었다.)
   *
   * `immutable` 은 쓰지 않는다. Next 자신의 `/_next/static/*` 만이 파일명에
   * 콘텐츠 해시를 달고 있어 immutable 이 참이고, 그건 Next 가 알아서 붙인다.
   * 아래 것들은 **이름이 고정된 자산**이라 내용이 바뀌어도 URL 이 그대로다 —
   * immutable 을 붙이면 방문자의 브라우저가 만료까지 새 파일을 영영 안 받는다.
   * 붙이지 않으면 만료 뒤 조건부 요청 한 번(304, 본문 없음)으로 끝난다. */
  async headers() {
    return [
      {
        /* 자체 호스팅 폰트. 이름이 `Pretendard.subset.woff2` 로 고정이고,
         * 서브셋을 다시 구우면 같은 이름으로 내용만 바뀐다. 일주일 뒤
         * 재검증하되 그동안은 네트워크를 타지 않는다. */
        source: '/fonts/:file*',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=604800, must-revalidate' },
        ],
      },
    ];
  },
};

export default nextConfig;
