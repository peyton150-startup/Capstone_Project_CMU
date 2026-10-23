"""The model client's request limit covers the whole request, not each read.

A local server on 127.0.0.1 plays the slow provider: it sends its reply a
byte at a time, the way the 146 s xKiro request arrived. No real service is
contacted.
"""

import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from capstone.providers.chat import (
    ModelError,
    post_json,
    run_with_deadline,
    urllib_transport,
)

REPLY = b'{"ok": true}'


def test_work_finished_in_time_gives_its_result():
    assert run_with_deadline(lambda: 42, 1.0) == 42


def test_work_past_the_deadline_is_cut_off_at_the_deadline():
    release = threading.Event()
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        run_with_deadline(lambda: release.wait(10), 0.2)
    assert time.monotonic() - started < 1.0
    release.set()  # let the abandoned thread end


def test_an_error_from_the_work_reaches_the_caller_unchanged():
    error = urllib.error.HTTPError("http://x", 503, "busy", {}, None)

    def fail():
        raise error

    with pytest.raises(urllib.error.HTTPError) as raised:
        run_with_deadline(fail, 1.0)
    assert raised.value is error


@pytest.fixture
def server():
    """A local server; `delay` is the pause between bytes of its reply."""
    stop = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        delay = 0.0

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(REPLY)))
            self.end_headers()
            for byte in REPLY:
                if stop.wait(self.delay):
                    return
                self.wfile.write(bytes([byte]))
                self.wfile.flush()

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd, Handler
    stop.set()
    httpd.shutdown()
    httpd.server_close()


def url_of(httpd) -> str:
    host, port = httpd.server_address[:2]
    return f"http://{host}:{port}/v1/chat/completions"


def test_a_prompt_reply_is_returned_whole(server):
    httpd, _ = server
    assert urllib_transport(url_of(httpd), {}, b"{}", 2.0) == REPLY


def test_a_trickling_reply_is_cut_off_at_the_whole_request_limit(server):
    """Each byte arrives well inside the 0.5 s limit, so urllib's per-read
    timeout never fires; the reply as a whole would take about 2.4 s."""
    httpd, handler = server
    handler.delay = 0.2
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        urllib_transport(url_of(httpd), {}, b"{}", 0.5)
    assert time.monotonic() - started < 1.5


def test_the_cut_off_is_recorded_as_a_timeout_that_may_be_retried(server):
    httpd, handler = server
    handler.delay = 0.2
    with pytest.raises(ModelError, match="the model service timed out") as raised:
        post_json(urllib_transport, url_of(httpd), "key", {"q": 1}, 0.5)
    assert raised.value.transient
