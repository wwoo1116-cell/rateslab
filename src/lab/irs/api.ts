import { paperLiveUrl, summaryUrl } from '@/lib/staticPaths';

/* ── 실시간 IRS — 두 시계를 한 줄에 [OWNER 2026-10-01] ────────────────────────
 *
 * [OWNER] 「스왑 데이터를 실시간으로 받아오고 있는데, Lab 탭에서 실시간 IRS 를 볼
 * 수 있을지」. 볼 수 있다 — **자료는 이미 와 있었다.** `infomax_API.irs_infomax`
 * (IRS 전 만기 · 초 단위)를 백엔드가 페이퍼 북 장중 평가용으로 벌써 읽고 있고
 * (`paperlive.py`), `/api/paper/live` 로 나와 있다. 없던 것은 **화면**뿐이다.
 *
 * ── 이 화면이 답하는 질문 ───────────────────────────────────────────────────
 * **「지금, 종가 대비 몇 bp 움직였나」.** v2 어디에도 없던 수다 — Main 은 종가와
 * **전일 대비**(어제 대 그제)를 말하지 오늘 장중을 말하지 않는다. 그래서 두 출처를
 * 겹친다:
 *
 *     지금  `/api/paper/live`    IRS 17만기 초 단위 (+ 국채선물 3Y·10Y 내재금리)
 *     종가  `/api/wall/summary`  `outrights[].now` — 그 날짜는 그 페이로드의 `asof`
 *
 * ⚠ **두 출처의 만기 집합이 다르다.** 라이브는 6M~30Y 열일곱이고 종가 쪽은 그
 * 부분집합이다. 겹치는 만기에서만 Δ 가 서고 나머지는 `close: null` 로 둔다 —
 * 빈칸이 **「0 움직임」으로 보이면 안 된다**(0 과 모름은 딴 사실이다, rv 의 그 규율).
 *
 * ⚠ **산술은 네트워크를 모른다.** `mergeIrs` 는 순수 함수라 가드가 서버 없이 Δ·
 * 결측·부호를 전부 잰다 — `paperlive.py` 가 `irs_levels` 를 SQL 밖으로 떼어 낸
 * 그 이유와 같다(「적대 검증 2026-09-28」).
 *
 * ⚠ **낡음 판정은 서버가 진다.** 「오늘 자료가 아니다 / N분 전 값이다」는
 * `paperlive` 가 정하고 값을 **안 싣고** 사유를 든다. 화면이 두 번째 의견을 내면
 * 갈리는 날이 온다 — 여기서는 그 사유를 그대로 옮겨 적기만 한다.
 */

/** `/api/paper/live` 의 한 칸. `kind` 는 `irs` 또는 `fut`(국채선물 내재금리). */
export type LiveLevel = {
  kind: string;
  tenor: string;
  level: number;
  at: string;
  source: string;
};

export type LiveSource = {
  name: string;
  table?: string | null;
  asof?: string;
  ageMin?: number | null;
  why?: string;
};

export type LivePayload = {
  available: boolean;
  levels: LiveLevel[];
  asof?: string | null;
  sources: LiveSource[];
  why?: string | null;
};

/** `/api/wall/summary` 에서 이 화면이 쓰는 조각만. `now` 가 그 날 **종가**다. */
export type CloseOutright = { id: string; label: string; now: number | null };
export type ClosePayload = { asof: string; outrights: CloseOutright[] };

export type IrsRow = {
  tenor: string;
  /** 지금(라이브, %). */
  now: number | null;
  /** 종가(%). 종가 쪽에 그 만기가 없으면 `null`. */
  close: number | null;
  /** 일중 = (지금 − 종가) × 100. 한쪽이라도 없으면 `null`. */
  moveBp: number | null;
  at: string | null;
};

/** 스왑 − 국채선물 내재금리(bp). **부호 규약은 리포의 그것**(BSS·FSW·ASW =
 *  스왑 − 채권현물/국채선물) — 계열만 뒤집으면 안 되는 자리다. 둘 다 라이브라
 *  같은 시계를 본다. */
export type FutBasis = { tenor: string; swap: number; fut: number; bp: number };

