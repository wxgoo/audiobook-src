"""音频批量转码——工具箱内置工具的注册壳。

实际的页面在 app/src/pages/toolbox/audio_transcode.vue（/toolbox/audio_transcode），
后端 API 在 webserver/handlers/toolbox.py（/api/toolbox/audio_transcode/*），
业务逻辑在 webserver/services/audio_transcode.py。

这里只提供 info() 供 ToolSet 注册，让工具出现在 /admin/toolbox 列表里。
点卡片 goToTool 跳静态页，与其它内置工具（如 author_clean）一致。
之所以要补这一层，是因为这工具最早直接挂在管理菜单里，没走工具箱体系；
菜单入口保留（老用户习惯），工具箱里也能看到，两边不冲突。
"""


class AudioTranscodeTool:
    @staticmethod
    def info() -> dict:
        return {
            "tool_id": "audio_transcode",
            "name": "音频转码",
            "description": "把有声书 .audio/ 里的 mp3 批量转成 m4a（AAC），洗掉杂乱 ID3 标签并做流式播放优化，成功后删除原 mp3",
            "revision": "0.1.0",
            "author": "MyBooks",
            "publish_date": "2026-11-04",
        }
