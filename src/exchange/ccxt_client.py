from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import ccxt  # type: ignore


def _okx_perp_symbol(pair: str) -> str:
    """
    Convert "BTCUSDT" -> "BTC/USDT:USDT" (USDT perpetual).
    OKX uses colon suffix for instrument type on many ccxt listings.
    """
    if not pair.endswith("USDT"):
        # Fallback: let ccxt attempt symbol matching (might require manual mapping later).
        return pair

    base = pair[: -len("USDT")]
    return f"{base}/USDT:USDT"


@dataclass(frozen=True)
class BidAsk:
    bid: float
    ask: float


class OKXClient:
    """
    Minimal OKX futures client (via ccxt) for:
    - fetching OHLCV candles
    - fetching bid/ask (for spread checks)

    Paper/live order placement will be added in later steps.
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        api_passphrase: str = "",
    ) -> None:
        self._exchange = ccxt.okx(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "password": api_passphrase,
                # Safer defaults for bot usage.
                "enableRateLimit": True,
                # Increase HTTP timeout (milliseconds) to make transient
                # latency spikes less likely to cause failures.
                "timeout": 30000,  # 30 seconds (temporary connectivity test)
                # OKX swap/USDT perpetual is commonly the defaultType="swap"
                "options": {"defaultType": "swap"},
            }
        )

    def load_markets(self) -> None:
        # Helps ccxt resolve the exact symbols.
        self._exchange.load_markets()

    def _symbol(self, pair: str) -> str:
        return _okx_perp_symbol(pair)

    def fetch_ohlcv(
        self,
        pair: str,
        timeframe: str,
        limit: int = 200,
    ) -> List[List[float]]:
        """
        Returns ccxt OHLCV format:
        [ [timestamp_ms, open, high, low, close, volume], ... ]
        """
        symbol = self._symbol(pair)
        ohlcv = self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return ohlcv

    def fetch_bid_ask(self, pair: str) -> BidAsk:
        symbol = self._symbol(pair)
        ticker = self._exchange.fetch_ticker(symbol)

        bid = ticker.get("bid")
        ask = ticker.get("ask")
        if bid is None or ask is None:
            # If ticker doesn't include bid/ask, fall back to order book.
            ob = self._exchange.fetch_order_book(symbol, limit=5)
            best_bids = ob.get("bids") or []
            best_asks = ob.get("asks") or []
            if not best_bids or not best_asks:
                raise RuntimeError(f"Could not fetch bid/ask for {pair}")
            bid = float(best_bids[0][0])
            ask = float(best_asks[0][0])

        return BidAsk(bid=float(bid), ask=float(ask))

