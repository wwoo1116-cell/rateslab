/**
 * 온톨로지 — **실제로 연결된 데이터에서만** 짓는다.
 *
 * ── 방향 전환 [OWNER 2026-08-26 — "실제 연결된 데이터에 기반해서 사용할 수
 *    있는 것만 만들기"] ─────────────────────────────────────────────────────
 * 앞선 판은 체결 600건·거래상대 여덟 곳을 **지어냈다**. 그것들은 이 백엔드에
 * 없다 — `backend/app/main.py` 의 라우트 전수를 확인했고, 체결 로그도 거래상대
 * 마스터도 없다. 그래서 지운다. 목업이 없는 것을 있는 척하면 그 화면으로는
 * 「이 문법이 이 데스크에서 쓸모 있는가」를 판단할 수 없고, 판단할 수 없는
 * 화면은 목업의 일을 안 하는 것이다.
 *
 * 대신 이 앱이 **진짜로 가진 것**으로 짓는다. 세 엔드포인트가 원천이다:
 *
 *     /api/universe            122행 — 국고 9 · 크레딧 96 · BSS 9 · 선물 6 · 퓨처스왑 2
 *     /api/mr/board            13행 — 볼린저 밴드 z·상태·순위
 *     /api/issuance/calendar   두 달 43영업일 — 섹터 발행액·그날의 일정
 *     /api/issuance/day/{iso}  그날의 **원문** — DART 발행 건·기재부 입찰 결과·출처 URL
 *
 * ── Gotham 의 것을 가져오되, 관계는 **유도**한다 ─────────────────────────────
 * 링크가 이 화면의 전부다. 그리고 이 데스크의 링크는 지어낼 필요가 없다 —
 * **id 가 이미 정의를 담고 있다**:
 *
 *     BSS-3Y        = 국고 3Y − IRS 3Y      → GOVT-3Y 로 이어진다
 *     FUT-KTB3-IY   = 3년 선물의 내재금리    → FUT-KTB3 에서 나온다
 *     FSW-KTB3      = 내재금리 − IRS 3Y     → FUT-KTB3-IY 에서 나온다
 *     CRD-BD-3Y     = 은행채 3년            → 발행체 「은행」 · 만기 3Y
 *
 * 그래서 이 파일은 관계를 **만들지 않고 읽는다**. 무작위로 이으면 그래프는
 * 예쁜 털뭉치가 되고, 그 화면으로는 아무것도 판단할 수 없다.
 *
 * ── 못 잇는 것은 안 잇는다 ─────────────────────────────────────────────────
 * 두 군데에서 이름이 어긋난다. 억지로 맞추지 않고 **어긋난 채로 둔다**:
 *
 *   1) 발행 캘린더의 섹터(은행·카드·캐피탈·증권·지주·보험·기타금융·공사·리츠·
 *      기타)와 크레딧 커브의 발행체(통안·산금·특수·은행·카드·기타금융·회사
 *      AAA~A)는 **셋만 정확히 겹친다**(은행·카드·기타금융). 「캐피탈」에는 커브가
 *      없다 — OFB 는 「기타금융」으로 라벨돼 있고, 그 둘이 같은 것이라는 근거가
 *      이 데이터 안에 없다. 그래서 이름이 정확히 같을 때만 잇는다.
 *   2) MR 보드는 퓨처스왑을 `FSW-3Y` 로 부르고 유니버스는 `FSW-KTB3` 로 부른다.
 *      이 리포는 이미 그 어휘 갈림을 알고 있다(`backtest/book.ts::MAIN_TO_BOOK_ID`
 *      가 세 번째 어휘 `FSW:3Y` 를 다룬다). 여기서는 표로 못 박고, 표에 없는
 *      id 는 **조용히 버리지 않고** `unmatched` 에 담아 화면이 말하게 한다.
 */

import type { IssuanceCalendar, IssuanceDay } from '@/lab/issuance/api';
import type { MrBoard, MrRow } from '@/mr/api';
import type { RvCreditItem, RvPayload } from '@/rv/api';
import type { UniversePayload } from '@/table/universeRows';

/* ── 종류 ────────────────────────────────────────────────────────────────── */

export type ObjType =
  | 'instrument'
  | 'issuer'
  | 'sector'
  | 'tenor'
  | 'issue'
  | 'auction'
  | 'event';

export const OBJ_LABEL: Record<ObjType, string> = {
  instrument: '계열',
  issuer: '발행체',
  sector: '섹터',
  tenor: '만기',
  issue: '발행',
  auction: '입찰',
  event: '일정',
};

/** 색은 CSS 변수 이름으로 든다 — 값은 `theme/direction.css` 에만 있다. */
export const OBJ_VAR: Record<ObjType, string> = {
  instrument: 'var(--sr-obj-instrument)',
  issuer: 'var(--sr-obj-issuer)',
  sector: 'var(--sr-obj-sector)',
  tenor: 'var(--sr-obj-tenor)',
  issue: 'var(--sr-obj-issue)',
  auction: 'var(--sr-obj-auction)',
  event: 'var(--sr-obj-event)',
};

