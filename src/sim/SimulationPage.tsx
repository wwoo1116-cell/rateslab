'use client';

/* 시뮬레이션 — "이 포지션을 이 금리 경로에 두면 어떻게 되나".
 *
 * ── 형태는 v1 실물에서 왔다 (2026-08-14, 실제 화면 관찰) ────────────────────
 *
 * 처음에 저는 v1 의 **소스만** 읽고 이 화면을 떠 있는 창 하나로 만들었다. 계약
 * (페이로드·부호·규칙)은 맞았지만 형태는 지어낸 것이었다. swap-monitor 를 실제로
 * 열어 보니 v1 은 이렇다:
 *
 *   설정은 **전체 페이지** — 좌측 카드 열(기간·포지션·시나리오·목표금리·경로설계·
 *   커브스프레드·기준금리이벤트) + 우측 **커브 미리보기** pane.
 *   결과는 **떠 있는 창** — 실행을 눌러야 뜬다.
 *
 * 설정을 창에 넣고 결과를 그 아래 붙였던 첫 판은 두 자리를 뒤집어 놓은 것이었다.
 * 그 배치가 중요한 이유: 설정은 **오래 만지는 것**이라 넓은 자리와 옆의 미리보기가
 * 필요하고, 결과는 **읽고 닫는 것**이라 떠 있어야 뒤의 설정을 다시 만질 수 있다.
 * (v1 의 결과 창에 「조건 수정」 버튼이 있는 이유도 그것이다.)
 *
 * 셸(상단 내비·색)은 v2 것을 그대로 둔다 [OWNER 2026-08-14] — 바꾸는 것은 화면
 * **안의 구성**이다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Select } from '@coinbase/cds-web/alpha/select';
import { Button } from '@coinbase/cds-web/buttons';
import { Collapsible as CdsCollapsible } from '@coinbase/cds-web/collapsible';
import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Pressable } from '@coinbase/cds-web/system';
/* 새 코드는 `Text font=…` 를 쓴다 — CLAUDE.md 5. 남은 shorthand 는 시각 무변이라
   존치 중이고, 여기서 하나(`TextLabel2`)는 이번 얼라인 수리로 자리를 잃었다. */
import { Text, TextBody, TextLabel1, TextLegal } from '@coinbase/cds-web/typography';

import { directionLabel } from '@/backtest/book';
import { runErrorMessage, type WallSummary } from '@/lib/api';
import { fmtLevel } from '@/lib/format';
import { fmtKrw } from '@/lib/krw';
import { Field, NumField, Segmented } from '@/ui/ControlCard';
import { fitWidth, useControlFont } from '@/ui/fit';
import { CONTROL_H } from '@/ui/controlHeight';
import { useFillHeight } from '@/ui/useFillHeight';
import { IsoDateField } from '@/ui/IsoDateField';
import { DROPDOWN_STYLES } from '@/ui/window/popup';

import { CurvePreview } from './CurvePreview';
// 결과 창은 별도 파일이다 — 이 파일이 설정만으로 충분히 길다.
import { ResultsWindow } from './ResultsWindow';
import { expandInstrument, fetchInstruments, runSimulation } from './api';
import {
  ANCHOR_TENORS,
  anchorError,
  preRunErrors,
  activeCase,
  applyRateOverrides,
  buildSimulateBody,
  DEFAULT_SCENARIO,
  effectiveRate,
  hasRateOverride,
  shownWaypointBp,
  pruneWaypoints,
  setLegRate,
  waypointClampMax,
  waypointGrid,
  WAYPOINT_STEP_BP,
  isBondKind,
  isBondLeg,
  isFuturesKind,
  isFuturesLeg,
  KIND_LABEL,
  KIND_ORDER,
  kindOf,
  MAX_ROWS,
  newEvent,
  newRow,
  notionalToKrw,
  rowError,
  SIM_CASES,
  type CaseId,
  type EngineLeg,
  type InstrumentCatalog,
  type InstrumentKind,
  type RateEvent,
  type Scenario,
  type ScenarioCase,
  type SimResponse,
  type SimRow,
} from './scenario';

/** 한 시나리오에 이벤트 여섯. 2026 에 남은 회의보다 넉넉하고, 이보다 많으면 그건
 * 시나리오가 아니라 곡선이다(그 자리는 경로 설계 몫이다). */
const MAX_EVENTS = 6;

/** 미리보기 카드에서 차트가 아닌 것 — 토글·칩 줄 + 아래 설명 + 카드 여백. */
const PREVIEW_CHROME_H = 96;

/* 카탈로그·전개 캐시 — 그 날 고를 수 있는 목록과 다리는 세션 안에서 안 바뀐다.
 * 실패는 캐시하지 않는다(백엔드가 늦게 뜬 경우 다시 묻는다). */
let catalogCache: Promise<InstrumentCatalog> | null = null;
function loadCatalog(): Promise<InstrumentCatalog> {
  if (!catalogCache) {
    catalogCache = fetchInstruments().catch((e: unknown) => {
      catalogCache = null;
      throw e;
    });
  }
  return catalogCache;
}

function expandKey(baseDate: string, r: SimRow): string {
  return `${baseDate}|${r.seriesId}|${r.direction}|${r.eok}`;
}

const expandCache = new Map<string, Promise<EngineLeg[]>>();
function loadLegs(baseDate: string, r: SimRow): Promise<EngineLeg[]> {
  const k = expandKey(baseDate, r);
  let hit = expandCache.get(k);
  if (!hit) {
    hit = expandInstrument({
      seriesId: r.seriesId,
      direction: r.direction,
      notional: notionalToKrw(r.eok),
      baseDate,
    }).then((res) => res.legs);
    hit.catch(() => expandCache.delete(k));
    expandCache.set(k, hit);
  }
  return hit;
}

