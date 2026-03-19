# kicad-hwdesign

[![Tests](https://github.com/yoonpro7/kicad-hwdesign/actions/workflows/test.yml/badge.svg)](https://github.com/yoonpro7/kicad-hwdesign/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

KiCad 9 하드웨어 설계 자동화 MCP 서버.

Claude Desktop / ChatGPT 등 MCP 클라이언트에서 대화형으로 KiCad를 조작합니다.
AI가 추론하고, kicad-hwdesign이 실행합니다. **API 키 불필요 — 구독만으로 동작.**

## 아키텍처

```
Claude Desktop / ChatGPT (구독형 AI, 추론)
      │ MCP (stdio)
      ▼
kicad-hwdesign MCP 서버 (외부 프로세스) ─── 24개 도구
      │
      ├─ 배치 최적화 (physics / evolutionary / hybrid, GPU 가속)
      ├─ 오토라우팅 (A* / negotiated / adaptive / parallel)
      ├─ IPC-7351 풋프린트 생성 (SOIC, QFP, QFN, BGA 등)
      ├─ 부품 검색 (LCSC), BOM 가격 통합
      ├─ DRC/ERC, Gerber/PDF/STEP/BOM 내보내기
      ├─ 넷리스트 파싱, 동적 심볼 로딩
      ├─ MCU 핀 분석, 디바이스 트리/HAL 코드 생성
      │
      └─ 소켓 ──→ KiCad 플러그인 (SWIG/IPC 실시간 조작)
```

## 요구 사항

- **KiCad 9.0+**
- **Python 3.10 ~ 3.12**
- Claude Desktop, ChatGPT Desktop, 또는 기타 MCP 호환 클라이언트

## 설치

```bash
git clone https://github.com/yoonpro7/kicad-hwdesign.git
cd kicad-hwdesign
```

### macOS

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[metal]"      # Apple Silicon GPU 가속
```

### Linux

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
# pip install -e ".[cuda]"    # NVIDIA GPU 가속 (선택)
```

### Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .
# pip install -e ".[cuda]"    # NVIDIA GPU 가속 (선택)
```

## MCP 클라이언트 연결

### Claude Desktop

설정 파일 위치:

| OS | 경로 |
|----|------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/claude/claude_desktop_config.json` |

macOS / Linux:
```json
{
  "mcpServers": {
    "kicad-hwdesign": {
      "command": "/absolute/path/to/kicad-hwdesign/.venv/bin/python",
      "args": ["-m", "core.main"],
      "cwd": "/absolute/path/to/kicad-hwdesign"
    }
  }
}
```

Windows:
```json
{
  "mcpServers": {
    "kicad-hwdesign": {
      "command": "C:\\path\\to\\kicad-hwdesign\\.venv\\Scripts\\python.exe",
      "args": ["-m", "core.main"],
      "cwd": "C:\\path\\to\\kicad-hwdesign"
    }
  }
}
```

### ChatGPT Desktop

Settings → Developer Mode 활성화 → MCP 서버 추가에서 동일한 경로를 등록합니다.

## KiCad 플러그인 (실시간 반영, 선택)

MCP 도구 호출 시 KiCad 화면에 즉시 반영하려면 플러그인을 설치합니다.

```bash
# macOS
ln -s $(pwd)/plugin ~/Library/Application\ Support/kicad/9.0/scripting/plugins/kicad-hwdesign

# Linux
ln -s $(pwd)/plugin ~/.local/share/kicad/9.0/scripting/plugins/kicad-hwdesign

# Windows (관리자 권한 PowerShell)
New-Item -ItemType SymbolicLink -Path "$env:APPDATA\kicad\9.0\scripting\plugins\kicad-hwdesign" -Target "$(Get-Location)\plugin"
```

KiCad 실행 → `도구 → 외부 플러그인 → kicad-hwdesign` 클릭 → 백그라운드 리스너 시작.
플러그인이 꺼져 있어도 MCP 도구는 파일 기반으로 동작합니다 (수동 리로드 필요).

## MCP 도구 (24개)

### 스키매틱
| 도구 | 설명 |
|------|------|
| `list_schematic_symbols` | 심볼 목록 조회 |
| `place_schematic_symbol` | 심볼 배치 (파일) |
| `kicad_place_symbol` | 심볼 배치 [실시간] |
| `add_schematic_wire` | 와이어 연결 |
| `add_schematic_label` | 넷 라벨 추가 |
| `search_kicad_symbols` | 10,000+ 심볼 라이브러리 검색 |
| `extract_netlist` | 넷리스트 추출 |

### PCB 레이아웃
| 도구 | 설명 |
|------|------|
| `optimize_pcb_placement` | 배치 최적화 |
| `route_pcb` | 자동 라우팅 |
| `generate_footprint` | IPC-7351 풋프린트 생성 |
| `kicad_move_footprint` | 풋프린트 이동 [실시간] |
| `kicad_apply_placement` | 배치 결과 일괄 적용 [실시간] |
| `kicad_get_board_info` | 보드 정보 조회 [실시간] |
| `kicad_add_3d_model` | 3D 모델 설정 [실시간] |

### 검증 & 내보내기
| 도구 | 설명 |
|------|------|
| `run_drc` | Design Rule Check |
| `run_erc` | Electrical Rule Check |
| `analyze_mcu_pins` | MCU 핀 충돌 분석 (STM32/ESP32/nRF52/RP2040) |
| `export_gerber` | Gerber 제조 파일 |
| `export_bom` | BOM 내보내기 |

### 부품 & 펌웨어
| 도구 | 설명 |
|------|------|
| `search_component` | LCSC 부품 검색 (JLCPCB 호환) |
| `enrich_bom_with_pricing` | BOM 가격/재고 통합 |
| `kicad_set_bom_property` | BOM 프로퍼티 설정 [실시간] |
| `generate_device_tree` | Linux Device Tree 생성 |
| `kicad_refresh` | KiCad 화면 갱신 [실시간] |

## 참조 프로젝트

아래 오픈소스 프로젝트의 아키텍처와 알고리즘을 참조하여 구축되었습니다:

- [mixelpixx/KiCAD-MCP-Server](https://github.com/mixelpixx/KiCAD-MCP-Server) — 동적 심볼 로딩, 와이어 연결, 핀 좌표 계산
- [rjwalters/kicad-tools](https://github.com/rjwalters/kicad-tools) — PlacementOptimizer, Autorouter, IPC-7351 풋프린트
- [Seeed-Studio/kicad-mcp-server](https://github.com/Seeed-Studio/kicad-mcp-server) — DRC/ERC 검증, 디바이스 트리, 핀 분석

## AI로 작성됨

이 프로젝트는 **Claude (Anthropic)**를 활용하여 설계, 코드 작성, 테스트가 수행되었습니다.
아키텍처 결정, 참조 레포 분석, 코드 구현, 테스트 전 과정에서 AI가 보조 도구로 사용되었습니다.

## 테스트

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## 라이선스

MIT
