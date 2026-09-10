"""what one endpoint does: a dozen small json-rpc requests, each a yes or a no, with the reason when it is a no."""
from __future__ import annotations

import http.client
import json
import re
import socket
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import NamedTuple

USER_AGENT = "rpcprobe/0.1 (+https://github.com/alinaschanz/rpcprobe)"
ORIGIN = "https://example.org"  # sent once, to see whether a browser page would be allowed to read the answer

# the uniswap v3 factory and its PoolCreated event: a handful of logs a day, so a wide range is
# refused for its width and never for the number of results in it
FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
POOL_CREATED = "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"
LOG_SPANS = (10, 50, 100, 1_000, 10_000)

# the ethereum foundation's old wallet held ether at block 1,000,000; only an archive node still knows
OLD_ADDRESS = "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe"
OLD_BLOCK = 1_000_000
PINGS = 5


class Answer(NamedTuple):
    body: object  # the parsed json (a json-rpc result after call())
    error: str | None  # why there is nothing, in a few words
    headers: dict
    ms: float


@dataclass
class Result:
    name: str
    url: str
    ok: bool = False
    error: str | None = None
    chain_id: int | None = None
    head: int | None = None
    latency_ms: float | None = None
    lag: int | None = None
    logs_range: int = 0
    logs_refusal: str | None = None
    archive: bool = False
    archive_refusal: str | None = None
    batch: bool = False
    receipts: bool = False
    receipts_refusal: str | None = None
    fee_history: int = 0
    blob_base_fee: bool = False
    eth_config: bool = False
    cors: str | None = None
    client: str | None = None

    @property
    def browser(self) -> bool:
        """a page on any site may read the answers."""
        return self.cors in ("*", ORIGIN)


def short_message(text: str, width: int = 70) -> str:
    text = " ".join(str(text).split())
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    return first if len(first) <= width else first[: width - 1] + "…"


def _reason(exc: BaseException) -> str:
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, socket.gaierror):
        return "no such host"
    if isinstance(reason, TimeoutError) or isinstance(exc, TimeoutError):
        return "timed out"
    if isinstance(reason, ConnectionResetError) or isinstance(exc, ConnectionResetError):
        return "connection reset"
    if isinstance(exc, http.client.IncompleteRead):
        return "answer cut off"
    if isinstance(exc, ValueError):
        return "not json"
    return short_message(str(reason) or type(reason).__name__, 50)


def post(url: str, payload, timeout: float = 15.0, origin: str | None = None) -> Answer:
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            got = {k.lower(): v for k, v in resp.headers.items()}
        body = json.loads(raw)
    except urllib.error.HTTPError as exc:
        got = {k.lower(): v for k, v in (exc.headers or {}).items()}
        return Answer(None, f"http {exc.code}", got, (time.perf_counter() - start) * 1000)
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as exc:
        return Answer(None, _reason(exc), {}, (time.perf_counter() - start) * 1000)
    return Answer(body, None, got, (time.perf_counter() - start) * 1000)


def call(url: str, method: str, params: list, timeout: float = 15.0, origin: str | None = None) -> Answer:
    a = post(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout, origin)
    if a.error:
        return a
    if not isinstance(a.body, dict):
        return a._replace(body=None, error="not a json-rpc answer")
    if a.body.get("error") is not None:
        e = a.body["error"]
        return a._replace(body=None, error=short_message(e.get("message", e) if isinstance(e, dict) else e))
    return a._replace(body=a.body.get("result"))


def short_client(version: str) -> str:
    """'Geth/v1.17.1-stable-16783c16/linux-amd64/go1.25.7' -> 'geth 1.17.1'."""
    parts = version.split("/")
    name = parts[0].strip().lower() or "?"
    for part in parts[1:]:
        m = re.match(r"v?(\d+(?:\.\d+)+)", part.strip())
        if m:
            return f"{name} {m.group(1)}"
    return name[:24]


def probe(name: str, url: str, timeout: float = 15.0) -> Result:
    r = Result(name, url)
    a = call(url, "eth_chainId", [], timeout, origin=ORIGIN)
    r.cors = a.headers.get("access-control-allow-origin")
    if a.error:
        r.error = a.error
        return r
    try:
        r.chain_id = int(a.body, 16)
    except (TypeError, ValueError):
        r.error = "the chain id is not a number"
        return r
    if r.chain_id != 1:
        r.error = f"chain id {r.chain_id}, not mainnet"
        return r

    times = []
    for _ in range(PINGS):
        a = call(url, "eth_blockNumber", [], timeout)
        if not a.error and isinstance(a.body, str):
            times.append(a.ms)
            r.head = int(a.body, 16)
    if not times:
        r.error = a.error or "no block number"
        return r
    r.ok, r.latency_ms = True, statistics.median(times)

    to_block = r.head - 5  # a few blocks back, so a node a little behind is not asked for the future
    for span in LOG_SPANS:
        a = call(url, "eth_getLogs", [{"fromBlock": hex(to_block - span + 1), "toBlock": hex(to_block), "address": FACTORY,
                                       "topics": [POOL_CREATED]}], timeout)
        if a.error or not isinstance(a.body, list):
            r.logs_refusal = a.error or "not a list of logs"
            break
        r.logs_range = span

    a = call(url, "eth_getBalance", [OLD_ADDRESS, hex(OLD_BLOCK)], timeout)
    r.archive = not a.error and isinstance(a.body, str) and int(a.body, 16) > 0
    if not r.archive:
        r.archive_refusal = a.error or "a zero balance, which is wrong"

    a = call(url, "eth_getBlockReceipts", [hex(to_block)], timeout)  # every receipt of one block in a single call
    r.receipts = not a.error and isinstance(a.body, list) and len(a.body) > 0
    if not r.receipts:
        r.receipts_refusal = a.error or "no receipts in the answer"

    a = post(url, [{"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []},
                   {"jsonrpc": "2.0", "id": 2, "method": "eth_chainId", "params": []}], timeout)
    r.batch = isinstance(a.body, list) and len(a.body) == 2 and all(isinstance(x, dict) and "result" in x for x in a.body)

    a = call(url, "eth_feeHistory", [hex(1024), "latest", []], timeout)
    if not a.error and isinstance(a.body, dict):
        r.fee_history = max(0, len(a.body.get("baseFeePerGas") or []) - 1)
    r.blob_base_fee = not call(url, "eth_blobBaseFee", [], timeout).error
    a = call(url, "eth_config", [], timeout)
    r.eth_config = not a.error and isinstance(a.body, dict)
    a = call(url, "web3_clientVersion", [], timeout)
    r.client = short_client(a.body) if not a.error and isinstance(a.body, str) else None
    return r


def measure_lag(results: list[Result], timeout: float = 15.0) -> None:
    """one eth_blockNumber to every working endpoint at the same moment; lag is the distance to the highest.
    the heads from the checks themselves were read seconds or minutes apart and would not compare."""
    live = [r for r in results if r.ok]
    if not live:
        return
    with ThreadPoolExecutor(max_workers=len(live)) as pool:
        answers = list(pool.map(lambda r: call(r.url, "eth_blockNumber", [], timeout), live))
    heads = {r.name: int(a.body, 16) for r, a in zip(live, answers, strict=True) if not a.error and isinstance(a.body, str)}
    if heads:
        top = max(heads.values())
        for r in live:
            r.lag = top - heads[r.name] if r.name in heads else None
