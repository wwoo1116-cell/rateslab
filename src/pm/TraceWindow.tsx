'use client';

/* 트레이드 추적 창 [OWNER 2026-09-28 — "그 트레이드를 클릭했을 때 진입일 시점부터
 * PnL 을 분해시켜서 그게 트레이스가 가능하게"].
 *
 * ## 산술을 새로 만들지 않는다
 *
 * 페이퍼 북의 손익은 한 수(rateSign × Δbp × DV01 − 비용)라 분해가 없다. 분해는
 * **백테스트 엔진**이 이미 한다 — 서버가 다리들을 그 엔진의 포지션으로 옮겨 값매기고
 * (`/api/paper/trace` 의 `book` 은 `/api/backtest` 응답 그대로), 이 창은 Backtest 창의
 * **부품을 그대로 임포트**한다: 누적 손익은 `TimeChart`, 일별 대사는 `ReconStack` 과
 * `backtest/recon.ts` 의 그 함수들. 「Backtest 를 참고한다 = 그 화면의 부품을
 * 임포트한다」(CLAUDE.md 캐논).
 *
 * ## 두 자리가 다른 것은 진입가뿐이다 — 그래서 대조 표가 먼저 선다
 *
 * 엔진은 진입일 **종가**로 치고 장부는 **내가 체결한 레벨**이다. 그 차이에 이름을
 * 붙인다 — 「체결 차이」. 그러면
 *
 *     장부 손익 = 체결 차이 + 엔진 손익(평가+캐리+롤다운+개시+조달) − 비용 + 차이
 *
 * 이고, 「차이」는 장부의 선형(진입일 DV01 고정)과 엔진의 재평가가 갈리는 몫이다.
 * 지우지 않고 열에 세운다 — 잔차 열이 하는 일이다. 못 센 성분은 «—»(공란 정책).
 */

import { useEffect, useState } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@coinbase/cds-web/tables';
import { Text } from '@coinbase/cds-web/typography';

import {
  backtestDays, bondReconNote, futuresReconNote, reconNote, reconPair, reconTenors,
} from '@/backtest/recon';
import { TimeChart, type TimeLine } from '@/chart/TimeChart';
import { BacktestUnavailable } from '@/lib/api';
import { fmtKrw } from '@/lib/krw';
import { directionClass } from '@/table/tint';
import { Cond } from '@/ui/Cond';
import { ErrorState, LoadingState } from '@/ui/DataState';
import { FloatingWindow } from '@/ui/window/FloatingWindow';
import { ReconStack } from '@/ui/window/ReconStack';

import { fetchTrace, type PaperTrace, type PaperTraceRow } from './api';
import { zWord } from './words';

const MINUS = '−';

/** 계열 값 한 칸 — 계열의 자기 단위(bp 둘째 자리 · % 셋째 자리). */
function seriesWord(v: number | null | undefined, unit: string | null | undefined): string {
  if (v == null) return MINUS;
  return `${unit === '%' ? v.toFixed(3) : v.toFixed(2)}${unit ?? ''}`;
}

/**
 * 계열의 경로 [OWNER 2026-09-28 — "추적 … 정교화"] — 「어디서 들어와 어디까지 왔고,
 * 선이 어디에 있나」를 한 그림으로. 값은 잉크 주선, 중심선은 흐린 점선, 청산선은
 * 상승색·손절선은 하락색 점선(둘은 방향이 아니라 **뜻**이다 — 청산은 계획대로 나가는
 * 것, 손절은 아니다 · 밴드 칸이 쓰는 그 규칙). 밴드가 안 선 봉은 `null` 이라 선이
 * 끊긴다. 진입 자리는 세로선.
 */
