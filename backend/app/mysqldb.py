"""IRS 종가의 두 번째 출처 — MySQL(MariaDB) `sim_portfolio` [OWNER, 2026-08-07].

CLAUDE.md 가 예고해 둔 이동이다: "Both halves move onto MySQL — the existing
database at miraebond2.kro.kr:4004". 이 파일은 그 첫 조각이고, **읽기 전용**이다.

## 읽기 전용이라는 말의 뜻

권한 이야기가 아니라 **코드 이야기**다. 이 모듈에는 INSERT/UPDATE/DELETE 를 낼
길이 없다 — `read_sql()` 하나만 내보내고, 그 함수는 `SELECT` 또는 `SHOW` 로
시작하지 않는 문장을 거부한다. 커넥션도 `autocommit=True` 로 열어 트랜잭션을
쌓지 않는다. 나중에 누가 쓰기를 붙이려면 이 파일을 고쳐야 하고, 그 diff 는
리뷰에서 보인다.

## 왜 SQLAlchemy 인가

풀 때문이다. FastAPI 워커가 넷이고 각 요청이 커브를 만들 때마다 연결을 새로
열면, 원격 MariaDB 왕복(수십 ms)이 캐시 미스마다 붙는다. `QueuePool` 이 연결을
재사용하고 `pool_pre_ping` 이 끊긴 연결을 조용히 되살린다 — 이 DB 는 사무실
네트워크 너머에 있어서 유휴 연결이 죽는다.

## 접속 정보

**환경변수에만 있다. 기본값은 없다.**

2026-08-07 에는 하드코딩이 승인돼 있었다 [OWNER — "코드에 상수로 하드코딩해도
됨"]. 그때는 리모트가 하나(비공개)였고 배포가 없었다. 2026-08-20 의 배포 준비
지시가 그 판단을 갈음한다 [OWNER — "mysqldb.py 의 os.getenv 기본값(평문
비밀번호) 제거 → 미설정이면 죽게"]. 리포는 이제 GitHub(rateslab)에 있고,
백엔드는 Funnel 로 공개된다.

미설정이면 `engine()` 이 `MissingCredentials` 로 죽는다. **import 때가 아니라
첫 연결 때**인 이유는 두 가지다: 엑셀만 만지는 경로(정적 굽기, 대부분의 테스트)
가 DB 없이도 돌아야 하고, 클린 호스트에서 `requirements.txt` 만 깔고 import 가
통하는지 보는 검증(BACKEND.md)이 자격증명 없이도 성립해야 한다. 대신 죽을 때는
어느 변수가 비었는지 이름으로 말한다 — 조용히 옛 상수로 붙는 일은 없다.

히스토리에 남아 있는 예전 값은 이 패스의 범위 밖이다.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Any, Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, Row

log = logging.getLogger("app.mysqldb")

class MissingCredentials(RuntimeError):
    """접속 정보가 환경에 없다. 기본값으로 때우지 않는다."""


#: 이름만 여기 있고 값은 없다. `_settings()` 가 부를 때마다 환경을 읽는다 —
#: 모듈 로드 시각에 굳혀 두면 테스트가 `monkeypatch.setenv` 로 못 바꾼다.
ENV_VARS = ("BW_MYSQL_HOST", "BW_MYSQL_PORT", "BW_MYSQL_USER", "BW_MYSQL_PASSWORD", "BW_MYSQL_DB")


def _settings() -> tuple[str, int, str, str, str]:
    """다섯 값. 하나라도 비어 있으면 **이름을 대며** 죽는다."""
    values = {name: (os.getenv(name) or "").strip() for name in ENV_VARS}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise MissingCredentials(
            "MySQL 접속 정보가 없습니다: " + ", ".join(missing) + ". "
            "백엔드를 띄우는 셸에서 설정하세요(.env.example 에 이름이 있습니다). "
            "예전에 코드에 있던 기본값은 2026-08-20 배포 준비에서 지웠습니다."
        )
    port_raw = values["BW_MYSQL_PORT"]
    if not port_raw.isdigit():
        raise MissingCredentials(f"BW_MYSQL_PORT 가 숫자가 아닙니다: {port_raw!r}")
    return (
        values["BW_MYSQL_HOST"],
        int(port_raw),
        values["BW_MYSQL_USER"],
        values["BW_MYSQL_PASSWORD"],
        values["BW_MYSQL_DB"],
    )

#: IRS 종가 테이블. 같은 스키마에 이름이 뒤집힌 `irs_mkt_close` 도 있는데 그건
#: 이 테이블이 아니다 — 오너가 지목한 것은 `mkt_irs_close` 다.
IRS_CLOSE_TABLE = "mkt_irs_close"

#: **보충 출처** — 데스크의 인포맥스 시계열 창고. 같은 서버, 다른 스키마
#: (`sim_portfolio` 아님). 2026-10-07 에 붙였다: `mkt_irs_close` 가 10-06 종가를
#: 안 들고 있는데 **같은 서버의 이 테이블에는 이미 와 있었다**. 출처가 둘이고
#: 하나가 섰다 — 9-22 국고 전수조사에서 밟은 그 모양이다.
#:
#: 쓰는 범위는 **하루**로 묶어 둔다 (`imx_irs_day`). 과거사를 여기로 갈아타지
#: 않는 이유는 엑셀 폴백과 같다: 출처가 날마다 바뀌면 차트에 유령 점프가 생긴다.
IMX_TIMESERIES_TABLE = "imx_data.timeseries"

#: 이 창고에는 IRS 가 출처별로 네 계열 담겨 있고(TP1·KMB·실거래TRD·종합ALL),
#: 종합ALL 만 산다 — 나머지 셋은 2026-09-11 에서 멈춰 있다(2026-10-07 실측).
#: 종합ALL 을 고른 근거는 **대조**다: `mkt_irs_close` 와 전 13테너·겹친 34,528칸에서 불일치 14건(0.04%)·최대 1.00bp 이고,
#: 그 14건이 **전부 8Y(8건)·9Y(6건)** 다 — 나머지 11테너는 2,656일 전부 자릿수까지
#: 같다. (★처음엔 2Y·5Y·10Y 셋만 재서 「1,308칸 0건」이라 적었다. 골라 쟨 수였고,
#: 2026-10-07 에 SQL 자신의 10-06 행이 도착했을 때 8Y 가 0.25bp 어긋나 드러났다.)
IMX_IRS_CATEGORY = "스왑-IRS(종합ALL)"

_engine: Engine | None = None


def engine() -> Engine:
    """풀을 든 엔진 하나. 첫 호출에서 만들고 그다음부터 재사용한다."""
    global _engine
    if _engine is None:
        host, port, user, password, database = _settings()
        url = (
            f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
            "?charset=utf8mb4"
        )
        _engine = create_engine(
            url,
            pool_size=5,
            max_overflow=5,
            pool_recycle=1800,   # 원격이라 유휴 연결이 죽는다
            pool_pre_ping=True,  # 죽은 연결을 조용히 되살린다
            future=True,
            # 트랜잭션을 쌓지 않는다. 읽기만 하므로 열어 둘 이유가 없고,
            # 열어 두면 MariaDB 쪽에 유휴 트랜잭션이 남는다.
            connect_args={"autocommit": True},
        )
        log.info("mysql engine: %s@%s:%s/%s", user, host, port, database)
    return _engine


class WriteAttempted(RuntimeError):
    """읽기 전용 헬퍼로 쓰기를 시도했다."""


_ALLOWED = ("select", "show", "describe", "explain", "with")


def read_sql(sql: str, params: dict[str, Any] | None = None) -> Sequence[Row[Any]]:
    """읽기 전용 질의. `SELECT`/`SHOW`/`DESCRIBE`/`EXPLAIN`/`WITH` 만 통과한다.

    이 검사는 보안 장치가 아니다 — 계정 권한이 그 일을 한다. 이건 **실수
    장치**다: 나중에 누가 이 헬퍼로 UPDATE 를 보내려 하면 런타임에 걸리고,
    그 시점에 "이 모듈은 읽기 전용" 이라는 결정을 다시 만나게 된다.
    """
    head = sql.lstrip().split(None, 1)[0].lower() if sql.strip() else ""
    if head not in _ALLOWED:
        raise WriteAttempted(
            f"read_sql 은 {'/'.join(_ALLOWED)} 만 받는다 (받은 것: {head!r}). "
            "이 DB 는 읽기 전용으로 붙어 있다."
        )
    with engine().connect() as cx:
        return cx.execute(text(sql), params or {}).fetchall()


def watermark() -> tuple[str, int]:
    """(마지막 날짜, 행 수) — **디스크 캐시의 키**로 쓸 값.

    CLAUDE.md 가 이 이동에서 잊지 말라고 못 박은 것이 정확히 이것이다:

        `app/cache.py` keys the disk cache on a HASH OF THE XLSX BYTES. With
        the source in MySQL that key has nothing to hash, and a cache keyed to
        the wrong data is worse than no cache.

    바이트가 없으므로 **테이블 워터마크**가 그 자리를 대신한다. 행이 늘거나
    마지막 날짜가 밀리면 키가 바뀌고 캐시가 무효가 된다.

    이 테이블에는 `updated_at` 이 없어서(스키마 확인 2026-08-07: 컬럼이
    irs_date + 15개 값뿐, PK 도 인덱스도 없다) 과거 행이 **조용히 수정되는**
    경우는 이 워터마크가 못 잡는다. 잡으려면 값 전체의 해시가 필요하고 그건
    2,618행 × 16열을 매번 읽는 일이다 — 그 비용을 치를지는 별도 판단이라
    여기서는 사실만 적어 둔다. [미해결]
    """
    row = read_sql(
        f"SELECT MAX(irs_date) AS d, COUNT(*) AS n FROM {IRS_CLOSE_TABLE}"
    )[0]
    return (str(row.d), int(row.n))


def irs_close_rows() -> list[dict[str, Any]]:
    """`mkt_irs_close` 전량, **날짜 오름차순**.

    오름차순인 이유: `Dataset` 이 그 순서를 요구하고(`dates` ascending,
    `asof = dates[-1]`), 로더가 순서를 검사한다. 정렬을 여기서 해 두면 그
    검사가 DB 쪽 실수도 같이 잡는다.

    2,618행 × 16열이라 전량을 한 번에 읽어도 몇 백 KB다. 페이지네이션을 두면
    커브 부트스트랩이 여러 왕복으로 갈라져서 오히려 느려진다.
    """
    rows = read_sql(f"SELECT * FROM {IRS_CLOSE_TABLE} ORDER BY irs_date ASC")
    return [dict(r._mapping) for r in rows]


def imx_irs_day(d: dt.date) -> dict[str, float]:
    """보충 출처의 종합ALL IRS 커브 **하루** — `{item 라벨: 값}`.

    행이 없으면 빈 dict 다. 예외가 아닌 이유: 「그 날이 아직 없다」는 오류가
    아니라 상태이고, 부르는 쪽(`dataset.merge_expected_close`)은 그 상태에서
    엑셀로 넘어가거나 지연 칩에 맡기는 선택을 해야 한다.

    하루만 읽는다. 전량(44,187행)을 읽을 이유가 없고, 읽으면 과거사를 이 출처로
    갈아타는 유혹이 생긴다 — `IMX_TIMESERIES_TABLE` 주석의 금지가 그것이다.
    """
    rows = read_sql(
        f"SELECT item, value FROM {IMX_TIMESERIES_TABLE} "
        "WHERE category = :c AND trade_date = :d",
        {"c": IMX_IRS_CATEGORY, "d": d.isoformat()},
    )
    return {
        str(r.item): float(r.value)
        for r in rows
        if r.value is not None
    }
