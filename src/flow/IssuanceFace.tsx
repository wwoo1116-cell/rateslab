'use client';

/* 「발행」 면 — 국고채 입찰 결과·공급·강도 [OWNER 2026-10-19].
 *
 * Flow 세입자의 **셋째 면**이다. 수급 두 면이 「누가 받고 누가 냈나」(수요)를
 * 말하고, 이 면은 「얼마가 새로 나왔나」(공급)를 말한다 — 같은 세그먼트 한 칸
 * 옆에 서는 이유다. 원천은 SQL 한 표(`infomax_API.ktb_auction_result`)이고
 * 산술·판정은 전부 `backend/app/ktb_issuance.py` 가 진다(§16) — 여기는
 * **읽고 칠하기만** 한다.
 *
 * ## 화면 문법은 수급 면 그대로
 *
 * 조건 스트립 → 히어로 → (넘겨받은) 컨트롤 행 → 좌 표 / 우 차트 → 사실 스트립.
 * 컨트롤 행을 `FlowPage` 가 만들어 넘기는 이유: 면·구간 손잡이가 **네 면에서 같은
 * 자리**에 있어야 면을 넘겨도 손이 헤매지 않는다.
 *
 * ## 자
 *
 * 서버가 **백만원**으로 준다(원표는 억원, 서버가 ×100). 그래서 수급 면과 같은
 * 자(`fmtEok` 일별 억 · `fmtJo` 누적 조)를 그대로 쓴다 — 두 면이 같은 수를 같은
 * 모양으로 적는다. 응찰률은 `%` 한 자리, 금리는 세 자리(원문 그대로).
 *
 * ## 판정 말은 서버 것이다
 *
 * 「강한 수요」…「표본 부족」은 `issuance_strength` 의 등급이고 Lab 발행 캘린더와
 * **같은 입찰에 같은 말**을 붙인다. 백분위 문장(「상위 8%」·「최고 응찰률」)은 그
 * 화면의 `StrengthLine` 과 같은 규칙으로 적는다.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Text } from '@coinbase/cds-web/typography';

import { TimeChart, useStackedScales, type TimeLine } from '@/chart/TimeChart';
import { BacktestUnavailable } from '@/lib/api';
import { fmtEok, fmtJo } from '@/lib/format';
import { signedBp } from '@/mr/planText';
import { directionClass } from '@/table/tint';
import { ChartReadoutStrip, slotChars, type StripSlot } from '@/ui/ChartReadoutStrip';
import { Cond } from '@/ui/Cond';
import { ErrorState, LoadingState } from '@/ui/DataState';
import { Stat, StatColumn } from '@/ui/Stat';
import { ThHelp } from '@/ui/ThHelp';

import { fetchIssuanceBoard, type IssuanceBoard, type IssuanceUnit } from './api';
import { monthsBefore, SPAN_MONTHS, type Span } from './span';

/** 계열 구분색 넷 — 수급 면과 같은 차례. */
const INK = ['--sr-flow-1', '--sr-flow-2', '--sr-flow-3', '--sr-flow-4'] as const;

/** 발행액은 부호가 없다 — 누적·올해는 조, 한 건은 억. */
const jo = (mil: number) => fmtJo(mil).replace('+', '');
const eok = (mil: number) => fmtEok(mil).replace('+', '');
const pct1 = (v: number | null) => (v == null ? '—' : `${v.toFixed(1)}%`);
const rate3 = (v: number | null) => (v == null ? '—' : `${v.toFixed(3)}%`);

/** 같은 만기물 52주와 견준 한 마디 — Lab 발행 캘린더 `StrengthLine` 의 그 규칙. */
function strengthText(u: IssuanceUnit): string {
  if (u.pct == null) return u.why ?? '—';
  const where = u.pct >= 100 ? '최고 응찰률' : u.pct <= 0 ? '최저 응찰률' : `상위 ${100 - u.pct}%`;
  return `최근 1년 ${where}${u.median != null ? ` · 평년 ${pct1(u.median)}` : ''}`;
}

