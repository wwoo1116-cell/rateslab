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
import { Pressable } from '@coinbase/cds-web/system';
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
import { fitWidth, useControlFont } from '@/ui/fit';
import { GAP } from '@/ui/gaps';
import { ErrorState, LoadingState } from '@/ui/DataState';
import { Stat, StatColumn } from '@/ui/Stat';
import { ThHelp } from '@/ui/ThHelp';
import { DROPDOWN_STYLES } from '@/ui/window/popup';

/* 쓰기는 지금 **다리 둘뿐**이다. `addTrade`·`closeTrade`·`enrollSeries`·
 * `retireSeries` 는 계약(`api.ts`)과 라우트에 그대로 살아 있고 여기서만 안 부른다
 * [OWNER 2026-09-22 — "지금은 일단"]. 되살릴 때 임포트만 되돌리면 된다. */
import {
  addLeg, attachKnobs, closeLeg, fetchInstruments, fetchLive, fetchPaper, fetchSuggest,
  knobsComplete, resetBook,
  type PaperInstruments, type PaperLegTrack,
  type PaperPositionGroup, type PaperPositionLeg,
  type PaperSheet, type PaperSuggest,
} from './api';
import { suggestLine } from './suggestLine';
import { TraceWindow } from './TraceWindow';
import { knobWord, zWord } from './words';

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
/** 「안 함」의 값 — `null` 을 쓰면 CDS 의 단일 선택 타입이 넓어져 호출부마다
 *  null 체크가 붙는다(`StartFilter.ALL_STARTS` 와 같은 판단). */
const NO_SERIES = 'none';

/* 진입 규칙의 우리말과 얼린 조건 한 줄(`knobWord`)은 `./words` 로 갔다 [2026-09-28]
   — 「그날 1등」 줄이 표와 **같은 꼴**로 조건을 적어야 해서다. */

/* `zWord` 도 `./words` 로 갔다 [2026-09-28] — 추적 창의 머리띠가 같은 꼴을 쓴다. */

/**
 * 지금 닿았는가 — 한 칸 [OWNER 2026-09-23].
 *
 * 세 가지를 **구별해서** 적는다. 셋을 뭉치면 읽는 사람이 엉뚱한 결론을 낸다:
 *
 *   닿음    「손절 −3.1σ」 — 사유와 수를 같이
 *   아직    「−2.1σ」      — 재고 있고 아직 아니다
 *   못 잼   「— 계열을 안 골랐어요」 — **안 닿은 것이 아니다**
 *
 * 닫힌 다리에는 아무것도 안 적는다 — 지난 일을 오늘 일처럼 적게 된다.
 */
function TrackCell({ track, open }: { track: PaperLegTrack | null; open: boolean }) {
  if (!open) return <Text font="legal" as="span" color="fgMuted">{MINUS}</Text>;
  if (!track) {
    return (
      <Text font="legal" as="span" color="fgMuted" noWrap>
        {MINUS}
      </Text>
    );
  }
  if (track.why) {
    /* 못 재는 이유는 **적는다**. 「—」만 두면 안 닿은 것으로 읽힌다. */
    return (
      <Text font="legal" as="span" color="fgMuted">
        {`${MINUS} ${track.why}`}
      </Text>
    );
  }
  const z = zWord(track.z);
  if (track.hit == null) {
    return (
      <VStack as="span" className="sr-name-stack">
        <Text font="label2" as="span" tabularNumbers noWrap>{z}</Text>
        <Text font="legal" as="span" color="fgMuted" tabularNumbers noWrap>
          {`진입 ${zWord(track.entryZ)}`}
        </Text>
      </VStack>
    );
  }
  /* 손절은 하락색으로 갈라 세운다 — 청산은 계획대로 나가는 것이고 손절은
     아니다(전략 창이 거래 사유에 쓰는 그 규칙과 같다). */
  return (
    <VStack as="span" className="sr-name-stack">
      <Text font="label2" as="span" tabularNumbers noWrap
        className={track.hit === 'stop' ? 'sr-down' : 'sr-up'}>
        {`${track.hit === 'stop' ? '손절' : '청산'} ${z}`}
      </Text>
      <Text font="legal" as="span" color="fgMuted" tabularNumbers noWrap>
        {`진입 ${zWord(track.entryZ)} · ${track.asof ?? ''}`}
      </Text>
    </VStack>
  );
}

/**
 * 청산·손절 **레벨** [OWNER 2026-09-28 — "언제 손절, 익절인지 레벨로 표시해주기로
 * 했었는데 어디간거임?"].
 *
 * 09-23 판은 z 만 적었다(옆 「밴드」 칸). 이 칸은 그 두 문을 **오늘 밴드의 값**으로
 * 푼 것이다 — 서버가 `중심선 ± 배수·σ` 로 번역해 보낸다(`track_leg`). 계열의 자기
 * 단위라(BSS·커브 bp · 선물 %) 단위를 수 옆에 적고, 진입한 쪽의 선 하나씩만
 * 적는다(중심선을 지나 반대편 손절선까지 가려면 청산선을 먼저 지난다).
 * 중심선과 σ 가 매일 움직이니 두 수도 매일 바뀐다 — 「데일리로」의 뜻이다.
 *
 * 못 재면(조건·계열 없음, 창 미달) «—» 다. 사유는 옆 「밴드」 칸이 이미 적는다 —
 * 같은 말을 두 칸에 적지 않는다.
 */
/** 내 다리 레벨의 자릿수 — 서버 `paper.track_leg` 의 `round(r, 4)` 와 **같은 수**여야
 *  한다(적힌 레벨 × DV01 = 적힌 돈). `guards/portfolio-canon.test.ts` 가 둘을 대사한다. */
const LEVEL_DP = 4;

/** 지금 시세를 다시 끌어오는 주기 — 초 단위 피드지만 화면이 그만큼 자주 다시
 *  매길 이유는 없다(한 번에 계열 둘·밴드 둘을 다시 센다). 10초면 눈이 따라간다. */
const LIVE_EVERY_MS = 10_000;

function LevelCell({ track, open }: { track: PaperLegTrack | null; open: boolean }) {
  if (!open || !track || track.exitLevel == null || track.stopLevel == null) {
    return <Text font="legal" as="span" color="fgMuted" tabularNumbers noWrap>{MINUS}</Text>;
  }
  const f = (v: number) => (track.unit === '%' ? v.toFixed(3) : v.toFixed(2));
  const u = track.unit ?? '';
  const series = `계열 ${track.series} 청산 ${f(track.exitLevel)}${u} · 손절 ${f(track.stopLevel)}${u}`;
  /* ★내 다리의 레벨 [OWNER 2026-09-28 — "2년이면 3.xx 에서 얼마, 10년이면 4.xx 에서
     얼마"]. 계열 값이 아니라 **이 계기의 금리**로 적고, 그 레벨에서 걷을 때의
     손익을 옆에 적는다. 가정(나머지 다리는 지금 값에)은 title 이 든다. 내 계기가
     계열의 다리가 아니면 계열 값으로 떨어지고 그 사유를 title 에 적는다. */
  const m = track.mine;
  if (!m) {
    /* 사유는 title 과 **aria-label 둘 다**에 — hover 만이면 키보드·리더에겐 없는
       문장이다(CLAUDE.md 「키보드와 접근성」 5). */
    return (
      <VStack as="span" className="sr-name-stack" alignItems="flex-end"
        title={track.mineWhy ?? undefined} aria-label={track.mineWhy ?? undefined}>
        <Text font="label2" as="span" tabularNumbers noWrap>
          {`청산 ${f(track.exitLevel)}${u}`}
        </Text>
        <Text font="legal" as="span" color="fgMuted" tabularNumbers noWrap>
          {`손절 ${f(track.stopLevel)}${u}`}
        </Text>
      </VStack>
    );
  }
  /* 가정을 문장으로 — 조사는 이름에 붙인다(숫자 뒤 조사는 `josa` 가 못 읽는다). */
  const held = m.others.length
    ? ` — ${m.others.map((o) => `${o.name}${eul(o.name)} ${o.v.toFixed(LEVEL_DP)}에`).join(' · ')} 둔 채 푼 값`
    : '';
  /* 계열의 진입 방향과 반대로 잡은 다리 — 「청산」 레벨이 이 다리엔 손해다.
     사실이라 지우지 않고 ⚠ 로 적는다(색이 아니라 글자 — WCAG 1.4.1). */
  const against = m.aligned === false ? '⚠ 계열 진입 방향과 반대로 잡은 다리예요 — ' : '';
  const said = `${against}${series}${held}`;
  return (
    <VStack as="span" className="sr-name-stack" alignItems="flex-end"
      title={said} aria-label={said}>
      {/* ★자릿수는 서버와 **한 값**(`LEVEL_DP` = `paper.py` 의 round 자리). 적힌 레벨로
          다시 곱해 적힌 돈이 나와야 한다 — 3자리로 접으면 ±50만원이 어긋난다
          (0.0005% × 100 × 1,000만원/bp). IRS 틱이 0.25bp 라 4자리가 맞는 눈금이다.
          `guards/portfolio-canon.test.ts` 가 두 자리를 대사한다. */}
      <Text font="label2" as="span" tabularNumbers noWrap>
        {`${m.aligned === false ? '⚠ ' : ''}청산 ${m.exitLevel.toFixed(LEVEL_DP)} · ${fmtKrw(m.exitPnl)}`}
      </Text>
      <Text font="legal" as="span" color="fgMuted" tabularNumbers noWrap>
        {`손절 ${m.stopLevel.toFixed(LEVEL_DP)} · ${fmtKrw(m.stopPnl)}`}
      </Text>
      {/* ★계열 값도 **병기** [OWNER 2026-09-28 — "계열 값도 병기해줘야지"]. 내 다리
          레벨은 「나머지 다리 고정」이라는 가정 위의 번역이고, 계열의 선은 가정 없는
          원래 문이다 — 둘을 같이 보여야 읽는 사람이 번역을 되짚을 수 있다. 차례는
          위 두 줄과 같다(청산 · 손절). */}
      <Text font="legal" as="span" color="fgMuted" tabularNumbers noWrap>
        {`계열 ${f(track.exitLevel)} · ${f(track.stopLevel)}${u}`}
      </Text>
    </VStack>
  );
}

