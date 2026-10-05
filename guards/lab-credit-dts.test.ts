/* 크레딧 RV (DTS) — Lab 세입자의 **축 계약과 키보드 문법** [OWNER 2026-10-02].
 *
 * ## 이 파일이 지는 명제
 *
 * **축이 이 레인의 본체다.** [OWNER] 「기존 사분면은 반영을 제대로 못 하고
 * 있었어서 … 지금 이 사분면을 제대로 고칠 수 있으면 그게 더 나을듯」 — 제품
 * 사분면이 「제대로 반영을 못 한」 까닭은 **그린 두 축이 점수의 입력이 아니었다는
 * 것**이다(x=월환산 총수익 · y=지난주 백분위인데 Score 는 `spreadVolPct ×
 * relRv`). 그래서 그림과 순위가 따로 놀았다.
 *
 * 여기서는 **세로가 곧 순위**(y = z = 점수 그 자체)이고 가로는 **점수에서
 * 일부러 뺀 것**(x = 지금 스프레드 = 캐리의 대리)이다. 그 선택이 조용히
 * 뒤집히는 것을 막는 것이 이 가드의 일이다 — 축을 바꾸면 그림은 여전히 예쁘게
 * 그려지고, 아무도 빨개지지 않는다.
 *
 * 그래서 산술을 컴포넌트에서 **떼어 뒀다**(`src/lab/creditdts/quadrant.ts`).
 * 렌더해야 재는 축 계약은 재지 않게 되고, 재지 않는 계약은 계약이 아니다
 * (`lab/irs/api.ts::mergeIrs` 를 떼어 낸 그 이유와 같다).
 *
 * ## 왜 키보드까지 여기서 재나
 *
 * CLAUDE.md «키보드와 접근성» 1·6·7 이 요구하는 네 개 한 벌(`role` ·
 * `tabIndex` · `onKeyDown` · 화살표를 적은 `aria-label`)과 낭독 줄·24px 판정을
 * 잰다. 터미널 쪽 같은 검사는 `guards/terminal-keyboard.test.ts` 에 있는데 그
 * 파일의 `read()` 가 `src/terminal` 에 뿌리를 박고 있어 Lab 파일을 그 목록에
 * 넣을 수 없다. 규칙을 옮겨 적는 대신 **같은 네 개를 여기서 잰다**.
 *
 * ⚠ 확대 키(`+`·`−`·`0`)는 **안 잰다** — 이 그림은 확대가 없다. 터미널 규칙의
 * 「축마다 같다」는 확대가 있는 축들 사이의 규칙이고, 없는 기능을 요구하면
 * 가드가 거짓말을 시킨다.
 */

import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments } from './_source';
import {
  median,
  quadrantCounts,
  quadrantGeometry,
  spearman,
} from '../src/lab/creditdts/quadrant';
import type { CreditDtsItem } from '../src/lab/creditdts/api';
import { DEFAULT_LAB, LAB_ITEMS, isLabId, resolveLab } from '../src/ui/nav';

const ROOT = path.resolve(import.meta.dirname, '..');
const read = (rel: string) => stripComments(fs.readFileSync(path.join(ROOT, rel), 'utf8'));

const PAGE = 'src/lab/creditdts/CreditDtsPage.tsx';

function item(over: Partial<CreditDtsItem> & { seriesId: string }): CreditDtsItem {
  return {
    sector: 'CB1',
    sectorLabel: '회사채 AAA',
    tenor: '3Y',
    years: 3,
    nowBp: 50,
    meanBp: 45,
    denomBp: 50,
    floored: false,
    z: 0.1,
    rank: 1,
    ...over,
  };
}

