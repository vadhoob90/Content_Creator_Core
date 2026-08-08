# How Content Creator works

Content Creator separates human editorial authority, governed workflow
execution, and model capability. The human works in natural language, Core
coordinates the lifecycle, repository-owned agents specialise each role, and
persisted artifacts keep the run reviewable without relying on chat history.

The diagrams below show the same system from three perspectives.

## Human, execution harness, and LLMs

Here, **execution harness** is a descriptive term for the complete runtime
assembly: Core mechanisms, the selected workspace agents, and the persisted run
artifacts they produce. It is not a separate package or an additional source of
editorial authority.

```mermaid
flowchart TB
    H["Human<br/>intent · feedback · approval"]

    subgraph HARNESS["Execution harness"]
        direction TB
        C["Core<br/>interpret · route · compose · validate · transition"]
        A["Agents<br/>briefing · research · writing · criticism · learning"]
        R["Artifacts<br/>work order · sources · drafts · decisions · receipts"]

        C -->|"loads role instructions"| A
        A -->|"returns structured role output"| C
        C -->|"persists state and provenance"| R
        R -->|"restores exact run context"| C
    end

    subgraph MODELS["Provider-neutral LLM layer"]
        direction LR
        P{"Selected adapter"}
        O["OpenAI API"]
        N["Anthropic API"]
        X["Codex-native"]
        L["Claude-native"]

        P --- O
        P --- N
        P --- X
        P --- L
    end

    H -->|"natural-language request"| C
    C -->|"drafts · checkpoints · explicit choices"| H
    C -->|"resolved prompt + contract + schema"| P
    P -->|"structured model output"| C
```

The LLM does not own workflow state or decide whether a voice, research
checkpoint, draft, or publication is approved. Core selects one configured
adapter for a request, validates its output, and persists the resulting state
in the Author's workspace.

## Agent interaction

Agents are specialised contributors rather than autonomous peers. Core gives
each agent only its resolved role context, validates the response, records the
artifacts, and determines which transition is allowed next.

```mermaid
flowchart LR
    H1["Author request"] --> C1["Core starts run<br/>and resolves route"]
    C1 --> B["Briefing agent<br/>structured work order"]
    B --> C2["Core validates<br/>pack · voice · research"]
    C2 --> Q{"Research required?"}

    Q -->|"yes"| RS["Researcher<br/>traceable evidence brief"]
    RS --> RC{"Approval checkpoint<br/>when required"}
    RC -->|"approved"| W
    Q -->|"no"| W["Writer<br/>voice-aware draft"]

    W --> V["Core validation<br/>rules · evidence · provenance"]
    V --> CR["Critic<br/>rubric assessment"]
    CR --> D{"Quality decision"}
    D -->|"revise"| W
    D -->|"ready"| H2["Author review"]
    H2 -->|"revise"| W
    H2 -->|"approve or publish"| P["Core records decision<br/>and verified output"]
    P --> LE["Learning extractor<br/>supported feedback only"]

    S[("runs/&lt;run-id&gt;/<br/>shared persisted memory")]
    B -.-> S
    RS -.-> S
    W -.-> S
    V -.-> S
    CR -.-> S
    P -.-> S
    LE -.-> S
```

Research approval appears only on routes that require it. No-research routes
remain no-research, and the author remains the final authority for revision,
approval, and repository publication.

## Core and the Author's workspace

Core owns reusable mechanisms and non-negotiable contracts. The Author's
workspace owns editorial policy, identity-linked material, learning, and
content. The resolved run context combines both without copying Core into the
workspace.

```mermaid
flowchart LR
    subgraph CORE["Content Creator Core"]
        direction TB
        C1["Routing and orchestration"]
        C2["Typed schemas and lifecycle"]
        C3["Provider adapters and prompt composition"]
        C4["Validation, quality gates, and retries"]
        C5["Evidence, provenance, and integrity rules"]
        C6["Versioning, receipts, and idempotency"]
    end

    subgraph AUTHOR["Author's workspace"]
        direction TB
        A1["Editable agent instructions"]
        A2["Verified voice and approved perspectives"]
        A3["Content packs, rubrics, and route policy"]
        A4["Repository and voice-scoped learning"]
        A5["Authorised research sources"]
        A6["Runs, approved content, and publications"]
    end

    CORE --> R["Resolved run context<br/>Core contracts + workspace policy"]
    AUTHOR --> R
    R --> O["Reproducible, reviewable content run"]
```

This boundary allows Core to evolve as a reusable dependency while every
author retains control of their own voice, agents, policies, evidence, run
history, and approved content.

For the exact prompt and context assembly order, see
[Runtime context composition](runtime-context-composition.md). For the design
rationale, see
[Content Creator compared with a general-purpose chat app](why-not-just-chat.md).
