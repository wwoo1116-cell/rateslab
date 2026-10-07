# The backend in this repo is a COPY

**This is a copy. Fixes made here do not reach braveworld, and braveworld's fixes
do not reach here. Divergence is expected; record it.**

| | |
|---|---|
| Source repo | `C:\Users\infomax\Projects\apps\braveworld` |
| Source commit | `f5de1fa74de475d801128b113c0a8060f434129f` |
| Source subject | 선 · 주봉 · 월봉 — 캔들을 팝업 밖으로, 전역 모드 하나로 |
| Copy date | 2026-08-13 |
| Method | plain file copy (`shutil.copytree`), excluding `__pycache__`, `*.pyc`, `.cache`, `.pytest_cache` |
| What was copied | `backend/` (127 files, 1.3 MB) and `data/` (4 entries, 25.4 MB) |

Not a `git worktree`, not a symlink, not a submodule: all three would either write
into braveworld's `.git` or leave v2 depending on that tree being present and intact.

## The one thing that is NOT a copy: the data

The market data is **not** a single workbook, and copying the workbooks does not
give v2 the same data v1 sees.

| Source | What |
|---|---|
| **MySQL** `sim_portfolio.mkt_irs_close` @ `miraebond2.kro.kr:4004` | **primary** source of IRS closes since 2026-08-07 |
| **MySQL** `imx_data.timeseries` (category `스왑-IRS(종합ALL)`) @ same server | **supplementary** source of the IRS close, one day at a time, since 2026-10-07 — tried BEFORE the workbook. Agrees with `mkt_irs_close` on 34,514/34,528 cells; the 14 exceptions are all 8Y/9Y, max 1.00bp |
| `data/irsdata.xlsx` | fallback workbook (copied, 776,519 B at copy time) |
| **ECOS** `722Y001/D/0101000` via `app/ecos.py` (`ECOS_API_KEY`) | **primary** source of the BOK base rate — funding since 2026-08-20, the policy step since 2026-09-01 |
| `data/bokbaserate.xlsx` | base-rate **fallback** only (copied, 640,795 B) — read when ECOS has no key, no network and no cache; `policy_step` says so in `warnings` |
| `data/` incl. `AS_data.zip`, `reference/` | the simulation's `DATA_DIR` |

The MySQL database is a **shared external dependency, read-only**, reached through
`app/mysqldb.py` (`BW_MYSQL_HOST` / `_PORT` / `_USER` / `_PASSWORD` / `_DB`, each with a
hardcoded default in source). v2 and v1 therefore read the **same live rows**.

So the divergence sentence above applies to **code, not to market data**: the code
forks here, the data does not. If v1's SQL loader changes shape and this copy's does
not, the two will disagree about the same rows — that is the failure mode to watch.

## The five v2-local edits

Each is marked in place with a `V2-LOCAL EDIT n of 5` comment. Edits 4–5 landed
2026-08-14 and are both about the same thing: **v1 keeps its Next app under
`frontend/`, v2's IS the repo root.** Every path that assumed otherwise was
silently dead.

4. **`backend/scripts/build_static.py` — `OUT_ROOT`.** `frontend/public` →
   `public`. It was writing to a directory nothing serves.
5. **`backend/tests/test_build_static.py` — `_baked_manifest()`.** Same path
   fix, plus: SKIP when no tree has been baked. Those two tests check that a
   COMMITTED tree has not gone stale, and v2 has never baked one — they had
   failed with `FileNotFoundError` since the copy was taken.

   Two neighbours moved with them and are **not** numbered because they are the
   same edit: `tests/test_static_agreement.py` (`frontend/public` → `public`,
   and `:8100` → **`:8200`** — it was pointed at v1's backend, so on this copy
   it always skipped; fixing the port woke it into 20 failures that all said
   "no tree", and it now skips on that too), and `app/policy.py::CALENDAR_JSON`
   (`frontend/src/data` → `src/data`; the file does not exist here yet and the
   function returns None, which is its documented behaviour).

1. **`backend/app/main.py` — CORS** (the `app.add_middleware(CORSMiddleware, ...)`
   block, `allow_origins`). Added `http://localhost:3200` and `http://127.0.0.1:3200`.
   v1's list was `:3100` only, so v2's frontend was blocked at the preflight.
   The `:3100` origins are kept so this copy stays runnable beside v1.

