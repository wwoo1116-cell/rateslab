'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import { Text } from '@coinbase/cds-web/typography';

import { ErrorState, LoadingState } from '@/ui/DataState';
import { useUrlState } from '@/ui/useUrlState';

import { CommandPalette } from './CommandPalette';
import { Dossier } from './Dossier';
import { ObjectExplorer } from './ObjectExplorer';
import { PanelHead } from './PanelHead';
import { ShortcutHelp } from './ShortcutHelp';
import { CHART_SPANS, ChartApp, type SpanKey } from './apps/ChartApp';
import { GraphApp } from './apps/GraphApp';
import { TABLE_SORT_KEYS, TableApp, type TableSortKey } from './apps/TableApp';
import { TimelineApp } from './apps/TimelineApp';
import { applyFacets, type FacetKey, type Ontology, type Selection } from './ontology';
import {
  decodeFacets,
  decodeRange,
  decodeSort,
  encodeFacets,
  encodeRange,
  encodeSort,
} from './urlState';
import { useExploration } from './useExploration';
import { useTermData } from './useTermData';
import { ROUTE_MISSING_DETAIL } from '@/lib/apiBase';

/**
 * 목업의 껍데기 — **한 프레임, 네 개의 축**.
 *
 * ── 왜 이 구조인가 [Gotham] ────────────────────────────────────────────────
 * Gotham 은 화면을 기능별로 쪼개서 각자 자기 데이터를 들게 하지 않는다. 프레임이
 * 하나 있고, 그 안에서 **같은 객체 집합**을 여러 축으로 본다: 관계(그래프),
 * 시간(타임라인), 표, 값(차트). 그래서 왼쪽에서 필터를 하나 걸면 네 화면이
 * 동시에 좁아지고, 어느 화면에서 객체를 고르든 오른쪽 도시에가 같은 것을 연다.
 *
 * 그 «동시에» 가 이 구조의 전부다. 화면마다 자기 상태를 들면 왼쪽에서 거른 것이
 * 가운데에 그대로 남아 두 패널이 서로를 부정하고, 그 순간 분석 도구가 아니라
 * 위젯 모음이 된다. 그래서 상태는 **여기 한 곳**에만 산다.
 *
 * ── 그 «한 곳» 이 이제 **주소**다 [2026-08-27] ─────────────────────────────
 * 필터·구간·축·정렬은 `useState` 가 아니라 URL 쿼리에서 **유도한다**
 * (`urlState.ts` 가 부호화를 진다). 상태를 두 벌로 두고 한쪽을 다른 쪽에 비추면
 * 마운트 한 프레임 동안 서로를 되받아 쓴다 — 첫 판이 실제로 그렇게 들어온 주소를
 * 덮어썼다. 유도값에는 그 사고가 없다: 쓰는 곳이 하나뿐이라 되받을 것이 없다.
 *
 * 초점만 예외다. 초점에는 **이력**이 딸려 있어서(뒤로/앞으로) 훅이 상태를 져야
 * 하고, 주소는 그 결과를 비춘다. 그래서 이동은 전부 `goTo`·`goBack`·`goForward`
 * 셋을 지나간다 — 두 곳에 쓰는 자리를 한 군데로 모아 둔다.
 *
 * ── 데이터는 전부 실제다 [OWNER 2026-08-26] ────────────────────────────────
 * `useTermData` 가 이 앱의 백엔드에서 읽어 온다(`/api/universe`, `/api/mr/board`,
 * `/api/rv/analysis`, `/api/issuance/calendar`, `/api/issuance/day/{iso}`). 지어낸
 * 값은 한 줄도 없고, 없는 것은 화면에도 없다 — 체결 로그와 거래상대가 앞선 판에서
 * 사라진 이유다.
 */

type AppId = 'graph' | 'timeline' | 'table' | 'chart';

const APPS: { id: AppId; label: string; hint: string }[] = [
  { id: 'graph', label: 'Graph', hint: '관계 — 이것과 닿아 있는 것' },
  { id: 'timeline', label: 'Timeline', hint: '시간 — 언제 일어났나' },
  { id: 'table', label: 'Table', hint: '표 — 지금 결과를 줄로' },
  { id: 'chart', label: 'Chart', hint: '값 — 그 계열의 실제 시계열' },
];

