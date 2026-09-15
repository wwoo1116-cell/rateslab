'use client';

import { Button } from '@coinbase/cds-web/buttons';

import { HStack, VStack } from '@coinbase/cds-web/layout';
import { TextBody, TextCaption } from '@coinbase/cds-web/typography';

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
        {/* The likeliest cause, in the reader's terms — :8200 is v2's own backend and
            the only thing that serves this screen. */}
        {detail ?? '백엔드(:8200)가 응답하지 않았어요. 꺼져 있을 수 있어요.'}
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
