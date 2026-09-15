'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@coinbase/cds-web/tables';
import { useSortableCell } from '@coinbase/cds-web/tables/hooks/useSortableCell';
import { TextCaption, TextLabel1, TextLabel2, TextLegal } from '@coinbase/cds-web/typography';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';

import type { BasisKey } from '@/lib/api';
import { fmtDelta } from '@/lib/format';
import { fmtKrw } from '@/lib/krw';
import { rangePosition } from '@/lib/range';

import { levelText, rangeText, subText } from './cells';
import { colSpecs, colStyle } from './colgroup';
import {
  ALL_COLUMNS,
  rangeTemplate,
  visibleColumns,
  type VisibleColumns,
} from './columns';
import type { Row } from './rows';
import { hasTheta, THETA_LABEL, THETA_TITLE, thetaTitle } from './theta';
import { HEADER_H, OVERSCAN, ROW_H } from './rowHeight';
import { byAbsChange, byTenor, unmappedRows } from './sortKey';
import { directionClass, directionGlyph, tintStyle, unsignedDelta } from './tint';
import { ROW_ATTR, ROW_SELECTOR, useFlipReorder } from './useFlipReorder';

/** 변화 열의 머리글 — **앱 하나에 한 벌**이다(캐논). 다른 표가 같은 양을 보여줄
 * 때 여기서 가져다 쓴다. 손으로 다시 적으면 한쪽만 낡는다. */
export const BASIS_LABEL: Record<BasisKey, string> = { d1: '1D', mtd: 'MTD', ytd: 'YTD' };

/**
 * 52주 레인지 안에서 오늘이 어디인지 — 낮은 쪽에서 높은 쪽으로 그은 선 위의 표식.
 *
 * v1 의 `RangeTrack` 과 같은 규칙이다: **옆에 인쇄된 숫자에서 자리를 낸다**.
 *
 * 이 문장은 2026-08-20 까지 거짓이었다. 주석은 "같은 필드를 읽는다" 고 적혀
 * 있었는데 실제로는 서버의 `pct`(순위 백분위)를 `left` 에 넣고 있었고, 옆의
 * 숫자는 최저·최고·평균이었다 — 다른 양이다. 실측 99행 중 20행이 10%p 넘게,
 * 최대 23.9%p 어긋났다. 이제 `lib/range.ts` 하나가 그 자리를 낸다.
 *
 * 그릴 수 없는 행은 트랙을 그리지 않는다 — 0% 로 그리면 "바닥에 있다" 는 없는
 * 사실을 말하게 된다.
 */
function RangeTrack({
  now,
  low,
  high,
}: {
  now: number | null;
  low: number | null;
  high: number | null;
}) {
  /* 자리는 **옆에 인쇄된 숫자에서** 나온다(`lib/range.ts`). 2026-08-19 까지는
     서버의 `pct`(순위 백분위)를 `left` 에 그대로 넣고 있었고, 그건 최저↔최고
     트랙 위의 자리와 다른 양이라 그림과 숫자가 다른 말을 했다 — 실측 99행 중
     20행이 10%p 넘게, 최대 23.9%p 어긋났다. */
  const pos = rangePosition(now, low, high);
  if (pos == null) {
    return (
      <TextLabel2 as="span" color="fgMuted" noWrap>
        —
      </TextLabel2>
    );
  }
  return (
    <span className="sr-track" title={`52주 최저↔최고의 ${Math.round(pos)}% 지점`}>
      <span className="sr-track-mark" style={{ left: `${pos}%` }} />
    </span>
  );
}

/** The sticky header's surface. MUST be fully opaque — guarded. */
export const STICKY_SURFACE = 'bg' as const;

