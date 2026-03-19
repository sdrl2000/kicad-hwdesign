"""
Schematic Symbol Placer

mixelpixx의 component_schematic.py + dynamic_symbol_loader.py 참조
kicad-skip 기반 심볼 배치 및 라이브러리 검색
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

from ..kicad_adapter.base import Position
from ..kicad_adapter.swig_adapter import SWIGSchematicAdapter


@dataclass
class ComponentSpec:
    """심볼 배치 스펙"""
    lib: str               # KiCad 라이브러리명 (예: "Device", "MCU_ST_STM32H7")
    symbol: str            # 심볼명 (예: "R", "STM32H743VITx")
    value: str = ""        # 값 (예: "10k", "100nF")
    reference_prefix: str = ""  # 참조 접두사 (예: "R", "C", "U")
    count: int = 1         # 수량
    footprint: str = ""    # 권장 풋프린트


@dataclass
class ConnectionSpec:
    """연결 스펙"""
    from_ref: str     # 예: "U1"
    from_pin: str     # 예: "VCC" 또는 "1"
    to_ref: str       # 예: "C1"
    to_pin: str       # 예: "1"


@dataclass
class SchematicSpec:
    """AI가 생성하는 회로 스펙 (JSON → 파이썬 변환)"""
    components: list[ComponentSpec] = field(default_factory=list)
    connections: list[ConnectionSpec] = field(default_factory=list)
    power_nets: list[str] = field(default_factory=lambda: ["+3.3V", "GND"])
    constraints: dict = field(default_factory=dict)


# 기본 심볼 → 라이브러리 매핑
DEFAULT_SYMBOL_MAP: dict[str, str] = {
    "R": "Device",
    "C": "Device",
    "C_Polarized": "Device",
    "L": "Device",
    "D": "Device",
    "LED": "Device",
    "Q_NPN_BCE": "Device",
    "Q_PNP_BCE": "Device",
    "Q_NMOS_GDS": "Device",
    "Q_PMOS_GDS": "Device",
    "Crystal": "Device",
    "Fuse": "Device",
    "Conn_01x02": "Connector_Generic",
    "Conn_01x04": "Connector_Generic",
    "Conn_01x06": "Connector_Generic",
    "USB_C_Receptacle_USB2.0": "Connector",
    "Barrel_Jack": "Connector",
}

# 참조 접두사 자동 결정
PREFIX_MAP: dict[str, str] = {
    "R": "R",
    "C": "C",
    "C_Polarized": "C",
    "L": "L",
    "D": "D",
    "LED": "D",
    "Q_NPN_BCE": "Q",
    "Q_PNP_BCE": "Q",
    "Q_NMOS_GDS": "Q",
    "Q_PMOS_GDS": "Q",
    "Crystal": "Y",
    "Fuse": "F",
}


class SymbolPlacer:
    """
    스키매틱 심볼 배치 엔진

    기능:
    1. AI 스펙(SchematicSpec)에서 심볼 자동 배치
    2. 그리드 기반 자동 위치 계산
    3. KiCad 10,000+ 심볼 라이브러리 검색
    4. 참조 번호 자동 할당
    """

    # 배치 그리드 설정
    GRID_SPACING_X = 20.0  # mm
    GRID_SPACING_Y = 15.0  # mm
    START_X = 50.0
    START_Y = 50.0
    MAX_COLS = 6

    def __init__(self, adapter: SWIGSchematicAdapter):
        self.adapter = adapter
        self._ref_counters: dict[str, int] = {}

    def place_from_spec(self, spec: SchematicSpec) -> list[str]:
        """
        SchematicSpec에서 심볼 자동 배치

        Args:
            spec: AI가 생성한 회로 스펙

        Returns:
            배치된 참조 지정자 목록 (예: ["U1", "R1", "R2", "C1"])
        """
        placed_refs: list[str] = []
        col = 0
        row = 0

        for comp_spec in spec.components:
            for i in range(comp_spec.count):
                # 위치 계산
                x = self.START_X + col * self.GRID_SPACING_X
                y = self.START_Y + row * self.GRID_SPACING_Y
                pos = Position(x, y)

                # 라이브러리 결정
                lib = comp_spec.lib or DEFAULT_SYMBOL_MAP.get(comp_spec.symbol, "Device")

                # 참조 번호 할당
                prefix = comp_spec.reference_prefix or self._get_prefix(comp_spec.symbol)
                ref = self._next_reference(prefix)

                # 값 결정
                value = comp_spec.value or comp_spec.symbol

                # 심볼 배치
                try:
                    self.adapter.place_symbol(
                        lib=lib,
                        symbol=comp_spec.symbol,
                        pos=pos,
                        reference=ref,
                        value=value,
                    )
                    placed_refs.append(ref)
                    logger.info(f"배치: {ref} ({lib}:{comp_spec.symbol}) = {value}")
                except Exception as e:
                    logger.error(f"배치 실패 {ref}: {e}")

                # 그리드 진행
                col += 1
                if col >= self.MAX_COLS:
                    col = 0
                    row += 1

        # 전원 심볼 배치
        self._place_power_symbols(spec.power_nets, row + 1)

        return placed_refs

    def search_symbol(self, query: str, kicad_lib_path: str = "") -> list[dict]:
        """
        KiCad 공식 라이브러리에서 심볼 검색

        Args:
            query: 검색어 (예: "STM32H7", "USB-C", "LDO")
            kicad_lib_path: KiCad 심볼 라이브러리 경로

        Returns:
            [{"lib": "MCU_ST_STM32H7", "symbol": "STM32H743VITx", "description": "..."}]
        """
        from ..config import HWDesignConfig

        if not kicad_lib_path:
            config = HWDesignConfig.from_env()
            kicad_lib_path = config.kicad.symbol_lib_path

        results = []
        lib_path = Path(kicad_lib_path)

        if not lib_path.exists():
            logger.warning(f"심볼 라이브러리 경로 없음: {kicad_lib_path}")
            return results

        query_lower = query.lower()

        for sym_file in lib_path.glob("*.kicad_sym"):
            lib_name = sym_file.stem
            try:
                content = sym_file.read_text(encoding="utf-8")
                # 빠른 텍스트 검색
                if query_lower in content.lower():
                    # 심볼명 추출
                    for line in content.split("\n"):
                        if line.strip().startswith('(symbol "') and query_lower in line.lower():
                            # (symbol "LibName:SymbolName" 형식
                            parts = line.strip().split('"')
                            if len(parts) >= 2:
                                full_name = parts[1]
                                if ":" in full_name:
                                    sym_name = full_name.split(":")[1]
                                else:
                                    sym_name = full_name
                                # 하위 심볼 (_0, _1) 필터
                                if "_" not in sym_name or not sym_name.split("_")[-1].isdigit():
                                    results.append({
                                        "lib": lib_name,
                                        "symbol": sym_name,
                                        "full_name": full_name,
                                    })
            except Exception:
                continue

        logger.info(f"심볼 검색 '{query}': {len(results)}개 발견")
        return results[:50]  # 최대 50개

    def _place_power_symbols(self, power_nets: list[str], start_row: int):
        """전원 심볼 (VCC, GND 등) 배치"""
        for i, net in enumerate(power_nets):
            x = self.START_X + i * self.GRID_SPACING_X
            y = self.START_Y + start_row * self.GRID_SPACING_Y
            pos = Position(x, y)

            if "GND" in net.upper():
                lib = "power"
                symbol = "GND"
            elif "VCC" in net.upper() or "+3.3V" in net or "+5V" in net:
                lib = "power"
                symbol = net.replace("+", "").replace("V", "V")
                if net == "+3.3V":
                    symbol = "+3V3"
                elif net == "+5V":
                    symbol = "+5V"
                else:
                    symbol = "VCC"
            else:
                lib = "power"
                symbol = net

            try:
                self.adapter.add_label(
                    text=net,
                    pos=pos,
                    label_type="power",
                )
            except Exception as e:
                logger.debug(f"전원 심볼 {net} 배치 실패: {e}")

    def _get_prefix(self, symbol: str) -> str:
        """심볼명에서 참조 접두사 추출"""
        if symbol in PREFIX_MAP:
            return PREFIX_MAP[symbol]
        # MCU, IC 계열
        if any(k in symbol.upper() for k in ["STM32", "ESP32", "NRF52", "RP2040", "ATMEGA"]):
            return "U"
        if symbol.startswith("Conn") or symbol.startswith("USB") or symbol.startswith("Barrel"):
            return "J"
        return "U"

    def _next_reference(self, prefix: str) -> str:
        """다음 참조 번호 반환 (예: R1, R2, ...)"""
        current = self._ref_counters.get(prefix, 0)
        self._ref_counters[prefix] = current + 1
        return f"{prefix}{current + 1}"
