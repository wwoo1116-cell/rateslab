'use client';

/* MR 두 창이 같이 쓰는 조각들 — 패널 상자·청산 사유의 우리말·짧은 날짜
 * [2026-09-01, 통합 밴드 워치].
 *
 * 낱개 창(`StrategyWindow`)과 통합 장부 창(`BookWindow`)이 같은 사건을 같은
 * 낱말로 불러야 한다. 「손절」을 한 창은 「손절」, 다른 창은 「스톱」이라 적으면
 * 두 표를 나란히 놓고 읽을 수 없다 — CLAUDE.md 얼라인 8(«같은 것은 한 번만
 * 만든다»)의 어휘 판이다.
 */

import { HStack, VStack } from '@coinbase/cds-web/layout';
import { TableCell } from '@coinbase/cds-web/tables';
import { Text } from '@coinbase/cds-web/typography';

import { fmtKrw } from '@/lib/krw';
import { Stat, StatColumn } from '@/ui/Stat';

import { MR_ENTRY_MODES, type MrPerf, type MrSplit, type MrStrategyParams,
  type MrStrategyTrade } from './api';

/** 청산 사유의 우리말 — 서버의 어휘를 화면에서 **한 번만** 옮긴다.
 *  우선순위가 곧 이름이다: 손절 > 청산 > 역신호 > 타임스탑. `미청산` 은 판정이
 *  아니라 상태다(팔지 않았고, 그래서 청산 비용도 안 물었다). */
export const WHY_WORD: Record<MrStrategyTrade['why'], string> = {
  stop: '손절',
  exit: '청산',
  reverse: '역신호',
  time: '타임스탑',
  open: '미청산',
};

/** 표 머리의 활자 기준 — **정의는 `lib/format` 에 있다**.
 *
 *  이 리포가 이미 정해 둔 기준이고(`StrategyWindow` 대사표 머리 주석·
 *  `BookWindow` 만기별 표 주석) 2026-09-02 에 함수가 됐다. 2026-09-09 에 `ui/ThHelp`
 *  (도움말이 달린 머리)도 같은 기준을 써야 해서 `lib/format` 으로 내려갔다 —
 *  `ui/` 가 `mr/` 를 임포트할 수는 없기 때문이다. 여기서는 **다시 내보내기만**
 *  한다: 이 레인의 파일들이 부르던 이름을 지키고, 정의는 하나로 남긴다. */
export { headFont } from '@/lib/format';

/** 짧은 날짜 — 구간 라벨용. `2020-01-02` → `20-01`. 칸이 좁아 연·월만 남긴다. */
export const ym = (iso: string): string => `${iso.slice(2, 4)}-${iso.slice(5, 7)}`;

export function Panel({
  title,
  sub,
  aside,
  children,
}: {
  title: string;
  sub?: string;
  /** 그 패널**만** 바꾸는 컨트롤이 서는 자리. 결과를 바꾸는 노브는 여기 오면
   *  안 된다 — 설정 줄에 있어야 「실행」이 그것을 삼킨다. 반대로 그림만 바꾸는
   *  것을 설정 줄에 두면 실행을 기다리게 만들고 stale 을 거짓으로 세운다. */
  aside?: React.ReactNode;
  children: React.ReactNode;
}) {
  /* **한 줄에 하나** [OWNER 2026-09-02 — 「세로 스택 정본화」]. 종전 값은
     `flexBasis: 50%` 였는데 gap 을 더하면 한 줄에 둘이 안 들어가 실제로는
     세로로 섰다 — 화면은 세로였고 주석만 「2×2 격자」라고 말하고 있었다
     (2026-09-02 디자인 감사가 그 어긋남을 잡았다). 정본을 화면 쪽으로
     맞춘다: Backtest 창의 세로 결(북 → 답 → 차트 쌍 → 서랍)과 같은 흐름이고,
     12년 시계열은 풀폭이 아니면 못 읽는다. */
  return (
    <VStack gap={0.5} width="100%" minWidth={0}>
      <HStack gap={1} alignItems="center" justifyContent="space-between" minHeight={24}>
        <Text font="label2" as="h3" noWrap>
          {title}
        </Text>
        <HStack gap={1} alignItems="center" minWidth={0}>
          {sub ? (
            <Text font="legal" as="span" color="fgMuted" noWrap>
              {sub}
            </Text>
          ) : null}
          {aside}
        </HStack>
      </HStack>
      {children}
    </VStack>
  );
}

/** 위험조정 비율 — **두 자리 고정**이고 못 잰 값은 «—» 다 [OWNER 2026-09-04].
 *
 *  `null` 은 「그 구간에서 그 지표가 안 선다」이지 「0 이다」가 아니다(낙폭이
 *  0 이라 Calmar 가 없는 칸, 손실 월이 없어 GPR 이 없는 칸). 0 으로 적으면
 *  화면이 「최악」이라고 말하는데 사실은 「최선이라 분모가 없다」인 경우가
 *  섞인다 — 그래서 카드의 note 가 왜 없는지를 같이 적는다.
 *
 *  두 자리인 이유는 이 수들이 **원/원**이라서다. 셋째 자리는 Delta 하나만 바꿔도
 *  움직이는 자리가 아니지만(비율은 Delta 에 불변) 칸 폭만 늘린다.
 *
 *  ⚠ 두 창이 같이 쓴다 [2026-09-07] — 낱개 창에 있던 것을 여기로 옮겼다.
 *  통합 장부도 같은 일곱을 세우게 되면서 두 벌이 될 자리였다(얼라인 8). */
