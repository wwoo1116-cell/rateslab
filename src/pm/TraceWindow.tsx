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
import { ErrorState, LoadingState } from '@/ui/DataState';
import { FloatingWindow } from '@/ui/window/FloatingWindow';
import { ReconStack } from '@/ui/window/ReconStack';

import { fetchTrace, type PaperTrace, type PaperTraceRow } from './api';

const MINUS = '−';

/** 돈 한 칸 — 부호 방향색, 못 센 것은 «—». */
function Money({ v, muted }: { v: number | null | undefined; muted?: boolean }) {
  if (typeof v !== 'number') {
    return <Text font="legal" as="span" color="fgMuted" tabularNumbers noWrap>{MINUS}</Text>;
  }
  return (
    <Text font={muted ? 'legal' : 'label2'} as="span" tabularNumbers noWrap
      color={muted ? 'fgMuted' : undefined}
      className={muted ? undefined : directionClass(v)}>
      {fmtKrw(v)}
    </Text>
  );
}

const COLS: { key: keyof PaperTraceRow; label: string; help?: string }[] = [
  { key: 'exec', label: '체결 차이' },
  { key: 'valuation', label: '평가' },
  { key: 'carry', label: '캐리' },
  { key: 'rolldown', label: '롤다운' },
  { key: 'startup', label: '개시' },
  { key: 'funding', label: '조달' },
  { key: 'cost', label: '비용' },
  { key: 'engine', label: '엔진 합' },
  { key: 'paper', label: '장부 손익' },
  { key: 'residual', label: '차이' },
];

function Th({ children, num }: { children: React.ReactNode; num?: boolean }) {
  return (
    <TableCell as="th" scope="col" className={num ? 'sr-num' : undefined}
      justifyContent={num ? 'flex-end' : undefined}>
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
            {/* ── 대조 표 — 장부 손익 = 체결 차이 + 엔진 손익 − 비용 + 차이 ── */}
            <VStack gap={0.5} width="100%">
              <div className="sr-rv-scroll">
                <Table bordered={false}>
                  <TableHeader>
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
                            <Money v={data.total[c.key as keyof PaperTrace['total']]}
                              muted={c.key === 'cost' || c.key === 'residual'} />
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
            </VStack>

            {/* ── 누적 손익 — 진입일부터, 엔진의 하루 단위 ── */}
            <VStack gap={0.5} width="100%">
              <HStack gap={1} alignItems="baseline">
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
                  height={200}
                  precision={0}
                  accessibilityLabel="트레이드 누적 손익"
                  hoverLabel={(i) => `${dates[i]} 누적 ${fmtKrw(book.points[i]?.pnl ?? 0)}`}
                />
              </Box>
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