/**
 * 표의 줄 — **트레이드 머리**와 그 밑의 다리 [OWNER 2026-09-28 — "각 트레이드 별과
 * 포트폴리오 전체에서의 PnL" → "묶음이랑 포트폴리오 전체랑 개별 포지션 간에 위계
 * 고려해서 … 재디자인"].
 *
 * 「트레이드」는 이 데스크의 말로 **묶음**(태그)이다 — BSS 하나가 IRS 페이 + 선물
 * 매수 두 다리다. 묶음 줄이 **자기 다리들 위에** 서고(위계는 위에서 아래로),
 * 포트폴리오 전체는 표가 아니라 위의 사실 스트립이 진다. 묶음이 없는 다리는 제
 * 혼자 트레이드다(머리 줄이 곧 그 다리 — 추적 버튼이 거기 서야 하므로 줄을
 * 생략하지 않는다). 순서는 묶음의 첫 등장 차례다.
 *
 * 합은 서버의 규율 그대로 센다: 한 다리라도 못 매겼으면 합계는 «—»이고, 매겨진
 * 다리만의 소계를 「n/N 매김」으로 따로 적는다(`position.pnl`·`scoredPnl` 의 그 규칙).
 */
type RowItem =
  | { kind: 'leg'; leg: PaperPositionLeg }
  | { kind: 'sum'; group: PaperPositionGroup };

/**
 * 줄 차례 — **트레이드 머리가 자기 다리들 위에** 선다 [OWNER 2026-09-28 — "묶음이랑
 * 포트폴리오 전체랑 개별 포지션 간에 위계 고려해서 … 재디자인"].
 *
 * 종전에는 다리들 뒤에 소계가 붙는 «회계 장부» 차례라 트레이드가 자기 다리 밑에
 * 묻혔다. 위계는 위에서 아래로 읽혀야 한다: 포트폴리오(표 위 사실 스트립) →
 * 트레이드(머리 줄) → 다리(들여쓴 줄). 「포트폴리오 전체」 줄은 표에서 내려가고
 * 스트립이 그 자리다 — 같은 수를 두 곳에 적지 않는다.
 *
 * 차례는 **서버의 묶음 차례**를 따르고 여기서 더하는 수는 없다(§16). 접힌 묶음은
 * 머리 줄만 서고, 묶음이 모르는 다리(있을 수 없지만)는 끝에 세워 안 사라지게 한다.
 */
function groupRows(legs: PaperPositionLeg[], groups: PaperPositionGroup[],
                   collapsed: ReadonlySet<string>): RowItem[] {
  const byN = new Map(legs.map((l) => [l.n, l]));
  const seen = new Set<number>();
  const out: RowItem[] = [];
  for (const g of groups) {
    out.push({ kind: 'sum', group: g });
    for (const n of g.legs) {
      const l = byN.get(n);
      if (!l) continue;
      seen.add(n);
      if (!collapsed.has(g.key)) out.push({ kind: 'leg', leg: l });
    }
  }
  for (const l of legs) if (!seen.has(l.n)) out.push({ kind: 'leg', leg: l });
  return out;
}

/** 계열 값 한 칸 — 계열의 자기 단위(bp 둘째 자리 · % 셋째 자리). */
function seriesWord(v: number | null | undefined, unit: string | null | undefined): string {
  if (v == null) return MINUS;
  return `${unit === '%' ? v.toFixed(3) : v.toFixed(2)}${unit ?? ''}`;
}

/**
 * 포트폴리오 전체 — 표 **위**의 사실 스트립 [OWNER 2026-09-28, 위계].
 *
 * 종전에는 같은 수가 두 곳에 있었다(카드 머리의 한 줄 + 표 맨 아래 「전체」 줄).
 * 위계의 꼭대기는 한 번만 말해야 하고, 이 앱에서 «여러 사실을 한 줄에 눕히는»
 * 문법은 `.sr-stats` + `StatColumn`/`Stat` 하나다(캐논). 전부 서버가 센 수다(§16).
 */
function PortfolioStrip({ p }: { p: PaperSheet['position'] }) {
  const won = (v: number) => fmtKrw(v);
  const near = p.nearest;
  return (
    <HStack className="sr-stats" width="100%" flexWrap="wrap">
      <StatColumn title="손익">
        {p.pnl != null ? (
          <Stat label="합계" value={won(p.pnl)} tone={p.pnl >= 0 ? 'up' : 'down'} />
        ) : (
          <Stat label="매겨진 다리" value={p.scoredPnl == null ? MINUS : won(p.scoredPnl)}
            tone={p.scoredPnl == null ? undefined : p.scoredPnl >= 0 ? 'up' : 'down'}
            note={`${p.scored}/${p.scored + p.pending}다리 · 나머지는 아직이에요`} />
        )}
      </StatColumn>
      <StatColumn title="들고 있는 것">
        <Stat label="트레이드" value={`${p.tradesOpen ?? 0} / ${p.trades ?? 0}`} />
        <Stat label="다리" value={`${p.open} / ${p.open + p.closed}`} />
        <Stat label="명목" value={`${((p.openNotional ?? 0) / 1e8).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}억`} />
      </StatColumn>
      <StatColumn title="금리 민감도">
        <Stat label="순 DV01" value={`${won(p.netDv01)}/bp`} />
        <Stat label="총 DV01" value={`${won(p.grossDv01)}/bp`} />
      </StatColumn>
      <StatColumn title="제일 가까운 문">
        {/* 어느 트레이드가 청산·손절에 먼저 닿는가 — **서버가 고른다**(§16).
            거리가 0 이하면 이미 닿은 것이고, 그건 밴드 칸이 그 줄에서 적는다. */}
        {/* ⚠ 이름을 `label` 에 넣지 말 것 — CDS `caption` 이 **대문자 변환**을 걸어
            「2nd Trader」가 「2ND TRADER」로 렌더된다(실측 2026-09-28 · σ 가 Σ 로
            렌더되던 그 자리와 같은 성질). 이름은 값 아래 `note` 가 진다. */}
        {near ? (
          <Stat label={near.kind === 'stop' ? '손절까지' : '청산까지'}
            value={near.gap <= 0 ? '닿았어요' : `${seriesWord(near.gap, near.unit)} 남음`}
            tone={near.kind === 'stop' ? 'down' : 'up'}
            note={`${near.label}${near.series ? ` · ${near.series}` : ''}`} />
        ) : (
          <Stat label="아직" value={MINUS} note="계열과 조건이 선 묶음이 없어요" />
        )}
      </StatColumn>
    </HStack>
  );
}

