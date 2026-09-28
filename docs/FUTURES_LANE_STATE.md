# 선물 레인 상태 (2026-08-25)

수정가 문제를 고치고 ④ Main 합류까지 가는 레인의 기록. 단계 순서는 고정이다:
Phase 0 약속 파일 커밋 → 1 진단 → 2 수리 → 3 퓨처스왑 재검정 → 4 Main 합류.

---

## Phase 0 — 약속 파일 커밋

**결론: 이미 충족돼 있었다. 이 레인이 새로 낼 커밋은 없다.**

세션 지시는 이 레인이 `BacktestWindow.tsx`·`SimulationPage.tsx` 를 포함한 33개를
스테이징한 채로 얼라인 레인을 막고 있다고 전제했다. 실측하니 그 상태는 이미
해소돼 있었다.

```
git diff --cached --name-only   → (빈 목록)
git status --short              → backend/data/raw/bigfoot_*.csv 14개뿐
git log --oneline -4
    3918bb5b 선물 진입 레벨이 «—» 였던 건 …          ← 이 레인, 로컬(미푸시)
    68253792 국채선물·퓨처스왑이 백테스트와 시뮬에 …   ← origin/main
    12fba67c 얼라인을 세로로만 재고 있었다 …
    d91031a1 주요 포워드는 손으로 짠 표였다 …
```

- **약속했던 두 파일은 `68253792` 에 실려 이미 푸시됐다.** 그 커밋의
  `src/sim/SimulationPage.tsx` 가 `import { Field } from '@/ui/ControlCard';` 를
  들고 있고 로컬 `function Field` 정의는 없다 — 이 레인이 넘긴 변경 그대로다.
  `BacktestWindow.tsx` 도 같은 커밋에 256줄로 들어갔다.
- **얼라인 레인은 안 막혀 있다.** `git merge-base --is-ancestor 12fba67c
  origin/main` 이 참이다 — 그쪽 6파일 커밋도 이미 올라갔다.
- 따라서 Phase 0 의 목적(얼라인 푸시 해제)은 달성된 상태이고, **없는 커밋을
  지어내지 않는다.**

**스테이징 목록 (커밋 전/후)**: 둘 다 빈 목록. 이 단계에서 `git add` 도
`git commit` 도 하지 않았다.

**남은 더러운 파일 14개는 이 레인 것이 아니다** — `backend/data/raw/bigfoot_*.csv`
는 bigfoot 레인 소유다. 건드리지 않는다.

**푸시 상태**: `3918bb5b`(선물 계열 엔드포인트)는 로컬에 남는다. 지시대로 이
레인은 푸시하지 않는다.

### 이 레인이 Phase 0 이전에 이미 낸 커밋

`3918bb5b` — 「선물 진입 레벨이 «—» 였던 건 데이터가 아니라 길이 없어서였다」.
`/api/futures/series/{id}` 신설. 이 커밋이 **지금 고치려는 결함을 하나 실었다**:
진입 레벨 둘째 줄의 `내재` 가 수정가를 역산한 값이다(Phase 2 §2.4 에서 수리).

---

## Phase 1 — 진단 (편집 없음)

### 항목 1 · 소비처 표 — 수준(LEVEL)인가 차분(DIFFERENCE)인가

수준으로 쓰는 곳은 전부 틀렸다(조정가를 역산하므로). 차분으로만 쓰는 곳은 옳다
— 조정은 상수 오프셋이라 **차분에서 상쇄된다**. 그것이 조정 계열의 존재 이유다.

| 파일:줄 | 무엇 | 역할 | 판정 |
|---|---|---|---|
| `app/futures.py:228` | `series_payload` 의 `y`(내재금리) | LEVEL | ✗ 수리 |
| `app/futures.py:240` | `series_payload` FSW 스프레드 | LEVEL | ✗ 수리 |
| `app/futures.py:304` | `fsw_swap_leg` `y0` — **DV01 산정에도 쓴다** | LEVEL | ✗ 수리 |
| `app/futures.py:411-412` | `run_one` `y_entry`/`y_exit`(결과 줄 표시) | LEVEL | ✗ 수리 |
| `app/futures.py:551` | `book_recon` 기준일 내재금리 | LEVEL | ✗ 수리 |
| `app/futures.py:570` | `book_recon` 일별 내재금리 | LEVEL | ✗ 수리 |
| `app/futures.py:580-581` | `book_recon` `dy` = 두 역산의 차 | LEVEL 차 | ✗ 수리 (비선형이라 상쇄 안 됨) |
| `app/mr.py:111` | `_fut_bundle` FUT 계열 + FSW 스프레드 | LEVEL | ✗ 수리 |
| `app/instruments.py:372,394` | 시뮬 선물 다리의 `mtmYield` | LEVEL | ✗ 수리 |
| `src/backtest/BacktestWindow.tsx` 진입 레벨 둘째 줄 | 내재금리 | LEVEL | ✗ 수리 |
| `src/backtest/BacktestWindow.tsx` 진입 레벨 첫 줄 | **조정가를 가격으로 표시** | LEVEL | ✗ 수리 |
| `src/backtest/LinkedCharts.tsx` 「종목 추이」 | 조정가를 수준으로 그림 | LEVEL | ✗ 수리 |
| `derive.series_history` stats(52주 min/max/avg) | 조정가·FSW 스프레드 위에서 | LEVEL | ✗ 수리 |
| `app/futures.py:314` | `run_one` 손익 `(close[i] − p_entry)` | DIFFERENCE | ✓ 유지 |
| `app/futures.py:490-491` | `book_recon` 일별 `(close[i] − close[i-1])` | DIFFERENCE | ✓ 유지 |
| `simulation/daily_valuation.py:133` | `synth_price(y0+shock) − synth_price(y0)` | DIFFERENCE (단 y0 가 오염) | △ y0 만 수리 |

### 항목 2 · KTB3 원가 불일치 — **[resolved]**

셋 중 어느 것인지 데이터로 갈랐다.

1. **조정 계열인가?** 아니다. 잔차(원가 − 벤더금리의 폐형가격)가 **3,174 구간 ·
   20일 이상 상수 0개** — 롤 계단이 아니라 **매끄러운 표류**다. (조정 계열이라면
   `CLOSE` 처럼 41개 상수 구간이 나왔어야 한다.)
2. **연도별 |잔차| 중앙(가격점)**: 2012 **5.110** → 2016 3.509 → 2020 2.191 →
   2024 0.961 → 2025 0.042 → 2026 0.001. 단조 수렴.
3. **어느 쪽이 진짜인가 — 국고 3년 현물을 기준점으로 잰다.** 선물 내재금리는
   현물에서 베이시스(수 bp)만큼만 떨어져 있어야 한다.

| KTB3, 현물 3년 대비 중앙(bp) | 2012 | 2016 | 2020 | 2023 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| **벤더 `선물내재수익률`** | +4.3 | +2.0 | +6.8 | +1.5 | +3.8 | +11.8 |
| 원가 `종가` 역산 | +182.6 | +115.4 | +76.0 | −51.9 | +0.9 | +11.8 |

