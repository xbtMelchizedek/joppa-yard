import json
from pathlib import Path

from joppa_yard.providers import ScriptedProvider
from joppa_yard.sim import run_sim, write_run
from joppa_yard.world import Agent, World


def test_run_writes_one_receipt_per_event_and_respects_world_rules(tmp_path: Path):
    world = World(agents=[Agent("silas", "Silas", 2, 2), Agent("tamar", "Tamar", 3, 2)])
    script = {
        "silas": [
            {"action": "work"},
            {"action": "trade", "item": "rope", "target": "tamar"},
            {"action": "move", "direction": "south"},
        ],
        "tamar": [
            {"action": "look"},
            {"action": "wait"},
            {"action": "talk", "line": "berth is clear"},
        ],
    }
    payload = run_sim(ticks=3, provider=ScriptedProvider(script), world=world)
    assert len(payload["events"]) == 6
    assert len(payload["receipts"]) == 6
    assert all(r.mock for r in payload["receipts"])
    assert all(e["receipt_id"] for e in payload["events"])
    # Trade conserved the rope Silas worked on the dock.
    assert world.cargo_total("rope") == 1
    assert world.agents["silas"].inventory.get("rope", 0) == 0
    assert world.agents["tamar"].inventory.get("rope", 0) == 1
    # Silas moved south from (2,2) to (2,3).
    assert world.agents["silas"].pos() == (2, 3)
    write_run(tmp_path, payload)
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    receipts = [json.loads(line) for line in (tmp_path / "receipts.jsonl").read_text().splitlines()]
    assert len(events) == 6
    assert all(row["mock"] is True for row in receipts)
    story = (tmp_path / "storyboard.md").read_text()
    assert "DRAFT — do not post" in story
    assert "Silas" in story and "Tamar" in story


def test_invalid_decision_is_receipted_and_does_not_mutate_the_world():
    world = World(agents=[Agent("eli", "Eli", 3, 5)])
    start = world.agents["eli"].pos()
    inv = dict(world.agents["eli"].inventory)
    script = {"eli": [{"action": "teleport", "x": 0, "y": 0}]}
    payload = run_sim(ticks=1, provider=ScriptedProvider(script), world=world)
    assert payload["events"][0]["verb"] is None
    assert payload["events"][0]["result"]["ok"] is False
    assert payload["receipts"][0].mock is True
    assert payload["receipts"][0].error is not None
    assert world.agents["eli"].pos() == start
    assert world.agents["eli"].inventory == inv


def test_ticks_must_be_positive():
    try:
        run_sim(ticks=0, provider=ScriptedProvider({"silas": []}))
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
