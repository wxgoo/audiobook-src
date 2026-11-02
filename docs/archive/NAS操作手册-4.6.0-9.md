# NAS 操作手册 · 4.6.0-9（按顺序照做）

> 每步都写了「该看到什么」，对不上就停下，别往下走。
> 建议一台电脑打开这份文件，另一台开 SSH 窗口，边看边敲。
>
> **这一版前后端都改了**：后端是作者归一化与重复书守卫，前端新增了
> 「作者归一化」页面和管理列表的锁图标。所以**必须重建镜像**（会重新
> `npm run build-spa`），不能只重启服务。
>
> 另外新增了 calibre 自定义列 `#author_locked`，`main.py` 启动时自动建列。

---

# 第一部分：主任务（升级到 4.6.0-9）

预计 12 分钟（含 4 分钟镜像重建）。**这一段必须做完。**

---

## 步骤 0：准备（在电脑上）

**最快路线**：只传 1 个文件。

1. 下载 `audiobook-deploy-4.6.0-9.tar.gz`（95M，**已合好，直接能上线**）
2. 打开群晖 DSM → File Station → 进入 `docker` 目录
3. 上传

**该看到什么**：`docker` 目录下多了 `audiobook-deploy-4.6.0-9.tar.gz`。

> **想自己从 `-8` 重新合一遍**（或者以后要重出包），再额外传这两个小文件：
> `audiobook-patch-4.6.0-9.tar.gz`（272K）、`merge-4.6.0-9.sh`（20K），然后做步骤 3、4。
> 如果你手上有合好的 deploy 包，**步骤 3 和 4 都可以跳过**。

> 顺手确认 `protect-custom.sh` 还在 `/volume1/docker/`。
> 在的话合并脚本会自动调用它保护 BOOK_NAV 与三语文案。

---

## 步骤 1：SSH 登录

在你电脑上开终端（Windows 用 PowerShell 或 CMD，Mac 用终端）：

```sh
ssh 你的用户名@192.168.x.x -p 22
```

密码就是你 DSM 登录密码。

**该看到什么**：出现 `用户名@RS2416P:~$` 这样的提示符。

> 群晖默认用 admin 组账号，升级操作建议用 `sudo`。下文命令里凡带 `sudo` 的都需要输密码。

---

## 步骤 2：确认身处的目录是干净的

```sh
cd /volume1/docker
pwd
ls -lh | grep -E "deploy|patch|merge|protect"
```

**该看到什么**：

- `pwd` 输出 `/volume1/docker`
- 列表里有 `audiobook-deploy-4.6.0-9.tar.gz`（你自己合的或我给的）
- 还有 `audiobook-deploy-4.6.0-8.tar.gz`（做基准用的，留着）

---

## 步骤 3：合并出包（**已有 deploy-4.6.0-9 就跳过**）

```sh
sh merge-4.6.0-9.sh
```

> **这条不要加 sudo**。脚本只读基准包、写 `/tmp` 和当前目录。

**这一步会跑 10~30 秒**（解压 95M 基准包 + 14 项校验 + 重打包）。

**该看到的完整输出**：

```
==> 基准包: /volume1/docker/audiobook-deploy-4.6.0-8.tar.gz
==> 补丁包: /volume1/docker/audiobook-patch-4.6.0-9.tar.gz
==> 解压基准包
==> 基准包顶层: /tmp/mp9/audiobook
==> 注入补丁（相对路径覆盖）
==> 符号链接: 127（应127）
==> 校验补丁文件已落位（23 个：后端 16 + 前端 7）
==> 校验补丁内容（关键字必须在）
==> 校验 i18n 的 _ 没被遮蔽
   OK
==> 校验 Python 语法
   17 个文件语法 OK
==> 校验 Vue 模板（非法标签名 / template v-for）
   119 个 .vue 模板 OK，3 个 locale 合法
==> 校验自定义内容（BOOK_NAV / 三语文案）
   使用 /volume1/docker/protect-custom.sh
==> 校验自定义内容是否健在
   ✓ BOOK_NAV 13 组
   ✓ 文案键与快照一致（2457 个）
==> 校验通过
==> 清理 .git / __pycache__ / *.pyc
==> 剔除运行时数据目录（cache/ sync/ 等，不应进源码包）
   移除 cache/（50 个文件，992K）
   移除 sync/（1 个文件，4.0K）
==> 重打包
==> 成品复检
   ✓ author_norm.py 已在包内
   ✓ test_author_norm.py 已在包内
   ✓ 无 cache/ sync/ 等运行时数据目录
==> 完成
-rw-r--r-- 1 root root  94M  /volume1/docker/audiobook-deploy-4.6.0-9.tar.gz
```

