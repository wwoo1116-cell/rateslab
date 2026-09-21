'use client';

/* 커브 미리보기 — **실행 전에** 무엇을 돌리는지 보여준다.
 *
 * v1 화면에서 설정 옆 절반을 차지하는 pane 이고, 그게 이 화면의 절반이라는 뜻이다.
 * 한 번의 실행이 서버에서 네 케이스 × 하루 단위 전면 재평가이므로, "내가 만든 게
 * 이 커브가 맞나" 를 누르기 전에 확인할 수 있어야 한다. 확인 없이 누르면 잘못된
 * 시나리오를 돌리고 그 답을 읽는 데 시간을 쓴다.
 *
 * **미리보기와 실행은 같은 함수를 부른다** (`caseShockCurve`). 둘이 갈리면 화면이
 * 보여준 시나리오와 돌아간 시나리오가 다르고, 그건 이 화면이 막으려던 바로 그
 * 실패다.
 *
 * 브라우저가 계산하는가? 한다. 하지만 §16 이 막는 것은 **시장 데이터의 파생**이고
 * (델타·레벨·DV01은 서버가 낸다), 여기서 더하는 것은 사용자가 방금 타이핑한 bp 다.
 * 기준 커브는 서버가 준 par 그대로이고, 미리보기는 그 위에 사용자의 입력을 얹어
 * 보여줄 뿐이다 — 시장에 대한 새 주장이 아니다.
 */

import { useCallback, useMemo, useState } from 'react';

import { Chip } from '@coinbase/cds-web/chips';
import { HStack, VStack } from '@coinbase/cds-web/layout';
import { SegmentedTabs } from '@coinbase/cds-web/tabs';
import { TextLegal } from '@coinbase/cds-web/typography';

import { CurveChart, type CurveLine } from '@/chart/CurveChart';
import { NumericChart, type NumericLine } from '@/chart/NumericChart';
import type { SeriesSummary } from '@/lib/api';
import { fmtLevel } from '@/lib/format';
import { ChartReadoutStrip, slotChars, type StripSlot } from '@/ui/ChartReadoutStrip';

import {
  buildWaypoints,
  caseShockCurve,
  lerpWaypoints,
  shockAtTenor,
  SIM_CASES,
  tenorYears,
  waypointGrid,
  type CaseId,
  type Scenario,
} from './scenario';

/** 미리보기 두 종류. 밖에 두는 이유는 `SegmentedTabs` 가 `activeTab` 으로 **객체
 * 신원**을 비교하기 때문이다 — 렌더마다 새 배열을 만들면 활성 표시가 흔들린다. */
const VIEW_TABS = [
  { id: 'curve' as const, label: '커브' },
  { id: 'time' as const, label: '시계열' },
];

/** 케이스 선의 색.
 *
 * ⚠ 첫 판은 `--color-chart1`…`4` 를 썼다. **그런 토큰은 없다** — CDS 가 심는
 * `--color-*` 43개를 실측으로 세어 보니 chart 계열이 하나도 없었고, 무효값이라
 * 브라우저가 상속색으로 떨어뜨려 **네 선이 전부 같은 회색**이 됐다. 아무것도 안
 * 깨져 보이는 그 결함이다(이 리포가 폰트·면 토큰에서 이미 세 번 밟았다).
 *
 * 지금 쓰는 것은 실재하는 토큰뿐이고, **케이스의 뜻과 색을 맞춘다**:
 * Bull 은 금리 하락이라 파랑, Bear 는 상승이라 빨강 — 원화 관례와 싸우지 않는
 * 유일한 배치다. Base 는 잉크(지금 편집 중인 것), Crisis 는 더 센 상승이지만
 * Bear 와 구별돼야 해서 보라다.
 *
 * 한계를 적어 둔다: 사용자가 Bull 의 목표를 +100 으로 고치면 색이 이름과 어긋난다.
 * 색은 **씨앗의 뜻**을 말하고, 실제 방향은 칩 옆의 숫자가 말한다. 그리고 회색조에서
 * 넷을 구별할 수 없으므로 칩이 항상 이름을 같이 싣는다(DESIGN §5 의 단서). */
/** 케이스 id → 사람이 읽는 이름. 칩과 리드아웃이 **같은 이름**을 써야
 * 커서가 짚은 선이 어느 칩인지 눈으로 이어진다. `SIM_CASES` 가 원천이다. */
const CASE_LABEL: Record<string, string> = Object.fromEntries(
  SIM_CASES.map((c) => [c.id, c.label]),
);

const CASE_COLOR: Record<CaseId, string> = {
  base: 'var(--color-fg)',
  bull: 'var(--sr-down)',
  bear: 'var(--sr-up)',
  crisis: 'var(--color-accentBoldPurple)',
};

