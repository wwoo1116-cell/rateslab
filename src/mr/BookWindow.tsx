'use client';

/* BSS 테너 **통합** 장부 창 [OWNER 2026-09-01 — "BSS만을 활용한 전략을 구상한다고
 * 할 때 지금은 각 테너별로 흩어져있는데, BSS 테너 통합 밴드 워치를 하나 만들어서
 * 승률 및 세부사항들을 확인할 수 있게 해줘"].
 *
 * 낱개 창(`StrategyWindow`)은 **한 만기**를 재현한다. 이 창은 같은 규칙을 아홉
 * 만기에 **동시에** 걸었을 때의 한 장부다. 노브는 공용(`KnobBar`)이고 산술은
 * 서버(`backend/app/mrbook.py`)이며, 계열 하나의 준비·시뮬은 낱개 창과 같은
 * 함수(`main._mr_leg`)라 통합의 수는 낱개 아홉의 합과 갈릴 수 없다.
 *
 * ── 이 창이 낱개 창과 **일부러 다른 것** 셋 ──────────────────────────────────
 *
 * ① **승률은 한 통에 모은 거래의 승률이다.** 아홉 승률의 평균이 아니다 —
 *    거래 수가 6건과 58건인 두 만기를 평균 내면 그 수는 아무것도 아니다.
 * ② **걸린 돈을 말한다.** 동일가중 합이라 아홉이 동시에 서면 Delta 가 아홉 배다.
 *    「최대 동시 다리」와 그 날짜가 없으면 Delta 100만원/bp 라고 적힌 화면이
 *    실제로는 900만원/bp 를 움직인다.
 * ③ **묶어서 나아졌는지를 답한다.** 통합 SR 옆에 개별 SR 중앙값·쌍상관·유효
 *    독립 계열 수가 선다. 그게 없으면 통합은 그냥 큰 숫자일 뿐이다.
 *
 * ── 없는 것도 적어 둔다(디자인 감사 2026-09-02: «의도인지 미완인지 화면이 못
 * 말한다» 는 지적) ────────────────────────────────────────────────────────────
 *
 * · **이웃 칸(노브 민감도)이 두 창 다 없다.** 여기서는 한 칸마다 아홉 계열을
 *   다시 돌아야 해서 열두 칸이면 백여덟 번이고, 낱개 창의 것도 2026-09-02 에
 *   내렸다(사유는 `StrategyWindow` 그 자리 주석 — 견고성 보기이지 고르는
 *   도구가 아니고, 전진분석이 파라미터 선택에 값을 못 더했다). 한 칸 옆이
 *   궁금하면 노브를 옮기고 실행한다.
 * · **표시 구간 탭이 없다.** 낱개 창의 그것은 «한 계열의 곡선을 잘라 본다» 인데,
 *   여기 곡선은 아홉을 더한 장부라 자르면 «구간 순손익» 이 아홉 다리의 진입
 *   시점과 어긋난 조각이 된다(걸쳐 들어온 다리를 어느 구간에 셀지가 정의되지
 *   않는다). 필요해지면 그 정의부터 정하고 붙인다.
 * · **거래 표에 레벨·Δ·다리 레벨 열이 없다.** 낱개 창은 한 만기라 레벨이 한
 *   축이지만 여기 거래는 만기가 섞여 있어, 같은 열에 6M 과 10Y 의 레벨이 세로로
 *   서면 그 열은 더할 수도 비교할 수도 없는 수의 목록이다(§레벨을 만들지 마라).
 *   대사는 만기를 골라 낱개 창에서 한다 — 만기 줄을 누르면 그 창으로 간다.
 * · **일별 대사 서랍이 없다.** 위와 같은 이유로 대사는 «한 다리»의 것이고, 그
 *   자리는 낱개 창의 서랍이다.
 *
 * 명구 의무는 낱개 창과 같다: 재현 도구이고 당일 종가 체결 규약이며 국고 다리는
 * 민평이다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@coinbase/cds-web/tables';
import { Text } from '@coinbase/cds-web/typography';

import { TimeChart, useStackedScales, type TimeLine } from '@/chart/TimeChart';
import type { ScalePriceLine } from '@/chart/ScaleChart';
import { BacktestUnavailable } from '@/lib/api';
import { fmtKrw } from '@/lib/krw';
import { Segmented } from '@/ui/ControlCard';
import { FloatingWindow } from '@/ui/window/FloatingWindow';
import { ReadoutCard, ReadoutFact, ReadoutMoney, placeReadout } from '@/ui/ReadoutCard';
import { Stat, StatColumn } from '@/ui/Stat';

import {
  MR_STRATEGY_DEFAULTS,
  fetchMrBook,
  fetchMrBookOptimize,
  rankCells,
  type MrBookOptimizeRun,
  type MrBookSpan,
  type MrBookSpanLeg,
  type MrOptimizeCell,
  type MrRankKey,
  type MrSpan,
  type MrStrategyParams,
  type MrBookRun,
  type MrBookTrade,
} from './api';
import { MrKnobBar, mrKnobsStale } from './KnobBar';
import { OptimizePane } from './OptimizePane';
import { Panel, RiskAdjusted, SplitColumn, WHY_WORD, fmtRatio, ym } from './parts';

/* 차트 높이 두 급·표 높이 — **낱개 창과 같은 값**(`StrategyWindow` 그 상수:
   Backtest LINKED PAIR 의 200/140). 주인공(누적 곡선)이 크고 파생(동시 다리
   수)이 작다. */
const CHART_H = 200;
const CHART_H_SUB = 140;
const TABLE_H = CHART_H + CHART_H_SUB;

const pct = (v: number) => `${Math.round(v * 100)}%`;

/** `BSS-2Y` → `2Y` — 회계 칸이 만기만 적는다(계열 이름은 이 창에서 전부 BSS 라
 *  접두가 아무 말도 안 한다). 서버의 `mrbook.tenor_of` 와 같은 규칙이다. */
