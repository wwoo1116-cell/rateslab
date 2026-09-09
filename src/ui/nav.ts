/* 두 층의 탐색 — 상단 바 다섯 섹션과 그 아래 메가 패널 [OWNER 2026-08-13].
 *
 * v1(`braveworld/frontend/src/ui/tabs.ts`)이 이미 Main / Backtest / Simulation /
 * Lab 을 정의해뒀고, 오너가 여기에 **Strategy** 를 더했다. 배치는 사이드바가 아니라
 * coinbase.com 의 상단 내비 + 메가메뉴다.
 *
 * ── 섹션은 상태가 아니라 유도값이다 (v1 의 규칙, 그대로 가져옴) ─────────────
 * 화면은 탭 값 하나만 들고 있고 표·미리보기·URL 이 전부 그걸 읽는다. 섹션을 두 번째
 * 상태로 두면 "Backtest 인데 종목군이 없음" 처럼 **화면에 존재하지 않는 조합**이
 * 표현 가능해진다. 그래서 `sectionOf()` 로 유도한다.
 */

import { GROUP_LABEL, type Group } from '@/table/rows';

/** 탭 = 종목군 · 오버뷰 · 시뮬레이션 · 전략 · 설정 · 연구실. URL 의 `g` 가 드는 값이다. */
export type TabId = Group | 'all' | 'sim' | 'strategy' | 'setting' | 'lab';

export type SectionId = 'main' | 'backtest' | 'simulation' | 'strategy' | 'setting' | 'lab';

export type Section = {
  id: SectionId;
  label: string;
  /** 메가 패널 오른쪽에 서는 한 줄. 이 섹션이 무엇을 하는 곳인지. */
  blurb: string;
  /** 섹션을 눌렀을 때 갈 탭. Backtest 만 마지막으로 보던 종목군으로 돌아간다. */
  tab: TabId | null;
};

/** 라벨은 영문 그대로 — v1 에서 오너가 그렇게 부른다. 앱 이름은 어디에도 없다
 * [OWNER 2026-08-07 — "sauron은 예명이야"]. */
export const SECTIONS: Section[] = [
  { id: 'main', label: 'Main', blurb: '오늘 시장을 한 화면에서 본다.', tab: 'all' },
  {
    id: 'backtest',
    label: 'Backtest',
    blurb: '행을 고르고, 차트를 보고, 그 자리에서 백테스트한다.',
    tab: null, // 마지막 종목군으로 — `tabForSection` 참조
  },
  { id: 'simulation', label: 'Simulation', blurb: '금리 시나리오를 넣고 손익을 본다.', tab: 'sim' },
  /* Strategy = RV Analysis [OWNER 2026-08-18 — "RV = v2 Strategy 섹션"]. 랭킹이지
   * 투자판단이 아니다 — blurb 도 그 문법을 지킨다(명령형·추천 금지). */
  /* 어휘는 사분면 라벨과 같은 결이다 [OWNER 2026-08-19 — "싸고 버팀" 계열 교체]. */
  /* **세입자를 두는 섹션이 됐다** [OWNER 2026-08-24] — 곧 둘째 전략이 들어온다.
     blurb 는 이제 «이 섹션이 무엇을 하는 곳인가» 이고, 지금 보고 있는 전략의
     이름은 `STRATEGY_ITEMS` 가 진다(Lab 이 세입자 이름을 h1 으로 쓰는 그 규칙). */
  { id: 'strategy', label: 'Strategy', blurb: '상대가치를 재는 화면들.', tab: 'strategy' },
  /* Setting 은 데이터 화면이 아니라 **다른 화면들이 읽는 값을 정하는 자리**라
   * 최상위다 [OWNER, 2026-08-14]. 지금은 조달금리 하나뿐이고, 그 값은 Cash
   * Bond 백테스트가 읽는다.
   *
   * **Lab 앞이다** [OWNER 규칙]. 섹션 순서는 확신의 순서이고 Lab 은 그
   * 가장자리라 반드시 마지막이어야 한다(실험은 가장자리에서 들어와 앞으로
   * 졸업한다). Setting 은 그 사다리에 참여하지 않는 유틸리티 화면이라 졸업할
   * 것도 없고, 뒤에 두면 Lab 이 마지막이 아니게 된다. */
  { id: 'setting', label: 'Setting', blurb: '다른 화면이 읽는 값을 정한다.', tab: 'setting' },
  { id: 'lab', label: 'Lab', blurb: '아직 규칙이 되지 못한 것들.', tab: 'lab' },
];

