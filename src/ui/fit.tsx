'use client';

/**
 * 컨트롤의 폭은 **제 옵션 집합에서 유도한다** — 손으로 적은 수가 아니라.
 * [OWNER 2026-09-23 · 폭·간격 정규화 Phase B]
 *
 * ── 왜 이 파일이 생겼나 ─────────────────────────────────────────────────────
 *
 * 2026-09-23 진단(Phase A)에서 **백테스트 북 여덟 칸이 전부** T1(죽은 폭 ≤16px)을
 * 실패했다. 만기 칸은 최장 라벨 `1.5Y` 가 25px 인데 상자가 116px 이었다.
 *
 * 원인은 등분할이 아니었다. 칸마다 `<Box width={N}>` 으로 **따로 잰 상수**였고,
 * 그 상수들이 서로 안 맞았다 — 같은 최장 라벨 「캐피탈채 AA-」에
 * `BacktestWindow` 는 168 을, `BondTypeFilter` 는 200 을 주고 있었다. 둘 다
 * 주석에 「실측」이라고 적혀 있었다.
 *
 * 더 나쁜 것은 **아무것도 다시 안 센다**는 것이다. `creditmatrix.BOND_TYPES` 에
 * 종목군이 하나 늘어도 상수는 그대로고, 잘림은 사람이 눈으로 볼 때까지 남는다.
 *
 * ── 이 리포는 이 길을 **이미 갔다** ─────────────────────────────────────────
 *
 * 표에서 같은 병을 앓았고 같은 답을 냈다(DESIGN.md §5.5): `ch` 문자열이 세 벌의
 * advance 로 풀려 트랙이 «표 안의 어떤 글자에도 속하지 않는 폭»으로 그려졌고,
 * 규칙은 **「사다리와 렌더는 같은 숫자를 쓴다」** 였다. 컨트롤도 같다 — 폭을 정하는
 * 산술과 글자를 그리는 폰트가 같은 수를 써야 한다.
 *
 * ── 폭은 «합집합» 에서 나온다 ───────────────────────────────────────────────
 *
 * 한 칸의 폭은 **그 칸이 가질 수 있는 모든 값** 중 가장 넓은 것에서 나온다.
 * 지금 값이 아니다 — 지금 값으로 재면 고를 때마다 칸이 움직이고, 그 흔들림은
 * 표에서 이미 한 번 밟은 자리다(DESIGN.md §5.1 「오늘 데이터가 아니라」).
 *
 * 그래서 백테스트 북의 종목 칸은 **채권·스왑·선물 라벨 전부**로 잰다. 부수로
 * 얻는 것이 있다: 줄마다 종류가 달라도 **열이 맞는다**. 종전에는 채권 줄과
 * 스왑 줄의 칸이 서로 다른 자리에서 시작했다.
 *
 * ── 웹폰트는 늦게 온다 ──────────────────────────────────────────────────────
 *
 * 첫 프레임의 캔버스는 폴백 metrics 로 재므로 수가 조금 다르다. 그래서 탐침이
 * `document.fonts.ready` 뒤에 한 번 더 읽고, 그 한 번의 재렌더를 감수한다.
 * 표가 `rangeTemplate` 에서 쓴 것과 같은 규율이다.
 */

import { useEffect, useRef, useState, type ReactElement } from 'react';

/** 컨트롤 종류 — 크롬이 종류마다 다르다. */
export type FitKind = 'select' | 'input' | 'readout';

/**
 * 크롬 = 글자가 **못 앉는** 폭. 브라우저 실측 2026-09-23(1920 · light · 13px SR):
 *
 * ```
 * select   테두리 1+1 · 패딩 16+16 · 셰브론 32            = 66
 * input    테두리 1+1 · 패딩 16+16                        = 34   (입력 셋에서 동일)
 * readout  없음                                            =  0
 * ```
 *
 * ⚠ 이 수는 **CDS 의 것**이라 버전이 오르면 낡는다. 그래서 Playwright 가드가
 * 살아 있는 DOM 에서 다시 재서 이 상수와 맞는지 본다 — 안 맞으면 터진다.
 * 유도로 멈추지 않는 것이 이 리포의 규칙이다(DESIGN.md §7).
 */
export const CHROME: Record<FitKind, number> = { select: 66, input: 34, readout: 0 };

/**
 * 쿠션 — 캔버스 실측과 실제 렌더가 미세하게 다를 때의 여유.
 *
 * 0 으로 두면 letter-spacing·font-feature 한 끗에 글자가 잘린다. 「말줄임 금지」가
 * 이 리포의 규칙이라 **잘리는 쪽보다 4px 남는 쪽**을 고른다. T1(≤16)을 크게
 * 밑돌아 기준을 무르게 하지 않는다.
 */
export const FIT_CUSHION = 4;

/**
 * 입력 칸의 **편집 여유** [OWNER 2026-09-23 — "입력은 편집 여유 별도"].
 * **⚠Provisional** — 「두 글자」는 유도가 아니라 고른 값이다.
 *
 * 셀렉트는 고르는 칸이라 최장 라벨이 곧 최대 폭이지만, 입력은 **치는 칸**이다.
 * 날짜 칸을 최장 내용(73px)에 딱 맞추면 111px 가 되는데, 캐럿이 끝에 섰을 때
 * 글자가 밀려 앞이 가려지고 드래그 선택도 갑갑해진다. 그래서 그 폰트의 `0` 두
 * 글자만큼을 더한다(13px SR 에서 ~15px).
 *
 * 「두 글자」인 근거는 없다 — 한 글자면 캐럿 자리뿐이고 셋이면 셀렉트와의 폭
 * 차이가 눈에 띈다는 판단이다. 실측으로 바꿀 자리라 Provisional 로 적는다.
 */
