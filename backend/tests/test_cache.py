"""On-disk own-history cache (Session final Pass D): a changed source file must
invalidate the cache."""

import logging
from pathlib import Path

import pytest

from app.cache import cached, data_hash


def test_hash_matches_loads_mismatch_recomputes(tmp_path):
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"v": calls["n"]}

    # miss → compute
    a = cached("dist", "hashA", compute, cache_dir=tmp_path)
    assert a == {"v": 1} and calls["n"] == 1
    # same hash → load from disk, no recompute
    b = cached("dist", "hashA", compute, cache_dir=tmp_path)
    assert b == {"v": 1} and calls["n"] == 1
    # changed source (new hash) → recompute + rewrite
    c = cached("dist", "hashB", compute, cache_dir=tmp_path)
    assert c == {"v": 2} and calls["n"] == 2


def test_data_hash_changes_with_content(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"one")
    h1 = data_hash(f)
    f.write_bytes(b"two")
    h2 = data_hash(f)
    assert h1 != h2
    assert data_hash(f) == h2  # stable for unchanged content


def test_data_hash_separates_days_for_the_same_bytes(tmp_path):
    """전일종가 rule (v7): the same file re-read after midnight yields a
    different dataset (the intraday row it dropped is now a past close), so
    cache keys must carry the effective asof, not the bytes alone."""
    import datetime as dt

    f = tmp_path / "data.bin"
    f.write_bytes(b"one")
    a = data_hash(f, dt.date(2026, 8, 4))
    b = data_hash(f, dt.date(2026, 8, 5))
    assert a != b
    assert a == data_hash(f, dt.date(2026, 8, 4))
    assert data_hash(f) != a  # the bytes-only form is a different key space


def test_real_data_file_hash_is_stable():
    data = Path(__file__).resolve().parents[2] / "data" / "irsdata.xlsx"
    assert data_hash(data) == data_hash(data)


# ── a cache file the process died halfway through writing ──────────────────
# Pass A found this already correct (failure-modes.md §3) and said a
# regression test was worth having. "Correct" here means one thing: an
# unreadable cache is a slow start, never a failed one. The danger being
# guarded is not the corruption — it is someone tightening the except clause
# later and turning a recompute back into a crash on startup.


@pytest.mark.parametrize(
    "corruption, why",
    [
        ('{"hash": "hashA", "pay', "truncated mid-write"),
        ("", "zero bytes — file created, nothing flushed"),
        # 열쇠 꼴이 2026-09-30 에 «자료|code:지문» 으로 바뀌었다. 이 칸은 「해시는
        # 맞는데 payload 가 없다」로 `KeyError` 경로를 밟는 것이 의도이므로,
        # 하드코딩된 옛 해시 대신 **그때의 전체 열쇠**를 넣는다(안 그러면 STALE
        # 가지로 빠져 이 칸이 재던 것을 안 잰다).
        ('{"hash": "__FULL_KEY__"}', "valid JSON, no payload key"),
        ("[1, 2, 3]", "valid JSON, not an object"),
        ("null", "valid JSON, nothing at all"),
        ("\x00\x00\x00", "binary garbage"),
    ],
)
def test_half_written_cache_recomputes_and_says_so(tmp_path, caplog, corruption, why):
    from app.cache import _full_key

    (tmp_path / "dist.json").write_text(
        corruption.replace("__FULL_KEY__", _full_key("hashA")), encoding="utf-8")

    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"v": "fresh"}

    with caplog.at_level(logging.WARNING, logger="sauron.cache"):
        got = cached("dist", "hashA", compute, cache_dir=tmp_path)

    assert got == {"v": "fresh"}, why
    assert calls["n"] == 1
    assert any("unreadable" in r.message for r in caplog.records)
    # and the bad file is replaced, so the next start is fast again
    assert cached("dist", "hashA", compute, cache_dir=tmp_path) == {"v": "fresh"}
    assert calls["n"] == 1


def test_the_write_is_atomic_so_no_half_file_is_left_behind(tmp_path):
    """The recovery above costs a full recompute. Writing through a temp file
    and renaming means a killed process leaves the OLD file or the NEW one,
    never a torn one."""
    cached("dist", "hashA", lambda: {"v": 1}, cache_dir=tmp_path)
    assert (tmp_path / "dist.json").exists()
    assert not list(tmp_path.glob("*.tmp"))


# ── ★코드 정체성 [2026-09-30] ────────────────────────────────────────────────
# 열쇠가 **자료**만 보고 있었다. 그래서 산출물의 «의미» 를 바꾸는 코드 수정은
# 캐시를 무효화하지 못하고, 재기동해도 옛 페이로드가 그대로 나온다. 실측으로
# 밟았다: 슬리브 주문표의 밴드 부등호를 바꿨는데 `sleeve-sheet.json` 이 그대로라
# 화면이 `band=0` 짜리 옛 표를 계속 냈다(손으로 지워야 했다).
#
# `SCHEMA_VERSION` 이 그 자리에 있었지만 그건 **shape** 용이고(모듈 머리가 그렇게
# 적어 뒀다) 사람이 올려야 한다 — 값의 의미가 바뀐 이번 경우엔 올릴 생각이 안 든다.

