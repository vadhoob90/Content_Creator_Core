# Public compatibility contracts

Core is both a command-line application and a versioned dependency used by
author workspaces. Internal refactoring must preserve the observable contracts
below. Version `1.0.0` establishes these surfaces as stable: an incompatible
change requires a new major release, migration support, and explicit release
notes.

## Supported surfaces

### Command line

- The `content-creator` executable and documented command families
- Argument names, defaults, exit codes, JSON output fields, and help behavior
- Approval, research, diagnostic, and publication checkpoints

Command behavior is characterized in `tests/test_cli.py`,
`tests/test_documentation_commands.py`, and
`tests/test_architecture_guardrails.py`.

### Python package

The supported root exports are declared by `content_creator.__all__`. Internal
module paths are not public merely because Python can import them. A new public
Python API must be intentionally exported and documented.

Core also maintains these documented subsystem façades while their
implementations may move:

| Import path | Stable surface |
| --- | --- |
| `content_creator.orchestrator` | `Orchestrator`, `OrchestrationError`, lifecycle stage and capability re-exports |
| `content_creator.diagnostics` | `RuntimeDiagnostics`, diagnostic contracts, and `DiagnosticDecisionRequired` |
| `content_creator.voice_builder` | `VoiceBuilder` and `VoiceBuildError` |
| `content_creator.voice_ml` | Names declared by `voice_ml.__all__` |

Sibling implementation paths such as `orchestration_support`, the modules under
`voice_build`, and the implementation modules under `voice_ml` are internal unless a
future release documents them as
supported. Repository tests may import an internal module to test its focused
behavior; that does not convert the path into a public contract.

When a documented façade changes from a module to a package, its import path
and characterized exports remain stable. A temporary compatibility shim for an
internal path is added only when a demonstrated downstream consumer needs a
migration window.

### Schemas and persisted state

- Work orders and run states
- Voice and perspective manifests, receipts, and component hashes
- Research, critique, learning, diagnostic, and visual artifacts
- Idempotency records and parent-run relationships

Readers must continue to accept supported older data. Writers use the current
canonical form. An incompatible schema change requires a migration, fixture
coverage for the old form, release notes, and an appropriate version bump.
The current writer version, supported read window, export commands, and
deprecation rules are defined in
[schema compatibility](schema-compatibility.md).

### Generated workspaces

The workspace generator owns its baseline layout and packaged resources while
preserving repository-owned customization. Generator changes require a fresh
workspace test, a repeat-generation preservation test, and downstream upgrade
verification.

### Extension contracts

Provider and visual adapter contracts are supported substitution points.
`VisualComponentRegistry`, `VisualRenderRequest`, `VisualRequestWorkflow`, and
`EditorialSvgRenderer` are additive root exports for installed-component
discovery, governed request execution, and credential-free deterministic
rendering. Component references persisted by the request workflow are immutable
provenance records.
Workflow stages and `RunCapabilities` are internal composition seams: they are
covered by architecture tests but become public only if deliberately exported
and documented in a future release.

## Compatibility policy

- Refactoring does not change observable behavior.
- Bug fixes may tighten invalid input handling but must document the change.
- Deprecated behavior needs a documented migration window before removal.
- Unknown schema versions fail closed; migration never guesses or mutates its input.
- Published PyPI versions, Git tags, and release artifacts are immutable.
- Downstream workspaces pin exact versions and upgrade deliberately.

Use Semantic Versioning for public releases and record migrations in the
changelog and focused guides.

## Release classification decision table

Classify a release by its effect on the supported surfaces above, not by the
number of changed lines or the implementation effort. When a release contains
more than one kind of change, use the highest version increment required by any
of them.

| Change | Version | Conditions and examples |
| --- | --- | --- |
| Internal refactor or maintenance | None or patch | No observable contract changes. It may remain unreleased or accompany a patch release. |
| Documentation-only correction | None or patch | Leave it unreleased unless users need a corrected immutable release. Do not use documentation to disguise a behavior change. |
| Backward-compatible bug fix | Patch | Restores documented behavior while preserving valid inputs and supported outputs. Document any tightened invalid-input handling. |
| Stricter validation | Patch or major | Use patch when rejecting input that was already documented as invalid or is unsafe. Rejecting a previously valid, supported workflow is incompatible and requires major, normally after deprecation. |
| Human-readable error or help wording | Patch | Applies when exact prose is not documented as stable. Preserve machine-readable classifications, JSON fields, and exit behavior. |
| Machine-readable errors or command output | Minor or major | Add an optional field or a new error classification with a minor release. Rename, remove, reinterpret, or make a field required only in a major release. Changing documented exit behavior incompatibly is also major. |
| Backward-compatible capability | Minor | Includes new optional commands, arguments, root exports, adapters, provider integrations, or schema fields. Existing callers and persisted data must continue to work. |
| Deprecation of a stable contract | Minor | Announce the replacement and migration window. Removal is a later major release. |
| Removal, rename, or incompatible default | Major | Includes supported CLI or Python APIs, accepted values, runtime requirements, generated-workspace behavior, adapter contracts, and persisted fields. Supply migration support and release notes. |
| Compatible security hardening | Patch | Close the vulnerability without rejecting valid supported use. Disclose only details that are safe to publish. |
| New opt-in security control | Minor | Adds functionality while leaving existing supported workflows available. |
| Incompatible security restriction | Major | A security emergency may shorten the normal deprecation window, but it does not turn a breaking change into a patch. Document mitigation and migration. |
| Add an experimental interface | Minor | Label it explicitly and keep it outside all stable surfaces documented above. |
| Change or remove an experimental interface | Minor | Allowed with release notes only while the interface remains explicitly experimental and outside stable surfaces. Otherwise apply the normal compatibility rules. |
| Compatible dependency update | Patch | Does not drop a supported runtime, alter a stable adapter contract, or require downstream configuration changes. |
| Add optional runtime or Python support | Minor | Expands supported functionality without invalidating current installations. |
| Drop a supported runtime or Python version | Major | Existing supported installations would no longer work. Provide advance notice and an upgrade path where practical. |

A bug label does not automatically make a change a patch. If callers could
reasonably rely on the documented behavior being changed, classify the change
by that compatibility impact. Conversely, an implementation detail does not
become public merely because downstream code can reach it.

An interface is experimental only when all of these are true:

- user-facing documentation and help label it experimental;
- it is not exported from `content_creator.__all__` or a documented subsystem
  façade;
- it is not written into a stable persisted schema or required by generated
  workspaces; and
- it is not part of a supported provider or visual adapter contract.

Feature flags and opt-in settings can make an additive capability minor. They
do not make an incompatible change to an existing default backward compatible.
When classification remains uncertain after checking tests, documentation, and
known downstream workspaces, perform an explicit compatibility review and use
the more conservative version increment.

The release classification also determines mutation-test scope. Patch changes
exercise configured regression-risk modules, minor changes exercise the complete
configured critical-module set, and major changes require reviewer-approved
expansion before merge. Critical persistence, recovery, security, provider, or
publication risk may widen that scope regardless of version increment. See the
[mutation-testing baseline and decision policy](mutation-testing-baseline.md).
