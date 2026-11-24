"""Inference providers. The live path pays only on official testnet."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from joppa_yard import TESTNET_CHAIN_ID, TESTNET_GENESIS
from joppa_yard.actions import DecisionError, parse_decision
from joppa_yard.receipts import Receipt, live_receipt, mock_receipt, new_request_id

DEFAULT_GATEWAY = "https://api.flop.network"
# Devnet genesis observed on the shared gateway and faucet, 24 Nov 2026.
DEVNET_GENESIS = "0x99c172c095340ace980631f9123544c6bebd4839f3437e463533422d8be2d631"

SYSTEM_PROMPT = (
    "You are a dock worker in Joppa Yard, an original fictional port. "
    "Choose one action. Reply with only a JSON object using keys "
    "action, direction, item, target, line. action must be one of "
    "move, work, talk, trade, look, wait. direction is north, south, east or west. "
    "Do not mention other video games or trademarks."
)


@dataclass(frozen=True)
class Probe:
    ok: bool
    reason: str
    network: str | None = None
    genesis: str | None = None
    raw_status: str | None = None

    @property
    def is_official_testnet(self) -> bool:
        if not self.ok or not self.genesis:
            return False
        return self.genesis.lower() == TESTNET_GENESIS.lower()


class Provider(Protocol):
    name: str

    def decide(self, *, agent_id: str, tick: int, observation: dict, prompt: str) -> tuple[dict | None, Receipt]:
        """Return (decision or None if rejected, receipt). Never raises for a bad model output."""


def render_prompt(observation: dict) -> str:
    return (
        SYSTEM_PROMPT
        + "\n\nObservation:\n"
        + json.dumps(observation, sort_keys=True)
        + "\n\nJSON decision:"
    )


class ScriptedProvider:
    """Deterministic test double. Still writes a labeled mock receipt per call."""

    name = "scripted-mock"

    def __init__(self, script: dict[str, list[dict]], reason: str = "scripted test policy; no network call") -> None:
        self.script = {k: list(v) for k, v in script.items()}
        self.reason = reason
        self.cursors: dict[str, int] = {k: 0 for k in script}

    def decide(self, *, agent_id: str, tick: int, observation: dict, prompt: str) -> tuple[dict | None, Receipt]:
        queue = self.script.get(agent_id, [])
        idx = self.cursors.get(agent_id, 0)
        raw: Any
        if idx < len(queue):
            raw = queue[idx]
            self.cursors[agent_id] = idx + 1
        else:
            raw = {"action": "wait"}
        output = json.dumps(raw, sort_keys=True)
        try:
            decision = parse_decision(raw)
            err = None
        except DecisionError as exc:
            decision = None
            err = str(exc)
        receipt = mock_receipt(
            agent_id=agent_id,
            tick=tick,
            model=self.name,
            prompt=prompt,
            output=output,
            reason=self.reason,
            error=err,
        )
        return decision, receipt


class HeuristicProvider:
    """No-LLM demo policy: work if empty-handed, otherwise wander the yard."""

    name = "heuristic-mock"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        self._steps = ("east", "south", "west", "north")

    def decide(self, *, agent_id: str, tick: int, observation: dict, prompt: str) -> tuple[dict | None, Receipt]:
        inventory = observation.get("inventory") or {}
        if not inventory:
            raw: dict[str, Any] = {"action": "work"}
        else:
            direction = self._steps[tick % 4]
            raw = {"action": "move", "direction": direction}
        if tick % 5 == 4:
            raw = {
                "action": "talk",
                "line": f"{observation.get('name', agent_id)} checks the {observation.get('tile')} berth.",
            }
        output = json.dumps(raw, sort_keys=True)
        decision = parse_decision(raw)
        receipt = mock_receipt(
            agent_id=agent_id,
            tick=tick,
            model=self.name,
            prompt=prompt,
            output=output,
            reason=self.reason,
        )
        return decision, receipt


class LiveFlopProvider:
    """Pays for a completion only when official testnet genesis is observed.

    Gateway bearer keys are read from FLOP_GATEWAY_KEY and are never attached
    to receipts, exception messages, or logs.
    """

    name = "flop-gateway"

    def __init__(
        self,
        gateway_url: str = DEFAULT_GATEWAY,
        opener: Callable[..., Any] | None = None,
        api_key: str | None = None,
    ) -> None:
        self.gateway_url = gateway_url.rstrip("/")
        self._opener = opener or _urlopen
        self._api_key = api_key if api_key is not None else os.environ.get("FLOP_GATEWAY_KEY")

    def probe(self) -> Probe:
        url = self.gateway_url + "/health"
        try:
            body, status = self._opener(url, method="GET", timeout=15)
        except Exception as exc:  # noqa: BLE001 — fail closed, hide any credential in the message
            return Probe(ok=False, reason=_safe_err("health probe failed", exc))
        if status != 200:
            return Probe(ok=False, reason=f"health HTTP {status}")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return Probe(ok=False, reason="health response was not JSON")
        network = None
        genesis = None
        raw_status = None
        if isinstance(data, dict):
            raw_status = data.get("status") if isinstance(data.get("status"), str) else None
            net = data.get("network")
            if isinstance(net, dict):
                if isinstance(net.get("network"), str):
                    network = net["network"]
                for key in ("observed_genesis_hash", "expected_genesis_hash", "genesis_hash"):
                    if isinstance(net.get(key), str):
                        genesis = net[key]
                        break
            elif isinstance(net, str):
                network = net
        if not genesis:
            return Probe(
                ok=False,
                reason="health JSON did not include a genesis hash",
                network=network,
                raw_status=raw_status,
            )
        return Probe(
            ok=True,
            reason="ok",
            network=network,
            genesis=genesis,
            raw_status=raw_status,
        )

    def can_settle_on_testnet(self, probe: Probe | None = None) -> tuple[bool, str, Probe]:
        probe = probe if probe is not None else self.probe()
        if not probe.ok:
            return False, probe.reason, probe
        if not probe.is_official_testnet:
            seen = probe.genesis or "unknown genesis"
            net = probe.network or "unknown network"
            return (
                False,
                (
                    f"official gateway reports network={net} genesis={seen}; "
                    f"testnet settlement requires chain {TESTNET_CHAIN_ID} "
                    f"genesis {TESTNET_GENESIS}. no paid request sent"
                ),
                probe,
            )
        return True, "official testnet genesis confirmed", probe

    def decide(self, *, agent_id: str, tick: int, observation: dict, prompt: str) -> tuple[dict | None, Receipt]:
        ok, reason, probe = self.can_settle_on_testnet()
        if not ok:
            # Fail closed: a heuristic decision still moves the demo, but the
            # receipt is a mock and no paid completion is sent.
            fallback = HeuristicProvider(reason=reason)
            decision, receipt = fallback.decide(
                agent_id=agent_id, tick=tick, observation=observation, prompt=prompt
            )
            # Re-label the model so the log shows we intended to use the gateway.
            receipt = mock_receipt(
                agent_id=agent_id,
                tick=tick,
                model=self.name,
                prompt=prompt,
                output=json.dumps({"fallback": "heuristic-mock", "reason": reason}),
                reason=reason,
                request_id=receipt.request_id,
                network_genesis=probe.genesis,
            )
            return decision, receipt
        return self._paid_decide(
            agent_id=agent_id, tick=tick, observation=observation, prompt=prompt, probe=probe
        )

    def _paid_decide(
        self,
        *,
        agent_id: str,
        tick: int,
        observation: dict,
        prompt: str,
        probe: Probe,
    ) -> tuple[dict | None, Receipt]:
        if not self._api_key:
            reason = "testnet genesis confirmed but FLOP_GATEWAY_KEY is not set; no paid request sent"
            return None, mock_receipt(
                agent_id=agent_id,
                tick=tick,
                model=self.name,
                prompt=prompt,
                output="",
                reason=reason,
                network_genesis=probe.genesis,
                error=reason,
            )
        request_id = new_request_id()
        url = self.gateway_url + "/v1/chat/completions"
        payload = {
            "model": "qwen/qwen2.5-0.5b-instruct",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 64,
        }
        try:
            body, status = self._authorized_post(url, payload, request_id)
        except Exception as exc:  # noqa: BLE001
            reason = _safe_err("paid completion failed", exc)
            return None, mock_receipt(
                agent_id=agent_id,
                tick=tick,
                model=self.name,
                prompt=prompt,
                output="",
                reason=reason,
                request_id=request_id,
                network_genesis=probe.genesis,
                error=reason,
            )
        if status != 200:
            reason = f"chat completion HTTP {status}"
            return None, mock_receipt(
                agent_id=agent_id,
                tick=tick,
                model=self.name,
                prompt=prompt,
                output=body[:500],
                reason=reason,
                request_id=request_id,
                network_genesis=probe.genesis,
                error=reason,
            )
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            reason = "chat completion was not JSON"
            return None, mock_receipt(
                agent_id=agent_id,
                tick=tick,
                model=self.name,
                prompt=prompt,
                output=body[:500],
                reason=reason,
                request_id=request_id,
                network_genesis=probe.genesis,
                error=reason,
            )
        output_text = _completion_text(data)
        flop = data.get("x_flop_receipt") if isinstance(data, dict) else None
        flop = flop if isinstance(flop, dict) else {}
        state = flop.get("settlementStatus") or flop.get("state") or "reserved"
        if state not in {"reserved", "estimated", "settled", "released"}:
            state = "reserved"
        try:
            decision = parse_decision(json.loads(output_text)) if output_text else None
            err = None
        except (json.JSONDecodeError, DecisionError) as exc:
            decision = None
            err = str(exc)
        receipt = live_receipt(
            agent_id=agent_id,
            tick=tick,
            model=str(data.get("model") if isinstance(data, dict) else self.name),
            prompt=prompt,
            output=output_text,
            request_id=str(flop.get("request_id") or request_id),
            state=state,
            reserved_spend=_opt_float(flop.get("reserved_spend") or flop.get("reservedSpend")),
            settled_spend=_opt_float(flop.get("settled_spend") or flop.get("settledSpend")),
            settled_spend_raw=_opt_str(flop.get("settled_spend_raw") or flop.get("settledSpendRaw")),
            channel_id=_opt_str(flop.get("channel_id") or flop.get("channelId")),
            terminal_event=_opt_str(flop.get("terminal_event") or flop.get("terminalEvent")),
            network_genesis=probe.genesis or TESTNET_GENESIS,
        )
        if err:
            receipt.error = err
        return decision, receipt

    def _authorized_post(self, url: str, payload: dict, request_id: str) -> tuple[str, int]:
        raw_headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": request_id,
        }
        return self._opener(url, method="POST", timeout=30, data=payload, headers=raw_headers)


def _opt_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _opt_str(val: Any) -> str | None:
    if isinstance(val, str) and val:
        return val
    return None


def _completion_text(data: dict) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def _safe_err(prefix: str, exc: BaseException) -> str:
    # urllib errors can echo the request URL. We never put the key in a URL,
    # but still strip any "Bearer ..." substring just in case.
    text = f"{prefix}: {type(exc).__name__}"
    return text


def _urlopen(
    url: str,
    *,
    method: str,
    timeout: int,
    data: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[str, int]:
    body = None if data is None else json.dumps(data).encode("utf-8")
    hdrs = dict(headers or {})
    # Cloudflare blocks the default Python-urllib user-agent with 403.
    hdrs.setdefault("User-Agent", "joppa-yard/0.1.0")
    req = urllib.request.Request(url, data=body, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8"), resp.getcode()
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        return payload, exc.code
