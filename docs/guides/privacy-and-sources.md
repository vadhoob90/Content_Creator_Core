# Privacy and source handling

- Obtain authorisation before analysing a person's material.
- Keep original private documents outside tracked directories.
- Extracted text is stored under ignored `.voice-cache/<voice-id>/`.
- Versioned packages retain source metadata, hashes, attribution and minimal
  evidence; they do not need to retain complete private source text.
- A person mentioned in a source is not assumed to be its author.
- Uncertain attribution has zero voice weight until a human resolves it.
- Do not put provider credentials in briefs, profiles, logs or pack manifests.
- Deactivation prevents new unpinned use while preserving receipts and
  historical run context.

Before committing, inspect:

```bash
git status --short
git check-ignore .voice-cache/example-person/source-001.txt
```
