from __future__ import annotations

import httpx

from symphony.trackers.github import GitHubClient
from symphony.workflow import TrackerConfig


def _cfg() -> TrackerConfig:
    return TrackerConfig(
        kind="github",
        endpoint="https://api.github.test",
        api_key="token",
        project_slug="owner/repo",
        active_states=("Ready", "In Progress", "Review"),
        terminal_states=("Done", "Blocked"),
        board_root=None,
    )


def test_github_tracker_projects_status_labels_and_filters_pull_requests():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/owner/repo/issues"
        return httpx.Response(
            200,
            json=[
                {
                    "number": 7,
                    "title": "Do work",
                    "body": "body",
                    "state": "open",
                    "html_url": "https://github.test/owner/repo/issues/7",
                    "labels": [{"name": "status:ready"}, {"name": "kind:feature"}],
                    "created_at": "2026-10-05T00:00:00Z",
                    "updated_at": "2026-10-05T00:00:00Z",
                },
                {
                    "number": 8,
                    "title": "PR",
                    "state": "open",
                    "pull_request": {},
                    "labels": [{"name": "status:ready"}],
                },
            ],
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.github.test")
    tracker = GitHubClient(_cfg(), http_client=client)
    issues = tracker.fetch_candidate_issues()

    assert [i.identifier for i in issues] == ["GH-7"]
    assert issues[0].id == "7"
    assert issues[0].state == "Ready"
    assert issues[0].labels == ("status:ready", "kind:feature")


def test_github_tracker_state_write_preserves_unrelated_labels():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["json"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"number": 7})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.github.test")
    tracker = GitHubClient(_cfg(), http_client=client)
    issue = tracker._normalize(
        {
            "number": 7,
            "title": "Do work",
            "state": "open",
            "labels": [{"name": "status:ready"}, {"name": "kind:feature"}],
        },
        minimal=False,
    )

    tracker.update_state(issue, "In Progress")

    assert seen["method"] == "PATCH"
    assert seen["json"] == {
        "state": "open",
        "labels": ["kind:feature", "status:in-progress"],
    }
