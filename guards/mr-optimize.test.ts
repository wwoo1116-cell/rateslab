/* 절대수익형 성과지표 · 구간 · 근사 최적화 [OWNER 2026-09-04 —
 * "지금 주어진 진입, 청산, 손절, 룩백, 진입 규칙을 바탕으로 전략 실험시에 근사
 * 최적화 세트를 바탕으로 결과를 보여주고, 그 밑에 TOP 5 조건을 매트릭스로
 * 보여주기" · "그리고 샤프가 아니라 절대수익형펀드(헤지펀드)에서 사용하는
 * 성과지표 가져와서 사용해주기" · "명목이 아니라 Delta라고 하기" ·
 * "비용기준은 0.25/0.5/1로 설정하기"].
 *
 * ## 이 파일이 지는 명제 다섯
 *
 * **격자는 화면이 고를 수 있는 값 위에서만 돈다.** 프리셋 밖의 최적을 적으면
 * 그 수를 재현할 손잡이가 없다 — 내렸던 이웃 칸 표가 지고 있던 규율이고,
 * 「채택」 버튼이 그 계약의 다른 쪽이다(칸 → 노브).
 *
 * **격자는 엔진 근사고, 화면이 그 사실을 적는다.** 162칸을 실가격으로 매기면
 * 못 돌아서다. 머리 카드가 실가격일 때 두 수는 다르고, 그 이유가 화면에 없으면
 * 읽는 사람이 둘 중 하나를 버그로 읽는다.
 *
 * **정렬은 화면이 한다.** 순위 기준을 바꿀 때마다 서버에 다시 물으면 같은
 * 격자를 기준만 바꿔 다시 도는 셈이다. 그리고 「기준을 바꾸면 1등이 바뀐다」는
 * 사실 자체가 이 표가 말해야 하는 것이라 전환은 즉각이어야 한다.
 *
 * **못 잰 값은 0 이 아니다.** `null` 은 「그 구간에서 그 지표가 안 선다」이지
 * 「최악이다」가 아니다(낙폭이 0 이라 Calmar 가 없는 칸, 손실 월이 없어 GPR 이
 * 없는 칸). 0 으로 채워 정렬하면 그런 칸이 한복판에 끼어 순위가 거짓이 된다.
 *
 * **샤프는 화면에서만 내려갔다.** 계약과 엔진에는 남는다 — 적합성 벡터가 그
 * 수를 잠그고 있고, 지우면 그 잠금이 풀린다(실전 규칙 다섯·이웃 칸을 내릴 때와
 * 같은 규율).
 */

import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments } from './_source';

const root = path.resolve(import.meta.dirname, '..');
const src = (rel: string) => stripComments(fs.readFileSync(path.join(root, rel), 'utf8'));
const raw = (rel: string) => fs.readFileSync(path.join(root, rel), 'utf8');

