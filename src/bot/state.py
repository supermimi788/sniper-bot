from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional


@dataclass
class PairCooldown:
    last_entry_time: Optional[datetime] = None

    def in_cooldown(self, now: datetime, cooldown_minutes: int) -> bool:
        if self.last_entry_time is None:
            return False
        delta_min = (now - self.last_entry_time).total_seconds() / 60.0
        return delta_min < cooldown_minutes


@dataclass
class BotState:
    """
    Tracks limits that reset with the trading day.
    This is a simplified state object; real paper/live fills will update it.
    """

    date_key: Optional[str] = None  # e.g. "2026-04-03"
    trades_today: int = 0
    losses_today: int = 0

    # Per-pair cooldown tracking to enforce "1 trade per pair" + "cooldown 30 minutes"
    pair_cooldowns: Dict[str, PairCooldown] = field(default_factory=dict)

    def reset_if_new_day(self, today_key: str) -> None:
        if self.date_key != today_key:
            self.date_key = today_key
            self.trades_today = 0
            self.losses_today = 0
            self.pair_cooldowns.clear()

    def register_entry(self, pair: str, now: datetime) -> None:
        self.trades_today += 1
        if pair not in self.pair_cooldowns:
            self.pair_cooldowns[pair] = PairCooldown()
        self.pair_cooldowns[pair].last_entry_time = now

    def clear_pair_cooldown(self, pair: str) -> None:
        """
        Spec update: no cooldown after closing.
        This clears the last-entry timestamp so the pair can trade again
        immediately when a new valid setup appears.
        """
        cd = self.pair_cooldowns.get(pair)
        if cd is None:
            return
        cd.last_entry_time = None

