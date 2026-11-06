# C 主题：音频与播放

对应 [清单 C 节](../上游跟进清单.md#c-音频播放链路前端为主)。
后端可回提的是 **C6/C8（受限用户脱敏部分）**；C1–C5、C7、C9–C11 与 fork 播放器/弹窗策略绑定，留 fork。

| 条目 | 上游处置 | 本仓库落点 | 补丁要点 | 验证 |
|---|---|---|---|---|
| C1 弹窗试听第二次卡死 | 自研替代 | 前端弹窗已下线（`app/src/pages/audio/_id.vue`） | 不回提 | 播放页连续切集不卡死 |
| C2 播放页三处初始化互相打断 | 自研替代 | `_id.vue` 初始化顺序 | 留 fork | 刷新/直链进入都能播放 |
| C3 续播 seek 时机 | 自研替代 | `_id.vue` + `handlers/audio.py: AudioFile.get` 的 Range 处理 | 留 fork | 从 50% 续播不触发中段 Range 卡死 |
| C4 弹窗进度映射恒空 | 自研替代 | 弹窗已下线 | — | — |
| C5 看门狗固定 8s 自愈死锁 | 自研替代 | `_id.vue` | 留 fork | 断网恢复后自动续播 |
| C6 `AudioFile` 响应头不规范 | **提 PR** | `handlers/audio.py: AudioFile` | HEAD 不返回 body；补 `ETag/Last-Modified`；Range 越界夹紧并返回 `416` + `Content-Range: bytes */total` | `curl -I` 无 body；`Range: bytes=9999999-` 返回 416 |
| C7 `_retryPlay` 重试代数守卫 | 自研替代 | `_id.vue` | 留 fork | 连续失败 3 次后停止重试 |
| C8 进度不互通 + 受限用户统计未脱敏 | 部分跟进 | 脱敏：`handlers/audio.py` 播放统计上报；进度互通：前端 | 受限用户不记录细粒度进度/统计，只保留匿名计数 | 受限用户播放后管理端看不到其进度明细 |
| C9 切集丢记忆 | 自研替代 | 前端 + `AudioPlayback` 模型 | 留 fork | 切集再切回进度保持 |
| C10 m4b 多章节共用 key | 自研替代 + 提 issue | `handlers/audio.py` 章节 key 生成 | 提 issue 说明「单文件多章节需按 chapter index 区分」 | 两个章节进度互不覆盖 |
| C11 双播放器进度不一致 | 自研替代 | 前端 | 已下线弹窗 | — |

## 与本次 P1 改动的关系
- `AudioFile` 的 Range 读盘已改为 `run_in_executor` + 分块 `flush`（P1-4），
  回提上游时应**拆成两个提交**：先补响应头（C6），再改异步读盘（性能）。
- 重构后的 `AudioFile` 保留 `HEAD` 与 `Range` 语义，回归用 `curl` 覆盖三种状态：`200` 全量、
  `206` 部分、`416` 越界。

## 回滚
C6 回滚只影响响应头，播放器兼容；C8 脱敏回滚会让受限用户统计重新可见，属隐私回归，建议保留。
