'use client';

/* 모멘텀 **슬리브** — 「오늘 칠 것」 (Strategy 넷째 세입자, 2026-09-21).
 *
 * [OWNER 2026-09-21 — "모멘텀도 좀 고쳐두자.. 원래 우리 하던 방향있잖아"] MR 을
 * 계획면으로 바꾼 그 방향을 모멘텀에 옮긴 면이다. 다만 **모멘텀에서의 「지금 할
 * 일」은 진입 트리거가 아니다** — 이 북은 매일 크기가 바뀌는 연속 북이라 「진입」
 * 이라는 사건이 없고, 데스크가 실제로 치는 것은 **어제와의 차이**다.
 *
 * ## 옆의 `Momentum` 면과 다른 북이다
 *
 *     Momentum    2026-09-08 등록(선물·합성)의 거울 — **굴리지 않는다**
 *     이 면        2026-09-15 동결 · 09-16 채점 중인 IRS 50/50 — **실물**
 *
 * 같은 탭에 나란히 서지만 수를 섞으면 어느 등록의 성적인지 못 읽는다. 조건 바
 * 첫 칸이 어느 등록인지 적는다(이웃 면의 그 규율 그대로).
 *
 * ## 이 면이 «추천» 을 하지 않는 자리
 *
 * 액면은 화면의 판단이 아니라 **등록된 규칙이 낸 값**이다(다섯 북 DV01 → 실측
 * 커브 pv01 → 만기별 액면 → W4 배율). 화면은 그것을 옮겨 적고, 그 수가 어떤
 * 가정 위에 서 있는지를 같이 적는다 — 특히 **평균회귀를 안 줄이면 오늘 슬리브는
 * 못 선다**는 사실(인계문 §5-1)은 숫자 옆에 서야 한다.
 *
 * 숫자는 전부 서버가 끝낸다(§16, `backend/app/sleeve.py`). 이 파일은 배치뿐이다.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@coinbase/cds-web/tables';
import { Text } from '@coinbase/cds-web/typography';

import { BacktestUnavailable } from '@/lib/api';
import { fmtSize } from '@/lib/krw';
import { ROW_H } from '@/table/rowHeight';
import { directionClass } from '@/table/tint';
import { Cond } from '@/ui/Cond';
import { ErrorState, LoadingState } from '@/ui/DataState';
import { Stat, StatColumn } from '@/ui/Stat';
import { ThHelp } from '@/ui/ThHelp';

import { fetchSleeve, type SleeveLeg, type SleeveSheet } from './api';

/** 억 단위 한 수 — 이 면의 모든 액면·증거금이 억이다(`lib/krw::fmtSize`). */
const uk = (v: number | undefined): string =>
  v == null ? '—' : `${fmtSize(v / 1e8)}억`;

/** 주문 한 줄 — **방향 낱말이 부호를 진다**.
 *
 *  계열이 −bp 라 DV01 이 양(+)이면 리시브이고, 서버가 `side` 로 그 판정을 끝낸다.
 *  「주문」은 목표가 아니라 어제와의 차이라 여기서도 **차이의 부호**로 읽는다:
 *  음수면 더 페이하고 양수면 더 리시브한다. 1억 미만은 «—» 다. */
function orderWord(l: SleeveLeg): string {
  if (!l.trade) return '—';
  return `${l.delta < 0 ? '페이' : '리시브'} ${uk(Math.abs(l.delta))}`;
}

