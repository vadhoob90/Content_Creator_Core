"""Register existing images as unapproved governed visual candidates."""

import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image
from pydantic import BaseModel

from .visual_contracts import (
    ExecutionClass,
    VisualAdapter,
    VisualAsset,
    VisualBrief,
    VisualError,
    VisualOutput,
    VisualPackProfile,
    VisualSource,
)
from .visual_mutation import visual_lock
from .visuals import VisualWorkflow


class VisualImportRequest(BaseModel):
    """Define an explicit local image import and its known source provenance."""

    run_id: str
    slot_id: str
    path: str
    source: VisualSource
    parent_asset_id: Optional[str] = None


class ImportedVisualAdapter(VisualAdapter):
    """Return inspected source bytes without changing or approving the image."""

    name = "governed-import"
    execution_class = ExecutionClass.DETERMINISTIC
    model_or_renderer = "author-supplied-image"

    def __init__(self, output: VisualOutput):
        """Initialize the immutable imported output.

        Args:
            output (VisualOutput): Inspected source content.

        Returns:
            None: Output is retained for this invocation.
        """
        self.output = output

    def render(self, _brief: VisualBrief, _parent: Optional[VisualAsset] = None) -> VisualOutput:
        """Return the original imported image bytes.

        Args:
            _brief (VisualBrief): Governed slot brief.
            _parent (Optional[VisualAsset]): Optional predecessor. Defaults to ``None``.

        Returns:
            VisualOutput: Original inspected source bytes.
        """
        return self.output


def import_visual(
    root: Path, profile: VisualPackProfile, request: VisualImportRequest
) -> VisualAsset:
    """Create and validate a candidate without selecting it or granting approval.

    Args:
        root (Path): Workspace root.
        profile (VisualPackProfile): Pack visual requirements.
        request (VisualImportRequest): Explicit source, slot, and provenance.

    Returns:
        VisualAsset: Registered candidate with validation diagnostics.

    Raises:
        VisualError: If source type or byte size is unsupported.
    """
    path = Path(request.path).expanduser()
    if not path.is_absolute():
        path = root / path
    content = path.read_bytes()
    if len(content) > (profile.max_file_size_bytes or 32 * 1024 * 1024):
        raise VisualError("Imported image exceeds the pack size limit")
    output = inspect_image(content)
    with visual_lock(root, request.run_id):
        workflow = VisualWorkflow(root)
        workflow.adapters.register(ImportedVisualAdapter(output))
        asset = workflow.execute(
            request.run_id, "governed-import", request.parent_asset_id, slot_id=request.slot_id
        )
        manifest = workflow._load_manifest(request.run_id)
        candidate = workflow._asset(manifest, asset.asset_id)
        candidate.sources = [request.source]
        candidate.source_ids = [request.source.source_id]
        candidate.metadata["imported_source_sha256"] = candidate.sha256
        workflow._save_manifest(manifest)
        workflow.validate(request.run_id, asset.asset_id, profile)
        return workflow.asset(request.run_id, asset.asset_id)


def inspect_image(content: bytes) -> VisualOutput:
    """Read SVG, PNG, JPEG, or WebP dimensions directly from the source bytes.

    Args:
        content (bytes): Complete image content.

    Returns:
        VisualOutput: Exact bytes with verified format and dimensions.

    Raises:
        VisualError: If the image header or supported SVG document is malformed.
    """
    try:
        if content.lstrip().startswith(b"<"):
            width, height = _svg_size(content)
            format_name = "svg"
        else:
            width, height, format_name = _raster_metadata(content)
        return VisualOutput(content=content, width=width, height=height, format=format_name)
    except (ValueError, KeyError, OSError, ET.ParseError, Image.DecompressionBombError) as exc:
        raise VisualError("Unsupported or malformed imported image") from exc


def _raster_metadata(content: bytes) -> tuple[int, int, str]:
    """Validate full raster bytes and return bounded image dimensions.

    Args:
        content (bytes): PNG, JPEG, or WebP content.

    Returns:
        tuple[int, int, str]: Width, height, and normalized format.

    Raises:
        ValueError: If a raster is animated or exceeds the decoded size limit.
    """
    with Image.open(BytesIO(content), formats=["PNG", "JPEG", "WEBP"]) as raster:
        width, height = raster.size
        if width * height > 40_000_000 or getattr(raster, "n_frames", 1) != 1:
            raise ValueError("Import a single-frame image with at most 40 million pixels")
        format_name = "jpg" if raster.format == "JPEG" else str(raster.format).lower()
        raster.verify()
    with Image.open(BytesIO(content)) as raster:
        raster.load()
    return width, height, format_name


def _svg_size(content: bytes) -> tuple[int, int]:
    """Read dimensions from a self-contained SVG without active or external content.

    Args:
        content (bytes): SVG document bytes.

    Returns:
        tuple[int, int]: Width and height.

    Raises:
        ValueError: If SVG contains external dependencies or unsupported dimensions.
    """
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise ValueError("SVG document declarations are unsupported")
    svg = ET.fromstring(content)
    if svg.tag.split("}")[-1] != "svg":
        raise ValueError("Expected SVG root")
    for node in svg.iter():
        if node.tag.split("}")[-1] in {"script", "foreignObject"}:
            raise ValueError("Active SVG content is unsupported")
        for key, value in node.attrib.items():
            if (
                key.lower().startswith("on")
                or (key.split("}")[-1] == "href" and not value.startswith("#"))
                or "url(" in value.lower()
            ):
                raise ValueError("SVG must be self-contained and inactive")
        if node.tag.split("}")[-1] == "style" and node.text:
            raise ValueError("Use inline SVG presentation attributes")
    return int(float(svg.attrib["width"].removesuffix("px"))), int(
        float(svg.attrib["height"].removesuffix("px"))
    )
