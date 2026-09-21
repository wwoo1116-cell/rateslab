'use client';

/* 백테스트의 차트 한 쌍 — 종목 차트 + **픽셀 정렬된** 누적 손익 [v1 OWNER
 * 재피드백, 2026-08-04 — "PL은 밑에 그려지되 … far left가 진입일, far right가
 * 청산일로 해서 … 완전히 수직적으로 얼라인"].
 *
 * v1 `ui/BacktestPnlCharts.tsx`(손 SVG)의 CDS 재구현이다. 정렬은 조정이 아니라
 * **구성**이다: 두 차트가 같은 날짜 배열을 x 도메인으로 받고(문자열 xAxis →
 * 인덱스 도메인, `[0, n-1]` 선형), 같은 inset 을 쓴다 — 한 날짜의 x 가 위아래서
 * 픽셀까지 같다. 십자선은 CDS `ReferenceLine`(dataX = 인덱스)로 **반대쪽
 * 차트에** 선다: 스크러버가 짚는 쪽은 CDS 자신의 세로선이 이미 있다.
 *
 * 손익 값은 서버의 발행점을 **찾아 쓸 뿐** 계산하지 않는다(§16): 각 날짜의
 * 돈은 그 날짜 이전 가장 최근 발행점의 누적 손익이고(전진 워크), `당일`(d)은
 * 서버가 발행점마다 전영업일을 따로 평가해 실어 준 1영업일 변화다.
 *
 * 0선은 항상 프레임 안이다 — 승패의 경계라, 자기 축 위·아래로 통째로 떠 있는
 * 손익 차트는 한눈에 읽히지 않는다. `ReferenceLine`(dataY=0)이 그 선이다.
 *
 * 리드아웃은 공용 `ReadoutCard` 가 아니라 **돈 카드**다(v1 의 같은 결정 —
 * 그 카드는 `fmtLevel`/`fmtDelta` 를 소유해서 수량 문법이 하나로 남는 물건이고,
 * 이 축은 `fmtKrw` 의 억/만이다. 다른 수량, 다른 카드).
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import { Box, VStack } from '@coinbase/cds-web/layout';

import { TimeChart, useStackedScales, type TimeLine } from '@/chart/TimeChart';
import type { ScalePriceLine } from '@/chart/ScaleChart';
import type { LwPalette } from '@/chart/palette';
import { alignByDate, policyByDate, referenceMode } from '@/chart/references';
import type { PolicyStep, Unit } from '@/lib/api';
import { fmtLevel, unitSuffix } from '@/lib/format';
import { fmtKrw } from '@/lib/krw';
import { loadCd } from '@/ui/PreviewPane';
/* `RefKey`(못 누르는 범례)와 `placeReadout`(떠 있는 카드의 자리)은 더 안 쓴다
   [2026-09-21] — 둘 다 스트립 한 줄이 흡수했다. 두 부품은 남는다: 시뮬·rv·
   MR·Lab 의 카드들과 Lab 시나리오의 범례가 아직 쓴다. */
import { ChartReadoutStrip, slotChars, type StripSlot } from '@/ui/ChartReadoutStrip';

/** `PnlSeries` — v1 과 같은 구조 프롭. 스왑과 현금채권이 한 북에 섞여도
 * (`BacktestResult`) 차트는 줄의 종류를 알 필요가 없다: 필요한 것은 이 네
 * 필드뿐이고, 하나라도 사라지면 타입이 먼저 말한다. */
export interface PnlSeries {
  from: string;
  to: string;
  pnl: number;
  points: { t: string; pnl: number; d: number | null }[];
}

/** 기준선 두 개 — 미리보기 pane 과 같은 낱말 [OWNER 2026-07-31: "CD와
 * 기준금리는 항상 같이 그린다" + 2026-08-19: "백테스트에 CD금리는 같이"].
 * %-종목은 같은 축, bp-종목은 왼쪽 %축(`referenceMode`). */
const CD_LINE = 'CD91';
const BASE_LINE = 'BASE';

/** 날짜별 누적 손익 — 서버 발행점의 **전진 워크**(찾기, 계산 아님 §16).
 * 각 날짜의 돈은 그 날짜 이전(포함) 가장 최근 발행점의 누적이고, 발행점보다
 * 앞선 날짜는 0(진입 전 = 아직 아무 일도 없다). 두 배열 다 날짜 오름차순. */
export function pnlAtDates(
  dates: string[],
  published: { t: string; pnl: number }[],
): number[] {
  const out: number[] = [];
  let j = -1;
  for (const t of dates) {
    while (j + 1 < published.length && published[j + 1].t <= t) j++;
    out.push(j >= 0 ? published[j].pnl : 0);
  }
  return out;
}



