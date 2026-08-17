"""Coverage for the five NFSN object types and the MX write-shape asymmetry."""

from urllib.parse import parse_qs

import httpx
import pytest

from nfsn_cli.config import Credentials
from nfsn_cli.models import Record
from nfsn_cli.resources import Nfsn
from nfsn_cli.transport import NfsnError, NfsnTransport

CREDENTIALS = Credentials(login="u", api_key="k")


def capture(response=None):
    """Return (recorder, handler) so a test can inspect the request that was made."""
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = parse_qs(request.content.decode()) if request.content else {}
        seen["raw_body"] = request.content
        return response if response is not None else httpx.Response(200, content=b"")

    return seen, handler


def api(handler):
    conn = NfsnTransport(CREDENTIALS, transport=httpx.MockTransport(handler))
    return conn, Nfsn(conn)


# -- paths -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("build", "expected"),
    [
        (lambda n: n.account("A1B2-C3D4E5F6").balance, "/account/A1B2-C3D4E5F6/balance"),
        (lambda n: n.account("A1").balance_cash, "/account/A1/balanceCash"),
        (lambda n: n.account("A1").balance_credit, "/account/A1/balanceCredit"),
        (lambda n: n.account("A1").balance_high, "/account/A1/balanceHigh"),
        (lambda n: n.account("A1").friendly_name, "/account/A1/friendlyName"),
        (lambda n: n.account("A1").status, "/account/A1/status"),
        (lambda n: n.account("A1").sites, "/account/A1/sites"),
        (lambda n: n.dns("example.com").expire, "/dns/example.com/expire"),
        (lambda n: n.dns("example.com").min_ttl, "/dns/example.com/minTTL"),
        (lambda n: n.dns("example.com").refresh, "/dns/example.com/refresh"),
        (lambda n: n.dns("example.com").retry, "/dns/example.com/retry"),
        (lambda n: n.dns("example.com").serial, "/dns/example.com/serial"),
        (lambda n: n.member("guest").accounts, "/member/guest/accounts"),
        (lambda n: n.member("guest").sites, "/member/guest/sites"),
    ],
)
def test_property_paths_match_the_api_reference(build, expected):
    seen, handler = capture(httpx.Response(200, content=b"1"))
    conn, nfsn = api(handler)
    build(nfsn)
    conn.close()
    assert seen["path"] == expected
    assert seen["method"] == "GET"


def test_sync_is_returned_as_a_float():
    _seen, handler = capture(httpx.Response(200, content=b"0.5"))
    conn, nfsn = api(handler)
    assert nfsn.dns("example.com").sync == 0.5
    conn.close()


def test_friendly_name_is_written_with_put():
    seen, handler = capture()
    conn, nfsn = api(handler)
    nfsn.account("A1").set_friendly_name("Business")
    conn.close()
    assert seen["method"] == "PUT"
    assert seen["raw_body"] == b"Business"


# -- DNS records -------------------------------------------------------------


def test_add_rr_folds_mx_priority_into_data():
    """NFSN's addRR has no `aux` parameter -- priority is a prefix on `data`."""
    seen, handler = capture()
    conn, nfsn = api(handler)
    nfsn.dns("example.com").add_rr(Record("", "MX", "mail.example.com.", ttl=3600, aux=10))
    conn.close()
    assert seen["path"] == "/dns/example.com/addRR"
    assert seen["body"]["data"] == ["10 mail.example.com."]
    assert "aux" not in seen["body"]


def test_add_rr_leaves_non_mx_data_alone():
    seen, handler = capture()
    conn, nfsn = api(handler)
    nfsn.dns("example.com").add_rr(Record("www", "A", "192.0.2.1"))
    conn.close()
    assert seen["body"]["data"] == ["192.0.2.1"]


def test_remove_rr_uses_the_split_shape_not_the_joined_one():
    """Verified live: removeRR 404s on "10 host." and succeeds on "host.".

    This is the opposite of addRR, which is exactly why it is easy to get wrong.
    """
    seen, handler = capture()
    conn, nfsn = api(handler)
    nfsn.dns("example.com").remove_rr(Record("", "MX", "mail.example.com.", aux=10))
    conn.close()
    assert seen["path"] == "/dns/example.com/removeRR"
    assert seen["body"]["data"] == ["mail.example.com."]


