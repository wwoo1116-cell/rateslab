'use client';

/* 근사 최적화 절 — **두 창이 같은 표를 세운다** [OWNER 2026-09-04 · 2026-09-07].
 *
 * 낱개 창(`StrategyWindow`)이 먼저 가졌고, 2026-09-07 에 통합 장부(`BookWindow`)
 * 가 같은 것을 요구하면서 여기로 갈라 냈다. 복제하면 한쪽만 낡는다 —
 * CLAUDE.md 얼라인 8(«같은 것은 한 번만 만든다»)이고, 이 리포에서 `Field` 가
 * 네 곳에 따로 정의돼 라벨 활자가 셋으로 갈렸던 그 자리와 같은 종류다.
 *
 * ## 두 창의 «다름» 은 무엇인가
 *
 * 격자의 **모양은 같다**(다섯 노브의 프리셋 · 같은 지표 · 같은 순위 기준).
 * 다른 것은 한 칸의 값이 계열 하나냐 아홉을 더한 장부냐이고, 그건 서버가 이미
 * 가른다(`/api/mr/optimize` 대 `/api/mr/book/optimize`). 화면이 아는 차이는
 * 둘뿐이라 **문장으로만** 받는다:
 *
 *   `intro`      안 돌렸을 때의 안내 — 칸 수와 무엇을 안 흔드는지
 *   `extraNote`  창별 경고 — 통합은 「만기 아홉이 같이 흔들린다」를 더 적는다
 *
 * 그 둘을 prop 이 아니라 창 안에서 분기로 쓰면, 이 파일이 두 창을 알게 되고
 * 셋째 창이 생길 때 다시 갈라야 한다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import {
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from '@coinbase/cds-web/tables';
import { Text } from '@coinbase/cds-web/typography';

import { fmtKrw } from '@/lib/krw';
import { Segmented } from '@/ui/ControlCard';
import { Stat, StatColumn } from '@/ui/Stat';

import {
  MR_RANK_KEYS,
  MR_SPAN_LABEL,
  type MrOptimizeRun,
  type MrOptimizeCell,
  type MrRankKey,
  type MrSpan,
  type MrStrategyParams,
  rankCells,
} from './api';
import { NumCell, Panel, condWord, fmtRatio, headFont, sameCond } from './parts';

/** 표의 열 — 조건 하나 + 지표들. 「채택」은 열 목록 밖이다(버튼이라 정렬도
 *  단위도 없다). */
const OPT_COLS: { k: string; label: string; num?: boolean }[] = [
  { k: 'rank', label: '순위', num: true },
  { k: 'cond', label: '조건' },
  { k: 'calmar', label: 'Calmar', num: true },
  { k: 'sortino', label: 'Sortino', num: true },
  { k: 'martin', label: 'Martin', num: true },
  { k: 'gpr', label: 'GPR', num: true },
  { k: 'omega', label: 'Omega', num: true },
  { k: 'pf', label: 'Profit F.', num: true },
  { k: 'pnl', label: '총손익', num: true },
  { k: 'mdd', label: '최대 낙폭', num: true },
  { k: 'n', label: '거래', num: true },
];

/** 한 칸의 조건을 한 줄로 — 표의 「조건」 칸·1등 카드·**설정 줄의 조건 칸**이
 *  같은 문장을 쓴다. 정의는 `parts.condWord` 한 곳이다(2026-09-09 에 노브 줄의
 *  읽기 칸이 생기면서 세 자리가 됐다 — 셋이 다른 문장이면 화면이 스스로를
 *  반박한다). 순서·표기의 근거는 그 함수 머리에. */
const cellWord = (c: MrOptimizeCell): string => condWord(c);

