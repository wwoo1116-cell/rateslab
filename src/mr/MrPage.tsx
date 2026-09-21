'use client';

/* Mean Reversion — **계획면**: 「지금 어디에 있고, 얼마면 무엇을 하나」.
 *
 * ## 이 화면이 무엇이 됐나 [OWNER 2026-09-21 · 시니어 트레이더 피드백]
 *
 * 2026-08-25 부터 이 화면은 **측정면**이었다: 룩백·밴드 폭 알약이 정한 밴드 위의
 * z·%B·상태와 진입 문턱 하나. 트레이더의 피드백은 그 표가 판단의 **재료**를
 * 직접 말하라는 것이었고("우리가 원하는 조건이 뭔지 명시 … 상태 칸에 토스스타일의
 * 문장으로 … 진입 추천 타점 … 이미 진입했다고 가정한 포지션이 존재한다면 청산
 * 시점과 손절 시점을 데일리로 … 손익도 클릭 없이 캐리·롤다운·평가로 분해 …
 * 전부 1년 백테스트를 중점으로"), 그 답이 `/api/mr/plan` 이다.
 *
 * 오너가 정한 것 넷(다시 묻지 말 것 — 전문은 `backend/app/mrplan.py` 머리):
 *
 *   ① 밴드는 **계열마다** 다르다 — 격자 1등 조건의 밴드다. 그래서 알약 둘이
 *      이 화면에서 내려갔고 그 자리에 읽기 칸이 섰다(전략 창에서 노브 다섯을
 *      내릴 때와 같은 처리 — 화면이 못 고르는 값은 화면이 안 묻는다).
 *   ② 조건은 **전체 표본**에서 고르고 성과·트리거만 **지난 1년**이다.
 *   ③ 청산·손절 레벨을 적는다 — 2026-09-09 의 「트리거는 진입 레벨까지」가
 *      뒤집혔다. **명목은 여전히 안 말한다.**
 *   ④ FSW 변동성 국면 플레이는 측정 먼저(그 레인은 화면 밖이다).
 *
 * ## 안 바뀐 것
 *
 * 숫자는 전부 서버가 끝낸다(§16) — 밴드·z·%B·상태·레벨·거리·포지션·1년 성적과
 * 분해까지. 이 파일은 조건 바와 카드 배치, 그리고 **문장을 어디에 세우나**뿐이고
 * 문장 자체는 `planText.ts` 한 벌이 진다(같은 줄이 표·히어로·상세 셋에 선다).
 * 표 문법은 Main/Backtest 의 것을 그대로 임포트한다(캐논).
 *
 * 통합 줄(BSS 아홉 묶음)과 그 상세 스트립은 종전 그대로다 — 계획면의 행이 보드
 * 행과 **같은 열쇠**를 갖기 때문에 `mrbook.watch` 가 그냥 선다.
 *
 * ## 부분 결과가 정상이다
 *
 * 25계열의 격자+실행이 **약 1분**이라(실측 2026-09-21: 처음부터 66초 · 계열당
 * 1.5~9초) 첫 응답에는 구워진 것만 있다. 화면은 못 구운 수를 **적고** 몇 초 뒤
 * 다시 묻는다 — 빈 표를 조용히 내거나 1분짜리 로딩 화면을 세우지 않는다.
 *
 * ── 배치: 조건 바 + 히어로 + [랭킹 표 | 상세] 2열, 페이지는 스크롤하지 않는다 ──
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@coinbase/cds-web/tables';
import { Text } from '@coinbase/cds-web/typography';

import type { Unit } from '@/lib/api';
import { BacktestUnavailable } from '@/lib/api';
import { fmtDelta, fmtLevel, levelHeadText, levelHeadTitle, unitSuffix } from '@/lib/format';
import { fmtKrw } from '@/lib/krw';
import { BASIS_LABEL } from '@/table/InstrumentTable';
import { ROW_H } from '@/table/rowHeight';
import { directionClass, directionGlyph, tintStyle, unsignedDelta } from '@/table/tint';
import { Cond } from '@/ui/Cond';
import { ErrorState, LoadingState } from '@/ui/DataState';
import { ThHelp } from '@/ui/ThHelp';
import { Stat, StatColumn } from '@/ui/Stat';

import {
  fetchMrPlan,
  fetchMrPlanHistory,
  type MrHistory,
  type MrPlan,
  type MrPlanRow,
  type MrWatch,
} from './api';
import { BandChart } from './BandChart';
import { BookWindow } from './BookWindow';
import { condWord, SplitColumn } from './parts';
import { fmtZ, gap, lvl, perfNote, planLines, stateText } from './planText';
import { StrategyWindow } from './StrategyWindow';

/* `Cond`(조건 바 한 칸)와 `ThHelp`(열 머리 뜻풀이)는 공용이다(`ui/Cond`·
   `ui/ThHelp`) [OWNER 2026-09-02 — "공용 부품은 한 벌로 승격"]. */

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

