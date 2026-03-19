"""
KiCad 9 Schematic Editor — SWIG + kicad-skip 방식

kicad-skip으로 .kicad_sch S-expression 직접 조작
KiCad 10에서 IPC로 교체 시 이 클래스만 교체

참조: mixelpixx의 wire_manager.py, pin_locator.py, component_schematic.py
"""

from __future__ import annotations

import math
import uuid
from pathlib import Path
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
    Position,
    SymbolInfo,
    TrackInfo,
    ViaInfo,
    WireInfo,
    ZoneInfo,
)


class SWIGSchematicAdapter(AbstractKiCadAdapter):
    """
    KiCad 9 Schematic Editor — kicad-skip 기반

    .kicad_sch 파일을 직접 파싱/수정하여 심볼 배치, 와이어 연결,
    넷 라벨 추가 등을 수행.

    S-expression 직접 주입으로 kicad-skip API 한계를 우회
    (mixelpixx wire_manager.py 패턴 참조)
    """

    def __init__(self, schematic_path: str = ""):
        self._sch_path = schematic_path
        self._sch = None
        self._loaded = False

        if schematic_path:
            self._load_schematic(schematic_path)

    def _load_schematic(self, path: str):
        """kicad-skip으로 스키매틱 로드"""
        try:
            from skip import Schematic

            self._sch = Schematic(path)
            self._sch_path = path
            self._loaded = True
            logger.info(f"스키매틱 로드: {path}")
        except ImportError:
            logger.error("kicad-skip 미설치. pip install kicad-skip")
            self._loaded = False
        except Exception as e:
            logger.error(f"스키매틱 로드 실패: {e}")
            self._loaded = False

    # ─── PCB 조작 (미지원 — IPCAdapter 사용) ──────────────

    def get_board_info(self) -> BoardInfo:
        raise NotImplementedError("PCB 조작은 IPCAdapter를 사용하세요")

    def get_all_footprints(self) -> list[FootprintInfo]:
        raise NotImplementedError("PCB 조작은 IPCAdapter를 사용하세요")

    def get_footprint(self, reference: str) -> Optional[FootprintInfo]:
        raise NotImplementedError("PCB 조작은 IPCAdapter를 사용하세요")

    def place_footprint(self, reference, footprint_lib, pos, rotation=0.0, layer="F.Cu", value=""):
        raise NotImplementedError("PCB 조작은 IPCAdapter를 사용하세요")

    def move_footprint(self, reference, pos, rotation=0.0):
        raise NotImplementedError("PCB 조작은 IPCAdapter를 사용하세요")

    def delete_footprint(self, reference):
        raise NotImplementedError("PCB 조작은 IPCAdapter를 사용하세요")

    def add_track(self, start, end, width_mm, layer, net=""):
        raise NotImplementedError("PCB 조작은 IPCAdapter를 사용하세요")

    def add_via(self, pos, diameter_mm=0.8, drill_mm=0.4, net="", from_layer="F.Cu", to_layer="B.Cu"):
        raise NotImplementedError("PCB 조작은 IPCAdapter를 사용하세요")

    def add_zone(self, zone):
        raise NotImplementedError("PCB 조작은 IPCAdapter를 사용하세요")

    def get_all_nets(self) -> list[NetInfo]:
        raise NotImplementedError("PCB 조작은 IPCAdapter를 사용하세요")

    def run_drc(self) -> list[DRCViolation]:
        raise NotImplementedError("DRC는 CLIAdapter를 사용하세요")

    def refresh_view(self) -> None:
        pass  # 파일 기반이므로 UI 갱신 불필요

    # ─── Schematic 조작 ───────────────────────────────────

    def get_all_symbols(self) -> list[SymbolInfo]:
        """스키매틱의 모든 심볼 정보 반환"""
        self._ensure_loaded()
        symbols = []

        for sym in self._sch.symbol_instances:
            # kicad-skip 심볼 인스턴스에서 정보 추출
            ref = getattr(sym, "reference", "?")
            value = getattr(sym, "value", "")
            lib_id = getattr(sym, "lib_id", "")
            pos = getattr(sym, "at", [0, 0, 0])

            x = float(pos[0]) if len(pos) > 0 else 0.0
            y = float(pos[1]) if len(pos) > 1 else 0.0
            rot = float(pos[2]) if len(pos) > 2 else 0.0

            # _TEMPLATE_ 접두사 심볼은 제외 (mixelpixx 패턴)
            if ref.startswith("_TEMPLATE_"):
                continue

            symbols.append(
                SymbolInfo(
                    reference=ref,
                    value=value,
                    library_id=lib_id,
                    position=Position(x, y),
                    rotation=rot,
                )
            )
        return symbols

    def place_symbol(
        self,
        lib: str,
        symbol: str,
        pos: Position,
        reference: str = "",
        value: str = "",
        rotation: float = 0.0,
    ) -> SymbolInfo:
        """
        심볼 배치 — S-expression 직접 주입

        kicad-skip은 새 심볼 생성 API가 제한적이므로
        S-expression을 직접 주입하는 방식 사용
        (mixelpixx dynamic_symbol_loader.py 패턴)
        """
        self._ensure_loaded()

        lib_id = f"{lib}:{symbol}"
        ref = reference or f"U{self._next_ref_number(symbol)}"
        val = value or symbol
        sym_uuid = str(uuid.uuid4())

        # S-expression 블록 생성
        sexp_block = self._create_symbol_sexp(
            lib_id=lib_id,
            reference=ref,
            value=val,
            x=pos.x_mm,
            y=pos.y_mm,
            rotation=rotation,
            sym_uuid=sym_uuid,
        )

        # .kicad_sch 파일에 직접 주입
        self._inject_sexp_before_closing(sexp_block)

        # 재로드
        self._load_schematic(self._sch_path)

        logger.info(f"심볼 배치: {ref} ({lib_id}) at ({pos.x_mm}, {pos.y_mm})")
        return SymbolInfo(
            reference=ref,
            value=val,
            library_id=lib_id,
            position=pos,
            rotation=rotation,
        )

    def add_wire(self, start: Position, end: Position) -> WireInfo:
        """
        와이어 추가 — S-expression 직접 주입

        kicad-skip은 와이어 생성 불가 → raw sexpdata 조작
        (mixelpixx wire_manager.py 패턴)
        """
        self._ensure_loaded()

        wire_uuid = str(uuid.uuid4())
        wire_sexp = (
            f'  (wire (pts (xy {start.x_mm} {start.y_mm}) (xy {end.x_mm} {end.y_mm}))\n'
            f'    (stroke (width 0) (type default))\n'
            f'    (uuid "{wire_uuid}")\n'
            f'  )\n'
        )

        self._inject_sexp_before_closing(wire_sexp)
        logger.debug(f"와이어 추가: ({start.x_mm},{start.y_mm}) → ({end.x_mm},{end.y_mm})")
        return WireInfo(start=start, end=end)

    def add_polyline_wire(self, points: list[Position]) -> list[WireInfo]:
        """
        다중 세그먼트 와이어 (직교 라우팅용)

        points: [시작점, 중간점들..., 끝점]
        연속된 점 쌍으로 와이어 세그먼트 생성
        """
        wires = []
        for i in range(len(points) - 1):
            wire = self.add_wire(points[i], points[i + 1])
            wires.append(wire)
        return wires

    def add_label(
        self,
        text: str,
        pos: Position,
        label_type: str = "local",
        orientation: float = 0.0,
    ) -> LabelInfo:
        """넷 라벨 추가"""
        self._ensure_loaded()

        label_uuid = str(uuid.uuid4())

        if label_type == "global":
            tag = "global_label"
            shape = '(shape input)'
        elif label_type == "power":
            tag = "power_port"
            shape = ""
        elif label_type == "hierarchical":
            tag = "hierarchical_label"
            shape = '(shape input)'
        else:
            tag = "label"
            shape = ""

        label_sexp = (
            f'  ({tag} "{text}" (at {pos.x_mm} {pos.y_mm} {orientation}) {shape}\n'
            f'    (effects (font (size 1.27 1.27)))\n'
            f'    (uuid "{label_uuid}")\n'
            f'  )\n'
        )

        self._inject_sexp_before_closing(label_sexp)
        logger.debug(f"라벨 추가: {text} ({label_type}) at ({pos.x_mm},{pos.y_mm})")
        return LabelInfo(
            text=text, position=pos, label_type=label_type, orientation=orientation
        )

    def add_sheet(
        self,
        sheet_name: str,
        sheet_file: str,
        pos: Position,
        size: tuple[float, float] = (40.0, 30.0),
        pins: list[dict] | None = None,
    ) -> dict:
        """
        계층 시트 추가 — S-expression 직접 주입

        pins: [{"name": "VCC", "direction": "input", "x": 130, "y": 45, "rotation": 180}, ...]
        """
        self._ensure_loaded()

        sheet_uuid = str(uuid.uuid4())
        pin_lines = ""
        for pin in (pins or []):
            pin_uuid = str(uuid.uuid4())
            pin_lines += (
                f'    (pin "{pin["name"]}" {pin.get("direction", "input")}\n'
                f'      (at {pin["x"]} {pin["y"]} {pin.get("rotation", 180)})\n'
                f'      (effects (font (size 1.27 1.27)) (justify left))\n'
                f'      (uuid "{pin_uuid}")\n'
                f'    )\n'
            )

        sheet_sexp = (
            f'  (sheet\n'
            f'    (at {pos.x_mm} {pos.y_mm}) (size {size[0]} {size[1]})\n'
            f'    (stroke (width 0.1524) (type solid))\n'
            f'    (fill (color 255 255 194 1.0))\n'
            f'    (uuid "{sheet_uuid}")\n'
            f'    (property "Sheetname" "{sheet_name}"\n'
            f'      (at {pos.x_mm} {pos.y_mm - 1} 0)\n'
            f'      (effects (font (size 1.27 1.27)) (justify left bottom))\n'
            f'    )\n'
            f'    (property "Sheetfile" "{sheet_file}"\n'
            f'      (at {pos.x_mm} {pos.y_mm + size[1] + 1} 0)\n'
            f'      (effects (font (size 1.27 1.27)) (justify left top) hide)\n'
            f'    )\n'
            f'{pin_lines}'
            f'  )\n'
        )

        self._inject_sexp_before_closing(sheet_sexp)

        # 서브시트 파일이 없으면 빈 스키매틱 생성
        sub_path = Path(self._sch_path).parent / sheet_file
        if not sub_path.exists():
            self._create_empty_subsheet(sub_path, pins or [])

        logger.info(f"시트 추가: {sheet_name} → {sheet_file}")
        return {"name": sheet_name, "file": sheet_file, "uuid": sheet_uuid}

    @staticmethod
    def _create_empty_subsheet(path: Path, pins: list[dict]):
        """빈 서브시트 생성 (hierarchical_label 자동 삽입)"""
        sub_uuid = str(uuid.uuid4())
        label_lines = ""
        y_offset = 40.0
        for pin in pins:
            label_uuid = str(uuid.uuid4())
            label_lines += (
                f'  (hierarchical_label "{pin["name"]}" (shape {pin.get("direction", "input")})\n'
                f'    (at 50 {y_offset} 180)\n'
                f'    (effects (font (size 1.27 1.27)) (justify right))\n'
                f'    (uuid "{label_uuid}")\n'
                f'  )\n'
            )
            y_offset += 10.0

        content = (
            f'(kicad_sch (version 20231120) (generator "kicad-hwdesign") (generator_version "9.0")\n'
            f'  (uuid "{sub_uuid}")\n'
            f'  (paper "A4")\n'
            f'  (lib_symbols\n'
            f'  )\n'
            f'{label_lines}'
            f')\n'
        )
        path.write_text(content, encoding="utf-8")

    def get_netlist(self) -> dict:
        """kicad-skip에서 넷 정보 추출"""
        self._ensure_loaded()
        nets: dict[str, list[str]] = {}

        for sym in self._sch.symbol_instances:
            ref = getattr(sym, "reference", "")
            for pin in getattr(sym, "pins", []):
                net = getattr(pin, "net", "")
                if net:
                    nets.setdefault(net, []).append(f"{ref}.{pin.number}")

        return {"nets": nets, "count": len(nets)}

    def run_erc(self) -> list[ERCViolation]:
        """ERC는 CLIAdapter를 사용하세요"""
        logger.warning("ERC는 CLIAdapter를 사용하세요 (kicad-cli)")
        return []

    # ─── 공통 ─────────────────────────────────────────────

    def save(self) -> None:
        if self._loaded and self._sch:
            self._sch.save()
            logger.info(f"스키매틱 저장: {self._sch_path}")

    def close(self) -> None:
        self._sch = None
        self._loaded = False

    # ─── 내부 헬퍼 ────────────────────────────────────────

    def _ensure_loaded(self):
        if not self._loaded:
            raise RuntimeError("스키매틱이 로드되지 않음. 먼저 load_schematic()을 호출하세요.")

    def _next_ref_number(self, symbol: str) -> int:
        """다음 참조 번호 계산"""
        existing = [s.reference for s in self.get_all_symbols()]
        prefix = symbol[0].upper() if symbol else "U"
        max_num = 0
        for ref in existing:
            if ref.startswith(prefix):
                try:
                    num = int(ref[len(prefix):])
                    max_num = max(max_num, num)
                except ValueError:
                    pass
        return max_num + 1

    def _create_symbol_sexp(
        self,
        lib_id: str,
        reference: str,
        value: str,
        x: float,
        y: float,
        rotation: float,
        sym_uuid: str,
    ) -> str:
        """심볼 인스턴스 S-expression 생성"""
        return (
            f'  (symbol (lib_id "{lib_id}") (at {x} {y} {rotation}) '
            f'(unit 1)\n'
            f'    (in_bom yes) (on_board yes) (dnp no)\n'
            f'    (uuid "{sym_uuid}")\n'
            f'    (property "Reference" "{reference}" (at {x} {y - 2.54} 0)\n'
            f'      (effects (font (size 1.27 1.27)))\n'
            f'    )\n'
            f'    (property "Value" "{value}" (at {x} {y + 2.54} 0)\n'
            f'      (effects (font (size 1.27 1.27)))\n'
            f'    )\n'
            f'  )\n'
        )

    def _inject_sexp_before_closing(self, sexp_block: str):
        """
        .kicad_sch 파일의 닫는 괄호 직전에 S-expression 블록 삽입

        kicad-skip API 한계 우회: raw 파일 조작
        """
        path = Path(self._sch_path)
        content = path.read_text(encoding="utf-8")

        # 마지막 닫는 괄호 ')\n' 직전에 삽입
        last_paren = content.rfind(")")
        if last_paren == -1:
            raise ValueError("유효하지 않은 .kicad_sch 파일")

        new_content = content[:last_paren] + "\n" + sexp_block + content[last_paren:]
        path.write_text(new_content, encoding="utf-8")

    @staticmethod
    def transform_pin_position(
        pin_x: float,
        pin_y: float,
        component_x: float,
        component_y: float,
        rotation: float,
    ) -> Position:
        """
        핀 좌표를 컴포넌트 회전 적용하여 절대 좌표로 변환
        (mixelpixx pin_locator.py 패턴)
        """
        angle_rad = math.radians(rotation)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # 회전 행렬 적용
        rotated_x = pin_x * cos_a - pin_y * sin_a
        rotated_y = pin_x * sin_a + pin_y * cos_a

        return Position(
            x_mm=component_x + rotated_x,
            y_mm=component_y + rotated_y,
        )
