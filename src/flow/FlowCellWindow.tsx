'use client';

/* 한 칸을 **자세히** — (만기물 × 주체) 하나에 대해 이 화면이 아는 것 전부
 * [OWNER 2026-10-21 — 「첫 화면에서 수급상황을 확인하고, 거기서 특정 버튼 누르면
 * 창을 띄워주는거」].
 *
 * ## 왜 창인가
 *
 * 한 칸을 판단하려면 지금 **네 군데**를 봐야 한다: 행렬의 그 칸(구간 합), 같은
 * 행의 발행, 순위 창의 그 줄(오늘·5일·20일·올해·분포 자리·보유), 그리고 감마 줄.
 * 눈으로 네 곳을 잇는 동안 어느 것이 어느 창의 수인지가 섞인다 — 실제로 이 면의
 * 두 표는 **서로 다른 창**을 말한다(행렬은 고른 구간의 합, 순위는 오늘).
 *
 * 그래서 한 칸을 고른 채로 여는 창이고, **창 자체가 창(구간)을 적는다.**
 *
 * ## 이 창이 하지 않는 것 — ★제일 중요하다
 *
 * **판단을 하지 않는다.** 「이 수급이면 금리가 이쪽」은 이 리포가 2026-10-20 에
 * 재서 **KILL** 한 자리다(`flow.py` 머리 · 화면의 감마 줄도 같은 말을 적는다).
 * 여기는 재료를 한자리에 모을 뿐이고, 모으는 것과 가리키는 것은 다른 일이다.
 * 어떤 칸도 「사라/팔아라」를 뜻하지 않는다.
 *
 * ## 산술이 없다
 *
 * 모든 수는 **서버가 낸 것을 그대로** 세운다(§16). 화면이 더하면 두 면이 다른
 * 수를 말하게 된다 — 이 레인에서 `FlowMatrix` 의 `reduce` 가 그래서 막혔고
 * (`guards/strategy-flow`), 같은 이유로 여기서도 안 더한다. 비율 하나(`share`)도
 * 서버가 계산해 보낸 값이다.
 */

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Text } from '@coinbase/cds-web/typography';

import { fmtJo } from '@/lib/format';
import { FloatingWindow } from '@/ui/window/FloatingWindow';
import { Stat, StatColumn } from '@/ui/Stat';

import type { FlowBoard, FlowRow, IssuanceUnit } from './api';

/** 억 단위 정수 — 순위 창의 `val` 과 같은 자다. 화면이 단위를 바꾸지 않는다. */
function eok(v: number | null | undefined): string {
  if (v == null) return '—';
  const s = Math.round(v / 100).toLocaleString('ko-KR');
  return v > 0 ? `+${s}` : s;
}

/** 방향색은 **부호 있는 값에만**. 수량·비율은 잉크다(CLAUDE.md 규칙 3 계열).
 *  `Stat` 은 값을 문자열로 받고 색은 `tone` 이 지므로, 부호를 톤으로 옮긴다. */
function tone(v: number | null | undefined): 'up' | 'down' | undefined {
  if (v == null || v === 0) return undefined;
  return v > 0 ? 'up' : 'down';
}

