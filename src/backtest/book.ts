/* 백테스트의 **북** — "그때 들어갔으면 지금 얼마였을까".
 *
 * 한 거래가 아니라 북이다 [v1 OWNER, 2026-07-31]: 행마다 종목·방향·규모·진입일·
 * 청산일이 따로 논다. 실제로 레그인은 다른 날에 하고 레그아웃도 다른 날에 한다.
 *
 * 이 파일은 순수하다 — DOM 도 fetch 도 없다. 창이 하는 일(입력·실행·표시)과
 * 북이 무엇인가(모양·인코딩·기억)를 갈라두면 규칙을 DOM 없이 검증할 수 있다.
 */

import { encodePositions, isBondKind, type BookKind, type PositionInput } from "@/lib/api";
import type { Group, Row } from "@/table/rows";

/** 한 창에 열두 줄. v1 의 상한이고, 근거는 화면이 아니라 **읽기**다: 열둘을
 * 넘으면 헤드라인 한 줄이 무엇의 합인지 눈으로 못 세게 된다. */
export const MAX_POSITIONS = 12;

/**
 * 북에 담을 수 있는 종목 [v1 V-PASS V5, 2026-08-03].
 *
 * 엔진이 받는 것만 고른다. **포워드는 빠진다** — `backtest._legs_for` 가 '-' 로
 * 다리를 쪼개고 `_validate` 가 'x' 가 든 id 를 전부 거부하므로, 목록에 넣어두면
 * 실행할 때마다 422 가 난다. 변동성은 비율이라 애초에 포지션이 아니다. 민평·선물도
 * 스왑이 아니다.
 *
 * **서버가 거부하는 것을 화면이 제안하지 않는다** — 이 리포가 이름 붙여 둔
 * claim-vs-behaviour 결함이 정확히 그것이다.
 */
export const BOOKABLE_GROUPS: Group[] = [
  "outright", "spread", "fly", "cashbond", "asw", "futures", "futuresswap",
];

/** 선물 카테고리의 그룹 — 아래 `bookIdOf` 에서 **id 어휘가 갈리는** 두 그룹. */
const FUTURES_GROUPS: Group[] = ["futures", "futuresswap"];

/**
 * Main 표의 id -> **엔진의 id**. 두 어휘가 있고, 하나로 합칠 수 없다.
 *
 *   Main    `FUT-KTB3` · `FUT-KTB3-IY` · `FUT-KTB3-BS` · `FSW-KTB3`
 *           출처 `infomax.daily_ktb_price` — 벤더 계약가·벤더 내재금리·저평가.
 *   엔진    `FUT:3Y` · `FSW:3Y`
 *           출처 `mkt_futures_investor_close`(조정가) + 같은 벤더 내재금리.
 *
 * **두 표는 같은 계열이 아니다**(조정가 대 계약가 — FUTURES_LANE_STATE §Phase 1).
 * 그래서 이 사전은 «같은 상품» 만 잇는다: 어느 계약이냐만 옮기고 수는 하나도
 * 옮기지 않는다. 담긴 뒤의 진입레벨·손익은 전부 엔진 쪽 규약을 탄다
 * (수준 = 벤더 `implied`, 손익 = `price_adj` 의 차분).
 *
 * 가격 행과 내재금리 행이 **같은 곳으로 간다** — 한 계약을 두 단위로 읽은
 * 것이지 두 상품이 아니다. **저평가(`-BS`) 행은 없다**: 그것은 계약이 아니라
 * 벤더가 낸 베이시스 수치라 담을 포지션이 아니고, 사전에 없으면 그 줄은
 * `isBookable` 이 false 로 답한다(서버가 거부하는 것을 화면이 제안하지 않는다).
 */
export const MAIN_TO_BOOK_ID: Readonly<Record<string, string>> = {
  "FUT-KTB3": "FUT:3Y",
  "FUT-KTB3-IY": "FUT:3Y",
  "FUT-KTB10": "FUT:10Y",
  "FUT-KTB10-IY": "FUT:10Y",
  "FSW-KTB3": "FSW:3Y",
  "FSW-KTB10": "FSW:10Y",
};

