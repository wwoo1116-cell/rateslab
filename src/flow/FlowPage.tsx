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
import { BacktestUnavailable } from '@/lib/api';
import { fmtContracts, fmtEok } from '@/lib/format';
import { Cond } from '@/ui/Cond';
import { Segmented } from '@/ui/ControlCard';
import { ErrorState, LoadingState } from '@/ui/DataState';
import { Stat, StatColumn } from '@/ui/Stat';

import { fetchFlowBoard, type FlowBoard, type FlowSide, type FlowTenor } from './api';
import { FlowTable } from './FlowTable';

/** 면 하나 = (원천, 만기). 현물엔 만기가 없다. */
type Face = 'fut3' | 'fut10' | 'cash';
const FACE: Record<Face, { side: FlowSide; tenor: FlowTenor; label: string }> = {
  fut3: { side: 'fut', tenor: '3Y', label: '선물 3년' },
  fut10: { side: 'fut', tenor: '10Y', label: '선물 10년' },
  cash: { side: 'cash', tenor: '3Y', label: '현물' },
};

/** 계열 구분색 넷. **순서가 곧 배정**이다 — 서버가 보낸 차례대로 입는다. */
const INK = ['--sr-flow-1', '--sr-flow-2', '--sr-flow-3', '--sr-flow-4'] as const;

/** 구간 — 자르는 자리는 **화면**이다. 서버는 전구간을 보내고(2,644일) 그 위에서
 *  누적이 서므로, 창을 서버가 자르면 누적의 **시작점이 0 이 아니게** 된다.
 *  여기서 자르면 선이 그 창의 첫날부터 다시 0 에서 오른다 — 「이 구간에 얼마나
 *  샀나」가 그림이 말해야 하는 것이다. */
type Span = '3M' | '1Y' | '3Y' | 'ALL';
const SPAN_BARS: Record<Span, number> = { '3M': 63, '1Y': 252, '3Y': 756, ALL: Infinity };

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

