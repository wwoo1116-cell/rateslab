'use client';

/* Momentum — 추세 다리와 매크로 다리를 **나란히** (Strategy 셋째 세입자, 2026-09-09).
 *
 * **방향과 강도를 재는 화면이지 단독 전략이 아니다.** 선물 추세 단독은 자본비용
 * 전액 규약에서 MMF 초과 −1.07 ~ +0.97%/년이었다(`research\ktb-tsmom`). 그래서
 * 크기·진입·손절을 말하지 않는다 — Credit RV 의 「랭킹이지 투자판단이 아니다」,
 * MR 의 「측정이지 신호가 아니다」와 같은 명구 의무.
 *
 * ## 구조는 «등록된 북» 그대로다 [OWNER 2026-09-09 — 「두 다리 나란히」]
 *
 *     추세 다리   계약 2 × 룩백 5 · 신호는 **macross 하나**
 *     매크로 다리 네 테마 부호 · 합성 `macro_sign`
 *     50/50      두 북을 따로 돌려 **손익**을 반씩
 *
 * ⚠ `tsmom`·`donchian` 은 `cta_validate.py` 의 PBO 격자 차원이지 이 북에 안 든다.
 * ⚠ 두 다리를 **곱하지 않는다** — 변조는 2026-09-09 에 NO-GO 였다.
 *
 * ## 룩백은 손잡이가 아니라 열이다
 *
 * 「룩백을 고르지 마라」가 이 레인의 규율이라(전진 선택하면 7년 합 −3,230만)
 * 셀렉트로 두면 화면이 규율을 어기는 도구가 된다. 다섯을 전부 열로 세우고
 * 왼쪽 빠름 → 오른쪽 느림으로 고정한다. 그 줄의 모양이 합성값 하나로는 안 보이는
 * 것을 말한다 — 3년물의 「빠른 쪽과 느린 쪽이 갈렸다」가 그 자리다.
 *
 * ## 색은 «금리» 방향이다
 *
 * 가격 상승 = 금리 하락이라 신호 +1 은 이 데스크에서 파랑이다. 서버가 `rate =
 * −signal` 을 같이 내고 화면은 그 값으로 캐논 네 부품(`tintStyle` 자리의
 * `signalTint` · `directionClass` · `directionGlyph` · `unsignedDelta`)을 부른다.
 * 캐논을 굽히지 않고 관례를 지키는 자리.
 *
 * 틴트만 눈금이 다르다 — 이 칸의 값은 bp 도 백분위도 아닌 «강도»(0~1)라
 * `table/tint.ts` 에 세 번째 램프가 섰다(매트릭스가 만든 그 선례).
 *
 * 숫자는 전부 서버가 끝낸다(§16, `backend/app/momentum.py`). 이 파일은 배치뿐이다.
 */

import { useCallback, useEffect, useState } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@coinbase/cds-web/tables';
import { Text } from '@coinbase/cds-web/typography';

import { BacktestUnavailable } from '@/lib/api';
import { fmtRatio, headFont } from '@/lib/format';
import { fmtSize } from '@/lib/krw';
import { TimeChart } from '@/chart/TimeChart';
import { ROW_H } from '@/table/rowHeight';
import { directionClass, directionGlyph, signalTint, unsignedDelta } from '@/table/tint';
import { Cond } from '@/ui/Cond';
import { ErrorState, LoadingState } from '@/ui/DataState';
import { Stat, StatColumn } from '@/ui/Stat';
import { ThHelp } from '@/ui/ThHelp';
import { useUrlState } from '@/ui/useUrlState';

import {
  fetchMomentumBoard,
  fetchMomentumBook,
  fetchMomentumHistory,
  type MomentumBoard,
  type MomentumBook,
  type MomentumHistory,
} from './api';

/** 금리 방향 한 낱말. **세 곳이 쓴다** — 히어로·상세 스트립·매크로 스트립.
 *  처음 판은 같은 삼항식이 두 곳에 인라인이었고 히어로가 셋째가 될 참이었다
 *  (캐논 규칙 8 — 같은 것은 한 번만 만든다). 0 은 「중립」이지 「모른다」가
 *  아니다: 서버가 못 잰 값은 `null` 로 오고 그건 부르는 쪽이 가른다. */
