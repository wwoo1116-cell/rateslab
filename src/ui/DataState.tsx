'use client';

import { Button } from '@coinbase/cds-web/buttons';

import { HStack, VStack } from '@coinbase/cds-web/layout';
import { TextBody, TextCaption } from '@coinbase/cds-web/typography';

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
