'use client';

/* 「모형」 탭 — 예상 커브 하나.
 *
 * ── 표준은 백테스트의 종목 차트다 [OWNER, 2026-08-20] ───────────────────────
 * "백테스트 들어가서 아웃라이트에서 9m 그래프 어떻게 생겼는지라도 한 번
 * 보고오셈, 이게 표준이야". 실제로 열어서 재고 그 해부를 그대로 옮겼다
 * (`ui/PreviewPane.tsx`):
 *
 *     머리      작은 muted 이름, 오른쪽에 칩/메타
 *     히어로    **거대한 숫자**(display3) + 작은 단위 + 방향 화살표와 변화
 *     차트      주선에 `showArea areaType="dotted"` 면 채움
 *               참조선은 굵기·불투명도가 주선과 같고 **다른 것은 색 하나**
 *               (`--sr-ref-cd` 호박 / `--sr-ref-policy` 보라 — direction.css)
 *               눈금 라벨은 `opacity 0.65` 로 물러남
 *               `Scrubber` 는 짚을 시리즈를 **명시**한다(기본은 전부라 유령 구슬)
 *     리드아웃  그림 **위** 한 줄(`ChartReadoutStrip`) — 견본 + 이름 + 값이 한 칸
 *               [2026-09-21] 종전에는 떠 있는 카드(값)와 바닥 범례(`RefKey`,
 *               견본+이름)로 **둘로 나뉘어** 있었다. 한 칸에 모으면 「그려진
 *               것」과 「그 값」이 갈릴 수가 없다
 *     통계      차트 아래 `.sr-stats` 세 칸, 사이는 여백이 아니라 **헤어라인**
 *
 * 앞선 두 판이 «메인/백테스트랑 그래프는 커녕 디자인 문법조차 안 맞는다» 는
 * 지적을 받은 이유가 정확히 이 목록이었다: 히어로도 면 채움도 색도 통계 블록도
 * 없었고, 머리가 두 층이라 as-of 가 두 번 찍혔고, 범례를 «┈ ── ━» 유니코드로
 * 그렸다.
 *
 * ── 선 셋 ──────────────────────────────────────────────────────────────────
 *     모형 12M   오늘 + 모형 Δ — 이 경로가 맞다면        잉크, 면 채움
 *     시장 12M   오늘 + 시장 캐리 — 이미 프라이싱된 것    호박
 *     오늘       오늘의 스팟 IRS 호가                     보라
 *
 * 앞 둘의 간격이 트레이드고, 히어로가 그 값을 진다.
 */

import { useCallback, useMemo, useState } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Text } from '@coinbase/cds-web/typography';

/* 스트립 문법은 **한 벌**이다 — `src/ui/Stat.tsx` 로 옮겼다.
   「모형」 레인이 같은 것을 다시 만들려던 참이었고, 두 벌이 되면 한쪽만
   낡는다. 모양은 한 글자도 안 바뀌었다. */
import { Stat, StatColumn } from '@/ui/Stat';

import { CurveChart, type CurveLine } from '@/chart/CurveChart';
import { ChartReadoutStrip, slotChars, type StripSlot } from '@/ui/ChartReadoutStrip';

import type { ScenarioRow } from './assemble';

const MODEL = 'MODEL';
const MARKET = 'MARKET';
const TODAY = 'TODAY';

const TENOR_LABEL: Record<string, string> = {
  '1y': '1Y',
  '2y': '2Y',
  '3y': '3Y',
  '5y': '5Y',
  '10y': '10Y',
};

/** 히어로가 서는 테너. 결과 탭의 헤드라인과 같은 자리여야 한다. */
const HEADLINE = '3y';

const lvl = (v: number | null | undefined) => (v == null ? '—' : v.toFixed(4));
const bp = (v: number | null | undefined) =>
  v == null ? '—' : `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}`;

