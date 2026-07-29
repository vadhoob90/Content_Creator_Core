# Migrating a v0.3 workspace to v0.4

Version 0.4 adds thin-workspace generation, explicit voice onboarding,
starter-voice safeguards, external local-directory ingestion, and deliberate
provider selection.

Do not update a production dependency to `v0.4.0` until that immutable tag has
been published.

## What remains compatible

Existing approved voices and perspectives remain valid. New manifest fields
have defaults for v0.3 packages:

```text
strategy = source-derived
evidence_status = author-sources
perspectives_allowed = true
```

Historical versions and run context remain resolvable. Existing authors with
an active voice do not need to select the starter route.

## 1. Protect private local material

Add these rules to the downstream `.gitignore`:

```gitignore
.voice-cache/
profiles/*/work-order.json
voice-material/**/*
!voice-material/**/
!voice-material/**/source-urls.txt
```

Check the repository history before assuming private files were never
committed. Adding an ignore rule does not remove an already tracked file.

Prefer keeping private writing outside the repository and point Core at it:

```bash
content-creator --workspace . voice add-sources <voice-id> \
  --documents "/absolute/path/to/my-writing"
```

## 2. Select a provider deliberately

Core 0.4 has no implicit provider. Persist a native provider:

```bash
content-creator --workspace . provider select codex-native
content-creator --workspace . provider verify codex-native
```

Use `claude-native`, `openai`, or `anthropic` when intentionally selected.
`CONTENT_CREATOR_PROVIDER` remains a temporary shell override.

## 3. Decide whether onboarding state is useful

New generated workspaces contain:

```text
profiles/<voice-id>/onboarding.json
```

An existing workspace with an approved active voice does not require this file.
Do not mark an established voice as a starter. New author workspaces should use
the v0.4 generator and complete the onboarding checkpoint.

Because scaffolding preserves existing `README.md` and `AGENTS.md` files,
rerunning the generator does not silently replace downstream guidance. Adapt
the new checkpoint instructions deliberately when an existing workspace needs
them.

## 4. Update the dependency after release

After `v0.4.0` exists:

```toml
dependencies = [
  "content-creator @ git+https://github.com/vadhoob90/Content_Creator_Core.git@v0.4.0",
]
```

Then refresh and validate:

```bash
uv lock --upgrade-package content-creator
uv sync --dev
uv run content-creator --workspace . doctor
uv run content-creator --workspace . agents status
uv run content-creator --workspace . voice verify <voice-id>
uv run ruff check tests
uv run pytest
```

Review the lockfile to confirm it resolves the intended immutable Core commit.
