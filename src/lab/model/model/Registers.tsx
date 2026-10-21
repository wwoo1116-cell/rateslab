'use client';

/* 방정식 등록부 · 계수표 · 미인쇄 인구조사.
 *
 * ## 인쇄된 것과 구현된 것을 **둘 다** 보여준다
 *
 * 「논문대로」 라고 적어 두고 다른 것을 계산하면 아무도 못 잡는다. 그래서 이
 * 등록부는 44개 인쇄식마다 «논문이 인쇄한 것» 과 «우리가 계산하는 것» 을 나란히
 * 놓고, 다르면 그 차이를 문장으로 적는다. 2026-08-21 의 수정 넷(eq 19 Δ₄ ·
 * eq 8/11 Δŷ · eq 21 에 IH·G · eq 40/42 전가 1.0)이 여기 서 있다.
 *
 * ## 「배선됨」은 유도값이다
 *
 * 손으로 안 적는다. 배선 그래프에 그 식 번호를 단 엣지가 있으면 배선된 것이다.
 * 그래야 다음에 배선이 바뀌었을 때 이 표가 혼자 낡지 않는다.
 *
 * ## 미공표는 **빈칸이 아니라 이름**으로
 *
 * 논문이 안 실은 계수를 빈칸으로 두면 «아직 안 채웠다» 로 읽힌다. 이름을 적고
 * 「논문 미공표」 라고 말한다.
 */

import { useMemo, useState } from 'react';

