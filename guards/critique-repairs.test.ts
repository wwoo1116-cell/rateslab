import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * 2026-08-19 전체 앱 크리틱(30/40)의 수리 여섯이 되돌아가지 않게 하는 핀.
 * 각 수리의 "왜"는 코드의 주석이 지고, 여기는 그 주석이 가리키는 사실이
 * 소스에 남아 있는지만 본다.
 */

const ROOT = path.resolve(import.meta.dirname, '..');
const read = (rel: string) => fs.readFileSync(path.join(ROOT, rel), 'utf8');

describe('critique repairs, 2026-08-19', () => {
  it('핀 행: aria-current 가 상태·시각 둘 다 진다 (aria-selected 는 은퇴)', () => {
    const table = read('src/table/InstrumentTable.tsx');
    // role=table 의 행에서 aria-selected 는 무효 — 접근성 트리에 안 잡힌다.
    expect(table).not.toContain('aria-selected={row.id');
    expect(table).toContain("aria-current={row.id === selectedId ? 'true' : undefined}");
    const css = read('src/theme/type.css');
    expect(css).toMatch(/tr\[aria-current='true'\] > td \{\s*background: var\(--sr-control\)/);
  });

  it('점프가 표를 스크롤한다 — 가상화 인덱스로, 이미 보이면 안 움직인다', () => {
    const table = read('src/table/InstrumentTable.tsx');
    expect(table).toContain("virtualizer.scrollToIndex(selectedIndex, { align: 'auto' })");
  });

  it('메가메뉴 스크림이 곧 닫기 표면이다', () => {
    const nav = read('src/ui/TopNav.tsx');
    expect(nav).toMatch(/sr-megascrim[\s\S]{0,80}onClick=\{\(\) => setOpen\(null\)\}/);
  });

  it('커맨드 바는 은퇴했다 [OWNER] — 부품·CSS·이벤트 전부', () => {
    expect(fs.existsSync(path.join(ROOT, 'src/ui/CommandBar.tsx'))).toBe(false);
    const css = read('src/theme/type.css');
    expect(css).not.toContain('sr-cmd');
    expect(css).not.toContain('sr-navslash');
    const nav = read('src/ui/TopNav.tsx');
    expect(nav).not.toContain('sr-commandbar');
  });

  /* ⚠ 이 시험은 2026-09-15 에 «무엇을 재는지» 가 바뀌었다.
   *
   * 원래는 `<TableCell>` 의 `aria-label` 문자열을 찾았다. 그런데 그 라벨은
   * `<th>` 로 가고, **누르는 것은 CDS 가 그 안에 그리는 `<button>`** 이다. 실제
   * DOM 을 열어 보니 버튼 이름은 여전히 `"1D󰟃󰞷"` 였다 — 수리가 한 단계 위에
   * 붙어 있었고, 시험은 그 잘못된 자리를 고정하고 있었다.
   *
   * 이제 재는 것은 두 가지다: 글리프가 `aria-hidden` 으로 이름에서 빠지는가,
   * 그리고 사람 말이 **버튼 안에** 있는가(`.sr-a11y-only` 는 화면에서만 숨고
   * 접근성 트리에는 남는 clip 수법이다). */
  it('정렬 버튼의 접근 이름은 사람 말이다 (PUA 글리프가 이름에 못 들어간다)', () => {
    const table = read('src/table/InstrumentTable.tsx');
    // 글리프는 장식 — 이름 계산에서 빠진다
    expect(table).toContain('end={<span aria-hidden="true">{end}</span>}');
    // 사람 말은 버튼의 자식이라 이름이 된다
    expect(table).toMatch(/<span className="sr-a11y-only">\s*변화 — 눌러서 정렬<\/span>/);
    // 라벨을 다시 <th> 로 올리지 않는다 — 그러면 버튼 이름이 또 글리프가 된다
    expect(table).not.toContain('aria-label={`${BASIS_LABEL[b]} 변화 — 눌러서 정렬`}');
  });

  /* 2026-09-15 에 IRS 북이 따로 동결되어 등록 북이 **둘**이 됐고, 09-21 에 이 면이
   * 그중 IRS 판으로 갈아탔다. 이름을 안 적으면 어느 등록의 성적인지 못 읽는다 —
   * 실제로 그 혼동이 났다. 화면이 그 이름과 동결일을 적는지 잰다. */
  it('Momentum 면은 어느 등록 북을 비추는지 적는다', () => {
    // 이름은 **서버가** 낸다 — 동결일을 클라이언트가 다시 적으면 두 번째 진실이 된다.
    const page = read('src/momentum/MomentumPage.tsx');
    expect(page).toContain('sheet.registry.freeze');
    expect(page).toContain('sheet.registry?.instrument');
    expect(page).toContain('sheet.registry?.note');
    const server = read('backend/app/momentum.py');
    expect(server).toMatch(/"registry":[\s\S]{0,200}"instrument": "국채선물"/);
    expect(server).toMatch(/별개의 북/);
  });

  it('확대 창 안에서는 pane 이 이름을 다시 그리지 않는다', () => {
    const pane = read('src/ui/PreviewPane.tsx');
    expect(pane).toMatch(/chartOnly \? \(\s*<span aria-hidden="true" \/>/);
  });

  it('시뮬 스트림의 에러 페이로드를 프런트가 읽는다', () => {
    const api = read('src/sim/api.ts');
    expect(api).toContain('"detail" in parsed');
  });

  it('컨트롤 등고 32 [OWNER "가로세로 얼라인"] — 우측 유틸리티 줄과 제목 줄 트리거', () => {
    const css = read('src/theme/type.css');
    expect(css).toMatch(/\.sr-naviconbtn \{[^}]*height: 32px/);
    expect(css).toMatch(/\.sr-clog-trigger \{[^}]*height: 32px/);
    // 제목 줄 우측의 창 트리거는 CDS Button(36)이 아니라 32px pill 문법이다.
    const page = read('src/app/page.tsx');
    expect(page).not.toMatch(/<Button[^>]*>\s*백테스트/);
    expect(page).toMatch(/className="sr-pillbtn"[\s\S]{0,200}백테스트/);
    expect(page).toMatch(/className="sr-pillbtn"[\s\S]{0,80}표로 보기/);
  });
});
