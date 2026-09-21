'use client';

/* 시뮬레이션 결과 — "이 경로면 얼마 벌었을까".
 *
 * 실행을 누르면 뜨는 **떠 있는 창**이다(v1 실물 그대로). 떠 있어야 하는 이유는
 * 뒤의 설정을 다시 만질 수 있어야 하기 때문이다 — 결과를 읽는 일의 절반은
 * "그럼 30bp 말고 50bp면?" 이고, 그건 설정으로 돌아가는 일이다.
 *
 * ── 읽는 순서가 곧 배치다 ──────────────────────────────────────────────────
 *  1. **케이스 넷의 총손익** — 한 줄. 이 화면의 첫 질문은 "얼마" 가 아니라
 *     "네 경로에서 각각 얼마" 다.
 *  2. **무엇을 물었나** — 기간·목표·총손익 칩. 결과 창은 자기가 답한 질문을
 *     다시 적는다(창이 떠 있는 동안 설정이 바뀌었을 수 있다).
 *  3. **케이스 비교** — 성분 × 케이스 표.
 *  4. **성분 누적 경로** — 평가·캐리·롤다운이 날마다 어떻게 쌓이는지.
 *  5. **워터폴** — 그 셋이 총손익으로 합쳐지는 그림.
 *  6. **일별 대사** — 트레이딩 시스템과 줄 단위로 맞춰 보는 표.
 */

import { useCallback, useMemo, useState } from 'react';

import { Button } from '@coinbase/cds-web/buttons';
import { Chip } from '@coinbase/cds-web/chips';
import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@coinbase/cds-web/tables';
import { TextLabel1, TextLabel2, TextLegal } from '@coinbase/cds-web/typography';

import { fmtKrw, fmtKrwFromMan, manUnits } from '@/lib/krw';
/* 방향 **글자**는 클래스(`sr-up`/`sr-down` — Backtest·Main 과 같은 기제),
   방향 **배경**은 토큰 var(색을 섞어야 하므로 클래스로는 안 된다). 한 뜻에 두
   기제를 쓰던 것을 이 선으로 가른다 [감사 2026-08-25]. */
import { directionClass } from '@/table/tint';
import { directionVar } from '@/theme/tint';
import { FloatingWindow } from '@/ui/window/FloatingWindow';
import { ReconStack, type ReconStackDay } from '@/ui/window/ReconStack';
import { NumericChart, type NumericLine } from '@/chart/NumericChart';
import { ChartReadoutStrip, slotChars, type StripSlot } from '@/ui/ChartReadoutStrip';

import type { CaseRuns } from './SimulationPage';
import {
  activeCase,
  SIM_CASES,
  type CaseId,
  type Scenario,
  type SimBondRecon,
  type SimBondReconRow,
  type SimReconRow,
  type SimResponse,
} from './scenario';

/** 성분. 순서가 곧 워터폴의 순서이고 표의 행 순서다.
 *
 * 채권 셋은 **북에 채권이 있을 때만** 선다 [OWNER, 2026-08-14 — 시뮬 포지션에
 * 현금채권·자산스왑]. 라벨은 v1 `sim/lib/components.ts` 의 그 이름들이다 —
 * 상수 0 을 줄로 그리면 "조달이 0이었다" 가 아니라 "조달이라는 게 있고 마침
 * 0이다" 로 읽히는데, 둘은 다른 주장이다(그쪽 주석 그대로). */
const SWAP_PARTS = [
  { key: 'val', label: '스왑평가' },
  { key: 'carry', label: '스왑캐리' },
  { key: 'roll', label: '스왑롤다운' },
] as const;
const BOND_PARTS = [
  { key: 'bondMtm', label: '채권평가' },
  { key: 'bondCarry', label: '채권캐리' },
  /* [OWNER, 2026-08-25 — 엔진 단위 분리] 종전 시뮬 채권에는 이 항이 아예
     없었다(unchanged-yields). 동결 민평 커브 롤이 합류하며 총액도 이 항만큼
     옳아졌다 — bond_roll.py. */
  { key: 'bondRoll', label: '채권롤다운' },
  { key: 'fund', label: '조달비용' },
] as const;
/* [OWNER, 2026-08-25 — 선물·퓨처스왑 합류] 선물은 성분이 **하나**다: KRX 폐형
   재값매김의 평가. 캐리·조달·롤다운은 존재하지 않는 성분이라 항 자체가 없다
   (합성채는 늙지 않는다 — backend futures_pricing). */
const FUT_PARTS = [{ key: 'futMtm', label: '선물평가' }] as const;

/** 커서 카드가 그리는 줄들 — 워터폴·표와 **같은 순서, 같은 이름**이다.
 * 세 곳이 각자 목록을 들면 하나만 고쳐지는 날이 온다. */
