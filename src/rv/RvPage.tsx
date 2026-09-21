'use client';

/* Strategy = RV Analysis — 세 구성 [OWNER].
 *
 *   A. 동일섹터 레인   만기 × Δy 격자 + 스왑점 목록 (결정 숫자)
 *   B. 동일테너 레인   섹터 × 만기 히트맵, 칸 = 스프레드 랭크 백분위
 *   C. 크레딧 RV       4구역 [트레이더 피드백 2026-08-18]: 랭킹 표 → Score
 *                      히트맵 → 사분면(월환산 총수익 × 지난주 백분위) →
 *                      클릭 상세 2차트. 옛 두 축(상대 RV × Coverage)은
 *                      2026-08-20 에 은퇴했다 — 근거는 `RvScatter` 머리.
 *
 * 숫자는 전부 서버가 끝낸다(§16, `/api/rv/analysis`) — 이 파일은 조건 바와
 * 카드의 배치, 그리고 틴트뿐이다. C 의 Score 는 **랭킹이지 투자판단이 아니다**
 * (명구 의무 — RankingTable·ScoreHeat) — 별점·메달·추천 문구는 없다.
 *
 * 조건 바는 **고정·불투명**이다 — 어떤 조건에서 나온 숫자인지(후보 수·H·조달·
 * 금통위·이력 창·가중·제외·소스별 as-of)가 카드보다 먼저 읽혀야 한다. 소스별
 * as-of 는 장식이 아니라 차단 사항(rv1 B-2): IRS 와 민평이 1영업일 갈라진 것이
 * 실측이고, 갈라진 날은 그렇다고 말해야 한다.
 *
 * H 는 **한 벌이다**(2026-08-20, 워크북 `만기선택!B7` 정렬) — 레인 A 6M /
 * 크레딧 3M 두 벌이었던 것을 6M 한 벌로 합치고 화면 컨트롤(3/6/12)로 냈다.
 * 조건 바의 `Cond k="H"` 한 칸이 그 값을 말한다. **H 를 말하는 문장은 이
 * 컨트롤을 따라가야 한다** — 상수를 적으면 화면이 자기 숫자의 기간을 틀리게
 * 말한다(랭킹표 「버퍼」 풀이가 "3개월"로 굳어 있던 실측, 2026-08-21).
 * 같은 이유로 「지난주 백분위」 풀이는 이력 창 토글을 따라간다.
 *
 * 크레딧 RV 의 BEP 는 **아웃라이트 금리축이다**(워크북 정렬 2, 원칙 ②) —
 * 한때 크레딧 스프레드 축이라 금리(듀레이션) 효과가 화면 밖이었고 각주 의무가
 * 붙어 있었는데, 축이 옮겨 가면서 그 효과는 화면 **안**으로 들어왔고 각주도
 * 같이 은퇴했다. 조달이 더 이상 상쇄되지 않고 캐리에 남는 것이 그 결과다.
 *
 * ── 배치: 2열 두 줄 [OWNER 2026-08-19 — 크리틱 후 "2열로 접기" 확정] ────────
 * [A 동일섹터 | B 동일테너] / [C 랭킹 | Score 히트맵 + 사분면]. 네 카드 세로
 * 나열은 1568 에서도 오른쪽 절반이 여백이었고 오너 실기기(2560)에서는 2/3 가
 * 빈다 — §8.13 "화면은 창을 채운다"의 적용. 좁아지면 flexWrap 으로 한 열로
 * 접힌다. (한때 세로 스크롤 페이지였으나 8차 IA 재구성으로 100vh 기둥에
 * 복귀했다 — 지금은 스크롤이 없고, 조건 바의 sticky 는 무해한 잔재다.)
 *
 * as-of 갈라짐 강조는 **색이 아니라 굵기+밑줄**(.sr-rv-asof-split)이다 —
 * 처음엔 .sr-up(방향색)이었는데 ① 이 바의 배경(--sr-page) 위에서 4.1:1 로
 * 기준 미달(DESIGN §3.2 "부호 있는 숫자는 카드 위에만"의 그 측정)이고
 * ② 같은 화면에서 빨강이 "상승"과 "경고"를 겸직하게 된다(크리틱 P1).
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import { Select } from '@coinbase/cds-web/alpha/select';
import { Collapsible as CdsCollapsible } from '@coinbase/cds-web/collapsible';
import { Box, Divider, HStack, VStack } from '@coinbase/cds-web/layout';
import {
  Text,
  TextBody,
  TextCaption,
  TextDisplay3,
  TextLabel1,
  TextLabel2,
  TextLegal,
} from '@coinbase/cds-web/typography';

import { TimeChart, type TimeLine } from '@/chart/TimeChart';
import type { ScalePriceLine } from '@/chart/ScaleChart';
import { BacktestUnavailable } from '@/lib/api';
import { useFunding } from '@/state/funding';
import { Cond } from '@/ui/Cond';
import { NumField } from '@/ui/ControlCard';
import { ErrorState, LoadingState } from '@/ui/DataState';
import { ChartReadoutStrip, slotChars, type StripSlot } from '@/ui/ChartReadoutStrip';
import { DROPDOWN_STYLES } from '@/ui/window/popup';
import { FloatingWindow } from '@/ui/window/FloatingWindow';
import { useUrlState } from '@/ui/useUrlState';

import {
  REINVEST_LABEL,
  fetchRv,
  fetchRvHistory,
  type RvCreditItem,
  type RvHistoryPayload,
  type RvPayload,
  type RvReinvestMode,
  type RvWindow,
} from './api';
import { bp1, sig } from './fmt';
import { RankingTable } from './RankingTable';
import { RvScatter } from './RvScatter';
import { ScoreHeat } from './ScoreHeat';
import { SectorLane } from './SectorLane';
import { TenorHeat } from './TenorHeat';

/* 금통위 Δbp 입력이던 `BpField` 는 공용 `NumField`(`ui/ControlCard`)가 됐다
   [OWNER 2026-09-02 — "공용 부품은 한 벌로 승격"] — 같은 blur/Enter 커밋 기계가
   시뮬·mr 에 두 벌 더 있었다. 종전 기본값(suffix 'bp'·width 76)은 호출부가
   명시로 넘긴다. 접근성 이름도 호출부 몫이다 — 같은 모양의 칸이 화면에 열여덟
   개 선다(금통위 3 + 재투자금리 1 + 경로 2×7). */

