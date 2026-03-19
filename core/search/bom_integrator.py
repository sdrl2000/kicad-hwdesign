"""BOM 통합기 — 부품 검색 결과를 BOM에 병합"""

from __future__ import annotations

from loguru import logger

from .base import AbstractComponentSearch, ComponentResult


class BOMIntegrator:
    """BOM에 검색된 부품 정보(가격/재고)를 병합"""

    def __init__(self, searchers: list[AbstractComponentSearch]):
        self.searchers = searchers  # 우선순위 순서

    async def enrich_bom(self, bom: list[dict]) -> list[dict]:
        """
        BOM 항목에 가격/재고/구매 URL 추가

        bom item: {"reference": "R1", "value": "10k", "footprint": "0402"}
        → 가격, 재고, 구매 URL 추가
        """
        enriched = []
        for item in bom:
            query = f"{item.get('value', '')} {item.get('footprint', '')}"
            result = await self._search_with_fallback(query)

            enriched_item = {**item}
            if result:
                enriched_item.update({
                    "mfr_part_number": result.mfr_part_number,
                    "manufacturer": result.manufacturer,
                    "price_usd": result.price_usd,
                    "stock": result.stock,
                    "supplier": result.supplier,
                    "url": result.url,
                    "lcsc_number": result.lcsc_number,
                })
            enriched.append(enriched_item)

        total_cost = sum(
            item.get("price_usd", 0) * int(item.get("count", 1))
            for item in enriched
        )
        logger.info(f"BOM 보강 완료: {len(enriched)}개 항목, 총 ${total_cost:.2f}")
        return enriched

    async def _search_with_fallback(self, query: str) -> ComponentResult | None:
        """우선순위 순서대로 검색 시도"""
        for searcher in self.searchers:
            try:
                results = await searcher.search(query, limit=1)
                if results:
                    return results[0]
            except Exception as e:
                logger.debug(f"{searcher.__class__.__name__} 검색 실패: {e}")
                continue
        return None
