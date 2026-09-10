# data

written by the [daily workflow](../.github/workflows/daily.yml) at 00:53 utc, from a github runner.

`daily.csv`: one row per endpoint per utc date. columns:

- `date_utc`, `endpoint` (the short name in `rpcprobe/endpoints.py`), `url`
- `ok`: 1 when it answered `eth_chainId` with mainnet and `eth_blockNumber`; `error`: why not, in a few words
- `latency_ms`: median of five `eth_blockNumber` round trips from the runner
- `lag`: blocks behind the highest head among the endpoints, read at one moment
- `logs_range`: the widest `eth_getLogs` range that answered, of 10 / 50 / 100 / 1,000 / 10,000 blocks, for
  the uniswap v3 factory's `PoolCreated` event (rare, so a refusal is about the range, never about the count)
- `archive`: 1 when it knew an address's balance at block 1,000,000
- `batch`: 1 when a two-call batch came back with two results
- `fee_history`: how many blocks `eth_feeHistory` returned when asked for 1,024
- `blob_base_fee`, `eth_config`: 1 when those methods answered
- `browser`: 1 when the answer allows any origin (`access-control-allow-origin`), so a web page can use it
- `client`: from `web3_clientVersion`, shortened; some gateways report a made-up one

a rerun for the same day replaces that day's rows. columns are only ever appended.
