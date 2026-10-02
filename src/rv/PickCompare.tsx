'use client';

/* 후보 비교 창 — 「사려는 유통물 둘셋을 나란히」 [OWNER 2026-10-02] ─────────────
 *
 * 왜 창인가: 지정 종목 카드는 **한 자리**뿐이어서 새로 고르면 앞 것이 사라졌다.
 * 트레이더가 실제로 하는 일은 「이 은행채 2.3년 vs 저 카드채 1.8년」 비교인데
 * 화면이 그 비교를 못 하게 하고 있었다. 본 화면(랭킹 표 + 사분면)의 세로 예산을
 * 먹지 않고, 랭킹을 보면서 옆에 띄워 두는 것이 이 일의 모양이라 **떠 있는 창**
 * (캐논 `ui/window/`)이다 — 포지션 담기(`paperadd`)와 같은 판단이다.
 *
 * ── ★후보는 **값을 복사해 두지 않는다** ─────────────────────────────────────
 * 담는 것은 `(섹터, 잔존, 민평 대비 호가)` **셋뿐**이고 Score·캐리·버퍼는 창이
 * 열릴 때마다 지금 페이로드로 **다시 스냅한다**. 담을 때의 `item` 을 넣어 두면
 * 창(52주/전체)·H·조달 기준을 바꿨을 때 이 표만 옛 숫자를 들고 서 있게 된다 —
 * 이 리포가 여러 번 밟은 그 결함이다(「멈춘 화면이 말하게」·갱신 staleness).
 * 그래서 이 파일에는 **담긴 값이 없다**: 열쇠만 있고 수는 전부 지금 것이다.
 *
 * ── 명구는 여기서도 의무다 ─────────────────────────────────────────────────
 * Score 를 적는 표면이면 **"투자판단이 아니라 RV 랭킹이에요"** 를 같이 적는다
 * (랭킹 표·Score 히트맵과 같은 규율 — `guards/rv-analysis` ①).
 *
 * CDS `Table` 금지는 이 화면의 로컬 캐논이다(셀당 32px — `RankingTable.tsx` 머리).
 * 그래서 손 표 `.sr-rv-table` 을 그대로 쓴다 — 랭킹 표와 **같은 CSS** 다.
 */

import { HStack, VStack } from '@coinbase/cds-web/layout';
import { Text } from '@coinbase/cds-web/typography';

import { FloatingWindow } from '@/ui/window/FloatingWindow';

import type { RvCreditItem, RvWindow } from './api';
import { sig, yr } from './fmt';
import { snapCreditBucket, type PickBounds } from './pick';

/** 담긴 후보 하나 — **열쇠만** 든다(위 ★). */
export interface PickCandidate {
  /** 담은 순서의 고유 번호. 같은 (섹터, 잔존)을 두 번 담을 수 있다 — 호가가
   *  다른 두 종목이고, 그 비교가 이 창의 목적이다. */
  id: number;
  sector: string;
  sectorLabel: string;
  ttm: number;
  /** 민평 대비 호가(bp). **`null` 은 「안 넣었다」이고 0 과 다른 사실이다** —
   *  0 은 「민평 그대로」라는 진술이다(이 리포의 공란 정책). */
  quoteBp: number | null;
}

/** 후보 하나를 지금 페이로드로 다시 스냅한 줄. */
function row(c: PickCandidate, items: readonly RvCreditItem[], bounds: PickBounds) {
  return { c, out: snapCreditBucket(items, c.sector, c.ttm, bounds) };
}

