/* 「얼라인」의 소스 쪽 절반 [2026-08-27, 감사 3라운드].
 *
 * ── 왜 이 가드가 따로 필요한가 ──────────────────────────────────────────────
 * 1·2라운드는 **화면에서 쟀다**(브라우저에서 행마다 컨트롤 높이와 라벨 top 을
 * 재는 프로브). 그것이 실제 위반 셋을 잡았고, 프로브 없이는 못 봤을 것들이다.
 * 그런데 그 방법에는 두 가지 구멍이 있다:
 *
 *   · 화면에 **그때 떠 있는 것**만 잰다. 안 열어 본 창·안 고른 종류는 안 잰다.
 *   · CI 에서 안 돈다. 다음 사람이 되돌려도 아무 말이 없다.
 *
 * 반대로 소스 스캔은 «어떻게 보이는가» 를 못 본다(docs/CHART_LANE_STATE.md §8
 * 의 그 교훈). 그래서 **둘 다** 필요하고, 이 파일은 소스에서만 볼 수 있는 것을
 * 맡는다: 규칙이 **한 곳에 적혀 있는가**(8)와 **라벨이 컨트롤 위인가**(2).
 */

import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { CONTROL_H } from '../src/ui/controlHeight';
import { stripComments, walk } from './_source';

const SRC = path.resolve(import.meta.dirname, '../src');
const read = (...p: string[]) => fs.readFileSync(path.join(SRC, ...p), 'utf8');

/** 터미널 레인은 자기 문법을 갖는다(그 화면의 행 높이는 20/24다 —
 *  `theme/terminal.css` 머리 주석). 이 가드의 대상이 아니다. */
const isOurs = (f: string) => !f.replace(/\\/g, '/').includes('/terminal/');

