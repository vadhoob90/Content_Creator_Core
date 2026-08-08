"""Preserve approved voice guidance during evidence-backed evolution."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from .storage import RunStore
from .versioned_artifacts import hash_file, hash_json, verify_components
from .voice_build.models import VoiceBuildError
from .voice_models import VoiceManifest, VoicePattern, VoiceStatus


class VoiceEvolutionAction(str, Enum):
    """Enumerate supported semantic voice-change classifications."""

    RETAIN = "retain"
    ADD = "add"
    MODIFY = "modify"
    SUPERSEDE = "supersede"
    REMOVE = "remove"


class VoiceEvolutionProposal(BaseModel):
    """Represent one explicit evidence-backed voice change proposal."""

    action: VoiceEvolutionAction
    target_id: Optional[str] = None
    replacement: Optional[VoicePattern] = None
    evidence_source_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)
    rationale: str


class VoiceEvolutionChangeSet(BaseModel):
    """Represent author-supplied proposals applied to an active baseline."""

    schema_version: str = "1.0"
    changes: list[VoiceEvolutionProposal] = Field(default_factory=list)


class VoiceEvolutionRecord(BaseModel):
    """Record one deterministic semantic difference from active guidance."""

    guidance_id: str
    replacement_id: Optional[str] = None
    provenance: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    rationale: str


class VoiceEvolutionDelta(BaseModel):
    """Persist a deterministic active-to-candidate semantic delta."""

    schema_version: str = "1.0"
    mode: str
    baseline_version: str
    baseline_candidate_hash: str
    baseline_manifest_hash: str
    generated_evidence_hash: str
    change_set_hash: Optional[str] = None
    retained: list[VoiceEvolutionRecord] = Field(default_factory=list)
    added: list[VoiceEvolutionRecord] = Field(default_factory=list)
    modified: list[VoiceEvolutionRecord] = Field(default_factory=list)
    superseded: list[VoiceEvolutionRecord] = Field(default_factory=list)
    removed: list[VoiceEvolutionRecord] = Field(default_factory=list)


@dataclass
class EvolutionResult:
    """Return merged artifacts needed by the remaining build pipeline."""

    profile: str
    constraints: dict[str, Any]
    rubric: dict[str, Any]
    patterns: list[VoicePattern]


class VoiceEvolution:
    """Apply safe active-baseline preservation to generated voice artifacts."""

    artifact_name = "voice-evolution.json"

    def __init__(
        self,
        root: Path,
        voice_id: str,
        full_regenerate: bool = False,
        change_set_path: Optional[Path] = None,
    ):
        """Resolve the immutable baseline and requested evolution mode.

        Args:
            root (Path): Workspace root.
            voice_id (str): Voice whose candidate is being built.
            full_regenerate (bool): Explicitly replace active guidance. Defaults to
                ``False``.
            change_set_path (Optional[Path]): Explicit semantic changes to propose.
                Defaults to ``None``.

        Returns:
            None: The service is initialized in place.

        Raises:
            VoiceBuildError: If active evidence or requested changes are invalid.
        """
        self.root = root.resolve()
        self.voice_id = voice_id
        self.baseline_dir, self.baseline = self._baseline()
        self.change_set, self.change_set_hash = self._load_changes(change_set_path)
        if full_regenerate and self.change_set is not None:
            raise VoiceBuildError("--full-regenerate cannot be combined with --change-set")
        if self.baseline is None and self.change_set is not None:
            raise VoiceBuildError("A voice change set requires an active baseline")
        self.mode = (
            "initial"
            if self.baseline is None
            else "full-regenerate"
            if full_regenerate
            else "evolve"
        )
        self.delta: Optional[VoiceEvolutionDelta] = None

    @property
    def baseline_version(self) -> Optional[str]:
        """Return the active baseline version when evolution is applicable.

        Returns:
            Optional[str]: Immutable baseline version or ``None`` for an initial build.
        """
        return self.baseline.version if self.baseline else None

    @property
    def baseline_candidate_hash(self) -> Optional[str]:
        """Return the active baseline candidate hash when available.

        Returns:
            Optional[str]: Baseline candidate hash or ``None`` for an initial build.
        """
        return self.baseline.candidate_hash if self.baseline else None

    @property
    def delta_hash(self) -> Optional[str]:
        """Return the written semantic delta hash when available.

        Returns:
            Optional[str]: Candidate delta artifact hash or ``None``.
        """
        return hash_json(self.delta.model_dump(mode="json")) if self.delta is not None else None

    def apply(self, candidate: Path) -> EvolutionResult:
        """Preserve active guidance while applying generated evidence.

        Args:
            candidate (Path): Staging candidate containing regenerated evidence.

        Returns:
            EvolutionResult: Final profile, constraints, rubric, and patterns.

        """
        generated = self._artifacts(candidate)
        if self.baseline is None:
            return generated
        baseline = self._artifacts(self._required_baseline_dir())
        if self.mode == "full-regenerate":
            self.delta = self._replacement_delta(candidate, baseline.patterns, generated.patterns)
            self._write_delta(candidate)
            return generated
        result = self._evolve(candidate, baseline, generated)
        self._write_result(candidate, result)
        self._write_delta(candidate)
        return result

    def regression_evaluation(self, candidate: Path) -> dict[str, Any]:
        """Return regression checks separately from standalone candidate quality.

        Compare protected structured artifacts and pattern identifiers with the immutable
        baseline while recognizing removals that have an explicit semantic delta record.

        Args:
            candidate (Path): Final staged candidate artifacts.

        Returns:
            dict[str, Any]: Deterministic active-baseline regression report.
        """
        if self.baseline is None:
            return {"applicable": False, "passed": True, "mode": "initial"}
        if self.mode == "full-regenerate":
            return {
                "applicable": True,
                "passed": True,
                "mode": self.mode,
                "baseline_version": self.baseline.version,
                "explicit_replacement": True,
                "unrecorded_losses": [],
            }
        baseline = self._artifacts(self._required_baseline_dir())
        current = self._artifacts(candidate)
        explained = (
            {
                item.guidance_id
                for group in (self.delta.modified, self.delta.superseded, self.delta.removed)
                for item in group
            }
            if self.delta
            else set()
        )
        baseline_ids = {item.id for item in baseline.patterns}
        current_ids = {item.id for item in current.patterns}
        losses = sorted(baseline_ids - current_ids - explained)
        checks = {
            "profile_baseline_preserved": current.profile.startswith(baseline.profile.rstrip()),
            "constraints_preserved": self._contains(current.constraints, baseline.constraints),
            "rubric_preserved": self._contains(current.rubric, baseline.rubric),
            "pattern_losses_recorded": not losses,
        }
        return {
            "applicable": True,
            "passed": all(checks.values()),
            "mode": self.mode,
            "baseline_version": self.baseline.version,
            "baseline_candidate_hash": self.baseline.candidate_hash,
            "checks": checks,
            "unrecorded_losses": losses,
        }

    def _baseline(self) -> tuple[Optional[Path], Optional[VoiceManifest]]:
        """Return the verified active version selected as the immutable baseline.

        Returns:
            tuple[Optional[Path], Optional[VoiceManifest]]: Active directory and manifest,
                or two ``None`` values when the voice has no active version.

        Raises:
            VoiceBuildError: If the active version fails component verification.
        """
        registry_path = self.root / "profiles" / "registry.json"
        if not registry_path.is_file():
            return None, None
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        item = registry.get("profiles", {}).get(self.voice_id)
        if not item or item.get("status") != VoiceStatus.ACTIVE.value:
            return None, None
        directory = self.root / "profiles" / self.voice_id / "versions" / item["active_version"]
        manifest_path = directory / "manifest.json"
        manifest = VoiceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        if item.get("candidate_hash") != manifest.candidate_hash:
            raise VoiceBuildError("Active voice registry hash does not match its manifest")
        mismatches = verify_components(directory, manifest.components, manifest.component_hashes)
        if mismatches:
            raise VoiceBuildError(f"Active voice component hash mismatch: {mismatches[0]}")
        return directory, manifest

    def _load_changes(
        self, path: Optional[Path]
    ) -> tuple[Optional[VoiceEvolutionChangeSet], Optional[str]]:
        """Load an explicit semantic change set and its exact artifact hash.

        Args:
            path (Optional[Path]): Workspace-relative or absolute change-set path.

        Returns:
            tuple[Optional[VoiceEvolutionChangeSet], Optional[str]]: Parsed changes and
                file hash, or two ``None`` values when no changes were requested.

        Raises:
            VoiceBuildError: If the requested change-set file does not exist.
        """
        if path is None:
            return None, None
        resolved = path if path.is_absolute() else self.root / path
        if not resolved.is_file():
            raise VoiceBuildError(f"Voice change set does not exist: {resolved}")
        changes = VoiceEvolutionChangeSet.model_validate_json(resolved.read_text(encoding="utf-8"))
        return changes, hash_file(resolved)

    @staticmethod
    def _artifacts(directory: Path) -> EvolutionResult:
        """Load the protected profile artifacts from one candidate or version.

        Args:
            directory (Path): Candidate or immutable version directory.

        Returns:
            EvolutionResult: Parsed profile, constraints, rubric, and patterns.
        """
        return EvolutionResult(
            profile=(directory / "profile.md").read_text(encoding="utf-8"),
            constraints=json.loads((directory / "constraints.json").read_text(encoding="utf-8")),
            rubric=json.loads((directory / "voice-rubric.json").read_text(encoding="utf-8")),
            patterns=[
                VoicePattern.model_validate(item)
                for item in json.loads((directory / "patterns.json").read_text(encoding="utf-8"))
            ],
        )

    def _evolve(
        self,
        candidate: Path,
        baseline: EvolutionResult,
        generated: EvolutionResult,
    ) -> EvolutionResult:
        """Return active-first artifacts and a complete semantic delta.

        Retain every baseline pattern unless an explicit proposal changes it, then append
        newly evidenced non-conflicting patterns for later author approval.

        Args:
            candidate (Path): Staged candidate containing regenerated evidence.
            baseline (EvolutionResult): Parsed author-approved active artifacts.
            generated (EvolutionResult): Parsed full-corpus regeneration artifacts.

        Returns:
            EvolutionResult: Active-first artifacts proposed for candidate approval.
        """
        _, active = self._required_baseline()
        approved_ids = {
            item["id"]
            for item in json.loads((candidate / "source-index.json").read_text(encoding="utf-8"))
            if item.get("approved_for_analysis")
        }
        patterns = {item.id: item.model_copy(deep=True) for item in baseline.patterns}
        order = [item.id for item in baseline.patterns]
        groups: dict[str, list[VoiceEvolutionRecord]] = {
            action.value: [] for action in VoiceEvolutionAction
        }
        changed: set[str] = set()
        for proposal in self.change_set.changes if self.change_set else []:
            self._apply_proposal(proposal, patterns, order, groups, changed, approved_ids)
        for pattern in sorted(generated.patterns, key=lambda item: item.id):
            if pattern.id in patterns or pattern.id in changed:
                continue
            self._validate_evidence(pattern.supporting_source_ids, approved_ids, pattern.id)
            patterns[pattern.id] = pattern
            order.append(pattern.id)
            groups[VoiceEvolutionAction.ADD.value].append(
                self._record(
                    pattern.id,
                    None,
                    pattern.supporting_source_ids,
                    pattern.confidence,
                    "New evidence-backed pattern proposed from the complete corpus",
                )
            )
        for item in baseline.patterns:
            if item.id not in changed:
                groups[VoiceEvolutionAction.RETAIN.value].append(
                    self._record(
                        item.id,
                        None,
                        [f"active:{active.version}"],
                        1.0,
                        "Author-approved active guidance retained",
                    )
                )
        groups[VoiceEvolutionAction.RETAIN.value].extend(
            self._record(
                f"artifact:{name}",
                None,
                [f"active:{active.version}"],
                1.0,
                "Author-approved artifact retained with active precedence",
            )
            for name in ("profile.md", "constraints.json", "voice-rubric.json")
        )
        self.delta = self._delta(candidate, groups)
        return EvolutionResult(
            profile=self._profile(baseline.profile, groups),
            constraints=self._merge(generated.constraints, baseline.constraints),
            rubric=self._merge(generated.rubric, baseline.rubric),
            patterns=[patterns[item_id] for item_id in order if item_id in patterns],
        )

    def _apply_proposal(
        self,
        proposal: VoiceEvolutionProposal,
        patterns: dict[str, VoicePattern],
        order: list[str],
        groups: dict[str, list[VoiceEvolutionRecord]],
        changed: set[str],
        approved_ids: set[str],
    ) -> None:
        """Apply one validated semantic proposal to the candidate pattern mapping.

        Args:
            proposal (VoiceEvolutionProposal): Explicit change requested by the author.
            patterns (dict[str, VoicePattern]): Mutable active-first pattern mapping.
            order (list[str]): Stable output order for pattern identifiers.
            groups (dict[str, list[VoiceEvolutionRecord]]): Delta records by action.
            changed (set[str]): Baseline identifiers already changed explicitly.
            approved_ids (set[str]): Authorised source identifiers in this build.

        Returns:
            None: Patterns and delta groups are updated in place.

        Raises:
            VoiceBuildError: If an add or retain proposal has invalid structure.
        """
        target = proposal.target_id
        replacement = proposal.replacement
        if proposal.action == VoiceEvolutionAction.RETAIN:
            if not target or target not in patterns:
                raise VoiceBuildError("Retain proposal requires an existing target_id")
            return
        self._validate_evidence(proposal.evidence_source_ids, approved_ids, target or "addition")
        if replacement is not None:
            self._validate_evidence(replacement.supporting_source_ids, approved_ids, replacement.id)
        if proposal.action == VoiceEvolutionAction.ADD:
            if target is not None or replacement is None or replacement.id in patterns:
                raise VoiceBuildError("Add proposal requires one new replacement and no target_id")
            patterns[replacement.id] = replacement
            order.append(replacement.id)
            guidance_id = replacement.id
        else:
            if target in changed:
                raise VoiceBuildError(f"Duplicate evolution proposal for target: {target}")
            guidance_id = self._apply_existing_proposal(proposal, patterns, order, changed)
        groups[proposal.action.value].append(
            self._record(
                guidance_id,
                replacement.id if replacement else None,
                proposal.evidence_source_ids,
                proposal.confidence,
                proposal.rationale,
            )
        )

    @staticmethod
    def _apply_existing_proposal(
        proposal: VoiceEvolutionProposal,
        patterns: dict[str, VoicePattern],
        order: list[str],
        changed: set[str],
    ) -> str:
        """Apply modify, supersede, or remove semantics to existing guidance.

        Args:
            proposal (VoiceEvolutionProposal): Explicit change targeting active guidance.
            patterns (dict[str, VoicePattern]): Mutable active-first pattern mapping.
            order (list[str]): Stable output order for pattern identifiers.
            changed (set[str]): Baseline identifiers changed explicitly.

        Returns:
            str: Target guidance identifier recorded in the semantic delta.

        Raises:
            VoiceBuildError: If the target or replacement violates action semantics.
        """
        target = proposal.target_id
        replacement = proposal.replacement
        if not target or target not in patterns:
            raise VoiceBuildError(f"{proposal.action.value} proposal requires an active target")
        changed.add(target)
        if proposal.action == VoiceEvolutionAction.REMOVE:
            if replacement is not None:
                raise VoiceBuildError("Remove proposal cannot include a replacement")
            patterns.pop(target)
        elif replacement is None:
            raise VoiceBuildError(f"{proposal.action.value} proposal requires a replacement")
        elif proposal.action == VoiceEvolutionAction.MODIFY:
            if replacement.id != target:
                raise VoiceBuildError("Modify replacement must retain the target id")
            patterns[target] = replacement
        else:
            if replacement.id == target or replacement.id in patterns:
                raise VoiceBuildError("Superseding replacement requires one new id")
            order[order.index(target)] = replacement.id
            patterns.pop(target)
            patterns[replacement.id] = replacement
        return target

    def _replacement_delta(
        self,
        candidate: Path,
        baseline: list[VoicePattern],
        generated: list[VoicePattern],
    ) -> VoiceEvolutionDelta:
        """Return a complete comparison for explicit full regeneration.

        Args:
            candidate (Path): Staged replacement candidate.
            baseline (list[VoicePattern]): Active patterns being replaced.
            generated (list[VoicePattern]): Full-corpus replacement patterns.

        Returns:
            VoiceEvolutionDelta: Deterministic replacement classification.
        """
        previous = {item.id: item for item in baseline}
        current = {item.id: item for item in generated}
        groups: dict[str, list[VoiceEvolutionRecord]] = {
            action.value: [] for action in VoiceEvolutionAction
        }
        for item_id in sorted(previous.keys() | current.keys()):
            old, new = previous.get(item_id), current.get(item_id)
            if old and new and old.model_dump() == new.model_dump():
                action = VoiceEvolutionAction.RETAIN
            elif old and new:
                action = VoiceEvolutionAction.MODIFY
            elif new:
                action = VoiceEvolutionAction.ADD
            else:
                action = VoiceEvolutionAction.REMOVE
            evidence = new.supporting_source_ids if new else self._approved_source_ids(candidate)
            confidence = new.confidence if new else 1.0
            groups[action.value].append(
                self._record(
                    item_id,
                    new.id if old and new else None,
                    evidence,
                    confidence,
                    "Explicit full-corpus replacement requested",
                )
            )
        return self._delta(candidate, groups)

    def _delta(
        self,
        candidate: Path,
        groups: dict[str, list[VoiceEvolutionRecord]],
    ) -> VoiceEvolutionDelta:
        """Build the deterministic delta envelope around classified records.

        Args:
            candidate (Path): Staged candidate containing source evidence.
            groups (dict[str, list[VoiceEvolutionRecord]]): Records grouped by action.

        Returns:
            VoiceEvolutionDelta: Versioned active-to-candidate evidence.
        """
        baseline_dir, baseline = self._required_baseline()
        return VoiceEvolutionDelta(
            mode=self.mode,
            baseline_version=baseline.version,
            baseline_candidate_hash=baseline.candidate_hash,
            baseline_manifest_hash=hash_file(baseline_dir / "manifest.json"),
            generated_evidence_hash=hash_file(candidate / "source-index.json"),
            change_set_hash=self.change_set_hash,
            retained=sorted(groups["retain"], key=lambda item: item.guidance_id),
            added=sorted(groups["add"], key=lambda item: item.guidance_id),
            modified=sorted(groups["modify"], key=lambda item: item.guidance_id),
            superseded=sorted(groups["supersede"], key=lambda item: item.guidance_id),
            removed=sorted(groups["remove"], key=lambda item: item.guidance_id),
        )

    def _write_result(self, candidate: Path, result: EvolutionResult) -> None:
        """Write merged protected artifacts to the isolated staging candidate.

        Args:
            candidate (Path): Staged candidate directory.
            result (EvolutionResult): Active-first artifacts to persist.

        Returns:
            None: Candidate files are replaced atomically.
        """
        RunStore._atomic_text(candidate / "profile.md", result.profile)
        RunStore._atomic_text(
            candidate / "constraints.json", json.dumps(result.constraints, indent=2)
        )
        RunStore._atomic_text(candidate / "voice-rubric.json", json.dumps(result.rubric, indent=2))
        RunStore._atomic_text(
            candidate / "patterns.json",
            json.dumps([item.model_dump(mode="json") for item in result.patterns], indent=2),
        )

    def _write_delta(self, candidate: Path) -> None:
        """Write the prepared semantic delta to the staging candidate.

        Args:
            candidate (Path): Staged candidate directory.

        Returns:
            None: The delta is written atomically.

        Raises:
            VoiceBuildError: If no semantic delta was prepared.
        """
        if self.delta is None:
            raise VoiceBuildError("Voice evolution delta was not prepared")
        RunStore._atomic_text(
            candidate / self.artifact_name,
            self.delta.model_dump_json(indent=2),
        )

    @staticmethod
    def _profile(baseline: str, groups: dict[str, list[VoiceEvolutionRecord]]) -> str:
        """Return baseline prose with an explicit semantic proposal appendix.

        Args:
            baseline (str): Exact author-approved active profile prose.
            groups (dict[str, list[VoiceEvolutionRecord]]): Delta records by action.

        Returns:
            str: Preserved profile with visible proposed changes.
        """
        proposals = [
            (category, item)
            for category in ("add", "modify", "supersede", "remove")
            for item in groups[category]
        ]
        if not proposals:
            return baseline
        lines = [baseline.rstrip(), "", "## Evolution proposal", ""]
        lines.extend(
            "- **{} `{}`{}:** {} (confidence {:.2f}; evidence: {})".format(
                category.title(),
                item.guidance_id,
                f" → `{item.replacement_id}`" if item.replacement_id else "",
                item.rationale,
                item.confidence,
                ", ".join(item.provenance),
            )
            for category, item in proposals
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _merge(generated: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
        """Return a recursive mapping with active baseline values taking precedence.

        Args:
            generated (dict[str, Any]): Newly inferred candidate mapping.
            baseline (dict[str, Any]): Author-approved mapping to preserve.

        Returns:
            dict[str, Any]: Merged mapping with active-first precedence.
        """
        merged = deepcopy(generated)
        for key, value in baseline.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = VoiceEvolution._merge(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged

    @staticmethod
    def _contains(current: Any, baseline: Any) -> bool:
        """Return whether a nested candidate preserves every baseline value.

        Args:
            current (Any): Candidate value being checked.
            baseline (Any): Author-approved value that must remain present.

        Returns:
            bool: Whether the candidate recursively contains the baseline.
        """
        if not isinstance(baseline, dict):
            return current == baseline
        return isinstance(current, dict) and all(
            key in current and VoiceEvolution._contains(current[key], value)
            for key, value in baseline.items()
        )

    @staticmethod
    def _validate_evidence(evidence: list[str], approved: set[str], label: str) -> None:
        """Validate that a semantic change cites authorised current evidence.

        Args:
            evidence (list[str]): Source identifiers cited by the proposal.
            approved (set[str]): Authorised source identifiers in the complete corpus.
            label (str): Guidance label used in failure reporting.

        Returns:
            None: Evidence is accepted without mutation.

        Raises:
            VoiceBuildError: If evidence is absent or unavailable.
        """
        unknown = sorted(set(evidence) - approved)
        if not evidence or unknown:
            detail = ", ".join(unknown) if unknown else "none supplied"
            raise VoiceBuildError(f"Unsupported evolution evidence for {label}: {detail}")

    @staticmethod
    def _record(
        guidance_id: str,
        replacement_id: Optional[str],
        evidence: list[str],
        confidence: float,
        rationale: str,
    ) -> VoiceEvolutionRecord:
        """Return one normalized privacy-safe semantic delta record.

        Args:
            guidance_id (str): Baseline or proposed guidance identifier.
            replacement_id (Optional[str]): Replacement identifier when applicable.
            evidence (list[str]): Baseline or source provenance identifiers.
            confidence (float): Bounded proposal confidence.
            rationale (str): Human-readable reason for the classification.

        Returns:
            VoiceEvolutionRecord: Normalized deterministic delta entry.
        """
        provenance = [item if item.startswith("active:") else f"source:{item}" for item in evidence]
        return VoiceEvolutionRecord(
            guidance_id=guidance_id,
            replacement_id=replacement_id,
            provenance=provenance,
            confidence=confidence,
            rationale=rationale,
        )

    @staticmethod
    def _approved_source_ids(candidate: Path) -> list[str]:
        """Return authorised source identifiers from the staged complete corpus.

        Args:
            candidate (Path): Staged candidate containing the source index.

        Returns:
            list[str]: Approved source identifiers in stable source order.
        """
        return [
            item["id"]
            for item in json.loads((candidate / "source-index.json").read_text(encoding="utf-8"))
            if item.get("approved_for_analysis")
        ]

    def _required_baseline_dir(self) -> Path:
        """Return the required immutable active-version directory.

        Returns:
            Path: Verified active baseline directory.
        """
        return self._required_baseline()[0]

    def _required_baseline(self) -> tuple[Path, VoiceManifest]:
        """Return required active directory and manifest or fail closed.

        Returns:
            tuple[Path, VoiceManifest]: Verified active baseline evidence.

        Raises:
            VoiceBuildError: If the expected active baseline is unavailable.
        """
        if self.baseline_dir is None or self.baseline is None:
            raise VoiceBuildError("Active voice baseline is unavailable")
        return self.baseline_dir, self.baseline
