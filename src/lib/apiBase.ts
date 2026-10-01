/* 백엔드 주소가 정해지는 **단 한 곳**.
 *
 * 배포 형태 [OWNER, 2026-08-20]: 프런트는 Vercel, 계산은 Tailscale Funnel 로
 * 공개한 :8200 백엔드. 그러면 브라우저가 다른 출처로 나가야 하고, 그 출처를
 * 아는 방법은 빌드 시각에 박히는 `NEXT_PUBLIC_API_BASE` 하나뿐이다.
 *
 * ## 미설정일 때
 *
 * 개발(`next dev`, vitest)에서는 `http://localhost:8200` 으로 떨어진다 — 옆에
 * 백엔드를 띄워 두고 일하는 것이 이 리포의 기본 자세다.
 *
 * **프로덕션 빌드에서 미설정이면 던진다.** v1 의 실제 사고가 이것이었다:
 * 값이 없으면 조용히 localhost 로 떨어지고, 그 문자열이 그대로 번들에 구워져
 * 배포되고, 방문자의 브라우저가 자기 PC 의 :8200 을 두드리다 실패했다. 아무도
 * 안 죽었기 때문에 아무도 몰랐다. 여기서는 `next build` 가 죽는다 —
 * 조용한 잘못보다 시끄러운 실패가 낫다.
 *
 * 백엔드 없이 프로덕션 빌드를 내야 할 때는 **빈 문자열을 명시**한다
 * (`NEXT_PUBLIC_API_BASE=`). 그건 "같은 출처로만 나간다"는 뜻이고
 * (`staticPaths.ts::IS_STATIC`), 백엔드가 필요한 화면은 404 를 받아
 * "백엔드가 필요한 화면이에요" 패널이 된다. 그 선택은 타이핑으로 남는다.
 */

/** `next build`/`next start` 가 켜는 값. vitest 는 `test` 라 여기 안 걸린다. */
const IS_PRODUCTION_BUILD = process.env.NODE_ENV === "production";

/** 미설정 시 개발에서만 쓰는 기본값. 프로덕션에서는 절대 쓰이지 않는다. */
export const DEV_FALLBACK_API_BASE = "http://localhost:8200";

export const MISSING_API_BASE_MESSAGE =
  "NEXT_PUBLIC_API_BASE 가 없습니다. 프로덕션 빌드는 백엔드 주소를 " +
  "빌드 시각에 박아야 하고, 없으면 localhost 로 조용히 떨어지는 대신 여기서 " +
  "멈춥니다. Funnel 주소를 넣거나(예: https://<host>.ts.net), 백엔드 없이 " +
  "굽겠다면 빈 문자열을 명시하세요(NEXT_PUBLIC_API_BASE=).";

export const BAD_API_BASE_MESSAGE =
  "NEXT_PUBLIC_API_BASE 가 http(s) 절대 주소가 아닙니다: ";

/** 값을 쓸 수 있는 모양으로 만들고, 아니면 던진다.
 *
 * 끝의 `/` 를 떼는 것이 원래 하던 일의 전부였다. 2026-08-20 에 하나 더 배웠다:
 * **눈에 안 보이는 글자가 앞에 붙어 들어올 수 있다.** PowerShell 5.1 에서
 * 값을 파이프로 `vercel env add` 에 넘겼더니 BOM(U+FEFF)이 앞에 붙은 채
 * 저장됐고, 번들에는 이렇게 구워졌다:
 *
 *     "\uFEFFhttps://e110430.tailc7b701.ts.net/v2"
 *
 * 그 문자열은 절대 URL 로 파싱되지 않아서 브라우저가 **상대 경로**로 취급한다.
 * 요청이 백엔드가 아니라 사이트 자신에게 가고, 화면에는 이렇게 뜬다:
 *
 *     시장 데이터를 불러오지 못했어요 — forwards: HTTP 404
 *
 * 404 는 "그 라우트가 없다" 는 뜻이라, 읽는 사람은 백엔드를 의심하러 간다.
 * 실제로 백엔드는 멀쩡했다. 그래서 여기서 **모양을 검사하고 빌드를 죽인다** —
 * 배포 뒤의 404 보다 빌드 실패가 낫다는 이 파일의 원칙 그대로다. */
