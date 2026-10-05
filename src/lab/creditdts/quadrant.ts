/* 사분면의 산술 — **순수 함수**로 떼어 둔다 [OWNER 2026-10-02].
 *
 * ── 왜 모듈을 가르나 ───────────────────────────────────────────────────────
 * [OWNER] 「기존 사분면은 반영을 제대로 못 하고 있었어서 … 지금 이 사분면을
 * 제대로 고칠 수 있으면 그게 더 나을듯」.
 *
 * **제품 사분면이 제대로 반영을 못 한 이유는 축이 점수의 입력이 아니었다는 것**
 * 이다: 제품은 x=월환산 총수익 · y=지난주 백분위를 그리는데 Score 의 입력은 그
 * 둘이 아니다(`spreadVolPct` × `relRv`). 그래서 그림과 순위가 따로 놀았다.
 *
 * 축을 고친 것이 이 레인의 본체이므로, **축 선택 자체를 가드가 잠글 수 있어야**
 * 한다. 컴포넌트 안에 두면 렌더해야 재고, 렌더해 재는 축 계약은 조용히 뒤집힌다
 * (`mergeIrs` 를 `lab/irs/api.ts` 로 떼어 낸 그 이유와 같다).
 *
 * ── 축 ─────────────────────────────────────────────────────────────────────
 *     y = **z** (이 화면의 점수 **그 자체**)   ← 위로 갈수록 제 평소보다 벌어짐
 *     x = **지금 스프레드 수준**(캐리의 대리)  ← 오른쪽으로 갈수록 넓음
 *
 * 그래서 **세로 위치가 곧 순위**이고, 가로는 **점수에서 일부러 뺀 것**이다.
 *
 * §16 과 다투지 않는다 — z 도 랭크도 서버가 낸 값을 그대로 꽂고, 여기서 새로
 * 세는 것은 **경계선 둘과 두 열의 순위상관** 뿐이다(서버가 낸 값들의 순서
 * 통계라 새 사실을 만들지 않는다 — `RvScatter` 가 중앙값 하나를 세는 그 근거).
 */

import type { CreditDtsItem } from './api';

/* z 의 표기는 **여기 없다** — `fmtDelta(z, 'ratio')` 다.
 *
 * 처음엔 손으로 `toFixed(2)` 를 적었는데 그게 음수를 **ASCII 하이픈**으로 냈다.
 * 이 제품의 음수는 U+2212 이고(`lib/format::MINUS`, `guards/krw-additivity` 가
 * 잠근다), z 는 무차원 비율이라 「부호 있는 2자리 비율」이 이미 캐논에 있다.
 * 서식을 두 번째로 적는 순간 한쪽만 고쳐지는 날이 온다. */

/** 순서 통계 하나 — 가로 경계선. 짝수 개면 두 가운데의 평균.
 *  **제품 `RvScatter::median` 과 같은 규약**이다 — 같은 일을 두 문법으로 하면
 *  셋째가 생기는 날 어느 쪽을 따를지가 취향 문제가 된다. */
export function median(xs: readonly number[]): number {
  if (xs.length === 0) return 0;
  const a = [...xs].sort((p, q) => p - q);
  const i = Math.floor(a.length / 2);
  return a.length % 2 ? a[i]! : (a[i - 1]! + a[i]!) / 2;
}

/** 두 열의 **스피어만 상관** — 이 수리의 증거를 화면이 직접 말한다.
 *
 *  0 에 가까울수록 「싼 것」과 「넓은 것」이 갈려 있다는 뜻이고, 그게 제품
 *  Score(같은 만기 안 레벨 누출 **+0.418**)와 이 축(**+0.076**)의 차이다.
 *  점수에는 **안 들어간다** — 읽는 사람에게 한 줄 적는 용도다.
 *
 *  동순위는 **평균 순위**로 묶는다. 민평은 평가사 호가라 같은 값이 흔하고,
 *  순차 순위를 매기면 입력 순서가 상관에 샌다. 표본이 8 미만이면 `null` —
 *  칸 셋으로 「거의 직교한다」를 주장할 수는 없다. */
