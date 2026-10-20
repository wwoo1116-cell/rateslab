'use client';

/* Lab 「모형」 · 전략 면 — 경로 하나를 놓으면 나오는 데스크 노트.
 *
 * ## 파는 것은 커브 그림이 아니라 **짧은 논증과 트레이드 표현**이다
 *
 *     뷰 · 함의 · 논거 · 트레이드 · 리스크
 *
 * 다섯 줄이 제품 전부다. 입력은 **정책금리 경로 하나**이고 나머지는 전부
 * 자동이고 읽기 전용이다.
 *
 * ## 왜 손잡이가 하나뿐인가
 *
 * 시나리오 화면에는 여섯이 있다(물가·갭·수출·Fed·유가·정책). 그 화면은 «모형이
 * 뭘 하나» 를 보는 실험대고, 이 면은 «내 뷰를 어떻게 표현하나» 를 답하는 데스크
 * 도구다. 손잡이를 여섯 두면 데스크가 매일 여섯 번 결정을 내려야 하고, 그러면
 * 아무도 안 쓴다.
 *
 * ## 골격은 시나리오 것이다
 *
 * **좌 설정 열 / 우 결과 카드.** 같은 종류의 일(입력 → 결과)을 하는 화면이라
 * 골격도 같아야 하고, `ControlCard` 는 시뮬·시나리오가 이미 쓰는 것을 그대로
 * 쓴다 — 두 벌을 두면 한쪽만 고쳐지는 날이 온다.
 *
 * **노트는 카드 안에서 구른다.** 페이지가 스크롤하지 않는 100vh 기둥이라
 * (`PRODUCT.md`), 카드가 자기 스크롤을 안 지면 다섯 줄 중 뒤의 둘과 가정 띠가
 * 아예 닿지 않는다 — 실측 2026-08-21 에 그 상태로 한 번 떴다.
 *
 * ## 화면이 못 하는 것을 화면이 말한다
 *
 * 10년은 트레이드 후보에 없고(12개월 포워드가 커브 밖), 다음 금통위 자리에는
 * 커브 숫자가 없고(분기 모형), 「이 답이 0 으로 놓은 것」 띠에는 지금 델타를
 * 움직이는 항목이 하나도 없다. 셋 다 빈칸이 아니라 **문장**으로 선다.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import { Select } from '@coinbase/cds-web/alpha/select';
import { Chip } from '@coinbase/cds-web/chips';
import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Pressable } from '@coinbase/cds-web/system';
import { SegmentedTabs } from '@coinbase/cds-web/tabs';
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@coinbase/cds-web/tables';
import { Text } from '@coinbase/cds-web/typography';

import { ControlCard } from '@/ui/ControlCard';
import { ErrorState, LoadingState } from '@/ui/DataState';
import { DROPDOWN_STYLES } from '@/ui/window/popup';

import { ANCHORS, anchorProps, eq, hrefFor, ledgerRow } from '../anchors';
import { useUrlState } from '@/ui/useUrlState';
import { ErrorBoundary } from '@/ui/ErrorBoundary';
import { ModelChart } from '@/lab/scenario/ModelChart';
import type { ScenarioRow } from '@/lab/scenario/assemble';

import {
  STEP_CHOICES,
  meetings,
  paramToSteps,
  marketSteps,
  runningLevels,
  stepsToDots,
  stepsToParam,
  type Steps,
} from './meetings';
import { AnchorsUnavailable, fetchAnchors } from './anchors';
import {
  ASSUMPTIONS,
  CONDITIONAL_NOTE,
  ENGINE_STATUS,
  NO_DELTA_ITEMS,
  STALENESS_LABEL,
  assumptionValue,
  effectGroups,
} from './assumptions';
import { decompose, type Term } from './decompose';
import {
  DEFAULT_HORIZON,
  HORIZONS,
  MPC_NO_CURVE,
  MPC_NO_TERMS,
  NO_CARRY_HERE,
  buildNote,
  noteText,
  pathInWords,
  type HorizonId,
} from './note';
import { BASIS, PINNED_Q, TENORS, outOfDomain, solvePath, type Tenor } from './path';
import { riskLines } from './risk';
import {
  HEADLINE_TENOR,
  candidates,
  gapVector,
  headlineGap,
  type StrategyAnchors,
} from './trades';
import { ROUTE_MISSING_DETAIL } from '@/lib/apiBase';

/** 점 눈금. 전부 기저의 검증 영역(`domain.policy_bp_per_q`) 안이다 — 밖을 고를
 *  수 있게 두면 화면이 «여기부터 외삽» 이라고 말하기 전에 이미 밖에 나가 있다. */
