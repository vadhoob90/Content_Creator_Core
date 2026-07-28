# ADR 0002: Single-base content packs

Status: accepted.

`general-text` is directly executable and specialised text packs may extend
exactly that one base. Deterministic overrides are restricted by the manifest.
Integrity validators are additive and cannot be removed. This avoids ambiguous
multiple-inheritance resolution and keeps pack rules isolated.
