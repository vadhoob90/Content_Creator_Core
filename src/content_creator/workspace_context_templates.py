"""Provide generated author guidance for runtime context composition."""

RUNTIME_CONTEXT_TEMPLATE = """# What my agents receive at runtime

Content Creator assembles each agent's context from Core rules and this
workspace. It records every loaded or skipped source without copying private
prompt text into another artifact.

## Preview a role

This command is read-only and does not invoke a model:

```bash
content-creator --workspace . personalisation explain \\
  --role writer \\
  --voice {voice_id} \\
  --pack {first_pack} \\
  --research none
```

It shows, in order, the Core harness and role contract, the editable agent
definition under `agents/`, the selected voice and approved perspectives,
active role-matched learning, and the pack's rubrics and instructions. Skipped
layers include an explanation.

## See it while creating content

Add `--show-context` to `content-creator run`. The loading trace goes to
standard error, while the normal run result remains on standard output.

## Inspect a completed run

```bash
content-creator --workspace . context show <run-id>
```

The underlying record is `runs/<run-id>/context-composition.json`. It contains
source paths, hashes, versions, selected record IDs, provider routing, and
private task-input hashes. It does not duplicate prompts, drafts, research,
feedback, credentials, or unselected private material.
"""
