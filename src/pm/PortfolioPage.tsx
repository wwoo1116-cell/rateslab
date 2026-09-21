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

import { useCallback, useEffect, useMemo, useState } from 'react';

import { Select } from '@coinbase/cds-web/alpha/select';
import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@coinbase/cds-web/tables';
import { TextInput } from '@coinbase/cds-web/controls';
import { Text } from '@coinbase/cds-web/typography';

import { TimeChart } from '@/chart/TimeChart';
import { BacktestUnavailable } from '@/lib/api';
import { eul } from '@/lib/josa';
import { fmtKrw } from '@/lib/krw';
import { fetchMrPlan, type MrPlanRow } from '@/mr/api';
import { SplitColumn } from '@/mr/parts';
import { ROW_H } from '@/table/rowHeight';
import { directionClass } from '@/table/tint';
import { Cond } from '@/ui/Cond';
import { Field, Segmented } from '@/ui/ControlCard';
import { CONTROL_H } from '@/ui/controlHeight';
import { ErrorState, LoadingState } from '@/ui/DataState';
import { ThHelp } from '@/ui/ThHelp';
import { DROPDOWN_STYLES } from '@/ui/window/popup';

import {
  addTrade, closeTrade, enrollSeries, fetchPaper, retireSeries,
  type PaperManualLeg, type PaperRuleLeg, type PaperSheet,
} from './api';

const MINUS = '−';

/** 조건 한 줄 — 얼린 노브를 사람이 읽는 순서로.
 *
 *  계획면의 `condWord` 와 **같은 순서**다(룩백 · 진입/청산/손절 · 모드). 두
 *  화면이 같은 조건을 다른 순서로 적으면 「같은 조건인가」를 눈으로 못 맞춘다. */
function knobWord(k: PaperRuleLeg['knobs']): string {
  const n = (v: unknown) => (typeof v === 'number' ? v : Number(v));
  const mode = k.entryMode === 'touch' ? '이탈 즉시' : '레벨';
  return `${n(k.lookback)}일 · ${n(k.entryZ)}/${n(k.exitZ)}/${n(k.stopZ)}σ · ${mode}`;
}

/** 두 북의 누적을 **한 날짜 축**에 세운다.
 *
 *  서버는 북마다 자기 날짜만 낸다(등록일이 다르고 수동 거래는 띄엄띄엄이다).
 *  합집합 축 위에서 빈 날은 **직전 누적을 잇는다** — `null` 로 두면 선이 끊겨
 *  「그날 북이 없었다」로 읽히는데, 사실은 그날 움직임이 없었을 뿐이다. */
function joinAxis(sheet: PaperSheet) {
  const ts = [...new Set([...sheet.rule.daily.map((d) => d.t),
                          ...sheet.manual.daily.map((d) => d.t)])].sort();
  const walk = (rows: { t: string; cum: number }[]): (number | null)[] => {
    const at = new Map(rows.map((d) => [d.t, d.cum]));
    let last: number | null = rows.length ? 0 : null;
    return ts.map((t) => {
      const got = at.get(t);
      if (got !== undefined) last = got;
      return last;
    });
  };
  return { dates: ts, rule: walk(sheet.rule.daily), manual: walk(sheet.manual.daily) };
}

/** 히어로 한 칸 — 큰 수 하나와 뒷말 한 줄. 부호색은 캐논이 정한다. */
function Head({ label, v, note, big }: {
  label: string; v: number; note: string; big?: boolean;
}) {
  return (
    <VStack gap={0} minWidth={0}>
      <Text font="label1" as="span" color="fgMuted" noWrap>{label}</Text>
      <Text
        font={big ? 'display3' : 'title3'}
        as="span"
        tabularNumbers
        noWrap
        className={directionClass(v)}
      >
        {fmtKrw(v)}
      </Text>
      <Text font="legal" as="span" color="fgMuted" noWrap>{note}</Text>
    </VStack>
  );
}

