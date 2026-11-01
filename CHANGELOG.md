# 变更日志（CHANGELOG）

本项目的版本号规则：**`<上游 mybooks tag>-<自建序号>`**
（上游 tag 无 `v` 前缀，如 `4.6.0`；自己改代码序号 +1，上游发新版序号归 1）

---

## 4.6.0-9（待发布）

> **这一版前后端都动了，必须重建镜像**（`upgrade.sh` 会自动做，约 4 分钟）。
>
> 核心一句话：**作者名不再被刮削搞乱，人工改过的作者也不会再被覆盖；
> 同名不同作者的书不会被误合并。**

### 背景：作者名为什么会乱

calibre 的目录结构是 `library/<作者>/<书名> (<id>)/`。
**作者名差一个字符，就是两个不同的目录，同一作者的书被物理拆到两处。**
而且拆开之后再合并，要搬文件夹、改数据库、重建索引，很麻烦。

脏作者名有三个来源，之前一条都没拦住：

| # | 来源 | 典型脏数据 |
|---|---|---|
| 1 | **有声书 ID3** 的 `artist` / `albumartist` | `某某听书`、`酷我音乐`、多歌手逗号连写 |
| 2 | **8 个元数据刮削源** | `(法)法布尔`、`王学富(译)`、`插画[美国]安德鲁·格拉斯` |
| 3 | **电子书内嵌元数据** | 出版社录入的 `温德著`、`韦东山 主编` |

更麻烦的是**刮削会把已经改好的作者又覆盖掉**：

> `autofill.py` 的 `should_update()` 用的是 `or` 判断——**缺封面 *或* 缺简介就触发刮削**，
> 压根不看作者写得好不好。触发后 `mi.smart_update(refer_mi, replace_metadata=True)`
> 直接把作者覆盖成刮削源的值。所以「先手工改好 → 过几天自动刮削又乱了」是必然的。

### 新增功能

| 功能 | 说明 |
|---|---|
| **S0 作者锁定** | 在界面上手动改过作者的书，打上 `#author_locked = 1` 标记。之后自动刮削**只更新封面/简介/标签，不碰作者**。日志会记一行「作者已锁定，保留 X（刮削值 Y）」，出问题能查 |
| **S2 作者别名表** | 同一作者的不同写法归一到标准名。落盘 `/data/toolbox/author_norm/config.json`，可手工编辑；支持繁简自动归一（`J·k·羅琳` 与 `J·K·罗琳` 同一个键） |

> **别名表默认是空的**——不预置任何数据，因为猜错的别名比不归一更糟。
> 什么都不配的情况下，这一版仍然生效的是 S0 锁定 + S1 清洗 + S3 刮削源清洗 + S4 入库归一。

### 修复 Bug

| Bug | 严重度 | 表现 | 修复 |
|---|---|---|---|
| **人工改好的作者被自动刮削覆盖** | **高** | 手工把作者改对，过几天自动刮削又变回脏名 | `autofill.py` 单本与批量两条路径都在 `smart_update` **之前**存下 `old_authors`，刮削后若已锁定则还原。批量路径的 `updates` 元组从 2 元扩到 3 元 |
| **`(法)法布尔` 这类国籍前缀清不掉** | **高** | 作者名带 `(法)` `[美]` `【英】`，看着一样的两本书分到两个目录 | `meta_helper.py` 复用已有 `_DYNASTY_REGION_PREFIX`；单字 `绘/校/注/译` 必须前面有空格才剥离（否则 `图图` → `图`） |
| **`插画[美国]安德鲁·格拉斯` 国籍剥不掉** | 中 | 「插画」挡在 `[` 前面，`^\[` 匹配不到 | 新增 `_DUTY_PREFIX`，执行顺序改为：`原作：` → **职责词** → 国籍/朝代。顺序不能换 |
| **`温德著` / `韦东山 主编` 后缀残留** | 中 | 作者名带「著」「主编」，目录名跟着脏 | `_AUTHOR_SUFFIX` 扩到 `绘\|校\|注\|原著\|改编\|主编\|插图` |
| **`王惟恒，李艳` 不拆，`李绍山、陈存军` 拆** | 中 | 同样是合著，顿号能拆、中文逗号不能拆，行为无法解释 | `_MULTI_AUTHOR_SEP` 补中文逗号 `，` |
| **`Rowling,J.K.` 被拆成两个作者** | 中 | 上一条修完后引入的新问题：西文「姓, 名」被逗号切开 | 新增 `_AUTHOR_INITIAL`，任一段是首字母缩写（`J.K.` / `JK`）时整体不拆 |
| **豆瓣 V2 把译者拼进作者** | **高** | `王学富(译)` 直接进作者字段，成为 `#translators` 之外的脏数据 | 六个刮削源（douban_v2 / baike / youshu / xhsd / neodb / ujxsw）统一在返回 `Metadata` 前过一遍 `guess_authors` |
| **刮削源清洗后 `mi.authors[0]` 崩** | **中** | 源返回 `著` / `[美]` / `佚名` 时清洗结果为空列表，紧接着 `mi.authors[0]` 抛 `IndexError`，整批刮削任务中断 | baike / xhsd / youshu 三处都改为 `mi.authors = _authors or [_raw or "佚名"]`，兜底用**原文**而不是「佚名」（保留信息量） |
| **有声书 ID3 的作者名完全不过滤** | **高** | `audios_import.py` 直接把 `artist` 写进作者，是全流程最大的一个口子 | 导入时先 `guess_authors` 清洗、再 `resolve_alias` 查别名表；清洗为空回退原文，不把有作者的书标成「佚名」 |

### 改动范围

**21 个文件：新增 4 个，修改 17 个。后端 15 个 + 前端 6 个。**

