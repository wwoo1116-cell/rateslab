'use client';

/* 크레딧 RV (DTS) — Lab 의 다섯째 세입자 [OWNER 2026-10-02].
 *
 * [OWNER] 「정규화 할 때 그 리스크팩터를 DTS 로 두면 어떻게 돼?」 →
 *         「**좁은 게 싸 보인다** > 이거 내가 원하는 방향성 맞는데?」 →
 *         「이러면 전부 다 스프레드를 **KTB 대비**로 할 수 있어」 → 「통안은 뺀다」 →
 *         「**DTS version 을 하나 Lab 에다가 만드는 게 낫겠는데?**」
 *
 * ── 이 화면이 답하는 질문 ───────────────────────────────────────────────────
 * **「같은 만기 안에서, 제 평소보다 벌어진 칸은 어디인가」.** 제품 Credit RV 의
 * Score 는 같은 만기 안에서 레벨 누출이 **+0.418** 이라(= 「넓은 등급을 사라」),
 * 분모를 σ 대신 **지금 스프레드**로 두면 **+0.076** 으로 죽는다. 표본밖에서도
 * 이긴다(근거 전부 `backend/app/creditdts.py` 머리 · `research/credit-rv-dts`).
 *
 * ── ★왜 제품을 안 고치고 Lab 인가 ───────────────────────────────────────────
 * 내가 제품 Score 를 갈아 끼우자고 했고 **오너가 Lab 으로 돌렸다. 그게 맞다** —
 * 제품 Score 는 트레이더 설계안(2026-08-18)이고 이 축은 표본밖을 **한 바퀴** 돈
 * 것뿐이다. 둘을 나란히 두고 기록이 쌓이면 그때 승격을 묻는다(실시간 IRS 와 같은
 * 자세). 그래서 `rv.py` 는 **한 줄도 안 건드렸다**.
 *
 * ── ★★사분면을 고쳤다 ──────────────────────────────────────────────────────
 * [OWNER] 「기존 사분면은 반영을 제대로 못 하고 있었어서 … 지금 이 사분면을 제대로
 * 고칠 수 있으면 그게 더 나을듯」
 *
 * 제품 사분면은 x=월환산 총수익 · y=지난주 백분위인데, **Score 의 입력은 그 둘이
 * 아니다**(`spreadVolPct` × `relRv`). 그래서 그림과 순위가 따로 놀았다. 여기서는
 * **세로 위치가 곧 순위**이고(y = z = 점수 그 자체), 가로는 **점수에서 일부러 뺀
 * 것**(x = 지금 스프레드 수준 = 캐리의 대리)이다.
 *
 *     ↖ 좁은데 싸다 = **순수 RV**(이 화면이 찾는 것)   ↗ 넓고 싸다
 *     ↙ 좁고 비싸다                                  ↘ 넓은데 비싸다 = **캐리만**
 *
 * 축 선택이 이 레인의 본체라 **산술은 `quadrant.ts` 에 순수 함수로 떼어 두었다** —
 * 렌더해야 재는 축 계약은 조용히 뒤집힌다. `guards/lab-credit-dts.test.ts` 가 잠근다.
 *
 * ── 캐논에서 가져온 것 (CLAUDE.md «화면 문법의 캐논») ───────────────────────
 * · 커서 리드아웃 = **그림 밖 한 줄** `ChartReadoutStrip` — 네이티브 `<title>`
 *   툴팁으로 첫 판을 지었는데 그건 **마우스 전용**이라 아래 키보드 규칙에
 *   걸리고, 떠 있는 `ReadoutCard` 는 새 표면에 쓰지 말라고 캐논에 박혀 있다.
 * · 레벨 값 = `fmtLevel(v, 'bp')` · z 표기 = `fmtDelta(z, 'ratio')`(무차원 비율).
 *   손으로 `toFixed` 를 적었다가 음수가 **ASCII 하이픈**으로 나왔다 — 이 제품의
 *   음수는 U+2212 이고 그 규약은 `lib/format` 한 곳에만 있어야 한다.
 * · 역방향 연동 = `.sr-rv-row[data-on]` — 점을 짚으면 표의 그 행이 같은 채움으로
 *   강조된다(이 클래스가 이미 그 일을 하라고 적혀 있었다).
 * · 표는 **조밀 문법**(`.sr-rv-table`) — 120행이면 캐논의 CDS `Table`(ROW_H 60)로는
 *   7,200px 이라 한 화면에 안 선다(실시간 IRS 가 같은 판단을 했다).
 *
 * ── 키보드 (CLAUDE.md «키보드와 접근성» 1·6·7) ──────────────────────────────
 * 그림은 **위젯 하나**다: 탭 정지 한 칸(`role="application"` · `tabIndex={0}` ·
 * `onKeyDown` · 「화살표가 무엇을 하는지」 적은 `aria-label`). 화살표가 두 축을
 * 따로 돈다 — **↑↓ 는 순위(=z=세로)**, **←→ 는 스프레드 폭(=가로)**. 축이 둘인
 * 그림이라 키도 둘이어야 하고, 그게 축 설계를 손가락으로 가르친다.
 *
 * 확대 키(`+`·`−`·`0`)는 **안 둔다** — 이 그림은 확대가 없다. 안 되는 키를 듣는
 * 척하면 라벨이 거짓말을 한다(캐논의 「확대 키는 축마다 같다」는 확대가 있는 축들
 * 사이의 규칙이다).
 *
 * **고르기가 없고 짚기만 있다**: 짚은 점이 표의 행을 강조하는 것이 이 화면의
 * 전부이고, 눌러서 바뀌는 상태가 없다. 그래서 `data-cursor`/`data-on` 두 표시를
 * 가르지 않는다(가르면 둘 중 하나가 아무 뜻도 없는 표시가 된다).
 *
 * ⚠ **느린 회전에서만 산다**: 손익분기 왕복비용이 21일 0.63bp · 63일 0.99bp ·
 *   126일 1.63bp 다. 이 리포 가정(1bp 왕복)에서 21일 회전은 죽는다. 화면이 적는다.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Text } from '@coinbase/cds-web/typography';

import { BacktestUnavailable } from '@/lib/api';
import { fmtDelta, fmtLevel } from '@/lib/format';
import { tintFor } from '@/theme/tint';
import { ChartReadoutStrip, slotChars } from '@/ui/ChartReadoutStrip';
import { ErrorState, LoadingState } from '@/ui/DataState';
import { useMeasure } from '@/ui/useMeasure';

import { fetchCreditDts, type CreditDts, type CreditDtsItem } from './api';
import { PAD, quadrantCounts, quadrantGeometry, spearman, xScaleNote } from './quadrant';

/** 측정 전 첫 프레임의 크기. `useMeasure` 가 0 을 주는 그 한 프레임에 좌표를
 *  0 으로 접으면 점이 모두 왼쪽 위에 모였다가 튀어나온다. */
