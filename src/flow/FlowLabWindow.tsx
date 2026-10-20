'use client';

/* 수급 신호 실험 창 — **오너가 직접 재 보는 자리**
 * [OWNER 2026-10-20 — 「이거 내가 사용할 수 있어야한다고,, Backtest에서 처럼」].
 *
 * ## Backtest 와 **같은 규율**을 진다 (`backtest/BacktestWindow` 머리)
 *
 * **스스로 실행되지 않는다.** 사람이 실행을 누른다. 한 번이 서버에서 격자 전체를
 * 가짜 판에 돌리는 일이라 2~5초다 — 창을 돌리는 중에 저절로 일어날 일이 아니다.
 *
 * **모달이 아니라 떠 있는 창이다.** 읽는 사람이 그 주위에서 앱을 계속 쓴다 —
 * 표에서 칸을 눌러 보고, 구간을 바꿔 보고, 다시 실험한다.
 *
 * **라이브 백엔드 전용.** 답이 읽는 사람이 고른 입력에 달렸다. 백엔드가 없으면
 * 빈 결과를 그리는 대신 그렇다고 말한다.
 *
 * ## ★이 창만의 규칙 — **수를 혼자 안 보여 준다**
 *
 * 2026-10-20 에 이 가족을 재서 KILL 했는데, 그 과정에서 **내가 한 번 틀린 판정을
 * 냈다**: 한 칸을 무작위 거래와 견줘 「p 0.025 로 살았다」고 적었고, 탐재 전체로
 * 다시 재니 우연의 중위보다도 못했다. 사람이 손으로 창을 스무 번 바꾸면 그것이
 * **탐색**이고, 탐색의 우연은 한 칸의 우연보다 훨씬 세다.
 *
 * 그래서 이 창은 성과 옆에 **둘을 같이** 세운다:
 *   ① 그 칸의 우연 — 그 포지션을 가짜 판에 돌린 분포(p)
 *   ② **탐색의 우연** — 격자 전체를 가짜 판에 돌린 **1등** 분포
 * ②가 판정의 자다. ①만 보면 열 번 중 한 번은 「살았다」가 나온다.
 *
 * 판정 문장도 화면이 지어내지 않는다 — 서버의 `warn` 을 그대로 싣고, 통과·실패는
 * `beat`(가짜 탐색이 이긴 몫) 하나로 가른다.
 */

import { useCallback, useEffect, useState } from 'react';

import { Select } from '@coinbase/cds-web/alpha/select';
import { Button } from '@coinbase/cds-web/buttons';
import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Text } from '@coinbase/cds-web/typography';

import { TimeChart, type TimeLine } from '@/chart/TimeChart';
import { BacktestUnavailable } from '@/lib/api';
import { fmtJo } from '@/lib/format';
import { Field, Segmented } from '@/ui/ControlCard';
import { FloatingWindow } from '@/ui/window/FloatingWindow';
import { DROPDOWN_STYLES } from '@/ui/window/popup';

import { fetchFlowLab, type FlowLab } from './api';

/** 격자 — 서버의 `flowlab.SHORTS/LONGS/HOLDS` 와 **같은 벌**이어야 한다.
 *  밖을 고르면 서버가 422 로 거절한다(천장과 견줄 수 없는 칸이라서). */
const SHORTS = [5, 10, 15, 20, 25, 30];
const LONGS = [40, 50, 60, 70, 90, 120];
const HOLDS = [1, 5, 10, 20, 40];
const TARGETS = ['3Y', '5Y', '10Y', '20Y', '30Y'];

const seg = (xs: (number | string)[], suffix = '') =>
  xs.map((v) => ({ value: String(v), label: `${v}${suffix}` }));

/** 억 단위 — 창의 수는 전부 이 자로 읽는다(`fmtJo` 는 조라 여기선 크다). */
function won(v: number): string {
  const eok = v / 1e8;
  return `${eok >= 0 ? '+' : '−'}${Math.abs(eok).toLocaleString('ko-KR', {
    maximumFractionDigits: 0,
  })}억`;
}

function num(v: number | null, digits = 2): string {
  return v == null ? '—' : v.toFixed(digits);
}

