'use client';

/* 선 하나를 차트에 세우는 일 — 커브·숫자축·시계열이 같이 쓴다 [2026-08-26 이관].
 *
 * 가로축의 «뜻» 은 셋이 다르지만(만기·숫자·날짜) **선을 세우는 규칙은 하나다**:
 * 색은 팔레트에서, 점무늬 면은 프리미티브로, 마지막값 라벨과 가격선은 끈다.
 * 화면마다 이걸 다시 적으면 곧 조금씩 달라진다 — CLAUDE.md 「얼라인」 8.
 */

import { HistogramSeries, LineSeries, LineStyle, LineType } from 'lightweight-charts';
import type {
  HistogramData, IChartApiBase, ISeriesApi, LineData, WhitespaceData,
} from 'lightweight-charts';

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
  /**
   * **점마다** 색을 고른다 — 막대에만 쓴다(`addHistogram`).
   *
   * 선은 한 색이지만 막대는 부호마다 색이 달라야 한다(순매수 빨강 · 순매도
   * 파랑). `HistogramData.color` 가 **데이터 점에 붙는** 성질이라 색을 계열
   * 옵션이 아니라 점에 꽂아야 하고, 그 자리가 여기다. 안 주면 `color` 한 색.
   */
  colorAt?: (v: number, p: LwPalette) => string;
};

/** 세워진 계열 하나.
 *
 *  ★`series` 가 **유니온**이다 [2026-10-19]. 2026-10-19 까지 이 리포에는 계열이
 *  `LineSeries` 한 종류뿐이라 `ISeriesApi<'Line'>` 로 못박혀 있었는데, 투자자별
 *  수급의 일별 순매수가 첫 막대 계열을 들였다. 둘 다 `createPriceLine`·
 *  `setData`·`attachPrimitive` 를 가지므로 부르는 쪽은 안 갈린다. */
export type PlacedLine<H> = {
  series: ISeriesApi<'Line', H> | ISeriesApi<'Histogram', H>;
  area: DottedArea<H> | null;
};

/** 선과 막대가 **같이 쓰는** 캐논 룩.
 *
 * 두 함수가 각자 적으면 곧 갈린다 — `guards/chart-palette.test.ts` ④ 가
 * 「캐논 룩은 한 곳에서만」을 재는 자리가 이것이고, 2026-10-19 에 막대가
 * 들어오면서 처음으로 「한 곳」이 둘이 될 뻔했다.
 */
function baseOptions<H>(line: ChartLine<H>, precision: number) {
  return {
    /* 마지막값 라벨과 가격선은 이 제품의 화면 문법에 없다 — 값은 리드아웃
       스트립과 사실 스트립이 읽어 준다. */
    priceLineVisible: false,
    lastValueVisible: false,
    priceScaleId: line.axis === 'aux' ? 'left' : 'right',
    priceFormat: line.format
      ? { type: 'custom' as const, formatter: line.format, minMove: 10 ** -precision }
      : { type: 'price' as const, precision, minMove: 10 ** -precision },
  };
}

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
    ...baseOptions(line, precision),
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

/** 막대 하나를 세운다 — **이 리포의 첫 히스토그램** [2026-10-19].
 *
 * ## 왜 선이 아니라 막대인가
 *
 * 일별 순매수는 **이산 일별값**이고, FT Visual Vocabulary 의 「change over time,
 * discrete values」가 column 이다. CLAUDE.md 규칙 8 이 차트 유형 판단을 그 외부
 * 표준에 맡기므로, 라인으로 그리면 유형 자체가 오독이다 — 점과 점 사이를 이으면
 * 거래되지 않은 값을 그리는 것이 된다(`references.ts` 머리의 계단 논증과 같다).
 *
 * ## `addLine` 과 **같은 자리에서** 옵션이 난다
 *
 * 캐논 룩(마지막값 라벨 끔·가격선 끔·축 배정·서식)은 두 함수가 **같은 말을**
 * 해야 한다 — `guards/chart-palette.test.ts` ④ 가 「캐논 룩은 한 곳에서만」을
 * 재는 이유다. 그래서 공통을 `baseOptions` 로 뽑았다.
 *
 * ## 색은 **점에** 붙는다
 *
 * `HistogramData.color` 는 계열 옵션이 아니라 데이터 점의 필드다. 부호마다 색이
 * 달라야 하는 것이 막대를 들인 이유의 절반이므로, `colorAt` 이 있으면 점마다
 * 꽂는다. 면(`area`)은 막대에 안 붙인다 — 막대가 이미 면이다.
 */
export function addHistogram<H>(
  chart: IChartApiBase<H>,
  palette: LwPalette,
  line: ChartLine<H>,
  precision: number,
): PlacedLine<H> {
  const base = line.color(palette);
  const series = chart.addSeries(HistogramSeries, {
    color: base,
    ...baseOptions(line, precision),
  });
  /* 점마다 색. `colorAt` 이 없으면 계열 색 그대로라 필드를 안 단다 — 빈 색을
     달면 라이브러리가 그 점을 투명하게 그린다. */
  series.setData(
    line.data.map((d) =>
      line.colorAt && 'value' in d && d.value != null
        ? ({ ...d, color: line.colorAt(d.value, palette) } as HistogramData<H>)
        : d),
  );
  return { series, area: null };
}

export function removeLines<H>(chart: IChartApiBase<H>, placed: readonly PlacedLine<H>[]): void {
  for (const { series, area } of placed) {
    if (area) series.detachPrimitive(area);
    chart.removeSeries(series);
  }
}
