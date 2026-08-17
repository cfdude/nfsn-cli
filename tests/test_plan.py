from nfsn_cli.models import Record
from nfsn_cli.plan import ADD, REMOVE, build_plan

DOMAIN = "example.com"

MX = Record(name="", type="MX", data="1 ASPMX.L.GOOGLE.com.", ttl=3600)
SPF = Record(name="", type="TXT", data="v=spf1 include:_spf.google.com ~all", ttl=3600)
DKIM = Record(name="tok._domainkey", type="CNAME", data="tok.dkim.amazonses.com.", ttl=3600)


def test_no_changes_when_desired_matches_actual():
    result = build_plan(DOMAIN, [DKIM], [DKIM, MX])
    assert result.is_empty
    assert result.render().startswith("No changes.")


def test_missing_record_is_added():
    result = build_plan(DOMAIN, [DKIM], [MX])
    assert [(c.action, c.record) for c in result.changes] == [(ADD, DKIM)]


def test_unmanaged_rrsets_are_never_touched():
    """A zone file listing only DKIM must not be able to delete the MX records."""
    result = build_plan(DOMAIN, [DKIM], [MX, SPF])
    assert result.removals == []
    assert set(result.unmanaged) == {MX, SPF}


def test_changed_data_removes_before_adding():
    """This is the exact failure from 2026-08-17: right name+type, wrong target."""
    broken = Record(
        name="tok._domainkey",
        type="CNAME",
        data="tok.dkim.amazonses.com.example.com.",
    )
    result = build_plan(DOMAIN, [DKIM], [broken])
    actions = [c.action for c in result.changes]
    assert actions == [REMOVE, ADD]
    assert result.changes[0].record == broken
    assert result.changes[1].record == DKIM


def test_wrong_record_type_is_replaced():
    """A TXT holding the CNAME's target is a different rrset, so it needs --prune."""
    as_txt = Record(name="tok._domainkey", type="TXT", data="tok.dkim.amazonses.com.")
    without_prune = build_plan(DOMAIN, [DKIM], [as_txt])
    assert without_prune.removals == []
    assert as_txt in without_prune.unmanaged

    with_prune = build_plan(DOMAIN, [DKIM], [as_txt], prune=True)
    assert [c.action for c in with_prune.changes] == [REMOVE, ADD]


def test_prune_removes_everything_absent_from_the_zone_file():
    result = build_plan(DOMAIN, [DKIM], [MX, SPF, DKIM], prune=True)
    assert {c.record for c in result.removals} == {MX, SPF}
    assert result.additions == []
    assert result.unmanaged == []


def test_ttl_only_difference_is_not_a_change():
    same_data_new_ttl = Record(name=DKIM.name, type=DKIM.type, data=DKIM.data, ttl=60)
    assert build_plan(DOMAIN, [same_data_new_ttl], [DKIM]).is_empty


def test_render_lists_removals_before_additions():
    stale = Record(name="tok._domainkey", type="CNAME", data="wrong.example.com.")
    rendered = build_plan(DOMAIN, [DKIM], [stale]).render()
    assert rendered.index("- tok._domainkey") < rendered.index("+ tok._domainkey")


def test_apex_name_variants_are_equivalent():
    assert build_plan(DOMAIN, [Record(name="@", type="MX", data=MX.data)], [MX]).is_empty
