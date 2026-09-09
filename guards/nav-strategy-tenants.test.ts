/* Strategy 의 세입자 [OWNER 2026-08-24].
 *
 * 「Strategy Tab에 곧 하나 다른 전략을 도입할 예정이라서 Credit RV라는 이름으로
 * 지금 있던 탭을 분리해서 다른 Backtest나 Lab과 같은 형태로 분리해두자」.
 *
 * ## 이 파일이 지는 명제
 *
 * **Lab 과 같은 기계여야 한다.** 두 섹션이 같은 일(여러 화면을 한 섹션 아래
 * 두기)을 다른 방식으로 하면, 셋째가 생기는 날 어느 쪽을 따를지가 취향 문제가
 * 된다. 그래서 여기서는 두 기계의 **모양이 같은지**를 잰다.
 *
 * **예전 링크가 안 죽어야 한다.** `?g=strategy` 는 세입자 키가 없는 주소이고,
 * 그게 가리키던 화면(RV Analysis)에 그대로 떨어져야 한다.
 */

import { describe, expect, it } from 'vitest';

import {
  DEFAULT_LAB,
  DEFAULT_STRATEGY,
  LAB_ITEMS,
  PANELED,
  SECTIONS,
  STRATEGY_ITEMS,
  isStrategyId,
  resolveLab,
  resolveStrategy,
  sectionOf,
} from '../src/ui/nav';

describe('Strategy 세입자', () => {
  it('세입자 셋 — Credit RV · Mean Reversion · Momentum(2026-09-09 입주)이다', () => {
    expect(STRATEGY_ITEMS.map((i) => i.id)).toEqual([
      'credit-rv',
      'mean-reversion',
      'momentum',
    ]);
    expect(STRATEGY_ITEMS[0]!.label).toBe('Credit RV');
    expect(STRATEGY_ITEMS[1]!.label).toBe('Mean Reversion');
    expect(STRATEGY_ITEMS[2]!.label).toBe('Momentum');
    /* 기본은 첫 세입자 그대로 — 예전 `?g=strategy` 링크가 가리키던 화면이다. */
    expect(DEFAULT_STRATEGY).toBe('credit-rv');
  });

  it('세입자마다 라벨·설명·글리프를 다 든다 — Lab 과 같은 모양이다', () => {
    for (const it_ of STRATEGY_ITEMS) {
      expect(it_.label.length, it_.id).toBeGreaterThan(0);
      expect(it_.desc.length, it_.id).toBeGreaterThan(8);
      expect(it_.glyph.length, it_.id).toBe(1);
    }
    /* 키가 겹치면 URL 에서 어느 섹션의 것인지가 사람 눈으로 안 갈린다. */
    const labIds = new Set(LAB_ITEMS.map((i) => i.id as string));
    for (const it_ of STRATEGY_ITEMS) expect(labIds.has(it_.id)).toBe(false);
  });

  it('예전 `?g=strategy` 링크가 안 죽는다 — 키가 없으면 기본 세입자다', () => {
    expect(resolveStrategy(undefined)).toBe(DEFAULT_STRATEGY);
    expect(resolveStrategy('')).toBe(DEFAULT_STRATEGY);
  });

  it('모르는 키도 기본으로 떨어진다 — Lab 과 같은 규율이다', () => {
    expect(resolveStrategy('없는전략')).toBe(DEFAULT_STRATEGY);
    expect(resolveLab('없는세입자')).toBe(DEFAULT_LAB);
  });

  it('아는 키는 그대로 산다', () => {
    for (const it_ of STRATEGY_ITEMS) {
      expect(isStrategyId(it_.id)).toBe(true);
      expect(resolveStrategy(it_.id)).toBe(it_.id);
    }
  });

  /* 세입자가 하나인 동안은 패널을 안 연다 — 이 리포의 규칙이
     「목적지가 하나면 버튼이지 메뉴가 아니다」 이기 때문이다. 둘째가 들어오면
     이 시험이 **먼저 빨개져서** `PANELED` 에 한 낱말을 더하라고 말한다. */
  it('세입자 수와 메가 패널 여부가 어긋나지 않는다', () => {
    const paneled = PANELED.includes('strategy');
    expect(paneled).toBe(STRATEGY_ITEMS.length > 1);
  });

  it('Lab 도 같은 규칙 아래 있다 — 한쪽만 예외면 그건 규칙이 아니다', () => {
    expect(PANELED.includes('lab')).toBe(LAB_ITEMS.length > 1);
  });

  it('섹션은 여전히 유도값이다 — Strategy 가 두 번째 상태를 안 만든다', () => {
    expect(sectionOf('strategy')).toBe('strategy');
    expect(SECTIONS.find((s) => s.id === 'strategy')?.tab).toBe('strategy');
  });
});
