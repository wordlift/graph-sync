# Agent Guide

## Verification

- Run `./tests/run-worai.sh`, `./tests/install-worai.sh`, and `./tests/install-playwright.sh` after any logic change.
- Add or update tests when behavior changes.

## Documentation Sync

- Keep `README.md`, `VERSIONING.md`, `docs/`, `specs/`, `INDEX.md`, and `TODO.md` aligned with implementation.

## Action Scope

This repository provides a GitHub Action wrapper around:

- `worai graph sync --profile <name> [--debug]`
- `worai --config <path> graph sync --profile <name> [--debug]`
- installation of pinned `worai` versions via `worai_version`
- optional installation of pinned Python Playwright + browser binaries
