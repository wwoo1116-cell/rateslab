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
 * 냈다**: 한 칸을 무작위 거래와 견줘 「p 0.025 로 살았다」고 적었고, 탐색 전체로
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
 *
 * ## 화면 문법은 **캐논 부품**이다
 * [OWNER 2026-10-20 — 「v2 디자인 문법 사용하려면 제대로 사용하기」]
 *
 * 첫 판은 수 네 칸을 `VStack` 으로 **손으로 쌓았고** 커서 리드아웃이 아예 없었다.
 * 둘 다 이 리포에 이미 있는 부품이다(CLAUDE.md 캐논 규칙 1 — 새로 만들기 전에
 * 찾는다):
 *
 *   사실 스트립   `StatColumn` + `Stat`, 감싸는 `.sr-stats`   (`ui/Stat.tsx`)
 *   커서 리드아웃 `ChartReadoutStrip` + `slotChars`           (`ui/ChartReadoutStrip`)
 *   컨트롤        `Field` + `Segmented`/`Select`              (`ui/ControlCard`)
 *
 * 얼라인도 그 파일들의 규칙을 그대로 진다 — 컨트롤 행 등고 32px, 라벨은 컨트롤
 * 위, 행은 바닥 정렬, **폭은 감싸는 `Box` 가 준다**(얼라인 7).
 */

import { useCallback, useEffect, useState } from 'react';

import { Select } from '@coinbase/cds-web/alpha/select';
import { Button } from '@coinbase/cds-web/buttons';
import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Text } from '@coinbase/cds-web/typography';