const FALLBACK = { w: 520, h: 360 } as const;

/** 눌리는 것의 판정 반지름 — 지름 24px (WCAG 2.2 §2.5.8). 점은 3.5px 그대로다. */
const HIT_R = 12;

/** 레벨 표기는 캐논 하나다 — bp 1자리. */
const bp = (v: number) => fmtLevel(v, 'bp');

/** 사분면 — 실측 크기로 그린다(손 차트들의 그 관용구: 고정 viewBox 는 여백을 만든다). */
function Quadrant({ items, hover, onHover }: {
  items: CreditDtsItem[];
  hover: string | null;
  onHover: (id: string | null) => void;
}) {
  const [ref, mw, mh] = useMeasure<HTMLDivElement>();
  const w = mw || FALLBACK.w;
  const h = mh || FALLBACK.h;
  const geo = useMemo(() => quadrantGeometry(items, w, h), [items, w, h]);
  const counts = useMemo(() => quadrantCounts(items), [items]);

  /* 화살표가 도는 두 순서. **축마다 하나**다 — 한 순서로 네 방향을 처리하면
     ←→ 가 세로로 튀고, 그 순간 그림이 가르치려던 축 설계가 거짓이 된다. */
  const byRank = useMemo(
    () => [...items].sort((a, b) => a.rank - b.rank).map((i) => i.seriesId),
    [items],
  );
  const byWidth = useMemo(
    () => [...items]
      .sort((a, b) => a.nowBp - b.nowBp || a.seriesId.localeCompare(b.seriesId))
      .map((i) => i.seriesId),
    [items],
  );

  const step = useCallback((order: readonly string[], d: number) => {
    if (order.length === 0) return;
    const i = hover ? order.indexOf(hover) : -1;
    /* 아직 아무것도 안 짚었으면 들어오는 방향의 **첫 칸**부터. 끝에서는 멈춘다
       (감싸면 「끝」이 안 느껴져서 같은 자리를 계속 돈다). */
    const next = i < 0
      ? (d > 0 ? 0 : order.length - 1)
      : Math.min(order.length - 1, Math.max(0, i + d));
    onHover(order[next] ?? null);
  }, [hover, onHover]);

  const onKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    switch (e.key) {
      case 'ArrowUp':
        e.preventDefault();
        step(byRank, -1);
        break;
      case 'ArrowDown':
        e.preventDefault();
        step(byRank, 1);
        break;
      case 'ArrowLeft':
        e.preventDefault();
        step(byWidth, -1);
        break;
      case 'ArrowRight':
        e.preventDefault();
        step(byWidth, 1);
        break;
      case 'Home':
        e.preventDefault();
        onHover(byRank[0] ?? null);
        break;
      case 'End':
        e.preventDefault();
        onHover(byRank[byRank.length - 1] ?? null);
        break;
      case 'Escape':
        e.preventDefault();
        onHover(null);
        break;
      default:
        break;
    }
  }, [byRank, byWidth, step, onHover]);

  /* 리드아웃이 읽는 점 — 짚은 것이 없으면 **1등**을 읽는다. 「비어 있는 상태」가
     없어야 줄이 생겼다 사라지며 그림 높이를 흔들지 않는다(스트립의 그 근거). */
  const at = useMemo(
    () => items.find((i) => i.seriesId === hover)
      ?? [...items].sort((a, b) => a.rank - b.rank)[0]
      ?? null,
    [items, hover],
  );

  /* 값이 들어갈 자리를 **극단으로 재서** 비워 둔다 — 짚어 옮길 때 오른쪽 칸이
     한 글자씩 밀리지 않게(`slotChars` 의 그 근거). */
  const nowCh = useMemo(() => {
    const v = items.map((i) => i.nowBp);
    return slotChars(bp, Math.min(...v), Math.max(...v));
  }, [items]);
  const meanCh = useMemo(() => {
    const v = items.map((i) => i.meanBp);
    return slotChars(bp, Math.min(...v), Math.max(...v));
  }, [items]);

  return (
    <>
      {at ? (
        <ChartReadoutStrip
          date={`${at.sectorLabel} ${at.tenor}`}
          slots={[
            { key: 'now', label: '국고 대비', value: bp(at.nowBp), chars: nowCh },
            { key: 'mean', label: '자기평소', value: bp(at.meanBp), chars: meanCh, drop: 1 },
            { key: 'rank', label: '순위', value: `${at.rank}위`, drop: 2 },
          ]}
          change={{ label: 'z', text: fmtDelta(at.z, 'ratio'), v: at.z }}
        />
      ) : null}

      {/* `overflow="hidden"` 은 장식이 아니다 — svg 를 상자의 실측 크기 그대로
          그리므로, 넘침을 안 막으면 스크롤바가 떴다 사라지며 `useMeasure` 를
          다시 울려 **진동**한다(`ui/useMeasure.ts` 머리의 그 16px 판례).
          제품 사분면의 `.sr-rv-plotfill` 이 같은 이유로 그 줄을 든다. */}
      <Box ref={ref} width="100%" minHeight={260} flexGrow={1} overflow="hidden">
        <svg
          width={w}
          height={h}
          role="application"
          /* 라벨이 **화살표가 무엇을 하는지**를 적는다 — 규칙을 안 적으면 눌러 볼
             이유가 없다(터미널 그림 축들이 같은 문장을 든다). */
          aria-label={
            `크레딧 RV 사분면 — 위아래 화살표로 순위를, 좌우 화살표로 스프레드 폭을 `
            + `짚습니다. Home 으로 1등, Esc 로 놓습니다. `
            + `후보 ${items.length}개 중 좁은데 싼 칸(순수 RV)이 ${counts.pureRv}개, `
            + `넓은데 비싼 칸(캐리만)이 ${counts.carryOnly}개예요`
          }
          tabIndex={0}
          onKeyDown={onKeyDown}
        >
          {/* 가로 경계 = 오늘 후보 중앙값. */}
          <line
            x1={geo.xMidPx} y1={PAD.t} x2={geo.xMidPx} y2={PAD.t + geo.inner.h}
            stroke="var(--color-fgMuted)" strokeWidth={1} opacity={0.35}
          />
          {/* 세로 경계 = 0(자기 평소). 자료 범위 밖이면 안 긋는다. */}
          {geo.zeroInRange ? (
            <line
              x1={PAD.l} y1={geo.zeroPx} x2={PAD.l + geo.inner.w} y2={geo.zeroPx}
              stroke="var(--color-fgMuted)" strokeWidth={1} opacity={0.35}
            />
          ) : null}
          {geo.points.map((p) => {
            const on = hover === p.id;
            return (
              <g key={p.id} data-on={on || undefined}>
                {/* 짚힌 점의 고리 — 제품 사분면이 강조를 그리는 그 모양이다. */}
                {on ? (
                  <circle
                    cx={p.cx} cy={p.cy} r={10}
                    fill="none" stroke="var(--color-fg)" strokeWidth={1} opacity={0.4}
                  />
                ) : null}
                <circle
                  cx={p.cx}
                  cy={p.cy}
                  r={on ? 6 : 3.5}
                  fill={on ? 'var(--color-fg)' : 'var(--color-fgMuted)'}
                  opacity={on ? 1 : 0.62}
                />
                {/* 판정만 넓힌다 — 점을 24px 로 키우면 120칸이 서로 먹는다. */}
                <circle
                  className="sr-quad-hit"
                  cx={p.cx}
                  cy={p.cy}
                  r={HIT_R}
                  onMouseEnter={() => onHover(p.id)}
                  onMouseLeave={() => onHover(null)}
                />
              </g>
            );
          })}
          {/* 네 구역의 이름 — 축 둘을 **말 그대로** 서술한다(제품 사분면의 그 규율:
              가치 판단 낱말을 얹지 않는다). 모서리에 적어야 「왼쪽 위」가 어디인지
              설명문과 그림이 따로 놀지 않는다. */}
          <text x={PAD.l + 6} y={PAD.t + 16} className="sr-rv-quad">좁은데 싸다 · 순수 RV</text>
          <text x={w - PAD.r - 6} y={PAD.t + 16} textAnchor="end" className="sr-rv-quad">
            넓고 싸다
          </text>
          <text x={PAD.l + 6} y={PAD.t + geo.inner.h - 8} className="sr-rv-quad">좁고 비싸다</text>
          <text
            x={w - PAD.r - 6} y={PAD.t + geo.inner.h - 8}
            textAnchor="end" className="sr-rv-quad"
          >
            넓은데 비싸다 · 캐리만
          </text>

          {/* ★눈금 — 첫 판에는 **숫자가 하나도 없었다**(실측 스크린샷에서 드러났다).
              「세로선은 중앙값」이라고 적어도 그 중앙값이 얼마인지 읽을 길이 없었다. */}
          {geo.xTicks.map((v, i) => (
            <text
              key={`x${i}`}
              x={i === 0 ? PAD.l : i === 1 ? geo.xMidPx : PAD.l + geo.inner.w}
              y={PAD.t + geo.inner.h + 18}
              textAnchor={i === 0 ? 'start' : i === 1 ? 'middle' : 'end'}
              className="sr-rv-tick"
            >
              {bp(v)}
            </text>
          ))}
          {geo.yTicks.map((v, i) => (
            <text
              key={`y${i}`}
              x={PAD.l - 8}
              y={(v === 0 ? geo.zeroPx : v > 0 ? PAD.t : PAD.t + geo.inner.h) + 4}
              textAnchor="end"
              className="sr-rv-tick"
            >
              {fmtDelta(v, 'ratio')}
            </text>
          ))}
          <text x={PAD.l + geo.inner.w / 2} y={h - 6} textAnchor="middle" className="sr-rv-tick">
            {xScaleNote(geo.xScale)}
          </text>
          {/* ⚠세로축 이름을 svg 안에 두지 않는다 — 좌상단 `z` 글자가 첫 눈금
              `+0.42` 와 **겹쳤다**(실측 스크린샷 2026-10-06). 제품 `RvScatter` 도
              세로축 이름을 그림 안에 안 둔다: 축이 무엇인지는 카드 머리의
              「세로가 점수고 …」 한 줄과 랭킹 표의 `z` 열이 이미 말한다.
              겹침은 잘림의 사촌이고 같은 등급의 결함이다(CLAUDE.md 말줄임 §3). */}
        </svg>
        {/* 그림의 변화는 **소리가 안 난다** — 짚은 자리를 한 문장으로 읽는다.
            스트립은 `aria-hidden` 이라(제 머리에 그 근거가 있다) 두 번 읽히지 않는다. */}
        <span className="sr-a11y-only" aria-live="polite">
          {hover && at
            ? `${at.sectorLabel} ${at.tenor} — 국고 대비 ${bp(at.nowBp)}bp, `
              + `자기평소 ${bp(at.meanBp)}bp, z ${fmtDelta(at.z, 'ratio')}, ${at.rank}위`
            : ''}
        </span>
      </Box>
    </>
  );
}

