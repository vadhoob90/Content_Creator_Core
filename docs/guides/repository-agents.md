# Repository-owned agents and learnings

Agent behaviour is content-repository policy. Core contracts define what each
role is allowed to do; repository agents define how that role approaches its
domain and audience.

## Agent layers

The core harness prevents any agent from taking over routing, approval,
publication, persistence, or model selection. Role contracts add invariant
boundaries such as source traceability for research and evidence integrity for
criticism.

Files under the workspace's `agents/` directory are editable specialisations.
A legal researcher can prioritise legislation, judgments, and official
guidance. A technical researcher can prioritise specifications, source code,
benchmarks, and vendor documentation. Both remain subject to the same core
research contract.

For onboarding, inspect the layers in this order:

1. `contracts/agent-harness.md` for authority, safety, and publication limits.
2. `contracts/roles/<role>.md` for the role-specific invariant.
3. `agents/<role>.md` for repository-owned specialization.
4. `learnings/memory.json` and the selected voice's learning memory.
5. `content-creator personalisation explain --role <role>` for the effective
   preflight view, followed by `context show <run-id>` for persisted evidence.

If these layers conflict, the Core harness and role contract win. Do not copy a
Core invariant into every repository agent merely to make it more visible;
link the invariant and keep the specialization focused.

Use:

```bash
content-creator --workspace . agents scaffold
content-creator --workspace . agents status
content-creator --workspace . agents diff-template
```

Scaffolding is additive and never overwrites an existing agent.

## Learning scopes

`learnings/memory.json` contains active repository-wide principles. They apply
to every voice in that content repository.

`profiles/<voice-id>/learnings/memory.json` contains voice-specific principles.
They apply only when that voice is selected. Publication-triggered extraction
continues to write to voice memory so one voice cannot silently train another.

Moving a voice learning into repository memory is a deliberate human-reviewed
policy decision. Research findings and author subject-matter positions are not
writing learnings.

Only active records enter prompts. Provisional records remain available for
review but do not affect later work.

## Template evolution

Core templates are starting points, not live dependencies. Existing content
repositories are not overwritten when a template changes. Use
`agents diff-template` after a core upgrade to see where a repository has
diverged, then adopt useful changes manually.

If identical agent wording repeatedly needs the same fix in every repository,
consider whether it is actually a core contract or harness invariant. If
repositories should be allowed to disagree, keep it in their agent files.
