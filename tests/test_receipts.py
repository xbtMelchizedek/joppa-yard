import json
from pathlib import Path

from joppa_yard import TESTNET_GENESIS
from joppa_yard.receipts import live_receipt, mock_receipt, sha256_text, write_jsonl


def test_mock_receipt_is_labeled_and_hashes_payloads(tmp_path: Path):
    row = mock_receipt(
        agent_id="silas",
        tick=0,
        model="scripted-mock",
        prompt="hello",
        output='{"action":"wait"}',
        reason="unit test mock",
        network_genesis="0xabc",
    )
    data = row.to_dict()
    assert data["kind"] == "inference_receipt"
    assert data["mock"] is True
    assert data["state"] == "mock"
    assert data["mock_reason"] == "unit test mock"
    assert data["prompt_hash"] == sha256_text("hello")
    assert data["output_hash"] == sha256_text('{"action":"wait"}')
    assert "hello" not in json.dumps(data)
    assert data["settled_spend"] is None
    dest = tmp_path / "receipts.jsonl"
    write_jsonl(dest, [row])
    loaded = json.loads(dest.read_text().splitlines()[0])
    assert loaded["mock"] is True


def test_live_receipt_rejects_unknown_state_and_omits_mock_reason():
    row = live_receipt(
        agent_id="tamar",
        tick=1,
        model="qwen/qwen2.5-0.5b-instruct",
        prompt="p",
        output="o",
        request_id="req-1",
        state="settled",
        reserved_spend=0.002,
        settled_spend=0.001,
        settled_spend_raw="1000000000000000",
        channel_id="ch-1",
        terminal_event="settled",
        network_genesis=TESTNET_GENESIS,
    )
    data = row.to_dict()
    assert data["mock"] is False
    assert "mock_reason" not in data
    assert data["state"] == "settled"
    assert data["channel_id"] == "ch-1"
    assert data["network_genesis"] == TESTNET_GENESIS
    try:
        live_receipt(
            agent_id="tamar",
            tick=1,
            model="m",
            prompt="p",
            output="o",
            request_id="req-2",
            state="mock",
            reserved_spend=None,
            settled_spend=None,
            settled_spend_raw=None,
            channel_id=None,
            terminal_event=None,
            network_genesis=TESTNET_GENESIS,
        )
        raise AssertionError("should have rejected state=mock as live")
    except ValueError as exc:
        assert "state" in str(exc)