| KTB10, 현물 10년 대비 중앙(bp) | 2012 | 2016 | 2020 | 2023 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| **벤더 `선물내재수익률`** | +1.0 | −0.1 | +0.5 | +1.4 | +3.4 | +3.3 |
| 원가 `종가` 역산 | +1.0 | −0.1 | +0.5 | +1.4 | +3.4 | +3.3 |

**판정**: KTB10 은 두 경로가 소수 첫째 자리까지 같다 — 방법 자체는 옳다.
KTB3 은 **벤더 컬럼만 옳고 원가 역산이 틀렸다**. 즉 `daily_ktb_price.종가`(3Y)는
5%/3년 합성 규약으로 역산되는 계약별 가격이 **아니다**(무엇인지는 이 레인의
질문이 아니다 — 쓰지 않으면 된다). 폐형과 1bp 안으로 붙기 시작한 첫 날은
**2021-12-21**(20일 연속 기준).

→ **두 테너 모두 벤더 컬럼을 읽는다.** 이것이 Phase 2 의 원칙과 같은 결론이다.

### 항목 3 · 벤더 컬럼 커버리지 — 완전

| | 시작 | 끝 | 행 | `선물내재수익률` 결측 | `종가` 결측 |
|---|---|---|---|---|---|
| `daily_ktb_price` (3Y) | 2012-01-02 | 2026-08-24 | 3,595 | **0** | 0 |
| `daily_lktb_price` (10Y) | 2012-01-02 | 2026-08-24 | 3,596 | **0** | 0 |

결측이 하나도 없고 **조정가 표(`mkt_futures_investor_close`, 2016~)보다 987일
더 길다**. 롤일에도 채워져 있으며, 오프셋 구간 경계(=롤)의 양쪽 날 모두 값이
있다 — 벤더 컬럼은 그날의 **최근월물(front)** 을 가리킨다(롤일 점프가 그 증거).

### 항목 4 · 롤 불연속 (벤더 내재금리 점프, bp)

| | 롤 횟수 | 점프 중앙 | 95분위 | 최대 | 비롤일 중앙 | 비롤일 95분위 |
|---|---|---|---|---|---|---|
| KTB3 | 40 | 5.70 | 25.90 | 27.20 | 2.00 | 8.40 |
| KTB10 | 42 | 3.40 | 9.00 | 16.30 | 2.30 | 8.90 |

가장 큰 셋: KTB3 2022-06-21(27.2) · 2022-09-20(25.9) · 2022-03-15(25.6);
KTB10 2022-12-20(16.3) · 2020-03-17(9.1) · 2024-09-13(9.0).

점프는 **하루 쌍에 갇혀 있다**(오프셋이 그날 한 번 바뀐다). 그래서 Phase 3 의
롤 규칙은 **N=1**(롤일의 일간 변화 하나를 가린다)로 충분하다 — 근거는 이 표다.

### 항목 5 · 사전등록 2 — **오염 확인됨**

기록: `Desktop\bollinger-mr\PREREG2.md` · `REPORT2.md` · `run_futures.py`.
입력 경로가 `/api/mr/strategy?id=FSW-3Y` → `main.py:919` → `mr.series_points`
(`mr.py:245`) → `_fut_bundle()` (`mr.py:111`) → `_implied_yield(CLOSE)` 다.
**FUT·FSW 네 계열 전부 조정가 역산을 소비했다.**

- 주가설: FSW-3Y·FSW-10Y, 룩백 60 · 진입 2.0 · 청산 0.5 · 손절 3.5 · lag=1
- 문턱: 본페로니 2 · 단측 p<0.025 · SR≥0.5 · 순평균>0
- 창: 계열 전 구간(2016~2026)
- **BSS 계열은 오염되지 않았다** — `mr.py:243` 에서 `universe_series` 로 갈라져
  선물 번들을 안 탄다. REPORT3 의 결론(마크 아티팩트 기각·10Y 폐기·3Y 비용 절벽)은
  BSS 위에 서 있으므로 **영향 없다**.

### 항목 6 · Main 은 이미 옳다

`backend/app/universe.py:219` 가 `SELECT 일자, 종가, 선물내재수익률, 저평가` 로
**벤더 컬럼을 읽고**, `:274` 가 그것을 `FUT-{code}-IY`(「… 내재금리」) 행으로
낸다. 유도하지 않는다. 따라서 Main 목록의 국채선물 내재금리는 처음부터 정확했고,
MR 보드·엔진만 유도해서 틀렸다 — **한 이름에 두 수**가 있었던 이유다.

---

## Phase 2 — 수리 (커밋 `de66d1e3`)

「선물 내재금리는 유도하는 게 아니라 읽는 것이었다」 — 7파일. 상세는 커밋
메시지에 있고, 여기는 이 레인이 이후 단계에서 지켜야 할 **계약**만 옮겨 적는다.

`FuturesSeries` 가 역할을 이름으로 못 박는다:

    price_adj   조정가. **차분에만**(손익·일별 변화). 역산 금지.
    implied     벤더 `선물내재수익률`. 수준·스프레드·백분위·표시 전부 이것.
    price_ctr   벤더 계약별 종가. 같은 날 내재금리와 폐형으로 안 맞으면 None
                (PRICE_RECONCILE_TOL 0.10).

가드 `test_futures.py::TestNoInversionOfAdjusted` 가 조정가를 역산하는 코드와 옛
이름 `.close` 가 다시 생기면 실패한다. **Phase 4 의 인수 조건이 이 가드다.**

**스테이징 목록**: 커밋 전 빈 목록 → `--only` 로 7파일 → 커밋 후 빈 목록.
`backend/app/main.py` 는 뺐다(전부 다른 레인). `backend/app/mr.py` 는 내 hunk만
싣고 그쪽 `DIR_LEGS` 작업을 워킹트리에 복원했다.

---

## Phase 3 — 퓨처스왑 재검정 (연구 기록 · 수리 아님)

기록은 리포 밖 `Desktop\bollinger-mr` 에 있다: `PREREG4.md`(실행 전 동결) ·
`REPORT4.md` · `run_futures4.py` · `probe_rollattrib.py` ·
`out/futures_results_v4.csv` · `data/roll_days.json`.

### 무효 표시

`PREREG2.md`·`REPORT2.md` 머리에 VOID 주석을 달았다 — 「입력 오염(조정가 역산
내재금리); FUTURES_LANE_STATE §Phase 1 참조」. **원본 결과는 지우지 않았다.**
실측 예를 함께 적었다: 그 사전등록이 소비한 FSW-3Y 의 2016-01-04 값 **175.45bp**
대 벤더 기반 **4.90bp**.

### 롤 규칙 — 실행 전에 확정했다 (PREREG4 §3)

롤일 = 조정가와 벤더 계약가의 **오프셋이 바뀌는 날**(분기 한 번의 계단, 최소
구간 47영업일). 전부 3·6·9·12월 셋째 화요일이고 3Y 40회 · 10Y 42회다. Phase 1
항목 4 를 이 레인에서 다시 재 확인했다(3Y 중앙 5.70/최대 27.20 · 10Y 3.30/16.30,
비롤일 2.10·2.40).

