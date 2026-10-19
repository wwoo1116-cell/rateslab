# v2 Strategy 탭 — 네 번째 세입자 「Flow(투자자별 수급)」

## Context

Strategy 탭에는 지금 세입자가 셋(`credit-rv`·`mean-reversion`·`momentum`)이고 셋 다
«가격이 평소 대비 어디인지»를 재는 화면이다. 데스크가 그 판단을 할 때 같이 보는
**누가 사고 누가 팔았는지**가 v2 에 없다 — SQL 에는 10년치가 들어 있는데 리포는
그 표의 `CLOSE` 한 칼럼만 읽고 투자자 칼럼 스물넷을 안 읽는다
(실측: `mkt_futures_investor_close` 를 읽는 자리는 `futures.py:148`·`:166` 둘뿐이고
**둘 다 투자자 칼럼을 안 본다**).

[OWNER 2026-10-16] 결정 둘:
- **선물 + 현물 둘 다** 올린다.
- **새 세입자**로 넣는다 (`?g=strategy&s=flow`).

산출물: 선물 3Y/10Y 와 현물 국고채의 투자자별 순매수를 날짜축에 세우고, 같은
그림에 가격·금리를 겹쳐 「수급 대 가격」을 한 눈에 보게 하는 화면 하나.

---

## 1. 실측한 자료 사실 (2026-10-16, 전수)

### 원천 ① 선물 — `sim_portfolio.mkt_futures_investor_close`

5,286행 · 2016-01-04 ~ 2026-10-15 · `(deal_date, ktb_type)` PK · `ktb_type` ∈ {`3Y`,`10Y`}
· **NULL 0건** · 연 242~248 거래일(결측 없음). `VOLUME`·`INTEREST`(미결제)도 같은 행에 있다.

★**함정 1 — `INST`(기관계)는 동료가 아니라 상위 집합이다.**

```
INSTQUANTITY = SECU + TRUST + BANK + INSUR + MERCH + PENS
```

전수 5,286행에서 **오차 최대 0** 으로 성립. 열한 칼럼을 그냥 다 더하면 기관을 두 번
센다. 화면의 계층은 둘이다:

| 층 | 주체 | 칼럼 |
|---|---|---|
| 1층 (서로 더하면 0) | 기관계 · 외국인 · 개인 · 기타 · 정부 | `INST` `FRGN` `INDI` `ETC` `GOVT` |
| 2층 (기관계의 쪼갬) | 증권 · 투신 · 은행 · 보험 · 종금 · 연기금 | `SECU` `TRUST` `BANK` `INSUR` `MERCH` `PENS` |

★**함정 2 — `ETCQUANTITY` 칼럼이 없다**(`ETCPRICE` 만 있다). 그리고 `ETCPRICE / CLOSE`
로 계약수를 유도하면 **이 리포가 가드로 막아 둔 역산**이다: `CLOSE` 는 뒤로 조정된
연속 계열이고 수준으로 쓰면 3Y 중위 89.5bp·최대 182bp 틀린다
(`app/futures.py:100-118`, `tests/test_futures.py:296-323` 가 잰다).

정답은 **영합 폐쇄** — 가격이 아예 필요 없다:
```
ETC = −(INST + FRGN + INDI + GOVT)
```
검증: 그 폐쇄값의 부호가 `ETCPRICE` 부호와 4,622/5,143(90%) 일치하고 불일치는 잔차가
±1 계약인 날들. 2026년 창에서 영합은 **±13 계약** 안에서 닫힌다(일 거래량 15만 계약
대비 0.01%).

★**함정 3 — `GOVT`(정부)는 죽은 칼럼이다.** 전 구간 평균 |GOVTPRICE| = 0.
1층에서 빼고 주석으로 남긴다(또는 「항상 0」이라고 화면이 말한다).

