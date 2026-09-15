# Brooks (2017) «A Half Century of Macro Momentum» — 부록 B·C 원문 대조 (2026-09-15)

[OWNER 2026-09-15] 「지금 테마들이 논문을 옮겨오면서 불명확하게 옮겨와진 게 아닌지 의심됨」
원문 PDF: `data/krw-macro-vintage/ref/Brooks2017_A_Half_Century_of_Macro_Momentum.pdf`
(AQR 공개 백서, 2017-08). 아래 인용은 원문 그대로이고, 대조는 우리 정의(`build_themes.py` ·
`macro_paper_fix.py` · 09-08 등록서)와 한 줄씩이다.

## 1. 원문 — Appendix B (신호 정의)

> **Business Cycle:** Business cycle trends are captured using one-year changes in forecasts of real
> GDP growth and CPI inflation. From 1990 onward forecast data is from Consensus Economics. Prior to
> 1990, I use one-year changes in realized year-on-year real GDP growth and CPI inflation, lagged one
> quarter (this definition is equivalent to changes in forecasts assuming that real GDP growth and CPI
> inflation follow random walks). Both series are from the OECD. […] Increasing growth is assumed to be
> […] bearish for fixed income […]. Increasing inflation is assumed to be […] bearish for fixed income.

> **International Trade:** International trade trends are captured using one-year changes in spot
> exchange rates against an export-weighted basket. […] A depreciating currency is […] bearish for
> fixed income (other things equal, a depreciating currency reduces the pressure on a central bank to
> reduce interest rates).

> **Monetary Policy:** Monetary policy trends are captured using one-year changes in the front end of
> the yield curve. From 1992 onwards, I use two-year yields, while prior to 1992 I use Libor and its
> international equivalents. […] Expansionary monetary policy is […] bullish for fixed income.

> **Risk Sentiment:** Changes in risk sentiment are captured using one-year equity market excess
> returns. […] Increasing risk sentiment — i.e., strong equity market returns — is […] bearish for
> fixed income.

본문 p.5: "business cycle trends are captured using a 50/50 combination of one-year changes in real
GDP growth forecasts and one-year changes in CPI inflation forecasts". 각주 12: "For 'Business Cycle'
within each asset class, I average together the growth and inflation **portfolios** to form a single
business cycle portfolio."

Exhibit 1 의 국채 부호: 성장↑ − · 물가↑ − · 통화 절하(경쟁력↑) − · 긴축(2y 상승) − · 위험선호↑ −.

## 2. 원문 — Appendix C (구성)

> **Long-short portfolio construction:** […] I first rank the universe of securities by the raw macro
> momentum measure. I then standardize the ranks […] to convert them into a set of standardized
> weights. […] I then volatility-adjust the resulting long and short positions such that the long-short
> portfolio is at 10% annual forecasted volatility using a three-year rolling risk model on monthly returns.

> **Directional portfolio construction:** For each theme within each asset class, I take a long position
> in assets in which the fundamental trend is positive and a short position in assets in which the
> fundamental trend is negative (since one-year equity returns are positive on average, I compare to an
> expanding mean). […] Each individual position is sized to target the same amount of volatility […].
> I then scale the theme portfolio across all assets to target 10% forecasted annual volatility.

p.6: 32개 자산군-테마 포트폴리오(4 자산군 × 4 테마 × 롱숏·방향성)를 각각 10% 변동성으로 맞춘 뒤
등가중. 방향성 포트폴리오는 "designed to be market neutral on average".

## 3. 대조 — 우리 정의와 어긋난 자리

| 자리 | 논문 | 우리 | 판정 |
|---|---|---|---|
| 경기순환의 성장 축 | 실질 GDP 성장률 «전망치» 1년 변화 (1990 이전 대체: 실현 GDP 성장률 1년 변화, 1분기 지연) | OECD **수출액** yoy 의 1년 변화 (실현치) | **어긋남.** 성장률 자리에 수출이 서 있다. `macro_paper_fix.py` 의 「경기순환은 논문과 같다」는 틀린 문장 |
| 경기순환의 결합 | 성장 «포트폴리오»와 물가 «포트폴리오»를 평균 (각주 12) | 성장·물가 가속을 신호에서 평균한 뒤 부호 = sign(mean) | **어긋남.** 둘이 갈리는 날 0 이 되거나 한쪽이 이긴다. 논문식은 북 둘의 평균 |
| 경기순환 전망 지평 | 명시 없음 ("one-year changes in forecasts") | 한은 판에서 「금년 축」 | 논문에 근거 없음. 09-15 RESULT §7 의 「논문은 금년·내년 혼합 12개월」은 이 논문에 없는 문장 — 철회 |
| 국제교역 | 수출가중 바스켓 대비 현물환 1년 변화, 절하 → 국채 숏 | NEER(수출가중) 로그 1년 변화, 원화 강세 → 국채 롱 | **같다** |
| 통화정책 | 2년 수익률 1년 변화, 긴축 → 국채 숏 | 통안 2년 1년 변화(국고 2년은 2021~), 부호 − | **같다**(09-11 수정 후. 그 전 국고 1년은 어긋남) |
| 위험선호 측정 | 주식 초과수익 1년 | KOSPI 로그수익 − 콜금리, 1년 | **같다**(09-11 수정 후) |
| 위험선호 부호 기준 | **확장 평균 대비** ("since one-year equity returns are positive on average, I compare to an expanding mean") | **0 대비** | **어긋남.** 주식 1년 초과수익은 평균이 양(+)이라 0 대비 부호는 국채 숏으로 기운다 |
| 방향성 구성 | 테마마다 **부호** 롱/숏, 포지션을 같은 위험으로, 테마 포트폴리오를 10% 변동성으로, 테마 간 등가중 | 네 부호의 **평균** 하나를 북 하나에 → 두 테마씩 갈리면 0 | **어긋남.** 논문의 방향성 구조는 「테마별 부호 북 넷 등가중」(= `RESULT_theme_books` 의 북넷·부호). 09-15 낮 「논문은 연속값으로 위험 배분」이라 한 것은 틀렸다 — 순위 표준화는 횡단면 롱숏에만 쓴다 |
| 위험 모형 | 3년 롤링, 월별 수익률, 10% 목표 | 60일 창, 일별, 하루 100만원 목표 | 규모 규약 차이. 방향엔 무관 |
| 리밸런싱 | 월별 | 일별(ffill) | 차이 작음 |

## 4. 그래서

어긋난 넷 중 **구성(북 넷)** 과 **위험선호 평균 제거**, **경기순환 결합(북 둘)** 은 지금 자료로
바로 세울 수 있어 `scripts/momentum_theme_books.py` 에 논문충실판으로 넣었다(`RESULT_theme_books`
§2). **성장률 자리의 수출**은 월별 빈티지 GDP 전망이 국내에 없어 못 고친다 — 한은 분기 전망(09-14)이
그 자리를 논문 쪽으로 옮겨 본 유일한 시도다.

09-08 등록서는 「네 부호의 산술평균」을 얼렸으므로 이 대조가 등록을 바꾸지는 않는다. 새 등록을
열 때 논문 구조(북넷·부호 · 위험선호 확장 평균 · 경기순환 북 둘)로 놓는 것은 «고르기»가 아니라
원문 대조다.
