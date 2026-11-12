# MCP 和 Skill 使用上手卡

给没用过这套东西的人看：这套书库系统有两条路能让 AI 帮你干活——配 MCP，或者装 Skill。两条路任选一条就能用，不用都装。

## 先分清 MCP 和 Skill

一句话：**MCP 是通道，Skill 是操作剧本。**

- **MCP 是底层通道**。服务端入口是 `POST /api/mcp/stream`，把书库能力包装成一组工具（搜索、改元数据、查阅读状态等），AI 客户端连上就能调用。它不关心"什么时候该用哪个工具"，只负责把工具摆出来。
- **Skill 是给客户端的操作剧本**。一个 `SKILL.md` 文件告诉 AI 每个工具该在什么场景用、参数怎么填；配套脚本 `scripts/mybooks_api.py` 负责真正发请求。AI 客户端读剧本、照着做，所以叫"技能"。
- **两者的工具名是对齐的**。`webserver/mcp/api_tools.py` 顶部注释明确要求工具名、参数与 Skill 保持一致，所以不管走哪条路，AI 面对的都是同一套动作，你说的话也一样。
- **装一个不等于另一个能用**。只配 MCP 就能用 MCP；想用 Skill 还得单独装 Skill 和它的脚本。

## 路线一：用 MCP（三步）

### 第一步：填一段配置

打开你的 AI 客户端里跟「MCP 服务器」有关的地方（一般叫 MCP 配置文件，或者设置里的「MCP 服务器」一栏），把下面这段整段粘进去：

```json
{
  "mcpServers": {
    "mybooks": {
      "type": "streamableHttp",
      "url": "https://<ip>:88/api/mcp/stream",
      "description": "MyBooks 个人书库"
    }
  }
}
```

写法按上游说明核对过：外层键名是 `mcpServers`，`type` 取 `streamableHttp`，`url` 指向 `/api/mcp/stream`，路径不要漏。

- 把 `<ip>` 换成你 NAS 的地址，端口不是 88 就一起改。
- 如果你的客户端界面里要求分开填「类型 / URL / 请求头」，类型选 **Streamable HTTP**，URL 填 `https://<ip>:88/api/mcp/stream`。
- 少数客户端（比如 Trae 的 HTTP 配置文档）只要求 `url` 和 `headers`，不写 `type` 也能加，以你客户端界面实际要求为准。
- `description` 只是备注，可留可删。填完保存，重启客户端或让它重新加载配置。

### 第二步：第一次登录

第一次用的时候，AI 会告诉你需要认证，问你要账号密码。把你在站点上的用户名和密码给它，它会调用登录工具换回一个 token，之后就能正常干活。

- 本仓库代码里 token 有效期是 **24 小时**（`webserver/mcp/mcp_service.py` 的 `TOKEN_EXPIRE_HOURS = 24`），到期再登一次。
- 服务重启后，登录换来的 token 也会失效，重新登一次即可。
- 上游说明对 MCP 登录写的是「使用流程会提示提供账号信息进行登录」；有效期和静态令牌开关名以本仓库代码为准：24 小时、`AI_MCP_TOKEN`。如果上游页面写的与此不同，按本仓库代码执行。

不想每次登，就换成固定令牌：

1. 进站点管理后台的 AI 设置，找到「MCP访问令牌」，点输入框后面的刷新图标生成一串令牌，然后保存设置。这个配置项的名字是 `AI_MCP_TOKEN`。
2. 在客户端给这个 MCP 服务器加上请求头：`Authorization: Bearer <刚才那串令牌>`。

配了令牌但客户端没带这个请求头，AI 还是会让你登录，这是正常的。另外这串令牌会被当成管理员身份使用，只建议在自己的环境里开，别外泄。

### 第三步：能直接说的话

配好之后不用记命令，直接用平常的话说就行：

- 帮我搜一下书库里余华的书。（`search_books`）
- 书库一共有多少本书？电子书和实体书各多少？（`library_stats`）
- 把第 123 本书的出版社改成「上海译文出版社」。（`edit_book`）
- 《三体》我读到什么进度了？（`get_book_reading_stats`）
- 帮我把昨天读《三体》的时间记成 1 小时。（`set_reading_time`）
- 把第 123 本书标成想读。（`wants`）
- 把《三体》推送到我的 Kindle。（`send_to_device`）
- 导出《活着》里我做过的笔记。（`get_notes`）
- 建一个叫「科幻待读」的公开书单。（`create_booklist`）
- 把第 123 本书转成有声书，转好后告诉我。（`tts_convert`、`tts_progress`）

