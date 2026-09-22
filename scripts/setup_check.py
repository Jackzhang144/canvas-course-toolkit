#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""首次使用的初始化与状态检测。

设计要点：
- **只检测、不猜测**：把「还差什么」算成一个明确的状态码，命令与 AI 代理都据此引导用户。
- **幂等且不破坏**：已经配好的 `.env` 绝不覆盖，只补缺的键。
- **不联网**：这里只判断本地配置，连通性交给 `canvas doctor`（需要令牌）。

状态码一览（`check_setup()` 返回）：
    no_env          还没有 .env
    missing_host    有 .env 但 CANVAS_HOST 空着
    missing_token   有 .env 但 CANVAS_API_TOKEN 空着
    token_placeholder  令牌值还是模板占位符（等于没填）
    host_looks_wrong   host 里带着 /api/v1 或明显的粘贴痕迹
    ready           配置齐全，可以去跑 canvas doctor
"""
from __future__ import annotations

import os
import re

from scripts.canvas_client import ENV_PATH, load_env, normalize_host

#: 这些值出现在令牌位说明用户复制的是模板/说明文字，不是真令牌
PLACEHOLDER_MARKERS = (
    "粘贴", "在这里", "your", "token", "xxxx", "…", "...", "填", "<", ">",
)

#: 生成 .env 时写入的内容（与仓库根的 .env.example 保持一致）
ENV_TEMPLATE = """# Canvas 凭据（本文件不入库；不要提交、不要贴给别人、不要截图）
#
# CANVAS_HOST：你的 Canvas 地址。写域名即可，程序会自动补 https://
#   托管版 : your-school.instructure.com
#   自建版 : canvas.your-school.edu
CANVAS_HOST="{host}"

# CANVAS_API_TOKEN：访问令牌。获取方式：
#   登录 Canvas → 头像 Account/账户 → Settings/设置 → Approved Integrations
#   → New Access Token → 生成后立刻复制（只显示一次）
CANVAS_API_TOKEN="{token}"

# 可选：默认学期，仅用于你自己过滤课程
CANVAS_TERM=""
"""


def _uncommented(line):
    """判断 `.env` 里这一行是不是「被注释掉的模板行」。"""
    return line.lstrip().startswith("#")


def looks_like_placeholder(token):
    """令牌位是否还是模板占位符（而不是真令牌）。

    真令牌是长串无空格的随机字符；含中文、空格或常见模板词就不像。
    """
    value = (token or "").strip()
    if not value:
        return True
    if len(value) < 20:                      # 真令牌远长于这个
        return True
    lowered = value.lower()
    if re.search(r"[\u4e00-\u9fff\s]", value):   # 含中文或空白
        return True
    return any(marker in lowered for marker in ("your", "xxxx", "粘贴", "填"))


def host_problem(host):
    """返回 host 的明显问题说明；没问题返回 None。"""
    value = (host or "").strip().strip("\"'")
    if not value:
        return None
    if "/api/" in value:
        return "CANVAS_HOST 只需要域名，不要带 /api/v1（程序会自己拼）"
    if "/courses/" in value or "/profile" in value or "/settings" in value:
        return "CANVAS_HOST 填的是具体页面地址，只要域名部分即可"
    return None


def check_setup(env_path=None, env=None):
    """检测初始化状态。

    返回 dict：{state, env_path, host, detail, next_steps}
    - 传入 `env`（dict）可绕过文件，便于测试；
    - 只读，不修改任何文件。
    """
    env_path = env_path or ENV_PATH
    values = dict(env) if env is not None else load_env(env_path)
    env_exists = env is not None or os.path.exists(env_path)

    host = (values.get("CANVAS_HOST") or "").strip()
    token = (values.get("CANVAS_API_TOKEN") or "").strip()

    def result(state, detail, steps):
        return {"state": state, "env_path": env_path, "host": host,
                "detail": detail, "next_steps": steps}

    if not env_exists:
        return result("no_env", "还没找到 %s" % env_path, [
            "运行 `uv run canvas init` 生成 .env（默认不会覆盖已存在的文件）",
            "然后填入你的 Canvas 域名与访问令牌，令牌获取方式见 docs/setup.md",
            "填好后运行 `uv run canvas doctor` 验证",
        ])

    if not host:
        return result("missing_host", "CANVAS_HOST 还是空的", [
            "在 %s 里填写 CANVAS_HOST，例如 https://your-school.instructure.com" % env_path,
        ])

    problem = host_problem(host)
    if problem:
        return result("host_looks_wrong", problem, [
            "把 CANVAS_HOST 改成纯域名后重跑 `uv run canvas doctor`",
        ])

    if not token:
        return result("missing_token", "CANVAS_API_TOKEN 还是空的", [
            "登录 Canvas → 头像 Account/账户 → Settings/设置 → Approved Integrations",
            "→ New Access Token → 生成后立刻复制，粘贴到 %s" % env_path,
            "然后运行 `uv run canvas doctor` 验证",
        ])

    if looks_like_placeholder(token):
        return result("token_placeholder",
                      "CANVAS_API_TOKEN 看起来还是模板占位符，不是真令牌",
                      ["换成你从 Canvas 生成的那一串令牌后重跑 `uv run canvas doctor`"])

    return result("ready", "配置齐全（令牌已读到，长度 %d）" % len(token), [
        "运行 `uv run canvas doctor` 验证连通性与权限",
        "然后 `uv run canvas courses` 看课程，`uv run canvas download <course_id>` 下载资料",
    ])


def ensure_env_file(env_path=None, host=None, token=None):
    """必要时创建 `.env`。

    返回 (action, path, message)，action ∈ {"created", "kept", "completed"}：
    - `created`：原本不存在，已按模板创建；
    - `kept`：已存在，**一个字节都不改**（避免覆盖用户已填好的令牌）；
    - `completed`：已存在但缺 CANVAS_HOST/CANVAS_API_TOKEN 键，只追加缺的键与注释。

    绝不覆盖已有的任何键值。调用方负责把结果告诉用户。
    """
    env_path = env_path or ENV_PATH
    if not os.path.exists(env_path):
        parent = os.path.dirname(os.path.abspath(env_path))
        os.makedirs(parent, exist_ok=True)     # 首次创建时父目录可能还不存在
        with open(env_path, "w", encoding="utf-8") as fh:
            fh.write(ENV_TEMPLATE.format(host=host or "", token=token or ""))
        try:
            os.chmod(env_path, 0o600)          # 只有自己能读
        except OSError:
            pass
        return ("created", env_path,
                "已创建 %s（权限 600）。请填入 CANVAS_HOST 与 CANVAS_API_TOKEN。" % env_path)

    values = load_env(env_path)
    missing = [key for key in ("CANVAS_HOST", "CANVAS_API_TOKEN") if key not in values]
    if not missing:
        return ("kept", env_path,
                "%s 已存在且含所需键，未做任何改动（不会覆盖你的令牌）。" % env_path)

    with open(env_path, "a", encoding="utf-8") as fh:
        fh.write("\n# 下面两行由 `canvas init` 补齐（原先缺少）：\n")
        for key in missing:
            fh.write('%s="%s"\n' % (key, (host if key == "CANVAS_HOST"
                                         else token) or ""))
    return ("completed", env_path,
            "%s 原先缺少 %s，已追加空行待填（其余内容未改动）。" % (env_path, "、".join(missing)))
