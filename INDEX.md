# Project Index

- `README.md`: user-facing action documentation and usage.
- `VERSIONING.md`: action and `worai` versioning and compatibility policy.
- `LICENSE`: project license.
- `action.yml`: action metadata and execution steps.
- `.github/workflows/release.yml`: manual release automation for immutable tags and major aliases.
- `scripts/install-worai.sh`: pinned `worai` installer with Python preflight checks.
- `scripts/install-playwright.sh`: optional Playwright/Chromium installer with input validation.
- `scripts/run-worai.sh`: runtime wrapper that validates inputs and runs `worai`.
- `tests/run-worai.sh`: local test suite for wrapper behavior.
- `tests/install-worai.sh`: local test suite for installer behavior.
- `tests/install-playwright.sh`: local test suite for Playwright installer behavior.
- `docs/usage.md`: concise operational usage reference.
- `docs/release-and-marketplace.md`: release process, pinning, and marketplace checklist.
- `specs/action-behavior.md`: technical behavior specification.
- `TODO.md`: current completed and pending work.
