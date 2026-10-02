// @vitest-environment jsdom
/* RV Analysis (rv2) 의 구조 핀 [트레이더 피드백 2026-08-18 + OWNER].
 *
 * 지키는 것: ① 명구("투자판단이 아니라 RV 랭킹이에요") — 랭킹 표·Score 히트맵
 * 둘 다 의무 ② 사분면 라벨은 **서술형**(명령형·매수·추천 금지) ③ 별·메달 금지
 * ④ 실행불가는 **속빈 마커**(지우지도, 채우지도 않는다) ⑤ "껍질" 과 "창 안
 * 승자" 는 딴 집합이라 딴 이름(PN-2) ⑥ 다이버징 틴트는 `tintFor(x − 50, 50)`
 * 소스 하나 ⑦ §16 — 프런트는 z·백분위·σ 를 재계산하지 않는다(서버 값 통과).
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render } from '@testing-library/react';
import fs from 'node:fs';
import path from 'node:path';

import { ThemeProvider } from '@coinbase/cds-web';

import { sauronTheme } from '../src/theme/sauronTheme';

import { RankingTable } from '../src/rv/RankingTable';
import { RvScatter } from '../src/rv/RvScatter';
import { ScoreHeat } from '../src/rv/ScoreHeat';
import { SectorLane } from '../src/rv/SectorLane';
import type { RvCreditItem, RvSector } from '../src/rv/api';
import { snapCreditBucket } from '../src/rv/pick';

afterEach(cleanup);

const RV_DIR = path.join(__dirname, '..', 'src', 'rv');

function item(over: Partial<RvCreditItem>): RvCreditItem {
  return {
    sector: 'BD',
    sectorLabel: '은행채 AAA',
    base: 'KDB',
    baseLabel: '산금채 AAA',
    tenor: '3Y',
    years: 3.0,
    nowBp: 70.0,
    carryBp: 6.9,
    rollBp: 5.0,
    bufferBp: 11.9,
    trMonthBp: 8.4,
    pctLastWeek: 70.0,
    lastWeekBp: 69.2,
    spreadVolPct: 66.0,
    pct: 62.0,
    cheapBp: 4.0,
    zAbs: 0.8,
    zSector: -0.2,
    zCurve: 0.4,
    relRv: 0.32,
    score: 75.0,
    rank: 1,
    rankDelta: 2,
    shortable: true,
    shortVia: 'IRS·선물',
    seriesId: 'CRD-BD-3Y',
    ...over,
  };
}

const ITEMS: RvCreditItem[] = [
  item({}),
  // 왼쪽 아래 — 덜 벌고 평소보다 좁다. (2026-08-20: 만기 상한 3Y 라 5Y 는
  // 이 화면에 못 서므로 픽스처도 2.5Y 로 내렸다.)
  item({ sector: 'CB1', sectorLabel: '회사채 AAA', tenor: '2.5Y', years: 2.5,
    base: 'KDB', baseLabel: '산금채 AAA',
    shortable: false, shortVia: null, seriesId: 'CRD-CB1-2.5Y',
    relRv: -0.6, trMonthBp: 5.1, pctLastWeek: 22.0, score: 30.0, rank: 3,
    rankDelta: -1 }),
  // 오른쪽 위 — 많이 벌고 평소보다 넓다.
  item({ sector: 'OFB', sectorLabel: '캐피탈채 AA-', tenor: '1Y', years: 1.0,
    base: 'KDB', baseLabel: '산금채 AAA',
    shortable: false, shortVia: null, seriesId: 'CRD-OFB-1Y',
    relRv: 0.9, trMonthBp: 12.6, pctLastWeek: 91.0, score: 60.0, rank: 2,
    rankDelta: null }),
  // 백분위 미확정 — 좌표 없음. 산점에는 못 서고 표에는 — 로 선다.
  item({ sector: 'CARD', sectorLabel: '카드채 AA+', tenor: '2Y', years: 2.0,
    base: 'KDB', baseLabel: '산금채 AAA',
    shortVia: 'IRS', seriesId: 'CRD-CARD-2Y',
    pctLastWeek: null, lastWeekBp: null, spreadVolPct: null, relRv: null, score: null,
    rank: null, rankDelta: null }),
];

const noop = () => {};

/* CDS Tooltip(열 머리 설명)의 Popover 가 useTheme 을 요구한다 — 렌더는
 * ThemeProvider 아래에서. 앱과 같은 테마(providers.tsx의 그 구성). */
