"""
AI Routing Engine — rjwalters Autorouter 래핑

Autorouter, AdaptiveAutorouter를 AI 오케스트레이터와 연결
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger


@dataclass
class RoutingConfig:
    """라우팅 설정"""
    grid_resolution: float = 0.1       # mm
    trace_width: float = 0.25          # mm
    trace_clearance: float = 0.2       # mm
    via_diameter: float = 0.8          # mm
    via_drill: float = 0.4             # mm
    via_clearance: float = 0.2         # mm
    min_trace_width: float = 0.15      # mm
    min_clearance: float = 0.15        # mm
    num_layers: int = 2
    max_iterations: int = 100


@dataclass
class RoutingResult:
    """라우팅 결과"""
    total_nets: int
    routed_nets: int
    failed_nets: list[str] = field(default_factory=list)
    success_rate: float = 0.0
    total_wire_length_mm: float = 0.0
    via_count: int = 0
    duration_seconds: float = 0.0
    output_path: str = ""


class AIRoutingEngine:
    """
    AI 기반 PCB 라우팅 엔진

    rjwalters의 Autorouter / AdaptiveAutorouter를
    직접 import하여 사용

    라우팅 알고리즘:
    - 기본: A* pathfinding
    - 고급: Negotiated cost routing
    - 적응형: 자동 파라미터 튜닝
    - 병렬: 멀티코어 병렬 라우팅
    """

    def __init__(self, config: RoutingConfig | None = None):
        self.config = config or RoutingConfig()
        self._check_dependencies()

    def _check_dependencies(self):
        try:
            from kicad_tools.router import Autorouter

            self._available = True
        except ImportError:
            logger.warning("kicad-tools 미설치")
            self._available = False

    def route(
        self,
        pcb_path: str,
        method: str = "adaptive",
        config: RoutingConfig | None = None,
    ) -> RoutingResult:
        """
        PCB 자동 라우팅 실행

        Args:
            pcb_path: .kicad_pcb 파일 경로
            method: 라우팅 방식 ("basic", "negotiated", "adaptive", "parallel")
            config: 라우팅 설정 (None이면 기본값 사용)

        Returns:
            RoutingResult
        """
        if not self._available:
            raise RuntimeError("kicad-tools가 설치되지 않음")

        import time

        from kicad_tools.router import Autorouter
        from kicad_tools.router.rules import DesignRules
        from kicad_tools.schema.pcb import PCB

        cfg = config or self.config
        start_time = time.time()

        # PCB 로드
        pcb = PCB.load(pcb_path)
        logger.info(f"PCB 로드: {pcb_path}")

        # 설계 규칙 설정
        rules = DesignRules(
            grid_resolution=cfg.grid_resolution,
            trace_width=cfg.trace_width,
            trace_clearance=cfg.trace_clearance,
            via_diameter=cfg.via_diameter,
            via_clearance=cfg.via_clearance,
            min_trace_width=cfg.min_trace_width,
            min_clearance=cfg.min_clearance,
            num_layers=cfg.num_layers,
        )

        # 라우터 생성
        router = Autorouter(
            width=pcb.width,
            height=pcb.height,
            rules=rules,
            grid_resolution=cfg.grid_resolution,
        )

        # 컴포넌트 및 넷 등록
        for fp in pcb.footprints:
            pads = [
                {
                    "number": p.number,
                    "x": p.position[0],
                    "y": p.position[1],
                    "net_name": p.net_name,
                }
                for p in fp.pads
            ]
            router.add_component(fp.reference, pads)

        # 라우팅 실행
        if method == "basic":
            result = router.route_all(max_iterations=cfg.max_iterations)
        elif method == "negotiated":
            result = router.route_all_negotiated(max_iterations=cfg.max_iterations)
        elif method == "adaptive":
            try:
                from kicad_tools.router.adaptive import AdaptiveAutorouter

                adaptive = AdaptiveAutorouter(
                    width=pcb.width,
                    height=pcb.height,
                    rules=rules,
                )
                # 컴포넌트 다시 등록
                for fp in pcb.footprints:
                    pads = [
                        {
                            "number": p.number,
                            "x": p.position[0],
                            "y": p.position[1],
                            "net_name": p.net_name,
                        }
                        for p in fp.pads
                    ]
                    adaptive.add_component(fp.reference, pads)
                result = adaptive.route_all_adaptive(
                    target_success=0.95,
                    max_iterations=cfg.max_iterations * 2,
                )
            except ImportError:
                logger.info("AdaptiveAutorouter 미사용. 기본 라우터로 fallback")
                result = router.route_all(max_iterations=cfg.max_iterations)
        elif method == "parallel":
            result = router.route_all_parallel()
        else:
            result = router.route_all(max_iterations=cfg.max_iterations)

        duration = time.time() - start_time

        # 결과 저장
        out_path = pcb_path.replace(".kicad_pcb", f"_routed.kicad_pcb")
        pcb.save(out_path)

        routing_result = RoutingResult(
            total_nets=result.total_nets,
            routed_nets=result.routed_nets,
            failed_nets=[f.net_name for f in result.failed_nets] if hasattr(result, "failed_nets") else [],
            success_rate=result.success_rate if hasattr(result, "success_rate") else 0.0,
            via_count=len([r for r in result.routes if hasattr(r, "via")]) if hasattr(result, "routes") else 0,
            duration_seconds=duration,
            output_path=out_path,
        )

        logger.info(
            f"라우팅 완료: {routing_result.routed_nets}/{routing_result.total_nets} 넷, "
            f"{duration:.1f}초"
        )
        return routing_result
