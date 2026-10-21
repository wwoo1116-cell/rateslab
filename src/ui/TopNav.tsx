'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { ListCell } from '@coinbase/cds-web/cells';
import { Icon } from '@coinbase/cds-web/icons';
import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Pressable } from '@coinbase/cds-web/system';
import { TextBody, TextHeadline, TextLabel2 } from '@coinbase/cds-web/typography';

import { useScheme } from '@/app/providers';
import type { Group } from '@/table/rows';

import {
  BACKTEST_CATEGORIES,
  LAB_ITEMS,
  PANELED,
  STRATEGY_ITEMS,
  itemsOf,
  SECTIONS,
  sectionOf,
  tabForSection,
  type LabId,
  type SectionId,
  type StrategyId,
  type TabId,
} from './nav';

/**
 * 상단 내비 + 메가 패널, coinbase.com 의 그것 [OWNER 2026-08-13, 참조 이미지
 * `coinbase_tab.png`].
 *
 * 구조는 참조 그대로다: 왼쪽에 이름, 가운데 섹션 다섯, 오른쪽에 상태. 섹션 위에
 * 커서가 오면 아래로 전체 폭 패널이 열리고, 그 안은 «글리프 칩 + 제목 + 한 줄 설명»
 * 이 열을 이룬다.
 *
 * ── 모두 CDS 컴포넌트다 [OWNER 2026-08-13] ──────────────────────────────────
 * 첫 판은 `<button>`·`<div>`·`<span>` 으로 짰다. `cds.md` 의 첫 규칙이
 * "CDS 컴포넌트가 존재하면 항상 그것을 우선한다 — **네이티브 HTML 요소도 포함**"
 * 이므로 전부 옮겼다.
 *
 *   섹션 버튼   `<button>` → `Pressable`   누름 접근성을 CDS 가 준다
 *   메가 항목   `<button>` → `ListCell`    media+title+description 이 정확히 이 모양
 *   레이아웃    `<div>`    → `Box`/`HStack`/`VStack`
 *
 * `ListCell` 을 쓴 것이 가장 큰 이득이다. 참조의 항목은 «아이콘 칩 + 굵은 제목 +
 * 흐린 한 줄» 인데 그게 곧 ListCell 의 해부 구조(`media` / `title` / `description`)
 * 라서, 직접 짠 flex 세 겹이 통째로 사라진다. `spacingVariant="condensed"` 로
 * 메뉴 밀도에 맞춘다.
 *
 * ── 왜 hover 로 열고 click 으로도 여는가 ────────────────────────────────────
 * 참조는 hover 로 연다. 그런데 hover 만으로 여는 메뉴는 키보드와 터치에서 도달할 수
 * 없으므로, 같은 핸들러를 focus 와 click 에도 건다. click 은 **바로 이동**시키기도
 * 한다 — Backtest 를 누르면 마지막으로 보던 종목군으로 돌아가는 편이 빠르다.
 *
 * ── 닫힘 ────────────────────────────────────────────────────────────────────
 * Esc 한 번에 한 겹만 닫는다(v1 §a11y 의 규칙). 여기서는 겹이 하나뿐이라 Esc =
 * 패널 닫기다. 바깥 클릭도 닫는다.
 */