function rateWord(rate: number): string {
  return rate > 0 ? '금리 상승' : rate < 0 ? '금리 하락' : '중립';
}

/** 강도는 소수 두 자리. 부호는 글리프가 지므로 숫자는 **무부호**다(캐논). */
function fmtStrength(v: number | null | undefined): string {
  if (v == null) return '—';
  return unsignedDelta(Math.abs(v).toFixed(2));
}

/* 원 표기(`fmtSize`)와 비율(`fmtRatio`)은 **캐논이 진다.**
 * 처음 판은 이 파일 안에 `fmtEok`·`fmtMan`·`fmtRatio` 를 따로 들고 있었는데,
 * `fmtRatio` 는 `mr/parts` 의 것과 **글자 하나 안 틀리고 같았다.** 캐논 규칙 8
 * (「같은 것은 한 번만 만든다」)의 그 자리라 `lib/format`·`lib/krw` 로 올렸다. */

/** 강도 칸 — 캐논 네 부품 한 벌. 색은 `rate`(금리 방향)가 진다. */
function StrengthCell({ rate, title }: { rate: number | null; title?: string }) {
  return (
    <TableCell className="sr-num" justifyContent="flex-end" style={signalTint(rate)}>
      <Text
        font="label2"
        as="span"
        tabularNumbers
        noWrap
        className={directionClass(rate)}
        title={title}
      >
        {directionGlyph(rate)} {fmtStrength(rate)}
      </Text>
    </TableCell>
  );
}

