'use client';

/* 포지셔닝 패널 — **COT 관례 그대로** [OWNER 2026-10-22 — 「COT index 관례를
 * 따라가주고, 가능하다면 디자인도 COT나 다른 사이트에 맞게」].
 *
 * ## 밖에서는 이렇게 생겼다
 *
 * 외부 COT 패널(Barchart · Tradingster · CFTC 주간 요약)의 공통 글리프는 수가
 * 아니라 **0~100 막대**다. 셋이 같은 꼴을 쓴다: 주체 한 줄 · 극단 구역을 칠한
 * 띠 · 띠 위의 표식 · 옆에 수. 수만 적으면 「80 이 높은 건가」를 읽는 사람이
 * 외워야 하고, 열 줄이 쌓이면 못 외운다.
 *
 * 색만 바꿨다 — 저쪽은 녹/적, 여기는 **적=순매수 · 청=순매도**다. 한 화면에서
 * 녹색이 다른 뜻을 가지면 안 된다(`theme/type.css` 의 `.sr-cotbar` 머리).
 *
 * ## 왜 표가 두 덩이인가 — 주체마다 **재는 것이 다르다**
 *
 * COT index 는 순포지션이 **평균회귀한다는 전제** 위에 있다(선물 투기자는
 * 롱↔숏을 뒤집는다). 현물 보유는 그렇지 않다 — 보험·연기금은 부채를 만기
 * 매칭하느라 **단조로 쌓는다** [OWNER 2026-10-22 — 「보험은 만기 매칭해야
 * 하니까 정상 아닌가? 그러면 변화량으로만 계산하는 게 맞지 않을까?」].
 *
 * 맞는 말이고 실측이 그 말과 같다(서버 `_cot_usable` 머리의 표): 창 안에서
 * 누적이 **100% 되돌아오는 주체는 금융투자와 은행 둘뿐**이고, 나머지는
 * 0.7~21.8% 다. 그래서 단조 주체에 수준 지표를 걸면 열 중 여덟이 천장·바닥에
 * 붙어 **변별을 못 한다**.
 *
 * 지우지 않고 **다른 자로 잰다**: 양방향 주체는 **수준**(COT index), 단방향
 * 주체는 **변화량**(1년 분포 자리). 둘 다 0~100 이지만 **다른 측정**이라
 * 한 덩이에 섞지 않고, 각 덩이의 머리가 무엇을 재는지 적는다.
 *
 * ## 부품
 *
 * 띠는 캐논(`.sr-track`/`.sr-track-mark` — Main 52주 「위치」 열의 그것)이고
 * 두께와 구역 음영만 다르다. 까닭은 그 CSS 의 머리에.
 */

import { VStack } from '@coinbase/cds-web/layout';
import { Text } from '@coinbase/cds-web/typography';

import { ThHelp } from '@/ui/ThHelp';

import type { FlowRow } from './api';

/** COT 관례의 극단 문턱. 아래가 바닥 쪽, 위가 천장 쪽이다. */
const LOW = 20;
const HIGH = 80;

/** 구역 경계 눈금 — 관례의 다섯 구간. */
const TICKS = [20, 40, 60, 80] as const;

/** 수 하나를 말로 — 「80 이 높은 건가」를 읽는 사람이 외우지 않게. */
function band(v: number): string {
  if (v >= HIGH) return '천장 쪽';
  if (v <= LOW) return '바닥 쪽';
  return '중간';
}

/** 0~100 띠 한 줄. `v` 는 이미 0~100 이고, 여기서 눈금을 바꾸지 않는다. */
function CotBar({ v, title }: { v: number; title: string }) {
  return (
    <span className="sr-track sr-cotbar" title={title}>
      {/* 극단 구역 — 칠은 **띠 안**이다. 띠 밖에 칠하면 줄과 줄 사이가 붙는다. */}
      <span
        className="sr-cotzone"
        style={{
          left: 0,
          width: `${LOW}%`,
          background: 'color-mix(in srgb, var(--sr-down) 22%, transparent)',
        }}
      />
      <span
        className="sr-cotzone"
        style={{
          left: `${HIGH}%`,
          right: 0,
          background: 'color-mix(in srgb, var(--sr-up) 22%, transparent)',
        }}
      />
      {TICKS.map((t) => (
        <span key={t} className="sr-cottick" style={{ left: `${t}%` }} />
      ))}
      <span className="sr-track-mark" style={{ left: `${v}%` }} />
    </span>
  );
}