/** 이 줄을 북에 담으면 어떤 id 가 되나. 담을 수 없으면 null.
 *
 * 담을 수 있는지와 무엇으로 담기는지는 **한 질문**이다 — 둘로 나누면 «담을 수
 * 있다» 고 답해 놓고 넣을 id 가 없는 상태가 생긴다. */
export function bookIdOf(row: Row): string | null {
  if (!BOOKABLE_GROUPS.includes(row.group)) return null;
  if (FUTURES_GROUPS.includes(row.group)) return MAIN_TO_BOOK_ID[row.id] ?? null;
  return row.id;
}

export function isBookable(row: Row): boolean {
  return bookIdOf(row) !== null;
}

/** 스왑만 담던 시절의 목록 — 종목 드롭다운이 이걸 쓴다. 현금채권·자산스왑은
 * 종목군과 만기를 **따로** 고르므로(그쪽 화면의 [OWNER] 규칙) 같은 목록에
 * 섞이지 않는다. */
export const SWAP_GROUPS: Group[] = ["outright", "spread", "fly"];

export function isSwapBookable(row: Row): boolean {
  return SWAP_GROUPS.includes(row.group);
}

/** id 만 보고 줄의 종류를 안다 — 백엔드 `mixedbook.is_bond` · 시뮬레이션
 * `scenario.kindOf` 와 같은 규칙이다. 접두사가 가장 먼저인 이유는 저쪽에
 * 적혀 있다: `CB:KTB:3Y` 에는 `-` 가 없어 아웃라이트로 읽힌다. */
export function bookKindOf(id: string): BookKind {
  if (id.startsWith("CB:")) return "cashbond";
  if (id.startsWith("ASW:")) return "assetswap";
  if (id.startsWith("FUT:")) return "futures";
  if (id.startsWith("FSW:")) return "futuresswap";
  return "swap";
}

/** 고를 수 있는 선물·퓨처스왑 [OWNER, 2026-08-25 — "선물이랑 선물스왑도"].
 *
 * 채권과 달리 **정적 목록**이다: 상장 만기 두 개(3Y·10Y)의 닫힌 어휘라
 * 데이터가 아니라 문법이고(2016년부터 상시), 백엔드가 선물 종가 SQL 에 못
 * 닿은 날은 실행이 명문 422 로 그 사실을 말한다. 라벨은 서버
 * `futures.FUT_LABELS/FSW_LABELS` 와 같은 글자다 — 용어 동결. */
export const FUTURES_OPTIONS = [
  { value: "FUT:3Y", label: "KTB3 선물" },
  { value: "FUT:10Y", label: "KTB10 선물" },
] as const;
export const FUTURESSWAP_OPTIONS = [
  { value: "FSW:3Y", label: "퓨처스왑 3Y" },
  { value: "FSW:10Y", label: "퓨처스왑 10Y" },
] as const;

export function isBondRow(row: { id: string }): boolean {
  return isBondKind(bookKindOf(row.id));
}

/** 채권 줄의 진입일 기본값 = **1년 전** (데이터 시작일보다 이르면 그 날).
 * 채권은 캐리가 쌓여야 읽히는 화면이라 며칠짜리 기본값은 늘 "거의 0" 을
 * 보여 준다 [v1 CashBondWindow 의 같은 규칙]. */
export function yearBefore(asOf: string, floorDate: string): string {
  const d = new Date(asOf);
  d.setFullYear(d.getFullYear() - 1);
  const iso = d.toISOString().slice(0, 10);
  return iso < floorDate ? floorDate : iso;
}

export interface BookRow extends PositionInput {
  /** 표시용 로컬 키. id 는 중복될 수 있다(같은 종목을 다른 날 두 번). */
  key: string;
}

/** 새 줄의 진입일 기본 — **상품이 정한다.**
 *
 * 스왑은 데이터 일자(오늘), 채권은 1년 전이다. 두 규칙이 갈리는 이유는 위
 * `yearBefore` 에 적혀 있고, 그것을 **부르는 자리마다** 다시 판단하면 언젠가
 * 한 곳만 안 따라간다 — 실제로 창을 합치는 첫 판에서 그렇게 됐다(현금채권 탭의
 * 백테스트 버튼과 「줄 추가」 가 채권 줄에 오늘을 심어, 늘 «거의 0» 을 보여
 * 주는 북이 떴다). */
