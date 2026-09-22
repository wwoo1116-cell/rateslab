import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { dateToIso, isoToDate } from '../src/ui/IsoDateField';

/**
 * ISO 날짜 칸 [OWNER 2026-08-26 — 「DateInput 으로 이관」].
 *
 * 재는 것 셋이고 셋 다 **조용히** 틀린다:
 *
 *   ① UTC 함정 — 하루가 새는 변환. 화면에 보이는 날짜와 서버로 가는 날짜가
 *      갈리면 백테스트가 다른 날에 들어간다.
 *   ② 로케일 — CDS `LocaleContext` 기본값이 `en-US` 라 그냥 두면 ko-KR
 *      브라우저에서도 `02/02/2026` 이 나온다(실측). 이 제품의 날짜 어휘는 ISO 다.
 *   ③ 얼라인 — `DateInput` 은 힌트 줄을 상시로 달아 블록이 74px 이 되고 같은
 *      행의 형제(48~50px)보다 컨트롤이 24px 위로 뜬다(실측). 그 슬롯은 **에러
 *      전용**이어야 한다.
 */

const src = fs.readFileSync(
  path.resolve(import.meta.dirname, '../src/ui/IsoDateField.tsx'),
  'utf8',
);

/** 주석을 걷은 판. 이 파일의 주석에는 «왜 안 쓰는가» 를 적느라 금지어가 그대로
 *  들어 있다(`toISOString`·`compact`) — 그걸 세면 근거를 적을수록 빨개진다. */
const code = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');

describe('① ISO ↔ Date 왕복 — 하루가 새지 않는다', () => {
  it('ISO 를 그 날 **로컬 자정**으로 읽는다', () => {
    const d = isoToDate('2026-08-25')!;
    expect(d.getFullYear()).toBe(2026);
    expect(d.getMonth()).toBe(7); // 0-index
    expect(d.getDate()).toBe(25);
    expect(d.getHours()).toBe(0);
  });

  it('Date 를 **로컬 달력**으로 적는다 — `toISOString` 이 아니다', () => {
    /* `new Date(2026,7,25).toISOString()` 은 KST(+9)에서 `2026-08-24T15:00Z` 라
       앞 열 글자가 **8/24** 다. 그 함수를 쓰면 하루가 샌다. */
    expect(dateToIso(new Date(2026, 7, 25))).toBe('2026-08-25');
    expect(code).not.toMatch(/toISOString/);
  });

  it('왕복이 항등이다 — 연말·월초·윤년 포함', () => {
    for (const iso of ['2026-01-01', '2026-12-31', '2024-02-29', '2026-03-01']) {
      expect(dateToIso(isoToDate(iso))).toBe(iso);
    }
  });

  it('빈 값과 못 읽는 꼴은 조용히 비어 있다 — 지어내지 않는다', () => {
    expect(isoToDate('')).toBeNull();
    expect(isoToDate(undefined)).toBeNull();
    expect(isoToDate('2026-8-5')).toBeNull(); // 0 채움이 아니면 우리 꼴이 아니다
    expect(isoToDate('아무거나')).toBeNull();
    expect(dateToIso(null)).toBe('');
    expect(dateToIso(new Date(NaN))).toBe('');
  });
});

