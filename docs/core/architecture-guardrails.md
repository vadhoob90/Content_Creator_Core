# Architecture and development guardrails

These are the blocking and review guardrails for reusable Core code. Start here
before changing structure; follow the linked specialist policy when a change
affects a public contract, persisted data, operations, or a release.

The current seven-module responsibility and dependency decisions are recorded
in the [hotspot cohesion review](hotspot-cohesion-review.md). Mutation evidence
used to prioritise decision paths is recorded in the
[mutation-testing baseline](mutation-testing-baseline.md).

## Module responsibility and size

- `content_creator.cli` is a compatibility façade and remains at most 100 lines.
- `content_creator.commands.runtime` owns error rendering and compatibility only
  and remains at most 300 lines.
- Every production Python module remains at most 500 implementation lines.
  Docstring lines are reported as part of physical size but do not consume the
  implementation budget. Treat 400 implementation lines as an early review
  signal: check whether contracts, parsing, persistence, rendering, or policy
  have become separate reasons to change.
- A command family owns both parser registration and execution. The top-level
  parser composes families; it does not absorb their domain behavior.
- Compatibility façades may re-export stable names while implementation modules
  own one cohesive responsibility.
- Across `src/`, `scripts/`, and `tests/`, 300 implementation lines is the
  preferred target, 301–400 requires a cohesion review, and 500 is the hard
  limit. Reports retain physical counts so documentation growth remains visible.

Size is a constraint, not a definition of cohesion. Every extraction names an
independently understandable responsibility and reason to change. A package is
appropriate when several modules form one named subsystem and each contained
module remains cohesive; moving flat files into a directory is not sufficient.

Inheritance represents genuine substitutability and must not be used merely to
distribute one implementation across files. Prefer direct functions or
composition when behavior is assembled. Do not introduce generic `base`,
`support`, `common`, `helpers`, or `utils` layers as countersinks for code that
does not have an independent responsibility.

Importer count, shared prefixes, small modules, and cross-file inheritance are
review signals rather than violations. They remain advisory unless a later ADR
establishes an objective rule with a low false-positive rate and clear
remediation.

`scripts/architecture_report.py` records single-importer modules and cross-file
inheritance under `advisories`. Review changes to those lists during structural
work; the report deliberately does not turn either signal into a blocking rule.

## Function readability and control flow

- Prefer functions of at most 40 implementation lines. Lines 41–80 are an
  explicit review signal; more than 80 is blocked. A function's own docstring
  is reported in its physical size but excluded from this implementation limit.
- Prefer cyclomatic complexity at most 10. Complexity 11–15 requires a focused
  review; more than 15 is blocked.
- Hard limits are 12 branches, 50 statements, 7 parameters (excluding
  `self`/`cls` in the readability report), and 4 nested blocks.
- Dispatch belongs in a typed route table or a cohesive sub-handler. A router
  coordinates; it does not contain the work performed by every route.
- Extract by reason to change—validation, persistence, rendering, policy, or
  adapter interaction—not merely to satisfy a counter.
- Prefix intentionally unused parameters with an underscore. Deleting parameters
  inside the function is prohibited because it hides the unused contract from
  static analysis; `scripts/architecture_report.py --check` enforces this rule.
- Recoverable exception paths remain observable through a bounded warning,
  domain event, counter, or explicit fallback result. Rollback-and-reraise and
  best-effort boundaries preserve the original error rather than silently
  discarding it.

`scripts/readability_report.py --check` enforces implementation module/function
and signature limits across production code, maintenance scripts, and tests. Ruff
enforces complexity, branches, statements, parameters, and nesting. Ideal
thresholds remain visible warnings and review prompts so they guide creation
without forcing meaningless fragments.

## Naming and documentation

- Names state domain intent. Exact generic module and class names `data`,
  `item`, `manager`, and `utils` are prohibited.
- Generic local names are a review smell: replace them when the domain concept
  is known; retain a conventional short name only when its small scope makes
  the meaning unambiguous.
- Prefer descriptive functions and variables to explanatory comments. Comments
  record why a surprising business or safety constraint exists, never narrate
  what plainly written code does.