/** 메가 패널 한 칸. Coinbase 의 항목 구조 그대로 — 글리프 + 제목 + 한 줄 설명. */
export type NavItem = {
  id: TabId;
  label: string;
  desc: string;
  /** 글리프는 v1 이 고른 문자 그대로다(`ui/tabs.ts`). 아이콘 폰트를 새로 고르면
   * 두 제품이 같은 것을 다른 그림으로 부르게 된다. */
  glyph: string;
  /** false 면 아직 화면이 없다는 뜻. 눌러도 되지만 빈 상태가 그렇게 말한다. */
  ready: boolean;
};

/**
 * Backtest 아래의 자산군 [OWNER 2026-08-13 — "굳이 따지면 스왑, 국채현물,
 * 국채선물, 크레딧"; **축소 2026-08-19** — "가상 데이터가 들어갔던 본드스왑,
 * 국고, 국채선물, 크레딧 지워주고"]. 국채현물·국채선물·크레딧 카테고리와 스왑
 * 아래의 본드스왑 탭이 그날 내려갔다. `Group` 값 자체는 건드리지 않는다 —
 * 행·정렬·사다리가 전부 그 값을 읽기 때문이고, 유니버스 백엔드도 그대로다.
 * 탭을 되살리려면 여기 배열(과 `page.tsx` 의 GROUPS)에 도로 넣으면 된다.
 */
export type CategoryId = 'swap' | 'cashbond' | 'futures';

export const BACKTEST_CATEGORIES: {
  id: CategoryId;
  label: string;
  desc: string;
  groups: Group[];
}[] = [
  {
    id: 'swap',
    label: '스왑',
    desc: 'IRS 아웃라이트와 거기서 나오는 스프레드·플라이·포워드',
    groups: ['outright', 'spread', 'fly', 'forward', 'vol'],
  },
  /* 항목 둘이 **별개 표 탭**인 것이 v1 규칙이다(v1 tabs.ts — 현금채권과
   * 자산스왑은 유니버스와 단위가 다른 딴 표다). 민평 8종 × 만기 격자에서 par
   * 발행한 3개월 이표채와, 같은 채권에 같은 명목의 페이 고정을 얹은 par-par
   * 패키지. 민평이 SQL 라이브라 2026-08-19 축소에서 살아남았다 [OWNER 확인]. */
  {
    id: 'cashbond',
    label: '현금채권',
    desc: '민평 커브에서 par 로 발행한 채권과 그 자산스왑',
    groups: ['cashbond', 'asw'],
  },
  /* 국채선물은 2026-08-19 에 «가상 데이터» 로 내려갔다가 **되돌아온다**
     [OWNER, 2026-08-25 — "선물, 퓨처스왑도 스왑·현금채권과 같은 분류에"].
     그날 내려간 이유가 사라졌기 때문이다: 이 카테고리의 행은 전부 벤더
     테이블(`infomax.daily_ktb_price`/`daily_lktb_price`)에서 **읽은** 값이고,
     퓨처스왑은 그 내재금리와 `mkt_irs_close` 의 교집합이다. 유도가 없다.
     같이 내려간 국고·본드스왑·크레딧은 그대로 둔다 — 이 레인의 질문이 아니다. */
  {
    id: 'futures',
    label: '국채선물',
    desc: '3년·10년 국채선물과 그 내재금리에서 나오는 퓨처스왑',
    groups: ['futures', 'futuresswap'],
  },
];

/** v1 의 글리프를 그대로. 없는 그룹은 v1 에 없던 자산군이라 같은 계열에서 골랐다. */
const GROUP_GLYPH: Record<Group, string> = {
  outright: '●',
  spread: '◧',
  fly: '◆',
  forward: '▶',
  vol: '〜',
  govt: '◍',
  bss: '◫',
  credit: '◈',
  futures: '◇',
  futuresswap: '⇆',
  cashbond: '▣',
  asw: '⇄',
};

