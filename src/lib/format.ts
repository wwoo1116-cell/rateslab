/* Numeric display grammar.
 *
 * Sign is now carried by BOTH an explicit +/− prefix (U+2212) and a direction
 * hue (red up / blue down — §9, Session 12). The mini-bar keeps sign legible
 * in grayscale, so nothing depends on hue alone. */

import type { Unit } from "./api";

const MINUS = "−";
const EMDASH = "—"; // the null placeholder — never 0.00, never blank (§ vol)

/** Rate level, 4 decimals: 4.2600 */
export function fmtRate(v: number | null | undefined): string {
  return v == null ? "–" : v.toFixed(4);
}

/** Signed delta in bp, 1 decimal: +4.3 / −12.5
 *
 * `digits` 는 **대사표**를 위한 자리다 [2026-08-28]. 그 표는 곱셈이 한 줄 안에서
 * 닫히는 것을 눈으로 보이는 물건이라 하루 0.17bp 가 정수·1자리 반올림에 지워지면
 * 안 된다 — `ui/window/ReconStack.tsx` 가 Δbp 를 두 자리로 적는 것과 같은 근거다.
 * 기본값은 종전 그대로라 부르던 자리는 하나도 안 바뀐다. */
export function fmtBp(v: number | null | undefined, digits = 1): string {
  if (v == null) return "–";
  const s = Math.abs(v).toFixed(digits);
  return v < 0 ? `${MINUS}${s}` : `+${s}`;
}

/**
 * The unit as it is WRITTEN BESIDE A NUMBER in running text — a row's subtitle,
 * a tooltip, a sentence. NOT for column headers: a column names its unit once at
 * the top, and repeating it in every cell pushes the digits apart, which is the
 * one thing a column of comparable numbers must not do.
 *
 * `가격` and `ratio` return the empty string, and neither is an oversight.
 * A futures price point is a price — nobody writes "104.230가격" — and a ratio is
 * dimensionless, so any suffix here would be a unit this product invented rather
 * than one its readers use.
 */
export function unitSuffix(unit: Unit): string {
  if (unit === "%") return "%";
  if (unit === "bp") return "bp";
  return "";
}

/** Level, unit-aware: % → 4dp, bp → 1dp, ratio → 2dp. Null → em dash. */
export function fmtLevel(v: number | null | undefined, unit: Unit): string {
  if (v == null) return EMDASH;
  if (unit === "%") return v.toFixed(4);
  if (unit === "ratio") return v.toFixed(2);
  // 가격: futures price points. Three places, because 저평가 lives in the third —
  // at two it prints as -0.0 and reads as "no basis".
  if (unit === "가격") return v.toFixed(3);
  return v.toFixed(1);
}

/** A candle's 등락률 — (종가 − 시가) / 시가, 2dp, signed (§G).
 *
 * ONE function because two surfaces print it: the popup's candle tooltip and,
 * since 2026-08-13, the preview chart's. It lived inline in DetailChart as a
 * bare `toFixed(2)`, which is exactly the second-display-grammar failure this
 * module exists to prevent (readout-parity).
 *
 * A ZERO OPEN HAS NO PERCENT CHANGE and prints the em dash. The inline version
 * returned `+0.00%` there, which is not a rounding — it is a fabricated number
 * on a bar that moved. Spreads and butterflies cross zero, so this is a real
 * bar in this product, not a theoretical one.
 */
export function fmtChangePct(
  open: number | null | undefined,
  close: number | null | undefined,
): string {
  if (open == null || close == null || open === 0) return EMDASH;
  const pct = ((close - open) / open) * 100;
  const s = `${Math.abs(pct).toFixed(2)}%`;
  return pct < 0 ? `${MINUS}${s}` : `+${s}`;
}

/** Signed change, unit-aware. A ratio's change is a ratio difference at 2dp
 * with no unit; bp/% changes stay at 1dp (fmtBp). Null → em dash. */
export function fmtDelta(v: number | null | undefined, unit: Unit): string {
  if (v == null) return EMDASH;
  if (unit === "ratio") {
    const s = Math.abs(v).toFixed(2);
    return v < 0 ? `${MINUS}${s}` : `+${s}`;
  }
  return fmtBp(v);
}

/* The LEVEL HEADER — the label over every current-level surface (pass M).
 *
 * It used to read 현재, which named the quantity and not the DAY it belongs to.
 * Against a dataset that is a file, those are different facts: the level under
 * that header is a CLOSE, and on any day the file has not been rebuilt, "현재"
 * asserts something the data cannot support. The header now prints the date
 * instead, and the word is gone from the level surfaces.
 *
 * THE DATE IS THE DATASET'S `asof`, NEVER THE READER'S CLOCK [OWNER]. A header
 * derived from `new Date()` would print today over last Friday's closes — the
 * silent-staleness failure `lib/freshness.ts` exists to prevent, restated in
 * the one place a reader trusts most. When the data IS current the two agree,
 * which is the whole point; when they disagree the honest one is `asof`, and
 * the header then says the same day as the freshness chip beside it.
 */

