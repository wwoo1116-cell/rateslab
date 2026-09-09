'use client';

/* Mean Reversion — BSS 전 테너 밴드 위치 랭킹 (Strategy 둘째 세입자, 2026-08-25).
 *
 * **측정이지 신호가 아니다.** 사전등록 검증(Desktop\bollinger-mr, 누적 108구성)이
 * 「볼린저 재진입」 신호 문법을 NO-GO 로 닫았고(REPORT.md), 이 화면은 그 결론
 * 위에 선다: 본드스왑 스프레드(국고 − IRS) 전 테너가 평소 밴드(SMA ± σ배수,
 * 룩백·폭은 근거 있는 선택지 — MR_WINDOWS·MR_KS) 대비 어디에 있는지를 재서
 * 늘어난 순서로 세울 뿐이다. 진입·청산·추천 문구는 없다 — Credit RV 의
 * 「랭킹이지 투자판단이 아니다」와 같은 명구 의무.
 *
 * **유니버스는 세 번 넓어졌다** — BSS 전 테너 아홉(2026-08-25) → 국채선물
 * 내재금리·퓨처스왑 넷(같은 날) → **IRS 커브·플라이 열둘**(2026-09-09
 * [OWNER — "스프레드(버터플라이나 커브와 같은 것도 연결해주기)"]). 25행이고,
 * 조합 목록은 이 리포의 주요 세트를 그대로 읽는다 — 근거는 backend/app/mr.py.
 *
 * **트리거 한 줄이 생겼다**(2026-09-09) [OWNER — "누르면 얼마 레벨에서는 매수
 * 추천과 같은 플로우로"]. 그래도 이 화면은 여전히 추천을 안 한다: 트리거는
 * 고른 밴드의 **경계 레벨**을 「거기서 이 데스크가 할 수 있는 다리」와 이어
 * 적은 것이고, 명목·손절·목표는 말하지 않는다(오너가 「트리거 레벨까지」로
 * 정했다). 명구 의무는 그대로 산다.
 *
 * 숫자는 전부 서버가 끝낸다(§16, `/api/mr/board`) — 밴드·z·%B·상태 판정·정렬·
 * 순위까지. 이 파일은 조건 바와 카드 배치뿐이다.
 *
 * ── 배치: 조건 바 + [랭킹 표 | 상세] 2열, 페이지는 스크롤하지 않는다 ─────────
 * Main/Backtest 의 공간문법 그대로: 내용은 카드 안, 주인공(랭킹)이 남는 높이를
 * 받고, 세부(값+밴드 이력 차트)는 행 클릭 뒤 오른쪽 카드가 진다. 표 문법은
 * rv 의 것을 그대로 쓴다(.sr-rv-table 계열·순위 열 포함) — Strategy 두 세입자가
 * 같은 표를 두 문법으로 말하지 않는다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@coinbase/cds-web/tables';
import { Text } from '@coinbase/cds-web/typography';

import type { Unit } from '@/lib/api';
import { BacktestUnavailable } from '@/lib/api';
import { fmtDelta, fmtLevel, levelHeadText, levelHeadTitle, unitSuffix } from '@/lib/format';
import { BASIS_LABEL } from '@/table/InstrumentTable';
import { ROW_H } from '@/table/rowHeight';
import { directionClass, directionGlyph, tintStyle, unsignedDelta } from '@/table/tint';
import { Cond } from '@/ui/Cond';
import { ErrorState, LoadingState } from '@/ui/DataState';
import { ThHelp } from '@/ui/ThHelp';
import { Stat, StatColumn } from '@/ui/Stat';
import { useUrlState } from '@/ui/useUrlState';

import {
  MR_KS,
  MR_WINDOWS,
  fetchMrBoard,
  fetchMrHistory,
  type MrBoard,
  type MrHistory,
  type MrParams,
  type MrRow,
  type MrState,
  type MrTrigger,
  type MrWatch,
} from './api';
import { BandChart } from './BandChart';
import { BookWindow } from './BookWindow';
import { StrategyWindow } from './StrategyWindow';

/* `Cond`(조건 바 한 칸)와 `ThHelp`(열 머리 뜻풀이)는 공용이 됐다(`ui/Cond`·
   `ui/ThHelp`) [OWNER 2026-09-02 — "공용 부품은 한 벌로 승격"] — rv 와 이
   화면이 같은 기계를 두 벌씩 갖고 있었고, 타이포 문법(shorthand 대 `Text
   font=…`)까지 갈려 있었다. 이 화면의 새 문법 판이 공용의 본이 됐다. */

/** 상태 문장 — 판정이지 행동이 아니다. */
function stateText(s: MrState): string {
  if (s.kind === 'below') return `하단 밖 ${s.days}일째`;
  if (s.kind === 'above') return `상단 밖 ${s.days}일째`;
  if (s.kind === 'reentry-low') return `하단 재진입 ${s.days}일째`;
  if (s.kind === 'reentry-high') return `상단 재진입 ${s.days}일째`;
  return '밴드 안';
}

const MINUS = '−';

/** 통합 줄의 상태 — **개수**다. 「밖 3 · 재진입 1 · 안 5」.
 *  0 인 것은 안 적는다(없는 일을 0 으로 적으면 줄만 길어진다 — `exitTally` 의
 *  그 규율). 전부 안이면 그 사실을 한 낱말로 말한다. */
function watchText(w: MrWatch): string {
  const out = w.outLow + w.outHigh;
  const parts = [
    out ? `밖 ${out}` : null,
    w.reentry ? `재진입 ${w.reentry}` : null,
    w.inside ? `밴드 안 ${w.inside}` : null,
  ].filter((x): x is string => x !== null);
  return parts.join(' · ') || '—';
}

