# Core engineering standards

These standards apply to reusable code and packaged resources in Content
Creator Core. CI is authoritative; local hooks are optional conveniences.
Start with the [architecture and development guardrails](architecture-guardrails.md)
for the consolidated map of these standards and the public-contract, schema,
operations, dependency, and release controls that accompany them.

## Supported Python

`pyproject.toml` defines the supported Python range. CI tests every declared
minor version: Python 3.11 through 3.14. Dropping a supported version is a
compatibility change that must be documented and released deliberately.

Python 3.9 is end-of-life, and the security-fixed pytest baseline requires
Python 3.10 or newer. Core therefore uses Python 3.11 as its minimum rather
than starting a new support window on Python 3.10 shortly before its end of
life.

## Code style and static checks

- Ruff is the single formatter and linter.
- The configured line length is 100 characters.
- CI runs `ruff check .` and `ruff format --check .`.
- Enabled lint families cover pycodestyle errors, Pyflakes, import ordering,
  pyupgrade, flake8-bugbear, unused arguments, silent exception suppression,
  McCabe complexity, and selected Pylint design limits. Intentionally unused
  parameters use an underscore prefix; do not delete a parameter merely to
  satisfy linting. Complexity has an ideal of 10 and a hard maximum of 15; the
  configured hard limits also cover branches, statements, parameters, and nesting.
- Mypy checks the complete production package and prohibits untyped function
  definitions. Do not exclude a module or weaken a rule to avoid a local fix.
- `python scripts/architecture_report.py --check` enforces accepted modular
  boundaries: a small CLI and runtime façade, a 500 implementation-line maximum
  for production modules, optional capabilities outside the orchestrator,
  explicit application stages, shared immutable-artifact mechanics, and the ban
  on deleting function parameters. It also blocks every internal import edge
  that participates in a cycle, including imports placed inside functions. The
  same required check blocks reverse dependencies without cycles: domain and
  storage remain inward, entry points remain terminal, provider adapters cannot
  drive workflows, application code cannot import concrete vendor adapters,
  inner modules cannot print to a terminal, and commands cannot access mutable
  persistence implementation details.
  Physical size remains visible in the report. New rules need a documented green
  baseline before becoming blocking.
- `python scripts/readability_report.py --check` scans every Python module in
  `src/`, `scripts/`, and `tests`: 500 module implementation lines, 80 function
  implementation lines, and 7 parameters are hard limits. It reports physical
  sizes plus the 300-line module and 40-line function ideals without failing the
  build.
- Exact generic module and class names (`data`, `item`, `manager`, `utils`) are
  blocked. Review local names for the same ambiguity; names should reveal the
  domain concept without requiring a comment.
- Every production module, class, function, and method uses Google Style,
  including private, nested, asynchronous, constructor, and special methods.
  Summaries are single active-imperative sentences. Callable `Args`, `Returns`,
  and `Raises` sections must agree with the signature, literal defaults, annotated
  return, and statically named explicit exceptions. `None` returns are documented.
- CI combines Ruff's Google pydocstyle rules with
  `python scripts/documentation_report.py --check`. The dependency-free report
  enforces repository requirements Ruff does not cover: explicit argument types,
  literal defaults, all returns, exception agreement, imperative summaries, and
  context for callables above 40 implementation lines.
- Tests and maintenance scripts are excluded from the blocking docstring scope.
  Reviewers still own prose accuracy and reject placeholders, name restatements,
  unsupported guarantees, and descriptions that disagree with side effects.
  Comments should explain constraints or intent rather than restating code.

## Tests and evaluation

- Behaviour changes require regression tests.
- The full test suite must pass on every declared Python version.
- Overall statement coverage may not fall below 88%, and branch coverage may
  not fall below the measured 80% baseline. Coverage.py measures branches for
  every coverage run. `scripts/coverage_report.py` enforces the thresholds
  independently so branch adoption cannot weaken the statement guarantee.
  Coverage is a guardrail, not a substitute for meaningful assertions.
