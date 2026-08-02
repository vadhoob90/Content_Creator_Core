import json
import os

import pytest

from content_creator.cli import main
from content_creator.operations import FailureCode, build_support_bundle, recovery_report


def test_support_bundle_contains_metadata_not_author_content(project):
    run = project / "runs" / "run-1"
    run.mkdir(parents=True)
    (run / "state.json").write_text(
        json.dumps({"status": "failed", "last_error": "provider unavailable"}),
        encoding="utf-8",
    )
    (run / "draft-01.md").write_text("private author draft", encoding="utf-8")

    bundle = build_support_bundle(project, "run-1")
    encoded = json.dumps(bundle)

    assert bundle["failure"]["code"] == FailureCode.PROVIDER_FAILURE
    assert "draft-01.md" in bundle["artifacts"]
    assert "private author draft" not in encoded
    assert bundle["privacy"]["author_content_included"] is False


def test_recovery_report_finds_stale_locks_and_corrupt_state(project):
    lock = project / "profiles" / "example" / ".activation.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("", encoding="utf-8")
    run = project / "runs" / "broken"
    run.mkdir(parents=True)
    (run / "state.json").write_text("not json", encoding="utf-8")

    report = recovery_report(project)

    assert report["status"] == "needs_attention"
    assert report["stale_activation_locks"] == ["profiles/example/.activation.lock"]
    assert report["corrupt_run_states"] == ["runs/broken/state.json"]


def test_operations_recovery_cli_is_offline(project, capsys):
    assert main(["--workspace", str(project), "operations", "recovery-report"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_support_bundle_rejects_path_traversal(project):
    with pytest.raises(ValueError, match="run_id"):
        build_support_bundle(project, "../outside")


def test_recovery_report_does_not_call_a_live_lock_stale(project):
    lock = project / "profiles" / "example" / ".activation.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")

    report = recovery_report(project)

    assert report["stale_activation_locks"] == []
    assert report["active_activation_locks"] == ["profiles/example/.activation.lock"]
