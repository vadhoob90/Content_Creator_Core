# ADR 0013: Google Style code contracts

- Status: Accepted
- Date: 2026-08-05

## Context

Core reached complete production docstring presence, but many descriptions were
name-derived summaries that did not explain inputs, outputs, failure behavior,
side effects, or domain policy. A coverage percentage could therefore remain
green while the documentation gave maintainers little more information than the
signature itself.

Type annotations are authoritative for static tooling, but they do not explain
what a value represents, why a default is safe, what persisted state changes, or
which domain error a caller should handle. Core needs one reviewable convention
and deterministic enforcement without adding a runtime documentation framework.

## Decision

Every definition under `src/content_creator` uses a Google Style docstring:

- the first line is one punctuated sentence beginning with an active imperative
  verb;
- every explicit callable parameter except `self` and `cls` appears in `Args`
  with its type, meaning, and literal default when present;
- every callable has `Returns`, including constructors and side-effect-only
  functions that return `None`;
- every statically named exception raised directly by the callable appears in
  `Raises`; and
- callables above the 40 implementation-line review threshold include a context
  paragraph describing their policy, lifecycle, orchestration, or side effects.

The annotated signature remains the source of truth. Documentation types and
defaults must agree with it rather than creating a second, divergent contract.
Descriptions explain domain meaning and observable behavior; they do not promise
validation, ordering, atomicity, retries, or persistence that the implementation
does not provide.

Ruff enables compatible pydocstyle rules under the Google convention for
production code. The dependency-free AST validator in
`scripts/documentation_contracts.py` and `scripts/documentation_report.py`
enforces signature agreement, explicit types and defaults, all returns, explicit
raises, imperative summaries, and complex-callable context. CI runs both checks.

Tests and maintenance scripts are excluded from the blocking docstring scope.
Descriptive test names often state behavior more clearly than repetitive prose,
and short maintenance scripts do not form the shipped production contract.

## Review boundary

Automation validates structure and facts available from the syntax tree. Human
review remains responsible for clarity, domain accuracy, useful detail, and
agreement with indirect side effects or exceptions propagated by collaborators.
Review rejects placeholders, mechanical name restatements, and unsupported
guarantees even when the structural check passes.

## Consequences

Maintainers can understand a callable's purpose, inputs, output, direct failure
modes, and important workflow context at its definition. Documentation changes
increase physical file size but do not consume the separately reported
implementation-line budget established by ADR 0010 and ADR 0011.

Adding a parameter, changing a default or return annotation, or introducing a
direct exception now requires the docstring contract to change in the same pull
request. Core accepts this maintenance cost in exchange for keeping shipped code
and its human-facing contract synchronized.
