"""Unit tests for keepalive, connect retries and timeout messages in ``_send``.

A local HTTP server stands in for JarvisPy. Run with ``python -m pytest tests``.
"""
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import pytest
import urllib3.util.connection as urllib3_connection

from prometheux_chain.client import jarvispy_client
from prometheux_chain.client.jarvispy_client import JarvisPyClient


class _Handler(BaseHTTPRequestHandler):
    behaviour = "ok"

    def do_GET(self):
        if self.behaviour == "hang":
            time.sleep(1.5)
        if self.behaviour == "drop":
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        body = b'{"status": "success"}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        _Handler.behaviour = "ok"
        httpd.shutdown()
        httpd.server_close()


def test_keepalive_is_set_on_the_connection(server):
    applied = []
    real = urllib3_connection._set_socket_options

    def record(sock, options):
        applied.extend(options or [])
        real(sock, options)

    with patch.object(urllib3_connection, "_set_socket_options", side_effect=record):
        assert JarvisPyClient._send("GET", server).status_code == 200
    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in applied
    idle = getattr(socket, "TCP_KEEPIDLE", None) or getattr(socket, "TCP_KEEPALIVE", None)
    if idle is not None:
        assert (socket.IPPROTO_TCP, idle, jarvispy_client._KEEPALIVE_IDLE) in applied


def _failing_connects(times):
    real = urllib3_connection.create_connection
    attempts = []

    def connect(*args, **kwargs):
        attempts.append(1)
        if len(attempts) <= times:
            raise socket.timeout("timed out")
        return real(*args, **kwargs)

    return patch.object(urllib3_connection, "create_connection", side_effect=connect), attempts


def test_a_connection_that_does_not_open_is_tried_again(server):
    failing, attempts = _failing_connects(2)
    with failing:
        assert JarvisPyClient._send("GET", server).status_code == 200
    assert len(attempts) == 3


def test_giving_up_says_it_could_not_connect_and_how_many_times(server, monkeypatch):
    monkeypatch.setenv("JARVISPY_CONNECT_RETRIES", "1")
    failing, attempts = _failing_connects(10)
    with failing, pytest.raises(Exception, match=r"Could not connect to .* in 2 attempt\(s\)"):
        JarvisPyClient._send("GET", server)
    assert len(attempts) == 2


def test_a_read_timeout_reports_the_time_it_actually_waited(server):
    _Handler.behaviour = "hang"
    with pytest.raises(Exception, match=r"timed out after [01]s \(read timeout 0.5s\)"):
        JarvisPyClient._send("GET", server, timeout=(5, 0.5))


def test_a_connection_dropped_before_the_answer_is_not_called_unreachable(server):
    _Handler.behaviour = "drop"
    with pytest.raises(Exception, match="was lost after"):
        JarvisPyClient._send("GET", server)
