from pathlib import Path

from symphony.orchestrator.dispatch_gate import DispatchGate


def test_dispatch_gate_defaults_off_and_persists(tmp_path: Path):
    path = tmp_path / ".symphony" / "dispatch.json"

    first = DispatchGate(path)
    assert first.enabled is False

    first.set_enabled(True)
    second = DispatchGate(path)
    assert second.enabled is True

    second.set_enabled(False)
    third = DispatchGate(path)
    assert third.enabled is False


def test_dispatch_gate_corrupt_state_fails_closed(tmp_path: Path):
    path = tmp_path / ".symphony" / "dispatch.json"
    path.parent.mkdir()
    path.write_text("{not-json", encoding="utf-8")

    assert DispatchGate(path).enabled is False
