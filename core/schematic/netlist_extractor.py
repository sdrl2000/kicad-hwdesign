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
class SchematicData:
    components: list[ParsedComponent] = field(default_factory=list)
    nets: list[ParsedNet] = field(default_factory=list)
    wires: list[ParsedWire] = field(default_factory=list)
    lib_symbols: dict[str, dict] = field(default_factory=dict)


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
        logger.info(
            f"파싱: {len(self._data.components)} 컴포넌트, "
            f"{len(self._data.nets)} 넷, {len(self._data.wires)} 와이어"
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
