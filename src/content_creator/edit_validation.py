"""Validate adopted text using verified generation-time pack inputs."""

import json
from pathlib import Path

from .domain import RunState
from .draft_integrity import text_hash
from .packs import ContentPack, PackRegistry
from .perspective_evaluation import evaluate_perspective_output
from .storage import StorageError
from .validation import validate_draft
from .version import VERSION
from .versioned_artifacts import hash_file
from .voice_evaluation import evaluate_voice_output


def historical_pack(root: Path, state: RunState) -> ContentPack:
    """Resolve preserved effective pack inputs without silent policy upgrades.

    Args:
        root (Path): Workspace root.
        state (RunState): Run whose generation context selects validation inputs.

    Returns:
        ContentPack: Verified original effective pack.

    Raises:
        StorageError: If historical pack evidence is unavailable or mismatched.
    """
    run = root / "runs" / state.id
    path = run / "resolved-context.json"
    if not path.is_file():
        raise StorageError("Historical pack inputs unavailable; restore resolved-context.json")
    context = json.loads(path.read_text(encoding="utf-8"))
    _verify_context_identity(context, state)
    snapshot = context.get("effective_pack")
    if snapshot:
        if context.get("effective_pack_sha256") != text_hash(json.dumps(snapshot, sort_keys=True)):
            raise StorageError("Historical effective pack hash does not match its snapshot")
        pack = ContentPack.model_validate(snapshot)
    else:
        registry = PackRegistry(root)
        expected = context.get("component_hashes", {}).get("pack_manifest")
        raw = registry.get(state.work_order.content_pack)
        if raw.extends or expected != hash_file(registry.path(raw.id)):
            raise StorageError(
                "Historical pack inputs unavailable; restore the original effective pack"
            )
        pack = registry.resolve(raw.id, state.work_order.pack_options)
    identity = context.get("content_pack", {})
    if (pack.id, pack.version) != (identity.get("id"), identity.get("version")):
        raise StorageError("Historical pack identity does not match the preserved inputs")
    return pack


def validate_author_edit(root: Path, state: RunState, draft: str) -> dict:
    """Run deterministic pack, voice, and perspective checks without a provider.

    Args:
        root (Path): Workspace root.
        state (RunState): Run carrying pinned voice and perspective references.
        draft (str): Exact author-edited Markdown.

    Returns:
        dict: Validation errors and explicit engine and historical pack identity.
    """
    pack = historical_pack(root, state)
    voice = evaluate_voice_output(root, state.work_order, draft)
    perspective = evaluate_perspective_output(root, state.work_order, draft)
    errors = validate_draft(draft, state.work_order, pack.validators)
    errors.extend(voice.get("errors", []))
    errors.extend(perspective.get("errors", []))
    return {
        "errors": errors,
        "voice": voice,
        "perspective": perspective,
        "validator_core_version": VERSION,
        "pack_id": pack.id,
        "pack_version": pack.version,
        "model_critique": "historical",
    }


def _verify_context_identity(context: dict, state: RunState) -> None:
    """Require validation to retain the original pack, voice, and perspective identity.

    Args:
        context (dict): Persisted generation context.
        state (RunState): Current work order with pinned references.

    Returns:
        None: Selected identities match generation-time evidence.

    Raises:
        StorageError: If the work order no longer matches its preserved context.
    """
    order = state.work_order
    voice = context.get("voice", {})
    if context.get("content_pack", {}).get("id") != order.content_pack:
        raise StorageError("Work order pack differs from the historical context")
    if (voice.get("id"), voice.get("version")) != (order.voice_id, order.voice_version):
        raise StorageError("Work order voice differs from the historical context")
    selected = [(s.context_id, s.version) for s in order.perspective_selections]
    recorded = [(s.get("context_id"), s.get("version")) for s in context.get("perspectives", [])]
    if selected != recorded:
        raise StorageError("Work order perspectives differ from the historical context")
