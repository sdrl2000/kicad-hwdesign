"""
디바이스 트리 생성기 — Seeed device_tree.py 참조

스키매틱에서 MCU + 주변장치 정보를 추출하여
Linux Device Tree Source (.dts) 파일 생성

지원 SoC: STM32, ESP32, nRF52
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

from .pin_analyzer import PinAnalyzer, PinFunction


# 디바이스 트리 바인딩 데이터베이스 (Seeed 참조)
DEVICE_BINDINGS: dict[str, dict] = {
    # 센서
    "BMP280": {"compatible": "bosch,bmp280", "bus": "i2c", "addr": "0x76"},
    "BME280": {"compatible": "bosch,bme280", "bus": "i2c", "addr": "0x76"},
    "MPU6050": {"compatible": "invensense,mpu6050", "bus": "i2c", "addr": "0x68"},
    "MPU9250": {"compatible": "invensense,mpu9250", "bus": "i2c", "addr": "0x68"},
    "LSM6DS3": {"compatible": "st,lsm6ds3", "bus": "i2c", "addr": "0x6a"},
    "HTS221": {"compatible": "st,hts221", "bus": "i2c", "addr": "0x5f"},
    # 디스플레이
    "ST7789": {"compatible": "sitronix,st7789v", "bus": "spi"},
    "ST7735": {"compatible": "sitronix,st7735r", "bus": "spi"},
    "ILI9341": {"compatible": "ilitek,ili9341", "bus": "spi"},
    "SSD1306": {"compatible": "solomon,ssd1306", "bus": "i2c", "addr": "0x3c"},
    "SH1106": {"compatible": "sinowealth,sh1106", "bus": "i2c", "addr": "0x3c"},
    # 메모리
    "AT24C256": {"compatible": "atmel,24c256", "bus": "i2c", "addr": "0x50"},
    "W25Q128": {"compatible": "jedec,spi-nor", "bus": "spi"},
    # 무선
    "NRF24L01": {"compatible": "nordic,nrf24", "bus": "spi"},
    "SX1278": {"compatible": "semtech,sx1278", "bus": "spi"},
    # USB 시리얼
    "CP2102": {"compatible": "silabs,cp2102", "bus": "usb"},
    "CH340G": {"compatible": "wch,ch340", "bus": "usb"},
    # 전원
    "AXP192": {"compatible": "x-powers,axp192", "bus": "i2c", "addr": "0x34"},
}

# SoC별 디바이스 트리 기본 구조
SOC_DTS_TEMPLATES: dict[str, str] = {
    "stm32": """/dts-v1/;
#include "stm32f4xx.dtsi"

/ {{
    model = "{board_name}";
    compatible = "st,stm32f4";

    chosen {{
        stdout-path = &usart1;
    }};

{peripherals}
}};
""",
    "esp32": """/dts-v1/;

/ {{
    model = "{board_name}";
    compatible = "espressif,esp32";

{peripherals}
}};
""",
    "nrf52": """/dts-v1/;
#include <nordic/nrf52840_qiaa.dtsi>

