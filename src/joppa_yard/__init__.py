"""Joppa Yard: original headless port-city sim with FLOP inference receipts."""

__version__ = "0.1.0"

# Official FLOP testnet genesis from docs.flop.network/docs/network-testnet
# (updated 24 Nov 2026). The live provider pays only if a probe observes this hash.
TESTNET_CHAIN_ID = "flop_testnet"
TESTNET_GENESIS = "0x918abd58fb16306b30ef3886514cfaebffecb4de43e82b6f8ec4795c43cfd800"

__all__ = ["TESTNET_CHAIN_ID", "TESTNET_GENESIS", "__version__"]
