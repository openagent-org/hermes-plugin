"""通过 Hermes 官方桌面插件 SDK 完成一次可见新对话验收。"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time


PROMPT = "OpenAgent 已安装，打开新用户引导"
FAILURES = {
    "unsupported_host": "当前 Hermes Desktop 缺少所需的原生插件能力",
    "profile_unavailable": "未连接到目标 Hermes 配置",
    "new_chat_timeout": "未确认可见的新对话输入框",
    "session_changed": "验收期间当前对话已改变",
    "account_invalid": "账号工具未返回严格的成功结果",
    "turn_failed": "新对话未正常完成",
    "evidence_missing": "新对话缺少完整的账号调用证据",
    "callback_failed": "桌面验收回执未确认",
    "timeout": "等待桌面验收超时",
}


def desktop_location(home: Path) -> tuple[Path, str]:
    """Desktop 插件属于应用根目录，命名 profile 的配置仍留在其原位置。"""
    if home.parent.name == "profiles":
        return home.parent.parent / "desktop-plugins", home.name
    return home / "desktop-plugins", "default"


def open_desktop() -> None:
    """只使用宿主注册的协议唤起窗口，不重新启动或控制界面元素。"""
    url = "hermes://open/"
    if sys.platform == "win32":
        os.startfile(url)
        return
    launcher = "open" if sys.platform == "darwin" else "xdg-open"
    try:
        result = subprocess.run([launcher, url], capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("无法通过 Hermes 原生链接打开 Desktop；未自动重试") from None
    if result.returncode:
        raise RuntimeError("Hermes Desktop 原生链接未被接收；未自动重试")


class ReceiptServer(HTTPServer):
    """随机地址只接收本次 SDK 的阶段回执，不接收账号正文或执行指令。"""

    def __init__(self):
        super().__init__(("127.0.0.1", 0), ReceiptHandler)
        self.timeout = 0.25
        self.path = "/" + secrets.token_urlsafe(32)
        self.phase = "waiting"
        self.session_id = None
        self.reason = None
        self.finished = threading.Event()

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(2)
        return connection, address

    def accept(self, data: dict) -> bool:
        if not isinstance(data, dict) or set(data) - {"phase", "session_id", "account_success", "reason"}:
            return False
        phase = data.get("phase")
        if phase == "ready" and self.phase == "waiting" and set(data) == {"phase"}:
            self.phase = "ready"
            return True
        session_id = data.get("session_id")
        valid_session = isinstance(session_id, str) and 0 < len(session_id) <= 160
        if phase == "sent" and self.phase == "ready" and valid_session:
            self.phase, self.session_id = phase, session_id
            return True
        if (phase == "complete" and self.phase == "sent" and session_id == self.session_id
                and data.get("account_success") is True):
            self.phase = phase
            self.finished.set()
            return True
        if phase == "failed" and self.phase in {"ready", "sent"} and data.get("reason") in FAILURES:
            self.phase, self.reason = phase, data["reason"]
            self.finished.set()
            return True
        return False


class ReceiptHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        # 回调地址包含一次性随机标识，不写入终端或日志。
        pass

    def do_POST(self):
        accepted = False
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if self.path == self.server.path and 0 < length <= 4096:
                accepted = self.server.accept(json.loads(self.rfile.read(length)))
        except (TypeError, ValueError):
            pass
        self.send_response(200 if accepted else 409)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(json.dumps({"ok": accepted}).encode())
        except (BrokenPipeError, ConnectionResetError):
            pass


def verify_desktop(source: Path, home: Path, *, timeout: float = 600) -> None:
    """临时插件只允许一次发送；进程结束后移除本次插件，保留真实对话。"""
    root, profile = desktop_location(home)
    if root.resolve() != root:
        raise ValueError("Hermes Desktop 插件目录包含符号链接，停止验收")
    template = (source / "desktop-onboarding.js").read_text(encoding="utf-8")
    if template.count("__OPENAGENT_DESKTOP_CONFIG__") != 1:
        raise ValueError("Hermes Desktop 验收模板不完整")
    root.mkdir(parents=True, exist_ok=True)
    plugin_id = "openagent-install-" + secrets.token_hex(12)
    target = root / plugin_id
    print("正在 Hermes Desktop 中创建新对话并发送新用户引导，请等待同一个安装进程。", flush=True)
    with ReceiptServer() as server:
        config = {"id": plugin_id, "callbackUrl": f"http://127.0.0.1:{server.server_port}{server.path}",
                  "profile": profile, "prompt": PROMPT, "timeoutMs": int(timeout * 1000)}
        content = template.replace("__OPENAGENT_DESKTOP_CONFIG__", json.dumps(config, ensure_ascii=False))
        published = False
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        worker.start()
        try:
            deadline = time.monotonic() + timeout
            # 完整目录原子移入官方监听目录，避免扫描半写入的插件。
            with tempfile.TemporaryDirectory(prefix=".openagent-desktop-", dir=root.parent) as temporary:
                staged = Path(temporary) / plugin_id
                staged.mkdir()
                (staged / "plugin.js").write_text(content, encoding="utf-8")
                staged.rename(target)
                published = True
            open_desktop()
            server.finished.wait(max(0, deadline - time.monotonic()))
            if server.phase != "complete":
                reason = FAILURES.get(server.reason, "未取得完整的 Desktop 新对话验收回执")
                raise RuntimeError(f"{reason}；安装文件及已创建的对话已保留，不自动重发提示或重新授权")
        finally:
            server.shutdown()
            worker.join()
            if published and target.exists():
                shutil.rmtree(target)
    print("OpenAgent 安装验收通过：Desktop 已打开新对话并发送引导，账号工具 success=true，回复已完成。")