/** 달력 일수를 더한 ISO 날짜 — 마감일 표시용. 영업일 환산은 엔진이 한다. */
function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** 설정 카드 한 장. v1 의 카드 열과 같은 문법이다. */
function Card({
  title,
  aside,
  children,
}: {
  title: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <VStack className="sr-simcard" gap={1} width="100%">
      <HStack alignItems="baseline" gap={1} width="100%">
        <TextLabel1 as="span" noWrap>
          {title}
        </TextLabel1>
        {aside ? <Box style={{ marginInlineStart: 'auto' }}>{aside}</Box> : null}
      </HStack>
      {children}
    </VStack>
  );
}

/** 접히는 카드. **요약은 접힌 채로도 무엇이 설정돼 있는지 말한다** [v1] — 펼쳐야만
 * 알 수 있으면 설정된 값이 조용히 잊힌다.
 *
 * 몸통은 CDS `Collapsible`(높이 애니메이션·`aria-hidden` 을 그쪽이 진다), 머리는
 * CDS `Pressable`(누름 접근성). 껍데기 CSS 만 이 리포 것이다. */
function Collapsible({
  title,
  summary,
  children,
}: {
  title: string;
  summary: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <VStack className="sr-simcard" gap={open ? 1 : 0} width="100%">
      {/* 머리는 **보통 카드 머리와 같은 높이**여야 한다 — 한 열에 서는 같은
          위계의 카드들이라(CLAUDE.md 「얼라인」 5). 실측 2026-08-27: 접히는
          카드만 22px 이고 보통 카드는 20px 이었다. 뿌리는 `Pressable` 의
          `<button>` 이 **블록 자식을 인라인 줄상자에 담는** 것이라 글리프 아래
          여유가 1px 씩 붙은 것이다. 상자를 flex 로 만들면 자식을 정확히 안는다
          (`.sr-simcard-head`). */}
      <Pressable
        as="button"
        className="sr-simcard-head"
        noScaleOnPress
        accessibilityLabel={`${title} — ${summary}`}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <HStack alignItems="baseline" gap={1} width="100%">
          <TextLabel1 as="span" noWrap>
            {title}
          </TextLabel1>
          <HStack gap={0.5} alignItems="baseline" style={{ marginInlineStart: 'auto' }}>
            <TextLegal as="span" color="fgMuted" noWrap>
              {summary}
            </TextLegal>
            <span aria-hidden className="sr-simcard-chev" data-open={open || undefined}>
              ⌄
            </span>
          </HStack>
        </HStack>
      </Pressable>
      <CdsCollapsible collapsed={!open}>
        <VStack gap={1} width="100%" paddingTop={open ? 1 : 0}>
          {children}
        </VStack>
      </CdsCollapsible>
    </VStack>
  );
}

/* `Field`·`NumField` 는 여기서 정의하지 않는다 — 앱에 하나뿐인 것을 임포트한다
   (`ui/ControlCard`). `Field` 는 네 곳 복제의 정리 [OWNER 2026-08-25],
   `NumField` 는 세 곳(시뮬·rv·mr) 복제의 정리 [OWNER 2026-09-02 — "공용 부품은
   한 벌로 승격"] — blur/Enter 커밋 규율의 원산지가 이 화면이었다(2026-08-14
   실측 결함). 호출부는 종전 기본값(width 96 등)을 명시로 넘긴다. */

/** 배타 선택은 **CDS `SegmentedTabs`** 다 [OWNER 2026-08-13 §5.4 — "CDS 컴포넌트가
 * 존재하면 항상 그것을 우선한다"].
 *
 * 첫 판은 `<button>` + CSS 로 직접 만들었다. 그건 키보드 이동·활성 인디케이터·포커스
 * 링을 전부 다시 만드는 일이고, CDS 가 이미 조율해 둔 것이다(§5.4 가 `PeriodSelector`
 * 에서 얻은 이득과 같은 종류).
 *
 * `SegmentedControl` 이 아닌 이유: **deprecated 다** — 그 파일의 주석이 "Please use
 * Tabs or SegmentedTabs instead" 라고 적혀 있다. 없어질 컴포넌트로 갈아타면 다음 CDS
 * 메이저에서 다시 갈아타야 한다.
 *
 * 이 래퍼는 두 가지만 한다: 제네릭을 좁히고(케이스 id 같은 유니온), CDS 의
 * `activeTab` 객체 API 를 이 화면이 쓰는 값 API 로 바꾼다. */
/* `Segmented` 는 앱에 하나뿐이다 — `ui/ControlCard` 에서 온다(캐논 규칙 1). */

export type CaseRuns = Partial<Record<CaseId, SimResponse>>;

