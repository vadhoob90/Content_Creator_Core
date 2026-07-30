from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .agent_resources import AgentWorkspace
from .storage import RunStore
from .workspace import scaffold_skills

IMMUTABLE_REF = re.compile(
    r"^(?:v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?|[0-9a-fA-F]{40})$"
)
DEPENDENCY = re.compile(
    r"content-creator\s*@\s*git\+"
    r"(?P<url>[^\"'\s@]+)"
    r"@(?P<ref>[^\"'\s,]+)"
)


class WorkspaceUpgradeError(RuntimeError):
    pass


class WorkspaceUpgrader:
    """Preview and apply a pinned, transactional downstream Core upgrade."""

    def __init__(
        self,
        root: Path,
        runner: Optional[Callable[[List[str]], subprocess.CompletedProcess]] = None,
    ):
        self.root = root.resolve()
        self.runner = runner or self._run

    def preview(self, target: str) -> Dict[str, Any]:
        self._validate_target(target)
        pyproject = self.root / "pyproject.toml"
        if not pyproject.is_file():
            raise WorkspaceUpgradeError("Missing workspace pyproject.toml")
        text = pyproject.read_text(encoding="utf-8")
        match = DEPENDENCY.search(text)
        if not match:
            raise WorkspaceUpgradeError(
                "pyproject.toml does not contain a pinned git content-creator dependency"
            )
        current = match.group("ref")
        url = match.group("url")
        dependency = "content-creator @ git+{}@{}".format(url, target)
        return {
            "schema_version": "1.0",
            "status": "preview",
            "workspace": str(self.root),
            "from": current,
            "to": target,
            "immutable_target": True,
            "dependency_before": match.group(0),
            "dependency_after": dependency,
            "lockfile": {
                "path": "uv.lock",
                "exists": (self.root / "uv.lock").exists(),
                "will_refresh": True,
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
        }

    def apply(self, target: str) -> Dict[str, Any]:
        report = self.preview(target)
        pyproject = self.root / "pyproject.toml"
        lockfile = self.root / "uv.lock"
        original_project = pyproject.read_text(encoding="utf-8")
        original_lock = (
            lockfile.read_text(encoding="utf-8") if lockfile.exists() else None
        )
        updated = DEPENDENCY.sub(report["dependency_after"], original_project, count=1)
        RunStore._atomic_text(pyproject, updated.rstrip())
        commands = [
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
        completed = []
        try:
            for command in commands:
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
            agents = AgentWorkspace(self.root).scaffold()
            skills = scaffold_skills(self.root)
        except Exception:
            RunStore._atomic_text(pyproject, original_project.rstrip())
            if original_lock is None:
                if lockfile.exists():
                    lockfile.unlink()
            else:
                RunStore._atomic_text(lockfile, original_lock.rstrip())
            raise
        report.update(
            {
                "status": "applied",
                "commands": completed,
                "scaffolded": {
                    "agents": agents["created"],
                    "skills": skills["created"],
                },
                "manual_follow_up": [
                    "Review agent and skill template differences.",
                    "Review and commit pyproject.toml and uv.lock deliberately.",
                ],
            }
        )
        return report

    @staticmethod
    def _validate_target(target: str) -> None:
        if not IMMUTABLE_REF.fullmatch(target):
            raise WorkspaceUpgradeError(
                "--to must be an immutable semantic version tag or full 40-character commit"
            )

    def _skill_changes(self) -> Dict[str, List[str]]:
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
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _run(self, command: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            command,
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
        )
