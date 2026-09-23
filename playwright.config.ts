import { defineConfig, devices } from '@playwright/test';

/**
 * 픽셀 가드의 설정 [OWNER 2026-09-23 · Phase C].
 *
 * ── 왜 이 리포에 브라우저가 필요한가 ────────────────────────────────────────
 *
 * 기존 가드(vitest)는 **소스 텍스트와 DOM 구조**를 읽는다. jsdom 이 CDS 를 안
 * 싣고 레이아웃도 안 하기 때문이고, 그 선택 자체는 근거가 있다. 대가는 폭·틈·
 * 줄바꿈을 **아무도 안 잰다**는 것이었고, 그래서 「✕ 가 혼자 내려간다」가 한 달
 * 넘게 살아 있었다. 그 종류의 결함을 잡을 수 있는 유일한 자리가 여기다.
 *
 * ── 서버는 **밖에서** 띄운다 ────────────────────────────────────────────────
 *
 * `webServer` 로 dev 를 붙잡지 않는다. 이 제품의 프런트는 백엔드(:8299 개발 ·
 * :8200 프로덕션)가 있어야 화면이 서고, 그 기동은 이 파일이 아니라 사람이
 * 정하는 일이다(`BACKEND.md`). 그래서 **이미 떠 있는 :3200 에 붙는다** — 안 떠
 * 있으면 즉시 실패하고, 그 실패 문구가 무엇을 해야 하는지 말한다.
 *
 * ⚠ 이 리포의 의존성은 **pnpm 이 관리한다**(`pnpm-lock.yaml` · `node_modules/.pnpm`).
 * `npm i` 는 arborist 가 그 트리를 못 읽어 `Cannot read properties of null
 * (reading 'matches')` 로 죽는다 — 실측 2026-09-23, 두 번. `pnpm add` 를 쓸 것.
 */
export default defineConfig({
  testDir: './e2e',
  /* 픽셀을 재는 검정이라 **병렬로 돌리지 않는다** — 같은 창을 여럿이 흔들면
     폭이 아니라 경합을 재게 된다. */
  workers: 1,
  fullyParallel: false,
  /* ⚠ `next dev` 의 **첫 컴파일이 16초**다(실측 2026-09-23, 6,299 모듈). 기본
     30초는 첫 검정에서 아슬아슬하게 터져 「접속 실패」로 보이는데, 그건 이
     가드가 재려는 것과 아무 상관이 없는 실패다. 그래서 넉넉히 준다. */
  timeout: 120_000,
  expect: { timeout: 15_000 },
  /* 실패를 재시도로 덮지 않는다. 여기서 흔들리면 그 자체가 보고할 사실이다. */
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.SAURON_E2E_URL ?? 'http://127.0.0.1:3200',
    /* 기하만 잰다 — 색·테마는 이 검정의 대상이 아니다(실측으로 테마가 기하를
       안 바꾸는 것을 확인했다, DESIGN.md §9.5). */
    colorScheme: 'dark',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
