# Create a thin content workspace

Use the workspace generator when a new author, client, team, or brand needs its
own Content Creator repository.

Do not clone Content Creator Core and delete reusable files. The generated
repository pins Core as a dependency and contains only the mutable editorial
material owned by that workspace.

## Install Core

Install the immutable `v1.19.0` release:

```bash
uv tool install content-creator==1.19.0
```

## Generate the repository

For a LinkedIn-oriented author workspace:

```bash
content-creator workspace create Content_Creator_Alice \
  --name "Content Creator Alice" \
  --author-name "Alice Example" \
  --voice-id alice-general \
  --voice-label "Alice — General" \
  --pack linkedin-post \
  --pack linkedin-article \
  --core-ref v1.19.0
```

Without `--pack`, the command enables `general-text`.

The generated workspace should pin the same registry version. Use an explicit
reviewed Git tag or commit only when consuming a private fork or diagnosing a
release:

```bash
content-creator workspace create Content_Creator_Alice \
  --author-name "Alice Example" \
  --core-source git \
  --core-ref 0123456789abcdef
```

Other useful options are:

```text
--agent-template standard
--perspective-mode automatic
--perspective-mode explicit
--perspective-mode disabled
--core-source registry
--core-source git
--core-url <private fork or canonical Core URL>
```

Relative destinations are resolved from the current directory. When the global
`--workspace` option is supplied, it acts as the base directory.

The generated main README names both the immutable Core revision and the exact
dependency declaration (for example, `content-creator==1.19.0`). That small
section is marked as generator-owned so a later `workspace upgrade --apply`
can refresh it without replacing the rest of the workspace's README.

## Generated repository

The result is a thin consumer:

```text
Content_Creator_Alice/
├── README.md
├── PERSONALISATION.md
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
│   ├── README.md
│   └── memory.json
├── profiles/
│   ├── README.md
│   ├── registry.json
│   └── alice-general/
│       ├── README.md
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
├── docs/
│   └── setup-and-technical-guide.md
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

The generated root README is an author-facing quick start. It signposts
`PERSONALISATION.md`, agent definitions, learning memory, profiles, and the
separate technical setup guide so ordinary content creation does not begin
with package-manager detail.

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
uv run content-creator --workspace . setup
uv run pytest
```

If a corporate TLS-intercepting proxy causes uv to report `UnknownIssuer`, retry
the sync with the operating system certificate store:

```bash
uv sync --dev --native-tls
```

The generator includes this recovery command in its machine-readable next
steps so a first-time author does not have to infer it from a failed install.

The generated README begins with the four-step `setup` view. The author chooses
whether to derive a writing style from previous work or begin with the neutral
Clear Professional Starter, then explicitly confirms a verified model
connection. Core infers the generated author, voice identifier, and enabled
packs rather than asking the author to copy them. The underlying
`profiles/alice-general/onboarding.json` remains `undecided` until that choice
is recorded.

For the fastest first draft:

```bash
uv run content-creator --workspace . setup starter
uv run content-creator --workspace . setup
```

The second command shows only provider choices currently available or
configured. Select one exact returned action. API and Bedrock routes require
`--confirm-api-billing`; native subscription routes never silently fall back to
API billing.

The lower-level commands below remain available for technical and automation
use.

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

For local writing, point directly to any directory on the author's computer:

```bash
uv run content-creator --workspace . voice add-sources alice-general \
  --documents "/absolute/path/to/my-writing"
```

Supported Markdown, text, DOCX, PDF, and HTML files are discovered recursively.
They are read in place rather than copied into the Git repository. Operational
work orders and extracted cache text are ignored; versioned source indexes use
privacy-safe local references rather than absolute filesystem paths.

Then follow the generated README to build, review, verify, and approve the
candidate.

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
