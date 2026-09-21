'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import {
  TextBody,
  TextCaption,
  TextDisplay3,
  TextLabel1,
  TextLabel2,
  TextTitle3,
} from '@coinbase/cds-web/typography';

import { CD_SERIES_ID, type PolicyStep } from '@/lib/api';
import { fmtDelta, fmtDeltaUnit, fmtLevel, toDeltaUnit, unitSuffix } from '@/lib/format';
import { rangePosition } from '@/lib/range';
import { cashbondSeriesUrl, seriesUrl, universeSeriesUrl } from '@/lib/staticPaths';
import { PeriodSelector } from '@coinbase/cds-web/visualizations/chart';

import { CurveChart, type CurveLine } from '@/chart/CurveChart';
import { TimeChart, type TimeLine, type TimeMarker } from '@/chart/TimeChart';
import { type IdleCurve } from '@/chart/curve';
import type { LwPalette } from '@/chart/palette';
import { alignByDate, policyByDate, referenceMode } from '@/chart/references';
import { panRange, sliceRange, zoomRange, type ViewRange } from '@/chart/zoom';
import { windowExtremes } from '@/chart/extremes';
import { maColorOf, maColorVar, useOverlayPrefs } from '@/state/overlays';
import type { Row } from '@/table/rows';

import { useFillHeight } from './useFillHeight';

/* `ReadoutCard` 는 **안 쓴다** [2026-09-21] — 이 pane 의 두 차트는 떠 있는
   카드에서 고정 스트립으로 옮겼다. 모듈과 CSS 는 남는다: 시뮬·rv·MR·Lab 의
   열네 카드가 아직 그 문법을 쓴다. 낱말(`READOUT_LABEL`)은 계속 한 곳이다 —
   같은 값에 표면마다 다른 이름을 붙이지 않기 위해서다. */
import { READOUT_LABEL } from './ReadoutCard';
import { ChartReadoutStrip, slotChars, type StripSlot } from './ChartReadoutStrip';

/** `d` = 그날의 전일 대비 변화. **백엔드가 낸다**(`derive.py::series_history`) —
 * 브라우저는 시계열을 차분하지 않는다(§16). 카드의 「당일 변화」가 이 값이다. */
type Point = { t: string; v: number; d?: number | null; ma?: (number | null)[] };

/**
 * 이동평균 — **벤더 표준 그대로** [OWNER, 2026-08-26 — "차트 회사들에서 제공하는
 * 표준 MA로"]. 창은 서버가 정한다(`derive.MA_WINDOWS` = 5·10·20·60·120, 키움 HTS
 * 공장 기본값). 켤지 말지와 무슨 색인지는 `state/ma.ts` 가 기억한다
 * [OWNER — "당연히 껏다 켰다 가능하게 … 색도 컬러토큰에서"].
 *
 * ── 무게 사다리는 남는다 ───────────────────────────────────────────────────
 * 색이 생겼다고 굵기까지 같아지면, 켤 수 있는 다섯이 전부 같은 무게로 서서
 * 종목 선과 다툰다. 창이 길수록 굵고 진하다 — 느리고 구조적인 선이 무거워야
 * 눈이 층을 읽는다. 가장 무거운 MA 도 종목 선(2px·불투명)보다 가볍다: 주선이
 * 주인공이라는 캐논은 색과 무관하다.
 *
 * MA 는 스크러버가 짚지 않는다(아래 `seriesIds`) — 구슬이 다섯 개 더 뜨면 커서가
 * 무엇을 읽는지 모르게 된다. 값은 리드아웃 카드가 줄로 적는다.
 */
/* 굵기는 **정수만** 된다 — 캔버스 라이브러리의 `lineWidth` 가 1~4 다(CDS 는
   소수 굵기를 받았다). 사다리의 뜻(«긴 창일수록 진하게»)은 불투명도가 그대로
   지고, 굵기는 뒤 두 개만 한 칸 올린다. */
const MA_INK: { width: 1 | 2; opacity: number }[] = [
  { width: 1, opacity: 0.55 },
  { width: 1, opacity: 0.65 },
  { width: 1, opacity: 0.75 },
  { width: 2, opacity: 0.85 },
  { width: 2, opacity: 0.95 },
];

/** 시리즈 id — 문자열을 두 군데 적으면 한 군데만 고쳐지는 날이 온다(§MAIN_AXIS). */
const maSeriesId = (w: number) => `MA${w}`;

/** 52주 통계. 이것도 서버 것이다 — 최근 252관측 창이고, 차트가 보여주는 구간과
 * **무관하게** 고정이다. v1 이 여기에 남긴 근거: 10년 창은 2020~21 레짐 단절을
 * 가로질러 모든 레벨을 99~100분위에 못박았다. 구간을 좁히거나 넓히면 카드가
 * 표의 52주 열과 다른 말을 하게 된다. */
type SeriesStats = { min: number | null; max: number | null; avg: number | null };


/**
 * The instrument detail pane, rebuilt against coinbase.com/price/* [OWNER
 * 2026-08-13: "나머지는 코인베이스 스타일 … 정말 정말 코인베이스처럼"].
 *
 * ── Why this is CDS components and not a hand-drawn SVG ─────────────────────
 * The reference page's chart was taken apart on 2026-08-13 and turned out to be
 * CDS itself: its axis labels resolve `var(--color-fgMuted)`, and the area fill
 * is the exact composition CDS's `LineChart` emits for `areaType="dotted"` —
 *
 *     <mask> <path d={area} fill="url(#pattern)"/> </mask>   pattern = 4×4, circle r=1
 *     <path d={area} fill="url(#gradient)" mask="url(#mask)"/>  gradient = hue, α 0→1
 *     <path d={line} stroke={hue} stroke-width="2" linecap/linejoin="round"/>
 *
 * So the faithful way to look like Coinbase is not to imitate that markup, it is
 * to call the component that produces it. Hand-rolling it would also give up
 * scrubbing, which the reference has and which a rates reader needs more than a
 * crypto one.
 *
 * ── What replaced lightweight-charts, and the rule that changed ─────────────
 * The previous pane drew an INK line, on the stated rule that "a line has no
 * sign". That rule is retired here, deliberately: a line drawn OVER A PERIOD
 * does have a sign — its net change — and that is precisely what the reference
 * encodes, colouring line, fill and the active period pill with it. The
 * refinement is that the sign belongs to THE SPAN THE LINE DRAWS, not to today:
 * colouring a one-year line by today's move paints a year of rises blue because
 * the last print ticked down.
 */

const CD_LINE = 'CD91';
const BASE_LINE = 'BASE';

/**
 * 52주 최고·최저·평균을 **리드아웃 줄에도** 적는가 [OWNER 2026-09-21: 뺀다].
 *
 * 카드 시절에는 세 줄이었다 [OWNER 2026-08-14: "날짜, 레벨, 52주 최고·최저·
 * 평균, CD91 금리가 나와야 함"]. 줄로 옮기면서 뺀 이유는 뜻이 바뀌어서가 아니라
 * **자리**다: 한 줄에 일곱 칸이 서는데 그 중 셋이 커서를 따라 **안 바뀌는 값**
 * 이면(52주 통계는 서버가 낸 252관측 고정이라 구간을 좁혀도 그대로다), 정작
 * 커서가 읽는 값들이 좁은 창에서 먼저 밀려난다.
 *
 * 없어진 것은 아니다 — 표의 52주 열과 히어로 밑 「이 구간」 통계가 같은 값을
 * 적는다. 되살릴 일이 생기면 이 상수 하나이고, 자리는 **둘째 줄**이다(첫 줄에
 * 끼우면 위의 이유가 그대로 돌아온다).
 */
const SHOW_52W_IN_STRIP = false;

