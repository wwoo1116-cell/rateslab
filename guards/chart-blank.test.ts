/* 그림 자리의 **빈칸** — 0선 + 한 문장 [디자인 감사 2026-10-21 · 전개 2026-10-22].
 *
 * ## 왜 이 파일이 뒤늦게 생겼나
 *
 * `ChartBlank` 는 감사에서 들인 부품인데 **가드가 하나도 없었다.** 들인 날
 * 깔린 자리가 `MrPage` **한 곳**이었고, 나머지 그림 자리 열셋은 종전 문법
 * 그대로였다 — 그래서 같은 화면이 같은 상태를 두 문법으로 말하는 결함이
 * 그 한 곳만 고쳐진 채 남았다. 이 리포가 세 번 겪은 **「범위가 좁은 가드」**
 * 와 같은 꼴이고(`sauron-v2-design-audit` 의 그 뿌리), 이번엔 **규칙 쪽**을
 * 박는다.
 *
 * ## 규칙
 *
 * 그림이 설 자리가 비면 **아무 말 없이 비우지 않는다.** 셋 중 하나다:
 *   ① `ChartBlank`(0선 + 한 문장) — 기다리는 중이거나 그릴 것이 없을 때
 *   ② 부모가 이미 문장을 세운다 — 그 자리까지 안 온다
 *   ③ 그 자리는 **빌 수가 없다** — 서버가 빈 자료를 `raise` 로 막는다
 *
 * ③ 인 자리에 ①을 깔면 **죽은 코드**다. 2026-10-22 에 열넷을 전수로 보고
 * 넷만 고친 까닭이 그것이고, 아래 `NEVER_EMPTY` 가 그 판정을 적어 둔다 —
 * 다음 사람이 「여긴 왜 안 깔았지」로 다시 재지 않게.
 */

import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments } from './_source';

const ROOT = process.cwd();
const read = (rel: string) => stripComments(fs.readFileSync(path.join(ROOT, rel), 'utf8'));

/** `ChartBlank` 가 서 있어야 하는 자리와 **그 자리가 비는 조건**. */
const BLANK_SITES: Record<string, string> = {
  'src/ui/PreviewPane.tsx':
    '추이가 아직 없거나 고른 구간에 점이 없을 때. 종전에는 `<Box height={chartH} />` — ' +
    '아무 말 없는 흰 칸이었고, 이 pane 이 앱에서 제일 많이 서는 그림 자리다.',
  'src/rv/RvPage.tsx':
    '이력을 받는 중이거나 점이 둘보다 적을 때. 종전에는 맨 한 줄 캡션이었고 ' +
    '그 아래 밴드 차트 둘이 설 자리가 통째로 비었다.',
  'src/backtest/BacktestWindow.tsx':
    '점이 둘보다 적어 차트 한 쌍이 못 설 때. 종전에는 `null` 이라 그 블록이 ' +
    '**말없이 사라졌다** — 결과 블록과 포지션 표가 붙어서 「원래 그림이 없는 창」으로 읽힌다.',
  'src/mr/MrPage.tsx':
    '계열을 하나도 못 구웠거나 산출 중일 때. 감사가 처음 깐 자리(실측 공백 380px).',
  'src/lab/scenario/ModelChart.tsx':
    '만기 행이 비어 `head` 가 없을 때. 종전에는 `null` 이었는데, 호출부 ' +
    '(`StrategySurface`)는 `curveRows` 가 참인지만 보고 **빈 배열도 참**이라 거기서 안 걸린다.',
};

/** 그림 자리이지만 **빌 수가 없는** 곳과 그 근거. 여기에 `ChartBlank` 를
 *  깔면 죽은 코드다 — 근거가 깨지는 날 이 표를 고친다. */
const NEVER_EMPTY: Record<string, string> = {
  'src/flow/FlowPage.tsx':
    'backend `_cash_board`/`_fut_board` 가 `if not dates: raise` 로 빈 보드를 막는다. ' +
    '`win` 은 `got` 이 있을 때만 서고, slice 는 최소 한 봉을 남긴다. `?? []` 는 ' +
    '옛 서버 대비 방어일 뿐 빈 그림의 경로가 아니다.',
  'src/flow/IssuanceFace.tsx': '같은 보드를 읽는다 — 위와 같은 근거.',
  'src/flow/FlowLabWindow.tsx':
    'backend `flowlab` 이 `겹치는 날이 너무 적어요` 로 `raise` 한다 — 창이 err 를 세운다.',
  'src/mr/BandChart.tsx':
    '호출부(`RvPage`)가 `data.points.length < 2` 를 먼저 거른다 — 그 자리에 blank 가 선다.',
  'src/mr/BookWindow.tsx': '`run` 이 있으면 손익 곡선 점이 있다(거래 0 이어도 0 의 곡선).',
  'src/mr/StrategyWindow.tsx': '같은 근거 — `run.points` 는 비지 않는다.',
  'src/sim/CurvePreview.tsx': '기둥(`pillars`)은 고정 집합이라 비지 않는다.',
  'src/sim/ResultsWindow.tsx': '`paths` 가 없으면 그 블록 자체가 안 선다.',
  'src/rv/RvScatter.tsx': '사분면은 **제 축을 그린다** — 점이 0 이어도 흰 칸이 아니다.',
  'src/lab/model/model/BasisIrf.tsx':
    '`data.length > 1` 로 가린 것은 차트가 아니라 **범례**다. 계열 하나면 범례가 없는 게 맞다.',
  'src/backtest/LinkedCharts.tsx':
    '점이 둘보다 적으면 `null` 을 내는데, **호출부가 그 자리를 받는다** — ' +
    'BacktestWindow 의 그 자리가 위 `BLANK_SITES` 에 있다.',
};

