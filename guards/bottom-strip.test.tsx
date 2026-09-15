import fs from 'node:fs';
import path from 'node:path';

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ANCHOR_IDS, BottomStrip, STRIP_H } from '@/ui/BottomStrip';
import type { Row } from '@/table/rows';

/**
 * 띠는 **세 기준점**이고, 그 셋이 이 제품의 세 가지 읽는 법이다.
 *
 * 가장 값나가는 검사는 마지막 둘이다. ① 앵커 id 가 행 빌더가 실제로 만드는 id 와
 * 같은가 — 다르면 띠는 조용히 **비어 있게** 되고, 빈 띠는 아무 오류도 안 낸다.
 * ② 눌렀을 때 **탭까지** 옮기는가 — 그 종목이 없는 탭에서 행만 선택하면 화면에
 * 아무 일도 안 일어난다.
 */

const ROOT = path.resolve(import.meta.dirname, '..');

function row(id: string, group: Row['group'], now: number, d1: number): Row {
  return {
    id,
    label: id,
    group,
    unit: '%',
    now,
    changes: { d1, mtd: null, ytd: null },
    pct: null,
    seriesId: id,
    rangeHigh: null,
    rangeLow: null,
    rangeAvg: null,
    sortKey: [0],
    movePct: null,
    key: true,
    theta: null,
  };
}

const ROWS = [
  row('10Y', 'outright', 2.47, -7),
  row('3Y-10Y', 'spread', 0.21, 1.5),
  row('1Yx1Y', 'forward', 2.31, 0),
  row('5Y', 'outright', 2.4, -3),
];

beforeEach(() => {
  localStorage.clear();
});

/* ⚠ 제목 문구는 2026-09-15 에 바뀌었다 — 「3Y-10Y(으)로 이동」이라는 회피형이
   낭독기에 「…(으)로」로 그대로 읽혔다. 이제 `lib/josa.euro` 가 앞말의 받침을
   보고 「로/으로」를 정한다(「10Y」는 «십와이» 라 받침이 없어 「로」). */
describe('하단 기준점 띠', () => {
  it('수준·기울기·포워드 하나씩을 든다', () => {
    expect(ANCHOR_IDS).toEqual(['10Y', '3Y-10Y', '1Yx1Y']);
  });

  it('세 앵커만 그린다 — 다른 행은 안 온다', () => {
    render(<BottomStrip rows={ROWS} onPin={() => {}} collapsed={false} onCollapsed={() => {}} />);
    expect(screen.getByText('10Y')).toBeTruthy();
    expect(screen.getByText('3Y-10Y')).toBeTruthy();
    expect(screen.getByText('1Yx1Y')).toBeTruthy();
    expect(screen.queryByText('5Y')).toBeNull();
  });

  it('앵커를 누르면 행 **과 탭**이 함께 온다', () => {
    const pinned: Row[] = [];
    render(
      <BottomStrip rows={ROWS} onPin={(r) => pinned.push(r)} collapsed={false} onCollapsed={() => {}} />,
    );
    fireEvent.click(screen.getByTitle('3Y-10Y로 이동'));
    expect(pinned).toHaveLength(1);
    // 그룹이 실려 와야 호출부가 탭을 옮길 수 있다.
    expect(pinned[0].group).toBe('spread');
    expect(pinned[0].id).toBe('3Y-10Y');
  });

  it('앵커가 하나도 없으면 띠를 안 세운다', () => {
    // 빈 띠는 "값이 없다" 가 아니라 "고장났다" 로 읽힌다.
    const { container } = render(
      <BottomStrip rows={[row('5Y', 'outright', 2.4, -3)]} onPin={() => {}} collapsed={false} onCollapsed={() => {}} />,
    );
    expect(container.querySelector('.sr-strip')).toBeNull();
  });

  it('접혀도 두 겹이 **둘 다 마운트**된 채로 남는다', () => {
    // 서브트리를 갈아 끼우면 높이 애니메이션 중간에 내용이 사라져 결함으로 보인다.
    const { container } = render(
      <BottomStrip rows={ROWS} onPin={() => {}} collapsed onCollapsed={() => {}} />,
    );
    expect(container.querySelector('.sr-strip-row')).not.toBeNull();
    expect(container.querySelector('.sr-strip-handle')).not.toBeNull();
    expect((container.querySelector('.sr-strip') as HTMLElement).style.height).toBe(
      `${STRIP_H.collapsed}px`,
    );
  });

  it('접힌 줄은 클릭을 안 먹는다', () => {
    const { container } = render(
      <BottomStrip rows={ROWS} onPin={() => {}} collapsed onCollapsed={() => {}} />,
    );
    // inert 가 없으면 흐려진 줄이 그 아래 손잡이로 가는 클릭을 가로챈다.
    expect(container.querySelector('.sr-strip-row')?.hasAttribute('inert')).toBe(true);
  });

  it('접힘을 localStorage 에 기억한다', () => {
    const set = vi.fn();
    render(<BottomStrip rows={ROWS} onPin={() => {}} collapsed={false} onCollapsed={set} />);
    fireEvent.click(screen.getByTitle('지표 바 접기'));
    expect(set).toHaveBeenCalledWith(true);
  });

  it('compact 경계의 높이가 띠의 펼친 높이와 같다', () => {
    // 두 숫자가 다른 파일에 떨어져 있어 한쪽만 고치면 결함 한 줄이 레이아웃을 민다.
    const css = fs.readFileSync(path.join(ROOT, 'src', 'theme', 'type.css'), 'utf8');
    const block = /\.sr-eb-compact\s*\{[^}]*\}/.exec(css)?.[0] ?? '';
    expect(block).toContain(`height: ${STRIP_H.open}px`);
  });

  it('페이지가 띠를 **모든 탭**에서 세운다', () => {
    const page = fs.readFileSync(path.join(ROOT, 'src', 'app', 'page.tsx'), 'utf8');
    expect(page).toContain('<BottomStrip');
    // `shown`(현재 탭의 행)을 주면 포워드 탭에서 10Y 가 사라진다.
    const usage = /<BottomStrip[\s\S]*?\/>/.exec(page)?.[0] ?? '';
    expect(usage).toContain('rows={rows}');
  });
});
