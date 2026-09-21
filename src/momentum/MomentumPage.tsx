'use client';

/* Momentum — 등록된 **IRS 50/50** 의 오늘 (Strategy 셋째 세입자).
 *
 * [OWNER 2026-09-21 — "원래있던 KTB 모멘텀을 대체하는거니까 거기서 제공하던
 * 정보들도 IRS 모멘텀 슬리브에 들어가야해. 슬리브라는 표현보다는 그냥
 * Strategy/Momentum 이 더 잘 맞겠다"]
 *
 * ## 이 자리의 주인이 바뀌었다
 *
 * 09-09~09-21 의 `Momentum` 면은 **선물 KTB** 등록(2026-09-08 · 합성)의 거울이었고
 * 굴리지 않는 북이었다. 지금 이 면은 **2026-09-15 동결 · 09-16 채점 중인 IRS
 * 50/50** 이다 — 데스크가 실제로 세울 북이 이쪽이다. KTB 면이 주던 두 표(테너 ×
 * 룩백 신호 격자 · 테마 넷)도 여기로 들어왔고, **IRS 계열 위에서** 선다.
 *
 * ## 「지금 할 일」이 진입 트리거가 아닌 이유
 *
 * 이 북은 매일 크기가 바뀌는 **연속 북**이라 「진입」이라는 사건이 없다. 데스크가
 * 실제로 치는 것은 **어제와의 차이**이고, 1억 미만은 호가 단위와 수수료를 못
 * 이겨 안 친다.
 *
 * ## MR 과 **별개로도** 선다 [OWNER 2026-09-21]
 *
 * 배율(W4)은 평균회귀가 증거금을 얼마나 쓰는가에 달렸고 그 경로는 리포 밖
 * 배분기를 읽는다. 그것이 없는 날에도 이 북 자신의 수는 멀쩡하므로, 화면은
 * **독립 판**(배율 1.0)을 늘 세우고 연동 판을 그 옆에 얹는다.
 *
 * ## 이 면이 «추천» 을 하지 않는 자리
 *
 * 액면은 화면의 판단이 아니라 **등록된 규칙이 낸 값**이다(다섯 북 DV01 → 실측
 * 커브 pv01 → 만기별 액면 → W4 배율). 화면은 그것을 옮겨 적고, 그 수가 어떤
 * 가정 위에 서 있는지를 같이 적는다 — 특히 **평균회귀를 안 줄이면 오늘 이 북은
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
import { directionClass, directionGlyph, signalTint, unsignedDelta } from '@/table/tint';
import { Cond } from '@/ui/Cond';
import { ErrorState, LoadingState } from '@/ui/DataState';
import { Stat, StatColumn } from '@/ui/Stat';
import { ThHelp } from '@/ui/ThHelp';

import { fetchSleeve, type SleeveLeg, type SleevePerf, type SleeveSheet, type SleeveSignals } from './api';

/** 억 단위 한 수 — 이 면의 모든 액면·증거금이 억이다(`lib/krw::fmtSize`).
 *
 *  `null` 을 받는 이유는 **연동이 안 선 날**이다(배분기를 못 읽으면 여력·배율이
 *  없다). 없는 것을 0 으로 적으면 「여력이 0 이다」라는 딴 사실이 된다. */
const uk = (v: number | null | undefined): string =>
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

/** 신호 강도 한 칸 — **KTB 보드의 네 부품 한 벌**(`table/tint.ts`)을 그대로 쓴다.
 *
 *  칠하는 값은 신호가 아니라 **금리** 방향이다(`rate`). 틴트만 눈금이 다르다 —
 *  이 칸의 값은 bp 도 백분위도 아닌 «강도»(0~1)라 `signalTint` 가 그 램프다. */
function SignalCellView({ rate }: { rate: number }) {
  return (
    <TableCell className="sr-num" justifyContent="flex-end" style={signalTint(rate)}>
      <Text font="label2" as="span" tabularNumbers noWrap className={directionClass(rate)}>
        {directionGlyph(rate)}
        {directionGlyph(rate) ? ' ' : ''}
        {unsignedDelta(Math.abs(rate).toFixed(2))}
      </Text>
    </TableCell>
  );
}

