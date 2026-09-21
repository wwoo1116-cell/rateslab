"""아침 데이터 갱신의 눈 — 전일 종가가 어디까지 와 있고, 백엔드가 뭘 보는가.

    python backend/scripts/check_close.py                    # 사람이 읽는 한 줄씩
    python backend/scripts/check_close.py --json             # 오케스트레이터용
    python backend/scripts/check_close.py --json --served 2026-09-18
                                                  # 판정까지 (refresh.ps1)

판정만 하고 아무것도 바꾸지 않는다. `backend/refresh.ps1` 이 이 출력을 읽어
재기동할지 기다릴지를 정한다 [OWNER, 2026-08-11 · 배선 2026-09-22].

내보내는 상태:

  businessDay   오늘(서울)이 한국 영업일인가 — 아니면 아침 루프 전체가 no-op
  expected      기대하는 전일 종가의 날짜 (직전 영업일)
  sql.status    full | missing-1d | partial | absent | error
                partial 은 "기대일 행은 있는데 1D 외의 노드가 빈" 상태 —
                적재가 진행 중일 수 있으니 기다리는 쪽으로 읽어야 한다
  xlsx.status   fresh | stale | missing | error
                fresh = 기대일 행이 있고 값이 수치다 (전일종가 컷 뒤 기준)
  wouldServe    **지금 백엔드를 재기동하면 서빙될 asof** — 서버가 부팅 때 지나는
                그 로더(`load_dataset_merged`)를 그대로 지나서 얻는다

## 왜 `wouldServe` 인가 — raw MAX(irs_date) 로는 안 된다 [2026-09-22]

`refresh.ps1` 은 원래 `irs_close_rows()[-1]` 을 썼다. 그건 테이블의 최대
날짜이고, 서버가 서빙하는 asof 는 **전일종가 컷과 엑셀 병합을 지난 뒤**의
날짜다. 둘은 보통 같지만 같다는 보장이 없다 — 테이블에 오늘 자 행이 한 번이라도
들어오면 MAX 는 오늘을 말하고 서버는 영원히 전영업일을 서빙하므로, 「SQL 이 더
새롭다」가 항상 참이 되어 **재기동이 그치지 않는다**. 30분 간격으로 다시 보게
바꾼 뒤로는 그 오독의 대가가 한 번의 헛재기동이 아니라 종일 재기동이다.
그래서 비교하는 두 수를 같은 계산에서 뽑는다.

## 판정 (`--served` 를 주면 `verdict` 가 붙는다)

  error     wouldServe 를 못 구했다(DB·엑셀 둘 다) — 재기동하면 안 된다
  start     백엔드가 안 떠 있다
  restart   wouldServe > served — 서버가 낡은 스냅샷을 들고 있다
  waiting   서버는 SQL 만큼은 최신인데 **SQL 이 아직 기대 전영업일을 안 들고
            있다** — 적재를 기다리는 중. 다음 회차에 다시 본다
  current   기대 전영업일까지 서빙 중 — 오늘은 더 할 일이 없다

`waiting` 이 이 파일에 생긴 이유가 진단의 요점이다: 옛 refresh.ps1 은 이 상태를
「이미 최신이에요」라고 적었고, 그래서 **2026-09-10 부터 09-22 까지 열 번의 아침이
전부 그 한 줄이었다**(refresh.log). 최신인 것은 서버가 아니라 서버와 SQL 의
«관계» 였다.

종료 코드는 늘 0 이다 — 이 스크립트의 실패는 JSON 의 error 로 말한다.
파싱하는 쪽이 예외 스택을 상태로 오독하는 것보다 낫다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.dataset import (  # noqa: E402
    DEFAULT_XLSX,
    SQL_COLUMN_TENOR,
    load_dataset,
    market_today,
    prev_kr_business_day,
)


def sql_state(expected: dt.date) -> dict:
    try:
        from app.mysqldb import IRS_CLOSE_TABLE, read_sql

        rows = read_sql(
            f"SELECT * FROM {IRS_CLOSE_TABLE} WHERE irs_date = :d",
            {"d": expected.isoformat()},
        )
    except Exception as e:  # noqa: BLE001 — DB 다운도 상태다
        return {"status": "error", "detail": str(e)[:200]}

    if not rows:
        return {"status": "absent"}
    r = dict(rows[0]._mapping)
    missing = [t for c, t in SQL_COLUMN_TENOR.items() if r.get(c) is None]
    if not missing:
        return {"status": "full"}
    if missing == ["1D"]:
        return {"status": "missing-1d"}
    return {"status": "partial", "missing": sorted(missing)}


def xlsx_state(expected: dt.date, today: dt.date) -> dict:
    if not DEFAULT_XLSX.exists():
        return {"status": "missing"}
    try:
        ds = load_dataset(DEFAULT_XLSX, today)  # 전일종가 컷 포함 — 서버와 같은 눈
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "detail": str(e)[:200]}
    newest = ds.asof
    if newest < expected:
        return {"status": "stale", "newest": newest.isoformat()}
    # 기대일 행이 있어도 1D 가 비었으면 보충 소스 역할을 못 한다 — 적어 둔다.
    blank = [t for t in ds.series if ds.latest(t) is None]
    out: dict = {"status": "fresh", "newest": newest.isoformat()}
    if blank:
        out["blankAtNewest"] = sorted(blank)
    return out


def would_serve(today: dt.date) -> dict:
    """지금 재기동하면 백엔드가 서빙할 asof. 서버와 **같은 로더**를 지난다.

    실패를 예외로 올리지 않는다 — DB 가 죽은 것도 상태이고, 부르는 쪽(refresh)은
    그 상태에서 «재기동 안 함» 을 골라야 한다. 예외로 올리면 그 선택이 스택
    트레이스가 되어 사라진다.
    """
    try:
        from app.dataset import load_dataset_merged

        ds = load_dataset_merged(today=today)
    except Exception as e:  # noqa: BLE001 — DB 다운·엑셀 부재 전부 상태다
        return {"asof": None, "error": str(e)[:200]}
    return {"asof": ds.asof.isoformat(), "source": ds.source}


#: 사람이 읽는 한 줄. 로그에 그대로 들어간다 — `refresh.ps1` 은 이 문장을
#: 만들지 않는다(한 사실에 두 어휘가 생기는 것이 이 리포의 고질병이다).
_WHY = {
    "error": "지금 서빙될 날짜를 못 구했어요(DB·엑셀 둘 다) — 재기동 안 함.",
    "start": "백엔드가 안 떠 있어요 — 띄웁니다.",
    "restart": "서버가 낡은 스냅샷을 들고 있어요 — 재기동합니다.",
    "waiting": "SQL 이 아직 기대 전영업일을 안 들고 있어요 — 다음 회차에 다시 봅니다.",
    "current": "기대 전영업일까지 서빙 중이에요 — 아무것도 안 합니다.",
}


def decide(served: str, serve_asof: str | None, expected: str | None,
           business_day: bool) -> dict:
    """다섯 상태 중 하나. **순수 함수** — DB 도 시계도 안 본다.

    문자열 비교인 것은 의도다: ISO 날짜는 사전순이 시간순이고, 날짜로 파싱하면
    「빈 문자열 = 안 떠 있음」 을 표현할 자리가 없어진다.

    `expected` 가 None 인 것은 영업일이 아닌 날이다. 그날은 적재가 없으므로
    기다릴 것도 없다 — 서버가 SQL 만큼만 최신이면 `current` 다.
    """
    if serve_asof is None:
        return {"verdict": "error", "why": _WHY["error"]}
    if not served:
        return {"verdict": "start", "why": _WHY["start"]}
    if serve_asof > served:
        return {"verdict": "restart", "why": _WHY["restart"]}
    # 여기 아래로는 재기동해도 날짜가 안 앞선다. 그러면 남은 물음은 하나다 —
    # **화면이 데스크가 기대하는 종가를 들고 있는가.** `serve_asof` 가 아니라
    # `served` 로 묻는 것이 요점이다(시험 하나가 이 자리를 박았다): 엑셀 병합분을
    # 들고 뜬 뒤 그 엑셀이 치워지면 서버가 로더보다 앞서고, 그건 기다림이 아니다.
    if business_day and expected and served < expected:
        return {"verdict": "waiting", "why": _WHY["waiting"]}
    return {"verdict": "current", "why": _WHY["current"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--served",
        default=None,
        metavar="ISO",
        help="지금 :8200 이 서빙 중인 asof. 주면 verdict 가 붙는다. "
             "안 떠 있으면 빈 문자열을 넘긴다.",
    )
    a = ap.parse_args()

    from app.engine_port import _is_kr_business_day

    today = market_today()
    business = _is_kr_business_day(today)
    report: dict = {
        "today": today.isoformat(),
        "businessDay": business,
    }
    expected: dt.date | None = None
    if business:
        expected = prev_kr_business_day(today)
        report["expected"] = expected.isoformat()
        report["sql"] = sql_state(expected)
        report["xlsx"] = xlsx_state(expected, today)
    report["wouldServe"] = would_serve(today)
    if a.served is not None:
        report.update(decide(
            a.served.strip(),
            report["wouldServe"]["asof"],
            expected.isoformat() if expected else None,
            business,
        ))

    if a.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        for k, v in report.items():
            print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
