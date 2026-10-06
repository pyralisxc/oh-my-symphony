"""Host-owned pull-request handoff for completed worker stages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .issue import Issue
from .logging import get_logger
from .utils import git_ops
from .workflow.constants import SYMPHONY_BRANCH_PREFIX

log = get_logger()

AppendNote = Callable[[Issue, str, str], None]


@dataclass(frozen=True)
class AutoPrOutcome:
    opened: bool
    status: str
    url: str = ""
    detail: str = ""


def maybe_open_pull_request(
    cfg,
    issue: Issue,
    target_state: str,
    *,
    append_note: AppendNote,
) -> AutoPrOutcome | None:
    auto = cfg.git.auto_pr
    if not auto.enabled:
        return None
    if target_state.strip().lower() != auto.trigger_state.strip().lower():
        return None

    workflow_dir = cfg.workflow_path.parent
    branch = f"{SYMPHONY_BRANCH_PREFIX}{issue.identifier}"
    pushed = git_ops.push_branch(workflow_dir, branch, auto.remote)
    if not pushed.ok:
        log.warning(
            "auto_pr_push_failed",
            identifier=issue.identifier,
            status=pushed.status,
        )
        _note(
            append_note,
            issue,
            "Pull request not opened",
            f"push failed: {pushed.status} — {pushed.detail}",
        )
        return AutoPrOutcome(False, pushed.status, detail=pushed.detail)

    title = f"{issue.identifier}: {issue.title}"
    body = (
        f"Symphony ticket {issue.identifier} reached {target_state}.\n\n"
        "This is a Preview candidate only; Main promotion remains outside "
        "the worker runtime."
    )
    result = git_ops.create_pull_request(
        workflow_dir, branch, auto.base, title, body
    )
    if result.ok or result.status == "pr_exists":
        url = result.url or ""
        log.info("auto_pr_opened", identifier=issue.identifier, url=url)
        _note(append_note, issue, "Pull request", url or result.detail)
        return AutoPrOutcome(True, result.status, url=url, detail=result.detail)

    log.warning("auto_pr_failed", identifier=issue.identifier, status=result.status)
    _note(
        append_note,
        issue,
        "Pull request not opened",
        f"{result.status} — {result.detail}",
    )
    return AutoPrOutcome(False, result.status, detail=result.detail)


def _note(append_note: AppendNote, issue: Issue, heading: str, body: str) -> None:
    try:
        append_note(issue, heading, body)
    except Exception as exc:
        log.warning(
            "auto_pr_note_failed",
            identifier=issue.identifier,
            error=str(exc),
        )
