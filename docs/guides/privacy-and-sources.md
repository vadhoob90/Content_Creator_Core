# Privacy and source handling

- Obtain authorisation before analysing a person's material.
- Prefer pointing `--documents` at an external local directory. Core reads
  supported files recursively in place and does not upload or copy them.
- Original documents placed under `voice-material/` are ignored by generated
  workspaces. Only the public `source-urls.txt` inventory is trackable by
  default.
- Voice work orders are ignored because they may contain absolute local paths.
- Extracted text is stored under ignored `.voice-cache/<voice-id>/`.
- Versioned packages retain source metadata, hashes, attribution and minimal
  evidence. Local locators are reduced to `local-document:<filename>` rather
  than retaining an absolute filesystem path.
- A person mentioned in a source is not assumed to be its author.
- Uncertain attribution has zero voice weight until a human resolves it.
- Do not put provider credentials in briefs, profiles, logs or pack manifests.
- Deactivation prevents new unpinned use while preserving receipts and
  historical run context.
- Approved perspective entries may reveal personal or professional positions
  and are Git-tracked by design. Review statements, evidence excerpts, and
  counterpositions before committing them.
- Keep confidential interview notes out of perspective provenance. Store a
  minimal reference or approved excerpt rather than the full private source.
- Perspective proposal queues remain inactive and are excluded from automatic
  CI, but they are not encrypted storage.

Before committing, inspect:

```bash
git status --short
git check-ignore .voice-cache/example-person/source-001.txt
git check-ignore profiles/example-person/work-order.json
git check-ignore voice-material/example-person/private-draft.docx
```