| 文件 | 增/删 | 改了什么 |
|---|---|---|
| `webserver/base/author_norm.py` | **新增 462 行** | 归一化核心：`clean_authors` / `author_norm_key` / `loose_author_key` / `author_key_set` / `authors_conflict` / `AliasStore` / `resolve_alias` / `resolve_author_list` / `lock_author` / `is_author_locked` |
| `webserver/handlers/author_norm.py` | **新增 270 行** | 管理接口 4 个 handler + `routes()` |
| `tests/test_author_norm.py` | **新增 248 行** | 32 个单元测试 |
| `app/src/pages/toolbox/author_norm.vue` | **新增 400 行** | 体检 + 别名表两个 Tab |
| `webserver/services/book_dedup.py` | +20 | **作者冲突守卫**（防同名不同作者误合并） |
| `webserver/base/meta_helper.py` | +34 / −7 | `_DUTY_PREFIX`、`_AUTHOR_SUFFIX` 扩展、中文逗号、`_AUTHOR_INITIAL`、执行顺序调整 |
| `webserver/handlers/book.py` | +28 / −3 | `edit_book` 归一化 + 打锁（兼容字符串入参）；**另 5 处入库/刮削路径只归一化、不打锁** |
| `webserver/services/autofill.py` | +29 / −4 | S0 锁定核心：单本 + 批量两条路径 |
| `webserver/services/audios_import.py` | +12 | 有声书导入归一化 |
| `webserver/plugins/meta/douban_v2/api.py` | +7 | 清洗（**保留**译者拼接行为，书页展示需要） |
| `webserver/plugins/meta/baike/api.py` | +7 / −1 | 清洗 + 空结果兜底 |
| `webserver/plugins/meta/youshu/api.py` | +7 / −1 | 清洗 + 空结果兜底 |
| `webserver/plugins/meta/xhsd/api.py` | +6 / −1 | 清洗 + 空结果兜底 |
| `webserver/plugins/meta/neodb/api.py` | +4 | 清洗 |
| `webserver/plugins/meta/ujxsw/api.py` | +4 | 清洗 |
| `webserver/constants.py` | +5 | `COLUMN_AUTHOR_LOCKED` / `CALIBRE_COLUMN_AUTHOR_LOCKED` |
| `webserver/main.py` | +4 / −1 | 注册 `#author_locked`（int 型）+ `author_norm` 路由 |
| `webserver/base/formatter.py` | +4 | 管理列表透传 `author_locked` 字段 |
| `app/src/pages/admin/books.vue` | +40 | 作者列锁图标 + 编辑框勾选 + 保存联动 |
| `app/src/components/AppHeader.vue` | +1 | 工具箱入口 |
| `app/locales/{zh,zh-TW,en}.json` | +44 / 各 | 44 个 `authorNorm.*` key + 3 个 `admin.books.*` key |

### 三个容易踩的设计坑（写在这里免得下次又踩）

1. **`norm_key` 不能当清洗用。** `(法)法布尔` 过一遍键函数得到 `法法布尔`——它把括号删了但留下了里面的「法」。所以必须**先 L1 清洗，再算键**，两步不能合并。
2. **`loose_key` 抓不到中英双写。** 去掉字母后 `J.K. Rowling` 变成空串，本意是让 `罗琳 (J.K.Rowling)` 能对上 `罗琳`，但对纯英文名直接失效。
3. **`_` 是 i18n 函数，不能拿来接译者列表。** 写 `_authors, _ = guess_authors(...)` 会把整个文件的 `_("...")` 全部弄崩。统一改用 `_trans` / `_cleaned_trans`。合并脚本里有一道专门的自检挡这个。

### 补丁包

| 文件 | 大小 | 说明 |
|---|---|---|
| `audiobook-patch-4.6.0-9.tar.gz` | 约 110 KB | 21 个文件，覆盖即用（含前端） |
| `audiobook-deploy-4.6.0-9.tar.gz` | 94 MB | 完整可部署包（基于 `-8` 合并） |
| `merge-4.6.0-9.sh` | 11 KB | 合并脚本，含 21 项校验 |

### 部署

```sh
# 三个文件都放 /volume1/docker/
sh merge-4.6.0-9.sh
sh /volume1/docker/audiobook/upgrade.sh /volume1/docker/audiobook-deploy-4.6.0-9.tar.gz
```

**必须重建镜像**，两条理由，任一条都够：

1. 新增了 calibre 自定义列 `#author_locked`，`main.py` 启动时会自动建列；
2. **本版含前端改动**（管理页锁图标、作者归一化页面、三语文案），必须重新 `npm run build-spa`。

`upgrade.sh` 会自动完成这两件事，不需要手工操作。构建约 4 分钟。

### 验证

| 项目 | 结果 |
|---|---|
| 32 个单元测试（有 / 无 OpenCC 两种环境） | 全过 |
| 28 例清洗回归（21 正例 + 7 反例） | 全过 |
| 33 例极端输入（`著` / `[美]` / `空串` × 3 个源） | 零崩溃 |
| 9 个端到端场景（锁定保留 / 未锁归一 / 繁简归一 / 空值不崩 / 目录合并 / 打锁 / 字符串入参 / 未登记保留） | 全过 |
| 合并脚本真实演练（基于 `-8` 部署包） | 通过，BOOK_NAV 13 组 + 文案键 2457 个未受损 |
| **9 例作者冲突判定**（法布尔/繁简/路遥vs天蚕土豆/佚名/曹雪芹/Unknown） | 全过 |
| **体检报告实测**（DUP 3 组 / SUS 1 组 / DIRTY 3 条，canonical 选对） | 全过 |
| **三语文案键完整性**（前端用到的 136 个 key × 3 语言） | **缺失 0** |
| **i18n 插值参数一致性**（16 处 `$t(k, {…})` 与文案占位符比对） | **全对** |
| **Vue 模板非法标签名扫描**（`<div:key=` 这类） | **0 处** |
| **前后端路由对齐**（5 个接口路径逐条比对） | 全对 |
| 21 个文件语法检查 | 全过 |

反例（**不该动**的，确认没被误伤）：`图图` / `绘心` / `张文` / `绘图：王五` / `Rowling,J.K.` / `J·K·罗琳` / `张三`。

### 升级后要做什么

1. **重启后看日志**：搜 `[AUTHOR_NORM]`，能看到打锁与命中的记录。
2. **手工改一次作者试试**：改完等一轮自动刮削（或手动点刮削），确认作者没被改回去。
3. **别名表按需配**：默认空的，不用就不配。配了才生效，位置 `/data/toolbox/author_norm/config.json`。
   **也可以直接在界面上配**：侧边栏「工具箱 → 作者归一化」（`/toolbox/author_norm`），见下节。
4. **存量脏数据这一版不清理**——只保证不再产生新的。跑一次体检知道有多脏，再决定怎么清。

