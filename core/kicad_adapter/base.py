"""
KiCad API 추상화 레이어 — base.py

KiCad 9: IPC (PCB) + SWIG (Schematic) 이중 구현
KiCad 10+: IPC 통합 구현으로 교체 예정
인터페이스는 변경하지 않음 (Adapter 패턴)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Layer(str, Enum):
    """KiCad PCB 레이어 정의"""
    F_CU = "F.Cu"
    B_CU = "B.Cu"
    IN1_CU = "In1.Cu"
    IN2_CU = "In2.Cu"
    F_SILK = "F.SilkS"
    B_SILK = "B.SilkS"
    F_MASK = "F.Mask"
    B_MASK = "B.Mask"
    F_PASTE = "F.Paste"
    B_PASTE = "B.Paste"
    F_FAB = "F.Fab"
    B_FAB = "B.Fab"
    EDGE_CUTS = "Edge.Cuts"
    MARGIN = "Margin"
    F_COURTYARD = "F.CrtYd"
    B_COURTYARD = "B.CrtYd"


@dataclass
class Position:
    """2D 좌표 (밀리미터 단위)"""
    x_mm: float
    y_mm: float

    def __iter__(self):
        yield self.x_mm
        yield self.y_mm

    def distance_to(self, other: "Position") -> float:
        import math
        return math.sqrt((self.x_mm - other.x_mm) ** 2 + (self.y_mm - other.y_mm) ** 2)


@dataclass
class PadInfo:
    """패드 정보"""
    number: str
    position: Position
    size_x_mm: float
    size_y_mm: float
    shape: str = "roundrect"
    pad_type: str = "smd"
    layers: list[str] = field(default_factory=list)
    net_name: str = ""
    net_number: int = 0
    drill_mm: float = 0.0


@dataclass
class FootprintInfo:
    """풋프린트 정보"""
    reference: str
    value: str
    footprint_lib: str
    position: Position
    rotation: float
    layer: str
    pads: list[PadInfo] = field(default_factory=list)
    uuid: str = ""


@dataclass
class TrackInfo:
    """트레이스 정보"""
    start: Position
    end: Position
    width_mm: float
    layer: str
    net_name: str = ""
    net_number: int = 0


@dataclass
class ViaInfo:
    """비아 정보"""
    position: Position
    diameter_mm: float
    drill_mm: float
    net_name: str = ""
    net_number: int = 0
    from_layer: str = "F.Cu"
    to_layer: str = "B.Cu"


@dataclass
class ZoneInfo:
    """구리 존(copper pour) 정보"""
    net_name: str
    layer: str
    outline: list[Position]
    clearance_mm: float = 0.3
    min_thickness_mm: float = 0.25
    thermal_gap_mm: float = 0.508
    thermal_bridge_width_mm: float = 0.508


@dataclass
class NetInfo:
    """넷 정보"""
    name: str
    number: int
    node_count: int = 0
    pins: list[str] = field(default_factory=list)


@dataclass
class SymbolInfo:
    """스키매틱 심볼 정보"""
    reference: str
    value: str
    library_id: str
    position: Position
    rotation: float = 0.0
    mirror_x: bool = False
    mirror_y: bool = False
    unit: int = 1
    properties: dict = field(default_factory=dict)


@dataclass
class WireInfo:
    """스키매틱 와이어 정보"""
    start: Position
    end: Position


@dataclass
class LabelInfo:
    """스키매틱 넷 라벨 정보"""
    text: str
    position: Position
    label_type: str = "local"
    orientation: float = 0.0


@dataclass
class BoardInfo:
    """보드 전체 정보"""
    width_mm: float
    height_mm: float
    layer_count: int
    footprint_count: int
    net_count: int
    track_count: int
    via_count: int
    zone_count: int
    file_path: str = ""


@dataclass
class DRCViolation:
    """DRC 위반 항목"""
    severity: str
    violation_type: str
    description: str
    position: Optional[Position] = None
    items: list[str] = field(default_factory=list)


@dataclass
class ERCViolation:
    """ERC 위반 항목"""
    severity: str
    violation_type: str
    description: str
    components: list[str] = field(default_factory=list)


class AbstractKiCadAdapter(ABC):
    """
    KiCad API 추상화 인터페이스

    구현체:
    - IPCAdapter: KiCad 9+ IPC API (PCB Editor)
    - SWIGSchematicAdapter: KiCad 9 SWIG (Schematic Editor)
    - CLIAdapter: kicad-cli (Export, DRC, ERC)

    KiCad 10+에서는 IPCAdapter가 Schematic도 지원 예정
    """

    # ─── PCB 조작 ─────────────────────────────────────────

    @abstractmethod
    def get_board_info(self) -> BoardInfo:
        """보드 전체 정보 조회"""
        ...

    @abstractmethod
    def get_all_footprints(self) -> list[FootprintInfo]:
        """모든 풋프린트 목록 조회"""
        ...

    @abstractmethod
    def get_footprint(self, reference: str) -> Optional[FootprintInfo]:
        """특정 풋프린트 조회"""
        ...

    @abstractmethod
    def place_footprint(
        self,
        reference: str,
        footprint_lib: str,
        pos: Position,
        rotation: float = 0.0,
        layer: str = "F.Cu",
        value: str = "",
    ) -> FootprintInfo:
        """풋프린트 배치"""
        ...

    @abstractmethod
    def move_footprint(
        self, reference: str, pos: Position, rotation: float = 0.0
    ) -> None:
        """풋프린트 이동"""
        ...

    @abstractmethod
    def delete_footprint(self, reference: str) -> None:
        """풋프린트 삭제"""
        ...

    @abstractmethod
    def add_track(
        self,
        start: Position,
        end: Position,
        width_mm: float,
        layer: str,
        net: str = "",
    ) -> TrackInfo:
        """트레이스 추가"""
        ...

    @abstractmethod
    def add_via(
        self,
        pos: Position,
        diameter_mm: float = 0.8,
        drill_mm: float = 0.4,
        net: str = "",
        from_layer: str = "F.Cu",
        to_layer: str = "B.Cu",
    ) -> ViaInfo:
        """비아 추가"""
        ...

    @abstractmethod
    def add_zone(self, zone: ZoneInfo) -> None:
        """구리 존 추가"""
        ...

    @abstractmethod
    def get_all_nets(self) -> list[NetInfo]:
        """모든 넷 목록 조회"""
        ...

    @abstractmethod
    def run_drc(self) -> list[DRCViolation]:
        """DRC 실행"""
        ...

    @abstractmethod
    def refresh_view(self) -> None:
        """KiCad UI 갱신"""
        ...

    # ─── Schematic 조작 ───────────────────────────────────

    @abstractmethod
    def get_all_symbols(self) -> list[SymbolInfo]:
        """모든 심볼 목록 조회"""
        ...

    @abstractmethod
    def place_symbol(
        self,
        lib: str,
        symbol: str,
        pos: Position,
        reference: str = "",
        value: str = "",
        rotation: float = 0.0,
    ) -> SymbolInfo:
        """심볼 배치"""
        ...

    @abstractmethod
    def add_wire(self, start: Position, end: Position) -> WireInfo:
        """와이어 추가"""
        ...

    @abstractmethod
    def add_label(
        self,
        text: str,
        pos: Position,
        label_type: str = "local",
        orientation: float = 0.0,
    ) -> LabelInfo:
        """넷 라벨 추가"""
        ...

    @abstractmethod
    def get_netlist(self) -> dict:
        """넷리스트 추출"""
        ...

    @abstractmethod
    def run_erc(self) -> list[ERCViolation]:
        """ERC 실행"""
        ...

    # ─── 공통 ─────────────────────────────────────────────

    @abstractmethod
    def save(self) -> None:
        """현재 상태 저장"""
        ...

    @abstractmethod
    def close(self) -> None:
        """연결 종료"""
        ...
