"""Provide voice builder contracts and behavior."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .runner import AgentRunner
from .storage import RunStore
from .voice_build_models import (
    VoiceBuildError as VoiceBuildError,
)
from .voice_build_models import analysis_excerpt, even_sample
from .voice_build_pipeline import VoiceBuildPipeline
from .voices import SourceRecord, VoiceManifest, VoiceWorkOrder


def _analysis_excerpt(text: str, limit: int = 6000) -> str:
    """Return the analysis excerpt.

    Args:
        text (str): The text to process.
        limit (int): The maximum number of records to return or process. Defaults to
            ``6000``.

    Returns:
        str: The resulting text for analysis excerpt.
    """
    return analysis_excerpt(text, limit)


def _even_sample(records: List[SourceRecord], limit: int) -> List[SourceRecord]:
    """Return the even sample.

    Args:
        records (List[SourceRecord]): The ordered persisted records to process.
        limit (int): The maximum number of records to return or process.

    Returns:
        List[SourceRecord]: The resulting even sample values in their documented order.
    """
    return even_sample(records, limit)


class VoiceBuilder:
    """Represent a voice builder."""

    def __init__(
        self,
        root: Path,
        runner: Optional[AgentRunner] = None,
        provider: Optional[str] = None,
    ):
        """Initialize the voice builder with its required state and collaborators.

        Args:
            root (Path): The workspace root directory.
            runner (Optional[AgentRunner]): The agent or command runner used to execute the
                operation. Defaults to ``None``.
            provider (Optional[str]): The provider implementation used for generation.
                Defaults to ``None``.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = root.resolve()
        self.runner = runner
        self.provider = provider

    def save_work_order(self, order: VoiceWorkOrder) -> Path:
        """Save the work order.

        Args:
            order (VoiceWorkOrder): The work order that defines the requested content run.

        Returns:
            Path: The resolved filesystem path for work order.
        """
        path = self.root / "profiles" / order.voice_id / "work-order.json"
        RunStore._atomic_text(path, order.model_dump_json(indent=2))
        return path

    def load_work_order(self, voice_id: str) -> VoiceWorkOrder:
        """Load the work order.

        Args:
            voice_id (str): The stable identifier for the selected voice.

        Returns:
            VoiceWorkOrder: The loaded voice work order for work order.

        Raises:
            VoiceBuildError: If the voice build operation cannot complete.
        """
        path = self.root / "profiles" / voice_id / "work-order.json"
        if not path.exists():
            raise VoiceBuildError(f"Unknown voice work order: {voice_id}")
        return VoiceWorkOrder.model_validate_json(path.read_text(encoding="utf-8"))

    def build(
        self,
        voice_id: str,
        full_regenerate: bool = False,
        change_set: Optional[Path] = None,
    ) -> VoiceManifest:
        """Build the voice builder workflow.

        Args:
            voice_id (str): The stable identifier for the selected voice.
            full_regenerate (bool): Explicitly replace active guidance. Defaults to
                ``False``.
            change_set (Optional[Path]): Evidence-backed semantic change proposals.
                Defaults to ``None``.

        Returns:
            VoiceManifest: The constructed voice manifest for value.
        """
        pipeline = VoiceBuildPipeline(self.root, self.runner, self.provider)
        return pipeline.build(
            self.load_work_order(voice_id),
            full_regenerate=full_regenerate,
            change_set=change_set,
        )
