/* Instrument explanation for the enlarged view (DESIGN §2 popup, Session 15
 * Pass C). What a thing *is* — static, keyed to instrument kind.
 *
 * §16: the API sends the classification (kind + legs, already present as
 * `kind`/`id`); the frontend renders the Korean here. No finished Korean string
 * ever ships from the backend, so wording changes never need a deploy. This is
 * purely presentation and lives only in the popup — it is not a table column
 * and not a row view-model field, so the row-vm-source guard is untouched.
 *
 * Since pass L deleted the 한 줄, THIS is one of the §16 exception's two
 * remaining subjects (the other is the curve banner) — see DESIGN §16. The
 * same classification also drives the Pay/Receive mode diagram, so `classify`
 * has two consumers, not one.
 *
 * Register: 해요체, one fact per sentence [OWNER, 2026-08-05 — reverses the
 * Session 15 합니다체 migration]. VOCABULARY DID NOT MOVE WITH IT: standard
 * market terminology only, never paraphrased into everyday words (§15 용어 —
 * 나비 / 양옆 / 싼지 비싼지 stay banned). Register is the only axis that
 * changed. */

import type { Row } from "./rows";
import { eul, gwa } from "@/lib/josa";

export type Construct =
  | { kind: "outright"; tenor: string }
  | { kind: "call" } // the 1D overnight call rate (an outright row, but not an IRS)
  | { kind: "spread"; short: string; long: string }
  | { kind: "butterfly"; short: string; belly: string; long: string }
  | { kind: "forward"; start: string; tenor: string }
  | { kind: "volatility"; tenor: string }
  | { kind: "unknown" };

/** Classify a row from its group + id (the legs). Butterfly vs spread is the
 * leg count on a derived id; the call rate is the 1D outright. */
export function classify(row: Row): Construct {
  if (row.group === "vol") {
    return { kind: "volatility", tenor: row.id.replace(/^vol:/, "") };
  }
  if (row.group === "forward") {
    const [start, tenor] = row.id.split("x");
    return { kind: "forward", start, tenor };
  }
  if (row.group === "outright") {
    return row.id === "1D" ? { kind: "call" } : { kind: "outright", tenor: row.id };
  }
  const legs = row.id.split("-");
  if (legs.length === 3) {
    return { kind: "butterfly", short: legs[0], belly: legs[1], long: legs[2] };
  }
  if (legs.length === 2) {
    return { kind: "spread", short: legs[0], long: legs[1] };
  }
  return { kind: "unknown" };
}

/** Tenor label → Korean duration. "10Y"→"10년", "1.5Y"→"1년 6개월",
 * "1Y3M"→"1년 3개월", "6M"→"6개월", "1D"→"1일", "ON"→"익일", "SPOT"→"현물". */
export function tenorKo(t: string): string {
  if (t === "ON") return "익일";
  if (t === "1D") return "1일";
  if (t === "SPOT") return "현물";
  const y = t.match(/(\d+(?:\.\d+)?)Y/);
  const m = t.match(/(\d+)M/);
  const parts: string[] = [];
  if (y) {
    const val = parseFloat(y[1]);
    const whole = Math.floor(val);
    const frac = Math.round((val - whole) * 12);
    if (whole) parts.push(`${whole}년`);
    if (frac) parts.push(`${frac}개월`);
  }
  if (m) parts.push(`${parseInt(m[1], 10)}개월`);
  return parts.join(" ") || t;
}

/** A tight subtitle naming the construct, shown under the instrument name. */
export function instrumentSubtitle(row: Row): string {
  const c = classify(row);
  switch (c.kind) {
    case "call":
      return "익일물(콜) 금리";
    case "outright":
      return `${tenorKo(c.tenor)} 만기 IRS 파 금리`;
    case "spread":
      return `${c.short}·${c.long} 커브 스프레드`;
    case "butterfly":
      return `${c.short}·${c.belly}·${c.long} 버터플라이`;
    case "forward":
      return c.tenor === "SPOT"
        ? `${tenorKo(c.start)} 현물 파 금리`
        : `${tenorKo(c.start)} 후 ${tenorKo(c.tenor)} 선도금리`;
    case "volatility":
      return `${c.tenor} 상대 변동성`;
    default:
      return "";
  }
}

/** Short sentences (해요체) — what it is, how it is built, what a rising value
 * means. Keyed to kind; legs interpolated from the classification.
 *
 * ONE FACT PER SENTENCE [OWNER, 2026-08-05]. Every gloss used to pack three
 * facts into one 86–120자 string; they are now split. The 확대/축소 pair is
 * treated as ONE fact — it is a single sign convention, and splitting it into
 * two sentences reads as pedantry to someone who already knows the term.
 *
 * VOCABULARY IS UNCHANGED. Only the register moved. 버터플라이 / 벨리 / 윙 /
 * 스티프닝 / 플래트닝 / 파 금리 / 내재 선도금리 stay verbatim — see §15
 * 용어. The wording is pinned by gloss.test.ts. */
export function instrumentGloss(row: Row): string {
  const c = classify(row);
  switch (c.kind) {
    case "call":
      return "익일물 콜 금리예요. 국내 단기자금시장의 기준 금리예요. IRS 커브의 단기 앵커로 써요.";
    case "outright":
      return `${tenorKo(c.tenor)} 만기 KRW IRS 파 금리예요. CD 91일물을 변동금리로 교환하는 조건이에요. 국내 IRS 시장의 표준 호가예요.`;
    case "spread":
      return `${c.short}·${c.long} 커브 스프레드예요. ${c.long}에서 ${c.short}${eul(c.short)} 뺀 값이에요. 확대는 스티프닝, 축소는 플래트닝이에요.`;
    case "butterfly":
      return `${c.short}·${c.belly}·${c.long} 버터플라이예요. ${c.belly} 금리의 두 배에서 ${c.short}${gwa(c.short)} ${c.long}${eul(c.long)} 뺀 값이에요. 확대되면 벨리가 윙 대비 약세, 축소되면 강세예요.`;
    case "forward":
      return c.tenor === "SPOT"
        ? `${tenorKo(c.start)} 현물 파 금리예요. 현재 커브에서 도출해요. 해당 구간에 대한 시장의 기대 금리를 나타내요.`
        : `${tenorKo(c.start)} 후 시작하는 ${tenorKo(c.tenor)} 내재 선도금리예요. 현재 커브에서 도출해요. 해당 구간에 대한 시장의 기대 금리를 나타내요.`;
    case "volatility":
      return "최근 5일 평균 변동폭을 60일 평균으로 나눈 상대 변동성 지표예요. 1을 넘으면 단기 변동성이 장기 평균보다 확대된 상태예요.";
    default:
      return "";
  }
}
