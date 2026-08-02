"""Stable voice-builder façade over the phased build pipeline."""

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
    return analysis_excerpt(text, limit)


def _even_sample(records: List[SourceRecord], limit: int) -> List[SourceRecord]:
    return even_sample(records, limit)


class VoiceBuilder:
    def __init__(
        self,
        root: Path,
        runner: Optional[AgentRunner] = None,
        provider: Optional[str] = None,
    ):
        self.root = root.resolve()
        self.runner = runner
        self.provider = provider

    def save_work_order(self, order: VoiceWorkOrder) -> Path:
        path = self.root / "profiles" / order.voice_id / "work-order.json"
        RunStore._atomic_text(path, order.model_dump_json(indent=2))
        return path

    def load_work_order(self, voice_id: str) -> VoiceWorkOrder:
        path = self.root / "profiles" / voice_id / "work-order.json"
        if not path.exists():
            raise VoiceBuildError(f"Unknown voice work order: {voice_id}")
        return VoiceWorkOrder.model_validate_json(path.read_text(encoding="utf-8"))

    def build(self, voice_id: str) -> VoiceManifest:
        pipeline = VoiceBuildPipeline(self.root, self.runner, self.provider)
        return pipeline.build(self.load_work_order(voice_id))
