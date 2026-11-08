# 变更日志（CHANGELOG）

本项目的版本号规则：**`<上游 mybooks tag>-build.<自建构建号>`**，当前版本 **`4.6.0-build.27`**。
上游基线：mybooks tag `4.6.0`（2026-10-25，commit `3c5947c`）。
交付标签 / 包名与运行期版本同值：`4.6.0-build.27`（tag `4.6.0-build.27`，提交 `a5019c6`）。

> 更早的变更记录（`4.6.0-build.21` 及以前、旧编号 v4.7.x / v4.8.x 时代）已精简归档，
> 完整历史见 git 提交记录（`git log`）。

---

## 4.6.0-build.27（当前）

> 主题：**有声书一集播完自动进下一集**，收起成迷你条之后同样生效；迷你条补上「上一首 / 下一首」。
> 起因是现场反馈：点最小化收起后听完一集就停住，得重新点开播放页才会继续；
> 而播放页里 `onTrackEnded → nextTrack(true)` 一直是好的 —— 差别在于**收起后播放页已销毁**，
> 只剩迷你条的 `onEnded` 在跑，而它只做 `miniPlayer_pause`。

### 变更

1. **store 增加播放列表**：`miniPlayer` 新增 `list` / `index`（整张列表 + 当前序号），
   `miniPlayer_play` 接收 `{list, index}`。**不带 list 的音源（友情链接电台）必须清空旧列表**，
   否则迷你条会拿上一本书的列表去「下一首」，串台。
2. **新增 `miniPlayer_step(delta)`**：收起后播放页已销毁，切集只能由这条 mutation 改
   `url` / `index` / `currentTime`。`currentTime` 取该集的 `base`（整轨起始秒），
   与 `collapseToMini` 的交接口径一致，换集后不会被 `applyStart` 定位回上一集。
3. **迷你条加「上一首 / 下一首」**：`step(±1)`，首页 / 末页自动置灰；`onEnded` 由
   「暂停」改成「推进到下一集并续播」，只有最后一集才停。
   相邻两集指向同一个文件（同轨切片）时 `url` 不变、watcher 不触发，补一次 `attach`，
   否则表现为「点了下一首没反应」。
4. **播放页 `collapseToMini` 交列表**：把整张 `audioFiles` 映射成 `{url, title, base}`
   一起交给迷你条；不带列表，收起后听完一集就没人接手了。
5. **看门狗放过「已播完」**：元素停在末尾不再判定为卡死，交给 `onEnded` 正常推进。
6. **i18n**：`miniPlayer.prev` / `miniPlayer.next`（zh / zh-TW / en）。

### 不变

- 版本门禁全套保留：build.25 的构建期 `--build-arg` + 镜像内 `VERSION` 强校验、
  build.26 的六处 `tr -d '\r'` 与 `check-version-lock.py` 的 LF 写入。
- 后端接口未改。`app/dist` **将在出包时重建**——本版前端有改动，
  前端产物不再与 build.26 逐字节相同（指纹以出包后 `verify` 输出为准）。

## 4.6.0-build.26

> 主题：**修掉版本门禁自己造出来的「假 FAIL」**。build.25 在现场跑 `check-version.sh`，
> 五个版本号打印出来一模一样（都是 `4.6.0-build.25`），却连报三行 `!!` 并 `FAIL`。
> 根因不在部署，在取值：`webserver/version.py` 是 **CRLF** 行尾，而
> `sed -n 's/^VERSION...="\(.*\)"/\1/p'` 只替换到收尾引号，**行尾那个 `\r` 留在变量里**。
> `echo` 到终端时 `\r` 被当成「光标回行首」吃掉，肉眼完全看不出差别，
> 但 `pkg_version` 比 `image/container/api_version` 多一个字节，三次比较全不等。
> 反过来推：若运行期那三个也带 `\r`，它们就会相等而不报错 —— 所以那三处恰恰证明
> 镜像、容器、接口返回值本来就是干净的。

### 变更

1. **六处取值统一 `| tr -d '\r'`**：`scripts/check-version.sh`（4 处）、
   `scripts/deploy.sh`、`scripts/upgrade.sh`（2 处），以及交付侧的
   `check-deployed-version.sh` / `fix-build-layer.sh` / `recover.sh`。
   这条不只是显示问题：`deploy.sh` 若把带 `\r` 的值当 `--build-arg` 传下去，
   镜像里会写进一个看不见的控制符。
