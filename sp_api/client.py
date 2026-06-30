"""Amazon SP-API client for Business OS.

v8.8.1 upgrades the v8.8 scaffold from configuration-only checks to a live
connection layer:

- Refreshes Login with Amazon (LWA) access tokens from the seller refresh token.
- Detects AWS SigV4 credentials required by SP-API data-plane endpoints.
- Signs SP-API requests with AWS Signature Version 4 when credentials exist.
- Exposes safe diagnostics and auth tests that never return secrets.

The first production path remains Reports API / GET_SALES_AND_TRAFFIC_REPORT,
which powers Revenue Intelligence and organic-vs-paid analysis.
"""

from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


@dataclass
class SPAPIConfig:
    client_id: str | None
    client_secret: str | None
    refresh_token: str | None
    region: str
    marketplace_id: str | None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None

    @staticmethod
    def from_env(marketplace: str | None = None) -> "SPAPIConfig":
        """Resolve SP-API config from environment.

        Supports both the explicit SP_API_* naming convention and the older
        Amazon Ads/LWA names already present in this project so Render does not
        require duplicated secrets.
        """
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
            client_id=os.getenv("SP_API_CLIENT_ID") or os.getenv("AMAZON_CLIENT_ID"),
            client_secret=os.getenv("SP_API_CLIENT_SECRET") or os.getenv("AMAZON_CLIENT_SECRET"),
            refresh_token=os.getenv("SP_API_REFRESH_TOKEN") or os.getenv("SPAPI_REFRESH_TOKEN") or os.getenv("AMAZON_REFRESH_TOKEN"),
            region=region,
            marketplace_id=marketplace_id,
            aws_access_key_id=os.getenv("SP_API_AWS_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("SP_API_AWS_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.getenv("SP_API_AWS_SESSION_TOKEN") or os.getenv("AWS_SESSION_TOKEN"),
        )

    @property
    def endpoint(self) -> str:
        return {
            "NA": "https://sellingpartnerapi-na.amazon.com",
            "EU": "https://sellingpartnerapi-eu.amazon.com",
            "FE": "https://sellingpartnerapi-fe.amazon.com",
        }.get(self.region, "https://sellingpartnerapi-na.amazon.com")

    @property
    def aws_region(self) -> str:
        return {
            "NA": "us-east-1",
            "EU": "eu-west-1",
            "FE": "us-west-2",
        }.get(self.region, "us-east-1")

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    def has_sigv4_credentials(self) -> bool:
        return bool(self.aws_access_key_id and self.aws_secret_access_key)

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "region": self.region,
            "aws_region": self.aws_region,
            "endpoint": self.endpoint,
            "marketplace_id": self.marketplace_id,
            "has_client_id": bool(self.client_id),
            "has_client_secret": bool(self.client_secret),
            "has_refresh_token": bool(self.refresh_token),
            "has_aws_access_key_id": bool(self.aws_access_key_id),
            "has_aws_secret_access_key": bool(self.aws_secret_access_key),
            "has_aws_session_token": bool(self.aws_session_token),
            "configured": self.is_configured(),
            "sigv4_configured": self.has_sigv4_credentials(),
        }


