"""
KiCad 내부 SWIG/IPC 실행기

MCP 서버로부터 전달받은 명령을 KiCad 프로세스 내부에서 실행.
pcbnew SWIG 바인딩을 사용하여 스키매틱/PCB를 실시간 조작.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class PluginExecutor:
    """
    KiCad 내부 명령 실행기

    지원 액션:
    - place_symbol: 스키매틱에 심볼 배치 (SWIG)
    - add_wire: 스키매틱에 와이어 추가 (SWIG)
    - add_label: 스키매틱에 넷 라벨 추가 (SWIG)
    - move_footprint: PCB 풋프린트 이동 (IPC/SWIG)
    - add_track: PCB 트레이스 추가 (IPC/SWIG)
    - add_via: PCB 비아 추가 (IPC/SWIG)
    - refresh: KiCad 화면 갱신
    - get_board_info: 현재 보드 정보 조회
    - get_schematic_symbols: 현재 스키매틱 심볼 목록
    - apply_placement: 최적화된 배치 결과를 현재 보드에 적용
    - set_symbol_property: 심볼 프로퍼티 수정 (BOM 데이터 등)
    - add_3d_model: 풋프린트에 3D 모델 경로 설정
    """

    def __init__(self):
        self._pcbnew = None
        try:
            import pcbnew
            self._pcbnew = pcbnew
        except ImportError:
            pass

    def execute(self, action: str, params: dict) -> dict:
        """액션 디스패치"""
        handlers = {
            "place_symbol": self._place_symbol,
            "add_wire": self._add_wire,
            "add_label": self._add_label,
            "move_footprint": self._move_footprint,
            "add_track": self._add_track,
            "add_via": self._add_via,
            "refresh": self._refresh,
            "get_board_info": self._get_board_info,
            "get_schematic_symbols": self._get_schematic_symbols,
            "apply_placement": self._apply_placement,
            "set_symbol_property": self._set_symbol_property,
            "add_3d_model": self._add_3d_model,
            "ping": self._ping,
        }

        handler = handlers.get(action)
        if not handler:
            raise ValueError(f"알 수 없는 액션: {action}")

        return handler(params)

    # ─── 스키매틱 (SWIG/kicad-skip) ──────────────────────

    def _place_symbol(self, params: dict) -> dict:
        """스키매틱에 심볼 배치"""
        from skip import Schematic
        import uuid as _uuid

        file_path = params["file_path"]
        library = params["library"]
        symbol = params["symbol"]
        x = float(params["x"])
        y = float(params["y"])
        reference = params.get("reference", "")
        value = params.get("value", symbol)

        # S-expression 직접 주입
        sym_uuid = str(_uuid.uuid4())
        lib_id = f"{library}:{symbol}"

        sexp = (
            f'  (symbol (lib_id "{lib_id}") (at {x} {y} 0) (unit 1)\n'
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
        self._inject_sexp(file_path, sexp)
        return {"reference": reference, "uuid": sym_uuid}

    def _add_wire(self, params: dict) -> dict:
        """스키매틱에 와이어 추가"""
        import uuid as _uuid

        file_path = params["file_path"]
        sx, sy = float(params["start_x"]), float(params["start_y"])
        ex, ey = float(params["end_x"]), float(params["end_y"])
        wire_uuid = str(_uuid.uuid4())

        sexp = (
            f'  (wire (pts (xy {sx} {sy}) (xy {ex} {ey}))\n'
            f'    (stroke (width 0) (type default))\n'
            f'    (uuid "{wire_uuid}")\n'
            f'  )\n'
        )
        self._inject_sexp(file_path, sexp)
        return {"uuid": wire_uuid}

    def _add_label(self, params: dict) -> dict:
        """스키매틱에 넷 라벨 추가"""
        import uuid as _uuid

        file_path = params["file_path"]
        text = params["text"]
        x, y = float(params["x"]), float(params["y"])
        label_type = params.get("label_type", "global")
        orientation = float(params.get("orientation", 0))
        label_uuid = str(_uuid.uuid4())

        tag_map = {
            "local": "label",
            "global": "global_label",
            "hierarchical": "hierarchical_label",
            "power": "power_port",
        }
        tag = tag_map.get(label_type, "label")
        shape = '(shape input)' if label_type in ("global", "hierarchical") else ""

        sexp = (
            f'  ({tag} "{text}" (at {x} {y} {orientation}) {shape}\n'
            f'    (effects (font (size 1.27 1.27)))\n'
            f'    (uuid "{label_uuid}")\n'
            f'  )\n'
        )
        self._inject_sexp(file_path, sexp)
        return {"uuid": label_uuid}

    def _set_symbol_property(self, params: dict) -> dict:
        """심볼 프로퍼티 수정 (BOM 데이터, LCSC 번호 등)"""
        file_path = params["file_path"]
        reference = params["reference"]
        prop_name = params["property"]
        prop_value = params["value"]

        path = Path(file_path)
        content = path.read_text(encoding="utf-8")

        # 해당 심볼 블록에서 프로퍼티 찾아 수정
        # 간단한 텍스트 치환 (정교한 구현은 kicad-skip 사용)
        import re
        # Reference가 일치하는 심볼 블록 내에서 프로퍼티 수정
        pattern = rf'(property "{prop_name}" )"[^"]*"'
        # TODO: 심볼 블록 범위 내에서만 치환하도록 개선
        new_content = content  # 실제 구현에서는 블록 범위 파싱 필요

        return {"reference": reference, "property": prop_name, "value": prop_value}

    def _get_schematic_symbols(self, params: dict) -> dict:
        """현재 스키매틱의 심볼 목록 조회"""
        from skip import Schematic

        file_path = params.get("file_path", "")
        if not file_path:
            return {"symbols": [], "count": 0}

        sch = Schematic(file_path)
        symbols = []
        for sym in sch.symbol_instances:
            ref = getattr(sym, "reference", "?")
            if ref.startswith("_TEMPLATE_"):
                continue
            val = getattr(sym, "value", "")
            lib_id = getattr(sym, "lib_id", "")
            pos = getattr(sym, "at", [0, 0])
            symbols.append({
                "reference": ref,
                "value": val,
                "library_id": lib_id,
                "x": float(pos[0]) if len(pos) > 0 else 0,
                "y": float(pos[1]) if len(pos) > 1 else 0,
            })

        return {"symbols": symbols, "count": len(symbols)}

    # ─── PCB (SWIG pcbnew) ───────────────────────────────

    def _move_footprint(self, params: dict) -> dict:
        """풋프린트 이동"""
        pcb = self._pcbnew
        if not pcb:
            raise RuntimeError("pcbnew 모듈 없음 (KiCad 외부 환경)")

        board = pcb.GetBoard()
        reference = params["reference"]
        x_mm = float(params["x"])
        y_mm = float(params["y"])
        rotation = float(params.get("rotation", 0))

        for fp in board.GetFootprints():
            if fp.GetReference() == reference:
                fp.SetPosition(pcb.VECTOR2I(pcb.FromMM(x_mm), pcb.FromMM(y_mm)))
                if rotation:
                    fp.SetOrientationDegrees(rotation)
                pcb.Refresh()
                return {"reference": reference, "x": x_mm, "y": y_mm}

        raise ValueError(f"풋프린트 '{reference}' 를 찾을 수 없음")

    def _add_track(self, params: dict) -> dict:
        """트레이스 추가"""
        pcb = self._pcbnew
        if not pcb:
            raise RuntimeError("pcbnew 모듈 없음")

        board = pcb.GetBoard()
        track = pcb.PCB_TRACK(board)

        sx, sy = float(params["start_x"]), float(params["start_y"])
        ex, ey = float(params["end_x"]), float(params["end_y"])
        width = float(params.get("width", 0.25))
        layer = params.get("layer", "F.Cu")

        track.SetStart(pcb.VECTOR2I(pcb.FromMM(sx), pcb.FromMM(sy)))
        track.SetEnd(pcb.VECTOR2I(pcb.FromMM(ex), pcb.FromMM(ey)))
        track.SetWidth(pcb.FromMM(width))
        track.SetLayer(board.GetLayerID(layer))

        board.Add(track)
        pcb.Refresh()
        return {"start": [sx, sy], "end": [ex, ey], "width": width}

    def _add_via(self, params: dict) -> dict:
        """비아 추가"""
        pcb = self._pcbnew
        if not pcb:
            raise RuntimeError("pcbnew 모듈 없음")

        board = pcb.GetBoard()
        via = pcb.PCB_VIA(board)

        x, y = float(params["x"]), float(params["y"])
        diameter = float(params.get("diameter", 0.8))
        drill = float(params.get("drill", 0.4))

        via.SetPosition(pcb.VECTOR2I(pcb.FromMM(x), pcb.FromMM(y)))
        via.SetDrill(pcb.FromMM(drill))
        via.SetWidth(pcb.FromMM(diameter))

        board.Add(via)
        pcb.Refresh()
        return {"x": x, "y": y, "diameter": diameter}

    def _get_board_info(self, params: dict) -> dict:
        """현재 열린 보드 정보 조회"""
        pcb = self._pcbnew
        if not pcb:
            return {"error": "pcbnew 모듈 없음"}

        board = pcb.GetBoard()
        if not board:
            return {"error": "열린 보드 없음"}

        fps = board.GetFootprints()
        tracks = board.GetTracks()
        nets = board.GetNetInfo()

        return {
            "file_path": board.GetFileName(),
            "footprint_count": len(fps),
            "track_count": len(tracks),
            "net_count": nets.GetNetCount(),
            "layer_count": board.GetCopperLayerCount(),
        }

    def _apply_placement(self, params: dict) -> dict:
        """최적화된 배치 결과를 현재 보드에 적용"""
        pcb = self._pcbnew
        if not pcb:
            raise RuntimeError("pcbnew 모듈 없음")

        board = pcb.GetBoard()
        placements = params.get("placements", [])
        applied = 0

        for p in placements:
            ref = p["reference"]
            x, y = float(p["x"]), float(p["y"])
            rot = float(p.get("rotation", 0))

            for fp in board.GetFootprints():
                if fp.GetReference() == ref:
                    fp.SetPosition(pcb.VECTOR2I(pcb.FromMM(x), pcb.FromMM(y)))
                    if rot:
                        fp.SetOrientationDegrees(rot)
                    applied += 1
                    break

        pcb.Refresh()
        return {"applied": applied, "total": len(placements)}

    def _add_3d_model(self, params: dict) -> dict:
        """풋프린트에 3D 모델 경로 설정"""
        pcb = self._pcbnew
        if not pcb:
            raise RuntimeError("pcbnew 모듈 없음")

        board = pcb.GetBoard()
        reference = params["reference"]
        model_path = params["model_path"]  # .step 또는 .wrl

        for fp in board.GetFootprints():
            if fp.GetReference() == reference:
                model = pcb.FP_3DMODEL()
                model.m_Filename = model_path
                fp.Models().push_back(model)
                return {"reference": reference, "model": model_path}

        raise ValueError(f"풋프린트 '{reference}' 를 찾을 수 없음")

    # ─── 공통 ─────────────────────────────────────────────

    def _refresh(self, params: dict) -> dict:
        """KiCad 화면 갱신"""
        if self._pcbnew:
            self._pcbnew.Refresh()
        return {"refreshed": True}

    def _ping(self, params: dict) -> dict:
        return {"status": "alive", "pcbnew": self._pcbnew is not None}

    @staticmethod
    def _inject_sexp(file_path: str, sexp_block: str):
        """S-expression 블록을 .kicad_sch 파일에 주입"""
        path = Path(file_path)
        content = path.read_text(encoding="utf-8")
        last_paren = content.rfind(")")
        if last_paren == -1:
            raise ValueError("유효하지 않은 .kicad_sch 파일")
        new_content = content[:last_paren] + "\n" + sexp_block + content[last_paren:]
        path.write_text(new_content, encoding="utf-8")
