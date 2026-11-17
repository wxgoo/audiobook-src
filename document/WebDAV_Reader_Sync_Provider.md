# WebDAV 每用户同步目录 Provider 设计（r46 补档）

> 本文恢复自 r45 及以前被删除的旧设计文档，并按 r46 现状重写。
> WebDAV 走 WSGI 旁路，不经过 `BaseHandler.prepare()` 门禁，因此权限规则需在此处手工补齐。

## 1. 路由与启动

- 路由：`r"/books/?(.*)"`，在 `webserver/main.py` 中注册，**必须早于** `static_files.routes()` 的 catch-all `r"/(.*)"`。
- 开关：`ENABLE_WEBDAV_SERVICE`（关闭返回 404）。`WebDAVHandler` 是裸 `tornado.web.RequestHandler`，自带 Basic 认证，首次请求懒加载 WsgiDAV app 后缓存。
- WSGI app 构造在 `webserver/webdav/server.py`，share 挂载点 `/books`；provider 变化时（`ENABLE_WEBDAV_SERVICE` / `WEBDAV_SYNC_FOLDER`）通过 `reset_app()` 丢弃缓存重建。

## 2. 认证（auth.py）

`MyBooksDomainController.basic_auth_user()`：

1. `username = user_name.strip().lower()`；
2. 查 `Reader`，用 `get_secure_password(password)` 与 `password` 比较；
3. 检查 `can_login()`；
4. 成功后写入 `environ["mybooks.user"]`。

r47 起 provider 侧统一通过 `_get_reader_from_environ(environ)` 解析用户：优先读 auth 写入的 `environ["mybooks.user"]`（Reader 对象，免查库），缺失时回退用 `environ["wsgidav.auth.user_name"]` 查库。所有出口都走这一个入口，杜绝对象/字符串混淆导致的"误判无用户→全放行"。

## 3. 每用户隔离模型（已实现）

- **物理目录**：`_get_user_sync_path(user_id)` → `/data/{sync_folder_name}/{user_id}/`，默认 `/data/reader/<数字 id>/`。每用户一个 `_UserSyncFilesystemProvider` 实例，缓存在 `_user_fs_providers[user_id]`。
- **对外路径统一 `/reader/`**（不暴露 username）：`mount_prefix = "/{sync_folder_name}"`。`_UserSyncFilesystemProvider._strip_prefix()` 把 `/reader/xxx` 剥成 `/xxx`；`_loc_to_file_path()` 同样剥前缀（MKCOL/PUT 写操作会绕过 `get_resource_inst` 直接调它）。
- **显示名修正**：根目录列目录时把 sync 项的 `name` 改为 `reader`。
- 隔离保证：用户 A 用 Basic 登录后，其 `/reader/` 落到 A 的目录；无法凭路径访问 B 的目录。目录名用**数字 id** 而非 username，规避重名与路径穿越。

设计取舍：**不改成 `/reader/<username>/`**——暴露用户名会引入跨用户穿越风险（需在 `_strip_prefix` 校验第一段属于当前认证用户），收益有限，故保留统一 `/reader/`。

## 4. 权限规则（WSGI 旁路手工补齐）

`dav_provider.py` 在关键出口手工实现了与 web 侧等价的规则：

| 规则 | 落点 |
| --- | --- |
| 版权下架 | `WebDavResource.get_content()` + 目录列表剔除（`book_takedown.is_takedown`） |
| 下载配额 | `get_content()` 里 `DownloadQuotaService.charge(..., PROTOCOL_WEBDAV)` |
| 阅读范围 | `_get_user_reading_range()` / `_is_book_in_reading_range()`，在书目/分类/标签列表过滤 |
| 私藏书 | `others_soled_books_id()` 剔除他人私藏 |
| 只读 | 虚拟集合与书籍资源所有写方法抛 403，仅 sync 目录可写 |

### r46 修复：阅读范围全局开关一致性

修复前 `_get_user_reading_range()` 只读用户字段，**不看 `ALLOW_READ_RANGE_SETTING` 全局开关**。结果：管理员在设置页关闭"阅读范围"后，web 侧 `is_book_visible()` 全库可见，但 WebDAV 仍按用户字段过滤，两边口径不一致。

修复后 `_get_user_reading_range()` 开头先判断：

```python
if not CONF.get("ALLOW_READ_RANGE_SETTING", False):
    return 0, set(), set()   # 全放行
```

与 web 侧 `BaseHandler.is_book_visible()` 的首行判断完全一致。管理员豁免、白名单(=1)/黑名单(=2) 判定也均对齐。