describe('절대수익형 성과지표 — 샤프의 자리에 분모가 다른 일곱', () => {
  const api = src('src/mr/api.ts');
  /* 카드 일곱은 **공유 부품**이다 [2026-09-07] — 통합 장부가 같은 열을 세우게
     되면서 `parts.RiskAdjusted` 로 갈라 냈다. 닻이 창에 박혀 있으면 부품을
     옮긴 날 이 가드가 「없어졌다」고 말한다(실제로 그렇게 죽었다). */
  const win = src('src/mr/parts.tsx');
  /* 같은 절의 사실이라도 **사는 집이 다르다** [2026-09-07]. 일곱 카드는 공유
     부품(`parts`), 회복일은 창의 「성과」 열, 단위 각주는 최적화 절이다. 한
     파일만 읽으면 옮긴 날 이 가드가 「없어졌다」고 거짓말한다. */
  const strat = src('src/mr/StrategyWindow.tsx');
  const pane = src('src/mr/OptimizePane.tsx');
  const py = raw('backend/app/mrmetrics.py');

  it('계약이 일곱을 다 싣는다 — 화면이 고를 수 있는 축이 그만큼이다', () => {
    const block = api.slice(api.indexOf('export interface MrPerf'), api.indexOf('export type MrSpanPerf'));
    for (const k of ['sortino', 'calmar', 'gpr', 'omega', 'profitFactor', 'ulcer', 'martin']) {
      expect(block, k).toMatch(new RegExp(`${k}:`));
    }
    /* 낙폭의 **길이**도 카드가 진다 — 깊이만 적으면 「얼마나 오래 물속이었나」를
       화면이 안 말한다. 회복 여부는 일수와 **다른 사실**이라 따로 온다. */
    expect(block).toMatch(/recoveryDays:/);
    expect(block).toMatch(/recovered:/);
    /* GPR 이 왜 없는지를 가르는 값 — 월 버킷이 모자란 것과 손실 월이 하나도
       없는 것은 둘 다 null 이지만 다른 사실이다. */
    expect(block).toMatch(/gprMonths:/);
  });

  it('화면이 일곱을 다 세우고, 없는 값에는 **왜인지**를 적는다', () => {
    for (const label of ['Sortino', 'Calmar', 'Martin', 'Ulcer', 'GPR', 'Omega', 'Profit Factor']) {
      expect(win, label).toContain(`label="${label}"`);
    }
    /* 회복일은 「위험조정」이 아니라 **성과** 열이다 — 비율이 아니라 일수라서. */
    expect(strat).toContain('label="회복일"');
    /* 못 잰 이유가 카드에 있다 — 「—」만 서면 0 인지 안 선 것인지 못 가른다. */
    expect(win).toMatch(/손실 난 날이 없어요/);
    expect(win).toMatch(/낙폭이 없었어요/);
    expect(win).toMatch(/손실 난 달이 없어요/);
    expect(win).toMatch(/진 거래가 없어요/);
    expect(strat).toMatch(/아직 회복 못 했어요/);
  });

  it('GPR 은 월 버킷, Omega 는 일별 — 같은 계열에서 재면 한 카드가 중복이다', () => {
    /* Σ손익 = Σ이익 − Σ손실 이므로 같은 일별 계열에서는 `GPR = Omega − 1` 이
       항등이다. 그 근거가 서버 주석에 있어야 다음 사람이 GPR 을 일별로
       되돌리지 않는다(`test_mrmetrics` 가 그 항등을 수로도 잰다). */
    expect(py).toMatch(/GPR = Omega − 1/);
    expect(py).toMatch(/월 버킷/);
  });

  it('샤프는 화면에서만 내려갔다 — 계약·엔진에는 남는다', () => {
    expect(win).not.toMatch(/label="Sharpe"/);
    expect(api).toMatch(/sharpe: number \| null/);
    expect(raw('backend/app/mrbacktest.py')).toMatch(/sharpe/);
    /* 내린 이유가 계약 주석에 남아 있다 — 지우면 되살릴 때 근거가 없다. */
    expect(raw('src/mr/api.ts')).toMatch(/화면에서 은퇴했다/);
  });

  it('비율은 원/원이라는 사실을 화면이 적는다 — 문헌값과 크기를 비교하면 안 된다', () => {
    expect(py).toMatch(/수익률이 아니라 \*\*원\*\*이다/);
    /* 화면의 그 문장은 최적화 절 각주가 진다 — 지표 카드 옆에서 읽힌다. */
    expect(pane).toMatch(/원\/원이라 수익률 기반 문헌값/);
  });
});

