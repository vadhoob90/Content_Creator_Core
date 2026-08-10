# Troubleshooting and recovery

Start with:

```bash
content-creator doctor
content-creator voice status <voice-id>
content-creator status <run-id>
```

## Source or build failure

Correct the URL or document, add sources if necessary, then rebuild. A failed
build does not activate or replace an existing version, and it leaves the
previous valid candidate unchanged. When a voice is active, the routine rebuild
preserves approved guidance by default.

```bash
content-creator voice add-sources <voice-id> --sources corrected-urls.txt
content-creator voice rebuild <voice-id>
```

Use `--full-regenerate` only for an intentional full replacement, then inspect
`content-creator voice diff <voice-id>` before approval.

## Approval overlaps candidate staging

Do not run voice build or rebuild concurrently with voice approval. For a
perspective context, do not create or stage a candidate, stage a proposal, or
retire an entry while approval is running. Current activation locks serialize
approvals, but they do not yet serialize candidate replacement with the full
multi-file promotion.

If commands overlap or approval is interrupted, stop further lifecycle writes
and preserve the workspace for inspection. Do not delete a numeric version
directory or edit a registry manually. Track recovery against
[#73](https://github.com/vadhoob90/Content_Creator_Core/issues/73).

## Candidate does not pass evaluation

Inspect `profiles/<voice-id>/candidate/evaluation-report.json` and
`corpus-report.json`. Add representative, directly authored material. Editorial
evaluation can be overridden only with an explicit reason; authorisation,
schema and provenance failures cannot.

## Deep research is paused

Inspect `runs/<run-id>/research.json`, then run one of:

```bash
content-creator approve-research <run-id>
content-creator reject-research <run-id> --notes "Reason"
```

## Publication name already exists

Choose a new `--filename`. The repository never silently overwrites published
content.

## Provider failure

Verify the credential and configured adapter:

```bash
content-creator provider verify openai
content-creator provider verify anthropic
content-creator provider verify bedrock
```

For Bedrock, confirm that `AWS_REGION` is set and that the AWS SDK can resolve
credentials from `AWS_PROFILE`, environment credentials, workload identity,
container credentials, or `AWS_BEARER_TOKEN_BEDROCK`. A live-search route is not
supported by Bedrock; choose no research or provide an approved research brief.

Persisted run artifacts remain available for diagnosis. Repeat only the
documented deterministic recovery command; do not edit state or registries by
hand.