/* ── 설정 패널의 배치 상수 ────────────────────────────────────────────────
 * 레이블 열이 **고정폭**이어야 컨트롤이 한 줄에 선다. 글자 수만큼 자리를 먹게
 * 두면 시작점이 줄마다 밀린다(재정돈 전 실측: 53·58·73·92px). 88 은 가장 긴
 * 레이블("커브 경로") + 여유다. */
const SET_LABEL_W = 88;
/** 격자 칸 폭 — 금통위·커브 경로가 같은 자를 쓴다(캡션과 칸이 같은 폭). */
const SET_FIELD_W = 76;
/** 경로 이름("경로 1") 칸 — 공유 캡션 줄의 왼쪽 빈 자리와 같은 폭. */
const SET_PATH_W = 56;

/** 설정 패널의 한 그룹 — 제목 + 줄들. 그룹 사이에만 Divider 를 긋는다. */
function SetGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <VStack gap={1} width="100%">
      <Text font="label2" as="span" color="fgMuted" noWrap>
        {title}
      </Text>
      <VStack gap={1} width="100%">
        {children}
      </VStack>
    </VStack>
  );
}

/** 설정 패널의 한 줄 — [고정폭 레이블][컨트롤들][우측 액션] + 아래 설명.
 *
 * `align` 은 컨트롤이 여러 줄일 때 레이블이 붙는 자리다: 금통위처럼 캡션+칸
 * 두 줄이면 `flex-end`(칸에 맞춤), 커브 경로처럼 블록이면 `flex-start`.
 * 설명(`note`)은 **레이블 열만큼 들여쓴** 아래 줄에 선다 — 컨트롤 뒤에 붙이면
 * 줄이 길어지고, 레이블 옆에 붙이면 컨트롤과 소속이 헷갈린다. */
function SetRow({
  label,
  note,
  action,
  align = 'center',
  children,
}: {
  label: string;
  note?: string;
  action?: React.ReactNode;
  align?: 'center' | 'flex-start' | 'flex-end';
  children: React.ReactNode;
}) {
  return (
    <VStack gap={0.5} width="100%">
      <HStack gap={1} alignItems={align} width="100%">
        <Box width={SET_LABEL_W} flexShrink={0}>
          <Text font="caption" as="span" color="fgMuted" noWrap>
            {label}
          </Text>
        </Box>
        <HStack gap={0.5} alignItems={align} flexWrap="wrap" flexGrow={1}>
          {children}
        </HStack>
        {action ? <Box flexShrink={0}>{action}</Box> : null}
      </HStack>
      {note ? (
        <HStack gap={1}>
          <Box width={SET_LABEL_W} flexShrink={0} />
          <Text font="legal" as="span" color="fgMuted">
            {note}
          </Text>
        </HStack>
      ) : null}
    </VStack>
  );
}

/* 조건 바 한 칸 `Cond` 는 공용이 됐다(`ui/Cond`) [OWNER 2026-09-02 — "공용
   부품은 한 벌로 승격"] — MR 조건 바와 같은 부품이고, 여기 있던 구 shorthand
   (TextCaption/TextLegal) 판이 새 문법(`Text font=…`)으로 넘어갔다(시각 동일 —
   shorthand 는 CDS 소스가 `Text font` 위임일 뿐이다). */

/** ±σ 밴드를 두른 소형 차트 하나 — 창 평균과 평균±σ 가 `ReferenceLine`(dataY)
 * 으로 선다. 통계는 서버 것 그대로(§16) — 여기서 평균을 다시 내지 않는다.
 *
 * 커서 리드아웃은 **그림 위 한 줄**이다(`ChartReadoutStrip`) — 2026-09-21 에
 * 떠 있는 카드에서 옮겼다. 이 차트가 180px 이라 카드(약 220px)가 그림보다 컸다.
 * 아래에 있던 「지금 X · 창 평균 Y · σ Z」 문장도 같이 걷었다: 줄이 쉴 때 마지막
 * 봉을 읽으므로 **같은 세 수를 두 번 적던 자리**였다. */