最后一句涉及的有声书转换属于管理员功能，批量补全元数据、修 EPUB 也是；用上面那串固定令牌时天然就是管理员身份。

## 路线二：用 Skill

Skill 不能自己跑，要由一个支持 Skill 的客户端加载：客户端读 `SKILL.md` 里的剧本，再按剧本调用 `scripts/mybooks_api.py`。所以下面三件事缺一不可：客户端支持 Skill、脚本在、环境变量配好。

### 准备：三个环境变量

Skill 的脚本不认 MCP 的 token，它靠账号密码自己登录站点。用之前先给三个变量（按你的 NAS 地址填）：

```powershell
$env:MYBOOKS_HOST="https://<ip>:88"
$env:MYBOOKS_USER="admin"
$env:MYBOOKS_PASSWORD="你的密码"
$env:MYBOOKS_SSL_VERIFY="false"
```

- `MYBOOKS_HOST` 只写到端口，不要带 `/api` 之类的路径。
- `MYBOOKS_SSL_VERIFY="false"` 是因为你的站点用自签证书；站点有正规证书时删掉这一行或改成 `true`。
- 上游明确提醒：账号密码别写进共享或全局配置文件，用会话级的变量或密钥管理工具传入。脚本只会把凭据发到你自己填的这个地址。
- 这些变量要在客户端启动时就能读到。图形界面客户端在哪填环境变量各不相同（**未确认**，以客户端文档为准）；临时做法是从同一个终端里启动客户端。
- 上游脚本按 `python3` 写；Windows 上一般叫 `python`，如果 `python3` 命令不存在就换成 `python`。

### 安装

上游页面：`https://clawhub.ai/poxenstudio/skills/mybooks`

在 OpenClaw 里装（上游给的命令）：

```bash
openclaw skills install @poxenstudio/mybooks
```

如果你的客户端不是 OpenClaw，也不一定要装它：页面上的 Files 页可以下载 Skill 的文件（具体包含哪些文件**未确认**，至少需要 `SKILL.md` 和 `scripts/mybooks_api.py`），放到客户端的 Skill 目录即可。客户端到底从哪个目录加载 Skill、认不认这种目录结构，**未确认**，以客户端文档为准。

### 第一句该说什么

装好、变量配好之后，先说一句最没有歧义的：

> 书库现在有多少本书？

这句话背后调的是 `library_stats`，不需要任何参数。AI 能回你一个数字，就说明 Skill 通了；如果它说找不到脚本、或者报 `user.need_login`，先看后面的「脚本缺失怎么补」和「两条路的凭据不通用」。

### 几句可以直接说的话

- 帮我搜一下书库里余华的书。（`search_books`）
- 把第 123 本书的出版社改成「上海译文出版社」。（`edit_book`）
- 联网找一下《三体》的元数据候选，先给我看，别直接改。（`book_refer_search`）
- 《三体》我读到什么进度了？（`get_book_reading_stats`）
- 把《三体》推送到我的 Kindle。（`send_to_device`）
- 把第 123 本书转成有声书，转好后告诉我。（`tts_convert`、`tts_progress`）

### 脚本缺失怎么补

我们这棵树里**没有** `skills/` 目录，`skills/mybooks/scripts/mybooks_api.py` 也不存在。也就是说，照上游装完，客户端可能只拿到了剧本、没有执行脚本。按这三步补：

1. **先看有没有脚本**：在客户端的 Skill 目录里找 `skills/mybooks/scripts/mybooks_api.py`。找到就跳到第 3 步。
2. **从上游拿**：打开 `https://clawhub.ai/poxenstudio/skills/mybooks` 的 Files 页，下载 `SKILL.md` 和 `scripts/mybooks_api.py`（页面若没有单独文件，就下载整个 Skill 包），放到项目根目录的 `skills/mybooks/` 下，保持 `skills/mybooks/SKILL.md`、`skills/mybooks/scripts/mybooks_api.py` 这个结构。如果已经用 `openclaw skills install` 装过，也可以直接从 OpenClaw 的安装目录把这两个文件复制过来。
3. **自检**：变量配好后跑一句

   ```bash
   python3 skills/mybooks/scripts/mybooks_api.py library_stats '{}'
   ```

   Windows 上没有 `python3` 就换成 `python`。返回 `"err": "ok"` 和统计数字就说明脚本能用了；这时再回到对话里说「书库有多少本书」。

