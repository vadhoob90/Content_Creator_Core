# Public compatibility contracts

Core is both a command-line application and a versioned dependency used by
author workspaces. Internal refactoring must preserve the observable contracts
below unless a release deliberately changes them with migration support.

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

Sibling implementation paths such as `orchestration_support`,
`diagnostic_support`, `diagnostic_recording`, `voice_build_pipeline`, and the
`voice_ml_*` modules are internal unless a future release documents them as
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