### 追加：管理界面与同名重复书守卫（4.6.0-9 第二批）

第一批只做了后端，这一批把管理界面补齐，并修了一个**会丢书**的隐患。

#### 修 Bug：同名重复书清理会误合并不同作者的书

`book_dedup.py` 原来只按**书名**分组，判断方向时只看「电子书 / 音频」的分布：

```python
len(with_ebook) == 1 and with_audio    # 就算 merge
```

**全程没比过作者。** 所以《人生》（路遥，epub）+《人生》（某个网络作者，音频）
会被判成重复书直接合并——音频挂到路遥那本下面，或者反过来，**书就串了**。

修法是在方向判断之前加一道作者冲突守卫：

```python
if authors_conflict(ebook_authors, b["authors"]):
    return {... "action": "skipped",
            "reason": "作者不同（路遥 vs 天蚕土豆），不是重复书，请人工确认"}
```

`authors_conflict()` 的判定刻意做得**宽松**：

| A | B | 判定 | 为什么 |
|---|---|---|---|
| `法布尔` | `(法)法布尔` | 不冲突 | 先 L1 清洗再算键，两者同键 |
| `J.K.罗琳` | `J·k·羅琳` | 不冲突 | 繁简 + 分隔符归一后同键 |
| `路遥` | `天蚕土豆` | **冲突** | 两个非空键完全不相交 |
| `佚名` | `路遥` | 不冲突 | **任一边为空一律不判冲突** |
| `Unknown` | `路遥` | 不冲突 | 同上，占位名不算有效作者 |

> **宁可放过，不可误杀。** 判成冲突只是跳过合并（书还在，人再看一眼），
> 判成不冲突则会真合并（很难回退）。所以空白/占位作者（`佚名`/`未知`/`Unknown`）
> 一律从键集合里剔除，不作为「这是另一个人」的证据。

例：9 个用例全部按预期通过，其中 `曹雪芹,高鹗` vs `(清)曹雪芹` 判为不冲突（有交集）。

#### 新增：作者归一化管理页 `/toolbox/author_norm`

侧边栏「工具箱」下新增入口，两个 Tab：

**Tab 1 · 体检**（只读，不改数据）

按归一化键给全库作者聚类，报三类：

| 类别 | 含义 | 建议 |
|---|---|---|
| **确定重复** | 归一化键相同、显示名不同（`法布尔` / `(法)法布尔`） | 高置信，一键加入别名表 |
| **疑似重复** | 键不同但一个名字包含另一个（`罗琳` / `J.K.罗琳`） | 需要人确认，可能是两个人 |
| **脏名候选** | L1 清洗后名字变了（`温德著` → `温德`） | 不一定要动，存量走「作者清理」 |

标准名（canonical）的选取规则：**优先选 L1 清洗后没变的写法**（`(法)法布尔` 和 `法布尔` 之间选后者），
再按书数降序。

> 体检**故意不改数据**。归一化键相同只能证明「写法可能指同一人」，不能证明「一定是同一人」
> （张三/张叁可能是两个人）。合并决策必须人来看，落地机制是别名表。

**Tab 2 · 别名表**

可视化编辑 `config.json`：标准名 + 别名列表 + 备注。支持增删规则、增删别名、
`never_merge` 名单（永不归一的词）。右侧有「归一化预览」输入框——输入一个作者名，
实时显示「清洗后 → 算键 → 查表命中 → 最终结果」，调规则时不用真导一本书来试。

#### 新增：作者锁图标

管理端「书籍列表」的作者列，已锁定的书后面显示一个小锁图标：

* **点锁 = 解锁**（调 `PUT /api/admin/book/<id>/author_lock`）
* 打开作者编辑框时，底部有「保存后锁定作者」勾选框，默认跟随当前锁定状态
* 改完作者点保存，按勾选状态自动落锁/解锁
* **批量编辑不动锁**（避免一次改一批书时把大量书误锁）

#### 新增接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/admin/author_norm/scan` | 体检报告（只读） |
| GET | `/api/admin/author_norm/alias` | 读别名表 |
| POST | `/api/admin/author_norm/alias` | 存别名表 |
| POST | `/api/admin/author_norm/test` | 归一化预览 |
| PUT | `/api/admin/book/<id>/author_lock` | 单本开锁/落锁 |

全部 `@is_admin` 保护。

### 打包 bug：部署包带进了运行时数据目录（`cache/` `sync/`）

**这是 4.6.0-9 首次打包时的失误，已在重出的包里修好。** 记在这里，避免下次再犯。

| 项 | 内容 |
|---|---|
| **现象** | `deploy.sh` 第 6 步「源码目录污染自检」报 `!! 源码目录出现数据类目录: sync cache`，中止部署 |
| **根因** | 基准包 `audiobook-deploy-4.6.0-7/8.tar.gz` 里就带着 `cache/`（52 张缩略图）和 `sync/1/reading.json`。`merge` 脚本解压基准包再重打包，原样继承了下来。**从 `-7` 起每个包都有** |
| **为什么没早发现** | 合并脚本只清了 `.git` / `__pycache__` / `*.pyc`，**从没检查过数据类目录** |
| **危害** | ① 污染新源码目录，部署中止；② `sync/1/reading.json` 是**旧快照**（`cached_through: 2026-10-29`），解压会盖掉现役文件，**阅读进度回退** |
| **修法** | `merge-4.6.0-9.sh` 增加「剔除运行时数据目录」步骤，移除 `cache/` `sync/` `books/` `audio/`，并在重打包后**复检**，残留则中止 |

> **⚠️ `calibre/` 不能一起删。** 它看着像书库数据，其实是 35 条**源码**路径
> （`calibre/7.6/calibre/*.py` 补丁 + `calibre/plugins/cbz_meta/` 等自定义插件），
> 删了镜像构建直接失败。真正的地点数据在 `/volume1/docker/audiobook-data/books`。
>
> 第一版修复时我错把它写进了剔除列表，实测后撤掉了。脚本里留了注释挡住这个坑。

**上游也没做对**：`.gitignore` 没忽略 `sync/` `cache/`，`.dockerignore` 只排除了
`__pycache__` 和各类 `.xxx_cache`，**没排除根目录的 `cache/`**。所以这是上游的疏漏，
不只是我们的打包问题。

