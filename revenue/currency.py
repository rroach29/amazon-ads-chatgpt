"""Simple reporting-currency helpers for Business OS v9.0.7.

This intentionally uses configurable static rates until a proper FX source is added.

Render env vars:
- BUSINESS_OS_REPORTING_CURRENCY=CAD
- FX_USD_CAD=1.37
- FX_CAD_USD=0.73
"""

from __future__ import annotations

import os
from typing import Any


class ReportingCurrencyService:
    version = "9.0.7"

    @staticmethod
    def reporting_currency() -> str:
        return (os.getenv("BUSINESS_OS_REPORTING_CURRENCY") or "CAD").upper()

    @staticmethod
    def rate(from_currency: str | None, to_currency: str | None = None) -> float:
        src = (from_currency or "").upper()
        dst = (to_currency or ReportingCurrencyService.reporting_currency()).upper()
        if not src or src == dst:
            return 1.0
        env_key = f"FX_{src}_{dst}"
        try:
            return float(os.getenv(env_key) or ReportingCurrencyService._default_rate(src, dst))
        except Exception:
            return 1.0

    @staticmethod
    def convert(amount: Any, from_currency: str | None, to_currency: str | None = None) -> float:
        try:
            value = float(amount or 0)
        except Exception:
            value = 0.0
        return round(value * ReportingCurrencyService.rate(from_currency, to_currency), 2)

    @staticmethod
    def _default_rate(src: str, dst: str) -> float:
        defaults = {
            ("USD", "CAD"): 1.37,
            ("CAD", "USD"): 0.73,
            ("MXN", "CAD"): 0.074,
            ("CAD", "MXN"): 13.5,
            ("USD", "MXN"): 18.5,
            ("MXN", "USD"): 0.054,
        }
        return defaults.get((src, dst), 1.0)
