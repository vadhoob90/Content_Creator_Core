# Standard repository agent template

These files are editable starting points for a content repository. The
`content-creator init` and `content-creator agents scaffold` commands copy them
into a workspace without overwriting existing files.

Repository agents define domain and editorial behaviour. They do not own
routing, model selection, persistence, approvals, retries, publication, or
output schemas. Those mechanisms and mandatory role boundaries come from the
versioned Content Creator core.

At runtime the prompt is composed in this order:

1. core harness;
2. core role contract;
3. repository-owned agent;
4. repository and voice learnings;
5. selected voice and perspective;
6. pack and rubric instructions.

Customise the copied files for the repository. For example, a legal researcher
and a technical researcher should use different source hierarchies while both
remain subject to the same core evidence-integrity contract.
