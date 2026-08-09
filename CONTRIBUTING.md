# Contributing

## Issues are welcome

Bug reports and feature requests are welcome through GitHub Issues. Before
opening an issue, please search existing issues and provide enough information
for the maintainers to reproduce or assess the request.

## External code contributions are closed

This project does not accept external code contributions or pull requests at
this time. Only the designated maintainers make changes to this repository.

Please do not submit patches, source-code implementations, or substantial
copyrightable code through issues, discussions, email, or pull requests.
Unsolicited code may be closed or removed without review and will not be
incorporated into the project.

Opening an issue does not transfer ownership of your submission to the project.
Keep issue submissions limited to problem reports, reproduction steps, expected
behaviour, and high-level feature suggestions that you have the right to share.

The AGPL permits anyone to fork and modify the project under its terms. This
policy governs only what the maintainers accept into this repository; it does
not restrict rights granted by the licence.

## Maintainer guardrails

Designated maintainers start with the
[architecture and development guardrails](docs/core/architecture-guardrails.md).
They signpost the enforced module and function limits, complexity and naming
rules, and the existing TDD, compatibility, schema, operational, security,
documentation, and release controls. A Core change is incomplete until the
applicable guidance and documentation are updated in the same pull request.

## Maintainer structural walkthrough

1. Identify the observable CLI, Python, generated-workspace, or persisted-data
   contract affected by the change.
2. Begin at the owning façade (`orchestrator.py`, `voice_builder.py`, or
   `voice_ml/`) and follow only the named subsystem it composes.
3. Add a behavior or characterization test before moving responsibilities.
4. Prefer functions for stateless transformations, classes for owned state or
   lifecycle, and protocols only where multiple implementations already exist.
5. Run the architecture report and review its advisory single-importer and
   cross-file-inheritance signals; they prompt judgment and do not fail CI.
6. Update the module map, extension example, ADR, and compatibility notes when
   the normal reading path or a supported seam changes.
7. Classify semantic-release impact and critical-path risk. Run the mutation
   scope selected by the
   [mutation-testing policy](docs/core/mutation-testing-baseline.md), and record
   every accepted survivor with an owner, expiry, rationale, and follow-up.

Worked provider, lifecycle-stage, and content-pack paths are linked from
[Extending Core](docs/guides/extending-core.md).

## Security reports

Do not include credentials, private data, or exploitable secrets in a public
issue. If GitHub private vulnerability reporting is enabled for the repository,
use that facility for security-sensitive reports. See the
[security policy](SECURITY.md) for supported versions, scope, and reporting
expectations.
