'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Chip } from '@coinbase/cds-web/chips';
import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { TextBody, TextCaption, TextLabel1, TextLegal } from '@coinbase/cds-web/typography';
import { PeriodSelector } from '@coinbase/cds-web/visualizations/chart';

import { useScheme } from '@/app/providers';
import {
  fetchSurface3D,
  type PolicyStep,
  type Surface3DPayload,
  type SurfacePool,
} from '@/lib/api';
import { fmtLevel } from '@/lib/format';
import { pchipSample } from '@/chart/pchip';
import {
  clampPitch,
  clampYaw,
  domainOf,
  fitTransform,
  nearestNode,
  PERSP,
  PITCH_DEG,
  PRESETS,
  projectFast,
  projectedBounds,
  sampleGrid,
  sampleRidges,
  smoothRidges,
  tenorAxis,
  SPAN_X,
  SPAN_Y,
  SPAN_Z,
  toScreen,
  YAW_DEFAULT,
  type Fit,
} from '@/chart/surfaceProjection';

import { ErrorState, LoadingState } from './DataState';
import { useFillHeight } from './useFillHeight';
import { useMeasure } from './useMeasure';

/* 3D 커브 표면 — Lab 의 세입자, 전작(YieldSurface, 고정 오블리크)의 교체
 * [OWNER 2026-08-18 — 설계 4결정 + "회전 가능하게" + "깔끔한 방식(WebGL)·일별"].
 *
 * X = 만기(실연수 1~10), 깊이 = 시간(최신이 앞), Y = 금리. NYT Upshot(2015)
 * 배치 그대로에 요 회전이 붙는다.
 *
 * ── 세 겹의 캔버스 ─────────────────────────────────────────────────────────
 * NYT 실측(2026-08-18)의 결론: 비단결은 WebGL 의 픽셀 단위 보간 + 일별 밀도에서
 * 온다. Canvas 2D 페인터(조각 4천 장 겹쳐 칠하기)는 아무리 최적화해도 "종이 띠"
 * 질감이 본질로 남았다. 그래서 층을 나눈다:
 *
 *   아래   2D — 바닥 연도선 (표면 **뒤**에 있어야 하는 것)
 *   가운데 WebGL — 표면 자체: 높이 램프·조명·역전 띠는 프래그먼트에서,
 *          가림은 깊이 버퍼가. 페인터 정렬도, 조각도, 프레임당 재투영도 없다 —
 *          지오메트리는 풀이 바뀔 때 한 번 굽고, 프레임은 유니폼 갱신뿐이다.
 *   위     2D — 오늘 커브·hover·라벨·축·기준금리 (표면 **위**에 있어야 하는 것)
 *
 * 세 층은 같은 투영 산수를 쓴다 — 버텍스 셰이더가 `projectFast`+`toScreen` 을
 * 그대로 옮긴 것이라, CPU 로 찍는 주석과 GPU 로 미는 표면이 어긋나지 않는다.
 *
 * ── 값은 그림이 아니라 페이로드에서 (§16) ──────────────────────────────────
 * PCHIP 표본화·평활은 그리기 결정이다. hover 는 실측 노드에만 스냅하고 숫자는
 * 전부 페이로드 값이다. 단면 패널도 노드를 직선으로 잇는다.
 */

const SAMPLES = 48;
/** 상자 밖 여백 — 테너 라벨이 바닥 모서리 아래 14px 에 선다. */
const PAD = 38;
/** 시간 방향 흰 메시의 간격(능선 수). 일별이므로 63 ≈ 분기. 21(영업월)은
 * 선 간격이 화면 ~4px 라 능선 계단과 맞물려 "쌓인 판" 경계선으로 읽혔다
 * [OWNER 2026-08-19 — "커브 못생김" 정비, 메시 다이어트]. */
const TIME_MESH_EVERY = 63;
const MIN_PLOT_W = 560;

type PoolTab = 'govt' | 'credit' | 'swap' | 'crdsp' | 'bss';
const POOL_TABS: { id: PoolTab; label: string }[] = [
  { id: 'govt', label: '국고' },
  { id: 'credit', label: '크레딧' },
  { id: 'swap', label: '스왑' },
  /* 스프레드 표면 [OWNER 2026-08-18] — 부호는 표와 같다: 신용SP = 크레딧−국고,
   * BSS = IRS−국고 (universe 의 행 그대로, §16 · 규약 [OWNER 2026-09-22]
   * «스왑 − 채권현물»). */
  { id: 'crdsp', label: '신용SP' },
  { id: 'bss', label: 'BSS' },
];

/** 창 규칙과 같은 세션 자리기억 — localStorage 금지. */
const remember = (k: string, v: string) => {
  try {
    sessionStorage.setItem(k, v);
  } catch {
    /* 프라이빗 모드 등 — 자리기억은 편의일 뿐이다 */
  }
};
const recall = (k: string): string | null => {
  try {
    return typeof window === 'undefined' ? null : sessionStorage.getItem(k);
  } catch {
    return null;
  }
};

type Vec4 = [number, number, number, number];

/** CDS `Tabs` 는 탭 객체를 버튼 DOM 에 그대로 스프레드한다(Tabs.js 실측) —
 * 이 통로로 aria-label 을 실어, 접근성 트리에서 이름 없는 탭으로 서던 알약
 * (critique 2·3차 실측)에 이름을 붙인다. 공개 타입에는 없는 통로라 캐스트가
 * 필요하다. 로빙 tabIndex(활성만 0)는 CDS 가 이미 진다. */
const a11yTab = (id: string, label: string): { id: string; label: string } =>
  ({ id, label, 'aria-label': label }) as unknown as { id: string; label: string };

/** CSS 색 문자열 → [r,g,b,a] (0..1). 색 리터럴을 소스에 두지 않고 **파싱만**
 * 한다(color-source 가드 — 색은 direction.css 한 곳). 16진이면 자릿수로 풀고,
 * 함수형이면 숫자만 추려 읽는다 — 쉼표든 공백-슬래시든 같은 순서다. */
function cssColorToVec(v: string): Vec4 {
  const s = v.trim();
  if (s.startsWith('#')) {
    const hex = s.slice(1);
    const w = hex.length >= 6 ? 2 : 1;
    const at = (i: number) => {
      const t = hex.slice(i * w, i * w + w);
      return parseInt(w === 1 ? t + t : t, 16) / 255;
    };
    return [at(0), at(1), at(2), hex.length === 8 ? at(3) : 1];
  }
  const nums = (s.match(/[\d.]+%?/g) ?? []).map((t) =>
    t.endsWith('%') ? parseFloat(t) / 100 : parseFloat(t),
  );
  const [r = 128, g = 128, b = 128] = nums;
  const a = nums.length > 3 ? Math.min(1, nums[3]) : 1;
  return [r / 255, g / 255, b / 255, a];
}

interface Colors {
  fg: string;
  line: string;
  policy: string;
  /** 라벨 헤일로·평면도 범례의 그라디언트 스톱 — 토큰이 준 문자열 그대로다
   * (color-source 가드: 조립하지 않는다). 헤일로·안개의 바탕은 **카드**다 —
   * 표면이 카드 위에 산다(2026-08-19, 메인·백테스트 문법 정렬). */
  card: string;
  lo: string;
  hi: string;
  /** 셰이더 유니폼 — 램프 두 스톱·스크림·메시 후보 둘(라이트=카드, 다크=잉크). */
  loVec: Vec4;
  hiVec: Vec4;
  scrimVec: Vec4;
  cardVec: Vec4;
  fgVec: Vec4;
  /** 캔버스 라벨의 서체 — 화면 나머지와 같은 스택(Pretendard). */
  font: string;
}

/** 캔버스·셰이더가 쓸 실색. 안 풀린 토큰은 여기서 죽는다 — `--sr-*` 가 :root 로
 * 올라가 조용히 무효가 된 것이 이 리포의 3회 재발 결함이다(surface-tokens
 * 가드). 마운트 이펙트에서 불려 ErrorBoundary 가 잡는다. */
function resolveColors(el: HTMLElement): Colors {
  const cs = getComputedStyle(el);
  const pick = (name: string): string => {
    const v = cs.getPropertyValue(name).trim();
    if (!v || v.includes('var(')) {
      throw new Error(`커브 표면: 토큰 ${name} 이 실색으로 풀리지 않았어요`);
    }
    return v;
  };
  const lo = pick('--sr-s3d-lo');
  const hi = pick('--sr-s3d-hi');
  const card = pick('--sr-card');
  return {
    fg: pick('--color-fg'),
    line: pick('--color-bgLine'),
    policy: pick('--sr-ref-policy'),
    card,
    lo,
    hi,
    loVec: cssColorToVec(lo),
    hiVec: cssColorToVec(hi),
    scrimVec: cssColorToVec(pick('--sr-scrim')),
    cardVec: cssColorToVec(card),
    fgVec: cssColorToVec(pick('--color-fg')),
    font: cs.fontFamily || 'sans-serif',
  };
}

interface Hover {
  poolId: string;
  ridge: number;
  tenor: number;
}

/** 짚은 날짜의 기준금리 — steps 는 결정이 발효된 모서리들이고, `through` 를
 * 지나면 백엔드가 보증하지 않으므로 null 이다(정책선 규약 그대로). */
function policyAt(policy: PolicyStep | undefined, date: string): number | null {
  if (!policy?.steps?.length || date > policy.through) return null;
  let v: number | null = null;
  for (const s of policy.steps) {
    if (s.date <= date) v = s.rate;
    else break;
  }
  return v;
}

/** 일별 계열에서 짚은 날짜 이하의 마지막 값 — 이진 탐색, 값 선택이지 계산이
 * 아니다(§16). */
function lastOnOrBefore(
  series: { dates: string[]; values: (number | null)[] } | null | undefined,
  date: string,
): number | null {
  if (!series?.dates.length) return null;
  let lo = 0;
  let hi = series.dates.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const m = (lo + hi) >> 1;
    if (series.dates[m] <= date) {
      ans = m;
      lo = m + 1;
    } else {
      hi = m - 1;
    }
  }
  return ans < 0 ? null : series.values[ans];
}

interface Scene {
  pool: SurfacePool;
  poolId: string;
  years: number[];
  /** 표본 격자 — 균등 격자 ∪ 실측 노드 연수. 노드가 격자 위에 있어야 테너
   * 방향 메시 선이 표면과 같은 높이를 지나 z-파이팅이 없다. */
  qs: number[];
  nodeCols: number[];
  /** 기준테너 등간격 축의 사상 — 연수 → 화면 x01 [OWNER 2026-08-19]. */
  toAxis: (y: number) => number;
  /** 테너별 52주(최근 252관측) 고저 — 표의 52주와 같은 창. 값은 pool.z 원값. */
  band52: ({ lo: number; hi: number } | null)[];
  /** [능선][표본] — PCHIP 표본화 + 그리기 전용 평활, 구멍은 null. */
  ridges: (number | null)[][];
  dom: { min: number; max: number };
  /** 실측 극값(패딩 전) — 범례가 말하는 수. 도메인 끝값은 6% 패딩이 섞인
   * 합성수라 시장에 찍힌 적이 없다(실측 지적: "0.4436%" 는 아무도 안 찍었다). */
  ext: { min: number; max: number };
  yearMarks: { r: number; year: string }[];
}

/* ── WebGL — 표면 한 장을 위한 최소한 ──────────────────────────────────────
 * 버텍스 셰이더는 `projectFast`+`toScreen` 의 직역이다. 여기 산수를 바꾸면
 * 반드시 저쪽도 같이 바꿔야 한다 — 주석 층이 CPU 로 같은 식을 쓴다. */