/** TOP 5 **+ 지금 칸**. 지금 칸이 다섯 안이면 다섯 줄, 밖이면 여섯 줄이다.
 *
 *  다섯만 적으면 「내 칸이 몇 등인가」를 표에서 못 찾는다 — 카드에 등수는
 *  적히지만 그 등수의 수가 안 보이면 «얼마나 뒤인가» 를 말할 수 없다. 붙이는
 *  줄은 자기 실제 등수를 달고 선다(6등이라고 적지 않는다). */
function optRows(
  ranked: MrOptimizeCell[], isNow: (c: MrOptimizeCell) => boolean,
): { c: MrOptimizeCell; n: number }[] {
  const rows = ranked.slice(0, 5).map((c, i) => ({ c, n: i + 1 }));
  const at = ranked.findIndex(isNow);
  if (at >= 5) rows.push({ c: ranked[at]!, n: at + 1 });
  return rows;
}

export type OptimizePaneProps = {
  /** 격자 — 아직 안 돌렸으면 `undefined`(창의 `useState<MrOptimizeRun>()` 그대로). */
  opt: MrOptimizeRun | undefined;
  /** 못 돌린 이유 — 없으면 `undefined`(창의 `useState<string>()` 그대로). */
  error: string | undefined;
  running: boolean;
  rankKey: MrRankKey;
  onRankKey: (k: MrRankKey) => void;
  span: MrSpan;
  /** 머리 카드가 **실가격**인가 — 격자는 늘 엔진 근사라, 참이면 각주가 「같은
   *  조건이라도 수가 달라요」를 더 적는다. */
  headReal: boolean;
  /** 다시 돌리기 — 격자가 실패했을 때의 재시도다. 창을 열면 저절로 도는
   *  흐름이라(2026-09-09) 「처음 실행」 버튼은 없다. */
  onRun: () => void;
  onAdopt: (c: MrOptimizeCell) => void;
  /** **지금 실행된 조건** — 「지금 칸」을 이 위에서 판정한다.
   *
   *  서버의 `cell.current` 는 **질의에 실린 노브** 기준이라, 「격자를 돌린 뒤
   *  1등을 채택해 다시 실행」하는 지금 흐름에서는 «직전 조건» 을 가리킨다
   *  (`parts.sameCond` 머리에 그 사정). 없으면 서버 플래그로 떨어진다 —
   *  구 호출부가 있으면 종전대로 선다. */
  currentParams?: MrStrategyParams;
  /** 안 돌렸을 때의 안내 — 칸 수와 «안 흔드는 것» 을 창이 정한다. */
  intro: string;
  /** 창별 경고 한 문장 — 없으면 공통 각주만 선다. */
  extraNote?: string;
};

/** 표가 실제로 **넘치는가** — 고정 열의 그림자가 그 사실에만 서게 한다.
 *
 *  CSS 는 넘침을 모른다. 그런데 이 표의 넘침은 **데이터에 달렸다**(열 폭이
 *  내용에서 온다 — 실측 BSS-3Y 10px · FSW-3Y 47.7px). 안 넘치는 판에서도
 *  그림자를 그리면 화면이 「여기서부터 덮고 있다」는 **없는 사실**을 말한다 —
 *  `.sr-recon-div-l` 이 2026-09-03 에 같은 이유로 그림자를 버린 그 판단이다.
 *
 *  재는 자리는 CDS 가 표에 두르는 `overflow-x: auto` 상자다(sticky 의 기준
 *  컨테이너와 같은 상자여야 한다). 폭은 창 크기·글꼴·데이터로 바뀌므로
 *  `ResizeObserver` 로 계속 본다.
 *
 *  ⚠ **읽기만 한다.** 여기서 레이아웃을 고치지 않는다 — 관측이 레이아웃을
 *  바꾸면 관측이 자기를 다시 부른다. */
