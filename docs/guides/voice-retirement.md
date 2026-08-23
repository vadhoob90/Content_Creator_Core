# Pause, retire, and restore voices and perspectives

Lifecycle withdrawal changes whether an aggregate may be used for new work. It never
deletes evidence, learning, publications, perspectives, receipts, or historical runs.

| Term | Meaning |
| --- | --- |
| Active | Eligible for new unpinned work |
| Inactive / paused | Reversible temporary withdrawal |
| Reactivated | The unchanged selected version is verified and made eligible again |
| Retired | Preserved but withdrawn from normal future use |
| Restored | Returned through a hash-bound plan and explicit review |
| Superseded | An immutable version was replaced by a later approved version |
| Rejected | One exact candidate hash was reviewed and not approved |
| Deleted | Physical removal; outside the graceful lifecycle |

## Voice preflight and decisions

Run:

```bash
content-creator --workspace . voice retirement-plan <voice-id>
```

The typed plan is built from persisted Core state. It binds registry status, selected
manifest and strategy, default configuration, learning epoch and counts, voice and
perspective candidates, proposals, owned contexts, unfinished runs, publications,
receipts, and associated provider or ML artifacts. Any state change produces a new
`binding_hash`, so stale retirement commands fail closed.

Pause with an actor and reason. A default must be explicitly cleared or replaced:

```bash
content-creator --workspace . voice deactivate <voice-id> \
  --deactivated-by "<author>" --reason "<reason>" --clear-default
content-creator --workspace . voice reactivate <voice-id> \
  --approved-by "<author>"
```

Pause blocks new unpinned runs and learning, preserves candidates and contexts, and
freezes the current learning epoch. Reactivation verifies the same immutable version,
opens a new activation epoch, and writes a receipt without allocating another voice
version.

Retirement additionally blocks revisions, publication of unpublished runs, upgrades,
and candidate activation. Supply the reviewed plan hash and every required exact-hash
candidate, proposal, default, and unfinished-run decision:

```bash
content-creator --workspace . voice retire <voice-id> \
  --retired-by "<author>" --reason "<reason>" \
  --plan-hash sha256:<hash> --clear-default
```

Installed content packs remain available because they are reusable workflows, not
identity. Repository agents and repository-wide learning are unchanged. Owned
perspective contexts become inaccessible beneath the retired voice but are not
silently retired. Explicit context cascade decisions must use their own receipts.

## Perspectives, restoration, and verification

Use the corresponding context commands:

```bash
content-creator perspective retirement-plan --voice <voice-id> --context <context-id>
content-creator perspective deactivate --voice <voice-id> --context <context-id> \
  --deactivated-by "<author>" --reason "<reason>"
content-creator perspective reactivate --voice <voice-id> --context <context-id> \
  --approved-by "<author>"
content-creator perspective retire-context --voice <voice-id> --context <context-id> \
  --retired-by "<author>" --reason "<reason>" --plan-hash sha256:<hash>
```

Perspective entry retirement still stages a candidate context version. Candidate
evidence is preserved, and `reject-candidate` or `abandon-candidate` binds the exact
hash to a human decision.

A retired aggregate cannot use ordinary reactivation. Generate a fresh
`restore-plan` or `restore-context-plan`, review the hash, and supply distinct request
and approval identities to `voice restore` or `perspective restore-context`. Offline
`verify-lifecycle` checks content-addressed receipts and selected manifest hashes.

Existing registry-only inactive state is preserved as legacy state. A reviewed
`voice migrate-lifecycle --migrated-by <actor>` receipt is explicitly labelled as a
migration; Core never invents a historical actor, reason, or approval.