export function defaultEntry(
  id: string,
  asOf: string,
  bondAsOf: string,
  bondFrom: string,
): string {
  return isBondRow({ id }) ? yearBefore(bondAsOf, bondFrom) : asOf;
}

let seq = 0;
export function newRow(id: string, entry: string): BookRow {
  seq += 1;
  return { key: `r${seq}`, id, direction: 1, eok: 100, entry, exit: "" };
}

/**
 * 방향을 **뭐라고 부르는가** [v1 OWNER, 외부 조사 후 2026-07-31].
 *
 * 엔진에서 `+1` 은 언제나 "호가값을 롱" 이다. 그걸 뭐라 부르는지는 종목마다 다른
 * 질문이었다:
 *
 *   아웃라이트 — **페이 / 리시브**. 원화 데스크는 이걸 동사로 쓴다("IRS 페이했다").
 *   고정 지급/수취는 회계의 말이지 트레이딩의 말이 아니다.
 *
 *   스프레드 — **스티프너 / 플래트너**는 시장 표준이다. 스티프너를 산다 = 가장 긴
 *   다리에 고정을 지급한다(Clarus), 그리고 그게 `backtest._legs_for` 가 만드는
 *   것이다. 다리를 옆에 같이 적으므로 용어만 믿을 필요는 없다.
 *
 *   버터플라이 — **용어가 없다.** 그게 조사의 결론이지 빈틈이 아니다. Clarus 는
 *   플라이를 사는 것 = 벨리 페이라 하고, 다른 데스크 글은 반대로 쓴다.
 *   TraditionData 는 아예 "한 트레이더의 'buy the fly' 가 다른 트레이더의 그것과
 *   같다는 보장이 없다 — 다리를 명시하지 않는 한" 이라고 적는다. 그래서 **다리를
 *   적고 단어를 만들지 않는다.** (v1 이 벨리 지급/수취, 벨리 페이/리시브 두 번
 *   지어냈다가 둘 다 오너가 처음 듣는 말이었다.)
 *
 * `backtest._legs_for` 를 그대로 반영한다: 2다리 `A-B` 는 +1 에서 B 를 페이,
 * 3다리 `A-B-C` 는 +1 에서 벨리 B 를 페이. 라벨이 거래와 조용히 어긋나면 라벨이
 * 없는 것보다 나쁘다.
 */
export function directionLabel(id: string, direction: number): string {
  // 채권은 살 수만 있다 [OWNER, 2026-08-14] — 화면은 이 줄에 방향 칸을 안
  // 그리지만, 부르는 자리가 생겼을 때 "페이" 라고 답하면 그건 거짓말이다.
  if (isBondKind(bookKindOf(id))) return "매수";
  // 선물 [2026-08-25]: +1 = 가격 롱 = **매수** (금리가 내리면 이득).
  if (bookKindOf(id) === "futures") return direction > 0 ? "매수" : "매도";
  // 퓨처스왑: +1 = 호가값(IRS − 내재) 롱. 단어를 만들지 않고 **다리를
  // 적는다**(플라이의 그 규칙): 스프레드가 벌어질 때 버는 쪽 = IRS 페이 +
  // 선물 매수다(IRS↑ = 페이 이득, 내재↓ = 선물 가격↑).
  // ⚠ 2026-09-22 에 **뜻이 뒤집혔다** [OWNER — "스왑 - 채권현물 또는 국채선물"] —
  // 같은 `+1` 이 종전에는 선물 매도·IRS 리시브였다. 엔진의 `futures.py` 머리와
  // 한 문장이어야 한다: 라벨이 거래와 조용히 어긋나면 라벨이 없는 것보다 나쁘다.
  if (bookKindOf(id) === "futuresswap")
    return direction > 0 ? "IRS 페이 · 선물 매수" : "IRS 리시브 · 선물 매도";
  const legs = id.split("-");
  const pay = direction > 0 ? "페이" : "리시브";
  const rec = direction > 0 ? "리시브" : "페이";
  if (legs.length === 3) return `${legs[1]} ${pay} · ${legs[0]}/${legs[2]} ${rec}`;
  if (legs.length === 2) {
    const word = direction > 0 ? "스티프너" : "플래트너";
    return `${word} (${legs[1]} ${pay} · ${legs[0]} ${rec})`;
  }
  return pay; // 아웃라이트 — 스왑 하나다
}

