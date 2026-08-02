# Development principles

These principles guide implementation and review in Content Creator Core. They
are decision aids rather than slogans or mechanical scoring rules.

The blocking limits and the map to all specialist controls are in
[Architecture and development guardrails](architecture-guardrails.md). Apply
that checklist alongside these principles; do not treat either document as a
substitute for the other.

## Protect author authority and integrity first

Correctness includes the product boundaries: human approval, voice and
perspective isolation, source provenance, no-research routes, deterministic
validation, and local publication. A refactoring is incomplete if it weakens
one of these guarantees.

## Prefer readability and explicit behavior

Code is maintained more often than it is written. Choose names that express
domain intent, keep control flow visible, and make state transitions explicit.
Comments explain why a constraint exists; they do not compensate for avoidably
unclear code.

## Apply DRY to knowledge, not incidental syntax

There should be one authoritative implementation of a rule such as component
hash verification or atomic manifest persistence. Similar-looking domain
policies may remain separate when they change for different reasons. Do not
introduce an abstraction merely to remove a few repeated lines.

## Balance reuse with YAGNI

Build the smallest seam required by current consumers. Prefer two proven uses
before generalising an internal abstraction. Delete speculative extension
points and compatibility paths when their supported purpose has ended.

## Keep modules cohesive and dependencies directed

Organise by capabilities that change together. Domain rules must not depend on
entry points or concrete external providers. Application services coordinate
through narrow contracts, and the CLI composes them. A small change should
normally require understanding one module and its neighbours.

## Use dependency inversion selectively

Use Python `Protocol` types where multiple implementations, fakes, or optional
capabilities already require substitution. Do not wrap stable concrete code in
an interface without a demonstrated boundary.

## Practice test-driven development

For new behavior:

1. Add a focused failing test that expresses the contract.
2. Implement the smallest change that passes it.
3. Refactor while the suite remains green.

For structural refactoring, first add characterization or contract tests for
the current observable behavior. Move one responsibility at a time and prove
that behavior is unchanged. Do not manufacture meaningless failures for a file
move.

Tests should cover behavior and boundaries rather than private implementation
shape unless that shape is an intentional architecture rule.

## Default development workflow

Future Core work should follow this sequence:

1. State the user or maintainer outcome and identify the public or persisted
   contracts it could affect.
2. Add a focused failing behavior test. For structural work, add a
   characterization or architecture test before moving responsibilities.
3. Implement the smallest coherent slice and keep domain decisions in the
   module that owns them.
4. Refactor only while the focused tests stay green, then run the full offline
   baseline and `scripts/architecture_report.py --check`.
5. Update the changelog, relevant task guide, ADR, and compatibility notes in
   the same pull request when behavior or structure changes.
6. Release through a protected-main pull request and immutable tag; validate
   every pinned downstream workspace before calling the work complete.

Record a deliberate exception in the pull request when a step does not apply.
Do not silently skip a guardrail.

## Make small, reversible changes

Keep substantial refactoring separate from feature work. One pull request
should have one coherent purpose, include its tests, and leave Core releasable.
Prefer a sequence of safe extractions over a large redesign.

## Treat compatibility as a feature

CLI behavior, exported Python names, schemas, persisted artifacts, generated
workspaces, and adapter contracts are observable behavior. Inventory and test
them before restructuring. Any deliberate incompatibility requires migration
support and clear release communication.

Persisted formats follow the explicit read/write window in
[schema compatibility](schema-compatibility.md). Never infer an unknown schema
version, mutate input during migration, or remove a supported reader without
the documented deprecation window.

## Design failures for safe recovery

Use stable failure classifications, atomic writes, and exclusive operations.
Diagnostics must be useful without containing author text, prompts, provider
responses, secrets, or source paths. Recovery advice is non-destructive by
default and never bypasses an approval checkpoint.

## Ratchet quality rather than chase metrics

Coverage, typing, module size, and dependency reports expose risk; they do not
replace engineering judgment. New work must not reduce the established
baseline. Tighten a check only when it produces actionable signal and has a
clear remediation path.

## Review checklist

- Does the change preserve author authority and integrity boundaries?
- Is the behavior represented by a focused test?
- Is domain knowledge defined in one appropriate place?
- Is a new abstraction justified by current consumers?
- Does the dependency direction match ADR 0007?
- Does the lifecycle or capability boundary match ADR 0008?
- Does the module stay within ADR 0010's responsibility and size limits?
- Does persisted state follow the schema read/write and deprecation policy?
- Can a failure be classified and investigated without exposing author content?
- Are public and persisted contracts preserved or migrated?
- Can the change be understood, reviewed, and reversed independently?
- Do documentation and examples still describe the implementation accurately?