import { Chip } from '@coinbase/cds-web/chips';
import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import {
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from '@coinbase/cds-web/tables';
import { Text } from '@coinbase/cds-web/typography';

import { anchorProps, ANCHORS, eq as eqAnchor } from '../anchors';

import { Emph } from './emph';
import surfaceJson from './model_surface.json';

type Equation = {
  no: string;
  name: string;
  block: string;
  page: string | null;
  printed: string;
  differs: string | null;
  wired: boolean;
};

type Coefficient = {
  slot: string;
  group: string;
  symbol: string | null;
  value: number | null;
  status: 'RESOLVED' | 'PROVISIONAL' | 'EXOG_V1';
  basis: string;
  candidates: string[];
  equation: string | null;
  wired: boolean;
};

type CensusBucket = {
  name: string;
  count: number | null;
  how: string;
  confidence: string;
};

type Surface = {
  equations: Equation[];
  coefficients: Coefficient[];
  coefficient_counts: Record<string, number>;
  stale_exog: string;
  unpublished: [string, string][];
  census: {
    total: number;
    printed: number;
    unprinted: number;
    partial: boolean;
    note: string;
    buckets: CensusBucket[];
  };
  eq_no_corrections: { where: string; code: string; paper: string; why: string }[];
};

const S = surfaceJson as unknown as Surface;

const STATUS_LABEL: Record<string, string> = {
  RESOLVED: '논문 부록 D',
  PROVISIONAL: '논문 미공표',
  EXOG_V1: '외생 고정 (라벨 낡음)',
};

const BLOCK_LABEL: Record<string, string> = {
  framework: 'PAC 틀',
  external: '해외',
  expenditure: '지출',
  price: '물가',
  financial: '금융',
};

/* ── 방정식 등록부 ──────────────────────────────────────────────────────────── */

export function EquationRegister() {
  const [onlyDiffers, setOnlyDiffers] = useState(false);
  const rows = useMemo(
    () => (onlyDiffers ? S.equations.filter((e) => e.differs) : S.equations),
    [onlyDiffers],
  );
  const nDiffers = S.equations.filter((e) => e.differs).length;
  const nWired = S.equations.filter((e) => e.wired).length;

  return (
    <VStack gap={1.5} width="100%" {...anchorProps(ANCHORS.model.equationRegister)}>
      <VStack gap={0.5}>
        {/* **개수를 문장 안에 숨기지 않는다** [2026-08-24]. 「44개 중 N개」 가
            회색 13px 문장 안에 있으면 아무도 안 읽는다. 이 앱은 스코어카드의
            `9/13` 처럼 세는 숫자를 크게 세운다 — 백테스트 카드의 헤드라인
            숫자, 코인베이스·토스의 종목 머리가 전부 같은 것을 한다(실측). */}
        <HStack gap={1.5} alignItems="baseline" flexWrap="wrap">
          <Text as="h3" font="label1">
            방정식 등록부
          </Text>
          <Text as="span" font="title1" tabularNumbers noWrap>
            {nWired}/{S.equations.length}
          </Text>
          <Text as="span" font="legal" color="fgMuted">
            에 배선이 붙어 있어요
          </Text>
        </HStack>
        <Text as="p" font="legal" color="fgMuted">
          논문 207개 식 중 인쇄된 것이 {S.equations.length}개예요. 그중{' '}
          <b>{nDiffers}개</b>는 인쇄된 것과 우리가 계산하는 것이 달라요.
        </Text>
      </VStack>

      <HStack gap={1} flexWrap="wrap">
        <Chip
          size="xs"
          className="sr-chip-toggle"
          aria-pressed={onlyDiffers}
          onClick={() => setOnlyDiffers(!onlyDiffers)}
          accessibilityLabel="인쇄된 것과 다른 식만 보기"
        >
          다른 것만 {nDiffers}
        </Chip>
      </HStack>

      <VStack gap={0} width="100%" className="sr-eqreg">
        {rows.map((e) => (
          <VStack
            key={e.no}
            gap={0.25}
            width="100%"
            paddingY={1}
            {...anchorProps(eqAnchor(e.no))}
          >
            <HStack gap={1} alignItems="baseline" flexWrap="wrap">
              <Text as="span" font="label2" noWrap>
                식 ({e.no})
              </Text>
              <Text as="span" font="label2" noWrap>
                <Emph t={e.name} />
              </Text>
              <Text as="span" font="legal" color="fgMuted" noWrap>
                {BLOCK_LABEL[e.block] ?? e.block}
                {e.page ? ` · 논문 ${e.page}` : ''}
              </Text>
              {!e.wired ? (
                <Text as="span" font="legal" color="fgMuted" noWrap>
                  배선 없음
                </Text>
              ) : null}
            </HStack>
            <Text as="p" font="legal" color="fgMuted">
              <Emph t={e.printed} />
            </Text>
            {e.differs ? (
              <Text as="p" font="legal" className="sr-eqreg-diff">
                <Emph t={e.differs} />
              </Text>
            ) : null}
          </VStack>
        ))}
      </VStack>

      {/* **정정표는 비워 두고 없애지 않는다** (D.3). 같은 일이 다시 생기면
          여기 서야 하고, 그러려면 지금 비어 있다는 것도 화면이 말해야 한다 —
          `map` 만 하면 «없다» 와 «안 봤다» 가 화면에서 같아진다. */}
      {S.eq_no_corrections.length === 0 ? (
        <Text as="p" font="legal" color="fgMuted">
          <b>번호 라벨 어긋남</b> — 지금은 갈리는 자리가 없어요. 코드가 스스로를
          부르는 번호와 인쇄 번호가 44개 식에서 다 같아요.
        </Text>
      ) : null}
      {S.eq_no_corrections.map((c) => (
        <Text key={c.where} as="p" font="legal" color="fgMuted">
          <b>번호 라벨 어긋남</b> — 코드의 <code>{c.where}</code> 가 스스로를 식 (
          {c.code}) 이라 부르는데 인쇄 번호는 ({c.paper}) 이에요. <Emph t={c.why} /> 배선은
          맞고 라벨만 틀렸어요.
        </Text>
      ))}
    </VStack>
  );
}

/* ── 계수표 ─────────────────────────────────────────────────────────────────── */

export function CoefficientTable() {
  const [status, setStatus] = useState<string | null>(null);
  const rows = useMemo(
    () => (status ? S.coefficients.filter((c) => c.status === status) : S.coefficients),
    [status],
  );

  return (
    <VStack gap={1.5} width="100%" {...anchorProps(ANCHORS.model.coefficientRegister)}>
      <VStack gap={0.5}>
        <HStack gap={1.5} alignItems="baseline" flexWrap="wrap">
          <Text as="h3" font="label1">
            계수
          </Text>
          <Text as="span" font="title1" tabularNumbers noWrap>
            {S.coefficients.length}
          </Text>
          <Text as="span" font="legal" color="fgMuted">
            슬롯 · 부록 D Table 1~17
          </Text>
        </HStack>
        <Text as="p" font="legal" color="fgMuted">
          값 하나하나가 어디서 왔는지 「출처」 열이 말해요.
        </Text>
      </VStack>

      <HStack gap={1} flexWrap="wrap">
        <Chip
          size="xs"
          className="sr-chip-toggle"
          aria-pressed={status === null}
          onClick={() => setStatus(null)}
          accessibilityLabel="모든 계수"
        >
          전체 {S.coefficients.length}
        </Chip>
        {(['RESOLVED', 'PROVISIONAL', 'EXOG_V1'] as const).map((s) => (
          <Chip
            key={s}
            size="xs"
            className="sr-chip-toggle"
            aria-pressed={status === s}
            onClick={() => setStatus(status === s ? null : s)}
            accessibilityLabel={STATUS_LABEL[s]}
          >
            {STATUS_LABEL[s]} {S.coefficient_counts[s] ?? 0}
          </Chip>
        ))}
      </HStack>

      <Text as="p" font="legal" color="fgMuted">
        <Emph t={S.stale_exog} />
      </Text>

      <Box overflow="auto" width="100%" className="sr-coef-scroll">
        <Table tableLayout="auto">
          <TableHeader>
            <TableRow>
              {['기호', '값', '슬롯', '식', '출처'].map((h, i) => (
                <TableCell
                  as="th"
                  scope="col"
                  key={h}
                  className={i === 1 ? 'sr-num' : 'sr-label'}
                  justifyContent={i === 1 ? 'flex-end' : undefined}
                >
                  <Text as="span" font="legal" color="fgMuted" noWrap>
                    {h}
                  </Text>
                </TableCell>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((c) => (
              <TableRow key={c.slot}>
                <TableCell className="sr-label">
                  <Text as="span" font="label2" noWrap>
                    {c.symbol ?? '—'}
                  </Text>
                </TableCell>
                <TableCell className="sr-num" justifyContent="flex-end">
                  <Text as="span" font="legal" tabularNumbers noWrap>
                    {c.value == null ? '—' : c.value}
                  </Text>
                </TableCell>
                <TableCell className="sr-label">
                  <Text as="span" font="legal" color="fgMuted" noWrap>
                    {c.slot}
                  </Text>
                </TableCell>
                <TableCell className="sr-label">
                  <Text as="span" font="legal" color="fgMuted" noWrap>
                    {c.equation ? (
                      <a href={`#${eqAnchor(c.equation)}`}>식 ({c.equation})</a>
                    ) : (
                      '—'
                    )}
                  </Text>
                </TableCell>
                {/* 이 칸의 머리는 「출처」 인데 2026-08-24 까지 상태 낱말
                    하나(RESOLVED·CALIBRATED…)만 찍고 있었다. 진짜 출처 문장은
                    `basis` 에 132행 전부 실려 오는데 화면에 없었다 — 머리가
                    약속한 것을 칸이 안 내면 그 표는 자기 열 이름으로 거짓말을
                    한다. 후보(`candidates`)도 같은 이유로 같이 낸다: 열다섯
                    행은 「이 슬롯에 무엇이 올 수 있었나」 가 곧 그 값의 근거다. */}
                <TableCell className="sr-label">
                  <VStack gap={0.25}>
                    <Text as="span" font="legal" color="fgMuted">
                      {STATUS_LABEL[c.status]}
                      {c.wired ? '' : ' · 배선 안 씀'}
                    </Text>
                    <Text as="span" font="legal" color="fgMuted">
                      {c.basis}
                    </Text>
                    {c.candidates.length > 0 ? (
                      <Text as="span" font="legal" color="fgMuted">
                        후보: {c.candidates.join(' · ')}
                      </Text>
                    ) : null}
                  </VStack>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>

      <VStack gap={0.5} width="100%">
        <Text as="h4" font="label2">
          부록 D 에 아예 없는 것 — 빈칸이 아니라 이름으로
        </Text>
        {S.unpublished.map(([name, why]) => (
          <Text key={name} as="p" font="legal" color="fgMuted">
            <b><Emph t={name} /></b> — <Emph t={why} />
          </Text>
        ))}
      </VStack>
    </VStack>
  );
}

/* ── 미인쇄 인구조사 ────────────────────────────────────────────────────────── */

export function Census() {
  const c = S.census;
  return (
    <VStack gap={1.5} width="100%" {...anchorProps(ANCHORS.model.census)}>
      <VStack gap={0.5}>
        <HStack gap={1.5} alignItems="baseline" flexWrap="wrap">
          <Text as="h3" font="label1">
            인쇄되지 않은 식
          </Text>
          <Text as="span" font="title1" tabularNumbers noWrap>
            {c.unprinted}
          </Text>
          <Text as="span" font="legal" color="fgMuted">
            개 · 논문 {c.total}개 중 {c.printed}개만 인쇄돼요
          </Text>
        </HStack>
        <Text as="p" font="legal" color="fgMuted">
          <Emph t={c.note} />
        </Text>
      </VStack>

      <VStack gap={0} width="100%" className="sr-eqreg">
        {c.buckets.map((b) => (
          <HStack key={b.name} gap={1.5} paddingY={1} alignItems="baseline" flexWrap="wrap">
            <Box width={56} flexShrink={0}>
              <Text as="span" font="label1" tabularNumbers noWrap>
                {b.count == null ? '—' : b.count}
              </Text>
            </Box>
            <VStack gap={0.25} flexGrow={1} minWidth={0}>
              <HStack gap={1} alignItems="baseline" flexWrap="wrap">
                <Text as="span" font="label2">
                  <Emph t={b.name} />
                </Text>
                <Text as="span" font="legal" color="fgMuted" noWrap>
                  {b.confidence}
                </Text>
              </HStack>
              <Text as="p" font="legal" color="fgMuted">
                <Emph t={b.how} />
              </Text>
            </VStack>
          </HStack>
        ))}
      </VStack>
    </VStack>
  );
}
