# 文件覆盖包（不依赖 git）

目标源码目录不是 git 仓库、也没有可用的 `APP_GIT_DIR` 时，用本包替代补丁序列。
内容取自优化分支 `opt/p0-p1` 的最终树 `fdbf006`（基线 `32bc1d4`），只包含**有改动的文件**。

## 构成

| 文件/目录 | 说明 |
|---|---|
| `files/` | 34 个改动文件，按原相对路径存放（直接对应目标源码目录） |
| `MANIFEST.tsv` | `action|path|mode|base_sha256|new_sha256`，首行 `#` 为表头注释 |
| `SHA256SUMS` | 本包完整性校验，`sha256sum -c` 可用 |
| `README.md` | 本说明 |

`action`：

- `add`：基线中不存在，本次新增（18 个）。目标已存在同名文件 → 冲突，默认跳过。
- `update`：基线中已存在，本次覆盖（16 个）。必须目标当前 sha256 等于 `base_sha256` 才覆盖。
- `base_sha256` 为 `-` 表示基线无此文件。

不包含：文档目录外的交付文档、`node_modules`、`.git`、`__pycache__`、构建产物。

## 用法

应用脚本在发布包的 `nas/60-apply-overlay.sh`：

```bash
# 只列清单
/bin/bash nas/60-apply-overlay.sh --list

# dry-run：逐个比对基线 sha256，打印 覆盖/新增/跳过
/bin/bash nas/60-apply-overlay.sh

# 应用（覆盖前备份到 rollback/<时间戳>/）
/bin/bash nas/60-apply-overlay.sh --apply

# 强制覆盖基线不一致或有冲突的文件（仍先备份）
/bin/bash nas/60-apply-overlay.sh --apply --force

# 回滚源码（省略时间戳即最近一次）
/bin/bash nas/60-apply-overlay.sh --rollback
```

可指定其他位置：

```bash
/bin/bash nas/60-apply-overlay.sh --overlay /path/to/overlay --target /path/to/audiobook
```

手工比对（不用脚本时）：

```bash
cd overlay && sha256sum -c SHA256SUMS
# 查某个文件的基线哈希：
awk -F'|' '$2=="webserver/main.py"{print $4}' MANIFEST.tsv
# 与目标对比：
sha256sum /volume1/docker/audiobook/webserver/main.py
```

## 基线校验的意义

`base_sha256` 是 `32bc1d4` 原始部署包中该文件的哈希。比对一致说明目标文件与你当时的部署包是同一版本，
覆盖是安全的；不一致说明目标被改过（hotfix、别的版本、自己修改），默认跳过，避免无声覆盖。
确认要覆盖时用 `--force`，脚本仍会先备份。

## 回滚

```text
<ops目录>/rollback/<YYYYmmdd-HHMMSS>/
├── files/<相对路径>   被覆盖前的原文件
└── ROLLBACK.tsv       M|路径 → 恢复 files 中的原文件
                       A|路径 → 本次新增，回滚时删除
```

回滚只还原源码，不还原镜像。若已重建镜像，回到旧镜像：

```bash
docker tag mybooks-local:pre-opt mybooks-local:latest
docker compose -f /volume1/docker/audiobook/docker-compose.yml up -d mybooks
```

## 生效方式

本部署包 `docker-compose.yml` 为 `build: context: .` + `image: mybooks-local:latest`，
仅挂载 `/volume1/docker/audiobook-data:/data` —— 源码**打进镜像**，覆盖后必须重建：

```bash
docker tag mybooks-local:latest mybooks-local:pre-opt
docker compose -f /volume1/docker/audiobook/docker-compose.yml build mybooks
docker compose -f /volume1/docker/audiobook/docker-compose.yml up -d mybooks
```

`60` 会自动判断并打印上述命令；`--tag-only` / `--build` / `--rollback-image` 才真正执行。

构建重启后用 `nas/70-check-image.sh` 确认镜像里确实是新代码（只读，逐文件比对 `new_sha256`）：

```bash
/bin/bash nas/70-check-image.sh          # 结论 + 逐文件 OK/DIFF/MISSING
/bin/bash nas/70-check-image.sh --json   # 机器可读
```

## 不适用的情况

宿主机只有预构建镜像、没有源码和 `Dockerfile` 时，本包无效：必须在**构建镜像的机器**上
把 `files/` 覆盖进源码树（或用补丁），重新构建镜像后再部署到 NAS。