export function SleevePage() {
  const [sheet, setSheet] = useState<SleeveSheet>();
  const [error, setError] = useState<string>();
  const [unavailable, setUnavailable] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  /* 늦게 온 옛 응답이 이기지 못하게 순번으로 버린다(폴링이 겹치는 자리). */
  const seq = useRef(0);
  const load = useCallback(() => {
    const my = ++seq.current;
    setError(undefined);
    setUnavailable(false);
    setRefreshing(true);
    fetchSleeve()
      .then((s) => {
        if (seq.current === my) setSheet(s);
      })
      .catch((e: unknown) => {
        if (seq.current !== my) return;
        if (e instanceof BacktestUnavailable) setUnavailable(true);
        else setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (seq.current === my) setRefreshing(false);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /* 굽는 동안 다시 묻는다 — 44초짜리라 첫 응답은 `building` 이다. 다 구워지면
     **멈춘다**(끝난 뒤에도 도는 폴링은 서버를 계속 깨운다). */
  useEffect(() => {
    if (!sheet || !sheet.building) return;
    const t = setTimeout(() => load(), 4000);
    return () => clearTimeout(t);
  }, [sheet, load]);

  if (unavailable) {
    return (
      <ErrorState
        what="모멘텀 슬리브"
        detail="실행 중인 백엔드(:8200)가 필요하고, 슬리브 라우트(/api/momentum/sleeve)를 아는 판이어야 해요 — 백엔드를 먼저 올려 주세요."
        onRetry={load}
        retrying={refreshing}
      />
    );
  }
  if (error) {
    return <ErrorState what="모멘텀 슬리브" detail={error} onRetry={load} retrying={refreshing} />;
  }
  if (!sheet) {
    return <LoadingState what="모멘텀 슬리브" />;
  }

  const legs = sheet.legs ?? [];
  /* 「안 줄이면 못 선다」 — 이 화면에서 가장 중요한 사실이라 숫자 옆이 아니라
     조건 바 밑 한 줄로 선다(인계문 §5-1). */
  const cannotStand = (sheet.scaleNoShrink ?? 1) <= 0;

  return (
    <VStack gap={1.5} width="100%" flexGrow={1} minHeight={0}>
      {/* ── 조건 바 — **어느 등록인지**가 숫자보다 먼저 읽힌다 ──────────────── */}
      <VStack className="sr-rv-bar" flexShrink={0} gap={0.5} width="100%">
        <HStack gap={1.5} alignItems="center" flexWrap="wrap">
          <Cond k="등록" v="IRS 50/50 슬리브 · 2026-09-15 동결" />
          <Cond k="기준일" v={sheet.asof ?? '—'} strong />
          <Cond k="상태" v={sheet.scored ? '채점 창' : '연습'} />
          <Cond k="증거금 상한" v="100억" />
          {sheet.building ? (
            <Text font="legal" as="span" color="fgMuted" noWrap>
              표를 굽는 중이에요…
            </Text>
          ) : refreshing ? (
            <Text font="legal" as="span" color="fgMuted" noWrap>
              갱신 중…
            </Text>
          ) : null}
          <Box style={{ marginInlineStart: 'auto' }}>
            {/* 명구 의무 — 이웃 셋과 같은 문법. 이 면은 집행면이라 문장이 다르다:
                크기를 «권하는» 것이 아니라 등록된 규칙이 낸 값을 옮겨 적는다. */}
            <Text font="legal" as="span" color="fgMuted" noWrap>
              등록된 규칙이 낸 값이에요 — 새 판단이 아니에요.
            </Text>
          </Box>
        </HStack>
        <Text font="legal" as="span" color="fgMuted">
          옆의 Momentum 면과 <b>다른 북</b>이에요 — 저쪽은 2026-09-08 등록(선물·합성)을
          비추는 거울이고, 이 면은 09-15 동결·09-16 채점 중인 IRS 50/50 이에요.
          「주문」은 목표가 아니라 <b>어제와의 차이</b>예요(매일 크기가 바뀌는 연속
          북이라 진입이라는 사건이 없어요).
        </Text>
        {cannotStand ? (
          /* ★이 줄이 이 화면에서 제일 중요하다 — 위의 배율·액면이 전부 「평균회귀를
             k_mr 로 줄여 세운다」는 가정 위에 있고, 그 축소를 그 레인에 지시한 적이
             없다. 숫자 옆이 아니라 여기 서야 읽는 사람이 먼저 본다. */
          <Text font="body" as="span" className="sr-up">
            평균회귀를 실제로 안 줄이면 여력이 {uk(sheet.headroomNoShrink)}이라 오늘
            슬리브는 못 서요 — 아래 액면은 k_mr {sheet.kMr?.toFixed(3)} 축소를{' '}
            <b>가정</b>한 수예요.
          </Text>
        ) : null}
        {!sheet.available && sheet.why ? (
          <Text font="body" as="span" color="fgMuted">
            {sheet.why}
          </Text>
        ) : null}
      </VStack>

      {!sheet.available ? (
        <LoadingState what="슬리브 주문표" />
      ) : (
        <>
          {/* ── 히어로 — 오늘 칠 것 한 줄 ──────────────────────────────────── */}
          <VStack flexShrink={0} gap={0} width="100%">
            <Text font="label1" as="span" color="fgMuted" noWrap>
              오늘 칠 것이에요
            </Text>
            <HStack gap={1.5} alignItems="baseline" flexWrap="wrap">
              <Text font="display3" as="span" tabularNumbers noWrap>
                {legs.some((l) => l.trade) ? `회전 ${uk(sheet.turnover)}` : '칠 것 없어요'}
              </Text>
              <Text font="body" as="span" color="fgMuted">
                {legs
                  .filter((l) => l.trade)
                  .map((l) => `${l.tenor} ${orderWord(l)}`)
                  .join(' · ') || `1억 미만 차이라 안 쳐요`}
              </Text>
            </HStack>
            <Text font="legal" as="span" color="fgMuted">
              세울 북 {uk(sheet.faceAfter)} · 증거금 {uk(sheet.marginNeed)} · 배율{' '}
              {sheet.scale?.toFixed(3)}
            </Text>
          </VStack>

          {/* ── 2열: 주문표가 주인공, 사실이 나머지 ─────────────────────────── */}
          <HStack gap={2} alignItems="stretch" width="100%" flexGrow={1} minHeight={0}>
            <VStack className="sr-card" flexBasis={760} flexGrow={0} flexShrink={1}
              maxWidth={760} minHeight={0}>
              <HStack alignItems="center" justifyContent="space-between" gap={1}
                paddingX={2} paddingTop={1.5} paddingBottom={0.5}>
                <Text font="label1" as="h2" noWrap>
                  주문표
                </Text>
              </HStack>
              <VStack gap={0} width="100%" minHeight={0} flexGrow={1}>
                <div className="sr-rv-rank-fill">
                  <div className="sr-rv-rank-scroll">
                    <Table bordered={false}>
                      <TableHeader sticky>
                        <TableRow>
                          <TableCell as="th" scope="col">
                            <Text font="caption" as="span" color="fgMuted">만기</Text>
                          </TableCell>
                          <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                            <ThHelp
                              label="순 DV01"
                              help="다섯 북(추세 하나·거시 넷)을 더한 값이에요. 계열이 −bp 라 양수면 리시브예요."
                            />
                          </TableCell>
                          <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                            <ThHelp
                              label="목표 액면"
                              help="순 DV01 을 그날 실측 커브의 pv01 로 나눈 액면이에요. 근사 pv01 은 3Y 3.8%·10Y 12.5% 과대평가였어요."
                            />
                          </TableCell>
                          <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                            <Text font="caption" as="span" color="fgMuted">축소 후</Text>
                          </TableCell>
                          <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                            <Text font="caption" as="span" color="fgMuted">어제</Text>
                          </TableCell>
                          <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                            <ThHelp
                              label="주문"
                              help="목표가 아니라 어제와의 차이예요. 1억 미만은 호가 단위와 수수료를 못 이겨서 안 쳐요."
                            />
                          </TableCell>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {legs.map((l) => (
                          <TableRow key={l.tenor} style={{ height: ROW_H }}>
                            <TableCell>
                              <VStack as="span" className="sr-name-stack">
                                <Text font="label1" as="span" noWrap>{l.tenor}</Text>
                                <Text font="legal" as="span" color="fgMuted" noWrap>
                                  {l.side > 0 ? '리시브' : l.side < 0 ? '페이' : '없음'}
                                </Text>
                              </VStack>
                            </TableCell>
                            <TableCell className="sr-num" justifyContent="flex-end">
                              <Text font="label2" as="span" tabularNumbers noWrap>
                                {`${fmtSize(l.dv01 / 1e4)}만`}
                              </Text>
                            </TableCell>
                            <TableCell className="sr-num" justifyContent="flex-end">
                              <Text font="label2" as="span" tabularNumbers noWrap>{uk(l.face)}</Text>
                            </TableCell>
                            <TableCell className="sr-num" justifyContent="flex-end">
                              <Text font="label2" as="span" tabularNumbers noWrap>{uk(l.faceAfter)}</Text>
                            </TableCell>
                            <TableCell className="sr-num" justifyContent="flex-end">
                              {/* 크기는 무부호가 캐논이고(`fmtSize`) 방향은 **낱말**이
                                  진다 — 어제의 방향이 오늘과 다를 수 있는 칸이라
                                  숫자만 적으면 읽는 사람이 오늘 방향으로 읽는다. */}
                              <Text font="label2" as="span" tabularNumbers noWrap color="fgMuted">
                                {l.prevSigned === 0
                                  ? '없음'
                                  : `${l.prevSigned < 0 ? '페이' : '리시브'} ${uk(Math.abs(l.prevSigned))}`}
                              </Text>
                            </TableCell>
                            <TableCell className="sr-num" justifyContent="flex-end">
                              {/* 색은 캐논 한 곳이 정한다(`table/tint.ts`) — 안 치는
                                  줄은 색도 없다(0 에서 뮤트가 그 일을 한다). */}
                              <Text
                                font="label2"
                                as="span"
                                tabularNumbers
                                noWrap
                                className={l.trade ? directionClass(l.delta) : undefined}
                              >
                                {orderWord(l)}
                              </Text>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              </VStack>
            </VStack>

            {/* ── 사실 — 배율·여력·채점 상태 ─────────────────────────────── */}
            <VStack className="sr-card" flexBasis={0} flexGrow={1} flexShrink={1}
              minWidth={420} minHeight={0}>
              <HStack alignItems="center" justifyContent="space-between" gap={1}
                paddingX={2} paddingTop={1.5} paddingBottom={0.5}>
                <Text font="label1" as="h2" noWrap>
                  오늘 이 수가 선 자리
                </Text>
              </HStack>
              <VStack gap={1.5} paddingX={2} paddingBottom={2} width="100%" flexGrow={1} minHeight={0}>
                <HStack className="sr-stats" width="100%" flexWrap="wrap">
                  <StatColumn title="배율">
                    <Stat
                      label="W4 배율"
                      value={sheet.scale?.toFixed(3) ?? '—'}
                      note={(sheet.scale ?? 1) >= 0.999 ? '안 줄였어요' : '여력이 모자라 줄였어요'}
                    />
                    <Stat
                      label="평균회귀 증거금"
                      value={uk(sheet.mrMargin)}
                      note={sheet.marginSource?.rule
                        ? `${sheet.marginSource.rule} · ${sheet.marginSource.asof}`
                        : undefined}
                    />
                    <Stat
                      label="여력"
                      value={uk(sheet.headroom)}
                      note={`축소 안 하면 ${uk(sheet.headroomNoShrink)}`}
                      tone={cannotStand ? 'down' : undefined}
                    />
                    <Stat
                      label="상한 넘은 날"
                      value={`${sheet.histHitDays ?? 0}일`}
                      note={`전체 ${sheet.histDays ?? 0}일 중`}
                    />
                  </StatColumn>

                  <StatColumn title="채점">
                    <Stat label="동결" value={sheet.freeze ?? '—'} note="채점은 다음 영업일부터" />
                    <Stat
                      label="이 표"
                      value={sheet.scored ? '채점 창' : '연습'}
                      note={sheet.asof ?? undefined}
                    />
                    <Stat
                      label="원장"
                      value={`${sheet.ledger?.rows ?? 0}일치`}
                      note={sheet.ledger?.last ? `마지막 ${sheet.ledger.last}` : '비어 있어요'}
                    />
                    {/* ★채점 창이 열렸는데 원장에 채점 행이 없다 — 「슬리브를 실제로
                        켤 것인가」가 아직 열린 결정이라 이전 세션이 안 적었다.
                        결함이 아니라 **대기**이고, 화면이 그렇게 말해야 한다. */}
                    {sheet.scored && (sheet.ledger?.scoredRows ?? 0) === 0 ? (
                      <Stat
                        label="채점 행"
                        value="없어요"
                        note="슬리브를 켤지 정한 뒤에 적어요"
                      />
                    ) : null}
                  </StatColumn>

                  <StatColumn title="크기">
                    <Stat label="배수" value={sheet.mult?.toFixed(2) ?? '—'} note="총위험 고정" />
                    <Stat label="목표 합" value={uk(sheet.faceTotal)} />
                    <Stat label="축소 후" value={uk(sheet.faceAfter)} note={`증거금 ${uk(sheet.marginNeed)}`} />
                  </StatColumn>
                </HStack>

                {/* 여력의 기준일이 주문표와 다를 수 있다 — 평균회귀가 그 사이에
                    다리를 더 넣었으면 여력은 이보다 적다. 조용히 넘기지 않는다. */}
                {sheet.marginSource?.asof && sheet.marginSource.asof !== sheet.asof ? (
                  <Text font="legal" as="span" color="fgMuted">
                    여력은 {sheet.marginSource.asof} 것이고 이 주문표는 {sheet.asof} 것이에요 —
                    평균회귀가 그 사이에 다리를 더 넣었으면 여력은 이보다 적어요.
                  </Text>
                ) : null}
                {sheet.marginSource?.stale?.length ? (
                  <Text font="legal" as="span" color="fgMuted">
                    평균회귀 적재가 {sheet.marginSource.stale.length}다리 지연됐어요(증거금
                    묶은 것 {sheet.marginSource.stale_held ?? 0}).
                  </Text>
                ) : null}
              </VStack>
            </VStack>
          </HStack>
        </>
      )}
    </VStack>
  );
}