/** 종류마다 글리프 하나. 색만으로 종류를 말하지 않는다(WCAG 2.2 §1.4.1) —
 *  그래프에서 노드가 작아지면 색은 제일 먼저 안 보이는 채널이다. */
export const OBJ_GLYPH: Record<ObjType, string> = {
  instrument: '◆',
  issuer: '■',
  sector: '⬟',
  tenor: '│',
  issue: '●',
  auction: '▲',
  event: '★',
};

export type LinkKind =
  | 'derives-from'
  | 'has-tenor'
  | 'issued-by'
  | 'in-sector'
  | 'sector-curve'
  | 'auctioned-tenor'
  | 'priced-against'
  | 'on-day';

/** 링크는 **이름을 갖는다**. 「연결됨」은 정보가 아니다. */
export const LINK_LABEL: Record<LinkKind, string> = {
  'derives-from': '구성',
  'has-tenor': '만기',
  'issued-by': '발행체',
  'in-sector': '섹터',
  'sector-curve': '섹터 커브',
  'auctioned-tenor': '입찰 연물',
  'priced-against': '스프레드 기준',
  'on-day': '같은 날',
};

export type Prop = { k: string; v: string };

export type TermObject = {
  id: string;
  type: ObjType;
  title: string;
  subtitle: string;
  props: Prop[];
  /** **어디서 왔나.** 백엔드가 준 출처를 그대로 든다 — 지어낸 문자열이 아니다. */
  source: string;
  /** 출처 원문 링크. 백엔드의 `src` 가 준 것만 — 없으면 `null`. */
  sourceUrl?: string | null;
  /** 시간축에 서는 객체만. epoch ms(UTC 자정 기준). */
  t?: number;
  /** 정렬·패싯이 읽는 값들. 화면 문자열이 아니라 **수**다. */
  num?: Record<string, number | null>;
};

export type TermLink = { a: string; b: string; kind: LinkKind };

export type Ontology = {
  objects: TermObject[];
  links: TermLink[];
  byId: Map<string, TermObject>;
  /** 객체 하나에서 뻗은 링크. search-around 가 읽는 색인. */
  adj: Map<string, TermLink[]>;
  /** 화면이 말해야 하는 것들 — 조용히 넘어가지 않는다. */
  notes: string[];
  asof: {
    universe: string | null;
    mrBss: string | null;
    mrFut: string | null;
    /** 크레딧 민평 매트릭스의 as-of. IRS 와 하루 갈리는 실측이 있어(rv1 B-2)
     *  RV 자체가 소스별로 둘을 드는데, 이 화면이 읽는 값은 민평 쪽이다. */
    rv: string | null;
    today: string | null;
  };
};

/* ── 유도 규칙 ───────────────────────────────────────────────────────────── */

/** 유니버스 id 에서 만기 토큰. `GOVT-3Y`·`CRD-BD-1.5Y`·`BSS-10Y` 가 전부 같은
 *  꼬리를 쓴다. 선물은 만기가 id 에 없어서 아래 표가 따로 맡는다. */
function tenorOfId(id: string): string | null {
  const m = /-((?:\d+(?:\.\d+)?)(?:Y|M))$/.exec(id);
  return m ? m[1] : null;
}

/** 선물의 연물. **id 에 없으므로 표로 못 박는다** — 「3년 국채선물」이라는 라벨이
 *  근거이고, 이 표가 그 라벨을 읽는 유일한 자리다. */
const FUT_TENOR: Record<string, string> = {
  'FUT-KTB3': '3Y',
  'FUT-KTB3-IY': '3Y',
  'FUT-KTB3-BS': '3Y',
  'FSW-KTB3': '3Y',
  'FUT-KTB10': '10Y',
  'FUT-KTB10-IY': '10Y',
  'FUT-KTB10-BS': '10Y',
  'FSW-KTB10': '10Y',
};

/** MR 보드의 id → 유니버스 id. 파일 머리의 «어휘 갈림» 그 표다. */
const MR_TO_UNIVERSE: Record<string, string> = {
  'FSW-3Y': 'FSW-KTB3',
  'FSW-10Y': 'FSW-KTB10',
};

/** 만기를 년 단위 수로. 정렬에만 쓴다 — 화면에는 원문 토큰이 그대로 선다. */
function tenorYears(t: string): number {
  const n = Number(t.replace(/[YM]$/, ''));
  return t.endsWith('M') ? n / 12 : n;
}

/** `derives-from` — id 가 담고 있는 정의를 읽는다. 파일 머리의 그 표. */
function derivesFrom(id: string): string | null {
  const bss = /^BSS-(.+)$/.exec(id);
  if (bss) return `GOVT-${bss[1]}`;
  const futDeriv = /^(FUT-KTB\d+)-(IY|BS)$/.exec(id);
  if (futDeriv) return futDeriv[1];
  const fsw = /^FSW-(KTB\d+)$/.exec(id);
  if (fsw) return `FUT-${fsw[1]}-IY`;
  return null;
}

