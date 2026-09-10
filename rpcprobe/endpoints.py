"""public ethereum mainnet json-rpc endpoints that are listed as needing no key (chainlist, the
providers' own pages). some of them have since started asking for one, or stopped answering:
that is what this tool is for. the names are short handles, not brands."""
from __future__ import annotations

from typing import NamedTuple


class Endpoint(NamedTuple):
    name: str
    url: str


ENDPOINTS = (
    Endpoint("publicnode", "https://ethereum-rpc.publicnode.com"),
    Endpoint("drpc", "https://eth.drpc.org"),
    Endpoint("mevblocker", "https://rpc.mevblocker.io"),
    Endpoint("tenderly", "https://gateway.tenderly.co/public/mainnet"),
    Endpoint("tenderly-gw", "https://mainnet.gateway.tenderly.co"),
    Endpoint("blastapi", "https://eth-mainnet.public.blastapi.io"),
    Endpoint("nodies", "https://eth-pokt.nodies.app"),
    Endpoint("flashbots", "https://rpc.flashbots.net"),
    Endpoint("1rpc", "https://1rpc.io/eth"),
    Endpoint("blockrazor", "https://eth.blockrazor.xyz"),
    Endpoint("zan", "https://api.zan.top/eth-mainnet"),
    Endpoint("nownodes", "https://public-eth.nownodes.io"),
    Endpoint("meowrpc", "https://eth.meowrpc.com"),
    Endpoint("onfinality", "https://eth.api.onfinality.io/public"),
    Endpoint("blockpi", "https://ethereum.blockpi.network/v1/rpc/public"),
    Endpoint("merkle", "https://eth.merkle.io"),
    Endpoint("cloudflare", "https://cloudflare-eth.com"),
    Endpoint("llamarpc", "https://eth.llamarpc.com"),
    Endpoint("ankr", "https://rpc.ankr.com/eth"),
    Endpoint("omniatech", "https://endpoints.omniatech.io/v1/eth/mainnet/public"),
    Endpoint("gatewayfm", "https://rpc.eth.gateway.fm"),
)


def pick(names: str | None, extra_urls: list[str] | None = None) -> list[Endpoint]:
    """the built-in list, or the named ones from it, plus any urls given on the command line."""
    chosen = list(ENDPOINTS)
    if names:
        wanted = [n.strip().lower() for n in names.split(",") if n.strip()]
        by_name = {e.name: e for e in ENDPOINTS}
        missing = [n for n in wanted if n not in by_name]
        if missing:
            raise KeyError(", ".join(missing))
        chosen = [by_name[n] for n in wanted]
    for url in extra_urls or []:
        host = url.split("://", 1)[-1].split("/", 1)[0]
        chosen.append(Endpoint(host, url))
    return chosen
