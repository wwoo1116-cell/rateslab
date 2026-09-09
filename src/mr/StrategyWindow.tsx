'use client';

/* 전략 실험 창 — 첫 PMS(krw-fi-pms) entry-signals 워크스페이스의 기술적 구성을
 * v2 문법으로 재현한 것 [OWNER 2026-08-25 — "맨처음 만들었던 PMS 에서 볼린저
 * 밴드 활용한 트레이딩 전략 했던 창 참고해서 기술적 구성 구현하기"].
 *
 * ── 원본에서 가져온 것 ──────────────────────────────────────────────────────
 * · 노브 일곱(룩백 프리셋 20/60/120 + 자유값·진입σ·관찰σ·청산σ·손절σ·비용bp·
 *   명목 원/bp)과 그 기본값(s16) — 밴드 배수가 곧 진입σ라는 «노브 하나, 뜻 둘»
 *   까지 그대로. **예외 하나: 비용 기본값은 0.05 가 아니라 0.5 다**
 *   [OWNER 2026-08-28]. 0.05 는 PMS 의 값이지 이 데스크의 실측이 아니고, 싸게
 *   잡은 비용은 결론을 통째로 뒤집는다. 규칙은 재현이고 **비용만 실측**이다.
 * · z-문턱 레벨 규칙(진입 |z|≥entryσ 역행·청산 |z|≤exitσ·손절 |z|≥stopσ 우선·
 *   당일 종가 체결·편도 비용) — 산술은 서버가 끝낸다(§16, mrbacktest.py 가
 *   원본과 적합성 벡터로 잠금).
 * · 패널 넷: 가격+SMA+밴드 / z 오실레이터(가이드 5줄 + 진입 마커) / 에쿼티
 *   커브 / KPI 타일+거래 표. **원본은 2×2 격자였고 이 창은 세로 스택**이다
 *   [OWNER 2026-09-02] — 12년 시계열이 반폭에서 안 읽히고, Backtest 창의
 *   세로 결과 같아진다.
 * · «실행 시점 고정(pinned)» 규율: 노브를 실행 없이 바꾸면 숫자를 조용히
 *   재계산하지 않는다 — stale 문구가 서고 오실레이터 마커가 숨는다.
 * · 실행은 사람이 누른다 — v2 백테스트 창과 원본 staged flow 가 같은 규칙이다.
 *
 * ── v2 로 옮기며 바꾼 것(문법 충돌 자리) ────────────────────────────────────
 * · 차트는 공용 `TimeChart`(lightweight-charts) 다 — 원본의 그 라이브러리가
 *   아니고, 이 리포의 15차트가 전부 그것이다(CLAUDE.md 규칙 7). 리드아웃은
 *   공용 기구(`ReadoutCard`)를 쓴다. ⚠ 종전 주석은 「CDS CartesianChart」라고
 *   적혀 있었다 — 2026-08-26 이관 뒤로 거짓이었고 2026-09-02 감사가 잡았다.
 * · 진입/청산은 **점(markers)과 세로선(markLines)을 같이** 쓴다 — 점이 방향색
 *   으로 «무엇을 샀나»를 말하고 세로선이 «언제»를 말한다. 거래별 정밀값은
 *   거래 표가 진다.
 * · 배치는 **세로 스택**이고 차트 셋이 Backtest LINKED PAIR 의 문법을 쓴다
 *   (같은 dates·`useStackedScales`·x 라벨은 맨 위만·십자선 `syncIndex` 동기).
 *   일별 대사는 창 바닥 **서랍**이 진다(Backtest 의 그 자리).
 * · Jade/Berry 방향색 대신 이 리포의 방향색(--sr-up/--sr-down) — 색은 방향만
 *   나른다는 규칙 그대로.
 *
 * **명구 의무**: 이 창은 재현 도구다. 당일 종가 체결 규약은 원본 그대로이며
 * 체결 가능성을 담보하지 않는다(연구 레인의 «즉시체결판은 상한» 실측 — 창이
 * 그 사실을 말한다). 신호 검증(NO-GO)과 딴 물건임도 aside 가 말한다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@coinbase/cds-web/tables';
import { Tooltip } from '@coinbase/cds-web/overlays';
import { Text } from '@coinbase/cds-web/typography';

import { TimeChart, useStackedScales, type TimeLine, type TimeMarker } from '@/chart/TimeChart';
import type { ScalePriceLine } from '@/chart/ScaleChart';
import type { BacktestRecon, Unit } from '@/lib/api';
import { BacktestUnavailable } from '@/lib/api';
import { fmtBp, fmtLevel, unitSuffix } from '@/lib/format';
import { fmtKrw, fmtKrwFromMan, manUnits } from '@/lib/krw';
import { FloatingWindow } from '@/ui/window/FloatingWindow';
import { ReadoutCard, ReadoutFact, ReadoutLevel, ReadoutMoney, placeReadout } from '@/ui/ReadoutCard';
import { Stat, StatColumn } from '@/ui/Stat';
import { ThHelp } from '@/ui/ThHelp';

import {
  MR_ENTRY_MODES,
  MR_SPAN_LABEL,
  MR_STRATEGY_DEFAULTS,
  fetchMrOptimize,
  fetchMrStrategy,
  rankCells,
  type MrOptimizeCell,
  type MrOptimizeRun,
  type MrPerf,
  type MrRankKey,
  type MrSpan,
  type MrStrategyParams,
  type MrStrategyRun,
  type MrStrategyTrade,
  type MrReconLeg,
  type MrStrategyPoint,
  fetchMrRecon,
  type MrRecon,
} from './api';
import { backtestDays, futuresReconNote, reconNote, reconTenors } from '@/backtest/recon';
import { ReconStack, type ReconStackDay } from '@/ui/window/ReconStack';
import { MrKnobBar, mrKnobsStale } from './KnobBar';
import { OptimizePane } from './OptimizePane';
import { Panel, RiskAdjusted, SplitColumn, WHY_WORD, headFont } from './parts';

/* 얼라인 규칙 [OWNER 2026-08-25 — CLAUDE.md «얼라인» 절]. 첫 판은 라벨을
 * 컨트롤 **옆**에 붙였고, 라벨 폭이 제각각이라 컨트롤 시작점이 계단이 졌다
 * ("아주 얼라인이 개판이야"). 백테스트·시뮬 창의 Field 문법(라벨 위·바닥 정렬·
 * 등고 32px)으로 다시 세운다. */
/* `Field` 는 여기서 정의하지 않는다 — 앱에 하나뿐인 것을 임포트한다
   (`ui/ControlCard`). 이 파일이 갖고 있던 `help`(값의 출처를 라벨이 진다)는
   그 공용 것으로 올라갔다 [OWNER 2026-08-25]. */

/* σ 알약·값 고르개·숫자 칸은 **공용 노브 바**로 옮겼다(`KnobBar.tsx`,
 * 2026-09-01) — 통합 장부 창이 같은 노브를 쓰기 때문이다.
 *
 * **`InlineSigma` 도 2026-09-02 에 내렸다** [OWNER — "이건 뭔지 확인하고
 * 필요없으면 치우기"]. 그 부품이 잡고 있던 값은 `warnZ`(「관찰 σ」) 하나뿐이고,
 * 그 값은 z 오실레이터에 점선 두 줄을 긋는 것 말고 아무 일도 안 했다 — 이름은
 * 「경보 문턱」인데 **경보하는 곳이 화면에 없었다**(그 값을 읽는 마커·집계·
 * 상태 문장이 하나도 없었다). 통합 장부 창에는 애초에 없었으니 두 창이 갈려
 * 있기도 했다(캐논 얼라인 8). 그림에는 이미 0선과 진입 문턱 ±entryZ 가
 * 굵게 서 있어서, 세 번째 점선 쌍은 잉크만 늘리고 결정은 안 붙어 있었다.
 *
 * 노브 하나를 내리는 값은 화면 밖에도 있었다: `warnZ` 는 쿼리·백엔드 검증·
 * 응답 `params` 세 층에 실려 다니면서 **결과를 한 번도 안 바꿨다**. */

/* ── 진단 절과 이웃 칸은 **화면에서 내렸다** [OWNER 2026-09-02 — 몸통에서
 * 내릴 절을 고른 그 선택] ────────────────────────────────────────────────────
 *
 * 내린 둘과 그 이유:
 *
 *   **진단**(135px) — 「신호가 한 일 · 승률의 출처 · 구간별」 세 칸. 2026-08-28
 *   오너 질문 둘(「저렇게 단순한 전략이 승률이 이렇게 높을 수 있나」·「과거에
 *   Overfitting 된 것 아닌가」)에 답하려고 세운 절이고, **그 답은 이미 나왔다** —
 *   승률은 청산 구조의 산물이 아니라 신호의 공로이고(신호일 10일 앞 +1.84bp·
 *   적중 72% 대 비신호일 −0.08bp·49%), 과거적합의 증거는 못 찾았으며 대신 국면
 *   의존이 보였다(−0.08 → 1.21 → 0.62). 근거와 수치는 `docs/MR_LANE_STATE.md`
 *   §승률·과거적합 의심에 대한 답 에 있다. 답이 끝난 질문을 매번 화면에 세울
 *   이유는 없다.
 *
 *   **이웃 칸**(260px) — 노브 넷 × 각 3칸 격자. 이 창에서 제일 큰 비차트
 *   블록이었고, 자기 주석이 「견고성 보기이지 **고르는 도구가 아니다**」라고
 *   적어 두고 있었다. 레인 실측도 같은 방향이다 — 전진분석은 파라미터 선택에
 *   값을 못 더했다(§Ⅱ). 한 칸 옆이 궁금하면 노브를 직접 옮기고 실행한다.
 *
 * **서버는 그대로다** — `/api/mr/strategy` 는 `diag` 와 `neighbors` 를 계속
 * 내고 계약(`MrStrategyRun`)에도 남아 있다. 되살리려면 이 자리에 컴포넌트를
 * 다시 세우면 된다(git 이력: 이 주석을 넣은 커밋 하나). 화면에서 내린 것이지
 * 측정을 끈 것이 아니다 — 실전 규칙 다섯을 내릴 때와 같은 규율이다. */
/* 차트 높이 두 급 — Backtest 의 LINKED PAIR 치수 그대로다(`LinkedCharts.tsx`:
   위 종목 200 · 아래 누적손익 140). 주선이 사는 차트가 크고 파생(z·누적)이
   작다 — 세로로 쌓았을 때 «무엇이 주인공인가»를 높이가 말한다. */
const CHART_H = 200;
const CHART_H_SUB = 140;
/* 거래 표 상자 — 차트 둘을 합친 높이. 표는 스크롤이라 높이가 곧 «한 번에 몇
   줄 보이나»이고, 풀폭이 된 뒤에도 200 이면 38거래에서 세 줄만 보인다. */
const TABLE_H = CHART_H + CHART_H_SUB;

/* ── 구간은 **전역 설정값**이 됐다 [OWNER 2026-09-04 — "지난 1년, 지난 1분기,
 * 지난 1개월을 전역 설정값으로 두고 이를 조정하면 성과도 바뀌게 해주기"] ─────
 *
 * 2026-09-02 판에서 이 손잡이는 «표시» 였다: 차트와 거래 표만 자르고 성과
 * 카드는 전체 기간이었다. 이제는 성과도 바뀐다 — 그래서 셋이 옮겨 갔다.
 *
 *   목록(`MR_SPANS`·`MR_SPAN_TABS`)  → `api.ts` (서버 `mrmetrics.SPANS` 의 거울)
 *   고르개                            → `KnobBar` (노브 줄 **위**의 제 줄)
 *   달력 산술(`monthsBefore`)         → **서버**. 화면은 `spans[].from` 을 읽는다
 *
 * 마지막 하나가 이 파일에서 없어진 함수다. 카드가 서버 채점이고 차트가 화면
 * 산술이면 둘이 하루씩 갈릴 수 있고(말일 넘침·휴장), 그때 「구간 순손익」과
 * 「구간 총손익」이 다른 수가 된다 — 같은 것을 두 번 계산하지 않는다.
 *
 * 누적 손익 곡선은 그대로 구간 시작을 0 으로 다시 긋는다(구간 순 = 구간 끝
 * 누적 − 구간 직전 누적). */

/** 액면을 데스크 말로 — «35.7억». `fmtKrw` 는 부호를 앞세우는 **손익** 표기라
 *  Delta 나 액면에 쓰면 「+35억 7,000만원」이 된다 — 둘 다 방향이 없는 양이다. */
const fmtEok = (krw: number): string => `${(krw / 1e8).toFixed(1)}억`;

/** 대사 열의 레벨 — bp 계열은 **2자리**다(캐논 `fmtLevel` 의 1자리에서 일부러
 *  이탈). 이 표들은 「청산 레벨 − 진입 레벨 = Δ」를 주장하는데 Δ 가 2자리
 *  (`fmtBp(v, 2)`)라, 레벨을 1자리로 적으면 실측 3.50→1.75 가 «3.5→1.8 인데
 *  Δ −1.75» 로 서서 표시 정밀도에서 항등이 깨진다 — 각자 반올림한 항이 표시된
 *  합과 모순되는 그 사고다(`lib/krw.ts` 머리의 1만원 판례). %·가격 계열은
 *  `fmtLevel` 그대로 — Δ 는 늘 bp 라 어차피 단위가 달라 눈으로 못 닫고, 그
 *  사실은 거래 표 머리 주석이 진다. */
const fmtReconLevel = (v: number | null, unit: Unit): string =>
  v == null ? '—' : unit === 'bp' ? v.toFixed(2) : fmtLevel(v, unit);

/* ── 사건 어휘 ──────────────────────────────────────────────────────────────
 * 거래 하나를 가리키는 열쇠는 «진입-청산» 이다 — 실행이 바뀌면 자연히 안 맞고,
 * 그때 화면은 목록으로 돌아간다(펴 놓은 대사가 딴 실행의 숫자를 이고 있는
 * 것보다 낫다). 문자열을 두 곳에서 짓지 않으려고 함수로 둔다. */
export const tradeKey = (t: { entryT: string; exitT: string }): string =>
  `${t.entryT}-${t.exitT}`;

type MrEvent = {
  kind: 'entry' | 'exit' | 'stop';
  /** 나간 사유 원본 — 진입 사건에서는 없다. */
  why?: MrStrategyTrade['why'];
  /** 엔진 부호. 미청산 다리는 0 으로 두어 방향색을 안 갖는다. */
  dir: number;
  /** 거래 순번(1부터) — 세로선의 라벨이 이걸 적는다. */
  n: number;
  key: string;
};

/** 미청산 다리를 **거래 줄 모양으로** [OWNER 2026-09-09 — "미청산도 PnL에
 *  포함하기"].
 *
 *  ## 무엇이 빠져 있었나
 *
 *  총손익·낙폭은 종전에도 이 다리를 지고 있었다(누적이 보유 봉마다 MTM 을
 *  더한다 — `mrbacktest` 의 그 주석). 빠져 있던 것은 **거래 표**였다: 표의
 *  세로합이 누적과 갈리고, 열려 있는 손익은 KPI 타일 한 칸에만 있었다. 그래서
 *  이 줄을 표의 마지막에 세운다 — 사유 칸이 「미청산」이고, 「청산」 쪽 값은
 *  청산이 아니라 **마지막 봉의 평가**다.
 *
 *  ## 무엇을 안 바꾸나
 *
 *  **승률·거래 수는 안 건드린다.** 그 둘을 바꾸는 것은 `countOpen` 노브의 일이고
 *  (엔진이 의사거래를 목록에 넣는다), 그 노브는 긴 표본에서 기각됐다
 *  (`docs/MR_LANE_STATE.md` §긴 표본 판정). 그래서 화면은 표의 줄만 늘리고 KPI
 *  타일의 「거래」는 그대로 둔다 — 각주가 그 사실을 적는다.
 *
 *  노브가 켜져 있으면 **이미 목록에 있으므로** null 이다(두 번 세지 않는다).
 *  구 백엔드는 「청산」 쪽 셋과 성분을 모르므로 그때도 null 이다 — 없는 값을
 *  0 으로 그리지 않는다(이 리포의 공란 정책). */
function openAsTrade(run: MrStrategyRun): MrStrategyTrade | null {
  const o = run.open;
  if (!o || run.params.countOpen) return null;
  if (o.exitT == null || o.exitV == null || o.dv == null) return null;
  if (o.mtm == null || o.carry == null || o.cost == null) return null;
  return {
    entryT: o.entryT, exitT: o.exitT, dir: o.dir,
    entryZ: o.entryZ, exitZ: o.exitZ ?? null,
    entryV: o.entryV, exitV: o.exitV,
    pnl: o.pnl, why: 'open',
    mtm: o.mtm, carry: o.carry,
    ...(o.rolldown != null ? { rolldown: o.rolldown } : {}),
    ...(o.funding != null ? { funding: o.funding } : {}),
    cost: o.cost,
    bars: o.bars,
    outFrom: o.outFrom, outDays: o.outDays, peakZ: o.peakZ,
    dv: o.dv, dvNet: o.dvNet, masked: o.masked,
  };
}


