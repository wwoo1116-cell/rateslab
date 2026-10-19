/* Flow 세입자 — **등록되고, 그려지고, 제 말을 한다** [2026-10-19].
 *
 * ## 왜 이 파일이 필요한가
 *
 * `guards/nav-strategy-tenants.test.ts` 는 **등록**만 잰다. 그런데
 * `src/app/page.tsx` 의 전략 분기는 마지막 가지가 `else` 라, 세입자를
 * `STRATEGY_ITEMS` 에만 더하면 **가드가 전부 초록인 채 새 탭이 이웃 화면을
 * 그린다**. Lab 쪽은 이 함정을 가드로 못 박아 뒀고(`lab-credit-dts.test.ts:367`)
 * Strategy 쪽에는 그 가드가 **없었다** — 이 파일이 그것이다.
 *
 * 나머지 셋은 이 면의 설계가 되돌아오지 못하게 막는 래칫이다.
 */

import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { DEFAULT_STRATEGY, isStrategyId, STRATEGY_ITEMS } from '../src/ui/nav';
import { stripComments } from './_source';

const ROOT = process.cwd();
const read = (rel: string) => stripComments(fs.readFileSync(path.join(ROOT, rel), 'utf8'));

const PAGE = read('src/app/page.tsx');
const FLOW_PAGE = read('src/flow/FlowPage.tsx');
const FLOW_PY = fs.readFileSync(path.join(ROOT, 'backend/app/flow.py'), 'utf8');

describe('① 등록만 하고 안 그려지는 함정', () => {
  it('page.tsx 에 **명시 분기**가 있다 — 없으면 Momentum 이 그려진다', () => {
    expect(PAGE, "page.tsx 에 flow 렌더 분기가 없어요 — 등록만 되고 Momentum 이 그려집니다")
      .toMatch(/strategy === 'flow' \?/);
    expect(PAGE).toContain('FlowPage');
  });

  it('마지막 가지가 여전히 catch-all 이다 — 그래서 명시 분기가 필요하다', () => {
    /* 이 단언이 깨지는 날은 누군가 `else` 를 없앤 날이고, 그때는 위 단언의
       **이유**가 사라진 것이라 이 파일을 다시 읽어야 한다. */
    const i = PAGE.indexOf("strategy === 'credit-rv'");
    expect(i).toBeGreaterThan(0);
    expect(PAGE.slice(i, i + 700)).toContain('MomentumPage');
  });

  it('런타임 판정도 같이 넓혔다 — 타입만 넓히면 왕복이 깨진다', () => {
    expect(isStrategyId('flow')).toBe(true);
    expect(STRATEGY_ITEMS.some((x) => x.id === 'flow')).toBe(true);
    /* 기본은 안 바뀐다 — 예전 `?g=strategy` 링크가 가리키던 화면 그대로. */
    expect(DEFAULT_STRATEGY).toBe('credit-rv');
  });
});

