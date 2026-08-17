import json
from email.utils import formatdate
from urllib.parse import parse_qs

import httpx
import pytest

from nfsn_cli.config import Credentials
from nfsn_cli.transport import (
    NfsnAuthError,
    NfsnClockSkewError,
    NfsnError,
    NfsnTransport,
)

CREDENTIALS = Credentials(login="testuser", api_key="topsecret")


def make_transport(handler):
    return NfsnTransport(CREDENTIALS, transport=httpx.MockTransport(handler))


def test_get_issues_a_get_with_no_body():
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["body"] = request.content
        return httpx.Response(200, content=b"9.04")

    with make_transport(handler) as t:
        value = t.get("/account/A1B2-C3D4E5F6/balance")

    assert seen["method"] == "GET"
    assert seen["body"] == b""
    assert value == 9.04


def test_put_sends_the_raw_value_as_the_body():
    """NFSN replaces the property with the request body verbatim -- not JSON, not a form."""
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["body"] = request.content
        return httpx.Response(200, content=b"")

    with make_transport(handler) as t:
        t.put("/dns/example.com/minTTL", 3600)

    assert seen["method"] == "PUT"
    assert seen["body"] == b"3600"


def test_post_sends_form_encoded_parameters():
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["content_type"] = request.headers.get("Content-Type")
        seen["body"] = parse_qs(request.content.decode())
        return httpx.Response(200, content=b"")

    with make_transport(handler) as t:
        t.post("/site/example/addAlias", {"alias": "www.example.com"})

    assert seen["method"] == "POST"
    assert seen["content_type"] == "application/x-www-form-urlencoded"
    assert seen["body"] == {"alias": ["www.example.com"]}


def test_every_verb_carries_the_auth_header_without_leaking_the_key():
    seen = []

    def handler(request):
        seen.append(request.headers.get("X-NFSN-Authentication", ""))
        return httpx.Response(200, content=b"")

    with make_transport(handler) as t:
        t.get("/dns/example.com/serial")
        t.put("/dns/example.com/expire", 86400)
        t.post("/dns/example.com/updateSerial", {})

    assert len(seen) == 3
    for header in seen:
        assert header.startswith("testuser;")
        assert len(header.split(";")) == 4
        assert "topsecret" not in header


def test_bare_string_responses_are_returned_as_text():
    """Documented: NFSN sometimes answers with a plain string rather than JSON."""
    with make_transport(lambda _r: httpx.Response(200, content=b"Ok\n")) as t:
        assert t.get("/account/X/status") == "Ok"


def test_empty_response_means_success():
    with make_transport(lambda _r: httpx.Response(200, content=b"")) as t:
        assert t.post("/dns/example.com/updateSerial", {}) is None


def test_json_object_responses_are_parsed():
    payload = {"color": "#00b000", "short": "OK", "status": "Ok"}
    with make_transport(lambda _r: httpx.Response(200, json=payload)) as t:
        assert t.get("/account/X/status") == payload


def test_error_payload_surfaces_error_and_debug():
    def handler(_request):
        return httpx.Response(400, json={"error": "Duplicate record", "debug": "addRR"})

    with make_transport(handler) as t, pytest.raises(NfsnError, match="Duplicate record"):
        t.post("/dns/example.com/addRR", {})


def test_401_raises_a_specific_auth_error():
    def handler(_request):
        return httpx.Response(401, json={"error": "Unauthorized", "debug": ""})

    with make_transport(handler) as t, pytest.raises(NfsnAuthError, match="NFSN_API_KEY"):
        t.get("/dns/example.com/serial")


def test_clock_skew_is_diagnosed_from_the_date_header():
    """NFSN rejects requests more than 5s off its clock; say so instead of 'auth failed'."""

    def handler(_request):
        return httpx.Response(
            401,
            json={"error": "Unauthorized", "debug": ""},
            headers={"Date": formatdate(timeval=0, usegmt=True)},
        )

    with make_transport(handler) as t, pytest.raises(NfsnClockSkewError, match="NTP"):
        t.get("/dns/example.com/serial")


def test_small_clock_skew_is_not_misreported():
    def handler(_request):
        return httpx.Response(
            401,
            json={"error": "Unauthorized", "debug": ""},
            headers={"Date": formatdate(usegmt=True)},
        )

    with make_transport(handler) as t, pytest.raises(NfsnAuthError):
        t.get("/dns/example.com/serial")


def test_non_json_error_body_is_still_reported():
    def handler(_request):
        return httpx.Response(500, content=b"<html>oops</html>")

    with make_transport(handler) as t, pytest.raises(NfsnError, match="oops"):
        t.get("/dns/example.com/serial")


def test_empty_error_body_gets_a_placeholder():
    with (
        make_transport(lambda _r: httpx.Response(503, content=b"")) as t,
        pytest.raises(NfsnError, match="empty response body"),
    ):
        t.get("/dns/example.com/serial")


def test_request_uri_used_for_signing_is_the_path_only():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, content=json.dumps([]).encode())

    with make_transport(handler) as t:
        t.post("/dns/example.com/listRRs", {})

    assert seen["url"] == "https://api.nearlyfreespeech.net/dns/example.com/listRRs"