/** 한 줄 — 이름 · 띠 · 수. 격자라 **열이 줄마다 같은 자리**에 선다
 *  (CLAUDE.md 얼라인 4·7 — 폭은 바깥이 준다). */
function Row({
  label, value, title, note, ranked = true,
}: {
  label: string;
  value: number | null | undefined;
  title: string;
  note?: string;
  /** 순위 하한 밖이면 흐리다 — **지우지 않는다**. 표와 같은 문법이고 같은
   *  까닭이다(`FlowTable` 의 하한 설명): 아주 작게 움직이는 주체는 백분위가
   *  쉽게 극단으로 가서, 흐리게 안 두면 그 줄이 제일 센 것처럼 읽힌다. */
  ranked?: boolean;
}) {
  return (
    <div className="sr-cotrow" style={ranked ? undefined : { opacity: 0.52 }}>
      <Text as="span" font="label2">{label}</Text>
      {value == null ? (
        /* ⚠`null` 은 **「못 잰다」**다 — 0 이 아니다. 띠를 그리면 「바닥에
           붙어 있다」로 읽힌다. */
        <Text as="span" font="legal" color="fgMuted">창이 안 찼어요</Text>
      ) : (
        <CotBar v={value} title={title} />
      )}
      <Text as="span" font="label2" className="sr-num">
        {value == null ? '—' : Math.round(value)}
      </Text>
      <Text as="span" font="legal" color="fgMuted">
        {value == null ? '' : (note ?? band(value))}
      </Text>
    </div>
  );
}

