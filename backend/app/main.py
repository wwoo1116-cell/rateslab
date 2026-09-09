"""braveworld backend — KRW IRS monitor API, plus the scenario simulation.

Stage-1 wall summary + stage-2 full series. All derived series (spreads,
flies) are computed here, never in the browser (design spec §4).

Forwards / curve bootstrapping are intentionally ABSENT: the module list to
port from the frozen engine is [TBD — owner]. /api/forwards is a stub that
documents the gate.

ONE SERVICE, TWO SURFACES [OWNER, 2026-08-07]. The simulation used to be its
own project (simulation_project, :8200/:3200) with its own FastAPI app. The
owner directed that it become a TAB on this monitor rather than a second
site, so `irs_pricer/` moved into this backend and its four routers are
registered here alongside this module's own. simulation_project stays alive
as the comparison copy until the merged surface has been seen working.

The route sets were disjoint except for `/api/health`, which both apps
defined and which is merged below into one response carrying both halves.

What this cost, and why it is written down: this repo's guardrail said
"braveworld has no database — it reads one xlsx", and the simulation's own
pyproject dropped sqlalchemy/pymysql/alembic on the way over for the same
reason. That guardrail is now on borrowed time — the owner is moving both
halves onto MySQL once the middle-office account arrives. Nothing here
depends on a database yet; the loaders that MySQL will replace are left
whole so the seam stays where it is (see CLAUDE.md).
"""

from __future__ import annotations

import logging
import logging.config

# Configured before anything else imports a logger, so `irs_pricer`'s DEBUG
# lines are not swallowed by the root default. Carried over from the
# simulation's app.py, which did the same thing at the same point and for the
# same reason; it also promotes this module's own INFO logging, which used to
# fall below the unconfigured root's WARNING threshold — the cache's LOUD
# recompute notice among them.
logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"default": {"format": "%(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "default"}},
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {"irs_pricer": {"level": "DEBUG"}},
})

import datetime as dt
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from irs_pricer.api.routers import credit_curve, market_data, positions, simulate
from irs_pricer.config import DATA_DIR
from irs_pricer.core import data_watch, ttl_cache
from irs_pricer.core.errors import CurveBootstrapError
from irs_pricer.engine import curve_cache
from irs_pricer.loaders import irsdata as irsdata_loader
from irs_pricer.services.simulation import bond_roll

from . import instruments as instruments_mod
from . import calendar_cache
from . import df_cache
from . import mr as mr_mod
from . import mrbacktest as mrbt
from . import mrbook
from . import mrcarry as mrc
from . import mrdiag as mrd
from . import mrmetrics as mrm
from . import mrregime as mrg
from . import mrseries as mrs
from . import payloads
from . import rv as rv_mod
from . import schedule_cache
# 백테스트 엔진은 이제 `mixedbook` 을 통해서만 부른다 — 스왑만 있는 북은 저쪽이
# 그대로 위임한다. 여기서 `run_backtest` 를 직접 들고 있으면 «스왑 전용 길» 이
# 하나 더 열려 있는 셈이고, 그 길로 들어간 북에는 `kind` 가 안 붙는다.
from . import backtest as bt_engine
from .backtest import BacktestError
from . import futures
from . import mixedbook
from .cache import cached
from .cors import allowed_origin_regex, allowed_origins
from . import dev_marker
from . import cashbond
from . import creditmatrix
from . import funding
from .curves import TENOR_T, build_basis_curves
from .dataset import load_dataset_merged
from .derive import basis_dates, derived_ids, ohlc_buckets, series_history
from .theta import theta_table
from .dv01 import build_dv01_table, pv01
from .events import detect_event_clusters
from .forwards import forwards_payload
from .issuance import IssuanceUnavailable, build as build_issuance, day_detail as issuance_day, months_from
from .labmacro import MacroUnavailable, build as build_macro
from .labscenario import build_anchors
from .policy import load_base_rate_auto, policy_step, MPC_DATES
from .staleness import dataset_freshness
from .surface import surface_payload
from .surface3d import build_surface3d, surface3d_watermark
from .universe import build_universe, universe_series
from .volatility import volatility_payload

# `DATA_PATH`(data/irsdata.xlsx)는 없어졌다 [OWNER, 2026-08-07] — IRS 종가는
# 이제 MySQL 에서 온다. 파일 자체는 남아 있고 정적 트리 빌드와 테스트가 계속
# 읽지만, **서버는 더 이상 열지 않는다**. 상수를 지운 이유는 남겨 두면 다음
# 사람이 "여기가 출처" 라고 읽기 때문이다.
#
# 기준금리는 2026-09-01 부터 ECOS 다 [OWNER — "굳이 엑셀을 참고하는게 아니라
# ECOS API에서 참조해오는게 편하잖아"]. 이 경로는 이제 폴백이다: 키·망·캐시가
# 전부 없을 때만 읽히고, 그때는 `policy_step` 의 warnings 가 그 사실을 말한다.
POLICY_PATH = Path(__file__).resolve().parents[2] / "data" / "bokbaserate.xlsx"


#: 시뮬 채권 롤다운 레인의 커브 공급자 [OWNER, 2026-08-25 — 엔진 단위 분리].
#: 시뮬(irs_pricer)은 SQL 을 모른다는 계층 규칙 때문에 app 이 여기서 민평
#: 최신 커브를 먹인다. `creditmatrix.load()` 는 워터마크 캐시라 호출마다
#: 싸고, 실패는 bond_roll 쪽이 삼켜 «롤 0 + provenance» 로 강등한다.
_ROLL_SECTOR_TYPES: dict[str, str] = {
    "국채": "KTB",
    "은행채": "BD",
    "특은채": "KDB",
    "카드채": "CARD",
    "회사채": "CB1",
}


def _bond_sector_curves() -> dict[str, list[tuple[float, float]]]:
    m = creditmatrix.load()
    i = len(m.dates) - 1
    out: dict[str, list[tuple[float, float]]] = {}
    for sector, bond_type in _ROLL_SECTOR_TYPES.items():
        pts = creditmatrix.curve_points(m, bond_type, i)
        if pts:
            out[sector] = pts
    return out


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Memoises the pure curve bootstrap that every simulation pricing/risk path
    # funnels through — see irs_pricer/engine/curve_cache.py for the
    # measurements (1409.7s -> 118.6s on a full book). IRS_PRICER_CURVE_CACHE=0
    # skips installation: the operational escape hatch, and the A/B mechanism
    # for byte-identity evidence against the frozen engine.
    #
    # This is the SIMULATION's cache and is unrelated to app/cache.py, which
    # persists this module's own forwards payload to disk. Two caches,
    # two lifetimes, no shared state — the name is the only thing they share.
    if os.environ.get(curve_cache.ENV_FLAG, "1") == "0":
        logging.getLogger("irs_pricer").warning(
            "curve_cache NOT installed (%s=0) — engine runs unmemoized", curve_cache.ENV_FLAG
        )
        curve_cache.uninstall()
    else:
        curve_cache.install()
    # The BACKTEST's equivalent, and a separate cache with a separate switch —
    # `BW_SCHEDULE_CACHE=0` (see app/schedule_cache.py). It memoises the ISDA
    # schedule build, which the reference book was doing 39,804 times to produce
    # 6 distinct schedules. Installed here rather than at import so the default
    # for tests and scripts stays the unmemoized engine, exactly as
    # curve_cache's does; `install()` reads the flag itself.
    schedule_cache.install()
    # MEMO-1C: the residual the schedule memo could not reach — `select_fixing`
    # walking back to F(R). 515,473 calls over 40 distinct inputs on the
    # reference book (app/calendar_cache.py). `BW_CALENDAR_CACHE=0` disables it.
    calendar_cache.install()
    # MEMO-2: the scalar discount-factor lookup, memoized PER CURVE. It was
    # 74% of simulation cost and ~4/5 of that is numpy dispatch, not
    # arithmetic; the same (curve, t) pair is asked 20-98x per run.
    # Installs on BOTH copies of the port (backtest + simulation) — they are
    # different function objects. `BW_DF_CACHE=0` disables it.
    df_cache.install()
    # 채권 롤다운 커브 공급자 — 위 `_bond_sector_curves` 주석 참조. 여기(기동)
    # 서 등록해야 테스트·스크립트의 기본이 «미등록 = 롤 레인 꺼짐»으로 남는다
    # (curve_cache 들과 같은 원칙).
    bond_roll.set_sector_curve_provider(_bond_sector_curves)
    # 시뮬 IRS 스냅샷 = 이 앱의 병합 데이터셋 **그 인스턴스** [OWNER,
    # 2026-08-25 — 감사록 F2]. 시뮬의 DATA_DIR 워크북 복사가 멈춰(08-19)
    # 스왑이 «당일 IRS 호가 없음»으로 제외되던 병의 근본 수정 — 백테스트와
    # 시뮬이 같은 데이터 한 벌(SQL 우선)을 본다. 미주입(테스트·스크립트)은
    # 종전 워크북 경로 그대로다.
    irsdata_loader.set_dataset(_dataset)
    logging.getLogger("irs_pricer").info("simulation data dir: %s", DATA_DIR)
    # 개발용으로 띄웠다는 쪽지(app/dev_marker.py). `SAURON_DEV_LOCAL=1` 없이는
    # 아무것도 안 쓴다 — Funnel 로 공개된 라이브 인스턴스는 쪽지를 안 남기고,
    # 그래서 백엔드 테스트가 그것을 자기 것으로 착각하지 못한다.
    dev_marker.write(dev_marker.listening_port())
    try:
        yield
    finally:
        dev_marker.clear()


app = FastAPI(title="braveworld", version="0.1.0", lifespan=lifespan)

# This module's own routes. They used to hang off `@app.get` directly; they are
# on a router now for one reason — `include_router` is how the simulation's
# four routers arrive, and routes registered both ways in one file read as two
# conventions fighting. Same paths, same handlers, same order.
router = APIRouter()


class _DataWatchMiddleware(BaseHTTPMiddleware):
    """Clear the simulation's derived caches when its data folder changed.

    Carried over from the simulation's app.py. The source cleared these inside
    its upload endpoint; it sits in middleware rather than in each router so no
    future endpoint can forget it. Only stat() calls — the check never opens a
    workbook.

    It does NOT cover this module's own payloads. Those are bound to the
    dataset loaded once at import (below) and keyed by file hash in
    app/cache.py; a refresh of irsdata.xlsx still needs a restart, exactly as
    before. Nothing about the merge changed that, and pretending otherwise
    would be the silent-staleness defect this project keeps having.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/"):
            data_watch.check()
        return await call_next(request)


class _UnhandledErrorMiddleware(BaseHTTPMiddleware):
    """Last-resort net for exception types no registered handler covers.

    A KeyError/TypeError/IndexError, or a numpy/scipy error, otherwise escapes
    to ServerErrorMiddleware and comes back as a bare 500 with no
    Access-Control-Allow-Origin — the browser then blames CORS and the client
    reports "cannot reach the server" though the server answered.

    This has to be middleware rather than @app.exception_handler(Exception):
    Starlette special-cases a handler keyed `Exception` (or 500) and hoists it
    into ServerErrorMiddleware, which sits *outside* CORSMiddleware. Middleware
    can sit inside it; that handler never can.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001 — being the last net is the point
            logging.getLogger("irs_pricer").exception("Unhandled error")
            return JSONResponse(status_code=500, content={"detail": f"서버 오류: {exc}"})


# ORDER IS LOAD-BEARING, and reads backwards: add_middleware() does
# user_middleware.insert(0, ...) and build_middleware_stack() wraps the list in
# reverse, so the LAST middleware added ends up OUTERMOST. CORS must therefore
# be added last to stay outside the catch-all — otherwise the catch-all's 500
# goes out without CORS headers and re-creates the very bug it exists to
# prevent. Resulting nesting, outside in:
#
#     CORS -> unhandled-error -> data-watch -> gzip -> routes
#
# GZip innermost is the one deviation from either source's order, and it is the
# right end: it compresses route responses, which is all it ever did here, and
# the error middleware's JSON payloads are a line long.

# Every response left here uncompressed (measured, Pass E: no Content-Encoding
# on any endpoint). These payloads are long lists of short numeric records and
# compress ~6x; the stage-2 series fetch, the one the reader actually waits on
# when opening a popup, goes 103 KB -> 17 KB. minimum_size skips the small
# ones, where the header costs more than it saves (/api/health is 156 bytes).
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(_DataWatchMiddleware)
app.add_middleware(_UnhandledErrorMiddleware)