export function FlowLabWindow({
  subject, tenor, subjects, tenors, onClose,
}: {
  /** 표에서 고른 칸이 그대로 들어온다 — 창을 열자마자 그 칸을 재게. */
  subject: string;
  tenor: string;
  subjects: { key: string; label: string }[];
  tenors: { key: string; label: string }[];
  onClose: () => void;
}) {
  const [subj, setSubj] = useState(subject);
  const [ten, setTen] = useState(tenor);
  const [target, setTarget] = useState('30Y');
  const [short, setShort] = useState(20);
  const [long, setLong] = useState(60);
  const [hold, setHold] = useState(20);

  const [got, setGot] = useState<FlowLab | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [down, setDown] = useState(false);
  const [busy, setBusy] = useState(false);

  /* ★**스스로 안 돈다** — 손잡이를 돌릴 때마다 서버가 격자를 가짜 판에 돌리면
     창이 쓸 수 없게 느려지고, 무엇보다 「고르는 중에 결과가 바뀌는」 화면은
     사람이 제일 좋은 칸을 **무심코 고르게** 만든다. 그게 오늘 죽은 그 길이다. */
  const run = useCallback(() => {
    setBusy(true);
    setErr(null);
    fetchFlowLab({ subject: subj, tenor: ten, target, short, long, hold })
      .then((r) => { setGot(r); setDown(false); })
      .catch((e: unknown) => {
        if (e instanceof BacktestUnavailable) { setDown(true); return; }
        setErr(e instanceof Error ? e.message : String(e));
      })
      .finally(() => setBusy(false));
  }, [subj, ten, target, short, long, hold]);

  /* 창을 열면 **고른 칸으로 한 번** 돈다 — 그 뒤로는 사람이 누른다. */
  useEffect(() => { run(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const r = got?.result;
  const beat = got?.searchCeiling.beat ?? null;
  /** ★판정은 **탐색의 우연**으로 가른다 — 한 칸의 p 가 아니다(머리 §수를 혼자). */
  const verdict = beat == null ? null : beat <= 0.05;

  const lines: TimeLine[] = got
    ? [{
      id: 'cum',
      values: got.cum,
      color: (p) => (verdict ? p.up : p.dim(p.fgMuted, 70)),
      width: 2,
      format: won,
    }]
    : [];

  return (
    <FloatingWindow
      windowKey="flow-lab"
      title="수급 신호 실험"
      width={900}
      aside={
        <Text as="span" font="legal" color="fgMuted">
          {got ? `${got.from} ~ ${got.to} · ${r?.bars}봉` : '라이브 전용'}
        </Text>
      }
      onClose={onClose}
    >
      <VStack gap={1.5} padding={2} width="100%">
        {/* ── 손잡이 ─────────────────────────────────────────────────── */}
        <HStack gap={2} alignItems="flex-end" flexWrap="wrap">
          {/* ★주체·만기물은 **전부** 고를 수 있어야 한다. 첫 판은 셋씩만 세웠는데
              (`slice(0,3)`), 그러면 **탐색에서 실제로 1등 했던 국가지자체**를 아예
              못 고른다 — 고를 수 없는 칸이 있는 실험 창은 그 자체가 숨은 선택이다.
              열 주체를 알약으로 세우면 970px 이라 창(900)을 넘으므로 `Select` 로
              간다(Backtest 가 종류·종목에 쓰는 그 부품·그 `DROPDOWN_STYLES`). */}
          <Box width={160}>
            <Field label="주체">
              <Select size="s" font="legal" styles={DROPDOWN_STYLES}
                accessibilityLabel="주체" value={subj}
                onChange={(v) => v && setSubj(String(v))}
                options={subjects.map((x) => ({ value: x.key, label: x.label }))} />
            </Field>
          </Box>
          <Box width={140}>
            <Field label="만기물">
              <Select size="s" font="legal" styles={DROPDOWN_STYLES}
                accessibilityLabel="만기물" value={ten}
                onChange={(v) => v && setTen(String(v))}
                options={tenors.map((x) => ({ value: x.key, label: x.label }))} />
            </Field>
          </Box>
          <Box width={300}>
            <Field label="표적 금리">
              <Segmented label="표적 금리" value={target} onChange={setTarget}
                options={seg(TARGETS)} fill />
            </Field>
          </Box>
        </HStack>
        <HStack gap={2} alignItems="flex-end" flexWrap="wrap">
          <Box width={330}>
            <Field label="짧은 창">
              <Segmented label="짧은 창" value={String(short)}
                onChange={(v) => setShort(Number(v))} options={seg(SHORTS, '일')} fill />
            </Field>
          </Box>
          <Box width={330}>
            <Field label="긴 창">
              <Segmented label="긴 창" value={String(long)}
                onChange={(v) => setLong(Number(v))} options={seg(LONGS, '일')} fill />
            </Field>
          </Box>
          <Box width={280}>
            <Field label="최소 보유">
              <Segmented label="최소 보유" value={String(hold)}
                onChange={(v) => setHold(Number(v))} options={seg(HOLDS, '봉')} fill />
            </Field>
          </Box>
          <Button size="xs" className="sr-ctlfont" onClick={run} disabled={busy}>
            {busy ? '재는 중…' : '실행'}
          </Button>
        </HStack>

        {down ? (
          <Text as="p" font="label2" color="fgMuted">
            백엔드가 안 보여요 — 이 창은 라이브에서만 돌아요.
          </Text>
        ) : null}
        {err ? <Text as="p" font="label2" className="sr-down">{err}</Text> : null}

        {got && r ? (
          <>
            {/* ── 판정 — **탐색의 우연**으로 가른다 ─────────────────────── */}
            <VStack gap={0.5}>
              <Text as="p" font="label1"
                className={verdict ? 'sr-up' : undefined}
                color={verdict ? undefined : 'fgMuted'}>
                {verdict
                  ? `같은 크기 탐색의 우연을 넘었어요 — 가짜가 이긴 몫 ${(beat! * 100).toFixed(0)}%`
                  : `우연 안이에요 — 같은 크기 탐색의 가짜 1등이 ${((beat ?? 1) * 100).toFixed(0)}% 확률로 이겨요`}
              </Text>
              <Text as="p" font="legal" color="fgMuted">{got.warn}</Text>
            </VStack>

            {/* ── 수 ─────────────────────────────────────────────────── */}
            <HStack className="sr-stats" width="100%" flexWrap="wrap" gap={2}>
              <VStack gap={0.25}>
                <Text as="span" font="legal" color="fgMuted">순손익 · 최대낙폭</Text>
                <Text as="span" font="label1"
                  className={r.total >= 0 ? 'sr-up' : 'sr-down'}>
                  {won(r.total)} <Text as="span" font="legal" color="fgMuted">
                    / {won(r.mdd).replace('+', '')}</Text>
                </Text>
              </VStack>
              <VStack gap={0.25}>
                <Text as="span" font="legal" color="fgMuted">Calmar · 거래</Text>
                <Text as="span" font="label1">
                  {num(r.calmar)} <Text as="span" font="legal" color="fgMuted">
                    / {r.trades}회</Text>
                </Text>
              </VStack>
              <VStack gap={0.25}>
                <Text as="span" font="legal" color="fgMuted">① 그 칸의 우연</Text>
                <Text as="span" font="label1">
                  p {num(got.shuffle.p, 3)}{' '}
                  <Text as="span" font="legal" color="fgMuted">
                    중위 {num(got.shuffle.median)} · 95%p {num(got.shuffle.p95)}</Text>
                </Text>
              </VStack>
              <VStack gap={0.25}>
                {/* ★이 칸이 판정의 자다 — 창을 바꿔 가며 고르면 그게 탐색이다. */}
                <Text as="span" font="legal" color="fgMuted">
                  ② 탐색의 우연 ({got.searchCeiling.cells}칸)
                </Text>
                <Text as="span" font="label1" className={verdict ? 'sr-up' : 'sr-down'}>
                  {((beat ?? 1) * 100).toFixed(0)}%{' '}
                  <Text as="span" font="legal" color="fgMuted">
                    중위 {num(got.searchCeiling.median)} · 95%p {num(got.searchCeiling.p95)}</Text>
                </Text>
              </VStack>
            </HStack>

            {/* ── 누적 손익 ─────────────────────────────────────────── */}
            <Box className="sr-plot" height={220} width="100%">
              <TimeChart
                dates={got.dates}
                lines={lines}
                precision={0}
                priceLines={[{ value: 0, color: (p) => p.line }]}
                hoverLabel={(i) => `${got.dates[i]} · 누적 ${won(got.cum[i] ?? 0)}`}
                accessibilityLabel={`${got.subjectLabel} ${got.tenorLabel} 신호의 누적 손익`}
              />
            </Box>

            {/* ── 연도별 — 한 해가 다 먹고 있나 ───────────────────────── */}
            <VStack gap={0.5} width="100%">
              <Text as="span" font="label2">연도별 순손익</Text>
              <HStack gap={2} flexWrap="wrap">
                {got.byYear.map((y) => (
                  <VStack key={y.year} gap={0.25}>
                    <Text as="span" font="legal" color="fgMuted">{y.year}</Text>
                    <Text as="span" font="label2"
                      className={y.pnl >= 0 ? 'sr-up' : 'sr-down'}>
                      {won(y.pnl)}
                    </Text>
                    {/* 한 해가 절반을 넘으면 그 해의 거래라는 뜻이다. */}
                    <Text as="span" font="legal"
                      color={y.share != null && Math.abs(y.share) > 0.5 ? 'fgWarning' : 'fgMuted'}>
                      {y.share == null ? '—' : `${(y.share * 100).toFixed(0)}%`}
                    </Text>
                  </VStack>
                ))}
              </HStack>
            </VStack>

            <Text as="p" font="legal" color="fgMuted">
              {got.basis} 1bp 의 돈은 {fmtJo(got.dv01).replace('+', '')}조로 뒀어요 —
              수는 여기에 비례하는 눈금이에요.
            </Text>
          </>
        ) : null}
      </VStack>
    </FloatingWindow>
  );
}
