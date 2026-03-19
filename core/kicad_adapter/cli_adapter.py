"""
KiCad CLI Adapter — kicad-cli 기반 Export/DRC/ERC

kicad-cli를 subprocess로 호출하여 실행
KiCad 9/10 모두 동일한 인터페이스

참조: Seeed validation.py 패턴
"""

from __future__ import annotations

import json
import subprocess
import tempfile
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


class CLIAdapter(AbstractKiCadAdapter):
    """
    kicad-cli 기반 Adapter

    주 용도:
    - DRC/ERC 실행
    - Gerber/PDF/SVG/3D 내보내기
    - 넷리스트 생성

    kicad-cli는 headless로 동작하며 별도 KiCad 인스턴스 불필요
    """

    def __init__(
        self,
        board_path: str = "",
        schematic_path: str = "",
        kicad_cli_path: str = "",
    ):
        self._board_path = board_path
        self._sch_path = schematic_path
        self._cli = kicad_cli_path or self._detect_kicad_cli()
        self._verify_cli()

    @staticmethod
    def _detect_kicad_cli() -> str:
        """OS별 kicad-cli 경로 자동 감지"""
        import shutil
        import platform

        # PATH에서 먼저 찾기
        found = shutil.which("kicad-cli")
        if found:
            return found

        system = platform.system()
        candidates = []
        if system == "Windows":
            candidates = [
                r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
                r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe",
                r"C:\Program Files (x86)\KiCad\9.0\bin\kicad-cli.exe",
            ]
        elif system == "Darwin":
            candidates = [
                "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
            ]
        elif system == "Linux":
            candidates = [
                "/usr/bin/kicad-cli",
                "/usr/local/bin/kicad-cli",
            ]

        for path in candidates:
            if Path(path).exists():
                return path

        return "kicad-cli"  # fallback to PATH

    def _verify_cli(self):
        """kicad-cli 사용 가능 여부 확인"""
        try:
            result = subprocess.run(
                [self._cli, "version"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
                errors="replace",
            )
            version = result.stdout.strip()
            logger.info(f"kicad-cli 감지: {version}")
        except FileNotFoundError:
            logger.warning(
                "kicad-cli를 찾을 수 없음. PATH에 kicad-cli가 있는지 확인하세요."
            )
        except Exception as e:
            logger.warning(f"kicad-cli 확인 실패: {e}")

    # ─── DRC/ERC ──────────────────────────────────────────

    def run_drc(self) -> list[DRCViolation]:
        """kicad-cli로 DRC 실행 (JSON 출력 파싱)"""
        if not self._board_path:
            raise ValueError("board_path가 설정되지 않음")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            report_path = tmp.name

        cmd = [
            self._cli,
            "pcb",
            "drc",
            "--format", "json",
            "--output", report_path,
            self._board_path,
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace"
            )
            logger.debug(f"DRC stdout: {result.stdout}")
            if result.returncode not in (0, 1):  # 1 = 위반 있음
                logger.warning(f"DRC stderr: {result.stderr}")

            return self._parse_drc_report(report_path)
        except subprocess.TimeoutExpired:
            logger.error("DRC 실행 타임아웃 (120초)")
            return []
        except Exception as e:
            logger.error(f"DRC 실행 실패: {e}")
            return []
        finally:
            Path(report_path).unlink(missing_ok=True)

    def run_erc(self) -> list[ERCViolation]:
        """kicad-cli로 ERC 실행"""
        sch_path = self._sch_path
        if not sch_path:
            raise ValueError("schematic_path가 설정되지 않음")

        # 루트 스키매틱 감지 (Seeed 패턴)
        root_sch = self._find_root_schematic(Path(sch_path))
        if root_sch:
            sch_path = str(root_sch)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            report_path = tmp.name

        cmd = [
            self._cli,
            "sch",
            "erc",
            "--format", "json",
            "--output", report_path,
            sch_path,
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace"
            )
            logger.debug(f"ERC stdout: {result.stdout}")
            return self._parse_erc_report(report_path)
        except subprocess.TimeoutExpired:
            logger.error("ERC 실행 타임아웃 (120초)")
            return []
        except Exception as e:
            logger.error(f"ERC 실행 실패: {e}")
            return []
        finally:
            Path(report_path).unlink(missing_ok=True)

    # ─── Export ────────────────────────────────────────────

    def export_gerber(self, output_dir: str, layers: list[str] | None = None) -> str:
        """Gerber 파일 내보내기"""
        if not self._board_path:
            raise ValueError("board_path가 설정되지 않음")

        Path(output_dir).mkdir(parents=True, exist_ok=True)

        cmd = [
            self._cli,
            "pcb",
            "export",
            "gerbers",
            "--output", output_dir,
            self._board_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(f"Gerber 내보내기 실패: {result.stderr}")

        # 드릴 파일도 생성
        drill_cmd = [
            self._cli,
            "pcb",
            "export",
            "drill",
            "--output", output_dir,
            self._board_path,
        ]
        subprocess.run(drill_cmd, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace")

        logger.info(f"Gerber 내보내기 완료: {output_dir}")
        return output_dir

    def export_pdf(self, output_path: str) -> str:
        """PDF 내보내기"""
        if not self._board_path:
            raise ValueError("board_path가 설정되지 않음")

        cmd = [
            self._cli,
            "pcb",
            "export",
            "pdf",
            "--output", output_path,
            self._board_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(f"PDF 내보내기 실패: {result.stderr}")

        logger.info(f"PDF 내보내기 완료: {output_path}")
        return output_path

    def export_step(self, output_path: str) -> str:
        """3D STEP 모델 내보내기"""
        if not self._board_path:
            raise ValueError("board_path가 설정되지 않음")

        cmd = [
            self._cli,
            "pcb",
            "export",
            "step",
            "--output", output_path,
            self._board_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(f"STEP 내보내기 실패: {result.stderr}")

        logger.info(f"STEP 내보내기 완료: {output_path}")
        return output_path

    def generate_netlist(self, output_path: str = "") -> str:
        """넷리스트 생성"""
        if not self._sch_path:
            raise ValueError("schematic_path가 설정되지 않음")

        if not output_path:
            output_path = str(Path(self._sch_path).with_suffix(".xml"))

        cmd = [
            self._cli,
            "sch",
            "export",
            "netlist",
            "--output", output_path,
            self._sch_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(f"넷리스트 생성 실패: {result.stderr}")

        return output_path

    def export_bom(self, output_path: str = "") -> str:
        """BOM 내보내기"""
        if not self._sch_path:
            raise ValueError("schematic_path가 설정되지 않음")

        if not output_path:
            output_path = str(Path(self._sch_path).with_suffix(".csv"))

        cmd = [
            self._cli,
            "sch",
            "export",
            "bom",
            "--output", output_path,
            self._sch_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(f"BOM 내보내기 실패: {result.stderr}")

        return output_path

    # ─── PCB/Schematic 조작 (미지원) ──────────────────────

    def get_board_info(self) -> BoardInfo:
        raise NotImplementedError("CLIAdapter는 조회 전용. IPCAdapter를 사용하세요.")

    def get_all_footprints(self) -> list[FootprintInfo]:
        raise NotImplementedError("CLIAdapter는 조회 전용")

    def get_footprint(self, reference) -> Optional[FootprintInfo]:
        raise NotImplementedError("CLIAdapter는 조회 전용")

    def place_footprint(self, reference, footprint_lib, pos, rotation=0.0, layer="F.Cu", value=""):
        raise NotImplementedError("CLIAdapter는 조회 전용")

    def move_footprint(self, reference, pos, rotation=0.0):
        raise NotImplementedError("CLIAdapter는 조회 전용")

    def delete_footprint(self, reference):
        raise NotImplementedError("CLIAdapter는 조회 전용")

    def add_track(self, start, end, width_mm, layer, net=""):
        raise NotImplementedError("CLIAdapter는 조회 전용")

    def add_via(self, pos, diameter_mm=0.8, drill_mm=0.4, net="", from_layer="F.Cu", to_layer="B.Cu"):
        raise NotImplementedError("CLIAdapter는 조회 전용")

    def add_zone(self, zone):
        raise NotImplementedError("CLIAdapter는 조회 전용")

    def get_all_nets(self) -> list[NetInfo]:
        raise NotImplementedError("CLIAdapter는 조회 전용")

    def get_all_symbols(self) -> list[SymbolInfo]:
        raise NotImplementedError("CLIAdapter는 조회 전용")

    def place_symbol(self, lib, symbol, pos, reference="", value="", rotation=0.0):
        raise NotImplementedError("CLIAdapter는 조회 전용")

    def add_wire(self, start, end):
        raise NotImplementedError("CLIAdapter는 조회 전용")

    def add_label(self, text, pos, label_type="local", orientation=0.0):
        raise NotImplementedError("CLIAdapter는 조회 전용")

    def get_netlist(self) -> dict:
        """kicad-cli로 넷리스트 생성 후 파싱"""
        path = self.generate_netlist()
        # XML 파싱은 별도 유틸리티
        return {"netlist_path": path}

    def refresh_view(self):
        pass

    def save(self):
        pass

    def close(self):
        pass

    # ─── 내부 헬퍼 ────────────────────────────────────────

    def _parse_drc_report(self, report_path: str) -> list[DRCViolation]:
        """DRC JSON 리포트 파싱"""
        try:
            data = json.loads(Path(report_path).read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return []

        violations = []
        for v in data.get("violations", []):
            pos = None
            if "pos" in v:
                pos = Position(v["pos"].get("x", 0), v["pos"].get("y", 0))

            violations.append(
                DRCViolation(
                    severity=v.get("severity", "error"),
                    violation_type=v.get("type", "unknown"),
                    description=v.get("description", ""),
                    position=pos,
                    items=v.get("items", []),
                )
            )
        return violations

    def _parse_erc_report(self, report_path: str) -> list[ERCViolation]:
        """ERC JSON 리포트 파싱"""
        try:
            data = json.loads(Path(report_path).read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return []

        violations = []
        for v in data.get("violations", []):
            violations.append(
                ERCViolation(
                    severity=v.get("severity", "error"),
                    violation_type=v.get("type", "unknown"),
                    description=v.get("description", ""),
                    components=v.get("items", []),
                )
            )
        return violations

    @staticmethod
    def _find_root_schematic(sch_path: Path) -> Optional[Path]:
        """
        루트 스키매틱 감지

        .kicad_pro 파일과 동일 이름의 .kicad_sch가 루트
        (Seeed validation.py 패턴)
        """
        directory = sch_path.parent
        for pro_file in directory.glob("*.kicad_pro"):
            root_sch = pro_file.with_suffix(".kicad_sch")
            if root_sch.exists():
                return root_sch
        return None
