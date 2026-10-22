#!/usr/bin/env python3
"""核对安装归属后，用 Hermes 原生命令卸载当前目录中的 OpenAgent。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


RELEASE_0_1_0_FILES = {
    "README.md", "INSTALL.md", "INSTALL.en.md", "plugin.json", "install.py", "uninstall.py",
    "skills/openagent-first-task-router/SKILL.md",
    "skills/openagent-guide-agent/SKILL.md",
    "skills/openagent-search-agent/SKILL.md",
    "skills/openagent-run-agent/SKILL.md",
    "skills/openagent-query-account/SKILL.md",
    "skills/openagent-run-agent/scripts/cos_upload.cjs",
    "skills/openagent-run-agent/scripts/cos_sdk.cjs.gz",
    "skills/openagent-run-agent/scripts/cos_sdk.lock.json",
    "skills/openagent-first-task-router/references/result-validation-and-delivery.md",
    "skills/openagent-login/runtime-sign-in.md",
}
FILES = RELEASE_0_1_0_FILES | {"desktop_onboarding.py", "desktop-onboarding.js"}
LEGACY_FILES = (RELEASE_0_1_0_FILES - {
    "INSTALL.en.md", "uninstall.py", "skills/openagent-first-task-router/references/result-validation-and-delivery.md",
    "skills/openagent-login/runtime-sign-in.md",
}) | {"skills/openagent-run-agent/references/hermes-runtime.md"}
RECEIPT = ".openagent-hermes-install.json"
CACHE = "skills/openagent-run-agent/scripts/.cos-sdk"
MCP_KEY = "mcp_servers.openagent"
MCP_URL = "https://oasn-ow.haimawan.com/mcp/v1/open-agent"
OAUTH_FILES = ("openagent.json", "openagent.client.json", "openagent.meta.json", "openagent.cimd-off")
ABSENT = object()


def check_path(path: Path) -> None:
    if path.resolve() != path or path.is_symlink():
        raise ValueError("目标路径包含符号链接，停止卸载")


def check_plugin(target: Path) -> bool:
    """接受本安装器的新旧回执，但不删除未知安装或被修改的文件。"""
    check_path(target)
    if not target.exists():
        return False
    receipt = target / RECEIPT
    if not target.is_dir() or not receipt.is_file() or receipt.is_symlink():
        raise ValueError("已有同名插件缺少本安装器回执，停止卸载")
    try:
        data = json.loads(receipt.read_text(encoding="utf-8"))
        files = data["files"]
        if (data.get("format") != "openagent-hermes-install-v1" or not isinstance(files, dict)
                or set(files) not in (LEGACY_FILES, RELEASE_0_1_0_FILES, FILES)):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise ValueError("安装回执无效或文件清单不符，停止卸载") from None
    directories = {parent.as_posix() for name in files for parent in Path(name).parents if str(parent) != "."}
    for path in target.rglob("*"):
        name = path.relative_to(target).as_posix()
        check_path(path)
        if name == CACHE or name.startswith(CACHE + "/"):
            continue
        if not ((path.is_file() and name in {*files, RECEIPT}) or (path.is_dir() and name in directories)):
            raise ValueError("已有插件包含清单外文件，停止卸载")
    for name, digest in files.items():
        path = target / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("已有插件文件被修改，停止卸载；请先保存并核对本地修改")
    manifest = json.loads((target / "plugin.json").read_text(encoding="utf-8"))
    if (not isinstance(manifest, dict) or manifest.get("name") != "openagent"
            or manifest.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"):
        raise ValueError("插件清单不是 OpenAgent Hermes 插件，停止卸载")
    return True


def command(hermes: str, args: list[str], env: dict, *, input_text: str = ""):
    # 根目录可能被 active_profile 重定向；命名 profile 则直接沿用 HERMES_HOME。
    profile_args = [] if Path(env["HERMES_HOME"]).parent.name == "profiles" else ["-p", "default"]
    try:
        return subprocess.run([hermes, *profile_args, *args], env=env, input=input_text,
                              text=True, capture_output=True, timeout=60, check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Hermes 命令超时，已保留现场；不自动重试") from None


def read_config(hermes: str, env: dict, key: str):
    result = command(hermes, ["config", "get", key, "--json"], env)
    if result.returncode:
        if f"Config key not set: {key}" in result.stdout + result.stderr:
            return ABSENT
        raise RuntimeError("无法读取 Hermes 配置，停止卸载")
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise RuntimeError("Hermes 配置回读不是有效 JSON，停止卸载") from None


def check_cli_home(hermes: str, env: dict, home: Path) -> None:
    if (home / ".container-mode").exists() or (home / ".container-mode").is_symlink():
        raise ValueError("目标使用容器转发，请在实际 Hermes 配置所在的本地环境卸载")
    result = command(hermes, ["config", "path"], env)
    if result.returncode or result.stdout.strip() != str(home / "config.yaml"):
        raise RuntimeError("Hermes 实际配置路径与目标目录不一致，停止卸载")


def check_mcp(value) -> None:
    if value is not ABSENT and (not isinstance(value, dict) or value.get("url") != MCP_URL
                               or value.get("auth") != "oauth" or "command" in value or "args" in value):
        raise ValueError("同名 MCP 不属于预期的 OpenAgent OAuth 连接，停止卸载")


def oauth_files(home: Path) -> list[Path]:
    directory = home / "mcp-tokens"
    check_path(directory)
    paths = [directory / name for name in (*OAUTH_FILES, "openagent.client.json.bak")]
    for path in paths:
        check_path(path)
        if path.exists() and not path.is_file():
            raise ValueError("OpenAgent 本地认证路径不是普通文件，停止卸载")
    return paths


def uninstall(home: Path, hermes: str, *, yes: bool = False, dry_run: bool = False) -> None:
    home = Path(os.path.abspath(home.expanduser()))
    check_path(home)
    check_path(home / "config.yaml")
    target = home / "plugins" / "openagent"
    installed = check_plugin(target)
    paths = oauth_files(home)
    env = dict(os.environ, HERMES_HOME=str(home))
    check_cli_home(hermes, env, home)
    existing = read_config(hermes, env, MCP_KEY)
    check_mcp(existing)
    if not installed and existing is ABSENT and any(path.exists() for path in paths):
        raise ValueError("发现认证残留，但缺少安装或 MCP 归属证据，停止卸载")
    print(f"目标 Hermes 配置目录：{home}")
    print("将移除经核对的 OpenAgent 插件、MCP 连接和本地 OAuth 状态；保留其他配置与凭据。")
    if dry_run:
        print("预览完成，未执行卸载。")
        return
    if not yes:
        if not sys.stdin.isatty():
            raise RuntimeError("非交互式卸载需要 --yes；可先使用 --dry-run 预览")
        if input("确认卸载 OpenAgent？输入 yes 继续：").strip().lower() != "yes":
            raise RuntimeError("用户取消卸载，未执行修改")
    # 确认前后重新核对，防止等待期间目标被替换。
    if check_plugin(target) != installed or read_config(hermes, env, MCP_KEY) != existing:
        raise RuntimeError("确认期间安装状态发生变化，停止卸载")
    check_cli_home(hermes, env, home)
    paths = oauth_files(home)
    if existing is not ABSENT:
        result = command(hermes, ["mcp", "remove", "openagent"], env, input_text="y\n")
        if result.returncode:
            raise RuntimeError("Hermes mcp remove 失败，已保留现场；不自动重试")
        if read_config(hermes, env, MCP_KEY) is not ABSENT:
            raise RuntimeError("MCP 配置仍然存在，卸载未完成")
        if any(path.exists() for path in paths[:len(OAUTH_FILES)]):
            raise RuntimeError("Hermes 未清除本地 OAuth 状态，已保留插件；卸载未完成")
    # 原生移除不清历史 client 备份；配置已缺失时也不会清理凭据。
    # 只有上面的插件回执或 MCP 归属已确认时，才补清这些精确路径。
    if installed or existing is not ABSENT:
        for path in oauth_files(home):
            path.unlink(missing_ok=True)
    if installed:
        if not check_plugin(target):
            raise RuntimeError("插件目录在卸载期间消失，停止匹配其他同名插件")
        if command(hermes, ["plugins", "remove", "openagent"], env).returncode:
            raise RuntimeError("Hermes plugins remove 失败，已保留现场；不自动重试")
    if target.exists() or target.is_symlink():
        raise RuntimeError("插件目录仍然存在，卸载未完成")
    if read_config(hermes, env, MCP_KEY) is not ABSENT:
        raise RuntimeError("MCP 配置仍然存在，卸载未完成")
    plugins = read_config(hermes, env, "plugins")
    if plugins is not ABSENT:
        if not isinstance(plugins, dict):
            raise RuntimeError("无法核对插件配置，卸载未完成")
        for key, expected_type in (("enabled", list), ("disabled", list), ("entries", dict)):
            value = plugins.get(key, expected_type())
            if not isinstance(value, expected_type):
                raise RuntimeError("无法核对插件配置，卸载未完成")
            if "openagent" in value:
                raise RuntimeError("OpenAgent 插件配置仍有残留，卸载未完成")
    if any(path.exists() for path in oauth_files(home)):
        raise RuntimeError("本地 OAuth 状态仍有残留，卸载未完成")
    print("OpenAgent 卸载完成：插件、MCP 和本地认证状态已核对；未撤销服务端授权。")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-home", type=Path,
                        default=Path(os.environ.get("HERMES_HOME") or "~/.hermes"),
                        help="目标配置目录；默认 HERMES_HOME 或 ~/.hermes，不跟随 active_profile")
    parser.add_argument("--yes", action="store_true", help="确认卸载，不再询问")
    parser.add_argument("--dry-run", action="store_true", help="核对目标并预览，不执行卸载")
    args = parser.parse_args(argv)
    try:
        hermes = shutil.which("hermes")
        if not hermes:
            raise RuntimeError("未找到 hermes 命令，请先恢复 Hermes CLI")
        uninstall(args.hermes_home, hermes, yes=args.yes, dry_run=args.dry_run)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"卸载停止：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
