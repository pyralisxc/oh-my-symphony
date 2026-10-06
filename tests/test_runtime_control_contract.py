from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from symphony.issue import Issue
from symphony.orchestrator import Orchestrator
from symphony.orchestrator.entries import RunningEntry
from symphony.workflow import WorkflowState


def _issue() -> Issue:
    return Issue(
        id="7",
        identifier="GH-7",
        title="Runtime control",
        description=None,
        priority=None,
        state="In Progress",
    )


def _orch(tmp_path: Path) -> Orchestrator:
    return Orchestrator(WorkflowState(tmp_path / "WORKFLOW.md"))


def test_running_projection_exposes_exact_runtime_identity(tmp_path: Path):
    orch = _orch(tmp_path)
    issue = _issue()
    entry = RunningEntry(
        issue=issue,
        started_at=datetime.now(timezone.utc),
        retry_attempt=None,
        worker_task=None,
        workspace_path=tmp_path / "ws" / issue.identifier,
        run_id="run-123",
        continued_from_run_id="run-122",
        session_id="session-abc",
        thread_id="thread-abc",
        turn_id="turn-4",
        recovery_session_resumed=True,
        agent_pgid=4242,
    )

    row = orch._running_row(issue.id, entry)

    assert row["run"] == {
        "id": "run-123",
        "continued_from_run_id": "run-122",
    }
    assert row["worker"] == {
        "process_id": 4242,
        "process_group_id": 4242,
    }
    assert row["session"] == {
        "session_id": "session-abc",
        "thread_id": "thread-abc",
        "turn_id": "turn-4",
        "recovery_resumed": True,
    }
    assert row["workspace"]["path"].endswith("/ws/GH-7")
    assert row["workspace"]["branch"] == "symphony/GH-7"


def test_terminate_pauses_before_cancelling_and_preserves_identity(tmp_path: Path):
    async def scenario() -> None:
        orch = _orch(tmp_path)
        issue = _issue()
        stopped = asyncio.Event()

        async def worker() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        task = asyncio.create_task(worker())
        # Let the synthetic worker enter its body before cancellation so the
        # test exercises real in-flight cleanup rather than cancelling an
        # as-yet-unstarted coroutine.
        await asyncio.sleep(0)
        entry = RunningEntry(
            issue=issue,
            started_at=datetime.now(timezone.utc),
            retry_attempt=None,
            worker_task=task,
            workspace_path=tmp_path / "ws" / issue.identifier,
            run_id="run-123",
            session_id="thread-abc",
            thread_id="thread-abc",
        )
        orch._running[issue.id] = entry

        assert orch.terminate_worker(issue.id) is True
        assert orch.is_paused(issue.id) is True
        assert entry.run_id == "run-123"
        assert entry.thread_id == "thread-abc"

        try:
            await task
        except asyncio.CancelledError:
            pass
        assert stopped.is_set()

    asyncio.run(scenario())


def test_terminate_is_not_destructive_reset(tmp_path: Path):
    orch = _orch(tmp_path)
    issue = _issue()
    workspace = tmp_path / "ws" / issue.identifier
    workspace.mkdir(parents=True)
    marker = workspace / "keep.txt"
    marker.write_text("recoverable", encoding="utf-8")

    async def scenario() -> None:
        async def worker() -> None:
            await asyncio.Event().wait()

        task = asyncio.create_task(worker())
        orch._running[issue.id] = RunningEntry(
            issue=issue,
            started_at=datetime.now(timezone.utc),
            retry_attempt=None,
            worker_task=task,
            workspace_path=workspace,
            run_id="run-123",
        )
        assert orch.terminate_worker(issue.id) is True
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())
    assert marker.read_text(encoding="utf-8") == "recoverable"
