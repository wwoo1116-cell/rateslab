/* 서버 대사 → 대사 스택이 받는 모양 [v1 OWNER, 2026-08-11].
 *
 * 이 파일은 순수하다 — DOM 도 fetch 도 없다. `book.ts` 와 같은 이유이고, 여기서는
 * 이유가 하나 더 있다: **이 사상이 한 번 조용히 틀렸다.** 창을 합치면서 조달 칸을
 * `r.funding ?? null` 로 채웠더니 스왑만 있는 북에도 열이 서서 250줄이 전부 «—» 인
 * 조달 칸이 생겼다. 컴포넌트는 멀쩡했고 틀린 것은 넘겨주는 쪽이었는데, 그때 이
 * 함수가 창 안에 있어서 가드가 닿지 못했다.
 *
 * 여기서 계산하는 것은 없다. 이름만 바꿔 넘긴다 — 두 번째 정의를 만들지 않는다.
 *
 * [OWNER, 2026-08-25 — 엔진 단위 분리] 서버 대사가 표 둘(`{swap, bond}`)이
 * 됐다. 스왑 표는 IRS 달력, 채권 표는 민평 달력 위에 각자 서고, 병합판이
 * 지불하던 드롭(한쪽만 쉰 날 + 다음 날 제거 → 세로합 ≠ 기간 3분해)은 서버에서
 * 사라졌다. 이 파일은 그 두 표를 각자 스택 모양으로 넘길 뿐이다.
 */

import type { BacktestRecon, BacktestReconPair, BacktestResult } from '@/lib/api';
import type { ReconStackDay } from '@/ui/window/ReconStack';

/** 서버 응답·구 세션 복원본을 한 모양으로. 라이브 서버는 언제나 `{swap, bond}`
 * 를 주고, 2026-08-25 이전 세션의 복원본은 병합 한 표다 — 그 판의 격자는
 * 접두사 열쇠(`S:`/`B:`)와 병합 달력이라 두 표로 되돌릴 수 없어 **버린다**
 * (다시 실행하면 새 모양이 온다). 순수 북의 구 복원본(한 표)은 조달 숫자의
 * 유무로 어느 엔진 것인지 판별해 자기 자리에 세운다. */
export function reconPair(
  recon: BacktestReconPair | BacktestRecon | undefined,
): BacktestReconPair {
  if (!recon) return { swap: null, bond: null, futures: null };
  if ('swap' in recon || 'bond' in recon || 'futures' in recon) {
    const pair = recon as BacktestReconPair;
    return {
      swap: pair.swap ?? null,
      bond: pair.bond ?? null,
      // [2026-08-25] 선물 표 — 이 키가 없는 응답(선물 합류 전)은 null 로.
      futures: pair.futures ?? null,
    };
  }
  const legacy = recon as BacktestRecon;
  if (legacy.tenors?.some((t) => t.includes(':')))
    return { swap: null, bond: null, futures: null };
  const isBond = legacy.rows?.some((r) => typeof r.funding === 'number');
  return isBond
    ? { swap: null, bond: legacy, futures: null }
    : { swap: legacy, bond: null, futures: null };
}

/**
 * 행은 서버 순서(오름차순) 그대로 넘긴다. 보이는 방향은 스택의 날짜 헤더 토글이
 * 정한다.
 *
 * 접는 것이 하나 있다: **개시**(거래일→발효일 한 밤)는 진입일 행에만 서고 총손익
 * 대비 0.005% 라 자기 열을 갖지 않는다 — 평가에 접는다 [OWNER, 2026-08-14].
 * 엔진은 여전히 따로 센다(`backend/app/backtest.py`).
 *
 * **조달은 있을 때만 싣는다.** 스왑에는 조달이라는 개념 자체가 없으므로 그 칸은
 * «0원이었다» 도 «모른다» 도 아니고 **그 질문이 없다** 이다 — `undefined` 가 그
 * 뜻이고, `null` 은 "그날은 모른다" 라는 다른 말이다. `ReconStack` 의 `hasFunding`
 * 이 보는 것이 정확히 이 구분이다.
 */
