'use client';

import { Select } from '@coinbase/cds-web/alpha/select';
import { Box } from '@coinbase/cds-web/layout';

import { Field } from '@/ui/ControlCard';
import { fitWidth, useControlFont } from '@/ui/fit';

import { DROPDOWN_STYLES } from '@/ui/window/popup';

/**
 * 포워드 탭의 시작점 필터 (§3).
 *
 * ── 왜 칩이 아니라 하나 고르는 컨트롤인가 ───────────────────────────────────
 * 시작점은 **21개**다(ON + 3M 간격으로 5Y 까지, `forwards.py::START_POINTS`).
 * 칩 21개는 필터가 아니라 두 번째 표고, 오너가 이번 패스에서 없앤 것도 그
 * 칩 줄이다. 하나만 고르는 컨트롤은 자리를 한 줄도 안 먹는다.
 *
 * ── 값은 URL 에 있다 ────────────────────────────────────────────────────────
 * `?fs=1Y` 로 링크가 된다. 쓰기는 replaceState — 시작점을 바꾸는 건 목적지가
 * 아니라 지금 보고 있는 것의 범위라서, 뒤로가기 스무 번이 되면 안 된다
 * (`useUrlState` 의 규칙 그대로).
 *
 * ── 목록은 데이터에서 나온다 ────────────────────────────────────────────────
 * 상수로 21개를 적어두지 않는다. 백엔드가 시작점을 하나 더 붙이거나 빼면 이
 * 목록도 같이 움직여야 하고, 두 벌이 있으면 반드시 어긋난다. `rows` 에 실제로
 * 있는 시작점만 고를 수 있다 — 고르면 빈 표가 나오는 선택지는 없다.
 */

/** "전체" 를 나타내는 값. `null` 을 쓰면 CDS 의 단일 선택 타입이 곧바로
 * `string | null` 로 넓어져서 호출부마다 null 체크가 붙는다. */
export const ALL_STARTS = 'all';

export function StartFilter({
  starts,
  value,
  onChange,
}: {
  /** 실제로 행이 있는 시작점, 오름차순 (표의 시작-우선 정렬 그대로) */
  starts: string[];
  value?: string;
  onChange: (v: string | undefined) => void;
}) {
  /* ★폭은 **유도**다 [OWNER 2026-09-23]. 200 은 「168 에서 `1Y3M` 이 두 줄로
     접혔다」는 손 실측이었다 — 그 진단은 옳았지만 답이 상수라, 시작점 라벨이
     늘어도 다시 안 셌다. 200 은 첫 프레임 폴백으로만 남는다. */
  const [fontProbe, font] = useControlFont();
  const w = fitWidth('select', ['전체', ...starts], font, 200);
  if (starts.length === 0) return null;
  return (
    <Box width={w}>
      {fontProbe}
      {/* 라벨이 "시작" 이고 값이 "1Y 시작" 이면 화면에는 "시작 1Y 시작" 이 남는다
          (실측 2026-08-14). 라벨이 단위를 지고 값은 값만 진다. */}
      {/* font legal(13) — 컨트롤 값 13px 규칙(popup.ts 의 근거).
          `styles`(목록 폭)는 BondTypeFilter 와 함께 빠져 있었다 [2026-08-25] —
          없으면 목록이 컨트롤보다 훨씬 좁게 잡혀 라벨이 글자마다 접힌다. */}
      <Field label="시작점">
        <Select
          size="s"
          font="legal"
          styles={DROPDOWN_STYLES}
          accessibilityLabel="포워드 시작점"
          value={value ?? ALL_STARTS}
          onChange={(v) => onChange(v === ALL_STARTS || v == null ? undefined : v)}
          options={[
            { value: ALL_STARTS, label: '전체' },
            ...starts.map((s) => ({ value: s, label: s })),
          ]}
        />
      </Field>
    </Box>
  );
}
