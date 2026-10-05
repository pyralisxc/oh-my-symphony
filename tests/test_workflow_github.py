from pathlib import Path

import pytest

from symphony.errors import MissingTrackerApiKey, MissingTrackerProjectSlug
from symphony.workflow import (
    build_service_config,
    load_workflow,
    validate_for_dispatch,
)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "WORKFLOW.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_github_tracker_uses_standard_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    cfg = build_service_config(
        load_workflow(
            _write(
                tmp_path,
                "---\ntracker:\n  kind: github\n  project_slug: owner/repo\n---\nBody\n",
            )
        )
    )
    assert cfg.tracker.endpoint == "https://api.github.com"
    assert cfg.tracker.api_key == "gh-token"
    validate_for_dispatch(cfg)


def test_github_tracker_requires_owner_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    cfg = build_service_config(
        load_workflow(
            _write(
                tmp_path,
                "---\ntracker:\n  kind: github\n  project_slug: repo-only\n---\nBody\n",
            )
        )
    )
    with pytest.raises(MissingTrackerProjectSlug):
        validate_for_dispatch(cfg)


def test_github_tracker_requires_token(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    cfg = build_service_config(
        load_workflow(
            _write(
                tmp_path,
                "---\ntracker:\n  kind: github\n  project_slug: owner/repo\n---\nBody\n",
            )
        )
    )
    with pytest.raises(MissingTrackerApiKey):
        validate_for_dispatch(cfg)
