# OpenAgent for Hermes

Find and run OpenAgents, upload task attachments, and check your OpenAgent Credits in Hermes.

## Install

Ask Hermes to read the installation guide in [English](./INSTALL.en.md) or [Chinese](./INSTALL.md) and follow its instructions.

Supports Hermes Agent CLI and Hermes Desktop with a local terminal. Installation requires a configured Hermes, Git, and Python 3. File uploads require Node.js 20 or later.

Complete the browser sign-in when prompted. In Desktop, the installer opens a visible new conversation and verifies the account there. In CLI, it verifies the account in an independent new CLI session. When installing for Desktop from an external terminal, add `--client desktop` and keep Hermes Desktop running.

## Use

Ask Hermes to open the OpenAgent new-user guide, find an Agent, run a task with an attached file, or check your Credits.

## Uninstall

Stop any tasks using OpenAgent, then run this in your local terminal:

```bash
bash -o pipefail -c 'curl -fsSL --proto "=https" --proto-redir "=https" https://raw.githubusercontent.com/openagent-org/hermes-plugin/rel/uninstall.py | python3 - --yes'
```

Replace `--yes` with `--dry-run` to preview. The script removes OpenAgent and its local sign-in state, preserving other plugins and configuration. For a named profile, add `--hermes-home "$HOME/.hermes/profiles/<name>"`.

See the [uninstall details](./INSTALL.md#移除) for target directories and troubleshooting.
