.PHONY: all build push test plugin

# 运行期版本锁：4.6.0-build.21 =「上游已发布 tag 4.6.0」+「第 20 次本地构建」。
# 该写法同时是合法 semver 预发布标记与合法 Docker tag（字符集 [A-Za-z0-9_.-]），无需转换。
# 理由：以前用分支名当显示版本，会把 webserver/version.py 顶成 opt/p0-p1 之类，
# 既不可追溯也会让“是否真的生效”无法判断。这里改为不匹配即报错退出（fail-fast），
# 比“静默忽略用户传入的 VER”更容易发现口径错误。
VERSION_LOCK := 4.6.0-build.21
VER := $(VERSION_LOCK)
ifneq ($(strip $(VER)),$(VERSION_LOCK))
$(error 版本锁: VER=$(VER) 与运行期版本 $(VERSION_LOCK) 不一致。这是防版本回退/被交付标签覆盖的保护，不是普通构建失败；请去掉 VER 覆盖，或先同步修改 webserver/version.py 与 scripts/check-version-lock.py)
endif
IMAGE := poxenstudio/mybooks:$(VER)
REPO1 := poxenstudio/mybooks:latest
TAG1 := poxenstudio/mybooks:server-side-render
TAG2 := poxenstudio/mybooks:server-side-render-$(VER)
BASE_IMAGE := poxenstudio/mybooks_base:$(VER)
BASE_REPO1 := poxenstudio/mybooks_base:latest
BUILDER := shukubuilder
ARCH := $(shell uname -m)
PLATFORM ?= linux/$(shell if [ "$(ARCH)" = "x86_64" ]; then echo "amd64"; elif [ "$(ARCH)" = "aarch64" ] || [ "$(ARCH)" = "arm64" ]; then echo "arm64"; else echo "amd64"; fi)

$(info Building for platform: $(PLATFORM))
$(info Building image: $(IMAGE))
$(info Building tag1: $(TAG1))
$(info Building tag2: $(TAG2))


all: build up

build:
	docker build --pull --platform=$(PLATFORM) --no-cache=false --build-arg BUILD_COUNTRY=CN --build-arg GIT_VERSION=$(VER) \
		-f Dockerfile -t $(IMAGE) -t $(REPO1) --target production .

push:
	docker push $(IMAGE)
	docker push $(REPO1)

# 初始化多架构构建环境（Linux必须要运行一次），不要使用snap安装的docker
setup-multiarch:
	docker run --privileged --rm tonistiigi/binfmt --install all
	docker buildx create --use --name $(BUILDER) || docker buildx use $(BUILDER)
	docker buildx inspect $(BUILDER) --bootstrap


# 构建并推送基础镜像多架构版本（ubuntu + 系统包 + python依赖 + calibre补丁）
# 仅在 requirements.txt / calibre补丁 / 系统包变更时需重新构建
build-base-multiarch:
	docker buildx build --pull --platform=linux/amd64,linux/arm64 \
		--builder $(BUILDER) \
		--build-arg BUILD_COUNTRY=CN \
		-f Dockerfile.base -t $(BASE_IMAGE) -t $(BASE_REPO1) \
		--load .

# 构建并推送多架构镜像（同时支持 amd64 和 arm64）
build-multiarch:
	docker buildx build --pull --platform=linux/amd64,linux/arm64 \
		--builder $(BUILDER) \
		--build-arg BUILD_COUNTRY=CN --build-arg GIT_VERSION=$(VER) \
		-f Dockerfile -t $(IMAGE) -t $(REPO1) \
		--target production --push .

# 仅构建多架构镜像到本地缓存（不推送）
build-multiarch-local:
	docker buildx build --pull --platform=linux/amd64,linux/arm64 \
		--builder $(BUILDER) \
		--build-arg BUILD_COUNTRY=CN --build-arg GIT_VERSION=$(VER) \
		-f Dockerfile -t $(IMAGE) -t $(REPO1) \
		--target production --load .

lint:
	flake8 webserver --count --select=E9,F63,F7,F82 --show-source --statistics --exclude epub_to_audio,test
	flake8 webserver --count --statistics --config .style.yapf --exclude epub_to_audio,test

pytest: lint
	pytest tests

PLUGIN_DIR := koreader_plugin/mybooks.koplugin
PLUGIN_OUT := koreader_plugin/dist/mybooks_koplugin.zip

plugin:
	@mkdir -p $(dir $(PLUGIN_OUT))
	@rm -f $(PLUGIN_OUT)
	@cd koreader_plugin && zip -rq $(abspath $(PLUGIN_OUT)) mybooks.koplugin -x "*.DS_Store" "*.git*"
	@echo "Built $(PLUGIN_OUT)"

up:
	docker compose up

down:
	docker compose stop

# ---- 本地快速构建（改代码后重建，几十秒级）----
# 原理：BuildKit + 本地目录缓存，只重跑发生变化的层；
# 前端 npm ci 与 webpack 产物会被缓存，源码小改不会重装依赖。
CACHE_DIR := $(CURDIR)/.buildcache

fast-build:
	DOCKER_BUILDKIT=1 docker build \
		--build-arg BUILD_COUNTRY=CN \
		--build-arg GIT_VERSION=$(VER) \
		--cache-from type=local,src=$(CACHE_DIR) \
		--cache-to type=local,dest=$(CACHE_DIR),mode=max \
		-t mybooks-local:latest --target production .

# 一键：构建 + 启动
fast-up: fast-build
	docker compose up -d --no-build

# 清掉构建缓存（镜像出怪问题时用）
clean-cache:
	rm -rf $(CACHE_DIR)

.PHONY: fast-build fast-up clean-cache
