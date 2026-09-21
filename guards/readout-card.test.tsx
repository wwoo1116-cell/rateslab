/* 커서 리드아웃 카드의 계약 [v1 `guards/readout-parity.test.ts` 의 v2 판].
 *
 * 이 카드는 화면에서 **가장 조용히 틀릴 수 있는 자리**다. 틀려도 레이아웃이 안
 * 깨지고, 커서를 대고 있는 동안만 보이며, 숫자가 그럴듯하다. v1 이 이 카드에
 * 가드를 붙인 이유가 그것이고 여기서도 같다.
 *
 * 지키는 것은 셋이다:
 *   ① **어떤 줄이 나오는가** — 오너가 지정한 여섯 [OWNER 2026-08-14]
 *   ② **여기서 반올림하지 않는다** — 서식은 `lib/format` 하나뿐
 *   ③ **카드가 커서를 안 먹는다** — 먹으면 스크러버가 멈추고 카드가 얼어붙는다
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  READOUT_LABEL,
  ReadoutCard,
  ReadoutChange,
  ReadoutLevel,
} from '../src/ui/ReadoutCard';

const SRC = (rel: string) =>
  readFileSync(join(process.cwd(), rel), 'utf8')
    /* 주석 먼저 걷어낸다 — 설명문이 자기 가드에 걸리는 사고를 이 리포에서 네 번
       겪었다. 주석은 아무것도 그리지 않는다. */
    .replace(/\/\*[\s\S]*?\*\//g, '');

describe('리드아웃 카드', () => {
  it('오너가 지정한 여섯 줄을 그 순서로 그린다', () => {
    render(
      <ReadoutCard title="2026-08-13" left={0}>
        <ReadoutLevel k={READOUT_LABEL.level} v={3.84} unit="%" />
        <ReadoutLevel k={READOUT_LABEL.rangeHigh} v={4.2} unit="%" />
        <ReadoutLevel k={READOUT_LABEL.rangeLow} v={2.51} unit="%" />
        <ReadoutLevel k={READOUT_LABEL.rangeAvg} v={3.2548} unit="%" />
        <ReadoutLevel k={READOUT_LABEL.cd91} v={2.93} unit="%" />
        <ReadoutChange k={READOUT_LABEL.dailyChange} v={0.8} unit="%" />
      </ReadoutCard>,
    );

    /* 날짜는 제목이다 — 줄이 아니라 카드가 무엇에 대한 것인지를 말한다. */
    expect(screen.getByText('2026-08-13')).toBeTruthy();

    const wanted = ['레벨', '52주 최고', '52주 최저', '52주 평균', 'CD 91일', '당일 변화'];
    for (const label of wanted) expect(screen.getByText(label), label).toBeTruthy();

    /* 순서까지 본다: 라벨만 맞고 순서가 뒤집히면 읽는 사람은 52주 최고를
       최저로 읽는다. */
    const text = document.body.textContent ?? '';
    const positions = wanted.map((w) => text.indexOf(w));
    expect(positions.every((p) => p >= 0)).toBe(true);
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);
  });

  it('레벨은 `fmtLevel`, 변화는 `fmtDelta` 의 서식 그대로다', () => {
    render(
      <ReadoutCard title="3Y" left={0}>
        <ReadoutLevel k={READOUT_LABEL.level} v={3.84} unit="%" />
        <ReadoutChange k={READOUT_LABEL.dailyChange} v={-1.2} unit="%" />
      </ReadoutCard>,
    );
    // % 레벨은 4자리, bp 변화는 1자리 + 부호(U+2212)
    expect(screen.getByText('3.8400')).toBeTruthy();
    expect(screen.getByText('−1.2')).toBeTruthy();
  });

  it('값이 없으면 em dash 이지 0 이 아니다', () => {
    render(
      <ReadoutCard title="1D" left={0}>
        <ReadoutLevel k={READOUT_LABEL.rangeAvg} v={null} unit="%" />
      </ReadoutCard>,
    );
    expect(screen.getByText('—')).toBeTruthy();
  });

  it('부호 있는 줄만 색을 가진다', () => {
    const { container } = render(
      <ReadoutCard title="5Y" left={0}>
        <ReadoutLevel k={READOUT_LABEL.level} v={3.9} unit="%" />
        <ReadoutChange k={READOUT_LABEL.dailyChange} v={2.5} unit="%" />
      </ReadoutCard>,
    );
    /* 레벨은 방향이 없다 — 색이 붙으면 읽는 사람이 레벨에서 방향을 읽는다. */
    expect(container.querySelectorAll('.sr-up, .sr-down').length).toBe(1);
  });

  it('카드 안에서 반올림하지 않는다', () => {
    expect(SRC('src/ui/ReadoutCard.tsx')).not.toMatch(/toFixed/);
  });
});