function useCovering(): [React.RefObject<HTMLDivElement | null>, boolean] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [covering, setCovering] = useState(false);
  const measure = useCallback(() => {
    const box = ref.current?.querySelector<HTMLElement>('div[class*="tableContainer"]')
      ?? ref.current;
    if (!box) return;
    setCovering(box.scrollWidth - box.clientWidth > 1);
  }, []);
  /* 의존 배열이 **없다** — 렌더마다 다시 잰다. 이 표의 폭은 데이터에서 오므로
     (칸이 바뀌면 돈 문자열이 바뀐다) 렌더가 곧 「폭이 바뀔 수 있는 순간」이다.

     ⚠ **`ResizeObserver` 하나에 기대지 않는다.** RO 콜백은 렌더 수명주기에
     실려 오므로 탭이 페인트를 안 하면 아예 안 온다(이 리포가 rAF 에서 이미
     겪은 그 인공산물 — 자동화 탭에서 실측 0회). 창 크기만 바뀌고 리렌더가 없는
     경우가 실사용에 있으므로 `resize` 도 같이 듣는다. 둘 다 같은 `measure` 를
     부르고, 그 함수는 읽기만 하므로 두 번 불려도 값이 같다. */
  useEffect(() => {
    const host = ref.current;
    if (!host) return;
    measure();
    window.addEventListener('resize', measure);
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    if (ro) {
      ro.observe(host);
      const inner = host.querySelector('table');
      if (inner) ro.observe(inner);
    }
    return () => {
      window.removeEventListener('resize', measure);
      ro?.disconnect();
    };
  });
  return [ref, covering];
}