function BandChart({
  title,
  dates,
  values,
  stats,
}: {
  title: string;
  dates: string[];
  values: (number | null)[];
  stats: { now: number | null; mean: number | null; sd: number | null };
}) {
  const [idx, setIdx] = useState<number | null>(null);
  const lines: TimeLine[] = [{ id: 'v', values, color: (p) => p.fg }];

  /* ±σ 밴드 — 창 평균(가운데)과 평균±σ. 도메인 밖이면 안 보일 뿐 무해하다
     (LinkedCharts 의 같은 판단). */
  const bands: ScalePriceLine[] = [
    ...(stats.mean != null ? [{ value: stats.mean, color: (p: { line: string }) => p.line }] : []),
    ...(stats.mean != null && stats.sd != null
      ? [
          { value: stats.mean + stats.sd, color: (p: { line: string }) => p.line, dash: true },
          { value: stats.mean - stats.sd, color: (p: { line: string }) => p.line, dash: true },
        ]
      : []),
  ];

  /* 커서가 그림 밖이면 마지막 봉을 읽는다 — 줄이 비어 서 있지 않게 하는 규칙. */
  const at = idx != null && idx >= 0 && idx < values.length ? idx : values.length - 1;
  /* 이 화면의 bp 서식은 **한 자리**다 — 걷어 낸 아래 문장이 쓰던 그 서식을
     그대로 든다(같은 수를 두 서식으로 말하지 않는다). */
  const bp = (v: number) => `${v.toFixed(1)}bp`;
  const fmtBp = (v: number | null | undefined) => (v == null ? '—' : bp(v));
  const ch = slotChars(bp, ...values, stats.mean, stats.sd);
  /* 창 평균·σ 는 **가격선**이라 계열이 아니다 — 견본을 그 선의 잉크로 준다.
     좁아지면 σ → 창 평균 순으로 값을 내려놓고 「값」은 안 내려놓는다. */
  const slots: StripSlot[] = [
    { key: 'v', label: '값', value: fmtBp(values[at]), color: 'var(--color-fg)', chars: ch },
    /* 견본 색은 그 가격선이 캔버스에서 쓰는 토큰 그대로다 — 팔레트의 `line`
       이 `--color-bgLine` 이다(`chart/palette.ts`). 「--color-line」 같은 토큰은
       **없다**(가드가 그 오타를 잡았다, 2026-09-21). */
    { key: 'mean', label: '창 평균', value: fmtBp(stats.mean),
      color: 'var(--color-bgLine)', chars: ch, drop: 2 },
    { key: 'sd', label: 'σ', value: fmtBp(stats.sd),
      color: 'var(--color-bgLine)', opacity: 0.6, chars: ch, drop: 1 },
  ];

  return (
    <VStack gap={0.25} width="100%" onMouseLeave={() => setIdx(null)}>
      <TextLabel2 as="span">{title}</TextLabel2>
      <ChartReadoutStrip date={dates[at] ?? ''} slots={slots} />
      <Box className="sr-plot" width="100%">
        <TimeChart
          height={180}
          accessibilityLabel={title}
          dates={dates}
          lines={lines}
          priceLines={bands}
          onHoverIndex={setIdx}
          hoverLabel={() => `${title} 스크러버`}
        />
      </Box>
    </VStack>
  );
}

/** 이력 창의 머리 요약 한 칸 — Backtest 창의 Field 문법(라벨 뮤트 위,
 * 값 등폭 아래). 문장으로 잇던 숫자들을 칸으로 세운 것 [OWNER 2026-08-19 —
 * "이력창도 전반적으로 정돈"]: 값이 여섯이면 문장은 세 줄이 되고, 세 줄이 된
 * 문장에서 BEP 하나를 다시 찾게 된다. `Text`(토큰 직접)인 것은 CLAUDE.md 의
 * "새 코드에서 shorthand 추가 금지" 때문이고, caption/label2 토큰이라 기존
 * Field 와 픽셀이 같다. */
function Stat({ k, v }: { k: string; v: string }) {
  return (
    <VStack gap={0.25}>
      <Text as="span" font="caption" color="fgMuted" noWrap>
        {k}
      </Text>
      <Text as="span" font="label2" tabularNumbers noWrap>
        {v}
      </Text>
    </VStack>
  );
}

/** 클릭 상세 — `/api/rv/history` 의 두 소형 차트: 스프레드 이력과 섹터 상대
 * (같은 테너 횡단면 평균 대비) 이력, 각각 ±σ 밴드. */
function DrillWindow({
  point,
  window,
  onClose,
}: {
  point: RvCreditItem;
  window: RvWindow;
  onClose: () => void;
}) {
  const [data, setData] = useState<RvHistoryPayload>();
  const [err, setErr] = useState<string>();
  useEffect(() => {
    let live = true;
    setData(undefined);
    setErr(undefined);
    fetchRvHistory({ sector: point.sector, tenor: point.tenor, window })
      .then((j) => {
        if (live) setData(j);
      })
      .catch((e: unknown) => {
        if (live) setErr(e instanceof Error ? e.message : String(e));
      });
    return () => {
      live = false;
    };
  }, [point.sector, point.tenor, window]);

  return (
    <FloatingWindow
      windowKey="rv"
      title={`${point.sectorLabel} ${point.tenor} 이력`}
      aside={
        /* TextCaption 은 uppercase 라 "bp"가 "BP"로 선다 — 단위가 든 문장은
           TextLegal (§8.9, 이 리포가 이미 밟은 함정). */
        <TextLegal as="span" color="fgMuted" noWrap>
          {point.baseLabel} 대비 · bp · {window === '52w' ? '52주' : '전체 이력'}
        </TextLegal>
      }
      onClose={onClose}
    >
      <VStack gap={1.5} padding={2} width="100%">
        {/* 머리 요약 — 창을 연 이유의 숫자들이 칸으로 먼저 선다(랭킹 표의
            열 순서 그대로: 한 달 수익 → 지난주 백분위 → 버퍼 → 상대 RV).
            문장 두 줄에 흩어져 있던 것의 재조판 [OWNER 2026-08-19 — "이력창
            정돈"]. 2026-08-20 에 열 순서가 사분면 두 축 우선으로 바뀌면서 이
            줄도 같이 움직였다 — 표·그림·창이 같은 순서여야 한 사실이 된다. */}
        <HStack gap={3} flexWrap="wrap">
          <Stat k="한 달 수익" v={`${sig(point.trMonthBp)}bp`} />
          {point.pctLastWeek != null ? (
            <Stat k="지난주 백분위" v={`${point.pctLastWeek.toFixed(0)}%`} />
          ) : null}
          <Stat k={`${point.baseLabel} 대비`} v={`${bp1(point.nowBp)}bp`} />
          <Stat k="버퍼" v={`${sig(point.bufferBp)}bp`} />
          {point.relRv != null ? <Stat k="상대 RV" v={`${sig(point.relRv, 2)}σ`} /> : null}
          <Stat k="캐리 + 롤" v={`${sig(point.carryBp)} + ${sig(point.rollBp)}bp`} />
          {/* Score 가 어디서 왔는지 — 표에는 안 서고 여기서만 보인다. 사분면
              y축(지난주 백분위)과 **다른 통계**라 이름도 다르다. */}
          {point.spreadVolPct != null ? (
            <Stat k="변동성 대비 백분위" v={`${point.spreadVolPct.toFixed(0)}%`} />
          ) : null}
        </HStack>
        {err ? (
          <TextBody as="p" color="fgMuted">
            이력을 읽지 못했어요 — {err}
          </TextBody>
        ) : !data ? (
          <TextCaption as="span" color="fgMuted">
            불러오는 중이에요…
          </TextCaption>
        ) : data.points.length < 2 ? (
          <TextCaption as="span" color="fgMuted">
            그릴 이력이 없어요.
          </TextCaption>
        ) : (
          <>
            <BandChart
              title={`스프레드 — ${data.baseLabel} 대비`}
              dates={data.points.map((p) => p.t)}
              values={data.points.map((p) => p.s)}
              stats={data.spread}
            />
            <BandChart
              title={`섹터 상대 — ${data.baseLabel} 대비인 ${data.peers}개 평균 대비`}
              dates={data.points.map((p) => p.t)}
              values={data.points.map((p) => p.rel)}
              stats={data.rel}
            />
          </>
        )}
        {/* 상대 RV 의 성분 분해 — 포인터 툴팁에만 두면 키보드 사용자가 못 본다
            (크리틱 Alex/Sam). 상시 채널은 이 창이 진다. 합성값 자체는 위 머리
            요약이 이미 말했으므로 여기는 성분과 범례만 남는다. */}
        <TextLegal as="span" color="fgMuted">
          {point.relRv != null
            ? `상대 RV = 절대 z ${point.zAbs ?? '—'} · 섹터 z ${point.zSector ?? '—'} · 커브 z ${
                point.zCurve ?? '—'
              } (가중 40/40/20) — `
            : ''}
          Score 는 변동성 대비 백분위와 상대 RV 를 반반 섞은 값이에요.
          차트의 가는 선은 창 평균과 ±1σ예요.
        </TextLegal>
      </VStack>
    </FloatingWindow>
  );
}

