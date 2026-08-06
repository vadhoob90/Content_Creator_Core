"""Provide upgrade capabilities."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .agent_resources import AgentWorkspace
from .storage import RunStore
from .upgrade_audit import UpgradeCompatibilityAudit
from .workspace import scaffold_skills, update_readme_core_dependency

IMMUTABLE_REF = re.compile(r"^(?:v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?|[0-9a-fA-F]{40})$")
GIT_DEPENDENCY = re.compile(
    r"content-creator\s*@\s*git\+"
    r"(?P<url>[^\"'\s@]+)"
    r"@(?P<ref>[^\"'\s,]+)"
)
REGISTRY_DEPENDENCY = re.compile(
    r"content-creator\s*==\s*(?P<version>\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)"
)


class WorkspaceUpgradeError(RuntimeError):
    """Report workspace upgrade failures."""

    pass


class WorkspaceUpgrader:
    """Preview and apply a pinned, transactional downstream Core upgrade."""

    def __init__(
        self,
        root: Path,
        runner: Optional[Callable[[List[str]], subprocess.CompletedProcess]] = None,
    ):
        """Initialize the workspace upgrader with its required state and collaborators.

        Args:
            root (Path): The workspace root directory.
            runner (Optional[Callable[[List[str]], subprocess.CompletedProcess]]): The agent
                or command runner used to execute the operation. Defaults to ``None``.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = root.resolve()
        self.runner = runner or self._run

    def preview(self, target: str) -> Dict[str, Any]:
        """Return the preview.

        Compare the pinned Core version and generator-owned files with the requested target
        before any workspace mutation occurs.

        Args:
            target (str): The target text processed when preview.

        Returns:
            Dict[str, Any]: The structured resulting data for preview.

        Raises:
            WorkspaceUpgradeError: If the workspace upgrade operation cannot complete.
        """
        self._validate_target(target)
        pyproject = self.root / "pyproject.toml"
        if not pyproject.is_file():
            raise WorkspaceUpgradeError("Missing workspace pyproject.toml")
        text = pyproject.read_text(encoding="utf-8")
        git_match = GIT_DEPENDENCY.search(text)
        registry_match = REGISTRY_DEPENDENCY.search(text)
        match = git_match or registry_match
        if not match:
            raise WorkspaceUpgradeError(
                "pyproject.toml does not contain a pinned content-creator dependency"
            )
        if git_match:
            current = git_match.group("ref")
            dependency = "content-creator @ git+{}@{}".format(git_match.group("url"), target)
            source = "git"
        else:
            assert registry_match is not None
            current = "v{}".format(registry_match.group("version"))
            dependency = "content-creator=={}".format(target.removeprefix("v"))
            source = "registry"
        compatibility = UpgradeCompatibilityAudit(self.root).inspect()
        compatibility.update(
            {
                "dependency_update": "preview",
                "from": current,
                "to": target,
            }
        )
        return {
            "schema_version": "1.0",
            "status": "preview",
            "workspace": str(self.root),
            "from": current,
            "to": target,
            "source": source,
            "immutable_target": True,
            "dependency_before": match.group(0),
            "dependency_after": dependency,
            "lockfile": {
                "path": "uv.lock",
                "exists": (self.root / "uv.lock").exists(),
                "will_refresh": True,
            },
            "readme": {
                "path": "README.md",
                "managed_core_dependency": self._readme_is_managed(),
            },
            "template_changes": {
                "agents": AgentWorkspace(self.root).diff_template(),
                "skills": self._skill_changes(),
                "policy": (
                    "Missing packaged files may be added; repository-owned files "
                    "are never overwritten."
                ),
            },
            "preserved": [
                "agents/",
                "content/",
                "learnings/",
                "profiles/",
                "voice-material/",
                "repository policy and configuration",
            ],
            "validation": [
                "content-creator doctor",
                "content-creator voice verify-all",
                "pytest",
            ],
            "apply_command": [
                "workspace",
                "upgrade",
                "--to",
                target,
                "--apply",
            ],
            "compatibility": compatibility,
        }

    def apply(self, target: str) -> Dict[str, Any]:
        """Apply the workspace upgrader workflow.

        Validate the preview, update only generator-owned dependency blocks transactionally,
        and restore originals if validation fails.

        Args:
            target (str): The target text processed when apply.

        Returns:
            Dict[str, Any]: The structured resulting data for apply.
        """
        report = self.preview(target)
        pyproject = self.root / "pyproject.toml"
        lockfile = self.root / "uv.lock"
        original_project = pyproject.read_text(encoding="utf-8")
        original_lock = lockfile.read_text(encoding="utf-8") if lockfile.exists() else None
        readme = self.root / "README.md"
        original_readme = readme.read_text(encoding="utf-8") if readme.exists() else None
        before = report["dependency_before"]
        updated = original_project.replace(before, report["dependency_after"], 1)
        RunStore._atomic_text(pyproject, updated.rstrip())
        readme_updated = False
        if original_readme is not None:
            updated_readme, readme_updated = update_readme_core_dependency(
                original_readme,
                target,
                report["dependency_after"],
            )
            if readme_updated:
                RunStore._atomic_text(readme, updated_readme.rstrip())
        completed = self._validate_upgrade(
            pyproject,
            lockfile,
            readme,
            original_project,
            original_lock,
            original_readme,
            readme_updated,
        )
        agents = AgentWorkspace(self.root).scaffold()
        skills = scaffold_skills(self.root)
        compatibility = UpgradeCompatibilityAudit(self.root).inspect()
        compatibility.update(
            {
                "dependency_update": "applied",
                "from": report["from"],
                "to": target,
            }
        )
        audit_path = UpgradeCompatibilityAudit(self.root).persist(
            compatibility, report["from"], target
        )
        report.update(
            {
                "status": "applied",
                "commands": completed,
                "scaffolded": {
                    "agents": agents["created"],
                    "skills": skills["created"],
                },
                "readme_updated": readme_updated,
                "compatibility": compatibility,
                "compatibility_report": str(audit_path.relative_to(self.root)),
                "manual_follow_up": [
                    "Review agent and skill template differences.",
                    "Review and commit pyproject.toml and uv.lock deliberately.",
                ],
            }
        )
        return report

    def _validation_commands(self) -> List[List[str]]:
        """Return the validation commands.

        Returns:
            List[List[str]]: The resulting validation commands values in their documented
                order.
        """
        return [
            ["uv", "lock", "--upgrade-package", "content-creator"],
            [
                "uv",
                "run",
                "content-creator",
                "--workspace",
                str(self.root),
                "doctor",
            ],
            [
                "uv",
                "run",
                "content-creator",
                "--workspace",
                str(self.root),
                "voice",
                "verify-all",
            ],
            ["uv", "run", "pytest"],
        ]

    def _validate_upgrade(
        self,
        pyproject: Path,
        lockfile: Path,
        readme: Path,
        original_project: str,
        original_lock: Optional[str],
        original_readme: Optional[str],
        readme_updated: bool,
    ) -> List[Dict[str, Any]]:
        """Validate the upgrade.

        Args:
            pyproject (Path): The filesystem path containing the pyproject.
            lockfile (Path): The filesystem path containing the lockfile.
            readme (Path): The filesystem path containing the readme.
            original_project (str): The original project text processed when validate
                upgrade.
            original_lock (Optional[str]): The original lock text processed when validate
                upgrade.
            original_readme (Optional[str]): The original readme text processed when
                validate upgrade.
            readme_updated (bool): Whether readme updated behavior is enabled.

        Returns:
            List[Dict[str, Any]]: The validated upgrade values in their documented order.

        Raises:
            WorkspaceUpgradeError: If the workspace upgrade operation cannot complete.
        """
        completed = []
        try:
            for command in self._validation_commands():
                result = self.runner(command)
                completed.append(
                    {
                        "command": command,
                        "returncode": result.returncode,
                        "stdout": result.stdout.strip(),
                        "stderr": result.stderr.strip(),
                    }
                )
                if result.returncode:
                    raise WorkspaceUpgradeError(
                        "Upgrade validation failed: {}".format(" ".join(command))
                    )
        except Exception:
            RunStore._atomic_text(pyproject, original_project.rstrip())
            if original_lock is None:
                if lockfile.exists():
                    lockfile.unlink()
            else:
                RunStore._atomic_text(lockfile, original_lock.rstrip())
            if original_readme is not None and readme_updated:
                RunStore._atomic_text(readme, original_readme.rstrip())
            raise
        return completed

    def _readme_is_managed(self) -> bool:
        """Return the readme is managed.

        Returns:
            bool: Whether readme is managed satisfies the documented condition.
        """
        readme = self.root / "README.md"
        if not readme.is_file():
            return False
        _, managed = update_readme_core_dependency(
            readme.read_text(encoding="utf-8"),
            "v0.0.0",
            "content-creator==0.0.0",
        )
        return managed

    @staticmethod
    def _validate_target(target: str) -> None:
        """Validate the target.

        Args:
            target (str): The target text processed when validate target.

        Returns:
            None: The callable updates target state and returns no value.

        Raises:
            WorkspaceUpgradeError: If the workspace upgrade operation cannot complete.
        """
        if not IMMUTABLE_REF.fullmatch(target):
            raise WorkspaceUpgradeError(
                "--to must be an immutable semantic version tag or full 40-character commit"
            )

    def _skill_changes(self) -> Dict[str, List[str]]:
        """Return the skill changes.

        Returns:
            Dict[str, List[str]]: The structured resulting data for skill changes.
        """
        source_root = Path(__file__).with_name("resources") / "skills"
        destination_root = self.root / ".agents" / "skills"
        missing: List[str] = []
        changed: List[str] = []
        unchanged: List[str] = []
        for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
            relative = source.relative_to(source_root)
            destination = destination_root / relative
            name = str(Path(".agents") / "skills" / relative)
            if not destination.exists():
                missing.append(name)
            elif self._digest(source) != self._digest(destination):
                changed.append(name)
            else:
                unchanged.append(name)
        return {
            "missing": missing,
            "changed": changed,
            "unchanged": unchanged,
        }

    @staticmethod
    def _digest(path: Path) -> str:
        """Return the digest.

        Args:
            path (Path): The filesystem path to inspect or update.

        Returns:
            str: The resulting text for digest.
        """
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _run(self, command: List[str]) -> subprocess.CompletedProcess:
        """Run the workspace upgrader workflow.

        Args:
            command (List[str]): The command name or invocation to execute.

        Returns:
            subprocess.CompletedProcess: The completed subprocess result with exit status
                and captured output.
        """
        return subprocess.run(
            command,
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
        )
