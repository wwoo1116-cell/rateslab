/* 크레딧 RV (DTS) — **산 값으로 그려 본다** [OWNER 2026-10-02].
 *
 * ## 왜 소스를 훑는 가드 하나로 안 끝나나
 *
 * 짝가드 `lab-credit-dts.test.ts` 는 축 계약과 키보드 문법을 **소스와 순수
 * 함수**로 잰다. 그게 잡지 못하는 것이 있다 — **그려 보면 터지는 것**.
 *
 * 이 리포에 그 전례가 있다 [2026-09-22]: 엔진 사유가 422 로 옷을 갈아입는데
 * 픽스처가 다른 예외를 던져 **시험만 초록이었다**. 결론은 한 줄로 남았다 —
 * **「산 값으로 재야 안다」**. 그래서 픽스처가 손으로 지은 숫자가 아니라
 * `GET /api/lab/creditdts` 의 **실제 응답**이다(`lab-credit-dts.live.json`,
 * 2026-10-02 · 120칸 · 제외 0 · 2.56초).
 *
 * 이 파일이 실제로 잡는 것 셋:
 *   ① `useMeasure` 의 콜백 ref 가 CDS `Box` 를 지나 DOM 에 닿는가 — 안 닿으면
 *      그림이 폴백 520×360 에 **영원히 멈추는데 아무 경고도 안 난다**.
 *   ② 화살표가 정말 커서를 옮기는가 — 소스에 `case 'ArrowUp'` 이 있는 것과
 *      그것이 커서를 옮기는 것은 다른 사실이다.
 *   ③ 서버가 센 **랭크 순서**가 화면의 줄 순서와 같은가(§16).
 *
 * jsdom 은 레이아웃을 안 재서 `clientWidth` 가 0 이다 — 그래서 ①은 「ref 가
 * 붙었는가」까지만 잴 수 있고, 치수 자체는 브라우저 실측의 몫이다. 그 한계를
 * 적어 두는 것이 모르는 척하는 것보다 낫다.
 */

import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '@coinbase/cds-web';

import live from './lab-credit-dts.live.json';
import { CreditDtsPage } from '../src/lab/creditdts/CreditDtsPage';
import { sauronTheme } from '../src/theme/sauronTheme';

/* 실패 패널의 재시도 버튼이 CDS `Button` 이고 그것이 `useTheme` 을 요구한다 —
 * 렌더는 앱과 같은 테마 아래에서(`providers.tsx` 의 그 구성). 사분면·표는
 * 프로바이더 없이도 서는데, **한 벌로 감싸는 쪽**이 맞다: 테마를 요구하는
 * 부품이 하나 늘어난 날 그 가지만 조용히 터지는 것을 막는다. */
function rtl(ui: React.ReactElement) {
  return render(
    <ThemeProvider theme={sauronTheme} activeColorScheme="light">
      {ui}
    </ThemeProvider>,
  );
}

/** 서버가 낸 1·2·120 등 — 픽스처에서 **읽어 온다**(손으로 적으면 갈린다). */
const byRank = [...live.items].sort((a, b) => a.rank - b.rank);
const first = byRank[0]!;
const second = byRank[1]!;
const last = byRank[byRank.length - 1]!;

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(live), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function mount() {
  const u = rtl(<CreditDtsPage />);
  /* 라이브 전용 화면이라 첫 프레임은 「불러오는 중」이다. */
  await screen.findByRole('application');
  return u;
}

describe('산 응답으로 화면이 선다', () => {
  it('머리가 서버가 적어 준 말을 옮긴다 — 화면이 근거를 지어내지 않는다', async () => {
    await mount();
    expect(screen.getByText(new RegExp(`민평 ${live.asof}`))).toBeTruthy();
    expect(screen.getByText(new RegExp(`${live.items.length}칸`))).toBeTruthy();
    expect(screen.getByText(new RegExp(live.basis.slice(0, 18)))).toBeTruthy();
  });

  it('랭킹 줄 순서 = **서버가 센 랭크** 순서다 (§16)', async () => {
    await mount();
    const rows = screen.getAllByRole('row').slice(1); // 머리 한 줄 제외
    expect(rows).toHaveLength(live.items.length);
    const firstCells = within(rows[0]!).getAllByRole('cell');
    expect(firstCells[0]!.textContent).toBe(String(first.rank));
    expect(firstCells[1]!.textContent).toContain(first.sectorLabel);
    expect(firstCells[1]!.textContent).toContain(first.tenor);
    const lastCells = within(rows[rows.length - 1]!).getAllByRole('cell');
    expect(lastCells[0]!.textContent).toBe(String(last.rank));
  });

  it('음수 z 가 **U+2212** 로 적힌다 — ASCII 하이픈이 아니다', async () => {
    await mount();
    /* 꼴찌는 z 가 음수다(산 응답에서 확인). 손 `toFixed` 로 적었던 첫 판이
       여기서 하이픈을 냈다. */
    expect(last.z).toBeLessThan(0);
    const rows = screen.getAllByRole('row').slice(1);
    const cells = within(rows[rows.length - 1]!).getAllByRole('cell');
    const zText = cells[4]!.textContent!;
    expect(zText.charCodeAt(0)).toBe(0x2212);
    expect(zText).not.toContain('-');
  });

  it('그림은 **탭 정지 한 칸**이고 측정 상자에 ref 가 붙는다', async () => {
    await mount();
    const plot = screen.getByRole('application');
    expect(plot.getAttribute('tabindex')).toBe('0');
    expect(plot.getAttribute('aria-label')).toMatch(/화살표/);
    /* ①의 잴 수 있는 만큼 — `useMeasure` 가 붙은 상자가 그림의 부모로 실재하고
       그림이 그 안에 있다(ref 가 CDS Box 를 지나 DOM 에 닿았다는 뜻).
       jsdom 은 치수를 안 재므로 폭·높이는 브라우저 실측의 몫이다. */
    expect(plot.parentElement).toBeTruthy();
    expect(plot.parentElement!.tagName).toBe('DIV');
    // 점마다 보이는 원 + 고리 없음 + 판정 원 — 판정은 120개 다 선다.
    expect(plot.querySelectorAll('circle.sr-quad-hit')).toHaveLength(live.items.length);
  });

  it('짚은 것이 없으면 리드아웃이 **1등**을 읽는다 — 빈 상태가 없다', async () => {
    await mount();
    const strip = document.querySelector('.sr-readout-strip')!;
    expect(strip).toBeTruthy();
    expect(strip.textContent).toContain(`${first.sectorLabel} ${first.tenor}`);
    expect(strip.textContent).toContain(`${first.rank}위`);
  });
});

