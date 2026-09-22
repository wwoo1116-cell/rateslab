'use client';

/* Portfolio — **세운 것을 매일 지켜보는 자리** [OWNER 2026-09-21 오후].
 *
 * > "Strategy와 동일 위계로 존재하는 Portfolio Management tab을 만들어서
 * >  거기에서 이제 우리가 테스트했던 걸 직접 페이퍼 트레이드를 할 수 있게,
 * >  그러니까 매일 PnL을 확인할 수 있게 환경을 하나 만들어다오."
 *
 * ## Strategy 와 무엇이 다른가 — 이 화면의 존재 이유
 *
 * 계획면은 스스로 이렇게 적는다: 「조건을 고른 창과 성과를 잰 창이 같아서 표본내
 * 과적합이 붙어요」. 그래서 그 화면의 1년 손익은 **성과가 아니라 고른 결과**다.
 * 이 데스크에 없던 것은 그 다음이었다 — **고른 뒤에 무슨 일이 일어났나.**
 *
 * 여기서 등록하면 조건이 그 자리에서 얼고, 그 뒤로는 시장만 움직인다. 하루가
 * 지날 때마다 표본밖이 하루씩 길어진다. 그것이 이 화면이 쌓는 유일한 자산이다.
 *
 * ## 북이 둘이고, 값어치는 **차이**에 있다
 *
 *     규칙 북   등록한 조건이 시키는 대로 한 것. 사람 손이 안 들어간다.
 *     수동 북   내가 직접 잡은 것. 규칙을 안 따르는 판단도 들어간다.
 *
 * 규칙 북만 있으면 「이 규칙이 사나」를 알고, 둘이 있으면 「내 판단이 규칙보다
 * 나은가」를 안다. 히어로가 셋째 수(차이)를 제일 크게 세우는 이유다.
 *
 * ## 부품은 전부 캐논이다
 *
 * 표는 `Table`+`ROW_H`, 방향색은 `table/tint`, 조건 바는 `Cond`,
 * 차트는 `TimeChart`, 컨트롤은 `Field`/`Segmented`(32px 등고). 새로 만든 모양이
 * 없다 — 새 탭이라고 새 문법을 쓰면 「사이트 전체에 얼라인이 없다」가 된다.
 */

import { useCallback, useEffect, useState } from 'react';

import { Select } from '@coinbase/cds-web/alpha/select';
import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@coinbase/cds-web/tables';
import { TextInput } from '@coinbase/cds-web/controls';
import { Text } from '@coinbase/cds-web/typography';

import { BacktestUnavailable } from '@/lib/api';
import { eul } from '@/lib/josa';
import { fmtKrw } from '@/lib/krw';
import { ROW_H } from '@/table/rowHeight';
import { directionClass } from '@/table/tint';
import { Cond } from '@/ui/Cond';
import { Field, Segmented } from '@/ui/ControlCard';
import { CONTROL_H } from '@/ui/controlHeight';
import { ErrorState, LoadingState } from '@/ui/DataState';
import { ThHelp } from '@/ui/ThHelp';
import { DROPDOWN_STYLES } from '@/ui/window/popup';

/* 쓰기는 지금 **다리 둘뿐**이다. `addTrade`·`closeTrade`·`enrollSeries`·
 * `retireSeries` 는 계약(`api.ts`)과 라우트에 그대로 살아 있고 여기서만 안 부른다
 * [OWNER 2026-09-22 — "지금은 일단"]. 되살릴 때 임포트만 되돌리면 된다. */
import {
  addLeg, closeLeg, fetchInstruments, fetchPaper, resetBook,
  type PaperInstruments, type PaperPositionLeg, type PaperSheet,
} from './api';

const MINUS = '−';






const KIND_WORD: Record<string, string> = {
  irs: 'IRS', bond: '국고 현물', fut: '국채선물',
};
const SIDE_WORD: Record<string, string> = {
  pay: '페이', receive: '리시브', buy: '매수', sell: '매도',
};

