/* 프로덕션 번들에 개발용 출처가 들어가지 않는가 — **설정과 산출물 양쪽**.
 *
 * v1 의 실제 사고: `NEXT_PUBLIC_API_BASE` 가 없으면 코드가 조용히
 * `http://localhost:…` 으로 떨어졌고, 그 문자열이 빌드 시각에 브라우저 번들로
 * 구워져 배포됐다. 방문자의 브라우저가 **자기 PC** 의 포트를 두드렸다.
 * 그때 있던 가드는 **설정 파일만** 봤기 때문에 초록이었다 — 설정에는 아무것도
 * 안 적혀 있었고, 사고는 적혀 있지 않다는 사실 자체였다.
 *
 * 그래서 여기는 셋을 본다:
 *
 *   1. 설정   — `.env*`, `next.config.ts`, `vercel.json` 에 개발 출처가 없다
 *   2. 소스   — `process.env.NEXT_PUBLIC_API_BASE` 를 읽는 파일이 하나뿐이고,
 *               `lib/` 밖에서 URL 을 다시 조립하지 않는다
 *   3. 산출물 — `.next/static/chunks` 에 개발 출처가 없다  ← 새로 생긴 눈
 *
 * 2026-08-20 실측: 이 가드를 쓰기 직전의 `.next` 에 `http://127.0.0.1:8200` 이
 * 실제로 들어 있었다. 설정만 보는 가드는 그걸 못 본다.
 */

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';
import { stripComments } from './_source';

const ROOT = path.resolve(import.meta.dirname, '..');
const read = (rel: string) => readFileSync(path.join(ROOT, rel), 'utf8');

/* ── 판정기 ─────────────────────────────────────────────────────────────────
 * "localhost 라는 글자" 를 금지하면 못 쓴다. 실측하면 라이브러리가 그 단어를
 * 정당하게 쓴다:
 *
 *   "localhost"===s.host          URL 파서의 호스트 비교
 *   new URL(r,"http://n")         Next 라우터가 상대경로를 풀 때 쓰는 더미 베이스
 *   http://www.w3.org/2000/svg    SVG 네임스페이스(네트워크로 안 나간다)
 *
 * 그래서 금지 대상은 **낱말이 아니라 출처**다: 요청이 실제로 나갈 수 있는
 * 모양만 잡는다. */

/** 네트워크로 안 나가는 `http://` — XML 네임스페이스. 실측으로 늘린다. */
const NAMESPACE_HOSTS = new Set(['www.w3.org']);

/** 어떤 스킴으로 와도 안 되는 호스트. */
const LOOPBACK = new Set(['localhost', '127.0.0.1', '0.0.0.0', '[::1]', '::1']);

const URLISH = /(?:https?|wss?):\/\/[^\s"'`)\\<>]+/g;

export function findDevOrigins(text: string): string[] {
  const hits: string[] = [];
  for (const raw of text.match(URLISH) ?? []) {
    let url: URL;
    try {
      url = new URL(raw);
    } catch {
      continue;
    }
    const host = url.hostname;
    if (LOOPBACK.has(host)) {
      hits.push(raw);
      continue;
    }
    /* 평문 http 로 나가는 진짜 호스트. 점이 없는 것(`http://n`)은 번들러가
     * 만든 더미 베이스라 통과시키고, 네임스페이스는 목록으로 통과시킨다. */
    if (url.protocol === 'http:' && host.includes('.') && !NAMESPACE_HOSTS.has(host)) {
      hits.push(raw);
    }
  }
  /* 스킴 없이 박힌 루프백("127.0.0.1:8200")도 잡는다. */
  for (const bare of text.match(/\b(?:127\.0\.0\.1|0\.0\.0\.0)\b/g) ?? []) hits.push(bare);
  return [...new Set(hits)];
}

/** 주석은 번들에 안 실린다 — 문서에 적힌 예시 주소까지 금지하면 설명을 못 쓴다. */

function walk(dir: string, ext: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) walk(full, ext, out);
    else if (full.endsWith(ext)) out.push(full);
  }
  return out;
}