describe('그림 자리가 비면 0선과 한 문장이 선다', () => {
  it('부품이 **한 곳**에 있고 0선을 긋는다', () => {
    const ds = read('src/ui/DataState.tsx');
    expect(ds, 'ChartBlank 가 사라졌어요').toMatch(/export function ChartBlank/);
    /* 0선은 CSS 가 긋는다 — 값을 말하지 않는 면 토큰이어야 한다. */
    const css = fs.readFileSync(path.join(ROOT, 'src/theme/type.css'), 'utf8');
    /* ⚠0선은 `.sr-chartblank` **자신**이 아니라 `::before` 가 긋는다(본체는
       `position: relative` 뿐이다). 첫 판이 본체 규칙만 보고 거짓 실패를 냈다 —
       **규칙 하나가 아니라 그 선택자 묶음 전체**를 봐야 한다. */
    const i = css.indexOf('.sr-chartblank::before');
    expect(i, '.sr-chartblank::before 가 없어요 — 0선을 누가 긋나요?').toBeGreaterThan(0);
    const rule = css.slice(i, css.indexOf('}', i));
    expect(rule, '0선이 안 그어져요').toMatch(/border-top/);
    expect(rule, '0선이 면 토큰이 아니에요 — 빈 자리가 자료처럼 보입니다')
      .toMatch(/--color-bgLine/);
    /* 눈금 숫자는 안 적는다 — 빈 자리가 값을 말하면 안 된다. */
    expect(ds, '빈 자리에 눈금 수가 들어왔어요').not.toMatch(/tickFormat|precision=/);
  });

  it.each(Object.entries(BLANK_SITES))('%s 가 빈 그림 자리를 말한다', (rel, why) => {
    expect(read(rel), `${rel}: ${why}`).toMatch(/<ChartBlank/);
  });

  /* ★이 자가 이 파일의 핵심이다 — **침묵한 빈칸**을 잡는다. 종전 결함 둘이
     전부 이 꼴이었다: `<Box height={chartH} />` 와 `) : null;`. 전자는 모양이
     뚜렷해서 정규식으로 잡힌다. */
  it('높이만 가진 **빈 상자**로 그림 자리를 때우지 않는다', () => {
    const dir = path.join(ROOT, 'src');
    const walk = (d: string): string[] =>
      fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => {
        const p = path.join(d, e.name);
        return e.isDirectory() ? walk(p) : e.name.endsWith('.tsx') ? [p] : [];
      });
    const bad: string[] = [];
    for (const f of walk(dir)) {
      const src = stripComments(fs.readFileSync(f, 'utf8'));
      /* `<Box height={…} />` — 자식도 없고 클래스도 없는 상자. 자리만 먹고
         아무 말도 안 하는 그 꼴이다. */
      if (/<Box\s+height=\{[^}]+\}\s*\/>/.test(src)) bad.push(path.relative(ROOT, f));
    }
    expect(bad, `빈 상자로 그림 자리를 때운 파일: ${bad.join(', ')}`).toEqual([]);
  });

  /* 깔지 **않은** 자리의 근거가 적혀 있나 — 이 표가 비면 다음 사람이 열넷을
     처음부터 다시 잰다. 근거 없는 등재를 막으려고 길이를 본다. */
  it('빌 수 없는 자리는 **근거와 함께** 적혀 있다', () => {
    for (const [rel, why] of Object.entries(NEVER_EMPTY)) {
      expect(fs.existsSync(path.join(ROOT, rel)), `${rel} 이 없어졌어요`).toBe(true);
      expect(why.length, `${rel}: 근거가 너무 짧아요`).toBeGreaterThan(20);
    }
    /* 전수였다는 사실을 수로 박는다 — 2026-10-22 에 `.sr-plot` 자리가 열넷이었다. */
    expect(Object.keys(BLANK_SITES).length + Object.keys(NEVER_EMPTY).length)
      .toBeGreaterThanOrEqual(14);
  });
});
