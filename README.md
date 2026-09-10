# rpcprobe

[![ci](https://github.com/alinaschanz/rpcprobe/actions/workflows/ci.yml/badge.svg)](https://github.com/alinaschanz/rpcprobe/actions/workflows/ci.yml)
![python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab)
![license mit](https://img.shields.io/badge/license-MIT-2b7a74)
[![release](https://img.shields.io/github/v/release/alinaschanz/rpcprobe?color=2b7a74)](https://github.com/alinaschanz/rpcprobe/releases)
[![openssf scorecard](https://api.scorecard.dev/projects/github.com/alinaschanz/rpcprobe/badge)](https://scorecard.dev/viewer/?uri=github.com/alinaschanz/rpcprobe)

which public ethereum rpcs answer today, and what they let you do. every endpoint that is listed
somewhere as "no key needed" gets the same dozen small json-rpc requests: the chain id, five pings,
log queries of growing width, one archive read, a batch, 1,024 blocks of fee history, the blob
fee, `eth_config`, and whether a web page may read the answer. a table, json, and a dataset that
fills itself every night.

```
$ rpcprobe
public ethereum rpcs, checked 2026-09-10 13:52 utc from this machine: 12 of 21 answer, head 25,947,413

endpoint     p50 ms  lag    logs archive batch fee hist blob fee eth_config browser  client
publicnode      228    0      50      no   yes     1024      yes        yes     yes  geth 1.17.1
tenderly-gw     239    0  10,000     yes   yes     1024      yes         no     yes  tenderly 1.0
tenderly        239    0  10,000     yes   yes     1024      yes         no     yes  tenderly 1.0
drpc            256    0  10,000     yes   yes     1024       no         no     yes  geth 10.0.0
nodies          281    0      50     yes   yes     1024      yes        yes     yes  reth 2.4.1
blastapi        315    0      10     yes   yes     1024       no         no     yes  reth 2.4.0
blockrazor      316    0      10      no   yes     1024      yes        yes     yes  geth 1.17.5
mevblocker      347    0  10,000     yes   yes     1024      yes         no     yes  mevblocker
1rpc            392    1       -      no   yes        -       no         no     yes
flashbots       557    0  10,000      no   yes     1024      yes         no     yes  reth 1.11.2
zan             646    0       -      no   yes     1024      yes         no     yes  geth 1.17.5
meowrpc        1027    0       -      no    no        -      yes         no     yes

no answer, or not without an account:
  nownodes     connection reset
  onfinality   http 429
  blockpi      http 521
  merkle       http 429
  cloudflare   Cannot fulfill request
  llamarpc     http 525
  ankr         Unauthorized: You must authenticate your request with an API key.
  omniatech    http 521
  gatewayfm    http 503

p50: median of five eth_blockNumber round trips from here. lag: blocks behind the highest head, read at one moment.
logs: the widest range of blocks answered for one address and one event (tried 10, 50, 100, 1,000, 10,000).
archive: an address's balance at block 1,000,000. browser: the answer carries access-control-allow-origin.
```

twelve of twenty-one, at 13:52 utc on 10 september. every script i publish carries a fallback list
of endpoints, and this is how that list gets made: tenderly, drpc and mevblocker answer a 10,000
block log query and know old state; publicnode answers fastest but stops at 50 blocks of logs and
keeps no archive; ankr wants an account now; cloudflare's and llamarpc's endpoints, still in a lot of
tutorials, did not answer at all.

## install

```
pipx install git+https://github.com/alinaschanz/rpcprobe
```

or clone it and run `python -m rpcprobe` from the folder. python 3.10 or newer, no dependencies.

## use

```
rpcprobe                                   # every built-in endpoint, three at a time, about a minute
rpcprobe --only publicnode,drpc,tenderly   # just these (--list shows the names)
rpcprobe --rpc http://localhost:8545       # your own node next to them
rpcprobe --json                            # everything, including why a check said no
rpcprobe --csv today.csv
rpcprobe --summary-append data/daily.csv --quiet   # one row per endpoint per day, the dataset
```

## what is checked

| check | request | why it matters |
| --- | --- | --- |
| mainnet | `eth_chainId`, with an `Origin` header | a url that serves another chain is worse than one that is down |
| p50 | five `eth_blockNumber` round trips, the median | the fast path of every script |
| lag | one `eth_blockNumber` to all working endpoints at the same moment | a node minutes behind answers happily with old data |
| logs | `eth_getLogs` for the uniswap v3 factory's `PoolCreated`, 10 / 50 / 100 / 1,000 / 10,000 blocks | the event is rare, so a refusal is about the width of the range, never about the number of results |
| archive | `eth_getBalance` of an address at block 1,000,000 | only an archive node still has that state |
| batch | two calls in one request | fewer round trips for anything that reads many blocks |
| fee hist | `eth_feeHistory` for 1,024 blocks, how many came back | [gasweek](https://github.com/alinaschanz/gasweek) pages through a week this way |
| blob fee | `eth_blobBaseFee` | the fee for blob space, eip-4844 |
| eth_config | `eth_config`, eip-7910 | the fork parameters, blob target and max included, straight from the node |
| browser | `access-control-allow-origin` on the first answer | whether a web page may use the endpoint at all |
| client | `web3_clientVersion`, shortened | some gateways report a made-up one |

each endpoint gets about fifteen small requests, three endpoints at a time. when a check says no, the
json says why, in the endpoint's own words (`Block range too large: maximum allowed is 50 blocks`,
`historical state is not available`).

## reading the table

- latency is from wherever this runs. from a laptop in berlin it is not what a server in virginia
  sees; compare endpoints within one run, and days within the dataset.
- `logs 50` is not "broken": most scripts ask for 25 to 50 blocks at a time on a public node anyway.
  `-` means even 10 blocks were refused, usually a rate limit on that method.
- a rate limit (429) today can be fine tomorrow. the dataset is there so that one bad hour does not
  decide anything.

## the dataset

`data/daily.csv` gets one row per endpoint every night at 00:53 utc, from a github runner, so the
latency column compares from day to day. columns are in [data/README.md](data/README.md); a rerun on
the same day replaces the day.

## exit codes and scripting

`0` when at least one endpoint answered, `2` when none did or a flag was wrong. `rpcprobe --json | jq
'.endpoints[] | select(.ok and .archive and .logs_range >= 1000) | .url'` is a fallback list for a
script that reads history.

## see also

- [blobwatch](https://github.com/alinaschanz/blobwatch), [gasweek](https://github.com/alinaschanz/gasweek),
  [bigmoves](https://github.com/alinaschanz/bigmoves): the scripts that live on these endpoints
- the notes: [alinaschanz.life](https://alinaschanz.life), the short version on [x](https://x.com/alinaschanz)

## verify a release

every release carries the sdist and the wheel, a `SHA256SUMS` file, an opentimestamps proof of that
file, and a build provenance attestation made in github's own signing flow. with the files downloaded
into one folder:

    sha256sum -c SHA256SUMS
    gh attestation verify ./*.whl --owner alinaschanz
    ots verify SHA256SUMS.ots

the commit itself is [signed](https://alinaschanz.life/verify/#commits).

## license

[mit](LICENSE). the endpoints belong to the people who run them; this only asks them simple questions.