export function TopNav({
  tab,
  lab,
  strategy,
  lastGroup,
  onNavigate,
  right,
}: {
  tab: TabId;
  /** Lab 안에서 지금 보고 있는 세입자. Lab 이 아닐 때는 의미가 없다. */
  lab: LabId;
  /** Strategy 안에서 지금 보고 있는 세입자 — Lab 과 같은 기계다 [2026-08-25]. */
  strategy: StrategyId;
  lastGroup: Group;
  onNavigate: (t: TabId, lab?: LabId, strategy?: StrategyId) => void;
  /** 오른쪽에 서는 것 — 지금은 신선도 칩. 참조의 Sign in / Sign up 자리다. */
  right?: React.ReactNode;
}) {
  const { scheme, toggleScheme } = useScheme();
  const [open, setOpen] = useState<SectionId | null>(null);
  /* ── 어떻게 열렸는지를 기억한다 [디자인 감사 2026-10-21] ────────────────────
   *
   * 패널에 등장 모션을 거는데(`type.css` 의 `.sr-mega`), **키보드로 연 것에는
   * 걸면 안 된다.** 키보드 동작은 하루에 수백 번이라 모션이 붙으면 느리고
   * 동떨어진 느낌이 된다 — 모션 판정의 1번 기준(빈도)이 그것이다.
   *
   * CSS 만으로는 못 가른다: `@media (hover: hover)` 는 **장치**를 묻지
   * «이번에 무엇으로 열었나» 를 묻지 않는다. 그래서 여는 손이 직접 적는다. */
  const [openVia, setOpenVia] = useState<'pointer' | 'focus'>('pointer');
  const hostRef = useRef<HTMLElement | null>(null);
  const current = sectionOf(tab);

  const close = useCallback(() => setOpen(null), []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        close();
      }
    };
    const onDown = (e: MouseEvent) => {
      if (!hostRef.current?.contains(e.target as Node)) close();
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onDown);
    };
  }, [open, close]);

  const go = useCallback(
    (t: TabId, labId?: LabId, strategyId?: StrategyId) => {
      onNavigate(t, labId, strategyId);
      close();
    },
    [onNavigate, close],
  );

  const openSection = open ? SECTIONS.find((s) => s.id === open) : undefined;

  /** 메가 항목 하나. `ListCell` 의 해부가 참조의 항목과 같은 모양이라 그대로 쓴다. */
  const item = (
    key: string,
    glyph: string,
    label: string,
    desc: string,
    target: TabId,
    on: boolean,
    labId?: LabId,
    strategyId?: StrategyId,
  ) => (
    <ListCell
      key={key}
      spacingVariant="condensed"
      selected={on}
      disableSelectionAccessory
      media={
        <Box className="sr-megaglyph" aria-hidden="true">
          {glyph}
        </Box>
      }
      title={<TextHeadline as="span">{label}</TextHeadline>}
      description={
        <TextLabel2 as="span" color="fgMuted">
          {desc}
        </TextLabel2>
      }
      onClick={() => go(target, labId, strategyId)}
    />
  );

  return (
    <Box as="nav" ref={hostRef} className="sr-nav" onMouseLeave={close} aria-label="주요 화면">
      <HStack className="sr-navbar" alignItems="center" gap={3}>
        <TextHeadline as="span" noWrap>
          KRW Rates
        </TextHeadline>

        <HStack className="sr-navitems" alignItems="center" gap={0.5} flexGrow={1}>
          {/* 패널은 **PANELED 섹션에만** 열린다(처음엔 Backtest 뿐 [OWNER 승인
              2026-08-18 점검], Lab 2026-08-20 · Strategy 2026-08-25 합류).
              항목이 하나뿐인 섹션에서 hover 만으로 전 화면 스크림이 덮이는 것은
              목록 없는 메뉴를 여는 셈이다 — 목적지가 하나면 버튼이지 메뉴가
              아니다. hover 로 다른 섹션에 들어오면 열린 패널은 닫는다(안 닫으면
              이웃 위에 계속 떠 있다). */}
          {SECTIONS.map((s) => (
            <Pressable
              key={s.id}
              className="sr-navitem"
              data-on={s.id === current}
              data-open={s.id === open}
              aria-expanded={PANELED.includes(s.id) ? s.id === open : undefined}
              aria-current={s.id === current ? 'page' : undefined}
              accessibilityLabel={s.label}
              onMouseEnter={() => {
                setOpenVia('pointer');
                setOpen(PANELED.includes(s.id) ? s.id : null);
              }}
              onFocus={() => {
                setOpenVia('focus');
                setOpen(PANELED.includes(s.id) ? s.id : null);
              }}
              onClick={() => go(tabForSection(s.id, lastGroup))}
            >
              <TextHeadline as="span" noWrap>
                {s.label}
              </TextHeadline>
            </Pressable>
          ))}
        </HStack>

        <HStack className="sr-navright" alignItems="center" gap={1}>
          {right}
          {/* The scheme toggle. `providers.tsx` has had `toggleScheme` since the
              spike began and nothing ever called it — so the dark palette, the
              dark direction pair and the dark surface tokens were all
              unreachable from the running app. v1 puts this in its toolbar. */}
          {/* 아이콘 버튼이지 라벨이 아니다. 전에는 글리프 문자("☾")를 내비
              라벨과 같은 알약에 넣었는데, 문자의 시각 중심이 라틴 글자와 달라
              어긋나 보였고 크기도 폰트가 정했다. 토스는 이 자리에 32×32 아이콘
              버튼을 둔다(실측). CDS 에 `sun`/`moon` 아이콘이 있다. */}
          <Pressable
            className="sr-naviconbtn"
            accessibilityLabel={scheme === 'dark' ? '밝은 화면으로' : '어두운 화면으로'}
            onClick={toggleScheme}
          >
            <Icon name={scheme === 'dark' ? 'sun' : 'moon'} size="s" color="currentColor" />
          </Pressable>
        </HStack>
      </HStack>

      {openSection ? (
        <>
          {/* 뒤를 덮는다 — 이게 없으면 패널이 표 위에 뜬 낱글자로 읽힌다
              (Coinbase 실측: 바 아래 전체가 `rgba(50,53,61,0.33)`).

              스크림 자체가 "바깥"이다: 이 노드가 nav 의 자식이라 문서 레벨의
              바깥-클릭 감지가 닿지 않았고, 열린 메뉴는 Esc 로만 닫혔다(전체 앱
              크리틱 실측 2026-08-19). 덮는 막이 곧 닫기 표면이 되는 것이
              오버레이의 관례이기도 하다. aria-hidden 은 보조기술용 표기일 뿐
              포인터 이벤트와 무관하다. */}
          <Box className="sr-megascrim" aria-hidden="true" onClick={() => setOpen(null)} />
          <Box
            className="sr-mega"
            data-via={openVia}
            role="group"
            aria-label={`${openSection.label} 메뉴`}
          >
          <HStack className="sr-mega-inner" gap={4} alignItems="flex-start">
            {/* 여기는 이제 Backtest 뿐이다 — 1항목 섹션의 패널은 은퇴했다
                (위 섹션 버튼 주석). 항목 하나짜리 패널 렌더 분기도 함께 걷어냈다. */}
            <HStack className="sr-mega-cols" gap={4} flexWrap="wrap" flexGrow={1}>
              {open === 'lab' ? (
                /* 세입자 셋은 **위계가 같다** [OWNER, 2026-08-20] — 열 제목도
                   강조도 없이 한 줄로 선다. 그룹을 지으면 그 순간 어느 하나가
                   상위가 되고, 셋이 각자 졸업한다는 규칙과 어긋난다. */
                <VStack className="sr-mega-col" gap={0.25}>
                  {LAB_ITEMS.map((it) =>
                    item(
                      it.id,
                      it.glyph,
                      it.label,
                      it.desc,
                      'lab',
                      tab === 'lab' && it.id === lab,
                      it.id,
                    ),
                  )}
                </VStack>
              ) : open === 'strategy' ? (
                /* Strategy 세입자 — Lab 과 같은 기계, 같은 무위계 [2026-08-25]. */
                <VStack className="sr-mega-col" gap={0.25}>
                  {STRATEGY_ITEMS.map((it) =>
                    item(
                      it.id,
                      it.glyph,
                      it.label,
                      it.desc,
                      'strategy',
                      tab === 'strategy' && it.id === strategy,
                      undefined,
                      it.id,
                    ),
                  )}
                </VStack>
              ) : (
                BACKTEST_CATEGORIES.map((c) => (
                  <VStack key={c.id} className="sr-mega-col" gap={0.25}>
                    <TextLabel2 as="h3" color="fgMuted" className="sr-mega-coltitle">
                      {c.label}
                    </TextLabel2>
                    {itemsOf(c.id).map((it) =>
                      item(it.id, it.glyph, it.label, it.desc, it.id, it.id === tab),
                    )}
                  </VStack>
                ))
              )}
            </HStack>

            {/* 참조의 오른쪽 카드 자리. 그림 대신 이 섹션이 무엇인지 한 줄. */}
            <Box className="sr-mega-aside">
              <TextBody as="p">{openSection.blurb}</TextBody>
            </Box>
            </HStack>
          </Box>
        </>
      ) : null}
    </Box>
  );
}
