"""Strict read-only HTTP transport for a single shop-authorized Haas endpoint.

Only calls constructed from a validated HaasConnectionProfile may reach this
transport. No discovery, redirects, proxies, credentials or controller writes.
"""

from __future__ import annotations

import re
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from capstone.ingestion.collector import MAX_RESPONSE_BYTES, REQUEST_TIMEOUT_SECONDS
from capstone.ingestion.haas_profile import HaasConnectionProfile


class UnsafeHaasRequest(ValueError):
    """The requested URL is outside the explicitly approved GET surface."""


class _DenyRedirects(HTTPRedirectHandler):
    """Do not follow an agent response to any other endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_haas_get(profile: HaasConnectionProfile, url: str) -> str:
    """Allow exactly the approved probe/current/sample URLs and bounded query."""
    parsed = urlsplit(url)
    expected = urlsplit(profile.base_url)
    if (
        parsed.scheme != "http"
        or parsed.netloc != expected.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.path not in {
            expected.path + "/probe",
            expected.path + "/current",
            expected.path + "/sample",
        }
    ):
        raise UnsafeHaasRequest("request is outside approved MTConnect endpoint")
    endpoint = parsed.path.removeprefix(expected.path + "/")
    if endpoint in {"probe", "current"}:
        if parsed.query:
            raise UnsafeHaasRequest("probe/current may not carry query parameters")
    else:
        try:
            pairs = parse_qsl(parsed.query, strict_parsing=True, keep_blank_values=True)
            if len(pairs) != 2 or {key for key, _ in pairs} != {"from", "count"}:
                raise ValueError("unexpected sample query")
            params = dict(pairs)
            if not re.fullmatch(r"[0-9]+", params["from"]):
                raise ValueError("invalid from sequence")
            if not re.fullmatch(r"[0-9]+", params["count"]):
                raise ValueError("invalid count")
            if not 1 <= int(params["count"]) <= 1000:
                raise ValueError("count outside approved bounds")
        except ValueError as error:
            raise UnsafeHaasRequest("invalid bounded sample query") from error
    return url


def haas_get(profile: HaasConnectionProfile, url: str) -> str:
    """GET authorized MTConnect XML without redirects, proxies or unbounded reads.

    The operator must have already verified machine/agent identity and
    permission; this function does not independently prove controller consent.
    """
    validate_haas_get(profile, url)
    opener = build_opener(ProxyHandler({}), _DenyRedirects())
    request = Request(
        url,
        method="GET",
        headers={"Accept": "application/xml"},
    )
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        body = error.read(MAX_RESPONSE_BYTES + 1)
        if len(body) <= MAX_RESPONSE_BYTES and b"MTConnectError" in body:
            return body.decode("utf-8", errors="replace")
        raise
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("MTConnect XML response exceeded maximum byte count")
    return body.decode("utf-8")
