/* Where the data lives — the frontend half of the id→path rule.
 *
 * Static conversion, Pass C. `backend/app/static_paths.py` is the other half
 * and the two MUST agree.
 *
 * (v1 의 문장은 `guards/static-paths.test.ts` 가 그 일치를 고정한다고 적어
 *  두었는데, **이 리포에는 그 파일이 없다** — 2026-08-20 확인. v2 는 트리를
 *  구운 적이 없어 검사할 대상 자체가 없다. 굽기를 되살리는 날 함께 옮겨 올
 *  것이고, 그때까지 이 두 파일의 일치는 사람이 지킨다.)
 *
 * Two shapes, because a static host cannot select a file by query string:
 *
 *   static (default)  /api/series/10Y.full.json
 *   live backend      https://<funnel-host>/api/series/10Y?res=full
 *
 * The live shape is what the deployment uses: Vercel serves this frontend and
 * `NEXT_PUBLIC_API_BASE` points at the Funnel-exposed FastAPI app
 * [OWNER, 2026-08-20]. `lib/apiBase.ts` owns that value.
 */

/** 백엔드 출처. 정해지는 곳은 `lib/apiBase.ts` **하나**이고 여기서는 다시
 * 내보내기만 한다 — 화면 코드가 `process.env` 를 직접 읽으면 규칙이 두 벌이
 * 되고, 그중 하나만 고쳐지는 날이 온다. */
import { API_BASE } from "./apiBase";

export { API_BASE };

/** True when no live backend is configured, i.e. the deployed case. */
export const IS_STATIC = API_BASE === "";

export type Resolution = "full" | "preview" | "w" | "m";

/** Id → path stem. The colon in `vol:1Y` is already a namespace separator, so
 * a directory is what it always meant: `vol/1Y`. It also has to go: on NTFS a
 * colon redirects the write into an alternate data stream (silently), and
 * `encodeURIComponent` turns it into `%3A`, so a literally-named file and the
 * request path would disagree even on Linux. Mirrors `static_paths.py::slug`. */
export function slug(seriesId: string): string {
  return seriesId.replace(/:/g, "/");
}

/** Path segments are already safe by construction (see slug + the backend's
 * refusal to emit anything else), so they are encoded per-segment — a whole-id
 * `encodeURIComponent` would escape the separators we just created. */
function encodePath(stem: string): string {
  return stem.split("/").map(encodeURIComponent).join("/");
}

export function seriesUrl(seriesId: string, res: Resolution): string {
  if (IS_STATIC) return `/api/series/${encodePath(slug(seriesId))}.${res}.json`;
  const id = encodeURIComponent(seriesId);
  return res === "w" || res === "m"
    ? `${API_BASE}/api/series/${id}?res=full&interval=${res}`
    : `${API_BASE}/api/series/${id}?res=${res}`;
}

export function dv01Url(seriesId: string): string {
  return IS_STATIC
    ? `/api/dv01/${encodePath(slug(seriesId))}.json`
    : `${API_BASE}/api/dv01/${encodeURIComponent(seriesId)}`;
}

export const summaryUrl = () =>
  IS_STATIC ? "/api/wall/summary.json" : `${API_BASE}/api/wall/summary`;
export const forwardsUrl = () =>
  IS_STATIC ? "/api/forwards.json" : `${API_BASE}/api/forwards`;
export const volatilityUrl = () =>
  IS_STATIC ? "/api/volatility.json" : `${API_BASE}/api/volatility`;
/** 3D 커브 표면(Lab, 3풀). universe 처럼 **라이브 전용**이다 — v2 는 배포가
 * 없는 스파이크고, 크레딧 절반이 SQL 라이브 테이블이라 굽기 짝을 만들 때
 * universe 와 같이 만든다. 정적 모드 경로는 그날을 위해 모양만 잡아 둔다. */
export const surfaceUrl = () =>
  IS_STATIC ? "/api/surface3d.json" : `${API_BASE}/api/surface3d`;

/** The manifest replaces `/api/health` when static: freshness is a "now"
 * question and the client owns the clock (§21). Against a live backend the
 * server still answers it, so the caller branches on IS_STATIC. */
/** The backtest is LIVE-ONLY. Every other endpoint has a static twin the
 * deployed site serves, but this answer depends on inputs the reader chooses,
 * so it cannot be baked. Vercel runs the frontend and a backend runs behind it
 * [OWNER, 2026-07-31]; with no `NEXT_PUBLIC_API_BASE` set there is nothing to
 * ask, and callers must say so rather than fetch a file that will never exist.
 * Returns null in that case — a URL here would 404 as HTML and surface as a
 * JSON parse error, which tells the reader nothing. */
