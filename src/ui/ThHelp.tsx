'use client';

/* 열 머리 뜻풀이 — CDS `Tooltip`(hover 와 **키보드 포커스** 둘 다 연다).
 * **앱에 하나뿐인 그것** [OWNER 2026-09-02 — "공용 부품은 한 벌로 승격"] —
 * 종전에는 rv(RankingTable)와 MR(MrPage)에 두 벌이었다.
 *
 * 열 머리 몇 개뿐이라 팝오버 비용 문제가 없다 — 셀 148개에 팝오버 기계를 하나씩
 * 달지 않던 그 판단(rv RankingTable 머리 주석)의 반대편. 점선 밑줄(cursor: help)
 * 이 "설명 있음"의 관례 표식이다. `.sr-rv-thhelp` 는 rv 에서 태어난 클래스지만
 * 앱 공용이다 — 클래스 이름은 소유권이 아니다(캐논 규칙 2). */

import { Tooltip } from '@coinbase/cds-web/overlays';
import { Text } from '@coinbase/cds-web/typography';

import { headFont } from '@/lib/format';

export function ThHelp({
  label,
  help,
  font = 'caption',
}: {
  label: string;
  help: string;
  /** 앵커의 활자 [2026-09-02 회귀 수리]. 기본 `caption`(13/600)은 이 앱이
   *  **실제로 그리는** 머리 활자다 — Main `InstrumentTable` 실측이 13px/600 이고
   *  MR 의 CDS 표도 그 값이다(`thead th { font-weight: 700 }` 규칙은 CDS `Text`
   *  의 토큰 굵기에 덮여 사실상 안 듣는다. 그 사실이 여기 적혀 있어야 다음
   *  사람이 그 규칙을 믿고 700 을 기대하지 않는다).
   *
   *  **`inherit` 는 rv 의 손 표를 위한 것**이다: 거기 머리는 `Text` 없이 글자를
   *  직접 넣어 `thead th` 의 700 을 그대로 받는다. 그 표에서 이 부품만 600 이면
   *  한 행에 두 굵기가 선다(실측 2026-09-02 — 승격 직후 실제로 그랬다). 부품이
   *  숙주의 굵기를 따라야 하는 자리다. */
  font?: 'caption' | 'inherit';
}) {
  return (
    <Tooltip
      content={
        /* 폭은 **`maxWidth` prop 이 진다** — 여기 클래스로 적지 않는다.
           2026-08-19 에 이 자리에 `.sr-rv-tiptext`(max-width 236 + white-space
           normal + keep-all)가 붙어 있었다. 툴팁이 `<th>` 안에 렌더돼 그 칸의
           nowrap 을 상속했고 긴 문장이 패널 밖으로 흘렀기 때문이다
           [OWNER — "패널 밖으로 글씨가 빠져나가"]. **그건 증상이었다**: 뿌리는
           루트에 `PortalProvider` 가 없어 CDS `Portal` 이 포털을 포기하고
           인라인 Fragment 로 떨어진 것이었다(`app/providers.tsx` 의 주석).
           프로바이더가 서면서 툴팁은 `#tooltipContainer` 로 나가고, 줄바꿈은
           body 의 `keep-all` 을 상속한다 — 실측(2026-08-26): inPortal true ·
           inTh false · white-space normal · word-break keep-all. 남은 것은
           폭뿐이고 그건 이미 아래 prop 이 말하고 있었다(클래스의 236 이 그
           prop 의 280 을 덮고 있었다). */
        <Text font="legal" as="span">
          {help}
        </Text>
      }
      maxWidth={280}
      placement="bottom"
    >
      {/* **크기는 자기가 지고, 굵기는 숙주를 따를 수 있다** [2026-09-02].
          종전에는 맨 `<span>` 이라 숙주의 활자를 통째로 상속했는데, CDS
          `TableCell` 은 children 을 `<Text font={thead ? 'headline' : 'body'}>`
          로 감싼다 — 그래서 MR 랭킹 표 머리 일곱 칸 중 셋이 headline 16/24 로
          서서 한 행에 두 크기가 섞였다(실측). 크기는 그래서 여기서 못 박고,
          굵기만 `font` prop 이 가른다(그 prop 주석에 두 숙주의 사정). */}
      {font === 'inherit' ? (
        <span className="sr-rv-thhelp sr-thhelp-host" tabIndex={0}>
          {label}
        </span>
      ) : (
        /* 활자는 **라벨이 정한다**(`headFont`) — 소문자가 든 머리는 `legal`
           이다. `caption` 은 CDS 테마가 대문자화를 걸어 「bp」를 「BP」로 세우고,
           그건 오타가 아니라 **틀린 단위**다(이 리포가 대사표 머리에서 이미
           밟은 판례). 2026-09-09 에 「순Δ (bp)」가 이 부품을 통과하면서 화면에
           「(BP)」로 섰다 — 그때 이 한 줄이 생겼다. 소문자가 없는 기존 라벨
           일곱(룩백·밴드 폭·늘어남·위치·상태·한 달 수익·버퍼…)은 전부 `caption`
           그대로다. */
        <Text font={headFont(label)} as="span" color="fgMuted" className="sr-rv-thhelp" tabIndex={0}>
          {label}
        </Text>
      )}
    </Tooltip>
  );
}