#### 根治：从忽略文件层面堵住

只清部署包是治标——每次 `git add .` 或 `docker build` 还会把数据带进去。这次改了根因：

| 文件 | 补充 | 作用 |
|---|---|---|
| `.gitignore` | `cache/` `sync/` | 运行时生成的缩略图与阅读进度快照不再入库 |
| `.dockerignore` | `cache` `sync` `books` `audio` | 不进构建上下文，layer 不再被几百张图拖慢 |

同时执行了 `git rm -r --cached cache sync`，把**已经跟踪**的 51 个运行时文件移出索引
（磁盘文件保留，不影响运行）。

#### 顺手修掉一个会让构建失败的历史损坏

整理时发现仓库里有 8 个 `.vue` 被早期的一次性脚本 `fix-template-key.py` **改坏了**——

```html
<!-- 坏的：:key 粘进了标签名，这是非法标签 -->
<div:key="'w-' + f.key" :id="'f-' + f.key">

<!-- 对的 -->
<div :key="'w-' + f.key" :id="'f-' + f.key">
```

受影响文件：`settings.vue` / `BookCards.vue` / `BookListAddBooksDialog.vue` /
`FolderEditor.vue` / `ServerFileBrowser.vue` / `folder.vue` / `login.vue` / `tag.vue`。

这种写法 **ESLint 报错、`nuxt build` 直接失败**，但因为一直是从源码树打包、
没走过仓库这条路，所以没暴露。现在已全部改回正确写法，并加了扫描复检（0 处残留）。
那个 `fix-template-key.py` 也一并删了——它会制造问题，不是解决问题。

### 文档与仓库整理（归一）

工作区积累了大量历史产物，`ls` 一眼看不完。这次清掉 20 个文件，**从 30 个减到 10 个**：

| 删除 | 理由 |
|---|---|
| `merge-4.6.0-4.sh` ~ `-8.sh`（5 个） | 被 `-9` 完全取代，校验清单只增不减 |
| `merge-patch2.sh`、`merge-patch3.sh` | 更早期的打包脚本 |
| `fix-eslint-final.py`、`fix-template-key.py` | 一次性脚本，后者还会改坏文件 |
| `UPSTREAM_DIFF_4.6.0.md` | 一次性对照报告 |
| `UPSTREAM_UPGRADE.md` | 与 `START_HERE.md` 第三章重复 |
| `如何执行.md` | 与 `NAS操作手册.md` **重复 90%**（同样 0→6 步） |
| `audiobook-scripts.tar.gz` | 旧脚本包 |
| `audiobook-patch-4.6.0-1` ~ `-8.tar.gz`（8 个） | 历史补丁包 |
| `audiobook-4.6.0-8-full.tar.gz` | 旧 full 包 |
| `changed-files/`、`dist/`、`v9/changed-files-README.md`、`__pycache__/` | 打包残留 |

**留下的 10 个**，每个都有不可替代的用途：

| 文件 | 用途 |
|---|---|
| `audiobook-deploy-4.6.0-9.tar.gz` | 部署包 |
| `audiobook-patch-4.6.0-9.tar.gz` | 补丁包 |
| `audiobook-4.6.0-9-full.tar.gz` | 完整源码包 |
| `merge-4.6.0-9.sh` | 本轮合并脚本 |
| `protect-custom.sh` | 保护 BOOK_NAV 与三语文案 |
| `upgrade-upstream.sh` | 跟随上游升级 |
| `START_HERE.md` | 操作总纲（升级/改代码/Gitee/回退） |
| `CHANGELOG.md` | 本文件 |
| `NAS操作手册.md` | 本次升级逐步操作 |
| `设计稿-4.6.0-9-作者归一化.md` | 归一化设计依据 |

> 归并原则：**同一个问题只留一份文档**。`START_HERE.md` 是总纲，遇到具体问题往下翻；
> 逐步操作看 `NAS操作手册.md`；`如何执行.md` 与之重复，删。

### 追加：繁体 epub 打开慢 — 坏字体剥离（4.6.0-9 第三批，v9 包）

> 完整排查与测试记录见 `坏字体修复-4.6.0-9-归档.md`。

**问题**：一本 3.11MB 的繁体 epub 打开要 50-60 秒，console 报
`OTS parsing error: invalid sfntVersion: 1179602516`（= ASCII `FONT`）。
calibre 从 PDF 转 epub 时把带子集加密的字体原样搬进包里，这种以 `FONT`
魔数开头的伪字体不是合法 sfnt，浏览器一律拒绝加载；数据本体是加密的，
**无法还原，只能删**。实测该书 4 个坏字体占全书体积 **52.4%**。

**修复（三件套，共用 `webserver/services/epub_font_fix.py`）**：

| 链路 | 文件 | 时机 |
|---|---|---|
| B 新书转换 | `services/converter.py` + `batch_convert.py` | 转换出包后就地清理 |
| A 旧书下载 | `handlers/book.py`（`epub_lite_path` + 负缓存） | 首次下载生成精简副本，缓存在 `CACHE_DIR/epub-lite/` |
| C 存量清扫 | `tools/fix_broken_fonts.py`（命令行） | dry-run / --apply / -r / --json |

另有阅读器侧兜底（`static_files.py`：坏字体 404 + no-store，CSS 动态剥离坏 `@font-face`）。

**效果**：样本 3.11MB → 1.65MB（省 46.9%），正文逐字一致；
用户实测打开从 50-60 秒降到 **1.15 秒**（`[open-perf] total=1155ms`）。

**踩坑记录**：`mkstemp` 产生的 0600 权限会经 `shutil.move` 带进书库导致
calibre/nginx 读不到——替换前必须恢复原文件的 mode/uid/gid/mtime。

**部署**：用 **v9 包** `audiobook-deploy-4.6.0-9-v9.tar.gz`
（md5 `ef924442b42b7fbf631a0284b149469d`）。v8 缺这批改动，勿用。
白名单 `build/patch-files-v3.txt` 已补 4 条。

---

## 4.6.0-8（待发布）

### 修复 Bug

