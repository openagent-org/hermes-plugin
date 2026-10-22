# Install OpenAgent in Hermes

Give this guide to Hermes and say, "Please follow this guide to install and verify OpenAgent." Hermes checks the environment, downloads and installs the files, waits for authorization, and completes verification in a new session. When sign-in is needed, the user authorizes access only on the page opened by Hermes.

This guide applies to Hermes Agent CLI and Hermes Desktop with a local terminal and has been checked against Hermes 0.22.2. It requires a working `hermes` command, a configured model, Python 3, and Git. Local file uploads also require Node.js 20+. The user does not need to provide a token, password, or credentials from another client.

Complete the following four steps in order. Do not announce success while a background process is still running, or leave new-session verification for the user to perform manually.

## 1. Check the environment and retrieve the files

First check `hermes --version`, `python3 --version`, and `git --version`. Confirm that the terminal uses the user's local environment and supports `pty`. Install into the current `HERMES_HOME`, or `~/.hermes` if it is unset. If the terminal uses a container or remote sandbox, or lacks a local PTY, stop and explain that installation must continue in the target Hermes's local terminal. Do not install into another environment.

First use `mktemp -d /tmp/openagent-hermes.XXXXXX` to obtain a new empty directory, retain the actual returned path, and then download the GitHub `rel` branch. Replace `<actual-installation-directory>` with that actual directory:

```bash
git clone --depth 1 --branch rel https://github.com/openagent-org/hermes-plugin.git <actual-installation-directory>
```

Only after a DNS, connection, timeout, interrupted-transfer, or HTTP 5xx download failure may you download once from `https://gitee.com/openagent-org/hermes-plugin.git`. Keep the `rel` branch and use another new directory; do not overwrite the failed directory or user files. Do not switch sources for denied permission, certificate errors, HTTP 401/403/404/429/451, file validation failures, installation failures, or OAuth failures. Do not pass `rel` to `hermes plugins install --ref`; this parameter requires a full commit SHA in the checked local version.

## 2. Start installation once in an interactive background terminal

First tell the user: "I will install OpenAgent. If Hermes opens an authorization page, please authorize access there; I will wait and verify the installation automatically." Then use the Hermes `terminal` tool, replace the path below, and execute once:

```json
{
  "command": "python3 <actual-installation-directory>/install.py",
  "background": true,
  "pty": true,
  "timeout": 1200,
  "notify": true
}
```

Quote the installation path correctly if it contains spaces. Both `background=true` and `pty=true` are required. Do not run the full installation through an ordinary non-interactive terminal, a pipe, or stdin redirection. Initial OAuth requires a TTY; the installer stops before making changes if no TTY is available. A user running the installation themselves can execute the same Python command directly in a local interactive terminal.

`--client auto` is the default: it selects Desktop verification when `HERMES_SESSION_SOURCE=desktop` or `HERMES_DESKTOP_TERMINAL=1`, and CLI verification otherwise. Use `--client desktop` or `--client cli` to select explicitly. When installing for Hermes Desktop from an external terminal, append `--client desktop` to the Python command above and keep the target Desktop running. Verification in an ordinary terminal's CLI session does not verify a new Desktop conversation.

Retain the `session_id` returned by the tool. Do not start a second installer just because one terminal call has returned.

## 3. Wait for the same process to complete authorization and verification

Use `process_manage` with `poll` to inspect the status, or `wait` for at most 60 seconds, then continue checking the same `session_id`. Replace the placeholder below with the `session_id` returned in the previous step:

```json
{"action":"wait","session_id":"<session_id-from-previous-step>","timeout":60}
```

Hermes's native MCP automatically opens the authorization flow, and the user completes it on the page. Give brief progress updates while waiting. Do not run another login, installer, or additional `mcp test`; do not open an authorization URL yourself or copy authorization URLs or authentication materials into replies.

After the connection check passes, the installer creates one new session in the selected client, sends the exact full prompt "OpenAgent 已安装，打开新用户引导", reads the installed Skill, and verifies the account tool. Keep this prompt in Chinese exactly as written:

- Desktop: use the official Hermes disk plugin SDK to open a new conversation visible to the user and send the prompt there. The installer verifies the account call and completion in that actual conversation; it does not substitute a background CLI session. After verification ends, it removes this temporary plugin and preserves the new conversation for continued use.
- CLI: create an independent Hermes CLI child session for the same guidance and account verification. CLI success does not mean a new Desktop conversation was created.

