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
workflow runs the same configuration and uploads `mutmut-cicd-stats.json`
without joining the required-check aggregate.

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

## Next decision

Review surviving boundary, comparison, and metadata mutations first. Add tests
only when the mutant represents an observable contract. Expand the module set
after runtime and survivor-review effort are known; do not establish a blocking
threshold until waiver handling and score stability have been demonstrated.