- Branch coverage proves that both outcomes of individual control-flow
  decisions execute somewhere in the suite. It does not prove that every
  meaningful end-to-end combination executes; the deterministic route matrix
  remains a separate required evaluation.
- Offline evaluation must remain deterministic and pass without provider
  credentials or external network access.
- Provider and ingestion evaluations remain manually dispatched, bounded, and
  isolated in their GitHub environments.
- Generator changes must create a temporary workspace, run its smoke tests,
  and prove that repeated generation preserves repository-owned files.
- Persisted-contract changes require a versioned historical fixture, a pure
  migration test, a deterministic schema export, and compatibility notes.
- Operational changes require fault-oriented tests for interrupted writes,
  corrupt state, lock ownership, and privacy-safe diagnostic output as relevant.
- Mutation execution is initially advisory, scheduled, and targeted on pull
  requests by semantic release impact and critical-path risk. The locked `mutmut`
  configuration targets quality-gate and versioned-artifact decisions first.
  Survivor-policy validation is deterministic: missing, invalid, or expired
  decisions fail. A score alone must not trigger weak assertions or production-
  code distortion. The blocking decision and expansion criteria are recorded in
  the [mutation-testing baseline](mutation-testing-baseline.md).
- Exception handlers must re-raise, return an explicit fallback, record a bounded
  warning or domain event, or otherwise make the degraded outcome observable.
  Bare silent `pass` and `continue` handlers are prohibited. Best-effort
  diagnostics must never mask the original failure or claim an artifact exists
  when persistence failed.

## Security and dependencies

- Dependencies must use bounded compatible ranges and the lockfile is
  committed. CI installs from `uv.lock` in frozen mode and fails if dependency
  declarations and the lockfile disagree.
- Dependency review blocks pull requests that introduce known vulnerabilities
  of moderate severity or higher.
- `pip-audit` checks the complete locked dependency environment on Python 3.11
  and 3.14 for pull requests, pushes to `main`, and a weekly schedule.
- CodeQL scans Python source on pull requests, `main`, and a weekly schedule.
- Dependabot checks Python and GitHub Actions dependencies weekly.
- GitHub Actions must be pinned to full commit SHAs, with the release tag kept
  in a comment for maintainability.
- Secret scanning and push protection must be enabled in repository settings.
- Secrets, private voice sources, unpublished content, and raw provider
  responses must not appear in commits, ordinary logs, or CI artifacts.
- Vulnerability exceptions require a documented identifier, rationale, owner,
  expiry date, and follow-up issue. Silent ignores are prohibited.

## Pull requests and releases

- `main` is protected. Changes arrive through focused pull requests and the
  required CI check must pass; force pushes and branch deletion are disabled.
- Unrelated editorial state or generated run artifacts must not be mixed into
  Core changes.
- Release tags are immutable, must match the package version, and must point to
  a commit contained in protected `main`.
- The release workflow builds and validates both distributions, tests the
  wheel in a clean environment, publishes through PyPI Trusted Publishing,
  and records checksums, a manifest, and a CycloneDX SBOM in the GitHub
  release. The distributions and release evidence receive GitHub artifact
  attestations, including an SBOM-linked attestation.
- Release build tools are installed from `uv.lock`, and builds disable isolated
  dependency resolution. CI builds each distribution twice with a commit-based
  `SOURCE_DATE_EPOCH` and requires byte-identical artifacts, so an unreviewed
  build-tool release or wall-clock timestamp cannot alter the artifacts
  produced by an existing source commit.

## Local validation

Before proposing a Core change, run:

```bash
ruff check .
ruff format --check .
mypy
python scripts/architecture_report.py --check
python scripts/readability_report.py --check
python scripts/documentation_report.py --check
pytest --cov=content_creator --cov-report=term-missing --cov-report=json:.coverage-report.json
python scripts/coverage_report.py .coverage-report.json --check
content-creator eval
mutmut run
git diff --check
```

Run `python -m pip_audit --local` after installing all relevant optional
dependencies when changing dependency declarations or preparing a release.
