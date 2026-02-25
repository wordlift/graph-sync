# Release and Marketplace Guidance

## Release Process

1. Run tests:
   - `./tests/run-worai.sh`
   - `./tests/install-worai.sh`
   - `./tests/install-playwright.sh`
   - `./tests/resolve-cache-key.sh`
2. Push a semantic version tag (example `v6.0.0`) to GitHub.
3. Workflow `.github/workflows/release.yml` runs automatically and will:
   - validate tag format (`vMAJOR.MINOR.PATCH`)
   - update major alias tag `v<major>` to the same commit (for example `v6`)
   - create a GitHub Release with generated notes
4. Marketplace publication remains a manual UI step in GitHub Release edit page.

## Consumer Pinning

For best security, consumers should pin actions by full commit SHA. Example:

```yaml
- uses: wordlift/graph-sync@<full-commit-sha>
```

If a tag is used, prefer a stable major tag (for example `@v6`) maintained as an alias to immutable release commits.

## Marketplace Readiness Checklist

- Public repository with an `action.yml` at repository root.
- Clear `name`, `description`, `author`, `branding` metadata.
- Versioned releases and stable major tags (`v1`, `v2`, ...).
- README usage with pinned dependencies and input descriptions.
- Automated tests in CI.

## Marketplace Publication Automation Limit

- Full Marketplace publication is not exposed by a public GitHub API endpoint.
- The workflow automates release creation and tag management, then prints a step summary with the release URL and manual Marketplace checklist.

## Versioning Policy

- See `VERSIONING.md` for the lockstep major strategy between this action and `worai`.