- Every production module, class, function, and method—including private,
  nested, asynchronous, and special methods—uses Google Style documentation.
  Summaries begin with an active imperative verb. Every callable documents all
  explicit parameters with types and literal defaults, its return type and
  meaning (including `None`), and every statically named explicit exception.
- Callables above the 40 implementation-line review threshold include a context
  paragraph explaining policy, side effects, lifecycle, or orchestration. Short
  callables add context when the contract is otherwise non-obvious.
- `python scripts/documentation_report.py --check` validates presence, section
  order, signature agreement, defaults, returns, explicit raises, and required
  context. Ruff enforces compatible Google pydocstyle rules. Human review remains
  responsible for technical accuracy and must reject restated names, placeholders,
  and unsupported guarantees.
- Tests and maintenance scripts remain outside the blocking scope because
  descriptive test names and short task-oriented scripts are often clearer than
  compulsory prose.

## Dependency direction and import cycles

- The internal `content_creator` module graph remains acyclic. A function-local
  import is still a dependency and must not be used to conceal a cycle.
- Dependencies point inward: entry points invoke application workflows, workflows
  use domain contracts and declared adapter boundaries, and inner code never knows
  which external interface invoked it.
- `content_creator.domain` has no internal package dependencies. Low-level
  `content_creator.storage` depends only on domain contracts; it does not import
  application workflows, manifests, packs, providers, or entry points. Higher-level
  capabilities may depend on storage, but storage never reaches back into them.
- No production module outside `content_creator.cli` and
  `content_creator.commands.*` imports those entry points. Provider adapters do not
  import commands or orchestration, and application modules use the provider package
  boundary rather than concrete vendor adapter modules.
- Inner production modules return structured results or emit narrow callbacks. Direct
  terminal output belongs to the CLI and command layer. Command handlers parse,
  invoke, and render; they do not construct mutable run stores, call private storage
  writers, or reach through `orchestrator.store`.
- Cross-cutting save behavior is composed at an application boundary through a
  narrow callback or existing service contract. It is not activated by importing
  the higher-level feature from the persistence implementation.
- `scripts/architecture_report.py --check` rejects every import cycle and every
  accepted boundary violation independently. Its failure names the boundary,
  source, target, and import line. A violation is fixed by restoring dependency
  direction, not by moving an import inside a function or suppressing CodeQL.

These rules apply even when Python's import cache makes the current execution
order appear safe. Import-order-dependent code is not an accepted runtime
contract.

## Structural-change review

Before moving code, classify affected import paths as permanent façades,
temporary migration shims, or internal implementation. Temporary shims need an
explicit retention decision and are not presented as canonical architecture.

Each structural pull request states:

- the demonstrated reading or maintenance problem;
- why every new module exists independently;
- which old structure is removed;
- whether the representative workflow is easier to trace; and
- how public imports, persisted formats, and generated output remain stable.

New protocols, factories, registries, and reusable abstractions require current
consumers. Avoid forwarding layers that increase the normal call path without
owning state, policy, or a distinct boundary.

Run `python scripts/architecture_report.py --check` locally. CI blocks boundary
violations and growth past these limits. Do not evade the check with generated monoliths, renamed
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
| Function readability, complexity, and naming | [ADR 0011](../adr/0011-readable-components-and-control-flow.md) |
| Concept cohesion and package promotion | [ADR 0012](../adr/0012-concept-cohesion-and-package-promotion.md) |
| Google Style code contracts | [ADR 0013](../adr/0013-google-style-code-contracts.md) |
| Publication packages and visual scope | [ADR 0014](../adr/0014-publication-packages-and-visual-scope.md) |
| Aggregate withdrawal and restoration | [ADR 0015](../adr/0015-graceful-aggregate-retirement.md) |

## Full local gate

```bash
ruff check .
ruff format --check .
mypy
python scripts/architecture_report.py --check
python scripts/readability_report.py --check
python scripts/documentation_report.py --check
pytest --cov=content_creator --cov-report=term-missing --cov-report=json:.coverage-report.json
python scripts/coverage_report.py .coverage-report.json --check
content-creator doctor
content-creator eval
git diff --check
```
