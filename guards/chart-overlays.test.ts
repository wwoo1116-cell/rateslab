import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * 이동평균 오버레이 [OWNER 2026-08-26 — "차트 회사들에서 제공하는 표준 MA로",
 * 그리고 "당연히 껏다 켰다 가능하게 … 색도 컬러토큰에서"].
 *
 * 재는 것은 다섯이고, 전부 **조용히** 틀리는 종류다:
 *
 *   ① 창을 화면이 정하지 않는다 — 서버(`derive.MA_WINDOWS`)가 유일한 목록이다.
 *      두 곳에 적으면 「MA120」이 서로 다른 수를 가리키는 날이 온다.
 *   ② MA 는 **점에 얹혀** 다닌다. 이 파일은 점 배열을 두 번 자르는데(구간 알약
 *      → 확대), MA 를 따로 들고 있으면 그 두 자르기를 두 번째 자리에서 흉내내야
 *      하고 언젠가 한쪽만 고쳐진다. 그러면 다른 날의 평균이 이 날 옆에 그려진다.
 *   ③ 색은 **CDS 시맨틱 토큰**에서만 온다. hex 를 박으면 다크에서 안 따라간다
 *      (실측 2026-08-26: accentBoldGray 가 light rgb(50,53,61) → dark
 *      rgb(193,198,207)). 이 제품에는 이미 뜻을 가진 색이 넷 있어(방향 둘·
 *      기준선 둘) 겹치는 선택지에는 경고를 단다 — 막지는 않는다.
 *   ④ 껏다 켰다 — 취향은 `state/overlays.ts` 한 곳이고 차트와 Setting 이 같이
 *      읽는다. MA 다섯과 **기준선 둘**이 같은 저장소·같은 칩 문법을 쓴다.
 *   ⑤ 색이 생겨도 잉크 위계는 남는다 — 주선이 주인공이다.
 */

const read = (p: string) => fs.readFileSync(path.join(__dirname, '..', p), 'utf8');
const pane = read('src/ui/PreviewPane.tsx');
const store = read('src/state/overlays.ts');
const derive = read('backend/app/derive.py');

/** 주석을 뺀 소스 — 이 리포의 주석에는 실측한 hex 가 **근거로** 적혀 있다. */
const codeOf = (src: string) =>
  src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');

describe('① 창은 서버가 정한다', () => {
  it('백엔드 목록은 벤더 표준이다 — 5·10·20·60·120', () => {
    expect(derive).toMatch(/MA_WINDOWS: tuple\[int, \.\.\.\] = \(5, 10, 20, 60, 120\)/);
  });

  it('프런트는 창 목록을 **자기가 적지 않는다**', () => {
    expect(pane).toMatch(/data\?\.maWindows \?\? \[\]/);
    /* 창 목록 자체가 프런트에 복제되지 않았는지. (굵기·불투명도 사다리에는
       숫자가 있어야 하므로 «숫자 금지» 로는 못 잰다 — 재는 것은 **목록**이다.) */
    expect(pane).not.toMatch(/\[\s*5\s*,\s*10\s*,\s*20\s*,\s*60\s*,\s*120\s*\]/);
  });
});