const VS = `
attribute vec3 aGrid;
attribute vec3 aNormal;
attribute float aInv;
uniform vec2 uYaw;
uniform vec2 uPitch;
uniform vec3 uSpan;
uniform float uPersp;
uniform vec4 uFit;
uniform vec2 uCanvas;
uniform float uBias;
varying float vY;
varying float vInv;
varying vec3 vN;
varying float vDepth;
void main() {
  float X = (aGrid.x - 0.5) * uSpan.x;
  float Y = aGrid.y * uSpan.y;
  float Z = (aGrid.z - 0.5) * uSpan.z;
  float xv = X * uYaw.x + Z * uYaw.y;
  float zv = -X * uYaw.y + Z * uYaw.x;
  float zview = zv * uPitch.y + Y * uPitch.x;
  float k = uPersp / (uPersp - zview);
  float sx = xv * k * uFit.x + uFit.z;
  float sy = (zv * uPitch.x - Y * uPitch.y) * k * uFit.y + uFit.w;
  gl_Position = vec4(sx / uCanvas.x * 2.0 - 1.0, 1.0 - sy / uCanvas.y * 2.0, -zview * 0.25 + uBias, 1.0);
  vY = aGrid.y;
  vInv = aInv;
  vN = aNormal;
  vDepth = zview;
}`;

const FS = `
// highp — 정점 셰이더의 기본과 맞춘다. 둘이 다르면 공유 유니폼(uYaw)의
// 정밀도 불일치로 링크가 실패한다(실측 2026-08-18, ANGLE/D3D).
precision highp float;
uniform vec3 uLo;
uniform vec3 uHi;
uniform vec4 uScrim;
uniform vec2 uYaw;
uniform float uMode;
uniform vec4 uLineColor;
uniform vec3 uBg;
varying float vY;
varying float vInv;
varying vec3 vN;
varying float vDepth;
void main() {
  if (uMode > 0.5) {
    gl_FragColor = uLineColor;
    return;
  }
  float nx = vN.x * uYaw.x + vN.z * uYaw.y;
  float nz = -vN.x * uYaw.y + vN.z * uYaw.x;
  vec3 n = normalize(vec3(nx, vN.y, nz));
  float b = max(dot(n, normalize(vec3(-0.42, 0.85, 0.31))), 0.0);
  float dark = (1.0 - min(0.18 + 0.82 * b, 1.0)) * 0.22 + vInv * 0.2;
  vec3 col = mix(uLo, uHi, vY);
  col = mix(col, uScrim.rgb, clamp(dark * uScrim.a, 0.0, 1.0));
  // 공기원근 — 먼 능선을 바탕 쪽으로 살짝 물린다. NYT 의 결이 이렇게 가라앉는다.
  float fog = clamp(0.5 - vDepth * 0.38, 0.0, 1.0) * 0.14;
  col = mix(col, uBg, fog);
  gl_FragColor = vec4(col, 1.0);
}`;

interface GlState {
  gl: WebGLRenderingContext;
  prog: WebGLProgram;
  u: Record<string, WebGLUniformLocation | null>;
  aGrid: number;
  aNormal: number;
  aInv: number;
  gridBuf: WebGLBuffer;
  normalBuf: WebGLBuffer;
  invBuf: WebGLBuffer;
  triBuf: WebGLBuffer;
  triCount: number;
  timeBuf: WebGLBuffer;
  timeCount: number;
  tenorBuf: WebGLBuffer;
  tenorCount: number;
}

function compile(gl: WebGLRenderingContext, type: number, src: string): WebGLShader {
  const sh = gl.createShader(type);
  if (!sh) throw new Error('커브 표면: 셰이더를 만들 수 없어요');
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    throw new Error(`커브 표면: 셰이더 컴파일 실패 — ${gl.getShaderInfoLog(sh) ?? ''}`);
  }
  return sh;
}

function initGl(canvas: HTMLCanvasElement): Omit<
  GlState,
  'triCount' | 'timeCount' | 'tenorCount'
> {
  const gl = canvas.getContext('webgl', {
    antialias: true,
    alpha: true,
    premultipliedAlpha: true,
  });
  if (!gl) throw new Error('커브 표면: 이 브라우저에서 WebGL 을 쓸 수 없어요');
  /* 정점이 6.5만을 넘는다(일별 능선 × 표본) — 32비트 인덱스가 필수다.
   * 사실상 모든 데스크톱 GPU 가 지원한다. */
  if (!gl.getExtension('OES_element_index_uint')) {
    throw new Error('커브 표면: 32비트 인덱스 확장이 없는 GPU 예요');
  }
  const prog = gl.createProgram();
  if (!prog) throw new Error('커브 표면: GL 프로그램을 만들 수 없어요');
  gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VS));
  gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FS));
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    throw new Error(`커브 표면: GL 링크 실패 — ${gl.getProgramInfoLog(prog) ?? ''}`);
  }
  gl.useProgram(prog);
  const u: Record<string, WebGLUniformLocation | null> = {};
  for (const name of [
    'uYaw', 'uPitch', 'uSpan', 'uPersp', 'uFit', 'uCanvas', 'uBias',
    'uLo', 'uHi', 'uScrim', 'uMode', 'uLineColor', 'uBg',
  ]) {
    u[name] = gl.getUniformLocation(prog, name);
  }
  const mk = () => {
    const b = gl.createBuffer();
    if (!b) throw new Error('커브 표면: GL 버퍼를 만들 수 없어요');
    return b;
  };
  return {
    gl,
    prog,
    u,
    aGrid: gl.getAttribLocation(prog, 'aGrid'),
    aNormal: gl.getAttribLocation(prog, 'aNormal'),
    aInv: gl.getAttribLocation(prog, 'aInv'),
    gridBuf: mk(),
    normalBuf: mk(),
    invBuf: mk(),
    triBuf: mk(),
    timeBuf: mk(),
    tenorBuf: mk(),
  };
}

/** 씬 → 지오메트리. 풀이 바뀔 때 **한 번**이다 — 프레임 경로가 아니다.
 * 구멍(null)이 낀 셀은 삼각형을 만들지 않는다: 메우면 없는 값이 면이 된다. */
function buildGeometry(scene: Scene): {
  grid: Float32Array;
  normal: Float32Array;
  inv: Float32Array;
  tris: Uint32Array;
  timeLines: Uint32Array;
  tenorLines: Uint32Array;
} {
  const { ridges, qs, dom, nodeCols, pool, toAxis } = scene;
  const R = ridges.length;
  const S = qs.length;
  const span = dom.max - dom.min || 1;
  const grid = new Float32Array(R * S * 3);
  const normal = new Float32Array(R * S * 3);
  const inv = new Float32Array(R * S);
  const ok = new Uint8Array(R * S);

  for (let r = 0; r < R; r++) {
    const z01 = R === 1 ? 1 : r / (R - 1);
    const invFlag = (pool.inversionBp[r] ?? 0) < 0 ? 1 : 0;
    for (let c = 0; c < S; c++) {
      const k = r * S + c;
      const v = ridges[r][c];
      grid[k * 3] = toAxis(qs[c]);
      grid[k * 3 + 1] = v == null ? 0 : (v - dom.min) / span;
      grid[k * 3 + 2] = z01;
      inv[k] = invFlag;
      ok[k] = v == null ? 0 : 1;
    }
  }

  /* 법선 — 중앙차분(모서리는 한쪽), 월드 단위. 이웃이 구멍이면 자기 값으로. */
  const hAt = (r: number, c: number, k: number) => (ok[r * S + c] ? grid[(r * S + c) * 3 + 1] : grid[k * 3 + 1]);
  for (let r = 0; r < R; r++) {
    for (let c = 0; c < S; c++) {
      const k = r * S + c;
      const cm = Math.max(0, c - 1);
      const cp = Math.min(S - 1, c + 1);
      const rm = Math.max(0, r - 1);
      const rp = Math.min(R - 1, r + 1);
      const gx =
        ((hAt(r, cp, k) - hAt(r, cm, k)) * SPAN_Y) /
        (((toAxis(qs[cp]) - toAxis(qs[cm])) || 1) * SPAN_X);
      const gz =
        ((hAt(rp, c, k) - hAt(rm, c, k)) * SPAN_Y) /
        ((((rp - rm) / Math.max(1, R - 1)) || 1) * SPAN_Z);
      const len = Math.hypot(gx, 1, gz);
      normal[k * 3] = -gx / len;
      normal[k * 3 + 1] = 1 / len;
      normal[k * 3 + 2] = -gz / len;
    }
  }

  const tris: number[] = [];
  for (let r = 0; r < R - 1; r++) {
    for (let c = 0; c < S - 1; c++) {
      const k00 = r * S + c;
      const k01 = k00 + 1;
      const k10 = k00 + S;
      const k11 = k10 + 1;
      if (ok[k00] && ok[k01] && ok[k10] && ok[k11]) {
        tris.push(k00, k10, k11, k00, k11, k01);
      }
    }
  }

  /* 시간 메시 — 영업월마다 한 줄. 오늘 능선은 위층이 굵게 그리므로 뺀다. */
  const timeLines: number[] = [];
  for (let r = 0; r < R - 1; r += TIME_MESH_EVERY) {
    for (let c = 0; c < S - 1; c++) {
      if (ok[r * S + c] && ok[r * S + c + 1]) timeLines.push(r * S + c, r * S + c + 1);
    }
  }
  /* 테너 메시 — 실측 노드 열 위로만(격자에 노드 열이 실재한다). */
  const tenorLines: number[] = [];
  for (const c of nodeCols) {
    if (c < 0) continue;
    for (let r = 0; r < R - 1; r++) {
      if (ok[r * S + c] && ok[(r + 1) * S + c]) tenorLines.push(r * S + c, (r + 1) * S + c);
    }
  }

  return {
    grid,
    normal,
    inv,
    tris: new Uint32Array(tris),
    timeLines: new Uint32Array(timeLines),
    tenorLines: new Uint32Array(tenorLines),
  };
}

export function Surface3D({ policy }: { policy?: PolicyStep }) {
  const [payload, setPayload] = useState<Surface3DPayload>();
  const [error, setError] = useState<string>();
  const [retrying, setRetrying] = useState(false);

  const load = () => {
    setError(undefined);
    setRetrying(true);
    fetchSurface3D()
      .then(setPayload)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setRetrying(false));
  };

  useEffect(() => {
    let alive = true;
    fetchSurface3D()
      .then((p) => alive && setPayload(p))
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, []);

  /* 로딩·에러도 **카드의 자리**에서 선다 — 한 줄짜리 상태가 620px 캔버스로
     바뀌면 화면 전체가 튄다(실측 지적). 480 은 플롯 최소 높이(380)+카드 머리
     어림 — 정확할 필요 없이 점프를 죽일 만큼이면 된다. */
  if (error) {
    return (
      <VStack
        className="sr-card"
        width="100%"
        minHeight={480}
        justifyContent="center"
        alignItems="center"
      >
        <ErrorState what="커브 표면" detail={error} onRetry={load} retrying={retrying} />
      </VStack>
    );
  }
  if (!payload) {
    return (
      <VStack
        className="sr-card"
        width="100%"
        minHeight={480}
        justifyContent="center"
        alignItems="center"
      >
        <LoadingState what="커브 표면" />
      </VStack>
    );
  }
  return <SurfaceBody payload={payload} policy={policy} />;
}