export function MomentumPage() {
  const [board, setBoard] = useState<MomentumBoard | null>(null);
  const [book, setBook] = useState<MomentumBook | null>(null);
  const [hist, setHist] = useState<MomentumHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  /* 고른 다리는 **URL 상태**다 — 세입자 키와 같은 규칙(공유한 링크가 같은 화면). */
  const [selParam, setSelParam] = useUrlState('leg', '10Y');
  const sel = selParam ?? '10Y';

  const load = useCallback(() => {
    setError(null);
    Promise.all([fetchMomentumBoard(), fetchMomentumBook()])
      .then(([b, k]) => {
        setBoard(b);
        setBook(k);
      })
      .catch((e: unknown) => {
        setError(e instanceof BacktestUnavailable ? '이 화면의 자료가 아직 없어요.'
                                                  : (e as Error).message);
      })
      .finally(() => setRetrying(false));
  }, []);

  useEffect(() => load(), [load]);

  useEffect(() => {
    let live = true;
    fetchMomentumHistory(sel)
      .then((h) => { if (live) setHist(h); })
      .catch(() => { if (live) setHist(null); });
    return () => { live = false; };
  }, [sel]);

  if (error) {
    return (
      <ErrorState
        what="Momentum"
        detail={error}
        onRetry={() => { setRetrying(true); load(); }}
        retrying={retrying}
      />
    );
  }
  if (!board) return <LoadingState what="Momentum" />;

  const row = board.trend.find((r) => r.tenor === sel) ?? board.trend[0]!;
  const macro = board.macro;

  return (
    <VStack gap={1.5} width="100%" flexGrow={1} minHeight={0}>
      {/* ── 조건 바 — 어떤 규약에서 나온 숫자인지가 카드보다 먼저 읽힌다 ──── */}
      <VStack className="sr-rv-bar" flexShrink={0} gap={0.5} width="100%">
        <HStack gap={1.5} alignItems="center" flexWrap="wrap">
          <Cond k="기준일" v={board.asof} />
          <Cond k="신호" v={board.signal} />
          <Cond k="룩백" v={board.lookbacks.join(' · ')} />
          <Cond k="북 변동성 목표" v={`하루 ${fmtSize(board.targetBookVolKrw)}원`} />
          <Cond k="비용" v={`편도 ${board.costTicks}틱 · 롤 왕복 1틱`} />
          <Box style={{ marginInlineStart: 'auto' }}>
            {/* 명구 의무 — Credit RV·MR 과 같은 문법. */}
            <Text font="legal" as="span" color="fgMuted" noWrap>
              방향과 강도를 재는 화면이에요 — 단독 전략이 아니에요.
            </Text>
          </Box>
        </HStack>
        <Text font="legal" as="span" color="fgMuted">
          룩백은 고르는 게 아니라 축이에요 — 다섯을 다 보여드려요. 왼쪽이 빠르고
          오른쪽이 느려요.
        </Text>
      </VStack>

      {/* ── 히어로: 「지금 무엇을 볼까」의 답을 표 앞에 세운다 ────────────────
          [OWNER 2026-09-09 — 「Momentum도 RV나 MR과 같이 위에 Hero 하나 올려서
          트레이더가 바로 판단할 수 있게」].

          문법은 **RV·MR 의 그 블록을 이식**한 것이다: 작은 라벨 한 줄 + 이름이
          display3 로 선 버튼 + 뮤트 메타 한 줄. 부품도 그쪽 것이다 —
          `.sr-rv-linkbtn` 은 이름만 rv 이고 `theme/type.css` 의 앱 공용 리셋이다
          (캐논 규칙 2: 「클래스 이름은 소유권이 아니다」).

          **고르는 것은 서버다**(§16 · `momentum._headline`). 화면이 `sort` 를 들면
          「무엇이 1순위인가」가 두 곳에 살게 된다.

          메타가 판단 재료 넷을 진다 — 방향·강도·속도합의·유지일. 여기에 **매크로가
          같은 방향인가**를 붙인다: 두 다리를 나란히 세운 화면에서 트레이더가 제일
          먼저 묻는 것이 그것이고, 「모른다」(둘 중 하나가 중립이거나 매크로가 아직
          안 옴)를 「반대」와 **안 섞는다**.

          ⚠ 크기·진입·손절은 여기서도 말하지 않는다 — 이 화면의 명구 의무다. */}
      {board.headline ? (
        <VStack flexShrink={0} gap={0} width="100%">
          <Text font="label1" as="span" color="fgMuted" noWrap>
            지금 가장 또렷한 다리예요
          </Text>
          <HStack gap={1.5} alignItems="baseline" flexWrap="wrap">
            <button
              type="button"
              className="sr-rv-linkbtn"
              aria-label={`KTB ${board.headline.tenor} 골라서 이력 보기`}
              onClick={() => setSelParam(board.headline!.tenor)}
            >
              <Text font="display3" as="span" noWrap>
                KTB {board.headline.tenor}
              </Text>
            </button>
            <Text font="body" as="span" color="fgMuted" tabularNumbers>
              <span className={directionClass(board.headline.rate)}>
                {directionGlyph(board.headline.rate)} {rateWord(board.headline.rate)}
              </span>
              {' · '}강도 {fmtStrength(board.headline.strength)}
              {' · '}속도합의 {board.headline.speedAgree} / {board.headline.speedOf}
              {' · '}{board.headline.holdDays}일째
              {board.headline.macroAgrees === true
                ? ' · 매크로도 같은 방향이에요'
                : board.headline.macroAgrees === false
                  ? ' · 매크로는 반대예요'
                  : ' · 매크로는 아직 모르겠어요'}
            </Text>
          </HStack>
        </VStack>
      ) : null}

      {/* ⚠ **이 행은 안 눌린다**(`flexShrink={0}`). MR 은 같은 자리에서
        * `flexGrow={1} minHeight={0}` 을 쓰는데 그건 **25행짜리 보드**라 안쪽
        * 스크롤이 옳기 때문이다. 여기 표는 **2행·1행**이라 스크롤이 날 이유가 없고,
        * 실제로 눌리면 CDS `Table` 이 자기를 감싼 `overflow-y:auto` 안에서 행을
        * **잘라 버린다**(2026-09-09 실측: 표 160px 이 컨테이너 106px 안에서 KTB 10Y
        * 한 줄을 통째로 삼켰다). 잘림은 「말줄임 절대 금지」와 같은 등급의 결함이다. */}
      <HStack gap={2} alignItems="stretch" width="100%" flexShrink={0}>
        {/* ── 왼쪽: 두 다리 ────────────────────────────────────────────── */}
        <VStack
          className="sr-card"
          flexBasis={820}
          flexGrow={0}
          flexShrink={1}
          maxWidth={820}
        >
          <HStack
            alignItems="center"
            justifyContent="space-between"
            gap={1}
            paddingX={2}
            paddingTop={1.5}
            paddingBottom={0.5}
          >
            <Text font="label1" as="h2" noWrap>추세 다리</Text>
            <Text font="legal" as="span" color="fgMuted" noWrap>
              계약 2 · 룩백 5 · {board.signal}
            </Text>
          </HStack>

          <Table bordered={false}>
            <TableHeader>
              <TableRow>
                <TableCell as="th" scope="col">
                  <Text font="caption" as="span" color="fgMuted">계약</Text>
                </TableCell>
                {board.lookbacks.map((lb) => (
                  <TableCell
                    key={lb}
                    as="th"
                    scope="col"
                    className="sr-num"
                    justifyContent="flex-end"
                  >
                    <Text font="caption" as="span" color="fgMuted">{lb}일</Text>
                  </TableCell>
                ))}
                <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                  <ThHelp
                    label="합성"
                    help={`다섯 룩백의 등가중 평균이에요. 강도 1.0 은 추세 t 값이 포화점 ${board.tstatCap} 에 닿았다는 뜻이에요.`}
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
                <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                  <Text font="caption" as="span" color="fgMuted">액면</Text>
                </TableCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {board.trend.map((r) => (
                <TableRow
                  key={r.tenor}
                  tabIndex={0}
                  aria-current={r.tenor === sel || undefined}
                  style={{ height: ROW_H, cursor: 'pointer' }}
                  onClick={() => setSelParam(r.tenor)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelParam(r.tenor);
                    }
                  }}
                >
                  <TableCell>
                    <VStack as="span" className="sr-name-stack">
                      <Text font="label1" as="span" noWrap>{`KTB ${r.tenor}`}</Text>
                      <Text font="legal" as="span" color="fgMuted" noWrap tabularNumbers>
                        {r.price.toFixed(2)}
                      </Text>
                    </VStack>
                  </TableCell>
                  {r.cells.map((c) => (
                    <StrengthCell
                      key={c.lookback}
                      rate={c.rate}
                      title={c.tstat == null ? undefined : `추세 t = ${c.tstat}`}
                    />
                  ))}
                  <StrengthCell rate={r.compositeRate} />
                  <TableCell className="sr-num" justifyContent="flex-end">
                    <Text font="label2" as="span" tabularNumbers noWrap>
                      {`${r.speedAgree} / ${r.speedOf}`}
                    </Text>
                  </TableCell>
                  <TableCell className="sr-num" justifyContent="flex-end">
                    <Text font="label2" as="span" tabularNumbers noWrap color="fgMuted">
                      {`${r.holdDays}일`}
                    </Text>
                  </TableCell>
                  <TableCell className="sr-num" justifyContent="flex-end">
                    <Text font="label2" as="span" tabularNumbers noWrap color="fgMuted">
                      {fmtSize(r.notionalKrw)}
                    </Text>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {/* ── 매크로 다리 — 같은 표 문법이되 **곱하지 않는다** ────────────── */}
          <HStack
            alignItems="center"
            justifyContent="space-between"
            gap={1}
            paddingX={2}
            paddingTop={1.5}
            paddingBottom={0.5}
          >
            <Text font="label1" as="h2" noWrap>매크로 다리</Text>
            {macro ? (
              <Text font="legal" as="span" color="fgMuted" noWrap>
                네 테마 · {macro.asof}
              </Text>
            ) : null}
          </HStack>

          {macro ? (
            <Table bordered={false}>
              <TableHeader>
                <TableRow>
                  <TableCell as="th" scope="col">
                    <Text font="caption" as="span" color="fgMuted">테마</Text>
                  </TableCell>
                  {macro.themes.map((t) => (
                    <TableCell
                      key={t.key}
                      as="th"
                      scope="col"
                      className="sr-num"
                      justifyContent="flex-end"
                    >
                      <Text font="caption" as="span" color="fgMuted">{t.label}</Text>
                    </TableCell>
                  ))}
                  <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                    <Text font="caption" as="span" color="fgMuted">합성</Text>
                  </TableCell>
                  <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                    <Text font="caption" as="span" color="fgMuted">유지</Text>
                  </TableCell>
                  <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                    <Text font="caption" as="span" color="fgMuted">액면</Text>
                  </TableCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow
                  tabIndex={0}
                  aria-current={sel === 'macro' || undefined}
                  style={{ height: ROW_H, cursor: 'pointer' }}
                  onClick={() => setSelParam('macro')}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelParam('macro');
                    }
                  }}
                >
                  <TableCell>
                    <VStack as="span" className="sr-name-stack">
                      <Text font="label1" as="span" noWrap>4테마</Text>
                      <Text font="legal" as="span" color="fgMuted" noWrap>
                        OECD 빈티지
                      </Text>
                    </VStack>
                  </TableCell>
                  {macro.themes.map((t) => (
                    <StrengthCell key={t.key} rate={t.rate} />
                  ))}
                  <StrengthCell rate={macro.rate} />
                  <TableCell className="sr-num" justifyContent="flex-end">
                    <Text font="label2" as="span" tabularNumbers noWrap color="fgMuted">
                      {`${macro.holdDays}일`}
                    </Text>
                  </TableCell>
                  <TableCell className="sr-num" justifyContent="flex-end">
                    <Text font="label2" as="span" tabularNumbers noWrap color="fgMuted">
                      {fmtSize(
                        Object.values(macro.notionalKrw).reduce((a, b) => a + b, 0),
                      )}
                    </Text>
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          ) : (
            <Box paddingX={2} paddingBottom={1.5}>
              <Text font="legal" as="span" color="fgMuted">
                {board.macroNote ?? '매크로 신호를 못 읽었어요.'}
              </Text>
            </Box>
          )}

          {/* ── 50/50 — «합쳐진 신호»가 없다는 사실을 화면이 말한다 ────────── */}
          <Box paddingX={2} paddingY={1.5}>
            <Text font="legal" as="span" color="fgMuted">
              {board.blend.note}
            </Text>
          </Box>
        </VStack>

        {/* ── 오른쪽: 상세 ─────────────────────────────────────────────── */}
        <VStack className="sr-card" flexGrow={1} flexShrink={1} minWidth={0} minHeight={0}>
          <HStack
            alignItems="center"
            justifyContent="space-between"
            gap={1}
            paddingX={2}
            paddingTop={1.5}
            paddingBottom={0.5}
          >
            <Text font="label1" as="h2" noWrap>
              {sel === 'macro' ? '매크로 다리' : `KTB ${sel}`}
            </Text>
            <Text font="legal" as="span" color="fgMuted" noWrap>
              {sel === 'macro' ? '테마 부호 평균' : '차분 누적 · 시작 100'}
            </Text>
          </HStack>

          {hist ? (
            <Box paddingX={1}>
              {/* 조정가는 **차분만 유효**해서 수준을 안 그린다. 매크로 다리는
                  가격이 없어 신호 계열 하나만 선다. */}
              <TimeChart
                dates={hist.dates}
                lines={
                  hist.index
                    ? [{
                        id: 'index',
                        values: hist.index,
                        color: (p) =>
                          (hist.index![hist.index!.length - 1]! - hist.index![0]!) > 0
                            ? p.down
                            : p.up,
                        area: 'dots',
                      }]
                    : [{
                        id: 'signal',
                        values: hist.rate,
                        color: (p) => (hist.rate[hist.rate.length - 1]! > 0 ? p.up : p.down),
                        area: 'solid',
                      }]
                }
                // 180 은 이 앱의 차트 높이다(`rv/RvPage`). 220 이었을 때 페이지가
                // 셸(855px)을 **29px 넘겨** 아래 카드의 「50/50」 줄과 각주가
                // 잘렸다 — 셸은 `overflow:hidden` 이라 스크롤로도 못 본다.
                height={180}
                precision={2}
                accessibilityLabel={
                  sel === 'macro'
                    ? '매크로 다리의 테마 부호 평균 이력이에요.'
                    : `KTB ${sel} 조정가 차분 누적 이력이에요. 창 시작이 100 이에요.`
                }
              />
            </Box>
          ) : (
            <Box paddingX={2} paddingBottom={1}>
              <Text font="legal" as="span" color="fgMuted">이력을 못 읽었어요.</Text>
            </Box>
          )}

          {/* 사실 스트립은 **차트 아래**이고 `.sr-stats` 가 감싼다(캐논).
            * 그 래퍼가 윗선(`border-top`)을 진다 — 빼면 이 화면만 차트와 스트립
            * 사이가 트여서 다른 세입자와 다르게 보인다. */}
          <HStack className="sr-stats" width="100%" flexWrap="wrap">
          <StatColumn title={sel === 'macro' ? '매크로 다리' : `KTB ${sel}`}>
            {sel === 'macro' && macro ? (
              <>
                <Stat
                  label="방향"
                  value={rateWord(macro.rate)}
                  tone={macro.rate > 0 ? 'up' : macro.rate < 0 ? 'down' : undefined}
                />
                <Stat label="합성" value={fmtStrength(macro.rate)} />
                <Stat label="유지" value={`${macro.holdDays}일`} />
                <Stat label="테마" value={`${macro.themes.length}개`} />
              </>
            ) : (
              <>
                <Stat
                  label="방향"
                  value={
                    rateWord(row.compositeRate)
                  }
                  tone={row.compositeRate > 0 ? 'up' : row.compositeRate < 0 ? 'down' : undefined}
                />
                <Stat label="합성 강도" value={fmtStrength(row.compositeRate)} />
                <Stat label="유지" value={`${row.holdDays}일`} />
                <Stat
                  label="속도합의"
                  value={`${row.speedAgree} / ${row.speedOf}`}
                  note={row.speedAgree === row.speedOf ? undefined : '빠른 쪽과 느린 쪽이 갈렸어요'}
                />
              </>
            )}
          </StatColumn>
          </HStack>
        </VStack>
      </HStack>

      {/* ── 표본내 장부 + 채점 잠금 ───────────────────────────────────── */}
      {/* ⚠ **줄어드는 쪽은 여기다**(`flexShrink={1} minHeight={0}`). 히어로가
          * 들어오면서 세 블록이 셸(911px)을 53px 넘겼는데, 위 두 표는 **오늘의
          * 판단 재료**라 한 줄도 자르면 안 되고(그래서 그 행이 `flexShrink={0}`),
          * 이 카드는 **표본내 배경 자료**라 안쪽 스크롤이 옳다. 어느 쪽을 줄일지는
          * 「지금 무엇을 볼까」가 이 화면의 물음이라는 데서 정해진다. */}
      {book ? (
        <VStack className="sr-card" flexShrink={1} minHeight={0} width="100%">
          <HStack
            alignItems="center"
            justifyContent="space-between"
            gap={1}
            paddingX={2}
            paddingTop={1.5}
            paddingBottom={0.5}
            flexShrink={0}
          >
            <Text font="label1" as="h2" noWrap>표본내 성적</Text>
            <Text font="legal" as="span" color="fgMuted" noWrap>
              {book.window.start} ~ {book.window.end}
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
                  {/* 원화 낙폭만 보면 「섞으면 반이 된다」로 읽히는데, 그중 얼마는
                      «덜 걸어서 덜 아팠던 것»이다 — 실현 변동성이 다리마다 다르다.
                      이 열이 그 몫을 걷어낸다(2026-09-09 재점검). */}
                  <ThHelp
                    label="위험맞춤 낙폭"
                    help="다리마다 실제로 건 위험이 달라요. 추세 다리의 변동성에 맞춘 뒤의 낙폭이에요 — Sharpe·Calmar 는 비율이라 안 변하지만 낙폭은 변해요."
                  />
                </TableCell>
                <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                  {/* 원화라 다리끼리 그대로 못 비교한다 — 낙폭과 같은 사정이라
                      위험 맞춤 값을 뜻풀이에 같이 적는다. 부호는 **안 뒤집는다**. */}
                  <ThHelp
                    label="Ulcer"
                    help="낙폭이 얼마나 깊고 오래갔나를 한 수로 압축한 값이에요. 원화라 다리끼리 그대로 비교하면 안 되고, 무차원인 Martin 을 보세요."
                  />
                </TableCell>
                <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                  <ThHelp
                    label="Martin"
                    help="연손익 ÷ Ulcer 예요. 무차원이라 자본 기준이 없어도 다른 전략과 나란히 놓을 수 있어요."
                  />
                </TableCell>
                <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                  {/* ⚠ **`headFont` 를 거쳐야 한다.** CDS `caption` 은 대문자 변환을
                    * 걸어서 「Sharpe」가 **SHARPE** 로 렌더된다 — 옆 칸의 `Ulcer`·
                    * `Martin` 은 `ThHelp` 가 `headFont` 를 부르니까 혼합으로 서고,
                    * 이 둘만 대문자라 **같은 머리 행에서 활자가 갈렸다**(2026-09-09
                    * 스크린샷 실측). 이 리포가 σ → Σ 로 이미 밟은 그 함정이다. */}
                  <Text font={headFont('Sharpe')} as="span" color="fgMuted">Sharpe</Text>
                </TableCell>
                <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                  <Text font={headFont('Calmar')} as="span" color="fgMuted">Calmar</Text>
                </TableCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {book.legs.map((l) => (
                <TableRow key={l.key} style={{ height: ROW_H }}>
                  <TableCell>
                    <Text font="label1" as="span" noWrap>{l.label}</Text>
                  </TableCell>
                  <TableCell className="sr-num" justifyContent="flex-end">
                    <Text font="label2" as="span" tabularNumbers noWrap>
                      {fmtSize(l.card.annPnlKrw)}
                    </Text>
                  </TableCell>
                  <TableCell className="sr-num" justifyContent="flex-end">
                    <Text font="label2" as="span" tabularNumbers noWrap color="fgMuted">
                      {fmtSize(l.card.annVolKrw)}
                    </Text>
                  </TableCell>
                  <TableCell className="sr-num" justifyContent="flex-end">
                    <Text font="label2" as="span" tabularNumbers noWrap color="fgMuted">
                      {fmtSize(l.card.maxDrawdown)}
                    </Text>
                  </TableCell>
                  <TableCell className="sr-num" justifyContent="flex-end">
                    <Text font="label2" as="span" tabularNumbers noWrap>
                      {fmtSize(l.card.maxDrawdownVolMatched)}
                    </Text>
                  </TableCell>
                  <TableCell className="sr-num" justifyContent="flex-end">
                    <Text
                      font="label2"
                      as="span"
                      tabularNumbers
                      noWrap
                      color="fgMuted"
                      title={`위험맞춤 ${fmtSize(l.card.ulcerVolMatched)}`}
                    >
                      {fmtSize(l.card.ulcer)}
                    </Text>
                  </TableCell>
                  <TableCell className="sr-num" justifyContent="flex-end">
                    <Text font="label2" as="span" tabularNumbers noWrap>
                      {fmtRatio(l.card.martin)}
                    </Text>
                  </TableCell>
                  <TableCell className="sr-num" justifyContent="flex-end">
                    <Text font="label2" as="span" tabularNumbers noWrap>
                      {fmtRatio(l.card.sharpe)}
                    </Text>
                  </TableCell>
                  <TableCell className="sr-num" justifyContent="flex-end">
                    <Text font="label2" as="span" tabularNumbers noWrap>
                      {fmtRatio(l.card.calmar)}
                    </Text>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {/* ★ 채점 잠금 — 이 줄이 이 카드가 존재해도 되는 조건이다. */}
          <Box paddingX={2} paddingY={1.5}>
            <Text font="legal" as="span" color="fgMuted">
              {book.volMatch ? `${book.volMatch.note} ` : ''}
              {book.lock.note} 동결일은 {book.lock.freeze} 이에요. {book.lock.why}
            </Text>
          </Box>
        </VStack>
      ) : null}
    </VStack>
  );
}
