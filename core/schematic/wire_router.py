"""
Schematic Wire Router

스키매틱 내 심볼 간 와이어 자동 연결
직교(orthogonal) 라우팅 지원

참조: mixelpixx connection_schematic.py, wire_manager.py
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from loguru import logger

from ..kicad_adapter.base import Position, WireInfo
from ..kicad_adapter.swig_adapter import SWIGSchematicAdapter


class RoutingMode(str, Enum):
    """와이어 라우팅 모드"""
    DIRECT = "direct"                    # 직선 연결
    ORTHOGONAL_H = "orthogonal_h"        # 수평 우선 직교
    ORTHOGONAL_V = "orthogonal_v"        # 수직 우선 직교


@dataclass
class PinLocation:
    """핀의 절대 좌표"""
    reference: str
    pin: str
    position: Position


class WireRouter:
    """
    스키매틱 와이어 라우팅 엔진

    기능:
    1. 핀-to-핀 직접 연결
    2. 직교(orthogonal) 라우팅
    3. 넷 라벨을 통한 암시적 연결
    4. 전원 넷 자동 연결
    """

    def __init__(self, adapter: SWIGSchematicAdapter):
        self.adapter = adapter

    def connect_pins(
        self,
        from_ref: str,
        from_pin: str,
        to_ref: str,
        to_pin: str,
        mode: RoutingMode = RoutingMode.ORTHOGONAL_H,
    ) -> list[WireInfo]:
        """
        두 핀을 와이어로 연결

        Args:
            from_ref: 시작 컴포넌트 참조 (예: "U1")
            from_pin: 시작 핀 (예: "1" 또는 "VCC")
            to_ref: 끝 컴포넌트 참조
            to_pin: 끝 핀
            mode: 라우팅 모드

        Returns:
            생성된 와이어 세그먼트 목록
        """
        # 핀 위치 찾기
        from_pos = self._find_pin_position(from_ref, from_pin)
        to_pos = self._find_pin_position(to_ref, to_pin)

        if from_pos is None:
            logger.warning(f"핀을 찾을 수 없음: {from_ref}.{from_pin}")
            return []
        if to_pos is None:
            logger.warning(f"핀을 찾을 수 없음: {to_ref}.{to_pin}")
            return []

        # 라우팅 경로 계산
        path = self._calculate_path(from_pos, to_pos, mode)

        # 와이어 생성
        wires = self.adapter.add_polyline_wire(path)
        logger.info(
            f"와이어 연결: {from_ref}.{from_pin} → {to_ref}.{to_pin} "
            f"({len(wires)} 세그먼트, {mode.value})"
        )
        return wires

    def connect_to_net(
        self,
        ref: str,
        pin: str,
        net_name: str,
        label_type: str = "global",
        wire_length: float = 5.0,
    ) -> Optional[WireInfo]:
        """
        핀을 넷 라벨로 연결 (전원 넷 등)

        예: connect_to_net("U1", "VDD", "VCC", "power")
        """
        pin_pos = self._find_pin_position(ref, pin)
        if pin_pos is None:
            logger.warning(f"핀을 찾을 수 없음: {ref}.{pin}")
            return None

        # 라벨 위치 (핀에서 약간 떨어진 곳)
        label_pos = Position(pin_pos.x_mm + wire_length, pin_pos.y_mm)

        # 와이어 + 라벨 추가
        wire = self.adapter.add_wire(pin_pos, label_pos)
        self.adapter.add_label(
            text=net_name,
            pos=label_pos,
            label_type=label_type,
        )

        logger.info(f"넷 라벨 연결: {ref}.{pin} → {net_name}")
        return wire

    def auto_connect(
        self,
        connections: list[dict],
        mode: RoutingMode = RoutingMode.ORTHOGONAL_H,
    ) -> int:
        """
        여러 연결을 일괄 처리

        Args:
            connections: [{"from": "U1.VCC", "to": "PWR.+3.3V"}, ...]
            mode: 기본 라우팅 모드

        Returns:
            성공적으로 연결된 수
        """
        success_count = 0
        for conn in connections:
            try:
                from_parts = conn["from"].split(".")
                to_parts = conn["to"].split(".")

                if len(from_parts) != 2 or len(to_parts) != 2:
                    logger.warning(f"잘못된 연결 형식: {conn}")
                    continue

                from_ref, from_pin = from_parts
                to_ref, to_pin = to_parts

                # PWR 접두사는 넷 라벨 연결
                if to_ref.upper() == "PWR" or from_ref.upper() == "PWR":
                    net_name = to_pin if to_ref.upper() == "PWR" else from_pin
                    target_ref = from_ref if to_ref.upper() == "PWR" else to_ref
                    target_pin = from_pin if to_ref.upper() == "PWR" else to_pin
                    self.connect_to_net(target_ref, target_pin, net_name)
                else:
                    self.connect_pins(from_ref, from_pin, to_ref, to_pin, mode)

                success_count += 1
            except Exception as e:
                logger.error(f"연결 실패 {conn}: {e}")

        logger.info(f"자동 연결 완료: {success_count}/{len(connections)}")
        return success_count

    def _find_pin_position(self, reference: str, pin: str) -> Optional[Position]:
        """
        심볼의 특정 핀 절대 좌표 계산

        1. 심볼 인스턴스에서 위치/회전 정보 획득
        2. 라이브러리 심볼 정의에서 핀 상대 좌표 추출
        3. 회전 변환 적용하여 절대 좌표 반환
        """
        symbols = self.adapter.get_all_symbols()

        for sym in symbols:
            if sym.reference == reference:
                # 핀의 상대 좌표를 추정 (심볼 정의 없이 근사)
                # 실제 구현 시 kicad-skip의 심볼 정의를 파싱해야 함
                pin_offset = self._estimate_pin_offset(sym, pin)
                if pin_offset:
                    abs_pos = SWIGSchematicAdapter.transform_pin_position(
                        pin_x=pin_offset.x_mm,
                        pin_y=pin_offset.y_mm,
                        component_x=sym.position.x_mm,
                        component_y=sym.position.y_mm,
                        rotation=sym.rotation,
                    )
                    return abs_pos

                # fallback: 심볼 중심 반환
                return sym.position

        return None

    def _estimate_pin_offset(self, symbol: SymbolInfo, pin: str) -> Optional[Position]:
        """핀 상대 좌표 추정 (심볼 정의 파싱 전 임시)"""
        # TODO: 실제 구현에서는 .kicad_sym 파일을 파싱하여 정확한 핀 좌표 반환
        # 현재는 기본 오프셋 사용
        try:
            pin_num = int(pin)
            # 2핀 부품 (저항, 커패시터 등)
            if pin_num == 1:
                return Position(-2.54, 0)
            elif pin_num == 2:
                return Position(2.54, 0)
            else:
                # 다핀 IC: 핀 번호에 따라 분포
                side = (pin_num - 1) % 4
                idx = (pin_num - 1) // 4
                offsets = [
                    Position(-5.08, -2.54 * idx),   # 왼쪽
                    Position(2.54 * idx, 5.08),      # 아래
                    Position(5.08, 2.54 * idx),      # 오른쪽
                    Position(-2.54 * idx, -5.08),    # 위
                ]
                return offsets[side]
        except ValueError:
            # 핀 이름(VCC, GND 등) → 기본 오프셋
            return Position(0, -2.54)

    @staticmethod
    def _calculate_path(
        start: Position, end: Position, mode: RoutingMode
    ) -> list[Position]:
        """
        라우팅 경로 계산

        Direct: [start, end]
        Orthogonal H-first: [start, (end.x, start.y), end]
        Orthogonal V-first: [start, (start.x, end.y), end]
        """
        if mode == RoutingMode.DIRECT:
            return [start, end]
        elif mode == RoutingMode.ORTHOGONAL_H:
            mid = Position(end.x_mm, start.y_mm)
            if abs(mid.x_mm - start.x_mm) < 0.01 or abs(mid.y_mm - end.y_mm) < 0.01:
                return [start, end]
            return [start, mid, end]
        elif mode == RoutingMode.ORTHOGONAL_V:
            mid = Position(start.x_mm, end.y_mm)
            if abs(mid.y_mm - start.y_mm) < 0.01 or abs(mid.x_mm - end.x_mm) < 0.01:
                return [start, end]
            return [start, mid, end]
        else:
            return [start, end]


# 타입 임포트 보완
from ..kicad_adapter.base import SymbolInfo  # noqa: E402
