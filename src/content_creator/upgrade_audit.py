"""Inspect downstream workspace compatibility during Core upgrades."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from .agent_resources import AgentWorkspace
from .configuration import Configuration
from .coordinator_models import operation as coordinator_operation
from .domain import RunEvent
from .health import WorkspaceHealth
from .packs import PackRegistry
from .production_store import production_run_store
from .storage import RunStore

logger = logging.getLogger(__name__)


def coordinator_upgrade_operations() -> List[Dict[str, Any]]:
    """Return chat-facing upgrade operations and approval boundaries.

    Returns:
        List[Dict[str, Any]]: Coordinator operation contracts for upgrade workflows.
    """
    return [
        coordinator_operation(
            "workspace.upgrade-preview",
            ["workspace", "upgrade", "--to", "<version>"],
        ),
        coordinator_operation(
            "workspace.upgrade-apply",
            ["workspace", "upgrade", "--to", "<version>", "--apply"],
            mutates=True,
            approval=True,
        ),
        coordinator_operation(
            "workspace.resolve-upgrade-run",
            ["workspace", "resolve-upgrade-run", "<run-id>", "--accept-current-pack"],
            mutates=True,
            approval=True,
        ),
    ]


def latest_upgrade_report(root: Path) -> Dict[str, Any] | None:
    """Return the most recent readable persisted upgrade audit.

    Args:
        root (Path): Downstream content workspace.

    Returns:
        Dict[str, Any] | None: Latest audit, or ``None`` when unavailable.
    """
    directory = root.resolve() / ".content-creator" / "upgrades"
    reports = sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime)
    if not reports:
        return None
    try:
        return json.loads(reports[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class UpgradeCompatibilityAudit:
    """Produce coordinator-ready upgrade compatibility findings."""

    def __init__(self, root: Path):
        """Initialize the compatibility audit.

        Args:
            root (Path): Downstream content workspace.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = root.resolve()
        self.packs = PackRegistry(self.root)

    def inspect(self) -> Dict[str, Any]:
        """Inspect workspace readiness without changing workspace state.

        Returns:
            Dict[str, Any]: Structured findings and chat-oriented summary data.
        """
        findings = [
            self._health_finding(),
            self._provider_finding(),
            self._runtime_finding(),
            self._agents_finding(),
            self._learning_finding(),
            self._idempotency_finding(),
            self._publication_finding(),
        ]
        runs = self._run_findings()
        counts = self._counts(runs)
        blocking_workspace = any(item["outcome"] == "blocking" for item in findings)
        return {
            "schema_version": "1.0",
            "dependency_update": "not_applied",
            "workspace_readiness": "blocking" if blocking_workspace else "compatible",
            "historical_run_compatibility": self._run_status(counts),
            "findings": findings,
            "historical_runs": runs,
            "counts": counts,
            "chat_summary": self._chat_summary(findings, counts),
            "decision_prompts": [
                self._decision_prompt(item)
                for item in runs
                if item["outcome"] == "decision_required"
            ],
        }

    def persist(self, report: Dict[str, Any], source: str, target: str) -> Path:
        """Persist an applied-upgrade audit for coordinator discovery.

        Args:
            report (Dict[str, Any]): Completed compatibility report.
            source (str): Previous Core version or ref.
            target (str): Applied Core version or ref.

        Returns:
            Path: Persisted report path.
        """
        directory = self.root / ".content-creator" / "upgrades"
        filename = "{}-to-{}.json".format(self._safe(source), self._safe(target))
        path = directory / filename
        RunStore._atomic_text(path, json.dumps(report, indent=2, ensure_ascii=False))
        self._persist_run_findings(report.get("historical_runs", []), source, target)
        return path

    def _persist_run_findings(
        self, findings: List[Dict[str, Any]], source: str, target: str
    ) -> None:
        """Persist run-level migration artifacts and visible lifecycle events.

        Args:
            findings (List[Dict[str, Any]]): Historical-run compatibility findings.
            source (str): Previous Core version or ref.
            target (str): Applied Core version or ref.

        Returns:
            None: Readable affected runs are updated in place.
        """
        store = production_run_store(self.root)
        for finding in findings:
            if finding["outcome"] not in {"automatically_migrated", "decision_required"}:
                continue
            try:
                state = store.load(finding["run_id"])
            except Exception as exc:
                logger.warning(
                    "Skipping run-level upgrade finding for %s: %s",
                    finding["run_id"],
                    exc,
                )
                continue
            event_name = (
                "legacy_pack_options_resolved"
                if finding["outcome"] == "automatically_migrated"
                else "pack_migration_decision_required"
            )
            detail = f"core={source}->{target}, pack={finding.get('pack', 'unknown')}"
            if not any(
                event.name == event_name and event.detail == detail for event in state.events
            ):
                state.events.append(RunEvent(name=event_name, detail=detail))
                store.save_state(state)
            store.write_artifact(
                state.id,
                "pack-migration.json",
                {"from": source, "to": target, **finding},
            )

    def _run_findings(self) -> List[Dict[str, Any]]:
        """Inspect every readable historical run against current packs.

        Returns:
            List[Dict[str, Any]]: Per-run compatibility decisions.
        """
        results: List[Dict[str, Any]] = []
        for path in sorted((self.root / "runs").glob("*/state.json")):
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
                order = state["work_order"]
                pack_id = order.get("content_pack") or "general-text"
                migrations = self.packs.override_compatibility(
                    pack_id, order.get("pack_options") or {}
                )
                conflicts = [item for item in migrations if item["outcome"] == "conflict"]
                compatible = [item for item in migrations if item["outcome"] == "compatible"]
                outcome = (
                    "decision_required"
                    if conflicts
                    else "automatically_migrated"
                    if compatible
                    else "compatible"
                )
                results.append(
                    {
                        "run_id": path.parent.name,
                        "run_status": state.get("status", "unknown"),
                        "pack": pack_id,
                        "outcome": outcome,
                        "migrations": migrations,
                        "publication_blocked": bool(conflicts),
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "run_id": path.parent.name,
                        "run_status": "unreadable",
                        "outcome": "blocking",
                        "publication_blocked": True,
                        "detail": str(exc),
                    }
                )
        return results

    def _health_finding(self) -> Dict[str, Any]:
        """Return configuration and required-resource health.

        Returns:
            Dict[str, Any]: Workspace health finding.
        """
        try:
            report = WorkspaceHealth(self.root).report()
            return self._finding(
                "configuration_and_resources",
                "compatible" if report["status"] == "ok" else "blocking",
                report,
            )
        except Exception as exc:
            return self._finding("configuration_and_resources", "blocking", str(exc))

    def _provider_finding(self) -> Dict[str, Any]:
        """Return effective provider selection readiness.

        Returns:
            Dict[str, Any]: Provider configuration finding.
        """
        try:
            provider = Configuration(self.root).default_provider
            detail: Any = {
                "provider": provider,
                "data_boundary": "provider receives only payloads selected for a run",
                "live_credentials_checked": False,
            }
            return self._finding("provider_and_privacy", "compatible", detail)
        except Exception as exc:
            return self._finding("provider_and_privacy", "blocking", str(exc))

    def _runtime_finding(self) -> Dict[str, Any]:
        """Return non-mutating runtime write-readiness checks.

        Returns:
            Dict[str, Any]: Runtime path permission finding.
        """
        paths = [self.root, self.root / "runs", self.root / ".content-creator"]
        checks = {
            str(path.relative_to(self.root) or Path(".")): self._writable(path) for path in paths
        }
        outcome = "compatible" if all(checks.values()) else "blocking"
        return self._finding("runtime_write_readiness", outcome, checks)

    def _agents_finding(self) -> Dict[str, Any]:
        """Return repository-agent preservation readiness.

        Returns:
            Dict[str, Any]: Agent resource finding.
        """
        status = AgentWorkspace(self.root).status()
        outcome = "compatible" if status["complete"] else "blocking"
        return self._finding("repository_agents", outcome, status)

    def _learning_finding(self) -> Dict[str, Any]:
        """Return learning-memory schema readability.

        Returns:
            Dict[str, Any]: Learning memory finding.
        """
        paths = sorted(self.root.glob("learnings/*.json")) + sorted(
            self.root.glob("profiles/*/learnings/*.json")
        )
        invalid = []
        for path in paths:
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                invalid.append(str(path.relative_to(self.root)))
        detail = {"records": len(paths), "invalid": invalid, "voice_scoped": True}
        return self._finding("learning_memory", "blocking" if invalid else "compatible", detail)

    def _idempotency_finding(self) -> Dict[str, Any]:
        """Return idempotency-index integrity without creating a database.

        Returns:
            Dict[str, Any]: Idempotency storage finding.
        """
        path = self.root / ".content-creator" / "idempotency.sqlite3"
        if not path.exists():
            return self._finding("idempotency", "compatible", {"index": "not_created"})
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            connection.close()
            return self._finding(
                "idempotency",
                "compatible" if integrity == "ok" else "blocking",
                {"integrity": integrity},
            )
        except sqlite3.Error as exc:
            return self._finding("idempotency", "blocking", str(exc))

    def _publication_finding(self) -> Dict[str, Any]:
        """Return publication and source inventory without exact-count assertions.

        Returns:
            Dict[str, Any]: Publication and source inventory finding.
        """
        publications = list((self.root / "content").glob("*/published/*"))
        sources = list((self.root / "sources").glob("**/*"))
        detail = {
            "publication_records": len([path for path in publications if path.is_file()]),
            "source_files": len([path for path in sources if path.is_file()]),
            "assertion_policy": "invariant_based",
        }
        return self._finding("publications_and_sources", "compatible", detail)

    @staticmethod
    def _finding(category: str, outcome: str, detail: Any) -> Dict[str, Any]:
        """Build one structured compatibility finding.

        Args:
            category (str): Audited compatibility area.
            outcome (str): Normalized compatibility outcome.
            detail (Any): Supporting structured or textual evidence.

        Returns:
            Dict[str, Any]: Structured finding.
        """
        return {"category": category, "outcome": outcome, "detail": detail}

    @staticmethod
    def _counts(runs: List[Dict[str, Any]]) -> Dict[str, int]:
        """Return counts for historical-run outcomes.

        Args:
            runs (List[Dict[str, Any]]): Per-run findings.

        Returns:
            Dict[str, int]: Count for every supported outcome.
        """
        names = ("compatible", "automatically_migrated", "decision_required", "blocking")
        return {name: sum(item["outcome"] == name for item in runs) for name in names}

    @staticmethod
    def _run_status(counts: Dict[str, int]) -> str:
        """Return the historical-run compatibility summary.

        Args:
            counts (Dict[str, int]): Aggregated run outcomes.

        Returns:
            str: Highest-severity historical-run status.
        """
        if counts["blocking"]:
            return "blocking"
        if counts["decision_required"]:
            return "decision_required"
        if counts["automatically_migrated"]:
            return "automatically_migrated"
        return "compatible"

    @staticmethod
    def _chat_summary(findings: List[Dict[str, Any]], counts: Dict[str, int]) -> List[str]:
        """Build concise coordinator-ready summary lines.

        Args:
            findings (List[Dict[str, Any]]): Workspace-level findings.
            counts (Dict[str, int]): Historical-run outcome counts.

        Returns:
            List[str]: Plain-language facts suitable for chat presentation.
        """
        blocked = [item["category"] for item in findings if item["outcome"] == "blocking"]
        return [
            "Workspace readiness: {}".format("needs attention" if blocked else "compatible"),
            "Historical runs: {} compatible, {} automatically migrated, {} need a "
            "decision, {} blocked".format(
                counts["compatible"],
                counts["automatically_migrated"],
                counts["decision_required"],
                counts["blocking"],
            ),
            "Blocking workspace checks: {}".format(", ".join(blocked) if blocked else "none"),
        ]

    @staticmethod
    def _decision_prompt(run: Dict[str, Any]) -> Dict[str, Any]:
        """Build the chat decision required for one conflicting run.

        Args:
            run (Dict[str, Any]): Conflicting historical-run finding.

        Returns:
            Dict[str, Any]: Coordinator decision prompt with old and current values.
        """
        return {
            "run_id": run["run_id"],
            "message": "This run contains legacy pack policy that differs from the current pack.",
            "differences": [item for item in run["migrations"] if item["outcome"] == "conflict"],
            "options": ["adopt_current_pack_and_revalidate", "leave_run_unchanged"],
        }

    @staticmethod
    def _writable(path: Path) -> bool:
        """Return whether a runtime path can accept writes without mutation.

        Args:
            path (Path): Runtime path or its not-yet-created descendant.

        Returns:
            bool: Whether the nearest existing ancestor is writable.
        """
        candidate = path
        while not candidate.exists() and candidate != candidate.parent:
            candidate = candidate.parent
        return candidate.is_dir() and os.access(candidate, os.W_OK | os.X_OK)

    @staticmethod
    def _safe(value: str) -> str:
        """Convert a version ref into a safe report filename component.

        Args:
            value (str): Version or immutable ref.

        Returns:
            str: Filesystem-safe component.
        """
        return "".join(character if character.isalnum() else "-" for character in value).strip("-")
