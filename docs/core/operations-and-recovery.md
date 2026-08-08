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
checkpoints. Atomic persistence applies to individual state files, and exclusive
activation locks serialize competing approval commands.

Candidate build/staging and the complete version/receipt/registry promotion are
not yet one transaction. Until
[#73](https://github.com/vadhoob90/Content_Creator_Core/issues/73) is resolved,
serialize candidate-changing commands and approval for each voice or perspective
context. After an overlapping or interrupted promotion, preserve the workspace
for inspection and do not manually delete numeric versions or edit registries.
