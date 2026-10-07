# P0a — what data actually exists

Measured 2026-08-13 against the live database the copied backend already connects to
(`sim_portfolio` @ `miraebond2.kro.kr:4004`), by querying it directly through
`backend/app/mysqldb.py`. Nothing here is inferred.

## Headline

**The session prompt assumed everything except swaps would ship empty. That assumption
is wrong.** Cash government bonds, credit sector curves and KTB futures all have live
data paths, current to the same date as IRS.

| Asset class | Source | Range | State |
|---|---|---|---|
| **IRS (swaps)** | `sim_portfolio.mkt_irs_close` | … 2026-08-12 | **live** |
| **IRS (swaps) — supplementary** | `imx_data.timeseries` cat. `스왑-IRS(종합ALL)`, 13 tenors | 2013-01-02 … | **live**, used one day at a time when `mkt_irs_close` lags [2026-10-07]. Values agree with `mkt_irs_close` on 34,514/34,528 overlapping cells; the 14 exceptions are all 8Y/9Y, max 1.00bp. No 1D/3M here, and its `CD 91일물` is a DIFFERENT series from `cd_rate` (331/440 mismatch) |
| **Cash govvy (KTB) + credit curves** | `sim_portfolio.credit_matrix` | 2020-01-02 … **2026-08-12** | **live** |
| **KTB futures 3Y** | `infomax.daily_ktb_price` | 2012-01-02 … **2026-08-12** | **live** |
| **KTB futures 10Y** | `infomax.daily_lktb_price` | 2012-01-02 … **2026-08-12** | **live** |
| On-the-run rotation schedule | `infomax.ontherun_schedule` | 2001-01-10 … 2026-06-10 | live (forward schedule) |
| 민평 sector × rating matrices | `infomax.matrix_*` (8 tables) | 2010-01-04 … **2026-01-23** | **stale ~7 months** |
| On-the-run intraday yields | `infomax.otr_bond_intra` | 2022-01-03 … 2026-07-09 | stale ~5 weeks |
| krw-fi-pms curve/position tables | `sim_portfolio.mkt_bond_curve`, `mkt_futures_curve`, `mkt_irs_curve`, `pos_irs`, `pos_futures`, `pos_krw_bond` | — | **0 rows — empty** |

## `sim_portfolio` — the database the backend already uses

| table | rows |
|---|---|
| `credit_matrix` | 19,476 |
| `mkt_irs_close` | 2,628 |
| `mkt_bond_curve` · `mkt_futures_curve` · `mkt_irs_curve` | 0 |
| `pos_irs` · `pos_futures` · `pos_krw_bond` | 0 |

`mkt_irs_close` columns: `irs_date, irs_6m, irs_9m, irs_1y, irs_18m, irs_2y, irs_3y,
irs_4y, irs_5y, irs_6y, irs_7y, irs_8y, irs_9y, irs_10y, call_rate, cd_rate`.

The six empty tables are the shape krw-fi-pms used. They exist and are unpopulated —
a schema waiting for a loader, not a data source.

### `credit_matrix` — the find of this pass

`bas_dt DATE, bond_type VARCHAR, rt_3m … rt_30y DOUBLE` (13 tenors: 3m, 6m, 9m, 1y,
18m, 2y, 30m, 3y, 5y, 7y, 10y, 20y, 30y). **12 curve types, 1,623 daily rows each.**

Latest close, 2026-08-12:

| type | 1Y | 3Y | 5Y | 10Y | reading |
|---|---|---|---|---|---|
| `KTB` | 3.408 | 3.782 | 4.015 | 4.285 | 국고 — the government curve |
| `MSB` | 3.250 | 3.805 | 0.0 | 0.0 | 통안 — zeros past 3Y are real (no long MSB), not missing |
| `KDB` | 3.612 | 4.010 | 4.288 | 4.608 | 산금채 |
| `SPB` | 3.671 | 4.094 | 4.299 | 4.465 | 특수채 |
| `BD` | 3.678 | 4.102 | 4.341 | 4.707 | 은행채 |
| `CARD` | 3.887 | 4.345 | 4.438 | 5.645 | 카드채 |
| `OFB` | 3.967 | 4.501 | 4.703 | 6.043 | 기타 금융 |
| `CB1`…`CB5` | 3.794 … 4.107 | 4.280 … 4.852 | 4.393 … 5.314 | 4.778 … 6.343 | 회사채, rating-ordered |

This single table gives **both** legs of the two spreads a KRW desk cares most about:

