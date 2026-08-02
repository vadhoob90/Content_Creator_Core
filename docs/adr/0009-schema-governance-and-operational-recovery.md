# ADR 0009: Schema governance and operational recovery

## Status

Accepted, 2026-08-02.

## Context

Core persists contracts consumed across releases and runs in private author
workspaces where failures must be diagnosable without exposing content. Model
classes alone did not state a read window, produce an indexed schema bundle,
or provide privacy-safe recovery evidence.

## Decision

Core will maintain a central schema catalogue derived from its Pydantic
models, explicit writer and reader versions, deterministic exports, and pure
compatibility migrations. Unsupported versions fail closed.

Core will also expose an offline operations command family. Support bundles
contain metadata and hashes only. Recovery inspection distinguishes active
locks, stale locks, and corrupt run state, and recommends non-destructive
actions without applying them.

Provider, visual, schema, and operations command families own parsing and
execution; voice and perspective own execution behind the stable CLI façade.
Full production source is subject to MyPy with untyped definitions prohibited.

## Consequences

Persisted-contract changes need fixtures, migrations, and release notes.
Operational evidence is useful for support but deliberately cannot reproduce
private content. New command families add small modules, while reducing the
responsibilities that accumulate in the shared runtime.
