"""
AI Placement Engine — rjwalters/kicad-tools 래핑

PlacementOptimizer, EvolutionaryPlacementOptimizer를 직접 import하여
AI 오케스트레이터와 연결
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from loguru import logger


class PlacementStrategy(str, Enum):
    """배치 최적화 전략"""
    PHYSICS = "physics"            # 물리 기반 힘-방향 (빠름)
    EVOLUTIONARY = "evolutionary"  # 유전 알고리즘 (정밀)
    HYBRID = "hybrid"              # GA → 물리 기반 (권장)
    LLM = "llm"                    # AI 추론 기반


@dataclass
class PlacementResult:
    """배치 최적화 결과"""
    output_path: str
    strategy: str
    generations: int = 0
    wire_length_mm: float = 0.0
    conflicts: int = 0
    success_rate: float = 0.0
    duration_seconds: float = 0.0
    report: str = ""


class AIPlacementEngine:
    """
    AI 기반 PCB 배치 최적화 엔진

    rjwalters의 PlacementOptimizer / EvolutionaryPlacementOptimizer를
    직접 import하여 사용

    지원 전략:
    - physics: 힘-방향 기반 (빠르지만 로컬 최적)
    - evolutionary: 유전 알고리즘 (느리지만 글로벌 최적)
    - hybrid: GA → 물리 (권장, 두 가지 장점 결합)
    - llm: AI 추론 기반 배치 제안
    """

    def __init__(self):
        self._check_dependencies()

    def _check_dependencies(self):
        """rjwalters/kicad-tools 설치 확인"""
        try:
            from kicad_tools.optim import PlacementOptimizer

            self._available = True
        except ImportError:
            logger.warning(
                "kicad-tools 미설치. pip install kicad-tools[metal] 실행 필요"
            )
            self._available = False

    def optimize(
        self,
        pcb_path: str,
        strategy: PlacementStrategy = PlacementStrategy.HYBRID,
        generations: int = 100,
        population_size: int = 50,
        fixed_refs: list[str] | None = None,
        enable_gpu: bool = True,
    ) -> PlacementResult:
        """
        PCB 배치 최적화 실행

        Args:
            pcb_path: .kicad_pcb 파일 경로
            strategy: 최적화 전략
            generations: 세대 수 (evolutionary/hybrid)
            population_size: 인구 크기 (evolutionary)
            fixed_refs: 고정할 컴포넌트 참조 목록
            enable_gpu: GPU 가속 사용 (Metal/CUDA)

        Returns:
            PlacementResult (최적화된 파일 경로 포함)
        """
        if not self._available:
            raise RuntimeError("kicad-tools가 설치되지 않음")

        import time

        from kicad_tools.schema.pcb import PCB

        start_time = time.time()

        # PCB 로드
        pcb = PCB.load(pcb_path)
        logger.info(f"PCB 로드: {pcb_path} ({len(pcb.footprints)}개 풋프린트)")

        if strategy == PlacementStrategy.PHYSICS:
            result = self._run_physics(pcb, fixed_refs, enable_gpu)
        elif strategy == PlacementStrategy.EVOLUTIONARY:
            result = self._run_evolutionary(
                pcb, generations, population_size, enable_gpu
            )
        elif strategy == PlacementStrategy.HYBRID:
            result = self._run_hybrid(pcb, generations, fixed_refs, enable_gpu)
        elif strategy == PlacementStrategy.LLM:
            result = self._run_llm_placement(pcb)
        else:
            raise ValueError(f"알 수 없는 전략: {strategy}")

        # 최적화 결과 저장
        out_path = pcb_path.replace(".kicad_pcb", f"_optimized_{strategy.value}.kicad_pcb")
        pcb.save(out_path)

        duration = time.time() - start_time
        result.output_path = out_path
        result.strategy = strategy.value
        result.duration_seconds = duration

        logger.info(
            f"배치 최적화 완료: {strategy.value}, "
            f"{duration:.1f}초, 와이어 길이 {result.wire_length_mm:.1f}mm"
        )
        return result

    def _run_physics(
        self,
        pcb,
        fixed_refs: list[str] | None,
        enable_gpu: bool,
    ) -> PlacementResult:
        """물리 기반 배치 최적화"""
        from kicad_tools.optim import PlacementOptimizer

        opt = PlacementOptimizer.from_pcb(pcb, fixed_refs=fixed_refs)

        if enable_gpu:
            try:
                opt.enable_gpu()
            except Exception:
                logger.debug("GPU 가속 불가, CPU 사용")

        opt.create_springs_from_nets()
        # PlacementOptimizer는 step 기반 → 수동 반복
        for _ in range(200):
            opt.step()

        opt.write_to_pcb(pcb)
        report = opt.report() if hasattr(opt, "report") else ""

        return PlacementResult(
            output_path="",
            strategy="physics",
            report=report,
        )

    def _run_evolutionary(
        self,
        pcb,
        generations: int,
        population_size: int,
        enable_gpu: bool,
    ) -> PlacementResult:
        """유전 알고리즘 배치 최적화"""
        from kicad_tools.optim.evolutionary import (
            EvolutionaryConfig,
            EvolutionaryPlacementOptimizer,
        )

        config = EvolutionaryConfig(
            population_size=population_size,
            generations=generations,
            use_gpu=enable_gpu,
        )

        evo = EvolutionaryPlacementOptimizer.from_pcb(pcb, config=config)
        best = evo.optimize(generations=generations)
        evo.write_to_pcb(pcb)

        report = evo.report() if hasattr(evo, "report") else ""

        return PlacementResult(
            output_path="",
            strategy="evolutionary",
            generations=generations,
            report=report,
        )

    def _run_hybrid(
        self,
        pcb,
        generations: int,
        fixed_refs: list[str] | None,
        enable_gpu: bool,
    ) -> PlacementResult:
        """하이브리드 최적화 (GA → 물리)"""
        from kicad_tools.optim.evolutionary import (
            EvolutionaryConfig,
            EvolutionaryPlacementOptimizer,
        )

        config = EvolutionaryConfig(
            generations=generations,
            use_gpu=enable_gpu,
        )

        evo = EvolutionaryPlacementOptimizer.from_pcb(pcb, config=config)
        opt = evo.optimize_hybrid(generations=generations)
        opt.write_to_pcb(pcb)

        report = opt.report() if hasattr(opt, "report") else ""

        return PlacementResult(
            output_path="",
            strategy="hybrid",
            generations=generations,
            report=report,
        )

    def _run_llm_placement(self, pcb) -> PlacementResult:
        """AI 추론 기반 배치 제안 (향후 구현)"""
        logger.warning("LLM 배치 전략은 향후 구현 예정. hybrid로 fallback")
        return PlacementResult(
            output_path="",
            strategy="llm",
            report="LLM 배치 전략은 아직 구현되지 않았습니다.",
        )
