# Contributing

Thanks for your interest. This is a small, focused tool; the bar for changes is that they
keep it correct and predictable when it is pointed at someone's live DNS.

## Getting set up

```sh
git clone https://github.com/cfdude/nfsn-cli
cd nfsn-cli
uv sync
scripts/install-hooks.sh     # lint + format + secret scan + tests on every commit
```

You will need [uv](https://docs.astral.sh/uv/). [gitleaks](https://github.com/gitleaks/gitleaks)
is optional but recommended — the hook skips the secret scan without it.

## The checks

```sh
uv run ruff check .            # lint
uv run ruff format .           # format
uv run pytest                  # tests
```

**ruff is the only linter and formatter.** Do not add black, flake8, isort or pylint
alongside it. Line length is 100.

Tests live in the root `tests/` directory, never beside the source. Package root is `src/`.

CI runs all of the above on Python 3.11, 3.12 and 3.13, then builds the distribution and
smoke-tests the installed wheel.

## Commits

Conventional commits with a scope:

```
feat(dns): add replaceRR support
fix(transport): send raw body on PUT
docs(readme): document the MX wire shapes
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`.

Do not use `--no-verify`. If the hook fails, fix the cause.

## Testing against the real API

Most tests use `httpx.MockTransport` and never touch the network. That is deliberate — but
be aware of its limitation: **mocks encode your assumptions, so they cannot tell you when
your assumptions are wrong.**

Every significant bug found in this project so far was invisible to the mocked tests and
only appeared against the live API:

- `aux` and `scope` were being dropped entirely by the client.
- MX priority was being sent in the wrong shape on `addRR`.
- `removeRR` was being sent the joined shape and 404ing on every MX deletion.

So if you change anything about how records are read or written, **verify it against a real
zone** before opening the PR, and say in the PR description what you observed. Use a
throwaway record name, and clean it up. Note that MX record names may not contain an
underscore — NFSN rejects them.

When you learn something about the API that its documentation does not say, add it to the
README and pin it with a test that quotes the observed payload.

## Versioning

[Semantic Versioning](https://semver.org/spec/v2.0.0.html):

- **MAJOR** — a breaking change to the CLI surface, the zone-file format, or the Python API.
- **MINOR** — new commands, new API coverage, backwards-compatible behaviour.
- **PATCH** — bug fixes and documentation.

Until 1.0.0 the CLI surface may still shift; breaking changes will be called out in
[CHANGELOG.md](CHANGELOG.md) regardless.

## Releasing

1. Update `version` in `pyproject.toml`.
2. Move the `Unreleased` entries in `CHANGELOG.md` under the new version with today's date,
   and update the link references at the bottom.
3. Commit, then tag: `git tag v0.2.0 && git push origin main --tags`.

The release workflow verifies that the tag matches `pyproject.toml`, re-runs the full check
suite, and publishes to PyPI via Trusted Publishing. No API token is stored in this repo.

## Scope

In scope: anything NFSN's API can do, and making it safe to drive from a script.

Out of scope: managing DNS at other registrars, and anything that requires scraping the
member web interface rather than using the API.
