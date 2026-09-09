'use client';

/* 전략 노브 한 벌 — 낱개 창(`StrategyWindow`)과 통합 장부 창(`BookWindow`)이
 * **같은 것**을 쓴다 [OWNER 2026-09-01, 통합 밴드 워치].
 *
 * 갈라 낸 이유는 CLAUDE.md 얼라인 8(«같은 것은 한 번만 만든다»)이다. 두 창이
 * 노브를 따로 그리면 프리셋 하나만 바뀌어도 화면이 둘로 갈리고, 그때 「낱개로는
 * 벌고 통합으로는 잃는다」가 규칙 탓인지 노브 탓인지 읽는 사람이 구분할 수
 * 없다. 서버도 같은 자리를 하나로 두었다(`main._mr_leg` — 준비·시뮬 한 벌).
 *
 * 여기 있는 것은 **모양뿐**이다. 값의 뜻·근거·기본값은 전부 `api.ts` 의 상수가
 * 지고(그 파일 주석에 출처), 산술은 서버가 진다(§16).
 *
 * 「종목」 칸만 창마다 다르다 — `lead` 로 받는다(낱개는 계열명, 통합은
 * 「BSS 통합」과 만기 수).
 */

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Text } from '@coinbase/cds-web/typography';
import { PeriodSelector } from '@coinbase/cds-web/visualizations/chart';

import { Field, NumField } from '@/ui/ControlCard';
import { CONTROL_H } from '@/ui/controlHeight';

import {
  MR_COST_PRESETS,
  MR_SPAN_TABS,
  type MrSpan,
  type MrStrategyParams,
} from './api';
import { condWord } from './parts';

/* σ 칸의 공통 폭 상수(`SIGMA_W`)는 은퇴했다 [OWNER 2026-09-02 — "칸안에서 빈
 * 부분 축약"]. 셋의 자연폭이 127.4·116.3·118.8 로 달라 공통 폭은 필연적으로
 * 죽은 폭을 낳았다 — 이제 칸마다 제 폭이고 그 수는 호출부에 실측과 함께 있다. */

/* 이 줄의 컨트롤은 **넷**이다 — 종목(읽기) · 구간 · 비용 · Delta.
 *
 * 배타 선택이던 손 알약 `Choice`(진입 규칙)와 σ 전용 알약 `SigmaPick` 은 여기
 * 있었고 2026-09-09 에 같이 내려갔다 [OWNER — "진입 규칙이나 룩백, 진입 청산
 * 손절 시그마는 그냥 최초 전략 실험 화면에서 사라지게 하고"]. 그 다섯은 이제
 * **격자가 답한다**(근사 최적화 162칸의 1등) — 자리와 근거는 아래 「조건」 칸의
 * 주석에 있다. 앱의 배타 선택 정본은 그대로 `ui/ControlCard` 의 `Segmented`
 * 이고(Backtest 방향 칸이 쓴다), 프리셋 목록도 그대로 계약(`api.ts`)에 산다 —
 * 격자가 그 목록 위에서 돈다.
 *
 * 남는 둘(비용·Delta)은 «프리셋 + 자유값» 줄이지 배타 선택이 아니다(값이 프리셋
 * 밖이면 아무 알약도 안 눌린다). */

/* 숫자 칸이던 `NumInput` 은 공용 `NumField`(`ui/ControlCard`)가 됐다
 * [OWNER 2026-09-02 — "공용 부품은 한 벌로 승격"] — 같은 blur/Enter 커밋
 * 기계가 시뮬·rv 에 두 벌 더 있었다. 여기 있던 «음수 거부»(n >= 0)는 공용의
 * `min={0}` 이 지고, 폭은 호출부의 `<Box width={64}>` 이 진다(그 폭의 산술은
 * 각 호출부 주석에 — 56 이던 시절 자기 화면의 프리셋이 안 들어갔다).
 * 라벨은 Field 가 진다 — NumField 의 label 은 접근성 이름이다. */