export function IssuanceFace({ span, controls }: { span: Span; controls: ReactNode }) {
  const [got, setGot] = useState<IssuanceBoard | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [down, setDown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [cursor, setCursor] = useState<{ i: number; src: 'cum' | 'day' }>();
  const onCum = useCallback(
    (i: number | null) => setCursor(i == null ? undefined : { i, src: 'cum' as const }), []);
  const onDay = useCallback(
    (i: number | null) => setCursor(i == null ? undefined : { i, src: 'day' as const }), []);
  const [off, setOff] = useState<Record<string, true>>({});
  const toggle = useCallback(
    (k: string) => setOff((o) => (o[k] ? Object.fromEntries(
      Object.entries(o).filter(([x]) => x !== k)) as Record<string, true> : { ...o, [k]: true })),
    []);

  const load = useCallback((signal?: AbortSignal) => {
    setBusy(true);
    fetchIssuanceBoard(signal)
      .then((r) => { setGot(r); setErr(null); setDown(false); })
      .catch((e: unknown) => {
        if (signal?.aborted) return;
        if (e instanceof BacktestUnavailable) { setDown(true); return; }
        setErr(e instanceof Error ? e.message : String(e));
      })
      .finally(() => { if (!signal?.aborted) setBusy(false); });
  }, []);

  useEffect(() => {
    const ac = new AbortController();
    load(ac.signal);
    return () => ac.abort();
  }, [load]);

  const stack = useStackedScales();

  /** 창 — 입찰일 축은 성글어서 **달 수**로 자른다(`span.ts` 머리). 누적은 창의
   *  첫날부터 다시 0 에서 센다(수급 면과 같은 이유). */
  const win = useMemo(() => {
    if (!got) return null;
    const dates0 = got.series.dates;
    const months = SPAN_MONTHS[span];
    const last = dates0[dates0.length - 1] ?? '';
    const cutoff = months == null ? '' : monthsBefore(last, months);
    let k = 0;
    while (k < dates0.length && (dates0[k] ?? '') < cutoff) k += 1;
    const dates = dates0.slice(k);
    const cum = got.series.cum.map((s) => {
      const base = s.values[k - 1] ?? 0;
      return { ...s, values: s.values.slice(k).map((v) => v - base) };
    });
    const daily = got.series.daily
      ? { ...got.series.daily, values: got.series.daily.values.slice(k) }
      : null;
    return { dates, cum, daily };
  }, [got, span]);

  const lines: TimeLine[] = useMemo(() => {
    if (!win) return [];
    return win.cum
      .map((s, i) => ({ s, i }))
      .filter(({ s }) => !off[s.key])
      .map(({ s, i }) => ({
        id: s.key,
        values: s.values,
        color: (p) => p.resolve(`var(${INK[i % INK.length]})`),
        width: 2 as const,
        format: jo,
        beacon: i === 0,
      }));
  }, [win, off]);

  /** 일별 막대 — 양수가 발행(공급), 음수가 매입(바이백). 부호가 색을 정한다. */
  const daily: TimeLine[] = useMemo(() => {
    if (!win?.daily) return [];
    return [{
      id: win.daily.key,
      values: win.daily.values,
      kind: 'histogram' as const,
      color: (p) => p.up,
      colorAt: (v, p) => (v >= 0 ? p.up : p.down),
      format: eok,
    }];
  }, [win]);

  const at = useMemo(() => {
    const n = win?.dates.length ?? 0;
    const i = cursor && cursor.i >= 0 && cursor.i < n ? cursor.i : n - 1;
    return { i, date: win?.dates[i] ?? '' };
  }, [cursor, win]);

  const slots = useMemo<StripSlot[]>(() => {
    if (!win) return [];
    const chars = slotChars(
      jo,
      ...win.cum.flatMap((c) => [Math.max(...c.values), Math.min(...c.values)]),
    );
    return win.cum.map((c, i) => ({
      key: c.key,
      label: c.label,
      value: jo(c.values[at.i] ?? 0),
      color: `var(${INK[i % INK.length]})`,
      chars,
      drop: (Math.min(i + 1, 6) as 1 | 2 | 3 | 4 | 5 | 6),
      toggle: { on: !off[c.key], onToggle: () => toggle(c.key) },
    }));
  }, [win, at.i, off, toggle]);

  if (down) {
    return <ErrorState what="국고채 발행 통계" onRetry={() => load()} retrying={busy}
      detail="백엔드가 안 보여요 — 이 화면은 SQL 입찰 결과표를 바로 읽어요." />;
  }
  if (err) {
    return <ErrorState what="국고채 발행 통계" detail={err} onRetry={() => load()} retrying={busy} />;
  }
  if (!got) return <LoadingState what="국고채 발행 통계" />;

  const L = got.latest;

  return (
    <VStack gap={1.5} width="100%" flexGrow={1} minHeight={0}>
      {/* ── 조건 스트립 ─────────────────────────────────────────────────── */}
      <VStack className="sr-rv-bar" width="100%" gap={0.5}>
        <HStack gap={2} flexWrap="wrap" alignItems="baseline" width="100%">
          <Cond k="입찰결과" v={got.asof.auction} />
          <Cond k="단위" v="한 건 억 · 누적 조" strong />
          <Cond k="표본" v={`${got.count.toLocaleString('ko-KR')}건 · ${got.since} 부터`} />
          {got.next.length > 0 ? (
            <Cond k="다음 입찰"
              v={got.next.map((n) => `${n.date.slice(5)} ${n.label}`).join(' · ')} />
          ) : null}
        </HStack>
        <Text as="p" font="legal" color="fgMuted">
          {got.basis}
          {got.excluded.length > 0
            ? ` (뺀 것 — ${got.excluded.map((e) => e.label).join(' · ')})`
            : ''}
        </Text>
      </VStack>

      {/* ── 히어로 — 가장 최근 경쟁입찰 한 건 ───────────────────────────── */}
      <VStack gap={0.25}>
        <Text as="span" font="legal" color="fgMuted">최근 입찰</Text>
        <HStack gap={1.5} alignItems="baseline" flexWrap="wrap">
          <Text as="h2" font="display3">{L.label}</Text>
          <Text as="span" font="title3" tabularNumbers>{jo(L.amount)}조</Text>
          <Text as="span" font="body" color="fgMuted" tabularNumbers>
            {L.date} · {L.names.join('·')} · 응찰률 {pct1(L.ratio)} · 낙찰 {rate3(L.rate)}
            {L.rateDelta != null ? ` (직전 대비 ${signedBp(L.rateDelta, 'bp')})` : ''}
          </Text>
        </HStack>
        <HStack gap={1} alignItems="baseline" flexWrap="wrap">
          <Text as="span" font="label2">{L.grade ?? '—'}</Text>
          <Text as="span" font="legal" color="fgMuted" tabularNumbers>{strengthText(L)}</Text>
          {L.notes.map((n) => (
            <Text key={n} as="span" font="legal" color="fgMuted">{n}</Text>
          ))}
        </HStack>
      </VStack>

      {controls}

      {/* ── 구르는 칸 (수급 면과 같은 이유 — `FlowPage` 의 그 주석) ──────── */}
      <VStack gap={1.5} width="100%" flexGrow={1} minHeight={0}
        style={{ overflowY: 'auto' }}>
      <HStack gap={2} alignItems="stretch" minHeight={560} width="100%"
        flexShrink={0} flexWrap="wrap">
        {/* 표가 열 열을 진다 — 수급 표(일곱 열·1,117px)보다 넓어 상자를 1,240 로. */}
        <VStack className="sr-card" flexBasis={1240} flexGrow={0} flexShrink={1}
          maxWidth={1300} minWidth={0} minHeight={0}>
          <VStack paddingX={2} paddingTop={1.5} paddingBottom={1} gap={0.5}>
            <Text as="h3" font="label1">만기물별 입찰 통계</Text>
            <Text as="span" font="legal" color="fgMuted">
              각 만기물의 가장 최근 경쟁입찰과 올해 누적이에요. 비경쟁은 PD 가 입찰 뒤
              행사한 인수분이고, 매입은 되사 간 물량이에요.
            </Text>
          </VStack>
          <Box flexGrow={1} minHeight={0} paddingX={1} paddingBottom={1}>
            <div className="sr-rv-rank-fill">
              <div className="sr-rv-rank-scroll">
                <table className="sr-rv-table sr-rv-divided">
                  <thead>
                    <tr>
                      <th className="sr-rv-th sr-rv-left">만기물</th>
                      <th className="sr-rv-th sr-rv-left">최근 입찰</th>
                      <th className="sr-rv-th">발행액 (억)</th>
                      <th className="sr-rv-th">응찰률</th>
                      <th className="sr-rv-th sr-rv-left">
                        <ThHelp font="inherit" label="수요 판정"
                          help="같은 만기물 최근 1년 입찰의 응찰률 분포에서 이번이 어디인지예요. 6회 미만이면 판정하지 않아요." />
                      </th>
                      <th className="sr-rv-th">낙찰금리</th>
                      <th className="sr-rv-th">
                        <ThHelp font="inherit" label="직전 대비"
                          help="직전 같은 만기물 입찰의 낙찰금리와의 차이예요. 민평이 없어 직전 입찰이 잣대예요." />
                      </th>
                      <th className="sr-rv-th">올해 경쟁 (조)</th>
                      <th className="sr-rv-th">비경쟁 (조)</th>
                      <th className="sr-rv-th">
                        <ThHelp font="inherit" label="작년 동기 (조)"
                          help="작년 같은 날까지의 경쟁 낙찰 합이에요." />
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {got.tenors.map((t) => {
                      const u = t.last;
                      return (
                        <tr key={t.key} className="sr-rv-row">
                          <td className="sr-rv-td sr-rv-left">
                            <span className="sr-rv-name">{t.label}</span>
                          </td>
                          <td className="sr-rv-td sr-rv-left">
                            {u ? (
                              <span className="sr-rv-stack">
                                <span className="sr-rv-name">{u.date}</span>
                                <span className="sr-rv-sub">
                                  {u.names.join('·')}{u.legs > 1 ? ' · 두 종목 합산' : ''}
                                </span>
                              </span>
                            ) : '—'}
                          </td>
                          <td className="sr-rv-td">{u ? eok(u.amount) : '—'}</td>
                          <td className="sr-rv-td">{u ? pct1(u.ratio) : '—'}</td>
                          <td className="sr-rv-td sr-rv-left">
                            {u ? (
                              <span className="sr-rv-stack">
                                <span className="sr-rv-name">{u.grade ?? '—'}</span>
                                <span className="sr-rv-sub">{strengthText(u)}</span>
                              </span>
                            ) : '—'}
                          </td>
                          <td className="sr-rv-td">{u ? rate3(u.rate) : '—'}</td>
                          <td className="sr-rv-td">
                            {u?.rateDelta != null ? (
                              <span className={directionClass(u.rateDelta)}>
                                {signedBp(u.rateDelta, 'bp')}
                              </span>
                            ) : '—'}
                          </td>
                          <td className="sr-rv-td">
                            <span className="sr-rv-stack">
                              <span className="sr-rv-name">{jo(t.ytd)}</span>
                              <span className="sr-rv-sub">{t.ytdCount}회</span>
                            </span>
                          </td>
                          <td className="sr-rv-td">{jo(t.ytdNoncomp)}</td>
                          <td className="sr-rv-td">{jo(t.ytdPrev)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <Text as="p" font="legal" color="fgMuted" paddingX={1} paddingY={1}>
                  {got.pd.note}
                </Text>
              </div>
            </div>
          </Box>
        </VStack>

        <VStack className="sr-card" flexBasis={460} flexGrow={1} flexShrink={1}
          minWidth={0} minHeight={0}>
          <VStack paddingX={2} paddingTop={1.5} paddingBottom={0.5} gap={0.75}>
            <HStack alignItems="baseline" justifyContent="space-between" gap={1}>
              <Text as="h3" font="label1">누적 공급 (조)</Text>
              <Text as="span" font="legal" color="fgMuted">
                고른 구간의 첫날부터 다시 세요 · 올해 공급이 큰 만기물 넷
              </Text>
            </HStack>
          </VStack>
          {/* ★`VStack width="100%"` — 수급 면이 두 번 밟은 자리(`Box` 는 가로 flex). */}
          <VStack width="100%" paddingBottom={0.5}>
            <ChartReadoutStrip
              date={at.date}
              slots={slots}
              ariaLabel="만기물별 누적 공급 — 커서가 짚은 날의 값"
            />
          </VStack>
          <VStack paddingX={2} paddingBottom={1} gap={0.5} flexGrow={1} minHeight={0}>
            <Box className="sr-plot" flexGrow={2} minHeight={0}>
              <TimeChart
                dates={win?.dates ?? []}
                lines={lines}
                precision={1}
                onHoverIndex={onCum}
                syncIndex={cursor?.src === 'day' ? cursor.i : null}
                hoverLabel={(i) => `${win?.dates[i] ?? ''} · `
                  + (win?.cum ?? []).map((c) => `${c.label} ${jo(c.values[i] ?? 0)}조`).join(', ')}
                accessibilityLabel={`만기물별 누적 공급 — ${got.series.cum.map((s) => s.label).join(', ')}`}
                {...stack}
              />
            </Box>
            <HStack alignItems="baseline" justifyContent="space-between" gap={1}>
              <Text as="span" font="label2">일별 — 발행 합계 (억)</Text>
              <Text as="span" font="legal" color="fgMuted">
                빨강이 발행, 파랑이 매입이에요
              </Text>
            </HStack>
            <Box className="sr-plot" flexGrow={1} minHeight={0}>
              <TimeChart
                dates={win?.dates ?? []}
                lines={daily}
                precision={0}
                priceLines={[{ value: 0, color: (p) => p.line }]}
                onHoverIndex={onDay}
                syncIndex={cursor?.src === 'cum' ? cursor.i : null}
                hoverLabel={(i) => `${win?.dates[i] ?? ''} · 발행 합계 ${eok(win?.daily?.values[i] ?? 0)}억`}
                accessibilityLabel="일별 발행 합계"
                {...stack}
              />
            </Box>
          </VStack>
        </VStack>
      </HStack>

      {/* ── 사실 스트립 ─────────────────────────────────────────────────── */}
      <Box flexShrink={0} width="100%">
        <HStack className="sr-stats" width="100%" flexWrap="wrap">
          <StatColumn title={`${got.year.label}년 공급 (조)`}>
            <Stat label="경쟁 낙찰" value={jo(got.year.comp)}
              note={`작년 같은 날까지 ${jo(got.year.compPrev)}조`} />
            <Stat label="비경쟁 인수" value={jo(got.year.noncomp)} note="PD 옵션 행사분" />
            <Stat label="매입" value={`−${jo(got.year.buyback)}`} note="되사 간 물량" />
          </StatColumn>
          <StatColumn title={`고른 구간 ${span === 'ALL' ? '전체' : span} · 그림 넷`}>
            {(win?.cum ?? []).map((c) => (
              <Stat key={c.key} label={c.label}
                value={jo(c.values[c.values.length - 1] ?? 0)} />
            ))}
          </StatColumn>
          {got.next.length > 0 ? (
            <StatColumn title="다음 입찰">
              {got.next.map((n) => (
                <Stat key={`${n.date}-${n.label}`} label={n.date} value={n.label}
                  note={n.planned != null ? `예정 ${eok(n.planned)}억` : '예정액은 공고 전이에요'} />
              ))}
            </StatColumn>
          ) : null}
          <StatColumn title="모집단">
            <Stat label="표본" value={`${got.count.toLocaleString('ko-KR')}건`}
              note={`${got.since} 부터 · 경쟁입찰 하루 단위`} />
            <Stat label="그림" value={`${got.series.cum.length}계열`} note="전수는 왼쪽 표가 져요" />
          </StatColumn>
        </HStack>
      </Box>
      </VStack>
    </VStack>
  );
}
