
# ----------------------------------------
# 第一阶段，拉取 node 基础镜像并安装依赖，执行构建
# 必须用 Node 20+：@clack/core 使用了 node:util 的 styleText（Node >= 20.12 才有），
# Node 16 会在 import 阶段直接 SyntaxError。node:16-alpine 已 EOL，禁止回退。
FROM node:20-alpine AS builder
ARG BUILD_COUNTRY=""
ARG APP_VERSION=""

WORKDIR /build
# 【v3】先判定包内有没有预构建 dist，再决定要不要装 node 依赖。
# Dockerfile 没法在 COPY 之前判断文件是否存在，所以用 `COPY app/dist*` 通配符
# 做容错：目录存在就拷进来，不存在也不报错（COPY 通配符无匹配时行为随版本而异，
# 下一行的 RUN 才是权威判定）。
COPY app/dist* /build/dist/
RUN if [ -f /build/dist/index.html ]; then \
        echo "==> 预构建 dist：有（跳过 npm ci / generate）"; \
    else \
        echo "==> 预构建 dist：无（将现场 npm ci + generate）"; \
    fi
# 限定 Node 版本，避免落到旧版本又不报错
RUN node -e "const m=+process.versions.node.split('.')[0]; if(m<20){console.error('Node >= 20 required, got '+process.version); process.exit(1)}"
# npm 网络参数：默认超时短、失败即退出，国内/慢盘环境极易在 npm ci 阶段失败。
# 这里统一放宽（写在 /root/.npmrc，跨 RUN 层持久化），并在 CN 时换镜像源。
# 注意 npm ci 出错时的常见误区：多数是网络超时，不是 lock 文件问题。
#
# 超时取值的权衡（踩过坑）：fetch-timeout 放到 600000 后，如果 registry 根本不通，
# 重试会把这个超时反复吃满，一次失败要等 10 分钟才看到错误——这比失败本身更难受。
# 所以取 120s：正常百兆宽带下一个包远用不到 2 分钟，而真不通时 1~2 分钟就能报出来。
# 另外先做一次 15 秒的连通性探测，不通就立刻失败并给出明确提示。
# v3：整段只在「没有预构建 dist」时才执行 —— 带 dist 的包不需要 npm。
RUN if [ ! -f /build/dist/index.html ]; then \
        if [ "x${BUILD_COUNTRY}" = "xCN" ]; then \
            echo "using repo mirrors for ${BUILD_COUNTRY}"; \
            npm config set registry https://registry.npmmirror.com; \
        else \
            echo "using default npm registry"; \
        fi && \
        npm config set fetch-retries 5 && \
        npm config set fetch-retry-mintimeout 10000 && \
        npm config set fetch-retry-maxtimeout 60000 && \
        npm config set fetch-timeout 120000 && \
        npm config set maxsockets 8 && \
        echo "npm registry: $(npm config get registry)" && \
        if wget -q -T 15 -O /dev/null "$(npm config get registry)"; then \
            echo "registry reachable"; \
        else \
            echo "=================================================================="; \
            echo "ERROR: npm registry 不可达：$(npm config get registry)"; \
            echo "这是网络/DNS 问题，不是代码或 package-lock 的问题。排查："; \
            echo "  1) NAS 能否上网：curl -sI https://www.baidu.com | head -1"; \
            echo "  2) DNS 是否正常：nslookup registry.npmmirror.com"; \
            echo "  3) 若 NAS 走代理，给 Docker 配 HTTP_PROXY/HTTPS_PROXY"; \
            echo "  4) 也可在 docker-compose.yml 的 build.args 里把 BUILD_COUNTRY"; \
            echo "     改成非 CN 值，改用官方源再试"; \
            echo "=================================================================="; \
            exit 1; \
        fi; \
    else \
        echo "==> 包内带预构建 dist，跳过 npm registry 探测"; \
    fi

COPY app/package.json app/package-lock.json* ./
# dist 可能不存在（开发场景）；用通配符让 COPY 不因缺文件而失败。
COPY app/dist* /build/dist/

