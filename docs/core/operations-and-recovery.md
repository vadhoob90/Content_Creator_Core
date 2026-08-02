# Operations and recovery

Core provides offline diagnostics for local failures without copying author
content into support output.

```bash
content-creator operations recovery-report
content-creator operations support-bundle <run-id>
```

The recovery report detects malformed run state, distinguishes live activation
locks from stale or unreadable locks, and gives non-destructive recovery
advice. It never removes a lock automatically: inspect the owning process
before any manual cleanup.

Support bundles are written below `.content-creator/support/`. They include the
Core version, stable failure classification, run status, and artifact names,
sizes, and SHA-256 hashes. They exclude artifact bodies, prompts, drafts,
provider responses, credentials, environment variables, and local source
content. Treat even metadata as private until the author reviews it.

Stable failure codes are:

- `provider_failure`
- `corrupt_state`
- `stale_lock`
- `validation_failure`
- `unknown`

Recovery must remain fail-safe and reversible. Restore corrupt state from a
reviewed backup or version control; do not invent state or bypass approval
checkpoints. Atomic persistence and exclusive activation-lock behavior have
fault-oriented regression tests in the offline suite.
