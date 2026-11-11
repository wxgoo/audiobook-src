# MyBooks Project Memory

> 本文件记录**踩过的坑与已验证的操作方式**，避免重复犯错。新增条目请写「错在哪 → 正确做法 → 怎么验证」。

## Key Reference Documents

- [`docs/操作总纲.md`](../docs/操作总纲.md) — 日常运维/升级先看这个
- [`INSTALL_GUIDE.md`](../INSTALL_GUIDE.md) — 首次安装、功能排障（1400+ 行，当字典查）
- [`docs/部署包说明.md`](../docs/部署包说明.md) — 包里有啥、目录布局、upgrade.sh 设计
- [`docs/上游跟进清单.md`](../docs/上游跟进清单.md) — 相对上游的缺陷与新增，按 issue 整理

---

## 部署环境（生产 NAS）

| 项 | 值 |
|---|---|
| 宿主机 | 群晖 `RS2416P`，DSM（内核 3.10.108，Braswell） |
| 部署目录 | `/volume1/docker/audiobook`（源码 + Dockerfile） |
| 数据目录 | `/volume1/docker/audiobook-data` → 容器 `/data`（**唯一数据目录，永不被升级流程触碰**） |
| 容器名 | `audiobook-mybooks-1` |
| 容器内代码路径 | `/var/www/mybooks`（**镜像内置，无源码挂载**） |
| 宿主机能力 | **无 python3.12、无 npm** —— 任何 python/npm 命令必须在容器内跑 |

> 宿主机只改源码不生效：必须 `docker compose up -d --build` 重建镜像，或 `docker cp` 进容器。

---

## ① supervisor 程序名必须带组前缀 `mybooks:`

**错过的写法**（都犯过不止一次）：
```bash
docker exec audiobook-mybooks-1 supervisorctl restart mybooks     # ERROR (no such process)
docker exec audiobook-mybooks-1 supervisorctl restart tornado     # ERROR (no such process)
```

**正确写法**：
```bash
docker exec audiobook-mybooks-1 supervisorctl restart mybooks:tornado
```

**四个程序完整名**（配置在容器内 `/etc/supervisor/conf.d/mybooks.conf`）：

| 程序名 | 作用 |
|---|---|
| `mybooks:tornado` | 后端主进程（Python） |
| `mybooks:nginx` | 静态文件 + 反代 |
| `mybooks:logrotate` | 日志轮转 |
| `mybooks:myreader` | 内嵌阅读器（Next.js standalone） |

**查状态不要带程序名**（带的话只看到一个，容易误判整体）：
```bash
docker exec audiobook-mybooks-1 supervisorctl status
```

**何时才需要重启**：
- 改了 **Python 后端** → 重启 `mybooks:tornado`
- 只改了 **前端**（`app/dist`）→ **完全不用重启**，`_nuxt/*.js` 由 nginx 直接发，浏览器 Ctrl+Shift+R 即可
- 改了 nginx 配置 → 重启 `mybooks:nginx`

---

## ② 前端热更：不要用 `docker cp src/. 目标/`，会撞类型冲突

**报错**：
```
Error response from daemon: cannot overwrite non-directory
"/var/www/mybooks/app/dist/avatar" with directory "/var/www/mybooks/app/dist"
```

**原因**：容器里 `dist/avatar` 是文件/软链，宿主 `dist/avatar` 是目录；`docker cp .../src/. dst/` 是**合并**语义，类型不一致直接失败。

**正确做法 A —— tar 管道（推荐，绕过类型判断，不做 rm）**：
```bash
tar c -C /tmp/audiobook/app dist | docker exec -i audiobook-mybooks-1 tar x -C /var/www/mybooks/app
```

**正确做法 B —— 先删再拷整体**：
```bash
docker exec audiobook-mybooks-1 rm -rf /var/www/mybooks/app/dist
docker cp /tmp/audiobook/app/dist audiobook-mybooks-1:/var/www/mybooks/app/
```
B 的源是 `dist`（**不带** `/.`），目标是**父目录** `app/`。

**验证前端真的更新了**（关键：`_nuxt` 里带哈希的 chunk）：
```bash
docker exec audiobook-mybooks-1 ls /var/www/mybooks/app/dist/_nuxt/ | grep <chunk前7位>
```
每次构建后记下新 chunk 名（如 `42d9016.js`），能列出来才算成功。

---

## ②b dist 必须完整入库：`app/.gitignore` 的 dist 忽略规则已删除（r13 事故）

`app/.gitignore` 里有两条模板自带的 dist 忽略规则（Node 模板的第 7 行 `/dist` + Nuxt 模板的第 81 行 `dist`）。
**后果**：「dist 重新部署」提交时 `_nuxt/*.js` 全部被 git 挡在门外，只有 html/css/fonts 被迫 `-f` 进来——
仓库里的 dist 是「有页面、没 JS」的残骸，`index.html` 引用的 chunk 全 404。
NAS 走 git 路径 `reset --hard + docker compose up -d --build`，怎么重建镜像都没用（r13 前端 404 事故根因）。

- 已修复（`9d4cdef`）：删掉两条规则并留注释；app/dist 现在 744 个文件完整入库
- **验证口径与 ② 相同**：`git ls-files app/dist | wc -l` 应 ≈744，且 `_nuxt` 下 .js ≥130
- 改了前端之后提交前自查：`git status app/dist` 里必须能看到新增/变更的 `.js` chunk，
  如果看不到说明又被哪条 ignore 规则拦了——`git check-ignore -v <文件>` 一查便知
- 注意 ② 的 `docker cp` 类型冲突与这里无关：那条管「往运行中的容器拷文件」，这条管「文件进不进仓库」

---

## ③ 命令逐条贴，别一次粘多行

