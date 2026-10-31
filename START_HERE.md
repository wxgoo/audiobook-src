# 📘 START HERE —— audiobook 操作总纲

> **看这一份就够了。** 其他 md 都是细则（遇到具体问题再翻）。
> 最后更新：4.6.0-1（基于上游 mybooks tag `4.6.0`）

---

## 〇、先认清 5 样东西

| 名字 | 位置 | 是什么 | 能不能删 |
|---|---|---|---|
| **audiobook** | `/volume1/docker/audiobook/` | 正在运行的源码（容器从这里启动） | ❌ 不能删 |
| **audiobook-data** | `/volume1/docker/audiobook-data/` | **所有数据和书**（11GB，唯一数据目录） | ❌ 绝对不能删 |
| **成品部署包** | `/volume1/docker/audiobook-deploy-4.6.0-1.tar.gz` | 248M 完整代码包，用来升级/重装 | 留档 |
| **补丁包** | `/volume1/docker/audiobook-patch-*.tar.gz` | 几十 KB，只含几个改动文件 | 用完可删 |
| **Gitee 仓库** | gitee.com/wxgoo/audiobook-src（master） | 代码备份 + 版本历史 | — |

**一句话铁律**：数据和源码永远分开。`audiobook/` 里一旦出现 `books/`、`data/`、`audios/` 目录，就是出错了。

---

## 一、三种场景，对号入座

| 我想做什么 | 看哪节 |
|---|---|
| 上游 mybooks 发了新版（比如 4.6.0 → 4.7.0），要跟着升 | **第二章** |
| 我自己改了点代码（比如修 bug、加功能），要上线 | **第三章** |
| 只是想把改动存到 Gitee | **第四章** |
| 系统坏了要重装 / 换新机器 | **第五章** |
| 出事了要回退 | **第六章** |

---

## 第二章：跟随上游升级（4.6.0 → 新版本）

### 最省事的方式：一条命令

```sh
sh /volume1/docker/upgrade-upstream.sh
```

脚本会依次问你/自动做：

| 步骤 | 脚本做什么 | 你要做什么 |
|---|---|---|
| 1 | 拉取 Gitee 上的代码 | 等着 |
| 2 | 查询上游最新版本号 | 等着（或手动输入，如 `4.7.0`） |
| 3 | 合并上游代码 | **可能有冲突**，见下方 |
| 4 | 检查代码完整性 | 暂停 → 你测试确认后回车 |
| 5 | 推送 Gitee | 等着 |
| 6 | 出成品包 `audiobook-deploy-4.7.0-1.tar.gz` | 等着 |
| 7 | 执行 upgrade.sh 上线 | 等着，最后验证网页 |

### 第 3 步遇到冲突怎么办

脚本会停下来，列出冲突文件（通常就 2~3 个）。处理规矩：

| 冲突文件 | 怎么办 |
|---|---|
| `webserver/settings.py` | 保留你的 `/data` 路径，同时把上游新增的配置项抄进来 |
| `docker-compose.yml` | 保留你的挂载写法 `/volume1/docker/audiobook-data:/data` |
| `myreader-dist` 目录 | 一律要自己的：`git checkout --ours myreader-dist && git add myreader-dist` |
| 其他文件 | 一般保留上游新版，删掉 `<<<<<<<` `=======` `>>>>>>>` 这些标记行 |

改完后：

```sh
cd /tmp/up-upgrade/audiobook
git add -A
git commit
```

**然后重新运行同一条命令**，脚本会自动从断点继续。

### 手动方式（不想用脚本时）

```sh
# 1. 在开发机/沙箱上
cd /root/work/audiobook-src
git fetch upstream --tags
git tag 4.6.0-before-upgrade          # 存档，可回退
git merge 4.7.0                       # 上游 tag 无 v 前缀

# 2. 有冲突就按上表处理，然后
git add -A && git commit

# 3. 测试（能打开网页、能听书、能上传）

# 4. 推送
git push origin master

# 5. 出包（见第三章"出包"部分）
```

---

## 第三章：自己改代码后上线（不打上游）

### 流程总览

```
改代码 → 本地提交 → 推送 Gitee → 打补丁包 → 传 NAS → 合并出成品包 → upgrade.sh → 验证
```

### 步骤 1：改代码并提交

```sh
cd /root/work/audiobook-src
git status                     # 看改了哪些
git add 改动的文件
git commit -m "说明你改了什么"
```

### 步骤 2：推送 Gitee

```sh
git push origin master
```

如果报 `could not read Username`，用带令牌的写法：

```sh
git push https://wxgoo:df1901c0825241bcc94aa54e6608fc2b@gitee.com/wxgoo/audiobook-src.git master
```

### 步骤 3：打补丁包

只改了少量文件时用这个（省时间，几秒完成）：

```sh
cd /root/work/audiobook-src
VER=4.6.0-2                    # ← 改这里：序号 +1
rm -rf /tmp/pt && mkdir -p /tmp/pt/audiobook-patch-$VER/audiobook
for f in 改动的文件1 改动的文件2; do
    mkdir -p /tmp/pt/audiobook-patch-$VER/audiobook/$(dirname $f)
    cp $f /tmp/pt/audiobook-patch-$VER/audiobook/$f
done
cd /tmp/pt && tar -czf audiobook-patch-$VER.tar.gz audiobook-patch-$VER
```

> ⚠️ 注意：补丁包内的顶层目录必须和文件名一致（`audiobook-patch-<版本>/`），否则合并脚本找不到文件。