describe('사분면 — 세로가 점수고 가로가 캐리다', () => {
  it('z 가 큰 칸이 **위**에 선다 — 세로 위치가 곧 순위다', () => {
    const cheap = item({ seriesId: 'A', nowBp: 40, z: 0.30 });
    const rich = item({ seriesId: 'B', nowBp: 40, z: -0.20 });
    const geo = quadrantGeometry([cheap, rich], 520, 360);
    const a = geo.points.find((p) => p.id === 'A')!;
    const b = geo.points.find((p) => p.id === 'B')!;
    // SVG 의 y 는 아래로 증가한다 — 「위」는 작은 cy 다.
    expect(a.cy).toBeLessThan(b.cy);
  });

  it('스프레드가 넓은 칸이 **오른쪽**에 선다', () => {
    const tight = item({ seriesId: 'A', nowBp: 20, z: 0.1 });
    const wide = item({ seriesId: 'B', nowBp: 90, z: 0.1 });
    const geo = quadrantGeometry([tight, wide], 520, 360);
    expect(geo.points.find((p) => p.id === 'A')!.cx)
      .toBeLessThan(geo.points.find((p) => p.id === 'B')!.cx);
  });

  /* ★이 둘이 축을 **못 바꾸게** 한다. 축을 서로 섞으면(가로에 z 를 넣는 등)
     아래 둘 중 하나가 반드시 빨개진다 — 「그림은 그려지는데 축이 뒤바뀐」
     상태를 통과시키지 않는다. */
  it('가로는 z 를 **안 본다** — z 만 바꾸면 cx 가 한 픽셀도 안 움직인다', () => {
    const base = [
      item({ seriesId: 'A', nowBp: 20, z: 0.30 }),
      item({ seriesId: 'B', nowBp: 60, z: 0.10 }),
      item({ seriesId: 'C', nowBp: 90, z: -0.20 }),
    ];
    const moved = base.map((i) => ({ ...i, z: i.z * 3 - 1 }));
    const a = quadrantGeometry(base, 520, 360);
    const b = quadrantGeometry(moved, 520, 360);
    for (const p of a.points) {
      expect(b.points.find((q) => q.id === p.id)!.cx, p.id).toBe(p.cx);
    }
  });

  it('세로는 스프레드를 **안 본다** — nowBp 만 바꾸면 cy 가 안 움직인다', () => {
    const base = [
      item({ seriesId: 'A', nowBp: 20, z: 0.30 }),
      item({ seriesId: 'B', nowBp: 60, z: 0.10 }),
      item({ seriesId: 'C', nowBp: 90, z: -0.20 }),
    ];
    const moved = base.map((i) => ({ ...i, nowBp: i.nowBp * 2 + 5 }));
    const a = quadrantGeometry(base, 520, 360);
    const b = quadrantGeometry(moved, 520, 360);
    for (const p of a.points) {
      expect(b.points.find((q) => q.id === p.id)!.cy, p.id).toBe(p.cy);
    }
  });
});

describe('경계선 둘 — 가로는 중앙값, 세로는 0', () => {
  it('중앙값은 **짝수면 두 가운데의 평균**이다 — 제품 사분면과 같은 규약', () => {
    /* `sorted[floor(n/2)]` 로 적으면 30 이 나온다. 같은 일을 두 문법으로 하면
       셋째가 생기는 날 어느 쪽을 따를지가 취향 문제가 된다. */
    expect(median([10, 20, 30, 40])).toBe(25);
    expect(median([40, 10, 30, 20])).toBe(25);
    expect(median([10, 20, 40])).toBe(20);
    expect(median([])).toBe(0);
  });

  it('가로 경계가 그 중앙값에 선다', () => {
    const its = [10, 20, 30, 40].map((v, i) =>
      item({ seriesId: `S${i}`, nowBp: v, z: 0.1 }));
    const geo = quadrantGeometry(its, 520, 360);
    expect(geo.xMid).toBe(25);
    /* 10~40 범위의 25 는 정확히 가운데 — 안쪽 폭의 절반 자리다. */
    expect(geo.xMidPx).toBeCloseTo(geo.points[0]!.cx
      + (geo.points[3]!.cx - geo.points[0]!.cx) / 2, 9);
  });

  it('세로 경계는 **0**이다 — 중앙값이 아니다', () => {
    /* z 는 이미 자기 이력에 상대화된 수라 절대선 0 이 뜻을 가진다(제품의 y=50
       과 같은 자세). 중앙값으로 바꾸면 날마다 반씩 갈라 그 사실을 지운다. */
    const its = [0.5, 0.4, 0.3, -0.1].map((v, i) =>
      item({ seriesId: `S${i}`, nowBp: 10 * (i + 1), z: v }));
    const geo = quadrantGeometry(its, 520, 360);
    expect(geo.zeroInRange).toBe(true);
    // 0 은 −0.1~0.5 에서 아래쪽 1/6 자리 → 바닥에 가깝다.
    const bottom = geo.points.find((p) => p.id === 'S3')!.cy;
    const top = geo.points.find((p) => p.id === 'S0')!.cy;
    expect(geo.zeroPx).toBeLessThan(bottom);
    expect(geo.zeroPx).toBeGreaterThan(top);
  });

  it('0 이 자료 범위 밖이면 **안 긋는다**', () => {
    const its = [0.5, 0.4, 0.3].map((v, i) =>
      item({ seriesId: `S${i}`, nowBp: 10 * (i + 1), z: v }));
    expect(quadrantGeometry(its, 520, 360).zeroInRange).toBe(false);
  });
});

