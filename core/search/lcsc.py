"""LCSC 부품 검색 (JLCPCB 연동)"""

from __future__ import annotations

import httpx
from loguru import logger

from .base import AbstractComponentSearch, ComponentResult


class LCSCSearch(AbstractComponentSearch):
    """
    LCSC 부품 검색 API

    JLCPCB SMT 조립 서비스와 직접 연동 가능
    Basic/Extended 파트 구분 지원
    """

    BASE_URL = "https://wmsc.lcsc.com/ftsp/wm/product/search"

    async def search(self, query: str, limit: int = 10) -> list[ComponentResult]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(
                    self.BASE_URL,
                    json={
                        "keyword": query,
                        "currentPage": 1,
                        "pageSize": min(limit, 50),
                    },
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
                return self._parse_results(data)
            except Exception as e:
                logger.warning(f"LCSC 검색 실패: {e}")
                return []

    async def get_by_part_number(self, part_number: str) -> ComponentResult | None:
        results = await self.search(part_number, limit=1)
        return results[0] if results else None

    def _parse_results(self, data: dict) -> list[ComponentResult]:
        results = []
        product_list = data.get("result", {}).get("tipProductDetailUrlVO", [])
        if not product_list:
            product_list = data.get("result", {}).get("productSearchResultVO", {}).get("productList", [])

        for item in product_list:
            try:
                results.append(
                    ComponentResult(
                        mfr_part_number=item.get("productModel", ""),
                        description=item.get("productDescEn", ""),
                        manufacturer=item.get("brandNameEn", ""),
                        package=item.get("encapStandard", ""),
                        price_usd=float(item.get("productPriceList", [{}])[0].get("productPrice", 0)),
                        stock=int(item.get("stockNumber", 0)),
                        supplier="LCSC",
                        url=f"https://www.lcsc.com/product-detail/{item.get('productCode', '')}.html",
                        datasheet_url=item.get("pdfUrl", None),
                        lcsc_number=item.get("productCode", ""),
                    )
                )
            except (IndexError, ValueError, KeyError):
                continue

        return results
