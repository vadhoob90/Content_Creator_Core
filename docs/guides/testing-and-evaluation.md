# Testing and evaluation

The project separates software correctness from output assessment.

`pytest` covers routing, pack inheritance and isolation, candidate selection,
quality calculation, mechanical validation, source ingestion, attribution,
voice building and activation, version resolution, phrase overlap, API and
native adapter request shapes, all six LinkedIn routes, the direct general-text
route, supplied
research, research pause/resume and rejection, failure persistence, bounded
revision, publication safety, documentation commands, and learning status.
Regression coverage also verifies typed prior-issue dispositions, fail-safe
legacy status normalisation, lifecycle-consistent active voice prompts, and
supplied-research rejection before normal run persistence.

`content-creator eval` is the offline harness. It executes the committed route
matrix with deterministic responses for the selected provider contracts. This includes
six LinkedIn cases plus direct general text and checks
route conformance and artifact production without API keys, cost, or model
drift. Results go to `.eval-results/`.

`content-creator eval --mode live --providers <provider>` runs two live
flagship cases. API modes incur usage-based cost; native modes consume the
corresponding product subscription allowance:

- A simple no-research post
- A deep article about 70 years of human-machine interaction

The live report records status, quality score, revisions, latency, models, and
token use. It does not publish content. Live evaluation is manual in GitHub
Actions and protected by an environment. Offline CI is path-filtered, so
ordinary content changes and publication-triggered learning updates do not
invoke the expensive harness. Documentation has its own offline command and
link checks.

Replay proves system behavior, not prose quality. Human assessment is captured
at publication through the approval event and optional `--feedback`.