export const fmtRatio = (v: number | null | undefined): string =>
  v == null ? '—' : v.toFixed(2);

/** 비율 한 칸 — 못 잰 값은 «—» 다(0 이 아니다 — `fmtRatio` 머리의 그 근거). */
export function NumCell({ v }: { v: number | null }) {
  return (
    <TableCell className="sr-num" justifyContent="flex-end">
      <Text font="label1" as="span" tabularNumbers noWrap>
        {fmtRatio(v)}
      </Text>
    </TableCell>
  );
}

/** **절대수익형 일곱** — 두 창이 같은 카드를 세운다 [OWNER 2026-09-04 · 2026-09-07].
 *
 *  분모가 저마다 다른 것이 이 열의 요점이다. 하나가 나쁘고 하나가 좋으면
 *  «어느 축에서» 를 묻게 되고, 그게 절대수익형 평가가 샤프 한 칸으로는 못
 *  하던 일이다.
 *
 *  못 잰 값은 «—» 이고 **왜 없는지**를 note 가 적는다 — 「손실 난 달이 없어요」
 *  와 「월 버킷이 모자라요」는 다른 사실인데 둘 다 null 이다.
 *
 *  단위는 **원/원**이다(AUM 이 없다) — 문헌의 수익률 기반 값과 크기를 직접
 *  비교하면 안 되고, 그 사실은 이 열을 감싸는 화면의 각주가 말한다. */
export function RiskAdjusted({ perf }: { perf: MrPerf }) {
  return (
    <StatColumn title="위험조정">
      <Stat
        label="Sortino"
        value={fmtRatio(perf.sortino)}
        note={perf.sortino == null ? '손실 난 날이 없어요' : '하방편차 · 연'}
      />
      <Stat
        label="Calmar"
        value={fmtRatio(perf.calmar)}
        note={perf.calmar == null ? '낙폭이 없었어요' : '연환산 ÷ 최대낙폭'}
      />
      <Stat
        label="Martin"
        value={fmtRatio(perf.martin)}
        note={perf.martin == null ? '낙폭이 없었어요' : '연환산 ÷ Ulcer'}
      />
      <Stat label="Ulcer" value={fmtKrw(-perf.ulcer)} note="RMS 낙폭" />
      {/* GPR 이 없는 이유가 둘이라 화면이 가른다 — 월 버킷이 모자란 것과
          손실 월이 하나도 없는 것은 다른 사실이다. */}
      <Stat
        label="GPR"
        value={fmtRatio(perf.gpr)}
        note={perf.gpr != null ? '월 버킷 · Schwager'
          : perf.gprMonths < 2 ? `월 버킷 ${perf.gprMonths}개라 못 세요`
          : '손실 난 달이 없어요'}
      />
      <Stat
        label="Omega"
        value={fmtRatio(perf.omega)}
        note={perf.omega == null ? '손실 난 날이 없어요' : 'θ=0 · 일별'}
      />
      <Stat
        label="Profit Factor"
        value={fmtRatio(perf.profitFactor)}
        note={perf.profitFactor == null
          ? (perf.numTrades ? '진 거래가 없어요' : '거래가 없어요')
          : '거래 기준'}
      />
    </StatColumn>
  );
}

/** **누적 분해** — 두 창이 같은 카드를 세운다 [OWNER 2026-09-09 — "누적 채권 +
 *  스왑 손익을 롤다운 캐리로 분해해서 보여주기"].
 *
 *  ## 정의는 v1 대사 엔진의 것이다 [OWNER 2026-09-09 — 「v1 대사 엔진 정의 이식」]
 *
 *  서버가 봉마다 이미 세워 둔 다섯을 더한 값이고(`backend/app/mrmetrics.py::split`),
 *  그 값은 `cashbond.book_recon` — 백테스트·시뮬 대사가 쓰는 바로 그 함수 — 에서
 *  온다. 그래서 이 앱의 세 화면이 「롤다운」을 같은 뜻으로 쓴다: 커브가 그대로인데
 *  잔존만기가 짧아져서 생긴 클린 가격 변화(전일 커브 위의 재평가), 캐리는 가만히
 *  있어 확정되는 현금흐름, 평가는 커브가 **움직여서** 생긴 잔여.
 *
 *  ## 구간을 따라간다
 *
 *  값은 구간 카드(`perf.split`)에서 오므로 옆의 일곱(`RiskAdjusted`)과 **같은
 *  구간**이다. 전체 기간의 분해를 구간 카드 옆에 세우면 두 칸이 딴 구간의 수다.
 *
 *  ## 없는 항은 «—» 다 — 0 이 아니다
 *
 *  엔진 근사 판에는 롤다운·조달이라는 항이 **아예 없다**. 0 으로 적으면 「그
 *  구간에 롤다운이 없었다」는 다른 말이 되고, 읽는 사람은 그 0 을 사실로 읽는다
 *  (이 리포의 공란 정책 — `fmtRatio` 머리와 같은 근거).
 *
 *  다섯을 더하면 구간 순손익이다. 그 항등이 이 카드의 자기검사이고, 서버 시험이
 *  같은 항등을 잰다(`tests/test_mrmetrics.py::test_split_parts_sum_to_the_cumulative`). */
