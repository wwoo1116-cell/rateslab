/* 시뮬 차트에서 **커서가 짚은 값을 읽을 수 있다**.
 *
 * v1 패리티 레인 P1-2 (LANE-v1-parity-2026-08-20.md). v1 `sim/ui/HoverPanel.tsx`.
 *
 * 시뮬은 금리 경로를 설계하고 그 결과를 보는 화면인데, 세 차트 어디에도 커서
 * 리드아웃이 없었다 — "D+37 에 얼마" 를 읽을 길이 없었다. 백테스트의
 * `LinkedCharts` 에는 있었으니 문법은 이미 리포 안에 있었고, 시뮬만 못 받은
 * 것이다.
 *
 * ## 세 차트가 다 받아야 한다
 *
 *   커브형   테너 × 케이스별 금리
 *   시계열형 D+n × 케이스별 Δbp
 *   성분경로 D+n × 성분별 손익
 *
 * 하나만 빠져도 읽는 사람은 "이 화면은 되고 저 화면은 안 되네" 를 배운다.
 *
 * ## 눈과 귀 둘 다
 *
 * 카드는 보는 쪽, `Scrubber` 의 `accessibilityLabel` 은 듣는 쪽이다. 카드만
 * 두면 스크린리더에게 차트가 침묵하고, 라벨만 두면 눈으로 못 읽는다.
 */

import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments } from './_source';

const read = (p: string) => fs.readFileSync(path.join(__dirname, '..', p), 'utf8');

const PREVIEW = 'src/sim/CurvePreview.tsx';
const RESULTS = 'src/sim/ResultsWindow.tsx';

describe('세 차트가 모두 커서를 받는다', () => {
  /* **재는 자리가 옮겨졌다** [2026-08-26 이관]: `enableScrubbing` + `<Scrubber>`
     라는 두 벌 배선이 없어지고 손잡이 하나(`onHoverIndex`)가 됐다. 규칙은
     그대로다 — 세 차트 전부 커서 자리를 알려 줘야 한다. */

  it('커브 미리보기의 두 차트가 커서 자리를 알려준다', () => {
    const src = read(PREVIEW);
    expect(src.match(/onHoverIndex=\{setHover\}/g)?.length ?? 0).toBe(2);
  });

  it('성분 경로 차트도 알려준다', () => {
    expect(read(RESULTS)).toMatch(/onHoverIndex=\{setPathHover\}/);
  });

  it('세 차트가 **부품**을 쓴다 — 각자 만들면 커서 문법이 갈린다', () => {
    expect(read(PREVIEW).match(/<CurveChart|<NumericChart/g)?.length ?? 0).toBe(2);
    expect(read(RESULTS).match(/<NumericChart/g)?.length ?? 0).toBe(1);
  });
});

describe('눈으로 읽는 줄', () => {
  /* 2026-09-21 에 떠 있는 카드에서 **그림 위 고정 줄**로 옮겼다. 명제 셋은
     그대로이고 주어만 바뀌었다 — ①부품을 각자 만들지 않는다 ②자리 산술이
     한 벌이다 ③커서가 쉴 때 빈 줄이 서지 않는다. 카드 시절 ②는 「클램프를
     지난다」였는데, 고정 줄은 **자리를 아예 안 잰다**(그게 그 부품의 요점이라
     클램프가 필요 없다). 그래서 ②는 「칸 폭을 손으로 세지 않는다」로 바뀐다. */

  it('두 화면이 **공용 줄**을 쓴다 — 자기 리드아웃을 만들지 않는다', () => {
    for (const f of [PREVIEW, RESULTS]) {
      expect(read(f), f).toMatch(/from '@\/ui\/ChartReadoutStrip'/);
      expect(read(f), f).toMatch(/<ChartReadoutStrip/);
    }
  });

  it('칸 폭을 손으로 세지 않는다 — `slotChars` 가 잰다', () => {
    /* 이 파일 머리가 적은 그 사고(「스왑롤다운 −12억 3,456만원」이 148px 를
       65px 넘겼다)의 고정 줄 판이다. 손으로 센 글자 수는 서식이 바뀌는 날
       틀리고, 틀리면 오른쪽 칸들이 한 글자씩 밀린다. */
    for (const f of [PREVIEW, RESULTS]) {
      const src = stripComments(read(f));
      expect(src, f).toMatch(/slotChars\(/);
      expect(src, f).not.toMatch(/chars:\s*\d+/);
    }
  });

  it('커서가 쉬어도 줄이 **안 빈다** — 마지막/끝 자리를 읽는다', () => {
    /* 줄이 생겼다 사라지면 그림 높이가 흔들린다(`ChartReadoutStrip` 머리).
       그래서 호버 인덱스가 없을 때 쓰는 대체 자리가 반드시 있어야 한다. */
    for (const f of [PREVIEW, RESULTS]) {
      expect(stripComments(read(f)), f).toMatch(/:\s*[\w.]+\.length\s*-\s*1/);
    }
  });

  it('줄이 기준으로 삼을 상자는 그대로 `.sr-plot` 이다', () => {
    /* 줄은 그림 «밖»이지만 상자는 남는다 — 차트가 그 안에서 높이를 받는다. */
    for (const f of [PREVIEW, RESULTS]) {
      expect(read(f), f).toMatch(/className="sr-plot"/);
    }
    expect(read('src/theme/type.css')).toMatch(/\.sr-plot \{[^}]*position: relative/);
  });
});

describe('귀로 듣는 라벨', () => {
  it('세 차트가 전부 낭독 문장을 받는다 — 기본 문구에 맡기지 않는다', () => {
    /* 캔버스에는 읽을 DOM 이 없어서, 스크러버가 읽어 주던 문장을 `hoverLabel`
       이 받아 `aria-live` 줄에 세운다(`chart/ScaleChart.tsx`). */
    expect(read(PREVIEW)).toMatch(/hoverLabel=\{curveScrubLabel\}/);
    expect(read(PREVIEW)).toMatch(/hoverLabel=\{timeScrubLabel\}/);
    expect(read(RESULTS)).toMatch(/hoverLabel=\{pathScrubLabel\}/);
  });
});

describe('이름이 한 곳에서 나온다', () => {
  it('케이스 이름은 SIM_CASES 가 원천이다 — 칩과 카드가 같은 말을 한다', () => {
    const src = read(PREVIEW);
    expect(src).toMatch(/const CASE_LABEL[\s\S]{0,120}SIM_CASES\.map/);
  });

  it('성분 이름은 워터폴·표와 같은 목록이다', () => {
    /* 세 곳이 각자 목록을 들면 하나만 고쳐지는 날이 온다. [2026-08-25] 선물
       성분이 같은 목록에 합류했다. */
    const src = read(RESULTS);
    expect(src).toMatch(/const PATH_ROWS = \[\.\.\.SWAP_PARTS, \.\.\.BOND_PARTS, \.\.\.FUT_PARTS\]/);
  });

  it('채권·선물 성분은 북에 있을 때만 선다 — 카드에서도', () => {
    /* 판정이 한 함수(drawPath)에 모여 있다 — 세 소비처(선·스크러버·카드)가
       각자 조건을 들면 하나만 고쳐지는 날이 온다. */
    const src = read(RESULTS);
    expect(src).toMatch(/const drawPath = useCallback/);
    expect(src).toMatch(/BOND_SERIES\.has\(key\)\) return paths\.hasBond/);
    expect(src).toMatch(/FUT_SERIES\.has\(key\)\) return paths\.hasFut/);
  });
});
