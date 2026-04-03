from __future__ import annotations

import time as time_module
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config import settings
from src.data.market_data import MarketData
from src.exchange.ccxt_client import OKXClient
from src.strategy.sniper_strategy import SniperStrategy
from src.trading.paper_account import PaperAccount
from .session import WIB_TZ, is_within_session_windows_wib
from .state import BotState


def _today_key_yyyy_mm_dd_local(dt: datetime) -> str:
    # Uses dt's timezone for the day rollover.
    return dt.strftime("%Y-%m-%d")


@dataclass
class EngineResult:
    in_session: bool
    scanned_pairs: List[str]
    signals_generated: int
    entered_trades: int = 0
    skipped_trades: int = 0
    opened_trades: List[dict] = None  # list of {pair, side, entry, sl, tp, score}
    failure_reasons: Dict[str, int] = None  # counts per reason
    pair_skip_reasons: Dict[str, str] = None  # pair -> first skip reason


class BotEngine:
    """
    Bot orchestration skeleton.

    Later steps will plug in:
    - top-down multi-timeframe strategy rules (4H/1H/15M)
    - paper trading execution + position management
    - CSV logging and Telegram alerts
    """

    def __init__(self) -> None:
        self.settings = settings
        self.state = BotState()

        # Data + paper simulation.
        self.exchange = OKXClient(
            api_key=settings.OKX_API_KEY,
            api_secret=settings.OKX_API_SECRET,
            api_passphrase=settings.OKX_API_PASSPHRASE,
        )
        # Helps ccxt resolve symbols reliably.
        try:
            self.exchange.load_markets()
        except Exception:
            # If market load fails, we'll still attempt fetches later.
            pass

        self.market_data = MarketData(self.exchange)
        self.paper_account = PaperAccount()
        self.strategy = SniperStrategy()

    def _in_session(self, now_utc: datetime) -> bool:
        return is_within_session_windows_wib(
            now=now_utc,
            windows=self.settings.SESSION_WINDOWS_WIB,
        )

    def _reset_daily_if_needed(self, now_utc: datetime) -> None:
        # Spec uses WIB for sessions; we reset based on WIB day.
        wib_now = now_utc.astimezone(WIB_TZ)
        today_key = _today_key_yyyy_mm_dd_local(wib_now)
        self.state.reset_if_new_day(today_key)

    def _cooldown_ok(self, pair: str, now: datetime) -> bool:
        # Risk-limit: only one open trade per pair.
        if self.paper_account.has_open_trade(pair):
            return False
        pair_cd = self.state.pair_cooldowns.get(pair)
        if pair_cd is None:
            return True
        return not pair_cd.in_cooldown(now=now, cooldown_minutes=self.settings.COOLDOWN_MINUTES)

    def run_once(self, now_utc: Optional[datetime] = None) -> EngineResult:
        """
        Runs a single scan across the pair universe.
        """
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)

        self._reset_daily_if_needed(now_utc)

        in_session = self._in_session(now_utc)
        if not in_session:
            return EngineResult(
                in_session=False,
                scanned_pairs=[],
                signals_generated=0,
                entered_trades=0,
                skipped_trades=len(self.settings.PAIRS),
                opened_trades=[],
                failure_reasons={"outside_session": len(self.settings.PAIRS)},
                pair_skip_reasons={pair: "outside_session" for pair in self.settings.PAIRS},
            )

        # Keep paper-trading positions updated (if any exist).
        for trade_id in list(self.paper_account.open_trade_ids):
            trade = self.paper_account.trades.get(trade_id)
            if trade is None:
                continue
            try:
                latest_15m = self.market_data.get_latest_candle(pair=trade.pair, timeframe="15m")
                self.paper_account.on_candle(latest_15m, trade_id=trade_id)
            except Exception:
                # Network hiccups shouldn't crash the bot.
                continue

        # Update daily loss counters from any newly closed paper trades.
        # Also apply the updated "pair trading rule": no cooldown after closing.
        for closed in self.paper_account.consume_closed_trades():
            if closed.realized_pnl_usdt < 0:
                self.state.losses_today += 1
            self.state.clear_pair_cooldown(pair=closed.pair)

        # Stop if too many losses today.
        if self.state.losses_today >= self.settings.MAX_LOSSES_BEFORE_STOP:
            return EngineResult(
                in_session=True,
                scanned_pairs=[],
                signals_generated=0,
                entered_trades=0,
                skipped_trades=len(self.settings.PAIRS),
                opened_trades=[],
                failure_reasons={"stop_after_losses": len(self.settings.PAIRS)},
                pair_skip_reasons={pair: "stop_after_losses" for pair in self.settings.PAIRS},
            )

        # Enforce risk limits (some will be upgraded later).
        if self.state.trades_today >= self.settings.MAX_TRADES_PER_DAY:
            return EngineResult(
                in_session=True,
                scanned_pairs=[],
                signals_generated=0,
                entered_trades=0,
                skipped_trades=len(self.settings.PAIRS),
                opened_trades=[],
                failure_reasons={"max_trades_per_day_reached": len(self.settings.PAIRS)},
                pair_skip_reasons={pair: "max_trades_per_day_reached" for pair in self.settings.PAIRS},
            )

        if self.paper_account.open_trades_count() >= self.settings.MAX_OPEN_TRADES:
            return EngineResult(
                in_session=True,
                scanned_pairs=[],
                signals_generated=0,
                entered_trades=0,
                skipped_trades=len(self.settings.PAIRS),
                opened_trades=[],
                failure_reasons={"max_open_trades_reached": len(self.settings.PAIRS)},
                pair_skip_reasons={pair: "max_open_trades_reached" for pair in self.settings.PAIRS},
            )

        entered = 0
        skipped = 0
        signals_generated = 0
        scanned_pairs: List[str] = []
        opened_trades: List[dict] = []
        failure_reasons: Dict[str, int] = {}
        pair_skip_reasons: Dict[str, str] = {}

        for pair in self.settings.PAIRS:
            scanned_pairs.append(pair)

            # Risk-limit: max 1 open trade per pair at a time.
            if self.paper_account.has_open_trade(pair):
                skipped += 1
                failure_reasons["pair_has_open_trade"] = failure_reasons.get("pair_has_open_trade", 0) + 1
                pair_skip_reasons[pair] = "pair_has_open_trade"
                continue

            try:
                snapshot = self.market_data.get_pair_snapshot(pair)
            except Exception:
                skipped += 1
                failure_reasons["data_fetch_error"] = failure_reasons.get("data_fetch_error", 0) + 1
                pair_skip_reasons[pair] = "data_fetch_error"
                continue

            # NO TRADE IF: spread too big
            if snapshot.spread_pct > self.settings.MAX_SPREAD_PCT:
                skipped += 1
                failure_reasons["spread_too_big"] = failure_reasons.get("spread_too_big", 0) + 1
                pair_skip_reasons[pair] = "spread_too_big"
                continue

            # Pair cooldown (30 minutes) remains active only while the pair has a recent entry
            # (cleared on close, per latest spec update).
            pair_cd = self.state.pair_cooldowns.get(pair)
            if pair_cd is not None and pair_cd.in_cooldown(now=now_utc, cooldown_minutes=self.settings.COOLDOWN_MINUTES):
                skipped += 1
                failure_reasons["pair_in_cooldown"] = failure_reasons.get("pair_in_cooldown", 0) + 1
                pair_skip_reasons[pair] = "pair_in_cooldown"
                continue

            signal, skip_reason = self.strategy.decide_debug(pair=pair, snapshot=snapshot)
            if signal is None:
                skipped += 1
                key = skip_reason or "strategy_no_signal"
                failure_reasons[key] = failure_reasons.get(key, 0) + 1
                pair_skip_reasons[pair] = key
                continue

            # Risk-limit checks just before opening.
            if self.state.trades_today >= self.settings.MAX_TRADES_PER_DAY:
                break
            if self.paper_account.open_trades_count() >= self.settings.MAX_OPEN_TRADES:
                break

            # Final safety guard: SL distance must not exceed 5%.
            sl_price = PaperAccount.sl_price_from_entry(entry_price=signal.entry_price, side=signal.side)
            sl_dist = abs(sl_price - signal.entry_price) / signal.entry_price
            if sl_dist > self.settings.STOP_LOSS_DISTANCE_PCT:
                skipped += 1
                failure_reasons["sl_distance_invalid"] = failure_reasons.get("sl_distance_invalid", 0) + 1
                pair_skip_reasons[pair] = "sl_distance_invalid"
                continue

            final_tp = PaperAccount.tp_price_from_r(
                entry_price=signal.entry_price,
                side=signal.side,
                r_mult=self.settings.FINAL_TP_R_MULTIPLIER,
            )

            # Open trade. Adaptive partial TP will be set after momentum classification.
            self.paper_account.open_trade(
                pair=pair,
                side=signal.side,
                entry_price=signal.entry_price,
                entry_ts_ms=signal.entry_ts_ms,
                sl_price=sl_price,
                partial_tp_price=None,
                final_tp_price=final_tp,
            )
            self.state.register_entry(pair=pair, now=now_utc)
            entered += 1
            signals_generated += 1
            opened_trades.append(
                {
                    "pair": pair,
                    "side": signal.side,
                    "entry": signal.entry_price,
                    "sl": sl_price,
                    "tp": final_tp,
                    "score": signal.score,
                }
            )

        return EngineResult(
            in_session=True,
            scanned_pairs=scanned_pairs,
            signals_generated=signals_generated,
            entered_trades=entered,
            skipped_trades=skipped,
            opened_trades=opened_trades,
            failure_reasons=failure_reasons,
            pair_skip_reasons=pair_skip_reasons,
        )

    def run_forever_paper(self, poll_seconds: int = 60) -> None:
        """
        Starts the paper-trading scan loop (strategy/execution still TODO).
        """
        while True:
            result = self.run_once()
            print(
                f"[bot] entered={result.entered_trades} skipped={result.skipped_trades} "
                f"trades_today={self.state.trades_today} open={self.paper_account.open_trades_count()}"
            )
            time_module.sleep(poll_seconds)

