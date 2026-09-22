/* Unified instrument rows for the list-first table (DESIGN §2). One row per
 * instrument across all groups.
 *
 * §16 computation boundary: this builder turns the API's numbers into a row
 * shape — it does NOT compute any of them. Levels, deltas, the 52-week
 * high/low/mean, percentiles, sort keys and the quoted flag all arrive
 * precomputed from the backend. The only work here is presentation: choosing a
 * display label and routing a series into its group. `ROW_FIELD_SOURCE` records
 * every field's provenance and `guards/row-vm-source.test.ts` fails the build
 * if a new field appears that isn't declared — a field that needs arithmetic
 * has no honest declaration and belongs in the backend. */

import type {
  BasisKey,
  ForwardsPayload,
  SeriesSummary,
  Theta,
  Unit,
  VolatilityPayload,
  WallSummary,
} from "@/lib/api";

/* Butterflies are their OWN group since 2026-07-31 [OWNER]. They used to ride
 * on the spread tab, which meant 20 flies buried 15 spreads; with 6M and 9M in
 * the tenor set it would have been 56 under 28. Two-leg and three-leg are
 * different instruments read for different reasons, so they are different
 * tabs — and butterflies deliberately do NOT appear on the 전체 overview. */
/* V2-LOCAL: widened for the expanded universe. The five swap groups are v1's and are
 * untouched; the four after them are the live classes P0a found sitting beside the
 * swap monitor (국고 현물, 크레딧 스프레드, 본드스왑스프레드, 국채선물). Rows of every
 * group go through this same builder shape, so the comparator, the ladder and the tint
 * ramp need no second vocabulary. */
/* V2, 2026-08-18: `cashbond`/`asw` joined for the Cash Bond lane — Backtest
 * 메가 패널의 다섯 번째 카테고리 아래 **별개 표 탭 둘**. 현금채권은 민평
 * 수익률(%), 자산스왑은 **IRS − 민평** 스프레드(bp — 부호 규약 [OWNER 2026-09-22]
 * «스왑 − 채권현물»; BSS 와 같은 수라 같이 뒤집혔다).
 *
 * v1 은 이 둘을 `Group` 밖에 두었다(v1 tabs.ts:29 — "Group 은 IRS 행 빌더가
 * 읽는 값"이라서). v2 에서 그 전제는 이미 사실이 아니다: 위 V2-LOCAL 이 적듯
 * 국고·크레딧·선물을 같은 열거에 들였고, 그 행들도 `buildRows` 가 아니라 자기
 * 어댑터(`universeRows.toRows`)가 만든다. v1 규칙이 지키던 것 — 두 항목이
 * 별개 탭이고, 현금채권 행이 IRS 빌더에 절대 들어가지 않는 것 — 은 그대로다:
 * 행은 `cashbondRows.toRows` 만 만든다. */
export type Group =
  | "outright"
  | "spread"
  | "fly"
  | "forward"
  | "vol"
  | "govt"
  | "credit"
  | "bss"
  | "futures"
  | "futuresswap"
  | "cashbond"
  | "asw";

export const BASIS_ORDER: BasisKey[] = ["d1", "mtd", "ytd"];

export const GROUP_LABEL: Record<Group, string> = {
  outright: "아웃라이트",
  spread: "스프레드",
  fly: "버터플라이",
  forward: "포워드",
  vol: "변동성",
  govt: "국고",
  credit: "크레딧",
  bss: "본드스왑",
  futures: "국채선물",
  futuresswap: "퓨처스왑",
  cashbond: "현금채권",
  asw: "자산스왑",
};

/** The three groups the 전체 overview columns show, left to right (§전체).
 * Volatility and butterflies are not among them — the overview is the three
 * things a rates screen opens on, not a summary of every tab. */
export const OVERVIEW_GROUPS: Group[] = ["outright", "spread", "forward"];

