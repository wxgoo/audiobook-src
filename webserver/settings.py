#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
# fmt: off
# flake8: noqa

import os

settings = {
    'installed'     : False,
    'STANDALONE'    : False,
    "autoreload"    : True,
    "xsrf_cookies"  : False,
    "static_host"   : "",
    "nuxt_env_path" : os.path.join(os.path.dirname(__file__), "../app/.env"),
    "html_path"     : os.path.join(os.path.dirname(__file__), "../app/dist"),
    "i18n_path"     : os.path.join(os.path.dirname(__file__), "i18n"),
    "static_path"   : os.path.join(os.path.dirname(__file__), "../app/dist"),
    "resource_path" : os.path.join(os.path.dirname(__file__), "resources"),
    "settings_path" : "/data/books/settings/",
    "progress_path" : "/data/books/progress/",
    "convert_path"  : "/data/books/convert/",
    "upload_path"   : "/data/books/upload/",
    "scan_upload_path"   : "/data/books/imports/",
    # 扫描导入 Phase1 哈希并行的线程数：1=串行（NAS 机械盘兜底），默认 4。
    # 仅存于此清单（不进设置页白名单），手工部署可写进 auto.py 调整。
    "scan_hash_workers"  : 4,
    # 扫描导入的写事务攒批窗口（书数）。Phase1 是 READY 行的短写事务，
    # Phase2 是行 + Item 链接的短写事务；越大 fsync 越少、失控风险越大。
    "import_phase1_batch_size"  : 500,
    "import_phase2_batch_size"  : 20,
    # 「有音频的书」缓存兜底全库扫描间隔（秒）。默认 5 分钟；导入/转码/删除
    # 走事件增量更新，统计接口也会把实时扫盘结果同步进来，这里只兜底
    # 「既没有统计请求、也没有事件」的极端情况。0 = 关闭兜底扫描。
    # 注意：这里的值会灌进 CONF 并覆盖 audio.py 里的 fallback，改间隔请改这里。
    "AUDIO_CACHE_REFRESH_SECONDS": 5 * 60,
    # 有声书导入目录（imports/audiobooks/）自动导入轮询。inotify 监控明确跳过
    # 该目录，且经 SMB 拷贝整本有声书时 3s 防抖会在没拷完时触发，故改用
    # 「目录指纹 + 连续两轮稳定」轮询。跟随 IMPORT_BY_INOTIFY 开关启用；
    # 置 False 可单独关掉有声书部分（电子书监控不受影响）。
    "AUDIO_AUTO_IMPORT_ENABLED": True,
    # 轮询间隔（秒），最小 20；稳定两轮后才触发，故最长约 2 倍间隔生效。
    "AUDIO_AUTO_IMPORT_INTERVAL": 60,
    # 中文检索索引（SQLite FTS5）。关闭后搜索自动回退到 calibre 原生 search。
    "SEARCH_INDEX_ENABLED": True,
    "SEARCH_INDEX_PATH": "/data/books/search_index.db",
    "SEARCH_INDEX_REFRESH_SECONDS": 300,     # 检查 metadata.db 版本变化的间隔
    "SEARCH_INDEX_MAX_RESULTS": 20000,       # 单次查询最多返回的候选 id 数
    "extract_path"  : "/data/books/extract/",
    "with_library"  : "/data/books/library/",
    "cookie_secret" : "cookie_secret",
    "cookie_expire" : 7*86400,
    "login_url"     : "/login",
    "user_database" : 'sqlite:////data/books/calibre-webserver.db',
    "site_title"    : "书屋",
    "site_language" : "auto",
    # 系统时区：阅读统计等按「天」分桶的时间基准。"auto" = 跟随站点语言（简繁中文 UTC+8、
    # 英文 UTC），也可填任意 IANA 时区名（如 Asia/Shanghai）。见 webserver/site_time.py。
    "site_timezone" : "auto",
    "site_theme"    : "dark",
    # 管理员配置的「网站默认访问链接」。留空时分享链接、二维码、OPDS/WebDAV 说明页
    # 与 Podcast 订阅链接使用当前访问地址；反代或内网访问下想让对外域名出现在这些
    # 链接里时填写（不含结尾斜杠）。
    # 注意与每请求被 set_hosts() 覆盖的小写 "site_url" 是两套概念：那个仍供邮件、
    # 头像、磁盘扫描等用请求派生的地址，本键只喂需要稳定对外域名的链接。
    "SITE_URL"      : "",
    "ssl_crt_file"  : "/data/books/ssl/ssl.crt",
    "ssl_key_file"  : "/data/books/ssl/ssl.key",

    "push_title": "%(site_title)s：推送给您一本书《%(title)s》",
    "push_content": "为您奉上一本《%(title)s》, 欢迎常来访问%(site_title)s！%(site_url)s",

    "convert_timeout" : 12000,

    # https://analytics.google.com/
    "google_analytics_id" : "G-LLF01B5ZZ8",

    "ENABLE_OPDS_SERVICE"      : True,
    "ENABLE_OPDS_AUTH"         : False,
    "opds_will_display"        : ["*"],
    "opds_wont_display"        : [],
    "opds_max_tags_shown"      : 10240,
    "opds_max_items"           : 50,
    "opds_max_ungrouped_items" : 100,
    "opds_url_prefix"          : "",

    "db_engine_args": {
        "echo": False,
    },

    # 100MB, tornado default max_buffer_size value
    "MAX_UPLOAD_SIZE": "100MB",

    # Chunked upload size threshold (0 means disabled, >0 means files larger than this will be uploaded in chunks)
    "CHUNK_UPLOAD_SIZE": "0MB",

    # 「版本与更新」(/admin/version)：后台每 8 小时比对 Gitee 发布清单并给管理员发站内提示。
    # 关闭只停后台自动检测，页面里的「立即检测」仍可手动执行。开关在该页面内直接修改。
    "AUTO_CHECKING_NEW_VERSION": True,

    "ENABLE_BOOKBARN": False,
    "BOOKBARN_TOKEN": "",
    "ENABLE_RECEIVING_BOOKS": False,
    "BOOKBARN_COLLECTION_HOUR": 3,
    "USE_BOOKBARN_PROXY": False,
    "BOOK2AUDIO_PROXY": "",
    "ENABLE_PHYSICAL_BOOKS": True,
    # 功能模块总开关，见 webserver/base/modules.py。
    # 默认全开：升级过来的人不该因为新增了这层开关而突然少一半功能。
    "ENABLE_MODULE_MULTIUSER": True,
    "ENABLE_MODULE_COMMUNITY": True,
    "ENABLE_MODULE_SHARED_READING": True,
    "ENABLE_MODULE_AUDIO": True,
    "ENABLE_MODULE_PHYSICAL": True,
    "ENABLE_MODULE_AI": True,
    "ENABLE_FOLDER_BROWSE": False,
    "ALLOW_GUEST_UPLOAD": False,
    "AI_ENABLED": False,
    "AI_MODEL": "deepseek-chat",
    "AI_MCP_TOKEN": "",
    # MCP 鉴权默认只接受 Authorization: Bearer 头；旧客户端若仍把 token 放 URL，
    # 需显式打开此项（不推荐，URL 会进 access log）
    "ALLOW_MCP_TOKEN_IN_URL": False,
    "AI_DEEPSEEK_API_KEY": "",
    "AI_API_URL": "https://api.deepseek.com",
    "AI_ALLOW_SET_CATEGORY": True,
    # 上游 5b270c0：LangGraph 按 superstep 计数（一次模型/工具往返约 2 步），
    # 16 只够约 7 轮工具调用；单轮工具调用另有硬上限，防止模型原地打转。
    "AI_RECURSION_LIMIT": 40,
    "AI_MAX_TOOL_CALLS": 12,
    "ENABLE_MYNEXUS": False,
    "MYNEXUS_URL": "",
    "MYNEXUS_TOKEN": "",
    "MAIN_PAGE_RANDOM_COUNT": 12,
    "MAIN_PAGE_RECENT_COUNT": 12,
    "RECOMMEND_ENABLE": True,                 # 首页推荐引擎总开关，关闭即回到旧的随机逻辑
    "RECOMMEND_FEATURE_TTL": 300,             # 书籍特征索引刷新周期（秒）
    "RECOMMEND_NEW_DAYS": 30,                 # 新书窗口（天），书不够时自动扩大到 90/180 天
    "RECOMMEND_NEW_BY": "timestamp",          # timestamp | id
    "RECOMMEND_NEW_HALF_LIFE_DAYS": 7,
    "RECOMMEND_DIVERSITY": 0.3,               # MMR 多样性惩罚系数
    "RECOMMEND_MAX_PER_AUTHOR": 2,
    "RECOMMEND_MAX_PER_SERIES": 2,
    "RECOMMEND_USE_CROWD": True,              # 参考其他用户的阅读/下载/读完/收藏数据
    "RECOMMEND_CROWD_TTL": 600,               # 群体数据刷新周期（秒）
    "RECOMMEND_CROWD_MIN_USERS": 2,           # 除本人外至少这么多用户有行为数据才启用群体信号
    "RECOMMEND_CROWD_SECS_CAP": 10800,        # 单人单书阅读时长封顶（秒）
    "RECOMMEND_CROWD_EXCLUDE_READERS": [],    # 不参与群体统计的用户 id（测试号、批量下载账号等）
    "RECOMMEND_CROWD_IGNORE_PROTOCOLS": ["webdav"],  # 这些协议的下载不计入群体统计（WebDAV 客户端同步时会批量读取文件）
    "RECOMMEND_USE_LEGACY_HISTORY": False,    # 把 Reader.extra 旧版阅读/推送历史作为弱群体信号
    "RECOMMEND_POOL_SIZE": 300,               # 每个用户预先打分保留的随机推荐候选数
    "RECOMMEND_SIMILAR_POOL": 60,             # 详情页相关推荐：每本书保留的高分候选数（按书缓存，所有人共用）
    "RECOMMEND_SIMILAR_MAX_TAG_BOOKS": 2000,  # 包含书数超过此值的泛标签不参与召回，只参与打分
    "RECOMMEND_SIMILAR_MAX_PER_AUTHOR": 3,
    "RECOMMEND_SIMILAR_MAX_PER_SERIES": 3,
    "RECOMMEND_SIMILAR_CACHE_SIZE": 1000,     # 缓存多少本书的候选池
    "RECOMMEND_TREND_DAYS": 30,
    "RECOMMEND_USE_REVIEWS": True,            # ENABLE_BOOK_REVIEW 关闭时自动视为 False
    "RECOMMEND_QUALITY_PRIOR_STRENGTH": 3,    # 贝叶斯平均先验强度
    "RECOMMEND_EXPLORE_RATIO": 0.25,          # 随机推荐中完全随机抽取的比例
    "RECOMMEND_TEMPERATURE": 0.35,            # 抽样温度，越大越随机
    "RECOMMEND_SEED_BUCKET_MINUTES": 0,       # 0：每次打开首页都重新随机；>0：该时间段内打开结果不变
    "RECOMMEND_WEIGHTS": {},                  # 覆盖默认权重，键见 webserver/recommend/config.py
    "RECOMMEND_PROFILE_TTL": 600,             # 用户画像缓存（秒），用户改阅读状态/评价时立即失效
    "RECOMMEND_HALF_LIFE_DAYS": 180,          # 用户行为时间衰减半衰期
    "RECOMMEND_COLD_START_THRESHOLD": 3.0,    # 画像权重低于此值视为冷启动，不做元数据相似推荐
    "RECOMMEND_DISLIKE_MAX_RATING": 4,        # 本人评分 ≤ 该值（0-10）视为不喜欢
    "RECOMMEND_CO_TTL": 86400,                # 共读关系重建周期（秒）
    "RECOMMEND_CO_MIN_SECS": 600,             # 阅读时长低于此值不计入共读的"读过"
    "RECOMMEND_CO_NEIGHBORS": 30,             # 每本书保留的共读邻居数
    "RECOMMEND_CO_MAX_BOOKS_PER_READER": 1000,  # 每个用户最多取最近这么多本书参与共读计算
    "DEFAULT_PAGE_SIZE": 60,
    "PERF_MONITOR": False,
    "PERF_STALL_MS": 500,
    "FAST_GET_DATA_AS_DICT": True,
    "MAX_PAGE_SIZE": 200,
    "UPLOAD_CONCURRENCY": 1,
    "USE_X_ACCEL": True,
    "WARMUP_ENABLE": True,
    "WARMUP_DELAY_SEC": 10,
    "SQLITE_RELAXED": False,
    "PERFORMANCE_MODE": "normal",
    "LITE_GROUP_LISTING": True,
    "LITE_GROUP_RECOMMEND": True,
    "LITE_GROUP_FILES": True,
    "LITE_GROUP_BACKGROUND": True,
    "LITE_GROUP_RESOURCES": True,
    "LITE_THROTTLE_LIMIT": 4,
    "LITE_BOOK_CACHE_SIZE": 2000,
    "LITE_BOOK_CACHE_MB": 32,
    "GIL_SWITCH_INTERVAL_MS": 0,
    "CALIBRE_POOL_SIZE": 4,
    "BLOCKING_POOL_SIZE": 20,
    "CACHE_DIR": "/data/cache",
    "CACHE_MAX_MB": 200,
    "THUMB_CACHE": True,
    "THUMB_USE_PILLOW": True,
    "THUMB_JPEG_QUALITY": 83,
    "THUMB_CONCURRENCY": 2,
    "THUMB_SIZES": [[60, 80], [120, 200], [240, 320], [480, 640]],
    "ENABLE_AUDIO_CONVERSION_LOG": False,
    "ENABLE_AUDIO_SUBTITLE": True,
    "LOG_LEVEL_DEBUG": False,
    "USE_DYNAMIC_COVER": True,
    "DEFAULT_LANGUAGE": "zho",

    "CALIBRE_CACHE_CLEAN_ENABLED": False,
    "CALIBRE_CACHE_CLEAN_INTERVAL": 1800,
    "ENABLE_TXT_TO_TXTZ_PLUGIN": False,

    # §douban v1 已下线§（build.27-r12）：douban-rs-api 伴生容器在本部署中不存在，
    # 默认源清单与 settings UI 均不再包含 douban（v2 直连保留）。
    "META_SELECTED_SOURCES": ["baidu", "xinhua", "douban_v2"],

    "ENABLE_AUTHOR_INFO": True,

    "ENABLE_STAMP_FEATURE": False,
    "STAMP_POSITION": "bottom-right",

    "EPUB_VIEWER": "MyReader",
    # Embedded MyReader (web) dictionaries — defaults for the reader's
    # dictionary list, see webserver/handlers/reader_dict.py.
    "READER_DICT_MYBOOKS_ENABLED": True,
    "READER_DICT_BAIKE_ENABLED": True,
    "READER_MYDICTS": [],
    "READER_GROUPS": {},                   # 读者组：组名 -> {mode, categories, tags},
    # 读者组总开关（4.6.0-19）：关闭时组规则全链路失效（用户自身的
    # read_limit/limit_* 不受影响），成员归属照常保存，重开即恢复。
    "READER_GROUPS_ENABLED": True,
    # 严格模式：白名单组一个条件都没填时，成员看不到任何书。
    # 关掉则退回 mybooks 原版语义（空条件 = 不限权）。默认开启。
    "READER_GROUP_STRICT": True,
    # 音频转写（faster-whisper）。模型缓存在 /data/models/whisper（可用环境变量
    # WHISPER_MODEL_DIR 覆盖），容器重建后无需重新下载。
    # KEEP_TXT：除了 .srt 字幕，是否同时输出 .txt 纯文本全稿（全文搜索/复制/离线阅读用）。
    "TRANSCRIBE_MODEL": "small",           # tiny/base/small/medium/large-v3
    "TRANSCRIBE_LANG": "auto",             # auto 或 zh/en/ja...
    "TRANSCRIBE_KEEP_TXT": True,
    # 有声书导入：遇到同名电子书已存在时，把音频挂到那本书上复用同一个 book_id
    # （目录合并到 audios/<book_id>/），而不是新建一条 calibre 记录。
    # 关掉则恢复旧行为：同名但没音频目录就新建书（会导致同一本书出现两条）。
    "AUDIO_LINK_TO_EXISTING_BOOK": True,
    # 同名重复书清理（迁移工具）的备份目录。合并前会把用户库备份到这里，
    # 空值 = <data_path>/backup。见 services/book_dedup.py
    "BOOK_DEDUP_BACKUP_DIR": "",
    "PDF_VIEWER": "/static/pdfjs/web/viewer.html?file=%(pdf_url)s",
    "DJVU_VIEWER": "/static/djvureader/index.html?file=%(djvu_url)s&name=%(name)s",
    "ENABLE_PODCAST_SERVICE": False,
    "ENABLE_WEBDAV_SERVICE": True,
    "WEBDAV_SYNC_FOLDER": False,
    "ENABLE_DATA_SYNC": True,
    "ENABLE_KOREADER_SERVICE": True,
    "MYREADER_SYNC_PATH": "/data/sync/",
    "ENABLE_BOOK_REVIEW": True,            # 允许用户对书籍进行评论及评分
    "REVIEW_REQUIRES_APPROVAL": False,     # 评论需要审核后才能展示
    "ENABLE_BOOK_RECOMMEND_TO_OTHERS": True,  # 评价是否计入推荐人数/首页推荐位
    "ENABLE_SHARED_NOTES": True,          # 阅读时可查看其他用户的划线与笔记，见 plan/Social_Reading_Plan.md
    "SYNC_DB_FLUSH_INTERVAL_SEC": 5,      # reading_records 批量落库周期（秒）
    "SYNC_SHARED_NOTES_MAX_USERS": 20,    # 共读场景单本书最多返回多少个不同用户的 notes
    "SYNC_LEGACY_MIGRATION_DONE": False,  # 旧版 sync 文件（books/configs/notes.json）是否已全部迁移入库
    "SYNC_SOFT_DELETE_RETENTION_DAYS": 7,  # reading_records 软删除（deleted_at）记录保留天数，超期物理清理
    "ALLOW_USER_DISABLE_STATISTIC": False,
    "READING_STATS_FLUSH_INTERVAL_SEC": 5,
    "VISIT_FLUSH_INTERVAL": 30,  # 浏览记录批量落库周期（秒），0 表示每次访问同步写库
    "VISIT_FLUSH_THRESHOLD": 200,  # 浏览记录缓存达到该条数立即落库
    "ENABLE_HOMEPAGE_READING_STATS": True,
    "ENABLE_HOMEPAGE_READING_BOOKS": True,
    "ENABLE_HOMEPAGE_BOOKLISTS": False,
    # 书单卡片的封面条是否自动横向轮播。关闭后只保留手动横滑，适合低配设备或
    # 不希望页面持续动起来的站点；前端读 sys.booklist_cover_scroll
    "ENABLE_BOOKLIST_COVER_SCROLL": True,
    "HOMEPAGE_CONFIG": {},
    "ALLOW_NEW_USER_MANAGE_BOOK": True,
    "ALLOW_NEW_USER_PUSH_BOOK": True,
    "ENABLE_AUTO_NEW_USER_APPROVAL": False,
    "ALLOW_READ_RANGE_SETTING": False,
    # 新用户默认的阅读范围：mode 0=全部可见 1=白名单(仅可见) 2=黑名单(不可见)
    "DEFAULT_READ_RANGE": {"mode": 0, "categories": "", "tags": ""},
    "IMPORT_BY_INOTIFY": False,
    "IMPORT_CATEGORY_WITH_FOLDER": False,
    "UPDATE_CATEGORY_WITH_FOLDER_RENAME": False,
    "SEND_MAIL_FOR_NEW_BOOKS" : False,
    "REMOVE_IMPORTED_FILE": False,
    "KEEP_UPLOAD_SOURCE_FILE": False,
    "ENABLE_SERVER_FILE_IMPORT": False,
    "UPLOAD_IGNORE_TITLE_CHECKING": False,
    "BATCH_ADD_IN_FORCE": False,

    "PDF_TILE_WITH_FILE_NAME": False,

    "TOOL_ROOT": "/data/books/tools/",
    "ENABLE_TOOLBOX_DEV_MODE": False,
    "ENABLE_TOOLBOX_STORE": True,

    "SOCIAL_AUTH_LOGIN_URL"          : '/',
    "SOCIAL_AUTH_LOGIN_REDIRECT_URL" : '/api/done/',
    "SOCIAL_AUTH_USER_MODEL"         : 'webserver.models.Reader',
    "SOCIAL_AUTH_AUTHENTICATION_BACKENDS" : (
        'social_core.backends.qq.QQOAuth2',
        'social_core.backends.weibo.WeiboOAuth2',
        'social_core.backends.amazon.AmazonOAuth2',
        'social_core.backends.github.GithubOAuth2',
        'social_core.backends.weixin.WeixinOAuth2',
    ),

    # See: http://open.weibo.com/developers
    'SOCIAL_AUTH_WEIBO_KEY'            : '',
    'SOCIAL_AUTH_WEIBO_SECRET'         : '',

    # See: https://connect.qq.com/
    'SOCIAL_AUTH_QQ_KEY'               : '',
    'SOCIAL_AUTH_QQ_SECRET'            : '',

    # See: https://github.com/settings/applications/new
    'SOCIAL_AUTH_GITHUB_KEY'           : '',
    'SOCIAL_AUTH_GITHUB_SECRET'        : '',

    # See: http://service.mail.qq.com/cgi-bin/help?subtype=1&&no=1001256&&id=28
    'smtp_server'       : "smtp.126.com",
    'smtp_encryption'   : "TLS",
    'smtp_username'     : "sender@126.com",
    'smtp_password'     : "password",
    # §douban v1 配置已随源下线§（build.27-r12）：douban_apikey / douban_baseurl 移除。
    # douban_max_count 保留：豆瓣V2 的每源返回条数也在读它（douban_v2/plugin.py），删了配置入口就没了。
    'douban_max_count'  : 2,
    'douban_v2_max_per_hour': 180,
    'ujxsw_max_count'   : 2,
    'auto_fill_meta'    : True,
    'auto_fill_qpm'     : 60,
    'auto_fill_pause_on_throttle': True,

    'avatar_service'    : "https://cravatar.cn",

    'BOOK_NAMES_FORMAT': 'utf8',
    'BOOK_NAV'          : '''经济金融=经济学/管理/经济/金融/商业/投资/营销/理财/创业/广告/股票/企业史/策划/经济管理/中国经济/市场营销/财政/投资理财/金融学/个人理财/企业与企业家/企业管理/经管/世界经济/经济学理论/管理学/经济金融/商业模式/银行/各行业经济/货币/金融史/经济史/管理学理论/新经济/价值投资/金融危机/证券/财经/商业管理/零售/电商/宏观经济/流行财经读物/对冲基金/经济与管理/商战/投资交易/金融投资/货币史/贸易经济/经管经管/领导力/资本主义/政治经济学/投资 交易
哲学社科=人文社科/哲学/社会学/文化/政治/社会/宗教/政治学/佛教/西方哲学/自由主义/思想史/社会科学/方法论/人类学/社科/法律/理想国/社会史/中国政治/佛学/传播学/日本研究/韩国/逻辑/国际政治/政治理论/世界政治/政治哲学/法学/王阳明/社会学家/道德哲学/基督教/中国哲学/哲学理论/世界哲学/中国研究/存在主义/精神分析/哲学入门/社会科学总论/政治人物/道教/社科历史/宗教伦理与研究/哲學/社会理论/哲学史/法律法规/人口学/科学哲学/地缘政治/信仰/美国政治/道家/民俗学/宗教知识读物/制度史/西学/认知/思维/人性/日本文化/文化史/文化研究/文化理论/语言文字/神话/军事/海外中国研究/社交/思想
历史=历史/中国历史/近代史/二战/考古/中国/世界历史/美国/日本/英国/法国/世界史/史学理论/德国/历史知识读物/意大利/战争/军事史/历史人物/明清史/欧洲史/清史/中国近/欧洲/全球史/中东/印度/罗马/清朝/俄国/土耳其/历史思考/英国史/民国/明史/历史学/政治史/中国史/俄罗斯/以色列/中世纪/中国近代史/明朝/晚清/中国近现代史/中国当代史/东南亚/日本史/非洲/三国/美国史/西班牙/历史与记忆/加拿大/瑞典/古罗马/古代史/国际关系/中国古代史/台湾/宋史/历史文化/区域国别史/中国通史/史料/蒙元史/民国史/苏联/秦汉史/中国史料典籍/近现代史/当代史/唐史/先秦史/中国专门史/罗马史/明清/二战史/一战/唐朝/史部/歷史/世界军事/通史/宋代/先秦/文明史/人类史/晚清史/太平天国/阿富汗/奥斯曼帝国/宋朝/历史地理/秦汉/蒙古/魏晋南北朝史/清代
文学=文学艺术/文学/随笔/中国文学/经典/散文/日本文学/诗歌/杂文/古典文学/名著/钱钟书/当代文学/外国名著/诗词/散文随笔/文学研究/文学理论/短篇/世界名著/文学天地/文学评论/文学史/文学评论与研究/人文/诗人/写作/现代文学/苏俄文学/短篇集/游记/纪实文学/诗歌词曲赋/当代散文随笔/自传/俄国文学/中国现当代文学/文学届/FICTION/意大利文学/现当代文学/西方文学/中国现代小说/外国文学/美国文学/法国文学/英国文学/拉美文学/俄罗斯文学/台湾文学/外国散文随笔/匈牙利文学/土耳其文学/爱尔兰文学/加拿大文学/欧美文学/外国文学作品集/中国文学作品集/中国文化/传统文化/文艺/古籍/国学/国学入门/宋词/唐诗/文学名著/茅盾文学奖/集部/汉学/中国当代文学
小说=小说/中国当代小说/青春/奇幻/短篇小说/爱情/历史小说/都市小说/中国古典小说/小说类/言情小说/网络小说/青春文学/言情/魔幻/外国小说/玄幻/长篇小说/武侠小说/中国小说/小說/奇幻小说/中篇小说/章回小说/历险小说/青春言情/轻小说/西方奇幻/玄幻小说/日本小说/长篇
推理悬疑=推理小说/悬疑/侦探/日系推理/欧美推理/日本推理/午夜文库/悬疑小说/悬疑推理/犯罪/烧脑/国产推理/侦探小说/恐怖/東野圭吾/推理/推理悬疑
科幻小说=科幻小说/科幻/世界科幻大师丛书/硬科幻/科幻经典/中国科幻
科技=科普/互联网/编程/科学/交互设计/用户体验/算法/web/科技/科技科技/UE/UCD/通信/交互/神经网络/程序/科学技术/自然/自然科学/计算机/生物学/天文/进化/动物/宇宙/科学史/计算机科学/脑科学/物理/物理学/科普读物/其他科普知识/人工智能/地理/科普文化/植物/生物/博物/博物学/产品设计/博弈论/量子力学/自然科学相关/生物科学/数据分析/软件开发/大数据/区块链/密码学/数学文化/计算科学/网络安全/产品经理/科技史/地理学/工具/数学
艺术设计=设计/建筑/电影/美术/音乐/戏剧/绘画/艺术史/漫画/半小时漫画/艺术
心理励志=心理学/心理/励志/女性/自我管理/治愈/成长/个人成长/职场/沟通/成功/人生/个人修养与自我完善/治愈系/社会以与交往/生活/个人管理/旅行/健康/自我成长/自我提升/成功心理学/时间管理/职业规划/女性主义/情感/心灵/灵修/社会心理学/个人提升/心理學/认知心理学/进化心理学/心灵成长/思维方式/鸡汤/认识精进/疗愈/人生哲学/心理自助/人际关系/自我发现/职业/身心灵
教育=小学书单/高中书单/初中书单/书单/小学语文阅读推荐/教育/绘本/少儿/童书/儿童/儿童文学/童话
医学养生=医学/中医/饮食/健身/养生/神经科学/医疗史/营养学/减肥/食物/癌症/生命
传记纪实=传记/回忆录/人物传记/纪实/非虚构''',

    'INVITE_MODE'   : False,
    'INVITE_CODE'   : 'mybooks',
    'INVITE_MESSAGE': '''本站为私人图书馆，需输入密码才可进行访问''',

    # 私人图书馆标准模式：所有页面与 /api 一律要求登录，访客权限（ALLOW_GUEST_*）随之失效。
    # 开启后 INVITE_MODE 被覆盖（访问码是比登录更弱的门，不叠加），见 BaseHandler.need_invited。
    'REQUIRE_LOGIN' : False,

    'ALLOW_GUEST_READ' : True,
    'ALLOW_GUEST_PUSH' : True,
    'ALLOW_GUEST_DOWNLOAD' : True,
    # 允许管理员为书籍创建分享链接，未登录访客可通过 /s/<token> 直接阅读。
    'ENABLE_SHARE_LINK' : False,
    "ENABLE_DOWNLOAD_QUOTA" : False,   # 是否启用每用户每日下载配额限制
    "ENABLE_USER_MEMOS": True,
    "GLOBAL_DOWNLOAD_QUOTA" : 10,       # 全局每日下载配额（用户未单独设置时使用），0表示不限制
    'ALLOW_REGISTER' : False,
    'HEADER': '',
    'FOOTER': '',
    'FOOTER_WATERMARK': 'PoxenStudio/MyBooks',
    'HIDE_PROJECT_LINKS': False,
    # 「反馈」弹窗内容管理员可改（build.22）：默认仍指上游，管理员可换成自己的二维码/文案/仓库链接
    'FEEDBACK_QR_URL': '/logo/link_gongzhonghao.jpg',
    'FEEDBACK_NOTICE': '',
    'FEEDBACK_GITHUB_URL': 'https://github.com/PoxenStudio/mybooks/issues',
    'SIDEBAR_ITEMS': [],                # 侧边栏显示的项目，空表示全部显示；仅含 "none" 表示全部隐藏
    'SIDEBAR_ITEMS_MIGRATED': False,    # 服务端内部标记（无 UI 控件）：管理员保存过设置页即置 True，之后 SIDEBAR_ITEMS 由管理员权威决定，读取期不再补齐旧默认列表缺的三个新项

    'FRIENDS': [],
    'SOCIALS': [],
    'DEVICES': [],
    'SIGNUP_MAIL_TITLE': '欢迎注册个人书屋',
    'SIGNUP_MAIL_CONTENT': '''
Hi, %(username)s！
欢迎注册%(site_title)s，这里虽然是个小小的图书馆，但是希望你找到所爱。

点击链接激活你的账号: %(active_link)s
''',

    'RESET_MAIL_TITLE': '密码重置',
    'RESET_MAIL_CONTENT': '''
Hi, %(username)s！

你刚刚在网站上提交了密码重置，请妥善保存你的新密码: %(password)s
''',
    'NEW_BOOK_MAIL_TITLE': '',
    'NWE_BOOK_MAIL_HEADER': ''
}
