"""Shared CLI plumbing: credential wiring, output, and error handling."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from nfsn_cli.config import ConfigError, load_credentials
from nfsn_cli.resources import Nfsn
from nfsn_cli.transport import NfsnError, NfsnTransport

CredentialsOption = Annotated[
    Path | None,
    typer.Option("--credentials", "-c", help="Path to the credentials file."),
]

JsonOption = Annotated[
    bool,
    typer.Option("--json", help="Emit raw JSON instead of formatted text."),
]


def fail(message: str) -> None:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def transport(credentials_path: Path | None) -> NfsnTransport:
    try:
        credentials, warnings = load_credentials(credentials_path)
    except ConfigError as exc:
        fail(str(exc))
        raise AssertionError("unreachable")  # pragma: no cover
    for warning in warnings:
        typer.secho(f"warning: {warning}", fg=typer.colors.YELLOW, err=True)
    return NfsnTransport(credentials)


def api(credentials_path: Path | None) -> tuple[NfsnTransport, Nfsn]:
    conn = transport(credentials_path)
    return conn, Nfsn(conn)


def run(conn: NfsnTransport, action):
    """Execute an API call, converting NfsnError into a clean CLI failure."""
    try:
        return action()
    except NfsnError as exc:
        conn.close()
        fail(str(exc))
        raise AssertionError("unreachable")  # pragma: no cover


def emit(value: object, *, as_json: bool = False) -> None:
    if as_json:
        typer.echo(json.dumps(value, indent=2, sort_keys=True, default=str))
        return
    if isinstance(value, dict):
        for key in sorted(value):
            typer.echo(f"{key:<24} {value[key]}")
    elif isinstance(value, list):
        for item in value:
            typer.echo(item)
    elif value is None or value == "":
        typer.echo("(ok)")
    else:
        typer.echo(value)


def confirm_write(description: str, *, yes: bool) -> None:
    """Gate a mutating call behind an explicit confirmation."""
    if yes:
        return
    typer.echo(description)
    if not typer.confirm("Proceed?", default=False):
        typer.echo("Aborted.")
        raise typer.Exit(code=1)