const rel = (full: string) => path.relative(ROOT, full).replace(/\\/g, '/');

describe('판정기 자신 — 심어서 실패하는지', () => {
  /* 아래 산출물 검사는 `.next` 가 없으면 건너뛴다. 건너뛴 검사는 아무것도
   * 증명하지 않으므로, 판정기에 이빨이 있다는 것만은 여기서 늘 증명한다. */
  it('사고 그대로의 문자열을 잡는다', () => {
    expect(findDevOrigins('fetch("http://localhost:8200/api/health")')).toContain(
      'http://localhost:8200/api/health',
    );
    expect(findDevOrigins('a="http://127.0.0.1:8200/api/universe"')).toContain(
      'http://127.0.0.1:8200/api/universe',
    );
    expect(findDevOrigins('const h="127.0.0.1:8200"')).toContain('127.0.0.1');
    expect(findDevOrigins('u="http://api.example.com/x"')).toContain('http://api.example.com/x');
  });

  it('실측된 정당한 쓰임은 통과시킨다', () => {
    expect(findDevOrigins('e=new URL(r.asPath,"http://n")')).toEqual([]);
    expect(findDevOrigins('xmlns:"http://www.w3.org/2000/svg"')).toEqual([]);
    expect(findDevOrigins('if("localhost"===s.host)')).toEqual([]);
    expect(findDevOrigins('u="https://rateslab.vercel.app/api/health"')).toEqual([]);
  });
});

describe('설정', () => {
  it('리포에 커밋된 .env 는 템플릿 하나뿐이다', () => {
    const present = readdirSync(ROOT).filter((f) => f.startsWith('.env'));
    /* `.env.local` 은 `next build` 도 읽는다 — 개발용 오버라이드가 거기 있으면
     * 프로덕션 번들이 그걸 물고 나간다. 개발 전용 값의 자리는
     * `.env.development.local` 이고, 그건 `next build` 가 안 읽는다.
     *
     * 실측 2026-08-20: **`vercel link` 와 `vercel env pull` 이 이 파일을
     * 만든다**(`VERCEL_OIDC_TOKEN` 한 줄). 이 리포는 OIDC 를 쓰지 않으므로
     * 지우면 되고, 이 검사가 그때 잡았다. 다시 만들어지면 다시 지운다 —
     * 자동 생성물이라고 통과시키면 그 파일에 다른 것이 들어오는 날 못 잡는다. */
    expect(present.filter((f) => f !== '.env.example' && f !== '.env.development.local')).toEqual(
      [],
    );
  });

  it('.env.example 은 값이 아니라 키만 담는다', () => {
    for (const line of read('.env.example').split(/\r?\n/)) {
      if (!line.trim() || line.trimStart().startsWith('#')) continue;
      const value = line.slice(line.indexOf('=') + 1);
      expect(value.trim(), line).toBe('');
    }
  });

  it('next.config.ts 에 개발 출처가 없다', () => {
    expect(findDevOrigins(stripComments(read('next.config.ts')))).toEqual([]);
  });

  it('vercel.json 이 있다면 캐시 헤더를 들고 있지 않다', () => {
    /* §4: 로컬 `next start` 는 vercel.json 을 읽지 않아 로컬과 배포가 갈린다.
     * 헤더의 자리는 next.config.ts 의 `headers()` 다. */
    if (!existsSync(path.join(ROOT, 'vercel.json'))) return;
    const json = JSON.parse(read('vercel.json')) as Record<string, unknown>;
    expect(Object.keys(json)).not.toContain('headers');
  });
});

