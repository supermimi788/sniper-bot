from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Candle:
    ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def parse_ohlcv(ohlcv: List[List[float]]) -> List[Candle]:
    return [
        Candle(
            ts_ms=int(row[0]),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
        )
        for row in ohlcv
    ]


def get_latest_candle(candles: List[Candle]) -> Candle:
    if not candles:
        raise ValueError("No candles provided.")
    return candles[-1]

