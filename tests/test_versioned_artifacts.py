from pathlib import Path

import pytest

from content_creator.versioned_artifacts import (
    ActivationLock,
    next_major_version,
    verify_components,
)


def test_next_major_version_ignores_non_version_directories(tmp_path: Path):
    versions = tmp_path / "versions"
    (versions / "1.0.0").mkdir(parents=True)
    (versions / "3.2.1").mkdir()
    (versions / "candidate").mkdir()

    assert next_major_version(versions) == "4.0.0"


def test_component_verification_reports_missing_and_changed_files(tmp_path: Path):
    intact = tmp_path / "intact.md"
    changed = tmp_path / "changed.md"
    intact.write_text("intact", encoding="utf-8")
    changed.write_text("before", encoding="utf-8")
    from content_creator.versioned_artifacts import hash_file

    expected = {"intact": hash_file(intact), "changed": hash_file(changed), "missing": "x"}
    changed.write_text("after", encoding="utf-8")

    assert verify_components(
        tmp_path,
        {"intact": "intact.md", "changed": "changed.md", "missing": "missing.md"},
        expected,
    ) == ["changed", "missing"]


def test_activation_lock_is_exclusive_and_released(tmp_path: Path):
    lock = tmp_path / ".activation.lock"

    with ActivationLock(lock, "already active"):
        with pytest.raises(RuntimeError, match="already active"):
            with ActivationLock(lock, "already active"):
                pass
    assert not lock.exists()
