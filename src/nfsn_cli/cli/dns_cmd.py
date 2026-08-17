"""`nfsn dns` -- record management plus the declarative zone-file workflow."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

import typer

from nfsn_cli.cli.common import (
    CredentialsOption,
    JsonOption,
    api,
    confirm_write,
    emit,
    fail,
    run,
)
from nfsn_cli.models import Record
from nfsn_cli.plan import ADD, build_plan
from nfsn_cli.zonefile import ZoneFileError, dump_zone, load_zone

app = typer.Typer(no_args_is_help=True, help="DNS records and zone properties.")

PROPERTIES = ("expire", "minTTL", "refresh", "retry", "serial", "sync")

DomainArg = Annotated[str, typer.Argument(help="Domain name, e.g. example.com")]
NameOpt = Annotated[str, typer.Option("--name", "-n", help="Record name ('' or '@' = apex).")]
TtlOpt = Annotated[int | None, typer.Option("--ttl", help="TTL in seconds (default 3600).")]
AuxOpt = Annotated[
    int | None,
    typer.Option("--aux", help="Priority for MX/SRV. Sent as a prefix on data, per NFSN."),
]
YesOpt = Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")]


@app.command("list")
def list_records(
    domain: DomainArg,
    as_json: JsonOption = False,
    credentials: CredentialsOption = None,
) -> None:
    """List the zone's records."""
    conn, nfsn = api(credentials)
    records = run(conn, lambda: nfsn.dns(domain).list_rrs())
    conn.close()
    if as_json:
        emit(
            [
                {
                    "name": r.name,
                    "type": r.type,
                    "data": r.data,
                    "ttl": r.ttl,
                    "aux": r.aux,
                    "scope": r.scope,
                }
                for r in records
            ],
            as_json=True,
        )
        return
    for record in sorted(records, key=lambda r: (r.name, r.type, r.aux or 0, r.data)):
        ttl = "-" if record.ttl is None else str(record.ttl)
        typer.echo(
            f"{record.display_name(domain):<52} {record.type:<6} {ttl:<7} {record.describe()}"
        )


@app.command("props")
def properties(
    domain: DomainArg,
    as_json: JsonOption = False,
    credentials: CredentialsOption = None,
) -> None:
    """Show every zone property (expire, minTTL, refresh, retry, serial, sync)."""
    conn, nfsn = api(credentials)
    dns = nfsn.dns(domain)
    values = {prop: run(conn, lambda p=prop: dns.get(p)) for prop in PROPERTIES}
    conn.close()
    emit(values, as_json=as_json)


@app.command("get")
def get_property(
    domain: DomainArg,
    prop: Annotated[str, typer.Argument(help=f"One of: {', '.join(PROPERTIES)}")],
    credentials: CredentialsOption = None,
) -> None:
    """Read one zone property."""
    conn, nfsn = api(credentials)
    value = run(conn, lambda: nfsn.dns(domain).get(prop))
    conn.close()
    emit(value)


@app.command("set")
def set_property(
    domain: DomainArg,
    prop: Annotated[str, typer.Argument(help="Property to write (sync is read-only).")],
    value: Annotated[str, typer.Argument(help="New value.")],
    yes: YesOpt = False,
    credentials: CredentialsOption = None,
) -> None:
    """Write one zone property."""
    if prop == "sync":
        fail("`sync` is GET-only -- it reports propagation, it cannot be set.")
    confirm_write(f"Set {prop} = {value} on {domain}", yes=yes)
    conn, nfsn = api(credentials)
    run(conn, lambda: nfsn.dns(domain).put(prop, value))
    conn.close()
    typer.echo(f"{prop} set to {value}.")


@app.command()
def add(
    domain: DomainArg,
    record_type: Annotated[str, typer.Argument(help="A, AAAA, CNAME, MX, NS, PTR, SRV, TXT")],
    data: Annotated[str, typer.Argument(help="Record data, member-interface format.")],
    name: NameOpt = "",
    ttl: TtlOpt = None,
    aux: AuxOpt = None,
    yes: YesOpt = False,
    credentials: CredentialsOption = None,
) -> None:
    """Add one resource record."""
    record = Record(name=name, type=record_type, data=data, ttl=ttl, aux=aux)
    confirm_write(f"Add  {record.display_name(domain)}  {record.type}  {record.wire_data}", yes=yes)
    conn, nfsn = api(credentials)
    run(conn, lambda: nfsn.dns(domain).add_rr(record))
    conn.close()
    typer.echo("Added.")


@app.command()
def remove(
    domain: DomainArg,
    record_type: Annotated[str, typer.Argument(help="Record type.")],
    data: Annotated[str, typer.Argument(help="Record data to match.")],
    name: NameOpt = "",
    aux: AuxOpt = None,
    yes: YesOpt = False,
    credentials: CredentialsOption = None,
) -> None:
    """Remove one resource record."""
    record = Record(name=name, type=record_type, data=data, aux=aux)
    confirm_write(
        f"Remove  {record.display_name(domain)}  {record.type}  {record.wire_data}", yes=yes
    )
    conn, nfsn = api(credentials)
    run(conn, lambda: nfsn.dns(domain).remove_rr(record))
    conn.close()
    typer.echo("Removed.")


