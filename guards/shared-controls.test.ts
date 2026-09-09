import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments } from './_source';

/**
 * 공용 부품 승격의 가드 [OWNER 2026-09-02 — "디자인 구성을 Main·Backtest 와
 * 통일" · "공용 부품은 한 벌로 승격"] — 얼라인 8(«같은 것은 한 번만 만든다»)의
 * 세 번째 판. `Field` 네 벌(2026-08-25 · `control-fill`)과 같은 병이 세 자리에
 * 더 있었고, 이 파일은 그 세 자리가 다시 갈라지지 않는 것을 잰다.
 *
 * ① **숫자 칸은 앱에 한 벌이다.** blur/Enter 커밋 숫자 입력이 세 벌이었다 —
 *    시뮬 `NumField` · rv `BpField` · mr `NumInput`. 같은 규율을 각자 적고
 *    있었고 차이는 전부 옵션(접미·포맷·하한·폭)이었다. 공용은
 *    `ui/ControlCard.tsx::NumField` 하나다. 기계의 규율(즉시 파싱 금지·되돌림)
 *    은 `simulation.test.ts` 의 «숫자 칸은 타이핑을 막지 않는다» 가 잰다.
 *
 * ② **`Cond`/`ThHelp` 는 한 벌이다.** rv 와 MR 이 조건 바 칩과 열 머리
 *    뜻풀이를 두 벌씩 갖고 있었고 타이포 문법까지 갈려 있었다(rv 는 구
 *    shorthand, MR 은 `Text font=…`). 공용은 `ui/Cond.tsx`·`ui/ThHelp.tsx` 고
 *    새 문법으로 선다(CLAUDE.md cds-code §5 — 새 코드에서 shorthand 금지).
 *
 * ③ **MR 의 배타 선택은 캐논 `Segmented` 다.** KnobBar 의 손 알약 `Choice`
 *    (`data-on`)가 배타 선택 여섯 자리(진입 규칙 + 실전 규칙 다섯)를 지고
 *    있었다 — 앱의 정본은 `ui/ControlCard.tsx::Segmented`(Backtest 방향 칸의
 *    그 부품)다. **2026-09-09 에 자리가 옮겨 갔다**: 노브 다섯이 화면에서
 *    내려가면서(격자가 답한다) KnobBar 의 마지막 세그먼트도 같이 내려갔고,
 *    MR 에 남은 배타 선택은 최적화 절의 「순위 기준」 하나다. KnobBar 에 남는
 *    손 알약은 «프리셋 + 자유값» 줄(비용) 하나뿐이다.
 */

const ROOT = path.resolve(import.meta.dirname, '..');
const SRC = path.join(ROOT, 'src');

function walk(dir: string, out: string[] = []): string[] {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === 'node_modules' || e.name === '.next') continue;
      walk(p, out);
    } else if (e.name.endsWith('.tsx')) {
      out.push(p);
    }
  }
  return out;
}

const files = walk(SRC);
const bodyOf = new Map(
  files.map((f) => [path.relative(ROOT, f).replaceAll('\\', '/'), stripComments(fs.readFileSync(f, 'utf8'))]),
);

/** `name` 을 정의하는 파일들(주석 걷은 소스 기준). */
function definers(re: RegExp): string[] {
  return [...bodyOf.entries()].filter(([, s]) => re.test(s)).map(([f]) => f).sort();
}

describe('① 숫자 칸은 앱에 한 벌이다', () => {
  it('잴 소스를 실제로 찾았다', () => {
    expect(files.length).toBeGreaterThan(20);
  });

  it('`NumField` 정의는 `ui/ControlCard.tsx` 뿐이다', () => {
    expect(
      definers(/function NumField\b/),
      '`NumField` 가 여러 곳에 정의돼 있어요 — 화면마다 같은 칸이 다르게 생깁니다.\n' +
        '공용은 `ui/ControlCard.tsx` 이고 나머지는 임포트해 쓰세요.',
    ).toEqual(['src/ui/ControlCard.tsx']);
  });

  it('옛 이름의 손 구현이 되살아나지 않았다 — `BpField`·`NumInput`', () => {
    expect(definers(/function (BpField|NumInput)\b/)).toEqual([]);
  });

  it('세 소비자가 전부 공용을 임포트한다', () => {
    for (const f of ['src/sim/SimulationPage.tsx', 'src/rv/RvPage.tsx', 'src/mr/KnobBar.tsx']) {
      const s = bodyOf.get(f);
      expect(s, f).toBeDefined();
      expect(s, f).toMatch(/import \{[^}]*\bNumField\b[^}]*\} from '@\/ui\/ControlCard'/);
      expect(s, f).toMatch(/<NumField\b/);
    }
  });
});

