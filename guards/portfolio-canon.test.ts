/* Portfolio — **기록을 쌓는 화면**의 불변식 [OWNER 2026-09-21].
 *
 * > "Strategy와 동일 위계로 존재하는 Portfolio Management tab을 만들어서 …
 * >  매일 PnL을 확인할 수 있게 환경을 하나 만들어다오."
 *
 * ## 왜 이 화면에 가드가 더 필요한가
 *
 * 이 앱의 다른 화면은 전부 **읽기**다. 틀리면 틀린 수가 보이고, 고치면 다음
 * 새로고침에 맞는 수가 선다. 이 화면만 **쓴다** — 틀린 규칙이 장부에 들어가면
 * 그 뒤의 기록이 전부 그 위에 쌓이고, 고쳐도 **되돌아오지 않는다**. 그래서
 * 여기서 재는 것은 생김새가 아니라 **장부가 거짓말을 못 하게 하는 규율**이다.
 *
 * ## 이 파일이 지는 명제 다섯
 *
 * **지우는 길이 없다.** 진 기록을 지우는 것이 생존 편향이 장부에 들어오는 가장
 * 흔한 길이다. 라우트에도 화면에도 «삭제»가 있으면 안 된다.
 *
 * **자를 두 벌 만들지 않는다.** 비용·Delta 가 계획면과 한 자라도 다르면 두
 * 화면이 같은 거래에 다른 돈을 매기고, 그 순간 이 장부는 대조가 아니라 세 번째
 * 의견이 된다.
 *
 * **숫자는 서버가 끝낸다**(§16). 누적도 차이도 서버가 낸 값이다 — 화면이 다시
 * 더하면 반올림이 갈리는 날 화면이 스스로를 반박한다.
 *
 * **「아직」과 「0」은 다른 말이다.** 등록일 뒤에 봉이 없는 다리는 안 번 것이
 * 아니라 아직 시작 안 한 것이다.
 *
 * **부품은 캐논이다.** 새 탭이라고 새 문법을 쓰면 「사이트 전체에 얼라인이
 * 없다」가 된다(오너가 세 번 한 그 지적).
 */

import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { PANELED, SECTIONS, sectionOf } from '../src/ui/nav';

const root = path.resolve(import.meta.dirname, '..');
const src = (rel: string) => fs.readFileSync(path.join(root, rel), 'utf8');

const page = () => src('src/pm/PortfolioPage.tsx');
const api = () => src('src/pm/api.ts');
const py = () => src('backend/app/paper.py');

describe('Portfolio — 섹션은 Strategy 와 같은 위계다', () => {
  it('최상위 섹션이고 Setting·Lab 앞이다', () => {
    /* [OWNER — "Strategy와 동일 위계로"]. 밑에 두면 「재는 화면의 하위」가 되는데
       이쪽은 재는 자리가 아니라 **지키는 자리**다.

       Setting·Lab 뒤에 둘 수도 없다: 섹션 순서는 확신의 순서이고 Lab 은 그
       가장자리라 반드시 마지막이어야 한다(`nav.ts` 의 그 근거). */
    const ids = SECTIONS.map((s) => s.id);
    expect(ids).toContain('portfolio');
    expect(ids.indexOf('portfolio')).toBeGreaterThan(ids.indexOf('strategy'));
    expect(ids.indexOf('portfolio')).toBeLessThan(ids.indexOf('setting'));
    expect(ids[ids.length - 1]).toBe('lab');
  });

  it('주소 하나가 섹션을 정한다', () => {
    expect(sectionOf('portfolio')).toBe('portfolio');
    expect(SECTIONS.find((s) => s.id === 'portfolio')?.tab).toBe('portfolio');
  });

  it('세입자가 하나뿐이라 메가 패널을 안 연다', () => {
    /* 패널은 **고를 것이 둘 이상일 때** 여는 물건이다(Strategy 가 둘째 세입자와
       함께 `PANELED` 에 들어간 그 규칙의 반대쪽). 하나짜리 패널은 누르면 한 칸만
       든 서랍이 열리는 것이라 한 번 더 누르게 만들 뿐이다. */
    expect(PANELED).not.toContain('portfolio');
  });

  it('페이지가 그 섹션에서 실제로 그려진다', () => {
    const app = src('src/app/page.tsx');
    expect(app).toMatch(/section === 'portfolio'/);
    expect(app).toContain('<PortfolioPage />');
  });
});

