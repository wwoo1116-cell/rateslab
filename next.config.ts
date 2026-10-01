import path from 'node:path';

import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  /* A stray `package-lock.json` in the user's home directory makes Next pick
   * `C:\Users\infomax` as the workspace root for file tracing. Pin it here so
   * the build traces this project and nothing above it. */
  outputFileTracingRoot: path.resolve(import.meta.dirname),

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