describe('② MA 는 점에 얹혀 잘린다', () => {
  it('로더가 응답의 ma 를 각 점에 붙인다', () => {
    expect(pane).toMatch(/points\[i\]\.ma = windows\.map/);
  });

  it('차트 시리즈는 **잘린 창의 점**에서 MA 를 읽는다 — 별도 배열이 아니라', () => {
    expect(pane).toMatch(/view\.win\.map\(\(pt\) => pt\.ma\?\.\[k\] \?\? null\)/);
  });

  it('MA 를 두 번째로 자르는 코드가 없다', () => {
    expect(pane).not.toMatch(/ma[A-Za-z]*\.slice\(-/);
    expect(pane).not.toMatch(/sliceRange\([^)]*ma/i);
  });

  it('워밍업 구간을 잇지 않는다 — 없던 평균을 직선으로 메우면 안 된다', () => {
    /* **재는 자리가 옮겨졌다** [2026-08-26 이관]: CDS 는 `connectNulls={false}`
       라는 손잡이가 있었고, 캔버스 판은 **`null` 을 whitespace 로 넣는 것**이
       그 일을 한다(값을 빼면 선이 이어져 없던 평균을 그린다). 규칙이 부품
       한 곳에 있으므로 거기서 잰다. */
    const time = fs.readFileSync(
      path.resolve(import.meta.dirname, '../src/chart/TimeChart.tsx'),
      'utf8',
    );
    expect(time).toMatch(/v == null \? \{ time: t as Time \} : \{ time: t as Time, value: v \}/);
    /* 그리고 MA 값은 서버가 준 `null` 을 그대로 들고 온다 — 0 으로 메우지 않는다. */
    expect(pane).toMatch(/pt\.ma\?\.\[k\] \?\? null/);
  });
});

describe('③ 색은 CDS 토큰에서만 온다 [OWNER 2026-08-26]', () => {
  it('고를 수 있는 색이 전부 CDS 시맨틱 토큰이다', () => {
    const list = store.slice(store.indexOf('MA_COLOR_TOKENS = ['), store.indexOf('] as const'));
    const tokens = [...list.matchAll(/'([A-Za-z]+)'/g)].map((m) => m[1]);
    expect(tokens.length).toBeGreaterThanOrEqual(5);
    for (const tk of tokens) expect(tk).toMatch(/^accent(Bold|Subtle)[A-Z]/);
  });

  it('저장소에도 화면에도 hex 가 없다 — 있으면 다크에서 안 따라간다', () => {
    expect(codeOf(store)).not.toMatch(/#[0-9a-fA-F]{3,8}/);
    expect(codeOf(read('src/ui/SettingView.tsx'))).not.toMatch(/#[0-9a-fA-F]{3,8}/);
  });

  it('차트는 토큰을 **변수 참조**로 넘긴다 — 이름 문자열로는 못 그린다', () => {
    expect(store).toMatch(/`var\(--color-\$\{t\}\)`/);
    /* 캔버스는 `var()` 조차 못 푼다 [2026-08-26 이관] — 그래서 그 변수 참조를
       `palette.dim` 이 그 자리에서 계산해 실제 색으로 바꾼다. 불투명도 사다리도
       거기서 함께 들어간다(캔버스에는 `strokeOpacity` 가 없다). */
    expect(pane).toMatch(/pal\.dim\(maColorVar\(maColorOf\(prefs, w\)\)/);
  });

  it('**기본으로 켜 두는 이동평균이 없다** [OWNER 2026-08-26]', () => {
    /* "기본값이라는게 없어야 함". 지표는 부르는 사람이 부를 때 뜬다 — 안 부른
       선이 차트에 있으면 그것도 데이터인 줄 읽는다. 그래서 이 시험은 «어느 창을
       켜 두는가» 가 아니라 «하나도 안 켠다» 를 잰다. */
    expect(store).toMatch(/shown: \[\],/);
  });

  it('꺼 둔 창도 **색은 배정돼 있다** — 켜는 순간 제 색으로 선다', () => {
    const from = store.indexOf('colors: {');
    const colors = store.slice(from, store.indexOf('};', from));
    for (const w of [5, 10, 20, 60, 120]) {
      expect(colors).toMatch(new RegExp(String(w) + ": 'accentBold[A-Za-z]+'"));
    }
  });

  it('겹치는 색에는 경고 문장이 붙는다 — 막지는 않는다', () => {
    const from = store.indexOf('MA_COLOR_WARNING');
    const warn = store.slice(from, store.indexOf('};', from));
    for (const tk of ['accentBoldRed', 'accentBoldBlue', 'accentBoldPurple', 'accentBoldYellow']) {
      expect(warn).toContain(tk);
    }
  });
});

describe('④ 껏다 켰다 [OWNER 2026-08-26]', () => {
  it('켠 창만 그린다 — 끈 창은 시리즈도 선도 안 만든다', () => {
    expect(pane).toMatch(/prefs\.shown\.includes\(w\)/);
  });

  it('켠 것을 거를 때도 **서버 목록의 첨자**를 쓴다', () => {
    /* `pt.ma` 가 서버 목록 순서라, 걸러진 배열의 첨자를 쓰면 다른 창의 평균을
       그린다. 그래서 순회는 `maWindows` 위에서 돌고 걸러내기만 안쪽에서 한다. */
    expect(pane).toMatch(/maWindows\.flatMap\(\(w, k\) =>/);
    expect(pane).not.toMatch(/maShown\.map\(\(w, k\)/);
  });

  it('범례가 손잡이다 — 켠 상태가 칸에 실린다', () => {
    /* **재는 자리가 옮겨졌다** [2026-09-21]: 그림 아래의 `Chip` 범례 줄이
       그림 **위**의 리드아웃 줄로 흡수됐다(떠 있던 카드가 그림을 가린다는
       트레이더 보고에서 나온 이동 — `ui/ChartReadoutStrip.tsx` 머리글).
       규칙은 그대로다: 켠 상태와 끄는 손잡이가 **그려진 것과 같은 자리**에
       있어야 둘이 갈리지 않는다. 이제 그 자리가 칩이 아니라 칸이다. */
    expect(pane).toMatch(/toggle: \{ on, onToggle: \(\) => ov\.toggle\(w\) \}/);
    expect(pane).not.toMatch(/invertColorScheme/);
  });

  it('끈 계열도 **칸은 남는다** — 좁은 창에서 켤 길이 없어지면 안 된다', () => {
    /* [OWNER 2026-09-21] 좁아질 때 내려놓는 것은 **값뿐**이다. 칸을 통째로
       떨구면 이 줄이 겸하는 범례가 같이 사라져, 좁은 창에서 그 계열을 켜고
       끌 수 없게 된다. CSS 가 값(`.sr-strip-v`)만 감춘다. */
    const css = read('src/theme/type.css');
    expect(css).toMatch(/\.sr-strip-slot\[data-drop='\d'\] \.sr-strip-v \{\s*display: none/);
    expect(css).not.toMatch(/\.sr-strip-slot\[data-drop='\d'\] \{\s*display: none/);
  });

  it('취향은 `state/overlays.ts` 한 곳이다 — Setting 과 차트가 같은 저장소를 읽는다', () => {
    expect(pane).toMatch(/useOverlayPrefs\(\)/);
    expect(read('src/ui/SettingView.tsx')).toMatch(/useOverlayPrefs\(\)/);
    expect(store).toMatch(/const KEY = 'sr-overlays'/);
  });

  it('리드아웃도 **켠 것만** 적는다 — 없는 선의 값을 읽지 않는다', () => {
    const from = pane.indexOf('const stripSlots = useMemo<StripSlot[]>');
    const block = pane.slice(from, pane.indexOf('return out;', from));
    expect(block).toMatch(/prefs\.shown\.includes\(w\)/);
    /* 값은 **서버 목록의 첨자**로 읽는다 — 켠 것만 거른 배열의 첨자를 쓰면
       다른 창의 평균을 적게 된다. 끈 창은 빈 글자이고 이름·견본만 남는다. */
    expect(block).toMatch(/stripPoint\.ma\?\.\[k\]/);
  });
});

describe('⑤ 잉크 위계는 색이 생겨도 남는다', () => {
  it('무게 사다리는 창이 길수록 무겁다', () => {
    /* 선언부가 아니라 **배열 리터럴**부터 잘라야 한다 — 타입 주석
       (`{ width: 1 | 2 }`)에도 `width: 1` 이 들어 있어 여섯 개로 세어진다
       (2026-08-26 실측). */
    const decl = pane.slice(pane.indexOf('const MA_INK: '), pane.indexOf('/** 시리즈 id'));
    const raw = decl.slice(decl.indexOf('['));
    const widths = [...raw.matchAll(/width: (\d)/g)].map((m) => Number(m[1]));
    const ops = [...raw.matchAll(/opacity: ([\d.]+)/g)].map((m) => Number(m[1]));
    expect(widths).toHaveLength(5);
    for (let i = 1; i < 5; i++) {
      expect(widths[i]).toBeGreaterThanOrEqual(widths[i - 1]);
      expect(ops[i]).toBeGreaterThan(ops[i - 1]);
    }
    /* 가장 무거운 MA 도 종목 선보다 가볍다 — 주선이 주인공이다.
       **굵기는 정수만 된다** [2026-08-26 이관]: 캔버스 라이브러리의 `lineWidth`
       가 1~4 라 CDS 의 소수 사다리(1·1·1.25·1.5·1.75)를 그대로 못 옮긴다.
       사다리의 뜻은 불투명도가 지고, 굵기는 종목 선과 **같아질 수는 있어도**
       불투명도로 뒤에 남는다. */
    expect(widths[4]).toBeLessThanOrEqual(2);
    expect(ops[4]).toBeLessThan(1);
  });

  it('스크러버는 MA 를 안 짚는다 — 값은 리드아웃이 진다', () => {
    /* 캔버스 판에는 «짚을 계열» 목록이 없다 — 크로스헤어는 자리를 주고 값은
       리드아웃 카드가 읽는다. 그래서 재는 것은 «MA 가 리드아웃의 주인공이
       아니다» 이고, 그건 리드아웃이 서버 첨자(`stripPoint.ma?.[k]`)로만 MA 를
       읽는 것으로 지켜진다. 구슬 쪽은 이제 손잡이가 생겼다 — 주선만
       `beacon: true` 다(`chart/series.ts::addLine`). */
    expect(pane).toMatch(/beacon: true,/);
    expect(pane).toMatch(/stripPoint\.ma\?\.\[k\]/);
  });

  it('종목 선이 MA **아래**가 아니다 — 잉크의 위계', () => {
    /* CDS(SVG)에서는 «나중에 적은 것이 위» 라 MA 를 먼저 적었다. 캔버스에서는
       **먼저 만든 계열이 아래**라 순서가 뒤집힌다: 주선을 먼저 적어야 MA 가
       그 위에 온다. 같은 규칙(주선이 MA 에 안 가린다)을 반대로 적는 자리라
       여기서 못 박는다 [2026-08-26 이관]. */
    const mainAt = pane.indexOf("id: row?.id ?? 'series'");
    const maAt = pane.indexOf('id: maSeriesId(w)');
    expect(mainAt).toBeGreaterThan(-1);
    expect(maAt).toBeGreaterThan(mainAt);
  });
});

describe('⑥ 기준선도 껏다 켰다 [OWNER 2026-08-26]', () => {
  it('있음과 그림이 갈려 있다 — `refs` 는 값이 있는가, `drawn` 은 켜져 있는가', () => {
    /* 없는 기준선은 **끌 수도 없어야** 한다(칩이 안 선다). 그래서 범례는 `refs`
       를 보고, 시리즈·스크러버·리드아웃·보조축은 `drawn` 을 본다. */
    expect(pane).toMatch(/const drawn = useMemo\(/);
    expect(pane).toMatch(/cd: prefs\.refs\.cd \? refs\.cd : null/);
    expect(pane).toMatch(/policy: prefs\.refs\.policy \? refs\.policy : null/);
  });

  it('그리는 자리는 전부 `drawn` 을 읽는다 — 하나라도 `refs` 면 끈 선이 남는다', () => {
    for (const re of [
      /id: CD_LINE,[\s\S]{0,30}values: drawn\.cd/,
      /id: BASE_LINE,[\s\S]{0,30}values: drawn\.policy/,
      /* 스크러버의 «짚을 계열» 목록은 캔버스 판에 없다 — 크로스헤어는 자리를
         주고 값은 리드아웃 줄이 읽는다. 그 줄도 `drawn` 을 지난다. */
      /value: drawn\?\.cd \? fmtLevel\(drawn\.cd\[i\], '%'\)/,
    ]) {
      expect(pane).toMatch(re);
    }
  });

  it('둘 다 끄면 보조 %축도 내려간다 — 빈 축은 폭만 먹고 아무 말도 안 한다', () => {
    expect(pane).toMatch(/const pctAxis = !!\(drawn && \(drawn\.cd \|\| drawn\.policy\)\)/);
  });

  it('칸은 **값이 있을 때만** 선다', () => {
    /* 없는 기준선은 끌 수도 없어야 한다. 칸이 서는가는 `refs`(값이 있는가)를
       보고, 값을 적는가는 `drawn`(켜져 있는가)을 본다 — 위 시험의 그 구별이
       리드아웃 줄에서도 그대로다. */
    const from = pane.indexOf('const stripSlots = useMemo<StripSlot[]>');
    const block = pane.slice(from, pane.indexOf('return out;', from));
    expect(block).toMatch(/if \(refs\?\.cd\) \{/);
    expect(block).toMatch(/if \(refs\?\.policy\) \{/);
  });

  it('기준선 색은 **고르는 대상이 아니다** — 저장소에 색 항목이 없다', () => {
    /* 두 색은 오너가 3차까지 보고 확정한 값이다(`direction.css`). MA 와 다른
       점이 그 하나이고, 저장소의 `refs` 가 boolean 둘인 것이 그 사실이다. */
    expect(store).toMatch(/refs: \{ cd: boolean; policy: boolean \}/);
    expect(store).not.toMatch(/refColors|refs:\s*\{[^}]*Token/);
  });
});