/** 다섯 테너 전부 같은 등급이다 [진단 §C.5]. IRS 다리는 기간프리미엄을 안 받고
 *  OU 스프레드는 편차에서 상쇄되므로, 남는 것은 정책 경로의 산술뿐이다. */
const PROVENANCE = '경로 산술';

const TENOR_LABEL: Record<Tenor, string> = {
  '1y': '1Y',
  '2y': '2Y',
  '3y': '3Y',
  '5y': '5Y',
  '10y': '10Y',
};

/** 논거 항이 가리키는 자리.
 *
 * **여기 있던 주소 셋이 아무 데도 안 닿고 있었다** [2026-08-24 전수 확인].
 * 세션 3 이 타깃을 세우는 중이라 그럴 수 있다고 적어 둔 주석이 그대로 남아
 * 있었는데, 세 면이 다 찬 뒤에도 아무도 다시 안 봤다.
 *
 *     eq('36-37')                 등록부는 번호를 **낱개**로 단다 → 36
 *     ledgerRow('r_star')         원장 키는 케밥이고, r* 행은 **없다**
 *     ledgerRow('policy_conditioning')  실제 키는 `policy-conditioning`
 *
 * 링크가 안 닿는 것은 조용하다 — 해시가 없으면 브라우저가 그냥 면 맨 위에
 * 선다. 그래서 `guards/model-anchor-targets.test.ts` 가 이제 이 두 표의
 * 타깃을 실제 페이로드가 낳는 앵커 집합과 대조한다. 그러려고 export 한다. */
export const TERM_HREF: Record<Term['key'], string> = {
  /* 기대가설은 eq (36)(37) 두 식인데 등록부는 낱개로 단다. 첫 식에 세운다. */
  eh: hrefFor(eq('36')),
  rule: hrefFor(eq('35')),
  cd: hrefFor(ANCHORS.model.channelPolicy),
  tp: hrefFor(ANCHORS.model.channelFinancial),
  spread: hrefFor(ANCHORS.model.channelFinancial),
};

export const RISK_HREF: Record<string, string> = {
  /* r* 줄이 답하는 것은 «왜 0 인가» 이고, 그 답이 사는 행이 편차 공간이다. */
  'r-star': hrefFor(ledgerRow('deviation-space')),
  /* 지평 이탈 줄은 이제 자기 행을 갖는다 — D.4 가 세운 `residual-tail`. */
  'horizon-exit': hrefFor(ledgerRow('residual-tail')),
  'rule-deviation': hrefFor(ANCHORS.method.ledger),
};

const bpTxt = (v: number) =>
  Math.abs(v) < 0.05 ? '0.0' : `${v < 0 ? '−' : '+'}${Math.abs(v).toFixed(1)}`;
const dirCls = (v: number | null) =>
  v == null || Math.abs(v) < 0.05 ? undefined : v > 0 ? 'sr-up' : 'sr-down';

const HORIZON_TABS = HORIZONS.map((x) => ({ id: x.id, label: x.label }));

/* ── 경로는 URL 에 산다, 그리고 «변화량» 이다 ────────────────────────────
 *
 * 예전에는 컴포넌트 상태뿐이라 새로고침에 날아갔고, 값이 **레벨(누적)** 이라
 * 동결을 유지하려면 뒤의 칸을 전부 다시 골라야 했다 [OWNER 2026-08-24].
 * 지금은 회의별 변화량이고, 안 건드린 회의는 0 이다. 표기와 검증은
 * `meetings.ts` 가 진다.
 *
 *     ?g=lab&lab=model&view=strategy&p=2026-08-27:-25,2027-01:-25
 *
 * 쓰기는 `replace` 다 — 셀렉트 한 번은 목적지가 아니다. */
const PATH_KEY = 'p';

/** 손으로 여덟 번 누르지 않아도 되는 뷰들.
 *
 *  고른 넷은 **모형의 응답 모양이 갈리는 자리**다 — 아무것도 안 함, 다음 회의
 *  한 번 인하, 두 회의 연속 인하, 인상 사이클. 「쓸 만한 시나리오」 를 고른 게
 *  아니라 응답이 달라지는 자리를 골랐다. 회의 키를 모르므로 **순번으로** 적고,
 *  누를 때 그날의 회의 목록에 붙인다. */
const PRESETS: { label: string; at: Record<number, number> }[] = [
  { label: '동결', at: {} },
  { label: '−25 한 번', at: { 0: -25 } },
  { label: '−25 두 번', at: { 0: -25, 1: -25 } },
  { label: '+25 두 번', at: { 0: 25, 1: 25 } },
];

