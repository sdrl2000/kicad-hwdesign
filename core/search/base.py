"""부품 검색 엔진 — 기본 인터페이스"""

from abc import ABC, abstractmethod
from pydantic import BaseModel


class ComponentResult(BaseModel):
    """부품 검색 결과"""
    mfr_part_number: str
    description: str
    manufacturer: str
    package: str
    price_usd: float = 0.0
    stock: int = 0
    supplier: str = ""
    url: str = ""
    datasheet_url: str | None = None
    lcsc_number: str = ""


class AbstractComponentSearch(ABC):
    """부품 검색 추상 인터페이스"""

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[ComponentResult]:
        ...

    @abstractmethod
    async def get_by_part_number(self, part_number: str) -> ComponentResult | None:
        ...
