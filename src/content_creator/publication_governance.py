"""Verify publication bindings to stable production governance."""

from __future__ import annotations

from pathlib import Path

from .production_manifest import ProductionManifest, manifest_governance_hash
from .publication_receipt_models import PublicationReceipt


def verify_production_governance(root: Path, receipt: PublicationReceipt) -> list[tuple[str, str]]:
    """Return deterministic failures for a receipt's production binding.

    Admit legacy receipts without either optional field. New receipts must provide both
    fields and match a recomputed governance hash rather than trusting the stored hash.

    Args:
        root (Path): Workspace root containing referenced run evidence.
        receipt (PublicationReceipt): Receipt containing an optional manifest binding.

    Returns:
        list[tuple[str, str]]: Stable finding-code and detail pairs.
    """
    if not receipt.production_manifest_path and not receipt.production_governance_hash:
        return []
    if not receipt.production_manifest_path or not receipt.production_governance_hash:
        return [
            (
                "incomplete_production_governance",
                "Production manifest path and governance hash must appear together",
            )
        ]
    path = (root / receipt.production_manifest_path).resolve()
    if not path.is_relative_to(root.resolve()):
        return [
            (
                "invalid_production_manifest_reference",
                "Referenced production manifest leaves the workspace",
            )
        ]
    if not path.is_file():
        return [
            (
                "missing_production_manifest",
                "Referenced production manifest is unavailable",
            )
        ]
    try:
        manifest = ProductionManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [("invalid_production_manifest", str(exc))]
    actual = manifest_governance_hash(manifest)
    if manifest.governance_hash != actual or receipt.production_governance_hash != actual:
        return [
            (
                "production_governance_hash_mismatch",
                "Published receipt and production manifest governance differ",
            )
        ]
    return []
