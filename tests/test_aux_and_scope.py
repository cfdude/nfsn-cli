"""NFSN's `aux` (MX/SRV priority) and `scope` fields.

Both were found empirically on 2026-08-17 by dumping a live listRRs payload -- neither is
mentioned on the DNSAddRR reference page. The asymmetry they create is the subtle part:
listRRs SPLITS priority into `aux`, while addRR wants it re-joined as a prefix on `data`.
"""

import httpx
import pytest
import yaml

from nfsn_cli.config import Credentials
from nfsn_cli.models import Record
from nfsn_cli.plan import ADD, REMOVE, build_plan
from nfsn_cli.resources import Nfsn
from nfsn_cli.transport import NfsnTransport
from nfsn_cli.zonefile import ZoneFileError, dump_zone, load_zone

CREDENTIALS = Credentials(login="u", api_key="k")
DOMAIN = "example.com"

# Verbatim from a live listRRs response against example.com.
LIVE_PAYLOAD = [
    {
        "name": "",
        "type": "MX",
        "data": "ASPMX.L.GOOGLE.COM.",
        "ttl": 3600,
        "scope": "member",
        "aux": 1,
    },
    {
        "name": "",
        "type": "MX",
        "data": "ALT1.ASPMX.L.GOOGLE.COM.",
        "ttl": 3600,
        "scope": "member",
        "aux": 5,
    },
    {
        "name": "mail",
        "type": "TXT",
        "data": "v=spf1 include:amazonses.com ~all",
        "ttl": 3600,
        "scope": "member",
    },
]


def api(handler):
    conn = NfsnTransport(CREDENTIALS, transport=httpx.MockTransport(handler))
    return conn, Nfsn(conn)


def test_aux_and_scope_are_parsed_from_the_live_payload():
    conn, nfsn = api(lambda _r: httpx.Response(200, json=LIVE_PAYLOAD))
    records = nfsn.dns(DOMAIN).list_rrs()
    conn.close()

    by_data = {r.data: r for r in records}
    assert by_data["ASPMX.L.GOOGLE.COM."].aux == 1
    assert by_data["ALT1.ASPMX.L.GOOGLE.COM."].aux == 5
    assert by_data["v=spf1 include:amazonses.com ~all"].aux is None
    assert all(r.scope == "member" for r in records)


def test_read_shape_and_write_shape_differ_for_mx():
    """The core asymmetry: split on read, joined on write."""
    record = Record("", "MX", "ASPMX.L.GOOGLE.COM.", ttl=3600, aux=1)
    assert record.data == "ASPMX.L.GOOGLE.COM."
    assert record.wire_data == "1 ASPMX.L.GOOGLE.COM."


def test_wire_data_is_unchanged_when_there_is_no_priority():
    assert Record("www", "A", "192.0.2.1").wire_data == "192.0.2.1"


def test_priority_change_alone_is_a_real_change():
    live = Record("", "MX", "mx.example.com.", ttl=3600, aux=10, scope="member")
    desired = Record("", "MX", "mx.example.com.", ttl=3600, aux=20)
    result = build_plan(DOMAIN, [desired], [live])
    assert [c.action for c in result.changes] == [REMOVE, ADD]
    assert result.changes[1].record.aux == 20


def test_identical_priority_is_not_a_change():
    live = Record("", "MX", "mx.example.com.", ttl=3600, aux=10, scope="member")
    desired = Record("", "MX", "mx.example.com.", ttl=3600, aux=10)
    assert build_plan(DOMAIN, [desired], [live]).is_empty


def test_aux_round_trips_through_the_zone_file(tmp_path):
    records = [Record("", "MX", "ASPMX.L.GOOGLE.COM.", ttl=3600, aux=1, scope="member")]
    path = tmp_path / "zone.yaml"
    path.write_text(dump_zone(DOMAIN, records), encoding="utf-8")

    _domain, loaded = load_zone(path)

    assert loaded[0].aux == 1
    # scope is API metadata and must not be written back out.
    assert "scope" not in yaml.safe_load(path.read_text())["records"][0]


def test_mx_without_aux_in_a_zone_file_is_rejected(tmp_path):
    """Guards the silent priority-rewrite this module exists to prevent."""
    path = tmp_path / "zone.yaml"
    path.write_text(
        "domain: example.com\nrecords:\n  - {name: '', type: MX, data: mx.example.com.}\n",
        encoding="utf-8",
    )
    with pytest.raises(ZoneFileError, match="no 'aux' priority"):
        load_zone(path)


def test_protected_records_are_never_removed_even_with_prune():
    system_ns = Record("", "NS", "ns.phx3.nearlyfreespeech.net.", ttl=3600, scope="system")
    result = build_plan(DOMAIN, [], [system_ns], prune=True)
    assert result.removals == []
    assert result.protected == [system_ns]
    assert "NFSN-managed" in result.render()


def test_plan_output_shows_the_priority():
    desired = Record("mail", "MX", "feedback-smtp.us-west-2.amazonses.com.", aux=10)
    rendered = build_plan(DOMAIN, [desired], []).render()
    assert "10 feedback-smtp.us-west-2.amazonses.com." in rendered


def test_two_mx_with_same_priority_are_distinct_records():
    live = [
        Record("", "MX", "ALT1.ASPMX.L.GOOGLE.COM.", aux=5, scope="member"),
        Record("", "MX", "ALT2.ASPMX.L.GOOGLE.COM.", aux=5, scope="member"),
    ]
    assert build_plan(DOMAIN, live, live).is_empty
    assert len(build_plan(DOMAIN, [], live, prune=True).removals) == 2
