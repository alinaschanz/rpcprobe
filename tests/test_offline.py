"""offline: every check against a fake transport, the table, json, csv and the daily file."""
import csv
import http.client
import json
import socket
import urllib.error

from rpcprobe import cli, endpoints, probe
from rpcprobe.endpoints import Endpoint, pick
from rpcprobe.probe import Answer, _reason, measure_lag, short_client, short_message

GOOD, LIMITED, DEAD, POLYGON = "https://good.example", "https://limited.example/rpc", "https://dead.example", "https://polygon.example"


def fake_post(url, payload, timeout=15.0, origin=None):
    if url == DEAD:
        return Answer(None, "http 525", {}, 5.0)
    if isinstance(payload, list):
        if url == LIMITED:
            return Answer(None, "http 400", {}, 5.0)
        return Answer([{"jsonrpc": "2.0", "id": 1, "result": "0x10"}, {"jsonrpc": "2.0", "id": 2, "result": "0x1"}], None, {}, 5.0)
    method, params = payload["method"], payload["params"]
    headers = {"access-control-allow-origin": "*"} if url == GOOD else {}

    def ok(result, ms=5.0):
        return Answer({"jsonrpc": "2.0", "id": 1, "result": result}, None, headers, ms)

    def err(message):
        return Answer({"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": message}}, None, headers, 5.0)

    if method == "eth_chainId":
        return ok("0x89" if url == POLYGON else "0x1")
    if method == "eth_blockNumber":
        return ok(hex(25_000_000 - (2 if url == LIMITED else 0)), 40.0 if url == GOOD else 120.0)
    if method == "eth_getLogs":
        span = int(params[0]["toBlock"], 16) - int(params[0]["fromBlock"], 16) + 1
        assert params[0]["topics"] == [probe.POOL_CREATED]
        return err("Block range too large: maximum allowed is 50 blocks") if url == LIMITED and span > 50 else ok([])
    if method == "eth_getBalance":
        assert params == [probe.OLD_ADDRESS, hex(1_000_000)]
        return ok("0x13da671e0d63ee48e48c0") if url == GOOD else err("historical state is not available")
    if method == "eth_getBlockReceipts":
        if url == GOOD:
            return ok([{"transactionHash": "0x01", "gasUsed": "0x5208"}])
        return err("the method eth_getBlockReceipts does not exist/is not available")
    if method == "eth_feeHistory":
        n = 1024 if url == GOOD else 100
        return ok({"oldestBlock": "0x1", "baseFeePerGas": ["0x1"] * (n + 1)})
    if method == "eth_blobBaseFee":
        return ok("0x1") if url == GOOD else err("the method eth_blobBaseFee does not exist/is not available")
    if method == "eth_config":
        return ok({"current": {"blobSchedule": {"target": 14, "max": 21}}}) if url == GOOD else err("method not found")
    if method == "web3_clientVersion":
        return ok("Geth/v1.17.1-stable-16783c16/linux-amd64/go1.25.7" if url == GOOD else "reth/v2.4.0-943af24/x86_64-unknown-linux-gnu")
    raise AssertionError(method)


def test_a_good_endpoint(monkeypatch):
    monkeypatch.setattr(probe, "post", fake_post)
    r = probe.probe("good", GOOD)
    assert r.ok and r.error is None and r.chain_id == 1 and r.head == 25_000_000 and r.latency_ms == 40.0
    assert r.logs_range == 10_000 and r.logs_refusal is None
    assert r.archive and r.batch and r.receipts and r.fee_history == 1024 and r.blob_base_fee and r.eth_config
    assert r.browser and r.client == "geth 1.17.1"


def test_a_limited_endpoint_says_why(monkeypatch):
    monkeypatch.setattr(probe, "post", fake_post)
    r = probe.probe("limited", LIMITED)
    assert r.ok and r.logs_range == 50 and r.logs_refusal == "Block range too large: maximum allowed is 50 blocks"
    assert not r.archive and r.archive_refusal == "historical state is not available"
    assert not r.batch and r.fee_history == 100 and not r.blob_base_fee and not r.eth_config
    assert not r.receipts and r.receipts_refusal == "the method eth_getBlockReceipts does not exist/is not available"
    assert not r.browser and r.client == "reth 2.4.0"


