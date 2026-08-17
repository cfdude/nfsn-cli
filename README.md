# nfsn-cli

A modern command line interface and Python client for the
[NearlyFreeSpeech.NET](https://www.nearlyfreespeech.net) API.

Covers the full documented API surface — Account, DNS, Email, Member and Site — plus a
declarative, plan-and-apply workflow for DNS zones.

```sh
pip install nfsn-cli
nfsn init
nfsn dns list example.com
```

## Why another one

The existing Python client, [`python-nfsn`](https://github.com/ktdreyer/python-nfsn), was
last committed in **June 2018**, targets **Python 2.6–3.5**, and depends on `beanbag`. It also
predates several API members: `balanceCash`, `balanceCredit`, `balanceHigh`, `replaceRR`, and
the `sync` property are all missing from it.

`nfsn-cli` is Python 3.11+, has no legacy baggage, ships a real CLI rather than a debug
wrapper, and — importantly — encodes several API behaviours that are **not in NFSN's
documentation** and that a naive client gets wrong. See [MX records](#mx-records-read-this).

It reads `~/.nfsn-api` if you already have one, so migrating costs nothing.

## Configuration

```sh
nfsn init                      # writes ~/.config/nfsn/credentials, mode 0600
$EDITOR ~/.config/nfsn/credentials
```

Generate the API key in the member panel: **Profile → Actions → Set/Change API Key.**

```
NFSN_LOGIN=yourlogin
NFSN_API_KEY=...
```

Credentials are resolved in this order:

1. `NFSN_LOGIN` / `NFSN_API_KEY` environment variables
2. `~/.config/nfsn/credentials`
3. `~/.nfsn-api` (the JSON file NFSN's Perl library established)

> NFSN rejects any request whose timestamp is more than **5 seconds** from its own clock.
> `nfsn-cli` detects this from the response `Date` header and tells you to sync your clock,
> rather than reporting a misleading authentication failure.

## Commands

```
nfsn dns      list, props, get, set, add, remove, replace, update-serial, sync,
              export, plan, apply
nfsn account  show, get, set-name, add-site, add-warning, remove-warning
nfsn email    forwards, set-forward, remove-forward
nfsn member   show
nfsn site     add-alias, remove-alias
```

Every mutating command prompts for confirmation; pass `--yes` to skip it. Read commands
accept `--json`.

## Declarative DNS

```sh
nfsn dns export example.com -o zone.yaml   # dump live state
$EDITOR zone.yaml
nfsn dns plan zone.yaml                    # diff, no changes made
nfsn dns apply zone.yaml --yes             # execute
nfsn dns apply zone.yaml --yes --wait      # ...and poll until fully propagated
```

`apply` without `--yes` is a dry run.

```yaml
domain: example.com
records:
  - name: ""                                  # "" or "@" is the apex
    type: TXT
    data: v=spf1 include:amazonses.com ~all
    ttl: 3600
  - name: mail
    type: MX
    data: feedback-smtp.us-west-2.amazonses.com.
    aux: 10                                   # priority; see below
```

### Safety model

By default `apply` only touches **record sets the zone file actually names** — a file listing
three DKIM CNAMEs cannot delete your MX records, whatever else is in the zone. Anything outside
those name+type pairs is reported as untouched and left alone.

`--prune` makes the file authoritative for the whole zone and deletes everything not listed.
Run `plan --prune` first, every time.

Records NFSN owns (`scope` other than `member`) are never proposed for removal, even under
`--prune`, and the client refuses to try.

TTL-only differences are not treated as changes; a delete/recreate cycle is not worth it.

One sharp edge: if the file declares an apex `TXT` for SPF and the apex also carries unrelated
TXT records (domain verification tokens, say), those share the name+type pair and *are*
considered managed — so they show up as removals. Read the plan.

## MX records: read this

NFSN uses **three different shapes for the same MX record across three verbs.** None of this
is documented; all of it was verified live against the API on 2026-08-17.

| Verb | `data` shape | Priority |
|---|---|---|
| `addRR` | `"10 mail.example.com."` | prefix on `data`; **there is no `aux` parameter** |
| `listRRs` | `"mail.example.com."` | separate `aux` field |
| `removeRR` | `"mail.example.com."` | matched **without** the prefix — the joined form 404s |

The consequences of getting this wrong are not subtle:

- Send the bare hostname to `addRR` and you create an MX record with no priority.
- Send the joined form to `removeRR` and the deletion silently 404s, so a "replace" leaves
  the old record in place and adds a second one beside it.

`nfsn-cli` handles the conversion for you: `Record.wire_data` produces the joined form for
`addRR`, and `remove_rr` sends the split form. Zone files always use the split shape (`data`
plus `aux`), matching what `export` gives you, and `load_zone` **rejects** an MX or SRV record
with no `aux` rather than guessing a default.

`replaceRR` supports only **A, AAAA and TXT**, so it sidesteps the issue entirely — but that
also means it cannot be used for MX or CNAME.

## Python API

```python
from nfsn_cli import Nfsn, NfsnTransport, Record
from nfsn_cli.config import load_credentials

credentials, _warnings = load_credentials()
with NfsnTransport(credentials) as transport:
    nfsn = Nfsn(transport)

    for record in nfsn.dns("example.com").list_rrs():
        print(record.display_name("example.com"), record.type, record.describe())

    print(nfsn.account("A1B2-C3D4E5F6").balance)
    print(nfsn.dns("example.com").sync)  # 0.0-1.0 propagation fraction
```

## API coverage

Mirrors [NFSN's API reference](https://members.nearlyfreespeech.net/wiki/API/Reference).

| Object | Properties | Methods |
|---|---|---|
| Account | `balance`, `balanceCash`, `balanceCredit`, `balanceHigh`, `friendlyName` (r/w), `status`, `sites` | `addSite`, `addWarning`, `removeWarning` |
| DNS | `expire`, `minTTL`, `refresh`, `retry`, `serial`, `sync` (read-only) | `addRR`, `listRRs`, `removeRR`, `replaceRR`, `updateSerial` |
| Email | — | `listForwards`, `setForward`, `removeForward` |
| Member | `accounts`, `sites` | — |
| Site | — | `addAlias`, `removeAlias` |

NFSN's Introduction page also names a `Database` object type, but its reference section
documents no members, so it is not implemented.

## Development

```sh
uv sync
scripts/install-hooks.sh
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

See [CONTRIBUTING.md](CONTRIBUTING.md) — in particular the note on why mocked tests are not
sufficient when changing how records are read or written.

- [CHANGELOG.md](CHANGELOG.md) — versions follow [SemVer](https://semver.org/spec/v2.0.0.html)
- [SECURITY.md](SECURITY.md) — reporting vulnerabilities, and how your API key is handled
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

## License

MIT. Not affiliated with or endorsed by NFSN, Inc.
