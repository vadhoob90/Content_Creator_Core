# Testing and evaluation

The project separates software correctness from output assessment.

Tests prefer observable contracts over private call shape. Focused unit tests
cover deterministic policy and transformation functions; integration tests
cross persistence, lifecycle, and adapter boundaries; the offline replay matrix
proves representative routes without network access. Structural tests are used
only for accepted architecture rules or characterized compatibility façades.

`FakeProvider` is the standard model boundary in tests. Give it role-keyed,
schema-valid responses and pass it through `ProviderRegistry`; do not patch
vendor SDK internals or make network calls. A fake demonstrates that Core sends
the normalized provider contract and handles the returned contract—it does not
claim that a live vendor model will produce equivalent prose.

`pytest` covers routing, pack inheritance and isolation, candidate selection,
quality calculation, mechanical validation, source ingestion, attribution,
voice building and activation, version resolution, phrase overlap, API and
native adapter request shapes, all six LinkedIn routes, the direct general-text
route, supplied
research, research pause/resume and rejection, failure persistence, bounded
revision, publication safety, documentation commands, and learning status.
Regression coverage also verifies typed prior-issue dispositions, fail-safe
legacy status normalisation, lifecycle-consistent active voice prompts, and
supplied-research rejection before normal run persistence. Idempotency tests
cover equivalent retries, conflicting reuse, concurrent claims, active-state
lookup, terminal publication safety, and intentional revision lineage.

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

The required pull-request gate deliberately stops at deterministic provider
contracts. It proves routing, context composition, persistence, approval, and
failure handling without credentials or network access. Live-provider workflows
remain bounded, credentialed release evidence: they can reveal model-specific
instruction-following or service behaviour, but their cost and nondeterminism make
them unsuitable as required change-control checks. A live-provider result never
replaces the offline route matrix or deterministic safety tests.

Packaged-skill routing has a separate deterministic gate:

```bash
python scripts/skill_routing_report.py --check
```

It validates positive, negative, and near-miss cases, both packaged skill
copies, frontmatter, instruction budgets, duplicate or contradictory prompts,
and report scoring. Host/model observations are supplied explicitly with
`--observations <json>` and remain advisory; the report records precision,
recall, false positives, false negatives, and individual failed cases.

Use the repeated-trial runner for a live host or model check:

```bash
python scripts/skill_routing_live.py \
  --host codex-desktop \
  --model-version gpt-example-2026-08 \
  --trials 3 \
  -- path/to/reviewed-routing-adapter --adapter-option
```

The provider-neutral adapter receives a JSON request on standard input for each
case and trial. It returns exactly one JSON object such as
`{"activated": true, "skill": "content-creator"}` or
`{"activated": false}`. Core invokes the adapter without a shell, requires a
positive odd trial count, computes trial-level precision and recall, records
strict case majorities and every failed prompt, and stores evidence below
`reports/skill-routing/<host>/<model-version>/`.

The manually dispatched `Advisory live skill routing` workflow runs the same
protocol. Configure the reviewed adapter command as a JSON string array in the
repository variable `SKILL_ROUTING_ADAPTER_JSON`, for example
`["python", "scripts/local_host_adapter.py"]`. The workflow records the exact
host and model version and uploads the result tree. Run it before a release,
after material skill-description changes, or after a significant host/model
update. It is advisory, credential and cost handling belong to the adapter, and
it is intentionally neither scheduled nor part of ordinary pull-request CI.

Replay proves system behavior, not prose quality. Human assessment is captured
at publication through the approval event and optional `--feedback`.
