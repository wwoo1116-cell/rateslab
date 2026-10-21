'use client';

/* 테너 × (발행 + 주체) 한 표 [OWNER 2026-10-20 — 「테너별 국고채 발행량이랑, 각
 * 투자주체들이 어떻게 이를 담아가는지」].
 *
 * `FlowTable`(주체별 순위)과 같은 **손 표**다 — 클래스 다섯 벌(`.sr-rv-rank-fill` ·
 * `-scroll` · `-table` · `-th` · `-td`)을 그대로 쓴다. CDS `Table` 을 안 쓰는
 * 이유도 같다(셀당 32px 이 이 밀도에 안 맞는다, `rv/RankingTable.tsx:28`).
 *
 * ## 왜 한 표인가
 *
 * 공급과 수요가 **같은 행**에 서야 「30년물 46.0조를 찍었는데 보험이 13.1조를
 * 담았다」가 한 줄로 읽힌다. 10-19 판에서는 발행이 다른 면에 있어서 둘을 눈으로
 * 이어야 했다 — 그 면을 접고 「발행」을 이 표의 **첫 값 열**로 들였다.
 *
 * ## 칸이 손잡이다 [OWNER 2026-10-20 — 「칸을 누른다」]
 *
 * 칸 하나가 (만기물 × 주체) 둘을 한 번에 고른다 — 누르면 오른쪽 그림이 그
 * 만기물의 그 주체 일별 순매수(+이동평균)로 바뀐다. `FlowTable` 이 이름 칸에
 * 진짜 `<button>` 을 두는 그 꼴 그대로다: `<tr>`·`<td>` 에 role 을 얹지 않아
 * 스크린리더의 표 탐색을 지키고, 짚기(`data-on`)와 고르기(`data-pick`)는 다른
 * 모양이다(CLAUDE.md 키보드 규칙 2).
 *
 * 열 머리의 주체 이름도 버튼이다 — 그쪽은 **만기물을 `ALL` 로** 두고 그 주체만
 * 바꾼다(「보험 전체가 어떻게 됐나」).
 *
 * ## 단위
 *
 * 구간 합이라 전부 **조**다(`fmtJo`). `FlowTable` 처럼 일별과 누적이 섞이지 않아
 * 열마다 자가 갈릴 일이 없다 — 머리에 한 번만 적는다.
 */

import { VStack } from '@coinbase/cds-web/layout';
import { Text } from '@coinbase/cds-web/typography';

import { fmtJo } from '@/lib/format';
import { directionClass } from '@/table/tint';
import { ThHelp } from '@/ui/ThHelp';

import type { CashTenor, FlowMatrixBoard } from './api';

/** 「발행」 열은 **방향색을 안 칠한다**.
 *
 *  방향색은 부호와 매매에만 쓴다(CLAUDE.md 규칙 3 계열). 발행량은 늘 양수라
 *  칠하면 표 전체가 한쪽 색으로 기울고, 그 옆 주체 칸의 빨강·파랑이 안 읽힌다.
 *  공급은 **크기**이지 방향이 아니다. */
function supplyText(v: number): string {
  return fmtJo(v).replace('+', '');
}

/** ★장기 합산 — **서버가 더한 줄을 읽기만 한다** [트레이더 2026-10-21 —
 *  「보험에서 20·30·50 현물 매수를 한번에 합산해서 볼 수 있으면」].
 *
 *  첫 판은 여기서 `reduce` 로 접었다가 `guards/strategy-flow` 에 걸렸다. 그
 *  가드가 맞다 — **화면이 합을 다시 세면 서버의 수와 갈릴 길이 열린다**(§16).
 *  합은 `flow.py` 의 `fold` 가 내고(`matrix.fold`), 여기서는 세 줄을 빼고 그
 *  줄을 끼우는 **고르기**만 한다. 산술이 한 줄도 없다.
 *
 *  접힌 줄을 누르면 만기물은 `ALL` 이다 — 세 줄의 합에 해당하는 단일 만기물이
 *  원천에 없으므로 없는 것을 만들어 내지 않는다(서버 주석과 같은 말). */
