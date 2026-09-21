'use client';

/* 선 하나를 차트에 세우는 일 — 커브·숫자축·시계열이 같이 쓴다 [2026-08-26 이관].
 *
 * 가로축의 «뜻» 은 셋이 다르지만(만기·숫자·날짜) **선을 세우는 규칙은 하나다**:
 * 색은 팔레트에서, 점무늬 면은 프리미티브로, 마지막값 라벨과 가격선은 끈다.
 * 화면마다 이걸 다시 적으면 곧 조금씩 달라진다 — CLAUDE.md 「얼라인」 8.
 */

import { LineSeries, LineStyle, LineType } from 'lightweight-charts';
import type { IChartApiBase, ISeriesApi, LineData, WhitespaceData } from 'lightweight-charts';

import { DottedArea, type AreaFill } from './dottedArea';
import type { LwPalette } from './palette';

/** 값 축 둘. 종목은 오른쪽, 배경(기준선)은 왼쪽 [OWNER 2026-08-14]. */
export type LineAxis = 'main' | 'aux';

export type ChartLine<H> = {
  id: string;
  /** 자리와 값의 짝. `null` 값은 **빼지 말고** whitespace 로 넣어야 선이 끊긴다. */
  data: (LineData<H> | WhitespaceData<H>)[];
  color: (p: LwPalette) => string;
  width?: 1 | 2;
  dash?: boolean;
  /**
   * 각진 계단으로 그린다 — CDS `Line curve="stepAfter"` 의 자리.
   *
   * 기준금리가 이것을 쓴다: 정책금리는 평평하다가 뛴다. 두 결정 사이를 사선으로
   * 이으면 시행된 적 없는 금리를, 시행된 적 없는 날에 그리는 것이다
   * (`chart/references.ts` 머리). 이관 때 이 손잡이가 없어서 두 곳
   * (Main 미리보기·백테스트)이 사선이 되어 있었다 [2026-08-27 수리].
   */
  step?: boolean;
  /** 선 아래 면. `dots` 는 캐논의 `areaType="dotted"`, `solid` 는 손익 차트의
   *  채운 면. 주선에만 준다(참조선까지 채우면 어느 것이 잉크인지 안 보인다). */
  area?: AreaFill;
  /** 면의 색. 안 주면 선 색 그대로 — `solid` 는 보통 흐린 색을 따로 준다. */
  areaColor?: (p: LwPalette) => string;
  axis?: LineAxis;
  /**
   * 그 축의 눈금 글자. **계열마다** 주는 이유: 값 축이 둘일 때
   * (`localization.priceFormatter`) 하나로는 둘을 못 나눈다 — bp 축과 % 축이
   * 같은 서식으로 찍힌다. 가격축 라벨은 거기 붙은 계열의 서식을 따른다.
   */
  format?: (v: number) => string;
  /** 커서가 이 선 위에 **구슬**을 띄우는가. 기본은 안 띄운다 — 근거는
   *  `addLine` 의 `crosshairMarkerVisible` 주석. 주선 하나만 켠다. */
  beacon?: boolean;
};

export type PlacedLine<H> = {
  series: ISeriesApi<'Line', H>;
  area: DottedArea<H> | null;
};

/** 선 하나를 세운다. 지울 때는 `removeLines` 를 쓴다. */
export function addLine<H>(
  chart: IChartApiBase<H>,
  palette: LwPalette,
  line: ChartLine<H>,
  precision: number,
): PlacedLine<H> {
  const series = chart.addSeries(LineSeries, {
    color: line.color(palette),
    lineWidth: line.width ?? 2,
    lineStyle: line.dash ? LineStyle.Dotted : LineStyle.Solid,
    lineType: line.step ? LineType.WithSteps : LineType.Simple,
    /* 마지막값 라벨과 가격선은 이 제품의 화면 문법에 없다 — 값은 리드아웃
       스트립과 사실 스트립이 읽어 준다. */
    priceLineVisible: false,
    lastValueVisible: false,
    /**
     * 커서 구슬은 **주선에만** [2026-09-21].
     *
     * 라이브러리 기본이 `true` 라(`typings.d.ts:501`) 그냥 두면 커서 밑에
     * 계열 수만큼 점이 뜬다 — 종목 미리보기는 종목 + CD91 + 기준금리 + MA 다섯
     * 이라 **최대 여덟 개**다. 그러면 커서가 무엇을 읽고 있는지 그림이 말해
     * 주지 못한다.
     *
     * 이 판단은 CDS 판에 이미 있었다. 그때는 `Scrubber seriesIds` 로 짚을 계열을
     * 명시했고(「기본은 전부라 유령 구슬」 — `lab/scenario/ModelChart.tsx:16`),
     * 캔버스로 옮기면서 그 손잡이가 없어진 자리다. 다른 계열의 값은 그림이
     * 아니라 리드아웃 스트립이 줄로 적는다.
     */
    crosshairMarkerVisible: line.beacon ?? false,
    priceScaleId: line.axis === 'aux' ? 'left' : 'right',
    priceFormat: line.format
      ? { type: 'custom', formatter: line.format, minMove: 10 ** -precision }
      : { type: 'price', precision, minMove: 10 ** -precision },
  });
  series.setData(line.data);

  let area: DottedArea<H> | null = null;
  if (line.area) {
    area = new DottedArea<H>();
    series.attachPrimitive(area);
    /* 면은 **값이 있는 점만** 잇는다 — 빈 점은 좌표 변환이 `null` 을 주고
       거기서 면이 끊긴다(`dottedArea.ts` 의 그 가드). */
    area.update(
      line.data
        .filter((d): d is LineData<H> => 'value' in d && d.value != null)
        .map((d) => ({ time: d.time, value: d.value })),
      line.areaColor ? line.areaColor(palette) : line.color(palette),
      line.area,
    );
  }
  return { series, area };
}

export function removeLines<H>(chart: IChartApiBase<H>, placed: readonly PlacedLine<H>[]): void {
  for (const { series, area } of placed) {
    if (area) series.detachPrimitive(area);
    chart.removeSeries(series);
  }
}
