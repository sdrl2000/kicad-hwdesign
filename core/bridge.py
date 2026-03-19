"""
MCP 서버 ↔ KiCad 플러그인 브릿지

MCP 서버에서 실시간 KiCad 조작이 필요한 경우
플러그인 리스너에 소켓으로 명령을 전달하고 결과를 받음.

플러그인이 실행 중이 아니면 파일 기반 fallback으로 동작.
"""

from __future__ import annotations

import json
import os
import socket

PLUGIN_SOCKET_PATH = "/tmp/hwdesign_plugin.sock"
TIMEOUT = 30.0


class PluginBridge:
    """MCP 서버 → KiCad 플러그인 통신 브릿지"""

    def __init__(self, socket_path: str = PLUGIN_SOCKET_PATH):
        self._socket_path = socket_path

    def is_plugin_running(self) -> bool:
        """플러그인 리스너가 실행 중인지 확인"""
        return os.path.exists(self._socket_path)

    def send(self, action: str, params: dict | None = None) -> dict:
        """
        플러그인에 명령 전달

        Args:
            action: 실행할 액션 (예: "place_symbol", "move_footprint")
            params: 액션 파라미터

        Returns:
            플러그인 실행 결과

        Raises:
            ConnectionError: 플러그인 미실행
        """
        if not self.is_plugin_running():
            raise ConnectionError(
                "KiCad 플러그인이 실행 중이 아닙니다. "
                "KiCad에서 hwdesign 플러그인을 활성화하세요."
            )

        request = {"action": action, "params": params or {}}
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)

        try:
            sock.connect(self._socket_path)
            sock.sendall((json.dumps(request) + "\n").encode())

            data = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break

            return json.loads(data.decode().strip())
        finally:
            sock.close()

    def send_or_fallback(self, action: str, params: dict, fallback_fn=None) -> dict:
        """
        플러그인에 전달 시도, 실패 시 fallback 함수 실행

        실시간 반영이 가능하면 플러그인으로,
        플러그인이 꺼져 있으면 파일 기반으로 동작.
        """
        try:
            return self.send(action, params)
        except (ConnectionError, OSError):
            if fallback_fn:
                return fallback_fn(params)
            return {
                "status": "fallback",
                "message": "플러그인 미실행. 파일 기반으로 처리됨. KiCad에서 리로드 필요.",
            }