export function backtestDays(recon: BacktestRecon): ReconStackDay[] {
  return recon.rows.map((r) => ({
    date: r.t,
    title: r.carryover ? `${r.t} · 다음 영업일로 들고 가는 이월 리스크` : r.t,
    krd: r.krd,
    dbp: r.dbp,
    est: r.est,
    estTotal: r.estTotal,
    valuation: r.valuation === null ? null : r.valuation + (r.startup ?? 0),
    /* 잔차 [OWNER, 2026-08-25 — 감사록 F4]: 서버 값 그대로. 개시를 평가에
       접는 것과 무관하다 — 잔차의 정의(평가−추정)는 서버의 평가 기준이고,
       개시는 추정의 대상이 아니라서 서버 잔차가 이미 옳은 수다. */
    residual: r.residual,
    carry: r.carry,
    rolldown: r.rolldown,
    ...(r.funding === undefined ? {} : { funding: r.funding }),
    actual: r.actual,
    /* 다리별 대사 [2026-09-04]. 여기서도 **이름만 바꿔 넘긴다** — 개시를
       평가에 접는 것은 하루의 일이고, 다리 블록에는 개시 항이 없다(자산스왑의
       개시는 국고 다리의 진입일 한 밤이라 서버가 이미 평가에 넣어 보낸다). */
    ...(r.legs === undefined ? {} : { legs: r.legs }),
  }));
}

/** 표의 열 — 다리별 대사면 **두 다리의 합집합**이다. 민평과 IRS 의 라벨 집합이
 * 어긋나므로(2.5Y·20Y·30Y ↔ 1D·4Y·6Y·8Y·9Y) 한쪽 목록만 쓰면 다른 다리의 칸이
 * 통째로 사라진다.
 *
 * **만기순으로 다시 세운다.** 두 목록을 그냥 이어 붙이면 IRS 에만 있는 1D·4Y·6Y
 * 가 민평의 30Y 뒤에 서서, 커브가 왼쪽에서 오른쪽으로 길어진다는 이 표의 유일한
 * 읽는 법이 깨진다. */
const tenorYears = (t: string): number => {
  const n = Number.parseFloat(t);
  if (!Number.isFinite(n)) return Number.POSITIVE_INFINITY;
  if (t.endsWith('D')) return n / 365;
  if (t.endsWith('M')) return n / 12;
  return n;
};

export function reconTenors(recon: BacktestRecon): string[] {
  if (!recon.legTenors?.length) return recon.tenors;
  const all = new Set(recon.legTenors.flatMap((leg) => leg.tenors));
  return [...all].sort((a, b) => tenorYears(a) - tenorYears(b));
}

/** 표 아래 한 줄 — 잘린 창은 **데이터 사실**이라 화면이 말해야 한다.
 * 없으면 `undefined` 를 돌려 각주 자체를 안 세운다. (한쪽 달력에만 있던 날을
 * 뺐다는 옛 문장은 은퇴했다 — 각 표가 자기 달력 위에 서면서 빠지는 날 자체가
 * 없어졌다 [OWNER, 2026-08-25].) */
export function reconNote(recon: BacktestRecon): string | undefined {
  return recon.truncated
    ? '긴 백테스트라 최근 영업일만 실었어요 — 기간 전체 분해는 위에 있어요.'
    : undefined;
}

/** 채권 표의 각주 — 잘린 창 + 캐리 라벨의 뜻 [OWNER, 2026-08-25 — 표기 보강].
 * 캐리 열은 **조달 차감 전**(그로스)이다: 문헌 표준 정의(carry = y − r_f,
 * Ilmanen)와 달리 이 리포는 IRS 세타와 정의를 맞추려 조달을 자기 열로 뺐다
 * [OWNER, 2026-08-14]. 화면만 보는 사람이 그 결정을 알 수 없으면 안 되므로
 * 여기서 말한다. */