NAS 终端（SSH + 中文输入法）粘贴多行时 `\` 续行会被吃掉，命令被截断、报错看不懂。

- 给用户的命令**一律单行**，不用 `\` 续行
- 多步操作给编号列表，一次一条
- 避免中文引号、全角符号

---

## ④ 验证命令要指向正确的文件类型

**犯过**：用前端符号去 grep 后端文件，输出 0，让用户误判部署失败。
```bash
# 错：sync_sys 是 AppHeader.vue 的前端改动，不在 models.py
grep -c sync_sys /var/www/mybooks/webserver/handlers/../models.py     # → 0
```

**正确**：前端查 `dist/_nuxt/*.js`，后端查 `.py`：
```bash
docker exec audiobook-mybooks-1 grep -rl "sync_sys" /var/www/mybooks/app/dist/_nuxt/ | head -1
docker exec audiobook-mybooks-1 grep -c "PrintBookImport" /var/www/mybooks/webserver/handlers/book.py
```

---

## ⑤ calibre 数据库：`custom_columns` 没有 `colnum` 字段

**犯过**：诊断 SQL 写 `select colnum from custom_columns` → `no such column: colnum`。

**事实**：
- `custom_columns` 表结构：`id` / `label` / `datatype`（**列号就是 `id`**）
- 值存 `custom_column_<id>`，引用关系在 `books_custom_column_<id>_link`
- 常用 label：`book_type`、`book_count`、`location`、`category`、`narrator`、`folder`

**查实体书数**：
```sql
SELECT count(*) FROM custom_column_<book_type的id> WHERE value = 1;
```

**分类候选值必须 JOIN link 表**（否则混入孤儿值——书移走后 `custom_column_N` 记录不清理）：
```sql
SELECT DISTINCT d.value FROM custom_column_<category的id> d
JOIN books_custom_column_<category的id>_link l ON l.value = d.id
WHERE d.value IS NOT NULL AND d.value != '' ORDER BY d.value;
```

---

## ⑥ 实体书是双写：`Item` 表 + calibre 自定义列

新建/转换实体书时两处都要写，漏一处就是「列表有但计数不对」或反之：
```python
item.book_type = BOOK_TYPE_PHYSICAL      # 1
item.book_count = count                   # 业务库 items 表
self.calibre_db_cache.set_field(CALIBRE_COLUMN_BOOK_TYPE, {book_id: 1})
self.calibre_db_cache.set_field(CALIBRE_COLUMN_PHY_COUNT, {book_id: count})
```

---

## ⑦ 上传权限：`sys.allow.upload` 只管访客，别拿它判断登录用户

- `sys.allow.upload` = `ALLOW_GUEST_UPLOAD`，**只表示访客能否上传**，且开「必须登录」后恒为 `False`
- 登录用户能否上传看 **`user.can_upload`**（用户 `u` 权限位，默认 `True`）
- 管理员**恒能**上传（后端已改 `is_admin() or can_upload()`）
- `/user/info` 下发 `can_upload`，前端用它判断按钮显隐

---

## ⑧ 上游仓库分支陷阱

| 上游 | 仓库 | **正确分支** | 说明 |
|---|---|---|---|
| mybooks | `PoxenStudio/mybooks` | **`develop`** | `main` 只有 24 个 service，`develop` 有 41 个，差 67 个文件 |
| talebook | `talebook/talebook` | `master` | |

GitHub 直连 `git clone` 会 `GnuTLS -110`，改用：
```
https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{branch}
```

---

## ⑨ 前端构建与打包

```bash
cd app && npx nuxt build --spa     # 产物在 app/dist，约 746 文件
```
改前端**必须重建 dist**，否则浏览器加载的还是旧 JS。

打包终验锚点：后端类/路由存在、`dist/_nuxt` 含新 chunk、语言包键存在、包内无过程文档残留。

**整包部署（换机器/大版本）**：
```bash
cd /volume1/docker && mv audiobook audiobook-backup-$(date +%m%d) && tar xzf audiobook-deploy-4.6.0-19-r13-patched.tar.gz && cd audiobook && docker compose up -d --build
```

---

## ⑩ 用户偏好

- 命令**单行**给，编号列表，一条一条来
- 交付物只要**完整部署包**；不要热修包、过程文档、归档
- 包内 `docs/` 只保留使用说明与部署文档，删归档、排障记录、移植清单
- 说话直接，别铺垫；错了就认，改到底

---

## ⑨ 新增「要持久化的设置」必须进 PERSISTABLE_KEYS，否则被静默抹掉

`SettingsSaver.dumpfile()` 是**整份覆盖** `auto.py`，只写 `PERSISTABLE_KEYS` 白名单里的键
（`save_partial` 也一样：先按白名单从 CONF 播种，再叠加本次改动的键）。

**后果**：某个键不在白名单里时，设置页**任意一次无关保存**都会把它从 auto.py 里删掉，
界面无任何提示。读者组分组规则就因此每次重建后全丢（r13 事故：`READER_GROUPS`
后来才补进白名单）。

自查清单（新增持久化设置时逐条过）：
- 键加进 `webserver/base/setting_saver.py` 的 `PERSISTABLE_KEYS`（设置页能编辑的再加 `ADMIN_SETTING_KEYS`）
- `tests/test_setting_saver.py` 里加两条断言：键在白名单内 + 设置页保存无关键后值不变
- 反向验证：临时把键从白名单删掉，测试必须变红，否则断言是假的

容器内权限相关：`docker exec` 默认是 root（镜像 USER），服务进程是 gosu 降到 `PUID:PGID`
（compose 默认 1026:100）；`/data` 下文件属主显示 1026 是正常的，别误判成权限问题。