/* 주봉·월봉(캔들 모드)이 여기 살았다가 **오너 지시로 제거됐다** [OWNER
 * 2026-08-18 — "주봉 월봉 없애도 될 거 같고"]. 백엔드의 `interval=w|m` 라우트와
 * `derive.py::ohlc_buckets` 는 남는다(v1 과 바이트 대사 유지·`/chart` 하니스가
 * 여전히 쓴다). 되살릴 일이 생기면 그 세션의 함정 셋을 함께 가져올 것:
 * 구간 days 는 영업일이라 봉 수로 환산해야 하고(1Y 주봉 = 52봉), 꼬리는 안
 * 그려지는 시리즈로 y 도메인에 넣어야 한다(둘 다 조용히 틀린다). 축 이름
 * 함정은 없어졌다 — 이제 계열이 `axis: 'main'|'aux'` 로만 말한다
 * [2026-08-26 이관]. 캔들은 `lightweight-charts` 가 기본으로 갖고 있다. */

/** The spans offered, and how many trailing points each keeps. `null` = all. */
const SPANS = [
  { key: '1M', label: '1M', days: 22 },
  { key: '3M', label: '3M', days: 66 },
  { key: '6M', label: '6M', days: 132 },
  { key: '1Y', label: '1Y', days: 260 },
  { key: 'ALL', label: '전체', days: null },
] as const;

type SpanKey = (typeof SPANS)[number]['key'];

/** `PeriodSelector` takes `{id,label}` tabs. Derived from SPANS rather than
 * typed twice, so a span cannot exist in one list and not the other. */
const SPAN_TABS = SPANS.map((s) => ({ id: s.key as string, label: s.label }));

async function loadSeries(row: Row): Promise<{
  unit: string;
  points: Point[];
  stats: SeriesStats | null;
  maWindows: number[];
}> {
  // Swap rows have a stage-2 history route; universe rows have their own; cash-bond
  // rows a third (민평은 SQL 전용이라 라이브만 있다). Three routes, one shape — the
  // pane does not care which produced it (`derive.series_history` 가 셋 다 만든다).
  const url =
    row.group === 'cashbond' || row.group === 'asw'
      ? cashbondSeriesUrl(row.id)
      : row.seriesId
        ? seriesUrl(row.seriesId, 'full')
        : universeSeriesUrl(row.id);
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const j = (await r.json()) as {
    unit?: string;
    points?: Point[];
    stats?: SeriesStats | null;
    ma?: Record<string, (number | null)[]>;
    maWindows?: number[];
  };
  /* `stats` 는 예전부터 이 응답 안에 있었다 — 프런트가 버리고 있었을 뿐이다.
     카드가 52주 세 줄을 이걸로 찍는다(v1 과 같은 출처). */
  const points = j.points ?? [];
  const windows = j.maWindows ?? [];
  /* **이동평균을 점에 얹는다.** 서버가 솎기 전에 얹은 것과 같은 이유다: 이 파일은
     점 배열을 두 번 자른다(구간 알약 → 확대). MA 를 따로 들고 있으면 그 두
     자르기를 두 번째 자리에서 똑같이 흉내내야 하고, 언젠가 한쪽만 고쳐진다.
     점에 붙여 두면 `view.win` 이 잘릴 때 MA 도 같이 잘린다 — 어긋날 길이 없다. */
  if (windows.length && j.ma) {
    for (let i = 0; i < points.length; i++) {
      points[i].ma = windows.map((w) => j.ma?.[String(w)]?.[i] ?? null);
    }
  }
  return {
    unit: j.unit ?? row.unit,
    points,
    stats: j.stats ?? null,
    maWindows: windows,
  };
}

/** One label-over-value pair, the reference's stat unit. The label is the quiet
 * one: small, muted, and never competing with the number it names. */
function Stat({ label, value, tone }: { label: string; value: string; tone?: 'up' | 'down' }) {
  return (
    <VStack gap={0.25} minWidth={0}>
      <TextCaption as="span" color="fgMuted" noWrap>
        {label}
      </TextCaption>
      <TextBody
        as="span"
        tabularNumbers
        noWrap
        className={tone === 'up' ? 'sr-up' : tone === 'down' ? 'sr-down' : undefined}
      >
        {value}
      </TextBody>
    </VStack>
  );
}

/* `RefChip`(끌 수 있는 기준선 범례 항목)이 여기 있었다 [은퇴 2026-09-21].
 *
 * 그 부품의 일 — 견본은 그려진 색 그대로, 끄면 흐려지고, 누르면 토글 — 은
 * 그대로 살아서 **리드아웃 줄의 칸**이 진다(`ui/ChartReadoutStrip.tsx`).
 * 없어진 것은 부품이 아니라 «값 없이 이름만 있는 범례» 라는 자리다: 그림
 * 아래에 이름만 서고 값은 떠 있는 카드에 있어서, 같은 커서를 두 자리가
 * 설명하고 있었다.
 *
 * ⚠ `RefKey`(못 끄는 범례)도 **2026-09-21 에 내려갔다**. 마지막 사용처였던 Lab
 * 시나리오가 고정 줄로 옮기면서 쓰는 곳이 0 이 됐고, 쓰는 곳 없는 export 는
 * 「아직 그 문법이 산다」고 거짓말을 한다. 되살릴 일이 있으면 git 이 든다. */

/** 세 통계 묶음 — 본문에서도, 확대 창의 서랍에서도 **이것 하나**를 그린다.
 * 두 벌이면 한쪽에만 열이 붙거나 단위가 갈리고, 그때 두 화면이 같은 종목을
 * 놓고 다른 말을 하게 된다. */
function StatColumns({
  row,
  view,
  u,
}: {
  row: Row;
  view: { hi: number; lo: number; win: unknown[] } | null;
  u: string;
}) {
  return (
    <HStack className="sr-stats" flexWrap="wrap">
      <StatColumn title="이 구간">
        <Stat label="최고" value={view ? fmtLevel(view.hi, row.unit) + u : '—'} />
        <Stat label="최저" value={view ? fmtLevel(view.lo, row.unit) + u : '—'} />
        <Stat label="영업일" value={view ? `${view.win.length}일` : '—'} />
      </StatColumn>

      <StatColumn title="변화">
        <Stat
          label="전일"
          value={fmtDelta(row.changes.d1, row.unit) + u}
          tone={row.changes.d1 == null ? undefined : row.changes.d1 > 0 ? 'up' : 'down'}
        />
        <Stat
          label="MTD"
          value={fmtDelta(row.changes.mtd, row.unit) + u}
          tone={row.changes.mtd == null ? undefined : row.changes.mtd > 0 ? 'up' : 'down'}
        />
        <Stat
          label="YTD"
          value={fmtDelta(row.changes.ytd, row.unit) + u}
          tone={row.changes.ytd == null ? undefined : row.changes.ytd > 0 ? 'up' : 'down'}
        />
      </StatColumn>

      <StatColumn title="52주">
        <Stat label="고점" value={fmtLevel(row.rangeHigh, row.unit) + u} />
        <Stat label="저점" value={fmtLevel(row.rangeLow, row.unit) + u} />
        <Stat label="평균" value={fmtLevel(row.rangeAvg, row.unit) + u} />
        {/* 트랙의 마커와 **같은 함수**가 낸다(`lib/range.ts`). 2026-08-19 까지
            이 칸은 서버의 `pct`(순위 백분위)를 찍고 있었는데, 바로 위 세 줄이
            고점·저점·평균이라 "위치" 는 그 둘 사이의 자리로 읽힌다. 다른 양을
            그 이름으로 찍고 있었다 — 표의 트랙과 같은 병이었다. */}
        <Stat
          label="위치"
          value={(() => {
            const pos = rangePosition(row.now, row.rangeLow, row.rangeHigh);
            return pos == null ? '—' : `${Math.round(pos)}%`;
          })()}
        />
      </StatColumn>
    </HStack>
  );
}