부수 사실: `PRICE / QUANTITY = CLOSE × 1e6` (계약 1장 = 액면 1억 × 가격/100).
**명목을 폭과 같이 적는 규칙**(기존 피드백)에 쓸 수 있는 금액 칼럼이 이미 있다는 뜻 —
위험 1단위당 명목을 따로 지어낼 필요가 없다.

### 원천 ② 현물 — `infomax_API.ktb_investor`

772,988행 · 2015-01-02 ~ 2026-10-15 · **PK 없음** · 종목(isin)별 ×
`market` ∈ {전체, 장외, 장내} × `buysell` ∈ {매수, 매도, 순매수} × 투자자 10주체.

- **단위는 백만원.** `infomax_API.bis_otc_investor_daily.vol_mil`(명시적 백만원)과
  대사해 확정: 10-13 외국인 장외매수 1,360,960 **자릿수까지 동일**, 보험은 3일 모두 동일.
- `순매수 = 매수 − 매도` 가 4,885/4,885 정확히 성립 → **순매수 행을 그대로 읽는다**.
- ★**함정 4 — 중복 22,775 조**(`date,isin,market,buysell` 기준, 최대 2행). 최근 날짜엔
  없고 과거에 있다. `deal_time` 최대값 한 장만 고르는 규칙이 필요하다(최근 자료는
  조합마다 `deal_time` 이 하나라 안전 — 실측).
- ★**함정 5 — 은행이 bis 와 안 맞는다.** 10-15 장외매수 은행 969,935 vs bis 790,102.
  외국인·보험은 맞는다. 원인 미확인 → **대사 관문**(§6)으로 둔다.
  > ★**대사 완료 [2026-10-19]** — 결함이 아니다. 「외국인·보험은 맞는다」가
  > **하루치 우연**이었고, 10-16 로 다시 재니 열 주체 전부 어긋난다(외국인
  > −40,001 · 보험 −340,000). 가른 자는 **영합**이다: `ktb_investor` 는 주체 합이
  > 0 이고(30영업일 전부, 잔차 ≤3백만원) 딜러가 한 주체로 선다 — **두 다리를 다
  > 적는 완결 회계**다. bis 는 매수 `전체` = 부분 합이고 `증권사간` 이 0 이라
  > **한쪽 면만** 적는다. 설계가 다른 두 측정이라 서로를 판정할 수 없다.
  > 정본 근거는 `backend/app/flow.py` 머리 함정 ⑤.
- 유니버스는 **국고채 전용**: 국고 명목 84종 + 물가 5종 + 원금/이자 분리채 79종.
  통안·은행채 없음. 분리채(`국고이자…`·`국고원금…`)는 기본 제외.
- `deal_time` 이 07:00:02 → **현물 수급은 T+1 아침에 도착한다**(선물도 T+1).
  > ★**정정 [2026-10-19]** — 둘의 도착 시각이 **다르다**. 월요일 실측:
  > 선물 투자자표는 08시대에 금요일(10-16)치를 받았고, **현물은 10:11 에도
  > 아직 10-15** 였다. [OWNER 2026-10-19] 「현물 수급은 원래 좀 늦게 들어온다」 —
  > **결측이 아니라 정상 지연**이다.
  > 설계 함의 둘: ① 두 원천의 `asof` 가 **다른 것이 정상**이므로 조건 스트립이
  > 둘을 따로 적어야 하고(목업이 그렇게 섰다), 현물 면이 하루 뒤여도 **경고가
  > 아니다**. ② 그래서 `flow.watermark()` 는 두 표의 `(MAX, COUNT)` 를 잇는
  > **복합**이어야 한다 — 한쪽만 보면 다른 쪽이 들어와도 캐시가 안 바뀐다(§3 1번).
- 2026년 누적 순매수(조원, 분리채 제외) 실측: 금융투자 −93.7 · 외국인 +59.9 ·
  보험 +17.7 · 자산운용 +11.4 · 개인 +5.0 · 국가지자체 +4.9 · 기타법인 +3.6 ·
  은행 −5.7 · 기금공제 −2.5 · 기타금융 −0.5. → **의미 있는 주체는 일곱, 셋은 잡음.**

