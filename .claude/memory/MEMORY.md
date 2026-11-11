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
cd app && npm ci                                        # package-lock 对齐，约 14s
node node_modules/nuxt/bin/nuxt.js generate --spa       # 产物 app/dist，757 文件 / 142 js
bash scripts/pack.sh                                    # 出包，必须 bash 不能 sh
```
改前端**必须重建 dist**，否则浏览器加载的还是旧 JS。注意两点：

- `nuxt generate` 才是静态产物（`dist/` 含 200.html 与各路由目录）；`nuxt build` 只出 `.nuxt/`
- **不要用旧包里的 dist 顶替**：旧 dist 自洽但缺新页面，会出现「升级入口 / 友情链接 /
  作者归一页消失」这类假 bug（r13 踩过）。判断方法：`ls app/dist/admin/version`、
  `ls app/dist/toolbox/author_tools`，缺了就说明是旧构建
- 构建产物里若出现 `dist/myreader` 软链，删掉——那是本地 `public/` 的临时链接被带进来了

打包终验锚点：后端类/路由存在、`dist/_nuxt` 含新 chunk、语言包键存在、包内无过程文档残留。

**整包部署（换机器/大版本）**：
```bash
cd /volume1/docker && mv audiobook audiobook-backup-$(date +%m%d) && tar xzf audiobook-deploy-4.6.0-build.27.tar.gz && cd audiobook && docker compose up -d --build
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

**补充（r16 教训，同一个坑丢了两遍）**：进 `PERSISTABLE_KEYS` 并不够。设置页 POST 会
`args.clear()` 后只填前端提交的键，「只在 PERSISTABLE、不在 ADMIN_SETTING_KEYS」的键
每次保存都被整份覆盖抹掉（`READER_GROUPS` / `READER_GROUP_STRICT` /
`ENABLE_KOREADER_SERVICE` / `scan_hash_workers` / `site_theme` 五个）。
r13 的断言只测了 `save_partial` 路径，所以「测试全绿、线上照丢」。
现在 `save_extra_settings()` 入口统一补齐未提交的持久化键；测试要测 **POST 路径**
（`TestSaveExtraSettingsCarryOver`），不是只测 `save_partial`。
另外 `dumpfile()` 覆盖前会留一份 `auto.py.bak`，配置被误抹时从那里捞。

---

## ⑪ 列表拖拽排序：稳定 key 要「看得见但存不进去」

设置页友情链接用 `vuedraggable` 拖动排序（`app/src/pages/admin/settings.vue`）。三条硬约束：

1. `v-for` 的 key **不能用下标**——Sortable 先移动真实 DOM，Vue 按下标复用元素，
   拖动后输入框里的文字会串到别的行。
2. 稳定 id **不能进配置文件**。用 `Object.defineProperty(item, "_uid",
   { value: ++seq, enumerable: false })`：`Object.keys` / `Object.assign` / `JSON.stringify`
   都看不到它，落盘到 `auto.py` 时干干净净，也不影响「未保存修改」的 JSON 比对。
3. 数组**不能整份替换**。`moveFriend` 早期用 `slice` + `$set` 换新数组去绕「Vue 2 侦测不到
   下标赋值」，但 `:list` 绑的是引用，换新数组后拖拽组件还指着旧数据。改用
   `splice` 摘出再插入：既响应式，又保持同一引用。

验证：无头 Chromium 用 `locator.drag_to()` 能触发 HTML5 拖拽；拖完比对
「数据顺序 / `_uid` / 输入框 value」三者是否一一对应，再跑一次删除 + 新增。

---

## ⑫ 悬空引用：只报告，不要「顺手修」

读者组的组名存在 `Reader.extra["reader_group"]`（用户侧），组定义存在
`CONF["READER_GROUPS"]`（设置侧）。两边不同步 → 「组不存在 → 读不到任何书」，
界面上又看不到这些人。

踩过的错：在 `GET /api/admin/reader_groups` 里发现悬空就 `clear_members_of()`。
自以为在修脏数据，实际是**在管理员看到告警之前把唯一能恢复的线索删了** ——
组定义重建回来，人也回不去了，DB 里没有 `extra` 的历史。

现在的做法：
- `collect_groups()` 只算 `orphan_groups()`，不写 DB；
- 悬空本身不危险，`effective_limits()` 对 `group-missing` 按「读不到书」兜底，不会静默放行；
- 重建走显式接口 `POST /api/admin/reader_groups/revive`（`names` 缺省=全部），
  建出来是「白名单 + 空条件」，人归位但规则仍挡着，等管理员补分类/标签。

判断口径：清理动作若丢掉「别处算不出来」的信息，就不能放在读路径上；
要么别做，要么改成显式操作 + 可回滚。

---

## ⑬ Gitee raw 会做内容审核：451 = 文件被拒发，不是网络问题

`https://gitee.com/<o>/<r>/raw/<branch>/<path>` 过内容审核，命中就返回
`451 The content may contain violation information`。**git clone 不受影响**，
所以仓库看起来正常，只有在线更新（直链下载）会断——r18 整版因此装不上。

- 判定是模型黑箱，不能靠试词表穷举：实测「血腥暴力」连排触发，`血腥,暴力` 不触发；
  `情色`/`色情`/`性爱` 单独不触发，叠在整段里整份文件被判。
- 规矩：`webserver/**`、`app/dist/**` 里不写露骨/暴力/涉政词组，用中性词代替，
  真实标签让管理员自己从库里选。
- **发版前必须全量自检**：清单里每个文件用 `MyBooks-VersionCheck/1.0` 的 UA 下载 +
  核 sha256，全 200 才打 tag。`python3` 十行脚本即可，别省。
- 失败提示要带路径：`_get()` 遇 4xx（除 408/429）立即失败，`_download_failure()`
  写明「发布侧问题、与本机网络无关」+ 整包部署兜底。

---

## ⑭ 永不 settle 的 Promise = 无限转圈且零提示

服务启动期（含在线更新后重启、DB 升级）端口由临时服务占着，`/api/*` 一律回
`{"err":"server_starting"}`。`$backend` 为「启动期间不弹错误框」直接
`return new Promise(() => {})`，指望 `redirect("/starting")` 接管。

但请求如果是在**导航结束之后**发出的（mounted 补拉、展开面板、点重试），
`app.context.redirect()` 已经是空操作，页面不跳；调用方 `await` 永远挂起，
`loading` 永远是 true —— 用户看到的是「一直转圈，不报错，刷新才好」。
读者组面板就是这么卡住的（r20 修，`server_starting` 分支补齐 300ms 整页跳 `/starting`）。

两条规矩：
- 用 `new Promise(() => {})` 表达「此响应无须回调」时，必须同时给出可见出路；
- 任何会显示 spinner 的 `await` 都要 `Promise.race` 超时兜底，超时后停转圈 + 报错 + 重试入口。

排查口径：Network 里那条请求 pending 且无响应 = 服务在启动/重启；
`200` 且 body 是 `server_starting` = 本节这个坑。
