import pytest
import yaml

from nfsn_cli.models import Record
from nfsn_cli.zonefile import ZoneFileError, dump_zone, load_zone


def write(tmp_path, text):
    path = tmp_path / "zone.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_zone_reads_domain_and_records(tmp_path):
    path = write(
        tmp_path,
        """
        domain: example.com
        records:
          - name: tok._domainkey
            type: CNAME
            data: tok.dkim.amazonses.com.
            ttl: 3600
          - name: ""
            type: TXT
            data: v=spf1 include:_spf.google.com ~all
        """,
    )
    domain, records = load_zone(path)
    assert domain == "example.com"
    assert records[0] == Record("tok._domainkey", "CNAME", "tok.dkim.amazonses.com.", 3600)
    assert records[1].name == ""
    assert records[1].ttl is None


def test_missing_domain_is_rejected(tmp_path):
    path = write(tmp_path, "records: []\n")
    with pytest.raises(ZoneFileError, match="missing a 'domain' key"):
        load_zone(path)


def test_missing_records_list_is_rejected(tmp_path):
    path = write(tmp_path, "domain: example.com\n")
    with pytest.raises(ZoneFileError, match="missing a 'records' list"):
        load_zone(path)


def test_record_without_data_is_rejected(tmp_path):
    path = write(tmp_path, "domain: example.com\nrecords:\n  - name: www\n    type: A\n")
    with pytest.raises(ZoneFileError, match="missing data"):
        load_zone(path)


def test_duplicate_records_are_rejected(tmp_path):
    path = write(
        tmp_path,
        """
        domain: example.com
        records:
          - {name: www, type: A, data: 1.2.3.4}
          - {name: www, type: A, data: 1.2.3.4}
        """,
    )
    with pytest.raises(ZoneFileError, match="more than once"):
        load_zone(path)


def test_invalid_yaml_is_reported(tmp_path):
    path = write(tmp_path, "domain: [unclosed\n")
    with pytest.raises(ZoneFileError, match="not valid YAML"):
        load_zone(path)


def test_non_numeric_ttl_is_rejected(tmp_path):
    path = write(
        tmp_path,
        "domain: example.com\nrecords:\n  - {name: www, type: A, data: 1.2.3.4, ttl: soon}\n",
    )
    with pytest.raises(ZoneFileError, match="non-numeric ttl"):
        load_zone(path)


def test_dump_then_load_round_trips(tmp_path):
    records = [
        Record("", "TXT", "v=spf1 include:amazonses.com ~all", 3600),
        # NFSN keeps MX priority in `aux`, not as a prefix on `data`.
        Record("mail", "MX", "feedback-smtp.us-west-2.amazonses.com.", 3600, aux=10),
    ]
    path = write(tmp_path, dump_zone("example.com", records))
    domain, loaded = load_zone(path)
    assert domain == "example.com"
    assert set(loaded) == set(records)


def test_dump_is_sorted_for_stable_diffs():
    records = [Record("zzz", "A", "1.2.3.4"), Record("aaa", "A", "1.2.3.4")]
    payload = yaml.safe_load(dump_zone("example.com", records))
    assert [entry["name"] for entry in payload["records"]] == ["aaa", "zzz"]
