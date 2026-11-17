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

注意 provider 侧取用户 id 用的是 wsgidav 自己填的 `environ["wsgidav.auth.user_name"]`，再回库查 `user.id`——两套 environ 键并存，扩展时勿混淆。

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

## 5. 配置

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `ENABLE_WEBDAV_SERVICE` | True | 服务总开关（设置页白名单内） |
| `WEBDAV_SYNC_FOLDER` | False | sync 目录总开关（设置页白名单内） |
| `WEBDAV_SYNC_FOLDER_NAME` | `"reader"` | 目录名/挂载前缀（r46 补默认值；**不进设置页白名单**，避免改错导致数据目录失联，可手工写 auto.py 覆盖） |

数据物理根：容器 `/data/reader/<id>/`（宿主机 `DATA_DIR/reader/<id>/`）。

## 6. 测试

`tests/test_webdav_user_isolation.py`（沙箱无 wsgidav，用纯函数复刻 + 源码核对）：

- 每用户 sync 路径互不重叠；
- 全局开关关闭 → WebDAV 全放行（r46 修复点）；
- 管理员豁免、白名单/黑名单判定；
- 源码核对：确认 `_get_user_reading_range` 含全局开关判断、`WEBDAV_SYNC_FOLDER_NAME` 默认值存在。