describe('구간은 전역 설정값이고, 성과가 그것을 따라간다', () => {
  const api = src('src/mr/api.ts');

  it('서버가 네 벌을 한 번에 보낸다 — 고르개가 재실행을 안 만든다', () => {
    expect(api).toMatch(/spans\?: MrSpanPerf\[\]/);
    expect(raw('backend/app/main.py')).toMatch(/"spans": mrm\.spans_for\(/);
    /* 목록은 서버와 화면이 같은 키를 쓴다 — 한쪽에만 있는 구간이 생기면
       고르개가 서버에 없는 구간을 고르게 된다. */
    const py = raw('backend/app/mrmetrics.py');
    for (const k of ['all', '1y', '1q', '1m']) {
      expect(py, k).toContain(`"${k}"`);
      expect(api, k).toContain(`v: '${k}'`);
    }
  });

  it('엔진은 구간으로 다시 안 돈다 — 룩백 워밍업이 구간 앞에 있어야 한다', () => {
    const py = raw('backend/app/mrmetrics.py');
    expect(py).toMatch(/엔진은 \*\*늘 전체 표본 위에서\*\* 돈다/);
    /* 최적화 라우트도 구간을 «채점» 으로만 쓴다 — 시뮬은 전체 dates 위에서. */
    const main = raw('backend/app/main.py');
    const grid = main.slice(main.indexOf('def _mr_optimize'), main.indexOf('def _mr_check_knobs'));
    expect(grid).toMatch(/start = mrm\.span_start\(dates, months\)/);
    expect(grid).toMatch(/mrbt\.simulate\(\s*\n\s*dates, vals,/);
  });
});

describe('근사 최적화 — 프리셋 격자 · TOP 5 매트릭스 · 채택', () => {
  /* 절 전체가 **공유 부품**이다 [2026-09-07] — 두 창(낱개·통합)이 같은 표를
     세운다. 창이 정하는 것은 안내·경고 문장 둘뿐이다. */
  const win = src('src/mr/OptimizePane.tsx');
  /* 부품이 아니라 **부르는 쪽**이 지는 사실이 있다 — 안내 문장·채택 처리·
     격자 버리기는 창마다 다르므로 창에서 잰다. */
  const strat = src('src/mr/StrategyWindow.tsx');
  /* 통합 장부 창도 **같은 흐름**이다 [OWNER 2026-09-09 — "둘 다 같은 흐름으로"]
     — 자동 실행·채택·격자 버리기를 두 창에서 같이 잰다. */
  const book = src('src/mr/BookWindow.tsx');
  const api = src('src/mr/api.ts');
  const main = raw('backend/app/main.py');

  it('격자는 다섯 노브의 프리셋 곱이다 — 3×3×3×3×2', () => {
    const grid = main.slice(main.indexOf('def _mr_optimize'), main.indexOf('def _mr_check_knobs'));
    for (const k of ['lookback', 'entryZ', 'exitZ', 'stopZ']) {
      expect(grid, k).toContain(`"${k}"`);
    }
    expect(main).toMatch(/MR_ENTRY_MODES_ALL: tuple\[str, \.\.\.\] = \("level", "touch"\)/);
    /* 프리셋 밖의 현재 값도 한 칸으로 낀다 — 안 그러면 「지금 칸」을 못 가리킨다. */
    expect(grid).toMatch(/if base\[knob\] not in o:/);
    /* 상한이 있다 — 화면에 안 쓰는 계산에 몇 초를 쓰지 않는다. */
    expect(main).toMatch(/MR_OPT_MAX_CELLS/);
  });

  it('비용·Delta·실전 규칙은 안 흔든다 — 통상값이 아니라 그날의 호가폭이다', () => {
    const grid = main.slice(main.indexOf('def _mr_optimize'), main.indexOf('def _mr_check_knobs'));
    /* 격자 축은 넷 + 진입 규칙뿐이다. costBp·notional 은 base 에서 **그대로** 온다. */
    expect(grid).toMatch(/cost_bp=base\["costBp"\]/);
    expect(grid).toMatch(/notional=base\["notional"\]/);
    expect(grid).not.toMatch(/for cb in/);
    /* 안내 문장은 창이 준다(`intro`) — 창마다 칸 수가 다를 수 있다. 2026-09-09
       에 그 문장이 「누르면 …」에서 「격자를 아직 못 돌렸어요 …」로 바뀌었다:
       격자는 이제 창을 열면 저절로 돌고, 이 문장은 **못 돌린 판**의 것이다. */
    expect(strat).toMatch(/비용·Delta 와 실전 규칙은 안 /);
    expect(strat).toMatch(/격자를 아직 못 돌렸어요/);
  });

  it('정렬은 화면이 한다 — 서버는 칸마다 지표를 다 실어 보낸다', () => {
    expect(api).toMatch(/export function rankCells/);
    /* 순위 기준이 쿼리에 없다 — 있으면 기준을 바꿀 때마다 격자를 다시 돈다. */
    const fetcher = api.slice(api.indexOf('export function fetchMrOptimize'), api.indexOf('export function rankCells'));
    expect(fetcher).not.toMatch(/rank/);
    expect(fetcher).toMatch(/q\.set\('span', span\)/);
  });

  it('못 잰 칸은 **뒤로** — 0 으로 채워 정렬하지 않는다', () => {
    const fn = api.slice(api.indexOf('export function rankCells'));
    expect(fn).toMatch(/if \(x === null\) return 1;/);
    expect(fn).toMatch(/if \(y === null\) return -1;/);
  });

  it('표는 TOP 5 **+ 지금 칸** 이다 — 자기 자리를 못 찾으면 순위가 말이 없다', () => {
    expect(win).toMatch(/function optRows/);
    expect(win).toMatch(/ranked\.slice\(0, 5\)/);
    expect(win).toMatch(/if \(at >= 5\) rows\.push/);
    /* 붙는 줄은 **자기 실제 등수**를 단다 — 6등이라고 적지 않는다. */
    expect(win).toMatch(/n: at \+ 1/);
    expect(win).toContain('label="지금 칸"');
  });

  it('채택은 **곧 실행이다** — 조건을 바꾸는 유일한 길이라서', () => {
    /* ⚠ 명제가 2026-09-09 에 뒤집혔다 [OWNER — "진입 규칙이나 룩백, 진입 청산
       손절 시그마는 … 사라지게 하고 … 바로 최적화 값을 보여주는 것"].

       종전에는 채택이 노브만 바꾸고 사람이 「실행」을 눌렀다 — 격자는 엔진
       근사고 머리 카드는 실가격일 수 있어서, 그 차이가 화면에 서는 순서를
       사람이 넘기게 한 것이었다. 그런데 노브 다섯이 화면에서 내려가면서 그
       「실행」 버튼이 **조건을 못 바꾸는 버튼**이 됐다. 채택이 실행까지 하지
       않으면 TOP 5 의 그 칸은 아무 일도 안 하는 버튼이 된다.

       두 회계의 차이는 사라지지 않았다 — 그 사실은 각주가 계속 말한다
       (「격자는 엔진 근사예요 — 머리 카드는 실가격이라 …」). */
    for (const [f, code] of [['StrategyWindow', strat], ['BookWindow', book]] as const) {
      const fn = code.slice(code.indexOf('const adopt = useCallback'),
                            code.indexOf('const adopt = useCallback') + 400);
      expect(fn, `${f} 의 채택`).toMatch(/adoptAndRun\(c, \+\+seq\.current\)/);
    }
    /* 실행까지 가는 길이 한 함수다 — 채택·격자 1등·순위 기준 변경이 같은 자리를
       지나야 세 길이 다른 조건으로 갈리지 않는다. */
    expect(strat).toMatch(/const adoptAndRun = useCallback/);
    expect(book).toMatch(/const adoptAndRun = useCallback/);
  });

  it('창을 열면 격자부터 돈다 — 두 창이 같은 흐름이다', () => {
    /* [OWNER 2026-09-09 — "전략 실험을 누름과 동시에 그냥 바로 최적화 값을",
       그리고 통합 장부도 "둘 다 같은 흐름으로"]. */
    for (const [f, code] of [['StrategyWindow', strat], ['BookWindow', book]] as const) {
      expect(code, `${f} 에 자동 흐름이 없다`).toMatch(/const runAuto = useCallback/);
      /* 격자 → 1등 → 실행. 1등을 고르는 자리가 화면이라는 사실도 여기 선다. */
      expect(code).toMatch(/rankCells\(o\.cells, rankKeyRef\.current\)\[0\]/);
      /* 실패해도 창이 비지 않는다 — 원본 규칙으로 실행하고 사유를 적는다. */
      expect(code).toMatch(/adoptAndRun\(knobsRef\.current, my\)/);
      /* 경합은 순번으로 버린다 — 비용을 빨리 두 번 바꾸면 늦은 응답이 이긴다. */
      expect(code).toMatch(/const seq = useRef\(0\)/);
    }
  });

  it('격자가 다시 도는 자리는 **비용·Delta·구간**이다 [OWNER 「자동으로 다시 돌리기」]', () => {
    /* 비용은 칸마다 다르게 물어서 순위를 바꾼다. Delta 는 비율 지표에 불변이라
       순위를 안 바꾸지만 총손익 축의 표와 「지금 칸」이 갈리지 않게 같이 돈다. */
    expect(strat).toMatch(/\}, \[id, span, knobs\.costBp, knobs\.notional\]\);/);
    expect(book).toMatch(/\}, \[span, knobs\.costBp, knobs\.notional\]\);/);
    /* 순위 기준은 **격자를 다시 안 돈다** — 칸마다 지표가 다 와 있다. */
    for (const code of [strat, book]) expect(code).toMatch(/\}, \[rankKey\]\);/);
  });

  it('격자가 엔진 근사임을 화면이 적는다', () => {
    expect(api).toMatch(/real: boolean;/);
    expect(main).toMatch(/"real": False/);
    expect(win).toMatch(/격자는 엔진 근사예요/);
  });

  it('새로 돌 때 옛 격자를 버린다 — 딴 조건의 순위를 들고 있지 않는다', () => {
    /* 자동 흐름에서는 «버리는 자리» 가 하나로 모였다(`runAuto` 의 첫 줄) —
       종목·구간·비용·Delta 가 전부 그 함수를 지난다. 종전처럼 세 자리에
       흩어 두면 하나가 빠져도 화면이 조용히 옛 순위를 이 실행의 것처럼 적는다. */
    for (const code of [strat, book]) {
      const fn = code.slice(code.indexOf('const runAuto = useCallback'));
      expect(fn.slice(0, 300)).toMatch(/setOpt\(undefined\)/);
    }
  });

  it('부품은 캐논이다 — Stat 스트립 · CDS Table · 공용 Segmented · 알약', () => {
    expect(win).toMatch(/from '@\/ui\/Stat'/);
    expect(win).toMatch(/from '@coinbase\/cds-web\/tables'/);
    expect(win).toMatch(/from '@\/ui\/ControlCard'/);
    /* 액션은 채움 알약(`data-fill`) — 이 절의 유일한 액션이 「최적화 실행」이다. */
    expect(win).toMatch(/className="sr-pillbtn"[\s\S]{0,80}data-fill/);
    /* 두 창이 **이 부품을 부른다** — 한쪽이 자기 판을 다시 만들면 갈린다. */
    for (const f of ['src/mr/StrategyWindow.tsx', 'src/mr/BookWindow.tsx']) {
      expect(src(f), f).toMatch(/<OptimizePane[\s/>]/);
      expect(src(f), f).toMatch(/from '\.\/OptimizePane'/);
    }
  });
});

