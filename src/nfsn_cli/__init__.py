"""A modern command line interface and Python client for the NearlyFreeSpeech.NET API."""

from importlib.metadata import PackageNotFoundError, version

from nfsn_cli.models import Record
from nfsn_cli.resources import Account, Dns, Email, Member, Nfsn, Site
from nfsn_cli.transport import NfsnAuthError, NfsnClockSkewError, NfsnError, NfsnTransport

try:
    # Single source of truth is pyproject.toml; do not duplicate the number here.
    __version__ = version("nfsn-cli")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0+unknown"

__all__ = [
    "Account",
    "Dns",
    "Email",
    "Member",
    "Nfsn",
    "NfsnAuthError",
    "NfsnClockSkewError",
    "NfsnError",
    "NfsnTransport",
    "Record",
    "Site",
    "__version__",
]