function SubtotalRow({ group: g, busy, collapsed, onToggle, onTrace }: {
  group: PaperPositionGroup;
  busy: boolean;
  /** 이 묶음의 다리가 접혀 있는가 — 머리 줄이 그 상태를 지고 토글한다. */
  collapsed: boolean;
  onToggle: () => void;
  onTrace: (ns: number[], title: string) => void;
}) {
  const shown = g.pnl ?? g.scoredPnl;
  const blank = (
    <Text font="legal" as="span" color="fgMuted" noWrap>{MINUS}</Text>
  );
  /* ★묶음 줄은 **계열 값**을 말한다 [OWNER 2026-09-28 — "묶음으로 지금 얼마나
     벌어져있는지 왜 안알려줘?"]. 다리 줄이 다리의 금리(4.145)를 말하면 묶음 줄은
     그 다리들이 이루는 계열(IRC-5Y-10Y 5.0bp)을 말한다 — 내 체결로 만든 진입
     스프레드 · 지금 · Δ · 밴드 · 계열의 청산·손절. 전부 서버가 센다(`group_series`).
     전체 줄은 계열이 하나가 아니라 이 칸들이 없다. */
  const hasSeries = !!g.series && g.now != null;
  const deltaTone = shown == null ? undefined : directionClass(shown);
  return (
    <TableRow style={{ height: ROW_H }} data-sr-trade="">
      <TableCell>
        {/* ★트레이드 이름이 곧 **접기 손잡이**다 [OWNER 2026-09-28, 위계].
            그림 위 onClick 이 아니라 CDS `Pressable as="button"` 이라 탭·엔터가
            그대로 듣고(WCAG §2.1.1), 펼침 상태는 `aria-expanded` 가 진다.
            8개가 넘어가면 다리를 접어 트레이드만 훑는 것이 이 줄의 값어치다. */}
        <Pressable as="button" noScaleOnPress
          onClick={onToggle}
          aria-expanded={!collapsed}
          accessibilityLabel={`${g.label} 다리 ${collapsed ? '펼치기' : '접기'}`}>
          <VStack as="span" className="sr-name-stack" alignItems="flex-start">
            <Text font="label1" as="span" noWrap>
              {`${collapsed ? '▸' : '▾'} ${g.label}`}
            </Text>
            <Text font="legal" as="span" color="fgMuted" noWrap>
              {`${g.legs.length}다리 · 보유 ${g.open}`
                + (g.unconditioned ? ` · 조건 없는 다리 ${g.unconditioned}` : '')}
            </Text>
          </VStack>
        </Pressable>
      </TableCell>
      <TableCell>
        {g.series ? (
          <VStack as="span" className="sr-name-stack" title={g.seriesWhy ?? undefined}>
            <Text font="legal" as="span" color="fgMuted" tabularNumbers noWrap>
              {g.knobs
                ? `${knobWord(g.knobs)}${g.knobsMixed ? ' · 다리마다 달라요' : ''}`
                : '조건 없음'}
            </Text>
            <Text font="legal" as="span" color="fgMuted" noWrap>{g.series}</Text>
          </VStack>
        ) : (
          <Text font="legal" as="span" color="fgMuted" noWrap title={g.seriesWhy ?? undefined}>
            {MINUS}
          </Text>
        )}
      </TableCell>
      <TableCell>
        <TrackCell track={g.track ?? null} open />
      </TableCell>
      <TableCell className="sr-num" justifyContent="flex-end">
        <LevelCell track={g.track ?? null} open />
      </TableCell>
      <TableCell className="sr-num" justifyContent="flex-end">
        {hasSeries && g.myLevel != null ? (
          <VStack as="span" className="sr-name-stack" alignItems="flex-end">
            <Text font="label2" as="span" tabularNumbers noWrap>
              {seriesWord(g.myLevel, g.unit)}
            </Text>
            <Text font="legal" as="span" color="fgMuted" noWrap>
              {g.myBasis === 'fill' ? '내 체결로 만든 스프레드' : `${g.entryT ?? ''} 종가`}
            </Text>
          </VStack>
        ) : blank}
      </TableCell>
      <TableCell className="sr-num" justifyContent="flex-end">
        {hasSeries ? (
          <VStack as="span" className="sr-name-stack" alignItems="flex-end">
            <Text font="label2" as="span" tabularNumbers noWrap color="fgMuted">
              {seriesWord(g.now, g.unit)}
            </Text>
            <Text font="legal" as="span" color="fgMuted" tabularNumbers noWrap>
              {g.asof ? `${g.asof} ${g.live ? '장중' : '종가'}` : ''}
            </Text>
          </VStack>
        ) : blank}
      </TableCell>
      <TableCell className="sr-num" justifyContent="flex-end">
        {hasSeries && g.delta != null ? (
          /* 색은 **손익 부호**를 따른다 — 다리 줄의 Δ 와 같은 규칙. */
          <Text font="label2" as="span" tabularNumbers noWrap className={deltaTone}>
            {`${g.delta >= 0 ? '+' : '−'}${seriesWord(Math.abs(g.delta), g.unit)}`}
          </Text>
        ) : blank}
      </TableCell>
      <TableCell className="sr-num" justifyContent="flex-end">
        <VStack as="span" className="sr-name-stack" alignItems="flex-end">
          <Text font="label2" as="span" tabularNumbers noWrap>
            {g.open ? `순 ${fmtKrw(g.netDv01)}/bp` : MINUS}
          </Text>
          <Text font="legal" as="span" color="fgMuted" tabularNumbers noWrap>
            {g.open ? `총 ${fmtKrw(g.grossDv01)}/bp` : ''}
          </Text>
        </VStack>
      </TableCell>
      <TableCell className="sr-num" justifyContent="flex-end">
        <Text font="label2" as="span" tabularNumbers noWrap color="fgMuted">
          {g.open
            ? `${(g.openNotional / 1e8).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}억`
            : MINUS}
        </Text>
      </TableCell>
      <TableCell className="sr-num" justifyContent="flex-end">
        {/* 합은 서버가 냈다 — 한 다리라도 아직이면 `pnl` 이 null 이고 매겨진
            것만의 소계(`scoredPnl`)를 「n/N 매김」으로 적는다(카드와 같은 규율). */}
        <VStack as="span" className="sr-name-stack" alignItems="flex-end">
          <Text font="label2" as="span" tabularNumbers noWrap
            className={shown == null ? undefined : directionClass(shown)}>
            {shown == null ? MINUS : fmtKrw(shown)}
          </Text>
          <Text font="legal" as="span" color="fgMuted" noWrap>
            {g.pending === 0 ? '트레이드 손익' : `${g.scored}/${g.legs.length} 매김`}
          </Text>
        </VStack>
      </TableCell>
      <TableCell className="sr-num" justifyContent="flex-end">
        {/* ★추적 [OWNER 2026-09-28 — "클릭했을 때 진입일 시점부터 PnL 을 분해"].
            묶음의 다리들을 백테스트 엔진에 실어 분해하는 창을 연다(`TraceWindow`). */}
        <button type="button" className="sr-pillbtn" data-outline=""
          disabled={busy}
          title="이 트레이드의 다리들을 백테스트 엔진에 실어 진입일부터 하루씩 분해해요"
          onClick={() => onTrace(g.legs, g.label)}>
          추적
        </button>
      </TableCell>
    </TableRow>
  );
}

