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

/** 백엔드의 출처. 빈 문자열이면 같은 출처(=정적/프록시 모드)라는 뜻이다. */
export const API_BASE = resolve();

/** 첫 자료 적재의 **시한**(ms). 이걸 넘기면 「기다림」이 아니라 「실패」다.
 *
 *  무거운 호출(백테스트)에는 걸지 않는다 — 그건 수십 초가 정상이다. 여기 있는
 *  값은 **화면을 여는 데 필요한 것들**(summary·forwards·vol·universe·health)의
 *  시한이고, 실측으로 그 다섯은 1~2초다. */
export const LOAD_DEADLINE_MS = 20_000;

/**
 * 시한을 넘겼을 때 읽는 사람에게 하는 말 — **어디에 못 닿았는지**를 적는다.
 *
 * ## 왜 이 문구가 따로 필요한가 [2026-10-01, 트레이더 자리]
 *
 * `ui/DataState` 는 「기다림과 실패는 다르게 보여야 한다」로 쓰인 부품이고, 머리에
 * v1 의 사고가 적혀 있다 — **모든 실패가 똑같이 영원한 「불러오는 중」이었고 81초에도
 * 여전히 loading 이었다.** 그런데 그 갈라짐은 fetch 가 **거절할 때만** 듣는다.
 * 방화벽이 패킷을 조용히 버리면 fetch 는 끝나지 않고, 상태는 `loading` 에 머문다.
 * 2026-10-01 에 트레이더 자리에서 본 것이 정확히 그것이다(「시장 데이터를 불러오는
 * 중이에요」만 계속).
 *
 * 그리고 `ErrorState` 의 기본 문구는 「백엔드(:8200)가 응답하지 않았어요」인데,
 * **멀리서 보는 사람에게는 틀린 말**이다 — 그 사람 PC 에는 :8200 이 없다. 그가
 * 확인할 수 있는 사실은 「이 주소에 못 닿았다」 하나다. 그래서 주소를 적는다.
 *
 * ⚠`${API_BASE}` 를 **`lib/` 안에서** 쓴다 — 밖에서 URL 을 다시 조립하는 것을
 *   `guards/production-env` 가 막는다(그 규칙은 v1 사고에서 왔다). 문구도 같은 규율을
 *   따른다: 주소를 아는 곳은 이 파일 하나다.
 */
export async function withDeadline<T>(
  work: Promise<T>,
  ms: number = LOAD_DEADLINE_MS,
): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      work,
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error(unreachableDetail(ms))), ms);
      }),
    ]);
  } finally {
    /* 성공했으면 타이머를 걷는다 — 안 걷으면 ms 뒤에 쓸데없이 한 번 더 깨어나고,
       테스트에서는 그게 「끝나지 않는 테스트」로 보인다. */
    if (timer !== undefined) clearTimeout(timer);
  }
}

export function unreachableDetail(ms: number = LOAD_DEADLINE_MS): string {
  const sec = Math.round(ms / 1000);
  const where = API_BASE === "" ? "이 사이트" : API_BASE;
  return (
    `${where} 에 ${sec}초 안에 못 닿았어요. 백엔드가 꺼져 있거나, ` +
    `지금 보고 있는 자리의 네트워크·방화벽이 그 주소를 막고 있을 수 있어요 ` +
    `(화면은 떠 있으니 자료 경로만 막힌 것입니다).`
  );
}

/** ⚠**임시 진단**(`app/api/probe`)이 때릴 주소 — 주소를 아는 곳은 이 파일 하나다
 *  (`guards/production-env`: 「NEXT_PUBLIC_API_BASE 를 읽는 파일은 하나다」 ·
 *   「lib/ 밖에서 백엔드 URL 을 다시 조립하지 않는다」). 그 규칙이 이 진단 라우트를
 *  **그 자리에서 잡았다** — 라우트가 `process.env` 를 직접 읽고 URL 을 이어 붙였다.
 *  ★쓰고 나면 라우트와 함께 지운다. */
export function probeTargets(): string[] {
  return ["/api/health", "/api/instruments"].map((p) => API_BASE + p);
}
