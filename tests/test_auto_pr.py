from pathlib import Path
from types import SimpleNamespace

from symphony.auto_pr import maybe_open_pull_request
from symphony.issue import Issue
from symphony.utils.git_ops import GitOpResult


def _issue() -> Issue:
    return Issue(
        id="42", identifier="GH-42", title="Canary", description=None,
        priority=None, state="Review", labels=("automation-eligible",),
    )


def _cfg(tmp_path: Path):
    return SimpleNamespace(
        workflow_path=tmp_path / "WORKFLOW.md",
        git=SimpleNamespace(
            auto_pr=SimpleNamespace(
                enabled=True, remote="origin", base="preview", trigger_state="Review"
            )
        ),
    )


def test_auto_pr_pushes_then_opens_preview_candidate(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "symphony.auto_pr.git_ops.push_branch",
        lambda workflow_dir, branch, remote: (
            calls.append(("push", branch, remote))
            or GitOpResult(True, "pushed", "")
        ),
    )
    monkeypatch.setattr(
        "symphony.auto_pr.git_ops.create_pull_request",
        lambda workflow_dir, branch, target, title, body: (
            calls.append(("pr", branch, target))
            or GitOpResult(True, "created", "", url="https://example/pr/1")
        ),
    )
    notes = []
    result = maybe_open_pull_request(
        _cfg(tmp_path), _issue(), "Review",
        append_note=lambda issue, heading, body: notes.append((heading, body)),
    )
    assert result is not None and result.opened is True
    assert calls == [("push", "symphony/GH-42", "origin"), ("pr", "symphony/GH-42", "preview")]
    assert notes == [("Pull request", "https://example/pr/1")]


def test_auto_pr_does_nothing_before_trigger_state(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "symphony.auto_pr.git_ops.push_branch",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not push")),
    )
    assert maybe_open_pull_request(
        _cfg(tmp_path), _issue(), "In Progress",
        append_note=lambda *args: None,
    ) is None
