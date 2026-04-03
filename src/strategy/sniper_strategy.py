from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from config import settings
from src.data.market_data import PairSnapshot
from src.strategy.bias_4h import compute_bias_4h, Bias4H
from src.strategy.context_1h import compute_context_1h, Context1H
from src.strategy.entry_15m import build_long_setup, build_short_setup, EntrySetup
from src.strategy.scoring import score_setup
from src.strategy.signal import TradeSignal


class SniperStrategy:
    """
    Implements the sniper strategy rules exactly as provided:
    - 4H bias (HH/HL, EMA50, BOS, support reaction; or bearish variant)
    - RANGE rule when unclear
    - 1H support/resistance context
    - 15M entry (touch zone, sweep rule, rejection, confirmation)
    - scoring (enter only if score >= 8)
    """

    def decide(self, pair: str, snapshot: PairSnapshot) -> Optional[TradeSignal]:
        signal, _ = self.decide_debug(pair=pair, snapshot=snapshot)
        return signal

    def decide_debug(self, pair: str, snapshot: PairSnapshot) -> Tuple[Optional[TradeSignal], Optional[str]]:
        bias = compute_bias_4h(snapshot.candles_4h)
        context = compute_context_1h(snapshot.candles_1h)

        long_setup = build_long_setup(snapshot.candles_15m, bias=bias, context=context)
        short_setup = build_short_setup(snapshot.candles_15m, bias=bias, context=context)

        long_raw_score = score_setup(long_setup) if long_setup is not None else None
        short_raw_score = score_setup(short_setup) if short_setup is not None else None

        # Only enter if score >= configured threshold.
        min_score = settings.SCORE_MIN_TO_ENTER
        long_score = long_raw_score if (long_raw_score is not None and long_raw_score >= min_score) else None
        short_score = short_raw_score if (short_raw_score is not None and short_raw_score >= min_score) else None

        # No trade if neither passes.
        if long_score is None and short_score is None:
            # Decide a clear reason for logging/explanation.
            if long_setup is None and short_setup is None:
                return None, "no_setup_matches_rules"

            if long_setup is not None and short_setup is None:
                return None, f"score_below_min_long(score={long_raw_score}, min={min_score})"

            if long_setup is None and short_setup is not None:
                return None, f"score_below_min_short(score={short_raw_score}, min={min_score})"

            return None, f"score_below_min_both(long={long_raw_score}, short={short_raw_score}, min={min_score})"

        # If both pass, take the higher score.
        if long_score is not None and (short_score is None or long_score >= short_score):
            assert long_setup is not None
            return (
                TradeSignal(
                pair=pair,
                side="long",
                entry_ts_ms=long_setup.entry_ts_ms,
                entry_price=long_setup.entry_price,
                sl_price=long_setup.sl_price,
                final_tp_price=long_setup.final_tp_price,
                score=long_score,
                reason=f"long setup passed 15m sweep/rejection/confirmation with score>={min_score}",
                ),
                None,
            )

        assert short_setup is not None
        return (
            TradeSignal(
            pair=pair,
            side="short",
            entry_ts_ms=short_setup.entry_ts_ms,
            entry_price=short_setup.entry_price,
            sl_price=short_setup.sl_price,
            final_tp_price=short_setup.final_tp_price,
            score=short_score if short_score is not None else 0,
            reason=f"short setup passed 15m sweep/rejection/confirmation with score>={min_score}",
            ),
            None,
        )

