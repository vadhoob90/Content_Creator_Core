"""Verify production Google Style documentation enforcement."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "scripts" / "documentation_report.py"


def _report_module():
    """Load the documentation report as an importable test module."""
    sys.path.insert(0, str(REPORT_PATH.parent))
    spec = importlib.util.spec_from_file_location("documentation_report", REPORT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_report_accepts_complete_google_style_contract():
    """Accept a callable that documents arguments, defaults, output, and errors."""
    result = _report_module().inspect_source(
        "sample.py",
        '''"""Provide documented sample behavior."""

class Example:
    """Represent a documented example."""

    def calculate(self, value: int, scale: float = 1.0) -> float:
        """Calculate a scaled example value.

        Apply the configured scale while rejecting values outside the supported
        non-negative input domain.

        Args:
            value (int): The source value to scale.
            scale (float): The multiplier to apply. Defaults to 1.0.

        Returns:
            float: The scaled value.

        Raises:
            ValueError: If value is negative.
        """
        if value < 0:
            raise ValueError("value must be non-negative")
        return value * scale
''',
    )

    assert result["totals"] == {"module": 1, "class": 1, "function": 1}
    assert result["documented"] == result["totals"]
    assert result["issues"] == []


def test_report_identifies_incomplete_and_stale_sections():
    """Report stable issue codes for malformed callable contracts."""
    result = _report_module().inspect_source(
        "sample.py",
        '''"""Sample module without an imperative summary."""

def calculate(value: int, scale: float = 1.0) -> float:
    """Returns a scaled value.

    Args:
        value: Value to scale.
        obsolete (str): A stale parameter.

    Raises:
        RuntimeError: If an unrelated operation fails.
    """
    if value < 0:
        raise ValueError("value must be non-negative")
    return value * scale
''',
    )

    codes = {issue.code for issue in result["issues"]}
    assert {
        "summary-not-imperative",
        "arg-missing-type",
        "arg-missing",
        "arg-stale",
        "default-undocumented",
        "returns-missing",
        "raises-missing",
        "raises-stale",
    } <= codes


def test_report_rejects_incorrect_signature_types_and_default_values():
    """Reject argument, return, and default text that contradicts the signature."""
    result = _report_module().inspect_source(
        "sample.py",
        '''"""Provide documented sample behavior."""

def calculate(value: int = 2) -> float:
    """Calculate a transformed value.

    Args:
        value (str): The source value. Defaults to ``3``.

    Returns:
        int: The transformed value.
    """
    return float(value)
''',
    )

    assert {issue.code for issue in result["issues"]} == {
        "arg-type-mismatch",
        "default-undocumented",
        "returns-type-mismatch",
    }


def test_report_rejects_known_placeholder_prose():
    """Reject mechanically green prose that does not describe domain behavior."""
    result = _report_module().inspect_source(
        "sample.py",
        '''"""Provide documented sample behavior."""

def calculate() -> int:
    """Calculate the value used by this operation.

    Returns:
        int: The result produced by the operation.
    """
    return 1
''',
    )

    assert "placeholder-prose" in {issue.code for issue in result["issues"]}


def test_report_requires_context_for_long_callables():
    """Require a description paragraph when a callable exceeds the review ideal."""
    body = "\n".join(f"    value += {number}" for number in range(41))
    source = f'''"""Provide documented sample behavior."""

def calculate(value: int) -> int:
    """Calculate a transformed value.

    Args:
        value (int): The source value.

    Returns:
        int: The transformed value.
    """
{body}
    return value
'''

    result = _report_module().inspect_source("sample.py", source)

    assert "description-missing" in {issue.code for issue in result["issues"]}


def test_production_documentation_report_is_machine_readable():
    """Expose strict coverage and issue details as deterministic JSON."""
    result = subprocess.run(
        [sys.executable, "scripts/documentation_report.py", "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)

    assert report["scope"] == "src/content_creator"
    assert report["summary"]["total"] >= 800
    assert report["totals"]["module"] >= 100
    assert report["totals"]["function"] >= 500
    assert all("code" in issue for issue in report["issues"])


def test_production_documentation_check_passes():
    """Keep the complete production documentation contract green."""
    result = subprocess.run(
        [sys.executable, "scripts/documentation_report.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