규칙은 **N=1 마스크** — 롤일의 일간 변화 하나를 0 으로 두고 계열을 다시 쌓는다.
근거 둘: 점프가 하루 쌍에 갇혀 있다(위 표), 그리고 최근월물이 바뀌는 날의 수준
차는 **보유자의 손익이 아니다**. 연구용 변환이고 화면 수준은 벤더 원본 그대로다.

### 판정: **NO-GO — 바뀌지 않았다**

| 주가설 (룩백60·진입2.0·lag=1·마스크) | n | 순평균 | t | 단측 p | SR | 판정 |
|---|---|---|---|---|---|---|
| FSW-10Y | 54 | +0.64bp | +0.99 | 0.163 | +0.29 | 미달 |
| FSW-3Y | 44 | −3.27bp | −2.02 | 0.975 | −0.91 | 미달 |

문턱은 사전등록 2 그대로(본페로니 2 · 단측 p<0.025 · SR≥0.5 · 순평균>0).
보조 FUT 도 전부 음(−). 시행 장부 156 + 16 = **172**.

무결성 검사도 사전등록에 미리 적은 대로 통과했다 — 오염되지 않은 BSS 대조군
다섯 줄이 REPORT2 와 **소수점까지 같다**(n·순평균·t·p·SR·MDD). 엔진도 데이터도
그 사이에 안 움직였으므로 위 수는 입력 교체와 마스크의 효과만 싣는다.

### 이번 재검정의 소득 — 롤 규칙을 미리 정한 것이 GO 를 막았다

마스크 없이 돌리면 FSW-3Y 룩백60·2.0 이 **문턱을 통과한다**(+2.92bp · t +3.62 ·
p .0003 · SR +0.61). 손익을 날짜로 가르면 그 이유가 한 줄이다:

| FSW-3Y 룩백60·2.0 · 마스크 없음 | bp |
|---|---|
| 보유 중 **롤일 22일** | **+206.5** |
| 나머지 ~750 보유일 | **−0.5** |
| 비용(50거래 왕복) | −60.0 |
| 총손익 | +146.0 |

**신호의 전부가 롤일 스물두 개**이고 나머지 날은 0 이다. 사전등록 §3 을 실행
뒤에 썼다면 이 자리에서 GO 를 지어냈을 것이다.

이것은 Phase 2 의 다른 얼굴이기도 하다 — 조정가는 **차분에 정확하고 수준에
무의미**했고, 벤더 계열은 **수준에 정확하고 차분에 롤 점프를 싣는다**. 한 계열이
두 일을 다 하지 못한다는 것이 이 레인이 두 번 배운 사실이다.

### FUT/FSW 백테스트 엔진에 대한 함의

`app/futures.py` 머리 주석은 조정가 표를 두고 「연결 계열의 롤오버 갭 병은 실측
으로 없다」고 적어 두었다. **그 문장은 조정가에 대해 여전히 참이다**(조정의 존재
이유가 그것이다) — 제품 엔진의 손익은 `price_adj` 차분이라 롤 점프를 안 탄다.
Phase 3 의 마스크는 **벤더 `implied` 계열**에만 필요한 규칙이고, 연구 레인이
그 계열 위에서 손익을 셌기 때문에 생긴 것이다. 두 문장은 충돌하지 않는다.

---

## Phase 4 — ④ Main 합류

오너 ④: 「선물/퓨처스왑이 스왑·현금채권과 같은 분류에 없다」. 맞았다 —
`Group` 열거에 `futures` 는 있었지만 **탭이 없었고**(2026-08-19 축소), 퓨처스왑은
아예 `Group` 에도 없었다. Main 표의 유니버스 행 어댑터(`toRows`)도 그날
`page.tsx` 의 rows 메모에서 빠져 있었다. 그래서 백엔드가 옳은 수를 내고 있어도
(§Phase 1 항목 6) **화면에 그 줄이 서는 자리가 없었다.**

### 왜 되살려도 되는가

2026-08-19 축소의 사유는 «가상 데이터» 였다. 이 분류에는 더 이상 해당하지 않는다:
국채선물 여섯 줄은 벤더 표(`infomax.daily_ktb_price`/`daily_lktb_price`)의
종가·선물내재수익률·저평가를 **읽은** 값이고, 퓨처스왑 두 줄은 그 벤더
내재금리와 `mkt_irs_close` 의 **교집합**이다. 같이 내려간 국고·본드스왑·크레딧은
그대로 둔다 — 이 레인의 질문이 아니다.

### 한 것

| 자리 | 무엇 |
|---|---|
| `backend/app/universe.py` | `FSW-KTB3`·`FSW-KTB10` 행 신설(kind `futuresswap`·bp) · `FUT_TENOR` 어휘 · `universe_series` 의 FSW 갈래 · `sources.futuresswap` |
| `backend/app/cache.py` | `SCHEMA_VERSION` 11 → 12 (같은 SQL 이 **다른 모양**을 낸다) |
| `src/table/rows.ts` | `Group` 에 `futuresswap` · `GROUP_LABEL` 「퓨처스왑」 |
| `src/table/universeRows.ts` | `UniverseKind` 에 `futuresswap` |
| `src/ui/nav.ts` | Backtest 카테고리 「국채선물」 신설(항목 둘) · 글리프·설명 |
| `src/app/page.tsx` | `GROUPS` 에 둘 · 유니버스 행을 **GROUPS 게이트로 걸러** 잇기 · 신선도 출처 |
| `src/backtest/book.ts` | `BOOKABLE_GROUPS` 에 둘 · **`MAIN_TO_BOOK_ID`·`bookIdOf`** |
| `backend/app/instruments.py` | `expand(..., entry_price)` — 오너 결정 2 의 서버 절반 |

### id 어휘가 둘이다 — 다리는 놓되 수는 안 옮긴다

    Main    FUT-KTB3 · FUT-KTB3-IY · FUT-KTB3-BS · FSW-KTB3   (벤더 계약가 표)
    엔진    FUT:3Y · FSW:3Y                                    (조정가 + 벤더 내재)

두 표는 **같은 계열이 아니다**. `MAIN_TO_BOOK_ID` 는 «같은 상품» 만 잇는다 —
어느 계약이냐만 옮기고 수는 하나도 옮기지 않는다. 가격 행과 내재금리 행이 같은
곳으로 가고(한 계약을 두 단위로 읽은 것이다), **저평가 행은 사전에 없다**
(계약이 아니라 벤더가 낸 베이시스 수치라 담을 포지션이 아니다).

`isBookable` 을 `bookIdOf(row) !== null` 로 다시 정의했다 — 「담을 수 있나」와
「무엇으로 담기나」는 한 질문이고, 둘로 나누면 «담을 수 있다» 고 답해 놓고 넣을
id 가 없는 상태가 생긴다.

### 인수 조건 — 「수준은 벤더, 손익은 차분」