2. **断掉源头**：`scripts/check-version-lock.py --set` 原来用 `Path.write_text()`，
   在 Windows 上按 `os.linesep` 换行，**每次改版本号都把 version.py 写成 CRLF**（真凶就在这）；
   改为 `open(..., newline="\n")`。`webserver/version.py` 本身也已归一为 LF。
3. **修 `recover.sh` 的重启口径**：DSM 7.2 上套件叫 `ContainerManager` 而不是 `Docker`，
   `synopkg restart Docker` 直接失败；改为按 `ContainerManager → Docker → synoservice → systemctl`
   候选逐个试，并保留 180s 等待守护进程就绪。
4. **修 `recover.sh` 的两处小坑**：`PROJ` 支持从 `scripts/` 目录运行（自动回退到上级）；
   兜底 `curl | grep` 的模式补上冒号后的空格（`"version":"…"` 匹配不到
   Flask 的 `"version": "…"`，原来会静默空输出）。
5. **三个现场脚本入包**：`scripts/recover.sh`（镜像丢失 / `layer does not exist` 恢复）、
   `scripts/check-deployed-version.sh`（六步定位页脚版本断点，带 `--fix`）、
   `scripts/fix-build-layer.sh`（七步诊断构建层）。以前它们只在交付目录里散放，
   解压新包就找不到了。
6. **文档**：`docs/部署包说明.md` 新增「常见构建失败」一节，收录 build.25 现场踩到的三类问题
   （`layer does not exist`、`synopkg` 重启口径、`compose up` 误拉镜像导致站点中断）。

### 不变

- 前端代码未改，`app/dist` 与 build.25 **逐字节相同**（738 文件 / 71 入口页，
  `index.html` 仍是 `f8771fea…`，入口脚本 `fa08a4c/73f398b/f4ce4e7/7d03e7e`）。
- 最小化播放相关修复（build.23/24）全部保留，未回退。
- 版本锁九处载体 `--set 4.6.0-build.26` 一次改齐并复检通过。

## 4.6.0-build.25

> 主题：**把「页脚版本还是旧号」挡在部署阶段**。build.24 交付后现场出现一个问题：
> 镜像、容器、`dist` 都是新的，页脚却仍显示 `4.6.0-build.22`。根因是
> `webserver/version.py` 由 **构建期的 `GIT_VERSION`** 覆写，而现场保留了自用的
> `docker-compose.yml`（PUID/PGID、路径本地化），里面 `GIT_VERSION` 还是旧号 ——
> 用 compose 构建就把旧号写进了镜像。旧门禁只比对 `app/dist/index.html`，
> 完全看不到版本串，所以一路绿灯。

### 变更

1. **构建时显式传版本号**（`scripts/deploy.sh` / `scripts/upgrade.sh`）：
   `docker build --build-arg GIT_VERSION=<包内 version.py 的值>`。
   从此不再依赖 `docker-compose.yml` 里的 `GIT_VERSION`，现场那行写错也影响不到镜像。
2. **新增版本门禁**（两脚本构建后立刻执行）：`sh scripts/check-version.sh --image`，
   镜像内 `webserver.version.VERSION` 必须等于包内版本，不等即 `exit 1`，
   **容器不会启动**（站点保持旧版本可用，不会出现半新半旧）。
3. **启动后再次全链路自检**：容器内 `version.py` + `GET /api/user/info` 的 `sys.version`
   都必须是包内版本，否则 `exit 1` 并打印排查入口。
4. **新增 `scripts/check-version.sh`**：可单独运行，一次打印
   `pkg_version` / `compose_version` / `image_version` / `container_version` / `api_version`，
   带 `!!` 的行就是断点。支持 `--image` 只看镜像。
5. `scripts/upgrade.sh` 增加提示：compose 的 `GIT_VERSION` 与包内不一致时明确告知
   「本脚本会覆盖，但别手工 `docker compose build`」。

### 不变

- 前端代码未改，`app/dist` 与 build.24 **逐字节相同**（738 文件 / 71 入口页，
  `index.html` 仍是 `f8771fea…`，入口脚本 `fa08a4c/73f398b/f4ce4e7/7d03e7e`）。
- 最小化播放相关修复（build.23/24）全部保留，未回退。
- 版本锁九处载体 `--set 4.6.0-build.25` 一次改齐并复检通过。

## 4.6.0-build.24

> 本版只动「最小化播放」这条链路：把回页接管、被打断的 play、移动端挂起这三条静默失败路径补上自愈，
> 并重建 dist。build.23 已实装的常驻 `<audio>`、可拖动进度条、切源互斥保持原样，只做加固。