function SurfaceBody({ payload, policy }: { payload: Surface3DPayload; policy?: PolicyStep }) {
  const { scheme } = useScheme();
  const [measureRef, w] = useMeasure<HTMLDivElement>();

  /* 높이는 **추정하지 않고 잰다** (2026-08-19, critique 3차 P1). 이전 판은
   * `innerHeight − top − 44` 로 어림했는데 실제 제약은 100vh flex 열이라
   * 흔한 창 높이(실측 855)에서 ~28px 어긋나 앞줄 테너·연도 라벨이 카드
   * 밖으로 잘렸다. 호스트가 카드의 남는 세로를 flex 로 받고(§8.13 의
   * useFillHeight 관용구), 캔버스는 그 실측을 쓴다. */
  const [fillRef, hostH] = useFillHeight(480);
  const ref = useCallback(
    (node: HTMLDivElement | null) => {
      measureRef(node);
      fillRef(node);
    },
    [measureRef, fillRef],
  );

  const [tab, setTab] = useState<PoolTab>(() => {
    const s = recall('sr-s3d-pool');
    return s === 'govt' || s === 'credit' || s === 'swap' || s === 'crdsp' || s === 'bss'
      ? s
      : 'swap';
  });
  const [creditType, setCreditType] = useState<string>(
    () => recall('sr-s3d-credit') ?? payload.creditDefault,
  );
  /* 카메라(요·피치·줌)는 세션이 기억하지 않는다 [OWNER 2026-08-19 — "항상
     기본각으로"]. 어제 손으로 돌려둔 요 91°/피치 2° 같은 이름 없는 각도로
     돌아오는 것은 남긴 사람 말고는 모두에게 함정이었다(critique 3차) — 풀·
     테너·고스트(무엇을 보나)는 기억하고, 어떻게 보나는 늘 기본에서 시작한다. */
  const [yaw, setYaw] = useState<number>(YAW_DEFAULT);
  const [pitch, setPitch] = useState<number>(PITCH_DEG);
  const [zoom, setZoom] = useState<number>(1);
  /** 선택 테너 [OWNER 2026-08-18 — "몇 년 테너 … 검정 그래프로"] — 라벨로 든다. */
  const [selTenor, setSelTenor] = useState<string | null>(() => recall('sr-s3d-tenor'));
  /** 고스트 날짜 — 표면을 클릭해 오늘 커브와 겹쳐 보는 그날. */
  const [ghostDate, setGhostDate] = useState<string | null>(() => recall('sr-s3d-ghost'));
  const [hover, setHover] = useState<Hover | null>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => remember('sr-s3d-pool', tab), [tab]);
  useEffect(() => remember('sr-s3d-credit', creditType), [creditType]);
  useEffect(() => remember('sr-s3d-tenor', selTenor ?? ''), [selTenor]);
  useEffect(() => remember('sr-s3d-ghost', ghostDate ?? ''), [ghostDate]);

  const poolId =
    tab === 'credit' ? `credit:${creditType}` : tab === 'crdsp' ? `crd:${creditType}` : tab;
  const pool = payload.pools[poolId];

  /* 표본화·도메인·연도 표식은 풀이 바뀔 때 한 번. */
  const scene: Scene | null = useMemo(() => {
    if (!pool || pool.tenors.length < 2 || pool.dates.length < 2) return null;
    const years = pool.tenors.map((t) => t.years);
    /* 표본은 **축 공간에서 균등**하게 뽑는다 — 등간격 축에서 연수 균등 표본을
       쓰면 5~10Y 구간의 표본이 좁은 화면 폭에 몰려 결이 뭉치고, 1~1.5Y 는
       성겨진다. 값 평가는 여전히 연수(qs)로 한다. */
    const axis = tenorAxis(years);
    const base = sampleGrid(0, 1, SAMPLES).map(axis.toYears);
    const qs = Array.from(
      new Set([...base, ...years].map((v) => Math.round(v * 1e6) / 1e6)),
    ).sort((a, b) => a - b);
    const nodeCols = years.map((y) => qs.findIndex((q) => Math.abs(q - y) < 1e-6));
    /* 평활은 그리기 전용 — hover·단면·수치는 pool.z(원값)만 읽는다. */
    const ridges = smoothRidges(sampleRidges(years, pool.z, qs));
    /* 기준금리는 % 축에서만 도메인에 든다 — bp 풀에 %를 섞으면 축이 거짓말한다. */
    const dom = domainOf(pool.z, pool.unit === '%' ? [policy?.latest] : []);
    /* 실측 극값 — 데이터만, 기준금리·패딩 제외. 범례의 답값이다. */
    let extMin = Infinity;
    let extMax = -Infinity;
    for (const row of pool.z) {
      for (const v of row) {
        if (v == null) continue;
        if (v < extMin) extMin = v;
        if (v > extMax) extMax = v;
      }
    }
    const ext = Number.isFinite(extMin) ? { min: extMin, max: extMax } : { ...dom };
    /* 52주 띠 [OWNER 2026-08-19 — 계기화]: 테너마다 최근 252관측의 고저.
       오늘 노드가 이 띠의 어디쯤인지가 "지금이 어디쯤인가"의 답이다. */
    const band52 = years.map((_, t) => {
      const zs = pool.z[t];
      let lo = Infinity;
      let hi = -Infinity;
      let n = 0;
      for (let i = zs.length - 1; i >= 0 && n < 252; i--) {
        const v = zs[i];
        if (v == null) continue;
        n++;
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
      return n > 0 ? { lo, hi } : null;
    });
    const yearMarks: { r: number; year: string }[] = [];
    let prev = '';
    pool.dates.forEach((d, r) => {
      const y = d.slice(0, 4);
      if (y !== prev) {
        yearMarks.push({ r, year: y });
        prev = y;
      }
    });
    return { pool, poolId, years, qs, nodeCols, toAxis: axis.toAxis, band52, ridges, dom, ext, yearMarks };
  }, [pool, poolId, policy?.latest]);

  const width = Math.max(MIN_PLOT_W, w);
  /* 12 = 호스트 padding-top. 폭 비례 상한(0.52)은 넓고 낮은 창에서 원근
     왜곡을 막는 기존 규칙 그대로다. */
  const height = Math.round(Math.max(380, Math.min(hostH - 12, width * 0.52)));

  const glCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const underRef = useRef<HTMLCanvasElement | null>(null);
  const overRef = useRef<HTMLCanvasElement | null>(null);
  const glRef = useRef<GlState | null>(null);
  const geomKeyRef = useRef<string>('');
  const schemeRef = useRef(scheme);
  schemeRef.current = scheme;
  const interactingRef = useRef(false);
  const yawRef = useRef(yaw);
  const pitchRef = useRef(pitch);
  const zoomRef = useRef(zoom);
  const selTenorIdxRef = useRef<number | null>(null);
  const readoutRef = useRef<HTMLDivElement | null>(null);
  const cursorRef = useRef<{ x: number; y: number } | null>(null);
  const ghostRef = useRef<string | null>(ghostDate);
  ghostRef.current = ghostDate;
  const nodesRef = useRef<{ x: number; y: number; ridge: number; tenor: number }[]>([]);
  /** draw 가 이번 프레임에 쓴 투영 — 면 읽기(pickAt)가 같은 산수로 능선 위
   * 표본을 재투영할 때 쓴다. 따로 계산하면 그림과 리드아웃이 어긋난다. */
  const viewRef = useRef<{ cy: number; sy: number; sp: number; cp: number; fit: Fit } | null>(
    null,
  );
  const colorsRef = useRef<Colors | null>(null);
  const rafRef = useRef(0);
  const hoverRef = useRef<Hover | null>(null);
  hoverRef.current = hover;
  const sceneRef = useRef<Scene | null>(null);
  sceneRef.current = scene;

  /* GL 지오메트리 업로드 — 풀(씬)이 바뀔 때만. */
  const ensureGeometry = useCallback(() => {
    const canvas = glCanvasRef.current;
    const sc = sceneRef.current;
    if (!canvas || !sc) return null;
    let st = glRef.current;
    if (!st || st.gl.isContextLost()) {
      const base = initGl(canvas);
      st = { ...base, triCount: 0, timeCount: 0, tenorCount: 0 };
      glRef.current = st;
      geomKeyRef.current = '';
    }
    const key = `${sc.poolId}:${sc.ridges.length}:${sc.qs.length}`;
    if (geomKeyRef.current !== key) {
      const g = buildGeometry(sc);
      const { gl } = st;
      gl.bindBuffer(gl.ARRAY_BUFFER, st.gridBuf);
      gl.bufferData(gl.ARRAY_BUFFER, g.grid, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, st.normalBuf);
      gl.bufferData(gl.ARRAY_BUFFER, g.normal, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, st.invBuf);
      gl.bufferData(gl.ARRAY_BUFFER, g.inv, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, st.triBuf);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, g.tris, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, st.timeBuf);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, g.timeLines, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, st.tenorBuf);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, g.tenorLines, gl.STATIC_DRAW);
      st.triCount = g.tris.length;
      st.timeCount = g.timeLines.length;
      st.tenorCount = g.tenorLines.length;
      geomKeyRef.current = key;
    }
    return st;
  }, []);

  const draw = useCallback(() => {
    const sc = sceneRef.current;
    const colors = colorsRef.current;
    const glCanvas = glCanvasRef.current;
    const under = underRef.current;
    const over = overRef.current;
    if (!sc || !colors || !glCanvas || !under || !over) return;
    const st = ensureGeometry();
    if (!st) return;

    const yawNow = yawRef.current;
    const pitchNow = pitchRef.current;
    const yawRad = (yawNow * Math.PI) / 180;
    const cy = Math.cos(yawRad);
    const sy = Math.sin(yawRad);
    const pitchRad = (pitchNow * Math.PI) / 180;
    const sp = Math.sin(pitchRad);
    const cp = Math.cos(pitchRad);
    /* 평면도(피치 70°↑)에서는 축별로 화면을 채운다 — 70→90 에서 매끄럽게.
       그 위에 드래그 줌 — 화면 중앙 기준의 순수 배율이다. */
    const baseFit: Fit = fitTransform(
      { w: width, h: height },
      PAD,
      projectedBounds(yawNow, yawNow, pitchNow),
      Math.min(1, Math.max(0, (pitchNow - 70) / 20)),
    );
    const zNow = zoomRef.current;
    const fit: Fit =
      zNow === 1
        ? baseFit
        : {
            scaleX: baseFit.scaleX * zNow,
            scaleY: baseFit.scaleY * zNow,
            ox: (width / 2) * (1 - zNow) + baseFit.ox * zNow,
            oy: (height / 2) * (1 - zNow) + baseFit.oy * zNow,
          };
    viewRef.current = { cy, sy, sp, cp, fit };
    const dpr = window.devicePixelRatio || 1;
    const pw = Math.round(width * dpr);
    const ph = Math.round(height * dpr);

    const { pool: p, years, qs, ridges, dom, ext, yearMarks, toAxis } = sc;
    const R = ridges.length;
    const S = qs.length;
    const span = dom.max - dom.min || 1;

    /* ── 아래층: 바닥 연도선 — 표면이 이 위를 덮는다. ── */
    {
      /* 폭·높이 **둘 다** 본다 — 폭만 보면 높이만 변한 프레임에서 백킹이
         안 늘고, CSS 박스에 눌린 이전 그림의 아랫단이 유령으로 남는다
         (실측 2026-08-19: 평면도 하단에 이전 뷰의 축·점선이 뭉개져 표류). */
      if (under.width !== pw || under.height !== ph) {
        under.width = pw;
        under.height = ph;
      }
      const ctx = under.getContext('2d');
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      /* NYT 예시의 바닥은 표면보다 **넓은 격자**다 — 축 상자 안에 그래프가
         들어있다는 문법 [OWNER 2026-08-18]. 연도선은 테너 범위 밖까지 연장하고
         테너 방향 바닥선도 같이 깐다. */
      /* 축은 헤어라인이 아니라 **잉크 회색**이다 [OWNER 2026-08-18 — "생각보다도
         더 진한 회색으로 해야 눈에 보일 듯"]. bgLine 은 카드 경계용이라 바닥
         격자에 쓰면 표면 옆에서 사라진다(실측). */
      ctx.strokeStyle = colors.fg;
      ctx.lineWidth = 1;
      /* 격자 농도 0.5/0.38 → 0.3/0.2 [OWNER 2026-08-19 — "커브 못생김" 정비,
         격자 다이어트. 12차의 "더 진하게"를 부분 대체 — 그때는 보라 핀·설명
         문단과 함께였고 지금은 표면이 커져 격자가 표면과 경쟁한다(실측)].
         라벨 잉크(0.85)는 그대로 — 다이어트는 선이지 글자가 아니다. */
      ctx.globalAlpha = 0.3;
      /* 축 프레임은 오블리크의 문법이다 — 평면도에서는 표면이 불투명 사각으로
         전면을 덮어 바닥선이 보일 자리가 없고, 원근이 만드는 바닥-표면 틈에
         회색 브래킷 토막만 남았다(실측). 평면도에서는 바닥선을 통째로 걷는다
         [OWNER 2026-08-19] — 연도는 하단 라벨이, 테너는 우측 라벨이 말한다. */
      if (pitchNow <= 70) {
        const overX = 0.1;
        const overZ = 0.05;
        for (const { r } of yearMarks) {
          const z01 = R === 1 ? 1 : r / (R - 1);
          const a = toScreen(projectFast(-overX, 0, z01, cy, sy, sp, cp), fit);
          const b = toScreen(projectFast(1 + overX, 0, z01, cy, sy, sp, cp), fit);
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
        ctx.globalAlpha = 0.2;
        /* 등간격 축에서는 **모든 기준테너**가 제 칸의 선을 갖는다 [OWNER
           2026-08-19 — "바닥에 1.5년 선 어디감"]. 실연수 축 시절의 1.5Y 제외
           (촘촘이 정리)는 등간격에서 근거를 잃었다 — 빈 칸이 더 어색하다. */
        for (const tn of sc.pool.tenors) {
          const x01n = toAxis(tn.years);
          const a = toScreen(projectFast(x01n, 0, -overZ, cy, sy, sp, cp), fit);
          const b = toScreen(projectFast(x01n, 0, 1 + overZ, cy, sy, sp, cp), fit);
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
      ctx.globalAlpha = 1;
    }

    /* ── 가운데층: 표면 (WebGL). 프레임 비용 = 유니폼 갱신 + 드로콜 셋. ── */
    {
      const { gl } = st;
      if (glCanvas.width !== pw || glCanvas.height !== ph) {
        glCanvas.width = pw;
        glCanvas.height = ph;
      }
      gl.viewport(0, 0, pw, ph);
      gl.clearColor(0, 0, 0, 0);
      gl.enable(gl.DEPTH_TEST);
      gl.depthFunc(gl.LEQUAL);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.useProgram(st.prog);

      gl.bindBuffer(gl.ARRAY_BUFFER, st.gridBuf);
      gl.enableVertexAttribArray(st.aGrid);
      gl.vertexAttribPointer(st.aGrid, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, st.normalBuf);
      gl.enableVertexAttribArray(st.aNormal);
      gl.vertexAttribPointer(st.aNormal, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, st.invBuf);
      gl.enableVertexAttribArray(st.aInv);
      gl.vertexAttribPointer(st.aInv, 1, gl.FLOAT, false, 0, 0);

      gl.uniform2f(st.u.uYaw, cy, sy);
      gl.uniform2f(st.u.uPitch, Math.sin(pitchRad), Math.cos(pitchRad));
      gl.uniform3f(st.u.uSpan, SPAN_X, SPAN_Y, SPAN_Z);
      gl.uniform1f(st.u.uPersp, PERSP);
      gl.uniform4f(st.u.uFit, fit.scaleX, fit.scaleY, fit.ox, fit.oy);
      gl.uniform2f(st.u.uCanvas, width, height);
      gl.uniform3f(st.u.uLo, colors.loVec[0], colors.loVec[1], colors.loVec[2]);
      gl.uniform3f(st.u.uHi, colors.hiVec[0], colors.hiVec[1], colors.hiVec[2]);
      gl.uniform4f(
        st.u.uScrim,
        colors.scrimVec[0],
        colors.scrimVec[1],
        colors.scrimVec[2],
        colors.scrimVec[3],
      );
      gl.uniform3f(st.u.uBg, colors.cardVec[0], colors.cardVec[1], colors.cardVec[2]);

      /* 표면 — 불투명, 깊이 버퍼가 가림을 진다. */
      gl.disable(gl.BLEND);
      gl.uniform1f(st.u.uBias, 0);
      gl.uniform1f(st.u.uMode, 0);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, st.triBuf);
      gl.drawElements(gl.TRIANGLES, st.triCount, gl.UNSIGNED_INT, 0);

      /* 메시 — NYT 의 밝은 선. 라이트=카드(흰), 다크=잉크. 표면보다 살짝
       * 앞으로 밀어 z-파이팅을 피한다. 프리멀티플라이드 블렌딩. */
      const meshVec = schemeRef.current === 'dark' ? colors.fgVec : colors.cardVec;
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.uniform1f(st.u.uBias, -0.004);
      gl.uniform1f(st.u.uMode, 1);
      /* 메시는 결이지 골격이 아니다 — 0.5 는 라이트에서 판 경계선을, 다크에서는
         어두운 채움을 삼키는 와이어프레임을 만들었다(실측 2026-08-19). 다크가
         더 연한 이유: 다크의 잉크 메시는 채움(#26303c)과의 대비가 라이트의
         흰 메시보다 훨씬 세다. */
      const lineA = schemeRef.current === 'dark' ? 0.22 : 0.32;
      gl.uniform4f(
        st.u.uLineColor,
        meshVec[0] * lineA,
        meshVec[1] * lineA,
        meshVec[2] * lineA,
        lineA,
      );
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, st.timeBuf);
      gl.drawElements(gl.LINES, st.timeCount, gl.UNSIGNED_INT, 0);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, st.tenorBuf);
      gl.drawElements(gl.LINES, st.tenorCount, gl.UNSIGNED_INT, 0);
    }

    /* ── 위층: 주석 — 오늘 커브·hover·라벨·축·기준금리. ── */
    {
      if (over.width !== pw || over.height !== ph) {
        over.width = pw;
        over.height = ph;
      }
      const ctx = over.getContext('2d');
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      /* 캔버스 글자는 표면 위를 지날 수 있다 — 바탕(카드)색 헤일로가 어느 램프
         농도 위에서도 글자를 세운다(halo 는 데이터가 아니라 가독 장치다).
         fillStyle 은 부르는 쪽의 것을 그대로 쓴다. */
      const label = (text: string, x: number, y: number) => {
        ctx.strokeStyle = colors.card;
        ctx.lineWidth = 3;
        ctx.lineJoin = 'round';
        ctx.strokeText(text, x, y);
        ctx.fillText(text, x, y);
      };
      /* 라벨은 캔버스를 나가지 않는다 — 평면도의 축별 맞춤이 격자선 끝을
         화면 밖으로 밀면, 그 끝에 붙던 라벨(연도)이 통째로 사라졌다(실측). */
      const clampX = (x: number) => Math.min(width - 6, Math.max(6, x));
      const clampY = (y: number) => Math.min(height - 5, Math.max(13, y));

      /* 우측 거터는 좁은 자리에 네 부족이 산다 — asof 날짜·금리 눈금·기준금리
         라벨·(측면에서) 테너 라벨. 겹치면 제일 신선한 데이터 옆이 제일 지저분해
         진다(실측: "50bp"×날짜 겹침·테너 압착). 규칙: 먼저 선 라벨이 자리를
         갖고(claim), 떨굴 수 있는 것(눈금·테너)은 겹치면 건너뛰고, 떨굴 수
         없는 것(기준금리)은 한 칸 비켜 선다. */
      const placed: { x0: number; x1: number; y: number }[] = [];
      const overlapsPlaced = (x0: number, x1: number, y: number) =>
        placed.some((r) => Math.abs(r.y - y) < 11 && x0 < r.x1 + 4 && x1 > r.x0 - 4);
      const claim = (x0: number, x1: number, y: number) => {
        placed.push({ x0, x1, y });
      };

      const rowPath = (r: number): { x: number; y: number }[][] => {
        const z01 = R === 1 ? 1 : r / (R - 1);
        const segs: { x: number; y: number }[][] = [];
        let run: { x: number; y: number }[] = [];
        for (let c = 0; c < S; c++) {
          const v = ridges[r][c];
          if (v == null) {
            if (run.length > 1) segs.push(run);
            run = [];
            continue;
          }
          run.push(
            toScreen(
              projectFast(toAxis(qs[c]), (v - dom.min) / span, z01, cy, sy, sp, cp),
              fit,
            ),
          );
        }
        if (run.length > 1) segs.push(run);
        return segs;
      };
      const strokeSegs = (segs: { x: number; y: number }[][]) => {
        for (const seg of segs) {
          ctx.beginPath();
          ctx.moveTo(seg[0].x, seg[0].y);
          for (let i = 1; i < seg.length; i++) ctx.lineTo(seg[i].x, seg[i].y);
          ctx.stroke();
        }
      };

      /* 테너별 52주 띠 [OWNER 2026-08-19 — 계기화, "오늘 커브 뷰 전용"으로
         재판정]: 정면(|요|<15 — 연도 라벨이 걷히는 그 문턱)에서만 선다.
         오블리크의 fg 회색 띠는 축·격자와 같은 색족이라 "받침 기둥"으로
         오독됐다(critique 4차). 색은 램프의 틸(hi 토큰) — 이 표면이 소유한
         색족이라 가구와 갈린다. 끝 눈금이 고저를 값으로 세우고, **오늘 점**이
         "지금이 띠의 어디"를 마킹하며, '52주' 태그가 키를 화면에 둔다.
         값은 pool.z 원값의 최근 252관측 고저다. */
      if (pitchNow < 70 && Math.abs(yawNow) < 15) {
        let tagged = false;
        for (let t = 0; t < years.length; t++) {
          const b52 = sc.band52[t];
          if (!b52) continue;
          const x01n = toAxis(years[t]);
          const aPt = toScreen(
            projectFast(x01n, (b52.lo - dom.min) / span, 1, cy, sy, sp, cp),
            fit,
          );
          const bPt = toScreen(
            projectFast(x01n, (b52.hi - dom.min) / span, 1, cy, sy, sp, cp),
            fit,
          );
          ctx.strokeStyle = colors.hi;
          ctx.globalAlpha = 0.22;
          ctx.lineWidth = 5;
          ctx.lineCap = 'round';
          ctx.beginPath();
          ctx.moveTo(aPt.x, aPt.y);
          ctx.lineTo(bPt.x, bPt.y);
          ctx.stroke();
          ctx.lineCap = 'butt';
          ctx.globalAlpha = 0.55;
          ctx.lineWidth = 1.5;
          for (const e of [aPt, bPt]) {
            ctx.beginPath();
            ctx.moveTo(e.x - 4, e.y);
            ctx.lineTo(e.x + 4, e.y);
            ctx.stroke();
          }
          const today = p.z[t][R - 1];
          if (today != null) {
            const tp = toScreen(
              projectFast(x01n, (today - dom.min) / span, 1, cy, sy, sp, cp),
              fit,
            );
            ctx.beginPath();
            ctx.arc(tp.x, tp.y, 2.5, 0, Math.PI * 2);
            ctx.fillStyle = colors.hi;
            ctx.globalAlpha = 0.9;
            ctx.fill();
          }
          /* 키는 화면에 — 왼쪽 첫 띠의 위 끝, 왼쪽 여백 쪽으로(정면에서 그
             자리는 연도 라벨이 걷혀 비어 있다). */
          if (!tagged) {
            const topPt = bPt.y < aPt.y ? bPt : aPt;
            ctx.font = `11px ${colors.font}`;
            ctx.fillStyle = colors.hi;
            ctx.globalAlpha = 0.9;
            ctx.textAlign = 'right';
            const tw52 = ctx.measureText('52주').width;
            if (!overlapsPlaced(topPt.x - 8 - tw52, topPt.x - 8, topPt.y - 2)) {
              label('52주', topPt.x - 8, topPt.y - 2);
              claim(topPt.x - 8 - tw52, topPt.x - 8, topPt.y - 2);
            }
            tagged = true;
          }
        }
        ctx.globalAlpha = 1;
      }

      /* 오늘 커브 — 항상 굵은 잉크 + 날짜 (NYT 의 "Wednesday"). */
      {
        const segs = rowPath(R - 1);
        ctx.strokeStyle = colors.fg;
        ctx.globalAlpha = 0.9;
        ctx.lineWidth = 1.8;
        strokeSegs(segs);
        let endX = -Infinity;
        let endY = 0;
        for (const seg of segs) {
          for (const pt of seg) {
            if (pt.x > endX) {
              endX = pt.x;
              endY = pt.y;
            }
          }
        }
        if (Number.isFinite(endX)) {
          ctx.font = `600 11px ${colors.font}`;
          ctx.textAlign = 'left';
          ctx.fillStyle = colors.fg;
          const tw = ctx.measureText(p.asof).width;
          const tx = Math.min(endX + 6, width - tw - 4);
          const ty = clampY(endY + 3);
          label(p.asof, tx, ty);
          claim(tx, tx + tw, ty);
        }
        ctx.globalAlpha = 1;
      }

      /* 선택 테너의 역사 — 검은 라인 [OWNER — "검정 그래프로"]. NYT 가 단기금리
         역사에 쓰는 그 문법. 원값(pool.z)이다 — 데이터 진술이라 평활을 안 탄다. */
      /* 오늘 커브(정면) 뷰에서는 시계열 라인을 걷는다 [OWNER 2026-08-18 —
         "오늘 커브에서는 시계열 커브가 안 보이게"] — 정면에서 이 선은 화면
         안쪽으로 눕는 세로 낙서가 되어 오늘 커브를 가로지른다. */
      const selT = Math.abs(yawNow) < 15 ? null : selTenorIdxRef.current;
      if (selT != null && selT >= 0 && selT < years.length) {
        const x01n = toAxis(years[selT]);
        ctx.strokeStyle = colors.fg;
        ctx.lineWidth = 1.8;
        ctx.globalAlpha = 0.95;
        ctx.beginPath();
        let open = false;
        for (let r = 0; r < R; r++) {
          const v = p.z[selT][r];
          if (v == null) {
            open = false;
            continue;
          }
          const pt = toScreen(
            projectFast(x01n, (v - dom.min) / span, R === 1 ? 1 : r / (R - 1), cy, sy, sp, cp),
            fit,
          );
          if (!open) {
            ctx.moveTo(pt.x, pt.y);
            open = true;
          } else {
            ctx.lineTo(pt.x, pt.y);
          }
        }
        ctx.stroke();
        ctx.globalAlpha = 1;
      }

      /* 고스트 — 클릭으로 고른 날의 커브를 **앞평면에** 점선으로 겹친다
         [OWNER — "두 날짜 커브 비교"]. 데이터 진술이므로 그날 원값 노드의
         PCHIP 이다(시간 평활을 타지 않는다). */
      const gDate = ghostRef.current;
      if (gDate) {
        let gi = -1;
        for (let r = p.dates.length - 1; r >= 0; r--) {
          if (p.dates[r] <= gDate) {
            gi = r;
            break;
          }
        }
        if (gi >= 0) {
          const gxs: number[] = [];
          const gys: number[] = [];
          for (let ti = 0; ti < years.length; ti++) {
            const v = p.z[ti][gi];
            if (v != null) {
              gxs.push(years[ti]);
              gys.push(v);
            }
          }
          if (gxs.length >= 2) {
            const gv = pchipSample(gxs, gys, qs);
            ctx.strokeStyle = colors.fg;
            ctx.globalAlpha = 0.7;
            ctx.lineWidth = 1.6;
            ctx.setLineDash([5, 4]);
            ctx.beginPath();
            let open = false;
            let leftX = Infinity;
            let leftY = 0;
            for (let c = 0; c < qs.length; c++) {
              const v = gv[c];
              if (v == null) {
                open = false;
                continue;
              }
              const pt = toScreen(
                projectFast(toAxis(qs[c]), (v - dom.min) / span, 1, cy, sy, sp, cp),
                fit,
              );
              if (!open) {
                ctx.moveTo(pt.x, pt.y);
                open = true;
              } else {
                ctx.lineTo(pt.x, pt.y);
              }
              if (pt.x < leftX) {
                leftX = pt.x;
                leftY = pt.y;
              }
            }
            ctx.stroke();
            ctx.setLineDash([]);
            if (Number.isFinite(leftX)) {
              ctx.font = `600 11px ${colors.font}`;
              ctx.textAlign = 'right';
              ctx.fillStyle = colors.fg;
              const tw = ctx.measureText(p.dates[gi]).width;
              const tx = Math.max(leftX - 6, tw + 4);
              let ty = clampY(leftY + 3);
              if (overlapsPlaced(tx - tw, tx, ty)) ty = clampY(ty + 12);
              label(p.dates[gi], tx, ty);
              claim(tx - tw, tx, ty);
            }
            ctx.globalAlpha = 1;
          }
        }
      }

      /* 금통위 마커(바닥 핀 + 평면도 세로선)는 지웠다 [OWNER 2026-08-19 —
         "금통위 일정 넣던 보라색 선 빼버리자"]. 짚은 날의 기준금리는 여전히
         리드아웃이 말하고, 현재 레벨 점선은 아래 §기준금리 그대로다. */

      /* 실측 노드 — hover 가 집는 것. 드래그·트윈 중에는 쉰다. */
      if (!interactingRef.current) {
        const nodes: { x: number; y: number; ridge: number; tenor: number }[] = [];
        const T = years.length;
        for (let r = 0; r < R; r++) {
          const z01 = R === 1 ? 1 : r / (R - 1);
          for (let t = 0; t < T; t++) {
            const v = p.z[t][r];
            if (v == null) continue;
            const pt = toScreen(
              projectFast(toAxis(years[t]), (v - dom.min) / span, z01, cy, sy, sp, cp),
              fit,
            );
            nodes.push({ x: pt.x, y: pt.y, ridge: r, tenor: t });
          }
        }
        nodesRef.current = nodes;
      }

      /* 짚은 능선 — 표면 위 단면 + 노드 점. 점은 언제나 **실측 노드**에 선다
         — 구역(노드 사이)을 짚어도 값의 자리는 노드다(pickAt 의 규칙). */
      const hov = hoverRef.current;
      if (hov && hov.poolId === sc.poolId) {
        ctx.strokeStyle = colors.fg;
        ctx.lineWidth = 2;
        strokeSegs(rowPath(hov.ridge));
        const n = nodesRef.current.find(
          (q) => q.ridge === hov.ridge && q.tenor === hov.tenor,
        );
        if (n) {
          ctx.beginPath();
          ctx.arc(n.x, n.y, 3, 0, Math.PI * 2);
          ctx.fillStyle = colors.fg;
          ctx.fill();
        }
      }

      /* 라벨 — 서로 12px 안에 겹치는 연도만 건너뛴다(올해가 지워지던 전작
         규칙의 교훈). */
      /* 라벨은 **축 프레임**이다 [OWNER 2026-08-18 — "연도·테너·금리 레벨을
         축으로 놓고 그 안에 3D 그래프"]. 표면 좌표에 그대로 찍으면 지형과
         겹친다(실측) — 격자선의 바깥 끝에서 플롯 중심 반대 방향으로 한 뼘 더
         밀어, 어느 각도에서도 그래프 바깥에 선다. */
      ctx.fillStyle = colors.fg;
      ctx.font = `11px ${colors.font}`;
      ctx.globalAlpha = 0.85;
      const cxm = width / 2;
      const cym = height / 2;
      const outward = (pt: { x: number; y: number }, d: number) => {
        const dx = pt.x - cxm;
        const dy = pt.y - cym;
        const L = Math.hypot(dx, dy) || 1;
        return { x: pt.x + (dx / L) * d, y: pt.y + (dy / L) * d };
      };
      /* 정면(오늘 커브) 근처에서는 연도 라벨을 걷는다 — 시간축이 화면 안쪽으로
         누워 라벨이 표면 위에 적층됐다(critique 3차). 시계열 라인을 걷는 것과
         같은 문턱(|요|<15)이다. */
      if (Math.abs(yawNow) >= 15) {
        /* 위치를 먼저 다 계산하고 **스트라이드**로 솎는다 — 이전의 선착순
           34px 디듀프는 확대할 때마다 살아남는 연도가 임의로 바뀌었다(critique
           3차). k 년마다 하나면 2016·2018·2020… 처럼 규칙적으로 선다. */
        const marks = yearMarks.map(({ r, year }) => {
          const z01 = R === 1 ? 1 : r / (R - 1);
          const base = toScreen(projectFast(-0.1, 0, z01, cy, sy, sp, cp), fit);
          const q = outward(base, 16);
          return { year, base, qx: clampX(q.x), qy: clampY(q.y + 3) };
        });
        let strideK = 1;
        while (strideK < marks.length) {
          let ok = true;
          for (let i = strideK; i < marks.length; i += strideK) {
            const a = marks[i - strideK];
            const m = marks[i];
            if (Math.abs(m.qy - a.qy) < 12 && Math.abs(m.qx - a.qx) < 34) {
              ok = false;
              break;
            }
          }
          if (ok) break;
          strideK++;
        }
        for (let i = 0; i < marks.length; i += strideK) {
          const m = marks[i];
          const align =
            m.qx <= 7 ? 'left' : m.qx >= width - 7 ? 'right' : m.qx <= m.base.x ? 'right' : 'left';
          const tw = ctx.measureText(m.year).width;
          const x0 = align === 'right' ? m.qx - tw : m.qx;
          if (overlapsPlaced(x0, x0 + tw, m.qy)) continue;
          ctx.textAlign = align;
          label(m.year, m.qx, m.qy);
          claim(x0, x0 + tw, m.qy);
        }
      }
      ctx.textAlign = 'center';
      /* 테너 라벨은 **우선순위 솎임**이다 (critique 4차 — 선착순은 국고에서
         5Y·10Y·30Y 를 떨궜다): 축의 양 끝이 최우선, 다음 벤치마크(1·3·5·10·30),
         다음 2·20, 나머지(9M·1.5Y·7Y…)가 먼저 양보한다. 자리는 그려질 위치와
         무관하게 우선순위 순으로 잡는다 — 접힌 축(측면)에서는 상위 몇만 산다. */
      {
        const tenorsN = sc.pool.tenors.length;
        const tmarks = sc.pool.tenors.map((t, i) => {
          const base = toScreen(
            projectFast(toAxis(t.years), 0, 1.05, cy, sy, sp, cp),
            fit,
          );
          const q = outward(base, 18);
          const pri =
            i === 0 || i === tenorsN - 1
              ? 0
              : [1, 3, 5, 10, 30].includes(t.years)
                ? 1
                : [2, 20].includes(t.years)
                  ? 2
                  : 3;
          return { t: t.t, qx: clampX(q.x), qy: clampY(q.y + 4), pri, i };
        });
        const won: { x: number; y: number }[] = [];
        for (const m of [...tmarks].sort((a, b) => a.pri - b.pri || a.i - b.i)) {
          if (won.some((w2) => Math.abs(w2.y - m.qy) < 12 && Math.abs(w2.x - m.qx) < 26)) {
            continue;
          }
          const tw = ctx.measureText(m.t).width;
          if (overlapsPlaced(m.qx - tw / 2, m.qx + tw / 2, m.qy)) continue;
          label(m.t, m.qx, m.qy);
          claim(m.qx - tw / 2, m.qx + tw / 2, m.qy);
          won.push({ x: m.qx, y: m.qy });
        }
      }

      /* 금리 축 — 오른쪽 앞 모서리 수직선 + 정수 눈금 (NYT 문법). 위에서 보는
         각(피치 높음)에서는 수직 축이 점으로 접혀 라벨만 뭉치므로 걷는다. */
      const bp = p.unit === 'bp';
      if (pitchNow < 70) {
        const a = toScreen(projectFast(1, 0, 1, cy, sy, sp, cp), fit);
        const b = toScreen(projectFast(1, 1, 1, cy, sy, sp, cp), fit);
        ctx.strokeStyle = colors.fg;
        ctx.globalAlpha = 0.6;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        ctx.globalAlpha = 0.85;
        /* 눈금은 축의 **왼쪽** 레인 — 오른쪽은 asof 날짜·기준금리 라벨의
           거터라, 오늘 레벨에 가장 가까운 눈금이 밀려났다(critique 4차: 스왑
           기본 뷰에서 4% 탈락, 오늘 10Y 4.15%). 표면 위를 지나므로 헤일로. */
        ctx.textAlign = 'right';
        ctx.fillStyle = colors.fg;
        /* 눈금 ~4개 목표의 nice-number — 손 사다리(span>4→2)는 이 풀의
           스팬에서 눈금을 한 개("2%")까지 떨어뜨렸다(실측, critique 3차). */
        const rawStep = span / 4;
        const mag = 10 ** Math.floor(Math.log10(rawStep));
        const norm = rawStep / mag;
        const step = (norm >= 5 ? 5 : norm >= 2 ? 2 : 1) * mag;
        const i0 = Math.ceil(dom.min / step - 1e-9);
        const i1 = Math.floor(dom.max / step + 1e-9);
        for (let i = i0; i <= i1; i++) {
          const v = Math.round(i * step * 100) / 100;
          const pt = toScreen(projectFast(1, (v - dom.min) / span, 1, cy, sy, sp, cp), fit);
          const tick = bp ? `${v}bp` : `${v}%`;
          const tw = ctx.measureText(tick).width;
          if (overlapsPlaced(pt.x - 7 - tw, pt.x - 7, pt.y + 3)) continue;
          label(tick, pt.x - 7, pt.y + 3);
          claim(pt.x - 7 - tw, pt.x - 7, pt.y + 3);
        }
      }
      ctx.globalAlpha = 1;

      /* 기준금리 — 맨 앞 평면의 점선 하나, pane 과 같은 토큰. 평면도에서는
         높이가 화면에 없으므로 같이 걷는다. */
      if (
        pitchNow < 70 &&
        !bp &&
        policy?.latest != null &&
        policy.latest > dom.min &&
        policy.latest < dom.max
      ) {
        const y01 = (policy.latest - dom.min) / span;
        const a = toScreen(projectFast(0, y01, 1, cy, sy, sp, cp), fit);
        const b = toScreen(projectFast(1, y01, 1, cy, sy, sp, cp), fit);
        ctx.strokeStyle = colors.policy;
        ctx.globalAlpha = 0.6;
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.globalAlpha = 0.9;
        ctx.fillStyle = colors.policy;
        const right = a.x > b.x ? a : b;
        ctx.textAlign = 'left';
        /* 값은 표·리드아웃과 같은 포매터를 지난다 — toFixed 는 두 번째 정의다. */
        const policyText = `기준금리 ${fmtLevel(policy.latest, '%')}%`;
        const tw = ctx.measureText(policyText).width;
        const tx = Math.min(right.x + 6, width - tw - 4);
        let ty = clampY(right.y + 3);
        /* 떨굴 수 없는 라벨이라 겹치면 한 칸 비켜 선다. */
        if (overlapsPlaced(tx, tx + tw, ty)) ty = clampY(ty + 14);
        label(policyText, tx, ty);
        claim(tx, tx + tw, ty);
        ctx.globalAlpha = 1;
      }

      /* 평면도의 정량 키 — 금리 축과 기준금리선이 걷힌 뷰라(위 §참조) 램프가
         유일한 값 단서인데 범례가 없으면 색이 아무 말도 안 한다. 스톱은
         셰이더와 같은 토큰(--sr-s3d-lo/hi)의 문자열 그대로다.
         답값은 **실측 극값**(ext)이다 — 도메인 끝값은 6% 패딩이 섞인 합성수라
         시장에 찍힌 적 없는 수를 4자리로 주장하게 된다(실측 지적). 막대는
         전체 램프 중 [ext.min, ext.max] 구간만 보이도록 그라디언트를 막대
         밖으로 연장해 자른다 — 라벨의 수와 그 자리의 색이 정확히 일치한다. */
      if (pitchNow > 70) {
        const LG_W = 140;
        const LG_H = 10;
        const lx = 12;
        const ly = 10;
        const f0 = (ext.min - dom.min) / span;
        const f1 = (ext.max - dom.min) / span;
        const wFull = LG_W / Math.max(1e-6, f1 - f0);
        const gx0 = lx - f0 * wFull;
        const grad = ctx.createLinearGradient(gx0, 0, gx0 + wFull, 0);
        grad.addColorStop(0, colors.lo);
        grad.addColorStop(1, colors.hi);
        ctx.fillStyle = grad;
        ctx.fillRect(lx, ly, LG_W, LG_H);
        ctx.strokeStyle = colors.line;
        ctx.lineWidth = 1;
        ctx.strokeRect(lx + 0.5, ly + 0.5, LG_W - 1, LG_H - 1);
        ctx.fillStyle = colors.fg;
        ctx.globalAlpha = 0.85;
        ctx.font = `11px ${colors.font}`;
        /* 색 읽기의 정밀도 — 4자리는 램프의 해상도보다 정밀한 주장이다
           (critique 3차). %는 2자리, bp 는 1자리. round 는 toFixed 금지 가드
           때문이 아니라 표시 반올림이 이 둘로 충분해서다. */
        const sfx = bp ? 'bp' : '%';
        const fmtEnd = (v: number) =>
          bp ? `${Math.round(v * 10) / 10}${sfx}` : `${Math.round(v * 100) / 100}${sfx}`;
        ctx.textAlign = 'left';
        label(fmtEnd(ext.min), lx, ly + LG_H + 13);
        ctx.textAlign = 'right';
        label(fmtEnd(ext.max), lx + LG_W, ly + LG_H + 13);
        ctx.globalAlpha = 1;
      }
    }
  }, [ensureGeometry, width, height, policy?.latest]);

  /* 색은 이펙트에서 풀어 둔다 — 안 풀리면 여기서 던지고 ErrorBoundary 가 잡는다.
     테마 전환은 `scheme` 이 리렌더를 끌고 와 다시 푼다. */
  useEffect(() => {
    const canvas = overRef.current;
    if (!canvas) return;
    colorsRef.current = resolveColors(canvas);
    yawRef.current = yaw;
    pitchRef.current = pitch;
    zoomRef.current = zoom;
    selTenorIdxRef.current =
      selTenor && scene ? scene.pool.tenors.findIndex((x) => x.t === selTenor) : null;
    if (selTenorIdxRef.current === -1) selTenorIdxRef.current = null;
    draw();
  }, [draw, yaw, pitch, zoom, selTenor, ghostDate, scheme, hover, scene]);

  /* 풀을 바꿨는데 그 풀에 없는 테너가 남아 있으면 조용히 전체로. */
  useEffect(() => {
    if (selTenor && pool && !pool.tenors.some((x) => x.t === selTenor)) setSelTenor(null);
  }, [poolId, pool, selTenor]);

  /* GL 컨텍스트 유실 — 막고, 복원되면 다시 굽는다. */
  useEffect(() => {
    const canvas = glCanvasRef.current;
    if (!canvas) return;
    const onLost = (e: Event) => {
      e.preventDefault();
      glRef.current = null;
    };
    const onRestored = () => {
      glRef.current = null;
      geomKeyRef.current = '';
      draw();
    };
    canvas.addEventListener('webglcontextlost', onLost);
    canvas.addEventListener('webglcontextrestored', onRestored);
    return () => {
      canvas.removeEventListener('webglcontextlost', onLost);
      canvas.removeEventListener('webglcontextrestored', onRestored);
    };
  }, [draw]);

  /* ── 프리셋 전환은 미끄러진다 — 두 축을 같이 tween 한다. reduced-motion 이면
     즉시. ── */
  const tweenRef = useRef(0);
  /* 트윈이 끝나면 커서 밑을 다시 집는다 — 휠·드래그와 같은 이유(프리셋 전환
     후 리드아웃이 옛 자리에 표류, critique 4차 P3). repickHover 는 뒤에서
     정의되므로 ref 로 늦게 잇는다(둘 다 ref 만 읽는 순수 콜백이다). */
  const repickAfterTween = useRef<() => void>(() => {});
  const animateView = useCallback(
    (targetYaw: number, targetPitch: number) => {
      cancelAnimationFrame(tweenRef.current);
      const fromYaw = yawRef.current;
      const fromPitch = pitchRef.current;
      const fromZoom = zoomRef.current;
      if (
        (fromYaw === targetYaw && fromPitch === targetPitch && fromZoom === 1) ||
        window.matchMedia('(prefers-reduced-motion: reduce)').matches
      ) {
        yawRef.current = targetYaw;
        pitchRef.current = targetPitch;
        zoomRef.current = 1;
        setYaw(targetYaw);
        setPitch(targetPitch);
        setZoom(1);
        cancelAnimationFrame(rafRef.current);
        rafRef.current = requestAnimationFrame(() => {
          draw();
          repickAfterTween.current();
        });
        return;
      }
      const t0 = performance.now();
      const dur = 480;
      interactingRef.current = true;
      const step = (now: number) => {
        const u = Math.min(1, (now - t0) / dur);
        const e = u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
        yawRef.current = fromYaw + (targetYaw - fromYaw) * e;
        pitchRef.current = fromPitch + (targetPitch - fromPitch) * e;
        zoomRef.current = fromZoom + (1 - fromZoom) * e;
        if (u < 1) {
          draw();
          tweenRef.current = requestAnimationFrame(step);
        } else {
          interactingRef.current = false;
          draw();
          repickAfterTween.current();
          setYaw(targetYaw);
          setPitch(targetPitch);
          setZoom(1);
        }
      };
      tweenRef.current = requestAnimationFrame(step);
    },
    [draw],
  );
  useEffect(() => () => cancelAnimationFrame(tweenRef.current), []);

  /* ── 제스처 — 표준 3D 관례로 (2026-08-19 정비): 드래그 = 요+피치(orbit),
     **휠 = 확대/축소**. 첫 판의 "세로 드래그 = 줌 · Shift = 피치" 는 이 앱의
     미리보기 차트(휠 줌)와도, 3D 도구 일반과도 어긋났고, 피치가 수식어 뒤에
     숨어 발견되지 않았다. 휠은 네이티브 non-passive 로 단다 — React 의
     `onWheel` 은 passive 라 preventDefault 가 무력하다(PreviewPane 전례). ── */
  const dragState = useRef<{ x: number; y: number; moved: number } | null>(null);

  /* 화면 (px,py) → 읽기 [OWNER 2026-08-19 — "없는 금리를 지어내지 말고, 있는
     금리에서 특정 지점부터 특정 다른 지점까지는 **그 금리**를 보이게"].
     표면을 노드 기준의 **구역**으로 나눈다: 능선(날짜)은 최근접으로, 테너는
     그 능선 위에서 커서가 앉은 표본의 연수를 **중간점 경계**로 노드에 배정
     한다 — 5Y 와 10Y 사이라면 7.5Y 가 경계이고, 양쪽 구역은 각자 실측 5Y·10Y
     금리를 그대로 말한다. 보간값은 만들지 않는다: 커브 사이를 짚어도 나오는
     수는 언제나 pool.z 의 실측이다.
     2단계 재투영은 viewRef(draw 와 같은 산수)를 쓴다 — 따로 계산하면 그림과
     리드아웃이 어긋난다. 테너를 골라 둔 상태는 그 라인 위만 논다. */
  const pickAt = useCallback((px: number, py: number): Hover | null => {
    const sc = sceneRef.current;
    if (!sc) return null;
    const selT = selTenorIdxRef.current;
    const cand =
      selT == null ? nodesRef.current : nodesRef.current.filter((n) => n.tenor === selT);
    const pick = nearestNode(cand, px, py, Number.POSITIVE_INFINITY);
    if (!pick) return null;
    const base: Hover = { poolId: sc.poolId, ridge: pick.ridge, tenor: pick.tenor };
    const view = viewRef.current;
    if (selT != null || !view) return base;
    const { cy, sy, sp, cp, fit } = view;
    const { qs, ridges, years, dom, pool: p, toAxis } = sc;
    const row = ridges[pick.ridge];
    const span = dom.max - dom.min || 1;
    const z01 = ridges.length === 1 ? 1 : pick.ridge / (ridges.length - 1);
    let bestCol = -1;
    let bestD2 = Infinity;
    for (let c = 0; c < qs.length; c++) {
      const v = row[c];
      if (v == null) continue;
      const pt = toScreen(
        projectFast(toAxis(qs[c]), (v - dom.min) / span, z01, cy, sy, sp, cp),
        fit,
      );
      const d2 = (pt.x - px) ** 2 + (pt.y - py) ** 2;
      if (d2 < bestD2) {
        bestD2 = d2;
        bestCol = c;
      }
    }
    if (bestCol < 0) return base;
    /* 표본 → 중간점 경계 구역 — 거리는 **축 공간**이다: 등간격 축에서 시각적
       중간점이 곧 구역 경계가 된다. 그날 값이 없는 노드는 구역을 갖지 않는다
       — 없는 금리를 이웃 구역이 대신 말하지, 빈 칸이 말하지는 않는다. */
    const aCol = toAxis(qs[bestCol]);
    let zone = -1;
    let bestDy = Infinity;
    for (let t = 0; t < years.length; t++) {
      if (p.z[t][pick.ridge] == null) continue;
      const dy = Math.abs(toAxis(years[t]) - aCol);
      if (dy < bestDy) {
        bestDy = dy;
        zone = t;
      }
    }
    if (zone < 0) return base;
    return { poolId: sc.poolId, ridge: pick.ridge, tenor: zone };
  }, []);

  /* 제스처가 끝나면 커서 밑을 **다시 집는다** — 줌·드래그가 투영을 옮겼는데
     카드가 이전 노드를 계속 말하면, 멈춰 있는 커서 옆에서 다른 지역의 값이
     떠 있는 오독이 된다(실측). draw 가 노드를 재투영한 뒤에 불러야 한다. */
  const repickHover = useCallback(() => {
    const c = cursorRef.current;
    if (!c) return;
    const next = pickAt(c.x, c.y);
    setHover((cur) =>
      cur?.poolId === next?.poolId && cur?.ridge === next?.ridge && cur?.tenor === next?.tenor
        ? cur
        : next,
    );
  }, [pickAt]);
  repickAfterTween.current = repickHover;

  const onWheel = useCallback(
    (e: WheelEvent) => {
      e.preventDefault();
      zoomRef.current = Math.min(
        3,
        Math.max(0.5, zoomRef.current * Math.exp(-e.deltaY * 0.0012)),
      );
      setZoom(zoomRef.current);
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        draw();
        repickHover();
      });
    },
    [draw, repickHover],
  );
  useEffect(() => {
    const host = overRef.current;
    if (!host) return;
    host.addEventListener('wheel', onWheel, { passive: false });
    return () => host.removeEventListener('wheel', onWheel);
  }, [onWheel]);

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    dragState.current = { x: e.clientX, y: e.clientY, moved: 0 };
    interactingRef.current = true;
    setDragging(true);
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      /* 합성 이벤트 등 활성 포인터가 없는 경우 — 캡처는 편의일 뿐이다 */
    }
  };
  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = overRef.current;
    if (!canvas) return;
    if (dragState.current) {
      const d = dragState.current;
      const dx = e.clientX - d.x;
      const dy = e.clientY - d.y;
      d.x = e.clientX;
      d.y = e.clientY;
      d.moved += Math.abs(dx) + Math.abs(dy);
      yawRef.current = clampYaw(yawRef.current + dx * 0.35);
      pitchRef.current = clampPitch(pitchRef.current + dy * 0.3);
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(draw);
      return;
    }
    const r = canvas.getBoundingClientRect();
    const px = e.clientX - r.left;
    const py = e.clientY - r.top;
    /* 스냅은 **전 픽셀**, 읽기는 **구역**이다(pickAt — 2026-08-19). 노드
       사이를 짚으면 중간점 경계로 가까운 노드의 실측 금리가 나온다. */
    const next = pickAt(px, py);
    setHover((cur) =>
      cur?.poolId === next?.poolId && cur?.ridge === next?.ridge && cur?.tenor === next?.tenor
        ? cur
        : next,
    );
    /* 리드아웃 카드는 커서를 따른다 — 위치는 상태가 아니라 스타일이다(이동마다
       리렌더·재그리기를 끌고 오지 않도록). 카드가 아직 없으면(막 hover 가 선
       프레임) cursorRef 가 마운트 콜백에서 자리를 잡아 준다. */
    cursorRef.current = { x: px, y: py };
    const card = readoutRef.current;
    if (card) {
      card.style.left = `${Math.min(px + 16, width - 190)}px`;
      card.style.top = `${Math.min(py + 14, height - 130)}px`;
    }
  };
  /* 고스트 지정은 더블클릭 창(250ms)을 기다린다 — 안 그러면 각도 리셋
     더블클릭의 첫 클릭이 고스트를 조용히 바꾼다(실측 2026-08-19). */
  const ghostTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (ghostTimer.current) clearTimeout(ghostTimer.current);
    },
    [],
  );

  const endDrag = (e?: React.PointerEvent<HTMLCanvasElement>) => {
    if (!dragState.current) return;
    const wasClick = dragState.current.moved < 5;
    dragState.current = null;
    /* 안 끈 클릭 = 고스트 지정 [OWNER — "두 날짜 커브 비교"]: 짚어 선 능선의
       그날. 해제는 캡션 옆 고스트 칩이 진다 — hover 가 전 픽셀에 답하게 되면서
       "허공" 이라는 자리가 없어졌고, 보이지 않는 히트 판정에 설정/해제를
       겸직시키던 것이 첫 클릭 무반응 플레이크의 원인이었다. (금통위 핀 히트는
       핀과 함께 은퇴 [OWNER 2026-08-19].) */
    if (wasClick && e && overRef.current) {
      const hov = hoverRef.current;
      const next =
        hov && sceneRef.current && hov.poolId === sceneRef.current.poolId
          ? sceneRef.current.pool.dates[hov.ridge]
          : null;
      if (next) {
        if (ghostTimer.current) clearTimeout(ghostTimer.current);
        ghostTimer.current = setTimeout(() => setGhostDate(next), 250);
      }
    }
    /* 드래그 동안 hover 갱신이 쉬므로 커서의 마지막 자리를 여기서 받아 둔다 —
       repickHover 가 이 자리로 다시 집는다. */
    if (e && overRef.current) {
      const r = overRef.current.getBoundingClientRect();
      cursorRef.current = { x: e.clientX - r.left, y: e.clientY - r.top };
    }
    interactingRef.current = false;
    setDragging(false);
    setYaw(yawRef.current);
    setPitch(pitchRef.current);
    setZoom(zoomRef.current);
    /* 값이 안 변한 클릭이면 setState 가 리렌더를 안 끌고 온다 — 노드 재투영을
       위해 한 번 더, 그리고 새 투영으로 커서 밑을 다시 집는다. */
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      draw();
      repickHover();
    });
  };

  /* ── 키보드 = 마우스 (미리보기 pane 의 규칙 그대로) — 포인터 없이도 모든
     값을 읽는다 (2026-08-19 정비). 화살표가 hover 를 옮기고 리드아웃·단면이
     그대로 따라온다: 두 번째 읽기 경로를 만들지 않는다. ← → = 날짜(Shift =
     영업월), PgUp/PgDn = 약 1년, Home/End = 처음/오늘, ↑ ↓ = 테너, Enter =
     짚은 날을 고스트로. */
  const onKeyDown = (e: React.KeyboardEvent<HTMLCanvasElement>) => {
    const sc = sceneRef.current;
    if (!sc) return;
    const R = sc.pool.dates.length;
    const T = sc.pool.tenors.length;
    const selT = selTenorIdxRef.current;
    const cur =
      hoverRef.current && hoverRef.current.poolId === sc.poolId ? hoverRef.current : null;
    let ridge = cur?.ridge ?? R - 1;
    let tenor = selT ?? cur?.tenor ?? Math.max(0, T - 1);
    const dayStep = e.shiftKey ? 21 : 1;
    switch (e.key) {
      case 'ArrowLeft':
        ridge = Math.max(0, ridge - dayStep);
        break;
      case 'ArrowRight':
        ridge = Math.min(R - 1, ridge + dayStep);
        break;
      case 'PageUp':
        ridge = Math.max(0, ridge - 252);
        break;
      case 'PageDown':
        ridge = Math.min(R - 1, ridge + 252);
        break;
      case 'Home':
        ridge = 0;
        break;
      case 'End':
        ridge = R - 1;
        break;
      case 'ArrowUp':
        /* 테너를 골라 뒀으면 그 라인에 잠긴다 — 포인터의 규칙과 같다. */
        if (selT == null) tenor = Math.min(T - 1, tenor + 1);
        break;
      case 'ArrowDown':
        if (selT == null) tenor = Math.max(0, tenor - 1);
        break;
      case 'Enter':
        if (cur) setGhostDate(sc.pool.dates[cur.ridge]);
        e.preventDefault();
        return;
      default:
        return;
    }
    e.preventDefault();
    const next: Hover = { poolId: sc.poolId, ridge, tenor };
    setHover((c) =>
      c?.poolId === next.poolId && c?.ridge === next.ridge && c?.tenor === next.tenor
        ? c
        : next,
    );
    /* 리드아웃 카드는 짚은 노드 곁에 선다 — 포인터가 하던 자리 잡기와 같은 길. */
    const n = nodesRef.current.find((q) => q.ridge === ridge && q.tenor === tenor);
    if (n) {
      cursorRef.current = { x: n.x, y: n.y };
      const card = readoutRef.current;
      if (card) {
        card.style.left = `${Math.min(n.x + 16, width - 190)}px`;
        card.style.top = `${Math.min(n.y + 14, height - 130)}px`;
      }
    }
  };

  const activePreset = PRESETS.find((pr) => pr.yaw === yaw && pr.pitch === pitch) ?? null;

  /* PeriodSelector 는 주면 주는 대로 폭을 다 먹는다 — 상자로 조인다.
     그룹마다 이름이 선다 (2026-08-19 정비): 같은 알약 네 무리가 네 가지
     의미(데이터 풀·발행체·테너 필터·**카메라**)를 지는데 간격만으로는
     카메라가 데이터 필터로 위장한다 — 실측 지적. 라벨은 TextLegal(문장
     레지스터), 보조기술에는 role="group" + aria-label 로 같은 이름.
     빈 풀에서도 이 줄이 서야 한다 — 컨트롤 없는 빈 상태는 다른 풀로
     돌아갈 길이 없는 함정이었다(세션 기억이 빈 풀을 복원하면 갇힌다). */
  const controlsRow = (
    <HStack gap={2} alignItems="center" flexWrap="wrap">
        <HStack gap={1} alignItems="center" role="group" aria-label="풀">
          <TextCaption as="span" color="fgMuted">
            풀
          </TextCaption>
          {/* sr-tabs-neutral: 이 네 무리는 데이터 부호가 없는 필터·카메라라
              활성은 앱 공통의 중립 잉크 문법을 입는다(type.css 참조). CDS 의
              primary wash 파랑은 이 제품에선 하락 방향의 낱말이다. */}
          <Box width={330} className="sr-tabs-neutral">
            <PeriodSelector
              tabs={POOL_TABS.map((t) => a11yTab(t.id, t.label))}
              activeTab={POOL_TABS.find((t) => t.id === tab) ?? null}
              onChange={(t) => t && setTab(t.id as PoolTab)}
            />
          </Box>
        </HStack>
        {tab === 'credit' || tab === 'crdsp' ? (
          <HStack gap={1} alignItems="center" role="group" aria-label="발행체">
            <TextCaption as="span" color="fgMuted">
              발행체
            </TextCaption>
            <Box width={400} className="sr-tabs-neutral">
              <PeriodSelector
                tabs={payload.creditTypes.map((t) => a11yTab(t.id, t.label))}
                activeTab={payload.creditTypes.find((t) => t.id === creditType) ?? null}
                onChange={(t) => t && setCreditType(t.id)}
              />
            </Box>
          </HStack>
        ) : null}
        {scene ? (
          <HStack gap={1} alignItems="center" role="group" aria-label="테너">
            <TextCaption as="span" color="fgMuted">
              테너
            </TextCaption>
            {/* 탭 수 = 테너 + '전체' 1. 탭당 56px — 12노드(3M~30Y)에서 50px
                셈은 '전체'를 두 줄로 접었다(실측 2026-08-19). */}
            <Box width={24 + (scene.pool.tenors.length + 1) * 56} className="sr-tabs-neutral">
              <PeriodSelector
                tabs={[a11yTab('all', '전체'), ...scene.pool.tenors.map((x) => a11yTab(x.t, x.t))]}
                activeTab={
                  selTenor
                    ? { id: selTenor, label: selTenor }
                    : { id: 'all', label: '전체' }
                }
                onChange={(x) => setSelTenor(x && x.id !== 'all' ? x.id : null)}
              />
            </Box>
          </HStack>
        ) : null}
        <HStack gap={1} alignItems="center" role="group" aria-label="구도">
          <TextCaption as="span" color="fgMuted">
            구도
          </TextCaption>
          <Box width={230} className="sr-tabs-neutral">
            <PeriodSelector
              tabs={PRESETS.map((pr) => a11yTab(pr.id, pr.label))}
              activeTab={activePreset}
              onChange={(t) => {
                const pr = PRESETS.find((x) => x.id === t?.id);
                if (pr) animateView(pr.yaw, pr.pitch);
              }}
            />
          </Box>
        </HStack>
    </HStack>
  );

  /* ── 카드 위에 산다 [OWNER 2026-08-19 — "디자인 컨셉을 메인·백테스트에
     맞춰서"]. 다른 화면의 문법 그대로: 페이지 바탕(--sr-page) 위에 카드
     (색조+라운드+헤어라인, §3.4) 하나, 컨트롤·캡션은 카드 머리(paddingX 2 —
     미리보기 카드의 헤더와 같은 인셋), 그림은 풀블리드. 페이지에 맨살로
     서 있던 전 판은 이 제품에서 Lab 만 와이어프레임으로 읽히게 했다. */
  if (!scene) {
    return (
      <VStack className="sr-card" width="100%" minHeight={0}>
        <VStack gap={1} paddingX={2} paddingTop={2} paddingBottom={1.5}>
          <TextLabel1 as="h2">커브 표면</TextLabel1>
          {controlsRow}
        </VStack>
        <VStack gap={0.5} paddingX={2} paddingY={2} className="sr-surface-host">
          <TextBody as="p" color="fgMuted">
            이 풀의 데이터가 없어요 — 다른 풀을 골라 보세요.
          </TextBody>
        </VStack>
      </VStack>
    );
  }

  const hoveredHere = hover && hover.poolId === scene.poolId ? hover : null;
  const hovDate = hoveredHere ? scene.pool.dates[hoveredHere.ridge] : null;
  /* 값은 언제나 실측(pool.z)이다 — 구역을 짚어도 그 구역 노드의 금리다. */
  const hovValue = hoveredHere ? scene.pool.z[hoveredHere.tenor][hoveredHere.ridge] : null;
  const hovTenorText = hoveredHere ? scene.pool.tenors[hoveredHere.tenor].t : null;
  const hovUnitSfx = scene.pool.unit === 'bp' ? 'bp' : '%';
  const hovInversion = hoveredHere ? scene.pool.inversionBp[hoveredHere.ridge] : null;
  /* 기준금리·CD 는 % 를 접미한다 — bp 풀에서 무단위 "3.5000" 이 무슨 수인지
     기억에 맡기고 있었다(critique 3차). 값이 없으면(—) 단위도 안 붙는다. */
  const hovPolicy = hovDate ? policyAt(policy, hovDate) : null;
  const hovCd = hovDate ? lastOnOrBefore(payload.cd, hovDate) : null;

  return (
    <VStack className="sr-card" width="100%" flexGrow={1} minHeight={0} minWidth={0}>
      {/* 카드 머리의 사다리 = 메인 카드 실측 그대로 (2026-08-19 [OWNER — "메인
          보고 와서, 폰트 위계 안 맞음"]): 머리 라벨 14/600 잉크("주요 아웃라이트"
          의 단, TextLabel1) → 캡션 13/500 muted(TextLegal) → 구조 라벨(풀·테너·
          구도)은 13/600 muted TextCaption(표 헤더·범례의 단). 전부 13/500 muted
          로 눌려 정점이 없던 판의 수리. 캡션 문장은 토스체 — 짧게, 쉬운 말로
          [OWNER — "토스 스타일의 쉬운 문장으로 간결하게"]. */}
      <VStack gap={1} paddingX={2} paddingTop={2} paddingBottom={1.5}>
        <VStack gap={0}>
          <TextLabel1 as="h2">{scene.pool.label} 커브 표면</TextLabel1>
          {/* minHeight 33 = 칩(xs) **실측** 높이 예약 — 고스트를 켜고 끄는
              순간, 두 커브를 비교하는 바로 그 순간에 캔버스가 밀리면 안 된다
              (실측: 예약 전 ~30px → 24 예약 시 9px → 33 예약 시 0). 칩 안은
              nowrap — ×가 둘째 줄로 접히던 자리. */}
          <HStack gap={1} alignItems="center" flexWrap="wrap" minHeight={33}>
            <TextLegal as="span" color="fgMuted">
              {scene.pool.dates[0].slice(0, 7)} ~ {scene.pool.asof}
              {scene.pool.missingNodes.length > 0
                ? ` · 빠진 값: ${scene.pool.missingNodes.join(', ')}`
                : ''}
              {' · 누르면 그날 커브를 겹치고, 두 번 누르면 처음 각도로 돌아가요'}
            </TextLegal>
          {/* 고스트는 보이는 상태다 — 점선이 시계열 뷰에서 모서리로 누우면
              화면 어디에도 "겹쳐 놓았다" 는 사실이 없었다. 해제도 이 칩이 진다.
              풀 라벨은 **지금 그려진 점선이 누구의 커브인지**를 말한다 — 고스트
              (날짜)는 풀 전환을 살아남는데, 칩이 날짜만 말하면 전환 후의 점선을
              이전 풀의 커브로 오독한다(실측 지적, 2026-08-19). */}
            {ghostDate ? (
              <Chip
                size="xs"
                accessibilityLabel={`고스트 ${ghostDate} (${scene.pool.label} 커브) 해제`}
                onClick={() => setGhostDate(null)}
              >
                <span style={{ whiteSpace: 'nowrap' }}>
                  고스트 {ghostDate} · {scene.pool.label} ×
                </span>
              </Chip>
            ) : null}
          </HStack>
        </VStack>
        {controlsRow}
      </VStack>
      <div className="sr-surface-host" ref={ref}>
        {w > 0 ? (
          <div className="sr-surface sr-s3d-stack" style={{ width, height }}>
            <canvas ref={underRef} className="sr-s3d-layer" style={{ width, height }} />
            <canvas ref={glCanvasRef} className="sr-s3d-layer" style={{ width, height }} />
            <canvas
              ref={overRef}
              className="sr-s3d-layer sr-s3d-canvas"
              style={{ width, height, cursor: dragging ? 'grabbing' : 'grab' }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={endDrag}
              onPointerCancel={() => endDrag()}
              onPointerLeave={() => {
                endDrag();
                setHover(null);
              }}
              onDoubleClick={() => {
                /* 리셋 더블클릭의 첫 클릭이 예약해 둔 고스트 지정을 버린다 —
                   각도만 되돌리고 비교 상태는 건드리지 않는다. */
                if (ghostTimer.current) clearTimeout(ghostTimer.current);
                animateView(YAW_DEFAULT, PITCH_DEG);
              }}
              onKeyDown={onKeyDown}
              tabIndex={0}
              role="application"
              aria-label={`커브 표면 — ${scene.pool.label}, ${scene.pool.dates[0]}부터 ${scene.pool.asof}까지. 드래그로 회전, 휠로 확대, 화살표로 날짜·테너 이동, Enter 로 고스트 지정`}
            />
            {/* 리드아웃의 텍스트 판 — 스크린리더가 캔버스 안을 못 보므로 같은
                사실을 **전부** 여기서 말한다(시각 카드보다 빈약하면 두 번째
                채널이 아니라 열화 채널이다 — 실측 지적으로 기준금리·CD·역전
                합류, 2026-08-19). 값의 출처는 리드아웃과 동일하다. */}
            <div className="sr-a11y-live" aria-live="polite">
              {hoveredHere && hovDate
                ? `${hovDate} ${hovTenorText} ${fmtLevel(hovValue, scene.pool.unit)}${hovUnitSfx} · 기준금리 ${fmtLevel(hovPolicy, '%')}${hovPolicy != null ? '%' : ''} · CD ${fmtLevel(hovCd, '%')}${hovCd != null ? '%' : ''}${hovInversion != null && hovInversion < 0 ? ` · 역전 ${scene.pool.inversionPair} ${fmtLevel(hovInversion, 'bp')}bp` : ''}`
                : ''}
            </div>
            {/* 커서 리드아웃 [OWNER — "커서 올리면 몇년몇월몇일, 금리 몇, 기준금리
                얼마, CD 얼마"]. 위치는 onPointerMove 가 스타일로 직접 민다. */}
            {hoveredHere && hovDate ? (
              <div
                ref={(el) => {
                  readoutRef.current = el;
                  const c = cursorRef.current;
                  if (el && c) {
                    el.style.left = `${Math.min(c.x + 16, width - 190)}px`;
                    el.style.top = `${Math.min(c.y + 14, height - 130)}px`;
                  }
                }}
                className="sr-readout sr-s3d-readout"
              >
                <span className="sr-surface-cut-date">{hovDate}</span>
                {/* 단위가 섞인 문장 줄 = TextLegal (TextCaption 은 "bp" 를
                    "BP" 로 세운다) · 값은 전부 fmtLevel — ReadoutCard 와 같은
                    규칙("이 파일에 toFixed 는 없다")이다. */}
                <div className="sr-readout-rows">
                  <TextLegal as="span">
                    {hovTenorText} {fmtLevel(hovValue, scene.pool.unit)}
                    {hovUnitSfx}
                  </TextLegal>
                  <TextLegal as="span" color="fgMuted">
                    기준금리 {fmtLevel(hovPolicy, '%')}
                    {hovPolicy != null ? '%' : ''}
                  </TextLegal>
                  <TextLegal as="span" color="fgMuted">
                    CD {fmtLevel(hovCd, '%')}
                    {hovCd != null ? '%' : ''}
                  </TextLegal>
                  {(() => {
                    const iv = scene.pool.inversionBp[hoveredHere.ridge];
                    return iv != null && iv < 0 ? (
                      <TextLegal as="span" color="fgMuted">
                        역전 {scene.pool.inversionPair} {fmtLevel(iv, 'bp')}bp
                      </TextLegal>
                    ) : null;
                  })()}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </VStack>
  );
}
/* 단면 패널(우측 상단 흰 카드)은 여기 살았다가 [OWNER 2026-08-18 — "보여줄
 * 필요는 없음"]으로 내렸다. 역전 bp 는 hover 리드아웃 캡션이 이어받았다. */
