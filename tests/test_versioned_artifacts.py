import json
from pathlib import Path

import pytest

from content_creator.versioned_artifacts import (
    ActivationLock,
    next_major_version,
    numeric_version_directories,
    publish_version_snapshot,
    replace_candidate,
    verify_components,
)


def test_next_major_version_ignores_non_version_directories(tmp_path: Path):
    versions = tmp_path / "versions"
    (versions / "1.0.0").mkdir(parents=True)
    (versions / "3.2.1").mkdir()
    (versions / "candidate").mkdir()

    assert next_major_version(versions) == "4.0.0"


def test_numeric_version_directories_exclude_hidden_and_invalid_state(tmp_path: Path):
    versions = tmp_path / "versions"
    for name in ("1.0.0", "10.0.0", "2.3.4", ".11.0.0-promotion-staging", "candidate"):
        (versions / name).mkdir(parents=True)

    assert [path.name for path in numeric_version_directories(versions)] == [
        "10.0.0",
        "2.3.4",
        "1.0.0",
    ]


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


def test_activation_lock_records_owner_metadata(tmp_path: Path):
    lock = tmp_path / ".activation.lock"

    with ActivationLock(lock, "busy"):
        metadata = json.loads(lock.read_text(encoding="utf-8"))
        assert metadata["pid"] > 0
        assert metadata["created_at"].endswith("+00:00")


def test_candidate_replacement_restores_previous_candidate_on_failure(tmp_path, monkeypatch):
    candidate = tmp_path / "candidate"
    staging = tmp_path / ".candidate-staging"
    candidate.mkdir()
    staging.mkdir()
    (candidate / "value.txt").write_text("previous", encoding="utf-8")
    (staging / "value.txt").write_text("next", encoding="utf-8")
    original_replace = __import__("os").replace

    def fail_staging_publish(source, destination):
        if Path(source) == staging:
            raise OSError("injected publish failure")
        original_replace(source, destination)

    monkeypatch.setattr("content_creator.versioned_artifacts.os.replace", fail_staging_publish)

    with pytest.raises(OSError, match="injected publish failure"):
        replace_candidate(staging, candidate)

    assert (candidate / "value.txt").read_text(encoding="utf-8") == "previous"


def test_version_snapshot_remains_hidden_until_verification_passes(tmp_path):
    candidate = tmp_path / "candidate"
    versions = tmp_path / "versions"
    candidate.mkdir()
    (candidate / "component.txt").write_text("candidate", encoding="utf-8")

    def prepare(staging, version):
        assert version == "1.0.0"
        (staging / "metadata.json").write_text("{}", encoding="utf-8")

    def reject(staging):
        assert staging.name.startswith(".1.0.0")
        assert not (versions / "1.0.0").exists()
        raise ValueError("injected verification failure")

    with pytest.raises(ValueError, match="injected verification failure"):
        publish_version_snapshot(candidate, versions, prepare, reject)

    assert not (versions / "1.0.0").exists()
    assert not list(versions.glob(".*.promotion-staging"))
    assert (candidate / "component.txt").read_text(encoding="utf-8") == "candidate"


@pytest.mark.parametrize("failure_boundary", ["copy", "prepare", "verify", "publish"])
def test_version_snapshot_rolls_back_at_each_persistence_boundary(
    tmp_path, monkeypatch, failure_boundary
):
    candidate = tmp_path / "candidate"
    versions = tmp_path / "versions"
    candidate.mkdir()
    (candidate / "component.txt").write_text("candidate", encoding="utf-8")

    if failure_boundary == "copy":
        monkeypatch.setattr(
            "content_creator.versioned_artifacts.shutil.copytree",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("injected copy failure")),
        )
    if failure_boundary == "publish":
        original_replace = __import__("os").replace

        def fail_publish(source, destination):
            if Path(source).name.endswith("promotion-staging"):
                raise OSError("injected publish failure")
            original_replace(source, destination)

        monkeypatch.setattr("content_creator.versioned_artifacts.os.replace", fail_publish)

    def prepare(staging, _version):
        (staging / "metadata.json").write_text("{}", encoding="utf-8")
        if failure_boundary == "prepare":
            raise OSError("injected prepare failure")

    def verify(_staging):
        if failure_boundary == "verify":
            raise OSError("injected verify failure")

    with pytest.raises(OSError, match="injected"):
        publish_version_snapshot(candidate, versions, prepare, verify)

    assert not list(versions.glob("[0-9]*"))
    assert not list(versions.glob(".*.promotion-staging"))
    assert (candidate / "component.txt").read_text(encoding="utf-8") == "candidate"