function isoToMs(iso: string): number {
  const [y, m, d] = iso.split('-').map(Number);
  return Date.UTC(y, m - 1, d);
}

/* ── 짓기 ────────────────────────────────────────────────────────────────── */

export type OntologyInput = {
  universe: UniversePayload;
  mr: MrBoard | null;
  calendar: IssuanceCalendar | null;
  /** 원문을 읽어 온 날들. 전부가 아니라 **최근 몇 날**이다 — 그 상한을 화면이
   *  말하도록 `notes` 에 남긴다(조용한 절단 금지). */
  days: IssuanceDay[];
  /** 크레딧 RV 랭킹. 밴드와 **같은 대우**를 받는다 — 별도 객체가 아니라 계열의
   *  속성으로 접힌다(아래 「RV 를 계열의 속성으로 접는다」). */
  rv: RvPayload | null;
};

/** RV 사분위 라벨. **값 순서가 있는 패싯**이라 이 배열이 곧 막대의 순서다
 *  (`bucketsOf` 가 읽는다) — 개수순으로 세우면 사분위가 뒤섞여 축이 아니게 된다.
 *
 *  이름에 「Score」를 붙이는 이유: 이 화면에는 순위가 될 수 있는 수가 여럿이고
 *  (밴드 z · 저평가 bp · 1년 위치), 「상위 25%」만 적으면 무엇의 상위인지가
 *  안 남는다. */
export const RV_QUARTILES = [
  'Score 상위 25%',
  'Score 25~50%',
  'Score 50~75%',
  'Score 하위 25%',
] as const;

/** 순위 → 사분위 라벨. `rank` 는 1 이 최고 Score(서버가 동점 규칙까지 정한다). */
function rvQuartile(rank: number, total: number): string {
  const q = Math.min(4, Math.max(1, Math.ceil((rank / Math.max(1, total)) * 4)));
  return RV_QUARTILES[q - 1];
}

