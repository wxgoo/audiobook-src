> 已归档（2026-11-13）：随《上游跟进清单》一并归档，仅作追溯。

# A 主题：安全与元数据（两个上游都存在的缺陷）

对应 [清单 A 节](../上游跟进清单.md#a-两个上游都存在的缺陷可分别提交)。
主题包文件清单见 `scripts/upstream/patch_tool.py` 的 `TOPICS["A"]`。

| 条目 | 上游处置 | 本仓库落点（按函数名定位，行号会漂移） | 补丁要点 | 验证 |
|---|---|---|---|---|
| A1 `@js` CORS 任意回显 + 堆栈泄露 | 提 PR | `handlers/base.py: js()` | `Origin` 只回显与 Host 同源的地址；异常分支不把 `traceback` 回给前端，只返回 `server.error` + 日志 | `curl -H 'Origin: https://evil.example' /api/...` 不应回显该 Origin |
| A2 PDF/TXT 作者被覆盖成「佚名」 | 提 PR | `handlers/book.py: normalize_pdf_meta()` | 文件名解析出的作者仅在被覆盖字段为空时使用；已有元数据优先 | 上传带作者 PDF，作者不应变成「佚名」 |
| A3 同名书判定顺序 | 提 PR + 回归用例 | `services/scan_service.py: _import_one_file()` 标题判重分支；`services/book_search.py` | 先判重再建行，避免「本该并入却新建」 | 同目录两本同名书导入后只有一条记录 |
| A4 监听导入静默失效 + 截断入库 | 提 PR（4 个缺陷合并） | `services/monitor_service.py` | 监听事件去重、`stat` 失败重试、复制完成后才入库、大小校验 | 往监听目录拷贝大文件，导入后大小与源文件一致 |
| A5 CSV 封面 URL SSRF | 提 PR | `services/batch_add.py` 封面抓取 | 仅 `http(s)` + 私网地址拦截 + 响应大小上限 + 超时 | 用 `file://` / `127.0.0.1` 封面 URL 应被拒 |
| A6 外部进程只 kill 不 wait | 提 PR | `services/converter.py`、`services/book_barn.py` 的 `Popen` 调用 | `terminate()` 后 `wait(timeout)`，超时再 `kill()+wait()` | 取消转换后无僵尸进程（`ps -ef | grep defunct`） |
| A7 分片上传阻塞事件循环 | 单独 PR + 压测 | `handlers/book.py` 分片上传 handler | 磁盘写入与哈希移入 `run_in_executor`；参数上下限与孤儿目录清理 | 上传 1GB 文件时其它接口 P95 不劣化 |
| A8 演播者被当作者 | 与 A2 同主题合并 | `services/audios_import.py` 元数据组装 | `artist/narrator` 映射到演播者字段，不写 `authors` | 有声书详情作者为原作者、演播者单独展示 |

## 已代选的决定
- A1 与 C6 都改 `handlers/base.py` / `audio.py` 的响应头，但**分开两个 PR**：安全修复优先合入。
- A5 的私网拦截用 `ipaddress` 判断解析后的地址（含 IPv6），不依赖域名黑名单。

## 回滚
单条回滚即 `git revert` 对应提交；A2/A8 涉及元数据，回滚后已导入的书不会自动改回，
需要重新刮削（`autofill` 任务可按 id 重跑）。
