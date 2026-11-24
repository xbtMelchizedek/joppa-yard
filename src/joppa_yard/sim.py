"""Run ticks, apply allowlisted actions, persist events and receipts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from joppa_yard.providers import (
    HeuristicProvider,
    LiveFlopProvider,
    Provider,
    ScriptedProvider,
    render_prompt,
)
from joppa_yard.receipts import Receipt, write_jsonl
from joppa_yard.storyboard import write_storyboard
from joppa_yard.world import World

APPLYABLE = {"move", "work", "talk", "trade", "look", "wait"}


def apply_decision(world: World, agent_id: str, decision: dict) -> dict:
    verb = decision["verb"]
    if verb == "move":
        return world.move(agent_id, decision["direction"])
    if verb == "work":
        return world.work(agent_id)
    if verb == "talk":
        return world.talk(agent_id, decision["line"] or "")
    if verb == "trade":
        return world.trade(agent_id, decision["item"] or "", decision["target"] or "")
    if verb == "look":
        return world.look(agent_id)
    if verb == "wait":
        return {"ok": True, "reason": "waited"}
    return {"ok": False, "reason": f"unhandled verb {verb}"}


def run_sim(
    *,
    ticks: int,
    provider: Provider,
    world: World | None = None,
) -> dict:
    if ticks < 1:
        raise ValueError("ticks must be >= 1")
    world = world or World()
    events: list[dict] = []
    receipts: list[Receipt] = []
    order = list(world.agents.keys())

    for tick in range(ticks):
        for agent_id in order:
            observation = world.observation(agent_id)
            prompt = render_prompt(observation)
            decision, receipt = provider.decide(
                agent_id=agent_id, tick=tick, observation=observation, prompt=prompt
            )
            receipts.append(receipt)
            if decision is None:
                result = {"ok": False, "reason": receipt.error or "invalid decision"}
                verb = None
            else:
                result = apply_decision(world, agent_id, decision)
                verb = decision["verb"]
            events.append(
                {
                    "tick": tick,
                    "agent_id": agent_id,
                    "name": world.agents[agent_id].display_name,
                    "verb": verb,
                    "decision": decision,
                    "result": result,
                    "x": world.agents[agent_id].x,
                    "y": world.agents[agent_id].y,
                    "tile": world.tile(world.agents[agent_id].x, world.agents[agent_id].y).name,
                    "inventory": dict(world.agents[agent_id].inventory),
                    "receipt_id": receipt.request_id,
                    "mock": receipt.mock,
                }
            )

    # Invariant: one receipt per event.
    if len(events) != len(receipts):
        raise RuntimeError("receipt count drifted from event count")
    if len(events) != ticks * len(order):
        raise RuntimeError("event count drifted from ticks × agents")

    return {"world": world, "events": events, "receipts": receipts}


def write_run(out_dir: Path, payload: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "events.jsonl"
    receipts_path = out_dir / "receipts.jsonl"
    with events_path.open("w", encoding="utf-8") as fh:
        for event in payload["events"]:
            fh.write(json.dumps(event, sort_keys=True) + "\n")
    write_jsonl(receipts_path, payload["receipts"])
    write_storyboard(out_dir / "storyboard.md", payload["events"], payload["receipts"])


def build_provider(kind: str, script: dict | None = None) -> Provider:
    if kind == "scripted":
        if not script:
            raise ValueError("scripted provider needs a script")
        return ScriptedProvider(script)
    if kind == "heuristic":
        return HeuristicProvider(
            reason=(
                "heuristic demo policy; official testnet settlement was not used. "
                "receipts are mock"
            )
        )
    if kind == "live":
        return LiveFlopProvider()
    raise ValueError(f"unknown provider {kind!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Joppa Yard episode")
    parser.add_argument("--ticks", type=int, default=6)
    parser.add_argument("--out", type=Path, default=Path("runs/latest"))
    parser.add_argument(
        "--provider",
        choices=("heuristic", "live"),
        default="heuristic",
        help="heuristic writes mock receipts. live probes the official gateway and pays only on testnet genesis, otherwise also mocks",
    )
    args = parser.parse_args(argv)
    provider = build_provider(args.provider)
    payload = run_sim(ticks=args.ticks, provider=provider)
    write_run(args.out, payload)
    mock_n = sum(1 for r in payload["receipts"] if r.mock)
    live_n = len(payload["receipts"]) - mock_n
    print(
        f"wrote {len(payload['events'])} events, {mock_n} mock receipts, "
        f"{live_n} live receipts under {args.out}",
        file=sys.stdout,
    )
    if mock_n and args.provider == "live":
        # Surface the first reason so an operator sees why we did not pay.
        print(f"mock reason: {payload['receipts'][0].mock_reason}", file=sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