export function bondReconNote(recon: BacktestRecon): string {
  const carry = '캐리는 조달 차감 전 금액이에요 — 조달은 자기 열에 음수로 서요.';
  const trunc = reconNote(recon);
  return trunc ? `${trunc} ${carry}` : carry;
}

/** 선물 표의 각주 [2026-08-25]. 캐리·롤다운·조달 열이 안 서는 이유(존재하지
 * 않는 성분)와 잔차의 뜻(선형 추정 대 폐형 실측 = 컨벡시티)을 화면만 보는
 * 사람에게 말한다 — 채권 각주와 같은 근거.
 *
 * **퓨처스왑이 섞이면 문장이 갈린다** [OWNER 2026-09-04]. 그 북의 표는 다리
 * 둘(IRS·선물)이라 캐리·롤다운 열이 **실제로 선다** — IRS 다리에서 온다. 옛
 * 문장을 그대로 두면 화면이 자기 표에 있는 열을 「없다」고 말하게 된다.
 *
 * IRS 다리가 선물 달력 위에 어떻게 서는지도 여기서 말한다: 그 다리는 IRS
 * 달력에서 값매겨지고 선물 행마다 «지난 선물 행 이후» 의 IRS 밤을 담는다.
 * 그래서 IRS 가 쉰 날은 그 다리가 0 이고 다음 행이 두 밤을 한 번에 진다 —
 * 돈은 보존되지만 그 줄만 보면 이상하게 읽히므로 각주가 미리 답한다. */
export function futuresReconNote(recon: BacktestRecon): string {
  const convexity =
    '잔차는 선형 추정(KRD×Δbp) 대비 실제 가격 변화의 차, 곧 컨벡시티예요.';
  /* 다리가 없는 표(FUT 아웃라이트)의 문장. 「전부 평가」가 **표 전체**에 대해
     참이다. */
  const outright = `선물은 손익이 전부 평가예요 — 합성채는 만기가 고정이라 캐리·롤다운이 없어요. ${convexity}`;
  /* 다리가 있는 표(FSW)에서는 그 문장을 **선물 다리로 좁힌다.** 그대로 두면
     바로 다음 문장(「캐리·롤다운은 IRS 다리에서 와요」)과 앞뒤가 어긋나 화면이
     자기 표에 서 있는 열을 「없다」고 말하게 된다 [실측 2026-09-04]. */
  const legs =
    `퓨처스왑은 하루가 일곱 줄이에요 — 선물 다리와 IRS 다리가 각자 KRD·Δbp·손익을 지고 합계가 닫아요. 선물 다리는 손익이 전부 평가예요(합성채는 만기가 고정이라 캐리·롤다운이 없어요) — 캐리·롤다운은 IRS 다리에서 와요. ${convexity} IRS 다리는 자기 달력에서 값매겨져 선물 행마다 «지난 행 이후» 의 밤을 담으니, IRS 가 쉰 날은 0 이고 다음 행이 두 밤을 한 번에 져요.`;
  const body = recon.legTenors?.length ? legs : outright;
  const trunc = reconNote(recon);
  return trunc ? `${trunc} ${body}` : body;
}

/** 혼합 차트 밑 달력 각주 — 차트·헤드라인은 여전히 민평 ∩ IRS 위에서 그린다.
 * 일별 대사가 표 둘로 갈라진 지금, 이 문장은 **차트**의 사실만 말한다. */
export function calendarNote(result: BacktestResult): string | undefined {
  const cal = result.calendar;
  if (!cal) return undefined;
  const parts = [
    cal.dropped
      ? `차트는 ${cal.basis} 달력 위에서 그려요 — 한쪽 달력에만 있던 ${cal.dropped}일은 점이 없어요.`
      : '',
    cal.clippedFrom
      ? `가장 이른 진입(${cal.clippedFrom})은 공통 달력보다 앞이라 선이 중간부터 시작해요 — 총액은 그대로예요.`
      : '',
  ].filter(Boolean);
  return parts.length ? parts.join(' ') : undefined;
}
