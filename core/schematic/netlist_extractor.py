"""
넷리스트 추출기 — Seeed schematic_parser.py 참조

.kicad_sch 파일을 직접 파싱하여
컴포넌트, 넷, 와이어 네트워크를 추출.
kicad-cli 없이 순수 텍스트 파싱으로 동작.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from loguru import logger


@dataclass
class ParsedComponent:
    reference: str
    value: str
    lib_id: str
    footprint: str = ""
    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0
    pins: list[dict] = field(default_factory=list)
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedNet:
    name: str
    net_type: str = "local"
    x: float = 0.0
    y: float = 0.0


@dataclass
class ParsedWire:
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class ParsedSheetPin:
    name: str
    direction: str  # input, output, bidirectional, passive
    x: float = 0.0
    y: float = 0.0


@dataclass
class ParsedSheet:
    name: str
    file: str  # relative path to subsheet .kicad_sch
    x: float = 0.0
    y: float = 0.0
    width: float = 40.0
    height: float = 30.0
    uuid: str = ""
    pins: list[ParsedSheetPin] = field(default_factory=list)


@dataclass
class SchematicData:
    components: list[ParsedComponent] = field(default_factory=list)
    nets: list[ParsedNet] = field(default_factory=list)
    wires: list[ParsedWire] = field(default_factory=list)
    lib_symbols: dict[str, dict] = field(default_factory=dict)
    sheets: list[ParsedSheet] = field(default_factory=list)


class NetlistExtractor:
    """
    .kicad_sch 순수 텍스트 파서

    정규식 기반으로 외부 의존성 없이 동작.
    lib_symbols 핀 정보, 컴포넌트 인스턴스, 넷 라벨, 와이어를 추출.
    """

    def __init__(self, file_path: str):
        self._path = Path(file_path)
        self._content = ""
        self._data: Optional[SchematicData] = None

    def parse(self) -> SchematicData:
        self._content = self._path.read_text(encoding="utf-8")
        self._data = SchematicData()
        self._parse_lib_symbols()
        self._parse_components()
        self._parse_nets()
        self._parse_wires()
        self._parse_sheets()
        logger.info(
            f"파싱: {len(self._data.components)} 컴포넌트, "
            f"{len(self._data.nets)} 넷, {len(self._data.wires)} 와이어, "
            f"{len(self._data.sheets)} 시트"
        )
        return self._data

    # ─── lib_symbols 핀 정보 ──────────────────────────────

    def _parse_lib_symbols(self):
        ls_match = re.search(r"\(lib_symbols\b", self._content)
        if not ls_match:
            return
        block = self._extract_block(self._content, ls_match.start())
        if not block:
            return

        pin_pat = re.compile(
            r'\(pin\s+(\w+)\s+\w+\s[\s\S]*?'
            r'\(name\s+"([^"]*)"[\s\S]*?\)\s*\(number\s+"([^"]*)"'
        )
        for sym_m in re.finditer(r'\(symbol\s+"([^"]*:[^"]*)"', block):
            lib_id = sym_m.group(1)
            sym_block = self._extract_block(block, sym_m.start())
            if not sym_block:
                continue
            pins = {}
            for pm in pin_pat.finditer(sym_block):
                pins[pm.group(3)] = {"name": pm.group(2), "electrical_type": pm.group(1)}
            if pins:
                self._data.lib_symbols[lib_id] = pins

    # ─── 컴포넌트 ─────────────────────────────────────────

    def _parse_components(self):
        # symbol 인스턴스 패턴: (symbol (lib_id ...) 가 있는 블록
        for m in re.finditer(r'\(symbol\s+\(lib_id\s+"([^"]+)"', self._content):
            block = self._extract_block(self._content, m.start())
            if not block:
                continue
            comp = self._parse_one_component(block, m.group(1))
            if comp and comp.reference and not comp.reference.startswith("#"):
                self._data.components.append(comp)

    def _parse_one_component(self, block: str, lib_id: str) -> Optional[ParsedComponent]:
        at_m = re.search(r"\(at\s+([\d.\-]+)\s+([\d.\-]+)(?:\s+([\d.\-]+))?\)", block)
        x = float(at_m.group(1)) if at_m else 0.0
        y = float(at_m.group(2)) if at_m else 0.0
        rot = float(at_m.group(3)) if at_m and at_m.group(3) else 0.0

        ref_m = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
        val_m = re.search(r'\(property\s+"Value"\s+"([^"]+)"', block)
        fp_m = re.search(r'\(property\s+"Footprint"\s+"([^"]+)"', block)

        pins = []
        lib_pins = self._data.lib_symbols.get(lib_id, {})
        for pm in re.finditer(r'\(pin\s+"([^"]+)"', block):
            num = pm.group(1)
            info = lib_pins.get(num, {})
            pins.append({"number": num, "name": info.get("name", ""),
                         "electrical_type": info.get("electrical_type", "")})

        props = {}
        for pp in re.finditer(r'\(property\s+"([^"]+)"\s+"([^"]*)"', block):
            props[pp.group(1)] = pp.group(2)

        return ParsedComponent(
            reference=ref_m.group(1) if ref_m else "",
            value=val_m.group(1) if val_m else "",
            lib_id=lib_id,
            footprint=fp_m.group(1) if fp_m else "",
            x=x, y=y, rotation=rot, pins=pins, properties=props,
        )

    # ─── 넷 ───────────────────────────────────────────────

    def _parse_nets(self):
        patterns = [
            (r'\(global_label\s+"([^"]+)"[\s\S]*?\(at\s+([\d.\-]+)\s+([\d.\-]+)', "global"),
            (r'\(label\s+"([^"]+)"[\s\S]*?\(at\s+([\d.\-]+)\s+([\d.\-]+)', "local"),
            (r'\(hierarchical_label\s+"([^"]+)"[\s\S]*?\(at\s+([\d.\-]+)\s+([\d.\-]+)', "hierarchical"),
            (r'\(symbol\s+\(lib_id\s+"power:([^"]+)"[\s\S]*?\(at\s+([\d.\-]+)\s+([\d.\-]+)', "power"),
        ]
        for pat, ntype in patterns:
            for m in re.finditer(pat, self._content):
                self._data.nets.append(ParsedNet(m.group(1), ntype, float(m.group(2)), float(m.group(3))))

    # ─── 와이어 ───────────────────────────────────────────

    def _parse_wires(self):
        for m in re.finditer(
            r'\(wire\s+\(pts\s+\(xy\s+([\d.\-]+)\s+([\d.\-]+)\)\s+\(xy\s+([\d.\-]+)\s+([\d.\-]+)\)',
            self._content,
        ):
            self._data.wires.append(ParsedWire(
                float(m.group(1)), float(m.group(2)),
                float(m.group(3)), float(m.group(4)),
            ))

    # ─── 계층 시트 ─────────────────────────────────────────

    def _parse_sheets(self):
        """(sheet ...) 블록에서 서브시트 참조 추출"""
        for m in re.finditer(r'\(sheet\s', self._content):
            block = self._extract_block(self._content, m.start())
            if not block:
                continue
            sheet = self._parse_one_sheet(block)
            if sheet:
                self._data.sheets.append(sheet)

    def _parse_one_sheet(self, block: str) -> Optional[ParsedSheet]:
        at_m = re.search(r'\(at\s+([\d.\-]+)\s+([\d.\-]+)\)', block)
        size_m = re.search(r'\(size\s+([\d.\-]+)\s+([\d.\-]+)\)', block)
        uuid_m = re.search(r'\(uuid\s+"([^"]+)"\)', block)
        name_m = re.search(r'\(property\s+"Sheetname"\s+"([^"]+)"', block)
        file_m = re.search(r'\(property\s+"Sheetfile"\s+"([^"]+)"', block)

        if not name_m or not file_m:
            return None

        pins = []
        for pm in re.finditer(r'\(pin\s+"([^"]+)"\s+(\w+)\s*\(at\s+([\d.\-]+)\s+([\d.\-]+)', block):
            pins.append(ParsedSheetPin(
                name=pm.group(1),
                direction=pm.group(2),
                x=float(pm.group(3)),
                y=float(pm.group(4)),
            ))

        return ParsedSheet(
            name=name_m.group(1),
            file=file_m.group(1),
            x=float(at_m.group(1)) if at_m else 0.0,
            y=float(at_m.group(2)) if at_m else 0.0,
            width=float(size_m.group(1)) if size_m else 40.0,
            height=float(size_m.group(2)) if size_m else 30.0,
            uuid=uuid_m.group(1) if uuid_m else "",
            pins=pins,
        )

    def parse_hierarchy(self) -> dict:
        """
        전체 계층 트리를 재귀적으로 파싱.

        반환:
            {"name": "Root", "file": "main.kicad_sch", "components": [...],
             "sheets": [{"name": "Logic", "file": "logic.kicad_sch", "components": [...], "sheets": [...]}]}
        """
        if not self._data:
            self.parse()

        visited: set[str] = {str(self._path.resolve())}
        return self._build_hierarchy_tree(self._path, self._data, visited)

    def _build_hierarchy_tree(
        self, sch_path: Path, data: SchematicData, visited: set[str]
    ) -> dict:
        tree: dict[str, Any] = {
            "name": sch_path.stem,
            "file": sch_path.name,
            "components": [
                {"reference": c.reference, "value": c.value, "lib_id": c.lib_id}
                for c in data.components
            ],
            "nets": [{"name": n.name, "type": n.net_type} for n in data.nets],
            "sheets": [],
        }

        for sheet in data.sheets:
            sub_path = sch_path.parent / sheet.file
            resolved = str(sub_path.resolve())

            if resolved in visited:
                logger.warning(f"순환 참조 감지: {sheet.file}")
                continue
            if not sub_path.exists():
                logger.warning(f"서브시트 없음: {sub_path}")
                tree["sheets"].append({
                    "name": sheet.name, "file": sheet.file,
                    "error": "file not found", "components": [], "nets": [], "sheets": [],
                })
                continue

            visited.add(resolved)
            sub_ext = NetlistExtractor(str(sub_path))
            sub_data = sub_ext.parse()
            sub_tree = self._build_hierarchy_tree(sub_path, sub_data, visited)
            sub_tree["name"] = sheet.name
            sub_tree["pins"] = [{"name": p.name, "direction": p.direction} for p in sheet.pins]
            tree["sheets"].append(sub_tree)

        return tree

    def get_all_components_recursive(self) -> list[dict]:
        """모든 시트의 컴포넌트를 flat 리스트로 반환 (계층 경로 포함)"""
        if not self._data:
            self.parse()

        result: list[dict] = []
        self._collect_components(self._path, self._data, "Root", result, set())
        return result

    def _collect_components(
        self, sch_path: Path, data: SchematicData,
        path_prefix: str, result: list[dict], visited: set[str],
    ):
        resolved = str(sch_path.resolve())
        if resolved in visited:
            return
        visited.add(resolved)

        for c in data.components:
            result.append({
                "reference": c.reference, "value": c.value,
                "lib_id": c.lib_id, "footprint": c.footprint,
                "sheet_path": path_prefix,
            })

        for sheet in data.sheets:
            sub_path = sch_path.parent / sheet.file
            if not sub_path.exists():
                continue
            sub_ext = NetlistExtractor(str(sub_path))
            sub_data = sub_ext.parse()
            self._collect_components(
                sub_path, sub_data,
                f"{path_prefix}/{sheet.name}", result, visited,
            )

    def validate_hierarchy(self) -> list[dict]:
        """
        계층 설계 검증.

        반환: [{"severity": "error"|"warning", "message": "...", "sheet": "..."}]
        """
        if not self._data:
            self.parse()

        issues: list[dict] = []
        self._validate_sheets(self._path, self._data, issues, set())
        return issues

    def _validate_sheets(
        self, sch_path: Path, data: SchematicData,
        issues: list[dict], visited: set[str],
    ):
        resolved = str(sch_path.resolve())
        if resolved in visited:
            issues.append({"severity": "error", "message": "순환 참조", "sheet": sch_path.name})
            return
        visited.add(resolved)

        for sheet in data.sheets:
            sub_path = sch_path.parent / sheet.file
            if not sub_path.exists():
                issues.append({
                    "severity": "error",
                    "message": f"서브시트 파일 없음: {sheet.file}",
                    "sheet": sch_path.name,
                })
                continue

            # 서브시트 파싱
            sub_ext = NetlistExtractor(str(sub_path))
            sub_data = sub_ext.parse()

            # 시트 핀 ↔ hierarchical_label 매칭 검증
            sub_hlabels = {n.name for n in sub_data.nets if n.net_type == "hierarchical"}
            sheet_pin_names = {p.name for p in sheet.pins}

            for pin_name in sheet_pin_names - sub_hlabels:
                issues.append({
                    "severity": "warning",
                    "message": f"시트 핀 '{pin_name}'에 대응하는 hierarchical_label 없음",
                    "sheet": sheet.file,
                })

            for label_name in sub_hlabels - sheet_pin_names:
                issues.append({
                    "severity": "warning",
                    "message": f"hierarchical_label '{label_name}'에 대응하는 시트 핀 없음",
                    "sheet": sheet.file,
                })

            # 재귀 검증
            self._validate_sheets(sub_path, sub_data, issues, visited)

    # ─── 와이어 네트워크 ─────────────────────────────────────

    def build_wire_network(self) -> dict[tuple, list[tuple]]:
        """와이어 연결 그래프 (토폴로지 분석용)"""
        if not self._data:
            self.parse()
        network: dict[tuple, list[tuple]] = {}
        for w in self._data.wires:
            p1, p2 = (w.x1, w.y1), (w.x2, w.y2)
            network.setdefault(p1, []).append(p2)
            network.setdefault(p2, []).append(p1)

        tol = 0.01
        for m in re.finditer(r'\(junction\s+\(at\s+([\d.\-]+)\s+([\d.\-]+)', self._content):
            jx, jy = float(m.group(1)), float(m.group(2))
            connected = [p for p in network if abs(p[0]-jx) < tol and abs(p[1]-jy) < tol]
            neighbors: set[tuple] = set()
            for p in connected:
                neighbors.update(network[p])
            for p in connected:
                network[p] = list(neighbors - {p})
        return network

    @staticmethod
    def _extract_block(text: str, start: int) -> Optional[str]:
        depth = 0
        for i in range(start, min(start + 50000, len(text))):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return None