1. **回页接管改走页面的播放意图链路**（`app/src/pages/audio/_id.vue` · `adoptFromMini`）：
   原实现是 `player.currentTime = at; player.play().catch(() => {})`——位置写在 `loadedmetadata`
   前后都有可能，`play()` 一旦被判成 AbortError 就被 `catch` 静默吞掉，而本页看门狗只认
   `_wantPlay`（此时为 false）不会救，表现是「从迷你条回到播放页没声音，点一下播放才恢复」。
   现在改为 `_wantPlay = true` + `_playWhenReady()`（等 canplay、最多 40×250ms 重试，AbortError
   走 `safePlay` 的重新武装），并把接管到的位置同步回 `currentTime/progress`。
2. **接管期间服务端进度让路**：新增 `_adoptedFromMini` 标记，`tryRestoreFromServer()` 在接管后直接
   返回，并置 `_positionAppliedFor` 让 `loadTrack` 的定位重试链不再把位置改回 localStorage 的旧值
   （原实现两条链各写一次 `currentTime`，进度条会跳）。
3. **迷你条看门狗 + 回前台续播**（`app/src/components/MiniPlayer.vue`）：每 2s 检查
   「store 说在播、元素却停在 paused」的静默失败（被打断的 play、移动端切后台/锁屏挂起、seek 后
   停住），自动补一次 `play()`；连续 10 次救不起来就退回「暂停」，不再空转。
   `visibilitychange` / `pageshow` 回到可见时同样补一次，避免切后台再回来「条在播没声音」。
4. **`resume()` 的 AbortError 不再直接丢弃**：改为最多 3 次、间隔 250ms 的重试（成功后清零），
   覆盖「换源那一拍 play 被打断就永久静音」的情况。
5. **拖动到最右不再触发 ended**：`onSeekEnd` 的目标位置夹到 `duration - 0.5`（原来夹到 `duration`，
   拖到底会立刻 `ended` → 自动暂停）。
6. **dist 重建**：`eslint`（0 error / 4 条既有 camelcase warning）+ `nuxt build --spa`，
   738 文件 / 71 个入口页；`app/dist/index.html` 新指纹见交付说明。
7. **版本号**：九处载体由 `python3 scripts/check-version-lock.py --set 4.6.0-build.24` 一次改齐并复检通过。

## 4.6.0-build.23

> 本版只做「版本号与包名统一」：取消 `rebuiltN` 交付命名，运行期版本、包名、dist 指纹三者同号。

1. **版本号统一**：运行期版本统一为 `4.6.0-build.23`，九处载体一次改齐
   （`webserver/version.py`、`docker-compose.yml` 的 `GIT_VERSION`、`Dockerfile` 的 `ARG GIT_VERSION` 默认值、
   `app/package.json` / `package-lock.json`、`Makefile` 的 `VERSION_LOCK`、
   `scripts/check-version-lock.py`、`tests/test_version_lock.py`），由
   `python3 scripts/check-version-lock.py --set 4.6.0-build.23` 写入并复检通过。
2. **包名取消 `rebuilt`**：交付包统一为 `audiobook-deploy-4.6.0-build.23.tar.gz` 与
   `audiobook-src-4.6.0-build.23.tar.gz`；源码包内第一层目录同步为 `audiobook-src-4.6.0-build.23/`。
3. **dist 重建**：因 `app/package.json` 版本变更重新构建（eslint + `nuxt build --spa`），
   新 `app/dist/index.html` 的 sha256 与文件数见交付说明，部署后按该指纹验收。
4. **两包同源**：部署包与源码包对应文件逐字节一致（`Dockerfile`、`app/dist`、设置页、白名单、
   locale、`favicon.ico` 等）；源码包 `SHA256SUMS` 重算并与包内实际文件一致。
5. **迷你播放条「第二次收起无声」修复**：`<audio>` 元素移出 `v-if` 改为常驻（原来条隐藏时元素被销毁，
   再展开的新元素没有 src，而 url watcher 已按旧值跑过，于是第二次起无声）；`attach()` 增加 ref
   缺失时的 nextTick 兜底，`resume()` 在无 src 时自动补 attach；`loadedmetadata` 补写 `duration`
   （新 mutation `miniPlayer_duration`），刚展开即可拖动。
6. **迷你条真正切源（有声书 ⇄ 友链电台）**：切源前先 `hls.destroy()` 再换 `src`；`miniPlayer_play`
   覆盖源时旧音源先停再放；有声书页监听 `miniPlayerSig`，迷你条切到别的音源时页面立即停声并清掉
   播放意图；页面开始播放时反向关闭迷你条里的电台；从迷你条回播放页时只有「还在放这本书」才
   adopt 并 seek，否则页面保持静音、迷你条继续放。