export function PickCompare({
  candidates,
  items,
  bounds,
  window: win,
  onRemove,
  onSelect,
  onClose,
}: {
  candidates: readonly PickCandidate[];
  items: readonly RvCreditItem[];
  bounds: PickBounds;
  /** 창(52주/전체) — 「지난주 백분위」가 무엇 대비인지 적는다. 상수를 적으면
   *  화면이 거짓말을 한다(RankingTable 의 같은 prop, 같은 이유). */
  window: RvWindow;
  onRemove: (id: number) => void;
  /** 종목 칸의 버튼 → 이력 단면(랭킹 표의 그 경로). */
  onSelect: (p: RvCreditItem) => void;
  onClose: () => void;
}) {
  /* 순서는 **Score 내림차순** — 비교가 목적인 표라 「어느 게 제일 싼가」가 첫
     줄이어야 한다. Score 없는 줄(집합이 얕음·범위 밖)은 아래로 모은다: 조용히
     빼면 "담았는데 왜 없지"가 된다(랭킹 표의 그 규율).
     ⚠`sort` 는 서버 값의 **배열 정렬**이고 재계산이 아니다(§16) — 금지된 것은
     `reduce`·`sqrt` 로 통계를 다시 세는 것이다. */
  const rows = candidates.map((c) => row(c, items, bounds));
  const sorted = [...rows].sort((a, b) => {
    const sa = a.out?.kind === 'hit' ? a.out.item.score : null;
    const sb = b.out?.kind === 'hit' ? b.out.item.score : null;
    if (sa == null && sb == null) return a.c.id - b.c.id;
    if (sa == null) return 1;
    if (sb == null) return -1;
    return sb - sa;
  });

  return (
    <FloatingWindow
      windowKey="rvpick"
      title="후보 비교"
      aside={
        <Text font="legal" as="span" color="fgMuted" noWrap>
          {candidates.length}개 · {win === '52w' ? '52주' : '전체 이력'} 창
        </Text>
      }
      onClose={onClose}
    >
      <VStack gap={1} width="100%">
        {candidates.length === 0 ? (
          <Text font="body" as="p" color="fgMuted">
            담은 후보가 없어요 — 위 바에서 섹터·잔존(그리고 민평 대비 호가)을 넣고 「담기」를
            누르면 여기 쌓여요.
          </Text>
        ) : (
          <table className="sr-rv-table sr-rv-divided">
            <thead>
              <tr>
                <th className="sr-rv-th sr-rv-left">종목</th>
                <th className="sr-rv-th">Score</th>
                <th className="sr-rv-th">순위</th>
                <th className="sr-rv-th">캐리</th>
                <th className="sr-rv-th">롤</th>
                <th className="sr-rv-th">버퍼</th>
                <th className="sr-rv-th">한 달</th>
                {/* 두 축을 가르는 열 머리 — 왼쪽 여섯은 **버킷의 역사**이고
                    이 열만 **내가 받은 호가**다. 둘을 한 수로 합치지 않는다. */}
                <th className="sr-rv-th">내 호가</th>
                <th className="sr-rv-th" />
              </tr>
            </thead>
            <tbody>
              {sorted.map(({ c, out }) => (
                <tr key={c.id}>
                  <td className="sr-rv-td sr-rv-left">
                    <div className="sr-name-stack">
                      {out?.kind === 'hit' ? (
                        <button
                          type="button"
                          className="sr-rv-linkbtn"
                          aria-label={`${out.item.sectorLabel} ${out.item.tenor} 이력 단면 열기`}
                          onClick={() => onSelect(out.item)}
                        >
                          <Text font="label1" as="span" noWrap>
                            {out.item.sectorLabel} {out.item.tenor}
                          </Text>
                        </button>
                      ) : (
                        <Text font="label1" as="span" noWrap>
                          {c.sectorLabel} 잔존 {yr(c.ttm)}년
                        </Text>
                      )}
                      {/* 서브라인 — 입력 잔존과 빌려온 버킷의 **거리**를 적는다.
                          버킷 이름만 적으면 2.3년을 3Y 로 빌린 것이 안 보인다. */}
                      <Text font="legal" as="span" color="fgMuted" noWrap>
                        {out?.kind === 'hit'
                          ? `잔존 ${yr(c.ttm)}년 → ${out.item.tenor} 버킷${
                              out.gapYears > 0 ? ` (${yr(out.gapYears)}년 차이)` : ' (딱 맞아요)'
                            }`
                          : out?.side === 'below'
                            ? `H ${bounds.hMonths}개월 안에 만기 — 채점은 ${yr(out.edgeYears)}년 초과부터예요`
                            : `${out ? yr(out.edgeYears) : ''}년 초과 — 이 화면의 범위 밖이에요`}
                      </Text>
                    </div>
                  </td>
                  <td className="sr-rv-td">
                    {out?.kind === 'hit' && out.item.score != null
                      ? out.item.score.toFixed(0)
                      : '—'}
                  </td>
                  <td className="sr-rv-td">
                    {out?.kind === 'hit' && out.item.rank != null ? `${out.item.rank}위` : '—'}
                  </td>
                  {/* 단위는 **셀에** 붙인다 — 랭킹 표의 그 규약이다(실측 2026-10-02:
                      「한 달」만 bp 가 붙어 한 표 안에서 표기가 갈려 있었다). */}
                  <td className="sr-rv-td">
                    {out?.kind === 'hit' ? `${sig(out.item.carryBp)}bp` : '—'}
                  </td>
                  <td className="sr-rv-td">
                    {out?.kind === 'hit' ? `${sig(out.item.rollBp)}bp` : '—'}
                  </td>
                  <td className="sr-rv-td">
                    {out?.kind === 'hit' ? `${sig(out.item.bufferBp)}bp` : '—'}
                  </td>
                  <td className="sr-rv-td">
                    {out?.kind === 'hit' ? `${sig(out.item.trMonthBp)}bp` : '—'}
                  </td>
                  {/* 민평 대비 — 안 넣은 칸은 «—» 다(0 과 다른 사실). */}
                  <td className="sr-rv-td">
                    {c.quoteBp == null ? '—' : `민평 ${sig(c.quoteBp)}bp`}
                  </td>
                  <td className="sr-rv-td">
                    <button
                      type="button"
                      className="sr-rv-linkbtn"
                      aria-label={`${c.sectorLabel} 잔존 ${yr(c.ttm)}년 후보 치우기`}
                      onClick={() => onRemove(c.id)}
                    >
                      <Text font="legal" as="span" color="fgMuted" noWrap>
                        치우기
                      </Text>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {/* 문장은 토스체 — 짧고 쉬운 말. 명구는 의무(위 머리 주석). */}
        <HStack paddingX={2} paddingBottom={1}>
          <Text font="legal" as="p" color="fgMuted">
            투자판단이 아니라 RV 랭킹이에요 — 왼쪽 여섯 칸은 그 버킷이 평소보다 얼마나
            벌어졌는지고, 「내 호가」는 제가 받은 호가가 민평에서 얼마 떨어졌는지예요(매수
            기준 · + 면 그만큼 싸게 사는 거예요). 둘은 다른 질문이라 한 수로 합치지 않아요.
          </Text>
        </HStack>
      </VStack>
    </FloatingWindow>
  );
}
