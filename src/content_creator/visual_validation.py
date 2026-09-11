"""Validate visual geometry, copy, provenance, and pack constraints."""

import re
from typing import List, Optional

from .visual_contracts import (
    BoundingBox,
    DiagnosticSeverity,
    RightsStatus,
    SafeAreaProfile,
    VisualAsset,
    VisualBrief,
    VisualDiagnostic,
    VisualPackProfile,
    VisualValidation,
)


class VisualValidator:
    """Evaluate objective visual constraints without changing approval or artifacts."""

    def validate(
        self, asset: VisualAsset, brief: VisualBrief, profile: VisualPackProfile
    ) -> VisualValidation:
        """Return deterministic diagnostics for an exact candidate and brief.

        Args:
            asset (VisualAsset): Candidate media evidence.
            brief (VisualBrief): Pinned editorial requirements.
            profile (VisualPackProfile): Pack output constraints.

        Returns:
            VisualValidation: Complete technical validation result.
        """
        diagnostics: List[VisualDiagnostic] = []
        self._validate_asset_basics(asset, brief, profile, diagnostics)
        self._validate_copy(asset, brief, diagnostics)
        self._validate_safe_areas(asset, brief, profile, diagnostics)
        self._validate_crops(asset, brief, profile, diagnostics)
        return VisualValidation(
            passed=not any(d.severity == DiagnosticSeverity.ERROR for d in diagnostics),
            diagnostics=diagnostics,
        )

    def _validate_asset_basics(
        self,
        asset: VisualAsset,
        brief: VisualBrief,
        profile: VisualPackProfile,
        diagnostics: List[VisualDiagnostic],
    ) -> None:
        """Validate the asset basics.

        Slot-specific dimensions and source rights are checked alongside pack
        constraints. A technically valid candidate still requires author approval.

        Args:
            asset (VisualAsset): The asset value passed to validate asset basics.
            brief (VisualBrief): The research or content brief that defines the requested
                work.
            profile (VisualPackProfile): The resolved voice, perspective, or content
                profile.
            diagnostics (List[VisualDiagnostic]): The runtime diagnostics service used to
                record safe evidence.

        Returns:
            None: The callable updates asset basics state and returns no value.
        """
        ratio = self._ratio(asset.width, asset.height)
        if not any(
            self._ratio_matches(asset.width, asset.height, item) for item in profile.aspect_ratios
        ):
            diagnostics.append(self._error("unsupported-aspect-ratio", ratio))
        if asset.format not in [value.lower().lstrip(".") for value in profile.formats]:
            diagnostics.append(self._error("unsupported-format", asset.format))
        if asset.execution_class not in profile.execution_classes:
            diagnostics.append(
                self._error("unsupported-execution-class", asset.execution_class.value)
            )
        if profile.max_file_size_bytes and asset.size_bytes > profile.max_file_size_bytes:
            diagnostics.append(self._error("file-too-large", str(asset.size_bytes)))
        if profile.require_alt_text and not brief.alt_text.strip():
            diagnostics.append(self._error("missing-alt-text", "Alt text is required"))
        if brief.slot_id and (
            asset.format not in brief.output_formats
            or not any(
                self._ratio_matches(asset.width, asset.height, ratio)
                for ratio in brief.aspect_ratios
            )
        ):
            diagnostics.append(
                self._error("slot-output-mismatch", "Image does not match the pinned slot outputs")
            )
        if asset.adapter == "governed-import" and not asset.sources:
            diagnostics.append(
                self._error("missing-import-provenance", "Imported source provenance is required")
            )
        if profile.require_provenance:
            unresolved = [
                item.source_id
                for item in [*brief.sources, *asset.sources]
                if item.rights_status == RightsStatus.UNVERIFIED
            ]
            if unresolved:
                diagnostics.append(self._error("unresolved-reuse-rights", ", ".join(unresolved)))

    def _validate_copy(
        self,
        asset: VisualAsset,
        brief: VisualBrief,
        diagnostics: List[VisualDiagnostic],
    ) -> None:
        """Validate the copy.

        Args:
            asset (VisualAsset): The asset value passed to validate copy.
            brief (VisualBrief): The research or content brief that defines the requested
                work.
            diagnostics (List[VisualDiagnostic]): The runtime diagnostics service used to
                record safe evidence.

        Returns:
            None: The callable updates copy state and returns no value.
        """
        if brief.exact_copy:
            if asset.extracted_copy is None:
                diagnostics.append(
                    self._error(
                        "exact-copy-unverified",
                        "The adapter did not supply OCR or deterministic copy evidence",
                    )
                )
            elif self._normalise_copy(asset.extracted_copy) != self._normalise_copy(
                brief.exact_copy
            ):
                diagnostics.append(
                    self._error("exact-copy-mismatch", "Rendered copy differs from the brief")
                )

    def _validate_safe_areas(
        self,
        asset: VisualAsset,
        brief: VisualBrief,
        profile: VisualPackProfile,
        diagnostics: List[VisualDiagnostic],
    ) -> None:
        """Validate the safe areas.

        Args:
            asset (VisualAsset): The asset value passed to validate safe areas.
            brief (VisualBrief): The research or content brief that defines the requested
                work.
            profile (VisualPackProfile): The resolved voice, perspective, or content
                profile.
            diagnostics (List[VisualDiagnostic]): The runtime diagnostics service used to
                record safe evidence.

        Returns:
            None: The callable updates safe areas state and returns no value.
        """
        safe_areas = {item.id: item for item in profile.safe_areas}
        for profile_id in brief.safe_area_profiles:
            safe = safe_areas.get(profile_id)
            if safe is None:
                diagnostics.append(self._error("unknown-safe-area", profile_id))
                continue
            for box in asset.content_boxes:
                if box.role in safe.applies_to_roles and not self._inside_safe_area(box, safe):
                    diagnostics.append(
                        self._error("unsafe-placement", box.role, profile=profile_id)
                    )

    def _validate_crops(
        self,
        asset: VisualAsset,
        brief: VisualBrief,
        profile: VisualPackProfile,
        diagnostics: List[VisualDiagnostic],
    ) -> None:
        """Validate the crops.

        Args:
            asset (VisualAsset): The asset value passed to validate crops.
            brief (VisualBrief): The research or content brief that defines the requested
                work.
            profile (VisualPackProfile): The resolved voice, perspective, or content
                profile.
            diagnostics (List[VisualDiagnostic]): The runtime diagnostics service used to
                record safe evidence.

        Returns:
            None: The callable updates crops state and returns no value.
        """
        crops = {item.id: item for item in profile.crop_profiles}
        for profile_id in brief.crop_profiles:
            crop = crops.get(profile_id)
            if crop is None:
                diagnostics.append(self._error("unknown-crop-profile", profile_id))
                continue
            for box in asset.content_boxes:
                if box.role in crop.protected_roles and not self._inside(box, crop.visible_area):
                    diagnostics.append(self._error("crop-risk", box.role, profile=profile_id))

    @staticmethod
    def _ratio(width: int, height: int) -> str:
        """Return the ratio.

        Args:
            width (int): The width value that controls ratio.
            height (int): The height value that controls ratio.

        Returns:
            str: The resulting text for ratio.
        """
        from math import gcd

        divisor = gcd(width, height)
        return "{}:{}".format(width // divisor, height // divisor)

    @staticmethod
    def _ratio_matches(width: int, height: int, expected: str) -> bool:
        """Return whether dimensions match a declared ratio within rounding tolerance.

        Args:
            width (int): Rendered width in pixels.
            height (int): Rendered height in pixels.
            expected (str): Pack ratio in positive ``WIDTH:HEIGHT`` form.

        Returns:
            bool: Whether the rendered and declared ratios differ by at most 0.5 percent.
        """
        expected_width, expected_height = (float(part) for part in expected.split(":"))
        expected_value = expected_width / expected_height
        return abs((width / height) - expected_value) / expected_value <= 0.005

    @staticmethod
    def _normalise_copy(lines: List[str]) -> List[str]:
        """Return the normalise copy.

        Args:
            lines (List[str]): The lines collection consumed while normalise copy.

        Returns:
            List[str]: The resulting normalise copy values in their documented order.
        """
        return [re.sub(r"\s+", " ", line).strip() for line in lines]

    @staticmethod
    def _inside(inner: BoundingBox, outer: BoundingBox) -> bool:
        """Return the inside.

        Args:
            inner (BoundingBox): The inner value passed to inside.
            outer (BoundingBox): The outer value passed to inside.

        Returns:
            bool: Whether inside satisfies the documented condition.
        """
        epsilon = 1e-9
        return (
            inner.x + epsilon >= outer.x
            and inner.y + epsilon >= outer.y
            and inner.x + inner.width <= outer.x + outer.width + epsilon
            and inner.y + inner.height <= outer.y + outer.height + epsilon
        )

    @classmethod
    def _inside_safe_area(cls, box: BoundingBox, safe: SafeAreaProfile) -> bool:
        """Return the inside safe area.

        Args:
            box (BoundingBox): The box value passed to inside safe area.
            safe (SafeAreaProfile): The safe value passed to inside safe area.

        Returns:
            bool: Whether inside safe area satisfies the documented condition.
        """
        return cls._inside(
            box,
            BoundingBox(
                x=safe.left,
                y=safe.top,
                width=1 - safe.left - safe.right,
                height=1 - safe.top - safe.bottom,
            ),
        )

    @staticmethod
    def _error(code: str, message: str, profile: Optional[str] = None) -> VisualDiagnostic:
        """Return the error.

        Args:
            code (str): The code text processed when error.
            message (str): The human-readable message associated with the operation.
            profile (Optional[str]): The resolved voice, perspective, or content profile.
                Defaults to ``None``.

        Returns:
            VisualDiagnostic: The resulting visual diagnostic for error.
        """
        return VisualDiagnostic(
            code=code,
            severity=DiagnosticSeverity.ERROR,
            message=message,
            profile=profile,
        )
