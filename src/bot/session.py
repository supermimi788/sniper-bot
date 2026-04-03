from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo


WIB_TZ = ZoneInfo("Asia/Jakarta")  # WIB = UTC+7


def _parse_hhmm(s: str) -> time:
    # Accepts "08:00" style.
    hh, mm = s.split(":")
    return time(int(hh), int(mm))


def is_within_session_windows_wib(
    now: Optional[datetime],
    windows: Iterable[Tuple[str, str]],
) -> bool:
    """
    Returns True if the given WIB time is inside any session window.
    Supports windows that cross midnight (e.g., "19:00" -> "00:00").
    """
    if now is None:
        now = datetime.now(tz=WIB_TZ)

    now_wib = now.astimezone(WIB_TZ)
    now_t = now_wib.time()

    for start_s, end_s in windows:
        start_t = _parse_hhmm(start_s)
        end_t = _parse_hhmm(end_s)

        if end_t > start_t:
            # Normal same-day window.
            if start_t <= now_t <= end_t:
                return True
        else:
            # Cross-midnight window.
            if now_t >= start_t or now_t <= end_t:
                return True

    return False

