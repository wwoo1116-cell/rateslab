'use client';

import { useSyncExternalStore } from 'react';

import { dirClass, fmtDelta, fmtLevel } from '@/lib/format';
import { euro } from '@/lib/josa';
import type { Row } from '@/table/rows';

/**
 * 화면 바닥의 **기준점 세 개**. 어느 탭에 있든 같은 자리에 있다.
 *
 * ── 왜 있는가 (v1 의 근거 그대로) ───────────────────────────────────────────
 * 탭이 다섯이고 행이 이백 개다. 포워드 탭 깊숙이 들어간 사람은 지금 10Y 가 어디
 * 있는지 모르는데, 다른 모든 숫자는 그 10Y 를 기준으로 읽힌다. 그래서 **수준
 * (10Y)** · **기울기(3s10s)** · **포워드(1Yx1Y)** 셋을 띠가 진다 — 커브를 읽는
 * 세 가지 방식이 하나씩이다. 셋 다 이미 요약 페이로드에 있는 값이라 백엔드에
 * 붙인 것은 없다.
 *
 * ── v1 과 다른 한 가지: `fixed` 가 아니다 ───────────────────────────────────
 * v1 의 띠는 `position: fixed` 였고, 그래서 접힘/펼침 때 **앱 루트의 패딩**이
 * 34↔12 로 같이 뛰어야 했다(안 그러면 마지막 행이 띠 밑에 깔린다). 그 동시성이
 * v1 이 이 컴포넌트에서 가장 길게 설명하는 문제다.
 *
 * v2 의 페이지는 `height: 100vh` 짜리 **flex 기둥**이라(§`app/page.tsx`) 그
 * 문제가 아예 없다: 띠를 마지막 flex 아이템으로 두면 내용이 받는 높이가 남는
 * 높이로 정의되고, 띠가 줄면 내용이 그만큼 커진다. 맞춰야 할 두 값이 없으므로
 * 어긋날 수도 없다.
 *
 * ── 접힘은 기억한다. 그리고 이건 `localStorage` 여도 된다 ───────────────────
 * 창 **자리**는 `localStorage` 를 쓰지 않는다(`ui/window/geometry.ts`) — 다른
 * 모니터에서 복원된 좌표는 아무도 못 찾는 창이 되기 때문이다. 접힘은 좌표가
 * 아니라 취향이고 어느 화면에서도 같은 뜻이라 그 규칙이 적용되지 않는다.
 */

/** 수준 하나, 기울기 하나, 포워드 하나. id 는 행 빌더가 만드는 그대로다
 * (스프레드는 다리 id 를 유지하고 라벨만 트레이더 약칭이 된다). */
export const ANCHOR_IDS = ['10Y', '3Y-10Y', '1Yx1Y'];

/** 두 상태의 높이. 접힌 12px 은 "여기 뭔가 접혀 있다" 를 말할 최소한이다. */
export const STRIP_H = { open: 34, collapsed: 12 } as const;

const STORE_KEY = 'sr-strip-collapsed';

function Anchor({ row, onPin }: { row: Row; onPin: (row: Row) => void }) {
  return (
    <button
      type="button"
      className="sr-strip-anchor"
      onClick={() => onPin(row)}
      title={`${row.label}${euro(row.label)} 이동`}
    >
      <span className="sr-strip-anchor-label">{row.label}</span>
      <span className="sr-strip-anchor-now">{fmtLevel(row.now, row.unit)}</span>
      <span className={`sr-strip-anchor-d ${dirClass(row.changes.d1)}`}>
        {fmtDelta(row.changes.d1, row.unit)}
      </span>
    </button>
  );
}

export function BottomStrip({
  rows,
  onPin,
  collapsed,
  onCollapsed,
}: {
  rows: Row[];
  /** 기준점을 누르면 그 종목이 있는 탭으로 가서 그 행이 선택된다. */
  onPin: (row: Row) => void;
  collapsed: boolean;
  onCollapsed: (v: boolean) => void;
}) {
  const anchors = ANCHOR_IDS.map((id) => rows.find((r) => r.id === id)).filter(
    (r): r is Row => !!r,
  );

  /* 데이터가 오기 전(그리고 세 id 중 하나도 못 찾은 경우) 띠를 **안 세운다.**
     빈 띠는 "값이 없다" 가 아니라 "여기 뭔가 고장났다" 로 읽힌다. */
  if (anchors.length === 0) return null;

  return (
    /* 두 내용이 **둘 다 마운트된 채** 교차한다. 접힐 때 서브트리를 갈아 끼우면
       높이 애니메이션 중간에 내용이 사라져서 접힘이 아니라 결함으로 보인다
       (v1 이 그렇게 만들었다가 고친 자리). */
    <div
      className="sr-strip"
      style={{ height: collapsed ? STRIP_H.collapsed : STRIP_H.open }}
    >
      {/* 접힌 상태에서는 **띠 전체가** 펼치기 버튼이다. 12px 높이 안에 32px 짜리
          표적을 넣는 건 잔인하고, 그 줄에 다른 할 일이 없다. */}
      <button
        type="button"
        className="sr-strip-handle"
        style={{ height: STRIP_H.collapsed }}
        onClick={() => onCollapsed(false)}
        aria-hidden={!collapsed}
        tabIndex={collapsed ? 0 : -1}
        data-shown={collapsed ? '' : undefined}
        title="지표 바 펼치기"
      >
        <span className="sr-strip-grab" />
      </button>

      <div
        className="sr-strip-row"
        style={{ height: STRIP_H.open }}
        data-shown={collapsed ? undefined : ''}
        // 흐려진 줄이 그 아래 손잡이로 가는 클릭을 먹으면 안 된다
        inert={collapsed}
      >
        {anchors.map((r) => (
          <Anchor key={r.id} row={r} onPin={onPin} />
        ))}
        {/* 접기 단추는 **기준점들과 같은 무리**에 선다. 띠 오른쪽 끝에 홀로 두면
            자기가 여는 것에서 1,700px 떨어진 유물처럼 읽힌다(v1 의 실측 판단). */}
        <button
          type="button"
          className="sr-strip-collapse"
          onClick={() => onCollapsed(true)}
          title="지표 바 접기"
        >
          ▾
        </button>
      </div>
    </div>
  );
}

/* 접힘 값은 외부 스토어로 읽는다 — 새로고침을 넘어 살아남고, 쓰면 구독자 전원이
 * 다시 그려진다. */
let listeners: (() => void)[] = [];

function subscribe(cb: () => void): () => void {
  listeners = [...listeners, cb];
  return () => {
    listeners = listeners.filter((l) => l !== cb);
  };
}

function read(): boolean {
  try {
    return localStorage.getItem(STORE_KEY) === '1';
  } catch {
    return false; // 스토리지가 막힌 환경 — 띠는 그냥 기억을 못 할 뿐이다
  }
}

/** 접힘 상태, 새로고침을 넘어 기억된다. 서버 스냅샷은 **항상 펼침**이고
 * 하이드레이션에서 교정된다 — 서버는 이 취향을 알 방법이 없다. */
export function useStripCollapsed(): [boolean, (v: boolean) => void] {
  const collapsed = useSyncExternalStore(subscribe, read, () => false);
  const set = (v: boolean) => {
    try {
      localStorage.setItem(STORE_KEY, v ? '1' : '0');
    } catch {
      /* 스토리지가 막힌 환경 */
    }
    for (const l of listeners) l();
  };
  return [collapsed, set];
}