function PositionTable({
  legs, groups, busy, today, exitDateW, exitLevelW, onClose, canAttach, onAttach, onTrace,
}: {
  legs: PaperPositionLeg[];
  /** 묶음(트레이드)들 — **서버가 센 수**(§16). 포트폴리오 전체는 표가 아니라
   *  위의 사실 스트립이 진다(`PortfolioStrip`). */
  groups: PaperPositionGroup[];
  busy: boolean;
  /** 오늘(서울) — 청산일의 기본값이다. **`asof`(자료의 날)가 아니다.** */
  today: string;
  /** 청산 칸 둘의 폭 — **부모가 유도해서 내려준다**. 훅은 행 루프 안에서 못
   *  부르고, 유도에 쓰는 활자 탐침은 화면에 하나면 된다. */
  exitDateW: number;
  exitLevelW: number;
  onClose: (n: number, exit: string, level: number) => void;
  /** 조건 없는 다리에 **아래 담는 줄에 친 조건**을 붙일 수 있는가(다섯이 다
   *  찼는가). 새 컨트롤을 표 안에 만들지 않고 이미 있는 다섯 칸을 쓴다 —
   *  같은 것은 한 번만 만든다(CLAUDE.md 얼라인 8). */
  canAttach: boolean;
  onAttach: (n: number) => void;
  /** 소계 줄의 「추적」 — 그 묶음의 다리 번호들과 제목. */
  onTrace: (ns: number[], title: string) => void;
}) {
  /* 줄마다의 청산 레벨 입력 — 다리 번호로 잡는다(행 순서는 정렬이 바꾼다).
     비워 두면 마지막 종가로 떨어진다(그 사실은 머리의 뜻풀이와 플레이스홀더가
     같이 말한다) — 그래야 「종가로 닫기」라는 종전 동작이 안 사라진다. */
  const [exitLv, setExitLv] = useState<Record<number, string>>({});
  /* 줄마다의 **청산일** 입력 [OWNER 2026-09-23]. 레벨과 같은 문법이다 — 내가
     치고, 비워 두면 오늘로 떨어진다. 종전에는 오늘 고정이라 «어제 청산한 것을
     오늘 적는» 경우를 장부가 받을 수 없었다. 서버는 처음부터 이 날을 받고
     있었고(`check_exit`), 화면만 안 물었다. */
  const [exitT, setExitT] = useState<Record<number, string>>({});
  /* 접힌 묶음 — **화면의 상태**라 서버에 안 간다. 기본은 펼침(보던 그대로)이고,
     트레이드가 많아지면 머리 줄을 눌러 접는다. 브라우저를 새로 고치면 다시
     펼쳐진다 — 어제의 접힘이 오늘 화면을 숨기면 안 된다(`book.ts` 의 그 판단). */
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set<string>());
  const toggle = (key: string) => setCollapsed((prev) => {
    const next = new Set(prev);
    if (!next.delete(key)) next.add(key);
    return next;
  });

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
            {/* ★조건 — 묶음 **오른쪽**이다 [트레이더 2026-09-23 · 자리는 오너].
                「어제 60일/2.5/0.5/3 으로 들어갔는데 오늘 화면은 120/2.5/0/3」
                이라 확인할 수가 없던 자리다. 다리는 그날의 조건으로 들어간 것이고
                Strategy 노브는 오늘 것이라, 장부가 안 들고 있으면 청산선도 손절선도
                딴 선이 된다. */}
            <TableCell as="th" scope="col">
              <ThHelp label="조건"
                help="담을 때 얼린 그날의 조건이에요 — 룩백 · 진입/청산/손절 σ · 진입 규칙. Strategy 화면의 노브가 나중에 바뀌어도 이 값은 안 바뀌어요." />
            </TableCell>
            {/* ★추적 [OWNER 2026-09-23 — "청산이랑 손절 추적할 수 있게"].
                얼린 조건으로 **지금** 닿았는지를 화면이 말한다. 판정은 엔진의
                문을 그대로 옮긴 것이다(손절 > 청산 · 교차선 · 방향은 진입일 z). */}
            <TableCell as="th" scope="col">
              {/* ⚠ 이름이 «지금» 이면 **열이 둘**이 된다 — 옆에 이미 마크를 적는
                  「지금」이 있다(실측 2026-09-23). 이 칸이 말하는 것은 값이
                  아니라 **밴드 위의 자리**라, 그 낱말을 쓴다. */}
              <ThHelp label="밴드"
                help="얼린 조건으로 지금 청산·손절에 닿았는지예요. 계열을 고른 다리에만 서요 — z 는 그 계열의 것이니까요. 판정 규칙은 백테스트 엔진과 같아요." />
            </TableCell>
            {/* ★레벨 [OWNER 2026-09-28] — 밴드 칸의 z 를 계열 값으로 푼 두 선. */}
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <ThHelp label="청산·손절"
                help="얼린 조건의 밴드를 오늘 값으로 푼 뒤, 이 다리의 금리로 옮긴 레벨이에요 — 나머지 다리는 지금 값에 둔 채 이 다리만 움직여 계열이 그 선에 닿는 자리이고, 옆의 돈은 거기서 걷을 때의 이 다리 손익(왕복 비용)이에요. 셋째 줄은 그 원래 문인 계열의 청산 · 손절 값이에요(계열 단위). 중심선과 σ 가 매일 움직이니 매일 바뀌어요. ⚠ 는 계열 진입 방향과 반대로 잡은 다리예요 — 그 「청산」 레벨에서 이 다리는 손해예요. 계열의 다리가 아닌 계기면 계열 값만 적어요." />
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
              <ThHelp label="청산"
                help="날과 레벨 둘 다 내가 적어요 — 진입을 종가로 안 매겼으니까요. 날을 비우면 오늘, 레벨을 비우면 마지막 종가로 닫아요." />
            </TableCell>
          </TableRow>
        </TableHeader>
        <TableBody>
          {groupRows(legs, groups, collapsed).map((item) => {
            if (item.kind === 'sum') {
              return (
                <SubtotalRow key={`sum-${item.group.key}`} group={item.group} busy={busy}
                  collapsed={collapsed.has(item.group.key)}
                  onToggle={() => toggle(item.group.key)}
                  onTrace={onTrace} />
              );
            }
            const l = item.leg;
            return (
            <TableRow key={l.n} style={{ height: ROW_H }} data-sr-leg="">
              <TableCell>
                {/* 다리는 트레이드 **밑**이다 — 들여쓰기와 활자(label2)가 그 위계를
                    진다. 트레이드 머리는 label1 이라 두 층이 한눈에 갈린다. */}
                <VStack as="span" className="sr-name-stack" paddingStart={2}>
                  <Text font="label2" as="span" noWrap>
                    {`${KIND_WORD[l.kind] ?? l.kind} ${l.tenor} ${SIDE_WORD[l.side] ?? l.side}`}
                  </Text>
                  <Text font="legal" as="span" color="fgMuted" noWrap>
                    {l.open ? `${l.entry} 진입` : `${l.entry} → ${l.exit} 청산`}
                  </Text>
                </VStack>
              </TableCell>
              {/* 「묶음」 열은 내려갔다 [2026-09-28, 위계] — 이름은 **바로 위
                  트레이드 머리 줄**이 적는다. 같은 이름을 다리마다 되풀이하면
                  위계가 안 보이고 열만 하나 넓어진다. */}
              <TableCell>
                {/* 조건 없는 다리는 «—» 다 — 「전부 0 으로 들어갔다」가 아니라
                    「안 적었다」이고, 둘은 다른 말이다(서버의 공란 정책). */}
                {l.open && !l.knobs ? (
                  /* ★조건 없는 다리 [OWNER 2026-09-28 — "어디간거임?"]. 09-23 전에
                     담은 다리들은 조건 칸이 없던 때의 것이라 청산선·손절선이 영영
                     못 선다. 「다시 고르기」가 아니라 **빈 칸 적기**라 허용하되,
                     새 입력을 표 안에 만들지 않고 아래 담는 줄의 다섯 칸(과 계열)을
                     그대로 붙인다. 붙인 날은 서버가 적는다(`knobsAt`). */
                  <VStack as="span" className="sr-name-stack">
                    <button type="button" className="sr-pillbtn" data-outline=""
                      disabled={busy || !canAttach}
                      title={canAttach
                        ? '아래 담는 줄에 친 조건 다섯(과 계열)을 이 다리에 붙여요'
                        : '아래 담는 줄의 조건 다섯을 먼저 채워요'}
                      onClick={() => onAttach(l.n)}>
                      조건 붙이기
                    </button>
                    <Text font="legal" as="span" color="fgMuted" noWrap>
                      {l.series ?? ''}
                    </Text>
                  </VStack>
                ) : (
                  <VStack as="span" className="sr-name-stack">
                    <Text font="legal" as="span" color="fgMuted" tabularNumbers noWrap>
                      {l.knobs ? knobWord(l.knobs) : MINUS}
                    </Text>
                    {/* 계열은 조건 **밑에** 적는다 — 그 조건이 무엇 위에서 도는지가
                        한 칸 안에서 읽혀야 한다. 뒤에 붙인 조건이면 그 날도 같이 —
                        「그날의 조건」이 아니라는 사실을 읽는 사람이 알아야 한다. */}
                    <Text font="legal" as="span" color="fgMuted" noWrap>
                      {[l.series ?? '', l.knobsAt ? `${l.knobsAt} 붙임` : '']
                        .filter(Boolean).join(' · ')}
                    </Text>
                  </VStack>
                )}
              </TableCell>
              <TableCell>
                <TrackCell track={l.track} open={l.open} />
              </TableCell>
              <TableCell className="sr-num" justifyContent="flex-end">
                <LevelCell track={l.track} open={l.open} />
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
                    {/* 장중 레벨로 덮인 마크는 **종가가 아니다** — 낱말이 그걸 말해야
                        다음 사람이 이 수를 종가로 읽지 않는다 [OWNER 2026-09-28]. */}
                    {!l.open || !l.markT ? ''
                      : l.live ? `${l.markT} 장중`
                        : l.markT !== l.entry ? `${l.markT} 종가` : ''}
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
                {/* ★**내가 적는 청산 레벨** [OWNER 2026-09-22 — "내가 적는 청산
                    레벨까지 하고 푸시하세요"]. 종전에는 마지막 종가로 닫는 버튼
                    하나뿐이었고, 그래서 한 거래 안에 「진입은 내 체결가 · 청산은
                    종가」라는 **두 규약**이 섰다. 진입 칸과 같은 문법이다 —
                    내가 치고, 비워 두면 서버가 아는 값으로 떨어진다.

                    ★**청산일도 그렇다** [OWNER 2026-09-23]. 종전에는 오늘 고정이라
                    「어제 청산한 것을 오늘 적는」 경우를 못 받았다. 이제 두 칸이다.

                    `.sr-numctl` — 숫자 칸의 우측정렬 규칙(`theme/type.css` 의 그
                    블록)이 값뿐 아니라 **컨트롤까지 밀어** 제 상자를 뚫고 나가게
                    한다. 컨트롤이 하나일 때는 안 보였고, 둘이 서자 **115px 이
                    겹쳤다**(실측 2026-09-23). 이 클래스가 그 줄만 되돌린다. */}
                {l.open ? (
                  <HStack className="sr-numctl" gap={0.5}
                    alignItems="center" justifyContent="flex-end">
                    {/* 날이 먼저다 — 「언제 · 얼마에」 차례로 읽힌다. 담는 줄의
                        체결일과 **같은 문법**이다(맨 텍스트 칸 + 오늘이 힌트):
                        이 화면은 날짜를 어디서나 ISO 로 치므로 둘이 달라지면
                        같은 일을 두 벌로 배우게 된다. */}
                    <Box width={exitDateW}>
                      <TextInput size="s" fontSize="legal" height={CONTROL_H}
                        accessibilityLabel={`${l.n}번 다리 청산일 (YYYY-MM-DD)`}
                        value={exitT[l.n] ?? ''}
                        placeholder={today}
                        disabled={busy}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          setExitT((m) => ({ ...m, [l.n]: e.target.value }))}
                      />
                    </Box>
                    <Box width={exitLevelW}>
                      <TextInput size="s" fontSize="legal" height={CONTROL_H}
                        accessibilityLabel={`${l.n}번 다리 청산 레벨 (%)`}
                        value={exitLv[l.n] ?? ''}
                        placeholder={l.mark == null ? '레벨' : l.mark.toFixed(3)}
                        disabled={busy}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          setExitLv((m) => ({ ...m, [l.n]: e.target.value }))}
                      />
                    </Box>
                    <button type="button" className="sr-pillbtn" data-fill=""
                      /* 비워 두면 마지막 종가로 떨어진다 — 그 값조차 없으면
                         적을 수가 없으므로 그때만 못 누른다.

                         **날짜는 여기서 안 막는다.** 레벨을 막는 이유는 화면이
                         `Number()` 로 **바꾸기** 때문이다(못 바꾸면 `null` 이
                         서버에 가서 뜻 모를 오류가 된다). 날짜는 친 글자가 그대로
                         가고, 서버가 사유를 한국어로 적어 돌려준다 —
                         「미래예요」·「체결일보다 앞서요」는 꼴만 봐서는 못 하는
                         판정이라 여기서 흉내 내면 규칙이 두 벌이 된다. */
                      disabled={busy || (!exitLv[l.n]?.trim() && l.mark == null)
                                || (!!exitLv[l.n]?.trim() && !Number.isFinite(Number(exitLv[l.n])))}
                      onClick={() => {
                        const typed = exitLv[l.n]?.trim();
                        onClose(l.n, exitT[l.n]?.trim() || today,
                                typed ? Number(typed) : (l.mark as number));
                        setExitLv((m) => ({ ...m, [l.n]: '' }));
                        setExitT((m) => ({ ...m, [l.n]: '' }));
                      }}>
                      닫기
                    </button>
                  </HStack>
                ) : (
                  /* 닫힌 다리의 **레벨은 「지금」 칸이 이미 적는다** — 여기서 또
                     적으면 한 줄에 같은 수가 둘이 선다. 여기는 날짜만. */
                  <Text font="legal" as="span" color="fgMuted" noWrap>
                    {l.exit ?? MINUS}
                  </Text>
                )}
              </TableCell>
            </TableRow>
            );
          })}
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
  /** ★계열 — **묶음과 다른 칸**이다 [OWNER 2026-09-23]. 묶음은 부르는 이름이라
   *  산술에 안 쓰고(그 칸 도움말의 규칙), 추적은 계열의 z 로 하므로 이 칸이
   *  있어야 청산·손절이 선다. 안 고르면 조건만 적히고 추적은 안 한다. */
  const [legSeries, setLegSeries] = useState('');
  /** ★그날의 조건 [트레이더 2026-09-23]. **다섯이 다 차야 같이 간다** — 서버가
   *  반쪽을 거절하고(「룩백만 적힌」 다리는 청산선을 못 그린다), 하나도 안 치면
   *  조건 없는 다리다(종전 동작이 기본값으로 산다).
   *
   *  기본값을 안 넣는 이유: 넣으면 **안 친 조건이 적힌 다리**가 생기고, 그건
   *  「안 적었다」가 아니라 거짓이 된다. 빈 칸은 빈 칸이다. */
  const [knobLb, setKnobLb] = useState('');
  const [knobEntryZ, setKnobEntryZ] = useState('');
  const [knobExitZ, setKnobExitZ] = useState('');
  const [knobStopZ, setKnobStopZ] = useState('');
  const [knobMode, setKnobMode] = useState<'level' | 'touch'>('level');
  /** 초기화 한 번 더 묻기 — 화면의 문이고, 서버가 확인 낱말로 둘째 문을 진다. */
  const [resetArm, setResetArm] = useState(false);
  /** 열린 추적 창 — 묶음(트레이드) 하나의 다리 번호들 [OWNER 2026-09-28]. */
  const [trace, setTrace] = useState<{ ns: number[]; title: string }>();
  /** ★**장중 레벨** [OWNER 2026-09-28 — "지금 2년은 4.06, 5년은 4.27, 10년은 4.3375"].
   *  이 장부의 마크는 종가인데 데스크는 장중에 산다 — 연휴 뒤 첫날처럼 종가가 아직
   *  없는 날 장부는 사흘 전 수에 묶인다. 지금 보는 금리를 치면 **서버가** 그 값으로
   *  다시 매겨 보낸다(§16 — 화면은 글자를 보내고 수를 받는다). 장부엔 안 적힌다.
   *  열쇠는 `계기:만기` 이고 값은 친 글자 그대로다(빈 칸은 안 보낸다). */
  const [liveLv, setLiveLv] = useState<Record<string, string>>({});
  /** ★**지금 시세를 그대로** [OWNER 2026-09-28 — "장중에 CRS IRS 종합이랑 3년국채,
   *  10년국채선물 떠있는거 보고 바로바로 입력해주면 안되나?"]. 그 화면들이 이미
   *  DB 로 초 단위로 들어오고 있다(`/api/paper/live`) — 눌러서 칸을 채우고, 켜 두면
   *  `LIVE_EVERY_MS` 마다 다시 채운다. 매기는 것은 그대로 `?marks=` 한 길이라
   *  산술이 두 벌이 되지 않고, 넣은 수가 칸에 **보이므로** 고칠 수도 있다. */
  /** ★기본이 **장중**이다 [OWNER 2026-09-28 — "따로 내가 입력 안해도 되게 그냥
   *  1년부터 10년까지 자동으로 다 넣어주고, 지금 들어가고 있다는 거만 명시"].
   *  서버가 `marks=live` 한 낱말로 IRS 전 만기와 국채선물을 통째로 깔고, 칸에 친
   *  값이 있으면 그 칸만 덮는다. 시세를 못 읽으면 조용히 종가로 선다. */
  const [autoLive, setAutoLive] = useState(true);
  const [liveAt, setLiveAt] = useState<string>();
  const [liveWhy, setLiveWhy] = useState<string>();
  /** 지금 시세 — **칸의 플레이스홀더**로만 쓴다(치는 값을 덮지 않게). */
  const [liveNow, setLiveNow] = useState<Record<string, number>>({});
  /** 장중이면 이 수가 올라 장부를 다시 묻는다(시세는 움직이는데 질의는 그대로다). */
  const [liveTick, setLiveTick] = useState(0);

  /** 장중 레벨을 물을 계기들 — **들고 있는 다리**에서 나온다(차례는 표의 차례).
   *  마크는 그 칸의 플레이스홀더가 되어 「종가는 이거였다」를 같이 말한다.
   *  훅보다 **앞에** 둔다 — 지금 시세를 끌어올 때 이 목록이 있어야 「이 북이 쥔
   *  계기만」 채울 수 있다(첫 판은 칸이 비어 있어 아무것도 안 채워졌다). */
  const liveKinds = (() => {
    const seen = new Map<string, { key: string; label: string; mark: number | null }>();
    for (const l of sheet?.position.legs ?? []) {
      if (!l.open) continue;
      const key = `${l.kind}:${l.tenor}`;
      if (!seen.has(key)) {
        seen.set(key, { key, label: `${KIND_WORD[l.kind] ?? l.kind} ${l.tenor}`, mark: l.mark });
      }
    }
    return [...seen.values()];
  })();

  /* ── 칸 폭은 **옵션 집합의 합집합**에서 [OWNER 2026-09-23] ─────────────────
     진단에서 이 줄의 **열두 칸이 전부** T1(죽은 폭 ≤16px)을 실패했다(21~130px).
     계기를 바꾸면 만기·방향 목록이 따라 바뀌므로 **모든 계기의 목록을 합쳐서**
     잰다 — 그래야 고를 때 칸이 안 움직인다. 폴백은 종전 상수 그대로다. */
  const [fontProbe, ctlFont] = useControlFont();
  const allKinds = inst?.kinds ?? [];
  const kindW = fitWidth('select', allKinds.map((k) => k.label), ctlFont, 130);
  const tenorW = fitWidth('select', allKinds.flatMap((k) => k.tenors), ctlFont, 110);
  const sideW = fitWidth('select', allKinds.flatMap((k) => k.sides.map((d) => d.label)),
                         ctlFont, 140);
  const rateW = fitWidth('input', ['9.9999'], ctlFont, 130);
  const sizeW = fitWidth('input', ['9,999.9'], ctlFont, 140);
  const dateW = fitWidth('input', ['2026-09-23'], ctlFont, 140);
  const tagW = fitWidth('input', ['BSS 2Y 스티프너'], ctlFont, 150);
  const lbW = fitWidth('input', ['600'], ctlFont, 92);
  const zW = fitWidth('input', ['20.0'], ctlFont, 78);
  const modeW = fitWidth('select', ['이탈 즉시', '밴드 복귀'], ctlFont, 132);
  const seriesW = fitWidth(
    'select',
    ['안 함', ...(inst?.series ?? []).map((x) => x.label)],
    ctlFont,
    150,
  );
  /** 장중 레벨 칸의 폭 — 금리는 네 자리까지 친다(4.3375). */
  const liveW = fitWidth('input', ['9.9999'], ctlFont, 96);
  /* 표 **안**의 청산 칸 둘 — 오늘 넣은 칸이고 손 상수였다. 날짜는 열 글자라
     104 로는 글자 자리가 모자랐다(70 < 73.2). 같은 규칙으로 유도한다. */
  const exitDateW = fitWidth('input', ['2026-09-23'], ctlFont, 104);
  const exitLevelW = fitWidth('input', ['9.999'], ctlFont, 92);

  /**
   * 친 조건 → 보낼 것.
   *
   * **다 비면 `undefined`**(조건 없는 다리 — 종전 동작). **하나라도 차 있으면
   * 친 것을 그대로 보낸다** — 반쪽이면 서버가 「빠진 것: exitZ」라고 사유를
   * 적는다.
   *
   * ★반쪽을 화면에서 조용히 버리지 않는 이유: 룩백만 치고 청산σ를 깜빡한
   * 사람에게 조건 **없는** 다리가 담기면, 화면은 「담았어요」라고 적고 장부에는
   * 안 적힌 조건이 남는다. 안 한 일을 했다고 적는 것이 이 장부에서 제일 나쁜
   * 결함이다(`close_leg` 의 그 규율과 같은 자리).
   *
   * ⚠ 숫자로 **안 바꾸고 글자 그대로** 보낸다. `Number('')` 은 `0` 이라 빈
   * 칸이 「0σ 로 들어갔다」가 되고, `Number('삼')` 은 `NaN` → JSON `null` 이라
   * 사유가 「빠졌다」로 바뀐다. 서버가 파싱해야 「숫자가 아니에요: '삼'」을
   * 말할 수 있다.
   */
  const knobs = (() => {
    const raw = [knobLb, knobEntryZ, knobExitZ, knobStopZ].map((v) => v.trim());
    if (raw.every((v) => !v)) return undefined;
    const put = (v: string) => (v ? v : undefined);
    return {
      lookback: put(raw[0]),
      entryZ: put(raw[1]),
      exitZ: put(raw[2]),
      stopZ: put(raw[3]),
      entryMode: knobMode,
    };
  })();

  useEffect(() => {
    /* 한 번만 읽는다 — 계기 목록은 하루에 안 바뀐다. 실패해도 화면은 서고,
       폼만 「계기를 못 읽었어요」로 잠긴다(조용히 빈 목록을 그리지 않는다). */
    fetchInstruments().then(setInst).catch(() => setInst(undefined));
  }, []);

  /** 보낼 장중 레벨 — `irs:5Y=4.27;irs:10Y=4.3375`. 빈 칸과 숫자가 아닌 글자는
   *  안 보낸다(서버가 422 로 거절하는 대신 화면이 그 칸만 조용히 종가로 둔다 —
   *  치는 중인 글자마다 붉은 줄이 서면 못 친다). */
  const typedMarks = Object.entries(liveLv)
    .filter(([, v]) => v.trim() !== '' && Number.isFinite(Number(v)))
    .map(([k, v]) => `${k}=${Number(v)}`)
    .sort()
    .join(';');
  /** 서버로 가는 것 — `live` 한 낱말이 **지금 시세를 통째로** 깔고, 친 칸이 덮는다. */
  const marksSpec = [autoLive ? 'live' : '', typedMarks].filter(Boolean).join(';');

  /** 한 번 끌어와 칸을 채운다 — 값은 **칸에 보이고**, 매기는 것은 `?marks=` 가 한다. */
  const pullLive = useCallback(async () => {
    try {
      const got = await fetchLive();
      const next: Record<string, number> = {};
      for (const l of got.levels) next[`${l.kind}:${l.tenor}`] = l.level;
      /* 칸을 **채우지 않는다** — 플레이스홀더로만 보여 준다. 채우면 트레이더가
         치는 중에 10초마다 글자가 덮이고, 그때 친 값이 어디 갔는지 알 수 없다. */
      setLiveNow(next);
      setLiveAt(got.asof ?? undefined);
      setLiveWhy(got.why ?? got.sources.find((x) => x.why && x.table)?.why ?? undefined);
    } catch (e: unknown) {
      setLiveWhy(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    if (!autoLive) {
      setLiveAt(undefined);
      setLiveNow({});
      return undefined;
    }
    void pullLive();
    const id = setInterval(() => {
      void pullLive();
      setLiveTick((t) => t + 1);          // 시세가 움직이면 장부도 다시 묻는다
    }, LIVE_EVERY_MS);
    return () => clearInterval(id);
  }, [autoLive, pullLive]);

  const load = useCallback(() => {
    setError(undefined);
    setUnavailable(false);
    fetchPaper(marksSpec || undefined)
      .then(setSheet)
      .catch((e: unknown) => {
        if (e instanceof BacktestUnavailable) setUnavailable(true);
        else setError(e instanceof Error ? e.message : String(e));
      });
  }, [marksSpec]);

  useEffect(() => {
    /* 자판이 멈춘 뒤에 묻는다 — 한 글자마다 한 번씩 물으면 서버가 계열을 그만큼 읽는다. */
    const t = setTimeout(load, typedMarks ? 350 : 0);
    return () => clearTimeout(t);
  }, [load, typedMarks, liveTick]);


  /* 쓰기 한 벌 — 응답이 곧 새 장부라 다시 묻지 않는다. */
  const write = useCallback((run: () => Promise<PaperSheet>, ok: string) => {
    setBusy(true);
    setNote(undefined);
    run()
      .then((s) => {
        setSheet(s);
        setNote(ok);
        /* 쓰기 응답은 **종가로** 매겨져 온다(쓰기 라우트는 장중 레벨을 안 받는다 —
           장부는 체결과 종가만 안다). 장중으로 보고 있었으면 다시 물어 덮는다. */
        if (marksSpec) load();
      })
      .catch((e: unknown) => setNote(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  }, [marksSpec, load]);

  /* ── 그날의 1등 [OWNER 2026-09-23 — "들어간 시점에서의 최적 파라미터로"] ──
     선택지에서 **「손으로 치되 1등을 제안」**을 고르셨다. 그래서 이 줄은 고르지
     않는다 — 계열과 체결일이 서면 그 계열을 **진입일까지의 자료로** 격자에 돌린
     1등을 담는 줄 아래에 적을 뿐이고, 담기는 것은 여전히 위 칸에 친 값이다.
     「채택」 버튼을 두지 않는 것이 설계다: 그 버튼이 있으면 이 줄은 제안이 아니라
     기본값이 되고, 「1등」은 고르라는 말로 읽힌다(PBO 레인의 경고 — 문장은
     `suggestLine` 이 늘 같이 세우고, `guards/paper-suggest.test.ts` 가 잰다).

     격자 한 바퀴가 2~3초(퓨처스왑 9초)라 **체결일을 다 친 뒤**(열 글자 꼴)에만
     묻고, 자판이 멈춘 뒤 잠깐 기다린다. 같은 (계열·날)은 서버가 기억한다. */
  const [suggest, setSuggest] = useState<PaperSuggest>();
  const [suggestBusy, setSuggestBusy] = useState(false);
  const [suggestFailed, setSuggestFailed] = useState<string>();
  const entryTyped = legEntry.trim();
  const entryReady = entryTyped === '' || /^\d{4}-\d{2}-\d{2}$/.test(entryTyped);
  const suggestEntry = entryReady ? (entryTyped || sheet?.today) : undefined;
  useEffect(() => {
    setSuggest(undefined);
    setSuggestFailed(undefined);
    if (!legSeries || !suggestEntry) {
      setSuggestBusy(false);
      return undefined;
    }
    const ctl = new AbortController();
    const timer = setTimeout(() => {
      setSuggestBusy(true);
      fetchSuggest(legSeries, suggestEntry, ctl.signal)
        .then((s) => {
          if (!ctl.signal.aborted) setSuggest(s);
        })
        .catch((e: unknown) => {
          if (ctl.signal.aborted) return;
          /* 404 = 라우트를 모르는 **옛 백엔드**. 조용히 빈 줄을 두면 「제안이
             없는 날」과 구별이 안 된다 — 규약이 어긋난 채 배포하면 조용히
             사라진다(인계문의 그 규칙: 백엔드 재기동이 먼저, 프런트 푸시가 뒤). */
          setSuggestFailed(e instanceof BacktestUnavailable
            ? '백엔드가 이 라우트를 몰라요 — 새 판으로 재기동해야 해요.'
            : e instanceof Error ? e.message : String(e));
        })
        .finally(() => {
          if (!ctl.signal.aborted) setSuggestBusy(false);
        });
    }, 350);
    return () => {
      clearTimeout(timer);
      ctl.abort();
    };
  }, [legSeries, suggestEntry]);


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
          {/* ★장중으로 보고 있으면 **그 사실이 먼저** 선다 [OWNER 2026-09-28] —
              이 수는 종가가 아니고 장부에도 없다. 되돌리는 손잡이가 같이 있어야
              한 번 친 값에 갇히지 않는다. */}
          {/* ★지금 무엇으로 보고 있는지를 **한 칸으로** 적는다 [OWNER 2026-09-28 —
              "지금 들어가고 있다는 거만 명시해주기"]. 열아홉 칸을 늘어놓으면 조건
              바가 시세표가 된다 — 몇 칸이 들어갔는지와 그 시각이면 충분하고,
              무엇이 들어갔는지는 표의 「지금」 칸이 줄마다 적는다. */}
          {sheet.live?.length ? (
            <>
              <Cond k="지금 보는 값"
                v={`장중 ${liveAt ?? ''} 시세 · ${sheet.live.length}칸 들어가는 중`} strong />
              <button type="button" className="sr-pillbtn" data-outline=""
                disabled={busy}
                onClick={() => { setAutoLive(false); setLiveLv({}); }}>
                종가로 보기
              </button>
            </>
          ) : (
            <>
              <Cond k="지금 보는 값" v={`종가 ${sheet.asof ?? ''}`} />
              <button type="button" className="sr-pillbtn" data-outline=""
                disabled={busy}
                onClick={() => setAutoLive(true)}>
                장중으로 보기
              </button>
            </>
          )}
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
              <Text font="legal" as="span" color="fgMuted" noWrap>
                포트폴리오 → 트레이드 → 다리 차례예요 — 트레이드 이름을 누르면 다리를 접어요.
              </Text>
            </HStack>
          </HStack>
          {/* ★위계의 꼭대기 — 포트폴리오 전체는 **표 위 한 줄**이다 [OWNER
              2026-09-28]. 종전에는 이 카드 머리와 표 맨 아래 「전체」 줄에 같은
              수가 두 번 있었다. */}
          <Box paddingX={2} paddingBottom={1}>
            <PortfolioStrip p={sheet.position} />
          </Box>
          {/* ★장중 레벨 줄 [OWNER 2026-09-28 — "지금 2년은 4.06, 5년은 4.27,
              10년은 4.3375"]. 칸은 **이 북이 실제로 들고 있는 계기**에서 나온다 —
              화면이 만기 목록을 손으로 적으면 안 쥔 만기 칸이 생긴다. 친 값은
              서버로 가고(§16) 장부엔 안 적힌다. */}
          {liveKinds.length > 0 ? (
            <HStack paddingX={2} paddingBottom={1} gap={GAP.field}
              alignItems="flex-end" flexWrap="wrap">
              <Text font="caption" as="span" color="fgMuted" noWrap
                style={{ alignSelf: 'center' }}>
                {autoLive ? '장중 레벨 (%) — 안 치면 지금 시세' : '장중 레벨 (%)'}
              </Text>
              {liveKinds.map((k) => (
                <Box key={k.key} width={liveW}>
                  <Field label={k.label}
                    help="지금 보는 금리를 치면 그 값으로 다시 매겨요 — 종가가 아니고 장부에도 안 적혀요. 비우면 종가로 돌아가요.">
                    <TextInput size="s" fontSize="legal" height={CONTROL_H}
                      accessibilityLabel={`${k.label} 장중 레벨 (%)`}
                      value={liveLv[k.key] ?? ''}
                      /* 플레이스홀더가 **지금 들어가고 있는 값**이다 — 장중이면 그
                         시세, 아니면 그 계기의 종가. 치면 그 칸만 덮는다. */
                      placeholder={
                        (autoLive ? liveNow[k.key] : undefined)?.toFixed(4)
                        ?? (k.mark == null ? '레벨' : k.mark.toFixed(4))
                      }
                      disabled={busy}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        setLiveLv((m) => ({ ...m, [k.key]: e.target.value }))}
                    />
                  </Field>
                </Box>
              ))}
              {/* ★지금 시세 — 켜 두면 초 단위로 들어오는 그 값으로 칸이 다시 찬다.
                  한 번 눌러 채우고 다시 누르면 멈춘다(켜 둔 채 값을 고쳐도 다음
                  갱신이 덮으므로, 손으로 칠 때는 꺼 두는 것이 맞다). */}
              {liveAt && autoLive ? (
                <Text font="legal" as="span" color="fgMuted" noWrap style={{ alignSelf: 'center' }}>
                  {`인포맥스 ${liveAt} 시세가 ${LIVE_EVERY_MS / 1000}초마다 들어가는 중이에요`}
                </Text>
              ) : null}
              {liveWhy ? (
                <Text font="legal" as="span" color="fgMuted" style={{ alignSelf: 'center' }}>
                  {`${MINUS} ${liveWhy}`}
                </Text>
              ) : null}
            </HStack>
          ) : null}
          <PositionTable
            legs={sheet.position.legs}
            groups={sheet.position.groups ?? []}
            busy={busy}
            today={sheet.today}
            exitDateW={exitDateW}
            exitLevelW={exitLevelW}
            canAttach={knobsComplete(knobs)}
            onAttach={(n) =>
              write(() => attachKnobs(n, knobs ?? {}, legSeries || undefined),
                    `${n}번 다리에 조건을 붙였어요 — 붙인 날이 장부에 남아요.`)}
            onTrace={(ns, title) => setTrace({ ns, title })}
            onClose={(n, exit, level) =>
              /* 날도 레벨도 **내가 적은 것**이 그대로 간다 — 둘 다 비면 표가
                 오늘·마지막 종가로 채워서 넘긴다(종전 동작). 말이 되는 날인지는
                 서버의 `check_exit` 가 본다: 미래 금지 · 체결일보다 앞서기 금지 ·
                 **같은 날은 허용**(오늘 열고 오늘 닫는 거래는 정상이다). */
              write(() => closeLeg(n, exit, level),
                    `${n}번 다리를 ${exit} 에 닫았어요.`)}
          />
          {/* 담는 줄 — 얼라인 캐논 그대로(라벨 위 · 32px 등고 · 바닥 정렬 ·
              폭은 감싸는 Box 가 준다). */}
          {/* ★접히는 단위는 **묶음**이다 [OWNER 2026-09-23 · T4]. 칸이 열넷이라
              1440 에서도 접히는데, 평평한 목록이면 끝의 요소 하나가 혼자 선다
              (Playwright 가드가 그것을 잡았다). 넷으로 묶는다 —
              무엇을(계기·만기·방향) / 얼마에·얼마나(체결금리·크기기준·명목) /
              언제·무엇으로(체결일·묶음) / 그날의 조건(다섯 + 담기).
              담기 버튼은 **마지막 묶음 안**이다: 혼자 두면 그 버튼이 또 혼자 선다.
              ⚠ 틈은 안 바꾼다 — 묶음 사이도 12px(09-02 의 그 결정). */}
          <HStack gap={GAP.field} alignItems="flex-end" paddingX={2} paddingBottom={0.5}
            flexWrap="wrap">
            <HStack gap={GAP.field} alignItems="flex-end">
            <Box width={kindW}>
              {fontProbe}
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
            <Box width={tenorW}>
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
            <Box width={sideW}>
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
            </HStack>
            <HStack gap={GAP.field} alignItems="flex-end">
            <Box width={rateW}>
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
            {/* ⚠ 이 칸은 **유도로 안 옮긴다** [실측 2026-09-23]. 죽은 폭이 27.5px
                (T1 초과)인 건 맞지만, `Segmented` 의 알약은 `.sr-ctlfont`
                (14px/600)를 쓰고 컨트롤 **값**은 13px/400 이다 — 값 폰트로 재서
                상자를 121 로 좁혔더니 알약 합(122.5)이 **상자를 1.5px 넘었다**.
                제대로 하려면 알약용 탐침이 하나 더 있어야 하고, 그건 이 회차의
                범위 밖이다. 150 을 그대로 둔다(넘치는 것보다 남는 게 낫다). */}
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
            <Box width={sizeW}>
              <Field label={sizeMode === 'notional' ? '명목(억)' : 'DV01(만원/bp)'}>
                <TextInput size="s" fontSize="legal" height={CONTROL_H}
                  accessibilityLabel={sizeMode === 'notional' ? '명목 (억)' : 'DV01 (만원/bp)'}
                  value={sizeVal}
                  placeholder={sizeMode === 'notional' ? '100' : '295'}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSizeVal(e.target.value)}
                />
              </Field>
            </Box>
            </HStack>
            <HStack gap={GAP.field} alignItems="flex-end">
            <Box width={dateW}>
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
            <Box width={tagW}>
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
            {/* ★그날의 조건 다섯 [트레이더 2026-09-23]. 이 줄은 `flexWrap` 이라
                좁으면 둘째 줄로 접힌다 — 칸이 열둘이 되는 자리고, 접히는 것이
                줄이는 것보다 낫다(「낱말 중간 줄바꿈 금지」 5 와 같은 규율).
                라벨 위 · 32px 등고 · 바닥 정렬은 형제와 같다. */}
            </HStack>
            <HStack gap={GAP.field} alignItems="flex-end">
            <Box width={seriesW}>
              <Field label="계열"
                help="이 다리가 속한 계열이에요. 고르면 얼린 조건으로 청산·손절이 닿았는지 화면이 말해요 — 안 고르면 조건만 적히고 추적은 안 해요.">
                <Select size="s" font="legal" styles={DROPDOWN_STYLES}
                  accessibilityLabel="계열"
                  value={legSeries || NO_SERIES}
                  onChange={(v: unknown) => {
                    const id = String(v ?? NO_SERIES);
                    setLegSeries(id === NO_SERIES ? '' : id);
                  }}
                  options={[
                    { value: NO_SERIES, label: '안 함' },
                    ...(inst?.series ?? []).map((x) => ({ value: x.id, label: x.label })),
                  ]}
                />
              </Field>
            </Box>
            <Box width={lbW}>
              <Field label="룩백 (일)"
                help="이 다리를 담을 때의 조건이에요. 다섯을 다 채우면 같이 얼고, 하나라도 비면 조건 없는 다리로 담겨요.">
                <TextInput size="s" fontSize="legal" height={CONTROL_H}
                  accessibilityLabel="룩백 (일)"
                  value={knobLb} placeholder="120"
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setKnobLb(e.target.value)}
                />
              </Field>
            </Box>
            <Box width={zW}>
              <Field label="진입 σ">
                <TextInput size="s" fontSize="legal" height={CONTROL_H}
                  accessibilityLabel="진입 σ"
                  value={knobEntryZ} placeholder="2.5"
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setKnobEntryZ(e.target.value)}
                />
              </Field>
            </Box>
            <Box width={zW}>
              <Field label="청산 σ">
                <TextInput size="s" fontSize="legal" height={CONTROL_H}
                  accessibilityLabel="청산 σ"
                  value={knobExitZ} placeholder="0.5"
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setKnobExitZ(e.target.value)}
                />
              </Field>
            </Box>
            <Box width={zW}>
              <Field label="손절 σ">
                <TextInput size="s" fontSize="legal" height={CONTROL_H}
                  accessibilityLabel="손절 σ"
                  value={knobStopZ} placeholder="3"
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setKnobStopZ(e.target.value)}
                />
              </Field>
            </Box>
            <Box width={modeW}>
              <Field label="진입 규칙">
                {/* 낱말은 MR 화면의 그것이다 — 두 화면이 같은 규칙을 다르게
                    부르면 어제 다리와 오늘 노브를 못 잇는다. */}
                <Select size="s" font="legal" styles={DROPDOWN_STYLES}
                  accessibilityLabel="진입 규칙"
                  value={knobMode}
                  onChange={(v: unknown) =>
                    setKnobMode(String(v ?? 'level') as 'level' | 'touch')}
                  options={[
                    { value: 'level', label: '이탈 즉시' },
                    { value: 'touch', label: '밴드 복귀' },
                  ]}
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
                    ...(knobs ? { knobs } : {}),
                    ...(legSeries ? { series: legSeries } : {}),
                  }),
                  `${KIND_WORD[legKind]} ${legTenor} ${SIDE_WORD[legSide] ?? legSide}${
                    eul(SIDE_WORD[legSide] ?? legSide)} 담았어요.`);
              }}
            >
              다리 담기
            </button>
            </HStack>
          </HStack>
          {legSeries ? (
            /* 그날 1등 — 담는 줄 **아래** 한 줄. 컨트롤이 아니라 글이라 폭 유도가
               없고, 계열을 안 고르면 아예 없다(담는 줄 e2e 가 재는 기하는 그대로다).
               문장 전체는 `suggestLine` 이 만든다 — 경고가 빠진 갈래가 없게. */
            <Box paddingX={2}>
              <Text font="legal" as="span" color="fgMuted" maxWidth={760}>
                {suggestLine({
                  label: inst?.series?.find((x) => x.id === legSeries)?.label ?? legSeries,
                  entryReady,
                  busy: suggestBusy,
                  failed: suggestFailed,
                  got: suggest,
                  knobs,
                })}
              </Text>
            </Box>
          ) : null}
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
      {/* 트레이드 추적 창 [OWNER 2026-09-28] — 소계 줄의 「추적」이 연다. */}
      {trace ? (
        <TraceWindow ns={trace.ns} title={trace.title} onClose={() => setTrace(undefined)} />
      ) : null}
    </VStack>
  );
}
