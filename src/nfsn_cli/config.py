"""Credential loading.

Order of precedence:
  1. NFSN_LOGIN / NFSN_API_KEY environment variables
  2. ~/.config/nfsn/credentials (KEY=VALUE lines, mode 0600)
  3. ~/.nfsn-api (JSON: {"login": ..., "api-key": ...})

The third is the file format NFSN's Perl library established and python-nfsn adopted. We
read it for compatibility so existing users don't have to migrate, but new setups get the
XDG-style path.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CREDENTIALS_PATH = Path.home() / ".config" / "nfsn" / "credentials"
LEGACY_CREDENTIALS_PATH = Path.home() / ".nfsn-api"

TEMPLATE = """\
# NearlyFreeSpeech.NET API credentials.
# Generate the API key in the member panel: Profile -> Actions -> Set/Change API Key.
# This file must stay mode 0600.

NFSN_LOGIN=
NFSN_API_KEY=
"""


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Credentials:
    login: str
    api_key: str


def parse_env_text(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines, tolerating comments, blanks, `export `, and quotes."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        cleaned = value.strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in "\"'":
            cleaned = cleaned[1:-1]
        values[key.strip()] = cleaned
    return values


def _warn_if_permissive(path: Path) -> list[str]:
    mode = path.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        return [f"{path} is readable beyond your user account; run: chmod 600 {path}"]
    return []


def load_credentials(path: Path | None = None) -> tuple[Credentials, list[str]]:
    """Return credentials plus any non-fatal warnings."""
    env_login = os.environ.get("NFSN_LOGIN", "").strip()
    env_key = os.environ.get("NFSN_API_KEY", "").strip()
    if env_login and env_key:
        return Credentials(env_login, env_key), []

    target = Path(path) if path is not None else DEFAULT_CREDENTIALS_PATH
    if not target.exists():
        if path is None and LEGACY_CREDENTIALS_PATH.exists():
            return _load_legacy(LEGACY_CREDENTIALS_PATH)
        raise ConfigError(
            f"No credentials found. Set NFSN_LOGIN and NFSN_API_KEY, or create {target}.\n"
            f"Run `nfsn init` to write a template there."
        )

    warnings = _warn_if_permissive(target)
    values = parse_env_text(target.read_text(encoding="utf-8"))
    login = values.get("NFSN_LOGIN", "").strip()
    api_key = values.get("NFSN_API_KEY", "").strip()
    missing = [n for n, v in (("NFSN_LOGIN", login), ("NFSN_API_KEY", api_key)) if not v]
    if missing:
        raise ConfigError(f"{target} is missing a value for: {', '.join(missing)}")
    return Credentials(login, api_key), warnings


def _load_legacy(path: Path) -> tuple[Credentials, list[str]]:
    """Read the ~/.nfsn-api JSON file used by NFSN's Perl library and python-nfsn."""
    warnings = _warn_if_permissive(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"{path} must contain a JSON object.")
    login = str(payload.get("login", "")).strip()
    api_key = str(payload.get("api-key", "")).strip()
    if not login or not api_key:
        raise ConfigError(f"{path} must define both 'login' and 'api-key'.")
    warnings.append(f"Using legacy credentials from {path}; `nfsn init` migrates to XDG paths.")
    return Credentials(login, api_key), warnings


def write_template(path: Path | None = None) -> Path:
    """Create the credentials file with a template body if it does not already exist."""
    target = Path(path) if path is not None else DEFAULT_CREDENTIALS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ConfigError(f"{target} already exists; refusing to overwrite it.")
    target.touch(mode=0o600)
    target.write_text(TEMPLATE, encoding="utf-8")
    target.chmod(0o600)
    return target
