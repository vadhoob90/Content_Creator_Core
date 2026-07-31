# Standard repository agent template

These files are editable starting points for a content repository. The
`content-creator init` and `content-creator agents scaffold` commands copy them
into a workspace without overwriting existing files.

Repository agents define domain and editorial behaviour. They do not own
routing, model selection, persistence, approvals, retries, publication, or
output schemas. Those mechanisms and mandatory role boundaries come from the
versioned Content Creator core.

At runtime Core composes the applicable prompt layers in this order (some
layers are role- or route-specific):

1. core harness;
2. core role contract;
3. repository-owned agent;
4. repository learning policy;
5. resolved active voice and approved perspectives;
6. active repository and voice-scoped learnings; and
7. rubrics and content-pack instructions.

The voice-building agents also receive deterministic linguistic measurements
from the authorised corpus. They interpret those measurements as evidence,
not as writing targets or proof of authorship. See the [statistical voice
evidence guide](https://github.com/vadhoob90/Content_Creator_Core/blob/main/docs/guides/linguistic-voice-framework.md).

When statistical draft scoring and the selected pack are both eligible, Core
supplies its advisory report only to the critic. The writer receives no
numerical target, and the score does not change validation, rubric weighting,
or publication gates.

Customise the copied files for the repository. For example, a legal researcher
and a technical researcher should use different source hierarchies while both
remain subject to the same core evidence-integrity contract.
