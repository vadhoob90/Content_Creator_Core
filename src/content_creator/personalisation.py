"""Show author-owned agents, learning, voices, and perspectives in one view."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agent_resources import LEARNING_FILES, ROLE_FILES, STANDARD_TEMPLATE, AgentWorkspace
from .configuration import Configuration
from .voice_rejection import candidate_decision, list_rejections
from .voices import VoiceRegistry, load_voice_onboarding

VOICE_ROLES = {"writer", "critic", "learning-extractor"}
PERSPECTIVE_ROLES = {
    "researcher",
    "writer",
    "critic",
    "learning-extractor",
    "perspective-extractor",
    "perspective-evaluator",
}
LEARNING_ROLES = {"researcher", "writer", "critic"}
PACK_ROLES = {"writer", "critic"}


class PersonalisationInspector:
    """Build a read-only author-facing explanation of effective behaviour."""

    def __init__(self, root: Path):
        """Initialize the inspector for one workspace.

        Args:
            root (Path): Workspace root directory.

        Returns:
            None: The inspector stores resolved read-only collaborators in place.
        """
        self.root = root.resolve()
        self.agents = AgentWorkspace(self.root)
        self.registry = VoiceRegistry(self.root)

    def inspect(self) -> dict[str, Any]:
        """Return the complete personalisation projection.

        Returns:
            dict[str, Any]: Stable paths, effective layers, records, and decisions.
        """
        policy = Configuration(self.root).coordinator_policy
        voices = self._voices()
        return {
            "schema_version": "1.0",
            "workspace": str(self.root),
            "default_voice": policy.get("default_voice"),
            "default_pack": policy.get("default_pack"),
            "agents": self._agents(),
            "voices": voices,
            "repository_learnings": self._learning_scope(
                self.root / "learnings" / "memory.json", "repository"
            ),
            "prompt_layers": self._prompt_layers(),
            "navigation": {
                "guide": "PERSONALISATION.md",
                "agents": "agents/README.md",
                "profiles": "profiles/README.md",
                "repository_learnings": "learnings/README.md",
                "technical_setup": "docs/setup-and-technical-guide.md",
            },
        }

    def _agents(self) -> list[dict[str, Any]]:
        """Return role purposes, provenance, learning policy, and consumers.

        Returns:
            list[dict[str, Any]]: One effective-personalisation record per agent role.
        """
        difference = self.agents.diff_template(STANDARD_TEMPLATE)
        changed = set(difference["changed"])
        missing = set(difference["missing"])
        result = []
        for role, filename in ROLE_FILES.items():
            contract = self.agents.contract_path(role)
            repository_path = Path("agents") / filename
            if filename in missing:
                provenance = "missing"
            elif filename in changed:
                provenance = "customised"
            else:
                provenance = "core-starting-point"
            result.append(
                {
                    "role": role,
                    "purpose": self._contract_purpose(contract),
                    "personalisation": provenance,
                    "repository_file": str(repository_path),
                    "core_contract": f"core:contracts/roles/{filename}",
                    "learning_policy": (
                        f"agents/{LEARNING_FILES[role]}" if role in LEARNING_FILES else None
                    ),
                    "receives_voice": role in VOICE_ROLES,
                    "receives_perspectives": role in PERSPECTIVE_ROLES,
                    "receives_learnings": role in LEARNING_ROLES,
                    "receives_pack_instructions": role in PACK_ROLES,
                }
            )
        return result

    def _voices(self) -> list[dict[str, Any]]:
        """Return every discoverable voice and its effective author-owned state.

        Combine registry, onboarding, candidate, rejection, learning, and
        perspective records so an author need not infer state from directories.

        Returns:
            list[dict[str, Any]]: Voice records ordered by stable voice identifier.
        """
        registry = self.registry.list()
        voice_ids = set(registry)
        voice_ids.update(
            path.parent.name for path in (self.root / "profiles").glob("*/onboarding.json")
        )
        voice_ids.update(
            path.parent.parent.name
            for path in (self.root / "profiles").glob("*/candidate/manifest.json")
        )
        voice_ids.update(
            path.parents[2].name
            for path in (self.root / "profiles").glob("*/rejections/*/rejection-receipt.json")
        )
        result = []
        for voice_id in sorted(voice_ids):
            active = registry.get(voice_id)
            onboarding = load_voice_onboarding(self.root, voice_id)
            result.append(
                {
                    "voice_id": voice_id,
                    "display_name": (active or {}).get("display_name")
                    or (onboarding.display_name if onboarding else voice_id),
                    "active": self._active_voice(voice_id, active),
                    "candidate": candidate_decision(self.root, voice_id, active),
                    "rejections": list_rejections(self.root, voice_id),
                    "learnings": self._learning_scope(
                        self.root / "profiles" / voice_id / "learnings" / "memory.json",
                        "voice",
                    ),
                    "perspectives": self._perspectives(voice_id),
                    "paths": {
                        "voice": f"profiles/{voice_id}/",
                        "learnings": f"profiles/{voice_id}/learnings/memory.json",
                        "perspectives": f"profiles/{voice_id}/perspectives/",
                    },
                }
            )
        return result

    def _active_voice(self, voice_id: str, active: dict | None) -> dict[str, Any] | None:
        """Return the current registry-selected voice version.

        Args:
            voice_id (str): Stable selected voice identifier.
            active (dict | None): Registry entry, or ``None`` when unavailable.

        Returns:
            dict[str, Any] | None: Active version metadata and paths, when selected.
        """
        if not active:
            return None
        version = active.get("active_version")
        return {
            "status": active.get("status"),
            "version": version,
            "candidate_hash": active.get("candidate_hash"),
            "path": f"profiles/{voice_id}/versions/{version}/" if version else None,
            "manifest": (
                f"profiles/{voice_id}/versions/{version}/manifest.json" if version else None
            ),
        }

    def _learning_scope(self, path: Path, scope: str) -> dict[str, Any]:
        """Return actual principles and counts for one learning-memory scope.

        Args:
            path (Path): Learning-memory JSON file to inspect.
            scope (str): Human-readable repository or voice scope label.

        Returns:
            dict[str, Any]: Records, role/status counts, paths, and parse problems.
        """
        result: dict[str, Any] = {
            "scope": scope,
            "path": str(path.relative_to(self.root)),
            "counts": {},
            "records": [],
            "problems": [],
        }
        if not path.is_file():
            result["problems"].append("learning memory is missing")
            return result
        try:
            records = json.loads(path.read_text(encoding="utf-8")).get("records", [])
        except (json.JSONDecodeError, AttributeError) as error:
            result["problems"].append(str(error))
            return result
        for record in records:
            role = str(record.get("role", "unknown"))
            status = str(record.get("status", "unknown"))
            result["counts"].setdefault(role, {}).setdefault(status, 0)
            result["counts"][role][status] += 1
            result["records"].append(
                {
                    key: record.get(key)
                    for key in (
                        "id",
                        "role",
                        "status",
                        "scope",
                        "principle",
                        "evidence",
                        "voice_version",
                        "content_pack",
                    )
                }
            )
        return result

    def _perspectives(self, voice_id: str) -> dict[str, Any]:
        """Return approved and pending perspective contexts for one voice.

        Read both the active registry and candidate manifests because they have
        deliberately different approval semantics.

        Args:
            voice_id (str): Stable selected voice identifier.

        Returns:
            dict[str, Any]: Approved contexts, pending candidates, and registry path.
        """
        base = self.root / "profiles" / voice_id / "perspectives"
        registry_path = base / "registry.json"
        approved = []
        problems = []
        if registry_path.is_file():
            try:
                contexts = json.loads(registry_path.read_text(encoding="utf-8")).get("contexts", {})
                approved = [
                    {
                        "context_id": context_id,
                        "display_name": item.get("display_name", context_id),
                        "status": item.get("status"),
                        "version": item.get("active_version"),
                        "path": (
                            f"profiles/{voice_id}/perspectives/{context_id}/versions/"
                            f"{item.get('active_version')}/"
                        ),
                    }
                    for context_id, item in sorted(contexts.items())
                    if item.get("status") == "active"
                ]
            except (json.JSONDecodeError, AttributeError) as error:
                problems.append(str(error))
        pending = []
        for manifest_path in sorted(base.glob("*/candidate/manifest.json")):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                problems.append(f"{manifest_path.relative_to(self.root)}: {error}")
                continue
            if manifest.get("status") in {"candidate", "awaiting_approval"}:
                context_id = manifest_path.parents[1].name
                pending.append(
                    {
                        "context_id": context_id,
                        "display_name": manifest.get("display_name", context_id),
                        "status": manifest.get("status"),
                        "candidate_hash": manifest.get("candidate_hash"),
                        "path": str(manifest_path.parent.relative_to(self.root)),
                    }
                )
        return {
            "approved": approved,
            "pending": pending,
            "registry": str(registry_path.relative_to(self.root)),
            "problems": problems,
        }

    @staticmethod
    def _contract_purpose(path: Path) -> str:
        """Return the first explanatory paragraph from a Core role contract.

        Args:
            path (Path): Packaged Core role-contract path.

        Returns:
            str: First non-heading paragraph, or a neutral fallback description.
        """
        paragraphs = path.read_text(encoding="utf-8").split("\n\n")
        return next(
            (
                paragraph.replace("\n", " ").strip()
                for paragraph in paragraphs
                if not paragraph.startswith("#")
            ),
            "Core role contract",
        )

    @staticmethod
    def _prompt_layers() -> list[dict[str, Any]]:
        """Return the documented runtime composition order.

        Returns:
            list[dict[str, Any]]: Ordered prompt layers and their consuming roles.
        """
        return [
            {"order": 1, "layer": "core-harness", "roles": "all"},
            {"order": 2, "layer": "core-role-contract", "roles": "all"},
            {"order": 3, "layer": "repository-agent", "roles": "all"},
            {
                "order": 4,
                "layer": "repository-learning-policy",
                "roles": sorted(LEARNING_ROLES),
            },
            {"order": 5, "layer": "active-voice", "roles": sorted(VOICE_ROLES)},
            {
                "order": 6,
                "layer": "approved-perspectives",
                "roles": sorted(PERSPECTIVE_ROLES),
            },
            {
                "order": 7,
                "layer": "active-repository-and-voice-learnings",
                "roles": sorted(LEARNING_ROLES),
            },
            {"order": 8, "layer": "rubrics-and-pack-instructions", "roles": sorted(PACK_ROLES)},
        ]


def render_personalisation(report: dict[str, Any]) -> str:
    """Render the projection for an author reading a terminal.

    Favor direct answers and repository paths over internal implementation
    terminology, while retaining exact candidate decisions and valid actions.

    Args:
        report (dict[str, Any]): Personalisation projection.

    Returns:
        str: Human-readable explanation with direct repository paths.
    """
    lines = [
        "How this workspace is personalised",
        f"Default voice: {report.get('default_voice') or 'not selected'}",
        f"Default content pack: {report.get('default_pack') or 'not selected'}",
        "",
        "Your agents",
    ]
    for agent in report["agents"]:
        learning = (
            "receives role-matched active learning"
            if agent["receives_learnings"]
            else "no incremental learning"
        )
        lines.append(
            f"- {agent['role']}: {agent['personalisation']}; {learning}; {agent['repository_file']}"
        )
        lines.append(f"  {agent['purpose']}")
    lines.extend(["", "What your agents have learnt"])
    _append_learning_lines(lines, report["repository_learnings"], "Repository-wide")
    for voice in report["voices"]:
        lines.extend(["", f"Voice: {voice['display_name']} ({voice['voice_id']})"])
        active = voice["active"]
        if active:
            lines.append(
                f"- Active version: {active['version']} ({active['status']}); {active['path']}"
            )
        else:
            lines.append("- Active version: none")
        candidate = voice["candidate"]
        lines.append(f"- Candidate decision: {candidate['status']}")
        if candidate.get("candidate_hash"):
            lines.append(f"  Candidate hash: {candidate['candidate_hash']}")
        for action in candidate.get("actions", []):
            lines.append("  Valid action: content-creator " + " ".join(action))
        lines.append(f"- Rejected candidates: {len(voice['rejections'])}")
        _append_learning_lines(lines, voice["learnings"], "Voice-specific")
        approved = voice["perspectives"]["approved"]
        pending = voice["perspectives"]["pending"]
        lines.append(
            "- Approved perspectives: "
            + (", ".join(item["display_name"] for item in approved) if approved else "none")
        )
        lines.append(
            "- Pending perspectives: "
            + (", ".join(item["display_name"] for item in pending) if pending else "none")
        )
        lines.append(f"- Inspect voice and perspectives: {voice['paths']['voice']}")
    lines.extend(
        [
            "",
            "Effective prompt order",
            *[f"{item['order']}. {item['layer']}" for item in report["prompt_layers"]],
            "",
            "Guide: PERSONALISATION.md",
        ]
    )
    return "\n".join(lines)


def _append_learning_lines(lines: list[str], memory: dict[str, Any], label: str) -> None:
    """Append role-grouped learning principles to the human view.

    Args:
        lines (list[str]): Mutable rendered-output line collection.
        memory (dict[str, Any]): Learning scope containing inspectable records.
        label (str): Human-readable scope heading.

    Returns:
        None: The supplied line collection is extended in place.
    """
    lines.append(f"{label} learning ({memory['path']}):")
    active = [item for item in memory["records"] if item.get("status") == "active"]
    if not active:
        lines.append("- No active learning.")
        return
    for record in active:
        lines.append(f"- {record.get('role')}: {record.get('principle')}")