2. **`backend/requirements.txt` — two missing runtime dependencies.**
   `app/mysqldb.py` imports `sqlalchemy` at module scope and builds a
   `mysql+pymysql://` URL, but neither `sqlalchemy` nor `pymysql` was listed.
   v1 runs because the developer machine already has both; a clean host dies on
   the first import. **This is a real defect in braveworld and it is NOT fixed
   there** — this session may not write to that tree. It is reported in
   `REPORT_v2.md` instead.

3. **`backend/serve.ps1` — new file, binds `:8200`.**
   The port was never in the source. v1 passes it on the uvicorn command line from
   `C:\Users\infomax\.sauron\start-backend.ps1`, which lives outside the repo. So
   "bind :8200" is a launcher, not a source edit. **`:8100` is never bound here.**

## Forward-ports FROM braveworld since the copy

The copy was taken at `f5de1fa7`. Anything v1 committed after that is not here
until it is brought over deliberately, and each one is recorded below.

### 1. 세타 — `app/theta.py` (2026-08-14)

v1 added it the same afternoon this copy was taken, in three commits
(`ef98badc` → `d3886fd1` → `41705cba`). Brought over as:

| File | How |
|---|---|
| `backend/app/theta.py` | **byte-identical copy** (md5 `923fc298…`, 296 lines) |
| `backend/tests/test_theta.py` | byte-identical copy (15 tests, all pass here) |
| `backend/app/payloads.py` | v1's two hunks applied verbatim — `payloads.py` is now **byte-identical to v1's** |
| `backend/app/cache.py` | `SCHEMA_VERSION` 7 → **8**, v2-local |

The schema bump is not optional and is not v1's: the same source rows now
produce a **different payload** (`row.theta`, `summary.thetaBasis`). Without it a
v7 cache keeps serving theta-less summaries and the screen draws a column of em
dashes with no error anywhere — this repo's recurring silent-staleness failure.

**v1 did NOT bump it** (braveworld is still at `SCHEMA_VERSION = 7`; checked
2026-08-14). It gets away with it because its key also carries the source-data
hash and the as-of date, so the next morning's bake misses the old entry anyway —
but any host that re-reads the SAME day's data from a pre-theta cache serves the
column empty. That is a latent v1 defect, reported here and **not** fixed there
(this tree may not write to braveworld). It is also why the two `cache.py` files
now differ: this is a deliberate divergence, not drift.

Every convention behind the numbers is in `theta.py`'s own docstring. Nothing was
re-derived on the frontend (§16): `perDv01` and `beBp` arrive finished.

### The cache directory needed no edit

The prompt called for pointing the cache inside `sauron-v2/`. It already is:
`app/cache.py` derives it as `Path(__file__).resolve().parent.parent / ".cache"`,
so in this copy it resolves to `sauron-v2/backend/.cache`. The same is true of
every other path in the backend — `POLICY_PATH` and `irs_pricer.config.DATA_DIR`
are both `__file__`-relative and land inside `sauron-v2/` by construction.
Verified, not assumed.

## The ported engine is frozen

The bootstrap / discount-factor / forward / CD-IRS code arrived in v1 under a
provenance header marked do-not-modify. **That marking carries into v2 unchanged.**
The known bootstrap residual (up to ~0.25bp on swap tenors, worst at 3Y) is accepted
and documented; it is not a v2 defect and not this session's to chase. If a number
looks wrong, report it — do not fix it here.

## Running it

```powershell
powershell -ExecutionPolicy Bypass -File backend\serve.ps1          # 공개 서비스용
powershell -ExecutionPolicy Bypass -File backend\serve.ps1 -Local   # 개발·테스트용
```

`-Local` 은 2026-08-20 배포 준비에서 생겼다. 배포되면 :8200 이 Tailscale Funnel
로 공개되고, 그때부터 "포트가 열려 있다" 는 사실은 **내가 띄운 개발 백엔드**일
수도 **사람들이 쓰고 있는 라이브 서비스**일 수도 있다. v1 은 그 구별을 못 해서
라이브에 대고 테스트를 돌렸다.

