from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from config import settings
from src.trading.paper_account import TradeEvent


class TradeLogger:
    CSV_COLUMNS = [
        "timestamp",
        "pair",
        "side",
        "event_type",
        "entry_price",
        "exit_price",
        "sl_price",
        "tp_price",
        "qty",
        "pnl_usdt",
        "pnl_r_multiple",
        "reason",
        "trade_id",
    ]

    def __init__(self) -> None:
        log_dir = Path(settings.LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = log_dir / settings.TRADE_LOG_CSV
        self._ensure_header()

    def _ensure_header(self) -> None:
        if self.csv_path.exists() and self.csv_path.stat().st_size > 0:
            return
        with self.csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_COLUMNS)
            writer.writeheader()

    def log_event(self, event: TradeEvent) -> None:
        row = {
            "timestamp": event.timestamp,
            "pair": event.pair,
            "side": event.side,
            "event_type": event.event_type,
            "entry_price": event.entry_price,
            "exit_price": event.exit_price,
            "sl_price": event.sl_price,
            "tp_price": event.tp_price,
            "qty": event.qty,
            "pnl_usdt": event.pnl_usdt,
            "pnl_r_multiple": event.pnl_r_multiple,
            "reason": event.reason,
            "trade_id": event.trade_id,
        }
        with self.csv_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_COLUMNS)
            writer.writerow(row)

        print(
            f"[trade] {event.timestamp} id={event.trade_id} {event.pair} {event.side} "
            f"{event.event_type} qty={event.qty:.8f} pnl={event.pnl_usdt:.6f} "
            f"r={event.pnl_r_multiple:.4f} reason={event.reason}"
        )

    def log_events(self, events: Iterable[TradeEvent]) -> None:
        for event in events:
            self.log_event(event)

