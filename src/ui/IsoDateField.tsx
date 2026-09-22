'use client';

/* ISO 날짜 한 칸 — CDS `DateInput` 을 이 제품의 어휘로 감싼다
 * [OWNER, 2026-08-26 — 「DateInput 으로 이관」].
 *
 * ── 왜 감싸는가 ─────────────────────────────────────────────────────────────
 * 이 제품의 날짜는 **화면 전체가 ISO 문자열**이다: 표 머리, 신선도 칩, 대사표,
 * URL 의 북 인코딩(`bt=FSW:3Y,1,100억,2026-08-24`), 백엔드 요청까지 전부 그렇다.
 * CDS `DateInput` 은 `Date | null` 과 `DateInputValidationError | null` 을 각각
 * 상태로 받는 컨트롤이라(넷 다 필수 prop) 호출부마다 변환 두 벌과 상태 하나를
 * 새로 들어야 한다. 세 곳에 그걸 흩으면 곧 세 벌이 조금씩 달라진다 —
 * CLAUDE.md 「얼라인」 8(«같은 것은 한 번만 만든다»)의 그 자리다.
 *
 * 그래서 계약은 **ISO in / ISO out** 하나다. 안쪽의 Date·error 상태는 이 파일이
 * 진다.
 *
 * ── 왜 네이티브 `<input type="date">` 를 떠나는가 ──────────────────────────
 * 종전 근거는 «네이티브가 ISO 로 보이니 화면 어휘가 하나다» 였는데, 그건
 * **로케일 의존**이다: 크롬의 날짜 입력은 브라우저 로케일로 그리므로 ko 에서만
 * `yyyy-MM-dd` 이고 en-US 에서는 `08/24/2026` 이다. 지키려던 불변식이 애초에
 * 보장이 아니었다. 그리고 그 대가로 라벨·에러·min/max 안내 문장을 전부 잃고
 * 있었다(`.sr-date` 라는 CSS 훅까지 따로 지고 있었다).
 *
 * ── ISO 표시는 **공짜가 아니다** (실측 2026-08-26) ─────────────────────────
 * 옮기고 나니 ko-KR 브라우저에서 `02/02/2026` · placeholder `mm/dd/yyyy` 가
 * 나왔다. 뿌리는 CDS `LocaleContext` 의 기본값이 **`en-US`** 인 것이다 —
 * `DateInput` 은 브라우저 로케일이 아니라 그 컨텍스트를 읽어
 * `new IntlDateFormat({locale, separator})` 를 만든다.
 *
 * 그래서 이 칸은 자기 로케일을 **명시**한다. `Intl` 실측:
 *
 *     en-US   "2/2/2026"      -> MM-DD-YYYY
 *     ko-KR   "2026. 2. 2."   -> YYYY-MM-DD-   (후행 구분자가 남는다)
 *     en-CA   "2026-02-02"    -> YYYY-MM-DD    <- 이것
 *
 * `en-CA` 는 **자릿수 순서 때문에** 고른 것이지 이 앱이 캐나다 것이어서가
 * 아니다. ko-KR 은 마지막 리터럴(«2.» 의 점)이 구분자로 바뀌어 `2026-02-02-`
 * 가 된다 — `IntlDateFormat.format` 이 literal 파트를 전부 separator 로
 * 치환하기 때문이다. 범위는 이 컨트롤 하나다(앱 전역 프로바이더가 아니다).
 *
 * 이제 표시가 **로케일과 무관하게** `2026-08-25` 다 — 네이티브가 못 주던 것이고,
 * 이 이관이 실제로 얻은 것이다.
 *
 * ── 이 칸은 **제 상자를 안 채운다** (실측 2026-09-23) ───────────────────────
 * CDS `DateInput` 의 껍질에 `min-width: 164px` 이 박혀 있다. `Field` 가
 * `minWidth:0`·`flexGrow:1` 로 150px 상자에 맞춰도 안쪽이 164 로 버티고 상자를
 * **오른쪽으로 뚫는다**(입력 자체는 162). 백테스트 북에서 「청산일 → 진입 레벨」
 * 틈이 −1px 이던 것이 이것이고, **「진입일 → 청산일」도 같은 −1** 이었다.
 * CLAUDE.md 「얼라인」 7 이 `Select`·`TextInput` 에 대해 적어 둔 규칙(«컨트롤은
 * 제 상자를 채운다»)이 이 컨트롤에서만 안 서던 자리다.
 *
 * 그래서 `Field` 에 `.sr-datefit` 을 건다 — 그 바닥을 **이 칸에서만** 푼다.
 * 글자는 안 잘린다(실측: 값 73px · 힌트 75.8px 이 148px 안에 선다). 규칙의
 * 전문과 근거는 `theme/type.css` 의 그 블록이고, `guards/control-fill.test.ts`
 * 가 잰다.
 *
 * ── UTC 함정 ────────────────────────────────────────────────────────────────
 * `new Date('2026-08-24')` 는 **UTC 자정**이라 KST(+9)에서 로컬 8/24 09:00 이
 * 되고, 반대로 `d.toISOString().slice(0,10)` 은 로컬 자정을 UTC 로 되돌려 **하루
 * 전** 날짜를 낸다. 그래서 양방향 모두 **로컬 자정**으로만 오간다.
 * `guards/iso-date-field.test.ts` 가 그 왕복을 잰다.
 */

