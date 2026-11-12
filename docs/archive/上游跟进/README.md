> 已归档（2026-11-13）：补丁生成方式已迁入 [`上游比对与跟进-4.6.1.md`](../../上游比对与跟进-4.6.1.md) 第 8 节；
> 以下 A~D 主题包仅作追溯。

# 上游跟进：按主题拆分的补丁包

本目录把 [上游跟进清单](../上游跟进清单.md) 中的 A/B/C/D 条目整理成**四个可独立提交的主题包**，
配合脚本 `scripts/upstream/patch_tool.py` 从任意一份上游（mybooks `4.6.0` / talebook `v26.10.18`）
检出目录生成真正的 `.patch` 文件。

- [A 安全与元数据](A-安全与元数据.md)
- [B 扫描与导入](B-扫描与导入.md)
- [C 音频与播放](C-音频与播放.md)
- [D 功能与权限](D-功能与权限.md)

## 为什么按主题而不是按文件拆

`webserver/handlers/base.py`、`handlers/book.py` 同时承载 A/C/D 的改动，按文件拆会把不相关的
改动捆进同一个 PR，上游 review 成本高、被拒风险大。主题包只声明**文件清单 + 条目清单**，
导出时仍可逐条 cherry-pick / 手工剔除。

## 生成补丁

```sh
# 1) 准备上游检出（浅克隆即可）
git clone --depth 1 --branch 4.6.0 https://github.com/PoxenStudio/mybooks.git /tmp/mybooks-4.6.0

# 2) 生成某个主题的补丁（左侧=上游，右侧=本仓库）
python3 scripts/upstream/patch_tool.py export A --upstream /tmp/mybooks-4.6.0 --out upstream-patches/

# 3) 查看上游是否已修（按条目的 grep 检查点）
python3 scripts/upstream/patch_tool.py status --upstream /tmp/mybooks-4.6.0
```

导出结果：`upstream-patches/A.patch` 等，`git apply --check` 可直接验证。
`status` 会逐条打印 `fork-only`（上游没有）或 `upstream-has-marker`（上游已出现修复标记），
后者意味着该条可以从主题包里剔除，避免补丁永久堆积。

## 与本地分支的关系

补丁是从**本仓库当前代码**相对上游生成的，因此天然包含本次优化分支 `opt/p0-p1` 的改动。
向上游提 PR 前必须先跑：

```sh
python -m pytest tests/ -q
./scripts/test-integration.sh
```

并把 `docs/上游跟进清单.md` 的检查点逐条对照上游 Release Notes。

## 默认决策（已代选，可调整）

- 主题包只生成、不自动 `git apply`：上游合并策略（保留双方/取上游）需要人工判断。
- 不引入第三方 diff 库：`patch_tool.py` 只用 Python 标准库 `difflib`，NAS 容器内可直接跑。
- 每个主题包一个 PR；主题内部条目仍按「独立可复现」原则再拆小提交。
