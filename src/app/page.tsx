'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { HStack, VStack } from '@coinbase/cds-web/layout';
import { TextBody, TextCaption, TextTitle3 } from '@coinbase/cds-web/typography';

import {
  fetchCashBondInstruments,
  fetchForwards,
  fetchHealth,
  fetchVolatility,
  fetchWallSummary,
  type CashBondInstruments,
  type ForwardsPayload,
  type Health,
  type VolatilityPayload,
  type WallSummary,
} from '@/lib/api';
import { levelHeadText, levelHeadTitle } from '@/lib/format';
import { idleCurve } from '@/chart/curve';
import { resolveStart, rowsFor, startPoints } from '@/table/forwardStarts';
import { InstrumentTable } from '@/table/InstrumentTable';
import { buildRows, GROUP_LABEL, type Group, type Row } from '@/table/rows';
import { filterByType, toCashBondRows } from '@/table/cashbondRows';
import { fetchUniverse, toRows, type UniversePayload } from '@/table/universeRows';
import { BottomStrip, useStripCollapsed } from '@/ui/BottomStrip';
import { ChangeLog } from '@/ui/ChangeLog';
import { CurveBanner } from '@/ui/CurveBanner';
import { ErrorState, FreshnessChip, LoadingState } from '@/ui/DataState';
import { ErrorBoundary } from '@/ui/ErrorBoundary';
import { ForwardMatrix, KeyForwardBlock } from '@/ui/ForwardMatrix';
import {
  DEFAULT_GROUP,
  NOT_BUILT,
  SECTIONS,
  sectionOf,
  type TabId,
} from '@/ui/nav';
import { OverviewColumns } from '@/ui/OverviewColumns';
import { PreviewPane } from '@/ui/PreviewPane';
import { useFillHeight } from '@/ui/useFillHeight';
import { BacktestWindow, encodeBook, seedBook } from '@/backtest/BacktestWindow';
import type { BookRow } from '@/backtest/book';
import { bookIdOf, defaultEntry, newRow } from '@/backtest/book';
import { SettingView } from '@/ui/SettingView';
import { BondTypeFilter } from '@/ui/BondTypeFilter';
import { SimulationPage, type CaseRuns } from '@/sim/SimulationPage';
import { MomentumPage } from '@/momentum/MomentumPage';
import { MrPage } from '@/mr/MrPage';
import { RvPage } from '@/rv/RvPage';
import { FloatingWindow } from '@/ui/window/FloatingWindow';
import { StartFilter } from '@/ui/StartFilter';
import { TopNav } from '@/ui/TopNav';
import { useUrlState } from '@/ui/useUrlState';
import {
  LAB_ITEMS,
  STRATEGY_ITEMS,
  resolveLab,
  resolveStrategy,
  type LabId,
  type StrategyId,
} from '@/ui/nav';
import { Surface3D } from '@/ui/Surface3D';
import { IssuancePage } from '@/lab/IssuancePage';
import { ModelSpace } from '@/lab/model/ModelSpace';

/** Swap groups first (v1's), then the Cash Bond pair (2026-08-18).
 *
 * 국고·본드스왑·크레딧·국채선물은 여기서 내려갔다 [OWNER 2026-08-19 — "가상
 * 데이터가 들어갔던 본드스왑, 국고, 국채선물, 크레딧 지워주고"]. 이 배열이 곧
 * URL 게이트라(`tab` 판정), 빠진 그룹은 딥링크로도 열리지 않고 DEFAULT_GROUP
 * 으로 떨어진다. 유니버스 백엔드·행 어댑터는 남아 있다 — 되살리려면 여기(와
 * `nav.ts` 의 BACKTEST_CATEGORIES)에 도로 넣고 rows 메모에 `toRows` 를 다시
 * 잇는다. */
const GROUPS: Group[] = [
  'outright',
  'spread',
  'fly',
  'forward',
  'vol',
  'cashbond',
  'asw',
  /* 국채선물·퓨처스왑이 **되돌아왔다** [OWNER, 2026-08-25 — "선물, 퓨처스왑도
     스왑·현금채권과 같은 분류에"]. 2026-08-19 축소의 사유(가상 데이터)가 이
     둘에는 더 이상 해당하지 않는다 — 근거와 되살린 범위는 `nav.ts` 의 같은
     자리에 적었다. 국고·본드스왑·크레딧은 여전히 빠져 있다. */
  'futures',
  'futuresswap',
];

/** Which feed each group's freshness comes from. The two close on the same day today,
 * but they are different feeds and must be able to disagree on screen — averaging
 * them away is the silent-staleness defect this product keeps having. */
const SOURCE_OF: Record<Group, 'irs' | 'universe'> = {
  outright: 'irs', spread: 'irs', fly: 'irs', forward: 'irs', vol: 'irs',
  govt: 'universe', bss: 'universe', credit: 'universe', futures: 'universe',
  /* 퓨처스왑은 두 피드의 교집합이라 백엔드가 **늦은 쪽**으로 자기 항목을 낸다
   * (`universe.py` sources.futuresswap) — 여기서 선물 항목을 가리키면 IRS 가
   * 하루 밀린 날 헤더가 조용히 신선해 보인다(아래 FRESH_KEY 가 고친 그 결함). */
  futuresswap: 'universe',
  /* 현금채권 = credit_matrix, 자산스왑 = credit_matrix × mkt_irs_close —
   * 유니버스의 govt/bss 항목이 각각 정확히 그 피드다 (`FRESH_KEY`). */
  cashbond: 'universe', asw: 'universe',
};

