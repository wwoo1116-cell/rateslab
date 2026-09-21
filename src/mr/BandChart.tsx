'use client';

/* 값 + 밴드(중심선·상단·하단) 이력 차트 — Mean Reversion 상세 카드.
 *
 * RvPage 의 소형 차트와 같은 기계다: 공용 `TimeChart`(lightweight-charts —
 * CLAUDE.md 규칙 7 로 15차트가 캔버스로 옮겨 갔다. 종전 주석은 CDS
 * `CartesianChart` + `Scrubber` 를 말했는데 2026-08-26 이후 거짓이다),
 * 커서 리드아웃은 공용 `ReadoutCard`. 밴드가 상수가 아니라 **구르는 선**이라
 * 가격선(dataY 상수) 대신 시리즈 셋으로 선다. 밴드 선은 값보다 흐리다 —
 * 캔버스에는 불투명도 손잡이가 없어 색 자체를 흐리게 만든다(`palette.dim`).
 * 색을 더 시키지 않는 판단은 LinkedCharts 의 기준선과 같다(지각적 무게).
 *
 * 숫자는 서버 것 그대로(§16) — 여기서 밴드를 다시 내지 않는다.
 */

import { useState } from 'react';

import { Box } from '@coinbase/cds-web/layout';

import { TimeChart, type TimeLine } from '@/chart/TimeChart';
import type { Unit } from '@/lib/api';
import { fmtLevel } from '@/lib/format';
import { ReadoutCard, ReadoutLevel, placeReadout } from '@/ui/ReadoutCard';

import type { MrHistory } from './api';

export function BandChart({ history }: { history: MrHistory }) {
  const [idx, setIdx] = useState<number | null>(null);
  const dates = history.points.map((p) => p.t);
  const v = history.points.map((p) => p.v);
  const ma = history.points.map((p) => p.ma);
  const up = history.points.map((p) => p.up);
  const lo = history.points.map((p) => p.lo);
  const cur = idx != null ? history.points[idx] : undefined;
  const unit = history.unit as Unit;
  /* 주선 색 = **보이는 구간의 순변화 방향** — Main 미리보기(PreviewPane)의
     그 규칙이다. 잉크로 칠했던 판은 시뮬 시나리오 커브의 문법을 잘못 가져온
     것이었다 [OWNER 2026-08-25 — "진짜 Backtest 랑 Main 을 참고한 게 맞는지"]. */
  const net = v.length > 1 ? v[v.length - 1]! - v[0]! : 0;
  const hue = net === 0 ? 'var(--color-fgMuted)' : net > 0 ? 'var(--sr-up)' : 'var(--sr-down)';

  /* 주선 = 구간 방향색(hue), 보조선(밴드·중심)은 뮤트 — Main 미리보기의 종목 선 +
     기준선 위계 그대로. **밴드가 먼저** = 아래에 깔린다.
     캔버스에는 불투명도 손잡이가 없어 색 자체를 흐리게 만든다(`palette.dim`). */
  const lines: TimeLine[] = [
    { id: 'up', values: up, color: (p) => p.dim('var(--color-fgMuted)', 45), width: 1 },
    { id: 'lo', values: lo, color: (p) => p.dim('var(--color-fgMuted)', 45), width: 1 },
    { id: 'ma', values: ma, color: (p) => p.dim('var(--color-fgMuted)', 70), width: 1 },
    /* 점선 면 — Main 미리보기 종목 선의 그 채움(areaType="dotted"). */
    { id: 'v', values: v, color: (p) => p.resolve(hue), area: 'dots' },
  ];

  return (
    <Box
      className="sr-plot"
      width="100%"
      /* 카드 자리는 상자의 CSS 변수 — 상태가 아니다(`placeReadout` 머리글). */
      onMouseMove={(e: React.MouseEvent<HTMLDivElement>) => {
        placeReadout(e.currentTarget, e.clientX);
      }}
      onMouseLeave={() => setIdx(null)}
    >
      <TimeChart
        /* 240 → **160** [2026-09-21 · 계획면]. 240 의 근거는 아래 그대로이고
           (밴드 셋이 겹친다) 바뀐 것은 **이 차트가 선 자리**다: 계획면에서 이
           카드는 큰 수·차트만 지고 사실 스트립은 페이지 폭으로 내려갔는데, 855px
           화면에서 240 을 그대로 두면 표가 네 줄만 보인다(실측). 이 화면에서
           차트는 맥락이고 주인공은 표와 스트립이라 그쪽에 자리를 준다 — rv 소형
           차트(180)보다도 낮지만 밴드가 여전히 갈라져 읽힌다(실측으로 확인).
           원래 근거:
           주선 + 중심선 + 상·하단이 한 그림에 들어가 180 에서는 상단선과
           중심선이 붙어 읽히고, 200(LINKED PAIR 위 차트)은 x축을 자기가 지는
           차트의 높이라 여기(축 있음 + 밴드 넷)와는 조건이 다르다. 카드가 준
           자리(상세 카드 몸통)가 그 이상을 허용한다 — 2026-09-02 간격 감사가
           「근거 없는 다섯 번째 수」로 지적해 근거를 적는다. */
        height={160}
        accessibilityLabel={`${history.label} 값과 밴드 이력`}
        dates={dates}
        lines={lines}
        onHoverIndex={setIdx}
        /* 짚은 봉을 문장으로 — 상수 문장은 «무엇을 짚었는지»를 안 말한다
           (CLAUDE.md 규칙 7 · Main 미리보기 `scrubLabel` 의 그 자리). */
        hoverLabel={(i) => `${history.label} ${dates[i]} ${fmtLevel(history.points[i]?.v ?? null, unit)}`}
      />
      {cur ? (
        <ReadoutCard title={cur.t}>
          <ReadoutLevel k="값" v={cur.v} unit={unit} />
          <ReadoutLevel k="중심선" v={cur.ma} unit={unit} />
          <ReadoutLevel k="상단" v={cur.up} unit={unit} />
          <ReadoutLevel k="하단" v={cur.lo} unit={unit} />
        </ReadoutCard>
      ) : null}
    </Box>
  );
}
