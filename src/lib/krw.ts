/* Money, the way a Korean desk reads it: 억 / 만, never 12 raw digits.
 *
 * V2 PORT (2026-08-14) of `braveworld/frontend/src/ui/krw.ts`, brought over
 * with the 세타 column — the first v2 surface that prints won. Three of v1's
 * four functions came: `manUnits`, `fmtKrwFromMan`, `fmtKrw`. `splitKrw` did
 * NOT — it exists for the backtest's 손익 구성 (평가/롤다운/캐리 must sum at
 * displayed precision), and v2 has no backtest yet. Copying it now would ship
 * a function nothing calls and nothing tests; it comes with 레인 4.
 *
 * ROUNDED to the nearest 만원, not floored (v1, 2026-08-03 verification). The
 * floor shipped a visible lie: the real book was 평가 1,091,329,056 + 캐리
 * 823,973 = 1,092,153,029 to the won, and the screen said 9,132만 + 82만
 * against a 9,215만 total — off by one 만원, purely from truncating each
 * figure separately. Rounding alone does not make PARTS SUM at displayed
 * precision; that is what `manUnits` is exported for, and why `thetaTitle`
 * differences its two displayed endpoints instead of rounding three figures
 * independently. Symmetric under negation (sign·round(|v|)), so a payer and
 * its mirror receiver always print mirror figures.
 *
 * The minus sign is U+2212 (−), not the hyphen: it is the same glyph
 * `lib/format.ts` uses for every other signed number on this screen, and a
 * table that mixes the two has two different-looking minus signs in one row.
 */

/** Nearest 만원, as signed integer units — the arithmetic domain in which
 * displayed money is additive. */
export function manUnits(v: number): number {
  return Math.sign(v) * Math.round(Math.abs(v) / 10_000);
}

/** Money from signed 만-units. The units-based twin of `fmtKrw`: a readout
 * whose parts must sum at displayed precision does its arithmetic on units and
 * formats the results through this. */
export function fmtKrwFromMan(units: number): string {
  const sign = units < 0 ? '−' : '+';
  const n = Math.abs(units);
  const eok = Math.floor(n / 10_000);
  const man = n % 10_000;
  if (eok > 0) return `${sign}${eok}억${man ? ` ${man.toLocaleString()}만` : ''}원`;
  return `${sign}${man.toLocaleString()}만원`;
}

export function fmtKrw(v: number): string {
  const n = Math.abs(Math.round(v));
  if (n < 10_000) return `${v < 0 ? '−' : '+'}${n.toLocaleString()}원`;
  return fmtKrwFromMan(manUnits(v));
}

/**
 * 평가 + 롤다운 + 캐리 = 합계, **표시 정밀도에서**, 구성상 그렇게 되도록.
 *
 * 레인 4 에서 실측으로 걸렸다(2026-08-14): 세 항목을 각자 `fmtKrw` 로 반올림했더니
 * 화면이 `평가 −3억 9,971 + 롤다운 +2억 9,148 + 캐리 +4,696` 인데 헤드라인은
 * **−6,128만원**(합은 −6,127)이었다. **1만원**이고, 이 리포는 이 거짓말을 이미 한 번
 * 출하한 적이 있다 — 삭제된 캐리&롤 블록이 −3.2 대 −3.1 로 어긋났던 그것이다.
 *
 * 그래서 합계·평가·롤다운만 각각 한 번 반올림하고 **캐리는 그 차로 낸다**. 반올림
 * 오차가 한 항목에 모이는 대신 네 숫자가 서로 모순되지 않는다. `fmtMove` 가 표시된
 * 두 끝점을 빼서 변화를 내는 것과 같은 선례다.
 *
 * v1 `ui/krw.ts::splitKrw` 의 이식. `rolldown` 이 0 기본인 것도 그대로다 — 롤다운이
 * 없던 시절의 결과(평가가 롤을 품고 있는)를 복원해도 그때 저장된 그대로 보인다.
 */