describe('② 표시는 로케일과 무관하게 ISO 다', () => {
  it('`en-CA` 로 로케일을 못 박고 구분자는 `-` 다', () => {
    /* 실측(Intl, 2026-08-26):
         en-US  "2/2/2026"     -> MM-DD-YYYY
         ko-KR  "2026. 2. 2."  -> YYYY-MM-DD-   (후행 구분자가 남는다)
         en-CA  "2026-02-02"   -> YYYY-MM-DD    <- 이것
       `en-CA` 는 **자릿수 순서 때문에** 고른 것이다. */
    expect(src).toMatch(/<LocaleProvider locale="en-CA">/);
    expect(src).toMatch(/separator: '-'/);
  });

  it('로케일은 이 컨트롤에만 건다 — 앱 전역이 아니다', () => {
    const providers = fs
      .readFileSync(path.resolve(import.meta.dirname, '../src/app/providers.tsx'), 'utf8');
    expect(providers).not.toMatch(/LocaleProvider/);
  });

  it('빈 칸은 **무엇을 적을지** 말한다 — CDS 기본은 「-  -」였다', () => {
    /* CDS 기본 placeholder 는 로케일이 만든 것이 아니라 문자열 조립이다
       (`cds-common/esm/dates/useDateInput.js`):

           "   ".concat(separator, "   ").concat(separator)

       슬래시에서는 빈 칸 마스크로 읽히지만 우리 구분자는 `-` 라 화면에는
       「-  -」 두 글자만 남았다(실측 2026-08-27 백테스트 청산일). 3-3 이라
       yyyy-mm-dd(4-2-2)와 자릿수도 안 맞는다. */
    expect(src).toMatch(/placeholder: 'yyyy-mm-dd'/);
  });

  it('placeholder 의 철자는 **CDS 자신의 것**이다 — 한 컨트롤에 두 철자를 두지 않는다', () => {
    /* 이 컨트롤의 형식 안내 문장이 쓰는 그 철자다. 문자열 대조가 아니라
       패키지에서 **읽어서** 잰다 — CDS 가 대문자로 바꾸면 여기서 터져야 한다. */
    const intl = fs.readFileSync(
      path.resolve(
        import.meta.dirname,
        '../node_modules/@coinbase/cds-common/esm/dates/IntlDateFormat.js',
      ),
      'utf8',
    );
    const map = /datePartTypeMap[^)]*?day:\s*'(\w+)'[\s\S]*?month:\s*'(\w+)'[\s\S]*?year:\s*'(\w+)'/.exec(
      intl,
    );
    expect(map).not.toBeNull();
    const [, dd, mm, yyyy] = map!;
    expect(src).toMatch(new RegExp(`placeholder: '${yyyy}-${mm}-${dd}'`));
  });

  it('그 순서가 정말 YYYY-MM-DD 인지 Intl 로 직접 잰다', () => {
    /* 문자열 대조가 아니라 **실행**한다 — 라이브러리나 런타임이 바뀌면 여기서
       터져야 한다. */
    const parts = new Intl.DateTimeFormat('en-CA').formatToParts(new Date(2026, 1, 2));
    const shape = parts.map((p) => (p.type === 'literal' ? '-' : p.type)).join('');
    expect(shape).toBe('year-month-day');
  });
});

describe('③ 힌트 슬롯은 에러 전용 — 행이 어긋나지 않는다', () => {
  it('평소에는 빈 문자열로 슬롯을 닫는다', () => {
    /* `DateInput` 은 `helperText ?? error?.message ?? 형식문자열` 순으로 채운다.
       `??` 는 `''` 에서 안 떨어지므로 빈 문자열이 슬롯을 닫고, 에러일 때만
       `undefined` 로 넘겨 그 문장이 나오게 한다. */
    expect(src).toMatch(/helperText: error \? undefined : ''/);
  });

  it('부가 설명은 `Field` 의 `help` 로 간다 — 힌트 슬롯이 아니다', () => {
    /* 닫는 `>` 를 안 묶는다 [2026-09-23] — 이 시험이 지키는 것은 «설명이 어디로
       가는가» 이지 `Field` 에 prop 이 몇 개인가가 아니다. `.sr-datefit`(CDS
       `DateInput` 의 164px 바닥을 푸는 훅)이 붙으면서 이 줄이 거짓으로 깨졌다.
       그 훅 자체는 `guards/control-fill.test.ts` 가 따로 잰다. */
    expect(src).toMatch(/<Field label=\{label\} help=\{helperText\}/);
  });

  it('세 문장을 다 준다 — 안 주면 그 상황에서 아무 말도 안 한다', () => {
    for (const p of ['invalidDateError', 'disabledDateError', 'requiredError']) {
      expect(src).toContain(p);
    }
  });

  it('32px 등고를 명시한다 — CDS 기본은 34 다(실측)', () => {
    expect(src).toMatch(/height: CONTROL_H/);
    /* `compact` 는 v11 에서 빠진다 — `size="s"` 가 그 자리다. */
    expect(src).toMatch(/size: 's' as const/);
    expect(code).not.toMatch(/compact/);
  });
});

describe('④ 네이티브 날짜 입력은 남아 있지 않다', () => {
  const walk = (d: string): string[] =>
    fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => {
      const full = path.join(d, e.name);
      if (e.isDirectory()) return walk(full);
      return e.name.endsWith('.tsx') ? [full] : [];
    });

  it('`<input type="date">` 도 그 CSS 훅도 없다', () => {
    const bad: string[] = [];
    for (const f of walk(path.resolve(import.meta.dirname, '../src'))) {
      const t = fs.readFileSync(f, 'utf8');
      const code = t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\{\/\*[\s\S]*?\*\/\}/g, '');
      if (/type="date"/.test(code) || /className="sr-date"/.test(code)) bad.push(f);
    }
    expect(bad).toEqual([]);
    const css = fs.readFileSync(
      path.resolve(import.meta.dirname, '../src/theme/type.css'),
      'utf8',
    );
    expect(css).not.toMatch(/\.sr-date\s*[,{]/);
  });
});
