# ADR 0011: Readable components and control flow

- Status: Accepted
- Date: 2026-08-02

## Context

ADR 0010 limited production modules, but a module below 500 lines could still
contain a god function, a long conditional dispatcher, deep nesting, or opaque
names. These shapes force maintainers and coding agents to load unrelated logic
for a small change. A single hard threshold of 10 would also encourage needless
extraction around legitimate orchestration code.

## Decision

Core adopts two-tier readability constraints across `src/`, `scripts`, and
`tests`:

- modules: 300 implementation-line ideal, review through 400, hard maximum 500;
- functions: 40 implementation-line ideal, hard maximum 80;
- cyclomatic complexity: ideal 10, hard maximum 15;
- branches: ideal 8, hard maximum 12;
- statements: ideal 30, hard maximum 50;
- parameters: ideal 5, hard maximum 7; and
- nesting: ideal 2, hard maximum 4.

Route tables and dedicated handlers replace long conditional dispatch chains.
Extraction follows a real responsibility and reason to change. Exact generic
module and class names `data`, `item`, `manager`, and `utils` are prohibited;
local names using those words require contextual justification in review.
Comments explain why surprising policy exists, not what code visibly does.

Ruff enforces control-flow hard limits. The readability report enforces module,
function, signature, and generic top-level naming limits while reporting ideal
thresholds as non-blocking warnings.

Implementation counts exclude definition docstrings while reports retain
physical sizes. This 2026-08-05 clarification keeps documentation from consuming
the code budget without concealing overall file size.

## Consequences

Command dispatch, orchestration, workspace generation, voice building and
activation, perspectives, visual validation, and statistical scoring are split
into cohesive components behind stable façades. Future changes should normally
require reading a small handler and its contract rather than a congested central
module. Reviewers retain judgment near ideal thresholds, while hard limits stop
new god functions and monoliths from entering the codebase.