### 두 원천의 어휘 맞추기

| 공통 주체 | 선물 | 현물 |
|---|---|---|
| 외국인 | `FRGN` | `foreigner` |
| 개인 | `INDI` | `individual` |
| 증권 | `SECU` | `financial_investment` (금융투자) |
| 투신·운용 | `TRUST` | `asset_management` |
| 은행 | `BANK` | `bank` |
| 보험 | `INSUR` | `insurance` |
| 연기금 | `PENS` | `fund_or_mutual_aid` (기금공제) |
| 짝 없음 | `INST`(기관계)·`MERCH`(종금)·`GOVT` | `other_financial`·`government_or_municipal`·`other_corporate` |

**매핑표는 백엔드가 쥔다**(서버가 말을 쥔다는 `creditdts.py:191` 의 `basis` 규칙).
단위가 다르다 — 선물은 **계약수**, 현물은 **백만원**. 한 축에 겹치지 않는다.

### 안 쓰는 원천 (근거를 남긴다)

| 표 | 왜 안 쓰나 |
|---|---|
| `infomax_API.investor_intra` (9.5M행, 오늘 15:45까지) | 2025-02 부터뿐이고 `underlying` 이 빈 문자열 — 계약코드 65/67/70 해독표가 없다. 일중은 별도 레인. |
| `infomax_API.otc_investor_daily` (34k) | 2026-09-14 부터 한 달. 차트로 짧다. |
| `infomax_API.bis_otc_investor_daily` (1.8k) | 2026-10-12 부터 나흘. **대사용으로만** 쓴다. |
| `imx_data.ktbinfo_investor` (2,811행) | `infomax_API.ktb_investor` 의 짧은 사본. |

---

## 2. 설계 — 차트가 이 레인의 실제 제약이다

★**이 리포에는 막대 계열이 없다.** 전수 검색 결과 `addSeries` 호출은 `src/chart/series.ts:64`
한 자리뿐이고 그것은 `LineSeries` 다. 히스토그램·바·캔들·베이스라인·누적(stacked) 차트가
**0건**이다. 그리고 ★**N계열 범주형 팔레트도 없다** — 이름 있는 색은 방향 2 + 참조 4뿐이고,
`state/overlays.ts:41` 의 `MA_COLOR_TOKENS` 6개 중 **넷은 이미 충돌 경고가 달려 있다**
(Red≈`--sr-up`, Blue≈`--sr-down`, Purple≈`--sr-ref-policy`, Yellow 는 WCAG 1.4.11 미달).
실제로 자유로운 색은 **녹색·진회색 둘**이다.

결론 둘이 거기서 따라 나온다.

**(가) 열한 주체를 한 그림에 칠하지 않는다.** 전수는 **표**가 지고, 그림에는
**최대 4계열**만 올린다. 고르는 손잡이는 새로 만들지 않는다 — `ChartReadoutStrip` 의
`StripSlot.toggle` 이 이미 그 문법이고(`guards/chart-readout-strip.test.tsx` ⑤가
토글·drop 사다리를 잰다), `MA_COLOR_WARNING` 이 「색이 겹칩니다」를 지우지 않고
**말해 주는** 선례다.

**(나) 일별 순매수는 막대가 맞다.** FT Visual Vocabulary 의 «change over time, discrete
values» 가 column 이고, CLAUDE.md 규칙 8 이 이 판단을 그 외부 표준에 맡긴다. 라인으로
그리면 차트 유형 자체가 오독이다. 그래서 **이 레인이 리포의 첫 `HistogramSeries` 를
들인다** — `src/chart/series.ts` 에 `addHistogram` 을 더하고 `TimeChart` 의 `TimeLine` 에
`kind?: 'line' | 'histogram'` 판별자를 붙인다. 점마다 색이 달라야 하므로(부호 방향색)
`HistogramData.color` 를 쓴다. 가드 영향은 열거 가능하다(§5).