const PATH_ROWS = [...SWAP_PARTS, ...BOND_PARTS, ...FUT_PARTS] as readonly {
  key: 'val' | 'carry' | 'roll' | 'bondMtm' | 'bondCarry' | 'bondRoll' | 'fund' | 'futMtm';
  label: string;
}[];
/** 성분마다의 잉크 — **한 벌**이다.
 *
 *  선(`pathLines`)과 리드아웃 줄의 견본이 같은 색이어야 하는데, 색을 두 곳에
 *  적으면 한쪽만 바뀌는 날이 온다(캐논 규칙 8 — 같은 것은 한 번만 만든다).
 *  캔버스 쪽은 `palette.resolve` 로 풀고 DOM 쪽은 그대로 쓴다.
 *
 *  ⚠ **모듈 자리여야 한다** — 컴포넌트 안에 두면 매 렌더 새 객체가 되어
 *  `useMemo` 의 의존이 매번 갈린다(eslint 가 그걸 잡았다, 2026-09-21). */
const PATH_INK: Record<string, string> = {
  val: 'var(--sr-up)',
  carry: 'var(--sr-down)',
  roll: 'var(--color-fgMuted)',
  bondMtm: 'var(--sr-ref-cd)',
  bondCarry: 'var(--sr-ref-policy)',
  bondRoll: 'var(--sr-ref-roll)',
  fund: 'var(--color-fg)',
  futMtm: 'var(--sr-ref-fut)',
};

/** 북에 채권이 없으면 서지 않는 셋. */
const BOND_SERIES = new Set<string>(BOND_PARTS.map((r) => r.key));
/** 북에 선물이 없으면 서지 않는 것. */
const FUT_SERIES = new Set<string>(FUT_PARTS.map((r) => r.key));

/** 케이스 선의 색.
 *
 * ⚠ 첫 판은 `--color-chart1`…`4` 를 썼다. **그런 토큰은 없다** — CDS 가 심는
 * `--color-*` 43개를 실측으로 세어 보니 chart 계열이 하나도 없었고, 무효값이라
 * 브라우저가 상속색으로 떨어뜨려 **네 선이 전부 같은 회색**이 됐다. 아무것도 안
 * 깨져 보이는 그 결함이다(이 리포가 폰트·면 토큰에서 이미 세 번 밟았다).
 *
 * 지금 쓰는 것은 실재하는 토큰뿐이고, **케이스의 뜻과 색을 맞춘다**:
 * Bull 은 금리 하락이라 파랑, Bear 는 상승이라 빨강 — 원화 관례와 싸우지 않는
 * 유일한 배치다. Base 는 잉크(지금 편집 중인 것), Crisis 는 더 센 상승이지만
 * Bear 와 구별돼야 해서 보라다.
 *
 * 한계를 적어 둔다: 사용자가 Bull 의 목표를 +100 으로 고치면 색이 이름과 어긋난다.
 * 색은 **씨앗의 뜻**을 말하고, 실제 방향은 칩 옆의 숫자가 말한다. 그리고 회색조에서
 * 넷을 구별할 수 없으므로 칩이 항상 이름을 같이 싣는다(DESIGN §5 의 단서). */
const CASE_COLOR: Record<CaseId, string> = {
  base: 'var(--color-fg)',
  bull: 'var(--sr-down)',
  bear: 'var(--sr-up)',
  crisis: 'var(--color-accentBoldPurple)',
};

/** 한 케이스의 3분해 — **표시 정밀도에서 총손익과 맞도록**. 셋을 각자 반올림하면
 * 1만원이 어긋난다(백테스트에서 실측으로 걸린 그 결함). */
function partsOf(run: SimResponse) {
  const d = run.totalReturnDecomposition;
  /* splitKrw 의 수법 그대로, 성분이 일곱으로 늘었을 뿐이다: 합계와 여섯 성분이
     각각 한 번씩 반올림하고 **스왑캐리가 잔차**를 진다. 북에 채권이 없으면
     채권 넷은 정확히 0 이라 예전의 3분해와 같은 숫자다.

     **제외된 스왑은 0 이 아니라 null 이다** [블랭크 정책 · 실측 2026-08-25:
     «당일 IRS 호가 없음» 런에서 스왑 성분 null 을 0 으로 강등하니 반올림
     잔차 +1만원이 «스왑캐리» 라벨을 뒤집어썼다 — 값이 안 매겨진 다리가
     숫자를 가진 것처럼 보였다]. 스왑이 제외되면 스왑 셋은 null(화면 —)이고
     잔차는 채권캐리가 진다. */
  const uPnl = manUnits(d.total);
  const hasSwap = d.swapMtm !== null && d.swapMtm !== undefined;
  const bondMtm = manUnits(d.bondMtm);
  const bondRoll = manUnits(d.bondRolldown ?? 0);
  const fund = manUnits(d.fundingCost);
  /* 선물평가 [2026-08-25] — 선물의 유일한 성분. 구 캐시 응답에는 키가 없다.
     존재 판정은 값이 아니라 **선물 대사표의 존재**다(= 북에 선물 포지션이
     있었다는 서버의 사실): FUT 매수와 FSW 의 선물 매도가 정확히 상쇄되면
     futMtm 이 0.0 이 되는데(같은 테너 100억 대 100억 — 실측 2026-08-25 첫
     화면), 그때 행을 숨기면 실재하는 그로스 포지션이 화면에서 사라진다. */
  const futMtm = manUnits(d.futMtm ?? 0);
  const hasFut = run.futuresDailyReconciliation != null || futMtm !== 0;
  if (!hasSwap) {
    const bondCarry = uPnl - bondMtm - bondRoll - fund - futMtm;
    return {
      uPnl, val: null, carry: null, roll: null,
      bondMtm, bondCarry, bondRoll, fund, futMtm,
      hasBond: bondMtm !== 0 || bondCarry !== 0 || bondRoll !== 0 || fund !== 0,
      hasSwap, hasFut,
    };
  }
  const val = manUnits(d.swapMtm);
  const roll = manUnits(d.swapRolldown ?? 0);
  const bondCarry = manUnits(d.bondCarry);
  const carry = uPnl - val - roll - bondMtm - bondCarry - bondRoll - fund - futMtm;
  const hasBond = bondMtm !== 0 || bondCarry !== 0 || bondRoll !== 0 || fund !== 0;
  return { uPnl, val, carry, roll, bondMtm, bondCarry, bondRoll, fund, futMtm, hasBond, hasSwap, hasFut };
}