export function spearman(xs: readonly number[], ys: readonly number[]): number | null {
  const n = xs.length;
  if (n !== ys.length || n < 8) return null;
  if (!xs.every(Number.isFinite) || !ys.every(Number.isFinite)) return null;

  const rank = (a: readonly number[]): number[] => {
    const order = a.map((v, i) => [v, i] as const).sort((p, q) => p[0] - q[0]);
    const r = new Array<number>(n);
    let i = 0;
    while (i < n) {
      let j = i;
      while (j + 1 < n && order[j + 1]![0] === order[i]![0]) j += 1;
      /* 동순위 구간 [i..j] 의 평균 순위(1-기준). */
      const avg = (i + j) / 2 + 1;
      for (let k = i; k <= j; k += 1) r[order[k]![1]] = avg;
      i = j + 1;
    }
    return r;
  };

  const rx = rank(xs);
  const ry = rank(ys);
  const mx = rx.reduce((a, b) => a + b, 0) / n;
  const my = ry.reduce((a, b) => a + b, 0) / n;
  let sxy = 0;
  let sxx = 0;
  let syy = 0;
  for (let i = 0; i < n; i += 1) {
    const dx = rx[i]! - mx;
    const dy = ry[i]! - my;
    sxy += dx * dy;
    sxx += dx * dx;
    syy += dy * dy;
  }
  return sxx > 0 && syy > 0 ? sxy / Math.sqrt(sxx * syy) : null;
}

export const PAD = { l: 46, r: 14, t: 14, b: 36 } as const;

export interface QuadrantPoint {
  id: string;
  /** 화면 좌표(px). 축 계약이 여기서 닫힌다. */
  cx: number;
  cy: number;
  item: CreditDtsItem;
}

export interface QuadrantGeometry {
  points: QuadrantPoint[];
  /** 가로 경계 = **오늘 후보의 중앙값**. 0 을 그으면 전부 오른쪽에 몰린다
   *  (제품 사분면이 같은 이유로 중앙값을 쓴다). */
  xMid: number;
  xMidPx: number;
  /** 세로 경계 = **0**(자기 평소) 그 자체. x 와 **일부러 다르다**: z 는 이미
   *  자기 이력에 상대화된 수라 절대선 0 이 뜻을 가진다(제품의 y=50 과 같은
   *  자세). 중앙값으로 바꾸면 날마다 반씩 갈라 그 사실을 지운다. */
  zeroPx: number;
  /** 0 이 자료 범위 밖이면 경계선을 **안 긋는다** — 그려 둔 선이 범위 끝에
   *  달라붙어 「전부 한쪽」을 「절반씩」처럼 보이게 한 전례가 있다. */
  zeroInRange: boolean;
  inner: { w: number; h: number };
}

/** 실측 크기로 좌표를 낸다(손 차트들의 관용구 — 고정 viewBox 는 여백을 만든다). */
export function quadrantGeometry(
  items: readonly CreditDtsItem[],
  w: number,
  h: number,
): QuadrantGeometry {
  const iw = Math.max(10, w - PAD.l - PAD.r);
  const ih = Math.max(10, h - PAD.t - PAD.b);

  const xs = items.map((it) => it.nowBp);
  const ys = items.map((it) => it.z);
  const x0 = xs.length ? Math.min(...xs) : 0;
  const x1 = xs.length ? Math.max(...xs) : 1;
  const y0 = ys.length ? Math.min(...ys) : 0;
  const y1 = ys.length ? Math.max(...ys) : 1;

  const px = (v: number) => PAD.l + ((v - x0) / Math.max(1e-9, x1 - x0)) * iw;
  const py = (v: number) => PAD.t + (1 - (v - y0) / Math.max(1e-9, y1 - y0)) * ih;

  const xMid = median(xs);
  return {
    points: items.map((it) => ({
      id: it.seriesId,
      cx: px(it.nowBp),
      cy: py(it.z),
      item: it,
    })),
    xMid,
    xMidPx: px(xMid),
    zeroPx: py(0),
    zeroInRange: y0 <= 0 && 0 <= y1,
    inner: { w: iw, h: ih },
  };
}

/** 네 구역의 수 — 화면이 「무엇이 몇 개인지」를 한 줄로 말할 때 쓴다.
 *  ★`pureRv` = **좁은데 싸다** = 이 화면이 찾는 것(왼쪽 위). */
export function quadrantCounts(items: readonly CreditDtsItem[]): {
  pureRv: number;
  wideCheap: number;
  tightRich: number;
  carryOnly: number;
} {
  const xMid = median(items.map((it) => it.nowBp));
  let pureRv = 0;
  let wideCheap = 0;
  let tightRich = 0;
  let carryOnly = 0;
  for (const it of items) {
    const wide = it.nowBp >= xMid;
    const cheap = it.z > 0;
    if (!wide && cheap) pureRv += 1;
    else if (wide && cheap) wideCheap += 1;
    else if (!wide && !cheap) tightRich += 1;
    else carryOnly += 1;
  }
  return { pureRv, wideCheap, tightRich, carryOnly };
}
