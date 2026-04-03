from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.exchange.ccxt_client import BidAsk


def spread_pct_from_bid_ask(bid_ask: BidAsk) -> float:
    """
    spread% = (ask - bid) / mid
    where mid = (ask + bid) / 2
    """
    bid = bid_ask.bid
    ask = bid_ask.ask
    if ask <= 0 or bid <= 0:
        return float("inf")

    mid = (ask + bid) / 2.0
    if mid <= 0:
        return float("inf")

    return (ask - bid) / mid


def spread_ok(spread_pct: float, max_spread_pct: float) -> bool:
    return spread_pct <= max_spread_pct