/** 신선도 항목 키가 그룹 이름과 다른 곳. 현금채권도 자산스왑도 **민평 달력**
 * 위에 선다(`asw_series` 는 민평 날짜에 IRS 를 맞춘다 — backend/app/cashbond.py)
 * — bss(교집합의 max, IRS 가 하루 앞설 수 있다)를 가리키면 헤더 날짜와 표의
 * 마지막 관측이 어긋난다(실측 2026-08-18: 헤더 08-17, 값 08-14). */
const FRESH_KEY: Partial<Record<Group, string>> = {
  cashbond: 'govt', asw: 'govt', futuresswap: 'futuresswap',
};

const SOURCE_LABEL = { irs: 'IRS 종가', universe: '민평·선물 종가' } as const;

/** 보이는 줄 중 처음으로 **담을 수 있는** 것의 엔진 id. 세 자리가 같은 폴백을
 * 쓰므로 한 번만 적는다. */
function firstBookId(rows: Row[]): string | null {
  for (const r of rows) {
    const id = bookIdOf(r);
    if (id) return id;
  }
  return null;
}

type Loaded = {
  summary: WallSummary;
  forwards: ForwardsPayload;
  vol: VolatilityPayload;
  universe: UniversePayload;
  cashbond: CashBondInstruments;
  health: Health;
};