describe('② 그림엔 넷, 표엔 전부', () => {
  /* 이 리포에 N계열 범주형 팔레트가 없다 — 이름 있는 색이 방향 2 + 참조 4뿐이다.
     그래서 서버가 계열을 **골라서** 보내고 전수는 표가 진다. */
  it('서버가 그림 계열을 네 개로 자른다', () => {
    expect(FLOW_PY).toMatch(/\[:3\]/);          // 외국인 + 세분 셋
    expect(FLOW_PY).toMatch(/picked\[:4\]|\[:4\]/);
  });

  it('표는 전수를 받는다 — 순위 밖도 지우지 않는다', () => {
    expect(FLOW_PY).toContain('"ranked"');
    expect(FLOW_PY, '순위 밖을 0등으로 적으면 「없다」와 「0등」이 섞인다')
      .toMatch(/r\["rank"\] = None/);
  });

  it('계열 구분색은 토큰으로만 — hex 는 direction.css 에만 있다', () => {
    expect(FLOW_PAGE).toContain('--sr-flow-1');
    expect(FLOW_PAGE).not.toMatch(/#[0-9a-fA-F]{6}/);
  });
});

describe('③ 두 층을 같이 더하지 않는다', () => {
  /* `INST` 는 동료가 아니라 상위 집합이다 — 다 더하면 기관을 두 번 센다. */
  it('대분류와 세분이 서로 겹치지 않는다', () => {
    /* 구간으로 자른다 — `FUT_TOP:[^\]]*\]` 는 `list[tuple[str, str]` 의
       **첫 닫는 괄호**에서 끊긴다(첫 판에서 밟았다). */
    const top = FLOW_PY.slice(FLOW_PY.indexOf('FUT_TOP'), FLOW_PY.indexOf('FUT_SUB'));
    const sub = FLOW_PY.slice(FLOW_PY.indexOf('FUT_SUB'), FLOW_PY.indexOf('FUT_DEAD'));
    expect(top).toContain('"INST"');
    for (const k of ['SECU', 'TRUST', 'BANK', 'INSUR', 'MERCH', 'PENS']) {
      expect(sub, k).toContain(`"${k}"`);
      expect(top, `${k} 가 대분류에도 있어요 — 이중계상입니다`).not.toContain(`"${k}"`);
    }
  });

  it('항등식을 **재고** 어긋나면 말한다', () => {
    expect(FLOW_PY).toContain('inst_identity_error');
    expect(FLOW_PY, '어긋난 행을 조용히 넘기고 있어요').toMatch(/if err:/);
  });
});

describe('④ 두 원천의 asof 를 따로 적는다', () => {
  /* 현물이 늦게 들어오는 것이 **정상**이다 [OWNER 2026-10-19] — 한 수로 적으면
     그 사실이 화면에서 사라지고, 어긋남이 경고처럼 읽힌다. */
  it('서버가 둘을 따로 싣는다', () => {
    expect(FLOW_PY).toMatch(/"asof": \{"fut":/);
  });

  it('화면이 둘을 따로 적는다', () => {
    expect(FLOW_PAGE).toContain('got.asof.fut');
    expect(FLOW_PAGE).toContain('got.asof.cash');
  });

  it('워터마크가 복합이다 — 한쪽만 세면 다른 쪽이 들어와도 캐시가 안 바뀐다', () => {
    const i = FLOW_PY.indexOf('def watermark()');
    const body = FLOW_PY.slice(i, FLOW_PY.indexOf('def _fetch()'));
    expect(body).toContain('{FUT_TABLE}');
    expect(body).toContain('{CASH_TABLE}');
  });
});

describe('⑤ 리드아웃 스트립이 범례를 흡수한다', () => {
  /* 범례를 따로 두면 「지금 그려진 것」과 「끄는 손잡이」가 갈릴 수 있다 —
     그 셋을 한 칸에 모으는 것이 `ChartReadoutStrip` 이 생긴 이유다. */
  it('스트립을 쓰고 손수 만든 범례는 없다', () => {
    expect(FLOW_PAGE).toContain('<ChartReadoutStrip');
    expect(FLOW_PAGE, '범례를 손으로 또 만들고 있어요 — 스트립이 그 일을 해요')
      .not.toMatch(/sr-casedash|범례/);
  });

  it('스트립이 `sr-plot` 보다 **먼저** 선다 — 그림 밖·위', () => {
    const strip = FLOW_PAGE.indexOf('<ChartReadoutStrip');
    const plot = FLOW_PAGE.indexOf('className="sr-plot"');
    expect(strip).toBeGreaterThan(0);
    expect(plot).toBeGreaterThan(strip);
  });

  it('칸마다 **값과 토글**을 든다 — 범례이자 값이자 손잡이', () => {
    const i = FLOW_PAGE.indexOf('const slots');
    const body = FLOW_PAGE.slice(i, i + 900);
    /* 서식 **이름**이 아니라 「칸이 값을 든다」를 잰다. 리터럴 `fmt(` 로
       박아 뒀더니 누적 자를 `fmtCum` 으로 가르는 순간 탐지가 샜다
       (2026-10-19 — `chart-stability` 가 `addLine(` 로 샌 것과 같은 과). */
    expect(body).toMatch(/value: fmt\w*\(/);
    expect(body).toMatch(/toggle: \{ on:/);
    expect(body).toMatch(/chars/);          // 값 자리를 미리 비운다
  });

  it('★감싸는 상자가 **세로**다 — 가로면 스트립이 내용 폭으로 줄어 잘린다', () => {
    /* 실측 2026-10-19: `Box`(가로 flex) 안에서 상자 618px · 스트립 141px ·
       계열 영역 16px 이 되어 값이 DOM 에만 있고 안 보였다. */
    const i = FLOW_PAGE.indexOf('<ChartReadoutStrip');
    const before = FLOW_PAGE.slice(Math.max(0, i - 200), i);
    expect(before, '스트립을 `Box` 로 감쌌어요 — `VStack` 이어야 폭을 찹니다')
      .toMatch(/<VStack[^>]*width="100%"/);
  });

  it('두 그림이 **한 커서**를 나눈다', () => {
    expect(FLOW_PAGE).toContain('onHoverIndex={onCum}');
    expect(FLOW_PAGE).toContain('onHoverIndex={onDay}');
    expect(FLOW_PAGE).toMatch(/syncIndex=\{cursor\?\.src === 'day'/);
    expect(FLOW_PAGE).toMatch(/syncIndex=\{cursor\?\.src === 'cum'/);
  });

  it('누적 그림도 **시간축**을 세운다 — 두 그림 사이에 제목 줄이 끼어서', () => {
    expect(FLOW_PAGE, 'hideTimeAxis 가 있으면 누적에서 날짜를 못 읽어요')
      .not.toContain('hideTimeAxis');
  });
});

describe('⑥ 화면 문장은 해요체다', () => {
  /* 판정은 `backend/tests/test_register.py::FORMAL` 과 같은 자다. 그 가드의
     범위(`COVERED`)가 아직 이 레인을 안 덮으므로 여기서 잰다. */
  const FORMAL = /(니다|한다\.|이다\.|않는다\.)/;

  it('서버가 내보내는 문장에 합니다체가 없다', () => {
    const says = [...FLOW_PY.matchAll(/"((?:[^"\\]|\\.)*(?:예요|에요|해요|이에요)[^"]*)"/g)]
      .map((m) => m[1]!);
    expect(says.length, '해요체 문장을 하나도 못 찾았어요 — 판정기가 샜어요')
      .toBeGreaterThan(2);
    for (const t of says) expect(FORMAL.test(t), t).toBe(false);
  });
});
