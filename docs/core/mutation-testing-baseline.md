# Mutation-testing baseline

This is the initial advisory baseline for issue #93. It is evidence for test
design and hotspot prioritisation, not a release gate.

## Reproduce

```bash
uv sync --frozen --extra dev
uv run --frozen --extra dev mutmut run
uv run --frozen --extra dev mutmut export-cicd-stats
```

The locked configuration mutates covered lines in:

- `content_creator.quality`
- `content_creator.versioned_artifacts`

It selects the focused quality and versioned-artifact tests. The scheduled
workflow runs the same configuration and uploads `mutmut-cicd-stats.json`.
Pull requests also run `scripts/mutation_policy.py`: the policy validates the
survivor-decision file and selects only the configured mutants justified by the
change's semantic impact and risk.

## Initial result — 2026-08-09

| Result | Count |
| --- | ---: |
| Total mutants | 208 |
| Killed | 159 |
| Survived | 49 |
| No tests | 0 |
| Timeout | 0 |
| Skipped | 0 |
| Mutation score | 76.44% |

The absence of untested mutants shows that the selected code is executed, while
the 49 survivors identify assertions and equivalence decisions that need review.
Survivors are not automatically defects. Each must be classified as a meaningful
behavioural gap, an equivalent mutation, or a documented tool limitation before
tests or production code change.

## Pull-request policy

Apply exactly one `release:patch`, `release:minor`, or `release:major` label when
a pull request has that semantic impact. With no release label, the policy still
selects a directly changed configured critical module.

| Change | Mutation expectation |
| --- | --- |
| Documentation or tooling only | No mutation run unless a critical module changed |
| Patch in production code | Complete configured regression-risk set |
| Minor public capability | Complete configured critical-module set |
| Major compatibility change | Complete configured critical-module set, plus reviewer-approved expansion before merge |

Targeted mutation execution is advisory while runtime and survivor noise settle.
The policy and waiver validation are deterministic and may be required. A future
blocking mutation threshold requires two consecutive comparable baselines, no
expired decisions, and a maintainer decision recorded here; until then, ordinary
regression, coverage, and evaluation gates remain blocking.

## Survivor decisions

Record accepted survivors in `.github/mutation-waivers.yaml`. Every entry must
name the exact mutant, classify it as `test-gap`, `equivalent`, or
`tool-limitation`, explain the observable contract, assign an owner and expiry,
and link a follow-up. Expired, incomplete, or silently ignored decisions fail the
policy step. A `test-gap` decision is temporary: add a meaningful assertion and
remove the entry once the mutant is killed.

## Representative regression proof

The issue #73 atomic-promotion regression tests kill the generated
`content_creator.versioned_artifacts.x_publish_version_snapshot__mutmut_12`
mutation, which corrupts the hidden promotion-staging path. They also kill the
cleanup mutation `...__mutmut_22`. This demonstrates that a real interrupted
publication fault, not only a score threshold, is detected by the focused suite.

## Expansion decision

Review surviving boundary, comparison, and metadata mutations first. Add tests
only when the mutant represents an observable contract. Expand the module set
when a release changes another high-risk domain and its focused test selection is
fast and stable; record the new baseline before considering it for blocking use.
