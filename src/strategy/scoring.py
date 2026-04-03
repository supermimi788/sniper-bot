from __future__ import annotations

from typing import Optional

from config import settings
from src.strategy.entry_15m import EntrySetup


def score_setup(setup: EntrySetup) -> int:
    score = 0
    if setup.htf_ok:
        score += settings.SCORE_4H_BIAS
    if setup.context_ok:
        score += settings.SCORE_1H_CONTEXT
    if setup.zone_ok:
        score += settings.SCORE_ZONE
    if setup.sweep_ok:
        score += settings.SCORE_SWEEP
    if setup.rejection_ok:
        score += settings.SCORE_REJECTION
    if setup.confirmation_ok:
        score += settings.SCORE_CONFIRMATION
    if setup.rr_ok:
        score += settings.SCORE_RR
    return score


def score_and_filter(setup: EntrySetup) -> Optional[int]:
    score = score_setup(setup)
    if score >= settings.SCORE_MIN_TO_ENTER:
        return score
    return None