type MatrixRow = FlowMatrixBoard['rows'][number];

export function FlowMatrix({
  matrix, tenor, picked, onPick, highlight, onHover, foldLongTenors = false,
}: {
  matrix: FlowMatrixBoard;
  /** 지금 그림에 선 만기물 — 그 행이 `data-pick` 으로 표시된다. */
  tenor: CashTenor;
  /** 지금 그림에 선 주체 열쇠. */
  picked: string | null;
  /** 칸을 누르면 둘을 한 번에 고른다. */
  onPick: (tenor: CashTenor, subject: string) => void;
  highlight?: string | null;
  onHover?: (key: string | null) => void;
  /** 20·30·50년을 한 줄로 접는다(위 `foldLong` 머리). */
  foldLongTenors?: boolean;
}) {
  const cells = matrix.cols;
  const fold = matrix.fold ?? null;
  const folding = foldLongTenors && !!fold;
  const hidden = new Set(fold?.of ?? []);
  /** 접은 자리에 서버의 합산 줄 하나를 끼운다 — 더하지 않고 고르기만 한다. */
  const rows: MatrixRow[] = !folding
    ? matrix.rows
    : matrix.rows.flatMap((r) =>
        !hidden.has(r.key) ? [r] : r.key === fold!.of[0] ? [fold as MatrixRow] : []);
  /** 접힌 줄은 어느 한 만기물이 아니므로 고르기를 `ALL` 로 돌린다. */
  const pickOf = (r: MatrixRow): CashTenor =>
    folding && r.key === fold!.key ? 'ALL' : (r.key as CashTenor);
  return (
    <div className="sr-rv-rank-fill">
      <div className="sr-rv-rank-scroll">
        <table className="sr-rv-table sr-rv-divided">
          <thead>
            <tr>
              <th className="sr-rv-th sr-rv-left">만기물</th>
              <th className="sr-rv-th">
                <ThHelp
                  font="inherit"
                  label="발행 (조)"
                  help="그 만기물의 경쟁 낙찰에 비경쟁 인수를 더하고 매입(바이백)을 뺀 수예요. 고른 구간의 합이에요."
                />
              </th>
              {cells.map((c) => (
                <th key={c.key} className="sr-rv-th">
                  {/* 열 머리가 버튼이다 — 만기물은 전체로 두고 주체만 바꾼다.
                      칸 버튼과 **다른 일**을 하므로 `aria-label` 이 그것을 적는다. */}
                  <button
                    type="button"
                    className="sr-rv-linkbtn sr-rv-stack"
                    aria-label={c.pd
                      ? `${c.label} 전체 만기물을 그림에 세우기 — PD 인수 가정이 더해진 열이에요`
                      : `${c.label} 전체 만기물을 그림에 세우기`}
                    aria-pressed={picked === c.key && tenor === 'ALL'}
                    onFocus={() => onHover?.(c.key)}
                    onBlur={() => onHover?.(null)}
                    onClick={() => onPick('ALL', c.key)}
                  >
                    <span className="sr-rv-name">{c.label}</span>
                    {/* ★**가정이 섞인 열은 표 안에서 구별된다** [OWNER 2026-10-20].
                        종전에는 조건 스트립의 회색 문장만 그 사실을 말해서 표만
                        보면 못 가렸다 — 실측: PD 를 켜면 은행 3년물이 +12.9 →
                        +27.8조가 되는데(공급 37.3 × 0.4 를 얹는다) 표에는 아무
                        표식이 없었다. 「은행이 3년을 27.8조 담았다」로 읽히면
                        틀린 수다. 말줄임 금지라 줄여 적지 않고 **둘째 줄**에 쓴다. */}
                    {c.pd ? <span className="sr-rv-sub">PD 포함</span> : null}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.label}
                className="sr-rv-row"
                data-on={r.key === highlight || undefined}
                data-pick={pickOf(r) === tenor || undefined}
                onMouseEnter={() => onHover?.(r.key)}
                onMouseLeave={() => onHover?.(null)}
              >
                <td className="sr-rv-td sr-rv-left">
                  <span className="sr-rv-name">{r.label}</span>
                </td>
                <td className="sr-rv-td">{supplyText(r.supply)}</td>
                {cells.map((c) => {
                  const v = r.cols[c.key] ?? 0;
                  const on = pickOf(r) === tenor && c.key === picked;
                  return (
                    <td key={c.key} className="sr-rv-td" data-pick={on || undefined}>
                      <button
                        type="button"
                        className="sr-rv-linkbtn"
                        aria-label={`${r.label} ${c.label} 일별 그림에 세우기`}
                        aria-pressed={on}
                        onFocus={() => onHover?.(r.key)}
                        onBlur={() => onHover?.(null)}
                        onClick={() => onPick(pickOf(r), c.key)}
                      >
                        <span className={directionClass(v)}>{fmtJo(v)}</span>
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
            {/* 합계는 **`ALL` 바구니와 같은 수**다(서버가 둘을 따로 세고
                `test_flow` 가 맞댄다). 줄을 가르는 표시는 클래스가 진다. */}
            <tr className="sr-rv-row sr-rv-total" data-pick={tenor === 'ALL' || undefined}>
              <td className="sr-rv-td sr-rv-left">
                <span className="sr-rv-name">{matrix.total.label}</span>
              </td>
              <td className="sr-rv-td">{supplyText(matrix.total.supply)}</td>
              {cells.map((c) => {
                const v = matrix.total.cols[c.key] ?? 0;
                const on = tenor === 'ALL' && c.key === picked;
                return (
                  <td key={c.key} className="sr-rv-td" data-pick={on || undefined}>
                    <button
                      type="button"
                      className="sr-rv-linkbtn"
                      aria-label={`전체 만기물 ${c.label} 일별 그림에 세우기`}
                      aria-pressed={on}
                      onFocus={() => onHover?.(c.key)}
                      onBlur={() => onHover?.(null)}
                      onClick={() => onPick('ALL', c.key)}
                    >
                      <span className={directionClass(v)}>{fmtJo(v)}</span>
                    </button>
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
        {/* ★**표가 닫혔나를 화면이 말한다** [OWNER 2026-10-20]. 열 주체 합은
            PD 끔이면 0, 켬이면 발행과 같아야 한다 — 그 한 줄이 「만기물 분해가
            샜나 · PD 가 두 번 더해졌나」를 동시에 잡는다. 수는 서버가 센다(§16).
            어긋나는 날은 **지목한다** — 「어긋나요」만 적으면 쓸 수 없는 경고다.

            ⚠세로 상자로 **감싸야 한다**: CDS `Text` 는 `as="p"` 라도
            `display: inline` 이라, 둘을 나란히 두면 **한 줄에 이어 붙는다**
            (실측 2026-10-20 — 경고 문장 끝에 설명 문장이 그대로 붙었다). 한
            문단일 때는 안 드러났던 자리다. */}
        <VStack gap={0.5} paddingX={1} paddingY={1}>
          <Text as="p" font="legal"
            color={matrix.check.ok ? 'fgMuted' : 'fgWarning'}>
            {matrix.check.say}
          </Text>
          <Text as="p" font="legal" color="fgMuted">
            칸을 누르면 그 만기물의 그 주체가 오른쪽 그림에 서요. 주체 이름을 누르면
            만기물은 전체가 돼요. 수는 고른 구간({matrix.from} ~ {matrix.to})의 합이에요.
            {matrix.pending > 0
              ? ` 입찰 ${matrix.pending}건은 현물 자료가 그 날에 아직 안 닿아 발행 열에 못 얹었어요.`
              : ''}
          </Text>
        </VStack>
      </div>
    </div>
  );
}