function rtl(ui: React.ReactElement) {
  return render(
    <ThemeProvider theme={sauronTheme} activeColorScheme="light">
      {ui}
    </ThemeProvider>,
  );
}

describe('명구 — 랭킹이지 투자판단이 아니다', () => {
  it('랭킹 표가 명구를 단다', () => {
    const { container } = rtl(<RankingTable hMonths={6} window="52w" items={ITEMS} onSelect={noop} />);
    expect(container.textContent).toContain('투자판단이 아니라 RV 랭킹이에요');
  });

  it('Score 히트맵도 명구를 단다', () => {
    const { container } = render(<ScoreHeat items={ITEMS} onSelect={noop} />);
    expect(container.textContent).toContain('투자판단이 아니라 RV 랭킹이에요');
  });

  it('별·메달·추천 문구는 어디에도 없다', () => {
    for (const el of [
      rtl(<RankingTable hMonths={6} window="52w" items={ITEMS} onSelect={noop} />),
      render(<ScoreHeat items={ITEMS} onSelect={noop} />),
      render(<RvScatter items={ITEMS} onSelect={noop} />),
    ]) {
      expect(el.container.textContent).not.toMatch(/[★☆🥇🥈🥉]|추천|베스트/);
    }
  });
});

describe('사분면 — 서술형, 명령형 금지', () => {
  it('네 라벨이 좌표의 뜻을 말한다 [OWNER 2026-08-19 — "싸고 버팀" 계열 교체]', () => {
    const { container } = render(<RvScatter items={ITEMS} onSelect={noop} />);
    for (const label of [
      '많이 벌고 · 평소보다 넓음',
      '많이 벌지만 · 평소보다 좁음',
      '덜 벌고 · 평소보다 넓음',
      '덜 벌고 · 평소보다 좁음',
    ]) {
      expect(container.textContent).toContain(label);
    }
  });

  /* 세로선(x)은 중앙값이라 늘 반씩 가르지만, 가로선(y)은 절대선 50 이라
     그러지 않는다 — 최근 252영업일 실측에서 "50 위" 비율이 2%~93% 로 흔들리고
     35~65% 로 갈린 날은 21% 뿐이다. 그 진폭이 곧 국면이라 축은 안 바꾸기로
     했고(중앙값으로 옮기면 그 사실이 지워진다), 대신 이 한 줄이 개수로 말한다
     [OWNER 2026-08-21]. 픽스처는 3개 중 2개가 50 위다. */
  it('국면 한 줄이 y 경계 위 개수를 말한다 [OWNER 2026-08-21]', () => {
    const { container } = render(<RvScatter items={ITEMS} onSelect={noop} />);
    expect(container.textContent).toContain('오늘은 3개 중 2개가 평소보다 넓어요');
  });

  it('국면 한 줄은 쏠리지 않은 날에도 선다 — 임계가 없다', () => {
    /* 넷 중 둘만 50 위로 내려 균형을 만든다. 임계를 두면 이 날 줄이 사라지고,
       "중립"이라는 같은 크기의 사실을 화면이 잃는다. */
    const balanced = ITEMS.map((p) =>
      p.seriesId === 'CRD-OFB-1Y' ? { ...p, pctLastWeek: 12.0 } : p,
    );
    const { container } = render(<RvScatter items={balanced} onSelect={noop} />);
    expect(container.textContent).toContain('오늘은 3개 중 1개가 평소보다 넓어요');
  });

  it('매수·명령형 문구가 없다', () => {
    const { container } = render(<RvScatter items={ITEMS} onSelect={noop} />);
    expect(container.textContent).not.toMatch(/매수|매도하세요|사세요|파세요/);
  });

  it('점은 잉크 단일이고 헤지수단 표기는 없다 [OWNER — "명시 빼기"]', () => {
    const { container } = render(<RvScatter items={ITEMS} onSelect={noop} />);
    const dots = [...container.querySelectorAll('circle.sr-rv-dot')];
    // σ 미확정 1개는 좌표가 없어 못 선다 — 나머지 셋만.
    expect(dots).toHaveLength(3);
    // 점은 잉크 중립 단일 — 속빈(헤지 불가) 마커도 표기와 함께 은퇴했다:
    // 표기가 없으면 마커는 설명 불가한 수수께끼가 된다.
    for (const d of dots) expect(d.getAttribute('fill')).toBe('var(--color-fg)');
    expect(container.textContent).not.toContain('헤지수단');
    // 좌표에 못 선 항목은 숫자로 말한다 — 조용히 사라지지 않는다.
    expect(container.textContent).toContain('백분위 미확정 1개');
  });

  it('열 머리 넷은 뜻 설명 표식을 단다 — 사분면 두 축이 앞에 [OWNER 2026-08-20]', () => {
    const { container } = rtl(<RankingTable hMonths={6} window="52w" items={ITEMS} onSelect={noop} />);
    const helps = [...container.querySelectorAll('.sr-rv-thhelp')].map((e) => e.textContent);
    expect(helps).toEqual(['한 달 수익', '지난주 백분위', '버퍼', '상대 RV']);
    // 헤지수단 표기는 표에서도 은퇴했다.
    expect(container.textContent).not.toContain('헤지수단');
  });

  it('비시각 요약은 svg 가 진다 — 점은 포인터 지름길이라 탭 정지가 아니다', () => {
    const { container } = render(<RvScatter items={ITEMS} onSelect={noop} />);
    const svg = container.querySelector('svg.sr-rv-scatter');
    expect(svg?.getAttribute('aria-label')).toMatch(
      /\d+개 중 \d+개가 중앙값보다 많이 벌고 평소보다 넓은/,
    );
    for (const d of container.querySelectorAll('circle.sr-rv-dot')) {
      expect(d.getAttribute('tabindex')).toBeNull();
    }
  });
});