class SPAPIClient:
    """SP-API client for safe Swagger-driven integration testing."""

    version = "8.8.1"

    def __init__(self, config: SPAPIConfig | None = None):
        self.config = config or SPAPIConfig.from_env()
        self._access_token: str | None = None
        self._access_token_expires_at: datetime | None = None

    def diagnostics(self) -> dict[str, Any]:
        status = "OK" if self.config.is_configured() else "AWAITING_CONFIGURATION"
        if self.config.is_configured() and not self.config.has_sigv4_credentials():
            status = "AWAITING_SIGV4_CONFIGURATION"
        return {
            "status": status,
            "version": self.version,
            "config": self.config.to_safe_dict(),
            "required_env": [
                "SP_API_CLIENT_ID or AMAZON_CLIENT_ID",
                "SP_API_CLIENT_SECRET or AMAZON_CLIENT_SECRET",
                "SP_API_REFRESH_TOKEN or SPAPI_REFRESH_TOKEN or AMAZON_REFRESH_TOKEN",
                "SP_API_REGION",
                "SP_API_MARKETPLACE_ID_US",
                "SP_API_MARKETPLACE_ID_CA",
            ],
            "sigv4_env": [
                "SP_API_AWS_ACCESS_KEY_ID or AWS_ACCESS_KEY_ID",
                "SP_API_AWS_SECRET_ACCESS_KEY or AWS_SECRET_ACCESS_KEY",
                "SP_API_AWS_SESSION_TOKEN or AWS_SESSION_TOKEN (optional)",
            ],
            "first_report_type": "GET_SALES_AND_TRAFFIC_REPORT",
            "capabilities": [
                "lwa_access_token_test",
                "sigv4_configuration_check",
                "marketplace_participations_test",
                "sales_and_traffic_report_request",
                "report_status",
                "report_document_download",
            ],
        }

    def auth_test(self, include_sp_api_call: bool = False) -> dict[str, Any]:
        """Test LWA token exchange, optionally followed by a signed SP-API call."""
        token, error = self._access_token_or_error()
        if error:
            return {
                "status": "ERROR",
                "version": self.version,
                "stage": "lwa_token_exchange",
                "config": self.config.to_safe_dict(),
                "error": error,
            }
        result: dict[str, Any] = {
            "status": "OK",
            "version": self.version,
            "lwa": {
                "access_token_obtained": bool(token),
                "expires_at": self._access_token_expires_at.isoformat() if self._access_token_expires_at else None,
            },
            "sigv4": {
                "configured": self.config.has_sigv4_credentials(),
                "aws_region": self.config.aws_region,
            },
        }
        if include_sp_api_call:
            result["marketplace_participations"] = self.get_marketplace_participations()
        return result

    def get_marketplace_participations(self) -> dict[str, Any]:
        return self._request("GET", "/sellers/v1/marketplaceParticipations")

    def request_sales_and_traffic_report(
        self,
        start_date: str,
        end_date: str,
        marketplace_id: str | None = None,
        asin_granularity: str = "CHILD",
        date_granularity: str = "DAY",
    ) -> dict[str, Any]:
        """Request a Seller Central Sales & Traffic report.

        Amazon's Reports API expects dataStartTime/dataEndTime as RFC3339 UTC
        timestamps and marketplaceIds as Amazon marketplace IDs, not country
        codes. Swagger users often enter values such as ``06/29/2026`` and
        ``CA``; normalize those before making the SP-API call so bad payloads
        are caught locally instead of creating confusing 400 responses.
        """
        resolved_marketplace_id = self._resolve_marketplace_id(marketplace_id or self.config.marketplace_id)
        if not resolved_marketplace_id:
            return {
                "status": "ERROR",
                "message": "No valid marketplace ID configured.",
                "hint": "Use marketplace=US/CA/MX or marketplace_id=ATVPDKIKX0DER/A2EUQ1WTGCTBG2/A1AM78C64UM0Y8.",
            }

        data_start = self._report_timestamp(start_date, end_of_day=False)
        data_end = self._report_timestamp(end_date, end_of_day=True)
        if not data_start or not data_end:
            return {
                "status": "ERROR",
                "message": "Invalid report date format.",
                "hint": "Use YYYY-MM-DD. MM/DD/YYYY and full ISO timestamps are also accepted.",
                "received": {"start_date": start_date, "end_date": end_date},
            }
        if data_start > data_end:
            return {
                "status": "ERROR",
                "message": "dataStartTime must be before dataEndTime.",
                "received": {"dataStartTime": data_start, "dataEndTime": data_end},
            }

        body = {
            "reportType": "GET_SALES_AND_TRAFFIC_REPORT",
            "marketplaceIds": [resolved_marketplace_id],
            "dataStartTime": data_start,
            "dataEndTime": data_end,
            "reportOptions": {
                "dateGranularity": str(date_granularity or "DAY").upper(),
                "asinGranularity": str(asin_granularity or "CHILD").upper(),
            },
        }
        return self._request("POST", "/reports/2021-06-30/reports", body=body)

    def _resolve_marketplace_id(self, value: str | None) -> str | None:
        if not value:
            return None
        normalized = str(value).strip()
        upper = normalized.upper()
        aliases = {
            "US": os.getenv("SP_API_MARKETPLACE_ID_US", "ATVPDKIKX0DER"),
            "USA": os.getenv("SP_API_MARKETPLACE_ID_US", "ATVPDKIKX0DER"),
            "AMAZON.COM": os.getenv("SP_API_MARKETPLACE_ID_US", "ATVPDKIKX0DER"),
            "CA": os.getenv("SP_API_MARKETPLACE_ID_CA", "A2EUQ1WTGCTBG2"),
            "CANADA": os.getenv("SP_API_MARKETPLACE_ID_CA", "A2EUQ1WTGCTBG2"),
            "AMAZON.CA": os.getenv("SP_API_MARKETPLACE_ID_CA", "A2EUQ1WTGCTBG2"),
            "MX": os.getenv("SP_API_MARKETPLACE_ID_MX", "A1AM78C64UM0Y8"),
            "MEXICO": os.getenv("SP_API_MARKETPLACE_ID_MX", "A1AM78C64UM0Y8"),
            "AMAZON.COM.MX": os.getenv("SP_API_MARKETPLACE_ID_MX", "A1AM78C64UM0Y8"),
        }
        return aliases.get(upper, normalized)

    def _report_timestamp(self, value: str, end_of_day: bool) -> str | None:
        parsed = self._parse_report_datetime(value)
        if parsed is None:
            return None
        if isinstance(parsed, date) and not isinstance(parsed, datetime):
            parsed = datetime.combine(parsed, time.max if end_of_day else time.min)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _parse_report_datetime(self, value: str | None) -> date | datetime | None:
        if not value:
            return None
        text = str(value).strip()
        # Full ISO/RFC3339 timestamps from Swagger or callers.
        try:
            iso_text = text.replace("Z", "+00:00")
            return datetime.fromisoformat(iso_text)
        except Exception:
            pass
        # Date-only values accepted by humans and previous Business OS releases.
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(text[:10], fmt).date()
            except Exception:
                continue
        return None

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
            safe = {k: v for k, v in data.items() if k != "access_token"}
            safe["access_token"] = data.get("access_token")
            return {"status": "OK", **safe}
        except HTTPError as exc:
            return {"status": "ERROR", "http_status": exc.code, "message": self._read_http_error(exc)}
        except URLError as exc:
            return {"status": "ERROR", "message": str(exc)}

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None, query: dict[str, Any] | None = None) -> dict[str, Any]:
        token, error = self._access_token_or_error()
        if error:
            return error
        if not self.config.has_sigv4_credentials():
            return {
                "status": "AWAITING_SIGV4_CONFIGURATION",
                "message": "LWA token succeeded, but SP-API endpoint calls require AWS SigV4 credentials.",
                "required_env": [
                    "SP_API_AWS_ACCESS_KEY_ID or AWS_ACCESS_KEY_ID",
                    "SP_API_AWS_SECRET_ACCESS_KEY or AWS_SECRET_ACCESS_KEY",
                    "SP_API_AWS_SESSION_TOKEN or AWS_SESSION_TOKEN (optional)",
                ],
                "config": self.config.to_safe_dict(),
            }
        body_bytes = json.dumps(body).encode("utf-8") if body is not None else b""
        qs = f"?{urlencode(query or {}, doseq=True)}" if query else ""
        url = f"{self.config.endpoint}{path}{qs}"
        headers = self._signed_headers(method=method, url=url, body=body_bytes, access_token=token or "")
        data = body_bytes if body is not None else None
        request = Request(url, data=data, method=method, headers=headers)
        try:
            with urlopen(request, timeout=60) as response:
                text = response.read().decode("utf-8")
            return {"status": "OK", "response": json.loads(text) if text else {}}
        except HTTPError as exc:
            return {
                "status": "ERROR",
                "http_status": exc.code,
                "message": self._read_http_error(exc),
                "hint": "Verify SP-API roles, marketplace authorization, and IAM/SigV4 credentials.",
            }
        except Exception as exc:
            return {"status": "ERROR", "message": str(exc)}

    def _signed_headers(self, method: str, url: str, body: bytes, access_token: str) -> dict[str, str]:
        parsed = urlparse(url)
        host = parsed.netloc
        canonical_uri = parsed.path or "/"
        canonical_query = parsed.query
        now = datetime.utcnow()
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body or b"").hexdigest()

        headers = {
            "content-type": "application/json",
            "host": host,
            "x-amz-access-token": access_token,
            "x-amz-date": amz_date,
        }
        if self.config.aws_session_token:
            headers["x-amz-security-token"] = self.config.aws_session_token

        signed_header_names = sorted(headers.keys())
        canonical_headers = "".join(f"{name}:{headers[name].strip()}\n" for name in signed_header_names)
        signed_headers = ";".join(signed_header_names)
        canonical_request = "\n".join([
            method.upper(),
            canonical_uri,
            canonical_query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ])
        credential_scope = f"{date_stamp}/{self.config.aws_region}/execute-api/aws4_request"
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ])
        signing_key = self._signature_key(self.config.aws_secret_access_key or "", date_stamp, self.config.aws_region, "execute-api")
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self.config.aws_access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Host": host,
            "X-Amz-Access-Token": access_token,
            "X-Amz-Date": amz_date,
            "Authorization": authorization,
            **({"X-Amz-Security-Token": self.config.aws_session_token} if self.config.aws_session_token else {}),
        }

    @staticmethod
    def _signature_key(secret_key: str, date_stamp: str, region_name: str, service_name: str) -> bytes:
        k_date = hmac.new(("AWS4" + secret_key).encode("utf-8"), date_stamp.encode("utf-8"), hashlib.sha256).digest()
        k_region = hmac.new(k_date, region_name.encode("utf-8"), hashlib.sha256).digest()
        k_service = hmac.new(k_region, service_name.encode("utf-8"), hashlib.sha256).digest()
        return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()

    @staticmethod
    def _read_http_error(exc: HTTPError) -> str:
        try:
            return exc.read().decode("utf-8")
        except Exception:
            return str(exc)