- **Bond–swap spread** — `KTB` vs `mkt_irs_close`. At 2026-08-12, 3Y: `3.782 − 3.8325`
  = **−5.05 bp**. Note the sign: 국고 is *below* IRS at 3Y today. Any convention
  stated from memory rather than from this number will be wrong.
- **Credit spread to government** — any `bond_type` minus `KTB` at the same tenor.
  3Y today: `CB1` +49.8 bp, `CARD` +56.3 bp, `CB5` +107.0 bp.

Both are computable **from one table, on one date, with no interpolation.**

## KTB futures

`infomax.daily_ktb_price` (3Y) and `daily_lktb_price` (10Y), keyed `일자`, columns:

```
시가 저가 고가 종가 거래량 미결제약정수량 매수성향체결수량 매도성향체결수량
선물내재수익률 저평가 수정듀레이션
```

Two of those are already the derived quantities a basis view needs:
**`선물내재수익률`** (futures-implied yield) and **`저평가`** (cheapness — the basis).
The vendor computes them; v2 would read, not derive.

**No 5Y futures table exists.** 3Y and 10Y only.

Tick and far-month data also exist (`3선 틱 데이터` 699k rows, `10선 틱 데이터` 1.99M,
`3선 원월물 데이터` 16k, `10선 원월물 데이터` 37k, `10선 스프레드 데이터` 1.1k), so
calendar spreads have a source. `global_bond.futures_kr_3yr` holds 593k rows of the
same instrument from another feed.

## Cash bonds beyond the KTB curve

`infomax.matrix_*` — eight daily sector × rating × maturity yield matrices from
2010-01-04, 15 maturity buckets each (3월이하 … 30년이하):

`matrix_국채` (53 cols) · `matrix_통안증권` · `matrix_공사_공단채` · `matrix_지방채` ·
`matrix_커버드본드` · `matrix_유동화증권` · `matrix_금융채` (407 cols) ·
`matrix_회사채` (379 cols)

The wide ones carry rating in the column name
(`금융채산금채(이표)AAA_3년이하`, `회사채공모_보증시중은행보증BBB_5년이하`), which is the
sector/rating attribute set P3 would need — **but every one of them stops at
2026-01-23.** They are a seven-month-stale archive, not a live feed.

`infomax.Bond Info` (691 rows) and `bond_tag_code` (2,505) hold issue-level attributes
(`stdcd, bondnm, issuedate, expidate, couponrate, issueamt, …`) for issuer-level work.

## Continuity — `ontherun_schedule`

860 rows, `일자 · 변경내용 · 만기 · 종목명 · 표준코드 · 발행일 · 만기일 · 상장금액 ·
표면금리`, with four event kinds:

```
지표지정 223   지표해제 215   조성지정 215   조성해제 207
```

This is the on-the-run rotation log — the thing P3 needs to keep a cash-bond series
continuous across benchmark changes. It exists and is dated to 2026-06-10.

It does **not** solve futures roll continuity; that needs the far-month tables above.

## What braveworld's routes expose today vs what these tables could support

v1's backend serves nine routes, all IRS-derived: `/api/health`, `/api/wall/summary`,
`/api/series/{id}`, `/api/forwards`, `/api/dv01/{id}`, `/api/backtest`,
`/api/volatility`, `/api/instruments`, `POST /api/instruments/expand`, plus four
simulation routers.

**Nothing in v1 reads `credit_matrix`, the futures tables, or the 민평 matrices.** The
data has been sitting beside the swap monitor the whole time.

## Consequence for the owner ruling

The ruling was "everything except swaps ships empty — no mock data anywhere". That
still holds as a *rule*, and this inventory does not weaken it. What changes is which
classes it applies to:

| class | ships |
|---|---|
| IRS | real |
| Cash govvy (KTB curve) | **real** — `credit_matrix` |
| Credit sector curves | **real** — `credit_matrix` |
| KTB futures 3Y / 10Y | **real** — daily tables incl. implied yield and basis |
| Issuer-level credit, sector × rating detail | **empty** — source is 7 months stale |
| Positions / P&L | **empty** — tables exist with 0 rows, and out of scope anyway |

**No mock market data is required for any of the four classes above**, which is a
better outcome than the ruling anticipated.

## Fixture separation

The synthetic rows in `src/dev/synth.ts` are reachable only from `/scale`, which is a
measurement harness not linked from any product surface. They are generated in the
browser from the live summary payload and are never written anywhere. `src/app/page.tsx`
does not import `synth.ts`. Confirmed by inspection at this commit.