/* 「위치」 트랙(`.sr-track`)은 2026-09-21 에 이 표에서 **내려갔다**. 한 행이
   같은 사실을 세 번 말하고 있었다 — 「늘어남」이 σ 로, 트랙이 그림으로, 그리고
   새 「지금 할 일」 문장이 말로. 셋 중 둘은 잉크만 늘리고 표를 118px 넘치게
   했다(실측: 표 1,098 대 카드 안폭 981). 밴드 안 어디인지는 만기별 스트립
   (`BookDetail`)이 여전히 트랙으로 말한다 — 거기서는 아홉 줄의 모양이 답이라
   그림이 일을 한다. */

/** 상태 칸 — **두 줄 문장**이다 [OWNER 2026-09-21 — "토스스타일의 문장으로"].
 *
 *  스택은 이름 칸의 그것이다(`sr-name-stack`) — 이 앱이 한 칸에 두 사실을 세울
 *  때 쓰는 유일한 문법이라 새 모양을 만들지 않는다. **활자만 이탈한다**: 이름
 *  칸은 label1(14/600)인데 여기는 **label2**(14/500)다. 이 칸은 이름이 아니라
 *  문장이고, 같은 행의 계열 이름과 같은 굵기로 세우면 둘이 서로 제목처럼 다툰다
 *  (캐논 규칙 3 — 이탈은 사유를 적는다). 문장 자체는 `planText` 한 벌이 짓는다. */
