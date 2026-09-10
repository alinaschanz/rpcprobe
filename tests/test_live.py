"""talks to the public endpoints. skipped unless RPCPROBE_LIVE=1."""
import os

import pytest

from rpcprobe import probe
from rpcprobe.endpoints import ENDPOINTS

pytestmark = pytest.mark.skipif(os.environ.get("RPCPROBE_LIVE") != "1", reason="set RPCPROBE_LIVE=1")


def test_some_built_in_endpoints_answer_on_mainnet():
    answered = [e.name for e in ENDPOINTS[:8] if probe.call(e.url, "eth_chainId", []).body == "0x1"]
    assert len(answered) >= 3, answered


def test_the_event_and_the_old_balance_are_real():
    """a wide log query that comes back empty and an archive answer of zero would both look like "works"."""
    found_logs = found_balance = False
    for e in ENDPOINTS[:8]:
        head = probe.call(e.url, "eth_blockNumber", [])
        if head.error:
            continue
        to_block = int(head.body, 16) - 5
        logs = probe.call(e.url, "eth_getLogs", [{"fromBlock": hex(to_block - 9_999), "toBlock": hex(to_block),
                                                  "address": probe.FACTORY, "topics": [probe.POOL_CREATED]}])
        found_logs = found_logs or (not logs.error and len(logs.body) > 0)
        balance = probe.call(e.url, "eth_getBalance", [probe.OLD_ADDRESS, hex(probe.OLD_BLOCK)])
        found_balance = found_balance or (not balance.error and int(balance.body, 16) > 0)
        if found_logs and found_balance:
            return
    assert found_logs, "no endpoint returned a PoolCreated log in 10,000 blocks"
    assert found_balance, "no endpoint knew the balance at block 1,000,000"