import { TimeChart, type TimeLine } from '@/chart/TimeChart';
import { BacktestUnavailable } from '@/lib/api';
import { ROUTE_MISSING_DETAIL } from '@/lib/apiBase';
import { fmtJo } from '@/lib/format';
import { ChartReadoutStrip, slotChars, type StripSlot } from '@/ui/ChartReadoutStrip';
import { CONTROL_H } from '@/ui/controlHeight';
import { Field, Segmented } from '@/ui/ControlCard';
import { Stat, StatColumn } from '@/ui/Stat';
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
  /* 커서가 짚은 자리. 그림 밖이면 **마지막 봉**을 읽는다 — 「비어 있는 상태」가
     없어야 줄이 생겼다 사라지며 창 높이를 흔들지 않는다(FlowPage 와 같은 규율). */
  const [cursor, setCursor] = useState<number | null>(null);

  /* ★**스스로 안 돈다** — 손잡이를 돌릴 때마다 서버가 격자를 가짜 판에 돌리면
     창이 쓸 수 없게 느려지고, 무엇보다 「고르는 중에 결과가 바뀌는」 화면은
     사람이 제일 좋은 칸을 **무심코 고르게** 만든다. 그게 오늘 죽은 그 길이다. */
  const run = useCallback(() => {
    setBusy(true);
    setErr(null);
    fetchFlowLab({ subject: subj, tenor: ten, target, short, long, hold })
      .then((r) => { setGot(r); setDown(false); setCursor(null); })
      .catch((e: unknown) => {
        if (e instanceof BacktestUnavailable) { setDown(true); return; }
        setErr(e instanceof Error ? e.message : String(e));
      })
      .finally(() => setBusy(false));
  }, [subj, ten, target, short, long, hold]);

  /* 창을 열면 **고른 칸으로 한 번** 돈다 — 그 뒤로는 사람이 누른다.
     ⚠의존성을 비운 것은 **의도다**: `run` 을 넣으면 손잡이를 돌릴 때마다 저절로
     돌아 「스스로 안 돈다」가 깨진다(머리 §Backtest 와 같은 규율). */
  useEffect(() => {
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const r = got?.result;
  const at = got ? Math.min(cursor ?? got.cum.length - 1, got.cum.length - 1) : 0;
  const beat = got?.searchCeiling.beat ?? null;
  /** ★판정은 **탐색의 우연**으로 가른다 — 한 칸의 p 가 아니다(머리 §수를 혼자). */
  const verdict = beat == null ? null : beat <= 0.05;

  const lines: TimeLine[] = got
    ? [{
      id: 'cum',
      values: got.cum,
      /* 우연을 못 넘은 선은 **방향색을 안 입는다** — 칠하면 졌는데 이긴 것처럼
         읽힌다. 방향색은 부호와 매매에만 쓴다(CLAUDE.md 규칙 3 계열). */
      color: (p) => (verdict ? p.up : p.dim(p.fgMuted, 70)),
      width: 2,
      format: won,
    }]
    : [];

  /* 리드아웃은 **그림 밖·위**에 선다(캐논). 값 자리를 미리 비워 커서가 움직여도
     칸이 안 흔들린다(`slotChars`). */
  const slots: StripSlot[] = got
    ? [{
      key: 'cum',
      label: '누적 손익',
      value: won(got.cum[at] ?? 0),
      color: verdict ? 'var(--sr-up)' : 'var(--color-fgMuted)',
      chars: slotChars(won, Math.max(...got.cum), Math.min(...got.cum)),
    }]
    : [];

  return (
    <FloatingWindow
      windowKey="flow-lab"
      title="수급 신호 실험"
      /* 폭은 **최장 라벨 × 칸 수**로 잰다(얼라인 7). 알약 한 칸은 「글자폭 + 32」다.
         둘째 행이 제일 넓다 — 짧은 창 6칸 × 64 = 384 · 긴 창 6칸 × 71(「120일」)
         = 426 · 실행 96 · gap 32 = 938. 첫 행은 160 + 140 + 285 + 320 + gap 48
         = 953. 안쪽 여백 32 를 더해 **1,160** 이면 둘 다 한 줄에 서고 안 접힌다
         (Backtest 1,020 보다 넓은 것은 손잡이가 여섯이라서다). */
      width={1160}
      aside={
        <Text as="span" font="legal" color="fgMuted" noWrap>
          {got ? `${got.from} ~ ${got.to} · ${r?.bars}봉` : '라이브 전용'}
        </Text>
      }
      onClose={onClose}
    >
      <VStack gap={1.5} paddingX={2} paddingTop={1.5} paddingBottom={2} width="100%">
        {/* ── 손잡이 두 줄 — 바닥 정렬 · 라벨은 컨트롤 위 · 폭은 상자가 준다 ── */}
        <HStack gap={2} alignItems="flex-end" flexWrap="wrap">
          {/* ★주체·만기물은 **전부** 고를 수 있어야 한다. 셋만 세우면 탐색에서
              실제로 1등 했던 국가지자체를 못 고른다 — 고를 수 없는 칸이 있는
              실험 창은 그 자체가 숨은 선택이다. 열 주체를 알약으로 세우면
              970px 이라 `Select` 로 간다(Backtest 가 종류·종목에 쓰는 그 부품). */}
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
          <Box width={285}>
            <Field label="표적 금리">
              <Segmented label="표적 금리" value={target} onChange={setTarget}
                options={seg(TARGETS)} fill />
            </Field>
          </Box>
          <Box width={320}>
            <Field label="최소 보유">
              <Segmented label="최소 보유" value={String(hold)}
                onChange={(v) => setHold(Number(v))} options={seg(HOLDS, '봉')} fill />
            </Field>
          </Box>
        </HStack>
        <HStack gap={2} alignItems="flex-end" flexWrap="wrap">
          <Box width={384}>
            <Field label="짧은 창">
              <Segmented label="짧은 창" value={String(short)}
                onChange={(v) => setShort(Number(v))} options={seg(SHORTS, '일')} fill />
            </Field>
          </Box>
          <Box width={426}>
            <Field label="긴 창">
              <Segmented label="긴 창" value={String(long)}
                onChange={(v) => setLong(Number(v))} options={seg(LONGS, '일')} fill />
            </Field>
          </Box>
          {/* ★버튼도 **같은 32px 상자**에 담는다 — 안 담으면 이 칸만 바닥에서
              어긋난다(얼라인 1 의 백테스트 「진입 레벨」 판례).
              ⚠수는 **따로 적지 않는다** — `ui/controlHeight` 가 정본이고
              `align-canon` 가드가 손으로 적은 32 를 잡는다(실제로 잡혔다). */}
          <Box width={96} height={CONTROL_H}>
            <Button size="xs" className="sr-ctlfont" onClick={run} disabled={busy} block>
              {busy ? '재는 중…' : '실행'}
            </Button>
          </Box>
        </HStack>

        {down ? (
          <Text as="p" font="label2" color="fgMuted">
            {ROUTE_MISSING_DETAIL} 이 창은 라이브에서만 돌아요.
          </Text>
        ) : null}
        {err ? <Text as="p" font="label2" className="sr-down">{err}</Text> : null}

        {got && r ? (
          <>
            {/* ── 판정 — 이 창의 머리말 ─────────────────────────────────── */}
            <VStack gap={0.5}>
              <Text as="p" font="title3"
                className={verdict ? 'sr-up' : undefined}
                color={verdict ? undefined : 'fgMuted'}>
                {verdict
                  ? `같은 크기 탐색의 우연을 넘었어요 — 가짜가 이긴 몫 ${(beat! * 100).toFixed(0)}%`
                  : `우연 안이에요 — 같은 크기 탐색의 가짜 1등이 ${((beat ?? 1) * 100).toFixed(0)}% 확률로 이겨요`}
              </Text>
              <Text as="p" font="legal" color="fgMuted">{got.warn}</Text>
            </VStack>

            {/* ── 수 — **캐논 사실 스트립**이다(`ui/Stat`). 손으로 쌓지 않는다. ── */}
            <Box width="100%">
              <HStack className="sr-stats" width="100%" flexWrap="wrap">
                <StatColumn title="성과">
                  <Stat label="순손익" value={won(r.total)}
                    tone={r.total > 0 ? 'up' : r.total < 0 ? 'down' : undefined}
                    note={`최대낙폭 ${won(r.mdd).replace('+', '')}`} />
                  {/* ★라벨은 `caption` 이라 CDS 테마가 **대문자화를 건다** —
                      「Calmar」가 「CALMAR」로, 「95%p」가 「95%P」로 섰다
                      (`ui/ThHelp` 가 「bp → BP」로 적어 둔 그 판례). 부품은
                      앱 공용이라 못 고치니 **라벨을 한글로** 둔다. */}
                  <Stat label="칼마" value={num(r.calmar)}
                    note={`거래 ${r.trades}회 · ${r.bars}봉`} />
                </StatColumn>
                <StatColumn title="① 그 칸의 우연">
                  <Stat label="우연일 확률" value={num(got.shuffle.p, 3)}
                    note={`가짜 ${got.shuffle.draws}판`} />
                  <Stat label="가짜 중위 · 상위 5%"
                    value={`${num(got.shuffle.median)} · ${num(got.shuffle.p95)}`} />
                </StatColumn>
                {/* ★이 칸이 **판정의 자**다 — 창을 바꿔 가며 고르면 그게 탐색이고,
                    탐색의 우연은 한 칸의 우연보다 훨씬 세다. */}
                <StatColumn title={`② 탐색의 우연 · ${got.searchCeiling.cells}칸`}>
                  <Stat label="가짜 1등이 이긴 몫"
                    value={`${((beat ?? 1) * 100).toFixed(0)}%`}
                    tone={verdict ? 'up' : 'down'}
                    note={`가짜 ${got.searchCeiling.draws}판`} />
                  <Stat label="가짜 중위 · 상위 5%"
                    value={`${num(got.searchCeiling.median)} · ${num(got.searchCeiling.p95)}`} />
                </StatColumn>
              </HStack>
            </Box>

            {/* ── 누적 손익 — 리드아웃은 **그림 밖·위** ──────────────────── */}
            <VStack width="100%" gap={0.5}>
              <HStack alignItems="baseline" justifyContent="space-between" gap={1}>
                <Text as="span" font="label2">누적 손익</Text>
                <Text as="span" font="legal" color="fgMuted">
                  {/* ★`fmtJo` 는 **백만원**을 받는데 `dv01` 은 **원**이다 —
                      그대로 넣었더니 1,000만원이 「10.0조」로 찍혔다(실측
                      2026-10-20). 단위가 다른 수를 같은 서식에 넣으면 그럴듯하게
                      틀린다. 여기서 원 → 만원으로 직접 읽는다. */}
                  1bp 의 돈을 {(got.dv01 / 1e4).toLocaleString('ko-KR')}만원으로 둔
                  눈금이에요 — 수는 여기에 비례해요
                </Text>
              </HStack>
              {/* ★감싸는 상자는 **세로**여야 한다 — `Box`(CDS 기본 가로 flex)면
                  `width="100%"` 를 줘도 상자만 늘고 스트립은 제 내용 폭으로 줄어
                  통째로 잘린다(`FlowPage` 가 두 번 밟은 그 자리). */}
              <VStack width="100%">
                <ChartReadoutStrip
                  date={got.dates[at] ?? got.to}
                  slots={slots}
                  ariaLabel="누적 손익 — 커서가 짚은 날의 값"
                />
              </VStack>
              <Box className="sr-plot" height={260} width="100%">
                <TimeChart
                  dates={got.dates}
                  lines={lines}
                  precision={0}
                  priceLines={[{ value: 0, color: (p) => p.line }]}
                  onHoverIndex={setCursor}
                  hoverLabel={(i) => `${got.dates[i]} · 누적 ${won(got.cum[i] ?? 0)}`}
                  accessibilityLabel={`${got.subjectLabel} ${got.tenorLabel} 신호의 누적 손익`}
                />
              </Box>
            </VStack>

            {/* ── 연도별 — 한 해가 다 먹고 있나 ──────────────────────────── */}
            <Box width="100%">
              <HStack className="sr-stats" width="100%" flexWrap="wrap">
                <StatColumn title="연도별 순손익">
                  {got.byYear.map((y) => (
                    <Stat key={y.year} label={y.year} value={won(y.pnl)}
                      tone={y.pnl > 0 ? 'up' : y.pnl < 0 ? 'down' : undefined}
                      /* 한 해가 절반을 넘으면 **그 해의 거래**라는 뜻이다 — 앞
                         레인이 죽은 자리가 정확히 그것이었다(2022 한 해에 51~85%). */
                      note={y.share == null ? '—'
                        : `${(y.share * 100).toFixed(0)}%${Math.abs(y.share) > 0.5 ? ' ★한 해가 절반 넘음' : ''}`} />
                  ))}
                </StatColumn>
              </HStack>
            </Box>

            <Text as="p" font="legal" color="fgMuted">{got.basis}</Text>
          </>
        ) : null}
      </VStack>
    </FloatingWindow>
  );
}