export function OptimizePane({
  opt, error, running, rankKey, onRankKey, span, headReal,
  onRun, onAdopt, currentParams, intro, extraNote,
}: OptimizePaneProps) {
  const ranked = useMemo(
    () => (opt ? rankCells(opt.cells, rankKey) : []),
    [opt, rankKey],
  );
  const best = ranked[0];
  /* 「지금 칸」은 **실행된 조건** 위에서 판정한다 — 서버 플래그는 질의 시점의
     노브를 가리킨다(prop 주석의 그 사정). 구 호출부(prop 없음)는 종전대로. */
  const isNow = useCallback(
    (c: MrOptimizeCell) => (currentParams ? sameCond(c, currentParams) : c.current),
    [currentParams],
  );
  const curRank = ranked.findIndex(isNow);
  const [gridRef, covering] = useCovering();
  const rank = MR_RANK_KEYS.find((k) => k.v === rankKey)!;

  return (
    <Panel
      title="근사 최적화"
      sub={opt
        ? `${opt.cells.length}칸 · ${MR_SPAN_LABEL[span]} 채점 · 엔진 근사`
        : '룩백·진입·청산·손절·진입 규칙의 프리셋을 전부 돌려요'}
      aside={
        <HStack gap={1} alignItems="center">
          {opt ? (
            <Box className="sr-tabs-neutral">
              <Segmented
                label="순위 기준"
                value={rankKey}
                options={MR_RANK_KEYS.map((k) => ({
                  value: k.v, label: k.label, title: k.help,
                }))}
                onChange={(v: MrRankKey) => onRankKey(v)}
              />
            </Box>
          ) : null}
          {/* 버튼은 **재시도**뿐이다 [OWNER 2026-09-09] — 창을 열면 격자가 저절로
              돌고(그 흐름은 창이 진다) 비용·Delta 를 바꾸면 다시 돈다. 「최적화
              실행」을 남겨 두면 이미 돌아 있는 것을 또 누르라고 권하는 셈이다.
              실패했을 때만 서는 이유: 성공한 판에서 이 자리는 노브 줄의 「다시
              돌리기」와 같은 일을 하는 둘째 버튼이 된다. */}
          {error ? (
            <button
              type="button"
              className="sr-pillbtn"
              data-fill
              disabled={running}
              onClick={onRun}
            >
              {running ? '격자 도는 중…' : '다시 시도'}
            </button>
          ) : running ? (
            <Text font="legal" as="span" color="fgMuted" noWrap>
              격자 도는 중…
            </Text>
          ) : null}
        </HStack>
      }
    >
      {error ? (
        <Text font="body" as="p" className="sr-up">
          격자를 못 돌렸어요 — {error}
        </Text>
      ) : !opt ? (
        <Text font="body" as="p" color="fgMuted">{intro}</Text>
      ) : !best ? (
        <Text font="body" as="p" color="fgMuted">
          이 구간에서 설 수 있는 칸이 없어요 — 이력이 룩백보다 짧아요.
        </Text>
      ) : (
        <VStack gap={1} width="100%">
          {/* 1등 한 벌 — 「근사 최적화 세트의 결과」. 지금 칸과 나란히 적어야
              «바꿀 값이 있나» 가 한 줄로 읽힌다. */}
          <HStack className="sr-stats" width="100%" flexWrap="wrap">
            <StatColumn title={`최적 세트 · ${rank.label} 1등`}>
              <Stat label="조건" value={cellWord(best)}
                note={isNow(best) ? '지금 이 조건으로 돌고 있어요' : '아직 안 돌린 조건이에요'} />
              <Stat
                label={rank.label}
                value={rankKey === 'totalPnl' ? fmtKrw(best.totalPnl) : fmtRatio(best[rankKey])}
              />
              <Stat
                label="총손익"
                value={fmtKrw(best.totalPnl)}
                tone={best.totalPnl > 0 ? 'up' : best.totalPnl < 0 ? 'down' : undefined}
              />
              <Stat label="최대 낙폭" value={fmtKrw(-best.maxDrawdown)} />
              <Stat label="거래" value={String(best.numTrades)} />
              {/* 지금 칸이 몇 등인가 — 이 표의 존재 이유다. 1등이면 그 사실이
                  「바꿀 것이 없다」는 답이고, 뒤쪽이면 얼마나 뒤인지가 답이다. */}
              <Stat
                label="지금 칸"
                value={curRank < 0 ? '—' : `${curRank + 1}등`}
                note={curRank < 0 ? '격자 밖이에요' : `${ranked.length}칸 중`}
              />
            </StatColumn>
          </HStack>

          {/* TOP 5 매트릭스 — 조건 다섯 열 + 지표 열. 표는 캐논(CDS Table),
              머리 활자는 `headFont`(소문자가 있으면 legal — CDS caption 이
              대문자화를 걸어 「bp」가 「BP」가 된다). */}
          {/* 「채택」 열을 오른쪽에 **고정**한다 [OWNER 2026-09-07 — "고정 열로"].
              표가 상자를 넘고 넘친 쪽이 하필 누르는 칸이라, 안 붙이면 이 표의
              유일한 액션이 기본 화면에 없다. 문법과 근거는 `theme/type.css` 의
              `.sr-mr-optgrid` — 대사표 고정 열과 같은 규율이다.
              `data-covering` 은 **실제로 넘칠 때만** 그림자를 켠다. */}
          <Box
            ref={gridRef}
            className="sr-mr-drawertable sr-mr-optgrid"
            width="100%"
            data-covering={covering ? '1' : '0'}
          >
            <Table bordered={false}>
              <TableHeader sticky>
                <TableRow>
                  {OPT_COLS.map((c) => (
                    <TableCell
                      key={c.k}
                      as="th"
                      scope="col"
                      className={c.num ? 'sr-num' : undefined}
                      justifyContent={c.num ? 'flex-end' : undefined}
                    >
                      <Text font={headFont(c.label)} as="span" color="fgMuted" noWrap>
                        {c.label}
                      </Text>
                    </TableCell>
                  ))}
                  <TableCell as="th" scope="col">
                    <Text font="caption" as="span" color="fgMuted" noWrap>
                      채택
                    </Text>
                  </TableCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {optRows(ranked, isNow).map(({ c, n }) => (
                  <TableRow key={`${c.lookback}-${c.entryZ}-${c.exitZ}-${c.stopZ}-${c.entryMode}`}>
                    <TableCell className="sr-num" justifyContent="flex-end">
                      <Text font="label1" as="span" tabularNumbers noWrap>{n}</Text>
                    </TableCell>
                    <TableCell>
                      <Text font="label1" as="span" noWrap>
                        {isNow(c) ? `${cellWord(c)} · 지금` : cellWord(c)}
                      </Text>
                    </TableCell>
                    <NumCell v={c.calmar} />
                    <NumCell v={c.sortino} />
                    <NumCell v={c.martin} />
                    <NumCell v={c.gpr} />
                    <NumCell v={c.omega} />
                    <NumCell v={c.profitFactor} />
                    <TableCell className="sr-num" justifyContent="flex-end">
                      <Text
                        font="label1"
                        as="span"
                        tabularNumbers
                        noWrap
                        className={c.totalPnl > 0 ? 'sr-up' : c.totalPnl < 0 ? 'sr-down' : undefined}
                      >
                        {fmtKrw(c.totalPnl)}
                      </Text>
                    </TableCell>
                    <TableCell className="sr-num" justifyContent="flex-end">
                      <Text font="label1" as="span" tabularNumbers noWrap>
                        {fmtKrw(-c.maxDrawdown)}
                      </Text>
                    </TableCell>
                    <TableCell className="sr-num" justifyContent="flex-end">
                      <Text font="label1" as="span" tabularNumbers noWrap>
                        {c.numTrades}
                      </Text>
                    </TableCell>
                    <TableCell>
                      <button
                        type="button"
                        className="sr-pillbtn"
                        disabled={isNow(c)}
                        onClick={() => onAdopt(c)}
                      >
                        {/* 「채택」 두 글자다 [실측 2026-09-04]. 「노브에 넣기」로
                            두면 이 열이 열 중 가장 넓어져 표가 상자를 넘고, 넘친
                            쪽이 하필 **누르는 칸**이라 가로로 밀어야 눌린다.
                            열 머리가 이미 「채택」이라 동사는 중복이기도 하다.
                            ⚠ 그래도 넘친다 — 열 폭이 내용에서 오므로(돈 문자열이
                            넓어지면 표도 넓어진다) 데이터에 달렸고, 실측 47.7px
                            (FSW-3Y). 여는 결정은 오너 몫으로 남아 있다. */}
                        {isNow(c) ? '적용됨' : '채택'}
                      </button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>

          {/* 이 표가 무엇이 아닌지 — 각주가 진다. 안 적으면 화면이 「이 칸이
              최적이다」라고만 말하게 된다. */}
          <Text font="legal" as="p" color="fgMuted">
            {`격자는 엔진 근사예요${headReal ? ' — 머리 카드는 실가격이라 같은 조건이라도 수가 달라요' : ''}.`}
            {' '}비율은 원/원이라 수익률 기반 문헌값과 크기를 직접 비교하면 안 돼요.
            {' '}같은 구간·같은 표본을 {opt.cells.length}번 잰 값이라 1등은 뽑기의
            결과이기도 해요 — 2등과의 거리가 그 칸의 신뢰도예요.
            {/* 「얼마나 뽑기인가」를 실제로 쟀다 [2026-09-07 · 표본 반 가르기].
                안 재고 「뽑기이기도 해요」만 적으면 그건 예의 표시일 뿐이고,
                읽는 사람은 결국 1등을 채택한다. */}
            {' '}표본을 반으로 갈라 재 보면 앞절반 순위가 뒤절반과 얼마나 맞는지가
            기준마다 달라요 — Calmar·Sortino·Martin 은 앞절반 1등~5등이 뒤절반
            상위권에 남지만, 「총손익」은 무작위보다 나빠요.
            {extraNote ? ` ${extraNote}` : ''}
          </Text>
        </VStack>
      )}
    </Panel>
  );
}
