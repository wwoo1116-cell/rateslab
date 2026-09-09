/* BSS 테너 **통합** 밴드 워치 [OWNER 2026-09-01 — "BSS만을 활용한 전략을 구상한다고
 * 할 때 지금은 각 테너별로 흩어져있는데, BSS 테너 통합 밴드 워치를 하나 만들어서
 * 승률 및 세부사항들을 확인할 수 있게 해줘.. 밴드워치 랭킹 순위, 계열 밑에 따로
 * 하나 빼주면 되겠다"].
 *
 * ## 이 파일이 지는 명제 넷
 *
 * **통합 줄은 랭킹이 아니다.** |z| 로 매긴 순위에 집계 한 줄을 끼우면 그 줄이
 * 「14위」로 읽힌다. 순위 칸은 비고, 레벨·전일 칸은 아예 값이 없다 — 만기가 다른
 * 아홉 스프레드의 평균은 거래할 수 있는 값이 아니라서 지어내지 않는다.
 *
 * **고정은 CSS 한 줄에 달려 있다.** CDS `Table` 이 표를 `overflow: auto` 상자로
 * 감싸므로 sticky 의 기준이 바깥 스크롤러가 아니라 그 상자가 된다. 그걸 풀어 주는
 * 규칙이 없으면 통합 줄도 **열 머리도** 안 붙는다(실측 2026-09-01: thead 가
 * −107px 로 밀려 올라갔고, 그때까지 주석은 「머리는 스크롤을 따라온다」였다).
 *
 * **승률의 분모와 걸린 돈을 화면이 말한다.** 통합 승률은 아홉 승률의 평균이 아니라
 * 한 통에 모은 거래의 승률이고(실측 78.41% 대 78.29% — 갈린다), 동일가중 합이라
 * 아홉이 동시에 서면 명목이 아홉 배다. 둘 다 안 적으면 큰 숫자만 남는다.
 *
 * **노브는 한 벌이다.** 낱개 창과 통합 창이 노브를 따로 그리면 프리셋 하나만
 * 바뀌어도 두 화면이 갈리고, 「낱개로는 벌고 통합으로는 잃는다」가 규칙 탓인지
 * 노브 탓인지 못 가린다. 서버도 같은 자리를 하나로 뒀다(`main._mr_leg`).
 *
 * 합치기의 산술 자체(총합·승률·상관·손익분기)는 파이썬 시험이 진다
 * (`backend/tests/test_mrbook.py`) — 그 계산이 사는 곳이 거기다.
 */

import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments } from './_source';

const root = path.resolve(import.meta.dirname, '..');
const src = (rel: string) => stripComments(fs.readFileSync(path.join(root, rel), 'utf8'));
const raw = (rel: string) => fs.readFileSync(path.join(root, rel), 'utf8');