@app.command()
def replace(
    domain: DomainArg,
    record_type: Annotated[str, typer.Argument(help="A, AAAA or TXT only.")],
    data: Annotated[str, typer.Argument(help="New record data.")],
    name: NameOpt = "",
    ttl: TtlOpt = None,
    yes: YesOpt = False,
    credentials: CredentialsOption = None,
) -> None:
    """Atomically replace every record at (name, type). A/AAAA/TXT only."""
    record = Record(name=name, type=record_type, data=data, ttl=ttl)
    confirm_write(
        f"Replace all {record.type} at {record.display_name(domain)} with {record.data}", yes=yes
    )
    conn, nfsn = api(credentials)
    run(conn, lambda: nfsn.dns(domain).replace_rr(record))
    conn.close()
    typer.echo("Replaced.")


@app.command("update-serial")
def update_serial(
    domain: DomainArg,
    yes: YesOpt = False,
    credentials: CredentialsOption = None,
) -> None:
    """Bump the zone serial and trigger a refresh."""
    confirm_write(f"Update the serial for {domain}", yes=yes)
    conn, nfsn = api(credentials)
    run(conn, lambda: nfsn.dns(domain).update_serial())
    conn.close()
    typer.echo("Serial updated.")


@app.command()
def sync(
    domain: DomainArg,
    watch: Annotated[
        bool, typer.Option("--watch", help="Poll until propagation reaches 1.0.")
    ] = False,
    interval: Annotated[float, typer.Option("--interval", help="Seconds between polls.")] = 5.0,
    timeout: Annotated[float, typer.Option("--timeout", help="Give up after N seconds.")] = 300.0,
    credentials: CredentialsOption = None,
) -> None:
    """Report what fraction of NFSN's name servers have the current zone."""
    conn, nfsn = api(credentials)
    dns = nfsn.dns(domain)
    deadline = time.monotonic() + timeout
    while True:
        value = run(conn, lambda: dns.sync)
        typer.echo(f"sync {value:.2f}")
        if not watch or value >= 1.0:
            break
        if time.monotonic() >= deadline:
            conn.close()
            fail(f"Still at {value:.2f} after {timeout:.0f}s.")
        time.sleep(interval)
    conn.close()


# -- declarative zone-file workflow ------------------------------------------

ZoneFileArg = Annotated[Path, typer.Argument(help="Zone file describing desired state.")]
PruneOpt = Annotated[bool, typer.Option("--prune", help="Also remove records the zone file omits.")]


@app.command()
def export(
    domain: DomainArg,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write here instead of stdout.")
    ] = None,
    credentials: CredentialsOption = None,
) -> None:
    """Dump the live zone as a zone file you can edit and feed back to `apply`."""
    conn, nfsn = api(credentials)
    records = run(conn, lambda: nfsn.dns(domain).list_rrs())
    conn.close()
    text = dump_zone(domain, records)
    if output is None:
        typer.echo(text, nl=False)
    else:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"Wrote {len(records)} record(s) to {output}")


def _plan_for(zone_file: Path, credentials: Path | None, prune: bool):
    try:
        domain, desired = load_zone(zone_file)
    except (ZoneFileError, OSError) as exc:
        fail(str(exc))
        raise AssertionError("unreachable")  # pragma: no cover
    conn, nfsn = api(credentials)
    actual = run(conn, lambda: nfsn.dns(domain).list_rrs())
    return conn, nfsn, domain, build_plan(domain, desired, actual, prune=prune)


@app.command()
def plan(
    zone_file: ZoneFileArg,
    prune: PruneOpt = False,
    credentials: CredentialsOption = None,
) -> None:
    """Show what `apply` would change. Makes no modifications."""
    conn, _nfsn, _domain, result = _plan_for(zone_file, credentials, prune)
    conn.close()
    typer.echo(result.render())


@app.command()
def apply(
    zone_file: ZoneFileArg,
    yes: YesOpt = False,
    prune: PruneOpt = False,
    wait: Annotated[
        bool, typer.Option("--wait", help="Poll `sync` until propagation completes.")
    ] = False,
    credentials: CredentialsOption = None,
) -> None:
    """Make the zone match the zone file."""
    conn, nfsn, domain, result = _plan_for(zone_file, credentials, prune)
    typer.echo(result.render())
    if result.is_empty:
        conn.close()
        return
    if not yes:
        typer.echo("\nDry run. Re-run with --yes to execute.")
        conn.close()
        return

    typer.echo("")
    dns = nfsn.dns(domain)
    failures = 0
    try:
        for change in result.changes:
            try:
                if change.action == ADD:
                    dns.add_rr(change.record)
                else:
                    dns.remove_rr(change.record)
            except Exception as exc:  # noqa: BLE001 - report and continue
                failures += 1
                typer.secho(f"FAILED {change.render(domain)}\n  {exc}", fg=typer.colors.RED)
            else:
                typer.secho(f"ok {change.render(domain)}", fg=typer.colors.GREEN)
        if wait and not failures:
            typer.echo("\nWaiting for propagation...")
            deadline = time.monotonic() + 300
            while (value := dns.sync) < 1.0:
                typer.echo(f"  sync {value:.2f}")
                if time.monotonic() >= deadline:
                    typer.secho("  gave up waiting after 300s", fg=typer.colors.YELLOW)
                    break
                time.sleep(5)
            else:
                typer.echo("  sync 1.00 - fully propagated")
    finally:
        conn.close()
    if failures:
        fail(f"\n{failures} of {len(result.changes)} change(s) failed.")
    typer.echo(f"\nApplied {len(result.changes)} change(s) to {domain}.")
