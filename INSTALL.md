# 安装 OpenAgent：Hermes

将本指南交给 Hermes，并说“请按这份指南完成 OpenAgent 安装和验收”。Hermes 负责检查环境、下载安装、等待授权和完成新会话验收；需要登录时，用户只在 Hermes 打开的网页完成授权。

适用于 Hermes Agent CLI 与 Hermes Desktop 的本地终端，本指南核对 Hermes 0.22.2。需要已有可用的 `hermes` 命令、已配置的模型、Python 3 和 Git；本地文件上传另需 Node.js 20+。不要求用户提供 Token、密码或其他客户端凭据。

按顺序完成下面四步。不要在后台进程仍运行时宣布成功，也不要把新会话验收留给用户手动操作。

## 1. 检查环境并取得文件

先检查 `hermes --version`、`python3 --version` 和 `git --version`。确认 terminal 使用用户的本地环境并支持 `pty`，安装到当前 `HERMES_HOME`（未设置时为 `~/.hermes`）。若使用容器、远程沙箱或缺少本地 PTY，停止并说明需要在目标 Hermes 的本地终端继续，不安装到另一个环境。

先用 `mktemp -d /tmp/openagent-hermes.XXXXXX` 取得新的空目录，记住实际返回路径，再下载 GitHub 的 `rel` 分支：

```bash
git clone --depth 1 --branch rel https://github.com/openagent-org/hermes-plugin.git <实际安装目录>
```

仅 DNS、连接、超时、传输中断或 HTTP 5xx 下载失败时，可改用 `https://gitee.com/openagent-org/hermes-plugin.git` 下载一次；分支仍为 `rel`，使用另一个新目录，不覆盖失败目录或用户文件。权限拒绝、证书错误、401/403/404/429/451、文件校验、安装或 OAuth 失败不换源。不要把 `rel` 传给 `hermes plugins install --ref`，本机版本的该参数要求完整提交 SHA。

## 2. 在交互式后台终端启动一次安装

先告知用户：“我将安装 OpenAgent；如果 Hermes 打开授权页，请在网页完成授权，我会等待并自动验证。”然后使用 Hermes 的 `terminal` 工具，替换下面的路径，执行一次：

```json
{
  "command": "python3 <实际安装目录>/install.py",
  "background": true,
  "pty": true,
  "timeout": 1200,
  "notify": true
}
```

安装路径含空格时正确引用路径。`background=true` 和 `pty=true` 必须同时设置；不要用普通非交互式 terminal、管道或 stdin 重定向运行完整安装。首次 OAuth 需要 TTY，安装器发现缺少 TTY 时会在修改前停止。用户自己操作时，在本地交互式终端直接运行同一条 Python 命令即可。

`--client auto` 是默认值：`HERMES_SESSION_SOURCE=desktop` 或 `HERMES_DESKTOP_TERMINAL=1` 时使用 Desktop 验收，其他环境使用 CLI 验收。可用 `--client desktop` 或 `--client cli` 明确选择。用户从外部终端为 Hermes Desktop 安装时，必须给上述 Python 命令追加 `--client desktop`，并保持目标 Desktop 运行；不能把普通终端的 CLI 验收当作 Desktop 新对话验收。

记住工具返回的 `session_id`。不要因为一次 terminal 调用已经返回，就启动第二份安装器。

## 3. 等待同一个进程完成授权与验收

使用 `process_manage` 的 `poll` 查看状态，或 `wait` 最多等待 60 秒，再继续检查同一个 `session_id`：

```json
{"action":"wait","session_id":"<上一步返回的 session_id>","timeout":60}
```

网页授权由 Hermes 原生 MCP 自动发起，用户在页面完成。等待期间简短说明进度，不再运行登录、安装器或额外的 `mcp test`，不自行补开授权 URL，不把授权地址或认证材料复制到回复中。

安装器连接通过后，按选定客户端创建一次新会话，发送完整提示词“OpenAgent 已安装，打开新用户引导”，读取已安装 Skill 并验证账号工具：

- Desktop：通过 Hermes 官方磁盘插件 SDK 打开一个用户可见的新对话，并在该对话发送提示。安装器从这个真实对话核对账号调用与结束状态，不另开后台 CLI 代替；验收结束后移除本次临时插件，保留新对话供用户继续使用。
- CLI：继续创建独立 Hermes CLI 子会话，完成相同的引导与账号验收。CLI 成功不表示 Desktop 已创建新对话。

