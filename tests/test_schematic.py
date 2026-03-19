"""
Schematic Engine 테스트

심볼 배치 스펙, 와이어 라우팅 경로 계산,
핀 분석, 디바이스 트리 생성 등
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.kicad_adapter.base import Position
from core.schematic.symbol_placer import (
    ComponentSpec,
    ConnectionSpec,
    SchematicSpec,
    SymbolPlacer,
    DEFAULT_SYMBOL_MAP,
    PREFIX_MAP,
)
from core.schematic.wire_router import RoutingMode, WireRouter


class TestSchematicSpec:
    """SchematicSpec 데이터 모델 테스트"""

    def test_empty_spec(self):
        spec = SchematicSpec()
        assert len(spec.components) == 0
        assert spec.power_nets == ["+3.3V", "GND"]

    def test_component_spec(self):
        comp = ComponentSpec(
            lib="Device", symbol="R", value="10k", count=4
        )
        assert comp.lib == "Device"
        assert comp.count == 4

    def test_full_spec(self):
        spec = SchematicSpec(
            components=[
                ComponentSpec(lib="Device", symbol="R", value="10k", count=4),
                ComponentSpec(lib="Device", symbol="C", value="100nF", count=4),
                ComponentSpec(
                    lib="MCU_ST_STM32H7",
                    symbol="STM32H743VITx",
                    count=1,
                    reference_prefix="U",
                ),
            ],
            connections=[
                ConnectionSpec(from_ref="U1", from_pin="VCC", to_ref="C1", to_pin="1"),
            ],
            power_nets=["+3.3V", "+5V", "GND"],
            constraints={"board_size_mm": [100, 80], "layers": 4},
        )
        assert len(spec.components) == 3
        assert spec.constraints["layers"] == 4


class TestSymbolMap:
    """심볼 매핑 테스트"""

    def test_default_symbol_map(self):
        assert DEFAULT_SYMBOL_MAP["R"] == "Device"
        assert DEFAULT_SYMBOL_MAP["C"] == "Device"
        assert DEFAULT_SYMBOL_MAP["LED"] == "Device"

    def test_prefix_map(self):
        assert PREFIX_MAP["R"] == "R"
        assert PREFIX_MAP["C"] == "C"
        assert PREFIX_MAP["LED"] == "D"
        assert PREFIX_MAP["Crystal"] == "Y"


class TestWireRouter:
    """와이어 라우팅 경로 계산 테스트"""

    def test_direct_path(self):
        path = WireRouter._calculate_path(
            Position(0, 0), Position(10, 5), RoutingMode.DIRECT
        )
        assert len(path) == 2
        assert path[0].x_mm == 0
        assert path[1].x_mm == 10

    def test_orthogonal_h_path(self):
        path = WireRouter._calculate_path(
            Position(0, 0), Position(10, 5), RoutingMode.ORTHOGONAL_H
        )
        assert len(path) == 3
        # 수평 우선: (0,0) → (10,0) → (10,5)
        assert path[1].x_mm == 10.0
        assert path[1].y_mm == 0.0
        assert path[2].x_mm == 10.0
        assert path[2].y_mm == 5.0

    def test_orthogonal_v_path(self):
        path = WireRouter._calculate_path(
            Position(0, 0), Position(10, 5), RoutingMode.ORTHOGONAL_V
        )
        assert len(path) == 3
        # 수직 우선: (0,0) → (0,5) → (10,5)
        assert path[1].x_mm == 0.0
        assert path[1].y_mm == 5.0

    def test_same_x_simplifies(self):
        """같은 X 좌표면 직선으로 간소화"""
        path = WireRouter._calculate_path(
            Position(5, 0), Position(5, 10), RoutingMode.ORTHOGONAL_H
        )
        assert len(path) == 2  # 중간점 불필요

    def test_same_y_simplifies(self):
        """같은 Y 좌표면 직선으로 간소화"""
        path = WireRouter._calculate_path(
            Position(0, 5), Position(10, 5), RoutingMode.ORTHOGONAL_V
        )
        assert len(path) == 2


class TestPinAnalyzer:
    """핀 분석기 테스트"""

    def test_detect_stm32(self):
        from core.firmware.pin_analyzer import PinAnalyzer

        analyzer = PinAnalyzer()
        assert analyzer.detect_mcu_family("STM32H743VIT6") == "stm32"
        assert analyzer.detect_mcu_family("STM32F103C8T6") == "stm32"

    def test_detect_esp32(self):
        from core.firmware.pin_analyzer import PinAnalyzer

        analyzer = PinAnalyzer()
        assert analyzer.detect_mcu_family("ESP32-WROOM-32") == "esp32"

    def test_detect_rp2040(self):
        from core.firmware.pin_analyzer import PinAnalyzer

        analyzer = PinAnalyzer()
        assert analyzer.detect_mcu_family("RP2040") == "rp2040"

    def test_infer_i2c_function(self):
        from core.firmware.pin_analyzer import PinAnalyzer, PinFunction

        analyzer = PinAnalyzer()
        assert analyzer.infer_pin_function("I2C1_SDA") == PinFunction.I2C
        assert analyzer.infer_pin_function("SCL0") == PinFunction.I2C

    def test_infer_spi_function(self):
        from core.firmware.pin_analyzer import PinAnalyzer, PinFunction

        analyzer = PinAnalyzer()
        assert analyzer.infer_pin_function("SPI1_MOSI") == PinFunction.SPI
        assert analyzer.infer_pin_function("SCK") == PinFunction.SPI

    def test_infer_uart_function(self):
        from core.firmware.pin_analyzer import PinAnalyzer, PinFunction

        analyzer = PinAnalyzer()
        assert analyzer.infer_pin_function("UART1_TX") == PinFunction.UART
        assert analyzer.infer_pin_function("USART2_RX") == PinFunction.UART

    def test_infer_power_function(self):
        from core.firmware.pin_analyzer import PinAnalyzer, PinFunction

        analyzer = PinAnalyzer()
        assert analyzer.infer_pin_function("VCC") == PinFunction.POWER
        assert analyzer.infer_pin_function("GND") == PinFunction.POWER

    def test_pin_conflict_detection(self):
        from core.firmware.pin_analyzer import (
            PinAnalyzer,
            PinAssignment,
            PinFunction,
            ConflictSeverity,
        )

        analyzer = PinAnalyzer()
        assignments = [
            PinAssignment(pin_name="PA0", net_name="", function=PinFunction.GPIO),
            PinAssignment(pin_name="PA1", net_name="", function=PinFunction.GPIO),
        ]
        conflicts = analyzer.analyze_pins(assignments)
        # 미연결 핀 경고가 있어야 함
        assert any(c.severity == ConflictSeverity.WARNING for c in conflicts)


class TestDeviceTreeGenerator:
    """디바이스 트리 생성 테스트"""

    def test_detect_soc(self):
        from core.firmware.device_tree_gen import DeviceTreeGenerator

        gen = DeviceTreeGenerator()
        components = [
            {"reference": "U1", "value": "STM32H743VIT6"},
        ]
        result = gen.generate(
            components=components,
            nets={},
            board_name="test-board",
        )
        assert result.soc_family == "stm32"
        assert "stm32f4" in result.dts_content.lower() or "stm32" in result.dts_content.lower()

    def test_detect_peripherals(self):
        from core.firmware.device_tree_gen import DeviceTreeGenerator

        gen = DeviceTreeGenerator()
        components = [
            {"reference": "U1", "value": "STM32F411"},
            {"reference": "U2", "value": "BMP280"},
            {"reference": "U3", "value": "SSD1306"},
        ]
        result = gen.generate(
            components=components,
            nets={},
            board_name="sensor-board",
        )
        assert len(result.peripherals) == 2
        periph_names = [p.name for p in result.peripherals]
        assert "bmp280" in periph_names
        assert "ssd1306" in periph_names

    def test_dts_content_has_nodes(self):
        from core.firmware.device_tree_gen import DeviceTreeGenerator

        gen = DeviceTreeGenerator()
        components = [
            {"reference": "U1", "value": "STM32F411"},
            {"reference": "U2", "value": "BMP280"},
        ]
        result = gen.generate(components=components, nets={})
        assert "bosch,bmp280" in result.dts_content
        assert "&i2c" in result.dts_content


class TestNetlistExtractor:
    """넷리스트 추출기 테스트 (샘플 스키매틱 사용)"""

    SAMPLE = os.path.join(
        os.path.dirname(__file__), "fixtures", "sample_project", "sample.kicad_sch"
    )

    def test_parse_components(self):
        from core.schematic.netlist_extractor import NetlistExtractor

        ext = NetlistExtractor(self.SAMPLE)
        data = ext.parse()
        assert len(data.components) == 3
        refs = [c.reference for c in data.components]
        assert "R1" in refs
        assert "R2" in refs
        assert "C1" in refs

    def test_parse_component_values(self):
        from core.schematic.netlist_extractor import NetlistExtractor

        ext = NetlistExtractor(self.SAMPLE)
        data = ext.parse()
        r1 = next(c for c in data.components if c.reference == "R1")
        assert r1.value == "10k"
        assert r1.lib_id == "Device:R"

    def test_parse_nets(self):
        from core.schematic.netlist_extractor import NetlistExtractor

        ext = NetlistExtractor(self.SAMPLE)
        data = ext.parse()
        net_names = [n.name for n in data.nets]
        assert "VCC" in net_names
        assert "GND" in net_names

    def test_parse_wires(self):
        from core.schematic.netlist_extractor import NetlistExtractor

        ext = NetlistExtractor(self.SAMPLE)
        data = ext.parse()
        assert len(data.wires) == 2

    def test_parse_lib_symbols(self):
        from core.schematic.netlist_extractor import NetlistExtractor

        ext = NetlistExtractor(self.SAMPLE)
        data = ext.parse()
        assert "Device:R" in data.lib_symbols
        assert "1" in data.lib_symbols["Device:R"]
        assert "2" in data.lib_symbols["Device:R"]

    def test_wire_network(self):
        from core.schematic.netlist_extractor import NetlistExtractor

        ext = NetlistExtractor(self.SAMPLE)
        ext.parse()
        network = ext.build_wire_network()
        assert len(network) > 0


class TestHALCodeGenerator:
    """HAL 코드 생성기 테스트"""

    def test_stm32_hal_generation(self):
        from core.firmware.hal_codegen import HALCodeGenerator

        gen = HALCodeGenerator()
        result = gen.generate(
            components=[{"reference": "U1", "value": "STM32F411CEU6"}],
            nets={"I2C1_SDA": ["U1.PB7"], "I2C1_SCL": ["U1.PB6"],
                  "UART1_TX": ["U1.PA9"], "GPIO_LED": ["U1.PA5"]},
            framework="stm32_hal",
            board_name="test-board",
        )
        assert "I2C" in result.code
        assert "UART" in result.code
        assert "test-board" in result.code

    def test_arduino_generation(self):
        from core.firmware.hal_codegen import HALCodeGenerator

        gen = HALCodeGenerator()
        result = gen.generate(
            components=[{"reference": "U1", "value": "ATmega328P"}],
            nets={"I2C_SDA": ["U1.SDA"], "SPI_MOSI": ["U1.PB3"]},
            framework="arduino",
            board_name="arduino-board",
        )
        assert "#include <Wire.h>" in result.code
        assert "#include <SPI.h>" in result.code


class TestDynamicSymbolLoader:
    """동적 심볼 로더 테스트"""

    def test_find_libraries(self):
        from core.schematic.dynamic_loader import DynamicSymbolLoader

        loader = DynamicSymbolLoader()
        dirs = loader.find_kicad_symbol_libraries()
        # CI 환경에서는 라이브러리 없을 수 있음
        assert isinstance(dirs, list)

    def test_extract_block_matching(self):
        from core.schematic.dynamic_loader import DynamicSymbolLoader

        sample = '(symbol "TestSym" (property "Ref" "U") (pin passive line))'
        result = DynamicSymbolLoader._extract_symbol_block(sample, "TestSym")
        assert result is not None
        assert "TestSym" in result

    def test_extract_block_nested(self):
        from core.schematic.dynamic_loader import DynamicSymbolLoader

        sample = '''(symbol "Outer"
  (property "Ref" "U")
  (symbol "Outer_0_1"
    (pin passive line)
  )
)'''
        result = DynamicSymbolLoader._extract_symbol_block(sample, "Outer")
        assert result is not None
        assert "Outer_0_1" in result
