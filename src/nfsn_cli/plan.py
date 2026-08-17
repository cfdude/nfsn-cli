"""Diffing desired zone state against what is actually published.

Safety model: by default the planner only touches record sets (name + type pairs) that
the zone file actually mentions. A file describing three DKIM CNAMEs can therefore never
remove your MX records, no matter what else is in the zone. ``prune=True`` lifts that
restriction and makes the file authoritative for the whole zone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nfsn_cli.models import Record

ADD = "add"
REMOVE = "remove"


@dataclass(frozen=True)
class Change:
    action: str
    record: Record

    def render(self, domain: str) -> str:
        marker = "+" if self.action == ADD else "-"
        ttl = "" if self.record.ttl is None else f"  (ttl {self.record.ttl})"
        return (
            f"{marker} {self.record.display_name(domain):<52} "
            f"{self.record.type:<6} {self.record.describe()}{ttl}"
        )


@dataclass(frozen=True)
class Plan:
    domain: str
    changes: list[Change] = field(default_factory=list)
    unmanaged: list[Record] = field(default_factory=list)
    protected: list[Record] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.changes

    @property
    def removals(self) -> list[Change]:
        return [c for c in self.changes if c.action == REMOVE]

    @property
    def additions(self) -> list[Change]:
        return [c for c in self.changes if c.action == ADD]

    def render(self) -> str:
        footnotes = self._footnotes()
        if self.is_empty:
            head = f"No changes. {self.domain} already matches the zone file."
            return "\n".join([head, *footnotes]) if footnotes else head
        lines = [
            f"Plan for {self.domain}: {len(self.removals)} to remove, {len(self.additions)} to add",
            "",
        ]
        # Removals first: NFSN rejects an addRR whose name+type already exists.
        lines.extend(change.render(self.domain) for change in self.removals)
        lines.extend(change.render(self.domain) for change in self.additions)
        lines.extend(footnotes)
        return "\n".join(lines)

    def _footnotes(self) -> list[str]:
        notes: list[str] = []
        if self.unmanaged:
            notes.append(
                f"\n{len(self.unmanaged)} record(s) outside the zone file were left untouched "
                f"(use --prune to delete them)."
            )
        if self.protected:
            notes.append(
                f"\n{len(self.protected)} NFSN-managed record(s) were skipped; the API cannot "
                f"modify them even with --prune."
            )
        return notes


def build_plan(
    domain: str,
    desired: list[Record],
    actual: list[Record],
    *,
    prune: bool = False,
) -> Plan:
    managed_rrsets = {record.rrset for record in desired}
    desired_identities = {record.identity for record in desired}
    actual_identities = {record.identity for record in actual}

    removals: list[Change] = []
    unmanaged: list[Record] = []
    protected: list[Record] = []
    for record in actual:
        if record.identity in desired_identities:
            continue
        if record.is_protected:
            # NFSN owns these; the API cannot delete them and neither can we.
            protected.append(record)
        elif prune or record.rrset in managed_rrsets:
            removals.append(Change(REMOVE, record))
        else:
            unmanaged.append(record)

    additions = [
        Change(ADD, record) for record in desired if record.identity not in actual_identities
    ]

    # Removals precede additions so a changed record is deleted before being recreated.
    return Plan(
        domain=domain,
        changes=removals + additions,
        unmanaged=unmanaged,
        protected=protected,
    )