| Bug | 严重度 | 表现 | 修复 |
|---|---|---|---|
| **管理员被自己的读者组拦住** | **高** | 用 admin 登录后打开任意书籍详情页，四个按钮全灰（置灰不可点）；书架、分类、标签也少一截 | `is_book_visible()` 漏了 `is_admin()` 豁免——分类列表那边（`book.py::_filter_categories_by_reading_range`）一直有，判定入口这里没有，于是管理员和普通组员走同一套限制。补上后管理员永远全可见 |
| 标签列表同样漏豁免 | 中 | 管理员侧边栏标签数量比实际少 | `base.py::_filter_tags` 与 `meta.py::_filter_tags` 两处独立实现，都只读 `read_limit`，一并补管理员豁免 |
| WebDAV 挂载对管理员限流 | 低 | 管理员用 WebDAV 挂载时只能看到组内那几本 | `dav_provider.py::_get_user_reading_range` 新增 `admin` 判定，返回"不受限" |
| **Podcast 分类页 / 标签页恒 404** | **高** | `/podcast/category/绘本`、`/podcast/tag/少儿` 一律 404，首页菜单点进去全挂 | 两处调用漏传 `user`，provider 把「没传 user」当成「未登录」直接返回空 dict。补上 `self.current_user` |
| **Podcast 分类过滤直接把 dict 变 list** | **高** | 只要用户受限且点分类页，`'list' object has no attribute 'keys'`，500 | `categories = [c for c in categories …]` 丢掉了值和类型，改为按 key 重建 dict：`{c: v for c, v in …}`。`get_tags` 同病 |
| **Podcast 单书订阅源无权限校验** | **高** | 知道 book_id 就能拼 `/podcast/book/<id>` 拿到整本音频订阅，读者组形同虚设 | 两个入口（匿名 + token）都补 `filter_book_ids` 校验，不在范围内一律 404（不用 403，避免被拿来枚举书目） |
| `/podcast/all` 不按用户过滤 | 中 | 全库有声书订阅源对任何登录用户都是全量 | 改为 `filter_book_ids(get_all_audiobook_ids(), current_user)`，未登录返回空 |
| Podcast 分类/标签/作者只读用户自身设置，不认读者组 | 中 | 用户自己的 `read_limit` 为 0 但在「儿童组」里，Podcast 首页照样列出全部目录 | 统一走 `ReaderGroupService.effective_limits()`，与网页端同一套口径；管理员豁免一并生效 |

> 根因是同一件事在 5 处各写了一遍判定（网页 / 标签两处 / WebDAV / Podcast），补一处就会漏四处。
> 这次全部统一为：**未登录 → 空条件书；管理员 → 全放行；其余 → 走生效限制。**
>
> Podcast 那套更彻底——它自带一份"读 user.read_limit"的实现，既不看读者组、
> 也没有管理员豁免，分类页还因为漏传 user 而永久 404。等于读者组管不到播客，
> 而管理员反而被播客拦住。这次让 Podcast 直接复用 `ReaderGroupService`，
> 以后调权限规则只需改一处。

### 新增功能

| 功能 | 文件 | 说明 |
|---|---|---|
| 详情页有声书弹窗加进度记忆 | `app/src/components/AudioListDialog.vue` | 试听中途关掉弹窗，重新打开自动回到上次位置，章节行右侧显示「上次听到 12:34」 |
| 弹窗内进度条 | 同上 | `v-slider` 可拖动定位，下方显示 `当前 / 总长`；原来只能听不能拖 |

实现要点：

- 键名 `audiobook_preview_<用户ID>_<书ID>_<章节url哈希>`，**按章节隔离**——不同章节时长差异大，按书存一个进度会出现「听第 3 章，点第 1 章却从第 3 章位置开始」。
- 恢复时机放在 `canplay` 且 `duration` 已有值之后，避开 HTMLAudio 元数据刷新把 `currentTime` 打回 0 的坑。
- 听完（距结尾 3 秒内）自动清 key，下次从头；`pagehide` 与 `beforeDestroy` 双保险各存一次（iOS Safari 不触发 `beforeunload`）。
- 与正式播放器（`/audio/:id`）的 `audiobook_progress_*` **互不干扰**：那套记的是「音轨索引 + 轨内偏移」（一本多轨），弹窗这套记的是「单文件秒数」。

### 界面调整

| 调整 | 说明 |
|---|---|
| **有声书导入挪进「导入与存储 · 上传」** | 原来单独挂在「阅读与浏览」下，跟它实际干的事（决定音频遇上同名电子书时是挂靠还是新建）对不上。现在紧跟「忽略根据书名和作者的同书检查」——两个开关管的是同一件事，挨着放才看得懂 |
| **「读者组分级权限」移到「默认权限与配额」下方** | 原来藏在「访客与公开访问」后面，滚半天找不到。现在紧跟默认配额，进去第一眼就是「启用阅读范围控制」这个总开关 |
| 总开关改名并加说明 | `ALLOW_READ_RANGE_SETTING` 的标签从「允许设置阅读范围」改为「启用阅读范围控制（总开关）」，并补一句 tips：关闭时所有读者组规则一律不生效，所有人按公开访问权限看全库 |

> 关于「这个开关能不能和用户组合并」——**不能合并，它俩是两层**：
> `READER_GROUPS` 定义「哪些书给谁看」，`ALLOW_READ_RANGE_SETTING` 是「这套机制要不要启用」。
> 合并掉开关会有一个说不清的状态：想让所有组都失效，就得把组一个个删掉，
> 但用户身上还留着 `reader_group` 引用，下次再打开就变成「组不存在 → 一本书都读不到」。
> 保留开关，关掉时是干净的「全员放开」，随时能开回来。界面上按上面那样挪位置，就不容易被忽略。

### 修复 Bug（续）

| Bug | 严重度 | 表现 | 修复 |
|---|---|---|---|
| **`settings.vue` 有 5 处 `<template v-for>` 的 `:key` 写错位置** | 中 | Vue2 里 `<template v-for="x in y" :key="...">` 是无效写法——编译器会**直接丢弃这个 key** 并报 `cannot be keyed`，列表渲染退化为「按索引复用」，出现勾选串行、输入框内容跟着跑 | 5 处全部改为把 key 放在真实子元素上 |

