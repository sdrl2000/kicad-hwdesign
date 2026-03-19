"""DigiKey component search via DigiKey Product Search API v4 with OAuth2."""

from __future__ import annotations

import os
import time

import httpx
from loguru import logger

from .base import AbstractComponentSearch, ComponentResult


class DigiKeySearch(AbstractComponentSearch):
    """
    DigiKey component search.

    Uses OAuth2 Client Credentials flow to obtain a bearer token, then
    queries the DigiKey Product Search API v4 keyword endpoint.

    Required environment variables:
      - DIGIKEY_CLIENT_ID
      - DIGIKEY_CLIENT_SECRET
    """

    TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"
    SEARCH_URL = "https://api.digikey.com/products/v4/search/keyword"

    def __init__(self) -> None:
        self._client_id: str = os.environ.get("DIGIKEY_CLIENT_ID", "")
        self._client_secret: str = os.environ.get("DIGIKEY_CLIENT_SECRET", "")

        if not self._client_id or not self._client_secret:
            logger.warning(
                "DIGIKEY_CLIENT_ID / DIGIKEY_CLIENT_SECRET not set "
                "-- DigiKeySearch will return empty results"
            )

        # Cached OAuth token
        self._access_token: str = ""
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def search(self, query: str, limit: int = 10) -> list[ComponentResult]:
        if not self._client_id or not self._client_secret:
            return []

        token = await self._get_token()
        if not token:
            return []

        headers = {
            "Authorization": f"Bearer {token}",
            "X-IBMID-ClientId": self._client_id,
            "Accept": "application/json",
        }
        params = {"keyword": query}

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(
                    self.SEARCH_URL,
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
                return self._parse_results(data, limit)
            except Exception as e:
                logger.warning(f"DigiKey search failed: {e}")
                return []

    async def get_by_part_number(self, part_number: str) -> ComponentResult | None:
        results = await self.search(part_number, limit=1)
        return results[0] if results else None

    # ------------------------------------------------------------------
    # OAuth2 token management
    # ------------------------------------------------------------------

    async def _get_token(self) -> str:
        """Return a valid bearer token, refreshing if expired."""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(
                    self.TOKEN_URL,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
                token_data = resp.json()

                self._access_token = token_data["access_token"]
                # Expire 60 s early to avoid edge-case rejections
                expires_in = int(token_data.get("expires_in", 3600))
                self._token_expires_at = time.time() + expires_in - 60

                return self._access_token
            except Exception as e:
                logger.warning(f"DigiKey OAuth2 token request failed: {e}")
                self._access_token = ""
                self._token_expires_at = 0.0
                return ""

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_results(self, data: dict, limit: int) -> list[ComponentResult]:
        results: list[ComponentResult] = []
        products = data.get("Products") or []

        for product in products:
            if len(results) >= limit:
                break
            try:
                results.append(
                    ComponentResult(
                        mfr_part_number=product.get("ManufacturerPartNumber", ""),
                        description=product.get("ProductDescription", ""),
                        manufacturer=product.get("ManufacturerName", ""),
                        package=product.get("PackageType", ""),
                        price_usd=self._extract_price(product),
                        stock=int(product.get("QuantityAvailable", 0)),
                        supplier="DigiKey",
                        url=product.get("ProductUrl", ""),
                        datasheet_url=product.get("PrimaryDatasheet") or None,
                    )
                )
            except (ValueError, KeyError) as e:
                logger.debug(f"DigiKey product parse error: {e}")
                continue

        return results

    @staticmethod
    def _extract_price(product: dict) -> float:
        """Extract the unit price as a float."""
        raw = product.get("UnitPrice", 0)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0