export function normalizeApiBase(raw: string): string {
  /* BOM·제로폭 공백·앞뒤 공백을 걷는다. 사람이 대시보드에 붙여 넣을 때 줄바꿈이
   * 딸려 오는 것도 같은 계열이다. */
  const cleaned = raw.replace(/[\uFEFF\u200B-\u200D]/g, "").trim().replace(/\/+$/, "");
  if (cleaned === "") return "";
  let parsed: URL;
  try {
    parsed = new URL(cleaned);
  } catch {
    throw new Error(BAD_API_BASE_MESSAGE + JSON.stringify(raw));
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error(BAD_API_BASE_MESSAGE + JSON.stringify(raw));
  }
  return cleaned;
}

function resolve(): string {
  /* `process.env.NEXT_PUBLIC_*` 는 번들러가 **텍스트로 치환**한다. 변수에 담아
   * 읽으면 치환이 일어나지 않으므로, 이 한 줄이 리터럴 접근이어야 한다. */
  const raw = process.env.NEXT_PUBLIC_API_BASE;
  if (raw === undefined) {
    if (IS_PRODUCTION_BUILD) throw new Error(MISSING_API_BASE_MESSAGE);
    return DEV_FALLBACK_API_BASE;
  }
  return normalizeApiBase(raw);
}

/** 자료를 부르는 **같은 출처** 접두사. `next.config.ts` 의 rewrite 가 이 경로를
 *  `NEXT_PUBLIC_API_BASE` 로 넘긴다. 두 곳이 같은 문자열을 알아야 해서 양쪽
 *  머리 주석이 서로를 가리킨다(값이 둘로 갈리면 404 가 조용히 난다).
 *
 *  ⚠빈 문자열이 **아니다** — `IS_STATIC`(`staticPaths.ts`)은 빈 문자열일 때만
 *    참이고, 그건 «구운 정적 트리» 라는 다른 뜻이다. 둘을 섞으면 라이브 모드가
 *    정적 파일 이름(`10Y.full.json`)을 부르러 간다. */
const PROXY_PREFIX = "/be";

/**
 * 백엔드의 출처 — **브라우저가 실제로 부르는 것**.
 *
 * ## 왜 같은 출처인가 [2026-10-01, 트레이더 자리에서 자료가 안 왔다]
 *
 * 종전에는 이 값이 Funnel 주소(`https://<host>.ts.net/v2`)였고, 그러면 **보는
 * 사람의 브라우저가 자기 네트워크에서** 그 주소로 나가야 한다. 실측:
 *
 *     화면(rateslab.vercel.app)        200
 *     백엔드(진짜 외부에서)             200   ← `/v2/api/health` 가 정상으로 온다
 *     CORS(rateslab 출처)              허용
 *     그런데 트레이더 자리             자료가 안 옴
 *
 * 남는 변수는 **보는 사람의 네트워크**다(데스크에서 `*.ts.net` 이 막히면 화면은
 * 열리고 자료만 안 온다). 그 변수를 없앤다 — 브라우저는 **이미 화면을 받고 있는
 * 그 출처**만 부르고, Funnel 로 나가는 일은 Vercel 서버가 한다.
 *
 * 부수로 둘이 같이 사라진다: **CORS**(같은 출처라 프리플라이트가 없다)와
 * **BOM 사고의 재발 여지**(브라우저 번들에 외부 주소가 안 구워진다).
 *
 * ⚠`normalizeApiBase` 는 **그대로 둔다** — 상대 경로를 거부하는 그 규칙이 2026-08-20
 *   사고를 잡은 자다(`guards/production-env`). 여기서 바뀐 것은 「검사한 값을
 *   브라우저가 직접 쓰는가」이고, 검사 자체는 안 건드린다.
 * ⚠백엔드 주소가 **아예 없는** 경우(`NEXT_PUBLIC_API_BASE=`)는 종전과 같다 —
 *   빈 문자열이고 `IS_STATIC` 이 참이 되어 구운 트리를 본다. 넘길 곳이 없으니
 *   `next.config.ts` 도 rewrite 를 안 만든다.
 */
export const API_BASE = resolve() === "" ? "" : PROXY_PREFIX;

/** 검사를 통과한 **원래** 주소 — 넘길 곳이 어디인지 적어 두는 자리.
 *  브라우저가 이걸로 요청하지 않는다(설정 화면이 「어디로 넘기나」를 적는 데 쓴다). */
export const BACKEND_ORIGIN = resolve();
