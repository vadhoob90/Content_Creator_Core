# Architecture and development guardrails

These are the blocking and review guardrails for reusable Core code. Start here
before changing structure; follow the linked specialist policy when a change
affects a public contract, persisted data, operations, or a release.

## Module responsibility and size

- `content_creator.cli` is a compatibility façade and remains at most 100 lines.
- `content_creator.commands.runtime` owns error rendering and compatibility only
  and remains at most 300 lines.
- Every production Python module remains at most 500 physical lines. Treat 400
  lines as an early review signal: check whether contracts, parsing, persistence,
  rendering, or policy have become separate reasons to change.
- A command family owns both parser registration and execution. The top-level
  parser composes families; it does not absorb their domain behavior.
- Compatibility façades may re-export stable names while implementation modules
  own one cohesive responsibility.

Run `python scripts/architecture_report.py --check` locally. CI blocks growth
past these limits. Do not evade the check with generated monoliths, renamed
"legacy" modules, dense formatting, or arbitrary fragments. If a limit cannot
be met safely, document a time-bounded ADR and remediation issue before changing
the guardrail.

## Change workflow

1. Characterise observable behaviour before structural work, or add a focused
   failing test before new behaviour.
2. Move one responsibility at a time and keep focused tests green.
3. Preserve dependency direction: domain and application code do not depend on
   entry points or concrete optional providers.
4. Run the complete local gate before release.
5. Update the changelog, relevant task guide, ADR, and compatibility notes in
   the same change.
6. Release through protected `main`, an immutable version tag, and PyPI; then
   validate every pinned downstream workspace against the published artifact.

## Guardrail map

| Change area | Required guidance |
| --- | --- |
| Design, DRY, YAGNI, TDD | [Development principles](development-principles.md) |
| Formatting, typing, coverage, security, CI, release | [Engineering standards](engineering-standards.md) |
| CLI, Python exports, adapters, generated workspaces | [Public contracts](public-contracts.md) |
| Persisted schemas and deprecation | [Schema compatibility](schema-compatibility.md) |
| Atomicity, diagnostics, recovery, privacy | [Operations and recovery](operations-and-recovery.md) |
| Dependency boundaries | [ADR 0007](../adr/0007-modular-monolith-boundaries.md) |
| Lifecycle and optional capabilities | [ADR 0008](../adr/0008-lifecycle-stages-and-capabilities.md) |
| Schema and operational governance | [ADR 0009](../adr/0009-schema-governance-and-operational-recovery.md) |
| Module responsibility and size | [ADR 0010](../adr/0010-module-responsibility-and-size-guardrails.md) |

## Full local gate

```bash
ruff check .
ruff format --check .
mypy
python scripts/architecture_report.py --check
pytest --cov=content_creator --cov-report=term-missing
content-creator doctor
content-creator eval
git diff --check
```

