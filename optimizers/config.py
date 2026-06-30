"""
Business OS v6.1.0
Optimizer Configuration

Keeps thresholds configurable without forcing each optimizer to invent its own
configuration pattern. Environment variables can override defaults later.
"""

import os
from dataclasses import dataclass


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except Exception:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except Exception:
        return default


@dataclass(frozen=True)
class BidOptimizerConfig:
    min_spend: float = _float_env("BOS_BID_MIN_SPEND", 3.0)
    min_clicks: int = _int_env("BOS_BID_MIN_CLICKS", 2)
    min_orders_for_bid_change: int = _int_env("BOS_BID_MIN_ORDERS", 1)
    high_acos_threshold: float = _float_env("BOS_BID_HIGH_ACOS", 0.40)
    efficient_acos_threshold: float = _float_env("BOS_BID_EFFICIENT_ACOS", 0.25)
    max_rows: int = _int_env("BOS_BID_MAX_ROWS", 50)


@dataclass(frozen=True)
class KeywordOptimizerConfig:
    min_spend: float = _float_env("BOS_KEYWORD_MIN_SPEND", 3.0)
    min_clicks: int = _int_env("BOS_KEYWORD_MIN_CLICKS", 2)
    max_rows: int = _int_env("BOS_KEYWORD_MAX_ROWS", 25)
