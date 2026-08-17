"""Loading and dumping the declarative zone file."""

from __future__ import annotations

from pathlib import Path

import yaml

from nfsn_cli.models import AUX_TYPES, Record


class ZoneFileError(RuntimeError):
    pass


def _optional_int(value: object, path: Path, index: int, field: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ZoneFileError(f"{path}: records[{index}] has a non-numeric {field}.") from exc


def load_zone(path: Path) -> tuple[str, list[Record]]:
    """Read a zone file and return (domain, records)."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ZoneFileError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(payload, dict):
        raise ZoneFileError(f"{path} must contain a mapping with 'domain' and 'records'.")

    domain = str(payload.get("domain", "")).strip()
    if not domain:
        raise ZoneFileError(f"{path} is missing a 'domain' key.")

    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise ZoneFileError(f"{path} is missing a 'records' list.")

    records: list[Record] = []
    for index, entry in enumerate(raw_records):
        if not isinstance(entry, dict):
            raise ZoneFileError(f"{path}: records[{index}] must be a mapping.")
        missing = [key for key in ("type", "data") if not str(entry.get(key, "")).strip()]
        if missing:
            raise ZoneFileError(f"{path}: records[{index}] is missing {', '.join(missing)}.")
        ttl = _optional_int(entry.get("ttl"), path, index, "ttl")
        aux = _optional_int(entry.get("aux"), path, index, "aux")
        record = Record(
            name=str(entry.get("name", "")),
            type=str(entry["type"]),
            data=str(entry["data"]),
            ttl=ttl,
            aux=aux,
        )
        if record.type in AUX_TYPES and record.aux is None:
            raise ZoneFileError(
                f"{path}: records[{index}] is a {record.type} record with no 'aux' priority. "
                f"Run `nfsn-cli export` to get the live values rather than guessing."
            )
        records.append(record)

    duplicates = _find_duplicates(records)
    if duplicates:
        joined = ", ".join(
            f"{record.name or '@'} {record.type} {record.describe()}" for record in duplicates
        )
        raise ZoneFileError(f"{path} lists the same record more than once: {joined}")
    return domain, records


def dump_zone(domain: str, records: list[Record]) -> str:
    """Serialize live records into the zone-file format, sorted for stable diffs."""
    ordered = sorted(records, key=lambda r: (r.name, r.type, r.aux or 0, r.data))
    payload = {
        "domain": domain,
        "records": [
            {
                "name": record.name,
                "type": record.type,
                "data": record.data,
                # `scope` is API metadata and is deliberately not round-tripped.
                **({"aux": record.aux} if record.aux is not None else {}),
                **({"ttl": record.ttl} if record.ttl is not None else {}),
            }
            for record in ordered
        ],
    }
    return yaml.safe_dump(payload, sort_keys=False, default_flow_style=False, width=1000)


def _find_duplicates(records: list[Record]) -> list[Record]:
    seen: set[tuple[str, str, str, int | None]] = set()
    duplicates: list[Record] = []
    for record in records:
        if record.identity in seen:
            duplicates.append(record)
        seen.add(record.identity)
    return duplicates