export default function Home() {
  const [data, setData] = useState<Loaded>();
  const [error, setError] = useState<string>();
  const [retrying, setRetrying] = useState(false);
  /* Screen state lives in the URL so a view is linkable and the back button works.
   * Filters use replaceState — a chip press is not a destination; the selected row
   * uses pushState, because closing a selection is the one step back a reader expects.
   * Neither goes through the router (see useUrlState for the production defect that
   * ruling came out of). */
  const [groupParam, setGroupParam] = useUrlState('g', 'outright');
  const [selectedId, setSelectedId] = useUrlState('r', undefined, 'push');

  /* Lab 안에서 지금 보고 있는 세입자 [2026-08-20]. **탭이 아니라 URL 상태**다 —
     탭을 늘리면 `sectionOf()` 가 드는 «섹션은 유도값» 규칙에 두 번째 상태가
     끼어든다. 모르는 값은 기본 세입자로 떨어진다(딥링크 게이트, GROUPS 와 같은
     규율). */
  const [labParam, setLabParam] = useUrlState('lab');
  /* 내려간 세입자의 링크는 **갈 곳으로 옮긴다**(`resolveLab`). 시나리오가
     2026-08-21 에 「모형」으로 내려갔고, 그 주소를 공유해 둔 사람이 있다. */
  const lab: LabId = resolveLab(labParam);

  /* Strategy 안에서 지금 보고 있는 전략 [OWNER 2026-08-24]. Lab 과 **같은
     기계**다 — 탭이 아니라 URL 상태이고, 모르는 값은 기본 세입자로 떨어진다.
     키가 아예 없는 예전 `?g=strategy` 링크도 여기로 떨어지는데, 지금 세입자가
     하나뿐이라 그 링크들이 가리키던 화면 그대로다. */
  const [stratParam, setStratParam] = useUrlState('s');
  const strategy: StrategyId = resolveStrategy(stratParam);


  /* ONE value in the URL, and the section is derived from it (`ui/nav.ts`).
   * Splitting section and tab into two states makes combinations representable
   * that the screen does not have — "Backtest with no asset class" — which is
   * v1's ruling, carried. */
  const NON_GROUP: TabId[] = ['all', 'sim', 'strategy', 'setting', 'lab'];
  const tab = (
    GROUPS.includes(groupParam as Group) || NON_GROUP.includes(groupParam as TabId)
      ? groupParam
      : DEFAULT_GROUP
  ) as TabId;

  const section = sectionOf(tab);
  const isGroupTab = GROUPS.includes(tab as Group);

  /* Backtest returns to the LAST asset class looked at, not always 아웃라이트 —
   * otherwise someone reading spreads who steps into Main once loses their place. */
  const lastGroupRef = useRef<Group>(DEFAULT_GROUP);
  if (isGroupTab) lastGroupRef.current = tab as Group;
  const group = (isGroupTab ? tab : lastGroupRef.current) as Group;

  /* 페이지 제목은 **지금 보고 있는 것의 이름**이다. Backtest 가 섹션 이름이 아니라
     «아웃라이트» 를 h1 으로 쓰는 것과 같은 규칙 — Lab 도 세입자 이름을 쓴다
     [디자인 얼라인 2026-08-20]. 그래야 카드 안에 같은 제목을 한 번 더 적지 않는다. */
  const sectionTitle = isGroupTab
    ? GROUP_LABEL[group]
    : section === 'lab'
      ? (LAB_ITEMS.find((i) => i.id === lab)?.label ?? 'Lab')
      : section === 'strategy'
        ? (STRATEGY_ITEMS.find((i) => i.id === strategy)?.label ?? 'Strategy')
        : (SECTIONS.find((s) => s.id === section)?.label ?? 'Main');

  const load = useCallback(async () => {
    setError(undefined);
    setRetrying(true);
    try {
      const [summary, forwards, vol, universe, cashbond, health] = await Promise.all([
        fetchWallSummary(), fetchForwards(), fetchVolatility(), fetchUniverse(),
        fetchCashBondInstruments(), fetchHealth(),
      ]);
      setData({ summary, forwards, vol, universe, cashbond, health });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRetrying(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const rows = useMemo(() => {
    if (!data) return [];
    /* 유니버스는 **탭이 있는 그룹만** 잇는다(2026-08-19 축소의 규칙 그대로) —
     * 탭이 없는 행을 rows 에 남기면 커맨드 바 검색이 열 수 없는 화면으로
     * 점프한다. 그래서 `GROUPS` 를 그대로 게이트로 쓴다: 여기 목록과 탭 목록이
     * 두 번 적히면 언젠가 갈라진다. 지금 통과하는 것은 국채선물·퓨처스왑
     * 넷뿐이고, 국고·본드스왑·크레딧은 GROUPS 에 없으니 그대로 걸러진다. */
    return [
      ...buildRows(data.summary, data.forwards, data.vol),
      ...toCashBondRows(data.cashbond),
      ...toRows(data.universe).filter((r) => GROUPS.includes(r.group)),
    ];
  }, [data]);

  /* The screener row is gone [OWNER 2026-08-13 — "필터 항목은 없애주고"], so the
   * rows shown are simply the group's — plus the forward tab's ONE remaining
   * narrowing, the start point (§3). It survives the chip cull because it is not
   * a preset over the same list: 21 starts × 7 tenors is 140 rows, and reading
   * "3M 시작" is reading a different curve section, not a filtered view of one.
   * `SCREENERS` still exists in `table/screener.ts` with its predicates intact;
   * nothing reads it now. */
  const [startParam, setStartParam] = useUrlState('fs');
  const starts = useMemo(() => startPoints(rows), [rows]);
  const start = resolveStart(startParam, starts, group);
  /* 현금채권·자산스왑 탭의 하나 남은 좁히기 — 종목군 (`BondTypeFilter`).
     포워드 시작점과 같은 규칙으로 URL 에 산다. */
  const [bondTypeParam, setBondTypeParam] = useUrlState('ct');
  const isCashBondTab = group === 'cashbond' || group === 'asw';
  const bondType =
    isCashBondTab && data?.cashbond.types.some((t) => t.id === bondTypeParam)
      ? (bondTypeParam as string)
      : null;
  const shown = useMemo(() => {
    const base = rowsFor(rows, group, start);
    if (!isCashBondTab || !data) return base;
    return filterByType(base, data.cashbond.rows, bondType);
  }, [rows, group, start, isCashBondTab, data, bondType]);

  /* ── hover preview ────────────────────────────────────────────────────────
   * The pane answers the row under the pointer, and falls back to the pinned
   * row when there is none. Hover is NOT in the URL: a pointer crossing the
   * table is not a destination, and writing it would put a history entry (or a
   * replace) behind every row it passes.
   *
   * 120ms [v1 §2]: crossing twelve rows to reach the thirteenth would otherwise
   * fire twelve series fetches and strobe the chart. The delay is on ARRIVAL
   * only — leaving clears at once, because a pane still showing a row the
   * pointer has left is the stale-state defect, and no reader is waiting on it.
   */
  const HOVER_MS = 120;

/** 커브 배너 한 줄이 표 위에서 먹는 높이. 아웃라이트 탭에서만 선다. */
const BANNER_H = 34;

/* 미리보기 카드의 차트 높이는 **여기서 안 정한다.**
 *
 * 예전엔 `PREVIEW_CHROME_H = 176` 을 빼서 줬고, 그 숫자가 89px 모자랐다 —
 * 실측 2026-08-14: 히어로 128 + 범례 22 + 통계 115 = **265**. 그만큼 차트가 커져서
 * 통계 3열(「이 구간」·「변화」·「52주」)이 카드 밖으로 88px 밀려났고, `.sr-card` 가
 * `overflow: hidden` 이라 통째로 잘렸다. 화면에서는 그 정보가 **그냥 없었다.**
 *
 * 상수를 89 올리는 것이 답이 아니다. 그 셋은 고정 높이가 아니다 — 범례는 기준선이
 * 있을 때만 서고(bp·ratio 차트엔 없다), 통계 3열은 폭에 따라 접힌다. 어떤 상수를
 * 넣어도 어떤 화면에서는 틀린다. 그래서 `PreviewPane` 이 **남는 높이를 스스로 재게**
 * 했다(`fill`). 표 쪽이 `useFillHeight` 로 이미 쓰는 방법과 같다. */
  const [hoveredId, setHoveredId] = useState<string>();
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const onHover = useCallback((row?: Row) => {
    clearTimeout(hoverTimer.current);
    if (row) hoverTimer.current = setTimeout(() => setHoveredId(row.id), HOVER_MS);
    else setHoveredId(undefined);
  }, []);
  useEffect(() => () => clearTimeout(hoverTimer.current), []);

  /* Resolved against the CURRENT tab's rows, not held as an object: a row from
   * the tab you just left resolves to nothing here and the pane falls back to
   * the pin, rather than showing an instrument that is no longer on screen. */
  const pinnedRow = shown.find((r) => r.id === selectedId);
  const previewRow = shown.find((r) => r.id === hoveredId) ?? pinnedRow;

  /* 아이들 커브는 **탭과 무관하게 하나** — IRS 파 커브다 [v1 OWNER, pass M].
     그래서 `shown` 이 아니라 요약에서 바로 만든다. */
  const idle = useMemo(() => idleCurve(data?.summary), [data?.summary]);

  /* 확대 창 — 레인 3(떠 있는 창)의 첫 세입자. URL 에 산다(`?w=`): 자리를 잡아
     둔 창은 링크로 넘길 만한 상태이고, 뒤로가기로 닫히는 것도 자연스럽다.
     `replace` 인 이유는 `useUrlState` 의 규칙 그대로 — 창을 여닫는 것은
     목적지가 아니다. 행이 사라지면(탭 이동) 창도 닫힌다. */
  const [enlargedId, setEnlarged] = useUrlState('w');
  const enlargedRow = enlargedId ? shown.find((r) => r.id === enlargedId) : undefined;

  /* ── 백테스트 창 (레인 4) ──────────────────────────────────────────────
     열려 있음 = URL 에 `bt` 가 있음이다. v1 의 규칙 그대로 — 인스턴스가 하나뿐
     이라는 사실이 상태 하나로 표현되고, 그래서 두 개가 될 수가 없다. 북 자체가
     그 파라미터에 실리므로 **링크가 곧 북**이다: 붙여넣으면 같은 질문이 뜬다.
     쓰기는 replace(창을 여닫는 건 목적지가 아니다). */
  const [btParam, setBtParam] = useUrlState('bt');
  const [book, setBookState] = useState<BookRow[]>([]);
  const btOpen = btParam != null;

  /* 북은 URL 과 화면 상태를 함께 움직인다 — 한쪽만 바뀌면 링크가 거짓말을 한다. */
  const setBook = useCallback(
    (next: BookRow[]) => {
      setBookState(next);
      setBtParam(encodeBook(next) || ' ');
    },
    [setBtParam],
  );

  const openBacktest = useCallback(() => {
    /* 씨앗은 **엔진의 id** 다. 선물 줄의 Main id(`FUT-KTB3`)를 그대로 심으면
       북이 스왑으로 읽어 실행할 때 422 가 난다 — `bookIdOf` 가 그 자리를
       한 번만 옮긴다. */
    const seedId =
      (previewRow ? bookIdOf(previewRow) : null) ??
      firstBookId(shown) ??
      '10Y';
    /* 진입일 기본은 **씨앗 상품**이 정한다(`defaultEntry`). 현금채권 탭에서
       이 버튼을 누르면 씨앗이 채권 줄인데, 거기 오늘을 심으면 캐리가 하루도
       안 쌓여 늘 «거의 0» 인 북이 뜬다. */
    const seeded = seedBook(
      btParam,
      seedId,
      data?.summary.asof ?? '',
      data?.cashbond.asof ?? '',
      data?.cashbond.from ?? '',
    );
    setBook(seeded);
  }, [btParam, previewRow, shown, data, setBook]);

  /* **차트를 눌러서 들어간다** [v1 계약 복원, OWNER 2026-08-18 — "원래 백테스트는
     그래프를 눌러서 들어갔었는데"]. v1 은 pane 의 차트 블록 전체가 role="button"
     이었고, 클릭하면 그 행 + **커서가 짚고 있던 날짜**(`btf`)로 백테스트가 열렸다
     (`v1 ui/PreviewPane.tsx:199` `onOpen(row, hoveredDate)`).

     버튼 진입과 다른 점 하나: **기억된 북을 되살리지 않고 새로 심는다.** 특정
     차트의 특정 날짜를 눌렀다는 것은 명시적인 질문이라, 지난번 북이 대신 뜨면
     날짜 힌트가 영영 안 먹는 것처럼 보인다(v1 도 클릭마다 새 bt 키를 민팅했다).
     담을 수 없는 행(포워드·변동성 등)이면 버튼과 같은 폴백으로 간다. */
  const openBacktestAt = useCallback(
    (row: Row, from?: string) => {
      /* 현금채권·자산스왑도 **같은 북**이다 [OWNER, 2026-08-21]. 진입일은 짚은
         날짜가 먼저이고, 없으면 그 상품의 기본이다(`defaultEntry` — 채권은
         캐리가 쌓여야 읽히는 화면이라 1년 전이다). 담을 수 없는 줄(포워드·
         변동성·선물 저평가)이면 버튼과 같은 폴백으로 간다 — 「담을 수 있나」와
         「무엇으로 담기나」가 한 질문이라 게이트도 하나다. */
      const bookId = bookIdOf(row);
      if (!bookId) {
        openBacktest();
        return;
      }
      const entry =
        from ??
        defaultEntry(
          bookId,
          data?.summary.asof ?? '',
          data?.cashbond.asof ?? '',
          data?.cashbond.from ?? '',
        );
      setBook([newRow(bookId, entry)]);
    },
    [openBacktest, setBook, data],
  );

  /* 링크로 들어온 경우: URL 에 북이 있으면 그걸로 화면을 세운다(한 번만). */
  useEffect(() => {
    if (!btOpen || book.length > 0 || !data) return;
    setBookState(
      seedBook(
        btParam,
        firstBookId(shown) ?? '10Y',
        data.summary.asof,
        data.cashbond.asof,
        data.cashbond.from,
      ),
    );
  }, [btOpen, btParam, book.length, data, shown]);


  /* 시뮬레이션 **결과 창** — 설정은 페이지에 있고 결과만 뜬다(v1 형태).
     URL 에 존재만 싣는다(`?sim=1`): 입력이 페이지에 있어서 값을 실을 자리가 아니다. */
  const [simParam, setSim] = useUrlState('sim');
  const simOpen = simParam != null;

  /* 표로 보기 — 포워드 격자. 다른 창들과 같은 규칙으로 URL 에 존재만 싣는다. */
  const [matrixParam, setMatrix] = useUrlState('fm');
  const matrixOpen = matrixParam != null;
  const [simRuns, setSimRuns] = useState<CaseRuns>();

  /* 표와 미리보기는 **창의 남는 높이를 전부** 쓴다 [OWNER 2026-08-14].
   *
   * 상수 560 이었고, 2560×1140 화면에서 아래 428px 이 빈 채 표가 1,022px 짜리
   * 내용을 8행만 보여주며 자체 스크롤했다. 화면은 남는데 내용이 갇힌 상태다.
   * 둘 다 픽셀 숫자를 요구하므로(가상화 스크롤러 · CDS 차트) 재서 내려준다. */
  const [tableCardRef, tableH] = useFillHeight(560);

  /** 한 종목으로 **이동**한다 — 탭과 행이 함께 정해진다. 커맨드 바와 하단 띠가
   * 둘 다 이걸 부른다: 탭을 안 옮기면 고른 행이 이 탭에 없어서 아무 일도 안
   * 일어난 것처럼 보이고, 두 곳이 각자 구현하면 언젠가 한쪽만 그렇게 된다. */
  const jumpTo = useCallback(
    (r: Row) => {
      setGroupParam(r.group);
      setSelectedId(r.id);
    },
    [setGroupParam, setSelectedId],
  );

  /* 하단 기준점 띠. 접힘은 새로고침을 넘어 기억된다(`ui/BottomStrip.tsx`).
     띠가 기둥의 마지막 아이템이라 접히면 그 높이가 그대로 내용으로 간다 —
     `useFillHeight` 가 재는 값이 저절로 따라오므로 맞출 숫자가 없다. */
  const [stripCollapsed, setStripCollapsed] = useStripCollapsed();

  const src = SOURCE_OF[group];
  const freshKey = FRESH_KEY[group] ?? group;
  const fresh =
    src === 'irs'
      ? { asof: data?.health.asof, level: data?.health.freshness?.level }
      : {
          asof: data?.universe.sources[freshKey]?.asof ?? data?.universe.asof,
          level: data?.universe.sources[freshKey]?.level,
        };

  return (
    /* The ground. `className` rather than CDS's `background` prop because the
       page tone flips between schemes in a way no single CDS token expresses —
       see the surface note in `theme/direction.css`. */
    /* 페이지가 **뷰포트에 묶인다** — `minHeight` 가 아니라 `height` 다.
     *
     * 실측 2026-08-14: `minHeight` 로는 flex 가 나눌 **정해진** 높이가 없어서,
     * 재서 내려준 높이가 내용을 키우고 그 내용이 다시 더 큰 측정값을 만드는
     * 되먹임이 생겼다(오버뷰 카드가 1,214 화면에서 2,106px 까지 자랐다).
     * `height` 면 flex 가 **남는** 높이를 나누므로 그 고리가 끊긴다.
     *
     * 잘리지 않나: 안쪽이 각자 스크롤한다(표 스크롤러 · 설정 열 · 서랍). v1 도
     * "페이지가 스크롤하지 않으므로" 를 전제로 실행 버튼을 바닥에 고정한다. */
    <VStack className="sr-page" height="100vh" overflow="hidden" gap={0}>
      <TopNav
        tab={tab}
        lab={lab}
        strategy={strategy}
        lastGroup={group}
        onNavigate={(t, labId, stratId) => {
          setGroupParam(t);
          /* Lab 을 떠나면 세입자 키를 URL 에서 걷는다 — 안 걷으면 Backtest 를
             보는 주소에 세입자 키가 남아 공유한 링크가 거짓을 말한다. */
          setLabParam(t === 'lab' ? (labId ?? lab) : undefined);
          /* Strategy 도 같은 기계다 [2026-08-24 → 2026-08-25 둘째 입주로 Lab 과
             완전히 같아졌다]: 패널에서 고른 세입자를 적고, 섹션 버튼이면 지금
             세입자를 유지한다. 「기본값은 주소에 안 적는다」던 한-세입자 시절
             규칙은 선택이 상태가 되면서 은퇴했다 — 예전 `?g=strategy` 링크는
             여전히 기본 세입자로 떨어진다(resolveStrategy). */
          setStratParam(t === 'strategy' ? (stratId ?? strategy) : undefined);
          setSelectedId(undefined);
          // a pending hover from the tab being left must not land on the new one
          clearTimeout(hoverTimer.current);
          setHoveredId(undefined);
        }}
        right={
          <>
            {/* 변화 기록은 **늘 있다** — 비어 있음 자체가 정보다("조용한 하루").
                변화가 없는 날 버튼이 사라지면 "조용하다" 와 "이 기능이 없다" 가
                구분되지 않는다. */}
            {data ? (
              <ChangeLog
                events={data.summary.events}
                onFocus={(id) => {
                  const r = rows.find((x) => x.id === id);
                  if (r) jumpTo(r);
                }}
              />
            ) : null}
            {/* 선/주봉/월봉 토글이 여기 살았다가 오너 지시로 제거됐다
                [OWNER 2026-08-18 — "주봉 월봉 없애도 될 거 같고"]. */}
            <FreshnessChip
              asof={fresh.asof}
              level={fresh.level as 'current' | 'behind' | 'stale' | undefined}
              source={SOURCE_LABEL[src]}
            />
          </>
        }
      />

      {/* 내용이 내비 아래 **남는 높이를 전부** 받는다. `minHeight={0}` 이 없으면
          flex 아이템의 기본 최소 높이가 자기 내용이라 줄지 않고, 그러면 안쪽 카드가
          창을 넘어 자란다(창 기구에서 겪은 것과 같은 규칙). */}
      <VStack gap={2} padding={3} width="100%" flexGrow={1} minHeight={0}>
        {/* 제목 줄이 포워드 탭에서만 컨트롤을 하나 더 진다. 표 위 별도의 필터
            줄을 만들지 않는 건 오너 지시(칩 줄 제거)의 연장이다 — 컨트롤 한
            개는 제목과 같은 줄에 산다. */}
        {/* 제목 줄은 **바닥 정렬**이다 [2026-08-27]. 필터가 `Field` 문법으로
            오면서 라벨이 컨트롤 **위**에 서고 블록이 50px 이 되는데, 가운데
            정렬이면 그 블록이 제목과 알약을 위아래로 밀어 셋의 밑선이 갈린다.
            바닥으로 맞추면 컨트롤·알약·제목이 **같은 밑선**에 서고 라벨만 그
            위로 올라간다 — 「얼라인」 3 이 설정 줄에 대해 말하는 그것이다. */}
        <HStack alignItems="flex-end" justifyContent="space-between" gap={2} width="100%">
          <TextTitle3 as="h1">{sectionTitle}</TextTitle3>
          <HStack gap={1} alignItems="flex-end">
            {group === 'forward' && isGroupTab ? (
              <>
                <StartFilter starts={starts} value={start} onChange={setStartParam} />
                {/* 같은 데이터, 다른 질문. 목록은 "이 포워드가 얼마인가" 이고
                    표는 "**어디가 움직였나**" 다 — 140행을 스크롤해서는 색의
                    모양을 볼 수 없다. 떠 있는 창인 이유는 목록을 밀어내지 않고
                    나란히 두기 위해서다. */}
                {/* 제목 줄 우측 창 트리거 — 아래 "백테스트" 와 같은 32px pill
                    문법(주석 참조). */}
                <button type="button" className="sr-pillbtn" onClick={() => setMatrix('1')}>
                  표로 보기
                </button>
              </>
            ) : null}
            {/* 현금채권·자산스왑 탭의 하나 남은 좁히기 — 종목군. 포워드
                시작점과 같은 자리·같은 규칙(제목 줄의 Select 하나). */}
            {isCashBondTab && data ? (
              <BondTypeFilter
                types={data.cashbond.types.filter((t) =>
                  data.cashbond.rows.some(
                    (r) => r.kind === (group === 'asw' ? 'ASW' : 'CB') && r.bondType === t.id,
                  ),
                )}
                value={bondType ?? undefined}
                onChange={setBondTypeParam}
              />
            ) : null}
            {/* 백테스트는 **작업대**라 탭 옆에 산다 — 지금 보고 있는 종목이 곧
                첫 줄이 된다. 담을 수 없는 종목(포워드·변동성·민평·선물)을 보고
                있으면 이 탭의 첫 담을 수 있는 종목으로 씨앗을 잡는다.
                현금채권 탭은 자기 창을 연다 — 엔진이 다르다. */}
            {isGroupTab && data ? (
              /* 카드-머리 우측의 창 트리거는 앱 전체가 한 문법이다 — RV 의
                 "설정"·"커브 레인"과 같은 32px pill(.sr-pillbtn, Main 기간
                 셀렉터 실측에서 온 14/600/32). CDS Button size s 는 36 이라 이
                 자리만 4px 튀어 있었다(전체 앱 크리틱 실측 2026-08-19). */
              <button
                type="button"
                className="sr-pillbtn"
                onClick={openBacktest}
              >
                백테스트
              </button>
            ) : null}
          </HStack>
        </HStack>

        {/* A section with no screen yet says WHY, and says what is already in place.
            "아직 없음" with no reason reads as a bug; naming the part that IS done
            (the simulation's four routers are on this server) makes it a plan. */}
        {section === 'main' && !isGroupTab ? (
          /* Main 은 **세 열 오버뷰**다 [OWNER 2026-08-14] — 그 전까지는 아웃라이트
             표를 그대로 보여줘서 Backtest 와 같은 화면이 둘이었다. 규칙과 근거는
             `ui/OverviewColumns.tsx`. */
          data ? (
            <VStack ref={tableCardRef} width="100%" flexGrow={1} minHeight={0}>
              {/* 영역마다 경계 하나 — 오버뷰가 죽어도 내비와 신선도 칩은 남는다. */}
              <ErrorBoundary region="오버뷰" fallback="오버뷰를 그리지 못했어요.">
                <OverviewColumns
                  rows={rows}
                  policy={data.summary.policy}
                  levelHeader={levelHeadText(fresh.asof)}
                  levelHeaderTitle={levelHeadTitle(fresh.asof)}
                  height={tableH}
                />
              </ErrorBoundary>
            </VStack>
          ) : null
        ) : section === 'simulation' && !isGroupTab ? (
          /* 시뮬레이션은 **전체 화면**이다 — 설정 열 + 커브 미리보기(v1 형태).
             결과만 떠 있는 창으로 뜬다. */
          data ? (
            <ErrorBoundary region="시뮬레이션" fallback="시뮬레이션 화면을 그리지 못했어요.">
              <SimulationPage
                summary={data.summary}
                open={simOpen}
                onOpen={() => setSim('1')}
                onClose={() => setSim(undefined)}
                runs={simRuns}
                setRuns={setSimRuns}
              />
            </ErrorBoundary>
          ) : null
        ) : section === 'setting' && !isGroupTab ? (
          /* Setting — 다른 화면이 읽는 값을 정하는 자리 [OWNER, 2026-08-14].
             데이터가 없어도 선다: 저장은 브라우저 몫이고 서버는 출처만 답한다. */
          <ErrorBoundary region="설정" fallback="설정 화면을 그리지 못했어요.">
            <SettingView />
          </ErrorBoundary>
        ) : section === 'strategy' && !isGroupTab ? (
          /* Strategy 의 세입자 [OWNER 2026-08-24 분리 → 2026-08-25 둘째 입주].
             Credit RV 와 Mean Reversion — Lab 과 같은 모양의 분기이고, 예고대로
             둘째가 들어오며 `nav.ts::PANELED` 에 'strategy' 가 붙어 메가 패널이
             열렸다.

             둘 다 라이브 전용이라(민평·BSS·선물이 SQL 에만) 데이터 로드와
             무관하게 자기 fetch 로 선다. */
          <ErrorBoundary
            region={STRATEGY_ITEMS.find((i) => i.id === strategy)?.label ?? '전략'}
            fallback="전략 화면을 그리지 못했어요."
          >
            {strategy === 'credit-rv' ? (
              <RvPage />
            ) : strategy === 'mean-reversion' ? (
              <MrPage />
            ) : (
              <MomentumPage />
            )}
          </ErrorBoundary>
        ) : section === 'lab' && !isGroupTab ? (
          /* Lab 의 세입자 = **커브 표면** [v1 2026-08-14]. v1 의 첫 세입자
             (라고 할 때 살걸)는 거기서 내려갔으므로 옮겨오지 않는다 — 백엔드의
             `/api/regret` 은 v2 에도 있지만 그 화면은 v1 에서 지워진 화면이다. */
          <ErrorBoundary
            region="연구실"
            fallback={
              lab === 'issuance'
                ? '발행 캘린더를 그리지 못했어요.'
                : lab === 'model'
                  ? '모형 화면을 그리지 못했어요.'
                  : '커브 표면을 그리지 못했어요.'
            }
          >
            {lab === 'issuance' ? (
              <IssuancePage />
            ) : lab === 'model' ? (
              /* 세션 1 이 세운 껍데기. 세 면의 내용은 다음 두 세션이 각자
                 자기 슬롯 안에만 넣는다 — 이 분기와 셸은 안 건드린다. */
              <ModelSpace />
            ) : (
              <Surface3D policy={data?.summary.policy} />
            )}
          </ErrorBoundary>
        ) : !isGroupTab && NOT_BUILT[section] ? (
          <VStack gap={0.5} paddingY={2} maxWidth={620}>
            <TextBody as="p" color="fgMuted">
              {NOT_BUILT[section]}
            </TextBody>
          </VStack>
        ) : error ? (
          <ErrorState what="시장 데이터" detail={error} onRetry={() => void load()} retrying={retrying} />
        ) : !data ? (
          <LoadingState what="시장 데이터" />
        ) : (
          <>
            {shown.length === 0 ? (
              <VStack gap={0.5} paddingY={2}>
                <TextCaption as="span" color="fgMuted">
                  {GROUP_LABEL[group]}에 아직 데이터가 없어요.
                </TextCaption>
              </VStack>
            ) : (
              /* Two cards on the ground. The table's signed numbers therefore sit
                 on `--sr-card`, which is the only surface measured to hold them
                 at 4.5:1 in both schemes. */
              <HStack
                gap={2}
                alignItems="stretch"
                width="100%"
                flexGrow={1}
                minHeight={0}
              >
                {/* 980, and like 860 before it this is arithmetic, not taste.
                    The ladder's rung list now ends in 세타, and MEASURED in the
                    running app (ch 8.6, Pretendard SR 14px) the full set needs

                      label 157 + 현재 104 + 변화 3개 209        =  470  (columns)
                      + 52주 227 + 위치 76 + 세타 125 + 셀 인셋 16 =  444  (one cell)
                                                                 =  914  of TABLE

                    and the table runs ~17px narrower than this card (scroll
                    container borders + the vertical scrollbar). 940 left it
                    4px short — which does not clip a number, it silently turns
                    the last column off, exactly as the 760 cap did to 위치.
                    Below this width the ladder drops from the tail (세타 → 위치
                    → 52주), visibly and by rule.

                    ── 그리고 `maxWidth` 만으로는 안 됐다 (실측 2026-08-14) ──
                    두 카드가 `width: 100%` 로 나란히 서 있으면 flex 가 남는
                    폭을 **반씩** 나눈다: 1920 화면에서 표 카드는 캡과 무관하게
                    928px 였고(=(1920−48−16)/2), 그래서 860→940 캡 인상은 아무
                    것도 바꾸지 못했다. 폭은 캡이 아니라 **basis** 로 준다 —
                    표는 사다리가 필요한 만큼 가져가고, 미리보기가 남는 걸 전부
                    받는다(v1 의 "표는 열에 맞춰, 미리보기가 나머지" 규칙). */}
                <VStack
                  ref={tableCardRef}
                  className="sr-card"
                  flexBasis={980}
                  flexGrow={0}
                  flexShrink={1}
                  maxWidth={980}
                  minHeight={0}
                >
                  {/* 커브 전체가 한쪽 끝에 몰렸을 때만 나타나는 한 줄 (§I).
                      아웃라이트 탭에서만 — 판정 입력이 아웃라이트 커브뿐이라,
                      국고·크레딧 표 위에 띄우면 그 표에 대한 말로 읽힌다.
                      카드 안에 두는 것도 규칙이다: 방향색은 카드 위에서만
                      4.5:1 을 넘는다 (DESIGN §3.2). */}
                  {group === 'outright' ? <CurveBanner banner={data.summary.curveBanner} /> : null}
                  {/* 표와 미리보기는 **각자** 경계를 진다. 한 경계로 묶으면 미리보기
                      한 줄의 결함이 표까지 지우고, 그러면 화면이 무엇이 고장났는지
                      말하지 못한다. */}
                  <ErrorBoundary region="표" fallback="표를 그리지 못했어요.">
                  <InstrumentTable
                    rows={shown}
                    onSelect={(r: Row) => setSelectedId(r.id)}
                    onHover={onHover}
                    selectedId={selectedId}
                    /* 월-일만. 연도는 이 헤더가 아니라 툴팁과 상단 신선도 칩이
                       진다 [OWNER 2026-08-14] — 셀 좌우 16px 씩을 CDS 가 먹어서
                       `2026-08-13` 이 72px 안에서 두 줄로 접히고 있었다. */
                    levelHeader={levelHeadText(fresh.asof)}
                    levelHeaderTitle={levelHeadTitle(fresh.asof)}
                    /* 카드가 준 높이에서 배너 한 줄을 뺀다 — 배너는 아웃라이트
                       탭에서만 서고, 안 빼면 그 탭에서만 표가 카드를 넘는다. */
                    height={tableH - (group === 'outright' ? BANNER_H : 0)}
                  />
                  </ErrorBoundary>
                </VStack>
                {/* 남는 폭 전부. `minWidth` 는 바닥이고, 그 바닥에 닿으면 이제
                    표 쪽이 줄면서 사다리가 꼬리부터 열을 떨군다. */}
                <VStack
                  className="sr-card"
                  flexGrow={1}
                  flexBasis={380}
                  minWidth={380}
                  minHeight={0}
                >
                  {/* 기준금리 스텝은 표 전체에 하나다 — 행이 아니라 화면의
                      성질이라 pane 이 스스로 가져오지 않고 여기서 내려준다. */}
                  <ErrorBoundary region="미리보기" fallback="이 종목의 차트를 그리지 못했어요.">
                    <PreviewPane
                      row={previewRow}
                      policy={data.summary.policy}
                      curve={idle ?? undefined}
                      onEnlarge={previewRow ? () => setEnlarged(previewRow.id) : undefined}
                      /* 차트 클릭 = 백테스트 [v1 계약]. **이 pane 에만** 단다 —
                         전체탭 오버뷰 차트는 v1 에서도 안 열렸고, 확대 창 안에서
                         열면 창 위에 창이 선다. */
                      onOpenBacktest={openBacktestAt}
                      /* 히어로·범례·통계가 자기 높이를 먼저 가져가고, 차트가 남는
                         것을 전부 쓴다. 위 주석 참조 — 상수로 빼면 통계가 잘린다. */
                      fill
                    />
                  </ErrorBoundary>
                </VStack>
              </HStack>
            )}

            {/* `universe.absent` 각주(종목별 크레딧·5년 선물)는 은퇴했다
                [OWNER 2026-08-19] — 둘 다 그날 내려간 자산군에 대한 말이라,
                화면에 없는 것의 부재 사유를 바닥에 남기면 그게 소음이다. */}
          </>
        )}
      </VStack>

      {/* 커맨드 바는 은퇴했다 [OWNER 2026-08-19 — "커맨드바도 없애"]. 종목
          이동은 기준점 띠의 앵커가 진다(같은 jumpTo). */}

      {/* 기준점 띠는 **모든 탭**에 선다 — 어느 화면에 있든 10Y 가 어디인지가
          같은 자리에 있어야 한다는 것이 이 띠의 존재 이유다. 그래서 `shown` 이
          아니라 `rows` 를 받는다(포워드 탭에 10Y 아웃라이트 행은 없다).
          경계는 compact — 34px 안에 문단이 들어갈 자리가 없다. */}
      <ErrorBoundary region="기준점 띠" fallback="기준점을 그리지 못했어요." compact>
        <BottomStrip
          rows={rows}
          collapsed={stripCollapsed}
          onCollapsed={setStripCollapsed}
          onPin={jumpTo}
        />
      </ErrorBoundary>

      {/* 창은 페이지 흐름 밖에 산다(fixed). 열림은 상태 하나이고 그 상태가 곧
          DOM 이다 — 닫힘을 애니메이션에 맡기지 않는다(이 리포의 "안 닫히는 창"
          두 번의 교훈). */}
      {/* 창은 자기 경계를 진다 — 창 안이 죽어도 뒤의 표는 살아 있고, 닫기는
          `FloatingWindow` 의 헤더가 아니라 **URL** 이 쥐고 있어서 여전히 닫힌다. */}
      {/* 창은 **하나**다 [OWNER, 2026-08-21]. 종전에는 IRS 와 현금채권이 각자
          창을 열었고 URL 키도 둘(`bt`·`cb`)이었다. 한 북에 스왑과 채권이 같이
          서는 지금은 그 갈래가 곧 두 개의 답을 뜻하므로 남겨 둘 수 없다 —
          `cb` 링크는 이제 열리지 않고, 북은 전부 `bt` 에 실린다. */}
      {btOpen && data ? (
        <ErrorBoundary region="백테스트 창" fallback="백테스트 결과를 그리지 못했어요.">
        <BacktestWindow
          rows={rows}
          cashbondRows={data.cashbond.rows}
          cashbondTypes={data.cashbond.types}
          cashbondAsOf={data.cashbond.asof}
          cashbondFrom={data.cashbond.from}
          asOf={data.summary.asof}
          policy={data.summary.policy}
          book={book}
          setBook={setBook}
          onClose={() => {
            setBtParam(undefined);
            setBookState([]);
          }}
        />
        </ErrorBoundary>
      ) : null}

      {/* 표로 보기 — 격자 + 주요 포워드 + 틴트 범례. 창 폭은 21×8 격자가
          가로 스크롤 없이 서는 데 필요한 만큼이고, 넘치면 격자 자신이 스크롤한다
          (`.sr-matrix-wrap`). */}
      {matrixOpen && data ? (
        <ErrorBoundary region="표로 보기" fallback="포워드 표를 그리지 못했어요.">
          <FloatingWindow
            windowKey="matrix"
            title="포워드 표"
            width={1080}
            onClose={() => setMatrix(undefined)}
            drawer={[
              {
                id: 'key',
                label: '주요 포워드',
                content: <KeyForwardBlock payload={data.forwards} />,
              },
            ]}
          >
            <ForwardMatrix payload={data.forwards} />
          </FloatingWindow>
        </ErrorBoundary>
      ) : null}

      {enlargedRow && data ? (
        <ErrorBoundary region="확대 창" fallback="확대한 차트를 그리지 못했어요.">
        <FloatingWindow
          windowKey="chart"
          title={enlargedRow.label}
          onClose={() => setEnlarged(undefined)}
          drawer={[
            {
              id: 'stats',
              label: '통계',
              content: (
                <PreviewPane
                  row={enlargedRow}
                  policy={data.summary.policy}
                  height={0}
                  statsOnly
                />
              ),
            },
          ]}
        >
          <PreviewPane
            row={enlargedRow}
            policy={data.summary.policy}
            height={460}
            chartOnly
          />
        </FloatingWindow>
        </ErrorBoundary>
      ) : null}
    </VStack>
  );
}