# 【v3 关键】dist 已经在最前面 COPY 过了，这里只补其余源码。
# 带预构建 dist 时【连 npm ci 都不做】：NAS 上一旦网络抖动，npm ci 重试两次
# 都失败整个 build 就挂，后面「检测到预构建 dist」的分支根本走不到。而带 dist
# 的包不需要 node_modules：
#   - /app-static/dist          已编译好的 SPA 产物 → COPY 进生产镜像
#   - myreader-dist/            独立的 Next.js standalone 产物 → COPY 进生产镜像
#   - 后端是 Python，不依赖 node
# 只有「改了前端但没重新出 dist」的开发场景才需要现场 build，见 else。
COPY app/ /build/
RUN if [ -f /build/dist/index.html ] && [ -f /build/dist/200.html ] \
       && [ -d /build/dist/_nuxt ]; then \
        echo "==> 检测到预构建 dist，跳过 npm ci 与 generate"; \
        mkdir -p /app-static/ && cp -r /build/dist /app-static/dist && \
        cp /build/nuxt.config.js /build/package.json /app-static/ 2>/dev/null || true; \
        cp /build/package-lock.json /app-static/ 2>/dev/null || true; \
        echo "==> dist 条目：$(find /app-static/dist -type f | wc -l) 个文件"; \
    else \
        echo "==> 无预构建 dist，现场执行 npm ci + generate（注意：必须是 generate，build/build-spa 只输出 .nuxt/ 不产生 dist/）"; \
        npm ci --no-fund --no-audit --loglevel=error \
            || (echo "npm ci failed, retrying with --prefer-offline ..." && \
                npm ci --no-fund --no-audit --loglevel=error --prefer-offline); \
        mkdir -p /app-static/ && npm run generate && \
        cp -r dist nuxt.config.js package* /app-static/; \
    fi

# 【硬门禁】dist 里的这批资源不是 nuxt generate 的产物（generate 会先清空 dist），
# 只能由 public/ 带出。缺了不会让 build 失败，但线上 PDF 阅读入口（settings.py 的
# PDF_VIEWER 指向 /static/pdfjs/web/viewer.html）直接 404，字体/壁纸/图标静默丢失。
# 所以在这里显式断言：宁可构建失败，也不要产出一个「装得上但缺文件」的镜像。
RUN if [ ! -f /app-static/dist/static/pdfjs/web/viewer.html ]; then \
        echo "=================================================================="; \
        echo "!! 构建中止：dist 缺少非构建资源 /static/pdfjs/web/viewer.html"; \
        echo "   原因：nuxt generate 会先清空 dist，pdfjs / 字体 / 壁纸 / 图标等"; \
        echo "         不是构建产物，必须由 public/ 带出。"; \
        echo "   检查：public/ 是否含 static/pdfjs、static/fonts、static/wallpaper、"; \
        echo "         static/images、static/js、static/toolbox-bridge.js、icons/、robots.txt；"; \
        echo "         且 app/nuxt.config.js 的 dir.static 指向 ../public。"; \
        echo "   校验：sh scripts/check-dist.sh（基线见该脚本 BASELINE，当前 768）。"; \
        echo "=================================================================="; \
        exit 1; \
    fi

# 生产阶段有两条 COPY --from=builder /app-static/dist/{logo,avatar}/ /data/books/…。
# buildkit 要求源路径必须存在，否则直接 failed to compute cache key，整个 build 中止。
# 这两个目录在 dist 里是「默认品牌资源 + 运行期用户数据」的混合体，clean generate
# 之后不一定有（generate 会先清空 dist），所以这里无条件补建空目录兜底：
# 有文件时不受影响，没有时也能让 COPY 通过并只创建目标目录。
RUN mkdir -p /app-static/dist/logo /app-static/dist/avatar

# ----------------------------------------
# 第二阶段，构建环境（基于预构建的基础镜像，含系统包、python依赖及calibre补丁）
# 基础镜像构建：make build-base-multiarch

# ----------------------------------------
# 测试阶段 (--break-system-packages)
# 仅供 CI/本地跑单测：docker build --target test -t mybooks-test .
# 日常部署用后面的 production 阶段；compose 里已指定 target: production，不会构建本阶段。
FROM docker.1ms.run/poxenstudio/mybooks_base:latest AS test
ARG BUILD_COUNTRY="CN"
# 与生产阶段一致：显式写 pip 镜像源，避免走 files.pythonhosted.org 超时
RUN if [ "x${BUILD_COUNTRY}" = "xCN" ]; then \
        printf '%s\n' \
            '[global]' \
            'index-url = https://mirrors.aliyun.com/pypi/simple/' \
            'extra-index-url = https://pypi.tuna.tsinghua.edu.cn/simple' \
            'trusted-host = mirrors.aliyun.com pypi.tuna.tsinghua.edu.cn' \
            'timeout = 120' \
            'retries = 10' \
            > /etc/pip.conf; \
    else \
        printf '%s\n' '[global]' 'timeout = 120' 'retries = 10' > /etc/pip.conf; \
    fi