/**
 * The selector for the element the probe must be measured INSIDE.
 *
 * `.sr-num` — a NUMERIC cell, specifically, and not merely the first cell in the
 * row. Every width this probe feeds is a width for digits (`level`, `delta`, and
 * the 52주 sub-columns all count glyphs of `−100.5`-shaped strings), so the
 * advance has to be the one the digits draw with.
 *
 * The selector used to be `td span`, which is the LABEL cell — fine only while
 * every cell in the row rendered through the same `TextLabel2`. It stopped being
 * fine when the label cell gained its own register (name at label1/600, subtitle
 * at legal): `ch` is the advance of "0" in the element's own font, and WEIGHT
 * MOVES IT in a variable face. v1 has already shipped that exact defect once —
 * a `font-medium` header cell resolving `44ch` differently from its `font-normal`
 * body cells and misaligning the column by a few px.
 *
 * So the label cell is now free to be styled without touching a single column
 * width, because it is no longer what anything is measured against.
 */
export const CH_PROBE_HOST = 'tbody tr[data-sr-row] td.sr-num span';

/**
 * Measure the '0' advance IN THE CONTEXT THAT RENDERS THE TEXT.
 *
 * Column widths come from format maxima × this number, so it has to be the advance
 * the cells actually draw with. The first version measured on the table's host `div`,
 * whose inherited face is not the cell's: after the Pretendard change the host still
 * resolved to CDS's face at 8.881 px while cells rendered at 8.813 px. 0.77% is small;
 * the structure is what is wrong. It is the same defect class the `<colgroup>` removed
 * — a width derived in one font context and applied in another — and P3 multiplied the
 * surface it corrupts.
 *
 * So the probe is appended to a real cell's text span. Before any row exists there is
 * nothing to measure, and the ladder falls back to `ALL_COLUMNS` on a zero width
 * anyway, so the initial value is only ever used for a frame.
 *
 * `guards/ch-context.test.tsx` fails if this selector stops matching what the cells
 * render, which is the only way the two contexts can silently diverge again.
 */
function useChPx(ref: React.RefObject<HTMLElement | null>, ready: boolean): number {
  const [ch, setCh] = useState(0);
  useEffect(() => {
    const host = ref.current?.querySelector<HTMLElement>(CH_PROBE_HOST);
    if (!host) return;
    const probe = document.createElement('span');
    probe.textContent = '0'.repeat(20);
    probe.style.cssText =
      'position:absolute;visibility:hidden;white-space:pre;font-variant-numeric:tabular-nums';
    host.appendChild(probe);
    const w = probe.getBoundingClientRect().width / 20;
    host.removeChild(probe);
    if (w > 0) setCh(w);
  }, [ref, ready]);
  return ch;
}

/**
 * The width the LADDER spends — the SCROLL CONTAINER's, which is neither the
 * host div's nor the table's. Both of those are wrong, and each was measured
 * wrong on 2026-08-14:
 *
 *   host div  926   the ladder's original subject. 17px too generous — scroll
 *                   container borders plus the vertical scrollbar — so it kept
 *                   adding a column against width the columns could never have.
 *                   Invisible until 세타 filled the tail exactly and the table
 *                   grew a horizontal scrollbar.
 *   <table>   909   correct at full width and WRONG as soon as the window
 *                   narrows: a `table-layout: fixed` table with `width: 100%`
 *                   does not shrink below the sum of its `<col>` widths. It
 *                   overflows instead. So the observed width froze at the last
 *                   state that fit, the ladder stopped dropping columns, and at
 *                   a 1280px page the table overflowed by 40px, at 1100 by 220.
 *                   A width that depends on the columns cannot be the width the
 *                   columns are chosen from — that is a feedback loop.
 *   scroller  909   the element that actually BOUNDS the table. Its content box
 *                   excludes its own borders and the vertical scrollbar, and it
 *                   tracks the container at every width. ← this one.
 *
 * Falls back to the host for the frame before CDS has rendered the table.
 */
