# Voice onboarding

Every new thin workspace begins with an explicit decision: derive a personal
voice from authorised writing, or begin with a neutral starter.

The system does not assume that a new author already has a usable archive, and
the assistant must not choose a route on the author's behalf.

## The checkpoint

A generated workspace stores:

```text
profiles/<voice-id>/onboarding.json
```

Its initial state is:

```json
{
  "status": "undecided",
  "strategy": null,
  "perspective_mode": "pending"
}
```

Before the first content request, chat guidance asks:

> Do you want to build a personalised voice from writing you can provide, or
> begin with the neutral Clear Professional Starter?

## Route A: source-derived voice

Select the route:

```bash
content-creator --workspace . voice onboard example-person-general \
  --strategy source-derived \
  --author-name "Example Person" \
  --selected-by "Example Person" \
  --use linkedin-post
```

This records the decision and creates an empty authorised voice work order. It
does not fabricate a candidate from no evidence.

Add writing and build:

```bash
content-creator --workspace . voice add-sources example-person-general \
  --sources voice-material/example-person-general/source-urls.txt \
  --documents voice-material/example-person-general/
content-creator --workspace . voice build example-person-general
```

Review, verify, and approve the candidate:

```bash
content-creator --workspace . voice status example-person-general
content-creator --workspace . voice show example-person-general
content-creator --workspace . voice verify example-person-general
content-creator --workspace . voice approve example-person-general \
  --approved-by "Example Person"
```

Only activation makes the candidate available to new runs. For the full
analysis and evaluation pipeline, see
[How Content Creator derives a voice](how-voice-is-derived.md).

## Route B: Clear Professional Starter

Select the starter:

```bash
content-creator --workspace . voice onboard example-person-general \
  --strategy starter \
  --author-name "Example Person" \
  --selected-by "Example Person" \
  --use linkedin-post
```

This deterministically activates a versioned starter. It does not call an LLM
or claim to have learned how Example Person writes.

The starter:

- uses plain, direct language;
- prefers clarity over cleverness;
- makes one principal argument at a time;
- uses concrete examples only when supplied or supported;
- distinguishes fact, inference, and opinion;
- avoids generic AI phrasing, manufactured drama, and inflated claims;
- never invents identity, experience, employment, anecdotes, measurements,
  organisational context, beliefs, or positions; and
- asks for author input when a personal view would materially change the
  piece.

Run metadata records:

```json
{
  "strategy": "starter",
  "evidence_status": "none",
  "perspectives_allowed": false,
  "template_id": "clear-professional"
}
```

## Why perspectives are disabled

A voice governs expression. A perspective represents something the author
believes, recommends, or interprets.

Without author evidence or a reviewed source-derived voice, automatically
selecting a perspective could manufacture the person's position. Core
therefore enforces the restriction in three places:

1. perspective management rejects starter voices;
2. runtime resolution forces `disabled`, even when workspace configuration
   says `automatic` or `explicit`; and
3. the run's `perspective-resolution.json` records
   `starter-voice-without-author-evidence`.

This is a Core integrity rule, not merely a chat instruction.

## Move from starter to source-derived

The choice is reversible without losing history.

1. Run `voice onboard` again with `--strategy source-derived`.
2. Add authorised writing, including approved pieces created while using the
   starter when the author chooses to use them as evidence.
3. Build and review the candidate.
4. Approve it explicitly.

The active starter remains usable while the candidate is under review. When
the source-derived candidate is activated:

- it receives the next immutable version;
- previous starter runs continue to resolve historically;
- the registry records `source-derived` and `author-sources`;
- perspective permission becomes `true`; and
- the workspace's configured perspective policy takes effect again.

Core never derives, activates, or changes the voice merely because enough
published content appears to exist.

## Inspect the state

```bash
content-creator --workspace . voice status example-person-general
content-creator --workspace . voice list
content-creator --workspace . voice verify example-person-general
```

`voice status` reports the onboarding record, candidate state, and active
registry entry together.
