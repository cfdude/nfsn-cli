# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-08-17

### Fixed

- `nfsn dns add` and `nfsn dns remove` disagreed about how to write an MX or SRV priority, so
  a record created with `add ... MX "10 mail.example.com."` could not be deleted with the same
  arguments — `removeRR` matches on the split form and returned 404. Priority written either
  way is now normalized on construction, so both verbs agree whichever form you type.
- Passing a priority twice (`add ... "10 mail.example.com." --aux 10`) silently produced
  `"10 10 mail.example.com."`, creating a malformed record. It is now rejected with an error
  naming both values.

### Added

- `plan` and `apply` refuse to leave a CNAME sharing a name with any other record, which NFSN
  documents as undefined behaviour and the API does not enforce. The check runs against the
  zone as it would exist after the plan, so it also catches a collision with a published
  record the zone file never mentions — and still allows a plan that removes the conflicting
  record in the same run.

## [0.1.0] - 2026-08-17

Initial release. Published to PyPI as
[`nfsn-cli`](https://pypi.org/project/nfsn-cli/).

### Added

- Full coverage of NFSN's documented API surface: Account, DNS, Email, Member and Site.
- `nfsn` CLI with per-resource subcommands, confirmation prompts on every mutating call,
  and `--json` output on reads.
- Declarative DNS workflow: `nfsn dns export`, `plan`, and `apply`, with a diff shown before
  anything is changed and a dry run by default.
- Safety model for `apply`: only record sets (name + type) named by the zone file are
  touched. `--prune` opts into whole-zone authority. Records NFSN owns (`scope` other than
  `member`) are never proposed for removal.
- `nfsn dns sync` and `apply --wait`, exposing NFSN's `sync` property (the fraction of
  anycast name servers carrying the current zone) so a change can be confirmed as
  propagated rather than assumed.
- Correct handling of NFSN's three different MX wire shapes — `addRR` takes the priority
  joined into `data`, `listRRs` returns it split into `aux`, and `removeRR` matches on the
  split form. See the README; none of this is documented upstream.
- Clock-skew detection: NFSN rejects requests more than 5 seconds from its clock, which
  otherwise surfaces as a misleading authentication failure.
- Credential resolution from environment variables, `~/.config/nfsn/credentials`, or the
  legacy `~/.nfsn-api` JSON file used by NFSN's Perl library and `python-nfsn`.
- Typed Python client (`nfsn_cli.Nfsn`) usable independently of the CLI.

### Security

- Documented why NFSN's authentication scheme forces SHA-1, what bounds the exposure, and
  where to change it if NFSN ever offers a stronger algorithm. No behaviour change — the
  hash is dictated by the server.

[Unreleased]: https://github.com/cfdude/nfsn-cli/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/cfdude/nfsn-cli/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/cfdude/nfsn-cli/releases/tag/v0.1.0