New-session verification has a total limit of 600 seconds, including session creation, MCP startup, model processing, and normal shutdown. Hermes CLI's `--run-budget` is a soft wrap-up hint and cannot replace this total limit. The new session does not read this installation guide, recursively install, or automatically execute example tasks. The outer installation process receives only the verification status and does not print the account balance, internal identifiers, or raw conversation content. A Desktop failure does not automatically fall back to CLI verification.

## 4. Report the final state

Tell the user that installation and account connection verification succeeded only if the same process exits with code 0 and its output contains "OpenAgent 安装验收通过". This marker requires the new session to actually call `openagent_account_credits` once, receive a strict `success=true`, and end normally. A plugin list, tool list, successful OAuth, or a model saying "installation succeeded" cannot independently replace these requirements.

After Desktop completion, tell the user: "OpenAgent is installed and has passed account verification in the newly opened Desktop conversation. You can continue using it there." After CLI completion, tell the user: "OpenAgent is installed and has passed account verification in an independent new CLI session. You can start using it." Do not describe a CLI result as a Desktop navigation, or leave Desktop new-conversation verification for the user to complete manually.

If the process fails, is cancelled, times out, or has an unknown state, preserve the current state and report the specific failed stage. Do not automatically replay installation, the account call, or OAuth. Unconfirmed verification alone does not prove that OAuth has expired or the model API is faulty; do not infer the cause from unrelated historical logs. Use `hermes mcp login openagent` only when the user explicitly requests signing in again. It resets the connection's previous authentication and must not be used as a read-only check. If the model in the new session is unavailable or the account result is unconfirmed, report only that the installation files have been written and functional verification has not passed.

## What the installer changes

The installer copies a fixed file list into `plugins/openagent` under the current Hermes configuration directory, enables the plugin through native commands, and registers an MCP connection named `openagent`:

- Endpoint: `https://oasn-ow.haimawan.com/mcp/v1/open-agent`.
- Authentication: Hermes native OAuth, with credentials managed by Hermes.
- Headers: `X-OASN-MCP-OAuth: required` and `X-OASN-MCP-Content-Mode: text-compatible`.
- Connection wait: 315 seconds, allowing time for initial browser authorization.
- Tool wait: 1800 seconds (the native `timeout` field), covering selection waits and synchronous execution. Do not replay a task if the timeout ends without a trusted final state.

Other plugins, MCP connections, and model configuration are preserved. Stop if an existing directory with the same name lacks this installer's receipt, installed files have been modified, or an MCP connection with the same name does not match. Do not delete or overwrite content from unknown sources. Identical payloads of the same version can be checked again. The installer does not automatically overwrite a different version; before updating, inspect local modifications and use the uninstall entry point below to remove the old version.

`--skip-connect` installs only files and configuration, skipping OAuth, network access, and new-session verification. It must not be reported as successful installation verification. `--hermes-home <directory>` can target an isolated environment with a configured model; both the connection and the new session always use that directory. Replace `<directory>` with the target directory.

Desktop verification temporarily uses the official disk plugin entry point to create a new conversation. Installation removes this temporary plugin afterward without modifying or deleting the user's other Desktop plugins or conversations. The installation target must belong to the running Desktop app's local configuration root. Verification uses its matching local profile; if Desktop does not load this temporary plugin, verification stops.

New-session verification uses the current Hermes model and therefore makes a normal model call. It does not submit a paid Agent task. Tools use the `mcp__openagent__` prefix; Skills use host-discovered names without hardcoded namespaces. Browsing or selecting an Agent does not authorize task execution.

## Uninstall

Use the [uninstall command in the README](https://github.com/openagent-org/hermes-plugin/blob/rel/README.md#uninstall). Before uninstalling, end related tasks and run the command outside the plugin installation directory.

`uninstall.py` supports `--dry-run`, `--yes`, and `--hermes-home`. By default, it targets `HERMES_HOME`, or `~/.hermes` if unset; it does not follow the selection saved by `hermes profile use`. For a named profile, append `--hermes-home "$HOME/.hermes/profiles/<profile-name>"` to specify the target explicitly, replacing `<profile-name>` with the profile name. A preview does not delete anything, although Hermes may maintain its own configuration backups when reading configuration.

The uninstaller first checks this installer's receipt, file digests, and MCP ownership. It then removes the plugin and connection through native Hermes commands and checks the local OAuth state. It stops for user modifications, an unknown installation with the same name, or configuration conflicts, while preserving other plugins, MCP connections, model configuration, and credentials. Local cleanup does not revoke server-side authorization; do not delete the shared configuration directory directly.

If removal fails, cleanup is incomplete, or the state is unknown, preserve the current state. Do not automatically retry or switch sources to replay the operation; inspect the cause before explicitly running it again. Repeating removal for an already cleaned target can end normally, after which you can reinstall using this guide.