/**
 * The dataset's as-of date as the level header — **month and day, no year**
 * [OWNER 2026-08-14: "앞에 연도는 없애줘도 될 듯"].
 *
 * MEASURED, and the reason the owner saw it wrap: a CDS `TableCell` spends 16px
 * on each side, so the 104px 현재 column offers 72px of text width, and
 * `2026-08-13` at 13px/600 renders 78.2px. It broke to two lines and made the
 * header row taller than every other column's.
 *
 *     2026-08-13   78.2 px   ← wraps in 72
 *          08-13   ~40  px   ← one line, with room
 *
 * The year is not lost: `levelHeadTitle` keeps the full date in the cell's
 * tooltip, and the freshness chip in the top bar states it in full beside the
 * feed's name. A column header names the day; the page states the date.
 *
 * Falls back to the quantity's name if a payload arrives without one — a header
 * that names nothing is worse than the old word. Width comes from
 * `WIDEST.levelHead` (table/columns.ts); keep the two in step.
 */
export function levelHeadText(asof: string | null | undefined): string {
  if (!asof || asof.length === 0) return "현재";
  // ISO `YYYY-MM-DD` → `MM-DD`. Anything else is passed through untouched
  // rather than sliced blindly: a payload with a different shape should look
  // wrong, not be silently trimmed to five characters of something else.
  const m = /^\d{4}-(\d{2}-\d{2})$/.exec(asof);
  return m ? m[1] : asof;
}

/** The header's tooltip: what the column's numbers are. */
export function levelHeadTitle(asof: string | null | undefined): string {
  return asof && asof.length > 0 ? `${asof} 종가 기준` : "가장 최근 레벨";
}

/** AXIS orientation label — deliberately COARSER than a level (bp → 1dp,
 * % / ratio → 2dp). Two gridline values exist to orient the eye on a y-range,
 * and `4.2446` in that role reads as data; full precision belongs to the
 * readout card, through `fmtLevel`. One definition for every chart axis
 * (CurveView's y marks, the preview's dual-axis unit ticks) so "how coarse is
 * an axis" cannot drift per surface. */
export function fmtAxis(v: number, unit: Unit): string {
  return unit === "bp" ? v.toFixed(1) : v.toFixed(2);
}

/** Tailwind text-color class for a signed value: red up, blue down, ink flat
 * (§9 direction). Null/zero is neutral ink. */
export function dirClass(v: number | null | undefined): string {
  if (v == null || v === 0) return "text-ink";
  return v > 0 ? "text-up" : "text-down";
}

/** 표 머리의 활자를 고른다 — **소문자가 들어 있으면 `legal`, 아니면 `caption`**.
 *
 *  CDS 기본 테마의 `textTransform.caption = 'uppercase'` 가 「z」를 「Z」로,
 *  「bp」를 「BP」로 만든다. 둘은 크기가 같고(0.8125rem) 중량·대문자화만 다르므로,
 *  **기호와 단위가 든 머리**만 `legal` 이다. MR 대사표·거래 표 머리가 이 기준을
 *  주석으로 지고 있었고 2026-09-02 에 함수가 됐다(눈대중에 걸리지 않게).
 *
 *  ⚠ 2026-09-09 에 `src/mr/parts.tsx` 에서 여기로 옮겼다 — `ui/ThHelp` 도 같은
 *  기준을 써야 하는데(도움말이 달린 머리에서 「bp」가 「BP」로 섰다) `ui/` 가
 *  기능 폴더(`mr/`)를 임포트할 수는 없다. 기준이 둘이 되면 한 표 안에서 도움말이
 *  달린 머리만 다른 활자로 선다. `mr/parts` 는 이 함수를 다시 내보낸다. */
export function headFont(label: string): "caption" | "legal" {
  return /[a-z]/.test(label) ? "legal" : "caption";
}

/** 비율 한 칸 — 소수 둘. **못 잰 값은 «—» 다**(0 이 아니다: 「쟀는데 0」과
 *  구별이 안 된다).
 *
 *  ⚠ 여기 있는 이유: 같은 함수가 `mr/parts` 와 모멘텀 화면에 **글자 하나 안 틀리고
 *  두 벌** 있었다. 캐논 규칙 8(「같은 것은 한 번만 만든다」)의 그 자리다 — `Field`
 *  가 네 곳에 흩어져 라벨 타이포가 셋으로 갈렸던 판례와 같다. */
export function fmtRatio(v: number | null | undefined): string {
  return v == null ? "—" : v.toFixed(2);
}
