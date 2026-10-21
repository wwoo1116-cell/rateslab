'use client';

import { Button } from '@coinbase/cds-web/buttons';

import { HStack, VStack } from '@coinbase/cds-web/layout';
import { Text, TextBody, TextCaption } from '@coinbase/cds-web/typography';

import { unreachableDetail } from '@/lib/apiBase';
import { eul } from '@/lib/josa';

/**
 * A failure looks different from a wait, and a failure is retryable in place.
 *
 * v1's diagnosis, carried: every backend failure — process down, a 500, a 200 with a
 * truncated body — rendered the same "불러오는 중입니다", permanently. Still "loading"
 * at 81 seconds. A reader could not tell a slow morning from a dead service and had
 * nothing to do about either.
 *
 * So these are two components with different shapes, and the error holds a BUTTON
 * rather than a toast: nothing dismisses itself, and recovery never requires knowing
 * to reload the page.
 */

export function LoadingState({ what }: { what: string }) {
  return (
    <VStack gap={0.5} paddingY={2}>
      <TextBody as="p" color="fgMuted">
        {what}
        {eul(what)} 불러오는 중이에요
      </TextBody>
    </VStack>
  );
}

/**
 * 그림이 설 자리가 비었을 때 — **0선을 긋고 그 틀 안에 한 문장** [디자인 감사
 * 2026-10-21].
 *
 * `LoadingState` 는 한 줄짜리 문장이라 **표**에는 맞지만 **그림 자리**에는
 * 안 맞는다. 실측: Main 셋째 카드가 큰 숫자만 세우고 그 아래 차트 자리를 수 초
 * 동안 흰 칸으로 뒀고, Mean Reversion 순위표는 머리만 서고 아래 380px 가 공백
 * 이었다. 같은 화면의 옆 카드는 같은 상태를 문장으로 처리해서, 한 화면이 같은
 * 상태를 두 문법으로 말하고 있었다.
 *
 * 스켈레톤을 안 쓰는 까닭: 그림 자리에서 쓸모 있는 것은 「뭔가 올 것」이 아니라
 * **「축이 어디 설 것인가」**다. 0선이 그어져 있으면 들어올 수가 그 위인지
 * 아래인지 읽을 준비가 되고, 수가 도착할 때 틀이 안 흔들린다.
 *
 * 선은 `--color-bgLine`(면 토큰)이고 글자는 뮤트다 — 둘 다 값을 말하지 않는다.
 * 빈 자리가 데이터처럼 보이면 안 되므로 **눈금 숫자는 안 적는다.**
 */
export function ChartBlank({ note, minHeight = 120 }: { note: string; minHeight?: number }) {
  return (
    <VStack
      className="sr-chartblank"
      justifyContent="center"
      alignItems="center"
      flexGrow={1}
      minHeight={minHeight}
      aria-live="polite"
    >
      <Text font="caption" as="p" color="fgMuted">
        {note}
      </Text>
    </VStack>
  );
}

export function ErrorState({
  what,
  detail,
  onRetry,
  retrying = false,
}: {
  what: string;
  detail?: string;
  onRetry: () => void;
  retrying?: boolean;
}) {
  return (
    <VStack gap={1} paddingY={2} role="alert">
      <TextBody as="p">
        {what}
        {eul(what)} 불러오지 못했어요
      </TextBody>
      <TextCaption as="span" color="fgMuted">
        {/* 읽는 사람의 말로 적은 가장 그럴듯한 원인.
            ★[2026-10-01] 종전 기본 문구는 「백엔드(:8200)가 응답하지 않았어요」였는데
            **멀리서 보는 사람에게는 틀린 말**이다 — 그 사람 PC 에는 :8200 이 없다.
            그가 확인할 수 있는 사실은 「이 주소에 못 닿았다」 하나이고, 주소를 아는
            곳은 `lib/apiBase` 다(밖에서 URL 을 다시 조립하지 않는다는 그 규율). */}
        {detail ?? unreachableDetail()}
      </TextCaption>
      <HStack>
        <Button size="s" variant="secondary" onClick={onRetry} disabled={retrying}>
          {retrying ? '다시 시도하는 중' : '다시 시도'}
        </Button>
      </HStack>
    </VStack>
  );
}

/** The freshness chip. The LEVEL is decided by the backend, per source — a browser
 * that decides what "stale" means is a second opinion, and the two will disagree on
 * the day it matters. */
export function FreshnessChip({
  asof,
  level,
  source,
}: {
  asof?: string;
  level?: 'current' | 'behind' | 'stale';
  source: string;
}) {
  if (!asof) return null;
  const word = level === 'stale' ? '오래됨' : level === 'behind' ? '하루 늦음' : '';
  return (
    <TextCaption as="span" color="fgMuted">
      {asof} · {source}
      {word ? ` · ${word}` : ''}
    </TextCaption>
  );
}
