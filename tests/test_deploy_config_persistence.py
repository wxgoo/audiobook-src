# -*- coding: utf-8 -*-
"""部署配置的「改完能留住」契约。

两起现场事故促成这个文件：

1) 用户在设置页把 AI 地址/模型改成 DeepSeek，一重装 onekey-install.sh 又回到
   openrouter 默认。根因：manual.py（只读挂载、加载优先级最高）无条件用 .env
   默认值覆盖了 auto.py 里用户保存的值。

2) 交付镜像经 docker export/import 展平后，start.sh 的可执行位被抹成 644，
   而 CMD 直接 exec 该脚本 → permission denied，容器反复重启起不来。

这里用静态契约把「预填而非覆盖」「CMD 走 /bin/sh」「安装器带回用户配置」钉死，
避免以后再改回去。
"""
import importlib.util
import os
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANUAL_PY = ROOT / "deploy" / "mybooks-mynexus-stack" / "settings" / "manual.py"
INSTALL_SH = ROOT / "deploy" / "mybooks-mynexus-stack" / "install.sh"
ENV_FILE = ROOT / "deploy" / "mybooks-mynexus-stack" / ".env"
DOCKERFILE = ROOT / "Dockerfile"
START_SH = ROOT / "docker" / "start.sh"


def _load_manual(user_saved, environ):
    """在一个隔离的临时目录里加载 manual.py，auto 模块用 user_saved 顶替。"""
    import tempfile

    tmp = pathlib.Path(tempfile.mkdtemp())
    (tmp / "manual.py").write_text(MANUAL_PY.read_text(encoding="utf-8"), encoding="utf-8")

    old_path = list(sys.path)
    old_modules = {k: sys.modules.get(k) for k in ("manual", "auto")}
    old_environ = dict(os.environ)
    try:
        sys.path.insert(0, str(tmp))
        for k in ("manual", "auto"):
            sys.modules.pop(k, None)
        fake_auto = types.ModuleType("auto")
        fake_auto.settings = dict(user_saved)
        sys.modules["auto"] = fake_auto
        os.environ.clear()
        os.environ.update(environ)

        spec = importlib.util.spec_from_file_location("manual", tmp / "manual.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["manual"] = mod
        spec.loader.exec_module(mod)
        return dict(mod.settings)
    finally:
        sys.path[:] = old_path
        for k, v in old_modules.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        os.environ.clear()
        os.environ.update(old_environ)


BASE_ENV = {
    "AI_BASE_URL": "https://openrouter.ai/api/v1",
    "AI_MODEL": "openrouter/free",
    "AI_API_KEY": "sk-or-v1-你的OpenRouter密钥",  # 占位符
    "AI_MCP_TOKEN": "",
    "MYNEXUS_AUTO_URL": "http://mynexus",
    "MYNEXUS_API_TOKEN": "env-token",
}


def test_manual_prefills_when_user_has_no_saved_value():
    """全新安装：auto.py 没值 → 用 .env 预填（行为不变）。"""
    out = _load_manual({}, BASE_ENV)
    assert out["AI_API_URL"] == "https://openrouter.ai/api/v1"
    assert out["AI_MODEL"] == "openrouter/free"
    assert out["MYNEXUS_TOKEN"] == "env-token"
    # 占位符 key 依旧被清洗成空，避免 SDK ascii 崩溃
    assert out["AI_DEEPSEEK_API_KEY"] == ""


def test_manual_respects_user_saved_deepseek():
    """核心回归：用户在设置页存过 DeepSeek → manual.py 不能盖回 openrouter。"""
    saved = {
        "AI_API_URL": "https://api.deepseek.com",
        "AI_MODEL": "deepseek-flash",
        "AI_DEEPSEEK_API_KEY": "sk-real-deepseek-key",
        "MYNEXUS_TOKEN": "user-saved-mynexus-token",
    }
    out = _load_manual(saved, BASE_ENV)
    assert out["AI_API_URL"] == "https://api.deepseek.com"
    assert out["AI_MODEL"] == "deepseek-flash"
    assert out["AI_DEEPSEEK_API_KEY"] == "sk-real-deepseek-key"
    assert out["MYNEXUS_TOKEN"] == "user-saved-mynexus-token"


def test_manual_ignores_misfilled_mnx_per_user_token():
    """设置页若误填 mnx_ 开头的 per-user token，必须忽略、回落到 .env 静态集成 token。

    MyNexus 对带 X-MyBooks-User-ID 的 chat 请求只认静态 MYNEXUS_API_TOKEN，
    per-user token 会触发 403 external user identity requires integration token。
    """
    saved = {"MYNEXUS_TOKEN": "mnx_abc123savedPerUserToken"}
    out = _load_manual(saved, BASE_ENV)
    assert out["MYNEXUS_TOKEN"] == "env-token", out["MYNEXUS_TOKEN"]
    # 大写前缀也应被识别（lower() 归一化）
    out2 = _load_manual({"MYNEXUS_TOKEN": "MNX_upper"}, BASE_ENV)
    assert out2["MYNEXUS_TOKEN"] == "env-token"


def test_manual_keeps_plain_static_token_user_value():
    """非 mnx_ 前缀的用户保存值（如 install.sh 生成的 hex 静态 token）仍被尊重。"""
    saved = {"MYNEXUS_TOKEN": "a" * 48}
    out = _load_manual(saved, BASE_ENV)
    assert out["MYNEXUS_TOKEN"] == "a" * 48


def test_install_sh_carries_user_ai_config_from_old_env():
    """安装器必须把用户改过的 URL/模型从旧 .env 带回，而不是只继承 3 个 key。"""
    t = INSTALL_SH.read_text(encoding="utf-8")
    for key in ("AI_BASE_URL", "AI_MODEL", "LLM_BASE_URL", "LLM_MODEL", "LLM_PROVIDER"):
        assert f"carry_config_from_old {key}" in t, f"install.sh 未带回用户配置 {key}"
    assert "carry_config_from_old()" in t, "缺少 carry_config_from_old 函数定义"


def test_env_template_defaults_to_deepseek():
    """随包 .env 模板应以用户实际在用的 DeepSeek 为默认，不再写死 OpenRouter。"""
    t = ENV_FILE.read_text(encoding="utf-8")
    assert "LLM_BASE_URL=https://api.deepseek.com" in t
    assert "LLM_MODEL=deepseek-flash" in t
    assert "AI_BASE_URL=https://api.deepseek.com" in t
    assert "AI_MODEL=deepseek-flash" in t
    # key 仍是占位符（安全），且是 DeepSeek 的 sk- 前缀而非 OpenRouter 的 sk-or-v1-
    assert "LLM_API_KEY=sk-你的DeepSeek密钥" in t
    assert "AI_API_KEY=sk-你的DeepSeek密钥" in t
    # 正文不应再把 openrouter 当作当前默认（仅允许出现在「备选」注释里）
    active = [ln for ln in t.splitlines()
              if ln and not ln.lstrip().startswith("#")]
    assert not any("openrouter" in ln.lower() for ln in active), active


def test_install_sh_skips_legacy_openrouter_defaults():
    """重装时不能把旧包写死的 OpenRouter 默认带回，否则新模板的 DeepSeek 又被盖掉。"""
    t = INSTALL_SH.read_text(encoding="utf-8")
    assert "is_legacy_default()" in t
    assert 'https://openrouter.ai/api/v1' in t
    assert 'openrouter/free' in t
    # carry_config_from_old 的守卫条件必须包含 legacy 判断
    assert "is_placeholder_key \"$oldval\" || is_legacy_default \"$key\" \"$oldval\"" in t


def test_dockerfile_cmd_uses_bin_sh():
    """CMD 走 /bin/sh 读脚本，不依赖 start.sh 的可执行位（展平后仍可起）。"""
    t = DOCKERFILE.read_text(encoding="utf-8")
    assert 'CMD ["/bin/sh", "/var/www/mybooks/docker/start.sh"]' in t


def test_start_sh_is_executable_in_git():
    """源码里 start.sh 必须有可执行位，正常 build 出的镜像脚本本身也能直接 exec。"""
    assert os.access(START_SH, os.X_OK), "docker/start.sh 缺可执行位"
