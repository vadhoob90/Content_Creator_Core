# ADR 0005: Gate package-registry distribution behind release validation

## Status

Proposed for the v0.6 release process.

## Context

A registry release would allow installation with:

```bash
uv tool install content-creator==0.6.0
```

The existing Git-tag dependency remains reproducible and exposes the exact
source required for licence compliance. A registry must not weaken those
properties or make an untested package route canonical.

## Decision

Keep immutable Git tags as the canonical workspace dependency until a registry
release passes all of the following:

1. Confirm the package name and publishing authority.
2. Build both wheel and source distribution from the release tag.
3. Verify packaged contracts, rubrics, profiles, packs, skills, and agent
   templates are present in the wheel.
4. Publish through GitHub Actions Trusted Publishing from a protected tag or
   release environment.
5. Record distribution hashes and repository/tag provenance in the GitHub
   release.
6. Test `uv tool install content-creator==<version>` in a clean environment.
7. Generate a thin workspace, run doctor and its tests, and exercise a
   previewed dependency upgrade.
8. Test rollback with `uv tool install --force content-creator==<previous>`.
9. Retain project, source, licence, changelog, and issue-tracker metadata in
   the package.

TestPyPI or an equivalent private dry run must precede the first production
publication. Registry publication must be tag-driven; pushes to `main` cannot
publish.

## Rollback

Registry releases are immutable. If a release is defective:

- mark it as yanked rather than deleting it;
- publish a corrected patch release;
- document the affected version and rollback command;
- retain the original Git tag and source; and
- keep existing pinned Git dependencies operational.

Changing the canonical installation documentation requires a separate reviewed
change after these checks pass.
