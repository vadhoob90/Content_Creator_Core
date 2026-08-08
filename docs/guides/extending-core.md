# Extending Content Creator Core

Core exposes narrow seams for integrations that have current consumers. Keep
extensions outside orchestration and preserve author approval, provenance,
validation, diagnostics, and local-only publication.

## Add a provider

Implement `content_creator.providers.Provider`, convert vendor responses into
`ModelResponse`, and register the instance with `ProviderRegistry`. Start with
the executable [custom provider example](../../examples/extensions/custom_provider.py)
and the [provider configuration guide](provider-configuration.md).

Provider adapters own credentials, vendor request syntax, retry translation,
and usage metadata. They do not select content routes or bypass validation.

## Compose lifecycle stages

Hosts can supply `LifecycleStages` containing implementations of the research
and draft-review contracts. The executable
[custom stages example](../../examples/extensions/custom_stages.py) uses the
callable adapters and injects the result into `Orchestrator(stages=...)`.

A custom stage replaces execution inside an existing checkpoint contract. It
does not remove research approval, author review, provenance, or publication
gates. Prefer a function plus the callable adapter when no independent state or
lifecycle needs to be owned.

## Add a content pack

Use the [content-pack authoring guide](content-pack-authoring.md) for the worked
CLI flow, manifest rules, validation, replay cases, and isolation test. Packs
own channel semantics and cannot select providers or weaken integrity gates.

## Prove a reusable seam

Use `examples/contrib/` for a small experiment before adding a protocol,
factory, or registry. Document at least two current consumers, characterize the
existing behavior, and show that the normal reading path becomes shorter. The
architecture report's cohesion signals are advisory evidence, not a mandate to
extract or merge files.