def test_dead_and_wrong_chain(monkeypatch):
    monkeypatch.setattr(probe, "post", fake_post)
    dead = probe.probe("dead", DEAD)
    assert not dead.ok and dead.error == "http 525" and dead.head is None
    other = probe.probe("polygon", POLYGON)
    assert not other.ok and other.error == "chain id 137, not mainnet"


def test_lag_is_read_at_one_moment(monkeypatch):
    monkeypatch.setattr(probe, "post", fake_post)
    results = [probe.probe("good", GOOD), probe.probe("limited", LIMITED), probe.probe("dead", DEAD)]
    measure_lag(results)
    assert [r.lag for r in results] == [0, 2, None]


def test_small_helpers():
    assert short_client("Tenderly/1.0") == "tenderly 1.0"
    assert short_client("MEVblocker") == "mevblocker"
    assert short_client("Geth/v10.0.0/drpc") == "geth 10.0.0"
    ankr = ("Unauthorized: You must authenticate your request with an API key. Create an account on https://www.ankr.com/rpc/ "
            "and generate your personal API key for free.")
    assert short_message(ankr) == "Unauthorized: You must authenticate your request with an API key."
    assert short_message("x" * 100).endswith("…") and len(short_message("x" * 100)) == 70
    assert _reason(urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))) == "no such host"
    assert _reason(TimeoutError()) == "timed out"
    assert _reason(http.client.IncompleteRead(b"partial")) == "answer cut off"
    assert _reason(ValueError("Expecting value")) == "not json"


def test_pick():
    assert [e.name for e in pick("drpc, publicnode")] == ["drpc", "publicnode"]
    assert pick(None, ["https://my.node.example:8545/rpc"])[-1] == Endpoint("my.node.example:8545", "https://my.node.example:8545/rpc")
    try:
        pick("nope")
    except KeyError as exc:
        assert "nope" in str(exc)
    else:
        raise AssertionError("an unknown name should fail")


def test_cli_table_json_and_the_daily_file(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(probe, "post", fake_post)
    monkeypatch.setattr(endpoints, "ENDPOINTS", (Endpoint("limited", LIMITED), Endpoint("good", GOOD), Endpoint("dead", DEAD)))
    path = tmp_path / "daily.csv"
    assert cli.main(["--summary-append", str(path)]) == 0
    out = capsys.readouterr().out
    assert "2 of 3 answer, head 25,000,000" in out
    rows = [line for line in out.splitlines() if line.startswith(("good ", "limited "))]
    assert rows[0].startswith("good") and "10,000" in rows[0] and rows[1].split()[3] == "50"
    assert "dead         http 525" in out
    assert cli.main(["--summary-append", str(path), "--quiet"]) == 0  # the same day again: replaced, not doubled
    with open(path, encoding="utf-8") as f:
        daily = list(csv.DictReader(f))
    assert [r["endpoint"] for r in daily] == ["dead", "good", "limited"] and daily[1]["logs_range"] == "10000" and daily[2]["lag"] == "2"
    assert [r["block_receipts"] for r in daily] == ["0", "1", "0"] and list(daily[0])[-1] == "block_receipts"  # appended, not inserted
    assert cli.main(["--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert len(doc["endpoints"]) == 3 and doc["endpoints"][1]["browser"] is True


def test_cli_edges(monkeypatch, capsys):
    monkeypatch.setattr(probe, "post", fake_post)
    assert cli.main(["--only", "nope"]) == 2
    assert cli.main(["--workers", "0"]) == 2
    assert cli.main(["--list"]) == 0 and "publicnode" in capsys.readouterr().out
    monkeypatch.setattr(endpoints, "ENDPOINTS", (Endpoint("dead", DEAD),))
    assert cli.main(["--quiet"]) == 2  # nothing answered
