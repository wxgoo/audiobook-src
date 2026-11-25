# -*- coding: utf-8 -*-
"""MyNexus 数据「升级改名 deploy-stack 就不丢」+ 模型配置单一来源契约。

现场事故：onekey-install.sh 每次升级都把 deploy-stack 改名为 deploy-stack.old，
而老 compose 把 MyNexus 的 /data、/config 挂在 ./mynexus-data、./mynexus-config
（相对 compose 文件 = 在 deploy-stack 内部）。改名后新栈挂的是全新空目录，
AI 解析出来的 mynexus.db / vectorstore / uploads 全被埋进 .old，表现为「数据没了」。

本文件用静态契约钉死修复：
  1) compose 的两个挂载点走 .env 绝对路径变量，不再写死 deploy-stack 内的相对路径；
  2) .env 模板给出 deploy-stack 之外的默认绝对路径；
  3) install.sh 解析/校验目录、预建授权、并从旧目录幂等迁移数据；
  4) 模型配置单一来源 = .env：LLM 与内置 embedding 都由 env 注入覆盖 config.yaml。
"""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
STACK = ROOT / "deploy" / "mybooks-mynexus-stack"
COMPOSE = STACK / "docker-compose.yml"
ENV_FILE = STACK / ".env"
INSTALL = STACK / "install.sh"


def test_compose_mounts_mynx_dirs_from_env_outside_stack():
    t = COMPOSE.read_text(encoding="utf-8")
    # 必须走变量，且默认值可以保留相对兜底，但正文不能只挂写死的 ./mynexus-data
    assert "${MYNEXUS_DATA_DIR:-./mynexus-data}:/data" in t
    assert "${MYNEXUS_CONFIG_DIR:-./mynexus-config}:/config" in t
    # 不允许出现「只挂相对路径」的裸写法
    assert "\n      - ./mynexus-data:/data" not in t
    assert "\n      - ./mynexus-config:/config" not in t


def test_env_declares_external_absolute_dirs():
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    active = [ln for ln in lines if ln and not ln.lstrip().startswith("#")]
    data = [ln for ln in active if ln.startswith("MYNEXUS_DATA_DIR=")]
    cfg = [ln for ln in active if ln.startswith("MYNEXUS_CONFIG_DIR=")]
    assert len(data) == 1 and len(cfg) == 1, (data, cfg)
    dv = data[0].split("=", 1)[1]
    cv = cfg[0].split("=", 1)[1]
    assert dv.startswith("/") and cv.startswith("/")
    # 默认必须落在 deploy-stack 之外；老栈名不能出现在路径里
    for v in (dv, cv):
        assert "deploy-stack" not in v, v
        assert v.startswith("/volume1/docker/audiobook-data/"), v


def test_install_resolves_and_guards_program_dir():
    t = INSTALL.read_text(encoding="utf-8")
    for needle in (
        "resolve_mynx_dirs()",
        "is_inside_program_dir()",
        "migrate_mynx_dir()",
        "env_set MYNEXUS_DATA_DIR",
        "env_set MYNEXUS_CONFIG_DIR",
        'migrate_mynx_dir "$OLD_STACK_DIR/mynexus-data"',
        'migrate_mynx_dir "$OLD_STACK_DIR/mynexus-config"',
        'step "6b/7 迁移旧目录里的 MyNexus 数据（幂等）"',
    ):
        assert needle in t, f"install.sh 缺少: {needle}"
    # 迁移必须在「全新安装」分支之外也能跑到，否则旧容器被删时数据仍丢。
    migrate_block = t.split('step "6b/7 迁移旧目录里的 MyNexus 数据（幂等）"', 1)[1].split(
        'step "7/7 启动并健康检查"', 1)[0]
    assert 'migrate_mynx_dir "$OLD_STACK_DIR/mynexus-data"' in migrate_block
    # 预建目录必须用外置变量，不能再用 $SCRIPT_DIR/mynexus-data
    assert "$MYNX_DATA_DIR $MYNX_CONFIG_DIR" in t
    assert "$SCRIPT_DIR/mynexus-data $SCRIPT_DIR/mynexus-config" not in t


def test_install_stops_old_mynx_before_migration():
    t = INSTALL.read_text(encoding="utf-8")
    assert "docker stop mynexus" in t
    assert "docker rm mynexus" in t


def test_model_config_single_source():
    """模型配置只需改 .env；env 覆盖 config.yaml，embedding 用镜像内置模型。"""
    compose = COMPOSE.read_text(encoding="utf-8")
    env = ENV_FILE.read_text(encoding="utf-8")
    # LLM 四个键 + timeout 都由 compose 从 .env 注入
    for key in (
        "MYNEXUS_LLM_PROVIDER: ${LLM_PROVIDER",
        "MYNEXUS_LLM_OPENAI_API_KEY: ${LLM_API_KEY}",
        "MYNEXUS_LLM_OPENAI_BASE_URL: ${LLM_BASE_URL",
        "MYNEXUS_LLM_OPENAI_MODEL: ${LLM_MODEL",
        "MYNEXUS_LLM_OPENAI_TIMEOUT: ${LLM_TIMEOUT",
    ):
        assert key in compose, key
    # base URL 默认值不能写死带 /v1 的合法路径之外的完整 endpoint
    assert "MYNEXUS_LLM_OPENAI_BASE_URL: ${LLM_BASE_URL:-https://api.deepseek.com}" in compose
    # embedding 钉死为 local + 镜像内置路径
    assert "MYNEXUS_EMBEDDING_PROVIDER: ${MYNEXUS_EMBEDDING_PROVIDER:-local}" in compose
    assert "MYNEXUS_EMBEDDING_LOCAL_MODEL_PATH: ${MYNEXUS_EMBEDDING_LOCAL_MODEL_PATH:-/usr/share/models}" in compose
    assert "LLM_TIMEOUT=90" in env
