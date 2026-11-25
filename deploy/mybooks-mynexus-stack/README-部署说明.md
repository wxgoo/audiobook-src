# MyBooks + MyNexus 二合一部署 — 最终版说明

这次的安装器已**重写并端到端验证**：全新安装、老用户迁移两种场景都在沙箱真实跑过，容器能正常启动、设置自动填好、两容器互通。不用再逐个踩坑。

## 先准备 3 个文件（放同一目录）

| 文件                                         | 作用                                   |
| ------------------------------------------ | ------------------------------------ |
| `mybooks-mynexus-stack.tar.gz`             | 部署包（compose + .env + 设置 + 安装器）       |
| `mybooks-image-4.7.0-build.09-full.tar.gz` | MyBooks 完整镜像（929MB，含 AI 助手依赖 + 语音输入） |
| `mynexus-image-latest.tar.gz`              | MyNexus 镜像（570MB）                    |

> 群晖直连 Docker Hub 常有 x509 证书错误，所以两个镜像都用离线包导入，不要在线 pull。

## 部署步骤（新用户 / 老用户都一样，脚本自动判断）

```sh
cd /volume1/docker                       # 你想放部署包的目录
tar xzf mybooks-mynexus-stack.tar.gz
cd mybooks-mynexus-stack

vi .env                                  # 只需确认/填这几项，见下方" config 核对"
./install.sh --dry-run                   # 先看计划，确认无误
./install.sh                             # 正式执行
```

脚本会**自动识别场景**：

- **全新安装**：没检测到旧容器/旧目录 → 自动建数据目录骨架（含 `books/settings`、`books/library`）、建 mynexus 挂载目录、导入镜像、起栈。
- **老用户迁移**：检测到旧容器或旧 `audiobook` 目录 → 自动从旧容器探测真实书库（不会用错路径）、停旧栈、旧目录改名 `audiobook.old`、再起新栈。

两种情况都**不需要你手动建任何目录**——这是之前 `Bind mount failed` 的根因，已内置解决。

## .env 需要确认的项

```ini
MYBOOKS_IMAGE=mybooks:4.7.0-build.09-full-autosplit  # 别改成其它 tag
DATA_DIR=/volume1/docker/audiobook-data      # 绝对路径；新用户用默认即可，脚本会自动建
# ★ MyNexus AI 解析数据/配置目录：绝对路径，默认在 DATA_DIR 下面、不在 deploy-stack 里。
#   升级改名 deploy-stack.old 不再丢数据；一般不用改。
MYNEXUS_DATA_DIR=/volume1/docker/audiobook-data/mynexus-data
MYNEXUS_CONFIG_DIR=/volume1/docker/audiobook-data/mynexus-config
PUID=1026          # 群晖：用你自己的（控制面板可查；填错会上传失败/设置存不下）
PGID=100
LLM_API_KEY=sk-你的DeepSeek密钥              # ★必须填，AI 功能要用
AI_API_KEY=sk-你的DeepSeek密钥               # ★同一个 key 填两处
LLM_BASE_URL=https://api.deepseek.com        # 只写到域名根，不带 /v1、更不带 /chat/completions
LLM_MODEL=deepseek-flash                     # DeepSeek 默认；强推理可换 deepseek-v4-pro
LLM_TIMEOUT=90                               # LLM 请求超时秒数，一般不用改
```

其余（TOKEN、HF 镜像、端口 9800/8443/3000）都已配好，不用动。`MYNEXUS_API_TOKEN` 脚本会自动生成。

### MyNexus 模型配置：全部在 .env，设置页不用填

MyNexus 的模型配置**单一来源就是 `.env`**，通过 compose 的 `MYNEXUS_LLM_*` / `MYNEXUS_EMBEDDING_*` 环境变量注入并在运行时覆盖 `config.yaml`。所以：

- **LLM**：改 `.env` 的 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`（+ 可选 `LLM_TIMEOUT`），重建容器即生效。**不要**去 MyNexus 设置页「LLM」标签页填——填了也会被 env 覆盖，白填还误导。
- **Embedding（向量化）**：镜像已内置本地 ONNX 模型（`/usr/share/models`），compose 钉死为 `local` + 内置路径，免下载。设置页「嵌入」标签页不用动。
- 只有「连接」标签页里的 MyBooks 地址/账号/密码如果没有自动填好时才需要手动填一次；它存在外置的 `mynexus-config/config.yaml` 里，升级改名也不会丢。

## 安装完成后

脚本最后会做健康检查，看到 `[OK] 两个容器均已启动（Status: running）` 就成了。然后：

1. 打开 `https://你的NAS_IP:8443`（自签证书点"仍要继续"）→ 设置页，确认 MyNexus 的**开关/URL/Token 已自动填好**。
2. 顶部导航的 **AI 助手**、书详情页的 **AI 伴读** 都能用，输入框旁有麦克风按钮（语音输入要 HTTPS 才弹权限）。
3. 语音首次用会下载 whisper 模型（走 hf-mirror 镜像，约 150MB），`docker logs mybooks` 可看进度，之后离线可用、容器重建不丢。

## 如果没起来

脚本会直接打印排查命令，通常是这三种：

- **端口占用**：9800/8443/3000 被别的容器占了 → 改 .env 端口或停占用的服务。
- **权限**：`chown` 失败 → 手动 `chown -R 1026:100` 数据目录和 `mynexus-data/config`。
- **镜像不全**：脚本会明确告诉你缺哪个包、放到哪个目录，不会让你做无意义的选择。

排查命令：

```sh
docker logs mybooks --tail 50
docker logs mynexus --tail 50
docker compose -f ~/docker/mybooks-mynexus-stack/docker-compose.yml ps
```

## 运维脚本（`scripts/`）

部署包自带 4 个从原项目移植、已按新栈（容器名 `mybooks`）改好的运维脚本，在 NAS 宿主机上执行：

| 脚本                            | 用途                                         | 用法                                                |
| ----------------------------- | ------------------------------------------ | ------------------------------------------------- |
| `backup.sh` + `backup_run.py` | **全量数据备份**（书库+音频+数据库+配置），日/周/月分级保留、硬链接增量   | `sh scripts/backup.sh`（详见《备份与恢复说明.md》）            |
| `check-reader.sh`             | 诊断"打开书没内容"：查容器/进程/端口/日志                    | `sh scripts/check-reader.sh`                      |
| `deploy-cert.sh`              | 申请真 Let's Encrypt 证书并装进容器（可选，自签够用可不碰）      | 见脚本内 `--help`                                     |
| `search_index.py`             | 重建中文搜索索引（需先 `docker cp` 进容器，见《备份与恢复说明.md》） | `docker exec ... python3 search_index.py rebuild` |

> 这些脚本都默认容器名 `mybooks`、数据目录 `/volume1/docker/audiobook-data`，与你的新栈一致，无需改参数。

## 校验

两个镜像包和部署包都带 `.sha256`，传输后可先校验：

```sh
sha256sum -c mybooks-image-4.7.0-build.09-full.tar.gz.sha256
sha256sum -c mynexus-image-latest.tar.gz.sha256
sha256sum -c mybooks-mynexus-stack.tar.gz.sha256
```
