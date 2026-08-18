"""MX/SRV priority may be written either way; internally it is stored one way.

NFSN's member interface takes `10 mail.example.com.` in a single Data field, and `addRR`
wants that same joined form. But `listRRs` and `removeRR` use the split form. Before
normalization, `nfsn dns add ... MX "10 mail.example.com."` succeeded while
`nfsn dns remove ... MX "10 mail.example.com."` returned 404 -- you could create a record you
could not delete with the same arguments.
"""

from urllib.parse import parse_qs

import httpx
import pytest

from nfsn_cli.config import Credentials
from nfsn_cli.models import Record
from nfsn_cli.resources import Nfsn
from nfsn_cli.transport import NfsnTransport
from nfsn_cli.zonefile import dump_zone, load_zone

CREDENTIALS = Credentials(login="u", api_key="k")


def test_joined_form_is_split_on_construction():
    record = Record("", "MX", "10 mail.example.com.")
    assert record.aux == 10
    assert record.data == "mail.example.com."


def test_split_form_is_left_alone():
    record = Record("", "MX", "mail.example.com.", aux=10)
    assert record.aux == 10
    assert record.data == "mail.example.com."


def test_both_forms_produce_an_identical_record():
    assert Record("", "MX", "10 mail.example.com.") == Record("", "MX", "mail.example.com.", aux=10)


def test_srv_priority_is_split_too():
    """SRV data is 'priority weight port target'; only the priority lives in aux."""
    record = Record("_jabber._tcp", "SRV", "1 2 3 service.example.com.")
    assert record.aux == 1
    assert record.data == "2 3 service.example.com."
    assert record.wire_data == "1 2 3 service.example.com."


def test_giving_the_priority_twice_is_an_error():
    """Previously this produced '10 10 mail.example.com.' -- a garbage record."""
    with pytest.raises(ValueError, match="sets the priority twice"):
        Record("", "MX", "10 mail.example.com.", aux=10)


def test_non_priority_types_are_untouched():
    """A TXT value that happens to start with a number must not be mangled."""
    record = Record("", "TXT", "2026 was a good year")
    assert record.aux is None
    assert record.data == "2026 was a good year"


def test_a_record_starting_with_a_number_is_untouched():
    record = Record("www", "A", "10.20.30.40")
    assert record.aux is None
    assert record.data == "10.20.30.40"


def test_mx_without_any_priority_is_left_for_the_zone_loader_to_reject():
    """Record itself stays permissive; load_zone is where the MX-needs-aux rule lives."""
    record = Record("", "MX", "mail.example.com.")
    assert record.aux is None


@pytest.mark.parametrize("written", ["10 mail.example.com.", "10   mail.example.com."])
def test_add_and_remove_agree_whichever_form_the_user_typed(written):
    """The bug this fixes: add used the joined shape, remove used the split shape."""
    sent = {}

    def handler(request):
        verb = request.url.path.rsplit("/", 1)[-1]
        sent[verb] = parse_qs(request.content.decode())["data"][0]
        return httpx.Response(200, content=b"")

    conn = NfsnTransport(CREDENTIALS, transport=httpx.MockTransport(handler))
    dns = Nfsn(conn).dns("example.com")
    record = Record("", "MX", written)
    dns.add_rr(record)
    dns.remove_rr(record)
    conn.close()

    assert sent["addRR"] == "10 mail.example.com."
    assert sent["removeRR"] == "mail.example.com."


def test_zone_file_accepts_the_joined_form(tmp_path):
    path = tmp_path / "zone.yaml"
    path.write_text(
        "domain: example.com\nrecords:\n  - {name: '', type: MX, data: '10 mail.example.com.'}\n",
        encoding="utf-8",
    )
    _domain, records = load_zone(path)
    assert records[0].aux == 10
    assert records[0].data == "mail.example.com."


def test_export_always_emits_the_split_form():
    """So a round-trip is stable regardless of how the record was originally written."""
    text = dump_zone("example.com", [Record("", "MX", "10 mail.example.com.")])
    assert "aux: 10" in text
    assert "data: mail.example.com." in text