export interface Row {
  id: string;
  label: string; // display instrument name
  group: Group;
  unit: Unit;
  now: number | null;
  changes: Record<BasisKey, number | null>; // bp vs each basis
  pct: number | null; // 52-week LEVEL percentile, null if none
  seriesId: string | null; // stage-2 history id, null = no history
  /** 52-week LEVEL high / low / mean, in the row's own unit — the last column
   * (pass L). Straight from `range1y`; rendered with the SAME formatter the
   * 현재 column uses, never a second rounding. */
  rangeHigh: number | null;
  rangeLow: number | null;
  rangeAvg: number | null;
  /** explicit ascending sort key, supplied by the backend (§6/§16). */
  sortKey: number[];
  /** own-history move percentile (§D screener); null where unavailable. */
  movePct: number | null;
  /** true only for the six quoted key forwards (pinned to the top, §3). */
  keyForward?: boolean;
  /** forward start point label, for the secondary start filter (§3). */
  startLabel?: string;
  /** THREE states, and the third is not "unknown" — it is "the question does
   * not apply to this instrument" (§6):
   *
   *   true       고시 만기 — the tenor is a live-quoted curve node
   *   false      보간 만기 — the tenor is interpolated between two of them
   *   undefined  개념 없음 — a spread/fly/vol row, or a class whose feed has no
   *              such distinction (see `universeRows.toRows`)
   *
   * The backend decides it and the browser reads the verdict (§16). For
   * outrights that is `derive.py:355` (`series_id in QUOTED_NODES if kind ==
   * "outright" else None`), so `false` genuinely means interpolated and only a
   * NON-outright arrives as null. For forwards it is `forwards.py:70`
   * (`is_live_point`): a forward is 고시 iff BOTH its start and its end sit on
   * quoted nodes, which is a wider set than the six 주요 forwards and is
   * therefore a fact the divider does not already tell you. */
  quoted?: boolean;
  /** 주요 membership — decides which side of the tab's divider this row sits
   * on (§3). Server-decided for every group, including forwards (whose flag
   * arrives as `keyForward`); the browser holds no copy of the owner's list. */
  key: boolean;
  /** 3개월 캐리 + 롤다운, 커브를 동결하고 (`backend/app/theta.py`). 스왑 다리가
   * 될 수 있는 아웃라이트 테너와 그것으로 짜인 스프레드·플라이만 값을 진다 —
   * 1D/3M, 포워드, 변동성, 민평·선물 행에는 없고 열은 거기서 em dash 를 그린다.
   * 어떤 산술도 여기서 하지 않는다(§16): `perDv01` 도 `beBp` 도 백엔드 값이다. */
  theta?: Theta | null;
}

/** Provenance of every Row field (§16). `dto` = read straight from the API;
 * `format` = pure presentation (label, routing, rendered copy). There is no
 * `compute` value on purpose: a field that would need arithmetic on market
 * data has no home here and must be produced by the backend. The guard fails
 * when a built row carries a key absent from this map. */
export const ROW_FIELD_SOURCE: Record<keyof Row, "dto" | "format"> = {
  id: "format",
  label: "format",
  group: "format",
  unit: "dto",
  now: "dto",
  changes: "dto",
  pct: "dto",
  seriesId: "format",
  rangeHigh: "dto",
  rangeLow: "dto",
  rangeAvg: "dto",
  sortKey: "dto",
  movePct: "dto",
  keyForward: "dto",
  startLabel: "format",
  quoted: "dto",
  key: "dto",
  theta: "dto",
};

/** lexicographic compare of numeric sort keys (§6). */
export function cmpKey(a: number[], b: number[]): number {
  const n = Math.max(a.length, b.length);
  for (let i = 0; i < n; i++) {
    const av = a[i] ?? -1;
    const bv = b[i] ?? -1;
    if (av !== bv) return av - bv;
  }
  return 0;
}

/** THE row ordering. Two states and no others, because `sortCol` is a
 * `BasisKey | null`:
 *
 *   a change column is sorted → by |change| in that column, nulls last;
 *   nothing is sorted        → the backend's explicit sort key, ascending
 *                              (§6), 주요 rows pinned to the top.
 *
 * The 주요 pin used to be forwards-only (`keyForwardFirst`). It now applies to
 * every tab that has a 주요 set, because every tab now draws the divider —
 * and the divider is only honest if the rows above it are in fact the ones
 * ordered first. Sorting by a change column overrides it, deliberately: the
 * question "what moved most" is asked of the whole tab, not of 주요 first.
 *
 * Only a CHANGE column can occupy the first state. The 52주 column carries no
 * sort key of its own — three statistics do not rank rows — so clicking its
 * header cannot reach here and the order does not move (pass L). That is a
 * property of the COLUMN and is silent by design; a ROW with no sort key is a
 * different and LOUD condition, non-finite so it lands at the end where it can
 * be seen (guards/sort-key.test.ts).
 *
 * Lifted out of the component so it is testable without a DOM. */
export function orderRows(
  rows: Row[],
  sortCol: BasisKey | null,
  sortAsc: boolean,
  keyFirst: boolean,
): Row[] {
  if (sortCol) {
    const withVal = rows.filter((r) => r.changes[sortCol] != null);
    const without = rows.filter((r) => r.changes[sortCol] == null);
    withVal.sort((a, b) => {
      const d = Math.abs(b.changes[sortCol]!) - Math.abs(a.changes[sortCol]!);
      return sortAsc ? -d : d;
    });
    return [...withVal, ...without];
  }
  return [...rows].sort((a, b) => {
    if (keyFirst) {
      const ak = a.key ? 0 : 1;
      const bk = b.key ? 0 : 1;
      if (ak !== bk) return ak - bk;
    }
    return cmpKey(a.sortKey, b.sortKey);
  });
}

