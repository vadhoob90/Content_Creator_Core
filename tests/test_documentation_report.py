import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "scripts" / "documentation_report.py"


def _report_module():
    spec = importlib.util.spec_from_file_location("documentation_report", REPORT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_report_detects_module_class_and_nested_callable_gaps():
    report = _report_module().inspect_source(
        "sample.py",
        '''
class Example:
    """Represent a documented example."""

    def missing(self):
        return None

def documented():
    """Return a documented value."""

    def nested():
        return None

    return nested()
''',
    )

    assert report["totals"] == {"module": 1, "class": 1, "function": 3}
    assert report["documented"] == {"module": 0, "class": 1, "function": 1}
    assert [item.qualified_name for item in report["missing"]] == [
        "sample",
        "Example.missing",
        "documented.nested",
    ]


def test_production_documentation_report_is_machine_readable():
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


def test_production_documentation_check_passes():
    result = subprocess.run(
        [sys.executable, "scripts/documentation_report.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