/** 실행과 노브가 갈렸는가 — **조용한 재계산 금지**의 판정.
 *
 * **여기 서는 것은 엔진에 들어가는 값뿐이다.** 결과를 못 바꾸는 값이 stale 을
 * 세우면 그 노브가 결과를 무효로 만들고 재실행을 요구하게 된다. 2026-08-26 에
 * 「관찰 σ」(`warnZ`)를 이 판정에서 뺐고, 2026-09-02 에 그 값 자체를 화면에서
 * 내렸다(`api.ts` 프리셋 주석에 근거) — 결과를 못 바꾸는 노브의 종착지다.
 *
 * 두 창이 같은 판정을 쓴다: 낱개와 통합이 다른 조건으로 stale 을 세우면 같은
 * 노브를 돌렸을 때 한 창만 낡은 숫자를 그대로 들고 있게 된다.
 */
export function mrKnobsStale(p: MrStrategyParams, k: MrStrategyParams): boolean {
  return (
    p.lookback !== k.lookback ||
    p.entryZ !== k.entryZ ||
    p.exitZ !== k.exitZ ||
    p.stopZ !== k.stopZ ||
    p.costBp !== k.costBp ||
    p.notional !== k.notional ||
    /* 진입 규칙은 엔진에 들어가고 거래 목록을 바꾼다 — 그래서 여기 선다. */
    p.entryMode !== k.entryMode ||
    /* 실전 규칙 다섯도 전부 엔진에 들어간다. `countOpen` 은 총손익을 안 바꾸지만
       승률·거래 수를 바꾸므로 조용히 재계산하면 안 되는 것은 같다. */
    p.timeStop !== k.timeStop ||
    p.costModel !== k.costModel ||
    p.regime !== k.regime ||
    p.reverseExit !== k.reverseExit ||
    p.countOpen !== k.countOpen
  );
}

/** 설정 줄 **하나** + 실행 — 원본 PMS 노브 줄이다. 그 위에 얹던 실전 규칙 줄은
 * 2026-09-02 에 화면에서 내렸다(아래 그 자리 주석). */
