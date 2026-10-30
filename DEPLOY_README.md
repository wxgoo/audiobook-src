# audiobook（MyBooks 移植版）完整部署包 v4.8.1

这是唯一需要的部署包，解压后的目录名是 `audiobook/`。

| 内容 | 说明 |
|---|---|
| audiobook/ 全部源码 | 含 webserver、app 前端源码、conf、docker |
| audiobook/myreader-dist/ | 内嵌阅读器 MyReader 构建产物（Next 16.2.6 standalone，127 个 pnpm 符号链接，封面修复已编译） |
| audiobook/tools/category_backfill.py | 读者组 #category 分类回填脚本 |
| audiobook/conf/nginx/mybooks.conf | 已含扫描器 444 屏蔽规则 |
| audiobook/deploy.sh | 一键部署脚本（校验→构建→启动→验证） |

## NAS 一键部署（推荐）

```bash
cd /volume1/docker
tar -xzf audiobook-deploy-v4.8.1.tar.gz
cd audiobook
sh deploy.sh
```

`deploy.sh` 会依次做：关键文件校验 → 符号链接抽查（防止解压压扁）→
`docker compose build` → `docker compose up -d` → 启动状态验证。
只构建不启动：`sh deploy.sh build-only`。

## 手动部署（等效于脚本内容）

```bash
cd /volume1/docker
tar -xzf audiobook-deploy-v4.8.1.tar.gz   # 务必命令行 tar，图形解压会压扁符号链接
cd audiobook
ls myreader-dist/app/server.js            # 确认产物在
grep -c "myreader" conf/supervisor/mybooks.conf
docker compose build && docker compose up -d
```

启动后验证（约等 20 秒）：

```bash
docker exec -it audiobook-mybooks-1 supervisorctl status
# myreader 应为 RUNNING；浏览器测试：
# http://<NAS_IP>:9800/read/589?format=epub  应一路跳到 /reader/cloud-589-epub
```

## 日常运维

```bash
# 读者组分类回填（先 dry-run 预览，确认后加 --apply）
docker exec -it audiobook-mybooks-1 python3 /var/www/mybooks/tools/category_backfill.py
docker exec -it audiobook-mybooks-1 python3 /var/www/mybooks/tools/category_backfill.py --apply

# MyReader 状态 / 日志
docker exec -it audiobook-mybooks-1 supervisorctl status myreader
docker exec -it audiobook-mybooks-1 tail -50 /data/log/myreader.log
```

## 版本记录

- v4.8.1（2026-10-30）
  - MyReader 502 三连修复：产物缺失 → supervisor 配置 → 符号链接压扁（详见 PORTING_NOTES.md 四之三）
  - MyReader 封面修复：applyCloudMetadata 补 metadata.coverImageUrl（同源 /get/cover/<id>.jpg）
  - nginx 扫描器 444 屏蔽（/api/mcp 是真实端点，刻意未拦）
  - 固化 tools/category_backfill.py 读者组分类回填脚本
  - 固化 deploy.sh 一键部署脚本；文档目录名统一为 audiobook
- 更早版本记录见 audiobook/README.md 与 audiobook/PORTING_NOTES.md

## 命名说明

对外目录/包名统一叫 `audiobook`（与 NAS 上的 `/volume1/docker/audiobook`、
容器名 `audiobook-mybooks-1` 一致）。代码内部运行路径 `/var/www/mybooks`、
`/var/www/myreader` 是上游程序写死的，不影响使用，请勿修改。