**Main 은 조정가 표를 아예 열지 않는다.** 열지 않으면 역산할 대상이 없다 —
`universe.py` 는 벤더 표와 `mkt_irs_close` 만 읽는다. 가드
`test_futures.py::TestSeriesPayload::test_main_never_opens_the_adjusted_table`
가 그것을 잰다(`mkt_futures_investor_close` 문자열이 그 파일에 있으면 실패).
기존 가드 `test_no_source_inverts_the_adjusted_price` 의 파일 목록에도
`app/universe.py` 를 넣었다.

### 라이브 실측 (2026-08-26, 재기동 후)

    /api/universe   FSW-KTB3  0.8bp · FSW-KTB10 20.95bp
                    → MR 보드·엔진과 **같은 수** (한 이름에 한 수)
    /api/universe/series/FSW-KTB10  bp · 2,609점 · 마지막 2026-08-24 20.95
    화면 「퓨처스왑」 탭 두 줄 · 「국채선물」 탭 여섯 줄
    Main 퓨처스왑 3Y 줄 클릭 → bt=**FSW:3Y**,1,100억 → 실행
        2026-02-02 → 2026-08-24  총손익 −4,024만원
        (평가 −9,871 · 롤다운 +3,219 · 캐리 +2,628만원)
        진입 레벨 3.3bp 「내재 − IRS」 · 방향 「선물 매도 · IRS 리시브」

**두 탭의 날짜가 다르다 — 그리고 그게 맞다.** 벤더 표가 IRS 보다 하루 앞서
있어서 국채선물 탭 머리는 08-25, 퓨처스왑 탭 머리는 08-24(「하루 늦음」)다.
퓨처스왑의 신선도는 두 다리 중 **늦은 쪽**(`min`)으로 백엔드가 따로 낸다 —
선물 항목을 가리켰다면 IRS 가 밀린 날 화면이 조용히 신선해 보였을 것이다.

### 안 한 것 — 시뮬 선물 진입가 편집 (오너 결정 2)

**서버 절반은 했고, 화면 절반은 못 했다.** `instruments.expand(...,
entry_price)` 가 그 가격을 `futures_pricing.implied_yield` 로 한 번 통과시켜
선물 다리의 `mtmYield`·`entryYield`·`pvbp` 를 정한다(퓨처스왑이면 IRS 다리의
DV01 중립 명목도 따라 움직인다). 시험 다섯이 그것을 잰다.

막힌 자리는 **라우트 한 줄**이다. `POST /api/instruments/expand` 가 `body` 에서
네 필드만 읽고 넘기므로 다섯째를 받아야 하는데, 그 라우트는 `backend/app/main.py`
에 있고 이 세션의 규칙은 **그 파일을 건드리지 않는 것**이다(지금 그 파일의
변경은 전부 다른 레인의 `mr_strategy` 작업이다). `app/` 안에 라우터를 여는
모듈은 `main.py` 뿐이라 우회로가 없다.

필요한 변경은 이것뿐이다:

    # main.py expand_instrument 안
    entry_price = body.get("entryPrice")
    entry_price = None if entry_price is None else float(entry_price)
    ...
    legs = instruments_mod.expand(_dataset, series_id, direction, notional, base,
                                  entry_price)

그 줄이 들어가면 `<Field>` 에 NumField 를 붙인다. **지금은 안 붙인다** — 서버가
안 받는 컨트롤을 화면에 두면 먹히는 척하는 입력이 되고, 그게 이 리포가 이름
붙여 둔 claim-vs-behaviour 결함이다.

---

## Phase 5 — 달력이 둘인 자리에서 퓨처스왑이 죽었다 · 결함 둘 수리 (2026-09-28)

추석 연휴(2026-09-24·25)가 드러냈다. IRS 종가는 역외 프린트로 그 이틀에도 찍히고
국채선물은 09-23 이 마지막이라, **IRS 달력이 선물 달력보다 이틀 더 산다.** 그날
아침 프로덕션 `GET /api/backtest?positions=FSW:3Y,…` 가 422
`2026-09-24 is after the last observation (2026-09-23)` 였고(10Y 도 같음), pytest
전수의 `test_cashbond.py::TestLegParts` 넷이 같은 이유로 빨갰다.

### 결함 ① `book_recon` 의 버킷 — 주석은 옳고 코드가 죽은 분기였다

`futures.book_recon(with_legs=True)` 는 IRS 다리의 대사 행을 선물 행에 담는다.
「마지막 선물 행보다 뒤인 IRS 행은 마지막 행에 담는다」고 주석까지 적어 두고
`_index_on_or_after(window, rd)` 로 자리를 찾았는데, 그 함수는 창 끝을 넘는
날짜에 **예외를 던진다** — 그 뒤의 `j < len(window)` 분기는 한 번도 돌 수 없는
코드였다. 라우트가 recon 을 본체 뒤에 붙이므로 recon 의 그 한 줄이 **FSW
백테스트 전체**를 422 로 만들었다. `bisect_left` 로 바꿨다(창 끝 넘김 → 마지막 행).

### 결함 ② 스왑 다리가 패키지보다 오래 살았다 — 422 가 걷히자 드러났다

`fsw_swap_leg` 가 스왑 다리 `Position` 을 `exit=pos.exit`(열린 다리면 `None`)로
만들어 스왑 다리가 IRS 달력 끝(09-25)까지 따로 평가됐다. 헤드라인(`run_one` 의
`own`)은 선물 달력에서 09-23 에 얼어 있는데 다리 기록·성분(`swap_rec`)은 이틀
더 움직여 **다리 손익의 합 ≠ 줄 손익** — 실측 FSW 3Y 100억에서 710,090원.
`test_the_legs_add_back_to_the_row` 가 정확히 이것을 잡았다.

패키지는 **두 다리가 다 마킹된 날에만 값이 있다.** 그래서 스왑 다리의 끝을
`cal[exit_i]`(패키지의 마지막 선물 마크)로 못 박았다 — 닫힌 다리도 같다(청산일이
IRS 만 찍힌 날이면 선물은 그 전 거래일로 스냅되는데 스왑만 청산일에 서면 같은
어긋남이 선다). 그 뒤의 IRS 움직임은 사라지는 것이 아니라 **다음 선물 마크의
Δ 에 통째로** 들어간다 — `book_recon` 버킷 규칙(「IRS 가 쉰 날의 돈은 다음
버킷에」)과 같은 사상이고, 이제 두 자리가 같은 날에 끝난다.

MR 대사표의 IRS 블록(`main._mr_recon_rows` 가 `fsw_swap_leg` 로 세우는 것)도 같은
함수를 지나므로 같은 날 끝난다 — 선물 블록과 어긋나던 꼬리가 없어진다.

### 실측 (재기동 뒤 프로덕션)

    FSW:3Y   exit 2026-09-23  pnl −11,689,816  다리합 −11,689,816  Δ0
    FSW:10Y  exit 2026-09-23  pnl +13,803,599  다리합 +13,803,599  Δ0
    혼합 북(ASW·3Y·FSW)  세 줄 전부 Δ0 · 3Y 는 09-25 까지 산다(자기 달력)

### 게이트