export function CreditDtsPage() {
  const [got, setGot] = useState<CreditDts | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [hover, setHover] = useState<string | null>(null);

  const load = useCallback((signal?: AbortSignal) => {
    setBusy(true);
    fetchCreditDts(signal)
      .then((r) => { setGot(r); setErr(null); })
      .catch((e: unknown) => {
        if (signal?.aborted) return;
        setErr(e instanceof BacktestUnavailable
          ? '실행 중인 백엔드가 필요해요 — 민평이 SQL 에만 있어서 미리 구워둘 수가 없어요.'
          : e instanceof Error ? e.message : String(e));
      })
      .finally(() => { if (!signal?.aborted) setBusy(false); });
  }, []);

  useEffect(() => {
    const ac = new AbortController();
    load(ac.signal);
    return () => ac.abort();
  }, [load]);

  const ranked = useMemo(
    () => [...(got?.items ?? [])].sort((a, b) => a.rank - b.rank), [got]);
  /* ★두 축의 순위상관 — 이 수리의 증거. 0 에 가까울수록 「싼 것」과 「넓은 것」이
     갈려 있다는 뜻이고, 그게 제품 Score 와 이 화면의 차이다. */
  const orth = useMemo(() => {
    const its = got?.items ?? [];
    return spearman(its.map((i) => i.nowBp), its.map((i) => i.z));
  }, [got]);
  const counts = useMemo(() => quadrantCounts(got?.items ?? []), [got]);

  if (err) {
    return (
      <ErrorState
        what="크레딧 RV (DTS)"
        detail={err}
        onRetry={() => load()}
        retrying={busy}
      />
    );
  }
  if (!got) return <LoadingState what="크레딧 RV (DTS)" />;

  return (
    <VStack gap={1} width="100%" minHeight={0} flexGrow={1}>
      <VStack gap={0.25} paddingX={2} paddingTop={1.5}>
        <HStack gap={1} alignItems="baseline" flexWrap="wrap">
          <Text font="label1" as="h2" noWrap>크레딧 RV (DTS)</Text>
          <Text font="legal" as="span" color="fgMuted">
            {`민평 ${got.asof} · ${got.items.length}칸 · 창 ${got.window}일 · 바닥 ${got.floorBp}bp`}
          </Text>
        </HStack>
        <Text font="legal" as="span" color="fgMuted">
          {got.basis} — 국고 대비 하나로 재고 통안은 뺐어요(금리물이라 국고 대비가 0 을 가로질러요).
        </Text>
      </VStack>

      <HStack gap={1} paddingX={2} width="100%" minHeight={0} flexGrow={1} flexWrap="wrap">
        <VStack className="sr-card" flexGrow={1} flexShrink={1} minWidth={420} minHeight={300}>
          <VStack gap={0.25} paddingX={2} paddingTop={1.5} paddingBottom={0.5}>
            <Text font="label1" as="h3" noWrap>사분면 — 싼 것과 넓은 것을 가른다</Text>
            <Text font="legal" as="span" color="fgMuted">
              {orth == null
                ? '세로가 점수고, 가로는 점수에서 일부러 뺀 것이에요.'
                : `세로가 점수고 가로는 점수에서 일부러 뺀 거예요 — 지금 둘의 순위상관은 ${fmtDelta(orth, 'ratio')} 예요.`}
            </Text>
            <Text font="legal" as="span" color="fgMuted">
              {`왼쪽 위가 「좁은데 싸다」 = 순수 RV ${counts.pureRv}개 · `
                + `오른쪽 아래가 「넓은데 비싸다」 = 캐리만 ${counts.carryOnly}개예요.`}
            </Text>
          </VStack>
          {got.items.length > 0 ? (
            <Quadrant items={got.items} hover={hover} onHover={setHover} />
          ) : null}
        </VStack>

        <VStack className="sr-card" flexGrow={1} flexShrink={1} minWidth={420} minHeight={300}>
          <VStack gap={0.25} paddingX={2} paddingTop={1.5} paddingBottom={0.5}>
            <Text font="label1" as="h3" noWrap>랭킹</Text>
            <Text font="legal" as="span" color="fgMuted">
              z 가 큰 순 — 제 평소보다 벌어진 칸이 위예요. 투자판단이 아니라 RV 랭킹이에요.
            </Text>
          </VStack>
          <Box paddingX={0} overflow="auto" maxHeight={420}>
            <table className="sr-rv-table sr-rv-divided">
              <thead>
                <tr>
                  <th className="sr-rv-th">순위</th>
                  <th className="sr-rv-th sr-rv-left">종목</th>
                  <th className="sr-rv-th">국고 대비</th>
                  <th className="sr-rv-th">자기평소</th>
                  <th className="sr-rv-th">z</th>
                </tr>
              </thead>
              <tbody>
                {ranked.map((it) => (
                  <tr
                    key={it.seriesId}
                    className="sr-rv-row"
                    /* 역방향 연동은 **이 클래스가 이미 지고 있다** — 인라인
                       배경으로 다시 적으면 한쪽만 낡는다. */
                    data-on={hover === it.seriesId ? 'true' : undefined}
                    onMouseEnter={() => setHover(it.seriesId)}
                    onMouseLeave={() => setHover(null)}
                  >
                    <td className="sr-rv-td">{it.rank}</td>
                    <td className="sr-rv-td sr-rv-left">
                      <div className="sr-name-stack">
                        <Text font="label1" as="span" noWrap>
                          {it.sectorLabel} {it.tenor}
                        </Text>
                        {it.floored ? (
                          <Text font="legal" as="span" color="fgMuted" noWrap>
                            {`스프레드가 바닥(${got.floorBp}bp)보다 좁아 바닥으로 나눴어요`}
                          </Text>
                        ) : null}
                      </div>
                    </td>
                    <td className="sr-rv-td">{bp(it.nowBp)}</td>
                    <td className="sr-rv-td">{bp(it.meanBp)}</td>
                    {/* 틴트는 캐논 한 곳 · 스케일 1 (|z| 가 1 을 넘는 일이 드물다).
                        글자는 **잉크**다(tint.ts 의 그 규율). */}
                    <td className="sr-rv-td" style={{ background: tintFor(it.z, 1) }}>
                      <Text font="body" as="span" tabularNumbers noWrap>
                        {fmtDelta(it.z, 'ratio')}
                      </Text>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Box>
        </VStack>
      </HStack>

      <VStack gap={0.25} paddingX={2} paddingBottom={2}>
        <Text font="legal" as="p" color="fgMuted" maxWidth={900}>
          ⚠ 느린 회전에서만 살아요 — 손익분기 왕복비용이 21일 0.63bp · 63일 0.99bp ·
          126일 1.63bp 예요. 이 데스크 가정(1bp 왕복)에서 21일 회전은 죽어요.
          표본밖은 2025-01 이후 한 번 돌린 것이고 겹침이 심해서 t 를 액면대로 믿으면 안 돼요.
        </Text>
        {got.excluded.length > 0 ? (
          <Text font="legal" as="p" color="fgMuted">
            {`못 세운 칸 ${got.excluded.length}개 — `
              + got.excluded.slice(0, 3).map((e) => `${e.label}: ${e.why}`).join(' · ')}
          </Text>
        ) : null}
      </VStack>
    </VStack>
  );
}