/** 한 글자 단축키를 쓸지. **저장한다** — 끄는 사람은 매번 끄고 싶은 게 아니라
 *  안 듣게 하고 싶은 것이다. 저장 매체는 `state/funding.ts` 와 같은 이유로
 *  localStorage 다(좌표가 아니라 취향이고, 어느 창에서도 같은 뜻이다). */
const SINGLE_KEY_STORE = 'sr-term-singlekey';

function loadSingleKeys(): boolean {
  try {
    return localStorage.getItem(SINGLE_KEY_STORE) !== 'off';
  } catch {
    /* 저장소가 막힌 브라우저 — 기본값(켬)이 안전하다. 지금까지 쓰던 그대로다. */
    return true;
  }
}

export function TerminalShell() {
  const data = useTermData();

  if (data.state === 'loading') {
    return (
      <div className="sr-term sr-term-boot" data-sr-scheme="dark">
        <LoadingState what="온톨로지" />
      </div>
    );
  }
  if (data.state === 'error') {
    return (
      <div className="sr-term sr-term-boot" data-sr-scheme="dark">
        {/* 재시도는 **페이지를 다시 여는 것**이다. `useTermData` 는 마운트에 한 번
            읽는 훅이라, 그 안에 재시도 손잡이를 만들면 훅이 두 가지 일을 하게 된다 —
            목업에서는 그 단순함이 더 값지다. */}
        <ErrorState
          what="온톨로지"
          detail={data.message}
          onRetry={() => window.location.reload()}
        />
        <Text font="legal" color="fgMuted">
          이 화면은 `/api/universe` 가 첫 관문이에요. {ROUTE_MISSING_DETAIL}
        </Text>
      </div>
    );
  }
  return <Loaded ontology={data.ontology} partial={data.partial} />;
}

/** 주소에서 첫 초점을 **동기적으로** 읽는다.
 *
 * `useUrlState` 는 마운트 뒤 효과에서 주소를 읽으므로, 그것만 쓰면 첫 프레임이
 * 기본 초점(국고 3년)으로 한 번 그려지고 다음 프레임에 주소의 것으로 바뀐다.
 * 그래프에서는 그 한 프레임이 **레이아웃 한 벌을 통째로 다시 그리는 것**이라
 * 눈에 띈다.
 *
 * 렌더 중에 `location` 을 읽어도 되는 이유: 이 컴포넌트는 데이터가 준비된 뒤에만
 * 선다(위 `TerminalShell` 이 그때까지 로딩 화면을 돌려준다). 서버 렌더와 하이드
 * 레이션에는 로딩 화면이 서므로 이 코드가 그때 도는 일이 없다 — 즉 하이드레이션
 * 불일치가 생길 자리가 아니다. */
function initialFocus(ontology: Ontology): string | null {
  if (typeof window !== 'undefined') {
    const fromUrl = new URLSearchParams(window.location.search).get('to');
    if (fromUrl && ontology.byId.has(fromUrl)) return fromUrl;
  }
  return ontology.byId.has('GOVT-3Y') ? 'GOVT-3Y' : (ontology.objects[0]?.id ?? null);
}

function isAppId(v: string | undefined): v is AppId {
  return !!v && APPS.some((a) => a.id === v);
}

function isSpan(v: string | undefined): v is SpanKey {
  return !!v && (CHART_SPANS as readonly string[]).includes(v);
}

