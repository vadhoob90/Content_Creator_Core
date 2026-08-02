# ADR 0006: Provider-independent visual assets

## Status

Accepted.

## Decision

Core defines typed visual briefs, adapter execution classes, asset lineage,
validation, critique, approval, and repository publication. Content packs
define platform constraints. Author workspaces retain personal design choices.

Adapters return a common `VisualOutput`; Core does not require or select a
specific image model. Deterministic renderers and generative providers are
equally valid execution classes. Exact copy and source rights fail closed when
they cannot be verified.

## Consequences

Visual production is reproducible and auditable without coupling Core to a
vendor. Packs can add platform behaviour without leaking personal brand rules
into the shared package. Existing packs remain text-only unless they opt in.
