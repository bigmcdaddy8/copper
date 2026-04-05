# Story-0000 — Environment Validation

**Status**: Completed  
**Phase**: 0 — Project Foundation

---

## Goal

Confirm that the development environment is correctly configured and that the existing project
scaffold is in a clean, working state before any business logic is written. This story has no
deliverable code beyond what already exists — it is a verification checkpoint.

---

## Background

The repository was initialized with a `trade_hunter` CLI scaffold under `apps/trade_hunter/`.
It contains a hello-world Typer command and a single smoke test. Before Story-0010 replaces the
scaffold with real functionality, we need confidence that the toolchain (uv, pytest, ruff) works
correctly on this machine and that the baseline smoke test is green.

---

## Acceptance Criteria

1. `uv sync --all-groups --all-packages` completes without errors from the workspace root.
2. `uv run pytest` runs and the existing `test_help` smoke test passes (exit code 0).
3. `uv run ruff check .` reports no errors.
4. `uv run ruff format --check .` reports no files would be reformatted.
5. `uv run python -m trade_hunter --help` exits 0 and prints usage output.

---

## Out of Scope

- No new source files are created.
- No new tests are written.
- No dependencies are added.
- No business logic is implemented.

---

## Implementation Notes

This story is completed entirely by running the verification commands above and confirming each
passes. If any command fails, the underlying issue must be fixed (e.g., missing dependency,
Python version mismatch, broken entry point) and documented before this story can be marked
Completed.

---

## Verification Steps

Run the following from the workspace root (`/home/temckee8/Documents/REPOs/copper`):

```bash
uv sync --all-groups --all-packages
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python -m trade_hunter --help
```

All five commands must exit 0. Paste the output for Vibe Engineer sign-off.

---

## Definition of Done

Vibe Engineer has reviewed the command output confirming all five verification steps passed and
has updated this story's status to **Completed**.