export function LinkedCharts({
  points,
  unit,
  seriesColor,
  result,
  marks,
  policy,
}: {
  /** 종목 차트가 그리는 창 — 진입(첫 점)부터 청산(끝 점)까지, 서버 발행점. */
  points: { t: string; v: number }[];
  unit: Unit;
  /** 종목 선의 색. 안 주면 잉크. */
  seriesColor?: string;
  result: PnlSeries;
  /** 진입·청산 표시 — 세로 기준선과 라벨. 날짜는 on-or-after 로 인덱스가 된다. */
  marks?: { date: string; label: string }[];
  /** 기준금리 스텝 — 화면의 성질이라 받는다(미리보기 pane 과 같은 규칙).
   * 없으면 그 선만 빠진다. */
  policy?: PolicyStep;
}) {
  /* 커서가 짚은 점 — 어느 차트가 짚었는지도 함께. 십자선은 반대쪽에만 선다. */
  const [hover, setHover] = useState<{ i: number; src: 'top' | 'bottom' }>();

  /* 훅은 **조기 반환 위**에 선다 — 아래 `if (points.length < 2) return null` 보다
     뒤에 두면 렌더마다 훅 순서가 달라진다(eslint `rules-of-hooks`). */
  /* 진입·청산 마크. **근접 마크를 합친다** [OWNER 2026-08-25 — 겹침 금지,
     CLAUDE.md «말줄임 절대 금지» §3]: 세로선 라벨에는 충돌 회피가 없어, 며칠
     차이로 레그인한 두 진입이 몇 년 x 도메인에서 같은 픽셀에 떨어지면 «진입»
     두 장이 포개진다. 도메인의 ~2% 안에 든 마크는 선 하나로 합치고 라벨이
     센다 — «진입 ×2», 섞이면 «진입·청산». */
  const markIdx = useMemo(() => {
    const raw = (marks ?? [])
      .map((m) => ({ ...m, i: points.findIndex((p) => p.t >= m.date) }))
      .filter((m) => m.i >= 0)
      .sort((a, b) => a.i - b.i);
    const gap = Math.max(1, Math.round(points.length * 0.02));
    const out: { index: number; label: string }[] = [];
    let bucket: typeof raw = [];
    const flush = () => {
      if (bucket.length === 0) return;
      const byLabel = new Map<string, number>();
      for (const b of bucket) byLabel.set(b.label, (byLabel.get(b.label) ?? 0) + 1);
      const label = [...byLabel.entries()]
        .map(([l, n]) => (n > 1 ? `${l} ×${n}` : l))
        .join('·');
      out.push({ index: bucket[0]!.i, label });
      bucket = [];
    };
    for (const m of raw) {
      if (bucket.length > 0 && m.i - bucket[bucket.length - 1]!.i > gap) flush();
      bucket.push(m);
    }
    flush();
    return out;
  }, [marks, points]);

  const onTop = useCallback(
    (i: number | null) => setHover(i == null ? undefined : { i, src: 'top' as const }),
    [],
  );
  const onBot = useCallback(
    (i: number | null) => setHover(i == null ? undefined : { i, src: 'bottom' as const }),
    [],
  );

  /* 두 차트가 **같은 값-축 폭**을 쓴다 — 이 파일의 계약이 «픽셀까지 같다» 인데
     레벨 라벨(`3.245`)과 금액 라벨(`+20원`)의 폭이 달라 플롯이 914 대 920 으로
     어긋나 있었다(실측 2026-08-27). */
  const stack = useStackedScales();

  /* CD 91일 — `PreviewPane.loadCd` 의 모듈 캐시를 그대로 쓴다(한 페이지에서 두
   * 번 받지 않는다). 실패는 null: 기준선이 없다고 백테스트가 안 보일 이유는
   * 없고, 범례가 없는 것으로 그 사실을 말한다. */
  const [cd, setCd] = useState<{ t: string; v: number }[] | null>(null);
  useEffect(() => {
    let on = true;
    void loadCd().then((p) => {
      if (on) setCd(p);
    });
  return () => {
      on = false;
    };
  }, []);

  const dates = useMemo(() => points.map((p) => p.t), [points]);

  const pnlVals = useMemo(() => pnlAtDates(dates, result.points), [dates, result.points]);

  /* 기준선을 종목 창의 날짜에 얹는다 — 미리보기와 같은 정렬 규칙(`alignByDate`:
   * 날짜로 맞추고, 시작 전은 null, 뒤로는 안 끌어온다). */
  const mode = referenceMode(unit);
  const refs = useMemo(() => {
    const cdLine = cd ? alignByDate(points, cd) : null;
    const policyLine = policyByDate(points, policy);
    const has = (a: (number | null)[] | null) => !!a && a.some((v) => v != null);
    if (!has(cdLine) && !has(policyLine)) return null;
    return { cd: has(cdLine) ? cdLine : null, policy: has(policyLine) ? policyLine : null };
  }, [points, cd, policy]);
  const pctAxis = refs != null && mode === 'own';
  /* 픽셀마다 돌던 `onMove` 가 여기 있었다 — 떠 있는 카드의 자리를 CSS 변수에
     적는 일이었고, 이 창은 차트 둘과 표를 함께 들고 있어 그게 공짜가 아니었다.
     스트립은 자리가 고정이라 아예 없앴다. 떠날 때 비우는 것만 남는다. */
  const leave = useCallback(() => setHover(undefined), []);

  /** 스트립이 읽는 점 — **커서가 없으면 마지막 봉**이다(`PreviewPane` 의 그
   *  규칙과 같다: 고정된 줄은 쉴 때도 무언가를 말해야 한다. 이 창에서 쉴 때의
   *  마지막 봉은 곧 **청산일**이라 그 자체로 읽을 값이다). */
  const hp = useMemo(() => {
    const i =
      hover && hover.i >= 0 && hover.i < points.length ? hover.i : points.length - 1;
    const p = points[i];
    if (!p) return { i: 0, t: '', v: null as number | null, pt: null as PnlSeries['points'][number] | null };
    return {
      i,
      t: p.t,
      v: p.v,
      // 그 날짜 이전 가장 최근 발행점 — 누적·당일이 읽는 것
      pt: [...result.points].reverse().find((q) => q.t <= p.t) ?? null,
    };
  }, [hover, points, result.points]);

  /* 손익 곡선의 부호색. **이른 반환보다 위**에 있어야 한다 — 아래 스트립
     memo 가 읽고, 훅은 조건부로 못 부른다. 아래 `botLines` 가 같은 상수를
     쓴다(두 군데 적으면 줄과 그림이 다른 색을 말하는 날이 온다). */
  const pnlColor = result.pnl >= 0 ? 'var(--sr-up)' : 'var(--sr-down)';

  /**
   * 스트립의 칸들 — 위 그림의 것(레벨·기준선 둘)과 아래 그림의 것(누적·당일)이
   * 한 줄에 선다. 종전에는 위 그림 밑에 못 누르는 범례(`RefKey`)가 한 줄,
   * 아래 그림 위에 돈 카드가 하나 있어서 **같은 커서를 두 자리가 설명**했다.
   *
   * 이 창의 기준선은 **못 끄는 것**이 그대로다(`toggle` 없음) — 백테스트는
   * 지나간 한 판을 보는 화면이라 취향으로 선을 껐다 켰다 할 자리가 아니고,
   * 그 판단은 종전 `RefKey`(못 누르는 범례)가 이미 지고 있었다.
   */
  const stripSlots = useMemo<StripSlot[]>(() => {
    const vals = points.map((p) => p.v);
    const chU = slotChars(
      (v) => fmtLevel(v, unit),
      Math.max(...vals),
      Math.min(...vals),
    );
    const out: StripSlot[] = [
      {
        key: 'level',
        label: '레벨',
        value: `${fmtLevel(hp.v, unit)}${unitSuffix(unit)}`,
        color: seriesColor ?? 'var(--color-fg)',
        chars: chU,
      },
    ];
    if (refs?.cd && refs.cd[hp.i] != null) {
      out.push({
        key: 'cd',
        label: 'CD 91일',
        value: `${fmtLevel(refs.cd[hp.i] as number, '%')}${unitSuffix('%')}`,
        color: 'var(--sr-ref-cd)',
        opacity: 0.9,
        drop: 5,
      });
    }
    if (refs?.policy && refs.policy[hp.i] != null) {
      out.push({
        key: 'policy',
        label: '기준금리',
        value: `${fmtLevel(refs.policy[hp.i] as number, '%')}${unitSuffix('%')}`,
        color: 'var(--sr-ref-policy)',
        opacity: 0.9,
        drop: 6,
      });
    }
    /* 돈 둘 — 아래 그림의 값이다. `당일` 은 늘 1영업일이다(서버가 발행점마다
       전영업일을 따로 평가한다) — 점이 며칠씩 떨어져 그려져도. */
    out.push(
      { key: 'cum', label: '누적', value: hp.pt ? fmtKrw(hp.pt.pnl) : '—', color: pnlColor },
      { key: 'day', label: '당일', value: hp.pt?.d == null ? '—' : fmtKrw(hp.pt.d), drop: 3 },
    );
    return out;
  }, [points, unit, hp, refs, seriesColor, pnlColor]);

  if (points.length < 2) return null;

    /* 위 차트 — 종목 선 + 기준선 둘. 기준선은 종목 선보다 얇고, 색 하나로만
     구분한다(같은 지각적 무게). 단위가 다르면 기준선만 왼쪽 %축으로 간다. */
  const topLines: TimeLine[] = [
    {
      id: 'level',
      values: points.map((p) => p.v),
      color: (pal) => (seriesColor ? pal.resolve(seriesColor) : pal.fg),
      format: (v) => fmtLevel(v, unit),
    },
    /* 잉크는 종목 선보다 한 칸 뒤로 — 아래 범례가 쓰는 `opacity={0.9}` 와 같은
       칸이다. 캔버스에는 불투명도 손잡이가 없어 색 자체를 흐리게 만든다. */
    ...(refs?.cd
      ? [{
          id: CD_LINE,
          values: refs.cd,
          color: (pal: LwPalette) => pal.dim(pal.refCd, 90),
          width: 1 as const,
          axis: (pctAxis ? 'aux' : 'main') as 'aux' | 'main',
          format: (v: number) => fmtLevel(v, pctAxis ? '%' : unit),
        }]
      : []),
    ...(refs?.policy
      ? [{
          id: BASE_LINE,
          values: refs.policy,
          color: (pal: LwPalette) => pal.dim(pal.refPolicy, 90),
          width: 1 as const,
          /* 기준금리는 계단 — 정책금리는 평평하다가 뛴다. */
          step: true,
          axis: (pctAxis ? 'aux' : 'main') as 'aux' | 'main',
          format: (v: number) => fmtLevel(v, pctAxis ? '%' : unit),
        }]
      : []),
  ];

  /* 아래 차트 — 누적 손익. 부호 방향색 + **채운 면**(점무늬가 아니다: 이 면은
     «얼마나» 를 말하는 덩어리이지 계열의 무늬가 아니다). 면은 흐리게. */
  const botLines: TimeLine[] = [
    {
      id: 'pnl',
      values: pnlVals,
      color: (pal) => pal.resolve(pnlColor),
      area: 'solid',
      areaColor: (pal) => pal.dim(pnlColor, 14),
      format: (v) => fmtKrw(v),
    },
  ];

  /* 0선 — 승패의 경계는 항상 프레임 안이다. */
  const zeroLine: ScalePriceLine[] = [{ value: 0, color: (pal) => pal.line }];



  return (
    /* `onMouseMove` 가 없어졌다 — 떠 있는 카드의 자리를 CSS 변수에 적던
       배선이고, 스트립은 자리가 고정이라 잴 것이 없다. */
    <VStack gap={0} width="100%" onMouseLeave={leave}>
      {/* ── 리드아웃 줄 [OWNER 2026-09-21] ─────────────────────────────────
          **차트 둘을 한 줄이 읽는다.** 두 그림은 같은 날짜 배열을 x 로 쓰고
          커서도 한 벌이라(`syncIndex`), 값을 읽는 자리도 하나여야 한다 —
          그림마다 하나씩 달면 같은 커서가 두 번 설명된다.

          자리가 맨 위인 것도 그래서다: 종전의 돈 카드는 **아래** 손익 그림 위에
          떠 있었는데, 그 그림은 높이가 140 이라 220px 짜리 카드가 그림보다
          컸다. 위로 올리면 두 그림 어느 쪽도 안 가린다.

          레벨과 돈이 한 줄에 서는 것은 이 창에서 **정상**이다 — 종전에 카드를
          둘로 가른 근거(「다른 수량, 다른 카드」)는 카드가 `fmtLevel`/`fmtKrw`
          를 **소유**해야 했을 때의 것이고, 스트립은 칸마다 이미 서식이 다른
          글자를 받는다. */}
      {points.length >= 2 ? (
        <ChartReadoutStrip date={hp.t} slots={stripSlots} />
      ) : null}

      {/* ── 종목 차트 ─────────────────────────────────────────────────────── */}
      <Box className="sr-plot" width="100%">
        <TimeChart
          height={200}
          accessibilityLabel="종목 추이 (진입부터 청산까지)"
          dates={dates}
          lines={topLines}
          markLines={markIdx}
          onHoverIndex={onTop}
          syncIndex={hover?.src === 'bottom' ? hover.i : null}
          {...stack}
        />
      </Box>

      {/* ── 누적 손익 — 같은 날짜 배열, 같은 축 폭 = 픽셀 정렬 ─────────────── */}
      <Box className="sr-plot" width="100%">
        {/* x 라벨은 **위 차트가 진다** — 두 벌이면 같은 날짜가 두 줄로 선다.
            CDS 판은 이 차트에 `<XAxis>` 를 아예 안 뒀고, 이관 때 그 손잡이가
            없어서 날짜가 두 줄이 됐다 [2026-08-27 수리]. */}
        <TimeChart
          height={140}
          accessibilityLabel="누적 손익 (위 차트와 같은 구간)"
          dates={dates}
          lines={botLines}
          priceLines={zeroLine}
          onHoverIndex={onBot}
          syncIndex={hover?.src === 'top' ? hover.i : null}
          hideTimeAxis
          {...stack}
        />
      </Box>
    </VStack>
  );
}
