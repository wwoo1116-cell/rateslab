'use client';

/* 투자자별 수급 — Strategy **네 번째 세입자** [OWNER 2026-10-16].
 *
 * 화면 문법은 Mean Reversion 면에서 가져왔다(조건 스트립 → 히어로 → 컨트롤 행 →
 * 좌 표 / 우 차트 → 사실 스트립). 근거와 함정은 `backend/app/flow.py` 머리에
 * 있고, 여기는 **읽고 칠하기만** 한다(§16).
 *
 * ## 이 면의 모양을 정한 것 셋
 *
 * ① **대분류는 순위가 아니라 대조다.** 수급은 영합이라 외국인과 기관계의 상관이
 *    −0.9996 이다 — 순위를 매기면 매일 같은 두 줄이 나온다. 그래서 위는 저울 한
 *    줄로 세우고, 순위는 기관계 세분이 진다.
 * ② **단위가 달라 한 축에 못 겹친다**(계약 대 백만원). 겹치면 이중축이 되고
 *    그건 이 리포가 외부 표준(FT Visual Vocabulary)으로 금지한 자리다 —
 *    그래서 겹치는 그림이 아니라 **갈라지는 면**이고 세그먼트가 그것을 가른다.
 * ③ **두 원천의 `asof` 가 다른 것이 정상이다** [OWNER 2026-10-19]. 현물이 늦게
 *    들어온다. 조건 스트립이 둘을 따로 적고, 어긋나는 것은 **경고가 아니다**.
 *
 * ## 2026-10-19 밤에 더한 것 셋 [OWNER]
 *
 * ④ **현물은 만기물로 갈린다**(전체·2~50년·물가). 종목→만기물은 서버가 푼다
 *    (`flow.py` §현물 만기물 ①) — 「전체」는 분리 전 화면과 같은 수다.
 * ⑤ **일별 그림의 주체를 표가 고르고, 그 위에 이동평균이 선다.** 평균은 서버가
 *    낸다(`series.ma`). 화면에 산술이 없어야 두 면이 같은 수를 말한다.
 * ⑥ **PD 인수 노브.** 발행시장 인수분이 자료에 없어서(입찰 당일 열 주체 합이 0)
 *    금융투자 몫을 사람이 정하고 서버가 더한다. 가정이라는 것을 `basis` 가 말한다.
 *
 * ## 2026-10-20 — 면 넷이 **하나**가 됐다 [OWNER]
 *
 * 「테너별 국고채 발행량이랑, 각 투자주체들이 어떻게 이를 담아가는지」가 요구였다.
 * 그 둘이 다른 면에 있으면 눈으로 이어야 한다 — 그래서 합쳤다.
 *
 * ⑦ **왼쪽은 테너 × (발행 + 주체) 한 표**(`FlowMatrix`). 행이 만기물, 첫 값 열이
 *    발행, 나머지 열 열이 주체다. 칸은 고른 구간의 합이고 맨 아랫줄 합계는 `ALL`
 *    바구니와 **같은 수**다(서버가 둘을 따로 세고 `test_flow` 가 맞댄다).
 * ⑧ **칸이 손잡이다** — 누르면 (만기물 × 주체) 둘을 한 번에 골라 오른쪽 일별
 *    그림(+이동평균)이 그 칸의 계열로 바뀐다. 열 머리를 누르면 만기물은 전체다.
 * ⑨ **선물 둘은 잠시 폐기, 발행 면은 접었다**(`FACES_SHOWN` 머리). 입찰 상세
 *    (응찰률·낙찰금리·수요 판정)는 `AuctionFact` 한 줄로 남았다. 주체별 순위표
 *    (`FlowTable`)는 지워지지 않고 **아래 전폭**으로 내려갔다 — 행렬에 없는
 *    「오늘이 평소보다 센가」(σ)를 그 표가 진다.
 *
 * ## 그림에 넷, 표에 전부
 *
 * 이 리포에는 N계열 범주형 팔레트가 없다 — 이름 있는 색이 방향 2 + 참조 4뿐이다.
 * 그래서 그림엔 최대 4계열(서버가 골라 보낸다)이고 열한 주체 전수는 표가 진다.
 * 계열 구분색 넷은 `--sr-flow-1..4`(Morgan Stanley 차트 팔레트 — 근거는
 * `theme/direction.css` 의 그 블록).
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Text } from '@coinbase/cds-web/typography';

import { TimeChart, useStackedScales, type TimeLine } from '@/chart/TimeChart';
import type { LwPalette } from '@/chart/palette';
import { BacktestUnavailable } from '@/lib/api';
import { fmtContracts, fmtEok, fmtJo } from '@/lib/format';
import { ChartReadoutStrip, slotChars, type StripSlot } from '@/ui/ChartReadoutStrip';
import { Cond } from '@/ui/Cond';
import { Field, NumField, Segmented } from '@/ui/ControlCard';
import { ErrorState, LoadingState } from '@/ui/DataState';
import { Stat, StatColumn } from '@/ui/Stat';

import {
  fetchFlowBoard, fetchIssuanceBoard, type CashTenor, type FlowBoard, type FlowSide,
  type FutTenor, type IssuanceBoard, type IssuanceUnit,
} from './api';
import { FlowLabWindow } from './FlowLabWindow';
import { FlowMatrix } from './FlowMatrix';
import { FlowTable } from './FlowTable';
import { SPAN_BARS, SPAN_OPTIONS, type Span } from './span';

/** 면 하나. 선물 둘·현물·발행. */
export type Face = 'fut3' | 'fut10' | 'cash' | 'issue';
const FACE: Record<Face, { label: string }> = {
  fut3: { label: '선물 3년' },
  fut10: { label: '선물 10년' },
  cash: { label: '현물' },
  issue: { label: '발행' },
};
const FUT_TENOR: Partial<Record<Face, FutTenor>> = { fut3: '3Y', fut10: '10Y' };

/** 화면에 **서는** 면 [OWNER 2026-10-20].
 *
 *  둘이 빠졌고 까닭이 다르다.
 *
 *  - **선물 둘은 「잠시 폐기」** 다. 코드와 라우트(`side=fut`)는 그대로 두고
 *    고를 자리만 뺐다 — 되돌리는 것이 이 배열에 두 글자를 더하는 일이어야 한다.
 *  - **발행은 접었다.** 공급이 이제 수급표의 첫 값 열이라(`FlowMatrix`) 면을
 *    따로 둘 까닭이 없다. 입찰 상세(응찰률·낙찰금리·수요 판정)는 고른 만기물의
 *    **사실 줄**로 왼쪽 카드 머리에 선다.
 *
 *  하나뿐이면 세그먼트를 아예 안 그린다 — 고를 것이 없는 컨트롤은 폭만 먹는다. */
const FACES_SHOWN: Face[] = ['cash'];

