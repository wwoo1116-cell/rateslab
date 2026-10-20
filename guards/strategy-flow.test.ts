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
/* 주석을 **안** 벗긴다 — 이 파일에서 재는 것은 CSS 규칙 자체다. */
const TYPE_CSS = fs.readFileSync(path.join(ROOT, 'src/theme/type.css'), 'utf8');
const ISSUE_FACE = read('src/flow/IssuanceFace.tsx');
const FLOW_PY = fs.readFileSync(path.join(ROOT, 'backend/app/flow.py'), 'utf8');
const ISSUE_PY = fs.readFileSync(path.join(ROOT, 'backend/app/ktb_issuance.py'), 'utf8');

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

  /* ⑯ 느린 주체는 분기 눈금이라 60일까지로는 안 보인다. */
  it('이동평균 창에 120 일이 있다 — 서버와 화면이 같은 벌', () => {
    expect(FLOW_PY).toMatch(/MA_WINDOWS = \(0, 5, 20, 60, 120\)/);
    expect(FLOW_PAGE).toMatch(/value: '120', label: '120일'/);
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
