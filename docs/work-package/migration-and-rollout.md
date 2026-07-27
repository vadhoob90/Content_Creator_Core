# Migration and rollout

## Strategy

Create a new repository. Do not convert LinkedIn Writer in place.

LinkedIn Writer remains the behavioural baseline and rollback path until the
new repository has proven:

- Provider parity
- All current routes
- Publication and learning behaviour
- Bharath voice compatibility
- Offline and live evaluation parity

## Migration sequence

### 1. Establish the new repository

- Create `content-creator`
- Copy only reusable code initially
- Preserve attribution to the original project
- Add new package and CLI names
- Configure offline CI

### 2. Extract the core

Move provider adapters, runner, storage and quality logic. Replace
LinkedIn-specific imports and enums with generic contracts.

Run the provider contract suite before adding content packs.

### 3. Migrate LinkedIn into packs

Implement and test `general-text` first. LinkedIn packs extend its common text
pipeline and add only channel-specific defaults, validators and rubrics.

Map:

```text
rubrics/post.yaml       → packs/linkedin-post/rubric.yaml
rubrics/article.yaml    → packs/linkedin-article/rubric.yaml
post validators         → packs/linkedin-post/validators.yaml
article validators      → packs/linkedin-article/validators.yaml
posts/ destination      → LinkedIn post pack destination
articles/ destination   → LinkedIn article pack destination
```

The generic orchestrator must contain no LinkedIn directory or word-limit
logic.

### 4. Migrate Bharath as the first voice package

Use the current profile, learnings and published content to build:

```text
profiles/bharath/
```

The imported profile begins as a candidate. Run the new voice evaluation and
activate it through the same deterministic command as any other profile.

Do not special-case Bharath in application code.

### 5. Add a second content pack

Implement `briefing-note` or `blog-post`. This proves that the pack abstraction
is real rather than renamed LinkedIn branching.

### 6. Add the first new voice

Use the user’s real authorised URL and document corpus after fixture tests pass.
Keep private extracted source content out of Git.

### 7. Parallel operation

For selected LinkedIn briefs:

1. Run the current repository
2. Run Content Creator with the migrated Bharath voice
3. Compare route, integrity, voice and author assessment
4. Record differences without making exact wording a regression target

### 8. Cutover

Cut over conversational use only when:

- The generic repository passes the definition of done
- The author accepts the migrated voice
- Manual OpenAI and Anthropic evaluations pass
- Recovery commands are documented

Keep LinkedIn Writer available in read-only or maintenance mode for a defined
rollback period.

## Data migration

Migrate:

- Stable voice profile
- Active and provisional learning records
- Agent definitions that are genuinely generic
- Published content used as approved evaluation evidence
- Provider and route evaluation cases

Do not migrate into the generic core:

- Person-specific prompt rules
- LinkedIn directory assumptions
- Historical run caches
- API keys
- Downloaded source pages
- Private documents without explicit approval

## Compatibility

Optional transitional aliases:

```bash
linkedin-writer run ...       # delegates to content-creator content run
linkedin-writer publish ...   # delegates to content approve + finalize
```

Aliases are temporary and must emit the resolved content pack and voice so
there is no hidden default.

## Rollback

Activation rollback does not delete a version. It changes the registry pointer
to the previous approved version and creates an audit event:

```bash
content-creator voice rollback aisha-khan --to 1.0.0
```

Repository rollout rollback returns conversational use to LinkedIn Writer.
Content and profile artifacts created in Content Creator remain preserved.

## Principal risks

| Risk | Mitigation |
|---|---|
| Framework becomes too broad | Limit first release to text content and prove a second pack |
| Generic prompts reduce quality | Keep pack and voice overlays explicit |
| Voice becomes caricature | Independent critic, held-out tests and human approval |
| Source authorship is guessed | Deterministic attribution and required review for uncertainty |
| Private corpus enters Git | Ignored cache and provenance-only committed records |
| Approved profile changes silently | Immutable versions, hashes and run snapshots |
| Learning leaks between people | Voice-scoped storage and isolation tests |
| Activation partially succeeds | Lock and atomic registry transaction |
| AI forgets a step | Authoritative CLI commands and state enforcement |
| Exact source language is copied | Phrase-overlap hard gate |
