"""CORS 목록과 프리뷰 정규식이 **의도한 것만** 무는지.

배포되면 이 백엔드는 Funnel 로 공개되고 인증이 없다. 그러면 CORS 가 "아무
웹페이지가 방문자의 브라우저를 시켜 이걸 읽게 할 수 있는가"의 유일한 문턱이
된다. 문턱을 정규식으로 만들었으니, 정규식이 넓어지는 날을 여기서 잡는다.

프리뷰 주소는 커밋마다 바뀌므로(`rateslab-<hash>-<scope>.vercel.app`) 목록에
적을 수가 없고, 그래서 이 하나만 패턴이다. 패턴은 눈으로 보면 항상 맞아 보인다
— 아래 거절 목록이 그 착시를 막는다.
"""

from __future__ import annotations

import pytest

from app import cors


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """환경변수가 남아 있으면 이 파일의 판정이 기계마다 달라진다."""
    monkeypatch.delenv("SAURON_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("SAURON_ALLOWED_ORIGIN_REGEX", raising=False)


ACCEPT = [
    "https://rateslab.vercel.app",             # 프로덕션
    "https://rateslab-git-main-me.vercel.app",  # 브랜치 프리뷰
    "https://rateslab-abc123.vercel.app",       # 커밋 프리뷰
    "http://localhost:3200",                    # 로컬 개발(v2)
    "http://127.0.0.1:3200",
]

REJECT = [
    "https://rateslab.vercel.app.evil.com",  # 뒤에 도메인을 붙였다
    "https://evil-rateslab.vercel.app",      # 앞에 라벨을 붙였다
    "https://xrateslab.vercel.app",          # 접두사를 붙였다
    "https://rateslab.vercel.app/",          # 출처에 경로는 없다
    "http://rateslab.vercel.app",            # 평문
    "https://rateslab.vercel.dev",           # 다른 TLD
    "https://vercel.app",                    # 프로젝트 이름이 없다
    "https://rateslab-abc.vercel.app.co",    # 뒤에 TLD 를 덧댔다
    "null",                                  # sandbox iframe / file:// 의 출처
    "*",
]


@pytest.mark.parametrize("origin", ACCEPT)
def test_accepts(origin: str) -> None:
    assert cors.origin_allowed(origin), origin


@pytest.mark.parametrize("origin", REJECT)
def test_rejects(origin: str) -> None:
    assert not cors.origin_allowed(origin), origin


def test_no_wildcard_in_defaults() -> None:
    """`*` 한 줄이면 이 파일이 통째로 필요 없다. 그 줄이 들어오는 날 여기서 깨진다."""
    assert "*" not in cors.allowed_origins()


def test_env_adds_rather_than_replaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """배포 도메인을 넣었다고 로컬 개발이 막히면, 다음 사람은 목록을 고치는
    대신 `*` 로 도망간다. 그래서 환경변수는 **더한다**."""
    monkeypatch.setenv("SAURON_ALLOWED_ORIGINS", "https://rates.example.com , https://b.example.com/")
    origins = cors.allowed_origins()
    assert "http://localhost:3200" in origins
    assert "https://rates.example.com" in origins
    # 끝 슬래시는 떨어져 있어야 한다 — 브라우저는 Origin 에 그것을 안 붙여 보낸다.
    assert "https://b.example.com" in origins
    assert "https://b.example.com/" not in origins


def test_env_regex_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """프로젝트 이름이 바뀌면 정규식은 통째로 갈아 끼운다(더하지 않는다 —
    두 패턴을 OR 로 잇는 문법은 사람이 틀리기 쉽다)."""
    monkeypatch.setenv("SAURON_ALLOWED_ORIGIN_REGEX", r"\Ahttps://only-this\.example\.com\Z")
    assert cors.origin_allowed("https://only-this.example.com")
    assert not cors.origin_allowed("https://rateslab.vercel.app")


# ── 공개 포트에 **죽은 라우트를 남기지 않는다** [전수조사 2026-10-16] ──────────
# 이 파일이 지는 명제와 같은 자리다: 배포되면 이 백엔드는 Funnel 로 공개되고
# 인증이 없다. `irs_pricer.api.routers.positions` 는 v1 업로드 화면의
# `data/Portfolio Data.xlsx` 파서인데 v2 엔 그 워크북도 그 화면도 없고, 프런트·
# 시험 어디서도 안 부르면서 404 본문에 **서버 절대경로**를 실어 보냈다.
# 모듈은 v1 대사용으로 남기고 **꽂지 않는 것**이 결정이라, 다시 꽂히는 날을
# 여기서 잡는다.
def test_dead_v1_positions_routes_are_not_mounted() -> None:
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/positions" not in paths
    assert "/api/positions/summary" not in paths