export function SplitColumn({ split }: { split?: MrSplit }) {
  if (!split) return null;
  const money = (v: number | null, why: string) => ({
    value: v == null ? '—' : fmtKrw(v),
    note: v == null ? why : undefined,
    tone: v == null ? undefined : v > 0 ? ('up' as const) : v < 0 ? ('down' as const) : undefined,
  });
  /* 근사 판이면 그 사실을 **카드 안에서** 말한다 — 「왜 두 칸이 비었나」의 답이
     카드 밖에 있으면 읽는 사람이 못 찾는다. */
  const why = '엔진 근사라 이 항이 없어요';
  return (
    <StatColumn title="누적 분해">
      <Stat label="평가" {...money(split.mtm, why)} />
      <Stat label="캐리" {...money(split.carry, why)} />
      <Stat label="롤다운" {...money(split.rolldown, why)} />
      <Stat label="조달" {...money(split.funding, why)} />
      <Stat label="비용" {...money(split.cost, why)} />
      {/* 검산 줄 — 다섯을 더한 값이 곧 구간 순손익이다. 합을 적어 두면 눈으로
          닫을 수 있고, 안 닫히는 날이 있으면 그게 결함이라는 뜻이다. */}
      <Stat
        label="합"
        value={fmtKrw(split.total)}
        tone={split.total > 0 ? 'up' : split.total < 0 ? 'down' : undefined}
        note="다섯의 합 = 구간 순손익"
      />
    </StatColumn>
  );
}

/** 진입 규칙의 이름 — 목록이 어휘의 주인이라 여기서 다시 짓지 않는다. */
const entryWord = (mode: string): string =>
  MR_ENTRY_MODES.find((m) => m.v === mode)?.label ?? mode;

/** 조건 한 줄 — 「60일 · 2/0.5/3.5σ · 이탈 즉시」.
 *
 *  ## 왜 한 벌인가
 *
 *  이 문장이 서는 자리가 셋이 됐다 [2026-09-09]: 최적화 표의 「조건」 칸, 1등
 *  카드, 그리고 **설정 줄의 「조건」 읽기 칸**(노브 다섯이 내려간 자리). 셋이
 *  같은 실행을 다른 문장으로 말하면 화면이 스스로를 반박한다 — 캐논 얼라인 8.
 *
 *  ## 왜 이 순서·이 표기인가
 *
 *  순서는 규칙이 도는 순서다(룩백 → 진입 → 청산 → 손절 → 진입 규칙). σ 는
 *  **라벨이 진다** — 칸 안에 「진입 2σ · 청산 0.5σ · 손절 3.5σ」처럼 적으면 그
 *  글자가 조건보다 넓어지고, 조건 칸은 최적화 표에서 이미 가장 넓은 열이다.
 *  자릿수만 남기고 빗금으로 잇는다(2026-09-07 에 한 번 풀어 썼다가 되돌렸다). */
export function condWord(p: {
  lookback: number; entryZ: number; exitZ: number; stopZ: number; entryMode: string;
}): string {
  const n = (v: number) => Number(v.toFixed(1));
  return `${p.lookback}일 · ${n(p.entryZ)}/${n(p.exitZ)}/${n(p.stopZ)}σ · ${entryWord(p.entryMode)}`;
}

/** 두 조건이 **같은 칸**인가 — 격자의 한 칸과 지금 실행을 견준다.
 *
 *  서버도 `current` 플래그를 실어 보내지만 그것은 **질의에 실린 노브** 기준이다.
 *  2026-09-09 부터 창은 「격자를 돌린 뒤 1등을 채택해서 다시 실행」하므로, 질의
 *  시점의 노브와 지금 실행이 갈린다 — 그때 서버 플래그는 «직전 조건» 을 가리키고
 *  화면은 「지금 칸」을 틀린 줄에 세운다. 그래서 판정을 실행 결과(`run.params`)
 *  위에서 다시 한다. 이건 계산이 아니라 **다섯 값의 동일성**이라 §16 의 「브라우저는
 *  계산하지 않는다」에 걸리지 않는다. */
export function sameCond(
  a: { lookback: number; entryZ: number; exitZ: number; stopZ: number; entryMode: string },
  b: MrStrategyParams | undefined,
): boolean {
  if (!b) return false;
  return (a.lookback === b.lookback && a.entryZ === b.entryZ && a.exitZ === b.exitZ
    && a.stopZ === b.stopZ && a.entryMode === b.entryMode);
}
