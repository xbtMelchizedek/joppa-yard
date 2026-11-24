"""Turn an event log into a short draft caption pack. Nothing is posted."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from joppa_yard.receipts import Receipt

DRAFT_BANNER = (
    "DRAFT — do not post. Palmer approves any public post. "
    "Wording for @bitcoinPalmer goes through the BitcoinPalmer Twitter Assistant "
    "(id 3d6469b1-6b1b-4e40-99ac-64f256fb8845), not this file."
)


def _beat(event: dict) -> str:
    name = event["name"]
    verb = event.get("verb")
    result = event.get("result") or {}
    tile = event.get("tile")
    if not result.get("ok"):
        return f"{name} hesitated at the {tile}: {result.get('reason', 'blocked')}."
    if verb == "move":
        return f"{name} walked to the {tile}."
    if verb == "work":
        return f"{name} worked the {tile} and took {result.get('item')}."
    if verb == "talk":
        line = result.get("line") or ""
        return f"{name} said, \"{line}\""
    if verb == "trade":
        return f"{name} handed {result.get('item')} to {result.get('to')}."
    if verb == "look":
        return f"{name} looked around the {tile}."
    if verb == "wait":
        return f"{name} waited on the {tile}."
    return f"{name} paused on the {tile}."


def render_storyboard(events: list[dict], receipts: list[Receipt]) -> str:
    if not events:
        raise ValueError("no events to caption")
    names = []
    seen = set()
    for event in events:
        if event["name"] not in seen:
            seen.add(event["name"])
            names.append(event["name"])
    ticks = max(e["tick"] for e in events) + 1
    mock_n = sum(1 for r in receipts if r.mock)
    live_n = len(receipts) - mock_n
    verbs = Counter(e.get("verb") or "rejected" for e in events)
    title = f"Joppa Yard — {', '.join(names)} on the docks"
    beats = [_beat(e) for e in events]
    # Keep shorts short: at most eight caption cards, preferring talk/work/trade.
    if len(beats) > 8:
        preferred = [e for e in events if e.get("verb") in {"talk", "work", "trade"}]
        if len(preferred) >= 4:
            chosen = preferred[:8]
        else:
            step = max(1, len(events) // 8)
            chosen = events[::step][:8]
        beats = [_beat(e) for e in chosen]

    lines = [
        f"# {title}",
        "",
        DRAFT_BANNER,
        "",
        f"- ticks: {ticks}",
        f"- agents: {', '.join(names)}",
        f"- receipts: {len(receipts)} ({mock_n} mock, {live_n} live)",
        f"- verbs: {', '.join(f'{k} {v}' for k, v in sorted(verbs.items()))}",
        "",
        "## Captions",
        "",
    ]
    for i, beat in enumerate(beats, start=1):
        lines.append(f"{i}. {beat}")
    lines.append("")
    lines.append("## Suggested (still a draft)")
    lines.append("")
    lines.append(
        f"{title}. {beats[0]} A short look at agents working a fictional port, "
        "with every action logged as an inference receipt."
    )
    lines.append("")
    return "\n".join(lines)


def write_storyboard(path: Path, events: list[dict], receipts: list[Receipt]) -> None:
    path.write_text(render_storyboard(events, receipts), encoding="utf-8")
