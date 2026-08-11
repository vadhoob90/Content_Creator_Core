import runpy
from pathlib import Path

import pytest

from content_creator.version import VERSION

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = runpy.run_path(str(ROOT / "scripts" / "validate_release_references.py"))
PACKAGE_VERSION = VALIDATOR["package_version"]
STALE_REFERENCES = VALIDATOR["stale_references"]
MAIN = VALIDATOR["main"]


def test_release_reference_validator_reads_package_version():
    assert PACKAGE_VERSION() == VERSION


def test_release_reference_validator_accepts_active_documentation():
    assert STALE_REFERENCES(VERSION) == []


def test_release_reference_validator_reports_every_stale_active_pattern(tmp_path, monkeypatch):
    active = tmp_path / "active.md"
    active.write_text(
        "\n".join(
            [
                "content-creator==0.16.0",
                "--core-ref v0.16.0",
                "workspace upgrade --to v0.16.0",
                "Install the immutable `v0.16.0` release",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(STALE_REFERENCES.__globals__, "ACTIVE_RELEASE_DOCUMENTS", (active,))
    monkeypatch.setitem(STALE_REFERENCES.__globals__, "ROOT", tmp_path)

    stale = STALE_REFERENCES(VERSION)

    assert len(stale) == 4
    assert all("expected {}".format(VERSION) in item for item in stale)


def test_release_reference_validator_main_reports_success(capsys, monkeypatch):
    monkeypatch.setitem(MAIN.__globals__, "package_version", lambda: VERSION)
    monkeypatch.setitem(MAIN.__globals__, "stale_references", lambda _version: [])

    assert MAIN() == 0
    assert "match content-creator {}".format(VERSION) in capsys.readouterr().out


def test_release_reference_validator_main_fails_closed(monkeypatch):
    monkeypatch.setitem(MAIN.__globals__, "package_version", lambda: VERSION)
    monkeypatch.setitem(
        MAIN.__globals__,
        "stale_references",
        lambda _version: ["active.md:1 references 0.16.0"],
    )

    with pytest.raises(SystemExit, match="Stale active release references"):
        MAIN()