describe('통합 줄은 랭킹이 아니다', () => {
  const page = src('src/mr/MrPage.tsx');

  it('랭킹 행 뒤에 **따로** 선다 — `rows.map` 밖이다', () => {
    /* 지도의 일부로 그리면(예: rows 에 밀어 넣기) 순위가 매겨진다.
       ⚠ 종전 판정은 `page.indexOf('))}')` 로 **파일의 첫** `))}` 를 집었는데
       그건 `BookDetail` 안 스트립 map 의 끝이라(192줄) 통합 줄을 랭킹 map
       **안**으로 밀어 넣어도 초록이었다(2026-09-02 검사). 이제 `rows.map(` 의
       여는 괄호부터 짝이 맞는 닫는 괄호까지를 잘라 **그 안에 없음**을 본다. */
    expect(page).toMatch(/\{watch \?/);
    expect(page).toMatch(/className="sr-mr-book"/);
    const open = page.indexOf('rows.map(');
    expect(open, 'rows.map(').toBeGreaterThan(0);
    let depth = 0;
    let close = -1;
    for (let i = page.indexOf('(', open); i < page.length; i++) {
      const c = page[i];
      if (c === '(') depth++;
      else if (c === ')') { depth--; if (depth === 0) { close = i; break; } }
    }
    expect(close, 'rows.map 의 닫는 괄호').toBeGreaterThan(open);
    expect(page.slice(open, close)).not.toContain('sr-mr-book');
  });

  it('레벨·전일 칸에 수를 안 적는다 — 평균 낼 수 없는 것은 안 낸다', () => {
    const row = page.slice(page.indexOf('className="sr-mr-book"'), page.indexOf('watchText(watch)'));
    /* 순위·값·1D 세 칸이 전부 `MINUS` 한 글자다. */
    expect(row.match(/\{MINUS\}/g)?.length).toBe(3);
    /* 계약에도 그 자리가 없다 — 서버가 아예 안 보낸다. */
    const api = src('src/mr/api.ts');
    const watch = api.slice(api.indexOf('export interface MrWatch {'), api.indexOf('export interface MrBoard'));
    expect(watch).not.toMatch(/^\s*v:/m);
    expect(watch).not.toMatch(/^\s*d1:/m);
    for (const k of ['meanAbsZ', 'meanPctB', 'outLow', 'outHigh', 'reentry', 'inside', 'peak']) {
      expect(watch, k).toMatch(new RegExp(`${k}:`));
    }
  });

  it('만기 순 스트립은 만기 순이다 — 서버가 준 차례를 다시 정렬하지 않는다', () => {
    const detail = page.slice(page.indexOf('function BookDetail'), page.indexOf('export function MrPage'));
    expect(detail).toMatch(/watch\.legs\.map/);
    expect(detail).not.toMatch(/\.sort\(/);
  });

  it('종가가 갈리면 그 사실을 말한다 — 최신 날짜만 적지 않는다', () => {
    expect(page).toMatch(/watch\.stale/);
    expect(page).toMatch(/watch\.asofMin/);
  });
});

describe('고정 — 통합 줄도 열 머리도 붙는다', () => {
  const css = raw('src/theme/type.css');

  it('CDS 가 두른 `overflow: auto` 상자를 풀어 준다', () => {
    /* 이 규칙이 없으면 sticky 의 기준 스크롤러가 «굴릴 것이 없는 상자» 가 된다.
       지우면 통합 줄과 열 머리가 **조용히** 안 붙는다 — 에러도 경고도 없다. */
    expect(css).toMatch(/\.sr-rv-rank-scroll > div \{\s*overflow: visible;/);
  });

  it('통합 줄은 바닥에 붙고 배경이 불투명하다', () => {
    const block = css.slice(css.indexOf('tr.sr-mr-book > td {'));
    expect(block).toMatch(/position: sticky;/);
    expect(block).toMatch(/bottom: 0;/);
    /* 반투명이면 밑을 지나는 틴트가 비쳐 줄이 격자처럼 읽힌다(ReconStack 의 규칙). */
    expect(block).toMatch(/background: var\(--sr-card\);/);
  });

  it('색이 아니라 헤어라인이 랭킹과 가른다 — 사이드 스트라이프 금지', () => {
    const block = css.slice(css.indexOf('tr.sr-mr-book > td {'), css.indexOf('tr.sr-mr-book > td {') + 600);
    expect(block).not.toMatch(/border-left/);
    expect(block).toMatch(/--color-bgLine/);
    expect(block).not.toMatch(/--sr-(up|down)/);
  });
});

describe('통합 장부 창이 말해야 하는 것', () => {
  const win = src('src/mr/BookWindow.tsx');

  it('승률의 **분모**를 적는다 — 아홉 승률의 평균이 아니다', () => {
    expect(win).toMatch(/한 통에/);
    /* 미청산 다리는 원본 규약대로 승률에 안 든다 — 몇 다리인지를 옆에서 말한다. */
    expect(win).toMatch(/openLegs/);
    expect(win).toMatch(/미청산 \$\{run\.summary\.openLegs\}다리/);
  });

  it('걸린 돈을 적는다 — 동일가중 합의 대가', () => {
    expect(win).toMatch(/book\.maxLegs/);
    expect(win).toMatch(/book\.peakNotional/);
    expect(win).toMatch(/book\.idleShare/);
  });

  it('묶어서 나아졌는지를 답한다 — 개별 Calmar·쌍상관·유효 독립', () => {
    /* 축이 샤프 → **Calmar** 로 갈렸다 [OWNER 2026-09-07]. 그러면서 이 절이
       답하는 질문도 갈렸다: 샤프판에서는 「유효 독립」과 산술이 맞물렸지만
       (SR 은 1/σ 라 통합/개별 ≈ √N_eff 가 검산), Calmar 의 분모는 최대낙폭이라
       그 검산이 안 선다. 화면이 그 사실을 적는지도 같이 잰다. */
    expect(win).toMatch(/legCalmar\.median/);
    expect(win).toMatch(/diversification\.meanPairCorr/);
    expect(win).toMatch(/diversification\.effectiveN/);
    /* **잰 다리 수**가 화면에 있어야 한다 — 낙폭이 0 인 다리는 Calmar 가 없고,
       0 으로 채우면 그 다리가 «최악» 으로 줄을 서서 중앙값을 끌어내린다. */
    expect(win).toMatch(/legCalmar\.of/);
    /* 상관을 **몇 봉에서 쟀나** — 짧은 구간에서는 값을 믿으면 안 된다. */
    expect(win).toMatch(/diversification\.days/);
  });

  it('구간은 전역 설정값이다 — 성과·만기별·묶어서 나아졌나가 같이 따라간다', () => {
    /* [OWNER 2026-09-07 — "통합 장부에도 마찬가지로 적용해줘"]. 낱개 창과 같은
       계약이고 같은 이유다: 서버가 네 벌을 한 번에 보내므로 고르개가 재실행도
       stale 도 안 만든다. */
    expect(win).toMatch(/onSpanChange=\{setSpan\}/);
    expect(win).toMatch(/run\?\.spans\?\.find/);
    expect(raw('backend/app/mrbook.py')).toMatch(/"spans": _spans\(/);
    /* 한 화면이 **두 구간을 말하지 않는다** — 카드가 구간이면 만기별 표도
       구간이어야 한다. 표는 `perf.legs`(구간) 이지 `run.legs`(전체)가 아니다. */
    expect(win).toMatch(/legs=\{perf\.legs\}/);
  });

  it('표본 삼분할만은 **항상 전체 위에** 선다 — 이름이 그 사실을 말한다', () => {
    /* [OWNER 2026-09-07]. 안정성 검사라 채점 구간과 무관하다 — 「지난 1개월」을
       다시 셋으로 쪼개면 한 조각이 열흘이라 수가 뜻을 잃는다. 옆 카드가 「지난
       1분기」인데 이 열만 2020년부터이므로 **제목과 각주가 그것을 적어야** 한다. */
    expect(win).toMatch(/title="표본 삼분할"/);
    expect(win).toMatch(/고른 구간과 무관하게/);
    /* 서버도 전체 위에서 낸다 — 화면만 이름을 바꾸면 거짓말이 된다. */
    expect(raw('backend/app/mrbook.py')).toMatch(/표본 삼분할은 항상 전체 위에 선다/);
  });

  it('못 선 만기를 조용히 빼지 않는다', () => {
    expect(win).toMatch(/run\.excluded/);
  });

  it('노브 민감도가 **생겼고**, 각주가 그 사실을 따라갔다', () => {
    /* 2026-09-01 판의 각주는 「노브 민감도(이웃 칸)는 두 창 다 없어요」였다.
       오너가 2026-09-07 에 그 결정을 뒤집었으므로 각주도 같이 고쳤다 — 화면이
       자기가 하는 일을 「안 한다」고 말하면 안 된다. */
    expect(win).toMatch(/<OptimizePane[\s/>]/);
    /* 옛 문장을 **인용해서 정정**하는 것은 허용이다(이 리포는 정정 이력을 남긴다).
       금지되는 것은 그것이 아직 **주장으로 서 있는** 것이라, 「두 창 다 없어요」가
       나오면 바로 뒤에 정정이 따라붙어야 한다. */
    const stale = /두 창 다 없어요/.exec(win);
    if (stale) {
      expect(win.slice(stale.index, stale.index + 120),
        '옛 각주가 정정 없이 주장으로 서 있다').toMatch(/이제 사실이 아니에요/);
    }
    /* 뒤집힌 것은 **결정**이지 경고가 아니다 — 표본내라는 사실은 그대로 적는다. */
    expect(win).toMatch(/표본내/);
    expect(win).toMatch(/전진분석이 파라미터 선택에 값을 못 더한다는/);
  });

  it('통합 격자는 **더한 뒤에** 채점한다 — 다리별 값의 평균이 아니다', () => {
    /* Calmar·낙폭은 비선형이라 아홉의 평균이 장부의 값이 아니다. 아홉이 서로
       다른 날 물속에 있으면 장부의 최대낙폭은 아홉 낙폭의 합보다 훨씬 작고,
       그 차이가 이 창의 존재 이유(«묶어서 나아졌나»)다. */
    const main = raw('backend/app/main.py');
    const fn = main.slice(main.indexOf('def _mr_book_optimize'),
                          main.indexOf('def _mr_check_knobs'));
    expect(fn).toMatch(/채점은 반드시 \*\*더한 뒤에\*\* 한다/);
    /* 더하는 것이 코드에도 있다 — 날짜로 포개고 그 위에서 한 번 잰다. */
    expect(fn).toMatch(/daily\[i\] \+= pt\["dailyPnl"\]/);
    expect(fn).toMatch(/m = mrm\.score\(dates, pts, raw, start/);
  });

  it('명구 의무 — 재현 도구이고 국고 다리는 민평이다', () => {
    expect(win).toMatch(/투자판단이 아니에요/);
    expect(win).toMatch(/민평/);
  });
});

describe('노브는 한 벌이다', () => {
  it('두 창이 같은 노브 바와 같은 stale 판정을 임포트한다', () => {
    for (const f of ['src/mr/StrategyWindow.tsx', 'src/mr/BookWindow.tsx']) {
      const code = src(f);
      expect(code, f).toMatch(/import \{ MrKnobBar, mrKnobsStale \} from '\.\/KnobBar'/);
    }
  });

  it('σ 알약과 손 구현은 화면에서 사라졌고, 되살아나지도 않는다', () => {
    /* 2026-09-09 에 노브 다섯(룩백 · 진입 규칙 · 진입/청산/손절 σ)이 설정 줄에서
       내려갔다 [OWNER — "진입 규칙이나 룩백, 진입 청산 손절 시그마는 그냥 최초
       전략 실험 화면에서 사라지게 하고"] — 그 값들은 이제 격자가 답한다. `SigmaPick`
       은 그 자리와 함께 지워졌고, 손 구현(`NumInput`·`Choice`)은 2026-09-02
       승격으로 이미 없다. 셋 다 **어느 mr 파일에도** 되살아나면 안 된다:
       살아나면 화면이 「고르는 자리」를 둘로 말하게 된다.

       숫자 칸은 여전히 공용 `NumField` 하나다(비용·Delta 가 그것을 쓴다). */
    const mrFiles = ['src/mr/KnobBar.tsx', 'src/mr/StrategyWindow.tsx', 'src/mr/BookWindow.tsx', 'src/mr/MrPage.tsx'];
    for (const name of ['function SigmaPick', 'function NumInput', 'function Choice']) {
      const homes = mrFiles.filter((f) => src(f).includes(name));
      expect(homes, `${name} 은 화면에 없다`).toEqual([]);
    }
    expect(src('src/mr/KnobBar.tsx')).toMatch(
      /import \{ Field, NumField \} from '@\/ui\/ControlCard'/,
    );
    /* 프리셋 목록은 **계약에 그대로 산다** — 격자가 그 위에서 돈다. 화면에서
       내린 것과 계약에서 지운 것은 다른 일이다(실전 규칙 다섯의 그 판례). */
    const api = src('src/mr/api.ts');
    for (const k of ['MR_STRATEGY_PRESETS', 'MR_STRATEGY_LOOKBACKS', 'MR_ENTRY_MODES']) {
      expect(api, k).toContain(k);
    }
  });

  it('청산 사유의 우리말은 앱에 한 벌이다 — 두 표가 같은 사건을 같게 부른다', () => {
    const homes = ['src/mr/parts.tsx', 'src/mr/StrategyWindow.tsx', 'src/mr/BookWindow.tsx']
      .filter((f) => src(f).includes('const WHY_WORD'));
    expect(homes).toEqual(['src/mr/parts.tsx']);
    for (const f of ['src/mr/StrategyWindow.tsx', 'src/mr/BookWindow.tsx']) {
      expect(src(f), f).toMatch(/WHY_WORD/);
    }
  });

  it('통합 창의 노브 쿼리는 낱개와 **한 함수**에서 나온다', () => {
    const api = src('src/mr/api.ts');
    expect(api).toMatch(/function strategyQuery\(/);
    /* 두 페처가 같은 조립기를 쓴다 — 한쪽만 노브가 빠지면 두 판이 딴 규칙이 된다. */
    const strat = api.slice(api.indexOf('export function fetchMrStrategy'));
    expect(strat).toMatch(/strategyQuery\(p\)/);
    const book = api.slice(api.indexOf('export function fetchMrBook'));
    expect(book).toMatch(/strategyQuery\(p\)/);
  });
});

describe('서버도 한 자리다', () => {
  it('낱개 라우트와 통합 라우트가 같은 준비·시뮬 함수를 부른다', () => {
    const py = fs.readFileSync(path.join(root, 'backend/app/main.py'), 'utf8');
    expect(py).toMatch(/def _mr_leg\(/);
    const strategy = py.slice(py.indexOf('def mr_strategy('), py.indexOf('def mr_book('));
    expect(strategy).toMatch(/_mr_leg\(/);
    const book = py.slice(py.indexOf('def mr_book('));
    expect(book).toMatch(/_mr_leg\(/);
    /* 노브 검증도 한 문이다 — 두 벌이면 한쪽만 통과하는 조합이 생긴다. */
    expect(strategy).toMatch(/_mr_check_knobs\(/);
    expect(book).toMatch(/_mr_check_knobs\(/);
  });

  it('보드 페이로드가 바뀌었으니 캐시 스키마가 올라가 있다', () => {
    /* 안 올리면 옛 캐시가 `watch` 없는 보드를 계속 내주고 화면은 통합 줄을
       아예 안 그린다 — 실제로 한 번 밟았다(2026-09-01).

       **이 시험은 판을 세는 게 아니라 「마지막 변경에 승급이 따라붙었나」를
       잰다.** 그래서 최신 판의 번호와 그 판의 사유 한 줄을 같이 본다:
         v14 = fut defn 정정(「5% 합성」 오라벨 — 2026-09-02 적대 대사)
         v15 = 보드 밴드의 σ 를 표본 → **모집단**으로(2026-09-02 오너 결정)
         v16 = 행에 `triggers`·`triggerBlocked`(2026-09-09 오너 「트리거 레벨까지」)
         v17 = IRS 커브·플라이 열둘 + `asof.irs`(2026-09-09 오너 「커브·버터플라이도」)
       — 같은 SQL 이 다른 모양·다른 z 를 만든다. v16 도 실제로 한 번 밟았다:
       라우트를 고치고 백엔드를 재기동했는데 응답에 `triggers` 가 없었다(디스크
       캐시가 v15 페이로드를 그대로 내줬다). */
    const cache = fs.readFileSync(path.join(root, 'backend/app/cache.py'), 'utf8');
    expect(cache).toMatch(/SCHEMA_VERSION = 17/);
    expect(cache).toMatch(/v17 \(2026-09-09\)/);
    expect(cache).toMatch(/v16 \(2026-09-09\)/);
    /* 옛 판의 사유 줄도 남아 있어야 한다 — 승급 이력이 곧 이 파일의 근거다. */
    expect(cache).toMatch(/v15 \(2026-09-02\)/);
    expect(cache).toMatch(/v14 \(2026-09-02\)/);
  });
});