export function CotPanel({ rows }: { rows: readonly FlowRow[] }) {
  /* 서버가 「이 주체에서 수준이 뜻이 있나」를 이미 판정해 보낸다 — 화면이
     되돌림을 다시 세지 않는다(CLAUDE.md §16 — 화면은 셈하지 않는다). */
  /* ★덩이 안에서는 **그 덩이가 재는 수**로 줄을 세운다 — 외부 COT 패널의
     관례이고(가장 극단인 쪽이 위), 뒤의 표(흐름 순위)와 차례가 다른 것이
     「다른 자」라는 말을 한 번 더 한다. */
  const level = rows.filter((r) => r.cotUsable)
    .slice().sort((a, b) => (b.cot ?? -1) - (a.cot ?? -1));
  const flow = rows.filter((r) => !r.cotUsable)
    .slice().sort((a, b) => (b.pct ?? -1) - (a.pct ?? -1));

  return (
    /* ★폭에 **천장을 둔다** [실측 2026-10-22]. 1,180px 창에서 띠가 764px 까지
       늘어났고, 0~100 짜리 지수에는 그 폭이 뜻이 없다 — 20% 구역 하나가
       153px 이라 극단 문턱이 「넓은 영역」으로 읽힌다. 외부 COT 패널의 막대도
       전부 고정폭이다. 남는 폭은 비워 둔다(늘리는 것보다 낫다). */
    <VStack gap={1.5} width="100%" maxWidth={620} paddingBottom={1}>
      {level.length > 0 ? (
        <VStack gap={0.75} width="100%">
          <ThHelp
            label="수준 — COT index"
            help="지금 들고 있는 양이 지난 3년(156주) 안에서 어디쯤인지예요. 0 이 3년 최저, 100 이 3년 최고이고, CFTC COT index 의 셈법(최저↔최고 min-max)을 그대로 따라요. 발행시장 인수분(PD)은 빼고 재요 — 배정받은 물량은 시장에서 잡은 포지션이 아니고, 늘 양수라 더하면 지수가 천장에 붙어요."
          />
          {level.map((r) => (
            <Row
              key={r.key}
              label={r.label}
              value={r.cot}
              ranked={r.ranked}
              title={`${r.label} — 3년 순포지션 범위의 ${Math.round(r.cot ?? 0)}% 지점`}
            />
          ))}
        </VStack>
      ) : null}

      {flow.length > 0 ? (
        <VStack gap={0.75} width="100%">
          <ThHelp
            label="변화량 — 1년 분포 자리"
            help="이 주체들은 포지션을 되돌리지 않고 단조로 쌓아요(부채 만기 매칭이 그래요). 그래서 수준으로 재면 전부 100 에 붙어 변별이 안 돼요 — 대신 「오늘 얼마나 샀나」를 지난 1년 분포에서 재요. 50 이 평소, 100 이 1년 중 가장 큰 순매수, 0 이 가장 큰 순매도예요."
          />
          {flow.map((r) => (
            <Row
              key={r.key}
              label={r.label}
              value={r.pct}
              ranked={r.ranked}
              title={`${r.label} — 지난 1년 순매수 분포의 ${Math.round(r.pct ?? 0)} 백분위`}
              /* 「왜 수준이 아닌가」를 줄마다 적는다 — 머리말에만 적으면 어느
                 주체가 얼마나 단조인지는 안 보인다. */
              note={r.retrace == null
                ? undefined
                : `되돌림 ${Math.round(r.retrace * 100)}%`}
            />
          ))}
        </VStack>
      ) : null}

      <Text as="p" font="legal" color="fgMuted">
        띠의 푸른 쪽({LOW} 이하)이 순매도 극단, 붉은 쪽({HIGH} 이상)이 순매수
        극단이에요 — COT 관례의 그 문턱이에요. 두 덩이는 <b>다른 자</b>예요:
        위는 「지금 얼마나 들고 있나」, 아래는 「오늘 얼마나 샀나」라서 수를
        서로 견주면 안 돼요. 어느 자로 잴지는 그 주체가 창 안에서 포지션을
        되돌린 적이 있나로 갈라요. 흐린 줄은 순위 하한 밖이에요 — 평소에 아주
        작게 움직이는 주체라 분포 자리가 쉽게 극단으로 가요.
      </Text>
    </VStack>
  );
}

/** 고른 주체 한 줄 — **오른쪽 카드의 머리**에 선다.
 *
 * 패널 전체를 카드에 넣지 않는 까닭은 오너의 1번 지적이 「너무 복잡하다」였기
 * 때문이다. 카드에는 **지금 보고 있는 주체 하나**만 서고, 열한 줄 전부는
 * 버튼 뒤의 창(`flow-rank`)에 있다 — 「첫 화면에서 수급상황을 보고, 버튼을
 * 누르면 창」 [OWNER 2026-10-21] 의 그 나눔이다.
 *
 * 어느 자로 재는지는 `CotPanel` 과 **같은 규칙**이다(서버의 `cotUsable`) —
 * 두 자리가 다른 판단을 하면 같은 주체가 두 수로 선다. */
export function CotLine({ row }: { row: FlowRow }) {
  const useLevel = !!row.cotUsable;
  const v = useLevel ? row.cot : row.pct;
  if (v == null) return null;
  return (
    <div className="sr-cotrow">
      <Text as="span" font="legal" color="fgMuted">
        {useLevel ? '포지셔닝' : '오늘 자리'}
      </Text>
      <CotBar
        v={v}
        title={useLevel
          ? `${row.label} — 3년 순포지션 범위의 ${Math.round(v)}% 지점 (COT index)`
          : `${row.label} — 지난 1년 순매수 분포의 ${Math.round(v)} 백분위`}
      />
      <Text as="span" font="label2" className="sr-num">{Math.round(v)}</Text>
      <Text as="span" font="legal" color="fgMuted">
        {/* **무엇을 잰 수인지를 줄에 적는다** — 두 자가 같은 0~100 이라
            안 적으면 옆 창의 수와 섞어 읽는다. */}
        {useLevel ? `COT · 3년` : `변화량 · 1년`}
      </Text>
    </div>
  );
}