export function RvPage() {
  const [funding] = useFunding();
  /* 화면 상태는 URL — 섹터(rs)와 이력 창(rw). 얕은 히스토리(useUrlState 규칙). */
  const [sectorParam, setSectorParam] = useUrlState('rs');
  const [windowParam, setWindowParam] = useUrlState('rw');
  const window: RvWindow = windowParam === 'all' ? 'all' : '52w';

  /** 금통위 오버라이드 — 달력의 남은 회의를 서버가 미리 채워 준다(기본 0)
   * [OWNER]. 날짜별 bp, ±100bp 클램프(손이 미끄러진 2500bp 가 조용히 계산되는
   * 것을 막는다 — funding.spread_bp 의 같은 판단). */
  const [mpc, setMpc] = useState<Record<string, number>>({});
  const [mpcOpen, setMpcOpen] = useState(false);
  const mpcEncoded = useMemo(
    () =>
      Object.entries(mpc)
        .filter(([, bp]) => bp !== 0)
        .map(([d, bp]) => `${d}:${bp}`)
        .join(';'),
    [mpc],
  );

  /** 보유기간 H(개월) — 워크북 `만기선택!B7`. **두 레인이 같은 값을 쓴다**
   * [OWNER 2026-08-20]: 전에는 레인 A 6M / 크레딧 3M 으로 갈려 있어서 "버퍼"와
   * "한 달 수익"이 다른 기간을 말했다. 워크북에는 H 가 하나뿐이고 그것도
   * 상수가 아니라 읽는 사람이 채우는 칸이라, 여기서도 컨트롤로 올렸다. */
  const [hMonths, setHMonths] = useState(6);

  /** 재투자 — 워크북 `만기선택!B11`. **만기가 H 안에 드는 후보에만 닿는다**
   * (6M 호라이즌이면 3M 후보 하나). 기본은 재투자 안 함이고, 그 갈래가 앵커
   * 8행의 세계다 — 켜면 그 후보들의 총수익이 움직인다. */
  const [reinvest, setReinvest] = useState<RvReinvestMode>('none');
  /** 직접 입력 금리(연 %) — 서버가 −10~30 으로 자른다. */
  const [reinvestRate, setReinvestRate] = useState(3.0);


  const [data, setData] = useState<RvPayload>();

  /** 경로 편집기가 세우는 테너 — **서버가 준 목록**(heat.tenors)이 진짜다.
   * 상수 사본을 들면 서버 상한(MAX_YEARS)이 움직인 날 조용히 갈린다: 상한이
   * 내려가면 422 가 말해 주지만 **올라가면 아무도 안 짖는다**(프런트가 새
   * 테너를 안 내놓을 뿐이다). 아래 상수는 첫 프레임(데이터 도착 전)의 자리만
   * 메우고, 그때는 값이 전부 0 이라 인코딩 결과가 어느 쪽이든 빈 문자열이다. */
  const tenorList = useMemo(
    () => data?.heat.tenors ?? ['3M', '6M', '9M', '1Y', '1.5Y', '2Y', '2.5Y', '3Y'],
    [data],
  );

  /** 비평행 커스텀 커브 두 벌 — 워크북 케이스 C/C-2. 테너별 Δ(bp) 이고, 빈 벌은
   * 열이 안 선다. 금통위 오버라이드와 같은 살림(React 상태 + 인코딩 + 재조회):
   * 계산 조건이지 화면 배치가 아니라서 URL 에 안 싣는다. */
  const [paths, setPaths] = useState<Record<string, number>[]>([{}, {}]);
  /* 한 벌이라도 0 이 아니면 **여덟 테너를 전부** 싣는다 — 0 을 빼면 안 된다.
   *
   * 처음엔 `.filter(bp !== 0)` 이었는데, 그러면 워크북의 기본 모양인
   * "단기 0 · 장기 +20" 램프가 표현되지 않는다: 0 이 빠져 노드가 3Y 하나만
   * 남고, 한 노드짜리 경로는 평탄 외삽이라 **평행이동과 같아진다**(실측으로
   * 걸렸다). 명시한 0 과 안 적은 칸은 딴 사실이고, 이 화면에서 0 은 "그
   * 테너는 안 움직인다"는 명시다. */
  const pathsEncoded = useMemo(
    () =>
      paths
        .map((p) =>
          Object.values(p).some((bp) => bp !== 0)
            ? tenorList.map((t) => `${t}:${p[t] ?? 0}`).join(',')
            : '',
        )
        // 빈 벌만 뺀다 — 둘 다 비면 경로 열 자체가 안 선다.
        .filter((chunk) => chunk !== '')
        .join('|'),
    [paths, tenorList],
  );
  const activePaths = useMemo(
    () => paths.map((p, i) => ({ i, on: Object.values(p).some((v) => v !== 0) })).filter((x) => x.on),
    [paths],
  );

  const [error, setError] = useState<string>();
  const [unavailable, setUnavailable] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [drill, setDrill] = useState<RvCreditItem | null>(null);
  /* 표 행 hover ↔ 사분면 점 강조 연동(Backtest 의 행↔미리보기 문법). */
  const [hovered, setHovered] = useState<RvCreditItem | null>(null);
  /* 커브 레인(동일섹터·동일테너·Score 히트맵) — 세부는 버튼 뒤 창으로
     [OWNER — "중요한 정보를 앞으로, 세부는 인터랙션 이후에"]. */
  const [lanesOpen, setLanesOpen] = useState(false);

  const load = useCallback(() => {
    setError(undefined);
    setUnavailable(false);
    setRefreshing(true);
    fetchRv({
      window,
      basis: funding.basis,
      spreadBp: funding.spreadBp,
      h: hMonths,
      mpc: mpcEncoded,
      reinvest,
      reinvestRate,
      paths: pathsEncoded,
    })
      .then(setData)
      .catch((e: unknown) => {
        if (e instanceof BacktestUnavailable) setUnavailable(true);
        else setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => setRefreshing(false));
  }, [
    window, funding.basis, funding.spreadBp, hMonths,
    mpcEncoded, reinvest, reinvestRate, pathsEncoded,
  ]);

  useEffect(() => {
    load();
  }, [load]);

  const sector = useMemo(() => {
    if (!data) return undefined;
    return data.sectors.find((s) => s.id === sectorParam) ?? data.sectors[0];
  }, [data, sectorParam]);

  /* 오늘의 한 줄 — 서버 랭크 1위 [OWNER 2026-08-19 문구: "지금 XX가 가장
   * 매력적"]. 근거(Score·버퍼·순위변동)가 같은 줄에 붙고, 누르면 이력 창. */
  const top = useMemo(
    () => data?.credit.items.find((i) => i.rank === 1) ?? null,
    [data],
  );

  /* 실패·대기는 공용 상태 컴포넌트로 — 손 문장 셋이 리포의 ErrorState(재시도
   * 버튼)·LoadingState 와 딴 모양으로 서 있던 것의 정리(크리틱·CDS 점검). */
  if (unavailable) {
    return (
      <ErrorState
        what="RV 분석"
        detail="실행 중인 백엔드(:8200)가 필요해요 — 민평이 SQL 에만 있어서 미리 구워둘 수가 없어요."
        onRetry={load}
        retrying={refreshing}
      />
    );
  }
  if (error) {
    return <ErrorState what="RV 분석" detail={error} onRetry={load} retrying={refreshing} />;
  }
  if (!data || !sector) {
    return <LoadingState what="RV 분석" />;
  }

  const asofSplit = data.asof.irs != null && data.asof.irs !== data.asof.creditMatrix;

  return (
    /* 페이지는 **스크롤하지 않는다** — Backtest 와 같은 100vh 기둥 [OWNER
       2026-08-19 — "스크롤해야 하는 불편"]. 주인공(랭킹)이 남는 높이를 다 받고,
       세부는 클릭(이력 창)과 버튼(커브 레인 창) 뒤에 있다. */
    <VStack gap={1.5} width="100%" flexGrow={1} minHeight={0} className="sr-rv-root">
      {/* ── 조건 바 — 고정·불투명·**한 줄** ────────────────────────────────
          sticky 는 조건 요약(Cond 행)과 as-of 차단 문구까지다. 각주·제외·
          금통위는 바로 아래 **흐름**에 서서 위에서는 읽히고 스크롤하면 비켜난다
          — 2차 크리틱 실측: 각주까지 sticky 면 바가 107~250px 이 되어 행 20~74
          를 읽는 자세에서 랭킹 열 머리를 통째로 덮었다. */}
      <VStack className="sr-rv-bar" flexShrink={0} gap={0.5} width="100%">
        <HStack gap={1.5} alignItems="center" flexWrap="wrap">
          {/* 첫 화면은 필요한 정보만 [OWNER 2026-08-19] — 후보·H·조달·as-of
              다섯 사실만 상시이고, 조작(이력 창·금통위)과 세부(가중)는 우측 끝
              **설정** 하나로 접힌다.

              순서는 **언제 → 무엇으로** [OWNER 2026-08-19, 선택지 컨펌]: 소스별
              as-of 가 맨 앞이다. 다섯이 같은 무게로 서 있으면 읽는 사람이 매번
              날짜를 찾아 훑는데, 이 화면에서 가장 먼저 확인해야 하는 사실이
              그것이다(두 소스가 갈라진 날은 숫자의 뜻이 달라진다 — 아래 차단
              문구가 존재하는 이유). 계산 조건(H·조달)은 그 뒤로 물러난다.
              접거나 숨기지 않는다 — 다섯 다 상시라는 규칙은 그대로다. */}
          {/* 소스별 as-of — 갈라진 날은 강조까지 한다(rv1 B-2). */}
          <Cond k="민평" v={data.asof.creditMatrix} strong={asofSplit} />
          <Cond k="IRS" v={data.asof.irs ?? '—'} strong={asofSplit} />
          <Cond k="후보" v={`${data.candidates}개`} />
          {/* H 는 한 값이다 [OWNER 2026-08-20] — 두 레인이 같은 기간을 쓴다. */}
          <Cond k="H" v={`${data.hMonths}개월`} />
          <Cond k="조달" v={data.funding.label} />
          {window === 'all' ? <Cond k="이력 창" v="전체(2020~)" /> : null}
          {mpcEncoded ? <Cond k="금통위" v="조정 중" /> : null}
          {/* 기본이 아닌 조건만 선다 — 다섯 상시 사실 옆에 늘 붙어 있으면
              "필요한 정보만" 규칙(2026-08-19)이 무너진다. */}
          {reinvest !== 'none' ? (
            <Cond
              k="재투자"
              v={
                reinvest === 'manual'
                  ? `${REINVEST_LABEL[reinvest]} ${reinvestRate}%`
                  : REINVEST_LABEL[reinvest]
              }
            />
          ) : null}
          {activePaths.length > 0 ? (
            <Cond k="커브 경로" v={`${activePaths.length}개`} />
          ) : null}
          {/* 창·금통위 재조회 동안 옛 숫자가 서 있다 — 그 사실을 바가 말한다. */}
          {refreshing ? (
            <TextLegal as="span" color="fgMuted" noWrap>
              갱신 중…
            </TextLegal>
          ) : null}
          <Box style={{ marginLeft: 'auto' }}>
            <button
              type="button"
              className="sr-pillbtn"
              data-on={mpcOpen || undefined}
              aria-expanded={mpcOpen}
              onClick={() => setMpcOpen((v) => !v)}
            >
              설정
            </button>
          </Box>
        </HStack>
        {asofSplit ? (
          /* 차단 사항이라 이 문구만은 sticky 에 남는다 — 갈라진 날의 숫자를
             각주 없이 읽게 두면 안 된다(rv1 B-2). */
          <TextLegal as="span" color="fgMuted">
            두 소스의 종가 날짜가 달라요 — 스프레드·자산스왑 숫자는 민평 날짜
            기준이에요.
          </TextLegal>
        ) : null}
        {/* 설정 펼침 — 이력 창·금통위·가중이 여기 산다 [OWNER — "우측 맨 끝
            Setting 하나로"]. 몸통은 CDS Collapsible. */}
        {/* 설정 펼침 — 조작 컨트롤 전부가 여기 산다 [OWNER — "우측 맨 끝
            Setting 하나로"]. 몸통은 CDS Collapsible.

            ## 배치 규칙 셋 [2026-08-20 재정돈 — 다섯 줄이 잡동사니가 됐던 것]

            1. **레이블은 고정폭 열**(`SET_LABEL_W`). 글자 수만큼 자리를 먹게
               두면 컨트롤 시작점이 줄마다 53·58·73·92px 로 계단이 진다(실측).
            2. **그룹 셋**(보는 방식 / 계산 조건 / 시나리오)으로 나누고 그 사이
               에만 Divider 를 긋는다. 다섯 항목을 평평하게 쌓으면 무엇이 무엇과
               한 벌인지가 사라진다.
            3. **설명 문구는 컨트롤 아래 줄**, 레이블 열만큼 들여쓴다. 전에는
               보유기간·재투자는 컨트롤 뒤, 커브 경로는 레이블 옆이라 같은
               위계의 문장이 두 자리에 흩어져 있었다. */}
        <CdsCollapsible collapsed={!mpcOpen}>
          {/* width 100% — Divider 가 부모 폭을 못 받으면 컨트롤 오른쪽 끝에서
              끊겨, 바로 아래 전폭 구분선과 어긋난다(실측). */}
          <VStack gap={1.5} paddingY={1} width="100%">
            {/* ── 보는 방식 ─────────────────────────────────────────────── */}
            <SetGroup title="보는 방식">
              <SetRow label="이력 창">
                <button
                  type="button"
                  className="sr-pillbtn"
                  data-on={window === '52w' || undefined}
                  aria-pressed={window === '52w'}
                  onClick={() => setWindowParam(undefined)}
                >
                  52주
                </button>
                <button
                  type="button"
                  className="sr-pillbtn"
                  data-on={window === 'all' || undefined}
                  aria-pressed={window === 'all'}
                  onClick={() => setWindowParam('all')}
                >
                  전체
                </button>
                {/* 가중은 **읽기 전용 사실**이라 알약 뒤로 밀어 띄운다 — 같은
                    줄에 붙여 두면 눌리는 것처럼 보인다(재정돈 전 상태). */}
                <Box style={{ marginLeft: 'auto' }}>
                  <Cond
                    k="가중"
                    v={`절대 ${Math.round(data.credit.weights.abs * 100)} / 섹터 ${Math.round(
                      data.credit.weights.sector * 100,
                    )} / 커브 ${Math.round(data.credit.weights.curve * 100)}`}
                  />
                </Box>
              </SetRow>
            </SetGroup>

            <Divider direction="horizontal" />

            {/* ── 계산 조건 ─────────────────────────────────────────────── */}
            <SetGroup title="계산 조건">
              {/* 보유기간 H [OWNER 2026-08-20 — 워크북 만기선택!B7]. 알약인
                  이유는 값이 몇 개뿐이고 옆 줄들과 같은 컨트롤 문법이어야
                  하기 때문이다. */}
              <SetRow label="보유기간" note="같은 섹터끼리와 크레딧 RV 가 같은 기간을 써요">
                {[3, 6, 12].map((mo) => (
                  <button
                    key={mo}
                    type="button"
                    className="sr-pillbtn"
                    data-on={hMonths === mo || undefined}
                    aria-pressed={hMonths === mo}
                    onClick={() => setHMonths(mo)}
                  >
                    {mo}개월
                  </button>
                ))}
              </SetRow>

              {/* 재투자 [OWNER 2026-08-20 — 워크북 만기선택!B11]. 만기가 H 안에
                  드는 후보의 남은 기간을 어떻게 굴리나. */}
              <SetRow label="재투자" note="만기가 보유기간 안에 드는 후보에만 붙어요">
                {(['none', 'residual', 'manual'] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    className="sr-pillbtn"
                    data-on={reinvest === mode || undefined}
                    aria-pressed={reinvest === mode}
                    onClick={() => setReinvest(mode)}
                  >
                    {REINVEST_LABEL[mode]}
                  </button>
                ))}
                {reinvest === 'manual' ? (
                  <NumField
                    value={reinvestRate}
                    label="재투자 금리(연 %)"
                    suffix="%"
                    width={SET_FIELD_W}
                    onCommit={(v) => setReinvestRate(Math.max(-10, Math.min(30, v)))}
                  />
                ) : null}
              </SetRow>
            </SetGroup>

            <Divider direction="horizontal" />

            {/* ── 시나리오 ──────────────────────────────────────────────── */}
            <SetGroup title="시나리오">
              {/* 금통위와 커브 경로는 **같은 격자 문법**이다 — 캡션 한 줄 위에
                  같은 폭의 칸들. 전에는 금통위 캡션이 위 줄에 떠서 이력 창의
                  부속처럼 읽혔다(실측). */}
              <SetRow
                label="금통위"
                align="flex-end"
                note="분석 시작일 이후 회의만 일할로 반영해요"
                /* 되돌리기 알약 — CDS `Button size="s"` 는 **36px** 이라 이 줄의
                   이웃(32px 알약·입력)과 4px 어긋났다 [감사 2026-08-25]. 앱의
                   행 컨트롤은 `.sr-pillbtn` 이고, `data-fill` 이 secondary 의
                   회색 채움을 진다(CSS 주석의 그 자리). */
                action={
                  mpcEncoded ? (
                    <button type="button" className="sr-pillbtn" data-fill onClick={() => setMpc({})}>
                      전부 0으로
                    </button>
                  ) : null
                }
              >
                {data.meetings.map((m) => (
                  <VStack key={m.date} gap={0.25} width={SET_FIELD_W}>
                    <Text font="caption" as="span" color="fgMuted" noWrap>
                      {m.date.slice(5)}
                    </Text>
                    <NumField
                      value={mpc[m.date] ?? 0}
                      label={`금통위 ${m.date} 변동(bp)`}
                      suffix="bp"
                      width={SET_FIELD_W}
                      onCommit={(v) =>
                        setMpc((prev) => ({ ...prev, [m.date]: Math.max(-100, Math.min(100, v)) }))
                      }
                    />
                  </VStack>
                ))}
              </SetRow>

              {/* 비평행 커브 경로 [OWNER 2026-08-20 — 워크북 케이스 C/C-2].
                  테너 캡션은 **두 경로가 공유**한다 — 같은 격자를 두 번 적으면
                  줄이 여섯이 되고 무엇이 머리인지 사라진다. */}
              <SetRow
                label="커브 경로"
                align="flex-start"
                note="테너마다 다르게 움직이는 경우예요 · 비워 두면 열이 안 생겨요"
                action={
                  pathsEncoded ? (
                    <button
                      type="button"
                      className="sr-pillbtn"
                      data-fill
                      onClick={() => setPaths([{}, {}])}
                    >
                      전부 0으로
                    </button>
                  ) : null
                }
              >
                <VStack gap={0.5}>
                  {/* 공유 캡션 — 왼쪽에 경로 이름 자리만큼 빈 칸을 둔다. */}
                  <HStack gap={1} alignItems="baseline">
                    <Box width={SET_PATH_W} />
                    {tenorList.map((t) => (
                      <Box key={t} width={SET_FIELD_W}>
                        <Text font="caption" as="span" color="fgMuted" noWrap>
                          {t}
                        </Text>
                      </Box>
                    ))}
                  </HStack>
                  {paths.map((row, pi) => (
                    <HStack key={pi} gap={1} alignItems="center">
                      <Box width={SET_PATH_W}>
                        <Text font="legal" as="span" color="fgMuted" noWrap>
                          경로 {pi + 1}
                        </Text>
                      </Box>
                      {tenorList.map((t) => (
                        <NumField
                          key={t}
                          value={row[t] ?? 0}
                          suffix="bp"
                          width={SET_FIELD_W}
                          label={`경로 ${pi + 1} ${t} 변동(bp)`}
                          onCommit={(v) =>
                            setPaths((prev) =>
                              prev.map((r, i) =>
                                i === pi ? { ...r, [t]: Math.max(-200, Math.min(200, v)) } : r,
                              ),
                            )
                          }
                        />
                      ))}
                    </HStack>
                  ))}
                </VStack>
              </SetRow>
            </SetGroup>
          </VStack>
        </CdsCollapsible>
      </VStack>

      {/* ── 히어로 — Main 의 그 문법이다(PreviewPane: "이름은 작게, **값은
          크게**"). 이 화면의 값은 숫자가 아니라 오늘의 1위 종목이라, 종목명이
          TextDisplay3 로 선다 [OWNER 2026-08-19 — "한 줄인데 눈에 안 띔"].
          메타(Score·버퍼·순위변동)는 히어로 옆 뮤트 — Main 히어로의 변화
          배지 자리다. */}
      {top ? (
        <VStack flexShrink={0} gap={0} width="100%">
          <TextLabel1 as="span" color="fgMuted" noWrap>
            지금 가장 매력적이에요
          </TextLabel1>
          <HStack gap={1.5} alignItems="baseline" flexWrap="wrap">
            <button
              type="button"
              className="sr-rv-linkbtn"
              aria-label={`${top.sectorLabel} ${top.tenor} 이력 단면 열기`}
              onClick={() => setDrill(top)}
            >
              <TextDisplay3 as="span" noWrap>
                {top.sectorLabel} {top.tenor}
              </TextDisplay3>
            </button>
            <TextBody as="span" color="fgMuted" tabularNumbers noWrap>
              Score {top.score?.toFixed(0)} · 한 달 {sig(top.trMonthBp)}bp
              {top.pctLastWeek != null ? ` · 지난주 ${top.pctLastWeek.toFixed(0)}%` : ''}
              {top.rankDelta != null
                ? top.rankDelta === 0
                  ? ' · 순위변동 없음'
                  : ` · ${top.rankDelta > 0 ? '▲' : '▼'}${Math.abs(top.rankDelta)}`
                : ''}
            </TextBody>
          </HStack>
        </VStack>
      ) : null}

      {/* ── 본 화면: [랭킹(주인공) | 사분면(미리보기)] — Backtest 의 표+미리보기
          문법 그대로 [OWNER — "위계를 살려 중요한 정보를 앞으로"]. 표 카드의
          basis 980 은 Backtest 표 카드의 그 규율(page.tsx 의 산술)이고,
          미리보기가 나머지를 받는다. 세부 셋(동일섹터·동일테너·Score 히트맵)은
          머리의 "커브 레인" 버튼이 여는 창 — Backtest 의 백테스트 버튼 자리다. */}
      <HStack gap={2} alignItems="stretch" width="100%" flexGrow={1} minHeight={0}>
        <VStack
          className="sr-card"
          flexBasis={980}
          flexGrow={0}
          flexShrink={1}
          maxWidth={980}
          minHeight={0}
        >
          <HStack
            alignItems="center"
            justifyContent="space-between"
            gap={1}
            paddingX={2}
            paddingTop={1.5}
            paddingBottom={0.5}
          >
            <TextLabel1 as="h2" noWrap>
              크레딧 RV — 랭킹
            </TextLabel1>
            {/* 카드 머리의 컨트롤은 Main pill 크기(32px)다 — CDS Button(s,
                36px)은 14px 제목 옆에서 위계를 눌렀다. */}
            {/* "커브 레인" → "상세 분석" [OWNER 2026-08-19 — 어휘 순화 컨펌]. */}
            <button
              type="button"
              className="sr-pillbtn"
              data-fill="true"
              onClick={() => setLanesOpen(true)}
            >
              상세 분석
            </button>
          </HStack>
          <RankingTable
            items={data.credit.items}
            onSelect={setDrill}
            onHover={setHovered}
            highlightId={hovered?.seriesId ?? null}
            exclusions={data.credit.exclusions}
            hMonths={data.hMonths}
            window={window}
          />
        </VStack>

        {/* 미리보기 — 사분면이 표의 hover 를 따라온다(PreviewPane 문법). */}
        <VStack className="sr-card" flexGrow={1} flexShrink={1} minWidth={420} minHeight={0}>
          <VStack gap={0.25} paddingX={2} paddingTop={1.5} paddingBottom={0.5}>
            <TextLabel1 as="h2" noWrap>
              크레딧 RV — 사분면
            </TextLabel1>
            <TextLegal as="span" color="fgMuted" noWrap>
              민평 {data.asof.creditMatrix} · {window === '52w' ? '52주' : '전체 이력'} 창
            </TextLegal>
          </VStack>
          <RvScatter
            items={data.credit.items}
            onSelect={setDrill}
            highlightId={hovered?.seriesId ?? null}
            onHover={setHovered}
          />
        </VStack>
      </HStack>

      {/* ── 커브 레인 — 세부 셋을 담는 창(세부는 인터랙션 뒤). ───────────────── */}
      {lanesOpen ? (
        <FloatingWindow
          windowKey="rvlanes"
          title="상세 분석"
          width={1180}
          aside={
            <TextLegal as="span" color="fgMuted" noWrap>
              같은 섹터끼리 · 같은 만기끼리 · Score
            </TextLegal>
          }
          onClose={() => setLanesOpen(false)}
        >
          <VStack gap={1} width="100%" paddingY={1}>
            <HStack
              alignItems="center"
              justifyContent="space-between"
              gap={1}
              paddingX={2}
              paddingTop={0.5}
            >
              <TextLabel1 as="h3" noWrap>
                같은 섹터끼리 — 만기 × Δy 총수익
              </TextLabel1>
              <Box width={160}>
                {/* font legal(13) — 컨트롤 값 13px 규칙(popup.ts 의 근거). */}
                <Select
                  size="s"
                  font="legal"
                  styles={DROPDOWN_STYLES}
                  accessibilityLabel="섹터"
                  value={sector.id}
                  onChange={(v) => v && setSectorParam(v === data.sectors[0].id ? undefined : v)}
                  options={data.sectors.map((s) => ({ value: s.id, label: s.label }))}
                />
              </Box>
            </HStack>
            <SectorLane
              sector={sector}
              dys={data.dys}
              hMonths={data.hMonths}
              pathCount={data.paths.length}
            />

            <VStack paddingX={2} paddingTop={0.5}>
              <TextLabel1 as="h3" noWrap>
                같은 만기끼리 — 스프레드 백분위
              </TextLabel1>
            </VStack>
            <TenorHeat heat={data.heat} window={window} items={data.credit.items} onSelect={setDrill} />

            <VStack paddingX={2} paddingTop={0.5}>
              <TextLabel1 as="h3" noWrap>
                크레딧 RV — Score 히트맵
              </TextLabel1>
            </VStack>
            <ScoreHeat items={data.credit.items} onSelect={setDrill} />
          </VStack>
        </FloatingWindow>
      ) : null}

      {drill ? <DrillWindow point={drill} window={window} onClose={() => setDrill(null)} /> : null}
    </VStack>
  );
}
