'use client';

/* 배선 그래프 — 이 숫자가 어디서 오는지의 지도.
 *
 * ## 그림이 아니라 **생성물**이다
 *
 * 노드도 엣지도 손으로 안 적었다. `backend/wiring/edges.py` 가
 * `bigfoot/solve/system.py` 의 solve 루프를 AST 로 읽고 계수를 수치미분해서
 * 낸다. 그래서 **빠진 배선이 빠진 화살표로 보인다** — 2026-08-21 감사가 잡은
 * eq 21(수입 수요에 건설·정부 누락)이 정확히 그 종류였다.
 *
 * ## 실선/점선이 논문의 설계를 말한다
 *
 * 장기(목표식·공적분)는 실선, 단기(PAC·오차수정)는 점선. 가계부채→소비가
 * 장기 음(eq 7)·단기 양(eq 8)으로 **같은 쌍에 두 화살표**가 서는 것이
 * FRB/US 계열 설계를 한 장에 담은 그림이다.
 *
 * ## 유령 화살표
 *
 * 논문이 인쇄했는데 배선이 없는 자리는 **흐린 파선**으로 선다. 없는 것을 안
 * 보이게 두면 «이게 논문에 충실한가» 에 답이 없다.
 *
 * ── 키보드 (CLAUDE.md «키보드와 접근성» 1·2·6·7) [고침 2026-10-19] ──────────
 * 그림은 **위젯 하나**다: 탭 정지 한 칸(`role="application"` · `tabIndex={0}` ·
 * `onKeyDown` · 「화살표가 무엇을 하는지」 적은 `aria-label`).
 *
 * 첫 판은 **노드 35개마다 `tabIndex={0}`** 이었다. 그건 이 그림 하나를 지나려면
 * 탭을 서른다섯 번 눌러야 한다는 뜻이고, 규칙 1 이 「노드 서른 개」를 예로 들어
 * 금지한 바로 그 꼴이다(터미널 표가 「탭 348번」으로 같은 것을 밟았다).
 *
 * ★그리고 더 조용한 결함이 하나 있었다: `<svg>` 가 **`role="img"`** 이었다.
 * 그 역할은 하위 트리를 보조기술에 **presentational 로 접어** 버리므로, 안에
 * 있던 버튼 서른다섯이 스크린리더에 **아예 안 보였다**. 탭 정지 서른다섯은
 * 눈에 띄는 고장이었고 이쪽은 안 띄는 고장이었다.
 *
 * 화살표는 **배치를 그대로 따른다** — 이 그래프는 층(layer)×줄(row) 격자다.
 * **←→ 는 층**(무엇이 무엇을 미는 방향), **↑↓ 는 같은 층 안의 줄**. 층을
 * 건널 때는 줄이 가장 가까운 노드로 간다. `Home`/`End` 는 처음·끝, `Enter`·
 * `Space` 는 고르기, `Esc` 는 놓기.
 *
 * **짚기와 고르기를 가른다**(규칙 2) — 짚은 노드는 `data-cursor`, 고른 노드는
 * `.sr-wire-picked` 다. 첫 판은 `:focus-visible` 과 `.sr-wire-picked` 가 **같은
 * 모양**(테두리 2px)이어서 둘을 구별할 수 없었다.
 *
 * 초점은 그림 하나에 머무르므로 **브라우저가 대신 스크롤해 주지 않는다** — 짚은
 * 노드를 가로 스크롤 상자 안으로 이 파일이 직접 들인다(오른쪽 48px 은 페이드가
 * 덮으므로 그만큼 더 민다).
 */

import { useCallback, useMemo, useRef, useState } from 'react';

import { Chip } from '@coinbase/cds-web/chips';
import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Text } from '@coinbase/cds-web/typography';

import { anchorProps, ANCHORS, eq as eqAnchor } from '../anchors';

import { Emph } from './emph';
import graphJson from './wiring_graph.json';
import {
  BLOCK_LABEL,
  CHANNELS,
  COL_GAP,
  layout,
  NODE_H,
  NODE_W,
  PRINTED_NOT_WIRED,
  reachable,
  type ChannelId,
  type Edge,
  type Graph,
  type Node,
  type Placed,
} from './layout';

const GRAPH = graphJson as unknown as Graph;

