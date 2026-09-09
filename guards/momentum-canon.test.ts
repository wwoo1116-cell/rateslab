/* Momentum 이 **이 리포의 문법**으로 서 있는가 [OWNER 2026-09-09 — 「기존 v2의
 * 문법을 충실히 따를 것」].
 *
 * ## 이 파일이 지는 명제 넷
 *
 * **부품을 새로 만들지 않았다.** 조건 바 한 칸은 `ui/Cond`, 열 머리 뜻풀이는
 * `ui/ThHelp`, 사실 스트립은 `ui/Stat`, 상태는 `ui/DataState`, 표는 CDS
 * `Table` + `ROW_H`. 같은 모양을 손으로 다시 만들면 한쪽만 낡는다(캐논 규칙 1).
 *
 * **강도 칸은 네 부품 한 벌이다.** 틴트 + 방향색 클래스 + 글리프 + 무부호 숫자.
 * 색 하나로만 방향을 말하면 WCAG 2.2 §1.4.1 을 어긴다.
 *
 * **룩백은 손잡이가 아니다.** 이 레인의 규율이 「룩백을 고르지 마라」이고(전진
 * 선택하면 7년 합 −3,230만), 셀렉트·알약을 두면 화면이 그 규율을 어기는 도구가
 * 된다. 다섯이 **열**로 선다.
 *
 * **등록된 북만 화면에 오른다.** 추세 다리의 신호는 `macross` 하나다 —
 * `tsmom`·`donchian` 은 `scripts/cta_validate.py` 의 PBO 격자 차원이지 이 북에
 * 안 든다. 그리고 두 다리를 **곱하지 않는다**(변조는 2026-09-09 NO-GO).
 */

import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments } from './_source';

const root = path.resolve(import.meta.dirname, '..');
const src = (rel: string) => stripComments(fs.readFileSync(path.join(root, rel), 'utf8'));
const raw = (rel: string) => fs.readFileSync(path.join(root, rel), 'utf8');

describe('Momentum 캐논', () => {
  const page = src('src/momentum/MomentumPage.tsx');

  it('공용 부품을 임포트한다 — 같은 것을 두 번 만들지 않는다', () => {
    for (const mod of [
      "@/ui/Cond",
      "@/ui/ThHelp",
      "@/ui/Stat",
      "@/ui/DataState",
      "@/table/rowHeight",
      "@/table/tint",
      "@/chart/TimeChart",
      "@coinbase/cds-web/tables",
      "@coinbase/cds-web/layout",
      "@coinbase/cds-web/typography",
    ]) {
      expect(page, mod).toContain(mod);
    }
  });

  it('행 높이는 ROW_H — 숫자를 다시 적지 않는다', () => {
    expect(page).toMatch(/height:\s*ROW_H/);
    expect(page).not.toMatch(/height:\s*60\b/);
  });

  it('강도 칸이 네 부품 한 벌이다', () => {
    for (const part of ['signalTint(', 'directionClass(', 'directionGlyph(', 'unsignedDelta(']) {
      expect(page, part).toContain(part);
    }
  });

  it('룩백이 손잡이가 아니라 열이다', () => {
    /* 서버가 목록을 주고 화면은 그 위를 돈다 — 고르는 컨트롤이 없다. */
    expect(page).toMatch(/board\.lookbacks\.map/);
    expect(page).not.toMatch(/sr-pillbtn/);
    expect(page).not.toMatch(/<Select/);
  });

  it('등록된 북만 오른다 — tsmom·donchian 은 화면에 없다', () => {
    expect(page).not.toMatch(/tsmom|donchian/);
    expect(src('src/momentum/api.ts')).not.toMatch(/tsmom|donchian/);
  });

  it('두 다리를 곱하지 않는다 — 화면에 결합 신호가 없다', () => {
    /* 변조(추세 × 매크로)는 NO-GO 였다. 화면이 그걸 몰래 채택하면 안 된다. */
    expect(page).not.toMatch(/composite\s*\*\s*macro|macro[^\n]*\*\s*composite/);
    expect(src('backend/app/momentum.py')).not.toMatch(/modulate|coef\(/);
  });

  it('명구 의무 — 이웃 둘과 같은 문법으로 한 줄이 선다', () => {
    expect(raw('src/momentum/MomentumPage.tsx')).toMatch(/단독 전략이 아니에요/);
  });

  /* ── 2026-09-09 채점 재점검이 남긴 불변식 셋 ─────────────────────────────
   *
   * MR 레인 진단(Phase 0)의 D2·D4 가 이 레인에도 올 수 있는 자리를 막는다.
   * D2 는 화면이 Ulcer 부호를 뒤집어 놓은 것이었고(`parts.tsx` 의 `-perf.ulcer`),
   * D4 는 원화 손익에 없는 자본 분모를 붙이려던 것이다. 오너 결정은
   * 「분모를 안 만든다 · Ulcer 는 MR 과 같은 잣대로」였다. */

  it('Ulcer 부호를 뒤집지 않는다 — 제곱해서 루트를 씌운 값이다', () => {
    expect(page).not.toMatch(/-\s*\w*\.?card\.ulcer|-\s*perf\.ulcer/);
    /* 서버 쪽도 같은 식이어야 한다. */
    expect(src('backend/app/momentum.py')).toMatch(/math\.sqrt\(sum\(d \* d for d in dd_path\)/);
  });

  it('원화 열은 «위험 맞춤» 짝을 갖는다 — 그냥 비교하면 덜 걸어서 덜 아픈 것이 이긴다', () => {
    for (const k of ['maxDrawdownVolMatched', 'ulcerVolMatched']) {
      expect(src('src/momentum/api.ts'), k).toContain(k);
    }
    expect(page).toContain('maxDrawdownVolMatched');
    expect(page).toContain('ulcerVolMatched');
  });

  it('없는 자본 분모를 지어내지 않는다 — 무차원 비율로 비교한다', () => {
    const py = src('backend/app/momentum.py');
    expect(py).not.toMatch(/AUM|capital_krw|equity_krw/i);
    /* 대신 무차원 Martin 이 있어야 한다 — 그게 분모 없이 비교하는 자리다. */
    expect(py).toMatch(/"martin"/);
    expect(page).toContain('l.card.martin');
  });

  it('말줄임·중간 줄바꿈 금지 규칙을 안 어긴다', () => {
    expect(page).not.toMatch(/text-overflow|overflow="truncate"|break-all|break-word/);
  });
});