`tests/test_futures.py::TestFswLegs::test_irs_rows_past_the_last_futures_row_land_in_the_last_bucket`
— 선물이 IRS 보다 이틀 먼저 끝나고 가운데 하루도 빠지는 픽스처에서 ①스왑 다리
끝 = 마지막 선물 마크 ②줄의 가산성 ③표가 서고 마지막 행이 마지막 선물 행
④세로합 보존 ⑤쉰 날의 IRS 행이 다음 선물 행에 담김. `test_cashbond.py::TestLegParts`
15건 · MR 셋(`test_mr`·`test_mr_convention`·`test_mr_legrecon`) 84건 초록.

### 같은 날 옆에서 잡힌 것 — 발행 캘린더 시험은 수집기 탓이 아니었다

`test_issuance.py::test_the_server_does_not_pre_sum_the_sectors` 가 빨갰던 것은
DART 파이프라인 CSV 가 **최근 30일 창**(rawData README)이라 8월을 박아 둔
픽스처가 한 달 뒤 저절로 빈 것이다. 수집기(`rawDataFullCollect` 07:54 ·
`rawDataWatch` 08:50)는 그날 아침에도 정상이었다. 달은 자료가 말하게 고쳤다
(`_latest_filing_day`).

## 부록 — CDS 준수 레인 (2026-08-26, 선물 레인과 별개)

