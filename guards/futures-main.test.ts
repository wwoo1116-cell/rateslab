import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { GROUP_LABEL, type Group, type Row } from '../src/table/rows';
import { toRows, type UniversePayload } from '../src/table/universeRows';
import { BACKTEST_CATEGORIES, itemsOf } from '../src/ui/nav';

/**
 * **국채선물·퓨처스왑이 스왑·현금채권과 같은 분류에 선다** [OWNER, 2026-08-25 —
 * 선물 레인 ④].
 *
 * 2026-08-19 에 국채선물 카테고리는 «가상 데이터» 라는 이유로 내려갔었다. 이번에
 * 되살아나는 근거는 그 이유가 사라졌다는 것이다: 이 분류의 행은 전부 벤더 표에서
 * **읽은** 수이고, 퓨처스왑은 그 벤더 내재금리와 IRS 의 교집합이다.
 *
 * 여기서 재는 것은 셋이다:
 *   ① 분류가 실제로 서는가 (카테고리·탭·라벨)
 *   ② 탭 없는 행이 rows 에 새지 않는가 (커맨드 바가 못 여는 화면으로 점프한다)
 *   ③ 퓨처스왑이 자기 신선도를 읽는가 (두 피드 중 늦은 쪽)
 */

const read = (p: string) => fs.readFileSync(path.join(__dirname, '..', p), 'utf8');
const page = read('src/app/page.tsx');

describe('① 분류가 선다', () => {
  it('Backtest 카테고리에 국채선물이 있고 항목은 두 탭이다', () => {
    const cat = BACKTEST_CATEGORIES.find((c) => c.id === 'futures');
    expect(cat).toBeDefined();
    expect(cat!.groups).toEqual(['futures', 'futuresswap']);
    expect(cat!.label).toBe('국채선물');
  });

  it('두 탭이 라벨·설명·글리프를 다 갖는다 — 빠지면 undefined 가 그려진다', () => {
    const items = itemsOf('futures');
    expect(items.map((i) => i.id)).toEqual(['futures', 'futuresswap']);
    for (const i of items) {
      expect(i.label).toBeTruthy();
      expect(i.desc).toBeTruthy();
      expect(i.glyph).toBeTruthy();
    }
  });

  it('글리프는 그룹마다 다르다 — 두 자산군이 같은 그림을 쓰면 내비가 거짓말한다', () => {
    const nav = read('src/ui/nav.ts');
    const block = nav.slice(nav.indexOf('GROUP_GLYPH'), nav.indexOf('GROUP_DESC'));
    const glyphs = [...block.matchAll(/^\s+\w+: '(.+?)',$/gm)].map((m) => m[1]);
    expect(glyphs.length).toBeGreaterThan(10);
    expect(new Set(glyphs).size).toBe(glyphs.length);
  });

  it('퓨처스왑 라벨은 「퓨처스왑」 — 엔진의 용어 동결과 같은 글자', () => {
    expect(GROUP_LABEL.futuresswap).toBe('퓨처스왑');
    expect(GROUP_LABEL.futures).toBe('국채선물');
  });

  it('URL 게이트(GROUPS)에도 둘 다 있다 — 없으면 딥링크가 조용히 폴백한다', () => {
    const block = page.slice(page.indexOf('const GROUPS'), page.indexOf('const SOURCE_OF'));
    expect(block).toMatch(/'futures',/);
    expect(block).toMatch(/'futuresswap',/);
  });
});

describe('② 탭 없는 행은 새지 않는다', () => {
  const kinds = ['govt', 'credit', 'bss', 'futures', 'futuresswap'] as const;
  const payload = (): UniversePayload => ({
    asof: '2026-08-24',
    rows: kinds.map((k, n) => ({
      id: `X-${k}`,
      label: k,
      kind: k,
      unit: 'bp' as const,
      now: 1,
      deltas: { d1: null, mtd: null, ytd: null },
      range1y: { min: null, max: null, avg: null, pct: null },
      sortKey: [n],
      quoted: true,
      movePct: null,
      key: true,
    })),
    sources: {},
    absent: [],
  });

  /** 페이지가 쓰는 그 게이트를 여기서도 그대로 읽는다 — 두 번 적으면 갈라진다. */
  const GROUPS = [
    ...page
      .slice(page.indexOf('const GROUPS'), page.indexOf('];', page.indexOf('const GROUPS')))
      .matchAll(/'([a-z]+)',/g),
  ].map((m) => m[1] as Group);

  it('kind 는 그대로 group 이 된다 — 어댑터는 산술도 이름 바꾸기도 안 한다', () => {
    const rows = toRows(payload());
    expect(rows.map((r) => r.group)).toEqual([...kinds]);
  });

  it('게이트를 통과하는 것은 선물 둘뿐이다', () => {
    const shown = toRows(payload()).filter((r: Row) => GROUPS.includes(r.group));
    expect(shown.map((r) => r.group)).toEqual(['futures', 'futuresswap']);
  });

  it('페이지가 실제로 그 게이트를 건다 — 필터 없이 이으면 국고까지 딸려 온다', () => {
    expect(page).toMatch(/toRows\(data\.universe\)\.filter\(\(r\) => GROUPS\.includes\(r\.group\)\)/);
  });
});

describe('③ 퓨처스왑은 자기 신선도를 읽는다', () => {
  it('SOURCE_OF 에 항목이 있고 FRESH_KEY 가 자기 이름을 가리킨다', () => {
    /* 선물 항목을 가리키면 IRS 가 하루 밀린 날 헤더가 조용히 신선해 보인다 —
       백엔드가 두 피드 중 **늦은 쪽**으로 자기 항목을 따로 낸다. */
    expect(page).toMatch(/futuresswap: 'universe'/);
    expect(page).toMatch(/futuresswap: 'futuresswap'/);
  });

  it('백엔드가 그 항목을 정말 낸다 — 늦은 쪽(min)으로', () => {
    const u = read('backend/app/universe.py');
    /* ★**철자가 아니라 그 항목이 선다**를 잰다 [고침 2026-10-15]. 이 줄은
       `"futuresswap": {` 였는데, 출처 칸들이 손잡이 하나(`_src(table, date)`)로
       모이면서(전수조사 — 신선도의 자를 하나로) 그 중괄호가 사라져 깨졌다.
       재려던 것은 「백엔드가 이 출처를 정말 내는가」다. */
    expect(u).toMatch(/"futuresswap":\s*_src\(/);
    expect(u).toMatch(/daily_ktb_price × mkt_irs_close/);
    expect(u).toMatch(/fsw_asof = \(min\(fut_asof, idate_last\)/);
  });
});