### 步骤 4：传 NAS

把 `audiobook-patch-4.6.0-2.tar.gz` 上传到 `/volume1/docker/`

### 步骤 5：合并出成品包

编辑 `/volume1/docker/merge-patch3.sh`，改三行：

```sh
BASE=/volume1/docker/audiobook-deploy-4.6.0-1.tar.gz     # 上一版成品包（基准）
PATCH=/volume1/docker/audiobook-patch-4.6.0-2.tar.gz     # 本次补丁
OUT=/volume1/docker/audiobook-deploy-4.6.0-2.tar.gz      # 本次成品
PPREFIX=audiobook-patch-4.6.0-2                          # 补丁包顶层目录名
```

然后：

```sh
sh /volume1/docker/merge-patch3.sh
```

看到 `符号链接: 127` + `完成` 就成功了。

### 步骤 6：上线

```sh
sh /volume1/docker/audiobook/upgrade.sh /volume1/docker/audiobook-deploy-4.6.0-2.tar.gz
```

脚本自动：备份数据库 → 停容器 → 旧源码改名 → 解压新源码 → 校验 → 构建 → 启动 → 验证 4 个进程。

### 步骤 7：验证

浏览器打开网页，**Ctrl+F5 强刷**（清缓存），检查改动是否生效。

---

## 第四章：Gitee 上传（详细版）

### 一次性准备（只做一次）

```sh
git config user.name "王兴国"
git config user.email "17788912+wxgoo@user.noreply.gitee.com"
```

令牌：`df1901c0825241bcc94aa54e6608fc2b`（在 Gitee → 设置 → 私人令牌 生成，2FA 开启后密码不能用）

### 每次上传

```sh
cd /root/work/audiobook-src
git add -A
git commit -m "这次改了什么"
git push https://wxgoo:df1901c0825241bcc94aa54e6608fc2b@gitee.com/wxgoo/audiobook-src.git master
```

看到 `master -> master` 就是成功了。

### 常见报错对照

| 报错 | 原因 | 解决 |
|---|---|---|
| `could not read Username` | 没带令牌 | 用上面带令牌的完整地址 |
| `dubious ownership` | 目录属主不对 | `git config --global --add safe.directory 路径` |
| `rejected / non-fast-forward` | 远程有你本地没有的提交 | `git fetch` → `git rebase FETCH_HEAD` → 再 push |
| `Author identity unknown` | 没配用户名邮箱 | 见上方"一次性准备" |
| `403` | 令牌失效 | Gitee 重新生成，替换脚本里的 TOKEN |

---

## 第五章：重装 / 换新机器

```sh
cd /volume1/docker
sh /volume1/docker/audiobook/upgrade.sh /volume1/docker/audiobook-deploy-4.6.0-1.tar.gz
```

如果是全新机器（`audiobook/` 目录都不存在），先临时解出 upgrade.sh：

```sh
cd /volume1/docker
rm -rf /tmp/boot && mkdir /tmp/boot
tar -xzf audiobook-deploy-4.6.0-1.tar.gz -C /tmp/boot
sh /tmp/boot/audiobook/upgrade.sh /volume1/docker/audiobook-deploy-4.6.0-1.tar.gz
```

前提：`audiobook-data/` 目录要先存在（空了也行，会重建）。

---

## 第六章：出事回退

| 情况 | 命令 |
|---|---|
| 刚升级完，网页打不开 | `cd /volume1/docker && rm -rf audiobook && mv audiobook.old-<时间戳> audiobook && docker restart audiobook` |
| 想回退到 Gitee 某个版本 | `cd /root/work/audiobook-src && git tag` 看存档 → `git reset --hard <tag>` → 重新出包 |
| 数据库坏了 | 去 `/volume1/docker/audiobook-data/backup-*/` 找 upgrade.sh 自动备份的库，复制回去 |

---

## 七、绝对不要做的事

| ❌ 禁止 | 原因 |
|---|---|
| `rm -rf /volume1/docker/audiobook-data` | 11GB 数据全没，没有第二次机会 |
| 把 books/、音频拷进 `audiobook/` 目录 | 下次升级会丢，且污染源码 |
| 直接从 Gitee 下载 zip 部署 | 符号链接丢失，网页会白屏 |
| 群晖 SSH 里粘贴多行命令 | BusyBox 会逐行执行，前半句就跑飞了 → 写成 .sh 文件再 sh |
| 用 `tar --exclude` 打包 | 群晖 BusyBox tar 不认，直接报空包 |

---

## 八、文档索引（细则）

| 文档 | 什么时候看 |
|---|---|
| `START_HERE.md`（本文） | **永远先看这个** |
| `UPSTREAM_UPGRADE.md` | 跟随上游升级要抠细节时 |
| `INSTALL_GUIDE.md` | 排查具体功能问题（1200+ 行，当字典查） |
| `DEPLOY_README.md` | 首次部署、目录布局说明 |
| `PORTING_NOTES.md` | 想知道自己改了上游哪些地方（版本号规则也在这） |

脚本清单：

| 脚本 | 作用 |
|---|---|
| `upgrade.sh` | ⭐ 升级/重装（唯一入口，最常用） |
| `upgrade-upstream.sh` | 跟随上游一条龙 |
| `merge-patch3.sh` | 补丁包 → 成品包 |
| `deploy.sh` | 全新部署（首次装机用） |
