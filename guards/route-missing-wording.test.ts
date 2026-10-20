import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments } from './_source';

/**
 * 404 를 받은 화면은 **원인을 단정하지 않는다** [2026-10-21].
 *
 * ## 왜 가드가 필요한가
 *
 * 2026-10-20 에 **같은 404 로 두 번 서버를 의심했다.** 화면이 「백엔드가 안
 * 보여요」라고 적었는데 백엔드는 떠 있었고 헬스 200 을 돌려주고 있었다.
 * 14:13 에 뜬 프로세스가 14:54 의 `main.py` 를 못 보고 있었을 뿐이고, 그래서
 * 그날 새로 넣은 `/api/flow/lab` 이 404 였다. 진단에 두 번 각각 수십 분이 들었다.
 *
 * 404 가 말해 주는 **사실은 하나**다 — 「그 라우트가 없다」. 원인은 둘이고
 * (백엔드가 없다 · 백엔드가 낡은 코드다) 화면은 그 둘을 구별할 수 없다. 그래서
 * 문구를 `lib/apiBase::ROUTE_MISSING_DETAIL` **한 곳**에 두고 둘을 같이 적는다.
 *
 * CLAUDE.md 「오류 문구는 원인을 단정하지 않는다」 절이 규칙 본문이다.
 *
 * 이 가드가 없으면 문구는 되돌아온다 — 한 화면을 고치는 사람이 그 자리에서
 * 「백엔드를 올려 주세요」가 더 짧다고 느끼는 것이 자연스럽기 때문이다.
 *
 * 잰다:
 *   ① 상수가 `lib/apiBase` 에 있고 **원인 둘을 다 적는다**.
 *   ② 단정하는 옛 문장들이 `src` 어디에도 없다.
 *   ③ `*Unavailable` 예외 다섯의 기본 문구가 그 상수다 — 화면이 `e.message`
 *      를 그대로 세우는 자리(`lab/IssuancePage`)가 있어서 클래스가 정본이다.
 *
 * ⚠`unreachableDetail`(같은 파일)은 **대상이 아니다.** 그쪽은 시한 초과이고,
 *   응답을 아예 못 받은 자리에서는 「꺼져 있을 수 있다」가 맞는 추측이다.
 */

const ROOT = path.resolve(import.meta.dirname, '..');
const SRC = path.join(ROOT, 'src');
const EXTS = new Set(['.ts', '.tsx']);

/** 원인을 단정해서 다음 사람을 엉뚱한 곳으로 보내는 문장들. */
const BANNED = [
  '백엔드가 꺼져 있어요',
  '백엔드가 안 보여요',
  '실행 중인 백엔드가 필요해요',
  '실행 중인 백엔드(:8200)가 필요해요',
  '백엔드를 먼저 올려 주세요',
];

/** 404 를 받은 자리를 지키는 예외들 — 파일과 클래스 이름. */
const UNAVAILABLE_CLASSES: { file: string; name: string }[] = [
  { file: 'src/lib/api.ts', name: 'BacktestUnavailable' },
  { file: 'src/lab/model/strategy/anchors.ts', name: 'AnchorsUnavailable' },
  { file: 'src/lab/issuance/api.ts', name: 'IssuanceUnavailable' },
  { file: 'src/lab/scenario/api.ts', name: 'ScenarioUnavailable' },
  { file: 'src/sim/api.ts', name: 'SimulationUnavailable' },
];

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.next') continue;
      walk(full, out);
    } else if (EXTS.has(path.extname(entry.name))) {
      out.push(full);
    }
  }
  return out;
}

describe('404 문구 — 사실만 적고 원인을 단정하지 않는다', () => {
  const files = walk(SRC);

  it('잴 소스가 있다', () => {
    expect(files.length).toBeGreaterThan(100);
  });

  it('상수가 apiBase 에 있고 원인 둘을 다 적는다', () => {
    const body = fs.readFileSync(path.join(SRC, 'lib', 'apiBase.ts'), 'utf8');
    expect(body).toContain('export const ROUTE_MISSING_DETAIL');
    /* 사실 하나 + 원인 둘. 하나만 적으면 10-20 의 오진이 되돌아온다. */
    expect(body).toContain('라우트가 없어요');
    expect(body).toContain('안 떠 있을 수도 있고');
    expect(body).toContain('낡은 코드로 떠 있을 수도 있어요');
  });

  it('원인을 단정하는 옛 문장이 없다', () => {
    const hits: string[] = [];
    for (const f of files) {
      const rel = path.relative(ROOT, f).replace(/\\/g, '/');
      const body = stripComments(fs.readFileSync(f, 'utf8'));
      body.split('\n').forEach((line, i) => {
        for (const b of BANNED) {
          if (line.includes(b)) hits.push(`${rel}:${i + 1} — ${b}`);
        }
      });
    }
    expect(hits, hits.join('\n')).toEqual([]);
  });

  it('Unavailable 예외 다섯의 기본 문구가 그 상수다', () => {
    const bad: string[] = [];
    for (const { file, name } of UNAVAILABLE_CLASSES) {
      const abs = path.join(ROOT, file);
      expect(fs.existsSync(abs), `${file} 가 없다 — 목록을 고쳐라`).toBe(true);
      const body = fs.readFileSync(abs, 'utf8');
      const at = body.indexOf(`class ${name} extends Error`);
      if (at < 0) {
        bad.push(`${file}: class ${name} 를 못 찾았다`);
        continue;
      }
      /* 생성자 본문만 본다 — 클래스 선언부터 다음 닫는 중괄호 줄까지. */
      const ctor = body.slice(at, body.indexOf('\n}', at));
      if (!ctor.includes('ROUTE_MISSING_DETAIL')) {
        bad.push(`${file}: ${name} 가 ROUTE_MISSING_DETAIL 를 안 쓴다`);
      }
    }
    expect(bad, bad.join('\n')).toEqual([]);
  });
});