describe('장부는 거짓말을 못 한다', () => {
  it('지우는 길이 **없다** — 라우트에도 화면에도', () => {
    /* 진 기록을 지우는 것이 생존 편향이 장부에 들어오는 가장 흔한 길이다.
       내리는 것(`retire`)은 **기록에 남고 날짜가 붙는** 다른 일이다. */
    const main = src('backend/app/main.py');
    expect(main).not.toMatch(/@router\.delete\("\/api\/paper/);
    expect(py()).not.toMatch(/def\s+(delete|remove|purge|clear)_/);
    /* 화면에도 없다 — 버튼이 있으면 라우트가 따라 생긴다. */
    expect(api()).not.toMatch(/method:\s*'DELETE'/);
  });

  it('내리면 **기록이 남고 날짜가 붙는다**', () => {
    const code = py();
    /* 함수 «안»만 본다 — 파일 전체에서 찾으면 다른 함수의 `!=` 에 걸려 헛돈다.
       ⚠ 첫 판은 `store["enrolled"] = [...]` 로 시작하는 한 줄 정규식이었는데,
       `[^\]]*` 가 `store["enrolled"]` 의 닫는 괄호에서 멈춰 **어떤 위반도 못
       잡았다**(2026-09-21, 위반을 합성해 확인). 초록인 가드가 헛도는 가드일 수
       있다는 그 자리다. */
    const body = code.slice(code.indexOf('def retire'), code.indexOf('def add_trade'));
    expect(body).toMatch(/"retired"/);
    /* 목록에서 빼는 구현이면 안 된다 — 남기는 구현이어야 한다. */
    expect(body).not.toMatch(/!=\s*sid/);
    expect(body).not.toMatch(/\.pop\(|del store/);
  });

  it('등록하면 조건이 얼고 **다시 등록해도 안 덮어쓴다**', () => {
    /* 덮어쓰면 그 전 손익은 다른 규칙의 것이 되고, 표본밖 기록이 조용히
       사라진다. 이 화면이 존재하는 이유가 그 기록이라 이게 제일 중요하다. */
    const code = py();
    expect(code).toMatch(/if any\(e\["id"\] == sid for e in store\["enrolled"\]\):\s*\n\s*return store/);
    expect(code).toMatch(/"knobs": dict\(knobs\)/);
  });

  it('조건은 **서버가** 집는다 — 요청이 실어 오지 않는다', () => {
    /* 요청이 노브를 실어 오면 화면이 보여 준 것과 다른 규칙이 등록될 수 있고,
       그 순간 이 장부는 「우리가 테스트했던 것」이 아니다. */
    const main = src('backend/app/main.py');
    const fn = main.slice(main.indexOf('def paper_enroll'),
                          main.indexOf('def paper_retire'));
    expect(fn).toMatch(/peek\(mrp\.cache_name\(sid\)/);
    expect(fn).not.toMatch(/body\.get\("knobs"\)/);
    /* 화면도 노브를 안 보낸다. */
    expect(api()).toMatch(/enrollSeries = \(id: string\) => post\(paperEnrollUrl\(\), \{ id \}\)/);
  });

  it('저장이 **원자적**이다 — 반쪽 JSON 이 기록을 지우지 않는다', () => {
    const code = py();
    expect(code).toMatch(/mkstemp/);
    expect(code).toMatch(/os\.replace/);
  });
});

describe('자를 두 벌 만들지 않는다', () => {
  it('비용·Delta 가 계획면과 **같은 수**다', () => {
    /* 다르면 두 화면이 같은 거래에 다른 돈을 매긴다 — 그러면 대조가 안 된다.
       `test_paper.py` 가 파이썬 쪽에서 같은 명제를 재고, 여기서는 그 상수가
       화면에 **하드코딩되지 않았는지**를 본다(서버가 준 것을 그린다). */
    const p = page();
    expect(p).toMatch(/sheet\.costBp/);
    expect(p).toMatch(/sheet\.notional/);
    expect(p).not.toMatch(/0\.5bp['"`]/);
  });

  it('손익 공식이 화면에도 `paper.py` 에도 **없다**', () => {
    /* 규칙 북은 엔진의 봉을 자르고 수동 북은 대사 경로를 지난다(레인 §10-10).
       두 번째 정의를 만들면 페이퍼 북과 계획면이 다른 수를 말한다. */
    expect(py()).toMatch(/mrm\.score\(/);
    /* 화면에는 곱셈이 없다 — 있다면 서버가 안 끝낸 것이다. */
    expect(page()).not.toMatch(/notional\s*\*\s*\(/);
  });

  it('누적을 **서버가** 굴린다 (§16)', () => {
    expect(py()).toMatch(/def _roll/);
    /* 화면은 `cum` 을 읽기만 한다 — `reduce`·누적 루프가 없다. */
    const p = page();
    expect(p).not.toMatch(/\.reduce\(/);
    expect(p).toMatch(/d\.cum/);
  });

  it('실가격과 근사를 **섞어 더하지 않는다**', () => {
    /* 못 잰 항은 `None` 이고 화면이 «—» 를 그린다. 0 으로 적으면 「0 원이었다」는
       딴 사실이 되고, 실가격 셋 + 근사 하나의 합이 실가격처럼 보인다. */
    const code = py();
    expect(code).toMatch(/def merge_split/);
    expect(code).toMatch(/if any\(v is None for v in vals\)/);
    /* 화면은 `null` 을 그대로 캐논 부품에 넘긴다(그 부품이 «—» 와 사유를 안다). */
    expect(page()).toMatch(/<SplitColumn split=/);
  });
});

describe('「아직」과 「0」은 다른 말이다', () => {
  it('등록일 뒤에 봉이 없으면 사유가 선다 — 0 원이 아니다', () => {
    /* ★실측 2026-09-21: 09-21 등록인데 마지막 봉이 09-18 이었다.
       `mrmetrics.index_at` 은 빈 구간을 안 만들려고 마지막 봉을 남기는데, 페이퍼
       북에서는 그 봉이 **등록 전의 하루**다 — 그날 손익을 얹으면 장부가 있지도
       않았던 날의 돈을 갖는다. */
    expect(py()).toMatch(/if start_iso is not None and dates\[-1\] < start_iso/);
    expect(py()).toMatch(/"why": f"등록일/);
    expect(api()).toMatch(/why: string \| null/);
    expect(page()).toMatch(/l\.why \?/);
  });
});

describe('부품은 캐논이다 — 새 탭이라고 새 문법을 쓰지 않는다', () => {
  it('공용 부품을 **임포트**한다', () => {
    const p = page();
    for (const m of [
      '@/table/rowHeight',     // ROW_H — 표 행 높이는 앱에 한 수다
      '@/table/tint',          // 방향색은 캐논 한 곳이 정한다(0 에서 갈린다)
      '@/ui/Cond',             // 조건 바의 그 칸
      '@/ui/ThHelp',           // 표 머리의 뜻풀이
      '@/ui/ControlCard',      // Field·Segmented — 32px 등고
      '@/ui/controlHeight',    // 그 32 를 따로 안 적는다
      '@/chart/TimeChart',     // x = 날짜인 차트는 이것 하나
      '@/mr/parts',            // 분해는 계획면의 그 부품
      '@/lib/josa',            // 조사는 한 곳에서만 정한다
    ]) {
      expect(p, m).toContain(m);
    }
  });

  it('명구 의무 — 이웃 화면과 같은 문법', () => {
    /* 집행면이 아니라 **기록면**이라 문장이 다르다: 권하는 것이 아니라 적는다. */
    expect(page()).toMatch(/체결이 아니라 기록이에요 — 투자판단이 아니에요/);
  });

  it('이 화면이 **왜 Strategy 와 다른지**를 화면이 말한다', () => {
    /* 안 적으면 「또 하나의 성과 화면」으로 읽힌다. 계획면의 1년 손익이 성과가
       아니라 고른 결과라는 것, 그래서 여기가 표본밖이라는 것이 이 탭의 전부다. */
    const p = page();
    expect(p).toMatch(/고른 결과/);
    expect(p).toMatch(/표본밖/);
  });
});
