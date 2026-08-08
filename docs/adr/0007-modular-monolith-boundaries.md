# ADR 0007: Modular monolith boundaries

Status: accepted.

## Context

Content Creator Core is distributed as one Python package and executed as one
local process. Its domain has grown to include orchestration, voices,
perspectives, providers, diagnostics, statistical assessment, and visuals.
Splitting those capabilities into network services would add deployment,
failure, security, and consistency costs without improving the author
workflow. Leaving every capability directly coupled to the orchestrator would,
however, make each addition harder to understand and change safely.

## Decision

Core remains a modular monolith. Modules are organised around cohesive domain
capabilities and communicate through narrow typed contracts at genuine
substitution points.

The intended dependency direction is:

1. Domain models, deterministic rules, and contracts do not depend on CLI or
   provider implementations.
2. Application services coordinate domain behavior through explicit
   interfaces.
3. Provider, persistence, diagnostics, and optional-capability adapters
   implement those interfaces.
4. The CLI and package entry points compose the application.

The internal package import graph remains acyclic. Low-level persistence does
not import application features to trigger secondary behavior. When a save must
also refresh feature-owned evidence, the application composition boundary
injects that behavior through a narrow callback or existing service contract.
Function-local imports are not an acceptable way to hide a reversed dependency.

Repository workspaces remain outside this package boundary. They supply
configuration, author-owned agents, voices, perspectives, and learning, but
cannot weaken Core contracts.

Optional capabilities must be registered at declared seams. Adding an optional
feature should not require unrelated feature branches throughout the main
workflow.

## Consequences

- Core keeps one release, one local transaction boundary, and one upgrade
  path.
- Refactoring proceeds through small behavior-preserving changes rather than a
  rewrite.
- Public CLI, Python, schema, persisted-artifact, and generated-workspace
  contracts require compatibility tests.
- Shared mechanics may be extracted, but domain policies remain with the
  domain that owns them.
- Architecture reporting begins as advisory evidence. A rule becomes blocking
  only after it is precise, useful, and compatible with current behavior.
- Architecture reporting blocks internal import cycles and identifies each
  participating direct edge so remediation restores dependency direction.

Microservices, a general event bus, and an unrestricted third-party plugin
system are explicitly out of scope.