import { useCallback, useMemo, useState } from 'react';

import { DateInput, DatePicker } from '@coinbase/cds-web/dates';
import { LocaleProvider } from '@coinbase/cds-common/system/LocaleProvider';
import type { DateInputValidationError } from '@coinbase/cds-common/dates/DateInputValidationError';

import { Field } from './ControlCard';
import { CONTROL_H } from './controlHeight';

/** `2026-08-24` → 그 날 **로컬 자정**. 빈 문자열·못 읽는 꼴은 `null`. */
export function isoToDate(iso: string | undefined | null): Date | null {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return Number.isNaN(d.getTime()) ? null : d;
}

/** 로컬 달력의 y-m-d. **`toISOString` 이 아니다** — 그건 UTC 라 하루가 샌다. */
export function dateToIso(d: Date | null | undefined): string {
  if (!d || Number.isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function IsoDateField({
  label,
  value,
  onChange,
  min,
  max,
  disabled,
  outOfRangeMessage = '데이터가 있는 구간 밖이에요.',
  helperText,
  highlight,
  highlightHint,
}: {
  label: string;
  /** ISO `YYYY-MM-DD`. 빈 문자열이면 «비어 있음» 이다(청산일의 «끝까지»). */
  value: string;
  /** ISO 로 돌려준다. 지우면 빈 문자열. */
  onChange: (iso: string) => void;
  min?: string;
  max?: string;
  disabled?: boolean;
  /** min/max 밖을 골랐을 때의 문장. 화면마다 이유가 다르다. */
  outOfRangeMessage?: string;
  helperText?: string;
  /**
   * 눈에 띄게 할 날짜들(ISO). 주면 **달력이 붙은 판**(`DatePicker`)으로 선다.
   *
   * 네이티브 `<input type="date" list>` 의 자리다. 시뮬 금통위 이벤트가 그
   * datalist 를 쓰고 있었고, 그 주석이 규칙을 적어 뒀다 — «고르는 것을 돕되
   * 막지 않는다». `highlightedDates` 가 정확히 그 일을 하고, datalist 보다
   * 낫다: 달력 안에서 **보이고** 스크린리더가 그 사실을 읽는다
   * (`highlightedDateAccessibilityHint`). 막지 않는 것은 그대로다 —
   * 강조는 `disabledDates` 가 아니다.
   */
  highlight?: string[];
  highlightHint?: string;
}) {
  /* 에러는 **컨트롤의 상태**다 — 값과 달리 바깥이 알 필요가 없다(바깥이 아는
     것은 «유효한 ISO 하나» 뿐이고, 유효하지 않은 동안은 값이 안 나간다). */
  const [error, setError] = useState<DateInputValidationError | null>(null);

  const date = useMemo(() => isoToDate(value), [value]);
  const minDate = useMemo(() => isoToDate(min) ?? undefined, [min]);
  const maxDate = useMemo(() => isoToDate(max) ?? undefined, [max]);
  const highlighted = useMemo(
    () => (highlight ?? []).map(isoToDate).filter((d): d is Date => d != null),
    [highlight],
  );

  const handle = useCallback(
    (d: Date | null) => {
      onChange(dateToIso(d));
    },
    [onChange],
  );

  /* 두 판이 **같은 prop 을 받는다** — `DatePicker` 는 `DateInput` 을 안에 두고
     달력 버튼만 더한 것이라 계약이 같다(그 타이핑이 `DateInputProps` 를 그대로
     펼친다). 그래서 공통 몫을 한 번만 적는다. */
  const common = {
    /* 라벨은 **`Field` 가 진다**(아래) — CDS `label` prop 은 label2(14px/400)로
       그려져 같은 행의 형제(`Field` = legal 13px/500)와 어긋난다(실측
       2026-08-26: 라벨 top 133 vs 171). CLAUDE.md 「얼라인」 2·3 의 그 자리다. */
    separator: '-',
    /* ── 빈 칸이 「-  -」로 보였다 [실측 2026-08-27, 백테스트 청산일] ──────────
     * CDS 의 기본 placeholder 는 로케일이 만든 것이 아니라 **문자열 조립**이다
     * (`cds-common/esm/dates/useDateInput.js`):
     *
     *     const placeholder = "   ".concat(separator, "   ").concat(separator);
     *
     * 공백 셋·구분자·공백 셋·구분자다. 슬래시(`/`)에서는 빈 칸 마스크로 읽히지만
     * 우리 구분자는 `-` 라 화면에는 「-  -」 두 글자만 남는다. 게다가 3-3 이라
     * `yyyy-mm-dd`(4-2-2)와 자릿수도 안 맞고, 마지막 구분자 뒤에는 칸이 아예
     * 없다. 무엇을 적으라는 것인지 화면이 말하지 않는 상태였다.
     *
     * 철자는 **CDS 자신의 것**을 쓴다 — `IntlDateFormat.datePartTypeMap` 이
     * `{day:'dd', month:'mm', year:'yyyy'}` 이고, 이 컨트롤의 형식 안내 문장도
     * 같은 소문자를 쓴다(위 `helperText` 주석의 그 줄). 한 컨트롤 안에서 날짜의
     * 꼴을 두 가지 철자로 말하지 않는다.
     *
     * 값이 이 순서인 것은 위 `locale="en-CA"` + `separator: '-'` 가 정한다 —
     * 셋은 한 묶음이고 `guards/iso-date-field.test.ts` 가 같이 잰다. */
    placeholder: 'yyyy-mm-dd',
    /* 32px 등고 — CLAUDE.md 「얼라인」 1. `size="s"` 가 밀도를 낮추고, 높이는 이
       리포가 `TextInput` 에 하는 것과 같이 못 박는다(`compact` 는 v11 에서 빠질
       예정이라 안 쓴다). */
    size: 's' as const,
    height: CONTROL_H,
    fontSize: 'legal' as const,
    date,
    onChangeDate: handle,
    error,
    onErrorDate: setError,
    minDate,
    maxDate,
    disabled,
    /* **힌트 슬롯은 에러 전용이다.**
       `DateInput` 은 `helperText ?? error?.message ?? 형식문자열` 순으로 그 줄을
       채운다(그 소스의 그 줄). 아무것도 안 주면 «yyyy-mm-dd» 가 상시로 붙어
       블록이 74px 이 되고, 같은 행의 형제(48~50px)보다 컨트롤이 **24px 위로**
       뜬다 — CLAUDE.md 「얼라인」 1(등고 32px)이 깨진다(실측 2026-08-26).
       그래서 평소에는 빈 문자열로 슬롯을 닫고(`??` 는 `''` 에서 안 떨어진다),
       에러가 있을 때만 `undefined` 로 넘겨 **그 문장이 나오게** 한다.
       줄은 할 말이 있을 때만 선다. */
    helperText: error ? undefined : '',
    /* 세 문장 다 준다 — 안 주면 그 상황에서 **아무 말도 안 하는** 컨트롤이
       된다(네이티브 input 이 그랬다). */
    invalidDateError: '없는 날짜예요.',
    disabledDateError: outOfRangeMessage,
    requiredError: '날짜가 필요해요.',
    accessibilityLabel: label,
  };

  const control =
    highlighted.length > 0 ? (
      <DatePicker
        {...common}
        highlightedDates={highlighted}
        highlightedDateAccessibilityHint={highlightHint}
      />
    ) : (
      <DateInput {...common} />
    );

  return (
    /* 부가 설명은 `Field` 의 `help`(라벨의 title)로 간다 — 힌트 슬롯을 쓰면
       위 이유로 행이 어긋난다. */
    <Field label={label} help={helperText} className="sr-datefit">
      {/* 로케일은 **이 칸에만** 건다 — 앱 전역 프로바이더로 올리면 다른 CDS
          소비처(숫자 포맷 등)까지 en-CA 로 끌려간다. */}
      <LocaleProvider locale="en-CA">{control}</LocaleProvider>
    </Field>
  );
}
