# ADR 0010: Module responsibility and size guardrails

- Status: Accepted
- Date: 2026-08-02

## Context

Core had stable public seams but several implementation modules mixed parsing,
dispatch, contracts, persistence, rendering, and workflow policy. The 1,424-line
command runtime and multiple 500–830-line modules made changes harder to review
and weakened confidence that tests isolated the responsibility being changed.
Line count is not a quality score, but sustained size was a useful signal of
multiple reasons to change.

## Decision

Core adopts enforceable production-module limits:

- the command runtime compatibility façade is limited to 300 lines;
- every production module is limited to 500 implementation lines; and
- 400 lines is a non-blocking review signal for extracting a cohesive
  responsibility.

Command families own parser registration and execution. Stable import locations
may remain as small compatibility façades. Extractions must name a real
responsibility and preserve dependency direction; moving a monolith unchanged,
compressing formatting, or creating arbitrary numbered fragments does not
satisfy this decision.

The architecture report enforces the limits in CI. Structural changes begin
with characterisation or architecture tests and retain public CLI, Python,
schema, generated-workspace, and persisted-data contracts unless a deliberate
migration is released.

Implementation lines exclude only definition docstrings. The report retains
physical line counts so documentation does not hide total file size. This
clarification, adopted on 2026-08-05 with full production docstring coverage,
preserves the executable-code budget instead of forcing cohesive modules to be
split merely because their contracts are documented.

## Consequences

The runtime, orchestration, diagnostics, scaffolding, coordinator, voice
builder, voice ML, visual, voice, and perspective implementations are split
into focused modules. More internal modules and compatibility re-exports are
accepted in exchange for smaller review units and clearer ownership. A future
exception requires an ADR with rationale, owner, expiry, and remediation issue;
it is not added silently to an allow-list.