describe('소스', () => {
  const sources = walk(path.join(ROOT, 'src'), '.ts').concat(
    walk(path.join(ROOT, 'src'), '.tsx'),
  );

  it('src 를 실제로 훑었다', () => {
    // 워커가 빈 목록을 훑고 초록을 내는 것이 이 계열 가드의 고전적 실패다.
    expect(sources.length).toBeGreaterThan(50);
  });

  it('NEXT_PUBLIC_API_BASE 를 읽는 파일은 하나다', () => {
    const readers = sources
      .filter((f) => readFileSync(f, 'utf8').includes('process.env.NEXT_PUBLIC_API_BASE'))
      .map(rel);
    expect(readers).toEqual(['src/lib/apiBase.ts']);
  });

  it('lib/ 밖에서 백엔드 URL 을 다시 조립하지 않는다', () => {
    /* v1 에서 컴포넌트가 URL 을 직접 이어 붙였고, 손으로 적은 목록이 `lib/`
     * 밖을 안 봐서 그걸 놓쳤다. 이 검사는 트리 전체를 본다. */
    const offenders = sources
      .filter((f) => !rel(f).startsWith('src/lib/'))
      .filter((f) => /\$\{API_BASE\}/.test(readFileSync(f, 'utf8')))
      .map(rel);
    expect(offenders).toEqual([]);
  });

  it('소스에 개발 출처 리터럴이 없다', () => {
    const offenders = sources
      /* apiBase.ts 는 개발 폴백을 **소유**한다 — 값이 있어야 하는 유일한 곳. */
      .filter((f) => rel(f) !== 'src/lib/apiBase.ts')
      .map((f) => [rel(f), findDevOrigins(stripComments(readFileSync(f, 'utf8')))] as const)
      .filter(([, hits]) => hits.length > 0)
      .map(([name, hits]) => `${name}: ${hits.join(', ')}`);
    expect(offenders).toEqual([]);
  });
});

/** 번들에 남은 주소처럼 생긴 리터럴. 앞에 스킴 말고 뭐라도 붙어 있으면
 *  브라우저가 상대경로로 읽는다 — 그게 이 검사가 보는 것이다. */
const RE_TSNET_LITERAL = /"([^"\s]*https?:\/\/[^"\s]*ts\.net[^"\s]*)"/g;

describe('API base 의 모양', () => {
  /* 2026-08-20 실화: PowerShell 5.1 에서 값을 파이프로 `vercel env add` 에
   * 넘겼더니 BOM(U+FEFF)이 앞에 붙은 채 저장됐고, 번들에 이렇게 구워졌다:
   *
   *     "\uFEFFhttps://e110430.tailc7b701.ts.net/v2"
   *
   * 절대 URL 로 파싱이 안 되니 브라우저가 상대 경로로 취급했고, 요청이 백엔드가
   * 아니라 사이트 자신에게 가서 `forwards: HTTP 404` 가 났다. 백엔드는 멀쩡했다.
   * 눈에 안 보이는 한 글자가 원인이라 화면만 봐서는 영영 못 찾는다. */

  it('보이지 않는 글자가 앞에 붙어도 걷어 낸다', async () => {
    const { normalizeApiBase } = await import('../src/lib/apiBase');
    const want = 'https://e110430.tailc7b701.ts.net/v2';
    expect(normalizeApiBase('\uFEFF' + want)).toBe(want);
    expect(normalizeApiBase('\u200B' + want)).toBe(want);
    expect(normalizeApiBase('  ' + want + '\n')).toBe(want);
    expect(normalizeApiBase(want + '/')).toBe(want);
    expect(normalizeApiBase('')).toBe('');
  });

  it('절대 주소가 아니면 던진다 — 배포 뒤 404 보다 빌드 실패가 낫다', async () => {
    const { normalizeApiBase } = await import('../src/lib/apiBase');
    for (const bad of ['localhost:8200', '/v2', 'ts.net/v2', 'ftp://x.example.com']) {
      expect(() => normalizeApiBase(bad), bad).toThrow();
    }
  });

  it('청크 판정기가 BOM 붙은 리터럴을 실제로 잡는다', () => {
    // 사고 당시 청크에 실제로 있던 모양 그대로.
    const chunk = 'let a=function(){let e="\\uFEFFhttps://e110430.tailc7b701.ts.net/v2";return e}';
    const found = [...chunk.replace(/\\\\uFEFF/g, '\uFEFF')
      .matchAll(RE_TSNET_LITERAL)].map((m) => m[1]);
    expect(found.length).toBe(1);
    expect(found[0].startsWith('https://')).toBe(false);
    // 그리고 정상 값은 통과한다.
    const ok = 'let e="https://e110430.tailc7b701.ts.net/v2"';
    const good = [...ok.matchAll(RE_TSNET_LITERAL)].map((m) => m[1]);
    expect(good).toEqual(['https://e110430.tailc7b701.ts.net/v2']);
  });

  it('배포된 청크의 값도 같은 검사를 통과한다', () => {
    /* 소스가 옳아도 **구워진 값**이 틀릴 수 있다 — 위 사고가 정확히 그랬다.
     * 청크에서 리터럴을 꺼내 같은 판정기에 건다. */
    const chunks = path.join(ROOT, '.next', 'static', 'chunks');
    /* **dev 산출물이면 안 본다** [2026-09-07] — `pnpm dev` 의 청크에는 치환이
       안 된 값과 에러 메시지 문구가 그대로 들어 있어서, 그걸 «구워진 값» 으로
       읽으면 빨강이 난다. 아래 「산출물」 절과 같은 판정기를 쓴다. */
    if (!existsSync(chunks) || !isProductionBuild()) return;
    const literals = new Set<string>();
    for (const file of walk(chunks, '.js')) {
      const js = readFileSync(file, 'utf8');
      /* 빌드가 치환한 값은 `let e="…"` 꼴로 남는다. 주소처럼 생긴 리터럴만 본다. */
      for (const m of js.matchAll(RE_TSNET_LITERAL)) literals.add(m[1]);
    }
    for (const lit of literals) {
      // 앞에 스킴 말고 다른 것이 붙어 있으면 상대경로가 된다.
      expect(lit.startsWith('http://') || lit.startsWith('https://'), JSON.stringify(lit)).toBe(
        true,
      );
    }
  });
});