export function buildOntology(input: OntologyInput): Ontology {
  const { universe, mr, calendar, days, rv } = input;
  const objects: TermObject[] = [];
  const links: TermLink[] = [];
  const notes: string[] = [];
  const ensure = new Set<string>();

  const push = (o: TermObject) => {
    if (ensure.has(o.id)) return;
    ensure.add(o.id);
    objects.push(o);
  };
  const link = (a: string, b: string, kind: LinkKind) => links.push({ a, b, kind });

  /* ── MR 보드를 계열의 속성으로 접는다 ─────────────────────────────────────
     MR 의 id 는 유니버스의 id 와 **같은 것**을 가리킨다(퓨처스왑 둘만 어휘가
     다르고, 그건 위 표가 맡는다). 그러니 별도 객체가 아니다 — 같은 것을 두 노드로
     그리면 그래프가 자기 자신과 이어진 쌍둥이로 덮인다. */
  const mrById = new Map<string, MrRow>();
  const mrUnmatched: string[] = [];
  const universeIds = new Set(universe.rows.map((r) => r.id));
  for (const row of mr?.rows ?? []) {
    const uid = MR_TO_UNIVERSE[row.id] ?? row.id;
    if (universeIds.has(uid)) mrById.set(uid, row);
    else mrUnmatched.push(row.id);
  }
  if (mrUnmatched.length > 0) {
    notes.push(`MR 보드의 ${mrUnmatched.join('·')} 는 유니버스에 같은 id 가 없어 밴드 값이 안 붙었어요.`);
  }

  /* ── RV 를 계열의 속성으로 접는다 ─────────────────────────────────────────
     `/api/rv/analysis` 의 크레딧 항목은 **이미 유니버스의 어휘로 말한다** —
     `seriesId` 가 `CRD-BD-3Y` 처럼 계열 id 그대로다(`rv/api.ts` 가 "universe 의
     CRD 어휘 그대로"라고 적어 둔 그 필드). 그래서 밴드와 똑같이 다룬다: 별도
     노드를 만들지 않고 그 계열의 속성으로 접는다.

     **어휘가 안 맞는 것은 조용히 버리지 않는다.** 실측(2026-08-26): 42개 중
     35개만 붙고 2.5Y 일곱이 남는다 — 유니버스에 2.5Y 노드가 없기 때문이고,
     그건 결함이 아니라 사실이라 화면이 그렇게 말한다.

     서버가 **뺀 것**(`exclusions`)도 적는다. 만기가 H 안에 드는 후보는 금리
     위험이 없어 버퍼가 정의되지 않는데, 그 사실을 안 적으면 「왜 통안 3M 에는
     Score 가 없나」가 화면에서 답이 없는 질문이 된다. */
  const rvById = new Map<string, RvCreditItem>();
  const rvUnmatched: string[] = [];
  const rvItems = rv?.credit.items ?? [];
  for (const it of rvItems) {
    if (universeIds.has(it.seriesId)) rvById.set(it.seriesId, it);
    else rvUnmatched.push(it.seriesId);
  }
  if (rvUnmatched.length > 0) {
    notes.push(
      `RV 랭킹의 ${rvUnmatched.join('·')} 는 유니버스에 같은 id 가 없어 Score 가 안 붙었어요.`,
    );
  }
  if (rv && rv.credit.exclusions.length > 0) {
    notes.push(
      `RV 후보에서 서버가 뺀 ${rv.credit.exclusions.length}건은 Score 가 없어요 — ` +
        `사유는 「${rv.credit.exclusions[0].reason}」 같은 것들이에요.`,
    );
  }

  /* ── 1) 계열 ─────────────────────────────────────────────────────────── */
  const issuerLabelOf = new Map<string, string>();
  for (const r of universe.rows) {
    const tenor = tenorOfId(r.id) ?? FUT_TENOR[r.id] ?? null;
    const m = mrById.get(r.id);
    const props: Prop[] = [
      { k: '분류', v: r.kind },
      { k: '단위', v: r.unit },
      { k: '현재', v: r.now == null ? '—' : String(r.now) },
      { k: '1일', v: r.deltas?.d1 == null ? '—' : `${r.deltas.d1 > 0 ? '+' : ''}${r.deltas.d1}` },
      { k: 'MTD', v: r.deltas?.mtd == null ? '—' : `${r.deltas.mtd > 0 ? '+' : ''}${r.deltas.mtd}` },
      { k: 'YTD', v: r.deltas?.ytd == null ? '—' : `${r.deltas.ytd > 0 ? '+' : ''}${r.deltas.ytd}` },
      { k: '1년 위치', v: r.range1y?.pct == null ? '—' : `${r.range1y.pct}%` },
      { k: '만기', v: tenor ?? '해당 없음' },
    ];
    if (m) {
      /* 밴드는 **측정이지 신호가 아니다** — Strategy 섹션의 Mean Reversion 이
         지키는 그 문법(명령형·추천 금지)을 여기서도 지킨다. */
      props.push(
        { k: '밴드 z', v: m.z == null ? '—' : m.z.toFixed(2) },
        { k: '밴드 위치', v: m.pctB == null ? '—' : `${m.pctB.toFixed(1)}%B` },
        /* `days` 는 **`inside` 면 null** 이다(`mr/api.ts::MrState` 가 그렇게 적어
           두었다). 안 걸렀더니 화면에 「밴드 안 null일」이 섰다(실측 2026-08-26) —
           그리고 그 문자열이 패싯의 버킷 값이 되어, 같은 상태가 「밴드 안」과
           「밴드 안 null일」 두 막대로 갈라졌다. 결함 하나가 두 자리에서 보인 것이다. */
        { k: '밴드 상태', v: m.state.days == null ? bandLabel(m) : `${bandLabel(m)} ${m.state.days}일` },
        { k: '정의', v: m.defn },
      );
    }
    const rvIt = rvById.get(r.id);
    if (rvIt) {
      /* 밴드와 같은 문법 — **측정이지 신호가 아니다.** 「사라」도 「비싸다」도
         적지 않는다. 스프레드에 앵커 이름을 **행마다** 붙이는 이유는 이 표에
         앵커가 둘 섞이기 때문이다(실측: 국고 18 · 산금채 24). 열 머리 하나로는
         못 적는다는 것을 RV 화면이 이미 배웠다(`rv/api.ts::base` 주석). */
      props.push(
        { k: 'RV Score', v: rvIt.score == null ? '—' : rvIt.score.toFixed(1) },
        { k: 'RV 순위', v: rvIt.rank == null ? '—' : `${rvIt.rank} / ${rvItems.length}` },
        {
          k: 'RV 사분위',
          v: rvIt.rank == null ? '—' : rvQuartile(rvIt.rank, rvItems.length),
        },
        {
          k: '순위 변화',
          v:
            rvIt.rankDelta == null
              ? '—'
              : `${rvIt.rankDelta > 0 ? '+' : ''}${rvIt.rankDelta}`,
        },
        { k: '스프레드', v: `${rvIt.nowBp.toFixed(1)}bp · ${rvIt.baseLabel} 대비` },
        {
          k: '이론 대비',
          v: rvIt.cheapBp == null ? '—' : `${rvIt.cheapBp > 0 ? '+' : ''}${rvIt.cheapBp.toFixed(1)}bp`,
        },
        { k: '버퍼', v: `${rvIt.bufferBp.toFixed(1)}bp` },
        { k: '월 총수익', v: `${rvIt.trMonthBp.toFixed(1)}bp` },
        { k: '숏 가능', v: rvIt.shortable ? (rvIt.shortVia ?? '예') : '아니오' },
      );
    }
    push({
      id: r.id,
      type: 'instrument',
      title: r.label,
      subtitle: tenor ? `${r.kind} · ${tenor}` : r.kind,
      props,
      source: rvIt
        ? `/api/universe · asof ${universe.asof} · RV /api/rv/analysis · asof ${rv?.asof.creditMatrix ?? '—'}`
        : `/api/universe · asof ${universe.asof}`,
      num: {
        now: r.now ?? null,
        d1: r.deltas?.d1 ?? null,
        pct1y: r.range1y?.pct ?? null,
        z: m?.z ?? null,
        score: rvIt?.score ?? null,
        rank: rvIt?.rank ?? null,
        cheap: rvIt?.cheapBp ?? null,
      },
    });

    if (tenor) {
      const tid = `TENOR-${tenor}`;
      push({
        id: tid,
        type: 'tenor',
        title: tenor,
        subtitle: '만기 축',
        props: [{ k: '년', v: tenorYears(tenor).toFixed(2) }],
        source: '유니버스 id 에서 유도',
        num: { years: tenorYears(tenor) },
      });
      link(r.id, tid, 'has-tenor');
    }

    const cred = /^CRD-([A-Z0-9]+)-/.exec(r.id);
    if (cred) {
      /* 발행체 라벨은 **행 라벨의 앞부분**이다("통안 6M" → "통안"). 코드(MSB)와
         라벨(통안)이 따로 노는 것을 이 한 줄이 잇고, 다른 데서는 라벨만 쓴다. */
      const label = r.label.replace(/\s+\S+$/, '');
      issuerLabelOf.set(cred[1], label);
      const iid = `ISSUER-${label}`;
      push({
        id: iid,
        type: 'issuer',
        title: label,
        subtitle: '크레딧 커브',
        props: [{ k: '코드', v: cred[1] }],
        source: `/api/universe · asof ${universe.asof}`,
      });
      link(r.id, iid, 'issued-by');
    }
  }

  /* ── 2) 계열끼리의 구성 ───────────────────────────────────────────────── */
  let derived = 0;
  for (const r of universe.rows) {
    const base = derivesFrom(r.id);
    if (base && universeIds.has(base)) {
      link(r.id, base, 'derives-from');
      derived += 1;
    }
  }
  notes.push(`구성 링크 ${derived}개는 id 가 담은 정의에서 유도했어요 — 지어낸 관계는 없어요.`);

  /* ── 2b) 스프레드 기준 — **RV 가 말해 준 관계** ─────────────────────────────
     크레딧 항목마다 `base` 가 있다: 앞단(통안·특은·공사)은 국고, 확산(은행·회사
     ·카드·캐피탈)은 특은채. 이건 유도가 아니라 **서버가 든 사실**이고, 그래서
     이을 근거가 있다 — 「이 스프레드가 무엇 대비인가」는 그래프에서 선 하나로
     읽히는 것이 표의 열 하나보다 낫다.

     자기 자신은 안 잇는다(산금채의 앵커가 국고이므로 자기 참조는 안 생기지만,
     앵커 규약이 바뀌는 날 조용히 자기 고리가 생기는 것을 막는다). */
  let priced = 0;
  for (const [sid, it] of rvById) {
    const anchor = it.base === 'KTB' ? `GOVT-${it.tenor}` : `CRD-${it.base}-${it.tenor}`;
    if (anchor === sid || !universeIds.has(anchor)) continue;
    link(sid, anchor, 'priced-against');
    priced += 1;
  }
  if (priced > 0) {
    notes.push(`스프레드 기준 링크 ${priced}개는 RV 응답의 앵커(base)를 그대로 읽은 것이에요.`);
  }

  /* ── 3) 섹터 · 일정 (발행 캘린더) ─────────────────────────────────────── */
  if (calendar) {
    for (const s of calendar.sectors) {
      const sid = `SECTOR-${s.k}`;
      push({
        id: sid,
        type: 'sector',
        title: s.k,
        subtitle: `${s.v.toFixed(2)}조 · ${s.n}건`,
        props: [
          { k: '기간 합계', v: `${s.v.toFixed(2)}조원` },
          { k: '건수', v: `${s.n}건` },
          { k: '여전·금융', v: s.fin ? '예' : '아니오' },
        ],
        source: '/api/issuance/calendar · DART 전자공시',
        sourceUrl: 'https://dart.fss.or.kr',
        num: { won: s.v, n: s.n },
      });
      /* 섹터 ↔ 커브는 **이름이 정확히 같을 때만**. 파일 머리의 그 제약. */
      const curve = `ISSUER-${s.k}`;
      if (ensure.has(curve)) link(sid, curve, 'sector-curve');
    }
    const noCurve = calendar.sectors.filter((s) => !ensure.has(`ISSUER-${s.k}`)).map((s) => s.k);
    if (noCurve.length > 0) {
      notes.push(`${noCurve.join('·')} 섹터는 유니버스에 같은 이름의 커브가 없어 안 이었어요.`);
    }

    for (const ym of calendar.order) {
      for (const d of calendar.months[ym]?.days ?? []) {
        for (const e of d.ev ?? []) {
          const eid = `EV-${d.iso}-${e.lane}-${e.label}`;
          push({
            id: eid,
            type: 'event',
            title: e.label,
            subtitle: `${d.iso} · ${e.lane.toUpperCase()}`,
            props: [
              { k: '일자', v: d.iso },
              { k: '레인', v: e.lane },
              /* `dir` 은 **재료가 미는 쪽**이지 시장의 반응이 아니다 — 백엔드가
                 그렇게 적어 두었고(`BIAS_IS_THE_MATERIAL`), 화면도 그 문장을 진다. */
              { k: '재료 방향', v: e.dir ?? '잰 것 없음' },
            ],
            source: laneSource(e.lane),
            sourceUrl: laneUrl(e.lane),
            t: isoToMs(d.iso),
          });
        }
        for (const [sec, won] of Object.entries(d.isec ?? {})) {
          const sid = `SECTOR-${sec}`;
          if (ensure.has(sid)) {
            /* 그날 그 섹터에 얼마가 얹혔는지는 **일정 객체가 아니라 링크의 사실**
               이다. 날짜별 섹터 노드를 또 만들면 43×10 개의 유령이 생긴다. */
            const eid = `ISSDAY-${d.iso}-${sec}`;
            push({
              id: eid,
              type: 'issue',
              title: `${sec} 발행`,
              subtitle: `${d.iso} · ${won.toFixed(2)}조 · ${(d.isn ?? {})[sec] ?? 0}건`,
              props: [
                { k: '일자', v: d.iso },
                { k: '섹터', v: sec },
                { k: '발행액', v: `${won.toFixed(2)}조원` },
                { k: '건수', v: `${(d.isn ?? {})[sec] ?? 0}건` },
              ],
              source: '/api/issuance/calendar · DART 전자공시',
              sourceUrl: 'https://dart.fss.or.kr',
              t: isoToMs(d.iso),
              num: { won, n: (d.isn ?? {})[sec] ?? 0 },
            });
            link(eid, sid, 'in-sector');
          }
        }
      }
    }
    for (const c of calendar.caveats) notes.push(c);
  }

  /* ── 4) 그날의 원문 — 개별 발행 건과 국고채 입찰 ───────────────────────── */
  for (const day of days) {
    for (const [i, it] of (day.issuing ?? []).entries()) {
      const iid = `ISS-${day.date}-${i}`;
      const props: Prop[] = [
        { k: '일자', v: day.date },
        { k: '발행체', v: it.issuer },
        { k: '섹터', v: it.sector },
        { k: '회차', v: it.round ?? '—' },
        { k: '금액', v: `${it.eok.toLocaleString('ko-KR')}억원` },
        { k: '표면금리', v: it.coupon == null ? '—' : `${it.coupon}%` },
        { k: '만기일', v: it.maturity ?? '—' },
        { k: '등급', v: it.rating ?? '—' },
        { k: '단계', v: it.stage ?? '—' },
      ];
      if (it.mp) {
        props.push(
          { k: '민평 잣대', v: it.mp.curve ?? '—' },
          { k: '민평 금리', v: it.mp.rate == null ? '—' : `${it.mp.rate}%` },
          { k: '민평 대비', v: it.mp.bp == null ? '—' : `${it.mp.bp > 0 ? '+' : ''}${it.mp.bp}bp ${it.mp.side ?? ''}`.trim() },
        );
      }
      push({
        id: iid,
        type: 'issue',
        title: `${it.issuer} ${it.round}`,
        subtitle: `${day.date} · ${it.eok.toLocaleString('ko-KR')}억 · ${it.rating ?? '등급 없음'}`,
        props,
        source: day.src?.iss ? `${day.src.iss.who} — ${day.src.iss.what}` : 'DART 전자공시',
        sourceUrl: day.src?.iss?.url ?? 'https://dart.fss.or.kr',
        t: isoToMs(day.date),
        num: { eok: it.eok, bp: it.mp?.bp ?? null },
      });
      const sid = `SECTOR-${it.sector}`;
      if (ensure.has(sid)) link(iid, sid, 'in-sector');
      const issuerId = `ISSUER-CORP-${it.issuer}`;
      push({
        id: issuerId,
        type: 'issuer',
        title: it.issuer,
        subtitle: `${it.sector} · ${it.rating ?? '등급 없음'}`,
        props: [
          { k: '섹터', v: it.sector },
          { k: '등급', v: it.rating ?? '—' },
        ],
        source: day.src?.iss ? `${day.src.iss.who} — ${day.src.iss.what}` : 'DART 전자공시',
        sourceUrl: day.src?.iss?.url ?? 'https://dart.fss.or.kr',
      });
      link(iid, issuerId, 'issued-by');
    }

    for (const [i, a] of (day.auctions ?? []).entries()) {
      const aid = `AUC-${day.date}-${i}`;
      const st = a.strength;
      const props: Prop[] = [
        { k: '일자', v: day.date },
        { k: '연물', v: a.name },
        { k: '종목', v: a.code ?? '—' },
        { k: '발행예정', v: a.offered == null ? '—' : `${a.offered.toLocaleString('ko-KR')}억원` },
        { k: '응찰', v: a.bid == null ? '—' : `${a.bid.toLocaleString('ko-KR')}억원` },
        { k: '응찰배수', v: a.ratio == null ? '—' : `${a.ratio}%` },
        { k: '낙찰금리', v: a.wavgRate == null ? '—' : `${a.wavgRate}%` },
      ];
      if (st) {
        props.push(
          { k: '수요', v: `${st.grade}${st.tone ? ` · ${st.tone}` : ''}` },
          { k: '같은 연물 백분위', v: st.pct == null ? '—' : `${st.pct}%` },
          { k: '직전 대비', v: st.wavgDelta == null ? '—' : `${st.wavgDelta > 0 ? '+' : ''}${st.wavgDelta}bp` },
        );
      }
      push({
        id: aid,
        type: 'auction',
        title: `국고 ${a.name}`,
        subtitle: `${day.date} · 응찰 ${a.ratio ?? '—'}% · ${st?.grade ?? ''}`.trim(),
        props,
        source: day.src?.ktb ? `${day.src.ktb.who} — ${day.src.ktb.what}` : '기획재정부 국채시장',
        sourceUrl: day.src?.ktb?.url ?? null,
        t: isoToMs(day.date),
        num: { ratio: a.ratio ?? null, wavg: a.wavgRate ?? null, pct: st?.pct ?? null },
      });
      /* 입찰 연물 → 만기 노드. 원천은 **`a.name`**("20년물")이다 — 응답에는
         `strength.tenor` 도 있지만 이 리포의 타입 선언(`lab/issuance/api.ts`)에
         그 필드가 없어서, 선언에 있는 것만 읽는다. 선언에 없는 필드를 읽으면
         백엔드가 그것을 지우는 날 타입 검사가 아무 말도 안 한다.
         유니버스에 그 만기가 있을 때만 잇는다 — 유니버스는 10Y 까지라
         20·30·50년물은 안 이어지고, 그건 사실이다. */
      const years = Number(String(a.name).replace(/[^0-9.]/g, ''));
      if (Number.isFinite(years)) {
        const tid = `TENOR-${years}Y`;
        if (ensure.has(tid)) link(aid, tid, 'auctioned-tenor');
      }
    }
  }

  if (days.length > 0) {
    notes.push(`원문(발행 건·입찰 결과)은 최근 ${days.length}영업일치만 읽었어요 — 그 앞은 캘린더의 집계만 있어요.`);
  }

  const byId = new Map(objects.map((o) => [o.id, o]));
  /* 링크의 양끝이 다 있는 것만 남긴다. 한쪽이 없는 링크는 그래프에서 허공으로
     뻗는 선이 되고, 그 선은 없는 관계를 주장한다. */
  const kept = links.filter((l) => byId.has(l.a) && byId.has(l.b));
  const adj = new Map<string, TermLink[]>();
  for (const l of kept) {
    if (!adj.has(l.a)) adj.set(l.a, []);
    if (!adj.has(l.b)) adj.set(l.b, []);
    adj.get(l.a)!.push(l);
    adj.get(l.b)!.push(l);
  }

  return {
    objects,
    links: kept,
    byId,
    adj,
    notes,
    asof: {
      universe: universe.asof ?? null,
      mrBss: mr?.asof.bss ?? null,
      mrFut: mr?.asof.fut ?? null,
      rv: rv?.asof.creditMatrix ?? null,
      today: calendar?.today ?? null,
    },
  };
}