> **대안(차트층을 안 건드리는 길)**: 일별 면을 라인 + `area:'solid'` + zero `priceLine`
> 으로 그린다(`backtest/LinkedCharts.tsx` 손익 차트 문법 그대로, 추가 코드 0). 모양은
> 실루엣이 되고 유형은 틀리지만 하루 안에 선다. 오너가 차트층을 열기 싫다면 이쪽.

### 화면 골격 (`PreviewPane` 의 네 토막 + `LinkedCharts` 의 쌍 차트)

```
┌ 조건 스트립 .sr-rv-bar ────────────────────────────────────────────────┐
│ Cond: 원천 / 기준일 / 단위 / 지연(T+1)      «집계예요 — 새 판단이 아니에요.» │
├ 컨트롤 행 (등고 32px) ────────────────────────────────────────────────┤
│ [선물 3Y|10Y|현물] 세그먼트   Select 만기대(현물)   PeriodSelector 구간    │
├ ChartReadoutStrip  (그림 밖·위, 높이 22 고정) ─────────────────────────┤
│ 날짜 · ■외국인 · ■증권 · ■은행 · ■개인  ← 토글 슬롯이 계열 선택을 진다    │
├ 차트 ①  .sr-plot  TimeChart ──────────────────────────────────────────┤
│ 누적 순매수 라인 ≤4개 (오른축) + 금리/가격 (aux = 왼축)                   │
├ 차트 ②  .sr-plot  TimeChart  (hideTimeAxis 없음 · syncIndex 로 묶임) ──┤
│ 일별 순매수 **히스토그램** 1계열 + zero priceLine                        │
├ 표 ─────────────────────────────── 사실 스트립 .sr-stats ─────────────┤
│ 투자자별 1D·5D·20D·YTD 순매수 랭킹        StatColumn: 규모 / 집중도      │
└──────────────────────────────────────────────────────────────────────┘
```

두 차트는 `useStackedScales()` 로 축 폭을 맞추고 **같은 `dates` 배열**을 받는다
(`guards/linked-charts.test.ts` 가 그 둘을 잰다). 리드아웃 스트립은 **하나**가 두 차트를
읽는다(`LinkedCharts.tsx:315-329` 의 그 근거).

h1 은 `STRATEGY_ITEMS` 의 label 이 지므로 **화면이 제 제목을 다시 적지 않는다**
(momentum 면과 같은 자세).

---

## 3. 백엔드

### 새 모듈 `backend/app/flow.py`

`creditdts.py`(최소 캐논) + `futures.py`(주입 시임) + `mrseries.py`(복합 워터마크)를 섞는다.

```python
#: 선물 투자자별 — 이 리포가 처음 읽는 칼럼들. 같은 표의 CLOSE 는 futures.py 가 읽는다.
FUT_TABLE = "sim_portfolio.mkt_futures_investor_close"
#: 현물 투자자별 — 데스크의 인포맥스 창고. 대소문자가 섞여 백틱으로 묶는다
#: (`paperlive.py:177` 의 그 관례).
CASH_TABLE = "`infomax_API`.`ktb_investor`"

@dataclass(frozen=True)
class FlowData:
    fut: dict[str, FlowSeries]   # '3Y'|'10Y' → 주체별 일별 순매수(계약) + 누적
    cash: FlowSeries             # 만기대별·주체별 일별 순매수(백만원)
    watermark: tuple[str, int]

def watermark() -> tuple[str, int]: ...   # ★복합 — 두 표의 (MAX, COUNT) 를 '|' 로 이음
def _fetch() -> FlowData: ...             # ★parameterless·patchable (test_creditdts 패턴)
def set_data(d: FlowData | None) -> None  # + conftest 에 autouse `flow_data_off`
def load() -> FlowData: ...               # 주입 → 워터마크 캐시 → SQL
def reset_cache() -> None: ...
def board(...) -> dict                    # 랭킹·집계는 **서버가 센다** (§16)
```

