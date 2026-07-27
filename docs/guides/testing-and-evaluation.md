# Testing and evaluation

The project separates software correctness from output assessment.

`pytest` covers routing, candidate selection, quality calculation, mechanical
validation, both adapter request shapes, all six primary routes, supplied
research, research pause/resume and rejection, failure persistence, bounded
revision, publication safety, and learning status.

`content-creator eval` is the offline harness. It executes the committed route
matrix with deterministic responses for both provider contracts. This checks
route conformance and artifact production without API keys, cost, or model
drift. Results go to `.eval-results/`.

`content-creator eval --mode live --providers <provider>` runs two paid
flagship cases:

- A simple no-research post
- A deep article about 70 years of human-machine interaction

The live report records status, quality score, revisions, latency, models, and
token use. It does not publish content. Live evaluation is manual in GitHub
Actions and protected by an environment. Offline CI is path-filtered, so
changes only under `content/*/drafting/` or
`profiles/*/learnings/` do not invoke the harness.

Replay proves system behavior, not prose quality. Human assessment is captured
at publication through the approval event and optional `--feedback`.
