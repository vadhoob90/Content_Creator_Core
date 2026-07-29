# Create a thin content workspace

Use the workspace generator when a new author, client, team, or brand needs its
own Content Creator repository.

Do not clone Content Creator Core and delete reusable files. The generated
repository pins Core as a dependency and contains only the mutable editorial
material owned by that workspace.

## Install a released Core version

Install the CLI from an immutable Core tag:

```bash
uv tool install \
  "content-creator @ git+https://github.com/vadhoob90/Content_Creator_Core.git@v0.4.0"
```

A development installation may use a reviewed commit instead. Do not use a
moving branch for a production workspace.

## Generate the repository

For a LinkedIn-oriented author workspace:

```bash
content-creator workspace create Content_Creator_Alice \
  --name "Content Creator Alice" \
  --author-name "Alice Example" \
  --voice-id alice-general \
  --voice-label "Alice — General" \
  --pack linkedin-post \
  --pack linkedin-article
```

Without `--pack`, the command enables `general-text`.

The generator pins the tag corresponding to the installed Core version. Use an
explicit reviewed tag or commit when necessary:

```bash
content-creator workspace create Content_Creator_Alice \
  --author-name "Alice Example" \
  --core-ref 0123456789abcdef
```

Other useful options are:

```text
--agent-template standard
--perspective-mode automatic
--perspective-mode explicit
--perspective-mode disabled
--core-url <private fork or canonical Core URL>
```

Relative destinations are resolved from the current directory. When the global
`--workspace` option is supplied, it acts as the base directory.

## Generated repository

The result is a thin consumer:

```text
Content_Creator_Alice/
├── README.md
├── AGENTS.md
├── CLAUDE.md
├── pyproject.toml
├── content-creator.yaml
├── .env.example
├── .gitignore
├── agents/
│   ├── briefing-agent.md
│   ├── researcher.md
│   ├── writer.md
│   ├── critic.md
│   └── ...
├── learnings/
│   └── memory.json
├── profiles/
│   ├── registry.json
│   └── alice-general/
│       ├── onboarding.json
│       └── learnings/
│           └── memory.json
├── voice-material/
│   └── alice-general/
│       └── source-urls.txt
├── content/
│   ├── linkedin-post/
│   │   └── published/
│   └── linkedin-article/
│       └── published/
├── runs/
└── tests/
    └── test_workspace.py
```

It does not copy:

- `src/content_creator`;
- provider adapters;
- core role contracts;
- packaged model configuration;
- generic rubrics;
- packaged content packs; or
- orchestration and versioning code.

Those remain supplied by the pinned Core dependency.

## What belongs in the generated repository

The downstream repository owns:

- author-specific voice evidence and approved versions;
- perspectives and their provenance;
- repository and voice-scoped learnings;
- editable agent specialisations;
- content-pack overrides or new domain packs;
- research, drafts, critiques, and publication artifacts;
- repository-specific tests and policies; and
- approved publications.

Generic reusable mechanisms belong in Content Creator Core.

## Continue the onboarding

Enter the new repository and install its pinned dependency:

```bash
cd Content_Creator_Alice
uv sync --dev
uv run content-creator --workspace . doctor
uv run pytest
```

The generated README begins with an author checkpoint. The author chooses
whether to derive a voice from previous writing or begin with the neutral Clear
Professional Starter. `profiles/alice-general/onboarding.json` remains
`undecided` until that choice is recorded.

### Use previous writing

```bash
uv run content-creator --workspace . voice onboard alice-general \
  --strategy source-derived \
  --author-name "Alice Example" \
  --selected-by "Alice Example" \
  --use linkedin-post \
  --use linkedin-article
```

Add public URLs to:

```text
voice-material/alice-general/source-urls.txt
```

Place private, directly authored Markdown, text, DOCX, PDF, or HTML documents
in the same directory. Then follow the generated README to add the sources,
build, review, verify, and approve the candidate.

### Begin without previous writing

```bash
uv run content-creator --workspace . voice onboard alice-general \
  --strategy starter \
  --author-name "Alice Example" \
  --selected-by "Alice Example" \
  --use linkedin-post \
  --use linkedin-article
```

This activates a versioned neutral writing policy without claiming to represent
Alice's established voice. Core disables perspective creation and resolution
for the starter because no author positions have yet been evidenced.

Approved writing can later be supplied to the source-derived route. The
starter remains active while the candidate is reviewed; explicit candidate
approval restores the workspace's configured perspective policy. See
[Voice onboarding](voice-onboarding.md).

After activation, open the repository in Codex or Claude Code and make a
natural-language content request. `AGENTS.md` and `CLAUDE.md` establish the
repository workflow and ownership boundaries.

## Safe reruns

The command is idempotent. Rerunning the same command:

- creates files that are missing;
- reports existing files as preserved; and
- never overwrites repository agents, README content, configuration, learning
  memory, source inventories, tests, or publications.

This supports recovery from an incomplete setup without resetting later
customisation.

## `workspace create` versus `init`

Use:

```bash
content-creator workspace create ...
```

to generate a complete new downstream repository.

Use:

```bash
content-creator --workspace . init
```

only when adapting an existing repository. `init` is the low-level,
backward-compatible initializer for agents, repository learning memory,
registry, runtime directories, and `content-creator.yaml`. It does not create a
consumer dependency, author onboarding, README, repository guidance, source
inventory, content destinations, or smoke tests.
