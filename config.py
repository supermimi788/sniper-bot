"""
Central configuration for the sniper-bot.

This file is intentionally dependency-light (no required third-party packages)
so it works out of the box. It still supports a local `.env` file for API keys
and secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar


T = TypeVar("T")


def _load_env_file(env_path: Path) -> None:
    """
    Minimal `.env` loader:
    - Reads KEY=VALUE lines
    - Ignores blank lines and lines starting with `#`
    - If an environment variable already exists, we do not overwrite it
    """
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _env(key: str, default: T, cast: Callable[[str], T]) -> T:
    val = os.environ.get(key)
    if val is None or val == "":
        return default
    return cast(val)


def _env_bool(key: str, default: bool) -> bool:
    def _cast(v: str) -> bool:
        return v.strip().lower() in {"1", "true", "yes", "y", "on"}

    return _env(key, default, _cast)


@dataclass(frozen=True)
class Settings:
    # ----------------------------
    # Exchange + trading mode
    # ----------------------------
    EXCHANGE: str = "okx"
    MARKET_TYPE: str = "futures"
    DEFAULT_TRADING_MODE: str = "paper"  # switch to "live" later

    # ----------------------------
    # Paper/live keys (optional)
    # ----------------------------
    OKX_API_KEY: str = ""
    OKX_API_SECRET: str = ""
    OKX_API_PASSPHRASE: str = ""

    # Telegram notifications (optional)
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    TELEGRAM_SEND_CYCLE_SUMMARY: bool = False
    TELEGRAM_SEND_SKIP_SUMMARY: bool = False
    TELEGRAM_SEND_ONLY_EVENTS: bool = True

    # ----------------------------
    # Risk + position sizing model
    # ----------------------------
    MARGIN_MODE: str = "isolated"
    MARGIN_PER_TRADE_USDT: float = 3.0
    LEVERAGE: int = 25
    NOTIONAL_PER_TRADE_USDT: float = 75.0

    STOP_LOSS_DISTANCE_PCT: float = 0.03  # 3%
    FINAL_TP_R_MULTIPLIER: float = 2  # 2R
    FINAL_TP_DISTANCE_PCT: float = None

    # ----------------------------
    # Universe
    # ----------------------------
    PAIRS: List[str] = None  # type: ignore[assignment]

    # ----------------------------
    # Top-down analysis timeframes
    # ----------------------------
    BIAS_TF_4H: str = "4h"
    CONTEXT_TF_1H: str = "1h"
    ENTRY_TF_15M: str = "15m"

    # ----------------------------
    # Indicators / zone geometry
    # ----------------------------
    EMA_PERIOD: int = 50

    # Zones (width as percentage of price)
    ZONE_WIDTH_MIN_PCT: float = 0.0008  # 0.08%
    ZONE_WIDTH_MAX_PCT: float = 0.004  # 0.4%

    # Sweep penetration rule (percentage over prior high/low)
    SWEEP_PEN_MIN_PCT: float = 0.00005  # 0.005%
    SWEEP_PEN_MAX_PCT: float = 0.004  # 0.4%
    SWEEP_WICK_TO_BODY_MIN: float = 0.7  # wick/body >= 0.7

    # Zone touch tolerance around zone boundaries (to avoid overly strict touches).
    ZONE_TOUCH_TOLERANCE_PCT: float = 0.0012  # 0.1%   

    # ----------------------------
    # Adaptive trade management
    # ----------------------------
    # Momentum classification uses the first 1-2 candles after entry.
    MOMENTUM_CHECK_CANDLES_MIN: int = 1
    MOMENTUM_CHECK_CANDLES_MAX: int = 3

    PARTIAL_EXIT_FRACTION: float = 0.40  # 40% partial TP
    REMAINDER_EXIT_FRACTION: float = 0.60  # remaining 60% to final TP

    # Weak/Medium/Strong:
    # - Weak: 40% at 1R, SL to BE, hold 60% to 2R
    # - Medium: 40% at 1.2R, SL to BE, hold 60% to 2R
    # - Strong: 40% at 1.5R, SL to +0.5R, hold 60% to 2R
    WEAK_PARTIAL_R: float = 1.0
    MEDIUM_PARTIAL_R: float = 1.2
    STRONG_PARTIAL_R: float = 1.5

    SL_MOVE_WEAK_TO_R: float = 0.0  # BE = 0R
    SL_MOVE_MEDIUM_TO_R: float = 0.0  # BE = 0R
    SL_MOVE_STRONG_TO_R: float = 0.3

    # Final target is always 2R
    FINAL_TP_R: float = 2

    # ----------------------------
    # Spread + "no trade" filters
    # ----------------------------
    # Your request: max spread 0.1% (percentage)
    MAX_SPREAD_PCT: float = 0.001

    # ----------------------------
    # Scoring (must match spec)
    # ----------------------------
    SCORE_4H_BIAS: int = 2
    SCORE_1H_CONTEXT: int = 2
    SCORE_ZONE: int = 2
    SCORE_SWEEP: int = 2
    SCORE_REJECTION: int = 2
    SCORE_CONFIRMATION: int = 2
    SCORE_RR: int = 2
    SCORE_MIN_TO_ENTER: int = 6

    # ----------------------------
    # Risk limits / session controls
    # ----------------------------
    MAX_TRADES_PER_DAY: int = 20
    MAX_LOSSES_BEFORE_STOP: int = 5
    MAX_OPEN_TRADES: int = 3
    COOLDOWN_MINUTES: int = 30

    # WIB session windows:
    # 08:00–11:00, 14:00–17:00, 19:00–00:00
    SESSION_WINDOWS_WIB: List[Tuple[str, str]] = None  # type: ignore[assignment]
    SESSION_TIMEZONE: str = "WIB"

    # Logging outputs
    LOG_DIR: str = "logs"
    TRADE_LOG_CSV: str = "trade_history.csv"


def build_settings() -> Settings:
    # Load .env first so overrides are available.
    project_root = Path(__file__).resolve().parent
    _load_env_file(project_root / ".env")

    # Defaults from Settings, with optional env overrides for secrets/settings.
    s = Settings()

    pairs = [
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "ADAUSDT",
        "DOGEUSDT",
        "TRXUSDT",
        "TONUSDT",
        "AVAXUSDT",
        "LINKUSDT",
        "DOTUSDT",
        "LTCUSDT",
        "BCHUSDT",
        "UNIUSDT",
        "XLMUSDT",
        "SUIUSDT",
        "APTUSDT",
        "SHIBUSDT",
        "NEARUSDT",
    ]

    session_windows = [
        ("08:00", "11:00"),
        ("14:00", "17:00"),
        ("19:00", "00:00"),
    ]

    # Apply values required by the spec (exact lists).
    object.__setattr__(s, "PAIRS", pairs)
    object.__setattr__(s, "SESSION_WINDOWS_WIB", session_windows)

    # Optional overrides (secrets, toggles, etc.). These do not change strategy logic.
    object.__setattr__(s, "OKX_API_KEY", os.environ.get("OKX_API_KEY", ""))
    object.__setattr__(s, "OKX_API_SECRET", os.environ.get("OKX_API_SECRET", ""))
    object.__setattr__(s, "OKX_API_PASSPHRASE", os.environ.get("OKX_API_PASSPHRASE", ""))
    object.__setattr__(s, "TELEGRAM_BOT_TOKEN", os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    object.__setattr__(s, "TELEGRAM_CHAT_ID", os.environ.get("TELEGRAM_CHAT_ID", ""))

    return s


# Public settings object used by the rest of the project.
settings: Settings = build_settings()

