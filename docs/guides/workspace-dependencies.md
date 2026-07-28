# Versioned core and implementation workspaces

`Content_Creator` is the reusable engine. A real content implementation should
be a separate, thin repository that installs a tagged engine release and keeps
its own voices, sources, runs, publications, and optional overrides.

## Consumer dependency

Pin an implementation to a release rather than the moving `main` branch:

```toml
[project]
name = "example-content-workspace"
version = "0.1.0"
dependencies = [
  "content-creator @ git+https://github.com/vadhoob90/Content_Creator.git@v0.2.0",
]
```

Commit the consumer lockfile. Upgrade deliberately by changing the tag,
refreshing the lock, and running downstream tests.

## Thin workspace

An implementation repository normally contains:

```text
content-creator.yaml
profiles/
voice-material/
runs/
published/
```

Run commands from that repository or pass it explicitly:

```bash
content-creator --workspace . init
content-creator --workspace . doctor
```

The installed package supplies default agents, model configuration, content
packs, rubrics, evaluation cases, and the placeholder voice. A workspace file
at the same relative path overrides the packaged default. Profiles, sources,
runs, publications, and learnings remain workspace-owned.

For example, `packs/legal-note/pack.json` adds a workspace-specific pack, while
`packs/general-text/pack.json` overrides the packaged `general-text` pack.

## Release flow

1. Implement and validate generic changes in `Content_Creator`.
2. Tag a release.
3. Update the pinned dependency in each implementation repository.
4. Run each implementation's downstream checks.
5. Commit the dependency and lockfile update.

Do not clone the core at runtime, manipulate `PYTHONPATH`, use a Git submodule,
or track the core repository's moving `main` branch.