export function FlowCellWindow({
  board, sub, tenorLabel, cellValue, supply, auction, onClose,
}: {
  board: FlowBoard;
  /** 고른 주체의 순위 한 줄 — 없으면 창을 안 연다(부르는 쪽이 막는다). */
  sub: FlowRow;
  tenorLabel: string;
  /** 행렬에서 이 (만기물 × 주체) 칸의 구간 합. `null` 이면 행렬이 없는 면이다. */
  cellValue: number | null;
  /** 같은 행의 발행. */
  supply: number | null;
  auction: IssuanceUnit | null;
  onClose: () => void;
}) {
  const hold = sub.hold ?? null;
  const span = board.matrix
    ? `${board.matrix.from ?? '?'} ~ ${board.matrix.to ?? '?'}`
    : null;

  return (
    <FloatingWindow
      windowKey="flow-cell"
      title={`${sub.label} · ${tenorLabel}`}
      width={760}
      onClose={onClose}
    >
      <VStack gap={1.5} width="100%" minWidth={0}>
        {/* ★이 창이 무엇인지 **먼저** 적는다 — 「재료」와 「판단」의 경계가
            흐려지면 이 면 전체가 예측 화면으로 읽힌다. */}
        <Text as="p" font="legal" color="fgMuted">
          이 칸에 대해 화면이 아는 것을 한자리에 모은 거예요 — 판단이 아니에요.
          수급으로 금리 방향을 맞추는 것은 재서 안 되는 것으로 나왔어요(2026-10-20).
        </Text>

        {/* ── ① 고른 구간 — 행렬이 말하는 것 ────────────────────────────── */}
        <HStack className="sr-stats" width="100%" flexWrap="wrap">
          <StatColumn title={span ? `고른 구간 · ${span}` : '고른 구간'}>
            <Stat label={`${sub.label}가 담은 양`}
              value={cellValue == null ? '—' : `${fmtJo(cellValue)}조`}
              note={`${tenorLabel} 한 칸이에요`} />
            <Stat label="같은 기간 발행"
              value={supply == null ? '—' : `${fmtJo(supply).replace('+', '')}조`}
              note={supply == null ? '행렬이 없는 면이에요' : '경쟁 낙찰 + 비경쟁 − 매입'} />
          </StatColumn>
        </HStack>

        {/* ── ② 오늘 — 순위표가 말하는 것(다른 창이다) ──────────────────── */}
        <HStack className="sr-stats" width="100%" flexWrap="wrap">
          <StatColumn title="오늘과 최근 — 만기물 전체">
            <Stat label="오늘" value={eok(sub.d1)} tone={tone(sub.d1)} note="억" />
            <Stat label="5일" value={eok(sub.d5)} tone={tone(sub.d5)} note="억" />
            <Stat label="20일" value={eok(sub.d20)} tone={tone(sub.d20)} note="억" />
            <Stat label="올해" value={sub.ytd == null ? '—' : `${fmtJo(sub.ytd)}조`}
              tone={tone(sub.ytd)} note="1월부터" />
          </StatColumn>
          <StatColumn title="평소와 견주면">
            {/* ★백분위다(σ 가 아니다) — CFTC COT 를 읽는 그 관례.
                꼬리 해상도를 잃는다는 사실을 `note` 가 적는다(`api.ts` 의 그 주석). */}
            <Stat label="분포 자리"
              value={sub.pct == null ? '—' : `${Math.round(sub.pct)}`}
              note="100이 가장 큰 순매수 · 꼬리는 못 가려요" />
            <Stat label="1년 일평균" value={`${eok(sub.avgAbs).replace('+', '')}억`}
              note={sub.ranked ? '순위 안' : '순위 밖 — 하한 아래예요'} />
          </StatColumn>
        </HStack>

        {/* ── ③ 들고 있는 양 — **거래가 아니다** ────────────────────────── */}
        <HStack className="sr-stats" width="100%" flexWrap="wrap">
          <StatColumn title="들고 있는 양 — 거래가 아니에요">
            {hold ? (
              <>
                <Stat label="보유" value={`${fmtJo(hold.face).replace('+', '')}조`}
                  note={hold.share == null ? '비중은 못 내요' : `전체의 ${(hold.share * 100).toFixed(1)}%`} />
                {/* ⚠**합쳐진 주체**는 그 사실을 적는다 — 잔고표의 짝이 1:1 이
                    아닌 자리가 있고(보험 ↔ 보험+기금공제), 안 적으면 흐름의
                    「보험」과 보유의 「보험」이 같은 것으로 읽힌다. */}
                {hold.merged && hold.merged.length > 1 ? (
                  <Stat label="짝" value={hold.merged.join(' + ')}
                    note="잔고표에서 합쳐진 주체예요" />
                ) : null}
              </>
            ) : (
              /* ★`null` 은 **0 이 아니다** — 잔고표에 그 주체가 없다는 뜻이다.
                 0 으로 적으면 「안 들고 있다」가 되어 거짓이 된다. */
              <Stat label="보유" value="—"
                note="잔고표에 이 주체의 짝이 없어요 — 0 이라는 뜻이 아니에요" />
            )}
          </StatColumn>
        </HStack>

        {/* ── ④ 직전 입찰 — 이 만기물의 공급이 어떻게 소화됐나 ──────────── */}
        {auction ? (
          <HStack className="sr-stats" width="100%" flexWrap="wrap">
            <StatColumn title={`직전 입찰 · ${auction.label} ${auction.date}`}>
              <Stat label="낙찰" value={`${fmtJo(auction.amount).replace('+', '')}조`} />
              <Stat label="응찰률"
                value={auction.ratio == null ? '—' : `${auction.ratio.toFixed(1)}%`}
                note={auction.grade ?? undefined} />
              <Stat label="낙찰금리"
                value={auction.rate == null ? '—' : `${auction.rate.toFixed(3)}%`} />
            </StatColumn>
          </HStack>
        ) : null}

        {/* 두 묶음이 **다른 창**이라는 것을 마지막에 한 번 더 적는다 — 위에서
            ①은 고른 구간, ②는 오늘이다. 이 면이 스스로를 반박하는 것처럼
            읽히는 자리가 거기였다(`FlowPage` 의 순위 창 부제와 같은 말). */}
        <Box>
          <Text as="p" font="legal" color="fgMuted">
            ①은 고른 구간의 합이고 ②는 오늘과 최근이에요 — 창이 다르니 같은 주체가
            두 수로 서는 게 맞아요. ②·③은 <b>만기물 전체</b>라 ①의 한 칸보다 넓어요.
          </Text>
        </Box>
      </VStack>
    </FloatingWindow>
  );
}
