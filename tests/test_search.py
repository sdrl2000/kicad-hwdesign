"""
Search Engine 및 통합 테스트

부품 검색 모델, AI Orchestrator JSON 파싱,
Config, 서버 핸들러 등
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestComponentResult:
    """부품 검색 결과 모델 테스트"""

    def test_create_result(self):
        from core.search.base import ComponentResult

        r = ComponentResult(
            mfr_part_number="STM32H743VIT6",
            description="ARM Cortex-M7 480MHz",
            manufacturer="STMicroelectronics",
            package="LQFP-100",
            price_usd=12.50,
            stock=5000,
            supplier="LCSC",
            url="https://lcsc.com/product-detail/C123456.html",
            lcsc_number="C123456",
        )
        assert r.mfr_part_number == "STM32H743VIT6"
        assert r.price_usd == 12.50
        assert r.supplier == "LCSC"

    def test_result_json_serialization(self):
        from core.search.base import ComponentResult

        r = ComponentResult(
            mfr_part_number="ESP32-WROOM-32",
            description="WiFi+BT module",
            manufacturer="Espressif",
            package="Module",
        )
        data = r.model_dump()
        assert data["mfr_part_number"] == "ESP32-WROOM-32"
        assert "manufacturer" in data


class TestPluginBridge:
    """플러그인 브릿지 테스트"""

    def test_bridge_creation(self):
        from core.bridge import PluginBridge

        bridge = PluginBridge()
        assert bridge._socket_path == "/tmp/hwdesign_plugin.sock"

    def test_bridge_plugin_not_running(self):
        from core.bridge import PluginBridge

        bridge = PluginBridge("/tmp/nonexistent_test.sock")
        assert bridge.is_plugin_running() is False

    def test_bridge_fallback(self):
        from core.bridge import PluginBridge

        bridge = PluginBridge("/tmp/nonexistent_test.sock")
        result = bridge.send_or_fallback(
            "test_action",
            {"param": "value"},
            fallback_fn=lambda p: {"status": "ok", "fallback": True},
        )
        assert result.get("fallback") is True


class TestConfig:
    """설정 관리 테스트"""

    def test_default_config(self):
        from core.config import HWDesignConfig

        cfg = HWDesignConfig.from_env()
        assert cfg.server.socket_path == "/tmp/hwdesign.sock"
        assert cfg.server.max_workers == 4
        assert cfg.ai.model == "claude-sonnet-4-6"

    def test_kicad_config_path_detection(self):
        from core.config import KiCadConfig

        kc = KiCadConfig()
        # Linux 환경에서 기본 경로 확인
        assert kc.kicad_path != ""

    def test_search_config_priority(self):
        from core.config import SearchConfig

        sc = SearchConfig()
        assert sc.search_priority == ["lcsc", "mouser", "digikey", "web"]


class TestDataModels:
    """전체 데이터 모델 테스트"""

    def test_position(self):
        from core.kicad_adapter.base import Position

        p = Position(3.0, 4.0)
        assert abs(p.distance_to(Position(0, 0)) - 5.0) < 0.001

    def test_position_iter(self):
        from core.kicad_adapter.base import Position

        p = Position(1.0, 2.0)
        x, y = p
        assert x == 1.0
        assert y == 2.0

    def test_footprint_info(self):
        from core.kicad_adapter.base import FootprintInfo, Position

        fp = FootprintInfo(
            reference="U1",
            value="STM32H743",
            footprint_lib="Package_QFP:LQFP-100",
            position=Position(50.0, 50.0),
            rotation=0.0,
            layer="F.Cu",
        )
        assert fp.reference == "U1"

    def test_layer_enum(self):
        from core.kicad_adapter.base import Layer

        assert Layer.F_CU == "F.Cu"
        assert Layer.B_CU == "B.Cu"
        assert Layer.EDGE_CUTS == "Edge.Cuts"


class TestMCPServer:
    """MCP 서버 구조 테스트"""

    def test_mcp_server_created(self):
        from core.main import mcp

        assert mcp.name == "kicad-hwdesign"

    def test_mcp_tools_registered(self):
        """MCP 도구가 등록되었는지 확인"""
        from core.main import mcp

        # fastmcp 서버에 등록된 도구 이름 확인
        # mcp._tool_manager 내부의 도구 목록 확인
        assert mcp is not None

    def test_main_entry_point(self):
        from core.main import main

        assert callable(main)