function PathChart({ path }: { path: PaperTrace['path'] }) {
  if (path.why || !path.dates?.length) {
    return (
      <Text font="legal" as="span" color="fgMuted">
        {`${MINUS} ${path.why ?? '계열 경로가 없어요'}`}
      </Text>
    );
  }
  const dates = path.dates;
  const unit = path.unit ?? '';
  const f = (v: number) => (unit === '%' ? v.toFixed(3) : v.toFixed(2));
  const lines: TimeLine[] = [
    { id: 'v', values: path.values ?? [], color: (pal) => pal.fg, width: 2, beacon: true,
      format: (v) => `${f(v)}${unit}` },
    { id: 'ma', values: path.ma ?? [], color: (pal) => pal.fgMutedSoft, dash: true,
      format: (v) => `${f(v)}${unit}` },
    { id: 'exit', values: path.exit ?? [], color: (pal) => pal.up, dash: true,
      format: (v) => `${f(v)}${unit}` },
    { id: 'stop', values: path.stop ?? [], color: (pal) => pal.down, dash: true,
      format: (v) => `${f(v)}${unit}` },
  ];
  const markLines = path.entryIdx == null ? [] : [{ index: path.entryIdx, label: '진입' }];
  return (
    <VStack gap={0.5} width="100%">
      <HStack gap={1} alignItems="baseline" flexWrap="wrap">
        <Text font="label1" as="span" noWrap>{`계열 경로 — ${path.series ?? ''}`}</Text>
        <Text font="legal" as="span" color="fgMuted" noWrap>
          잉크 = 계열 값 · 흐린 점선 = 중심선 · 상승색 점선 = 청산선 · 하락색 점선 = 손절선
        </Text>
      </HStack>
      <Box width="100%">
        <TimeChart
          dates={dates}
          lines={lines}
          markLines={markLines}
          height={220}
          precision={unit === '%' ? 3 : 2}
          accessibilityLabel={`${path.series ?? '계열'} 경로 — 값·중심선·청산선·손절선`}
          hoverLabel={(i) => {
            const v = path.values?.[i];
            const e = path.exit?.[i];
            const s = path.stop?.[i];
            return `${dates[i]} 값 ${v == null ? MINUS : f(v)}${unit}`
              + ` · 청산선 ${e == null ? MINUS : f(e)} · 손절선 ${s == null ? MINUS : f(s)}`;
          }}
        />
      </Box>
    </VStack>
  );
}

/** 돈 한 칸 — 부호 방향색, 못 센 것은 «—». */
function Money({ v, muted, strong }: {
  v: number | null | undefined; muted?: boolean;
  /** 합계 줄 — 한 단계 무겁게. 뮤트 칸(비용·차이)은 뮤트를 유지한다. */
  strong?: boolean;
}) {
  if (typeof v !== 'number') {
    return <Text font="legal" as="span" color="fgMuted" tabularNumbers noWrap>{MINUS}</Text>;
  }
  return (
    <Text font={muted ? 'legal' : strong ? 'label1' : 'label2'} as="span" tabularNumbers noWrap
      color={muted ? 'fgMuted' : undefined}
      className={muted ? undefined : directionClass(v)}>
      {fmtKrw(v)}
    </Text>
  );
}

/* 열은 **두 묶음**이다 [OWNER 2026-10-01 — 추적 손질]. 열둘이 한 줄로 서면 어디까지가
   재료이고 어디부터가 결과인지 읽는 사람이 세어야 했다. 묶음 머리가 그 선을 긋는다.
   ⚠`group` 이 **이어진 것끼리만** 묶이므로 목록의 차례가 곧 묶음의 경계다. */
const COLS: { key: keyof PaperTraceRow; label: string; group: '성분' | '합계' }[] = [
  { key: 'exec', label: '체결 차이', group: '성분' },
  { key: 'valuation', label: '평가', group: '성분' },
  { key: 'carry', label: '캐리', group: '성분' },
  { key: 'rolldown', label: '롤다운', group: '성분' },
  { key: 'startup', label: '개시', group: '성분' },
  { key: 'funding', label: '조달', group: '성분' },
  { key: 'cost', label: '비용', group: '성분' },
  { key: 'engine', label: '엔진 합', group: '합계' },
  { key: 'paper', label: '장부 손익', group: '합계' },
  { key: 'residual', label: '차이', group: '합계' },
];

