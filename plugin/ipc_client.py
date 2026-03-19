"""
hwdesign-core 서버와의 IPC 클라이언트

JSON over Unix socket 통신
"""

from __future__ import annotations

import json
import socket
import uuid
from typing import Optional

SOCKET_PATH = "/tmp/hwdesign.sock"
TIMEOUT = 30.0


class IPCClient:
    """hwdesign-core 서버 IPC 클라이언트"""

    def __init__(self, socket_path: str = SOCKET_PATH):
        self._socket_path = socket_path

    def send_request(self, action: str, params: dict | None = None) -> dict:
        """
        core 서버에 요청 전송 및 응답 수신

        Args:
            action: 액션명 (예: "generate_schematic", "optimize_placement")
            params: 액션 파라미터

        Returns:
            서버 응답 dict
        """
        request = {
            "id": str(uuid.uuid4()),
            "action": action,
            "params": params or {},
        }

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)

        try:
            sock.connect(self._socket_path)
            # 요청 전송 (줄바꿈으로 메시지 구분)
            sock.sendall((json.dumps(request) + "\n").encode())

            # 응답 수신
            response_data = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                response_data += chunk
                if b"\n" in response_data:
                    break

            response = json.loads(response_data.decode().strip())
            return response

        except FileNotFoundError:
            return {
                "status": "error",
                "error": f"hwdesign-core 서버 미실행. 소켓 경로: {self._socket_path}",
            }
        except socket.timeout:
            return {"status": "error", "error": "요청 타임아웃"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
        finally:
            sock.close()

    def ping(self) -> bool:
        """서버 연결 확인"""
        try:
            resp = self.send_request("ping")
            return resp.get("status") == "ok"
        except Exception:
            return False

    # ─── 편의 메서드 ──────────────────────────────────────

    def generate_schematic(self, prompt: str) -> dict:
        return self.send_request("generate_schematic", {"prompt": prompt})

    def optimize_placement(
        self, board_path: str, strategy: str = "hybrid", generations: int = 100
    ) -> dict:
        return self.send_request(
            "optimize_placement",
            {"board_path": board_path, "strategy": strategy, "generations": generations},
        )

    def route_board(self, board_path: str, method: str = "adaptive") -> dict:
        return self.send_request(
            "route_board", {"board_path": board_path, "method": method}
        )

    def search_component(self, query: str, limit: int = 10) -> dict:
        return self.send_request(
            "search_component", {"query": query, "limit": limit}
        )

    def run_drc(self, board_path: str) -> dict:
        return self.send_request("run_drc", {"board_path": board_path})

    def run_erc(self, schematic_path: str) -> dict:
        return self.send_request("run_erc", {"schematic_path": schematic_path})

    def export_gerber(self, board_path: str, output_dir: str) -> dict:
        return self.send_request(
            "export_gerber", {"board_path": board_path, "output_dir": output_dir}
        )

    def review_design(
        self, board_path: str, drc_results: list = None, erc_results: list = None
    ) -> dict:
        return self.send_request(
            "review_design",
            {
                "board_path": board_path,
                "drc_results": drc_results or [],
                "erc_results": erc_results or [],
            },
        )
