"""로그에 **시각**이 있는가.

★왜 [2026-09-30]: `backend.log` 에 타임스탬프가 **한 줄도 없었다**(2.7MB · 36,753줄).
그래서 500 이 언제 났는지, 어느 재기동 뒤인지 로그만으로 알 수 없었다 — 이번 세션은
`.cache` 의 mtime 과 프로세스 시작 시각으로 **에둘러** 맞췄다. 공개돼 있는 서비스
(`:8200` · Tailscale Funnel)의 로그가 그러면 안 된다.

앱 로거는 `main.py` 의 dictConfig 가 덮지만 **uvicorn 의 접근 로그는 자기 포매터**를
쓴다(파일의 대부분이 그것이다). 그래서 둘 다 덮어야 한다.
"""

from __future__ import annotations

import logging

from app import logfmt


def _logger_with(fmt: str | None) -> tuple[logging.Logger, logging.Handler]:
    lg = logging.getLogger("테스트.가짜")
    for h in list(lg.handlers):
        lg.removeHandler(h)
    h = logging.StreamHandler()
    if fmt is not None:
        h.setFormatter(logging.Formatter(fmt))
    lg.addHandler(h)
    return lg, h


def test_포매터에_시각을_붙인다():
    lg, h = _logger_with("%(levelname)s %(message)s")
    logfmt.stamp_handlers(["테스트.가짜"])
    assert "%(asctime)s" in h.formatter._style._fmt
    assert "%(message)s" in h.formatter._style._fmt, "원래 꼴을 잃지 않는다"
    assert h.formatter.datefmt == logfmt.DATEFMT


def test_두_번_불러도_한_번만_붙는다():
    """uvicorn 이 로거를 다시 세우는 경우가 있어 이 함수는 여러 번 불릴 수 있다."""
    lg, h = _logger_with("%(levelname)s %(message)s")
    logfmt.stamp_handlers(["테스트.가짜"])
    once = h.formatter._style._fmt
    logfmt.stamp_handlers(["테스트.가짜"])
    assert h.formatter._style._fmt == once
    assert once.count("%(asctime)s") == 1


def test_포매터가_없는_핸들러에도_세운다():
    lg, h = _logger_with(None)
    logfmt.stamp_handlers(["테스트.가짜"])
    assert h.formatter is not None
    assert "%(asctime)s" in h.formatter._style._fmt


def test_없는_로거_이름은_조용히_넘긴다():
    """uvicorn 이 안 뜬 환경(전수·TestClient)에서도 죽지 않아야 한다."""
    logfmt.stamp_handlers(["없는.로거.이름"])        # 예외 없음


def test_실제로_찍힌_줄에_시각이_있다(caplog):
    """포맷 문자열이 아니라 **나온 글자**를 본다."""
    import io

    lg = logging.getLogger("테스트.실제")
    for h in list(lg.handlers):
        lg.removeHandler(h)
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    lg.addHandler(h)
    lg.propagate = False
    lg.setLevel(logging.INFO)

    logfmt.stamp_handlers(["테스트.실제"])
    lg.info("한 줄")
    out = buf.getvalue()
    assert "한 줄" in out
    # 2026-09-30 09:47:12 꼴 — 네자리 연도와 콜론 둘
    import re
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", out), out
