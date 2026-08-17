"""nfsn -- a command line interface for the NearlyFreeSpeech.NET API."""

from __future__ import annotations

from typing import Annotated

import typer

from nfsn_cli.cli.common import CredentialsOption, fail
from nfsn_cli.cli.dns_cmd import app as dns_app
from nfsn_cli.cli.resource_cmds import account_app, email_app, member_app, site_app
from nfsn_cli.config import ConfigError, write_template

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="A command line interface for the NearlyFreeSpeech.NET API.",
)


def _version_callback(value: bool) -> None:
    if value:
        from nfsn_cli import __version__

        typer.echo(f"nfsn-cli {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """A command line interface for the NearlyFreeSpeech.NET API."""


app.add_typer(dns_app, name="dns")
app.add_typer(account_app, name="account")
app.add_typer(email_app, name="email")
app.add_typer(member_app, name="member")
app.add_typer(site_app, name="site")


@app.command()
def init(credentials: CredentialsOption = None) -> None:
    """Write a credentials template at ~/.config/nfsn/credentials (mode 0600)."""
    try:
        path = write_template(credentials)
    except ConfigError as exc:
        fail(str(exc))
        return
    typer.echo(f"Created {path}. Fill in NFSN_LOGIN and NFSN_API_KEY.")


if __name__ == "__main__":  # pragma: no cover
    app()
