"""Unit tests for retrying an evaluation the workspace refused as busy.

The backend is patched out, so nothing here reaches JarvisPy. Run with
``python -m pytest tests``.
"""
from unittest.mock import patch

import pytest

import prometheux_chain as px
from prometheux_chain.client import jarvispy_client
from prometheux_chain.client.jarvispy_client import JarvisPyClient


class _Response:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


BUSY = _Response(409, {"status": "busy", "data": {"errorCode": "ENGINE_BUSY"},
                       "message": "0 runs and 24 engine calls are already in progress"})
DONE = _Response(200, {"status": "success", "data": {"resultSet": {"p": [[1]]}}})


class _Clock:
    """Stands in for time.monotonic and time.sleep, so waiting costs nothing."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(jarvispy_client.time, "monotonic", c.monotonic)
    monkeypatch.setattr(jarvispy_client.time, "sleep", c.sleep)
    monkeypatch.delenv("ENGINE_BUSY_RETRY_SECONDS", raising=False)
    with patch.object(JarvisPyClient, "_get_auth", return_value="t"):
        yield c


def _evaluate(responses):
    with patch.object(JarvisPyClient, "_send", side_effect=responses) as send:
        try:
            return px.evaluate_program("p(1). @output(\"p\")."), send
        except Exception as exc:
            return exc, send


def test_a_busy_evaluation_is_sent_again_until_it_runs(clock):
    result, send = _evaluate([BUSY, BUSY, DONE])
    assert send.call_count == 3
    assert len(clock.sleeps) == 2
    assert not isinstance(result, Exception)


def test_the_wait_backs_off_and_stays_capped(clock):
    _evaluate([BUSY] * 8 + [DONE])
    assert clock.sleeps[0] <= 0.5
    assert all(s <= 5.0 for s in clock.sleeps)
    assert clock.sleeps[-1] >= 2.5


def test_it_gives_up_when_the_budget_runs_out(clock, monkeypatch):
    monkeypatch.setenv("ENGINE_BUSY_RETRY_SECONDS", "10")
    result, send = _evaluate([BUSY] * 100)
    assert isinstance(result, Exception)
    assert "409" in str(result)
    assert clock.now <= 10.0
    assert send.call_count < 100


def test_zero_turns_the_retry_off(clock, monkeypatch):
    monkeypatch.setenv("ENGINE_BUSY_RETRY_SECONDS", "0")
    result, send = _evaluate([BUSY, DONE])
    assert isinstance(result, Exception)
    assert send.call_count == 1


@pytest.mark.parametrize("body", [
    {"status": "conflict", "message": "Output claimed by another run"},
    {"status": "busy", "data": {"errorCode": "OUTPUT_CLAIMED"}},
    {"status": "busy", "data": "ENGINE_BUSY"},
    ValueError("not JSON"),
])
def test_other_conflicts_fail_at_once(clock, body):
    result, send = _evaluate([_Response(409, body), DONE])
    assert isinstance(result, Exception)
    assert send.call_count == 1


def test_a_server_error_is_not_retried(clock):
    result, send = _evaluate([_Response(500, {"status": "error"}), DONE])
    assert isinstance(result, Exception)
    assert send.call_count == 1


@pytest.mark.parametrize("value, expected", [
    ("abc", 120.0), ("nan", 120.0), ("-5", 0.0), ("1e9", 3600.0), ("30", 30.0),
])
def test_bad_budgets_fall_back_to_safe_values(monkeypatch, value, expected):
    monkeypatch.setenv("ENGINE_BUSY_RETRY_SECONDS", value)
    assert JarvisPyClient._busy_retry_budget() == expected


def test_check_program_passes_after_a_busy_refusal(clock):
    with patch.object(JarvisPyClient, "_send", side_effect=[BUSY, DONE]):
        report = px.check_program("p(1). @output(\"p\").", expect={"p": [[1]]})
    assert report.ok, report.summary()
