# Versioned core and content workspaces

`Content_Creator` is a reusable execution kernel. A content implementation is a
separate repository that pins a tagged kernel release and owns its editorial
team, voices, learnings, sources, policies, runs, and publications.

## Responsibility boundary

The core owns mechanisms and non-negotiable contracts:

- routing and orchestration machinery;
- provider interfaces and standard adapters;
- shared input and output schemas;
- lifecycle, checkpoint, persistence, and immutable-version mechanisms;
- validation and evaluation machinery;
- hard evidence, provenance, and state-integrity rules; and
- deterministic prompt composition.

The content repository owns policy and behaviour:

- editable briefing, research, writing, criticism, and learning agents;
- repository-wide and voice-specific learnings;
- authorised voices and source inventories;
- domain rubrics, evaluation cases, packs, and route policy; and
- domain-specific approval and safety requirements.

## Consumer dependency

Pin a content repository to a package release rather than the moving `main`
branch:

```toml
[project]
name = "example-content-workspace"
version = "0.1.0"
dependencies = [
  "content-creator==1.0.0",
]
```

Commit the consumer lockfile. Upgrade deliberately by changing the tag,
refreshing the lock, and running downstream tests.

From v0.6, preview that change with:

```bash
content-creator --workspace . workspace upgrade --to v1.0.0
```

The preview shows the dependency and lockfile operation, packaged template
differences, preserved repository-owned paths, validation commands, and manual
follow-up. It also audits configuration and resources, provider selection and
privacy boundaries, runtime write paths, agents, learning memory, idempotency
storage, publications, sources, and every historical run against current pack
policy. It does not modify the workspace.

The compatibility result deliberately separates three claims: whether the
dependency update has been applied, whether the current workspace is ready,
and whether historical runs remain usable. Findings use `compatible`,
`automatically_migrated`, `decision_required`, or `blocking`, and include
plain-language summary lines plus decision prompts for the chat coordinator.

Apply the reviewed preview explicitly:

```bash
content-creator --workspace . workspace upgrade --to v1.0.0 --apply
```

Core accepts only a semantic-version tag or full 40-character reviewed commit,
never `main`, another branch, or an abbreviated commit. The apply workflow
refreshes the lock, runs doctor, verifies all voices, runs workspace tests, and
restores the dependency and lockfile if validation fails. New packaged
template files may be added, but existing repository-owned agents and skills
are preserved for manual review.

After a successful apply, Core persists the report under
`.content-creator/upgrades/` and adds `pack-migration.json` plus a visible event
to affected runs. The coordinator includes the latest report in its context,
so a chat response can explain compatible migrations and show both values for
conflicts. A conflict blocks only the affected run.

When the author approves adopting current pack policy, chat can invoke the
approval-gated operation represented by:

```bash
content-creator --workspace . workspace resolve-upgrade-run RUN_ID \
  --accept-current-pack
```

Core records the decision, removes only the conflicting legacy override, and
runs the existing final draft back through validation, criticism, quality
scoring, diff history, and provenance before it can be published.

Workspaces generated with the managed Core dependency block in their README
also have that block refreshed and rolled back transactionally. The rest of
the README is repository-owned. Legacy or fully custom READMEs without the
managed marker are never rewritten.

The workspace generator is available from `v0.4.0`. Production workspaces
should pin a reviewed package release. The corresponding immutable Git tag
remains the source-provenance record and fallback installation route.

## Generate a new repository

Use the complete generator for a new author, client, team, or brand workspace:

```bash
content-creator workspace create Content_Creator_Alice \
  --name "Content Creator Alice" \
  --author-name "Alice Example" \
  --voice-id alice-general \
  --pack linkedin-post \
  --pack linkedin-article
```

The generator creates the consumer dependency, repository configuration,
editable agents, learning scopes, author source inventory, content
destinations, repository guidance, smoke tests, and personalised onboarding. It
does not copy the Core implementation. See the
[complete workspace creation guide](creating-a-content-workspace.md).

## Initialise an existing repository

Use the low-level initializer only when adapting a repository that already owns
its dependency, README, guidance, source layout, and tests:

```bash
content-creator --workspace . init --agent-template standard
content-creator --workspace . doctor
```

Initialisation copies editable agent starting points and creates empty
repository learning memory without overwriting existing files:

```text
content-creator.yaml
agents/
├── briefing-agent.md
├── researcher.md
├── writer.md
├── critic.md
├── learning-extractor.md
└── ...
learnings/
└── memory.json
profiles/
voice-material/
runs/
```

The copied agents belong to the content repository. A legal workspace and a
technical-writing workspace can therefore develop different writers and
researchers while using the same execution kernel.

Inspect customisation against the template:

```bash
content-creator --workspace . agents status
content-creator --workspace . agents diff-template
```

Scaffolding preserves every existing workspace file. Core template changes do
not silently overwrite a repository's editorial configuration.

## Runtime composition

Every role prompt is assembled from:

```text
core harness
+ core role contract
+ repository-owned agent
+ repository learning policy
+ active repository learnings
+ selected voice and active voice learnings
+ perspective, pack, rubric, and run instructions
```

Repository instructions specialise a role but cannot replace the core contract.
Run context records hashes of every resolved contract, agent, and learning
memory used.

The installed package still supplies generic model configuration, packs,
rubrics, evaluation machinery, the legacy test placeholder, and the Clear
Professional Starter used by explicit onboarding. A workspace may add or
override those policies deliberately. For example,
`packs/legal-note/pack.json` adds a legal pack, while
`packs/general-text/pack.json` overrides the packaged general-text policy.

## Release flow

1. Implement and validate generic mechanisms in `Content_Creator`.
2. Tag a release.
3. Update the pinned dependency in each content repository.
4. Scaffold only genuinely new template files; never overwrite custom agents.
5. Review template differences and adapt intentionally.
6. Run each repository's downstream checks.
7. Commit the dependency and lockfile update.

Do not clone the core at runtime, manipulate `PYTHONPATH`, use a Git submodule,
or track the core repository's moving `main` branch.
