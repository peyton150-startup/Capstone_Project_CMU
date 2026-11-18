"""No real network: all Haas HTTP acceptance checks are local."""

from io import BytesIO
from urllib.request import ProxyHandler

import pytest

from capstone.ingestion.haas_http import (
    UnsafeHaasRequest,
    _DenyRedirects,
    haas_get,
    validate_haas_get,
)
from tests.test_haas_profile import profile


def test_approved_endpoints_and_bounded_sample_are_allowed():
    p = profile()
    for request in ("probe", "current", "sample?from=1&count=1000"):
        assert validate_haas_get(p, p.base_url + "/" + request)


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.10.5:8082/VF-4/probe",
        "https://192.168.10.4:8082/VF-4/probe",
        "http://192.168.10.4:8082/VF-4/../VF-4/probe",
        "http://192.168.10.4:8082/VF-4/current?x=1",
        "http://192.168.10.4:8082/VF-4/sample?from=1&count=0",
        "http://192.168.10.4:8082/VF-4/sample?from=1&count=10000",
        "http://192.168.10.4:8082/VF-4/sample?from=1&count=1&foo=bar",
        "http://192.168.10.4:8082/VF-4/probe#fragment",
    ],
)
def test_prohibits_host_switch_and_out_of_scope_request(url):
    with pytest.raises(UnsafeHaasRequest):
        validate_haas_get(profile(), url)


def test_transport_sends_get_with_no_proxy_or_redirect(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, count):
            captured["bytes_limit"] = count
            return b"<MTConnectDevices/>"

    class Opener:
        def open(self, request, timeout):
            captured["method"] = request.get_method()
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            return Response()

    def fake_build(*handlers):
        captured["no_proxy"] = any(
            isinstance(handler, ProxyHandler) and not handler.proxies
            for handler in handlers
        )
        captured["no_redirect"] = any(
            isinstance(handler, _DenyRedirects) for handler in handlers
        )
        return Opener()

    monkeypatch.setattr("capstone.ingestion.haas_http.build_opener", fake_build)
    p = profile()
    assert haas_get(p, p.base_url + "/probe") == "<MTConnectDevices/>"
    assert captured["method"] == "GET"
    assert captured["no_proxy"] and captured["no_redirect"]
    assert captured["bytes_limit"] > 0
