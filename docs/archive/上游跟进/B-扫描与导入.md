> 已归档（2026-11-13）：随《上游跟进清单》一并归档，仅作追溯。

# B 主题：扫描与导入

对应 [清单 B 节](../上游跟进清单.md#b-仅-mybooks-上游存在的缺陷talebook-无此实现)。
本主题大部分是 fork 自研实现，**只有 B4/B6 适合回提**。

| 条目 | 上游处置 | 本仓库落点 | 补丁要点 | 验证 |
|---|---|---|---|---|
| B1 `books/audios/` 删了又回来 | 不回提 | `docker/start.sh`、`.audio/` 布局（`base/audio_dir.py`） | 上游布局不同，PR 会被拒；本地用 Dockerfile/启动脚本排除规则 | 重启后旧 `audios/` 不再被拷回 |
| B2 扫描并入既有书作者/封面不更新 | 自研替代 | `services/scan_service.py: _merge_existing_book()` | 依赖 fork 合并逻辑，不回提 | 同名书二次导入后作者/封面按新文件更新 |
| B3 扫描/有声导入互斥单侧设防 | 自研替代 | `scan_service.py: do_import()` 的 `AudioBookImporter.is_running()` 检查 | 双向互斥，留 fork | 两边同时触发时后者被拒并提示 |
| B4 `do_import` 置锁后裸代码，异常锁泄漏 | **提 PR** | `scan_service.py: do_import()` 的 `try/finally` 释放 `static_is_importing` | 置锁之后所有路径（含选择器解析、`_collect_files`）都包进 `try`，`finally` 复位锁与用户上下文 | 构造 `_collect_files` 抛异常，下一轮导入仍可启动 |
| B5 `ImportRun.paths` 任意路径 | 自研替代 | `handlers/scan.py: ImportRun.post()` | `realpath` + `commonpath` 限定在 `scan_upload_path` | 传 `/etc` 应返回「路径不在扫描目录内」 |
| B6 `BatchAddRun` 预检/清理 | 拆分后提 PR | `handlers/scan.py` 批量导入入口；`services/batch_add.py` | 运行前互斥预检 + 异常路径删除暂存目录；CSV 业务耦合部分留 fork | 重复点击只启动一个任务；失败后暂存目录不残留 |
| B7 零散小 issue | 拆分后跟进 | 见清单逐条 | 每条独立可复现才提 PR | — |

## 一致性说明（与 P0/P1 实现对齐）
- `do_import` 的锁释放已经用 `try/finally` 覆盖（B4）；新增的分批提交窗口
  `import_phase1_batch_size` / `import_phase2_batch_size` 只改提交频率，不改状态机。
- 失败批次整批回滚，行留在 `READY`，下一轮重扫自愈；不会出现「计数虚高但没入库」。

## 回滚
B4 回滚后锁泄漏风险回归，建议保留；B6 回滚只需还原 handler 预检，不影响已导入数据。