/** 손으로 쌓은 다리 표 — **한 줄이 한 체결**이다.
 *
 *  「내 레벨」과 「지금」을 나란히 두는 것이 이 표의 전부다. 수동 북(계열+방향)은
 *  진입을 그날 **종가**로 매겼고, 그래서 내가 실제로 받은 값을 적을 자리가 없었다
 *  [OWNER 2026-09-22]. Δbp 는 그 둘의 차이고 손익은 거기에 DV01 을 곱한 것이다.
 *
 *  ⚠ 부호는 **낱말이 아니라 `rateSign`** 이 진다 — 「페이」와 「선물 매도」가 같은
 *  쪽이고 「리시브」와 「매수」가 같은 쪽이다. 낱말로 색을 칠하면 계기마다 규약을
 *  다시 적게 되고, 그게 이 리포가 반복해서 밟은 자리다. */
function PositionTable({ legs, asof, busy, onClose }: {
  legs: PaperPositionLeg[]; asof: string | null; busy: boolean;
  onClose: (n: number, level: number) => void;
}) {
  if (legs.length === 0) {
    return (
      <Box paddingX={2} paddingBottom={2}>
        <Text font="legal" as="span" color="fgMuted">
          아직 쌓은 다리가 없어요 — 아래에서 하나씩 담으면 여기 쌓여요.
        </Text>
      </Box>
    );
  }
  return (
    <div className="sr-rv-scroll">
      <Table bordered={false}>
        <TableHeader>
          <TableRow>
            <TableCell as="th" scope="col">
              <Text font="caption" as="span" color="fgMuted">계기</Text>
            </TableCell>
            <TableCell as="th" scope="col">
              <Text font="caption" as="span" color="fgMuted">묶음</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <ThHelp label="내 레벨"
                help="내가 실제로 체결한 금리예요. 그날 종가가 아니에요 — 그게 이 표가 생긴 이유예요." />
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="caption" as="span" color="fgMuted">지금</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="caption" as="span" color="fgMuted">Δ</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <ThHelp label="DV01"
                help="1bp 움직일 때의 돈이에요. 명목을 치면 이 값이, 이 값을 치면 명목이 진입일 커브로 채워져요." />
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="caption" as="span" color="fgMuted">명목</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="caption" as="span" color="fgMuted">손익</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="caption" as="span" color="fgMuted">청산</Text>
            </TableCell>
          </TableRow>
        </TableHeader>
        <TableBody>
          {legs.map((l) => (
            <TableRow key={l.n} style={{ height: ROW_H }}>
              <TableCell>
                <VStack as="span" className="sr-name-stack">
                  <Text font="label1" as="span" noWrap>
                    {`${KIND_WORD[l.kind] ?? l.kind} ${l.tenor} ${SIDE_WORD[l.side] ?? l.side}`}
                  </Text>
                  <Text font="legal" as="span" color="fgMuted" noWrap>
                    {l.open ? `${l.entry} 진입` : `${l.entry} → ${l.exit} 청산`}
                  </Text>
                </VStack>
              </TableCell>
              <TableCell>
                <Text font="legal" as="span" color="fgMuted" noWrap>{l.tag || MINUS}</Text>
              </TableCell>
              <TableCell className="sr-num" justifyContent="flex-end">
                <Text font="label2" as="span" tabularNumbers noWrap>{l.level.toFixed(3)}</Text>
              </TableCell>
              <TableCell className="sr-num" justifyContent="flex-end">
                {/* ★레벨 **아래에 그 날**을 적는다 [OWNER 2026-09-22]. 마크는
                    종가라 체결일과 다른 날일 수 있고, 특히 오늘 체결한 다리는
                    마크가 하루 앞선다 — 날을 안 적으면 「지금」이 정말 지금인
                    줄 읽는다. 체결일과 같은 날이면 군더더기라 안 적는다. */}
                <VStack as="span" className="sr-name-stack" alignItems="flex-end">
                  <Text font="label2" as="span" tabularNumbers noWrap color="fgMuted">
                    {l.open
                      ? (l.mark == null ? MINUS : l.mark.toFixed(3))
                      : (l.exitLevel == null ? MINUS : l.exitLevel.toFixed(3))}
                  </Text>
                  <Text font="legal" as="span" color="fgMuted" tabularNumbers noWrap>
                    {l.open && l.markT && l.markT !== l.entry ? `${l.markT} 종가` : ''}
                  </Text>
                </VStack>
              </TableCell>
              <TableCell className="sr-num" justifyContent="flex-end">
                {/* 색은 **손익 부호**를 따른다 — Δ 의 부호가 아니다. 같은 +2bp 가
                    페이에겐 이익이고 리시브에겐 손실이라, Δ 에 방향색을 칠하면
                    표가 절반의 줄에서 거짓말을 한다. */}
                <Text font="label2" as="span" tabularNumbers noWrap
                  className={l.pnl == null ? undefined : directionClass(l.pnl)}>
                  {l.bp == null ? MINUS : `${l.bp >= 0 ? '+' : '−'}${Math.abs(l.bp).toFixed(1)}bp`}
                </Text>
              </TableCell>
              <TableCell className="sr-num" justifyContent="flex-end">
                <VStack as="span" className="sr-name-stack" alignItems="flex-end">
                  <Text font="label2" as="span" tabularNumbers noWrap>
                    {`${fmtKrw(l.dv01)}/bp`}
                  </Text>
                  <Text font="legal" as="span" color="fgMuted" noWrap>
                    {l.rateSign > 0 ? '금리↑에 번다' : '금리↓에 번다'}
                  </Text>
                </VStack>
              </TableCell>
              <TableCell className="sr-num" justifyContent="flex-end">
                <Text font="label2" as="span" tabularNumbers noWrap color="fgMuted">
                  {`${(l.notional / 1e8).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}억`}
                </Text>
              </TableCell>
              <TableCell className="sr-num" justifyContent="flex-end">
                <VStack as="span" className="sr-name-stack" alignItems="flex-end">
                  <Text font="label2" as="span" tabularNumbers noWrap
                    className={l.pnl == null ? undefined : directionClass(l.pnl)}>
                    {l.pnl == null ? MINUS : fmtKrw(l.pnl)}
                  </Text>
                  <Text font="legal" as="span" color="fgMuted" noWrap>
                    {l.why ?? (l.cost == null ? '' : `비용 ${fmtKrw(l.cost)}`)}
                  </Text>
                </VStack>
              </TableCell>
              <TableCell className="sr-num" justifyContent="flex-end">
                {l.open && l.mark != null ? (
                  /* ★버튼이 **어느 날 종가로** 닫는지 말한다 [OWNER 2026-09-22].
                     「지금 레벨」이라고만 적혀 있었는데 그 값은 마지막 **종가**라,
                     종가가 하루 늦은 날에는 오늘 청산을 어제 레벨로 적으면서
                     화면은 「지금」이라고 말하고 있었다. 청산일은 오늘이다.
                     ▶내가 적는 청산 레벨 칸은 아직 없다 — 오너 결정. */
                  <button type="button" className="sr-pillbtn" disabled={busy || !asof}
                    onClick={() => onClose(l.n, l.mark as number)}>
                    {l.markT ? `${l.markT} 종가로 닫기` : '지금 레벨로 닫기'}
                  </button>
                ) : (
                  <Text font="legal" as="span" color="fgMuted" noWrap>
                    {l.open ? '레벨 없음' : (l.exit ?? MINUS)}
                  </Text>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function PortfolioPage() {
  const [sheet, setSheet] = useState<PaperSheet>();
  const [error, setError] = useState<string>();
  const [unavailable, setUnavailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string>();

  /* 손잡이는 **북마다 따로**다. 한 상태를 둘이 나눠 쓰면 거래를 담으려고 고른
     계열이 등록 칸까지 바꾸는데(그쪽은 이미 등록된 것을 목록에서 빼므로 방금 고른
     것이 사라지기도 한다), 두 북은 서로 다른 결정이라 그 연동이 틀렸다. */

  /* ── 다리 쌓기 손잡이 [OWNER 2026-09-22] ────────────────────────────────
     계기 목록은 **서버가 낸다**(`fetchInstruments`) — 화면이 손으로 적으면
     선물 2Y 같은 «화면에서만 가능한 거래»가 생긴다. 그래서 만기·방향 목록도
     고른 계기에서 파생시키고, 여기서 상수로 두지 않는다. */
  const [inst, setInst] = useState<PaperInstruments>();
  const [legKind, setLegKind] = useState<'irs' | 'bond' | 'fut'>('irs');
  const [legTenor, setLegTenor] = useState('2Y');
  const [legSide, setLegSide] = useState('pay');
  const [legEntry, setLegEntry] = useState('');
  const [legLevel, setLegLevel] = useState('');
  /** 명목이냐 DV01 이냐 — **하나만 친다** [OWNER 「둘 다 적는다」]. 표에는 둘 다
   *  서고, 채우는 것은 서버다(안 맞는 쌍을 장부에 안 들인다). */
  const [sizeMode, setSizeMode] = useState<'notional' | 'dv01'>('notional');
  const [sizeVal, setSizeVal] = useState('');
  const [legTag, setLegTag] = useState('');
  /** 초기화 한 번 더 묻기 — 화면의 문이고, 서버가 확인 낱말로 둘째 문을 진다. */
  const [resetArm, setResetArm] = useState(false);

  useEffect(() => {
    /* 한 번만 읽는다 — 계기 목록은 하루에 안 바뀐다. 실패해도 화면은 서고,
       폼만 「계기를 못 읽었어요」로 잠긴다(조용히 빈 목록을 그리지 않는다). */
    fetchInstruments().then(setInst).catch(() => setInst(undefined));
  }, []);

  const load = useCallback(() => {
    setError(undefined);
    setUnavailable(false);
    fetchPaper()
      .then(setSheet)
      .catch((e: unknown) => {
        if (e instanceof BacktestUnavailable) setUnavailable(true);
        else setError(e instanceof Error ? e.message : String(e));
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);


  /* 쓰기 한 벌 — 응답이 곧 새 장부라 다시 묻지 않는다. */
  const write = useCallback((run: () => Promise<PaperSheet>, ok: string) => {
    setBusy(true);
    setNote(undefined);
    run()
      .then((s) => {
        setSheet(s);
        setNote(ok);
      })
      .catch((e: unknown) => setNote(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  }, []);


  if (unavailable) {
    return (
      <ErrorState
        what="페이퍼 북"
        detail="실행 중인 백엔드가 필요하고, /api/paper 를 아는 판이어야 해요 — 백엔드를 먼저 올려 주세요."
        onRetry={load}
      />
    );
  }
  if (error) return <ErrorState what="페이퍼 북" detail={error} onRetry={load} />;
  if (!sheet) return <LoadingState what="페이퍼 북" />;
  if (!sheet.available) {
    return <ErrorState what="페이퍼 북" detail={sheet.why ?? '못 세웠어요'} onRetry={load} />;
  }

  return (
    <VStack gap={1.5} width="100%" flexGrow={1} minHeight={0}>
      {/* ── 조건 바 ─────────────────────────────────────────────────────── */}
      <VStack className="sr-rv-bar" flexShrink={0} gap={0.5} width="100%">
        <HStack gap={1.5} alignItems="center" flexWrap="wrap">
          <Cond k="장부 개설" v={sheet.opened ?? '아직 없어요'} strong />
          {/* ★두 날을 **나란히** 적는다 [OWNER 2026-09-22 — "민평 종가는 9월
              21일까지 들어와있지만 … 오늘 장중에 진입했다면 그건 22일날 진입한거임"].
              체결은 장중이고 마크는 종가라 둘이 다를 수 있고, 한 칸만 적으면
              읽는 사람이 그 차이를 못 본다. 같은 날이면 한 칸으로 접는다. */}
          <Cond k="오늘" v={sheet.today} strong />
          {sheet.asof && sheet.asof !== sheet.today ? (
            <Cond k="마지막 종가" v={sheet.asof} />
          ) : null}
          <Cond k="포지션" v={`${sheet.position.open}다리 · 청산 ${sheet.position.closed}`} />
          <Cond k="비용" v={`편도 ${sheet.costBp}bp`} />
          {/* 규칙 북·수동 북 칩 둘은 그 카드들과 같이 내렸다 [OWNER 2026-09-22].
              `Delta` 칩도 뺀다 — 그건 수동 북의 고정 명목이고, 다리는 명목·DV01 을
              줄마다 스스로 적는다(한 화면에 두 크기 규약이 서면 안 읽힌다). */}
          {busy ? (
            <Text font="legal" as="span" color="fgMuted" noWrap>쓰는 중…</Text>
          ) : null}
          {/* 초기화 — **두 번 눌러야 한다** [OWNER 2026-09-22 "포트폴리오 전체
              초기화 버튼도 만들어줘"]. 한 번 누르면 묻고, 다시 누르면 친다.
              서버도 확인 낱말을 따로 검사하므로 **문이 둘**이다: 장부가 버튼
              하나로 사라지면 그건 사고가 아니라 설계다.
              ⚠ 지우는 것이 아니라 **치우는 것**이다 — 옛 장부는 서버가
              `data/paper_archive/` 에 시각 도장을 찍어 남긴다. */}
          <button
            type="button"
            className="sr-pillbtn"
            /* 조건 바는 바탕이 `--sr-page` 라 `data-fill` 채움이 라이트에서
               안 보인다 — 선으로 세운다(그 근거는 type.css 의 그 변형). */
            data-outline=""
            disabled={busy}
            onClick={() => {
              if (!resetArm) {
                setResetArm(true);
                setNote('다시 누르면 장부를 새로 시작해요 — 옛 장부는 파일로 남아요.');
                return;
              }
              setResetArm(false);
              /* `write` 는 성공 문장을 **인자로** 받으므로 여기서 setNote 를 해도
                 그 뒤에 덮인다(첫 판에서 보관본 이름이 그렇게 사라졌다). 이 한
                 건만 직접 돌린다 — 문장이 응답에 달려 있기 때문이다. */
              setBusy(true);
              setNote(undefined);
              resetBook()
                .then((r) => {
                  setSheet(r);
                  setNote(r.archivedTo
                    ? `장부를 새로 시작했어요 — 옛 장부는 ${r.archivedTo} 로 남겼어요.`
                    : '장부를 새로 시작했어요.');
                })
                .catch((e: unknown) =>
                  setNote(e instanceof Error ? e.message : String(e)))
                .finally(() => setBusy(false));
            }}
          >
            {resetArm ? '정말 초기화할까요?' : '장부 초기화'}
          </button>
          <Box style={{ marginInlineStart: 'auto' }}>
            <Text font="legal" as="span" color="fgMuted" noWrap>
              체결이 아니라 기록이에요 — 투자판단이 아니에요.
            </Text>
          </Box>
        </HStack>
        <Text font="legal" as="span" color="fgMuted" maxWidth={760}>
          Strategy 의 1년 손익은 <b>조건을 고른 창에서 잰 수</b>라 성과가 아니라 고른
          결과예요. 이 장부는 그 다음을 재요 — 등록하는 순간 조건이 얼고, 그 뒤로는
          시장만 움직여요. 하루가 지날 때마다 표본밖이 하루씩 길어져요.
        </Text>
        {note ? (
          <Text font="legal" as="span" color="fgMuted" maxWidth={760}>{note}</Text>
        ) : null}
        {sheet.failed.length > 0 ? (
          <Text font="legal" as="span" color="fgMuted" maxWidth={760}>
            {sheet.failed.map((f) => `${f.id}: ${f.why}`).join(' · ')}
          </Text>
        ) : null}
      </VStack>

      {/* ── 지금은 **포지션 하나만** [OWNER 2026-09-22 — "규칙북이랑 수동북
          없애고 이렇게 개별 포지션 쌓는 칸만 남기자 지금은 일단"] ────────

          걷은 것: 히어로(규칙 대 수동의 «차이») · 누적 손익 차트 · 규칙 북 ·
          수동 북. 셋 다 «두 북을 견준다» 는 한 물음에 매달려 있어서, 그 물음을
          접으면 같이 접힌다.

          ⚠ **화면에서만 걷었다.** `/api/paper/enroll`·`retire`·`trade`·`close`
          와 장부의 `enrolled`·`trades` 는 그대로다 — 이 리포는 쓰기 라우트를
          안 지우고(생존 편향), 「지금은 일단」이라 되돌릴 자리를 남긴다.
          되살리려면 이 커밋의 JSX 를 되돌리면 된다. */}
      <VStack gap={1.5} width="100%" flexGrow={1} minHeight={0} style={{ overflowY: 'auto' }}>
        {/* ── 포지션 — **손으로 쌓는 다리** [OWNER 2026-09-22] ─────────────
            > "포지션은 써서 넣을 수 있게 … IRS pay receive 하나 씩 쌓는 방식으로"
            > "ex. BSS라고 하면, 국채선물 2년 금리 몇에 매수 / IRS Pay 2년 금리 몇에 매도"

            아래 수동 북과 **다른 물건**이다. 저쪽은 «계열 + 방향»을 받아 그날
            **종가**로 값을 매기고, 이쪽은 «계기 하나 + 내가 체결한 레벨»이다.
            BSS 를 선물로 세우든 현물로 세우든 실제로 쥔 다리를 그대로 적는다. */}
        <VStack className="sr-card" flexShrink={0} width="100%">
          <HStack alignItems="baseline" justifyContent="space-between" gap={1}
            paddingX={2} paddingTop={1.5} paddingBottom={0.5} flexWrap="wrap">
            <HStack alignItems="baseline" gap={1}>
              <Text font="label1" as="h2" noWrap>포지션</Text>
              <Text font="legal" as="span" color="fgMuted" tabularNumbers noWrap>
                {`보유 ${sheet.position.open} · 청산 ${sheet.position.closed}`}
              </Text>
            </HStack>
            <Text font="legal" as="span" color="fgMuted" tabularNumbers>
              {`순 DV01 ${fmtKrw(sheet.position.netDv01)}/bp · 총 ${fmtKrw(sheet.position.grossDv01)}/bp`}
              {/* 합계는 **전부 매겨졌을 때만** 선다(하나라도 「아직」이면 0 으로
                  채우는 셈이 된다). 그때는 매겨진 다리의 소계를 «몇 중 몇»과 같이
                  적는다 — 다른 칸이라 둘을 섞을 수 없다 [2026-09-22]. */}
              {sheet.position.pnl != null
                ? ` · 합계 ${fmtKrw(sheet.position.pnl)}`
                : sheet.position.scoredPnl != null
                  ? ` · 매겨진 ${sheet.position.scored}다리 ${fmtKrw(sheet.position.scoredPnl)}`
                    + ` · 아직 ${sheet.position.pending}다리`
                  : ''}
            </Text>
          </HStack>
          <PositionTable
            legs={sheet.position.legs}
            asof={sheet.asof}
            busy={busy}
            onClose={(n, level) =>
              /* 청산일도 **오늘**이다(체결일과 같은 이유). 청산 레벨은 여전히
                 내가 적는다 — 아래 버튼이 넘기는 값이 그것이다. */
              write(() => closeLeg(n, sheet.today, level),
                    `${n}번 다리를 닫았어요.`)}
          />
          {/* 담는 줄 — 얼라인 캐논 그대로(라벨 위 · 32px 등고 · 바닥 정렬 ·
              폭은 감싸는 Box 가 준다). */}
          <HStack gap={1.5} alignItems="flex-end" paddingX={2} paddingBottom={0.5} flexWrap="wrap">
            <Box width={130}>
              <Field label="계기">
                <Select size="s" font="legal" styles={DROPDOWN_STYLES}
                  accessibilityLabel="계기"
                  value={legKind}
                  onChange={(v: unknown) => {
                    const k = String(v ?? 'irs') as 'irs' | 'bond' | 'fut';
                    setLegKind(k);
                    {/* 계기를 바꾸면 만기·방향이 그 계기의 것으로 **따라간다** —
                        안 따라가면 「선물 2Y 페이」 같은 조합이 폼에 남는다. */}
                    const found = inst?.kinds.find((x) => x.kind === k);
                    if (found) {
                      if (!found.tenors.includes(legTenor)) setLegTenor(found.tenors[0] ?? '');
                      if (!found.sides.some((sd) => sd.v === legSide)) {
                        setLegSide(found.sides[0]?.v ?? '');
                      }
                    }
                  }}
                  options={(inst?.kinds ?? []).map((k) => ({ value: k.kind, label: k.label }))}
                />
              </Field>
            </Box>
            <Box width={110}>
              <Field label="만기">
                <Select size="s" font="legal" styles={DROPDOWN_STYLES}
                  accessibilityLabel="만기"
                  value={legTenor}
                  onChange={(v: unknown) => setLegTenor(String(v ?? ''))}
                  options={(inst?.kinds.find((k) => k.kind === legKind)?.tenors ?? [])
                    .map((t) => ({ value: t, label: t }))}
                />
              </Field>
            </Box>
            <Box width={140}>
              <Field label="방향"
                help="부호는 낱말이 아니라 「금리가 오르면 버는가」로 저장돼요 — 페이와 선물 매도가 같은 쪽이에요.">
                <Select size="s" font="legal" styles={DROPDOWN_STYLES}
                  accessibilityLabel="방향"
                  value={legSide}
                  onChange={(v: unknown) => setLegSide(String(v ?? ''))}
                  options={(inst?.kinds.find((k) => k.kind === legKind)?.sides ?? [])
                    .map((sd) => ({ value: sd.v, label: sd.label }))}
                />
              </Field>
            </Box>
            <Box width={130}>
              <Field label="체결 금리(%)"
                help="내가 실제로 받은 레벨이에요. 종가가 아니라 이걸 적는 게 이 표의 존재 이유예요.">
                <TextInput size="s" fontSize="legal" height={CONTROL_H}
                  accessibilityLabel="체결 금리 (%)"
                  value={legLevel}
                  placeholder="3.970"
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setLegLevel(e.target.value)}
                />
              </Field>
            </Box>
            <Box width={150}>
              <Field label="크기 기준"
                help="하나만 쳐요 — 나머지는 진입일 커브로 서버가 채워요. 둘 다 받으면 안 맞는 쌍이 장부에 남아요.">
                <Segmented
                  value={sizeMode}
                  onChange={setSizeMode}
                  label="크기 기준"
                  options={[
                    { value: 'notional', label: '명목', title: '억 단위' },
                    { value: 'dv01', label: 'DV01', title: '만원/bp' },
                  ]}
                />
              </Field>
            </Box>
            <Box width={140}>
              <Field label={sizeMode === 'notional' ? '명목(억)' : 'DV01(만원/bp)'}>
                <TextInput size="s" fontSize="legal" height={CONTROL_H}
                  accessibilityLabel={sizeMode === 'notional' ? '명목 (억)' : 'DV01 (만원/bp)'}
                  value={sizeVal}
                  placeholder={sizeMode === 'notional' ? '100' : '295'}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSizeVal(e.target.value)}
                />
              </Field>
            </Box>
            <Box width={140}>
              <Field label="체결일">
                <TextInput size="s" fontSize="legal" height={CONTROL_H}
                  accessibilityLabel="체결일 (YYYY-MM-DD)"
                  value={legEntry}
                  /* ★`asof`(자료의 날)가 아니라 **오늘**이다 — 종전에는 이 기본값
                     때문에 오늘 장중에 한 거래가 어제 날짜로 장부에 들어갔다.
                     하드코딩돼 있던 '2026-09-21' 폴백도 같이 없앤다(서버가 늘
                     오늘을 실어 준다). */
                  placeholder={sheet.today}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setLegEntry(e.target.value)}
                />
              </Field>
            </Box>
            <Box width={150}>
              <Field label="묶음"
                help="다리들을 부르는 이름이에요(예 「BSS 2Y」). 산술에는 안 써요 — 묶음이 산술을 지면 화면이 BSS 를 다시 정의하게 돼요.">
                <TextInput size="s" fontSize="legal" height={CONTROL_H}
                  accessibilityLabel="묶음 이름"
                  value={legTag}
                  placeholder="BSS 2Y"
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setLegTag(e.target.value)}
                />
              </Field>
            </Box>
            <button
              type="button"
              className="sr-pillbtn"
              /* 카드(흰/짙은 카드색) 위라 캐논의 «액션 pill» 채움이 보인다 —
                 쓰는 버튼은 사실 칩과 구별돼야 한다 [트레이더 2026-09-22]. */
              data-fill=""
              disabled={busy || !inst || !legTenor || !legSide || !legLevel || !sizeVal}
              onClick={() => {
                const size = Number(sizeVal);
                const level = Number(legLevel);
                write(
                  () => addLeg({
                    kind: legKind,
                    tenor: legTenor,
                    side: legSide,
                    entry: legEntry || sheet.today,
                    level,
                    ...(sizeMode === 'notional'
                      ? { notional: size * 1e8 }
                      : { dv01: size * 1e4 }),
                    tag: legTag,
                  }),
                  `${KIND_WORD[legKind]} ${legTenor} ${SIDE_WORD[legSide] ?? legSide}${
                    eul(SIDE_WORD[legSide] ?? legSide)} 담았어요.`);
              }}
            >
              다리 담기
            </button>
          </HStack>
          <Box paddingX={2} paddingBottom={2}>
            <Text font="legal" as="span" color="fgMuted" maxWidth={760}>
              {inst
                ? (inst.kinds.find((k) => k.kind === legKind)?.why
                   ?? '체결 레벨과 크기는 내가 적고, 오늘 레벨과 나머지 한 칸은 서버가 채워요.')
                : '계기 목록을 못 읽었어요 — 백엔드를 보세요.'}
            </Text>
          </Box>
        </VStack>

      </VStack>
    </VStack>
  );
}