const GROUP_DESC: Record<Group, string> = {
  outright: '고정금리의 절대 수준',
  spread: '두 만기의 차 — 커브가 서는지 눕는지',
  fly: '가운데 만기가 양 날개 대비 비싼지',
  forward: '미래 시점에서 시작하는 금리',
  vol: '만기별 상대 변동성',
  govt: '국고채 수익률',
  bss: '국고 대비 스왑의 차',
  credit: '국고 대비 신용 스프레드',
  futures: '3년·10년 선물 — 가격 · 내재금리 · 저평가',
  futuresswap: '선물 내재금리 − IRS · 같은 만기',
  cashbond: '민평 수익률 · 3개월 이표채로 가정',
  asw: '민평 − IRS · 같은 만기 · 같은 명목',
};

/** 한 카테고리가 펼치는 항목들. */
export function itemsOf(cat: CategoryId): NavItem[] {
  const c = BACKTEST_CATEGORIES.find((x) => x.id === cat);
  if (!c) return [];
  return c.groups.map((g) => ({
    id: g,
    label: GROUP_LABEL[g],
    desc: GROUP_DESC[g],
    glyph: GROUP_GLYPH[g],
    ready: true,
  }));
}

/** 탭에서 섹션을 유도한다. 두 번째 상태를 만들지 않는 지점. */
export function sectionOf(t: TabId): SectionId {
  if (t === 'all') return 'main';
  if (t === 'sim') return 'simulation';
  if (t === 'strategy') return 'strategy';
  if (t === 'setting') return 'setting';
  if (t === 'lab') return 'lab';
  return 'backtest';
}

/** 섹션을 누르면 어디로 가나. Backtest 는 **마지막으로 보던 종목군**으로 돌아간다 —
 * 늘 아웃라이트로 되돌리면 스프레드를 보다 Main 을 한 번 들른 사람이 자리를 잃는다
 * (v1 의 이유 그대로). */
export function tabForSection(s: SectionId, lastGroup: Group): TabId {
  const sec = SECTIONS.find((x) => x.id === s);
  return sec?.tab ?? lastGroup;
}

/* ── Lab 의 세입자들 [2026-08-20] ─────────────────────────────────────────────
 *
 * 세입자가 둘이 되면서 Lab 도 메가 패널을 연다. 이 파일의 위 주석이 이미 그
 * 규칙을 적어 두었다 — "목적지가 하나면 버튼이지 메뉴가 아니다". 반대도 참이다.
 *
 * **위계는 셋이 같다** [OWNER, 2026-08-20]. 세입자끼리 서로를 읽지 않고, 셋을
 * 잇는 화면도 만들지 않는다. 각자 들어와서 각자 졸업하기 때문이다 — 시나리오가
 * Simulation 으로 올라가는 날 표면이 딸려 올라가면 안 된다. 그래서 목록에 순서
 * 말고는 아무 강조도 없다.
 *
 * 세입자는 **탭이 아니라 URL 상태**다(`?g=lab&lab=scenario`). 탭을 늘리면
 * `sectionOf()` 가 드는 «섹션은 유도값» 규칙에 두 번째 상태가 끼어든다. */
export type LabId = 'surface' | 'issuance' | 'model';

/** 내려간 세입자. 공유된 링크가 죽지 않게 갈 곳을 적어 둔다. */
export const RETIRED_LAB: Record<string, LabId> = { scenario: 'model' };

export const DEFAULT_LAB: LabId = 'surface';

export const LAB_ITEMS: { id: LabId; label: string; desc: string; glyph: string }[] = [
  { id: 'surface', label: '커브 표면', desc: '풀별 커브가 지난 몇 해 어떻게 움직였나', glyph: '◇' },
  { id: 'issuance', label: '발행 캘린더', desc: '내일 이 섹터에 얼마가 새로 얹히나', glyph: '▤' },
  /* 「모형」이 시나리오를 **대체했다** [OWNER 2026-08-21, 2026-08-21 시행].
     시나리오는 여기서 내려갔다 — 죽은 쌍둥이로 남기지 않는다. 그 화면이 하던
     일은 세 면으로 갈라졌다: 손잡이와 결과표는 「전략」, 논문 Figure 18 의 여덟
     칸은 「모형」의 기저 충격반응, 원장 줄은 「방법」의 해석 원장.
     셈 모듈(`lab/scenario/combine.ts` 등)은 **그대로 산다** — 「전략」이 같은
     산술을 쓰기 때문이고, 가드 40개가 계속 그 산술을 잠근다. */
  { id: 'model', label: '모형', desc: '경로 하나로 데스크 노트까지, 그리고 그 숫자가 어디서 왔는지', glyph: '⌗' },
];

