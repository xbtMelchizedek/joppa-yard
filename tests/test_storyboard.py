from joppa_yard.receipts import mock_receipt
from joppa_yard.storyboard import DRAFT_BANNER, render_storyboard


def test_storyboard_is_marked_draft_and_summarizes_a_run():
    events = [
        {
            "tick": 0,
            "agent_id": "silas",
            "name": "Silas",
            "verb": "work",
            "result": {"ok": True, "item": "rope"},
            "tile": "dock",
        },
        {
            "tick": 0,
            "agent_id": "tamar",
            "name": "Tamar",
            "verb": "talk",
            "result": {"ok": True, "line": "the market is open"},
            "tile": "market",
        },
    ]
    receipts = [
        mock_receipt(
            agent_id="silas", tick=0, model="m", prompt="p", output="o", reason="test"
        ),
        mock_receipt(
            agent_id="tamar", tick=0, model="m", prompt="p", output="o", reason="test"
        ),
    ]
    text = render_storyboard(events, receipts)
    assert text.startswith("# Joppa Yard")
    assert DRAFT_BANNER in text
    assert "2 mock, 0 live" in text
    assert "Silas worked the dock and took rope." in text
    assert "the market is open" in text
    assert "bitcoinPalmer" in text
