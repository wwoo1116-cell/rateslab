"""The static build pipeline (Pass B).

Four things are pinned here, each because getting it wrong fails quietly:

  determinism  — a rebuild on unchanged data must be byte-identical, or every
                 commit shows the whole tree as modified and diffs stop meaning
                 anything.
  ids          — an id that cannot round-trip to a filename must RAISE. On NTFS
                 a colon silently redirects the write into an alternate data
                 stream; Pass A lost 24 files that way with a clean exit code.
  non-finite   — Python emits bare NaN by default, which is not valid JSON and
                 which response.json() rejects in the browser: a payload that
                 parses everywhere except where it is used.
  gaps         — a missing observation is an ABSENT POINT, not a null and not a
                 NaN. That is the live behaviour and the static build keeps it.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "scripts"))

import build_static as B  # noqa: E402

from app.dataset import load_dataset_sql  # noqa: E402
from app.static_paths import (  # noqa: E402
    UnsafeId,
    UnsafePath,
    assert_writable_path,
    dv01_path,
    series_path,
    slug,
)


def _baked_manifest() -> dict:
    """The manifest of the CHECKED-IN static tree, or a skip.

    V2-LOCAL EDIT 5 of 5 — see ../../BACKEND.md. Two things were wrong here and
    both were silent:

    1. The path said `frontend/public`, which is v1's layout. v2's Next app IS
       the repo root, so the tree lives at `public/api/**` — the old path could
       never exist and these two tests had failed since the day the backend was
       copied (`FileNotFoundError`, not an assertion).
    2. Even at the right path there may be no tree at all. These tests do not
       test the BUILDER (that is the rest of this file, which builds into
       `tmp_path`); they test that a tree somebody baked and committed has not
       gone stale. With nothing baked there is nothing to be stale, and a
       failure there is noise that hides real ones. So: skip, and say what to
       run.
    """
    m = B.OUT_ROOT / "api" / "manifest.json"
    if not m.exists():
        pytest.skip(
            f"no baked static tree at {m.relative_to(REPO)} — this checks that a "
            "COMMITTED tree has not gone stale, so there is nothing to check. "
            "Run `python backend/scripts/build_static.py` to bake one."
        )
    return json.loads(m.read_text("utf-8"))

# 이 파일은 **빌드 결과**를 검사한다. 빌드가 읽는 것과 같은 출처를 읽어야
# 비교가 성립하고, 2026-08-07 부터 그것은 MySQL 이다 [OWNER — "그냥 모든 걸
# MySQL로"]. `DATA`(irsdata.xlsx)는 그래서 없어졌다.
#
# 얼린 파일을 픽스처로 쓰는 다른 테스트들과 다른 이유: 저쪽은 xlsx 를 **입력**
# 으로 받아 로더의 동작을 본다(네트워크에 매이지 않아야 하고 값이 매일 바뀌면
# 안 된다). 여기는 파이프라인이 만든 것을 그 파이프라인의 입력과 맞춰 보는
# 것이라, 입력이 옮겨가면 같이 옮겨가야 한다.


# ── ids → filenames ─────────────────────────────────────────────────────────

def test_ordinary_ids_pass_through_unchanged():
    for sid in ["1Y", "10Y", "1.5Y", "1Y-10Y", "2Y-5Y-10Y", "6Mx3M", "4Y6Mx2Y"]:
        assert slug(sid) == sid


def test_the_colon_becomes_a_directory():
    """The rule, stated as a test. `vol:` is already a namespace, so a
    directory is what the colon always meant."""
    assert slug("vol:1Y") == "vol/1Y"
    assert slug("vol:1.5Y") == "vol/1.5Y"
    assert series_path("vol:10Y", "full") == "api/series/vol/10Y.full.json"
    assert dv01_path("vol:10Y") == "api/dv01/vol/10Y.json"


def test_the_resolution_rides_in_the_filename():
    # a static host cannot select a file by ?res=
    assert series_path("10Y", "full") == "api/series/10Y.full.json"
    assert series_path("10Y", "preview") == "api/series/10Y.preview.json"
    assert series_path("10Y", "w") == "api/series/10Y.w.json"
    # a dot inside the id is fine: the suffix is appended, never parsed off
    assert series_path("1.5Y", "m") == "api/series/1.5Y.m.json"


@pytest.mark.parametrize("bad", [
    "a b",        # space
    "a?b",        # URL query
    "a%2Fb",      # pre-encoded
    "a\\b",       # windows separator
    "a|b", "a*b", "a<b", 'a"b',
    "..", "../etc/passwd",
    "/leading", "trailing/",
    "",
])
def test_an_id_that_cannot_round_trip_raises(bad):
    """Loudly, not silently. This is the whole point of the module."""
    with pytest.raises(UnsafeId):
        slug(bad)


def test_an_unknown_resolution_raises():
    with pytest.raises(UnsafeId):
        series_path("10Y", "daily")


# ── the path written to disk (Pass G) ───────────────────────────────────────
# `slug()` guards the ID; `assert_writable_path()` guards the PATH. They are
# different checks at different layers, and the bug happened at the second one:
# the write is where a colon becomes an alternate data stream.

def test_the_exact_path_that_shipped_the_bug_raises():
    """`series/vol:1Y.json` — the literal shape that cost 24 artifacts. On NTFS
    this does not create that file and does not error: it creates a zero-byte
    file named `vol` and hides the content in a stream, exit 0."""
    with pytest.raises(UnsafePath, match="alternate data stream"):
        assert_writable_path("api/series/vol:1Y.full.json")


def test_vol_ids_reach_disk_with_no_colon_anywhere():
    """The other half of the same guarantee, and the reason `slug()` maps
    rather than rejects: `vol:1Y` is a REAL id the volatility tab needs. It is
    safe because the colon becomes a directory before the path is built, so
    nothing colon-shaped ever reaches the writer."""
    for res in ("full", "preview", "w", "m"):
        p = series_path("vol:1Y", res)
        assert ":" not in p
        assert p.startswith("api/series/vol/1Y.")
    assert ":" not in dv01_path("vol:1.5Y")


@pytest.mark.parametrize("bad, why", [
    ("api/series/vol:1Y.json", "colon — NTFS alternate data stream"),
    ("api/series/a?b.json", "URL query character"),
    ("api/series/a*b.json", "glob"),
    ("api/series/a|b.json", "pipe"),
    ("api/series/a<b.json", "redirect"),
    ("api/series/a>b.json", "redirect"),
    ('api/series/a"b.json', "quote"),
    ("api/series/a\\b.json", "backslash separator"),
    # Windows strips trailing spaces and dots from a name on create, so the
    # file written is not the file requested. Only a genuinely TRAILING one is
    # a hazard: `name .json` is legal and is deliberately not rejected.
    ("api/series/trailing /x.json", "directory segment ending in a space"),
    ("api/series/x./y.json", "directory segment ending in a dot"),
    ("api/series/10Y.full.json ", "filename ending in a space"),
    ("api/series/10Y.full.json.", "filename ending in a dot"),
    ("api/series/CON.json", "reserved Windows device name"),
    ("api/series/com1.full.json", "reserved device name, lowercased"),
    ("api/series/../escape.json", "traversal"),
    ("/api/series/x.json", "absolute"),
    ("api//series/x.json", "empty segment"),
    ("", "empty"),
])
def test_paths_illegal_on_either_filesystem_are_refused(bad, why):
    with pytest.raises(UnsafePath):
        assert_writable_path(bad)


def test_it_refuses_rather_than_sanitising():
    """A silent rename is worse than the bug it prevents: the build would
    succeed and the manifest would point at a name that is not on disk, so the
    client 404s on exactly one instrument and nothing upstream notices."""
    with pytest.raises(UnsafePath):
        assert_writable_path("api/series/vol:1Y.full.json")
    # and it does not return a cleaned-up string on the way out
    assert assert_writable_path("api/series/1.5Y.full.json") == (
        "api/series/1.5Y.full.json"
    )


def test_a_space_that_is_not_trailing_is_allowed():
    """Deliberately not rejected: `a b.json` is legal on both filesystems, and
    over-rejecting would push a future caller toward silent sanitising."""
    assert assert_writable_path("api/series/a b.json") == "api/series/a b.json"


def test_ordinary_paths_pass_through_untouched():
    for good in [
        "api/manifest.json",
        "api/wall/summary.json",
        "api/series/10Y.full.json",
        "api/series/1.5Y.preview.json",
        "api/series/2Y-5Y-10Y.w.json",
        "api/series/vol/1.5Y.m.json",
        "api/dv01/4Y6Mx2Y.json",
    ]:
        assert assert_writable_path(good) == good


# ── serialisation ───────────────────────────────────────────────────────────

def test_non_finite_floats_are_refused():
    for v in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="non-finite"):
            B.dumps({"points": [{"t": "2026-01-01", "v": v}]})


def test_nulls_are_ordinary_and_survive():
    # deltas/basisValues/range1y carry None legitimately — null is correct JSON
    out = B.dumps({"a": None, "b": {"c": None}})
    assert json.loads(out) == {"a": None, "b": {"c": None}}


def test_keys_are_sorted_at_every_level():
    out = B.dumps({"z": 1, "a": {"z": 1, "a": 2}})
    assert out.index('"a"') < out.index('"z"')
    assert json.loads(out) == {"z": 1, "a": {"z": 1, "a": 2}}


def test_series_arrays_are_one_observation_per_line():
    """A storage decision: as line appends a daily update is a few KB of git
    delta; as one long line every file rewrites whole, ~31 MB per update."""
    body = B.dumps({
        "id": "10Y",
        "points": [{"t": "2026-01-01", "v": 1.0, "d": None},
                   {"t": "2026-01-02", "v": 1.1, "d": 10.0}],
    })
    assert '{"d":null,"t":"2026-01-01","v":1.0},\n{"d":10.0' in body
    assert json.loads(body)["points"][1]["v"] == 1.1


def test_only_the_append_arrays_explode():
    # summary rows are rewritten wholly every day; spreading them costs bytes
    # and buys no delta
    body = B.dumps({"outrights": [{"id": "1Y"}, {"id": "2Y"}]})
    assert "\n" not in body


# ── the pipeline end to end ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def two_builds(tmp_path_factory):
    """Run the whole pipeline twice into separate trees."""
    a = tmp_path_factory.mktemp("build_a")
    b = tmp_path_factory.mktemp("build_b")
    B.build(a, quiet=True)
    B.build(b, quiet=True)
    return a, b


def test_the_build_is_deterministic(two_builds):
    a, b = two_builds
    fa = sorted(p.relative_to(a).as_posix() for p in a.rglob("*") if p.is_file())
    fb = sorted(p.relative_to(b).as_posix() for p in b.rglob("*") if p.is_file())
    assert fa == fb, "the two builds produced different file sets"

    differing = []
    for rel in fa:
        x, y = (a / rel).read_bytes(), (b / rel).read_bytes()
        if x == y:
            continue
        if rel.endswith("manifest.json"):
            # the ONE payload carrying a build time, by design; compare the rest
            jx, jy = json.loads(x), json.loads(y)
            jx.pop("builtAt"), jy.pop("builtAt")
            if jx == jy:
                continue
        differing.append(rel)
    assert differing == [], f"non-deterministic output: {differing[:10]}"


def test_every_emitted_file_is_valid_json(two_builds):
    a, _ = two_builds
    for p in a.rglob("*.json"):
        json.loads(p.read_text(encoding="utf-8"))  # raises on NaN


def test_a_known_gap_is_an_absent_point_not_a_null(two_builds):
    """The history has blanks — the loader reports 9 for 1D and 10 for 3M. A
    blank must produce NO point, matching the live API. A null would render as
    a gap in the chart; a NaN would not parse at all."""
    a, _ = two_builds
    ds = load_dataset_sql()
    gaps = {
        tenor: [d for d, v in zip(ds.dates, ds.series[tenor]) if v is None]
        for tenor in ("1D", "3M")
    }
    assert any(gaps.values()), "expected the fixture data to contain blanks"

    for tenor, missing in gaps.items():
        if not missing:
            continue
        body = json.loads((a / series_path(tenor, "full")).read_text("utf-8"))
        got = {p["t"] for p in body["points"]}
        for d in missing:
            assert d.isoformat() not in got, (
                f"{tenor}: blank {d} was emitted as a point"
            )
        # and the surrounding series is intact, not truncated at the gap
        assert len(body["points"]) == len(ds.dates) - len(missing)


def test_the_manifest_reuses_the_existing_hash_scheme(two_builds):
    """Not a second scheme: two hashing schemes drift and only one gets
    checked. 그 스킴이 2026-08-07 에 파일 바이트에서 **테이블 워터마크**로
    바뀌었다 (`cache.sql_data_hash`) — 출처가 MySQL 이라 해시할 바이트가 없다.
    서버(app/main.py)와 빌드가 같은 함수를 쓴다는 것이 이 테스트의 주장이고,
    그 주장은 스킴이 바뀌어도 그대로다."""
    from app.cache import SCHEMA_VERSION, sql_data_hash
    from app.dataset import load_dataset_merged

    a, _ = two_builds
    m = json.loads((a / "api" / "manifest.json").read_text("utf-8"))
    # ★빌드와 서버가 지나는 **그 로더**로 묻는다 [2026-10-07]. 종전에는
    # `load_dataset_sql()` 로 물었고, 그러면 보충 출처가 하루를 메운 날 —
    # 2026-10-07 아침이 그 날이었다 — 빨개진다. 그 날 빨개지는 것은 스킴이
    # 둘이라는 뜻이 아니라 **질문이 틀렸다**는 뜻이었다: 병합 로더만이
    # `data_key` 를 채우고(`dataset.load_dataset_merged` 꼬리), 서버와 빌드는
    # 둘 다 그것을 쓴다. 옛 질문은 병합이 no-op 인 날에만 성립했다.
    ds = load_dataset_merged()
    # the key carries the dataset's effective asof too — the same table read
    # on different days is a different dataset under the 전일종가 cutoff
    assert m["dataHash"] == ds.data_key
    assert f":v{SCHEMA_VERSION}:" in m["dataHash"]
    assert m["schemaVersion"] == SCHEMA_VERSION
    assert m["asof"] == ds.asof.isoformat()

    # 스킴은 하나다 — 어느 날이든 키는 **테이블 워터마크**로 시작한다.
    pure = sql_data_hash(load_dataset_sql().asof)
    watermark = pure.split(":v")[0]
    assert m["dataHash"].startswith(watermark)
    if ds.source == "sql":
        assert m["dataHash"] == pure
    else:
        # 보충분이 섞인 날은 키가 **갈라져야** 한다. 내용이 다른데 키가 같은
        # 캐시가 이 리포의 고질병이다.
        assert m["dataHash"] != pure
        assert ds.source in m["dataHash"]


# ── the integrity check itself (Pass G) ─────────────────────────────────────
# A verifier that cannot fail is decoration. Each corruption class the check
# claims to catch is produced here and shown to raise.

def _tiny_tree(root):
    """Two declared artifacts plus a manifest, all valid."""
    (root / "api" / "series").mkdir(parents=True)
    for rel in ["api/series/10Y.full.json", "api/series/1Y.full.json"]:
        (root / rel).write_text('{"id":"x"}', encoding="utf-8")
    (root / "api" / "manifest.json").write_text('{"a":1}', encoding="utf-8")
    return ["api/series/10Y.full.json", "api/series/1Y.full.json"]


def test_verify_passes_on_a_sound_tree(tmp_path):
    declared = _tiny_tree(tmp_path)
    out = B.verify_tree(tmp_path, declared, "api/manifest.json")
    assert out == {"declared": 2, "onDisk": 3}  # 2 artifacts + the manifest


def test_verify_catches_a_missing_file(tmp_path):
    declared = _tiny_tree(tmp_path)
    (tmp_path / declared[0]).unlink()
    with pytest.raises(B.IntegrityError, match="MISSING"):
        B.verify_tree(tmp_path, declared, "api/manifest.json")


def test_verify_catches_a_zero_byte_file(tmp_path):
    """This is what the alternate-data-stream write actually leaves behind: a
    real file, correct name in the listing, no content. An existence check
    passes on it — which is why size is checked separately."""
    declared = _tiny_tree(tmp_path)
    (tmp_path / declared[0]).write_bytes(b"")
    with pytest.raises(B.IntegrityError, match="EMPTY"):
        B.verify_tree(tmp_path, declared, "api/manifest.json")


def test_verify_catches_a_truncated_write(tmp_path):
    declared = _tiny_tree(tmp_path)
    (tmp_path / declared[0]).write_text('{"id":"10Y","points":[{"t"', encoding="utf-8")
    with pytest.raises(B.IntegrityError, match="UNPARSED"):
        B.verify_tree(tmp_path, declared, "api/manifest.json")


def test_verify_catches_an_orphan(tmp_path):
    """The rename failure: an id changes, the new file is written, the old one
    survives, and the client happily resolves a series that no longer exists.
    An orphan is as much a defect as a missing file, so the check runs both
    ways."""
    declared = _tiny_tree(tmp_path)
    (tmp_path / "api" / "series" / "GHOST.full.json").write_text("{}", encoding="utf-8")
    with pytest.raises(B.IntegrityError, match="ORPHAN"):
        B.verify_tree(tmp_path, declared, "api/manifest.json")


def test_verify_reports_every_problem_not_just_the_first(tmp_path):
    declared = _tiny_tree(tmp_path)
    (tmp_path / declared[0]).unlink()
    (tmp_path / declared[1]).write_bytes(b"")
    (tmp_path / "api" / "series" / "GHOST.full.json").write_text("{}", encoding="utf-8")
    with pytest.raises(B.IntegrityError) as e:
        B.verify_tree(tmp_path, declared, "api/manifest.json")
    msg = str(e.value)
    assert "MISSING" in msg and "EMPTY" in msg and "ORPHAN" in msg
    assert "3 artifact integrity problem" in msg


def test_the_real_build_declares_exactly_what_it_wrote(two_builds):
    """End to end: the manifest's own list must account for every file in the
    tree, with the manifest itself as the only unlisted one."""
    a, _ = two_builds
    m = json.loads((a / "api" / "manifest.json").read_text("utf-8"))
    on_disk = {
        p.relative_to(a).as_posix() for p in (a / "api").rglob("*") if p.is_file()
    }
    assert set(m["artifacts"]) | {"api/manifest.json"} == on_disk
    assert m["artifactCount"] == len(m["artifacts"]) == len(on_disk) - 1
    assert "api/manifest.json" not in m["artifacts"]


# ── holiday coverage behind the ladder (Pass J) ─────────────────────────────

def test_the_ladder_only_uses_populated_calendar_years():
    """Diagnosed, not assumed. If the holiday table ever stops covering a year,
    `_is_kr_business_day` quietly degrades to a weekend-only test and the
    ladder fills with plausible wrong dates — Chuseok and Seollal move with the
    lunar calendar and cannot be guessed. Same class as the fabricated calendar
    this project deleted once, landing at the tail where nobody looks."""
    ladder = B._business_days_after(dt.date(2026, 7, 24), 400)
    assert len(ladder) == 400
    covered = B._covered_years()
    assert {dt.date.fromisoformat(x).year for x in ladder} <= covered


def test_the_coverage_assertion_actually_bites(monkeypatch):
    """A check that cannot fail is decoration. Shrink the apparent coverage and
    the same call must refuse rather than emit dates it cannot vouch for."""
    monkeypatch.setattr(B, "_covered_years", lambda: {2026})
    with pytest.raises(B.HolidayCoverageError, match="only holds entries"):
        B._business_days_after(dt.date(2026, 7, 24), 400)


def test_the_holiday_table_extends_on_demand():
    """Why there is no cliff today, pinned so a future swap to a static table
    is caught. `holidays.KR` is constructed for 2016–2035 but populates further
    years when asked — probed at 2050, where the lunar dates are computed, not
    extrapolated. If this ever stops being true, the ladder needs truncating
    and this test says so first."""
    from app.engine_port import _is_kr_business_day

    assert not _is_kr_business_day(dt.date(2050, 1, 1))   # 신정
    assert not _is_kr_business_day(dt.date(2050, 3, 1))   # 삼일절
    assert not _is_kr_business_day(dt.date(2050, 9, 30))  # 추석, lunar
    assert 2050 in B._covered_years()


def test_the_horizon_stays_well_ahead_of_the_ladder_being_needed():
    """The refresh signal, same shape as the calendar horizon guard: it fires
    as a prompt to rebuild, not as a break. The ladder is generated from the
    dataset's asof, so it shortens as the data file ages without a rebuild.
    Below 60 remaining business days the freshness badge is working off a
    nearly exhausted ladder and would soon clamp."""
    m = _baked_manifest()
    today = dt.date.today().isoformat()
    remaining = sum(1 for d in m["businessDaysAfter"] if d > today)
    assert remaining >= 60, (
        f"only {remaining} business days left in the manifest ladder "
        f"(through {m['businessDaysAfter'][-1]}). Re-run "
        "backend/scripts/build_static.py against fresher data."
    )


def test_the_manifest_publishes_its_coverage():
    m = _baked_manifest()
    cov = m["holidayCoverage"]
    assert cov["ladderThrough"] == m["businessDaysAfter"][-1]
    assert cov["ladderDays"] == len(m["businessDaysAfter"])
    assert cov["constructedThrough"] >= dt.date.today().year


def test_a_removed_id_does_not_leave_a_stale_file(tmp_path):
    """The output tree is cleared before writing. Without that, renaming or
    dropping a series leaves a file that still resolves — the frontend would
    keep working and keep serving data for something that no longer exists."""
    out = tmp_path / "pub"
    (out / "api" / "series").mkdir(parents=True)
    ghost = out / "api" / "series" / "GHOST.full.json"
    ghost.write_text('{"stale":true}', encoding="utf-8")
    B.build(out, quiet=True)
    assert not ghost.exists()