`-Local` 로 뜬 프로세스만 `backend/.cache/dev-backend.json` 에 자기 PID 를
남기고(`app/dev_marker.py`), 백엔드 테스트는 그 쪽지의 PID 가 실제로 그 포트를
듣고 있을 때만 진행한다(`tests/_live_backend.py`). 아니면 **skip 이 아니라
수집 단계 에러**로 거절한다. 테스트가 말을 걸 주소는 `SAURON_TEST_BASE` 로
바꾼다 — 하드코딩된 포트는 더 이상 없다.

### 아침 데이터 갱신 — 스냅샷 백엔드의 하루 [2026-09-22]

`app/main.py` 는 **모듈 import 때 데이터셋을 한 번 읽고** `_bases`·`_curves`·
`_events`·`_volatility`·`_forwards`·`_surface` 를 전역에 붙든다. 다시 읽는 자리가
없다. 그래서 백엔드가 뜬 뒤에 도착한 종가는 **재기동 전까지 화면에 안 나온다**.

증상이 화면마다 다르다는 것이 이 병의 얼굴이다:

| 화면 | 읽는 방식 | 늦는가 |
|---|---|---|
| Main · Backtest | 기동 스냅샷(`_dataset`) | **늦는다** |
| Strategy 계열 | 요청마다 SQL 라이브 | 안 늦는다 |

그래서 「rateslab 이 이상하다」가 접속 문제로 오독되기 쉽다 — 접속은 멀쩡하고
한 화면만 하루 늦는다.

#### 무엇이 열흘을 먹었는가

`refresh.ps1` 은 「SQL 이 백엔드보다 새로울 때만 재기동」한다. 아침 순서가 이렇다:

    07:37  PC 부팅 → SauronV2Backend 가 **그때의** SQL 을 읽는다
    07:42  refresh → SQL 과 서버가 같다 → 「이미 최신이에요」로 종료
    그 뒤   전영업일 종가가 SQL 에 도착 → 아무도 다시 안 본다

둘이 같은 것은 참이었다. 거짓은 그 상태를 **«최신»이라 부른 것**이다 — SQL 자신이
기대 전영업일을 안 들고 있었다. `refresh.log` 에 그 한 줄이 **2026-09-10 부터
09-22 까지 열 번의 아침** 연속으로 찍혀 있다. 부수로 확인된 것 둘:

- `-WaitMinutes 60` 의 대기 루프는 **한 번도 돈 적이 없다.** 판정 두 줄이 ISO
  날짜 문자열에 대해 완전하고 배타적이라 첫 바퀴에서 늘 exit/break 했다 —
  `Start-Sleep 300` 은 도달 불가능한 코드였다.
- 비교에 쓰던 `irs_close_rows()[-1]` 은 테이블 raw MAX 라서 **전일종가 컷과 엑셀
  병합을 안 지난다.** 서버가 서빙하는 asof 와 다를 수 있다.

#### 지금의 설계

판정은 `scripts/check_close.py` 가 한다(파이썬엔 시험이 있다 —
`tests/test_refresh_decide.py`). 다섯 상태고, 새로 생긴 것은 **`waiting`** 이다.

| verdict | 뜻 | exit |
|---|---|---|
| `error` | 서빙될 날짜를 못 구했다(DB·엑셀 둘 다) — 재기동 금지 | 1 |
| `start` | 백엔드가 안 떠 있다 | – |
| `restart` | 재기동하면 날짜가 앞선다 | – |
| `waiting` | 서버는 SQL 만큼 최신인데 **SQL 이 기대 전영업일을 안 들고 있다** | 2 |
| `current` | 기대 전영업일까지 서빙 중 | 0 |

비교하는 두 수는 같은 계산에서 뽑는다 — `wouldServe` 는 서버가 부팅 때 지나는
그 로더(`load_dataset_merged`)의 asof 다. 기다림은 스크립트가 아니라 **스케줄러의
반복 트리거**가 한다(`refresh_schedule.ps1`). `refresh.ps1` 은 단발이다 —
`MultipleInstances=IgnoreNew` 아래서 오래 도는 인스턴스는 다음 회차를 막는다.

    powershell -File backend/refresh_schedule.ps1            # 지금 상태만
    powershell -File backend/refresh_schedule.ps1 -Apply     # 30분마다 12시간
    powershell -File backend/refresh.ps1 -DryRun             # 판정만, 안 죽인다

#### 출처가 둘이고 하나가 섰다 + 유령 휴일 행 [2026-10-07]