/** 부호 색.
 *
 * 처음엔 `+` 를 `--sr-up`(빨강)으로 두었는데, 엣지 90개 중 3분의 2가 `+` 라
 * **그림 전체가 빨개졌다**(실측 2026-08-21). 색이 다수를 칠하면 색이 아무것도
 * 말하지 않는다. 그래서 `+` 는 잉크로 두고 `−` 만 칠한다 — 눈에 띄어야 하는 것은
 * **부호가 뒤집히는 자리**이고, 가계부채→소비 같은 쌍도 그래야 한 눈에 보인다.
 *
 * 새 팔레트는 안 만든다. `--sr-down` 은 이 앱의 방향 토큰 그대로다. */
const SIGN_COLOR = { '+': 'var(--color-fg)', '-': 'var(--sr-down)' } as const;

/** 곡선 하나. 층을 건너뛰는 엣지가 노드를 관통하지 않게 살짝 휜다. */
function edgePath(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  backward: boolean,
): string {
  if (backward) {
    /* 되돌아가는 화살표는 **아래로 크게 돈다.** 앞으로 가는 선과 같은 통로에
       두면 두 방향이 구분이 안 된다 — 되먹임이 있다는 사실 자체가 이 모형의
       성질이라 눈에 띄어야 한다. */
    const dip = Math.max(28, Math.abs(x1 - x2) * 0.12);
    return `M ${x1} ${y1} C ${x1 - 24} ${y1 + dip}, ${x2 + 24} ${y2 + dip}, ${x2} ${y2}`;
  }
  const dx = Math.max(24, (x2 - x1) * 0.45);
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
}

type Sel = { node: Node; edges: Edge[] } | null;

