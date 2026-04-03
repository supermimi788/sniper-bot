from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from src.data.candles import Candle, get_latest_candle, parse_ohlcv
from src.data.spread import spread_pct_from_bid_ask
from src.exchange.ccxt_client import BidAsk, OKXClient


@dataclass(frozen=True)
class PairSnapshot:
    spread_pct: float
    candles_4h: List[Candle]
    candles_1h: List[Candle]
    candles_15m: List[Candle]

    def latest_15m(self) -> Candle:
        return get_latest_candle(self.candles_15m)


class MarketData:
    def __init__(self, exchange: OKXClient) -> None:
        self.exchange = exchange

        # Lookback sizes are not part of the strategy rules themselves.
        # They just ensure we have enough candles for EMA50 + structure checks.
        self.bias_4h_lookback = 120
        self.context_1h_lookback = 120
        self.entry_15m_lookback = 240

    def get_spread_pct(self, pair: str) -> float:
        bid_ask: BidAsk = self.exchange.fetch_bid_ask(pair)
        return spread_pct_from_bid_ask(bid_ask)

    def get_candles(self, pair: str, timeframe: str, limit: int) -> List[Candle]:
        ohlcv = self.exchange.fetch_ohlcv(pair=pair, timeframe=timeframe, limit=limit)
        return parse_ohlcv(ohlcv)

    def get_latest_candle(self, pair: str, timeframe: str) -> Candle:
        candles = self.get_candles(pair=pair, timeframe=timeframe, limit=3)
        return get_latest_candle(candles)

    def get_pair_snapshot(self, pair: str) -> PairSnapshot:
        """
        Fetches spread + 4H/1H/15M candles for a pair.
        Includes simple retry logic and clear console logging so that
        transient connectivity issues to OKX don't immediately kill the scan.
        """
        last_error: Exception | None = None
        # 2 attempts total keeps the bot responsive while still being resilient.
        # Fetching is sequential (no concurrency) for easier debugging under light load.
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                spread_pct = self.get_spread_pct(pair)
                print(f"[market_data] {pair} spread fetched successfully: {spread_pct:.6f}")
                candles_4h = self.get_candles(pair, timeframe="4h", limit=self.bias_4h_lookback)
                print(f"[market_data] {pair} candles fetched successfully: 4h={len(candles_4h)}")
                candles_1h = self.get_candles(pair, timeframe="1h", limit=self.context_1h_lookback)
                print(f"[market_data] {pair} candles fetched successfully: 1h={len(candles_1h)}")
                candles_15m = self.get_candles(pair, timeframe="15m", limit=self.entry_15m_lookback)
                print(f"[market_data] {pair} candles fetched successfully: 15m={len(candles_15m)}")

                return PairSnapshot(
                    spread_pct=spread_pct,
                    candles_4h=candles_4h,
                    candles_1h=candles_1h,
                    candles_15m=candles_15m,
                )
            except Exception as e:
                last_error = e
                print(
                    f"[market_data] error fetching snapshot for {pair} "
                    f"(attempt {attempt}/{max_attempts}) "
                    f"type={type(e).__name__} repr={e!r}"
                )

        # If we get here, all attempts failed.
        raise RuntimeError(f"Failed to fetch market snapshot for {pair} after {max_attempts} attempts") from last_error

