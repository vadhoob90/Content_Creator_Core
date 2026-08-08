# ADR 0012: Concept cohesion and package promotion

- Status: Accepted
- Date: 2026-08-05

## Context

ADR 0010 and ADR 0011 established useful module, function, and control-flow
limits. Those limits prevent monoliths, but a mechanical extraction can still
make code harder to read. In particular, moving part of one implementation to
a base class in another flat module makes a reader reconstruct one concept
across an inheritance chain. Conversely, importer counts, filename prefixes,
and physical size cannot by themselves prove that a boundary is wrong.

Core needs a consistent way to distinguish a cohesive extraction from an
incidental split without replacing engineering judgment with noisy structural
metrics.

## Decision

Core retains the 500 implementation-line hard module limit while reporting
physical size separately. A size limit is a constraint, not a definition of
cohesion: extraction follows an independently understandable responsibility
and reason to change.

A package is appropriate when several modules form one named subsystem and
each contained module owns a responsibility that can be understood and tested
independently. Moving a flat implementation into a directory, or creating
generic `base`, `support`, `common`, `helpers`, or `utils` layers, does not
establish a package boundary.

Inheritance represents genuine substitutability. A base class is not used
merely to distribute one implementation across files. When behavior is
assembled from one implementation of each responsibility, Core prefers direct
functions or composition. New protocols, factories, registries, and reusable
abstractions require current consumers; the existing two-use principle remains
the default before generalising internal code.

A module with one production importer, a small module, a shared filename
prefix, or a cross-file base class triggers review only. These signals remain
non-blocking until a separate decision demonstrates an objective rule, a low
false-positive rate, and a clear remediation path. CI may block precise
accepted invariants and supported compatibility contracts.

The root exports in `content_creator.__all__` remain the primary public Python
API. Documented subsystem façades may additionally provide stable import
locations. An internal import path does not become supported merely because it
is importable. Before structural work, maintainers classify affected paths as:

- permanent façade: a documented entry point retained across internal moves;
- temporary migration shim: retained for a documented compatibility window;
  or
- internal implementation: may move with repository callers updated in the
  same change.

Temporary shims are not documented as canonical architecture and include an
explicit removal decision. A refactor is incomplete when it only adds wrappers
without removing or justifying the structure that caused the reading problem.

## Implementation workflow

Structural work begins with behavior and import characterization. Each focused
change states the demonstrated reading or maintenance problem, explains every
new module's independent responsibility, and identifies the old structure it
removes. The normal reading path for a representative operation must not gain
unexplained delegation layers.

Large structural programmes use a pilot and reassessment. Later refactors are
not authorised merely because they appeared in the original plan; they proceed
only when the pilot reduces navigation and preserves behavior without
speculative abstractions.

## Consequences

Core accepts that some cohesive modules will approach the hard size limit and
that some small or single-consumer modules are legitimate boundaries. Reviews
must explain architectural judgment rather than cite one metric. Stable
façades protect deliberate entry points, while internal modules remain free to
move. Architecture reporting can expose useful structural signals without
forcing maintainers to optimise for the report.

The v1.7 review applied this rule to the earlier `overlap`, `corpus`, and
`health` candidates. Corpus sufficiency moved into the cohesive `voice_build`
subpackage, and phrase-overlap policy moved beside its sole consumer in voice
evaluation. `health` remains a standalone capability because CLI diagnostics,
the coordinator, and upgrade auditing consume it for the same named purpose;
merging it would hide rather than improve cohesion.