/** 현물 만기물 — 서버의 `CASH_TENORS` 와 같은 열쇠·같은 차례. */
const CASH_TENORS: { value: CashTenor; label: string }[] = [
  { value: 'ALL', label: '전체' },
  { value: '2Y', label: '2년' }, { value: '3Y', label: '3년' }, { value: '5Y', label: '5년' },
  { value: '10Y', label: '10년' }, { value: '20Y', label: '20년' }, { value: '30Y', label: '30년' },
  { value: '50Y', label: '50년' }, { value: '물가', label: '물가' },
];
const CASH_TENOR_LABEL = Object.fromEntries(CASH_TENORS.map((t) => [t.value, t.label])) as Record<CashTenor, string>;

/** 계열 구분색 넷. **순서가 곧 배정**이다 — 서버가 보낸 차례대로 입는다. */
const INK = ['--sr-flow-1', '--sr-flow-2', '--sr-flow-3', '--sr-flow-4'] as const;

/** 이동평균 선 넷의 **진하기**(%) — 창이 짧을수록 흐리다 [OWNER 2026-10-20].
 *
 *  색은 하나(`INK[2]` 바이올렛)고 진하기만 가른다. 누적 그림이 `INK` 넷을 이미
 *  주체에 쓰고 있어서 같은 네 색을 창에 또 쓰면 한 카드 안에서 같은 색이 두 가지를
 *  뜻한다. 그리고 진하기 차례가 `flow.WINDOW_TRUST` 와 같아서, **진한 선일수록
 *  믿을 만한 창**이라는 뜻이 덤으로 붙는다(Γ5·Γ20 은 잡음). */
const MA_INK = [42, 60, 80, 100] as const;

/** 대분류 **순매수 대조** — 받은 쪽과 낸 쪽을 한 막대에 [2026-10-19].
 *
 * 숫자 넷을 나란히 적으면 「넷이 있다」로 읽히고, 이 면이 말하려는 「한쪽이 산
 * 만큼 다른 쪽이 팔았다」가 안 보인다. 영합이라 **양쪽 폭이 늘 같고**, 그
 * 사실 자체가 그림이다.
 *
 * 폭은 각 주체의 **절댓값 몫**이다. 색은 부호(순매수 빨강·순매도 파랑) —
 * 계열 구분색이 아니라 방향색을 쓰는 자리다.
 */
function Balance({
  top, fmt, unit,
}: {
  top: { key: string; label: string; value: number }[];
  fmt: (v: number) => string;
  unit: string;
}) {
  const buy = top.filter((t) => t.value > 0);
  const sell = top.filter((t) => t.value < 0);
  const flat = top.filter((t) => t.value === 0);
  const side = (xs: typeof top) => xs.reduce((a, t) => a + Math.abs(t.value), 0);
  const total = Math.max(side(buy), side(sell), 1);
  const bar = (xs: typeof top, hue: string, align: 'flex-start' | 'flex-end') => (
    <HStack flexGrow={1} gap={0.25} justifyContent={align}>
      {xs.map((t, i) => (
        <Box
          key={t.key}
          height={14}
          borderRadius={100}
          style={{
            background: `var(${hue})`,
            opacity: i === 0 ? 1 : 0.45,
            flex: `${Math.max(Math.abs(t.value), total * 0.004)} 0 0`,
          }}
        />
      ))}
    </HStack>
  );
  return (
    <VStack gap={0.5} width="100%">
      <HStack gap={1} alignItems="baseline" justifyContent="space-between">
        <Text as="span" font="legal" color="fgMuted">받은 쪽</Text>
        <Text as="span" font="legal" color="fgMuted">낸 쪽</Text>
      </HStack>
      <HStack gap={0.5} width="100%" alignItems="center">
        {bar(buy, '--sr-up', 'flex-end')}
        {bar(sell, '--sr-down', 'flex-start')}
      </HStack>
      <HStack gap={1} alignItems="baseline" justifyContent="space-between" flexWrap="wrap">
        <Text as="span" font="label2" className="sr-up">
          {buy.map((t) => `${t.label} ${fmt(t.value)}`).join(' · ') || '—'}
        </Text>
        <Text as="span" font="label2" className="sr-down">
          {sell.map((t) => `${t.label} ${fmt(t.value)}`).join(' · ') || '—'}
        </Text>
      </HStack>
      <Text as="span" font="legal" color="fgMuted">
        합이 0 이에요 — 영합이라 순위가 아니라 대조로 봐요
        {flat.length > 0 ? ` · ${flat.map((t) => `${t.label} 0${unit}`).join(' · ')}` : ''}
      </Text>
    </VStack>
  );
}

/** 고른 만기물의 **직전 입찰** 한 줄 — 접은 「발행」 면이 남긴 것 [OWNER 2026-10-20].
 *
 *  표의 발행 열은 구간 합(금액)만 든다. 「그래서 그 입찰이 셌나」는 응찰률·낙찰금리·
 *  수요 판정이 말하는데, 그건 만기물마다 **한 건**이라 표의 열이 아니라 머리의
 *  사실 줄이 맞다(열로 넣으면 열두 열이 되고 행마다 같은 수가 반복된다).
 *
 *  판정 문구는 **서버가 지은 것**을 그대로 쓴다(`issuance_strength.annotate`) —
 *  화면이 등급을 다시 매기지 않는다. */
function AuctionFact({ unit, tenorLabel }: { unit: IssuanceUnit | null; tenorLabel: string }) {
  if (!unit) {
    return (
      <Text as="p" font="legal" color="fgMuted">
        {tenorLabel} 입찰 자료를 아직 못 받았어요.
      </Text>
    );
  }
  return (
    <HStack gap={1.5} flexWrap="wrap" alignItems="baseline">
      <Cond k="직전 입찰" v={`${unit.label} ${unit.date}`} strong />
      {/* 단위를 **값에 붙인다** — 표는 열 머리가 단위를 지지만(「발행 (조)」)
          이 줄엔 머리가 없다. 「낙찰 2.1」은 2.1조인지 2.1억인지 못 읽는다. */}
      <Cond k="낙찰" v={`${fmtJo(unit.amount).replace('+', '')}조`} />
      {unit.ratio != null ? <Cond k="응찰률" v={`${unit.ratio.toFixed(1)}%`} /> : null}
      {unit.rate != null ? <Cond k="낙찰금리" v={`${unit.rate.toFixed(3)}%`} /> : null}
      {unit.rateDelta != null ? (
        <Cond
          k="직전 대비"
          v={`${unit.rateDelta > 0 ? '+' : unit.rateDelta < 0 ? '−' : ''}${Math.abs(unit.rateDelta).toFixed(1)}bp`}
        />
      ) : null}
      {unit.grade ? <Cond k="수요 판정" v={unit.grade} strong /> : null}
    </HStack>
  );
}