/** 트리거 한 문장 — 「25.6bp 이상이면 국고 매수 · IRS 페이」
 *  [OWNER 2026-09-09 — "누르면 얼마 레벨에서는 매수 추천과 같은 플로우로"].
 *
 *  **문턱과 다리만 말한다.** 명목·손절·목표는 적지 않는다 [OWNER 2026-09-09 —
 *  「트리거 레벨까지」] — 그 셋을 적으면 이 화면이 주문 카드가 되고, 창설부터
 *  지고 있는 명구 의무(이 파일 머리)가 깨진다. 레벨은 계열의 자기 단위이고
 *  거리는 bp 다(서버가 그렇게 끝낸다 — `mr.triggers_for`).
 *
 *  이미 지난 문턱을 「남았어요」로 적으면 거짓이라 문장이 갈린다. */
function triggerText(t: MrTrigger, unit: string, dUnit: string): string {
  const lv = `${fmtLevel(t.level, unit as Unit)}${unitSuffix(unit as Unit)}`;
  const word = t.side === 'above' ? '이상' : '이하';
  const gap = `${fmtLevel(Math.abs(t.gap), dUnit as Unit)}${unitSuffix(dUnit as Unit)}`;
  return t.reached
    ? `${lv} ${word}(${gap} 지났어요) → ${t.legs}`
    : `${lv} ${word}이면 ${t.legs} — ${gap} 남았어요`;
}

/** 히어로 한 줄이 적을 트리거 — **지난 것이 먼저, 없으면 가까운 것**.
 *
 *  양방향 계열(선물·퓨처스왑)은 경계가 둘이라 고르는 규칙이 있어야 한다. 지난
 *  문턱이 곧 「지금 할 수 있는 것」이라 그쪽이 먼저이고, 둘 다 멀면 더 가까운
 *  쪽이 다음에 닿을 문턱이다. 둘 다 보여 주는 자리는 상세 카드의 「트리거」 칸.
 *  트리거가 아예 없으면(창 미달·한 방향이 막힌 계열의 반대쪽) `undefined` 다. */
function heroTrigger(r: MrRow): MrTrigger | undefined {
  const ts = r.triggers ?? [];
  return ts.find((t) => t.reached) ?? [...ts].sort((a, b) => a.gap - b.gap)[0];
}

/** z 표기 — 부호 명시, 반올림 후 0 은 부호 없이(rv fmt 의 규칙 그대로). */
function fmtZ(z: number | null): string {
  if (z == null) return '—';
  const s = Math.abs(z).toFixed(2);
  if (Number(s) === 0) return '0.00σ';
  return z > 0 ? `+${s}σ` : `${MINUS}${s}σ`;
}

/** 히어로의 전일 변화 — Main 미리보기 히어로의 그 문법: 방향 글리프 + 부호
 * 있는 변화 + 방향색 글자(PreviewPane 의 `↗ +4.3bp`). */
function HeroDelta({ d, unit }: { d: number; unit: string }) {
  return (
    <span className={directionClass(d)}>
      {directionGlyph(d) || '→'} {fmtDelta(d, unit as Unit)}
      {unitSuffix(unit as Unit)}
    </span>
  );
}

/** 밴드 위치 트랙 — Main 52주 「위치」 열의 그 부품(sr-track). 숫자(%B)는
 * title 로 물러나고 그림이 말한다: 하단↔상단 트랙 위의 지금 자리. 밖이면
 * 끝에 붙는다(클램프) — 상태 열이 «밖 n일째» 로 그 사실을 말한다. */
function BandTrack({ pctB }: { pctB: number | null }) {
  if (pctB == null) {
    return (
      <Text font="label2" as="span" color="fgMuted" noWrap>
        —
      </Text>
    );
  }
  const pos = Math.max(0, Math.min(100, pctB));
  return (
    /* sr-track 은 폭 없는 블록이라(Main 에선 sr-range 격자가 폭을 줌) 여기선
       고정폭 상자가 트랙 길이를 진다 — 없으면 2px 짜리 점으로 접힌다(실측). */
    <Box as="span" width={72} display="block">
      <span className="sr-track" title={`밴드 하단↔상단의 ${Math.round(pctB)}% 지점 (%B)`}>
        <span className="sr-track-mark" style={{ left: `${pos}%` }} />
      </span>
    </Box>
  );
}

/** BSS 통합 상세 — **만기 순** 밴드 위치 스트립.
 *
 * 랭킹 표와 같은 자료를 다른 순서로 세운 것이고, 그 순서가 이 카드의 전부다:
 * 랭킹(|z| 순)은 「지금 어디가 제일 늘어났나」를 답하고 이 스트립(6M→10Y)은
 * 「커브의 어느 구간이 늘어났나」를 답한다. 둘은 다른 질문이라 한 표로는 못
 * 한다 — 순위로 늘어놓으면 만기 축이 흩어져 모양이 사라진다.
 *
 * **표가 아니라 그림이다** [의도한 캐논 이탈, 실측 2026-09-01]. 처음에는 CDS
 * `Table` 로 세웠는데 행이 44px 이라 아홉 줄이 436px 이고 카드가 준 자리는
 * 292px 이었다 — 여섯 줄만 보이고 나머지는 스크롤 뒤였다. 한눈에 보려고 만든
 * 그림을 굴려서 보게 하면 그 그림은 아무 일도 안 한다. 부품은 캐논 그대로다
 * (`.sr-track`/`.sr-track-mark` — Main 52주 「위치」 열의 그것).
 *
 * 줄은 **누를 수 없다**. 아홉 만기는 바로 위 랭킹 표에 이미 다 있고, 거기서
 * 고르면 된다 — 같은 행동을 두 곳에 두면 탭 정지만 아홉 개 늘어난다.
 */
