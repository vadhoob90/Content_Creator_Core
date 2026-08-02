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
  pyupgrade, and flake8-bugbear.
- Mypy checks the complete production package and prohibits untyped function
  definitions. Do not exclude a module or weaken a rule to avoid a local fix.
- `python scripts/architecture_report.py --check` enforces accepted modular
  boundaries: a small CLI and runtime façade, a 500-line maximum for production
  modules, optional capabilities outside the orchestrator, explicit application
  stages, and shared immutable-artifact mechanics. New rules need a documented
  green baseline before becoming blocking.
- Public APIs need useful type annotations and docstrings. Comments should
  explain constraints or intent rather than restating code.

## Tests and evaluation

- Behaviour changes require regression tests.
- The full test suite must pass on every declared Python version.
- Overall statement coverage may not fall below 88%. Coverage is a guardrail,
  not a substitute for meaningful assertions; branch coverage can be adopted
  later with a measured baseline and ratchet.
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

## Security and dependencies

- Dependencies must use bounded compatible ranges and the lockfile is
  committed.
- Dependency review blocks pull requests that introduce known vulnerabilities
  of moderate severity or higher.
- `pip-audit` checks the installed dependency environment in CI.
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
- Release tags are immutable and must match the package version.
- The release workflow builds and validates both distributions, tests the
  wheel in a clean environment, publishes through PyPI Trusted Publishing,
  and records checksums and a manifest in the GitHub release.
- A future supply-chain hardening increment may add signed provenance and an
  SBOM; these do not replace distribution tests or dependency review.

## Local validation

Before proposing a Core change, run:

```bash
ruff check .
ruff format --check .
mypy
python scripts/architecture_report.py --check
pytest --cov=content_creator --cov-report=term-missing
content-creator eval
git diff --check
```

Run `python -m pip_audit --local` after installing all relevant optional
dependencies when changing dependency declarations or preparing a release.
