# Troubleshooting and recovery

Start with:

```bash
content-creator doctor
content-creator voice status <voice-id>
content-creator status <run-id>
```

## Source or build failure

Correct the URL or document, add sources if necessary, then rebuild. A failed
build does not activate or replace an existing version.

```bash
content-creator voice add-sources <voice-id> --sources corrected-urls.txt
content-creator voice rebuild <voice-id>
```

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
```

Persisted run artifacts remain available for diagnosis. Repeat only the
documented deterministic recovery command; do not edit state or registries by
hand.