describe('명목이 아니라 Delta 다 · 비용은 0.25 / 0.5 / 1', () => {
  const knob = src('src/mr/KnobBar.tsx');
  const win = src('src/mr/StrategyWindow.tsx');

  it('노브와 카드가 같은 낱말을 쓴다 — 화면 하나에 두 이름이 서지 않는다', () => {
    expect(knob).toContain('label="Delta (원/bp)"');
    expect(knob).toContain('label="Delta(원/bp)"');
    expect(knob).not.toContain('label="명목 (원/bp)"');
    expect(win).toContain('label="Delta"');
    /* 「원」은 한글이다 — Pretendard SR 의 `₩` 가 반각 「W」로 서기 때문
       [OWNER 2026-08-28]. 그 판례가 이 개명으로 지워지지 않는다. */
    expect(knob).not.toMatch(/₩\/bp/);
  });

  it('바뀐 이유가 주석에 있다 — 액면과 한 카드에서 충돌하고 있었다', () => {
    expect(raw('src/mr/KnobBar.tsx')).toMatch(/Delta라고 하기/);
    expect(raw('src/mr/KnobBar.tsx')).toMatch(/「명목」은 채권·스왑에서 \*\*액면\*\*/);
  });

  it('비용 프리셋 셋이 다 이 데스크의 값이다 — 0.05 는 화면이 안 권한다', () => {
    const api = src('src/mr/api.ts');
    expect(api).toMatch(/MR_COST_PRESETS = \[0\.25, 0\.5, 1\]/);
    /* 기본은 여전히 오너 실측 0.5 다 — 싸게 잡은 비용은 결론을 뒤집는다. */
    expect(api).toMatch(/costBp: 0\.5/);
    /* 도움말이 셋의 뜻을 말한다 — 셋이 같은 성격이면 프리셋이 아니라 눈금이다. */
    expect(knob).toMatch(/0\.25는 좋은 날, 1은 나쁜 날/);
  });
});

