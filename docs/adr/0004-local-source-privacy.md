# ADR 0004: Local source privacy

Status: accepted.

Original writing may remain in an external local directory and is read in
place. Generated workspaces ignore uploaded files under `voice-material/`,
voice work orders containing local paths, and complete normalized source text
under `.voice-cache/`.

Versioned voice packages store content hashes, attribution, analysis outputs,
and privacy-safe `local-document:<filename>` references rather than absolute
local paths or complete source text. Public URL inventories may remain
trackable. This reduces accidental publication of private corpora while
keeping builds traceable. The repository owner remains responsible for source
authorisation and retention.
