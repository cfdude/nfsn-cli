# Security Policy

## Supported versions

This project is pre-1.0. Security fixes land on the latest released version only.

| Version | Supported |
| ------- | --------- |
| 0.1.x   | yes       |

## Reporting a vulnerability

Report privately through
[GitHub Security Advisories](https://github.com/cfdude/nfsn-cli/security/advisories/new).
Please do not open a public issue for a security problem.

Include what you did, what happened, and what you expected. A proof of concept helps. You
should get an acknowledgement within a week.

If the issue is in NearlyFreeSpeech.NET's service rather than in this client, report it to
NFSN through a secure support request in their member interface instead.

## Handling your credentials

This tool holds an API key that can modify DNS, create billable sites, and read account
balances. Treat it accordingly.

- Credentials are read from `NFSN_LOGIN` / `NFSN_API_KEY`, `~/.config/nfsn/credentials`, or
  the legacy `~/.nfsn-api`. `nfsn init` creates its file with mode `0600` and the tool warns
  if an existing credentials file is readable by anyone else.
- **The API key is never logged, never printed, and never included in error output.** It is
  used only as an input to the request signature; the `X-NFSN-Authentication` header carries
  a SHA-1 digest, not the key itself. There is a test asserting the key does not appear in
  that header.
- The tool talks only to `https://api.nearlyfreespeech.net` over TLS.
- Nothing is sent anywhere else — no telemetry, no analytics, no crash reporting.

If you believe a key has been exposed, generate a new one immediately from the NFSN member
panel under **Profile → Actions → Set/Change API Key**. Doing so invalidates the old key.

## Why this code uses SHA-1

Static analysis will flag `hashlib.sha1` in `src/nfsn_cli/auth.py`, and that flag is correct
in general — SHA-1 is broken for collision resistance. It is used here anyway because
**NFSN's API specifies it**: their authentication scheme defines both the request body hash
and the header digest as SHA-1, and the server rejects anything else. Substituting a stronger
hash would make every request fail.

What bounds the exposure:

- **The API key is never transmitted.** It is an input to the digest, not a value in the
  header. Forging a request therefore requires a *preimage* attack on SHA-1. The practical
  breaks against SHA-1 (SHAttered, 2017) are collision attacks, which do not yield preimages.
- **Every request is salted and time-bound.** A fresh 16-character random salt plus a Unix
  timestamp go into each digest. NFSN rejects timestamps more than 5 seconds from its clock
  and refuses to reuse a `(login, salt, timestamp)` triple, so the replay window is seconds.
- **Transport is HTTPS**, so the digest is not observable in transit in the first place.

The call site carries a `nosemgrep` annotation with this rationale, and the corresponding
code-scanning alert is dismissed as won't-fix rather than silently suppressed. If NFSN ever
offers a stronger algorithm, `_sha1` in `auth.py` is the only place that needs to change.

## Scope notes

Two behaviours are deliberate and are not vulnerabilities:

- **`--yes` skips confirmation prompts.** It exists for scripting. Anything destructive still
  requires it explicitly.
- **`--prune` deletes records absent from your zone file.** That is its documented purpose.
  `plan` shows exactly what would be removed, and `apply` is a dry run without `--yes`.

## Supply chain

Every push and pull request is scanned with Semgrep (SAST) and Trivy (dependencies and
filesystem), plus a weekly scheduled run to catch newly disclosed CVEs. Dependency updates
come through Renovate. Releases are published to PyPI with Trusted Publishing, so no
long-lived API token exists to leak.