[OWNER — "이거 왜 종가업데이트 안 되냐"] 화면이 10-05 를 「IRS 종가」라 부르고
장부는 10-02 를 마지막 종가라 적고 있었다. 한 화면에 날짜가 둘이었고, 원인도
둘이었다.

**(1) `mkt_irs_close` 가 10-06 을 안 들고 있었다.** 배관은 멀쩡했다 —
`refresh.log` 가 `sql=absent -> waiting` 을 정직하게 찍고 30분마다 다시 보고
있었다. 그런데 **같은 서버의 `imx_data.timeseries` 종합ALL 에는 10-06 이 이미
와 있었다**(2년 3.87 · 5년 4.085 · 10년 4.18). 「종가가 안 왔다」가 아니라
**출처가 둘인데 우리가 보는 쪽만 섰다** — 2026-09-22 국고 전수조사에서 밟은 그
모양이다.

고른 근거는 대조다: 겹친 **34,528칸에서 불일치 14건(0.04%)·최대 1.00bp**, 그리고
그 14건이 **전부 8Y(8건)·9Y(6건)** — 커브에서 가장 얇은 두 점이다. 나머지 11테너는
2,656일 전부 자릿수까지 같다. ★처음엔 2Y·5Y·10Y 셋만 재서 「1,308칸 0건」이라
적었다 — **골라 쟨 수였고**, 같은 날 SQL 자신의 10-06 행이 도착했을 때 8Y 가
0.25bp 어긋나 드러났다. 그래서 하루가 통째로 없을 때 **종합ALL 을 엑셀보다 먼저** 쓴다
(`dataset.merge_expected_close`, `source="sql+imx-day"`). 단서 둘:

- **과거사는 안 갈아탄다.** `mysqldb.imx_irs_day` 는 **하루만** 읽는다.
- **둘을 한 날에 섞지 않는다.** 종합ALL 에 1D(콜)·3M(CD91)이 없는데 그 둘을
  엑셀에서 끌어오면 「엑셀이 섞이면 source 가 반드시 말한다」를 라벨 하나로 못
  적는다. 그 날의 1D·3M 칸은 **빈칸**이고 경고가 노드 이름을 말한다 — ⚠ 다만
  **화면이 em dash 를 보이는 것은 아니다**(2026-10-07 라이브 실측): `derive.value_at`
  이 「없으면 직전 종가」로 이어 붙여서 1D 가 3.113·d1 0.0 으로 찍혔다. 이 테이블에
  1D 빈칸이 9건·3M 이 10건 이미 있어 원래부터 있던 동작이고, 이 변경은 그것을 가장
  최근 날로 옮긴다. 같은 계열의 어제 값이 40~61bp 다른 계열의 오늘 값보다 낫다는
  판단은 그대로다. **열린 결정**: 이어 붙인 칸임을 화면이 말해야 하는가. imx 의
  `CD 91일물` 은 `cd_rate` 와 **다른 계열**이기도 하다(440칸 중 331칸 불일치·
  최대 40bp) — 1D 가 엑셀과 다른 계열인 것과 같은 함정이라 같은 답을 썼다.

**(2) 휴일에 유령 행이 있었다.** 2026-10-05(개천절 대체공휴일) 행의 IRS 13칼럼이
10-02 와 **한 자리까지 같았다** — 전영업일 커브의 복사본이다. 역사 전체에 12개,
종합ALL 쪽에도 9개 있다. 그래서 컷은 출처별이 아니라 공통 관문
`dataset._finalize` 에 뒀다(전일종가 컷 바로 다음). 그 행이 `asof` 가 되면
화면이 장이 쉰 날을 「종가」라 부르고, 영업일만 걷는 장부와 날짜가 갈리고,
수익률 0 인 가짜 거래일이 역사에 낀다.

⚠ **지연 칩은 안 깨져 있었다.** `staleness.py` 가 영업일로 세므로 asof 가
10-02 든 10-05 든 「덜 센 영업일」은 하나다 — 9-22 메모의 「칩 자체는
정직했다」가 여기서도 유효하다. 고친 것은 날짜가 가리키는 **날**이고 숫자가
아니다.

아침 로그가 이제 둘을 나란히 적는다 — `sql=absent imx=full` 이 한 줄에 있으면
다음 사람이 「안 왔다」와 「우리 쪽만 섰다」를 구별한다.

    today: 2026-10-07   expected: 2026-10-06
    sql: absent   imx: full(13)   xlsx: stale 2026-08-19
    wouldServe: 2026-10-06  (source=sql+imx-day)

