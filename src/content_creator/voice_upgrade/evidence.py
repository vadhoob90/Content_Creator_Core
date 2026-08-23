"""Calculate canonical evidence baselines and provenance-set deltas."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from ..ingestion import content_hash, read_source
from ..publication_receipt_models import PublicationReceipt
from ..versioned_artifacts import hash_file, hash_json
from ..voice_models import SourceRecord, VoiceManifest, VoiceWorkOrder
from .models import EvidenceRecord, EvidenceSet


def evidence_id(value: str) -> str:
    """Return a stable identifier derived from a canonical content hash.

    Args:
        value (str): Canonical SHA-256 content hash.

    Returns:
        str: Stable evidence identifier.
    """
    return "evidence-{}".format(value.removeprefix("sha256:")[:20])


def load_evidence_baseline(
    _root: Path,
    voice_id: str,
    directory: Path,
    manifest: VoiceManifest,
) -> EvidenceSet:
    """Load a native baseline or derive one from a legacy source index.

    Args:
        _root (Path): Reserved workspace-root boundary for future schema migration.
        voice_id (str): Selected voice identifier.
        directory (Path): Immutable active-version directory.
        manifest (VoiceManifest): Verified active manifest.

    Returns:
        EvidenceSet: Complete represented evidence with a deterministic legacy rule.
    """
    baseline_path = directory / manifest.components.get(
        "evidence_baseline", "evidence-baseline.json"
    )
    if baseline_path.is_file():
        return EvidenceSet.model_validate_json(baseline_path.read_text(encoding="utf-8"))
    source_path = directory / manifest.components.get("sources", "source-index.json")
    records = []
    for source in json.loads(source_path.read_text(encoding="utf-8")):
        if not source.get("approved_for_analysis"):
            continue
        digest = str(source["content_hash"])
        records.append(
            EvidenceRecord(
                evidence_id=evidence_id(digest),
                kind=str(source.get("kind", "legacy-source")),
                locator=str(source.get("locator", source.get("id"))),
                content_hash=digest,
                title=str(source.get("title", source.get("id"))),
                word_count=int(source.get("analysis_word_count") or source.get("word_count", 0)),
                source_id=source.get("id"),
                authorisation_basis="legacy-approved-source-index",
                analysis_cache_path=source.get("cache_path"),
            )
        )
    cutoff = datetime.fromtimestamp(
        (directory / "manifest.json").stat().st_mtime, tz=UTC
    ).isoformat()
    return EvidenceSet(
        voice_id=voice_id,
        voice_version=manifest.version,
        evidence_cutoff=cutoff,
        records=_deduplicated(records),
    )


def authorised_evidence(
    root: Path, order: VoiceWorkOrder
) -> tuple[EvidenceSet, list[dict[str, str]]]:
    """Collect currently authorised work-order and publication evidence.

    Args:
        root (Path): Workspace root.
        order (VoiceWorkOrder): Authorised source-derived voice work order.

    Returns:
        tuple[EvidenceSet, list[dict[str, str]]]: Canonical evidence and duplicate records.
    """
    records = [_source_record(root, locator, order) for locator in order.urls + order.documents]
    records.extend(_publication_records(root, order.voice_id))
    unique: list[EvidenceRecord] = []
    duplicates = []
    by_hash: dict[str, EvidenceRecord] = {}
    for record in records:
        existing = by_hash.get(record.content_hash)
        if existing:
            duplicates.append(
                {
                    "locator": record.locator,
                    "represented_by": existing.evidence_id,
                    "content_hash": record.content_hash,
                }
            )
            continue
        by_hash[record.content_hash] = record
        unique.append(record)
    return (
        EvidenceSet(
            voice_id=order.voice_id,
            evidence_cutoff=datetime.now(UTC).isoformat(),
            records=sorted(unique, key=lambda item: (item.evidence_id, item.locator)),
        ),
        duplicates,
    )


def evidence_delta(current: EvidenceSet, baseline: EvidenceSet) -> EvidenceSet:
    """Return current evidence not represented by baseline content hashes.

    Args:
        current (EvidenceSet): Complete currently authorised evidence.
        baseline (EvidenceSet): Evidence represented by the active version.

    Returns:
        EvidenceSet: Provenance-set difference, independent of publication dates.
    """
    represented = {record.content_hash for record in baseline.records}
    return EvidenceSet(
        voice_id=current.voice_id,
        evidence_cutoff=current.evidence_cutoff,
        records=[record for record in current.records if record.content_hash not in represented],
    )


def evidence_set_hash(evidence: EvidenceSet) -> str:
    """Hash authoritative evidence identities independently of display timestamps.

    Args:
        evidence (EvidenceSet): Evidence set to bind.

    Returns:
        str: Canonical hash of ordered evidence records.
    """
    return hash_json([record.model_dump(mode="json") for record in evidence.records])


def evidence_from_sources(
    voice_id: str,
    sources: Iterable[SourceRecord],
    evidence_cutoff: str,
) -> EvidenceSet:
    """Create a complete evidence baseline from approved analyzed sources.

    Args:
        voice_id (str): Selected voice identifier.
        sources (Iterable[SourceRecord]): Collected source-index records.
        evidence_cutoff (str): Authoritative build cutoff in ISO-8601 format.

    Returns:
        EvidenceSet: Deduplicated evidence represented by the built version.
    """
    records = [
        EvidenceRecord(
            evidence_id=evidence_id(source.content_hash),
            kind=source.kind,
            locator=source.locator,
            content_hash=source.content_hash,
            title=source.title,
            word_count=source.analysis_word_count or source.word_count,
            source_id=source.id,
            authorisation_basis="approved-source-index",
            analysis_cache_path=source.cache_path,
        )
        for source in sources
        if source.approved_for_analysis
    ]
    return EvidenceSet(
        voice_id=voice_id,
        evidence_cutoff=evidence_cutoff,
        records=_deduplicated(records),
    )


def retrieval_locators(root: Path, order: VoiceWorkOrder) -> dict[str, str]:
    """Resolve canonical evidence identifiers to current retrievable locators.

    Args:
        root (Path): Workspace root.
        order (VoiceWorkOrder): Current authorised voice work order.

    Returns:
        dict[str, str]: Evidence identifiers mapped to URL or local file locators.
    """
    result = {}
    for locator in order.urls + order.documents:
        _, _, text = read_source(locator)
        result[evidence_id(content_hash(text))] = locator
    receipts_root = root / "publication-receipts"
    for path in sorted(receipts_root.rglob("*.receipt.json")):
        receipt = PublicationReceipt.model_validate_json(path.read_text(encoding="utf-8"))
        artifact = root / receipt.artifact_path
        if receipt.voice_id != order.voice_id or not artifact.is_file():
            continue
        if hash_file(artifact) != receipt.artifact_hash:
            continue
        _, _, text = read_source(str(artifact))
        result[evidence_id(content_hash(text))] = str(artifact)
    return result


def combined_evidence(
    baseline: EvidenceSet, delta: EvidenceSet, version: str | None = None
) -> EvidenceSet:
    """Return the deduplicated union represented by a prospective version.

    Args:
        baseline (EvidenceSet): Active represented evidence.
        delta (EvidenceSet): Newly authorised evidence delta.
        version (str | None): Resulting immutable version when known. Defaults to ``None``.

    Returns:
        EvidenceSet: Complete prospective represented evidence.
    """
    return EvidenceSet(
        voice_id=baseline.voice_id,
        voice_version=version,
        evidence_cutoff=delta.evidence_cutoff,
        records=_deduplicated([*baseline.records, *delta.records]),
    )


def _source_record(root: Path, locator: str, order: VoiceWorkOrder) -> EvidenceRecord:
    """Read one authorised source without writing provider or cache state.

    Args:
        root (Path): Workspace root.
        locator (str): URL or local document locator.
        order (VoiceWorkOrder): Authorised source-derived work order.

    Returns:
        EvidenceRecord: Canonical source evidence.
    """
    kind, title, text = read_source(locator)
    digest = content_hash(text)
    public_locator = (
        locator
        if locator.startswith(("http://", "https://"))
        else str(
            Path(locator).resolve().relative_to(root)
            if Path(locator).resolve().is_relative_to(root)
            else Path(locator).name
        )
    )
    return EvidenceRecord(
        evidence_id=evidence_id(digest),
        kind=kind,
        locator=public_locator,
        content_hash=digest,
        title=title,
        word_count=len(text.split()),
        authorisation_basis="work-order-authorisation:{}".format(
            order.authorisation.attested_by or "repository-owner"
        ),
    )


def _publication_records(root: Path, voice_id: str) -> list[EvidenceRecord]:
    """Return verified local publications associated with the selected voice.

    Args:
        root (Path): Workspace root.
        voice_id (str): Selected voice identifier.

    Returns:
        list[EvidenceRecord]: Author-reviewed local publication evidence.
    """
    records = []
    receipts_root = root / "publication-receipts"
    for path in sorted(receipts_root.rglob("*.receipt.json")):
        receipt = PublicationReceipt.model_validate_json(path.read_text(encoding="utf-8"))
        artifact = root / receipt.artifact_path
        if receipt.voice_id != voice_id or not artifact.is_file():
            continue
        if hash_file(artifact) != receipt.artifact_hash:
            continue
        kind, title, text = read_source(str(artifact))
        digest = content_hash(text)
        records.append(
            EvidenceRecord(
                evidence_id=evidence_id(digest),
                kind=kind,
                locator=receipt.artifact_path,
                content_hash=digest,
                title=title,
                word_count=len(text.split()),
                publication_receipt=str(path.relative_to(root)),
                publication_receipt_hash=hash_file(path),
                authorisation_basis="author-reviewed-publication-receipt",
            )
        )
    return records


def _deduplicated(records: Iterable[EvidenceRecord]) -> list[EvidenceRecord]:
    """Return one deterministic record per canonical content hash.

    Args:
        records (Iterable[EvidenceRecord]): Evidence records to deduplicate.

    Returns:
        list[EvidenceRecord]: Stable deduplicated evidence records.
    """
    by_hash: dict[str, EvidenceRecord] = {}
    for record in records:
        by_hash.setdefault(record.content_hash, record)
    return sorted(by_hash.values(), key=lambda item: (item.evidence_id, item.locator))