/** `.next` 가 **프로덕션 빌드**인가 — `pnpm dev` 가 남긴 것인가.
 *
 *  ★ 이 구분이 없어서 이 가드는 개발 기계에서 **늘 빨강**이었다 [실측 2026-09-07].
 *  `pnpm dev` 도 `.next/static/chunks` 를 채우는데, 그 청크에는 개발 출처가
 *  당연히 들어 있고 `NEXT_PUBLIC_API_BASE` 치환도 안 돼 있다. 가드는 그것을
 *  «배포될 번들» 로 읽고 두 검사를 빨강으로 냈다 — 세션마다 「기존 문제」로
 *  넘겨지다가 오늘 실제로 열어 보니 **가드가 옳았고 대상이 틀렸다**.
 *
 *  같은 날 프로덕션 빌드로 돌리니 18/18 초록이다:
 *      NEXT_PUBLIC_API_BASE=https://<host>.ts.net/v2 pnpm build && pnpm test
 *
 *  **dev 산출물에서는 «건너뛴다»** — 「검사할 게 없었다」와 「검사했더니
 *  깨끗하다」가 다른 사실이라는, 이 파일이 이미 아래에 적어 둔 그 규율의
 *  세 번째 얼굴이다. 빨강으로 두면 진짜 회귀가 묻힌다(오늘 하루 종일 그랬다).
 *
 *  판별: 프로덕션 빌드는 `BUILD_ID` 를 남기고, dev 는 `static/development/` 를
 *  만든다. 둘 다 보는 이유는 실패한 빌드가 중간 상태를 남기기 때문이다. */
function isProductionBuild(): boolean {
  return existsSync(path.join(ROOT, '.next', 'BUILD_ID'))
    && !existsSync(path.join(ROOT, '.next', 'static', 'development'));
}

/** 청크 목록에서 **앱이 만든 것**만 — polyfills 는 빌드가 늘 두는 것이라
 * 그것 하나만 남은 상태는 "검사할 게 없다"이지 "깨끗하다"가 아니다. */
