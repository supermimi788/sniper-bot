from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from src.data.candles import Candle
from src.strategy.zones import Zone, latest_resistance_zone, latest_support_zone, resistance_reaction, support_reaction


@dataclass(frozen=True)
class Context1H:
    support_context: bool
    resistance_context: bool
    support_zone: Optional[Zone]
    resistance_zone: Optional[Zone]


def compute_context_1h(candles_1h: List[Candle]) -> Context1H:
    """
    1H context:
    - For BUY entries we need support context.
    - For SELL entries we need resistance context.

    Implementation uses the same zone idea as bias reaction:
    - support context = touch support zone + close above its upper edge
    - resistance context = touch resistance zone + close below its lower edge
    """
    if len(candles_1h) < 30:
        return Context1H(
            support_context=False,
            resistance_context=False,
            support_zone=None,
            resistance_zone=None,
        )

    last = candles_1h[-1]
    support_zone = latest_support_zone(candles_1h)
    resistance_zone = latest_resistance_zone(candles_1h)

    sup_ok = support_zone is not None and support_reaction(last, support_zone)
    res_ok = resistance_zone is not None and resistance_reaction(last, resistance_zone)

    return Context1H(
        support_context=sup_ok,
        resistance_context=res_ok,
        support_zone=support_zone if sup_ok else None,
        resistance_zone=resistance_zone if res_ok else None,
    )