### r47 修复：书目树完全隔离（堵住越权读漏洞）

**问题**：r46 及以前，阅读范围过滤只作用在"列表枚举"路径（`BooksCollection.get_dynamic_members()` 及各分类/标签列表）。但有 8 个**直接定位单本书**的分支（`handle_category/tags/authors/recent/favorite/wants/reading/read_done` 的路径含 book_id 时）和唯一的下载出口 `WebDavResource.get_content()` **完全不做阅读范围/私藏判定**。用户只要知道 book_id，就能构造 URL 读到白名单之外或他人私藏的书——列表过滤形同虚设，属高危数据泄露。

**修复**：新增 `_can_access_book(environ, book_id, mi=None)` 作为所有出口的唯一校验点，判定顺序：

1. **未解析到用户 → 拒绝（fail-closed）**。WebDAV `require_authentication()=True`、`is_share_anonymous()=False`，恒要求认证，不存在合法匿名访问。
2. **管理员 → 全放行**（含 superuser 视角）。
3. **版权下架 → 拒绝**（出口兜底，目录层已过滤）。
4. **他人私藏 → 拒绝**（`others_soled_books_id()`）。
5. **全局开关关闭 → 放行**（与 web 侧一致）。
6. **阅读范围判定**：无条件从缓存重取**完整元数据**（含 `#category`/`tags`）后转调公共函数 `reading_range.book_matches_limits()`。不能用 `_build_book_item()` 的产物判定——它只有 `fmt_*`/`title`/`id`，缺分类标签，会让白名单误拒所有书。

接线位置：

- 8 个直链分支在构造 `WebDavResource` **之前**调用 `_can_access_book`，越界书返回 `None` → 404（目录层也隐藏）。
- `WebDavResource.get_content()` 在**下载配额扣费之前**调用，越界访问抛 403 且不误扣配额。构造时持有 provider 引用（`provider=self`），9 个构造点全部传入，无 fail-open。
- `handle_authors` 维度：先收集可见书（`_can_access_book`）再取其作者，避免作者名泄露越界书的存在。
- 虚拟书目路径层加 `posixpath.normpath` + 拒绝 `..` 段（sync 文件系统层的穿越由 `FilesystemProvider` 自带 containment 校验）。

**口径单一来源**：判定本体抽到 `webserver/services/reading_range.py`（只依赖 `webserver.constants`，无 Tornado/wsgidav 依赖）。`handlers/base.py._book_matches_limits`、`services/access_control.py.AccessControl.is_admin/reading_range_of`、WebDAV 三处全部转调它。网页列表 / 网页统计 / WebDAV 书目树共用同一份判定，改一处全站生效，杜绝 r46 那种"两份口径靠人肉同步"的漂移。

**与"跟上游一致"的关系**：不新增任何 per-user 数据模型或定制权限层，仍是上游 4.7.0 的"全库视图 + 用户阅读范围字段"语义；本修复只是把这一语义**在 WebDAV 的所有出口强制一致地执行**，属于补齐安全缺口而非引入偏离上游的新机制。

## 5. 配置

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `ENABLE_WEBDAV_SERVICE` | True | 服务总开关（设置页白名单内） |
| `WEBDAV_SYNC_FOLDER` | False | sync 目录总开关（设置页白名单内） |
| `WEBDAV_SYNC_FOLDER_NAME` | `"reader"` | 目录名/挂载前缀（r46 补默认值；**不进设置页白名单**，避免改错导致数据目录失联，可手工写 auto.py 覆盖） |

数据物理根：容器 `/data/reader/<id>/`（宿主机 `DATA_DIR/reader/<id>/`）。

## 6. 测试

- `tests/test_reading_range.py`：公共判定模块可直接 import 测试——管理员豁免、阅读范围字段读取、白名单(=1)/黑名单(=2) 全矩阵（含"白名单空条件不得误放行""黑名单空条件全库可读"两个关键边界）、dict 与元数据对象两种入参结果一致。
- `tests/test_webdav_user_isolation.py`（沙箱无 wsgidav，用纯函数复刻 + 源码核对）：
  - 每用户 sync 路径互不重叠；
  - 全局开关关闭 → WebDAV 全放行（r46 修复点）；
  - 管理员豁免、白名单/黑名单判定；
  - **r47 源码核对**：统一用户解析（对象优先+字符串回退）、fail-closed、8 个直链分支全过校验、`get_content()` 校验在扣费之前、管理员豁免、判定转调公共模块、路径穿越拒绝、作者维度过滤。
