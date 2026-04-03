from __future__ import annotations

import argparse

from src.bot.engine import BotEngine


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rule-based crypto futures bot (paper first).")
    p.add_argument("--mode", choices=["paper", "backtest"], default="paper")
    p.add_argument("--once", action="store_true", help="Run one scan and exit.")
    p.add_argument("--poll-seconds", type=int, default=60, help="Loop polling interval in seconds.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    engine = BotEngine()

    if args.mode == "paper":
        if args.once:
            result = engine.run_once()
            print(f"Session ok: {result.in_session}")
            print(f"Pairs scanned ({len(result.scanned_pairs)}): {', '.join(result.scanned_pairs)}")
            print(f"Trade signals generated: {result.signals_generated}")
            print(f"Trades opened: {result.entered_trades}")
            if result.opened_trades:
                for t in result.opened_trades:
                    print(
                        f"- {t['pair']} {t['side']} entry={t['entry']:.8f} SL={t['sl']:.8f} "
                        f"TP={t['tp']:.8f} score={t['score']}"
                    )
            else:
                # Show the most common reasons first.
                if result.failure_reasons:
                    sorted_reasons = sorted(result.failure_reasons.items(), key=lambda kv: kv[1], reverse=True)
                    print("No trades opened. Most common skip reasons:")
                    for reason, count in sorted_reasons[:10]:
                        print(f"- {reason}: {count}")
                if result.pair_skip_reasons:
                    print("Per-pair skip reasons:")
                    for pair in result.scanned_pairs:
                        reason = result.pair_skip_reasons.get(pair)
                        if reason is not None:
                            print(f"- {pair}: {reason}")
        else:
            engine.run_forever_paper(poll_seconds=args.poll_seconds)
    else:
        # Backtest module will be added in a later step.
        raise SystemExit("Backtest not implemented yet. Use --mode paper for now.")


if __name__ == "__main__":
    main()

