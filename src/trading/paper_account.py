from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config import settings
from src.data.candles import Candle


_id_gen = itertools.count(1)


@dataclass
class PaperTrade:
    trade_id: int
    pair: str
    side: str  # "long" or "short"

    entry_price: float

    # Used to decide momentum after entry (first 1–2 15m candles after this timestamp).
    entry_ts_ms: int

    # Stop loss (active)
    sl_price: float
    initial_sl_price: float

    # Adaptive partial TP (set after momentum classification)
    partial_tp_price: Optional[float]
    final_tp_price: float

    # Process tracking
    last_processed_ts_ms: Optional[int] = None
    post_entry_candles_seen: int = 0

    partial_taken: bool = False
    closed: bool = False
    close_price: Optional[float] = None
    realized_pnl_usdt: float = 0.0

    # Tracks momentum classification (weak/medium/strong) to decide partial TP and SL move.
    momentum_class: Optional[str] = None

    # For momentum classification: extremes over first 1–2 post-entry candles.
    favorable_max_high: float = 0.0
    favorable_min_low: float = 0.0

    # Position sizing (simple: uses notional + leverage model)
    notional_usdt: float = settings.NOTIONAL_PER_TRADE_USDT
    leverage: int = settings.LEVERAGE
    margin_used_usdt: float = settings.MARGIN_PER_TRADE_USDT

    # Quantity in base asset units (for PnL calculation)
    qty: float = 0.0
    qty_remaining: float = 0.0


@dataclass
class TradeEvent:
    timestamp: str
    pair: str
    side: str
    event_type: str
    entry_price: float
    exit_price: float
    sl_price: float
    tp_price: float
    qty: float
    pnl_usdt: float
    pnl_r_multiple: float
    reason: str
    trade_id: int


