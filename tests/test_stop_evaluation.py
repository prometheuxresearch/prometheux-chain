"""Unit tests for tagging evaluations with an execution id and stopping them.

The backend is patched out, so nothing here reaches JarvisPy. Run with
``python -m pytest tests``.
"""
from unittest.mock import patch

import pytest

import prometheux_chain as px
from prometheux_chain.client.jarvispy_client import JarvisPyClient


class _Response:
    status_code = 200

    def __init__(self, body):
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


DONE = _Response({"status": "success", "data": {"resultSet": {"p": [[1]]}}})
STOPPED = _Response({"status": "success", "data": {"execution_id": "suite-1",
                                                   "engine_stopped": False}})


@pytest.fixture
def send():
    with patch.object(JarvisPyClient, "_get_auth", return_value="t"), \
            patch.object(JarvisPyClient, "_send") as send:
        yield send


def test_evaluate_sends_the_execution_id(send):
    send.return_value = DONE
    px.evaluate_program('p(1). @output("p").', execution_id="suite-1")
    assert send.call_args.kwargs["json"]["execution_id"] == "suite-1"


def test_evaluate_without_an_execution_id_sends_none(send):
    send.return_value = DONE
    px.evaluate_program('p(1). @output("p").')
    assert "execution_id" not in send.call_args.kwargs["json"]


def test_check_program_passes_the_execution_id_on(send):
    send.return_value = DONE
    report = px.check_program('p(1). @output("p").', expect={"p": [[1]]}, execution_id="suite-1")
    assert report.ok
    assert send.call_args.kwargs["json"]["execution_id"] == "suite-1"


def test_stop_evaluation_names_the_execution(send):
    send.return_value = STOPPED
    data = px.stop_evaluation("suite-1")
    method, url = send.call_args.args[:2]
    assert (method, url.endswith("/api/v1/vadalog/stop")) == ("GET", True)
    assert send.call_args.kwargs["params"] == {"execution_id": "suite-1"}
    assert data["engine_stopped"] is False


def test_stop_evaluation_without_an_id_stops_everything(send):
    send.return_value = STOPPED
    px.stop_evaluation()
    assert send.call_args.kwargs["params"] is None


def test_stop_evaluation_accepts_the_engines_own_answer(send):
    send.return_value = _Response({"data": None, "message": "Evaluation stopped"})
    assert px.stop_evaluation("suite-1") == {"data": None, "message": "Evaluation stopped"}


def test_stop_evaluation_raises_when_refused(send):
    send.return_value = _Response({"status": "error", "message": "nope"})
    with pytest.raises(Exception, match="nope"):
        px.stop_evaluation("suite-1")
