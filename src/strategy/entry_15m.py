from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from config import settings
from src.data.candles import Candle
from src.strategy.bias_4h import Bias4H
from src.strategy.context_1h import Context1H
from src.strategy.sweeps import detect_sweep_high, detect_sweep_low
from src.strategy.zones import Zone, touch_resistance_zone, touch_support_zone


@dataclass(frozen=True)
class EntrySetup:
    side: str  # "long" or "short"

    # Entry timing/price
    entry_ts_ms: int
    entry_price: float

    # Fixed stop + fixed final TP (2.5R)
    sl_price: float
    final_tp_price: float

    # Scoring booleans (must follow the scoring table)
    htf_ok: bool
    context_ok: bool
    zone_ok: bool
    sweep_ok: bool
    rejection_ok: bool
    confirmation_ok: bool
    rr_ok: bool


def _sl_price(entry_price: float, side: str) -> float:
    if side == "long":
        return entry_price * (1.0 - settings.STOP_LOSS_DISTANCE_PCT)
    return entry_price * (1.0 + settings.STOP_LOSS_DISTANCE_PCT)


def _tp_final(entry_price: float, side: str) -> float:
    # Final TP is always 2.5R. 1R equals the fixed SL distance (5%).
    r_pct = settings.STOP_LOSS_DISTANCE_PCT
    if side == "long":
        return entry_price * (1.0 + settings.FINAL_TP_R_MULTIPLIER * r_pct)
    return entry_price * (1.0 - settings.FINAL_TP_R_MULTIPLIER * r_pct)


def _is_buy_bias_ok(bias: Bias4H) -> bool:
    return bias.bias_type in {"bullish", "range_lower"}


def _is_sell_bias_ok(bias: Bias4H) -> bool:
    return bias.bias_type in {"bearish", "range_upper"}


def _bullish_rejection(rejection: Candle, support_zone: Zone) -> bool:
    # Touch is checked separately; rejection means bullish candle that closes back above the zone lower edge.
    return (rejection.close > rejection.open) and (rejection.close > support_zone.lower)


def _bearish_rejection(rejection: Candle, resistance_zone: Zone) -> bool:
    # Touch is checked separately; rejection means bearish candle that closes back below the zone upper edge.
    return (rejection.close < rejection.open) and (rejection.close < resistance_zone.upper)


def _bullish_confirmation(confirmation: Candle, rejection: Candle) -> bool:
    # Relaxed confirmation: normal continuation is enough.
    # Accept either:
    # - bullish close above rejection close, or
    # - higher low / higher high continuation versus rejection candle.
    if (confirmation.close > confirmation.open) and (confirmation.close > rejection.close):
        return True
    return (confirmation.low >= rejection.low) and (confirmation.high >= rejection.high)


def _bearish_confirmation(confirmation: Candle, rejection: Candle) -> bool:
    # Relaxed confirmation: normal continuation is enough.
    if (confirmation.close < confirmation.open) and (confirmation.close < rejection.close):
        return True
    return (confirmation.high <= rejection.high) and (confirmation.low <= rejection.low)


def build_long_setup(candles_15m: List[Candle], bias: Bias4H, context: Context1H) -> Optional[EntrySetup]:
    if len(candles_15m) < 3:
        return None
    if bias.bias_type == "range_middle":
        return None
    if not _is_buy_bias_ok(bias):
        return None
    if not context.support_context or context.support_zone is None:
        return None

    rejection = candles_15m[-2]
    confirmation = candles_15m[-1]
    support_zone = context.support_zone

    zone_ok = touch_support_zone(rejection, support_zone)

    sweep_ok, _, _ = detect_sweep_low(candles_15m, sweep_candle_index=len(candles_15m) - 2)

    rejection_ok = zone_ok and _bullish_rejection(rejection, support_zone)

    confirmation_ok = _bullish_confirmation(confirmation, rejection)

    if not (zone_ok and sweep_ok and rejection_ok and confirmation_ok):
        return None

    entry_price = confirmation.close
    entry_ts_ms = confirmation.ts_ms
    sl = _sl_price(entry_price, side="long")
    final_tp = _tp_final(entry_price, side="long")

    # RR validity: with fixed SL and TP model, RR is structurally valid if we got here.
    rr_ok = True

    return EntrySetup(
        side="long",
        entry_ts_ms=entry_ts_ms,
        entry_price=entry_price,
        sl_price=sl,
        final_tp_price=final_tp,
        htf_ok=True,
        context_ok=True,
        zone_ok=zone_ok,
        sweep_ok=sweep_ok,
        rejection_ok=rejection_ok,
        confirmation_ok=confirmation_ok,
        rr_ok=rr_ok,
    )


def build_short_setup(candles_15m: List[Candle], bias: Bias4H, context: Context1H) -> Optional[EntrySetup]:
    if len(candles_15m) < 3:
        return None
    if bias.bias_type == "range_middle":
        return None
    if not _is_sell_bias_ok(bias):
        return None
    if not context.resistance_context or context.resistance_zone is None:
        return None

    rejection = candles_15m[-2]
    confirmation = candles_15m[-1]
    resistance_zone = context.resistance_zone

    zone_ok = touch_resistance_zone(rejection, resistance_zone)
    sweep_ok, _, _ = detect_sweep_high(candles_15m, sweep_candle_index=len(candles_15m) - 2)

    rejection_ok = zone_ok and _bearish_rejection(rejection, resistance_zone)
    confirmation_ok = _bearish_confirmation(confirmation, rejection)

    if not (zone_ok and sweep_ok and rejection_ok and confirmation_ok):
        return None

    entry_price = confirmation.close
    entry_ts_ms = confirmation.ts_ms
    sl = _sl_price(entry_price, side="short")
    final_tp = _tp_final(entry_price, side="short")

    rr_ok = True

    return EntrySetup(
        side="short",
        entry_ts_ms=entry_ts_ms,
        entry_price=entry_price,
        sl_price=sl,
        final_tp_price=final_tp,
        htf_ok=True,
        context_ok=True,
        zone_ok=zone_ok,
        sweep_ok=sweep_ok,
        rejection_ok=rejection_ok,
        confirmation_ok=confirmation_ok,
        rr_ok=rr_ok,
    )

