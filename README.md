# Joppa Yard

A tiny, original, headless port-city sim. Two or three agents walk a docks yard, each action goes through an inference provider, and every call is written down as a FLOP-shaped receipt.

This is not Grand Theft Auto, not a console emulator, and not FiveM. The world, map and characters are original. The name comes from the historical port of Joppa — a yard as in a docks yard.

## Why it exists

Flop Network's testnet airdrop is measured on what an agent *does*, specifically inference it actually pays for, not faucet tokens it holds. Agents still need somewhere legal to spend that inference. Joppa Yard is a first slice of that somewhere: a shared world we own, with receipts we can later settle in testnet FLOP.

The in-repo reminder is in [LEGAL.md](LEGAL.md). The short version:

- Official testnet settlement was **not** live when v0.1 shipped. The public faucet and gateway still identified as **devnet**. Until a probe sees the official testnet genesis, receipts are written with `"mock": true` and a reason. The sim will not silently spend on devnet and call it testnet farming.
- Early testnet activity is **unscored**. Official docs say earning starts at a future announced activation block, with no backfill.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/joppa-yard --ticks 6 --out runs/demo
```

That writes `events.jsonl`, `receipts.jsonl` and a draft `storyboard.md` under the output directory. The storyboard is a draft. It is not posted. Any public X wording goes through palmer's Twitter assistant, not this tool.

To *attempt* live settlement (still fail-closed unless the official gateway reports the testnet genesis):

```bash
.venv/bin/joppa-yard --ticks 4 --out runs/live --provider live
```

Do not put a gateway key on the command line. If you ever have a testnet gateway key, set `FLOP_GATEWAY_KEY` in the environment and keep the value out of logs. Today's live probe should refuse to pay and fall back to mock receipts.

## Receipt schema

Each row matches the public gateway receipt fields we can usefully persist, plus our own labels:

| field | meaning |
|-------|---------|
| `mock` | `true` unless this call settled (or reserved) on official testnet |
| `mock_reason` | why a mock was written; omitted on live rows |
| `request_id` | idempotency / receipt id |
| `state` | `mock`, or `reserved` / `estimated` / `settled` / `released` |
| `reserved_spend`, `settled_spend`, `settled_spend_raw`, `channel_id`, `terminal_event` | gateway fields; null on mocks |
| `prompt_hash`, `output_hash` | sha256 of the prompt and the model output; raw prompts stay out of the default receipt log |
| `network_genesis` | genesis the provider observed, when it probed |

## Design notes (dev-taste G0 / G1)

Pain, one sentence: agents need a legal shared world that records one inference receipt per action and will settle in testnet FLOP once the official API actually supports it.

Invariants, tested:

- Agents cannot walk on sea tiles.
- Two agents cannot occupy the same tile; a bump is a no-op, not a teleport.
- Every applied (or rejected) decision writes exactly one receipt.
- `mock` is true unless the provider confirmed official testnet settlement.
- Trades conserve cargo: the crate moves from seller to buyer, it is not duplicated or destroyed.
- The live provider never sends a paid completion when health/genesis is not testnet.
- Output directories do not receive credentials.

This is not a contract repo, so the adversarial contract checklist is N/A. The trust boundary that remains: treat the official gateway as an untrusted reporter, persist what it returns, and do not invent a settled spend.

## License

MIT. No third-party game assets are included.
