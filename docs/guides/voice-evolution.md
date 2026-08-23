# Evolve an existing voice

A voice upgrade is a reviewed transition from one immutable active voice version
to the next. It is different from upgrading the Core dependency and different
from adding runtime learning.

The active version remains usable and unchanged until deterministic approval.
Core persists the plan, evidence sets, learning dispositions, semantic diff,
evaluations, and approval or rejection receipt; chat memory is never lifecycle
state.

## Choose the operation

| Need | Operation |
|---|---|
| Adopt a newer Core release | `workspace upgrade --to <tag>` |
| Apply feedback as a runtime overlay | `learn <run-id>` |
| Evolve voice from new evidence and reviewed learning | `voice upgrade-plan`, then `voice upgrade` |
| Reassess every authorised source while preserving the baseline | `voice upgrade-plan --mode full-corpus` |
| Discard baseline precedence | `voice rebuild --full-regenerate` |

## Version 1 strategy

Version 1 records one of two non-equivalent strategies:

- `starter-neutral` is a neutral writing policy with no author voice evidence;
- `source-derived` is built from an authorised, attributed author corpus.

Replacing a starter with the first source-derived voice is recorded as
`starter-neutral-to-source-derived` in the candidate manifest and approval
receipt. Starter prose is never treated as corpus evidence.

## Default incremental workflow

Add authorised material to the voice work order, then plan:

```bash
content-creator --workspace . voice add-sources <voice-id> \
  --documents "/path/to/new-writing"
content-creator --workspace . voice upgrade-plan <voice-id> \
  --mode incremental \
  --offline-analysis
```

Planning inventories:

- the active version, candidate hash, strategy, and evidence cutoff;
- the complete represented evidence baseline;
- currently authorised sources and reviewed local publications;
- the canonical content-hash set difference;
- the exact prior-version learning epoch and active records;
- duplicate content already represented;
- provider and historical-corpus sharing implications; and
- exact build, diff, and approval commands.

Publication dates are display information, not delta authority. A backdated but
previously unrepresented article is new evidence. A later-dated duplicate is
not. Edited content becomes new evidence when its reviewed normalized content
hash changes.

Incremental analysis reads only evidence in that delta. It deterministically
combines new per-source measurements with persisted baseline measurements and
does not retrieve or transmit historical baseline corpus text.

## Review learning dispositions

When active learning exists, planning creates
`profiles/<voice-id>/upgrade/learning-selection.template.json`. Copy it to
`learning-selection.json`, identify the reviewer, and decide every record.

Supported classifications are:

- `voice-profile`, `voice-constraint`, and `critic/rubric` for reviewed
  linguistic guidance;
- `repository-agent-policy` and `remain-learning` for non-profile policy;
- `perspective`, `research-only`, and `visual-preference` for separate
  lifecycles; and
- `reject/obsolete/conflicting` for excluded records.

Supported dispositions include `incorporate`, `carry-forward`, specialist
routes, `leave-prior-version`, and `reject-retire`. Core proposes
`remain-learning` and `carry-forward` conservatively; it never promotes a record
merely because the record is active. Researcher learning cannot enter linguistic
voice, and visual or perspective classifications must use their separate route.

Build the exact reviewed selection:

```bash
content-creator --workspace . voice upgrade <voice-id> \
  --mode incremental \
  --learning-selection profiles/<voice-id>/upgrade/learning-selection.json \
  --idempotency-key <stable-equivalent-build-key>
```

The build verifies every active component hash, evidence-set binding, learning
epoch hash, mode, and disposition. A changed input requires a new plan and key.
A failed build leaves the active voice and previous valid candidate unchanged.

## Full-corpus reanalysis

Use this mode when attribution or historical evidence changed, the analysis
framework materially changed, or the author deliberately wants all evidence
reassessed:

```bash
content-creator --workspace . voice upgrade-plan <voice-id> \
  --mode full-corpus \
  --provider codex-native
content-creator --workspace . voice upgrade <voice-id> \
  --mode full-corpus \
  --approve-provider-sharing \
  --learning-selection profiles/<voice-id>/upgrade/learning-selection.json
```

The plan discloses the provider, execution mode, source and learning counts,
and whether historical private corpus text will be transmitted. Native
subscription execution never silently falls back to API-key billing.
Full-corpus mode still preserves approved baseline guidance unless an explicit,
evidence-backed semantic change is reviewed.

## Full replacement

Full replacement is separate and exceptional:

```bash
content-creator --workspace . voice rebuild <voice-id> --full-regenerate
```

It discards baseline precedence, records every semantic loss, runs evaluation,
and still requires human approval. It is not an alias for full-corpus
reanalysis.

## Diff, approval, rejection, and recovery

```bash
content-creator --workspace . voice diff <voice-id>
content-creator --workspace . voice approve <voice-id> \
  --approved-by "<author>"
content-creator --workspace . voice reject <voice-id> \
  --candidate-hash sha256:<hash> \
  --rejected-by "<author>" \
  --reason "<reason>"
```

Approval validates the active baseline again under the shared lifecycle lock,
publishes the next immutable version atomically, freezes the prior learning
epoch, creates a fresh new-version epoch, writes an epoch-transition receipt,
and updates the registry. Incorporated records are not copied into the new
epoch. Only explicitly `carry-forward` records enter it.

Repeating approval for the same candidate returns the existing receipt. A stale
baseline, concurrent lifecycle operation, component mismatch, or incomplete
learning selection fails closed. Rejection and failure leave the active voice
unchanged.

## Persisted evidence

An upgrade candidate includes:

- `voice-upgrade-plan.json`;
- `evidence-baseline.json` and `evidence-delta.json`;
- `learning-selection.json` and `learning-dispositions.json`;
- `voice-evolution.json`;
- standalone and active-baseline regression evaluation;
- the candidate manifest and component hashes; and
- after activation, approval and learning-epoch-transition receipts.

Learning memory is resolved by exact immutable voice version:

```text
profiles/<voice-id>/learnings/1.0.0/memory.json
profiles/<voice-id>/learnings/2.0.0/memory.json
```

A run pinned to version 1 can never mutate or load version 2 learning. Historical
epochs remain frozen and verifiable rather than being deleted.