/** 오늘의 신호 — **테너 × 룩백 격자**와 **테마 넷**.
 *
 *  KTB 면이 주던 두 표이고 [OWNER 2026-09-21 — "거기서 제공하던 정보들도 들어가야
 *  해"], 이제 IRS 계열 위에서 선다. 룩백은 **손잡이가 아니라 열**이다 — 「룩백을
 *  고르지 마라」가 이 레인의 규율이라(전진 선택하면 7년 합 −3,230만) 셀렉트로 두면
 *  화면이 규율을 어기는 도구가 된다. 다섯을 전부 열로 세우고 왼쪽 빠름 → 오른쪽
 *  느림으로 고정한다. */
function SignalPanel({ sig }: { sig: SleeveSignals }) {
  if (!sig.available) {
    return (
      <Text font="legal" as="span" color="fgMuted">
        {sig.why ?? '신호를 못 세웠어요.'}
      </Text>
    );
  }
  const lookbacks = sig.lookbacks ?? [];
  return (
    <VStack gap={1.5} width="100%">
      <VStack gap={0.5} width="100%">
        <HStack gap={1} alignItems="baseline" justifyContent="space-between">
          <Text font="label2" as="h3" noWrap>추세 다리</Text>
          <Text font="legal" as="span" color="fgMuted" noWrap>
            테너 {sig.rows?.length ?? 0} · 룩백 {lookbacks.length} · {sig.signal}
          </Text>
        </HStack>
        <Table bordered={false}>
          <TableHeader>
            <TableRow>
              <TableCell as="th" scope="col">
                <Text font="caption" as="span" color="fgMuted">테너</Text>
              </TableCell>
              {lookbacks.map((lb) => (
                <TableCell key={lb} as="th" scope="col" className="sr-num" justifyContent="flex-end">
                  <Text font="caption" as="span" color="fgMuted">{lb}일</Text>
                </TableCell>
              ))}
              <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                <ThHelp
                  label="합성"
                  help="다섯 룩백의 등가중 평균이에요. 계열이 −bp 라 값이 양수면 금리가 내리는 쪽, 즉 리시브예요."
                />
              </TableCell>
              <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                <ThHelp
                  label="속도합의"
                  help="다섯 룩백 중 합성과 같은 방향인 것의 수예요. 갈리면 «모른다»에 가까워요."
                />
              </TableCell>
              <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                <Text font="caption" as="span" color="fgMuted">유지</Text>
              </TableCell>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(sig.rows ?? []).map((r) => (
              <TableRow key={r.tenor} style={{ height: ROW_H }}>
                <TableCell>
                  <VStack as="span" className="sr-name-stack">
                    <Text font="label1" as="span" noWrap>{r.tenor}</Text>
                    <Text font="legal" as="span" color="fgMuted" noWrap>
                      {r.rate.toFixed(1)}bp
                    </Text>
                  </VStack>
                </TableCell>
                {r.cells.map((c) => (
                  <SignalCellView key={c.lookback} rate={c.rate} />
                ))}
                <SignalCellView rate={r.compositeRate} />
                <TableCell className="sr-num" justifyContent="flex-end">
                  <Text font="label2" as="span" tabularNumbers noWrap>
                    {r.agree}/{r.of}
                  </Text>
                </TableCell>
                <TableCell className="sr-num" justifyContent="flex-end">
                  <Text font="label2" as="span" tabularNumbers noWrap color="fgMuted">
                    {r.holdDays}일
                  </Text>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </VStack>

      <VStack gap={0.5} width="100%">
        <HStack gap={1} alignItems="baseline" justifyContent="space-between">
          <Text font="label2" as="h3" noWrap>매크로 다리</Text>
          <Text font="legal" as="span" color="fgMuted" noWrap>
            테마 {sig.themes?.length ?? 0} · 부호 북 등가중
          </Text>
        </HStack>
        <HStack className="sr-stats" width="100%" flexWrap="wrap">
          <StatColumn title="테마">
            {(sig.themes ?? []).map((t) => (
              <Stat
                key={t.theme}
                label={THEME_WORD[t.theme] ?? t.theme}
                /* 테마는 **부호**다(±1) — 강도가 아니라 방향이라 낱말로 적는다. */
                value={t.sign > 0 ? '리시브' : t.sign < 0 ? '페이' : '없음'}
                tone={t.sign > 0 ? 'down' : t.sign < 0 ? 'up' : undefined}
                note={`${t.holdDays}일째`}
              />
            ))}
            <Stat
              label="합성"
              value={`${((sig.macroSign ?? 0) * 100).toFixed(0)}%`}
              note="네 부호의 평균"
            />
          </StatColumn>
        </HStack>
      </VStack>
    </VStack>
  );
}

/** 다리의 우리말 — 서버의 열쇠를 화면에서 **한 번만** 옮긴다. */
const LEG_WORD: Record<string, string> = { trend: '추세', macro: '거시', blend: '50/50' };

/** **표본내 성적** — 다리 셋. 원화 열은 위험 맞춤 짝과 무차원 비율을 같이 세운다.
 *
 *  절단은 **서버가** 한다(`build_perf`) — 화면은 준 것만 그린다. 창이 언제까지인지
 *  머리에 적는 이유는, 그 한 주가 50/50 SR 을 1.000 에서 1.168 로 옮기기 때문이다. */
function PerfPanel({ perf }: { perf: SleevePerf }) {
  if (!perf.available) {
    return (
      <Text font="legal" as="span" color="fgMuted">
        {perf.why ?? '성적을 못 세웠어요.'}
      </Text>
    );
  }
  return (
    <VStack gap={0.5} width="100%">
      <HStack gap={1} alignItems="baseline" justifyContent="space-between">
        <Text font="label2" as="h3" noWrap>표본내 성적</Text>
        <Text font="legal" as="span" color="fgMuted" noWrap>
          {perf.window?.start} ~ {perf.window?.end} · 등록 판정문의 창이에요
        </Text>
      </HStack>
      <Table bordered={false}>
        <TableHeader>
          <TableRow>
            <TableCell as="th" scope="col">
              <Text font="caption" as="span" color="fgMuted">다리</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="caption" as="span" color="fgMuted">연손익</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="caption" as="span" color="fgMuted">연변동</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="caption" as="span" color="fgMuted">최대낙폭</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <ThHelp
                label="위험맞춤 낙폭"
                help="다리마다 실제로 건 위험이 달라요. 추세 다리의 변동성에 맞춘 뒤의 낙폭이에요 — Sharpe·Martin 은 비율이라 안 변하지만 낙폭은 변해요."
              />
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <ThHelp
                label="Ulcer"
                help="낙폭이 얼마나 깊고 오래갔나를 한 수로 압축한 값이에요. 원화라 다리끼리 그대로 비교하면 안 되고, 옆의 위험맞춤 값이나 무차원인 Martin 을 보세요."
              />
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <ThHelp
                label="위험맞춤 Ulcer"
                help="추세 다리의 변동성에 맞춘 뒤의 Ulcer 예요. 원화 열은 짝이 있어야 읽혀요 — 맞추지 않으면 덜 걸어서 덜 아팠던 다리가 이겨요."
              />
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <ThHelp
                label="Martin"
                help="연손익 ÷ Ulcer 예요. 무차원이라 자본 기준이 없어도 다른 전략과 나란히 놓을 수 있어요."
              />
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <ThHelp label="Sharpe" help="연환산 평균 ÷ 연환산 표준편차예요. 등록 판정문의 그 수예요." />
            </TableCell>
          </TableRow>
        </TableHeader>
        <TableBody>
          {(perf.rows ?? []).map((r) => (
            <TableRow key={r.leg} style={{ height: ROW_H }}>
              <TableCell>
                <VStack as="span" className="sr-name-stack">
                  <Text font="label1" as="span" noWrap>{LEG_WORD[r.leg] ?? r.leg}</Text>
                  <Text font="legal" as="span" color="fgMuted" noWrap>{r.days}일</Text>
                </VStack>
              </TableCell>
              <TableCell className="sr-num" justifyContent="flex-end">
                <Text font="label2" as="span" tabularNumbers noWrap className={directionClass(r.annPnl)}>
                  {`${fmtSize(r.annPnl / 1e4)}만`}
                </Text>
              </TableCell>
              <TableCell className="sr-num" justifyContent="flex-end">
                <Text font="label2" as="span" tabularNumbers noWrap color="fgMuted">
                  {`${fmtSize(r.annVol / 1e4)}만`}
                </Text>
              </TableCell>
              <TableCell className="sr-num" justifyContent="flex-end">
                <Text font="label2" as="span" tabularNumbers noWrap>
                  {`${fmtSize(r.maxDrawdown / 1e4)}만`}
                </Text>
              </TableCell>
              <TableCell className="sr-num" justifyContent="flex-end">
                <Text font="label2" as="span" tabularNumbers noWrap>
                  {`${fmtSize(r.maxDrawdownVolMatched / 1e4)}만`}
                </Text>
              </TableCell>
              {/* 원화라 다리끼리 그대로 못 비교한다 — 낙폭이 그랬듯 Ulcer 도
                  **짝을 옆에 세운다**(마우스를 올려야 보이는 값은 없는 값이다).
                  부호는 안 뒤집는다 — 낙폭의 «크기» 라 원래 양수다. */}
              <TableCell className="sr-num" justifyContent="flex-end">
                <Text font="label2" as="span" tabularNumbers noWrap>
                  {`${fmtSize(r.ulcer / 1e4)}만`}
                </Text>
              </TableCell>
              <TableCell className="sr-num" justifyContent="flex-end">
                <Text font="label2" as="span" tabularNumbers noWrap>
                  {`${fmtSize(r.ulcerVolMatched / 1e4)}만`}
                </Text>
              </TableCell>
              <TableCell className="sr-num" justifyContent="flex-end">
                <Text font="label2" as="span" tabularNumbers noWrap>
                  {r.martin == null ? '—' : r.martin.toFixed(2)}
                </Text>
              </TableCell>
              <TableCell className="sr-num" justifyContent="flex-end">
                <Text font="label2" as="span" tabularNumbers noWrap>
                  {r.sharpe == null ? '—' : r.sharpe.toFixed(2)}
                </Text>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </VStack>
  );
}

/** 테마의 우리말 — 서버의 열쇠를 화면에서 **한 번만** 옮긴다. */
const THEME_WORD: Record<string, string> = {
  cycle: '경기순환',
  policy: '통화정책',
  trade: '국제교역',
  risk: '위험선호',
};

export function MomentumPage() {
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
        what="모멘텀 북"
        detail="실행 중인 백엔드(:8200)가 필요하고, /api/momentum/sleeve 를 아는 판이어야 해요 — 백엔드를 먼저 올려 주세요."
        onRetry={load}
        retrying={refreshing}
      />
    );
  }
  if (error) {
    return <ErrorState what="모멘텀 북" detail={error} onRetry={load} retrying={refreshing} />;
  }
  if (!sheet) {
    return <LoadingState what="모멘텀 북" />;
  }

  const legs = sheet.legs ?? [];
  /* 「안 줄이면 못 선다」 — 이 화면에서 가장 중요한 사실이라 숫자 옆이 아니라
     조건 바 밑 한 줄로 선다(인계문 §5-1). */
  const cannotStand = sheet.linked === true && (sheet.scaleNoShrink ?? 1) <= 0;

  return (
    <VStack gap={1.5} width="100%" flexGrow={1} minHeight={0}>
      {/* ── 조건 바 — **어느 등록인지**가 숫자보다 먼저 읽힌다 ──────────────── */}
      <VStack className="sr-rv-bar" flexShrink={0} gap={0.5} width="100%">
        <HStack gap={1.5} alignItems="center" flexWrap="wrap">
          {/* 이름·동결일은 **서버가 낸다**(`sheet.registry`) — 여기서 다시 적으면
              등록서가 바뀐 날 화면만 옛 날짜를 말한다. */}
          <Cond
            k="등록"
            v={sheet.registry
              ? `${sheet.registry.book} · ${sheet.registry.freeze} 동결`
              : '—'}
          />
          <Cond k="계기" v={sheet.registry?.instrument ?? '—'} />
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
        {/* 산문은 **재는 폭**이 따로 있다 — 1,920px 한 줄은 눈이 다음 줄 머리를
            못 찾는다. 이 면의 주문표 카드와 같은 760 을 쓴다(같은 수를 두 번
            정하지 않는다). 낱말은 하나도 안 줄인다 — 접을 뿐이다. */}
        <Text font="legal" as="span" color="fgMuted" maxWidth={760}>
          {sheet.registry?.note.replace(/\*\*/g, '') ?? ''} 「주문」은 목표가 아니라{' '}
          <b>어제와의 차이</b>예요 — 매일 크기가 바뀌는 연속 북이라 진입이라는 사건이
          없고, 데스크가 실제로 치는 것은 그 차이예요. <b>단독 전략이 아니에요</b>:
          크기는 등록된 규칙이 내고 이 화면은 옮겨 적어요.
        </Text>
        {cannotStand ? (
          /* ★이 줄이 이 화면에서 제일 중요하다 — 위의 배율·액면이 전부 「평균회귀를
             k_mr 로 줄여 세운다」는 가정 위에 있고, 그 축소를 그 레인에 지시한 적이
             없다. 숫자 옆이 아니라 여기 서야 읽는 사람이 먼저 본다. */
          <Text font="body" as="span" className="sr-up" maxWidth={760}>
            평균회귀를 실제로 안 줄이면 여력이 {uk(sheet.headroomNoShrink)}이라 오늘
            이 북은 못 서요 — 아래 액면은 k_mr {sheet.kMr?.toFixed(3)} 축소를{' '}
            <b>가정</b>한 수예요.
          </Text>
        ) : null}
        {sheet.available && sheet.linked === false ? (
          /* MR 배분기를 못 읽은 날 — **이 북 자신의 수는 멀쩡하다**. 그 둘을
             가르지 않으면 화면이 「모멘텀이 안 선다」로 읽힌다. */
          <Text font="body" as="span" color="fgMuted" maxWidth={760}>
            {sheet.linkedWhy} — 아래는 <b>이 북 혼자</b>의 수예요(배율 1.000).
          </Text>
        ) : null}
        {!sheet.available && sheet.why ? (
          <Text font="body" as="span" color="fgMuted">
            {sheet.why}
          </Text>
        ) : null}
      </VStack>

      {!sheet.available ? (
        <LoadingState what="모멘텀 주문표" />
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

          {/* ── 여기부터 **구르는 칸** ────────────────────────────────────────
              바닥 띠(`ui/BottomStrip`)는 `fixed` 가 아니라 기둥의 마지막 칸이라,
              내용이 기둥보다 길면 띠 «밑으로 깔리는» 것이 아니라 띠를 밀어낸다 —
              실측(1,920×855)에서 주문표 칸이 **높이 0 으로 접혀** 오늘 칠 것이
               통째로 안 보였다. 아래 셋은 저마다 제 높이를 쓰고, 넘치면 이 칸이
              구른다. 조건 바와 히어로는 위에 남는다(그 둘이 「지금 뭘 보나」다). */}
          <VStack
            gap={1.5}
            width="100%"
            flexGrow={1}
            minHeight={0}
            style={{ overflowY: 'auto' }}
          >
          {/* ── 2열: 주문표가 주인공, 사실이 나머지 ─────────────────────────── */}
          <HStack gap={2} alignItems="stretch" width="100%" flexShrink={0} minHeight={360}>
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
                  {/* ★**독립 판이 먼저다** [OWNER 2026-09-21 「MR 이랑 별개도
                      돌아가게」] — 이 북 혼자의 답이 이 화면의 바닥이고, 배율은
                      그 위에 얹히는 제약이다. 순서가 그 위계를 말한다. */}
                  <StatColumn title="이 북 혼자">
                    <Stat
                      label="세울 북"
                      value={uk(sheet.standalone?.faceTotal)}
                      note="배율 안 먹인 값"
                    />
                    <Stat label="증거금" value={uk(sheet.standalone?.marginNeed)} />
                    <Stat
                      label="회전"
                      value={uk(sheet.standalone?.turnover)}
                      note="어제와의 차이"
                    />
                  </StatColumn>

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
                    {/* ★채점 창이 열렸는데 원장에 채점 행이 없다 — 「이 북을 실제로
                        켤 것인가」가 아직 열린 결정이라 이전 세션이 안 적었다.
                        결함이 아니라 **대기**이고, 화면이 그렇게 말해야 한다. */}
                    {sheet.scored && (sheet.ledger?.scoredRows ?? 0) === 0 ? (
                      <Stat
                        label="채점 행"
                        value="없어요"
                        note="이 북을 켤지 정한 뒤에 적어요"
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

          {/* ── 오늘의 신호 — **카드 밖 · 페이지 폭** ──────────────────────────
              KTB 면이 주던 두 표다 [OWNER 2026-09-21]. 카드 안에 넣으면 룩백 다섯
              열이 접혀 격자가 격자로 안 읽힌다 — 이 표는 **줄의 모양**이 답이라
              (빠른 쪽과 느린 쪽이 갈렸는가) 폭을 줘야 일을 한다. MR 계획면에서
              스트립을 페이지 폭으로 내린 것과 같은 판단. */}
          {sheet.signals ? (
            <Box flexShrink={0} width="100%">
              <SignalPanel sig={sheet.signals} />
            </Box>
          ) : null}
          {sheet.perf ? (
            <Box flexShrink={0} width="100%">
              <PerfPanel perf={sheet.perf} />
            </Box>
          ) : null}
          </VStack>
        </>
      )}
    </VStack>
  );
}