/** 그림 아래 **감마 한 줄** [OWNER 2026-10-20 — 「그림아래 감마 한줄로」].
 *
 *  ## 왜 속도가 아니라 감마인가
 *
 *  순매수의 **부호에는 정보가 거의 없다**. 잔액이 늘고 이 회계는 영합이라
 *  금융투자(PD)가 내놓는 것을 나머지가 **늘** 받는다 — 60일 MA 의 양수 비중이
 *  보험·30년물 **100%** · 국가지자체·전체 100% · 외국인·30년물 100%다. 감마는
 *  44~57% 라 부호가 산다(`flow.gamma` 머리의 실측).
 *
 *  ## 표가 아니라 **그림 아래 한 줄**이다
 *
 *  표에 값 모드를 더하는 안도 있었는데 그러면 같은 표가 세 가지를 말하게 되고,
 *  어느 모드인지 놓치면 **구간 합을 감마로 읽는다**. 그림이 이미 그 (만기물 ×
 *  주체) 하나를 그리고 있으므로, 그 아래 한 줄이 「그 계열이 빨라지나」를
 *  말하는 자리로 맞다.
 *
 *  ## 잡음인 창을 **흐리게 적는다**
 *
 *  Γ5·Γ20 은 부호가 중위 5~7일마다 뒤집혀 신호가 아니다. 지우지는 않는다 —
 *  「안 보인다」와 「없다」는 다른 말이고, 짧은 창이 왜 못 믿을 것인지는 보여야
 *  배운다. 판정문(`say`)은 믿을 만한 창(60·120)만 보고 서버가 짓는다(§16). */
function GammaLine({ g }: { g: NonNullable<FlowBoard['gamma']> }) {
  /** 감마는 백만원/일이라 **억/일**로 줄여 읽는다 — 표의 `fmtEok` 과 같은 자다. */
  const cell = (v: number | null) => (v == null ? '—' : fmtEok(v));
  return (
    <VStack gap={0.25} width="100%">
      {/* ★**판정이 먼저 온다** [OWNER 2026-10-20 — 「이게 메인이야,, 난 이걸 보고
          싶은거고」]. 종전에는 수 넉 줄 뒤에 legal 크기로 붙어 있어서 각주처럼
          읽혔다. 이 면이 재는 축이 가속이므로(§감마) 그 한 문장이 머리말이다. */}
      <Text as="p" font="label1"
        className={g.tone === 'up' ? 'sr-up' : g.tone === 'down' ? 'sr-down' : undefined}
        color={g.tone ? undefined : 'fgMuted'}>
        {g.say}
      </Text>
      <HStack gap={1.5} flexWrap="wrap" alignItems="baseline">
        <Text as="span" font="legal" color="fgMuted">감마 (억/일)</Text>
        {g.rows.map((r) => (
          <HStack key={r.window} gap={0.5} alignItems="baseline">
            {/* 창 이름을 **선과 같은 진하기**로 — 위 그림의 어느 선인지 눈으로
                이어진다(`MA_INK` 와 같은 차례). */}
            <Text as="span" font="legal" color="fgMuted"
              style={{ opacity: (MA_INK[g.rows.indexOf(r)] ?? 100) / 100 }}>
              {r.window}일
            </Text>
            {/* 잡음인 창은 흐리게 — 지우지 않고 **믿을 만함의 차이**를 보인다. */}
            <Text as="span" font="label2"
              className={r.gamma == null ? undefined
                : r.gamma > 0 ? 'sr-up' : r.gamma < 0 ? 'sr-down' : 'sr-flat'}
              style={r.trust === '잡음' ? { opacity: 0.52 } : undefined}>
              {cell(r.gamma)}
            </Text>
          </HStack>
        ))}
      </HStack>
      <Text as="p" font="legal" color="fgMuted">{g.note}</Text>
    </VStack>
  );
}

