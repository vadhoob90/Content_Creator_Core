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