describe('백테스트 대사도 다리로 갈라진다 — 하루 일곱 줄', () => {
  const bt = src('src/backtest/BacktestWindow.tsx');

  it('세 표가 다 `reconTenors` 로 열을 세운다 — 한 표만 옛 방식이면 감도가 사라진다', () => {
    for (const k of ['swap', 'bond', 'futures']) {
      expect(bt, k).toContain(`tenors={reconTenors(pair.${k})}`);
      expect(bt, k).not.toContain(`tenors={pair.${k}.tenors}`);
    }
  });

  it('퓨처스왑의 IRS 다리가 스왑 표에서 빠진다 — 같은 돈이 두 표에 서지 않는다', () => {
    const mb = raw('backend/app/mixedbook.py');
    const fn = mb.slice(mb.indexOf('def book_recon'));
    expect(fn).toMatch(/with_legs=True/);
    /* 옛 경로 — 스왑 표에 FSW 다리를 얹던 그 목록이 사라졌다. */
    expect(fn).not.toMatch(/fsw_swap_legs/);
  });

  it('선물 각주가 자기 표에 있는 열을 「없다」고 말하지 않는다', () => {
    const rc = src('src/backtest/recon.ts');
    expect(rc).toMatch(/recon\.legTenors\?\.length \? legs : outright/);
    expect(rc).toMatch(/퓨처스왑은 하루가 일곱 줄이에요/);
    /* 「선물은 손익이 전부 평가」는 **다리가 없는 표**의 문장이다 — 다리 판에서
       그대로 쓰면 바로 다음 문장(캐리·롤다운은 IRS 다리에서 온다)과 어긋난다. */
    expect(rc).toMatch(/선물 다리는 손익이 전부 평가예요/);
  });

  it('IRS 다리는 **버킷**으로 선물 달력에 얹힌다 — 돈이 보존된다', () => {
    const ft = raw('backend/app/futures.py');
    expect(ft).toMatch(/def _bucket_leg/);
    /* 두 번째 정의 금지 — 값매김은 스왑 엔진이 하고 여기서는 접기만 한다. */
    expect(ft).toMatch(/swap_rec = swap_book_recon\(dataset, swap_pos, with_krd=True\)/);
    /* Δbp 는 더한다(수준의 차라 이어 붙는다), 못 잰 노드는 공란이다. */
    expect(ft).toMatch(/dbp\[lb\] = round\(sum\(seen\), 2\) if seen else None/);
  });
});