export function FlowPage() {
  const [face, setFace] = useState<Face>('cash');
  const [span, setSpan] = useState<Span>('1Y');
  /* ④⑤⑥ 의 손잡이 셋 + 일별 그림의 주체. 면이 바뀌면 주체 열쇠 집합이 다르니
     고른 주체를 내린다(선물 `BANK` 와 현물 `bank` 는 다른 열쇠다). */
  const [cashTenor, setCashTenor] = useState<CashTenor>('ALL');
  /* 이동평균 창은 더 이상 **고르는 것이 아니다** — 그림이 넷을 늘 그린다
     (`MA_INK` 머리). 서버에 `ma` 를 안 보내면 `series.ma` 는 `null` 이고
     `series.mas` 넷만 온다. */
  const [pdOn, setPdOn] = useState(false);
  const [pdPct, setPdPct] = useState(60);
  const [daily, setDaily] = useState<string | null>(null);
  const pickFace = useCallback((f: Face) => { setFace(f); setDaily(null); }, []);
  /** 행렬의 칸 — 만기물과 주체를 **한 번에** 고른다 [OWNER 2026-10-20].
   *
   *  주체 열쇠 집합은 만기물이 바뀌어도 같으므로(`CASH_COLS` 한 벌) 면을 바꿀
   *  때와 달리 고른 주체를 안 내린다 — 「30년물 보험」에서 「10년물」 칸으로
   *  옮겨도 보험이 그대로 서는 것이 맞다. */
  const pickCell = useCallback((t: CashTenor, subject: string) => {
    setCashTenor(t);
    setDaily(subject);
  }, []);

  /** 실험 창 — Backtest 와 같이 **사람이 열고 사람이 실행한다**. 고른 칸이
   *  그대로 들어가서, 「이 칸이 뜻이 있나」를 바로 재 볼 수 있다. */
  const [labOpen, setLabOpen] = useState(false);
  const [got, setGot] = useState<FlowBoard | null>(null);
  /** 입찰 상세 — 왼쪽 카드 머리의 사실 줄만 쓴다. 없어도 화면은 선다. */
  const [iss, setIss] = useState<IssuanceBoard | null>(null);
  const [err, setErr] = useState<string | null>(null);
  /* `unavailable`(백엔드가 없다) 과 `err`(그 밖) 를 **따로** 든다 — 문구가
     다르기 때문이다(MrPage 와 같은 규율). */
  const [down, setDown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [hover, setHover] = useState<string | null>(null);
  /* 두 그림이 **한 커서**를 나눈다 — 어느 쪽을 짚어도 같은 날을 읽는다
     (`backtest/LinkedCharts.tsx` 의 그 문법). `src` 를 들고 있는 이유는
     자기가 세운 커서를 자기에게 되돌려 주면 깜빡이기 때문이다. */
  const [cursor, setCursor] = useState<{ i: number; src: 'cum' | 'day' }>();
  const onCum = useCallback(
    (i: number | null) => setCursor(i == null ? undefined : { i, src: 'cum' as const }), []);
  const onDay = useCallback(
    (i: number | null) => setCursor(i == null ? undefined : { i, src: 'day' as const }), []);
  /* 계열 끄기 — 손잡이는 **스트립의 토글**이다(`StripSlot.toggle`). 새 컨트롤을
     안 만든다는 캐논 규칙 1 의 자리이고, 끄는 손잡이와 값이 한 칸에 있어야
     둘이 갈릴 수 없다(`ChartReadoutStrip` 머리). */
  const [off, setOff] = useState<Record<string, true>>({});
  const toggle = useCallback(
    (k: string) => setOff((o) => (o[k] ? Object.fromEntries(
      Object.entries(o).filter(([x]) => x !== k)) as Record<string, true> : { ...o, [k]: true })),
    []);

  const side: FlowSide = face === 'cash' ? 'cash' : 'fut';
  const tenor = side === 'cash' ? cashTenor : (FUT_TENOR[face] ?? '3Y');
  const pdShare = side === 'cash' && pdOn ? pdPct / 100 : null;

  /* 라이브 단발이라 `AbortController` 로 충분하다 — MrPage 의 순번 가드는
     폴링과 딥링크가 겹치는 자리의 해법이고 여기엔 둘 다 없다
     (`lab/creditdts/CreditDtsPage.tsx:327` 선례). */
  const load = useCallback((signal?: AbortSignal) => {
    if (face === 'issue') return;
    setBusy(true);
    /* 행렬이 합할 창을 **봉 수로** 넘긴다 — 그림을 자르는 그 수다(`span.ts`).
       날짜로 넘기면 휴일 하나에 표와 그림이 갈린다. `Infinity`(전체)는
       `flowQueryString` 이 빼고, 서버 기본이 전구간이라 뜻이 같다. */
    fetchFlowBoard({ side, tenor, pdShare, daily, span: SPAN_BARS[span] }, signal)
      .then((r) => { setGot(r); setErr(null); setDown(false); })
      .catch((e: unknown) => {
        if (signal?.aborted) return;
        if (e instanceof BacktestUnavailable) { setDown(true); return; }
        setErr(e instanceof Error ? e.message : String(e));
      })
      .finally(() => { if (!signal?.aborted) setBusy(false); });
  }, [face, side, tenor, pdShare, daily, span]);

  useEffect(() => {
    const ac = new AbortController();
    load(ac.signal);
    return () => ac.abort();
  }, [load]);

  /* 입찰 상세는 **따로·한 번만** 받는다 [OWNER 2026-10-20 — 발행 면을 접음].
     수급 손잡이(만기물·PD·이동평균·구간)와 무관한 자료라 같이 다시 받으면
     손잡이를 만질 때마다 쓸데없이 한 번 더 다녀온다. 실패해도 **화면을 안
     막는다** — 수급표가 주인공이고 이쪽은 머리의 사실 줄이다. */
  useEffect(() => {
    const ac = new AbortController();
    fetchIssuanceBoard(ac.signal)
      .then((r: IssuanceBoard) => setIss(r))
      .catch(() => { /* 사실 줄만 비면 된다 */ });
    return () => ac.abort();
  }, []);

  const stack = useStackedScales();
  const unitIsCash = side === 'cash';
  /** 일별 자 — 현물은 **억**이다. 조로 적으면 일별이 전부 `+0.0조` 로 뭉개진다
   *  (실측 2026-10-19). 누적(올해)만 조를 쓰고 그건 표가 진다. */
  const fmt = useCallback(
    (v: number) => (unitIsCash ? fmtEok(v) : fmtContracts(v)),
    [unitIsCash],
  );
  /** ★**누적 자는 다르다** — 현물 누적은 억으로 적으면 열 자리가 된다
   *  (실측 2026-10-19: 금융투자 1년 누적 −680,061,101백만원 = `−6,800,611억`).
   *  그 길이가 리드아웃 스트립을 넘쳐 **넷째 값이 밀려 나갔다**. 조로 적으면
   *  `−680.1` 여섯 자다. 표가 이미 같은 판단을 했고(`FlowTable::val` — 일별 억 ·
   *  올해 조), 그 규칙이 그림·스트립·사실 칸에는 안 와 있었다. */
  const fmtCum = useCallback(
    (v: number) => (unitIsCash ? fmtJo(v) : fmtContracts(v)),
    [unitIsCash],
  );
  /** 칸 옆에 붙는 단위 말. 일별과 누적이 다르다. */
  const unitWord = unitIsCash ? '억' : '계약';
  const cumWord = unitIsCash ? '조' : '계약';

  /** 창 안의 날짜와 **다시 센 누적**.
   *
   *  ★서버가 보낸 `cum` 을 그냥 자르면 선이 창의 첫날 값에서 시작해 「올해 얼마」가
   *  아니라 「2016년부터 얼마」를 보여 준다. 창 안에서 **0 부터 다시** 센다.
   *  이동평균(⑤)은 수준이라 그대로 자른다 — 다시 세는 것이 아니다. */
  const win = useMemo(() => {
    if (!got) return null;
    const n = got.series.dates.length;
    const k = Math.max(0, n - (SPAN_BARS[span] === Infinity ? n : SPAN_BARS[span]));
    const dates = got.series.dates.slice(k);
    const cum = got.series.cum.map((s) => {
      const base = s.values[k - 1] ?? 0;
      return { ...s, values: s.values.slice(k).map((v) => v - base) };
    });
    const dailyS = got.series.daily
      ? { ...got.series.daily, values: got.series.daily.values.slice(k) }
      : null;
    /* ★`?? []` 가 **지켜 주는 것** [2026-10-20]. 프런트는 Vercel 이 밀면 바로
       서는데 백엔드 `:8200` 은 `SauronV2Refresh` 가 30분마다 띄운다 — 그 사이
       화면은 **새 것**이고 서버는 **옛 것**이다. 그때 `mas` 가 없는데 바로
       `.map` 하면 화면 전체가 흰 판이 된다(실측: 개발 백엔드를 옛 코드로 두고
       열었더니 「Cannot read properties of undefined」로 면이 통째로 죽었다).
       새 칸은 **없을 수 있는 것**으로 다룬다. */
    const masS = (got.series.mas ?? []).map((m) => ({ ...m, values: m.values.slice(k) }));
    return { dates, cum, daily: dailyS, mas: masS };
  }, [got, span]);

  /** 누적 선 넷. */
  const lines: TimeLine[] = useMemo(() => {
    if (!win) return [];
    /* ★색은 **계열의 차례**가 정한다, 그려지는 차례가 아니라 — 하나를 끄면
       나머지가 색을 갈아입는 것을 막는다(dataviz 의 「색은 개체를 따른다」). */
    return win.cum
      .map((s, i) => ({ s, i }))
      .filter(({ s }) => !off[s.key])
      .map(({ s, i }) => ({
        id: s.key,
        values: s.values,
        color: (p) => p.resolve(`var(${INK[i % INK.length]})`),
        width: 2 as const,
        format: fmtCum,
        beacon: i === 0,
      }));
  }, [win, fmtCum, off]);

  /** 일별 막대 하나 + 그 위의 이동평균 선(⑤). 막대는 **부호마다 색**이고,
   *  평균선은 계열색 셋째(바이올렛) — 빨강·파랑 막대 위에서 둘 다와 갈린다. */
  const dailyLines: TimeLine[] = useMemo(() => {
    if (!win?.daily) return [];
    const bars: TimeLine = {
      id: win.daily.key,
      values: win.daily.values,
      kind: 'histogram' as const,
      color: (p) => p.up,
      /* 부호가 색을 정한다 — 그것이 막대를 들인 이유의 절반이다. */
      colorAt: (v, p) => (v >= 0 ? p.up : p.down),
      format: fmt,
    };
    if (!win.mas.length) return [bars];
    /* ★평균선 **넷을 같이** 그린다 [OWNER 2026-10-20 — 「동시에 여러 MA도 보고
       싶고 그런거야」]. 하나씩 갈아 끼우면 「짧은 쪽은 식고 긴 쪽은 빨라진다」를
       기억으로 맞대야 하는데, 그건 화면이 할 일이다.

       **색은 한 가지에 진하기만 가른다.** 누적 그림이 이미 `INK` 넷을 주체에
       쓰고 있어서 같은 네 색을 창에 또 쓰면 한 카드 안에서 같은 색이 두 가지를
       뜻한다. 진하기로 가르면 색은 「이동평균」 하나를 뜻하고, 덤으로 **진할수록
       믿을 만한 창**이 된다(`flow.WINDOW_TRUST` 와 같은 차례).

       넷 다 **왼쪽 축**이다 — 막대와 겹치면 묻힌다(위 `bars` 아래의 그 실측). */
    return [bars, ...win.mas.map((m, i) => ({
      id: m.key,
      values: m.values,
      color: (p: LwPalette) => p.dim(`var(${INK[2]})`, MA_INK[i] ?? 100),
      width: (i >= 2 ? 2 : 1) as 1 | 2,
      axis: 'aux' as const,
      format: fmt,
    }))];
  }, [win, fmt]);

  /** 커서가 짚은 자리. 그림 밖이면 **마지막 봉**을 읽는다 — 「비어 있는 상태」가
   *  없어야 줄이 생겼다 사라지며 그림 높이를 흔들지 않는다. */
  const at = useMemo(() => {
    const n = win?.dates.length ?? 0;
    const i = cursor && cursor.i >= 0 && cursor.i < n ? cursor.i : n - 1;
    return { i, date: win?.dates[i] ?? '' };
  }, [cursor, win]);

  /** 스트립 칸 — **범례이자 값이자 손잡이**다. 셋을 한 자리에 모으는 것이
   *  이 부품이 생긴 이유다(`ChartReadoutStrip` 머리). 그래서 따로 범례를 안 둔다. */
  const slots = useMemo<StripSlot[]>(() => {
    if (!win) return [];
    const chars = slotChars(
      fmtCum,
      ...win.cum.flatMap((c) => [Math.max(...c.values), Math.min(...c.values)]),
    );
    return win.cum.map((c, i) => ({
      key: c.key,
      label: c.label,
      value: fmtCum(c.values[at.i] ?? 0),
      color: `var(${INK[i % INK.length]})`,
      chars,
      /* 좁아지면 **값만** 떨군다 — 칸은 남는다. 뒤 계열부터 떨어진다. */
      drop: (Math.min(i + 1, 6) as 1 | 2 | 3 | 4 | 5 | 6),
      toggle: { on: !off[c.key], onToggle: () => toggle(c.key) },
    }));
  }, [win, at.i, fmtCum, off, toggle]);

  /* ── 컨트롤 행 (등고 32) — 면·구간은 네 면이 같이 쓴다. 발행 면은 이 줄을
     그대로 받아 제 자리에 세운다(같은 손잡이가 같은 자리에 있어야 면을 넘겨도
     손이 헤매지 않는다). */
  const controls = (
    <HStack gap={2} alignItems="flex-end" flexWrap="wrap">
      {/* 폭은 **최장 라벨**로 잰다 — 260 에서는 「선물 10년」이 두 줄로
          접혔다(실측 2026-10-19). 말줄임 금지라 폭을 키우는 쪽이 답이다.
          네 면이라 330 → 420. */}
      {/* 면이 하나면 안 그린다 — 까닭은 `FACES_SHOWN` 머리에. */}
      {FACES_SHOWN.length > 1 ? (
        <Box width={105 * FACES_SHOWN.length}>
          <Segmented
            label="면"
            value={face}
            onChange={pickFace}
            options={FACES_SHOWN.map((k) => ({ value: k, label: FACE[k].label }))}
            fill
          />
        </Box>
      ) : null}
      <Box width={250}>
        <Segmented label="구간" value={span} onChange={setSpan} options={SPAN_OPTIONS} fill />
      </Box>
      {face === 'cash' ? (
        /* ④ 만기물 — 아홉 칸. 「전체」가 분리 전 화면과 같은 수다. */
        <Box width={540}>
          <Segmented
            label="만기물"
            value={cashTenor}
            onChange={(t) => { setCashTenor(t); setDaily(null); }}
            options={CASH_TENORS}
            fill
          />
        </Box>
      ) : null}
      {/* ★이동평균 **단일 선택 컨트롤을 들어냈다** [OWNER 2026-10-20 — 「동시에
          여러 MA도 보고 싶고 그런거야」]. 이제 그림이 창 넷을 **늘** 그리므로
          고를 것이 없다 — 고를 것이 없는 컨트롤은 폭만 먹는다(`FACES_SHOWN` 과
          같은 규율). 감마 판정도 네 창을 다 보므로 이 손잡이에 안 매였다.
          서버의 `ma` 인자는 남아 있고(옛 호출부·시험), 화면이 안 보낼 뿐이다. */}
      {face === 'cash' ? (
        /* ⑥ PD 인수 — 켜면 발행시장 인수분을 금융투자·은행에 더한다. 몫은 가정. */
        <>
          {/* 폭은 **최장 라벨**로 잰다 — 위 「면」 주석의 그 판례를 이 상자가
              안 받아서 또 밟았다(실측 2026-10-20). 알약 속 `span` 이 좌우 16px
              씩 미니 한 칸에 **글자폭 + 32** 가 든다: 「PD 켬」은 33.8 + 32 =
              65.8 인데 130 ÷ 2 = 65 라 0.8px 모자라 두 줄로 접혔다. 두 칸 ×
              70 = 140 으로 여유 4.2px 를 둔다. */}
          <Box width={140}>
            <Segmented
              label="PD 인수 반영"
              value={pdOn ? 'on' : 'off'}
              onChange={(v) => setPdOn(v === 'on')}
              options={[{ value: 'off', label: 'PD 끔' }, { value: 'on', label: 'PD 켬' }]}
              fill
            />
          </Box>
          <Box width={120}>
            <Field label="금융투자 몫" help="발행시장 인수분 중 금융투자가 받는 비율. 은행은 나머지예요. 공표되지 않아 가정이에요.">
              <NumField
                label="PD 인수 중 금융투자 몫"
                value={pdPct}
                min={0}
                suffix="%"
                onCommit={(v) => setPdPct(Math.min(100, Math.max(0, Math.round(v))))}
              />
            </Field>
          </Box>
        </>
      ) : null}
    </HStack>
  );

  /* 「발행」 면은 **접혔다** [OWNER 2026-10-20] — 공급이 수급표의 첫 값 열이 되고
     입찰 상세는 `AuctionFact` 가 든다. `IssuanceFace.tsx` 는 지우지 않았다:
     입찰 전수 표와 누적 공급 그림이 거기 있고, 되살릴 때 다시 지을 일이 아니다.
     `FACES_SHOWN` 에 `'issue'` 를 더하고 이 가지를 되돌리면 선다. */

  if (down) {
    return <ErrorState what="투자자별 수급" onRetry={() => load()} retrying={busy}
      detail="백엔드가 안 보여요 — 이 화면은 SQL 두 원천을 바로 읽어요." />;
  }
  if (err) {
    return <ErrorState what="투자자별 수급" detail={err} onRetry={() => load()} retrying={busy} />;
  }
  if (!got) return <LoadingState what="투자자별 수급" />;

  /** 고른 만기물의 직전 입찰. 「전체」면 가장 최근 입찰 하나를 든다. */
  const lastAuction: IssuanceUnit | null = iss
    ? (cashTenor === 'ALL'
      ? iss.latest
      : iss.tenors.find((t) => t.key === cashTenor)?.last ?? null)
    : null;

  const pdPctShown = got.pd ? Math.round(got.pd.share * 100) : null;

  return (
    <VStack gap={1.5} width="100%" flexGrow={1} minHeight={0}>
      {/* ── 조건 스트립 ─────────────────────────────────────────────────── */}
      <VStack className="sr-rv-bar" width="100%" gap={0.5}>
        <HStack gap={2} flexWrap="wrap" alignItems="baseline" width="100%">
          {/* ★둘을 **따로** 적는다 — 어긋나는 것이 정상이고 경고가 아니다.
              다만 **그 면이 읽는 원천만** 적는다: 현물 면에서 서버는 선물표를
              아예 안 읽어 `asof.fut` 이 `null` 로 온다. 거기에 `—` 를 세우면
              「선물 자료가 빠졌다」로 읽히는데, 안 빠졌고 안 물어본 것이다
              (실측 2026-10-19 — 현물 면에 「선물수급 —」 이 서 있었다). */}
          {got.asof.fut ? <Cond k="선물수급" v={got.asof.fut} /> : null}
          {got.asof.cash ? <Cond k="현물수급" v={got.asof.cash} /> : null}
          {side === 'cash' ? <Cond k="만기물" v={CASH_TENOR_LABEL[cashTenor]} strong /> : null}
          {/* ★「단위」와 「순위」 칸을 **들어냈다** [OWNER 2026-10-20].
              단위는 **열 머리가 이미 진다**(「발행 (조)」·「오늘 (억)」·「올해 (조)」)
              — 조건 줄에 또 적으면 같은 말이 두 곳이고, 정작 어느 열이 어느
              단위인지는 머리를 봐야 안다. 순위 하한도 순위표 **아래 설명 줄**이
              더 길게 말하고 있었고, 트레이더가 못 바꾸는 고정값이다. */}
          <Cond k="표본" v={`${got.days.toLocaleString('ko-KR')}일`} />
          {got.series.mas?.length
            ? <Cond k="이동평균" v={got.series.mas.map((m) => m.label).join(' · ')} />
            : null}
          {got.pd && pdPctShown != null
            ? <Cond k="PD 인수" v={`금융투자 ${pdPctShown}% · 은행 ${100 - pdPctShown}%`} strong />
            : null}
          {/* ★「집계예요 — 새 판단이 아니에요.」를 여기 또 적지 않는다. 바로
              아랫줄의 `got.basis` 가 이미 그 말로 시작한다(`flow.py`) —
              같은 문장이 두 줄 연속으로 서 있었다(실측 2026-10-19). 기준을
              말하는 것은 **서버 한 곳**이다. */}
        </HStack>
        {/* 한 줄로 합친다 — 회색 문장 셋이 쌓이면 벽처럼 읽혀서 아무도 안
            읽는다(실측 2026-10-19). 뺀 것은 괄호로 이어 붙인다. */}
        <Text as="p" font="legal" color="fgMuted">
          {got.basis}
          {got.excluded.length > 0
            ? ` (뺀 것 — ${got.excluded.map((e) => e.label).join(' · ')})`
            : ''}
        </Text>
      </VStack>

      {/* ★히어로를 **들어냈다** [OWNER 2026-10-20 — 「빼도되는건 빼보면서 가보자」].
          「평소 대비가 가장 큰 주체 = 외국인 +6,918억」은 아래 순위표 1행과
          사실 스트립 「오늘·순위 위 셋」에 **같은 수가 또** 있었다(3중복). 게다가
          이 면의 주제는 10-20 부터 「공급을 누가 담나」인데 히어로는 「오늘 누가
          셌나」라 주제와도 어긋났다 — 화면에서 제일 큰 글씨를 중복에 쓰고 있었다.
          그 사실은 순위표가 σ 와 함께 지므로 잃는 것이 없다. */}

      {controls}

      {/* ── 여기부터 **구르는 칸** — 바닥 띠(`ui/BottomStrip`)가 `fixed` 가 아니라
          기둥의 마지막 칸이라, 내용이 기둥보다 길면 **자라려는 칸이 0 으로 눌린다**
          (MrPage 가 먼저 밟은 자리). 조건 바·히어로·컨트롤만 위에 남기고 나머지를
          감싼다 — 안 감싸면 일별 그림과 사실 스트립이 잘린 채 **스크롤도 안 된다**
          (실측 2026-10-19). */}
      <VStack gap={1.5} width="100%" flexGrow={1} minHeight={0}
        style={{ overflowY: 'auto' }}>
      {/* ── 두 칸 ───────────────────────────────────────────────────────── */}
      {/* ★카드는 **`VStack`** 이다 — `Box` 는 CDS 기본이 **가로**라 머리와 대조
          줄이 한 줄에 붙어 뒤섞였다(실측 2026-10-19, MrPage 가 쓰는 그 꼴). */}
      {/* ★높이를 **감마 줄만큼** 키웠다 [2026-10-20]. 560 은 그림 둘 + 스트립에
          맞춘 수였는데 그 아래 감마 줄(56px)이 들어오면서 일별 그림이 57px 로
          눌렸다 — 그 줄이 설명하는 계열을 정작 못 읽게 된다. */}
      <HStack gap={2} alignItems="stretch" minHeight={640} width="100%"
        flexShrink={0} flexWrap="wrap">
        {/* 표가 일곱 열을 진다 — 640 에서는 20일·올해가 잘렸다(실측). */}
        {/* 표는 **자연폭까지만** 먹는다(실측 1,207 → 부제 축약 뒤 1,117).
            남는 폭은 오른쪽으로 보낸다 — 리드아웃 칸 넷이 값을 다 들려면
            계열 영역이 480px 를 넘어야 한다(`type.css` 의 떨굼 사다리). */}
        <VStack className="sr-card" flexBasis={1120} flexGrow={0} flexShrink={1}
          maxWidth={1180} minWidth={0} minHeight={0}>
          <VStack paddingX={2} paddingTop={1.5} paddingBottom={1} gap={1}>
            {/* ★제목이 **구간을 진다** [OWNER 2026-10-20]. 이 표는 고른 구간의
                합인데 아래 순위표의 마지막 열은 **올해(YTD)** 라, 같은 주체가 위에서
                +20.3 아래에서 +17.9 로 섰다(실측 1Y·보험). 둘 다 맞는 수인데 어느
                쪽이 「지금 보는 구간」인지 화면에 없었다 — 종전에는 표 **아래**
                설명 줄에만 날짜가 있었다. */}
            <Text as="h3" font="label1">
              {got.matrix
                ? `만기물별 발행과 순매수 · ${span === 'ALL' ? '전체 구간' : span}`
                : '기관계 세분 순위'}
            </Text>
            {/* 접은 「발행」 면이 남긴 것 — 고른 만기물의 **직전 입찰**이다.
                표의 발행 열은 금액만 들고, 응찰률·낙찰금리·수요 판정은 여기 선다. */}
            {got.matrix ? <AuctionFact unit={lastAuction} tenorLabel={CASH_TENOR_LABEL[cashTenor]} /> : null}
            {/* 대분류 대조 — **순위가 아니다**(상관 −0.9996). 숫자를 나란히
                적는 것보다 **양쪽 막대**가 「누가 받고 누가 냈나」를 한 눈에
                말한다(목업에서 가장 잘 읽히던 자리인데 첫 판에서 빼먹었다). */}
            {got.top.length > 0 ? <Balance top={got.top} fmt={fmt} unit={unitWord} /> : null}
          </VStack>
          <Box flexGrow={1} minHeight={0} paddingX={1} paddingBottom={1}>
            {got.matrix ? (
              <FlowMatrix
                matrix={got.matrix}
                tenor={cashTenor}
                picked={got.series.daily?.key ?? null}
                onPick={pickCell}
                highlight={hover}
                onHover={setHover}
              />
            ) : (
              <FlowTable rows={got.sub} side={side} floor={got.rankFloor}
                highlight={hover} onHover={setHover}
                picked={got.series.daily?.key ?? null} onPick={setDaily} />
            )}
          </Box>
        </VStack>

        {/* ★**이 칸의 주인공은 이동평균과 감마다** [OWNER 2026-10-20 — 「이게
            메인이야,, 난 이걸 보고 싶은거고」]. 10-20 첫 판에서 판정 문장만 크게
            키우고 **자리는 안 옮겼더니**, 주인공이 작은 칸(460) 안의 맨 아래에
            서서 화면 밖으로 밀렸다(일별+MA 161px 대 누적 321px, 카드 제목은
            「누적 순매수」). 차례를 뒤집는다:

              제목(고른 칸) → **판정** → 일별+MA(큰 그림) → 누적(작은 그림)

            누적을 안 지우는 이유는 그것이 **증거**이기 때문이다 — 「이 구간에
            얼마나 샀나」가 거기 있고, 판정은 그 위의 읽기다. */}
        <VStack className="sr-card" flexBasis={460} flexGrow={1} flexShrink={1}
          minWidth={0} minHeight={0}>
          <VStack paddingX={2} paddingTop={1.5} paddingBottom={0.5} gap={0.75}>
            <HStack alignItems="baseline" justifyContent="space-between" gap={1}>
              {/* 제목이 **고른 칸**을 말한다 — 종전에는 아래 그림 하나의 이름
                  (「누적 순매수」)이라, 카드가 무엇에 대한 것인지 안 적혀 있었다. */}
              <Text as="h3" font="label1">
                {CASH_TENOR_LABEL[cashTenor]} · {win?.daily?.label ?? ''} — 사는 속도
              </Text>
              <HStack gap={1} alignItems="baseline">
                <Text as="span" font="legal" color="fgMuted">
                  일별 {unitWord} · 누적 {cumWord}
                </Text>
                {/* ★「이 칸이 뜻이 있나」를 **직접 재는** 자리 [OWNER 2026-10-20 —
                    「이거 내가 사용할 수 있어야한다고,, Backtest에서 처럼」].
                    고른 칸이 그대로 창에 들어간다. 판정은 2026-10-20 에 KILL 이고,
                    그 창은 **수 옆에 우연을 같이** 적어서 같은 실수를 막는다. */}
                {got.matrix ? (
                  <button type="button" className="sr-pillbtn"
                    onClick={() => setLabOpen(true)}>
                    이 칸 재보기
                  </button>
                ) : null}
              </HStack>
            </HStack>
          </VStack>
          {/* ── 판정 — 이 카드의 머리말 ──────────────────────────────────── */}
          {got.gamma ? (
            <VStack paddingX={2} paddingBottom={1}>
              <GammaLine g={got.gamma} />
            </VStack>
          ) : null}
          <VStack paddingX={2} paddingBottom={1} gap={0.5} flexGrow={1} minHeight={0}>
            {/* ── 일별 + 이동평균 넷 — **큰 그림** ─────────────────────────── */}
            <HStack alignItems="baseline" justifyContent="space-between" gap={1}>
              <Text as="span" font="label2">
                일별 — {win?.daily?.label ?? ''} ({unitWord})
              </Text>
              {/* 범례 — 선 넷의 **진하기와 창**을 짝지어 적는다. 진하기로만 갈린
                  선이라 글자 없이는 어느 것이 몇 일인지 못 읽는다. 축이 둘이라는
                  것도 여기서 말한다 — 안 적으면 평균선이 막대보다 위에 있는 것을
                  「그날보다 평균이 크다」로 읽는다. */}
              <HStack gap={1} alignItems="baseline" flexWrap="wrap">
                {(win?.mas ?? []).map((m, i) => (
                  <HStack key={m.key} gap={0.5} alignItems="center">
                    <Box width={14} height={0} borderRadius={100}
                      style={{
                        borderTop: `${i >= 2 ? 2 : 1}px solid var(${INK[2]})`,
                        opacity: (MA_INK[i] ?? 100) / 100,
                      }} />
                    <Text as="span" font="legal" color="fgMuted">{m.label}</Text>
                  </HStack>
                ))}
                <Text as="span" font="legal" color="fgMuted">
                  평균선은 왼쪽 축 · 막대는 빨강이 순매수, 파랑이 순매도예요
                </Text>
              </HStack>
            </HStack>
            {/* ★`flexBasis={0}` 이 있어야 `flexGrow` 가 **실제로** 그 비율이 된다.
                기본 `auto` 면 그림의 고유 높이가 먼저 자리를 잡고 남는 것만
                갈려서, 실측 345:57(약 6:1)이 나왔다. 몫은 **일별이 둘**이다. */}
            <Box className="sr-plot" flexGrow={2} flexBasis={0} minHeight={160}>
              <TimeChart
                dates={win?.dates ?? []}
                lines={dailyLines}
                precision={0}
                priceLines={[{ value: 0, color: (p) => p.line }]}
                onHoverIndex={onDay}
                syncIndex={cursor?.src === 'cum' ? cursor.i : null}
                hoverLabel={(i) => `${win?.dates[i] ?? ''} · ${win?.daily?.label ?? ''} `
                  + fmt(win?.daily?.values[i] ?? 0)
                  /* 네 창을 **다** 읽는다 — 그림이 넷을 그리는데 한 줄만 읽어
                     주면 나머지 셋은 눈으로 재야 한다. */
                  + (win?.mas ?? [])
                    .filter((m) => m.values[i] != null)
                    .map((m) => ` · ${m.label} ${fmt(m.values[i] as number)}`)
                    .join('')}
                accessibilityLabel={`${win?.daily?.label ?? ''} 일별 순매수와 이동평균 `
                  + `${(win?.mas ?? []).map((m) => m.label).join('·')}`}
                {...stack}
              />
            </Box>
            {/* ── 누적 — **증거**. 아래 작은 그림으로 내려왔다 ─────────────── */}
            <HStack alignItems="baseline" justifyContent="space-between" gap={1}>
              <Text as="span" font="label2">누적 순매수 ({cumWord})</Text>
              <Text as="span" font="legal" color="fgMuted">
                고른 구간의 첫날부터 다시 세요
              </Text>
            </HStack>
            {/* ★리드아웃 스트립은 **그 그림 밖·위**에 선다 [OWNER 2026-09-21] —
                계열 이름·값·끄는 손잡이 셋을 한 칸에 모은다. 따로 두면 「지금
                그려진 것」과 「끄는 손잡이」가 갈릴 수 있다.
                ⚠감싸는 상자는 **세로**여야 한다 — `Box`(CDS 기본 가로 flex)면
                `width="100%"` 를 줘도 상자만 늘고 스트립은 제 내용 폭으로 줄어
                통째로 잘린다(실측: 상자 618 · 스트립 141 · 계열 영역 16px). */}
            <VStack width="100%">
              <ChartReadoutStrip
                date={at.date}
                slots={slots}
                ariaLabel={`${FACE[face].label} 누적 순매수 — 커서가 짚은 날의 값`}
              />
            </VStack>
            <Box className="sr-plot" flexGrow={1} flexBasis={0} minHeight={120}>
              <TimeChart
                dates={win?.dates ?? []}
                lines={lines}
                precision={0}
                /* ★시간축을 **둘 다** 세운다. 쌓인 차트는 보통 위쪽 축을 숨기는데
                   (`hideTimeAxis`), 여기는 두 그림 사이에 제목 줄이 끼어 있어
                   아래 축이 위 그림의 것으로 안 읽힌다 [OWNER 2026-10-19]. */
                onHoverIndex={onCum}
                syncIndex={cursor?.src === 'day' ? cursor.i : null}
                hoverLabel={(i) => `${win?.dates[i] ?? ''} · `
                  + (win?.cum ?? []).map((c) => `${c.label} ${fmtCum(c.values[i] ?? 0)}${cumWord}`).join(', ')}
                accessibilityLabel={`${FACE[face].label} 누적 순매수 — ${got.series.cum.map((s) => s.label).join(', ')}`}
                {...stack}
              />
            </Box>
          </VStack>
        </VStack>
      </HStack>

      {/* ── 주체별 순위 ─────────────────────────────────────────────────── */}
      {/* 행렬이 왼쪽 칸을 가져갔으므로 이 표는 **아래 전폭**으로 내려온다 —
          지우지 않는다. 행렬에 없는 것 둘을 이 표가 진다: 「오늘이 평소보다
          센가」(σ)와 순위 하한 밖 주체를 흐리게 남기는 일. 「안 보인다」와
          「없다」는 다른 말이다(`FlowTable` 머리). */}
      {got.matrix ? (
        <VStack className="sr-card" width="100%" flexShrink={0} minWidth={0}>
          <VStack paddingX={2} paddingTop={1.5} paddingBottom={1} gap={0.5}>
            <Text as="h3" font="label1">주체별 순위 · {CASH_TENOR_LABEL[cashTenor]}</Text>
            {/* ★마지막 열이 **올해**라는 것을 부제가 말한다 — 위 표의 구간과
                다른 창이라 같은 주체가 두 수로 선다. 「구간이 다르다」를 안 적으면
                화면이 스스로를 반박하는 것처럼 읽힌다. */}
            <Text as="span" font="legal" color="fgMuted">
              위 표가 고른 구간({span === 'ALL' ? '전체' : span})의 합을 말한다면 이
              표는 오늘을 말해요 — 그 주체의 지난 1년 분포에 견준 자리예요. 마지막
              열만 올해(1월부터)라 위 표와 창이 달라요.
            </Text>
          </VStack>
          <Box paddingX={1} paddingBottom={1}>
            <FlowTable rows={got.sub} side={side} floor={got.rankFloor}
              highlight={hover} onHover={setHover}
              picked={got.series.daily?.key ?? null} onPick={setDaily} />
          </Box>
        </VStack>
      ) : null}

      {labOpen && got.matrix ? (
        <FlowLabWindow
          subject={got.series.daily?.key ?? 'foreigner'}
          tenor={cashTenor === 'ALL' ? 'ALL' : cashTenor}
          subjects={got.matrix.cols}
          tenors={got.tenors ?? []}
          onClose={() => setLabOpen(false)}
        />
      ) : null}

      {/* ── 사실 스트립 — **한 칸만 남았다** [OWNER 2026-10-20] ──────────── */}
      {/* 넷 중 셋을 들어냈다. 전부 화면 위쪽에 **같은 수가 이미 있었다**:
            「오늘·순위 위 셋」  → 순위표 1~3행과 글자 그대로 같다.
            「고른 구간 · 그림 넷」→ 행렬 **합계 행**이 열 주체 전부를 주고,
                                   리드아웃 줄이 같은 넷을 또 적는다(3중복).
            「모집단」           → 표본은 조건 줄에, 순위 대상은 순위표 설명
                                   줄에 있다. 「그림 4계열」은 아무도 안 쓴다.
          남긴 하나는 **다른 데 없는 사실**이다 — PD 가 얼마를 얹었나. */}
      {got.pd && pdPctShown != null ? (
        <Box flexShrink={0} width="100%">
          <HStack className="sr-stats" width="100%" flexWrap="wrap">
            <StatColumn title="PD 인수 보정 · 올해">
              <Stat label="더한 공급" value={fmtCum(got.pd.supplyYtd)}
                note={`금융투자 ${pdPctShown}% · 은행 ${100 - pdPctShown}% 가정`} />
              <Stat label="반영 전 입찰" value={`${got.pd.pending}건`}
                note={got.pd.pending ? '현물 자료가 그 날에 아직 안 닿았어요' : '전부 닿았어요'} />
            </StatColumn>
          </HStack>
        </Box>
      ) : null}
      </VStack>
    </VStack>
  );
}