export function isLabId(v: string | undefined): v is LabId {
  return v === 'surface' || v === 'issuance' || v === 'model';
}

/* ── Strategy 의 세입자들 [OWNER 2026-08-24] ─────────────────────────────────
 *
 * 「Strategy Tab에 곧 하나 다른 전략을 도입할 예정이라서 Credit RV라는 이름으로
 * 지금 있던 탭을 분리해서 다른 Backtest나 Lab과 같은 형태로 분리해두자」.
 *
 * Lab 의 세입자 기계를 **그대로** 본떴다. 새 문법을 만들지 않는다 — 두 섹션이
 * 같은 일(여러 화면을 한 섹션 아래 두기)을 다른 방식으로 하면, 셋째가 생기는
 * 날 어느 쪽을 따를지가 취향 문제가 된다.
 *
 * 세입자는 **탭이 아니라 URL 상태**다(`?g=strategy&s=credit-rv`). 탭을 늘리면
 * `sectionOf()` 가 드는 «섹션은 유도값» 규칙에 두 번째 상태가 끼어든다.
 *
 * ## 둘째 세입자가 들어와 패널이 열렸다 [2026-08-25]
 *
 * 「지금은 패널을 안 연다」던 자리다 — 목적지가 둘이 되어 `PANELED` 에
 * 'strategy' 가 들어갔고, 예고대로 가드(nav-strategy-tenants)가 먼저 빨개져서
 * 이 이동을 요구했다.
 *
 * ## 이름에 대해 [OWNER 확인]
 *
 * 유니버스 8섹터에 **국고채·통안채가 들어 있다**(산금채AAA·공사채AAA·은행채AAA·
 * 회사채AAA·카드채AA+·캐피탈채AA- 와 함께). 그 둘은 벤치마크로 같이 서는 것이고,
 * 데스크가 이 화면을 「크레딧 RV」로 부르는 것이 맞다는 판단이다. 화면이 그
 * 사실을 한 줄로 말한다. */
export type StrategyId = 'credit-rv' | 'mean-reversion' | 'momentum';

export const DEFAULT_STRATEGY: StrategyId = 'credit-rv';

export const STRATEGY_ITEMS: {
  id: StrategyId;
  label: string;
  desc: string;
  glyph: string;
}[] = [
  {
    id: 'credit-rv',
    label: 'Credit RV',
    desc: '평소 대비 얼마나 벌어졌고 버퍼가 얼마나 남는지 — 8섹터 랭킹',
    /* 글리프는 v1 이 크레딧에 쓰던 것 그대로(`GROUP_GLYPH.credit`). 같은 것을
       두 그림으로 부르지 않는다. */
    glyph: '◈',
  },
  /* 둘째 세입자 [OWNER 2026-08-25]. **측정이지 신호가 아니다** — 사전등록 검증
     (Desktop\bollinger-mr, 누적 108구성)이 「볼린저 재진입」 신호 문법을 NO-GO 로
     닫았고, 이 화면은 그 결론 위에 선다: 밴드 대비 위치를 재서 세울 뿐 진입·
     청산·추천을 말하지 않는다(Credit RV 의 「랭킹이지 투자판단이 아니다」와
     같은 명구 의무). desc 도 그 문법이다 — 명령형·추천 금지. */
  {
    id: 'mean-reversion',
    label: 'Mean Reversion',
    /* 유니버스 = 본드스왑 전 테너 + 국채선물 내재금리 + 퓨처스왑 [OWNER
       2026-08-25 — "일단 본드스왑만" → 같은 날 "선물 들어왔는데 … 퓨처스왑
       롱숏도 반영하기"]. 근거는 backend/app/mr.py 머리. */
    desc: '본드스왑·선물내재·퓨처스왑이 평소 밴드 대비 얼마나 늘어났는지 — 랭킹',
    /* 진동 곡선 — 기존 글리프 계열(도형·화살)에 같은 뜻의 그림이 없어 새로
       골랐다. vol 의 '〜'(상대 변동성)와는 딴 것이라 같은 그림을 안 쓴다. */
    glyph: '∿',
  },
  /* 셋째 세입자 [OWNER 2026-09-09 — "v2 strategy tab 밑에 지금까지 한 거
     momentum으로 붙이는 계획. 위계상으로는 RV, MR과 동일"]. **방향과 강도를
     재는 화면이지 단독 전략이 아니다** — 선물 추세 단독은 자본비용 전액 규약에서
     MMF 초과 −1.07 ~ +0.97%/년이었다(research\ktb-tsmom). 이웃 둘의 명구 의무를
     같은 문법으로 진다(desc 도 명령형·추천 금지).

     구조는 «등록된 북» 그대로다 — AQR 병렬 50/50 의 두 다리(추세·매크로)이고,
     추세 다리의 신호는 macross 하나다. tsmom·donchian 은 PBO 격자 차원이지 이
     북에 안 든다(backend/app/momentum.py 머리). */
  {
    id: 'momentum',
    label: 'Momentum',
    desc: '추세가 어느 쪽으로 얼마나 강한지 — 계약별 속도 프로파일과 매크로 다리',
    /* 오름 화살 [OWNER 2026-09-09 확인]. 변화 셀의 `directionGlyph`(↗↘)와 그림이
       겹치지만, 거기서는 «그 값의 부호»이고 여기서는 «추세»라 뜻이 이어진다 —
       오너가 그대로 가기로 정했다. */
    glyph: '↗',
  },
];