/** 묶음 머리의 칸 수 — `COLS` 에서 **유도한다**(손으로 세지 않는다). */
const COL_GROUPS = COLS.reduce<{ label: string; span: number }[]>((out, c) => {
  const last = out[out.length - 1];
  if (last && last.label === c.group) last.span += 1;
  else out.push({ label: c.group, span: 1 });
  return out;
}, []);

function Th({ children, num, colSpan, center }: {
  children?: React.ReactNode; num?: boolean; colSpan?: number; center?: boolean;
}) {
  return (
    <TableCell as="th" scope="col" colSpan={colSpan}
      className={num ? 'sr-num' : undefined}
      justifyContent={center ? 'center' : num ? 'flex-end' : undefined}>
      <Text font="caption" as="span" color="fgMuted" noWrap>{children}</Text>
    </TableCell>
  );
}

export function TraceWindow({ ns, title, onClose }: {
  /** 추적할 다리 번호들 — 묶음(태그) 하나거나 다리 하나. */
  ns: readonly number[];
  title: string;
  onClose: () => void;
}) {
  const [data, setData] = useState<PaperTrace>();
  const [err, setErr] = useState<string>();
  /** 다시 시도 — 실패한 창이 스스로 다시 묻는다(`ErrorState` 의 그 버튼). */
  const [tick, setTick] = useState(0);
  const key = ns.join(',');

  useEffect(() => {
    setData(undefined);
    setErr(undefined);
    const ctl = new AbortController();
    fetchTrace(ns, ctl.signal)
      .then((t) => { if (!ctl.signal.aborted) setData(t); })
      .catch((e: unknown) => {
        if (ctl.signal.aborted) return;
        setErr(e instanceof BacktestUnavailable
          ? '백엔드가 이 라우트를 몰라요 — 새 판으로 재기동해야 해요.'
          : e instanceof Error ? e.message : String(e));
      });
    return () => ctl.abort();
    // `key` 가 곧 `ns` 의 내용이다 — 배열 참조가 바뀌어도 내용이 같으면 다시 안 묻는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, tick]);

  const book = data?.book;
  const dates = book?.points.map((p) => p.t) ?? [];
  const pnlColor = (book?.pnl ?? 0) >= 0 ? 'var(--sr-up)' : 'var(--sr-down)';
  /* 누적 손익 — Backtest 아래 차트와 **같은 잉크**(부호 방향색 + 채운 면, 흐리게). */
  const lines: TimeLine[] = book ? [{
    id: 'pnl',
    values: book.points.map((p) => p.pnl),
    color: (pal) => pal.resolve(pnlColor),
    area: 'solid',
    areaColor: (pal) => pal.dim(pnlColor, 14),
    format: (v) => fmtKrw(v),
  }] : [];
  /* 진입일 — 「그 날 들어갔다」는 사실을 세로선으로. 같은 날이면 하나로. */
  const entryIdx = [...new Set((data?.rows ?? []).map((r) => r.entry).filter(Boolean))]
    .map((d) => dates.indexOf(d as string)).filter((i) => i >= 0);
  const markLines = entryIdx.map((index) => ({ index, label: '진입' }));
  /* 머리띠 ①의 재료 — **가장 이른 진입일**과 거기부터 엔진 마지막 날까지의 날수.
     달력 날수다(영업일 아님) — 「며칠째 들고 있나」는 사람이 달력으로 센다. */
  const entryT = [...(data?.rows ?? [])].map((r) => r.entry).filter(Boolean).sort()[0];
  const heldDays = (entryT && book)
    ? Math.max(0, Math.round(
        (Date.parse(book.to) - Date.parse(entryT)) / 86_400_000))
    : null;
  const pair = book ? reconPair(book.recon) : undefined;
  const blocks = pair ? [pair.swap, pair.bond, pair.futures].filter(Boolean).length : 0;

  return (
    <FloatingWindow
      windowKey="papertrace"
      title={`트레이드 추적 — ${title}`}
      /* 대조 표가 열셋이라 1120 에서는 「차이」 열이 가로 스크롤 뒤로 숨는다(실측
         2026-09-28). 1240 이면 1440 뷰포트에도 든다. */
      width={1240}
      aside={
        <Text font="caption" as="span" color="fgMuted" noWrap>
          {book ? `${book.from} → ${book.to} · 백테스트 엔진의 분해예요` : '다리들을 엔진에 싣는 중…'}
        </Text>
      }
      onClose={onClose}
    >
      {/* 창 몸통 리듬은 Backtest 창과 한 값(padding 2 · gap 2). */}
      <VStack gap={2} padding={2} width="100%">
        {err ? (
          <ErrorState what="트레이드 추적" detail={err} onRetry={() => setTick((t) => t + 1)} />
        ) : !data || !book ? (
          <LoadingState what="트레이드 추적" />
        ) : (
          <>
            {/* ── 머리띠 ① **지금 무엇을 보고 있나** [OWNER 2026-10-01 — 추적 손질].
                종전에는 창을 열면 바로 «계열 밴드»가 나와서, 이 창이 어느 트레이드의
                어느 구간을 말하는지는 제목과 부제에 흩어져 있었다. 트레이드를 읽는
                사람이 먼저 묻는 것은 «언제 들어가 며칠째이고 지금 얼마인가»다. */}
            <HStack className="sr-rv-bar" gap={1.5} alignItems="center" flexWrap="wrap" width="100%">
              <Cond k="진입" v={entryT ?? MINUS} />
              <Cond k="보유" v={heldDays == null ? MINUS : `${heldDays}일`} />
              <Cond k="다리" v={`${data.rows.length}개`} />
              <Cond k="장부 손익"
                v={data.total.paper == null ? MINUS : fmtKrw(data.total.paper)} strong />
              <Cond k="기준" v={data.basis?.head === 'live' ? '머리띠·그림 장중 · 표 종가' : '종가'} />
            </HStack>

            {/* ── 머리띠 ② 묶음의 계열 시선(내 레벨 · 지금 · Δ · 밴드 · 계열 선) ──
                표의 조건 바와 같은 부품(`Cond`)이다. 계열이 없으면 사유 한 줄. */}
            {data.group.series ? (
              <HStack className="sr-rv-bar" gap={1.5} alignItems="center" flexWrap="wrap" width="100%">
                <Cond k="계열" v={data.group.series} strong />
                <Cond k="내 레벨" v={`${seriesWord(data.group.myLevel, data.group.unit)}${
                  data.group.myBasis === 'fill' ? ' (내 체결)' : data.group.myBasis === 'close' ? ' (진입일 종가)' : ''}`} />
                <Cond k="지금" v={`${seriesWord(data.group.now, data.group.unit)}${
                  data.group.asof ? ` (${data.group.asof})` : ''}`} strong />
                <Cond k="Δ" v={data.group.delta == null ? MINUS
                  : `${data.group.delta >= 0 ? '+' : MINUS}${seriesWord(Math.abs(data.group.delta), data.group.unit)}`} strong />
                <Cond k="밴드" v={data.group.track?.z == null ? MINUS
                  : `${zWord(data.group.track.z)} (진입 ${zWord(data.group.track.entryZ)})`} />
                <Cond k="청산 · 손절" v={data.group.track?.exitLevel == null ? MINUS
                  : `${seriesWord(data.group.track.exitLevel, data.group.unit)} · ${seriesWord(data.group.track.stopLevel, data.group.unit)}`} />
              </HStack>
            ) : (
              <Text font="legal" as="span" color="fgMuted">
                {`${MINUS} ${data.group.seriesWhy ?? '계열이 없어요'}`}
              </Text>
            )}

            {/* ── 그림 둘은 **나란히** [OWNER 2026-10-01 — 추적 손질] ──────────
                계열 경로(220)와 누적 손익(200)이 세로로 쌓여 있어 표를 보려면 그림
                둘을 지나야 했고, 창이 한 화면에 안 들었다. 둘은 **같은 기간의 두
                얼굴**(계열이 어디 있나 / 돈이 얼마가 됐나)이라 나란히 두면 눈이
                한 번에 읽는다. 좁아지면 `flexWrap` 이 도로 세로로 세운다. */}
            <HStack gap={2} width="100%" alignItems="stretch" flexWrap="wrap">
              <VStack flexGrow={1} flexShrink={1} flexBasis={520} minWidth={420}>
                <PathChart path={data.path} />
              </VStack>
              <VStack gap={0.5} flexGrow={1} flexShrink={1} flexBasis={520} minWidth={420}>
                <HStack gap={1} alignItems="baseline" flexWrap="wrap">
                  <Text font="label1" as="span" noWrap>누적 손익 (엔진, 종가 진입)</Text>
                  <Text font="legal" as="span" color="fgMuted" noWrap>
                    {`총 ${fmtKrw(book.pnl)} · 최대 ${fmtKrw(book.maxProfit)} · 최저 ${fmtKrw(book.maxLoss)}`}
                  </Text>
                </HStack>
                <Box width="100%">
                  <TimeChart
                    dates={dates}
                    lines={lines}
                    markLines={markLines}
                    priceLines={[{ value: 0, color: (pal) => pal.line }]}
                    height={220}
                    precision={0}
                    accessibilityLabel="트레이드 누적 손익"
                    hoverLabel={(i) => `${dates[i]} 누적 ${fmtKrw(book.points[i]?.pnl ?? 0)}`}
                  />
                </Box>
              </VStack>
            </HStack>

            {/* ── 대조 표 — 장부 손익 = 체결 차이 + 엔진 손익 − 비용 + 차이 ── */}
            <VStack gap={0.5} width="100%">
              <div className="sr-rv-scroll">
                <Table bordered={false}>
                  <TableHeader>
                    {/* 묶음 머리 — 어디까지가 재료이고 어디부터가 결과인가. */}
                    <TableRow>
                      <Th />
                      <Th />
                      {COL_GROUPS.map((g) => (
                        <Th key={g.label} colSpan={g.span} center>{g.label}</Th>
                      ))}
                    </TableRow>
                    <TableRow>
                      <Th>다리</Th>
                      <Th num>내 레벨 → 종가</Th>
                      {COLS.map((c) => <Th key={c.key} num>{c.label}</Th>)}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.rows.map((r) => (
                      <TableRow key={r.n}>
                        <TableCell>
                          <VStack as="span" className="sr-name-stack">
                            <Text font="label1" as="span" noWrap>{r.label ?? r.id ?? `${r.n}번`}</Text>
                            <Text font="legal" as="span" color="fgMuted" noWrap>
                              {r.exit && r.exit !== book.to ? `${r.entry} → ${r.exit}` : `${r.entry} 진입`}
                            </Text>
                          </VStack>
                        </TableCell>
                        <TableCell className="sr-num" justifyContent="flex-end">
                          <Text font="legal" as="span" color="fgMuted" tabularNumbers noWrap>
                            {`${r.level.toFixed(3)} → ${r.entryClose == null ? MINUS : r.entryClose.toFixed(3)}`}
                          </Text>
                        </TableCell>
                        {COLS.map((c) => (
                          <TableCell key={c.key} className="sr-num" justifyContent="flex-end">
                            <Money v={r[c.key] as number | null} muted={c.key === 'cost' || c.key === 'residual'} />
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                    {data.rows.length > 1 ? (
                      <TableRow>
                        <TableCell>
                          <Text font="label1" as="span" noWrap>합계</Text>
                        </TableCell>
                        <TableCell className="sr-num" justifyContent="flex-end">
                          <Text font="legal" as="span" color="fgMuted" noWrap>{MINUS}</Text>
                        </TableCell>
                        {COLS.map((c) => (
                          <TableCell key={c.key} className="sr-num" justifyContent="flex-end">
                            {/* 합계 줄의 수는 다리 줄보다 **무겁다** — 종전에는
                                같은 활자라 어디가 결론인지 눈이 안 멈췄다. */}
                            <Money v={data.total[c.key as keyof PaperTrace['total']]}
                              muted={c.key === 'cost' || c.key === 'residual'} strong />
                          </TableCell>
                        ))}
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </div>
              <Text font="legal" as="span" color="fgMuted" maxWidth={1000}>
                장부 손익 = 체결 차이 + 엔진 합(평가 + 캐리 + 롤다운 + 개시 + 조달) − 비용 + 차이.
                체결 차이는 내가 체결한 레벨과 엔진이 친 진입일 종가의 거리예요. 차이는 장부의
                선형(진입일 DV01 고정)과 엔진의 재평가가 갈리는 몫이고, 지우지 않고 적어요.
              </Text>
              {/* ★**이 표는 종가다** [적대 검증 2026-09-28]. 위의 머리띠·그림은 장중일 수
                  있어서, 아무 말도 안 하면 같은 트레이드가 창 안에서 두 수로 적힌다.
                  두 수를 다 서버가 낸다(§16) — 여기서 빼지 않는다. */}
              {data.basis?.head === 'live' ? (
                <Text font="legal" as="span" color="fgMuted" maxWidth={1000}>
                  {data.basis.why}
                  {data.basis.paperLive != null
                    ? ` 장중으로 매기면 이 트레이드의 장부 손익은 ${fmtKrw(data.basis.paperLive)}이고,`
                      + ` 위 표의 종가 기준은 ${data.total.paper != null ? fmtKrw(data.total.paper) : MINUS}예요.`
                    : ''}
                </Text>
              ) : null}
            </VStack>


            {/* ── 일별 대사 — Backtest 창의 그 스택, 표마다 자기 달력 ── */}
            {pair?.swap ? (
              <VStack gap={0.5} width="100%">
                {blocks > 1 ? (
                  <Text font="caption" as="span" color="fgMuted">스왑 대사 — IRS 달력</Text>
                ) : null}
                <ReconStack days={backtestDays(pair.swap)} tenors={reconTenors(pair.swap)}
                  defaultOrder="desc" note={reconNote(pair.swap)} maxHeight="32vh" />
              </VStack>
            ) : null}
            {pair?.bond ? (
              <VStack gap={0.5} width="100%">
                {blocks > 1 ? (
                  <Text font="caption" as="span" color="fgMuted">채권 대사 — 민평 달력</Text>
                ) : null}
                <ReconStack days={backtestDays(pair.bond)} tenors={reconTenors(pair.bond)}
                  defaultOrder="desc" note={bondReconNote(pair.bond)} maxHeight="32vh" />
              </VStack>
            ) : null}
            {pair?.futures ? (
              <VStack gap={0.5} width="100%">
                {blocks > 1 ? (
                  <Text font="caption" as="span" color="fgMuted">선물 대사 — 선물 달력</Text>
                ) : null}
                <ReconStack days={backtestDays(pair.futures)} tenors={reconTenors(pair.futures)}
                  defaultOrder="desc" note={futuresReconNote(pair.futures)} maxHeight="32vh" />
              </VStack>
            ) : null}
          </>
        )}
      </VStack>
    </FloatingWindow>
  );
}
