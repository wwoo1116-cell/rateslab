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
const FLOW_TABLE = read('src/flow/FlowTable.tsx');
const FLOW_MATRIX = read('src/flow/FlowMatrix.tsx');
const FLOW_LAB = read('src/flow/FlowLabWindow.tsx');
const LAB_PY = fs.readFileSync(path.join(ROOT, 'backend/app/flowlab.py'), 'utf8');
/* 주석을 **안** 벗긴다 — 이 파일에서 재는 것은 CSS 규칙 자체다. */
const TYPE_CSS = fs.readFileSync(path.join(ROOT, 'src/theme/type.css'), 'utf8');
const ISSUE_FACE = read('src/flow/IssuanceFace.tsx');
const FLOW_PY = fs.readFileSync(path.join(ROOT, 'backend/app/flow.py'), 'utf8');
const ISSUE_PY = fs.readFileSync(path.join(ROOT, 'backend/app/ktb_issuance.py'), 'utf8');
/* 주석을 **안** 벗긴다 — 틴트의 눈금과 그 비용이 머리 주석에 적혀 있고,
   「적어 뒀나」가 이 절이 재는 것의 절반이다. */
const TINT_TS = fs.readFileSync(path.join(ROOT, 'src/table/tint.ts'), 'utf8');
/* 주석을 **안** 벗긴다 — 「짝이 없다와 0 은 다른 말이다」가 주석에 있고,
   그 경고가 적혀 있나가 이 절이 재는 것의 절반이다. */
const FLOW_TABLE_RAW = fs.readFileSync(path.join(ROOT, 'src/flow/FlowTable.tsx'), 'utf8');

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

  it('스트립이 **제 그림(누적)** 보다 먼저 선다 — 그림 밖·위', () => {
    /* ⚠종전에는 **첫** `sr-plot` 보다 앞인지로 쟀다. 2026-10-20 에 이동평균·감마가
       주인공이 되면서 **일별 그림이 앞으로** 왔고(판정 → 일별 → 누적), 그 순간
       이 자가 거짓 양성을 냈다 — 스트립은 여전히 제 그림 위에 있는데.
       재는 것은 「첫 그림보다 앞」이 아니라 **「그 스트립이 설명하는 그림보다 앞」**
       이다.

       ⚠⚠**두 번째로 샜다** [2026-10-21]. 그 고침이 누적 그림을 `lines={lines}`
       **리터럴**로 집었는데, 가격 선이 들어오면서 변수가 `cumLines` 가 되자 이 자가
       또 거짓 양성을 냈다 — 이 리포가 적어 둔 그 과다(`chart-stability` 가
       `addLine(` 로 샌 것과 같다). 변수 이름은 **우연**이다.
       그래서 이제 **의미**로 집는다: 누적 그림의 `accessibilityLabel` 은 「누적
       순매수」로, 일별 쪽은 「일별 순매수와 이동평균」으로 시작한다. 그 문구는
       읽어 주는 말이라 리팩터로 안 바뀐다. */
    const strip = FLOW_PAGE.indexOf('<ChartReadoutStrip');
    const cum = FLOW_PAGE.indexOf('누적 순매수 —');
    expect(strip).toBeGreaterThan(0);
    expect(cum, '누적 그림을 못 찾았어요 — 읽어 주는 말이 바뀌었나요?')
      .toBeGreaterThan(0);
    expect(cum).toBeGreaterThan(strip);
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
    const says = [...FLOW_PY.matchAll(/"((?:[^"\\\n]|\\.)*(?:예요|에요|해요|이에요)[^"\n]*)"/g)]
      .map((m) => m[1]!);
    expect(says.length, '해요체 문장을 하나도 못 찾았어요 — 판정기가 샜어요')
      .toBeGreaterThan(2);
    for (const t of says) expect(FORMAL.test(t), t).toBe(false);
  });
});

