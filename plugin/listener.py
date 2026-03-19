"""
KiCad 플러그인 백그라운드 소켓 리스너

MCP 서버로부터 JSON 명령을 수신하여
SWIG/IPC로 KiCad 내부에서 실시간 실행.

싱글턴 패턴 — KiCad 프로세스당 하나만 실행.
"""

from __future__ import annotations

import json
import os
import socket
import threading
from typing import Optional

PLUGIN_SOCKET_PATH = "/tmp/hwdesign_plugin.sock"


class PluginListener:
    """
    백그라운드 소켓 리스너

    MCP 서버가 이 소켓에 JSON 명령을 보내면
    executor가 KiCad 내부에서 SWIG/IPC로 실행.
    """

    _instance: Optional["PluginListener"] = None

    @classmethod
    def get_instance(cls) -> "PluginListener":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, socket_path: str = PLUGIN_SOCKET_PATH):
        self._socket_path = socket_path
        self._server_socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def start(self):
        """백그라운드 리스너 시작"""
        if self._running:
            return

        # 기존 소켓 파일 정리
        if os.path.exists(self._socket_path):
            os.unlink(self._socket_path)

        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_socket.bind(self._socket_path)
        self._server_socket.listen(5)
        self._server_socket.settimeout(1.0)  # 1초마다 중지 체크

        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """리스너 중지"""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
        if os.path.exists(self._socket_path):
            try:
                os.unlink(self._socket_path)
            except Exception:
                pass

    def _listen_loop(self):
        """메인 리스닝 루프 (백그라운드 스레드)"""
        while self._running:
            try:
                conn, _ = self._server_socket.accept()
                # 각 연결을 별도 스레드에서 처리
                threading.Thread(
                    target=self._handle_connection,
                    args=(conn,),
                    daemon=True,
                ).start()
            except socket.timeout:
                continue
            except OSError:
                break

    def _handle_connection(self, conn: socket.socket):
        """클라이언트 연결 처리"""
        try:
            conn.settimeout(30.0)
            data = b""
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break

            if data:
                request = json.loads(data.decode().strip())
                response = self._execute(request)
                conn.sendall((json.dumps(response) + "\n").encode())
        except Exception as e:
            try:
                error_resp = {"status": "error", "error": str(e)}
                conn.sendall((json.dumps(error_resp) + "\n").encode())
            except Exception:
                pass
        finally:
            conn.close()

    def _execute(self, request: dict) -> dict:
        """
        명령 실행 — KiCad 메인 스레드에서 SWIG/IPC 호출

        wx.CallAfter를 사용하여 KiCad GUI 스레드에서 안전하게 실행.
        SWIG 호출은 반드시 메인 스레드에서 해야 함.
        """
        from .executor import PluginExecutor

        action = request.get("action", "")
        params = request.get("params", {})

        try:
            executor = PluginExecutor()
            result = executor.execute(action, params)
            return {"status": "ok", "result": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}