/** 밴드 상태의 이름. **다섯 가지 전부**를 적는다.
 *
 * 처음엔 셋만 다루고 나머지를 「밴드 안」으로 뭉갰는데, `reentry-high`/
 * `reentry-low` 는 «밖에 있다가 되돌아왔다» 라서 «계속 안에 있었다» 와 다른
 * 사실이다. 이 리포는 그 구분을 값비싸게 배웠다 — `Desktopollinger-mr` 레인이
 * 「밴드 재진입」 문법을 사전등록 검증으로 NO-GO 판정한 것이 그 구분 위에서였다.
 * 두 상태를 한 이름으로 부르면 그 판정을 화면이 지운다.
 *
 * 이름만 적고 **판단은 안 한다** — Strategy 섹션의 Mean Reversion 이 지키는
 * «측정이지 신호가 아니다» 를 여기서도 지킨다. */
function bandLabel(m: MrRow): string {
  /* 낱말은 계획면의 `mr/planText.stateText` 와 **같은 어휘**다 [OWNER 2026-09-21 —
     데스크 표준]: 밖 → 이탈 · 재진입 → 복귀 · 밴드 안 → 밴드 내. 터미널과 화면이
     같은 사건을 두 낱말로 부르면 둘을 나란히 못 읽는다. 위 주석이 지키라는
     **구분**(복귀 ≠ 계속 안)은 그대로다 — 바뀐 것은 이름뿐이다. */
  if (m.state.kind === 'above') return '상단 이탈';
  if (m.state.kind === 'below') return '하단 이탈';
  if (m.state.kind === 'reentry-high') return '밴드 복귀 (상단)';
  if (m.state.kind === 'reentry-low') return '밴드 복귀 (하단)';
  return '밴드 내';
}

