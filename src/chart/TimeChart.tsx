'use client';

/* 시계열 한 장 — 아홉 화면이 같이 쓴다 [2026-08-26 이관].
 *
 * 쓰는 곳: Main 미리보기 · 백테스트(짝 차트 둘 포함) · 밴드 · 전략 실험 창 셋 ·
 * rv 추이.
 *
 * ── 왜 커브·숫자축과 몸통이 다른가 ─────────────────────────────────────────
 * 저쪽은 축의 «뜻» 을 우리가 정해야 해서 `IHorzScaleBehavior` 를 직접 짰다.
 * 날짜 축은 다르다 — 라이브러리가 **월·년 경계에 더 큰 무게를 주는** 눈금 규칙을
 * 이미 갖고 있고, 그건 우리가 다시 만들 이유가 없는 좋은 규칙이다.
 *
 * 그리고 걱정할 것이 하나 없다: 라이브러리의 가로축은 **인덱스 간격**이라
 * 주말·휴일이 자리를 차지하지 않는다. CDS 의 범주 축과 같은 간격이 그대로 나온다.
 * 선을 세우는 일은 `series.ts` 가 커브·숫자축과 **공유한다**.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { LineStyle, createSeriesMarkers } from 'lightweight-charts';
import type {
  ISeriesApi,
  ISeriesMarkersPluginApi,
  LineData,
  Time,
  WhitespaceData,
} from 'lightweight-charts';

import type { AreaFill } from './dottedArea';
import type { LwPalette } from './palette';
import { VerticalLines } from './verticalLines';
import type { ScalePriceLine } from './ScaleChart';
import { addLine, removeLines, type LineAxis, type PlacedLine } from './series';
import {
  sameLines,
  sameMarkLines,
  sameMarkers,
  samePriceLines,
  sameStrings,
  useStable,
} from './stable';
import { CROSSHAIR_LABEL_MIN_W, useLwChart } from './useLwChart';

export type TimeLine = {
  id: string;
  /** `dates` 와 **같은 길이**. `null` 은 그날 값이 없다는 뜻이고 선이 끊긴다. */
  values: readonly (number | null)[];
  color: (p: LwPalette) => string;
  width?: 1 | 2;
  dash?: boolean;
  /** 각진 계단 — 기준금리가 쓴다(`series.ts::ChartLine.step`). */
  step?: boolean;
  /** 선 아래 면 — 캐논은 점무늬. 주선에만. */
  area?: AreaFill;
  areaColor?: (p: LwPalette) => string;
  /** 종목은 오른쪽(`main`), 기준선은 왼쪽(`aux`) [OWNER 2026-08-14]. */
  axis?: LineAxis;
  /** 그 축의 눈금 글자. 축마다 다르므로 계열이 진다(`series.ts` 주석). */
  format?: (v: number) => string;
  /** 커서 구슬 — **주선 하나만** 켠다(`series.ts::addLine` 의 그 주석). */
  beacon?: boolean;
};

/** 세로선의 결 — 색을 직접 주지 않고 **뜻**을 준다(`theme/tint.ts` 의 규율).
 *  `muted` 가 기본이고, `ink` 는 지금 펴 놓은 것, `up`·`down` 은 방향색이다. */
export type MarkLineTone = 'muted' | 'ink' | 'up' | 'down';

/** 보이는 구간의 고·저 같은 표시점. CDS `Point` 의 자리. */
export type TimeMarker = {
  /** `dates` 의 순번. */
  index: number;
  color: (p: LwPalette) => string;
};