/** A stat column under the chart. The reference divides these with a vertical
 * hairline rather than a gap, which is what makes three lists read as one block
 * instead of three floating groups. */
function StatColumn({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <VStack gap={1.5} paddingX={2} paddingY={2} flexGrow={1} minWidth={0} className="sr-statcol">
      <TextTitle3 as="h3">{title}</TextTitle3>
      <HStack gap={3} flexWrap="wrap">
        {children}
      </HStack>
    </VStack>
  );
}

/**
 * CD 91일 — 한 번만 가져온다.
 *
 * 행마다 다시 부르면 hover 로 표를 가로지를 때마다 2,600점짜리 히스토리를 다시
 * 받는다. CD 는 종목이 아니라 **화면 전체의 기준**이라 한 번 받아서 모두가 쓴다.
 * 실패는 `null` 로 삼킨다 — 기준선이 없다고 종목 차트가 안 나올 이유는 없고,
 * 화면은 범례가 없는 것으로 그 사실을 말한다.
 *
 * 실측 2026-08-14: 페이지 로드에 1회. 다섯 행을 hover 로 훑으면 요청이 하나 더
 * 느는데 그건 이 캐시가 샌 게 아니라 **3M 행 자신의 히스토리**다 — 3M 노드가 곧
 * CD 91일이라 URL 이 같다(`lib/api.ts::CD_SERIES_ID`).
 */
let cdPromise: Promise<Point[] | null> | null = null;
/** exported: 백테스트 창의 `LinkedCharts` 도 같은 캐시를 쓴다 — CD 는 화면
 * 전체의 기준이라 두 번 받을 이유가 없다. */
export function loadCd(): Promise<Point[] | null> {
  cdPromise ??= (async () => {
    try {
      const r = await fetch(seriesUrl(CD_SERIES_ID, 'full'));
      if (!r.ok) return null;
      const j = (await r.json()) as { points?: Point[] };
      return j.points ?? null;
    } catch {
      return null;
    }
  })();
  return cdPromise;
}

