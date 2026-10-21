'use client';

/* Lab 「모형」 의 셋째 면 — «믿어도 돼» 에 답한다.
 *
 * ## 이 면의 원칙 하나
 *
 * **자기 실패 방식을 스스로 부르는 도구가, 흠 없어 보이는 도구보다 믿을 만하다.**
 * 그래서 올림하지 않는다. 스코어카드는 9/13 이고, 그 9 조차 독립적인 시험이
 * 아니라는 것을 바로 옆에서 말한다. 백테스트는 아직 못 하고, 못 하는 이유를
 * 내용으로 세운다.
 *
 * ## 순서
 *
 *   1. 무엇을 출하하나   — 한 문장. 이 화면이 파는 것이 무엇인지
 *   2. 해석 원장         — 논문이 말한 것 · 우리가 한 것 · 왜 · 어떻게 틀릴 수 있나
 *   3. 한계              — 외생 대체분
 *   4. 스코어카드 + 자유모수 — **같은 화면에서.** 떨어뜨리면 핀이 시험으로 읽힌다
 *   5. 백테스트          — 막는 것 목록
 *
 * 읽기 전용이다.
 */

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import {
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from '@coinbase/cds-web/tables';
import { Text } from '@coinbase/cds-web/typography';

import { anchorProps, ANCHORS, eq as eqAnchor, hrefFor, ledgerRow } from '../anchors';
import { SurfaceShell, type TocItem } from '../SurfaceShell';
import { Stat, StatColumn } from '@/ui/Stat';

import { Emph } from '../model/emph';

import anchorsJson from '../artifacts/paper_anchors.json';
import statusJson from '../artifacts/engine_status.json';
import type { EngineStatus } from '../contracts';
import backtestJson from './backtest_2021_cycle.json';
import methodJson from './method_surface.json';

type LedgerEntry = {
  key: string;
  title: string;
  paper_says: string;
  we_do: string;
  why: string;
  could_be_wrong: string;
  paper: string;
  code: string;
  node: string | null;
  equation: string | null;
};

type AnchorRow = {
  anchor_id: string;
  shock: string;
  panel: string;
  page: string;
  paper: number | null;
  unit: string;
  kind: string;
  measured: number | null;
  measured_q: number | null;
  measured_12q: number | null;
  tail: boolean;
  band: [number, number] | null;
  verdict: string;
  note: string | null;
};

type Method = {
  ledger: LedgerEntry[];
  limitations: {
    ships: string;
    ships_why: string;
    ledger_row: string;
    no_effect: { equation: string; what: string; why: string }[];
    level_only: { equation: string; what: string; why: string }[];
    note: string;
  };
  scorecard: {
    engine_total: number;
    engine_passed: number;
    /** 9/13 을 **만드는** 열세 칸. 수치 여덟 + 모양 다섯이다.
     *  모양 칸은 값도 밴드도 `null` 이다 — 부호·꼴만 보는 자리라 그게 정상이고,
     *  0 으로 채우면 «밴드 정중앙» 처럼 보인다. */
    engine_rows: {
      irf: string;
      metric: string;
      value: number | null;
      band: [number, number] | null;
      pass: boolean;
    }[];
    anchor_rows: AnchorRow[];
    chain: string;
    root: string;
    not_a_baseline: string;
    two_thirteens: string;
    horizon_rule: string;
  };
  free_params: {
    name: string;
    value: string;
    chosen_by: string;
    kind: string;
    contaminates: string;
    code: string;
  }[];
  free_params_headline: string;
};

type Backtest = {
  verdict: string;
  headline: string;
  window: string[];
  blockers: {
    id: string;
    what: string;
    detail: string;
    measured?: Record<string, number>;
    measured_note?: string;
    needs: string;
  }[];
  coherence_check: {
    what: string;
    how: string;
    realised_i_kr: number[];
    realised_kr10y: number[];
    model_kr10y: number[];
    rmse_bp: number;
    benchmark: string;
    benchmark_rmse_bp: number;
    ratio: number;
    reads_as: string;
  };
  error_shares: [string, string, string][];
  benchmark_options: [string, boolean, string][];
};

const M = methodJson as unknown as Method;
const B = backtestJson as unknown as Backtest;

const VERDICT_LABEL: Record<string, string> = {
  pass: '통과',
  miss: '벗어남',
  shape_pass: '모양 통과',
  shape_miss: '모양 벗어남',
  pinned: '핀 — 시험 아님',
  no_band: '밴드 없음',
  not_comparable: '대조 불가',
};

const KIND_LABEL: Record<string, string> = {
  fit: '맞춘 값',
  mixed: '판정 + 앵커 근거',
  unpublished: '논문 미공표',
  external: '외부 자료에 적합',
};

/* ── 1. 무엇을 출하하나 ─────────────────────────────────────────────────────── */

function Ships() {
  const l = M.limitations;
  return (
    <VStack gap={1} maxWidth={760} {...anchorProps(ANCHORS.method.ships)}>
      {/* 소제목을 안 단다 — 바로 아래 큰 문장이 「이 화면이 파는 것은 …」 으로
          시작해서 같은 말이 두 번 섰다. 이 블록은 차례가 이름을 준다. */}
      {/* **한 문장이다.** 「델타도 되고 레벨도 됩니다」 로 흐리면 트레이더가 레벨을
          읽고, 그러면 위의 외생 대체분이 조용히 청구된다. */}
      <Text as="p" font="title4">
        <Emph t={l.ships} />
      </Text>
      <Text as="p" font="legal" color="fgMuted">
        <Emph t={l.ships_why} />{' '}
        <a href={`#${ledgerRow(l.ledger_row)}`}>원장의 같은 행</a>에 같은 말이 적혀
        있어요.
      </Text>
    </VStack>
  );
}

/* ── 1b. 알려진 이음매 · 엔진의 출처 ────────────────────────────────────────── */

/* 엔진이 **자기 입으로** 아는 이음매 셋이 `engine_status.json::known_seams` 로
 * 실려 오는데, 2026-08-24 까지 어느 면도 그걸 렌더하지 않았다. 계약에 타입까지
 * 있고(`contracts.ts::EngineStatus.known_seams`) 리베이크가 매번 옮기는데
 * 화면에는 없었다 — 「믿어도 돼」 에 답하는 면에서 빠질 수 있는 것이 아니다.
 *
 * 셋 중 둘은 트레이더가 **당장** 알아야 하는 것이다. IRS 다리에 기간프리미엄이
 * 안 오고, 국고 3년은 기대가설 평균만이다. 그걸 모르고 화면의 bp 를 읽으면
 * «커브가 이만큼 움직인다» 를 «가격이 이만큼 움직인다» 로 읽는다.
 *
 * 같은 이유로 `tests` 와 `engine` 도 여기서 선다. 엔진이 어디서 왔고 몇 개의
 * 시험을 지고 있는지는 이 면의 질문 그 자체다. */

function Seams() {
  const st = statusJson as unknown as EngineStatus;
  const paper = (anchorsJson as unknown as {
    paper: { id: string; title: string; authors: string; published: string; pdf: string };
  }).paper;
  const t = st.tests;
  return (
    <VStack gap={1.5} width="100%" {...anchorProps(ANCHORS.method.seams)}>
      <VStack gap={0.25} maxWidth={760}>
        <Text as="h3" font="label1">
          알려진 이음매
        </Text>
        <Text as="p" font="legal" color="fgMuted">
          엔진이 자기 입으로 아는 자리예요. 고쳐야 할 것으로 적어 둔 게 아니라,
          지금 이렇게 돌고 있다는 사실이에요.
        </Text>
      </VStack>

      {/* 라벨과 문장을 **한 줄에 안 둔다** [실측 2026-08-24]. `flexBasis` 280 이
          문장을 좁게 잡아서 끝의 「요.」 가 홀로 다음 줄로 떨어졌다. 코드
          플래그는 라벨이지 문장의 일부가 아니라, 위에 눕힌다. */}
      <VStack gap={0.75} width="100%" maxWidth={760}>
        {st.known_seams.map((sm) => (
          <VStack key={sm.flag} gap={0.25} className="sr-readrow">
            <Text as="span" font="legal" color="fgMuted">
              <code>{sm.flag}</code>
            </Text>
            <Text as="p" font="legal">
              <Emph t={sm.what} />
            </Text>
          </VStack>
        ))}
      </VStack>

      {/* 빈티지와 출처를 **문장이 아니라 칸으로** 낸다 [2026-08-24].
          예전에는 「국민계정 실질 2026Q2 근원 CPI 2026Q2 …」 가 한 줄로 이어지고
          그 아래 논문·엔진·시험이 회색 문단 셋이었다. 13px 회색이 화면의
          대부분이라 무엇이 키고 무엇이 값인지가 안 보였다.

          이 앱이 여러 사실을 눕히는 문법은 통계 스트립이다 — 백테스트 카드 아래
          「이 구간·변화·52주」가 그것이고, 코인베이스 가격 페이지와 토스증권
          종목 머리가 같은 것을 한다(실측). 산문을 안 쓰고, 작은 회색 키 위에
          굵은 잉크 값을 올리고, 칸 사이는 헤어라인이다. */}
      <HStack className="sr-stats" width="100%" flexWrap="wrap">
        <StatColumn title="모형이 마지막으로 본 분기">
          {Object.entries(st.data_edge.per_series).map(([name, q]) => (
            <Stat key={name} label={name} value={q ?? '몰라요'} />
          ))}
        </StatColumn>
      </HStack>
      <Text as="p" font="legal" color="fgMuted">
        제일 새 분기는 {st.data_edge.newest_quarter ?? '몰라요'} 인데 구속하는 것은{' '}
        <b>{st.data_edge.binding_quarter ?? '몰라요'}</b> 예요 — 모형은 제일 이른 쪽에
        맞춰 서요.
      </Text>

      {/* 논문의 신원. 이 면은 「논문은 …」 을 수십 번 말하는데 **어느 논문인지**
          한 번도 통째로 대지 않았다. */}
      <HStack className="sr-stats" width="100%" flexWrap="wrap">
        <StatColumn title="논문">
          <Stat label="번호" value={paper.id} />
          <Stat label="발표" value={paper.published} />
        </StatColumn>
        <StatColumn title="엔진">
          <Stat label="사는 곳" value={st.engine.home} />
          <Stat label="옮긴 날" value={st.engine.moved_on} />
          <Stat
            label="지고 있는 시험"
            value={t.collected === null ? '못 셌어요' : `${t.collected}개`}
          />
        </StatColumn>
      </HStack>
      <Text as="p" font="legal" color="fgMuted">
        {paper.title} — {paper.authors}. PDF 는 <code>{paper.pdf}</code> 예요.{' '}
        <Emph t={st.engine.note} /> 출처 커밋은 {st.engine.source_commits.join(' · ')} 예요.
      </Text>
    </VStack>
  );
}

/* ── 2. 해석 원장 ───────────────────────────────────────────────────────────── */

function Ledger() {
  return (
    <VStack gap={1.5} width="100%" {...anchorProps(ANCHORS.method.ledger)}>
      <VStack gap={0.5}>
        <Text as="h3" font="label1">
          해석 원장 — 논문이 말한 것과 우리가 한 것
        </Text>
        <Text as="p" font="legal" color="fgMuted">
          행 {M.ledger.length}개예요. 행마다 <b>논문 인용과 코드 자리를 둘 다</b>{' '}
          들어요 — 하나라도 빠지면 빌드가 서요.
        </Text>
      </VStack>

      <VStack gap={0} width="100%" className="sr-ledger">
        {M.ledger.map((r) => (
          <VStack
            key={r.key}
            gap={0.75}
            width="100%"
            paddingY={1.5}
            {...anchorProps(ledgerRow(r.key))}
          >
            <Text as="h4" font="label1">
              <Emph t={r.title} />
            </Text>
            <VStack gap={0.5} width="100%">
              <Text as="p" font="legal" color="fgMuted">
                <b className="sr-ledger-tag">논문</b> <Emph t={r.paper_says} />
              </Text>
              <Text as="p" font="legal" color="fgMuted">
                <b className="sr-ledger-tag">우리</b> <Emph t={r.we_do} />
              </Text>
              <Text as="p" font="legal" color="fgMuted">
                <b className="sr-ledger-tag">왜</b> <Emph t={r.why} />
              </Text>
              <Text as="p" font="legal" className="sr-ledger-risk">
                <b className="sr-ledger-tag">틀릴 수 있는 자리</b> <Emph t={r.could_be_wrong} />
              </Text>
            </VStack>
            <HStack gap={1.5} flexWrap="wrap" alignItems="baseline">
              <Text as="span" font="legal" color="fgMuted" noWrap>
                {r.paper}
              </Text>
              <Text as="span" font="legal" color="fgMuted">
                <code>{r.code}</code>
              </Text>
              {r.equation && r.equation !== '항등식' ? (
                <Text as="span" font="legal" color="fgMuted" noWrap>
                  <a href={`${hrefFor(ANCHORS.model.wiring)}`.replace(
                    `#${ANCHORS.model.wiring}`,
                    `#${eqAnchor(r.equation)}`,
                  )}>
                    모형 면의 식 ({r.equation})
                  </a>
                </Text>
              ) : null}
            </HStack>
          </VStack>
        ))}
      </VStack>
    </VStack>
  );
}

/* ── 3. 한계 ────────────────────────────────────────────────────────────────── */

function Limitations() {
  const l = M.limitations;
  return (
    <VStack gap={1.5} width="100%" {...anchorProps(ANCHORS.method.limitations)}>
      <VStack gap={0.5}>
        <Text as="h3" font="label1">
          «자동» 이 아닌 자리
        </Text>
        <Text as="p" font="legal" color="fgMuted">
          엔진이 외생으로 두는데 실데이터가 없어 고정값이 들어간 자리예요. <Emph t={l.note} />
        </Text>
      </VStack>

      <VStack gap={0.5} width="100%">
        <Text as="h4" font="label2">
          오너의 답에 영향 없음 (편차 공간의 0)
        </Text>
        {l.no_effect.length === 0 ? (
          <Text as="p" font="legal" color="fgMuted">
            지금은 없어요 — 아래 것들이 전부 레벨 쪽이에요.
          </Text>
        ) : (
          l.no_effect.map((x) => (
            <Text key={`${x.equation}-${x.what}`} as="p" font="legal" color="fgMuted">
              <b>식 ({x.equation})</b> <Emph t={x.what} /> — <Emph t={x.why} />
            </Text>
          ))
        )}
      </VStack>

      <VStack gap={0.5} width="100%">
        <Text as="h4" font="label2">
          레벨 전망에 영향 있음
        </Text>
        {l.level_only.map((x, i) => (
          <Text key={`${x.equation}-${i}`} as="p" font="legal" color="fgMuted">
            <b>식 ({x.equation})</b> <Emph t={x.what} /> — <Emph t={x.why} />
          </Text>
        ))}
      </VStack>
    </VStack>
  );
}

/* ── 4. 스코어카드 + 자유모수 — 같은 화면에서 ───────────────────────────────── */

function Scorecard() {
  const s = M.scorecard;
  return (
    <VStack gap={1.5} width="100%" {...anchorProps(ANCHORS.method.scorecard)}>
      <VStack gap={0.5}>
        <HStack gap={1.5} alignItems="baseline" flexWrap="wrap">
          <Text as="h3" font="label1">
            스코어카드
          </Text>
          <Text as="span" font="title1" tabularNumbers noWrap>
            {s.engine_passed}/{s.engine_total}
          </Text>
        </HStack>
        <Text as="p" font="legal" color="fgMuted">
          <Emph t={s.not_a_baseline} />
        </Text>
        <Text as="p" font="legal" color="fgMuted">
          <Emph t={s.two_thirteens} /> <Emph t={s.horizon_rule} />
        </Text>
      </VStack>

      {/* **9/13 을 만드는 열세 칸 자체.**
       *
       * 2026-08-24 까지 이 면은 큰 숫자로 「9/13」 을 찍고 그 아래에 **다른**
       * 열셋(논문 앵커)의 표를 놨다. 두 13 이 다른 것이라고 바로 위 문장이
       * 말하기는 하는데, 그러면 화면에 실린 표 어디에서도 9/13 을 셀 수 없다.
       * 헤드라인 숫자의 근거가 화면에 없는 것이라 채운다.
       *
       * 모양 다섯은 밴드가 없다 — 값이 아니라 부호·꼴을 보는 칸이라 `null` 이
       * 정상이고, 0 으로 채우면 «밴드 정중앙» 처럼 보인다. */}
      {/* **표로 세운다** [2026-08-24]. flex 줄로 눕혔더니 값이 `flexGrow` 를
          먹어 판정이 화면 한가운데에 떠 있었고, 열세 줄의 실측값이 서로 칼럼을
          안 이뤄 위아래로 못 비교했다. 숫자를 비교하라고 내놓은 표에서 그건
          표가 아니다 — 이 앱의 다른 표들이 하는 대로 `tabular` + 우측정렬이다. */}
      <Box className="sr-strat-table" width="100%" maxWidth={760}>
        <Table>
          <TableHeader>
            <TableRow>
              {['충격', '칸', '실측', '밴드', '판정'].map((h, i) => (
                <TableCell
                  as="th"
                  scope="col"
                  key={h}
                  className={i === 2 ? 'sr-num' : 'sr-label'}
                  justifyContent={i === 2 ? 'flex-end' : undefined}
                >
                  <Text as="span" font="legal" color="fgMuted" noWrap>
                    {h}
                  </Text>
                </TableCell>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {s.engine_rows.map((r) => (
              <TableRow key={`${r.irf}-${r.metric}`}>
                <TableCell className="sr-label">
                  <Text as="span" font="legal" color="fgMuted" noWrap>
                    {r.irf}
                  </Text>
                </TableCell>
                <TableCell className="sr-label">
                  <Text as="span" font="legal" noWrap>
                    <code>{r.metric.replace('shape:', '')}</code>
                  </Text>
                </TableCell>
                <TableCell className="sr-num" justifyContent="flex-end">
                  <Text as="span" font="legal" tabularNumbers noWrap>
                    {r.value === null ? '—' : r.value.toFixed(4)}
                  </Text>
                </TableCell>
                <TableCell className="sr-label">
                  <Text as="span" font="legal" color="fgMuted" noWrap>
                    {r.band ? `[${r.band[0]}, ${r.band[1]}]` : '모양만 봐요'}
                  </Text>
                </TableCell>
                <TableCell className="sr-label">
                  {/* 판정에 **방향색을 안 쓴다** — 파랑은 이 앱에서 「금리가
                      내렸다」 하나만 뜻하고, 미달은 방향이 아니다. */}
                  <Text as="span" font="legal" noWrap>
                    {r.pass ? '통과' : <b>미달</b>}
                  </Text>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>

      <Box overflow="auto" width="100%">
        <Table tableLayout="auto">
          <TableHeader>
            <TableRow>
              {['충격', '칸', '논문', '실측', '분기', '밴드', '판정'].map((h, i) => (
                <TableCell
                  as="th"
                  scope="col"
                  key={h}
                  className={i >= 2 && i <= 4 ? 'sr-num' : 'sr-label'}
                  justifyContent={i >= 2 && i <= 4 ? 'flex-end' : undefined}
                >
                  <Text as="span" font="legal" color="fgMuted" noWrap>
                    {h}
                  </Text>
                </TableCell>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {s.anchor_rows.map((r) => (
              <TableRow key={r.anchor_id}>
                <TableCell className="sr-label">
                  <Text as="span" font="legal" color="fgMuted" noWrap>
                    <Emph t={r.shock} />
                  </Text>
                </TableCell>
                <TableCell className="sr-label">
                  <Text as="span" font="label2" noWrap>
                    <Emph t={r.panel} />
                  </Text>
                </TableCell>
                <TableCell className="sr-num" justifyContent="flex-end">
                  <Text as="span" font="legal" color="fgMuted" tabularNumbers noWrap>
                    {r.paper == null ? '모양' : `${r.paper}${r.unit}`}
                  </Text>
                </TableCell>
                <TableCell className="sr-num" justifyContent="flex-end">
                  <Text as="span" font="label2" tabularNumbers noWrap>
                    {r.measured == null ? '—' : r.measured}
                  </Text>
                </TableCell>
                <TableCell className="sr-num" justifyContent="flex-end">
                  <Text as="span" font="legal" color="fgMuted" tabularNumbers noWrap>
                    {r.measured_q == null ? '—' : `q${r.measured_q}`}
                  </Text>
                </TableCell>
                <TableCell className="sr-label">
                  <Text as="span" font="legal" color="fgMuted" tabularNumbers noWrap>
                    {r.band ? `${r.band[0]} ~ ${r.band[1]}` : '—'}
                  </Text>
                </TableCell>
                <TableCell className="sr-label">
                  <span className="sr-verdict" data-v={r.verdict}>
                    <Text as="span" font="legal" noWrap>
                      {VERDICT_LABEL[r.verdict] ?? r.verdict}
                    </Text>
                  </span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>

      <VStack gap={0.5} width="100%">
        {s.anchor_rows
          .filter((r) => r.tail || r.note || r.verdict === 'pinned')
          .map((r) => (
            <Text key={`n-${r.anchor_id}`} as="p" font="legal" color="fgMuted">
              <b><Emph t={r.panel} /></b>
              {r.verdict === 'pinned'
                ? ' — 이 칸은 자유모수를 맞춘 표적이에요. 「맞았다」로 읽으면 안 돼요.'
                : ''}
              {r.tail
                ? ` — 극값이 q${r.measured_q} 에서 나왔어요. 논문 그림은 12분기 근처까지라 12분기 안의 값(${r.measured_12q})을 같이 봐 주세요.`
                : ''}
              {r.note ? <> <Emph t={r.note} /></> : null}
            </Text>
          ))}
      </VStack>

      <VStack gap={0.5} maxWidth={760}>
        <Text as="h4" font="label2">
          벗어난 넷은 한 사슬이에요
        </Text>
        <Text as="p" font="legal" color="fgMuted">
          <Emph t={s.chain} />. <Emph t={s.root} />
        </Text>
      </VStack>
    </VStack>
  );
}

function FreeParams() {
  return (
    <VStack
      gap={1.5}
      width="100%"
      className="sr-freeparams"
      padding={1.5}
      {...anchorProps(ANCHORS.method.freeParams)}
    >
      <VStack gap={0.5}>
        <Text as="h3" font="label1">
          맞춘 값과 시험한 값
        </Text>
        <Text as="p" font="legal">
          <Emph t={M.free_params_headline} />
        </Text>
      </VStack>

      <Box overflow="auto" width="100%">
        <Table tableLayout="auto">
          <TableHeader>
            <TableRow>
              {['모수', '값', '종류', '무엇에 맞췄나', '오염되는 앵커'].map((h) => (
                <TableCell as="th" scope="col" key={h} className="sr-label">
                  <Text as="span" font="legal" color="fgMuted" noWrap>
                    {h}
                  </Text>
                </TableCell>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {M.free_params.map((p) => (
              <TableRow key={p.name}>
                <TableCell className="sr-label">
                  <Text as="span" font="label2" noWrap>
                    <Emph t={p.name} />
                  </Text>
                </TableCell>
                <TableCell className="sr-label">
                  <Text as="span" font="legal" tabularNumbers noWrap>
                    {p.value}
                  </Text>
                </TableCell>
                <TableCell className="sr-label">
                  <Text as="span" font="legal" color="fgMuted" noWrap>
                    {KIND_LABEL[p.kind] ?? p.kind}
                  </Text>
                </TableCell>
                <TableCell className="sr-label">
                  <Text as="span" font="legal" color="fgMuted">
                    <Emph t={p.chosen_by} />
                  </Text>
                </TableCell>
                <TableCell className="sr-label">
                  <Text as="span" font="legal" color="fgMuted">
                    <Emph t={p.contaminates} />
                  </Text>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>
    </VStack>
  );
}

/* ── 5. 백테스트 ────────────────────────────────────────────────────────────── */

function Backtest() {
  const c = B.coherence_check;
  return (
    <VStack gap={1.5} width="100%" {...anchorProps(ANCHORS.method.backtest)}>
      <VStack gap={0.5} maxWidth={760}>
        <Text as="h3" font="label1">
          백테스트 — {B.window[0]} ~ {B.window[B.window.length - 1]}
        </Text>
        <Text as="p" font="body">
          <Emph t={B.headline} />
        </Text>
      </VStack>

      <VStack gap={0} width="100%" className="sr-ledger">
        {B.blockers.map((b) => (
          <VStack key={b.id} gap={0.5} width="100%" paddingY={1.5}>
            <Text as="h4" font="label2">
              <Emph t={b.what} />
            </Text>
            <Text as="p" font="legal" color="fgMuted">
              <Emph t={b.detail} />
            </Text>
            {b.measured ? (
              <>
                <HStack gap={1.5} flexWrap="wrap">
                  {Object.entries(b.measured).map(([k, v]) => (
                    <Text key={k} as="span" font="legal" tabularNumbers noWrap>
                      {k} <b>{v > 0 ? '+' : ''}{v}</b>
                    </Text>
                  ))}
                </HStack>
                <Text as="p" font="legal" color="fgMuted">
                  <Emph t={b.measured_note} />
                </Text>
              </>
            ) : null}
            <Text as="p" font="legal" color="fgMuted">
              필요한 것 — <Emph t={b.needs} />
            </Text>
          </VStack>
        ))}
      </VStack>

      <VStack gap={1} width="100%" className="sr-freeparams" padding={1.5}>
        <Text as="h4" font="label2">
          <Emph t={c.what} />
        </Text>
        <Text as="p" font="legal" color="fgMuted">
          <Emph t={c.how} />
        </Text>
        <Box overflow="auto" width="100%">
          <Table tableLayout="auto">
            <TableHeader>
              <TableRow>
                <TableCell as="th" scope="col" className="sr-label">
                  <Text as="span" font="legal" color="fgMuted" noWrap>
                    분기
                  </Text>
                </TableCell>
                {B.window.map((q) => (
                  <TableCell
                    as="th"
                    scope="col"
                    key={q}
                    className="sr-num"
                    justifyContent="flex-end"
                  >
                    <Text as="span" font="legal" color="fgMuted" noWrap>
                      {q}
                    </Text>
                  </TableCell>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {(
                [
                  ['실현 기준금리 편차', c.realised_i_kr],
                  ['실현 국고 10년 편차', c.realised_kr10y],
                  ['모형 국고 10년 편차', c.model_kr10y],
                ] as [string, number[]][]
              ).map(([name, path]) => (
                <TableRow key={name}>
                  <TableCell className="sr-label">
                    <Text as="span" font="label2" noWrap>
                      <Emph t={name} />
                    </Text>
                  </TableCell>
                  {path.map((v, i) => (
                    <TableCell
                      key={`${name}-${i}`}
                      className="sr-num"
                      justifyContent="flex-end"
                    >
                      <Text as="span" font="legal" tabularNumbers noWrap>
                        {v > 0 ? '+' : ''}
                        {v.toFixed(3)}
                      </Text>
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
        <HStack gap={2} flexWrap="wrap" alignItems="baseline">
          <Text as="span" font="legal" tabularNumbers noWrap>
            RMSE <b>{c.rmse_bp}bp</b>
          </Text>
          <Text as="span" font="legal" color="fgMuted" tabularNumbers noWrap>
            <Emph t={c.benchmark} /> {c.benchmark_rmse_bp}bp
          </Text>
          <Text as="span" font="legal" tabularNumbers noWrap>
            비율 <b>{c.ratio}</b>
          </Text>
        </HStack>
        <Text as="p" font="legal" color="fgMuted">
          <Emph t={c.reads_as} />
        </Text>
      </VStack>

      <VStack gap={0.5} width="100%">
        <Text as="h4" font="label2">
          오차는 다섯 몫의 합이에요
        </Text>
        {B.error_shares.map(([what, whose, why]) => (
          <Text key={what} as="p" font="legal" color="fgMuted">
            <b><Emph t={what} /></b> — {whose}. <Emph t={why} />
          </Text>
        ))}
      </VStack>

      <VStack gap={0.5} width="100%">
        <Text as="h4" font="label2">
          벤치마크
        </Text>
        {B.benchmark_options.map(([name, ok, why]) => (
          <Text key={name} as="p" font="legal" color="fgMuted">
            <b><Emph t={name} /></b> — {ok ? '돼요' : '안 돼요'}. <Emph t={why} />
          </Text>
        ))}
      </VStack>
    </VStack>
  );
}

/* 차례. 순서는 읽는 순서다 — 무엇을 파는지 → 어디가 이음매인지 → 무엇을
   해석했는지 → 무엇을 못 하는지 → 얼마나 맞는지 → 무엇을 맞췄는지 → 왜
   백테스트가 아닌지. */
const TOC: TocItem[] = [
  { id: ANCHORS.method.ships, label: '이 화면이 파는 것' },
  { id: ANCHORS.method.seams, label: '알려진 이음매' },
  { id: ANCHORS.method.ledger, label: '해석 원장' },
  { id: ANCHORS.method.limitations, label: '«자동» 이 아닌 자리' },
  { id: ANCHORS.method.scorecard, label: '스코어카드' },
  { id: ANCHORS.method.freeParams, label: '맞춘 값과 시험한 값' },
  { id: ANCHORS.method.backtest, label: '백테스트' },
];

export function MethodSurface() {
  return (
    <SurfaceShell
      items={TOC}
      className="sr-method-surface"
      blurb="논문을 어디까지 따랐고 어디서 해석했는지예요. 자기 실패 방식을 부르는 도구가 흠 없어 보이는 도구보다 믿을 만하다고 봤어요."
    >
      <Ships />
      <Seams />
      <Ledger />
      <Limitations />
      <Scorecard />
      <FreeParams />
      <Backtest />
    </SurfaceShell>
  );
}