function appChunksOf(files: string[]): string[] {
  return files.filter((f) => !path.basename(f).startsWith('polyfills'));
}

describe('빌드 산출물', () => {
  const chunks = path.join(ROOT, '.next', 'static', 'chunks');
  const built = existsSync(chunks) && isProductionBuild();

  it.skipIf(!built)('청크에 개발 출처가 없다 (프로덕션 빌드가 있을 때만)', () => {
    const offenders: string[] = [];
    for (const file of walk(chunks, '.js')) {
      const hits = findDevOrigins(readFileSync(file, 'utf8'));
      if (hits.length) offenders.push(`${rel(file)}: ${hits.join(', ')}`);
    }
    expect(offenders).toEqual([]);
  });

  it('프로덕션 빌드가 없으면 위 검사는 아무것도 증명하지 않는다', () => {
    /* 이 테스트 자체가 기록이다. 초록을 "번들이 깨끗하다" 로 읽으면 안 되고,
     * 배포 전에는 `pnpm build` **뒤에** `pnpm vitest run` 을 한 번 더 돌린다.
     * 청크는 빌드가 만들고, vitest 는 만들지 않는다.
     *
     * ★ `.next` 가 **있어도** dev 산출물이면 마찬가지다 [2026-09-07]. 그때는
     * 위 검사가 건너뛰므로, 이 줄이 그 사실을 화면에 남긴다. */
    expect(typeof built).toBe('boolean');
    if (existsSync(chunks) && !isProductionBuild()) {
      console.warn(
        '[production-env] `.next` 가 dev 산출물이라 산출물 검사를 건너뛰었어요 — '
        + '배포 전에 `NEXT_PUBLIC_API_BASE=… pnpm build` 뒤에 다시 도세요.',
      );
    }
  });

  /* ── 초록이 거짓말한 실측 [2026-08-21] ──────────────────────────────────
     위 `skipIf(!built)` 는 **디렉터리 유무**만 본다. 그런데 그날 `.next/static/
     chunks` 는 있는데 안에 `polyfills.js` 하나뿐이었다(동시 세션이 빌드 중간에
     비운 상태). 그래서 검사는 **건너뛰지도 않고 돌아서, 아무것도 못 보고
     통과했다** — 직전 실행에서 layout.js·page.js 로 3건 빨강이던 것이 초록이
     됐고, 그 초록은 "고쳐졌다"로 읽힐 뻔했다.

     "검사할 게 없었다"와 "검사했더니 깨끗하다"는 다른 사실이다. 앱 청크가
     없으면 그렇다고 말한다 — 조용한 통과를 남기지 않는다. */
  it('앱 청크가 없으면 위 초록은 "깨끗함"이 아니다 — 조용히 통과하지 않는다', () => {
    if (!built) return; // .next 자체가 없는 경우는 위 테스트가 기록한다
    const js = walk(chunks, '.js');
    expect(
      appChunksOf(js).length > 0,
      `.next/static/chunks 에 앱 청크가 없어요(파일 ${js.length}개). 위 검사는 ` +
        '아무것도 못 봤으니 초록을 "번들이 깨끗하다"로 읽으면 안 돼요 — ' +
        '`pnpm build` 뒤에 다시 도세요.',
    ).toBe(true);
  });

  /* 위 판정을 **음성 쪽으로도** 확인한다. 진짜 `.next` 를 비워서 재보는 것은
     동시 세션의 빌드를 깨뜨리므로(인계서가 두 번 깨졌다고 적은 그 레이스),
     판정기만 떼어 내 가짜 목록에 건다. */
  it('판정기는 polyfills 만 있는 목록을 "앱 청크 없음"으로 읽는다', () => {
    expect(appChunksOf(['/x/polyfills.js'])).toEqual([]);
    expect(appChunksOf(['/x/polyfills-abc123.js'])).toEqual([]);
    expect(appChunksOf([])).toEqual([]);
    expect(appChunksOf(['/x/polyfills.js', '/x/app/page.js'])).toEqual(['/x/app/page.js']);
  });
});
