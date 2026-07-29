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

Pin a content repository to a release rather than the moving `main` branch:

```toml
[project]
name = "example-content-workspace"
version = "0.1.0"
dependencies = [
  "content-creator @ git+https://github.com/vadhoob90/Content_Creator_Core.git@v0.4.0",
]
```

Commit the consumer lockfile. Upgrade deliberately by changing the tag,
refreshing the lock, and running downstream tests.

## Initialise a repository

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
rubrics, evaluation machinery, and the placeholder voice. A workspace may add
or override those policies deliberately. For example,
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
