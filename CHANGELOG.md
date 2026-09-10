# changelog

all notable changes to rpcprobe. the format follows [keep a changelog](https://keepachangelog.com/en/1.1.0/),
versions follow [semver](https://semver.org/) as far as a command line tool has an api.

## [unreleased]

- `eth_getBlockReceipts` for one recent block, a `receipts` column, and `block_receipts` appended to the dataset

## [0.1.0] - 2026-09-10

first cut: twenty-one public mainnet endpoints, a dozen checks each.

- chain id, latency (median of five), lag read at one moment, the widest `eth_getLogs` range for a rare event,
  archive state at block 1,000,000, batches, `eth_feeHistory` depth, `eth_blobBaseFee`, `eth_config`, cors, client
- the reason for every no, in the endpoint's own words
- the table, `--json`, `--csv`, `--summary-append` and a daily workflow that writes `data/daily.csv`
