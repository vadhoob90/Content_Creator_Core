# LinkedIn Writer migration audit

This audit compares the working LinkedIn Writer baseline with Content Creator.
It distinguishes reusable engine capability, LinkedIn pack behaviour, private
voice data, and future Voice Builder work.

## Capability matrix

| LinkedIn Writer capability | Content Creator location | Status |
|---|---|---|
| Structured work orders | `src/content_creator/domain.py` | Migrated; adds `content_pack` and `voice_id` |
| Deterministic intake | `src/content_creator/intake.py` | Migrated |
| Ambiguous-request agent | `agents/briefing-agent.md` | Migrated and renamed from Intake Planner |
| Six post/article × research routes | `evals/cases/route-matrix.yaml` | Migrated |
| Route validation | `src/content_creator/routing.py` | Migrated |
| Deep agent-research checkpoint | `src/content_creator/orchestrator.py` | Migrated |
| Supplied research | `src/content_creator/orchestrator.py` | Migrated |
| OpenAI adapter | `src/content_creator/providers/openai.py` | Migrated |
| Anthropic adapter | `src/content_creator/providers/anthropic.py` | Migrated |
| Fake/replay provider | `src/content_creator/providers/fake.py` | Migrated |
| Capability-based model selection | `src/content_creator/configuration.py` | Migrated |
| Researcher, writer, critic, learning roles | `agents/` | Migrated and stripped of personal voice data |
| Core quality gate | `rubrics/core.yaml` | Migrated |
| Research overlays | `rubrics/research-*.yaml` | Migrated |
| Post/article overlays | `packs/linkedin-*/rubric.yaml` | Migrated into packs |
| Deterministic draft and research validation | `src/content_creator/validation.py` | Migrated |
| Bounded revision loop | `src/content_creator/orchestrator.py` | Migrated |
| Atomic run storage | `src/content_creator/storage.py` | Migrated |
| Pack-owned publication destinations | `packs/linkedin-*/pack.json` | Generalised |
| Publication-triggered learning | `src/content_creator/learning.py` | Migrated and scoped by voice |
| Replay evaluation harness | `src/content_creator/evaluation.py` | Migrated |
| Manual live-provider evaluation | `.github/workflows/live-provider-eval.yml` | Migrated |
| Path-filtered offline CI | `.github/workflows/ci.yml` | Migrated; content and learning-only changes do not trigger it |
| Conversational invocation | `.agents/skills/content-creator/` | Migrated and generalised |
| Repository operating rules | `AGENTS.md` | Migrated and generalised |
| Claude Code entry-point rules | `CLAUDE.md` | Migrated and generalised |

## Deliberately not copied

The following are user data, not reusable engine capability:

- The original author's stable voice profile
- Personal writer, critic, and researcher learnings
- Drafting history
- Published posts and articles
- Topic-specific research corrections

Content Creator contains a clearly labelled `default` placeholder profile for
offline tests. A real voice must enter through the authorised, versioned Voice
Builder lifecycle rather than being silently embedded in the generic template.

## Still outstanding

These capabilities did not exist in LinkedIn Writer and therefore cannot be
migrated from it:

- source ingestion for voice creation;
- author/subject/co-author attribution checking;
- corpus sufficiency assessment;
- candidate voice analysis and criticism;
- held-out voice evaluation;
- deterministic voice approval, activation, and deactivation;
- a direct executable route for the base `general-text` pack.

They remain covered by the staged Voice Builder work package.
