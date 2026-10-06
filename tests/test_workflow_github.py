from pathlib import Path

import pytest

from symphony.errors import (
    ConfigValidationError,
    MissingTrackerApiKey,
    MissingTrackerProjectSlug,
)
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
                "---\n"
                "tracker:\n"
                "  kind: github\n"
                "  project_slug: owner/repo\n"
                "agent:\n"
                "  feature_base_branch: preview\n"
                "  auto_merge_target_branch: preview\n"
                "---\nBody\n",
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


def test_github_tracker_canary_rejects_concurrency_above_one(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    cfg = build_service_config(
        load_workflow(
            _write(
                tmp_path,
                "---\n"
                "tracker:\n"
                "  kind: github\n"
                "  project_slug: owner/repo\n"
                "agent:\n"
                "  max_concurrent_agents: 2\n"
                "  feature_base_branch: preview\n"
                "  auto_merge_target_branch: preview\n"
                "---\nBody\n",
            )
        )
    )
    with pytest.raises(ConfigValidationError, match="max_concurrent_agents=1"):
        validate_for_dispatch(cfg)


def test_github_tracker_canary_rejects_main_delivery_target(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    cfg = build_service_config(
        load_workflow(
            _write(
                tmp_path,
                "---\n"
                "tracker:\n"
                "  kind: github\n"
                "  project_slug: owner/repo\n"
                "agent:\n"
                "  feature_base_branch: preview\n"
                "  auto_merge_target_branch: main\n"
                "---\nBody\n",
            )
        )
    )
    with pytest.raises(ConfigValidationError, match="refuses automatic merge"):
        validate_for_dispatch(cfg)


def test_github_tracker_canary_requires_explicit_preview_feature_base(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    cfg = build_service_config(
        load_workflow(
            _write(
                tmp_path,
                "---\n"
                "tracker:\n"
                "  kind: github\n"
                "  project_slug: owner/repo\n"
                "agent:\n"
                "  auto_merge_on_done: false\n"
                "---\nBody\n",
            )
        )
    )
    with pytest.raises(ConfigValidationError, match="feature_base_branch"):
        validate_for_dispatch(cfg)


def test_github_canary_allows_preview_auto_pr_when_auto_merge_is_off(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    cfg = build_service_config(
        load_workflow(
            _write(
                tmp_path,
                "---\n"
                "tracker:\n"
                "  kind: github\n"
                "  project_slug: owner/repo\n"
                "  active_states: [Ready, In Progress, Review]\n"
                "  terminal_states: [Done, Blocked]\n"
                "agent:\n"
                "  auto_merge_on_done: false\n"
                "  feature_base_branch: preview\n"
                "git:\n"
                "  auto_pr:\n"
                "    enabled: true\n"
                "    base: preview\n"
                "    trigger_state: Review\n"
                "---\nBody\n",
            )
        )
    )
    validate_for_dispatch(cfg)
    assert cfg.git.auto_pr.enabled is True
    assert cfg.git.auto_pr.base == "preview"


def test_github_canary_rejects_auto_pr_to_main(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    cfg = build_service_config(
        load_workflow(
            _write(
                tmp_path,
                "---\n"
                "tracker:\n"
                "  kind: github\n"
                "  project_slug: owner/repo\n"
                "agent:\n"
                "  auto_merge_on_done: false\n"
                "  feature_base_branch: preview\n"
                "git:\n"
                "  auto_pr:\n"
                "    enabled: true\n"
                "    base: main\n"
                "    trigger_state: Review\n"
                "---\nBody\n",
            )
        )
    )
    with pytest.raises(ConfigValidationError, match="git.auto_pr.base"):
        validate_for_dispatch(cfg)
