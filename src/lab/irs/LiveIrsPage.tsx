'use client';

/* 실시간 IRS — Lab 의 네 번째 세입자 [OWNER 2026-10-01].
 *
 * [OWNER] 「스왑 데이터를 실시간으로 받아오고 있는데, Lab 탭에서 실시간 IRS 볼 수
 * 있을지」 → 볼 수 있다. **자료는 이미 와 있었고 화면만 없었다**(출처와 그 근거는
 * `./api.ts` 머리).
 *
 * ── 이 화면이 답하는 질문 ───────────────────────────────────────────────────
 * **「지금, 종가 대비 몇 bp 움직였나」.** Main 은 종가와 **전일 대비**(어제 대 그제)를
 * 말한다 — 오늘 장중을 말하는 자리가 이 앱에 없었다. 그래서 라이브 커브와 종가
 * 커브를 **같은 그림에 겹치고**, 표가 그 차이를 만기마다 bp 로 적는다.
 *
 * ── 왜 Lab 인가 ────────────────────────────────────────────────────────────
 * Lab 은 「아직 규칙이 되지 못한 것들」이다(nav.ts). 이 수로 무엇을 할지(문턱·신호)는
 * 아직 안 정했고, 정해지면 그때 제 화면으로 승격한다 — 발행 캘린더가 지난 길이다.
 *
 * ── 낡음은 **서버가 판정한다** ──────────────────────────────────────────────
 * 「오늘 자료가 아니다 / N분 전 값이다」는 `paperlive` 가 정하고 값을 **안 싣고**
 * 사유를 든다(MAX_AGE_MIN). 화면은 그 사유를 **옮겨 적기만** 한다 — 여기서 두 번째
 * 문턱을 두면 갈리는 날이 오고, 그날 둘 중 어느 쪽이 옳은지 댈 자료가 없다.
 * (`freshness` 칩이 서버 판정을 그대로 읽는 그 규율과 같다.)
 *
 * ── 표는 **조밀 문법**이다 ──────────────────────────────────────────────────
 * 캐논의 표는 CDS `Table` + `ROW_H`(60)인데, 만기 열일곱이면 1,020px 이라 Lab 한
 * 화면에 안 선다. 그래서 rv 가 74행에 쓰는 조밀 표(`.sr-rv-table`)를 쓴다 — 클래스
 * 이름은 소유권이 아니라는 그 규칙(CLAUDE.md 캐논 §2)이고, 변화 칸은 캐논의
 * **네 부품 한 벌**(틴트·방향색·글리프·무부호)을 그대로 조립한다.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Text } from '@coinbase/cds-web/typography';

import { CurveChart, type CurveLine } from '@/chart/CurveChart';
import { fmtBp, fmtLevel } from '@/lib/format';
import { directionClass, directionGlyph, tintStyle, unsignedDelta } from '@/table/tint';
import { Cond } from '@/ui/Cond';
import { ErrorState, LoadingState } from '@/ui/DataState';

import { fetchIrsBoard, type IrsBoard } from './api';

/** 자동 갱신 주기. 소스는 초 단위지만 화면이 초마다 깜빡일 이유는 없다 — 사람이
 *  커브를 읽는 속도가 이 수를 정한다. 수동 「갱신」은 언제나 옆에 있다. */
const POLL_MS = 15_000;

/** 나이를 사람 말로. 서버가 분(float)으로 준다 — 「0.0분 전」은 사람 말이 아니다. */
function ageText(ageMin: number | null): string {
  if (ageMin == null) return '—';
  if (ageMin < 1) return '방금';
  return `${Math.round(ageMin)}분 전`;
}