/** 엔진의 일별 대사 → 대사 스택. **시간순이 기본**(D+0 이 위) — 미래 경로에는
 * "최신" 이랄 게 없다. 여기서 계산하는 것은 없다.
 *
 * 내보내는 이유는 백테스트 쪽 `backtest/recon.ts` 와 같다 [2026-08-21]: 이
 * 사상이 창 안에만 있으면 가드가 닿지 못하고, 저쪽에서 정확히 그 자리가 한 번
 * 조용히 틀렸다.
 *
 * [OWNER, 2026-08-25 — 엔진 단위 분리] 스왑 표는 v1 계약으로 돌아갔다 — 조달
 * 필드를 넘기지 않는다(스왑에는 그 질문이 없다). 채권의 대사는 `bondDays` 가
 * 자기 표로 넘긴다. */
export function simDays(rows: SimReconRow[]): ReconStackDay[] {
  return rows.map((r) => ({
    date: r.date,
    title: r.carryover
      ? `${r.date} · D+${r.day} · 다음 영업일로 들고 가는 이월 리스크`
      : `${r.date} · D+${r.day}`,
    krd: r.pvbp,
    dbp: r.dailyDbp,
    est: r.pnl,
    estTotal: r.totalEstPnl,
    valuation: r.valuationPnl,
    residual: r.residual,
    carry: r.carryPnl ?? null,
    rolldown: r.rolldownPnl ?? null,
    actual: r.totalActual,
  }));
}

/** 채권 일별 대사 → 대사 스택. 조달은 이 표의 것이다 — 서버가 이미 음수로
 * 주므로 여기서 부호를 다시 주지 않는다. */
export function bondDays(rows: SimBondReconRow[]): ReconStackDay[] {
  return rows.map((r) => ({
    date: r.date,
    title: r.carryover
      ? `${r.date} · D+${r.day} · 다음 영업일로 들고 가는 이월 리스크`
      : `${r.date} · D+${r.day}`,
    krd: r.pvbp,
    dbp: r.dailyDbp,
    est: r.pnl,
    estTotal: r.totalEstPnl,
    valuation: r.valuation,
    residual: r.residual,
    carry: r.carry,
    rolldown: r.rolldown,
    funding: r.funding,
    actual: r.actual,
  }));
}

/** 채권 표 각주 — 캐리 라벨의 뜻 + 롤 레인의 프로버넌스 [OWNER, 2026-08-25].
 * 캐리는 **조달 차감 전**(그로스)이다: 문헌 표준(carry = y − r_f)과 달리 이
 * 리포는 IRS 세타와 정의를 맞추려 조달을 자기 열로 뺐다 [OWNER, 2026-08-14] —
 * 화면만 보는 사람이 그 결정을 알 수 있어야 한다. 롤 레인이 꺼진 채 나온
 * 응답(커브 공급자 부재)은 그 사실도 말한다 — 조용한 0 금지. */
export function bondReconNote(recon: SimBondRecon): string {
  const carry = '캐리는 조달 차감 전 금액이에요 — 조달은 자기 열에 음수로 서요.';
  if (!recon.rollBasis.applied) {
    return `${carry} 이 실행은 민평 커브에 닿지 못해 롤다운이 0으로 나왔어요 — 백엔드 데이터 연결을 확인해 주세요.`;
  }
  if (recon.rollBasis.missing.length) {
    return `${carry} ${recon.rollBasis.missing.join('·')} 섹터는 민평 커브가 없어 롤다운이 0이에요.`;
  }
  return carry;
}

/** 조건 칩 — 이 창이 답한 질문.
 *
 * CDS `Chip` 은 `Pressable` 이라 언제나 `<button>` 이다(`as` 가 'button' 하나만
 * 받는다). 이 칩들은 누르는 것이 아니므로 `disabled` 로 탭 순서에서 뺀다 — 안 누르는
 * 것이 탭 순서에 끼면 키보드 이동이 그만큼 길어진다. */
function CondChip({ label, value }: { label: string; value: string }) {
  return (
    <Chip
      disabled
      size="xs"
      start={
        <TextLegal as="span" color="fgMuted" noWrap>
          {label}
        </TextLegal>
      }
    >
      <TextLabel2 as="span" tabularNumbers noWrap>
        {value}
      </TextLabel2>
    </Chip>
  );
}