function BookDetail({ watch }: { watch: MrWatch }) {
  return (
    <VStack gap={0} width="100%">
      {/* 머리는 한 줄 — 아래 아홉 줄의 칸 폭과 자로 맞춘다. */}
      <HStack gap={1} alignItems="center" height={22} width="100%">
        <Box width={44}>
          <Text font="caption" as="span" color="fgMuted" noWrap>만기</Text>
        </Box>
        <Box width={64} display="flex" justifyContent="flex-end">
          <Text font="caption" as="span" color="fgMuted" noWrap>현재</Text>
        </Box>
        {/* 트랙 열의 머리는 **가운데**다 — 왼쪽에 붙이면 바로 앞의 「현재」와
            8px 만 떨어져 「현재 위치」 한 낱말로 읽힌다(실측 2026-09-01). */}
        <Box flexGrow={1} minWidth={0} display="flex" justifyContent="center">
          <Text font="caption" as="span" color="fgMuted" noWrap>위치</Text>
        </Box>
        <Box width={68} display="flex" justifyContent="flex-end">
          <Text font="caption" as="span" color="fgMuted" noWrap>늘어남</Text>
        </Box>
      </HStack>
      {watch.legs.map((g) => (
        <HStack key={g.id} gap={1} alignItems="center" height={26} width="100%">
          <Box width={44}>
            <Text font="label2" as="span" noWrap>{g.tenor}</Text>
          </Box>
          <Box width={64} display="flex" justifyContent="flex-end">
            <Text font="label2" as="span" tabularNumbers noWrap>
              {fmtLevel(g.v, 'bp' as Unit)}
            </Text>
          </Box>
          {/* 트랙은 남는 폭을 다 받는다 — 아홉 줄이 같은 자로 그려져야 커브의
              모양이 읽힌다(폭이 줄마다 다르면 그건 그림이 아니다). */}
          {/* `display="block"` 이 있어야 트랙이 폭을 받는다 — CDS `Box` 는
              기본이 flex 라, 그 안의 `.sr-track`(내용 없는 블록)이 flex 아이템이
              되어 **폭 0** 으로 접힌다(실측 2026-09-01: 상자 808px · 트랙 0px).
              `BandTrack` 이 같은 이유로 `display="block"` 을 적어 두었다. */}
          <Box flexGrow={1} minWidth={0} display="block">
            <span
              className="sr-track"
              title={`${g.label} · 밴드 하단↔상단의 ${
                g.pctB == null ? '—' : Math.round(g.pctB)
              }% 지점 (%B) · ${stateText(g.state)}`}
            >
              {g.pctB == null ? null : (
                <span
                  className="sr-track-mark"
                  style={{ left: `${Math.max(0, Math.min(100, g.pctB))}%` }}
                />
              )}
            </span>
          </Box>
          <Box width={68} display="flex" justifyContent="flex-end">
            <Text font="label2" as="span" tabularNumbers noWrap>{fmtZ(g.z)}</Text>
          </Box>
        </HStack>
      ))}
    </VStack>
  );
}