/** 그날 사건의 한 마디 — 판독과 대사표의 「구분」 칸이 같은 말을 쓴다. */
/** 롤 표식 — 「이 줄의 Δ 는 수준의 차가 아니다」 [OWNER 2026-09-02].
 *
 *  선물·퓨처스왑의 값은 벤더 내재수익률이라 **수준**은 옳지만, 계약이 갈리는
 *  날의 차분은 앞 계약 마지막과 뒷 계약 첫 값을 뺀 것이라 아무도 실현하지
 *  못한다. 그 봉의 Δ 를 0 으로 두면 대사표의 곱셈은 닫히지만 **「청산 − 진입」과
 *  Δ 가 갈린다** — 표식이 없으면 읽는 사람이 그것을 표의 결함으로 읽는다.
 *
 *  글자가 아니라 위첨자 하나다: 숫자 열의 자릿수를 안 밀고, 뜻은 툴팁이 진다.
 *  말줄임이 아니다(잘린 글자가 아니라 덧붙인 표식). */
function RollMark({ n }: { n: number }) {
  return (
    <Tooltip
      content={
        <Text font="legal" as="span">
          {`보유 중 선물 계약이 ${n}번 갈렸어요. 그날의 수준 변화는 거래할 수 없어서 Δ 에 안 실려요 — 그래서 청산 − 진입 과 Δ 가 달라요.`}
        </Text>
      }
      maxWidth={280}
      placement="bottom"
    >
      <Text font="legal" as="span" color="fgMuted" className="sr-mr-rollmark" tabIndex={0}>
        {' R'}
      </Text>
    </Tooltip>
  );
}

function eventWord(e: MrEvent | undefined, holding: boolean): string {
  if (!e) return holding ? '보유' : '—';
  return e.kind === 'entry' ? '진입' : (e.why ? WHY_WORD[e.why] : '청산');
}

/** 진입 사건의 수 — 거래 + (아직 목록에 없는) 미청산 다리.
 *
 * `countOpen` 이 켜져 있으면 미청산이 **이미 거래로 들어와 있으므로** 또 세면
 * 안 된다. 종전에는 무조건 더해서 「진입 15 · 거래 14」가 화면에 같이 서 있었다
 * (실측 2026-08-28). */
function entryCount(run: MrStrategyRun): number {
  return run.trades.length + (run.open && !run.params.countOpen ? 1 : 0);
}

/** 나간 사유의 집계 한 마디 — **0 인 사유는 안 적는다**.
 *
 * 종전에는 청산과 손절만 셌다. 나가는 문이 넷으로 늘어난 뒤에도 그대로 두었더니
 * 「청산 10 · 손절 0」이 서 있는데 거래는 14였다 — 타임스탑 2·역신호 1·미청산 1이
 * 화면에서 사라져 있었다. 사유를 하나라도 빠뜨리면 그 줄은 거짓이 된다. */
function exitTally(run: MrStrategyRun): string {
  const order: MrStrategyTrade['why'][] = ['exit', 'stop', 'time', 'reverse', 'open'];
  const n = (w: MrStrategyTrade['why']) => run.trades.filter((t) => t.why === w).length;
  const parts = order.filter((w) => n(w) > 0).map((w) => `${WHY_WORD[w]} ${n(w)}`);
  return parts.length ? parts.join(' · ') : '거래 없음';
}

/** 진입 규칙의 이름 — 목록이 어휘의 주인이라 여기서 다시 짓지 않는다. */
const entryWord = (mode: string): string =>
  MR_ENTRY_MODES.find((m) => m.v === mode)?.label ?? mode;

/** 그 봉의 포지션 한 마디 — 「보유 6봉째 · 거래 3」 또는 「무포지션」.
 *
 * `hold`(그 봉을 통과해서 들고 있던 것)로 판정한다. 청산 봉은 `pos` 가 이미 0
 * 이지만 그날 하루는 들고 있었으므로 무포지션이라고 말하면 거짓이다. */
function posWord(run: MrStrategyRun, i: number): string {
  const p = run.points[i];
  if (!p) return '—';
  const t = run.trades.find((q) => q.entryT <= p.t && p.t <= q.exitT);
  const open = !t && run.open && p.t >= run.open.entryT ? run.open : null;
  const from = t?.entryT ?? open?.entryT;
  if (from == null) return p.hold === 0 && p.pos === 0 ? '무포지션' : '보유';
  const e = run.points.findIndex((q) => q.t === from);
  const day = e < 0 ? null : i - e;
  const who = t ? `거래 ${run.trades.indexOf(t) + 1}` : '미청산';
  return day === 0 ? `진입일 · ${who}` : `보유 ${day}봉째 · ${who}`;
}

/** 대사표의 숫자 열 — 머리와 몸통이 **같은 목록**을 읽는다. 두 벌이면 열이
 * 어긋나고, 어긋난 대사표는 대사표가 아니다.
 *
 * ## 다리가 «열» 이 아니라 «행» 이다 [OWNER 2026-09-03]
 *
 * 종전에는 하루가 한 줄이고 다리 레벨 셋이 열이었다. 그런데 이건 **스프레드
 * 플레이**라 하루에 다리가 둘이고, 다리마다 감도·Δ·손익이 따로 있다 — 한 줄에
 * 다 못 담는다. 그래서 백테스트·시뮬 대사표의 문법을 그대로 가져온다:
 * 하루가 **다리마다 세 줄**(KRD·Δbp·손익)이고 마지막에 종합 한 줄이다.
 *
 * 「값」 칸은 줄마다 단위가 다르다(₩/bp · bp · ₩) — 무엇인지는 「구분」이 말한다.
 * ReconStack 의 테너 칸이 KRD·Δbp·손익을 차례로 담는 것과 같은 자리다. */
export const RECON_COLS = ['값', '평가', '캐리', '비용', '그날', '누적'] as const;

/** 레벨·z·CD 는 **대사표에서 나갔다** [OWNER 2026-09-03 — "레벨이랑 Z값은
 *  일별대사 말고 일별레벨 칸을 하나 파서 다른 칸에서 보여주게 하고"]. 대사는
 *  「얼마나 벌었나」의 표고, 레벨은 「어디에 있었나」의 표다 — 위계가 같으므로
 *  서랍의 **형제 탭**으로 선다.
 *
 *  그 칸의 열은 **상수가 아니라 다리에서 뽑는다**(`levelCols`) — 다리 이름이
 *  계열마다 다르기 때문이다(BSS 국고·IRS · 퓨처스왑 선물·IRS · 선물 하나).
 *  2026-09-03 감사에서 여기 `LEVEL_COLS` 상수가 있었는데, 화면은 안 읽고
 *  가드만 읽는 **죽은 상수**였고 `국고·IRS` 로 못 박혀 있어 선물 계열에서는
 *  틀린 값이었다 — 「관찰 σ」와 같은 병이라 지웠다. */

/** 합계 줄의 다리 레벨 — 더할 수 있는 양이 아니라 **진입 → 청산**이다(레벨·z
 *  의 그 규칙). 한쪽이라도 없으면 지어내지 않고 '—' 다. */
function LegArrow({ a, b }: { a?: number | null; b?: number | null }) {
  const t = a == null || b == null
    ? '—'
    : `${fmtReconLevel(a, '%' as Unit)}→${fmtReconLevel(b, '%' as Unit)}`;
  return (
    <TableCell className="sr-num" justifyContent="flex-end">
      <Text font="label1" as="span" tabularNumbers noWrap color={t === '—' ? 'fgMuted' : undefined}>
        {t}
      </Text>
    </TableCell>
  );
}

/** 대사표의 숫자 한 칸.
 *
 * `tone` 은 **손익 두 열에만** 준다 — 방향색은 「번 돈인가 잃은 돈인가」를
 * 나르는 채널이라, 감도·Δ 처럼 부호가 방향을 뜻하는 열에 같은 색을 쓰면 색이
 * 두 가지 뜻을 갖게 된다(`theme/tint.ts` 의 「한 셀 한 채널」).
 * 0 은 `—` 로 적는다: 「그날 그 항이 없었다」와 「0원이었다」는 같은 말이고,
 * 그 자리에 0 을 찍으면 눈이 자릿수를 세게 된다. */
function ReconNum({
  v,
  kind,
  tone,
  head,
  unit,
}: {
  v: number | null;
  kind: 'sigma' | 'bp' | 'won' | 'level';
  tone?: boolean;
  /** 합계 줄 — 굵기가 한 단계 올라간다. */
  head?: boolean;
  /** `level` 에만 — 계열의 자기 단위로 적는다(`fmtLevel`). 0 은 '—' 가 아니라
   *  0 이다: 스프레드가 0 인 날은 「없던 날」이 아니라 그 값이었던 날이다. */
  unit?: Unit;
}) {
  const text =
    v == null ? '—'
    : kind === 'sigma' ? `${v.toFixed(2)}σ`
    : kind === 'bp' ? fmtBp(v, 2)
    : kind === 'level' ? fmtReconLevel(v, unit ?? ('bp' as Unit))
    : v === 0 ? '—'
    : fmtKrw(v);
  return (
    <TableCell className="sr-num" justifyContent="flex-end">
      <Text
        font={head ? 'label1' : 'label2'}
        as="span"
        tabularNumbers
        noWrap
        color={text === '—' ? 'fgMuted' : undefined}
        className={tone && v ? (v > 0 ? 'sr-up' : 'sr-down') : undefined}
      >
        {text}
      </Text>
    </TableCell>
  );
}

/** 실가격 대사의 **거래 총손익** — 행의 「그날」을 세로로 더한다.
 *
 * 이월 앵커 행은 `actual` 이 `null` 이라 자연히 빠진다(그 행은 «내일 아침에
 * 들고 갈 리스크»이지 오늘의 돈이 아니다 — `ReconStack` 머리의 그 규약).
 * 이 값이 백테스트 성과표의 거래 손익과 다른 이유는 `realPane` 머리에. */
function reconTotal(r: Extract<MrRecon, { available: true }>): number {
  return reconBlocks(r).reduce(
    (a, b) => a + b.rows.reduce((n: number, x) => n + (x.actual ?? 0), 0),
    0,
  );
}

/** 이 대사가 **몇 표인가.**
 *
 * **어느 계열이든 하나다** [OWNER 2026-09-07]. BSS 는 자산스왑 한 표(다리 둘이
 * 그 안에 선다). 선물 계열은 블록으로 오는데 FUT 은 선물 달력 하나, FSW 도
 * 하나다 — IRS 다리가 그 표 **안에** 서서 하루가 일곱 줄이 된다(백테스트 창이
 * 간 그 길, `futures.book_recon` 의 «버킷»). 종전에는 FSW 가 둘이었고, 그래서
 * 화면 둘이 같은 상품을 다른 모양으로 그렸다.
 *
 * 그래도 목록으로 두는 이유는 **세로합·검산이 한 곳에서 돌아야** 하기 때문이고
 * (블록이 다시 늘어도 여기만 산다), 응답이 여전히 `blocks` 로 오기 때문이다. */
function reconBlocks(
  r: Extract<MrRecon, { available: true }>,
): ({ name?: string } & BacktestRecon)[] {
  return 'blocks' in r ? r.blocks : [r];
}

/** 대사 줄의 문장 — **표가 곧 엔진의 장부다** [OWNER 2026-09-03 — "캐리
 * 롤다운 다 넣고 우리가 원래 사용하던 백테스트/시뮬레이션에서의 대사와 동일하게
 * 작성하기"].
 *
 * 종전에는 둘이 **다른 회계**였다. 엔진은 `평가 = 명목 × Δ스프레드` 하나였고
 * 롤다운도 조달도 없었다 — 실측에서 안 세는 롤다운(789만원)이 세는 전부
 * (688만원)보다 컸다. 그래서 두 수를 나란히 놓고 차이를 설명하는 줄이 필요했다.
 *
 * 이제 아니다. 진입·청산 시점은 엔진이 정하고 **그 구간의 돈은 이 표가 센다** —
 * 같은 `cashbond` 대사가 백테스트·시뮬과 같은 네 성분(평가·캐리·롤다운·조달)을
 * 내고, 거기에 전략의 비용이 붙는다. 그래서 이 줄은 «차이의 변명» 이 아니라
 * **검산**이다: 표의 세로합에 비용을 더하면 거래 손익이 나온다(실측 차 0.00원).
 *
 * 비용이 표에 없는 이유는 그것이 **상품의 성질이 아니라 전략의 노브**이기
 * 때문이다 — 백테스트·시뮬 대사표에도 그 열이 없다. */
function bridgeText(t: MrStrategyTrade, r: Extract<MrRecon, { available: true }>): string {
  const uTot = manUnits(reconTotal(r));
  const uCost = manUnits(t.cost);
  /* «표들이» 대 «표가» — **세는 것이지 계열로 가르는 것이 아니다**. 종전에는
     `'blocks' in r` 로 갈랐는데, 선물이 한 표가 된 지금(2026-09-07) 그 식은 표
     하나를 두고 「표들이」라고 말한다. 블록이 다시 늘면 문장도 같이 는다. */
  const head =
    `표 세로합 ${fmtKrwFromMan(uTot)} · 비용 ${fmtKrwFromMan(uCost)}`
    + ` → 거래 손익 ${fmtKrwFromMan(uTot + uCost)}`
    + ` — ${reconBlocks(r).length > 1 ? '이 표들이' : '이 표가'} 곧 이 거래의 장부예요`;
  if (!('blocks' in r)) {
    return (
      `${head}(평가·캐리·롤다운·조달).`
      + ` 액면 ${fmtEok(r.principal.krw)} 자산스왑으로 실제로 가격했고,`
      + ` 비용은 상품이 아니라 전략의 노브라 표 밖에 있어요.`
    );
  }
  /* 선물은 성분이 다르다. 선물 다리는 **평가뿐**이고(현금결제·연결 계열이라
     캐리·롤다운·조달이 존재하지 않는 성분이에요), FSW 의 IRS 다리만 캐리·
     롤다운을 진다. 그리고 비용에 **롤**이 들어 있다 — 분기마다 실제로
     갈아타므로 그 왕복을 물어야 해요 [OWNER 2026-09-04 «0.5틱»]. */
  /* `won` 은 **크기**로 오므로 부호를 여기서 준다 — `fmtKrw` 가 «+» 를 붙여
     「회당 +32만원」이 되면 문 돈이 번 돈처럼 읽힌다(실측 2026-09-04 스크린샷). */
  const roll = r.roll.days > 0
    ? ` 비용에는 갈아타기 ${r.roll.days}회(회당 ${fmtKrw(-r.roll.won)})가 들어 있어요.`
    : ' 이 구간에는 갈아타는 날이 없었어요.';
  /* IRS 다리가 있는지는 **다리 목록**이 말한다 — 블록 수가 아니다. 2026-09-07
     에 FSW 가 한 표로 합쳐지면서 `blocks.length > 1` 은 늘 거짓이 됐고, 그대로
     뒀으면 화면이 자기 표에 서 있는 캐리·롤다운 열을 「없다」고 말했다
     (`futuresReconNote` 가 2026-09-04 에 밟은 바로 그 함정). */
  const hasIrsLeg = r.blocks.some((b) => (b.legTenors?.length ?? 0) > 1);
  return (
    `${head}.`
    + ` 액면 ${fmtEok(r.principal.krw)} 로 실제로 가격했어요 —`
    + ` 선물 다리는 평가뿐이고(현금결제·연결 계열이라 캐리·롤다운·조달이`
    + ` 존재하지 않는 성분이에요)${hasIrsLeg ? ', IRS 다리가 캐리·롤다운을 져요' : ''}.`
    + roll
  );
}

/** 갈아타는 날의 행에 **왜 그렇게 생겼는지**를 붙인다 [2026-09-04].
 *
 * 롤일에는 계약이 바뀌므로 벤더 내재금리의 Δ 가 통째로 튄다(실측 KTB3 중앙
 * 5.70bp·최대 27.2bp). 그러면 `추정 = −KRD × Δbp` 가 유령이 되고 **잔차가 그것을
 * 다 진다** — 실측 2026-09-04, FSW-3Y 03-16 행: 추정 +14,938,197 · 평가 −2,545,502
 * · 잔차 −17,483,699.
 *
 * 그 수는 사실이라 안 지운다(`futures.book_recon` 의 그 결정). 대신 **표가 이유를
 * 말한다** — 안 적으면 읽는 사람은 대사가 깨졌다고 읽는다. 돈 쪽은 멀쩡하다:
 * 평가는 조정가 차분에서 나오고 조정가는 롤갭이 이미 빠진 계열이다.
 *
 * IRS 다리는 상수만기라 롤이 없다 — 그 표에는 안 붙인다. */