export function LiveIrsPage() {
  const [board, setBoard] = useState<IrsBoard>();
  const [error, setError] = useState<string>();
  const [refreshing, setRefreshing] = useState(false);
  /** 자동 갱신은 켜고 시작한다 — 「실시간」이라 적힌 화면이 멈춰 있으면 거짓말이다. */
  const [auto, setAuto] = useState(true);

  const load = useCallback(() => {
    setRefreshing(true);
    fetchIrsBoard()
      .then((b) => {
        setBoard(b);
        setError(undefined);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setRefreshing(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!auto) return undefined;
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [auto, load]);

  const rows = useMemo(() => board?.rows ?? [], [board]);
  const nodes = useMemo(() => rows.map((r) => r.tenor), [rows]);
  /* 두 선 — 지금은 잉크(굵게), 종가는 뮤트(가늘게). 「무엇이 움직였나」를 읽는
     그림이라 색이 아니라 **무게**가 둘을 가른다. */
  const lines = useMemo<CurveLine[]>(
    () => [
      {
        id: 'now',
        label: '지금',
        values: rows.map((r) => r.now),
        color: (p) => p.fg,
        width: 2,
      },
      {
        id: 'close',
        label: '종가',
        values: rows.map((r) => r.close),
        color: (p) => p.fgMuted,
        width: 1,
      },
    ],
    [rows],
  );

  if (error && !board) {
    return <ErrorState what="실시간 IRS" detail={error} onRetry={load} retrying={refreshing} />;
  }
  if (!board) return <LoadingState what="실시간 IRS" />;

  return (
    <VStack gap={1.5} width="100%" flexGrow={1} minHeight={0}>
      {/* ── 조건 바 — 어느 시계의 숫자인지가 먼저다(rv 조건 바의 그 규율). */}
      <VStack gap={0.5} flexShrink={0} width="100%">
        <HStack gap={1.5} alignItems="center" flexWrap="wrap">
          <Cond k="지금" v={board.liveAsof ?? '—'} />
          <Cond k="나이" v={ageText(board.liveAgeMin)} />
          <Cond k="종가" v={board.closeAsof ?? '—'} />
          <Cond k="만기" v={`${rows.length}개`} />
          {refreshing ? (
            <Text font="legal" as="span" color="fgMuted" noWrap>
              갱신 중…
            </Text>
          ) : null}
          <HStack gap={1} alignItems="center" style={{ marginLeft: 'auto' }}>
            <button
              type="button"
              className="sr-pillbtn"
              data-on={auto || undefined}
              aria-pressed={auto}
              onClick={() => setAuto((v) => !v)}
            >
              자동 갱신
            </button>
            <button type="button" className="sr-pillbtn" onClick={load} disabled={refreshing}>
              갱신
            </button>
          </HStack>
        </HStack>
        {/* 값이 안 섰으면 **왜 없는지**를 화면이 말한다 — 서버가 적어 준 그대로. */}
        {board.why ? (
          <Text font="legal" as="p" color="fgMuted">
            {board.why}
          </Text>
        ) : null}
        {/* 스왑 − 국채선물 내재금리. 둘 다 라이브라 같은 시계다 — 이 데스크의
            부호 규약(스왑 − 선물)을 그대로 쓴다. */}
        {board.futBasis.length > 0 ? (
          <Text font="legal" as="p" color="fgMuted" tabularNumbers>
            스왑 − 국채선물 내재 ·{' '}
            {board.futBasis.map((b) => `${b.tenor} ${fmtBp(b.bp)}bp`).join(' · ')}
          </Text>
        ) : null}
      </VStack>

      {rows.length === 0 ? (
        /* 라이브가 안 설 때 — 빈 그림을 그리지 않는다. 사유는 위 줄이 이미 말했다. */
        <Text font="body" as="p" color="fgMuted">
          지금 값이 없어요 — 위 사유를 보세요.
        </Text>
      ) : (
        <HStack gap={2} alignItems="stretch" width="100%" flexGrow={1} minHeight={0}>
          {/* ── 커브 — 지금과 종가를 겹친다. x 는 √만기(CurveChart 의 그 축). */}
          <VStack className="sr-card" flexGrow={1} flexShrink={1} minWidth={420} minHeight={0}>
            <VStack gap={0.25} paddingX={2} paddingTop={1.5} paddingBottom={0.5}>
              <Text font="label1" as="h2" noWrap>
                IRS 커브 — 지금과 종가
              </Text>
              <Text font="legal" as="span" color="fgMuted" noWrap>
                진한 선이 지금({board.liveAsof ?? '—'}) · 흐린 선이 종가(
                {board.closeAsof ?? '—'})
              </Text>
            </VStack>
            <Box paddingX={2} paddingBottom={1.5}>
              <CurveChart
                height={360}
                accessibilityLabel={`IRS 커브, 지금과 종가 두 선, 만기 ${nodes.length}개`}
                nodes={nodes}
                lines={lines}
                tickFormat={(v) => v.toFixed(2)}
                hoverLabel={(i) =>
                  `${nodes[i]} · 지금 ${fmtLevel(rows[i]?.now, '%')}% · 종가 ${fmtLevel(
                    rows[i]?.close,
                    '%',
                  )}% · 일중 ${fmtBp(rows[i]?.moveBp ?? null)}bp`
                }
              />
            </Box>
          </VStack>

          {/* ── 표 — 만기마다 [지금 | 종가 | 일중]. */}
          <VStack
            className="sr-card"
            flexBasis={420}
            flexGrow={0}
            flexShrink={1}
            maxWidth={420}
            minHeight={0}
          >
            <VStack gap={0.25} paddingX={2} paddingTop={1.5} paddingBottom={0.5}>
              <Text font="label1" as="h2" noWrap>
                만기별 — 일중 이동
              </Text>
              <Text font="legal" as="span" color="fgMuted" noWrap>
                일중 = 지금 − 종가
              </Text>
            </VStack>
            <Box paddingX={2} paddingBottom={1.5} overflow="auto" minHeight={0}>
              <table className="sr-rv-table sr-rv-divided">
                <thead>
                  <tr>
                    <th className="sr-rv-th sr-rv-left">만기</th>
                    <th className="sr-rv-th">지금</th>
                    <th className="sr-rv-th">종가</th>
                    <th className="sr-rv-th">일중</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.tenor}>
                      <td className="sr-rv-td sr-rv-left">{r.tenor}</td>
                      <td className="sr-rv-td">{fmtLevel(r.now, '%')}</td>
                      <td className="sr-rv-td">{fmtLevel(r.close, '%')}</td>
                      {/* 변화 칸 = 캐논 네 부품 한 벌(InstrumentTable 의 그 조립). */}
                      <td className="sr-rv-td" style={tintStyle(r.moveBp)}>
                        <Text
                          font="label2"
                          as="span"
                          tabularNumbers
                          noWrap
                          className={directionClass(r.moveBp)}
                        >
                          {directionGlyph(r.moveBp)}
                          {directionGlyph(r.moveBp) ? ' ' : ''}
                          {unsignedDelta(fmtBp(r.moveBp))}
                        </Text>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Box>
          </VStack>
        </HStack>
      )}
    </VStack>
  );
}