/** "1Y-10Y" → "1s10s", "2Y-5Y-10Y" → "2s5s10s" (trader shorthand).
 *
 * The shorthand only works when every leg is a YEAR count: it drops the unit
 * and lets `s` carry it. A month leg has no such reading — 6M-9M-1Y through
 * the old rule came out `6Ms9Ms1s`, which is not shorthand for anything and
 * is the label the 6M/9M butterfly would have shipped with. So a legset that
 * is not all-years keeps its units and joins on a slash: `6M/9M/1Y`. Both
 * forms are what a KRW desk writes; the mixed one is what nobody writes.
 * Pinned by guards/instrument-label.test.ts. */
export function traderName(id: string): string {
  const legs = id.split("-");
  if (legs.every((t) => t.endsWith("Y"))) {
    return legs.map((t) => t.slice(0, -1)).join("s") + "s";
  }
  return legs.join("/");
}

/* `renderOneLiner` phrased the backend 한 줄 classification into Korean and is
 * gone with the column (pass L). It was the §16 exception's most visible
 * subject; the exception itself still has two (`ui/gloss.ts` and the curve
 * banner) — see DESIGN §16. */

function fromSummary(s: SeriesSummary, group: Group, label: string): Row {
  return {
    id: s.id,
    label,
    group,
    unit: s.unit,
    now: s.now,
    changes: { ...s.deltas },
    pct: s.range1y.pct,
    seriesId: s.id,
    rangeHigh: s.range1y.max,
    rangeLow: s.range1y.min,
    rangeAvg: s.range1y.avg,
    sortKey: s.sortKey,
    movePct: s.movePct,
    /* null → undefined, and `false` is CARRIED. The API's three values map onto
     * the row's three (see the field's doc): only a non-outright arrives null,
     * so collapsing it to undefined loses nothing, while `false` is the
     * 보간 만기 verdict and must survive. `?? undefined` did the right thing
     * here all along; it is written out because a previous pass read it as
     * collapsing `false` too and dropped the 보간 mark on that belief. */
    quoted: s.quoted === null ? undefined : s.quoted,
    key: s.key,
    theta: s.theta ?? null,
  };
}

export function buildRows(
  summary: WallSummary,
  forwards: ForwardsPayload | undefined,
  volatility?: VolatilityPayload,
): Row[] {
  const rows: Row[] = [];

  for (const o of summary.outrights) {
    rows.push(fromSummary(o, "outright", o.id));
  }
  for (const d of summary.derived) {
    // `kind` already distinguishes the two server-side — a three-leg id is
    // not a spread with an extra leg, it is a different instrument.
    rows.push(fromSummary(d, d.kind === "fly" ? "fly" : "spread", traderName(d.id)));
  }
  if (forwards) {
    // every non-degenerate forward in the matrix, start-major (§3)
    for (const sp of forwards.startPoints) {
      // ONx* is the spot curve wearing a forward's name (carry session,
      // Pass A): an overnight start IS today, so every ON-start "forward"
      // equals the outright of its tenor by construction and the whole row
      // duplicates the outright tab. The ON row stays in the matrix (표로
      // 보기) as the grid's spot anchor, relabelled 현물 — never in the list.
      if (sp.label === "ON") continue;
      for (const tenor of forwards.tenors) {
        const clean = tenor.replace("F", ""); // "1YF"→"1Y", "SPOT" stays
        // {start}xSPOT is a spot-starting par rate — the outright at that
        // start, with no forward period — so it is a duplicate in the forward
        // LIST (§I). It stays in the matrix (표로 보기) as the spot reference
        // column, but is dropped from the row list here.
        if (clean === "SPOT") continue;
        const name = `${sp.label}x${clean}`;
        const cell = forwards.grid[tenor].find((c) => c.start === sp.label);
        if (!cell) continue;
        rows.push({
          id: name,
          label: name,
          group: "forward",
          unit: "%",
          now: cell.values.now,
          changes: { ...cell.deltas },
          pct: null,
          seriesId: name, // stage-2 forward history (Session 13)
          rangeHigh: cell.range1y.max,
          rangeLow: cell.range1y.min,
          rangeAvg: cell.range1y.avg,
          sortKey: cell.sortKey,
          movePct: null, // forwards have no cheap daily-move history
          /* 고시/보간 for a forward is `live` — both legs on quoted nodes
           * (`forwards.py:70`). Independent of `keyForward`: the six 주요
           * forwards are an owner's list, `live` is a property of the grid
           * point, and plenty of live points are not 주요. */
          quoted: cell.live,
          keyForward: cell.keyForward,
          key: cell.keyForward,
          startLabel: sp.label,
        });
      }
    }
  }
  // Volatility rows — the relative-ATR ratio per tenor, precomputed server-side
  // (§16) and shaped like every other summary, so this reuses fromSummary.
  if (volatility) {
    for (const v of volatility.rows) {
      rows.push(fromSummary(v, "vol", v.label));
    }
  }
  return rows;
}
