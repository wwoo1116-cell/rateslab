/* MR 세 화면이 **Main·Backtest 와 같은 문법**으로 서 있는가 [OWNER 2026-09-02 —
 * "이제 디자인 구성도 Main이나 Backtest와 통일해주세요"].
 *
 * ## 이 파일이 지는 명제 넷
 *
 * **떠 있는 창은 같은 리듬이다.** 창 몸통은 `padding 2 · gap 2`(Backtest 창의
 * 그 값)이고 머리 부제는 `caption`(Backtest 「{asOf} 종가까지」와 같은 급)이다.
 * 같은 위계의 창 둘이 안쪽 여백부터 다르면 나란히 놓았을 때 그 사실이 먼저
 * 보인다(CLAUDE.md 얼라인 5).
 *
 * **상태 문구는 앱에 한 문법이다.** 안내·빈 상태는 `body` 뮤트, 오류는 `body` +
 * `.sr-up` — Backtest·Main 미리보기가 쓰는 그것이다. MR 은 셋 다 `legal` 맨
 * 잉크였고, 그래서 「실행하지 못했어요」가 각주처럼 조용히 서 있었다.
 *
 * **차트는 LINKED PAIR 의 결로 쌓인다.** 세로 스택 + 같은 `dates` +
 * `useStackedScales` + **x 라벨은 맨 위만**(`hideTimeAxis`) + 십자선 `syncIndex`
 * 동기. 같은 눈금을 세 번 그리면 그게 다른 축인 줄 읽힌다.
 *
 * **일별 대사는 창 바닥 서랍이다.** Backtest 가 대사를 서랍에 둔 근거가 트레이더
 * 피드백 5(«팝업창 하단에 열었다 닫았다 하는 탭» — `WindowDrawer.tsx` 머리)이고,
 * MR 도 같은 물건을 같은 자리에 둔다. 종전에는 거래 패널의 내용이 «바뀌는» 판이라
 * 목록과 대사를 같이 볼 수 없었다.
 */

import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments } from './_source';

const root = path.resolve(import.meta.dirname, '..');
const src = (rel: string) => stripComments(fs.readFileSync(path.join(root, rel), 'utf8'));

/** 여는 태그를 **순서대로** 뽑는다 — 개수만 세면 「맨 위」 같은 순서 명제를 못
 *  지킨다(2026-09-02 검사가 그 구멍을 잡았다: hideTimeAxis 를 첫 차트로 옮겨도
 *  개수는 같아서 초록이었다). 중괄호 깊이를 세는 방식은 `control-parity` 의
 *  `openingTags` 판례 그대로다(속성 안의 `>` 를 넘기려면 그래야 한다). */
function openingTags(body: string, tag: string): string[] {
  const out: string[] = [];
  /* 낱말 경계는 문자열로 만든다 — 템플릿 리터럴 안의 `\b` 는 정규식 메타가
     아니라 **백스페이스 문자**(U+0008)가 되어 아무것도 안 잡는다(실측: 태그
     0개). 이 함수를 옮겨 심을 때 가장 밟기 쉬운 자리다. */
  const rx = new RegExp('<' + tag + String.fromCharCode(92) + 'b', 'g');
  let m: RegExpExecArray | null;
  while ((m = rx.exec(body))) {
    let depth = 0;
    for (let i = m.index; i < body.length; i++) {
      const c = body[i];
      if (c === '{') depth++;
      else if (c === '}') depth--;
      else if (c === '>' && depth === 0) { out.push(body.slice(m.index, i + 1)); break; }
    }
  }
  return out;
}

const WINDOWS = ['src/mr/StrategyWindow.tsx', 'src/mr/BookWindow.tsx'] as const;

describe('떠 있는 창의 리듬은 Backtest 와 한 값이다', () => {
  it('창 몸통 = padding 2 · gap 2', () => {
    /* 기준을 코드에서 읽는다 — Backtest 가 바뀌면 이 시험이 그 사실을 먼저
       말해야지, 여기 박아 둔 수와 갈리면 안 된다. */
    const bt = src('src/backtest/BacktestWindow.tsx');
    expect(bt).toMatch(/<VStack gap=\{2\} padding=\{2\} width="100%">/);
    for (const f of WINDOWS) {
      expect(src(f), f).toMatch(/<VStack gap=\{2\} padding=\{2\} width="100%">/);
    }
  });

  it('창 머리 부제는 caption 뮤트 — legal 이 아니다', () => {
    for (const f of WINDOWS) {
      const code = src(f);
      /* **창의** aside 다 — 파일의 첫 `aside={` 가 아니다. 2026-09-04 에 창
         본문의 `Panel` 이 자기 aside 를 갖게 되면서(근사 최적화 절의 순위
         기준 세그먼트) 첫 `aside={` 가 그쪽이 됐고, 이 시험이 패널의 활자를
         창 머리의 것이라고 읽었다. 닻은 `FloatingWindow` 의 첫 prop 이다. */
      const at = code.indexOf('windowKey=');
      expect(at, f).toBeGreaterThan(0);
      const aside = code.slice(code.indexOf('aside={', at), code.indexOf('onClose={onClose}', at));
      expect(aside, f).toMatch(/font="caption"/);
      expect(aside, f).not.toMatch(/font="legal"/);
    }
  });
});

describe('상태 문구는 앱에 한 문법이다', () => {
  it('오류는 body + sr-up(Backtest 와 같은 것)', () => {
    const bt = src('src/backtest/BacktestWindow.tsx');
    expect(bt).toMatch(/실행하지 못했어요/);
    for (const f of WINDOWS) {
      const code = src(f);
      const i = code.indexOf('실행하지 못했어요');
      expect(i, f).toBeGreaterThan(0);
      /* 그 문장을 감싼 여는 태그를 뒤로 훑어 활자를 본다. */
      const open = code.lastIndexOf('<Text', i);
      const tag = code.slice(open, i);
      expect(tag, f).toMatch(/font="body"/);
      expect(tag, f).toMatch(/className="sr-up"/);
    }
  });

  it('안내·빈 상태·stale 은 body 뮤트', () => {
    for (const f of WINDOWS) {
      const code = src(f);
      const i = code.indexOf('설정이 실행과 달라요');
      expect(i, f).toBeGreaterThan(0);
      const tag = code.slice(code.lastIndexOf('<Text', i), i);
      expect(tag, f).toMatch(/font="body"/);
      expect(tag, f).toMatch(/color="fgMuted"/);
    }
  });
});

