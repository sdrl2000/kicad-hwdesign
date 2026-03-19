# hwdesign — KiCad 9 AI Hardware Design MCP Server

[![Tests](https://github.com/YOUR_USERNAME/hwdesign/actions/workflows/test.yml/badge.svg)](https://github.com/YOUR_USERNAME/hwdesign/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Claude Desktop / ChatGPT에서 MCP로 연결하여 사용하는 KiCad 9 하드웨어 설계 자동화 서버.
AI가 추론하고, hwdesign이 KiCad를 조작합니다. **API 키 불필요** — 구독만으로 동작.

## 아키텍처

```
Claude Desktop / ChatGPT (구독형 AI, 추론)
      │ MCP (stdio)
      ▼
hwdesign MCP 서버 (외부 프로세스) ─── 24개 도구
      │
      ├─ kicad-tools: 배치 최적화 (Metal/CUDA GPU 가속)
      ├─ kicad-tools: 오토라우팅 (A*, Negotiated, Adaptive)
      ├─ kicad-tools: IPC-7351 풋프린트 생성
      ├─ LCSC API: 부품 검색, BOM 가격 통합
      ├─ kicad-cli: DRC/ERC, Gerber/PDF/STEP/BOM 내보내기
      │
      └─ 소켓 (localhost) ──→ KiCad 플러그인 (백그라운드 리스너)
                                 ├─ SWIG: 스키매틱 실시간 조작
                                 ├─ IPC API: PCB 실시간 조작
                                 └─ 3D 모델/BOM 프로퍼티 설정
```

## 설치

```bash
git clone https://github.com/YOUR_USERNAME/hwdesign.git
cd hwdesign

python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[metal]"      # macOS Apple Silicon
# pip install -e ".[cuda]"     # NVIDIA GPU
```

## Claude Desktop 연결

`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "hwdesign": {
      "command": "/absolute/path/to/hwdesign/.venv/bin/python",
      "args": ["-m", "core.main"],
      "cwd": "/absolute/path/to/hwdesign"
    }
  }
}
```

## KiCad 플러그인 설치 (실시간 반영용, 선택)

```bash
# macOS
ln -s $(pwd)/plugin ~/Library/Application\ Support/kicad/9.0/scripting/plugins/hwdesign
# Linux
ln -s $(pwd)/plugin ~/.local/share/kicad/9.0/scripting/plugins/hwdesign
```

KiCad에서 `도구 → 외부 플러그인 → hwdesign` 클릭하면 백그라운드 리스너 시작.

## MCP 도구 (24개)

### 스키매틱
| 도구 | 설명 |
|------|------|
| `list_schematic_symbols` | 심볼 목록 조회 |
| `place_schematic_symbol` | 심볼 배치 (파일) |
| `kicad_place_symbol` | [실시간] 심볼 배치 |
| `add_schematic_wire` | 와이어 연결 |
| `add_schematic_label` | 넷 라벨 추가 |
| `search_kicad_symbols` | 10,000+ 심볼 검색 |
| `extract_netlist` | 넷리스트 추출 |

### PCB 레이아웃
| 도구 | 설명 |
|------|------|
| `optimize_pcb_placement` | 배치 최적화 (physics/evolutionary/hybrid) |
| `route_pcb` | 자동 라우팅 (basic/negotiated/adaptive/parallel) |
| `generate_footprint` | IPC-7351 풋프린트 생성 |
| `kicad_move_footprint` | [실시간] 풋프린트 이동 |
| `kicad_apply_placement` | [실시간] 배치 결과 적용 |
| `kicad_get_board_info` | [실시간] 보드 정보 조회 |
| `kicad_add_3d_model` | [실시간] 3D 모델 설정 |

### 검증 & 내보내기
| 도구 | 설명 |
|------|------|
| `run_drc` | Design Rule Check |
| `run_erc` | Electrical Rule Check |
| `analyze_mcu_pins` | MCU 핀 충돌 분석 |
| `export_gerber` | Gerber 제조 파일 |
| `export_bom` | BOM 내보내기 |

### 부품 & 펌웨어
| 도구 | 설명 |
|------|------|
| `search_component` | LCSC 부품 검색 |
| `enrich_bom_with_pricing` | BOM 가격/재고 통합 |
| `kicad_set_bom_property` | BOM 프로퍼티 설정 |
| `generate_device_tree` | Linux Device Tree 생성 |
| `kicad_refresh` | [실시간] KiCad 화면 갱신 |

## 참조 프로젝트

이 프로젝트는 아래 오픈소스 프로젝트의 아키텍처와 알고리즘을 참조하여 구축되었습니다:

- [mixelpixx/KiCAD-MCP-Server](https://github.com/mixelpixx/KiCAD-MCP-Server) — 동적 심볼 로딩, 와이어 연결, 핀 좌표 계산 알고리즘
- [rjwalters/kicad-tools](https://github.com/rjwalters/kicad-tools) — PlacementOptimizer, Autorouter, IPC-7351 풋프린트 생성
- [Seeed-Studio/kicad-mcp-server](https://github.com/Seeed-Studio/kicad-mcp-server) — DRC/ERC 검증, 디바이스 트리 생성, MCU 핀 분석

## AI로 작성됨

이 프로젝트는 **Claude (Anthropic)의 AI 어시스턴트**를 활용하여 설계, 코드 작성, 테스트가 수행되었습니다.
아키텍처 결정, 참조 레포 분석, 코드 구현, 테스트 작성 전 과정에서 AI가 보조 도구로 사용되었습니다.

## 테스트

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## 라이선스

MIT