/* ── 컨트롤을 따라가지 않는 문구 [2026-08-21 실측 둘] ──────────────────────
   H(3/6/12)와 이력 창(52주/전체)은 화면 컨트롤이 됐는데 열 머리 풀이는 상수로
   남아, 기본 화면이 자기 숫자의 기간과 모집단을 틀리게 말하고 있었다:

       「버퍼」      "3개월 캐리와 롤" — 기본 H 는 6개월
       「지난주 백분위」 "과거 52주 중" — 전체 이력을 골라도 그대로

   둘 다 눈으로는 안 잡힌다(문장이 멀쩡하다). 그래서 **렌더해서 읽는** 검사로
   건다 — 컨트롤 값을 바꿔 렌더하고 문구가 따라오는지 본다. */
describe('풀이는 컨트롤을 따라간다 [2026-08-21]', () => {
  /* 풀이는 CDS Tooltip 안이라 **열기 전에는 DOM 에 없다** — 이 사실이 두 거짓말이
     여태 안 잡힌 이유다(container.textContent 로는 영영 안 보인다). 열쇠를 열고
     포털까지 읽는다: 트리거는 tabIndex=0 인 `.sr-rv-thhelp` 이고 툴팁은 hover 와
     키보드 포커스 둘 다에 열린다. */
  function openHelp(label: string): string {
    const trigger = [...document.querySelectorAll('.sr-rv-thhelp')].find(
      (el) => el.textContent === label,
    );
    if (!trigger) throw new Error(`열 머리를 못 찾았어요: ${label}`);
    fireEvent.focus(trigger);
    fireEvent.mouseEnter(trigger);
    return document.body.textContent ?? '';
  }

  it('버퍼 풀이가 H 를 말한다 — 상수 "3개월" 아님', () => {
    for (const h of [3, 6, 12]) {
      rtl(<RankingTable hMonths={h} window="52w" items={ITEMS} onSelect={noop} />);
      expect(openHelp('버퍼')).toContain(`${h}개월 캐리와 롤`);
      cleanup();
    }
  });

  it('지난주 백분위 풀이가 이력 창을 말한다 — 상수 "52주" 아님', () => {
    rtl(<RankingTable hMonths={6} window="52w" items={ITEMS} onSelect={noop} />);
    expect(openHelp('지난주 백분위')).toContain('과거 52주 중');
    cleanup();
    rtl(<RankingTable hMonths={6} window="all" items={ITEMS} onSelect={noop} />);
    const all = openHelp('지난주 백분위');
    expect(all).toContain('전체 이력 중');
    expect(all).not.toContain('과거 52주');
  });
});