7. **迷你条进度条可拖动**：整条 41px 为拖拽热区（按钮层级更高，不误触），拖动中 `timeupdate`
   不再覆盖显示值，松手才 seek 并写回 store；触屏用 pointer events + `touch-action:none`；
   电台/时长未知（NaN/Infinity）退化为静态线并显示「直播」，不出现无意义可拖动条。

## 4.6.0-build.22

> 相对 build.21 的增量：**交付前换行修复（CRLF→LF 全包 3644 文件）、dist 语言包补 4 键
> （作者归一化指引 openClean、设置页归堆标签）、上游 develop（至 fdf982a6）按主题移植 6 组**。

1. **换行纪律**：全包文本 CRLF→LF（修复 build.21 交付包容器 `start.sh` shebang 带 `\r`
   无法启动的交付事故）；新增 `.gitattributes` 强制 LF；`pack.sh --check` 增加换行检查
   与 dist/src 同步抽查（`openClean` 键）。
2. **EPUB 修复页 i18n 修复**（上游 `d7dd8af1`）：扁平点键→嵌套结构（`op.*`/`stage.*`），
   修复整页语言失效；检测结果/阶段文案分隔符不再硬编码；检测完成后进度条复位；
   后端新书上标 `（精修）` 走 i18n。
3. **OPDS 两处**（上游 `8ccab741`/`c0245c78` 适配）：必须登录时 `from=opds` 下载直链回
   401 挑战（原 200 JSON 会被阅读器存成假书）；`ENABLE_OPDS_SERVICE` 关闭后 OPDS 直链
   一并 404。
4. **「即将读完」三项修复**（上游 `606a5031`/`26509dd7`/`2b231705`）：手动标记读完的书
   不再占名额；排除用相关 NOT EXISTS（避免全表扫已读集合）；明细查询复查堵并发窗口。
5. **依赖升级**：tornado 6.5.9→6.6、social-auth-core 5.0.0→6.2.0（需重建镜像生效）。
6. **设置页**：新增「作者重名 / 别名归一」指路条目（三语）；dist 语言包补
   `authorNorm.openClean` 与设置页归堆标签（作者归一化功能本体 build.21 已有）。