function rollMarked(
  days: ReconStackDay[],
  name: string | undefined,
  r: Extract<MrRecon, { available: true }>,
): ReconStackDay[] {
  if (name !== '선물' || !('roll' in r) || !r.roll.dates.length) return days;
  const on = new Set(r.roll.dates);
  return days.map((d) =>
    on.has(d.date)
      ? {
          ...d,
          title: `${d.title ?? d.date} · 계약이 갈리는 날 — Δbp 가 계약 교체라 튀고,`
            + ' 추정이 그 위에 서요. 그날의 돈(평가)은 조정가에서 나와요.',
        }
      : d,
  );
}

/** 그 표 밑에 서는 한 줄 — 위 `rollMarked` 와 같은 사실을 글로. */
function rollNote(
  name: string | undefined,
  r: Extract<MrRecon, { available: true }>,
): string {
  if (name !== '선물' || !('roll' in r) || !r.roll.dates.length) return '';
  const ds = r.roll.dates.map((d) => d.slice(5)).join('·');
  return (
    ` 계약이 갈리는 날(${ds})은 Δbp 가 교체라 튀어요 — 그 줄의 추정과 잔차는`
    + ' 그 위에 선 값이고, 그날의 돈은 조정가에서 나오니 평가는 멀쩡해요.'
    + ' 갈아타기 비용은 표 밖 비용 칸에 들어 있어요.'
  );
}

/** 대사표의 **하루** — 다리마다 세 줄(KRD·Δbp·손익)에 종합 한 줄
 * [OWNER 2026-09-03 — "채권 KRD, bp, 손익과 IRS KRD, bp, 손익, 그리고 종합
 * 손익이 하루에 찍혀야 함"].
 *
 * ## 왜 이 모양인가
 *
 * 아웃라이트는 물건이 하나라 KRD·Δbp·손익 세 줄로 닫힌다(백테스트 대사표).
 * 스프레드는 **다리가 둘**이라 그 세 줄이 다리마다 있어야 「어느 다리가
 * 벌었나」를 말할 수 있다. 다리가 하나인 계열(선물 아웃라이트)은 종합 줄이
 * 없다 — 그때 표는 백테스트와 글자 그대로 같은 모양이고, 오른쪽 요약이 손익
 * 줄에 붙는다 [OWNER 2026-09-03 — "한개면 그냥 백테스트와 동일한 형태로"].
 *
 * ## 항등이 세로로 닫힌다
 *
 * 서버가 봉마다 재고 안 맞으면 아예 안 보낸다(`main._attach_leg_recon`).
 * 화면에서 눈으로 보이는 것은 둘이다 — **다리 KRD 의 합이 0**(DV01 중립)이고,
 * **다리 손익의 합이 종합의 평가**다. 캐리도 같은 자리에서 합이 닫힌다.
 *
 *
 * ## ⚠ 부호가 종전 「감도」 칸과 **반대**다
 *
 * 종전 이 표는 `감도 = hold × 명목` 을 싣고 `평가 = 감도 × Δ` 로 읽혔다. 그래서
 * 국고 매수(BSS 는 `hold = −1`)의 감도가 **음수**로 찍혔다. 백테스트·시뮬
 * 대사표는 반대 규약이다 — `손익 = −KRD × Δbp` 이고 **음수 KRD 가 「금리
 * 오르면 버는 쪽」**(페이·숏)을 뜻한다. 오너가 붙여 준 실물 표로 대조했다
 * (2026-09-03): `KRD −509,059 · Δbp 0.75 · 손익 +381,795`.
 *
 * 이 표를 백테스트 문법으로 옮기는 이상 부호도 그쪽을 따른다 — 한 데스크가 두
 * 화면에서 KRD 를 다르게 읽으면 그게 사고다. 그래서 국고 매수의 KRD 는 이제
 * **양수**다. 눈에 익은 수가 뒤집히는 변경이라 여기 적어 둔다.
 * ## 롤일
 *
 * 롤일은 봉 전체의 Δ 가 마스크되므로 **다리도 같이 0** 이다 — 한쪽만 살리면
 * 「감도 × Δ = 손익」이 그 줄에서 안 닫힌다. 왜 0 인지는 표식이 말한다.
 *
 * 날짜는 블록의 **첫 줄에만** 적는다. `rowSpan` 을 쓰지 않는 이유는 CDS
 * `Table` 이 그 개념을 안 내놓기 때문이고(`ui/window/ReconStack` 머리의 그
 * 조항), 빈 칸으로 두면 같은 읽기가 된다 — 백테스트 대사표가 이미 그렇다. */
export function ReconDay({
  p, word,
}: {
  p: MrStrategyPoint;
  word: string;
}) {
  /* 서버가 다리를 안 보냈으면(구 백엔드·분해가 안 닫힌 봉) 종합 한 줄만 선다 —
     없는 분해를 화면이 지어내지 않는다. */
  const legs = p.legs ?? [];
  const single = legs.length === 1;
  const rows: React.ReactNode[] = [];

  legs.forEach((g: MrReconLeg, j: number) => {
    const first = j === 0;
    /* 다리의 마지막 줄(손익)에 요약이 붙는 것은 **다리가 하나일 때뿐**이다.
       그때는 종합 줄이 없으므로 **그날의 사건도 여기 붙는다** — 안 그러면
       선물 두 계열의 대사표에서 「언제 들어가고 나왔나」가 통째로 사라진다
       (2026-09-03 감사가 잡았다: `word` 가 `!single` 블록에만 있었다). */
    const tail = single;
    rows.push(
      <TableRow key={`${p.t}-${g.k}-krd`} {...(first ? { 'data-sr-daytop': '1' } : {})}>
        <TableCell>
          {first ? <Text font="label2" as="span" tabularNumbers noWrap>{p.t}</Text> : ''}
        </TableCell>
        <TableCell>
          <Text font="label2" as="span" color="fgMuted" noWrap>{`${g.k} KRD`}</Text>
        </TableCell>
        <ReconNum v={g.krd} kind="won" />
        <ReconNum v={null} kind="won" />
        <ReconNum v={null} kind="won" />
        <ReconNum v={null} kind="won" />
        <ReconNum v={null} kind="won" />
        <ReconNum v={null} kind="won" />
      </TableRow>,
    );
    rows.push(
      <TableRow key={`${p.t}-${g.k}-dv`}>
        <TableCell>{''}</TableCell>
        <TableCell>
          <Text font="label2" as="span" color="fgMuted" noWrap>{`${g.k} Δbp`}</Text>
        </TableCell>
        {p.roll ? (
          <TableCell className="sr-num" justifyContent="flex-end">
            <Text font="label2" as="span" tabularNumbers noWrap color="fgMuted">
              {fmtBp(0, 2)}
              <RollMark n={1} />
            </Text>
          </TableCell>
        ) : (
          <ReconNum v={g.dv} kind="bp" />
        )}
        <ReconNum v={null} kind="won" />
        <ReconNum v={null} kind="won" />
        <ReconNum v={null} kind="won" />
        <ReconNum v={null} kind="won" />
        <ReconNum v={null} kind="won" />
      </TableRow>,
    );
    rows.push(
      <TableRow key={`${p.t}-${g.k}-pnl`}>
        <TableCell>{''}</TableCell>
        <TableCell>
          <Text font="label2" as="span" color="fgMuted" noWrap>
            {tail ? `${g.k} 손익 · ${word}` : `${g.k} 손익`}
          </Text>
        </TableCell>
        <ReconNum v={g.mtm} kind="won" tone />
        <ReconNum v={tail ? p.mtm : null} kind="won" />
        <ReconNum v={g.carry} kind="won" />
        <ReconNum v={tail ? p.cost : null} kind="won" />
        <ReconNum v={tail ? p.pnl : null} kind="won" tone />
        <ReconNum v={tail ? p.tradePnl : null} kind="won" tone />
      </TableRow>,
    );
  });

  if (!single) {
    rows.push(
      <TableRow key={`${p.t}-sum`} {...(legs.length === 0 ? { 'data-sr-daytop': '1' } : {})}>
        <TableCell>
          {legs.length === 0 ? <Text font="label2" as="span" tabularNumbers noWrap>{p.t}</Text> : ''}
        </TableCell>
        <TableCell>
          <Text font="label2" as="span" color="fgMuted" noWrap>
            {legs.length === 0 ? word : `종합 · ${word}`}
          </Text>
        </TableCell>
        {/* 「값」 칸은 **다리 줄의 것**이다(₩/bp · bp · ₩ 셋을 구분이 말한다).
            종합 줄에는 대응하는 지표가 없어 비운다.

            구 백엔드(다리 없음)에서는 종전에 여기 `hold × 명목`(옛 「감도」)을
            세웠는데, 2026-09-03 감사에서 뺐다. 이유 둘: 다리 줄이 없으니 그 수가
            **무엇인지 말해 줄 이름표가 없고**, 부호가 새 KRD 규약과 **반대**라
            (위 「부호」 문단) 한 표 안에서 두 규약이 서게 된다. 남는 열들은 전부
            제 이름을 달고 있으므로 읽기는 여전히 선다. */}
        <ReconNum v={null} kind="won" />
        <ReconNum v={p.mtm} kind="won" />
        <ReconNum v={p.carry} kind="won" />
        <ReconNum v={p.cost} kind="won" />
        <ReconNum v={p.pnl} kind="won" tone />
        <ReconNum v={p.tradePnl} kind="won" tone />
      </TableRow>,
    );
  }
  return <>{rows}</>;
}

/** 대사표 머리의 한 줄 — 「무엇을 보고 들어가 어떻게 나왔나」.
 *
 * 이탈 구간을 여기서 말하는 이유: 「밴드 복귀」 판에서는 진입 z 가 밴드 선
 * 언저리라, 그 수만 보면 4σ 까지 갔다 온 거래와 살짝 넘었다 온 거래가 같은
 * 줄이다. 무엇을 보고 들어갔는지는 진입 z 가 아니라 **그 구간**이 진다. */
function reconSub(t: MrStrategyTrade, run: MrStrategyRun): string {
  const legs = (t.dir > 0 ? run.dirs.plus : run.dirs.minus).legs;
  const out =
    t.outFrom == null || t.outDays == null
      ? ''
      : ` · ${t.outFrom}부터 밖 ${t.outDays}일` +
        (t.peakZ == null ? '' : `(최대 ${t.peakZ.toFixed(2)}σ)`);
  /* Delta·액면이 대사표 머리에 선다 [OWNER 2026-09-02] — 대사표의 KRD 줄이
     ±이 수라(다리 둘이면 합이 0), 이 표만 떼어 봐도 검산이 서게. 액면은 pv01
     근사(거래 표의 그 각주).

     **「명목」이 아니라 「Delta」** [OWNER 2026-09-04, 2026-09-07 에 이 자리까지].
     노브와 카드는 09-04 에 바꿨는데 이 줄과 거래 표 부제·창 각주가 남아, 하필
     바로 옆의 «액면 약 35.0억» 과 한 줄에 서 있었다 — 그 충돌이 애초에 이름을
     바꾼 이유다(`KnobBar` 의 그 주석). */
  const size = ` · Delta ${run.params.notional.toLocaleString()}원/bp` +
    (run.principal ? `(액면 약 ${fmtEok(run.principal.krw)} — 지금 커브)` : '');
  return `${t.entryT} → ${t.exitT} · ${t.bars}봉 · ${legs}${out} · ${WHY_WORD[t.why]}${size}`;
}

/** 밴드 상태 한 마디 — 측정 보드의 어휘(`MrState`)와 같은 말이다. */
function bandWord(out: number, run: number): string {
  if (out === 0) return '밴드 안';
  return `밴드 ${out > 0 ? '위' : '아래'} 밖 ${run}일째`;
}

