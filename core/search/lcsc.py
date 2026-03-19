"""LCSC/JLCPCB 부품 검색 (JLCPCB SMT 조립 연동)"""

from __future__ import annotations

import httpx
from loguru import logger

from .base import AbstractComponentSearch, ComponentResult


class LCSCSearch(AbstractComponentSearch):
    """
    JLCPCB/LCSC 부품 검색 API

    JLCPCB SMT 조립 서비스와 직접 연동.
    API 키 불필요 — 공개 부품 검색 엔드포인트 사용.
    """

    SEARCH_URL = (
        "https://jlcpcb.com/api/overseas-pcb-order/v1/"
        "shoppingCart/smtGood/selectSmtComponentList"
    )

    async def search(self, query: str, limit: int = 10) -> list[ComponentResult]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) kicad-hwdesign/0.1",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
            try:
                resp = await client.post(
                    self.SEARCH_URL,
                    json={
                        "keyword": query,
                        "currentPage": 1,
                        "pageSize": min(limit, 30),
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return self._parse_results(data, limit)
            except Exception as e:
                logger.warning(f"LCSC/JLCPCB 검색 실패: {e}")
                return []

    async def get_by_part_number(self, part_number: str) -> ComponentResult | None:
        results = await self.search(part_number, limit=1)
        return results[0] if results else None

    def _parse_results(self, data: dict, limit: int = 10) -> list[ComponentResult]:
        results = []

        page_info = data.get("data", {}).get("componentPageInfo", {})
        product_list = page_info.get("list") or []

        for item in product_list:
            if len(results) >= limit:
                break
            try:
                # 가격 추출 (첫 번째 tier)
                price_list = item.get("componentPrices") or []
                price = float(price_list[0].get("productPrice", 0)) if price_list else 0.0

                # LCSC 번호 (componentCode)
                lcsc_code = item.get("componentCode", "")

                # 제조사
                brand = (
                    item.get("componentBrandEn")
                    or item.get("brandNameEn")
                    or ""
                )

                # 패키지
                package = item.get("encapStandard") or item.get("componentSpecificationEn") or ""

                results.append(
                    ComponentResult(
                        mfr_part_number=item.get("componentModelEn", ""),
                        description=item.get("describe", ""),
                        manufacturer=brand,
                        package=package,
                        price_usd=price,
                        stock=int(item.get("stockCount", 0)),
                        supplier="LCSC",
                        url=f"https://www.lcsc.com/product-detail/{lcsc_code}.html",
                        datasheet_url=item.get("dataManualUrl") or None,
                        lcsc_number=lcsc_code,
                    )
                )
            except (IndexError, ValueError, KeyError) as e:
                logger.debug(f"부품 파싱 오류: {e}")
                continue

        return results
