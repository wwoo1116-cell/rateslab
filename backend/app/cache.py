"""On-disk cache for the own-history distributions (Session final Pass D).

The forward-matrix own-history percentiles bootstrap each historical date's
curve once and reprice all 168 forwards (~13s), and the curve heatmap scans
every node's history. That is a one-time computation over a file that changes
once a day, so it should not be paid on every restart.

The cache is keyed by a hash of the source data file PLUS a schema version.
On a match the payload is loaded; on a miss or mismatch it is recomputed and
rewritten — and that recompute is logged LOUDLY, because a cache keyed to the
wrong data is worse than no cache, and this project's recurring defect is
silent degradation.

SCHEMA_VERSION exists because the trap fired (annual-stats session): the
forwards payload's `range10y` was renamed `range1y`, the DATA had not
changed, and the disk cache silently served the old shape to new frontend
code. Bump it whenever a cached payload's SHAPE changes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Callable

log = logging.getLogger("sauron.cache")

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"

# Bump on ANY change to a cached payload's shape (field renames included).
# 4 = WTD/QTD dropped from every deltas/values block, and KEY_FORWARDS
#     re-picked (3Mx3M/9Mx3M in, 2Yx2Y/3Yx3Y out) — both change the cached
#     forwards payload's shape and content, and a v3 cache would be served
#     with the old keys still in it.
# v5 (2026-08-03, V-PASS V5): forward derivation SKIPS dates whose curve
# cannot price the span (curve_prices_span) — 3Mx3M loses its ten served-0.0%
# rows from early 2016, and short-start cells' movePct/range histories shrink
# by the same dates. Same xlsx bytes, different derived content: without the
# bump a v4 cache would keep serving the zeros.
# v6 (2026-08-04): the regret replay restricts to the 주요 sets [OWNER] —
# same xlsx bytes, different cached `regret` content (44 → 29 lines); a v5
# cache would keep serving the non-주요 lines.
# v7 (2026-08-05): the 전일종가 rule drops today-dated rows at load — the
# SAME xlsx bytes now produce different dataset content on different days
# (the intraday row a Tuesday load drops is included by a Wednesday load).
# The bump clears v6 caches; the `asof` component below is what keeps the
# key honest ACROSS days from here on.
# v8 (2026-08-14, v2-local): 세타가 페이로드에 들어왔다 — 행마다 `theta`,
# 요약에 `thetaBasis`. 같은 xlsx/같은 SQL 행이 **다른 내용**을 만든다는 뜻이라
# 키가 바뀌어야 한다. 안 바꾸면 v7 캐시가 세타 없는 요약을 계속 내주고, 화면은
# 전 종목 em dash 를 그리면서 아무 에러도 내지 않는다 — 이 리포가 반복해서
# 밟는 조용한 스테일 결함 그대로다.
# v9 (2026-08-14, v2-local): `policy` 에 `upcoming`(앞으로 남은 금통위 날짜)이
# 붙었다 — 시뮬레이션의 기준금리 이벤트가 읽는다. 같은 xlsx 가 **다른 모양**의
# 요약을 만든다는 뜻이고, 안 바꾸면 v8 캐시가 그 필드 없는 요약을 계속 내준다.
# 화면은 날짜 후보가 하나도 없는 빈 목록을 그리면서 아무 에러도 안 낸다.
# v10 (2026-08-25): `mr` 페이로드가 12계열 → BSS 전 테너로 갈렸다 [OWNER "일단
# 본드스왑만"] — 행에서 group/groupLabel 이 빠지고 rank 가 붙고, asof 가 소스별
# 셋에서 하나로 줄고, excluded 가 생겼다. 같은 SQL 이 **다른 모양**을 만든다는
# 뜻이라 안 올리면 v9 의 12계열 캐시가 새 프런트에 그대로 서빙된다 — 이 파일
# 머리가 적어 둔 바로 그 함정이다.
# v11 (2026-08-25): `mr` 유니버스에 국채선물 내재금리·퓨처스왑이 들어왔다
# [OWNER "선물 들어왔는데 … 반영하기"] — 행에 kind/defn 이 붙고 asof 가
# {bss, fut} 두 소스로 갈라졌다. 같은 SQL 이 다른 모양을 만든다.
# v12 (2026-08-26): `universe` 에 **퓨처스왑 행 둘**(FSW-KTB3·FSW-KTB10, 새
# kind "futuresswap")과 `sources.futuresswap` 이 들어왔다 [OWNER "선물, 퓨처스왑도
# 스왑·현금채권과 같은 분류에"]. 같은 SQL 이 다른 모양을 만든다 — 안 올리면 v11
# 캐시가 그 행 없는 유니버스를 계속 내주고, 화면은 새로 살린 탭을 **빈 표**로
# 그리면서 아무 에러도 안 낸다(이 파일 머리가 적어 둔 그 함정).
# v13 (2026-09-01): `mr` 페이로드에 **`watch`**(BSS 통합 한 줄)가 붙었다
# [OWNER "밴드워치 랭킹 순위, 계열 밑에 따로 하나 빼주면 되겠다"]. 같은 SQL 이
# 다른 모양을 만든다 — 안 올리면 v12 캐시가 그 필드 없는 보드를 계속 내주고,
# 화면은 통합 줄을 **아예 안 그리면서** 아무 에러도 안 낸다(이 파일 머리가 적어
# 둔 그 함정 그대로다. 실측 2026-09-01: 라우트를 고치고 백엔드를 재기동했는데도
# `watch` 가 응답에 없었다).
# v14 (2026-09-02): `mr` 행의 fut `defn` 문장을 정정했다 — 「선물 종가의
# 내재수익률 (5% 합성)」은 2026-08-25 이후 파이프라인(벤더 내재 직독)에서
# 거짓이고 KTB3 는 역사 구간에서 5% 합성 역산과 중앙 58bp 어긋난다(적대 대사
# 실측). 같은 SQL 이 다른 문장을 만든다 — 안 올리면 v13 캐시가 옛 문장을 계속
# 내준다.
# v15 (2026-09-02): 보드 밴드의 σ 를 표본(ddof=1)에서 **모집단**으로 바꿨다
# [OWNER — "엔진(모집단 σ)으로 통일"]. 같은 SQL 이 다른 z·밴드·상태를 만든다
# (창 60 에서 σ 가 0.84% 작아지고, BSS-3Y 2,958봉 중 9봉은 밴드 안팎이 뒤집힌다).
# 안 올리면 v14 캐시가 옛 규약의 밴드를 계속 내준다.
# v16 (2026-09-09): `mr` 행에 **`triggers`·`triggerBlocked`** 가 붙었다
# [OWNER "누르면 얼마 레벨에서는 매수 추천과 같은 플로우"] — 밴드 경계를 「얼마
# 레벨이면 어느 다리인가」로 옮겨 적은 칸이다. 같은 SQL 이 다른 모양을 만든다 —
# 안 올리면 v15 캐시가 그 필드 없는 보드를 계속 내주고, 화면은 히어로의 트리거
# 문장과 상세 카드의 「트리거」 칸을 **아예 안 그리면서** 아무 에러도 안 낸다
# (v13 에서 `watch` 로 실제로 밟은 그 함정 — 이번에도 재기동만 하고 한 번 밟았다).
# v17 (2026-09-09): `mr` 유니버스에 **IRS 커브·플라이 열둘**이 들어왔다
# [OWNER "스프레드(버터플라이나 커브와 같은 것도 연결해주기)" — 축은 IRS].
# 보드가 13행 → 25행이고 `asof` 에 셋째 소스(`irs`)가 붙었다. 같은 SQL 이 다른
# 모양을 만든다 — 안 올리면 v16 캐시가 13행 보드를 계속 내주고, 화면은 새 계열을
# **아예 안 그리면서** 아무 에러도 안 낸다(v13·v16 에서 이미 두 번 밟은 그 함정).
# v18 (2026-09-09): 통합 장부의 봉에 **`cost`(그날 문 비용 · 지불액 양수)** 가
# 붙었다. 화면이 쓰는 칸은 아니고 **다른 레인이 읽는 칸**이다 — 모멘텀 레인이
# 공통 창에서 MR 의 비용 쿠션을 다시 재려다 「장부 캐시가 일별 비용을 안 들고
# 있다」로 막혀 있었다(`HANDOFF-momentum` §11-2). 안 올리면 v17 캐시가 그 칸 없는
# 장부를 계속 내주고, 그쪽 스크립트는 **KeyError 도 아니고 그냥 못 재는** 상태로
# 남는다.
SCHEMA_VERSION = 18


def data_hash(path: Path, asof: "object | None" = None) -> str:
    """SHA-256 of the source file's bytes + the payload schema version, plus
    the dataset's effective as-of date when given — changes iff the data, the
    cached payloads' shape, OR the 전일종가 cutoff's effect changes.

    `asof` exists because file bytes stopped determining content (v7): a row
    dated "today" is dropped at load, so the same file re-read after midnight
    yields a different dataset. Callers that cache derived payloads MUST pass
    `dataset.asof`; the bytes-only form remains for content-change checks."""
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    tail = f":{asof.isoformat()}" if asof is not None else ""
    return f"{digest}:v{SCHEMA_VERSION}{tail}"


def sql_data_hash(asof: "object | None" = None) -> str:
    """`data_hash` 의 MySQL 판 — 해시할 **바이트가 없을 때**의 캐시 키.

    CLAUDE.md 가 이 이동에서 유일하게 못 박아 둔 것이 이 자리다:

        `app/cache.py` keys the disk cache on a HASH OF THE XLSX BYTES. With
        the source in MySQL that key has nothing to hash, and a cache keyed to
        the wrong data is worse than no cache (this project's recurring defect
        is silent staleness). It has to become a table watermark —
        `MAX(updated_at)` plus a row count.

    그 지시대로 **테이블 워터마크**(마지막 날짜 + 행 수)가 바이트 해시를 대신
    한다. 행이 늘거나 마지막 날짜가 밀리면 키가 바뀌고 캐시가 무효가 된다.
    `asof` 는 엑셀 판과 같은 이유로 붙는다 — 같은 테이블도 전일종가 컷 때문에
    날이 바뀌면 다른 데이터셋이 된다.

    **못 잡는 것**: 이 테이블에는 `updated_at` 이 없다(컬럼이 irs_date + 값 15개
    뿐, PK 도 인덱스도 없음). 과거 행의 값이 조용히 수정되면 날짜도 행 수도 안
    바뀌므로 이 키는 그대로다. 잡으려면 값 전체의 해시가 필요하고 그건 매번
    2,600행 × 16열을 읽는 일이라, 그 비용을 치를지는 별도 판단으로 남긴다.
    [미해결, 2026-08-07]
    """
    from .mysqldb import watermark

    last, rows = watermark()
    tail = f":{asof.isoformat()}" if asof is not None else ""
    return f"sql:{last}:{rows}:v{SCHEMA_VERSION}{tail}"


def cached(
    name: str,
    current_hash: str,
    compute: Callable[[], object],
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> object:
    """Return the cached payload for `name` if its stored hash matches
    `current_hash`; otherwise compute, persist, and return it. Loud on miss."""
    f = Path(cache_dir) / f"{name}.json"
    if f.exists():
        try:
            blob = json.loads(f.read_text(encoding="utf-8"))
            if blob.get("hash") == current_hash:
                log.info("[cache] %s: loaded from disk (hash match)", name)
                return blob["payload"]
            log.warning(
                "[cache] %s: STALE — source data changed, recomputing", name
            )
        # AttributeError/TypeError are in here for a reason: a file holding
        # valid JSON that is not an object (`[1,2,3]`, `null`) has no `.get`,
        # and that used to escape as a crash on startup rather than a
        # recompute. Every unreadable cache must degrade the same way.
        except (OSError, ValueError, KeyError, AttributeError, TypeError) as e:
            log.warning("[cache] %s: unreadable (%s), recomputing", name, e)
    else:
        log.warning("[cache] %s: MISSING, computing", name)

    payload = compute()
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    # Write through a temp file and rename. A direct write that dies partway
    # leaves a half file which the next start recovers from — correctly, but
    # only after paying the full recompute. os.replace is atomic on both
    # POSIX and Windows, so a killed process leaves either the old file or
    # the new one, never a torn one.
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"hash": current_hash, "payload": payload}), encoding="utf-8"
    )
    os.replace(tmp, f)
    return payload