describe('TOP 5 의 「채택」은 오른쪽에 **고정**된다', () => {
  /* [OWNER 2026-09-07 — "고정 열로 ㄱㄱ"]. 이 표는 상자를 넘고 넘침이 데이터에
     달렸다(열 폭이 내용에서 온다 — 실측 BSS-3Y 10px · FSW-3Y 47.7px). 넘친 쪽이
     하필 누르는 칸이라, 안 붙이면 표의 유일한 액션이 기본 화면에 없다.
     실측 2026-09-07: 붙인 뒤 스크롤 양 끝에서 「채택」이 상자 안에 선다. */

  const pane = src('src/mr/OptimizePane.tsx');
  const css = raw('src/theme/type.css');
  const block = css.slice(css.indexOf('.sr-mr-optgrid th:last-child'));

  it('격자에 제 클래스가 있다 — 대사표와 같은 상자를 쓰면서도 규칙은 다르다', () => {
    /* `.sr-mr-drawertable` 은 대사표와 **공유**다. 고정을 그 클래스에 걸면
       하루 일곱 줄짜리 대사표의 마지막 열까지 같이 붙는다. */
    expect(pane).toMatch(/className="sr-mr-drawertable sr-mr-optgrid"/);
    expect(css).toContain('.sr-mr-optgrid');
  });

  it('경계는 box-shadow 다 — border 는 sticky 셀에서 1px 이 곧 샘이다', () => {
    /* 대사표 고정 열(`.sr-recon-edge-l`)이 적어 둔 그 근거와 같다: 테두리는
       레이아웃을 1px 밀고, 밀린 1px 로 밑이 샌다. */
    expect(block).toMatch(/box-shadow:/);
    expect(block, '고정 셀에 border 를 썼다').not.toMatch(/border(-left|-right)?:/);
  });

  it('고정 셀의 배경은 불투명이다 — 밑을 지나는 행이 비치면 두 줄이 겹쳐 읽힌다', () => {
    expect(block).toMatch(/background: var\(--sr-card\)/);
    /* 색은 토큰만 — hex 는 `direction.css` 에만(CLAUDE.md 규칙 3). */
    expect(block, 'hex 색을 썼다').not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });

  it('**안 넘치면 그림자를 안 그린다** — 없는 사실을 말하지 않는다', () => {
    /* 덮는 것이 없는데 「여기서부터 덮고 있다」를 그리면 화면이 거짓말한다 —
       `.sr-recon-div-l` 이 2026-09-03 에 같은 이유로 그림자를 버린 판단이다.
       CSS 는 넘침을 모르므로 화면이 재서 `data-covering` 을 단다. */
    expect(block).toMatch(/\[data-covering='1'\][\s\S]{0,200}box-shadow:/);
    expect(pane).toMatch(/data-covering=\{covering \? '1' : '0'\}/);
    expect(pane).toMatch(/scrollWidth - box\.clientWidth > 1/);
  });

  it('재는 자리는 **CDS 가 두른 스크롤 상자**다 — sticky 의 기준과 같아야 한다', () => {
    /* sticky 는 가장 가까운 스크롤 컨테이너에 붙는다. 바깥 Box 를 재면 그
       상자는 안 스크롤하므로 넘침이 늘 0 이고 그림자가 영영 안 선다. */
    expect(pane).toMatch(/querySelector<HTMLElement>\('div\[class\*="tableContainer"\]'\)/);
  });

  it('ResizeObserver 하나에 안 기댄다 — 페인트가 없으면 콜백도 없다', () => {
    /* RO 콜백은 렌더 수명주기에 실려 온다. 탭이 페인트를 안 하면 아예 안 오고
       (자동화 탭 실측 0회), 그러면 창 크기만 바뀐 판에서 그림자가 안 따라간다. */
    expect(pane).toMatch(/window\.addEventListener\('resize', measure\)/);
    expect(pane).toMatch(/window\.removeEventListener\('resize', measure\)/);
  });
});