const tenorOf = (sid: string) => sid.split('-').slice(1).join('-');
const bp = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(2)}bp`;

/** 만기별 표의 숫자 한 칸 — 손익만 방향색이다(낱개 창 거래 표와 같은 규칙). */
function Num({ v, tone }: { v: string; tone?: 'up' | 'down' }) {
  return (
    <TableCell className="sr-num" justifyContent="flex-end">
      <Text
        font="label2"
        as="span"
        tabularNumbers
        noWrap
        className={tone === 'up' ? 'sr-up' : tone === 'down' ? 'sr-down' : undefined}
      >
        {v}
      </Text>
    </TableCell>
  );
}

/** 만기별 성적 — **만기 순**이다(랭킹 순이 아니다).
 *
 * 순서가 곧 주장이다: 통합 장부에서 알고 싶은 것은 「어느 만기가 1등인가」가
 * 아니라 「커브의 어디가 버는가」라, 6M→10Y 로 세워야 그 모양이 보인다(실측에서
 * 짧은 쪽이 세다 — `docs/MR_LANE_STATE.md` 의 신호일 앞수익 표).
 */
function LegTable({ legs, onPick }: { legs: MrBookSpanLeg[]; onPick?: (id: string) => void }) {
  return (
    <Box style={{ position: 'relative', height: TABLE_H, overflow: 'auto' }} width="100%">
      <Table bordered={false}>
        <TableHeader sticky>
          <TableRow>
            <TableCell as="th" scope="col">
              <Text font="caption" as="span" color="fgMuted">만기</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="caption" as="span" color="fgMuted">거래</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="caption" as="span" color="fgMuted">승률</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="caption" as="span" color="fgMuted">손익</Text>
            </TableCell>
            {/* 축이 **Calmar** 다 [OWNER 2026-09-07] — 위의 「통합 대 개별」과
                같은 자여야 표와 판정이 갈리지 않는다. 소문자가 있으므로 `legal`
                이다(`caption` 은 대문자화를 걸어 「Calmar」를 「CALMAR」로 만든다). */}
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="legal" as="span" color="fgMuted">Calmar</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="caption" as="span" color="fgMuted">최대 낙폭</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="caption" as="span" color="fgMuted">평균 보유</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="caption" as="span" color="fgMuted">몫</Text>
            </TableCell>
          </TableRow>
        </TableHeader>
        <TableBody>
          {legs.map((g: MrBookSpanLeg) => (
            <TableRow
              key={g.id}
              tabIndex={onPick ? 0 : undefined}
              style={onPick ? { cursor: 'pointer' } : undefined}
              onClick={onPick ? () => onPick(g.id) : undefined}
              onKeyDown={
                onPick
                  ? (e: React.KeyboardEvent) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onPick(g.id);
                      }
                    }
                  : undefined
              }
            >
              <TableCell>
                <Text font="label2" as="span" noWrap>
                  {g.tenor}
                </Text>
              </TableCell>
              <Num v={String(g.numTrades)} />
              <Num v={g.winRate == null ? '—' : pct(g.winRate)} />
              <Num
                v={fmtKrw(g.totalPnl)}
                tone={g.totalPnl > 0 ? 'up' : g.totalPnl < 0 ? 'down' : undefined}
              />
              <Num v={fmtRatio(g.calmar)} />
              <Num v={fmtKrw(-g.maxDrawdown)} />
              <Num v={g.avgBars == null ? '—' : `${g.avgBars.toFixed(1)}봉`} />
              {/* 몫은 **양수 다리에만** 있다 — 총합이 0 이하이거나 이 다리가
                  음수면 서버가 null 을 준다(120% 같은 수를 안 적는다). */}
              <Num v={g.share == null ? '—' : pct(g.share)} />
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

/** 모은 거래에 세울 줄 — 거래들 + **미청산 다리들** [OWNER 2026-09-09 —
 *  "미청산도 PnL에 포함하기"].
 *
 *  낱개 창과 같은 이유다(`StrategyWindow.openAsTrade` 머리): 총손익은 열려 있는
 *  다리를 이미 지고 있는데 목록에는 없어서, 표의 세로합이 누적과 갈렸다. 만기가
 *  섞인 이 표에서는 그 갈림이 더 나빴다 — 「미청산 2다리」라는 숫자만 있고 **어느
 *  만기**인지는 표에 없었다.
 *
 *  「청산」 칸은 청산이 아니라 **마지막 봉**이고 사유 칸이 「미청산」이라고 말한다.
 *  `countOpen` 을 켜면 엔진이 이미 목록에 넣으므로 더하지 않는다. 구 백엔드는
 *  마지막 봉 셋을 모르므로 그때는 종전처럼 거래만 선다.
 *
 *  차례는 **진입일 순**이다 — 서버가 거래를 그렇게 정렬해 보내므로(`mrbook`),
 *  미청산을 뒤에 붙이면 그 줄만 시간 순서에서 튄다. */
function bookRows(run: MrBookRun): MrBookTrade[] {
  const opens: MrBookTrade[] = run.params.countOpen
    ? []
    : run.open
        .filter((o) => o.exitT != null && o.exitV != null)
        .map((o) => ({
          sid: o.sid, label: o.label, tenor: o.tenor,
          entryT: o.entryT, exitT: o.exitT!, dir: o.dir,
          entryZ: o.entryZ, exitZ: o.exitZ ?? null,
          entryV: o.entryV, exitV: o.exitV!,
          pnl: o.pnl, why: 'open' as const,
          mtm: o.mtm ?? 0, carry: o.carry ?? 0, cost: o.cost ?? 0,
          ...(o.rolldown != null ? { rolldown: o.rolldown } : {}),
          ...(o.funding != null ? { funding: o.funding } : {}),
          bars: o.bars,
          outFrom: o.outFrom ?? null, outDays: o.outDays ?? null,
          peakZ: o.peakZ ?? null,
          dv: o.dv ?? 0, dvNet: o.dvNet,
        }));
  return [...run.trades, ...opens].sort((a, b) =>
    a.entryT < b.entryT ? -1 : a.entryT > b.entryT ? 1 : a.sid < b.sid ? -1 : 1,
  );
}

/** 한 통에 모은 거래 — 첫 칸이 **어느 만기**다.
 *
 *  **Δ·레벨 열이 없는 것은 의도다**(이 파일 머리 「없는 것」 목록) — 만기가
 *  섞인 표에서 6M 과 10Y 의 레벨을 한 열에 세로로 세우면 그 열이 무엇인지 말할
 *  수 없다. 2026-09-09 에 낱개 창에 생긴 「순Δ」도 같은 이유로 여기 없다. */
function TradeTable({ run }: { run: MrBookRun }) {
  return (
    <Box style={{ position: 'relative', height: TABLE_H, overflow: 'auto' }} width="100%">
      <Table bordered={false}>
        <TableHeader sticky>
          <TableRow>
            <TableCell as="th" scope="col">
              <Text font="caption" as="span" color="fgMuted">만기</Text>
            </TableCell>
            <TableCell as="th" scope="col">
              <Text font="caption" as="span" color="fgMuted">진입</Text>
            </TableCell>
            <TableCell as="th" scope="col">
              <Text font="caption" as="span" color="fgMuted">청산</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="legal" as="span" color="fgMuted">진입 z</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="legal" as="span" color="fgMuted">청산 z</Text>
            </TableCell>
            <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
              <Text font="caption" as="span" color="fgMuted">손익</Text>
            </TableCell>
            <TableCell as="th" scope="col">
              <Text font="caption" as="span" color="fgMuted">사유</Text>
            </TableCell>
          </TableRow>
        </TableHeader>
        <TableBody>
          {bookRows(run).map((t) => (
            <TableRow key={`${t.sid}-${t.entryT}-${t.exitT}`}>
              <TableCell>
                <Text font="label2" as="span" noWrap>
                  {t.tenor}
                </Text>
              </TableCell>
              <TableCell>
                <Text font="label2" as="span" tabularNumbers noWrap>{t.entryT}</Text>
              </TableCell>
              <TableCell>
                <Text font="label2" as="span" tabularNumbers noWrap>{t.exitT}</Text>
              </TableCell>
              <Num v={`${t.entryZ.toFixed(2)}σ`} />
              {/* 타임스탑 청산은 z=null 봉에 앉을 수 있다(api.ts `exitZ`). */}
              <Num v={t.exitZ == null ? '—' : `${t.exitZ.toFixed(2)}σ`} />
              <Num
                v={fmtKrw(t.pnl)}
                tone={t.pnl > 0 ? 'up' : t.pnl < 0 ? 'down' : undefined}
              />
              <TableCell>
                <Text font="label2" as="span" color="fgMuted" noWrap>
                  {WHY_WORD[t.why]}
                </Text>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

export function BookWindow({
  onClose,
  onPickLeg,
}: {
  onClose: () => void;
  /** 만기 줄을 누르면 보드의 그 계열로 옮겨 간다 — 통합에서 낱개로 내려가는 문. */
  onPickLeg?: (id: string) => void;
}) {
  const [knobs, setKnobs] = useState<MrStrategyParams>(MR_STRATEGY_DEFAULTS);
  const [run, setRun] = useState<MrBookRun>();
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string>();
  const [idx, setIdx] = useState<{ chart: 'eq' | 'legs'; i: number } | null>(null);
  /* 아래쪽 패널이 만기별 성적과 거래 목록 중 무엇을 드는가. 표 둘을 세로로
     쌓으면 창이 두 배가 되고, 나란히 두면 열이 열넷이라 어느 쪽도 안 읽힌다. */
  const [tab, setTab] = useState<'legs' | 'trades'>('legs');
  /* 구간은 **전역 설정값**이다 [OWNER 2026-09-07 — "통합 장부에도 마찬가지로"].
     낱개 창과 같은 계약이고 같은 이유다: 서버가 네 벌을 한 번에 보내므로
     (`run.spans`) 고르개는 이미 와 있는 값을 고르기만 한다 — 재실행도 stale 도
     안 만든다. 엔진은 늘 전체 표본 위에서 돈다(룩백 워밍업이 구간 앞에 있어야
     z 가 선다). */
  const [span, setSpan] = useState<MrSpan>('all');
  const [opt, setOpt] = useState<MrBookOptimizeRun>();
  const [optRunning, setOptRunning] = useState(false);
  const [optError, setOptError] = useState<string>();
  /* 기본 기준은 **CDaR 비**다 [OWNER 2026-09-09] — Calmar 에서 옮겨 왔다.
     근거와 실측(순위상관 0.84 · 1등이 계열에 따라 갈림)은 `api.ts::MR_RANK_KEYS`
     머리와 `docs/EVAL_LANE_STATE.md` §8 에. */
  const [rankKey, setRankKey] = useState<MrRankKey>('cdarRatio');

  /* ── 창을 열면 **격자부터 돈다** [OWNER 2026-09-09 — "둘 다 같은 흐름으로"] ──
     낱개 창과 **같은 흐름**이다(그 창의 `runAuto` 머리에 산술과 근거): 격자
     → 순위 기준 1등 채택 → 그 조건으로 실행. 사람이 고르는 것은 비용·Delta
     뿐이고, 그 둘이 바뀌면 격자부터 다시 돈다.

     ⚠ **여기서는 그 값이 비싸다.** 통합 격자는 162칸마다 만기 아홉을 다시
     도므로 낱개의 아홉 배다(실측 수십 초). 그래도 두 창을 같은 흐름으로 두는
     것이 오너 결정이다 — 한 데스크가 두 창에서 다른 방식으로 일하면 「낱개로는
     벌고 통합으로는 잃는다」가 규칙 탓인지 조작 탓인지 구분이 안 된다. 대신
     화면이 **기다림을 말한다**(노브 줄의 「돌리는 중…」과 최적화 절의 그 줄). */
  const seq = useRef(0);
  const knobsRef = useRef(knobs);
  knobsRef.current = knobs;
  const rankKeyRef = useRef(rankKey);
  rankKeyRef.current = rankKey;

  /** 조건을 꽂고 **그 조건으로 실행**한다 — 채택이 곧 실행이다(노브 줄에서
   *  다섯이 내려가 「실행」 버튼이 조건을 못 바꾼다). */
  const adoptAndRun = useCallback((c: {
    lookback: number; entryZ: number; exitZ: number; stopZ: number;
    entryMode: MrStrategyParams['entryMode'];
  }, my: number) => {
    const next: MrStrategyParams = { ...knobsRef.current, ...c };
    setKnobs(next);
    setError(undefined);
    setRunning(true);
    fetchMrBook(next)
      .then((r) => {
        if (seq.current === my) setRun(r);
      })
      .catch((e: unknown) => {
        if (seq.current !== my) return;
        if (e instanceof BacktestUnavailable) setError('실행 중인 백엔드(:8200)가 필요해요.');
        else setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (seq.current === my) setRunning(false);
      });
  }, []);

  /** 격자 → 1등 채택 → 실행. 격자가 실패해도 창이 비지 않는다(원본 규칙으로
   *  실행하고 왜 격자가 없는지를 최적화 절이 적는다). */
  const runAuto = useCallback(() => {
    const my = ++seq.current;
    setOpt(undefined);
    setOptError(undefined);
    setOptRunning(true);
    fetchMrBookOptimize(knobsRef.current, span)
      .then((o) => {
        if (seq.current !== my) return;
        setOpt(o);
        const best = rankCells(o.cells, rankKeyRef.current)[0];
        adoptAndRun(best ?? knobsRef.current, my);
      })
      .catch((e: unknown) => {
        if (seq.current !== my) return;
        if (e instanceof BacktestUnavailable) setOptError('실행 중인 백엔드(:8200)가 필요해요.');
        else setOptError(e instanceof Error ? e.message : String(e));
        adoptAndRun(knobsRef.current, my);
      })
      .finally(() => {
        if (seq.current === my) setOptRunning(false);
      });
  }, [span, adoptAndRun]);

  /* 다시 도는 자리는 셋뿐이다: 구간 · 비용 · Delta(창은 종목이 없다). */
  useEffect(() => {
    runAuto();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [span, knobs.costBp, knobs.notional]);

  /* 순위 기준이 바뀌면 격자는 그대로, 1등만 다시 고르고 다시 실행한다. */
  const firstRank = useRef(true);
  useEffect(() => {
    if (firstRank.current) {
      firstRank.current = false;
      return;
    }
    if (!opt) return;
    const best = rankCells(opt.cells, rankKey)[0];
    if (best) adoptAndRun(best, ++seq.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rankKey]);

  /** 「채택」 — 조건을 바꾸는 유일한 길이고, 곧 실행이다. */
  const adopt = useCallback((c: MrOptimizeCell) => {
    adoptAndRun(c, ++seq.current);
  }, [adoptAndRun]);

  /* 도는 중에는 stale 을 안 세운다 — 낱개 창의 그 판단과 같다(자동 흐름에서는
     조건을 꽂는 순간과 응답 사이가 늘 «다름» 이라 배너가 깜빡인다). */
  const stale = useMemo(
    () => (run && !running && !optRunning ? mrKnobsStale(run.params, knobs) : false),
    [run, knobs, running, optRunning],
  );
  const dates = useMemo(() => run?.points.map((p) => p.t) ?? [], [run]);
  const stack = useStackedScales();

  /* ── 이 구간의 성적 ────────────────────────────────────────────────────
     서버가 네 벌을 다 보내 온다. 구 백엔드는 이 필드를 모르므로 `undefined`
     이고, 그때 화면은 옛 `summary`(전체 기간)로 **조용히 떨어지지 않는다** —
     그러면 전체 기간의 수를 이 구간의 수인 것처럼 말하게 된다. */
  const perf: MrBookSpan | undefined = useMemo(
    () => run?.spans?.find((b) => b.span === span),
    [run, span],
  );

  const only = run && run.dirs.allowed.length === 1
    ? (run.dirs.allowed[0]! > 0 ? run.dirs.plus : run.dirs.minus)
    : null;

  /* 「실전 규칙이 켜져 있어요」 각주는 **없앴다** [2026-09-02 검사] — 낱개 창과
     같은 이유다(노브를 화면에서 내린 뒤로 기본값 밖으로 갈 경로가 없어 도달
     불가였고, 「끄면」이라고 말하면서 끌 컨트롤이 없는 화면이 된다). */

  /* 손익 곡선은 부호가 색을 정한다 — LinkedCharts 누적 손익의 그 문법. */
  const eqHue = (run?.summary.totalPnl ?? 0) >= 0 ? 'var(--sr-up)' : 'var(--sr-down)';
  const eqLines: TimeLine[] = !run ? [] : [
    {
      id: 'cum',
      values: run.points.map((p) => p.cum),
      color: (pa) => pa.resolve(eqHue),
      area: 'solid',
      areaColor: (pa) => pa.dim(eqHue, 14),
      format: (v: number) => fmtKrw(v),
    },
  ];
  /* 동시 다리 수 — **계단**이다. 하루 사이에 0.4다리 같은 것은 없고, 부드러운
     선으로 그리면 없는 중간값을 그림이 지어낸다(기준금리 선의 그 규칙). */
  const legLines: TimeLine[] = !run ? [] : [
    {
      id: 'legs',
      values: run.points.map((p) => p.legs),
      color: (pa) => pa.fg,
      step: true,
      area: 'solid',
      areaColor: (pa) => pa.dim('var(--color-fg)', 10),
      format: (v: number) => `${v}다리`,
    },
  ];
  const zeroLine: ScalePriceLine[] = [{ value: 0, color: (pa) => pa.line }];
  /* 아홉이 다 선 자리 — 「여기가 Delta 의 천장」을 그림이 스스로 말한다. */
  const capLine: ScalePriceLine[] = !run ? [] : [
    { value: 0, color: (pa) => pa.line },
    { value: run.legs.length, color: (pa) => pa.lineHeavy, dash: true },
  ];

  return (
    <FloatingWindow
      windowKey="mrbook"
      title="BSS 통합 장부"
      width={1120}
      /* 창 머리 부제는 caption — Backtest 「{asOf} 종가까지」와 같은 급이다. */
      aside={
        <Text font="caption" as="span" color="fgMuted" noWrap>
          아홉 만기를 같은 규칙으로 동시에 — 재현 도구예요, 투자판단이 아니에요.
        </Text>
      }
      onClose={onClose}
    >
      {/* 창 몸통 리듬은 **Backtest 창과 한 값**(padding 2 · gap 2) — 낱개 창도
          같다. 떠 있는 창들이 같은 위계면 안쪽 여백도 같아야 한다(얼라인 5). */}
      <VStack gap={2} padding={2} width="100%">
        <MrKnobBar
          lead={run ? `BSS 만기 ${run.legs.length}개` : 'BSS 전 만기'}
          leadLabel="장부"
          knobs={knobs}
          onChange={(patch) => setKnobs((k) => ({ ...k, ...patch }))}
          onRun={runAuto}
          running={running || optRunning}
          span={span}
          onSpanChange={setSpan}
          /* 서버가 실제로 채점한 구간을 적는다 — 화면이 달력을 다시 세지
             않는다(두 자가 갈리면 카드와 곡선이 다른 구간을 말한다). */
          spanNote={!perf || span === 'all' ? undefined
            : `${perf.from ?? '—'} 부터 ${perf.days.toLocaleString()}봉 — 성과·만기별·최적화가 이 구간에서 채점돼요.`}
        />
        {/* 상태 문구의 활자는 Backtest 와 한 벌 — 안내는 `body` 뮤트, 오류는
            `body` + `.sr-up`(앱 공통 오류 문법). 낱개 창도 같다. */}
        {stale ? (
          <Text font="body" as="p" color="fgMuted">
            설정이 실행과 달라요 — 「다시 돌리기」를 눌러야 아래 숫자에 반영돼요.
          </Text>
        ) : null}
        {error ? (
          <Text font="body" as="p" className="sr-up">
            실행하지 못했어요 — {error}
          </Text>
        ) : null}
        {run && run.excluded.length ? (
          /* 못 선 만기는 조용히 빠지지 않는다 — 여덟의 합을 「아홉 만기 통합」
             이라 부르면 화면이 거짓말을 한다(보드의 exclusions 문법). */
          <Text font="legal" as="span" color="fgMuted">
            {run.excluded.map((x) => `${x.label}: ${x.reason}`).join(' · ')}
          </Text>
        ) : null}

        {!run ? (
          <Text font="body" as="p" color="fgMuted">
            {/* 자동 흐름이라 «누르면» 이 아니다 — 창을 열면 격자부터 돈다
                [OWNER 2026-09-09]. 통합은 격자가 만기 아홉을 다시 도므로 이
                기다림이 수십 초다: 무엇을 기다리는지 화면이 말해야 한다. */}
            {optRunning ? '격자를 도는 중이에요 — 162칸마다 만기 아홉을 다시 재요(수십 초).'
              : running ? '아홉 만기를 돌리는 중이에요…'
              : '창을 열면 최적화 격자부터 돌아요.'}
          </Text>
        ) : (
          <>
            {!perf ? (
              /* 구 백엔드 — 조용히 전체 기간(`summary`)으로 떨어지지 않는다.
                 그러면 화면이 전체 기간의 수를 이 구간의 수인 것처럼 말한다. */
              <Text font="body" as="p" color="fgMuted">
                구간별 성과는 새 백엔드가 필요해요 — 지금 백엔드는 전체 기간
                하나만 보내고 있어요.
              </Text>
            ) : (
            <HStack className="sr-stats" width="100%" flexWrap="wrap">
              <StatColumn title="성과">
                <Stat
                  label="총손익"
                  value={fmtKrw(perf.totalPnl)}
                  tone={
                    perf.totalPnl > 0 ? 'up' : perf.totalPnl < 0 ? 'down' : undefined
                  }
                  note={`${perf.days.toLocaleString()}봉 · ${perf.from}~${perf.to}`}
                />
                <Stat label="최대 낙폭" value={fmtKrw(-perf.maxDrawdown)} />
                {/* 낙폭의 **길이** — 깊이만 적으면 「얼마나 오래 물속이었나」를
                    화면이 안 말한다. 샤프가 있던 자리이고, 절대수익형 평가가
                    실제로 답해야 하는 물음이 이쪽이다. */}
                <Stat
                  label="회복일"
                  value={perf.recoveryDays == null ? '—' : `${perf.recoveryDays}일`}
                  note={perf.recoveryDays == null
                    ? '낙폭이 없었어요'
                    : perf.recovered ? '골에서 전고점까지' : '아직 회복 못 했어요'}
                />
                <Stat
                  label="승률"
                  value={perf.winRate == null ? '—' : pct(perf.winRate)}
                  /* **분모를 말한다.** 아홉 승률의 평균이 아니라 모은 거래의
                     승률이고, 미청산 다리는 원본 규약대로 여기 안 든다. */
                  note={
                    run.summary.openLegs === 0
                      ? `${perf.numTrades}거래를 한 통에`
                      : run.params.countOpen
                        ? `미청산 ${run.summary.openLegs}다리 포함`
                        : `미청산 ${run.summary.openLegs}다리 제외`
                  }
                />
                <Stat
                  label="거래"
                  value={String(perf.numTrades)}
                  note={perf.numTrades === run.summary.numTrades
                    ? undefined : `전체 ${run.summary.numTrades}건`}
                />
                {run.summary.openPnl != null ? (
                  <Stat
                    label="미청산"
                    value={fmtKrw(run.summary.openPnl)}
                    tone={run.summary.openPnl > 0 ? 'up' : run.summary.openPnl < 0 ? 'down' : undefined}
                    note={`${run.summary.openLegs}다리`}
                  />
                ) : null}
              </StatColumn>

              {/* 절대수익형 일곱 — 낱개 창과 **같은 부품**이다(`parts.RiskAdjusted`).
                  샤프가 여기서 내려갔다 [OWNER 2026-09-04 · 2026-09-07]. */}
              <RiskAdjusted perf={perf} />

              {/* 누적 분해 [OWNER 2026-09-09 — "누적 채권 + 스왑 손익을 롤다운
                  캐리로 분해해서 보여주기"] — 낱개 창과 **같은 부품**이다.
                  이 창에서는 아홉 다리의 봉을 한 통에 모아 더한 값이고(다리별
                  분해는 「만기별 성적」이 진다), 한 다리라도 그 성분이 없으면
                  그 칸이 «—» 다(`backend/app/mrbook.py::_pooled_parts`). */}
              <SplitColumn split={perf.split} />

              {/* 걸린 돈 — 동일가중 합의 **대가**다. 이 칸이 없으면 「Delta
                  100만원/bp」가 실제로 움직인 돈을 최대 아홉 배 작게 말한다.

                  낱말은 **노브를 따라간다** [OWNER 2026-09-04 «Strategy에서 명목이
                  아니라 Delta라고 하기», 2026-09-07 에 이 창까지]. 같은 노브가
                  두 창에서 다른 이름으로 서면 읽는 사람은 다른 수라고 읽는다. */}
              <StatColumn title="장부">
                <Stat
                  label="최대 동시"
                  value={`${run.book.maxLegs}다리`}
                  note={run.book.peakT ?? undefined}
                />
                <Stat
                  label="그때 Delta"
                  value={`${run.book.peakNotional.toLocaleString()}원/bp`}
                  note={`Delta ${run.params.notional.toLocaleString()} × ${run.book.maxLegs}`}
                />
                <Stat
                  label="평균 동시"
                  value={run.book.meanLegs == null ? '—' : `${run.book.meanLegs.toFixed(2)}다리`}
                />
                <Stat
                  label="무포지션"
                  value={run.book.idleShare == null ? '—' : pct(run.book.idleShare)}
                  note="다리가 하나도 없던 날"
                />
              </StatColumn>

              <StatColumn title="조건">
                <Stat
                  label="비용"
                  value={run.cost.model === 'flat'
                    ? `편도 ${run.cost.bp}bp`
                    : `편도 ${run.cost.lo}~${run.cost.hi}bp`}
                  note={run.cost.model === 'dynamic' ? `동적 · 중앙 ${run.cost.mid}bp` : undefined}
                />
                {run.summary.breakevenCostBp != null ? (
                  <Stat
                    label="손익분기 비용"
                    value={`편도 ${run.summary.breakevenCostBp.toFixed(2)}bp`}
                    tone={run.summary.breakevenCostBp <= run.params.costBp ? 'down' : undefined}
                    note={
                      run.summary.breakevenCostBp <= run.params.costBp
                        ? '지금 비용에서 이미 손실'
                        : `여유 ${(run.summary.breakevenCostBp - run.params.costBp).toFixed(2)}bp`
                    }
                  />
                ) : run.summary.breakevenCostMult != null ? (
                  <Stat
                    label="손익분기 비용"
                    value={`지금 경로의 ${run.summary.breakevenCostMult.toFixed(1)}배`}
                    tone={run.summary.breakevenCostMult <= 1 ? 'down' : undefined}
                    note={run.summary.breakevenCostMult <= 1 ? '지금 비용에서 이미 손실' : undefined}
                  />
                ) : null}
                <Stat label="종가" value={run.asof ?? '—'} />
                {/* ── 회계 [2026-09-09, krw-crs 레인이 잡아 보낸 결함] ──────────
                    이 장부의 돈이 **실가격 대사**에서 나왔는지 **엔진 근사**에서
                    나왔는지를 말한다. 낱개 창(`real`)과 격자(`headReal`)는 종전에도
                    말했는데 **이 창만 안 말했다** — 그런데 다리마다 갈릴 수 있으므로
                    합계가 두 회계를 더한 수일 수 있다(레인 실측: 격자 162칸 중
                    42칸이 섞임 · 이 화면 기본 노브에서는 9/9 실가격).

                    **「근사」로 뭉뚱그리지 않는다** — 8/9 와 0/9 가 같은 말이 되면
                    안 되므로 센 수를 적고, 섞였으면 **어느 다리인지 이름**을 적는다
                    (「빈칸으로 렌더하느니 이유를 쓴다」 — `MR_RECON_WHY` 의 그 규율).
                    구 백엔드는 필드가 없다: 그때 «실가격» 으로 조용히 떨어지지 않고
                    모른다고 말한다. */}
                {run.accounting ? (
                  <Stat
                    label="회계"
                    value={run.accounting.real === run.accounting.total
                      ? '실가격'
                      : `실가격 ${run.accounting.real}/${run.accounting.total}`}
                    tone={run.accounting.real === run.accounting.total ? undefined : 'down'}
                    note={run.accounting.real === run.accounting.total
                      ? '자산스왑 대사'
                      : [
                          run.accounting.approx.length
                            ? `엔진 근사: ${run.accounting.approx.map(tenorOf).join(' · ')}`
                            : null,
                          run.accounting.unknown.length
                            ? `모름: ${run.accounting.unknown.map(tenorOf).join(' · ')}`
                            : null,
                        ].filter(Boolean).join(' · ')}
                  />
                ) : (
                  <Stat label="회계" value="모름" note="이 백엔드는 회계를 안 말해요" />
                )}
                <Stat label="방향" value={only ? only.legs : '양방향'} />
                {run.dirs.why ? (
                  <Stat
                    label="막힌 진입"
                    value={`${run.dirs.blocked.spells}회`}
                    note={`만기 ${run.legs.length}개 합계`}
                  />
                ) : null}
                {run.params.regime !== 'none' ? (
                  <Stat
                    label="필터가 지운 진입"
                    value={`${run.gated.spells}회`}
                    note={run.gated.spells === 0 ? '한 건도 안 막았어요' : `${run.gated.days}일`}
                  />
                ) : null}
              </StatColumn>
            </HStack>
            )}

            {/* ── 묶어서 나아졌나 — 이 창의 존재 이유를 한 줄이 답한다 ───────
                구간을 따라간다 [OWNER 2026-09-07] — 위 카드가 「지난 1분기」인데
                이 절만 전체 기간이면 한 화면이 두 구간을 말한다. */}
            {!perf ? null : (
            <VStack gap={0.5} width="100%">
              <HStack gap={1} alignItems="baseline" justifyContent="space-between">
                <Text font="label2" as="h3" noWrap>
                  묶어서 나아졌나
                </Text>
                <Text font="legal" as="span" color="fgMuted">
                  낙폭 대비로 재요 — 유효 독립은 「왜 그만큼인지」의 사정이에요
                </Text>
              </HStack>
              <HStack className="sr-stats" width="100%" flexWrap="wrap">
                {/* 축이 **Calmar** 다 [OWNER 2026-09-07] — 샤프에서 갈렸다.
                    그러면서 이 절이 답하는 질문도 갈렸다는 것을 적어 둔다:
                    샤프판에서는 바로 옆 「유효 독립」과 산술이 맞물렸다(SR 은
                    1/σ 로 움직이므로 통합/개별 ≈ √N_eff 가 검산이었다). Calmar
                    의 분모는 최대낙폭이라 **그 검산이 안 선다** — 최대낙폭은
                    경로의 한 점이라 √N 으로 줄지 않는다. 지금 묻는 것은
                    «묶어서 낙폭 대비가 나아졌나» 이고, 유효 독립은 그 옆에서
                    사정을 말한다. */}
                <StatColumn title="통합 대 개별">
                  <Stat label="통합 Calmar" value={fmtRatio(perf.calmar)} />
                  <Stat
                    label="개별 Calmar 중앙"
                    value={fmtRatio(perf.legCalmar.median)}
                    note={
                      perf.legCalmar.min == null || perf.legCalmar.max == null
                        ? undefined
                        : `${fmtRatio(perf.legCalmar.min)} ~ ${fmtRatio(perf.legCalmar.max)}`
                    }
                  />
                  <Stat
                    label="양수 만기"
                    value={`${perf.legCalmar.positive}/${perf.legCalmar.n}`}
                    /* **잰 다리 수를 말한다.** 낙폭이 0 인 다리는 Calmar 가
                       없어서 안 센다 — 0 으로 채우면 그 다리가 «최악» 으로 줄을
                       서서 중앙값을 끌어내린다. */
                    note={perf.legCalmar.n === perf.legCalmar.of
                      ? 'Calmar 기준'
                      : `Calmar 기준 · ${perf.legCalmar.of}개 중 ${perf.legCalmar.n}개만 잴 수 있어요`}
                  />
                </StatColumn>
                <StatColumn title="분산">
                  <Stat
                    label="평균 쌍상관"
                    value={
                      perf.diversification.meanPairCorr == null
                        ? '—'
                        : perf.diversification.meanPairCorr.toFixed(3)
                    }
                    /* **몇 봉에서 쟀는지**를 같이 적는다. 「지난 1개월」이면 봉이
                       스물 남짓이라 ρ̄ 의 표준오차가 0.2 를 넘는다 — 그 수를
                       「분산이 좋아졌다」로 읽으면 안 된다. */
                    note={`일별 손익끼리 · ${perf.diversification.days.toLocaleString()}봉`}
                  />
                  <Stat
                    label="유효 독립"
                    value={
                      perf.diversification.effectiveN == null
                        ? '—'
                        : `${perf.diversification.effectiveN.toFixed(1)}/${perf.diversification.n}`
                    }
                    note="N / (1 + (N−1)·상관)"
                  />
                </StatColumn>
                <StatColumn title="승률의 출처">
                  {run.diag.exits.map((e) => (
                    <Stat
                      key={e.why}
                      label={WHY_WORD[e.why]}
                      value={`${e.n}건 · ${pct(e.winRate)}`}
                      note={`평균 ${bp(e.avgBp)} · ${e.avgBars.toFixed(1)}일`}
                    />
                  ))}
                  {run.diag.payoff ? (
                    <Stat
                      label="손익비"
                      value={run.diag.payoff.payoff == null ? '—' : run.diag.payoff.payoff.toFixed(2)}
                      /* 프로핏팩터가 1 아래면 승률이 아무리 높아도 돈을 잃는다. */
                      tone={
                        run.diag.payoff.profitFactor != null && run.diag.payoff.profitFactor < 1
                          ? 'down'
                          : undefined
                      }
                      note={
                        run.diag.payoff.profitFactor == null
                          ? `이긴 ${run.diag.payoff.wins} / 진 ${run.diag.payoff.losses}`
                          : `프로핏팩터 ${run.diag.payoff.profitFactor.toFixed(2)}`
                      }
                    />
                  ) : null}
                </StatColumn>
                {/* **표본 삼분할은 항상 전체 위에 선다** [OWNER 2026-09-07].
                    이건 «시대가 바뀌어도 사나» 를 재는 안정성 검사라 채점
                    구간과 무관하다 — 「지난 1개월」을 다시 셋으로 쪼개면 한
                    조각이 열흘이라 수가 뜻을 잃는다. 그래서 제목이 「구간별」이
                    아니라 **「표본 삼분할」**이다: 옆 카드가 「지난 1분기」인데
                    이 열만 2020년부터면, 이름이 그 사실을 말해야 한다.

                    ⚠ SR 이 여기 남는다. 삼분할은 «분산이 시대마다 사나» 를 재는
                    자리라 σ 기반이 맞고, 위의 「통합 대 개별」이 Calmar 로 간 것과
                    **다른 질문**이다. 한 화면에 두 자가 서므로 이름과 각주가
                    그 사실을 적는다. */}
                {run.diag.periods.length ? (
                  <StatColumn title="표본 삼분할">
                    {run.diag.periods.map((p) => (
                      <Stat
                        key={p.from}
                        label={`${ym(p.from)}~${ym(p.to)}`}
                        value={p.sharpe == null ? '—' : `SR ${p.sharpe.toFixed(2)}`}
                        note={fmtKrw(p.totalPnl)}
                      />
                    ))}
                  </StatColumn>
                ) : null}
              </HStack>
              {run.diag.periods.length ? (
                <Text font="legal" as="p" color="fgMuted">
                  표본 삼분할은 고른 구간과 무관하게 전체 표본을 셋으로 나눈
                  것이에요 — 시대가 바뀌어도 사는지를 재는 자리라, 짧은 구간을
                  다시 쪼개면 한 조각이 열흘이 돼요. 축이 SR 인 것도 그 때문이에요
                  (위 「통합 대 개별」은 낙폭 대비라 다른 질문이에요).
                </Text>
              ) : null}
            </VStack>
            )}

            {/* ── 곡선 둘, 표 하나 = **LINKED PAIR 의 세로 결**(Backtest
                `LinkedCharts`). `Panel` 은 이제 풀폭이 정본이고(2026-09-02,
                낱개 창과 공용), x 라벨은 **위 곡선만** 지고 아래는 숨긴다 —
                같은 눈금을 두 번 그리면 다른 축으로 읽힌다. 십자선은
                `syncIndex` 로 반대쪽에 건넨다. */}
            <VStack gap={2} width="100%">
              <Panel
                title="누적 손익"
                sub={`${run.summary.numTrades} 거래 · 순 ${fmtKrw(run.summary.totalPnl)}`}
              >
                <Box
                  className="sr-plot"
                  width="100%"
                  onMouseMove={(e: React.MouseEvent<HTMLDivElement>) => placeReadout(e.currentTarget, e.clientX)}
                  onMouseLeave={() => setIdx(null)}
                >
                  <TimeChart
                    height={CHART_H}
                    accessibilityLabel="BSS 통합 누적 손익"
                    hoverLabel={(i) => `${dates[i]} 누적 ${fmtKrw(run.points[i]!.cum)}`}
                    syncIndex={idx && idx.chart !== 'eq' ? idx.i : null}
                    dates={dates}
                    lines={eqLines}
                    priceLines={zeroLine}
                    onHoverIndex={(i) => setIdx(i == null ? null : { chart: 'eq', i })}
                    {...stack}
                  />
                  {idx?.chart === 'eq' && run.points[idx.i] ? (
                    <ReadoutCard title={run.points[idx.i]!.t}>
                      <ReadoutMoney k="누적" v={run.points[idx.i]!.cum} />
                      <ReadoutMoney k="그날" v={run.points[idx.i]!.pnl} />
                      <ReadoutFact k="다리" v={`${run.points[idx.i]!.legs}개`} />
                    </ReadoutCard>
                  ) : null}
                </Box>
              </Panel>

              <Panel
                title="동시 보유 다리"
                sub={`최대 ${run.book.maxLegs} · 평균 ${run.book.meanLegs?.toFixed(2) ?? '—'} · 무포지션 ${
                  run.book.idleShare == null ? '—' : pct(run.book.idleShare)
                }`}
              >
                <Box
                  className="sr-plot"
                  width="100%"
                  onMouseMove={(e: React.MouseEvent<HTMLDivElement>) => placeReadout(e.currentTarget, e.clientX)}
                  onMouseLeave={() => setIdx(null)}
                >
                  <TimeChart
                    height={CHART_H_SUB}
                    accessibilityLabel="BSS 통합 동시 보유 다리 수"
                    hoverLabel={(i) => `${dates[i]} 다리 ${run.points[i]!.legs}개`}
                    syncIndex={idx && idx.chart !== 'legs' ? idx.i : null}
                    hideTimeAxis
                    dates={dates}
                    lines={legLines}
                    priceLines={capLine}
                    onHoverIndex={(i) => setIdx(i == null ? null : { chart: 'legs', i })}
                    {...stack}
                  />
                  {idx?.chart === 'legs' && run.points[idx.i] ? (
                    <ReadoutCard title={run.points[idx.i]!.t}>
                      <ReadoutFact k="다리" v={`${run.points[idx.i]!.legs}개`} />
                      <ReadoutFact
                        k="걸린 Delta"
                        v={`${(run.points[idx.i]!.legs * run.params.notional).toLocaleString()}원/bp`}
                      />
                      <ReadoutMoney k="그날" v={run.points[idx.i]!.pnl} />
                    </ReadoutCard>
                  ) : null}
                </Box>
              </Panel>

              <Panel
                title={tab === 'legs' ? '만기별 성적' : '거래'}
                sub={
                  tab === 'legs'
                    ? onPickLeg
                      /* 누르면 창이 바뀐다 — 그 사실을 안 적으면 눌러 보고 나서야
                         안다(랭킹 표의 «줄을 누르면 이력이 열려요» 와 같은 규율). */
                      ? '만기 순이에요 — 줄을 누르면 그 만기의 낱개 창으로 바뀌어요'
                      : '만기 순이에요 — 커브의 어디가 벌었는지가 순위로는 안 보여요'
                    : `${run.summary.numTrades}건을 한 통에${only ? ` · ${only.legs}` : ''}`
                }
                /* 둘 중 하나를 고르는 **배타 선택**이라 캐논 `Segmented` 다
                   [2026-09-02 간격 감사 — 노브 여섯이 그리로 갔는데 이 자리만
                   손 알약으로 남아 있었다]. 폭은 감싸는 상자가 지고(`fill`),
                   132 = 「만기별」·「거래」가 세그먼트 패딩(16+16)과 함께 서는
                   자연폭에 여유 — 라벨이 길어지면 다시 잰다. */
                aside={
                  <Box width={132}>
                    <Segmented
                      fill
                      label="보기"
                      value={tab}
                      options={[
                        { value: 'legs' as const, label: '만기별' },
                        { value: 'trades' as const, label: '거래' },
                      ]}
                      onChange={(v) => setTab(v)}
                    />
                  </Box>
                }
              >
                {tab === 'legs'
                  ? (perf
                      ? <LegTable legs={perf.legs} onPick={onPickLeg} />
                      : (
                        <Text font="body" as="p" color="fgMuted">
                          만기별 성적은 새 백엔드가 필요해요 — 지금 백엔드는 전체
                          기간 하나만 보내고 있어요.
                        </Text>
                      ))
                  : <TradeTable run={run} />}
              </Panel>
            </VStack>

            {/* 근사 최적화 — **낱개 창과 같은 부품**이다(`OptimizePane`).
                여기서 정하는 것은 안내·경고 문장 둘뿐이다. */}
            <OptimizePane
              opt={opt}
              error={optError}
              running={optRunning}
              rankKey={rankKey}
              onRankKey={setRankKey}
              span={span}
              headReal={opt?.headReal ?? false}
              onRun={runAuto}
              onAdopt={adopt}
              currentParams={run.params}
              intro={'격자를 아직 못 돌렸어요 — 룩백 3 × 진입 3 × 청산 3 × 손절 3 × 진입 규칙 2 = 162칸을 '
                + `만기 ${run.legs.length}개에 동시에 걸어 이 구간에서 채점해요 — 칸마다 `
                + '아홉을 더한 장부를 재요 — 다리별 값의 평균이 아니에요(Calmar·'
                + '낙폭은 비선형이라 더한 뒤에 재야 「묶어서 나아졌나」가 답이 돼요). '
                + '한 칸이 아홉 배라 몇 초 걸려요. 비용·Delta 와 실전 규칙은 안 흔들어요.'}
              extraNote={`한 칸이 만기 ${run.legs.length}개를 같이 흔들어요 — 표본내 격자라 `
                + '1등 칸을 그대로 믿으면 과적합이 그만큼 배로 붙어요.'}
            />

            <Text font="legal" as="span" color="fgMuted">
              만기 {run.legs.length}개에 각각 Delta {run.params.notional.toLocaleString()}원/bp 를
              걸고 일별 손익을 더한 장부예요 — 승률·손익비는 아홉 목록을 한 통에 모아서
              셌어요(아홉 승률의 평균이 아니에요). 동시에 선 다리가 최대 {run.book.maxLegs}개라
              그날 걸린 돈은 {run.book.peakNotional.toLocaleString()}원/bp 예요.{' '}
              {run.dirs.why
                ? `${run.dirs.why} 그래서 못 들어간 진입 신호가 만기 ${run.legs.length}개 합계 ${run.dirs.blocked.spells}회(${run.dirs.blocked.days}일) 있어요. `
                : ''}
              {run.carry.on && run.carry.defn
                ? `캐리는 ${run.carry.defn}이고 조달은 ${run.carry.funding} 이에요. `
                : ''}
              노브 민감도는 위 「근사 최적화」가 답해요 — 162칸을 만기{' '}
              {run.legs.length}개에 동시에 걸어 지금 칸의 등수를 매겨요. 종전에는 이 자리에
              「두 창 다 없어요」라고 적혀 있었고 그건 이제 사실이 아니에요. 다만 그때 적어 둔
              경고는 그대로예요: 표본내 격자라 1등 칸이 표본외에서도 1등이라는 보장이 없고,
              전진분석이 파라미터 선택에 값을 못 더한다는 실측도 그대로예요. 국고 다리는
              민평(평가사 고시) 기준이고 당일 종가 체결 규약이에요.
            </Text>
          </>
        )}
      </VStack>
    </FloatingWindow>
  );
}
