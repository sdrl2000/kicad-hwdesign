"""
IPC-7351 기준 풋프린트 자동 생성

rjwalters/kicad-tools library/generators/ 직접 import
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger


@dataclass
class FootprintSpec:
    """풋프린트 생성 스펙 (데이터시트에서 파싱)"""
    package_type: str          # SOIC, QFP, QFN, SOT, BGA, chip, DIP
    pins: int
    pitch: float = 0.0        # mm
    body_width: float = 0.0   # mm
    body_length: float = 0.0  # mm
    body_size: float = 0.0    # mm (정사각형 패키지)
    pad_width: float = 0.0    # mm
    pad_height: float = 0.0   # mm
    exposed_pad: float = 0.0  # mm (열방출 패드)
    name: str = ""             # 커스텀 이름


class FootprintGenerator:
    """
    IPC-7351 기준 풋프린트 자동 생성기

    rjwalters의 generators 모듈을 직접 호출:
    - create_soic: SOIC-4 ~ SOIC-28
    - create_qfp: LQFP-8 ~ LQFP-200+
    - create_qfn: QFN-4 ~ QFN-64+
    - create_sot: SOT-23, SOT-223 등
    - create_chip: 0402, 0603, 0805 등
    - create_bga: BGA 패키지
    - create_dip: DIP through-hole
    """

    GENERATORS: dict[str, str] = {
        "SOIC": "create_soic",
        "QFP": "create_qfp",
        "LQFP": "create_qfp",
        "TQFP": "create_qfp",
        "QFN": "create_qfn",
        "DFN": "create_dfn",
        "SOT": "create_sot",
        "chip": "create_chip",
        "0402": "create_chip",
        "0603": "create_chip",
        "0805": "create_chip",
        "1206": "create_chip",
        "BGA": "create_bga",
        "DIP": "create_dip",
    }

    def __init__(self):
        self._check_dependencies()

    def _check_dependencies(self):
        try:
            from kicad_tools.library.generators import create_soic

            self._available = True
        except ImportError:
            logger.warning("kicad-tools 미설치. 풋프린트 생성 불가")
            self._available = False

    def generate(self, spec: FootprintSpec, output_dir: str = "/tmp") -> str:
        """
        풋프린트 생성 및 .kicad_mod 파일 저장

        Args:
            spec: 풋프린트 스펙
            output_dir: 출력 디렉토리

        Returns:
            생성된 .kicad_mod 파일 경로
        """
        if not self._available:
            raise RuntimeError("kicad-tools가 설치되지 않음")

        import kicad_tools.library.generators as gen

        func_name = self.GENERATORS.get(spec.package_type)
        if not func_name:
            raise ValueError(
                f"지원하지 않는 패키지: {spec.package_type}. "
                f"지원 목록: {list(self.GENERATORS.keys())}"
            )

        generator = getattr(gen, func_name)

        # 파라미터 구성
        kwargs = {"pins": spec.pins}

        if spec.pitch > 0:
            kwargs["pitch"] = spec.pitch
        if spec.body_width > 0:
            kwargs["body_width"] = spec.body_width
        if spec.body_length > 0:
            kwargs["body_length"] = spec.body_length
        if spec.body_size > 0:
            kwargs["body_size"] = spec.body_size
        if spec.pad_width > 0:
            kwargs["pad_width"] = spec.pad_width
        if spec.pad_height > 0:
            kwargs["pad_height"] = spec.pad_height
        if spec.name:
            kwargs["name"] = spec.name

        # QFN 전용: exposed_pad
        if spec.package_type in ("QFN", "DFN") and spec.exposed_pad > 0:
            kwargs["exposed_pad"] = spec.exposed_pad

        # 풋프린트 생성
        fp = generator(**kwargs)

        # 저장
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        fp_name = spec.name or f"{spec.package_type}-{spec.pins}"
        out_path = str(Path(output_dir) / f"{fp_name}.kicad_mod")
        fp.save(out_path)

        logger.info(f"풋프린트 생성: {out_path}")
        return out_path

    def generate_from_datasheet(
        self, datasheet_path: str, output_dir: str = "/tmp"
    ) -> list[str]:
        """
        데이터시트에서 패키지 정보 파싱 후 풋프린트 자동 생성

        rjwalters DatasheetParser를 사용하여 PDF에서
        패키지 치수를 추출하고 IPC-7351 풋프린트 생성

        Returns:
            생성된 .kicad_mod 파일 경로 목록
        """
        if not self._available:
            raise RuntimeError("kicad-tools가 설치되지 않음")

        try:
            from kicad_tools.datasheet import DatasheetParser
        except ImportError:
            raise RuntimeError(
                "데이터시트 파싱 의존성 미설치. "
                "pip install kicad-tools[datasheet]"
            )

        parser = DatasheetParser(datasheet_path)
        parsed = parser.parse()

        generated = []
        # 데이터시트에서 추출된 패키지 정보로 풋프린트 생성
        # TODO: 파싱 결과에서 FootprintSpec 자동 변환
        logger.info(f"데이터시트 파싱 완료: {parsed.page_count}페이지")

        return generated

    @staticmethod
    def list_supported_packages() -> dict[str, str]:
        """지원되는 패키지 타입 목록"""
        return {
            "SOIC": "Small Outline IC (SOIC-4 ~ SOIC-28)",
            "QFP": "Quad Flat Package (LQFP/TQFP)",
            "QFN": "Quad Flat No-lead (thermal pad 옵션)",
            "DFN": "Dual Flat No-lead",
            "SOT": "Small Outline Transistor (SOT-23, SOT-223 등)",
            "chip": "Chip resistor/capacitor (0402~1206)",
            "BGA": "Ball Grid Array",
            "DIP": "Dual In-line Package (through-hole)",
        }
