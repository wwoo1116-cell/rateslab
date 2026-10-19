/**
 * jsdom gaps the components actually depend on.
 *
 * These are STUBS, not implementations, and the distinction matters: they let a
 * component mount so its STRUCTURE can be asserted. Nothing here produces real
 * geometry, so no test may assert a pixel measurement — that is what the browser
 * probes in the reports are for.
 */

if (typeof globalThis.ResizeObserver === 'undefined') {
  // `InstrumentTable` measures its container to drive the column ladder.
  // Never firing is the honest stub: width stays 0, so the ladder falls back to
  // ALL_COLUMNS, which is the state the ladder guard already covers directly.
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

if (typeof globalThis.requestAnimationFrame === 'undefined') {
  globalThis.requestAnimationFrame = ((cb: FrameRequestCallback) =>
    setTimeout(() => cb(0), 0) as unknown as number) as typeof requestAnimationFrame;
  globalThis.cancelAnimationFrame = ((id: number) =>
    clearTimeout(id as unknown as NodeJS.Timeout)) as typeof cancelAnimationFrame;
}

/* `CSS.escape` — 브라우저엔 2015년부터 있고 jsdom 엔 없다. `InstrumentTable` 의
 * 초점 복원·화살표 이동이 **행 id 로 선택자를 조립**할 때 쓴다(id 가 `IRC-1Y-3Y`
 * 같은 자유 문자열이라 escape 가 필요하다).
 *
 * ★이 공백이 2026-10-19 까지 안 보였던 까닭: 그 선택자를 쓰는 초점 복원 효과는
 * 「초점이 표 안에 있으면 건드리지 않는다」로 **이른 반환**을 하고, 시험에서는
 * 초점이 늘 표 밖이어서 그 줄에 한 번도 안 닿았다. roving tabindex 가 같은
 * 선택자를 표 **안에서** 부르자 비로소 드러났다.
 *
 * 스펙을 그대로 옮기지 않는다. 여기서 필요한 것은 선택자에 넣어도 **같은 요소를
 * 찾는 꼴**이고, 식별자로 안전한 문자만 통과시켜 나머지를 역슬래시로 덮으면
 * 그 일은 끝난다(스펙의 16진수 + 공백 꼴은 선택자 매칭 결과가 같다).
 *
 * ⚠ 안전 집합의 상한을 **코드포인트로** 적는다 — 첫 판은 그 자리에 글자를 그대로
 * 넣었고, 보이지 않는 U+00A0 과 U+FFFF 가 소스에 박혀 읽을 수도 고칠 수도 없게
 * 됐다. 같은 판에서 치환값의 역슬래시도 한 겹 먹혀 `${c}` 를 **문자 그대로**
 * 내보내고 있었는데, 시험 행 id 가 `R0` 라 치환이 한 번도 안 일어나 초록이었다.
 * 그래서 아래 문자열은 템플릿이 아니라 **이어 붙이기**다. */
const CSS_SAFE = /[^A-Za-z0-9_\u0080-\uFFFF-]/g;

if (typeof globalThis.CSS === 'undefined') {
  globalThis.CSS = {} as typeof globalThis.CSS;
}
if (typeof globalThis.CSS.escape !== 'function') {
  globalThis.CSS.escape = ((v: string) =>
    String(v).replace(CSS_SAFE, (c) => '\\' + c)) as typeof CSS.escape;
}
