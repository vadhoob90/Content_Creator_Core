# Content-pack authoring

Create a pack that extends the single `general-text` base:

```bash
content-creator pack create internal-briefing --extends general-text
content-creator pack validate internal-briefing
content-creator pack show internal-briefing --resolved
```

A pack owns its format, destination, defaults, prompts, rubric additions and
validators. It may request capability profiles but cannot name provider models,
select credentials, activate voices, or remove the base integrity validators.

Resolution order is deterministic:

```text
general-text → one specialised pack → schema-approved run overrides
```

Unknown overrides, inheritance cycles, multiple base levels, invalid word
ranges and destinations outside the repository fail before a run is created.
Add replay cases for each supported research route and an isolation test proving
that another pack does not receive the new rules.
