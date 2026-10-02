/* 떠 있는 창의 **기하** — 어디에 서는가. v1 `ui/floatingWindow.ts` 의 규칙을
 * 그대로 옮겼다(값과 근거 포함). 순수 함수라 DOM 없이 검증된다.
 *
 * 창 하나에 자유는 하나: **자리**. 크기 조절도, 최소화도, 두 번째 인스턴스도
 * 없다 — 각각이 제품이 legible 해야 할 상태를 하나씩 늘린다.
 */

export interface WinPos {
  left: number;
  top: number;
}

/** 기본 폭. 내용이 이보다 넓어야 하는 창은 자기 폭을 넘긴다. */
export const WINDOW_W = 980;

/**
 * 끌기 손잡이의 높이 — **뷰포트를 절대 벗어나면 안 되는 띠**다.
 *
 * 이게 클램프의 전부다: 손잡이가 화면 밖으로 나가면 그 창은 **되돌릴 방법이
 * 없다**(끌 수 있는 면이 헤더뿐이므로). 본문은 화면 아래로 흘러도 된다.
 */
export const WINDOW_HEADER_H = 44;

/** 가로는 완전히 안쪽에(뷰포트가 창보다 좁으면 왼쪽에 앵커), 세로는 **헤더가**
 * 완전히 안쪽에. 본문은 접혀 나가도 되고 손잡이는 안 된다. */
export function clampWindowPos(
  pos: WinPos,
  viewport: { w: number; h: number },
  winW: number = WINDOW_W,
): WinPos {
  return {
    left: Math.max(0, Math.min(pos.left, viewport.w - winW)),
    top: Math.max(0, Math.min(pos.top, viewport.h - WINDOW_HEADER_H)),
  };
}

/** 처음 열릴 자리 — 가로 가운데, 위쪽. 표가 아니라 미리보기 pane 위에 뜨도록
 * 해서 목록이 옆에서 계속 쓸 수 있게 둔다. */
export function defaultWindowPos(
  viewport: { w: number; h: number },
  winW: number = WINDOW_W,
): WinPos {
  return clampWindowPos(
    { left: Math.round((viewport.w - winW) / 2), top: 72 },
    viewport,
    winW,
  );
}

/* ── 창마다 자기 자리를 기억한다 ─────────────────────────────────────────────
 *
 * v1 은 처음에 모듈 변수 **하나**였고, 창이 하나일 때만 맞는 모양이었다. 두 번째
 * 창(시뮬레이션)이 생기자 하나를 옮기면 다른 하나가 다음에 열릴 때 거기로 따라
 * 갔다. "읽는 사람이 놓아 둔 자리로 돌아온다" 는 약속은 **창마다** 성립해야
 * 하므로 키를 받는다.
 *
 * **localStorage 가 아니다.** 다른 모니터에서 복원된 위치는 아무도 못 찾는 창이
 * 된다. 세션 메모리(모듈 변수)라 닫았다 열면 그 자리로 오고, 새로고침하면
 * 기본값에서 시작한다. */
export type WindowKey =
  | "chart"
  | "backtest"
  | "cashbond"
  | "simulation"
  | "matrix"
  | "rv"
  | "rvlanes"
  | "mrstrategy"
  /* BSS 테너 통합 장부 [2026-09-01]. 낱개 창(`mrstrategy`)과 **다른 열쇠**다 —
     둘이 같이 열릴 수 있고, 그때 한쪽을 옮기면 다른 쪽이 따라가면 안 된다. */
  | "mrbook"
  /* 페이퍼 북의 트레이드 추적 [OWNER 2026-09-28] — 다리들을 백테스트 엔진에 실어
     진입일부터 분해한 창. 백테스트 창과 **다른 열쇠**다(둘이 같이 열릴 수 있다). */
  | "papertrace"
  /* 포지션(다리) 담기 [OWNER 2026-10-01 — 「포지션 추가할때는 다른탭에서 백테스트
     확인하듯이 새 창 띄워서」]. 추적 창(`papertrace`)과 **다른 열쇠**다 — 추적을
     열어 두고 다음 다리를 담는 일이 있고, 그때 한쪽을 옮기면 다른 쪽이 따라가면
     안 된다. */
  | "paperadd"
  /* Credit RV 후보 비교 [OWNER 2026-10-02 — 「후보 둘셋 비교」]. 이력 단면 창
     (`rv`)과 **다른 열쇠**다 — 후보를 띄워 놓고 한 줄의 이력을 여는 일이 있고,
     그때 한쪽을 옮기면 다른 쪽이 따라가면 안 된다. */
  | "rvpick";

const remembered = new Map<WindowKey, WinPos>();

/** 이 세션에서 기억된 자리, 없으면 이 뷰포트의 기본값. 기억된 자리도 **다시
 * 클램프한다** — 창을 옮겨 두고 브라우저를 줄였을 수 있다. */
export function initialWindowPos(
  viewport: { w: number; h: number },
  key: WindowKey,
  winW: number = WINDOW_W,
): WinPos {
  const seen = remembered.get(key);
  return seen ? clampWindowPos(seen, viewport, winW) : defaultWindowPos(viewport, winW);
}

/** 읽는 사람이 놓아 둔 자리를 적어 둔다(호출부가 이미 클램프한 값). */
export function rememberWindowPos(pos: WinPos, key: WindowKey): WinPos {
  remembered.set(key, pos);
  return pos;
}

/** 테스트 전용 — 세션 기억을 비운다. 이걸 export 하지 않으면 가드가 이전
 * 테스트의 기억을 물려받아 서로를 오염시킨다. */
export function forgetWindowPos(key?: WindowKey): void {
  if (key) remembered.delete(key);
  else remembered.clear();
}
