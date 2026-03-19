"""
End-to-End 테스트 — 실제 KiCad 9 + LCSC API + 넷리스트 파싱

kicad-cli 9.0.8 + JLCPCB API + NetlistExtractor 실 동작 확인.
KiCad 9 설치 필요 (CI에서는 skip).
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

FIXTURES = Path(__file__).parent / "fixtures" / "sample_project"
VOLTAGE_DIVIDER = str(FIXTURES / "voltage_divider.kicad_sch")
LABEL_MCU = str(FIXTURES / "label_based_mcu.kicad_sch")
SAMPLE_SCH = str(FIXTURES / "sample.kicad_sch")

HAS_KICAD = Path(r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe").exists() or bool(
    __import__("shutil").which("kicad-cli")
)


# ═══════════════════════════════════════════════════════════
# kicad-cli E2E
# ═══════════════════════════════════════════════════════════


@pytest.mark.skipif(not HAS_KICAD, reason="KiCad 9 not installed")
class TestKiCadCLI:
    def test_cli_auto_detect(self):
        from core.kicad_adapter.cli_adapter import CLIAdapter

        cli = CLIAdapter(schematic_path=VOLTAGE_DIVIDER)
        assert "kicad-cli" in cli._cli

    def test_erc(self):
        from core.kicad_adapter.cli_adapter import CLIAdapter

        cli = CLIAdapter(schematic_path=VOLTAGE_DIVIDER)
        violations = cli.run_erc()
        # voltage_divider는 간단한 회로이므로 심각한 에러 없음
        errors = [v for v in violations if v.severity == "error"]
        assert len(errors) == 0

    def test_bom_export(self):
        from core.kicad_adapter.cli_adapter import CLIAdapter

        cli = CLIAdapter(schematic_path=VOLTAGE_DIVIDER)
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            output = f.name
        try:
            result = cli.export_bom(output)
            content = Path(result).read_text(encoding="utf-8")
            assert len(content) > 0
            assert "R1" in content or "R" in content
        finally:
            Path(output).unlink(missing_ok=True)

    def test_netlist_export(self):
        from core.kicad_adapter.cli_adapter import CLIAdapter

        cli = CLIAdapter(schematic_path=VOLTAGE_DIVIDER)
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            output = f.name
        try:
            result = cli.generate_netlist(output)
            content = Path(result).read_text(encoding="utf-8")
            assert len(content) > 0
            assert "netlist" in content.lower() or "comp" in content.lower()
        finally:
            Path(output).unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════
# 넷리스트 파서 — 복잡한 스키매틱 검증
# ═══════════════════════════════════════════════════════════


class TestNetlistExtractorComplex:
    def test_parse_voltage_divider(self):
        from core.schematic.netlist_extractor import NetlistExtractor

        ext = NetlistExtractor(VOLTAGE_DIVIDER)
        data = ext.parse()
        assert len(data.components) >= 2  # 최소 2개 저항
        refs = {c.reference for c in data.components}
        assert "R1" in refs

    def test_parse_label_based_mcu(self):
        from core.schematic.netlist_extractor import NetlistExtractor

        if not Path(LABEL_MCU).exists():
            pytest.skip("label_based_mcu.kicad_sch not found")
        ext = NetlistExtractor(LABEL_MCU)
        data = ext.parse()
        assert len(data.components) >= 3  # MCU + 주변 부품들
        # MCU가 존재하는지 확인
        mcu_found = any("MCU" in c.lib_id or "STM32" in c.lib_id or "RP2040" in c.lib_id
                        for c in data.components)
        # 넷 라벨이 있는지 확인
        assert len(data.nets) >= 1 or mcu_found

    def test_wire_network(self):
        from core.schematic.netlist_extractor import NetlistExtractor

        ext = NetlistExtractor(VOLTAGE_DIVIDER)
        data = ext.parse()
        if data.wires:
            network = ext.build_wire_network()
            assert len(network) >= 2

    def test_parse_sample_sch(self):
        """수동 생성 스키매틱 파싱 (kicad-cli 불필요)"""
        from core.schematic.netlist_extractor import NetlistExtractor

        ext = NetlistExtractor(SAMPLE_SCH)
        data = ext.parse()
        assert len(data.components) == 3  # R1, R2, C1
        refs = {c.reference for c in data.components}
        assert refs == {"R1", "R2", "C1"}
        assert len(data.wires) == 2
        assert len(data.nets) == 2  # VCC, GND


# ═══════════════════════════════════════════════════════════
# LCSC/JLCPCB API 실제 호출
# ═══════════════════════════════════════════════════════════


class TestLCSCLive:
    @pytest.mark.asyncio
    async def test_search_stm32(self):
        from core.search.lcsc import LCSCSearch

        s = LCSCSearch()
        results = await s.search("STM32H743VIT6", limit=3)
        assert len(results) > 0
        assert results[0].mfr_part_number == "STM32H743VIT6"
        assert results[0].supplier == "LCSC"

    @pytest.mark.asyncio
    async def test_search_resistor(self):
        from core.search.lcsc import LCSCSearch

        s = LCSCSearch()
        results = await s.search("10k 0402", limit=3)
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_get_by_part_number(self):
        from core.search.lcsc import LCSCSearch

        s = LCSCSearch()
        result = await s.get_by_part_number("STM32H743VIT6")
        assert result is not None
        assert result.stock >= 0


# ═══════════════════════════════════════════════════════════
# 동적 심볼 로더 — 실제 KiCad 라이브러리
# ═══════════════════════════════════════════════════════════


@pytest.mark.skipif(not HAS_KICAD, reason="KiCad 9 not installed")
class TestDynamicSymbolLoaderLive:
    def test_find_libraries(self):
        from core.schematic.dynamic_loader import DynamicSymbolLoader

        loader = DynamicSymbolLoader()
        dirs = loader.find_kicad_symbol_libraries()
        assert len(dirs) > 0

    def test_extract_resistor(self):
        from core.schematic.dynamic_loader import DynamicSymbolLoader

        loader = DynamicSymbolLoader()
        block = loader.extract_symbol("Device", "R")
        assert block is not None
        assert 'symbol "R"' in block

    def test_extract_stm32(self):
        from core.schematic.dynamic_loader import DynamicSymbolLoader

        loader = DynamicSymbolLoader()
        block = loader.extract_symbol("MCU_ST_STM32H7", "STM32H743VITx")
        assert block is not None
        assert len(block) > 10000  # 대형 심볼

    def test_extract_led(self):
        from core.schematic.dynamic_loader import DynamicSymbolLoader

        loader = DynamicSymbolLoader()
        block = loader.extract_symbol("Device", "LED")
        assert block is not None