export function MrKnobBar({
  lead,
  leadLabel = '종목',
  knobs,
  onChange,
  onRun,
  running,
  span,
  onSpanChange,
  spanNote,
}: {
  /** 「종목」 칸에 설 값. 낱개는 계열명, 통합은 「BSS 통합」이다. */
  lead: string;
  leadLabel?: string;
  knobs: MrStrategyParams;
  onChange: (patch: Partial<MrStrategyParams>) => void;
  onRun: () => void;
  running: boolean;
  /** 구간 — **전역 설정값** [OWNER 2026-09-04]. 주면 노브 줄 **위에** 자기 줄로
   *  선다. 위에 두는 이유는 그것이 «전역» 이라는 사실을 자리가 말해야 하기
   *  때문이다: 아래 줄은 이 종목의 규칙이고, 이 줄은 그 규칙을 **어느 구간에서
   *  채점하는가** 다.
   *
   *  안 주면 줄 자체가 안 선다 — 아직 이 손잡이를 안 받은 창(통합 장부)이
   *  빈 줄을 그리지 않게. */
  span?: MrSpan;
  onSpanChange?: (v: MrSpan) => void;
  /** 그 구간이 실제로 언제부터인가 — 서버가 채점한 첫 봉이다. 화면이 지어내지
   *  않고 결과에서 읽어 넘긴다(달력 산술이 서버·화면 두 곳에 있으면 갈린다). */
  spanNote?: string;
}) {
  const set = onChange;
  return (
    /* 감싸는 `VStack` 은 **줄이 둘이던 시절의 seam** 이었다(두 줄 사이를 창
       몸통의 gap 16 이 아니라 부품이 6 으로 지게 한 것). 실전 규칙 줄을 내린
       지금은 자식이 하나뿐이라 gap 이 아무 일도 안 하지만, 상자는 남긴다 —
       줄을 되살리면 seam 도 같이 살아야 하고, 그때 이 주석이 그 값을 지킨다. */
    <VStack gap={1} width="100%">
      {/* ── 구간 줄 — **전역 설정값** [OWNER 2026-09-04 — "지난 1년, 지난
          1분기, 지난 1개월을 전역 설정값으로 두고 이를 조정하면 성과도 바뀌게
          해주기"] ───────────────────────────────────────────────────────────
          2026-09-02 판에서 이 고르개는 창 **본문**에 있었고 차트·거래 표만
          잘랐다(성과 카드는 전체 기간). 성과까지 바꾸는 값이 되었으니 자리도
          노브 쪽으로 올라온다 — 결과를 바꾸는 것은 설정 줄에 있어야 한다는
          `Panel.aside` 주석의 그 규율이다.

          **그런데 stale 은 안 세운다.** 서버가 네 구간을 한 번에 보내 오므로
          (`MrStrategyRun.spans`) 고르개는 이미 와 있는 값을 고르기만 한다 —
          엔진을 다시 안 도는 이유는 `api.ts::MR_SPANS` 주석에 있다(룩백
          워밍업이 구간 앞에 있어야 z 가 선다).

          부품은 Main 미리보기의 그 캐논(`PeriodSelector`)이고, 이 고르개의
          선택은 데이터 부호가 아니므로 `.sr-tabs-neutral` 이다. */}
      {span && onSpanChange ? (
        <HStack gap={1.5} alignItems="flex-end" flexWrap="wrap">
          <Field label="구간" help="이 구간 안의 봉만 더하고, 이 구간에서 청산된 거래만 세요. 규칙은 늘 전체 표본에서 돌아요.">
            <HStack gap={1.5} alignItems="center" height={CONTROL_H}>
              <Box className="sr-tabs-neutral">
                <PeriodSelector
                  tabs={MR_SPAN_TABS}
                  activeTab={MR_SPAN_TABS.find((t) => t.id === span) ?? null}
                  onChange={(t) => t && onSpanChange(t.id as MrSpan)}
                />
              </Box>
              {spanNote ? (
                <Text font="legal" as="span" color="fgMuted" noWrap>
                  {spanNote}
                </Text>
              ) : null}
            </HStack>
          </Field>
        </HStack>
      ) : null}

      {/* ── 설정 줄 — 원본 노브 일곱 + 실행. 실행은 사람이 누른다.
          바닥 정렬 행: 블록 높이가 곧 라벨 높이(2026-08-19 얼라인 레인),
          한 행의 컨트롤은 전부 32px 등고(control-parity 의 그 등고)라
          실행도 알약이다(rv 「상세 분석」 자리의 그 컨트롤). */}
      {/* **칸 사이는 어디서나 12px 한 값이다** [OWNER 2026-09-02 — "가로 근접성
          리듬 폐기하고 그냥 동간격으로 배치하기"]. 종전에는 묶음 안 6 · 묶음
          사이 24(`.sr-fgroup`)로 덩어리를 만들었는데, 그 문법이 앱에서 은퇴했다
          (그 클래스 자리의 주석에 근거). 무엇이 한 가족인지는 이제 **라벨**이
          말한다 — 간격은 균일하고, 대신 칸마다 죽은 폭을 0 으로 조인다. */}
      <HStack gap={1.5} alignItems="flex-end" flexWrap="wrap">
        {/* 폭은 감싸는 `Box` 가 준다 — `Field` 규약(`ui/ControlCard` 머리
            주석). 상자 없이 행에 바로 놓으면 그 칸만 자기 내용 폭이 되어
            형제와 어긋난다. **96 = 최장 계열명 「KTB10 내재금리」 92.31px
            (Pretendard 14px/400 어드밴스 합, 실측 2026-09-02) + 여유 4** — 값이
            바뀌어도 뒤 칸이 안 밀리게 최장값으로 잡는다(말줄임 금지). 통합 장부가
            넘기는 실제 문자열은 「BSS 만기 9개」 77.59px 이라 함께 들어간다
            (종전 주석은 코드에 없는 「BSS 통합 · 9만기」를 인용하고 있었다).
            ⚠ 종전 160 은 죽은 폭이 67.7~107.5px 라 이 줄 첫 빈틈이 73.7px 로
            벌어졌다 — 묶음 안(6)이 묶음 사이(24)보다 넓어 근접성이 뒤집혔다. */}
        <Box width={96}>
          <Field label={leadLabel}>
            {/* 컨트롤이 아닌 값도 같은 32px 상자에 담는다 — 백테스트 「진입
                레벨」 칸의 판례(안 담으면 이 블록만 바닥에서 어긋난다). */}
            <HStack height={CONTROL_H} alignItems="center">
              <Text font="label2" as="span" noWrap>
                {lead}
              </Text>
            </HStack>
          </Field>
        </Box>
        {/* ── 조건은 **읽는 칸**이다 [OWNER 2026-09-09 — "진입 규칙이나 룩백,
            진입 청산 손절 시그마는 그냥 최초 전략 실험 화면에서 사라지게 하고,
            전략 실험을 누름과 동시에 그냥 바로 최적화 값을 보여주는 것이
            합당해 보임"] ─────────────────────────────────────────────────────
            여기 있던 다섯(룩백 · 진입 규칙 · 진입/청산/손절 σ)이 내려갔다.
            **엔진·계약·프리셋은 그대로**이고(`MR_STRATEGY_PRESETS` 는 격자가
            읽는다), 손으로 고르는 자리만 없앤 것이다 — 실전 규칙 다섯을 내릴
            때의 그 판례와 같은 처리이고, 되살리려면 이 자리에 줄을 다시
            세우면 된다(git 이력: 이 줄을 지운 커밋 하나).

            **왜 내렸나.** 이 다섯은 사람이 고를 값이 아니라 격자가 답하는
            값이다 — 창을 열면 근사 최적화 162칸이 돌고 그 1등이 곧 조건이다.
            사람이 고르는 것은 **비용과 Delta** 뿐이다(그 둘은 그날 호가폭과
            이 데스크의 포지션 크기라 격자가 흔들 수 없다).

            대신 **무엇으로 돌린 수인지**는 화면에 남아야 한다 — 그 문장이 이
            칸이고, 조건을 바꾸는 길은 최적화 절의 「채택」 하나다.

            폭 232 = 최장 문장 「120일 · 2.5/1/3.5σ · 밴드 복귀」의 실측 잉크
            (Pretendard 13px/500, 브라우저 실측 2026-09-09: 228.4px)에 여유 4.
            값이 바뀌어도 뒤 칸이 안 밀리게 최장값으로 잡는다(말줄임 금지). */}
        <Box width={232}>
          <Field
            label="조건"
            help="근사 최적화 격자 162칸의 1등이에요. 룩백 · 진입/청산/손절 σ · 진입 규칙 순서예요. 바꾸려면 아래 최적화 절의 TOP 5 에서 채택하세요."
          >
            <HStack height={CONTROL_H} alignItems="center">
              <Text font="label2" as="span" noWrap>
                {condWord(knobs)}
              </Text>
            </HStack>
          </Field>
        </Box>
        {/* ── 비용·Delta·실행은 **한 상자에 담는다** [2026-08-28 실측] ─────
            묶음을 만들려는 게 아니라 **감쌈(wrap)을 제어**하는 장치다: 형제로
            늘어놓으면 줄이 넘칠 때 감쌈이 아무 데서나 잘라 비용만 첫 줄에 남고
            Delta·실행이 둘째 줄로 갔다(실측 x 1409~1473). 셋을 한 상자에 담으면
            **셋째** 넘어간다. 안쪽 간격도 바깥과 같은 12px 다. */}
        <HStack gap={1.5} alignItems="flex-end">
        {/* 비용에 프리셋이 생겼다 [OWNER 2026-08-28]. 종전에는 「근거 없는
            값을 늘어놓지 않는다」는 이유로 자유 입력만 뒀는데, 그 사이에 근거가
            생겼다 — 국고3Y·IRS3Y 패키지 실제 편도가 ≤0.5bp 라는 오너 답이다.
            **기본이 0.5 다.** 싸게 잡은 비용은 결론을 통째로 뒤집는다. 자유
            입력은 남긴다 — 그날 그 종목의 호가폭이 셋 중 어느 것도 아닐 수 있다.

            **셋이 0.05/0.2/0.5 → 0.25/0.5/1 로 갈렸다** [OWNER 2026-09-04].
            뜻과 근거는 `api.ts::MR_COST_PRESETS` 가 진다.

            **폭 205 = 실측** [2026-09-07, 브라우저에서]. 알약 셋 53.45 + 44.89
            + 30.44 에 자유 입력 64 를 더해 잉크 192.78 이고, 간격 3 × 4px 를
            얹어 **차지하는 폭 204.78** 이다 — 205 면 죽은 폭 0.22px 다.

            정정 이력을 남긴다. 2026-09-02 실측은 옛 프리셋(0.05/0.2/0.5)의
            「잉크 219.3px」이었고, 09-04 에 셋이 갈리면서(「0.5」 3글자 → 「1」
            1글자) 그 수를 **유도**로 줄여 212 를 썼다(숫자 ≈7.7 · 마침표 ≈3.5
            로 잡아 ≈208 + 여유 4). 유도는 방향은 맞았지만 **7.22px 을 남겼다**
            — 같은 줄의 룩백 칸 0.98 · 진입 σ 0.56 과 견주면 이 칸만 어긋나
            있었다. 재고 나서야 그것이 보였다(CLAUDE.md 얼라인 6 — 눈이 마지막
            가드다). */}
        <Box width={205}>
          <Field
            label="비용 (bp)"
            help="왕복이 아니라 편도예요. 0.5는 오너 실측(국고3Y·IRS3Y 패키지)이고, 0.25는 좋은 날, 1은 나쁜 날의 호가폭이에요."
          >
            <HStack gap={0.5} alignItems="center">
              {MR_COST_PRESETS.map((v) => (
                <button
                  key={v}
                  type="button"
                  className="sr-pillbtn"
                  data-on={knobs.costBp === v || undefined}
                  aria-pressed={knobs.costBp === v}
                  aria-label={`비용 편도 ${v}bp`}
                  onClick={() => set({ costBp: v })}
                >
                  {v}
                </button>
              ))}
              {/* 64 = 최장 값 「0.05」 25.91px + CDS TextInput 좌우 패딩 16+16 +
                  테두리 2 = 59.9 에 여유(실측 2026-09-02). 종전 56 은 글자 자리가
                  22px 뿐이라 **자기 화면의 프리셋 0.05(25.9)와 도움말이 말하는
                  동적 비용 0.15(23.1)가 안 들어갔다** — 입력 칸은 말줄임 대신
                  잘라서 스크롤하므로 포커스가 없으면 끝자리가 조용히 사라진다
                  (말줄임 금지 §3 의 잘림과 같은 등급). */}
              <Box width={64}>
                <NumField label="비용(bp)" value={knobs.costBp} min={0} onCommit={(v) => set({ costBp: v })} />
              </Box>
            </HStack>
          </Field>
        </Box>
        {/* 96 — 글자 자리 62px(96 − CDS 좌우 패딩 32 − 테두리 2)이고, 이 데스크가
            넣는 최대 명목 「10000000」(1천만원/bp)이 59.92px 다(13px/500 실측
            2026-09-02). 그 위(1억)는 70.02 라 안 들어간다 — 그때는 폭을 108 로
            올리거나 `NumField` 의 `format` 으로 천 단위를 넣고 다시 잰다. */}
        <Box width={96}>
          {/* 「명목」이 아니라 **「Delta」** 다 [OWNER 2026-09-04 — "Strategy에서
              명목이 아니라 Delta라고 하기"].

              라벨이 값의 뜻을 틀리게 말하고 있었다. 이 칸의 단위는 처음부터
              `₩/bp`(= DV01)이지 액면이 아닌데, 「명목」은 채권·스왑에서 **액면**
              을 가리키는 말이다 — 그래서 「명목 100만원」이 「액면 1억」과 같은
              줄에 서면 둘 중 어느 것이 주문 단위인지 화면이 못 말했다(액면은
              옆 카드가 따로 적고 있고, 그 환산이 거래마다 5~16% 움직인다).
              Delta 는 그 값이 실제로 하는 일 — 「1bp 움직일 때의 손익」 — 을
              가리키는 이 데스크의 낱말이다.

              **「원」은 한글이다** [OWNER 2026-08-28 — "이게 표기가 왜 이런식으로
              되는거지?"]. 종전에는 `₩`(U+20A9)를 썼는데, 이 앱의 본문 폰트
              **Pretendard SR 의 그 글리프가 「W + 가는 가로줄 둘」**이다 —
              40px 래스터 대조에서 `₩` 와 `W` 의 차이가 202픽셀(같은 폰트의
              「원」 대 「W」는 684)이었고, 13px 다크에서는 그 두 줄이 사라져
              화면에 **「명목 (W/bp)」** 로 섰다(실측 2026-08-28). Malgun Gothic
              에서는 652픽셀로 제대로 갈린다 — 폰트가 없어서가 아니라 이 폰트의
              U+20A9 가 반각 표기라서다.
              기호를 바꾸는 대신 한글로 적는다: 이 화면의 돈은 전부 `fmtKrw`
              가 「+100만원」으로 쓰고 있어서, 「원」이 오히려 같은 어휘다.

              폭 96 은 그대로다 — 라벨이 「명목 (원/bp)」(글자 자리 62px 산술의
              근거는 값 쪽이지 라벨 쪽이 아니다)에서 「Delta (원/bp)」로 바뀌어도
              **들어가는 값**이 안 바뀌기 때문이다(최대 「10000000」 59.92px). */}
          <Field label="Delta (원/bp)" help="1bp 움직일 때의 손익이에요. 포지션 크기라 프리셋이 없어요.">
            <NumField label="Delta(원/bp)" value={knobs.notional} min={0}
              onCommit={(v) => set({ notional: v })} />
          </Field>
        </Box>
        {/* 실행은 이 줄의 유일한 **액션**이라 채움 알약이다(`data-fill` —
            CSS 주석의 «액션 pill = 상시 회색 채움, Backtest secondary 의 look»).
            투명 알약으로 두면 옆의 라벨들과 같은 무게로 읽혀 눌리는 것처럼
            안 보인다(실측). */}
        <button
          type="button"
          className="sr-pillbtn"
          data-fill
          disabled={running}
          onClick={onRun}
        >
          {/* 창을 열면 저절로 도는 흐름이라 이 버튼은 «처음 실행» 이 아니라
              **다시 돌리기**다 [OWNER 2026-09-09]. 비용·Delta 를 바꾸면 화면이
              스스로 돌므로, 이 버튼이 필요한 자리는 실패한 뒤의 재시도와
              «같은 조건으로 한 번 더» 뿐이다. */}
          {running ? '돌리는 중…' : '다시 돌리기'}
        </button>
        </HStack>
      </HStack>

      {/* ── 실전 운용 규칙 다섯은 **화면에서 내렸다** [OWNER 2026-09-02 —
          "실전 규칙 다섯은 일단 없애서 기억만 해두는 걸로"] ──────────────────
          내린 것: 타임스탑 · 레짐 필터(변동성/추세) · 비용 모델(고정/동적) ·
          역신호 청산 · 미청산 계상. 다섯 다 2026-08-28 에 노브로 세웠던 것이고,
          그날 저녁 긴 표본(2014-06~, OOS 8.9년 · 9계열)에서 **기각**됐다 —
          타임스탑 2/9 개선, 동적비용 0/9, 레짐(변동성) 1/9, 역신호는 8/9 에서
          아무 것도 안 걸렸고, 다섯 전부 켠 포트폴리오는 SR 1.60 → 1.01 로 모든
          축에서 나빠졌다(`docs/MR_LANE_STATE.md` §긴 표본 판정 ①).

          **엔진은 그대로다** — 서버 파라미터(`timeStop`·`regime`·`costModel`·
          `reverseExit`·`countOpen`)도, 그 계약(`MrStrategyParams`)도, 기본값
          (전부 꺼짐)도 안 건드렸다. 화면에서 고르는 손잡이만 없앤 것이라
          되살리려면 이 주석 자리에 줄을 다시 세우면 된다(git 이력: 이 줄을
          지운 커밋 하나). 기각된 노브를 화면에 두면 «이걸 켜 보면 좋아질까»
          라는 질문을 화면이 계속 부른다 — 답은 이미 측정돼 있다. */}
    </VStack>
  );
}
