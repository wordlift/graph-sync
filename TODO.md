# TODO

## Completed

- [x] Create composite GitHub Action to install and run `worai graph sync`.
- [x] Implement wrapper script for `--config`, `--profile`, and optional `--debug`.
- [x] Add local tests for command construction and input validation.
- [x] Add installer tests for Python preflight and pinned version install command.
- [x] Add user-facing docs and technical spec.
- [x] Add project index.
- [x] Add release/pinning guidance and marketplace readiness checklist docs.
- [x] Bump default pinned `worai_version` to `1.17.0` and align tests/docs/specs.

## Future

- [x] Add automated release workflow for version tags and major tag alias updates.
- [ ] Add optional pip cache support for faster installs in repeated CI runs.
- [ ] Add a dedicated preflight workflow that validates Marketplace checklist fields before tagging.