describe('⑦ 만기물 · PD 인수 · 이동평균 · 발행 면 [OWNER 2026-10-19]', () => {
  /* 세 손잡이가 **서버 산술 + 화면 손잡이** 한 쌍씩이다. 한쪽만 남으면 손잡이가
     아무것도 안 하거나(화면만), 아무도 못 돌리는 산술이 된다(서버만). */
  it('현물 만기물 — 서버 열쇠와 화면 선택지가 같다', () => {
    expect(FLOW_PY).toContain('CASH_TENORS');
    expect(FLOW_PAGE).toMatch(/label="만기물"/);
    for (const k of ['2Y', '3Y', '5Y', '10Y', '20Y', '30Y', '50Y', '물가']) {
      expect(FLOW_PAGE, `${k} 선택지가 없어요`).toContain(`'${k}'`);
    }
    /* 「전체」가 분리 전 화면과 같은 수여야 한다 — 바구니 합이 ALL 이다. */
    expect(FLOW_PY).toMatch(/def sum_cash_buckets/);
  });

  it('PD 인수 — 서버가 더하고 화면이 몫을 묻는다, 그리고 가정이라고 말한다', () => {
    expect(FLOW_PY).toMatch(/def apply_pd/);
    expect(FLOW_PY).toContain('pd_share');
    expect(FLOW_PY, '가정이라는 말이 서버 문장에 없어요').toMatch(/가정이에요/);
    expect(FLOW_PAGE).toContain('pdShare');
    expect(FLOW_PAGE, '몫을 묻는 숫자 칸이 없어요').toContain('<NumField');
  });

  /* ⑧ [OWNER 2026-10-20] 「금융투자가 60%면 남는 40%는 은행이 하는 거 알고있지?」 —
     그렇다. 그래서 **몫은 하나**이고 은행은 나머지다. 둘을 따로 받는 칸이 생기면
     합이 100 이 아닌 상태를 화면이 만들 수 있고, 그건 제도에 없는 상태다. */
  it('PD 몫은 **하나**다 — 은행은 나머지이고, 제도와 가정을 갈라 말한다', () => {
    expect(FLOW_PY, '은행 몫을 따로 받고 있어요 — 나머지여야 해요')
      .toMatch(/1\.0 - share|1 - share/);
    expect(FLOW_PY, '은행 몫을 받는 인자가 생겼어요').not.toMatch(/bank_share/);
    expect((FLOW_PAGE.match(/<NumField/g) ?? []).length,
      '몫을 묻는 숫자 칸은 하나여야 해요').toBe(1);
    /* 합이 100 이라는 것은 **제도**고, 60 이라는 수가 가정이다. 종전 문장은
       「자료에 없는 배분이라 가정이에요」라 합까지 의심하는 말로 읽혔다. */
    expect(FLOW_PY, '제도와 가정을 안 가르고 있어요').toMatch(/제도이고/);
  });

  /* ⑨ 테너 × (발행 + 주체) 한 표 [OWNER 2026-10-20 — 「이 표를 좌측에 박아두고,
     우측에는 보험이면 순매수세가 어떻게 됐는지 MA로」]. */
  it('행렬 — 발행이 수급표의 열이고, 칸이 (만기물 × 주체) 를 고른다', () => {
    expect(FLOW_PY, '행렬을 내는 함수가 없어요').toMatch(/def cash_matrix/);
    expect(FLOW_PY, '구간을 봉 수로 자르지 않아요').toMatch(/def span_slice/);
    /* 발행 열은 공급표 그대로다 — PD 노브가 공급 자체를 바꾸면 두 번 센다. */
    expect(FLOW_PY).toMatch(/supply_table/);
    expect(FLOW_MATRIX, '칸이 버튼이 아니에요').toMatch(/<button[\s\S]{0,400}aria-pressed/);
    expect(FLOW_MATRIX, 'tr 에 role 을 얹었어요').not.toMatch(/<tr[^>]*role=/);
    expect(FLOW_PAGE, '칸이 만기물과 주체를 같이 안 고르고 있어요')
      .toMatch(/setCashTenor\(t\)[\s\S]{0,80}setDaily\(subject\)/);
    /* 표와 그림이 **같은 창**을 봐야 한다 — 화면이 쓰는 봉 수를 그대로 넘긴다. */
    expect(FLOW_PAGE).toMatch(/span:\s*SPAN_BARS\[span\]/);
  });

  /* ⑩ 선물은 「잠시 폐기」이고 발행 면은 접혔다 — **지운 게 아니다**.
     되살리는 것이 배열 한 줄이어야 한다. */
  it('면을 접었을 뿐 지우지 않았다 — 선물 라우트와 발행 면 파일이 남아 있다', () => {
    expect(FLOW_PAGE).toMatch(/FACES_SHOWN/);
    expect(FLOW_PY, '선물 면이 지워졌어요').toMatch(/def _fut_board/);
    expect(fs.existsSync(path.join(ROOT, 'src/flow/IssuanceFace.tsx')),
      '발행 면 파일이 지워졌어요 — 접은 것이지 버린 게 아니에요').toBe(true);
    /* 접었으면 **입찰 상세가 어딘가 남아야** 한다(응찰률·수요 판정). */
    expect(FLOW_PAGE, '입찰 상세가 통째로 사라졌어요').toMatch(/AuctionFact/);
    expect(FLOW_PAGE).toMatch(/수요 판정/);
  });

  /* ⑫ [OWNER 2026-10-20] 가정이 섞인 칸은 **표 안에서** 구별돼야 한다. 조건 줄의
     회색 문장만으로는 표만 보고 못 가린다(은행 3년물 +12.9 → +27.8조). */
  it('PD 가 켜지면 그 두 열이 표에서 구별된다', () => {
    expect(FLOW_PY, '어느 열이 가정인지 페이로드가 안 들고 있어요')
      .toMatch(/"pd": bool\(pd_share is not None and c in PD_COLS\)/);
    expect(FLOW_MATRIX, '표가 그 표식을 안 그려요').toMatch(/c\.pd \?/);
    expect(FLOW_MATRIX).toMatch(/PD 포함/);
    /* 말줄임 금지라 줄여 적지 않고 둘째 줄에 쓴다 — 스택이어야 한다. */
    expect(FLOW_MATRIX).toMatch(/sr-rv-linkbtn sr-rv-stack/);
  });

  /* ⑬ 표가 닫혔나를 **서버가** 세고 화면은 읽는다. 열 주체 합은 PD 끔이면 0,
     켬이면 발행과 같다 — 그 한 줄이 분해 누락과 PD 이중계상을 같이 잡는다. */
  it('합계 검산을 서버가 내고, 안 닫히는 날은 지목한다', () => {
    expect(FLOW_PY).toMatch(/def _matrix_check/);
    expect(FLOW_PY, '봉 단위로 안 재면 깨진 하루가 반올림에 묻혀요')
      .toMatch(/CHECK_BREAK/);
    expect(FLOW_MATRIX).toMatch(/matrix\.check\.say/);
    /* 화면이 합을 **다시 세지 않는다**(§16) — 서버의 수를 읽기만 한다. */
    expect(FLOW_MATRIX).not.toMatch(/reduce\(|\.map\([^)]*\)\.reduce/);
  });

  /* ⑭ 중복을 들어냈다 [OWNER 2026-10-20 — 「빼도되는건 빼보면서 가보자」].
     되살아나면 같은 수가 다시 세 곳에 선다. */
  it('히어로와 중복 사실 칸이 **돌아오지 않는다**', () => {
    expect(FLOW_PAGE, '히어로가 돌아왔어요').not.toMatch(/평소 대비가 가장 큰 주체예요/);
    expect(FLOW_PAGE, '「오늘·순위 위 셋」이 돌아왔어요').not.toMatch(/순위 위 셋/);
    expect(FLOW_PAGE, '「그림 넷」 칸이 돌아왔어요').not.toMatch(/그림 넷/);
    expect(FLOW_PAGE, '「모집단」 칸이 돌아왔어요').not.toMatch(/title="모집단"/);
    expect(FLOW_PAGE, '「단위」 조건 칸이 돌아왔어요').not.toMatch(/k="단위"/);
    /* 남긴 하나는 **다른 데 없는 사실**이다. */
    expect(FLOW_PAGE).toMatch(/title="PD 인수 보정 · 올해"/);
  });

  /* ⑮ 구간이 섞이면 같은 주체가 두 수로 선다(1Y 보험 +20.3 대 올해 +17.9). */
  it('행렬 제목이 구간을 지고, 순위표가 「올해」를 따로 말한다', () => {
    expect(FLOW_PAGE).toMatch(/만기물별 발행과 순매수 · \$\{span === 'ALL' \? '전체 구간' : span\}/);
    expect(FLOW_PAGE).toMatch(/마지막\s*\n?\s*열만 올해/);
  });

  /* ⑯ 느린 주체는 분기 눈금이라 60일까지로는 안 보인다 — **창 넷은 그대로
     온다**. 바뀐 것은 그중 **몇을 그리나**이고, 그 선택을 **서버 판정이** 한다.

     ★[OWNER 2026-10-22 — 「걍 뺄 수 있는 건 다 빼보는 방식으로 미니멀하게,
     COT 정도의 밀도면 좋을 듯」]. 10-20 의 「동시에 여러 MA」를 이 지시가 덮는다.
     지우는 근거는 취향이 아니라 **이 리포의 실측**이다: Γ5·Γ20 은 부호가
     5~7일마다 뒤집혀(10년에 150번) `WINDOW_TRUST` 가 「잡음」으로 판정하고,
     **판정 문장도 이미 그 둘을 빼고 쓴다**. 그림만 넷을 같은 무게로 그려서,
     한 카드가 「이 둘은 신호가 아니에요」라고 적으면서 동시에 그리고 있었다.

     ⚠**수는 안 지운다** — 감마 줄에 넷이 그대로 서고 잡음인 둘은 흐리다
     (아래 ⑰ 이 그걸 지킨다). 「재 봤고 잡음이더라」는 사실이다. */
  it('그릴 창을 **서버 판정이 고른다** — 화면이 창 목록을 안 적는다', () => {
    expect(FLOW_PY).toMatch(/MA_WINDOWS = \(0, 5, 20, 60, 120\)/);
    expect(FLOW_PY, '서버가 창 넷을 안 싣고 있어요').toMatch(/"mas":/);
    /* ★판정을 읽어서 거른다 — **창 번호를 화면에 적지 않는다.** 하드코딩하면
       서버가 판정을 바꿔도 그림이 안 따라오고, 둘이 다른 말을 하게 된다. */
    expect(FLOW_PAGE, '그릴 창을 화면이 직접 고르고 있어요')
      .toMatch(/r\.trust === '잡음'[\s\S]{0,120}\.map\(\(r\) => r\.window\)/);
    expect(FLOW_PAGE).toMatch(/const maShown/);
    expect(FLOW_PAGE, '그림이 거른 목록을 안 쓰고 있어요').toMatch(/maShown\.map/);
    /* 창 번호가 화면에 박히면 안 된다 — 서버 판정이 유일한 출처다. */
    expect(FLOW_PAGE, '창 번호를 화면이 적고 있어요')
      .not.toMatch(/window === (?:5|20)/);
    /* 고를 것이 없으면 컨트롤도 없다 — 폭만 먹는다. */
    expect(FLOW_PAGE, '단일 선택 컨트롤이 돌아왔어요').not.toMatch(/MA_OPTIONS/);
    /* ★새 칸은 **없을 수 있는 것**으로 다룬다 — 프런트는 즉시 서고 백엔드는
       30분 주기라, 그 사이 `mas` 가 없는데 바로 `.map` 하면 면이 통째로 죽는다
       (실측 2026-10-20 — 「Cannot read properties of undefined」). */
    expect(FLOW_PAGE, '옛 서버에서 화면이 죽어요').toMatch(/got\.series\.mas \?\? \[\]/);
  });

  /* ⑰ 감마는 **그림 아래 한 줄**이다 [OWNER 2026-10-20 — 「그림아래 감마 한줄로」].
     표에 값 모드를 더하는 안은 버렸다 — 같은 표가 세 가지를 말하면 모드를 놓친
     사람이 구간 합을 감마로 읽는다. */
  it('감마가 그림 아래 한 줄로 서고, 산술은 서버가 한다', () => {
    expect(FLOW_PY, '감마 산술이 서버에 없어요').toMatch(/def gamma\(/);
    expect(FLOW_PY, '판정을 내는 자리가 없어요').toMatch(/def verdict\(/);
    expect(FLOW_PY).toMatch(/WINDOW_TRUST/);
    /* 그림이 세운 주체와 **같은 열쇠**여야 한다 — 갈리면 그림과 그 아래 줄이
       다른 계열을 말한다. */
    expect(FLOW_PY).toMatch(/verdict\(cols, daily or picked\[0\]\)/);
    expect(FLOW_PAGE).toMatch(/<GammaLine g=\{got\.gamma\}/);
    /* 화면이 감마를 **다시 재지 않는다**(§16) — 이동평균과 같은 규율. */
    expect(FLOW_PAGE).not.toMatch(/MA_n|movingAverage|rolling/i);
    /* 잡음인 창을 지우지 않고 흐리게 둔다 — 「안 보인다」와 「없다」는 다른 말. */
    expect(FLOW_PAGE).toMatch(/trust === '잡음'/);
  });

  /* ⑱ 평균선은 **제 축**에 선다 [OWNER 2026-10-20 — 「이동평균 지금 너무 작아서
     보이지도 않음」]. 한 축에 겹치면 일별 막대가 세로를 다 먹는다 — 실측으로
     평균선이 차지하는 비중이 MA5 43% → MA20 25% → MA60 11% → **MA120 4.0%** 라,
     느린 주체에 꼭 필요한 창이 제일 묻혔다. */
  it('이동평균이 왼쪽 축으로 가고, 화면이 그 사실을 적는다', () => {
    /* ⚠창을 **끝 표시로** 잡는다. `stripComments` 는 블록 주석을 지우지 않고
       **공백으로 채워 길이를 보존**하므로(줄 번호를 살리려고), 고정 길이 창은
       주석이 길어진 순간 코드에 못 닿는다 — 첫 판이 900자로 끊겨 `axis` 를
       못 봤다. */
    const i = FLOW_PAGE.indexOf('const dailyLines');
    const body = FLOW_PAGE.slice(i, FLOW_PAGE.indexOf('}, [win, maShown, fmt]);', i));
    expect(body, '평균선이 아직 막대와 같은 축이에요').toMatch(/axis: 'aux'/);
    /* 막대는 **오른쪽 그대로** — 둘 다 옮기면 축을 가른 뜻이 없다. */
    expect(body).not.toMatch(/kind: 'histogram'[\s\S]{0,200}axis: 'aux'/);
    /* ★축이 둘이라는 것을 안 적으면 「그날보다 평균이 크다」로 읽힌다.
       2026-10-22 에 범례 문장을 걷어내면서 **이 두 글자는 남겼다** — 적/청이
       순매수·순매도라는 것은 앱 전체 문법이라 뺐지만, 축이 둘인 것은 **이
       그림만의 사실**이라 여기 말고 적을 데가 없다.

       ⚠축을 하나로 합치는 것은 **못 한다**(실측 2026-10-22, 자산운용 1Y):
       막대가 −18,581~+16,162억인데 MA60·120 은 −576~+1,521억이라, 합치면
       평균선이 0 에 눌려 모양이 사라진다. */
    expect(FLOW_PAGE, '축이 둘이라는 말이 사라졌어요').toMatch(/왼쪽 축/);
    expect(FLOW_PAGE, '앱 공용 방향색을 이 그림만 또 적고 있어요')
      .not.toMatch(/막대는 빨강이 순매수/);
  });

  /* ⑳ ★**주인공 차례** [OWNER 2026-10-20 — 「이게 메인이어야 하는데 반영된거
     맞니」]. 첫 판에서 판정 문장만 키우고 자리는 안 옮겨서, 주인공이 작은 칸의
     맨 아래에 서서 화면 밖으로 밀렸다(일별+MA 161px 대 누적 321px). */
  it('이동평균·감마가 **주인공 자리**에 선다', () => {
    const card = FLOW_PAGE.slice(FLOW_PAGE.indexOf('flexBasis={460}'));
    const gamma = card.indexOf('<GammaLine');
    /* ★그림을 **읽어 주는 말**로 집는다, 변수 이름이 아니라 [2026-10-21] —
       `lines={lines}` 로 집었더니 가격 선이 들어와 `cumLines` 가 되는 순간 샜다.
       위 ⑤ 의 같은 자리에 그 경위가 적혀 있다. */
    const daily = card.indexOf('일별 순매수와 이동평균');
    const cum = card.indexOf('누적 순매수 —');
    expect(gamma, '판정이 없어요').toBeGreaterThan(0);
    expect(gamma, '판정이 그림들 **뒤**에 있어요 — 머리말이어야 해요')
      .toBeLessThan(daily);
    expect(daily, '일별+MA 가 누적 **뒤**에 있어요 — 앞이어야 해요').toBeLessThan(cum);
    /* 몫도 일별이 커야 한다. */
    expect(card).toMatch(/lines=\{dailyLines\}/);
    const dailyBox = card.lastIndexOf('flexGrow={2}', daily);
    expect(dailyBox, '일별 그림이 큰 몫(flexGrow 2)을 안 가졌어요').toBeGreaterThan(0);
  });

  /* ㉑ 수급 신호 실험 창 [OWNER 2026-10-20 — 「이거 내가 사용할 수 있어야한다고,,
     Backtest에서 처럼」]. 오늘의 검정이 스크래치패드에서 증발했으므로 산술을
     제품으로 옮겼다. ★이 창의 존재 이유는 **수 옆에 우연을 같이 적는 것**이다. */
  it('실험 창이 **수를 혼자 안 보여 준다** — 우연을 같이 싣는다', () => {
    expect(LAB_PY, '그 칸의 우연이 없어요').toMatch(/"shuffle":/);
    expect(LAB_PY, '★탐색의 우연이 없어요 — 이게 판정의 자예요')
      .toMatch(/"searchCeiling":/);
    expect(LAB_PY, '원형 이동이 아니면 자기상관이 깨져요').toMatch(/def shift\(/);
    /* 판정은 **탐색의 우연**으로 가른다 — 한 칸의 p 로 가르면 열 번에 한 번은
       「살았다」가 나온다(2026-10-20 에 내가 그렇게 한 번 틀렸다). */
    expect(FLOW_LAB).toMatch(/const verdict = beat == null \? null : beat <= 0\.05/);
    expect(FLOW_LAB, '탐색의 우연을 화면이 안 적어요').toMatch(/탐색의 우연/);
  });

  it('실험 창이 **캐논 부품**을 쓴다 — 손으로 쌓지 않는다', () => {
    /* [OWNER 2026-10-20 — 「v2 디자인 문법 사용하려면 제대로 사용하기」]. 첫 판은
       수 네 칸을 `VStack` 으로 쌓았고 커서 리드아웃이 아예 없었다 — 둘 다 이
       리포에 이미 있는 부품이다(CLAUDE.md 캐논 규칙 1). */
    expect(FLOW_LAB, '사실 스트립을 손으로 쌓고 있어요').toMatch(/<StatColumn/);
    expect(FLOW_LAB).toMatch(/<Stat /);
    expect(FLOW_LAB, '커서 리드아웃이 없어요').toMatch(/<ChartReadoutStrip/);
    expect(FLOW_LAB, '값 자리를 안 비우면 커서마다 칸이 흔들려요').toMatch(/slotChars\(/);
    expect(FLOW_LAB, '컨트롤에 라벨이 위로 안 서요').toMatch(/<Field label=/);
    /* 얼라인 — 행은 바닥 정렬이고 버튼도 32px 상자에 담긴다. */
    expect(FLOW_LAB).toMatch(/alignItems="flex-end"/);
    expect(FLOW_LAB, '실행 버튼이 32px 상자 밖이에요')
      .toMatch(/<Box width=\{96\} height=\{CONTROL_H\}>[\s\S]{0,400}<Button/);
    /* hex 는 direction.css 에만 — 창에는 없다. */
    expect(FLOW_LAB).not.toMatch(/#[0-9a-fA-F]{6}/);
  });

  it('창이 **단위를 안 섞는다** — `fmtJo` 는 백만원을 받는다', () => {
    /* ★실측 2026-10-20: `dv01`(원)을 `fmtJo`(백만원)에 그대로 넣어 1,000만원이
       「10.0조」로 찍혔다. 단위가 다른 수를 같은 서식에 넣으면 **그럴듯하게**
       틀린다 — 화면만 보고는 못 가린다. */
    expect(FLOW_LAB, 'dv01 을 fmtJo 에 넣고 있어요 — 단위가 달라요')
      .not.toMatch(/fmtJo\(got\.dv01\)/);
    expect(FLOW_LAB).toMatch(/got\.dv01 \/ 1e4/);
  });

  it('실험 창이 **스스로 안 돈다** — 사람이 실행을 누른다', () => {
    /* Backtest 와 같은 규율(`BacktestWindow` 머리). 손잡이마다 저절로 돌면
       「고르는 중에 결과가 바뀌는」 화면이 되고, 그러면 제일 좋은 칸을 무심코
       고르게 된다 — 그게 오늘 죽은 그 길이다. */
    expect(FLOW_LAB).toMatch(/<Button[\s\S]{0,120}onClick=\{run\}/);
    /* 손잡이 상태가 `useEffect` 의 의존성에 들어가면 저절로 돈다. */
    expect(FLOW_LAB).not.toMatch(/useEffect\(\(\) => \{ run\(\); \}, \[run\]\)/);
  });

  it('고를 수 있는 칸을 **안 자른다** — 격자가 서버와 같은 벌이다', () => {
    /* 첫 판은 주체를 셋만 세웠고(`slice(0,3)`), 그러면 탐색에서 실제로 1등 했던
       국가지자체를 아예 못 고른다 — 고를 수 없는 칸이 있는 실험 창은 그 자체가
       숨은 선택이다. */
    expect(FLOW_LAB, '주체를 잘라서 보여 주고 있어요').not.toMatch(/subjects\.slice\(/);
    expect(FLOW_LAB, '만기물을 걸러서 보여 주고 있어요').not.toMatch(/tenors\.filter\(/);
    for (const n of [5, 10, 15, 20, 25, 30]) expect(FLOW_LAB).toContain(String(n));
    expect(LAB_PY).toMatch(/SHORTS = \(5, 10, 15, 20, 25, 30\)/);
    expect(LAB_PY).toMatch(/LONGS = \(40, 50, 60, 70, 90, 120\)/);
    expect(LAB_PY).toMatch(/HOLDS = \(1, 5, 10, 20, 40\)/);
  });

  it('실험도 **공표 지연**을 진다 — 엿보기를 못 만들게 한 곳에서', () => {
    expect(LAB_PY).toMatch(/^LAG = 1$/m);
    expect(LAB_PY, '지연을 _align 밖에서 넣으면 호출부가 엿보기를 만든다')
      .toMatch(/k \+ 1 \+ LAG/);
    expect(LAB_PY, '비용 정본이 계획면이 아니에요').toMatch(/COST_BP = mrplan\.COST_BP/);
  });

  /* ⑲ ★**이 면은 설명이지 예측이 아니다** [판정 2026-10-20]. 수급으로 금리
     방향을 맞추는 것을 네 번 쟀고 네 번 다 우연을 못 넘었다(단일 0.87 대 우연
     0.93 · AND/OR 0.92 대 1.02 · 보유기간까지 0.97 대 **1.36**). 화면이 그
     사실을 적어야 다음 사람이 이 줄을 신호로 읽지 않는다. */
  it('화면이 「설명이지 예측이 아니다」를 말한다', () => {
    expect(FLOW_PY, '판정 근거가 모듈에 안 적혀 있어요').toMatch(/설명이지 예측이 아니다/);
    expect(FLOW_PY, '화면 문장이 그 말을 안 해요').toMatch(/설명이지 예측이 아니에요/);
    /* 판정 문서가 남아 있어야 한다 — 다음 레인이 같은 탐색을 다시 돌리지 않게. */
    expect(fs.existsSync(path.join(ROOT, 'docs/VERDICT_flow_direction_2026-10-20.md')),
      '판정 문서가 없어졌어요').toBe(true);
  });

  /* ⑪ CDS `Tooltip` 앵커가 `justify-content: flex-end` 라 왼쪽 정렬 머리에서
     글자가 오른끝으로 간다 — 실측(2026-10-20): 칸 405~800 인데 머리 글자가
     744~792, 그 칸의 값은 413~492 로 **350px 어긋났다**. */
  it('왼쪽 정렬 머리의 뜻풀이 앵커가 왼쪽에 선다', () => {
    expect(TYPE_CSS, '왼쪽 정렬 머리 안 앵커를 되돌리는 규칙이 없어요')
      .toMatch(/\.sr-rv-th\.sr-rv-left\s*>\s*\*\s*\{[^}]*justify-content:\s*flex-start/);
  });

  it('이동평균 — 서버가 내고 화면은 선만 긋는다', () => {
    expect(FLOW_PY).toMatch(/def moving_average/);
    expect(FLOW_PY, '창 미만을 None 으로 두지 않아요').toMatch(/else None/);
    expect(FLOW_PAGE).toContain('series.ma');
    /* 화면이 평균을 다시 재면 두 면이 다른 수를 말할 수 있다. */
    expect(FLOW_PAGE).not.toMatch(/movingAverage|rolling/i);
  });

  it('일별 그림의 주체는 표의 **이름 버튼**이 고른다 — tr 에 role 을 얹지 않는다', () => {
    expect(FLOW_TABLE).toContain('onPick');
    expect(FLOW_TABLE).toMatch(/<button[\s\S]{0,300}aria-pressed/);
    expect(FLOW_TABLE).not.toMatch(/<tr[^>]*role=/);
    expect(FLOW_PAGE).toMatch(/onPick=\{setDaily\}/);
  });

  it('발행 면도 같은 문법 — 스트립이 그림 위·세로 상자·토큰 색', () => {
    const strip = ISSUE_FACE.indexOf('<ChartReadoutStrip');
    const plot = ISSUE_FACE.indexOf('className="sr-plot"');
    expect(strip).toBeGreaterThan(0);
    expect(plot).toBeGreaterThan(strip);
    expect(ISSUE_FACE.slice(Math.max(0, strip - 200), strip)).toMatch(/<VStack[^>]*width="100%"/);
    expect(ISSUE_FACE).toContain('--sr-flow-1');
    expect(ISSUE_FACE).not.toMatch(/#[0-9a-fA-F]{6}/);
    expect(ISSUE_FACE).not.toContain('hideTimeAxis');
    expect(FLOW_PAGE).toContain("face === 'issue'");
  });

  it('★물가채 제목은 서버가 직접 짓는다 — 원문 제목이 「국고채 10년물」을 달고 있다', () => {
    expect(ISSUE_PY).toMatch(/"제목": f"\{LABEL/);
    expect(ISSUE_PY, '물가채 라벨이 없어요').toContain('"물가": "물가채"');
  });

  it('발행 서버 문장도 해요체다', () => {
    const FORMAL = /(니다|한다\.|이다\.|않는다\.)/;
    const says = [...ISSUE_PY.matchAll(/"((?:[^"\\\n]|\\.)*(?:예요|에요|해요|이에요)[^"\n]*)"/g)]
      .map((m) => m[1]!);
    expect(says.length).toBeGreaterThan(2);
    for (const t of says) expect(FORMAL.test(t), t).toBe(false);
  });
});

/* ㉒ 가격 × 미결제약정 2×2 [OWNER 2026-10-21 — 「해외에선 어떻게 해?」].
 *
 * 선물 데스크의 1차 판독을 옮긴 것이다. 이 절이 지키는 것 셋:
 *   ① 2×2 가 **가격** 기준으로 정의돼 있다(금리로 뒤집으면 관례가 거꾸로 읽힌다)
 *   ② 한쪽이 0 인 날을 **어느 칸에도 안 넣는다**
 *   ③ 가격 선의 **수준을 읽게 두지 않는다** — 보조축 + 그 사실을 적는 문장
 */
describe('㉒ 가격 × 미결제 2×2', () => {
  it('네 이름이 **가격** 기준으로 서 있다', () => {
    for (const n of ['신규 매수', '숏 커버', '신규 매도', '롱 청산']) {
      expect(FLOW_PY, `${n} 가 없어요`).toContain(n);
    }
    /* 가격 ↑ × 미결제 ↑ = 신규 매수. 이 짝이 뒤집히면 화면이 거짓말을 한다. */
    expect(FLOW_PY).toMatch(/if d_close > 0:\s*\n\s*return OI_NEW_LONG if d_oi > 0 else OI_SHORT_COVER/);
  });

  it('한쪽이 0 인 날은 **네 칸 어디도 아니다**', () => {
    expect(FLOW_PY, '0 을 한쪽에 붙이고 있어요')
      .toMatch(/if d_close == 0 or d_oi == 0:\s*\n\s*return None/);
  });

  it('집계가 **분모를 같이** 낸다 — 넷의 합이 구간 봉 수보다 작다', () => {
    expect(FLOW_PY, 'counted 가 없어요').toContain('"counted": counted');
    expect(FLOW_PAGE, '화면이 분모를 안 적어요').toContain('oi.counted');
  });

  it('가격 선은 **보조축**이고 수준을 읽게 두지 않는다', () => {
    expect(FLOW_PAGE, '가격이 주축에 서 있어요 — 단위가 다른데 같은 눈금이 돼요')
      .toMatch(/id: PRICE_KEY[\s\S]{0,220}axis: 'aux'/);
    /* 서버가 그 사실을 쥔다(§16) — 화면이 지어낸 문장이 아니다. */
    expect(FLOW_PY).toContain('"priceNote"');
    expect(FLOW_PY, '수준에 뜻이 없다는 말이 없어요').toMatch(/수준에 뜻이 없어요/);
    expect(FLOW_PAGE, '화면이 그 문장을 안 세워요').toContain('oi.priceNote');
    /* 스트립 값은 **Δ** 다 — 수준을 적으면 누군가 호가로 읽는다. */
    expect(FLOW_PAGE).toMatch(/label: '가격 Δ'/);
  });

  it('서버 문구는 **평문**이다 — 화면은 마크다운을 안 그린다', () => {
    const i = FLOW_PY.indexOf('"priceNote"');
    expect(i).toBeGreaterThan(0);
    expect(FLOW_PY.slice(i, i + 260), 'priceNote 에 ** 가 새어 나갔어요')
      .not.toContain('**');
  });

  it('현물 면은 2×2 를 **열쇠는 두고 값은 없이** 낸다', () => {
    /* 열쇠가 면마다 없으면 화면이 「안 왔다」와 「없다」를 구별 못 해 추측한다. */
    expect(FLOW_PY).toMatch(/#: ★현물엔 미결제약정이 없다[\s\S]{0,200}"oi": None/);
  });
});

/* ㉓ 순위 키 = 백분위, 그리고 **칠하는 축이 세우는 축과 같다** [2026-10-21].
 *
 * 이 절이 생긴 까닭: σ → 백분위 전환을 **가드가 하나도 안 잡았다.** 「칠하는 축과
 * 세우는 축이 같아야 눈과 순위가 서로를 반박하지 않는다」가 `table/tint.ts` 머리와
 * CLAUDE.md 캐논에 적혀 있는데 재는 자가 없었다 — 적어만 둔 규칙은 다음 사람이
 * 모르고 지나간다.
 */
describe('㉓ 순위 키는 백분위다', () => {
  it('서버가 **|백분위 − 50|** 로 세운다', () => {
    expect(FLOW_PY, 'percentile_of 가 없어요').toContain('def percentile_of(');
    expect(FLOW_PY, '정렬 키가 백분위가 아니에요')
      .toMatch(/rows\.sort\([\s\S]{0,200}pct[\s\S]{0,80}- 50\.0\)/);
  });

  it('동점은 **중간 순위**다 — 0 이 많은 주체의 0 이 바닥으로 읽히면 안 된다', () => {
    expect(FLOW_PY).toMatch(/below \+ 0\.5 \* ties/);
  });

  it('★칠하는 축이 세우는 축과 **같다**', () => {
    /* 표가 백분위로 줄을 세우면서 σ 로 칠하면 눈과 순위가 서로를 반박한다. */
    expect(FLOW_TABLE, '표가 백분위로 칠하지 않아요').toContain('flowPctTint(r.pct)');
    expect(FLOW_TABLE, 'σ 틴트가 남아 있어요 — 축이 둘이 됐어요')
      .not.toContain('flowTint(');
    expect(TINT_TS, '백분위 틴트가 없어요').toContain('export function flowPctTint');
  });

  it('하한은 **남아 있다** — 백분위로도 필요하다는 것이 실측이다', () => {
    /* ⚠내가 「백분위는 안 터지니 하한을 없앨 수 있다」로 적었고 틀렸다.
       하한 아래가 1위를 가져가는 비중이 백분위 37.9/60.8/29.1% 로 σ 와 같다. */
    expect(FLOW_PY).toContain('RANK_FLOOR = 500.0');
    expect(FLOW_PY).toContain('CASH_RANK_FLOOR = 40_000.0');
    expect(FLOW_PY, '그 실측이 적혀 있지 않아요 — 다음 사람이 또 없애려 한다')
      .toMatch(/백분위로 바꿔도 하한은 못 없앤다/);
  });

  it('꼬리 해상도를 잃는다는 **비용**이 적혀 있다', () => {
    expect(TINT_TS, '백분위의 비용이 안 적혀 있어요').toMatch(/꼬리 해상도를 잃는다/);
    expect(FLOW_TABLE, '화면이 꼬리를 어디서 보라고 말하지 않아요')
      .toMatch(/꼬리의 크기는 이 수로 안 갈려요/);
  });
});

/* ㉔ DV01 눈금 [OWNER 2026-10-21]. 계약수로는 만기물을 더할 수 없다.
 *
 * 이 절은 **단위 함정 셋**을 지킨다. 셋 다 이 세션에 실제로 밟았다:
 *   ① `creditmatrix` 는 소수를 주고 `par_pvbp` 는 퍼센트를 받는다
 *   ② `ALL` 은 바구니마다 환산한 **뒤** 더해야 한다
 *   ③ 하한은 **날것**으로 재야 한다 — 환산값으로 재면 조용히 무력해진다
 */
describe('㉔ DV01 눈금', () => {
  it('선물과 현물이 **다른 PVBP** 를 쓴다 — 다른 물건이다', () => {
    /* 선물은 KRX 5% 합성채가 규약, 현물은 par 채권. 하나로 묶으면 둘 중 하나가
       틀린다. */
    expect(FLOW_PY).toContain('def par_pvbp(');
    expect(FLOW_PY).toContain('def fut_dv01_per_contract(');
    expect(FLOW_PY, 'par_pvbp 를 선물에 쓰지 말라는 경고가 없어요')
      .toMatch(/선물에 쓰지 말 것/);
  });

  it('①커브는 **소수**이고 PVBP 는 **퍼센트**를 받는다', () => {
    /* 이 리포가 단위로 세 번 틀린 자리. ×100 이 코드에 있고 근거가 옆에 있어야 한다. */
    expect(FLOW_PY).toMatch(/cmx\.interp\(pts, years\) \* 100\.0/);
    expect(FLOW_PY, '소수/퍼센트 경고가 없어요').toMatch(/소수를 퍼센트로/);
  });

  it('②전체는 바구니마다 환산한 **뒤** 더한다', () => {
    expect(FLOW_PY).toContain('def cash_dv01_sum(');
    expect(FLOW_PY, '액면 합에 배수 하나를 곱하면 틀린다는 말이 없어요')
      .toMatch(/배수 하나를 곱하면 \*\*틀린다/);
    /* `cashDv01` 에 `ALL` 을 두면 틀린 길이 생긴다 — 그 금지가 적혀 있어야 한다. */
    expect(FLOW_PY).toMatch(/`ALL` 은 \*\*없다\*\*/);
  });

  it('③하한은 **날것**으로 잰다 — 환산값으로 재면 무력해진다', () => {
    expect(FLOW_PY, '_series_row 가 날것 계열을 안 받아요')
      .toMatch(/def _series_row\([\s\S]{0,220}native: list\[int\] \| None = None/);
    expect(FLOW_PY).toMatch(/조용히 무력해진다/);
    /* 화면도 같은 규율 — 일평균과 하한은 원단위로 적는다. */
    expect(FLOW_TABLE).toMatch(/일평균 \{val\(Math\.abs\(r\.avgAbs\), side\)/);
  });

  it('화면은 **손잡이가 아니라 응답의 눈금**으로 서식을 고른다', () => {
    /* 서버가 원단위로 떨어뜨렸는데 손잡이를 보고 서식을 고르면 계약수를
       억원/bp 로 적는다. */
    expect(FLOW_PAGE).toMatch(/got\?\.unitKey \?\? 'native'/);
    expect(FLOW_PAGE, '눈금 손잡이가 없어요').toMatch(/label="눈금"/);
    expect(FLOW_PAGE, '눈금의 한계를 안 세워요').toContain('got.unitNote');
  });

  it('원단위를 **지우지 않는다** — DV01 은 덧눈금이다', () => {
    expect(FLOW_PY).toMatch(/UNITS = \("native", "dv01"\)/);
    expect(FLOW_PY, '원단위가 기본이 아니에요').toMatch(/unit: str = "native"/);
  });
});

/* ㉕ 보유잔량 [OWNER 2026-10-21 — 「대사도 해주고」].
 *
 * 누적 순매수는 시작일이 임의라 포지션이 아니다. 짝과 단위는 **전수 대사로**
 * 확정했고(모듈 머리 §보유잔량), 이 절은 그 결론이 코드에 서 있는지 잰다.
 * ★제일 중요한 것: **「짝이 없다」와 「0」은 다른 말이다.**
 */
describe('㉕ 보유잔량', () => {
  it('짝 표가 **대사 결과**로 적혀 있다', () => {
    expect(FLOW_PY).toMatch(/HOLD_MAP: dict\[str, tuple\[str, \.\.\.\]\]/);
    expect(FLOW_PY, '투신+사모펀드 짝이 없어요')
      .toMatch(/"asset_management": \("투신", "사모펀드"\)/);
    expect(FLOW_PY, '보험기금 합성 표시가 없어요').toContain('HOLD_MERGED');
    /* 그 수치가 적혀 있어야 다음 사람이 손으로 바꾸지 않는다. */
    expect(FLOW_PY).toMatch(/99\.7%/);
    expect(FLOW_PY, '은행이 약하다는 실측이 없어요').toMatch(/45\.1%/);
  });

  it('★딜러는 **없다** — 더하면 더 나빠진다는 실측이 적혀 있다', () => {
    expect(FLOW_PY, 'HOLD_MAP 에 딜러가 들어갔어요')
      .not.toMatch(/HOLD_MAP[\s\S]{0,700}"financial_investment":/);
    expect(FLOW_PY).toMatch(/중위 −6\.156|중위 -6\.156/);
  });

  it('단위가 **전수 대사로** 확정돼 있다', () => {
    expect(FLOW_PY).toMatch(/HOLD_FACE_UNIT = 10_000\.0/);
    expect(FLOW_PY, '비율 100.000 실측이 없어요').toMatch(/\*\*정확히 100\.000\*\*/);
  });

  it('★「짝이 없다」와 「0」을 **화면이 가른다**', () => {
    /* 0 으로 그리면 「안 들고 있다」로 읽힌다 — 딜러가 바로 그 자리다. */
    expect(FLOW_TABLE).toMatch(/r\.hold == null \?[\s\S]{0,60}'—'/);
    expect(FLOW_TABLE_RAW, '짝 없음과 0 이 다르다는 경고가 없어요')
      .toMatch(/「짝이 없다」\*\*다 — 0 이 아니다/);
  });

  it('몫의 **분모**를 같이 낸다 — 332조가 큰 수인지 알 수 없다', () => {
    expect(FLOW_PY).toMatch(/"share": round\(face \/ total, 4\)/);
    expect(FLOW_TABLE, '화면이 몫을 안 적어요').toMatch(/r\.hold\.share \* 100/);
  });

  it('빈 열을 세우지 않는다 — 선물 면엔 칸이 아예 없다', () => {
    expect(FLOW_PY, '선물 면에 hold 열쇠가 없어요')
      .toMatch(/★선물엔 보유잔고 원천이 없다[\s\S]{0,80}"hold": None/);
    expect(FLOW_PAGE).toContain('showHold={!!got.hold}');
  });

  it('두 측정을 섞지 말라는 말을 **서버가** 쥔다', () => {
    expect(FLOW_PY).toMatch(/서로를 판정하지 않아요/);
    expect(FLOW_PAGE, '화면이 그 문장을 안 세워요').toContain('got.hold.note');
    /* 평문이어야 한다 — 이 리포가 세 번 밟았다. */
    const i = FLOW_PY.indexOf('note = ("보유 칸은');
    expect(i).toBeGreaterThan(0);
    expect(FLOW_PY.slice(i, i + 300)).not.toContain('**');
  });
});
