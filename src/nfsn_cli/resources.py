"""The five NFSN object types, mirroring the official API reference.

Surface taken from https://members.nearlyfreespeech.net/wiki/API/Reference (read 2026-08-17).
The Introduction page also names a ``Database`` object type, but the Reference page documents
no members for it, so it is deliberately not implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass

from nfsn_cli.models import Record
from nfsn_cli.transport import NfsnError, NfsnTransport

# replaceRR is documented as supporting only these types.
REPLACEABLE_TYPES = frozenset({"A", "AAAA", "TXT"})

# addRR documents this set; anything else is rejected by the API.
VALID_RECORD_TYPES = frozenset({"A", "AAAA", "CNAME", "MX", "NS", "PTR", "SRV", "TXT"})


@dataclass(frozen=True)
class Resource:
    """Base for an addressable API object: /<kind>/<instance>/<member>."""

    transport: NfsnTransport
    instance: str
    kind: str = ""

    def _path(self, member: str) -> str:
        return f"/{self.kind}/{self.instance}/{member}"

    def get(self, member: str) -> object:
        return self.transport.get(self._path(member))

    def put(self, member: str, value: object) -> object:
        return self.transport.put(self._path(member), value)

    def call(self, member: str, **params: object) -> object:
        cleaned = {k: str(v) for k, v in params.items() if v is not None}
        return self.transport.post(self._path(member), cleaned)


@dataclass(frozen=True)
class Account(Resource):
    """Instance ID is the 12-digit account number, e.g. A1B2-C3D4E5F6."""

    kind: str = "account"

    # Properties
    @property
    def balance(self) -> object:
        return self.get("balance")

    @property
    def balance_cash(self) -> object:
        return self.get("balanceCash")

    @property
    def balance_credit(self) -> object:
        return self.get("balanceCredit")

    @property
    def balance_high(self) -> object:
        return self.get("balanceHigh")

    @property
    def friendly_name(self) -> object:
        return self.get("friendlyName")

    @property
    def status(self) -> object:
        return self.get("status")

    @property
    def sites(self) -> object:
        return self.get("sites")

    def set_friendly_name(self, name: str) -> object:
        return self.put("friendlyName", name)

    # Methods
    def add_site(self, site: str) -> object:
        """Create a new site backed by this account. This provisions real service."""
        return self.call("addSite", site=site)

    def add_warning(self, balance: float) -> object:
        return self.call("addWarning", balance=balance)

    def remove_warning(self, balance: float) -> object:
        return self.call("removeWarning", balance=balance)


@dataclass(frozen=True)
class Dns(Resource):
    """Instance ID is the domain name."""

    kind: str = "dns"

    # Properties
    @property
    def expire(self) -> object:
        return self.get("expire")

    @property
    def min_ttl(self) -> object:
        return self.get("minTTL")

    @property
    def refresh(self) -> object:
        return self.get("refresh")

    @property
    def retry(self) -> object:
        return self.get("retry")

    @property
    def serial(self) -> object:
        return self.get("serial")

    @property
    def sync(self) -> float:
        """Fraction of NFSN's anycast name servers carrying the current zone (0.0-1.0).

        GET only. Poll until it reaches 1.0 to be certain an update has propagated.
        """
        return float(self.get("sync"))  # type: ignore[arg-type]

    # Methods
    def list_rrs(
        self,
        name: str | None = None,
        record_type: str | None = None,
        data: str | None = None,
    ) -> list[Record]:
        payload = self.call("listRRs", name=name, type=record_type, data=data)
        if not isinstance(payload, list):
            raise NfsnError(
                f"Expected a list of records from listRRs, got {type(payload).__name__}"
            )
        return [_record_from_payload(entry) for entry in payload]

    def add_rr(self, record: Record) -> object:
        _reject_protected(record)
        _validate_type(record.type)
        # addRR has no `aux` parameter: the priority goes in `data` as a prefix, matching
        # the member interface. See Record.wire_data.
        return self.call(
            "addRR",
            name=record.name,
            type=record.type,
            data=record.wire_data,
            ttl=record.ttl,
        )

    def remove_rr(self, record: Record) -> object:
        _reject_protected(record)
        # removeRR matches on the SPLIT data -- the shape listRRs returns -- not the joined
        # shape addRR wants. Verified live 2026-08-17: removing an MX with "10 host." 404s,
        # removing the same record with "host." succeeds. See Record.wire_data.
        return self.call("removeRR", name=record.name, type=record.type, data=record.data)

    def replace_rr(self, record: Record) -> object:
        """Atomically replace every record at (name, type). A/AAAA/TXT only."""
        _reject_protected(record)
        if record.type not in REPLACEABLE_TYPES:
            raise NfsnError(
                f"replaceRR supports only {', '.join(sorted(REPLACEABLE_TYPES))}; "
                f"got {record.type}. Use remove_rr + add_rr instead."
            )
        return self.call(
            "replaceRR",
            name=record.name,
            type=record.type,
            data=record.wire_data,
            ttl=record.ttl,
        )

    def update_serial(self) -> object:
        return self.call("updateSerial")


@dataclass(frozen=True)
class Email(Resource):
    """Instance ID is the domain name."""

    kind: str = "email"

    def list_forwards(self) -> dict[str, str]:
        payload = self.call("listForwards")
        if payload in (None, ""):
            return {}
        if not isinstance(payload, dict):
            raise NfsnError(f"Expected a mapping from listForwards, got {payload!r}")
        return {str(k): str(v) for k, v in payload.items()}

    def set_forward(self, forward: str, dest_email: str) -> object:
        return self.call("setForward", forward=forward, dest_email=dest_email)

    def remove_forward(self, forward: str) -> object:
        return self.call("removeForward", forward=forward)


@dataclass(frozen=True)
class Member(Resource):
    """Instance ID is the member login name."""

    kind: str = "member"

    @property
    def accounts(self) -> object:
        return self.get("accounts")

    @property
    def sites(self) -> object:
        return self.get("sites")


@dataclass(frozen=True)
class Site(Resource):
    """Instance ID is the site short name (``example`` for example.nfshost.com)."""

    kind: str = "site"

    def add_alias(self, alias: str) -> object:
        return self.call("addAlias", alias=alias)

    def remove_alias(self, alias: str) -> object:
        return self.call("removeAlias", alias=alias)


class Nfsn:
    """Entry point: ``Nfsn(transport).dns("example.com").list_rrs()``."""

    def __init__(self, transport: NfsnTransport) -> None:
        self._transport = transport

    def account(self, number: str) -> Account:
        return Account(self._transport, number)

    def dns(self, domain: str) -> Dns:
        return Dns(self._transport, domain)

    def email(self, domain: str) -> Email:
        return Email(self._transport, domain)

    def member(self, login: str) -> Member:
        return Member(self._transport, login)

    def site(self, name: str) -> Site:
        return Site(self._transport, name)


def _validate_type(record_type: str) -> None:
    if record_type not in VALID_RECORD_TYPES:
        raise NfsnError(
            f"{record_type} is not an NFSN-supported record type "
            f"({', '.join(sorted(VALID_RECORD_TYPES))})."
        )


def _reject_protected(record: Record) -> None:
    if record.is_protected:
        raise NfsnError(
            f"Refusing to modify {record.rrset}: it is NFSN-managed "
            f"(scope={record.scope!r}), not yours to change."
        )


def _coerce_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _record_from_payload(entry: object) -> Record:
    if not isinstance(entry, dict):
        raise NfsnError(f"Expected a record object, got {entry!r}")
    scope = entry.get("scope")
    return Record(
        name=str(entry.get("name", "")),
        type=str(entry.get("type", "")),
        data=str(entry.get("data", "")),
        ttl=_coerce_int(entry.get("ttl")),
        aux=_coerce_int(entry.get("aux")),
        scope=None if scope in (None, "") else str(scope),
    )
