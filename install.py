#!/usr/bin/env python3
"""复制 OpenAgent 固定载荷，通过 Hermes 原生命令启用和配置；不接触 OAuth 凭据。"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from desktop_onboarding import verify_desktop


SKILLS = (
    "openagent-first-task-router", "openagent-guide-agent", "openagent-search-agent",
    "openagent-run-agent", "openagent-query-account",
)
FILES = (
    "README.md", "INSTALL.md", "INSTALL.en.md", "plugin.json", "install.py", "uninstall.py",
    "desktop_onboarding.py", "desktop-onboarding.js",
    *(f"skills/{name}/SKILL.md" for name in SKILLS),
    "skills/openagent-run-agent/scripts/cos_upload.cjs",
    "skills/openagent-run-agent/scripts/cos_sdk.cjs.gz",
    "skills/openagent-run-agent/scripts/cos_sdk.lock.json",
    "skills/openagent-first-task-router/references/result-validation-and-delivery.md",
    "skills/openagent-login/runtime-sign-in.md",
)
RECEIPT = ".openagent-hermes-install.json"
RECEIPT_FORMAT = "openagent-hermes-install-v1"
CACHE = "skills/openagent-run-agent/scripts/.cos-sdk"
MCP_KEY = "mcp_servers.openagent"
ABSENT = object()
MCP_CONFIG = {
    "url": "https://openagent.org/mcp/v1/open-agent",
    "auth": "oauth",
    "enabled": True,
    "connect_timeout": 315,
    "timeout": 1800,
    "headers": {
        "X-OASN-MCP-OAuth": "required",
        "X-OASN-Client-Source": "hermes",
        "X-OASN-MCP-Content-Mode": "text-compatible",
    },
}


def read_payload(source: Path) -> dict[str, bytes]:
    """只读取固定安装清单，禁止将符号链接和开发文件带入客户端。"""
    payload = {}
    for name in FILES:
        path = source / name
        if not path.is_file() or path.resolve() != path:
            raise ValueError(f"安装文件缺失或包含符号链接：{name}")
        payload[name] = path.read_bytes()
    manifest = json.loads(payload["plugin.json"])
    if (manifest.get("name") != "openagent"
            or manifest.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"):
        raise ValueError("安装清单不是 OpenAgent Hermes 插件")
    scripts = "skills/openagent-run-agent/scripts/"
    lock = json.loads(payload[scripts + "cos_sdk.lock.json"])
    bundle = lock.get("bundle", {})
    if (lock.get("format") != "openagent-cos-node-sdk-v1"
            or bundle.get("file") != "cos_sdk.cjs.gz"):
        raise ValueError("COS SDK 锁定清单无效")
    archive = payload[scripts + "cos_sdk.cjs.gz"]
    for prefix, data in (("", archive), ("uncompressed_", gzip.decompress(archive))):
        if len(data) != bundle.get(prefix + "size") or hashlib.sha256(data).hexdigest() != bundle.get(prefix + "sha256"):
            raise ValueError("COS SDK 归档或解压内容与锁定摘要不符")
    return payload


def receipt_for(payload: dict[str, bytes]) -> dict:
    return {"format": RECEIPT_FORMAT, "files": {
        name: hashlib.sha256(data).hexdigest() for name, data in payload.items()
    }}


def check_target(target: Path, payload: dict[str, bytes]) -> bool:
    """只复用本安装器写入且未改变的相同载荷；初版不自动升级。"""
    if target.resolve() != target:
        raise ValueError("插件安装路径不能包含符号链接")
    if not target.exists():
        return False
    receipt = target / RECEIPT
    if not target.is_dir() or not receipt.is_file() or receipt.is_symlink():
        raise ValueError("已有同名插件缺少本安装器回执，停止安装")
    if json.loads(receipt.read_text(encoding="utf-8")) != receipt_for(payload):
        raise ValueError("已有插件的版本或载荷不同，停止覆盖；请先核对本地修改")
    for path in target.rglob("*"):
        name = path.relative_to(target).as_posix()
        if path.is_symlink():
            raise ValueError("已有插件包含符号链接，停止安装")
        if name == CACHE or name.startswith(CACHE + "/"):
            continue
        if path.is_file() and name not in {*FILES, RECEIPT}:
            raise ValueError(f"已有插件包含清单外文件，停止安装：{name}")
    for name, data in payload.items():
        path = target / name
        if not path.is_file() or path.read_bytes() != data:
            raise ValueError(f"已有插件文件被修改，停止覆盖：{name}")
    return True


def copy_payload(target: Path, payload: dict[str, bytes]) -> None:
    """先在同目录准备完整载荷，再发布为新插件目录。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".openagent-install-", dir=target.parent) as temporary:
        staged = Path(temporary) / "openagent"
        staged.mkdir()
        for name, data in payload.items():
            path = staged / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (staged / RECEIPT).write_text(
            json.dumps(receipt_for(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if target.exists() or target.is_symlink():
            raise ValueError("准备期间目标插件目录已出现，停止安装")
        staged.rename(target)


def profile_args(env: dict) -> list[str]:
    # 根目录可能被 active_profile 重定向；与卸载器一样固定实际目标。
    return [] if Path(env["HERMES_HOME"]).parent.name == "profiles" else ["-p", "default"]


def command(hermes: str, args: list[str], env: dict, *, capture: bool = True):
    """配置输出只在内存解析；错误不回显未知配置或认证材料。"""
    return subprocess.run([hermes, *profile_args(env), *args], env=env,
                          text=True, capture_output=capture, check=False)


def read_mcp(hermes: str, env: dict):
    result = command(hermes, ["config", "get", MCP_KEY, "--json"], env)
    if result.returncode:
        if f"Config key not set: {MCP_KEY}" in result.stdout + result.stderr:
            return ABSENT
        raise RuntimeError("无法通过 Hermes 读取 OpenAgent MCP 配置，停止安装")
    try:
        return json.loads(result.stdout)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Hermes 返回的 OpenAgent MCP 配置不是有效 JSON，停止安装") from exc


def run_required(hermes: str, args: list[str], env: dict, *, capture: bool = True) -> None:
    if command(hermes, args, env, capture=capture).returncode:
        raise RuntimeError(f"Hermes {' '.join(args[:2])} 失败；已保留现场，不自动重试")


def parse_acceptance(output: str) -> bool:
    """只认可本次原生事件中的账号调用与成功终态，不读取模型的成功声明。"""
    calls = results = 0
    account_ok = finished = False
    try:
        for line in output.splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict) or finished:
                return False
            if event.get("name") == "mcp__openagent__openagent_account_credits":
                if event.get("type") == "tool_use":
                    calls += 1
                    if calls != 1 or event.get("input") != {}:
                        return False
                elif event.get("type") == "tool_result":
                    results += 1
                    if calls != 1 or results != 1 or event.get("is_error") is not False:
                        return False
                    data = json.loads(event["output"])
                    if not isinstance(data, dict) or "error" in data:
                        return False
                    data = data.get("structuredContent", data.get("result", data))
                    if isinstance(data, str):
                        data = json.loads(data)
                    account_ok = isinstance(data, dict) and data.get("success") is True
                    if not account_ok:
                        return False
            elif event.get("type") == "result":
                if type(event.get("exit_code")) is not int or event["exit_code"] != 0 or event.get("error"):
                    return False
                finished = True
        return calls == results == 1 and account_ok and finished
    except (KeyError, TypeError, ValueError):
        return False


def verify_session(hermes: str, env: dict) -> None:
    """新建一次独立会话验收；原始账号和模型输出只在内存解析。"""
    print("正在新 Hermes 会话中验证 OpenAgent 账号连接，请等待同一个安装进程。", flush=True)
    # 冷启动按 MCP 连接名过滤；mcp-openagent 是连接后注册的内部工具组名。
    args = [hermes, *profile_args(env), "chat", "--oneshot", "--format", "stream-json",
            "--toolsets", "skills,openagent", "--max-turns", "8", "--run-budget", "180",
            "-q", "OpenAgent 已安装，打开新用户引导"]
    try:
        with tempfile.TemporaryDirectory(prefix="openagent-hermes-verify-") as directory:
            session_env = {key: value for key, value in env.items()
                           if not key.startswith("HERMES_KANBAN_") and key != "HERMES_QUIET_TURN_REPORT_FILE"}
            session_env["TERMINAL_CWD"] = directory
            result = subprocess.run(args, env=session_env, cwd=directory, stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, timeout=600, check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError("新会话验收超时，账号连接尚未确认；不自动重新授权或重试") from None
    if result.returncode or not parse_acceptance(result.stdout):
        raise RuntimeError("新会话未取得完整的账号成功证据；安装文件已保留，账号连接尚未确认，不自动重试")
    print("OpenAgent 安装验收通过：新 Hermes 会话已真实调用账号工具，success=true。")
    print("可以在 Hermes CLI 中开始使用 OpenAgent。")


def install(source: Path, home: Path, hermes: str, *, skip_connect: bool = False, client: str = "auto") -> None:
    if client == "auto":
        is_desktop = (os.environ.get("HERMES_SESSION_SOURCE") == "desktop"
                      or os.environ.get("HERMES_DESKTOP_TERMINAL") == "1")
        client = "desktop" if is_desktop else "cli"
    if client not in {"desktop", "cli"}:
        raise ValueError("不支持的 Hermes 客户端")
    if not skip_connect and not sys.stdin.isatty():
        raise RuntimeError("完整安装需要交互式终端；Hermes terminal 请使用 background=true、pty=true，勿用管道或重定向 stdin")
    source, home = source.resolve(), home.expanduser().resolve()
    env = dict(os.environ, HERMES_HOME=str(home))
    target = home / "plugins" / "openagent"
    payload = read_payload(source)
    reused = check_target(target, payload)
    existing = read_mcp(hermes, env)
    if existing is not ABSENT and existing != MCP_CONFIG:
        raise ValueError("已有同名 MCP 配置与 OpenAgent 安装要求不同，停止覆盖")
    if not reused:
        copy_payload(target, payload)
    if existing is ABSENT:
        run_required(hermes, ["config", "set", MCP_KEY, json.dumps(MCP_CONFIG)], env)
    if read_mcp(hermes, env) != MCP_CONFIG:
        raise RuntimeError("Hermes MCP 配置回读不一致，停止安装")
    run_required(hermes, ["plugins", "enable", "openagent"], env)
    print(f"OpenAgent 安装文件及 MCP 配置已核对：{target}")
    if skip_connect:
        print("已跳过连接测试；尚未验证 OAuth、MCP 连通或真实业务调用。")
        return
    print("开始 Hermes 原生连接测试；如需授权，请完成 Hermes 打开的页面，勿重复发起登录。", flush=True)
    run_required(hermes, ["mcp", "test", "openagent"], env, capture=False)
    if client == "desktop":
        verify_desktop(target, home)
    else:
        verify_session(hermes, env)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-home", type=Path,
                        default=Path(os.environ.get("HERMES_HOME") or "~/.hermes"),
                        help="目标 Hermes 配置目录；默认沿用 HERMES_HOME 或 ~/.hermes")
    parser.add_argument("--skip-connect", action="store_true", help="仅安装并配置，不验证 OAuth 和 MCP 连接")
    parser.add_argument("--client", choices=("auto", "desktop", "cli"), default="auto",
                        help="验收客户端；自动识别 Desktop terminal，外部终端安装 Desktop 时指定 desktop")
    args = parser.parse_args(argv)
    try:
        hermes = shutil.which("hermes")
        if not hermes:
            raise RuntimeError("未找到 hermes 命令，请先安装并配置 Hermes")
        install(Path(__file__).resolve().parent, args.hermes_home, hermes,
                skip_connect=args.skip_connect, client=args.client)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"安装停止：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
