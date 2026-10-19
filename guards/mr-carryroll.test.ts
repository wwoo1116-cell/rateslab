/* 계획면 카드의 **3M 캐리·롤** 칸과 그 칸이 밟은 함정들 [2026-10-19].
 *
 * ## 왜 이 가드가 있나
 *
 * 백엔드는 2026-10-16 에 `carryRoll` 을 싣기 시작했는데(`mrplan.py:497`,
 * 커밋 `3827c702`) **프런트가 사흘 동안 그 글자를 한 번도 안 썼다** — 계획면
 * 21/25 계열에 값이 실려 나가는데 화면에는 칸이 없었다. 「페이로드에 있다」와
 * 「화면에 있다」가 다른 말이라는 것이 이 레인의 교훈이고, 이 파일이 그 거리를
 * 재는 자다.
 *
 * ## 지는 명제 넷
 *
 *   ① **부호를 적는다.** 캐리·롤은 「얼마나 더 가야 하나」가 아니라 「시간이
 *      돈을 주나 빼앗나」라서 `gap`(거리·무부호)을 쓰면 안 된다.
 *   ② **자릿수가 둘이다.** 분기 몫과 하루 몫은 크기가 100배 달라 같은 자로
 *      못 적는다.
 *   ③ **빈 자리는 비운다.** 안 서는 계열은 `—` 이고 `0` 이 아니다.
 *   ④ **채택 기준 이름을 박지 않는다.** 서버가 `cond.basis` 로 말한다.
 */

import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { signedBp } from '../src/mr/planText';
import { stripComments } from './_source';

const ROOT = path.join(__dirname, '..');
const MR_DIR = path.join(ROOT, 'src', 'mr');
const PAGE = fs.readFileSync(path.join(MR_DIR, 'MrPage.tsx'), 'utf8');
const CODE = stripComments(PAGE);

/** U+2212. ASCII 하이픈이 아니다 — 숫자 칸이 tabular 라 폭이 맞는 쪽을 쓴다. */
const MINUS = '−';

describe('① 캐리·롤은 부호를 적는다', () => {
  /* 실측으로 밟은 자리: BSS-1Y 의 `thetaBp` 는 −0.698 인데 `gap` 으로 적어
     화면에 `0.7bp` 가 서고 **색만** 파랬다. 세 수(캐리 +4.8 · 롤 −5.5 ·
     합 −0.7)가 눈으로 안 맞아떨어졌다. */
  it('음수는 U+2212 를 달고 나온다', () => {
    const got = signedBp(-0.698, 'bp');
    expect(got.startsWith(MINUS), `하이픈이 아니라 U+2212 여야 해요: ${got}`).toBe(true);
    expect(got.charCodeAt(0)).toBe(0x2212);
  });

  it('양수는 + 를 달고, 0 은 아무것도 안 단다', () => {
    expect(signedBp(6.408, 'bp')).toBe('+6.4bp');
    expect(signedBp(0, 'bp')).toBe('0.0bp');
  });

  it('없는 값은 —', () => {
    expect(signedBp(null, 'bp')).toBe('—');
    expect(signedBp(undefined, 'bp')).toBe('—');
  });

  it('세 수가 눈으로 맞아떨어진다 — 캐리 + 롤 = 합', () => {
    /* 서식이 부호를 떼면 이 덧셈이 화면에서 깨진다. 그것이 ①의 하중이다. */
    expect(signedBp(4.845, 'bp')).toBe('+4.8bp');
    expect(signedBp(-5.543, 'bp')).toBe(`${MINUS}5.5bp`);
    expect(signedBp(4.845 - 5.543, 'bp')).toBe(`${MINUS}0.7bp`);
  });

  it('카드가 `gap`(무부호) 이 아니라 부호 자를 쓴다', () => {
    const col = CODE.slice(CODE.indexOf('function CarryRollColumn'));
    const body = col.slice(0, col.indexOf('function PlanStats'));
    expect(body, '캐리·롤 칸이 무부호 자(`gp`) 를 쓰고 있어요').not.toMatch(/\bgp\(/);
    expect(body).toMatch(/sg\(cr\.carryBp\)/);
    expect(body).toMatch(/sg\(cr\.rollBp\)/);
    expect(body).toMatch(/sg\(cr\.thetaBp\)/);
  });
});

describe('② 분기 몫과 하루 몫은 자가 다르다', () => {
  /* `signedBp` 는 계열 서식(`fmtLevel`)이라 bp 를 **소수 한 자리**로 끊는다.
     하루 몫 0.050 을 그 자로 적으면 `+0.0bp` 로 뭉개진다 — 실측으로 밟았다. */
  it('계열 자로 하루 몫을 적으면 뭉개진다 (그래서 따로 쓴다)', () => {
    expect(signedBp(0.04987, 'bp')).toBe('+0.0bp');
  });

  it('하루 칸은 소수 셋으로 적는다', () => {
    expect(CODE).toMatch(/toFixed\(3\)}bp/);
  });
});

