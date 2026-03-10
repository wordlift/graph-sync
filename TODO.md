# TODO

## Completed

- [x] Create composite GitHub Action to install and run `worai --profile <name> graph sync run`.
- [x] Implement wrapper script for `--config`, `--profile`, and optional `--debug`.
- [x] Add local tests for command construction and input validation.
- [x] Add installer tests for Python preflight and pinned version install command.
- [x] Add user-facing docs and technical spec.
- [x] Add project index.
- [x] Add release/pinning guidance and marketplace readiness checklist docs.
- [x] Bump default pinned `worai_version` to `6.9.4`, align action examples to `@v6`, and add `VERSIONING.md` policy.
- [x] Refresh `worai.toml` docs examples with anonymized multi-profile Google Sheets config (`acme`).
- [x] Add optional Python Playwright installer with Chromium browser defaults and dedicated tests.
- [x] Add optional built-in cache for pip and Playwright binaries with auto-derived cache key suffix fallback.
- [x] Bump default pinned `worai_version` to `6.9.6` and sync tests/docs/specs references.
- [x] Bump default pinned `worai_version` to `6.9.7` and sync tests/docs/specs references.
- [x] Bump default pinned `worai_version` to `6.11.0` and sync tests/docs/specs references.
- [x] Bump default pinned `worai_version` to `6.11.1` and sync tests/docs/specs references.
- [x] Bump default pinned `worai_version` to `6.12.1` and sync tests/docs/specs references.
- [x] Bump default pinned `worai_version` to `6.12.11` and sync tests/docs/specs references.
- [x] Bump default pinned `worai_version` to `6.12.12` and sync tests/docs/specs references.
- [x] Clarify `sheets_service_account` documentation in README/docs/specs (accepted formats and failure cases).
- [x] Clarify `sheets_service_account` vs `oauth.service_account` naming compatibility in docs/specs for `worai` `6.9.4`.
- [x] Switch docs/examples to use `oauth.service_account` naming for Google Sheets credentials.

## Future

- [x] Add automated release workflow for version tags and major/minor alias tag force updates.
- [ ] Add a dedicated preflight workflow that validates Marketplace checklist fields before tagging.
