from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any
from urllib.parse import quote

import requests

from config import (
    UPSTOX_ACCESS_TOKEN,
    UPSTOX_API_BASE_URL,
    UPSTOX_MAX_RETRIES,
    UPSTOX_REQUEST_TIMEOUT_SECONDS,
    UPSTOX_RETRY_BACKOFF_SECONDS,
)


class UpstoxAPIError(RuntimeError):
    """Raised when Upstox returns an unsuccessful API response."""


class UpstoxAuthenticationError(UpstoxAPIError):
    """Raised when the Upstox token is missing or rejected."""


class UpstoxClient:
    """
    Small read-only Upstox REST client.

    This Step 1 client is intentionally based on requests rather
    than the SDK so the scanner has a stable, transparent API layer.
    It supports Analytics Tokens and does not place orders.
    """

    def __init__(
        self,
        access_token: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.access_token = (
            access_token
            if access_token is not None
            else UPSTOX_ACCESS_TOKEN
        ).strip()

        self.session = (
            session
            if session is not None
            else requests.Session()
        )

    def validate_configuration(self) -> None:
        if not self.access_token:
            raise UpstoxAuthenticationError(
                "UPSTOX_ACCESS_TOKEN is missing. "
                "Set it as an environment variable or GitHub secret."
            )

    def _headers(self) -> dict[str, str]:
        self.validate_configuration()

        return {
            "Accept": "application/json",
            "Authorization": (
                f"Bearer {self.access_token}"
            ),
        }

    @staticmethod
    def _extract_error_message(
        response: requests.Response,
    ) -> str:
        try:
            payload = response.json()
        except ValueError:
            body = response.text.strip()
            return body or response.reason

        errors = payload.get("errors")

        if isinstance(errors, list):
            messages: list[str] = []

            for error in errors:
                if isinstance(error, dict):
                    message = (
                        error.get("message")
                        or error.get("errorCode")
                        or error.get("error_code")
                    )

                    if message:
                        messages.append(str(message))

            if messages:
                return "; ".join(messages)

        return str(
            payload.get("message")
            or payload.get("error")
            or payload.get("status")
            or response.reason
        )

    def get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = (
            path
            if path.startswith("http")
            else f"{UPSTOX_API_BASE_URL}{path}"
        )

        last_exception: Exception | None = None

        for attempt in range(
            1,
            UPSTOX_MAX_RETRIES + 1,
        ):
            try:
                response = self.session.get(
                    url,
                    headers=self._headers(),
                    params=params,
                    timeout=(
                        UPSTOX_REQUEST_TIMEOUT_SECONDS
                    ),
                )

                if response.status_code in {
                    401,
                    403,
                }:
                    raise UpstoxAuthenticationError(
                        "Upstox authentication failed: "
                        + self._extract_error_message(
                            response
                        )
                    )

                if response.status_code == 429:
                    if attempt < UPSTOX_MAX_RETRIES:
                        wait_seconds = (
                            UPSTOX_RETRY_BACKOFF_SECONDS
                            * attempt
                        )
                        logging.warning(
                            "Upstox rate limit reached; "
                            "retrying in %.1f seconds",
                            wait_seconds,
                        )
                        time.sleep(wait_seconds)
                        continue

                if 500 <= response.status_code < 600:
                    if attempt < UPSTOX_MAX_RETRIES:
                        wait_seconds = (
                            UPSTOX_RETRY_BACKOFF_SECONDS
                            * attempt
                        )
                        logging.warning(
                            "Upstox server returned %s; "
                            "retrying in %.1f seconds",
                            response.status_code,
                            wait_seconds,
                        )
                        time.sleep(wait_seconds)
                        continue

                if not response.ok:
                    raise UpstoxAPIError(
                        f"Upstox HTTP "
                        f"{response.status_code}: "
                        + self._extract_error_message(
                            response
                        )
                    )

                payload = response.json()

                if payload.get("status") not in {
                    None,
                    "success",
                }:
                    raise UpstoxAPIError(
                        "Unexpected Upstox response: "
                        + str(payload)
                    )

                return payload

            except (
                requests.Timeout,
                requests.ConnectionError,
            ) as exc:
                last_exception = exc

                if attempt >= UPSTOX_MAX_RETRIES:
                    break

                wait_seconds = (
                    UPSTOX_RETRY_BACKOFF_SECONDS
                    * attempt
                )
                logging.warning(
                    "Upstox network error; "
                    "retrying in %.1f seconds: %s",
                    wait_seconds,
                    exc,
                )
                time.sleep(wait_seconds)

        raise UpstoxAPIError(
            "Upstox request failed after "
            f"{UPSTOX_MAX_RETRIES} attempts: "
            f"{last_exception}"
        )

    def get_historical_candles(
        self,
        instrument_key: str,
        unit: str,
        interval: int,
        to_date: date,
        from_date: date,
    ) -> list[list[Any]]:
        encoded_key = quote(
            instrument_key,
            safe="",
        )

        path = (
            "/v3/historical-candle/"
            f"{encoded_key}/"
            f"{unit}/"
            f"{interval}/"
            f"{to_date.isoformat()}/"
            f"{from_date.isoformat()}"
        )

        payload = self.get_json(path)

        candles = (
            payload.get("data", {})
            .get("candles", [])
        )

        if not isinstance(candles, list):
            raise UpstoxAPIError(
                "Historical candles response "
                "has an invalid structure."
            )

        return candles

    def get_ltp(
        self,
        instrument_keys: list[str],
    ) -> dict[str, Any]:
        clean_keys = [
            key.strip()
            for key in instrument_keys
            if key and key.strip()
        ]

        if not clean_keys:
            return {}

        if len(clean_keys) > 500:
            raise ValueError(
                "Upstox LTP V3 supports a maximum "
                "of 500 instrument keys per request."
            )

        payload = self.get_json(
            "/v3/market-quote/ltp",
            params={
                "instrument_key": ",".join(
                    clean_keys
                ),
            },
        )

        data = payload.get("data", {})

        if not isinstance(data, dict):
            raise UpstoxAPIError(
                "LTP response has an invalid structure."
            )

        return data

    def get_full_market_quotes(
        self,
        instrument_keys: list[str],
    ) -> dict[str, Any]:
        """Return quote snapshots including daily circuit limits."""
        clean_keys = [
            key.strip()
            for key in instrument_keys
            if key and key.strip()
        ]

        if not clean_keys:
            return {}

        if len(clean_keys) > 500:
            raise ValueError(
                "Upstox Full Market Quotes supports a maximum "
                "of 500 instrument keys per request."
            )

        payload = self.get_json(
            "/v2/market-quote/quotes",
            params={
                "instrument_key": ",".join(
                    clean_keys
                ),
            },
        )

        data = payload.get("data", {})

        if not isinstance(data, dict):
            raise UpstoxAPIError(
                "Full Market Quotes response has an "
                "invalid structure."
            )

        return data
