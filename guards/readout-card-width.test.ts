/* 리드아웃 카드의 폭과 자리 — **호출부가 아무것도 몰라도 맞아야 한다**.
 *
 * v1 패리티 레인 검증 라운드에서 나온 것(2026-08-20).
 *
 * ## 왜 생겼나
 *
 * 카드는 **고정 폭 148** 이었고, 호출부가 자기 최장 줄을 계산해서 `width` 로
 * 넘겨야 했다. 두 명이 연속으로 그 함정에 빠졌다:
 *
 *   RvScatter      "버퍼 +10.8bp (1.2σ)" 가 삐져나감 → 오너 지적 후 200 [08-19]
 *   ResultsWindow  "스왑롤다운 −12억 3,456만원" ≈ 213px → 148 에서 65px 초과 [08-20]
 *
 * 두 번째는 **첫 번째의 교훈이 코드 주석에 있었는데도** 났다. 호출부가 알아야만
 * 맞는 기본값은 기본값이 아니라 함정이다.
 *
 * 폭 계산이 어디로 갔는지 세는 것이 이 가드다 — CSS 가 `max-content` 로 잡고,
 * 아무도 픽셀을 다시 세지 않는다.
 *
 * ## 폭 모델 (실측 보정)
 *
 * 한글 14px ≈ 14px · 등폭 숫자 14px = 8.60px(`columns.ts` 실측 chPx) ·
 * 줄 gap 8px · 좌우 패딩 8+8. RV 의 최장 줄로 검산하면 ≈196px 이고 그때 고른
 * 값이 200 이었다 — 모델이 그 실측과 맞는다.
 */

import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { READOUT_CARD_MAX, READOUT_X_VAR, readoutLeft } from '../src/ui/ReadoutCard';

import { stripComments, walk } from './_source';

const ROOT = path.resolve(__dirname, '..');
const read = (p: string) => fs.readFileSync(path.join(ROOT, p), 'utf8');

/** 카드를 띄우는 모든 표면. 새 표면이 생기면 여기 추가되어야 한다.
 *
 * **2026-09-21 에 여섯이 빠졌다.** 먼저 종목 차트(`ui/PreviewPane.tsx`)와
 * 백테스트(`backtest/LinkedCharts.tsx`)가, 이어서 시뮬 둘(`sim/CurvePreview`·
 * `sim/ResultsWindow`) · RV 이력(`rv/RvPage`) · MR 밴드(`mr/BandChart`) ·
 * 연구실(`lab/scenario/ModelChart`)이 떠 있는 카드에서 **그림 위의 고정 줄**로
 * 옮겼다 — 카드가 그림을 가린다는 트레이더 보고 때문이고, 경위는
 * `ui/ChartReadoutStrip.tsx` 머리글에 있다. 옮긴 표면은
 * `guards/chart-readout-strip.test.ts` 가 다른 계약으로 잰다.
 *
 * 카드 자체는 은퇴하지 않았다 — 산점도(축이 둘이라 「커서 밑의 한 날」이 없다) ·
 * 3D 표면 · 터미널 · MR 두 창이 아직 쓴다. 표면마다 폭이 다르므로 은퇴도
 * 표면마다 따로 본다. */
const SURFACES = [
  'src/rv/RvScatter.tsx',
];