describe('네 구역 — 「좁은데 싸다」가 이 화면이 찾는 것이다', () => {
  it('구역마다 하나씩 센다', () => {
    const its = [
      item({ seriesId: 'A', nowBp: 10, z: 0.3 }),   // 좁고 싸다 = 순수 RV
      item({ seriesId: 'B', nowBp: 20, z: -0.1 }),  // 좁고 비싸다
      item({ seriesId: 'C', nowBp: 30, z: 0.2 }),   // 넓고 싸다
      item({ seriesId: 'D', nowBp: 40, z: -0.3 }),  // 넓은데 비싸다 = 캐리만
    ];
    expect(quadrantCounts(its)).toEqual({
      pureRv: 1, tightRich: 1, wideCheap: 1, carryOnly: 1,
    });
  });

  it('칸이 없으면 전부 0 이다 — 빈 자료에서 터지지 않는다', () => {
    expect(quadrantCounts([])).toEqual({
      pureRv: 0, tightRich: 0, wideCheap: 0, carryOnly: 0,
    });
    const geo = quadrantGeometry([], 520, 360);
    expect(geo.points).toHaveLength(0);
    expect(Number.isFinite(geo.xMidPx)).toBe(true);
  });
});

describe('순위상관 — 이 수리의 증거를 화면이 직접 말한다', () => {
  it('완전 동순위와 완전 역순위를 제대로 낸다', () => {
    const asc = [1, 2, 3, 4, 5, 6, 7, 8];
    expect(spearman(asc, asc)).toBeCloseTo(1, 10);
    expect(spearman(asc, [...asc].reverse())).toBeCloseTo(-1, 10);
  });

  it('동순위는 **평균 순위**로 묶는다 — 입력 순서가 상관에 새지 않는다', () => {
    /* 민평은 평가사 호가라 같은 값이 흔하다. 순차 순위를 매기면 아래가 정확히
       1.0 이 되는데 그건 묶인 두 칸의 순서를 **지어낸** 결과다. */
    const xs = [1, 1, 2, 3, 4, 5, 6, 7];
    const ys = [1, 2, 3, 4, 5, 6, 7, 8];
    const r = spearman(xs, ys)!;
    expect(r).toBeCloseTo(41.5 / Math.sqrt(41.5 * 42), 10);
    expect(r).toBeLessThan(1);
    // 묶인 두 칸의 y 를 맞바꿔도 답이 같다.
    expect(spearman(xs, [2, 1, 3, 4, 5, 6, 7, 8])).toBeCloseTo(r, 10);
  });

  it('표본이 8 미만이면 **안 말한다** — 칸 셋으로 「직교한다」를 주장할 수 없다', () => {
    expect(spearman([1, 2, 3], [3, 2, 1])).toBeNull();
    expect(spearman([1, 2, 3, 4, 5, 6, 7], [1, 2, 3, 4, 5, 6, 7])).toBeNull();
  });

  it('길이가 다르거나 유한하지 않으면 null 이다', () => {
    expect(spearman([1, 2, 3, 4, 5, 6, 7, 8], [1, 2, 3])).toBeNull();
    expect(spearman([1, 2, 3, 4, 5, 6, 7, Number.NaN], [1, 2, 3, 4, 5, 6, 7, 8]))
      .toBeNull();
  });

  it('한 축이 상수면 null 이다 — 상관이 정의되지 않는다', () => {
    expect(spearman([5, 5, 5, 5, 5, 5, 5, 5], [1, 2, 3, 4, 5, 6, 7, 8])).toBeNull();
  });
});

