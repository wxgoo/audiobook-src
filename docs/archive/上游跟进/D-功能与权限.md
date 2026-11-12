> 已归档（2026-11-13）：随《上游跟进清单》一并归档，仅作追溯。

# D 主题：功能与权限

对应 [清单 D 节](../上游跟进清单.md#d-我们新增的功能-)。多数是业务定制，**可回提的是 D8/D9**，
D2 建议先提 issue 对齐数据模型。

| 条目 | 上游处置 | 本仓库落点 | 补丁要点 | 验证 |
|---|---|---|---|---|
| D1 实体书 CSV 批量导入 | feature request（低优先） | `handlers/scan.py`、`services/batch_add.py` | 业务定制强，先观察上游意愿 | 导入 CSV 后实体书类型正确 |
| D2 播放进度服务端存储 | 先提 issue | `models.py: AudioPlayback` | 跨设备续播普适，但数据模型改动大 | 两台设备续播位置一致 |
| D3 读者组总开关 | 自研替代 | `settings.py: READER_GROUPS_ENABLED` | 权限体系定制 | 关闭后读者组入口隐藏 |
| D4 同目录音频随书挂载 | 自研替代 | `services/scan_service.py` sidecar 音频 | 依赖 `.audio/` 布局 | 扫描导入后音频随书可见 |
| D5 音频转码工具 | 自研替代 | `handlers/audio.py`、`worker/epub2audio_worker.py` | 业务定制 | 批量转码可取消 |
| D6 账号体系增强 | 自研替代 | `handlers/user.py` | 业务规则定制 | 出生年份/密码强度校验生效 |
| D7 分类下拉只列有书分类 | 自研替代 | `handlers/book.py` 分类导航 | 与读者组绑定 | 空分类不出现 |
| D8 上传权限口径统一 | **提 PR** | `handlers/book.py`（7 处校验）、`models.py: can_upload()`、`handlers/user.py`、`services/book_access_service.py` | 统一走 `is_admin() or can_upload()`；`/api/user` 下发 `can_upload` 供前端判断 | 普通用户前台显示可上传且后端放行；受限用户前后端一致拒绝 |
| D9 首页推荐不足 + 测试污染 | **提 PR** | `handlers/book.py` 推荐卡片；`tests/` 全局状态隔离 | 推荐数量不足时补位；测试 fixture 清理单例 | 首页始终有 N 张卡片；单跑/全跑测试结果一致 |

## 已代选的决定
- D8 只统一「判断口径」，不改角色模型；新字段 `can_upload` 为追加字段，旧客户端忽略即可。
- D9 的补位逻辑取「按热度 + 随机」混合，不引入新表。

## 回滚
D8 回滚会让前后端上传权限重新分叉（前端可点、后端拒绝），建议保留；
D9 回滚只影响首页卡片数量与测试隔离。