describe('카드를 여는 배선', () => {
  const pane = SRC('src/ui/PreviewPane.tsx');

  it('두 차트가 모두 커서 위치를 알려준다', () => {
    /* 커브와 히스토리 둘 다. 하나만 배선하면 pane 이 어느 상태냐에 따라
       "패널이 나왔다 안 나왔다" 하고, 그건 버그로 안 읽히고 착각으로 읽힌다.
       **손잡이 이름이 둘로 갈렸다** [2026-08-26 라이트웨이트 이관]: 히스토리는
       아직 CDS `Scrubber`(`onScrubberPositionChange`), 커브는 캔버스라
       크로스헤어(`onHoverIndex`)다. 재는 것은 이름이 아니라 **둘 다 배선돼
       있는가** 이므로 각각 한 번씩을 확인한다. */
    /* 이제 둘 다 크로스헤어다 [2026-08-26 이관 완료] — 커브도 히스토리도
       같은 손잡이(`onHoverIndex`)로 자리를 알려 준다. 재는 것은 **둘 다
       배선돼 있는가** 다: 하나만 배선하면 pane 이 어느 상태냐에 따라
       "패널이 나왔다 안 나왔다" 하고, 그건 버그로 안 읽히고 착각으로 읽힌다. */
    const cross = pane.match(/onHoverIndex=\{setCurveHover\}/g) ?? [];
    expect(cross.length).toBe(2);
  });

  it('카드가 놓일 상자가 위치 기준을 진다', () => {
    // `.sr-plot` 이 relative 가 아니면 카드는 페이지 기준으로 떠서 차트를 떠난다.
    const plots = pane.match(/className="sr-plot"/g) ?? [];
    expect(plots.length).toBe(2);
    const css = SRC('src/theme/type.css');
    expect(css).toMatch(/\.sr-plot\s*\{[^}]*position:\s*relative/);
  });

  it('카드가 커서를 먹지 않는다', () => {
    /* 이게 풀리면 카드가 스크러버의 mousemove 를 가로채 자기가 가린 값에
       얼어붙는다 — 카드는 보이는데 안 움직이는, 진단하기 나쁜 증상이다. */
    const css = SRC('src/theme/type.css');
    expect(css).toMatch(/\.sr-readout\s*\{[^}]*pointer-events:\s*none/);
  });

  it('CD 91일은 그려진 선이 있을 때만 나온다', () => {
    /* 없는 선의 값을 읽지 않는다 — 범례가 지는 규칙과 같다.

       2026-08-26 부터 명제가 **한 겹 강해졌다**: 기준선을 끌 수 있게 되면서
       (`drawn` = 있고 + 켜져 있음) 카드가 읽는 조건도 «그려진 선» 으로 좁아졌다.
       `refs`(있음)를 읽으면 꺼 둔 선의 값이 카드에 남는다.

       2026-09-21 부터 그 «카드» 는 종목 차트에서 **그림 위의 고정 줄**이다
       (`ui/ChartReadoutStrip.tsx`). 재는 자리만 옮겨지고 명제는 그대로다:
       칸이 서는가는 `refs`, 값을 적는가는 `drawn`. */
    expect(pane).toMatch(/value: drawn\?\.cd \? fmtLevel\(drawn\.cd\[i\], '%'\)/);
    expect(pane).not.toMatch(/value: prefs\.refs\.cd \?/);
  });
});