#### ⚠ PowerShell 5.1 함정 다섯 (전부 실측으로 밟았다)

1. **`.ps1` 은 BOM 있는 UTF-8 이어야 한다.** 없으면 5.1 이 ANSI(cp949)로 읽어
   한글 문자열의 인용이 깨지고, `refresh_schedule.ps1` 에서는 그 탓에 `-Apply`
   **가드 블록이 통째로 무력화됐다**(본문이 코드가 아니라 텍스트로 출력되고 실행이
   아래로 흘렀다). 그래서 바꾸는 코드를 `if ($Apply)` **안쪽**에 둔다 — 가드가
   깨지면 변경도 같이 죽는다.
2. **`Parser::ParseFile` 의 «parse OK» 는 헛초록일 수 있다.** `(if (...) {...}
   else {...})` 는 5.1 에 없는 if-식인데 파서가 그걸 **명령 이름 `if`** 로 읽어
   통과시킨다. 런타임에 CommandNotFound 로 죽는다.
3. **`$ErrorActionPreference="Stop"` + 네이티브 exe 의 stderr = 종료 오류.** 5.1 은
   리다이렉트한 stderr 의 각 줄을 ErrorRecord 로 싸므로, 파이썬 로거가 `[dataset] …`
   경고를 쓰는 것만으로 호출이 **던진다**. `Get-Verdict` 안에서 `Continue` 로 가린다.
   옛 `Get-SqlAsof` 가 안 밟은 것은 `python -c` 가 stderr 를 안 썼기 때문이다.
4. **`--served "$x"` 가 아니라 `--served=$x`.** `$x` 가 빈 문자열이면 5.1 이
   네이티브 exe 에 넘기는 **빈 인자를 떨어뜨려** argparse 가 usage 로 죽는다.
   하필 「백엔드가 안 떠 있다」가 그 경로였다.
5. **네이티브 stdout 의 한글은 `[Console]::OutputEncoding` 으로 디코드된다**(기본
   cp949). 그래서 **손으로 돌리면 멀쩡하고 스케줄러가 돌리면 깨진다** — 태스크는
   `conhost --headless` 밑이라 콘솔 인코딩이 다르다. 첫 자동 회차(08:30)의 판정
   문장이 `湲곕? ?꾩쁺?낆씪源뚯? …` 로 찍혀서 잡았다. `Get-Verdict` 가 호출 전후로
   UTF-8 을 걸고 되돌린다. ★JSON 키·날짜·verdict 는 ASCII 라 **판정 자체는 맞았다**
   — 「기계가 읽는 것을 ASCII 로, 사람이 읽는 문장을 따로」 둔 설계가 그걸 버텼다.

그리고 `Stop-ScheduledTask` 로는 uvicorn 이 안 죽는다 — 리스너 PID 를 직접 잡는다
(`refresh.ps1` 머리에 실측 근거).

### 환경변수

| 이름 | 읽는 곳 | 없으면 |
|---|---|---|
| `BW_MYSQL_HOST/PORT/USER/PASSWORD/DB` | `app/mysqldb.py` | SQL 을 읽는 순간 `MissingCredentials` 로 죽는다. 기본값 없음 (2026-08-20) |
| `ECOS_API_KEY` | `app/ecos.py` | 조달 기준의 **기준금리**를 못 가져온다 → base 가 실패, 화면은 콜금리로 안내. 기본값 없음 (2026-08-20) |
| `SAURON_ALLOWED_ORIGINS` | `app/cors.py` | 로컬 개발 오리진만 허용 |
| `SAURON_ALLOWED_ORIGIN_REGEX` | `app/cors.py` | `rateslab` 프로젝트의 vercel.app 프리뷰 패턴 |
| `SAURON_DEV_LOCAL` | `app/dev_marker.py` | 쪽지를 안 남긴다(=공개 서비스로 취급) |
| `SAURON_TEST_BASE` | `tests/_live_backend.py` | `http://127.0.0.1:8200` |

Never run braveworld's `gate.ps1` while v2 is working: its mode 1 demands `:8100`
be free, and its known orphan-uvicorn defect can leave a stray process holding a
port that neither app can then reclaim.