function Loaded({ ontology, partial }: { ontology: Ontology; partial: string[] }) {
  /* ── 주소가 곧 상태다 ─────────────────────────────────────────────────────
     `ui/useUrlState.ts` 를 그대로 쓴다(캐논 규칙 1 — 새로 만들기 전에 찾는다).
     그 훅이 이 앱의 규약을 진다: 라우터가 아니라 `history.replaceState`,
     마운트와 `popstate` 에서만 읽기. */
  const [appParam, setAppParam] = useUrlState('ta', 'graph');
  const [focusParam, setFocusParam] = useUrlState('to');
  const [facetParam, setFacetParam] = useUrlState('tf');
  const [rangeParam, setRangeParam] = useUrlState('tr');
  const [spanParam, setSpanParam] = useUrlState('ts', '1Y');
  const [sortParam, setSortParam] = useUrlState('tk');

  const app: AppId = isAppId(appParam) ? appParam : 'graph';
  const span: SpanKey = isSpan(spanParam) ? spanParam : '1Y';
  const sel = useMemo(() => decodeFacets(facetParam), [facetParam]);
  const range = useMemo(() => decodeRange(rangeParam), [rangeParam]);
  const sort = useMemo(
    () => decodeSort<TableSortKey>(sortParam, TABLE_SORT_KEYS, { key: 'z', desc: true }),
    [sortParam],
  );

  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [singleKeys, setSingleKeys] = useState(true);

  /* 저장된 값은 **효과에서** 읽는다. 렌더 중에 읽으면 서버가 그린 것과 갈리고,
     이 컴포넌트가 클라이언트에서만 선다 해도 그 규칙을 깰 이유가 없다. */
  useEffect(() => setSingleKeys(loadSingleKeys()), []);

  const changeSingleKeys = useCallback((v: boolean) => {
    setSingleKeys(v);
    try {
      localStorage.setItem(SINGLE_KEY_STORE, v ? 'on' : 'off');
    } catch {
      /* 저장이 안 되면 이번 세션에만 적용된다 — 화면은 그대로 동작한다. */
    }
  }, []);

  /** 초점과 **그 이력**. Shneiderman 의 «history» 과업 — `useExploration.ts` 머리
   *  에 근거가 있다. 첫 자리는 주소가 정하고, 없으면 국고 3년(이 데스크의 기준물). */
  const explore = useExploration(useMemo(() => initialFocus(ontology), [ontology]));
  const focusId = explore.focusId;

  /* 주소 → 상태. `popstate`(브라우저 뒤로/앞으로)와 마운트에서만 값이 바뀐다.
     같은 값이면 아무 일도 안 하므로, 아래 `goTo` 가 쓴 값이 되돌아와도 조용하다. */
  useEffect(() => {
    if (focusParam && focusParam !== explore.focusId && ontology.byId.has(focusParam)) {
      explore.reset(focusParam);
    }
  }, [focusParam, explore, ontology]);

  const goTo = useCallback(
    (id: string) => {
      explore.go(id);
      setFocusParam(id);
    },
    [explore, setFocusParam],
  );

  /* 뒤로/앞으로가 **닿을 자리를 미리 읽어** 주소에 같이 적는다. `back()` 의
     결과를 효과로 뒤쫓으면 주소→상태 효과와 마주 보게 된다(훅 머리 주석). */
  const goBack = useCallback(() => {
    const t = explore.backTarget;
    explore.back();
    if (t) setFocusParam(t);
  }, [explore, setFocusParam]);

  const goForward = useCallback(() => {
    const t = explore.forwardTarget;
    explore.forward();
    if (t) setFocusParam(t);
  }, [explore, setFocusParam]);

  const result = useMemo(() => {
    const byFacet = applyFacets(ontology.objects, sel);
    if (!range) return byFacet;
    /* 시간이 **없는** 객체(계열·발행체·섹터·만기)는 브러시가 못 거른다 — 그것들을
       시간 구간으로 지우면 그래프에서 사건만 남고 그 사건이 무엇에 붙는지가
       사라진다. 시간축의 필터는 시간이 있는 것에만 건다. */
    return byFacet.filter((o) => o.t == null || (o.t >= range[0] && o.t <= range[1]));
  }, [ontology, sel, range]);

  const visible = useMemo(() => new Set(result.map((o) => o.id)), [result]);

  const toggle = useCallback(
    (f: FacetKey, v: string) => {
      const next: Selection = {};
      for (const k of Object.keys(sel) as FacetKey[]) next[k] = new Set(sel[k]);
      const s = new Set(next[f] ?? []);
      if (s.has(v)) s.delete(v);
      else s.add(v);
      if (s.size === 0) delete next[f];
      else next[f] = s;
      setFacetParam(encodeFacets(next));
    },
    [sel, setFacetParam],
  );

  const setRange = useCallback(
    (r: [number, number] | null) => setRangeParam(encodeRange(r)),
    [setRangeParam],
  );

  const clear = useCallback(() => {
    setFacetParam(undefined);
    setRangeParam(undefined);
  }, [setFacetParam, setRangeParam]);

  /* ── 키보드 ─────────────────────────────────────────────────────────────
     `Ctrl/Cmd+K` 는 커맨드 팔레트의 지금 관례다(VS Code·Linear·Vercel 이 같은
     키를 쓴다). 관례를 따르는 것 자체가 근거다 — 이 화면만의 키를 새로 만들면
     배울 것이 하나 늘고, 그 하나가 팔레트가 주는 시간을 도로 먹는다.

     `/` 와 `?` 도 받는다. 읽기 전용 화면의 오래된 관례이고, 입력 칸 안에서는 안
     듣게 막았다. 다만 **한 글자 단축키는 끌 수 있어야 한다**(WCAG 2.1.4) —
     `singleKeys` 가 그 스위치이고, 단축키 목록에서 만진다.

     축 바꾸기는 `Alt+1…4` 다. 맨숫자로 두면 그것도 2.1.4 의 대상이 되어 끄기
     스위치에 딸려 나가는데, 축 바꾸기는 이 화면의 기본 동작이라 늘 있어야 한다.
     조합키는 2.1.4 가 요구하는 «수정자를 함께 누른다» 를 이미 만족한다. */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const typing =
        !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable);
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen(true);
        return;
      }
      if (e.altKey && !e.ctrlKey && !e.metaKey) {
        /* 뒤로/앞으로는 **버튼과 같은 함수**를 지나간다. 한때 이 키를
           `useExploration` 이 직접 들었는데, 그쪽은 주소를 안 써서 셸의
           «주소 → 상태» 효과가 곧바로 되돌려 놨다 — 즉 눌러도 아무 일이 안
           일어났다(실측 2026-08-27). 이력과 주소를 함께 쓰는 자리는 하나여야
           한다. 입력 칸 안에서는 안 듣는다(치던 글자가 사라지므로). */
        if (!typing && e.key === 'ArrowLeft') {
          e.preventDefault();
          goBack();
          return;
        }
        if (!typing && e.key === 'ArrowRight') {
          e.preventDefault();
          goForward();
          return;
        }
        const n = Number(e.key);
        if (Number.isInteger(n) && n >= 1 && n <= APPS.length) {
          e.preventDefault();
          setAppParam(APPS[n - 1].id);
        }
        return;
      }
      if (typing || !singleKeys) return;
      if (e.key === '/') {
        e.preventDefault();
        setPaletteOpen(true);
      } else if (e.key === '?') {
        e.preventDefault();
        setHelpOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [singleKeys, setAppParam, goBack, goForward]);

  /** 「추출」 — Shneiderman 의 일곱 번째 과업. 지금 결과를 **탭 구분 텍스트**로
   *  클립보드에 넣는다. 엑셀·구글시트가 탭 구분을 그대로 표로 붙여넣기 때문이고,
   *  파일 내려받기보다 한 단계 짧다.
   *
   *  열은 표 축이 보여주는 것과 **같은 것**을 쓴다 — 화면에서 본 것과 붙여넣은
   *  것이 다르면 그건 다른 데이터다. */
  const extract = useCallback(async () => {
    const head = ['종류', '이름', 'id', '현재', '1D', '1Y%', 'z', 'Score', '출처'].join('\t');
    const body = result
      .map((o) =>
        [
          o.type,
          o.title,
          o.id,
          o.num?.now ?? '',
          o.num?.d1 ?? '',
          o.num?.pct1y ?? '',
          o.num?.z ?? '',
          o.num?.score ?? '',
          o.source,
        ].join('\t'),
      )
      .join('\n');
    try {
      await navigator.clipboard.writeText(`${head}\n${body}`);
      setCopied(`${result.length.toLocaleString('ko-KR')}행을 클립보드에 넣었어요`);
    } catch {
      /* 클립보드가 막힌 브라우저·비보안 출처 — 조용히 실패하지 않는다. */
      setCopied('클립보드를 쓸 수 없어요 (브라우저가 막았습니다)');
    }
    window.setTimeout(() => setCopied(null), 2600);
  }, [result]);

  const focused = focusId ? ontology.byId.get(focusId) : undefined;

  /* 차트 축은 **계열**에만 뜻이 있다. 계열이 아닌 것을 고른 채 넘어오면 그것과
     닿아 있는 계열 하나를 그린다 — 축을 바꿨다고 보고 있던 대상이 사라지면 안
     되고, 무엇으로 갈아탔는지는 `chartNote` 가 말한다. */
  const chart = useMemo(() => {
    if (!focused) return { target: null, note: undefined as string | undefined };
    if (focused.type === 'instrument') return { target: focused, note: undefined };
    for (const l of ontology.adj.get(focused.id) ?? []) {
      const other = ontology.byId.get(l.a === focused.id ? l.b : l.a);
      if (other?.type === 'instrument') return { target: other, note: `${focused.title} 에서` };
    }
    return { target: null, note: `${focused.title} 에는 붙은 계열이 없어요` };
  }, [ontology, focused]);

  /** 화면 밖으로 나가는 한 줄 — **스크린 리더가 읽는 사실**.
   *
   *  이 화면의 변화는 전부 그림에서 일어난다(그래프가 다시 뻗고, 막대가 다시
   *  그려지고, 표가 좁아진다). 그림을 못 보는 사람에게 그 셋은 아무 소리도
   *  안 낸다 — 눌렀는데 아무 일도 안 일어난 것과 구별되지 않는다.
   *
   *  그래서 «지금 무엇을 보고 있고 결과가 몇 개인가» 를 한 문장으로 세운다.
   *  `aria-live="polite"` 라 읽던 것을 끊지 않고 사이에 끼워 읽는다. 클립보드
   *  결과도 같은 줄이 진다 — 그것도 화면에서만 보이던 사실이었다. */
  const live = useMemo(() => {
    if (copied) return copied;
    const what = focused ? `${focused.title} · ${focused.subtitle}` : '고른 객체 없음';
    const axis = APPS.find((a) => a.id === app)!.label;
    return `${axis} 축 · ${what} · 결과 ${result.length.toLocaleString('ko-KR')}개`;
  }, [copied, focused, app, result.length]);

  const asof = ontology.asof;

  return (
    /* `data-sr-scheme="dark"` 는 장식이 아니라 **배선**이다 — 방향 쌍·
       `color-scheme`·상속 글자색이 그 속성에 걸려 있다(`theme/terminal.css`
       루트 주석). */
    <div className="sr-term" data-sr-scheme="dark">
      {/* ── 블록 건너뛰기 (WCAG 2.4.1) ────────────────────────────────────
          왼쪽 칸에는 패싯 막대가 마흔 개 넘게 서 있다. 키보드로 들어온 사람은
          가운데 화면에 닿기까지 그것을 전부 지나야 했다 — 탭 마흔 번이 «화면을
          연다» 의 비용이 되면 그 화면은 키보드로 못 쓰는 것이다. */}
      <a className="sr-term-skip" href="#sr-term-viewport">
        가운데 화면으로 건너뛰기
      </a>

      <ObjectExplorer
        all={ontology.objects}
        result={result}
        sel={sel}
        range={range}
        onToggle={toggle}
        onClear={clear}
        onClearRange={() => setRange(null)}
      />

      <main className="sr-term-col" data-viewport="true" id="sr-term-viewport" aria-label="뷰포트">
        <PanelHead
          label={APPS.find((a) => a.id === app)!.label}
          brace
          note={`${result.length.toLocaleString('ko-KR')}개 객체${range ? ' · 구간 한정' : ''}`}
        />

        <div className="sr-term-appbar">
          <div className="sr-term-seg" role="group" aria-label="축">
            {APPS.map((a, i) => (
              <button
                key={a.id}
                type="button"
                className="sr-term-seg-btn"
                data-on={a.id === app}
                aria-pressed={a.id === app}
                title={`${a.hint} (Alt+${i + 1})`}
                onClick={() => setAppParam(a.id)}
              >
                {a.label}
              </button>
            ))}
          </div>
          {/* 이력 — 뒤로/앞으로. **보이는 버튼과 단축키를 둘 다** 둔다:
              커맨드 팔레트 지침이 «중요한 명령은 눈에 보이는 자리에도 두어
              키보드만이 유일한 길이 되지 않게 하라» 고 하는 그것이다. */}
          <div className="sr-term-seg" role="group" aria-label="이력">
            <button
              type="button"
              className="sr-term-seg-btn"
              onClick={goBack}
              disabled={!explore.canBack}
              title="뒤로 (Alt+←)"
              aria-label="뒤로"
            >
              ←
            </button>
            <button
              type="button"
              className="sr-term-seg-btn"
              onClick={goForward}
              disabled={!explore.canForward}
              title="앞으로 (Alt+→)"
              aria-label="앞으로"
            >
              →
            </button>
          </div>

          <button
            type="button"
            className="sr-term-seg-btn sr-term-clear"
            onClick={() => setPaletteOpen(true)}
            title="객체 찾기 (Ctrl+K)"
          >
            찾기 Ctrl+K
          </button>

          <button
            type="button"
            className="sr-term-seg-btn sr-term-clear"
            onClick={extract}
            title="지금 결과를 클립보드로"
          >
            추출
          </button>

          {/* 단축키가 **화면에 있다**. 여기 버튼이 없으면 `?` 를 아는 사람만 그
              목록을 열 수 있고, 그건 단축키를 아는 사람에게만 단축키를 알려
              주는 것이다. */}
          <button
            type="button"
            className="sr-term-seg-btn sr-term-clear"
            onClick={() => setHelpOpen(true)}
            title="단축키 (?)"
          >
            단축키 ?
          </button>

          <Text font="legal" color="fgMuted" noWrap>
            {copied ?? APPS.find((a) => a.id === app)!.hint}
          </Text>
        </div>

        {/* ── 지금까지 온 길 ───────────────────────────────────────────────
            search-around 은 «어디서 여기로 왔는지» 를 잃기 쉽다. 마지막 네
            자리만 적는다 — 그보다 길면 띠가 두 줄이 되고, 더 앞은 뒤로 가기가
            데려다 준다. */}
        {explore.trail.length > 1 ? (
          <nav className="sr-term-trail" aria-label="지나온 길">
            {explore.trail.slice(-4).map((id, i, arr) => {
              const o = ontology.byId.get(id);
              if (!o) return null;
              const last = i === arr.length - 1;
              return (
                <span key={`${id}-${i}`} className="sr-term-crumb" data-on={last}>
                  {i > 0 ? (
                    <span className="sr-term-crumb-sep" aria-hidden>
                      ›
                    </span>
                  ) : null}
                  <button
                    type="button"
                    className="sr-term-crumb-btn"
                    onClick={() => goTo(id)}
                    aria-current={last ? 'true' : undefined}
                  >
                    {o.title}
                  </button>
                </span>
              );
            })}
          </nav>
        ) : null}

        {app === 'graph' ? (
          <GraphApp
            ontology={ontology}
            focusId={focusId}
            onFocus={goTo}
            visible={visible}
            onClearFilters={clear}
          />
        ) : null}

        {app === 'timeline' ? (
          <TimelineApp
            objects={result}
            focusId={focusId}
            onFocus={goTo}
            range={range}
            onRange={setRange}
          />
        ) : null}

        {app === 'table' ? (
          <TableApp
            objects={result}
            focusId={focusId}
            onFocus={goTo}
            sort={sort}
            onSort={(s) => setSortParam(encodeSort(s))}
          />
        ) : null}

        {app === 'chart' ? (
          <ChartApp
            target={chart.target}
            span={span}
            onSpan={(s) => setSpanParam(s)}
            note={chart.note}
          />
        ) : null}

        {/* ── 화면이 말해야 하는 것들 ─────────────────────────────────────
            as-of, 못 이은 것, 읽어 온 창의 상한, 데이터의 caveat. 이 리포는
            «조용한 절단» 과 «출처 없는 값» 을 결함으로 다루고, 이 띠가 그
            규율이 화면에 서는 자리다. */}
        <div className="sr-term-notes sr-term-sep">
          <span className="sr-term-eyebrow">As of</span>
          <Text font="legal" color="fgMuted" tabularNumbers>
            {[
              asof.universe ? `유니버스 ${asof.universe}` : null,
              asof.mrBss ? `밴드 ${asof.mrBss}` : null,
              asof.rv ? `RV ${asof.rv}` : null,
              asof.today ? `오늘 ${asof.today}` : null,
            ]
              .filter(Boolean)
              .join(' · ')}
          </Text>
          <ul className="sr-term-notelist">
            {[...partial, ...ontology.notes].map((n) => (
              <li key={n}>
                <Text font="legal" color="fgMuted">
                  {n}
                </Text>
              </li>
            ))}
          </ul>
        </div>
      </main>

      <Dossier ontology={ontology} focusId={focusId} onFocus={goTo} visible={visible} />

      {/* 팔레트는 **전체 객체**에서 찾는다 — 필터 결과가 아니라. 필터에 가려진
          것으로 가려는 것이 검색을 쓰는 흔한 이유이고, 거기서도 걸러 버리면
          「분명히 있는데 안 나온다」가 된다. */}
      <CommandPalette
        objects={ontology.objects}
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onPick={goTo}
      />

      <ShortcutHelp
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        singleKeys={singleKeys}
        onSingleKeys={changeSingleKeys}
      />

      {/* 화면 밖 한 줄 — 위 `live` 주석이 이 자리의 근거다. */}
      <span className="sr-a11y-only" aria-live="polite">
        {live}
      </span>
    </div>
  );
}