新会话验收总时限为 600 秒，包含创建会话、MCP 启动、模型处理和正常收尾；Hermes CLI 的 `--run-budget` 是软收尾提示，不能代替这个总时限。新会话不读取本安装指南、不递归安装、不自动执行示例任务。外层安装进程只接收验收状态，不打印账号余额、内部标识或原始对话正文。Desktop 失败时不自动改用 CLI 验收。

## 4. 按终态交付

只有同一个进程退出码为 0，且输出包含“OpenAgent 安装验收通过”，才能告知用户安装及账号连接验证成功。此标记要求新会话实际调用一次 `openagent_account_credits`、返回严格的 `success=true`，且会话正常结束；插件列表、工具列表、OAuth 成功或模型说“安装成功”均不能单独替代。

Desktop 完成后告知：“OpenAgent 已安装，并已在新打开的 Desktop 对话中通过账号验证，可以在该对话继续使用。”CLI 完成后告知：“OpenAgent 已安装，并已通过独立 CLI 新会话的账号验证，可以开始使用。”不要把 CLI 的结果说成 Desktop 已跳转，也不要将 Desktop 新对话验收留给用户手动补做。

若进程失败、取消、超时或状态未知，保留现场并报告具体失败阶段，不自动重放安装、账号调用或 OAuth。验收未确认本身不能证明 OAuth 过期或模型 API 故障，不能凭无关历史日志推断原因。用户明确要求重新登录时才使用 `hermes mcp login openagent`；它会重置该连接的旧认证，不能用作只读检查。新会话模型不可用或账号结果未确认时，只能说明安装文件已写入、业务验收未通过。

## 安装器的修改范围

安装器把固定清单复制到当前 Hermes 配置目录的 `plugins/openagent`，通过原生命令启用插件，并登记名为 `openagent` 的 MCP：

- 地址：`https://openagent.org/mcp/v1/open-agent`。
- 认证：Hermes 原生 OAuth，凭据由 Hermes 管理。
- 请求头：`X-OASN-MCP-OAuth: required`、`X-OASN-MCP-Content-Mode: text-compatible`。
- 连接等待：315 秒，为首次浏览器授权留出时间。
- 工具等待：1800 秒（原生 `timeout` 字段），覆盖选择等待和同步执行；到时无可信终态时不能重放任务。

其他插件、MCP 和模型配置保留。已有同名目录缺少本安装器回执、安装文件被修改或同名 MCP 不匹配时停止；不删除或覆盖未知来源。同版本相同载荷可重复核对，不自动覆盖不同版本；更新前需先检查本地修改并使用下文卸载入口移除旧版本。

`--skip-connect` 仅安装文件及配置，跳过 OAuth、联网与新会话验收，不能报告安装验收成功。`--hermes-home <目录>` 可用于已配置模型的隔离环境，连接和新会话始终使用该目录。

Desktop 验收临时使用官方磁盘插件入口创建新对话；安装结束清理本次临时插件，不修改或删除用户的其他桌面插件和对话。安装目标必须属于当前 Desktop 的本机配置根目录，验收只使用对应的本地 profile；目标 Desktop 未加载本次临时插件时停止。

新会话验收使用当前 Hermes 模型，因此会产生正常的模型调用；不提交付费 Agent 任务。工具使用 `mcp__openagent__` 前缀；Skills 通过宿主发现名称，不硬编码命名空间。浏览或选择 Agent 不等于授权执行任务。

## 移除

使用 [README 中的卸载命令](https://github.com/openagent-org/hermes-plugin/blob/rel/README.md#uninstall)。卸载前结束相关任务，并在插件安装目录之外执行命令。

`uninstall.py` 支持 `--dry-run`、`--yes` 和 `--hermes-home`。默认处理 `HERMES_HOME`，未设置时处理 `~/.hermes`，不跟随 `hermes profile use` 保存的选择。命名 profile 需追加 `--hermes-home "$HOME/.hermes/profiles/<名称>"`，明确指定目标。预览不执行删除，Hermes 读取配置时可能维护自己的配置备份。

卸载器先核对本安装器回执、文件摘要和 MCP 归属，再通过 Hermes 原生命令移除插件和连接，并检查本地 OAuth 状态。用户修改、未知同名安装或配置冲突时停止；保留其他插件、MCP、模型配置和凭据。本地清理不等于服务端撤销授权，不要直接删除共享配置目录。

失败、清理未完成或状态未知时保留现场，不自动重试或换源重放；核对原因后再明确执行。重复卸载已清理的目标可正常结束，之后可按本指南重新安装。