지켜야 하는 것 일곱:
1. **자기 `watermark()` 를 가진다.** `futures.watermark()` 를 재사용하면 안 된다 —
   그것은 `WHERE CLOSE IS NOT NULL` 로 걸러 투자자 행의 모집단이 아니다.
2. 두 표를 **한 연결**에서 읽는다(`with engine().connect()` — `futures.py:164` 선례).
   `read_sql()` 은 호출마다 연결을 새로 연다.
3. **산술은 DB 를 모른다**(`paperlive.py:85-88`). 영합 폐쇄·누적·랭킹은 `_fetch` 밖의
   순수 함수로 꺼내 둔다 — 그래야 SQL 없이 잴 수 있다.
4. **`CLOSE` 를 수준으로 쓰지 않는다.** 가격·금리 겹침은 `futures.load()` 의
   `implied`/`price_ctr`(벤더)를 읽는다 — 이미 있는 것을 쓴다.
5. 응답은 **plain dict · camelCase · pydantic 없음**. `asof` 는 `.isoformat()`.
6. **`excluded` 에 `why` 를 적는다**(정부 칼럼·분리채·중복 행). 조용히 버리지 않는다.
7. 화면으로 나가는 문장은 **해요체**(`test_register.py` 의 그 가드). `basis` 한 줄로
   「무엇을 보고 있나」를 서버가 말한다.

### 라우트 (`backend/app/main.py`, `@router.get` 데코레이터)

| 경로 | 반환 |
|---|---|
| `/api/flow/board?side=fut&tenor=3Y&win=…` | 주체별 랭킹 + 누적·일별 계열 + `asof`·`basis`·`excluded` |
| `/api/flow/history/{key}` | 한 주체 한 계열의 전구간(`derive.series_history` 재사용) |

`flow.FlowError` → 422, 알 수 없는 key → 404, `MissingCredentials` 는 **반드시 잡아서**
503 으로 — 안 잡으면 `RuntimeError` 전역 핸들러가 500 「계산 오류」로 바꾼다.
**디스크 캐시는 안 쓴다**(라이브 전용 선례: `/api/lab/creditdts`·`/api/rv/analysis`).
모듈의 워터마크 캐시가 그 일을 한다.

---

## 4. 프런트

| 파일 | 할 일 |
|---|---|
`src/ui/nav.ts:260` | `StrategyId` 에 `'flow'` 추가 |
`src/ui/nav.ts:264-323` | `STRATEGY_ITEMS` 에 **맨 뒤로** 한 항목. label `Flow`, glyph **1 UTF-16 단위**(`⇅` 후보 — 기존 `◈ ∿ ↗` 및 `LAB_ITEMS` 글리프와 중복 확인), desc 9자 이상 |
`src/ui/nav.ts:325-327` | `isStrategyId` 체인에 `\|\| v === 'flow'` — **손으로 쓴 체인이라 `STRATEGY_ITEMS` 에서 유도되지 않는다** |
`src/app/page.tsx:660-664` | ★`strategy === 'flow' ? <FlowPage />` **명시 분기**. 지금 체인은 `momentum` 조건이 없는 catch-all 이라 **등록만 하면 MomentumPage 가 그려진다** |
`src/lib/staticPaths.ts` | `flowBoardUrl`/`flowHistoryUrl` — `liveUrl()` 로. **URL 은 반드시 여기** (`guards/production-env.test.ts`) |
`src/flow/api.ts` | 타입 + `fetch` 셋줄(404→`BacktestUnavailable`). 선례 `momentum/api.ts:214` |
`src/flow/FlowPage.tsx` | 화면. `useState`+`useCallback`+`useEffect`, AbortController(`CreditDtsPage:319`) |
`src/flow/FlowTable.tsx` | 투자자별 랭킹. `rv/RankingTable.tsx` 선례(CDS `Table` 은 이 밀도에서 금지) |
`src/chart/series.ts` | `addHistogram()` 신설 — 리포의 두 번째 `addSeries` |
`src/chart/TimeChart.tsx` | `TimeLine.kind?: 'line'\|'histogram'` 판별자 |

