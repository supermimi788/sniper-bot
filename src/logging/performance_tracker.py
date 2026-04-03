from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from src.trading.paper_account import TradeEvent


@dataclass
class PerformanceTracker:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakevens: int = 0
    realized_pnl_usdt: float = 0.0
    win_values: List[float] = field(default_factory=list)
    loss_values: List[float] = field(default_factory=list)

    def on_trade_closed(self, close_event: TradeEvent) -> None:
        # One close event == one completed trade.
        self.total_trades += 1
        self.realized_pnl_usdt += close_event.pnl_usdt

        pnl = close_event.pnl_usdt
        eps = 1e-9
        if pnl > eps:
            self.wins += 1
            self.win_values.append(pnl)
        elif pnl < -eps:
            self.losses += 1
            self.loss_values.append(abs(pnl))
        else:
            self.breakevens += 1

    def snapshot(self, open_trades_count: int) -> Dict[str, float]:
        avg_win = sum(self.win_values) / len(self.win_values) if self.win_values else 0.0
        avg_loss = (sum(self.loss_values) / len(self.loss_values)) if self.loss_values else 0.0
        winrate = (self.wins / self.total_trades * 100.0) if self.total_trades else 0.0
        gross_win = sum(self.win_values)
        gross_loss = sum(self.loss_values)
        if gross_loss > 0:
            profit_factor = gross_win / gross_loss
        elif gross_win > 0:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0

        return {
            "total_trades": float(self.total_trades),
            "wins": float(self.wins),
            "losses": float(self.losses),
            "breakevens": float(self.breakevens),
            "winrate": winrate,
            "realized_pnl_usdt": self.realized_pnl_usdt,
            "average_win": avg_win,
            "average_loss": avg_loss,
            "profit_factor": profit_factor,
            "open_trades_count": float(open_trades_count),
        }

    @staticmethod
    def format_stats(stats: Dict[str, float]) -> str:
        pf = "inf" if stats["profit_factor"] == float("inf") else f"{stats['profit_factor']:.2f}"
        return (
            f"trades={int(stats['total_trades'])} wins={int(stats['wins'])} losses={int(stats['losses'])} "
            f"be={int(stats['breakevens'])} winrate={stats['winrate']:.1f}% pnl={stats['realized_pnl_usdt']:.4f} "
            f"avg_win={stats['average_win']:.4f} avg_loss={stats['average_loss']:.4f} "
            f"pf={pf} open={int(stats['open_trades_count'])}"
        )