export type IrsBoard = {
  rows: IrsRow[];
  futBasis: FutBasis[];
  /** 라이브 시각(`HH:MM:SS`) 과 나이(분) — 출처가 적어 준 그대로. */
  liveAsof: string | null;
  liveAgeMin: number | null;
  /** 종가 기준일. */
  closeAsof: string | null;
  /** 라이브가 안 선 사유. 값이 없을 때 **왜 없는지**를 화면이 말하게 한다. */
  why: string | null;
};

/* ⚠ 여기서 **반올림하지 않는다** [2026-10-01]. 처음엔 소수 첫째까지 깎아서
 * 내보냈는데, 표기(`fmtBp`)가 어차피 한 번 더 깎으므로 **깎는 자리가 둘**이 된다.
 * 이중 반올림은 경계에서 갈린다(6.65 를 먼저 6.7 로 깎고 다시 적는 것과, 6.65 를
 * 한 번에 적는 것은 같은 수가 아니다). 자리수를 아는 곳은 `lib/format` 하나다 —
 * 레벨·bp 표기가 한 벌인 그 규율.
 *
 * 부수로 배운 것: `4.0675 − 4.0` 은 이진수로 정확히 `0.0675` 가 아니라 ×100 이
 * **6.7499…** 다. 「6.75 니까 6.8」이라고 적었던 내 첫 시험이 그래서 틀렸다 —
 * 원값을 들고 있으면 그 사실이 보이고, 미리 깎으면 안 보인다.
 *
 * 틴트(`tintAlpha`)도 원값을 받는 편이 낫다 — 0.5bp 바닥 판정이 이미 깎인 수에
 * 걸리면 경계에서 한 칸이 조용히 색을 잃는다. */

export function mergeIrs(live: LivePayload, close: ClosePayload | null): IrsBoard {
  const closeBy = new Map<string, number>();
  for (const o of close?.outrights ?? []) {
    /* `id` 가 만기 이름이다(`IRS 6M` 은 라벨 쪽). `1D`(콜)는 커브 만기가 아니라 뺀다. */
    if (o.id !== '1D' && o.now != null) closeBy.set(o.id, o.now);
  }

  const rows: IrsRow[] = [];
  const swapBy = new Map<string, number>();
  for (const l of live.levels ?? []) {
    if (l.kind !== 'irs') continue;
    swapBy.set(l.tenor, l.level);
    const c = closeBy.get(l.tenor);
    rows.push({
      tenor: l.tenor,
      now: l.level,
      close: c ?? null,
      moveBp: c === undefined ? null : (l.level - c) * 100,
      at: l.at ?? null,
    });
  }

  const futBasis: FutBasis[] = [];
  for (const l of live.levels ?? []) {
    if (l.kind !== 'fut') continue;
    const swap = swapBy.get(l.tenor);
    /* 짝이 없으면 안 세운다 — 한쪽만으로는 베이시스가 아니다. */
    if (swap === undefined) continue;
    futBasis.push({
      tenor: l.tenor,
      swap,
      fut: l.level,
      bp: (swap - l.level) * 100,
    });
  }

  const irsSrc = (live.sources ?? []).find((s) => s.name === 'IRS');
  /* 사유는 **출처의 것이 먼저**다(만기별로 적힌 그 문장), 없으면 페이로드의 것. */
  const why = irsSrc?.why ?? live.why ?? null;

  return {
    rows,
    futBasis,
    liveAsof: irsSrc?.asof ?? live.asof ?? null,
    liveAgeMin: irsSrc?.ageMin ?? null,
    closeAsof: close?.asof ?? null,
    why,
  };
}

export async function fetchIrsBoard(): Promise<IrsBoard> {
  const [liveR, closeR] = await Promise.all([fetch(paperLiveUrl()), fetch(summaryUrl())]);
  if (!liveR.ok) throw new Error(`장중 시세: HTTP ${liveR.status}`);
  const live = (await liveR.json()) as LivePayload;
  /* 종가는 **없어도 화면이 선다** — 그러면 Δ 칸만 빈다. 라이브가 주인공이고,
     종가는 그것을 읽는 자[尺]다. */
  const close = closeR.ok ? ((await closeR.json()) as ClosePayload) : null;
  return mergeIrs(live, close);
}
