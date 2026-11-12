# update/ —— 发布清单目录

`manifest.json` 是「版本与更新」（`/admin/version`）的**唯一发布源**：

- 线上：容器通过 Gitee raw 直链读取仓库 master 分支上的这份文件，比对 `revision`。
- 本地：同一份文件随部署包打进镜像（`Dockerfile` 的 `COPY update/`），作为已安装修订的基线。
  在线热更新成功后，后端会直接覆写容器内这份文件。

生成方式（在仓库根目录，代码提交推送之后）：

```sh
python3 scripts/gen-update-manifest.py \
  --revision 4.6.0-build.27-r27 \
  --base-revision 4.6.0-build.27-r26 \
  --base-commit <r26 的 commit sha> \
  --summary "一句话说明"
```

生成后**必须再提交并推送**，页面才能检测到新修订。
`scripts/pack.sh` 会校验本文件存在且含 `revision`，缺了禁止出包。

完整机制见 `docs/在线更新说明.md`。