`TopNav.tsx` 는 **안 건드린다** — `STRATEGY_ITEMS` 로 완전히 자료구동된다.

임포트해 쓸 것(새로 만들지 않는다): `@/ui/Cond` · `@/ui/ThHelp` · `@/ui/Stat`
(`StatColumn`/`Stat`) · `@/ui/DataState`(`LoadingState`/`ErrorState`) ·
`@/ui/ChartReadoutStrip`(+`slotChars`) · `@/ui/ControlCard`(`Field`/`NumField` — **앱에 하나**) ·
`@/table/rowHeight`(`ROW_H`) · `@/table/tint`(네 부품 한 벌) · `@/chart/TimeChart`
(+`useStackedScales`) · `@/lib/format`(`fmtLevel`) · `@/state/overlays`
(`MA_COLOR_TOKENS`·`maColorVar`) · `@/ui/window/popup`(`DROPDOWN_STYLES`).

타이포는 `Text font="…"` 만 — 옛 shorthand 는 ratchet 천장(231)이 막는다.

---

## 5. 가드 — 깨지는 것 하나, 고쳐야 하는 것 둘

**깨진다**: `guards/nav-strategy-tenants.test.ts:39-48`
```ts
expect(STRATEGY_ITEMS.map(i => i.id)).toEqual(['credit-rv','mean-reversion','momentum']);
expect(STRATEGY_ITEMS[0]!.label).toBe('Credit RV'); … [2] 'Momentum'
```
→ 목록에 `'flow'` 를 더하고 `[3]!.label` 단언 한 줄 추가. `DEFAULT_STRATEGY` 는
`credit-rv` 로 **그대로 둔다**(같은 파일이 그것을 핀한다).

**보강한다 ①** — `src/flow/`+`guards/flow-canon.test.ts` 신설. `momentum-canon` ·
`lab-credit-dts` 를 본뜬다. 꼭 들어갈 단언:
- `page.tsx` 에 `/strategy === 'flow' \?/` 가 있다 — **등록만 되고 안 그려지는 것**이
  이 탭의 알려진 구멍이다(Lab 쪽엔 이 단언이 있고 Strategy 쪽엔 없다).
- 캐논 부품 임포트 · `height: ROW_H`(raw 60 금지) · 네 부품 tint 한 벌 ·
  고지 문장 존재 · `INST` 를 2층과 **같이 더하지 않는다**(함정 1의 코드판 가드).

**보강한다 ②** — 차트층을 건드리므로 같이 손봐야 하는 가드:
`chart-palette.test.ts`(④ 캐논 한 곳 — 히스토그램 옵션도 거기서) ·
`chart-stability.test.ts`(비교자가 `kind` 를 봐야 한다) ·
`linked-charts.test.ts`(같은 `dates`·같은 인셋·zero 항상 프레임 안) ·
`chart-readout-strip.test.tsx`(⑤ 사다리 깊이 = 토글 가능 계열 수).

자동으로 새 디렉터리를 훑는 것들(등록 불필요, 그러나 통과해야 함):
`color-source`(hex 는 `direction.css` 만) · `no-ellipsis`(허용목록 없음) ·
`no-midword-break` · `css-token-names`(`line` 은 토큰 이름이 아니다 — `--color-bgLine`) ·
`control-fill` · `control-parity`(32/36) · `align-canon`(`32` 를 따로 쓰지 않는다) ·
`spacing-scale` · `control-value-font`(`Select font="legal"`) · `typography-ratchet` ·
`production-env` · `portal-provider`(`ThHelp` 쓰면 필요).

