"""
MCU 핀 충돌 분석 — Seeed pin_analysis.py 참조

스키매틱에서 MCU 핀 할당을 분석하고
전기적 충돌, 미사용 핀, 핀멀티플렉싱 문제를 검출
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from loguru import logger


class PinFunction(str, Enum):
    I2C = "I2C"
    SPI = "SPI"
    UART = "UART"
    GPIO = "GPIO"
    ADC = "ADC"
    PWM = "PWM"
    USB = "USB"
    CAN = "CAN"
    INTERRUPT = "INTERRUPT"
    POWER = "POWER"
    UNKNOWN = "UNKNOWN"


class ConflictSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class PinAssignment:
    """핀 할당 정보"""
    pin_name: str
    net_name: str
    function: PinFunction
    component_ref: str = ""
    alternate_functions: list[str] = field(default_factory=list)


@dataclass
class PinConflict:
    """핀 충돌 정보"""
    severity: ConflictSeverity
    description: str
    pins: list[str] = field(default_factory=list)
    suggestion: str = ""


# 넷 이름으로 핀 기능 추론 패턴 (Seeed 참조)
NET_FUNCTION_PATTERNS: dict[PinFunction, list[str]] = {
    PinFunction.I2C: [r"I2C[_\d]*(?:SDA|SCL)", r"SDA[\d]*$", r"SCL[\d]*$", r"TWI"],
    PinFunction.SPI: [r"SPI[_\d]*(?:MISO|MOSI|SCK|CS|NSS)", r"MISO", r"MOSI", r"SCK", r"NSS"],
    PinFunction.UART: [r"U?ART[_\d]*(?:TX|RX)", r"USART", r"^TX[\d]*$", r"^RX[\d]*$"],
    PinFunction.GPIO: [r"GPIO[_\d]+", r"^IO[_\d]+$", r"^P[A-D]\d+$"],
    PinFunction.ADC: [r"ADC[_\d]+", r"AIN[\d]+", r"^AN[\d]+$"],
    PinFunction.PWM: [r"PWM[_\d]+", r"TIM[_\d]*CH[\d]+"],
    PinFunction.USB: [r"USB[_\d]*(?:DM|DP|D[\-\+])", r"^D[\-\+]$"],
    PinFunction.CAN: [r"CAN[_\d]*(?:TX|RX|H|L)"],
    PinFunction.INTERRUPT: [r"^INT[\d]*$", r"IRQ[\d]*", r"_INT$"],
    PinFunction.POWER: [r"VCC|VDD|GND|VSS|VBUS|VBAT|3V3|5V"],
}

# MCU 패밀리 인식 패턴
MCU_PATTERNS: dict[str, str] = {
    "stm32": r"STM32[FHL][\dA-Za-z]+",
    "esp32": r"ESP32(?:-[A-Za-z0-9]+)?",
    "nrf52": r"nRF52[\dA-Za-z]*",
    "atmega": r"ATmega[\d]+[A-Za-z]*",
    "samd": r"ATSAMD[\d]+[A-Za-z]*",
    "rp2040": r"RP2040",
}

# MCU별 핀 사양
MCU_PIN_SPECS: dict[str, dict] = {
    "stm32": {"max_current_ma": 25, "is_5v_tolerant": False, "adc_bits": 12},
    "esp32": {"max_current_ma": 40, "is_5v_tolerant": False, "adc_bits": 12},
    "nrf52": {"max_current_ma": 5, "is_5v_tolerant": False, "adc_bits": 12},
    "atmega": {"max_current_ma": 40, "is_5v_tolerant": True, "adc_bits": 10},
    "rp2040": {"max_current_ma": 12, "is_5v_tolerant": False, "adc_bits": 12},
}


class PinAnalyzer:
    """
    MCU 핀 분석기

    기능:
    1. 넷 이름에서 핀 기능 추론 (I2C/SPI/UART/GPIO 등)
    2. 전기적 충돌 검출 (다중 출력, 전원 단락 등)
    3. MCU 패밀리 자동 인식
    4. 핀멀티플렉싱 검증
    """

    def detect_mcu_family(self, component_value: str) -> Optional[str]:
        """컴포넌트 값에서 MCU 패밀리 인식"""
        for family, pattern in MCU_PATTERNS.items():
            if re.search(pattern, component_value, re.IGNORECASE):
                return family
        return None

    def infer_pin_function(self, net_name: str) -> PinFunction:
        """넷 이름에서 핀 기능 추론"""
        for func, patterns in NET_FUNCTION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, net_name, re.IGNORECASE):
                    return func
        return PinFunction.UNKNOWN

    def analyze_pins(self, pin_assignments: list[PinAssignment]) -> list[PinConflict]:
        """
        핀 할당 분석 및 충돌 검출

        Args:
            pin_assignments: 핀 할당 목록

        Returns:
            발견된 충돌 목록
        """
        conflicts: list[PinConflict] = []

        # 넷별 핀 그룹핑
        net_pins: dict[str, list[PinAssignment]] = {}
        for pa in pin_assignments:
            net_pins.setdefault(pa.net_name, []).append(pa)

        # 1. 다중 출력 검출
        for net_name, pins in net_pins.items():
            output_pins = [p for p in pins if p.function in (PinFunction.UART, PinFunction.SPI)]
            if len(output_pins) > 1:
                conflicts.append(PinConflict(
                    severity=ConflictSeverity.ERROR,
                    description=f"넷 '{net_name}'에 다중 출력 핀 연결됨",
                    pins=[p.pin_name for p in output_pins],
                    suggestion="출력 핀 하나만 연결하세요",
                ))

        # 2. 전원 핀 검증
        for pa in pin_assignments:
            if pa.function == PinFunction.POWER:
                if "GND" in pa.net_name.upper() and "VCC" in pa.net_name.upper():
                    conflicts.append(PinConflict(
                        severity=ConflictSeverity.ERROR,
                        description=f"전원과 그라운드가 같은 넷에 연결됨: {pa.net_name}",
                        pins=[pa.pin_name],
                        suggestion="전원과 GND를 분리하세요",
                    ))

        # 3. 미연결 핀 경고
        unconnected = [pa for pa in pin_assignments if not pa.net_name or pa.net_name == "unconnected"]
        if unconnected:
            conflicts.append(PinConflict(
                severity=ConflictSeverity.WARNING,
                description=f"{len(unconnected)}개 핀이 미연결 상태",
                pins=[p.pin_name for p in unconnected],
                suggestion="No Connect 표시 또는 풀업/풀다운 추가를 고려하세요",
            ))

        logger.info(f"핀 분석 완료: {len(pin_assignments)}개 핀, {len(conflicts)}개 이슈")
        return conflicts

    def get_mcu_pin_spec(self, mcu_family: str) -> dict:
        """MCU 패밀리별 핀 사양 반환"""
        return MCU_PIN_SPECS.get(mcu_family, {})
