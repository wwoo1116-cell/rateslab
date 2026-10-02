/* Risk Management — 거래 간 상관 히트맵의 구조 핀 [OWNER 2026-10-02].
 *
 * > "거래별 Correlation 계산해주는거 가능?"
 * > "그냥 포트폴리오 탭에 Risk Management로 해서 Heatmap으로 구현 가능?"
 *
 * 지키는 것 여섯:
 *  ① **§16 — 화면은 상관을 안 센다.** 서버(`/api/paper/risk`)가 행렬도 n 도 창도
 *    낸다. 화면에 통계 산술(sqrt·reduce)이 들어오면 같은 북에 두 수가 선다.
 *  ② **색만으로 말하지 않는다.** 칸마다 수를 찍는다 — 틴트는 거드는 채널이지
 *    유일한 채널이 아니다(색각·인쇄·강제색).
 *  ③ **틴트 위 글자는 잉크다.** 같은 색조로 칠하면 글자가 배경에 먹힌다 —
 *    `theme/tint.ts` 가 실측으로 「어떤 농도에서도 4.5:1 을 못 넘는다」를 적어 뒀다.
 *  ④ **발산 스케일은 1 로 고정.** 표 안 최댓값으로 정규화하면 「+0.2 뿐인 북」이
 *    「+0.9 인 북」과 같은 진하기로 보여 두 북을 비교할 수 없다.
 *  ⑤ **대각선은 안 칠한다** — 자기 자신과의 상관 1 은 사실이 아니라 항등식이다.
 *  ⑥ **「무엇의 상관인가」는 서버 말을 옮긴다**(`basis`). 화면이 지어내면 서버가
 *    기준을 바꾼 날 화면만 옛말을 한다.
 */
import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const SRC = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'pm', 'RiskHeatmap.tsx'), 'utf8',
);
const API = fs.readFileSync(path.join(__dirname, '..', 'src', 'pm', 'api.ts'), 'utf8');
const PAGE = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'pm', 'PortfolioPage.tsx'), 'utf8',
);

describe('§16 — 상관은 서버가 센다', () => {
  it('화면에 통계 산술이 없다', () => {
    expect(SRC, '화면이 상관을 다시 세면 같은 북에 두 수가 선다')
      .not.toMatch(/Math\.sqrt|\.reduce\(/);
  });

  it('행렬·n·창·사유를 전부 서버에서 받는다', () => {
    for (const k of ['matrix', 'n', 'minN', 'excluded', 'basis']) {
      expect(API, `응답에 ${k} 가 있어야 한다`).toMatch(new RegExp(`\\b${k}\\b`));
    }
    expect(SRC).toMatch(/got\?\.matrix/);
  });

  it('못 잰 칸은 `null` 이다 — 0 이 아니다', () => {
    // 타입이 `number | null` 이어야 「0 과 못 잼」이 섞이지 않는다.
    expect(API).toMatch(/matrix:\s*\(number \| null\)\[\]\[\]/);
    expect(SRC, '«—» 로 적는다').toMatch(/v == null \? '—'/);
  });
});

describe('히트맵의 색 규율', () => {
  it('색만으로 말하지 않는다 — 칸에 수를 찍는다', () => {
    expect(SRC).toMatch(/\{self \? '1\.00' : rho\(v\)\}/);
  });

  it('발산 틴트는 캐논 한 곳에서 오고 스케일은 1 로 고정이다', () => {
    expect(SRC).toMatch(/import \{ tintFor \} from '@\/theme\/tint'/);
    expect(SRC, '|ρ| ≤ 1 이 자연 상한이다 — 표마다 기준이 달라지면 안 된다')
      .toMatch(/tintFor\(v \?\? 0, 1\)/);
  });

  it('틴트 위 글자에 방향색을 쓰지 않는다', () => {
    /* ⚠주석이 아니라 **코드**만 본다 — 이 파일의 머리 주석이 색 규율을 설명하며
       토큰 이름을 적고 있어서, 소스 전체를 훑으면 그 설명이 걸린다(실측). */
    expect(SRC, '방향색 함수를 쓰면 글자가 배경에 먹힌다').not.toMatch(/directionVar/);
    expect(SRC, '방향색 클래스는 틴트가 없는 곳 전용이다')
      .not.toMatch(/className=["'`][^"'`]*sr-(up|down)/);
    expect(SRC, '칸 글자는 잉크다 — 색 prop 을 안 준다(대각선 뮤트만 예외)')
      .toMatch(/color=\{self \? 'fgMuted' : undefined\}/);
  });

  it('대각선은 안 칠한다', () => {
    expect(SRC).toMatch(/self \? undefined : \{ background: tintFor/);
  });

  it('칸마다 짚을 수 있는 설명이 붙는다', () => {
    expect(SRC).toMatch(/title=\{self/);
  });
});

describe('창과 자리', () => {
  it('창은 셋이고 1년을 넘지 않는다 — 그보다 길면 엔진 선이 다운샘플된다', () => {
    const ids = [...SRC.matchAll(/id: '(\w+)', label:/g)].map((m) => m[1]);
    expect(ids).toEqual(['3m', '6m', '1y']);
    expect(API).toMatch(/RiskWindow = '3m' \| '6m' \| '1y'/);
  });

  it('포트폴리오 탭에 서고, 포지션 카드 **아래**다', () => {
    expect(PAGE).toMatch(/<RiskHeatmap \/>/);
    const risk = PAGE.indexOf('<RiskHeatmap />');
    const pos = PAGE.indexOf('>포지션</Text>');
    expect(pos, '포지션 카드가 있어야 한다').toBeGreaterThan(-1);
    expect(risk, '「무엇을 들고 있나」를 읽은 다음에 오는 질문이다').toBeGreaterThan(pos);
  });

  it('거래가 둘 미만이면 행렬 대신 사유가 선다', () => {
    expect(SRC).toMatch(/trades\.length < 2/);
    expect(SRC).toMatch(/거래가 둘 이상이어야/);
  });

  it('행렬에서 뺀 거래를 사유와 함께 적는다', () => {
    expect(SRC).toMatch(/excluded/);
    expect(SRC).toMatch(/\$\{e\.label\} — \$\{e\.why\}/);
  });
});
