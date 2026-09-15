/* 한국어 조사 — 받침으로 갈리는 자리를 **한 곳**에서 정한다.
 *
 * 왜 이 파일이 생겼나 [2026-09-15 디자인 점검]. 화면 셋이 각자 다른 방법으로
 * 같은 문제를 풀고 있었고, 셋 다 틀렸다.
 *
 *   `ui/DataState.tsx`   `{what}을` 로 고정 → 「시장 데이터**을** 불러오지 못했어요」
 *   `lab/…/note.ts`      `${what}을` 로 고정 → what 이 「+25bp」면 「bp**을**」
 *   `ui/BottomStrip.tsx` `${label}(으)로` 회피형 → 낭독기가 「십와이 **으로** 이동」
 *
 * 조사는 앞말의 **소리**가 정한다. 그래서 한글이 아닌 꼬리(영문·숫자)는 한국어
 * 독음의 받침으로 판정한다 — 「10Y」는 «십와이» 라 받침이 없고(를·로),
 * 「Momentum」은 «모멘텀» 이라 받침이 있다(을·으로).
 *
 * ⚠ 완전한 한국어 형태소 분석이 아니다. 이 앱이 실제로 넣는 말(계열 이름·만기·
 * 단위)을 덮는 것이 목표이고, 못 읽는 꼬리는 **받침 없음**으로 떨어진다 —
 * 틀리더라도 「데이터를」쪽이 「데이터을」보다 덜 어색하기 때문이다.
 */

/** 앞말의 마지막 소리에 받침이 있나. 판정 못 하면 `null`. */
function batchim(word: string): { has: boolean; rieul: boolean } | null {
  const s = word.trimEnd();
  if (!s) return null;
  const ch = s[s.length - 1];
  const code = ch.charCodeAt(0);

  // 한글 음절 — (코드 − 0xAC00) % 28 이 종성 인덱스다. 8 이 ㄹ.
  if (code >= 0xac00 && code <= 0xd7a3) {
    const jong = (code - 0xac00) % 28;
    return { has: jong !== 0, rieul: jong === 8 };
  }

  // 숫자 — 한국어 독음의 받침. 1·7·8 은 ㄹ(일·칠·팔).
  if (ch >= '0' && ch <= '9') {
    const RIEUL = new Set(['1', '7', '8']);
    const HAS = new Set(['0', '1', '3', '6', '7', '8']); // 영·일·삼·육·칠·팔
    return { has: HAS.has(ch), rieul: RIEUL.has(ch) };
  }

  // 영문 — 알파벳 한국어 독음의 받침. L·R 은 ㄹ(엘·알), M·N 은 ㅁ·ㄴ, Z 는 제트.
  const up = ch.toUpperCase();
  if (up >= 'A' && up <= 'Z') {
    const RIEUL = new Set(['L', 'R']);
    const HAS = new Set(['L', 'R', 'M', 'N', 'Z']);
    return { has: HAS.has(up), rieul: RIEUL.has(up) };
  }

  return null; // 기호로 끝나면 못 읽는다
}

/** 앞말에 맞는 조사를 고른다. 받침을 못 읽으면 **받침 없음** 쪽으로 떨어진다. */
function pick(word: string, withBatchim: string, withoutBatchim: string): string {
  const b = batchim(word);
  return b?.has ? withBatchim : withoutBatchim;
}

/** 을 / 를 — 목적격. `${what}${eul(what)} 불러오지 못했어요` */
export function eul(word: string): string {
  return pick(word, '을', '를');
}

/** 이 / 가 — 주격. */
export function i(word: string): string {
  return pick(word, '이', '가');
}

/** 은 / 는 — 보조사. */
export function eun(word: string): string {
  return pick(word, '은', '는');
}

/** 과 / 와 — 접속. */
export function gwa(word: string): string {
  return pick(word, '과', '와');
}

/** 으로 / 로 — 방향. **ㄹ 받침은 「로」다**(「10Y로」가 아니라 「1Y로」처럼). */
export function euro(word: string): string {
  const b = batchim(word);
  return b?.has && !b.rieul ? '으로' : '로';
}

/** 앞말과 조사를 붙여 돌려준다 — `josa('시장 데이터', eul)` → `'시장 데이터를'`. */
export function withJosa(word: string, f: (w: string) => string): string {
  return `${word}${f(word)}`;
}