백엔드: `conftest.py` 에 autouse `flow_data_off` 추가(주입 시임을 만들면 **의무**),
`tests/test_flow.py` 신설 — `_fetch` 를 `monkeypatch.setattr` 로 갈아 **SQL 없이
결정적으로** 돈다. `TestClient(app)` 은 **컨텍스트 매니저로 쓰지 않는다**(lifespan 이
굽기 산출물을 덮어 `test_rebake` 넷을 오염시킨다).

---

## 6. 검증 (끝났다고 말하기 전에 통과해야 하는 것)

**자료 관문** — `backend/scripts/flow_check.py` 로 짜고 수를 판정문에 적는다.
1. 항등식 A: `INST = SECU+TRUST+BANK+INSUR+MERCH+PENS`, 전수 5,286행 오차 0. (현재 성립)
2. 영합: `INST+FRGN+INDI+GOVT+ETC = 0`, 2026년 창 잔차 ≤ 13계약. (현재 성립)
3. 현물 중복: `(date,isin,market,buysell)` 당 1행이 되도록 `deal_time` 최대값만 골랐나.
4. 현물 항등식: `순매수 = 매수 − 매도`.
5. ~~★**대사 관문** — `bis_otc_investor_daily` 겹치는 날(10-12~)에 주체별 대조.
   외국인·보험은 자릿수까지 맞아야 한다. **은행이 안 맞는 이유를 설명하기 전에는
   은행 줄을 화면에 싣지 않는다**~~ → **닫혔다 [2026-10-19]**. 이 관문은 전제가
   틀렸다 — bis 는 ktb 를 판정할 수 없는 다른 측정이고(위 §1 함정 5 의 대사),
   「외국인·보험은 맞아야 한다」는 기대 자체가 하루치 우연에서 나왔다. 은행 줄은
   싣는다. 대신 **ktb 자체의 영합**(주체 합 0 · 매수−매도=순매수)이 이 자리의
   관문을 대신한다.

**코드 관문**: `pnpm test`(가드 전부 녹색) · `cd backend && python -m pytest tests/test_flow.py tests/test_futures.py tests/test_register.py` · `pnpm build`.

**화면 관문**: `backend\serve.ps1 -Local` → `pnpm dev` → `/?g=strategy&s=flow`.
얼라인 규칙 6 대로 **스크린샷으로 실측**한다 — 컨트롤 행 등고 32, 두 차트 축 폭 일치,
리드아웃 높이 22, 1,920×855 에서 안 무너지는지(momentum 이 실제로 무너졌던 해상도).
그리고 배경 탭에서는 차트가 안 그려지는 것이 정상이다(라이브러리 성질).

---

## 7. 단계

| 단계 | 내용 | 끝났다는 뜻 |
|---|---|---|
**P0** | `flow.py` 선물면 + `watermark` + `_fetch` + 순수 산술 + `test_flow.py` + 라우트 | `curl /api/flow/board?side=fut&tenor=3Y` 가 선다, 관문 1·2 수치가 판정문에 있다 |
**P1** | `series.ts::addHistogram` + `TimeChart` 판별자 + 차트 가드 넷 보강 | 히스토그램 하나가 zero 선 위에 서고 가드가 녹색 |
**P2** | 세입자 등록(nav·page·staticPaths) + `FlowPage` + `FlowTable` + `flow-canon` 가드 | `/?g=strategy&s=flow` 가 선물면을 그린다, 스크린샷 실측 통과 |
**P3** | 현물면(`flow.py` 둘째 표 + 만기대 묶기 + 세그먼트) | 관문 3·4·5 통과. **5가 막히면 그 주체만 빼고 why 를 적고 출하** |