### 必须核对的五行

| 行 | 必须是什么 | 不对说明什么 |
|---|---|---|
| `==> 基准包:` | 结尾是 `-4.6.0-8.tar.gz` | 显示 `-7` 或更早 → 基准包不对，停下 |
| `符号链接: N（应127）` | N = 127 | 不是 127 → 基准包坏了，脚本自动中止 |
| `17 个文件语法 OK` | 17 | 少于 17 → 补丁不完整 |
| `119 个 .vue 模板 OK` | 119 | 报出非法标签名/文件行号 → 补丁被改坏，脚本已中止 |
| `✓ BOOK_NAV 13 组` | 13 | 不是 13 → 补丁没生效，脚本已中止 |
| **`✓ 无 cache/ sync/ 等运行时数据目录`** | 必须有 | 没有这行 → 用了旧版脚本，`deploy.sh` 第 6 步会拦 |

**脚本退出码 0 且出现「==> 完成」，就是成功了。**

> **如果报错中止**：脚本自带保护，出错时**不会产出 4.6.0-9 包**，
> 现役环境完全没被碰过。把报错信息发我。

> **`deploy.sh` 第 6 步报「源码目录出现数据类目录: sync cache」？**
> 那是**旧包**的问题。`-7` 起的基准包就带着 `cache/`（52 张缩略图）和
> `sync/1/reading.json`，合并时被原样继承。新版脚本会自动剔除并复检。
> 你手上的 `audiobook-deploy-4.6.0-9.tar.gz` 已经是修好的版本，直接部署即可。
>
> ⚠️ 别手动 `rm -rf audiobook/calibre`。它看着像书库数据，其实是
> calibre 的补丁源码和自定义插件，删了镜像构建会失败。

---

## 步骤 4：上线（重建镜像）

```sh
sudo sh /volume1/docker/audiobook/upgrade.sh /volume1/docker/audiobook-deploy-4.6.0-9.tar.gz
```

> **这条必须加 sudo**。`upgrade.sh` 内部要调 `docker compose` / `docker stop`，
> 群晖上普通用户没权限访问 docker。

**这一步约 4 分钟**（要重建镜像）。

> **为什么必须重建镜像？**两条理由，任一条都够：
>
> 1. **前端改了**——新增「作者归一化」页面、管理列表锁图标、三语文案。
>    不重新 `npm run build-spa`，这些界面根本不会出现。
> 2. **新增了 calibre 自定义列 `#author_locked`**，由 `main.py` 启动时
>    调 `add_meta_in_calibre` 自动建列。不重启服务 = 列不会建 = 作者锁定不生效。

**该看到什么**：一堆构建日志，最后出现类似：

```
✔ 容器已启动 / 服务正常
```

> **这期间别断 SSH、别关窗口。**

---

## 步骤 5：验证（3 项，逐项确认）

> **不用强制刷新浏览器**——这版没动前端。但如果你看到旧界面，刷一下也无妨。

### 5.1 确认服务起来了

```sh
sudo docker ps | grep audiobook
```

**该看到什么**：`Up` 状态，且可以看到 `Up X minutes`（说明刚重启过）。

### 5.2 确认锁定列建出来了（关键）