export function StrategyWindow({
  id,
  label,
  onClose,
}: {
  id: string;
  label: string;
  onClose: () => void;
}) {
  const [knobs, setKnobs] = useState<MrStrategyParams>(MR_STRATEGY_DEFAULTS);
  const [run, setRun] = useState<MrStrategyRun>();
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string>();
  const [idx, setIdx] = useState<{ chart: 'price' | 'z' | 'eq'; i: number } | null>(null);
  /* 눌러서 편 거래 — 그 구간의 **일별 대사**를 연다 [OWNER 2026-08-27 — "개별
     거래 눌러보면 대사도 가능하게 해주고,, 원래 우리가 그렇게 해왔듯이"].
     백테스트 창의 「일별 대사」와 같은 문법이다: 하루씩 펴 놓고, 가로합이
     그날 손익이 되고, 세로합이 거래 손익이 된다. 실행할 때마다 닫는다 —
     다른 실행의 거래를 펴 놓고 있으면 그 표가 거짓이 된다. */
  const [openTrade, setOpenTrade] = useState<string | null>(null);
  /* 구간 — **전역 설정값** [OWNER 2026-09-04]. 실행·종목이 바뀌어도 남는다.
     성과를 바꾸지만 stale 은 안 세운다: 서버가 네 구간을 한 번에 보내 오므로
     (`MrStrategyRun.spans`) 고르개는 이미 와 있는 값을 고를 뿐이고, 엔진은
     늘 전체 표본에서 한 번만 돈다(그 근거는 `api.ts::MR_SPANS`). */
  const [span, setSpan] = useState<MrSpan>('all');
  /* ── 근사 최적화 [OWNER 2026-09-04] ──────────────────────────────────────
     162칸이라 **누를 때만** 부른다(`/api/mr/recon` 이 갈라져 있는 그 근거).
     결과는 실행·종목·구간이 바뀌면 버린다 — 딴 조건의 순위를 들고 있으면
     화면이 거짓말을 한다. 순위 기준만은 남긴다(서버에 다시 안 묻는다). */
  const [opt, setOpt] = useState<MrOptimizeRun>();
  const [optRunning, setOptRunning] = useState(false);
  const [optError, setOptError] = useState<string>();
  /* 기본 기준은 **CDaR 비**다 [OWNER 2026-09-09] — Calmar 에서 옮겨 왔다.
     근거와 실측(순위상관 0.84 · 1등이 계열에 따라 갈림)은 `api.ts::MR_RANK_KEYS`
     머리와 `docs/EVAL_LANE_STATE.md` §8 에. */
  const [rankKey, setRankKey] = useState<MrRankKey>('cdarRatio');
  /* 서랍 펼침을 창이 쥔다 — 거래 줄을 누르면 그 자리에서 대사가 펴져야 한다
     (안 쥐면 「눌렀는데 아무 일도 안 일어난」 화면이 된다). 접는 손잡이는
     여전히 서랍 탭이다. */
  const [drawerOpen, setDrawerOpen] = useState(false);

  /* ── 창을 열면 **격자부터 돈다** [OWNER 2026-09-09 — "전략 실험을 누름과
     동시에 그냥 바로 최적화 값을 보여주는 것이 합당해 보임"] ─────────────────
     순서는 셋이다: ① 근사 최적화 162칸 → ② 순위 기준의 1등을 노브에 꽂고 →
     ③ 그 조건으로 실행. 사람이 누르는 것은 **비용·Delta** 뿐이고, 그 둘이
     바뀌면 ①부터 다시 돈다 [OWNER — "자동으로 다시 돌리기"].

     **왜 비용이 격자를 다시 돌리나.** 비용은 칸마다 다르게 문다(거래 수가
     달라서) — 편도 0.25 에서 1등인 칸이 1.0 에서는 아닐 수 있다. 반대로
     **Delta 는 순위를 안 바꾼다**: 비율 지표(Calmar·Sortino·Martin·GPR)의
     분자·분모가 같은 배로 커져 불변이다. 그래도 같이 다시 도는 이유는 총손익
     기준으로 볼 때의 표와 「지금 칸」이 갈리지 않게 하기 위해서다(그 기준은
     채택 금지지만 화면에는 있다).

     경합은 순번으로 버린다 — 비용을 빨리 두 번 바꾸면 첫 격자의 늦은 응답이
     둘째의 결과를 덮을 수 있다(보드 딥링크에서 이미 밟은 그 판례). */
  const seq = useRef(0);

  /** ②③ — 격자의 한 칸을 노브에 꽂고 **그 조건으로 실행**한다.
   *
   *  종전에는 채택이 노브만 바꾸고 사람이 「실행」을 눌러야 했다. 노브 줄에서
   *  다섯이 내려간 지금은 그 버튼이 없으므로, 채택이 곧 실행이다 — 안 그러면
   *  TOP 5 의 「채택」이 아무 일도 안 하는 버튼이 된다. */
  const adoptAndRun = useCallback((c: {
    lookback: number; entryZ: number; exitZ: number; stopZ: number;
    entryMode: MrStrategyParams['entryMode'];
  }, my: number) => {
    const next: MrStrategyParams = { ...knobsRef.current, ...c };
    setKnobs(next);
    /* 다른 실행의 거래를 펴 놓고 있으면 그 대사가 거짓이 된다. */
    setOpenTrade(null);
    setDrawerOpen(false);
    setError(undefined);
    setRunning(true);
    fetchMrStrategy(id, next)
      .then((r) => {
        if (seq.current === my) setRun(r);
      })
      .catch((e: unknown) => {
        if (seq.current !== my) return;
        if (e instanceof BacktestUnavailable) setError('실행 중인 백엔드(:8200)가 필요해요.');
        else setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (seq.current === my) setRunning(false);
      });
  }, [id]);

  /** ① — 격자를 돌리고 1등을 채택한다. 실패해도 **창이 비지 않는다**: 원본
   *  PMS 규칙(기본 노브)으로 실행하고 왜 격자가 없는지를 최적화 절이 적는다.
   *  빈 화면은 「백엔드가 죽었나」와 「이 종목은 격자가 안 선다」를 구분해 주지
   *  못한다. */
  const runAuto = useCallback(() => {
    const my = ++seq.current;
    setOpt(undefined);
    setOptError(undefined);
    setOptRunning(true);
    fetchMrOptimize(id, knobsRef.current, span)
      .then((o) => {
        if (seq.current !== my) return;
        setOpt(o);
        const best = rankCells(o.cells, rankKeyRef.current)[0];
        adoptAndRun(best ?? knobsRef.current, my);
      })
      .catch((e: unknown) => {
        if (seq.current !== my) return;
        if (e instanceof BacktestUnavailable) setOptError('실행 중인 백엔드(:8200)가 필요해요.');
        else setOptError(e instanceof Error ? e.message : String(e));
        adoptAndRun(knobsRef.current, my);
      })
      .finally(() => {
        if (seq.current === my) setOptRunning(false);
      });
  }, [id, span, adoptAndRun]);

  /* 노브·순위 기준의 **지금 값**을 콜백이 읽는다 — 의존 배열에 넣으면 채택이
     노브를 바꿀 때마다 격자가 다시 도는 고리가 된다(채택 → 노브 → 격자 →
     채택 …). 격자를 다시 도는 조건은 아래 효과가 명시적으로 정한다. */
  const knobsRef = useRef(knobs);
  knobsRef.current = knobs;
  const rankKeyRef = useRef(rankKey);
  rankKeyRef.current = rankKey;

  /* 격자가 다시 도는 자리는 **넷뿐**이다: 종목 · 구간 · 비용 · Delta.
     (다시 돌리기 버튼은 같은 함수를 손으로 부른다.) */
  useEffect(() => {
    runAuto();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, span, knobs.costBp, knobs.notional]);

  /* 순위 기준이 바뀌면 **격자는 그대로**, 1등만 다시 고른다 — 서버는 칸마다
     지표를 다 실어 보내므로 다시 물을 이유가 없다(`OptimizePane` 머리의 그
     판단). 실행은 다시 한다: 조건이 바뀌었으니 머리 카드가 옛 조건의 수를
     들고 있으면 안 된다. */
  const firstRank = useRef(true);
  useEffect(() => {
    if (firstRank.current) {                 // 첫 렌더는 위 효과가 이미 돈다
      firstRank.current = false;
      return;
    }
    if (!opt) return;
    const best = rankCells(opt.cells, rankKey)[0];
    if (best) adoptAndRun(best, ++seq.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rankKey]);

  /** 「채택」 — TOP 5 의 한 칸을 조건으로 삼는다(= 곧 실행). 노브 줄에서 다섯이
   *  내려간 뒤로 **조건을 바꾸는 유일한 길**이다. */
  const adopt = useCallback((c: MrOptimizeCell) => {
    adoptAndRun(c, ++seq.current);
  }, [adoptAndRun]);

  /* pinned 규율 — 실행 시점 파라미터와 지금 노브가 갈리면 stale. 판정은
     **공용**이다(`KnobBar.mrKnobsStale`) — 통합 장부 창과 같은 조건을 써야
     같은 노브를 돌렸을 때 한 창만 낡은 숫자를 들고 있는 일이 없다. */
  /* ⚠ **도는 중에는 stale 을 안 세운다** [2026-09-09]. 종전에는 사람이 노브를
     바꾸고 실행을 누르기 전까지가 stale 이었다. 지금은 화면이 스스로 조건을
     꽂고 곧바로 실행하므로, 그 사이(요청이 도는 동안)에도 판정이 참이 되어
     배너가 깜빡이고 마커가 사라졌다 가 돌아온다. 「지금 노브가 실행과 다르다」는
     사실은 **응답을 기다리는 동안에는 정보가 아니다** — 기다림은 「돌리는 중…」
     이 이미 말한다. */
  const stale = useMemo(
    () => (run && !running && !optRunning ? mrKnobsStale(run.params, knobs) : false),
    [run, knobs, running, optRunning],
  );

  const dates = useMemo(() => run?.points.map((p) => p.t) ?? [], [run]);

  /* ── 이 구간의 성과 [OWNER 2026-09-04] ──────────────────────────────────
     서버가 네 벌을 다 보내 온다(`spans`). 화면은 고르기만 하므로 재실행도
     stale 도 없다. 구 백엔드는 이 필드를 모르므로(§6 ⑥ 배포 순서) 없으면
     `undefined` 이고, 그때 카드가 「구간별 성과는 새 백엔드가 필요해요」를
     적는다 — 옛 `summary` 로 조용히 떨어지면 화면이 전체 기간의 수를 이
     구간의 수인 것처럼 말하게 된다. */
  const perf: MrPerf | undefined = useMemo(
    () => run?.spans?.find((b) => b.span === span),
    [run, span],
  );

  /* 구간의 첫 인덱스 — **서버가 채점한 첫 봉**을 그대로 찾는다.
     종전에는 화면이 달력 산술(`monthsBefore`)로 직접 잘랐는데, 이제 카드가
     서버 채점이라 두 자가 하루라도 갈리면 「구간 순손익」(곡선)과 「총손익」
     (카드)이 다른 수가 된다. 마지막 두 점은 남긴다: 한 점짜리 차트는 선이
     못 된다. */
  const w0 = useMemo(() => {
    if (!run || run.points.length < 2) return 0;
    const from = perf?.from;
    if (!from) return 0;
    const i = run.points.findIndex((p) => p.t >= from);
    return Math.min(i < 0 ? 0 : i, run.points.length - 2);
  }, [run, perf]);
  const winPoints = useMemo(() => (run ? run.points.slice(w0) : []), [run, w0]);
  const winDates = useMemo(() => winPoints.map((p) => p.t), [winPoints]);
  /* 누적의 재기준점 = 구간 **직전** 봉의 누적. 구간 순손익 = 구간 끝 누적 − 이
     값이라, 재기준한 곡선의 마지막 점이 곧 구간 순손익이다 — 전체 곡선을 자른
     것과 같은 수임이 구성상 보장된다. */
  const baseCum = run && w0 > 0 ? run.points[w0 - 1]!.cum : 0;
  const winPnl = winPoints.length ? winPoints[winPoints.length - 1]!.cum - baseCum : 0;
  /* 구간에 «걸친» 거래 — 청산이 구간 시작 뒤인 것 전부(진입은 표본 끝보다 늘
     앞이다). 구간 안 진입만 세면 걸쳐 들어온 거래의 손익이 구간 순손익에는
     있는데 표에는 없어, 표와 곡선이 딴말을 하게 된다. */
  const winFrom = winPoints[0]?.t ?? '';
  /* 표에 세울 줄 — 거래들 + **미청산 한 줄** [OWNER 2026-09-09 — "미청산도 PnL에
     포함하기"]. 미청산은 늘 마지막 봉까지 열려 있으므로 어느 구간에도 걸린다
     (그래서 구간 필터를 안 탄다). 번호는 마지막 거래 다음이다 — 「몇 번째
     진입인가」를 세는 번호라 열려 있는 다리도 그 줄에 선다(`entryCount` 와 같은
     셈). */
  const shownTrades = useMemo(
    () => {
      if (!run) return [];
      const rows = run.trades
        .map((t, k) => ({ t, n: k + 1 }))
        .filter(({ t }) => span === 'all' || t.exitT >= winFrom);
      const op = openAsTrade(run);
      return op ? [...rows, { t: op, n: run.trades.length + 1 }] : rows;
    },
    [run, span, winFrom],
  );

  /* 세 패널(값·z·누적)이 **같은 값-축 폭**을 쓴다 — 라벨이 `2.55`·`-1.85`·
     `+1.2억` 으로 제각각이라 그냥 두면 셋의 플롯이 서로 다른 폭이 되고, 같은
     날짜가 세 패널에서 다른 가로 자리에 선다(CLAUDE.md 「얼라인」 7). */
  const stack = useStackedScales();
  /* 봉마다의 **사건** — 마커·세로선·판독이 이 하나를 같이 읽는다
     [OWNER 2026-08-28 — "언제 진입했고 그런걸 알 수 있게"].
     종전에는 진입 순번만 있었고(세로선 하나) 그래서 화면이 「들어갔다」만
     말하고 「어떻게 나왔다」는 안 말했다 — 청산과 손절이 같은 그림이었다.
     청산 봉 재진입 금지 규약 덕에 한 봉에 사건이 둘일 수 없으므로 Map 이다. */
  const events = useMemo(() => {
    const m = new Map<number, MrEvent>();
    if (!run) return m;
    const at = new Map(dates.map((t, i) => [t, i]));
    run.trades.forEach((t, k) => {
      const key = tradeKey(t);
      const e = at.get(t.entryT);
      const x = at.get(t.exitT);
      if (e != null) m.set(e, { kind: 'entry', dir: t.dir, n: k + 1, key });
      /* 손절만 하락색으로 갈라 세운다 — 나머지 셋(청산·역신호·타임스탑)은
         「계획대로 나왔다」는 같은 종류라 같은 뮤트다. 정확한 사유는 표가 진다. */
      if (x != null)
        m.set(x, { kind: t.why === 'stop' ? 'stop' : 'exit', why: t.why,
                   dir: t.dir, n: k + 1, key });
    });
    /* 미청산 다리도 사건이다 — 표본 끝에 열려 있는 포지션이 차트에서만
       사라지면, 승률 옆의 「미청산 1건」이 어디 것인지 화면이 못 가리킨다.

       열쇠는 **거래와 같은 모양**이다(`tradeKey`) — 종전에는 `'open'` 이라는
       따로 된 상수였는데, 그 줄이 2026-09-09 에 거래 표의 줄이 되면서 표의
       클릭과 차트의 강조가 같은 열쇠를 써야 하게 됐다(안 맞추면 미청산 줄을
       눌러도 차트가 딴 거래를 굵게 세운다). */
    const op = openAsTrade(run);
    if (op) {
      const e = at.get(op.entryT);
      if (e != null && !m.has(e))
        m.set(e, { kind: 'entry', dir: op.dir, n: run.trades.length + 1,
                   key: tradeKey(op) });
    }
    return m;
  }, [run, dates]);

  const unit = (run?.unit ?? 'bp') as Unit;
  const set = (patch: Partial<MrStrategyParams>) => setKnobs((k) => ({ ...k, ...patch }));

  /* 이 계열에서 실제로 할 수 있는 거래 [OWNER 2026-08-25 — "BSS에서 숏은 없는거야,,
     현물대차매도는 안할거거든"]. 한 방향뿐이면 그 사실을 숫자 옆에서 말한다 —
     노브가 아니므로 설정 줄이 아니라 「조건」과 거래 표의 머리에 선다. */
  const only = run && run.dirs.allowed.length === 1
    ? (run.dirs.allowed[0]! > 0 ? run.dirs.plus : run.dirs.minus)
    : null;
  const dirSub = only ? `${only.legs} 한 방향이에요` : undefined;

  /* 펴 놓은 거래와 그 구간의 봉들 — 대사표의 재료. 키는 «진입-청산» 이라
     실행이 바뀌면 자연히 안 맞고, 그때는 목록으로 돌아간다. */
  /* 미청산 줄도 펴진다 — 표의 줄이 된 이상 누를 수 있어야 하고(같은 행동을
     줄마다 다르게 두면 그 줄만 죽은 줄이다), 대사표는 진입→마지막 봉 구간을
     그대로 편다. */
  const sel = (run
    ? [...run.trades, ...(openAsTrade(run) ? [openAsTrade(run)!] : [])]
        .find((t) => tradeKey(t) === openTrade)
    : null) ?? null;
  const reconRows = useMemo(
    () =>
      sel && run
        ? run.points
            .map((p, i) => ({ p, i }))
            .filter(({ p }) => p.t >= sel.entryT && p.t <= sel.exitT)
        : [],
    [sel, run],
  );
  const dirStat = !run ? '—' : only ? only.legs : '양방향';

  /* 다리 **레벨** 유무 — BSS 만 있다(캐리와 같은 출처 — api.ts `govt` 주석).
     선물·퓨처스왑·구 백엔드는 없고, 그때 열은 조용히 접힌다.

     ⚠ 점의 `legs`(다리별 대사 줄)와 **다른 것**이다. `legs` 는 계열 전부에
     오고, 이 값은 「국고·IRS·CD 세 레벨을 아는가」다 — CD 열과 거래 표의
     진입 다리 레벨이 이 값에 달려 있다. 2026-09-03 에 다리가 줄로 내려가면서
     둘이 헷갈릴 자리가 생겨 이름을 늘렸다. */
  const hasLegLevels = useMemo(() => !!run && run.points.some((p) => p.govt != null), [run]);
  /* 대사표의 숫자 열 — 레벨·z·CD 는 2026-09-03 에 「일별 레벨」 칸으로 나갔다
     (위 `LEVEL_COLS`). 머리와 몸통이 **같은 목록**을 읽어야 열이 안 어긋난다. */
  const reconCols: readonly string[] = RECON_COLS;
  /* 「일별 레벨」의 다리 이름 — 계열이 정한다(`국고`·`IRS`·`선물`). 다리가
     있는 첫 봉에서 뽑고, **머리와 몸통이 이 한 목록만 읽는다.**

     종전에는 머리는 이 목록에서, 몸통은 «그 줄의 봉»에서 열을 만들었다
     (2026-09-03 감사) — 봉 하나가 다리를 빠뜨리면 그 줄만 짧아져 격자가
     어긋난다. 어긋난 표는 대사표가 아니다(같은 이유로 `RECON_COLS` 도 한
     목록이다). 값은 이름이 아니라 **자리**로 찾는다. */
  const legNames: readonly string[] = useMemo(
    () => (run?.points ?? []).find((p) => p.legs?.length)?.legs?.map((g) => g.k) ?? [],
    [run],
  );
  const levelCols: readonly string[] = useMemo(
    () => ['레벨', 'z', ...legNames, ...(hasLegLevels ? ['CD'] : [])],
    [legNames, hasLegLevels],
  );
  /* 날짜 → 점 — 거래 표가 진입 시점 다리 레벨을 여기서 찾는다(서버가 점마다
     실었으므로 거래에 또 싣지 않는다 — 같은 수를 두 자리에 두면 갈릴 수 있다). */
  const pointAt = useMemo(() => new Map((run?.points ?? []).map((p) => [p.t, p])), [run]);

  /* 거래 표 머리 — 총 건수·명목·액면 [OWNER 2026-09-02 — "진입 레벨과 기준
     노셔널과 같은 것들이 전부 나와야 직접 대사가 가능"]. 명목·액면은 모든
     거래에 **같은 수**라 열이 아니라 머리에 선다 — 같은 수 서른여덟 줄은 표가
     없는 정보를 있는 척하는 것이다.

     액면은 **지금 커브** 기준이다 — 「지금 세우면 이만큼」이다. 거래마다의
     액면은 그 거래의 진입일 커브로 따로 잰다(2026-09-03 검산: 그렇게 안 하면
     옛 거래가 명목 노브보다 최대 16% 큰 포지션이 된다). 그 값은 대사표가
     적는다. */
  const tradeSub = !run ? undefined
    : run.trades.length === 0 ? '이 창에 거래가 없어요'
    : [
        dirSub,
        span === 'all'
          ? `${run.trades.length}건`
          : `구간에 걸친 ${shownTrades.length}건 / 전체 ${run.trades.length}건`,
        /* 미청산 줄은 **건수에 안 든다** — 표의 줄은 늘었지만 「몇 건 거래했나」는
           원본 규약대로 청산된 것만이다(KPI 타일의 「거래」와 같은 수여야 한다).
           그래서 그 줄이 표에 있다는 사실만 따로 적는다. */
        openAsTrade(run) ? '미청산 1줄 포함(건수 밖)' : null,
        `Delta ${run.params.notional.toLocaleString()}원/bp`,
        run.principal ? `액면 약 ${fmtEok(run.principal.krw)}(지금 커브)` : null,
      ].filter((x): x is string => x != null).join(' · ');

  /* 「실전 규칙이 켜져 있어요」 각주는 **없앴다** [2026-09-02 검사]. 그 다섯을
     화면에서 내린 뒤로 노브가 기본값 밖으로 갈 경로가 없어(딥링크도 없다) 이
     각주는 증명 가능하게 도달 불가였고, 도달 불가한 가지는 「끄면 원본 재현」
     이라고 말하면서 **끌 컨트롤이 없는** 화면을 만든다. 노브를 되살리는 날
     `KnobBar.tsx` 그 자리 주석과 함께 이것도 되살린다. */

  /* 가격 주선 색 = 구간 순변화 방향(Main 미리보기의 규칙) — 「구간」은 **보이는
     구간**이다. 표시 창을 잘랐는데 색이 12년 순변화를 말하면 색과 그림이
     딴말을 한다. */
  const priceHue = useMemo(() => {
    if (winPoints.length < 2) return 'var(--color-fgMuted)';
    const net = winPoints[winPoints.length - 1]!.v - winPoints[0]!.v;
    return net === 0 ? 'var(--color-fgMuted)' : net > 0 ? 'var(--sr-up)' : 'var(--sr-down)';
  }, [winPoints]);

  /* 주선 = 구간 방향색 + 점선 면(Main 미리보기·MR 상세 카드와 같은 문법 — 같은
     값+밴드 그림이 두 결이면 안 된다), 보조선 뮤트. **밴드가 먼저** = 아래에 깔린다.
     캔버스에는 불투명도 손잡이가 없어 색 자체를 흐리게 만든다(`palette.dim`). */
  const priceLines: TimeLine[] = !run ? [] : [
    { id: 'up', values: winPoints.map((p) => p.up), color: (pa) => pa.dim('var(--color-fgMuted)', 45), width: 1 },
    { id: 'lo', values: winPoints.map((p) => p.lo), color: (pa) => pa.dim('var(--color-fgMuted)', 45), width: 1 },
    { id: 'ma', values: winPoints.map((p) => p.ma), color: (pa) => pa.dim('var(--color-fgMuted)', 70), width: 1 },
    {
      id: 'v',
      values: winPoints.map((p) => p.v),
      color: (pa) => pa.resolve(priceHue),
      area: 'dots',
      format: (v: number) => fmtLevel(v, unit),
    },
  ];

  /* 사건의 **점**(오실레이터·손익 곡선)과 **세로선**(세 패널 공통).
     stale 이면 둘 다 숨는다 — 노브가 실행과 갈린 판에서 마커만 옛 자리에 남으면
     화면이 「이 설정으로 여기서 들어갔다」고 거짓말한다(원본 규율). */
  /* 사건 인덱스는 전체 기준이다(`events` 가 전체 날짜로 만든다) — 표시 창을
     자르면 `w0` 만큼 옮겨 세운다. 구간 앞의 사건은 화면 밖이라 버린다. */
  const evList = stale ? [] : [...events.entries()].filter(([i]) => i >= w0);
  const evMarkers: TimeMarker[] = evList.map(([i, e]) => ({
    index: i - w0,
    /* 진입은 **방향색**(그 다리가 무엇을 사는지), 청산은 뮤트, 손절은 하락색.
       청산과 손절이 같은 점이면 「어떻게 끝났나」를 표에서만 알 수 있다. */
    color: (pa) =>
      e.kind === 'stop' ? pa.down
      : e.kind === 'exit' ? pa.fgMuted
      : e.dir === 0 ? pa.fgMuted
      : e.dir > 0 ? pa.up : pa.down,
  }));
  /* 세로선은 **진입**만 긋는다 — 거래마다 둘씩 그으면 15거래에 30줄이라 200px
     패널이 빗금이 된다. 펴 놓은 거래 하나만 청산선까지 잉크로 세운다.
     라벨도 그 하나에만 붙인다: 겹침 회피는 호출부의 몫인데(verticalLines 머리),
     열다섯 개를 다 적으면 회피할 수 없는 밀도가 된다. */
  const evLines = evList
    .filter(([, e]) => e.kind === 'entry' || e.key === openTrade)
    .map(([i, e]) => ({
      index: i - w0,
      label: e.key === openTrade ? (e.kind === 'entry' ? '진입' : eventWord(e, false)) : undefined,
      tone: e.key === openTrade ? ('ink' as const) : ('muted' as const),
    }));

  const zLines: TimeLine[] = !run ? [] : [
    {
      id: 'z',
      values: winPoints.map((p) => p.z),
      color: (pa) => pa.fg,
      format: (v: number) => `${v.toFixed(1)}σ`,
    },
  ];

  /* 0선과 진입 문턱 — 그림이 긋는 선은 **결정이 붙어 있는 것**뿐이다.
     ±1.5σ 점선 쌍(「관찰 σ」)이 2026-09-02 에 여기서 빠졌다 — 근거는 파일 머리
     주석. 결정이 안 붙은 선은 눈금이 아니라 잡음이다. */
  const zBands: ScalePriceLine[] = !run ? [] : [
    { value: 0, color: (pa) => pa.line },
    { value: run.params.entryZ, color: (pa) => pa.lineHeavy },
    { value: -run.params.entryZ, color: (pa) => pa.lineHeavy },
  ];

  /* 손익 곡선은 부호가 색을 정한다 — LinkedCharts 누적 손익의 그 문법. 표시
     창을 잘랐으면 부호도 **구간 순손익**의 것이다(곡선이 재기준돼 있으므로
     마지막 점의 부호가 곧 그것이다). */
  const eqHue = winPnl >= 0 ? 'var(--sr-up)' : 'var(--sr-down)';
  const eqLines: TimeLine[] = !run ? [] : [
    {
      id: 'cum',
      /* 구간 시작 = 0 재기준 [OWNER 2026-09-02]. 전체 표시(`w0 = 0`)에서는
         `baseCum = 0` 이라 원래 곡선 그대로다 — 두 판이 딴 산술이 아니다. */
      values: winPoints.map((p) => p.cum - baseCum),
      color: (pa) => pa.resolve(eqHue),
      area: 'solid',
      areaColor: (pa) => pa.dim(eqHue, 14),
      format: (v: number) => fmtKrw(v),
    },
  ];
  const zeroLine: ScalePriceLine[] = [{ value: 0, color: (pa) => pa.line }];

  /* 캔버스가 못 하는 말 — 짚은 봉의 한 문장 [CLAUDE.md 규칙 7: «읽을 DOM 이
     없다 → hoverLabel → .sr-a11y-only 의 aria-live 줄이 진다»]. 차트마다
     주인공이 다르므로 문장도 다르다(값·z·누적) — Main 미리보기 `scrubLabel`
     이 날짜+값을 읽는 그 자리다. */
  const scrubWord = (i: number, chart: 'price' | 'z' | 'eq'): string => {
    const p = winPoints[i];
    if (!p) return '';
    if (chart === 'price') return `${p.t} ${fmtLevel(p.v, unit)}${unitSuffix(unit)}`;
    if (chart === 'z') return `${p.t} z ${p.z == null ? '—' : `${p.z.toFixed(2)}σ`}`;
    return `${p.t} 누적 ${fmtKrw(p.cum - baseCum)}`;
  };

  /* 일별 대사는 **창 바닥 서랍**이 진다 [2026-09-02, Backtest 창의 그 문법].
     백테스트가 대사를 서랍에 둔 근거가 트레이더 피드백 5(«팝업창 하단에
     열었다 닫았다 하는 탭» — `WindowDrawer.tsx` 머리)이고, 이 창도 같은
     물건을 같은 자리에 둔다. 종전에는 거래 패널의 «내용이 바뀌는» 판이라
     목록과 대사를 같이 볼 수 없었다. */
  /** 「일별 레벨」 칸 — **어디에 있었나**의 표 [OWNER 2026-09-03 — "레벨이랑
   *  Z값은 일별대사 말고 일별레벨 칸을 하나 파서 다른 칸에서 보여주게 하고
   *  (일별대사와 일별레벨은 동일한 위계임)"].
   *
   *  대사는 「얼마나 벌었나」이고 이 표는 「어디에 있었나」다. 둘을 한 표에 두면
   *  열이 열두 개가 되고, 어느 것이 돈이고 어느 것이 자리인지 눈이 매번 가른다.
   *  위계가 같으므로 **서랍의 형제 탭**이지 대사의 하위가 아니다.
   *
   *  다리 레벨은 서버가 봉마다 실어 준 것을 그대로 적는다(`legs[].lvl`) —
   *  BSS 는 국고·IRS, 퓨처스왑은 선물·IRS, 선물 아웃라이트는 하나다. CD 는
   *  다리가 아니라 IRS 다리 캐리의 받는 쪽이라 맨 끝에 따로 선다. */
  /* 거래 하나의 **실가격 대사** [OWNER 2026-09-03 — "이 방향이 정확한 대사"].
     BSS 를 자산스왑으로 세워 민평 노드를 범프한 테너별 KRD 를 받는다. 서버가
     별도 라우트인 이유(범프가 비싸다)와 같은 이유로 **거래를 누를 때만** 부른다. */
  const [recon, setRecon] = useState<MrRecon | null>(null);
  useEffect(() => {
    if (!sel || !run) { setRecon(null); return; }
    let alive = true;
    setRecon(null);
    fetchMrRecon(run.id, sel.entryT, sel.exitT, sel.dir, run.params.notional)
      .then((r) => { if (alive) setRecon(r); })
      /* 못 받아 온 것과 «못 세운다»는 다른 말이다 — 전자는 이유를 그대로 싣는다. */
      .catch((e: unknown) => {
        if (alive) setRecon({ available: false, why: e instanceof Error ? e.message : '대사를 못 받았어요.' });
      });
    return () => { alive = false; };
  }, [sel, run]);

  const levelPane = sel && run ? (
    <VStack gap={0.5} width="100%" flexGrow={1} minHeight={0}>
      <Text font="caption" as="span" color="fgMuted">
        {reconSub(sel, run)}
      </Text>
      <Box className="sr-mr-drawertable" width="100%">
        <Table bordered={false}>
          <TableHeader sticky>
            <TableRow>
              <TableCell as="th" scope="col">
                <Text font="caption" as="span" color="fgMuted">날짜</Text>
              </TableCell>
              {levelCols.map((c) => (
                <TableCell key={c} as="th" scope="col" className="sr-num" justifyContent="flex-end">
                  <Text font={headFont(c)} as="span" color="fgMuted" noWrap>{c}</Text>
                </TableCell>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {reconRows.map(({ p }) => (
              <TableRow key={p.t}>
                <TableCell>
                  <Text font="label2" as="span" tabularNumbers noWrap>{p.t}</Text>
                </TableCell>
                <ReconNum v={p.v} kind="level" unit={unit} />
                <ReconNum v={p.z} kind="sigma" />
                {legNames.map((k, j) => (
                  <ReconNum key={k} v={p.legs?.[j]?.lvl ?? null} kind="level" unit={'%' as Unit} />
                ))}
                {hasLegLevels ? <ReconNum v={p.cd ?? null} kind="level" unit={'%' as Unit} /> : null}
              </TableRow>
            ))}
            <TableRow>
              <TableCell>
                <Text font="label1" as="span" noWrap>합계</Text>
              </TableCell>
              {/* 레벨·z 는 더할 수 있는 양이 아니다 — **진입 → 청산**으로 적는다
                  (거래 표의 그 규칙). 다리 레벨도 같은 자로 잰다. */}
              <TableCell className="sr-num" justifyContent="flex-end">
                <Text font="label1" as="span" tabularNumbers noWrap>
                  {`${fmtReconLevel(sel.entryV, unit)}→${fmtReconLevel(sel.exitV, unit)}`}
                </Text>
              </TableCell>
              <TableCell className="sr-num" justifyContent="flex-end">
                <Text font="label1" as="span" tabularNumbers noWrap>
                  {`${sel.entryZ.toFixed(2)}→${sel.exitZ == null ? '—' : sel.exitZ.toFixed(2)}`}
                </Text>
              </TableCell>
              {legNames.map((k, j) => (
                <LegArrow
                  key={k}
                  a={reconRows[0]?.p.legs?.[j]?.lvl}
                  b={reconRows.at(-1)?.p.legs?.[j]?.lvl}
                />
              ))}
              {hasLegLevels ? (
                <LegArrow a={reconRows[0]?.p.cd} b={reconRows.at(-1)?.p.cd} />
              ) : null}
            </TableRow>
          </TableBody>
        </Table>
      </Box>
    </VStack>
  ) : null;

  /** 대사 칸의 **정본** — 실가격 자산스왑 대사 [OWNER 2026-09-03 — "krd에서
   *  원래는 테너별로 민감도 찍어줬잖아 … 이 방향이 정확한 대사니까"].
   *
   *  BSS 는 국고 매수 · IRS 페이라 이 앱의 자산스왑과 같은 구조다. 그래서
   *  `cashbond` 의 그 기계를 그대로 부른다 — 민평 노드를 1bp 씩 범프해 채권을
   *  다시 가격하고, 그 결과가 **테너별 KRD**·Δbp·추정이다. 백테스트·시뮬과
   *  같은 `ReconStack` 이 그린다(같은 응답 모양).
   *
   *  ## 이 수는 백테스트 성과표와 다르다 — 그게 측정이다
   *
   *  이 리포의 자산스왑은 par-par(같은 명목)이라 **DV01 중립이 아니고**
   *  [OWNER 2026-08-14], MR 엔진은 반대로 DV01 중립이다. 그래서 실가격 손익이
   *  엔진 손익보다 체계적으로 크다(실측 BSS-7Y 거래별 +0.7~+3.5백만원). 화면이
   *  **둘을 나란히** 적어 「근사와 실제가 이만큼 다르다」를 보인다
   *  [OWNER 2026-09-03] — 숨기면 두 화면이 다른 수를 말하는 이유가 사라진다.
   *
   *  ## 못 세우는 자리
   *
   *  민평 이력은 2020-01-02 부터라 MR 표본의 절반이 그 앞이고, 선물 계열은
   *  자산스왑이 아니다. 앞의 것은 **왜인지만 적고 비워 두며**, 뒤의 것은 오늘
   *  만든 다리 표(`ReconDay`)가 그대로 선다 [OWNER 2026-09-03]. */
  const realPane = sel && run && recon?.available ? (
    <VStack gap={0.5} width="100%" flexGrow={1} minHeight={0}>
      <Text font="caption" as="span" color="fgMuted">
        {reconSub(sel, run)}
      </Text>
      {/* 근사와 실제를 **한 줄에** — 이 차이가 곧 「DV01 중립 근사가 실제
          자산스왑과 얼마나 다른가」다. 숨기면 백테스트 성과표와 이 표가 다른
          수를 말하는 이유를 읽는 사람이 못 찾는다. */}
      {/* 차이를 **성분으로 가른다** [2026-09-03 감사]. 종전에는 "잔여
          금리노출과 캐리·롤다운·조달" 이라고만 적었는데, 실측해 보니 가장 큰
          항이 **거래비용**(엔진만 있다)이고 그 다음이 **롤다운**(실가격만
          있다)이며 잔여 금리노출은 가장 작았다(16건 합: 비용 +16.0백만 ·
          롤다운 +7.9백만 · 평가 차 +1.9백만). 큰 것을 빼놓고 작은 것을 앞에
          세운 문장이었다.

          **표시 정밀도에서도 더해진다** — `splitKrw` 의 그 수법이다
          (`lib/krw.ts`, 2026-08-14): 각 항을 한 번씩만 반올림하고 **마지막
          항이 잔차를 진다.** 안 그러면 만원 단위에서 세 항의 합이 차이와
          어긋난다(실측 16건 중 3건). 읽는 사람이 암산으로 줄을 검산할 수
          있어야 하고, 그게 이 줄의 존재 이유다. */}
      <Text font="legal" as="p" color="fgMuted">
        {reconBlocks(recon).some((b) => b.truncated)
          ? `엔진 근사 ${fmtKrw(sel.pnl)} · 실가격은 창이 잘려 합을 못 내요 — 아래 각주를 보세요.`
          : bridgeText(sel, recon)}
      </Text>
      {/* 표는 **자기 달력 위에** 선다 — 백테스트 창과 같은 문법이다
          (`BacktestWindow`). 이름표는 선물 계열에만 세운다: 자산스왑 한 표에
          «자산스왑 대사» 라고 적으면 안 읽히는 줄이 하나 는다.

          높이를 **안 박는다** [2026-09-07]. 종전에는 블록이 여럿일 때 `15vh` 로
          눌렀는데, FSW 가 한 표가 되면서 그 조건이 늘 거짓이 됐다 — 조건만 죽은
          채로 두면 다음 사람이 «표가 눌리는 판» 이 있다고 읽는다. 남는 높이는
          서랍이 준다(`realPane` 의 `flexGrow`). */}
      {reconBlocks(recon).map((b, i) => (
        <VStack key={b.name ?? i} gap={0.5} width="100%">
          {b.name ? (
            <Text font="caption" as="span" color="fgMuted">
              {`${b.name} 대사 — ${b.name} 달력`}
            </Text>
          ) : null}
          <ReconStack
            days={rollMarked(backtestDays(b), b.name, recon)}
            /* 열은 **두 다리의 합집합**이다 [OWNER 2026-09-04] — 민평과 IRS 의
               라벨이 어긋나서 한쪽 목록만 쓰면 다른 다리의 칸이 통째로 사라진다.
               다리별 대사가 아니면 이 함수가 `tenors` 를 그대로 돌려준다. */
            tenors={reconTenors(b)}
            defaultOrder="desc"
            /* 선물 표의 각주는 **백테스트의 그것**이다 [OWNER 2026-09-07] —
               같은 함수라야 「하루 일곱 줄」·「IRS 다리가 캐리·롤다운을 진다」·
               「쉰 날은 0 이고 다음 행이 두 밤을 진다」가 두 화면에서 같은 말로
               선다. 자산스왑 표는 종전대로 잘림만 말한다. */
            note={`${b.name ? futuresReconNote(b) : (reconNote(b) ?? '')}`
              .concat(rollNote(b.name, recon)).trim() || undefined}
          />
        </VStack>
      ))}
    </VStack>
  ) : null;

  const reconPaneLegs = sel && run ? (
    /* 서랍의 **남는 높이를 받는다** — `.sr-drawer-body` 가 열 flex 라
       (`flex: 1 · min-height: 0`) 창이 눌리면 이 패널도 같이 줄어야 한다. */
    <VStack gap={0.5} width="100%" flexGrow={1} minHeight={0}>
      {/* 무엇을 펴 놓았는지 — 서랍은 제목이 없으므로 이 줄이 그 일을 한다. */}
      <Text font="caption" as="span" color="fgMuted">
        {reconSub(sel, run)}
      </Text>
      {/* 높이를 **박지 않는다** — 서랍이 준 남는 높이를 받고, 스크롤(가로·세로)은
          CDS 가 표에 두른 컨테이너 하나가 진다. 종전에는 여기 `maxHeight: 30vh`
          가 박혀 있어 서랍이 눌린 판(실측 173px)에서 상자 바닥이 창 밖으로
          나갔고, **가로 스크롤바가 그 바닥에 달려 있어 같이 사라졌다**
          [OWNER 2026-09-02 — "왜 밑에 좌우로 드래그 할 수 있는 홀더 같은게
          없어?"]. 규칙과 근거는 `.sr-mr-drawertable`(theme/type.css). */}
      <Box className="sr-mr-drawertable" width="100%">
                <Table bordered={false}>
                  <TableHeader sticky>
                    <TableRow>
                      <TableCell as="th" scope="col">
                        <Text font="caption" as="span" color="fgMuted">날짜</Text>
                      </TableCell>
                      <TableCell as="th" scope="col">
                        <Text font="caption" as="span" color="fgMuted">구분</Text>
                      </TableCell>
                      {reconCols.map((c) => (
                        <TableCell key={c} as="th" scope="col" className="sr-num" justifyContent="flex-end">
                          {/* `caption` 이 아니라 `legal` 이다 — CDS 기본 테마의
                              `textTransform.caption = 'uppercase'` 가 「z」를 「Z」로,
                              「bp」를 「BP」로 만든다(실측 2026-08-28). 둘은 크기가
                              같고(0.8125rem) 중량·대문자화만 다르므로, **기호와
                              단위가 든 머리**는 `legal` 이 맞다 — `rv/SectorLane`
                              이 같은 근거로 정한 판례다. 이 표는 단위가 곧 검산의
                              전제라(감도 ₩/bp × Δbp) 대문자 BP 는 오식이다. */}
                          <Text font={headFont(c)} as="span" color="fgMuted" noWrap>{c}</Text>
                        </TableCell>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {reconRows.map(({ p, i }) => (
                      <ReconDay
                        key={p.t}
                        p={p}
                        word={eventWord(events.get(i), p.hold !== 0)}
                      />
                    ))}
                    <TableRow>
                      <TableCell>
                        <Text font="label1" as="span" noWrap>합계</Text>
                      </TableCell>
                      <TableCell>
                        {/* 「값」 칸이 줄마다 단위가 다르므로(₩/bp · bp · ₩) 합계
                            줄에서도 **무엇인지 말한다** — 여기 서는 것은 Δ 뿐이다
                            (2026-09-03 감사: 이름표 없는 숫자가 서 있었다). */}
                        <Text font="label1" as="span" color="fgMuted" noWrap>
                          {`${sel.bars}봉 · Δ`}
                        </Text>
                      </TableCell>
                      {/* 「값」 칸에는 **거래의 Δ 합계**가 선다. 다리 줄들이 그
                          칸을 세 단위로 쓰지만(₩/bp · bp · ₩) 합계에서 더할 수
                          있는 것은 Δ 뿐이고, 마스크된 롤이 몇 봉이었는지도 여기
                          붙는다 — 「청산 − 진입」과 이 값이 갈리는 이유다. */}
                      <TableCell className="sr-num" justifyContent="flex-end">
                        <Text font="label1" as="span" tabularNumbers noWrap>
                          {fmtBp(sel.dv, 2)}
                          {sel.masked ? <RollMark n={sel.masked} /> : null}
                        </Text>
                      </TableCell>
                      {/* 레벨·z 는 더할 수 있는 양이 아니다 — 진입 → 청산으로
                          적는다. 레벨 두 끝의 차가 곧 Δ 합계다(bp 계열에서 —
                          선물은 % 라 100배 갈리고, 그 사실은 거래 표 머리의
                          주석이 진다). */}
                      <ReconNum v={sel.mtm} kind="won" head />
                      <ReconNum v={sel.carry} kind="won" head />
                      <ReconNum v={sel.cost} kind="won" head />
                      <ReconNum v={sel.pnl} kind="won" tone head />
                      <ReconNum v={sel.pnl} kind="won" tone head />
                    </TableRow>
                  </TableBody>
                </Table>
              </Box>
    </VStack>
  ) : null;

  /* 대사 칸이 무엇을 세우나 [OWNER 2026-09-03].
       BSS   → 실가격 자산스왑 대사. 못 세우면 **왜인지만** 적고 비워 둔다.
       선물  → 자산스왑이 아니므로 다리 표(`ReconDay`)가 그대로 선다.
     빈 칸에 이유를 쓰는 것이 서랍의 규율이고(`WindowDrawer` 의 `unavailable`),
     여기서는 그 이유가 **서버 문장 그대로**다 — 화면이 다시 쓰면 갈린다. */
  /* 어느 표를 세우나 — **회계가 정한다**(`run.real`), 계열 종류가 아니라.
   *
   * 종전에는 `hasLegLevels`(= BSS 만 싣는 `govt` 필드가 있나)로 갈랐다. 그건
   * 「BSS 인가」의 대역이었고, 2026-09-04 에 선물 넷도 실가격 회계로 들어오면서
   * 거짓이 됐다 — 선물이 실가격으로 돌면서도 화면은 **폐기된 근사 표**를 그리고
   * 있게 된다. 판정은 그 봉의 돈이 어느 회계에서 나왔는가여야 한다. */
  const reconContent = !sel || !run
    ? null
    : run.real
      ? (recon?.available ? realPane : null)
      : reconPaneLegs;
  /* 고르개 옆 한 줄 — **서버가 실제로 채점한 구간**을 적는다. 화면이 달력을
     다시 세지 않는 이유는 `w0` 주석과 같다(두 자가 갈리면 카드와 곡선이
     다른 구간을 말한다). 전체 구간은 안 적는다 — 「전체」가 이미 그 뜻이다. */
  const spanNote = !perf || span === 'all'
    ? undefined
    : `${perf.from ?? '—'} 부터 ${perf.days.toLocaleString()}봉 — 성과·최적화가 이 구간에서 채점돼요.`;

  /* ── 근사 최적화 절 [OWNER 2026-09-04 — "전략 실험시에 근사 최적화 세트를
     바탕으로 결과를 보여주고, 그 밑에 TOP 5 조건을 매트릭스로"] ─────────────

     격자는 다섯 노브의 **프리셋 전부**(3×3×3×3×2 = 162칸)이고 순위 기준은
     화면이 고른다(서버는 칸마다 지표를 다 실어 보낸다 — 기준을 바꿀 때마다
     같은 격자를 다시 돌 이유가 없고, 「기준을 바꾸면 1등이 바뀐다」는 사실
     자체가 이 표가 말해야 하는 것이라 그 전환은 즉각이어야 한다).

     **1등 카드와 TOP 5 표를 같이 세운다.** 1등만 적으면 「그 칸이 얼마나
     외로운가」를 못 말한다 — 2등과 3% 차이인 1등과 두 배 차이인 1등은 같은
     숫자가 아니고, 그 차이가 곧 그 칸의 신뢰도다(내렸던 이웃 칸 표가 재던
     것이 그것이었다). 그래서 표에는 **지금 칸의 순위**도 같이 선다.

     회계가 머리 카드와 다를 수 있다는 사실은 각주가 말한다 — 162칸을 실가격
     으로 매기면 못 돌아서 격자는 늘 엔진 근사다. */
  /* 근사 최적화 절은 **공유 부품**이다 [2026-09-07] — 통합 장부가 같은 표를
     세우게 되면서 `OptimizePane` 으로 갈라 냈다. 이 창이 정하는 것은 문장 둘
     (안내·경고)뿐이고 나머지는 서버가 가른다(라우트가 둘). */
  const optPane = !run ? null : (
    <OptimizePane
      opt={opt}
      error={optError}
      running={optRunning}
      rankKey={rankKey}
      onRankKey={setRankKey}
      span={span}
      headReal={run.real}
      onRun={runAuto}
      onAdopt={adopt}
      currentParams={run.params}
      intro={'격자를 아직 못 돌렸어요 — 룩백 3 × 진입 3 × 청산 3 × 손절 3 × 진입 '
        + '규칙 2 = 162칸을 이 구간에서 채점해요. 비용·Delta 와 실전 규칙은 안 '
        + '흔들어요: 그 둘은 통상값이 아니라 그날의 호가폭이고 이 데스크의 포지션 '
        + '크기예요.'}
    />
  );

  const reconWhy = !run
    ? '재현이 끝나면 거래가 서고, 거래 줄을 누르면 하루씩 대사가 열려요.'
    : !sel
      ? '거래 줄을 누르면 하루씩 대사가 서요 — 실제 가격기로 다시 세워서 재요.'
      : run.real && recon === null
        ? '대사를 재는 중이에요 — 실제 가격기로 다시 세우고 있어요.'
        : run.real && recon && !recon.available
          ? recon.why
          : undefined;



  return (
    <FloatingWindow
      windowKey="mrstrategy"
      title="전략 실험"
      width={1120}
      /* 창 머리 부제는 **caption**(Backtest 창의 「{asOf} 종가까지」와 같은 급).
         종전 `legal` 은 크기는 같고 중량만 낮아, 두 창을 나란히 놓으면 같은
         자리의 같은 성격 문장이 다른 굵기로 섰다. */
      aside={
        <Text font="caption" as="span" color="fgMuted" noWrap>
          첫 PMS 의 z-스코어 규칙 재현이에요 — 투자판단이 아니에요.
        </Text>
      }
      onClose={onClose}
      drawerOpen={drawerOpen}
      onDrawerOpenChange={setDrawerOpen}
      drawer={[
        {
          id: 'recon',
          label: '일별 대사',
          content: reconContent,
          /* 왜 비었는지를 그 자리에서 말한다(서랍의 규율). 민평 밖 거래와
             선물 계열은 이유가 서버 문장 그대로 온다 — 위 `reconWhy`. */
          unavailable: reconWhy,
        },
        {
          /* **대사와 같은 위계** [OWNER 2026-09-03 — "일별대사와 일별레벨은
             동일한 위계임"]. 대사는 「얼마나 벌었나」, 이 칸은 「어디에
             있었나」다 — 하위 탭이 아니라 형제 탭이다. */
          id: 'levels',
          label: '일별 레벨',
          content: levelPane,
          unavailable: run
            ? '거래 줄을 누르면 그 구간의 레벨·z·다리 레벨이 하루씩 서요.'
            : '재현이 끝나면 거래가 서고, 거래 줄을 누르면 레벨이 하루씩 열려요.',
        },
      ]}
    >
      {/* 창 몸통 리듬은 **Backtest 창과 한 값**이다(`BacktestWindow.tsx`
          `<VStack gap={2} padding={2}>`) — 떠 있는 창 둘이 같은 위계인데 안쪽
          여백이 다르면 나란히 놓았을 때 그 사실이 먼저 보인다(얼라인 5). */}
      <VStack gap={2} padding={2} width="100%">
        {/* 노브 두 줄은 **공용**이다(`KnobBar.tsx`) — 통합 장부 창과 같은 것을
            쓴다. 갈라 낸 근거는 그 파일 머리에 있다. */}
        <MrKnobBar
          lead={label}
          knobs={knobs}
          onChange={set}
          onRun={runAuto}
          running={running || optRunning}
          /* 구간은 **전역 설정값**이라 노브 줄 위에 선다 [OWNER 2026-09-04].
             결과가 있어야 「언제부터」를 말할 수 있으므로 안내 문장은 실행
             뒤에만 붙는다 — 없으면 고르개만 서고 그것도 맞는 화면이다. */
          span={span}
          onSpanChange={setSpan}
          spanNote={spanNote}
        />
        {/* 상태 문구의 활자는 **Backtest 와 한 벌**이다 — 안내·빈 상태는
            `body` 뮤트, 오류는 `body` + `.sr-up`(앱 공통 오류 문법: 백테스트·
            Main 미리보기가 같은 것을 쓴다). 종전에는 셋 다 `legal` 맨 잉크라
            «실행하지 못했어요» 가 각주처럼 조용히 서 있었다. */}
        {stale ? (
          /* 조용한 재계산 금지 — 원본의 stale 배너 + 마커 숨김 규율 그대로. */
          <Text font="body" as="p" color="fgMuted">
            설정이 실행과 달라요 — 「다시 돌리기」를 눌러야 아래 숫자에 반영돼요. 진입 마커는 숨겼어요.
          </Text>
        ) : null}
        {error ? (
          <Text font="body" as="p" className="sr-up">
            실행하지 못했어요 — {error}
          </Text>
        ) : null}

        {!run ? (
          <Text font="body" as="p" color="fgMuted">
            {/* 표본 구간을 **박아 두지 않는다** — 2026-08-28 에 출처를 옮기며
                2020~ 이 2014~ 가 됐고, 그때 이 문장만 옛 구간을 말하고 있었다.
                구간은 실행 결과가 진다(아래 「종가」·차트 축). */}
            {/* 자동 흐름이라 «누르면» 이 아니다 [OWNER 2026-09-09] — 창을 열면
                격자 162칸이 돌고 그 1등 조건으로 과거 전체를 재현한다. 무엇을
                기다리는지 화면이 말한다: 격자와 재현은 다른 기다림이다. */}
            {optRunning ? '최적화 격자 162칸을 이 구간에서 채점하는 중이에요…'
              : running ? '1등 조건으로 이 종목의 과거 전체를 재현하는 중이에요…'
              : '창을 열면 격자부터 돌아요.'}{' '}당일 종가 체결 규약이라 체결
            가능성은 담보하지 않아요.
          </Text>
        ) : (
          <>
            {/* ── 성과 — **절대수익형 지표 열둘** [OWNER 2026-09-04 — "샤프가
                   아니라 절대수익형펀드(헤지펀드)에서 사용하는 성과지표 가져와서
                   사용해주기"]. 부품은 이 앱의 스트립(`ui/Stat.tsx`) 그대로다.

                   **Sharpe 가 내려갔다.** 그 값은 계약과 엔진에 남아 있고(적합성
                   벡터가 잠그고 있다) 화면만 안 읽는다 — 실전 규칙 다섯·이웃 칸을
                   내릴 때와 같은 규율이다. 왜 σ 가 아니라 낙폭·하방편차인지는
                   서버 `mrmetrics.py` 머리가 진다.

                   **수는 전부 고른 구간 것이다.** 열둘이 `perf` 하나에서 나오므로
                   구간을 바꾸면 열둘이 같이 움직인다 — 한 칸만 전체 기간이면
                   그 카드가 조용히 딴 구간을 말하게 된다.

                   표기는 이 리포 문법(억/만), 방향색은 손익에만 — 낙폭은 늘
                   음수라 색이 정보를 더하지 않는다. 비율은 **두 자리**다(원/원
                   이라 문헌의 수익률 기반 값과 크기를 직접 비교하면 안 되고,
                   그 사실은 열 머리 옆 각주가 말한다). */}
            {!perf ? (
              /* 구 백엔드 — 조용히 `summary`(전체 기간)로 떨어지지 않는다.
                 그러면 화면이 전체 기간의 수를 이 구간의 수인 것처럼 말한다. */
              <Text font="body" as="p" color="fgMuted">
                구간별 성과는 새 백엔드가 필요해요 — 지금 백엔드는 전체 기간
                하나만 보내고 있어요.
              </Text>
            ) : (
            <HStack className="sr-stats" width="100%" flexWrap="wrap">
              <StatColumn title="성과">
                <Stat
                  label="총손익"
                  value={fmtKrw(perf.totalPnl)}
                  tone={perf.totalPnl > 0 ? 'up' : perf.totalPnl < 0 ? 'down' : undefined}
                  note={span === 'all' ? undefined : MR_SPAN_LABEL[span]}
                />
                <Stat label="최대 낙폭" value={fmtKrw(-perf.maxDrawdown)} />
                {/* 낙폭의 **길이** — 깊이만 적으면 「얼마나 오래 물속이었나」를
                    화면이 안 말한다. 골에서부터 센다(고점은 지나고 나서야
                    고점인 줄 안다 — `mrmetrics._drawdowns` 의 그 근거). */}
                <Stat
                  label="회복일"
                  value={perf.recoveryDays == null ? '—' : `${perf.recoveryDays}일`}
                  note={perf.recoveryDays == null
                    ? '낙폭이 없었어요'
                    : perf.recovered ? '골에서 전고점까지' : '아직 회복 못 했어요'}
                />
                <Stat
                  label="승률"
                  value={perf.winRate == null ? '—' : `${Math.round(perf.winRate * 100)}%`}
                  /* 분모를 여기서 말한다 [OWNER 2026-08-26]. 미청산 다리는 원본
                     규약대로 거래·승률에 안 들어가는데(총손익에는 들어간다),
                     카드가 그 사실을 안 적으면 열려 있는 손실 포지션이 승률에서
                     조용히 사라진다 — 실측 80% 는 15건 중 12건이었고 빠진 한
                     건은 표본 두 번째로 나쁜 −600만이었다. */
                  note={!run.open ? undefined
                    : run.params.countOpen ? '미청산 1건 포함' : '미청산 1건 제외'}
                />
                {/* 거래 수는 **구간 안에서 청산된 것**이다 — 곡선의 구간
                    순손익에 든 거래가 표에도 있어야 한다(`shownTrades` 와 같은
                    규약). 전체와 다르면 그 사실을 note 가 적는다. */}
                <Stat
                  label="거래"
                  value={String(perf.numTrades)}
                  note={perf.numTrades === run.summary.numTrades
                    ? undefined : `전체 ${run.summary.numTrades}건`}
                />
                {run.open ? (
                  <Stat
                    label="미청산"
                    value={fmtKrw(run.open.pnl)}
                    tone={run.open.pnl > 0 ? 'up' : run.open.pnl < 0 ? 'down' : undefined}
                    note={`${run.open.entryT} 진입`}
                  />
                ) : null}
              </StatColumn>
              {/* 분모가 저마다 다른 일곱 — 두 창이 **같은 부품**을 세운다
                  (`parts.RiskAdjusted`). 통합 장부도 같은 일곱을 쓰게 되면서
                  여기서 갈라 냈다 [2026-09-07] — 두 벌이면 한쪽만 낡는다. */}
              <RiskAdjusted perf={perf} />
              {/* 누적 분해 [OWNER 2026-09-09 — "누적 채권 + 스왑 손익을 롤다운
                  캐리로 분해해서 보여주기"]. **구간을 따라간다**(`perf.split`) —
                  옆 열들과 같은 구간이어야 한 줄로 읽힌다. 두 창이 같은 부품을
                  세운다(`parts.SplitColumn`). */}
              <SplitColumn split={perf.split} />
              <StatColumn title="조건">
                {/* 비용이 봉마다 다르면 「편도 몇 bp」가 한 숫자로 안 나온다 —
                    실제로 문 범위와 중앙값을 적는다. 상수 하나로 뭉개면 화면이
                    실제로 낸 비용을 감추게 된다. */}
                <Stat
                  label="비용"
                  value={run.cost.model === 'flat'
                    ? `편도 ${run.cost.bp}bp`
                    : `편도 ${run.cost.lo}~${run.cost.hi}bp`}
                  note={run.cost.model === 'dynamic' ? `동적 · 중앙 ${run.cost.mid}bp` : undefined}
                />
                {/* 손익분기 — 노브를 돌려 0 을 찾는 대신 닫힌형으로 답한다
                    (`mrbacktest.breakeven_cost_bp`). 「이 구성이 얼마짜리
                    호가폭까지 견디는가」 는 비용 노브의 값보다 먼저 알아야 하는
                    사실이고, 그걸 모르면 비용 기본값이 곧 결론이 된다. */}
                {/* 손익분기도 **이 구간의 수**다 [OWNER 2026-09-04]. 구간
                    안에서 문 비용 위의 닫힌형이라(`mrmetrics.score` 의 그 산술)
                    전체 기간의 값과 다르고, 달라야 맞다 — 성과가 구간을 따라가는데
                    「이 성과가 견디는 호가폭」만 전체 기간이면 두 칸이 딴 구간을
                    말한다. 고정 비용 판은 bp 로, 동적 비용 판은 «그 경로의 몇 배»
                    로 적는다(동적에서는 「몇 bp」가 한 숫자로 안 나온다). */}
                {run.cost.model === 'flat' && perf.breakevenCostBp != null ? (
                  <Stat
                    label="손익분기 비용"
                    value={`편도 ${perf.breakevenCostBp.toFixed(2)}bp`}
                    tone={perf.breakevenCostBp <= run.params.costBp ? 'down' : undefined}
                    note={
                      perf.breakevenCostBp <= run.params.costBp
                        ? '지금 비용에서 이미 손실'
                        : `여유 ${(perf.breakevenCostBp - run.params.costBp).toFixed(2)}bp`
                    }
                  />
                ) : perf.breakevenCostMult != null ? (
                  /* 동적 비용 판 — 「몇 bp」가 아니라 «이 경로의 몇 배» 다.
                     여기가 비어 있으면 비용 모델을 바꾸는 순간 손익분기가
                     화면에서 사라진다(실측 2026-08-28). */
                  <Stat
                    label="손익분기 비용"
                    value={`지금 경로의 ${perf.breakevenCostMult.toFixed(1)}배`}
                    tone={perf.breakevenCostMult <= 1 ? 'down' : undefined}
                    note={perf.breakevenCostMult <= 1
                      ? '지금 비용에서 이미 손실'
                      : `편도 ${(run.cost.model === 'dynamic'
                          ? run.cost.mid * perf.breakevenCostMult
                          : run.params.costBp * perf.breakevenCostMult).toFixed(2)}bp 중앙 기준`}
                  />
                ) : null}
                {/* 액면 병기 [OWNER 2026-09-02] — Delta 노브는 DV01 이고 주문
                    단위는 억이다. 환산은 서버(`principal` — 지금 커브 pv01 하나의
                    근사)가 하고, 화면은 근사임을 같이 적는다. 선물은 원금이
                    없어(증거금·일일정산) note 가 그 사실을 말한다.

                    **라벨이 「명목」에서 「Delta」로 바뀌었다** [OWNER 2026-09-04].
                    이 칸의 단위는 처음부터 ₩/bp 였는데 「명목」은 액면을 가리키는
                    말이라, 바로 옆 note 의 「액면 약 35.7억」과 한 카드 안에서
                    충돌하고 있었다 — 근거는 `KnobBar` 의 그 자리에. */}
                <Stat
                  label="Delta"
                  value={`${run.params.notional.toLocaleString()}원/bp`}
                  /* `null` 은 「그 환산을 못 세웠다」는 서버의 답이고,
                     `undefined` 는 이 필드를 모르는 **구 백엔드**다(§6 ⑥ 의 그
                     배포 순서 함정) — 모르면 조용히 비운다.

                     ⚠ 종전에는 null 에 「선물은 액면 환산이 없어요」를 적었다.
                     2026-09-04 부터 **선물도 액면으로 환산한다**(선물 DV01 —
                     `futures.face_for_dv01`), 그래서 그 문장은 거짓이 됐다. */
                  /* ⚠ null 의 뜻이 **둘**이다 [2026-09-09]: 못 세운 것과, 한
                     숫자로는 못 적는 것(커브·플라이는 다리마다 액면이 다르다).
                     둘을 같은 문장으로 적으면 화면이 「환산 실패」라고 거짓말을
                     한다 — 사유가 오면 그 사유가 이긴다(서버 문장 그대로). */
                  note={run.principal
                    ? `액면 약 ${fmtEok(run.principal.krw)} (지금 커브)`
                    : run.principalNote ? '다리마다 달라요 (아래 각주)'
                    : run.principal === null ? '액면 환산을 못 세웠어요' : undefined}
                />
                <Stat label="종가" value={run.asof ?? '—'} />
                {/* 방향은 노브가 아니라 사실이라 「조건」에 선다 — 이 데스크가
                    실제로 할 수 있는 거래가 무엇인지가 성과의 전제다. */}
                <Stat label="방향" value={dirStat} />
                {run.dirs.why ? (
                  <Stat label="막힌 진입" value={`${run.dirs.blocked.spells}회`} />
                ) : null}
                {/* 필터가 지운 신호는 **따로** 센다 — 방향은 데스크의 제약이고
                    필터는 우리가 고른 것이라, 한 숫자로 합치면 선택의 대가가
                    제약 뒤에 숨는다. 필터를 켰는데 0 이면 그것도 사실이다
                    (실측: 변동성 상위 10% 는 검증 창에서 한 건도 안 막았다). */}
                {run.params.regime !== 'none' ? (
                  <Stat
                    label="필터가 지운 진입"
                    value={`${run.gated.spells}회`}
                    note={run.gated.spells === 0 ? '한 건도 안 막았어요' : `${run.gated.days}일`}
                  />
                ) : null}
              </StatColumn>
            </HStack>
            )}

            {/* ── 근사 최적화 [OWNER 2026-09-04] — 고르개는 노브 줄로 올라갔다
                (`KnobBar` 의 구간 줄). 여기 있던 「표시만 자른다」 문장은
                은퇴했다: 이제 자르는 것이 표시가 아니라 채점이다. */}
            {optPane}

            {/* ── 차트 셋 = **LINKED PAIR 의 세로 결**(Backtest `LinkedCharts`).
                   같은 `dates` 배열과 `useStackedScales`(값축 폭이 형제 최광폭
                   으로 수렴)로 픽셀이 맞고, **x 라벨은 맨 위가 지고 나머지는
                   숨긴다** — 같은 눈금을 세 번 그리면 그게 다른 축인 줄 읽힌다.
                   십자선은 `syncIndex` 로 반대쪽 차트에 건네, 한 차트를 짚으면
                   나머지 둘의 같은 날에 선이 선다(Backtest 의 그 문법). */}
            <VStack gap={2} width="100%">
              <Panel title="가격 · SMA · 밴드" sub={`밴드 = 평균 ±${run.params.entryZ}σ`}>
                <Box
                  className="sr-plot"
                  width="100%"
                  onMouseMove={(e: React.MouseEvent<HTMLDivElement>) => placeReadout(e.currentTarget, e.clientX)}
                  onMouseLeave={() => setIdx(null)}
                >
                  <TimeChart
                    height={CHART_H}
                    accessibilityLabel={`${label} 가격과 밴드`}
                    dates={winDates}
                    lines={priceLines}
                    markLines={evLines}
                    onHoverIndex={(i) => setIdx(i == null ? null : { chart: 'price', i })}
                    /* 캔버스에는 읽을 DOM 이 없다 — 짚은 봉을 문장으로 만들어
                       `.sr-a11y-only` 의 aria-live 줄에 보낸다(CLAUDE.md 규칙 7·
                       Main 미리보기 `scrubLabel` 의 그 자리). 종전에는 세 차트
                       전부 이 문장이 없어 스크린리더에 아무 말도 안 했다. */
                    hoverLabel={(i) => scrubWord(i, 'price')}
                    syncIndex={idx && idx.chart !== 'price' ? idx.i : null}
                    {...stack}
                  />
                  {idx?.chart === 'price' && winPoints[idx.i] ? (
                    <ReadoutCard title={winPoints[idx.i]!.t}>
                      <ReadoutLevel k="값" v={winPoints[idx.i]!.v} unit={unit} />
                      <ReadoutLevel k="중심선" v={winPoints[idx.i]!.ma} unit={unit} />
                      <ReadoutLevel k="상단" v={winPoints[idx.i]!.up} unit={unit} />
                      <ReadoutLevel k="하단" v={winPoints[idx.i]!.lo} unit={unit} />
                      {/* 밴드에 대해 지금 어디인지 — 진입 규칙이 보는 바로 그 사실.
                          「밴드 복귀」 판에서는 이 줄이 신호의 전제다. */}
                      <ReadoutFact
                        k="상태"
                        v={bandWord(winPoints[idx.i]!.out, winPoints[idx.i]!.outRun)}
                      />
                    </ReadoutCard>
                  ) : null}
                </Box>
              </Panel>

              <Panel
                title="z 오실레이터"
                sub={
                  stale
                    ? `진입 ±${run.params.entryZ}σ · 마커 숨김`
                    : `진입 ±${run.params.entryZ}σ · ${entryWord(run.params.entryMode)}` +
                      ` · 진입 ${entryCount(run)} · ${exitTally(run)}`
                }
              >
                <Box
                  className="sr-plot"
                  width="100%"
                  onMouseMove={(e: React.MouseEvent<HTMLDivElement>) => placeReadout(e.currentTarget, e.clientX)}
                  onMouseLeave={() => setIdx(null)}
                >
                  <TimeChart
                    height={CHART_H_SUB}
                    accessibilityLabel={`${label} z-스코어`}
                    dates={winDates}
                    lines={zLines}
                    priceLines={zBands}
                    markers={evMarkers}
                    markLines={evLines}
                    onHoverIndex={(i) => setIdx(i == null ? null : { chart: 'z', i })}
                    hoverLabel={(i) => scrubWord(i, 'z')}
                    syncIndex={idx && idx.chart !== 'z' ? idx.i : null}
                    hideTimeAxis
                    {...stack}
                  />
                  {idx?.chart === 'z' && winPoints[idx.i] ? (
                    /* 종전에는 z 한 줄뿐이었다 — 「이 봉에 무슨 일이 있었나」를
                       차트가 말하지 못해 거래 표와 눈으로 대조해야 했다. */
                    <ReadoutCard title={winPoints[idx.i]!.t}>
                      <ReadoutLevel k="z" v={winPoints[idx.i]!.z} unit={'ratio' as Unit} />
                      <ReadoutFact
                        k="상태"
                        v={bandWord(winPoints[idx.i]!.out, winPoints[idx.i]!.outRun)}
                      />
                      {/* posWord 는 전체 인덱스를 받는다 — 거래·미청산 탐색이
                          전체 목록 위라서다. 표시 창만큼 옮겨 되돌린다. */}
                      <ReadoutFact k="포지션" v={posWord(run, idx.i + w0)} />
                      <ReadoutMoney k="그날" v={winPoints[idx.i]!.pnl} />
                    </ReadoutCard>
                  ) : null}
                </Box>
              </Panel>

              <Panel
                title="누적 손익"
                /* 구간 표시면 머리도 구간을 말한다 — 곡선이 구간 시작 0 재기준
                   인데 머리가 12년 합을 적으면 둘이 딴 그림이 된다. 「걸친」은
                   청산이 구간 안인 거래다(winFrom 주석 — 곡선의 구간 순손익에
                   든 거래가 표에도 있어야 한다). 전체 순은 옆에 남긴다: 조각과
                   전체가 같은 곡선임을 머리가 잇는다. */
                sub={span === 'all'
                  ? `${run.summary.numTrades} 거래 · 순 ${fmtKrw(run.summary.totalPnl)}`
                  : `구간 순 ${fmtKrw(winPnl)} · 걸친 거래 ${shownTrades.length}건 · 전체 순 ${fmtKrw(run.summary.totalPnl)}`}
              >
                <Box
                  className="sr-plot"
                  width="100%"
                  onMouseMove={(e: React.MouseEvent<HTMLDivElement>) => placeReadout(e.currentTarget, e.clientX)}
                  onMouseLeave={() => setIdx(null)}
                >
                  <TimeChart
                    height={CHART_H_SUB}
                    accessibilityLabel={`${label} 누적 손익`}
                    dates={winDates}
                    lines={eqLines}
                    priceLines={zeroLine}
                    markers={evMarkers}
                    markLines={evLines}
                    onHoverIndex={(i) => setIdx(i == null ? null : { chart: 'eq', i })}
                    hoverLabel={(i) => scrubWord(i, 'eq')}
                    syncIndex={idx && idx.chart !== 'eq' ? idx.i : null}
                    hideTimeAxis
                    {...stack}
                  />
                  {idx?.chart === 'eq' && winPoints[idx.i] ? (
                    <ReadoutCard title={winPoints[idx.i]!.t}>
                      {/* 구간 표시면 곡선의 수(재기준)와 전체 누적을 **둘 다**
                          적는다 — 하나만 적으면 곡선과 판독이, 또는 판독과 성과
                          카드가 딴말을 한다. 전체 표시에서는 같은 수라 한 줄이다. */}
                      <ReadoutMoney
                        k={span === 'all' ? '누적' : '구간 누적'}
                        v={winPoints[idx.i]!.cum - baseCum}
                      />
                      {span !== 'all' ? (
                        <ReadoutMoney k="전체 누적" v={winPoints[idx.i]!.cum} />
                      ) : null}
                      <ReadoutMoney k="그날" v={winPoints[idx.i]!.pnl} />
                      <ReadoutFact k="포지션" v={posWord(run, idx.i + w0)} />
                    </ReadoutCard>
                  ) : null}
                </Box>
              </Panel>

              {/* 거래 표 — Main/Backtest 방언(CDS Table, 숫자는 label2 tabular
                  우측, 손익만 방향색 글자 [OWNER 2026-08-25 «기준을 Backtest 에»]).
                  **일별 대사는 이 패널이 아니라 창 바닥 서랍이 진다**(아래
                  `drawer` — Backtest 창의 그 문법). 종전에는 거래 줄을 누르면
                  이 패널의 내용이 대사표로 «바뀌었고», 그래서 목록과 대사를
                  동시에 볼 수 없었다. */}
              <Panel title="거래" sub={tradeSub}>
                {/* 표 높이는 차트 둘을 합친 값 — 풀폭이 된 뒤에도 200 이면 38거래에서
                    세 줄만 보인다. `overflow`·`position` 은 Box prop 이 없어 style 에 남는다. */}
                <Box style={{ position: 'relative', height: TABLE_H, overflow: 'auto' }} width="100%">
                  <Table bordered={false}>
                    {/* 거래가 수십 줄이라 머리가 따라와야 한다(Main 규칙). */}
                    <TableHeader sticky>
                      <TableRow>
                        {/* 일련번호 [OWNER 2026-09-02 — "건수"] — 실제 블로터와
                            줄 단위로 대사할 때 「몇 번째 거래」가 열쇠다. 번호는
                            **전체 실행 기준**이라 표시 구간을 잘라도 안 바뀐다 —
                            같은 거래가 구간마다 딴 번호면 번호가 아니다. */}
                        <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                          <Text font={headFont('#')} as="span" color="fgMuted">#</Text>
                        </TableCell>
                        <TableCell as="th" scope="col">
                          <Text font="caption" as="span" color="fgMuted">진입</Text>
                        </TableCell>
                        <TableCell as="th" scope="col">
                          <Text font="caption" as="span" color="fgMuted">청산</Text>
                        </TableCell>
                        <TableCell as="th" scope="col">
                          <Text font="caption" as="span" color="fgMuted">방향</Text>
                        </TableCell>
                        {/* 진입 시점 다리 레벨 [OWNER 2026-09-02] — 그날 데스크가
                            봤을 국고 커브·IRS 파·CD 91일(%). 값의 원천은 점
                            (서버 조인)이고 여기는 진입일을 찾아 적을 뿐이다.
                            BSS 에만 서는 조건부 열(「이탈 최대」의 그 문법). */}
                        {hasLegLevels ? (
                          <>
                            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                              <Text font="caption" as="span" color="fgMuted" noWrap>진입 국고</Text>
                            </TableCell>
                            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                              <Text font={headFont('진입 IRS')} as="span" color="fgMuted" noWrap>진입 IRS</Text>
                            </TableCell>
                            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                              <Text font={headFont('진입 CD')} as="span" color="fgMuted" noWrap>진입 CD</Text>
                            </TableCell>
                          </>
                        ) : null}
                        {/* 이탈 구간은 **「밴드 복귀」 판에서만** 열이 선다.
                            「이탈 즉시」 판에서는 진입 봉이 곧 이탈 첫 봉이라
                            최대 z 가 진입 z 와 같은 수다 — 같은 수를 두 열에
                            적으면 표가 없는 정보를 있는 척한다. */}
                        {run.params.entryMode === 'touch' ? (
                          <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                            <Text font={headFont('이탈 최대')} as="span" color="fgMuted" noWrap>이탈 최대</Text>
                          </TableCell>
                        ) : null}
                        {/* z 는 소문자다 — `caption` 은 대문자로 세운다(위 판례). */}
                        <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                          <Text font={headFont('진입 z')} as="span" color="fgMuted">진입 z</Text>
                        </TableCell>
                        <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                          <Text font={headFont('청산 z')} as="span" color="fgMuted">청산 z</Text>
                        </TableCell>
                        {/* 레벨·Δ [OWNER 2026-09-02 — "진입 레벨과 기준 노셔널과
                            같은 것들이 전부 나올 수 있게"] — 한 줄이 스스로
                            검산이 되는 열들이다: 청산 레벨 − 진입 레벨 ≈ Δ,
                            방향 × Δ × 명목(머리) ≈ 평가(대사표). Δ 는 늘 **bp**
                            다 — 선물 계열은 레벨이 % 라 둘이 100배 갈리는 그
                            단위 함정을 머리가 막는다. */}
                        <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                          <Text font="caption" as="span" color="fgMuted" noWrap>진입 레벨</Text>
                        </TableCell>
                        <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                          <Text font="caption" as="span" color="fgMuted" noWrap>청산 레벨</Text>
                        </TableCell>
                        <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                          <Text font={headFont('Δ (bp)')} as="span" color="fgMuted" noWrap>Δ (bp)</Text>
                        </TableCell>
                        {/* 순Δ [OWNER 2026-09-09 — "체결비용이 델타에는 반영되게
                            해야 직관적으로 델타와 손익을 비교 가능"]. Δ 는 시장이
                            움직인 것이고 순Δ 는 비용을 문 뒤 **우리가 가진** 것이다
                            — 두 열이 있어야 「청산 − 진입 = Δ」 검산과 「Δ 대 손익」
                            비교가 **동시에** 선다(산술은 서버 `mrmetrics.dv_net`). */}
                        <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                          <ThHelp
                            label="순Δ (bp)"
                            help="체결비용을 bp 로 되돌려 Δ 에 실은 값이에요 — 감도(방향 × Delta) × 순Δ = 평가 + 비용 이에요. Δ 는 시장이 움직인 것이고, 이 열은 비용을 문 뒤에 남은 것이에요."
                          />
                        </TableCell>
                        <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                          <Text font="caption" as="span" color="fgMuted">손익</Text>
                        </TableCell>
                        <TableCell as="th" scope="col">
                          <Text font="caption" as="span" color="fgMuted">사유</Text>
                        </TableCell>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {shownTrades.map(({ t, n }) => (
                        /* 줄을 누르면 그 거래의 일별 대사가 열린다 — rv 랭킹 표의
                           그 문법(«줄을 누르면 이력이 열려요»)이다. */
                        <TableRow
                          key={tradeKey(t)}
                          onClick={() => {
                            setOpenTrade(tradeKey(t));
                            setDrawerOpen(true);
                          }}
                          style={{ cursor: 'pointer' }}>
                          <TableCell className="sr-num" justifyContent="flex-end">
                            <Text font="label2" as="span" tabularNumbers color="fgMuted" noWrap>{n}</Text>
                          </TableCell>
                          <TableCell>
                            <Text font="label2" as="span" tabularNumbers noWrap>{t.entryT}</Text>
                          </TableCell>
                          <TableCell>
                            <Text font="label2" as="span" tabularNumbers noWrap>{t.exitT}</Text>
                          </TableCell>
                          <TableCell>
                            {/* 「롱/숏」이 아니라 **다리를 적는다** — BSS 에서 스프레드
                                롱은 국고 매도라 부호말은 정확히 반대로 읽힌다(북의
                                `directionLabel` 이 플라이에서 내린 그 판단). 이름은
                                서버가 계열마다 짓는다(§16). */}
                            <Text font="label2" as="span" noWrap>
                              {(t.dir > 0 ? run.dirs.plus : run.dirs.minus).short}
                            </Text>
                          </TableCell>
                          {hasLegLevels ? (
                            <>
                              <TableCell className="sr-num" justifyContent="flex-end">
                                <Text font="label2" as="span" tabularNumbers noWrap>
                                  {fmtReconLevel(pointAt.get(t.entryT)?.govt ?? null, '%' as Unit)}
                                </Text>
                              </TableCell>
                              <TableCell className="sr-num" justifyContent="flex-end">
                                <Text font="label2" as="span" tabularNumbers noWrap>
                                  {fmtReconLevel(pointAt.get(t.entryT)?.irs ?? null, '%' as Unit)}
                                </Text>
                              </TableCell>
                              <TableCell className="sr-num" justifyContent="flex-end">
                                <Text font="label2" as="span" tabularNumbers noWrap>
                                  {fmtReconLevel(pointAt.get(t.entryT)?.cd ?? null, '%' as Unit)}
                                </Text>
                              </TableCell>
                            </>
                          ) : null}
                          {run.params.entryMode === 'touch' ? (
                            <TableCell className="sr-num" justifyContent="flex-end">
                              <Text font="label2" as="span" tabularNumbers noWrap>
                                {t.peakZ == null ? '—' : `${t.peakZ.toFixed(2)}σ`}
                                {t.outDays == null ? '' : ` · ${t.outDays}일`}
                              </Text>
                            </TableCell>
                          ) : null}
                          <TableCell className="sr-num" justifyContent="flex-end">
                            <Text font="label2" as="span" tabularNumbers noWrap>{t.entryZ.toFixed(2)}σ</Text>
                          </TableCell>
                          <TableCell className="sr-num" justifyContent="flex-end">
                            <Text font="label2" as="span" tabularNumbers noWrap>
                              {/* 타임스탑 청산은 z=null 봉에 앉을 수 있다(api.ts). */}
                              {t.exitZ == null ? '—' : `${t.exitZ.toFixed(2)}σ`}
                            </Text>
                          </TableCell>
                          {/* 레벨은 계열의 자기 단위(각주의 「기준」), Δ 는 bp —
                              머리의 그 주석. 색은 손익에만(한 셀 한 채널). */}
                          <TableCell className="sr-num" justifyContent="flex-end">
                            <Text font="label2" as="span" tabularNumbers noWrap>{fmtReconLevel(t.entryV, unit)}</Text>
                          </TableCell>
                          <TableCell className="sr-num" justifyContent="flex-end">
                            <Text font="label2" as="span" tabularNumbers noWrap>{fmtReconLevel(t.exitV, unit)}</Text>
                          </TableCell>
                          <TableCell className="sr-num" justifyContent="flex-end">
                            {/* 롤을 지난 거래는 **청산 − 진입 ≠ Δ** 가 정상이다
                                [OWNER 2026-09-02 — 롤일 Δ 마스크]. 표식이 없으면
                                읽는 사람이 그 어긋남을 이 표의 결함으로 읽는다. */}
                            <Text font="label2" as="span" tabularNumbers noWrap>
                              {fmtBp(t.dv, 2)}
                              {t.masked ? <RollMark n={t.masked} /> : null}
                            </Text>
                          </TableCell>
                          {/* 구 백엔드는 이 열이 없다 — 0 으로 채우면 「비용이
                              없었다」가 되므로 '—' 다(공란 정책). */}
                          <TableCell className="sr-num" justifyContent="flex-end">
                            <Text font="label2" as="span" tabularNumbers noWrap>
                              {t.dvNet == null ? '—' : fmtBp(t.dvNet, 2)}
                            </Text>
                          </TableCell>
                          <TableCell className="sr-num" justifyContent="flex-end">
                            <Text
                              font="label2"
                              as="span"
                              tabularNumbers
                              noWrap
                              className={t.pnl > 0 ? 'sr-up' : t.pnl < 0 ? 'sr-down' : undefined}
                            >
                              {fmtKrw(t.pnl)}
                            </Text>
                          </TableCell>
                          <TableCell>
                            <Text font="label2" as="span" color="fgMuted" noWrap>
                              {WHY_WORD[t.why]}
                            </Text>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
              </Panel>
            </VStack>

            <Text font="legal" as="span" color="fgMuted">
              {fmtLevel(run.points.at(-1)?.v ?? null, unit)}
              {unitSuffix(unit)} 기준 ·{' '}
              {run.params.entryMode === 'touch'
                ? '밖에 있다가 밴드 선으로 돌아오는 봉에 들어가요 — 방향은 나갔던 쪽이 정해요.'
                : '|z|가 진입σ를 넘는 봉에 들어가요 — 밴드를 뚫는 그 봉이에요.'}{' '}
              거래 줄을 누르면 일별 대사가 열려요 — 하루가 다리마다 세 줄(KRD·Δbp·
              손익)이고 마지막이 종합이에요. 줄마다 −KRD × Δ = 손익 · 다리 손익을 더하면
              평가 · 세로합 = 거래 손익이에요. 표본 끝의 미청산 포지션은 **표의
              마지막 줄**(사유 「미청산」)로 서요 — 누적에는 늘 들어 있었고, 승률·
              거래 수에는 여전히 안 들어가요(원본 규약). 그 줄의 「청산」 칸은 청산이
              아니라 마지막 봉의 평가예요. 순Δ 는 체결비용을 bp 로 되돌려 Δ 에 실은
              값이라(감도 × 순Δ = 평가 + 비용) Δ 와 손익을 같은 자로 볼 수 있어요 —
              실가격 회계에서는 평가가 자산스왑 대사의 값이라 그 곱이 원 단위까지는
              안 닫혀요.
              {run.dirs.why
                ? ` ${run.dirs.why} 그래서 못 들어간 진입 신호가 ${run.dirs.blocked.spells}회(${run.dirs.blocked.days}일) 있어요.`
                : ''}
              {/* 캐리가 무엇인지 화면이 말한다 — 부호 기준이 한 방향이라 정의가
                  없으면 읽는 사람이 자기 방향으로 읽는다. 원본 PMS 산술에는 이
                  항이 없었다는 사실도 같이 적는다(재현 도구의 명구 의무). */}
              {run.carry.on && run.carry.defn
                ? ` 캐리는 ${run.carry.defn}${run.carry.funding ? `이고 조달은 ${run.carry.funding} 이에요` : ' 이에요'} — 원본 PMS 산술에는 없던 항이에요.`
                : ''}
              {/* 액면이 한 숫자가 아닌 계열(커브·플라이)은 **왜 없는지**를 적는다 —
                  빈칸으로 두면 화면이 「이 거래엔 액면이 없다」고 말한다. */}
              {run.principalNote ? ` ${run.principalNote}` : ''}
              {run.principal
                ? ` 액면은 거래마다 진입일 커브로 환산해요 — 그래야 「Delta ${run.params.notional.toLocaleString()}원/bp」가 모든 거래에서 같은 뜻이에요. 머리의 ${fmtEok(run.principal.krw)}은 「지금 세우면」이고, 거래마다의 액면은 그 거래의 대사표가 적어요(표본 안에서 ${run.real ? '5~16%' : ''} 움직여요).`
                : ''}
              {/* 다리 레벨의 출처와 항등 — 안 적으면 이 세 열이 어디서 온
                  값인지, 스프레드와 무슨 관계인지 화면만 보고는 알 수 없다. */}
              {hasLegLevels
                ? ' 다리 레벨(국고 커브·IRS 파·CD 91일)은 캐리와 같은 출처예요 — (국고 − IRS) × 100 = 레벨(bp)이 줄마다 그대로 닫혀요.'
                : ''}
              {/* 이 각주는 **국고 다리가 있는 계열**의 것이다 — 종전에는 창이
                  계열 종류를 몰라서 선물·커브에도 그대로 섰다(거짓). 구
                  백엔드(`kind` 없음)에서는 종전대로 적는다: 그때 유니버스는
                  BSS·선물뿐이고, 안 적는 쪽이 더 나쁜 거짓이다. */}
              {run.kind == null || run.kind === 'bss'
                ? ' 국고 다리는 민평(평가사 고시) 기준이에요 — 체결가로 재면 성과가 낮아질 수 있어요.'
                : ''}
            </Text>
          </>
        )}
      </VStack>
    </FloatingWindow>
  );
}