export function ResultsWindow({
  runs,
  scenario,
  asOf,
  onClose,
}: {
  runs: CaseRuns;
  scenario: Scenario;
  asOf: string;
  onClose: () => void;
}) {
  /* 성분 경로 차트의 커서. 백테스트와 같은 문법(`LinkedCharts`). */
  const [pathIdx, setPathIdx] = useState<number>();

  const [shown, setShown] = useState<CaseId>(scenario.activeCase);
  const run = runs[shown];
  const cur = activeCase(scenario);

  const ran = SIM_CASES.filter((c) => runs[c.id]);

  /** 케이스 비교 — 성분 × 케이스. 각 칸은 그 케이스의 3분해다. */
  const grid = useMemo(
    () =>
      ran.map((c) => {
        const r = runs[c.id];
        return { id: c.id, label: c.label, parts: r ? partsOf(r) : null };
      }),
    [ran, runs],
  );

  /* 성분 누적 경로 — 평가·캐리·롤다운이 날마다 어떻게 쌓이는지. 서버가
     `decompositionDaily` 로 **누적값**을 주므로 여기서 차분하지 않는다. */
  const paths = useMemo(() => {
    const daily = run?.decompositionDaily ?? [];
    if (daily.length === 0) return null;
    return {
      /* **숫자**다. 종전에는 `D+${d.day}` 문자열이었고, 그 탓에 리드아웃 제목이
         `D+${paths.days[i]}` 로 한 번 더 붙어 **「D+D+30」** 이 찍히고 있었다
         (2026-08-26 이관 중 발견). 「D+」는 이제 **찍는 쪽**이 붙인다. */
      days: daily.map((d) => d.day),
      val: daily.map((d) => d.swapMtm ?? null),
      carry: daily.map((d) => d.swapCarry ?? null),
      roll: daily.map((d) => d.swapRolldown ?? null),
      /* 채권 넷 — 북에 채권이 있을 때만 선이 선다. 없는 북에서는 전부 0 이라
         상수 0 선 넷이 범례만 늘리므로 그린 것에만 이름을 준다(범례 규칙). */
      bondMtm: daily.map((d) => d.bondMtm ?? null),
      bondCarry: daily.map((d) => d.bondCarry ?? null),
      bondRoll: daily.map((d) => d.bondRolldown ?? null),
      fund: daily.map((d) => d.fundingCost ?? null),
      /* 선물평가 [2026-08-25] — 선이 서는 조건은 partsOf 의 hasFut 과 같은
         존재 판정(대사표 존재 = 북에 선물이 있다). 값으로 재면 FUT 매수와
         FSW 선물 매도가 상쇄된 북에서 선이 사라진다(그쪽 주석의 실측). */
      futMtm: daily.map((d) => d.futMtm ?? null),
      hasBond: daily.some(
        (d) =>
          (d.bondMtm ?? 0) !== 0 ||
          (d.bondCarry ?? 0) !== 0 ||
          (d.bondRolldown ?? 0) !== 0 ||
          (d.fundingCost ?? 0) !== 0,
      ),
      hasFut:
        run?.futuresDailyReconciliation != null ||
        daily.some((d) => (d.futMtm ?? 0) !== 0),
    };
  }, [run]);

  /** 스크러버가 스크린리더에 읽어 줄 한 줄. 카드는 눈, 이건 귀 — 둘 다 있어야 한다. */
  /** 이 경로 줄을 그릴 것인가 — 채권·선물 무리는 북에 있을 때만(범례 규칙). */
  const drawPath = useCallback(
    (key: string) => {
      if (!paths) return false;
      if (BOND_SERIES.has(key)) return paths.hasBond;
      if (FUT_SERIES.has(key)) return paths.hasFut;
      return true;
    },
    [paths],
  );

/** 성분 선들. 색은 전부 이 리포의 CSS 변수라 `palette.resolve` 가 푼다. */
  const pathLines = useMemo<NumericLine[]>(() => {
    if (!paths) return [];
    const line = (id: keyof typeof PATH_INK, values: (number | null)[]): NumericLine => ({
      id,
      values,
      color: (pal) => pal.resolve(PATH_INK[id]!),
    });
    return [
      line('val', paths.val),
      line('carry', paths.carry),
      line('roll', paths.roll),
      ...(paths.hasBond
        ? [
            line('bondMtm', paths.bondMtm),
            line('bondCarry', paths.bondCarry),
            line('bondRoll', paths.bondRoll),
            line('fund', paths.fund),
          ]
        : []),
      ...(paths.hasFut ? [line('futMtm', paths.futMtm)] : []),
    ];
  }, [paths]);

  /** 리드아웃 칸 — **그려진 성분 선 그대로**다(견본 색이 그 선의 잉크).
   *
   *  돈이라 자리가 넓다(억 단위 여섯 자리) — 경로 전체의 극단으로 재서 커서를
   *  옮겨도 칸이 안 밀린다. 좁아지면 채권·선물 성분부터 값을 내려놓고 스왑
   *  평가·캐리는 안 내려놓는다(이 창이 답하는 「어떻게 쌓였나」의 주인공). */
  const pathSlots = useMemo<StripSlot[]>(() => {
    if (!paths) return [];
    const at =
      pathIdx != null && pathIdx >= 0 && pathIdx < paths.days.length
        ? pathIdx : paths.days.length - 1;
    const ink = new Map(pathLines.map((l) => [l.id, PATH_INK[l.id] ?? 'var(--color-fg)']));
    const shown = PATH_ROWS.filter((r) => drawPath(r.key));
    const ch = slotChars(
      fmtKrw,
      ...shown.flatMap((r) => (paths[r.key] as (number | null)[]).filter(
        (x): x is number => x != null)),
    );
    return shown.map((r, n) => ({
      key: r.key,
      label: r.label,
      value: fmtKrw((paths[r.key] as (number | null)[])[at] ?? 0),
      color: ink.get(r.key),
      chars: ch,
      drop: (n < 2 ? undefined : Math.min(n - 1, 6) as 1 | 2 | 3 | 4 | 5 | 6),
    }));
  }, [paths, pathIdx, pathLines, drawPath]);

  const setPathHover = useCallback((i: number | null) => setPathIdx(i ?? undefined), []);
  const dayLabel = useCallback((d: number) => `D+${d}`, []);
  const krwTick = useCallback((v: number) => fmtKrw(v), []);

  const pathScrubLabel = useCallback(
    (i: number) => {
      if (!paths || paths.days[i] == null) return '';
      const rows = PATH_ROWS.filter((r) => drawPath(r.key))
        .map((r) => `${r.label} ${fmtKrw((paths[r.key] as (number | null)[])[i] ?? 0)}`);
      return [`D+${paths.days[i]}`, ...rows].join(', ');
    },
    [paths, drawPath],
  );

  const p = run ? partsOf(run) : null;
  const recon = run?.irsDailyReconciliation ?? [];
  const bondRecon = run?.bondDailyReconciliation ?? null;
  const futRecon = run?.futuresDailyReconciliation ?? null;
  /* 표가 몇 개 서나 — 둘 이상이면 각 표를 낮게 눕혀 셋이 한 서랍에 들어간다. */
  const reconStacks = (recon.length ? 1 : 0) + (bondRecon ? 1 : 0) + (futRecon ? 1 : 0);
  const reconCap = reconStacks > 1 ? '20vh' : '34vh';

  return (
    <FloatingWindow
      windowKey="simulation"
      title="시뮬레이션 결과"
      width={1120}
      aside={
        <TextLegal as="span" color="fgMuted" noWrap>
          이 경로면 얼마 벌었을까
        </TextLegal>
      }
      onClose={onClose}
    >
      <VStack gap={2} padding={2} width="100%">
        {/* ── 1. 케이스 넷 ─────────────────────────────────────────────────── */}
        <HStack gap={0.5} flexWrap="wrap">
          {ran.map((c) => {
            const r = runs[c.id];
            const u = r ? manUnits(r.totalReturnDecomposition.total) : 0;
            return (
              <Chip
                key={c.id}
                size="s"
                accessibilityLabel={`${c.label} 케이스`}
                start={<span className="sr-casedash" style={{ background: CASE_COLOR[c.id] }} />}
                end={
                  <TextLabel2 as="span" tabularNumbers noWrap className={directionClass(u)}>
                    {fmtKrwFromMan(u)}
                  </TextLabel2>
                }
                onClick={() => setShown(c.id)}
                active={c.id === shown}
              >
                {c.label}
              </Chip>
            );
          })}
        </HStack>

        {/* ── 2. 무엇을 물었나 ─────────────────────────────────────────────── */}
        <HStack gap={0.5} alignItems="center" flexWrap="wrap" width="100%">
          <CondChip label="기간" value={`D+${scenario.days}`} />
          <CondChip
            label={`국고 ${scenario.anchorTenor} 목표`}
            value={`${cur.shockBp >= 0 ? '+' : '−'}${Math.abs(cur.shockBp)}bp`}
          />
          {cur.events.length ? (
            <CondChip label="기준금리 이벤트" value={`${cur.events.length}건`} />
          ) : null}
          {p ? <CondChip label="Total Return" value={fmtKrwFromMan(p.uPnl)} /> : null}
          <Box style={{ marginInlineStart: 'auto' }}>
            <Button variant="secondary" size="xs" className="sr-ctlfont" onClick={onClose}>
              조건 수정
            </Button>
          </Box>
        </HStack>

        {/* ── 3. 케이스 비교 ───────────────────────────────────────────────── */}
        <VStack gap={0.5} width="100%">
          <TextLabel1 as="span">케이스 비교</TextLabel1>
          <TextLegal as="span" color="fgMuted">
            같은 포지션이 네 경로에서 각각 어디에 도착하는지예요.
          </TextLegal>
          {/* CDS `Table` — 이 표는 `<colgroup>`·sticky 오프셋이 필요 없다(대사
              스택과 다른 점). 그래서 §5.4 의 예외가 아니라 그냥 CDS 것을 쓴다. */}
          <Table tableLayout="auto">
            <TableHeader>
              <TableRow>
                <TableCell as="th" scope="col">
                  <TextLegal as="span" color="fgMuted">
                    성분
                  </TextLegal>
                </TableCell>
                {/* `.sr-num` 이 없으면 **가로 정렬이 아예 안 된다** — CDS 가 값을
                    세로 flex 로 감싸서 `justifyContent` 는 위아래를 다룬다
                    (type.css:619-632 의 실측). 이 표의 숫자들이 그래서 왼쪽에
                    붙어 있었다 [감사 2026-08-25]. */}
                {grid.map((g) => (
                  <TableCell as="th" scope="col" key={g.id} className="sr-num" justifyContent="flex-end">
                    <HStack gap={0.5} alignItems="center">
                      <span className="sr-casedash" style={{ background: CASE_COLOR[g.id] }} />
                      <TextLegal as="span" color="fgMuted" noWrap>
                        {g.label}
                      </TextLegal>
                    </HStack>
                  </TableCell>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {[
                ...SWAP_PARTS,
                ...(grid.some((g) => g.parts?.hasBond) ? BOND_PARTS : []),
                ...(grid.some((g) => g.parts?.hasFut) ? FUT_PARTS : []),
              ].map((part) => (
                <TableRow key={part.key}>
                  <TableCell>
                    <TextLegal as="span" color="fgMuted" noWrap>
                      {part.label}
                    </TextLegal>
                  </TableCell>
                  {grid.map((g) => {
                    /* null = 그 다리가 값매겨지지 않았다(스왑 제외) — 0 이 아니라
                       공란이다. 제외 사실은 표 밑 «제외됨» 줄이 말한다. */
                    const u = g.parts ? g.parts[part.key] : null;
                    return (
                      <TableCell key={g.id} className="sr-num" justifyContent="flex-end">
                        {/* 방향은 **클래스**로 — Backtest 가 같은 양(손익)에
                            `sr-up`/`sr-down` 을 쓴다. 인라인 `directionVar` 는
                            한 뜻에 두 기제였다 [감사 2026-08-25]. */}
                        <TextLabel2
                          as="span"
                          tabularNumbers
                          noWrap
                          className={u === null ? undefined : directionClass(u)}
                        >
                          {u === null ? '—' : fmtKrwFromMan(u)}
                        </TextLabel2>
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
              {/* 토탈만 굵다 — 나머지는 그 합의 구성이다. */}
              <TableRow>
                <TableCell>
                  <TextLabel1 as="span" noWrap>
                    토탈
                  </TextLabel1>
                </TableCell>
                {grid.map((g) => (
                  <TableCell key={g.id} className="sr-num" justifyContent="flex-end">
                    <TextLabel1
                      as="span"
                      tabularNumbers
                      noWrap
                      className={g.parts ? directionClass(g.parts.uPnl) : undefined}
                    >
                      {g.parts ? fmtKrwFromMan(g.parts.uPnl) : '—'}
                    </TextLabel1>
                  </TableCell>
                ))}
              </TableRow>
            </TableBody>
          </Table>
        </VStack>

        {/* ── 4. 성분 누적 경로 ────────────────────────────────────────────── */}
        {paths ? (
          <VStack gap={0.5} width="100%">
            <TextLabel1 as="span">성분 누적 경로</TextLabel1>
            <TextLegal as="span" color="fgMuted">
              설계한 금리 경로대로 갔을 때 손익이 어떻게 쌓이는지예요. 평가는 커브가 움직여
              생기는 몫, 캐리는 실제 주고받는 이자의 몫, 롤다운은 커브가 멈춰도 잔존만기가
              줄어 생기는 몫이에요.
            </TextLegal>
            {/* 커서가 짚은 날의 성분 — **그림 위 한 줄**이다 [2026-09-21 이관].
                손익이 어떻게 쌓이는지 보는 창이라, 떠 있던 카드가 하필 쌓이는
                구간을 덮고 있었다. */}
            <ChartReadoutStrip
              date={`D+${paths.days[
                pathIdx != null && pathIdx >= 0 && pathIdx < paths.days.length
                  ? pathIdx : paths.days.length - 1
              ] ?? 0}`}
              slots={pathSlots}
            />
            <Box className="sr-plot" width="100%">
              <NumericChart
                height={260}
                accessibilityLabel="성분 누적 경로"
                nodes={paths.days}
                lines={pathLines}
                label={dayLabel}
                tickFormat={krwTick}
                onHoverIndex={setPathHover}
                hoverLabel={pathScrubLabel}
              />
            </Box>
            {p ? (
              <HStack gap={1.5} flexWrap="wrap">
                {(
                  [
                    // 제외된 스왑(null)은 줄 자체가 안 선다 — 값매겨지지 않은
                    // 다리에 0원을 지어 주지 않는다(블랭크 정책).
                    ...(p.hasSwap
                      ? ([
                          ['스왑평가', p.val, 'var(--sr-up)'],
                          ['스왑캐리', p.carry, 'var(--sr-down)'],
                          ['스왑롤다운', p.roll, 'var(--color-fgMuted)'],
                        ] as const)
                      : []),
                    ...(p.hasBond
                      ? ([
                          ['채권평가', p.bondMtm, 'var(--sr-ref-cd)'],
                          ['채권캐리', p.bondCarry, 'var(--sr-ref-policy)'],
                          ['채권롤다운', p.bondRoll, 'var(--sr-ref-roll)'],
                          ['조달비용', p.fund, 'var(--color-fg)'],
                        ] as const)
                      : []),
                    ...(p.hasFut ? ([['선물평가', p.futMtm, 'var(--sr-ref-fut)']] as const) : []),
                  ] as readonly (readonly [string, number, string])[]
                ).map(([label, u, colour]) => (
                  <HStack key={label} gap={0.5} alignItems="baseline">
                    <span className="sr-casedash" style={{ background: colour }} />
                    <TextLegal as="span" color="fgMuted" noWrap>
                      {label}
                    </TextLegal>
                    <TextLabel2 as="span" tabularNumbers noWrap className={directionClass(u)}>
                      {fmtKrwFromMan(u)}
                    </TextLabel2>
                  </HStack>
                ))}
              </HStack>
            ) : null}
          </VStack>
        ) : null}

        {/* ── 5. 워터폴 ───────────────────────────────────────────────────── */}
        {p ? (
          <VStack gap={0.5} width="100%">
            <TextLabel1 as="span">Total Return</TextLabel1>
            <TextLegal as="span" color="fgMuted">
              기간이 끝났을 때의 도착점이에요. 위 커브의 마지막 값과 같은 숫자예요.
            </TextLegal>
            <Waterfall parts={p} />
            {p.hasBond ? (
              <TextLegal as="span" color="fgMuted">
                채권평가·채권캐리·채권롤다운·조달비용은 북의 채권 다리 몫이에요 — 채권캐리는
                조달 차감 전 금액이고(조달은 자기 막대), 채권롤다운은 커브가 멈춰도 잔존만기가
                줄며 생기는 몫이에요.
              </TextLegal>
            ) : null}
            {p.hasFut ? (
              <TextLegal as="span" color="fgMuted">
                선물평가는 국채선물 다리의 전부예요 — 합성채는 만기가 고정이라 캐리·롤다운
                막대가 없고, 증거금 조달은 세지 않아요.
              </TextLegal>
            ) : null}
          </VStack>
        ) : null}

        {/* ── 6. 일별 대사 — 표 둘 [OWNER, 2026-08-25 — 엔진 단위 분리] ──────
            스왑 표는 진짜 일별 KRD 재계산, 채권 표는 감쇠 pvbp 의 배분 격자다.
            다른 자로 잰 것을 한 표에 세우지 않는다 — 2026-08-21 병합판이 채권
            성분을 스왑 열에 합산하며 흐려졌던 그 구분이다. 각 표는 자기
            항등식으로 닫힌다(스왑: 평가+캐리+롤다운 · 채권: +조달). */}
        <VStack gap={0.5} width="100%">
          <TextLabel1 as="span">일별 대사</TextLabel1>
          <TextLegal as="span" color="fgMuted">
            하루가 세 줄이에요 — KRD(전일 종가 감도), Δbp(그날 변화), 손익(KRD × Δbp 추정).
            같은 블록의 KRD와 Δbp를 곱하면 손익 줄이 나와요. 추정 합계와 평가의 차가 선형화
            잔차이고, 평가·캐리·롤다운(채권은 +조달)을 더하면 그날 손익이에요. 마지막 블록은
            다음 영업일로 들고 가는 이월 리스크예요.
          </TextLegal>
          {recon.length ? (
            <VStack gap={0.5} width="100%">
              {reconStacks > 1 ? (
                <TextLegal as="span" color="fgMuted">
                  스왑 대사 — 일별 KRD 재계산
                </TextLegal>
              ) : null}
              <ReconStack
                days={simDays(recon)}
                tenors={Object.keys(recon[0].pvbp)}
                defaultOrder="asc"
                maxHeight={reconCap}
              />
            </VStack>
          ) : (
            <TextLegal as="span" color="fgMuted">
              스왑 일별 KRD가 없어요 — 스왑이 없거나 제외됐거나 par 커브가 없는 실행이에요.
            </TextLegal>
          )}
          {bondRecon ? (
            <VStack gap={0.5} width="100%">
              {reconStacks > 1 ? (
                <TextLegal as="span" color="fgMuted">
                  채권 대사 — 시나리오 충격 테너에 배분한 감쇠 pvbp
                </TextLegal>
              ) : null}
              <ReconStack
                days={bondDays(bondRecon.rows)}
                tenors={bondRecon.tenors}
                groups={bondRecon.groups}
                defaultOrder="asc"
                maxHeight={reconCap}
                note={bondReconNote(bondRecon)}
              />
            </VStack>
          ) : null}
          {futRecon ? (
            /* 세 번째 표 [OWNER, 2026-08-25 — 선물·퓨처스왑 합류]. 행 계약은
               채권 표와 같아 `bondDays` 를 그대로 쓴다 — 캐리·롤다운·조달이
               전 행 null 이라 ReconStack 이 그 열들을 안 세운다(숫자-있을-
               때만 규칙). 잔차가 싣는 것은 컨벡시티다(폐형 실측 − 선형 추정). */
            <VStack gap={0.5} width="100%">
              {reconStacks > 1 ? (
                <TextLegal as="span" color="fgMuted">
                  선물 대사 — 상장 만기 고정 지평의 KRD
                </TextLegal>
              ) : null}
              <ReconStack
                days={bondDays(futRecon.rows)}
                tenors={futRecon.tenors}
                groups={futRecon.groups}
                defaultOrder="asc"
                maxHeight={reconCap}
                note="선물은 손익이 전부 평가예요 — 합성채는 만기가 고정이라 캐리·롤다운이 없어요. 잔차는 선형 추정 대비 폐형 재값매김의 차, 곧 컨벡시티예요."
              />
            </VStack>
          ) : null}
        </VStack>

        {run?.exclusions?.length ? (
          <TextLegal as="span" color="fgMuted">
            제외됨: {run.exclusions.map((e) => e.reason ?? e.assetClass).join(' · ')}
          </TextLegal>
        ) : null}
        <TextLegal as="span" color="fgMuted">
          {asOf} 커브에서 시작했어요.
        </TextLegal>
      </VStack>
    </FloatingWindow>
  );
}

/** 워터폴 — 성분 셋이 총손익으로 합쳐지는 그림. 막대 넷(평가·캐리·롤다운·토탈)이고,
 * 앞의 셋은 **떠 있는 막대**(누적 위에서 시작)라 합쳐지는 것이 눈에 보인다.
 *
 * 크기는 만-단위 정수로 잰다 — 화면의 숫자와 막대가 같은 값에서 나와야 한다. */
function Waterfall({ parts }: { parts: ReturnType<typeof partsOf> }) {
  const steps = [
    // 제외된 스왑(hasSwap=false)은 막대가 안 선다 — null 을 0 막대로 그리면
    // "값이 0 이었다" 는 없는 주장이 된다(블랭크 정책).
    ...(parts.hasSwap
      ? [
          { label: '스왑평가', u: parts.val as number },
          { label: '스왑캐리', u: parts.carry as number },
          { label: '스왑롤다운', u: parts.roll as number },
        ]
      : []),
    ...(parts.hasBond
      ? [
          { label: '채권평가', u: parts.bondMtm },
          { label: '채권캐리', u: parts.bondCarry },
          { label: '채권롤다운', u: parts.bondRoll },
          { label: '조달비용', u: parts.fund },
        ]
      : []),
    // 선물의 유일한 막대 [2026-08-25] — 캐리·조달 막대가 없는 것이 사실이다.
    ...(parts.hasFut ? [{ label: '선물평가', u: parts.futMtm }] : []),
  ];
  // 누적 경계 — 각 막대의 아래/위 끝.
  let acc = 0;
  const bars = steps.map((s) => {
    const from = acc;
    acc += s.u;
    return { ...s, from, to: acc };
  });
  const lo = Math.min(0, ...bars.map((b) => Math.min(b.from, b.to)));
  const hi = Math.max(0, ...bars.map((b) => Math.max(b.from, b.to)));
  const span = hi - lo || 1;
  const H = 140;
  const y = (v: number) => ((hi - v) / span) * H;

  return (
    <HStack gap={2} alignItems="flex-start" flexWrap="wrap" width="100%">
      {/* 높이는 **prop 이 진다** — Box 는 `height` 를 갖고 있고, style 로 적으면
          토큰 체계 밖으로 나간다(cds-code: style prop > inline style). 값 자체는
          실측 고정값이라 그대로다(H=140 + 라벨 여백 48). */}
      <Box className="sr-waterfall" height={H + 48}>
        {bars.map((b) => (
          <div key={b.label} className="sr-wf-col">
            <div
              className="sr-wf-bar"
              style={{
                top: y(Math.max(b.from, b.to)),
                height: Math.max(1, Math.abs(y(b.to) - y(b.from))),
                background: `color-mix(in srgb, ${directionVar(b.u)} 28%, var(--sr-card))`,
              }}
            />
            <span className="sr-wf-val" style={{ top: y(Math.max(b.from, b.to)) - 16 }}>
              {fmtKrwFromMan(b.u)}
            </span>
            <span className="sr-wf-label">{b.label}</span>
          </div>
        ))}
        <div className="sr-wf-col">
          <div
            className="sr-wf-bar"
            style={{
              top: y(Math.max(0, parts.uPnl)),
              height: Math.max(1, Math.abs(y(parts.uPnl) - y(0))),
              background: `color-mix(in srgb, ${directionVar(parts.uPnl)} 28%, var(--sr-card))`,
            }}
          />
          <span className="sr-wf-val" style={{ top: y(Math.max(0, parts.uPnl)) - 16 }}>
            {fmtKrwFromMan(parts.uPnl)}
          </span>
          <span className="sr-wf-label sr-wf-total">토탈</span>
        </div>
      </Box>
      <VStack gap={0.25} minWidth={220}>
        {steps.map((s) => (
          <HStack key={s.label} gap={1} alignItems="baseline" width="100%">
            <TextLegal as="span" color="fgMuted" noWrap>
              {s.label}
            </TextLegal>
            <TextLabel2
              as="span"
              tabularNumbers
              noWrap
              className={directionClass(s.u)}
              style={{ marginInlineStart: 'auto' }}
            >
              {fmtKrwFromMan(s.u)}
            </TextLabel2>
          </HStack>
        ))}
        <HStack gap={1} alignItems="baseline" width="100%" className="sr-wf-sum">
          <TextLabel1 as="span" noWrap>
            토탈
          </TextLabel1>
          <TextLabel1
            as="span"
            tabularNumbers
            noWrap
            className={directionClass(parts.uPnl)}
            style={{ marginInlineStart: 'auto' }}
          >
            {fmtKrwFromMan(parts.uPnl)}
          </TextLabel1>
        </HStack>
      </VStack>
    </HStack>
  );
}
