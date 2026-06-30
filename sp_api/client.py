"""Minimal Amazon SP-API client for Business OS.

This module intentionally focuses on the Reports API first because Revenue
Intelligence needs GET_SALES_AND_TRAFFIC_REPORT before Listing, Finance, and
Growth Intelligence can become truly business-aware.
"""

from __future__ import annotations

import gzip
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class SPAPIConfig:
    client_id: str | None
    client_secret: str | None
    refresh_token: str | None
    region: str
    marketplace_id: str | None

    @staticmethod
    def from_env(marketplace: str | None = None) -> "SPAPIConfig":
        region = os.getenv("SP_API_REGION", "NA").upper()
        marketplace_id = None
        normalized = str(marketplace or "").upper()
        if normalized in {"US", "AMAZON.COM"}:
            marketplace_id = os.getenv("SP_API_MARKETPLACE_ID_US", "ATVPDKIKX0DER")
        elif normalized in {"CA", "AMAZON.CA"}:
            marketplace_id = os.getenv("SP_API_MARKETPLACE_ID_CA", "A2EUQ1WTGCTBG2")
        else:
            marketplace_id = os.getenv("SP_API_MARKETPLACE_ID")
        return SPAPIConfig(
            client_id=os.getenv("SP_API_CLIENT_ID"),
            client_secret=os.getenv("SP_API_CLIENT_SECRET"),
            refresh_token=os.getenv("SP_API_REFRESH_TOKEN"),
            region=region,
            marketplace_id=marketplace_id,
        )

    @property
    def endpoint(self) -> str:
        return {
            "NA": "https://sellingpartnerapi-na.amazon.com",
            "EU": "https://sellingpartnerapi-eu.amazon.com",
            "FE": "https://sellingpartnerapi-fe.amazon.com",
        }.get(self.region, "https://sellingpartnerapi-na.amazon.com")

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "region": self.region,
            "endpoint": self.endpoint,
            "marketplace_id": self.marketplace_id,
            "has_client_id": bool(self.client_id),
            "has_client_secret": bool(self.client_secret),
            "has_refresh_token": bool(self.refresh_token),
            "configured": self.is_configured(),
        }


class SPAPIClient:
    """Small Reports API client using LWA refresh token auth.

    This deliberately avoids adding new dependencies. It supports the first
    Revenue Intelligence path: request report, check report, fetch document,
    download/decode JSON. AWS SigV4 signing may be required depending on app
    configuration; when that is missing the client returns actionable errors.
    """

    def __init__(self, config: SPAPIConfig | None = None):
        self.config = config or SPAPIConfig.from_env()
        self._access_token: str | None = None
        self._access_token_expires_at: datetime | None = None

    def diagnostics(self) -> dict[str, Any]:
        return {
            "status": "OK" if self.config.is_configured() else "AWAITING_CONFIGURATION",
            "version": "8.8",
            "config": self.config.to_safe_dict(),
            "required_env": [
                "SP_API_CLIENT_ID",
                "SP_API_CLIENT_SECRET",
                "SP_API_REFRESH_TOKEN",
                "SP_API_REGION",
                "SP_API_MARKETPLACE_ID_US",
                "SP_API_MARKETPLACE_ID_CA",
            ],
            "first_report_type": "GET_SALES_AND_TRAFFIC_REPORT",
            "note": "If Amazon returns an authorization/signature error, configure the SP-API IAM/SigV4 credentials next. This release prepares the Business OS workflow and safe Swagger actions.",
        }

    def request_sales_and_traffic_report(
        self,
        start_date: str,
        end_date: str,
        marketplace_id: str | None = None,
        asin_granularity: str = "CHILD",
        date_granularity: str = "DAY",
    ) -> dict[str, Any]:
        body = {
            "reportType": "GET_SALES_AND_TRAFFIC_REPORT",
            "marketplaceIds": [marketplace_id or self.config.marketplace_id],
            "dataStartTime": f"{start_date}T00:00:00Z",
            "dataEndTime": f"{end_date}T23:59:59Z",
            "reportOptions": {
                "dateGranularity": date_granularity,
                "asinGranularity": asin_granularity,
            },
        }
        body["marketplaceIds"] = [m for m in body["marketplaceIds"] if m]
        if not body["marketplaceIds"]:
            return {"status": "ERROR", "message": "No marketplace ID configured."}
        return self._request("POST", "/reports/2021-06-30/reports", body=body)

    def get_report(self, report_id: str) -> dict[str, Any]:
        return self._request("GET", f"/reports/2021-06-30/reports/{report_id}")

    def get_report_document(self, document_id: str) -> dict[str, Any]:
        return self._request("GET", f"/reports/2021-06-30/documents/{document_id}")

    def download_report_document(self, document: dict[str, Any]) -> dict[str, Any]:
        url = document.get("url")
        if not url:
            return {"status": "ERROR", "message": "Report document URL missing."}
        try:
            with urlopen(url, timeout=60) as response:
                raw = response.read()
            compression = str(document.get("compressionAlgorithm") or "").upper()
            if compression == "GZIP":
                raw = gzip.decompress(raw)
            text = raw.decode("utf-8")
            try:
                payload = json.loads(text)
            except Exception:
                payload = text
            return {"status": "OK", "document": payload}
        except Exception as exc:
            return {"status": "ERROR", "message": str(exc)}

    def _access_token_or_error(self) -> tuple[str | None, dict[str, Any] | None]:
        if not self.config.is_configured():
            return None, {"status": "AWAITING_CONFIGURATION", "config": self.config.to_safe_dict()}
        now = datetime.now(timezone.utc)
        if self._access_token and self._access_token_expires_at and self._access_token_expires_at > now + timedelta(seconds=60):
            return self._access_token, None
        token_response = self._lwa_refresh_token()
        if token_response.get("status") != "OK":
            return None, token_response
        self._access_token = token_response.get("access_token")
        expires = int(token_response.get("expires_in") or 3600)
        self._access_token_expires_at = now + timedelta(seconds=expires)
        return self._access_token, None

    def _lwa_refresh_token(self) -> dict[str, Any]:
        payload = json.dumps({
            "grant_type": "refresh_token",
            "refresh_token": self.config.refresh_token,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }).encode("utf-8")
        request = Request(
            "https://api.amazon.com/auth/o2/token",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
            return {"status": "OK", **data}
        except HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8")
            except Exception:
                detail = str(exc)
            return {"status": "ERROR", "http_status": exc.code, "message": detail}
        except URLError as exc:
            return {"status": "ERROR", "message": str(exc)}

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        token, error = self._access_token_or_error()
        if error:
            return error
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.config.endpoint}{path}",
            data=data,
            method=method,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-amz-access-token": token or "",
            },
        )
        try:
            with urlopen(request, timeout=60) as response:
                text = response.read().decode("utf-8")
            return {"status": "OK", "response": json.loads(text) if text else {}}
        except HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8")
            except Exception:
                detail = str(exc)
            return {
                "status": "ERROR",
                "http_status": exc.code,
                "message": detail,
                "hint": "If this is an authorization/signature error, add SP-API AWS IAM/SigV4 credentials in the next connector hardening step.",
            }
        except Exception as exc:
            return {"status": "ERROR", "message": str(exc)}
