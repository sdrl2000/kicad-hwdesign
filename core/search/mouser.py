"""Mouser Electronics component search via Mouser Search API v2."""

from __future__ import annotations

import os
import re

import httpx
from loguru import logger

from .base import AbstractComponentSearch, ComponentResult


class MouserSearch(AbstractComponentSearch):
    """
    Mouser Electronics component search.

    Uses the Mouser Search API v2 keyword endpoint.
    Requires the MOUSER_API_KEY environment variable.
    """

    SEARCH_URL = "https://api.mouser.com/api/v2/search/keyword"

    def __init__(self) -> None:
        self._api_key: str = os.environ.get("MOUSER_API_KEY", "")
        if not self._api_key:
            logger.warning(
                "MOUSER_API_KEY not set -- MouserSearch will return empty results"
            )

    async def search(self, query: str, limit: int = 10) -> list[ComponentResult]:
        if not self._api_key:
            return []

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = {
            "SearchByKeywordRequest": {
                "keyword": query,
                "records": limit,
                "startingRecord": 0,
                "searchOptions": "1",
            }
        }
        params = {"apiKey": self._api_key}

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(
                    self.SEARCH_URL,
                    headers=headers,
                    params=params,
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                return self._parse_results(data, limit)
            except Exception as e:
                logger.warning(f"Mouser search failed: {e}")
                return []

    async def get_by_part_number(self, part_number: str) -> ComponentResult | None:
        results = await self.search(part_number, limit=1)
        return results[0] if results else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_results(self, data: dict, limit: int) -> list[ComponentResult]:
        results: list[ComponentResult] = []
        parts = (
            data.get("SearchResults", {}).get("Parts") or []
        )

        for part in parts:
            if len(results) >= limit:
                break
            try:
                results.append(
                    ComponentResult(
                        mfr_part_number=part.get("ManufacturerPartNumber", ""),
                        description=part.get("Description", ""),
                        manufacturer=part.get("Manufacturer", ""),
                        package=part.get("Category", ""),
                        price_usd=self._extract_price(part),
                        stock=self._extract_stock(part),
                        supplier="Mouser",
                        url=part.get("ProductDetailUrl", ""),
                        datasheet_url=part.get("DataSheetUrl") or None,
                    )
                )
            except (ValueError, KeyError) as e:
                logger.debug(f"Mouser part parse error: {e}")
                continue

        return results

    @staticmethod
    def _extract_price(part: dict) -> float:
        """Return the lowest-tier unit price from PriceBreaks."""
        price_breaks = part.get("PriceBreaks") or []
        if not price_breaks:
            return 0.0
        # PriceBreaks are sorted by ascending Quantity; first entry is the
        # single-unit (or smallest MOQ) price.
        raw = price_breaks[0].get("Price", "0")
        # Price may contain currency symbols or commas (e.g. "$1,234.56")
        cleaned = re.sub(r"[^\d.]", "", str(raw))
        return float(cleaned) if cleaned else 0.0

    @staticmethod
    def _extract_stock(part: dict) -> int:
        """Parse the Availability string (e.g. '502 In Stock') into an int."""
        avail = part.get("Availability", "")
        match = re.search(r"([\d,]+)", str(avail))
        if match:
            return int(match.group(1).replace(",", ""))
        return 0