> **更正一处此前的判断**：早先我说「全仓 16 处错误、涉及 12 个 vue」，那是批量 grep 的误判。
> 逐文件核对上游原文后确认：**只有 `admin/settings.vue` 一个文件真有问题（5 处）**，
> 其余 10 个 vue（`AppHeader`/`BookCards`/`FolderEditor`/`ServerFileBrowser`/`folder`/`login`/`tag` 等）
> 上游写的本来就是对的——只是把 `:key` 换行写在下一行，或者属性顺序和我们不同，语法完全正确。
> 那 10 个文件已**全部还原为上游原版**，不进补丁（放进去只会增加合并冲突面）。
>
> 批量替换过程中还误伤出两类问题，都已修复并加了自动检查：
> - **11 处标签名粘连**：`<v-chip:key=` 少了空格，会被解析成名为 `v-chip:key` 的标签。
>   Vue 编译器**不报错**（HTML 解析器容忍），但浏览器里这个标签渲染不出来。
> - **1 处注释被污染**：`:key="'w-' + grp.key"` 被塞进了 `<!-- 注释 -->` 里，同时那个 `div` 丢了 `:key`。
>
> 教训：`<template v-for :key>` 这类批量替换没法靠「看起来规范」判断对错，
> 只能拿上游原文逐文件比对，或者用编译器实测。这次两样都补上了。

### 补丁包

`audiobook-patch-4.6.0-8.tar.gz`（16 个文件：5 个后端 py + 6 个 vue + 3 个 locale + 2 个脚本）
**含前端改动，需要重新构建镜像**（约 4 分钟）。

其中 `folder.vue` / `FolderEditor.vue` / `ServerFileBrowser.vue` 三个是**上游原版逐字节一致**的，
进包的原因见下一节——`-7` 基准包里这三个文件是旧写法，不覆盖就构建不过。

改动文件的实际内容见 `changed-files/` 目录（与项目同结构），逐条说明见 `changed-files/README.md`。

### 修复：Docker 构建卡在 `vue/valid-v-for`

| 项 | 内容 |
|---|---|
| 表现 | `docker compose build` 到 `[mybooks builder 8/8] RUN npm run build-spa` 失败 |
| 报错 | `FolderEditor.vue 6:17` / `ServerFileBrowser.vue 23:17` / `folder.vue 10:11`，均为 `Custom elements in iteration require 'v-bind:key' directives  vue/valid-v-for` |
| 直接原因 | `build-spa` = `eslint --ext .js,.vue src && nuxt build --spa`，`vue/valid-v-for` 是 error，`eslint` 返回非 0，`nuxt build` 根本没执行 |
| 根本原因 | `-7` 基准包里这三个文件是「`<template v-for :key>` + 子元素无 key」的历史遗留。Vue2 编译会把 template 上的 key 丢掉，移到子元素后子元素仍缺 key，于是规则报错 |

上游 4.6.0 这三个文件本身是对的（每个子元素各带 `:key`）。所以修法是**用上游原版覆盖**，
把 key 逐个放回 `<v-icon>` / `<v-chip>` / `<v-text-field>` / `<span>` 上。

> 澄清一个容易搞错的点：`vue/valid-v-for` 只要求"该元素有没有 key 属性"，
> **不要求 key 写在属性第一位、也不要求同行**。实测把 `:key` 放在 `:color` 之后跨行写，
> 规则照样通过。所以不需要为了这条规则去调属性顺序。

新增兜底脚本 **`fix-eslint-final.py`**，`merge-4.6.0-8.sh` 现在**无条件**跑一遍（以前只在发现
`template:key` 时才跑）：

| 能力 | 说明 |
|---|---|
| `<template v-for :key>` | key 下移到第一个真实子元素 |
| 子元素缺 key | 自动补 `:key`，索引变量从最近的外层 `template v-for` 取（`(item, idx)` → `idx`） |
| `<v-chip:key=` 粘连 | 补空格 |
| 补不了的 | 打印文件+行号，退出码 1，**不让有问题的包进入构建** |

打包前后各查一次：注入前查基准包、打包后再查成品。任一处残留就中止，不出包。

实测：
- 模拟 `-7` 基准包注入 16 处错误 → 全部修正 → **118 个 .vue 的 ESLint 0 错误、模板编译 0 错误**
- 用真实 `-7` 基准包端到端跑 `merge-4.6.0-8.sh` → 出包 95MB，成品 ESLint 0 错误
- 幂等：对已修好的源码再跑一次，文件零改动

### 脚本：保护 BOOK_NAV 与三语文案

新增 `protect-custom.sh`，三动作 `save` / `apply` / `check`，已接入两条升级链路。

**为什么需要**：上游升级时 `webserver/settings.py` 和 `app/locales/*.json` 会被整段替换，
而这两处恰好是我们改动最集中的地方——`BOOK_NAV` 上游 9 组、我们 13 组，被覆盖后分类导航直接变回上游版；
文案被覆盖后，界面会显示 `settings.reader_group_strict` 这样的原始键名。**不报错，只是功能静默消失**，
最难发现。

| 动作 | 时机 | 行为 |
|---|---|---|
| `save` | 合并前 | `BOOK_NAV` 整段 + 3 份 locale → `/tmp/custom-snap` |
| `apply` | 合并后 | `BOOK_NAV` 整段替换回去；locale 按 key 递归合并（我们的键补回，上游新增键保留） |
| `check` | 打包前 | `BOOK_NAV` 少于 13 组报错；文案键逐一比对快照，缺哪个报哪个 |

设计取舍：
- `BOOK_NAV` **整段替换**而不是逐行 merge——上游改这段时是「重排分类」，逐行 merge 只会产出一堆无意义冲突。
- locale **按 key 合并**——上游可能新增键，我们只负责把自己的补回去。
- `check` 有快照就按快照逐键比对（不漏任何自定义键），没快照退回 6 个关键键兜底。

接入点：
- `upgrade-upstream.sh`：步骤 3 合并前 `save`；冲突解决后 `3.2 apply + check + 提示 commit`；步骤 4 打包前再 `check` 一次。
- `merge-4.6.0-N.sh`：注入补丁后 `check`，不通过直接中止（不出包）。

实测（用真实源码走完整链路）：
- 正常：13 组 / 2457 个文案键，通过
- 模拟上游覆盖：准确报出「BOOK_NAV 只有 9 组」+ 缺失的 4 个键，退出码 1，未出包
- `apply` 后：4 个文件与原始源码**逐字节一致**
- 上游新增键场景：新键保留、我们的键回归，双向都对

