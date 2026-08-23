"""Scaffold additive downstream guidance for voice and Core upgrades."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .storage import RunStore

UPGRADE_OPTIONS_START = "<!-- content-creator-upgrade-options:start -->"
UPGRADE_OPTIONS_END = "<!-- content-creator-upgrade-options:end -->"

UPGRADE_OPTIONS_BLOCK = """{start}
## Upgrade options

- **Upgrade Core** to adopt a newer dependency: preview with
  `content-creator --workspace . workspace upgrade --to <tag>`.
- **Add runtime learning** when feedback should guide later runs without changing
  the immutable voice.
- **Evolve the voice** with `voice upgrade-plan <voice-id>`. Incremental mode is
  the default and analyses only new authorised evidence plus reviewed learning.
- **Reanalyse the full corpus** only with explicit `--mode full-corpus`; review
  provider, cost, and privacy implications first.
- **Replace the voice completely** only through the separate, exceptional
  `voice rebuild <voice-id> --full-regenerate` path.
- A neutral starter is not evidence of the author's voice. Replacing it with a
  first source-derived voice is a reviewed strategy transition.

See [How to evolve my voice](docs/how-to-evolve-my-voice.md).
{end}""".format(start=UPGRADE_OPTIONS_START, end=UPGRADE_OPTIONS_END)

HOW_TO_EVOLVE_VOICE = """# How to evolve my voice

Core dependency upgrades, runtime learning, and immutable voice upgrades are
different operations.

## Default: incremental evolution

Run `content-creator --workspace . voice upgrade-plan <voice-id>`. The plan
compares canonical source and publication hashes with the active version, shows
new evidence and active learning, and creates a learning-selection template.
Review every disposition, then run `voice upgrade`, inspect `voice diff`, and
approve the exact candidate with `voice approve`.

Incremental mode does not resend the historical corpus. It combines persisted
baseline measurements with measurements from the evidence delta.

## Full-corpus reanalysis

Use `--mode full-corpus` when attribution, historical evidence, or the analysis
framework materially changed. This can transmit the complete authorised corpus
to the selected provider and therefore requires an explicit sharing decision.
The approved baseline still has precedence unless evidenced changes are reviewed.

## Full replacement

`voice rebuild <voice-id> --full-regenerate` discards baseline precedence. It is
not a routine upgrade and must be requested and approved explicitly.

## Learning boundary

Active learning is never copied automatically into linguistic voice. Research,
perspectives, visual preferences, and repository-agent policy remain in their
separate lifecycles. Activation freezes the prior version's learning epoch and
creates a fresh epoch for the new immutable version.
"""


class WorkspaceUpgradeDocumentation:
    """Preview and add generator-owned downstream upgrade documentation."""

    def __init__(self, root: Path):
        """Initialize additive documentation scaffolding.

        Args:
            root (Path): Downstream workspace root.

        Returns:
            None: The root is retained for preview and apply.
        """
        self.root = root.resolve()

    def preview(self) -> dict[str, Any]:
        """Return exact additive documentation changes without writing files.

        Returns:
            dict[str, Any]: Managed blocks, new files, and manual follow-up paths.
        """
        readme = self.root / "README.md"
        text = readme.read_text(encoding="utf-8") if readme.is_file() else ""
        return {
            "main_readme": {
                "path": "README.md",
                "action": "update-managed-block"
                if UPGRADE_OPTIONS_START in text
                else "append-managed-block",
                "describes": [
                    "Core dependency upgrade",
                    "runtime learning",
                    "incremental voice evolution",
                    "full-corpus reanalysis",
                    "full replacement",
                    "starter-neutral transition",
                ],
            },
            "guide": {
                "path": "docs/how-to-evolve-my-voice.md",
                "action": (
                    "preserve-existing"
                    if (self.root / "docs/how-to-evolve-my-voice.md").exists()
                    else "create"
                ),
            },
            "manual_follow_up": self._manual_follow_up(),
        }

    def apply(self) -> dict[str, Any]:
        """Append the managed README block and create a missing detailed guide.

        Returns:
            dict[str, Any]: Created, updated, preserved, and manual-follow-up paths.
        """
        created: list[str] = []
        updated: list[str] = []
        preserved: list[str] = []
        readme = self.root / "README.md"
        original = readme.read_text(encoding="utf-8") if readme.is_file() else ""
        revised = update_upgrade_options(original)
        RunStore._atomic_text(readme, revised.rstrip())
        (updated if original else created).append("README.md")
        guide = self.root / "docs/how-to-evolve-my-voice.md"
        if guide.exists():
            preserved.append("docs/how-to-evolve-my-voice.md")
        else:
            RunStore._atomic_text(guide, HOW_TO_EVOLVE_VOICE.rstrip())
            created.append("docs/how-to-evolve-my-voice.md")
        return {
            "created": created,
            "updated": updated,
            "preserved": preserved,
            "manual_follow_up": self._manual_follow_up(),
        }

    def _manual_follow_up(self) -> list[str]:
        """Return customised downstream files requiring an author-owned link.

        Returns:
            list[str]: Exact existing files that do not have a managed update block.
        """
        candidates = [
            "PERSONALISATION.md",
            "profiles/README.md",
            "docs/setup-and-technical-guide.md",
            "AGENTS.md",
        ]
        candidates.extend(
            str(path.relative_to(self.root))
            for path in sorted((self.root / "profiles").glob("*/README.md"))
        )
        return [
            "Add a link to docs/how-to-evolve-my-voice.md in {}".format(path)
            for path in candidates
            if (self.root / path).is_file()
            and "how-to-evolve-my-voice.md" not in (self.root / path).read_text(encoding="utf-8")
        ]


def update_upgrade_options(text: str) -> str:
    """Update or append the generator-owned main README upgrade block.

    Args:
        text (str): Existing downstream README prose.

    Returns:
        str: README with exactly one managed upgrade-options block.
    """
    start = text.find(UPGRADE_OPTIONS_START)
    end = text.find(UPGRADE_OPTIONS_END)
    if start >= 0 and end >= start:
        end += len(UPGRADE_OPTIONS_END)
        return text[:start] + UPGRADE_OPTIONS_BLOCK + text[end:]
    return text.rstrip() + "\n\n" + UPGRADE_OPTIONS_BLOCK + "\n"
