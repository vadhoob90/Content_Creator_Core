# ADR 0019: Shared editorial guidance with local voice authority

Status: Accepted; included in v1.21.0.

## Context

Author workspaces have been defining overlapping rules to reduce generic model
prose. Copying those rules into repository-owned agents makes updates depend
on manual reconciliation and risks replacing distinctive author preferences.
The [research review](../research/ai-writing-patterns.md) supports contextual
editorial assessment, with substantial limits on universal linguistic tells.

## Decision

Load one packaged `contracts/editorial-standard.md` into writer and critic
prompts. Read it directly from Core, independently of workspace rubric and
contract overrides. Keep the repository source copy in parity with the packaged
resource. Compose it before the selected voice and learnings, after the
existing base contract and repository-agent sections.

The standard defines shared editorial defaults and explicitly gives local
author instructions, selected voice, active learnings, and pack context the
ability to specialise those defaults. Existing factual-integrity and author
approval rules are unchanged. No detector, lexical blacklist, deterministic
rewriter, new score, or style-based publication gate is introduced.

Reuse `PromptProvenance` to record a `core-editorial` loaded/skipped layer.
Record an `editorial_standard` component hash in new resolved contexts. These
are additive fields in existing open-ended categories/maps; historical records
remain readable without migration. There is no new public API or configuration
schema. Prompt text and token usage change for writers and critics.

## Consequences and validation

Core package upgrades distribute the policy to existing and new workspaces;
updating repository files alone does not. Existing content and local policies
are preserved. Research and worked examples remain documentation; the manual
evaluation set is packaged separately and is not part of route replay.

Behaviour tests cover applicable roles, composition without a work order,
legacy overrides, local-file preservation, package-policy changes, and hashes.
Resource parity and wheel validation protect distribution. Human/model
evaluation remains separate from deterministic software tests. No claim of
universal stylistic improvement follows from instruction delivery.

The change is backward-compatible added functionality and should be included
in a minor release under the existing classification policy. Version 1.21.0 includes this capability. Consumer pins remain deliberate
workspace upgrades.
