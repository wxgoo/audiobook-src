# 移除旧布局 audios 目录（4.6.0-15）

4.6.0-13 起音频统一放在书目录内的 `.audio/`（`library/<作者>/<书名> (id)/.audio/`），
**4.6.0-15 起旧布局 `audiobook-data/books/audios/<book_id>/` 不再被读取**。
本文说明如何确认旧目录已空、如何手工迁移残留音频、以及如何删掉整个旧目录。

## 1. 确认旧目录里有没有东西

```sh
# 列出旧布局下的音频文件（无输出 = 干净）
find /volume1/docker/audiobook-data/books/audios/ -mindepth 2 -maxdepth 2 -type f \
  \( -name '*.mp3' -o -name '*.m4a' -o -name '*.m4b' -o -name '*.flac' \
     -o -name '*.wav' -o -name '*.opus' -o -name '*.ogg' -o -name '*.wma' \
     -o -name '*.aac' \) 2>/dev/null
```

`upgrade.sh` 升级时也会自动做这个检查，发现残留会列出来并要求确认。

## 2. 有残留怎么办

残留 = 这本书是 **4.6.0-12 或更早**导入的有声书，从未在新布局重建。
目录名就是 book_id，需要先在网页端确认它对应哪本书：

```sh
# 例：audios/150/ 对应哪本书 —— 进容器查 calibre 库
docker exec audiobook-mybooks-1 python3 -c "
from webserver import loader
db = loader.get_calibre_db()
print(db.field_for('title', 150), db.field_for('path', 150))
"
```

然后把整个旧目录内容搬进该书目录的 `.audio/`：

```sh
# 例：book 150
cp -a "/volume1/docker/audiobook-data/books/audios/150/." \
      "/volume1/docker/audiobook-data/books/library/<作者>/<书名> (150)/.audio/"
```

搬完重扫一次导入页确认无损，再删旧目录。

## 3. 删除旧目录

确认第 1 步无输出后：

```sh
rm -rf /volume1/docker/audiobook-data/books/audios
```

`audio_output_folder` 配置项自本版起不再参与音频路径解析（仅保留在
`describe_leftover_legacy_audio()` 的检查逻辑里）。

## 4. 代码层面改了什么

| 位置 | 改动 |
| --- | --- |
| `webserver/base/audio_dir.py` | 删 `legacy_audio_dir`/`legacy_audio_dirs`/`LEGACY_AUDIO_ROOT`；`audio_dir_for_read` 无回退；`audio_dir_for_write` 无 legacy 抢跑 |
| `webserver/handlers/audio.py` | 7 处硬编码 + `AudioFile` 兜底 + 扫描并集全部清除；常量删除 |
| `webserver/handlers/base.py` | 有声书计数改扫 library（旧实现数 `audios/`，空目录后恒为 0） |
| `webserver/handlers/podcast.py`、`podcast_provider.py` | 音频服务改 `audio_dir_for_read` |
| `webserver/toolbox/mimo_tts.py` | TTS 输出改 `audio_dir_for_write` |
| `webserver/services/book_dedup.py` | 合并搬音频目标变为保留书目录的 `.audio/`；顺带修复 handler 里已然 ImportError 的 `AUDIO_OUTPUT_DIR` 导入 |
| `scripts/upgrade.sh` | 新增步骤 1.5 残留检查 |
