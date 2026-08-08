# My agents

Each Markdown file in this directory specialises one agent for this repository.
Run `content-creator --workspace . personalisation show` to see which files
have been customised and which remain unchanged Core starting points.

## How an agent becomes personal

Core builds an effective instruction set for every run from:

1. the mandatory Core harness and role contract;
2. the editable repository agent in this directory;
3. the role's learning policy, where applicable;
4. the selected active voice and approved perspectives;
5. active repository-wide and voice-specific learning; and
6. rubrics and content-pack instructions.

The files here are deliberately stable. New author feedback is recorded as
traceable learning rather than silently rewriting an agent definition.

## Roles

- `briefing-agent.md` turns a request into a structured work order.
- `researcher.md` builds a traceable evidence brief.
- `writer.md` produces the draft.
- `critic.md` reviews it against evidence, voice, and rubrics.
- `learning-extractor.md` proposes role-specific learning after author review.
- `voice-analyst.md`, `profile-critic.md`, `attribution-reviewer.md`, and
  `voice-evaluator.md` build and assess voice candidates.
- `perspective-extractor.md` and `perspective-evaluator.md` govern reusable
  author positions.

The `researcher-learnings.md`, `writer-learnings.md`, and
`critic-learnings.md` files define what each role may learn. Core still owns
routing, persistence, approvals, publication, retries, and output schemas.
