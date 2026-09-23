'use client';

import { Select } from '@coinbase/cds-web/alpha/select';
import { Box } from '@coinbase/cds-web/layout';

import { Field } from '@/ui/ControlCard';
import { fitWidth, useControlFont } from '@/ui/fit';

import { DROPDOWN_STYLES } from '@/ui/window/popup';

/**
 * 현금채권·자산스왑 탭의 종목군 필터 — `StartFilter` 와 같은 성질·같은 자리.
 *
 * v1 은 이 축을 칩 줄(국고채·통안채·…)로 뒀지만, v2 의 칩 줄은 오너가 걷어냈고
 * 남은 하나의 좁히기 컨트롤은 제목 줄의 Select 다(포워드 시작점의 선례). 이
 * 축이 스크리너 칩과 다른 이유도 그쪽과 같다: 같은 목록의 프리셋이 아니라
 * **다른 유니버스의 단면**이다 — 8종 × 만기 격자에서 "산금채만" 은 다른 커브를
 * 읽는 일이다.
 *
 * 목록은 데이터에서 나온다(`/api/cashbond/instruments` 의 `types`). 상수로
 * 적어두지 않는 이유는 StartFilter 와 같다 — 두 벌은 반드시 어긋난다.
 */

/** "전체" 값. null 을 피하는 이유는 `ALL_STARTS` 와 같다. */
export const ALL_TYPES = 'all';

export function BondTypeFilter({
  types,
  value,
  onChange,
}: {
  /** 실제로 행이 있는 종목군, 신용 사다리 순 (서버 순서 그대로) */
  types: { id: string; label: string }[];
  value?: string;
  onChange: (v: string | undefined) => void;
}) {
  const [fontProbe, font] = useControlFont();
  const w = fitWidth(
    'select',
    ['전체', ...types.map((t) => t.label)],
    font,
    200,
  );
  if (types.length === 0) return null;
  /* ★폭은 **유도**다 [OWNER 2026-09-23]. 200 은 「가장 긴 라벨 «캐피탈채 AA-» 가
     한 줄로 서는 폭」이라 적힌 손 실측이었는데, **같은 최장 라벨**에 백테스트
     창은 168 을 주고 있었다 — 둘 다 「실측」이라 적힌 채로 32px 이 달랐다.
     이제 둘 다 `fitWidth` 를 지나므로 같은 목록에서 같은 수가 나온다.
     200 은 첫 프레임 폴백으로만 남는다. */
  return (
    <Box width={w}>
      {fontProbe}
      {/* font legal(13) — 컨트롤 값 13px 규칙(popup.ts 의 근거).
          `styles`(목록 폭)가 **빠져 있었다** [OWNER 2026-08-25 — "산금채 AAA
          이런거 다 잘려서 나오잖아"]: 이게 없으면 CDS 가 목록을 컨트롤 폭이
          아니라 훨씬 좁게 잡아, 「산금채 AAA」가 「산금 / 채 / AA / A」로 글자마다
          접혔다(실측). 창 안의 Select 들은 전부 이걸 지고 있었고 제목 줄의
          `compact` 필터 둘만 안 지고 있었다 — `guards/dropdown-width.test.ts`
          가 이제 그 누락을 잰다. */}
      <Field label="종목군">
        <Select
          size="s"
          font="legal"
          styles={DROPDOWN_STYLES}
          accessibilityLabel="종목군"
          value={value ?? ALL_TYPES}
          onChange={(v) => onChange(v === ALL_TYPES || v == null ? undefined : v)}
          options={[
            { value: ALL_TYPES, label: '전체' },
            ...types.map((t) => ({ value: t.id, label: t.label })),
          ]}
        />
      </Field>
    </Box>
  );
}