function useContainerWidth(ref: React.RefObject<HTMLElement | null>): number {
  const [w, setW] = useState(0);
  useEffect(() => {
    const host = ref.current;
    if (!host) return;
    const el = host.querySelector('table')?.parentElement ?? host;
    const ro = new ResizeObserver(([entry]) => setW(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return w;
}

/**
 * CDS owns the scrolling element and hands out no ref to it — the same gap as
 * `TableRow`. It is found by walking up from the `<table>` to the first ancestor
 * that actually scrolls. This fails LOUDLY (the virtualizer gets nothing and
 * renders no rows) rather than silently, which is why it is acceptable.
 */
function useScrollElement(hostRef: React.RefObject<HTMLElement | null>, ready: boolean) {
  const [el, setEl] = useState<HTMLElement | null>(null);
  useEffect(() => {
    if (!ready) return;
    const table = hostRef.current?.querySelector('table');
    let node: HTMLElement | null = table?.parentElement ?? null;
    while (node) {
      const oy = getComputedStyle(node).overflowY;
      if (oy === 'auto' || oy === 'scroll') break;
      node = node.parentElement;
    }
    setEl(node);
  }, [hostRef, ready]);
  return el;
}

export function InstrumentTable({
  rows,
  onSelect,
  onHover,
  selectedId,
  height = 560,
  compact = false,
  levelHeader,
  levelHeaderTitle,
  divider = true,
  quietLadderNote = false,
}: {
  rows: Row[];
  onSelect: (row: Row) => void;
  /**
   * The row under the pointer (or under keyboard focus), or `undefined` when the
   * table is left. Fires ONLY WHEN THE ROW CHANGES: `mouseover` bubbles from
   * every descendant a pointer crosses, so an un-deduped stream would re-fire
   * several times inside one row — and anything downstream that delays on it
   * (the pane's 120ms) would have its timer restarted by each of them and never
   * reach the end of the wait.
   *
   * The DELAY is not here. This reports what the pointer is on; how long the
   * pointer has to stay there before the screen answers is the READER's
   * question, and it is answered where the answer is shown (`app/page.tsx`).
   */
  onHover?: (row: Row | undefined) => void;
  selectedId?: string;
  /** The 현재 column's header is the DATA DATE, not the word 현재 — the number under
   * it is a close, and a column that says "현재" over yesterday's close is the
   * silent-staleness defect wearing a label. Since 2026-08-14 it is MONTH-DAY
   * only (`lib/format.ts::levelHeadText`), so the full date rides in the
   * tooltip below. */
  levelHeader?: string;
  /** The same date in full, for the header's tooltip — the year the column no
   * longer prints has to be reachable from the column itself, not only from the
   * freshness chip at the other end of the page. */
  levelHeaderTitle?: string;
  /** 주요 / 전체 divider. Only meaningful in tenor order: once rows are sorted by
   * |change| the two sets interleave and a divider would be drawing a line through
   * the middle of the answer. */
  divider?: boolean;
  /** PIXELS, and it must be a number — see the comment on the `height` prop below. */
  height?: number;
  compact?: boolean;
  /** 「N개 열이 폭에 맞춰 숨었어요」 를 끈다. Main 오버뷰가 쓴다 [OWNER 승인
   * 2026-08-18 점검] — 같은 문장이 세 열에 세 번 서면 정보가 아니라 소음이다.
   * 좁은 열이 열을 떨구는 건 오버뷰의 **설계**이지 이상 상태가 아니고, 어떤
   * 열이 사는지는 표 자신이 이미 보여 준다. 정렬 키 경고는 끄지 않는다 —
   * 그건 데이터 결함 신고라 어디서든 서야 한다. */
  quietLadderNote?: boolean;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const width = useContainerWidth(hostRef);

  const [sorting, setSorting] = useState<SortingState>([]);
  const sortCol = (sorting[0]?.id ?? null) as BasisKey | null;
  const asc = sorting[0]?.desc === false;

  /**
   * OUR comparator, verbatim. TanStack owns the sorting STATE (which column,
   * which direction) and the header affordance; it does not own the ordering.
   *
   * `manualSorting` rather than a registered `sortingFn`, and the reason is the
   * contract: a row with no print keeps tenor order BEHIND the ones that have one,
   * in both directions. TanStack inverts a `sortingFn` wholesale for the
   * descending pass, which would float the no-print rows to the top; its
   * `sortUndefined` escape hatch keys on `undefined` and these are `null`.
   * The comparator is not reimplemented in TanStack's vocabulary — it is the same
   * function this table has always used.
   */
  const ordered = useMemo(() => {
    const copy = [...rows];
    copy.sort(sortCol ? byAbsChange(sortCol, asc) : byTenor);
    return copy;
  }, [rows, sortCol, asc]);

  const unmapped = useMemo(() => unmappedRows(rows), [rows]);

  /* Stable and ladder-independent. TanStack needs a column list; the ladder decides
   * what is DRAWN, and every cell is rendered by hand below. Keeping this constant
   * breaks a dependency cycle — the ch probe must wait for a rendered cell, which
   * means the virtualizer has to run before it, which it cannot do if the table's
   * columns depend on the ladder that depends on the probe. */
  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      { id: 'label', accessorKey: 'label' },
      { id: 'level', accessorKey: 'now' },
      { id: 'd1', accessorFn: (r: Row) => r.changes.d1 },
      { id: 'mtd', accessorFn: (r: Row) => r.changes.mtd },
      { id: 'ytd', accessorFn: (r: Row) => r.changes.ytd },
      { id: 'range52', accessorKey: 'pct' },
    ],
    [],
  );

  const table = useReactTable({
    data: ordered,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    manualSorting: true,
    getRowId: (r) => r.id,
    getCoreRowModel: getCoreRowModel(),
  });

  const modelRows = table.getRowModel().rows;

  /* The list the virtualizer actually walks: rows, with one sentinel where 주요 ends.
   * The sentinel is a list item rather than a sticky overlay because it has to scroll
   * with the rows it separates — a divider that floats is a legend, not a divider. */
  type Item = { kind: 'row'; row: Row } | { kind: 'divider'; label: string };
  const display = useMemo<Item[]>(() => {
    const asRows = modelRows.map((r) => ({ kind: 'row' as const, row: r.original }));
    if (!divider || sortCol != null) return asRows;
    const firstRest = asRows.findIndex((i) => !i.row.key);
    if (firstRest <= 0) return asRows;
    return [
      ...asRows.slice(0, firstRest),
      { kind: 'divider' as const, label: '전체' },
      ...asRows.slice(firstRest),
    ];
  }, [modelRows, divider, sortCol]);

  const scrollEl = useScrollElement(hostRef, rows.length > 0);
  const virtualizer = useVirtualizer({
    count: display.length,
    getScrollElement: () => scrollEl,
    estimateSize: () => ROW_H,
    overscan: OVERSCAN,
  });

  const items = virtualizer.getVirtualItems();

  /* 점프가 절반만 이동하던 결함(전체 앱 크리틱 2026-08-19): 기준점 띠의
   * 앵커는 탭과 행을 정하지만 표는 꿈쩍하지 않았다 — 가상화라 그 행이 DOM 에
   * 없을 수도 있으니 scrollIntoView 로는 못 간다. 스크롤러의 주인인 여기가
   * 인덱스로 간다. align 'auto' 는 이미 보이는 행이면 움직이지 않는다 —
   * 표 안에서 직접 클릭해 고른 행에서 화면이 튀지 않는 이유. */
  const selectedIndex = useMemo(
    () =>
      selectedId
        ? display.findIndex((it) => it.kind === 'row' && it.row.id === selectedId)
        : -1,
    [display, selectedId],
  );
  const selectedPresent = selectedIndex >= 0;
  /* 인덱스 자체는 deps 에 **없다**: 정렬·필터로 자리만 바뀔 때마다 재스크롤하면
     화면이 끌려다닌다. 선택이 바뀌거나(탭 점프 직후) 그 행이 표에 나타나는
     순간에만 간다.
     ⚠ 억제 주석은 **deps 배열 바로 위**에 있어야 닿는다 — 설명문 위에 두면
     「next line」이 주석을 가리켜 규칙이 그대로 울고 억제는 미사용이 된다
     (경고 두 개가 그 자리였다, 2026-09-15). */
  useEffect(() => {
    if (selectedPresent) virtualizer.scrollToIndex(selectedIndex, { align: 'auto' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, selectedPresent]);
  // Only once a cell is actually on the page can the probe measure the face the cells
  // draw with. Before that `chPx` is 0 and the colgroup declares nothing.
  const chPx = useChPx(hostRef, items.length > 0);

  /* The ladder, once the probe has a real advance. Until then ALL_COLUMNS: the header
   * draws every column and the colgroup declares nothing, which is a truthful
   * "not measured yet" rather than a guess. */
  /* Two questions, asked separately and in this order: does the 세타 column FIT
   * (the ladder, from width) and does it APPLY (does any row here carry one).
   * Keeping them apart is what stops a tab with no swaps — 포워드, 변동성,
   * 민평 — from spending a column on a full page of em dashes, while still
   * reporting an honest 숨김 count for the columns width actually took away. */
  const anyTheta = useMemo(() => hasTheta(rows), [rows]);
  const cols = useMemo<VisibleColumns>(
    () =>
      width > 0 && chPx > 0
        ? visibleColumns(width, chPx, sortCol, anyTheta)
        : { ...ALL_COLUMNS, theta: anyTheta },
    [width, chPx, sortCol, anyTheta],
  );
  const totalSize = virtualizer.getTotalSize();
  const padTop = items.length > 0 ? items[0].start : 0;
  const padBottom = items.length > 0 ? totalSize - items[items.length - 1].end : 0;

  const flip = useFlipReorder(hostRef);

  const sortable = useSortableCell<BasisKey>({
    sortBy: (sortCol ?? '') as BasisKey,
    sortDirection: sortCol == null ? undefined : asc ? 'ascending' : 'descending',
    onChange: (key) => {
      flip.snapshot();
      setSorting((prev) =>
        prev[0]?.id === key ? [{ id: key, desc: !prev[0].desc }] : [{ id: key, desc: true }],
      );
    },
  });

  /* ── delegation, unchanged in kind ──────────────────────────────────────── */
  const rowFromEvent = useCallback(
    (target: EventTarget | null): Row | undefined => {
      const tr = (target as HTMLElement | null)?.closest?.(ROW_SELECTOR);
      const id = tr?.getAttribute(ROW_ATTR);
      return id ? rows.find((r) => r.id === id) : undefined;
    },
    [rows],
  );

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      const row = rowFromEvent(e.target);
      if (row) onSelect(row);
    },
    [rowFromEvent, onSelect],
  );

  /* ── hover / focus, deduped by row identity ─────────────────────────────── */
  const hoveredId = useRef<string | undefined>(undefined);
  const emitHover = useCallback(
    (row: Row | undefined) => {
      if (row?.id === hoveredId.current) return; // the dedupe the delay depends on
      hoveredId.current = row?.id;
      onHover?.(row);
    },
    [onHover],
  );

  const handleMouseOver = useCallback(
    (e: React.MouseEvent) => emitHover(rowFromEvent(e.target)),
    [emitHover, rowFromEvent],
  );

  /* `mouseleave` rather than `mouseout`: mouseout fires on every internal
   * boundary the pointer crosses, so clearing on it would blank the pane
   * between two cells of the SAME row. React's onMouseLeave is the
   * relatedTarget-checked version and fires once, when the table is actually
   * left. Divider rows and the spacer rows have no row id, so crossing one
   * reports `undefined` through mouseover and the pane falls back to the pinned
   * row — which is correct: nothing is under the pointer. */
  const handleMouseLeave = useCallback(() => emitHover(undefined), [emitHover]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      const row = rowFromEvent(e.target);
      if (!row) return;
      e.preventDefault();
      onSelect(row);
    },
    [rowFromEvent, onSelect],
  );

  /**
   * Focus survival across virtualization.
   *
   * A focused row can scroll out of the window and unmount, which drops focus to
   * `<body>` — the keyboard user loses their place with nothing on screen saying
   * so. The row identity is remembered on focus; when that row re-mounts, focus
   * returns to it. While it is unmounted the CONTAINER holds focus, so the
   * delegated key handler still has somewhere to fire and Tab order does not jump
   * to the end of the document.
   */
  const focusedId = useRef<string | null>(null);
  const onFocusCapture = useCallback(
    (e: React.FocusEvent) => {
      const tr = (e.target as HTMLElement).closest?.(ROW_SELECTOR);
      const id = tr?.getAttribute(ROW_ATTR);
      if (id) focusedId.current = id;
      /* FOCUS IS HOVER (v1's rule, kept): a keyboard reader arrowing down the
       * table gets the same preview a pointer would, and Enter pins it the way
       * a click does. Without this the pane is reachable by mouse only. */
      emitHover(rowFromEvent(e.target));
    },
    [emitHover, rowFromEvent],
  );

  /* Only when focus LEAVES the table. Moving between two rows fires blur then
   * focus, and clearing on that blur would push the pane back to the pinned row
   * for one tick on every arrow press. */
  const onBlurCapture = useCallback(
    (e: React.FocusEvent) => {
      const next = e.relatedTarget as Node | null;
      if (next && hostRef.current?.contains(next)) return;
      emitHover(undefined);
    },
    [emitHover],
  );

  useEffect(() => {
    const want = focusedId.current;
    if (!want) return;
    const host = hostRef.current;
    if (!host) return;
    const active = document.activeElement;
    if (active && active !== document.body && host.contains(active)) return;
    const el = host.querySelector<HTMLTableRowElement>(
      `${ROW_SELECTOR}[${ROW_ATTR}="${CSS.escape(want)}"]`,
    );
    if (el) el.focus({ preventScroll: true });
    else host.focus({ preventScroll: true });
  }, [items]);

  // 0 would collapse every fixed width; before the first measurement the
  // colgroup declares nothing and the browser lays the table out on content.
  const specs = chPx > 0 ? colSpecs(cols, chPx) : [];

  /* Spacer and divider rows must span the columns THAT EXIST, and the ladder
   * drops columns: at a narrow width the row is 종목 + 현재 + one change + the
   * tail, which is 4. The literal 6 this replaced was the full-ladder count, so
   * every spacer over-spanned by two whenever anything had dropped. Derived from
   * the same ladder the header and body cells are rendered from, so the three
   * cannot disagree. */
  const colCount = 2 + cols.bases.length + 1;

  /* 표의 host — raw `<div style>` 이 아니라 `Box` 다. 폭은 style prop 이 진다
   * (cds-code: style prop > inline style).
   *
   * **`display="block"` 이 load-bearing 이다**: CDS `Box` 는 기본이
   * `display: flex` 이고(그 컴포넌트 문서의 첫 줄), 그대로 두면 안의 `<table>`
   * 이 flex 아이템이 되어 이 표의 폭 규약(`table-layout: fixed` + colgroup)과
   * 다툰다. 여기서 필요한 것은 블록 컨테이너 하나다.
   *
   * `ref`·키보드·포인터 핸들러는 그대로 간다 — Box 는 polymorphic 이고 기본
   * 요소가 `div` 라 네이티브 prop 을 그대로 받는다. */
  return (
    <Box
      as="div"
      display="block"
      width="100%"
      ref={hostRef}
      tabIndex={-1}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      onMouseOver={handleMouseOver}
      onMouseLeave={handleMouseLeave}
      onFocusCapture={onFocusCapture}
      onBlurCapture={onBlurCapture}
    >
      <Table
        variant="ruled"
        bordered
        tableLayout="fixed"
        /* CDS GAP — the type lies about this prop.
           `TableProps.height` is typed `React.CSSProperties['height']`, so a
           string like '70vh' type-checks. The implementation does
           `'--table-height': \`${height}px\`` unconditionally, producing
           `70vhpx` — an invalid value, which resolves to `none` and leaves the
           scroll container unconstrained. The virtualiser then has no viewport
           and windows against the whole document.
           It must be a NUMBER of pixels. Measured, not inferred. */
        height={height}
        compact={compact}
        accessibilityLabel="종목"
      >
        {/* THE single width source — unchanged by virtualization. A spacer row
            consumes no width authority under `table-layout: fixed`; measured in D0. */}
        {specs.length > 0 ? (
          <colgroup>
            {specs.map((s) => (
              <col key={s.key} style={colStyle(s)} />
            ))}
          </colgroup>
        ) : null}

        <TableHeader sticky>
          <TableRow backgroundColor={STICKY_SURFACE} style={{ height: HEADER_H }}>
            <TableCell as="th" scope="col">
              <TextCaption as="span" color="fgMuted">종목</TextCaption>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <TextCaption as="span" color="fgMuted" title={levelHeaderTitle}>
                {levelHeader ?? '현재'}
              </TextCaption>
            </TableCell>
            {cols.bases.map((b) => {
              const { end, ...cell } = sortable(b);
              return (
                <TableCell
                  key={b}
                  as="th"
                  scope="col"
                  className="sr-num"
                  justifyContent="flex-end"
                  {...cell}
                  /* CDS 의 정렬 글리프는 아이콘 폰트의 사용자 영역(PUA) 문자라,
                     접근 이름이 "1D󰟃󰞷" 로 읽히고 있었다(전체 앱 크리틱 실측).
                     ⚠ 그때의 수리는 **한 단계 위에 붙었다** [2026-09-15 확인] —
                     `aria-label` 이 `<th>` 로 갔는데 누르는 것은 CDS 가 그 안에
                     그리는 `<button>` 이고, 그 버튼 이름은 여전히 "1D󰟃󰞷" 였다.
                     이제 이름을 **버튼 안에서** 만든다: 글리프는 `aria-hidden` 으로
                     장식이 되고, 사람 말은 눈에 안 보이는 span 이 잇는다. */
                  end={<span aria-hidden="true">{end}</span>}
                >
                  <TextCaption as="span" color="fgMuted">{BASIS_LABEL[b]}</TextCaption>
                  <span className="sr-a11y-only"> 변화 — 눌러서 정렬</span>
                </TableCell>
              );
            })}
            {/* 52주 is FOUR sub-columns, not one number. v1 prints 고점/저점/평균
                as ink statistics plus a low→high track with a marker; v2's
                `columns.ts` has always sized the cell for them (`RANGE_SUBS`,
                `slider`) and only the render was missing. */}
            <TableCell as="th" scope="col" className="sr-num">
              {cols.range52 ? (
                <span
                  className="sr-range"
                  style={{ gridTemplateColumns: rangeTemplate(cols.slider, cols.theta, chPx) }}
                >
                  <TextCaption as="span" color="fgMuted">52주 고점</TextCaption>
                  <TextCaption as="span" color="fgMuted">저점</TextCaption>
                  <TextCaption as="span" color="fgMuted">평균</TextCaption>
                  {cols.slider ? (
                    <TextCaption as="span" color="fgMuted">위치</TextCaption>
                  ) : null}
                  {/* 세타 — the label carries the normaliser because the number
                      is unreadable without it; horizon and side ride in the
                      title, which is the only place they fit. */}
                  {cols.theta ? (
                    <TextCaption as="span" color="fgMuted" title={THETA_TITLE}>
                      {THETA_LABEL}
                    </TextCaption>
                  ) : null}
                  <span />
                </span>
              ) : (
                /* CDS GAP — `TableCell` types its children as non-nullable, so
                   the usual `cond ? … : null` does not type-check. An empty span
                   is the filler the dropped column leaves behind anyway. */
                <span />
              )}
            </TableCell>
          </TableRow>
        </TableHeader>

        <TableBody>
          {padTop > 0 ? (
            <tr data-sr-spacer="top" aria-hidden>
              <td colSpan={colCount} style={{ height: padTop, padding: 0, border: 0 }} />
            </tr>
          ) : null}

          {items.map((vi) => {
            const item = display[vi.index];
            if (!item) return null;
            if (item.kind === 'divider') {
              return (
                <tr key="sr-divider" data-sr-divider style={{ height: ROW_H }}>
                  <td colSpan={colCount} style={{ padding: '0 8px', border: 0 }}>
                    <TextCaption as="span" color="fgMuted">
                      {item.label}
                    </TextCaption>
                  </td>
                </tr>
              );
            }
            const row = item.row;
            return (
              <TableRow
                key={row.id}
                {...{ [ROW_ATTR]: row.id }}
                tabIndex={0}
                /* `aria-current`, not `aria-selected`: on a plain `role=table`
                   row aria-selected is invalid and assistive tech ignores it
                   (전체 앱 크리틱 실측 2026-08-19). aria-current is valid on
                   any element, and this row IS the current instrument — the
                   URL's `r`. The pinned-row fill in type.css keys off it. */
                aria-current={row.id === selectedId ? 'true' : undefined}
                style={{ height: ROW_H }}
              >
                {/* The name and where it normally sits. Two registers, never
                    three: the name carries the row's only non-numeric emphasis
                    and the second line separates by size and colour rather than
                    by a third weight. The name is also this row's anchor — see
                    the recorded rejection of the tenor chip in `cells.ts`. */}
                <TableCell>
                  <VStack as="span" className="sr-name-stack">
                    <TextLabel1 as="span" noWrap>
                      {row.label}
                    </TextLabel1>
                    <TextLegal as="span" color="fgMuted" noWrap>
                      {subText(row)}
                    </TextLegal>
                  </VStack>
                </TableCell>
                <TableCell className="sr-num" justifyContent="flex-end">
                  <TextLabel2 as="span" tabularNumbers noWrap>
                    {levelText(row)}
                  </TextLabel2>
                </TableCell>
                {cols.bases.map((b) => (
                  <TableCell key={b} className="sr-num" justifyContent="flex-end" style={tintStyle(row.changes[b])}>
                    <TextLabel2
                      as="span"
                      tabularNumbers
                      noWrap
                      className={directionClass(row.changes[b])}
                    >
                      {directionGlyph(row.changes[b])}
                      {directionGlyph(row.changes[b]) ? ' ' : ''}
                      {unsignedDelta(fmtDelta(row.changes[b], row.unit))}
                    </TextLabel2>
                  </TableCell>
                ))}
                <TableCell className="sr-num">
                  {cols.range52 ? (
                    <span
                      className="sr-range"
                      style={{ gridTemplateColumns: rangeTemplate(cols.slider, cols.theta, chPx) }}
                    >
                      <TextLabel2 as="span" tabularNumbers noWrap>
                        {rangeText(row.rangeHigh, row.unit)}
                      </TextLabel2>
                      <TextLabel2 as="span" tabularNumbers noWrap>
                        {rangeText(row.rangeLow, row.unit)}
                      </TextLabel2>
                      <TextLabel2 as="span" tabularNumbers noWrap>
                        {rangeText(row.rangeAvg, row.unit)}
                      </TextLabel2>
                      {cols.slider ? (
                        <RangeTrack now={row.now} low={row.rangeLow} high={row.rangeHigh} />
                      ) : null}
                      {/* 세타 — INK, although it IS a signed money value and hue
                          is reserved for exactly those. This row already spends
                          that hue on RATE direction (어제/MTD/YTD), and two
                          meanings of one colour in one row is worse than none;
                          the sign glyph `fmtKrw` prints carries the direction on
                          its own. An em dash where there is no value: an empty
                          cell would read as a loading state. */}
                      {cols.theta ? (
                        <TextLabel2
                          as="span"
                          tabularNumbers
                          noWrap
                          title={row.theta ? thetaTitle(row.theta) : undefined}
                        >
                          {row.theta ? fmtKrw(row.theta.perDv01) : '—'}
                        </TextLabel2>
                      ) : null}
                      <span />
                    </span>
                  ) : (
                    <span />
                  )}
                </TableCell>
              </TableRow>
            );
          })}

          {padBottom > 0 ? (
            <tr data-sr-spacer="bottom" aria-hidden>
              <td colSpan={colCount} style={{ height: padBottom, padding: 0, border: 0 }} />
            </tr>
          ) : null}
        </TableBody>
      </Table>

      <HStack justifyContent="space-between" paddingY={0.5}>
        <TextCaption as="span" color="fgMuted">
          {!quietLadderNote && cols.hidden > 0 ? `${cols.hidden}개 열이 폭에 맞춰 숨었어요` : ''}
        </TextCaption>
        {unmapped.length > 0 ? (
          <TextCaption as="span" className="sr-up">
            정렬 키가 없는 종목 {unmapped.length}개
          </TextCaption>
        ) : null}
      </HStack>
    </Box>
  );
}