RUN pip install flake8 pytest --break-system-packages
COPY requirements_release.txt /tmp/requirements.txt
COPY prebuilt/wheels/ /tmp/wheels/
RUN pip install --no-cache-dir --no-compile --find-links /tmp/wheels \
        -r /tmp/requirements.txt --break-system-packages && \
    rm -rf /root/.cache /root/.config/pip /tmp/requirements.txt /tmp/wheels /tmp/pip-* /var/tmp/*
# 插件源码不放进 /var/www/mybooks/calibre，避免目录名遮蔽真正的 calibre 包；测试经环境变量定位
ENV MYBOOKS_CALIBRE_PLUGINS_SRC=/opt/mybooks/calibre-plugins
COPY calibre/plugins/ /opt/mybooks/calibre-plugins/
RUN python3 /opt/mybooks/calibre-plugins/build.py --out /usr/lib/calibre/mybooks-plugins
COPY webserver/ /var/www/mybooks/webserver/
# third-party/foliate-js 与 edge-tts 已随源码包内置（从上游仓库拉取后去 .git），
# 不再依赖 git submodule。两分支逻辑保留作为兜底：目录万一被清空时
# foliate-js 缺失只影响微信读书批注导入（警告不中断），
# edge-tts 缺失则回退 PyPI 官方版（官方版 list_voices 无 proxy 参数）。
# 测试阶段：有就拷，没有就跳过并警告。
COPY third-party/ /tmp/third-party-test/
RUN mkdir -p /var/www/mybooks/third-party && \
    if [ -d /tmp/third-party-test/foliate-js ] && [ -n "$(ls -A /tmp/third-party-test/foliate-js 2>/dev/null)" ]; then \
        mkdir -p /var/www/mybooks/third-party/foliate-js && \
        cp -a /tmp/third-party-test/foliate-js/. /var/www/mybooks/third-party/foliate-js/; \
    else \
        echo "WARN(test): foliate-js 子模块为空，跳过"; \
    fi && \
    if [ -d /tmp/third-party-test/edge-tts ] && [ -n "$(ls -A /tmp/third-party-test/edge-tts 2>/dev/null)" ]; then \
        cp -a /tmp/third-party-test/edge-tts /var/www/mybooks/third-party/edge-tts && \
        pip install --no-cache-dir --no-compile -e /var/www/mybooks/third-party/edge-tts --break-system-packages; \
    else \
        echo "WARN(test): edge-tts 子模块为空，改用 PyPI 官方版"; \
        pip install --no-cache-dir --no-compile edge-tts --break-system-packages; \
    fi && \
    rm -rf /tmp/third-party-test
RUN cd /var/www/mybooks/webserver/services/cfi_gen && \
    npm config set registry https://registry.npmmirror.com && \
    npm ci --omit=dev
COPY tests/ /var/www/mybooks/tests/
CMD ["pytest", "/var/www/mybooks/tests"]

# ----------------------------------------
# 生产环境（必须是最后一个 FROM：Docker 默认构建最后阶段）
FROM docker.1ms.run/poxenstudio/mybooks_base:latest AS production
ARG BUILD_COUNTRY="CN"
ARG GIT_VERSION="4.7.0-build.03"
# 是否安装 faster-whisper（音频转写）。默认装：不带 torch，只多约 250MB，
# x86 上比 openai-whisper 快 4 倍以上，ARM/低端 CPU 也能跑 tiny/base。
# 不需要时构建加 --build-arg WITH_WHISPER=0 即可跳过，镜像体积回落。
ARG WITH_WHISPER="1"

LABEL Author="wxgoo"
LABEL Thanks="Rex <talebook@foxmail.com>, oldiy <oldiy2018@gmail.com>, PoxenStudio（上游 mybooks）"
LABEL org.opencontainers.image.title="mybooks (audiobook 定制版)" \
      org.opencontainers.image.description="基于 PoxenStudio/mybooks 的私人图书/有声书服务器定制版" \
      org.opencontainers.image.vendor="wxgoo" \
      org.opencontainers.image.source="https://github.com/wxgoo/audiobook-src" \
      org.opencontainers.image.url="https://github.com/wxgoo/audiobook-src" \
      org.opencontainers.image.documentation="https://github.com/wxgoo/audiobook-src#readme"

# ---- pip 全局配置（关键：解决 files.pythonhosted.org 超时）----
# 基础镜像里可能残留指向官方源的配置，这里显式覆盖：
#   index-url 走阿里云镜像；并加大超时与重试，弱网也能装完。
# 用 /etc/pip.conf 而不是 pip config set，保证容器内所有用户/所有 pip 调用都生效。
RUN if [ "x${BUILD_COUNTRY}" = "xCN" ]; then \
        printf '%s\n' \
            '[global]' \
            'index-url = https://mirrors.aliyun.com/pypi/simple/' \
            'extra-index-url = https://pypi.tuna.tsinghua.edu.cn/simple' \
            'trusted-host = mirrors.aliyun.com pypi.tuna.tsinghua.edu.cn' \
            'timeout = 120' \
            'retries = 10' \
            > /etc/pip.conf; \
        echo "pip: using aliyun mirror (timeout=120s, retries=10)"; \
    else \
        printf '%s\n' '[global]' 'timeout = 120' 'retries = 10' > /etc/pip.conf; \
        echo "pip: default index (timeout=120s, retries=10)"; \
    fi

# set default language
ENV TZ=Asia/Shanghai
ENV LANG=C.UTF-8
ENV PUID=1000
ENV PGID=1000
# HuggingFace 模型下载源。国内直连 huggingface.co 基本不通，whisper 模型
# 首次转写时会卡死/超时。hf-mirror.com 是国内常用镜像（含全部 Systran 模型）。
# 想用官方源就把它改成 https://huggingface.co，或构建时覆盖此 ENV。
ENV HF_ENDPOINT=https://hf-mirror.com
# hf-xet 走的是 cas-server.xethub.hf.co，镜像不代理这条通道且需要鉴权，
# 开着会报 401。走普通 HTTPS 下载即可（tiny 模型 75MB，速度无感）。
ENV HF_HUB_DISABLE_XET=1


# prepare dirs
RUN mkdir -p /data/log/nginx/ && \
    mkdir -p /data/books/library  && \
    mkdir -p /data/books/extract  && \
    mkdir -p /data/books/upload  && \
    mkdir -p /data/books/imports  && \
    mkdir -p /data/books/convert  && \
    mkdir -p /data/books/progress  && \
    mkdir -p /data/books/settings && \
    mkdir -p /data/books/logo && \
    mkdir -p /data/books/avatar && \
    mkdir -p /data/books/ssl && \
    mkdir -p /var/www/mybooks/ && \
    mkdir -p /var/www/myreader/ && \
    chmod a+w -R /data/log /data/books /var/www

COPY server.py /var/www/mybooks/
COPY docker/ /var/www/mybooks/docker/
COPY webserver/ /var/www/mybooks/webserver/
# 发布清单：包内这份是本地修订基线，/admin/version 会拿它和 Gitee 上的同名文件比对。
# 在线热更新成功后会直接改写容器内这份文件，所以目录必须可写（见 start.sh 的 chown）。
COPY update/ /var/www/mybooks/update/
# 运维工具（如 tools/category_backfill.py 读者组 #category 回填），容器内 docker exec 直接可用
COPY tools/ /var/www/mybooks/tools/
# 注：音频转写文稿的识别内核 srt_core.py 已随 webserver/ 一起进入镜像
# （webserver/toolbox/srt-tool/，工具箱「音频转写文稿」网页版依赖）；
# faster-whisper 本体见 requirements-optional.txt，未装时工具页面自动降级提示
# third-party/foliate-js 与 edge-tts 已随源码包内置（从上游仓库拉取后去 .git），
# 不再依赖 git submodule。以下逻辑保留两分支作为兜底：万一目录被清空，
# foliate-js 缺失只影响微信读书批注导入（警告不中断），
# edge-tts 缺失则回退 PyPI 官方版（注意官方版 list_voices 无 proxy 参数）。
# 只拷运行时会用到的 foliate-js（cfi_gen 依赖其 epubcfi.js）；
# epubreader-js(35M) 仅前端用，镜像内不需要，跳过以减小上下文与镜像体积。
COPY third-party/ /tmp/third-party-copy/
RUN mkdir -p /var/www/mybooks/third-party/foliate-js && \
    if [ -d /tmp/third-party-copy/foliate-js ] && [ -n "$(ls -A /tmp/third-party-copy/foliate-js 2>/dev/null)" ]; then \
        cp -a /tmp/third-party-copy/foliate-js/. /var/www/mybooks/third-party/foliate-js/; \
        echo "foliate-js: copied"; \
    else \
        echo "WARN: foliate-js 子模块为空，微信读书批注导入(CFI 生成)将不可用。"; \
        echo "      如需启用：git submodule update --init third-party/foliate-js 后重新构建。"; \
    fi && \
    if [ -d /tmp/third-party-copy/edge-tts ] && [ -n "$(ls -A /tmp/third-party-copy/edge-tts 2>/dev/null)" ]; then \
        cp -a /tmp/third-party-copy/edge-tts /var/www/mybooks/third-party/edge-tts; \
        echo "edge-tts: copied vendored source"; \
    fi && \
    rm -rf /tmp/third-party-copy
# edge-tts：优先用本地 submodule（PoxenStudio 定制版，支持 proxy 等参数）。
# 若 submodule 为空则退回 PyPI 官方版 —— 注意官方版 list_voices 不支持 proxy 参数，
# 在需要代理的环境下听书可能报错，构建时会打印提示。
RUN if [ -d /var/www/mybooks/third-party/edge-tts ] && \
       [ -f /var/www/mybooks/third-party/edge-tts/setup.py ]; then \
        echo "edge-tts: installing from vendored submodule (full features)"; \
        pip install --no-cache-dir --no-compile -e /var/www/mybooks/third-party/edge-tts --break-system-packages; \
    else \
        echo "WARN: edge-tts 子模块为空，改用 PyPI 官方版。"; \
        echo "      官方版 list_voices 不支持 proxy 参数，代理环境下听书可能异常。"; \
        echo "      如需完整功能：git submodule update --init third-party/edge-tts"; \
        pip install --no-cache-dir --no-compile edge-tts --break-system-packages; \
    fi
# cfi_gen 是纯 JS 小工具，用国内源装依赖（原命令没走镜像，国内很慢）
RUN cd /var/www/mybooks/webserver/services/cfi_gen && \
    npm config set registry https://registry.npmmirror.com && \
    npm ci --omit=dev
COPY conf/nginx/ssl.* /data/books/ssl/
COPY conf/nginx/mybooks.conf /etc/nginx/conf.d/
COPY conf/logrotate/mybooks-nginx /etc/logrotate.d/
COPY conf/supervisor/mybooks.conf /etc/supervisor/conf.d/
COPY --from=builder /app-static/ /var/www/mybooks/app/
COPY --from=builder /app-static/dist/logo/ /data/books/logo/
COPY --from=builder /app-static/dist/avatar/ /data/books/avatar/

# myreader-dist/ 是内嵌阅读器 MyReader 的 Next.js standalone 产物，来自
# 独立仓库 PoxenStudio/MyReader（见下方「怎么生成」）。它是构建产物，但
# **完整随本仓库入库**（2724 个条目、119 根相对符号链接）：.gitignore 末尾
# 有专门的反解规则，把 node_modules/ / src/ / *.mp3 等通配排除逐条放行。
# 所以联网 `git clone` 全新安装时它就在，不需要自己生成。
# 旧注释说「构建产物不入库、源码包里只有 .keep 占位」是 r8 时代口径，已更正。
#
# 产物被压扁或删掉时：/readerx、/reader、/api/mybooks/* 这些路由全部 502——
# supervisor 起 `node app/server.js` 找不到文件 → 9100 不监听 → nginx upstream
# 拒绝连接。其余功能不受影响。Windows 检出 / 图形解压工具会把 119 根软链变成
# 普通文件，所以 clone 必须带 `git -c core.symlinks=true`，且只在 Linux 上做。
#
# 怎么生成（仅在上游 MyReader 仓库重新出产物时才需要，普通安装不用）：
#   git submodule update --init packages/foliate-js packages/simplecc-wasm \
#       packages/js-mdict packages/qcms \
#       app/src-tauri/plugins/tauri-plugin-turso \
#       app/src-tauri/plugins/tauri-plugin-webview-upgrade
#   pnpm install --frozen-lockfile
#   pnpm --filter @poxenstudio/myreader setup-vendors
#   pnpm --filter @poxenstudio/myreader build-docker-dist
#   rsync -a --delete app/myreader-dist/ <mybooks>/myreader-dist/
#
# ── 为什么不能自己重新装依赖 ──
# 这份 node_modules 不是「可以重装一遍的依赖」，而是 Next 的 output file
# tracing 沿着真实 import 图裁剪出的最小闭包，里面三层 node_modules 互相用
# 相对符号链接串起来（app/node_modules/next -> ../../node_modules/.pnpm/…、
# app/.next/node_modules/js-md5-<hash> -> ../../../node_modules/.pnpm/…）。
# 所以 .dockerignore 里对 myreader-dist 下的 node_modules 做了显式放行，
# 少一层都会启动即 MODULE_NOT_FOUND。
COPY myreader-dist/ /var/www/myreader/

# ── 符号链接兜底：构建上下文里的链接状态会被原样 COPY 进来 ──
# 2026-11-09 现场实锤：myreader-dist 的 119 根相对符号链接，经 Windows
# 检出 / File Station 上传 / 图形界面解压后会被压扁成「内容=目标路径文本」
# 的普通文件或空目录。deploy.sh / upgrade.sh 会在构建前修复宿主机目录，但
# 手工 `docker compose build` 会绕过那一步，于是镜像里带着坏链接：
#   myreader 启动 FATAL，或显示 Ready 但 /reader/open 首个请求就 500。
# 这里按权威清单在镜像内再校验/重建一次（幂等，链接完好时只打印统计）。
COPY scripts/check-myreader-links.sh scripts/myreader-links.manifest /tmp/mrcheck/
RUN sh /tmp/mrcheck/check-myreader-links.sh --fix \
        --manifest /tmp/mrcheck/myreader-links.manifest /var/www/myreader && \
    rm -rf /tmp/mrcheck

# ── 权限归一：必须在 COPY 之后 ──
# 坑：上面第 191 行有 `chmod a+w -R /var/www`，但那是在 COPY 之前跑的。
# 产物是谁在哪台机器打包的，就带着谁的权限位进来。实测从 NAS 以 root
# 打包的产物是 drwx------ / -rwx------，COPY 后原样保留，于是：
#   supervisor 用 `gosu mybooks:mybooks node app/server.js` 启动
#   → mybooks 用户 Permission denied
#   → Node 把「读不到」报成 Error: Cannot find module '.../app/server.js'
#   → 进程 FATAL → 9100 不监听 → /readerx 全 502 → 书页空白
# 以 root 身份手动跑 `node -e require(...)` 却是好的，极具迷惑性。
# 所以这里补一刀，不依赖产物自带的权限位。
RUN chown -R mybooks:mybooks /var/www/myreader && \
    chmod -R u+rwX,go+rX /var/www/myreader && \
    echo "myreader 权限已归一" && \
    ls -ld /var/www/myreader/app /var/www/myreader/app/server.js
COPY release_notes.txt /var/www/mybooks/app/dist/static/
COPY thanks_to.txt /var/www/mybooks/app/dist/static/


# 相对于base镜像，如果有临时增加的一两个库，可以使用这个方法更新
COPY requirements_release.txt /tmp/requirements.txt
# 预置 wheel：djvu-rs 的 wheel 约 1.1MB，部分网络环境从任何源下载都会超时，
# 直接打进镜像，pip 优先用本地文件，彻底不联网。
COPY prebuilt/wheels/ /tmp/wheels/
# MyBooks 自带的 calibre 插件（DjVu/CBZ/UVZ 元数据）
COPY calibre/plugins/ /tmp/calibre-plugins/
# 装依赖 + 装 calibre 插件 + 收尾初始化，合并成一个 RUN：
# 每多一个 RUN 就多一层、多一次容器启停；这三步互相依赖，合并后层数更少、镜像更小。
RUN set -eux; \
    # 优先从本地 wheel 装（离线、零等待）；缺的包才回落到镜像源
    pip install --no-cache-dir --no-compile --find-links /tmp/wheels \
        -r /tmp/requirements.txt --break-system-packages; \
    rm -rf /root/.cache /root/.config/pip /tmp/requirements.txt /tmp/wheels /tmp/pip-* /var/tmp/*; \
    # 音频转写（可选）：faster-whisper 用 CTranslate2 推理，不需要 torch。
    # 注意 av 的版本：faster-whisper 1.2.x 仍调用 av.open(metadata_errors=...)，
    # 而 av 16+ 删掉了这个参数，装上 av 19 会直接 TypeError。锁定 av<16。
    if [ "$WITH_WHISPER" = "1" ]; then \
        echo "installing faster-whisper ..."; \
        pip install --no-cache-dir --no-compile --break-system-packages \
            "faster-whisper" "av<16"; \
        python3 -c "import faster_whisper, av; print('faster-whisper', faster_whisper.__version__, '/ av', av.__version__)" \
            || (echo "ERROR: faster-whisper 安装后无法导入" && exit 1); \
        python3 -c "from faster_whisper import WhisperModel; import inspect; \
assert 'vad_filter' in inspect.signature(WhisperModel.transcribe).parameters, 'API 不匹配'; \
print('faster-whisper API check OK')" \
            || (echo "ERROR: faster-whisper API 与预期不符" && exit 1); \
    else \
        echo "skip faster-whisper (WITH_WHISPER=$WITH_WHISPER)"; \
    fi; \
    rm -rf /root/.cache /root/.config/pip /tmp/pip-* /var/tmp/*; \
    # 音频转换（EPUB → 有声书）：webserver/epub_to_audio 是上游内置的第三方工具，
    # 不在主 requirements.txt 里，这里单独装它缺的几样。
    # 为什么不直接 pip install -r webserver/epub_to_audio/requirements.txt：
    # 那份表里有 gradio 5.33 + gradio_log + docker，会把基础镜像里已装好的
    # numpy / pydantic 顶到不兼容的版本，连 calibre 一起弄坏。生产只跑命令行
    # （main.py），不跑它的 WebUI（main_ui.py），所以那三个包不装。
    # 也不装 edge-tts：Dockerfile 上面已经从 third-party/edge-tts 装了 PoxenStudio
    # 定制版（支持 proxy），定制版进不了 PyPI，重装会覆盖成官方版、丢掉 proxy 参数。
    pip install --no-cache-dir --no-compile --find-links /tmp/wheels \
        "EbookLib==0.19" "mutagen==1.47.0" "pydub==0.25.1" "sentencex==0.6.1" \
        --break-system-packages; \
    python3 -c "import ebooklib, mutagen, pydub, sentencex, edge_tts; print('epub->audio deps OK')" \
        || (echo "ERROR: EPUB 转音频依赖装完无法导入，检查上面的 pip 输出" && exit 1); \
    rm -rf /root/.cache /root/.config/pip /tmp/pip-* /var/tmp/*; \
    # MyBooks 自带的 calibre 插件（DjVu/CBZ/UVZ 元数据）
    python3 /tmp/calibre-plugins/build.py --out /usr/lib/calibre/mybooks-plugins; \
    rm -rf /tmp/calibre-plugins; \
    # logrotate 会忽略 group/other 可写的配置文件，构建机 umask 为 002 时 COPY 进来是 0664
    chmod 644 /etc/logrotate.d/mybooks-nginx; \
    rm -f /etc/nginx/conf.d/default.conf; \
    rm -rf /var/www/html; \
    cd /var/www/mybooks/; \
    ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime; \
    echo ${TZ} > /etc/timezone; \
    if [ -z "${GIT_VERSION:-}" ]; then echo "ERROR: GIT_VERSION 为空，触发版本锁保护（见 scripts/check-version-lock.py）" >&2; exit 1; fi; \
    echo "VERSION = \"$GIT_VERSION\"" > webserver/version.py; \
    echo 'settings = {}' > /data/books/settings/auto.py; \
    chmod a+w /data/books/settings/auto.py; \
    calibredb add --library-path=/data/books/library/ -r docker/book/; \
    python3 server.py --syncdb; \
    python3 server.py --update-config; \
    find webserver -name "*.pyc" -type f -delete; \
    (python3 -m compileall -q -x "webserver/test/" webserver server.py || true); \
    rm -rf app/src; \
    rm -rf app/dist/logo; \
    ln -s /data/books/logo app/dist/logo; \
    rm -rf app/dist/avatar; \
    ln -s /data/books/avatar app/dist/avatar; \
    mkdir -p /prebuilt/; \
    mv /data/* /prebuilt/; \
    chmod +x /var/www/mybooks/docker/start.sh

EXPOSE 80 443

VOLUME ["/data"]

CMD ["/var/www/mybooks/docker/start.sh"]

# ----------------------------------------
# 测试阶段 (--break-system-packages)
# 仅供 CI/本地跑单测使用：docker build --target test && docker run ... pytest
# 日常部署用 production 阶段，不要用这个。