export function PreviewPane({
  row,
  policy,
  curve,
  onEnlarge,
  onOpenBacktest,
  chartOnly,
  statsOnly,
  fill,
  height = 320,
}: {
  row?: Row;
  /** 아무 행도 안 고른 상태에서 그릴 IRS 파 커브(`chart/curve.ts`). 행이 아니라
   * 화면의 성질이라 pane 이 스스로 만들지 않고 받는다. */
  curve?: IdleCurve;
  /** 기준금리 스텝. 표 전체에 하나이고 `WallSummary` 가 실어 온다. 없으면 그
   * 선만 빠진다 — 없는 것을 지어내지 않는다. */
  policy?: PolicyStep;
  /** 확대 창을 여는 손잡이. 없으면 버튼이 안 나온다 — 창 **안에서** 이 pane 을
   * 다시 그릴 때가 그렇다(창 안에 확대 버튼이 또 있으면 자기를 연다). */
  onEnlarge?: () => void;
  /** 차트 클릭 = 백테스트 [v1 계약, OWNER 2026-08-18 복원]. 두 번째 인자는
   * **커서가 짚고 있던 날짜** — 그 날이 진입일이 된다(v1 의 `btf` 그대로).
   * 안 주면 차트가 안 눌린다: 전체탭 오버뷰(v1 에서도 안 열림)와 확대 창
   * (창 위에 창)이 그 경우다. */
  onOpenBacktest?: (row: Row, from?: string) => void;
  /* 확대 창이 이 pane 을 **두 조각으로 나눠 쓴다**: 본문에는 차트를, 서랍에는
   * 통계를. 컴포넌트를 둘로 쪼개는 대신 두 플래그를 둔 이유는 히어로·구간
   * 선택·기준선·통계가 전부 같은 `view` 하나에서 나오기 때문이다 — 쪼개면 그
   * 계산이 두 벌이 되고, 두 벌은 언젠가 서로 다른 구간을 말한다. */
  chartOnly?: boolean;
  statsOnly?: boolean;
  /** 차트가 **남는 높이를 전부** 쓴다 — `height` 대신.
   *
   * 부르는 쪽이 「카드 높이 − 상수」로 차트 높이를 정하던 자리다. 그 상수가 89px
   * 모자랐고(실측 2026-08-14: 히어로 128 + 범례 22 + 통계 115 = 265, 상수는 176),
   * 통계 3열이 카드 밖으로 88px 밀려 `.sr-card` 의 `overflow: hidden` 에 잘렸다.
   * 셋 다 고정 높이가 아니라서 — 범례는 기준선이 있을 때만 서고 통계는 폭에 따라
   * 접힌다 — 어떤 상수를 넣어도 어떤 화면에서는 틀린다. 그래서 **재서 쓴다.**
   *
   * 확대 창과 오버뷰 열은 이 모드를 안 쓴다: 창은 자기 본문 높이를 알고, 오버뷰
   * 차트는 고정 200 이 규칙이다 [v1 OWNER]. */
  fill?: boolean;
  height?: number;
}) {
  const [data, setData] = useState<{
    unit: string;
    points: Point[];
    stats: SeriesStats | null;
    maWindows: number[];
  }>();
  const [cd, setCd] = useState<Point[] | null>(null);
  const [error, setError] = useState<string>();
  const [span, setSpan] = useState<SpanKey>('1Y');

  /* 커서가 짚은 점. 인덱스는 **CDS 가 준다**(`onScrubberPositionChange`) — 그쪽이
   * 축 스케일을 가진 쪽이라, 우리가 픽셀에서 인덱스를 되계산하면 두 벌이 된다.
   * x 는 카드를 놓을 자리일 뿐이라 커서에서 바로 읽는다. */
  const [hoverIdx, setHoverIdx] = useState<number>();

  /* 그림에 남은 세로. `fill` 일 때만 쓴다 — 아닐 때는 `height` 가 답이고, 이 값은
   * 재도 무해하다(콜백 ref 는 붙는 그 순간 재므로 데이터보다 늦게 생기는 요소도
   * 잡는다. 그 함정은 `ui/useFillHeight.ts` 에 적혀 있다). */
  const [plotRef, plotH] = useFillHeight(height);
  const chartH = fill ? plotH : height;

  /* 커서 자리를 상자의 CSS 변수에 적던 `onPlotMove` 가 여기 있었다 —
     떠 있는 카드가 그걸 읽어 커서를 따라다녔다. 스트립은 자리가 고정이라 잴
     것이 없고, 그래서 픽셀마다 도는 콜백도 없다.

     떠날 때 비우는 것은 남는다: 커서가 그림 밖으로 나가면 스트립이 마지막
     봉으로 돌아가야 한다(`stripPoint` 머리글). */
  const onPlotLeave = useCallback(() => setHoverIdx(undefined), []);

  /* ── 제자리 확대 [v1 OWNER 2026-08-04] ──────────────────────────────────────
   * 휠로 확대·축소, **Shift+휠**로 좌우 이동. 끌기가 아닌 이유는 CDS 스크러버가
   * 포인터 이동을 이미 쓰고 있어서다 — 끌면 확대인지 값 읽기인지 화면이 모른다.
   * 페이지가 스크롤하지 않으므로(100vh 기둥) 휠을 가져가도 잃는 동작이 없다. */
  const [zoom, setZoom] = useState<ViewRange | null>(null);

  useEffect(() => {
    let cancelled = false;
    void loadCd().then((p) => {
      if (!cancelled) setCd(p);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setData(undefined);
    setError(undefined);
    if (!row) return;
    let cancelled = false;
    void (async () => {
      try {
        const d = await loadSeries(row);
        if (!cancelled) setData(d);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [row]);

  const days = SPANS.find((s) => s.key === span)?.days ?? null;

  /** 서버가 정한 이동평균 창. 화면은 목록을 따로 갖지 않는다 — 두 곳에 적으면
   *  「MA120」이 서로 다른 수를 가리키는 날이 온다. */
  const maWindows = useMemo(() => data?.maWindows ?? [], [data]);

  /* 켠 것과 색 — Setting 과 **같은 저장소**를 읽는다(`state/ma.ts`). 범례를
     눌러도 여기가 바뀌고, 그래서 두 화면이 갈리지 않는다. */
  const [prefs, ov] = useOverlayPrefs();


  /* The window the chart actually draws, and everything read off it. Kept in one
   * memo so the line's sign, the hero's change and the range readout can never
   * describe different windows — the defect that makes a chart argue with its
   * own caption. */
  const view = useMemo(() => {
    const pts = data?.points ?? [];
    /* 두 겹의 자르기 — **구간**(기간 알약)이 먼저, 그 안에서 **확대**가 다음.
       순서가 중요하다: 확대는 지금 보고 있는 구간 위의 조작이라, 1M 에서 확대해
       두고 1Y 로 넓히면 그 확대는 뜻을 잃는다(그래서 구간이 바뀌면 초기화한다). */
    const span = days == null ? pts : pts.slice(-days);
    const win = sliceRange(span, zoom);
    if (win.length === 0) return null;
    const first = win[0].v;
    const last = win[win.length - 1].v;
    /* 고·저는 `chart/extremes.ts` 가 낸다 — **자리까지** 같이 온다. 여기서
       값만 훑던 시절에는 "어느 날이 최고인가" 를 아무도 몰랐고, 그래서 그
       점을 찍을 수도 없었다. 동점 규칙(가장 최근)도 그 파일이 진다. */
    const ext = windowExtremes(win.map((p) => p.v));
    if (ext == null) return null;
    const { hi, lo } = ext;
    /* `spanLen` 은 확대 계산이 기준으로 삼는 **모수**다 — 지금 보이는 조각이
       아니라 구간 전체의 길이. 이게 없으면 확대할수록 모수가 줄어서 축소가
       전체로 돌아오지 못한다. */
    return { win, first, last, hi, lo, ext, net: last - first, spanLen: span.length };
  }, [data, days, zoom]);

  /* THE sign of this chart. `--sr-up` / `--sr-down` are read as CSS variables
   * rather than passed as tokens because CDS resolves a series `color` straight
   * into an SVG attribute, and the two direction hues are v2's, not CDS's. */
  const dir = view == null || view.net === 0 ? null : view.net > 0 ? 'up' : 'down';
  const hue =
    dir == null ? 'var(--color-fgMuted)' : dir === 'up' ? 'var(--sr-up)' : 'var(--sr-down)';

  /* 커서 아래의 점. 구간을 바꾸면 `view.win` 이 통째로 갈리므로 **인덱스가 남아
   * 있어도 버린다** — 범위 밖 인덱스로 카드를 그리면 있지도 않은 날짜의 값을
   * 지어내는 셈이고, v1 도 같은 자리에 같은 가드를 뒀다. `i` 를 같이 실어 보내는
   * 이유는 CD 기준선이 **같은 인덱스**로 정렬돼 있어서다(`alignByDate`). */
  const hoverPoint = useMemo(() => {
    if (!view || hoverIdx == null || hoverIdx < 0 || hoverIdx >= view.win.length) return null;
    const p = view.win[hoverIdx];
    /* `ma` 도 여기서 실어 보낸다 — 카드가 `view` 를 다시 뒤지면 널 검사가
       두 곳이 되고, 선과 카드가 다른 점을 읽을 길이 생긴다. */
    return { i: hoverIdx, t: p.t, v: p.v, d: p.d ?? null, ma: p.ma };
  }, [view, hoverIdx]);

  /* 52주 세 줄의 출처. 스왑 라우트는 `stats` 를 싣고(252관측) 유니버스 라우트는
     안 싣는다. 없을 때 **행의 값**으로 떨어지는데 그 둘은 같은 백엔드 함수
     (`annual_stats`)에서 나오므로 카드가 표의 52주 열과 다른 말을 할 수 없다. */
  /* memo 인 이유는 성능이 아니라 **참조**다: 매 렌더 새 객체면 이걸 의존성에
     둔 `stripSlots` 가 렌더마다 다시 돈다(lint 가 그 자리를 가리킨다). */
  const stats52 = useMemo(
    () => ({
      max: data?.stats?.max ?? row?.rangeHigh ?? null,
      min: data?.stats?.min ?? row?.rangeLow ?? null,
      avg: data?.stats?.avg ?? row?.rangeAvg ?? null,
    }),
    [data?.stats, row?.rangeHigh, row?.rangeLow, row?.rangeAvg],
  );

  /* 확대는 **지금 보고 있는 것** 위의 조작이라, 보고 있는 것이 갈리면 초기화한다.
     남겨두면 다른 종목·다른 구간·다른 종류의 인덱스 구간을 그대로 적용하게 되고,
     그건 있지도 않은 날짜 범위를 그리는 일이다. */
  useEffect(() => {
    setZoom(null);
  }, [row, span]);

  /* 휠은 **네이티브로** 단다. React 17 부터 `wheel`·`touchstart`·`touchmove` 는
     루트에 **passive** 로 붙어서, `onWheel` 안의 `preventDefault()` 는 아무 일도
     하지 않고 경고만 남긴다. 여기서는 그걸 막아야 한다 — 안 그러면 확대하려던
     휠이 창 본문(`.sr-window-body`)까지 같이 스크롤한다. */
  const plotEl = useRef<HTMLElement | null>(null);
  const setPlotEl = useCallback(
    (node: HTMLElement | null) => {
      plotEl.current = node;
      if (fill) plotRef(node);
    },
    [fill, plotRef],
  );

  const onWheel = useCallback(
    (e: WheelEvent) => {
      const len = view?.spanLen ?? 0;
      if (len < 2) return;
      e.preventDefault();
      const host = plotEl.current;
      if (!host) return;
      const r = host.getBoundingClientRect();
      if (e.shiftKey) {
        // 이동: 한 번에 보이는 폭의 10% 씩. 폭에 비례해야 확대 정도와 무관하게
        // 같은 "한 칸" 느낌이 난다.
        const visible = zoom ? zoom.i1 - zoom.i0 + 1 : len;
        const step = Math.max(1, Math.round(visible * 0.1));
        setZoom((z) => panRange(z, len, e.deltaY > 0 ? step : -step));
        return;
      }
      /* 앵커는 **커서의 x** 다 — 그 자리의 날짜가 그 자리에 남는다. 가운데
         기준으로 확대하면 보려던 지점이 화면 밖으로 밀려난다. */
      const frac = r.width > 0 ? (e.clientX - r.left) / r.width : 0.5;
      setZoom((z) => zoomRange(z, len, frac, e.deltaY > 0 ? 1.25 : 0.8));
    },
    [view?.spanLen, zoom],
  );

  useEffect(() => {
    const host = plotEl.current;
    if (!host) return;
    host.addEventListener('wheel', onWheel, { passive: false });
    return () => host.removeEventListener('wheel', onWheel);
  }, [onWheel]);

  const unit = data?.unit ?? row?.unit ?? '%';
  const fmtY = useCallback((v: number) => fmtLevel(v, unit as Row['unit']), [unit]);
  /** 왼쪽 축의 눈금은 언제나 % — 그게 이 축의 존재 이유다. */
  const fmtPct = useCallback((v: number) => fmtLevel(v, '%'), []);

  /* 기준선 두 개. 종목 선과 **같은 x 날짜 위에** 얹는다(`alignByDate`). 어느 축에
   * 실릴지는 단위가 정한다 — `chart/references.ts::referenceMode`. */
  const mode = referenceMode(unit as Row['unit']);
  const refs = useMemo(() => {
    if (!view) return null;
    const cdLine = cd ? alignByDate(view.win, cd) : null;
    const policyLine = policyByDate(view.win, policy);
    const has = (a: (number | null)[] | null) => !!a && a.some((v) => v != null);
    if (!has(cdLine) && !has(policyLine)) return null;
    return { cd: has(cdLine) ? cdLine : null, policy: has(policyLine) ? policyLine : null };
  }, [view, cd, policy]);

  /**
   * **그려지는** 기준선 — 있음(`refs`)과 그림(`drawn`)은 다른 질문이다
   * [OWNER, 2026-08-26 — "기준금리랑 CD금리도 MA처럼 껏다 켰다"].
   *
   *   `refs`  그 날짜 위에 얹을 값이 **있는가** — 범례에 칩을 세울지 정한다.
   *           없는 것은 끌 수도 없어야 하므로 칩 자체가 안 선다.
   *   `drawn` 있고 **켜져 있는가** — 시리즈·스크러버·리드아웃·보조축이 읽는다.
   */
  const drawn = useMemo(
    () =>
      refs
        ? {
            cd: prefs.refs.cd ? refs.cd : null,
            policy: prefs.refs.policy ? refs.policy : null,
          }
        : null,
    [refs, prefs.refs],
  );

  /** 보조 %축을 그리는가 — **그려지는** 기준선이 있고, 그것이 종목과 다른
   *  단위일 때만. 둘 다 꺼 두면 축도 내려간다: 빈 축은 눈금을 그리고 폭을
   *  먹으면서 아무것도 말하지 않는다(아래 `yAxes` 의 그 규칙). */
  const pctAxis = !!(drawn && (drawn.cd || drawn.policy)) && mode === 'own';


  /**
   * 스트립이 읽는 점 — **커서가 없으면 마지막 봉**이다.
   *
   * 카드에는 «없는 상태» 가 있었다(커서가 그림 밖이면 카드가 사라진다). 줄에는
   * 없다 — 자리가 고정이라 비워 두면 빈 줄이 서 있게 되고, 그건 화면이 아무
   * 말도 안 하면서 높이만 먹는 것이다. 쉴 때 마지막 봉을 읽으면 그 줄은 늘
   * «지금 이 종목이 어디에 있나» 를 말한다.
   */
  const stripPoint = useMemo(() => {
    const w = view?.win;
    if (!w?.length) return { i: 0, t: '', v: null as number | null, d: null as number | null, ma: undefined as (number | null)[] | undefined };
    const p = hoverPoint ?? w[w.length - 1];
    const i = hoverPoint ? hoverPoint.i : w.length - 1;
    return { i, t: p.t, v: p.v, d: p.d ?? null, ma: p.ma };
  }, [view, hoverPoint]);

  /**
   * 스트립의 칸들 — **그려진 선과 일대일**이다. 선이 없으면 칸도 없고, 칸의
   * 견본 색은 선의 색이며, 칸을 누르면 그 선이 꺼진다.
   *
   * 값의 출처가 선의 출처와 **같다**: MA 는 둘 다 `pt.ma[k]` 이고 `k` 는 서버
   * 목록의 첨자다(켠 것만 거른 배열의 첨자를 쓰면 다른 창의 평균을 그린다).
   * 기준선은 둘 다 `refs.*[i]` 다. 그래서 줄과 선이 다른 수를 말할 수 없다.
   */
  const stripSlots = useMemo<StripSlot[]>(() => {
    if (!view || !row) return [];
    const i = stripPoint.i;
    const fmtU = (v: number | null | undefined) => fmtLevel(v, row.unit);
    /* 자리는 **보이는 구간의 고·저**로 잰다 — 그 둘이 이 구간에서 가장 긴
       글자를 만든다(서식이 고정 자릿수라 길이는 정수부가 정한다). */
    const chU = slotChars(fmtU, view.hi, view.lo);
    const chPct = slotChars((v) => fmtLevel(v, '%'), 5, 0.5);

    const out: StripSlot[] = [
      { key: 'level', label: READOUT_LABEL.level, value: fmtU(stripPoint.v), color: hue, chars: chU },
    ];
    /* 이동평균 — **켠 것만** 값을 적는다. 끈 창은 이름과 견본만 남아 손잡이로
       선다(칸을 떨구면 좁은 창에서 켤 길이 없어진다).

       좁아질 때는 **긴 창부터** 값을 내려놓는다. 잉크 사다리(긴 창일수록
       무겁다)의 뒤집힘이 아니라 읽는 순서다: 커서 옆에서 먼저 보는 것은 가까운
       평균이고, 긴 평균은 그림의 선으로 이미 보인다. 서버 목록이 짧은 창부터라
       (`MA_WINDOWS` = 5·10·20·60·120) 첨자가 클수록 먼저 내려간다. */
    const maDrop = (k: number) => Math.min(6, Math.max(1, k + 1)) as 1 | 2 | 3 | 4 | 5 | 6;
    maWindows.forEach((w, k) => {
      const on = prefs.shown.includes(w);
      out.push({
        key: maSeriesId(w),
        label: `MA${w}`,
        value: on ? fmtU(stripPoint.ma?.[k]) : '',
        color: maColorVar(maColorOf(prefs, w)),
        opacity: MA_INK[k]?.opacity ?? 0.6,
        chars: chU,
        drop: maDrop(k),
        toggle: { on, onToggle: () => ov.toggle(w) },
      });
    });
    /* 기준선 둘 — **있음과 그림이 갈려 있다**: 칸이 서는가는 `refs`(값이
       있는가)가 정하고, 값을 적는가는 `drawn`(켜져 있는가)이 정한다. 없는
       기준선은 끌 수도 없어야 하고, 끈 기준선은 이름과 견본만 남아 손잡이로
       선다. 둘을 한 식으로 합치면 여기가 `drawn` 의 두 번째 벌이 된다. */
    if (refs?.cd) {
      out.push({
        key: CD_LINE,
        label: 'CD 91일',
        value: drawn?.cd ? fmtLevel(drawn.cd[i], '%') : '',
        color: 'var(--sr-ref-cd)',
        opacity: 0.9,
        chars: chPct,
        drop: 5,
        toggle: { on: prefs.refs.cd, onToggle: () => ov.toggleRef('cd') },
      });
    }
    if (refs?.policy) {
      out.push({
        key: BASE_LINE,
        label: '기준금리',
        value: drawn?.policy ? fmtLevel(drawn.policy[i], '%') : '',
        color: 'var(--sr-ref-policy)',
        opacity: 0.9,
        chars: chPct,
        drop: 6,
        toggle: { on: prefs.refs.policy, onToggle: () => ov.toggleRef('policy') },
      });
    }
    if (SHOW_52W_IN_STRIP) {
      out.push(
        { key: 'w52h', label: READOUT_LABEL.rangeHigh, value: fmtU(stats52.max), chars: chU, drop: 6 },
        { key: 'w52l', label: READOUT_LABEL.rangeLow, value: fmtU(stats52.min), chars: chU, drop: 6 },
        { key: 'w52a', label: READOUT_LABEL.rangeAvg, value: fmtU(stats52.avg), chars: chU, drop: 6 },
      );
    }
    return out;
  }, [view, row, stripPoint, hue, maWindows, prefs, refs, drawn, ov, stats52]);

  /* 차트가 먹는 선들. `axis` 가 어느 쪽인지 말한다: 같은 단위면 셋 다 종목
   * 축(오른쪽), 다른 단위면 기준선 둘만 왼쪽 %축으로 간다. */
  const chartLines = useMemo<TimeLine[]>(() => {
    if (!view) return [];
    const refAxis = pctAxis ? ('aux' as const) : ('main' as const);
    return [
      {
        id: row?.id ?? 'series',
        values: view.win.map((p) => p.v),
        color: (pal) => pal.resolve(hue),
        area: 'dots',
        format: fmtY,
        /* 구슬은 주선에만 — 기준선 둘과 MA 다섯까지 점을 띄우면 커서가 무엇을
           읽는지 그림이 말해 주지 못한다(`series.ts::addLine` 의 그 주석). */
        beacon: true,
      },
      /* 두 기준선은 **같은 위계의 두 색**이다 [OWNER 2026-08-18, 3차 확정 —
         네이버 MA 방식]. 색·판정 이력은 `theme/direction.css` 의 토큰 주석에
         있다. 잉크는 종목 선보다 한 칸 뒤로 물러난다 — CDS 판의
         `strokeOpacity={0.9}` 자리이고, 캔버스에는 불투명도 손잡이가 없어
         **색 자체를 흐리게** 만든다(`palette.dim`). 이관 때 이 한 칸이 빠져
         기준선이 주선보다 진했다 [2026-08-27 수리]. */
      ...(drawn?.cd
        ? [{
            id: CD_LINE,
            values: drawn.cd,
            color: (pal: LwPalette) => pal.dim(pal.refCd, 90),
            width: 1 as const,
            axis: refAxis,
            format: pctAxis ? fmtPct : fmtY,
          }]
        : []),
      ...(drawn?.policy
        ? [{
            id: BASE_LINE,
            values: drawn.policy,
            color: (pal: LwPalette) => pal.dim(pal.refPolicy, 90),
            width: 1 as const,
            /* 각진 모서리 — 정책금리는 평평하다가 뛴다(`chart/references.ts`).
               CDS 판의 `curve="stepAfter"` 자리다. */
            step: true,
            axis: refAxis,
            format: pctAxis ? fmtPct : fmtY,
          }]
        : []),
      /* 이동평균 — **종목과 같은 축**이다(같은 단위의 같은 계열의 평균이므로).
         기준선과 달리 `refAxis` 를 안 탄다: bp 차트에서도 MA 는 bp 다.

         `k` 는 **서버 목록의 첨자**다 — 점에 얹힌 `pt.ma` 가 그 순서이므로,
         켠 것만 걸러진 배열의 첨자를 쓰면 다른 창의 평균을 그리게 된다.

         불투명도는 캔버스에 손잡이가 없어 **색 자체를 흐리게** 만든다. */
      ...maWindows.flatMap((w, k) =>
        prefs.shown.includes(w)
          ? [{
              id: maSeriesId(w),
              values: view.win.map((pt) => pt.ma?.[k] ?? null),
              color: (pal: { dim: (c: string, n: number) => string }) =>
                pal.dim(maColorVar(maColorOf(prefs, w)), (MA_INK[k]?.opacity ?? 0.6) * 100),
              width: MA_INK[k]?.width ?? 1,
              format: fmtY,
            }]
          : [],
      ),
    ];
  }, [view, drawn, pctAxis, hue, row?.id, maWindows, prefs, fmtY, fmtPct]);

  /** 보이는 구간의 고·저 — CDS `Point` 자리. */
  const chartMarkers = useMemo<TimeMarker[]>(
    () =>
      view?.ext
        ? [
            { index: view.ext.hiIdx, color: (pal) => pal.fgMuted },
            { index: view.ext.loIdx, color: (pal) => pal.fgMuted },
          ]
        : [],
    [view],
  );



  const scrubLabel = useCallback(
    (i: number) => {
      const p = view?.win[i];
      return p
        ? `${p.t} ${fmtLevel(p.v, unit as Row['unit'])}${unitSuffix(unit as Row['unit'])}`
        : '';
    },
    [view, unit],
  );

  /** 커브 노드의 리드아웃 — 만기, 오늘, 그리고 전일 대비 bp.
   *
   * 변화는 **백엔드 값**(`deltas.d1`)이지 여기서 뺀 값이 아니다. 화면에 있는 두
   * 레벨을 빼면 이미 반올림된 수의 차라 표의 어제 열과 어긋날 수 있고, 그건
   * §16 이 막는 실패다. */
  const curveScrubLabel = useCallback(
    (i: number) => {
      if (!curve) return '';
      const t = curve.tenors[i];
      const n = curve.now[i];
      const d = curve.changeBp[i];
      if (n == null) return `${t} —`;
      const head = `${t} ${fmtLevel(n, '%')}%`;
      return d == null ? head : `${head} (${fmtDelta(d, 'bp')}bp)`;
    },
    [curve],
  );

  /** 커브의 선 둘. **전일이 먼저 = 아래에 깔린다.**
   *
   * 전일선 색은 `fgMutedSoft` 다 — CDS 판이 `color=fgMuted` 에
   * `strokeOpacity={0.5}` 를 겹쳐 쓰던 그 색이고, 캔버스에는 불투명도 손잡이가
   * 따로 없어 색 자체가 반투명이어야 한다(`chart/palette.ts::soften`). */
  /* 이 화면의 «안 고름» 은 `undefined` 인데 차트는 `null` 로 말한다. 여기서
     한 번 맞춘다 — **인라인 화살표로 넘기면 매 렌더 새 함수라** 크로스헤어
     구독이 렌더마다 붙었다 떨어진다. */
  const setCurveHover = useCallback((i: number | null) => setHoverIdx(i ?? undefined), []);

  const curveLines = useMemo<CurveLine[]>(() => {
    if (!curve) return [];
    const out: CurveLine[] = [];
    if (curve.prev.some((v) => v != null)) {
      out.push({ id: 'PREV', values: curve.prev, color: (p) => p.fgMutedSoft, width: 1 });
    }
    out.push({ id: 'NOW', values: curve.now, color: (p) => p.fg });
    return out;
  }, [curve]);

  /** 커브 리드아웃의 칸들 — 그려진 선과 **같은 둘**이다(오늘·전일). 종전에는
   *  카드가 값을 적고 아래 `RefKey` 줄이 이름을 적어 둘로 나뉘어 있었다. 한
   *  칸에 견본·이름·값이 같이 서면 그럴 수가 없다. */
  const curveSlots = useMemo<StripSlot[]>(() => {
    if (!curve) return [];
    /* 쉴 때는 **맨 오른쪽 노드**를 읽는다 — 시계열 차트가 쉴 때 마지막 봉을
       읽는 것과 같은 규칙이다(그림의 오른쪽 끝). 커브에는 «마지막 날» 이 없고
       «가장 긴 만기» 가 그 자리다. 줄이 빈 채로 서 있지 않게 하는 것이 이
       규칙의 요점이고, 그래야 행을 안 고른 첫 화면이 em 대시 줄로 열리지
       않는다. */
    const i =
      hoverIdx != null && hoverIdx >= 0 && hoverIdx < curve.tenors.length
        ? hoverIdx
        : curve.tenors.length - 1;
    const at = (a: readonly (number | null)[]) => fmtLevel(a[i] ?? null, '%');
    /* 자리는 커브 전체의 고·저로 잰다 — 커브는 짧아서(노드 십수 개) 매 렌더
       훑어도 공짜이고, 그래야 노드를 옮겨도 칸이 안 밀린다. */
    const ch = slotChars(
      (v) => fmtLevel(v, '%'),
      ...curve.now,
      ...curve.prev,
    );
    const out: StripSlot[] = [
      { key: 'NOW', label: '오늘', value: at(curve.now), color: 'var(--color-fg)', chars: ch },
    ];
    if (curve.prev.some((v) => v != null)) {
      out.push({
        key: 'PREV',
        label: '전일',
        value: at(curve.prev),
        color: 'var(--color-fgMuted)',
        opacity: 0.5,
        chars: ch,
        drop: 1,
      });
    }
    return out;
  }, [curve, hoverIdx]);

  /* ── 아무것도 안 고른 상태 = **IRS 파 커브** ────────────────────────────────
     빈 pane 에 "행을 고르세요" 라고 적어두는 대신 커브를 그린다. 커브 보기가 이
     제품의 1순위이고, 그건 탭과 무관하게 같은 커브다 [v1 OWNER, pass M].
     선은 둘 — 데이터 일자와 전일. 노드에 커서를 대면 스크러버가 그 노드를 읽는다.
     커브가 아예 없으면(요약 미도착) 그때는 안내 문구로 돌아간다. */
  if (!row) {
    if (!curve) {
      return (
        <VStack gap={0.5} paddingY={2}>
          <TextLabel2 as="span" color="fgMuted">
            행을 고르면 그 종목의 history 가 여기 그려져요.
          </TextLabel2>
        </VStack>
      );
    }
    /* 다른 커브에서 넘어온 인덱스는 **버린다**. pane 이 행과 커브를 오갈 때
       인덱스는 남아 있는데 가리키는 배열이 바뀌므로, 범위를 벗어난 인덱스로
       카드를 그리면 없는 만기의 값을 지어내게 된다(v1 도 같은 자리에서 같은
       가드를 둔다 — "stale until the next mouse move"). */
    const curveIdx =
      hoverIdx != null && hoverIdx >= 0 && hoverIdx < curve.tenors.length ? hoverIdx : null;
    /* `fill` 이면 이 열이 카드의 남는 높이를 전부 받는다. `minHeight={0}` 이 없으면
       flex 아이템의 기본 최소 높이가 자기 내용이라 줄지 않고, 그러면 안쪽 차트가
       카드를 넘어 자란다. */
    return (
      <VStack gap={0} width="100%" flexGrow={fill ? 1 : undefined} minHeight={0}>
        <VStack gap={0.5} paddingX={2} paddingTop={2} paddingBottom={1.5}>
          <TextLabel1 as="span" color="fgMuted" noWrap>
            IRS 커브
          </TextLabel1>
          <TextCaption as="span" color="fgMuted" noWrap>
            {curve.asof}
            {curve.prevDate ? ` · 전일 ${curve.prevDate}` : ''}
          </TextCaption>
        </VStack>
        {/* 커브의 리드아웃 줄. 히스토리 차트와 **같은 부품**이고, 만기가 날짜
            자리에 온다(v1 `ui/CurveView.tsx` 이래 두 표면이 같은 질문에 답한다:
            «커서 밑의 숫자는 얼마인가»). 52주 세 줄은 여기서도 빠졌다 —
            커브의 고·저·평균은 아래 두 선과 축이 이미 말한다. */}
        <ChartReadoutStrip
          date={curve.tenors[curveIdx ?? curve.tenors.length - 1] ?? curve.asof}
          slots={curveSlots}
          change={{
            label: READOUT_LABEL.dailyChange,
            text: fmtDeltaUnit(curve.changeBp[curveIdx ?? curve.tenors.length - 1], 'bp'),
            v: curve.changeBp[curveIdx ?? curve.tenors.length - 1],
          }}
        />
        <Box
          ref={fill ? plotRef : undefined}
          className="sr-plot"
          paddingX={1}
          flexGrow={fill ? 1 : undefined}
          flexBasis={fill ? 0 : undefined}
          minHeight={0}
          onMouseLeave={onPlotLeave}
        >
          <CurveChart
            height={chartH}
            accessibilityLabel={`IRS 파 커브, ${curve.tenors.length}개 노드`}
            nodes={curve.tenors}
            lines={curveLines}
            tickFormat={fmtPct}
            onHoverIndex={setCurveHover}
            hoverLabel={curveScrubLabel}
          />
        </Box>
      </VStack>
    );
  }

  const u = unitSuffix(row.unit);

  /* 서랍 모드 — 통계만. 히어로와 차트는 창 본문이 이미 그리고 있고, 서랍에서
   * 한 번 더 그리면 같은 차트가 한 창에 둘이 된다. */
  if (statsOnly) {
    return (
      <StatColumns row={row} view={view} u={u} />
    );
  }

  return (
    <VStack gap={0} width="100%" flexGrow={fill ? 1 : undefined} minHeight={0}>
      {/* ── hero ─────────────────────────────────────────────────────────────
          The reference puts the name small and the NUMBER large: the biggest
          thing on the page is the value, not the title of the page. */}
      <VStack gap={1.5} paddingX={2} paddingTop={2} paddingBottom={1.5}>
        <HStack justifyContent="space-between" alignItems="center" gap={2} flexWrap="wrap">
          {/* 확대 창 안에서는 이름을 창 제목이 진다 — 같은 낱말이 두 줄
              간격으로 두 번 서 있었다(전체 앱 크리틱 "확대 창 제목 중복").
              자리를 빈 span 으로 지키는 이유: 이 줄은 space-between 이라
              이름이 빠지면 기간 셀렉터가 왼쪽 끝으로 이사한다. */}
          {chartOnly ? (
            <span aria-hidden="true" />
          ) : (
            <TextLabel1 as="span" color="fgMuted" noWrap>
              {row.label}
            </TextLabel1>
          )}

          {/* CDS's own control for exactly this [OWNER 2026-08-13: CDS 컴포넌트만].
              `PeriodSelector` is a `SegmentedTabs` tuned for chart periods —
              transparent ground, a wash on the active tab, keyboard handling and
              the sliding indicator all included. The hand-rolled pill row it
              replaced had to reimplement each of those.

              The active tab still takes the CHART'S SIGN, which is the
              reference's trick — the control agrees with the picture. That is
              the one thing CDS cannot know, so it is set through a class on the
              root and read off `currentColor`. */}
          <HStack gap={1} alignItems="center">
            <Box className="sr-spans" data-dir={dir ?? 'flat'}>
              <PeriodSelector
                tabs={SPAN_TABS}
                activeTab={SPAN_TABS.find((t) => t.id === span) ?? null}
                onChange={(t) => t && setSpan(t.id as SpanKey)}
              />
            </Box>
            {/* 확대 — 떠 있는 창(레인 3)의 **첫 세입자**. 기구만 만들고 아무도
                안 살면 브라우저에서 검증할 방법이 없고, 그러면 레인 4·5 가 그
                위에 올라앉는 날 처음으로 시험받는다. 이 창은 그 자체로도 쓸모가
                있다: 같은 차트를 크게, 그리고 자리를 잡아두고 본다. */}
            {/* 확대 중일 때만 나오는 되돌리기 — 그리고 이제 **유일한** 되돌리기다
                (더블클릭 리셋은 차트 클릭 = 백테스트 복원과 함께 내렸다). */}
            {/* `.sr-enlarge` 는 **CSS 가 없는 클래스였다** [실측 2026-08-25 감사]
                — 이 둘이 브라우저 기본 버튼(UA 회색 베벨·13.3px 시스템 폰트)으로
                그려지고 있었고, 바로 옆 `PeriodSelector` 와 높이도 활자도 안
                맞았다. 이 앱의 카드-머리 컨트롤은 `.sr-pillbtn`(32px 알약)이고
                page.tsx·rv·Strategy 가 다 그것을 쓴다. 문법을 정의하는 파일이
                자기 문법 밖에 있었던 셈이다. */}
            {zoom ? (
              <button type="button" className="sr-pillbtn" onClick={() => setZoom(null)}>
                구간 전체
              </button>
            ) : null}
            {onEnlarge ? (
              <button type="button" className="sr-pillbtn" onClick={onEnlarge}>
                확대
              </button>
            ) : null}
          </HStack>
        </HStack>

        <HStack gap={1.5} alignItems="baseline" flexWrap="wrap">
          <TextDisplay3 as="span" tabularNumbers noWrap>
            {fmtLevel(row.now, row.unit)}
            {u ? (
              <Box as="span" className="sr-hero-unit">
                {u}
              </Box>
            ) : null}
          </TextDisplay3>
          {view ? (
            <TextBody
              as="span"
              tabularNumbers
              noWrap
              className={dir === 'up' ? 'sr-up' : dir === 'down' ? 'sr-down' : 'sr-flat'}
            >
              {/* **변화는 bp 다** — 레벨의 단위가 아니다 [2026-09-21 수리].
                  종전에는 `fmtDelta(net, '%') + unitSuffix('%')` 라 같은 양을
                  카드는 `+2.2`(bp), 이 줄은 `+0.2%` 로 말하고 있었다. 규약은
                  백엔드·표·표 머리 셋에 이미 박혀 있었고(`deltaUnitSuffix`
                  머리글) 이 줄만 밖에 있었다. */}
              {dir === 'up' ? '↗' : dir === 'down' ? '↘' : '→'}{' '}
              {fmtDeltaUnit(toDeltaUnit(view.net, row.unit), row.unit)}{' '}
              {/* 확대 중이면 이 변화는 **보이는 창**의 변화지 「1Y」의 변화가
                  아니다. 구간 이름을 그대로 두면 숫자와 라벨이 다른 기간을
                  말하게 되고, 그건 이 pane 이 처음부터 막으려던 실패다. */}
              <Box as="span" className="sr-hero-span">
                {zoom ? `${view.win[0].t} ~ ${view.win[view.win.length - 1].t}` : SPANS.find((s) => s.key === span)?.label}
              </Box>
            </TextBody>
          ) : null}
        </HStack>
      </VStack>

      {/* ── 리드아웃 줄 [OWNER 2026-09-21] ───────────────────────────────────
          그림 **밖**에, 그림 **위**에, 고정 높이로. 떠 있던 카드가 그림을
          가린다는 트레이더 보고에서 나온 자리다(`ui/ChartReadoutStrip.tsx`
          머리글에 경위). 이 줄이 종전의 카드와 아래 범례 줄 **둘을 대신한다** —
          견본·이름·값·토글이 한 칸에 선다.

          52주 최고·최저·평균은 여기 없다 [OWNER 2026-09-21]: 표의 52주 열과
          히어로 밑 통계가 이미 적고 있어서, 한 줄짜리 리드아웃이 그걸 또 지면
          정작 그려진 선들의 값이 밀려난다. 되살리려면 `SHOW_52W_IN_STRIP`. */}
      {view && row ? (
        <ChartReadoutStrip
          date={stripPoint.t}
          slots={stripSlots}
          change={{
            label: READOUT_LABEL.dailyChange,
            text: fmtDeltaUnit(stripPoint.d, row.unit),
            v: stripPoint.d,
          }}
        />
      ) : null}

      {/* ── chart ────────────────────────────────────────────────────────────
          Reference chrome, matched: no gridlines, y labels on the RIGHT, the
          dotted area under the line, and a scrubber. */}
      {/* `flexBasis={0}` 이 없으면 **되먹임이 생긴다**: 상자가 자기 내용(차트)에서
          기본 크기를 잡는데 그 차트의 높이가 방금 잰 상자 높이라, 잴 때마다 조금씩
          자란다. 기본 크기를 0 으로 못박으면 상자는 «남는 만큼» 만 갖고, 차트는
          그걸 채우기만 한다. 표 카드가 창을 넘어 자라던 것과 같은 규칙이다. */}
      <Box
        ref={setPlotEl}
        className="sr-plot"
        paddingX={1}
        flexGrow={fill ? 1 : undefined}
        flexBasis={fill ? 0 : undefined}
        /* 고정 높이 모드에서는 **눌리지 않는다** [실측 2026-08-18]. 안의 CDS
           차트가 고정 픽셀(chartH)이라 상자를 눌러도 그림은 안 줄고 아래로
           비어져 나오기만 한다 — Main 오버뷰에서 상자가 173px 로 눌리자 차트
           하단 27px(날짜 줄)이 범례 밑으로 새어 **글자가 글자 위에** 겹쳤다.
           눌림이 필요하면(fill) 차트도 잰 값을 따라 주니 shrink 를 허용한다. */
        flexShrink={fill ? undefined : 0}
        minHeight={0}
        /* `onMouseMove` 가 없어졌다 — 카드 자리를 CSS 변수에 적던 배선이고,
           스트립은 자리가 고정이라 잴 것이 없다(`placeReadout` 은 남은 열네
           카드가 계속 쓴다). 떠날 때 인덱스를 비우는 것은 남는다: 커서가
           나가면 스트립이 마지막 봉으로 돌아가야 한다. */
        onMouseLeave={onPlotLeave}
        /* ── 차트 클릭 = 백테스트 [v1 계약 복원, OWNER 2026-08-18] ──────────
           v1 은 차트 블록 전체가 role="button" 이었고, 클릭하면 그 행 +
           **커서가 짚고 있던 날짜**로 백테스트가 열렸다. 짚은 날이 곧 진입일
           이다 — 차트에서 "저 날 들어갔으면" 을 보다가 누르는 것이 이 진입의
           전부다.

           더블클릭 확대-리셋은 이 복원에서 **내렸다**: 첫 클릭이 창을 여는
           순간 더블클릭은 도달 불가능한 조작이 된다. 되돌리기는 확대 중에만
           나타나는 「구간 전체」 버튼이 이미 지고 있다. */
        role={onOpenBacktest && row ? 'button' : undefined}
        tabIndex={onOpenBacktest && row ? 0 : undefined}
        aria-label={onOpenBacktest && row ? `${row.label} 백테스트 열기` : undefined}
        style={onOpenBacktest && row ? { cursor: 'pointer' } : undefined}
        onClick={
          onOpenBacktest && row ? () => onOpenBacktest(row, hoverPoint?.t) : undefined
        }
        onKeyDown={
          onOpenBacktest && row
            ? (e: React.KeyboardEvent) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onOpenBacktest(row, hoverPoint?.t);
                }
              }
            : undefined
        }
      >
        {error ? (
          <TextLabel2 as="span" className="sr-up">
            history 를 불러오지 못했어요 — {error}
          </TextLabel2>
        ) : view ? (
          <TimeChart
            height={chartH}
            accessibilityLabel={`${row.label} ${SPANS.find((s) => s.key === span)?.label} 추이, ${view.win.length}개 점`}
            dates={view.win.map((p) => p.t)}
            lines={chartLines}
            markers={chartMarkers}
            onHoverIndex={setCurveHover}
            hoverLabel={scrubLabel}
          />
        ) : (
          <Box height={chartH} />
        )}
      </Box>

      {/* ── stat columns ─────────────────────────────────────────────────────
          `chartOnly` 면 통째로 빠진다 — 확대 창이 이걸 서랍에 따로 그린다. */}
      {chartOnly ? null : (
      <>
      {/* ─────────────────────────────────────────────────────────────────────
          Three groups divided by vertical hairlines, as the reference divides
          Trading Insights / Market Stats / Performance. */}
      <StatColumns row={row} view={view} u={u} />
      </>
      )}
    </VStack>
  );
}