export function MrPage() {
  const [board, setBoard] = useState<MrBoard>();
  const [error, setError] = useState<string>();
  const [unavailable, setUnavailable] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [selId, setSelId] = useState<string>();
  const [histories, setHistories] = useState<Record<string, MrHistory>>({});
  const [histErr, setHistErr] = useState<string>();
  /* 전략 실험 창 [OWNER 2026-08-25] — 세부는 클릭 뒤 창이 진다(백테스트 문법). */
  const [stratOpen, setStratOpen] = useState(false);

  /* 룩백·밴드 폭 — URL 상태(rv 의 이력 창과 같은 문법: 기본값은 주소에 안
     적는다). 모르는 값은 기본으로 떨어진다(딥링크 게이트). 선택지 근거는
     서버(mr.py) 주석과 열 머리 툴팁이 진다. */
  const [mwParam, setMwParam] = useUrlState('mw');
  const [mkParam, setMkParam] = useUrlState('mk');
  const bandWindow = (MR_WINDOWS as readonly number[]).includes(Number(mwParam))
    ? Number(mwParam)
    : MR_WINDOWS[0];
  const bandK = (MR_KS as readonly number[]).includes(Number(mkParam))
    ? Number(mkParam)
    : 2.0;
  const params = useMemo<MrParams>(
    () => ({ window: bandWindow, k: bandK }),
    [bandWindow, bandK],
  );

  /* 딥링크 경합 가드 — 마운트 직후 URL 훅이 아직 기본값일 때의 fetch 와 실제
     파라미터의 fetch 가 경주한다(라이브 실측 2026-08-25: mw=252 링크가 20일
     보드를 그렸다). 늦게 온 옛 응답이 이기지 못하게 순번으로 버린다. */
  const loadSeq = useRef(0);
  const load = useCallback(() => {
    const my = ++loadSeq.current;
    setError(undefined);
    setUnavailable(false);
    setRefreshing(true);
    fetchMrBoard(params)
      .then((b) => {
        if (loadSeq.current === my) setBoard(b);
      })
      .catch((e: unknown) => {
        if (loadSeq.current !== my) return;
        if (e instanceof BacktestUnavailable) setUnavailable(true);
        else setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (loadSeq.current === my) setRefreshing(false);
      });
  }, [params]);

  useEffect(() => {
    load();
  }, [load]);

  /* 파라미터가 바뀌면 밴드도 바뀐다 — 옛 창의 이력 캐시는 통째로 무효다. */
  useEffect(() => {
    setHistories({});
    setHistErr(undefined);
  }, [params]);

  /* 레벨 열 머리가 이름할 날짜. 두 소스가 갈리면 하루를 못 고르므로 null 로
     보내 `levelHeadText` 의 폴백(「현재」)에 맡긴다 — 조건 바가 소스별 날짜를
     이미 말하고 있다. */
  const headAsof =
    board && board.asof.bss === board.asof.fut ? board.asof.bss : null;
  const rows = board?.rows ?? [];
  const sel: MrRow | undefined = rows.find((r) => r.id === selId) ?? rows[0];
  const selHist = sel ? histories[sel.id] : undefined;
  /* 통합 줄이 골라져 있는가 — 이 줄은 계열이 아니라 집계라 `rows` 에 없고,
     그래서 선택 판정이 따로 선다. 오른쪽 카드와 창이 이 하나로 갈린다. */
  const watch = board?.watch ?? null;
  const isBook = watch != null && selId === watch.id;

  useEffect(() => {
    const id = sel?.id;
    if (!id || histories[id]) return;
    let dead = false;
    setHistErr(undefined);
    fetchMrHistory(id, params)
      .then((h) => {
        if (!dead) setHistories((prev) => ({ ...prev, [id]: h }));
      })
      .catch((e: unknown) => {
        if (!dead) setHistErr(e instanceof Error ? e.message : String(e));
      });
    return () => {
      dead = true;
    };
  }, [sel?.id, histories, params]);

  if (unavailable) {
    return (
      <ErrorState
        what="Mean Reversion"
        detail="실행 중인 백엔드(:8200)가 필요해요 — BSS·선물이 SQL 에만 있어서 미리 구워둘 수가 없어요."
        onRetry={load}
        retrying={refreshing}
      />
    );
  }
  if (error) {
    return <ErrorState what="Mean Reversion" detail={error} onRetry={load} retrying={refreshing} />;
  }
  if (!board || !sel) {
    return <LoadingState what="Mean Reversion" />;
  }

  return (
    <VStack gap={1.5} width="100%" flexGrow={1} minHeight={0}>
      {/* ── 조건 바 — 어떤 밴드에서 나온 숫자인지가 카드보다 먼저 읽힌다 ──── */}
      <VStack className="sr-rv-bar" flexShrink={0} gap={0.5} width="100%">
        <HStack gap={1.5} alignItems="center" flexWrap="wrap">
          {/* 순서는 언제 → 무엇으로(rv 의 판단). 소스가 둘이라 as-of 도 둘이고,
              갈라진 날은 굵기+밑줄이 그 사실을 말한다(rv B-2). 계열 정의는
              행의 서브라인이 진다 — 혼합 유니버스에서 바 한 칸으로는 거짓말이
              된다. */}
          <Cond
            k="민평·IRS"
            v={board.asof.bss ?? '—'}
            strong={board.asof.bss !== board.asof.fut}
          />
          <Cond
            k="선물"
            v={board.asof.fut ?? '—'}
            strong={board.asof.bss !== board.asof.fut}
          />
          {/* IRS 커브만 쓰는 계열(커브·플라이)의 종가 — **따로 선다**
              [OWNER 2026-09-09]. 민평을 안 타므로 BSS 와 하루가 갈릴 수 있고,
              한 칸에 뭉치면 그 날 화면이 거짓을 말한다(rv 의 B-2). 구 백엔드는
              이 값이 없어 칸이 조용히 접힌다. */}
          {board.asof.irs ? (
            <Cond
              k="IRS 커브"
              v={board.asof.irs}
              strong={board.asof.irs !== board.asof.bss}
            />
          ) : null}
          {/* 룩백·밴드 폭 선택지 [OWNER 2026-08-25 — "보통 사용하는 값들을
              선택지로"]. 알약은 rv 설정의 그 컨트롤, 근거는 라벨 툴팁이 진다. */}
          <HStack gap={0.5} alignItems="center">
            <ThHelp
              label="룩백"
              help="20일은 볼린저 밴드의 관례 기본값이에요. 60·120·252일은 채권 RV 리서치가 흔히 쓰는 분기·반기·1년 창이에요."
            />
            {MR_WINDOWS.map((w) => (
              <button
                key={w}
                type="button"
                className="sr-pillbtn"
                data-on={bandWindow === w || undefined}
                aria-pressed={bandWindow === w}
                onClick={() => setMwParam(w === MR_WINDOWS[0] ? undefined : String(w))}
              >
                {w}일
              </button>
            ))}
          </HStack>
          <HStack gap={0.5} alignItems="center">
            <ThHelp
              label="밴드 폭"
              help="2σ가 볼린저 기본이에요. 1.5σ는 벗어남을 민감하게, 2.5σ는 보수적으로 잡는 문헌의 통상 변형이에요."
            />
            {MR_KS.map((kk) => (
              <button
                key={kk}
                type="button"
                className="sr-pillbtn"
                data-on={bandK === kk || undefined}
                aria-pressed={bandK === kk}
                onClick={() => setMkParam(kk === 2.0 ? undefined : String(kk))}
              >
                {`${kk}σ`}
              </button>
            ))}
          </HStack>
          <Cond k="재진입 표기" v={`${board.params.recentN}영업일`} />
          {refreshing ? (
            <Text font="legal" as="span" color="fgMuted" noWrap>
              갱신 중…
            </Text>
          ) : null}
          {/* 논리 속성 — 캐논(`ui/ControlCard`)이 쓰는 그 낱말(marginInlineStart). */}
          <Box style={{ marginInlineStart: 'auto' }}>
            {/* 명구 의무 — Credit RV 와 같은 문법. */}
            <Text font="legal" as="span" color="fgMuted" noWrap>
              늘어남을 재는 화면이에요 — 투자판단이 아니에요.
            </Text>
          </Box>
        </HStack>
        {/* 소스가 셋이 되면서 판정도 셋을 본다 — 종전에는 둘만 비교했다. */}
        {new Set([board.asof.bss, board.asof.fut,
                  ...(board.asof.irs ? [board.asof.irs] : [])]).size > 1 ? (
          <Text font="legal" as="span" color="fgMuted">
            소스마다 종가 날짜가 달라요 — 각 행은 자기 소스의 날짜 기준이에요.
          </Text>
        ) : null}
        {/* 트리거가 무엇인지 **화면이 말한다** [OWNER 2026-09-09 — 「트리거
            레벨까지」]. 안 적으면 읽는 사람이 그 수를 「추천 진입가」로 읽는데,
            그것은 위 두 알약이 정한 밴드의 경계일 뿐이다 — 알약을 바꾸면 같이
            움직인다. 명구 의무(오른쪽 줄)와 한 몸이다. */}
        <Text font="legal" as="span" color="fgMuted">
          트리거는 위에서 고른 밴드({bandWindow}일 · {bandK}σ)의 경계 레벨이에요 —
          거기서 이 데스크가 할 수 있는 다리를 적은 것이고, 명목·손절·목표는 안
          말해요.
        </Text>
        {board.excluded.length > 0 ? (
          /* 못 읽은 테너 — 조용히 빼지 않는다(rv 의 exclusions 문법). */
          <Text font="legal" as="span" color="fgMuted">
            {board.excluded.map((x) => `${x.label}: ${x.reason}`).join(' · ')}
          </Text>
        ) : null}
      </VStack>

      {/* ── 히어로 — **1순위를 바로 띄운다** [OWNER 2026-09-09 — "1순위를 바로
          띄우기 … Credit RV에서 은행채 AAA가 가장 매력적이다라고 블록으로
          보여주는 것처럼"] ──────────────────────────────────────────────────
          문법은 **rv 의 그 블록을 이식**한 것이다(`RvPage` 「지금 가장
          매력적이에요」): 작은 라벨 한 줄 + 이름이 display3 로 선 버튼 +
          뮤트 메타 한 줄. 부품도 그쪽 것이다 — `.sr-rv-linkbtn`(글자를
          버튼으로 만드는 리셋)은 이름만 rv 이고 `theme/type.css` 의 앱 공용
          리셋이다(CLAUDE.md 캐논 규칙 2: 「클래스 이름은 소유권이 아니다」).

          **표에 1위가 이미 골라져 있는데 왜 이 블록인가.** 선택은 칸 하나의
          테두리로만 표시돼서, 열세 줄 중 어느 것이 1위인지 눈이 표를 훑어야
          알았다. 그리고 이 화면이 답해야 하는 물음이 「지금 무엇을 볼까」이므로
          (오너의 말 그대로 「지금 모니터링할 테너가 뭐냐가 중요함」) 그 답은
          표 안이 아니라 표 **앞**에 서야 한다.

          메타 줄이 트리거를 진다 — 블록 하나로 「무엇을·지금 얼마고·어디서
          들어가나」가 닫힌다. 명목·손절·목표는 없다(`triggerText` 머리). */}
      {rows[0] ? (
        <VStack flexShrink={0} gap={0} width="100%">
          <Text font="label1" as="span" color="fgMuted" noWrap>
            지금 모니터링할 테너예요
          </Text>
          <HStack gap={1.5} alignItems="baseline" flexWrap="wrap">
            <button
              type="button"
              className="sr-rv-linkbtn"
              aria-label={`${rows[0].label} 골라서 전략 실험 창 열기`}
              onClick={() => {
                setSelId(rows[0]!.id);
                setStratOpen(true);
              }}
            >
              <Text font="display3" as="span" noWrap>
                {rows[0].label}
              </Text>
            </button>
            <Text font="body" as="span" color="fgMuted" tabularNumbers>
              {fmtLevel(rows[0].v, rows[0].unit as Unit)}
              {unitSuffix(rows[0].unit as Unit)} · {fmtZ(rows[0].z)} ·{' '}
              {stateText(rows[0].state)}
              {/* 트리거는 **한 개만** 적는다 — 양방향 계열(선물·퓨처스왑)은
                  경계가 둘인데 히어로 한 줄에 둘을 적으면 그 줄이 접힌다.
                  고르는 규칙: 지난 것이 있으면 그것, 없으면 가까운 것. 둘 다
                  보려면 아래 상세 카드의 「트리거」 칸이 진다. */}
              {heroTrigger(rows[0])
                ? ` · ${triggerText(heroTrigger(rows[0])!, rows[0].unit, rows[0].dUnit)}`
                : ''}
            </Text>
          </HStack>
        </VStack>
      ) : null}

      {/* ── 2열: 보드가 주인공, 상세가 나머지를 받는다 ───────────────────── */}
      <HStack gap={2} alignItems="stretch" width="100%" flexGrow={1} minHeight={0}>
        <VStack
          className="sr-card"
          flexBasis={820}
          flexGrow={0}
          flexShrink={1}
          maxWidth={820}
          minHeight={0}
        >
          <HStack
            alignItems="center"
            justifyContent="space-between"
            gap={1}
            paddingX={2}
            paddingTop={1.5}
            paddingBottom={0.5}
          >
            <Text font="label1" as="h2" noWrap>
              밴드 위치 랭킹
            </Text>
          </HStack>
          {/* 표는 Main/Backtest 의 그 방언이다 [OWNER 2026-08-25 — "값, 전일,
              늘어남 이런것도 전부 기준을 Backtest 에 맞춰서"]: CDS Table ·
              60px 행 · 이름은 label1 + legal 2줄 스택 · 숫자는 label2 tabular
              우측 · **전일은 틴트 셀**(배경 = 방향 워시, 글자 = 방향색, 부호는
              ↗↘ 글리프가 지고 숫자는 무부호 — `table/tint.ts` 그대로) ·
              위치는 트랙(코인베이스 52주 «위치» 의 그 부품). 첫 판의 rv 방언
              (.sr-rv-table)은 Strategy 이웃이지 Main 형제가 아니었다. */}
          <VStack gap={0} width="100%" minHeight={0} flexGrow={1}>
            <div className="sr-rv-rank-fill">
              <div className="sr-rv-rank-scroll">
                <Table bordered={false}>
                  {/* 머리는 스크롤을 따라온다 — Main 의 `<TableHeader sticky>`
                      그대로. 13행이 스크롤하는 표에서 「어느 열이 늘어남이었지」를
                      기억으로 들게 하지 않는다 [감사 2026-08-25]. */}
                  <TableHeader sticky>
                    <TableRow>
                      <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                        <Text font="caption" as="span" color="fgMuted">순위</Text>
                      </TableCell>
                      <TableCell as="th" scope="col">
                        <Text font="caption" as="span" color="fgMuted">계열</Text>
                      </TableCell>
                      {/* 레벨 열 머리는 **날짜**다(levelHeadText) — Main·Backtest·
                          매트릭스가 다 그렇다. 「값」 같은 낱말은 그 열이 어느 날
                          종가인지를 안 말한다. 두 소스 as-of 가 갈린 날은 이
                          함수의 문서화된 폴백(「현재」)으로 떨어지고, 조건 바가
                          어느 소스가 언제인지 말한다. */}
                      <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                        <Text font="caption" as="span" color="fgMuted" title={levelHeadTitle(headAsof)}>
                          {levelHeadText(headAsof)}
                        </Text>
                      </TableCell>
                      {/* 변화 열 이름은 형제 것을 **임포트**한다 — 문자열로 다시
                          적으면 한쪽만 낡는다(BASIS_LABEL 머리 주석의 그 규칙).
                          종전에는 '1D' 하드코딩이었다(2026-09-02 수리). */}
                      <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                        <Text font="caption" as="span" color="fgMuted">{BASIS_LABEL.d1}</Text>
                      </TableCell>
                      <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                        {/* 창을 상수로 적으면 컨트롤을 바꾼 날 화면이 거짓말을
                            한다(rv 「버퍼 3개월」 실측의 같은 자리). */}
                        <ThHelp
                          label="늘어남"
                          help={`지금 값이 ${bandWindow}일 평균에서 σ 몇 개만큼 떨어져 있는지예요. 이 표의 정렬 축이에요.`}
                        />
                      </TableCell>
                      <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                        <ThHelp
                          label="위치"
                          help="밴드 하단↔상단 트랙 위의 지금 자리예요. 밖이면 끝에 붙고, 상태 열이 며칠째인지 말해요."
                        />
                      </TableCell>
                      <TableCell as="th" scope="col">
                        <ThHelp
                          label="상태"
                          help="밴드 밖이면 며칠째인지, 안으로 돌아왔으면 며칠째인지예요."
                        />
                      </TableCell>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((r) => (
                      <TableRow
                        key={r.id}
                        tabIndex={0}
                        /* Main 의 선택 문법 그대로 — aria-current 가 곧 핀 채움
                           (`tr[aria-current='true']` 의 --sr-control). */
                        aria-current={r.id === sel.id ? 'true' : undefined}
                        style={{ height: ROW_H, cursor: 'pointer' }}
                        onClick={() => setSelId(r.id)}
                        onKeyDown={(e: React.KeyboardEvent) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setSelId(r.id);
                          }
                        }}
                      >
                        <TableCell className="sr-num" justifyContent="flex-end">
                          <Text font="label2" as="span" tabularNumbers noWrap>
                            {r.rank}
                          </Text>
                        </TableCell>
                        <TableCell>
                          {/* 이름 + 정의 — Main 의 2줄 스택(label1/legal) 그대로.
                              국고−IRS 와 선물내재가 한 표에 섞이므로 숫자 옆의
                              «무엇인지» 는 서브라인이 진다. */}
                          <VStack as="span" className="sr-name-stack">
                            <Text font="label1" as="span" noWrap>
                              {r.label}
                            </Text>
                            <Text font="legal" as="span" color="fgMuted" noWrap>
                              {r.defn}
                            </Text>
                          </VStack>
                        </TableCell>
                        <TableCell className="sr-num" justifyContent="flex-end">
                          <Text font="label2" as="span" tabularNumbers noWrap>
                            {fmtLevel(r.v, r.unit as Unit)}
                          </Text>
                        </TableCell>
                        {/* 전일 = Main 변화 셀: 틴트 워시 + 방향색 글자 + 글리프,
                            숫자는 무부호(tabular 정렬 — 부호 폭이 흔든다). */}
                        <TableCell
                          className="sr-num"
                          justifyContent="flex-end"
                          style={tintStyle(r.d1)}
                        >
                          <Text
                            font="label2"
                            as="span"
                            tabularNumbers
                            noWrap
                            className={directionClass(r.d1)}
                          >
                            {directionGlyph(r.d1)}
                            {directionGlyph(r.d1) ? ' ' : ''}
                            {unsignedDelta(fmtDelta(r.d1, r.dUnit as Unit))}
                          </Text>
                        </TableCell>
                        <TableCell className="sr-num" justifyContent="flex-end">
                          <Text font="label2" as="span" tabularNumbers noWrap>
                            {fmtZ(r.z)}
                          </Text>
                        </TableCell>
                        <TableCell className="sr-num" justifyContent="flex-end">
                          <BandTrack pctB={r.pctB} />
                        </TableCell>
                        <TableCell>
                          <Text font="label2" as="span" color="fgMuted" noWrap>
                            {stateText(r.state)}
                          </Text>
                        </TableCell>
                      </TableRow>
                    ))}
                    {/* ── BSS 통합 한 줄 [OWNER 2026-09-01 — "밴드워치 랭킹
                        순위, 계열 밑에 따로 하나 빼주면 되겠다"] ──────────────
                        같은 표 안에 두되 헤어라인으로 가른다(`.sr-mr-book`):
                        열 격자를 나눠 쓰지 않으면 두 줄을 나란히 못 읽고, 그렇다고
                        랭킹의 일부로 보이면 「순위 14위」로 읽힌다.

                        **값·전일 칸이 없다.** 만기가 다른 아홉 스프레드의 평균은
                        거래할 수 있는 값이 아니다 — 단위 없는 둘(|z|·%B)만 평균이고
                        나머지는 개수다. 그 사실을 서브라인이 말한다. */}
                    {watch ? (
                      <TableRow
                        className="sr-mr-book"
                        tabIndex={0}
                        aria-current={isBook ? 'true' : undefined}
                        style={{ height: ROW_H, cursor: 'pointer' }}
                        onClick={() => setSelId(watch.id)}
                        onKeyDown={(e: React.KeyboardEvent) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setSelId(watch.id);
                          }
                        }}
                      >
                        {/* 순위 칸은 비운다 — 이 줄은 |z| 로 매긴 순위에 낄 수
                            있는 물건이 아니다(집계이지 계열이 아니다). */}
                        <TableCell className="sr-num" justifyContent="flex-end">
                          <Text font="label2" as="span" color="fgMuted" noWrap>
                            {MINUS}
                          </Text>
                        </TableCell>
                        <TableCell>
                          <VStack as="span" className="sr-name-stack">
                            <Text font="label1" as="span" noWrap>
                              {watch.label}
                            </Text>
                            {/* 「9만기」를 안 적는다 — 이 줄이 `noWrap` 이라
                                네 글자가 계열 열을 40px 넓히고, 그만큼 표가
                                카드를 넘어 마지막 열(상태)이 잘린다(실측
                                2026-09-01: scrollWidth 843 → 803). 만기 수는
                                상세 카드의 「만기」 칸이 진다. */}
                            <Text font="legal" as="span" color="fgMuted" noWrap>
                              {watch.defn} · 아래 수는 평균이에요
                            </Text>
                          </VStack>
                        </TableCell>
                        <TableCell className="sr-num" justifyContent="flex-end">
                          <Text
                            font="label2"
                            as="span"
                            color="fgMuted"
                            noWrap
                            title="만기가 다른 아홉 스프레드의 평균은 거래할 수 있는 값이 아니라서 레벨을 안 적어요."
                          >
                            {MINUS}
                          </Text>
                        </TableCell>
                        <TableCell className="sr-num" justifyContent="flex-end">
                          <Text font="label2" as="span" color="fgMuted" noWrap>
                            {MINUS}
                          </Text>
                        </TableCell>
                        <TableCell className="sr-num" justifyContent="flex-end">
                          {/* 평균 |z| — 부호가 없다(서로 반대로 늘어난 만기가
                              섞이면 평균이 상쇄돼 「안 늘어났다」가 된다). */}
                          <Text
                            font="label2"
                            as="span"
                            tabularNumbers
                            noWrap
                            title={`${watch.n}만기 |z| 의 평균이에요`}
                          >
                            {watch.meanAbsZ == null ? '—' : `${watch.meanAbsZ.toFixed(2)}σ`}
                          </Text>
                        </TableCell>
                        <TableCell className="sr-num" justifyContent="flex-end">
                          <BandTrack pctB={watch.meanPctB} />
                        </TableCell>
                        <TableCell>
                          <Text font="label2" as="span" color="fgMuted" noWrap>
                            {watchText(watch)}
                          </Text>
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </div>
            </div>
          </VStack>
        </VStack>

        {/* ── 상세 — 선택 계열의 큰 숫자와 값+밴드 이력 ────────────────────── */}
        <VStack className="sr-card" flexGrow={1} flexShrink={1} minWidth={0} minHeight={0}>
          <HStack
            alignItems="baseline"
            justifyContent="space-between"
            gap={1}
            paddingX={2}
            paddingTop={1.5}
            paddingBottom={0.5}
          >
            <HStack gap={1} alignItems="baseline">
              <Text font="label1" as="h2" noWrap>
                {isBook && watch ? watch.label : sel.label}
              </Text>
              <Text font="caption" as="span" color="fgMuted" noWrap>
                {isBook && watch ? watch.defn : sel.defn}
              </Text>
            </HStack>
            <HStack gap={1} alignItems="center">
              <Text font="caption" as="span" color="fgMuted" noWrap>
                {isBook && watch ? (watch.asof ?? '—') : sel.asof}
              </Text>
              {/* rv 「상세 분석」 자리의 문법 — 세부(전략 재현)는 버튼 뒤 창.
                  통합 줄에서는 **다른 창**이 열린다(아홉을 한 장부로 돌린다) —
                  그래서 버튼의 이름도 다르다. 같은 이름으로 두 창을 열면 어느
                  숫자를 보고 있는지 화면이 안 말한다. */}
              <button
                type="button"
                className="sr-pillbtn"
                data-on={stratOpen || undefined}
                aria-pressed={stratOpen}
                onClick={() => setStratOpen((v) => !v)}
              >
                {isBook ? '통합 장부' : '전략 실험'}
              </button>
            </HStack>
          </HStack>
          <VStack gap={1.5} paddingX={2} paddingBottom={2} width="100%" flexGrow={1} minHeight={0}>
            {isBook && watch ? (
              <>
                {/* 큰 건 제목이 아니라 숫자다(공간문법). 통합 줄의 그 숫자는
                    레벨이 아니라 **평균 |z|** 다 — 거래할 수 있는 값이 아니라서
                    레벨 자리를 비워 두는 대신, 밴드 워치가 답해야 하는 수를
                    히어로로 올린다. */}
                <HStack gap={2} alignItems="baseline" flexWrap="wrap">
                  <Text font="display3" as="span" tabularNumbers>
                    {watch.meanAbsZ == null ? '—' : `${watch.meanAbsZ.toFixed(2)}σ`}
                  </Text>
                  <Text font="body" as="span" color="fgMuted">
                    {watchText(watch)}
                  </Text>
                </HStack>
                <BookDetail watch={watch} />
                <HStack className="sr-stats" width="100%" flexWrap="wrap">
                  <StatColumn title="묶음">
                    <Stat label="만기" value={`${watch.n}개`} />
                    <Stat label="밴드 밖" value={`${watch.outLow + watch.outHigh}개`}
                      note={`아래 ${watch.outLow} · 위 ${watch.outHigh}`} />
                    <Stat label="재진입" value={`${watch.reentry}개`} />
                    <Stat label="밴드 안" value={`${watch.inside}개`} />
                  </StatColumn>
                  <StatColumn title="지금">
                    <Stat label="평균 |z|"
                      value={watch.meanAbsZ == null ? '—' : `${watch.meanAbsZ.toFixed(2)}σ`} />
                    <Stat
                      label="가장 늘어난 곳"
                      value={watch.peak == null ? '—' : watch.peak.label}
                      note={watch.peak == null ? undefined : fmtZ(watch.peak.z)}
                    />
                    {/* 종가가 만기마다 갈릴 수 있다 — 민평×IRS 교집합이라 한
                        만기가 하루 안 찍히면 그 다리만 뒤처진다. 최신 날짜만
                        적으면 화면이 아홉 다 최신인 척한다(rv 의 B-2 판단). */}
                    <Stat
                      label="종가"
                      value={watch.asof ?? '—'}
                      note={
                        watch.stale > 0
                          ? `${watch.stale}만기는 ${watch.asofMin}`
                          : `${watch.n}만기 모두`
                      }
                    />
                  </StatColumn>
                </HStack>
              </>
            ) : (
              <>
            {/* 큰 건 제목이 아니라 숫자다(공간문법). */}
            <HStack gap={2} alignItems="baseline" flexWrap="wrap">
              <Text font="display3" as="span" tabularNumbers>
                {fmtLevel(sel.v, sel.unit as Unit)}
                {unitSuffix(sel.unit as Unit)}
              </Text>
              <Text font="body" as="span" tabularNumbers>
                <HeroDelta d={sel.d1} unit={sel.dUnit} />
              </Text>
            </HStack>
            {selHist ? (
              <BandChart history={selHist} />
            ) : histErr ? (
              <Text font="legal" as="span" color="fgMuted">
                이력을 불러오지 못했어요 — {histErr}
              </Text>
            ) : (
              <Text font="legal" as="span" color="fgMuted">
                이력을 불러오는 중이에요…
              </Text>
            )}
            {/* 사실 줄은 **차트 아래**, 그리고 이 앱의 유일한 스트립 문법이다
                (`ui/Stat.tsx` — 그 파일 머리가 코인베이스 가격 페이지·토스증권
                종목 머리 실측을 적어 두었다). Main 미리보기의 「이 구간 · 변화 ·
                52주」와 같은 자리·같은 부품. 방향색은 안 쓴다 — z 는 방향이
                아니라 자리다. */}
            <HStack className="sr-stats" width="100%" flexWrap="wrap">
              <StatColumn title="밴드">
                <Stat label="늘어남" value={fmtZ(sel.z)} />
                <Stat label="%B" value={sel.pctB == null ? '—' : sel.pctB.toFixed(0)} />
                <Stat
                  label="전폭"
                  value={
                    sel.width == null
                      ? '—'
                      : `${fmtLevel(sel.width, sel.dUnit as Unit)}${unitSuffix(sel.dUnit as Unit)}`
                  }
                />
              </StatColumn>
              <StatColumn title="지금">
                <Stat label="상태" value={stateText(sel.state)} />
                <Stat label="종가" value={sel.asof} />
              </StatColumn>
              {/* ── 트리거 [OWNER 2026-09-09 — "누르면 얼마 레벨에서는 매수
                  추천과 같은 플로우로 가야함"] ──────────────────────────────
                  히어로는 1순위 한 줄만 말하므로, **고른 줄**의 문턱은 여기가
                  진다(표를 누르는 플로우의 끝). 양방향 계열은 칸이 둘이다.
                  값은 문턱 레벨이고 note 가 다리와 남은 거리를 적는다 —
                  `Stat` 의 그 두 칸 문법(`ui/Stat.tsx`).

                  막힌 방향은 **칸을 안 만들고 사유를 적는다**(rv exclusions
                  문법) — 빈칸으로 두면 화면이 「그쪽은 문턱이 없다」고 말한다. */}
              {sel.triggers && sel.triggers.length > 0 ? (
                <StatColumn title="트리거">
                  {sel.triggers.map((t) => (
                    <Stat
                      key={t.side}
                      label={t.side === 'above' ? '상단 밖이면' : '하단 밖이면'}
                      value={`${fmtLevel(t.level, sel.unit as Unit)}${unitSuffix(sel.unit as Unit)}`}
                      note={`${t.legs} · ${
                        t.reached
                          ? `${fmtLevel(Math.abs(t.gap), sel.dUnit as Unit)}${unitSuffix(sel.dUnit as Unit)} 지났어요`
                          : `${fmtLevel(t.gap, sel.dUnit as Unit)}${unitSuffix(sel.dUnit as Unit)} 남았어요`
                      }`}
                    />
                  ))}
                  {sel.triggerBlocked ? (
                    <Stat label="반대 방향" value="안 해요" note={sel.triggerBlocked} />
                  ) : null}
                </StatColumn>
              ) : null}
            </HStack>
              </>
            )}
          </VStack>
        </VStack>
      </HStack>

      {/* 창은 고른 줄이 정한다 — 통합이면 아홉을 한 장부로, 아니면 그 계열
          하나를 재현한다. 만기 줄을 누르면 보드의 선택이 그 만기로 옮겨 가고
          창도 따라 바뀐다(통합에서 낱개로 내려가는 문). */}
      {stratOpen && isBook ? (
        <BookWindow onClose={() => setStratOpen(false)} onPickLeg={setSelId} />
      ) : stratOpen ? (
        <StrategyWindow id={sel.id} label={sel.label} onClose={() => setStratOpen(false)} />
      ) : null}
    </VStack>
  );
}
