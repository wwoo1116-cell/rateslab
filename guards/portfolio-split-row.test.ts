/* 포트폴리오 — 트레이드별 기여·분해의 구조 핀 [OWNER 2026-10-01].
 *
 * > "손익에서 합계랑 분해랑 각각을 이제 트레이드 별로 분리해서 나눠주고"
 * > "전체수익이 5000이라고만 지금은 나와있는데, 1st Trade는 3000, 2nd Trade는 2000"
 * > "개시랑 체결 차이가 무슨 차이인지 설명해주고"
 *
 * 지키는 것 넷:
 *  ① 분해 칸은 **한 부품**이다 — 전체 스트립과 트레이드 줄이 `SplitStats` 를 같이 쓴다
 *    (두 벌이 되면 한쪽만 낡는다 — 캐논 §8).
 *  ② 가로지르는 줄의 `colSpan` 은 **표의 실제 열 수**와 같다. 손으로 센 수가 칸이
 *    늘어난 날 조용히 틀리는 것을 막는다(백테스트 분해 격자 판례 2026-09-29).
 *  ③ **개시와 체결 차이는 서로 다른 말로 설명된다** — 시간 대 가격. 둘 다 「진입 때」
 *    생겨서 헷갈리는 칸이고, 설명이 사라지면 그 혼동이 돌아온다.
 *  ④ 기여 칸은 트레이드 **이름을 `Stat.label` 에 넣지 않는다** — 그 활자(caption)에
 *    대문자 변환이 걸려 「2nd Trader」가 「2ND TRADER」가 된다(실측 2026-09-28).
 */
import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const SRC = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'pm', 'PortfolioPage.tsx'), 'utf8',
);

describe('분해 칸은 한 부품이다', () => {
  it('전체 스트립과 트레이드 줄이 같은 `SplitStats` 를 쓴다', () => {
    expect(SRC).toMatch(/function SplitStats\(/);
    // 두 호출부가 다 있어야 한다 — 하나만 남으면 다른 쪽이 손으로 베낀 것이다.
    const uses = SRC.match(/<SplitStats\b/g) ?? [];
    expect(uses.length).toBe(2);
    expect(SRC).toMatch(/function PnlSplit\([\s\S]*?<SplitStats/);
    expect(SRC).toMatch(/function TradeSplitRow\([\s\S]*?<SplitStats/);
  });
});

describe('가로지르는 줄의 폭 = 표의 열 수', () => {
  it('`POS_COLS` 가 헤더의 `as="th"` 개수와 같다', () => {
    const declared = Number(/const POS_COLS = (\d+);/.exec(SRC)?.[1]);
    expect(Number.isFinite(declared)).toBe(true);
    const header = /<TableHeader>([\s\S]*?)<\/TableHeader>/.exec(SRC)?.[1] ?? '';
    expect(header).not.toBe('');
    const ths = header.match(/as="th"/g) ?? [];
    expect(ths.length, '표의 열을 늘렸으면 POS_COLS 도 같이 늘려야 해요').toBe(declared);
  });

  it('분해 줄은 상수를 지나간다 — 숫자를 손으로 다시 적지 않는다', () => {
    expect(SRC).toMatch(/<TradeSplitRow[^>]*cols=\{POS_COLS\}/);
    expect(SRC).toMatch(/colSpan=\{cols\}/);
  });
});

describe('개시 ≠ 체결 차이 — 설명이 화면에 있다', () => {
  it('개시는 **시간**, 체결 차이는 **가격**으로 설명된다', () => {
    const startup = /label="개시"[\s\S]{0,220}?note="([^"]+)"/.exec(SRC)?.[1] ?? '';
    const exec = /label="체결 차이"[\s\S]{0,220}?note="([^"]+)"/.exec(SRC)?.[1] ?? '';
    expect(startup, '개시 칸에 설명이 없어요').not.toBe('');
    expect(exec, '체결 차이 칸에 설명이 없어요').not.toBe('');
    // 두 설명이 서로 달라야 한다 — 같은 말이면 구분이 안 된다.
    expect(startup).not.toBe(exec);
    expect(startup).toMatch(/발효일|한 밤|시간/);
    expect(exec).toMatch(/종가|가격/);
  });
});

describe('기여 칸 — 이름은 대문자로 바뀌면 안 된다', () => {
  it('트레이드 이름을 `Stat.label` 로 넘기지 않는다', () => {
    /* 구역은 **이름으로** 자른다 — 중괄호로 자르면 구조분해 props 의 `}) {` 가
       열 0 에 서서 함수가 시작하자마자 끊긴다(첫 판에서 그렇게 틀렸다). */
    const from = SRC.indexOf('function Contrib(');
    const to = SRC.indexOf('function PortfolioStrip(');
    expect(from, 'Contrib 부품이 없어요').toBeGreaterThan(-1);
    expect(to).toBeGreaterThan(from);
    const block = SRC.slice(from, to);
    // `Stat` 을 쓰면 label 이 caption 이라 이름이 대문자가 된다.
    expect(block).not.toMatch(/<Stat\b/);
    expect(block).toMatch(/font="label2"/);
  });

  it('기여 칸은 묶음이 둘 이상일 때만 선다', () => {
    expect(SRC).toMatch(/showContrib/);
    expect(SRC).toMatch(/groups\.length > 1/);
  });
});
