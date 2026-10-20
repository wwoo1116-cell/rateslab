'use client';

/* 수급 순위표 — **손 표**다 [2026-10-19].
 *
 * CDS `Table` 을 안 쓰는 이유는 `rv/RankingTable.tsx:28` 과 같다: 셀당 32px 이
 * 이 밀도에 안 맞는다. 그 파일의 클래스 다섯 벌(`.sr-rv-rank-fill` ·
 * `-scroll` · `-table` · `-th` · `-td`)을 그대로 쓴다 — 이름이 `rv` 로
 * 시작하지만 **앱 공용**이다(MrPage 도 같은 두 벌을 쓴다, CLAUDE.md 캐논 규칙 2:
 * 「클래스 이름은 소유권이 아니다」).
 *
 * ## 이 표가 지는 것
 *
 * 그림에는 **최대 4계열**만 올라간다(이 리포에 N계열 범주형 팔레트가 없다).
 * 그래서 **전수는 표가 진다** — 열한 주체가 전부 여기 서고, 순위 밖인 줄도
 * 지우지 않고 흐리게 남는다. 「안 보인다」와 「없다」는 다른 말이다.
 *
 * ## 이름이 버튼이다 [OWNER 2026-10-19 — 「각 엔드수요별로 MA」]
 *
 * 일별 그림(+이동평균)은 한 주체만 세울 수 있다. 어느 주체를 세울지 고르는
 * 손잡이가 **이 표의 이름 칸**이다 — `rv/RankingTable.tsx:188` 과 같은 꼴로 `<tr>`
 * 에 role 을 얹지 않고 칸 안에 진짜 `<button>` 을 둔다(스크린리더의 표 탐색을
 * 지킨다). 짚기(hover·focus → `data-on`)와 고르기(click → `data-pick`)는 다른
 * 모양이다(CLAUDE.md 키보드 규칙 2).
 */

import { Text } from '@coinbase/cds-web/typography';

import { fmtContracts, fmtEok, fmtJo } from '@/lib/format';
import { directionClass, flowTint } from '@/table/tint';
import { ThHelp } from '@/ui/ThHelp';

import type { FlowRow, FlowSide } from './api';

/** 값 한 칸 — **면마다, 그리고 열마다** 자가 다르다.
 *
 *  선물은 전부 계약수다. 현물은 서버가 백만원으로 주는데 **일별과 누적의 크기가
 *  1,000배 다르다** — 일별을 조로 적으면 전부 `+0.0조` 로 뭉개지고(실측: 보험
 *  1,455억이 0.1조), 누적을 억으로 적으면 `−936,000억` 이 된다. 그래서 열이
 *  자기 단위를 지고 머리가 그것을 적는다. */
function val(v: number, side: FlowSide, scale: 'day' | 'year' = 'day'): string {
  if (side !== 'cash') return fmtContracts(v);
  return scale === 'year' ? fmtJo(v) : fmtEok(v);
}

/** 열 머리에 붙는 단위 — 숫자 칸에 단위를 반복하지 않는다(폭 낭비). */
function unitOf(side: FlowSide, scale: 'day' | 'year'): string {
  if (side !== 'cash') return '계약';
  return scale === 'year' ? '조' : '억';
}