describe('랭크와 Δ — 서버 값 통과 [OWNER 2026-08-19]', () => {
  it('순서는 서버 rank 그대로이고 Δ 는 ▲▼로, 어제 없던 항목은 공란이다', () => {
    const { container } = rtl(<RankingTable hMonths={6} window="52w" items={ITEMS} onSelect={noop} />);
    const firstCells = [...container.querySelectorAll('tbody tr')].map(
      (tr) => tr.querySelector('td')?.textContent,
    );
    // rank 1(BD 3Y) → 2(OFB 6M) → 3(CB1 5Y) → 랭크 없음(—) 순.
    expect(firstCells).toEqual(['1', '2', '3', '—']);
    expect(container.textContent).toContain('▲2'); // BD 3Y 올라옴
    expect(container.textContent).toContain('▼1'); // CB1 2.5Y 내려감
    // 글리프는 소리로도 뜻이어야 한다 — "black up-pointing triangle" 금지.
    const up = [...container.querySelectorAll('[role="img"]')].find(
      (el) => el.textContent === '▲2',
    );
    expect(up?.getAttribute('aria-label')).toBe('2계단 올라옴');
    // 어제 없던 OFB 6M 의 Δ 칸은 비어 있다 — 0 과 "모름"은 딴 사실이다.
    const ofbRow = [...container.querySelectorAll('tbody tr')].find((tr) =>
      tr.textContent?.includes('캐피탈채'),
    );
    expect(ofbRow?.querySelectorAll('td')[1]?.textContent).toBe('');
  });
});

describe('표 의미론 — 여는 것은 버튼, 행은 행', () => {
  it('랭킹 표: tr 에 role 이 없고, 종목 칸의 실제 <button> 이 키보드 경로다', () => {
    const { container } = rtl(<RankingTable hMonths={6} window="52w" items={ITEMS} onSelect={noop} />);
    for (const tr of container.querySelectorAll('tbody tr')) {
      expect(tr.getAttribute('role')).toBeNull(); // role="button" 은 표 탐색을 부순다
      expect(tr.getAttribute('tabindex')).toBeNull();
    }
    const btns = [...container.querySelectorAll('tbody button.sr-rv-linkbtn')];
    expect(btns).toHaveLength(ITEMS.length);
    expect(btns[0]?.getAttribute('aria-label')).toContain('이력 단면 열기');
  });

  it('히트맵 칸 버튼은 tabIndex=-1 — 같은 목적지의 포인터 지름길이다', () => {
    const { container } = render(<ScoreHeat items={ITEMS} onSelect={noop} />);
    const btns = [...container.querySelectorAll('button.sr-rv-cellbtn')];
    expect(btns.length).toBeGreaterThan(0);
    for (const b of btns) expect(b.getAttribute('tabindex')).toBe('-1');
  });
});