describe('② `Cond`/`ThHelp` 는 한 벌이다', () => {
  it('`Cond` 정의는 `ui/Cond.tsx`, `ThHelp` 정의는 `ui/ThHelp.tsx` 뿐이다', () => {
    /* `\b` 라서 시뮬의 `CondChip`(라벨·값 쌍 — 딴 부품)은 안 걸린다. */
    expect(definers(/function Cond\b/)).toEqual(['src/ui/Cond.tsx']);
    expect(definers(/function ThHelp\b/)).toEqual(['src/ui/ThHelp.tsx']);
  });

  it('rv 와 MR 이 공용을 임포트한다', () => {
    expect(bodyOf.get('src/rv/RvPage.tsx')).toMatch(/import \{ Cond \} from '@\/ui\/Cond'/);
    expect(bodyOf.get('src/mr/MrPage.tsx')).toMatch(/import \{ Cond \} from '@\/ui\/Cond'/);
    expect(bodyOf.get('src/rv/RankingTable.tsx')).toMatch(/import \{ ThHelp \} from '@\/ui\/ThHelp'/);
    expect(bodyOf.get('src/mr/MrPage.tsx')).toMatch(/import \{ ThHelp \} from '@\/ui\/ThHelp'/);
  });

  it('`ThHelp` 는 **숙주마다** 한 굵기로 선다 — 승격이 rv 를 갈라 놓았던 자리', () => {
    /* 2026-09-02 회귀: 승격하며 앵커를 `Text font="caption"`(13/600)으로 감쌌더니
       **rv 머리가 「600 넷 · 700 넷」으로 갈렸다**(실측). rv 는 손 표라 머리에
       `Text` 가 없어 `thead th { font-weight: 700 }` 을 그대로 받는데, 이 부품만
       토큰 굵기를 얹었기 때문이다. MR 은 CDS 표라 형제가 전부 600 이라 반대다.
       → 숙주가 둘이면 답도 둘이다: `font` prop 이 그것을 가른다.
       **부품이 숙주의 활자를 통째로 상속하면 숙주마다 다른 부품이 되고, 통째로
       못 박으면 어느 한 숙주를 깬다** — 크기만 못 박고 굵기는 고르게 한다. */
    const th = bodyOf.get('src/ui/ThHelp.tsx')!;
    expect(th).toMatch(/font\?: 'caption' \| 'inherit'/);
    /* 크기는 어느 판에서도 13px 로 못 박힌다(승격이 고친 진짜 결함 — MR 의 셋이
       headline 16/24 였다). inherit 판의 13px 은 `.sr-thhelp-host` 가 진다. */
    const css = fs.readFileSync(path.join(ROOT, 'src/theme/type.css'), 'utf8');
    expect(css).toMatch(/\.sr-thhelp-host \{\s*font-size: 13px;/);
    /* rv(손 표)는 숙주 추종, MR(CDS 표)은 기본값 — 호출부가 그 사실을 말한다. */
    expect(bodyOf.get('src/rv/RankingTable.tsx')).toMatch(/font="inherit"/);
    expect(bodyOf.get('src/mr/MrPage.tsx')).not.toMatch(/font="inherit"/);
  });

  it('공용 두 벌은 새 타이포 문법이다 — deprecated shorthand 가 없다', () => {
    /* rv 판이 `TextCaption`/`TextLegal` 을 쓰고 있었다 — 승격하며 `Text font=…`
       로 옮겼고(시각 동일 — shorthand 는 CDS 소스가 `Text font` 위임), 여기로
       되돌아오면 안 된다. 앱 전체의 래칫은 `typography-ratchet` 이 진다. */
    for (const f of ['src/ui/Cond.tsx', 'src/ui/ThHelp.tsx']) {
      const s = bodyOf.get(f);
      expect(s, f).toBeDefined();
      expect(s, f).not.toMatch(/<Text(Caption|Legal|Label\d|Body)\b/);
    }
    expect(bodyOf.get('src/ui/Cond.tsx')).toMatch(/font="caption"/);
    expect(bodyOf.get('src/ui/Cond.tsx')).toMatch(/font="legal"/);
  });
});

describe('③ MR 의 배타 선택은 캐논 `Segmented` 다', () => {
  const knob = bodyOf.get('src/mr/KnobBar.tsx')!;

  it('손 알약 `Choice` 는 없다 — 앱 어디에도', () => {
    expect(definers(/function Choice\b/)).toEqual([]);
  });

  it('MR 의 배타 선택은 최적화 절의 「순위 기준」 하나다', () => {
    /* 2026-09-09 에 KnobBar 의 마지막 세그먼트(진입 규칙)가 내려갔다 [OWNER —
       "진입 규칙이나 룩백, 진입 청산 손절 시그마는 그냥 최초 전략 실험 화면에서
       사라지게 하고"]. 그 다섯은 이제 격자가 답한다.

       그래서 명제가 자리를 옮긴다: MR 에서 세그먼트를 **세우는 곳**은
       `OptimizePane` 의 순위 기준 하나이고, KnobBar 에는 없다. 수가 늘면 내린
       칸이 돌아온 것이고, KnobBar 에 다시 서면 노브가 돌아온 것이다. */
    expect(knob).not.toMatch(/<Segmented\b/);
    const pane = bodyOf.get('src/mr/OptimizePane.tsx')!;
    expect(pane).toMatch(/import \{[^}]*\bSegmented\b[^}]*\} from '@\/ui\/ControlCard'/);
    expect(pane.match(/<Segmented\b/g)?.length).toBe(1);
  });

  it('배타 선택 자리에 `data-on` 알약이 되살아나지 않았다', () => {
    /* KnobBar 에 남은 `data-on` 은 배타 선택이 아니라 «프리셋 + 자유값» 줄
       하나뿐이다(비용). 룩백 줄과 `SigmaPick` 은 2026-09-09 에 같이 내려갔다 —
       하나를 넘으면 내린 줄이 돌아왔거나 배타 선택이 손 알약이 된 것이다. */
    expect((knob.match(/data-on=/g) ?? []).length).toBeLessThanOrEqual(1);
  });
});