export function CurvePreview({
  height = 420,
  scenario,
  outrights,
  asOf,
  overlay,
  onToggleOverlay,
}: {
  /** 카드가 준 높이. 차트는 픽셀 숫자를 요구한다. */
  height?: number;
  scenario: Scenario;
  /** 서버가 준 par 커브. 여기서 만들지 않는다. */
  outrights: SeriesSummary[];
  asOf: string;
  /** 겹쳐 볼 케이스들. 편집 중인 케이스는 항상 켜져 있다. */
  overlay: Set<CaseId>;
  onToggleOverlay: (id: CaseId) => void;
}) {
  const [view, setView] = useState<'curve' | 'time'>('curve');

  /** 기둥은 **서버가 준 아웃라이트**다 — 프론트가 목록을 들면 화면의 커브와 표의
   * 커브가 갈릴 수 있다. 만기를 못 읽는 id 는 빠진다(지어내지 않는다). */

  /* 커서가 짚은 자리. 백테스트의 `LinkedCharts` 와 **같은 문법**이다 —
     `enableScrubbing` + `onScrubberPositionChange` 로 인덱스를 받고, 카드를
     그 x 에 띄운다. 시뮬은 경로를 설계하는 화면인데 "D+37 에 얼마" 를 읽을
     길이 없었다(v1 `sim/ui/HoverPanel.tsx` 84줄이 하던 일). */
  const [hoverIdx, setHoverIdx] = useState<number>();


  /** 리드아웃 칸 — **그려진 선 그대로**다(견본이 그 선의 잉크).
   *
   *  커브 판은 기준 + 켠 케이스들, 경로 판은 케이스별 누적 bp 다. 커서가 그림
   *  밖이면 **오른쪽 끝**을 읽는다 — 커브는 가장 긴 만기, 경로는 마지막 날이고,
   *  둘 다 「그림의 오른쪽 끝」이라는 같은 규칙이다(`ChartReadoutStrip` 머리).
   *
   *  좁아지면 켠 케이스부터 값을 내려놓는다. 기준(커브)·활성 케이스(경로)는
   *  안 내려놓는다 — 그 둘이 이 화면이 답하는 「지금 얼마」다. */
  const pillars = useMemo(
    () =>
      outrights
        .map((o) => ({ id: o.id, t: tenorYears(o.id), now: o.now }))
        .filter((x): x is { id: string; t: number; now: number | null } => x.t !== null)
        .sort((a, b) => a.t - b.t),
    [outrights],
  );

  const base = useMemo(() => pillars.map((p) => p.now), [pillars]);

  const shown = useMemo(
    () => SIM_CASES.filter((c) => c.id === scenario.activeCase || overlay.has(c.id)),
    [overlay, scenario.activeCase],
  );

  /** 케이스별 시나리오 커브 — 기준 % + 그 만기의 충격 bp / 100. */
  const caseLines = useMemo(
    () =>
      shown.map((c) => {
        const nodes = caseShockCurve(scenario, c.id, asOf);
        return {
          id: c.id,
          label: c.label,
          data: pillars.map((p, i) =>
            base[i] === null ? null : (base[i] as number) + shockAtTenor(nodes, p.t) / 100,
          ),
        };
      }),
    [shown, scenario, asOf, base, pillars],
  );

  /* 시계열 — 목표까지 가는 **경로**. 커브 뷰가 "어디에 도착하나" 라면 이쪽은
     "어떻게 가나" 다. 경유지를 꺾어 두면 여기서 꺾인 것이 보여야 한다.
 
     표본을 경유지 날에 **꼭 맞춘다** — 균등 간격만 찍으면 D+30 의 꺾임이 두 표본
     사이에 묻혀 직선처럼 보인다(설계와 미리보기가 갈리는 자리). */
  const timeLines = useMemo(() => {
    const step = Math.max(1, Math.round(scenario.days / 24));
    const daySet = new Set<number>([0, scenario.days]);
    for (let d = step; d < scenario.days; d += step) daySet.add(d);
    for (const d of waypointGrid(scenario.days)) daySet.add(d);
    const days = [...daySet].sort((a, b) => a - b);
    return {
      days,
      lines: shown.map((c) => {
        const path = buildWaypoints(scenario.cases[c.id], scenario.days);
        return {
          id: c.id,
          label: c.label,
          data: days.map((d) =>
            scenario.shape === 'ramp'
              ? lerpWaypoints(d, path)
              : d > 0
                ? scenario.cases[c.id].shockBp
                : 0,
          ),
        };
      }),
    };
  }, [shown, scenario]);

  /** 스크러버가 스크린리더에 읽어 줄 한 줄. 카드는 눈으로 보는 쪽이고 이건
      귀로 듣는 쪽이라 **둘 다** 있어야 한다(백테스트와 같은 규율). */
  const curveScrubLabel = useCallback(
    (i: number) => {
      const t = pillars[i]?.id;
      if (t == null) return '';
      const parts = caseLines.map((l) => `${CASE_LABEL[l.id] ?? l.id} ${fmtLevel(l.data[i], '%')}%`);
      return [`${t} 기준 ${fmtLevel(base[i], '%')}%`, ...parts].join(', ');
    },
    [pillars, caseLines, base],
  );

  /* 이 화면의 «안 고름» 은 `undefined` 인데 차트는 `null` 로 말한다. 한 번 맞춘다 —
     인라인 화살표로 넘기면 매 렌더 새 함수라 크로스헤어 구독이 붙었다 떨어진다. */
  const setHover = useCallback((i: number | null) => setHoverIdx(i ?? undefined), []);

  /** 커브 선들 — 기준이 먼저 = 아래에 깔린다.
   *
   * 케이스 색은 `var(--sr-…)` 라 캔버스가 못 읽는다. `palette.resolve` 가 그
   * 자리에서 계산해 준다 — 호출부는 이 리포의 어휘(CSS 변수)를 그대로 쓴다. */
  const curveLines = useMemo<CurveLine[]>(
    () => [
      { id: 'now', values: base, color: (p) => p.fgMuted, width: 1 },
      ...caseLines.map((l) => ({
        id: `case:${l.id}`,
        values: l.data,
        color: (p: { resolve: (c: string) => string }) => p.resolve(CASE_COLOR[l.id]),
      })),
    ],
    [base, caseLines],
  );

  const pathLines = useMemo<NumericLine[]>(
    () =>
      timeLines.lines.map((l) => ({
        id: `case:${l.id}`,
        values: l.data,
        color: (p: { resolve: (c: string) => string }) => p.resolve(CASE_COLOR[l.id]),
      })),
    [timeLines],
  );

  const dayLabel = useCallback((d: number) => `D+${d}`, []);
  const pctTick = useCallback((v: number) => fmtLevel(v, '%'), []);
  const bpTick = useCallback((v: number) => `${v.toFixed(0)}bp`, []);

  const timeScrubLabel = useCallback(
    (i: number) => {
      const d = timeLines.days[i];
      if (d == null) return '';
      const parts = timeLines.lines.map(
        (l) => `${CASE_LABEL[l.id] ?? l.id} ${l.data[i] == null ? '—' : `${l.data[i]!.toFixed(1)}bp`}`,
      );
      return [`D+${d}`, ...parts].join(', ');
    },
    [timeLines],
  );

  /* ── 리드아웃 줄의 칸 — 커브 판과 경로 판이 서로 다른 축을 읽는다 ─────────
     커브는 만기축·%, 경로는 날짜축·bp 다. 그래서 자리(`slotChars`)도 따로 잰다.
     쉴 때 읽는 자리는 둘 다 **그림의 오른쪽 끝**이다(커브는 가장 긴 만기,
     경로는 마지막 날) — 줄이 빈 채로 서 있지 않게 하는 그 규칙. */
  const curveAt =
    hoverIdx != null && hoverIdx >= 0 && hoverIdx < pillars.length
      ? hoverIdx : pillars.length - 1;
  const timeAt =
    hoverIdx != null && hoverIdx >= 0 && hoverIdx < timeLines.days.length
      ? hoverIdx : timeLines.days.length - 1;

  const stripDate =
    view === 'curve'
      ? (pillars[curveAt]?.id ?? asOf)
      : timeLines.days[timeAt] == null ? asOf : `D+${timeLines.days[timeAt]}`;

  const stripSlots = useMemo<StripSlot[]>(() => {
    if (view === 'curve') {
      if (!pillars.length) return [];
      const fmt = (v: number | null | undefined) => fmtLevel(v ?? null, '%');
      const ch = slotChars(
        (v) => fmtLevel(v, '%'),
        ...base, ...caseLines.flatMap((l) => l.data),
      );
      return [
        /* ⚠ 열쇠에 이름공간을 둔다 — 케이스 하나의 id 가 그냥 `base` 라
           「기준」 칸과 부딪혔다(브라우저 실측 2026-09-21: React 가 같은 열쇠
           둘을 경고했고, 그러면 칸 하나가 조용히 사라질 수 있다). */
        { key: 'ref', label: '기준', value: fmt(base[curveAt]),
          color: 'var(--color-fgMuted)', opacity: 0.6, chars: ch },
        ...caseLines.map((l, n) => ({
          key: `case:${l.id}`,
          label: CASE_LABEL[l.id] ?? l.id,
          value: fmt(l.data[curveAt]),
          color: CASE_COLOR[l.id as CaseId] ?? 'var(--color-fg)',
          chars: ch,
          /* 겹쳐 본 케이스부터 값을 내려놓는다 — 활성 케이스가 맨 앞이라
             `n === 0` 은 안 내려놓는다(그게 이 화면의 주인공이다). */
          drop: (n === 0 ? undefined : Math.min(n, 5) as 1 | 2 | 3 | 4 | 5),
        })),
      ];
    }
    if (!timeLines.days.length) return [];
    const fmtBp = (v: number | null | undefined) =>
      v == null ? '—' : `${v.toFixed(1)}bp`;
    const ch = slotChars(
      (v) => `${v.toFixed(1)}bp`,
      ...timeLines.lines.flatMap((l) => l.data.filter((x): x is number => x != null)),
    );
    return timeLines.lines.map((l, n) => ({
      key: `case:${l.id}`,
      label: CASE_LABEL[l.id] ?? l.id,
      value: fmtBp(l.data[timeAt]),
      color: CASE_COLOR[l.id as CaseId] ?? 'var(--color-fg)',
      chars: ch,
      drop: (n === 0 ? undefined : Math.min(n, 5) as 1 | 2 | 3 | 4 | 5),
    }));
  }, [view, pillars, base, caseLines, timeLines, curveAt, timeAt]);

  return (
    <VStack gap={1} width="100%" height="100%">
      <HStack gap={1} alignItems="center" flexWrap="wrap" width="100%">
        {/* CDS `SegmentedTabs` — 활성 인디케이터와 키보드 이동이 딸려 온다.
            (`SegmentedControl` 은 deprecated 다: "use Tabs or SegmentedTabs".) */}
        <SegmentedTabs
          accessibilityLabel="미리보기 종류"
          tabs={VIEW_TABS}
          activeTab={VIEW_TABS.find((t) => t.id === view) ?? null}
          onChange={(t) => t && setView(t.id)}
        />
        {/* 케이스 칩 — 편집 중인 것은 끌 수 없다(그게 지금 보고 있는 시나리오다). */}
        {SIM_CASES.map((c) => {
          const on = c.id === scenario.activeCase || overlay.has(c.id);
          return (
            <Chip
              key={c.id}
              size="xs"
              accessibilityLabel={`${c.label} 케이스 겹쳐 보기`}
              start={<span className="sr-casedash" style={{ background: CASE_COLOR[c.id] }} />}
              disabled={c.id === scenario.activeCase}
              active={on}
              onClick={() => onToggleOverlay(c.id)}
            >
              {c.label}
            </Chip>
          );
        })}
        <TextLegal as="span" color="fgMuted" noWrap style={{ marginInlineStart: 'auto' }}>
          {asOf} · D+{scenario.days}
        </TextLegal>
      </HStack>

      {/* 커서가 짚은 자리의 값 — **그림 위 한 줄**이다 [2026-09-21 이관].
          종전에는 그림 «안»에 카드가 떠서 경로를 덮었는데, 경로를 설계하는
          화면에서 덮이는 것이 하필 방금 그린 구간이었다. */}
      <ChartReadoutStrip date={stripDate} slots={stripSlots} />
      <VStack className="sr-plot" width="100%">
      {view === 'curve' ? (
        <CurveChart
          height={height}
          accessibilityLabel="시나리오 커브 미리보기"
          nodes={pillars.map((p) => p.id)}
          lines={curveLines}
          tickFormat={pctTick}
          onHoverIndex={setHover}
          hoverLabel={curveScrubLabel}
        />
      ) : (
        <NumericChart
          height={height}
          accessibilityLabel="시나리오 경로 미리보기"
          nodes={timeLines.days}
          lines={pathLines}
          label={dayLabel}
          tickFormat={bpTick}
          onHoverIndex={setHover}
          hoverLabel={timeScrubLabel}
        />
      )}
      </VStack>

      <TextLegal as="span" color="fgMuted">
        {view === 'curve' ? (
          <>
            회색이 {asOf} 현재이고, 색선이 D+{scenario.days} 시나리오예요. 위 칩을 눌러 다른
            케이스를 겹쳐 볼 수 있어요.
          </>
        ) : (
          <>
            목표까지 가는 경로예요(앵커 {scenario.anchorTenor} 기준 누적 bp).{' '}
            {scenario.shape === 'ramp'
              ? '경로 설계에서 30일 간격의 중간점을 꺾을 수 있어요.'
              : '첫날 목표까지 한 번에 가요.'}
          </>
        )}
      </TextLegal>
    </VStack>
  );
}