```sh
sudo docker exec audiobook python -c "
from calibre.library.database import LibraryDatabase
import os
p = '/config/library'
print('db exists:', os.path.exists(p))
"
```

> 容器名不一定是 `audiobook`，先用 `sudo docker ps` 看实际名字，替换掉。

更简单的办法是看日志里有没有我们的标记：

```sh
sudo docker logs audiobook 2>&1 | grep -i "AUTHOR_NORM" | head
```

**该看到什么**：暂时可能是空的（还没触发过归一化），没关系，下一步实地试一次就有了。

### 5.3 实地试一次（**这一步一定要做**）

> 它验证的是「以后会不会又白干」——这是本版的核心目的。

1. 打开网页，挑一本**作者名有脏数据**的书（比如作者是 `(法)法布尔`）
2. 编辑，把作者改成 `法布尔`，保存
3. 等一轮自动刮削，或者手动点「刮削」按钮
4. **作者应该还是 `法布尔`，没被打回 `(法)法布尔`**

然后看日志：

```sh
sudo docker logs audiobook 2>&1 | grep "作者已锁定" | tail -3
```

**该看到什么**：类似这样一行：

```
书籍 id=1234 作者已锁定，保留 ['法布尔']（刮削值 ['(法)法布尔']）
```

有这行 = 锁定生效了。**没有这行** = 打锁失败，告诉我。

再检查目录有没有分裂：

```sh
ls /volume1/docker/audiobook/config/library/ | grep -i "法布尔"
```

**该看到什么**：只有一个 `法布尔`，没有 `(法)法布尔`。

---

## 步骤 6：确认没问题后清理

```sh
cd /volume1/docker
rm -f audiobook-patch-4.6.0-8.tar.gz      # 旧补丁包，可删
rm -f audiobook-4.6.0-8-full.tar.gz       # 旧 full 包，可删
```

> **这些不要删**：
> - `audiobook-deploy-4.6.0-8.tar.gz`（下次合并的基准，留着）
> - `audiobook-deploy-4.6.0-9.tar.gz`（回退用，留着）
> - `protect-custom.sh`、`merge-4.6.0-9.sh`（以后升级要复用）

---

# 第二部分：回退预案（只有出问题才用）

`upgrade.sh` 在替换源码前会自动备份。

```sh
ls -d /volume1/docker/audiobook.old-*
```

**该看到什么**：类似 `/volume1/docker/audiobook.old-20251101-143022`（带时间戳）。

```sh
cd /volume1/docker
rm -rf audiobook.broken
mv audiobook audiobook.broken
mv audiobook.old-<把上面看到的时间戳粘这里> audiobook
sudo docker compose -f audiobook/docker-compose.yml up -d --build
```

等 4 分钟重建完，页面就回到升级前。

> 回退后 `#author_locked` 这一列还留在数据库里，**不影响任何功能**——
> 旧代码不认识它，只是多了一个没用的字段。

---

# 第三部分：别名表（可选，不配也能用）

**默认是空的**，不用就完全不用管。这一版真正的效果来自
「作者锁定 + 清洗增强 + 刮削源清洗 + 入库归一」，别名表只是锦上添花。

如果确实想配（比如 `J.K.罗琳` / `J·K·罗琳` / `罗琳` 要统一成一个）：

```sh
sudo docker exec audiobook cat /data/toolbox/author_norm/config.json
```

（文件可能还不存在，第一次保存时才创建。也可以自己建。）

格式：

```json
{
  "version": 1,
  "canonical": {
    "jk罗琳": {
      "name": "J·K·罗琳",
      "aliases": ["J.K.罗琳", "J·K·罗琳", "罗琳", "J·k·羅琳"],
      "note": "哈利波特作者"
    }
  },
  "never_merge": ["佚名", "未知"]
}
```

要点：

