# Migrating a content repository to v0.3

Version 0.3 makes repository agents explicit. The core no longer treats an
installed generic agent prompt as the content repository's editorial policy.

## Migration

After updating the dependency and lockfile:

```bash
content-creator --workspace . agents scaffold
content-creator --workspace . agents status
content-creator --workspace . agents diff-template
content-creator --workspace . doctor
```

Scaffolding creates only missing files. It never overwrites an existing agent
or learning store.

Review every file under `agents/`. Remove generic material that belongs to the
core contract and replace it with the repository's domain and editorial
behaviour. Keep the role names and required files.

The new `learnings/memory.json` is repository-wide. Do not copy voice memory
into it automatically. Promote a principle across voices only after human
review.

## Behaviour change

In v0.2, `agents/writer.md` replaced the packaged writer prompt. In v0.3 it is
composed after the mandatory core harness and writer contract. This prevents a
content repository from accidentally removing routing, evidence, or lifecycle
boundaries while still allowing its writer to be genuinely different.

`doctor` now fails when required repository agents or repository learning
memory are missing. Run context schema `1.1` records hashes for core contracts,
repository agents, repository learning memory, and voice learning memory.