export function TimeChart({
  dates,
  lines,
  markers,
  priceLines,
  markLines,
  syncIndex,
  hideTimeAxis,
  scaleWidth,
  onScaleWidth,
  height,
  onHoverIndex,
  precision = 2,
  accessibilityLabel,
  hoverLabel,
}: {
  /** ISO 날짜들, **오름차순**. */
  dates: readonly string[];
  lines: readonly TimeLine[];
  markers?: readonly TimeMarker[];
  /** 가로로 눕는 상수선 — 손익 차트의 0선. */
  priceLines?: readonly ScalePriceLine[];
  /** 세로로 서는 선들 — «그 날 들어갔다» 같은 **사실**을 긋는다.
   *  CDS `ReferenceLine dataX={…} label={…}` 의 자리. 겹침 회피(근접 마크
   *  합치기)는 **호출부가** 한다 — 라벨을 아는 쪽이 거기다. */
  markLines?: readonly { index: number; label?: string; tone?: MarkLineTone }[];
  /**
   * 바깥에서 짚어 주는 자리 — **짝 차트**가 쓴다(백테스트의 위/아래 차트).
   *
   * CDS 판은 `<ReferenceLine dataX={hover.i}>` 로 세로선을 그렸다. 여기서는
   * 라이브러리의 크로스헤어를 그 자리에 세운다 — 커서가 실제로 그 위에 있을
   * 때와 **같은 그림**이라 두 차트가 한 커서를 공유하는 것으로 읽힌다.
   */
  syncIndex?: number | null;
  /**
   * 가로축(날짜 줄)을 감춘다 — **위아래로 쌓인 차트의 위쪽**이 쓴다.
   *
   * CDS 판의 백테스트는 아래 손익 차트에 `<XAxis>` 를 아예 안 뒀고 그 자리에
   * «x 라벨은 위 차트가 진다 — 두 벌이면 같은 날짜가 두 줄로 선다» 라고 적어
   * 두었다. 이관하면서 그 손잡이가 없어져 날짜가 두 줄이 됐다(실측
   * 2026-08-27 백테스트: 같은 세 날짜가 y≈396 과 y≈523 에 두 번).
   */
  hideTimeAxis?: boolean;
  /** 값 축이 **최소한** 차지할 폭. 쌓인 차트들을 같은 폭으로 맞춘다
   *  (`useStackedScales`). */
  scaleWidth?: number;
  /** 이 차트의 값 축이 실제로 먹은 폭 — 쌓인 형제끼리 최대값을 나눈다. */
  onScaleWidth?: (w: number) => void;
  height?: number;
  onHoverIndex?: (i: number | null) => void;
  precision?: number;
  accessibilityLabel: string;
  hoverLabel?: (i: number) => string;
}) {
  const [el, setEl] = useState<HTMLDivElement | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const handle = useLwChart<Time>('time', el);

  /* ── 프롭은 **내용**으로 본다 [2026-08-27] ───────────────────────────────────
     호출부는 `dates={points.map((p) => p.t)}` 처럼 매 렌더 새 배열을 줘도 된다.
     참조로 비교하던 시절에는 그것이 계열 전체의 파괴·재생성을 불렀고 화면이
     번쩍였다 — 경위와 계측은 `chart/stable.ts` 머리에. */
  const sDates = useStable(dates, sameStrings);
  const sLines = useStable(lines, sameLines);
  const sMarkers = useStable(markers, sameMarkers);
  const sPriceLines = useStable(priceLines, samePriceLines);
  const sMarkLines = useStable(markLines, sameMarkLines);

  /* 색·서식은 «모양» 이 아니라 안정화 대상이 아니다. 계열을 다시 세우는
     순간에는 **그때의 최신 것**이 쓰여야 하므로 ref 로 읽는다. */
  const latest = useRef({ lines, markers, priceLines, onHoverIndex, onScaleWidth });
  latest.current = { lines, markers, priceLines, onHoverIndex, onScaleWidth };

  /** 날짜 -> 순번. 크로스헤어가 주는 것은 날짜뿐이다. */
  const indexOf = useMemo(() => new Map(sDates.map((d, i) => [d, i])), [sDates]);

  /* 콜백도 ref 로 읽는다 — 인라인 화살표를 넘기는 호출부가 있어서(전략 실험
     창 셋), 의존성에 두면 크로스헤어 구독이 렌더마다 붙었다 떨어진다. */
  const notify = useCallback((i: number | null) => {
    setHover(i);
    latest.current.onHoverIndex?.(i);
  }, []);

  /** 왼쪽 축은 **쓸 때만** 선다 — 빈 축이 서면 플롯이 그만큼 좁아진다. */
  const hasAux = useMemo(() => lines.some((l) => l.axis === 'aux'), [lines]);
  useEffect(() => {
    if (!handle) return;
    handle.chart.applyOptions({
      leftPriceScale: {
        visible: hasAux,
        borderVisible: false,
        scaleMargins: { top: 0.08, bottom: 0.04 },
        /* 눈금 글자만 한 칸 더 흐리게 — CDS 판의
           `styles={{ tickLabel: { opacity: 0.65 } }}` 자리다. 이 축은 종목의
           축이 아니라 **배경의 축**이고(기준선 둘이 쓴다), 읽는 사람이 어느
           숫자가 어느 선의 것인지 헷갈리면 안 된다. 이관 때 빠져서 두 축의
           잉크가 같았다 [2026-08-27 수리]. */
        textColor: handle.palette.dim(handle.palette.fgMuted, 65),
      },
    });
  }, [handle, hasAux]);

  /* ── 쌓인 차트의 «픽셀 정렬» [2026-08-27] ───────────────────────────────────
     값 축의 폭은 **그 축 라벨의 폭**으로 정해진다. 백테스트의 두 차트는
     `3.245`(56px)와 `+20원`(50px)이라 플롯이 914 대 920 으로 어긋났다 — 그
     파일의 계약이 «픽셀까지 같다» 인데도. `minimumWidth` 는 라이브러리가 바로
     이 용도로 둔 옵션이다("multiple charts positioned in a vertical stack each
     have an identical price scale width"). 형제 중 가장 넓은 폭을 다 같이 쓴다.

     폭을 재는 것은 `applyOptions` **뒤**여야 하고, 그리기 한 프레임 뒤에야
     확정되므로 rAF 로 한 번 더 잰다. 값이 커지기만 하므로(형제의 최대) 되먹임
     없이 한두 프레임에 수렴한다. */
  useEffect(() => {
    if (!handle) return;
    const { chart } = handle;
    chart.applyOptions({
      /* 바닥이 **둘**이고 큰 쪽이 이긴다 [2026-09-21]. 하나는 형제 차트와 폭을
         맞추는 것(`scaleWidth`), 다른 하나는 크로스헤어 라벨이 잘리지 않게 하는
         것(`CROSSHAIR_LABEL_MIN_W` — 그 수의 유래는 그 상수의 머리글).

         둘을 따로 `applyOptions` 하면 **나중 것이 앞 것을 덮는다** — 같은 키에
         쓰는 것이라 「합쳐진다」가 아니다. 한 줄에서 `Math.max` 로 합치는 이유가
         그것이고, 이 리포가 쌓인 차트에서 이미 한 번 겪은 어긋남이다. */
      rightPriceScale: {
        minimumWidth: Math.max(scaleWidth ?? 0, CROSSHAIR_LABEL_MIN_W),
      },
      timeScale: { visible: !hideTimeAxis },
    });
    const report = () => latest.current.onScaleWidth?.(chart.priceScale('right').width());
    report();
    const id = requestAnimationFrame(report);
    return () => cancelAnimationFrame(id);
  }, [handle, scaleWidth, hideTimeAxis, sDates, sLines]);

  const markerApi = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  /** 크로스헤어를 세울 계열 — 첫 줄(주선)이다. */
  const anchor = useRef<ISeriesApi<'Line', Time> | null>(null);
  const vlines = useRef<VerticalLines<Time> | null>(null);
  /** 지금 서 있는 계열들 — 겉모습 이펙트가 여기로 색을 갈아입힌다. */
  const placedRef = useRef<PlacedLine<Time>[] | null>(null);
  /** 계열에 **실제로 입혀진** 색. 이것과 다를 때만 다시 입힌다. */
  const inkRef = useRef<string[]>([]);
  /** 짝 차트가 세운 커서가 있는가 — 없는데 지우면 **내 커서**가 지워진다. */
  const syncedRef = useRef(false);

  /* ── 이펙트가 둘인 이유 ─────────────────────────────────────────────────────
     아래는 **구조**다: 계열을 세우고 부순다. 그 아래 «겉모습» 이펙트는 색만
     갈아입힌다. 가른 이유는 색이 바뀌었다고 계열을 부수면 크로스헤어가 끊기고
     화면이 번쩍이기 때문이다(MA 색 취향을 바꾸면 값은 그대로인데 색만 바뀐다). */
  useEffect(() => {
    if (!handle || sDates.length === 0) return;
    const { chart, palette, alive } = handle;
    /* 함수는 최신 것 — `sLines` 와 모양이 같으므로 순번이 맞는다. */
    const src = latest.current;

    const placed: PlacedLine<Time>[] = sLines.map((ln, i) =>
      addLine(
        chart,
        palette,
        {
          id: ln.id,
          color: src.lines[i]?.color ?? ln.color,
          width: ln.width,
          dash: ln.dash,
          step: ln.step,
          area: ln.area,
          areaColor: src.lines[i]?.areaColor ?? ln.areaColor,
          axis: ln.axis,
          format: src.lines[i]?.format ?? ln.format,
          /* 아무도 안 켰으면 **첫 줄**이 켠 것으로 친다. 이 리포의 모든 시계열
             차트에서 첫 줄이 주선이고(`anchor` 도 그 규약을 쓴다), 그래야 아홉
             호출부가 한 줄씩 더 적지 않아도 구슬이 하나 남는다. */
          beacon: ln.beacon ?? (sLines.some((l) => l.beacon) ? false : i === 0),
          data: sDates.map((t, k) => {
            const v = ln.values[k];
            return (v == null ? { time: t as Time } : { time: t as Time, value: v }) as
              | LineData<Time>
              | WhitespaceData<Time>;
          }),
        },
        precision,
      ),
    );
    placedRef.current = placed;
    /* 방금 입힌 색을 적어 둔다 — 아래 겉모습 이펙트가 곧바로 다시 입히지
       않도록. */
    inkRef.current = sLines.map((ln, i) => (src.lines[i]?.color ?? ln.color)(palette));

    /* 고·저 표시점 — CDS `Point` 자리. 주선(첫 계열)에 매단다. */
    if (sMarkers?.length && placed[0]) {
      markerApi.current = createSeriesMarkers(
        placed[0].series,
        sMarkers
          .filter((m) => sDates[m.index] != null)
          .map((m, i) => ({
            time: sDates[m.index] as Time,
            position: 'inBar' as const,
            shape: 'circle' as const,
            color: (src.markers?.[i]?.color ?? m.color)(palette),
            size: 0.6,
          })),
      );
    }

    /* 가로 상수선. 첫 계열에 매단다 — 값 축이 하나뿐이라 어디 붙어도 같다. */
    (sPriceLines ?? []).forEach((pl, i) => {
      placed[0]?.series.createPriceLine({
        price: pl.value,
        color: (src.priceLines?.[i]?.color ?? pl.color)(palette),
        lineWidth: 1,
        lineStyle: pl.dash ? LineStyle.Dotted : LineStyle.Solid,
        axisLabelVisible: false,
        title: '',
      });
    });

    anchor.current = placed[0]?.series ?? null;

    if (sMarkLines?.length && placed[0]) {
      const v = new VerticalLines<Time>();
      placed[0].series.attachPrimitive(v);
      const tone: Record<MarkLineTone, string> = {
        muted: palette.fgMuted,
        ink: palette.fg,
        up: palette.up,
        down: palette.down,
      };
      v.update(
        sMarkLines
          .filter((m) => sDates[m.index] != null)
          .map((m) => ({
            time: sDates[m.index] as Time,
            label: m.label,
            color: m.tone ? tone[m.tone] : undefined,
          })),
        palette.fgMuted,
        palette.fontFamily,
      );
      vlines.current = v;
    }

    chart.timeScale().fitContent();

    return () => {
      /* 차트가 이미 사라졌으면 지울 것이 없다 — `LwHandle.alive` 주석. */
      markerApi.current = null;
      anchor.current = null;
      placedRef.current = null;
      if (alive.current && vlines.current && placed[0]) {
        placed[0].series.detachPrimitive(vlines.current);
      }
      vlines.current = null;
      if (alive.current) removeLines(chart, placed);
    };
  }, [handle, sDates, sLines, sMarkers, sPriceLines, sMarkLines, precision]);

  /* ── 겉모습 — 계열을 부수지 않고 색만 갈아입힌다 ───────────────────────────
     값은 그대로인데 색만 바뀌는 자리가 실제로 있다(MA 색 취향). 푼 색이 정말
     달라졌을 때만 `applyOptions` 를 부른다 — 인라인 화살표를 주는 호출부가
     있어서, 함수 참조가 바뀐 것만으로는 아무 일도 하지 않는다. */
  useEffect(() => {
    const placed = placedRef.current;
    if (!handle || !placed) return;
    const { palette } = handle;
    const ink = inkRef.current;
    lines.forEach((ln, i) => {
      const p = placed[i];
      if (!p) return;
      const stroke = ln.color(palette);
      if (ink[i] !== stroke) {
        ink[i] = stroke;
        p.series.applyOptions({ color: stroke });
      }
      if (p.area) p.area.setColor(ln.areaColor ? ln.areaColor(palette) : stroke);
    });
  }, [handle, lines]);

  /* 짝 차트가 짚어 준 자리. 값은 주선의 그날 값을 쓴다 — 크로스헤어는 가로
     자리만 보이면 되지만 API 가 값을 요구한다. */
  useEffect(() => {
    if (!handle) return;
    const { chart } = handle;
    const s = anchor.current;
    const t = syncIndex == null ? null : sDates[syncIndex];
    const v = syncIndex == null ? null : (sLines[0]?.values[syncIndex] ?? null);
    if (s && t != null && v != null) {
      syncedRef.current = true;
      chart.setCrosshairPosition(v, t as Time, s);
    } else if (syncedRef.current) {
      /* **세운 적이 있을 때만 지운다** [실측 2026-08-27]. 그냥 지우면 커서가
         이 차트 위에 있을 때도 라이브러리가 크로스헤어를 내리고, 그 순간
         빈 이벤트가 날아와 리드아웃 카드가 사라진다. 짝을 안 쓰는 화면
         (Main 미리보기는 `syncIndex` 를 아예 안 넘긴다)에서는 렌더마다
         그 일이 났다 — 번쩍거림의 두 번째 뿌리였다. */
      syncedRef.current = false;
      chart.clearCrosshairPosition();
    }
  }, [handle, syncIndex, sDates, sLines]);

  useEffect(() => {
    if (!handle) return;
    const { chart } = handle;
    const onMove = (param: { time?: Time }) => {
      const t = param.time;
      notify(t == null ? null : (indexOf.get(String(t)) ?? null));
    };
    chart.subscribeCrosshairMove(onMove);
    return () => chart.unsubscribeCrosshairMove(onMove);
  }, [handle, indexOf, notify]);

  return (
    <>
      <div
        ref={setEl}
        role="img"
        aria-label={accessibilityLabel}
        /* **부모가 가로 flex 든 세로 flex 든 맞아야 한다.**
           CDS `Box` 는 flex row, `VStack` 은 flex column 이라 이 div 는 둘 다에
           놓인다. 실측 2026-08-26 에 양쪽으로 한 번씩 틀렸다:
             · 아무 것도 안 주면 가로 부모에서 **폭 0** 이 된다(캔버스는 안에서
               절대 배치라 «내용» 이 없다 — 부모 874px 에 이 div 0px).
             · `flexBasis: 0` 을 주면 세로 부모에서 **높이 0** 이 된다(그 축의
               main-size 가 0 이 되고, 부모에 정해진 높이가 없어 안 자란다).
           `flexBasis: 'auto'` 는 «그 축의 크기 속성을 쓰라» 는 뜻이라 가로에서는
           `width`, 세로에서는 `height` 를 본다. 둘 다 주고 `flexGrow` 로 남는
           자리를 받는다. `minWidth/minHeight: 0` 이 없으면 flex 아이템의 최소
           크기가 내용이라 줄지 않는다. */
        style={{
          flexGrow: 1,
          flexBasis: 'auto',
          minWidth: 0,
          minHeight: 0,
          width: '100%',
          height: height != null ? height : '100%',
        }}
      />
      <span className="sr-a11y-only" aria-live="polite">
        {hoverLabel && hover != null ? hoverLabel(hover) : ''}
      </span>
    </>
  );
}

/**
 * 위아래로 쌓인 차트들이 **같은 값-축 폭**을 쓰게 한다.
 *
 * 돌려주는 둘을 형제 차트마다 그대로 펼쳐 준다:
 *
 *     const stack = useStackedScales();
 *     <TimeChart … {...stack} />
 *     <TimeChart … {...stack} hideTimeAxis={false} />
 *
 * 폭은 형제 중 **가장 넓은 것**으로 수렴한다. 줄어들지 않는 이유는 좁아지는
 * 쪽으로 따라가면 둘이 서로를 밀며 진동하기 때문이다 — 창은 새 실행마다 다시
 * 서므로 한 화면 안에서 단조인 것으로 충분하다.
 */
export function useStackedScales(): {
  scaleWidth: number | undefined;
  onScaleWidth: (w: number) => void;
} {
  const [scaleWidth, setScaleWidth] = useState<number>();
  const onScaleWidth = useCallback(
    (w: number) => setScaleWidth((prev) => (prev == null || w > prev ? w : prev)),
    [],
  );
  return { scaleWidth, onScaleWidth };
}
