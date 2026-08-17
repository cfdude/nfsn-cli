"""Core value types shared by the client, planner, and zone-file loader."""

from __future__ import annotations

from dataclasses import dataclass

# NFSN represents the zone apex as an empty name. Zone files may also spell it "@".
APEX_ALIASES = frozenset({"", "@"})

# NFSN tags each record with a scope. Records it manages itself cannot be edited via the
# API, so the planner must never propose removing them.
MEMBER_SCOPE = "member"

# Record types whose priority lives in NFSN's separate `aux` field rather than in `data`.
AUX_TYPES = frozenset({"MX", "SRV"})


def normalize_name(name: str | None) -> str:
    """Reduce a record name to NFSN's canonical form (apex is the empty string)."""
    value = (name or "").strip().rstrip(".")
    return "" if value in APEX_ALIASES else value.lower()


@dataclass(frozen=True)
class Record:
    """A single DNS resource record.

    ``data`` is passed to and from the API verbatim. ``aux`` carries the priority for MX and
    SRV records -- NFSN keeps it in its own field rather than as a prefix on ``data``, so
    dropping it silently rewrites every MX priority in the zone.
    """

    name: str
    type: str
    data: str
    ttl: int | None = None
    aux: int | None = None
    # Read-only metadata from the API; never sent back, never part of identity.
    scope: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", normalize_name(self.name))
        object.__setattr__(self, "type", self.type.strip().upper())
        object.__setattr__(self, "data", self.data.strip())

    @property
    def rrset(self) -> tuple[str, str]:
        """The (name, type) pair this record belongs to."""
        return (self.name, self.type)

    @property
    def identity(self) -> tuple[str, str, str, int | None]:
        """Everything that makes this record distinct.

        TTL is deliberately excluded -- a TTL-only difference is not worth a delete/recreate
        cycle. ``aux`` IS included: an MX priority change is a real change.
        """
        return (self.name, self.type, self.data, self.aux)

    @property
    def is_protected(self) -> bool:
        """True when NFSN owns this record and the API cannot modify it."""
        return self.scope is not None and self.scope != MEMBER_SCOPE

    def display_name(self, domain: str) -> str:
        return domain if self.name == "" else f"{self.name}.{domain}"

    @property
    def wire_data(self) -> str:
        """The ``data`` value to send when writing this record.

        NFSN uses three different shapes across three verbs. Verified live 2026-08-17:

        * ``addRR``    wants the JOINED form -- ``data="10 mail.example.com."``. There is
          no ``aux`` parameter; the member interface has no priority field either, so the
          documented "same format as the member interface" means the prefix.
        * ``listRRs``  returns the SPLIT form -- ``data="mail.example.com."``, ``aux=10``.
        * ``removeRR`` matches on the SPLIT form. Passing the joined form returns 404.

        So ``wire_data`` is for ``addRR`` only; ``removeRR`` uses plain ``data``.
        """
        if self.aux is None:
            return self.data
        return f"{self.aux} {self.data}"

    def describe(self) -> str:
        """Human-readable data, with the priority folded in for MX/SRV."""
        return self.wire_data