/** 레인의 출처. 백엔드 `src` 가 날짜별로 같은 값을 주므로 여기 한 벌만 둔다. */
function laneSource(lane: string): string {
  if (lane === 'ktb') return '기획재정부 국채시장 — 국고채 입찰결과 공고';
  if (lane === 'omo') return '한국은행 공개시장운영 공지';
  if (lane === 'mpc') return '한국은행 통화정책방향 의결문';
  if (lane === 'res') return '한국은행 지준 적립기간 공표';
  return '/api/issuance/calendar';
}

function laneUrl(lane: string): string | null {
  if (lane === 'ktb') return 'https://ktb.moef.go.kr/mnbyIsuCldr.do';
  if (lane === 'omo') return 'https://www.bok.or.kr/portal/bbs/P0001773/list.do?menuNo=200037';
  if (lane === 'mpc') return 'https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do?mtgSe=A';
  return null;
}

export function otherEnd(l: TermLink, self: string): string {
  return l.a === self ? l.b : l.a;
}

/* ── 패싯 ────────────────────────────────────────────────────────────────── */

export type FacetKey = 'type' | 'kind' | 'tenor' | 'issuer' | 'band' | 'rv';

export const FACET_LABEL: Record<FacetKey, string> = {
  type: '객체 종류',
  kind: '계열 분류',
  tenor: '만기',
  issuer: '발행체 · 섹터',
  band: '밴드 상태',
  rv: 'RV 사분위',
};