---

## 4.6.0-7（待发布）

### 修复 Bug

| Bug | 严重度 | 表现 | 修复 |
|---|---|---|---|
| **成员指向已删除的组 → 静默放行全库** | **致命** | `group_def` 为 `null`、`source` 为 `none`，用户明明"在组里"却能看到所有书 | 组名对不上时不再当作"不限权"，改为按【受限且一本书都读不到】处理（`source: group-missing`）；读组列表时自动清理这些悬空引用，界面顶部弹出黄色告警列出「组名 → 受影响用户」 |

> 触发场景：删组后重建同名组、改名过程中断、从别的机器导入 db 但没带 `READER_GROUPS` 设置。
> 这是权限系统里最危险的兜底方向——数据一脏，权限就静默全开。

| 分类/标签「或」关系不够明确，容易误以为要两边都填 | 中 | 只填标签却被要求也匹配分类，看起来像"选了绘本却看不到书" | 匹配逻辑本就是「或」，但界面上没写清；补齐说明文案，并在 `is_book_in_reading_range` 里显式拦掉"两边都空"（原来借空集合的副作用恰好成立，黑名单则会反向全放行） |

### 新增功能

| 功能 | 文件 | 说明 |
|---|---|---|
| 规则说明补充 | `app/src/components/ReaderGroupEditor.vue` | 表单下方明确写出：分类与标签是「或」，只填一边就够 |
| 悬空引用告警条 | `app/src/components/ReaderGroupEditor.vue` | 黄色 Alert 显示「已删除的组名 → 这些人」，并提示重新分配即可恢复 |
| 自动修复 | `webserver/services/reader_group.py` | `clear_members_of()`：读列表时清掉失效的组引用并写日志，不留下"看不见的病人" |

### 补丁包

`audiobook-patch-4.6.0-7.tar.gz`（222KB，与 4.6.0-6 相同的 12 个文件）
**需要重新构建镜像**。

> 4.6.0-6 未被采用（发现悬空引用问题后合并进 4.6.0-7 一起出），两者内容叠加。

---

## 4.6.0-6（未独立发布）

### 修复 Bug

| Bug | 严重度 | 表现 | 修复 |
|---|---|---|---|
| **白名单组一个条件都没填 = 放行全库（权限完全失效）** | **致命** | 建个「儿童组」白名单、分类和标签都不填，组员照样能看所有书；清空用户名单后也一样 | 新增严格模式 `READER_GROUP_STRICT`（默认开）：白名单空条件 → 返回永不匹配的哨兵条件，成员看不到任何书。想回到原版「空 = 不限权」，在设置里关掉该开关 |

> 这是移植时从上游继承的语义：mybooks 原版认为「白名单空条件 = 不限权」。
> 但读者组是管理员手工建的规则，只写组名不填条件时本意几乎总是「先锁住再配」，
> 放行全库会让整套权限看起来完全失效。故改为默认严格，并可一键切回。

### 新增功能

| 功能 | 文件 | 说明 |
|---|---|---|
| 设置页「严格模式」开关 | `app/src/pages/admin/settings.vue`<br>`webserver/settings.py` | 用户与访问 → 读者组，带说明文字；保存立即生效，不需要重启 |
| 表单空条件实时警示 | `app/src/components/ReaderGroupEditor.vue` | 白名单且分类标签都为空时，保存按钮上方出现橙色提示 |
| 权限排障接口 | `webserver/handlers/reader_group.py` | `GET /api/admin/reader_groups/debug?username=xxx`，一次看清：总开关、所属组、组定义、生效规则及来源（self / group / group-strict / none） |

### 补丁包

`audiobook-patch-4.6.0-6.tar.gz`（221KB，12 个文件：5 个后端 py + 5 个前端 + 2 个脚本）
**含前端改动，需要重新构建镜像**（约 4 分钟）。

---

## 4.6.0-5

### 修复 Bug

| Bug | 严重度 | 表现 | 修复 |
|---|---|---|---|
| **`container is marked for removal and cannot be started`** | **高（服务起不来）** | 上一次 `compose down` 被打断，容器卡在 `State=removing`；下次 `up -d` 无法启动它 | 停容器后等它真正退出；起容器前若检测到 `removing` 残留，先清理再 up |
| 升级结尾误报 `unix:///var/run/supervisor.sock no such file` | 低（仅误报，不影响服务） | `upgrade.sh` 固定 `sleep 20` 后立刻 `supervisorctl status`；容器此时还在跑 `--syncdb` / `--update-config`，supervisord 尚未 exec，socket 自然不存在 | 改为轮询：容器 Running → 等 sock 出现（最多 3 分钟）→ 等 4 个 program 全 RUNNING → 容器内 HTTP 自检，非 200 才提示 |

> 说明：这条报错**不是升级失败**。紧跟其后的"书数: 62"能正常读出来，就说明数据完好、容器活着。
> 只是在 62 本书的库上 syncdb 耗时超过 20 秒，检查跑得太早了。

### 补丁包

`audiobook-patch-4.6.0-5.tar.gz`（6.2KB，2 个文件：`upgrade.sh`、`deploy.sh`）
**纯脚本包，不含镜像内代码，不需要重建镜像、不需要重启容器。**

---

## 4.6.0-4

### 新增功能

| 功能 | 文件 | 说明 |
|---|---|---|
| Mimo-TTS 使用说明 | `app/src/pages/toolbox/mimo_tts.vue` | 折叠面板：API 类型怎么选、api-key 与 Bearer 的区别、密钥来源、保存配置说明 |
| Mimo-TTS 搜索按钮 | `app/src/pages/toolbox/mimo_tts.vue` | 原来只有回车能搜，新增可点击的「搜索」按钮（空输入禁用、搜索中转圈） |

### 修复 Bug