export function StrategySurface() {
  const [pathParam, setPathParam] = useUrlState(PATH_KEY, undefined);
  /* 회의 목록은 **오늘**이 정한다. 마운트 뒤에 잡는다 — 서버에서 만든 목록과
     클라이언트의 것이 자정 근처에서 갈리면 hydration 이 어긋난다. */
  const [today, setToday] = useState<Date | null>(null);
  useEffect(() => setToday(new Date()), []);
  const ms = useMemo(() => (today ? meetings(today) : []), [today]);

  const steps = useMemo(() => paramToSteps(pathParam, ms) ?? {}, [pathParam, ms]);
  const dots = useMemo(() => stepsToDots(steps, ms), [steps, ms]);
  const levels = useMemo(() => runningLevels(steps, ms), [steps, ms]);
  const setStep = (key: string, v: number) =>
    setPathParam(stepsToParam({ ...steps, [key]: v }));
  const setPreset = (at: Record<number, number>) => {
    const next: Steps = {};
    for (const [i, v] of Object.entries(at)) {
      const m = ms[Number(i)];
      if (m) next[m.key] = v;
    }
    setPathParam(stepsToParam(next));
  };
  const [horizon, setHorizon] = useState<HorizonId>(DEFAULT_HORIZON);
  const [anchors, setAnchors] = useState<StrategyAnchors | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  /** 각주를 펼쳤나. **유도값이 아니라 읽는 사람의 선택**이라 상태로 든다.
   *  URL 에는 안 넣는다 — 공유한 링크가 남의 읽기 습관을 강요할 이유가 없다.
   *
   *  오너: 「여전히 내가 필요없는 정보가 너무 많음」. 각주를 지우지는 않는다 —
   *  이 화면의 값은 못 하는 것을 이름으로 부르는 데 있고, 지우면 그게 사라진다.
   *  기본으로 접고, 묻는 사람에게만 편다. */
  const [showNotes, setShowNotes] = useState(false);

  const load = useCallback(async () => {
    setRetrying(true);
    try {
      setAnchors(await fetchAnchors());
      setError(null);
      setUnavailable(false);
    } catch (e) {
      if (e instanceof AnchorsUnavailable) setUnavailable(true);
      else setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRetrying(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const h = HORIZONS.find((x) => x.id === horizon)?.h ?? null;
  const sol = useMemo(() => solvePath(dots), [dots]);
  const decomp = useMemo(() => (h === null ? [] : decompose(sol, h)), [sol, h]);
  const gaps = useMemo(
    () => (anchors && h !== null ? gapVector(sol, anchors, h) : null),
    [anchors, sol, h],
  );
  const head = gaps ? headlineGap(gaps) : null;
  /* 커브가 없거나 12개월 자리가 아니어도 **논거·리스크는 3년으로 선다** —
     그 둘은 구운 기저만으로 나오니까. 자리 번호가 아니라 이름으로 찾는다. */
  const headDecomp = decomp.find((d) => d.tenor === HEADLINE_TENOR) ?? null;
  const cands = useMemo(() => (gaps ? candidates(gaps) : []), [gaps]);

  /** 시장이 보는 12개월 정책 이동, bp. 호가에서 나온 **사실**이다. */
  const marketBp = anchors?.irs['1y']?.carry12mBp ?? null;
  /** 그것을 회의 결정으로 편 것. 총량은 시장, 배분은 우리 것. */
  const mkt = useMemo(() => marketSteps(marketBp, ms), [marketBp, ms]);
  /** 지금 놓은 경로의 12개월 이동 = 넷째 분기 말 레벨. */
  const mineBp = dots[3] ?? 0;

  /* 커브 셋을 그리는 데 필요한 것은 `ScenarioRow` 인데, 「전략」 면의 `TenorGap`
     이 이미 그 값을 전부 갖고 있다. **차트를 새로 만들지 않는다** — 시나리오
     면이 화면에서 내려갈 때 이 그림도 같이 내려갔을 뿐이고, 백테스트 종목
     차트의 해부를 그대로 옮긴 판이라 이 앱의 표준이다(`ModelChart` 머리글). */
  const curveRows = useMemo<ScenarioRow[] | null>(
    () =>
      gaps
        ? gaps.gaps.map((g) => ({
            tenor: g.tenor,
            spot: g.spot,
            market12m: g.marketPct,
            scenario12m: g.modelPct,
            deltaBp: g.deltaBp,
            marketCarryBp: g.carry12mBp,
            vsMarketBp: g.vsMarketBp,
            live: g.live,
          }))
        : null,
    [gaps],
  );
  const risks = useMemo(() => riskLines(sol, headDecomp), [sol, headDecomp]);
  const note = useMemo(
    () =>
      buildNote({
        sol,
        gaps,
        headlineGap: head,
        headlineDecomp: headDecomp,
        candidates: cands,
        risks,
        h,
        provenance: PROVENANCE,
      }),
    [sol, gaps, head, headDecomp, cands, risks, h],
  );

  /* 화면에 보이는 평문과 복사되는 평문은 **한 문자열**이다. 두 벌로 만들면
     둘이 갈리는 날이 오고, 그때 복사된 쪽이 틀린다. */
  const exportText = useMemo(
    () =>
      noteText(note, {
        asof: anchors?.asof ?? '커브 없음',
        basisAsOf: ENGINE_STATUS.basis_as_of,
      }),
    [note, anchors],
  );

  const groups = useMemo(() => effectGroups(ASSUMPTIONS), []);
  const outside = outOfDomain(dots);
  /** 여덟 점이 다 0 인가. 유도값이라 상태로 안 든다. */
  const frozen = dots.every((v) => v === 0);
  const stale = ENGINE_STATUS.staleness;

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(exportText);
      setCopied('클립보드에 담았어요');
    } catch {
      setCopied('클립보드를 못 썼어요 — 아래 글을 직접 복사하세요');
    }
  };

  /* 루트 행은 **`flexWrap` 을 안 쓴다** [실측 2026-08-21]. 줄바꿈하는 flex 행에서는
     줄의 가로높이가 «가장 큰 항목의 내용 높이» 로 정해져서, 노트 카드가 1,348px 로
     부풀고 컨테이너(668px)를 넘어섰다 — 그러면 카드가 자기 스크롤을 못 만들고
     리스크 세 줄과 가정 띠가 화면 밖에 남는다. */
  return (
    <HStack gap={2} width="100%" flexGrow={1} minHeight={0} alignItems="stretch">
      {/* ── 유일한 입력 ─────────────────────────────────────────────────── */}
      <VStack className="sr-strat-controls" gap={1}>
        <ControlCard title="정책금리 경로">
          <Text as="p" font="legal" color="fgMuted">
            회의마다 무엇을 할지만 고르면 돼요 — 안 건드린 회의는 동결이에요.
          </Text>

          {/* **시장이 보는 것**을 먼저 말한다 [OWNER 2026-08-24].
              기준선이 없으면 내가 놓은 경로가 큰지 작은지 알 방법이 없다.
              총량(bp)은 1Y1Y 포워드에서 나온 **사실**이고, 그것을 회의로 나누는
              것은 **우리 배분**이다 — 그 둘을 갈라 말한다. */}
          {marketBp !== null ? (
            <VStack gap={0.25} width="100%">
              <HStack gap={1} alignItems="baseline" flexWrap="wrap">
                <Text as="span" font="caption" color="fgMuted" noWrap>
                  시장
                </Text>
                <Text as="span" font="label2" tabularNumbers noWrap className={dirCls(marketBp) ?? ''}>
                  {marketBp > 0 ? '+' : '−'}
                  {Math.abs(marketBp).toFixed(0)}bp
                </Text>
                <Text as="span" font="caption" color="fgMuted" noWrap>
                  내 경로
                </Text>
                <Text as="span" font="label2" tabularNumbers noWrap className={dirCls(mineBp) ?? ''}>
                  {mineBp === 0 ? '0' : `${mineBp > 0 ? '+' : '−'}${Math.abs(mineBp)}`}bp
                </Text>
              </HStack>
              <Text as="span" font="caption" color="fgMuted">
                12개월 정책 이동이에요 — 시장 쪽은 1Y1Y 포워드에서 나온 값이고,
                그걸 회의로 나눈 건 우리 배분이에요.
              </Text>
            </VStack>
          ) : null}

          {/* 프리셋. 회의 **순번**으로 적는다 — 회의 키는 날짜가 정하고 그건
              오늘이 정하기 때문이다. 「동결」 이 되돌리기를 겸한다. */}
          <HStack gap={0.5} flexWrap="wrap">
            {mkt ? (
              <Chip
                size="xs"
                className="sr-chip-toggle"
                aria-pressed={
                  Object.keys(mkt).length > 0 &&
                  ms.every((m) => (steps[m.key] ?? 0) === (mkt[m.key] ?? 0))
                }
                accessibilityLabel="시장이 프라이싱한 경로를 놓아요"
                onClick={() => setPathParam(stepsToParam(mkt))}
              >
                시장대로
              </Chip>
            ) : null}
            {PRESETS.map((ps) => {
              const on = ms.every((m, i) => (steps[m.key] ?? 0) === (ps.at[i] ?? 0));
              return (
                <Chip
                  key={ps.label}
                  size="xs"
                  className="sr-chip-toggle"
                  aria-pressed={on}
                  accessibilityLabel={`${ps.label} 경로를 놓아요`}
                  onClick={() => setPreset(ps.at)}
                >
                  {ps.label}
                </Chip>
              );
            })}
          </HStack>

          {/* 회의 한 줄 = 날짜 · 무엇을 하나 · **그래서 얼마가 되나**.
              오른쪽의 누적 레벨이 곧 경로 그림이다 — 「시각적으로 어떻게 될
              거다」 가 없다는 지적이 이 열을 만들었다 [OWNER]. */}
          <VStack gap={0} width="100%" className="sr-mpc-list">
            {ms.map((m, i) => {
              const v = steps[m.key] ?? 0;
              const lv = levels[i] ?? 0;
              const first = i === 0 || ms[i - 1]?.qLabel !== m.qLabel;
              return (
                <VStack key={m.key} gap={0} width="100%">
                  {first ? (
                    <Text as="span" font="caption" color="fgMuted" className="sr-mpc-q">
                      {m.qLabel}
                    </Text>
                  ) : null}
                  <HStack gap={0.5} alignItems="center" width="100%" className="sr-mpc-row">
                    <Text
                      as="span"
                      font="legal"
                      color={m.dated ? undefined : 'fgMuted'}
                      noWrap
                      className="sr-mpc-when"
                      title={
                        m.dated
                          ? '한은이 낸 일정이에요'
                          : '한은이 아직 일정을 안 내서 달까지만 세운 자리예요'
                      }
                    >
                      {m.label}
                    </Text>
                    <Select
                      size="s"
                      font="legal"
                      styles={DROPDOWN_STYLES}
                      accessibilityLabel={`${m.label} 금통위 결정`}
                      value={String(v)}
                      onChange={(nv) => nv != null && setStep(m.key, Number(nv))}
                      options={STEP_CHOICES.map((o) => ({
                        value: String(o),
                        label: o === 0 ? '동결' : `${o > 0 ? '+' : '−'}${Math.abs(o)}`,
                      }))}
                    />
                    <Text
                      as="span"
                      font="legal"
                      tabularNumbers
                      noWrap
                      color={lv === 0 ? 'fgMuted' : undefined}
                      className={`sr-mpc-lv ${dirCls(lv) ?? ''}`}
                    >
                      {lv === 0 ? '0' : `${lv > 0 ? '+' : '−'}${Math.abs(lv)}`}
                    </Text>
                  </HStack>
                </VStack>
              );
            })}
          </VStack>
          <Text as="p" font="caption" color="fgMuted">
            날짜가 적힌 회의는 한은이 낸 일정이고, 달만 적힌 회의는 아직 안 냈어요
            — 연 8회 규칙(1·2·4·5·7·8·10·11월)으로 달까지만 세웠어요.
          </Text>
          {outside ? (
            <HStack gap={1} alignItems="center" flexWrap="wrap">
              <Chip size="xs" accessibilityLabel="검증 영역 밖 — 여기부터는 선형 외삽이에요">
                검증 영역 밖
              </Chip>
            </HStack>
          ) : null}
        </ControlCard>
      </VStack>

      {/* ── 노트 ────────────────────────────────────────────────────────── */}
      <VStack className="sr-card sr-strat-note" flexGrow={1} minWidth={0} minHeight={0}>
        {/* 카드 머리는 **한 층**이다 — 왼쪽에 지평, 오른쪽에 as-of. 시나리오
            결과 카드가 같은 자리에 같은 문법을 쓴다. */}
        <HStack gap={1.5} alignItems="center" flexWrap="wrap" paddingX={2} paddingTop={2}>
          <SegmentedTabs
            accessibilityLabel="지평"
            tabs={HORIZON_TABS}
            activeTab={HORIZON_TABS.find((t) => t.id === horizon) ?? null}
            onChange={(t) => t && setHorizon(t.id as HorizonId)}
          />
          {/* 각주·리스크·가정을 펴는 손잡이. 카드 머리 오른쪽은 백테스트 카드가
              기간 세그먼트를 두는 자리이고, 이 카드에서 그 자리에 서는 손잡이가
              이것 하나다. */}
          <Chip
            size="xs"
            className="sr-chip-toggle"
            aria-pressed={showNotes}
            accessibilityLabel="각주와 리스크·가정을 펴요"
            onClick={() => setShowNotes((v) => !v)}
            style={{ marginInlineStart: 'auto' }}
          >
            근거
          </Chip>
          <Text as="span" font="legal" color="fgMuted">
            모형 기저 {ENGINE_STATUS.basis_as_of} · {STALENESS_LABEL[stale.state]}
            {anchors ? ` · 커브 ${anchors.asof}` : ''}
          </Text>
        </HStack>

        <VStack className="sr-strat-scroll" gap={2} paddingX={2} paddingY={2}>
          {/* 뷰 */}
          <VStack gap={0.25} {...anchorProps(ANCHORS.strategy.view)}>
            <Text as="span" font="legal" color="fgMuted">
              뷰
            </Text>
            <Text as="p" font="title3">
              {pathInWords(dots)}
            </Text>
            <Text as="p" font="legal" color="fgMuted" {...anchorProps(ANCHORS.strategy.asOf)}>
              {ENGINE_STATUS.as_of_sentence}
            </Text>
          </VStack>

          {/* 함의 */}
          <VStack gap={0.25} {...anchorProps(ANCHORS.strategy.implication)}>
            <Text as="span" font="legal" color="fgMuted">
              함의
            </Text>
            {h === null ? (
              <>
                <Text as="p" font="title3">
                  {note.implication}
                </Text>
                <Text as="p" font="legal" color="fgMuted">
                  {MPC_NO_CURVE}
                </Text>
              </>
            ) : unavailable ? (
              <Text as="p" font="body" color="fgMuted">
                오늘의 커브가 없어서 시장 대비를 못 재요. {ROUTE_MISSING_DETAIL}
              </Text>
            ) : error ? (
              <ErrorState what="오늘의 커브" detail={error} onRetry={load} retrying={retrying} />
            ) : !anchors ? (
              <LoadingState what="오늘의 커브" />
            ) : (
              <Text as="p" font="title3" className={dirCls(head?.vsMarketBp ?? null)}>
                {note.implication}
              </Text>
            )}
          </VStack>

          {/* 커브 셋 — 「내가 생각하는 경로면 커브가 이렇게 된다」.
              오늘 · 모형 12개월 · 시장 12개월. 앞 둘의 간격이 트레이드고, 그 값이
              바로 위 「함의」 줄이다.

              **차트를 새로 안 만들었다** — 시나리오 면이 화면에서 내려갈 때 같이
              내려간 판이고, 백테스트 종목 차트의 해부를 그대로 옮긴 것이라 이
              앱의 표준이다(`lab/scenario/ModelChart.tsx` 머리글). */}
          {h !== null && curveRows && anchors ? (
            <VStack gap={0.5} width="100%" className="sr-strat-curve">
              <ErrorBoundary region="커브" fallback="커브를 그리지 못했어요.">
                <ModelChart rows={curveRows} asof={anchors.asof} />
              </ErrorBoundary>
            </VStack>
          ) : null}

          {/* 논거 */}
          <VStack gap={0.5} {...anchorProps(ANCHORS.strategy.argument)}>
            <Text as="span" font="legal" color="fgMuted">
              논거 — 이 bp 가 무엇으로 이루어져 있나
            </Text>
            {/* **동결은 표 위에서 말한다** [OWNER 2026-08-24]. 기본 경로가 동결
                이라 처음 여는 사람이 보는 것은 다섯 테너 × 여섯 항 = 서른 칸의
                `0.0` 이다. 이유(편차가 0 이면 통째로 0)는 표 **아래** 각주에만
                있어서, 그때까지 화면은 고장난 것처럼 보였다.
                기본값을 바꾸지는 않는다 — 아무것도 가정하지 않은 상태가 이
                물건의 정직한 출발점이고, 그 말을 화면이 하면 된다. */}
            {frozen ? (
              <Text as="p" font="body" color="fgMuted">
                아직 아무것도 가정하지 않았어요 — 왼쪽에 점을 하나라도 놓으면 이
                표에 숫자가 서요. 지금 0 인 건 계산이 안 된 게 아니라 편차가 0
                이라서예요.
              </Text>
            ) : null}
            {h === null ? (
              <Text as="p" font="body" color="fgMuted">
                {MPC_NO_TERMS}
              </Text>
            ) : (
              <>
                {/* 넓은 표는 자기 상자 안에서만 가로로 구른다 — 몸통이 가로로
                    밀리면 왼쪽 설정 열까지 같이 움직인다. */}
                <Box className="sr-strat-table" width="100%">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableCell>
                          <Text as="span" font="legal">
                            테너
                          </Text>
                        </TableCell>
                        {decomp[0]?.terms.map((t) => (
                          <TableCell key={t.key} className="sr-num" justifyContent="flex-end">
                            <a href={TERM_HREF[t.key]} title={t.note}>
                              <Text as="span" font="legal">
                                {t.label}
                              </Text>
                            </a>
                          </TableCell>
                        ))}
                        <TableCell className="sr-num" justifyContent="flex-end">
                          <Text as="span" font="legal">
                            합계
                          </Text>
                        </TableCell>
                        <TableCell className="sr-num" justifyContent="flex-end">
                          <Text as="span" font="legal">
                            준칙 몫
                          </Text>
                        </TableCell>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {decomp.map((d) => (
                        <TableRow key={d.tenor}>
                          <TableCell>
                            <Text as="span" font="legal">
                              {TENOR_LABEL[d.tenor]}
                            </Text>
                          </TableCell>
                          {/* 숫자는 등폭이어야 세로로 비교된다 — 이 표의 목적이
                              테너별 성분을 위아래로 훑는 것이다 [감사 2026-08-25]. */}
                          {d.terms.map((t) => (
                            <TableCell key={t.key} className="sr-num" justifyContent="flex-end">
                              <Text
                                as="span"
                                font="legal"
                                tabularNumbers
                                color={t.structuralZero ? 'fgMuted' : undefined}
                                className={t.structuralZero ? undefined : dirCls(t.value)}
                              >
                                {bpTxt(t.value)}
                              </Text>
                            </TableCell>
                          ))}
                          <TableCell className="sr-num" justifyContent="flex-end">
                            <Text as="span" font="label1" tabularNumbers className={dirCls(d.totalBp)}>
                              {bpTxt(d.totalBp)}
                            </Text>
                          </TableCell>
                          <TableCell className="sr-num" justifyContent="flex-end">
                            <Text as="span" font="legal" tabularNumbers color="fgMuted">
                              {d.ruleShare === null ? '—' : `${Math.round(d.ruleShare * 100)}%`}
                            </Text>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
                {showNotes ? (
                  <>
                    <Text as="p" font="legal" color="fgMuted">
                      다섯 항의 합이 합계와 정확히 같아요. 기간프리미엄과 스왑 스프레드가 0 인
                      건 안 잰 게 아니라 이 다리에 안 오기 때문이에요 — 열을 지우면 그 사실이
                      같이 지워져요.
                    </Text>
                    <Text as="p" font="legal" color="fgMuted">
                      다섯 테너뿐이에요 — 기저가 1Y·2Y·3Y·5Y·10Y 만 담아요. 나머지 만기는
                      보간해서 세우지 않아요.
                    </Text>
                  </>
                ) : null}
              </>
            )}
          </VStack>

          {/* 트레이드 */}
          <VStack gap={0.5} {...anchorProps(ANCHORS.strategy.trade)}>
            <Text as="span" font="legal" color="fgMuted">
              트레이드 — 모형 Δ − 시장 캐리
            </Text>
            {h === null ? (
              <Text as="p" font="body" color="fgMuted">
                {NO_CARRY_HERE}
              </Text>
            ) : !gaps ? (
              <Text as="p" font="body" color="fgMuted">
                오늘의 커브가 있어야 시장 대비를 재요.
              </Text>
            ) : cands.length === 0 ? (
              <Text as="p" font="body" color="fgMuted">
                {NO_CARRY_HERE}
              </Text>
            ) : (
              <VStack gap={0.25}>
                {cands.map((c) => (
                  <HStack key={c.label} gap={1} alignItems="baseline" flexWrap="wrap">
                    <Text as="span" font="label1" className={dirCls(c.bp)}>
                      {c.label}
                    </Text>
                    {/* 크기는 절댓값이다 — 방향은 이름이 이미 말한다.
                        「리시브 −55.2bp」 는 부호를 두 번 말하는 셈이다. */}
                    <Text as="span" font="legal">
                      {Math.abs(c.bp).toFixed(1)}bp
                    </Text>
                    {/* «수렴» 과 «여기까지밖에 못 봄» 은 다르다. 최댓값이 기저의
                        마지막 분기에 있으면 그건 수렴한 자리가 아니라 지평 끝이다. */}
                    <Text as="span" font="legal" color="fgMuted">
                      {c.convergenceAtEdge
                        ? `${c.convergenceQ}분기까지 계속 벌어져요 — 기저가 거기서 끝나요`
                        : `수렴 지평 ${c.convergenceQ}분기`}
                    </Text>
                    {c.interpolatedLeg ? (
                      <Text as="span" font="legal" color="fgMuted">
                        끝점이 호가가 아니에요
                      </Text>
                    ) : null}
                  </HStack>
                ))}
                {showNotes ? (
                  <>
                    {gaps.excluded.map((x) => (
                      <Text key={x.tenor} font="legal" color="fgMuted" as="p">
                        {TENOR_LABEL[x.tenor]} 는 후보에 없어요 — {x.why}
                      </Text>
                    ))}
                    <Text as="p" font="legal" color="fgMuted">
                      진입·목표·손절은 안 적어요 — 그건 트레이더 몫이에요.
                    </Text>
                    <Text as="p" font="legal" color="fgMuted">
                      캐리는 커브가 함의하는 이동이지 정책 기대가 아니에요 —
                      기간프리미엄이 섞여 있어요.
                    </Text>
                  </>
                ) : null}
              </VStack>
            )}
          </VStack>

          {/* 리스크와 가정 띠도 같은 토글 뒤에 선다 [OWNER 2026-08-24].
              「내가 필요없는 정보가 너무 많음」 — 매일 읽는 것은 위의 넷(뷰 ·
              함의 · 커브 · 논거)이고, 아래 둘은 그 숫자를 **의심할 때** 읽는
              것이다. 지우지 않고 접는다. */}
          {showNotes ? (
            <>
          <VStack gap={0.5} {...anchorProps(ANCHORS.strategy.risk)}>
            <Text as="span" font="legal" color="fgMuted">
              리스크
            </Text>
            {risks.map((r) => (
              <VStack
                key={r.key}
                gap={0.25}
                {...anchorProps(
                  r.key === 'r-star'
                    ? ANCHORS.strategy.rStar
                    : r.key === 'horizon-exit'
                      ? ANCHORS.strategy.horizonExit
                      : ANCHORS.strategy.ruleDeviation,
                )}
              >
                {/* **문장 전체를 링크로 감싸지 않는다** [2026-08-24]. 세 줄이
                    통째로 밑줄이라 링크 어포던스가 아니라 그냥 읽기 힘든 본문이
                    됐고, 어디를 눌러야 할지도 몰랐다. 문장은 문장으로 두고,
                    근거로 가는 문은 배지 줄 끝에 하나 단다. */}
                <Text as="p" font="body">
                  {r.text}
                </Text>
                <HStack gap={1} flexWrap="wrap" alignItems="baseline">
                  {r.badges.map((b) => (
                    <Text key={b} as="span" font="legal" color="fgMuted">
                      {b}
                    </Text>
                  ))}
                  <a href={RISK_HREF[r.key]} title={r.source}>
                    <Text as="span" font="legal">
                      근거
                    </Text>
                  </a>
                </HStack>
              </VStack>
            ))}
          </VStack>

          {/* 이 답이 0 으로 놓은 것 */}
          <VStack gap={0.5} {...anchorProps(ANCHORS.strategy.assumptions)}>
            <Text as="span" font="legal" color="fgMuted">
              이 답이 0 으로 놓은 것
            </Text>
            <Text as="p" font="body">
              {CONDITIONAL_NOTE}
            </Text>
            {/* 세 묶음이 **칸으로** 눕는다 [2026-08-24].
                예전에는 열두 줄이 전부 같은 회색 13px 로 이어져서 위계가 없는
                글벽이었다 — 「무엇이 bp 를 움직이나」 와 「그 출처가 무엇인가」 가
                한 줄에 섞여 있었다.
                Main/Backtest 의 하단 통계 스트립이 이 앱에서 쓰는 문법이다:
                구분선으로 나뉜 칸, 칸마다 굵은 라벨 + 작은 회색 키/값.
                출처는 **숨기지 않는다** — 근거가 보이는 것이 이 물건의 값이라,
                위계만 주고 자리는 지킨다. */}
            <HStack className="sr-assume" gap={0} width="100%" flexWrap="wrap">
              {groups.map((g) => (
                <VStack key={g.effect} className="sr-assume-col" gap={0.5}>
                  <Text as="p" font="label2">
                    {g.items.length === 0 && g.effect === 'delta' ? NO_DELTA_ITEMS : g.headline}
                  </Text>
                  {g.items.map((it) => (
                    <VStack key={it.key} gap={0}>
                      <Text as="p" font="legal">
                        {it.label} <b>{assumptionValue(it)}</b>
                      </Text>
                      <Text as="p" font="legal" color="fgMuted">
                        {it.source}
                        {it.as_of ? ` · ${it.as_of}` : ''}
                      </Text>
                    </VStack>
                  ))}
                </VStack>
              ))}
            </HStack>
            <Text as="p" font="legal" color="fgMuted">
              {stale.why}
            </Text>
          </VStack>
            </>
          ) : null}

          {/* 노트 내보내기 */}
          <VStack gap={0.5}>
            <HStack gap={1} alignItems="center">
              <Pressable
                as="button"
                noScaleOnPress
                accessibilityLabel="다섯 줄을 평문으로 복사해요"
                onClick={() => void onCopy()}
              >
                <Text as="span" font="label1">
                  노트 복사
                </Text>
              </Pressable>
              {copied ? (
                <Text as="span" font="legal" color="fgMuted" role="status">
                  {copied}
                </Text>
              ) : null}
            </HStack>
            <Box as="pre" className="sr-strat-export">
              <Text as="span" font="legal">
                {exportText}
              </Text>
            </Box>
            <Text as="p" font="legal" color="fgMuted">
              기저 {BASIS.as_of} · 점 {PINNED_Q}개 · 테너 {TENORS.length}개
            </Text>
          </VStack>
        </VStack>
      </VStack>
    </HStack>
  );
}