describe('자동 채택 기준은 **CDaR 비**다 [OWNER 2026-09-09]', () => {
  /* Calmar 에서 옮겨 왔다. 근거는 평가층 사양의 그 문장 — **MaxDD 는 단일관측
     추정량**이라(이 표본에서 MaxDD 의 50% 를 넘는 낙폭 사건이 셋뿐이고 1등은
     코로나 창이다) Calmar 의 표준오차가 넓다. 재 보고 옮겼다: 162칸에서 두
     기준의 순위상관 0.84 · 1등은 계열에 따라 갈리되 서로의 상위 5 안
     (`docs/EVAL_LANE_STATE.md` §8). */

  const win = src('src/mr/OptimizePane.tsx');
  const api2 = src('src/mr/api.ts');
  const stratW = src('src/mr/StrategyWindow.tsx');
  const bookW = src('src/mr/BookWindow.tsx');
  const mainPy = raw('backend/app/main.py');

  it('두 창의 기본 기준이 CDaR 비다', () => {
    for (const [f, code] of [['StrategyWindow', stratW], ['BookWindow', bookW]] as const) {
      expect(code, `${f} 의 기본 기준`).toMatch(/useState<MrRankKey>\('cdarRatio'\)/);
    }
  });

  it('기준 목록의 **첫 칸**이자 표의 첫 지표 열이다', () => {
    /* 순위를 매긴 자가 맨 앞에 서야 「왜 이 줄이 1등인가」가 눈으로 읽힌다. */
    const first = api2.slice(api2.indexOf('MR_RANK_KEYS = ['), api2.indexOf("{ v: 'calmar'"));
    expect(first).toMatch(/v: 'cdarRatio'/);
    const cols = win.slice(win.indexOf('OPT_COLS'), win.indexOf("{ k: 'sortino'"));
    expect(cols.indexOf("k: 'cdarRatio'")).toBeGreaterThan(0);
    expect(cols.indexOf("k: 'cdarRatio'")).toBeLessThan(cols.indexOf("k: 'calmar'"));
  });

  it('Calmar 는 **안 지운다** — 둘이 갈리는 자리를 보려면 나란히 있어야 한다', () => {
    expect(api2).toMatch(/v: 'calmar'/);
    expect(win).toMatch(/k: 'calmar'/);
  });

  it('서버가 칸마다 그 값을 싣는다 — 화면이 다시 계산하지 않는다', () => {
    expect(mainPy).toMatch(/"cdarRatio",/);
    const met = raw('backend/app/mrmetrics.py');
    expect(met).toMatch(/"cdarRatio": _r\(cdar_ratio, 4\)/);
    /* 산술은 **평가층 한 곳**이 진다 — 화면이 고르는 기준과 평가층이 순위 매기는
       기준이 갈리면 화면이 고른 칸을 평가층이 다른 자로 다시 잰다. */
    expect(met).toMatch(/from evaluation import metrics as ev/);
  });

  it('못 잰 칸은 **뒤로** 간다 — 구 백엔드의 `undefined` 도 그렇다', () => {
    /* 0 으로 채워 정렬하면 안 잰 칸이 한복판에 끼어들어 순위가 거짓이 된다. */
    expect(api2).toMatch(/const x = a\[key\] \?\? null;/);
    expect(win).toMatch(/best\[rankKey\] \?\? null/);
  });
});
