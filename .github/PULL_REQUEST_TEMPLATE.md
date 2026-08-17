## What this changes

<!-- One or two sentences. -->

## Why

<!-- The problem, not the patch. -->

## Verification

- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass
- [ ] `uv run pytest` passes
- [ ] Changelog updated under `Unreleased` (skip for pure refactors)

**If this changes how records are read or written**, mocked tests are not sufficient —
they encode assumptions rather than checking them. Describe what you observed against a
real zone:

```
<paste the relevant listRRs payload or command output>
```

## Notes for the reviewer

<!-- Anything surprising, any API behaviour that contradicts NFSN's docs, anything you
     were unsure about. -->