function PlanCell({ r }: { r: MrPlanRow }) {
  const { lead, sub, pnl } = planLines(r);
  return (
    <VStack as="span" className="sr-name-stack">
      {/* 색은 **캐논 한 곳**이 정한다(`table/tint.ts`) — 손으로 매기면 0 에서
          갈린다(캐논은 `sr-flat`, 손 판은 맨 잉크). 돈이 없는 줄은 색도 없다. */}
      <Text
        font="label2"
        as="span"
        noWrap
        className={pnl == null ? undefined : directionClass(pnl)}
      >
        {lead}
      </Text>
      <Text font="legal" as="span" color="fgMuted" noWrap>
        {sub}
      </Text>
    </VStack>
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

/** 고른 계열의 **계획 카드 넷** — 조건·트리거·포지션·지난 1년.
 *
 *  분해(`SplitColumn`)는 다섯째로 서고 **클릭이 필요 없다** [OWNER 2026-09-21 —
 *  "손익에서도 내가 클릭따로 안해도 바로 캐리, 롤다운, 평가 등으로 분해"].
 *  종전에는 전략 실험 창을 열어야 보이던 카드이고, 부품은 그쪽과 **같은 한 벌**
 *  이다(`parts.SplitColumn`) — 두 화면이 「롤다운」을 같은 뜻으로 쓴다. */
function PlanStats({ r, place }: { r: MrPlanRow; place: 'strip' | 'card' }) {
  const unit = r.unit as Unit;
  const dUnit = r.dUnit as Unit;
  /* 레벨·거리 포맷은 **문장과 같은 한 벌**이다(`planText`) — 표의 문장과 이
     카드가 같은 수를 다른 자릿수로 적으면 한 화면이 스스로를 반박한다. */
  const money = (v: number) => fmtKrw(v);
  const lv = (v: number | null | undefined) => lvl(v, unit);
  const gp = (v: number | null | undefined) => gap(v, dUnit);
  const p = r.position;
  /* **셋은 아래(페이지 폭), 둘은 카드 안** [실측 2026-09-21].
     다섯을 다 페이지 폭에 세우면 스트립이 두 줄(220px)이 되고, 855px 화면에서
     표 카드가 268px 로 눌려 **표(360px)가 카드를 넘는다**. 트레이더가 달라고 한
     셋(트리거·포지션·분해)만 아래에 두면 스트립이 한 줄이라 표가 제 키를 지킨다.
     조건·지난 1년은 참고라 카드 안에서 굴러도 된다(1년 손익은 표에도 있다). */
  if (place === 'card') {
    return (
      <HStack className="sr-stats" width="100%" flexWrap="wrap">
        <StatColumn title="조건">
          {/* 문장은 `parts.condWord` 한 벌 — 최적화 표·전략 창과 같은 줄이다. */}
          <Stat label="격자 1등" value={condWord(r.cond)} />
          <Stat
            label="고른 기준"
            value={`CDaR 비 · ${r.cond.cells}칸`}
            note={r.cond.fallback ?? '성과를 잰 그 1년에서 골랐어요'}
          />
          <Stat
            label="회계"
            value={r.real ? '실가격' : '엔진 근사'}
            note={r.real ? '자산스왑 대사' : '롤다운·조달이 없어요'}
          />
        </StatColumn>
        <StatColumn title="지난 1년">
          <Stat
            label="손익"
            value={money(r.perf1y.totalPnl)}
            tone={r.perf1y.totalPnl > 0 ? 'up' : r.perf1y.totalPnl < 0 ? 'down' : undefined}
            note={`${r.perf1y.from ?? '—'} 부터`}
          />
          <Stat label="거래" value={`${r.perf1y.numTrades}건`} note={perfNote(r)} />
          <Stat label="최대 낙폭" value={fmtKrw(-r.perf1y.maxDrawdown)} />
        </StatColumn>
      </HStack>
    );
  }
  return (
    <HStack className="sr-stats" width="100%" flexWrap="wrap">
      {/* 차례가 곧 「먼저 보는 것」이다 [실측 2026-09-21: 다섯 칸이 접히면서
          지난 1년·누적 분해가 접힌 아래(988px)로 내려가 「클릭 없이 바로」가
          안 지켜졌다]. 트리거·포지션·분해를 앞에 세우고 조건·지난 1년을 뒤로
          보낸다 — 조건은 참고이고 1년 손익은 표에 이미 서 있다. */}
      {/* 트리거 — 방향마다 「여기서 들어가면 저기서 나온다」. 막힌 방향은 칸을
          안 만들고 사유를 적는다(rv exclusions 문법). */}
      <StatColumn title="트리거">
        {r.levels.map((l) => (
          <Stat
            key={l.dir}
            label={`${l.short} 진입`}
            value={`${lv(l.entry)} ${l.side === 'above' ? '이상' : '이하'}`}
            note={`${l.legs} · ${gp(l.entryGap)} ${l.entryReached ? '지났어요' : '남았어요'}`}
          />
        ))}
        {r.levels.length === 0 ? (
          <Stat label="문턱" value="—" note="밴드가 아직 못 서요" />
        ) : null}
        {r.triggerBlocked ? (
          <Stat label="반대 방향" value="안 해요" note={r.triggerBlocked} />
        ) : null}
      </StatColumn>

      {/* 포지션 — 백테스트가 표본 끝에 연 다리. 없으면 그 사실을 적는다. */}
      <StatColumn title="포지션">
        {p ? (
          <>
            <Stat label="방향" value={p.short} note={p.legs} />
            <Stat
              label="진입"
              value={lv(p.entryV)}
              note={`${p.entryT} · ${p.bars}일째`}
            />
            <Stat
              label="평가손익"
              value={money(p.pnl)}
              tone={p.pnl > 0 ? 'up' : p.pnl < 0 ? 'down' : undefined}
              note={r.real ? '실가격 회계' : '엔진 근사'}
            />
            <Stat
              label="청산"
              value={p.exit == null ? '—' : lv(p.exit)}
              note={p.exitGap == null ? '밴드가 못 서요' : `${gp(p.exitGap)} 좁혀지면`}
            />
            <Stat
              label="손절"
              value={p.stop == null ? '—' : lv(p.stop)}
              note={p.stopGap == null ? '밴드가 못 서요' : `${gp(p.stopGap)} 더 벌어지면`}
            />
            {/* 중심선을 넘어가 있으면 청산선이 **진입한 쪽이 아니다** — 안 적으면
                화면이 「이미 지난 선」을 가리키는 것처럼 읽힌다. */}
            {p.crossed ? (
              <Stat label="지금 자리" value="중심선 건너" note="청산선이 반대쪽에 있어요" />
            ) : null}
          </>
        ) : (
          <Stat
            label="들고 있는 다리"
            value="없어요"
            note="이 조건으로는 지금 비어 있어요"
          />
        )}
      </StatColumn>

      <SplitColumn split={r.perf1y.split} />
    </HStack>
  );
}

export function MrPage() {
  const [plan, setPlan] = useState<MrPlan>();
  const [error, setError] = useState<string>();
  const [unavailable, setUnavailable] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [selId, setSelId] = useState<string>();
  const [histories, setHistories] = useState<Record<string, MrHistory>>({});
  const [histErr, setHistErr] = useState<string>();
  /* 전략 실험 창 [OWNER 2026-08-25] — 세부는 클릭 뒤 창이 진다(백테스트 문법). */
  const [stratOpen, setStratOpen] = useState(false);

  /* 늦게 온 옛 응답이 이기지 못하게 순번으로 버린다(딥링크·폴링이 겹치는 자리 —
     2026-08-25 라이브 실측의 그 레이스). */
  const loadSeq = useRef(0);
  const load = useCallback(() => {
    const my = ++loadSeq.current;
    setError(undefined);
    setUnavailable(false);
    setRefreshing(true);
    fetchMrPlan()
      .then((p) => {
        if (loadSeq.current === my) setPlan(p);
      })
      .catch((e: unknown) => {
        if (loadSeq.current !== my) return;
        if (e instanceof BacktestUnavailable) setUnavailable(true);
        else setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (loadSeq.current === my) setRefreshing(false);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /* ── 채점이 끝날 때까지 다시 묻는다 ──────────────────────────────────────
     25계열이 약 1분이라 첫 응답은 부분이다. `pending` 이 0 이 되면 **멈춘다** —
     끝난 뒤에도 도는 폴링은 서버를 계속 깨우고, 화면은 그 사실을 말하지 않는다. */
  useEffect(() => {
    if (!plan || plan.pending <= 0) return;
    const t = setTimeout(() => load(), 3000);
    return () => clearTimeout(t);
  }, [plan, load]);

  /* 자료가 갈리면 밴드도 갈린다 — 옛 이력 캐시는 통째로 무효다. */
  const asofKey = plan ? `${plan.asof.bss}|${plan.asof.fut}|${plan.asof.irs}` : '';
  useEffect(() => {
    setHistories({});
    setHistErr(undefined);
  }, [asofKey]);

  /* 레벨 열 머리가 이름할 날짜. 두 소스가 갈리면 하루를 못 고르므로 null 로
     보내 `levelHeadText` 의 폴백(「현재」)에 맡긴다 — 조건 바가 소스별 날짜를
     이미 말하고 있다. */
  const headAsof =
    plan && plan.asof.bss === plan.asof.fut ? plan.asof.bss : null;
  const rows = useMemo(() => plan?.rows ?? [], [plan]);
  const sel: MrPlanRow | undefined = rows.find((r) => r.id === selId) ?? rows[0];
  const selHist = sel ? histories[sel.id] : undefined;
  /* 통합 줄이 골라져 있는가 — 이 줄은 계열이 아니라 집계라 `rows` 에 없고,
     그래서 선택 판정이 따로 선다. 오른쪽 카드와 창이 이 하나로 갈린다. */
  const watch = plan?.watch ?? null;
  const isBook = watch != null && selId === watch.id;

  useEffect(() => {
    const id = sel?.id;
    if (!id || histories[id]) return;
    let dead = false;
    setHistErr(undefined);
    fetchMrPlanHistory(id)
      .then((h) => {
        if (!dead) setHistories((prev) => ({ ...prev, [id]: h }));
      })
      .catch((e: unknown) => {
        /* 아직 안 구워진 계열은 404 다 — 결함이 아니라 「아직」이라고 적는다. */
        if (!dead) {
          setHistErr(e instanceof BacktestUnavailable
            ? '이 계열은 아직 채점 중이에요'
            : e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      dead = true;
    };
  }, [sel?.id, histories]);

  if (unavailable) {
    return (
      <ErrorState
        what="Mean Reversion"
        detail="실행 중인 백엔드(:8200)가 필요하고, 계획면(/api/mr/plan)을 아는 판이어야 해요 — 백엔드를 먼저 올려 주세요."
        onRetry={load}
        retrying={refreshing}
      />
    );
  }
  if (error) {
    return <ErrorState what="Mean Reversion" detail={error} onRetry={load} retrying={refreshing} />;
  }
  if (!plan) {
    return <LoadingState what="Mean Reversion" />;
  }

  return (
    <VStack gap={1.5} width="100%" flexGrow={1} minHeight={0}>
      {/* ── 조건 바 — 어떤 조건에서 나온 숫자인지가 카드보다 먼저 읽힌다 ──── */}
      <VStack className="sr-rv-bar" flexShrink={0} gap={0.5} width="100%">
        <HStack gap={1.5} alignItems="center" flexWrap="wrap">
          {/* 순서는 언제 → 무엇으로(rv 의 판단). 소스가 셋이라 as-of 도 셋이고,
              갈라진 날은 굵기+밑줄이 그 사실을 말한다(rv B-2). */}
          <Cond
            k="민평·IRS"
            v={plan.asof.bss ?? '—'}
            strong={plan.asof.bss !== plan.asof.fut}
          />
          <Cond
            k="선물"
            v={plan.asof.fut ?? '—'}
            strong={plan.asof.bss !== plan.asof.fut}
          />
          {plan.asof.irs ? (
            <Cond
              k="IRS 커브"
              v={plan.asof.irs}
              strong={plan.asof.irs !== plan.asof.bss}
            />
          ) : null}
          {/* 종전에는 룩백·밴드 폭 알약이 섰던 자리 — 이제 **읽기 칸**이다.
              고를 수 없는 값을 고르개로 두면 화면이 없는 손잡이를 약속한다. */}
          <Cond k="조건" v="계열마다 격자 1등 · CDaR 비" />
          {/* 고른 창과 잰 창이 **같다** — 한 칸으로 적는다 [OWNER 2026-09-21 오후].
              두 칸으로 적으면 둘이 다른 창인 것처럼 읽힌다. */}
          <Cond k="격자·성과 창" v="지난 1년" strong />
          <Cond k="비용" v={`편도 ${plan.params.costBp}bp`} />
          <Cond k="Delta" v={`${(plan.params.notional / 10_000).toLocaleString()}만원/bp`} />
          {plan.pending > 0 ? (
            <Cond k="채점" v={`${plan.done}/${plan.total}`} strong />
          ) : null}
          {refreshing ? (
            <Text font="legal" as="span" color="fgMuted" noWrap>
              갱신 중…
            </Text>
          ) : null}
          {/* 논리 속성 — 캐논(`ui/ControlCard`)이 쓰는 그 낱말(marginInlineStart). */}
          <Box style={{ marginInlineStart: 'auto' }}>
            {/* 명구 의무 — Credit RV 와 같은 문법. */}
            <Text font="legal" as="span" color="fgMuted" noWrap>
              백테스트가 말하는 자리예요 — 투자판단이 아니에요.
            </Text>
          </Box>
        </HStack>
        {/* 소스가 셋이 되면서 판정도 셋을 본다 — 종전에는 둘만 비교했다. */}
        {new Set([plan.asof.bss, plan.asof.fut,
                  ...(plan.asof.irs ? [plan.asof.irs] : [])]).size > 1 ? (
          <Text font="legal" as="span" color="fgMuted">
            소스마다 종가 날짜가 달라요 — 각 행은 자기 소스의 날짜 기준이에요.
          </Text>
        ) : null}
        {/* 무엇을 보고 있는지 **화면이 말한다** [OWNER 2026-09-21]. 안 적으면
            읽는 사람이 이 레벨을 「추천 진입가」로 읽는데, 그것은 격자가 표본
            안에서 고른 조건의 밴드 경계일 뿐이다. 명구 의무와 한 몸이다. */}
        <Text font="legal" as="span" color="fgMuted">
          트리거는 계열마다 격자가 고른 조건의 밴드 경계예요 — 조건을 고른 창과 성과를
          잰 창이 같아서(둘 다 지난 1년) 표본내 과적합이 붙어요. 옆의 1년 손익은 162칸
          중 1등의 값이라 성과가 아니라 고른 결과예요. 진입·청산·손절 레벨은 오늘
          밴드라 매일 바뀌고, 명목은 안 말해요.
        </Text>
        {plan.pending > 0 ? (
          <Text font="legal" as="span" color="fgMuted">
            {plan.total}계열 중 {plan.done}계열을 채점했어요 — 순위는 채점된 것들
            안에서예요. 몇 초 뒤에 다시 볼게요.
          </Text>
        ) : null}
        {plan.excluded.length > 0 ? (
          /* 못 읽은 계열 — 조용히 빼지 않는다(rv 의 exclusions 문법). */
          <Text font="legal" as="span" color="fgMuted">
            {plan.excluded.map((x) => `${x.label}: ${x.reason}`).join(' · ')}
          </Text>
        ) : null}
      </VStack>

      {/* ── 히어로 — **1순위를 바로 띄운다** [OWNER 2026-09-09 — "1순위를 바로
          띄우기 … Credit RV에서 은행채 AAA가 가장 매력적이다라고 블록으로
          보여주는 것처럼"] ──────────────────────────────────────────────────
          문법은 rv 의 그 블록을 이식한 것이다: 작은 라벨 한 줄 + 이름이 display3
          로 선 버튼 + 뮤트 메타. 메타 줄이 **계획 문장 둘**을 진다(2026-09-21) —
          블록 하나로 「무엇을·지금 얼마고·얼마면 무엇을 하나」가 닫힌다. */}
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
              {planLines(rows[0]).lead}
            </Text>
          </HStack>
          <Text font="legal" as="span" color="fgMuted">
            {planLines(rows[0]).sub}
          </Text>
        </VStack>
      ) : null}

      {/* ── 2열: 보드가 주인공, 상세가 나머지를 받는다 ───────────────────── */}
      <HStack gap={2} alignItems="stretch" width="100%" flexGrow={1} minHeight={0}>
        <VStack
          className="sr-card"
          /* 820 → **1,060** [2026-09-21 · 브라우저 실측 세 번]. 상태 칸이 문장
             둘이 되고 「1년 손익」 열이 붙으면서 표가 카드보다 넓어졌고, 그건
             「말줄임 금지」의 그 자리다.

             폭을 «오늘 데이터» 로 잡으면 내일 또 넘친다 — 조건이 계열마다 매일
             다시 골라지므로 문장 길이가 **자료에 달렸다**(실측: 격자 표본을
             전체에서 1년으로 바꾸자 25계열의 조건이 전부 갈리고 표가 994 →
             1,027 이 됐다). 그래서 **어휘의 최장**을 캔버스로 재서 잡았다:
             「-99.9bp 이상 · 123.4bp 지났어요 → 긴 쪽 리시브 · 짧은 쪽 페이」
             = 334px(커브 다리 이름이 가장 길다) + 나머지 여섯 열 693 + 카드
             안쪽 여백 → **1,060**. 그보다 긴 조합이 나오면 카드 안에서
             가로로 굴린다(글자를 자르지 않는다). */
          flexBasis={1060}
          flexGrow={0}
          flexShrink={1}
          maxWidth={1060}
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
          {/* 표는 Main/Backtest 의 그 방언이다: CDS Table · 60px 행 · 이름은
              label1 + legal 2줄 스택 · 숫자는 label2 tabular 우측 · **전일은
              틴트 셀**(배경 = 방향 워시, 글자 = 방향색, 부호는 ↗↘ 글리프가 지고
              숫자는 무부호 — `table/tint.ts` 그대로) · 위치는 트랙. */}
          <VStack gap={0} width="100%" minHeight={0} flexGrow={1}>
            <div className="sr-rv-rank-fill">
              <div className="sr-rv-rank-scroll">
                <Table bordered={false}>
                  {/* 머리는 스크롤을 따라온다 — Main 의 `<TableHeader sticky>`. */}
                  <TableHeader sticky>
                    <TableRow>
                      <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                        <Text font="caption" as="span" color="fgMuted">순위</Text>
                      </TableCell>
                      <TableCell as="th" scope="col">
                        <Text font="caption" as="span" color="fgMuted">계열</Text>
                      </TableCell>
                      {/* 레벨 열 머리는 **날짜**다(levelHeadText) — Main·Backtest·
                          매트릭스가 다 그렇다. */}
                      <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                        <Text font="caption" as="span" color="fgMuted" title={levelHeadTitle(headAsof)}>
                          {levelHeadText(headAsof)}
                        </Text>
                      </TableCell>
                      {/* 변화 열 이름은 형제 것을 **임포트**한다 — 문자열로 다시
                          적으면 한쪽만 낡는다(BASIS_LABEL 머리 주석의 그 규칙). */}
                      <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                        <Text font="caption" as="span" color="fgMuted">{BASIS_LABEL.d1}</Text>
                      </TableCell>
                      <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                        <ThHelp
                          label="늘어남"
                          help="지금 값이 그 계열의 조건(격자 1등)이 쓰는 평균에서 σ 몇 개만큼 떨어져 있는지예요. 이 표의 정렬 축이에요."
                        />
                      </TableCell>
                      <TableCell as="th" scope="col">
                        <ThHelp
                          label="지금 할 일"
                          help="포지션이 있으면 청산·손절 레벨을, 없으면 진입 문턱과 남은 거리를 적어요. 레벨은 오늘 밴드라 매일 바뀌어요."
                        />
                      </TableCell>
                      <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
                        <ThHelp
                          label="1년 손익"
                          help="같은 조건으로 지난 1년만 채점한 순손익이에요. 조건 자체는 전체 표본에서 골랐어요."
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
                        aria-current={sel && r.id === sel.id ? 'true' : undefined}
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
                          {/* 이름 + 정의 — Main 의 2줄 스택(label1/legal) 그대로. */}
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
                        <TableCell>
                          <PlanCell r={r} />
                        </TableCell>
                        <TableCell className="sr-num" justifyContent="flex-end">
                          <VStack as="span" className="sr-name-stack">
                            <Text
                              font="label2"
                              as="span"
                              tabularNumbers
                              noWrap
                              className={directionClass(r.perf1y.totalPnl)}
                            >
                              {fmtKrw(r.perf1y.totalPnl)}
                            </Text>
                            <Text font="legal" as="span" color="fgMuted" noWrap>
                              {perfNote(r)}
                            </Text>
                          </VStack>
                        </TableCell>
                      </TableRow>
                    ))}
                    {/* ── BSS 통합 한 줄 [OWNER 2026-09-01 — "밴드워치 랭킹
                        순위, 계열 밑에 따로 하나 빼주면 되겠다"] ──────────────
                        같은 표 안에 두되 헤어라인으로 가른다(`.sr-mr-book`).

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
                        <TableCell>
                          <Text font="label2" as="span" color="fgMuted" noWrap>
                            {watchText(watch)}
                          </Text>
                        </TableCell>
                        {/* 묶음의 1년 손익은 **여기서 못 만든다** — 만기마다 조건이
                            달라 그 아홉을 더한 장부는 이 화면의 수가 아니다.
                            통합 장부 창이 자기 노브로 그것을 센다. */}
                        <TableCell className="sr-num" justifyContent="flex-end">
                          <Text
                            font="label2"
                            as="span"
                            color="fgMuted"
                            noWrap
                            title="만기마다 조건이 달라서 묶음의 1년 손익은 통합 장부 창이 자기 노브로 세요."
                          >
                            {MINUS}
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

        {/* ── 상세 — 선택 계열의 큰 숫자·밴드 이력·계획 카드 ───────────────── */}
        {/* `flexBasis={0}` 이 **왼쪽 표를 지킨다** [실측 2026-09-21]. 기본
            `auto` 는 이 카드의 **max-content** 를 기준으로 삼는데, 스트립이
            다섯 칸으로 늘면서 그 max-content 가 1,280px 을 넘어 왼쪽 카드를
            1,000 → 598 로 눌렀다(표가 517px 넘쳤다). 0 이면 이 카드는 남는
            자리만 받고, 스트립은 그 폭 안에서 접힌다(flexWrap 이 이미 그 일을
            한다). `minWidth` 는 차트가 뭉개지지 않을 하한이다. */}
        <VStack
          className="sr-card"
          flexBasis={0}
          flexGrow={1}
          flexShrink={1}
          minWidth={420}
          minHeight={0}
        >
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
                {isBook && watch ? watch.label : sel?.label ?? '—'}
              </Text>
              <Text font="caption" as="span" color="fgMuted" noWrap>
                {isBook && watch ? watch.defn : sel?.defn ?? ''}
              </Text>
            </HStack>
            <HStack gap={1} alignItems="center">
              <Text font="caption" as="span" color="fgMuted" noWrap>
                {isBook && watch ? (watch.asof ?? '—') : sel?.asof ?? '—'}
              </Text>
              {/* rv 「상세 분석」 자리의 문법 — 세부(전략 재현)는 버튼 뒤 창.
                  통합 줄에서는 **다른 창**이 열린다(아홉을 한 장부로 돌린다). */}
              {sel || isBook ? (
                <button
                  type="button"
                  className="sr-pillbtn"
                  data-on={stratOpen || undefined}
                  aria-pressed={stratOpen}
                  onClick={() => setStratOpen((v) => !v)}
                >
                  {isBook ? '통합 장부' : '전략 실험'}
                </button>
              ) : null}
            </HStack>
          </HStack>
          {/* 카드 안에서 **세로로 굴린다** [실측 2026-09-21: 내용 801 대 카드 501 —
              300px 이 `overflow: hidden` 뒤에 있었고, 하필 트레이더가 달라고 한
              칸들(트리거·포지션·분해)이 거기였다]. 페이지는 여전히 안 굴린다 —
              굴리는 것은 카드 안쪽이고, 부품은 왼쪽 표가 쓰는 그 한 벌이다
              (`.sr-rv-rank-fill`/`-scroll`. 이름은 rv 지만 앱 공용이다 — 캐논
              규칙 2). */}
          <VStack gap={1.5} paddingX={2} paddingBottom={2} width="100%" flexGrow={1} minHeight={0}>
           <div className="sr-rv-rank-fill">
            <div className="sr-rv-rank-scroll">
             <VStack gap={1.5} width="100%">
            {isBook && watch ? (
              <>
                {/* 큰 건 제목이 아니라 숫자다(공간문법). 통합 줄의 그 숫자는
                    레벨이 아니라 **평균 |z|** 다. */}
                <HStack gap={2} alignItems="baseline" flexWrap="wrap">
                  <Text font="display3" as="span" tabularNumbers>
                    {watch.meanAbsZ == null ? '—' : `${watch.meanAbsZ.toFixed(2)}σ`}
                  </Text>
                  <Text font="body" as="span" color="fgMuted">
                    {watchText(watch)}
                  </Text>
                </HStack>
                <BookDetail watch={watch} />
              </>
            ) : sel ? (
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
                  <Text font="body" as="span" color="fgMuted">
                    {planLines(sel).lead}
                  </Text>
                </HStack>
                {selHist ? (
                  <BandChart history={selHist} />
                ) : histErr ? (
                  <Text font="legal" as="span" color="fgMuted">
                    {histErr}
                  </Text>
                ) : (
                  <Text font="legal" as="span" color="fgMuted">
                    이력을 불러오는 중이에요…
                  </Text>
                )}
                {/* 참고 둘 — 캐논대로 **차트 아래**다. 트레이더가 달라고 한
                    셋(트리거·포지션·분해)은 카드 밖 페이지 폭에 선다. */}
                <PlanStats r={sel} place="card" />
              </>
            ) : (
              <Text font="body" as="span" color="fgMuted">
                {plan.excluded.length === plan.total
                  ? '계열을 하나도 못 구웠어요 — 위의 사유를 보세요.'
                  : '채점이 끝나는 대로 계열이 여기 서요.'}
              </Text>
            )}
             </VStack>
            </div>
           </div>
          </VStack>
        </VStack>
      </HStack>

      {/* ── 사실 스트립 — **카드 밖 · 페이지 폭** [실측 2026-09-21] ──────────
          캐논 그대로 차트 **아래**이고(`ui/Stat.tsx`), 다른 것은 **어느 상자
          안인가**뿐이다. 상세 카드 안에 두면 카드가 796px 이라 다섯 칸이 다섯
          줄로 접혀 428px 이 스크롤 뒤로 내려갔다 — 하필 트레이더가 달라고 한
          「클릭 없이 바로 보이는 분해」가 거기였다. 페이지 폭(1,856)에서는 다섯
          칸이 **한 줄**에 선다. 카드 둘이 세로로 준 자리만큼 표가 짧아지지만
          그 표는 원래 안쪽에서 구르는 표다. */}
      <Box flexShrink={0} width="100%">
        {isBook && watch ? (
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
              {/* 종가가 만기마다 갈릴 수 있다 — 민평×IRS 교집합이라 한 만기가
                  하루 안 찍히면 그 다리만 뒤처진다. */}
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
            {/* 통합 줄에는 **계획 카드가 없다** — 만기마다 조건이 달라
                「이 묶음의 진입 레벨」이라는 수가 성립하지 않는다. 그 답은
                통합 장부 창이 자기 노브로 낸다. */}
          </HStack>
        ) : sel ? (
          <PlanStats r={sel} place="strip" />
        ) : null}
      </Box>

      {/* 창은 고른 줄이 정한다 — 통합이면 아홉을 한 장부로, 아니면 그 계열
          하나를 재현한다. 만기 줄을 누르면 보드의 선택이 그 만기로 옮겨 가고
          창도 따라 바뀐다(통합에서 낱개로 내려가는 문). */}
      {stratOpen && isBook ? (
        <BookWindow onClose={() => setStratOpen(false)} onPickLeg={setSelId} />
      ) : stratOpen && sel ? (
        <StrategyWindow id={sel.id} label={sel.label} onClose={() => setStratOpen(false)} />
      ) : null}
    </VStack>
  );
}