class PaperAccount:
    """
    A simple paper-trading simulator for futures that supports:
    - isolated margin per trade
    - partial take profit using candle high/low
    - final take profit
    - stop loss

    Adaptive SL moves (BE or +0.5R) require that some rule decides the momentum class.
    We provide `set_sl_move` so strategy logic can call it after entry.
    """

    def __init__(self) -> None:
        self.trades: Dict[int, PaperTrade] = {}
        self.open_trade_ids: List[int] = []
        self._closed_trade_events: List[PaperTrade] = []
        self._trade_events: List[TradeEvent] = []

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _r_value_usdt(entry_price: float, qty: float) -> float:
        # 1R in USDT for the given position size.
        return entry_price * qty * settings.STOP_LOSS_DISTANCE_PCT

    def _emit_event(
        self,
        trade: PaperTrade,
        event_type: str,
        qty: float,
        pnl_usdt: float,
        exit_price: Optional[float],
        tp_price: Optional[float],
        reason: str,
    ) -> None:
        r_value = self._r_value_usdt(trade.entry_price, qty=qty) if qty > 0 else 0.0
        pnl_r = (pnl_usdt / r_value) if r_value > 0 else 0.0
        self._trade_events.append(
            TradeEvent(
                timestamp=self._utc_now_iso(),
                pair=trade.pair,
                side=trade.side,
                event_type=event_type,
                entry_price=trade.entry_price,
                exit_price=exit_price if exit_price is not None else 0.0,
                sl_price=trade.sl_price,
                tp_price=tp_price if tp_price is not None else 0.0,
                qty=qty,
                pnl_usdt=pnl_usdt,
                pnl_r_multiple=pnl_r,
                reason=reason,
                trade_id=trade.trade_id,
            )
        )

    @staticmethod
    def sl_price_from_entry(entry_price: float, side: str) -> float:
        """
        Spec: fixed stop loss distance = 5% from entry.
        """
        if side == "long":
            return entry_price * (1.0 - settings.STOP_LOSS_DISTANCE_PCT)
        return entry_price * (1.0 + settings.STOP_LOSS_DISTANCE_PCT)

    @staticmethod
    def tp_price_from_r(entry_price: float, side: str, r_mult: float) -> float:
        """
        Spec model:
        - 1R equals the fixed SL distance (5%).
        - Final TP is 2.5R => 12.5% total move.
        """
        r_pct = settings.STOP_LOSS_DISTANCE_PCT
        if side == "long":
            return entry_price * (1.0 + r_mult * r_pct)
        return entry_price * (1.0 - r_mult * r_pct)

    def open_trade(
        self,
        pair: str,
        side: str,
        entry_price: float,
        entry_ts_ms: int,
        sl_price: float,
        partial_tp_price: Optional[float],
        final_tp_price: float,
    ) -> PaperTrade:
        trade_id = next(_id_gen)

        qty = settings.NOTIONAL_PER_TRADE_USDT / entry_price
        trade = PaperTrade(
            trade_id=trade_id,
            pair=pair,
            side=side,
            entry_price=entry_price,
            entry_ts_ms=entry_ts_ms,
            sl_price=sl_price,
            initial_sl_price=sl_price,
            partial_tp_price=partial_tp_price,
            final_tp_price=final_tp_price,
            qty=qty,
            qty_remaining=qty,
        )

        self.trades[trade_id] = trade
        self.open_trade_ids.append(trade_id)

        self._emit_event(
            trade=trade,
            event_type="entry_opened",
            qty=trade.qty,
            pnl_usdt=0.0,
            exit_price=None,
            tp_price=trade.final_tp_price,
            reason="entry_opened",
        )
        return trade

    def set_sl_move(self, trade_id: int, new_sl_price: float) -> None:
        trade = self.trades.get(trade_id)
        if trade is None or trade.closed:
            return
        trade.sl_price = new_sl_price

    def _set_momentum(self, trade: PaperTrade, momentum_class: str) -> None:
        if trade.closed or trade.momentum_class is not None:
            return

        trade.momentum_class = momentum_class

        # Set partial TP based on momentum classification.
        if momentum_class == "weak":
            partial_r = settings.WEAK_PARTIAL_R
            sl_move_r = settings.SL_MOVE_WEAK_TO_R
        elif momentum_class == "medium":
            partial_r = settings.MEDIUM_PARTIAL_R
            sl_move_r = settings.SL_MOVE_MEDIUM_TO_R
        elif momentum_class == "strong":
            partial_r = settings.STRONG_PARTIAL_R
            sl_move_r = settings.SL_MOVE_STRONG_TO_R
        else:
            raise ValueError(f"Unknown momentum class: {momentum_class}")

        trade.partial_tp_price = self.tp_price_from_r(trade.entry_price, trade.side, r_mult=partial_r)

        # Move SL after classification.
        if sl_move_r != 0.0:
            new_sl = self.tp_price_from_r(trade.entry_price, trade.side, r_mult=sl_move_r)
            self.set_sl_move(trade_id=trade.trade_id, new_sl_price=new_sl)
        else:
            # BE means SL at entry.
            self.set_sl_move(trade_id=trade.trade_id, new_sl_price=trade.entry_price)
            self._emit_event(
                trade=trade,
                event_type="sl_moved_to_be",
                qty=trade.qty_remaining,
                pnl_usdt=0.0,
                exit_price=None,
                tp_price=trade.partial_tp_price,
                reason="sl_moved_to_be",
            )

    @staticmethod
    def _r_mult_from_favorable_move(entry_price: float, side: str, favorable_high: float, favorable_low: float) -> float:
        """
        Convert favorable excursion into an R multiple, where 1R equals the fixed SL distance (5%).
        """
        r_pct = settings.STOP_LOSS_DISTANCE_PCT
        if side == "long":
            move = favorable_high - entry_price
            if entry_price <= 0 or r_pct <= 0:
                return 0.0
            return move / (entry_price * r_pct)
        else:
            move = entry_price - favorable_low
            if entry_price <= 0 or r_pct <= 0:
                return 0.0
            return move / (entry_price * r_pct)

    @staticmethod
    def _pnl_usdt(side: str, entry: float, exit: float, qty: float) -> float:
        # Futures PnL approximation: qty * (exit-entry) for long, reversed for short.
        if side == "long":
            return qty * (exit - entry)
        return qty * (entry - exit)

    def on_candle(self, candle: Candle, trade_id: int) -> None:
        trade = self.trades.get(trade_id)
        if trade is None or trade.closed:
            return

        # Process each 15m candle at most once per trade.
        if trade.last_processed_ts_ms is not None and candle.ts_ms <= trade.last_processed_ts_ms:
            return
        trade.last_processed_ts_ms = candle.ts_ms

        # Do not evaluate exits on the entry candle itself.
        if candle.ts_ms <= trade.entry_ts_ms:
            return

        # Update extremes for momentum classification after entry.
        if candle.ts_ms > trade.entry_ts_ms:
            trade.post_entry_candles_seen += 1
            if trade.side == "long":
                trade.favorable_max_high = max(trade.favorable_max_high, candle.high)
            else:
                # For short: favorable move is downward (lower lows).
                if trade.favorable_min_low == 0.0:
                    trade.favorable_min_low = candle.low
                trade.favorable_min_low = min(trade.favorable_min_low, candle.low)

            # Classify momentum using the first 1–2 candles after entry.
            # - If we reached STRONG threshold in the first candle, we classify immediately.
            # - Otherwise, we classify once we have seen 2 candles.
            if trade.momentum_class is None:
                seen = trade.post_entry_candles_seen
                # Need at least 1 candle to compute anything meaningful.
                if seen >= settings.MOMENTUM_CHECK_CANDLES_MIN:
                    r_mult = self._r_mult_from_favorable_move(
                        entry_price=trade.entry_price,
                        side=trade.side,
                        favorable_high=trade.favorable_max_high if trade.side == "long" else 0.0,
                        favorable_low=trade.favorable_min_low if trade.side == "short" else 0.0,
                    )

                    if seen == 1 and r_mult >= settings.STRONG_PARTIAL_R:
                        self._set_momentum(trade, momentum_class="strong")
                    elif seen >= settings.MOMENTUM_CHECK_CANDLES_MAX:
                        if r_mult >= settings.STRONG_PARTIAL_R:
                            self._set_momentum(trade, momentum_class="strong")
                        elif r_mult >= settings.MEDIUM_PARTIAL_R:
                            self._set_momentum(trade, momentum_class="medium")
                        else:
                            self._set_momentum(trade, momentum_class="weak")

        # Conservative ordering: for each candle, assume SL triggers before TP if both are touched.
        if trade.side == "long":
            sl_touched = candle.low <= trade.sl_price
            partial_touched = (
                (not trade.partial_taken)
                and (trade.partial_tp_price is not None)
                and (candle.high >= trade.partial_tp_price)
            )
            final_touched = candle.high >= trade.final_tp_price

            if sl_touched:
                self._close_trade(
                    trade,
                    exit_price=trade.sl_price,
                    qty_to_close=trade.qty_remaining,
                    reason="sl_hit",
                )
                return

            if partial_touched:
                self._take_partial(trade)

            if final_touched and not trade.closed:
                self._close_trade(
                    trade,
                    exit_price=trade.final_tp_price,
                    qty_to_close=trade.qty_remaining,
                    reason="final_tp_hit",
                )
                return

        else:
            sl_touched = candle.high >= trade.sl_price
            partial_touched = (
                (not trade.partial_taken)
                and (trade.partial_tp_price is not None)
                and (candle.low <= trade.partial_tp_price)
            )
            final_touched = candle.low <= trade.final_tp_price

            if sl_touched:
                self._close_trade(
                    trade,
                    exit_price=trade.sl_price,
                    qty_to_close=trade.qty_remaining,
                    reason="sl_hit",
                )
                return

            if partial_touched:
                self._take_partial(trade)

            if final_touched and not trade.closed:
                self._close_trade(
                    trade,
                    exit_price=trade.final_tp_price,
                    qty_to_close=trade.qty_remaining,
                    reason="final_tp_hit",
                )
                return

    def _take_partial(self, trade: PaperTrade) -> None:
        # Partial exit fraction fixed at 40% of the position value/qty.
        if trade.partial_tp_price is None:
            return
        qty_to_close = trade.qty_remaining * settings.PARTIAL_EXIT_FRACTION
        pnl = self._pnl_usdt(trade.side, trade.entry_price, trade.partial_tp_price, qty_to_close)
        trade.realized_pnl_usdt += pnl
        trade.qty_remaining -= qty_to_close
        trade.partial_taken = True
        self._emit_event(
            trade=trade,
            event_type="partial_exit",
            qty=qty_to_close,
            pnl_usdt=pnl,
            exit_price=trade.partial_tp_price,
            tp_price=trade.partial_tp_price,
            reason="partial_tp_hit",
        )

    def _close_trade(self, trade: PaperTrade, exit_price: float, qty_to_close: float, reason: str) -> None:
        if qty_to_close <= 0:
            trade.closed = True
            trade.close_price = exit_price
            return

        pnl = self._pnl_usdt(trade.side, trade.entry_price, exit_price, qty_to_close)
        trade.realized_pnl_usdt += pnl
        trade.qty_remaining -= qty_to_close
        trade.closed = True
        trade.close_price = exit_price

        hit_event = reason
        if reason == "sl_hit" and abs(exit_price - trade.entry_price) <= (trade.entry_price * 1e-8):
            hit_event = "break_even_exit"

        self._emit_event(
            trade=trade,
            event_type=hit_event,
            qty=qty_to_close,
            pnl_usdt=pnl,
            exit_price=exit_price,
            tp_price=trade.final_tp_price if reason == "final_tp_hit" else trade.sl_price,
            reason=reason,
        )
        self._emit_event(
            trade=trade,
            event_type="trade_closed",
            qty=trade.qty,
            pnl_usdt=trade.realized_pnl_usdt,
            exit_price=exit_price,
            tp_price=trade.final_tp_price,
            reason=hit_event,
        )

        # Store close event for engine to update daily loss counters.
        self._closed_trade_events.append(trade)

        # Remove from open ids
        if trade.trade_id in self.open_trade_ids:
            self.open_trade_ids.remove(trade.trade_id)

    def open_trades_count(self) -> int:
        return len(self.open_trade_ids)

    def consume_closed_trades(self) -> List[PaperTrade]:
        events = self._closed_trade_events
        self._closed_trade_events = []
        return events

    def consume_trade_events(self) -> List[TradeEvent]:
        events = self._trade_events
        self._trade_events = []
        return events

    def has_open_trade(self, pair: str) -> bool:
        for trade_id in self.open_trade_ids:
            trade = self.trades.get(trade_id)
            if trade is not None and trade.pair == pair and not trade.closed:
                return True
        return False