/** 실행할 수 있는 줄만. 종목과 진입일이 있고 규모가 0 이 아니어야 한다 —
 * 반쯤 채운 줄을 서버에 보내면 422 를 라벨 없이 받는다. */
export function runnable(book: BookRow[]): BookRow[] {
  return book.filter(
    (r) =>
      r.id &&
      r.entry &&
      r.eok !== 0 &&
      // 채권은 매수만이고 규모도 양수다 [OWNER, 2026-08-14 — "국고채는 매도는
      // 없는거고"]. 서버가 거절하는 것을 화면이 보내지 않는다.
      (!isBondRow(r) || (r.direction === 1 && r.eok > 0)),
  );
}

/* ── URL — 북은 붙여넣을 수 있는 링크다 ─────────────────────────────────────
 *
 * 인코딩은 `lib/api.ts::encodePositions` 것 하나뿐이다(서버가 읽는 바로 그 문자열).
 * 여기 있는 것은 그 역이고, **왕복이 성립하는지**를 가드가 본다 — 링크를 열었을
 * 때 다른 북이 뜨면 그건 남의 답을 내 질문으로 읽는 것이다.
 */
export function encodeBook(book: BookRow[]): string {
  return encodePositions(runnable(book));
}

/** `id,direction,notional,entry[,exit]` 를 `;` 로 이은 문자열의 역. 모양이 안 맞는
 * 조각은 **버린다** — 반쯤 해석한 북으로 실행하느니 그 줄이 없는 게 낫다. */
export function decodeBook(s: string | undefined | null): BookRow[] {
  if (!s) return [];
  const out: BookRow[] = [];
  for (const part of s.split(";")) {
    const f = part.split(",");
    if (f.length < 4) continue;
    const [id, dir, notional, entry, exit] = f;
    const direction = Number(dir);
    const n = Number(notional);
    if (!id || !entry || !Number.isFinite(direction) || !Number.isFinite(n)) continue;
    if (direction !== 1 && direction !== -1) continue;
    // 손으로 만든 URL 의 채권 매도 — 서버도 거절한다. 반쯤 해석한 북으로
    // 실행하느니 그 줄이 없는 게 낫다(이 함수의 규칙).
    if (isBondKind(bookKindOf(id)) && (direction !== 1 || n <= 0)) continue;
    seq += 1;
    out.push({
      key: `u${seq}`,
      id,
      direction,
      // 서버 문법은 원이고 화면은 억이다. 나누는 자리는 여기 하나뿐.
      eok: n / 1e8,
      entry,
      exit: exit ?? "",
    });
    if (out.length >= MAX_POSITIONS) break;
  }
  return out;
}

/* ── 세션 기억 ──────────────────────────────────────────────────────────────
 *
 * 창을 닫았다 열면 **적어둔 북이 그대로** 있다. 창 위치와 같은 이유로 모듈
 * 변수다(localStorage 아님): 북은 그 세션의 질문이고, 어제의 질문이 오늘 창을
 * 열자마자 떠 있으면 그건 남의 답이다.
 *
 * 결과도 같이 기억한다. 이미 실행을 눌러서 받은 답을 다시 보여주는 것은
 * "스스로 실행되지 않는다" 를 어기지 않는다 — 아무것도 돌지 않는다.
 */
export interface BacktestMemory {
  book?: BookRow[];
  result?: unknown;
}

const memory = new Map<string, BacktestMemory>();

export function saveBacktestMemory(key: string, patch: BacktestMemory): void {
  memory.set(key, { ...memory.get(key), ...patch });
}

export function loadBacktestMemory(key: string): BacktestMemory {
  return memory.get(key) ?? {};
}

export function forgetBacktestMemory(): void {
  memory.clear();
}
