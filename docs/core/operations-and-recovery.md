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

Candidate replacement and activation share a per-voice or per-perspective lock.
Activation prepares manifests, receipts, and locks under a hidden directory,
verifies the complete snapshot, and exposes the numeric version with one atomic
rename before updating the registry. A normal persistence failure removes the new
snapshot and preserves the candidate and prior active registry entry. If the
process stops after the rename but before the registry write, repeating approval
verifies and reconnects that same version instead of allocating another one.
