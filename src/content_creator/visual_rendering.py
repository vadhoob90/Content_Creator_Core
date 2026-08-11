"""Render provider-independent deterministic SVG visual assets."""

from __future__ import annotations

import re
from textwrap import wrap
from typing import Optional
from xml.sax.saxutils import escape

from .visual_contracts import (
    BoundingBox,
    ExecutionClass,
    VisualAdapter,
    VisualAdapterRegistry,
    VisualAsset,
    VisualBrief,
    VisualOutput,
)

DEFAULT_TOKENS = {
    "background": "#071A2B",
    "foreground": "#F4F7FA",
    "accent": "#19C3B1",
    "font_family": "Arial, sans-serif",
}


class EditorialSvgRenderer(VisualAdapter):
    """Render an accessible editorial card without external provider credentials."""

    name = "core-deterministic-svg"
    execution_class = ExecutionClass.DETERMINISTIC
    model_or_renderer = "core.editorial-card-layout"
    prompt_or_template_version = "1.0.0"

    def render(self, brief: VisualBrief, parent: Optional[VisualAsset] = None) -> VisualOutput:
        """Render one deterministic SVG concept or revision.

        Args:
            brief (VisualBrief): Reviewed visual brief and workspace brand tokens.
            parent (Optional[VisualAsset]): Parent revision, when present. Defaults to
                ``None``.

        Returns:
            VisualOutput: SVG bytes, dimensions, copy evidence, and layout metadata.
        """
        width, height = self._dimensions(brief)
        tokens = self._tokens(brief.brand_tokens)
        headline = brief.exact_copy[0] if brief.exact_copy else brief.objective
        lines = self._headline_lines(headline, width)
        line_height = max(42, round(height * 0.075))
        start_y = round(height * 0.32)
        text = "\n".join(
            '<text x="{x}" y="{y}" class="headline">{line}</text>'.format(
                x=round(width * 0.09),
                y=start_y + index * line_height,
                line=escape(line),
            )
            for index, line in enumerate(lines)
        )
        svg = self._document(width, height, tokens, text, brief.alt_text)
        box_height = min(0.5, max(0.12, len(lines) * line_height / height))
        return VisualOutput(
            content=svg.encode("utf-8"),
            width=width,
            height=height,
            format="svg",
            extracted_copy=[headline],
            content_boxes=[
                BoundingBox(x=0.09, y=0.24, width=0.82, height=box_height, role="headline")
            ],
            metadata={
                "component_id": "core.deterministic-svg-renderer",
                "layout_id": "core.editorial-card-layout",
                "parent_asset_id": parent.asset_id if parent else None,
            },
        )

    @staticmethod
    def _dimensions(brief: VisualBrief) -> tuple[int, int]:
        """Resolve requested dimensions with a bounded ratio fallback.

        Args:
            brief (VisualBrief): Visual brief containing dimensions or aspect ratio.

        Returns:
            tuple[int, int]: Positive output width and height.
        """
        if brief.output_width and brief.output_height:
            return brief.output_width, brief.output_height
        ratio_width, ratio_height = (float(part) for part in brief.aspect_ratios[0].split(":"))
        return 1200, max(1, round(1200 * ratio_height / ratio_width))

    @staticmethod
    def _tokens(tokens: dict[str, str]) -> dict[str, str]:
        """Return safe workspace tokens layered over neutral Core defaults.

        Args:
            tokens (dict[str, str]): Workspace-owned visual brand tokens.

        Returns:
            dict[str, str]: Sanitized renderer tokens.
        """
        resolved = dict(DEFAULT_TOKENS)
        for key in ("background", "foreground", "accent"):
            value = tokens.get(key)
            if value and re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
                resolved[key] = value
        font = tokens.get("font_family")
        if font and re.fullmatch(r"[A-Za-z0-9 ,'-]{1,80}", font):
            resolved["font_family"] = font
        return resolved

    @staticmethod
    def _headline_lines(headline: str, width: int) -> list[str]:
        """Return headline copy wrapped for the requested canvas width.

        Args:
            headline (str): Exact reviewed headline copy.
            width (int): Output width in pixels.

        Returns:
            list[str]: At most four non-empty display lines.
        """
        characters = max(18, min(42, round(width / 42)))
        return wrap(" ".join(headline.split()), width=characters) or ["Reviewed content"]

    @staticmethod
    def _document(
        width: int,
        height: int,
        tokens: dict[str, str],
        headline: str,
        alt_text: str,
    ) -> str:
        """Compose a complete accessible SVG document.

        Args:
            width (int): Output width in pixels.
            height (int): Output height in pixels.
            tokens (dict[str, str]): Sanitized renderer tokens.
            headline (str): Escaped SVG text elements.
            alt_text (str): Human-authored accessibility description.

        Returns:
            str: Complete SVG document.
        """
        document = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">\n'
            '  <title id="title">Editorial visual</title>\n'
            '  <desc id="desc">{alt_text}</desc>\n'
            '  <rect width="{width}" height="{height}" fill="{background}"/>\n'
            '  <rect x="{accent_x}" y="{accent_y}" width="{accent_width}" '
            'height="{accent_height}" rx="8" fill="{accent}"/>\n'
            "  <style>.headline {{ fill: {foreground}; font: 700 {font_size}px "
            "{font_family}; }}</style>\n"
            "  {headline}\n"
            "</svg>\n"
        )
        return document.format(
            width=width,
            height=height,
            alt_text=escape(alt_text),
            background=tokens["background"],
            foreground=tokens["foreground"],
            accent=tokens["accent"],
            font_family=tokens["font_family"],
            font_size=max(36, round(height * 0.065)),
            accent_x=round(width * 0.09),
            accent_y=round(height * 0.15),
            accent_width=round(width * 0.16),
            accent_height=max(8, round(height * 0.018)),
            headline=headline,
        )


def default_visual_adapters() -> VisualAdapterRegistry:
    """Return the production adapters that can ship without host credentials.

    Returns:
        VisualAdapterRegistry: Registry containing Core's deterministic SVG renderer.
    """
    registry = VisualAdapterRegistry()
    registry.register(EditorialSvgRenderer())
    return registry