export function backtestUrl(
  spec: string,
  funding?: { basis: string; spreadBp: number },
): string | null {
  /* 조달은 **채권 줄이 있을 때만** 서버가 읽는다 [2026-08-21]. 그래도 늘 실어
   * 보내는 이유: 북에 채권이 섞였는지는 문자열을 파싱해야 알고, 그 판정을 두
   * 군데(여기와 서버)에 두면 갈릴 수 있다. 스왑만 있는 북에서는 서버가 이 값을
   * 쓰지 않으므로 답이 달라지지 않는다. */
  const f = funding
    ? `&basis=${encodeURIComponent(funding.basis)}&spreadBp=${funding.spreadBp}`
    : "";
  const q = `positions=${encodeURIComponent(spec)}${f}`;
  // Development against a live backend: the explicit origin.
  if (!IS_STATIC) return `${API_BASE}/api/backtest?${q}`;
  /* 정적 모드(= `NEXT_PUBLIC_API_BASE` 를 빈 문자열로 명시): 같은 출처 경로.
   *
   * v1 의 문장은 next.config.ts 의 rewrite 가 이걸 백엔드로 넘긴다고 적어
   * 두었는데, **이 리포에는 rewrite 가 없다** — 2026-08-20 확인. 그래서 이
   * 경로는 404 가 되고, `fetchBacktest` 가 그것을 "백엔드가 필요한 화면이에요"
   * 패널로 바꾼다. 그게 정직한 답이다: 그 라우트는 정말 없다.
   *
   * 이 리포의 배포는 rewrite 가 아니라 **다른 출처**로 간다(Vercel 프런트 +
   * Funnel 백엔드). 그 길에서는 `IS_STATIC` 이 거짓이라 위쪽 가지를 탄다. */
  return `/api/backtest?${q}`;
}

/* ── Cash Bond [OWNER, 2026-08-14] — 전부 라이브 ─────────────────────────────
 * 민평이 SQL 에만 있어 정적 쌍둥이를 구울 수 없다(backtest 와 같은 성질).
 * 정적 모드에서는 same-origin 경로가 되고, 프록시가 없으면 404 → liveJson 이
 * "백엔드가 필요한 화면이에요" 로 바꾼다. */
function liveUrl(path: string, query?: string): string {
  const q = query ? `?${query}` : "";
  return IS_STATIC ? `${path}${q}` : `${API_BASE}${path}${q}`;
}

/* ── Lab 시나리오 [2026-08-20] ────────────────────────────────────────────────
 * 앵커(오늘의 스팟 호가 + 12개월 시장 캐리)뿐이다. 손잡이는 프런트가 돌리므로
 * 이 요청은 화면당 **한 번**이고, 서버가 없으면 화면이 그 사실을 말한다. */
export const scenarioAnchorsUrl = () => liveUrl("/api/scenario/anchors");
export const scenarioMacroUrl = () => liveUrl("/api/scenario/macro");

/* ── Lab 발행 캘린더 [2026-08-20] ─────────────────────────────────────────────
 * CSV 를 읽는 화면이라 정적 쌍둥이를 구울 수 없다 — 수집기가 5분마다 새로 쓰는
 * 파일이 원천이고, 구운 판은 그 순간 낡는다. */
export const issuanceCalendarUrl = (ym: string, months: number) =>
  liveUrl("/api/issuance/calendar", `ym=${encodeURIComponent(ym)}&months=${months}`);

export const issuanceDayUrl = (iso: string) =>
  liveUrl(`/api/issuance/day/${encodeURIComponent(iso)}`);

export const cashbondInstrumentsUrl = () => liveUrl("/api/cashbond/instruments");

export const cashbondSeriesUrl = (id: string) =>
  liveUrl(`/api/cashbond/series/${encodeURIComponent(id)}`);

export const fundingSettingsUrl = (basis: string, spreadBp: number) =>
  liveUrl("/api/settings/funding", `basis=${encodeURIComponent(basis)}&spreadBp=${spreadBp}`);

export const manifestUrl = () => "/api/manifest.json";
export const healthUrl = () => `${API_BASE}/api/health`;

/* ── 나머지 라이브 라우트 [2026-08-20, 배포 준비] ─────────────────────────────
 * 이 아래 넷은 원래 화면 코드가 `${API_BASE}/api/...` 로 **직접 조립**하던
 * 것이다. v1 에서 같은 모양이 정적 호스팅의 404 로 나타났고, 손으로 적은
 * 목록은 `lib/` 밖을 안 봤기 때문에 그걸 놓쳤다. 조립이 한 파일 안에만 있으면
 * 다음번 배포 형태 변경은 이 파일 하나를 고치는 일이 된다.
 * `guards/api-base.test.ts` 가 `lib/` 밖의 재조립을 실패시킨다. */

