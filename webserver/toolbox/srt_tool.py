"""音频转写文稿（SRT 字幕生成）——工具箱内置工具。

实际的页面在 app/src/pages/toolbox/srt_tool.vue（/toolbox/srt_tool），
后端 API 在 webserver/handlers/toolbox.py（/api/toolbox/srt_tool/*），
业务逻辑在 webserver/services/srt_transcribe.py（识别内核复用
仓库根 srt-tool/srt_core.py，与 PC 版 make_srt_gui.exe 同源）。

这里只提供 info() 供 ToolSet 注册，让工具出现在 /admin/toolbox 列表里。
依赖 faster-whisper（requirements-optional.txt）；未安装时页面给出
降级提示（改用 PC 版 srt-tool）。
"""


class SrtTool:
    @staticmethod
    def info() -> dict:
        return {
            "tool_id": "srt_tool",
            "name": "音频转写文稿",
            "description": "选择书籍，把 .audio/ 里的音频用 faster-whisper 批量转写成同名 .srt 字幕，网页播放器自动加载；支持后台运行与取消",
            "revision": "1.2.0",
            "author": "MyBooks",
            "publish_date": "2026-11-07",
        }