export function FlowTable({
  rows, side, floor, highlight, onHover, picked, onPick,
}: {
  rows: readonly FlowRow[];
  side: FlowSide;
  floor: number;
  highlight?: string | null;
  onHover?: (key: string | null) => void;
  /** 일별 그림에 서 있는 주체 — 그 줄의 이름에 밑줄이 선다. */
  picked?: string | null;
  /** 이름을 누르면 그 주체가 일별 그림에 선다. */
  onPick?: (key: string) => void;
}) {
  return (
    <div className="sr-rv-rank-fill">
      <div className="sr-rv-rank-scroll">
        <table className="sr-rv-table sr-rv-divided">
          <thead>
            <tr>
              <th className="sr-rv-th">순위</th>
              <th className="sr-rv-th sr-rv-left">
                <ThHelp
                  font="inherit"
                  label="주체"
                  help="이름을 누르면 그 주체가 오른쪽 일별 그림(과 이동평균)에 서요."
                />
              </th>
              <th className="sr-rv-th">오늘 ({unitOf(side, 'day')})</th>
              <th className="sr-rv-th">
                <ThHelp
                  font="inherit"
                  label="평소 대비"
                  help="그 주체의 지난 1년 분포에 견준 오늘이에요. 창에서 오늘은 빼고 재요 — 오늘이 제 잣대를 키우면 안 되니까요."
                />
              </th>
              <th className="sr-rv-th">5일 ({unitOf(side, 'day')})</th>
              <th className="sr-rv-th">20일 ({unitOf(side, 'day')})</th>
              <th className="sr-rv-th">올해 ({unitOf(side, 'year')})</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.key}
                className="sr-rv-row"
                /* 순위 밖은 흐리게. 지우지 않는 이유는 위 머리에. */
                style={r.ranked ? undefined : { opacity: 0.52 }}
                data-on={r.key === highlight || undefined}
                data-pick={r.key === picked || undefined}
                onMouseEnter={() => onHover?.(r.key)}
                onMouseLeave={() => onHover?.(null)}
              >
                <td className="sr-rv-td">{r.rank ?? '—'}</td>
                <td className="sr-rv-td sr-rv-left">
                  {/* 2줄 이름 스택 — 캐논(`table/InstrumentTable.tsx`)의 그 꼴.
                      아랫줄이 **모집단**을 좁힌다: 어느 층의 주체이고 평소에
                      얼마나 움직이나. 스택 전체가 버튼이다(머리 §이름이 버튼이다). */}
                  <button
                    type="button"
                    className="sr-rv-linkbtn sr-rv-stack"
                    aria-label={`${r.label} 일별 그림에 세우기`}
                    aria-pressed={r.key === picked}
                    onFocus={() => onHover?.(r.key)}
                    onBlur={() => onHover?.(null)}
                    onClick={() => onPick?.(r.key)}
                  >
                    <span className="sr-rv-name">{r.label}</span>
                    {/* ★소속은 **카드 제목**이 이미 말한다(「기관계 세분 순위」).
                        여기 또 적으면 열 폭만 먹고(실측 90px) 오른쪽 카드의
                        리드아웃 칸 하나가 값을 떨군다. 아랫줄은 **모집단**만
                        좁힌다 — 「평소에 얼마나 움직이나」. */}
                    <span className="sr-rv-sub">
                      일평균 {val(Math.abs(r.avgAbs), side).replace('+', '')}
                      {unitOf(side, 'day')}
                    </span>
                  </button>
                </td>
                {/* 틴트 축은 **편차**다 — 크기로 칠하면 계약수가 천장을 뚫는다
                    (`table/tint.ts::flowTint` 머리). 세우는 축과 같아야 눈과
                    순위가 서로를 반박하지 않는다. */}
                <td className="sr-rv-td" style={flowTint(r.sigma)}>
                  <span className={directionClass(r.d1)}>{val(r.d1, side)}</span>
                </td>
                <td className="sr-rv-td">
                  {r.sigma == null ? (
                    '—'
                  ) : (
                    <span className={directionClass(r.sigma)}>
                      {r.sigma > 0 ? '+' : r.sigma < 0 ? '−' : ''}
                      {Math.abs(r.sigma).toFixed(2)}σ
                    </span>
                  )}
                </td>
                <td className="sr-rv-td">
                  <span className={directionClass(r.d5)}>{val(r.d5, side)}</span>
                </td>
                <td className="sr-rv-td">
                  <span className={directionClass(r.d20)}>{val(r.d20, side)}</span>
                </td>
                <td className="sr-rv-td">
                  <span className={directionClass(r.ytd)}>{val(r.ytd, side, 'year')}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {/* 조용히 빼지 않는다 — 왜 순위 밖인지 표가 말한다. */}
        <Text as="p" font="legal" color="fgMuted" paddingX={1} paddingY={1}>
          흐린 줄은 순위 밖이에요 — 지난 1년 일평균 순매수가{' '}
          {val(floor, side).replace('+', '')}{unitOf(side, 'day')}에 못 미쳐요. 그만큼 작게 움직이는
          주체는 평소 대비로 세우면 아주 작은 수가 1위가 돼요. 이름을 누르면 그 주체가
          일별 그림에 서요.
        </Text>
      </div>
    </div>
  );
}
