"""
KiCad 9+ IPC API Adapter — PCB Editor 전용

kicad-python (kipy/kiapi) 패키지를 사용하여
실행 중인 KiCad와 실시간 양방향 통신
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

from .base import (
    AbstractKiCadAdapter,
    BoardInfo,
    DRCViolation,
    ERCViolation,
    FootprintInfo,
    LabelInfo,
    NetInfo,
    PadInfo,
    Position,
    SymbolInfo,
    TrackInfo,
    ViaInfo,
    WireInfo,
    ZoneInfo,
)


class IPCAdapter(AbstractKiCadAdapter):
    """
    KiCad 9+ IPC API 구현 — PCB Editor 전용

    변경 사항이 즉시 KiCad UI에 반영됨 (실시간 동기화)
    KiCad 10에서 Schematic IPC도 지원 예정
    """

    def __init__(self, board_path: str = ""):
        self._board_path = board_path
        self._client = None
        self._board = None
        self._connected = False
        self._connect()

    def _connect(self):
        """IPC API 연결"""
        try:
            import kipy

            self._client = kipy.KiCad()
            if self._board_path:
                self._board = self._client.board
            else:
                self._board = self._client.board
            self._connected = True
            logger.info("KiCad IPC API 연결 성공")
        except ImportError:
            logger.warning("kicad-python 패키지 미설치. pip install kicad-python")
            self._connected = False
        except Exception as e:
            logger.warning(f"KiCad IPC 연결 실패 (KiCad가 실행 중인지 확인): {e}")
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ─── PCB 조작 ─────────────────────────────────────────

    def get_board_info(self) -> BoardInfo:
        self._ensure_connected()
        board = self._board
        footprints = board.get_footprints()
        nets = board.get_nets()
        tracks = board.get_tracks()

        # 보드 크기 계산
        bbox = board.get_bounding_box()
        width = (bbox.end.x - bbox.start.x) / 1e6  # nm → mm
        height = (bbox.end.y - bbox.start.y) / 1e6

        return BoardInfo(
            width_mm=width,
            height_mm=height,
            layer_count=board.get_layer_count(),
            footprint_count=len(footprints),
            net_count=len(nets),
            track_count=len([t for t in tracks if hasattr(t, "start")]),
            via_count=len([t for t in tracks if hasattr(t, "drill")]),
            zone_count=len(board.get_zones()),
            file_path=self._board_path,
        )

    def get_all_footprints(self) -> list[FootprintInfo]:
        self._ensure_connected()
        result = []
        for fp in self._board.get_footprints():
            pos = fp.position
            pads = []
            for pad in fp.pads:
                pads.append(
                    PadInfo(
                        number=str(pad.number),
                        position=Position(pad.position.x / 1e6, pad.position.y / 1e6),
                        size_x_mm=pad.size.x / 1e6,
                        size_y_mm=pad.size.y / 1e6,
                        net_name=getattr(pad, "net_name", ""),
                    )
                )
            result.append(
                FootprintInfo(
                    reference=fp.reference,
                    value=fp.value,
                    footprint_lib=fp.footprint_name,
                    position=Position(pos.x / 1e6, pos.y / 1e6),
                    rotation=fp.orientation / 10.0,
                    layer=fp.layer,
                    pads=pads,
                )
            )
        return result

    def get_footprint(self, reference: str) -> Optional[FootprintInfo]:
        for fp in self.get_all_footprints():
            if fp.reference == reference:
                return fp
        return None

    def place_footprint(
        self,
        reference: str,
        footprint_lib: str,
        pos: Position,
        rotation: float = 0.0,
        layer: str = "F.Cu",
        value: str = "",
    ) -> FootprintInfo:
        self._ensure_connected()
        fp = self._board.create_footprint(footprint_lib)
        fp.reference = reference
        fp.value = value or reference
        fp.position = (int(pos.x_mm * 1e6), int(pos.y_mm * 1e6))
        fp.orientation = int(rotation * 10)
        fp.layer = layer
        self._board.commit()
        logger.info(f"풋프린트 배치: {reference} ({footprint_lib}) at ({pos.x_mm}, {pos.y_mm})")
        return FootprintInfo(
            reference=reference,
            value=value,
            footprint_lib=footprint_lib,
            position=pos,
            rotation=rotation,
            layer=layer,
        )

    def move_footprint(self, reference: str, pos: Position, rotation: float = 0.0) -> None:
        self._ensure_connected()
        fp = self._board.get_footprint(reference)
        if fp is None:
            raise ValueError(f"풋프린트 '{reference}' 를 찾을 수 없음")
        fp.position = (int(pos.x_mm * 1e6), int(pos.y_mm * 1e6))
        if rotation != 0.0:
            fp.orientation = int(rotation * 10)
        self._board.commit()
        logger.info(f"풋프린트 이동: {reference} → ({pos.x_mm}, {pos.y_mm})")

    def delete_footprint(self, reference: str) -> None:
        self._ensure_connected()
        fp = self._board.get_footprint(reference)
        if fp:
            self._board.remove(fp)
            self._board.commit()
            logger.info(f"풋프린트 삭제: {reference}")

    def add_track(
        self,
        start: Position,
        end: Position,
        width_mm: float,
        layer: str,
        net: str = "",
    ) -> TrackInfo:
        self._ensure_connected()
        track = self._board.create_track()
        track.start = (int(start.x_mm * 1e6), int(start.y_mm * 1e6))
        track.end = (int(end.x_mm * 1e6), int(end.y_mm * 1e6))
        track.width = int(width_mm * 1e6)
        track.layer = layer
        if net:
            track.net_name = net
        self._board.commit()
        return TrackInfo(
            start=start, end=end, width_mm=width_mm, layer=layer, net_name=net
        )

    def add_via(
        self,
        pos: Position,
        diameter_mm: float = 0.8,
        drill_mm: float = 0.4,
        net: str = "",
        from_layer: str = "F.Cu",
        to_layer: str = "B.Cu",
    ) -> ViaInfo:
        self._ensure_connected()
        via = self._board.create_via()
        via.position = (int(pos.x_mm * 1e6), int(pos.y_mm * 1e6))
        via.diameter = int(diameter_mm * 1e6)
        via.drill = int(drill_mm * 1e6)
        via.layers = (from_layer, to_layer)
        if net:
            via.net_name = net
        self._board.commit()
        return ViaInfo(
            position=pos,
            diameter_mm=diameter_mm,
            drill_mm=drill_mm,
            net_name=net,
            from_layer=from_layer,
            to_layer=to_layer,
        )

    def add_zone(self, zone: ZoneInfo) -> None:
        self._ensure_connected()
        z = self._board.create_zone()
        z.net_name = zone.net_name
        z.layer = zone.layer
        z.clearance = int(zone.clearance_mm * 1e6)
        for pt in zone.outline:
            z.add_outline_point((int(pt.x_mm * 1e6), int(pt.y_mm * 1e6)))
        self._board.commit()

    def get_all_nets(self) -> list[NetInfo]:
        self._ensure_connected()
        nets = []
        for net in self._board.get_nets():
            nets.append(
                NetInfo(
                    name=net.name,
                    number=net.number,
                )
            )
        return nets

    def run_drc(self) -> list[DRCViolation]:
        # IPC에서 직접 DRC 실행 불가 → CLIAdapter로 위임
        logger.warning("IPC에서 DRC는 CLIAdapter를 사용하세요")
        return []

    def refresh_view(self) -> None:
        if self._connected and self._board:
            self._board.commit()
            logger.debug("KiCad UI 갱신 완료")

    # ─── Schematic 조작 (KiCad 10에서 구현 예정) ────────

    def get_all_symbols(self) -> list[SymbolInfo]:
        raise NotImplementedError("Schematic IPC는 KiCad 10+에서 지원 예정. SWIGSchematicAdapter를 사용하세요.")

    def place_symbol(self, lib, symbol, pos, reference="", value="", rotation=0.0) -> SymbolInfo:
        raise NotImplementedError("Schematic IPC는 KiCad 10+에서 지원 예정")

    def add_wire(self, start, end) -> WireInfo:
        raise NotImplementedError("Schematic IPC는 KiCad 10+에서 지원 예정")

    def add_label(self, text, pos, label_type="local", orientation=0.0) -> LabelInfo:
        raise NotImplementedError("Schematic IPC는 KiCad 10+에서 지원 예정")

    def get_netlist(self) -> dict:
        raise NotImplementedError("Schematic IPC는 KiCad 10+에서 지원 예정")

    def run_erc(self) -> list[ERCViolation]:
        raise NotImplementedError("ERC는 CLIAdapter를 사용하세요")

    # ─── 공통 ─────────────────────────────────────────────

    def save(self) -> None:
        if self._connected and self._board:
            self._board.save()
            logger.info("보드 저장 완료")

    def close(self) -> None:
        self._connected = False
        self._board = None
        self._client = None
        logger.info("IPC 연결 종료")

    def _ensure_connected(self):
        if not self._connected:
            raise ConnectionError(
                "KiCad IPC 연결되지 않음. KiCad가 실행 중인지, kicad-python이 설치되어 있는지 확인하세요."
            )