def test_코드가_바뀌면_열쇠가_바뀐다(tmp_path, monkeypatch):
    """같은 자료 열쇠라도 **코드가 다르면** 다시 굽는다."""
    from app import cache as C

    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"v": calls["n"]}

    monkeypatch.setattr(C, "CODE_KEY", "code-A")
    assert cached("x", "dataH", compute, cache_dir=tmp_path) == {"v": 1}
    assert cached("x", "dataH", compute, cache_dir=tmp_path) == {"v": 1}   # 그대로
    monkeypatch.setattr(C, "CODE_KEY", "code-B")
    assert cached("x", "dataH", compute, cache_dir=tmp_path) == {"v": 2}   # 다시 굽는다
    assert calls["n"] == 2


def test_peek_도_같은_코드_열쇠를_본다(tmp_path, monkeypatch):
    """`peek()` 은 `cached()` 의 읽기 가지다 — 둘이 다른 열쇠를 보면 부분 결과
    라우트가 옛 페이로드를 내주고 `cached()` 만 다시 굽는다."""
    from app import cache as C

    monkeypatch.setattr(C, "CODE_KEY", "code-A")
    cached("y", "dataH", lambda: {"v": 1}, cache_dir=tmp_path)
    assert C.peek("y", "dataH", cache_dir=tmp_path) == {"v": 1}
    monkeypatch.setattr(C, "CODE_KEY", "code-B")
    assert C.peek("y", "dataH", cache_dir=tmp_path) is None


def test_코드_지문은_내용으로_잰다():
    """mtime 이 아니라 **내용**이다 — 체크아웃이나 `touch` 로 바뀌면 배포마다
    전부 다시 굽는다. 두 번 재서 같아야 한다."""
    from app.cache import _code_fingerprint

    assert _code_fingerprint() == _code_fingerprint()
    assert len(_code_fingerprint()) >= 8


# ── ★이름바꾸기 실패 [2026-09-30] ────────────────────────────────────────────
def test_이름바꾸기가_막히면_500이_아니라_값을_낸다(tmp_path, caplog, monkeypatch):
    """윈도우에서 `os.replace` 는 **대상이 다른 프로세스에 열려 있으면** 실패한다
    (`WinError 32`). 이 리포는 테스트 프로세스와 산 :8200 이 같은 `.cache` 를
    쓰므로 실제로 났고, `/api/mr/board`·`/api/mr/history` 가 **500** 을 냈다
    (실측 로그 여섯 건). 캐시에 못 쓴 것은 사고가 아니다 — 값은 이미 맞다.

    ⚠위 주석이 「os.replace is atomic on both POSIX and Windows」라고만 적혀
    있었다. 원자성은 맞지만 POSIX 는 열린 핸들이 있어도 성공하고 윈도우는 아니다.
    """
    from app import cache as C

    def boom(src, dst):
        raise PermissionError(32, "다른 프로세스가 파일을 사용 중입니다")

    monkeypatch.setattr(C.os, "replace", boom)
    with caplog.at_level(logging.WARNING, logger="sauron.cache"):
        got = cached("z", "dataH", lambda: {"v": 7}, cache_dir=tmp_path)
    assert got == {"v": 7}, "캐시에 못 썼다고 값을 잃으면 안 된다"
    assert any("캐시에 못 썼" in r.message or "could not be cached" in r.message
               for r in caplog.records), "조용히 넘기지 않는다"
    assert not list(tmp_path.glob("*.tmp")), "임시 파일을 남기지 않는다"


def test_이름바꾸기가_한_번_막혀도_다시_해_본다(tmp_path, monkeypatch):
    """읽는 쪽이 핸들을 쥐는 시간은 밀리초다 — 한 번 실패는 재시도로 넘어간다."""
    from app import cache as C

    real = C.os.replace
    tries = {"n": 0}

    def flaky(src, dst):
        tries["n"] += 1
        if tries["n"] == 1:
            raise PermissionError(32, "사용 중")
        return real(src, dst)

    monkeypatch.setattr(C.os, "replace", flaky)
    assert cached("w", "dataH", lambda: {"v": 3}, cache_dir=tmp_path) == {"v": 3}
    assert tries["n"] == 2, "재시도를 안 했다"
    # 정말 디스크에 섰나 — 다음 호출이 계산을 안 해야 한다.
    assert cached("w", "dataH", lambda: {"v": 99}, cache_dir=tmp_path) == {"v": 3}


def test_사유를_자료와_코드로_갈라_적는다(tmp_path, caplog, monkeypatch):
    """`STALE — source data changed` 는 **코드가 바뀐 경우엔 거짓**이다.

    열쇠에 코드를 넣은 뒤(2026-09-30) 첫 재기동에서 이 줄이 전부 「자료가 바뀌었다」로
    찍혔는데 자료는 그대로였다. 로그가 원인을 잘못 말하면 다음 사람이 자료를 뒤진다 —
    타임스탬프를 세운 것과 같은 이유로 고친다.
    """
    from app import cache as C

    monkeypatch.setattr(C, "CODE_KEY", "code-A")
    cached("s", "dataH", lambda: {"v": 1}, cache_dir=tmp_path)

    # 코드만 바뀐 경우
    monkeypatch.setattr(C, "CODE_KEY", "code-B")
    with caplog.at_level(logging.WARNING, logger="sauron.cache"):
        cached("s", "dataH", lambda: {"v": 2}, cache_dir=tmp_path)
    msgs = " ".join(r.message for r in caplog.records)
    assert "코드" in msgs, msgs
    assert "자료" not in msgs, f"자료는 안 바뀌었다 — {msgs}"

    # 자료만 바뀐 경우
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="sauron.cache"):
        cached("s", "dataH2", lambda: {"v": 3}, cache_dir=tmp_path)
    msgs = " ".join(r.message for r in caplog.records)
    assert "자료" in msgs and "코드" not in msgs, msgs
