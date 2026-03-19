"""
hwdesign-core 서버 자동 시작/종료 관리
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

SOCKET_PATH = "/tmp/hwdesign.sock"
PID_FILE = "/tmp/hwdesign.pid"


def ensure_core_running() -> None:
    """core 서버가 실행 중인지 확인하고, 없으면 자동 시작"""
    if is_core_running():
        return

    # hwdesign-core venv의 Python으로 서버 시작
    core_dir = os.path.join(os.path.dirname(__file__), "..", "core")
    project_root = os.path.dirname(os.path.dirname(__file__))
    venv_python = os.path.join(project_root, ".venv", "bin", "python")

    # venv가 없으면 시스템 Python 사용
    if not os.path.exists(venv_python):
        venv_python = sys.executable

    proc = subprocess.Popen(
        [venv_python, "-m", "core.main"],
        cwd=project_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # PID 파일 저장
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))

    # 서버 기동 대기 (최대 10초)
    for _ in range(100):
        if is_core_running():
            return
        time.sleep(0.1)

    raise RuntimeError("hwdesign-core 서버 시작 실패 (10초 타임아웃)")


def is_core_running() -> bool:
    """소켓 파일 존재 여부로 서버 실행 상태 확인"""
    return os.path.exists(SOCKET_PATH)


def stop_core() -> None:
    """core 서버 종료"""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            os.kill(pid, 15)  # SIGTERM
        except (FileNotFoundError, ValueError, ProcessLookupError):
            pass
        finally:
            if os.path.exists(PID_FILE):
                os.unlink(PID_FILE)
            if os.path.exists(SOCKET_PATH):
                os.unlink(SOCKET_PATH)
