"""Unit tests for engine workers: extra engine replicas beside the running machine.

The backend is patched out, so nothing here reaches JarvisPy. Run with
``python -m pytest tests``.
"""
from unittest.mock import patch

import pytest

import prometheux_chain as px
from prometheux_chain.compute import manage_compute
from prometheux_chain.client.jarvispy_client import JarvisPyClient


class _Backend:
    def __init__(self, ready_after=0):
        self.desired = 0
        self.polls = 0
        self.ready_after = ready_after
        self.sets = []

    def set(self, replicas, idle_minutes=None, user_machine_id=None):
        self.sets.append((replicas, idle_minutes))
        self.desired = replicas
        self.polls = 0
        return {"status": "success", "data": {"desired": replicas, "ready": 0}}

    def get(self, user_machine_id=None):
        self.polls += 1
        ready = self.desired if self.polls > self.ready_after else 0
        return {"status": "success", "data": {"desired": self.desired, "ready": ready}}


@pytest.fixture
def backend():
    b = _Backend(ready_after=2)
    with patch.object(JarvisPyClient, "set_engine_workers", side_effect=b.set), \
            patch.object(JarvisPyClient, "get_engine_workers", side_effect=b.get), \
            patch.object(manage_compute.time, "sleep"):
        yield b


def test_set_returns_the_state(backend):
    assert px.set_engine_workers(2, idle_minutes=5) == {"desired": 2, "ready": 0}
    assert backend.sets == [(2, 5)]


def test_wait_polls_until_ready(backend):
    px.set_engine_workers(3)
    seen = []
    state = px.wait_for_engine_workers(3, on_progress=seen.append)
    assert state["ready"] == 3
    assert [s["ready"] for s in seen] == [0, 0, 3]


def test_wait_times_out(backend):
    backend.ready_after = 10 ** 6
    px.set_engine_workers(2)
    with pytest.raises(TimeoutError, match="0 of 2"):
        px.wait_for_engine_workers(2, timeout=0)


def test_context_manager_scales_up_then_down(backend):
    with px.engine_workers(2) as state:
        assert state["ready"] == 2
        assert backend.desired == 2
    assert backend.sets == [(2, None), (0, None)]


def test_context_manager_scales_down_when_the_block_fails(backend):
    with pytest.raises(RuntimeError):
        with px.engine_workers(2):
            raise RuntimeError("a test blew up")
    assert backend.desired == 0


def test_context_manager_scales_down_when_workers_never_come_up(backend):
    backend.ready_after = 10 ** 6
    with pytest.raises(TimeoutError):
        with px.engine_workers(2, timeout=0):
            pass
    assert backend.desired == 0


def test_keep_leaves_the_workers_running(backend):
    with px.engine_workers(1, keep=True):
        pass
    assert backend.desired == 1


def test_zero_workers_is_a_no_op_block(backend):
    with px.engine_workers(0) as state:
        assert state == {}
    assert backend.sets == [(0, None)]


class _Response:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


def test_a_refusal_raises_the_servers_message():
    refusal = _Response(409, {"status": "error",
                              "message": "No compute machine is running; start one before adding workers"})
    with patch.object(JarvisPyClient, "_get_auth", return_value="t"), \
            patch.object(JarvisPyClient, "_send", return_value=refusal):
        with pytest.raises(Exception, match="No compute machine is running"):
            px.set_engine_workers(1)


def test_a_user_without_billing_is_told_why():
    refused = _Response(402, {"code": "PAYMENT_REQUIRED", "error": "billing_required"})
    with patch.object(JarvisPyClient, "_get_auth", return_value="t"), \
            patch.object(JarvisPyClient, "_send", return_value=refused):
        with pytest.raises(Exception, match="add a payment method"):
            px.set_engine_workers(2)


@pytest.mark.parametrize("status", [404, 405])
def test_a_platform_without_workers_says_so(status):
    missing = _Response(status, {"detail": "Not Found"})
    with patch.object(JarvisPyClient, "_get_auth", return_value="t"), \
            patch.object(JarvisPyClient, "_send", return_value=missing):
        with pytest.raises(Exception, match="not available on this platform"):
            px.get_engine_workers()
