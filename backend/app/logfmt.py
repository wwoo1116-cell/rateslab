"""로그 한 줄에 **시각**을 세운다.

★왜 이 파일이 생겼나 [2026-09-30]: `backend.log` 에 타임스탬프가 **한 줄도 없었다**
(2.7MB · 36,753줄). 그래서 `/api/mr/board` 의 500 여섯 건이 언제 났는지 로그만으로
알 수 없었고, 이번 세션은 `.cache` 파일의 mtime 과 프로세스 시작 시각으로 **에둘러**
구간을 맞췄다. `:8200` 은 Tailscale Funnel 로 공개돼 있는 자리다 — 그 로그가 「언제」를
못 말하면 사고를 못 읽는다.

**왜 dictConfig 하나로 안 되나**: `main.py` 의 dictConfig 는 루트(=우리 로거들)를
덮지만, `backend.log` 의 대부분은 **uvicorn 의 접근 로그**이고 그 로거들은
`propagate=False` 로 자기 핸들러·포매터를 쓴다. `serve.ps1` 이 uvicorn CLI 로 띄우므로
(`python -m uvicorn app.main:app`) uvicorn 의 `configure_logging()` 은 `app.main` 을
임포트하기 **전에** 돈다 — 그래서 임포트 직후에 그 핸들러들을 덮을 수 있다.

**꼴을 안 바꾼다**: uvicorn 의 포매터는 `%(levelprefix)s` 같은 자기 필드를 쓰고 색도
넣는다. 그래서 포매터를 **갈아치우지 않고** 기존 꼴 앞에 `%(asctime)s` 만 붙인다
(클래스가 그대로라 색·레벨 접두가 살아 있다).
"""

from __future__ import annotations

import logging

#: 로컬 시각, 초까지. 날짜를 같이 적는 이유는 이 파일이 **재기동을 넘어 쌓이기**
#: 때문이다(`serve.ps1` 이 5MB 넘을 때만 지운다) — 시각만 있으면 어느 날인지 모른다.
DATEFMT = "%Y-%m-%d %H:%M:%S"

#: 시각을 세울 로거들. uvicorn 셋은 이름이 고정이다.
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def stamp_handlers(names: object = UVICORN_LOGGERS) -> None:
    """이 로거들의 **모든 핸들러**에 시각을 세운다 — 여러 번 불려도 한 번만 붙는다.

    포매터가 없는 핸들러에는 세워 준다(기본 포매터는 시각이 없다). 없는 로거
    이름은 조용히 넘긴다 — 전수나 `TestClient` 에는 uvicorn 이 없다.
    """
    for name in names:
        lg = logging.getLogger(name)
        for h in lg.handlers:
            f = h.formatter
            if f is None:
                h.setFormatter(logging.Formatter(f"%(asctime)s %(message)s", DATEFMT))
                continue
            fmt = getattr(getattr(f, "_style", None), "_fmt", None)
            if not fmt or "%(asctime)" in fmt:
                continue
            stamped = f"%(asctime)s {fmt}"
            # 클래스를 바꾸지 않고 꼴만 갈아 끼운다(uvicorn 의 색·레벨 접두 보존).
            f._style._fmt = stamped
            f._fmt = stamped
            f.datefmt = DATEFMT
