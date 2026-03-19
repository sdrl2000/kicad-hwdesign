"""
hwdesign-core 설정 관리
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class AIConfig:
    """AI 설정"""
    anthropic_api_key: str = ""
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 4096

    # 로컬 LLM fallback
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:32b"
    use_local_llm: bool = False

    def __post_init__(self):
        if not self.anthropic_api_key:
            self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")


@dataclass
class ServerConfig:
    """서버 설정"""
    socket_path: str = "/tmp/hwdesign.sock"
    max_workers: int = 4
    log_level: str = "INFO"

    def __post_init__(self):
        self.socket_path = os.environ.get("HWDESIGN_SOCKET_PATH", self.socket_path)
        self.max_workers = int(os.environ.get("HWDESIGN_MAX_WORKERS", self.max_workers))
        self.log_level = os.environ.get("HWDESIGN_LOG_LEVEL", self.log_level)


@dataclass
class SearchConfig:
    """부품 검색 API 설정"""
    mouser_api_key: str = ""
    digikey_client_id: str = ""
    digikey_client_secret: str = ""

    # 검색 우선순위: LCSC → Mouser → DigiKey → web_search
    search_priority: list[str] = field(
        default_factory=lambda: ["lcsc", "mouser", "digikey", "web"]
    )

    def __post_init__(self):
        self.mouser_api_key = os.environ.get("MOUSER_API_KEY", "")
        self.digikey_client_id = os.environ.get("DIGIKEY_CLIENT_ID", "")
        self.digikey_client_secret = os.environ.get("DIGIKEY_CLIENT_SECRET", "")


@dataclass
class KiCadConfig:
    """KiCad 관련 설정"""
    # KiCad 설치 경로 (자동 감지)
    kicad_path: str = ""
    kicad_version: str = "9.0"

    # 라이브러리 경로
    symbol_lib_path: str = ""
    footprint_lib_path: str = ""

    # API 모드
    prefer_ipc: bool = True  # IPC 우선, fallback SWIG

    def __post_init__(self):
        self._detect_kicad_paths()

    def _detect_kicad_paths(self):
        """OS별 KiCad 경로 자동 감지"""
        import platform

        system = platform.system()

        if system == "Darwin":  # macOS
            default_kicad = "/Applications/KiCad/KiCad.app"
            default_lib = Path.home() / "Library/Preferences/kicad" / self.kicad_version
            default_sym = os.environ.get(
                "KICAD9_SYMBOL_DIR",
                "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols",
            )
            default_fp = os.environ.get(
                "KICAD9_FOOTPRINT_DIR",
                "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints",
            )
        elif system == "Linux":
            default_kicad = "/usr/bin/kicad"
            default_lib = Path.home() / ".config/kicad" / self.kicad_version
            default_sym = os.environ.get(
                "KICAD9_SYMBOL_DIR", "/usr/share/kicad/symbols"
            )
            default_fp = os.environ.get(
                "KICAD9_FOOTPRINT_DIR", "/usr/share/kicad/footprints"
            )
        elif system == "Windows":
            default_kicad = r"C:\Program Files\KiCad\9.0\bin\kicad.exe"
            default_lib = Path.home() / "AppData/Roaming/kicad" / self.kicad_version
            default_sym = os.environ.get(
                "KICAD9_SYMBOL_DIR",
                r"C:\Program Files\KiCad\9.0\share\kicad\symbols",
            )
            default_fp = os.environ.get(
                "KICAD9_FOOTPRINT_DIR",
                r"C:\Program Files\KiCad\9.0\share\kicad\footprints",
            )
        else:
            default_kicad = ""
            default_sym = ""
            default_fp = ""

        if not self.kicad_path:
            self.kicad_path = default_kicad
        if not self.symbol_lib_path:
            self.symbol_lib_path = default_sym
        if not self.footprint_lib_path:
            self.footprint_lib_path = default_fp


@dataclass
class HWDesignConfig:
    """hwdesign 통합 설정"""
    ai: AIConfig = field(default_factory=AIConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    kicad: KiCadConfig = field(default_factory=KiCadConfig)

    @classmethod
    def from_env(cls) -> "HWDesignConfig":
        """환경 변수에서 설정 로드"""
        return cls()