describe('차트는 LINKED PAIR 의 결로 쌓인다', () => {
  it('패널은 풀폭이다 — flexBasis 50% 의 «한 줄에 둘» 주장이 사라졌다', () => {
    const parts = src('src/mr/parts.tsx');
    expect(parts).not.toMatch(/flexBasis="50%"/);
    expect(parts).toMatch(/<VStack gap=\{0\.5\} width="100%" minWidth=\{0\}>/);
  });

  it('x 라벨은 **맨 위** 차트만 진다 — 순서로 잰다', () => {
    /* 종전에는 `hideTimeAxis` **개수**만 셌다. 그러면 축이 스택 한가운데나 맨
       아래로 내려가도 초록이라, 「같은 눈금을 다른 축인 줄 읽는」 바로 그 실패를
       못 잡는다(2026-09-02 검사가 변형으로 확인). 이제 여는 태그를 순서대로
       잘라 첫 블록에는 없고 나머지에는 각각 있는지를 본다. */
    for (const f of WINDOWS) {
      const tags = openingTags(src(f), 'TimeChart');
      expect(tags.length, f).toBeGreaterThan(1);
      expect(tags[0]!.includes('hideTimeAxis'), `${f} 첫 차트가 x축을 진다`).toBe(false);
      tags.slice(1).forEach((t, i) => {
        expect(t.includes('hideTimeAxis'), `${f} 차트 ${i + 2} 는 축을 숨긴다`).toBe(true);
      });
    }
  });

  it('십자선은 형제 차트에 동기된다(syncIndex)', () => {
    for (const f of WINDOWS) {
      expect(src(f), f).toMatch(/syncIndex=\{idx && idx\.chart !== '/);
    }
  });

  it('캔버스가 못 하는 말을 hoverLabel 이 한다 — 차트마다', () => {
    /* CLAUDE.md 규칙 7: «읽을 DOM 이 없다 → hoverLabel → aria-live 줄이 진다».
       Main 미리보기 `scrubLabel` 이 그 판례다. */
    for (const f of WINDOWS) {
      const code = src(f);
      const charts = code.split('<TimeChart').length - 1;
      const labels = code.split('hoverLabel=').length - 1;
      expect(labels, f).toBe(charts);
    }
  });

  it('차트 높이는 Backtest 의 두 급(200/140)이다', () => {
    for (const f of WINDOWS) {
      const code = src(f);
      expect(code, f).toMatch(/const CHART_H = 200;/);
      expect(code, f).toMatch(/const CHART_H_SUB = 140;/);
    }
  });
});

describe('일별 대사는 창 바닥 서랍이다', () => {
  it('전략 실험 창이 FloatingWindow 의 drawer 로 대사를 낸다', () => {
    const code = src('src/mr/StrategyWindow.tsx');
    expect(code).toMatch(/drawer=\{\[/);
    expect(code).toMatch(/label: '일별 대사'/);
    /* 왜 비었는지를 그 자리에서 말한다(서랍의 규율). */
    expect(code).toMatch(/unavailable:/);
  });

  it('거래 줄을 누르면 서랍이 펴진다 — 「눌렀는데 아무 일도」가 없게', () => {
    const code = src('src/mr/StrategyWindow.tsx');
    expect(code).toMatch(/setOpenTrade\(tradeKey\(t\)\);\s*setDrawerOpen\(true\);/);
    /* 실행하면 닫는다 — 딴 실행의 대사를 펴 놓고 있으면 그 표가 거짓이다. */
    expect(code).toMatch(/setOpenTrade\(null\);\s*setDrawerOpen\(false\);/);
  });

  it('서랍 펼침은 제어 prop 으로 지나간다 — 부품을 복제하지 않았다', () => {
    /* `WindowDrawer` 는 기본이 «자기 상태»다(백테스트 판). 밖에서 쥐는 판만
       옵셔널로 더했다 — 두 벌을 만들면 서랍이 둘이 된다(얼라인 8). */
    const drawer = src('src/ui/window/WindowDrawer.tsx');
    expect(drawer).toMatch(/open\?: boolean/);
    expect(drawer).toMatch(/onOpenChange\?: \(open: boolean\) => void/);
    expect(drawer).toMatch(/const open = openProp \?\? openSelf/);
    const fw = src('src/ui/window/FloatingWindow.tsx');
    expect(fw).toMatch(/drawerOpen\?: boolean/);
  });
});

describe('칸 폭은 실측이고 죽은 폭이 없다', () => {
  /* 얼라인 7 의 「컨트롤은 제 상자를 채운다」 판. 브라우저 실측(2026-09-02):
     상자 사이 빈틈은 6px(묶음 안)·24px(묶음 사이)로 Backtest 와 같은 문법인데,
     상자 안 **죽은 폭**이 0~27.8px 로 흩어져 «보이는» 간격이 제각각이었다.
     비용 칸은 반대로 −15.3px, 즉 상자보다 내용이 넓어 이웃 칸(명목)을 침범했다.
     실측값으로 조인 뒤 죽은 폭이 0~1.2px 로 수렴했다 — σ 셋도 `SIGMA_W` 은퇴로
     예외가 아니게 됐다(아래 그 시험). */
  const knob = src('src/mr/KnobBar.tsx');
  const knobRaw = fs.readFileSync(path.join(root, 'src/mr/KnobBar.tsx'), 'utf8');

  it('세그먼트는 제 상자를 채운다 — 폭을 손으로 맞추는 대신 구조로', () => {
    /* CDS Tabs 기본은 fit-content 라 상자와 컨트롤 사이에 죽은 폭이 남는다.
       `fill`(→ equalWidth)이 그것을 0 으로 만든다 — 얼라인 7 이 Select 에
       DROPDOWN_STYLES 로 막아 둔 그 실패의 세그먼트 판(실측 2026-09-02:
       5.1~27.8px → 0). Backtest 방향 칸은 고정폭 상자가 아니라 켜지 않는다. */
    const cc = src('src/ui/ControlCard.tsx');
    expect(cc).toContain('equalWidth={fill}');
    /* MR 에 남은 세그먼트는 **진입 규칙 하나**다 — 실전 규칙 다섯은
       2026-09-02 에 화면에서 내렸다(아래 시험). 남은 것은 채운다. */
    expect((knob.match(/<Segmented\s+fill/g) || []).length).toBe(1);
    /* Backtest 방향 칸은 자기 줄에 살아서 켜면 줄 전체로 늘어난다 — 안 켠다. */
    expect(src('src/backtest/BacktestWindow.tsx')).not.toMatch(/<Segmented\s+fill/);
  });

  it('실전 규칙 다섯은 화면에 없다 — 내린 근거가 주석에 남아 있다', () => {
    /* [OWNER 2026-09-02 — "실전 규칙 다섯은 일단 없애서 기억만 해두는 걸로"].
       긴 표본에서 기각된 노브다(§긴 표본 판정 ①). **엔진은 그대로**이므로
       계약과 기본값은 살아 있어야 하고, 화면에서 고르는 손잡이만 없다. */
    for (const label of ['타임스탑 (일)', '레짐 필터', '비용 모델', '역신호 청산', '미청산 계상']) {
      expect(knob, label).not.toContain(`label="${label}"`);
    }
    /* 되살릴 자리와 이유가 주석에 있다. */
    expect(knobRaw).toMatch(/화면에서 내렸다/);
    expect(knobRaw).toMatch(/엔진은 그대로다/);
    /* 계약·기본값은 안 건드렸다 — 서버가 받는 노브는 그대로다. */
    const api = src('src/mr/api.ts');
    for (const k of ['timeStop', 'regime', 'costModel', 'reverseExit', 'countOpen']) {
      expect(api, k).toMatch(new RegExp(`${k}:`));
    }
  });

  it('비용 칸은 알약 셋 + 자유 입력을 담고, 프리셋이 갈리면 폭도 따라간다', () => {
    /* 2026-09-04 에 프리셋이 0.05/0.2/0.5 → 0.25/0.5/1 로 갈렸고(오너 지시),
       그때는 옛 실측(219.3)에서 **유도한** 212 를 썼다. 2026-09-07 에 브라우저
       에서 실제로 쟀더니 차지하는 폭이 204.78 이라 212 는 7.22px 을 남기고
       있었다 — 이 줄의 다른 칸(룩백 0.98 · 진입 σ 0.56)과 유일하게 어긋난
       칸이었다. 그래서 205 다.

       유도가 틀렸다는 게 아니라 **유도로 멈추면 안 된다**는 것이 이 시험의
       뜻이다(CLAUDE.md 얼라인 6). */
    expect(knob).toContain('<Box width={205}>');
    expect(knob).toContain('MR_COST_PRESETS');
    /* 정정 이력을 지우지 않는다 — 옛 실측과 그 사이의 유도가 주석에 남아야
       되돌릴 때 같은 자리를 다시 밟지 않는다. */
    expect(knobRaw).toMatch(/219\.3px/);
    expect(knobRaw).toMatch(/폭 205 = 실측/);
    /* 실측이면 **잰 수가 적혀 있어야 한다.** 「실측」이라는 낱말만 있고 수가
       없으면 그것은 선언이지 실측이 아니다. */
    expect(knobRaw).toMatch(/204\.78/);
  });

  it('프리셋 목록은 화면이 아니라 계약이 진다 — 0.25 / 0.5 / 1', () => {
    /* 값이 KnobBar 에 손으로 적혀 있으면 서버 검증·다른 창과 갈린다. */
    const api = src('src/mr/api.ts');
    expect(api).toMatch(/MR_COST_PRESETS = \[0\.25, 0\.5, 1\]/);
    /* 0.05 는 «화면이 안 권할» 뿐 사라진 값이 아니다 — 자유 입력이 남고,
       그 사실이 주석에 있다. */
    const apiRaw = fs.readFileSync(path.join(root, 'src/mr/api.ts'), 'utf8');
    expect(apiRaw).toMatch(/자유 입력에 적으면 된다/);
  });

  it('σ 칸은 **각자 제 내용 폭**이다 — 공통 폭 상수는 은퇴했다', () => {
    /* [OWNER 2026-09-02 — "칸안에서 빈 부분 축약해서 깔끔하게"]. 종전에는 셋이
       `SIGMA_W` 하나를 공유해 죽은 폭 11.7·9.2px 를 남겼다(알약 라벨의 자릿수가
       「1.5」와 「0」으로 달라서다). 실측 잉크 127.4·116.3·118.8 → 128·117·120. */
    expect(knob).not.toContain('SIGMA_W');
    for (const w of ['128', '117', '120']) {
      expect(knob, `σ width ${w}`).toContain(`width={${w}}`);
    }
  });

  it('폭 선언 **하나하나**에 근거가 붙어 있다 — 말줄임 금지 §3', () => {
    /* 종전에는 파일 전체에서 「실측」·날짜를 찾았다 — 그 낱말이 머리 주석에만
       있어도 통과라, 근거 없이 폭을 바꿔도 영원히 초록이었다(2026-09-02 검사).
       이제 선언마다 **바로 앞 40줄** 안에 그 수나 「실측」이 든 주석이 있는지 본다. */
    const lines = knobRaw.split(String.fromCharCode(10));
    const offenders: string[] = [];
    lines.forEach((ln, i) => {
      const m = /<Box width=\{(\d+)\}/.exec(ln);
      if (!m) return;
      const before = lines.slice(Math.max(0, i - 40), i).join(String.fromCharCode(10));
      if (!before.includes(m[1]!) && !before.includes('실측')) offenders.push(`${i + 1}: width ${m[1]}`);
    });
    expect(offenders).toEqual([]);
  });

  it('주석이 적은 폭과 코드의 폭이 같다 — 선언이 거짓이면 되돌릴 때 재발한다', () => {
    /* 실제로 한 번 갈렸다: 주석 「폭 212 = 실측」 대 코드 `<Box width={220}>`
       (2026-09-02 검사). 212 는 실측 잉크 219.3 을 못 담아, 그 수를 믿고
       되돌리면 이웃 칸 침범이 그대로 재발한다. */
    /* 「= 실측」과 「= 유도」 둘 다 잰다. 2026-09-04 에 비용 칸이 유도값이
       됐는데(프리셋이 갈려 옛 실측을 못 쓴다), 실측만 재면 그 칸의 선언과
       코드가 갈려도 이 시험이 아무 말도 안 하게 된다. */
    const rx = /폭 (\d+) = (?:실측|유도)/g;
    let m: RegExpExecArray | null;
    const bad: string[] = [];
    while ((m = rx.exec(knobRaw))) {
      const after = knobRaw.slice(m.index, m.index + 900);
      const box = /<Box width=\{(\d+)\}/.exec(after);
      if (!box || box[1] !== m[1]) bad.push(`주석 ${m[1]} vs 코드 ${box ? box[1] : '없음'}`);
    }
    expect(bad).toEqual([]);
  });
});

describe('가로 간격은 앱에 한 값이다 — 12px 동간격', () => {
  /* [OWNER 2026-09-02 — "가로 근접성 리듬 폐기하고 그냥 동간격으로 배치하기"].
     종전에는 묶음 안 6 · 묶음 사이 24(`.sr-fgroup`)로 덩어리를 만들었고, 조건
     바는 또 4/16 이라 리듬이 두 벌이었다. 어느 것이 정본인지 어느 파일도 말하지
     않았고, 상자 안 죽은 폭에 흔들려 선언(6/24)과 화면(여덟 가지)이 달랐다. */
  it('`.sr-fgroup` 은 앱 어디에도 안 쓰인다', () => {
    const files = ['src/backtest/BacktestWindow.tsx', 'src/mr/KnobBar.tsx', 'src/mr/MrPage.tsx',
      'src/rv/RvPage.tsx', 'src/sim/SimulationPage.tsx'];
    for (const f of files) {
      expect(src(f), f).not.toContain("className=\"sr-fgroup\"");
      expect(src(f), f).not.toContain("'sr-fgroup'");
    }
    /* CSS 규칙도 없다 — 은퇴 근거만 주석으로 남는다. */
    const css = fs.readFileSync(path.join(root, 'src/theme/type.css'), 'utf8');
    expect(css).not.toMatch(/^\.sr-fgroup \{/m);
    expect(css).toMatch(/`\.sr-fgroup` 은퇴/);
  });

  it('컨트롤 행은 어디서나 gap 1.5(12px)다', () => {
    const rows: [string, RegExp][] = [
      ['src/backtest/BacktestWindow.tsx', /<HStack gap=\{1\.5\} alignItems="flex-end" flexWrap="wrap">/],
      ['src/mr/KnobBar.tsx', /<HStack gap=\{1\.5\} alignItems="flex-end" flexWrap="wrap">/],
      ['src/mr/MrPage.tsx', /<HStack gap=\{1\.5\} alignItems="center" flexWrap="wrap">/],
      ['src/rv/RvPage.tsx', /<HStack gap=\{1\.5\} alignItems="center" flexWrap="wrap">/],
      ['src/sim/SimulationPage.tsx', /<HStack gap=\{1\.5\} alignItems="flex-end"/],
    ];
    for (const [f, re] of rows) expect(src(f), f).toMatch(re);
  });
});

describe('서랍은 남는 높이를 받고, 몸통이 양보한다', () => {
  /* [OWNER 2026-09-02 — "일별대사에서 왜 밑에 좌우로 드래그 할 수 있는 홀더
     같은게 없어?"]. 바는 있었고 **화면 밖에 있었다** — 표 상자에 박아 둔
     `maxHeight: 30vh`(256px)가 서랍이 실제로 준 높이(173px)보다 커서, 가로 바가
     달린 바닥 모서리가 창 밖으로 나갔다. `.sr-drawer-body` 의 주석이 그 실패를
     이미 경고하고 있었다(«안 줄면 스크롤러가 둘이 되고…»). */
  it('대사 상자는 높이를 박지 않고 받는다', () => {
    const code = src('src/mr/StrategyWindow.tsx');
    expect(code).toContain('className="sr-mr-drawertable"');
    expect(code).not.toMatch(/maxHeight: '30vh'/);
    const css = fs.readFileSync(path.join(root, 'src/theme/type.css'), 'utf8');
    const block = css.slice(css.indexOf('.sr-mr-drawertable {'), css.indexOf('.sr-mr-drawertable >'));
    expect(block).toContain('flex: 1 1 auto');
    /* 스크롤은 CDS 가 두른 컨테이너 하나가 진다(자식 선택자 — 해시 클래스는
       빌드마다 바뀐다). */
    expect(css).toMatch(/\.sr-mr-drawertable > div \{\s*max-height: 100%;/);
  });

  it('먼저 주는 쪽은 몸통이다 — 비율로 가르고, 서랍도 0 은 아니다', () => {
    /* 2026-09-02 감사가 잡은 자리다. 종전엔 서랍이 `flex-shrink: 0` 이라
       **아무도 안 무는 부족분**이 생겼다: 창을 화면 아래로 끌면 상한이
       서랍(38vh)+머리+탭 보다 작아지고, 몸통이 0 이 된 뒤에는 물 쪽이 없어
       창이 화면 밖으로 자랐다(실측: 창 하단 948 · 화면 911 — 37px 밖).
       그래서 0 이 아니라 **비율**이다 — 몸통 12 대 서랍 1. */
    const css = fs.readFileSync(path.join(root, 'src/theme/type.css'), 'utf8');
    const drawer = css.slice(css.indexOf('.sr-drawer {'), css.indexOf('.sr-drawer-tabs'));
    expect(drawer).toMatch(/flex-shrink: 1;/);
    const body = css.slice(css.indexOf('.sr-window-body {'), css.indexOf('.sr-drawer {'));
    expect(body).toMatch(/flex: 0 12 auto;/);
  });
});

describe('몸통에서 내린 절 — 답이 끝난 질문은 화면에 안 세운다', () => {
  /* [OWNER 2026-09-02 — 몸통 1,940px 에서 내릴 절을 고른 그 선택: 진단 135px ·
     이웃 칸 260px]. 실전 규칙 다섯과 같은 규율이다 — 화면에서만 내리고 서버·
     계약은 그대로 둔다. */
  const code = src('src/mr/StrategyWindow.tsx');

  it('진단·이웃 칸 컴포넌트가 없다', () => {
    expect(code).not.toContain('function Diagnostics');
    expect(code).not.toContain('function Sensitivity');
    expect(code).not.toContain('<Diagnostics');
    expect(code).not.toContain('<Sensitivity');
  });

  it('서버 계약은 살아 있다 — 측정을 끈 것이 아니다', () => {
    const api = src('src/mr/api.ts');
    expect(api).toMatch(/diag:/);
    expect(api).toMatch(/neighbors:/);
    const py = fs.readFileSync(path.join(root, 'backend/app/main.py'), 'utf8');
    expect(py).toMatch(/"diag":/);
    expect(py).toMatch(/"neighbors":/);
  });

  it('내린 이유가 주석에 남아 있다', () => {
    const raw = fs.readFileSync(path.join(root, 'src/mr/StrategyWindow.tsx'), 'utf8');
    expect(raw).toMatch(/화면에서 내렸다/);
    expect(raw).toMatch(/서버는 그대로다/);
  });
});

describe('머리 주석이 화면과 같은 말을 한다', () => {
  it('차트 라이브러리를 CDS CartesianChart 라고 적지 않는다', () => {
    /* 15차트가 lightweight-charts 로 옮겨 간 뒤(CLAUDE.md 규칙 7) 그 문장은
       거짓이다 — 이 리포는 «판단은 그 파일의 머리 주석이 한다» 라서 거짓
       주석은 그 자체로 결함이다(2026-09-02 감사가 잡았다). */
    for (const f of ['src/mr/StrategyWindow.tsx', 'src/mr/BandChart.tsx']) {
      const head = fs.readFileSync(path.join(root, f), 'utf8').slice(0, 4000);
      expect(head, f).not.toMatch(/차트는 lightweight-charts 가 아니라 CDS/);
      expect(head, f).not.toMatch(/같은 기계다: CDS `CartesianChart`/);
    }
  });

  it('배치를 2×2 라고 주장하지 않는다 — 세로 스택이 정본이다', () => {
    for (const f of WINDOWS) {
      const raw = fs.readFileSync(path.join(root, f), 'utf8');
      expect(raw, f).not.toMatch(/2×2 패널 — 원본 결과 그리드의 배치/);
      expect(raw, f).not.toMatch(/flexBasis: 50%` 인데, 간격까지 더하면/);
    }
  });
});

describe('스프레드는 한 물건이 아니다 — 대사가 다리마다 선다', () => {
  /* [OWNER 2026-09-03 — "채권 KRD, bp, 손익과 IRS KRD, bp, 손익, 그리고 종합
     손익이 하루에 찍혀야 함"].

     종전 대사표는 하루가 한 줄이고 다리 레벨 셋이 «열» 이었다. 그런데 이건
     채권 매수 · IRS 페이라 **하루에 다리가 둘**이고, 다리마다 감도·Δ·손익이
     따로 있다 — 한 줄에 못 담는다. 그래서 백테스트·시뮬 대사표의 문법을
     가져왔다: 다리마다 세 줄(KRD·Δbp·손익)에 종합 한 줄.

     여기서 지키는 것은 «모양» 이 아니라 **누가 계산하나** 다. 다리 Δ 는 레벨의
     차이고 KRD 는 부호 규약이며 손익은 엔진의 곱셈이다 — 셋 다 화면에서 다시
     하면 화면과 엔진이 다른 수를 말할 자리가 생긴다(§16). 값이 실제로 닫히는지
     는 `backend/tests/test_mr_legrecon.py` 가 라우트를 타고 잰다. */

  it('화면이 다리 줄을 세운다 — 다리 하나면 종합 줄이 없다', () => {
    const code = src('src/mr/StrategyWindow.tsx');
    expect(code).toContain('function ReconDay');
    for (const label of ['KRD', 'Δbp', '손익']) expect(code).toContain(label);
    /* 다리가 하나인 계열은 백테스트와 글자 그대로 같은 3줄이다
       [OWNER 2026-09-03 — "한개면 그냥 백테스트와 동일한 형태로"]. */
    expect(code).toMatch(/const single = legs\.length === 1/);
    expect(code).toMatch(/if \(!single\)/);
  });

  it('화면은 다리 값을 **다시 계산하지 않는다** — 서버가 낸 것만 적는다', () => {
    const code = src('src/mr/StrategyWindow.tsx');
    const day = code.slice(code.indexOf('function ReconDay'), code.indexOf('/** 대사표 머리의 한 줄'));
    expect(day).toContain('g.krd');
    expect(day).toContain('g.mtm');
    expect(day).toContain('g.carry');
    /* 곱셈·뺄셈이 이 부품 안에 있으면 §16 위반이다. `p.hold * notional` 은
       다리가 아예 없는 봉(구 백엔드)의 감도라 예외로 남는다 — 그 자리는 종합
       줄 하나뿐이고, 다리 줄에서는 서버 값만 쓴다. */
    expect(day).not.toMatch(/g\.krd\s*\*/);
    expect(day).not.toMatch(/g\.lvl\s*-/);
  });

  it('계약이 항등을 말한다 — KRD 합 0 · 손익 합 = 평가', () => {
    /* **주석을 안 걷은 원문**을 본다 — `src()` 는 주석을 지우는데, 여기서
       지키려는 것이 정확히 「계약이 그 항등을 말로 적어 두었나」다. 타입만
       있으면 다음 사람이 부호를 자기 방향으로 읽는다(이 리포의 그 규율). */
    const api = fs.readFileSync(path.join(root, 'src/mr/api.ts'), 'utf8');
    expect(api).toMatch(/interface MrReconLeg/);
    expect(api).toMatch(/Σ krd = 0/);
    expect(api).toMatch(/Σ mtm = 평가/);
  });

  it('서버가 봉마다 그 항등을 재고, 안 맞으면 다리를 안 싣는다', () => {
    const py = fs.readFileSync(path.join(root, 'backend/app/main.py'), 'utf8');
    const fn = py.slice(py.indexOf('def _attach_leg_recon('), py.indexOf('@router.get("/api/mr/strategy")'));
    expect(fn).toMatch(/LEG_RECON_TOL_KRW/);
    /* 지어낸 분해를 화면에 올리지 않는다 — 안 맞으면 통째로 접는다. */
    expect(fn.match(/return$/gm)?.length ?? 0).toBeGreaterThanOrEqual(3);
    /* 롤일은 다리도 같이 0 이다 — 한쪽만 살리면 그 줄이 안 닫힌다. */
    expect(fn).toMatch(/p\.get\("roll"\)/);
  });

  it('화면이 읽는 사람에게 **지금** 규약을 말한다 — 옛 문장이 남아 있지 않다', () => {
    /* 2026-09-03 감사가 잡은 자리다. 표를 다리 줄로 바꿨는데 **설명 문장 둘이
       옛 규약을 그대로 말하고 있었다** — 「감도 × Δ = 평가」. 새 표에서는 줄마다
       `−KRD × Δ = 손익` 이고 다리 손익을 더해야 평가다. 부호까지 반대라, 그
       문장을 읽고 손으로 검산하면 안 맞는다.

       주석이 아니라 **화면에 서는 글자**라 더 무겁다. 코드에서 지운 규약이
       설명에 남아 있으면 그건 화면이 거짓말을 하는 것이다. */
    const code = src('src/mr/StrategyWindow.tsx');
    expect(code).not.toContain('감도 × Δ = 평가');
    expect(code).toContain('−KRD × Δ = 손익');
  });

  it('대사표가 곧 엔진의 장부다 — 줄이 검산이 된다', () => {
    /* [OWNER 2026-09-03 — "캐리 롤다운 다 넣고 우리가 원래 사용하던 백테스트/
       시뮬레이션에서의 대사와 동일하게 작성하기"].

       종전에는 둘이 다른 회계였다 — 엔진은 `평가 = 명목 × Δ스프레드` 하나뿐이라
       롤다운도 조달도 없었고, 실측에서 **안 세는 롤다운(789만원)이 세는 전부
       (688만원)보다 컸다.** 이제 진입·청산 시점만 엔진이 정하고 그 구간의 돈은
       이 표가 센다(`평가·캐리·롤다운·조달` + 전략의 비용). 실측 차 0.00원.

       그래서 이 줄은 «차이의 변명» 이 아니라 **검산**이다 — 표의 세로합에 비용을
       더하면 거래 손익이 나온다. 그 산술이 화면에서 더해져야 하므로 만원 단위
       반올림도 `splitKrw` 의 수법을 쓴다(`lib/krw.ts`). */
    const code = src('src/mr/StrategyWindow.tsx');
    expect(code).toContain('function bridgeText');
    expect(code).toMatch(/uTot \+ uCost/);
    expect(code).toMatch(/manUnits\(/);
    expect(code).toMatch(/fmtKrwFromMan\(/);
    for (const w of ['표 세로합', '거래 손익', '전략의 노브']) expect(code).toContain(w);
    /* 계약이 두 회계를 구분해 말한다 — 선물은 이 표가 없다. */
    const api = fs.readFileSync(path.join(root, 'src/mr/api.ts'), 'utf8');
    expect(api).toMatch(/real: boolean/);
    expect(api).toMatch(/rolldown\?: number/);
  });

  it('캐리도 다리마다 온다 — 엔진의 곱셈이 선형이라 합이 닫힌다', () => {
    const py = fs.readFileSync(path.join(root, 'backend/app/mrcarry.py'), 'utf8');
    expect(py).toMatch(/def carry_rates_by_leg\(/);
    expect(py).toMatch(/LEG_NAMES/);
    /* 선물 다리의 0 은 «모르는 값» 이 아니라 «0 이라고 아는 값» 이다. */
    expect(py).toMatch(/선물 다리는 \*\*0 이 아니라/);
  });
});

describe('결과를 못 바꾸는 노브는 화면에 안 선다 — 「관찰 σ」 은퇴', () => {
  /* [OWNER 2026-09-02 — "이건 뭔지 확인하고 필요없으면 치우기"]. `warnZ` 는
     이름이 「경보 문턱」이었는데 **경보하는 곳이 없었다**: z 그림에 점선 두
     줄을 긋는 것 말고 읽는 데가 없었고(마커·집계·상태 문장 어디에도 안 들어감),
     통합 장부 창에는 애초에 없어서 두 창이 갈려 있었다. 그런데도 쿼리·백엔드
     검증·응답 params 세 층을 타고 다녔다. 결정이 안 붙은 선은 눈금이 아니다. */
  const files = [
    'src/mr/api.ts',
    'src/mr/StrategyWindow.tsx',
    'src/mr/KnobBar.tsx',
    'src/mr/BookWindow.tsx',
  ];

  it('화면·계약 어디에도 warnZ 를 쓰는 코드가 없다', () => {
    for (const f of files) {
      const raw = fs.readFileSync(path.join(root, f), 'utf8');
      /* 주석의 은퇴 기록은 남긴다 — 코드에서만 없으면 된다. */
      const code = raw
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/^\s*\/\/.*$/gm, '');
      expect(code, f).not.toMatch(/warnZ/);
    }
  });

  it('백엔드 두 라우트도 그 값을 안 받는다', () => {
    const py = fs.readFileSync(path.join(root, 'backend/app/main.py'), 'utf8');
    const code = py.replace(/^\s*#.*$/gm, '');
    expect(code).not.toMatch(/warnZ/);
  });

  it('z 그림의 가로선은 0선과 진입 문턱뿐이다', () => {
    const raw = fs.readFileSync(path.join(root, 'src/mr/StrategyWindow.tsx'), 'utf8');
    const block = raw.slice(raw.indexOf('const zBands'), raw.indexOf('const eqHue'));
    expect(block).toContain('value: 0');
    expect(block).toContain('run.params.entryZ');
    expect(block).not.toContain('dash: true');
  });

  it('내린 이유가 주석에 남아 있다', () => {
    const raw = fs.readFileSync(path.join(root, 'src/mr/api.ts'), 'utf8');
    expect(raw).toMatch(/경보하는 곳이 없었고/);
  });
});

describe('롤일 Δ 는 손익이 아니다 — 마스크와 그 표식', () => {
  /* [OWNER 2026-09-02 — "롤일 Δ 를 0 으로 마스크"]. 선물·퓨처스왑의 값은 벤더
     내재수익률이라 수준은 옳지만, 계약이 갈리는 날의 차분은 앞 계약 마지막과
     뒷 계약 첫 값을 뺀 것이라 **아무도 실현하지 못한다**(실측: FUT 109건 중
     35건 >1bp, 최대 25.6bp/거래 · FSW-3Y 는 총손익 +1.75억이 −0.71억으로 뒤집힘).

     마스크는 손익만 건드리고 **수준·z·신호는 안 건드린다** — 그래서 「청산 −
     진입」과 Δ 가 갈린다. 그 어긋남을 화면이 결함으로 읽히게 두면 안 된다. */

  it('마스크가 붙은 거래·봉에 표식이 선다', () => {
    const code = src('src/mr/StrategyWindow.tsx');
    expect(code).toContain('function RollMark');
    /* 거래 표 Δ · 대사표 합계 Δ · 롤 봉의 Δ 셋 다. */
    expect(code.match(/<RollMark /g)?.length ?? 0).toBeGreaterThanOrEqual(3);
    expect(code).toMatch(/t\.masked \?/);
    expect(code).toMatch(/sel\.masked \?/);
    expect(code).toMatch(/p\.roll \?/);
  });

  it('계약에 masked·roll 이 있고 뜻이 주석에 적혀 있다', () => {
    const api = fs.readFileSync(path.join(root, 'src/mr/api.ts'), 'utf8');
    expect(api).toMatch(/masked\?: number;/);
    expect(api).toMatch(/roll\?: boolean;/);
    expect(api).toMatch(/실현하지 못한다/);
  });

  it('엔진은 마스크를 안 주면 예전 산술 그대로다', () => {
    const py = fs.readFileSync(path.join(root, 'backend/app/mrbacktest.py'), 'utf8');
    expect(py).toContain('tradable_dv: list[float] | None = None');
    /* 기본 경로가 값의 차분이라는 사실 — 적합성 벡터가 그것을 잰다. */
    expect(py).toMatch(/if tradable_dv is None else list\(tradable_dv\)/);
    expect(py).toContain('position * notional * dv_bar[i]');
  });

  it('롤일은 달력이 정한다 — 가격 탐지는 자료가 비어 못 잡는 날이 있다', () => {
    const py = fs.readFileSync(path.join(root, 'backend/app/futures.py'), 'utf8');
    expect(py).toContain('def roll_days(');
    expect(py).toMatch(/셋째 화요일/);
    /* 마스크를 거는 쪽은 선물 가족뿐이다 — BSS 는 상수만기라 롤이 없다. */
    const main = fs.readFileSync(path.join(root, 'backend/app/main.py'), 'utf8');
    expect(main).toMatch(/if kinds\[id\] in \("fut", "fsw"\):/);
  });
});

describe('퓨처스왑 대사는 두 화면에서 한 모양이다 — 하루 일곱 줄', () => {
  /* [OWNER 2026-09-07 — "통일한다"]. 2026-09-04 에 Backtest 만 7행으로 갔고 MR
     창은 두 블록(선물 달력 + IRS 달력)으로 남아 있었다. 화면 둘이 같은 상품을
     다른 모양으로 그리는 상태였고, 이 절이 그것이 다시 갈라지는 것을 막는다.

     ⚠ 이 가드가 재는 것은 **모양의 출처**다. 돈이 두 길에서 같은지는 파이썬이
     잰다(`test_the_two_paths_are_the_same_money`) — 여기서 잴 수 없는 사실이다. */

  it('MR 창이 백테스트의 선물 각주를 **임포트**한다 — 옮겨 적지 않았다', () => {
    /* 캐논 규칙 1: 「참고한다」= 그 함수를 임포트한다. 문장을 복사하면 한쪽만
       낡고, 그게 바로 2026-09-04 에 각주가 자기 표의 열을 「없다」고 말한 자리다. */
    const code = src('src/mr/StrategyWindow.tsx');
    expect(code).toMatch(/import \{[^}]*futuresReconNote[^}]*\} from '@\/backtest\/recon'/);
    expect(code).toMatch(/b\.name \? futuresReconNote\(b\)/);
    /* 각주 문장 자체는 한 곳에만 산다. */
    const mine = code.match(/하루가 일곱 줄|하루 일곱 줄/g)?.length ?? 0;
    expect(mine, 'MR 창이 각주 문장을 자기 안에 다시 적었다').toBe(0);
  });

  it('IRS 다리가 있는지는 다리 목록이 정한다 — 블록 수가 아니다', () => {
    /* `blocks.length > 1` 은 FSW 가 한 표가 된 뒤로 늘 거짓이다. 그 식을 남겨
       두면 화면이 자기 표에 서 있는 캐리·롤다운 열을 「없다」고 말한다. */
    const code = src('src/mr/StrategyWindow.tsx');
    expect(code).toMatch(/legTenors\?\.length \?\? 0\) > 1/);
    expect(code, '블록 수로 다리를 판정하는 식이 남아 있다')
      .not.toMatch(/r\.blocks\.length > 1 \?/);
    /* 이름표도 마찬가지 — 「IRS 달력」 표는 이제 없다. */
    expect(code).not.toMatch(/b\.name === 'IRS'/);
  });

  it('서버가 다리를 화면에만 켠다 — 회계는 두 블록 그대로', () => {
    /* 다리 표는 IRS 파 커브를 범프해야 서는데(`with_krd=True` 가 박혀 있다)
       회계는 거래마다 돈다. 모양이 갈리는 자리라 **열쇠에 든다.** */
    const main = fs.readFileSync(path.join(root, 'backend/app/main.py'), 'utf8');
    expect(main).toMatch(/with_krd=True, with_legs=True/);
    expect(main).toMatch(/entry, exit_, with_krd, with_legs\)/);
    /* 빈 `legTenors` 를 실으면 화면이 다리 판으로 들어가 열을 못 세운다. */
    expect(main).toMatch(/if b\["recon"\]\.get\("legTenors"\) else \{\}/);
  });
});

describe('이 칸의 이름은 Delta 다 — 화면 어디에서도', () => {
  /* [OWNER 2026-09-04 — "Strategy에서 명목이 아니라 Delta라고 하기"].
     낱말 바꾸기가 아니다: 이 칸의 단위는 `₩/bp`(DV01)인데 「명목」은 채권·스왑에서
     **액면**을 가리키는 말이라, 바로 옆에 선 「액면 약 35.0억」과 충돌한다.

     ⚠ 이 가드가 있는 이유는 **한 번 놓쳤기 때문**이다. 09-04 에 노브와 카드만
     바꿨고 거래 표 부제·창 각주·서랍 머리·통합 장부 창 넷이 남아, 화면이 같은
     노브를 두 이름으로 불렀다(브라우저 실측 2026-09-07). 사람 눈이 마지막
     가드였고 그건 너무 늦은 가드다. */

  const WINDOWS = ['src/mr/StrategyWindow.tsx', 'src/mr/KnobBar.tsx', 'src/mr/BookWindow.tsx'];

  it.each(WINDOWS)('%s 의 화면 문자열에 「명목」이 없다', (f) => {
    /* 주석은 판단 대상이 아니다 — 이름이 바뀐 **경위**를 적은 자리가 있고,
       그것까지 지우면 다음 사람이 왜 Delta 인지를 못 찾는다. */
    const code = src(f);
    const bad = code.split('\n')
      .map((line, i) => ({ line, n: i + 1 }))
      .filter(({ line }) => /명목/.test(line));
    expect(bad.map((b) => `${b.n}: ${b.line.trim()}`), `${f} 에 화면 「명목」이 남았다`)
      .toEqual([]);
  });

  it('Delta 는 ₩/bp 라는 사실이 노브에 적혀 있다', () => {
    const knob = fs.readFileSync(path.join(root, 'src/mr/KnobBar.tsx'), 'utf8');
    expect(knob).toMatch(/Delta \(원\/bp\)/);
    /* 왜 「명목」이 아닌지 — 근거가 코드 옆에 있어야 되돌리지 않는다. */
    expect(knob).toMatch(/액면/);
  });
});

describe('소스 표기는 화면에 안 샌다 — 주석의 문법과 문장의 문법은 다르다', () => {
  /* [실측 2026-09-07, 브라우저에서]. 이 리포의 주석은 `**강조**` · `«인용»` ·
     `[OWNER 날짜]` 를 쓴다. 그 표기가 **렌더되는 문자열**에 들어가면 화면에
     별표와 꺾쇠가 그대로 찍힌다 — 실제로 찍혀 있었다:

       「액면은 **거래마다 진입일 커브**로 환산해요」   (전략 실험 창 각주)

     주석이라 눈에 안 띄었고, 시험은 주석을 걷고 보므로 잡을 수도 없었다.
     `src()` 가 주석을 걷은 **뒤에** 이 표기가 남아 있으면 그건 문장 안이다.

     화면의 강조는 「」 다(이 리포의 렌더 텍스트가 이미 쓰는 것). 별표는 없다. */

  const FILES = [
    'src/mr/BookWindow.tsx', 'src/mr/StrategyWindow.tsx', 'src/mr/OptimizePane.tsx',
    'src/mr/parts.tsx', 'src/mr/KnobBar.tsx', 'src/mr/api.ts',
  ];

  it.each(FILES)('%s — 주석을 걷고 나면 소스 표기가 없다', (f) => {
    const code = src(f);
    const bad: string[] = [];
    code.split('\n').forEach((line, i) => {
      for (const [what, rx] of [
        ['별표 강조', /\*\*[^*\n]+\*\*/],
        ['꺾쇠 인용', /«[^»\n]*»/],
        ['오너 표기', /\[OWNER/],
      ] as const) {
        if (rx.test(line)) bad.push(`${i + 1} (${what}): ${line.trim().slice(0, 90)}`);
      }
    });
    expect(bad, `${f} 의 문장에 소스 표기가 남았다`).toEqual([]);
  });
});

/* ── 2026-09-09 피드백 여섯 중 넷 [OWNER] ────────────────────────────────────
 *
 * 「미청산도 PnL에 포함」·「1순위를 바로 띄우기」·「누적을 롤다운·캐리로 분해」·
 * 「체결비용이 델타에 반영」. 넷 다 **한 벌로만** 서야 하고, 그 규율이 화면에서
 * 지켜지는지는 눈이 아니라 이 파일이 잰다.
 */
describe('미청산은 거래 표의 줄이다 — 승률은 안 건드린다', () => {
  const win = () => src('src/mr/StrategyWindow.tsx');

  it('미청산 줄은 한 함수가 만든다 — 표·차트·서랍이 같은 것을 읽는다', () => {
    const code = win();
    expect(code).toMatch(/function openAsTrade\(run: MrStrategyRun\)/);
    /* 세 자리가 다 그 함수를 부른다: 표(shownTrades)·차트 사건(events)·서랍(sel).
       한 자리라도 손으로 다시 만들면 열쇠가 갈려 줄을 눌러도 딴 것이 굵어진다. */
    expect(code.match(/openAsTrade\(run\)/g)?.length ?? 0).toBeGreaterThanOrEqual(4);
  });

  it('`countOpen` 이 켜져 있으면 줄을 안 더한다 — 두 번 세지 않는다', () => {
    expect(win()).toMatch(/if \(!o \|\| run\.params\.countOpen\) return null;/);
  });

  it('구 백엔드에서는 줄을 안 세운다 — 없는 값을 0 으로 그리지 않는다', () => {
    const code = win();
    expect(code).toMatch(/o\.exitT == null \|\| o\.exitV == null \|\| o\.dv == null/);
    expect(code).toMatch(/o\.mtm == null \|\| o\.carry == null \|\| o\.cost == null/);
  });

  it('통합 장부도 같은 규율이다 — 미청산이 모은 거래에 진입일 순으로 선다', () => {
    const code = src('src/mr/BookWindow.tsx');
    expect(code).toMatch(/function bookRows\(run: MrBookRun\): MrBookTrade\[\]/);
    expect(code).toMatch(/run\.params\.countOpen/);
    expect(code).toMatch(/bookRows\(run\)\.map/);
  });
});

describe('1순위를 바로 띄운다 — rv 히어로의 문법으로', () => {
  const page = () => src('src/mr/MrPage.tsx');

  it('히어로가 rv 의 부품·활자를 쓴다', () => {
    const code = page();
    expect(code).toMatch(/지금 모니터링할 테너예요/);
    expect(code).toMatch(/className="sr-rv-linkbtn"/);
    expect(code).toMatch(/font="display3"/);
  });

  it('히어로는 **1위**를 세운다 — 고른 줄이 아니다', () => {
    /* 표의 선택(`sel`)을 세우면 줄을 누를 때마다 히어로가 따라 움직여서
       「지금 무엇을 볼까」의 답이 아니라 선택의 메아리가 된다. */
    expect(page()).toMatch(/\{rows\[0\] \?/);
  });

  it('트리거는 서버가 끝낸 값이다 — 화면이 밴드를 다시 계산하지 않는다', () => {
    const code = page();
    expect(code).toMatch(/r\.triggers \?\? \[\]/);
    /* 레벨·거리를 화면에서 만들면 §16 이 깨지고 보드와 다른 수가 선다. */
    expect(code).not.toMatch(/upper - |ma \+ |sd \*/);
  });

  it('트리거가 무엇인지 화면이 말한다 — 명구 의무와 한 몸', () => {
    const code = page();
    expect(code).toMatch(/트리거는 위에서 고른 밴드/);
    expect(code).toMatch(/명목·손절·목표는 안/);
    /* 창설부터 지고 있는 명구는 그대로 산다. */
    expect(code).toMatch(/투자판단이 아니에요/);
  });
});

describe('누적 분해와 순Δ는 서버가 끝낸다', () => {
  it('분해 카드는 앱에 한 벌이고 두 창이 그것을 세운다', () => {
    expect(src('src/mr/parts.tsx')).toMatch(/export function SplitColumn/);
    for (const f of ['src/mr/StrategyWindow.tsx', 'src/mr/BookWindow.tsx']) {
      expect(src(f), `${f} 가 공용 분해 카드를 안 쓴다`).toMatch(/<SplitColumn split=\{perf\.split\}/);
    }
  });

  it('분해는 **구간을 따라간다** — 전체 기간 값을 구간 카드 옆에 안 세운다', () => {
    /* `perf` 는 구간 카드다(`spans`). `run.summary.split` 을 세우면 옆 칸들과
       다른 구간의 수가 한 줄에 선다. */
    for (const f of ['src/mr/StrategyWindow.tsx', 'src/mr/BookWindow.tsx']) {
      expect(src(f)).not.toMatch(/SplitColumn split=\{run\.summary\.split\}/);
    }
  });

  it('순Δ 는 서버 값을 그대로 적는다 — 화면이 비용을 bp 로 되돌리지 않는다', () => {
    const code = src('src/mr/StrategyWindow.tsx');
    expect(code).toMatch(/t\.dvNet == null \? '—' : fmtBp\(t\.dvNet, 2\)/);
    expect(code).not.toMatch(/t\.cost \/ /);
  });

  it('두 라우트가 같은 함수로 순Δ 를 낸다 — 두 표가 다른 수를 말하지 않게', () => {
    const main = fs.readFileSync(path.join(root, 'backend/app/main.py'), 'utf8');
    const book = fs.readFileSync(path.join(root, 'backend/app/mrbook.py'), 'utf8');
    expect(main).toMatch(/mrm\.dv_net\(/);
    expect(book).toMatch(/mrm\.dv_net\(/);
  });

  it('없는 성분은 0 이 아니라 빈칸이다 — 서버도 화면도', () => {
    const met = fs.readFileSync(path.join(root, 'backend/app/mrmetrics.py'), 'utf8');
    /* 일부 봉에만 있는 성분은 아예 안 싣는다(섞인 합은 성분이 아니다). */
    expect(met).toMatch(/len\(vals\) == len\(points\)/);
    expect(src('src/mr/parts.tsx')).toMatch(/v == null \? '—' : fmtKrw\(v\)/);
  });
});