describe('화면 — 산술을 다시 세지 않고 서식을 다시 적지 않는다', () => {
  const src = read(PAGE);

  it('검사할 소스를 실제로 찾았다', () => {
    expect(src.length).toBeGreaterThan(2000);
  });

  it('랭크·z 를 화면이 다시 세지 않는다 (§16 — 산술은 서버 하나다)', () => {
    /* 서버가 `-z` 로 정렬해 `rank` 를 박아 준다. 화면이 z 로 다시 줄을 세우면
       동순위 처리가 서버와 갈리는 날 순위가 둘이 된다. */
    expect(src, 'z 로 다시 정렬하고 있어요 — 랭크는 서버가 센 값입니다')
      .not.toMatch(/sort\([^)]*\.z\s*-/);
    expect(src, 'denomBp 로 z 를 다시 세고 있어요').not.toMatch(/denomBp\s*\)?\s*[*/]/);
  });

  it('음수 표기는 `lib/format` 이 진다 — 손 `toFixed` 로 하이픈이 샜다', () => {
    expect(src).toContain("fmtDelta(");
    expect(src).toContain("fmtLevel(");
    /* 값에 `toFixed` 를 직접 걸면 음수가 ASCII 하이픈(U+002D)으로 나온다. 이
       제품의 음수는 U+2212 이고 그 규약은 한 곳에만 있어야 한다. */
    expect(src, 'toFixed 가 남아 있어요 — 서식이 두 벌이 됩니다')
      .not.toMatch(/\.toFixed\(/);
  });

  it('커서 리드아웃은 캐논 부품이다 — 네이티브 title 툴팁이 아니다', () => {
    /* `<title>` 은 **마우스 전용**이라 아래 키보드 계약과 양립하지 않는다.
       떠 있는 `ReadoutCard` 도 캐논이 「새 표면에는 쓰지 말 것」 이라 적는다. */
    expect(src).toContain('ChartReadoutStrip');
    expect(src, 'svg <title> 툴팁이 남아 있어요 — 마우스 전용입니다')
      .not.toMatch(/<title>/);
    expect(src, '은퇴한 ReadoutCard 를 새 표면에 썼어요').not.toMatch(/\bReadoutCard\b/);
  });

  it('역방향 연동은 이미 있는 클래스가 진다 — 인라인 배경이 아니다', () => {
    expect(src).toMatch(/data-on=\{hover === it\.seriesId/);
    expect(src, '행 배경을 인라인으로 다시 적었어요 — .sr-rv-row[data-on] 이 그 일을 합니다')
      .not.toMatch(/background:\s*'var\(--color-bgAlternate\)'/);
  });
});

describe('화면 — 그림 축은 키보드로 쓸 수 있다 (CLAUDE.md 1·6·7)', () => {
  const src = read(PAGE);

  it('네 개가 한 벌이다 — role · tabIndex · onKeyDown · 화살표 라벨', () => {
    expect(src, 'role="application" 이 없어요').toContain('role="application"');
    expect(src, 'tabIndex 가 없어요 — 탭이 닿지 않습니다').toMatch(/tabIndex=\{0\}/);
    expect(src, 'onKeyDown 이 없어요 — 닿아도 아무 일이 안 일어납니다')
      .toContain('onKeyDown={onKeyDown}');
    expect(src, 'aria-label 이 화살표를 안 적었어요').toMatch(/화살표/);
  });

  it('화살표가 **두 축을 따로** 돈다 — ↑↓ 순위, ←→ 스프레드 폭', () => {
    for (const k of ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']) {
      expect(src, `${k} 를 안 듣습니다`).toContain(`case '${k}':`);
    }
    /* 한 순서로 네 방향을 처리하면 ←→ 가 세로로 튀고, 그 순간 그림이 가르치려던
       축 설계가 거짓이 된다. */
    expect(src).toMatch(/case 'ArrowUp':[\s\S]{0,120}step\(byRank, -1\)/);
    expect(src).toMatch(/case 'ArrowLeft':[\s\S]{0,120}step\(byWidth, -1\)/);
  });

  it('짚은 자리를 소리로 읽는다 — 그림의 변화는 소리가 안 난다', () => {
    expect(src, 'aria-live 줄이 없어요').toContain('aria-live="polite"');
    expect(src).toContain('sr-a11y-only');
  });

  it('판정은 24px 이상이다 (WCAG 2.2 §2.5.8)', () => {
    /* 점을 키우는 대신 판정만 넓힌다 — 120칸이 서는 그림에서 점을 24px 로
       키우면 서로 먹는다. */
    expect(src).toMatch(/const HIT_R = 12;/);
    expect(src).toMatch(/className="sr-quad-hit"[\s\S]{0,200}r=\{HIT_R\}/);
  });

  it('판정 원은 정말 눌린다 — `fill: transparent` 이지 `none` 이 아니다', () => {
    /* `fill: none` 은 히트 테스트를 통과하지 못한다. 둘을 헷갈리면 판정이
       통째로 사라지고 아무 경고도 안 난다. */
    const css = read('src/theme/type.css');
    expect(css).toMatch(/\.sr-quad-hit\s*\{[^}]*fill:\s*transparent/);
  });
});

describe('세입자로 **등록돼** 있다 — 안 걸린 화면은 없는 화면이다', () => {
  it('Lab 목록에 서고 라벨·설명·글리프를 다 든다', () => {
    const it_ = LAB_ITEMS.find((x) => x.id === 'creditdts');
    expect(it_, 'LAB_ITEMS 에 없어요 — 메가 패널에 안 뜹니다').toBeTruthy();
    expect(it_!.label).toBe('크레딧 RV (DTS)');
    expect(it_!.desc.length).toBeGreaterThan(8);
    expect(it_!.glyph.length).toBe(1);
  });

  it('주소로 열린다 — `?g=lab&lab=creditdts`', () => {
    expect(isLabId('creditdts')).toBe(true);
    expect(resolveLab('creditdts')).toBe('creditdts');
    // 기본 세입자를 밀어내지 않는다 — 공유된 옛 링크가 딴 화면으로 가면 안 된다.
    expect(DEFAULT_LAB).not.toBe('creditdts');
  });

  it('렌더 분기와 실패 문구가 둘 다 있다', () => {
    const page = read('src/app/page.tsx');
    expect(page, 'page.tsx 에 렌더 분기가 없어요 — 등록만 되고 안 그려집니다')
      .toMatch(/lab === 'creditdts' \?/);
    expect(page, 'ErrorBoundary 실패 문구가 없어요 — 「커브 표면」 문구가 뜹니다')
      .toMatch(/크레딧 RV \(DTS\) 를 그리지 못했어요/);
    expect(page).toContain('CreditDtsPage');
  });

  it('제품 Credit RV 를 **한 줄도 안 건드렸다** — 둘은 짝이지 대체가 아니다', () => {
    /* 오너가 제품 Score 교체를 Lab 으로 돌렸다. 이 레인이 제품 쪽 파일을
       임포트하거나 제품이 이쪽을 임포트하면 그 분리가 사라진다. */
    const page = read(PAGE);
    expect(page, '제품 rv 모듈을 끌어다 썼어요').not.toMatch(/from '@\/rv\//);
    for (const f of ['src/rv/RvPage.tsx', 'src/rv/RvScatter.tsx', 'src/rv/pick.ts']) {
      expect(read(f), `${f} 가 Lab 쪽을 임포트해요`).not.toMatch(/creditdts/);
    }
  });
});