/** 한 객체가 그 패싯에서 갖는 값. `null` 이면 그 패싯의 대상이 아니다 —
 *  «해당 없음» 을 버킷으로 만들지 않는다. */
export function facetValue(o: TermObject, f: FacetKey): string | null {
  const p = (k: string) => o.props.find((x) => x.k === k)?.v ?? null;
  if (f === 'type') return OBJ_LABEL[o.type];
  if (f === 'kind') return o.type === 'instrument' ? p('분류') : null;
  if (f === 'tenor') {
    if (o.type === 'tenor') return o.title;
    const t = p('만기');
    return t && t !== '해당 없음' ? t : null;
  }
  if (f === 'issuer') {
    if (o.type === 'issuer' || o.type === 'sector') return o.title;
    return p('섹터') ?? null;
  }
  if (f === 'band') {
    const b = p('밴드 상태');
    return b ? b.replace(/\s+\d+일$/, '') : null;
  }
  if (f === 'rv') return p('RV 사분위');
  return null;
}

export type Bucket = { value: string; n: number };

/** 한 패싯의 막대들. 순서가 있는 패싯(만기)은 **값 순서**를 지킨다 — 거기서
 *  크기순 정렬은 축을 뒤섞는 것이고, 그러면 분포가 아니라 순위표가 된다. */