describe('규칙 1·8 — 컨트롤 등고는 **한 수**다', () => {
  it('그 수는 32 이고 한 곳에서 나온다', () => {
    expect(CONTROL_H).toBe(32);
    const src = stripComments(read('ui', 'controlHeight.ts'));
    expect(src).toMatch(/export const CONTROL_H = 32/);
  });

  it('아무도 그 수를 **따로 적지 않는다**', () => {
    /* 2026-08-27 이전에는 일곱 파일에 열세 번 따로 적혀 있었고, 그래서 CDS
       `Select` 가 30px 로 앉은 것을 아무것도 잡아 주지 못했다. 수를 모으면
       다음에는 여기서 걸린다. */
    const offenders: string[] = [];
    for (const file of walk(SRC, ['.ts', '.tsx'])) {
      if (!isOurs(file)) continue;
      const code = stripComments(fs.readFileSync(file, 'utf8'));
      const lines = code.split('\n');
      lines.forEach((ln, i) => {
        if (/height\s*[:=]\s*\{?\s*32\b/.test(ln)) {
          offenders.push(`${path.relative(SRC, file)}:${i + 1}`);
        }
      });
    }
    expect(offenders).toEqual([]);
  });

  it('컨트롤 세 종류가 **같은 상수**를 진다', () => {
    /* 입력·날짜·드롭다운. 셋 중 하나만 빠지면 그 칸만 짧아지고, 바닥 정렬
       행에서는 그것이 곧 라벨 줄이 갈리는 것이다(「얼라인」 3). */
    expect(stripComments(read('ui', 'IsoDateField.tsx'))).toMatch(/height:\s*CONTROL_H/);
    expect(stripComments(read('ui', 'window', 'popup.ts'))).toMatch(/height:\s*CONTROL_H/);
    expect(stripComments(read('backtest', 'BacktestWindow.tsx'))).toMatch(/height=\{CONTROL_H\}/);
  });
});

describe('규칙 2 — 라벨은 컨트롤 **위**다', () => {
  const field = stripComments(read('ui', 'ControlCard.tsx'));

  it('`Field` 는 세로 스택이고 라벨이 **먼저** 온다', () => {
    /* 라벨을 옆에 붙이면 라벨 폭마다 컨트롤 시작점이 계단이 진다(전략 실험 창
       첫 판의 실측 — "아주 얼라인이 개판"). */
    const body = field.slice(field.indexOf('export function Field'));
    const stack = body.indexOf('<VStack');
    const label = body.indexOf('{label}');
    const kids = body.indexOf('{children}');
    expect(stack).toBeGreaterThan(-1);
    expect(label).toBeGreaterThan(stack);
    expect(kids).toBeGreaterThan(label);
  });

  it('라벨의 활자는 **legal** 이다 — CDS `label` prop 의 label2 가 아니다', () => {
    /* CDS 컨트롤의 `label` prop 은 label2(14/400)로 그려져 같은 행의 `Field`
       라벨(legal 13/500)과 어긋난다 — 실측 2026-08-26 라벨 top 133 대 171.
       그래서 이 리포의 라벨은 언제나 `Field` 가 진다. */
    expect(field).toMatch(/font="legal"/);
  });

  it('CDS 컨트롤의 `label` prop 은 **`compact` 일 때만** 쓴다', () => {
    /* `accessibilityLabel` 은 다른 것이다(이름이지 그려지는 라벨이 아니다).
       우리 래퍼(`Field`·`NumField`·`IsoDateField`·`SigmaPick`)의 `label` 도
       아니다 — 그것들이 곧 이 규칙을 **지키는** 부품이다.
     *
     * ── 왜 `compact` 는 예외인가 [실측 2026-08-27] ────────────────────────────
     * 처음엔 CDS `label` 을 통째로 금했더니 제목 줄의 필터 둘이 걸렸다
     * (`ui/StartFilter.tsx`·`ui/BondTypeFilter.tsx`). 화면에서 재 보니
     * **위반이 아니었다**: `compact` 는 라벨을 컨트롤 **안**에 그리고, 그 상자가
     * 정확히 32px 이라 옆의 알약과 맞는다 —
     *
     *     시작점전체⌄  h 32 @89    표로 보기  h 32 @89    백테스트  h 32 @89
     *
     * 규칙 2 가 막으려는 것은 «라벨이 컨트롤 옆에 붙어 시작점이 계단 지는 것»
     * 이고, 컨트롤 안에 든 라벨은 그 병을 만들지 않는다. 그래서 금지는 «라벨이
     * 컨트롤 **밖**에 그려지는 경우» 로 좁힌다.
     *
     * [미결·오너 판단] 그 둘은 `compact` 를 쓰는데 CDS 는 그것을 v11 에서 뺄
     * 예정이다(`ui/IsoDateField.tsx` 주석의 그 사실). 빠지는 날 이 자리는 라벨을
     * 잃으므로 그 전에 `Field` 문법으로 옮길지 정해야 한다. */
    /* `[^>]` 은 줄바꿈도 먹으므로 `s` 플래그가 필요 없다(이 tsconfig 의
       target 에서는 쓸 수도 없다). */
    const CDS_CONTROL = /<(TextInput|Select|DateInput|DatePicker)\b[^>]*?\/?>/g;
    const offenders: string[] = [];
    for (const file of walk(SRC, ['.tsx'])) {
      if (!isOurs(file)) continue;
      const code = stripComments(fs.readFileSync(file, 'utf8'));
      for (const m of code.matchAll(CDS_CONTROL)) {
        if (/\slabel[=\s]/.test(m[0]) && !/\scompact\b/.test(m[0])) {
          offenders.push(path.relative(SRC, file));
        }
      }
    }
    expect([...new Set(offenders)]).toEqual([]);
  });
});

/* ── 규칙 4½ — **격자 열 수는 그리는 칸과 같은 조건으로 센다** [2026-09-29] ───
 *
 * 백테스트 헤드라인 분해(`Decomp`)는 `grid-template-columns:
 * repeat(cols, max-content)` 격자이고, `cols` 를 코드가 **손으로 센다**. 칸을
 * 하나 더 그리면서 그 셈을 안 늘리면 격자가 넘친 칸을 **조용히 다음 줄로
 * 접는다** — 실측 2026-09-29(ASW:KTB:3Y 100억): 풀투파 칸이 붙은 판에서
 * 헤드라인의 조달이 아래 줄로 떨어지고 「국고」가 홈통이 아니라 둘째 열에,
 * 「IRS」가 줄 가운데에 앉았다. 눌러 보면 숫자는 다 있고 **자리만 거짓말**을
 * 한다(이 격자의 쓸모가 «세로로 같은 성분끼리 맞는 것» 이라 그게 전부다).
 *
 * 플레이라이트가 안 잡는 이유: 이 서랍은 북을 실행해야 열리고, 픽셀 가드는
 * 실행 전 화면만 잰다. 그래서 소스에서 잡는다 — 「그리는 조건」과 「세는 조건」이
 * 같은 낱말을 쓰는가.
 */
describe('규칙 4½ — 격자 열 수는 그리는 칸과 같은 조건으로 센다', () => {
  const backtest = () => stripComments(read('backtest', 'BacktestWindow.tsx'));

  it('헤드라인 칸을 켜는 깃발은 전부 열 셈에도 든다', () => {
    const src = backtest();
    const body = src.slice(src.indexOf('function Decomp('),
                           src.indexOf('function LegCells('));
    const cols = body.match(/const cols = ([^;]+);/);
    expect(cols, '`Decomp` 에서 열 셈을 못 찾았어요').not.toBeNull();
    /* 칸을 켜고 끄는 것은 `head.has*` 깃발과 `head.uFund != null` 둘뿐이다. */
    const flags = new Set([...body.matchAll(/head\.(has[A-Z]\w*)/g)].map((m) => m[1]));
    if (/head\.uFund != null/.test(body)) flags.add('uFund');
    expect(flags.size, '헤드라인 칸을 켜는 깃발이 하나도 없어요 — 격자가 바뀌었나요?')
      .toBeGreaterThanOrEqual(3);
    for (const f of flags) {
      expect(cols![1], `칸은 ${f} 로 켜는데 열 셈에 ${f} 가 없어요 — 격자가 접혀요`)
        .toContain(f);
    }
  });

  it('다리 줄의 칸은 **줄이 아니라 헤드라인**이 정한다', () => {
    /* 줄마다 칸 수가 갈리면 그 줄의 다음 성분이 옆 열로 밀린다(국고는 숫자,
       IRS 는 `null` → IRS 의 캐리가 풀투파 열 아래 섰다 — 실측 2026-09-29).
       열이 섰으면 그 줄은 숫자든 em dash 든 한 칸을 낸다. */
    const src = backtest();
    const legs = src.slice(src.indexOf('function LegCells('),
                           src.indexOf('function LegCells(') + 1400);
    const gates = [...legs.matchAll(/if \(([^)]+)\) items\.push/g)].map((m) => m[1].trim());
    expect(gates.length, '다리 칸의 조건을 못 찾았어요').toBeGreaterThanOrEqual(2);
    expect(
      gates.filter((g) => !/^has[A-Z]\w*$/.test(g)),
      '다리 칸을 줄의 값(`row.*`)으로 켜고 있어요 — 줄마다 칸 수가 갈립니다',
    ).toEqual([]);
  });
});