export function WiringGraph() {
  const [channel, setChannel] = useState<ChannelId | null>(null);
  const [ghosts, setGhosts] = useState(true);
  const [picked, setPicked] = useState<string | null>(null);
  /** 짚은 노드. 고른 노드(`picked`)와 **다른 값**이다 — 훑어보는 동안 화면이
   *  안 바뀌어야 훑어볼 수 있다(규칙 2). */
  const [cursor, setCursor] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const L = useMemo(() => layout(GRAPH.nodes, GRAPH.edges), []);

  /** 층마다 줄 차례로 세운 격자 — 화살표가 걷는 길이다. */
  const grid = useMemo(() => {
    const m = new Map<number, Placed[]>();
    for (const n of L.nodes) {
      const row = m.get(n.layer);
      if (row) row.push(n);
      else m.set(n.layer, [n]);
    }
    for (const v of m.values()) v.sort((a, b) => a.row - b.row);
    return m;
  }, [L]);

  /** 탭 정지를 가질 **한 노드**. 커서가 없으면 고른 것, 그것도 없으면 첫 노드로
   *  떨어진다 — 「짚은 데가 없다」는 상태를 안 만든다. */
  const at = (cursor && L.byId[cursor]) || (picked && L.byId[picked]) || L.nodes[0] || null;

  const lit = useMemo(() => {
    if (!channel) return null;
    const c = CHANNELS.find((x) => x.id === channel);
    return c ? reachable(GRAPH.edges, c.seeds) : null;
  }, [channel]);

  const sel: Sel = useMemo(() => {
    if (!picked) return null;
    const node = GRAPH.nodes.find((n) => n.id === picked);
    if (!node) return null;
    return {
      node,
      edges: GRAPH.edges.filter((e) => e.to === picked || e.from === picked),
    };
  }, [picked]);

  /** 짚은 노드를 가로 스크롤 상자 **안으로** 들인다. 초점은 그림 하나에
   *  머무르므로 브라우저가 대신 해 주지 않는다. 오른쪽 48px 은 페이드(`.sr-wire-fade`)
   *  가 덮으니 그만큼 더 민다 — 안 그러면 짚은 노드가 흐린 띠 밑에 선다. */
  const reveal = useCallback((n: Placed) => {
    const box = scrollRef.current;
    if (!box) return;
    const FADE = 48;
    const left = n.x;
    const right = n.x + NODE_W;
    if (left < box.scrollLeft) box.scrollLeft = Math.max(0, left - COL_GAP);
    else if (right > box.scrollLeft + box.clientWidth - FADE) {
      box.scrollLeft = right + FADE + COL_GAP - box.clientWidth;
    }
  }, []);

  const go = useCallback(
    (n: Placed | undefined) => {
      if (!n) return;
      setCursor(n.id);
      reveal(n);
    },
    [reveal],
  );

  /** 화살표가 **배치를 따른다** — ←→ 는 층, ↑↓ 는 같은 층 안의 줄. 층을 건널
   *  때는 줄이 가장 가까운 노드로 간다(층마다 줄 수가 다르다). */
  const onKeyDown = useCallback(
    (ev: React.KeyboardEvent<SVGSVGElement>) => {
      if (!at) return;
      const col = grid.get(at.layer) ?? [];
      const i = col.findIndex((n) => n.id === at.id);
      const hop = (d: -1 | 1) => {
        const next = grid.get(at.layer + d);
        if (!next || next.length === 0) return undefined;
        return next.reduce((best, n) =>
          Math.abs(n.row - at.row) < Math.abs(best.row - at.row) ? n : best);
      };
      switch (ev.key) {
        case 'ArrowUp': ev.preventDefault(); return go(col[Math.max(0, i - 1)]);
        case 'ArrowDown': ev.preventDefault(); return go(col[Math.min(col.length - 1, i + 1)]);
        case 'ArrowLeft': ev.preventDefault(); return go(hop(-1));
        case 'ArrowRight': ev.preventDefault(); return go(hop(1));
        case 'Home': ev.preventDefault(); return go(L.nodes[0]);
        case 'End': ev.preventDefault(); return go(L.nodes[L.nodes.length - 1]);
        case 'Enter':
        case ' ':
          ev.preventDefault();
          setPicked((v) => (v === at.id ? null : at.id));
          return;
        case 'Escape':
          /* 놓는 것은 **고른 것**이지 짚은 자리가 아니다 — 짚은 자리까지 잃으면
             훑던 곳으로 돌아갈 길이 없다. */
          if (picked) { ev.preventDefault(); setPicked(null); }
          return;
        default:
          return;
      }
    },
    [at, grid, go, L.nodes, picked],
  );

  const on = (id: string) => !lit || lit.has(id);
  const label = (id: string) => GRAPH.nodes.find((n) => n.id === id)?.label ?? id;

  return (
    <VStack gap={1.5} width="100%" {...anchorProps(ANCHORS.model.wiring)}>
      <VStack gap={0.5}>
        <Text as="h3" font="label1">
          배선 — 무엇이 무엇을 미나
        </Text>
        <Text as="p" font="legal" color="fgMuted">
          손으로 그린 그림이 아니에요. 엔진의 풀이 루프를 읽어서 만들어요, 그래서{' '}
          <b>빠진 배선이 빠진 화살표로 보여요</b>. 노드를 누르면 그 변수로 오가는
          식과 계수가 열려요.
        </Text>
      </VStack>

      {/* ── 손잡이 ─────────────────────────────────────────────────────────── */}
      <HStack gap={1} flexWrap="wrap" alignItems="center">
        <Chip
          size="xs"
          className="sr-chip-toggle"
          aria-pressed={channel === null}
          onClick={() => setChannel(null)}
          accessibilityLabel="전달경로 필터 끄기"
        >
          전체
        </Chip>
        {CHANNELS.map((c) => (
          <span key={c.id} {...anchorProps(`model:channel:${c.id}`)}>
            <Chip
              size="xs"
              className="sr-chip-toggle"
              aria-pressed={channel === c.id}
              onClick={() => setChannel(channel === c.id ? null : c.id)}
              accessibilityLabel={`${c.label} 경로 — ${c.figure}`}
            >
              {c.label}
            </Chip>
          </span>
        ))}
        <Box flexGrow={1} />
        <Chip
          size="xs"
          className="sr-chip-toggle"
          aria-pressed={ghosts}
          onClick={() => setGhosts(!ghosts)}
          accessibilityLabel="논문에는 있고 배선에 없는 화살표 보이기"
        >
          논문에만 있는 것 {PRINTED_NOT_WIRED.length}
        </Chip>
      </HStack>

      {channel ? (
        <Text as="p" font="legal" color="fgMuted">
          <b>{CHANNELS.find((c) => c.id === channel)?.figure}</b> ·{' '}
          {CHANNELS.find((c) => c.id === channel)?.blurb}
        </Text>
      ) : null}

      {/* ── 그림 ───────────────────────────────────────────────────────────── */}
      {/* 가로만 흐른다. 세로로 흐르게 두면 카드가 페이지를 밀고, 이 앱은 페이지가
          안 흐른다는 전제 위에 서 있다.

          오른쪽 가장자리의 페이드는 **잘렸다는 표시**다 [2026-08-24]. 그림이
          2,302px 이고 상자는 1,851px 이라 늘 잘리는데, 노드가 끝에서 딱 끊기면
          그림이 거기서 끝난 것처럼 보였다. 스크롤이 되는 것과 스크롤할 게
          있다고 말하는 것은 다른 일이다. */}
      <Box className="sr-wire-scroll" width="100%" ref={scrollRef}>
        <span className="sr-wire-fade" aria-hidden="true" />
        <svg
          className="sr-wire-svg"
          width={L.width}
          height={L.height}
          viewBox={`0 0 ${L.width} ${L.height}`}
          /* ★`role="img"` 이 아니다. 그 역할은 하위 트리를 보조기술에
             presentational 로 접어서 **안의 노드 서른다섯을 통째로 감춘다**
             (실측 2026-10-19). 이 그림은 읽는 그림이 아니라 **조작하는 위젯**이다. */
          role="application"
          tabIndex={0}
          onKeyDown={onKeyDown}
          /* 라벨이 **화살표가 무엇을 하는지**를 적는다 — 규칙을 안 적으면 눌러 볼
             이유가 없다(캐논의 다른 그림 축들이 같은 문장을 든다). */
          aria-label={
            `배선 그래프 — 좌우 화살표로 층을, 위아래 화살표로 같은 층의 줄을 `
            + `짚습니다. Enter 로 고르고 Esc 로 놓습니다. `
            + `노드 ${GRAPH.nodes.length}개, 화살표 ${GRAPH.edges.length}개. `
            + `해외 블록으로 들어가는 화살표는 0개예요`
          }
        >
          <defs>
            <marker
              id="sr-wire-tip-up"
              viewBox="0 0 8 8"
              refX="7"
              refY="4"
              markerWidth="5"
              markerHeight="5"
              orient="auto-start-reverse"
            >
              <path d="M0,0 L8,4 L0,8 z" fill="var(--color-fg)" />
            </marker>
            <marker
              id="sr-wire-tip-down"
              viewBox="0 0 8 8"
              refX="7"
              refY="4"
              markerWidth="5"
              markerHeight="5"
              orient="auto-start-reverse"
            >
              <path d="M0,0 L8,4 L0,8 z" fill="var(--sr-down)" />
            </marker>
          </defs>

          {/* 유령이 먼저 — 실제 배선 아래에 깔린다. */}
          {ghosts
            ? PRINTED_NOT_WIRED.map((g) => {
                const a = L.byId[g.from];
                const b = L.byId[g.to];
                if (!a || !b) return null;
                return (
                  <path
                    key={`ghost-${g.from}-${g.to}-${g.equation}`}
                    className="sr-wire-ghost"
                    d={edgePath(
                      a.x + NODE_W,
                      a.y + NODE_H / 2,
                      b.x,
                      b.y + NODE_H / 2,
                      b.layer <= a.layer,
                    )}
                  />
                );
              })
            : null}

          {GRAPH.edges.map((e) => {
            const a = L.byId[e.from];
            const b = L.byId[e.to];
            if (!a || !b) return null;
            const active = on(e.from) && on(e.to);
            const touched = picked === e.from || picked === e.to;
            const backward = b.layer <= a.layer;
            return (
              <path
                key={`${e.from}-${e.to}-${e.horizon}`}
                className={`sr-wire-edge${active ? '' : ' sr-wire-dim'}${
                  touched ? ' sr-wire-hot' : ''
                }`}
                data-horizon={e.horizon}
                d={edgePath(
                  a.x + NODE_W,
                  a.y + NODE_H / 2,
                  b.x,
                  b.y + NODE_H / 2,
                  backward,
                )}
                stroke={SIGN_COLOR[e.sign]}
                markerEnd={`url(#sr-wire-tip-${e.sign === '+' ? 'up' : 'down'})`}
              />
            );
          })}

          {L.nodes.map((n) => (
            <g
              key={n.id}
              className={`sr-wire-node${on(n.id) ? '' : ' sr-wire-dim'}${
                picked === n.id ? ' sr-wire-picked' : ''
              }`}
              data-block={n.block}
              /* ★짚은 자리는 **고른 자리와 다른 표시**다(규칙 2). 첫 판은
                 `:focus-visible` 과 `.sr-wire-picked` 가 같은 테두리여서 둘을
                 구별할 수 없었다. */
              data-cursor={at?.id === n.id || undefined}
              transform={`translate(${n.x},${n.y})`}
              role="button"
              /* 탭 정지를 **안 둔다** — 그림 전체가 한 칸이고 안에서는 화살표다.
                 여기 `tabIndex={0}` 을 두면 이 그림 하나가 탭 서른다섯 번이 된다. */
              aria-label={`${n.label}. ${BLOCK_LABEL[n.block]} 블록.`}
              aria-pressed={picked === n.id}
              onClick={() => { setCursor(n.id); setPicked(picked === n.id ? null : n.id); }}
            >
              <rect width={NODE_W} height={NODE_H} rx={6} />
              <text x={NODE_W / 2} y={NODE_H / 2 + 4} textAnchor="middle">
                {n.label}
              </text>
            </g>
          ))}
        </svg>
        {/* 규칙 7 — SVG 안의 변화는 소리가 안 난다. **키보드가 짚은 것만** 읽는다
            (마우스가 스치는 것까지 읽으면 문장이 끊이지 않는다). */}
        <span className="sr-a11y-only" aria-live="polite">
          {at ? `${at.label}. ${BLOCK_LABEL[at.block]} 블록.${picked === at.id ? ' 고름.' : ''}` : ''}
        </span>
      </Box>

      {/* ── 범례 ───────────────────────────────────────────────────────────── */}
      <HStack gap={2} flexWrap="wrap" alignItems="center">
        <HStack gap={0.75} alignItems="center">
          <span className="sr-wire-key" data-kind="lr" aria-hidden />
          <Text as="span" font="legal" color="fgMuted" noWrap>
            장기 (목표식)
          </Text>
        </HStack>
        <HStack gap={0.75} alignItems="center">
          <span className="sr-wire-key" data-kind="sr" aria-hidden />
          <Text as="span" font="legal" color="fgMuted" noWrap>
            단기 (PAC·오차수정)
          </Text>
        </HStack>
        <HStack gap={0.75} alignItems="center">
          <span className="sr-wire-key" data-kind="plus" aria-hidden />
          <Text as="span" font="legal" color="fgMuted" noWrap>
            같은 방향 +
          </Text>
        </HStack>
        <HStack gap={0.75} alignItems="center">
          <span className="sr-wire-key" data-kind="minus" aria-hidden />
          <Text as="span" font="legal" color="fgMuted" noWrap>
            반대 방향 −
          </Text>
        </HStack>
        <HStack gap={0.75} alignItems="center">
          <span className="sr-wire-key" data-kind="ghost" aria-hidden />
          <Text as="span" font="legal" color="fgMuted" noWrap>
            논문에만 있는 것
          </Text>
        </HStack>
      </HStack>

      {/* ── 블록외생: 이건 렌더링 사고가 아니라 모형의 성질이다 ─────────────── */}
      <Text as="p" font="legal" color="fgMuted">
        <b>해외 블록으로 들어가는 화살표는 0개예요.</b> 해외 여건과 유가는 한국에
        일방으로 작용하고, 한국은 되먹이지 않아요 — 그림이 그렇게 생긴 게 아니라
        모형이 그래요. 이 0 은 시험으로 잠가 뒀어요.
      </Text>

      {/* ── 고른 노드 ──────────────────────────────────────────────────────── */}
      {sel ? (
        <VStack gap={1} className="sr-wire-detail" padding={1.5}>
          <HStack gap={1} alignItems="baseline" flexWrap="wrap">
            <Text as="h4" font="label1" noWrap>
              {sel.node.label}
            </Text>
            <Text as="span" font="legal" color="fgMuted" noWrap>
              {BLOCK_LABEL[sel.node.block]} 블록 · {sel.node.id}
            </Text>
          </HStack>
          <VStack gap={0.5} width="100%">
            {sel.edges.map((e) => (
              <HStack
                key={`${e.from}-${e.to}-${e.horizon}`}
                gap={1}
                alignItems="baseline"
                flexWrap="wrap"
              >
                <Text as="span" font="legal" noWrap>
                  <span className={e.sign === '+' ? 'sr-up' : 'sr-down'}>
                    {e.sign}
                  </span>{' '}
                  {label(e.from)} → {label(e.to)}
                </Text>
                <Text as="span" font="legal" color="fgMuted" noWrap>
                  {e.horizon === 'LR' ? '장기' : '단기'} ·{' '}
                  <a href={`#${eqAnchor(e.equation)}`}>
                    {e.equation === '항등식' ? '항등식' : `식 (${e.equation})`}
                  </a>
                  {e.paper_page ? ` · 논문 ${e.paper_page}` : ''}
                </Text>
                {e.coefficient_slot ? (
                  <Text as="span" font="legal" color="fgMuted" noWrap>
                    {e.coefficient_slot}
                  </Text>
                ) : null}
                {e.via ? (
                  <Text as="span" font="legal" color="fgMuted">
                    <Emph t={e.via} />
                  </Text>
                ) : null}
              </HStack>
            ))}
            {PRINTED_NOT_WIRED.filter(
              (g) => g.from === sel.node.id || g.to === sel.node.id,
            ).map((g) => (
              <Text
                key={`g-${g.from}-${g.to}-${g.equation}`}
                as="p"
                font="legal"
                color="fgMuted"
              >
                <b>
                  논문에만: {label(g.from)} → {label(g.to)} (식 ({g.equation})
                  {g.paper_page ? `, ${g.paper_page}` : ''})
                </b>{' '}
                <Emph t={g.why} />
              </Text>
            ))}
          </VStack>
        </VStack>
      ) : null}

      {/* ── 생성기가 못 잡은 것 ────────────────────────────────────────────── */}
      <VStack gap={0.5}>
        <Text as="p" font="legal" color="fgMuted">
          접은 것: {GRAPH.flow_merges.map((m) => `${m.folded}→${m.into}`).join(' · ')}{' '}
          — 수준과 그 증분은 같은 변수라 한 노드로 둬요.
        </Text>
        {GRAPH.uncovered.map((u) => (
          <Text key={u.var} as="p" font="legal" color="fgMuted">
            <b><Emph t={u.var} /></b> — <Emph t={u.why} />
          </Text>
        ))}
        {/* 아래 셋은 **비어 있을 때도 말한다.** 생성기가 못 푼 식이 없다는 것과
            그걸 안 세어 봤다는 것은 다른 사실인데, 빈 배열을 `map` 만 하면 화면은
            둘을 똑같이 «아무것도 없음» 으로 보여 준다. 지금은 셋 다 깨끗해서
            더 그렇다 — 깨끗하다고 말할 자리가 있어야 더러워졌을 때 보인다. */}
        <Text as="p" font="legal" color="fgMuted">
          못 푼 식:{' '}
          {GRAPH.unsupported_expressions.length === 0
            ? '없어요 — 스캔한 대입문을 전부 미분했어요.'
            : GRAPH.unsupported_expressions.join(' · ')}
        </Text>
        <Text as="p" font="legal" color="fgMuted">
          이름 못 붙인 노드:{' '}
          {GRAPH.missing_labels.length === 0
            ? '없어요.'
            : GRAPH.missing_labels.join(' · ')}
        </Text>
        <Text as="p" font="legal" color="fgMuted">
          논문에 안 인쇄된 식:{' '}
          {Object.entries(GRAPH.non_paper_equations).length === 0
            ? '없어요.'
            : Object.entries(GRAPH.non_paper_equations)
                .map(([k, v]) => `${k}(${v})`)
                .join(' · ')}
          {' '}— 그래프에는 서지만 논문 쪽수를 못 달아요.
        </Text>
        <Text as="p" font="legal" color="fgMuted">
          출처: <Emph t={GRAPH.generated_from} />
        </Text>
      </VStack>
    </VStack>
  );
}
