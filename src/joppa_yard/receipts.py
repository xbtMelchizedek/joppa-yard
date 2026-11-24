"""Inference receipts. Mock rows are labeled; live rows never include secrets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Receipt:
    kind: str
    mock: bool
    request_id: str
    agent_id: str
    tick: int
    model: str
    state: str
    created_at: str
    prompt_hash: str
    output_hash: str
    reserved_spend: float | None = None
    settled_spend: float | None = None
    settled_spend_raw: str | None = None
    channel_id: str | None = None
    terminal_event: str | None = None
    network_genesis: str | None = None
    mock_reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Drop null optional labels so a live row does not carry mock_reason: null
        # in a way that could be mistaken for an unset flag. Keep spend fields,
        # which are meaningful when null.
        if not self.mock:
            data.pop("mock_reason", None)
        return data


def new_request_id() -> str:
    return str(uuid4())


def mock_receipt(
    *,
    agent_id: str,
    tick: int,
    model: str,
    prompt: str,
    output: str,
    reason: str,
    request_id: str | None = None,
    error: str | None = None,
    network_genesis: str | None = None,
) -> Receipt:
    return Receipt(
        kind="inference_receipt",
        mock=True,
        mock_reason=reason,
        request_id=request_id or new_request_id(),
        agent_id=agent_id,
        tick=tick,
        model=model,
        state="mock",
        created_at=utc_now(),
        prompt_hash=sha256_text(prompt),
        output_hash=sha256_text(output),
        network_genesis=network_genesis,
        error=error,
    )


def live_receipt(
    *,
    agent_id: str,
    tick: int,
    model: str,
    prompt: str,
    output: str,
    request_id: str,
    state: str,
    reserved_spend: float | None,
    settled_spend: float | None,
    settled_spend_raw: str | None,
    channel_id: str | None,
    terminal_event: str | None,
    network_genesis: str,
) -> Receipt:
    if state not in {"reserved", "estimated", "settled", "released"}:
        raise ValueError(f"unexpected live receipt state {state!r}")
    return Receipt(
        kind="inference_receipt",
        mock=False,
        request_id=request_id,
        agent_id=agent_id,
        tick=tick,
        model=model,
        state=state,
        created_at=utc_now(),
        prompt_hash=sha256_text(prompt),
        output_hash=sha256_text(output),
        reserved_spend=reserved_spend,
        settled_spend=settled_spend,
        settled_spend_raw=settled_spend_raw,
        channel_id=channel_id,
        terminal_event=terminal_event,
        network_genesis=network_genesis,
    )


def write_jsonl(path, rows: list[Receipt]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row.to_dict(), sort_keys=True) + "\n")