describe('③ 안 서는 계열은 비운다 — 0 이 아니다', () => {
  it('`carryRoll == null` 가지가 있고 — 를 세운다', () => {
    expect(CODE).toMatch(/const cr = r\.carryRoll;/);
    expect(CODE).toMatch(/if \(cr == null\)/);
    const nullBranch = CODE.slice(CODE.indexOf('if (cr == null)'));
    const head = nullBranch.slice(0, nullBranch.indexOf('</StatColumn>'));
    expect(head, '빈 자리에 숫자를 채우고 있어요').toMatch(/value=\{MINUS\}/);
    expect(head).not.toMatch(/value="0/);
  });

  it('칼럼 자체는 지우지 않는다 — 빈 자리도 자리다', () => {
    const nullBranch = CODE.slice(CODE.indexOf('if (cr == null)'));
    expect(nullBranch.slice(0, 400)).toMatch(/<StatColumn title="3M 캐리·롤">/);
  });
});

describe('④ 채택 기준 이름을 박지 않는다', () => {
  /* 2026-10-15 에 `PLAN_RANK_KEY` 가 `cdarRatio → calmar` 로 갔는데 화면 두
     자리가 「CDaR 비」를 글자로 들고 있었다. 한 카드가 「고른 기준 CDaR 비」라
     적고 바로 아래에서 「채택 기준 (Calmar)」이라 적었다 — 같은 화면이 스스로를
     반박한 것이다. 라벨은 `MR_RANK_KEYS` 한 벌에서만 난다. */
  /* 범위는 **계획면 한 파일**이다. 「CDaR 비」라는 글자가 정당한 자리가 둘 있다:
     `api.ts:MR_RANK_KEYS` 의 라벨 정의와, `OptimizePane.tsx` 의 격자 **열 머리**
     (그 열은 실제로 CDaR 비라는 지표를 보여 준다 — 채택 기준 이름이 아니다).
     결함이 있던 곳은 계획면이고, 되돌아올 곳도 거기다.
     ⚠ 남은 중복 하나: `OptimizePane.tsx:63` 이 `MR_RANK_KEYS` 의 라벨을 제 표에
     다시 적는다. 오늘 결함과 다른 과(科)라 안 건드렸다. */
  it('MrPage 에 「CDaR 비」가 글자로 안 박혀 있다', () => {
    expect(CODE, '계획면이 채택 기준 이름을 글자로 들고 있어요 — cond.basis 를 읽으세요')
      .not.toContain('CDaR 비');
  });

  it('카드와 조건 스트립이 서버가 준 기준을 읽는다', () => {
    expect(CODE).toMatch(/function rankLabel/);
    expect(CODE).toMatch(/rankLabel\(r\.cond\.basis\)/);
    expect(CODE).toMatch(/rankLabel\(plan\.params\.rankKey\)/);
  });
});
