import asyncio
from pathlib import Path
from types import SimpleNamespace

from symphony.issue import Issue
from symphony.orchestrator import Orchestrator
from symphony.workflow import WorkflowState


def test_observed_transition_fires_host_owned_delivery(tmp_path, monkeypatch):
    calls = []
    cfg = SimpleNamespace(
        notifications=SimpleNamespace(has_any=lambda: False),
        git=SimpleNamespace(auto_pr=SimpleNamespace(enabled=True)),
    )
    issue = Issue(
        id="42", identifier="GH-42", title="Canary", description=None,
        priority=None, state="Review",
    )
    orch = Orchestrator(WorkflowState(Path(tmp_path) / "WORKFLOW.md"))

    def fake_pr(cfg, issue, target_state, *, append_note):
        calls.append((issue.identifier, target_state))
        return None

    monkeypatch.setattr("symphony.orchestrator.core.maybe_open_pull_request", fake_pr)
    asyncio.run(
        orch._observed_transition_side_effects(
            cfg, issue, "In Progress", "Review"
        )
    )
    assert calls == [("GH-42", "Review")]
