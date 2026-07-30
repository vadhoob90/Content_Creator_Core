# Changelog

All notable changes to Content Creator are documented here.

The project follows semantic versioning. Entries marked **Unreleased** are
present on the development branch but are not available from an immutable
release tag.

## [Unreleased]

### Changed

- Linked the PyPI package from the main README and documented the complete
  maintainer release and downstream-upgrade process.

## [0.6.0] - 2026-07-30

### Added

- Human-readable `overview` and guided, non-mutating `start` entry points.
- Typed coordinator workspace, provider, voice, run, warning, and recommended
  action state.
- Preview-first, immutable workspace dependency upgrades with validation and
  rollback.
- A task-oriented documentation index and registry-distribution release ADR.
- A validated, tag-driven PyPI release workflow using Trusted Publishing.
- A left-to-right repository workflow diagram for authors and maintainers.

### Changed

- Default help emphasizes the author command surface while preserving advanced
  command families and all existing CLI invocations.
- Offline doctor checks are reusable by the coordinator and overview.

## [0.5.0] - 2026-07-29

### Added

- A deterministic Content Creator Coordinator interface for agent hosts.
- Machine-readable workspace context, capability, run-list, and next-action
  commands.
- Workspace-scoped coordinator defaults that reduce repetitive questions
  without overriding explicit author choices.
- Packaged Content Creator and Voice Builder skills in generated workspaces.
- Whole-workspace voice verification through `voice verify-all`.

### Changed

- Generated repository guidance now begins from persisted coordinator context.
- Voice onboarding guidance distinguishes a stylistically different voice from
  a subject-matter perspective.

## [0.4.0] - 2026-07-29

### Added

- Thin author-workspace generation through `content-creator workspace create`.
- Explicit starter versus source-derived voice onboarding.
- The versioned Clear Professional Starter for authors without prior writing.
- Automatic perspective disabling while a starter voice is active.
- Automatic perspective catalogue resolution for approved source-derived
  voices.
- Recursive ingestion from external local writing directories.
- Persisted provider selection through `content-creator provider select`.
- A workspace-first landing README and separate Core development README.

### Changed

- Core no longer silently defaults to a metered API provider.
- Local file paths are removed from versioned voice source indexes.
- Generated workspaces ignore uploaded voice documents and operational voice
  work orders while retaining public URL inventories.
- Local author documents can be attested directly without publication or
  public attribution.
- README and repository references use the current Core and downstream names.

### Compatibility

- Existing approved v0.3 voice manifests remain readable because new manifest
  fields have backward-compatible defaults.
- Existing workspaces must select a provider explicitly or continue supplying
  `CONTENT_CREATOR_PROVIDER`.
- Existing active voices do not need starter onboarding.
- See [Migrating to v0.4](docs/guides/migrating-to-v0.4.md).

## [0.3.0]

- Added repository-owned agent architecture and versioned workspace
  dependencies.

## [0.2.0]

- Added the workspace-oriented provider-neutral Core.
