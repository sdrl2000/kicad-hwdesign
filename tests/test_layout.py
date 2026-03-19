"""
Layout Engine 테스트 — 실제 kicad-tools 연동

풋프린트 생성, 배치 최적화 데이터 모델 등
kicad-tools가 설치된 환경에서 실행
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestFootprintGenerator:
    """풋프린트 생성 테스트 — kicad-tools generators 직접 호출"""

    def test_create_soic8(self):
        from kicad_tools.library.generators import create_soic

        fp = create_soic(pins=8)
        assert fp.name == "SOIC-8_3.9x4.9mm_P1.27mm"
        assert len(fp.pads) == 8

    def test_create_soic16(self):
        from kicad_tools.library.generators import create_soic

        fp = create_soic(pins=16)
        assert len(fp.pads) == 16
        assert "SOIC-16" in fp.name

    def test_create_qfp48(self):
        from kicad_tools.library.generators import create_qfp

        fp = create_qfp(pins=48, pitch=0.5, body_size=7.0)
        assert len(fp.pads) == 48
        assert "LQFP-48" in fp.name

    def test_create_qfn16_with_exposed_pad(self):
        from kicad_tools.library.generators import create_qfn

        fp = create_qfn(pins=16, body_size=3.0, exposed_pad=1.5)
        assert len(fp.pads) == 17  # 16 + 1 exposed pad
        assert "EP" in fp.name

    def test_save_footprint_to_file(self):
        from kicad_tools.library.generators import create_soic

        fp = create_soic(pins=8)
        with tempfile.NamedTemporaryFile(suffix=".kicad_mod", delete=False) as f:
            path = f.name

        try:
            fp.save(path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 100

            content = open(path).read()
            assert "(footprint" in content
            assert "SOIC-8" in content
        finally:
            os.unlink(path)

    def test_footprint_generator_wrapper(self):
        """hwdesign FootprintGenerator 래퍼 테스트"""
        from core.layout.footprint_gen import FootprintGenerator, FootprintSpec

        gen = FootprintGenerator()
        assert gen._available is True

        spec = FootprintSpec(package_type="SOIC", pins=8)
        path = gen.generate(spec, output_dir=tempfile.mkdtemp())
        assert os.path.exists(path)
        assert path.endswith(".kicad_mod")


class TestPlacementDataModels:
    """배치 최적화 데이터 모델 테스트"""

    def test_placement_strategy_enum(self):
        from core.layout.placement import PlacementStrategy

        assert PlacementStrategy.HYBRID.value == "hybrid"
        assert PlacementStrategy.PHYSICS.value == "physics"
        assert PlacementStrategy.EVOLUTIONARY.value == "evolutionary"

    def test_placement_result_dataclass(self):
        from core.layout.placement import PlacementResult

        result = PlacementResult(
            output_path="/tmp/test.kicad_pcb",
            strategy="hybrid",
            generations=100,
            wire_length_mm=500.0,
            duration_seconds=2.5,
        )
        assert result.strategy == "hybrid"
        assert result.wire_length_mm == 500.0

    def test_placement_engine_init(self):
        """AIPlacementEngine 초기화 (kicad-tools 설치 확인)"""
        from core.layout.placement import AIPlacementEngine

        engine = AIPlacementEngine()
        assert engine._available is True


class TestRoutingDataModels:
    """라우팅 데이터 모델 테스트"""

    def test_routing_config(self):
        from core.layout.routing import RoutingConfig

        config = RoutingConfig(
            trace_width=0.3,
            trace_clearance=0.25,
            num_layers=4,
        )
        assert config.trace_width == 0.3
        assert config.num_layers == 4

    def test_routing_result(self):
        from core.layout.routing import RoutingResult

        result = RoutingResult(
            total_nets=50,
            routed_nets=48,
            failed_nets=["NET1", "NET2"],
            success_rate=0.96,
        )
        assert result.total_nets == 50
        assert len(result.failed_nets) == 2

    def test_routing_engine_init(self):
        from core.layout.routing import AIRoutingEngine

        engine = AIRoutingEngine()
        assert engine._available is True


class TestKicadToolsIntegration:
    """kicad-tools 직접 연동 테스트"""

    def test_placement_optimizer_import(self):
        from kicad_tools.optim.placement import PlacementOptimizer

        assert hasattr(PlacementOptimizer, "from_pcb")
        assert hasattr(PlacementOptimizer, "write_to_pcb")
        assert hasattr(PlacementOptimizer, "run")

    def test_evolutionary_optimizer_import(self):
        from kicad_tools.optim.evolutionary import EvolutionaryPlacementOptimizer

        assert hasattr(EvolutionaryPlacementOptimizer, "from_pcb")
        assert hasattr(EvolutionaryPlacementOptimizer, "optimize")
        assert hasattr(EvolutionaryPlacementOptimizer, "optimize_hybrid")

    def test_autorouter_import(self):
        from kicad_tools.router.core import Autorouter

        assert hasattr(Autorouter, "route_all")
        assert hasattr(Autorouter, "route_all_negotiated")
        assert hasattr(Autorouter, "route_all_parallel")
        assert hasattr(Autorouter, "add_component")

    def test_design_rules_import(self):
        from kicad_tools.router.rules import DesignRules

        rules = DesignRules(
            trace_width=0.25,
            trace_clearance=0.2,
            via_diameter=0.8,
            via_clearance=0.2,
        )
        assert rules.trace_width == 0.25
