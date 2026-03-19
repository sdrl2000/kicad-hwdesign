"""
KiCad ActionPlugin 진입점

hwdesign 백그라운드 리스너를 시작하여
MCP 서버로부터 소켓 명령을 받아 SWIG/IPC로 실시간 실행.

~/.local/share/kicad/9.0/scripting/plugins/ 에 심링크 필요
macOS: ~/Library/Application Support/kicad/9.0/scripting/plugins/
"""

import os
import sys

try:
    import pcbnew

    class HWDesignPlugin(pcbnew.ActionPlugin):

        def defaults(self):
            self.name = "hwdesign"
            self.category = "AI Hardware Design"
            self.description = "AI 기반 하드웨어 설계 자동화 (MCP 리스너)"
            self.show_toolbar_button = True
            icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
            if os.path.exists(icon_path):
                self.icon_file_name = icon_path

        def Run(self):
            """플러그인 실행 — 백그라운드 리스너 시작/중지 토글"""
            from .listener import PluginListener

            try:
                listener = PluginListener.get_instance()
                if listener.is_running():
                    listener.stop()
                    self._show_message("hwdesign 리스너 중지됨")
                else:
                    listener.start()
                    self._show_message(
                        "hwdesign 리스너 시작됨\n"
                        "Claude Desktop에서 MCP 도구를 호출하면\n"
                        "KiCad에 실시간 반영됩니다."
                    )
            except Exception as e:
                self._show_message(f"hwdesign 오류:\n{str(e)}", error=True)

        def _show_message(self, msg: str, error: bool = False):
            try:
                import wx
                style = wx.OK | (wx.ICON_ERROR if error else wx.ICON_INFORMATION)
                wx.MessageBox(msg, "hwdesign", style)
            except ImportError:
                print(msg)

    HWDesignPlugin().register()

except ImportError:
    pass