export function SimulationPage({
  summary,
  open,
  onOpen,
  onClose,
  runs,
  setRuns,
}: {
  summary: WallSummary;
  /** 결과 창이 떠 있나 — URL(`?sim=1`)이 주인이다. */
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
  runs: CaseRuns | undefined;
  setRuns: (r: CaseRuns | undefined) => void;
}) {
  const asOf = summary.asof;
  const [rows, setRows] = useState<SimRow[]>(() => [newRow()]);
  const [scenario, setScenario] = useState<Scenario>(DEFAULT_SCENARIO);
  const [overlay, setOverlay] = useState<Set<CaseId>>(() => new Set());
  const [catalog, setCatalog] = useState<InstrumentCatalog>();
  const [catalogError, setCatalogError] = useState<string>();
  const [legsByRow, setLegsByRow] = useState<Record<string, EngineLeg[] | { error: string }>>({});
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string>();

  /* 에러 줄은 버튼 아래에 서므로(아래 주석) 열 스크롤이 버튼에서 끝나 있으면
   * 시야 밖에 태어난다 — 태어날 때 한 번 보이는 곳까지 데려온다. */
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (error) errorRef.current?.scrollIntoView({ block: 'nearest' });
  }, [error]);

  /* 미리보기도 창의 남는 높이를 쓴다 — 표 화면과 같은 규칙(`useFillHeight`). */
  const [previewRef, previewH] = useFillHeight(420);

  useEffect(() => {
    let live = true;
    loadCatalog().then(
      (c) => {
        if (live) setCatalog(c);
      },
      (e: Error) => {
        if (live) setCatalogError(e.message);
      },
    );
    return () => {
      live = false;
    };
  }, []);

  /* 줄이 바뀌면 다리를 다시 편다. 효과가 **내용**에 걸린다 — 배열 신원에 걸면
     매 렌더마다 새 배열이라 setState → 리렌더 → 효과 로 돈다(v1 이 `useQueries`
     에서 그렇게 물려 화면이 통째로 에러 경계에 잡혔다). */
  const rowsKey = useMemo(() => rows.map((r) => expandKey(asOf, r)).join('\n'), [rows, asOf]);
  const rowsRef = useRef(rows);
  rowsRef.current = rows;

  useEffect(() => {
    let live = true;
    for (const r of rowsRef.current) {
      if (rowError(r)) continue;
      const key = r.key;
      loadLegs(asOf, r).then(
        (legs) => {
          if (live) setLegsByRow((m) => ({ ...m, [key]: legs }));
        },
        (e: Error) => {
          if (live) setLegsByRow((m) => ({ ...m, [key]: { error: e.message } }));
        },
      );
    }
    return () => {
      live = false;
    };
  }, [rowsKey, asOf]);

  /** 페이로드에 실리는 것은 줄이 아니라 **다리**다.
   *
   * 줄을 훑어서 모은다 — `Object.values` 로 평평하게 펴면 다리가 어느 줄에서 왔는지를
   * 잃고, 그러면 그 줄의 금리 덮어쓰기를 얹을 수 없다. 덮어쓰는 곳은 여기 하나다. */
  const legs = useMemo(() => {
    const out: EngineLeg[] = [];
    for (const r of rows) {
      const got = legsByRow[r.key];
      if (Array.isArray(got)) out.push(...applyRateOverrides(got, r));
    }
    return out;
  }, [rows, legsByRow]);

  const cur = activeCase(scenario);
  const patchCase = (next: Partial<ScenarioCase>) =>
    setScenario({
      ...scenario,
      cases: { ...scenario.cases, [scenario.activeCase]: { ...cur, ...next } },
    });

  /** 기간을 바꾸면 경유지 격자가 바뀐다 — 새 격자에 없는 편집은 **버린다**(v1).
   * 안 버리면 마감일이 지난 경유지를 그대로 물고 들어가 경로가 거짓이 된다.
   * 네 케이스 전부를 정리한다: 셋은 케이스 전환기 뒤에 숨어 있어서 안 하면
   * 갈아 끼우는 순간 낡은 경유지가 살아난다. */
  const setDays = (days: number) =>
    setScenario({
      ...scenario,
      days,
      cases: Object.fromEntries(
        SIM_CASES.map((c) => [
          c.id,
          { ...scenario.cases[c.id], waypoints: pruneWaypoints(scenario.cases[c.id].waypoints, days) },
        ]),
      ) as Scenario['cases'],
    });

  const patchRow = (key: string, next: Partial<SimRow>) =>
    setRows(rows.map((r) => (r.key === key ? { ...r, ...next } : r)));

  const patchEvent = (key: string, next: Partial<RateEvent>) =>
    patchCase({ events: cur.events.map((e) => (e.key === key ? { ...e, ...next } : e)) });

  /**
   * 실행 하나가 **네 케이스를 전부** 돌린다 [v1 OWNER, 2026-08-10 — "실행결과
   * 나란히 보여주는 거 ㄱㄱ"]. 넷이 병렬로 나가고, **하나라도 실패하면 전체가
   * 실패다** — 세 케이스만 있는 결과 화면은 "비교" 라는 이 화면의 목적을 반쪽으로
   * 만든다. 앵커 환산이 무너지는 케이스가 있으면 요청 전에 막고, 어느 케이스인지
   * 이름을 댄다(셋은 케이스 전환기 뒤에 숨어 있어서 안 그러면 못 찾는다).
   */
  const run = useCallback(async () => {
    /* 실행 전 검증(scenario.ts::preRunErrors) — "조용히 빠지는 것들"을 요청이
       나가기 전에 사람 말로. legs.length===0 의 무언 return 도 여기로 들어갔다:
       버튼이 눌리는데 아무 일도 없는 것은 가장 나쁜 종류의 에러 화면이다. */
    const pre = preRunErrors(rows, legsByRow, scenario, asOf, SIM_CASES);
    if (pre) {
      setError(pre);
      return;
    }
    if (legs.length === 0) {
      setError('실행할 포지션이 없어요 — 줄을 추가해 주세요.');
      return;
    }
    for (const c of SIM_CASES) {
      const bad = anchorError(scenario.cases[c.id], scenario.anchorTenor);
      if (bad) {
        setError(`${c.label} 케이스: ${bad}`);
        return;
      }
    }
    setRunning(true);
    setError(undefined);
    try {
      const results = await Promise.all(
        SIM_CASES.map(async (c) => {
          const body = buildSimulateBody(legs, scenario, asOf, c.id);
          if (!body) throw new Error('보낼 포지션이 없어요');
          return [c.id, await runSimulation(body)] as const;
        }),
      );
      setRuns(Object.fromEntries(results) as CaseRuns);
      onOpen();
    } catch (e) {
      setError(runErrorMessage(e));
    } finally {
      setRunning(false);
    }
  }, [rows, legsByRow, legs, scenario, asOf, setRuns, onOpen]);

  const optionsByKind = useMemo(() => {
    const out = {} as Record<
      InstrumentKind,
      { label: string; options: { value: string; label: string }[] }[]
    >;
    for (const k of KIND_ORDER) {
      const list = catalog?.[k] ?? [];
      out[k] = [
        { label: '주요', options: list.filter((o) => o.key) },
        { label: '전체', options: list.filter((o) => !o.key) },
      ]
        .filter((g) => g.options.length > 0)
        .map((g) => ({
          label: g.label,
          options: g.options.map((o) => ({ value: o.id, label: o.label })),
        }));
    }
    return out;
  }, [catalog]);

  /* ── 칸 폭은 **옵션 집합의 합집합**에서 [OWNER 2026-09-23] ─────────────────
     종전 주석의 산술(«크롬 82 + 최장 115 = 197»)은 손계산이라 종목이 늘어도
     다시 안 셌다. 상품 목록은 «주요/전체» 두 무리로 나뉘어 오므로 라벨을 통째로
     펴서 잰다. 폴백은 그 상수 그대로다. */
  const [fontProbe, ctlFont] = useControlFont();
  const kindW = fitWidth('select', KIND_ORDER.map((k) => KIND_LABEL[k]), ctlFont, 160);
  const prodLabels = useMemo(
    () =>
      Object.values(optionsByKind)
        .flat()
        .flatMap((g) => g.options.map((o) => o.label)),
    [optionsByKind],
  );
  const prodW = fitWidth('select', prodLabels, ctlFont, 200);

  /** 그 종류에서 처음 고를 것 — **주요의 첫 번째**다 [v1]. 아무것도 안 만졌을 때
   * 평가되는 상품이 사람이 실제로 보는 것이어야 한다. */
  const firstOf = (k: InstrumentKind): string | undefined => {
    const list = catalog?.[k] ?? [];
    return (list.find((o) => o.key) ?? list[0])?.id;
  };

  /** 고를 것이 하나도 없어서 못 옮긴 종류 [v1 642c5c46]. 채권 목록은 민평(SQL)
   * 에서 오므로 백엔드가 그것을 못 읽으면 빈 채로 온다 — 그때 셀렉트는 옛
   * 종류로 되돌아가고, 아무 말이 없으면 "왜 안 바뀌지" 만 남는다. */
  const [emptyKind, setEmptyKind] = useState<InstrumentKind | null>(null);

  /* 경로 설계가 읽는 것 — 격자와 손댄 개수, 그리고 접힌 채로 보일 요약. */
  const grid = waypointGrid(scenario.days);
  const touchedCount = grid.filter((d) => typeof cur.waypoints[d] === 'number').length;
  const pathSummary =
    scenario.shape === 'step'
      ? '첫날 한 번에'
      : touchedCount > 0
        ? `${touchedCount}개 조정함`
        : '직선';

  const cd = summary.outrights.find((o) => o.id === '3M')?.now ?? null;
  const legCount = legs.length;

  return (
    <HStack gap={2} width="100%" alignItems="stretch" flexGrow={1} minHeight={0}>
      {/* ── 설정 열 ──────────────────────────────────────────────────────────
          폭이 화면을 따라간다 [OWNER 2026-08-14]. 2560 에서 360px 은 화면의 14%
          이고, 그 폭에서는 방향 세그먼트와 다리 줄이 아래로 접힌다. 위 상한 480 은
          입력 칸이 더 넓어져도 안 읽히기 때문이다 — 넓어져야 하는 건 커브 쪽이다. */}
      <VStack
        gap={1.5}
        flexShrink={0}
        style={{ width: 'clamp(360px, 24vw, 480px)', overflowY: 'auto', minHeight: 0 }}
      >
        <Card title="기간" aside={<TextLegal as="span" color="fgMuted">D+{scenario.days}</TextLegal>}>
          <HStack gap={1.5} alignItems="flex-end" flexWrap="wrap">
            {/* 시작일은 **고르는 것이 아니다** — 데이터가 있는 마지막 날이다.
                오늘을 기본값으로 쓰면 워크북이 며칠 뒤처지는 순간 커브가 비고
                스왑이 통째로 제외되는데, 화면은 조용히 비기만 한다(v1 실패). */}
            {/* 컨트롤이 아닌 **값**도 컨트롤과 같은 32px 상자에 담는다 —
                백테스트 「진입 레벨」과 같은 관용구다(그 자리의 주석에 근거가
                있다). 이 행은 `alignItems="flex-end"` 라 **블록 높이가 곧 라벨
                높이**이고, 값이 맨살 글자면 그 칸만 라벨이 내려앉는다. 실측
                2026-08-27: 시작일·마감일 20@184 대 기간(일) 32@172 — 라벨 줄이
                12px 로 갈려 있었다. 글자도 같은 행의 입력과 같은 13px(legal)로
                맞춘다(`ui/window/popup.ts` 의 그 규칙). */}
            <Field label="시작일">
              <VStack height={CONTROL_H} justifyContent="center">
                <Text as="span" font="legal" tabularNumbers noWrap>
                  {asOf}
                </Text>
              </VStack>
            </Field>
            <Field label="기간 (일)">
              <NumField label="기간(일)" width={90} value={scenario.days} onCommit={setDays} />
            </Field>
            <Field label="마감일">
              <VStack height={CONTROL_H} justifyContent="center">
                <Text as="span" font="legal" tabularNumbers noWrap>
                  {addDays(asOf, scenario.days)}
                </Text>
              </VStack>
            </Field>
          </HStack>
          <TextLegal as="span" color="fgMuted">
            {rows.length}개 상품 · 스왑 {legCount}다리를 평가해요
          </TextLegal>
        </Card>

        <Card
          title="포지션"
          aside={
            <TextLegal as="span" color="fgMuted" tabularNumbers noWrap>
              CD 3M {cd === null ? '—' : `${fmtLevel(cd, '%')}%`}
            </TextLegal>
          }
        >
          {catalogError ? (
            <TextBody as="p" color="fgMuted">
              상품 목록을 읽지 못했어요 — {catalogError}
            </TextBody>
          ) : null}
          {emptyKind ? (
            /* 되돌아간 이유를 적는다 [v1 642c5c46]. 채권 목록은 민평(SQL)에서
               오므로 백엔드가 못 읽으면 빈 채로 온다 — 말이 없으면 "왜 안
               바뀌지" 만 남는다. */
            <TextLegal as="span" color="fgMuted">
              {KIND_LABEL[emptyKind]}에 고를 수 있는 상품이 없어요.
              {isBondKind(emptyKind)
                ? ' 민평 수익률을 못 읽었어요 — 백엔드가 SQL에 닿는지 확인해 주세요.'
                : isFuturesKind(emptyKind)
                  ? ' 선물 종가를 못 읽었어요 — 백엔드가 SQL에 닿는지 확인해 주세요.'
                  : ''}
            </TextLegal>
          ) : null}
          {rows.map((r) => {
            const got = legsByRow[r.key];
            const rowLegs = Array.isArray(got) ? got : null;
            const legErr = got && !Array.isArray(got) ? got.error : null;
            const rowKind = kindOf(r.seriesId);
            return (
              <VStack key={r.key} gap={0.5} width="100%">
                <HStack gap={1.5} alignItems="flex-end" flexWrap="wrap">
                  {/* 폭 = 최장 라벨 실측 + 컨트롤 크롬 82px(백테스트 종류 칸의
                      실측) — 말줄임 금지 [OWNER 2026-08-25, CLAUDE.md]. 종류의
                      최장 «아웃라이트/버터플라이» 5자 ≈ 65px → 82+65=147, 여유
                      13px. 150 이던 시절 여유가 3px 라 폰트가 흔들리면 잘렸다. */}
                  <Box width={kindW}>
                    {fontProbe}
                    <Field label="종류">
                      {/* font legal(13) — 컨트롤 값 13px 규칙(popup.ts 의 근거). */}
                      <Select
                        size="s"
                        font="legal"
                        styles={DROPDOWN_STYLES}
                        accessibilityLabel="종류"
                        value={rowKind}
                        onChange={(v) => {
                          const k = v as InstrumentKind;
                          const id = v && firstOf(k);
                          // 다리가 달라지므로 금리 덮어쓰기를 비운다 — 남겨 두면
                          // 3s10s 의 3Y 금리가 2s5s 의 2Y 다리에 조용히 붙는다.
                          //
                          // 채권으로 옮길 때 **방향도 되돌린다** [v1 642c5c46]. 숏
                          // 아웃라이트를 들고 있다가 현금채권을 고르면 방향 칸이
                          // 사라지면서 −1 이 남는데, 백엔드는 그걸 거절하므로
                          // (`_expand_bond`) 안 보이는 값 때문에 줄이 죽는다.
                          if (id) {
                            setEmptyKind(null);
                            patchRow(r.key, {
                              seriesId: id,
                              rateOverrides: undefined,
                              ...(isBondKind(k) ? { direction: 1 as const } : {}),
                            });
                          } else {
                            setEmptyKind(k);
                          }
                        }}
                        options={KIND_ORDER.map((k) => ({ value: k, label: KIND_LABEL[k] }))}
                      />
                    </Field>
                  </Box>
                  {/* 112 이던 칸 — 글자 자리가 30px 라 «국고채 3Y» 가 «국고…» 로
                      잘렸다(오너 신고 2026-08-25, 이 화면의 그 칸). 최장 라벨
                      «캐피탈채 AA- 10Y» ≈ 115px → 82+115=197. 열이 좁은 날은
                      flexWrap 이 명목 칸을 다음 줄로 접는다 — 접히는 건 되고
                      잘리는 건 안 된다. */}
                  <Box width={prodW}>
                    <Field label="상품">
                      <Select
                        size="s"
                        font="legal"
                        styles={DROPDOWN_STYLES}
                        accessibilityLabel="상품"
                        value={r.seriesId}
                        onChange={(v) =>
                          v && patchRow(r.key, { seriesId: v, rateOverrides: undefined })
                        }
                        options={optionsByKind[rowKind]}
                      />
                    </Field>
                  </Box>
                  {/* 단위는 라벨이 진다 — 옆에 세우면 360px 열에서 줄이 접힌다. */}
                  <Field label="명목 (억)">
                    <NumField
                      label="명목(억)"
                      width={80}
                      value={r.eok}
                      onCommit={(v) => patchRow(r.key, { eok: v })}
                    />
                  </Field>
                </HStack>
                {/* 방향은 세그먼트다 — 라벨이 문장이라(스티프너 (10Y 페이 · 3Y
                    리시브)) 드롭다운에 넣으면 잘리고, 선택지도 둘뿐이다.
                    **채권에는 방향 칸이 없다** — 살 수만 있다 [OWNER, 2026-08-14].
                    비활성 세그먼트를 놓아 두는 대신 칸을 안 그린다: 못 고르는
                    컨트롤은 "왜 안 눌리지" 를 묻게 하고, 백테스트의 현금채권
                    창도 같은 자리를 비워 두었다. */}
                {isBondKind(rowKind) ? null : (
                  <Segmented
                    label="방향"
                    value={String(r.direction) as '1' | '-1'}
                    options={[
                      { value: '1', label: directionLabel(r.seriesId, 1) },
                      { value: '-1', label: directionLabel(r.seriesId, -1) },
                    ]}
                    onChange={(v) => patchRow(r.key, { direction: v === '-1' ? -1 : 1 })}
                  />
                )}
                {/* 서버가 편 다리 — 읽기 전용. 스프레드의 명목이 반반이 아니라는
                    것(DV01 중립)은 실행 전에 보여야 하는 사실이다. */}
                {legErr ? (
                  <TextLegal as="span" color="fgMuted">
                    다리를 세우지 못했어요 — {legErr}
                  </TextLegal>
                ) : rowLegs ? (
                  <VStack gap={0.25} width="100%">
                    {rowLegs.map((l) => {
                      const rate = effectiveRate(l, r);
                      const off = rate !== l.couponRate;
                      const bond = isBondLeg(l);
                      /* 선물 다리 [2026-08-25]: 매수/매도 문법, 값은 기준일 종가의
                         내재수익률(읽기 전용 — 엔진의 폐형 재값매김이 이 값을
                         기준으로 충격을 얹는다). 만기 줄은 안 적는다: 연결
                         선물에는 만기가 없고 합성채 만기는 상수(3Y/10Y)다. */
                      if (isFuturesLeg(l)) {
                        const y0 = typeof l.mtmYield === 'number' ? l.mtmYield : null;
                        return (
                          <HStack key={l.id} gap={0.75} alignItems="center" flexWrap="wrap">
                            <TextLegal as="span" color="fgMuted" tabularNumbers noWrap>
                              {l.name} {l.direction > 0 ? '매수' : '매도'}{' '}
                              {fmtKrw(l.notional).replace(/^\+/, '')}
                            </TextLegal>
                            <TextLegal
                              as="span"
                              color="fgMuted"
                              tabularNumbers
                              noWrap
                              title="선물 종가의 내재수익률 (5% 합성)"
                            >
                              내재 {y0 === null ? '—' : `${y0.toFixed(4)}%`}
                            </TextLegal>
                          </HStack>
                        );
                      }
                      return (
                        <HStack key={l.id} gap={0.75} alignItems="center" flexWrap="wrap">
                          {/* 채권 다리는 수취/지급 문법이 아니다: 살 수만 있고,
                              이름이 종목군을 이미 말하므로 테너 자리에 이름을
                              놓는다 [v1 642c5c46]. */}
                          <TextLegal as="span" color="fgMuted" tabularNumbers noWrap>
                            {bond ? `${l.name} 매수` : `${l.tenor} ${l.direction > 0 ? '수취' : '지급'}`}{' '}
                            {fmtKrw(l.notional).replace(/^\+/, '')}
                          </TextLegal>
                          {bond ? (
                            /* 채권의 이 칸은 **민평**이고 읽기 전용이다. 입력칸으로
                               두면 조용한 거짓말이 된다: 엔진의 채권 캐리는
                               `mtmYield` 를 읽고 가격·pvbp 는 이미 서버에서
                               민평으로 매겨져 오므로 `couponRate` 를 고쳐도 아무
                               숫자도 안 움직인다. 스왑 다리의 par 덮어쓰기는
                               그대로 살아 있다 — 그쪽은 엔진이 실제로 쓴다. */
                            <TextLegal
                              as="span"
                              color="fgMuted"
                              tabularNumbers
                              noWrap
                              title="민평 수익률 — 표면금리와 할인율이 같아 진입가가 par 예요"
                            >
                              {rate.toFixed(4)}
                            </TextLegal>
                          ) : (
                            /* par 가 있던 자리가 그대로 입력칸이 된다 [v1 트레이더
                                피드백 3]. 새 칸을 만들지 않는 이유: 이 줄은 이미 "이
                                다리는 이 금리로 쳐진다" 를 말하고 있었다. 고칠 수 있게
                                된 것뿐이다. */
                            <NumField
                              label={`${l.tenor} 고정금리`}
                              width={86}
                              value={rate}
                              format={(v) => v.toFixed(4)}
                              onCommit={(v) => patchRow(r.key, setLegRate(r, l.id, v))}
                            />
                          )}
                          <TextLegal as="span" color="fgMuted" noWrap>
                            %
                          </TextLegal>
                          {bond ? (
                            <TextLegal as="span" color="fgMuted" tabularNumbers noWrap>
                              만기 {l.maturityDate}
                            </TextLegal>
                          ) : off ? (
                            // 되돌릴 곳. par 가 얼마였는지도 같이 말한다 — "얼마에서
                            // 옮겼나" 를 물으려고 다시 계산하게 두지 않는다.
                            <Button
                              variant="tertiary"
                              size="xs"
                              className="sr-ctlfont"
                              onClick={() => patchRow(r.key, setLegRate(r, l.id, null))}
                            >
                              par {l.couponRate.toFixed(4)}%로
                            </Button>
                          ) : (
                            <TextLegal as="span" color="fgMuted" tabularNumbers noWrap>
                              만기 {l.maturityDate}
                              {l.startDate !== asOf ? ` · ${l.startDate} 시작` : ''}
                            </TextLegal>
                          )}
                        </HStack>
                      );
                    })}
                    {hasRateOverride(rowLegs, r) ? (
                      /* 사실 하나를 말한다. par 진입은 MtM 0 에서 출발하지만 옮긴
                         진입은 아니다 — 결과의 평가손익에 **경로가 만들지 않은 몫**이
                         처음부터 섞여 있다는 뜻이고, 그걸 모르면 숫자를 잘못 읽는다. */
                      <TextLegal as="span" color="fgMuted">
                        금리를 par에서 옮겼어요. 진입 시점 평가손익이 0이 아니에요.
                      </TextLegal>
                    ) : null}
                  </VStack>
                ) : null}
                {rows.length > 1 ? (
                  <Box>
                    <Button
                      variant="tertiary"
                      size="xs"
                      className="sr-ctlfont"
                      onClick={() => setRows(rows.filter((x) => x.key !== r.key))}
                    >
                      삭제
                    </Button>
                  </Box>
                ) : null}
              </VStack>
            );
          })}
          <Box>
            <Button
              variant="secondary"
              size="xs"
              className="sr-ctlfont"
              disabled={rows.length >= MAX_ROWS}
              onClick={() => setRows([...rows, newRow(rows.at(-1)?.seriesId)])}
            >
              포지션 추가
            </Button>
          </Box>
        </Card>

        <Card title="시나리오">
          <Segmented
            label="케이스"
            value={scenario.activeCase}
            options={SIM_CASES.map((c) => ({ value: c.id, label: c.label }))}
            onChange={(v) => setScenario({ ...scenario, activeCase: v })}
          />
          <TextLegal as="span" color="fgMuted">
            네 케이스가 한 번에 돌아요. 여기서 고른 케이스가 결과 창에 먼저 보여요.
            불은 금리 하락, 베어는 상승이에요(주식과 반대예요).
          </TextLegal>
        </Card>

        <Card title="목표 금리" aside={<TextLegal as="span" color="fgMuted">국고</TextLegal>}>
          <Field label="앵커 테너">
            <Segmented
              label="앵커 테너"
              value={scenario.anchorTenor}
              options={ANCHOR_TENORS.map((t) => ({ value: t, label: t }))}
              onChange={(v) => setScenario({ ...scenario, anchorTenor: v })}
            />
          </Field>
          <HStack gap={1.5} alignItems="flex-end">
            <Field label={`국고 ${scenario.anchorTenor} 목표 변동`}>
              <NumField
                label="목표 변동(bp)"
                width={110}
                value={cur.shockBp}
                onCommit={(v) => patchCase({ shockBp: v })}
              />
            </Field>
            {/* 단위 꼬리표도 32px 상자에 담는다 — 안 담으면 `flex-end` 가 글자를
                입력 상자 **바닥**에 붙이고, 입력의 글자는 32px 안에서 가운데라
                둘의 시선 높이가 어긋난다(실측 2026-08-27: 32 대 16). */}
            <VStack height={CONTROL_H} justifyContent="center">
              <TextLegal as="span" color="fgMuted">
                bp · D+{scenario.days} 시점
              </TextLegal>
            </VStack>
          </HStack>
          {anchorError(cur, scenario.anchorTenor) ? (
            <TextLegal as="span" className="sr-up">
              {anchorError(cur, scenario.anchorTenor)}
            </TextLegal>
          ) : null}
        </Card>

        {/* 경로 설계 — **D+0 과 마감일은 고정 핀**이고, 30일 간격의 중간점만 손댈 수
            있다. 시작은 0 이고 끝은 위 목표 금리 칸이 정한다. */}
        <Collapsible title="경로 설계" summary={pathSummary}>
          <Segmented
            label="경로 모양"
            value={scenario.shape}
            options={[
              { value: 'ramp', label: '경유지' },
              { value: 'step', label: '첫날 한 번에' },
            ]}
            onChange={(v) => setScenario({ ...scenario, shape: v })}
          />
          {scenario.shape === 'step' ? (
            <TextLegal as="span" color="fgMuted">
              첫날 목표까지 한 번에 가요. 경유지는 안 써요.
            </TextLegal>
          ) : grid.length === 0 ? (
            <TextLegal as="span" color="fgMuted">
              기간이 60일보다 짧아서 중간 지점이 없어요. 경로는 직선이에요.
            </TextLegal>
          ) : (
            <VStack gap={0.5} width="100%">
              {grid.map((day) => {
                // 보여주는 값 ≠ 싣는 값. 안 손댄 날은 여기 직선 값이 보이지만
                // 페이로드에는 안 들어간다(`buildWaypoints` 의 실측 주석 참조).
                const bp = shownWaypointBp(cur, day, scenario.days);
                const clamp = waypointClampMax(cur.shockBp);
                const set = (v: number) =>
                  patchCase({
                    // 손댔다는 것은 **명시 플래그**다(키의 존재). 값으로 추론하면
                    // 우연히 직선 위에 놓인 편집이 목표를 바꾸는 순간 지워진다.
                    waypoints: {
                      ...cur.waypoints,
                      [day]: Math.max(-clamp, Math.min(clamp, v)),
                    },
                  });
                return (
                  <HStack key={day} gap={0.75} alignItems="center">
                    <TextLegal as="span" color="fgMuted" tabularNumbers noWrap>
                      D+{day}
                    </TextLegal>
                    <Box style={{ marginInlineStart: 'auto' }}>
                      <NumField label={`D+${day} 변동폭`} width={86} value={bp} onCommit={set} />
                    </Box>
                    {/* 스테퍼는 입력 **오른쪽**이다. 값 양옆에 −/+ 를 세우면 부호
                        있는 값에서 "−" 가 한 줄에 두 번 나온다. 걸음은 목표 칸과
                        같은 5bp — 다른 눈금을 쓰면 손으로 맞춰 놓은 경로가 목표를
                        한 번 누를 때마다 어긋난다. */}
                    <Button
                      variant="secondary"
                      size="xs"
                      className="sr-ctlfont"
                      accessibilityLabel={`D+${day} ${WAYPOINT_STEP_BP}bp 내리기`}
                      onClick={() => set(bp - WAYPOINT_STEP_BP)}
                    >
                      −
                    </Button>
                    <Button
                      variant="secondary"
                      size="xs"
                      className="sr-ctlfont"
                      accessibilityLabel={`D+${day} ${WAYPOINT_STEP_BP}bp 올리기`}
                      onClick={() => set(bp + WAYPOINT_STEP_BP)}
                    >
                      +
                    </Button>
                    <TextLegal as="span" color="fgMuted" noWrap>
                      bp
                    </TextLegal>
                  </HStack>
                );
              })}
              {touchedCount > 0 ? (
                <Box>
                  <Button
                    variant="tertiary"
                    size="xs"
                    className="sr-ctlfont"
                    onClick={() => patchCase({ waypoints: {} })}
                  >
                    직선으로 되돌리기
                  </Button>
                </Box>
              ) : null}
            </VStack>
          )}
        </Collapsible>

        <Collapsible
          title="커브 스프레드"
          summary={cur.spread1y === 0 && cur.spread10y === 0 ? '평행' : `1Y ${cur.spread1y} · 10Y ${cur.spread10y}`}
        >
          <TextLegal as="span" color="fgMuted">
            3Y 대비 얼마나 더(덜) 움직이는지예요. 둘 다 0이면 3Y 위쪽이 나란히 움직여요.
          </TextLegal>
          <HStack gap={1.5} alignItems="flex-end">
            <Field label="1Y (bp)">
              <NumField
                label="1Y 스프레드(bp)"
                width={100}
                value={cur.spread1y}
                onCommit={(v) => patchCase({ spread1y: v })}
              />
            </Field>
            <Field label="10Y (bp)">
              <NumField
                label="10Y 스프레드(bp)"
                width={100}
                value={cur.spread10y}
                onCommit={(v) => patchCase({ spread10y: v })}
              />
            </Field>
          </HStack>
        </Collapsible>

        <Collapsible
          title="기준금리 이벤트"
          summary={cur.events.length ? `${cur.events.length}건` : '없음'}
        >
          <TextLegal as="span" color="fgMuted">
            기준금리가 얼마나 움직이는지, CD는 기준금리 대비 얼마나 움직이는지 알려주세요.
            없으면 지평 내내 그대로예요 — 그때는 짧은 끝도 안 움직여요.
          </TextLegal>
          {cur.events.length === 0 ? (
            <TextLegal as="span" color="fgMuted">
              등록된 이벤트가 없어요.
            </TextLegal>
          ) : null}
          {cur.events.map((ev) => (
            <HStack key={ev.key} gap={1} alignItems="flex-end" flexWrap="wrap">
              {/* 금통위 날짜는 **강조**로 온다(`highlight`) — 종전의
                  `<datalist>` 자리다. 그 자리의 규칙은 그대로다: «고르는 것을
                  돕되 막지 않는다». 강조는 `disabledDates` 가 아니고, 달력
                  안에서 보이며 스크린리더가 그 사실을 읽는다. */}
              <Box width={160}>
                <IsoDateField
                  label="날짜"
                  value={ev.date}
                  min={asOf}
                  onChange={(iso) => patchEvent(ev.key, { date: iso })}
                  highlight={summary.policy.upcoming ?? []}
                  highlightHint="금통위 예정일"
                  outOfRangeMessage="기준일보다 앞선 날짜는 못 써요."
                />
              </Box>
              <Field label="기준금리">
                <NumField
                  label="기준금리 변동(bp)"
                  width={84}
                  value={ev.shiftBp}
                  onCommit={(v) => patchEvent(ev.key, { shiftBp: v })}
                />
              </Field>
              <Field label="CD 추가">
                <NumField
                  label="CD 추가(bp)"
                  width={84}
                  value={ev.cdSpreadBp}
                  onCommit={(v) => patchEvent(ev.key, { cdSpreadBp: v })}
                />
              </Field>
              <Button
                variant="tertiary"
                size="xs"
                className="sr-ctlfont"
                onClick={() => patchCase({ events: cur.events.filter((x) => x.key !== ev.key) })}
              >
                삭제
              </Button>
            </HStack>
          ))}
          <Box>
            <Button
              variant="secondary"
              size="xs"
              className="sr-ctlfont"
              disabled={cur.events.length >= MAX_EVENTS}
              onClick={() =>
                patchCase({
                  events: [
                    ...cur.events,
                    newEvent(nextMeeting(summary.policy.upcoming, cur.events)),
                  ],
                })
              }
            >
              이벤트 추가
            </Button>
          </Box>
        </Collapsible>

        <Button
          block
          size="xs"
          className="sr-ctlfont"
          onClick={() => void run()}
          disabled={running || legs.length === 0}
        >
          {/* 실행 하나 = 케이스 넷(scenario.ts SIM_CASES) — 넷을 돈다고 말해야
              한 케이스 분량을 기대한 손이 기다림을 이해한다. */}
          {running ? '네 케이스를 나란히 돌리는 중…' : '시뮬레이션 실행'}
        </Button>
        {/* 에러는 버튼 **아래**에 선다 — 위에 서면 나타날 때마다 실행 버튼이
            아래로 밀려, 재시도하려는 손이 움직인 버튼을 쫓게 된다. 대신 시야
            밖에 태어날 수 있어서 위의 scrollIntoView 가 데려온다. */}
        {error ? (
          <Box ref={errorRef}>
            <TextBody as="p" className="sr-up">
              실행하지 못했어요 — {error}
            </TextBody>
          </Box>
        ) : null}
        {runs && !open ? (
          <Box>
            <Button variant="tertiary" size="xs" className="sr-ctlfont" onClick={onOpen}>
              지난 결과 다시 보기
            </Button>
          </Box>
        ) : null}
      </VStack>

      {/* ── 미리보기 pane ──────────────────────────────────────────────────── */}
      <VStack
        ref={previewRef}
        className="sr-simcard"
        gap={1}
        flexGrow={1}
        minWidth={420}
        minHeight={0}
      >
        <CurvePreview
          height={Math.max(280, previewH - PREVIEW_CHROME_H)}
          scenario={scenario}
          outrights={summary.outrights}
          asOf={asOf}
          overlay={overlay}
          onToggleOverlay={(id) =>
            setOverlay((prev) => {
              const next = new Set(prev);
              if (next.has(id)) next.delete(id);
              else next.add(id);
              return next;
            })
          }
        />
      </VStack>

      {open && runs ? (
        <ResultsWindow
          runs={runs}
          scenario={scenario}
          asOf={asOf}
          onClose={onClose}
        />
      ) : null}
    </HStack>
  );
}

/** 아직 안 쓴 회의 중 가장 가까운 날. 없으면 빈 문자열 — 사람이 직접 적는다. */
function nextMeeting(upcoming: string[] | undefined, used: { date: string }[]): string {
  const taken = new Set(used.map((e) => e.date));
  return (upcoming ?? []).find((d) => !taken.has(d)) ?? '';
}