app.add_middleware(
    CORSMiddleware,
    # V2-LOCAL EDIT 1 of 5 — see ../../BACKEND.md.
    # This is sauron-v2's OWN COPY, served on :8200 for a frontend on :3200.
    # The :3100 origins stay because the copy must still be runnable in
    # isolation against v1's port layout while the two run side by side; the
    # comment below is v1's and is kept for provenance.
    #
    # (v1's note) braveworld runs on :3100/:8100 — :3000/:8000 belong to the
    # frozen krw-fi-pms deployment and must stay untouched.
    #
    # 2026-08-20 (배포 준비): 목록이 `app/cors.py` 로 나갔다. 배포되면 프런트가
    # Vercel 에 있어 출처가 달라지고, 프리뷰 주소는 커밋마다 바뀌어 목록에 적을
    # 수가 없다. 값은 환경변수로 들어오고 규칙은 tests/test_cors_origins.py 가
    # 고정한다. 전면 허용(`*`)은 하지 않는다 — 이 API 는 인증이 없다.
    allow_origins=allowed_origins(),
    allow_origin_regex=allowed_origin_regex(),
    # POST joins GET for the simulation's three POST routes (/api/simulate,
    # /api/credit-curve/series, /api/market-data/live). GET-only would have
    # failed them at the preflight, before any handler ran.
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(CurveBootstrapError)
async def curve_bootstrap_error_handler(request: Request, exc: CurveBootstrapError) -> JSONResponse:
    """Every simulation endpoint routes through build_curve() at some point —
    handling this centrally means a bad market rate (corrupt snapshot, typo'd
    quote) comes back as one clean 400 everywhere instead of an opaque 500."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError) -> JSONResponse:
    """Catch unhandled RuntimeErrors before they escape as bare 500s without
    CORS headers. Same caveat as above — this MUST be a specific subclass,
    never bare `Exception`, or Starlette pulls it out of ExceptionMiddleware
    and puts it in ServerErrorMiddleware *outside* CORSMiddleware."""
    logging.getLogger("irs_pricer").exception("Unhandled runtime error")
    return JSONResponse(status_code=500, content={"detail": f"계산 오류: {exc}"})

# IRS 종가의 출처는 **MySQL** 이다 [OWNER, 2026-08-07 — "무조건 SQL 쪽이 정답임"].
#
# `data/irsdata.xlsx` 는 지웠거나 옮기지 않았다 — 백테스트의 정적 트리 빌드
# (scripts/build_static.py)와 테스트가 아직 그 파일을 읽고, 대조 스크립트
# (scripts/check_mysql.py)도 그것을 기준으로 두 출처를 비교한다. 서버가 읽는
# 것만 옮겼다.
#
# 대조 근거는 dataset.py 의 `load_dataset_sql` 주석에 있다: 3M~10Y 는 2,616일이
# 소수점 끝까지 일치했고, 1D(콜금리)만 80.8% 어긋났다(다른 계열). 오너가 SQL 을
# 정답으로 정했으므로 1D 도 그대로 받는다 — 과거 짧은 끝 커브가 달라지고 그건
# 의도된 변경이다.
#
# 2026-08-11 부터는 **병합 로더**다 [OWNER — 아침 자동 굽기]: SQL 이 기대
# 전영업일을 온전히 들고 있으면 위와 동작이 같고, 1D 만 비면 그 칸을, 하루가
# 통째로 없으면 그 하루를 엑셀(irsdata.xlsx)에서 보충한다. 정적 빌드
# (scripts/build_static.py)도 같은 로더를 지난다 — 한쪽만 병합을 알면 폴백한
# 날마다 static-agreement 가 갈라진다.
_dataset = load_dataset_merged()
_bases = basis_dates(_dataset)
# The policy step, resolved ONCE against this dataset's as-of date — the carry
# bound depends on both files, so it cannot be decided by policy.py alone (see
# its docstring). Two dozen corners; it rides in the summary rather than
# earning an endpoint, because every %-unit chart needs it and the summary is
# already the first thing fetched.
_policy = policy_step(load_base_rate_auto(POLICY_PATH), _dataset.asof)
_curves = build_basis_curves(_dataset)
_events = detect_event_clusters(_dataset)
_volatility = volatility_payload(_dataset, _bases)
_dv01_table = build_dv01_table(_curves["now"], derived_ids)
# The own-history distributions are the slow part (§D) — bootstrap each
# historical curve once and reprice all forwards (~13s) — over a file that
# changes once a day. Persist them keyed by the data-file hash; recompute only
# when the data changes (loudly logged).
# 바이트가 없으므로 **테이블 워터마크**가 캐시 키다 (cache.sql_data_hash) —
# CLAUDE.md 가 이 이동에서 잊지 말라고 못 박은 자리다. 키는 병합 로더가 만든다:
# 순수 SQL 이면 워터마크 그대로, 엑셀이 섞이면 병합분 지문이 붙는다.
_data_hash = _dataset.data_key
_forwards = cached("forwards", _data_hash, lambda: forwards_payload(_dataset, _curves))
# 라고 할 때 살걸: a 20-day event replay plus ~2 valuations per line — a
# couple of seconds over a file that changes once a day, so it caches the
# same way forwards does.
# `_regret` 이 여기 있었다 — 은퇴 [OWNER, 2026-08-20]. 디스크에 남은 v7
# `regret` 캐시 파일은 이제 아무도 열지 않는다. 모양이 바뀐 게 아니라
# 사라진 것이라 SCHEMA_VERSION 은 그대로다.
# 커브 표면(Lab). 주별로 솎은 격자 하나라 굽는 값이 싸지만, 캐시에 태우는
# 것은 값 때문이 아니라 **굽기와 서버가 같은 페이로드를 내도록** 하기
# 위해서다 — forwards 와 같은 자리, 같은 키.
# FORWARD-PORT from braveworld (2026-08-14, `app/surface.py` 바이트 동일).
_surface = cached("surface", _data_hash, lambda: surface_payload(_dataset))
# Two things that used to sit here are gone, both from this region of the
# popup: the curve heatmap (its 어제-column question was answered faster by
# the table, and daily resolution over ten years was noise) and carry & roll
# after it (see DESIGN — removed for a repeated figure and components that
# did not sum). `forwards` is the only cached payload now.


@router.get("/api/health")
def health() -> dict:
    """Liveness for both halves of the service.

    The monitor's five fields are FIRST and unchanged: the frontend reads them
    (lib/api.ts), and test_static_agreement pins `asof` against the static
    manifest. The simulation's app.py had its own /api/health — the only route
    the two apps collided on — and its fields are appended rather than merged
    into the ones above, because they answer a different question: is the data
    folder there, and are the caches doing anything.

    It also doubles as the cheapest way to confirm the event loop is free: if
    this doesn't answer instantly while a simulation is computing, something
    heavy is back on the loop again.
    """
    return {
        # freshness recomputed per request (its age advances with the wall clock
        # while the file does not) — see staleness.py.
        "status": "ok",
        "asof": _dataset.asof.isoformat(),
        "rows": len(_dataset.dates),
        "missingNodes": _dataset.missing_nodes,
        # 어디서 온 데이터인가 — "sql" 이 아니면 프론트가 엑셀 연결 칩을 단다
        # [OWNER, 2026-08-11 "엑셀데이터에 연결되어있다고 말은 해줘야 해"].
        "source": _dataset.source,
        "freshness": dataset_freshness(_dataset.asof),
        "simulation": {
            "dataDir": str(DATA_DIR),
            "dataPresent": DATA_DIR.is_dir(),
            "curveCache": curve_cache.stats(),
            "ttlCache": ttl_cache.stats(),
        },
    }


@router.get("/api/wall/summary")
def wall_summary() -> dict:
    return payloads.wall_summary(_dataset, _bases, _events, _policy)


@router.get("/api/series/{series_id}")
def series_detail(series_id: str, res: str = "full", interval: str | None = None) -> dict:
    # Content comes from payloads.py so the static build cannot drift from this
    # (Pass B). All that is left here is turning an unknown id into a 404.
    try:
        return payloads.series_detail(_dataset, series_id, res, interval)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown series {series_id}")


@router.get("/api/universe")
def universe() -> dict:
    """V2-LOCAL route. The expanded universe — 국고 현물, 크레딧 스프레드, 본드스왑
    스프레드, 국채선물 — read from live tables. Cached like the other payloads: the
    inputs only move once a day."""
    return cached("universe", _dataset.data_key, build_universe)


@router.get("/api/universe/series/{series_id:path}")
def universe_series_route(series_id: str, interval: str | None = None) -> dict:
    """V2-LOCAL. History for one expanded-universe row, for the preview pane.

    `interval=w|m` returns weekly/monthly OHLC bars instead of daily points,
    the same shape `/api/series/{id}` returns and built by the SAME function
    (`derive.ohlc_buckets`). The chart type is a global reader preference, so a
    route that could not answer it would leave 국고/크레딧/선물 rows drawing a
    line while the control said 주봉 — the screen would be lying about which
    series it is showing. Aggregation stays on this side (§16): the browser
    never buckets a series.
    """
    try:
        body = universe_series(series_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown universe series {series_id}")
    if interval in ("w", "m"):
        pairs = [(p["t"], p["v"]) for p in body.get("points", [])]
        return {"id": body["id"], "unit": body["unit"], "interval": interval,
                "bars": ohlc_buckets(pairs, interval)}
    return body


@router.get("/api/forwards")
def forwards() -> dict:
    return _forwards


@router.get("/api/surface")
def surface() -> dict:
    # 커브 표면 — 테너 × 날짜 × 금리 (Lab). 리더 입력 없음 → 통째로 굽힌다.
    return _surface


@router.get("/api/surface3d")
def surface3d() -> dict:
    """V2-LOCAL. Lab 3D 커브 표면 — 국고·크레딧·스왑 3풀, 1~10Y (surface3d.py).

    universe 처럼 라우트 안에서 게으르게 캐시한다 — SQL 이 절반이라 임포트
    시점(모듈 상수)에 태우면 기동이 DB 에 묶인다. 키는 dataset 워터마크 +
    credit_matrix 워터마크 둘 다다: universe 는 dataset 키만 쓰지만 이
    페이로드는 크레딧이 절반이라 크레딧 쪽 낡음도 잡아야 한다.
    """
    # 키의 마지막 조각은 **페이로드 판 번호**다 — 데이터 워터마크만으로는 코드가
    # 바뀐 것을 못 본다(실측 2026-08-18: 일별 전환 후 디스크 캐시가 주별을 그대로
    # 돌려줬다). 전역 SCHEMA 범프는 forwards 등 남의 캐시까지 태우므로 국소로 적는다.
    key = f"{_dataset.data_key}|{surface3d_watermark()}|p5-tenors"
    return cached("surface3d", key, lambda: build_surface3d(_dataset))


@router.get("/api/scenario/anchors")
def scenario_anchors() -> dict:
    """V2-LOCAL. Lab 시나리오가 오늘의 시장에 닿는 자리 (labscenario.py).

    캐시하지 않는다 — 포워드 par 금리 여덟 번이라 커브가 이미 서 있는 이 시점엔
    공짜다. 손잡이는 프런트가 돌리고 여기는 **앵커만** 답한다.

    기준금리는 `_policy` 에서 넘긴다. 이 모듈이 두 번째 사본을 만들면 `MPC_DATES`
    가 이미 겪은 «조용히 갈리는 사본» 이 하나 더 생긴다.
    """
    return build_anchors(_dataset, _curves, _policy.get("latest"))


@router.get("/api/scenario/macro")
def scenario_macro() -> dict:
    """V2-LOCAL. 모형이 딛고 선 거시 실측 — 한국은행 ECOS (labmacro.py).

    손잡이 셋(물가·갭·수출)이 무엇에 얹히는 값인지를 화면이 같이 보여주기 위한
    것이다. 캐시는 모듈이 진다(분기 계열이라 TTL 12시간).

    ECOS 가 죽어도 **화면은 서야 한다** — 시나리오의 본체는 구운 기저와 오늘의
    커브라 이 실측이 없어도 계산은 그대로다. 그래서 503 이 아니라 빈 목록을 주고
    화면이 그 자리에 이유를 적는다.
    """
    try:
        return build_macro()
    except MacroUnavailable as exc:
        logging.getLogger("app.main").warning("거시 실측 없음: %s", exc)
        return {"asof": None, "quarters": 0, "series": [], "notes": [str(exc)], "stale": True}


@router.get("/api/issuance/calendar")
def issuance_calendar(ym: str = "", months: int = 2) -> dict:
    """V2-LOCAL. 발행 캘린더 (issuance.py) — Lab 의 세 번째 세입자.

    `ym` 은 `YYYY-MM`, 비우면 오늘 달. 수집기가 CSV 를 새로 쓰면 mtime 이 캐시 키라
    다음 요청이 알아서 읽는다 — 서버를 건드릴 필요가 없다.

    금통위 날짜는 `policy.MPC_DATES` 가 준다. 그 목록은 `src/data/calendar.json` 의
    사본이고 둘의 일치는 테스트가 본다 — 이 모듈이 세 번째 사본을 만들지 않는다.
    """
    today = _dataset.asof
    try:
        y, m = (int(ym[:4]), int(ym[5:7])) if len(ym) >= 7 else (today.year, today.month)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{ym} 는 YYYY-MM 이 아니에요")
    span = months_from(y, m, max(1, min(6, months)))
    mpc = [d.isoformat() for d in MPC_DATES]
    try:
        return build_issuance(span, mpc)
    except IssuanceUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/issuance/day/{iso}")
def issuance_day_detail(iso: str) -> dict:
    """그날 하루 — 발행 종목 · 국고채 입찰(+응찰 강도) · 공개시장운영 · 금통위."""
    try:
        return issuance_day(iso, [d.isoformat() for d in MPC_DATES])
    except IssuanceUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/dv01/{series_id}")
def dv01(series_id: str) -> dict:
    # Per-leg DV01 + DV01-neutral notional ratio at the current curve (§B).
    # Forwards/vol/unknown ids get an empty block (kind null).
    return _dv01_table.get(series_id, payloads.empty_dv01(series_id))


@router.get("/api/backtest")
def backtest(
    positions: str = "",
    basis: str = funding.DEFAULT_BASIS,
    spreadBp: float = funding.DEFAULT_SPREAD_BP,
) -> dict:
    """Revalue a BOOK of positions daily and sum them (§backtest).

    `positions` is a `;`-separated list, one position per entry, each
    `id,direction,notional,entry[,exit]` — e.g.

        10Y,1,1e10,2025-07-30;3Y-10Y,1,5e9,2026-01-02,2026-05-01

    A query string rather than a POST body because every other route here is a
    GET and a backtest is a question, not a submission: this way a book is a
    URL somebody can paste to a colleague, which is the same property `?tile=`
    gives the rest of the product.

    LIVE ONLY, by design. Every other endpoint has a static twin under
    `frontend/public/api/**` that the deployed site serves; this one cannot,
    because the answer depends on inputs the reader chooses. Vercel runs the
    frontend and this backend runs behind it [OWNER, 2026-07-31], which is also
    what keeps §16 intact — the browser still computes nothing.

    스왑과 현금채권을 **한 북에** 담는다 [OWNER, 2026-08-21]. `id` 가 `CB:`/`ASW:`
    로 시작하면 채권 줄이다 — 같은 문자열이 시뮬레이션·모니터에서 뜻하는 것과
    같고(`instruments.kind_of`), 조달은 채권 줄이 있을 때만 읽힌다. 한 종류뿐인
    북은 종전 엔진에 그대로 위임되므로 답이 한 원도 달라지지 않는다
    (`app/mixedbook.py`).
    """
    if not positions.strip():
        raise HTTPException(status_code=422, detail="at least one position is required")

    parsed: list[mixedbook.MixedPosition] = []
    for raw in positions.split(";"):
        raw = raw.strip()
        if not raw:
            continue
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) not in (4, 5):
            raise HTTPException(
                status_code=422,
                detail=f"bad position {raw!r}: expected id,direction,notional,entry[,exit]",
            )
        try:
            parsed.append(
                mixedbook.MixedPosition(
                    series_id=parts[0],
                    direction=int(parts[1]),
                    notional=float(parts[2]),
                    entry=dt.date.fromisoformat(parts[3]),
                    exit=dt.date.fromisoformat(parts[4]) if len(parts) == 5 and parts[4] else None,
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"bad position {raw!r}: {exc}")

    # 민평은 **채권 줄이 있을 때만** 읽는다 — 스왑만 있는 북이 SQL 에 닿아야 할
    # 이유가 없고, 닿게 만들면 그 테이블이 죽은 날 스왑 백테스트까지 같이 죽는다.
    # 선물 종가도 같은 규율이다 [OWNER, 2026-08-25 — 선물·퓨처스왑 합류].
    spec = _funding_spec(basis, spreadBp)
    matrix = None
    if mixedbook.has_bond(parsed):
        try:
            matrix = creditmatrix.load()
        except creditmatrix.CreditMatrixError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    fut_data = None
    if mixedbook.has_futures(parsed):
        try:
            fut_data = futures.load()
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail=f"선물 종가를 읽지 못했습니다: {exc}"
            )

    try:
        # 일별 대사(`recon`)는 별도 패스다 — KRD 범프가 백테스트 본체보다
        # 비싸서 엔진 함수를 둘로 나눴다(backtest.book_recon doc). 응답은
        # 종전 그대로 한 덩어리에 `recon`만 얹는다.
        result = mixedbook.run_backtest(matrix, _dataset, parsed, spec, fut=fut_data)
        result["recon"] = mixedbook.book_recon(matrix, _dataset, parsed, spec, fut=fut_data)
        return result
    except (
        BacktestError,
        mixedbook.MixedBookError,
        cashbond.CashBondError,
        creditmatrix.CreditMatrixError,
        funding.FundingError,
        futures.FuturesError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ── Cash Bond [OWNER, 2026-08-14] ───────────────────────────────────────────
# Backtest 섹션의 여섯 번째 종목군. IRS 쪽 라우트와 같은 성질이다: 표는
# 서버가 다 계산해 내려보내고(§16), 백테스트는 **라이브 전용**이다 — 읽는
# 사람이 고르는 입력에 답이 달려 있어 정적 쌍둥이를 만들 수 없다.
#
# 민평은 워크북이 아니라 SQL 이다(`app/creditmatrix.py` 의 주석이 근거를
# 든다). 조달 기준의 기본이 v1(base)과 달리 call 인 것은 `app/funding.py`
# 의 V2 절 — infomax.기준금리 가 멈춰 있어 base 는 실패 상태다.


def _funding_spec(basis: str, spread_bp: float) -> funding.FundingSpec:
    try:
        return funding.FundingSpec(basis=basis, spread_bp=spread_bp).validated()
    except funding.FundingError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/api/settings/funding")
def funding_settings(
    basis: str = funding.DEFAULT_BASIS,
    spreadBp: float = funding.DEFAULT_SPREAD_BP,
) -> dict:
    """Setting 탭이 조달 기준을 고르고 그 결과를 미리 보는 자리.

    화면이 값을 저장하는 곳은 아니다 — 스펙은 URL 로 다니고 백테스트 요청에
    실려 온다. 이 라우트는 "그 스펙이 유효한가, 지금 몇 %인가" 만 답한다.
    base 가 게이트에 걸려 있으면 여기서 422 로 그 사실이 그대로 나간다 —
    폴백 없이 실패 상태를 보여주는 것이 규칙이다 [OWNER 2026-08-18].
    """
    spec = _funding_spec(basis, spreadBp)
    try:
        prov = funding.provenance(spec)
    except funding.FundingError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "options": [
            {"id": k, "label": v} for k, v in funding.BASIS_LABEL.items()
        ],
        "default": {"basis": funding.DEFAULT_BASIS, "spreadBp": funding.DEFAULT_SPREAD_BP},
        **prov,
    }


@router.get("/api/cashbond/instruments")
def cashbond_instruments() -> dict:
    """표의 행 전부, 세타까지 계산해서.

    조달을 안 받는다 [OWNER, 2026-08-14 — "채권에서는 조달 차감하지 않는 걸로"].
    세타가 쿠폰캐리 + 롤다운이라 Setting 과 무관해졌고, 안 쓰는 인자를 남겨 두면
    다음 사람이 그것이 쓰인다고 믿는다. 조달은 백테스트 쪽 라우트가 여전히 받는다.
    """
    try:
        # IRS 세타는 자산스왑 행이 자기 스왑 다리 몫으로 쓴다. 커브 하나로
        # 닫힌 식이라 매 요청 다시 계산해도 싸고(측정 33ms), 데이터가 갱신되면
        # 자동으로 따라온다 — 여기 캐시를 두면 그 갱신을 놓친다.
        irs_theta, _basis = theta_table(_dataset)
        return cashbond.instruments(creditmatrix.load(), _dataset, irs_theta)
    except (cashbond.CashBondError, creditmatrix.CreditMatrixError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/api/futures/series/{series_id}")
def futures_series(series_id: str, res: str = "full") -> dict:
    """국채선물·퓨처스왑 한 계열의 전 기간 — 백테스트 창의 진입 레벨과
    「종목 추이」 차트가 읽는다 [OWNER, 2026-08-25].

    `/api/cashbond/series/{id}` 와 같은 자리의 같은 규율이다: 현금채권도 선물도
    `/api/series/{id}`(IRS 카탈로그)에 없는 계열이라 자기 길을 가지되, **몸통은
    같은 `derive.series_history`** 를 쓴다. 사유와 단위 규약은 `futures.py::
    series_payload` 머리에 있다.
    """
    try:
        return futures.series_payload(futures.load(), _dataset, series_id, res)
    except futures.FuturesError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/api/cashbond/series/{series_id}")
def cashbond_series(series_id: str) -> dict:
    """한 종목의 전 기간 시계열 — 표를 눌렀을 때 뜨는 차트가 읽는다.

    IRS 쪽 `/api/series/{id}` 와 **같은 몸통**(`derive.series_history`)을 쓴다.
    같은 차트 컴포넌트(PreviewChart)가 먹을 모양이어야 하기 때문이다: 점마다
    전일 대비(`d`, 늘 bp)와 52주 min/max/avg 가 붙어야 툴팁이 선다. 여기서
    직접 만들면 두 화면이 같은 질문에 다른 정밀도로 답하게 된다.

    `unit` 을 넘기는 것이 요점이다 — 현금채권은 %(그래서 `d` 가 ×100 되어 bp),
    자산스왑은 이미 bp(그대로)다.
    """
    try:
        m = creditmatrix.load()
        kind, bond_type, tenor = cashbond.parse_id(series_id)
        values = cashbond.series_for(m, _dataset, series_id)
    except (cashbond.CashBondError, creditmatrix.CreditMatrixError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    unit = "%" if kind == cashbond.KIND_CASH else "bp"
    pairs = [
        (d.isoformat(), v) for d, v in zip(m.dates, values) if v is not None
    ]
    return {
        "id": series_id,
        "label": cashbond.instrument_label(kind, bond_type, tenor),
        "unit": unit,
        **series_history(pairs, unit),
    }


@router.get("/api/cashbond/backtest")
def cashbond_backtest(
    positions: str = "",
    basis: str = funding.DEFAULT_BASIS,
    spreadBp: float = funding.DEFAULT_SPREAD_BP,
) -> dict:
    """현금채권 북을 매일 재평가한다.

    `positions` 문법은 IRS 백테스트와 같다 — `;` 로 나열하고 하나는
    `id,direction,notional,entry[,exit]`. id 는 `CB:KTB:3Y` 또는
    `ASW:KTB:3Y` 다. 조달은 쿼리로 따라온다(Setting 탭이 채운다).
    """
    if not positions.strip():
        raise HTTPException(status_code=422, detail="포지션이 하나는 있어야 합니다.")

    spec = _funding_spec(basis, spreadBp)
    parsed: list[cashbond.BondPosition] = []
    for raw in positions.split(";"):
        raw = raw.strip()
        if not raw:
            continue
        parts = [x.strip() for x in raw.split(",")]
        if len(parts) not in (4, 5):
            raise HTTPException(
                status_code=422,
                detail=f"잘못된 포지션 {raw!r}: id,direction,notional,entry[,exit] 형식입니다.",
            )
        try:
            kind, bond_type, tenor = cashbond.parse_id(parts[0])
            parsed.append(
                cashbond.BondPosition(
                    kind=kind,
                    bond_type=bond_type,
                    tenor=tenor,
                    direction=int(parts[1]),
                    notional=float(parts[2]),
                    entry=dt.date.fromisoformat(parts[3]),
                    exit=dt.date.fromisoformat(parts[4]) if len(parts) == 5 and parts[4] else None,
                )
            )
        except (ValueError, cashbond.CashBondError) as exc:
            raise HTTPException(status_code=422, detail=f"잘못된 포지션 {raw!r}: {exc}")

    try:
        m = creditmatrix.load()
        result = cashbond.run_backtest(m, _dataset, parsed, spec)
        # 일별 대사는 별도 패스다 — KRD 범프가 본체보다 비싸서 IRS 쪽도 함수를
        # 둘로 나눴다(`backtest.book_recon` 의 근거). 응답은 한 덩어리에 얹는다.
        result["recon"] = cashbond.book_recon(m, _dataset, parsed, spec)
        return result
    except (cashbond.CashBondError, creditmatrix.CreditMatrixError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except funding.FundingError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ── RV Analysis — Strategy 섹션 (rv2) ───────────────────────────────────────
# 라이브 전용이다: 민평이 SQL 에만 있고(Cash Bond 와 같은 성질), 조달·금통위
# 경로가 읽는 사람의 입력이다. `creditmatrix.load()` 는 워터마크 캐시라 요청마다
# 전량을 다시 긁지 않는다(그 모듈의 규약).


@router.get("/api/rv/analysis")
def rv_analysis(
    h: int = rv_mod.H_DEFAULT_MONTHS,
    basis: str = funding.DEFAULT_BASIS,
    spreadBp: float = funding.DEFAULT_SPREAD_BP,
    window: str = "52w",
    mpc: str = "",
    reinvest: str = "none",
    reinvestRate: float = 0.0,
    paths: str = "",
) -> dict:
    """세 구성(동일섹터 격자·동일테너 히트맵·크레딧 산점) 페이로드 전부.

    파생량(carry·roll·재투자·매도 듀레이션·BEP·스왑점·경로별 총수익)을 서버가
    끝낸다(§16).

        mpc          `날짜:bp;…` — 달력 회의의 오버라이드, 기본 전부 0
        reinvest     none | manual | residual (워크북 만기선택!B11)
        reinvestRate manual 일 때의 연 이자율(%). 화면 단위 그대로 받아 decimal 로
        paths        `3M:0,6M:5,…|3M:20,…` — 비평행 경로(워크북 케이스 C/C-2)
    """
    if window not in ("52w", "all"):
        raise HTTPException(status_code=422, detail=f"알 수 없는 이력 창입니다: {window!r} (52w 또는 all)")
    if not 1 <= h <= 24:
        raise HTTPException(status_code=422, detail=f"호라이즌이 범위를 벗어납니다: {h}개월 (1~24)")
    if reinvest not in rv_mod.REINVEST_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"알 수 없는 재투자 방식입니다: {reinvest!r} ({', '.join(rv_mod.REINVEST_MODES)})",
        )
    # 재투자 금리는 화면이 퍼센트로 준다 — 손이 미끄러진 300%가 조용히 계산되지
    # 않도록 여기서 자른다(funding.spread_bp·금통위 ±100bp 와 같은 판단).
    if not -10.0 <= reinvestRate <= 30.0:
        raise HTTPException(
            status_code=422, detail=f"재투자금리가 범위를 벗어납니다: {reinvestRate}% (−10~30)"
        )
    spec = _funding_spec(basis, spreadBp)
    try:
        meetings = rv_mod.parse_meetings(mpc)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"금통위 오버라이드를 읽지 못했어요: {exc}")
    try:
        curve_paths = rv_mod.parse_paths(paths)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"커스텀 커브를 읽지 못했어요: {exc}")
    try:
        return rv_mod.build_rv(
            creditmatrix.load(), _dataset, spec,
            h_months=h, meetings=meetings, window=window,
            reinvest=reinvest, reinvest_rate=reinvestRate / 100.0,
            paths=curve_paths,
        )
    except (creditmatrix.CreditMatrixError, funding.FundingError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/api/rv/history")
def rv_history(sector: str, tenor: str, window: str = "52w") -> dict:
    """크레딧 RV 클릭 상세의 두 소형 차트 — 스프레드 이력·섹터 상대 이력과
    각각의 창 통계(±σ 밴드 재료). 숫자는 서버가 끝낸다(§16)."""
    if window not in ("52w", "all"):
        raise HTTPException(status_code=422, detail=f"알 수 없는 이력 창입니다: {window!r} (52w 또는 all)")
    try:
        return rv_mod.credit_history(creditmatrix.load(), sector, tenor, window)
    except creditmatrix.CreditMatrixError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _mr_payload(window: int, k: float) -> dict:
    """검증된 (window, k) 조합의 페이로드 — 조합마다 캐시 이름이 다르다.

    universe 캐시와 같은 판단으로 `_dataset.data_key` 에 태운다: BSS 는 호출 시
    SQL 이지만 하루 한 번 움직이는 입력이다. 조합은 WINDOWS×KS 로 유한하므로
    캐시 파일도 유한하다.
    """
    if window not in mr_mod.WINDOWS:
        raise HTTPException(
            status_code=422,
            detail=f"알 수 없는 룩백입니다: {window}일 ({', '.join(map(str, mr_mod.WINDOWS))})",
        )
    if k not in mr_mod.KS:
        raise HTTPException(
            status_code=422,
            detail=f"알 수 없는 밴드 폭입니다: {k}σ ({', '.join(map(str, mr_mod.KS))})",
        )
    return cached(f"mr-w{window}-k{k}", _dataset.data_key,
                  lambda: mr_mod.build_mr(_dataset, window=window, k=k))


@router.get("/api/mr/board")
def mr_board(window: int = mr_mod.WINDOW, k: float = mr_mod.K) -> dict:
    """Mean Reversion 측정면의 보드 — BSS 전 테너의 밴드 위치·상태·랭킹(§16).

    룩백·밴드 폭은 화면 선택지(WINDOWS·KS — 근거는 mr.py 머리)이고, 히스토리는
    무겁고 행마다 필요하지도 않아 `/api/mr/history` 가 따로 썬다.
    """
    p = _mr_payload(window, k)
    return {key: v for key, v in p.items() if key != "history"}


@router.get("/api/mr/history/{series_id:path}")
def mr_history(series_id: str, window: int = mr_mod.WINDOW, k: float = mr_mod.K) -> dict:
    """한 계열의 값+밴드 이력(약 1년) — 클릭 상세 차트의 재료. 밴드가 룩백·폭을
    따라가므로 보드와 같은 파라미터를 받는다."""
    p = _mr_payload(window, k)
    body = p["history"].get(series_id)
    if body is None:
        raise HTTPException(status_code=404, detail=f"unknown mr series {series_id}")
    return body


def _mr_neighbors(dates: list[str], vals: list[float], base: dict,
                  allow: tuple[int, ...], *,
                  carry: list[float] | None = None,
                  entry_mode: str = "level",
                  gate: list[bool] | None = None,
                  time_stop: int | None = None,
                  cost_bp_series: list[float] | None = None,
                  reverse_exit: bool = False,
                  close_open_at_end: bool = False) -> list[dict]:
    """노브를 한 칸씩 옮겼을 때의 결과 — 「이 칸이 얼마나 튼튼한가」.

    화면은 고른 칸 하나만 보여 준다. 그러면 손절 3.5 의 +2,605만은 보이고 손절
    3.0 의 +1,120만은 안 보이므로, 한 칸 차이가 결과를 절반으로 만든다는 사실이
    노브를 눌러 보기 전까지 감춰진다 — 재현 도구가 그 사실을 감추면 재현이
    아니라 주장이 된다 [OWNER 2026-08-26].

    **머리 숫자와 같은 규칙으로 돈다** [2026-08-28]. 종전에는 캐리를 안 넘겨서
    「현재」 칸이 머리의 총손익과 달랐다 — 실측 BSS-3Y 에서 머리 +4,443만 ·
    현재 칸 +4,160만(SR 0.812 대 0.762). 이웃 표는 «한 칸 옮기면 얼마나
    달라지는가» 를 재는 물건인데, 기준점이 머리와 다르면 그 차이가 노브 탓인지
    항이 빠진 탓인지 화면이 구분해 주지 못한다.

    격자는 `mr.STRATEGY_PRESETS` 위에서만 돈다(화면이 고를 수 있는 칸 = 견고성을
    재야 하는 칸). 현재 값이 프리셋 밖이면(딥링크·자유 룩백) 그 값도 한 칸으로
    끼워 넣는다 — 안 그러면 「현재」가 어느 칸인지 못 가리킨다. 계산은 노브당
    셋이라 열둘, 밀리초라 캐시를 안 태운다.
    """
    rows: list[dict] = []
    for knob, (label, suffix) in mr_mod.STRATEGY_KNOB_LABELS.items():
        cur = base[knob]
        opts = list(mr_mod.STRATEGY_PRESETS[knob])
        if cur not in opts:
            opts = sorted(opts + [cur])
        cells = []
        for v in opts:
            lb = int(v) if knob == "lookback" else base["lookback"]
            if len(vals) < lb + 1 or lb < 2:
                continue
            p = dict(base, **{knob: v})
            r = mrbt.simulate(dates, vals, lookback=int(p["lookback"]),
                              entry_z=p["entryZ"], exit_z=p["exitZ"],
                              stop_z=p["stopZ"], cost_bp=p["costBp"],
                              notional=p["notional"], allow_dirs=allow,
                              carry=carry, entry_mode=entry_mode, gate=gate,
                              time_stop=time_stop, cost_bp_series=cost_bp_series,
                              reverse_exit=reverse_exit,
                              close_open_at_end=close_open_at_end)
            sm = r["summary"]
            cells.append({
                "v": v,
                "totalPnl": round(sm["totalPnl"], 2),
                "sharpe": round(sm["sharpe"], 3) if sm["sharpe"] is not None else None,
                "winRate": round(sm["winRate"], 4) if sm["winRate"] is not None else None,
                "numTrades": sm["numTrades"],
                "current": v == cur,
            })
        if cells:
            rows.append({"knob": knob, "label": label, "suffix": suffix, "cells": cells})
    return rows


#: 최적화 격자가 흔드는 다섯 [OWNER 2026-09-04 — "지금 주어진 진입, 청산,
#: 손절, 룩백, 진입 규칙을 바탕으로 … 근사 최적화 세트"]. 진입 규칙만 프리셋이
#: 아니라 **전 경우**(둘)다 — 값이 아니라 규칙이라 「이웃」이라는 말이 안 선다.
MR_ENTRY_MODES_ALL: tuple[str, ...] = ("level", "touch")

#: 격자가 낼 수 있는 최대 칸 수 — 3×3×3×3×2 = 162 가 프리셋 그대로의 값이다.
#: 현재 노브가 프리셋 밖이면(자유 룩백) 칸이 하나씩 늘어 최대 4×4×4×4×2 = 512.
#: 그 위는 라우트가 막는다 — 화면에 안 쓰는 계산에 몇 초를 쓰지 않는다.
MR_OPT_MAX_CELLS = 512


def _mr_optimize(dates: list[str], vals: list[float], base: dict,
                 allow: tuple[int, ...], *,
                 span: str,
                 carry: list[float] | None = None,
                 gate: list[bool] | None = None,
                 time_stop: int | None = None,
                 cost_bp_series: list[float] | None = None,
                 reverse_exit: bool = False,
                 close_open_at_end: bool = False,
                 tradable_dv: list[float] | None = None) -> dict:
    """**근사 최적화 격자** — 다섯 노브의 프리셋을 전부 돌린 결과
    [OWNER 2026-09-04].

    ## 왜 «근사» 인가

    연속 최적화를 안 한다. 격자는 **화면이 고를 수 있는 값** 위에서만 돌고
    (`mr.STRATEGY_PRESETS` + 진입 규칙 둘), 그건 이웃 칸 표가 서던 자리와 같은
    규율이다: 화면이 못 고르는 조합을 최적이라고 적으면 그 수를 재현할 손잡이가
    없다. 프리셋 밖의 최적을 찾는 도구가 아니라 **「내가 지금 고른 칸이 이
    격자에서 몇 등인가」** 를 답하는 도구다.

    ## 회계는 **엔진 근사**다 — 그 사실을 화면이 적는다

    162칸을 실가격(자산스왑 재가격)으로 매기면 한 칸이 초 단위라 못 돈다.
    그래서 여기서는 `mrbacktest.simulate` 의 수를 그대로 쓴다 — 머리 카드가
    실가격일 때 이 표의 숫자는 그것과 **다르다**(BSS 실측: 실가격이 거래당
    +0.7~+3.5백만원 크다). 화면은 최적 칸을 «채택» 버튼으로 노브에 꽂고,
    정식 실행은 늘 그대로 돈다 — 그때 실가격이 붙는다.

    ## 순위는 서버가 안 매긴다

    칸을 전부 돌려주고 **정렬은 화면**이 한다. 순위 기준(Calmar·Sortino·…)을
    바꿀 때마다 서버에 다시 물으면, 같은 격자를 기준만 바꿔 다시 도는 셈이다.
    그리고 「기준을 바꾸면 1등이 바뀐다」는 사실 자체가 이 표가 말해야 하는
    것이라, 그 전환은 즉각이어야 한다.
    """
    opts: dict[str, list] = {}
    for knob in ("lookback", "entryZ", "exitZ", "stopZ"):
        o = list(mr_mod.STRATEGY_PRESETS[knob])
        if base[knob] not in o:
            o = sorted(o + [base[knob]])
        opts[knob] = o
    modes = list(MR_ENTRY_MODES_ALL)
    if base["entryMode"] not in modes:
        modes.append(base["entryMode"])

    n_cells = 1
    for o in opts.values():
        n_cells *= len(o)
    n_cells *= len(modes)
    if n_cells > MR_OPT_MAX_CELLS:
        raise HTTPException(
            status_code=422,
            detail=f"격자가 너무 커요: {n_cells}칸 (최대 {MR_OPT_MAX_CELLS})")

    months = dict(mrm.SPANS).get(span)
    start = mrm.span_start(dates, months)

    cells: list[dict] = []
    for lb in opts["lookback"]:
        lb = int(lb)
        if lb < 2 or len(vals) < lb + 1:
            continue
        # 룩백이 같은 칸 54개가 **같은 밴드**를 쓴다 — 한 번 재서 나눠 준다
        # (`mrbacktest.simulate` 의 `roll` 손잡이. 산술은 안 바뀐다).
        rs = mrbt.rolling_series(vals, lb)
        for ez in opts["entryZ"]:
            for xz in opts["exitZ"]:
                for sz in opts["stopZ"]:
                    for md in modes:
                        r = mrbt.simulate(
                            dates, vals, lookback=lb, entry_z=ez, exit_z=xz,
                            stop_z=sz, cost_bp=base["costBp"],
                            notional=base["notional"], allow_dirs=allow,
                            carry=carry, entry_mode=md, gate=gate,
                            time_stop=time_stop, cost_bp_series=cost_bp_series,
                            reverse_exit=reverse_exit,
                            close_open_at_end=close_open_at_end,
                            tradable_dv=tradable_dv, roll=rs)
                        m = mrm.score(dates, r["points"], r["trades"], start,
                                      base["costBp"])
                        cells.append({
                            "lookback": lb, "entryZ": ez, "exitZ": xz,
                            "stopZ": sz, "entryMode": md,
                            # 지금 노브가 어느 칸인가 — 순위를 매기는 쪽이
                            # 「내 칸」을 표에서 못 찾으면 이 표의 목적이 없다.
                            "current": (lb == base["lookback"] and ez == base["entryZ"]
                                        and xz == base["exitZ"] and sz == base["stopZ"]
                                        and md == base["entryMode"]),
                            **{k: m[k] for k in (
                                "totalPnl", "maxDrawdown", "sortino", "calmar",
                                "gpr", "omega", "profitFactor", "ulcer",
                                "martin", "recoveryDays", "recovered",
                                "winRate", "numTrades", "breakevenCostBp",
                                # **화면의 자동 채택 기준** [OWNER 2026-09-09] —
                                # 칸마다 있어야 순위가 선다(`mrmetrics` 의 그 산술).
                                "cdarRatio",
                                "breakevenCostMult")},
                        })
    return {
        "span": span,
        "from": dates[start] if dates else None,
        "to": dates[-1] if dates else None,
        "days": len(dates) - start,
        "cells": cells,
    }


def _mr_book_optimize(legs: list[dict], base: dict, *, span: str,
                      time_stop: int | None, reverse_exit: bool,
                      close_open_at_end: bool) -> dict:
    """**통합 장부의 근사 최적화 격자** [OWNER 2026-09-07 — "통합 장부에도
    마찬가지로 적용해줘"].

    낱개 격자(`_mr_optimize`)와 **같은 프리셋·같은 채점자**를 쓴다. 다른 것은
    한 칸의 값이 계열 하나가 아니라 **아홉을 더한 장부**라는 것뿐이다: 칸마다
    아홉을 돌려 날짜로 포개고(`mrbook._pooled` 와 같은 사상), 그 통합 곡선 위에서
    `mrmetrics.score` 를 부른다.

    ## 왜 아홉을 각자 채점해서 더하지 않나

    Calmar·Sortino 는 **비선형**이라 다리별 값의 평균이 장부의 값이 아니다.
    낙폭은 특히 그렇다 — 아홉이 서로 다른 날 물속에 있으면 장부의 최대낙폭은
    아홉 낙폭의 합보다 훨씬 작다. 그 차이가 이 창이 존재하는 이유(«묶어서
    나아졌나»)이므로, 채점은 반드시 **더한 뒤에** 한다.

    ## 값 — 이 표는 화면이 이미 「안 한다」고 적어 둔 자리였다

    2026-09-01 판의 각주는 「노브 민감도(이웃 칸)는 두 창 다 없어요 — 여기서는
    한 칸마다 만기 아홉을 다시 돌아야 하고, 전진분석이 파라미터 선택에 값을 못
    더한다는 실측이 있어요」였다. 오너가 그 결정을 뒤집었으므로(2026-09-07)
    **각주도 같이 고친다** — 화면이 자기가 하는 일을 「안 한다」고 말하면 안 된다.
    남는 경고는 그대로다: 이 격자는 **표본내**이고, 1등 칸을 그대로 믿으면
    과적합이 만기 아홉 배로 붙는다. 화면이 그 문장을 진다.
    """
    dates = sorted({t for leg in legs for t in leg["dates"]})
    at = {t: i for i, t in enumerate(dates)}
    cut = mrm.span_cut(dates, dict(mrm.SPANS).get(span))
    start = mrm.index_at(dates, cut)

    opts: dict[str, list] = {}
    for knob in ("lookback", "entryZ", "exitZ", "stopZ"):
        o = list(mr_mod.STRATEGY_PRESETS[knob])
        if base[knob] not in o:
            o = sorted(o + [base[knob]])
        opts[knob] = o
    modes = list(MR_ENTRY_MODES_ALL)
    if base["entryMode"] not in modes:
        modes.append(base["entryMode"])

    n_cells = len(modes)
    for o in opts.values():
        n_cells *= len(o)
    if n_cells > MR_OPT_MAX_CELLS:
        raise HTTPException(
            status_code=422,
            detail=f"격자가 너무 커요: {n_cells}칸 (최대 {MR_OPT_MAX_CELLS})")

    cells: list[dict] = []
    for lb in opts["lookback"]:
        lb = int(lb)
        # 룩백이 같은 칸이 **같은 밴드**를 쓴다 — 다리마다 한 번 재서 나눠 준다
        # (`mrbacktest.simulate` 의 `roll` 손잡이. 산술은 안 바뀐다). 이걸 안
        # 하면 아홉 × 54칸이 밴드를 처음부터 다시 잰다.
        rolls = {}
        usable = []
        for leg in legs:
            if len(leg["vals"]) >= lb + 1 and lb >= 2:
                rolls[leg["id"]] = mrbt.rolling_series(leg["vals"], lb)
                usable.append(leg)
        if not usable:
            continue
        for ez in opts["entryZ"]:
            for xz in opts["exitZ"]:
                for sz in opts["stopZ"]:
                    for md in modes:
                        daily = [0.0] * len(dates)
                        bcost = [0.0] * len(dates)
                        raw: list[dict] = []
                        for leg in usable:
                            r = mrbt.simulate(
                                leg["dates"], leg["vals"], lookback=lb,
                                entry_z=ez, exit_z=xz, stop_z=sz,
                                cost_bp=base["costBp"], notional=base["notional"],
                                allow_dirs=tuple(leg["dirs"]["allowed"]),
                                carry=leg["carryKrw"], entry_mode=md,
                                gate=leg["gate"], time_stop=time_stop,
                                cost_bp_series=leg["costSeries"],
                                reverse_exit=reverse_exit,
                                close_open_at_end=close_open_at_end,
                                tradable_dv=leg["tradable"],
                                roll=rolls[leg["id"]])
                            for j, pt in enumerate(r["points"]):
                                i = at[leg["dates"][j]]
                                daily[i] += pt["dailyPnl"]
                                bcost[i] += pt["barCost"]
                            raw.extend(r["trades"])
                        pts = [{"dailyPnl": daily[i], "barCost": bcost[i]}
                               for i in range(len(dates))]
                        m = mrm.score(dates, pts, raw, start, base["costBp"])
                        cells.append({
                            "lookback": lb, "entryZ": ez, "exitZ": xz,
                            "stopZ": sz, "entryMode": md,
                            # 「내 칸」을 표에서 못 찾으면 순위가 아무 말도 못 한다.
                            "current": (lb == base["lookback"] and ez == base["entryZ"]
                                        and xz == base["exitZ"] and sz == base["stopZ"]
                                        and md == base["entryMode"]),
                            # 몇 만기가 실제로 섰나 — 룩백이 길면 짧은 계열이
                            # 빠질 수 있고, 그때 그 칸은 **다른 장부**다.
                            "legs": len(usable),
                            **{k: m[k] for k in (
                                "totalPnl", "maxDrawdown", "sortino", "calmar",
                                "gpr", "omega", "profitFactor", "ulcer",
                                "martin", "recoveryDays", "recovered",
                                "winRate", "numTrades", "breakevenCostBp",
                                # **화면의 자동 채택 기준** [OWNER 2026-09-09] —
                                # 칸마다 있어야 순위가 선다(`mrmetrics` 의 그 산술).
                                "cdarRatio",
                                "breakevenCostMult")},
                        })
    return {
        "span": span,
        "from": dates[start] if dates else None,
        "to": dates[-1] if dates else None,
        "days": len(dates) - start,
        "cells": cells,
    }


def _mr_check_knobs(lookback: int, entryZ: float, exitZ: float,
                    stopZ: float, costBp: float, notional: float,
                    entryMode: str, timeStop: int, costModel: str,
                    regime: str) -> None:
    """노브의 범위·허용값 — `/api/mr/strategy` 와 `/api/mr/book` 이 **같은 문**을
    쓴다. 두 벌이면 한쪽만 통과하는 조합이 생기고, 그때 통합의 수와 낱개의 수가
    다른 규칙에서 나온 것이 된다."""
    if not 2 <= lookback <= 600:
        raise HTTPException(status_code=422, detail=f"룩백이 범위를 벗어나요: {lookback}일 (2~600)")
    # 「관찰 σ」(warnZ)가 2026-09-02 에 여기서 빠졌다 [OWNER — "이건 뭔지 확인하고
    # 필요없으면 치우기"]. 엔진에 안 들어가고 화면에 점선만 긋던 값이라 문을
    # 지킬 것이 없었다 — 검증은 **결과를 바꾸는 값**에만 값이 있다.
    for name, v in (("entry", entryZ), ("exit", exitZ), ("stop", stopZ)):
        if not 0.0 <= v <= 20.0:
            raise HTTPException(status_code=422, detail=f"{name} σ가 범위를 벗어나요: {v} (0~20)")
    if not 0.0 <= costBp <= 10.0:
        raise HTTPException(status_code=422, detail=f"비용이 범위를 벗어나요: {costBp}bp (0~10)")
    if not 0.0 <= notional <= 1e12:
        raise HTTPException(status_code=422, detail=f"명목이 범위를 벗어나요: {notional} (0~1e12)")
    if entryMode not in mrbt.ENTRY_MODES:
        raise HTTPException(status_code=422,
                            detail=f"진입 규칙이 이상해요: {entryMode} ({'|'.join(mrbt.ENTRY_MODES)})")
    # ── 실전 운용 손잡이 넷 [OWNER 2026-08-28] ─────────────────────────────────
    # 전부 기본이 꺼짐이라 안 주면 원본 PMS 재현 그대로다. 근거와 실측은
    # `docs/MR_LANE_STATE.md` 와 `backend/scripts/mr_live_report.py`.
    if not 0 <= timeStop <= 500:
        raise HTTPException(status_code=422, detail=f"타임스탑이 범위를 벗어나요: {timeStop} (0~500)")
    if costModel not in mrg.COST_MODELS:
        raise HTTPException(status_code=422,
                            detail=f"비용 모델이 이상해요: {costModel} ({'|'.join(mrg.COST_MODELS)})")
    if regime not in mrg.REGIMES:
        raise HTTPException(status_code=422,
                            detail=f"레짐 필터가 이상해요: {regime} ({'|'.join(mrg.REGIMES)})")


#: 대사를 캐시해 두는 기준 액면. **대사는 명목에 선형이다**(실측 2026-09-03:
#: 3배 명목에서 차이가 서버 자신의 원 단위 반올림 ≤2원). 그래서 한 번 재고
#: 배수로 쓴다 — 명목 노브를 돌려도 다시 안 잰다.
MR_REF_PRINCIPAL = 1_000_000_000.0
#: (워터마크, 계열, 진입, 청산, 방향, 조달기준, 조달스프레드, 다리, 창) → 행.
#: 워터마크가 키에 있어 민평이 갱신되면 저절로 갈린다.
#:
#: **여기 든 `None` 은 「결정적으로 반쪽」이다** — 창이 잘렸다는 잰 결과이고 같은
#: 자료 위에서 다시 재도 답이 안 바뀐다. 예외로 못 잰 자리는 **아예 안 들어온다**
#: (`_mr_recon_rows` 머리 — 실패를 붙들었더니 87칸이 뒤집혔다).
_mr_recon_cache: dict[tuple, dict | None] = {}
MR_RECON_CACHE_MAX = 4096


#: 날짜 → 그날 커브의 par-swap 연금계수. 부트스트랩이 비싸서 캐시한다.
_mr_pv01_cache: dict[tuple[str, float], float] = {}


def _mr_pv01_at(on: dt.date, tenor_years: float) -> float | None:
    """**그날 커브의** pv01. 없으면 `None`.

    ## 왜 «그날» 이어야 하나 [검산 2026-09-03]

    명목 노브는 `₩/bp`(DV01)이고 자산스왑의 명목은 **액면**이라 환산이 필요한데,
    종전에는 그 환산을 **지금 커브**의 pv01 하나로 6년 내내 했다. `mrcarry` 가
    그것을 「[알려진 근사]」로 적어 두면서 «이 환산은 캐리의 크기만 정하고 부호나
    시점은 안 건드린다» 고 했고, 손익이 `명목 × Δ스프레드` 이던 시절에는 참이었다.

    **회계를 실가격으로 바꾸면서 그 문장이 거짓이 됐다** — 이제 손익은 그 액면을
    가격해서 나오므로 환산 오차가 손익 전체를 스케일한다. 손으로 재 보니 진입
    시점 연금계수가 6.15~6.76(7Y)이고 지금은 6.08 이라, 옛 거래일수록 **명목
    노브가 말하는 것보다 최대 11% 큰 포지션**이었다(10Y 는 16%). 총손익으로는
    2~8% 다.

    그래서 거래마다 **진입일 커브**로 잰다. 그러면 「명목 1,000,000원/bp」가 모든
    거래에서 같은 뜻이 되고, 백테스트가 요구하는 «비교 가능한 거래» 가 된다.
    """
    key = (on.isoformat(), tenor_years)
    if key in _mr_pv01_cache:
        return _mr_pv01_cache[key]
    try:
        from .backtest import _curve_at                # noqa: PLC0415 — 순환 회피
        j = {d: i for i, d in enumerate(_dataset.dates)}.get(on)
        if j is None:
            # IRS 달력에 없는 날 — 직전 영업일로 물러선다(민평 달력의 그 규약).
            prev = [i for i, d in enumerate(_dataset.dates) if d <= on]
            if not prev:
                return None
            j = prev[-1]
        v = float(pv01(_curve_at(_dataset, j), tenor_years))
    except Exception:                                  # noqa: BLE001
        return None
    if len(_mr_pv01_cache) > 8192:
        _mr_pv01_cache.clear()
    _mr_pv01_cache[key] = v
    return v


def _mr_principal_at(on: dt.date, tenor: str, notional: float) -> float | None:
    """그 거래의 **액면** — 진입일 커브에서 명목(₩/bp)을 액면으로."""
    pv = _mr_pv01_at(on, TENOR_T[tenor])
    return None if not pv else notional / (pv * 1e-4)


#: MR 선물 계열 → 선물 엔진의 계열 id·테너와 **방향 사상**
#: [실측 2026-09-04, 계열마다 여섯 거래 부호 전건 일치].
#:
#: FUT 는 MR 의 값이 **금리**라 +1(금리 롱) = 선물 매도이므로 뒤집는다(BSS 와
#: 같은 사상). FSW 는 값이 **스프레드**이고 `futures.py` 의 «+1 = 호가값(스프레드)
#: 롱 = 선물 매도 + IRS 리시브» 와 같은 말이라 그대로 넘긴다.
MR_FUT_MAP: dict[str, tuple[str, str, int]] = {
    "FUT-KTB3": ("FUT:3Y", "3Y", -1),
    "FUT-KTB10": ("FUT:10Y", "10Y", -1),
    "FSW-3Y": ("FSW:3Y", "3Y", 1),
    "FSW-10Y": ("FSW:10Y", "10Y", 1),
}

#: 선물 대사 캐시 — `_mr_recon_cache` 와 **같은 규율**이다(거래 목록은 z 에만
#: 달려 있어 노브를 돌리는 동안 거의 다 맞는다). 실패를 안 붙드는 이유도 같다
#: (그 함수 머리의 실측 — 붙들었더니 87칸이 뒤집혔다).
_mr_fut_cache: dict = {}


def _mr_fut_recon(sid: str, direction: int, notional: float,
                  entry: dt.date, exit_: dt.date, *, with_krd: bool,
                  with_legs: bool = False) -> dict | None:
    """MR **선물 거래 하나**의 실가격 대사 — 못 세우면 `None`.

    반환 `{"blocks": [{"name", "recon"}], "face": 액면, "rolls": [롤일]}`.

    ## `with_legs` — 화면은 한 표, 회계는 두 블록 [OWNER 2026-09-07]

    **켜면**(화면) FSW 도 블록 **하나**다. IRS 다리가 선물 표 안으로 들어와
    하루가 일곱 줄이 된다 — 백테스트 창이 2026-09-04 에 간 그 길이고
    (`futures.book_recon(with_legs=True)` 의 «버킷»), 이제 두 화면이 같은 상품을
    같은 모양으로 그린다. 종전에는 여기가 **둘**이었다(선물 달력 + IRS 달력)
    [OWNER 2026-08-25, 엔진 단위 분리] — 그 분리는 «표는 자기 달력 위에 선다»
    까지 살고, 「한 거래의 두 다리는 한 표에」가 그 위에 얹힌다.

    **끄면**(회계) 종전 그대로 둘이다. 모양이 아니라 **값**이 필요한 자리라서
    그렇다: 다리 표는 IRS 파 커브를 범프해야 서는데(`with_krd=True` 가 박혀 있다
    — `futures.book_recon` 의 그 호출), 회계는 거래마다 도므로 그 값을 안 쓰고도
    낼 수 있는 총계만 받는다(BSS 가 `_mr_recon_rows` 에서 같은 이유로 다리를
    안 묻는다). **돈은 어느 쪽이든 같다** — 다리의 합이 곧 합계 줄이고, 회계는
    블록의 행을 한 줄기로 펴서 날짜로 얹는다.

    실측 2026-09-04: 블록의 돈 합이 거래 손익과 ±2원으로 닫힌다.

    ## 액면

    MR 노브는 ₩/bp(DV01)인데 선물 포지션은 **액면**을 받는다. 환산은 그 거래의
    **진입일 벤더 내재금리**로 한다(`futures.face_for_dv01` — BSS 의
    `_mr_principal_at` 과 같은 자리, 같은 이유).

    ## 캐리·롤다운·조달이 없는 다리

    선물 다리는 현금결제·연결 계열이라 **존재하지 않는 성분**이다(공란 정책 —
    `futures.book_recon` 머리). 0 으로 채우지 않는다.
    """
    hit = MR_FUT_MAP.get(sid)
    if hit is None:
        return None
    fid, tenor, sign = hit
    try:
        fut = futures.load()
    except Exception:                                  # noqa: BLE001
        return None
    #: `with_legs` 가 **열쇠에 든다** — 다리 유무는 응답의 모양을 바꾼다
    #: (`_mr_recon_rows` 의 같은 조항). 안 넣으면 회계가 먼저 캐시를 채우고
    #: 화면이 두 블록짜리 옛 판을 받는다.
    key = (fut.watermark, _dataset.data_key if hasattr(_dataset, "data_key") else None,
           sid, direction, notional, entry, exit_, with_krd, with_legs)
    if key in _mr_fut_cache:
        return _mr_fut_cache[key]

    got: dict | None = None
    try:
        fs = fut.series[tenor]
        i = futures._index_on_or_before(fs.dates, entry)   # noqa: SLF001 — 같은 레인
        y0 = futures.implied_at_index(fs, i, tenor)
        face = futures.face_for_dv01(notional, y0, tenor)
        pos = futures.as_position(fid, sign * int(direction), face, entry, exit_)
        # 다리를 켜는 것은 **FSW 일 때만** 뜻이 있다 — FUT 아웃라이트는 물건이
        # 하나라 다리가 없고, `book_recon` 도 그때는 `with_legs` 를 무시한다.
        want_legs = bool(with_legs and pos.kind == futures.KIND_FSW)
        blocks = [{"name": "선물",
                   "recon": futures.book_recon(fut, _dataset, [pos],
                                               with_legs=want_legs)}]
        if pos.kind == futures.KIND_FSW and not want_legs:
            swap_pos, _y, _dv = futures.fsw_swap_leg(fut, _dataset, pos)
            blocks.append({"name": "IRS",
                           "recon": bt_engine.book_recon(_dataset, [swap_pos],
                                                         with_krd=with_krd)})
        # 보유 중 **롤일** — 그날 갈아타므로 왕복 1틱을 문다(`futures.roll_cost`).
        rolls = sorted(d for d in futures.roll_days(list(fs.dates))
                       if entry < d <= exit_)
        got = {"blocks": blocks, "face": face, "rolls": [d.isoformat() for d in rolls]}
    except (futures.FuturesError, BacktestError, KeyError, ValueError, IndexError) as exc:
        # **같은 병, 같은 처방** [2026-09-09] — 이 캐시도 실패를 붙들면 한 번의
        # 사고가 재시작 전까지 그 다리를 근사로 묶는다(`_mr_recon_rows` 머리의
        # 그 실측). 캐시에 안 넣고 나간다.
        logging.getLogger("app.main").warning(
            "[mr] 선물 실가격 대사 실패 — %s %s~%s: %s", sid, entry, exit_, exc)
        return None
    if len(_mr_fut_cache) >= MR_RECON_CACHE_MAX:
        _mr_fut_cache.clear()
    _mr_fut_cache[key] = got
    return got


def _mr_recon_rows(m, tenor: str, entry: dt.date, exit_: dt.date,
                   direction: int, spec, with_legs: bool = False,
                   max_days: int | None = cashbond.RECON_MAX_DAYS) -> dict | None:
    """기준 액면에서의 대사 — `{"tenors", "rows"}`. 못 세우면 `None`.

    **거래 목록은 z 에만 달려 있다**(`mrbacktest` 머리) — 명목·비용·조달을
    돌려도 진입·청산 날짜가 안 움직인다. 그래서 이 캐시는 노브를 돌리는 동안
    거의 다 맞는다. 통합 장부(아홉 다리 143건)가 매번 8초를 쓰지 않는 이유다.

    ## ⚠ 실패를 **영구히 캐시하지 않는다** [2026-09-09]

    종전에는 예외를 잡아 `None` 을 그대로 열쇠에 넣었다. 그래서 DB 가 **한 번**
    버벅이면 그 거래창을 쓰는 뒤의 모든 요청이 근사로 떨어지고, 캐시가 4,096칸을
    채워 통째로 비워질 때까지 안 나았다 — 사용자에게는 「같은 화면인데 열 때마다
    손익이 다르다」로 보인다.

    실측(krw-crs 레인 2026-09-09): 셀 캐시를 3프로세스로 나눠 돌렸더니 근사가
    443/1,458 나왔는데, BSS-3Y 만 단독으로 다시 받으니 실가격이 48 → 135칸으로
    **162칸 중 87칸이 뒤집혔다.** 진짜 절단은 결정적이라 다시 돌려도 같은 답이므로
    **그 차이는 전부 캐시 오염**이었다.

    그래서 실패를 둘로 가른다:

      · **결정적 실패**(`truncated` — 창이 잘렸다) → 같은 자료면 늘 같은 답이라
        **캐시한다.** 다시 재도 답이 안 바뀌므로 재시도는 값이 없다.
      · **그 밖의 실패**(예외) → **캐시하지 않는다.** 자료가 없어서 못 재는
        것인지 이번에 못 잰 것인지를 여기서 확실히 가를 수 없기 때문이다
        (`CashBondError` 는 둘 다에서 난다 — 「민평 진입일이 IRS 달력에 없다」는
        자료이고, 그 아래 커브 조회가 흔들린 것은 이번 일이다). 가를 수 없으면
        **다시 재는 쪽**이 맞다: 늘 실패하는 자리가 무는 것은 예외 하나의 값이고,
        붙들었을 때 무는 것은 **틀린 손익을 화면에 띄우는 값**이다.

    `truncated` 를 성공처럼 캐시하는 것이 이상해 보이면 — 이건 「못 잰다」가 아니라
    **「이 창에서는 반쪽이다」라는 잰 결과**다. 회계 경로는 2026-09-09 부터
    `max_days=None` 으로 부르므로 애초에 이 답을 거의 안 받는다.
    """
    #: `with_legs` 가 **열쇠에 든다** — 다리 유무는 응답의 모양을 바꾼다. 안
    #: 넣으면 회계가 먼저 캐시를 채우고 화면이 다리 없는 판을 받는다.
    #: `max_days` 도 **같은 이유로 열쇠에 든다** [2026-09-09] — 창이 다르면 답도
    #: 다르고(잘림 여부가 통째로 갈린다), 안 넣으면 화면이 채운 절단 캐시를 회계가
    #: 받아 창을 가른 것이 아무 일도 안 하게 된다.
    key = (m.watermark, tenor, entry, exit_, direction, spec.basis, spec.spread_bp,
           with_legs, max_days)
    if key in _mr_recon_cache:
        return _mr_recon_cache[key]
    try:
        pos = cashbond.BondPosition(
            kind=cashbond.KIND_ASW, bond_type="KTB", tenor=tenor,
            direction=direction, notional=MR_REF_PRINCIPAL, entry=entry, exit=exit_)
        rec = cashbond.book_recon(m, _dataset, [pos], spec, with_legs=with_legs,
                                  max_days=max_days)
        # 창이 잘리면 **회계가 반쪽이다** — 반쪽을 총손익이라 부르지 않는다.
        got = (
            None if rec.get("truncated")
            # `legTenors` 는 다리별 대사의 **열 목록**이다 — 화면이 두 다리의
            # 합집합으로 칸을 세운다. 자산스왑 북에서만 온다.
            else {"tenors": rec["tenors"], "rows": rec["rows"],
                  "legTenors": rec.get("legTenors")}
        )
    except (cashbond.CashBondError, creditmatrix.CreditMatrixError, KeyError, ValueError) as exc:
        # **캐시에 안 넣고 그대로 나간다**(위 문단) — 다음 요청이 다시 잰다.
        # 조용히 근사로 떨어지는 것이 이 결함의 정체였으므로 로그는 남긴다.
        # 늘 실패하는 자리는 요청마다 예외 비용을 다시 무는데, 그 값은 «틀린 수를
        # 붙들고 있는 값» 보다 싸다 — 여기는 회계다.
        logging.getLogger("app.main").warning(
            "[mr] 실가격 대사 실패 — %s %s~%s: %s", tenor, entry, exit_, exc)
        return None
    if len(_mr_recon_cache) >= MR_RECON_CACHE_MAX:
        _mr_recon_cache.clear()          # 통째로 버린다 — LRU 를 짤 값이 아니다
    _mr_recon_cache[key] = got
    return got


#: 명목에 **비례하지 않는** 칸 — 금리 변화지 돈이 아니다.
MR_ROW_NOT_MONEY = ("t", "dbp", "carryover")


def _mr_scale_rows(rows: list[dict], scale: float) -> list[dict]:
    """기준 액면의 행을 실제 액면으로. **`dbp` 는 안 곱한다** — 그건 금리의
    변화지 돈이 아니다(곱하면 표가 「그날 3배로 움직였다」고 말한다).

    화면과 엔진이 **같은 수**를 쓰게 하려고 둘 다 이 길을 지난다. 각자 재면
    기준 액면에서의 원 단위 반올림이 배수만큼 벌어져 표와 헤드라인이 갈린다
    (실측 2026-09-03: 그 차이가 거래당 최대 21원이었다).
    """
    out: list[dict] = []
    for r in rows:
        d: dict = {}
        for k, v in r.items():
            if k in MR_ROW_NOT_MONEY or v is None:
                d[k] = v
            elif isinstance(v, dict):
                d[k] = {a: (b if k == "dbp" or b is None else round(b * scale))
                        for a, b in v.items()}
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                d[k] = round(v * scale)
            else:
                d[k] = v
        # ── 행이 **스스로 더해지게** 한다 ─────────────────────────────────────
        # 기준 액면에서 이미 원 단위로 반올림된 값을 배수하면 성분의 합과 총계가
        # 갈린다(실측: 1.64배에서 `Σest` 와 `estTotal` 이 최대 8원). 표가 가로로
        # 안 더해지면 그건 대사표가 아니라 숫자 더미다 — `splitKrw` 의 그 규칙
        # 으로 **한쪽이 잔차를 진다.**
        if isinstance(d.get("est"), dict) and isinstance(d.get("krd"), dict):
            # **줄이 곱해진다** — 추정을 반올림한 KRD·Δbp 에서 유도한다. 각자
            # 반올림하면 `−KRD × Δbp ≠ 추정` 이 되고(실측 2원), 그건 이 표가
            # 테너별 KRD 를 세우는 이유 자체를 깨뜨린다.
            dbp = d.get("dbp") or {}
            d["est"] = {lb: (0 if dbp.get(lb) is None else round(-k * dbp[lb]))
                        for lb, k in d["krd"].items()}
            d["estTotal"] = sum(d["est"].values())     # 총계는 성분의 합이다
        if d.get("actual") is not None:
            # 「그날 손익」이 정본이고 **평가가 잔차를 진다**(엔진과 같은 규칙).
            d["valuation"] = (d["actual"] - (d.get("carry") or 0)
                              - (d.get("rolldown") or 0) - (d.get("funding") or 0))
            if d.get("estTotal") is not None:
                d["residual"] = d["valuation"] - d["estTotal"]
        # ── 다리 블록도 같은 자로 [OWNER 2026-09-04] ─────────────────────────
        # 리스트라 위 루프의 어느 갈래에도 안 걸린다 — 안 곱하면 다리합이
        # 총계와 갈리고(실측: 배수 1.48 에서 거래당 431만원) 화면이 두 답을
        # 말한다. 반올림 규율은 위와 같다: **총계 행이 정본이고 국고 다리가
        # 잔차를 진다.**
        legs = r.get("legs")
        if isinstance(legs, list) and legs:
            scaled: list[dict] = []
            for lg in legs:
                e: dict = {}
                for k, v in lg.items():
                    if k == "name" or k in MR_ROW_NOT_MONEY or v is None:
                        e[k] = v
                    elif isinstance(v, dict):
                        e[k] = {a: (b if k == "dbp" or b is None else round(b * scale))
                                for a, b in v.items()}
                    elif isinstance(v, (int, float)) and not isinstance(v, bool):
                        e[k] = round(v * scale)
                    else:
                        e[k] = v
                if isinstance(e.get("est"), dict) and isinstance(e.get("krd"), dict):
                    # 다리 안에서도 **줄이 곱해진다** — 추정을 반올림한 KRD·Δbp
                    # 에서 유도한다(위 총계 줄과 같은 근거).
                    dbp_l = e.get("dbp") or {}
                    e["est"] = {lb: (0 if dbp_l.get(lb) is None else round(-k * dbp_l[lb]))
                                for lb, k in e["krd"].items()}
                    e["estTotal"] = sum(e["est"].values())
                scaled.append(e)
            if len(scaled) == 2 and d.get("actual") is not None:
                bond, swap = scaled
                s_carry = swap.get("carry") or 0
                s_roll = swap.get("rolldown") or 0
                s_act = swap.get("actual") or 0
                # IRS 다리는 조달이 없다 — 그 다리 안에서 평가가 잔차를 진다.
                swap["valuation"] = s_act - s_carry - s_roll
                swap["funding"] = None
                # 국고 다리는 **총계에서 IRS 다리를 뺀 것**이다. 각자 반올림해
                # 세우면 다리합이 그날 손익과 원 단위로 갈린다.
                bond["carry"] = (d.get("carry") or 0) - s_carry
                bond["rolldown"] = (d.get("rolldown") or 0) - s_roll
                bond["funding"] = d.get("funding") or 0
                bond["actual"] = d["actual"] - s_act
                bond["valuation"] = (bond["actual"] - bond["carry"]
                                     - bond["rolldown"] - bond["funding"])
                for lg in (bond, swap):
                    if lg.get("estTotal") is not None:
                        lg["residual"] = lg["valuation"] - lg["estTotal"]
            d["legs"] = scaled
        out.append(d)
    return out


def mr_combo_faces(sid: str, notional: float) -> list[tuple[str, float]]:
    """커브·플라이의 **다리별 액면**(₩) — `[(만기, 액면)]`, 리시브 다리부터.

    ## 액면이 한 숫자가 아닌 이유

    다리가 둘·셋이고 **DV01 중립**이라 원금이 다리마다 다르다: 짧은 쪽이 pv01
    비만큼 크고, 플라이의 벨리는 윙 둘의 합만큼이다(`mrcarry.combo_weights`).
    한 숫자를 「이 거래의 액면」이라 적으면 그건 기준 다리의 것일 뿐이다.

    ## 산술 — 나누는 것은 **기준 다리의 pv01** 이다

        기준원금 = 명목 / (pv01_기준 × 1e-4)
        원금_j  = 가중_j × 기준원금

    가중이 이미 `pv01_기준 / pv01_j` 를 지고 있으므로 각 다리의 pv01 로 **또**
    나누면 두 번 나누는 것이고, 그 액면은 DV01 중립이 아니다 — 첫 판에서 실제로
    그렇게 적었고 윙의 DV01 이 1.5배로 나왔다(화면에는 그럴듯한 억 단위 수가
    섰다). `tests/test_mr_combo.py` 가 다리마다 `액면 × pv01 × 1e-4` 를 되곱아
    명목과 같은지 잰다 — 벨리만 두 배다(값 규약 `2×벨리`).

    ⚠ **지금 커브**의 pv01 하나를 쓴다 — 액면·캐리가 이미 지고 있는 그 근사다
    (`docs/MR_LANE_STATE.md` §6 ⑤).
    """
    pv = lambda t: pv01(_curves["now"], TENOR_T[t])          # noqa: E731
    ws = mrc.combo_weights(sid, pv)
    ts = mrs.combo_tenors(sid)
    order = [ts[-1], ts[0]] if len(ts) == 2 else [ts[1], ts[0], ts[2]]
    base = notional / (pv(mrc._tenor_of(sid)) * 1e-4)
    return [(t, base * w) for t, w in zip(order, ws)]


def _mr_real_accounting(r: dict, *, sid: str, kind: str, tenor: str,
                        notional: float, cost_bp: float, spec) -> bool:
    """`simulate()` 의 **언제** 위에 백테스트·시뮬의 **얼마** 를 얹는다
    [OWNER 2026-09-03 — "캐리 롤다운 다 넣고 우리가 원래 사용하던 백테스트/
    시뮬레이션에서의 대사와 동일하게 작성하기"].

    ## 무엇을 바꾸고 무엇을 안 바꾸나

    **엔진 함수는 안 건드린다.** `mrbacktest.simulate` 는 PMS 원본 이식이고
    합성 픽스처로 잠겨 있다(`test_mrbacktest.test_kpi_conformance_vector_matches_pms`).
    그것이 정하는 것은 **진입·청산 시점**이고, 여기서 바꾸는 것은 **그 구간의
    돈을 어떻게 세는가**다. 잠긴 벡터는 그대로 통과한다.

    ## 왜 바꾸나

    종전 산술은 `평가 = 명목 × Δ스프레드` 하나였다 — **롤다운도 조달도 없었다.**
    실측(BSS-7Y 16건): 엔진이 안 세는 롤다운이 789만원인데 엔진 총손익이
    688만원이다. 안 세는 항이 세는 전부보다 크면 그건 근사가 아니라 다른 물건이다.

    그래서 BSS 를 **실제 자산스왑으로 가격해** 평가·캐리·롤다운·조달을 받는다
    (`cashbond.book_recon` — 백테스트·시뮬 대사가 쓰는 바로 그 함수). 비용만
    엔진의 것을 그대로 둔다 — `costBp` 는 전략의 노브지 상품의 성질이 아니다.

        그날 손익 = 평가 + 캐리 + 롤다운 + 조달 + 비용

    ## 선물 계열도 실가격이다 [2026-09-04]

    자산스왑은 아니지만 **자기 엔진의 실가격**이 있다: 선물 다리는 조정가 차분,
    FSW 의 IRS 다리는 스왑 엔진(`_mr_fut_recon`). 두 블록의 돈 합이 거래 손익과
    ±2원으로 닫힌다(실측 2026-09-04).

    거기에 **롤 비용**이 붙는다 [OWNER 2026-09-04 — "0.5틱으로 해두자"]. 종전에는
    분기마다 실제로 갈아타는데 그 왕복이 모형에 없었고(비용은 진입·청산 봉에만
    걸린다), 롤일 Δ 를 0 으로 마스크하는 근사가 그 사실을 가리고 있었다 — 마스크는
    벤더 내재금리 차분에만 참인 규약이라 조정가 위에서는 죽는다.

    **롤 마스크는 여기서 안 쓴다.** 엔진이 만든 `tradable` 은 근사의 부속이고,
    실가격 회계에서는 돈이 조정가에서 나므로 그 배열이 손익에 안 쓰인다. 시점은
    z 가 정하므로 거래 목록은 한 건도 안 움직인다(실측: `dv_bar` 는 `trade_mtm`·
    `dailyPnl` 에만 들어간다).

    ## 미청산 다리도 센다

    표본 끝에 열려 있는 다리는 `trades` 에 없지만 **총손익과 낙폭은 그것을
    실시간으로 지고 있다**(`mrbacktest` 의 그 주석 — 누적이 보유 봉마다 MTM 을
    더한다). 여기서 빼먹으면 그 구간의 봉이 통째로 0 이 되고 곡선이 거짓말을
    한다(실측 2026-09-03: BSS-9M 51봉·3Y 31봉이 그랬다). 그래서 청산일을
    마지막 봉으로 잡아 같이 돌린다.

    ## 달력이 어긋나는 날

    대사는 민평 달력, 엔진은 계열 달력이라 대사 행의 날이 봉에 없을 수 있다.
    **버리지 않는다** — 다음 봉으로 이월해서 얹는다. 그래야 거래의 세로합이
    대사표의 합과 한 자도 안 갈린다.
    """
    if kind not in ("bss", "fut", "fsw"):
        return False
    trades = r["trades"]
    if not trades:
        return False
    #: 대사를 돌릴 구간 — 거래들 + **미청산 다리**(청산일 = 마지막 봉).
    last_t = r["points"][-1]["date"] if r["points"] else None
    legs_to_price = [(t, t["entryDate"], t["exitDate"], t["direction"]) for t in trades]
    op = r.get("open")
    if op and last_t:
        legs_to_price.append((op, op["entryDate"], last_t, op["direction"]))
    m = None
    if kind == "bss":
        try:
            m = creditmatrix.load()
        except Exception:                              # noqa: BLE001
            return False

    #: 날짜 → 네 성분. 여러 거래가 한 날을 나눠 갖지 않는다(한 번에 한 포지션).
    day: dict[str, tuple[float, float, float, float]] = {}
    #: 날짜 → 그날 갈아타는 비용(양수). 선물 계열에만 선다.
    roll_day: dict[str, float] = {}
    per_trade: list[dict[str, float]] = []
    for obj, e_iso, x_iso, direction in legs_to_price:
        e_d, x_d = dt.date.fromisoformat(e_iso), dt.date.fromisoformat(x_iso)
        if kind == "bss":
            # 액면은 **거래마다 진입일 커브**로 잰다 — 그래야 「명목 N원/bp」가 모든
            # 거래에서 같은 뜻이 된다(`_mr_pv01_at` 머리의 검산).
            principal = _mr_principal_at(e_d, tenor, notional)
            if principal is None:
                return False
            # 회계는 **총계만** 쓴다 — 다리를 물으면 IRS 파 커브 범프가 거래마다
            # 붙어서(실측 5.55배) 전략 라우트가 통째로 느려진다. 다리는 거래를
            # 누를 때 `/api/mr/recon` 이 받는다.
            # **회계 경로는 창을 안 자른다** [2026-09-09] — 잘린 창은 반쪽이라
            # `None` 이 되고, 그러면 이 다리 전체가 엔진 근사로 되돌아간다.
            # 서빙 경로(`/api/mr/recon`)는 상수를 그대로 쓴다: 페이로드와
            # 응답시간은 한 자도 안 바뀐다(근거·실측은 `cashbond.RECON_MAX_DAYS`
            # 머리 — 이 경로가 `with_legs=False` 라 6배 싼 쪽이다).
            got = _mr_recon_rows(m, tenor, e_d, x_d, -int(direction), spec,
                                 max_days=None)
            if got is None:
                return False                           # 한 건이라도 못 재면 전부 안 바꾼다
            rows = _mr_scale_rows(got["rows"], principal / MR_REF_PRINCIPAL)
        else:
            got = _mr_fut_recon(sid, int(direction), notional, e_d, x_d,
                                with_krd=False)
            if got is None:
                return False
            # 블록의 행을 한 줄기로 편다. 두 달력(선물·IRS)이 어긋나도 아래에서
            # **날짜로** 봉에 얹으므로 합이 안 샌다.
            rows = [row for b in got["blocks"] for row in b["recon"]["rows"]]
            # 보유 중 롤일마다 **왕복 1틱** — 연결 계열은 상품이 아니라서
            # 갈아타기의 마찰을 따로 문다(`futures.roll_cost` 머리).
            rc = futures.roll_cost(got["face"])
            for d_iso in got["rolls"]:
                roll_day[d_iso] = roll_day.get(d_iso, 0.0) + rc
            obj["cost"] = (obj.get("cost") or 0.0) - rc * len(got["rolls"])
        agg = {"mtm": 0.0, "carry": 0.0, "rolldown": 0.0, "funding": 0.0}
        for row in rows:
            if row.get("actual") is None:
                continue                               # 이월 앵커 — 오늘의 돈이 아니다
            # **「그날 손익」이 정본이고 평가가 잔차를 진다** — `splitKrw` 의 그
            # 규칙(`lib/krw.ts`, 2026-08-14). 서버가 성분마다 따로 반올림하므로
            # `actual ≠ 평가+캐리+롤다운+조달` 이고(실측 거래당 최대 23원), 각자
            # 더하면 대사표의 합과 헤드라인이 갈린다. 한쪽이 잔차를 지면 **줄이
            # 반드시 가로로 더해지고** 표와 엔진이 한 자도 안 갈린다.
            c, rd, f = (row.get("carry") or 0.0), (row.get("rolldown") or 0.0), (row.get("funding") or 0.0)
            v = (row.get("actual") or 0.0) - c - rd - f
            prev = day.get(row["t"], (0.0, 0.0, 0.0, 0.0))
            day[row["t"]] = (prev[0] + v, prev[1] + c, prev[2] + rd, prev[3] + f)
            agg["mtm"] += v
            agg["carry"] += c
            agg["rolldown"] += rd
            agg["funding"] += f
        per_trade.append((obj, agg))

    # ── 봉에 얹는다. 봉에 없는 날은 **다음 봉으로 이월**한다(위 「달력」). ──
    carry_over = [0.0, 0.0, 0.0, 0.0]
    seen: set[str] = set()
    cum = 0.0
    trade_cum = 0.0
    for pt in r["points"]:
        d = pt["date"] if "date" in pt else pt["t"]
        got = day.get(d)
        if got:
            seen.add(d)
        v, c, rd, f = (
            (got[0] + carry_over[0], got[1] + carry_over[1],
             got[2] + carry_over[2], got[3] + carry_over[3]) if got
            else (carry_over[0], carry_over[1], carry_over[2], carry_over[3]))
        carry_over = [0.0, 0.0, 0.0, 0.0]
        # 롤 비용은 **비용 칸**에 든다 — 새 열을 만들지 않아야 대사표의
        # 「평가+캐리+롤다운+조달+비용 = 그날 손익」이 그대로 닫힌다.
        rc_today = roll_day.pop(d, 0.0)
        cost = pt["barCost"] - rc_today
        pt["barCost"] = cost
        pt["mtm"] = v
        pt["barCarry"] = c
        pt["barRolldown"] = rd
        pt["barFunding"] = f
        pt["dailyPnl"] = v + c + rd + f + cost
        cum += pt["dailyPnl"]
        pt["cumulativePnl"] = cum
        trade_cum = 0.0 if pt["position"] == 0 and pt["dailyPnl"] == 0 else trade_cum + pt["dailyPnl"]
        pt["tradePnl"] = trade_cum
    # 봉에 못 얹은 롤 비용 — 롤일은 선물 달력이고 봉도 그 달력이라 보통 0 이지만,
    # 남으면 마지막 봉이 진다(아래 돈과 같은 규율).
    left_roll = sum(roll_day.values())
    if abs(left_roll) > 1e-9 and r["points"]:
        last = r["points"][-1]
        last["barCost"] -= left_roll
        last["dailyPnl"] -= left_roll
        last["cumulativePnl"] -= left_roll
        last["tradePnl"] -= left_roll
    # 봉에 못 얹은 날 — 마지막 봉에 몰아 얹어 **한 자도 안 잃는다**.
    left = [sum(day[d][i] for d in day if d not in seen) for i in range(4)]
    if any(abs(x) > 1e-9 for x in left) and r["points"]:
        last = r["points"][-1]
        last["mtm"] += left[0]
        last["barCarry"] += left[1]
        last["barRolldown"] += left[2]
        last["barFunding"] += left[3]
        last["dailyPnl"] += sum(left)
        last["cumulativePnl"] += sum(left)
        last["tradePnl"] += sum(left)

    for obj, agg in per_trade:
        obj["mtm"] = agg["mtm"]
        obj["carry"] = agg["carry"]
        obj["rolldown"] = agg["rolldown"]
        obj["funding"] = agg["funding"]
        obj["pnl"] = (agg["mtm"] + agg["carry"] + agg["rolldown"]
                      + agg["funding"] + obj["cost"])

    r["summary"].update(mrbt.summarize(r["points"], trades))
    # 미청산 손익도 새 회계의 것으로 — 안 고치면 한 화면에 두 회계가 선다.
    r["summary"]["openPnl"] = op["pnl"] if op else None
    # 손익분기 비용도 총손익에 딸려 있다. 손익은 여전히 비용의 **정확한 일차식**
    # 이므로(비용을 따로 더한다) 닫힌형이 그대로 산다: 문 돈 대비 몇 배까지
    # 견디는가 = 1 + 총손익/문 돈 (`mrbacktest.breakeven_cost_bp` 의 그 산술).
    paid = -sum(p["barCost"] for p in r["points"])
    mult = None if paid <= 0 else 1.0 + r["summary"]["totalPnl"] / paid
    # 선물 계열은 문 돈에 **롤 비용**이 섞여 있고 그것은 편도 bp 에 비례하지
    # 않는다 — 그래서 「편도 N bp 까지 견딘다」로 옮길 수 없다. 배수만 말한다.
    if kind != "bss" or r["summary"].get("breakevenCostMult") is not None or mult is None:
        r["summary"]["breakevenCostMult"] = mult
        r["summary"]["breakevenCostBp"] = None
    else:
        r["summary"]["breakevenCostBp"] = None if mult is None else cost_bp * mult
    return True


def _mr_reconcilable(pts: list[dict], kind: str) -> list[dict]:
    """**대사할 수 있는 구간만** 엔진에 넣는다 [OWNER 2026-09-03 — "2020-01-02
    이전의 데이터를 안 보이게 해서 차단"].

    실가격 대사(`/api/mr/recon`)는 민평 행렬로 채권을 다시 가격하는데, 그 표는
    **2020-01-02 부터**다(실측: `credit_matrix` 전 bond_type 이 같은 날 시작,
    1,636일. MR 의 값 계열은 `imx_data.timeseries` 라 2014-05-28 부터라서 둘이
    갈린다). 그래서 종전에는 거래의 절반이 «대사할 수 없는 거래» 였다
    (BSS-7Y 34건 중 18건).

    **화면이 보여 주는 것은 전부 대사할 수 있어야 한다.** 그래서 표본을
    자른다 — 못 재는 구간의 성과를 세워 두고 「이 거래는 왜 표가 안 뜨죠」를
    받는 것보다, 아예 안 보이는 편이 정직하다.

    바닥은 **하드코딩하지 않는다** — 민평 행렬 자신의 첫 날을 읽는다. 데이터가
    뒤로 늘면 표본도 같이 는다(전량 캐시라 왕복이 안 는다:
    `creditmatrix.load` 는 워터마크가 같으면 재사용한다).

    민평에 아예 닿지 못하면 **자르지 않는다** — 대사는 못 서지만 값 계열은
    제 출처(imx)로 멀쩡하고, 못 읽었다고 6년을 지우는 것은 과하다.

    **선물 계열은 안 자른다.** 그쪽은 자산스왑이 아니라 실가격 경로 자체가
    없고(증거금·일일정산), 대사는 다리 표가 진다 — 민평 제약이 걸리지 않는
    자리다. 거기까지 자르면 얻는 것 없이 표본만 천 봉 잃는다(실측: FSW-3Y
    2,614 → 1,636).
    """
    if kind != "bss":
        return pts
    try:
        first = creditmatrix.load().dates[0].isoformat()
    except Exception:                                  # noqa: BLE001
        return pts
    return [p for p in pts if p["t"] >= first]


def _mr_leg(id: str, *, lookback: int, entryZ: float, exitZ: float, stopZ: float,
            costBp: float, notional: float, carry: bool, entryMode: str,
            timeStop: int, costModel: str, regime: str, reverseExit: bool,
            countOpen: bool, spec: funding.FundingSpec) -> dict:
    """한 계열의 **준비 + 시뮬** — 낱개 창과 통합 장부가 같은 것을 쓴다.

    2026-09-01 에 통합 밴드 워치(`/api/mr/book`)가 생기면서 갈라 냈다. 아홉
    만기를 한 장부로 더하는 화면에서 **통합의 수가 낱개 아홉의 합과 갈리면**
    그 화면은 아무 말도 못 하게 되므로, 계열 하나를 준비하는 자리는 하나여야
    한다: 단위 환산(%→bp)·방향·캐리·레짐 게이트·비용 경로·엔진 호출까지.

    반환은 화면 모양이 아니라 **재료**다 — 라우트가 각자의 페이로드로 썬다.
    """
    # 보드와 같은 유도 창구 — 선물·퓨처스왑도 여기서 같은 환산을 지난다.
    kinds = {s: kd for s, _, kd in mr_mod.SERIES}
    labels = {s: l for s, l, _ in mr_mod.SERIES}
    body = mr_mod.series_points(id)
    pts = [p for p in body["points"] if p.get("v") is not None]
    pts = _mr_reconcilable(pts, kinds[id])
    dates = [p["t"] for p in pts]
    # ⚠ **손익 산술은 bp 위에서 한다** [2026-08-28].
    #
    # 명목 노브의 단위는 `₩/bp` 인데 엔진은 `명목 × Δ값` 을 그대로 곱한다.
    # 계열의 값이 bp 면 맞지만 **선물 내재금리는 `%`** 라, 15.7bp 움직임이
    # Δ값 0.157 로 들어가 평가가 100배 작게 나왔다. 비용(`명목 × costBp`)과
    # 캐리(원금 환산이 `₩/bp` 기준)는 제 단위라, 결과는 «비용만 100배 무거운
    # 판» 이었다 — 실측 FUT-KTB3 승률 17%·SR −1.25 는 신호가 아니라 그것이다.
    # (`docs/MR_LANE_STATE.md` 의 «선물 넷은 전부 음수» 도 이 산술의 산물이다.)
    #
    # z·밴드는 눈금 변환에 불변이라 값이 안 바뀐다 — 바뀌는 것은 돈뿐이다.
    # 화면에 되돌려 줄 때는 계열의 자기 단위(%)로 나눠 보낸다.
    unit = body["unit"]
    scale = 100.0 if unit == "%" else 1.0
    vals = [float(p["v"]) * scale for p in pts]
    disp = (lambda v: round(v / scale, 4)) if scale != 1.0 else (lambda v: round(v, 4))
    if len(vals) < lookback + 1:
        raise HTTPException(status_code=422, detail=f"이력이 룩백보다 짧아요: {len(vals)} < {lookback + 1}")

    # 실행할 수 있는 방향만 재현한다 [OWNER 2026-08-25 — "BSS에서 숏은 없는거야,,
    # 현물대차매도는 안할거거든"]. 노브가 아니라 이 데스크의 사실이라 화면에
    # 스위치를 두지 않는다 — 백테스트의 현금채권이 매수만 받는 것과 같은 자리다.
    dirs = mr_mod.dirs_for(kinds[id])

    # ── 캐리 [OWNER 2026-08-27 — "중간에 CF는 상쇄되는건가?"] ──────────────────
    # 안 상쇄된다(`app/mrcarry.py` 머리에 다리별 산술). 원본 PMS 산술에는 이 항이
    # 없으므로 **끌 수 있게** 둔다 — `carry=false` 면 예전 수 그대로다.
    carry_krw: list[float] | None = None
    carry_defn: str | None = None
    #: 다리마다의 봉당 캐리(₩) — 대사표가 다리 줄에 세운다 [OWNER 2026-09-03].
    #: 엔진의 `c = -position * carry[i]` 가 선형이라 이 합이 총 캐리와 항등이다.
    carry_legs: list[tuple[str, list[float]]] = []
    if carry:
        # 커브·플라이는 다리가 둘·셋이라 **가중**이 있어야 캐리가 선다 —
        # DV01 중립이 그 거래의 정의이고, 가중은 지금 커브의 pv01 비다
        # [OWNER 2026-09-09 — 「스프레드(버터플라이나 커브)도 연결」].
        # 여기서 재서 넘기는 이유: pv01 은 커브를 아는 자리에서만 나오고
        # (`_curves["now"]`), `mrcarry` 를 커브에 묶으면 그 모듈이 SQL 을 또
        # 알게 된다.
        w = (mrc.combo_weights(id, lambda t: pv01(_curves["now"], TENOR_T[t]))
             if kinds[id] in ("irc", "irf") else None)
        rates, carry_defn = mrc.carry_rates(id, kinds[id], dates, spec, weights=w)
        leg_rates = mrc.carry_rates_by_leg(id, kinds[id], dates, spec, weights=w)
        if kinds[id] == "fut":
            # 선물은 캐리가 0 이다(증거금·일일정산 — `mrcarry` 머리). 원금 환산이
            # 없으므로 pv01 도 필요 없다. 종전에는 그걸 먼저 읽으려 해서
            # `TENOR_T["KTB3"]` 로 500 이 났다 — `FUT-KTB3` 의 「KTB3」은 만기
            # 라벨이 아니라 상품명이다. 기본이 `carry=true` 라 **선물 두 계열은
            # 전략 실험 창에서 아예 열리지 않았다**(실측 2026-08-28).
            carry_krw = [0.0] * len(dates)
            carry_legs = [(nm, [0.0] * len(dates)) for nm, _ in leg_rates]
        else:
            # 명목 노브가 ₩/bp(DV01)라 원금 환산이 필요하다 — 그 근거도 그 파일에.
            pv = pv01(_curves["now"], TENOR_T[mrc._tenor_of(id)])
            carry_krw = mrc.carry_krw(rates, dates, notional_per_bp=notional, pv01=pv)
            # 같은 환산을 다리마다 한 번씩 — `carry_krw` 가 봉마다 선형이라
            # (원금 × r/100 × 날수/365) 다리 합이 총합과 갈리지 않는다. 다만
            # **결측 처리가 갈릴 수 있어** 항등을 아래에서 실제로 잰다.
            carry_legs = [
                (nm, mrc.carry_krw(rr, dates, notional_per_bp=notional, pv01=pv))
                for nm, rr in leg_rates
            ]
            # 지어낸 분해를 화면에 올리지 않는다 — 합이 안 맞으면 다리를 안 싣는다.
            for i in range(len(dates)):
                if abs(sum(lg[i] for _, lg in carry_legs) - carry_krw[i]) > 1e-6:
                    carry_legs = []
                    break

    # 필터·비용 경로는 **서버가** 만든다(§16, 브라우저는 계산하지 않는다).
    # 값은 bp 로 환산한 `vals` 위에서 잰다 — 화면 단위(%)로 재면 선물 계열의
    # 변동성 백분위가 딴 계열이 된다.
    gate = mrg.gate_for(regime, vals)
    cost_series = mrg.cost_for(costModel, vals)

    # ── 롤일의 Δ 는 손익이 아니다 [OWNER 2026-09-02 — "롤일 Δ 를 0 으로 마스크"] ──
    #
    # 선물·퓨처스왑의 값은 벤더 **내재수익률**이라 수준은 옳지만, 계약이 갈리는
    # 날의 차분은 앞 계약의 마지막과 뒷 계약의 첫 값을 뺀 것이라 **아무도 실현할
    # 수 없다**. 실측(2026-09-02 적대 대사): FUT 거래 109건 중 35건이 >1bp 팬텀,
    # 최대 25.6bp/거래. 롤일을 정하는 규칙과 그 검증은 `futures.roll_days` 에.
    #
    # BSS 는 상수만기라 해당이 없다 — 마스크를 안 만들면 `None` 이 넘어가고
    # 엔진은 예전과 완전히 같은 수를 낸다.
    tradable = None
    if kinds[id] in ("fut", "fsw"):
        flags = [bool(p.get("roll")) for p in pts]
        tradable = [0.0] + [
            0.0 if flags[i] else (vals[i] - vals[i - 1]) for i in range(1, len(vals))
        ]

    r = mrbt.simulate(dates, vals, lookback=lookback, entry_z=entryZ,
                      exit_z=exitZ, stop_z=stopZ, cost_bp=costBp,
                      notional=notional,
                      allow_dirs=tuple(dirs["allowed"]),
                      carry=carry_krw, entry_mode=entryMode,
                      gate=gate,
                      time_stop=timeStop or None,
                      cost_bp_series=cost_series,
                      reverse_exit=reverseExit,
                      close_open_at_end=countOpen,
                      tradable_dv=tradable)

    # ── 회계를 백테스트·시뮬과 같은 것으로 [OWNER 2026-09-03] ────────────────
    # `simulate` 가 정한 **언제** 위에 실제 자산스왑의 **얼마** 를 얹는다.
    # 엔진 함수는 안 건드린다(잠긴 적합성 벡터가 그대로 통과한다) — 근거와
    # 한계는 `_mr_real_accounting` 머리에.
    real = _mr_real_accounting(
        r, sid=id, kind=kinds[id], tenor=mrc._tenor_of(id),
        notional=notional, cost_bp=costBp, spec=spec)

    return {"id": id, "label": labels[id], "kind": kinds[id], "unit": unit,
            # 이 다리의 수가 «실가격 회계» 인가 «엔진 근사» 인가. 두 회계가
            # 한 화면에 섞이면 화면이 그 사실을 말해야 한다.
            "real": real,
            "dates": dates, "vals": vals, "disp": disp, "dirs": dirs,
            "carryKrw": carry_krw, "carryDefn": carry_defn,
            "carryLegs": carry_legs,
            "gate": gate, "costSeries": cost_series, "r": r,
            # 롤 마스크의 재료 — 라우트가 봉마다 「거래 가능한 Δ」와 「그 봉이
            # 롤인가」를 그대로 실어야 대사표가 닫힌다. BSS 는 None·False 다.
            "tradable": tradable, "pts": pts}


#: 다리 손익·캐리 합이 엔진의 수와 이만큼 넘게 갈리면 **다리를 안 싣는다**.
#: 원 단위 표이므로 1원이 기준이다 — 잡티는 레벨의 4자리 반올림에서만 온다.
LEG_RECON_TOL_KRW = 1.0


def _attach_leg_recon(points: list[dict], *, kind: str,
                      leg_lv: dict[str, tuple[float, float]],
                      pts: list[dict], notional: float,
                      carry_legs: list[tuple[str, list[float]]],
                      levels_only: bool = False) -> None:
    """봉마다 **다리별 대사 줄**을 붙인다 [OWNER 2026-09-03 — "채권 KRD, bp,
    손익과 IRS KRD, bp, 손익, 그리고 종합 손익이 하루에 찍혀야 함"].

    ## 왜 서버가 하나

    §16 그대로다 — 브라우저는 계산하지 않는다. 다리 Δ 는 %레벨의 차이고,
    KRD 는 부호 규약이며, 손익은 엔진의 곱셈이다. 셋 다 화면에서 다시 하면
    화면과 엔진이 다른 수를 말할 자리가 생긴다.

    ## 산술 — 항등이 줄로 닫힌다

    값은 `v = (다리0 − 다리1) × 100`(bp)이고 엔진은 `mtm = hold × N × Δv` 다.
    그래서 Δv = Δ다리0 − Δ다리1 이고,

        mtm = (hold·N)·Δ다리0 + (−hold·N)·Δ다리1

    백테스트 대사표의 부호 규약(`손익 = −KRD × Δbp`)으로 옮기면

        KRD(다리0) = −hold·N      KRD(다리1) = +hold·N      합 = 0

    이다. **KRD 합이 0 인 것이 DV01 중립을 눈으로 보이는 자리**이고, 다리 손익의
    합이 평가와 같은 것이 이 표의 자기검사다. 다리가 하나인 계열(FUT 아웃라이트)
    은 KRD 가 하나뿐이라 합이 0 이 아니다 — 그때 표는 백테스트와 같은 3줄이다.

    캐리는 엔진이 `c = -position × carry[i]` 로 먹으므로 다리별도 같은 곱셈이다
    (`mrcarry.carry_rates_by_leg`).


    ## ⚠ 부호가 종전 「감도」 칸과 반대다

    종전 화면은 `감도 = hold × 명목` 을 싣고 `평가 = 감도 × Δ` 로 읽혔다 —
    국고 매수(`hold = −1`)의 감도가 **음수**였다. 백테스트·시뮬 대사표는 반대
    규약이고(`손익 = −KRD × Δbp`, **음수 KRD 가 페이·숏**), 이 표가 그 문법을
    쓰는 이상 부호도 그쪽을 따른다. 한 데스크가 두 화면에서 KRD 를 다르게
    읽으면 그게 사고다. 오너의 실물 표로 대조했다(2026-09-03):
    `KRD −509,059 · Δbp 0.75 · 손익 +381,795`.
    ## 롤일

    롤일은 봉 전체의 Δ 가 마스크된다(`futures.roll_days`). **다리도 같이 0 이다**
    — 한쪽만 살려 두면 「감도 × Δ = 손익」이 그 줄에서 안 닫힌다. 그 봉이 왜 0
    인지는 화면의 롤 표식이 말한다.

    ## 안 맞으면 안 싣는다

    합이 엔진의 수와 갈리면 `legs` 를 아예 안 붙인다 — 화면은 열이 없는 것을
    조용히 접고, 지어낸 분해가 대사표에 서지 않는다(이 리포의 그 규율).

    ## 실가격 회계에서는 **레벨만** 싣는다

    실가격 회계가 서면 그 구간의 돈은 자산스왑 대사가 센다 — 다리의 감도·손익·
    캐리는 폐기된 근사(`평가 = 명목 × Δ스프레드`)의 값이라 같이 세우면 한 화면에
    두 회계가 선다. 「일별 레벨」 칸이 쓰는 **레벨**은 근사와 무관한 사실이므로
    그것만 남긴다.
    """
    names = mrc.LEG_NAMES.get(kind)
    if not names:
        return
    n = len(points)

    # 봉마다의 다리 레벨(%). BSS 는 조인해 둔 표에서, 선물 계열은 계열 자신이
    # 실어 보낸 값에서 온다. 한 봉이라도 모르면 통째로 접는다.
    if kind == "bss":
        levels = [leg_lv.get(p["t"]) for p in points]
    else:
        levels = [tuple(q.get("legs") or ()) or None for q in pts]
    if len(levels) != n or any(lv is None or len(lv) != len(names) for lv in levels):
        return

    carry_by_name = dict(carry_legs)
    have_carry = all(nm in carry_by_name for nm in names)

    rows: list[list[dict]] = []
    for i, p in enumerate(points):
        hold = p["hold"]
        legs = []
        for j, nm in enumerate(names):
            if i == 0:
                dv = None
            elif p.get("roll"):
                dv = 0.0                      # 마스크 — 위 「롤일」 문단
            else:
                dv = (levels[i][j] - levels[i - 1][j]) * 100.0
            sign = -1.0 if j == 0 else 1.0    # KRD 부호 — 위 산술
            krd = sign * hold * notional
            mtm = 0.0 if (dv is None or hold == 0) else -krd * dv
            car = 0.0
            if have_carry and hold != 0:
                car = -hold * carry_by_name[nm][i]
            # `+ 0.0` 은 **음수 0 을 없앤다** — `-hold * 0.0` 이 `-0.0` 이 되고
            # JSON 을 타고 화면에서 「-0」 으로 선다(선물 다리의 캐리가 늘 그렇다).
            if levels_only:
                legs.append({"k": nm, "lvl": round(levels[i][j], 4)})
                continue
            legs.append({"k": nm, "lvl": round(levels[i][j], 4),
                         "dv": None if dv is None else round(dv, 4) + 0.0,
                         "krd": round(krd, 2) + 0.0, "mtm": round(mtm, 2) + 0.0,
                         "carry": round(car, 2) + 0.0})
        # 자기검사 — 합이 엔진의 수와 갈리면 통째로 접는다.
        if levels_only:
            rows.append(legs)
            continue
        if abs(sum(g["mtm"] for g in legs) - p["mtm"]) > LEG_RECON_TOL_KRW:
            return
        if have_carry and abs(sum(g["carry"] for g in legs) - p["carry"]) > LEG_RECON_TOL_KRW:
            return
        rows.append(legs)

    for p, legs in zip(points, rows):
        p["legs"] = legs


@router.get("/api/mr/strategy")
def mr_strategy(id: str, lookback: int = 60, entryZ: float = 2.0,
                # 손절 기본값 3.5 → **2.5** [OWNER 2026-09-09]. 프리셋이
                # 2026-09-08 에 갈렸는데(커밋 `74d8eb8f`) 기본값이 안 따라와
                # 초기 화면이 옛 값으로 서 있었다. 근거·프레임의 갈림은 프런트
                # `api.ts::MR_STRATEGY_DEFAULTS.stopZ` 주석에 있다(같은 값을 두
                # 곳에서 쓰므로 근거는 한 곳에만 적고 여기서 가리킨다).
                # ⚠ 사전등록 스크립트(`scripts/mr_live_wfo.py::STOP_Z`)의 3.5 는
                # 안 따라간다 — 그 값은 OOS 전에 못 박은 값이다.
                exitZ: float = 0.5, stopZ: float = 2.5,
                # 편도 비용 기본값 0.05 → 0.5 [OWNER 2026-08-28]. 0.05 은 첫 PMS 의
                # 값이고 이 데스크의 실측이 아니다 — 국고3Y·IRS3Y 패키지 실제 편도가
                # ≤0.5bp 라는 오너 답이 있으므로 **보수적인 쪽을 기본**으로 둔다.
                # 싸게 잡은 비용은 결론을 통째로 뒤집는다(볼린저 레인의 그 자리).
                costBp: float = 0.5, notional: float = 1_000_000.0,
                carry: bool = True, entryMode: str = "level",
                timeStop: int = 0, costModel: str = "flat",
                regime: str = "none", reverseExit: bool = False,
                countOpen: bool = False,
                fundingBasis: str = funding.DEFAULT_BASIS,
                fundingSpreadBp: float = funding.DEFAULT_SPREAD_BP) -> dict:
    """전략 실험 창 — 첫 PMS entry-signals 의 z-스코어 백테스트 재현(§16).

    산술은 `mrbacktest.py`(PMS 원본 이식·적합성 벡터로 잠금), 기본값도 그쪽
    기본(s16) 그대로다. 캐시 없음 — 파라미터가 자유값이고 계산이 밀리초라 태울 이유가 없다.

    방향은 계열이 정한다(`mr.dirs_for`) — BSS 는 국고 매수 쪽 한 방향뿐이다.
    파라미터가 아니라 이 데스크의 사실이라 쿼리로 열지 않는다.
    """
    labels = {s: l for s, l, _ in mr_mod.SERIES}
    if id not in labels:
        raise HTTPException(status_code=404, detail=f"unknown mr series {id}")
    _mr_check_knobs(lookback, entryZ, exitZ, stopZ, costBp, notional,
                    entryMode, timeStop, costModel, regime)

    # 준비·시뮬은 **공용 자리**가 한다(`_mr_leg`) — 통합 장부(`/api/mr/book`)가
    # 같은 함수를 아홉 번 부르므로, 통합의 수가 낱개 아홉의 합과 갈릴 수 없다.
    spec = _funding_spec(fundingBasis, fundingSpreadBp)
    leg = _mr_leg(id, lookback=lookback, entryZ=entryZ, exitZ=exitZ, stopZ=stopZ,
                  costBp=costBp, notional=notional, carry=carry,
                  entryMode=entryMode, timeStop=timeStop, costModel=costModel,
                  regime=regime, reverseExit=reverseExit, countOpen=countOpen,
                  spec=spec)
    dates, vals, disp = leg["dates"], leg["vals"], leg["disp"]
    tradable, pts = leg["tradable"], leg["pts"]
    dirs, carry_defn = leg["dirs"], leg["carryDefn"]
    carry_krw, gate, cost_series = leg["carryKrw"], leg["gate"], leg["costSeries"]
    carry_legs = leg["carryLegs"]
    r = leg["r"]

    # ── 액면 환산 [OWNER 2026-09-02 — "진입 레벨과 기준 노셔널과 같은 것들이
    # 전부 나올 수 있게 해야 이게 직접 대사가 가능하므로"] ────────────────────
    # 명목 노브는 DV01(₩/bp)인데 데스크의 주문 단위는 액면(억원)이다. 환산은
    # 캐리의 그 식(`mrcarry.carry_krw`: 원금 = 명목 / (pv01 × 1e-4))이고, 같은
    # 한계도 그대로다 — **지금 커브의 pv01 하나**를 전 기간에 쓰는 근사라
    # (위 «pv01 근사» 주석·`docs/MR_LANE_STATE.md` §6 ⑤) 화면이 「근사」를 같이
    # 적는다. 선물은 원금이 없다(증거금·일일정산) — 지어내지 않고 null 로 보낸다.
    principal = None
    #: 액면을 한 숫자로 못 적는 사유 — 화면이 빈칸에 이유를 쓴다(서버 문장 그대로).
    principal_note = None
    if leg["kind"] in ("irc", "irf"):
        # 커브·플라이는 **액면이 한 숫자가 아니다** — 사유와 산술은
        # `mr_combo_faces` 머리에. 지어내지 않고 다리별 액면을 문장으로 적는다.
        principal_note = (
            "다리마다 액면이 달라요(DV01 중립) — 지금 커브로 "
            + " · ".join(f"{t} {round(v) / 1e8:.1f}억"
                         for t, v in mr_combo_faces(id, notional))
            + " 예요."
        )
    elif leg["kind"] in ("fut", "fsw"):
        # 선물 계열의 액면은 **선물 DV01** 로 환산한다 [2026-09-04] — 스왑 pv01 이
        # 아니다. FSW 는 두 다리가 진입일 DV01 중립이라 스프레드 1bp 의 값이 곧
        # 선물 다리의 DV01 이고, 회계도 그 액면 위에서 돈다(`_mr_fut_recon`).
        # 머리의 수는 «지금 세우면» 이고 거래마다의 액면은 그 거래의 진입일
        # 커브가 정한다(BSS 와 같은 규약).
        _fid, _ft, _sg = MR_FUT_MAP[id]
        try:
            _fs = futures.load().series[_ft]
            _j = len(_fs.implied) - 1
            while _j >= 0 and _fs.implied[_j] is None:
                _j -= 1
            if _j >= 0:
                principal = {
                    "krw": round(futures.face_for_dv01(notional, _fs.implied[_j], _ft)),
                    # 선물은 연금계수(pv01)가 아니라 합성채 PVBP 로 환산한다 —
                    # 스왑의 항등(`명목 = 액면 x pv01 x 1e-4`)이 안 서는 자리라
                    # 그 칸을 비운다(공란 정책).
                    "pv01": None,
                }
        except (futures.FuturesError, KeyError, ValueError):
            principal = None
    else:
        pv = pv01(_curves["now"], TENOR_T[mrc._tenor_of(id)])
        # pv01 은 **무반올림** — 4자리로 내보냈더니 되곱한 명목이 14.66원/bp,
        # 8자리로도 원금 큰 단기 테너(6M 202억)에서 84원 어긋났다(2026-09-02
        # 독립 대사 두 판이 차례로 잡음). 페이로드가 항등의 양변(krw·pv01)을
        # 다 내보내면 그 항등은 페이로드 안에서 원 단위까지 닫혀야 한다 —
        # 화면 «약 35.4억» 은 못 보는 차이지만 손 대사는 본다.
        principal = {"krw": round(notional / (pv * 1e-4)), "pv01": pv}

    # ── 다리 레벨 [OWNER 2026-09-02 — "델타, 노셔널, 스왑 파 커브 상의 레벨,
    # 채권 커브 상의 레벨, CD금리 레벨이 진입시점에 확인되고 … 대사도 명확하게"]
    # 캐리가 읽는 그 출처(`mrseries` — 국고 커브·IRS 파·CD 91일)를 날짜로
    # 조인해 점마다 싣는다. BSS 의 값은 정확히 (국고 − IRS) × 100 이므로
    # (`mrseries.points`) 화면에서 «국고 − IRS = 레벨» 이 그대로 닫힌다.
    # CD 는 값의 전제(교집합)가 아니라 참고라, 없는 날은 null — 지어내지 않는다
    # (`legs(need_cd=False)` 의 넷째 값은 결측을 0.0 으로 채우므로 안 쓴다).
    # 선물·퓨처스왑은 다리가 이 셋이 아니라서 null 이다(선물내재 다리는 별도).
    leg_lv: dict[str, tuple[float, float]] = {}
    cd_lv: dict[str, float] = {}
    if leg["kind"] == "bss":
        ld, lg, ls, _ = mrs.legs(id)
        leg_lv = {d: (lg[i], ls[i]) for i, d in enumerate(ld)}
        cd_lv = mrs.bundle()["cd"]
    roll = r["roll"]
    points = [
        {
            "t": dates[i], "v": disp(vals[i]),
            "z": round(r["points"][i]["z"], 4) if r["points"][i]["z"] is not None else None,
            "ma": disp(roll["mean"][i]) if roll["mean"][i] is not None else None,
            # 밴드 배수는 entryZ 다 — PMS 의 «노브 하나, 뜻 둘» 그대로.
            "up": disp(roll["mean"][i] + entryZ * roll["std"][i])
                  if roll["mean"][i] is not None else None,
            "lo": disp(roll["mean"][i] - entryZ * roll["std"][i])
                  if roll["mean"][i] is not None else None,
            # ── 대사표가 곱셈을 눈으로 닫게 하는 둘 [OWNER 2026-08-28] ────────
            # `hold` = 그 봉을 **통과해서 들고 있던** 포지션(엔진 부호). 봉이 끝난
            # 뒤의 `pos` 와 다르다 — 진입 봉은 0, 청산 봉은 ±1 이다. 백테스트
            # 대사표가 「전일 종가 KRD」를 싣는 것과 같은 자리이고, 이유도 같다:
            # 감도 × 변화 = 평가 가 **한 줄 안에서** 닫혀야 한다.
            # `dv` = 그 봉의 **거래 가능한** 변화(**bp**). 브라우저는 계산하지
            # 않는다(§16). 롤일이 마스크된 계열(선물·퓨처스왑)에서는 그 봉이
            # 0 이고, 그래야 대사표의 「감도 × 명목 × Δ = 평가」가 줄마다 닫힌다
            # — 화면이 수준의 차(거래 불가)를 Δ 로 적으면 그 줄만 안 맞는다.
            # 수준 자체(`v`·진입/청산 레벨)는 안 건드린다.
            "hold": r["points"][i]["hold"],
            "dv": (round(tradable[i], 4) if tradable is not None
                   else round(vals[i] - vals[i - 1], 4)) if i > 0 else None,
            # 그 봉이 롤이라 Δ 를 못 싣는가 — 화면이 「왜 0 인가」를 말할 수 있게.
            "roll": bool(pts[i].get("roll")) if tradable is not None else False,
            # 거래 안 누적 — 대사표의 세로합을 줄마다 적는다(마지막 줄 = 거래 손익).
            "tradePnl": round(r["points"][i]["tradePnl"], 2),
            # 밴드 밖 여부와 연속 일수 — 측정 보드(`mr._state`)와 같은 어휘로,
            # 「지금 어디에 서 있나」를 오실레이터의 판독이 말할 수 있게.
            "out": r["points"][i]["out"], "outRun": r["points"][i]["outRun"],
            "cum": round(r["points"][i]["cumulativePnl"], 2),
            # 그날의 분해 — 거래를 누르면 화면이 이 셋으로 **일별 대사**를 편다.
            # 셋의 합 = `pnl`(그날 손익)이고, 대사표가 그 항등을 잰다.
            "mtm": round(r["points"][i]["mtm"], 2),
            "carry": round(r["points"][i]["barCarry"], 2),
            # 롤다운·조달은 **실가격 회계에서만** 온다(엔진 근사에는 그 항이
            # 없다). 없으면 열이 조용히 접힌다 — 0 으로 채우면 «그날 롤다운이
            # 0 이었다» 는 거짓말이 된다.
            **({"rolldown": round(r["points"][i]["barRolldown"], 2),
                "funding": round(r["points"][i]["barFunding"], 2)}
               if leg["real"] else {}),
            "cost": round(r["points"][i]["barCost"], 2),
            "pnl": round(r["points"][i]["dailyPnl"], 2),
            "pos": r["points"][i]["position"],
        }
        for i in range(len(vals))
    ]
    # 다리 레벨을 점에 붙인다(위 주석) — 스프레드(bp)와 달리 **%** 그대로다.
    # 반올림 4자리 = 이 앱의 % 레벨 문법(fmtLevel)과 같은 자리라, 화면의
    # (국고 − IRS) × 100 이 레벨 칸(2자리 bp)과 표시 정밀도에서 닫힌다.
    for p in points:
        gv = leg_lv.get(p["t"])
        c = cd_lv.get(p["t"])
        p["govt"] = round(gv[0], 4) if gv else None
        p["irs"] = round(gv[1], 4) if gv else None
        p["cd"] = round(c, 4) if c is not None else None
    _attach_leg_recon(points, kind=leg["kind"], leg_lv=leg_lv, pts=pts,
                      notional=notional, carry_legs=carry_legs,
                      levels_only=leg["real"])
    trades = [
        {
            "entryT": t["entryDate"], "exitT": t["exitDate"],
            "dir": t["direction"],
            "entryZ": round(t["entryZ"], 2),
            # 청산 z 는 **None 일 수 있다** — 타임스탑은 z 를 안 보므로(엔진
            # 규약: 지표가 비는 구간에 포지션이 갇히는 것을 막는 문) time 청산이
            # σ=0(z=null) 봉에 앉을 수 있고, countOpen 의사거래도 마지막 봉이
            # σ=0 이면 같다. 무가드 round 가 유효 노브 조합(lookback 2~600 ×
            # timeStop)에서 창을 통째로 500 으로 죽였다(2026-09-02 적대 대사가
            # 잡음 — 진입 z 는 신호가 z 를 요구하므로 None 이 될 수 없다).
            "exitZ": round(t["exitZ"], 2) if t["exitZ"] is not None else None,
            "entryV": disp(t["entryValue"]), "exitV": disp(t["exitValue"]),
            # 진입 직전의 밴드 밖 구간 — 「무엇을 보고 들어갔나」. `touch` 에서는
            # 진입 z 가 밴드 선 언저리라 이것 없이는 4σ 까지 갔다 온 것과 2.01σ 를
            # 살짝 넘었다 온 것이 같은 줄로 보인다.
            "outFrom": t["outFrom"], "outDays": t["outDays"],
            "peakZ": round(t["peakZ"], 2) if t["peakZ"] is not None else None,
            # 보유 동안의 총 변화(bp) — 대사표 합계 줄의 Δ.
            "dv": round(t["dv"], 4),
            # 체결비용까지 문 Δ [OWNER 2026-09-09 — "체결비용이 델타에는
            # 반영되게 해야 직관적으로 델타와 손익을 비교 가능"]. 산술은
            # `_mr_dv_net` 머리에 — 「2bp 움직였는데 1.9bp 만 남았다」.
            "dvNet": mrm.dv_net(t["dv"], t["cost"], t["direction"], notional),
            # 보유 중 롤을 몇 번 지났나 — 0 이 아니면 「청산 − 진입 ≠ Δ」가
            # 정상이다(그 차이가 곧 실현 못 한 롤 점프다).
            "masked": int(t.get("masked", 0)),
            "pnl": round(t["pnl"], 2), "why": t["exitReason"],
            # 대사용 삼분해 — 셋의 합이 `pnl` 이다. 거래 한 줄을 눌렀을 때
            # 화면이 그 항등을 그대로 보여 준다(이 앱의 3분해 문법).
            "mtm": round(t["mtm"], 2),
            "carry": round(t["carry"], 2),
            # 실가격 회계에서만 오는 둘 — 엔진 근사에는 그 항이 없다.
            **({"rolldown": round(t["rolldown"], 2),
                "funding": round(t["funding"], 2)} if leg["real"] else {}),
            "cost": round(t["cost"], 2),
            "bars": t["bars"],
        }
        for t in r["trades"]
    ]
    s = r["summary"]
    return {
        "id": id, "label": labels[id], "unit": leg["unit"],
        # 계열 종류 — 화면이 «이 계열에 있는 다리» 를 알아야 각주가 거짓말을
        # 안 한다(국고 다리가 없는 계열에 「국고 다리는 민평 기준」을 적던
        # 자리다 — 선물 넷과 커브·플라이 열둘에서 거짓이었다).
        "kind": leg["kind"],
        "asof": dates[-1] if dates else None,
        "params": {"lookback": lookback, "entryZ": entryZ,
                   "exitZ": exitZ, "stopZ": stopZ, "costBp": costBp,
                   "notional": notional, "entryMode": entryMode,
                   "timeStop": timeStop, "costModel": costModel,
                   "regime": regime, "reverseExit": reverseExit,
                   "countOpen": countOpen},
        # 명목(₩/bp)의 액면 환산 — 위 주석의 근사. 거래 표·대사표가 「이 손익을
        # 내려면 실제로 몇 억을 걸어야 했나」를 적을 수 있게 낸다.
        # 이 실행의 수가 «실가격 회계» 인가 «엔진 근사» 인가 — 화면이 그 사실을
        # 말해야 한다. 선물 계열은 자산스왑이 아니라 늘 근사다.
        "real": leg["real"],
        "principal": principal,
        # 액면이 한 숫자가 아닌 계열(커브·플라이)의 사유 — 없으면 null.
        "principalNote": principal_note,
        # 비용이 봉마다 다르면 「편도 몇 bp」가 한 숫자로 안 나온다 — 실제로 쓴
        # 범위와 중앙값을 화면이 적을 수 있게 낸다.
        "cost": ({"model": "flat", "bp": costBp} if cost_series is None else {
            "model": "dynamic",
            "lo": round(min(cost_series), 3), "hi": round(max(cost_series), 3),
            "mid": round(sorted(cost_series)[len(cost_series) // 2], 3),
        }),
        # 필터가 지운 진입 신호 — 조용히 빠지면 「신호가 없었다」로 읽힌다.
        # 방향 때문에 못 한 것(`dirs.blocked`)과 **따로** 센다.
        "gated": r["gated"],
        # ── 진단 [OWNER 2026-08-28 — "승률이 이렇게 높을 수 있다는게 이해가 잘
        # 안간다" · "과거에 Overfitting 된거 아닌가"] ──────────────────────────
        # 의심 둘 다 화면 밖에서만 답할 수 있었다. 산술은 `app/mrdiag.py`.
        "diag": {
            "exits": mrd.exit_tally(r["trades"], notional),
            "payoff": mrd.payoff(r["trades"], notional),
            # 청산 규칙을 떼고 신호일의 고정 보유 수익을 잰다 — 승률이 진입의
            # 공로인지 청산 구조의 산물인지가 여기서 갈린다.
            "forward": mrd.forward_edge(
                vals, roll["z"], entry_z=entryZ,
                allow_dirs=tuple(dirs["allowed"]), entry_mode=entryMode),
            # 구간을 갈라 같은 규칙을 잰다 — 과거적합이면 최근이 무너지고,
            # 엣지 소멸이면 크기만 단조로 줄어든다. 모양이 다르다.
            "periods": mrd.period_split(dates, r["points"]),
        },
        # 캐리가 무엇인지 화면이 읽을 문장 — 부호 기준이 −1 이라 정의가 없으면
        # 읽는 사람이 자기 방향으로 읽는다(`mr.KIND_DEFN` 과 같은 규율).
        # 조달은 **있는 계열에만** 적는다 — 커브·플라이는 스왑끼리라 원금을
        # 주고받지 않아서 조달 항이 아예 없다(`mrcarry.CARRY_DEFN` 의 그 문장).
        # 화면이 「조달은 기준금리 +10bp 예요」를 그 계열에서 적으면 없는 항을
        # 있다고 말하는 것이다.
        "carry": ({"on": carry, "defn": carry_defn,
                   **({} if leg["kind"] in ("irc", "irf") else {"funding": spec.label})}
                  if carry else {"on": False}),
        "points": points,
        "trades": trades,
        # 방향의 이름과 «못 들어간 신호» — 조용히 빠진 진입은 «신호가 없었다»
        # 로 읽히므로 세어서 같이 보낸다(엔진의 blocked).
        "dirs": {**dirs, "blocked": r["blocked"]},
        # 표본 끝의 미청산 다리 — 거래·승률에는 원본 규약대로 안 들어가고,
        # 「안 들어갔다」는 사실만 화면이 승률 옆에 적을 수 있게 낸다.
        "open": ({
            "entryT": r["open"]["entryDate"],
            # ── 미청산 다리도 **거래 줄의 어휘를 다 갖는다** [OWNER 2026-09-09
            #    — "미청산도 PnL에 포함하기"] ────────────────────────────────
            # 총손익·낙폭은 종전에도 이 다리를 실시간으로 지고 있었다
            # (`mrbacktest` 의 그 주석 — 누적이 보유 봉마다 MTM 을 더한다).
            # 빠져 있던 것은 **거래 표**였다: 표의 세로합이 누적과 갈리고, 열려
            # 있는 손익이 목록 어디에도 없었다. 그래서 낱개 창이 이 줄을 표의
            # 마지막에 세울 수 있게 같은 열들을 채워 보낸다 — 승률·거래 수는
            # 원본 규약대로 **안 건드린다**(그 둘을 바꾸는 것은 `countOpen`
            # 노브의 일이고, 긴 표본에서 기각된 노브다).
            #
            # 「청산」 쪽 값은 **마지막 봉**이다(청산이 아니라 지금 평가다) —
            # 그 사실은 화면의 사유 칸(「미청산」)이 말한다.
            "exitT": dates[-1] if dates else None,
            "exitV": points[-1]["v"] if points else None,
            "exitZ": points[-1]["z"] if points else None,
            # Δ·롤 횟수는 봉에서 센다 — 엔진의 `close_open_at_end` 가 같은
            # 구간을 같은 배열로 더하고(그 블록), 여기서 또 유도하면 두 수가
            # 갈릴 자리가 생기므로 **이미 페이로드에 있는 봉의 Δ** 를 쓴다.
            "dv": round(sum(p["dv"] or 0.0
                            for p in points[r["open"]["entryIdx"] + 1:]), 4),
            "dvNet": mrm.dv_net(
                sum(p["dv"] or 0.0 for p in points[r["open"]["entryIdx"] + 1:]),
                r["open"]["cost"], r["open"]["direction"], notional),
            "masked": sum(1 for p in points[r["open"]["entryIdx"] + 1:] if p["roll"]),
            # 성분 — 거래 줄과 같은 분해(실가격 회계에서는 다섯, 근사는 셋).
            "mtm": round(r["open"]["mtm"], 2),
            "carry": round(r["open"]["carry"], 2),
            **({"rolldown": round(r["open"]["rolldown"], 2),
                "funding": round(r["open"]["funding"], 2)}
               if leg["real"] and "rolldown" in r["open"] else {}),
            "cost": round(r["open"]["cost"], 2),
            # 방향 — 화면이 미청산 다리를 차트에 세우려면 필요하다(마커의 색이
            # 방향이다). 승률·거래 수에 안 들어가는 것과 별개의 사실이다.
            "dir": r["open"]["direction"],
            "entryZ": round(r["open"]["entryZ"], 2),
            "entryV": disp(r["open"]["entryValue"]),
            "outFrom": r["open"]["outFrom"], "outDays": r["open"]["outDays"],
            "peakZ": (round(r["open"]["peakZ"], 2)
                      if r["open"]["peakZ"] is not None else None),
            "pnl": round(r["open"]["pnl"], 2),
            "bars": r["open"]["bars"],
        } if r["open"] else None),
        # 한 칸 옆 — 고른 칸이 이웃보다 얼마나 나은지가 그 칸의 신뢰도다.
        # **머리 숫자와 같은 규칙으로** 돈다(필터·비용·타임스탑까지) — 기준점이
        # 다르면 그 차이가 노브 탓인지 규칙 탓인지 화면이 구분해 주지 못한다.
        "neighbors": _mr_neighbors(
            dates, vals,
            {"lookback": lookback, "entryZ": entryZ, "exitZ": exitZ,
             "stopZ": stopZ, "costBp": costBp, "notional": notional},
            tuple(dirs["allowed"]), carry=carry_krw, entry_mode=entryMode,
            gate=gate, time_stop=timeStop or None, cost_bp_series=cost_series,
            reverse_exit=reverseExit, close_open_at_end=countOpen),
        # ── 구간별 성과 [OWNER 2026-09-04 — "지난 1년, 지난 1분기, 지난
        #    1개월을 전역 설정값으로 두고 이를 조정하면 성과도 바뀌게"] ──────
        # 네 벌을 **한 번에** 낸다. 엔진은 전체 표본에서 한 번만 돌고(룩백
        # 워밍업이 구간 앞에 있어야 z 가 선다 — `mrmetrics` 머리 §구간),
        # 바뀌는 것은 채점뿐이라 네 벌의 값이 봉 배열을 네 번 훑는 값이다.
        # 그래서 화면의 구간 고르개는 재실행도 stale 도 안 만든다.
        # 자본 기준 = **액면**(원금) [OWNER 2026-09-09] — Ulcer 를 무단위로 세우고
        # 연환산 수익률을 비율로 내는 분모다. 「지금 커브」의 한 값이라 표본 안에서
        # 5~16% 움직이는 근사이고(`principal` 주석), 못 세우면 그 칸이 «—» 다.
        "spans": mrm.spans_for(dates, r["points"], r["trades"], costBp,
                               (principal or {}).get("krw")),
        "summary": {
            "totalPnl": round(s["totalPnl"], 2),
            "maxDrawdown": round(s["maxDrawdown"], 2),
            "winRate": round(s["winRate"], 4) if s["winRate"] is not None else None,
            "sharpe": round(s["sharpe"], 3) if s["sharpe"] is not None else None,
            "numTrades": s["numTrades"],
            "openPnl": round(s["openPnl"], 2) if s["openPnl"] is not None else None,
            # 총손익이 0 이 되는 편도 비용 — 노브를 돌려 찾는 대신 닫힌형으로.
            "breakevenCostBp": (round(s["breakevenCostBp"], 3)
                                if s["breakevenCostBp"] is not None else None),
            # 비용이 봉마다 다르면 「몇 bp」가 한 숫자로 안 나온다 — 대신 **그
            # 경로의 몇 배까지 견디는가**를 답한다. 안 내보내면 동적 비용 판에서
            # 화면의 손익분기 칸이 통째로 비어 버린다(실측 2026-08-28).
            "breakevenCostMult": (round(s["breakevenCostMult"], 3)
                                  if s.get("breakevenCostMult") is not None else None),
            # 누적 손익의 성분 [OWNER 2026-09-09 — "누적 채권 + 스왑 손익을
            # 롤다운 캐리로 분해해서 보여주기"]. 봉마다 이미 서 있던 다섯을
            # 더하기만 한다(`mrmetrics.split` 머리 — 정의는 v1 대사 엔진의 것).
            "split": mrm.split(r["points"]),
        },
    }


@router.get("/api/mr/optimize")
def mr_optimize(id: str, span: str = "all",
                lookback: int = 60, entryZ: float = 2.0,
                exitZ: float = 0.5, stopZ: float = 2.5,
                costBp: float = 0.5, notional: float = 1_000_000.0,
                carry: bool = True, entryMode: str = "level",
                timeStop: int = 0, costModel: str = "flat",
                regime: str = "none", reverseExit: bool = False,
                countOpen: bool = False,
                fundingBasis: str = funding.DEFAULT_BASIS,
                fundingSpreadBp: float = funding.DEFAULT_SPREAD_BP) -> dict:
    """근사 최적화 격자 — 다섯 노브의 프리셋을 전부 돌린 표 [OWNER 2026-09-04].

    **비용·명목·실전 규칙은 안 흔든다.** 비용은 그날 그 종목의 호가폭이고
    명목은 이 데스크의 포지션 크기라 최적화할 대상이 아니다(`mr.STRATEGY_PRESETS`
    머리의 그 규율). 실전 규칙 다섯은 긴 표본에서 이미 기각됐다 — 격자에 넣으면
    화면이 «이걸 켜 보면 좋아질까» 를 다시 묻게 된다.

    `/api/mr/strategy` 와 **같은 준비 자리**(`_mr_leg`)를 지난다. 별도 라우트인
    이유는 `/api/mr/recon` 이 갈라져 있는 이유와 같다: 162칸이 본체보다 비싸서
    누를 때만 돈다.
    """
    labels = {s: l for s, l, _ in mr_mod.SERIES}
    if id not in labels:
        raise HTTPException(status_code=404, detail=f"unknown mr series {id}")
    if span not in dict(mrm.SPANS):
        raise HTTPException(status_code=422, detail=f"모르는 구간이에요: {span}")
    _mr_check_knobs(lookback, entryZ, exitZ, stopZ, costBp, notional,
                    entryMode, timeStop, costModel, regime)

    spec = _funding_spec(fundingBasis, fundingSpreadBp)
    leg = _mr_leg(id, lookback=lookback, entryZ=entryZ, exitZ=exitZ, stopZ=stopZ,
                  costBp=costBp, notional=notional, carry=carry,
                  entryMode=entryMode, timeStop=timeStop, costModel=costModel,
                  regime=regime, reverseExit=reverseExit, countOpen=countOpen,
                  spec=spec)
    got = _mr_optimize(
        leg["dates"], leg["vals"],
        {"lookback": lookback, "entryZ": entryZ, "exitZ": exitZ, "stopZ": stopZ,
         "costBp": costBp, "notional": notional, "entryMode": entryMode},
        tuple(leg["dirs"]["allowed"]), span=span,
        carry=leg["carryKrw"], gate=leg["gate"],
        time_stop=timeStop or None, cost_bp_series=leg["costSeries"],
        reverse_exit=reverseExit, close_open_at_end=countOpen,
        tradable_dv=leg["tradable"])
    # 이 표의 수는 **엔진 근사**다 — 머리 카드가 실가격이면 둘이 다르다.
    # 화면이 그 사실을 적을 수 있게 같이 보낸다(`MrStrategyRun.real` 과 같은 값).
    return {"id": id, "label": labels[id], "real": False,
            "headReal": leg["real"], **got}


def _mr_cost_span(legs: list[dict]) -> dict | None:
    """아홉 다리가 **실제로 문** 비용의 범위와 중앙값 — 동적 비용일 때만.

    첫 다리의 경로만 적으면 안 된다: 동적 비용은 그 만기의 변동성 백분위에
    연동하므로 만기마다 다른 경로다. 화면이 「편도 0.15~0.25bp」라고 적을 때
    그건 장부 전체가 문 비용이어야 한다.
    """
    paths = [c for leg in legs if leg["costSeries"] is not None for c in leg["costSeries"]]
    if not paths:
        return None
    return {"model": "dynamic", "lo": round(min(paths), 3), "hi": round(max(paths), 3),
            "mid": round(sorted(paths)[len(paths) // 2], 3)}


#: 대사가 설 수 없는 이유들 — 화면이 그대로 읽는 문장이다. 「없다」가 아니라
#: **왜 없는지**를 말한다(이 리포의 그 규율 — 빈칸으로 렌더하느니 이유를 쓴다).
MR_RECON_WHY = {
    "before": "민평 이력은 {first} 부터예요 — 이 거래는 그 앞이라 실가격 대사를 "
              "세울 수 없어요.",
    "after": "민평 이력은 {last} 까지예요 — 이 거래는 그 뒤예요.",
}


@router.get("/api/mr/recon")
def mr_recon(id: str, entry: str, exit: str, notional: float = 1_000_000.0,
             dir: int = -1,
             fundingBasis: str = funding.DEFAULT_BASIS,
             fundingSpreadBp: float = funding.DEFAULT_SPREAD_BP) -> dict:
    """MR 거래 하나의 **실가격 일별 대사** [OWNER 2026-09-03 — "krd에서 원래는
    테너별로 민감도 찍어줬잖아 … 이 방향이 정확한 대사니까"].

    ## 왜 자산스왑을 세우나

    BSS 는 **국고 매수 · IRS 페이**이고, 그게 이 앱의 자산스왑(`cashbond` 의
    `ASW`)과 같은 구조다. 그래서 새 가격기를 짓지 않고 그쪽을 그대로 부른다 —
    민평 노드를 1bp 씩 범프해 채권을 다시 가격하는 그 기계(`_krd_bond`)가
    **테너별 KRD** 를 만든다. 응답 모양은 `backtest.book_recon` 과 같아서 화면이
    `ReconStack` 으로 그대로 그린다.

    ## 표는 **다리 둘**이다 [OWNER 2026-09-04 — 「국고매수랑 IRS Pay가 별개로」]

    행마다 `legs: [국고, IRS]` 가 실린다(`with_legs=True`). 다리마다 **자기 커브**
    위에 선다: 국고는 민평 노드·Δ민평, IRS 는 IRS 노드·ΔIRS.

    종전에는 한 벌이었고 그 자가 섞여 있었다 — `krd` 는 `_krd_bond` 라 국고 다리
    것만인데 `dbp` 는 `asw_series` 라 «민평 − IRS» 스프레드여서, `추정 = −(국고
    KRD) × Δ스프레드` 였다. par-par 자산스왑의 1차 근사로는 성립하지만 한 다리의
    감도에 두 다리의 Δ 를 곱한 것이고, 그 몫이 전부 잔차로 갔다(실측 2026-09-04,
    9봉 거래: Σ|잔차| 199만 → 6.4만원). 스프레드 관점은 화면에서 은퇴했다
    [OWNER — 「없앤다」]. 페이로드의 행 수준 `krd`·`dbp`·`est` 는 백테스트·시뮬
    표가 아직 그 모양을 쓰기 때문에 남아 있다.

    IRS 다리의 KRD 는 파 커브를 노드마다 흔드는 값이라 **여기서만** 켠다
    (`cashbond.book_recon` 의 `with_legs` 머리 — 250일 창에서 6.9배). 전략
    라우트의 회계는 총계만 쓰므로 끈 채로 돈다.

    ## 이 수는 백테스트의 수와 **다르다**

    이 리포의 자산스왑은 **par-par(같은 명목)이고 DV01 중립이 아니다**
    [OWNER 2026-08-14]. MR 엔진은 반대로 DV01 중립(명목이 스프레드 ₩/bp
    하나)이라, 실가격 손익이 엔진 손익보다 체계적으로 크다(실측 2026-09-03,
    BSS-7Y 거래별 +0.7백만~+3.5백만원). 그 차이는 결함이 아니라 **잔여
    금리노출과 캐리·롤다운·조달을 실제로 센 값**이고, 화면이 둘을 나란히 적어
    「근사와 실제가 이만큼 다르다」를 보이게 한다 [OWNER 2026-09-03].

    ## 못 세우는 자리는 비워 둔다

    민평 행렬은 2020-01-02 부터라 MR 표본(2014-06~)의 절반이 그 앞이다
    (실측: BSS-7Y 16/34 · BSS-3Y 17/38). 그때는 표 대신 **왜 없는지**를
    돌려준다 — 지어낸 대사를 세우지 않는다 [OWNER 2026-09-03].

    별도 라우트인 이유는 `cashbond` 가 이미 아는 것과 같다: KRD 범프가 본체보다
    비싸서 거래를 **누를 때만** 돈다.
    """
    kinds = {s: kd for s, _, kd in mr_mod.SERIES}
    if id not in kinds:
        raise HTTPException(status_code=404, detail=f"unknown mr series {id}")

    tenor = mrc._tenor_of(id)                      # noqa: SLF001 — 같은 레인
    try:
        entry_d = dt.date.fromisoformat(entry)
        exit_d = dt.date.fromisoformat(exit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"날짜가 이상해요: {exc}")

    if kinds[id] != "bss":
        # ── 선물 계열 [OWNER 2026-09-04] ───────────────────────────────────
        # 자산스왑은 아니지만 자기 엔진의 실가격이 있다. 표는 **블록**으로 오고
        # 화면에서는 **어느 계열이든 하나**다 [OWNER 2026-09-07]: FUT 은 선물
        # 달력, FSW 는 그 안에 IRS 다리가 들어와 하루 일곱 줄(`with_legs` —
        # `_mr_fut_recon` 머리). 민평 제약이 안 걸리는 자리라 표본도 안 자른다.
        got = _mr_fut_recon(id, int(dir), notional, entry_d, exit_d,
                            with_krd=True, with_legs=True)
        if got is None:
            return {"available": False,
                    "why": "선물 대사를 못 세웠어요 — 그 구간의 종가나 IRS 마킹이 "
                           "빠져 있어요."}
        rc = futures.roll_cost(got["face"])
        # `legTenors` 는 **있을 때만** 싣는다 — 화면의 열은 두 다리의 합집합인데
        # (`reconTenors`), 빈 목록을 보내면 그 함수가 다리 판으로 들어가 놓고
        # 열을 하나도 못 세운다. 없으면 그 질문이 없는 것이다(FUT 아웃라이트).
        return {
            "available": True,
            "blocks": [{"name": b["name"],
                        "tenors": b["recon"]["tenors"],
                        "rows": b["recon"]["rows"],
                        "truncated": bool(b["recon"].get("truncated")),
                        **({"legTenors": b["recon"]["legTenors"]}
                           if b["recon"].get("legTenors") else {})}
                       for b in got["blocks"]],
            # 액면과 그 액면을 만든 DV01 — 페이로드 안에서 환산이 닫혀야 손
            # 대사가 선다(BSS 의 `principal` 과 같은 규율).
            "principal": {"krw": round(got["face"]), "pv01": None},
            # 롤 비용은 **비용 칸**에 이미 들어가 있다 — 화면이 그 사실을 말한다.
            "roll": {"days": len(got["rolls"]), "won": round(rc),
                     "dates": got["rolls"]},
        }

    try:
        m = creditmatrix.load()
    except creditmatrix.CreditMatrixError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if entry_d < m.dates[0]:
        return {"available": False,
                "why": MR_RECON_WHY["before"].format(first=m.dates[0].isoformat())}
    if exit_d > m.dates[-1]:
        return {"available": False,
                "why": MR_RECON_WHY["after"].format(last=m.dates[-1].isoformat())}

    # 명목 노브는 ₩/bp(DV01)인데 자산스왑의 명목은 **액면**이다. 환산은
    # **그 거래의 진입일 커브**로 한다 — 엔진이 같은 자를 쓰므로 표와 헤드라인이
    # 갈리지 않는다(`_mr_pv01_at` 머리의 검산).
    principal = _mr_principal_at(entry_d, tenor, notional)
    if principal is None:
        return {"available": False,
                "why": "진입일 커브를 못 읽어서 액면을 못 세워요."}
    spec = _funding_spec(fundingBasis, fundingSpreadBp)
    # 엔진 부호 `-1` 이 **국고 매수**다(`mr.dirs_for` — BSS 는 한 방향뿐).
    # 자산스왑의 `direction` 은 채권 쪽 부호라 뒤집어 넘긴다(`_mr_recon_rows`
    # 안에서 포지션이 선다 — 캐시 키가 그 인자들이다).
    # **엔진과 같은 길을 지난다** — 기준 액면에서 한 번 재고 배수로 쓴다. 각자
    # 재면 반올림이 벌어져 표와 헤드라인이 갈린다(`_mr_scale_rows` 머리).
    got = _mr_recon_rows(m, tenor, entry_d, exit_d, -int(dir), spec, with_legs=True)
    if got is None:
        return {"available": False,
                "why": "대사를 못 세웠어요 — 구간이 너무 길거나 민평이 그 날들을 "
                       "다 갖고 있지 않아요."}
    rec = {"tenors": got["tenors"],
           "rows": _mr_scale_rows(got["rows"], principal / MR_REF_PRINCIPAL),
           "truncated": False, "available": True}
    if got.get("legTenors"):
        rec["legTenors"] = got["legTenors"]
    # 액면과 **그 액면을 만든 pv01** 을 같이 싣는다 — 페이로드 안에서
    # `명목 = 액면 × pv01 × 1e-4` 이 닫혀야 손 대사가 선다(이 리포의 그 규율).
    rec["principal"] = {"krw": round(principal),
                        "pv01": _mr_pv01_at(entry_d, TENOR_T[tenor])}
    return rec


@router.get("/api/mr/book/optimize")
def mr_book_optimize(span: str = "all",
                     lookback: int = 60, entryZ: float = 2.0,
                     exitZ: float = 0.5, stopZ: float = 2.5,
                     costBp: float = 0.5, notional: float = 1_000_000.0,
                     carry: bool = True, entryMode: str = "level",
                     timeStop: int = 0, costModel: str = "flat",
                     regime: str = "none", reverseExit: bool = False,
                     countOpen: bool = False,
                     fundingBasis: str = funding.DEFAULT_BASIS,
                     fundingSpreadBp: float = funding.DEFAULT_SPREAD_BP) -> dict:
    """통합 장부의 근사 최적화 격자 [OWNER 2026-09-07].

    노브는 `/api/mr/book` 과 **완전히 같다**(구간만 더 받는다). 두 라우트가 다른
    기본값에서 열리면 「지금 칸」이 격자 안에서 자기 자리를 못 찾는다.

    낱개 격자보다 아홉 배 비싸다 — 별도 라우트인 이유가 그것이고(누를 때만
    돈다), 산술과 한계는 `_mr_book_optimize` 머리에 있다.
    """
    if span not in dict(mrm.SPANS):
        raise HTTPException(status_code=422, detail=f"모르는 구간이에요: {span}")
    _mr_check_knobs(lookback, entryZ, exitZ, stopZ, costBp, notional,
                    entryMode, timeStop, costModel, regime)
    spec = _funding_spec(fundingBasis, fundingSpreadBp)

    legs: list[dict] = []
    excluded: list[dict] = []
    for sid, label in mrbook.bss_series():
        try:
            legs.append(_mr_leg(
                sid, lookback=lookback, entryZ=entryZ, exitZ=exitZ, stopZ=stopZ,
                costBp=costBp, notional=notional, carry=carry,
                entryMode=entryMode, timeStop=timeStop, costModel=costModel,
                regime=regime, reverseExit=reverseExit, countOpen=countOpen,
                spec=spec))
        except (HTTPException, KeyError, ValueError) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            excluded.append({"id": sid, "label": label, "reason": str(detail)})
    if not legs:
        raise HTTPException(status_code=422,
                            detail="통합할 수 있는 만기가 하나도 없어요")

    got = _mr_book_optimize(
        legs,
        {"lookback": lookback, "entryZ": entryZ, "exitZ": exitZ, "stopZ": stopZ,
         "costBp": costBp, "notional": notional, "entryMode": entryMode},
        span=span, time_stop=timeStop or None, reverse_exit=reverseExit,
        close_open_at_end=countOpen)
    # 격자는 **엔진 근사**다(낱개와 같은 계약) — 머리 카드가 실가격이면 둘이
    # 다르고, 화면이 그 사실을 적어야 한다.
    return {"id": mrbook.BOOK_ID, "label": mrbook.BOOK_LABEL, "real": False,
            "headReal": all(leg["real"] for leg in legs),
            "excluded": excluded, **got}


@router.get("/api/mr/book")
def mr_book(lookback: int = 60, entryZ: float = 2.0,
            exitZ: float = 0.5, stopZ: float = 2.5,
            costBp: float = 0.5, notional: float = 1_000_000.0,
            carry: bool = True, entryMode: str = "level",
            timeStop: int = 0, costModel: str = "flat",
            regime: str = "none", reverseExit: bool = False,
            countOpen: bool = False,
            fundingBasis: str = funding.DEFAULT_BASIS,
            fundingSpreadBp: float = funding.DEFAULT_SPREAD_BP) -> dict:
    """BSS 테너 **통합** 밴드 워치 [OWNER 2026-09-01 — "BSS 테너 통합 밴드 워치를
    하나 만들어서 승률 및 세부사항들을 확인할 수 있게"].

    같은 규칙을 아홉 만기에 **동시에** 걸었을 때의 한 장부다. 계열 하나의 준비·
    시뮬은 낱개 창과 **같은 함수**(`_mr_leg`)가 하고, 이 라우트는 그 아홉을
    `mrbook.aggregate` 로 더하기만 한다 — 통합의 수와 낱개 아홉의 합이 갈릴 수
    있는 자리를 아예 안 만든다.

    노브는 `/api/mr/strategy` 와 **완전히 같다**(`id` 만 없다). 두 창이 다른
    기본값에서 열리면 「낱개로는 벌고 통합으로는 잃는다」가 규칙 탓인지 기본값
    탓인지 화면이 구분해 주지 못한다.

    캐시 없음 — 파라미터가 자유값이고 아홉 번 돌아도 초 단위다.
    """
    _mr_check_knobs(lookback, entryZ, exitZ, stopZ, costBp, notional,
                    entryMode, timeStop, costModel, regime)
    spec = _funding_spec(fundingBasis, fundingSpreadBp)

    legs: list[dict] = []
    excluded: list[dict] = []
    for sid, label in mrbook.bss_series():
        try:
            legs.append(_mr_leg(
                sid, lookback=lookback, entryZ=entryZ, exitZ=exitZ, stopZ=stopZ,
                costBp=costBp, notional=notional, carry=carry,
                entryMode=entryMode, timeStop=timeStop, costModel=costModel,
                regime=regime, reverseExit=reverseExit, countOpen=countOpen,
                spec=spec))
        except (HTTPException, KeyError, ValueError) as exc:
            # 못 선 만기는 **조용히 빠지지 않는다**(보드의 exclusions 문법).
            # 여덟 만기의 합을 「BSS 통합」이라 부르면서 그 사실을 안 적으면
            # 화면이 거짓말을 한다.
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            excluded.append({"id": sid, "label": label, "reason": str(detail)})
    if not legs:
        raise HTTPException(status_code=422,
                            detail="통합할 수 있는 만기가 하나도 없어요 — "
                                   + (excluded[0]["reason"] if excluded else "이력이 없어요"))

    span = _mr_cost_span(legs)
    out = mrbook.aggregate(legs, notional=notional, cost_bp=costBp,
                           dynamic_cost=span is not None)
    first = legs[0]
    # 막힌 진입은 방향 사전 안으로 들어간다(낱개 라우트와 같은 자리) — 집계에서
    # 꺼내 두고 나머지를 펼친다. 딕셔너리 안에서 pop 하면 평가 순서에 기대게 된다.
    blocked = out.pop("blocked")
    return {
        "id": mrbook.BOOK_ID, "label": mrbook.BOOK_LABEL, "defn": mrbook.BOOK_DEFN,
        # 값 단위는 아홉이 다 bp 다(국고 − IRS). 손익 단위와 헷갈리지 않게 적어 둔다.
        "unit": first["unit"],
        "params": {"lookback": lookback, "entryZ": entryZ,
                   "exitZ": exitZ, "stopZ": stopZ, "costBp": costBp,
                   "notional": notional, "entryMode": entryMode,
                   "timeStop": timeStop, "costModel": costModel,
                   "regime": regime, "reverseExit": reverseExit,
                   "countOpen": countOpen},
        # 방향은 아홉이 같다(전부 BSS) — 낱개 창과 같은 사전을 쓰고, 막힌 진입
        # 수만 아홉을 더한 것이다.
        "dirs": {**first["dirs"], "blocked": blocked},
        "cost": span if span is not None else {"model": "flat", "bp": costBp},
        "carry": ({"on": True, "defn": first["carryDefn"], "funding": spec.label}
                  if carry else {"on": False}),
        "excluded": excluded,
        **out,
    }


@router.get("/api/volatility")
def volatility() -> dict:
    # Relative-ATR list rows + across-tenor curve, all precomputed (§16).
    return payloads.volatility(_dataset, _bases, _volatility)


@router.get("/api/instruments")
def instruments() -> dict:
    """What the 시뮬레이션 tab can book, grouped the way the tabs are.

    The monitor already divides the world into 아웃라이트/스프레드/버터플라이/
    포워드; the simulation's position entry offers the same list rather than a
    bare tenor picker, so "3s10s" means one thing in this product.
    """
    return instruments_mod.catalog()


@router.post("/api/instruments/expand")
def expand_instrument(body: dict) -> dict:
    """One instrument line → the swap legs the engine prices.

    LIVE, and it has to be: the leg weights are DV01-neutral at the base date's
    curve, and §16 says the browser computes nothing. The response rows are
    already in the shape /api/simulate takes.
    """
    try:
        series_id = str(body["seriesId"])
        direction = int(body.get("direction", 1))
        notional = float(body["notional"])
        base = dt.date.fromisoformat(str(body["baseDate"])[:10])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"seriesId·notional·baseDate가 필요해요 ({exc})",
        )
    if notional <= 0:
        raise HTTPException(status_code=422, detail="명목은 0보다 커야 해요.")
    try:
        legs = instruments_mod.expand(_dataset, series_id, direction, notional, base)
    except BacktestError as exc:
        # 다리를 못 세우는 이유는 사용자가 고칠 수 있는 것들이다 — 그 날 호가가
        # 없거나, 데이터 범위를 벗어난 날짜거나. 500이 아니라 이유를 말한다.
        raise HTTPException(status_code=422, detail=str(exc))
    return {"seriesId": series_id, "kind": instruments_mod.kind_of(series_id), "legs": legs}


# The monitor first, then the simulation — the order the reader meets them, and
# the order the tabs sit in. FastAPI matches on the full path and the two sets
# are disjoint, so nothing here depends on the order; it is for whoever reads
# the file next.
#
#     this module   /api/health  /api/wall/summary  /api/series/{id}
#                   /api/forwards  /api/dv01/{id}  /api/backtest
#                   /api/volatility
#     market_data   /api/market-data/range  /api/market-data/live
#                   /api/market-data/{valuation_date}
#     credit_curve  /api/credit-curve/taxonomy  /api/credit-curve/series
#     positions     /api/positions  /api/positions/summary
#     simulate      /api/simulate
app.include_router(router)
app.include_router(market_data.router)
app.include_router(credit_curve.router)
app.include_router(positions.router)
app.include_router(simulate.router)