describe('폭은 내용이 정한다 — 호출부가 세지 않는다', () => {
  it('CSS 가 max-content 로 잡고 상한을 둔다', () => {
    const css = read('src/theme/type.css');
    const block = css.slice(css.indexOf('.sr-readout {'), css.indexOf('.sr-readout-rows'));
    expect(block).toMatch(/width: max-content/);
    expect(block).toMatch(/max-width: \d+px/);
  });

  it('어느 표면도 카드에 픽셀 폭을 넘기지 않는다', () => {
    /* 이 한 줄이 되살아나는 순간 함정도 같이 돌아온다. */
    const offenders = SURFACES.filter((f) => /<ReadoutCard[\s\S]{0,200}?width=\{/.test(read(f)));
    expect(offenders).toEqual([]);
  });

  it('표면별 폭 상수가 없다', () => {
    const offenders: string[] = [];
    for (const f of SURFACES) {
      const src = stripComments(read(f));
      for (const m of src.matchAll(/const \w*CARD_W\w*\s*=\s*\d+/g)) offenders.push(`${f}: ${m[0]}`);
    }
    expect(offenders).toEqual([]);
  });
});

describe('클램프는 한 벌이다', () => {
  it('모든 표면이 공용 클램프를 지난다 — 자기 산술을 쓰지 않는다', () => {
    /* 2026-08-20 이전에는 셋(LinkedCharts · RvPage · RvScatter)이 각자 같은
     * 식을 복제하고 있었다. 복제는 언젠가 갈린다.
     *
     * 표면은 둘 중 하나를 지난다: 커서를 따라가면 `placeReadout`(상자에 적는다),
     * 데이터 좌표에 붙으면 `readoutLeft`(직접 클램프). 어느 쪽이든 식은 한 벌이다. */
    const missing = SURFACES.filter(
      (f) => !read(f).includes('placeReadout(') && !read(f).includes('readoutLeft('),
    );
    expect(missing).toEqual([]);
  });

  it('그 한 벌이 실제로 같은 식이다 — placeReadout 이 readoutLeft 를 부른다', () => {
    expect(read('src/ui/ReadoutCard.tsx')).toMatch(/setProperty\(READOUT_X_VAR[\s\S]{0,60}readoutLeft\(/);
  });

  it('손으로 쓴 클램프 식이 남아 있지 않다', () => {
    const offenders: string[] = [];
    for (const f of SURFACES) {
      const src = stripComments(read(f));
      // `Math.min(Math.max(0, x + 12), …)` 계열
      if (/Math\.min\(Math\.max\(0, x \+ 12\)/.test(src)) offenders.push(f);
      if (/boxW - \w+ - 8/.test(src)) offenders.push(f);
    }
    expect([...new Set(offenders)]).toEqual([]);
  });

  it('카드는 상자 안에 머문다 — 폭과 무관하게', () => {
    const boxW = 400;
    for (const x of [-50, 0, 100, 399, 900]) {
      const left = readoutLeft(x, boxW);
      expect(left).toBeGreaterThanOrEqual(0);
      expect(left + READOUT_CARD_MAX).toBeLessThanOrEqual(boxW);
    }
  });

  it('상자가 카드보다 좁으면 0 에 붙는다 — 음수로 나가지 않는다', () => {
    expect(readoutLeft(100, 100)).toBe(0);
    expect(readoutLeft(0, 10)).toBe(0);
  });

  it('커서 오른쪽 12px 에 선다 — 커서를 덮지 않는다', () => {
    expect(readoutLeft(40, 1000)).toBe(52);
  });
});

describe('자리는 상태가 아니다 — 픽셀마다 리렌더하지 않는다', () => {
  /* `rerender-use-ref-transient-values` (2026-08-20 검증 라운드). 자리는
   * 픽셀마다 바뀌는데 CSS 속성 하나만 먹인다 — 상태로 두면 마우스가 움직일
   * 때마다 컴포넌트 전체가 다시 그려진다. 인덱스는 상태가 맞다(카드의 **내용**이
   * 그걸 읽는다). 둘을 갈라 두는 것이 이 절의 전부다. */

  /** **2026-09-21 이후 커서를 «따라다니는» 표면은 하나도 없다.** 고정 줄로 다
   *  옮겼고(`ui/ChartReadoutStrip`), 남은 카드 하나(RvScatter)는 시간축이 없어
   *  인덱스가 아니라 **자료 좌표**에서 자리를 낸다.
   *
   *  목록을 손으로 들지 않는다 — 손목록은 새 표면이 생겨도 조용히 초록이다.
   *  대신 **src 전체**를 훑는다. */
  const withCard = () =>
    walk(path.join(ROOT, 'src'), ['.tsx'])
      .filter((f) => stripComments(fs.readFileSync(f, 'utf8')).includes('<ReadoutCard'))
      .map((f) => path.relative(ROOT, f).split(path.sep).join('/'));

  it('카드를 띄우는 표면은 공용 클램프 **둘 중 하나**를 지난다', () => {
    /* `placeReadout` 은 상자의 CSS 변수에 적고(커서를 따라가는 판),
       `readoutLeft` 는 그 안에서 쓰는 산술을 직접 부른다(자료 좌표에 붙는 판).
       어느 쪽이든 **식은 한 벌**이고, 손으로 다시 쓰는 순간 갈린다 — 이 파일
       머리가 적은 그 사고가 두 번 났다. */
    const offenders = withCard().filter((f) => {
      const src = stripComments(read(f));
      return !src.includes('placeReadout(') && !src.includes('readoutLeft(');
    });
    expect(offenders).toEqual([]);
  });

  it('지금 카드를 쓰는 표면은 산점도 하나뿐이다 — 은퇴 진도를 여기서 센다', () => {
    /* 수를 박아 두면 다음 사람이 「어디까지 옮겼나」를 이 줄에서 읽는다. 또
       옮기면 이 줄이 빨개지고, 그때 줄을 고치는 것이 곧 기록이 된다.

       산점도가 마지막인 데는 이유가 있다: 고정 줄의 계약은 「한 날 + 그날의
       값들」인데 산점도는 축이 둘이라 **커서 밑의 «한 날»이 없다**. 옮기려면
       줄의 계약부터 바꿔야 하고, 그건 이 이관의 범위가 아니다. */
    expect(withCard()).toEqual(['src/rv/RvScatter.tsx']);
  });

  it('CSS 가 그 변수를 읽는다', () => {
    const css = read('src/theme/type.css');
    const block = css.slice(css.indexOf('.sr-readout {'), css.indexOf('.sr-readout-rows'));
    expect(block).toMatch(/left: var\(--sr-readout-x/);
  });

  it('변수 이름이 한 곳에서 나온다 — 문자열을 두 벌 적지 않는다', () => {
    expect(READOUT_X_VAR).toBe('--sr-readout-x');
    const helper = read('src/ui/ReadoutCard.tsx');
    expect(helper).toMatch(/setProperty\(READOUT_X_VAR/);
  });

  it('RvScatter 만 left 를 넘긴다 — 커서가 아니라 데이터 좌표에 붙기 때문', () => {
    /* 강조된 점의 카드는 hover 가 없어도 서야 하므로 x 가 진짜 상태다.
     * 예외를 목록으로 고정해 둔다 — 다른 표면이 슬그머니 따라 하는 것을 막는다. */
    const passers = SURFACES.filter((f) => /<ReadoutCard[\s\S]{0,200}?left=\{/.test(read(f)));
    expect(passers).toEqual(['src/rv/RvScatter.tsx']);
  });
});

describe('상한이 실제로 넉넉한지 — 실측 보정 모델', () => {
  /** 한글 14px, 등폭 14px 숫자 8.60px(`columns.ts` 실측). */
  const w = (s: string) =>
    [...s].reduce((acc, ch) => acc + (/[가-힣]/.test(ch) ? 14 : 8.6), 0);
  /** 카드가 한 줄을 담는 데 필요한 폭 = 라벨 + gap 8 + 값 + 좌우 패딩 16. */
  const need = (label: string, value: string) => w(label) + 8 + w(value) + 16;

  it('모델이 RV 의 실측(200) 언저리에 든다 — ±15%', () => {
    /* 그 값을 고를 때 근거였던 최장 줄. 모델이 이걸 못 맞히면 아래 판정도 못
     * 믿는다. 밴드가 넓은 이유는 모델이 **근사**여서다: 공백과 `+ - .` 을
     * 숫자 폭(8.6)으로 세는데 실제로는 그보다 좁아, 기호가 많은 줄에서 6% 쯤
     * 과대평가한다(이 줄에서 212 vs 실측 200). 과대평가는 안전한 방향이다 —
     * 상한이 필요보다 넉넉해질 뿐 모자라지 않는다. */
    const est = need('캐리 + 롤', '+16.7 + -4.8bp');
    expect(est).toBeGreaterThan(200 * 0.85);
    expect(est).toBeLessThan(200 * 1.15);
  });

  it('시뮬 성분의 최장 줄이 옛 고정 폭 148 을 넘는다 — 이 가드의 계기', () => {
    expect(need('스왑롤다운', '−12억 3,456만원')).toBeGreaterThan(148);
  });

  it('상한이 그 줄을 담는다', () => {
    expect(need('스왑롤다운', '−12억 3,456만원')).toBeLessThanOrEqual(READOUT_CARD_MAX);
  });
});
