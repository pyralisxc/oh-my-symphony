"""GitHub Issues tracker adapter.

GitHub remains the durable work truth. This adapter projects issue labels into
Symphony's normalized Issue model and writes state changes back to the same
GitHub issue; it never mirrors tickets into a local board.
"""

from __future__ import annotations

from typing import Any, Iterable

import httpx

from ..errors import SymphonyError
from ..issue import Issue, normalize_labels, parse_iso_timestamp
from ..workflow import TrackerConfig


PAGE_SIZE = 100
MAX_PAGES = 10


def _slug(state: str) -> str:
    return "-".join((state or "").strip().lower().split())


def _status_label(state: str) -> str:
    return f"status:{_slug(state)}"


class GitHubClient:
    """Synchronous GitHub Issues adapter used through the orchestrator executor."""

    def __init__(
        self, tracker: TrackerConfig, http_client: httpx.Client | None = None
    ) -> None:
        self._tracker = tracker
        try:
            self._owner, self._repo = tracker.project_slug.split("/", 1)
        except ValueError as exc:
            raise SymphonyError(
                "github tracker project_slug must be owner/repository"
            ) from exc
        self._base = (tracker.endpoint or "https://api.github.com").rstrip("/")
        self._owns_client = http_client is None
        if http_client is None:
            self._client = httpx.Client(
                base_url=self._base,
                timeout=tracker.network_timeout_seconds,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {tracker.api_key}",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "oh-my-symphony/github-tracker",
                },
            )
        else:
            self._client = http_client

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    @property
    def _issues_path(self) -> str:
        return f"/repos/{self._owner}/{self._repo}/issues"

    def fetch_candidate_issues(self) -> list[Issue]:
        active = {_slug(s) for s in self._tracker.active_states}
        return [
            issue
            for issue in self._list_issues(state="open", minimal=False)
            if _slug(issue.state) in active
        ]

    def fetch_issues_by_states(self, state_names: Iterable[str]) -> list[Issue]:
        wanted = {_slug(s) for s in state_names if s}
        if not wanted:
            return []
        return [
            issue
            for issue in self._list_issues(state="all", minimal=True)
            if _slug(issue.state) in wanted
        ]

    def fetch_issue_states_by_ids(self, ids: Iterable[str]) -> list[Issue]:
        out: list[Issue] = []
        for raw in ids:
            number = self._number(raw)
            if number is None:
                continue
            payload = self._json(
                self._client.get(f"{self._issues_path}/{number}")
            )
            if isinstance(payload, dict) and "pull_request" not in payload:
                out.append(self._normalize(payload, minimal=True))
        return out

    def fetch_issue_full_by_id(self, issue_id: str) -> Issue | None:
        number = self._number(issue_id)
        if number is None:
            return None
        response = self._client.get(f"{self._issues_path}/{number}")
        if response.status_code == 404:
            return None
        payload = self._json(response)
        if not isinstance(payload, dict) or "pull_request" in payload:
            return None
        return self._normalize(payload, minimal=False)

    def update_state(self, issue: Issue, target_state: str) -> None:
        number = self._number(issue.id) or self._number(issue.identifier)
        if number is None:
            raise SymphonyError("github issue has no numeric identity")
        target = _slug(target_state)
        labels = [label for label in issue.labels if not label.startswith("status:")]
        labels.append(_status_label(target_state))
        close = target in {"done", "closed"}
        response = self._client.patch(
            f"{self._issues_path}/{number}",
            json={"state": "closed" if close else "open", "labels": labels},
        )
        self._json(response)

    def append_note(self, issue: Issue, heading: str, body: str) -> None:
        number = self._number(issue.id) or self._number(issue.identifier)
        if number is None:
            raise SymphonyError("github issue has no numeric identity")
        text = f"## {heading}\n\n{body}" if heading else body
        response = self._client.post(
            f"{self._issues_path}/{number}/comments", json={"body": text}
        )
        self._json(response)

    def _list_issues(self, *, state: str, minimal: bool) -> list[Issue]:
        out: list[Issue] = []
        for page in range(1, MAX_PAGES + 1):
            response = self._client.get(
                self._issues_path,
                params={
                    "state": state,
                    "per_page": PAGE_SIZE,
                    "page": page,
                    "sort": "created",
                    "direction": "asc",
                },
            )
            payload = self._json(response)
            if not isinstance(payload, list):
                raise SymphonyError("github issues response must be a list")
            rows = [
                row
                for row in payload
                if isinstance(row, dict) and "pull_request" not in row
            ]
            out.extend(self._normalize(row, minimal=minimal) for row in rows)
            if len(payload) < PAGE_SIZE:
                break
        return out

    def _normalize(self, node: dict[str, Any], *, minimal: bool) -> Issue:
        number = node.get("number")
        labels = normalize_labels(node.get("labels"))
        state = self._project_state(node, labels)
        return Issue(
            id=str(number or ""),
            identifier=f"GH-{number}" if number is not None else "",
            title=str(node.get("title") or ""),
            description=None if minimal else (node.get("body") or None),
            priority=None,
            state=state,
            branch_name=None,
            url=node.get("html_url"),
            labels=labels,
            blocked_by=(),
            created_at=None if minimal else parse_iso_timestamp(node.get("created_at")),
            updated_at=parse_iso_timestamp(node.get("updated_at")),
        )

    def _project_state(self, node: dict[str, Any], labels: tuple[str, ...]) -> str:
        configured = self._tracker.active_states + self._tracker.terminal_states
        by_slug = {_slug(state): state for state in configured}
        for label in labels:
            if not label.startswith("status:"):
                continue
            key = label.split(":", 1)[1]
            if key in by_slug:
                return by_slug[key]
        if str(node.get("state") or "").lower() == "closed":
            return by_slug.get("done", by_slug.get("closed", "Done"))
        return by_slug.get("backlog", "Backlog")

    @staticmethod
    def _number(value: str) -> int | None:
        text = str(value or "").strip()
        if text.upper().startswith("GH-"):
            text = text[3:]
        return int(text) if text.isdigit() and int(text) > 0 else None

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SymphonyError(f"github tracker request failed: {exc}") from exc
        try:
            return response.json()
        except ValueError as exc:
            raise SymphonyError("github tracker returned invalid JSON") from exc
