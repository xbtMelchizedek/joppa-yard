import json

from joppa_yard import TESTNET_GENESIS
from joppa_yard.providers import DEVNET_GENESIS, LiveFlopProvider, ScriptedProvider
from joppa_yard.world import World


def _health(genesis: str, network: str) -> tuple[str, int]:
    body = json.dumps(
        {
            "status": "ok",
            "network": {
                "network": network,
                "observed_genesis_hash": genesis,
                "expected_genesis_hash": genesis,
            },
        }
    )
    return body, 200


def test_scripted_provider_writes_mock_receipts_and_rejects_bad_json_decisions():
    world = World()
    script = {
        "silas": [{"action": "work"}, {"foo": "nope"}],
    }
    provider = ScriptedProvider(script)
    prompt = "p"
    decision, receipt = provider.decide(
        agent_id="silas", tick=0, observation=world.observation("silas"), prompt=prompt
    )
    assert decision is not None and decision["verb"] == "work"
    assert receipt.mock is True
    assert receipt.state == "mock"
    bad, bad_receipt = provider.decide(
        agent_id="silas", tick=1, observation=world.observation("silas"), prompt=prompt
    )
    assert bad is None
    assert bad_receipt.mock is True
    assert bad_receipt.error is not None


def test_live_provider_refuses_to_pay_when_health_is_devnet():
    paid = {"called": False}

    def opener(url, *, method, timeout, data=None, headers=None):
        if url.endswith("/health"):
            return _health(DEVNET_GENESIS, "devnet")
        paid["called"] = True
        raise AssertionError("paid completion must not be sent on devnet")

    provider = LiveFlopProvider(opener=opener, api_key="should-never-be-sent")
    ok, reason, probe = provider.can_settle_on_testnet()
    assert ok is False
    assert probe.genesis == DEVNET_GENESIS
    assert "devnet" in reason
    assert "no paid request sent" in reason

    world = World()
    decision, receipt = provider.decide(
        agent_id="silas", tick=0, observation=world.observation("silas"), prompt="prompt"
    )
    assert paid["called"] is False
    assert receipt.mock is True
    assert receipt.network_genesis == DEVNET_GENESIS
    assert "no paid request sent" in (receipt.mock_reason or "")
    assert decision is not None  # heuristic fallback still picks a legal action
    # The dummy key must not appear in the receipt.
    blob = json.dumps(receipt.to_dict())
    assert "should-never-be-sent" not in blob
    assert "Bearer" not in blob


def test_live_provider_refuses_when_health_fails_closed():
    def opener(url, *, method, timeout, data=None, headers=None):
        raise OSError("network down")

    provider = LiveFlopProvider(opener=opener, api_key="secret-key")
    ok, reason, probe = provider.can_settle_on_testnet()
    assert ok is False
    assert probe.ok is False
    assert "health probe failed" in reason
    _, receipt = provider.decide(
        agent_id="silas", tick=0, observation=World().observation("silas"), prompt="p"
    )
    assert receipt.mock is True
    assert "secret-key" not in json.dumps(receipt.to_dict())
    assert "secret-key" not in (receipt.mock_reason or "")
    assert "secret-key" not in (receipt.error or "")


def test_live_provider_pays_only_on_official_testnet_genesis():
    calls = []

    def opener(url, *, method, timeout, data=None, headers=None):
        calls.append(method)
        if url.endswith("/health"):
            return _health(TESTNET_GENESIS, "flop_testnet")
        assert method == "POST"
        assert headers is not None
        assert headers.get("Idempotency-Key")
        assert headers.get("Authorization") == "Bearer test-key"
        body = json.dumps(
            {
                "model": "qwen/qwen2.5-0.5b-instruct",
                "choices": [
                    {"message": {"content": json.dumps({"action": "look"})}},
                ],
                "x_flop_receipt": {
                    "state": "reserved",
                    "channelId": "ch-test",
                    "reserved_spend": 0.01,
                    "settled_spend_raw": None,
                },
            }
        )
        return body, 200

    provider = LiveFlopProvider(opener=opener, api_key="test-key")
    ok, reason, probe = provider.can_settle_on_testnet()
    assert ok is True
    assert probe.is_official_testnet is True
    assert "confirmed" in reason

    decision, receipt = provider.decide(
        agent_id="tamar", tick=2, observation=World().observation("tamar"), prompt="p"
    )
    assert "POST" in calls
    assert decision is not None and decision["verb"] == "look"
    assert receipt.mock is False
    assert receipt.state == "reserved"
    assert receipt.channel_id == "ch-test"
    assert receipt.network_genesis == TESTNET_GENESIS
    assert "mock_reason" not in receipt.to_dict()
    # The test key is a fixture, but it still must not be persisted.
    assert "test-key" not in json.dumps(receipt.to_dict())


def test_live_provider_stays_mock_if_testnet_but_no_key():
    def opener(url, *, method, timeout, data=None, headers=None):
        if url.endswith("/health"):
            return _health(TESTNET_GENESIS, "flop_testnet")
        raise AssertionError("no key, so no paid call")

    provider = LiveFlopProvider(opener=opener, api_key="")
    decision, receipt = provider.decide(
        agent_id="eli", tick=0, observation=World().observation("eli"), prompt="p"
    )
    assert decision is None
    assert receipt.mock is True
    assert "FLOP_GATEWAY_KEY" in (receipt.mock_reason or "")