/ {{
    model = "{board_name}";
    compatible = "nordic,nrf52840";

    chosen {{
        zephyr,console = &uart0;
    }};

{peripherals}
}};
""",
}


@dataclass
class PeripheralConfig:
    """주변장치 설정"""
    name: str
    compatible: str
    bus_type: str  # i2c, spi, uart, gpio
    bus_instance: int = 0
    address: str = ""
    properties: dict = field(default_factory=dict)


@dataclass
class DeviceTreeResult:
    """디바이스 트리 생성 결과"""
    dts_content: str
    peripherals: list[PeripheralConfig]
    soc_family: str
    output_path: str = ""


class DeviceTreeGenerator:
    """
    Linux Device Tree Source (.dts) 생성기

    스키매틱의 넷리스트에서 MCU + 주변장치를 분석하여
    디바이스 트리를 자동 생성
    """

    def __init__(self):
        self.pin_analyzer = PinAnalyzer()

    def generate(
        self,
        components: list[dict],
        nets: dict[str, list[str]],
        board_name: str = "hwdesign-board",
        target_soc: str = "",
    ) -> DeviceTreeResult:
        """
        디바이스 트리 생성

        Args:
            components: 컴포넌트 목록 [{"reference": "U1", "value": "STM32H743VIT6", ...}]
            nets: 넷 정보 {"net_name": ["U1.pin1", "U2.pin2"]}
            board_name: 보드 이름
            target_soc: 타겟 SoC 패밀리 (자동 감지 가능)

        Returns:
            DeviceTreeResult
        """
        # MCU 감지
        soc = target_soc
        if not soc:
            soc = self._detect_soc(components)
        if not soc:
            soc = "stm32"
            logger.warning("MCU를 감지할 수 없음. 기본값 stm32 사용")

        # 주변장치 감지
        peripherals = self._detect_peripherals(components, nets)

        # DTS 생성
        peripheral_nodes = self._generate_peripheral_nodes(peripherals)
        template = SOC_DTS_TEMPLATES.get(soc, SOC_DTS_TEMPLATES["stm32"])
        dts_content = template.format(
            board_name=board_name,
            peripherals=peripheral_nodes,
        )

        logger.info(f"디바이스 트리 생성: {soc}, {len(peripherals)}개 주변장치")
        return DeviceTreeResult(
            dts_content=dts_content,
            peripherals=peripherals,
            soc_family=soc,
        )

    def save(self, result: DeviceTreeResult, output_path: str) -> str:
        """DTS 파일 저장"""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(result.dts_content, encoding="utf-8")
        result.output_path = output_path
        logger.info(f"DTS 저장: {output_path}")
        return output_path

    def _detect_soc(self, components: list[dict]) -> Optional[str]:
        for comp in components:
            value = comp.get("value", "")
            family = self.pin_analyzer.detect_mcu_family(value)
            if family:
                return family
        return None

    def _detect_peripherals(
        self, components: list[dict], nets: dict[str, list[str]]
    ) -> list[PeripheralConfig]:
        peripherals = []
        for comp in components:
            value = comp.get("value", "").upper()
            for part_name, binding in DEVICE_BINDINGS.items():
                if part_name.upper() in value:
                    bus_instance = self._infer_bus_instance(comp, nets, binding["bus"])
                    peripherals.append(PeripheralConfig(
                        name=part_name.lower(),
                        compatible=binding["compatible"],
                        bus_type=binding["bus"],
                        bus_instance=bus_instance,
                        address=binding.get("addr", ""),
                    ))
                    break
        return peripherals

    def _infer_bus_instance(self, comp: dict, nets: dict, bus_type: str) -> int:
        """넷 이름에서 버스 인스턴스 번호 추론"""
        ref = comp.get("reference", "")
        for net_name, pins in nets.items():
            if any(ref in p for p in pins):
                match = re.search(rf"{bus_type}(\d+)", net_name, re.IGNORECASE)
                if match:
                    return int(match.group(1))
        return 0

    def _generate_peripheral_nodes(self, peripherals: list[PeripheralConfig]) -> str:
        """주변장치 DTS 노드 생성"""
        nodes = []
        for p in peripherals:
            if p.bus_type == "i2c" and p.address:
                node = (
                    f"    &i2c{p.bus_instance} {{\n"
                    f"        status = \"okay\";\n"
                    f"        {p.name}@{p.address[2:]} {{\n"
                    f"            compatible = \"{p.compatible}\";\n"
                    f"            reg = <{p.address}>;\n"
                    f"        }};\n"
                    f"    }};\n"
                )
            elif p.bus_type == "spi":
                node = (
                    f"    &spi{p.bus_instance} {{\n"
                    f"        status = \"okay\";\n"
                    f"        {p.name}@0 {{\n"
                    f"            compatible = \"{p.compatible}\";\n"
                    f"            reg = <0>;\n"
                    f"            spi-max-frequency = <10000000>;\n"
                    f"        }};\n"
                    f"    }};\n"
                )
            else:
                continue
            nodes.append(node)
        return "\n".join(nodes)


# 순환 import 방지
import re  # noqa: E402
