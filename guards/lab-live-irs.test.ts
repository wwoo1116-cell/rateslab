/* 실시간 IRS(Lab) 의 산술 핀 [OWNER 2026-10-01].
 *
 * 지키는 것: ① 일중 = **(지금 − 종가) × 100** ② 종가에 없는 만기는 **빈칸이지
 * 0 이 아니다** ③ 콜(`1D`)은 커브 만기가 아니다 ④ 선물 베이시스의 **부호 규약은
 * 스왑 − 선물**(BSS·FSW·ASW 의 그것)이고 짝이 없으면 안 선다 ⑤ 낡음 사유는
 * **서버가 적어 준 것**을 그대로 옮긴다(화면이 두 번째 문턱을 두지 않는다).
 *
 * `mergeIrs` 가 순수 함수라 서버·SQL 없이 전부 잰다 — `paperlive.py` 가
 * `irs_levels` 를 SQL 밖으로 떼어 낸 그 이유와 같다.
 */
import { describe, expect, it } from 'vitest';

import { fmtBp } from '../src/lib/format';
import { mergeIrs, type ClosePayload, type LivePayload } from '../src/lab/irs/api';

function live(over: Partial<LivePayload> = {}): LivePayload {
  return {
    available: true,
    asof: '15:49:25',
    why: null,
    sources: [
      {
        name: 'IRS',
        table: 'infomax_API.irs_infomax',
        asof: '2026-10-01 15:49:25',
        ageMin: 0.0,
      },
    ],
    levels: [
      { kind: 'irs', tenor: '6M', level: 3.42, at: '15:49:25', source: 'IRS' },
      { kind: 'irs', tenor: '3Y', level: 4.0675, at: '15:49:25', source: 'IRS' },
      { kind: 'irs', tenor: '12Y', level: 4.2475, at: '15:49:25', source: 'IRS' },
    ],
    ...over,
  };
}

const CLOSE: ClosePayload = {
  asof: '2026-09-30',
  outrights: [
    { id: '1D', label: 'Call (1D)', now: 3.073 },
    { id: '6M', label: 'IRS 6M', now: 3.4275 },
    { id: '3Y', label: 'IRS 3Y', now: 4.0 },
    // 12Y 는 종가 표시 집합에 없다 — 라이브에만 있는 만기.
  ],
};

describe('일중 = 지금 − 종가', () => {
  it('bp 로 환산하되 **깎지 않는다** — 자리수는 표기가 한 번만 정한다', () => {
    const b = mergeIrs(live(), CLOSE);
    const six = b.rows.find((r) => r.tenor === '6M')!;
    expect(six.moveBp).toBeCloseTo((3.42 - 3.4275) * 100, 10);
    const three = b.rows.find((r) => r.tenor === '3Y')!;
    expect(three.moveBp).toBeCloseTo((4.0675 - 4.0) * 100, 10);
    /* ★원값을 들고 있어야 보이는 사실: `4.0675 − 4.0` 은 이진수로 정확히
       `0.0675` 가 아니라서 ×100 이 6.75 가 **아니다**(6.7499…). 그래서 표기는
       6.8 이 아니라 6.7 이다 — 미리 깎았으면 이 사실이 안 보였다. */
    expect(three.moveBp).not.toBe(6.75);
    expect(fmtBp(three.moveBp)).toBe('+6.7');
    expect(fmtBp(six.moveBp)).toBe(`${'−'}0.8`);
  });

  it('종가에 없는 만기는 빈칸이다 — 0 과 모름은 딴 사실이다', () => {
    const b = mergeIrs(live(), CLOSE);
    const twelve = b.rows.find((r) => r.tenor === '12Y')!;
    expect(twelve.close).toBeNull();
    expect(twelve.moveBp).toBeNull();
    // 그래도 「지금」은 선다 — 라이브가 주인공이다.
    expect(twelve.now).toBe(4.2475);
  });

  it('종가 묶음이 통째로 없어도 화면이 선다 — Δ 칸만 빈다', () => {
    const b = mergeIrs(live(), null);
    expect(b.rows).toHaveLength(3);
    expect(b.rows.every((r) => r.close === null && r.moveBp === null)).toBe(true);
    expect(b.closeAsof).toBeNull();
  });

  it('콜(1D)은 커브 만기가 아니다 — 종가 매칭에 안 들어간다', () => {
    const withCall = live({
      levels: [{ kind: 'irs', tenor: '1D', level: 3.1, at: '15:49:25', source: 'IRS' }],
    });
    const b = mergeIrs(withCall, CLOSE);
    // 라이브에 1D 가 와도 종가 3.073 과 짝지어지지 않는다.
    expect(b.rows[0]?.close).toBeNull();
    expect(b.rows[0]?.moveBp).toBeNull();
  });
});

describe('선물 베이시스 — 스왑 − 선물', () => {
  it('부호 규약은 스왑 − 국채선물 내재다', () => {
    const b = mergeIrs(
      live({
        levels: [
          { kind: 'irs', tenor: '3Y', level: 4.0675, at: '15:49:25', source: 'IRS' },
          { kind: 'fut', tenor: '3Y', level: 4.1552, at: '15:45:02', source: '국채선물' },
        ],
      }),
      CLOSE,
    );
    expect(b.futBasis).toHaveLength(1);
    // (4.0675 − 4.1552) × 100 = −8.77 → 표기 −8.8. 부호를 뒤집으면 빨개진다.
    expect(b.futBasis[0]?.tenor).toBe('3Y');
    expect(b.futBasis[0]?.bp).toBeCloseTo((4.0675 - 4.1552) * 100, 10);
    expect(fmtBp(b.futBasis[0]?.bp ?? null)).toBe(`${'−'}8.8`);
  });

  it('짝이 없으면 안 세운다 — 한쪽만으로는 베이시스가 아니다', () => {
    const b = mergeIrs(
      live({
        levels: [{ kind: 'fut', tenor: '10Y', level: 4.4842, at: '15:45:02', source: '국채선물' }],
      }),
      CLOSE,
    );
    expect(b.futBasis).toHaveLength(0);
    // 선물은 IRS 행으로도 안 샌다 — kind 가 다르다.
    expect(b.rows).toHaveLength(0);
  });
});

describe('낡음은 서버가 판정한다', () => {
  it('값이 안 실리면 사유를 그대로 옮긴다 — 화면이 문턱을 다시 두지 않는다', () => {
    const stale = live({
      levels: [],
      sources: [
        {
          name: 'IRS',
          table: 'infomax_API.irs_infomax',
          asof: '2026-10-01 09:10:00',
          ageMin: 395.2,
          why: '395분 전 값이에요 — 지금이라고 부르지 않아요',
        },
      ],
    });
    const b = mergeIrs(stale, CLOSE);
    expect(b.rows).toHaveLength(0);
    expect(b.why).toBe('395분 전 값이에요 — 지금이라고 부르지 않아요');
    expect(b.liveAgeMin).toBe(395.2);
    expect(b.liveAsof).toBe('2026-10-01 09:10:00');
  });

  it('출처 사유가 없으면 페이로드의 사유를 든다', () => {
    const b = mergeIrs(
      live({ levels: [], sources: [], why: '장중 시세를 못 읽었어요 — 연결 실패' }),
      CLOSE,
    );
    expect(b.why).toBe('장중 시세를 못 읽었어요 — 연결 실패');
  });
});