export function splitKrw(
  pnl: number,
  valuation: number,
  rolldown: number = 0,
  startup: number = 0,
): { uPnl: number; uVal: number; uRoll: number; uCarry: number } {
  const uPnl = manUnits(pnl);
  /* **개시는 평가에 접어 넣는다** [OWNER, 2026-08-14 — "개시손익 적으면 걍
   * 무시해도 될 거 같은데"]. 그 밤을 롤다운에서 빼낸 것은 그대로다 — 바뀌는
   * 것은 어느 칸이 그것을 안고 있느냐뿐이고, 총손익 대비 0.005% 짜리 숫자에
   * 열을 하나 더 주지 않기로 한 것이다. 대가는 적어 둔다: 그 밤은 엄밀히
   * '금리가 움직인 몫'이 아닌데 평가가 그것을 안는다. 서버는 여전히 `startup`
   * 을 따로 보낸다 — 접는 것은 표시 결정이고, 다시 펴려면 여기 하나만 고친다. */
  const uVal = manUnits(valuation + startup);
  const uRoll = manUnits(rolldown);
  return { uPnl, uVal, uRoll, uCarry: uPnl - uVal - uRoll };
}

/** 현금채권의 네 칸을 표시 정밀도에서 가산적으로 [OWNER, 2026-08-14].
 *
 * `splitKrw` 와 **같은 수법·같은 규칙**이다: 합계와 평가·롤다운·조달이 각각 한
 * 번씩 반올림하고, 캐리가 그 잔차를 진다. 개시는 평가에 접힌다(위 참조) —
 * 현금채권 단독은 어차피 0 이고, 자산스왑에서만 스왑 다리 몫으로 붙는다.
 *
 * 잔차에 실리는 반올림이 셋이라 캐리는 원 단위 값에서 최대 2만원까지 떨어질 수
 * 있다. 그래도 **행은 반드시 가로로 더해진다** — 그 성질이 이 표의 존재
 * 이유다(읽는 사람이 암산으로 표의 거짓말을 잡을 수 있어야 한다).
 *
 * 조달은 서버가 이미 음수로 준다(`app/cashbond.py`) — 여기서 부호를 다시 주면
 * 두 번 뒤집힌다. */
export function splitCashBondKrw(
  pnl: number,
  valuation: number,
  rolldown: number,
  funding: number,
  startup: number,
): {
  uPnl: number;
  uVal: number;
  uRoll: number;
  uFund: number;
  uCarry: number;
} {
  const uPnl = manUnits(pnl);
  const uVal = manUnits(valuation + startup);
  const uRoll = manUnits(rolldown);
  const uFund = manUnits(funding);
  return { uPnl, uVal, uRoll, uFund, uCarry: uPnl - uVal - uRoll - uFund };
}

/** **부호 없는** 압축 크기 — `1.2억` · `100만` · `8,300`.
 *
 *  `fmtKrw` 와 다른 물건이다: 저쪽은 **손익**이라 부호가 뜻을 지고 「+1억 2,000만원」
 *  으로 적는다. 이쪽은 **크기**(액면·변동성 목표처럼 부호가 없는 값)라 부호를 붙이면
 *  없는 방향을 주장하게 된다.
 *
 *  ⚠ 여기 있는 이유: 모멘텀 화면이 `fmtEok`·`fmtMan` 두 벌을 자기 파일 안에 들고
 *  있었다. 캐논 규칙 1(「새로 만들기 전에 찾는다」)은 없을 때 만들지 말라는 뜻이
 *  아니라 **찾을 수 있는 자리에 두라**는 뜻이다 — 다음 화면이 또 만들지 않도록.
 *
 *  ⚠ **단위(「원」)를 안 붙인다** — 캐논이 「열 제목이 단위를 진다」이고, 표 안에서는
 *  머리(「액면」)가 그 일을 한다. 문장 안에 쓸 때만 부르는 쪽이 「원」을 붙인다.
 *  처음 판은 작은 값 갈래만 「원」을 달고 있어서 문장에서 「8,300원원」이 됐다. */
export function fmtSize(v: number | null | undefined): string {
  if (v == null) return "—";
  const n = Math.abs(v);
  if (n >= 1e8) return `${(n / 1e8).toFixed(1)}억`;
  if (n >= 1e4) return `${Math.round(n / 1e4).toLocaleString()}만`;
  return Math.round(n).toLocaleString();
}
