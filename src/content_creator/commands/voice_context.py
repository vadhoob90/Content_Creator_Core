"""Dependencies shared by focused voice command handlers."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from ..voice_builder import VoiceBuilder
from ..voices import VoiceRegistry


@dataclass(frozen=True)
class VoiceCommandContext:
    """Represent a voice command context."""

    root: Path
    arguments: argparse.Namespace
    builder: VoiceBuilder
    registry: VoiceRegistry