describe('표기 — fmt 한 벌', () => {
  it('반올림 후 0 은 부호가 없다 — "-0.0σ" 를 찍지 않는다', async () => {
    const { sig } = await import('../src/rv/fmt');
    expect(sig(-0.04)).toBe('0.0');
    expect(sig(-0.001, 2)).toBe('0.00');
    expect(sig(0.06)).toBe('+0.1');
    expect(sig(-0.06)).toBe('-0.1');
  });

  it('sig 정의는 fmt.ts 한 곳뿐이다', () => {
    for (const f of fs.readdirSync(RV_DIR)) {
      if (f === 'fmt.ts') continue;
      const src = fs.readFileSync(path.join(RV_DIR, f), 'utf8');
      expect(src, `${f} 에 사설 sig 정의`).not.toMatch(/function sig\(/);
    }
  });
});

describe('껍질 ≠ 창 안 승자 (PN-2)', () => {
  const sector: RvSector = {
    id: 'SHEET',
    label: '특은채',
    candidates: [
      // 껍질에는 있으나 창 안 승자가 아닌 후보 — 앵커의 6M 이 이 모양이다.
      { tenor: '6M', years: 0.5, dur: 0, carryBp: 9.5, rollBp: 0, reinvBp: 0,
        reinvDays: 0, trBp: 9.5,
        bepBp: null, maturityHold: true, inHull: true, winFrom: null, winTo: null,
        tr: [9.5, 9.5, 9.5], pathTr: [], pathDy: [] },
      { tenor: '3Y', years: 3.0, dur: 2.6, carryBp: 46.2, rollBp: 22.8, reinvBp: 0,
        reinvDays: 0, trBp: 69.0,
        bepBp: 29.1, maturityHold: false, inHull: true, winFrom: -50, winTo: 13,
        tr: [120.0, 69.0, 10.0], pathTr: [], pathDy: [] },
    ],
    swapPoints: [{ from: '3Y', to: '9M', dyBp: 13.0 }],
    filtered: 0,
  };

  it('껍질 ◆ 마커는 은퇴했고(무표) 1등 구간 열은 선다 [OWNER 2026-08-19 — "없애도 될 듯"]', () => {
    const { container } = render(
      <SectorLane sector={sector} dys={[-50, 0, 50]} hMonths={6} />,
    );
    // inHull 이 와도 아무 표시도 안 남는다 — 계약(inHull)은 잔존, 표시만 은퇴.
    expect(container.querySelector('.sr-rv-hull')).toBeNull();
    expect(container.textContent).not.toContain('◆');
    expect(container.textContent).toContain('1등 구간');
    // 창 안 1등이 없는 6M 줄의 1등 구간은 — 다.
    const rows = [...container.querySelectorAll('tbody tr')];
    const row6m = rows.find((r) => r.textContent?.includes('6M'));
    expect(row6m?.textContent).toContain('—');
  });

  it('1등 구간은 격자 위 테두리 띠로도 선다 [OWNER 2026-08-19 — "테이블 자체적으로"]', () => {
    const { container } = render(
      <SectorLane sector={sector} dys={[-50, 0, 50]} hMonths={6} />,
    );
    const rows = [...container.querySelectorAll('tbody tr')];
    const row3y = rows.find((r) => r.textContent?.includes('3Y'))!;
    // winFrom −50 .. winTo +13 → 격자 −50, 0 두 칸이 띠(시작·끝 닫힘), +50 은 밖.
    const cells = [...row3y.querySelectorAll('td.sr-rv-win')];
    expect(cells).toHaveLength(2);
    expect(cells[0]?.className).toContain('sr-rv-win-start');
    expect(cells[1]?.className).toContain('sr-rv-win-end');
    // 승자 없는 6M 줄에는 띠가 없다.
    const row6m = rows.find((r) => r.textContent?.includes('6M'))!;
    expect(row6m.querySelector('td.sr-rv-win')).toBeNull();
  });
});

describe('틴트·재계산 소스 핀', () => {
  it('다이버징 틴트는 tintFor(x − 50, 50) 하나다 — 레인 B 와 Score', () => {
    const tenorHeat = fs.readFileSync(path.join(RV_DIR, 'TenorHeat.tsx'), 'utf8');
    expect(tenorHeat).toContain('tintFor(pctOf(c) - 50, 50)');
    const scoreHeat = fs.readFileSync(path.join(RV_DIR, 'ScoreHeat.tsx'), 'utf8');
    expect(scoreHeat).toContain('tintFor(p.score - 50, 50)');
    const ranking = fs.readFileSync(path.join(RV_DIR, 'RankingTable.tsx'), 'utf8');
    expect(ranking).toContain('tintFor(p.score - 50, 50)');
  });

  it('§16 — 프런트는 z·백분위·σ 를 재계산하지 않는다', () => {
    /* 서버 값 통과의 소스 핀: 표준편차·평균 계산의 재료(sqrt·reduce)가 rv
     * 컴포넌트에 없어야 한다. 화면 좌표 변환(min/max/abs)은 허용이다. */
    for (const f of fs.readdirSync(RV_DIR)) {
      const src = fs.readFileSync(path.join(RV_DIR, f), 'utf8');
      expect(src, `${f} 에 재계산 흔적`).not.toMatch(/Math\.sqrt|\.reduce\(/);
    }
  });

  it('랭킹 열 머리는 sticky·불투명이다 — 74행 스크롤이 머리를 지우면 안 된다', () => {
    const css = fs.readFileSync(
      path.join(__dirname, '..', 'src', 'theme', 'type.css'), 'utf8',
    );
    const th = css.match(/\.sr-rv-th \{[^}]*\}/)?.[0] ?? '';
    expect(th).toContain('position: sticky');
    expect(th).toContain('background: var(--sr-card)');
    // 채움 기하 — absolute 패턴이어야 표 내용이 행 높이를 밀어올리지 않는다
    // (2차 크리틱: 캡 상수판은 카드 하단 366px 이 죽은 여백이었다).
    expect(css).toMatch(/\.sr-rv-rank-fill \{[^}]*position: relative/);
    expect(css).toMatch(/\.sr-rv-rank-scroll \{[^}]*position: absolute/);
    expect(css).toMatch(/\.sr-rv-rank-scroll \{[^}]*overflow: auto/);
    // 표는 카드 폭을 채운다 [OWNER "꽉 채우기"].
    expect(css).toMatch(/\.sr-rv-table \{[^}]*width: 100%/);
  });

  it('브라우저 크롬도 스킴을 따른다 — 다크의 흰 스크롤바 회귀 금지', () => {
    const css = fs.readFileSync(
      path.join(__dirname, '..', 'src', 'theme', 'direction.css'), 'utf8',
    );
    expect(css).toMatch(/\[data-sr-scheme='dark'\] \{\s*color-scheme: dark/);
    expect(css).toMatch(/\[data-sr-scheme='light'\] \{\s*color-scheme: light/);
  });

  it('as-of 강조는 색이 아니다 — 방향색은 이 바의 배경 위에서 기준 미달', () => {
    const rvPage = fs.readFileSync(path.join(RV_DIR, 'RvPage.tsx'), 'utf8');
    expect(rvPage).toContain('sr-rv-asof-split');
    // Cond 의 강조가 .sr-up(방향색)으로 돌아가면 4.1:1 미달이 재발한다.
    expect(rvPage).not.toMatch(/strong \? 'sr-up'/);
  });
});

/* ── 종목 지정 → 버킷 매핑 [OWNER 2026-10-01] ────────────────────────────────
   「사려는 유통물의 지금 매력도」는 (섹터, 잔존)을 v2 섹터×테너 버킷으로 스냅해
   그 버킷의 Score 를 빌려 온다(`src/rv/pick.ts`). 아래가 그 규칙의 핀이다 —
   스냅/상한/미지정을 어긋내면 이 시험만 빨개져야 한다(되돌림 가드). */
describe('종목 지정 — 잔존→버킷 스냅', () => {
  /* 한 섹터에 테너가 여럿 있어야 최근접 선택이 검정된다 — ITEMS 는 섹터당
     하나뿐이라 전용 픽스처를 둔다(KDB 2Y/2.5Y/3Y). */
  const SNAP: RvCreditItem[] = [
    item({ sector: 'KDB', sectorLabel: '산금채 AAA', tenor: '2Y', years: 2.0, seriesId: 'k2' }),
    item({ sector: 'KDB', sectorLabel: '산금채 AAA', tenor: '2.5Y', years: 2.5, seriesId: 'k25' }),
    item({ sector: 'KDB', sectorLabel: '산금채 AAA', tenor: '3Y', years: 3.0, seriesId: 'k3' }),
  ];

  /* 끝값은 **페이로드 모양**으로 넘긴다 — 화면이 상수를 적으면 H 를 3/12개월로
     바꾼 날 거짓말을 한다(`pick.ts` 의 그 이유). H 6개월 → 하한 0.5년. */
  const B = { maxYears: 3.0, hMonths: 6 };

  it('가장 가까운 테너로 스냅한다 — 2.4→2.5Y, 2.8→3Y, 2.2→2Y', () => {
    const r24 = snapCreditBucket(SNAP, 'KDB', 2.4, B);
    const r28 = snapCreditBucket(SNAP, 'KDB', 2.8, B);
    const r22 = snapCreditBucket(SNAP, 'KDB', 2.2, B);
    expect(r24?.kind === 'hit' && r24.item.tenor).toBe('2.5Y');
    expect(r28?.kind === 'hit' && r28.item.tenor).toBe('3Y');
    expect(r22?.kind === 'hit' && r22.item.tenor).toBe('2Y');
  });

  it('상한(maxYears) 밖은 스냅하지 않고 사유를 돌려준다 — 조용히 3Y 로 안 끌려간다', () => {
    expect(snapCreditBucket(SNAP, 'KDB', 5.0, B)).toEqual({
      kind: 'oob',
      side: 'above',
      edgeYears: 3.0,
    });
    // 경계: 3.0 은 3Y 로 적중, 3.01 은 밖.
    expect(snapCreditBucket(SNAP, 'KDB', 3.0, B)?.kind).toBe('hit');
    expect(snapCreditBucket(SNAP, 'KDB', 3.01, B)?.kind).toBe('oob');
  });

  /* ★이 묶음이 2026-10-02 에 생겼다 — **하한에는 가드가 없었다.**
     Score 가 붙은 테너는 산 페이로드에서 9M~3Y 여섯 칸이고 3M·6M 에는 없다
     (서버 사유: "만기 보유(H 안에 만기) — 금리 위험이 없어 버퍼가 정의되지
     않아요"). 그래서 잔존 0.4년이 **조용히 9M 버킷으로 끌려가** 잔존이 거의 두
     배인 칸의 Score 를 빌려 쓰고 있었다 — 상한 쪽에 「조용히 3Y 로 끌려가 거짓이
     된다」고 적어 둔 바로 그 결함이 아래쪽에만 살아 있었다. */
  it('★하한(H 안에 만기)도 스냅하지 않는다 — 0.4년이 조용히 9M 로 안 끌려간다', () => {
    const SHORT: RvCreditItem[] = [
      item({ sector: 'KDB', sectorLabel: '산금채 AAA', tenor: '9M', years: 0.75, seriesId: 'k9m' }),
      ...SNAP,
    ];
    expect(snapCreditBucket(SHORT, 'KDB', 0.4, B)).toEqual({
      kind: 'oob',
      side: 'below',
      edgeYears: 0.5,
    });
    // 경계는 서버 식 그대로 — `years <= hMonths/12` 가 채점 불가다.
    expect(snapCreditBucket(SHORT, 'KDB', 0.5, B)?.kind).toBe('oob');
    const over = snapCreditBucket(SHORT, 'KDB', 0.51, B);
    expect(over?.kind === 'hit' && over.item.tenor).toBe('9M');
  });

  it('★하한은 H 를 따라 움직인다 — 화면 상수가 아니다', () => {
    const SHORT: RvCreditItem[] = [
      item({ sector: 'KDB', sectorLabel: '산금채 AAA', tenor: '6M', years: 0.5, seriesId: 'k6m' }),
      item({ sector: 'KDB', sectorLabel: '산금채 AAA', tenor: '9M', years: 0.75, seriesId: 'k9m' }),
    ];
    // H 3개월이면 하한 0.25년 — 0.4년은 이제 **적중**이다(6M 으로).
    const h3 = snapCreditBucket(SHORT, 'KDB', 0.4, { maxYears: 3.0, hMonths: 3 });
    expect(h3?.kind === 'hit' && h3.item.tenor).toBe('6M');
    // H 12개월이면 하한 1.0년 — 0.9년도 밖이다.
    expect(snapCreditBucket(SHORT, 'KDB', 0.9, { maxYears: 3.0, hMonths: 12 })).toEqual({
      kind: 'oob',
      side: 'below',
      edgeYears: 1.0,
    });
  });

  it('★스냅 거리를 같이 돌려준다 — 버킷 이름만으론 얼마나 멀리 빌렸는지 모른다', () => {
    const r = snapCreditBucket(SNAP, 'KDB', 2.3, B);
    expect(r?.kind === 'hit' && r.gapYears).toBeCloseTo(0.2, 10);
    const exact = snapCreditBucket(SNAP, 'KDB', 2.5, B);
    expect(exact?.kind === 'hit' && exact.gapYears).toBe(0);
  });

  it('미지정(섹터 공란·잔존 0)은 null — 카드가 서지 않는다', () => {
    expect(snapCreditBucket(SNAP, '', 2.5, B)).toBeNull();
    expect(snapCreditBucket(SNAP, 'KDB', 0, B)).toBeNull();
  });

  it('Score 가 없는 버킷도 적중은 적중이다 — 카드가 "Score 없음"으로 선다', () => {
    const noScore: RvCreditItem[] = [
      item({ sector: 'CARD', sectorLabel: '카드채 AA+', tenor: '2Y', years: 2.0, score: null }),
    ];
    const r = snapCreditBucket(noScore, 'CARD', 1.9, B);
    expect(r?.kind).toBe('hit');
    expect(r?.kind === 'hit' && r.item.score).toBeNull();
  });

  /* ── 화면이 사유를 **적는가** ─────────────────────────────────────────────
     함수가 사유를 돌려줘도 화면이 안 적으면 조용한 스냅과 같다. 그리고 상한
     문구는 틀린 사유("5Y·10Y 선물")를 대고 있었다 — 실제 사유는 트레이더
     워크북의 커브가 3M~3Y 여덟 노드라는 것이다(`rv.py` MAX_YEARS 주석). */
  it('★화면이 양쪽 끝의 사유와 스냅 거리를 적는다 — 틀린 「선물」 사유는 돌아오지 않는다', () => {
    const src = fs.readFileSync(path.join(RV_DIR, 'RvPage.tsx'), 'utf8');
    expect(src, '하한 사유(H 안에 만기)를 화면이 적어야 한다').toMatch(/H\(\{data\.hMonths\}개월\) 안에 만기/);
    expect(src, '상한 사유는 워크북이다').toMatch(/워크북의 커브가 3M~3Y 여덟 노드/);
    expect(src, '틀린 「선물」 사유가 돌아왔다').not.toMatch(/5Y·10Y 선물은 만기 상한 밖/);
    expect(src, '스냅 거리를 적어야 한다').toMatch(/년 차이/);
  });

  /* ── ⓐ 내 호가는 버킷 Score 와 **다른 축**이다 ───────────────────────────── */
  it('★내 호가 칸은 안 넣으면 «—» 다 — 0 은 「민평 그대로」라는 딴 진술이다', () => {
    const src = fs.readFileSync(path.join(RV_DIR, 'RvPage.tsx'), 'utf8');
    // 상태가 number 면 안 넣은 칸이 "민평 0.0bp" 라는 없는 진술을 한다.
    expect(src).toMatch(/useState<number \| null>\(null\)/);
    expect(src, '방향을 말로 적어야 한다(+ = 싸게 산다, 매수 기준)').toMatch(/그만큼 싸게 사요/);
    const cmp = fs.readFileSync(path.join(RV_DIR, 'PickCompare.tsx'), 'utf8');
    expect(cmp, '비교표도 안 넣은 호가를 «—» 로 적는다').toMatch(/quoteBp == null \? '—'/);
  });

  /* ── ⓑ 후보는 값을 복사하지 않는다 ─────────────────────────────────────── */
  it('★후보 비교는 담을 때의 값을 복사하지 않는다 — 지금 페이로드로 다시 스냅한다', () => {
    const cmp = fs.readFileSync(path.join(RV_DIR, 'PickCompare.tsx'), 'utf8');
    // 열쇠만 든다: 후보 타입에 Score·캐리 같은 **값 필드가 없다**.
    expect(cmp).toMatch(/export interface PickCandidate/);
    expect(cmp, '후보가 값을 들면 창·H 를 바꿔도 이 표만 옛 수로 선다').not.toMatch(
      /PickCandidate[\s\S]{0,400}?\bscore\b/,
    );
    // 그리고 창이 **직접** 스냅한다.
    expect(cmp).toMatch(/snapCreditBucket\(items, c\.sector, c\.ttm, bounds\)/);
    // 명구는 Score 를 적는 표면의 의무다(이 리포의 ① 규율).
    expect(cmp).toMatch(/투자판단이 아니라 RV 랭킹이에요/);
  });
});
