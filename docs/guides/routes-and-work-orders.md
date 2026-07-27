# Routes and work orders

`WorkOrder` is the provider-neutral hand-off from briefing to orchestration.
Its routing fields are `content_pack`, `format`, `research_depth`, and
`research_source`; `voice_id` selects the isolated profile and learning
namespace.

| Format | Depth | Source | Checkpoint |
|---|---|---|---|
| post | none | none | no |
| post | light | agent or supplied | no |
| post | deep | agent | after research |
| article | none | none | no |
| article | light | agent or supplied | no |
| article | deep | agent | after research |

Deep supplied research skips the researcher checkpoint because the author
supplied the evidence. The critic and evidence rules still apply.

Explicit author instructions win. Deterministic briefing handles phrases such as
“no research” or “deep research” without spending a model call. Materially
ambiguous requests go to the Briefing Agent, which may return focused
clarification questions rather than guessing.

Deep agent research persists `research.json` and returns
`awaiting_research_approval`. `approve-research` resumes from disk;
`reject-research` records the author's decision and stops before drafting.