describe('화살표가 정말 커서를 옮긴다', () => {
  it('↓ 는 **순위**를 한 칸 내린다 — 1등에서 2등으로', async () => {
    const { container } = await mount();
    const plot = screen.getByRole('application');
    const { fireEvent } = await import('@testing-library/react');
    fireEvent.keyDown(plot, { key: 'ArrowDown' });
    /* 아직 아무것도 안 짚은 상태에서 들어오면 **첫 칸**부터다. */
    expect(container.querySelector('.sr-rv-row[data-on="true"]')!.textContent)
      .toContain(first.sectorLabel);
    fireEvent.keyDown(plot, { key: 'ArrowDown' });
    const on = container.querySelector('.sr-rv-row[data-on="true"]')!;
    expect(on.textContent).toContain(`${second.sectorLabel} ${second.tenor}`);
    // 리드아웃과 낭독 줄이 같은 것을 읽는다.
    expect(document.querySelector('.sr-readout-strip')!.textContent)
      .toContain(`${second.rank}위`);
    expect(document.querySelector('.sr-a11y-only[aria-live="polite"]')!.textContent)
      .toContain(`${second.rank}위`);
  });

  it('→ 는 **스프레드 폭** 순서를 돈다 — 순위 순서가 아니다', async () => {
    const { container } = await mount();
    const plot = screen.getByRole('application');
    const { fireEvent } = await import('@testing-library/react');
    fireEvent.keyDown(plot, { key: 'ArrowRight' });
    const narrowest = [...live.items]
      .sort((a, b) => a.nowBp - b.nowBp || a.seriesId.localeCompare(b.seriesId))[0]!;
    /* ★축이 둘이라는 사실이 여기서 드러난다: ↓ 가 짚는 1등과 → 가 짚는 가장
       좁은 칸이 **다른 종목**이다(산 응답에서 그렇다). 한 순서로 네 방향을
       처리했으면 이 시험이 빨개진다. */
    expect(narrowest.seriesId).not.toBe(first.seriesId);
    expect(container.querySelector('.sr-rv-row[data-on="true"]')!.textContent)
      .toContain(`${narrowest.sectorLabel} ${narrowest.tenor}`);
  });

  it('Home 은 1등, Esc 는 놓는다', async () => {
    const { container } = await mount();
    const plot = screen.getByRole('application');
    const { fireEvent } = await import('@testing-library/react');
    fireEvent.keyDown(plot, { key: 'End' });
    expect(container.querySelector('.sr-rv-row[data-on="true"]')!.textContent)
      .toContain(last.sectorLabel);
    fireEvent.keyDown(plot, { key: 'Home' });
    expect(container.querySelector('.sr-rv-row[data-on="true"]')!.textContent)
      .toContain(first.sectorLabel);
    fireEvent.keyDown(plot, { key: 'Escape' });
    expect(container.querySelector('.sr-rv-row[data-on="true"]')).toBeNull();
    /* 놓으면 낭독 줄은 조용해지고, 리드아웃은 1등으로 돌아간다(빈 상태 없음). */
    expect(document.querySelector('.sr-a11y-only[aria-live="polite"]')!.textContent)
      .toBe('');
    expect(document.querySelector('.sr-readout-strip')!.textContent)
      .toContain(`${first.rank}위`);
  });

  it('끝에서 **감싸지 않는다** — 같은 자리를 계속 돌지 않게', async () => {
    const { container } = await mount();
    const plot = screen.getByRole('application');
    const { fireEvent } = await import('@testing-library/react');
    fireEvent.keyDown(plot, { key: 'Home' });
    fireEvent.keyDown(plot, { key: 'ArrowUp' });
    fireEvent.keyDown(plot, { key: 'ArrowUp' });
    expect(container.querySelector('.sr-rv-row[data-on="true"]')!.textContent)
      .toContain(first.sectorLabel);
  });

  it('조합키가 눌린 화살표는 **안 듣는다** — 브라우저 것이다', async () => {
    const { container } = await mount();
    const plot = screen.getByRole('application');
    const { fireEvent } = await import('@testing-library/react');
    fireEvent.keyDown(plot, { key: 'ArrowDown', ctrlKey: true });
    expect(container.querySelector('.sr-rv-row[data-on="true"]')).toBeNull();
  });
});

describe('백엔드가 없으면 그 사실을 말한다', () => {
  it('404 는 「백엔드가 필요한 화면」으로 바뀐다 — 파싱 오류가 아니라', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 404 })));
    rtl(<CreditDtsPage />);
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('민평이 SQL 에만 있어서');
  });
});