export function bucketsOf(objects: TermObject[], f: FacetKey): Bucket[] {
  const m = new Map<string, number>();
  for (const o of objects) {
    const v = facetValue(o, f);
    if (v == null) continue;
    m.set(v, (m.get(v) ?? 0) + 1);
  }
  const out = [...m.entries()].map(([value, n]) => ({ value, n }));
  if (f === 'tenor') return out.sort((x, y) => tenorYears(x.value) - tenorYears(y.value));
  /* RV 사분위도 **값 순서**다 — 「상위 25%」가 개수가 적다고 아래로 내려가면
     그 막대는 분위가 아니라 순위표가 된다(만기 패싯과 같은 이유). */
  if (f === 'rv') {
    const order = (v: string) => {
      const i = (RV_QUARTILES as readonly string[]).indexOf(v);
      return i < 0 ? RV_QUARTILES.length : i;
    };
    return out.sort((x, y) => order(x.value) - order(y.value));
  }
  return out.sort((x, y) => y.n - x.n);
}

export type Selection = Partial<Record<FacetKey, Set<string>>>;

/** 같은 패싯 안은 OR, 패싯끼리는 AND — 패싯 필터의 표준 의미론. 반대로 하면
 *  막대를 두 개 누르는 순간 결과가 0 이 되어 «필터가 고장났다» 로 읽힌다. */
export function applyFacets(objects: TermObject[], sel: Selection): TermObject[] {
  const keys = (Object.keys(sel) as FacetKey[]).filter((k) => (sel[k]?.size ?? 0) > 0);
  if (keys.length === 0) return objects;
  return objects.filter((o) =>
    keys.every((k) => {
      const v = facetValue(o, k);
      return v != null && sel[k]!.has(v);
    }),
  );
}