7. **源码包内层缺陷修复**：`audiobook-nas-release.tar.gz` 的 overlay MANIFEST 有 27 行
   引用了内层未携带的文件（CHANGELOG.md、Dockerfile、app/locales/*、settings.vue 等，
   它们只在外层 overlay/files 里）——无 git 覆盖部署会漏掉这 27 个文件。本轮已从外层
   overlay 补齐进内层，内层三份清单（SHA256SUMS / overlay 两件）随之全量重生成；
   overlay 现在与清单逐行对账 0 差异。
8. **作者归一化指路升级**（用户反馈"一直说作者清理很突兀"）：设置页指路条目改为
   **可点击直达**（subtitle 字段新增 `to` 支持）；归一化页内链接文案标明
   「工具箱 → 作者清理」；设置页 tips 说明两个入口的分工。
9. **反馈弹窗内容管理员可改**：新增 `FEEDBACK_QR_URL` / `FEEDBACK_NOTICE` /
   `FEEDBACK_GITHUB_URL` 三个设置项（站点信息组），siteinfo 下发，反馈弹窗读配置；
   默认值保持上游行为，管理员可换自己的二维码/文案，仓库链接填 `-` 可隐藏按钮
   （不再指向上游）。
10. **实体书导入入口合并**：导入图书页的「批量导入实体书」按钮与弹窗下线
    （后端 `/admin/batch_add/run` 接口保留），实体书导入统一走「实体书」页的
    「导入实体书」（模板下载 + 逐行错误反馈）。
11. **工具箱新增「音频转写文稿」**（srt_tool）：选书直接转写 `.audio/` 里的音频，
    生成同名 `.srt`（faster-whisper，与 PC 版 srt-tool 同一识别内核 srt_core）；
    后台任务可取消（取消点前的识别结果写入），已有字幕跳过；依赖 faster-whisper
    （requirements-optional.txt），未安装时页面降级提示改用 PC 版。此前 srt-tool
    与网页转写接口都没有任何 UI 入口（用户发现的"大 bug"），本条补齐。
    **交付热修**：首版在 NAS 上启动循环——Dockerfile 未 COPY srt-tool/ 导致容器内
    `import srt_core` 失败拖垮 tornado。已修：srt-tool 目录移入 `webserver/toolbox/`
    （与既有工具同目录，随 webserver/ 整体 COPY 进镜像，不再需要单独 COPY）；
    srt_transcribe 的 srt_core 导入改为容错（缺失时工具降级，不再拖垮启动）。
12. **友情链接类型改为显式选择**（本次 rebuilt 新增）：原先前端按 URL / 名称推断
    友链类型，导致大量普通链接被猜成「电台」，点一下就意外开始播放。现在：
    - 后端 `FRIENDS[].type` 持久化；新增 `webserver/friend_links.py` 统一 canonical
      取值（`radio / website / bbs / video / news / book / link`）、历史别名
      （`stream→radio`、`forum→bbs`、`site→website`、`other→link`）与非法值清洗；
      保存时清洗，非法值不会写进配置；读取时容错非 list / 非 dict / 字段类型异常。
    - 后台设置页友情链接编辑新增「类型」下拉（七类），沿用原有增删改与上下移；
      老数据缺 `type` 时归一化为「网站」，可正常编辑、删除、前后新增、排序。
    - 前台图标按 `type` 显示（`mdi-web` 新增进 MDI 子集）；**只有「电台」类型
      点击触发底部迷你播放条，其余类型一律普通外链跳转**，不再按 URL 猜测。
    - 三套 locale（zh / en / zh-TW）补齐 `friend_type` 与七个类型名、提示文案。
    - `app/dist` 已重建（入口指纹见 `docs/部署包说明.md`「本次构建产物指纹」）。
13. **反馈弹窗设置修复 + 二维码后台上传 + 部署口径修正**（rebuilt8 新增）：
    - `FEEDBACK_QR_URL` / `FEEDBACK_NOTICE` / `FEEDBACK_GITHUB_URL` 此前只出现在
      `settings.py` 默认值与前端表单，未登记进 `webserver/base/setting_saver.py` 的
      `ADMIN_SETTING_KEYS`，导致后台保存被 `AdminSettings.post` 的白名单丢弃、刷新后
      回退默认值。三个键已补齐，保存即落盘、刷新生效（`PERSISTABLE_KEYS` 由其派生，自动跟随）。
    - **反馈二维码改为后台上传**：设置页「反馈二维码图片地址」下方新增选图 + 上传
      （`v-file-input` → `POST /api/feedback_qr`），复用作者头像上传的同一套基础设施
      （`@is_admin`、multipart、JPG/PNG/WEBP 校验）；写入容器 `/data/books/logo/feedback_qr.<ext>`
      （宿主 `/volume1/docker/audiobook-data/books/logo/`），目录不存在自动创建，
      返回 `/logo/feedback_qr.<ext>?v=<时间戳>` 自动回填输入框并即时预览。保留手填
      URL / 外链能力；不写镜像内路径，不需要重启容器；换扩展名时清理旧的其它格式文件。
    - 三语 `feedback_qr_url_tips` 由错误的 `app/public/logo/` 改为生产真实路径
      `/data/books/logo/`（宿主 `/volume1/docker/audiobook-data/books/logo/`），并说明可在页面上传。
    - 构建口径：`docker compose build` 在本机会走 compose 内嵌 BuildKit，其上下文快照
      按 `(mtime,size)` 判重，会复用旧 `dist`（表现为「新 `_nuxt` + 旧 `index.html`」，
      页面一直转圈）。统一改为 `DOCKER_BUILDKIT=0 docker build --no-cache`，
      启动用 `docker compose up -d --force-recreate --no-build`；
      `scripts/deploy.sh` / `scripts/upgrade.sh` 已同步，并在构建后比对镜像内
      `dist/index.html` 与包内文件。
    - 包内所有文件 mtime 常量换新（`1794019300` → `1794019500`），避免再次命中旧上下文快照。

    - `app/dist` 已按新前端重建：`index.html` sha256 `f698cb5b…`、入口脚本 `71819e1.js`。
    - **站点图标收敛为一张**：`app/public/logo/` 与 `app/dist/logo/` 删除全部
      `favico*`（`favicon_0.ico` ~ `favicon_8.ico` 一并移除），只保留新的 `favicon.ico`；
      后台「网站图标」下拉相应收敛为「沿用当前图标」，不再指向不存在的文件。
      `favicon.ico` 与默认反馈二维码 `link_gongzhonghao.jpg` 采用「缺失才补」：
      全新部署由 `deploy.sh` / `upgrade.sh` 写入 `/volume1/docker/audiobook-data/books/logo/`，
      存量站点一律不覆盖，需要更换由管理员手工覆盖或后台选图上传。

版本锁九处载体已由 `check-version-lock.py --set` 同步升号；CHANGELOG 本条为人工补写。