| Bug | 严重度 | 表现 | 修复 |
|---|---|---|---|
| 读者组列表 KeyError: ScopedSession | 致命 | 打开读者组直接 500 报错 | `_groups_with_members` 由 staticmethod 改为实例方法，改用 `self.settings` |
| 编辑组改名后成员名单被清空 | 高 | 改组名后组员"消失"（实际还挂在旧组名下） | 前端记住 `old_name`，后端识别改名并迁移成员归属 |
| 保存组后成员列全部变"-" | 中 | 保存任意组，列表里所有组成员列被置空 | 保存接口响应补上 `members`，与 GET 返回结构一致 |
| 设置页保存卡住、像在重启 | 中 | 点保存长时间无响应、提示弹两次 | 删除重复的全量提交请求；去重弹窗；保存按钮加 loading |
| 7 个工具页搜索图标不可点 | 中 | 只能按回车，点放大镜无反应（chinese_converter / epub_beautify / epub_fixer / epub_merge / epub_split / text_replace / txt_encoding_fixer） | 补 `append-outer-icon` + `@click:append-outer="search"` |
| 批量分配空格分隔失效 | 低 | 手输 `alice bob` 被当作一个用户名，全部 missing | 按 `[,;\s]+` 切分 |
| 组改名可撞已存在组名 | 中 | 两个组的组员混在同一名字下，永久无法区分 | 后端拒绝改名并提示"已存在同名组" |
| 读者组按钮判空崩溃风险 | 低 | combobox 返回非数组时 `.length` 误判 | 加 `!assignUsers` 前置判断 |

### 补丁包

`audiobook-patch-4.6.0-4.tar.gz`（181KB，14 个文件）

---

## 4.6.0-3

### 修复 Bug

| Bug | 表现 | 修复 |
|---|---|---|
| 设置页保存卡住 | 点保存后长时间无响应、像在重启服务 | 删除对 `/admin/settings` 的重复全量提交，成功提示只弹一次，按钮加 loading |

> 说明：服务端重启逻辑本身正确，仅以下 8 个键变化时才重启：
> `cookie_secret`、`xsrf_cookies`、`static_host`、`MAX_UPLOAD_SIZE`、
> `BOOK_NAMES_FORMAT`、`ENABLE_TXT_TO_TXTZ_PLUGIN`、`LOG_LEVEL_DEBUG`、
> `douban_v2_max_per_hour`。其余设置只写配置、不重启。

---

## 4.6.0-2

### 修复 Bug

| Bug | 表现 | 修复 |
|---|---|---|
| 读者组列表 KeyError: ScopedSession | 打开读者组 500 | `_groups_with_members` 改用 `self.settings["ScopedSession"]` |

---

## 4.6.0-1（换算前旧编号 v4.8.2 / v4.8.3）

**本版是移植版的第一个正式基线**，包含相对上游的全部定制。

### 新增功能

| 功能 | 文件 | 说明 |
|---|---|---|
| 读者组分权限管理 | `webserver/handlers/reader_group.py`<br>`webserver/services/reader_group.py`<br>`app/src/components/ReaderGroupEditor.vue` | 按组批量限制可读书目（白名单/黑名单 + 分类/标签）；用户归属存 `Reader.extra`，零数据库迁移 |
| 读者组预置模板 | 同上 | 儿童 / 访客 / 成人家属 / 会员四套开箱配置，一键填充 |
| 批量分配用户到组 | 同上 | 从数据库读取真实用户，下拉多选 chips + 可手输 |
| 音频转写 | `webserver/services/transcribe.py` | faster-whisper / openai-whisper 双后端，输出 `.srt` + `.txt` |
| 数据目录外置 | `webserver/settings.py`、`docker-compose.yml` | 数据统一在 `/volume1/docker/audiobook-data`，源码目录永远干净 |
| 原子升级脚本 | `upgrade.sh` | 预检 → 备份库 → 停容器 → 旧源码改名 → 全新解压 → 污染自检 → 挂载校验 → 构建 → 启动验证 |
| 部署脚本 + 污染自检 | `deploy.sh` | 发现 books/data 混入源码目录立即停止并给清理命令 |
| 跟随上游升级工具 | `upgrade-upstream.sh` | 一条命令：拉代码 → merge 上游 tag → 冲突暂停 → 出包 → 上线 |
| 出包工具 | `merge-*.sh` | 补丁包 + 基准包 → 成品包，自动校验 127 个符号链接 |
| 操作手册 | `START_HERE.md`<br>`UPSTREAM_UPGRADE.md`<br>`PORTING_NOTES.md`<br>`DEPLOY_README.md` | 总纲 + 细则，含"开发侧/NAS 分工"、三种改代码方式 |
| 版本号规则 | `PORTING_NOTES.md` | `<上游tag>-<序号>`，跟上游同步 |

### 修复 Bug

| Bug | 严重度 | 表现 | 修复 |
|---|---|---|---|
| 编辑组改名后成员名单被清空 | 高 | 改个组名，组员全"消失" | 前端记住 `old_name`，后端识别改名并迁移成员 |
| 保存组后成员列全部变"-" | 中 | 保存任意组，列表所有组成员列被置空 | 保存接口响应补上 `members` |
| 数据目录跑进源码目录 | 致命 | 升级后 books/data 出现在 `audiobook/` 下 | 挂载外置 + upgrade.sh/deploy.sh 污染自检 |
| git 推送符号链接丢失 | 中 | myreader-dist 127 个符号链接变普通文件 | 改用 tar 包分发，不依赖 git |

---

## 附：升级历史速查

| 版本 | 主要内容 | 备注 |
|---|---|---|
| 4.6.0-8 | **修管理员被读者组拦住（详情页按钮全灰）**；标签/分类/WebDAV/Podcast 五处口径统一；**修 Podcast 分类标签页 404 与单书订阅越权**；有声书弹窗加进度记忆 | 含 -7 全部内容，需重建镜像 |
| 4.6.0-7 | **修悬空组引用静默放行**；悬空引用告警+自动修复 | 含 4.6.0-6 全部内容，需重建镜像 |
| 4.6.0-6 | 修白名单空条件放行全库；严格模式开关；权限排障接口 | 未独立发布，并入 -7 |
| 4.6.0-5 | upgrade.sh/deploy.sh 启动验证改轮询；修容器残留导致起不来 | 纯脚本包，不重建镜像 |
| 4.6.0-4 | Mimo-TTS 搜索按钮 + 使用说明；7 个工具页搜索图标可点；读者组 4 处修复 | 已上线 |
| 4.6.0-3 | 设置页保存优化 | |
| 4.6.0-2 | 读者组 KeyError 修复 | 未单独出成品包 |
| 4.6.0-1 | 全部定制基线（原 v4.8.2/v4.8.3） | |