export function ModelChart({ rows, asof }: { rows: ScenarioRow[]; asof: string }) {
  const [hoverIdx, setHoverIdx] = useState<number | undefined>(undefined);

  const onLeave = useCallback(() => setHoverIdx(undefined), []);

  const s = useMemo(
    () => ({
      today: rows.map((r) => r.spot),
      /* 캐리가 없는 테너에서 시장 선은 **끊긴다**. 스팟으로 메우면 «시장은 10년이
         안 움직인다고 본다» 는 없는 사실이 그려진다 — 빈칸은 0 이 아니다. */
      market: rows.map((r) => r.market12m),
      model: rows.map((r) => r.scenario12m),
      labels: rows.map((r) => TENOR_LABEL[r.tenor] ?? r.tenor),
    }),
    [rows],
  );

  const hasMarket = s.market.some((v) => v != null);

  /* 선 셋. **먼저 선언한 것이 아래에 깔린다** — 잉크(모형)가 맨 위여야 한다.
     참조선 둘은 똑같이 그려진다(같은 굵기·불투명도, 다른 것은 색 하나). */
  const lines = useMemo<CurveLine[]>(
    () => [
      { id: TODAY, values: s.today, color: (p) => p.refPolicy, width: 1 },
      ...(hasMarket
        ? [{ id: MARKET, values: s.market, color: (p: { refCd: string }) => p.refCd, width: 1 as const }]
        : []),
      { id: MODEL, values: s.model, color: (p) => p.fg, area: 'dots' },
    ],
    [s, hasMarket],
  );

  const setHover = useCallback((i: number | null) => setHoverIdx(i ?? undefined), []);
  const rateTick = useCallback((v: number) => Number(v).toFixed(2), []);
  const nodeLabel = useCallback(
    (i: number) => {
      const r = rows[i];
      if (!r) return '';
      return (
        `${TENOR_LABEL[r.tenor] ?? r.tenor} 모형 ${lvl(r.scenario12m)}%` +
        (r.vsMarketBp == null ? ', 시장 캐리 없음' : `, 시장 대비 ${bp(r.vsMarketBp)}bp`)
      );
    },
    [rows],
  );
  const head = rows.find((r) => r.tenor === HEADLINE) ?? rows[0];
  const dir = head?.vsMarketBp == null ? 'flat' : head.vsMarketBp > 0 ? 'up' : head.vsMarketBp < 0 ? 'down' : 'flat';

  const idx = hoverIdx != null && hoverIdx >= 0 && hoverIdx < rows.length ? hoverIdx : null;
  /* 커서가 그림 밖이면 **맨 오른쪽 노드**를 읽는다 — 커브에는 「마지막 날」이
     없고 「가장 긴 만기」가 그 자리다(`ChartReadoutStrip` 머리의 그 규칙). */
  const at = idx ?? rows.length - 1;
  const hit = rows[at] ?? null;

  /** 리드아웃 칸 — **그려진 선 셋 그대로**다(견본 색·잉크가 그 선의 것).
   *
   *  「시장 캐리」는 선이 아니라 수라 견본이 없다. 좁아지면 캐리 → 오늘 → 시장
   *  순으로 값을 내려놓고 모형은 안 내려놓는다 — 이 화면의 주인공이다. */
  const slots: StripSlot[] = (() => {
    const lvlOf = (v: number | null | undefined) => (v == null ? '—' : `${lvl(v)}%`);
    const ch = slotChars(
      (v) => `${lvl(v)}%`,
      ...s.model, ...s.market, ...s.today,
    );
    const out: StripSlot[] = [
      { key: 'model', label: '모형 12M', value: lvlOf(hit?.scenario12m),
        color: 'var(--color-fg)', chars: ch },
    ];
    if (hasMarket) {
      out.push({ key: 'market', label: '시장 12M', value: lvlOf(hit?.market12m),
        color: 'var(--sr-ref-cd)', opacity: 0.9, chars: ch, drop: 2 });
    }
    out.push({ key: 'today', label: `오늘 ${asof}`, value: lvlOf(hit?.spot),
      color: 'var(--sr-ref-policy)', opacity: 0.9, chars: ch, drop: 3 });
    out.push({ key: 'carry', label: '시장 캐리',
      value: hit?.marketCarryBp == null ? '—' : `${hit.marketCarryBp.toFixed(1)}bp`,
      drop: 1 });
    return out;
  })();

  if (!head) return null;

  return (
    <VStack gap={0} width="100%" flexGrow={1} minHeight={0}>
      {/* ── 머리 + 히어로 ─────────────────────────────────────────────────
          백테스트가 «9M» 을 작게 얹고 그 아래 3.2850 을 크게 세우는 그 자리다.
          이름 옆의 오른쪽 자리는 카드 머리(탭·as-of)가 이미 지므로 비운다. */}
      <VStack gap={1.5} paddingX={2} paddingTop={2} paddingBottom={1.5}>
        <Text as="h3" font="label1" color="fgMuted" noWrap>
          12개월 뒤 IRS 커브
        </Text>
        <HStack gap={1.5} alignItems="baseline" flexWrap="wrap">
          <Text as="span" font="display3" tabularNumbers noWrap>
            {lvl(head.scenario12m)}
            <Box as="span" className="sr-hero-unit">
              %
            </Box>
          </Text>
          <Text
            as="span"
            font="body"
            tabularNumbers
            noWrap
            className={dir === 'up' ? 'sr-up' : dir === 'down' ? 'sr-down' : 'sr-flat'}
          >
            {dir === 'up' ? '↗' : dir === 'down' ? '↘' : '→'} {bp(head.vsMarketBp)}bp{' '}
            <Box as="span" className="sr-hero-span">
              {TENOR_LABEL[head.tenor]} · 시장 대비
            </Box>
          </Text>
        </HStack>
      </VStack>

      {/* ── 차트 ──────────────────────────────────────────────────────────
          `flexBasis={0}` 이 없으면 상자가 자기 내용에서 높이를 얻으려 하고,
          내용은 상자에서 높이를 얻으려 해서 되먹임이 생긴다. */}
      {/* 커서 밑의 값 — **그림 위 한 줄**이다 [2026-09-21 이관]. 아래에 따로
          있던 범례(`RefKey` 셋)도 이 줄이 흡수했다: 견본·이름·값이 한 자리에
          서면 「그려진 것」과 「그 값」이 갈릴 수가 없다(그 줄이 존재하던 이유가
          그것이었고, 정작 «값»은 거기 없었다). */}
      <ChartReadoutStrip
        date={TENOR_LABEL[hit?.tenor ?? ''] ?? hit?.tenor ?? ''}
        slots={slots}
        change={hit?.vsMarketBp == null ? undefined : {
          label: '차이',
          text: `${Math.abs(hit.vsMarketBp).toFixed(1)}bp`,
          v: hit.vsMarketBp,
        }}
      />
      <Box
        className="sr-plot"
        paddingX={1}
        flexGrow={1}
        flexBasis={0}
        minHeight={0}
        onMouseLeave={onLeave}
      >
        <CurveChart
          accessibilityLabel={`12개월 뒤 IRS 커브. ${rows.map((_, i) => nodeLabel(i)).join('. ')}`}
          nodes={s.labels}
          lines={lines}
          precision={4}
          tickFormat={rateTick}
          onHoverIndex={setHover}
          hoverLabel={nodeLabel}
        />

      </Box>

      {/* ── 통계 셋 ───────────────────────────────────────────────────────
          사이가 여백이 아니라 헤어라인이라 세 목록이 **한 덩어리**로 읽힌다. */}
      <HStack className="sr-stats" flexWrap="wrap">
        <StatColumn title="오늘">
          {rows.map((r) => (
            <Stat key={r.tenor} label={TENOR_LABEL[r.tenor]} value={`${lvl(r.spot)}%`} />
          ))}
        </StatColumn>
        <StatColumn title="모형 12M">
          {rows.map((r) => (
            <Stat key={r.tenor} label={TENOR_LABEL[r.tenor]} value={`${lvl(r.scenario12m)}%`} />
          ))}
        </StatColumn>
        <StatColumn title="시장 대비">
          {rows.map((r) => (
            <Stat
              key={r.tenor}
              label={TENOR_LABEL[r.tenor]}
              value={`${bp(r.vsMarketBp)}${r.vsMarketBp == null ? '' : 'bp'}`}
              tone={r.vsMarketBp == null ? undefined : r.vsMarketBp > 0 ? 'up' : 'down'}
            />
          ))}
        </StatColumn>
      </HStack>
    </VStack>
  );
}