오너 지적에서 시작했다 [OWNER — "이 가이드라인들을 안 지키는 거 같아 + 컴포넌트의
사용에 있어서도 무지"]. 맞았다. `CLAUDE.md` 가 2026-08-19 부터 «UI 작업 시
cds-code 를 따른다» 를 못 박고 있었는데 이 세션이 그걸 안 부르고 진행했다.

### 감사가 낸 것 중 살아남은 것과 철회한 것

문서(`cds.coinbase.com/llms/web/...`)를 읽고 나서야 **감사의 절반이 틀렸다는 게**
드러났다 — 「CDS 로 바꿔야 할 것」으로 올린 `Field`·`.sr-pillbtn`·`.sr-track`·
`.sr-card`·`ReadoutCard`·`FloatingWindow` 가 전부 CLAUDE.md 「화면 문법의 캐논」
표에 이미 오너가 정해 둔 부품이었다. **철회.**

살아남은 것 넷: ①`PortalProvider` 누락(아래) ②토큰 값을 px 로 다시 적은 CSS
③네이티브 `<input type="date">` ④`alpha/select` 6곳.

### `24022434` — 툴팁이 흐른 건 CSS 문제가 아니었다

`Portal.js` 가 `!document.getElementById(containerId)` 에서 **조용히 인라인
Fragment 로 떨어진다.** 그래서 툴팁이 `<th>` 안에 렌더돼 `nowrap` 을 상속했고,
2026-08-19 에 그 증상을 `.sr-rv-tiptext` 로 덮었다. 뿌리는 루트에 프로바이더가
없던 것이었다. 라이브 실측(수리 후): `#portalRoot` z-index 100001 · body 직속 ·
컨테이너 5 · 툴팁 `inPortal true`/`inTh false` · 패널 292×81 안에 229×53 3줄.

우회를 걷어내면서 클래스의 `max-width: 236px` 가 같은 컴포넌트의
`maxWidth={280}` prop 을 덮고 있었다는 것도 드러났다 — 폭은 이제 prop 하나가 진다.

`CLAUDE.md` 의 UI 절을 «cds-code 단독» 으로 개정했다 [OWNER — "폐기하고 전부
cds-code로"]. `ui-ux-pro-max` 는 출처 미기록(락파일·git 메타·source 필드 없음,
73파일 3.8MB)이라 조언을 상류와 대조할 수 없어 등록 해제했다.

### 이동평균 — 벤더 표준 [OWNER — "차트 회사들에서 제공하는 표준 MA로"]

**창을 발명하지 않았다.** 키움 HTS 공장 기본값이 «종가 단순 5·10·20·60·120» 이고,
주 5거래일이라 5=1주 · 10=2주 · 20=1개월 · 60=1분기 · 120=반기다. TradingView 계열
리본(5·10·20·50·100·200)도 같은 계열이고, 이 리포 MR 보드의 창(20·60·120·252)과
셋이 겹친다 — 두 화면이 「MA120」이라는 같은 낱말로 같은 수를 말한다.

정의는 TA-Lib 규약을 따른다: 창이 차기 전은 **`None` 이고 0 이 아니다**(lookback).

**정렬은 원리적으로 못 깨지게 만들었다.** 프리뷰는 150점으로 솎이고 화면은 그
점 배열을 두 번 더 자른다(구간 알약 → 확대). MA 를 따로 들면 그 세 자르기를
따라다녀야 하고 언젠가 한쪽만 고쳐진다 — 다른 날의 평균이 이 날 옆에 그려진다.
그래서 MA 는 **점에 얹혀** 다닌다: 서버가 솎기 전에 각 점에 붙였다가 솎인 뒤
배열로 되꺼내고, 프런트도 받자마자 점에 붙인다. 자르기가 MA 를 공짜로 데려간다.

라우트 넷이 전부 낸다 — `/api/series`(스왑) · `/api/cashbond/series` ·
`/api/futures/series` 는 `derive.series_history` 를 지나므로 **`main.py` 를 한 줄도
안 건드리고** 흘러갔고, `/api/universe/series` 만 자기 래퍼를 얻었다.

그리는 법: **색이 아니라 무게**다. 이 제품에서 색은 이미 두 사전을 갖고 있어
(방향 `--sr-up`/`--sr-down`, 기준선 호박/보라) 다섯 색을 더하면 「빨간 선」이
상승인지 MA5 인지 화면이 못 정한다. 한 색(`fgMuted`)의 사다리로 창이 길수록
굵고 진하다(1/0.30 → 1.75/0.85, 가장 무거운 것도 종목 선 2px 보다 가볍다).
스크러버는 MA 를 안 짚는다.

### MA — 껏다 켰다 + 색은 컬러토큰에서 [OWNER 2026-08-26]

오너: "당연히 껏다 켰다 가능하게 해주고, MA값도 넣어줘야지 … 색도 회색이 아니라
컬러토큰에서 가져와서 배정해주고 OR 내가 색상 지정할 수 있게". **셋 다 했다.**

취향은 `src/state/ma.ts` 한 곳이다 — `state/funding.ts` 와 같은 기계
(`useSyncExternalStore` + localStorage + 모듈 리스너). **창 목록은 여기 없다**:
서버(`derive.MA_WINDOWS`)가 유일한 목록이고 이 파일은 «보여줄까 · 무슨 색» 만
기억한다.

- **껏다 켰다** — 차트 범례의 칩이 곧 손잡이다(시뮬 케이스 칩 `CurvePreview.tsx`
  의 판례 그대로: `Chip size="xs"` + `.sr-casedash` 견본 + `invertColorScheme`).
  Setting 「이동평균」 카드에서도 같은 칩으로 켠다 — 같은 저장소라 갈리지 않는다.
- **MA 값** — 리드아웃 카드에 **켠 창만** 줄로 선다. 값의 출처가 선의 출처와
  같다(`hoverPoint.ma[k]`, `k` 는 서버 목록 첨자)라 카드와 선이 다른 수를 말할 수
  없다. 스크러버는 여전히 MA 를 안 짚는다(구슬 다섯이 더 뜨면 안 된다).
- **색** — CDS 시맨틱 토큰 여섯 중에서 고른다(`accentBold*`). hex 는 없다:
  실측으로 토큰이 테마를 따라간다(accentBoldGray light `rgb(50,53,61)` → dark
  `rgb(193,198,207)`, accentBoldGreen `rgb(9,133,81)` → `rgb(39,173,117)`).

**색 충돌은 실측해서 갈랐다**(light):

| CDS 토큰 | 이미 뜻을 가진 색 |
|---|---|
| accentBoldRed #CF202F | `--sr-up` #de2b39 (상승) |
| accentBoldBlue #0052FF | `--sr-down` #2171eb (하락) |
| accentBoldPurple #5A30AD | `--sr-ref-policy` #7c3aed (기준금리) |
| accentBoldYellow #F7D21A | 흰 배경 대비 ~1.5:1 — WCAG 1.4.11(3:1) 미달 |
| **accentBoldGreen · accentBoldGray** | **충돌 없음** |

그래서 **기본 노출 둘(MA20·MA120)이 그 둘을 가져간다.** 나머지 넷도 고를 수
있고, 고르면 Setting 이 «상승 방향색과 비슷해요» 같은 문장을 옆에 단다 —
막지는 않는다. 겹치는 색을 쓸지는 읽는 사람이 정할 일이다.

기본은 **20·120 둘만 켬**. 다섯을 다 켜면 금리 차트에 선이 일곱(종목·CD·기준금리·
MA 다섯)이 된다. 20=1개월 · 120=반기가 이 데스크가 실제로 읽는 둘이다.

라이브 SVG 실측(2026-08-26): MA20 `var(--color-accentBoldGreen)` w1.25 op.75 ·
MA120 `var(--color-accentBoldGray)` w1.75 op.95 · 종목 `var(--sr-up)` w2 op1 —
**끈 창은 path 자체가 없다.** 범례에서 MA60 을 켜니 파랑 path 가 생기고
`localStorage['sr-ma']` 가 `shown:[20,60,120]` 으로 남았다.

### 기준선도 껏다 켰다 [OWNER 2026-08-26 — "기준금리랑 CD금리도 MA처럼"]

`state/ma.ts` 를 **`state/overlays.ts`** 로 넓혔다. 기준선 둘이 MA 와 **같은
질문**(겹쳐 그릴까)을 갖게 되면서 파일 이름이 내용보다 좁아졌다 — 이름을 넓히는
편이 두 번째 저장소를 만드는 것보다 낫다(캐논 «같은 것은 한 번만 만든다»).
저장 열쇠도 `sr-ma` → `sr-overlays`: 옛 열쇠의 값은 기준선 항목이 없는 모양이라
새 열쇠로 시작해 기본값(둘 다 켬)에서 출발한다.

**있음과 그림을 갈랐다.** 이게 이 변경의 핵심이다:

    refs    그 날짜 위에 얹을 값이 **있는가** — 범례에 칩을 세울지 정한다.
            없는 것은 끌 수도 없어야 하므로 칩 자체가 안 선다(원래 규칙 유지:
            «범례가 없다 = 기준선이 없다»).
    drawn   있고 **켜져 있는가** — 시리즈·스크러버·리드아웃·보조 %축이 읽는다.

하나라도 `refs` 를 읽는 자리가 남으면 끈 선이 그 자리에만 남는다. 가드가 다섯
자리를 전부 잰다.

**색은 고르는 대상이 아니다.** CD·기준금리의 두 색은 오너가 3차까지 보고 확정한
값이라(`direction.css`) `refs` 는 boolean 둘뿐이다 — MA 와 다른 점이 그 하나다.

범례 부품은 `RefChip` 신설(MA 칩과 같은 `Chip size="xs"` + `.sr-casedash`).
`RefKey` 는 못 끄는 자리(아이들 커브의 오늘/전일)가 계속 쓴다. Setting 카드는
「이동평균」 → **「차트에 겹쳐 그리기」**로 넓히고 기준선 절을 앞에 세웠다.

라이브 실측: CD 끄니 `var(--sr-ref-cd)` path 사라지고 `--sr-ref-policy` 남음 ·
`localStorage['sr-overlays'].refs = {cd:false, policy:true}` · **둘 다 끄면 bp
차트(3s10s)의 왼쪽 %축도 내려간다**(빈 축은 폭만 먹고 아무 말도 안 한다).

기존 가드 둘이 옛 모양을 재고 있어 새 모양으로 옮겼다 — 재려던 명제는 그대로다
(`reference-lines`: 둘이 같은 부품·같은 취급 / `readout-card`: 없는 선의 값을 안
읽는다, 이제 **한 겹 강해져** «꺼 둔 선» 도 포함).

### CDS 전수 감사 (C) — 결과와 조치 [2026-08-26]

프로덕션 UI 115파일(tsx 50 · ts 65, 하니스 넷 제외). `cds-code/guidelines/
code-review.md` 14규칙을 기계 검출 -> 소스 확인 -> 판정.

**깨끗한 항목**: 원시 hex/rgb **0** · `dangerouslySet*` **0** · 잘못된 CDS 임포트
경로 **0**(18경로 전부 유효 export) · 레이아웃 스타일 붙은 raw div/span **1**.
`color-source` 가드가 실제로 일하고 있다는 뜻이다.

**철회한 지적들** — 문서·CLAUDE.md 대조 후. `background`/`color` 를 style 로
넘기는 9곳은 전부 **계산된 CSS 값**(tint 램프·케이스 팔레트·CSS 변수)이라 토큰
prop 으로 못 간다. `TableRow style={{height}}` 3곳은 **TableRow 에 height prop 이
없다**(타이핑 확인). `.sr-pillbtn` raw button 18개는 캐논. deprecated 타이포
573건은 CLAUDE.md 가 이미 정책화(신규만 금지, 이번 세션 신규 0).

**감사 수치 정정**: 「죽은 클래스 14」는 과다였다 — 넷(`sr-surface-page`·
`sr-rv-dotlabel`·`sr-rv-hovercard`·`sr-rv-pane-readout`)은 **주석에만** 있는
은퇴 기록이지 코드가 아니다. 실제는 **10클래스 / 22블록 / 161줄**.

#### 조치한 것

    ① 죽은 CSS 제거      type.css 2,922 -> 2,761 (161줄)
                         .sr-brand · .sr-megaitem{,:hover,[data-on],:focus-visible}
                         · .sr-megaitem-solo · .sr-megatext
                         · .sr-surface-cut-head/foot
                         · Lab 시나리오 절 통째(.sr-scn-strip/col/bar/pinned/vs)
    ② Box height         sim/ResultsWindow.tsx 폭포 상자 — style -> `height` prop
    ③ div -> Box         table/InstrumentTable.tsx 표 host

`.sr-megaitem` 류가 죽은 이유가 드러났다 — 메가 패널 항목이 **CDS `ListCell` 로
이미 이사**했고 CSS 만 남았다(`ui/TopNav.tsx:125`). `.sr-scn-*` 는
`lab/ScenarioPage.tsx` 가 아예 없다(2026-08-21 은퇴). 둘 다 «컴포넌트는 옮겼는데
CSS 는 안 지운» 같은 자국이다.

③ 에서 **`display="block"` 이 load-bearing** 이다: CDS `Box` 는 기본이
`display: flex` 라 그대로 두면 안의 `<table>` 이 flex 아이템이 되어 폭 규약과
다툰다. 실측으로 확인했다(host display block · table-layout fixed · colgroup
157.4/73.6/69.6… 그대로).

#### 인계받아 고친 것 — 존재하지 않는 토큰 이름 2건

동시 세션(Advanced 레인)이 넘긴 건이고 **직접 재검증했다**(dev :3200,
ThemeProvider 루트에서 getComputedStyle):

    --color-bgLine       rgba(138,145,158,0.2)    OK
    --color-bgLineHeavy  rgba(138,145,158,0.66)   OK
    --color-line         ""                       없음  <- type.css 가 부르고 있었다
    --color-lineHeavy    ""                       없음  <- 같음

프로브로 결과까지 쟀다: `.sr-eqreg > * + *` 의 border-top 계산값이 **`0px none`**
(테두리가 아예 없음)이고, 이름을 고치면 `2px solid rgba(138,145,158,0.2)`.
**등록부·원장의 행 구분선이 그동안 안 그려지고 있었다.**

`color-source.test.ts` 가 못 잡은 이유는 `var(--color-*)` **접두사만** 보고 이름의
실존은 안 보기 때문이다. 가드 신설 `guards/css-token-names.test.ts` 6 — CSS·tsx
의 모든 `var(--color-X)` 가 실측 화이트리스트 안에 있는지, 그리고 `line`/
`lineHeavy` 로 되돌아가지 않는지.

#### 동시 세션 확인 (오너 지시 «Advanced 감안»)

- `infomax-f7` = **Advanced 레인**. 리포를 안 건드린다(실행 중인 :3200 에
  `<style>` 주입 + 스크린샷). 지운 10개 중 되살릴 것 없음. 앞으로 손댈 계획은
  `sauronTheme.ts`·`table/rowHeight.ts`(ROW_H 60->42)·`type.css` 인데 **미승인·
  미착수**이고, 착수 전에 알리기로 했다.
- `infomax-be` = MR 통계 검증 레인. 읽기 전용, CSS 미접촉. 앞으로
  `src/mr/StrategyWindow.tsx` 를 만질 수 있다(오너 선택 대기).

그래서 ①은 지금 하는 편이 낫다는 데 양쪽이 합의했다 — Advanced 가 나중에
시작할 때 죽은 클래스가 이미 빠져 있는 편이 낫다.

#### 남은 오너 판단 셋

네이티브 `<input type="date">` ×3(로케일 의존 불변식) · `alpha/select` ×6(안정판
존재) · cds-web **9.15.0 -> 9.22.0**(첫 항목 = `invertColorScheme` -> `active`
rename, 이번 작업으로 2곳 -> 4곳).

### cds-web 9.15.0 → 9.22.0 승급 [OWNER 선택: «Advanced 착수 전에»]

승급을 **DateInput 이관보다 먼저** 했다: 9.20 이 입력 컴포넌트의 기본 라벨
스타일을 바꾸므로, 9.15 에서 DateInput 을 붙였다가 올리면 같은 자리를 두 번
확인해야 한다.

`💥 Breaking` 절 **0건**(9.16~9.22 전수). 올린 것 셋 — cds-web 9.22.0 ·
cds-common 9.22.0 · cds-icons 5.22.0(9.22 가 `^5.22.0` 을 요구). illustrations
4.48.0 은 그대로.

    9.16    invertColorScheme deprecate -> active (제거 예정 v11)
    9.17.0  차트 막대 그라디언트
    9.17.1  Select field press target 복구 (tshirt size 작업 여파)
    9.17.2  textTransform 을 Text 로 forwarding
    9.18    PeriodSelector 테마링
    9.19    커스텀 아이콘 세트
    9.20    입력 라벨 기본 restyle — label1->label2 · fg->fgMuted
    9.21.x  인위적 범프(변경 없음)
    9.22    체크박스 라벨 fix

조치: `invertColorScheme` -> `active` **7곳/4파일**(CurvePreview·ResultsWindow·
PreviewPane·SettingView). 가드 `chart-overlays` 도 새 이름으로 옮기고 옛 이름이
되돌아오지 않는지 함께 잰다.

#### 승급 후 실측

- **9.20 라벨 restyle 이 실제로 적용됐다**: `StartFilter` 의 «시작점» 이
  14px/400/`rgb(91,97,110)`(=fgMuted). 리포의 `Field` 가 이미
  `font="legal" color="fgMuted"` 라 **CDS 기본이 이 리포 관례에 가까워졌다**.
  CDS `label` prop 을 쓰는 곳은 둘뿐이다(BondTypeFilter·StartFilter).
- **CDS `Select` 트리거 = 높이 34px · 라운드 8px · 테두리 1px.** 32px 등고
  캐논은 안 깨졌다(`control-parity` 그린) — 그 캐논이 걸리는 행은 리포가
  `height={32}` 를 명시하는 자리이고, 이 Select 는 그 행이 아니다.
- 프런트 1,403 그린 · tsc 0 · eslint 0.

#### 승급과 무관한 발견 — `font="caption"` 은 대문자 변환이다

동시 세션(MR 레인)이 «2σ» 가 화면에 **«2Σ»** 로 나온다고 넘겼고, 재검증했다:
CDS 기본 테마의 `textTransform.caption = 'uppercase'` 이고 리포는 안 덮는다.
**9.15.0 에도 같은 값이라 승급이 만든 것이 아니다**(unpkg 로 옛 판 대조).

시그마는 대소문자가 서로 다른 글자라 오타가 아니라 **틀린 기호**다. 소스에서
caption 아래 소문자 라틴·그리스가 든 자리는 셋뿐이다:

    src/mr/StrategyWindow.tsx:770  «진입 z»   -> 화면 «진입 Z»   (MR 레인 관할)
    src/mr/StrategyWindow.tsx:773  «청산 z»   -> «청산 Z»        (같음)
    src/rv/SectorLane.tsx:148      «창(±50bp)» -> «50BP»

내삽된 단위(`{n}bp` 등)는 이 셈에 안 잡힌다 — caption 을 단위·기호에 쓰는 것은
피하는 편이 맞고, 그 판단은 별도 레인 몫으로 남긴다.

#### 인계

- Advanced 레인(`infomax-f7`)에 착수 전 통보하고 진행했다. 그쪽 Advanced 실측은
  등고 **32px 단일**(34개 중 14)·라운드 **0px(18) > 6px(13) > pill(3)** 이라
  CDS Select 의 34/8px 와 어긋난다 — `sauronTheme` 으로 맞출지 컴포넌트에서
  잡을지가 그쪽 판단이고, 수치를 넘겼다.
- **MCP 서버 핀이 `@coinbase/cds-mcp-server@9.15.0` 이다**(user 스코프). 승급
  후에는 9.22.0 으로 다시 핀 해야 문서·타이핑이 설치본과 맞는다 — 리포 밖
  설정이라 안 건드렸다. **오너 조치 필요.**

#### 감사 ②번 정정 — `alpha/select` 는 결함이 아니었다

`dts/controls/Select.d.ts` 가 `@deprecated Please use the new Select alpha
component instead` 다. **안정판이라 부른 쪽이 deprecated 이고 CDS 가 alpha 를
쓰라고 지시한다.** 리포의 6곳은 옳은 경로였다. 「alpha = 불안정」이라는 통념으로
판단하고 타이핑을 안 읽은 내 오류다.

### 날짜 입력 → CDS `DateInput` [OWNER 선택: 「DateInput 으로 이관」]

세 곳(백테스트 진입일·청산일, 시뮬 금통위 이벤트일)을 옮겼다. 어댑터 하나를
새로 만들었다 — `src/ui/IsoDateField.tsx`.

**계약은 ISO in / ISO out 하나다.** CDS `DateInput` 은 `Date | null` 과
`DateInputValidationError | null` 을 각각 상태로 받으므로(넷 다 필수 prop) 호출부
셋에 변환 두 벌과 상태 하나를 흩으면 곧 세 벌이 갈린다 — CLAUDE.md 「얼라인」 8.

#### 옮기고 나서 드러난 것 셋 (전부 실측)

**① ISO 표시는 공짜가 아니었다.** 옮기자마자 ko-KR 브라우저에서
`02/02/2026` · placeholder `mm/dd/yyyy` 가 나왔다. 뿌리는 CDS `LocaleContext`
기본값이 **`en-US`** 인 것 — `DateInput` 은 브라우저 로케일이 아니라 그 컨텍스트를
읽어 `new IntlDateFormat({locale, separator})` 를 만든다(그 소스 49~53줄).

Intl 실측으로 로케일을 골랐다:

    en-US   "2/2/2026"      -> MM-DD-YYYY
    ko-KR   "2026. 2. 2."   -> YYYY-MM-DD-   (후행 리터럴이 구분자로 남는다)
    en-CA   "2026-02-02"    -> YYYY-MM-DD    <- 이것

`<LocaleProvider locale="en-CA">` + `separator="-"`. **자릿수 순서 때문에 고른
것**이지 이 앱이 캐나다 것이어서가 아니다. 범위는 이 컨트롤 하나다 — 앱 전역에
올리면 다른 CDS 소비처까지 끌려간다.

결과적으로 표시가 **로케일과 무관하게** `2026-08-25` 다. 네이티브가 못 주던
것이고, 이 이관이 실제로 얻은 것이다(네이티브는 ko 에서만 ISO 였다).

**② 힌트 줄이 행을 깨뜨렸다.** `DateInput` 은
`helperText ?? error?.message ?? 형식문자열` 로 그 줄을 채운다 — 아무것도 안 주면
«yyyy-mm-dd» 가 상시로 붙어 블록이 **74px** 이 되고, 같은 행 형제(48~50px)보다
컨트롤이 **24px 위로** 뜬다(실측). CLAUDE.md 「얼라인」 1(등고 32px)이 깨진다.

그래서 그 슬롯을 **에러 전용**으로 돌렸다: 평소 `''`(그 `??` 는 빈 문자열에서 안
떨어진다), 에러일 때만 `undefined` 로 넘겨 문장이 나오게 한다. **줄은 할 말이
있을 때만 선다.** 부가 설명은 `Field` 의 `help` 로 간다.
수리 후 실측: 규모·진입일·청산일 셋 다 blockH 50 · ctrlTop 152 · ctrlH 30 — 동일.

**③ 라벨은 `Field` 가 져야 했다.** CDS `label` prop 은 label2(14px/400)로
그려져 형제(`Field` = legal 13px/500)와 어긋난다(라벨 top 133 vs 171). 그래서
어댑터가 `Field` 로 감싸고 CDS 라벨은 안 쓴다.

#### 얻은 것 — 실측으로 확인

범위 밖 날짜(2030-01-01)를 넣으니 **빨간 테두리 + ⚠ + 「데이터가 있는 구간
밖이에요.」** 가 뜨고 실행 버튼이 비활성됐다. 네이티브 `<input type="date">` 는
이 상황에서 **아무 말도 안 했다.**

시뮬 쪽은 `<datalist>` 가 하던 금통위 날짜 제안을 `DatePicker` 의
`highlightedDates` 로 옮겼다 — 그 자리의 규칙(«고르는 것을 돕되 막지 않는다»)은
그대로이고, 달력 안에서 **보이며** 스크린리더가 읽는다
(`highlightedDateAccessibilityHint`). 강조는 `disabledDates` 가 아니다.

#### 함께 지운 것

`.sr-date` CSS(32줄)와 고아가 된 `<datalist id="sr-mpc-dates">`. 마지막 소비처가
사라진 자리다.

가드 둘을 새 집으로 옮겼다 — `control-parity`(CSS 컨트롤 높이 셀렉터 5 -> 4)와
`control-value-font`(13px 규칙). **재는 명제는 그대로**이고 재는 자리만 CSS 에서
prop 으로 옮겼다. 신설 `guards/iso-date-field.test.ts` 12 — UTC 왕복(연말·월초·
윤년)·로케일 순서를 `Intl` 로 **직접 실행해** 확인·힌트 슬롯·네이티브 잔재 0.

### 배포 전 마무리 [OWNER — "남은 거 더 고칠 거 있으면 바로 고치고"]

- **`caption` 대문자 함정 수리 1건.** `rv/SectorLane.tsx` 의 «창(±50bp) 안에
  없어요» 가 화면에서 «50BP» 로 렌더되고 있었다 — CDS 기본 테마의
  `textTransform.caption = 'uppercase'` 다. `legal` 로 옮겼다: 둘은 **크기가
  같고**(0.8125rem) 중량과 대문자화만 다르므로, 단위·기호가 든 문장은 `legal`
  이 맞다. `src/mr/StrategyWindow.tsx` 의 «진입 z»·«청산 z» 둘은 MR 레인 관할이라
  그쪽에 넘겼다.
- **죽은 CSS 2 클래스 더.** `.sr-pill`(3블록 + 그 14줄 주석 — 참조 23건은 전부
  `sr-pillbtn` 이라 접두사로 세면 살아 있는 것처럼 보인다)과
  `.sr-surface-cut`(컨테이너 — 쓰이는 것은 `.sr-surface-cut-date` 뿐).
  `type.css` 2,761 -> 2,688.

앞선 청소에서 이 둘을 놓친 이유가 같다 — **접두사로 세면 안 된다.** 이번엔
`(?![a-z0-9-])` 로 클래스명 경계를 잡아 다시 셌다.
