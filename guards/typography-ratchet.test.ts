import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';
import { stripComments } from './_source';

/**
 * 타이포 shorthand 는 **늘어날 수 없다** — 래칫.
 *
 * CDS 9.15 에서 `TextCaption`/`TextLegal`/`TextLabel1·2`/`TextBody`/`TextTitle*`/
 * `TextHeadline`/`TextDisplay*` 는 전부 `@deprecated` 이고, 대체는 `Text font="…"`
 * 하나다. 시각은 동일해서 지금 화면은 멀쩡하고, 그래서 이 부채는 **조용히
 * 자란다** — 새 컴포넌트를 쓸 때마다 손이 기억하는 쪽으로 손이 간다.
 *
 * CLAUDE.md 의 규칙이 정확히 그것이다: "새 코드에서 추가 사용 금지, 일괄
 * 마이그레이션은 CDS 메이저 승급 전에 별도 레인으로". 일괄 교체는 이 패스의
 * 크기가 아니지만, **한도를 못 박는 것**은 지금 할 수 있다.
 *
 * 그래서 이 가드는 개수의 상한이다. 지금 수를 천장으로 박아 두고, 새 사용이
 * 하나라도 늘면 실패한다. 줄어들면 — 마이그레이션 레인이 열려서 진짜로 줄면 —
 * 이 상수를 내려 적는 것이 그 레인의 마지막 커밋이다. 절대 올리지 않는다.
 *
 * ── 왜 주석을 걷어내나 ──────────────────────────────────────────────────────
 * 이 리포의 가드는 산문에 네 번 속았다(color-source 의 기록). 여기서는 여는
 * 태그(`<TextCaption`)만 세므로 산문 속 이름은 애초에 안 걸리지만, 주석 안의
 * **예시 JSX** 는 걸린다 — 그건 화면을 안 그리므로 먼저 지운다.
 */

const SRC = path.resolve(import.meta.dirname, '../src');

/** CDS 가 `@deprecated` 로 표시한 타이포 shorthand 전부. */
const SHORTHAND =
  /<(TextDisplay\d|TextTitle\d|TextHeadline|TextBody|TextLabel\d|TextCaption|TextLegal)\b/g;

/** 현재 수. **오직 내려갈 수만 있다.**
 *
 *  251 → **231** [2026-09-21]. 떠 있는 리드아웃 카드를 그림 위 고정 줄로 옮기면서
 *  여섯 표면의 `TextLabel2`·`TextLegal` 줄이 공용 부품(`ChartReadoutStrip` 안의
 *  `Text font="label2"`)으로 빨려 들어갔다 — 마이그레이션이 아니라 **부품화**의
 *  부수 효과다. 래칫이 그걸 세어서 내려 적으라고 했고, 이 줄이 그 기록이다. */
const CEILING = 231;


function tsxFiles(dir: string, out: string[] = []): string[] {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) tsxFiles(p, out);
    else if (e.name.endsWith('.tsx')) out.push(p);
  }
  return out;
}

function countAll(): { total: number; byFile: Map<string, number> } {
  const byFile = new Map<string, number>();
  let total = 0;
  for (const f of tsxFiles(SRC)) {
    const n = (stripComments(fs.readFileSync(f, 'utf8')).match(SHORTHAND) ?? []).length;
    if (n > 0) {
      byFile.set(path.relative(SRC, f), n);
      total += n;
    }
  }
  return { total, byFile };
}

describe('타이포 shorthand — 래칫(늘어날 수 없다)', () => {
  it(`전체 사용 수가 ${CEILING} 을 넘지 않는다`, () => {
    const { total, byFile } = countAll();
    const worst = [...byFile.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
    expect(
      total,
      `deprecated 타이포 shorthand 가 늘었어요(${total} > ${CEILING}).\n` +
        `새 코드는 \`Text font="caption|legal|label1|label2|body|…"\` 를 씁니다.\n` +
        `가장 많은 파일: ${worst.map(([f, n]) => `${f}(${n})`).join(', ')}`,
    ).toBeLessThanOrEqual(CEILING);
  });

  it('상수는 실제 수보다 뒤처지지 않는다 — 줄었으면 내려 적는다', () => {
    const { total } = countAll();
    /* 20 이상 줄었는데 상수가 그대로면 래칫이 헐거워진 것이다(그만큼 다시
       늘어날 여지가 생긴다). 마이그레이션 레인의 마지막 할 일을 여기서 상기시킨다. */
    expect(
      CEILING - total,
      `shorthand 가 ${CEILING - total} 개 줄었어요 — 이 파일의 CEILING 을 ${total} 로 내려 적어 주세요.`,
    ).toBeLessThan(20);
  });
});