/** 유니버스 카탈로그(민평 종목 목록). 라이브 전용이다. */
export const universeUrl = () => liveUrl("/api/universe");

/** 유니버스 한 종목의 히스토리. `/api/series` 와 달리 정적 쌍둥이가 없다. */
export const universeSeriesUrl = (id: string) =>
  liveUrl(`/api/universe/series/${encodeURIComponent(id)}`);

/** 국채선물·퓨처스왑 한 계열의 히스토리 [2026-08-25]. `/api/series` 와 달리
 * 정적 쌍둥이가 없다(선물 종가가 SQL 에만 있다 — 현금채권과 같은 사정). */
export const futuresSeriesUrl = (id: string) =>
  liveUrl(`/api/futures/series/${encodeURIComponent(id)}`);

export const rvAnalysisUrl = (query: string) => liveUrl("/api/rv/analysis", query);
export const rvHistoryUrl = (query: string) => liveUrl("/api/rv/history", query);

/** Mean Reversion 측정면(Strategy 둘째 세입자) — 라이브 전용(BSS 가 SQL 에만).
 * query = `window=..&k=..`(rv 페처들과 같은 문법). */
export const mrBoardUrl = (query: string) => liveUrl("/api/mr/board", query);
export const mrHistoryUrl = (id: string, query: string) =>
  liveUrl(`/api/mr/history/${encodeURIComponent(id)}`, query);
/** 전략 실험 창 — 첫 PMS entry-signals 의 z-스코어 백테스트 재현. */
export const mrStrategyUrl = (query: string) => liveUrl("/api/mr/strategy", query);
/** BSS 테너 통합 장부 — 같은 규칙을 아홉 만기에 동시에 건 한 장부.
 * query 는 `/api/mr/strategy` 와 같고 `id` 만 없다. */
export const mrBookUrl = (query: string) => liveUrl("/api/mr/book", query);
/** Momentum 측정면(Strategy 셋째 세입자) — 라이브 전용(선물 종가가 SQL 에만).
 * 손잡이가 없어 query 도 없다: 룩백은 고르는 것이 아니라 축이고 신호는 등록된
 * 북 그대로 `macross` 하나다(`backend/app/momentum.py` 머리). */
export const momentumBoardUrl = () => liveUrl("/api/momentum/board");
export const momentumHistoryUrl = (key: string) =>
  liveUrl(`/api/momentum/history/${encodeURIComponent(key)}`);
/** **표본내** 장부 — 동결일 이후는 서버가 잘라서 낸다(채점 잠금). */
export const momentumBookUrl = () => liveUrl("/api/momentum/book");

/** 거래 하나의 실가격 일별 대사 — 자산스왑으로 세워 민평 노드를 범프한
 * 테너별 KRD. **거래를 누를 때만** 도는 별도 패스라 라우트도 따로다
 * (KRD 범프가 본체보다 비싸다 — `cashbond` 의 그 근거). */
export const mrReconUrl = (query: string) => liveUrl("/api/mr/recon", query);
/** 근사 최적화 격자 — 다섯 노브(룩백·진입·청산·손절·진입 규칙)의 프리셋을
 * 전부 돌린 표 [OWNER 2026-09-04]. **누를 때만** 도는 별도 패스라 라우트도
 * 따로다(162칸이 본체보다 비싸다 — `/api/mr/recon` 과 같은 근거).
 * query 는 `/api/mr/strategy` 와 같고 `span` 이 하나 더 있다. */
export const mrOptimizeUrl = (query: string) => liveUrl("/api/mr/optimize", query);
/** 통합 장부의 근사 최적화 격자 [OWNER 2026-09-07]. 같은 격자를 아홉 만기에
 * 걸어 칸마다 더한다 — **아홉 배 비싸서**(실측 4.4초 대 0.68초) 낱개와도 라우트를
 * 가른다. query 는 `/api/mr/book` 과 같고 `span` 이 하나 더 있다. */
export const mrBookOptimizeUrl = (query: string) =>
  liveUrl("/api/mr/book/optimize", query);

export const simInstrumentsUrl = () => liveUrl("/api/instruments");
export const simExpandUrl = () => liveUrl("/api/instruments/expand");
export const simulateUrl = () => liveUrl("/api/simulate");