def test_add_and_remove_disagree_on_data_shape_for_the_same_record():
    """Pins the three-way asymmetry so a future refactor cannot quietly unify them."""
    record = Record("", "MX", "mail.example.com.", aux=10)
    sent = {}

    def handler(request):
        from urllib.parse import parse_qs

        sent[request.url.path.rsplit("/", 1)[-1]] = parse_qs(request.content.decode())["data"][0]
        return httpx.Response(200, content=b"")

    conn, nfsn = api(handler)
    nfsn.dns("example.com").add_rr(record)
    nfsn.dns("example.com").remove_rr(record)
    conn.close()

    assert sent["addRR"] == "10 mail.example.com."
    assert sent["removeRR"] == "mail.example.com."


def test_add_rr_rejects_unknown_record_types():
    _seen, handler = capture()
    conn, nfsn = api(handler)
    with pytest.raises(NfsnError, match="not an NFSN-supported record type"):
        nfsn.dns("example.com").add_rr(Record("x", "SOA", "whatever"))
    conn.close()


def test_replace_rr_rejects_types_the_api_does_not_support():
    """replaceRR is documented as A, AAAA and TXT only."""
    _seen, handler = capture()
    conn, nfsn = api(handler)
    with pytest.raises(NfsnError, match="replaceRR supports only"):
        nfsn.dns("example.com").replace_rr(Record("", "MX", "mail.example.com.", aux=10))
    conn.close()


def test_replace_rr_accepts_txt():
    seen, handler = capture()
    conn, nfsn = api(handler)
    nfsn.dns("example.com").replace_rr(Record("", "TXT", "v=spf1 -all", ttl=3600))
    conn.close()
    assert seen["path"] == "/dns/example.com/replaceRR"
    assert seen["body"]["data"] == ["v=spf1 -all"]


def test_list_rrs_filters_are_passed_through():
    seen, handler = capture(httpx.Response(200, json=[]))
    conn, nfsn = api(handler)
    nfsn.dns("example.com").list_rrs(name="www", record_type="A")
    conn.close()
    assert seen["body"] == {"name": ["www"], "type": ["A"]}


def test_update_serial_posts_with_no_parameters():
    seen, handler = capture()
    conn, nfsn = api(handler)
    nfsn.dns("example.com").update_serial()
    conn.close()
    assert seen["path"] == "/dns/example.com/updateSerial"
    assert seen["body"] == {}


# -- email / site ------------------------------------------------------------


def test_list_forwards_returns_a_mapping():
    _seen, handler = capture(httpx.Response(200, json={"hello": "cs@example.net"}))
    conn, nfsn = api(handler)
    assert nfsn.email("example.com").list_forwards() == {"hello": "cs@example.net"}
    conn.close()


def test_list_forwards_tolerates_an_empty_response():
    _seen, handler = capture(httpx.Response(200, content=b""))
    conn, nfsn = api(handler)
    assert nfsn.email("example.com").list_forwards() == {}
    conn.close()


def test_set_forward_sends_both_parameters():
    seen, handler = capture()
    conn, nfsn = api(handler)
    nfsn.email("example.com").set_forward("hi", "h@example.net")
    conn.close()
    assert seen["path"] == "/email/example.com/setForward"
    assert seen["body"] == {"forward": ["hi"], "dest_email": ["h@example.net"]}


def test_remove_forward():
    seen, handler = capture()
    conn, nfsn = api(handler)
    nfsn.email("example.com").remove_forward("hi")
    conn.close()
    assert seen["path"] == "/email/example.com/removeForward"


def test_site_aliases():
    seen, handler = capture()
    conn, nfsn = api(handler)
    nfsn.site("mycoolsite").add_alias("mobile.example.com")
    assert seen["path"] == "/site/mycoolsite/addAlias"
    assert seen["body"] == {"alias": ["mobile.example.com"]}
    nfsn.site("mycoolsite").remove_alias("mobile.example.com")
    conn.close()
    assert seen["path"] == "/site/mycoolsite/removeAlias"


def test_account_add_site_and_warnings():
    seen, handler = capture()
    conn, nfsn = api(handler)
    nfsn.account("A1").add_site("testing")
    assert seen["path"] == "/account/A1/addSite"
    assert seen["body"] == {"site": ["testing"]}
    nfsn.account("A1").add_warning(1.23)
    assert seen["body"] == {"balance": ["1.23"]}
    nfsn.account("A1").remove_warning(1.23)
    conn.close()
    assert seen["path"] == "/account/A1/removeWarning"


def test_protected_records_are_refused_at_the_client():
    _seen, handler = capture()
    conn, nfsn = api(handler)
    system_ns = Record("", "NS", "ns.phx3.nearlyfreespeech.net.", scope="system")
    with pytest.raises(NfsnError, match="NFSN-managed"):
        nfsn.dns("example.com").remove_rr(system_ns)
    conn.close()
