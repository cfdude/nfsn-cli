"""`nfsn account`, `nfsn email`, `nfsn member`, `nfsn site`."""

from __future__ import annotations

from typing import Annotated

import typer

from nfsn_cli.cli.common import (
    CredentialsOption,
    JsonOption,
    api,
    confirm_write,
    emit,
    run,
)

YesOpt = Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")]

account_app = typer.Typer(no_args_is_help=True, help="Account balances, status, and sites.")
email_app = typer.Typer(no_args_is_help=True, help="Email forwarding.")
member_app = typer.Typer(no_args_is_help=True, help="Membership: accounts and sites.")
site_app = typer.Typer(no_args_is_help=True, help="Site aliases.")

AccountArg = Annotated[str, typer.Argument(help="Account number, e.g. A1B2-C3D4E5F6")]
DomainArg = Annotated[str, typer.Argument(help="Domain name, e.g. example.com")]
LoginArg = Annotated[str, typer.Argument(help="Member login name.")]
SiteArg = Annotated[str, typer.Argument(help="Site short name, e.g. 'example'.")]

ACCOUNT_PROPERTIES = (
    "balance",
    "balanceCash",
    "balanceCredit",
    "balanceHigh",
    "friendlyName",
    "status",
    "sites",
)


# -- account -----------------------------------------------------------------


@account_app.command("show")
def account_show(
    number: AccountArg, as_json: JsonOption = False, credentials: CredentialsOption = None
) -> None:
    """Show every account property."""
    conn, nfsn = api(credentials)
    account = nfsn.account(number)
    values = {prop: run(conn, lambda p=prop: account.get(p)) for prop in ACCOUNT_PROPERTIES}
    conn.close()
    emit(values, as_json=as_json)


@account_app.command("get")
def account_get(
    number: AccountArg,
    prop: Annotated[str, typer.Argument(help=f"One of: {', '.join(ACCOUNT_PROPERTIES)}")],
    credentials: CredentialsOption = None,
) -> None:
    """Read one account property."""
    conn, nfsn = api(credentials)
    value = run(conn, lambda: nfsn.account(number).get(prop))
    conn.close()
    emit(value)


@account_app.command("set-name")
def account_set_name(
    number: AccountArg,
    name: Annotated[str, typer.Argument(help="New friendly name.")],
    yes: YesOpt = False,
    credentials: CredentialsOption = None,
) -> None:
    """Set the account's friendly name."""
    confirm_write(f"Rename account {number} to {name!r}", yes=yes)
    conn, nfsn = api(credentials)
    run(conn, lambda: nfsn.account(number).set_friendly_name(name))
    conn.close()
    typer.echo("Renamed.")


@account_app.command("add-site")
def account_add_site(
    number: AccountArg,
    site: Annotated[str, typer.Argument(help="Short name for the new site.")],
    yes: YesOpt = False,
    credentials: CredentialsOption = None,
) -> None:
    """Create a new site backed by this account. This provisions real, billable service."""
    confirm_write(
        f"Create site {site!r} on account {number}.\n"
        f"This provisions real hosting service and affects your balance.",
        yes=yes,
    )
    conn, nfsn = api(credentials)
    run(conn, lambda: nfsn.account(number).add_site(site))
    conn.close()
    typer.echo(f"Created site {site}. Allow a few minutes for DNS to propagate.")


@account_app.command("add-warning")
def account_add_warning(
    number: AccountArg,
    balance: Annotated[float, typer.Argument(help="Balance threshold to be warned at.")],
    yes: YesOpt = False,
    credentials: CredentialsOption = None,
) -> None:
    """Add a low-balance warning threshold."""
    confirm_write(f"Add a low-balance warning at {balance} on account {number}", yes=yes)
    conn, nfsn = api(credentials)
    run(conn, lambda: nfsn.account(number).add_warning(balance))
    conn.close()
    typer.echo("Warning added.")


@account_app.command("remove-warning")
def account_remove_warning(
    number: AccountArg,
    balance: Annotated[float, typer.Argument(help="Threshold to remove.")],
    yes: YesOpt = False,
    credentials: CredentialsOption = None,
) -> None:
    """Remove a low-balance warning threshold."""
    confirm_write(f"Remove the low-balance warning at {balance} on account {number}", yes=yes)
    conn, nfsn = api(credentials)
    run(conn, lambda: nfsn.account(number).remove_warning(balance))
    conn.close()
    typer.echo("Warning removed.")


# -- email -------------------------------------------------------------------


@email_app.command("forwards")
def email_forwards(
    domain: DomainArg, as_json: JsonOption = False, credentials: CredentialsOption = None
) -> None:
    """List email forwards for a domain."""
    conn, nfsn = api(credentials)
    forwards = run(conn, lambda: nfsn.email(domain).list_forwards())
    conn.close()
    emit(forwards, as_json=as_json)


@email_app.command("set-forward")
def email_set_forward(
    domain: DomainArg,
    forward: Annotated[str, typer.Argument(help="Local part, e.g. 'hello'.")],
    dest_email: Annotated[str, typer.Argument(help="Destination address.")],
    yes: YesOpt = False,
    credentials: CredentialsOption = None,
) -> None:
    """Create or update an email forward."""
    confirm_write(f"Forward {forward}@{domain} -> {dest_email}", yes=yes)
    conn, nfsn = api(credentials)
    run(conn, lambda: nfsn.email(domain).set_forward(forward, dest_email))
    conn.close()
    typer.echo("Forward set.")


@email_app.command("remove-forward")
def email_remove_forward(
    domain: DomainArg,
    forward: Annotated[str, typer.Argument(help="Local part to remove.")],
    yes: YesOpt = False,
    credentials: CredentialsOption = None,
) -> None:
    """Remove an email forward."""
    confirm_write(f"Remove the forward for {forward}@{domain}", yes=yes)
    conn, nfsn = api(credentials)
    run(conn, lambda: nfsn.email(domain).remove_forward(forward))
    conn.close()
    typer.echo("Forward removed.")


# -- member ------------------------------------------------------------------


@member_app.command("show")
def member_show(
    login: LoginArg, as_json: JsonOption = False, credentials: CredentialsOption = None
) -> None:
    """Show the member's accounts and sites."""
    conn, nfsn = api(credentials)
    member = nfsn.member(login)
    values = {
        "accounts": run(conn, lambda: member.accounts),
        "sites": run(conn, lambda: member.sites),
    }
    conn.close()
    emit(values, as_json=as_json)


# -- site --------------------------------------------------------------------


@site_app.command("add-alias")
def site_add_alias(
    name: SiteArg,
    alias: Annotated[str, typer.Argument(help="Hostname to alias to this site.")],
    yes: YesOpt = False,
    credentials: CredentialsOption = None,
) -> None:
    """Add a hostname alias to a site."""
    confirm_write(f"Alias {alias} -> site {name}", yes=yes)
    conn, nfsn = api(credentials)
    run(conn, lambda: nfsn.site(name).add_alias(alias))
    conn.close()
    typer.echo("Alias added.")


@site_app.command("remove-alias")
def site_remove_alias(
    name: SiteArg,
    alias: Annotated[str, typer.Argument(help="Hostname alias to remove.")],
    yes: YesOpt = False,
    credentials: CredentialsOption = None,
) -> None:
    """Remove a hostname alias from a site."""
    confirm_write(f"Remove alias {alias} from site {name}", yes=yes)
    conn, nfsn = api(credentials)
    run(conn, lambda: nfsn.site(name).remove_alias(alias))
    conn.close()
    typer.echo("Alias removed.")
