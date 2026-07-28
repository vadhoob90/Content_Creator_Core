# Agent contracts

These files define specialised execution roles. An agent is a prompt, input
contract, output contract, permitted tools, learnings, and model profile. It is
not an autonomous workflow controller.

## Boundaries

| Component | Owns | Does not own |
|---|---|---|
| Briefing Agent | Understanding and structuring the request | Route execution or model selection |
| Researcher | Evidence and source integrity | Prose |
| Writer | Drafting and revision | Research or approval |
| Critic | Editorial assessment | Revision loops or publication |
| Learning extractor | Evidence-backed learning candidates | Rewriting history or publishing |
| Attribution reviewer | Resolving evidentially ambiguous authorship | Guessing identity or activation |
| Voice analyst | Evidence-backed style-pattern candidates | Biography or approval |
| Profile critic | Rejecting unsupported or caricatured patterns | Rewriting the candidate |
| Voice evaluator | Transfer, channel, genericity and integrity evaluation | Activation |
| Orchestrator | Stage order, state, retries, pause and resume | Editorial judgement |

The orchestrator is deterministic application code. The quality gate is
calculated from critic output and deterministic validation; the critic does not
publish or control iteration.
