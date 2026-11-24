"""Allowlisted agent decisions. Unknown verbs are rejected, never executed."""

from __future__ import annotations

from typing import Any

ALLOWED = frozenset({"move", "work", "talk", "trade", "look", "wait"})


class DecisionError(ValueError):
    """The model (or script) returned something we will not execute."""


def parse_decision(raw: Any) -> dict:
    """Validate and normalize a decision object.

    Returns a dict with keys verb, direction, item, target, line. Raises
    DecisionError on missing or illegal fields so the sim can log a rejected
    receipt without mutating the world.
    """
    if not isinstance(raw, dict):
        raise DecisionError("decision must be an object")
    verb = raw.get("action") or raw.get("verb")
    if not isinstance(verb, str) or verb not in ALLOWED:
        raise DecisionError(f"action must be one of {sorted(ALLOWED)}")

    def optional_str(key: str) -> str | None:
        val = raw.get(key)
        if val is None or val == "":
            return None
        if not isinstance(val, str):
            raise DecisionError(f"{key} must be a string")
        return val.strip()

    decision = {
        "verb": verb,
        "direction": optional_str("direction"),
        "item": optional_str("item"),
        "target": optional_str("target"),
        "line": optional_str("line"),
    }
    if verb == "move" and decision["direction"] is None:
        raise DecisionError("move requires direction")
    if verb == "talk" and decision["line"] is None:
        raise DecisionError("talk requires line")
    if verb == "trade":
        if decision["item"] is None or decision["target"] is None:
            raise DecisionError("trade requires item and target")
    return decision
