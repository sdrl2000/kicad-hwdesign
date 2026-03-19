"""
KiCad API Adapter Layer

사용법:
    adapter = create_adapter(board_path="project.kicad_pcb")
    # 또는
    sch_adapter = create_schematic_adapter("project.kicad_sch")
    cli = create_cli_adapter(board_path="project.kicad_pcb")
"""

from .base import (
    AbstractKiCadAdapter,
    BoardInfo,
    DRCViolation,
    ERCViolation,
    FootprintInfo,
    LabelInfo,
    Layer,
    NetInfo,
    PadInfo,
    Position,
    SymbolInfo,
    TrackInfo,
    ViaInfo,
    WireInfo,
    ZoneInfo,
)
from .cli_adapter import CLIAdapter
from .ipc_adapter import IPCAdapter
from .swig_adapter import SWIGSchematicAdapter

from loguru import logger


def create_adapter(board_path: str = "", prefer_ipc: bool = True) -> AbstractKiCadAdapter:
    """
    PCB Adapter 자동 생성

    우선순위:
    1. IPC (kicad-python 설치 + KiCad 실행 중)
    2. 실패 시 에러

    Args:
        board_path: .kicad_pcb 파일 경로
        prefer_ipc: IPC 우선 사용 (기본값: True)
    """
    if prefer_ipc:
        try:
            adapter = IPCAdapter(board_path)
            if adapter.is_connected:
                logger.info("IPC Adapter 생성 성공")
                return adapter
        except Exception as e:
            logger.warning(f"IPC Adapter 생성 실패: {e}")

    raise RuntimeError(
        "PCB Adapter를 생성할 수 없음. "
        "kicad-python 설치 및 KiCad 실행 상태를 확인하세요."
    )


def create_schematic_adapter(schematic_path: str) -> SWIGSchematicAdapter:
    """Schematic Adapter 생성 (kicad-skip 기반)"""
    return SWIGSchematicAdapter(schematic_path)


def create_cli_adapter(
    board_path: str = "",
    schematic_path: str = "",
) -> CLIAdapter:
    """CLI Adapter 생성 (DRC/ERC/Export용)"""
    return CLIAdapter(board_path=board_path, schematic_path=schematic_path)


__all__ = [
    "AbstractKiCadAdapter",
    "IPCAdapter",
    "SWIGSchematicAdapter",
    "CLIAdapter",
    "create_adapter",
    "create_schematic_adapter",
    "create_cli_adapter",
    # Data models
    "Position",
    "PadInfo",
    "FootprintInfo",
    "TrackInfo",
    "ViaInfo",
    "ZoneInfo",
    "NetInfo",
    "SymbolInfo",
    "WireInfo",
    "LabelInfo",
    "BoardInfo",
    "DRCViolation",
    "ERCViolation",
    "Layer",
]
