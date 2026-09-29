"""테스트가 **어느 백엔드**에 말을 걸어도 되는가 — 그 판정을 잰다.

`_live_backend.claim()` 은 배포된 :8200 이 Tailscale Funnel 로 공개돼 있다는
사실 때문에 있다(그 파일 머리). 그런데 **그 판정 자체에는 시험이 없었다** —
그래서 09-30 에 결함이 하나 나왔다(아래 `…쪽지가_다른_포트의_것`).

여기서 산 포트를 열지 않는다. `claim()` 이 바깥과 말하는 자리는 셋뿐이고
(`is_up` · `_listening_pids` · `_marker`) 셋 다 갈아 끼운다.
"""

from __future__ import annotations

import pytest

import _live_backend as lb


@pytest.fixture
def wire(monkeypatch):
    """세 바깥 자리를 갈아 끼운다 — 포트도 프로세스도 쪽지도 안 만든다."""

    def _wire(*, up=True, pids=(1234,), marker=None, base="http://127.0.0.1:8200"):
        monkeypatch.setenv("SAURON_TEST_BASE", base)
        monkeypatch.setattr(lb, "is_up", lambda b, timeout=2.0: up)
        monkeypatch.setattr(lb, "_listening_pids", lambda port: set(pids))
        monkeypatch.setattr(lb, "_marker", lambda: marker)
        return lb.claim()

    return _wire


def test_포트가_닫혀_있으면_건너뛴다(wire):
    """비교할 것이 없다 — 이건 결함이 아니라 부재다(fail 이 아니다)."""
    v = wire(up=False)
    assert (v.run, v.fail) == (False, False)


def test_쪽지가_없으면_거절한다(wire):
    """포트가 열렸다는 사실만으로 진행하지 않는다 — 남의 라이브 서비스일 수 있다."""
    v = wire(marker=None)
    assert (v.run, v.fail) == (False, True)


def test_쪽지의_PID가_다르면_거절한다(wire):
    """지난번에 죽은 백엔드의 유령 쪽지."""
    v = wire(pids=(1234,), marker={"pid": 9999, "port": 8200})
    assert (v.run, v.fail) == (False, True)
    assert "9999" in v.reason


def test_쪽지가_다른_포트의_것이면_그렇게_말한다(wire):
    """★09-30 결함 — `claim()` 이 쪽지의 `port` 칸을 **안 읽고** 있었다.

    쓰는 쪽은 그 칸을 왜 쓰는지 적어 뒀다(`dev_marker.listening_port()`:
    「쪽지에 적어 두면 검사 쪽이 base URL 의 포트와 맞춰 볼 수 있다」). 읽는 쪽이
    그 맞춤을 안 하니, 개발용을 8299 로 띄워 둔 채(인계문이 그러라고 한다) :8200 을
    보면 **8299 쪽지의 PID** 를 8200 의 리스너와 견주고 「유령 쪽지이거나 남의
    것」이라고 말했다. 거절은 맞지만 **사유가 틀렸고**, 그 틀린 사유 때문에
    `test_static_agreement.py` 가 늘 `--ignore` 로 지나가고 있었다.

    거절은 그대로다(8200 에 있는 것이 남의 라이브 서비스일 수 있다). 바뀌는 것은
    사람이 읽고 **바로 행동할 수 있는 문장**인가다.
    """
    v = wire(pids=(12788,), marker={"pid": 16292, "port": 8299})
    assert (v.run, v.fail) == (False, True)
    assert "8299" in v.reason and "8200" in v.reason, (
        f"두 포트를 다 말해야 사람이 행동할 수 있다 — 지금 사유: {v.reason}"
    )
    assert "유령" not in v.reason, "유령 쪽지가 아니다 — 다른 포트의 쪽지다"


def test_쪽지에_포트가_없으면_PID만_대조한다(wire):
    """`--port` 를 안 준 채 띄우면 `listening_port()` 가 None 이다 — 그때는
    맞춰 볼 것이 없으므로 종전대로 PID 만 본다(거절 조건을 더 조이지 않는다)."""
    v = wire(pids=(1234,), marker={"pid": 1234, "port": None})
    assert (v.run, v.fail) == (True, False)


def test_다_맞으면_진행한다(wire):
    v = wire(pids=(1234,), marker={"pid": 1234, "port": 8200})
    assert (v.run, v.fail) == (True, False)
    assert "1234" in v.reason
