# Security policy

## Supported versions

Security fixes are applied to the latest published Content Creator release.
Users should upgrade author workspaces to that release after reviewing the
workspace upgrade preview and passing downstream validation.

## Report a vulnerability privately

Use GitHub's private vulnerability reporting for security-sensitive reports.
Do not open a public issue containing exploit details, credentials, private
voice material, personal data, provider responses, or unpublished content.

Include the affected version, impact, reproduction conditions, and the
smallest safe example that demonstrates the issue. Do not include real secrets
or third-party personal data.

The maintainer will acknowledge a report as soon as practical, assess its
severity, and coordinate disclosure after a fix is available. No fixed
response or remediation time is guaranteed.

## Scope

Security reports may cover the Core package, release artifacts, dependency
handling, provider boundaries, diagnostics redaction, workspace isolation, or
unauthorised disclosure of repository-owned material.

Frozen lockfile installation, multi-version `pip-audit`, dependency review,
CodeQL, secret and malware scanning, release SBOMs, and artifact attestations
are complementary controls. They reduce known risks but do not prove that a
release is free of vulnerabilities.