- `canonical` 的**键**是标准名的归一化键（小写、去标点、繁转简、只留汉字和字母数字）
- `aliases` 里任一写法命中都会归到 `name`
- 繁简自动归一，`J·k·羅琳` 不用单独写也能命中
- 改完**不用重启**，文件改时间变了会自动重载

> 不想手算键就先随便填，重启一次后系统会按 `aliases` 重建索引。

---

# 备忘：常见问题速查

| 现象 | 原因 | 处理 |
|---|---|---|
| `sh: merge-4.6.0-9.sh: No such file` | 没传那个 9K 的脚本 | 传上去，或用我合好的 deploy 包跳过合并 |
| **`!! 源码目录出现数据类目录: sync cache`** | 用了**旧版** deploy 包（`-7` 起就有这个毛病） | 换成重出的 `audiobook-deploy-4.6.0-9.tar.gz`。别手动删完就上——`sync/1/reading.json` 是旧快照 |
| `!! 找不到基准包 audiobook-deploy-4.6.0-8.tar.gz` | `-8` 不在 `/volume1/docker/` | 找到它挪过来，或显式指定路径 |
| `!! 基准包不是 -8 及以上` | 用了 `-7` | 换成 `-8`，否则 `-8` 的修复会丢 |
| `! 找不到 protect-custom.sh`（只是警告） | 脚本没放同目录 | 放回去，否则 BOOK_NAV 未校验 |
| 页面打开是空白 | 镜像没构建成功 | `sudo docker logs audiobook`，把日志发我 |
| **作者还是被改回去了** | 打锁没生效 | `sudo docker logs audiobook \| grep 作者已锁定`，把结果发我 |
| **阅读进度回退了** | 旧包的 `sync/reading.json` 盖了新文件 | 见下方「如果进度已经回退」 |
| 出现 `IndexError: list index out of range` | 某个刮削源返回纯职责词 | 把这行日志发我，告诉我哪个源 |
| 日志里 `[AUTHOR_NORM] 打锁失败` | `#author_locked` 列没建 | 说明镜像没重建，重做步骤 4 |

### 如果阅读进度已经回退了

如果你已经用旧包部署过一次，`/volume1/docker/audiobook/sync/1/reading.json`
可能被包里的旧快照盖了。三个恢复途径，按可靠程度排：

**① 从数据库备份恢复**（最可靠）

你的 `deploy.sh` 第 2 步做了备份：`/volume1/docker/audiobook-data-dbbackup-20261101-133404`。
如果同期还有别的备份，找最新的那份。

**② 从 `audiobook.old` 找**

`deploy.sh` 第 4 步把旧源码移到了 `/volume1/docker/audiobook.old`：

```sh
ls -l /volume1/docker/audiobook.old/sync/1/reading.json
cat /volume1/docker/audiobook.old/sync/1/reading.json | head -c 200
```

看里面的 `cached_through` 日期，如果比包里的 `2026-10-29` 新，直接拷回来：

```sh
cp /volume1/docker/audiobook.old/sync/1/reading.json \
   /volume1/docker/audiobook/sync/1/reading.json
```

**③ 接受**：这个文件记的是每日阅读时长/下载数统计（`reading_seconds` / `download_count`），
丢的是统计数字，**不影响书签、阅读位置这类真实进度**（那些在 calibre 数据库里，没被动过）。

---

# 一页速查（就把这两行贴在手边）

已经用我合好的包：

```sh
sudo sh /volume1/docker/audiobook/upgrade.sh /volume1/docker/audiobook-deploy-4.6.0-9.tar.gz
```

自己合并再上线：

```sh
cd /volume1/docker && sh merge-4.6.0-9.sh \
  && sudo sh /volume1/docker/audiobook/upgrade.sh /volume1/docker/audiobook-deploy-4.6.0-9.tar.gz
```

成功标志：合并阶段 `17 个文件语法 OK`、`119 个 .vue 模板 OK`、`✓ BOOK_NAV 13 组`；
上线后改一次作者、刮削、作者没被改回去。