export function isStrategyId(v: string | undefined): v is StrategyId {
  return v === 'credit-rv' || v === 'mean-reversion' || v === 'momentum';
}

/** 내려간 세입자. 지금은 없지만 자리를 비워 둔다 — `RETIRED_LAB` 과 같은 이유로,
 *  공유된 링크가 조용히 엉뚱한 데로 가면 링크를 준 사람이 거짓말을 한 셈이 된다. */
export const RETIRED_STRATEGY: Record<string, StrategyId> = {};

/**
 * URL 의 세입자 키를 지금 사는 세입자로 옮긴다.
 *
 * 키가 아예 없는 경우(= 예전 `?g=strategy` 링크)도 기본 세입자로 떨어진다.
 * 그 링크들은 **안 죽는다** — 지금 세입자가 하나뿐이라 가리키던 화면 그대로다.
 */
export function resolveStrategy(v: string | undefined): StrategyId {
  if (isStrategyId(v)) return v;
  return (v && RETIRED_STRATEGY[v]) || DEFAULT_STRATEGY;
}

/**
 * URL 의 세입자 키를 지금 사는 세입자로 옮긴다.
 *
 * `lab=scenario` 를 그냥 모르는 값으로 두면 기본 세입자(커브 표면)로 떨어지는데,
 * 그건 **다른 화면**이다. 공유된 링크가 조용히 엉뚱한 데로 가면 링크를 준 사람이
 * 거짓말을 한 셈이 된다.
 */
export function resolveLab(v: string | undefined): LabId {
  if (isLabId(v)) return v;
  return (v && RETIRED_LAB[v]) || DEFAULT_LAB;
}

/** 메가 패널을 여는 섹션. 나머지는 목적지가 하나뿐이라 버튼이다.
 * Strategy 는 2026-08-25 둘째 세입자(Mean Reversion)와 함께 들어왔다 —
 * 가드(nav-strategy-tenants)의 «세입자 수 ↔ 패널» 불변식이 요구한 이동이다. */
export const PANELED: SectionId[] = ['backtest', 'lab', 'strategy'];

/** 그 그룹이 속한 카테고리. 메가 패널에서 지금 자리를 표시할 때 쓴다. */
export function categoryOf(g: Group): CategoryId | undefined {
  return BACKTEST_CATEGORIES.find((c) => c.groups.includes(g))?.id;
}

export const DEFAULT_GROUP: Group = 'outright';

/** 아직 화면이 없는 섹션. 빈 상태가 이유를 말해야 하므로 여기에 이유를 둔다.
 *
 * 시뮬레이션(레인 5)·연구실(커브 표면)·Strategy(RV Analysis, rv2)가 차례로
 * **여기서 내려갔다** — 화면이 생겼기 때문이다. 지금은 빈 목록이고, 새 섹션이
 * 생기면 화면보다 이유가 먼저 여기 선다. */
export const NOT_BUILT: Partial<Record<SectionId, string>> = {};