### 两条路的凭据不通用

- **MCP**：登录换 token（24 小时），或者用站点里配的 `AI_MCP_TOKEN`，请求走 `/api/mcp/stream`。
- **Skill**：脚本读 `MYBOOKS_HOST` / `MYBOOKS_USER` / `MYBOOKS_PASSWORD`，调 `/api/user/sign_in` 拿 Secure Cookie（浏览器里那种登录态），过期后脚本会自动重新登录一次。

所以：配好了 MCP 不会让 Skill 免登录，反过来配了 Skill 的账号密码也不会让 MCP 免登录。两边各配各的。

## 选哪个 AI 客户端

先说一句：**MCP 服务自己不产生任何行为**，它只是把书库能力摆出来，必须挂在一个支持 MCP 的 AI 客户端上才能用。你至少有客户端，还得在客户端里配一个能用的模型（比如 DeepSeek），填 API Key 那一步按客户端引导走。另外，走 Skill 还要求客户端本身支持加载 Skill（**未确认**，以客户端文档为准），下表只讨论 MCP。

| 客户端 | 直接连远程 streamableHttp | 要不要装桥接 | 自签证书 | 收费 | 配置入口 |
|---|---|---|---|---|---|
| Cherry Studio（推荐） | 支持，类型选 Streamable HTTP，可填请求头 | 不需要 | 未确认；可能要导入根证书 | 免费开源 | 设置 → MCP 服务器 |
| Trae（备选，这台电脑已有） | 官方文档写的是「HTTP 类型」，填 `url` 和 `headers`，未写 `streamableHttp` 字样，是否兼容本服务的传输方式需实测 | 不需要 | 未确认 | 未确认（以官网为准） | 设置 → MCP → 手动添加 |
| Claude Desktop | 可通过「自定义连接器」填远程 URL，但需要付费套餐；配置文件那种方式只支持本地 stdio | 配置文件方式要 `mcp-remote` 转接 | 未确认；HTTPS 地址通常要求有效证书 | 付费套餐 | 设置 → 连接器；或 `claude_desktop_config.json` |

**推荐 Cherry Studio**：Windows 桌面应用、免费，界面里直接选类型、填 URL 和请求头，不用装 Node、不用桥接，最接近「照着念就能用」。

**备选 Trae**：你电脑上已经有，省一次安装，配置也在图形界面里；缺点是它偏 IDE，日常聊天不如桌面聊天客户端顺手。

自签证书这一点要单独说：你的 NAS 是自签证书 + IP 直连，客户端很可能直接报证书错误。可以先把 NAS 的证书导入 Windows 的「受信任的根证书颁发机构」（浏览器打开站点 → 看地址栏证书 → 安装证书 → 本地计算机 → 受信任的根证书颁发机构），但客户端是否使用系统证书库**未确认，需要实测**。如果导入后仍然报错，就改走 NAS 的内网 http 端口（如果有开），或者换一个明确允许跳过证书校验的客户端——目前这几家的跳过选项都**未确认**，不要照抄网上的偏方。

最后一句现实提醒：如果手上的客户端根本不支持远程 HTTP，最省事的路是先换一个支持远程 MCP 的桌面客户端，别一上来折腾 `mcp-remote` 这类桥接。

## 排错三行

- 连不上：先用浏览器打开 `https://<ip>:88/api/mcp/health`，正常会返回 `"status": "healthy"`；打不开就查地址、端口和 nginx 是否在跑。客户端报证书错误按上一节处理。
- 提示 401 或一直要求认证：MCP 这边是 token 过期了（24 小时）或请求没带 `Authorization: Bearer`，重新登录或换新令牌；Skill 这边是账号密码不对或环境变量没生效。
- 工具调用报错：去服务器上看 `mybooks.log`，Docker 部署一般在 `/data/log/mybooks.log`，里面会有真正的错误原因。

## 一个提醒

`/api/mcp/` 这一段不经过站点的登录门禁，只靠 MCP token 认人，所以这个 token 等同于管理员凭据。Skill 脚本里的账号密码同样是管理员级凭据。两边都不要写进公开仓库，也不要贴到共享文档里；怀疑泄露就重新生成令牌、改密码。
