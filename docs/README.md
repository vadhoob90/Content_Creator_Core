# Content Creator documentation

Choose the task that matches what you want to do. The root README stays focused
on the author journey; these guides contain the detailed terminal procedures.

## I want to create my first workspace

- [Create a thin content workspace](guides/creating-a-content-workspace.md)
- [Choose and configure a provider](guides/provider-configuration.md)
- [Troubleshoot setup](guides/troubleshooting.md)

After setup, run `content-creator --workspace . start` to see the next task and
`content-creator --workspace . overview` to inspect workspace health.

## I want to create or revise a voice

- [Voice onboarding](guides/voice-onboarding.md)
- [Voice creation](guides/voice-creation.md)
- [How voice is derived](guides/how-voice-is-derived.md)
- [Privacy and authorised sources](guides/privacy-and-sources.md)
- [Linguistic voice framework](guides/linguistic-voice-framework.md)

Voice activation remains an explicit human action. A new subject may require a
governed [perspective](guides/perspective-provenance.md), not a new voice.

## I want to create content

- [Content Creator Coordinator](guides/content-coordinator.md)
- [Routes and work orders](guides/routes-and-work-orders.md)
- [Learning and repository publication](guides/learning-and-publication.md)
- [Content Creator compared with a general-purpose chat app](guides/why-not-just-chat.md)

Core always returns the result for review and never publishes externally.

## I maintain an author workspace

- [Versioned dependencies and upgrades](guides/workspace-dependencies.md)
- [Repository-owned agents](guides/repository-agents.md)
- [Content pack authoring](guides/content-pack-authoring.md)
- [Testing and evaluation](guides/testing-and-evaluation.md)
- [Troubleshooting](guides/troubleshooting.md)

## I develop Content Creator Core

- [Core development guide](core/README.md)
- [Architecture decisions](adr/0001-provider-neutral-contract.md)
- [Package-registry distribution decision](adr/0005-package-registry-distribution.md)
- [Changelog](../CHANGELOG.md)
