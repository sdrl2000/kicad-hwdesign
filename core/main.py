"""
hwdesign MCP Server

Claude Desktop에서 MCP 도구로 호출되는 KiCad 하드웨어 설계 자동화 서버.
AI 추론은 Claude가 직접 수행하고, 이 서버는 KiCad 조작/검색/최적화 도구만 제공.

사용법:
  Claude Desktop의 claude_desktop_config.json에 등록:
  {
    "mcpServers": {
      "hwdesign": {
        "command": "/path/to/hwdesign/.venv/bin/python",
        "args": ["-m", "core.main"],
        "cwd": "/path/to/hwdesign"
      }
    }
  }
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

from fastmcp import FastMCP
from loguru import logger

# ─── MCP 서버 인스턴스 ──────────────────────────────────

mcp = FastMCP(
    name="hwdesign",
    instructions="""hwdesign — AI 기반 KiCad 하드웨어 설계 자동화 MCP 서버.

KiCad 9 프로젝트의 회로도/PCB를 분석·조작하는 도구를 제공합니다.
AI 판단(회로 구성, 배치 전략 등)은 당신(Claude)이 직접 수행하고,
이 서버의 도구로 KiCad 파일 조작, 부품 검색, 최적화를 실행하세요.

주요 도구 카테고리:
- 스키매틱: 심볼 목록 조회, 심볼 배치, 와이어 연결, 넷리스트 추출
- PCB 레이아웃: 배치 최적화, 자동 라우팅, 풋프린트 생성
- 검증: DRC/ERC 실행, 핀 충돌 분석
- 내보내기: Gerber, PDF, STEP, BOM
- 부품 검색: LCSC 부품 검색, BOM 가격 통합
- 펌웨어: 디바이스 트리 생성, MCU 핀 분석
""",
)


# ═══════════════════════════════════════════════════════════
# 스키매틱 도구
# ═══════════════════════════════════════════════════════════


@mcp.tool()
async def list_schematic_symbols(file_path: str) -> str:
    """스키매틱 파일의 모든 심볼(컴포넌트) 목록을 조회합니다.

    Args:
        file_path: .kicad_sch 파일 경로
    """
    from .kicad_adapter.swig_adapter import SWIGSchematicAdapter

    adapter = SWIGSchematicAdapter(file_path)
    symbols = adapter.get_all_symbols()

    if not symbols:
        return "심볼이 없습니다."

    lines = [f"# 스키매틱 심볼 목록 ({len(symbols)}개)", ""]
    lines.append("| Reference | Value | Library | Position |")
    lines.append("|-----------|-------|---------|----------|")
    for s in symbols:
        lines.append(
            f"| {s.reference} | {s.value} | {s.library_id} | ({s.position.x_mm:.1f}, {s.position.y_mm:.1f}) |"
        )
    return "\n".join(lines)


@mcp.tool()
async def place_schematic_symbol(
    file_path: str,
    library: str,
    symbol: str,
    x: float,
    y: float,
    reference: str = "",
    value: str = "",
    rotation: float = 0.0,
) -> str:
    """스키매틱에 심볼을 배치합니다.

    Args:
        file_path: .kicad_sch 파일 경로
        library: KiCad 라이브러리명 (예: "Device", "MCU_ST_STM32H7")
        symbol: 심볼명 (예: "R", "STM32H743VITx")
        x: X 좌표 (mm)
        y: Y 좌표 (mm)
        reference: 참조 지정자 (예: "R1"). 비워두면 자동 할당
        value: 값 (예: "10k"). 비워두면 심볼명 사용
        rotation: 회전 각도 (0, 90, 180, 270)
    """
    from .kicad_adapter.base import Position
    from .kicad_adapter.swig_adapter import SWIGSchematicAdapter

    adapter = SWIGSchematicAdapter(file_path)
    result = adapter.place_symbol(
        lib=library,
        symbol=symbol,
        pos=Position(x, y),
        reference=reference,
        value=value,
        rotation=rotation,
    )
    return f"심볼 배치 완료: {result.reference} ({library}:{symbol}) = {result.value} at ({x}, {y})"


@mcp.tool()
async def add_schematic_wire(
    file_path: str,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
) -> str:
    """스키매틱에 와이어(전선)를 추가합니다.

    Args:
        file_path: .kicad_sch 파일 경로
        start_x: 시작 X 좌표
        start_y: 시작 Y 좌표
        end_x: 끝 X 좌표
        end_y: 끝 Y 좌표
    """
    from .kicad_adapter.base import Position
    from .kicad_adapter.swig_adapter import SWIGSchematicAdapter

    adapter = SWIGSchematicAdapter(file_path)
    adapter.add_wire(Position(start_x, start_y), Position(end_x, end_y))
    return f"와이어 추가: ({start_x}, {start_y}) → ({end_x}, {end_y})"


@mcp.tool()
async def add_schematic_label(
    file_path: str,
    text: str,
    x: float,
    y: float,
    label_type: str = "global",
    orientation: float = 0.0,
) -> str:
    """스키매틱에 넷 라벨을 추가합니다.

    Args:
        file_path: .kicad_sch 파일 경로
        text: 라벨 텍스트 (넷 이름, 예: "VCC", "SDA", "GPIO5")
        x: X 좌표
        y: Y 좌표
        label_type: 라벨 유형 — "local", "global", "hierarchical", "power"
        orientation: 방향 (0, 90, 180, 270)
    """
    from .kicad_adapter.base import Position
    from .kicad_adapter.swig_adapter import SWIGSchematicAdapter

    adapter = SWIGSchematicAdapter(file_path)
    adapter.add_label(text, Position(x, y), label_type, orientation)
    return f"라벨 추가: '{text}' ({label_type}) at ({x}, {y})"


@mcp.tool()
async def search_kicad_symbols(query: str, kicad_lib_path: str = "") -> str:
    """KiCad 공식 라이브러리에서 심볼을 검색합니다.

    Args:
        query: 검색어 (예: "STM32H7", "USB-C", "LDO", "MOSFET")
        kicad_lib_path: 심볼 라이브러리 경로. 비워두면 시스템 기본 경로 사용
    """
    from .schematic.symbol_placer import SymbolPlacer
    from .kicad_adapter.swig_adapter import SWIGSchematicAdapter

    # 임시 adapter (검색만 사용)
    placer = SymbolPlacer(SWIGSchematicAdapter())
    results = placer.search_symbol(query, kicad_lib_path)

    if not results:
        return f"'{query}'에 대한 심볼을 찾지 못했습니다."

    lines = [f"# 심볼 검색 결과: '{query}' ({len(results)}개)", ""]
    lines.append("| Library | Symbol |")
    lines.append("|---------|--------|")
    for r in results[:30]:
        lines.append(f"| {r['lib']} | {r['symbol']} |")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# PCB 레이아웃 도구
# ═══════════════════════════════════════════════════════════


@mcp.tool()
async def optimize_pcb_placement(
    pcb_path: str,
    strategy: str = "hybrid",
    generations: int = 100,
) -> str:
    """PCB 컴포넌트 배치를 AI 최적화합니다.

    물리 기반 또는 유전 알고리즘으로 와이어 길이를 최소화하는 최적 배치를 계산합니다.

    Args:
        pcb_path: .kicad_pcb 파일 경로
        strategy: 최적화 전략 — "physics"(빠름), "evolutionary"(정밀), "hybrid"(권장)
        generations: 세대 수 (evolutionary/hybrid에서 사용, 기본 100)
    """
    from .layout.placement import AIPlacementEngine, PlacementStrategy

    engine = AIPlacementEngine()
    result = engine.optimize(
        pcb_path=pcb_path,
        strategy=PlacementStrategy(strategy),
        generations=generations,
    )
    return (
        f"배치 최적화 완료\n"
        f"- 전략: {result.strategy}\n"
        f"- 소요 시간: {result.duration_seconds:.1f}초\n"
        f"- 출력 파일: {result.output_path}\n"
        f"{result.report}"
    )


@mcp.tool()
async def route_pcb(
    pcb_path: str,
    method: str = "adaptive",
) -> str:
    """PCB 자동 라우팅을 실행합니다.

    A* pathfinding 기반으로 모든 넷을 자동 라우팅합니다.

    Args:
        pcb_path: .kicad_pcb 파일 경로
        method: 라우팅 방식 — "basic", "negotiated", "adaptive"(권장), "parallel"
    """
    from .layout.routing import AIRoutingEngine

    engine = AIRoutingEngine()
    result = engine.route(pcb_path=pcb_path, method=method)
    return (
        f"라우팅 완료\n"
        f"- 총 넷: {result.total_nets}\n"
        f"- 성공: {result.routed_nets} ({result.success_rate:.0%})\n"
        f"- 실패: {', '.join(result.failed_nets) if result.failed_nets else '없음'}\n"
        f"- 소요 시간: {result.duration_seconds:.1f}초\n"
        f"- 출력 파일: {result.output_path}"
    )


@mcp.tool()
async def generate_footprint(
    package_type: str,
    pins: int,
    pitch: float = 0.0,
    body_size: float = 0.0,
    exposed_pad: float = 0.0,
    output_dir: str = "",
) -> str:
    """IPC-7351 기준 풋프린트를 자동 생성합니다.

    Args:
        package_type: 패키지 유형 — "SOIC", "QFP", "QFN", "SOT", "chip", "BGA", "DIP", "DFN"
        pins: 핀 수
        pitch: 핀 간격 (mm). 0이면 패키지 기본값 사용
        body_size: 패키지 크기 (mm, 정사각형). QFP/QFN에서 사용
        exposed_pad: 열방출 패드 크기 (mm). QFN에서 사용
        output_dir: 출력 디렉토리. 비워두면 임시 디렉토리 사용
    """
    from .layout.footprint_gen import FootprintGenerator, FootprintSpec

    gen = FootprintGenerator()
    spec = FootprintSpec(
        package_type=package_type,
        pins=pins,
        pitch=pitch,
        body_size=body_size,
        exposed_pad=exposed_pad,
    )
    out_dir = output_dir or tempfile.mkdtemp(prefix="hwdesign_fp_")
    path = gen.generate(spec, output_dir=out_dir)
    return f"풋프린트 생성 완료: {path}"


# ═══════════════════════════════════════════════════════════
# 검증 도구
# ═══════════════════════════════════════════════════════════


@mcp.tool()
async def run_drc(pcb_path: str) -> str:
    """PCB Design Rule Check (DRC)를 실행합니다.

    Args:
        pcb_path: .kicad_pcb 파일 경로
    """
    from .kicad_adapter import create_cli_adapter

    cli = create_cli_adapter(board_path=pcb_path)
    violations = cli.run_drc()

    if not violations:
        return "DRC 통과 — 위반 사항 없음"

    lines = [f"# DRC 결과: {len(violations)}개 위반", ""]
    for v in violations:
        icon = "🔴" if v.severity == "error" else "🟡"
        lines.append(f"- {icon} [{v.severity}] {v.violation_type}: {v.description}")
    return "\n".join(lines)


@mcp.tool()
async def run_erc(schematic_path: str) -> str:
    """Electrical Rule Check (ERC)를 실행합니다.

    Args:
        schematic_path: .kicad_sch 파일 경로
    """
    from .kicad_adapter import create_cli_adapter

    cli = create_cli_adapter(schematic_path=schematic_path)
    violations = cli.run_erc()

    if not violations:
        return "ERC 통과 — 위반 사항 없음"

    lines = [f"# ERC 결과: {len(violations)}개 위반", ""]
    for v in violations:
        icon = "🔴" if v.severity == "error" else "🟡"
        lines.append(f"- {icon} [{v.severity}] {v.violation_type}: {v.description}")
    return "\n".join(lines)


@mcp.tool()
async def analyze_mcu_pins(
    schematic_path: str,
    component_ref: str = "",
) -> str:
    """스키매틱에서 MCU 핀 할당을 분석하고 충돌을 검출합니다.

    지원 MCU: STM32, ESP32, nRF52, RP2040, ATmega, SAMD

    Args:
        schematic_path: .kicad_sch 파일 경로
        component_ref: 분석할 MCU 참조 (예: "U1"). 비워두면 자동 감지
    """
    from .kicad_adapter.swig_adapter import SWIGSchematicAdapter
    from .firmware.pin_analyzer import PinAnalyzer, PinAssignment

    adapter = SWIGSchematicAdapter(schematic_path)
    symbols = adapter.get_all_symbols()
    analyzer = PinAnalyzer()

    # MCU 찾기
    mcu = None
    for s in symbols:
        family = analyzer.detect_mcu_family(s.value)
        if family:
            if not component_ref or s.reference == component_ref:
                mcu = s
                break

    if not mcu:
        return "MCU를 찾을 수 없습니다."

    family = analyzer.detect_mcu_family(mcu.value)
    spec = analyzer.get_mcu_pin_spec(family)

    lines = [
        f"# MCU 핀 분석: {mcu.reference} ({mcu.value})",
        f"- 패밀리: {family}",
        f"- 최대 전류: {spec.get('max_current_ma', 'N/A')}mA",
        f"- ADC: {spec.get('adc_bits', 'N/A')}bit",
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 내보내기 도구
# ═══════════════════════════════════════════════════════════


@mcp.tool()
async def export_gerber(pcb_path: str, output_dir: str) -> str:
    """Gerber 제조 파일을 내보냅니다.

    Args:
        pcb_path: .kicad_pcb 파일 경로
        output_dir: Gerber 파일 출력 디렉토리
    """
    from .kicad_adapter import create_cli_adapter

    cli = create_cli_adapter(board_path=pcb_path)
    path = cli.export_gerber(output_dir)
    return f"Gerber 내보내기 완료: {path}"


@mcp.tool()
async def export_bom(schematic_path: str, output_path: str = "") -> str:
    """BOM(Bill of Materials)을 내보냅니다.

    Args:
        schematic_path: .kicad_sch 파일 경로
        output_path: 출력 파일 경로 (비워두면 자동 생성)
    """
    from .kicad_adapter import create_cli_adapter

    cli = create_cli_adapter(schematic_path=schematic_path)
    path = cli.export_bom(output_path)
    return f"BOM 내보내기 완료: {path}"


# ═══════════════════════════════════════════════════════════
# 부품 검색 도구
# ═══════════════════════════════════════════════════════════


@mcp.tool()
async def search_component(query: str, limit: int = 10) -> str:
    """LCSC에서 전자 부품을 검색합니다. JLCPCB SMT 조립과 호환됩니다.

    Args:
        query: 검색어 (예: "STM32H743", "10k 0402 resistor", "USB-C connector")
        limit: 최대 결과 수 (기본 10)
    """
    from .search.lcsc import LCSCSearch

    searcher = LCSCSearch()
    results = await searcher.search(query, limit)

    if not results:
        return f"'{query}'에 대한 부품을 찾지 못했습니다."

    lines = [f"# LCSC 부품 검색: '{query}' ({len(results)}개)", ""]
    lines.append("| Part Number | Package | Price | Stock | LCSC# |")
    lines.append("|-------------|---------|-------|-------|-------|")
    for r in results:
        lines.append(
            f"| {r.mfr_part_number} | {r.package} | ${r.price_usd:.3f} | {r.stock:,} | {r.lcsc_number} |"
        )
    return "\n".join(lines)


@mcp.tool()
async def enrich_bom_with_pricing(bom_json: str) -> str:
    """BOM에 LCSC 부품 가격/재고 정보를 추가합니다.

    Args:
        bom_json: BOM 항목 JSON 배열. 예: [{"reference":"R1","value":"10k","footprint":"0402"}]
    """
    from .search.lcsc import LCSCSearch
    from .search.bom_integrator import BOMIntegrator

    bom = json.loads(bom_json)
    integrator = BOMIntegrator([LCSCSearch()])
    enriched = await integrator.enrich_bom(bom)

    total = sum(item.get("price_usd", 0) for item in enriched)
    lines = [f"# BOM 가격 정보 ({len(enriched)}개 항목, 총 ${total:.2f})", ""]
    lines.append("| Ref | Value | MPN | Price | Stock | Supplier |")
    lines.append("|-----|-------|-----|-------|-------|----------|")
    for item in enriched:
        lines.append(
            f"| {item.get('reference','')} | {item.get('value','')} | "
            f"{item.get('mfr_part_number','-')} | ${item.get('price_usd',0):.3f} | "
            f"{item.get('stock',0):,} | {item.get('supplier','-')} |"
        )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 펌웨어 도구
# ═══════════════════════════════════════════════════════════


@mcp.tool()
async def generate_device_tree(
    components_json: str,
    nets_json: str = "{}",
    board_name: str = "hwdesign-board",
    target_soc: str = "",
) -> str:
    """스키매틱 정보로 Linux Device Tree Source (.dts)를 생성합니다.

    지원 SoC: STM32, ESP32, nRF52. 30+ 주변장치 바인딩 내장.

    Args:
        components_json: 컴포넌트 JSON 배열. 예: [{"reference":"U1","value":"STM32H743VIT6"}]
        nets_json: 넷 정보 JSON. 예: {"I2C1_SDA": ["U1.PB7", "U2.SDA"]}
        board_name: 보드 이름
        target_soc: 타겟 SoC (예: "stm32"). 비워두면 자동 감지
    """
    from .firmware.device_tree_gen import DeviceTreeGenerator

    components = json.loads(components_json)
    nets = json.loads(nets_json)

    gen = DeviceTreeGenerator()
    result = gen.generate(
        components=components,
        nets=nets,
        board_name=board_name,
        target_soc=target_soc,
    )

    return (
        f"# Device Tree 생성 완료\n"
        f"- SoC: {result.soc_family}\n"
        f"- 주변장치: {len(result.peripherals)}개\n\n"
        f"```dts\n{result.dts_content}\n```"
    )


# ═══════════════════════════════════════════════════════════
# KiCad 실시간 연동 도구 (플러그인 브릿지 경유)
# ═══════════════════════════════════════════════════════════


@mcp.tool()
async def kicad_place_symbol(
    file_path: str,
    library: str,
    symbol: str,
    x: float,
    y: float,
    reference: str = "",
    value: str = "",
) -> str:
    """[실시간] KiCad에 열린 스키매틱에 심볼을 배치합니다.

    KiCad 플러그인이 활성화되어 있으면 즉시 화면에 반영됩니다.
    비활성화 시 파일 수정 후 리로드가 필요합니다.

    Args:
        file_path: .kicad_sch 파일 경로
        library: KiCad 라이브러리명
        symbol: 심볼명
        x: X 좌표 (mm)
        y: Y 좌표 (mm)
        reference: 참조 지정자 (비워두면 자동)
        value: 값 (비워두면 심볼명)
    """
    from .bridge import PluginBridge
    from .kicad_adapter.base import Position
    from .kicad_adapter.swig_adapter import SWIGSchematicAdapter

    bridge = PluginBridge()

    def fallback(params):
        adapter = SWIGSchematicAdapter(file_path)
        r = adapter.place_symbol(library, symbol, Position(x, y), reference, value)
        return {"status": "ok", "result": {"reference": r.reference}, "realtime": False}

    result = bridge.send_or_fallback(
        "place_symbol",
        {"file_path": file_path, "library": library, "symbol": symbol,
         "x": x, "y": y, "reference": reference, "value": value},
        fallback_fn=fallback,
    )

    realtime = result.get("realtime", result.get("status") == "ok")
    ref = result.get("result", {}).get("reference", reference)
    mode = "실시간 반영" if realtime else "파일 수정 (KiCad에서 리로드 필요)"
    return f"심볼 배치: {ref} ({library}:{symbol}) — {mode}"


@mcp.tool()
async def kicad_move_footprint(
    reference: str,
    x: float,
    y: float,
    rotation: float = 0.0,
) -> str:
    """[실시간] KiCad에 열린 PCB에서 풋프린트를 이동합니다.

    KiCad 플러그인이 활성화되어 있으면 즉시 화면에 반영됩니다.

    Args:
        reference: 풋프린트 참조 (예: "U1", "R1")
        x: 이동할 X 좌표 (mm)
        y: 이동할 Y 좌표 (mm)
        rotation: 회전 각도 (도)
    """
    from .bridge import PluginBridge

    bridge = PluginBridge()
    result = bridge.send(
        "move_footprint",
        {"reference": reference, "x": x, "y": y, "rotation": rotation},
    )
    return f"풋프린트 이동: {reference} → ({x}, {y}) rot={rotation}°"


@mcp.tool()
async def kicad_apply_placement(pcb_path: str) -> str:
    """[실시간] 배치 최적화 결과를 KiCad에 열린 PCB에 적용합니다.

    optimize_pcb_placement으로 생성된 최적화 파일을 읽어서
    현재 KiCad 보드의 모든 풋프린트 위치를 업데이트합니다.

    Args:
        pcb_path: 최적화된 .kicad_pcb 파일 경로
    """
    from .bridge import PluginBridge
    from kicad_tools.schema.pcb import PCB

    pcb = PCB.load(pcb_path)
    placements = []
    for fp in pcb.footprints:
        placements.append({
            "reference": fp.reference,
            "x": fp.position[0],
            "y": fp.position[1],
            "rotation": fp.rotation,
        })

    bridge = PluginBridge()
    result = bridge.send("apply_placement", {"placements": placements})
    applied = result.get("result", {}).get("applied", 0)
    return f"배치 적용 완료: {applied}/{len(placements)}개 풋프린트 이동"


@mcp.tool()
async def kicad_get_board_info() -> str:
    """[실시간] KiCad에 열린 PCB의 정보를 조회합니다.

    풋프린트 수, 트레이스 수, 넷 수, 레이어 수 등을 반환합니다.
    """
    from .bridge import PluginBridge

    bridge = PluginBridge()
    result = bridge.send("get_board_info", {})
    info = result.get("result", {})

    return (
        f"# 보드 정보\n"
        f"- 파일: {info.get('file_path', 'N/A')}\n"
        f"- 풋프린트: {info.get('footprint_count', 0)}개\n"
        f"- 트레이스: {info.get('track_count', 0)}개\n"
        f"- 넷: {info.get('net_count', 0)}개\n"
        f"- 레이어: {info.get('layer_count', 0)}개"
    )


@mcp.tool()
async def kicad_add_3d_model(
    reference: str,
    model_path: str,
) -> str:
    """[실시간] 풋프린트에 3D 모델(.step/.wrl)을 설정합니다.

    Args:
        reference: 풋프린트 참조 (예: "U1")
        model_path: 3D 모델 파일 경로 (.step 또는 .wrl)
    """
    from .bridge import PluginBridge

    bridge = PluginBridge()
    result = bridge.send("add_3d_model", {"reference": reference, "model_path": model_path})
    return f"3D 모델 설정: {reference} → {model_path}"


@mcp.tool()
async def kicad_set_bom_property(
    file_path: str,
    reference: str,
    property_name: str,
    property_value: str,
) -> str:
    """스키매틱 심볼의 프로퍼티를 수정합니다. BOM 데이터(LCSC 번호, 가격 등) 설정에 사용.

    Args:
        file_path: .kicad_sch 파일 경로
        reference: 심볼 참조 (예: "U1")
        property_name: 프로퍼티 이름 (예: "LCSC", "MPN", "Price")
        property_value: 프로퍼티 값 (예: "C123456")
    """
    from .bridge import PluginBridge

    bridge = PluginBridge()
    result = bridge.send_or_fallback(
        "set_symbol_property",
        {"file_path": file_path, "reference": reference,
         "property": property_name, "value": property_value},
    )
    return f"프로퍼티 설정: {reference}.{property_name} = {property_value}"


@mcp.tool()
async def kicad_refresh() -> str:
    """[실시간] KiCad 화면을 갱신합니다."""
    from .bridge import PluginBridge

    bridge = PluginBridge()
    bridge.send("refresh", {})
    return "KiCad 화면 갱신 완료"


# ═══════════════════════════════════════════════════════════
# 넷리스트 도구
# ═══════════════════════════════════════════════════════════


@mcp.tool()
async def extract_netlist(schematic_path: str) -> str:
    """스키매틱에서 넷리스트를 추출합니다.

    각 넷에 연결된 핀 목록을 반환합니다.

    Args:
        schematic_path: .kicad_sch 파일 경로
    """
    from .kicad_adapter import create_cli_adapter

    cli = create_cli_adapter(schematic_path=schematic_path)
    netlist_path = cli.generate_netlist()
    return f"넷리스트 생성 완료: {netlist_path}"


# ═══════════════════════════════════════════════════════════
# 진입점
# ═══════════════════════════════════════════════════════════


def main():
    """MCP 서버 시작"""
    mcp.run()


if __name__ == "__main__":
    main()