/** 규칙 북의 표 — 등록한 것이 표본밖에서 무엇을 했나. */
function RuleTable({ legs, busy, onRetire }: {
  legs: PaperRuleLeg[]; busy: boolean; onRetire: (id: string) => void;
}) {
  if (legs.length === 0) {
    return (
      <Box paddingX={2} paddingBottom={2}>
        <Text font="legal" as="span" color="fgMuted">
          아직 등록한 계열이 없어요 — 아래에서 하나 올리면 그날부터 표본밖 기록이
          쌓여요.
        </Text>
      </Box>
    );
  }
  return (
    <Table bordered={false}>
      <TableHeader sticky>
        <TableRow>
          <TableCell as="th" scope="col">
            <Text font="caption" as="span" color="fgMuted">계열</Text>
          </TableCell>
          <TableCell as="th" scope="col">
            <ThHelp
              label="얼린 조건"
              help="등록하는 순간의 조건이에요. 계획면이 매일 조건을 다시 고르더라도 이 북은 안 바뀌어요 — 그래야 표본밖 기록이에요."
            />
          </TableCell>
          <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
            <ThHelp label="표본밖" help="등록일 이후 영업일 수예요." />
          </TableCell>
          <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
            <Text font="caption" as="span" color="fgMuted">손익</Text>
          </TableCell>
          <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
            <Text font="caption" as="span" color="fgMuted">최대낙폭</Text>
          </TableCell>
          <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
            <Text font="caption" as="span" color="fgMuted">해지</Text>
          </TableCell>
        </TableRow>
      </TableHeader>
      <TableBody>
        {legs.map((l) => (
          <TableRow key={l.id} style={{ height: ROW_H }}>
            <TableCell>
              <VStack as="span" className="sr-name-stack">
                <Text font="label1" as="span" noWrap>{l.label}</Text>
                <Text font="legal" as="span" color="fgMuted" noWrap>
                  {l.retired ? `${l.opened} ~ ${l.retired} 해지` : `${l.opened} 등록`}
                </Text>
              </VStack>
            </TableCell>
            <TableCell>
              <Text font="legal" as="span" color="fgMuted" noWrap>
                {knobWord(l.knobs)}
              </Text>
            </TableCell>
            <TableCell className="sr-num" justifyContent="flex-end">
              <VStack as="span" className="sr-name-stack">
                <Text font="label2" as="span" tabularNumbers noWrap>
                  {l.days}일
                </Text>
                <Text font="legal" as="span" color="fgMuted" noWrap>
                  {l.numTrades ? `${l.numTrades}건` : '거래 0건'}
                </Text>
              </VStack>
            </TableCell>
            <TableCell className="sr-num" justifyContent="flex-end">
              {/* 「아직」과 「0」은 다른 말이다 — 등록일 뒤의 봉이 없으면 돈이
                  아니라 사유가 선다(서버의 `why`). */}
              {l.why ? (
                <Text font="legal" as="span" color="fgMuted" noWrap title={l.why}>
                  아직
                </Text>
              ) : (
                <VStack as="span" className="sr-name-stack">
                  <Text
                    font="label2"
                    as="span"
                    tabularNumbers
                    noWrap
                    className={directionClass(l.totalPnl)}
                  >
                    {fmtKrw(l.totalPnl)}
                  </Text>
                  <Text font="legal" as="span" color="fgMuted" noWrap>
                    {l.winRate == null ? '승률 —' : `승률 ${Math.round(l.winRate * 100)}%`}
                  </Text>
                </VStack>
              )}
            </TableCell>
            <TableCell className="sr-num" justifyContent="flex-end">
              <Text font="label2" as="span" tabularNumbers noWrap>
                {l.why ? MINUS : fmtKrw(l.maxDrawdown)}
              </Text>
            </TableCell>
            <TableCell className="sr-num" justifyContent="flex-end">
              {l.retired ? (
                <Text font="legal" as="span" color="fgMuted" noWrap>해지됨</Text>
              ) : (
                <button
                  type="button"
                  className="sr-pillbtn"
                  disabled={busy}
                  onClick={() => onRetire(l.id)}
                  title="기록은 남고 「내린 날」이 붙어요 — 지우지 않아요."
                >
                  내리기
                </button>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

/** 수동 북의 표 — 내가 잡은 것. */
function ManualTable({ legs, asof, busy, onClose }: {
  legs: PaperManualLeg[]; asof: string | null; busy: boolean;
  onClose: (n: number) => void;
}) {
  const rows = legs.flatMap((l) => l.trades.map((t) => ({ leg: l, t })));
  if (rows.length === 0) {
    return (
      <Box paddingX={2} paddingBottom={2}>
        <Text font="legal" as="span" color="fgMuted">
          아직 잡은 거래가 없어요 — 아래에서 한 건 담으면 그날부터 규칙 북과 나란히
          서요.
        </Text>
      </Box>
    );
  }
  return (
    <Table bordered={false}>
      <TableHeader sticky>
        <TableRow>
          <TableCell as="th" scope="col">
            <Text font="caption" as="span" color="fgMuted">계열</Text>
          </TableCell>
          <TableCell as="th" scope="col">
            <Text font="caption" as="span" color="fgMuted">방향</Text>
          </TableCell>
          <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
            <Text font="caption" as="span" color="fgMuted">진입</Text>
          </TableCell>
          <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
            <ThHelp label="Delta" help="1bp 움직일 때의 손익이에요. 명목이 아니라 감도로 적어요 — 이 데스크의 규약이에요." />
          </TableCell>
          <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
            <ThHelp
              label="손익"
              help="비용까지 반영한 값이에요. 실가격 대사가 붙은 계열은 평가·캐리·롤다운·조달로 갈려요."
            />
          </TableCell>
          <TableCell as="th" scope="col" className="sr-num" justifyContent="flex-end">
            <Text font="caption" as="span" color="fgMuted">청산</Text>
          </TableCell>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map(({ leg, t }) => (
          <TableRow key={t.n} style={{ height: ROW_H }}>
            <TableCell>
              <VStack as="span" className="sr-name-stack">
                <Text font="label1" as="span" noWrap>{leg.label}</Text>
                <Text font="legal" as="span" color="fgMuted" noWrap>
                  {leg.real ? '실가격 대사' : '엔진 근사 · 롤다운·조달 항 없음'}
                </Text>
              </VStack>
            </TableCell>
            <TableCell>
              <VStack as="span" className="sr-name-stack">
                <Text font="label2" as="span" noWrap>
                  {t.dir > 0 ? '리시브' : '페이'}
                </Text>
                <Text font="legal" as="span" color="fgMuted" noWrap>
                  {t.open ? `보유 ${t.bars}일` : `${t.bars}일 보유 후 청산`}
                </Text>
              </VStack>
            </TableCell>
            <TableCell className="sr-num" justifyContent="flex-end">
              <VStack as="span" className="sr-name-stack">
                <Text font="label2" as="span" tabularNumbers noWrap>{t.entryT}</Text>
                <Text font="legal" as="span" color="fgMuted" noWrap>
                  {t.open ? `~ ${asof ?? '현재'}` : `~ ${t.exitT}`}
                </Text>
              </VStack>
            </TableCell>
            <TableCell className="sr-num" justifyContent="flex-end">
              <Text font="label2" as="span" tabularNumbers noWrap>
                {`${(t.notional / 10_000).toLocaleString()}만원/bp`}
              </Text>
            </TableCell>
            <TableCell className="sr-num" justifyContent="flex-end">
              <VStack as="span" className="sr-name-stack">
                <Text
                  font="label2"
                  as="span"
                  tabularNumbers
                  noWrap
                  className={directionClass(t.pnl)}
                >
                  {fmtKrw(t.pnl)}
                </Text>
                <Text font="legal" as="span" color="fgMuted" noWrap>
                  {`비용 ${fmtKrw(t.cost)}`}
                </Text>
              </VStack>
            </TableCell>
            <TableCell className="sr-num" justifyContent="flex-end">
              {t.open ? (
                <button
                  type="button"
                  className="sr-pillbtn"
                  disabled={busy || !asof}
                  onClick={() => onClose(t.n)}
                  title={`마지막 봉(${asof ?? '—'}) 기준으로 닫아요.`}
                >
                  닫기
                </button>
              ) : (
                <Text font="legal" as="span" color="fgMuted" noWrap>청산됨</Text>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function PortfolioPage() {
  const [sheet, setSheet] = useState<PaperSheet>();
  const [plan, setPlan] = useState<MrPlanRow[]>([]);
  const [error, setError] = useState<string>();
  const [unavailable, setUnavailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string>();

  /* 손잡이는 **북마다 따로**다. 한 상태를 둘이 나눠 쓰면 거래를 담으려고 고른
     계열이 등록 칸까지 바꾸는데(그쪽은 이미 등록된 것을 목록에서 빼므로 방금 고른
     것이 사라지기도 한다), 두 북은 서로 다른 결정이라 그 연동이 틀렸다. */
  const [pickEnroll, setPickEnroll] = useState('');
  const [pickTrade, setPickTrade] = useState('');
  const [dir, setDir] = useState<'pay' | 'receive'>('pay');
  const [entry, setEntry] = useState('');

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

  /* 등록할 수 있는 계열은 **계획면이 아는 것**이다 — 여기서 목록을 다시 만들면
     두 화면의 유니버스가 갈린다. 계획면이 아직 굽는 중이면 목록이 비고, 서버가
     등록을 409 로 막는다(그 사유를 그대로 세운다). */
  useEffect(() => {
    fetchMrPlan()
      .then((p) => {
        setPlan(p.rows);
      })
      .catch(() => setPlan([]));
  }, []);

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

  const axis = useMemo(() => (sheet ? joinAxis(sheet) : null), [sheet]);

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

  const enrolledIds = new Set(sheet.rule.legs.map((l) => l.id));
  /* 손익 선의 잉크 — **누적의 부호**가 정한다(백테스트 손익 차트의 그 규칙). */
  const pnlColor = sheet.manual.cum >= 0 ? 'var(--sr-up)' : 'var(--sr-down)';
  const options = plan.map((r) => ({ value: r.id, label: r.label }));
  const enrollable = options.filter((o) => !enrolledIds.has(o.value));
  /* **고른 것이 목록에 없으면 첫 칸이다.** 등록 목록은 이미 올린 계열을 빼므로,
     방금 등록한 계열을 고른 채로 두면 값이 목록 밖이 되고 CDS `Select` 의
     트리거가 **글자 없이** 선다 — 읽는 사람에게는 고장난 칸이다(실측 2026-09-21).
     상태를 고치지 않고 **그릴 때** 떨어뜨린다: 목록은 자료에 달렸고 상태는 사람의
     것이라, 자료가 바뀔 때마다 사람의 선택을 덮어쓰면 그게 더 나쁘다. */
  const enrollValue =
    enrollable.some((o) => o.value === pickEnroll) ? pickEnroll
      : (enrollable[0]?.value ?? '');
  const tradeValue =
    options.some((o) => o.value === pickTrade) ? pickTrade : (options[0]?.value ?? '');

  return (
    <VStack gap={1.5} width="100%" flexGrow={1} minHeight={0}>
      {/* ── 조건 바 ─────────────────────────────────────────────────────── */}
      <VStack className="sr-rv-bar" flexShrink={0} gap={0.5} width="100%">
        <HStack gap={1.5} alignItems="center" flexWrap="wrap">
          <Cond k="장부 개설" v={sheet.opened ?? '아직 없어요'} strong />
          <Cond k="기준일" v={sheet.asof ?? '—'} />
          <Cond k="규칙 북" v={`${sheet.rule.enrolled}계열`} />
          <Cond k="수동 북" v={`${sheet.manual.trades}건 · 보유 ${sheet.manual.open}`} />
          <Cond k="비용" v={`편도 ${sheet.costBp}bp`} />
          <Cond k="Delta" v={`${(sheet.notional / 10_000).toLocaleString()}만원/bp`} />
          {busy ? (
            <Text font="legal" as="span" color="fgMuted" noWrap>쓰는 중…</Text>
          ) : null}
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

      {/* ── 히어로 — 셋째 수(차이)가 이 화면이 묻는 물음이다 ───────────── */}
      <HStack gap={3} alignItems="flex-end" flexWrap="wrap" flexShrink={0} width="100%">
        <Head
          label="오늘 — 내 판단 − 규칙"
          v={sheet.diff.today}
          note={`누적 ${fmtKrw(sheet.diff.cum)}`}
          big
        />
        <Head
          label="규칙 북 오늘"
          v={sheet.rule.today}
          note={`누적 ${fmtKrw(sheet.rule.cum)} · ${sheet.rule.enrolled}계열`}
        />
        <Head
          label="수동 북 오늘"
          v={sheet.manual.today}
          note={`누적 ${fmtKrw(sheet.manual.cum)} · ${sheet.manual.trades}건`}
        />
      </HStack>

      {/* ── 구르는 칸 — 차트와 두 북 ───────────────────────────────────── */}
      <VStack gap={1.5} width="100%" flexGrow={1} minHeight={0} style={{ overflowY: 'auto' }}>
        {axis && axis.dates.length > 1 ? (
          <VStack className="sr-card" flexShrink={0} width="100%">
            <HStack alignItems="center" justifyContent="space-between" gap={1}
              paddingX={2} paddingTop={1.5} paddingBottom={0.5}>
              <Text font="label1" as="h2" noWrap>누적 손익</Text>
              <Text font="legal" as="span" color="fgMuted" noWrap>
                {axis.dates[0]} ~ {axis.dates[axis.dates.length - 1]}
              </Text>
            </HStack>
            <Box paddingX={2} paddingBottom={2} width="100%">
              {/* 주선은 **수동 북**(내가 한 것)이고 규칙 북이 기준선이다 — 기준은
                  흐린 선, 지금 재는 것이 진한 선(캐논 `palette.dim`). */}
              <TimeChart
                dates={axis.dates}
                height={200}
                accessibilityLabel="규칙 북과 수동 북의 누적 손익"
                lines={[
                  {
                    id: 'rule',
                    values: axis.rule,
                    color: (p) => p.dim('var(--sr-fg-muted)', 60),
                    width: 1,
                  },
                  {
                    id: 'manual',
                    values: axis.manual,
                    /* 손익 차트의 캐논 그대로 — 부호 방향색 + **흐린** 면
                       (`backtest/LinkedCharts` 의 그 14%). 면을 안 흐리면 그림이
                       통째로 파랗게 차서 기준선이 그 밑에 묻힌다(실측). */
                    color: (p) => p.resolve(pnlColor),
                    areaColor: (p) => p.dim(pnlColor, 14),
                    width: 2,
                    area: 'solid',
                    format: (v) => fmtKrw(v),
                  },
                ]}
              />
            </Box>
          </VStack>
        ) : null}

        {/* ── 규칙 북 ──────────────────────────────────────────────────── */}
        <VStack className="sr-card" flexShrink={0} width="100%">
          <HStack alignItems="center" justifyContent="space-between" gap={1}
            paddingX={2} paddingTop={1.5} paddingBottom={0.5}>
            <Text font="label1" as="h2" noWrap>규칙 북</Text>
            <Text font="legal" as="span" color="fgMuted" noWrap>
              등록한 조건이 시키는 대로 — 사람 손이 안 들어가요
            </Text>
          </HStack>
          <RuleTable
            legs={sheet.rule.legs}
            busy={busy}
            onRetire={(id) =>
              write(() => retireSeries(id),
                    `${id}${eul(id)} 내렸어요 — 기록은 남아요.`)}
          />
          {/* 누적 분해 — **클릭 없이** 선다 [OWNER 2026-09-09 의 그 규율].
              부품은 계획면의 것을 그대로 임포트한다(같은 것을 두 번 만들지 않는다). */}
          {sheet.rule.split ? (
            <Box paddingX={2} paddingBottom={1.5} className="sr-stats">
              <SplitColumn split={sheet.rule.split} />
            </Box>
          ) : null}
          {/* 등록 — 조건은 **서버가** 계획면 캐시에서 집는다(요청이 안 실어 온다). */}
          <HStack gap={1.5} alignItems="flex-end" paddingX={2} paddingBottom={2} flexWrap="wrap">
            <Box width={220}>
              <Field label="계열" help="계획면이 아는 계열이에요. 조건은 등록하는 순간 그 화면이 쓰는 것으로 얼려요.">
                <Select
                  size="s"
                  font="legal"
                  styles={DROPDOWN_STYLES}
                  accessibilityLabel="등록할 계열"
                  value={enrollValue}
                  onChange={(v: unknown) => setPickEnroll(v == null ? '' : String(v))}
                  options={enrollable}
                />
              </Field>
            </Box>
            <button
              type="button"
              className="sr-pillbtn"
              disabled={busy || !enrollValue}
              onClick={() =>
                write(() => enrollSeries(enrollValue),
                      `${enrollValue}${eul(enrollValue)} 등록했어요 — 오늘부터 표본밖이에요.`)}
            >
              규칙 북에 등록
            </button>
            <Text font="legal" as="span" color="fgMuted">
              {plan.length === 0
                ? '계획면을 아직 못 읽었어요 — Strategy/Mean Reversion 을 한 번 열어 주세요.'
                : '한 번 등록한 계열은 조건을 안 덮어써요. 조건을 갈려면 내렸다가 다시 올려요.'}
            </Text>
          </HStack>
        </VStack>

        {/* ── 수동 북 ──────────────────────────────────────────────────── */}
        <VStack className="sr-card" flexShrink={0} width="100%">
          <HStack alignItems="center" justifyContent="space-between" gap={1}
            paddingX={2} paddingTop={1.5} paddingBottom={0.5}>
            <Text font="label1" as="h2" noWrap>수동 북</Text>
            <Text font="legal" as="span" color="fgMuted" noWrap>
              내가 직접 잡은 것 — 규칙을 안 따르는 판단도 들어가요
            </Text>
          </HStack>
          <ManualTable
            legs={sheet.manual.legs}
            asof={sheet.asof}
            busy={busy}
            onClose={(n) =>
              write(() => closeTrade(n, sheet.asof ?? ''),
                    `${n}번 거래를 닫았어요.`)}
          />
          {sheet.manual.split ? (
            <Box paddingX={2} paddingBottom={1.5} className="sr-stats">
              <SplitColumn split={sheet.manual.split} />
            </Box>
          ) : null}
          <HStack gap={1.5} alignItems="flex-end" paddingX={2} paddingBottom={2} flexWrap="wrap">
            <Box width={220}>
              <Field label="계열">
                <Select
                  size="s"
                  font="legal"
                  styles={DROPDOWN_STYLES}
                  accessibilityLabel="거래할 계열"
                  value={tradeValue}
                  onChange={(v: unknown) => setPickTrade(v == null ? '' : String(v))}
                  options={options}
                />
              </Field>
            </Box>
            <Box width={180}>
              <Field label="방향" help="계열이 −bp 라 「리시브」가 값이 오르는 쪽이에요 — 엔진 규약 그대로예요.">
                <Segmented
                  value={dir}
                  onChange={setDir}
                  label="방향"
                  options={[
                    { value: 'pay', label: '페이', title: '값이 내리는 쪽에 건다' },
                    { value: 'receive', label: '리시브', title: '값이 오르는 쪽에 건다' },
                  ]}
                />
              </Field>
            </Box>
            <Box width={150}>
              <Field label="진입일" help="그날 봉이 있어야 해요 — 없으면 담기지 않고 화면이 그 사실을 적어요.">
                <TextInput
                  size="s"
                  fontSize="legal"
                  height={CONTROL_H}
                  accessibilityLabel="진입일 (YYYY-MM-DD)"
                  value={entry}
                  placeholder={sheet.asof ?? '2026-09-18'}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setEntry(e.target.value)}
                />
              </Field>
            </Box>
            <button
              type="button"
              className="sr-pillbtn"
              disabled={busy || !tradeValue || !(entry || sheet.asof)}
              onClick={() =>
                write(
                  () => addTrade({
                    id: tradeValue,
                    dir: dir === 'receive' ? 1 : -1,
                    entry: entry || (sheet.asof ?? ''),
                    label: options.find((o) => o.value === tradeValue)?.label,
                  }),
                  `${tradeValue} ${dir === 'receive' ? '리시브' : '페이'}${
                    eul(dir === 'receive' ? '리시브' : '페이')} 담았어요.`)}
            >
              거래 담기
            </button>
            <Text font="legal" as="span" color="fgMuted">
              Delta 는 {(sheet.notional / 10_000).toLocaleString()}만원/bp 고정이에요 —
              명목은 이 화면의 것이 아니에요.
            </Text>
          </HStack>
        </VStack>
      </VStack>
    </VStack>
  );
}