export const EDIT_CH = 2;

/** 캔버스 하나를 돌려 쓴다 — 측정마다 만들면 GC 가 일한다. */
let ctx: CanvasRenderingContext2D | null = null;
/** (폰트⊕글자) → 폭. 같은 목록을 행마다 다시 재지 않는다. */
const memo = new Map<string, number>();

/** 그 폰트에서 이 글자가 차지하는 폭(px). */
export function textWidth(text: string, font: string): number {
  /* 구분자는 `\u0000` 이다 — 폰트 이름에도 글자에도 못 나오므로 키가 절대
     안 겹친다. **이스케이프로 적는다**: 날바이트로 넣으면 git 이 이 파일을
     바이너리로 보고 diff 가 사라진다(실측 2026-09-23). */
  const key = `${font}\u0000${text}`;
  const hit = memo.get(key);
  if (hit !== undefined) return hit;
  if (ctx === null && typeof document !== 'undefined') {
    ctx = document.createElement('canvas').getContext('2d');
  }
  if (!ctx) return 0;
  ctx.font = font;
  const w = ctx.measureText(text).width;
  memo.set(key, w);
  return w;
}

/** 웹폰트가 바뀌면 옛 metrics 는 거짓이다 — 통째로 버린다. */
export function forgetWidths(): void {
  memo.clear();
}

/**
 * 한 컨트롤이 담아야 하는 폭 — **가장 넓은 내용 + 크롬 + 쿠션**.
 *
 * `font` 가 아직 없으면(첫 프레임) `fallback` 을 그대로 돌려준다 — 그 수는 지금
 * 코드에 있던 손 실측값이라, 이 변경은 첫 프레임에서 **종전과 같은 화면**이다.
 */
export function fitWidth(
  kind: FitKind,
  labels: readonly string[],
  font: string | null,
  fallback: number,
): number {
  if (!font) return fallback;
  let widest = 0;
  for (const l of labels) widest = Math.max(widest, textWidth(l, font));
  const edit = kind === 'input' ? EDIT_CH * textWidth('0', font) : 0;
  return Math.ceil(widest + CHROME[kind] + edit + FIT_CUSHION);
}

/**
 * 컨트롤 활자를 재는 **탐침**.
 *
 * ── ★두 번 틀리고 고친 자리다 [실측 2026-09-23] ────────────────────────────
 *
 * 첫 판은 CDS `TextLegal` 에 `ref` 를 걸고 그 계산된 폰트를 읽으려 했다. 둘 다
 * 틀렸다:
 *
 *   ① **CDS 가 `ref` 를 안 넘겨준다.** `ref.current` 가 늘 `null` 이라 폰트가
 *      영영 안 잡히고, 폭은 폴백 상수에 머물렀다 — 화면은 멀쩡해 보이는데
 *      유도가 **아무 일도 안 하고 있었다**(포트폴리오 줄에서 실측으로 걸렸다).
 *   ② **무게가 다르다.** `TextLegal` 은 500 이고 컨트롤 **값**은 400 이다.
 *      500 으로 재면 폭이 2~3% 넓게 나온다 — 죽은 폭을 없애자는 일에서 그만큼을
 *      다시 죽은 폭으로 넣는 셈이다.
 *
 * 그래서 **살아 있는 컨트롤에서 직접 읽는다.** 이 앱의 컨트롤 값은 전부 같은
 * 활자다(13px `legal` — `control-value-font` 가드가 그 규칙을 지킨다). 그러니
 * 아무 컨트롤이나 하나면 되고, 흉내 낸 탐침보다 정직하다: **재는 대상이 곧
 * 그리는 대상**이다.
 *
 * 돌려주는 노드는 컨트롤이 아직 하나도 없는 첫 프레임의 대비책이다 — 그때는
 * 폴백 상수가 서므로 화면이 종전과 같다.
 */
export function useControlFont(): readonly [ReactElement, string | null] {
  const ref = useRef<HTMLSpanElement | null>(null);
  const [font, setFont] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    /* ★한 번만 읽으면 **놓친다** [실측 2026-09-23]. 포트폴리오는 장부를 받아올
       때까지 `LoadingState` 라 컨트롤이 하나도 없고, 그 순간에 딱 한 번 읽은
       효과는 영영 `null` 에 머문다 — 폭이 폴백 상수에 갇힌다. 백테스트 창이
       우연히 됐던 것은 컨트롤이 같은 커밋에 서기 때문이었다.
       그래서 **찾을 때까지** 프레임마다 다시 본다(1초 상한). */
    let tries = 0;
    let raf = 0;
    const read = (): boolean => {
      if (!live) return true;
      /* 값이 앉는 요소를 그대로 잡는다 — 셀렉트는 트리거, 입력은 input. */
      const el =
        document.querySelector<HTMLElement>('input, [role="combobox"]') ?? ref.current;
      if (!el) return false;
      const f = getComputedStyle(el).font;
      if (!f) return false;
      setFont(f);
      return true;
    };
    const poll = () => {
      if (read() || tries > 60) return;
      tries += 1;
      raf = requestAnimationFrame(poll);
    };
    poll();
    const fonts = (document as Document & { fonts?: FontFaceSet }).fonts;
    if (fonts?.ready) {
      void fonts.ready.then(() => {
        /* 폴백 metrics 로 잰 첫 수는 거짓이다 — 버리고 다시 읽는다. */
        forgetWidths();
        read();
      });
    }
    return () => {
      live = false;
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);
  const probe = (
    <span ref={ref} aria-hidden className="sr-fitprobe" data-testid="sr-fitprobe">
      0
    </span>
  );
  return [probe, font] as const;
}
