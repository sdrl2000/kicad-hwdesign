# kicad-hwdesign

[![Tests](https://github.com/sdrl2000/kicad-hwdesign/actions/workflows/test.yml/badge.svg)](https://github.com/sdrl2000/kicad-hwdesign/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

KiCad 9 하드웨어 설계 자동화 MCP 서버.

Claude Desktop / ChatGPT 등 MCP 클라이언트에서 대화형으로 KiCad를 조작합니다.
AI가 추론하고, kicad-hwdesign이 실행합니다. **API 키 불필요 — AI 구독만으로 동작.**

## 주요 기능

- **회로도 자동화** — 심볼 배치, 와이어 연결, 넷 라벨, 10,000+ 심볼 라이브러리 검색
- **PCB 레이아웃** — 물리/유전 알고리즘 배치 최적화, A* 기반 자동 라우팅, GPU 가속
- **IPC-7351 풋프린트** — SOIC, QFP, QFN, BGA, DIP, SOT, DFN, chip 8종 자동 생성
- **부품 검색** — LCSC/JLCPCB(무료), Mouser, DigiKey 3사 통합 검색 + BOM 가격 자동 병합
- **설계 검증** — kicad-cli 기반 DRC/ERC, MCU 핀 충돌 분석 (STM32/ESP32/nRF52/RP2040/ATmega/SAMD)
- **내보내기** — Gerber, PDF, STEP, BOM, 넷리스트
- **펌웨어 코드 생성** — Linux Device Tree (.dts), STM32 HAL/Arduino 초기화 코드
- **실시간 KiCad 연동** — 소켓 기반 플러그인으로 KiCad 화면 즉시 반영 (선택)

## 아키텍처

```
Claude Desktop / ChatGPT (구독형 AI, 추론 담당)
      │ MCP (stdio)
      ▼
kicad-hwdesign MCP 서버 ── 28개 도구
      │
      ├─ 파일 기반 도구 (17개)
      │   ├─ 스키매틱: 심볼 배치, 와이어 연결, 라벨, 심볼 검색, 넷리스트
      │   ├─ PCB: 배치 최적화, 오토라우팅, 풋프린트 생성
      │   ├─ 검증: DRC, ERC, MCU 핀 분석
      │   ├─ 내보내기: Gerber, BOM, 넷리스트
      │   ├─ 부품: LCSC/Mouser/DigiKey 검색, BOM 가격 통합
      │   └─ 펌웨어: 디바이스 트리, HAL 코드 생성
      │
      └─ 실시간 도구 (8개) ─── 소켓 ──→ KiCad 플러그인 (SWIG/IPC)
```

## 요구 사항

- **KiCad 9.0+** (kicad-cli 자동 감지 — Windows/macOS/Linux)
- **Python 3.10 ~ 3.12**
- MCP 호환 클라이언트 (Claude Desktop, ChatGPT Desktop, Claude Code 등)

## 설치

```bash
git clone https://github.com/sdrl2000/kicad-hwdesign.git
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

### Claude Code

```bash
claude mcp add kicad-hwdesign -- /path/to/kicad-hwdesign/.venv/bin/python -m core.main
```

### ChatGPT Desktop

Settings → Developer Mode 활성화 → MCP 서버 추가에서 동일한 경로를 등록합니다.

## 사용 예시

MCP 클라이언트에서 자연어로 요청합니다:

```
"STM32H743 기반 USB-C PD 회로를 설계해줘"
→ 심볼 검색 → 배치 → 와이어 연결 → DRC/ERC → Gerber 내보내기

"이 PCB의 배치를 최적화해줘"
→ optimize_pcb_placement (hybrid, 100세대)

"LCSC에서 STM32H743VIT6 가격 찾아줘"
→ search_component("STM32H743VIT6")
→ 결과: $9.22 | 재고 726 | LCSC# C114409

"BOM에 부품 가격 추가해줘"
→ enrich_bom_with_pricing([{"reference":"R1","value":"10k","footprint":"0402"}, ...])

"이 MCU의 핀 충돌 확인해줘"
→ analyze_mcu_pins("project.kicad_sch")
```

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

## MCP 도구 (28개)

### 스키매틱

| 도구 | 설명 |
|------|------|
| `list_schematic_symbols` | 심볼 목록 조회 |
| `place_schematic_symbol` | 심볼 배치 (파일) |
| `add_schematic_wire` | 와이어 연결 |
| `add_schematic_label` | 넷 라벨 추가 (local/global/hierarchical/power) |
| `search_kicad_symbols` | 10,000+ 심볼 라이브러리 검색 |
| `extract_netlist` | 넷리스트 추출 |
| `kicad_place_symbol` | 심볼 배치 [실시간] |

### PCB 레이아웃

| 도구 | 설명 |
|------|------|
| `optimize_pcb_placement` | AI 배치 최적화 (physics/evolutionary/hybrid) |
| `route_pcb` | 자동 라우팅 (basic/negotiated/adaptive/parallel) |
| `generate_footprint` | IPC-7351 풋프린트 생성 (8종 패키지) |
| `kicad_move_footprint` | 풋프린트 이동 [실시간] |
| `kicad_apply_placement` | 배치 결과 일괄 적용 [실시간] |
| `kicad_get_board_info` | 보드 정보 조회 [실시간] |
| `kicad_add_3d_model` | 3D 모델 설정 [실시간] |

### 검증 & 내보내기

| 도구 | 설명 |
|------|------|
| `run_drc` | Design Rule Check |
| `run_erc` | Electrical Rule Check |
| `analyze_mcu_pins` | MCU 핀 충돌 분석 (STM32/ESP32/nRF52/RP2040/ATmega/SAMD) |
| `export_gerber` | Gerber + 드릴 제조 파일 |
| `export_bom` | BOM (CSV) 내보내기 |

### 부품 검색 & 펌웨어

| 도구 | 설명 |
|------|------|
| `search_component` | LCSC/JLCPCB 부품 검색 (API 키 불필요) |
| `search_component_multi` | LCSC + Mouser + DigiKey 통합 검색 |
| `enrich_bom_with_pricing` | BOM 가격/재고 자동 병합 |
| `kicad_set_bom_property` | BOM 프로퍼티 설정 [실시간] |
| `generate_device_tree` | Linux Device Tree (.dts) 생성 |
| `kicad_refresh` | KiCad 화면 갱신 [실시간] |

### 계층 스키매틱

| 도구 | 설명 |
|------|------|
| `get_sheet_hierarchy` | 계층 시트 트리 구조 조회 (재귀) |
| `validate_hierarchical_design` | 계층 설계 무결성 검증 (누락 파일, 핀 매칭) |
| `add_hierarchical_sheet` | 계층 서브시트 추가 (자동 파일 생성) |

## 부품 검색 API 설정 (선택)

LCSC/JLCPCB 검색은 API 키 없이 동작합니다. Mouser/DigiKey를 추가하려면:

```bash
# .env 파일에 추가
MOUSER_API_KEY=your-mouser-api-key
DIGIKEY_CLIENT_ID=your-digikey-client-id
DIGIKEY_CLIENT_SECRET=your-digikey-client-secret
```

- **Mouser**: [Mouser API 등록](https://www.mouser.com/api-search/)에서 키 발급
- **DigiKey**: [DigiKey API 등록](https://developer.digikey.com/)에서 OAuth2 클라이언트 생성

## 테스트

```bash
pip install -e ".[dev]"
pytest tests/ -v             # 전체 테스트 (78개)
pytest tests/test_e2e.py -v  # E2E 테스트 (15개, KiCad 9 + 네트워크 필요)
```

## 참조 프로젝트

아래 오픈소스 프로젝트의 아키텍처와 알고리즘을 참조하여 구축되었습니다:

- [mixelpixx/KiCAD-MCP-Server](https://github.com/mixelpixx/KiCAD-MCP-Server) — 동적 심볼 로딩, 와이어 연결, 핀 좌표 계산
- [rjwalters/kicad-tools](https://github.com/rjwalters/kicad-tools) — PlacementOptimizer, Autorouter, IPC-7351 풋프린트
- [Seeed-Studio/kicad-mcp-server](https://github.com/Seeed-Studio/kicad-mcp-server) — DRC/ERC 검증, 디바이스 트리, 핀 분석

## AI로 작성됨

이 프로젝트는 **Claude (Anthropic)**를 활용하여 설계, 코드 작성, 테스트가 수행되었습니다.

## 라이선스

MIT