P3 이 막혀도 P0~P2 는 출하 가능하다 — 선물면만으로도 쓸 수 있는 화면이다.

---

## 8. 다음 세션 인계 프롬프트

```
sauron-v2 Strategy 탭에 네 번째 세입자 「Flow(투자자별 수급)」를 짓는다.
계획 정본: C:\Users\infomax\.claude\plans\ancient-fluttering-brooks.md — 먼저 통째로 읽어라.
리포: C:\Users\infomax\Projects\apps\sauron-v2 · CLAUDE.md 의 캐논이 전부 적용된다.

[OWNER 2026-10-16] 결정: 선물+현물 둘 다 · 새 세입자(?g=strategy&s=flow).

## 이 레인이 이미 잰 것 (다시 재지 말 것)
원천 둘: sim_portfolio.mkt_futures_investor_close (선물 3Y/10Y, 2016~, 5,286행, NULL 0)
         infomax_API.ktb_investor (현물 국고채 종목별, 2015~, 773k행, 단위 백만원)
함정 다섯이 계획 §1 에 수치와 함께 있다. 특히:
 ① INST(기관계) = SECU+TRUST+BANK+INSUR+MERCH+PENS — 전수 오차 0. 다 더하면 두 번 센다.
 ② ETCQUANTITY 칼럼이 없다. CLOSE 로 역산 금지(가드가 있다). 영합 폐쇄로 구한다.
 ③ GOVT 는 전 구간 0 (죽은 칼럼).
 ④ 현물에 중복 22,775조 — deal_time 최대값만.
 ⑤ [해결 10-19] bis 는 한쪽 면만 적는 다른 측정이다 — ktb 는 주체 합 0 으로 닫힌다. 싣는다.

## 차트층의 제약 (이게 이 레인의 진짜 비용)
이 리포에 막대 계열이 0건이다 — addSeries 는 src/chart/series.ts:64 한 자리, LineSeries 뿐.
N계열 범주형 팔레트도 없다(자유로운 색 둘). 그래서:
 - 열한 주체는 **표**가 지고 그림엔 최대 4계열. 고르는 손잡이는 ChartReadoutStrip 의
   StripSlot.toggle (이미 있는 문법) — 새 컨트롤을 만들지 말 것.
 - 일별 순매수는 FT Visual Vocabulary 상 column 이 맞다 → series.ts 에 addHistogram 신설.
   차트층을 열기 싫다면 라인+area:'solid'+zero priceLine 폴백(계획 §2 의 대안).

## 순서
P0 백엔드 선물면 → P1 히스토그램 → P2 세입자 등록+화면 → P3 현물면.
계획 §7 의 「끝났다는 뜻」을 그대로 인수 조건으로 쓴다.

## 반드시 밟을 자리
- 자기 watermark() 를 만들어라. futures.watermark() 는 WHERE CLOSE IS NOT NULL 로 걸러
  투자자 행의 모집단이 아니다.
- page.tsx:660 의 전략 분기는 catch-all 이다 — 명시 분기를 안 넣으면 등록만 되고
  MomentumPage 가 그려진다. 그 단언을 guards/flow-canon.test.ts 에 박아라.
- guards/nav-strategy-tenants.test.ts:39-48 의 하드 목록이 깨진다. 새 항목은 **맨 뒤**,
  DEFAULT_STRATEGY 는 credit-rv 로 유지, 글리프는 1 UTF-16 단위.
- set_data 시임을 만들면 conftest.py 에 autouse flow_data_off 를 **같이** 넣어라.
- 화면으로 나가는 문장은 해요체(test_register.py). 서버가 basis 한 줄로 말을 쥔다.
- 끝에 pnpm test · pytest · pnpm build · 그리고 스크린샷 실측(얼라인 규칙 6).

## 보고
수치 없는 완료 보고는 받지 않는다. 관문 1~5 의 실측 수와, 못 한 것은 못 했다고 적어라.
```