export function FlowPage() {
  const [face, setFace] = useState<Face>('fut3');
  const [got, setGot] = useState<FlowBoard | null>(null);
  const [err, setErr] = useState<string | null>(null);
  /* `unavailable`(백엔드가 없다) 과 `err`(그 밖) 를 **따로** 든다 — 문구가
     다르기 때문이다(MrPage 와 같은 규율). */
  const [down, setDown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [hover, setHover] = useState<string | null>(null);
  const [span, setSpan] = useState<Span>('1Y');

  const { side, tenor } = FACE[face];

  /* 라이브 단발이라 `AbortController` 로 충분하다 — MrPage 의 순번 가드는
     폴링과 딥링크가 겹치는 자리의 해법이고 여기엔 둘 다 없다
     (`lab/creditdts/CreditDtsPage.tsx:327` 선례). */
  const load = useCallback((signal?: AbortSignal) => {
    setBusy(true);
    fetchFlowBoard(side, tenor, signal)
      .then((r) => { setGot(r); setErr(null); setDown(false); })
      .catch((e: unknown) => {
        if (signal?.aborted) return;
        if (e instanceof BacktestUnavailable) { setDown(true); return; }
        setErr(e instanceof Error ? e.message : String(e));
      })
      .finally(() => { if (!signal?.aborted) setBusy(false); });
  }, [side, tenor]);

  useEffect(() => {
    const ac = new AbortController();
    load(ac.signal);
    return () => ac.abort();
  }, [load]);

  const stack = useStackedScales();
  const unitIsCash = side === 'cash';
  /** 일별 자 — 현물은 **억**이다. 조로 적으면 일별이 전부 `+0.0조` 로 뭉개진다
   *  (실측 2026-10-19). 누적(올해)만 조를 쓰고 그건 표가 진다. */
  const fmt = useCallback(
    (v: number) => (unitIsCash ? fmtEok(v) : fmtContracts(v)),
    [unitIsCash],
  );
  /** 칸 옆에 붙는 단위 말. */
  const unitWord = unitIsCash ? '억' : '계약';

  /** 창 안의 날짜와 **다시 센 누적**.
   *
   *  ★서버가 보낸 `cum` 을 그냥 자르면 선이 창의 첫날 값에서 시작해 「올해 얼마」가
   *  아니라 「2016년부터 얼마」를 보여 준다. 창 안에서 **0 부터 다시** 센다. */
  const win = useMemo(() => {
    if (!got) return null;
    const n = got.series.dates.length;
    const k = Math.max(0, n - (SPAN_BARS[span] === Infinity ? n : SPAN_BARS[span]));
    const dates = got.series.dates.slice(k);
    const cum = got.series.cum.map((s) => {
      const base = s.values[k - 1] ?? 0;
      return { ...s, values: s.values.slice(k).map((v) => v - base) };
    });
    const daily = got.series.daily
      ? { ...got.series.daily, values: got.series.daily.values.slice(k) }
      : null;
    return { dates, cum, daily };
  }, [got, span]);

  /** 누적 선 넷 + 일별 막대 하나. 막대는 **부호마다 색**이다. */
  const lines: TimeLine[] = useMemo(() => {
    if (!win) return [];
    return win.cum.map((s, i) => ({
      id: s.key,
      values: s.values,
      color: (p) => p.resolve(`var(${INK[i % INK.length]})`),
      width: 2 as const,
      format: fmt,
      beacon: i === 0,
    }));
  }, [win, fmt]);

  const daily: TimeLine[] = useMemo(() => {
    if (!win?.daily) return [];
    return [{
      id: win.daily.key,
      values: win.daily.values,
      kind: 'histogram' as const,
      color: (p) => p.up,
      /* 부호가 색을 정한다 — 그것이 막대를 들인 이유의 절반이다. */
      colorAt: (v, p) => (v >= 0 ? p.up : p.down),
      format: fmt,
    }];
  }, [win, fmt]);

  if (down) {
    return <ErrorState what="투자자별 수급" onRetry={() => load()} retrying={busy}
      detail="백엔드가 안 보여요 — 이 화면은 SQL 두 원천을 바로 읽어요." />;
  }
  if (err) {
    return <ErrorState what="투자자별 수급" detail={err} onRetry={() => load()} retrying={busy} />;
  }
  if (!got) return <LoadingState what="투자자별 수급" />;

  const lead = got.top.find((t) => t.value > 0) ?? got.sub[0];
  const other = got.top.find((t) => t.value < 0);

  return (
    <VStack gap={1.5} width="100%" flexGrow={1} minHeight={0}>
      {/* ── 조건 스트립 ─────────────────────────────────────────────────── */}
      <VStack className="sr-rv-bar" width="100%" gap={0.5}>
        <HStack gap={2} flexWrap="wrap" alignItems="baseline" width="100%">
          {/* ★둘을 **따로** 적는다 — 어긋나는 것이 정상이고 경고가 아니다. */}
          <Cond k="선물수급" v={got.asof.fut ?? '—'} />
          <Cond k="현물수급" v={got.asof.cash ?? '—'} />
          {/* 서버가 말하는 원단위(계약·백만원)와 **화면의 자**가 다르다 —
              백만원으로 적으면 일별이 여섯 자리라 억으로 줄여 읽는다. */}
          <Cond k="단위" v={unitIsCash ? '억 (올해는 조)' : '계약'} strong />
          <Cond k="순위"
            v={`${side === 'cash' ? '주체별' : '기관계 세분'} · 하한 ${fmt(got.rankFloor).replace('+', '')}${unitWord}`} />
          <Cond k="표본" v={`${got.days.toLocaleString('ko-KR')}일`} />
          <Box style={{ marginInlineStart: 'auto' }}>
            <Text as="span" font="legal" color="fgMuted">
              집계예요 — 새 판단이 아니에요.
            </Text>
          </Box>
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

      {/* ── 히어로 ──────────────────────────────────────────────────────── */}
      <VStack gap={0.25}>
        <Text as="span" font="legal" color="fgMuted">
          {side === 'cash' ? '평소 대비가 가장 큰 주체예요' : '당일 순매수 대조'}
        </Text>
        <HStack gap={1.5} alignItems="baseline" flexWrap="wrap">
          <Text as="h2" font="display3">
            {'label' in lead ? lead.label : ''}
          </Text>
          <Text as="span" font="title3"
            className={('value' in lead ? lead.value : lead.d1) >= 0 ? 'sr-up' : 'sr-down'}>
            {fmt('value' in lead ? lead.value : lead.d1)} {unitWord}
          </Text>
          {other ? (
            <Text as="span" font="body" color="fgMuted">
              반대편은 {other.label} {fmt(other.value)}{unitWord}
            </Text>
          ) : null}
        </HStack>
      </VStack>

      {/* ── 컨트롤 행 (등고 32) ─────────────────────────────────────────── */}
      <HStack gap={2} alignItems="flex-end">
        {/* 폭은 **최장 라벨**로 잰다 — 260 에서는 「선물 10년」이 두 줄로
            접혔다(실측 2026-10-19). 말줄임 금지라 폭을 키우는 쪽이 답이다. */}
        <Box width={330}>
          <Segmented
            label="면"
            value={face}
            onChange={setFace}
            options={(Object.keys(FACE) as Face[]).map((k) => ({
              value: k, label: FACE[k].label,
            }))}
            fill
          />
        </Box>
        <Box width={250}>
          <Segmented
            label="구간"
            value={span}
            onChange={setSpan}
            options={[
              { value: '3M' as const, label: '3M' },
              { value: '1Y' as const, label: '1Y' },
              { value: '3Y' as const, label: '3Y' },
              { value: 'ALL' as const, label: '전체' },
            ]}
            fill
          />
        </Box>
        <Text as="span" font="legal" color="fgMuted" paddingBottom={0.5}>
          단위가 달라 한 축에 못 겹쳐요 — 면을 가릅니다. 누적은 고른 구간의
          첫날부터 다시 세요.
        </Text>
      </HStack>

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
      <HStack gap={2} alignItems="stretch" minHeight={560} width="100%"
        flexShrink={0} flexWrap="wrap">
        {/* 표가 일곱 열을 진다 — 640 에서는 20일·올해가 잘렸다(실측). */}
        <VStack className="sr-card" flexBasis={900} flexGrow={2} flexShrink={1}
          minWidth={0} minHeight={0}>
          <VStack paddingX={2} paddingTop={1.5} paddingBottom={1} gap={1}>
            <Text as="h3" font="label1">
              {side === 'cash' ? '주체별 순매수' : '기관계 세분 순위'}
            </Text>
            {/* 대분류 대조 — **순위가 아니다**(상관 −0.9996). 숫자를 나란히
                적는 것보다 **양쪽 막대**가 「누가 받고 누가 냈나」를 한 눈에
                말한다(목업에서 가장 잘 읽히던 자리인데 첫 판에서 빼먹었다). */}
            {got.top.length > 0 ? <Balance top={got.top} fmt={fmt} unit={unitWord} /> : null}
          </VStack>
          <Box flexGrow={1} minHeight={0} paddingX={1} paddingBottom={1}>
            <FlowTable rows={got.sub} side={side} floor={got.rankFloor}
              highlight={hover} onHover={setHover} />
          </Box>
        </VStack>

        <VStack className="sr-card" flexBasis={460} flexGrow={1} flexShrink={1}
          minWidth={0} minHeight={0}>
          <VStack paddingX={2} paddingTop={1.5} paddingBottom={0.5} gap={0.75}>
            <HStack alignItems="baseline" justifyContent="space-between" gap={1}>
              <Text as="h3" font="label1">누적 순매수</Text>
              <Text as="span" font="legal" color="fgMuted">
                고른 구간의 첫날부터 다시 세요
              </Text>
            </HStack>
            {/* 범례 — 색 단독으로 식별하지 않게(WCAG 2.2 §1.4.1). */}
            <HStack gap={1.5} flexWrap="wrap">
              {got.series.cum.map((s, i) => (
                <HStack key={s.key} gap={0.5} alignItems="center">
                  <Box width={11} height={3} borderRadius={100}
                    style={{ background: `var(${INK[i % INK.length]})` }} />
                  <Text as="span" font="legal" color="fgMuted">{s.label}</Text>
                </HStack>
              ))}
            </HStack>
          </VStack>
          {/* 그림 둘이 **남는 높이를 나눠 갖는다** — 고정 높이로 두면 카드 아래가
              빈다(실측). 누적이 둘, 일별이 하나 몫이다. */}
          <VStack paddingX={2} paddingBottom={1} gap={0.5} flexGrow={1} minHeight={0}>
            <Box className="sr-plot" flexGrow={2} minHeight={0}>
              <TimeChart
                dates={win?.dates ?? []}
                lines={lines}
                precision={0}
                hideTimeAxis
                accessibilityLabel={`${FACE[face].label} 누적 순매수 — ${got.series.cum.map((s) => s.label).join(', ')}`}
                {...stack}
              />
            </Box>
            <HStack alignItems="baseline" justifyContent="space-between" gap={1}>
              <Text as="span" font="label2">일별 — {win?.daily?.label ?? ''}</Text>
              <Text as="span" font="legal" color="fgMuted">
                빨강이 순매수, 파랑이 순매도예요
              </Text>
            </HStack>
            <Box className="sr-plot" flexGrow={1} minHeight={0}>
              <TimeChart
                dates={win?.dates ?? []}
                lines={daily}
                precision={0}
                priceLines={[{ value: 0, color: (p) => p.line }]}
                accessibilityLabel={`${win?.daily?.label ?? ''} 일별 순매수`}
                {...stack}
              />
            </Box>
          </VStack>
        </VStack>
      </HStack>

      {/* ── 사실 스트립 ─────────────────────────────────────────────────── */}
      <Box flexShrink={0} width="100%">
        <HStack className="sr-stats" width="100%" flexWrap="wrap">
          <StatColumn title="오늘">
            {got.sub.filter((r) => r.ranked).slice(0, 3).map((r) => (
              <Stat
                key={r.key}
                label={r.label}
                value={fmt(r.d1)}
                tone={r.d1 > 0 ? 'up' : r.d1 < 0 ? 'down' : undefined}
                note={r.sigma == null ? '평소 대비를 못 재요'
                  : `평소 대비 ${r.sigma > 0 ? '+' : '−'}${Math.abs(r.sigma).toFixed(2)}σ`}
              />
            ))}
          </StatColumn>
          {/* 그림이 말하는 것을 **수로** 받는 칸 — 선을 눈으로 재지 않게.
              누적은 고른 구간의 첫날부터라 이 수가 곧 「이 구간에 얼마나 샀나」다. */}
          <StatColumn title={`고른 구간 (${span === 'ALL' ? '전체' : span})`}>
            {(win?.cum ?? []).map((c) => {
              const last = c.values[c.values.length - 1] ?? 0;
              return (
                <Stat
                  key={c.key}
                  label={c.label}
                  value={fmt(last)}
                  tone={last > 0 ? 'up' : last < 0 ? 'down' : undefined}
                />
              );
            })}
          </StatColumn>
          <StatColumn title="모집단">
            <Stat label="표본" value={`${got.days.toLocaleString('ko-KR')}일`}
              note={`${got.series.dates[0] ?? '—'} 부터`} />
            <Stat label="순위 대상"
              value={`${got.sub.filter((r) => r.ranked).length} / ${got.sub.length}주체`}
              note={`일평균 ${fmt(got.rankFloor).replace('+', '')}${unitWord} 미만은 순위 밖`} />
            <Stat label="그림" value={`${got.series.cum.length}계열`}
              note="전수는 왼쪽 표가 져요" />
          </StatColumn>
        </HStack>
      </Box>
      </VStack>
    </VStack>
  );
}
